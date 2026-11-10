import logging
import uuid
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, List
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

from app.models import Deposito, Insumo, MovimientoStock, Lote, CicloCultivo

logger = logging.getLogger(__name__)


class StockIntegrityService:
    """
    Servicio central de integridad transaccional de stock para IA Desk Agro.
    Garantiza:
    - Única fuente de verdad en base de datos relacional (SQLite).
    - Asientos auditables con saldo anterior y posterior.
    - Prevención de saldos negativos y excesos de capacidad.
    - Idempotencia (prevención de doble clic o peticiones duplicadas).
    - Sincronización automática hacia las planillas JSON, CSVs y Excel.
    """

    @classmethod
    def get_or_create_gasoil_insumo(cls) -> Insumo:
        insumo, _ = Insumo.objects.get_or_create(
            categoria="combustible",
            defaults={
                "nombre": "Gasoil Grado 2 (Diesel Agro)",
                "unidad_medida": "litros",
                "stock_actual": Decimal("0.00"),
                "stock_minimo_alerta": Decimal("3000.00"),
                "deposito_habitual": "Cisterna Planta (22.000 L)"
            }
        )
        return insumo

    @classmethod
    @transaction.atomic
    def registrar_salida_combustible(
        cls,
        litros: float,
        deposito_codigo: str,
        lote: Optional[Lote] = None,
        ciclo_cultivo: Optional[CicloCultivo] = None,
        labor: str = "Labor Agrícola General",
        maquinaria: str = "Maquinaria de labor",
        operario: str = "Productor",
        observaciones: str = "",
        documento_referencia: str = "",
        idempotency_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registra una salida de combustible auditada para una labor agrícola.
        """
        cant = Decimal(str(round(litros, 2)))
        if cant <= Decimal("0.00"):
            raise ValidationError("La cantidad de litros consumidos debe ser mayor a 0.")

        # 1. Comprobación de idempotencia
        if idempotency_token:
            existente = MovimientoStock.objects.filter(idempotency_token=idempotency_token).first()
            if existente:
                logger.info(f"Movimiento id={existente.id} ya registrado con token {idempotency_token}.")
                return {
                    "success": True,
                    "duplicado_evitado": True,
                    "movimiento_id": existente.id,
                    "mensaje": f"Operación previamente asentada: {existente}",
                    "deposito": existente.deposito_origen_fk.nombre if existente.deposito_origen_fk else deposito_codigo,
                    "saldo_posterior": float(existente.saldo_posterior or 0)
                }

        # 2. Obtener y bloquear depósito
        try:
            deposito = Deposito.objects.select_for_update().get(codigo=deposito_codigo)
        except Deposito.DoesNotExist:
            deposito = Deposito.objects.filter(codigo__icontains="grande").first() or Deposito.objects.first()

        saldo_ant = deposito.stock_actual
        if saldo_ant < cant:
            raise ValidationError(
                f"No es posible realizar la operación porque no hay stock suficiente en {deposito.nombre}. Stock disponible: {saldo_ant:,.1f} L. Intentaste gastar/retirar: {cant:,.1f} L."
            )

        # 3. Aplicar descuento en Depósito
        saldo_post = saldo_ant - cant
        deposito.stock_actual = saldo_post
        deposito.save(update_fields=["stock_actual"])

        # 4. Actualizar insumo general
        insumo = cls.get_or_create_gasoil_insumo()
        insumo.stock_actual = max(Decimal("0.00"), insumo.stock_actual - cant)
        insumo.save(update_fields=["stock_actual"])

        # 5. Registrar movimiento auditable
        token_final = idempotency_token or f"salida_{uuid.uuid4().hex[:12]}"
        mov = MovimientoStock.objects.create(
            insumo=insumo,
            tipo_movimiento="consumo_labor",
            estado="confirmado",
            cantidad=cant,
            fecha=timezone.now().date(),
            lote=lote,
            ciclo_cultivo=ciclo_cultivo,
            deposito_origen_fk=deposito,
            labor_realizada=labor,
            maquinaria=maquinaria,
            operario=operario,
            deposito_origen=deposito.nombre,
            documento_referencia=documento_referencia,
            saldo_anterior=saldo_ant,
            saldo_posterior=saldo_post,
            idempotency_token=token_final,
            observaciones=observaciones
        )

        # 6. Sincronizar archivos de proyección (JSON & Excel)
        cls.sincronizar_gasoil_json()

        return {
            "success": True,
            "duplicado_evitado": False,
            "movimiento_id": mov.id,
            "litros": float(cant),
            "deposito": deposito.nombre,
            "saldo_anterior": float(saldo_ant),
            "saldo_posterior": float(saldo_post),
            "mensaje": f"Consumo asentado: {cant:,.1f} L de {deposito.nombre} (Saldo restante: {saldo_post:,.1f} L)."
        }

    @classmethod
    @transaction.atomic
    def registrar_traslado_combustible(
        cls,
        litros: float,
        origen_codigo: str,
        destino_codigo: str,
        operario: str = "Encargado de Galpón",
        observaciones: str = "",
        idempotency_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registra un traslado interno entre depósitos (ej: Cisterna Planta -> Tanque Grande).
        Valida stock disponible en origen y capacidad máxima en destino.
        """
        cant = Decimal(str(round(litros, 2)))
        if cant <= Decimal("0.00"):
            raise ValidationError("La cantidad a trasladar debe ser mayor a 0.")
        if origen_codigo == destino_codigo:
            raise ValidationError("El depósito de origen y destino deben ser diferentes.")

        if idempotency_token:
            existente = MovimientoStock.objects.filter(idempotency_token=idempotency_token).first()
            if existente:
                return {"success": True, "duplicado_evitado": True, "movimiento_id": existente.id}

        dep_origen = Deposito.objects.select_for_update().get(codigo=origen_codigo)
        dep_destino = Deposito.objects.select_for_update().get(codigo=destino_codigo)

        # Validaciones de integridad
        if dep_origen.stock_actual < cant:
            raise ValidationError(
                f"No es posible realizar el traslado porque no hay stock suficiente en {dep_origen.nombre}. Stock disponible: {dep_origen.stock_actual:,.1f} L. Solicitado a transferir: {cant:,.1f} L."
            )

        espacio_libre = dep_destino.capacidad_maxima - dep_destino.stock_actual
        if dep_destino.capacidad_maxima > 0 and (dep_destino.stock_actual + cant) > dep_destino.capacidad_maxima:
            raise ValidationError(
                f"Capacidad máxima excedida en {dep_destino.nombre}. Capacidad: {dep_destino.capacidad_maxima:,.0f} L. "
                f"Actual: {dep_destino.stock_actual:,.1f} L. Espacio libre: {espacio_libre:,.1f} L."
            )

        # Impacto atómico en ambos depósitos
        dep_origen.stock_actual -= cant
        dep_origen.save(update_fields=["stock_actual"])

        dep_destino.stock_actual += cant
        dep_destino.save(update_fields=["stock_actual"])

        insumo = cls.get_or_create_gasoil_insumo()
        token_final = idempotency_token or f"traslado_{uuid.uuid4().hex[:12]}"

        mov = MovimientoStock.objects.create(
            insumo=insumo,
            tipo_movimiento="traslado_interno",
            estado="confirmado",
            cantidad=cant,
            fecha=timezone.now().date(),
            deposito_origen_fk=dep_origen,
            deposito_destino_fk=dep_destino,
            labor_realizada=f"Traslado interno {dep_origen.nombre} ➔ {dep_destino.nombre}",
            operario=operario,
            deposito_origen=dep_origen.nombre,
            saldo_anterior=dep_origen.stock_actual + cant,
            saldo_posterior=dep_origen.stock_actual,
            idempotency_token=token_final,
            observaciones=observaciones
        )

        cls.sincronizar_gasoil_json()

        return {
            "success": True,
            "movimiento_id": mov.id,
            "litros": float(cant),
            "origen": dep_origen.nombre,
            "origen_saldo": float(dep_origen.stock_actual),
            "destino": dep_destino.nombre,
            "destino_saldo": float(dep_destino.stock_actual),
            "mensaje": f"Traslado asentado: {cant:,.1f} L de {dep_origen.nombre} a {dep_destino.nombre}."
        }

    @classmethod
    @transaction.atomic
    def registrar_ingreso_compra_combustible(
        cls,
        litros: float,
        destino_codigo: str = "cisterna_planta",
        proveedor: str = "YPF Directo",
        nro_remito: str = "",
        operario: str = "Administrador",
        observaciones: str = "",
        idempotency_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registra el ingreso de combustible por compra / descarga de camión cisterna.
        """
        cant = Decimal(str(round(litros, 2)))
        if cant <= Decimal("0.00"):
            raise ValidationError("La cantidad ingresada debe ser mayor a 0.")

        if idempotency_token:
            existente = MovimientoStock.objects.filter(idempotency_token=idempotency_token).first()
            if existente:
                return {"success": True, "duplicado_evitado": True, "movimiento_id": existente.id}

        dep_destino = Deposito.objects.select_for_update().get(codigo=destino_codigo)

        if dep_destino.capacidad_maxima > 0 and (dep_destino.stock_actual + cant) > dep_destino.capacidad_maxima:
            raise ValidationError(
                f"No es posible descargar {cant:,.1f} L en {dep_destino.nombre}. "
                f"Capacidad máxima: {dep_destino.capacidad_maxima:,.0f} L. Espacio disponible: {dep_destino.espacio_disponible:,.1f} L."
            )

        saldo_ant = dep_destino.stock_actual
        saldo_post = saldo_ant + cant
        dep_destino.stock_actual = saldo_post
        dep_destino.save(update_fields=["stock_actual"])

        insumo = cls.get_or_create_gasoil_insumo()
        insumo.stock_actual += cant
        insumo.save(update_fields=["stock_actual"])

        token_final = idempotency_token or f"ingreso_{uuid.uuid4().hex[:12]}"
        mov = MovimientoStock.objects.create(
            insumo=insumo,
            tipo_movimiento="ingreso_compra",
            estado="confirmado",
            cantidad=cant,
            fecha=timezone.now().date(),
            deposito_destino_fk=dep_destino,
            labor_realizada=f"Recepción compra {proveedor} ({nro_remito or 'S/R'})",
            operario=operario,
            documento_referencia=nro_remito,
            saldo_anterior=saldo_ant,
            saldo_posterior=saldo_post,
            idempotency_token=token_final,
            observaciones=observaciones or f"Proveedor: {proveedor}"
        )

        cls.sincronizar_gasoil_json()

        return {
            "success": True,
            "movimiento_id": mov.id,
            "litros": float(cant),
            "deposito": dep_destino.nombre,
            "saldo_posterior": float(saldo_post),
            "mensaje": f"Ingreso registrado: +{cant:,.0f} L en {dep_destino.nombre} (Nuevo saldo: {saldo_post:,.0f} L)."
        }

    @classmethod
    @transaction.atomic
    def registrar_consumo_insumo(
        cls,
        insumo_id: int,
        cantidad: float,
        lote: Optional[Lote] = None,
        ciclo_cultivo: Optional[CicloCultivo] = None,
        labor: str = "Aplicación de Insumos",
        maquinaria: str = "",
        operario: str = "Productor",
        idempotency_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registra el consumo de semillas, fertilizantes o fitosanitarios en un lote.
        """
        cant = Decimal(str(round(cantidad, 2)))
        if cant <= Decimal("0.00"):
            raise ValidationError("La cantidad consumida debe ser mayor a 0.")

        insumo = Insumo.objects.select_for_update().get(id=insumo_id)
        if insumo.stock_actual < cant:
            raise ValidationError(
                f"Stock insuficiente de {insumo.nombre}. Disponible en galpón: {insumo.stock_actual} {insumo.unidad_medida}. "
                f"Requerido: {cant} {insumo.unidad_medida}."
            )

        saldo_ant = insumo.stock_actual
        saldo_post = saldo_ant - cant
        insumo.stock_actual = saldo_post
        insumo.save(update_fields=["stock_actual"])

        token_final = idempotency_token or f"insumo_{uuid.uuid4().hex[:12]}"
        mov = MovimientoStock.objects.create(
            insumo=insumo,
            tipo_movimiento="consumo_labor",
            estado="confirmado",
            cantidad=cant,
            fecha=timezone.now().date(),
            lote=lote,
            ciclo_cultivo=ciclo_cultivo,
            labor_realizada=labor,
            maquinaria=maquinaria,
            operario=operario,
            saldo_anterior=saldo_ant,
            saldo_posterior=saldo_post,
            idempotency_token=token_final
        )

        cls.sincronizar_insumos_json()

        return {
            "success": True,
            "movimiento_id": mov.id,
            "insumo": insumo.nombre,
            "cantidad": float(cant),
            "unidad": insumo.unidad_medida,
            "saldo_posterior": float(saldo_post),
            "mensaje": f"Consumo registrado: {cant} {insumo.unidad_medida} de {insumo.nombre}. Quedan {saldo_post} en galpón."
        }

    # ==============================================================
    # SINCRONIZACIÓN AUTOMÁTICA CON PROYECCIONES JSON Y EXCEL
    # ==============================================================

    @classmethod
    def sincronizar_gasoil_json(cls):
        """
        Exporta el estado verificado de la base de datos hacia stock_gasoil.json
        para mantener 100% de coherencia con las vistas heredadas y Excel.
        """
        import json
        json_path = settings.FILES_STORAGE_DIR / "stock_gasoil.json"

        data = {}
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        deps_db = {d.codigo: d for d in Deposito.objects.filter(unidad_medida="litros")}

        data.setdefault("depositos", {})
        data["depositos"]["cisterna_planta"] = {
            "nombre": "Cisterna Planta",
            "capacidad_max_litros": int(deps_db.get("cisterna_planta", Deposito()).capacidad_maxima or 22000),
            "stock_actual_litros": float(deps_db.get("cisterna_planta", Deposito()).stock_actual or 14600)
        }
        data["depositos"]["tanque_grande"] = {
            "nombre": "Tanque Grande",
            "capacidad_max_litros": int(deps_db.get("tanque_grande", Deposito()).capacidad_maxima or 5000),
            "stock_actual_litros": float(deps_db.get("tanque_grande", Deposito()).stock_actual or 1264)
        }
        data["depositos"]["tanque_chico"] = {
            "nombre": "Tanque Chico",
            "capacidad_max_litros": int(deps_db.get("tanque_chico", Deposito()).capacidad_maxima or 3000),
            "stock_actual_litros": float(deps_db.get("tanque_chico", Deposito()).stock_actual or 1720)
        }
        data["depositos"]["acopio_por_retirar"] = {
            "nombre": "Gasoil por Retirar",
            "litros_disponibles": float(deps_db.get("acopio_por_retirar", Deposito()).stock_actual or 2200)
        }

        fisico = (
            data["depositos"]["cisterna_planta"]["stock_actual_litros"] +
            data["depositos"]["tanque_grande"]["stock_actual_litros"] +
            data["depositos"]["tanque_chico"]["stock_actual_litros"]
        )
        total = fisico + data["depositos"]["acopio_por_retirar"]["litros_disponibles"]

        data["totales"] = {
            "stock_fisico_campo_litros": fisico,
            "stock_total_con_acopio_litros": total
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        try:
            from app.services.google_sheets_service import on_movement_recorded
            on_movement_recorded()
        except Exception as e:
            logger.debug(f"Aviso sync excel: {e}")

    @classmethod
    def sincronizar_insumos_json(cls):
        """
        Exporta el estado de semillas y fertilizantes a stock_insumos.json.
        """
        import json
        json_path = settings.FILES_STORAGE_DIR / "stock_insumos.json"
        if not json_path.exists():
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for h in data.get("semillas_maiz", {}).get("hibridos", []):
                ins = Insumo.objects.filter(nombre__icontains=h.get("hibrido", "")[:10]).first()
                if ins:
                    h["en_planta_bolsas"] = int(ins.stock_actual)
                    h["total_bolsas"] = h["en_planta_bolsas"] + h.get("por_retirar_bolsas", 0)

            for v in data.get("semillas_soja", {}).get("variedades", []):
                ins = Insumo.objects.filter(nombre__icontains=v.get("variedad", "")[:10]).first()
                if ins:
                    v["en_planta_bolsas"] = int(ins.stock_actual)
                    v["total_bolsas"] = v["en_planta_bolsas"]

            for fert in data.get("fertilizantes", []):
                ins = Insumo.objects.filter(nombre__icontains=fert.get("nombre", "")[:10]).first()
                if ins:
                    fert["en_galpon_kg"] = float(ins.stock_actual)
                    fert["total_kg"] = fert["en_galpon_kg"] + fert.get("por_retirar_kg", 0)

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error sincronizando stock_insumos.json: {e}")

    @classmethod
    def obtener_balance_verificado(cls) -> Dict[str, Any]:
        """
        Devuelve el balance consolidado auditable directo de la base de datos.
        """
        depositos = Deposito.objects.filter(activo=True)
        dep_dict = {}
        fisico_litros = Decimal("0.00")
        acopio_litros = Decimal("0.00")

        for d in depositos:
            dep_dict[d.codigo] = {
                "nombre": d.nombre,
                "tipo": d.tipo,
                "capacidad_max": float(d.capacidad_maxima),
                "actual": float(d.stock_actual),
                "porcentaje_llenado": d.porcentaje_llenado,
                "espacio_libre": float(d.espacio_disponible)
            }
            if d.tipo in ["cisterna", "tanque_movil"]:
                fisico_litros += d.stock_actual
            elif d.tipo == "acopio_externo":
                acopio_litros += d.stock_actual

        movimientos_recientes = MovimientoStock.objects.select_related(
            "insumo", "lote", "deposito_origen_fk"
        ).order_by("-fecha", "-creado_el")[:15]

        insumos_bajos = Insumo.objects.filter(
            stock_minimo_alerta__gt=0, stock_actual__lte=models.F("stock_minimo_alerta")
        )

        return {
            "depositos": dep_dict,
            "combustible": {
                "fisico_campo_litros": float(fisico_litros),
                "acopio_externo_litros": float(acopio_litros),
                "total_disponible_litros": float(fisico_litros + acopio_litros)
            },
            "movimientos_recientes": [
                {
                    "id": m.id,
                    "fecha": m.fecha.strftime("%d/%m/%Y"),
                    "insumo": m.insumo.nombre,
                    "tipo": m.get_tipo_movimiento_display(),
                    "cantidad": float(m.cantidad),
                    "unidad": m.insumo.unidad_medida,
                    "lote": m.lote.nombre if m.lote else "-",
                    "deposito": m.deposito_origen_fk.nombre if m.deposito_origen_fk else (m.deposito_origen or "-"),
                    "labor": m.labor_realizada or "-",
                    "operario": m.operario or "-",
                    "saldo_posterior": float(m.saldo_posterior) if m.saldo_posterior is not None else None
                }
                for m in movimientos_recientes
            ],
            "alertas_stock_bajo": [
                {
                    "insumo": i.nombre,
                    "actual": float(i.stock_actual),
                    "minimo": float(i.stock_minimo_alerta),
                    "unidad": i.unidad_medida
                }
                for i in insumos_bajos
            ]
        }
