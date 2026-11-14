# app/services/alertas_service.py
"""
Servicio Integral de Alertas de Stock Crítico y Configuración de Umbrales Mínimos.
Permite establecer niveles de seguridad personalizados para combustibles, semillas,
fertilizantes y agroquímicos, detectando automáticamente faltantes y niveles de reposición.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)

def get_umbrales_file() -> Path:
    return settings.FILES_STORAGE_DIR / "umbrales_stock_critico.json"

DEFAULT_UMBRALES: Dict[str, Dict[str, Any]] = {
    "combustibles": {
        "cisterna_planta": {"id": "cisterna_planta", "nombre": "Cisterna Planta", "minimo": 4000.0, "unidad": "Litros", "categoria": "Combustible"},
        "tanque_grande": {"id": "tanque_grande", "nombre": "Tanque Grande", "minimo": 800.0, "unidad": "Litros", "categoria": "Combustible"},
        "tanque_chico": {"id": "tanque_chico", "nombre": "Tanque Chico", "minimo": 500.0, "unidad": "Litros", "categoria": "Combustible"},
        "acopio_por_retirar": {"id": "acopio_por_retirar", "nombre": "Gasoil en Acopio YPF", "minimo": 1000.0, "unidad": "Litros", "categoria": "Combustible"}
    },
    "fertilizantes": {
        "FERT-01": {"id": "FERT-01", "nombre": "Fosfato Monoamónico (MAP)", "minimo": 500.0, "unidad": "kg", "categoria": "Fertilizante"},
        "FERT-02": {"id": "FERT-02", "nombre": "Urea Granulada", "minimo": 3000.0, "unidad": "kg", "categoria": "Fertilizante"},
        "FERT-03": {"id": "FERT-03", "nombre": "MicroEssentials SZ", "minimo": 2000.0, "unidad": "kg", "categoria": "Fertilizante"}
    },
    "semillas": {
        "MZ-DK7210": {"id": "MZ-DK7210", "nombre": "Dekalb DK 72-10 VT3P", "minimo": 10.0, "unidad": "bolsas", "categoria": "Semilla"},
        "MZ-P2089": {"id": "MZ-P2089", "nombre": "Pioneer P2089 VYHR", "minimo": 10.0, "unidad": "bolsas", "categoria": "Semilla"},
        "MZ-AX7784": {"id": "MZ-AX7784", "nombre": "Nidera AX 7784 VIP3", "minimo": 10.0, "unidad": "bolsas", "categoria": "Semilla"},
        "SJ-DM46R18": {"id": "SJ-DM46R18", "nombre": "Soja Don Mario DM 46R18", "minimo": 30.0, "unidad": "bolsas", "categoria": "Semilla"},
        "TR-MSINTA119": {"id": "TR-MSINTA119", "nombre": "Trigo Pan MS INTA 119", "minimo": 25.0, "unidad": "bolsas", "categoria": "Semilla"}
    },
    "fitosanitarios": {
        "FITO-01": {"id": "FITO-01", "nombre": "Glifosato 66% Concentrado", "minimo": 300.0, "unidad": "Litros", "categoria": "Fitosanitario"},
        "FITO-02": {"id": "FITO-02", "nombre": "2,4-D Enlist Colex-D", "minimo": 150.0, "unidad": "Litros", "categoria": "Fitosanitario"},
        "FITO-03": {"id": "FITO-03", "nombre": "Coadyuvante Siliconado", "minimo": 50.0, "unidad": "Litros", "categoria": "Fitosanitario"},
        "FITO-04": {"id": "FITO-04", "nombre": "Coragen (Clorantraniliprol)", "minimo": 20.0, "unidad": "Litros", "categoria": "Fitosanitario"}
    }
}

def obtener_umbrales() -> Dict[str, Dict[str, Any]]:
    """Obtiene el diccionario persistente de umbrales configurados por el usuario."""
    path = get_umbrales_file()
    if not path.exists():
        guardar_umbrales(DEFAULT_UMBRALES)
        return DEFAULT_UMBRALES

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Asegurar que todas las categorías y claves existan
            for cat, items in DEFAULT_UMBRALES.items():
                if cat not in data:
                    data[cat] = {}
                for k, v in items.items():
                    if k not in data[cat]:
                        data[cat][k] = v
            return data
    except Exception as e:
        logger.error(f"Error leyendo umbrales de stock: {e}")
        return DEFAULT_UMBRALES

def guardar_umbrales(umbrales: Dict[str, Dict[str, Any]]) -> bool:
    """Guarda los umbrales configurados en el almacenamiento JSON y sincroniza con BD."""
    path = get_umbrales_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(umbrales, f, indent=2, ensure_ascii=False)

        # Sincronizar en base de datos si Insumo está disponible
        try:
            from app.models import Insumo
            for cat, items in umbrales.items():
                for item_id, item_data in items.items():
                    min_val = float(item_data.get("minimo", 0))
                    nombre = item_data.get("nombre", "")
                    Insumo.objects.filter(nombre__icontains=nombre.split()[0]).update(stock_minimo_alerta=min_val)
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"Error guardando umbrales de stock: {e}")
        return False

def actualizar_umbral_individual(item_key_or_name: str, nuevo_minimo: float) -> Optional[Dict[str, Any]]:
    """
    Actualiza el stock mínimo de alerta de un insumo o depósito específico.
    """
    umbrales = obtener_umbrales()
    clean_target = item_key_or_name.lower().strip()

    updated_info = None

    for cat, items in umbrales.items():
        for k, v in items.items():
            k_low = k.lower()
            nom_low = v.get("nombre", "").lower()
            if clean_target == k_low or clean_target in nom_low or nom_low in clean_target:
                v["minimo"] = float(nuevo_minimo)
                updated_info = {
                    "categoria": cat,
                    "id": k,
                    "nombre": v["nombre"],
                    "nuevo_minimo": float(nuevo_minimo),
                    "unidad": v["unidad"]
                }
                break
        if updated_info:
            break

    if updated_info:
        guardar_umbrales(umbrales)

    return updated_info

def evaluar_stock_critico() -> Dict[str, Any]:
    """
    Evalúa el estado de todos los insumos y tanques contra los umbrales configurados.
    Categoriza en:
    - critico: stock_actual <= minimo (reposición urgente)
    - advertencia: minimo < stock_actual <= minimo * 1.25 (próximo a agotarse, aviso para comprar)
    - optimo: stock_actual > minimo * 1.25
    """
    umbrales = obtener_umbrales()

    # 1. Combustibles
    path_gasoil = settings.FILES_STORAGE_DIR / "stock_gasoil.json"
    gasoil_data = {}
    if path_gasoil.exists():
        try:
            with open(path_gasoil, "r", encoding="utf-8") as f:
                gasoil_data = json.load(f).get("depositos", {})
        except Exception:
            pass

    # 2. Insumos (Fertilizantes, Semillas, Fitosanitarios)
    path_insumos = settings.FILES_STORAGE_DIR / "stock_insumos.json"
    insumos_data = {}
    if path_insumos.exists():
        try:
            with open(path_insumos, "r", encoding="utf-8") as f:
                insumos_data = json.load(f)
        except Exception:
            pass

    items_evaluados = []
    alertas_criticas = []
    alertas_advertencia = []
    items_optimos = []

    # Evaluar Combustibles
    comb_umbrales = umbrales.get("combustibles", {})
    for k, u in comb_umbrales.items():
        dep = gasoil_data.get(k, {})
        actual = float(dep.get("stock_actual_litros") if "stock_actual_litros" in dep else dep.get("litros_disponibles", 0.0))
        minimo = float(u.get("minimo", 0.0))
        capacidad = float(dep.get("capacidad_max_litros", 0.0))

        estado = "optimo"
        if minimo > 0:
            if actual <= minimo:
                estado = "critico"
            elif actual <= minimo * 1.25:
                estado = "advertencia"

        item_res = {
            "id": k,
            "nombre": u.get("nombre", k),
            "categoria": "Combustible",
            "stock_actual": actual,
            "minimo": minimo,
            "unidad": u.get("unidad", "Litros"),
            "capacidad": capacidad,
            "estado": estado,
            "porcentaje_minimo": round((actual / max(minimo, 1.0)) * 100, 1) if minimo > 0 else 100.0,
            "diferencia": round(actual - minimo, 1)
        }
        items_evaluados.append(item_res)
        if estado == "critico":
            alertas_criticas.append(item_res)
        elif estado == "advertencia":
            alertas_advertencia.append(item_res)
        else:
            items_optimos.append(item_res)

    # Evaluar Fertilizantes
    fert_list = insumos_data.get("fertilizantes", [])
    fert_dict = {f.get("id"): f for f in fert_list}
    fert_umbrales = umbrales.get("fertilizantes", {})
    for fid, u in fert_umbrales.items():
        f = fert_dict.get(fid, {})
        actual = float(f.get("en_galpon_kg", 0.0))
        acopio = float(f.get("por_retirar_kg", 0.0))
        minimo = float(u.get("minimo", 0.0))

        estado = "optimo"
        if minimo > 0:
            if actual <= minimo:
                estado = "critico"
            elif actual <= minimo * 1.25:
                estado = "advertencia"

        item_res = {
            "id": fid,
            "nombre": u.get("nombre", f.get("nombre", fid)),
            "categoria": "Fertilizante",
            "stock_actual": actual,
            "acopio_pendiente": acopio,
            "minimo": minimo,
            "unidad": u.get("unidad", "kg"),
            "estado": estado,
            "porcentaje_minimo": round((actual / max(minimo, 1.0)) * 100, 1) if minimo > 0 else 100.0,
            "diferencia": round(actual - minimo, 1)
        }
        items_evaluados.append(item_res)
        if estado == "critico":
            alertas_criticas.append(item_res)
        elif estado == "advertencia":
            alertas_advertencia.append(item_res)
        else:
            items_optimos.append(item_res)

    # Evaluar Semillas
    hibridos = insumos_data.get("semillas_maiz", {}).get("hibridos", [])
    hib_dict = {h.get("id"): h for h in hibridos}
    var_soja = insumos_data.get("semillas_soja", {}).get("variedades", [{}])[0]
    var_trigo = insumos_data.get("semillas_trigo", {}).get("variedades", [{}])[0]

    sem_umbrales = umbrales.get("semillas", {})
    for sid, u in sem_umbrales.items():
        actual = 0.0
        acopio = 0.0
        if sid in hib_dict:
            actual = float(hib_dict[sid].get("en_planta_bolsas", 0.0))
            acopio = float(hib_dict[sid].get("por_retirar_bolsas", 0.0))
        elif "SJ" in sid:
            actual = float(var_soja.get("en_planta_bolsas", 0.0))
            acopio = float(var_soja.get("por_retirar_bolsas", 0.0))
        elif "TR" in sid:
            actual = float(var_trigo.get("en_planta_bolsas", 0.0))
            acopio = float(var_trigo.get("por_retirar_bolsas", 0.0))

        minimo = float(u.get("minimo", 0.0))
        estado = "optimo"
        if minimo > 0:
            if actual <= minimo:
                estado = "critico"
            elif actual <= minimo * 1.25:
                estado = "advertencia"

        item_res = {
            "id": sid,
            "nombre": u.get("nombre", sid),
            "categoria": "Semilla",
            "stock_actual": actual,
            "acopio_pendiente": acopio,
            "minimo": minimo,
            "unidad": u.get("unidad", "bolsas"),
            "estado": estado,
            "porcentaje_minimo": round((actual / max(minimo, 1.0)) * 100, 1) if minimo > 0 else 100.0,
            "diferencia": round(actual - minimo, 1)
        }
        items_evaluados.append(item_res)
        if estado == "critico":
            alertas_criticas.append(item_res)
        elif estado == "advertencia":
            alertas_advertencia.append(item_res)
        else:
            items_optimos.append(item_res)

    # Evaluar Fitosanitarios
    fitos_list = insumos_data.get("fitosanitarios", [])
    fitos_dict = {f.get("id"): f for f in fitos_list}
    fito_umbrales = umbrales.get("fitosanitarios", {})
    for fid, u in fito_umbrales.items():
        f = fitos_dict.get(fid, {})
        actual = float(f.get("en_galpon", 0.0))
        acopio = float(f.get("a_retirar", 0.0))
        minimo = float(u.get("minimo", 0.0))

        estado = "optimo"
        if minimo > 0:
            if actual <= minimo:
                estado = "critico"
            elif actual <= minimo * 1.25:
                estado = "advertencia"

        item_res = {
            "id": fid,
            "nombre": u.get("nombre", f.get("nombre", fid)),
            "categoria": "Fitosanitario",
            "stock_actual": actual,
            "acopio_pendiente": acopio,
            "minimo": minimo,
            "unidad": u.get("unidad", "Litros"),
            "estado": estado,
            "porcentaje_minimo": round((actual / max(minimo, 1.0)) * 100, 1) if minimo > 0 else 100.0,
            "diferencia": round(actual - minimo, 1)
        }
        items_evaluados.append(item_res)
        if estado == "critico":
            alertas_criticas.append(item_res)
        elif estado == "advertencia":
            alertas_advertencia.append(item_res)
        else:
            items_optimos.append(item_res)

    items_por_cat = {
        "Combustibles": [x for x in items_evaluados if x["categoria"] == "Combustible"],
        "Semillas": [x for x in items_evaluados if x["categoria"] == "Semilla"],
        "Fertilizantes": [x for x in items_evaluados if x["categoria"] == "Fertilizante"],
        "Fitosanitarios": [x for x in items_evaluados if x["categoria"] == "Fitosanitario"],
    }

    return {
        "umbrales_configurados": umbrales,
        "items": items_evaluados,
        "items_por_categoria": items_por_cat,
        "alertas_criticas": alertas_criticas,
        "alertas_advertencia": alertas_advertencia,
        "items_optimos": items_optimos,
        "total_criticos": len(alertas_criticas),
        "total_advertencias": len(alertas_advertencia),
        "total_items": len(items_evaluados),
        "totales": {
            "criticos": len(alertas_criticas),
            "advertencias": len(alertas_advertencia),
            "optimos": len(items_optimos),
            "total": len(items_evaluados)
        },
        "hay_alertas": (len(alertas_criticas) > 0 or len(alertas_advertencia) > 0)
    }

def generar_reporte_alertas_chat() -> str:
    """Genera un informe en texto formateado para el chat de IA Desk Agro y WhatsApp."""
    eval_res = evaluar_stock_critico()
    criticos = eval_res["alertas_criticas"]
    advertencias = eval_res["alertas_advertencia"]

    if not criticos and not advertencias:
        return (
            "✅ **Todos los insumos y depósitos se encuentran en niveles óptimos.**\n\n"
            "Ningún producto ha alcanzado su umbral mínimo de seguridad. Todo el stock operativo está listo para las labores."
        )

    lines = []
    lines.append("⚠️ **Panel de Alertas de Stock Crítico y Reposición • IA Desk Agro**\n")

    if criticos:
        lines.append("🔴 **STOCK CRÍTICO — REPOSICIÓN O COMPRA INMEDIATA:**")
        lines.append("*El stock actual está en o por debajo del umbral mínimo de seguridad establecido:*\n")
        for c in criticos:
            nom = c["nombre"]
            act = c["stock_actual"]
            mini = c["minimo"]
            uni = c["unidad"]
            cat = c["categoria"]
            acopio_str = f" *(Pendiente en acopio: {int(c['acopio_pendiente']):,} {uni})*" if c.get("acopio_pendiente", 0) > 0 else ""
            lines.append(f"• **{nom}** ({cat}): **{int(act):,} {uni}** (Umbral mínimo: {int(mini):,} {uni}){acopio_str} ➔ ⚠️ *Faltan {int(mini - act):,} {uni} para recuperar el nivel mínimo.*")
        lines.append("")

    if advertencias:
        lines.append("🟡 **NIVEL DE ADVERTENCIA — PRÓXIMO AL LÍMITE (COORDINAR COMPRA):**")
        lines.append("*Stock cercano al umbral de seguridad (+25%), recomendable iniciar gestión de compra:*\n")
        for a in advertencias:
            nom = a["nombre"]
            act = a["stock_actual"]
            mini = a["minimo"]
            uni = a["unidad"]
            cat = a["categoria"]
            lines.append(f"• **{nom}** ({cat}): **{int(act):,} {uni}** (Umbral de alerta: {int(mini):,} {uni}) ➔ *Quedan solo {int(act - mini):,} {uni} de margen.*")
        lines.append("")

    lines.append("💡 *Puedes modificar cualquier umbral diciendo por ejemplo: 'poner stock mínimo de tanque grande en 1000 litros' o desde el botón '⚙️ Umbrales de Stock' en la barra superior.*")
    return "\n".join(lines)

def verificar_alerta_para_item(item_id_or_name: str, saldo_nuevo: float) -> Optional[str]:
    """
    Verifica si una salida reciente de stock dejó al ítem en nivel crítico o de advertencia.
    Devuelve un mensaje de aviso para anexar a la respuesta del asistente.
    """
    umbrales = obtener_umbrales()
    clean_target = item_id_or_name.lower().strip()

    item_conf = None
    for cat, items in umbrales.items():
        for k, v in items.items():
            if clean_target == k.lower() or clean_target in v["nombre"].lower() or v["nombre"].lower() in clean_target:
                item_conf = v
                break
        if item_conf:
            break

    if not item_conf:
        return None

    minimo = float(item_conf.get("minimo", 0.0))
    if minimo <= 0:
        return None

    nom = item_conf["nombre"]
    uni = item_conf["unidad"]

    if saldo_nuevo <= minimo:
        return (
            f"\n\n🚨 **ALERTA DE STOCK CRÍTICO:**\n"
            f"El depósito o insumo **{nom}** ha quedado en **{int(saldo_nuevo):,} {uni}**, alcanzando o superando el umbral mínimo configurado (**{int(minimo):,} {uni}**).\n"
            f"👉 *Se recomienda programar la compra o reposición inmediata para evitar interrupciones en las labores.*"
        )
    elif saldo_nuevo <= minimo * 1.25:
        return (
            f"\n\n⚠️ **AVISO PREVENTIVO DE STOCK:**\n"
            f"El nivel de **{nom}** ha quedado en **{int(saldo_nuevo):,} {uni}**, aproximándose a su umbral de reposición (**{int(minimo):,} {uni}**).\n"
            f"👉 *Considerar coordinar nueva compra o flete.*"
        )

    return None
