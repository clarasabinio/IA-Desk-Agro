from app.services.agronomic_engine import get_live_soil_and_weather_factor
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest, HttpResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .services.claude_service import (
    process_agro_chat,
    get_dashboard_summary
)
from .services.storage_service import (
    read_file,
    list_storage_files,
    reset_chat_history
)
from .services.sheets_export_service import generate_consolidated_workbook
from .services.google_sheets_service import (
    on_movement_recorded,
    get_live_json_payload,
    get_drive_folder_id
)

def index_view(request: HttpRequest):
    """Renderiza el panel de control principal de IA Desk Agro"""
    storage_files = list_storage_files()
    has_anthropic_key = bool(settings.ANTHROPIC_API_KEY)
    has_api_key = bool(getattr(settings, 'OPENROUTER_API_KEY', '') or settings.ANTHROPIC_API_KEY)
    ai_provider = "OpenRouter (Claude Sonnet 5.5)" if getattr(settings, 'OPENROUTER_API_KEY', '') else ("Anthropic (Claude 3.5 Sonnet)" if settings.ANTHROPIC_API_KEY else "Modo Local Autónomo")
    stock_data = get_dashboard_summary()
    drive_folder_id = get_drive_folder_id()
    drive_url = f"https://drive.google.com/drive/folders/{drive_folder_id}?usp=sharing"

    # Cargar lotes con sus híbridos y diagramas
    lotes_path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
    try:
        with open(lotes_path, "r", encoding="utf-8") as f:
            lotes_data = json.load(f).get("lotes", [])
    except Exception:
        lotes_data = []

    # Cargar campos con su cartografía y planos satelitales
    campos_path = settings.FILES_STORAGE_DIR / "registro_campos.json"
    try:
        with open(campos_path, "r", encoding="utf-8") as f:
            campos_data = json.load(f).get("campos", [])
    except Exception:
        campos_data = []

    # Contexto enriquecido desde la Única Fuente de Verdad (Base de Datos SQLite)
    from app.models import Deposito, Insumo, MovimientoStock, Lote, Campo, CicloCultivo
    from app.services.stock_service import StockIntegrityService

    depositos_list = Deposito.objects.filter(activo=True).order_by("tipo", "nombre")
    insumos_list = Insumo.objects.all().order_by("categoria", "nombre")
    movimientos_list = MovimientoStock.objects.select_related("insumo", "lote", "deposito_origen_fk", "deposito_destino_fk").order_by("-fecha", "-creado_el")[:60]
    lotes_db = Lote.objects.filter(activo=True).select_related("campo").order_by("campo__nombre", "nombre")
    balance_auditado = StockIntegrityService.obtener_balance_verificado()

    context = {
        "storage_files": storage_files,
        "has_anthropic_key": has_anthropic_key,
        "has_api_key": has_api_key,
        "ai_provider": ai_provider,
        "field_name": "Campo La Esperanza",
        "season": "Campaña Gruesa 2026/2027",
        "stock": stock_data,
        "lotes": lotes_data,
        "campos": campos_data,
        "google_drive_folder_url": drive_url,
        "google_drive_folder_id": drive_folder_id,
        "depositos_db": depositos_list,
        "insumos_db": insumos_list,
        "movimientos_db": movimientos_list,
        "lotes_db": lotes_db,
        "balance_auditado": balance_auditado,
        "clima": get_live_soil_and_weather_factor()
    }
    return render(request, "app/index.html", context)

@csrf_exempt
@require_http_methods(["POST"])
def api_chat_view(request: HttpRequest):
    """Endpoint REST JSON para chat en lenguaje natural con bucle de Tool Calling"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"status": "error", "message": "El mensaje no puede estar vacío."}, status=400)

        result = process_agro_chat(user_message, is_whatsapp=False)
        return JsonResponse({
            "status": "success",
            "data": result
        })

    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Formato JSON inválido."}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def api_whatsapp_simulator_view(request: HttpRequest):
    """
    Endpoint dedicado que simula la recepción de audios/mensajes informales de WhatsApp
    enviados por el personal de campo para actualizar stock y labores.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        raw_message = data.get("message", "").strip()
        sender = data.get("sender", "Juan González (Tractorista)").strip()
        is_audio = data.get("is_audio", True)

        if not raw_message:
            return JsonResponse({"status": "error", "message": "Mensaje de WhatsApp requerido."}, status=400)

        result = process_agro_chat(raw_message, is_whatsapp=True, sender_name=sender)
        result["whatsapp_metadata"] = {
            "sender": sender,
            "is_audio": is_audio,
            "received_at": "Ahora mismo",
            "transcription": raw_message
        }

        return JsonResponse({
            "status": "success",
            "data": result
        })

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@require_http_methods(["GET"])
def api_storage_list(request: HttpRequest):
    files = list_storage_files()
    return JsonResponse({"status": "success", "files": files})

@require_http_methods(["GET"])
def api_storage_file_content(request: HttpRequest, filename: str):
    content = read_file(filename)
    return JsonResponse({
        "status": "success",
        "filename": filename,
        "content": content
    })

@csrf_exempt
@require_http_methods(["POST"])
def api_reset_history(request: HttpRequest):
    success = reset_chat_history()
    return JsonResponse({
        "status": "success" if success else "error",
        "message": "Historial reiniciado." if success else "Error al reiniciar."
    })

# ==============================================================
# ENDPOINTS DE HOJAS DE CÁLCULO & GOOGLE DRIVE
# ==============================================================

@require_http_methods(["GET"])
def api_sheets_download_view(request: HttpRequest, crop_name: Optional[str] = None):
    """Permite descargar el archivo Excel consolidado o uno de los 4 libros de cultivos por campo"""
    target_crop = crop_name or request.GET.get("crop", "consolidado")
    target_crop = target_crop.lower().strip()

    crop_map = {
        "consolidado": ("IA_Desk_Agro_Consolidado.xlsx", None),
        "maiz": ("IA_Desk_Agro_Maiz.xlsx", "maiz"),
        "maíz": ("IA_Desk_Agro_Maiz.xlsx", "maiz"),
        "soja_primera": ("IA_Desk_Agro_Soja_Primera.xlsx", "soja_primera"),
        "soja-primera": ("IA_Desk_Agro_Soja_Primera.xlsx", "soja_primera"),
        "soja1": ("IA_Desk_Agro_Soja_Primera.xlsx", "soja_primera"),
        "soja_segunda": ("IA_Desk_Agro_Soja_Segunda.xlsx", "soja_segunda"),
        "soja-segunda": ("IA_Desk_Agro_Soja_Segunda.xlsx", "soja_segunda"),
        "soja2": ("IA_Desk_Agro_Soja_Segunda.xlsx", "soja_segunda"),
        "trigo": ("IA_Desk_Agro_Trigo.xlsx", "trigo")
    }

    if target_crop not in crop_map:
        target_crop = "consolidado"

    filename, crop_key = crop_map[target_crop]
    file_path = settings.FILES_STORAGE_DIR / filename

    if not file_path.exists():
        if crop_key:
            from .services.crop_sheets_service import generate_crop_workbook
            file_path = generate_crop_workbook(crop_key)
        else:
            file_path = generate_consolidated_workbook()

    return FileResponse(
        open(file_path, "rb"),
        as_attachment=True,
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@require_http_methods(["GET"])
def api_sheets_live_data_view(request: HttpRequest):
    """Devuelve los datos estructurados en JSON para Google Apps Script o PowerBI"""
    data = get_live_json_payload()
    return JsonResponse(data)

@require_http_methods(["GET"])
def api_sheets_csv_view(request: HttpRequest, module_name: str):
    """
    Devuelve el CSV en vivo de un módulo específico.
    Permite a Google Sheets sincronizarse usando la fórmula =IMPORTDATA("http://.../api/sheets/csv/fertilizantes/")
    """
    valid_modules = {
        "combustibles": "combustibles_live.csv",
        "fertilizantes": "fertilizantes_live.csv",
        "insumos": "insumos_live.csv",
        "semillas_maiz": "semillas_maiz_live.csv",
        "granos_silos": "granos_silos_live.csv"
    }
    
    if module_name not in valid_modules:
        return JsonResponse({"status": "error", "message": f"Módulo no válido. Opciones: {list(valid_modules.keys())}"}, status=404)

    csv_path = settings.FILES_STORAGE_DIR / valid_modules[module_name]
    if not csv_path.exists():
        generate_consolidated_workbook()

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HttpResponse(content, content_type="text/csv; charset=utf-8")
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST", "GET"])
def api_sheets_sync_now_view(request: HttpRequest):
    """Fuerza la regeneración de las 5 hojas y devuelve el estado"""
    try:
        from .services.crop_sheets_service import generate_all_crop_workbooks
        xlsx_path = generate_consolidated_workbook()
        crop_files = generate_all_crop_workbooks()
        folder_id = get_drive_folder_id()
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"
        return JsonResponse({
            "status": "success",
            "message": "5 Hojas de cálculo regeneradas y sincronizadas exitosamente (Consolidado + Maíz, Soja 1ra, Soja 2da, Trigo).",
            "files": [xlsx_path.name] + [p.name for p in crop_files.values()],
            "google_drive_folder_url": folder_url
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_lote_update_view(request: HttpRequest):
    """
    Actualiza la información agronómica de un lote específico:
    - Híbridos o variedades que se plantan en el mismo
    - Carga y almacenamiento de una foto o diagrama (plano, esquema o estado)
    """
    try:
        import os
        from datetime import datetime
        lote_id = request.POST.get("lote_id", "").strip()
        hibridos = request.POST.get("hibridos_plantados", "").strip()
        uploaded_file = request.FILES.get("foto_diagrama")

        if not lote_id:
            return JsonResponse({"status": "error", "message": "Identificador de lote requerido."}, status=400)

        lotes_path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
        with open(lotes_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        target_lote = None
        for l in data.get("lotes", []):
            if l.get("id") == lote_id or l.get("nombre", "").lower().startswith(lote_id.lower()):
                target_lote = l
                break

        if not target_lote:
            return JsonResponse({"status": "error", "message": f"Lote '{lote_id}' no encontrado."}, status=404)

        if hibridos is not None:
            target_lote["hibridos_plantados"] = hibridos
            target_lote["variedad"] = hibridos

        if uploaded_file:
            media_dir = settings.BASE_DIR / "media" / "lotes"
            media_dir.mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
            clean_id = target_lote.get("id", "lote").lower().replace("-", "_")
            timestamp = int(datetime.now().timestamp())
            filename = f"{clean_id}_{timestamp}{ext}"
            file_path = media_dir / filename

            with open(file_path, "wb") as dest:
                for chunk in uploaded_file.chunks():
                    dest.write(chunk)

            target_lote["diagrama_url"] = f"/media/lotes/{filename}"
            target_lote["diagrama_nombre"] = uploaded_file.name

        with open(lotes_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Registrar en bitácora / memoria operativa
        from .services.storage_service import append_memory
        desc_memo = f"Actualización agronómica de {target_lote.get('nombre')}: Híbrido '{target_lote.get('hibridos_plantados')}'"
        if uploaded_file:
            desc_memo += f" y nuevo plano/diagrama cargado ('{uploaded_file.name}')"
        append_memory(desc_memo)

        return JsonResponse({
            "status": "success",
            "message": f"{target_lote.get('nombre')} actualizado correctamente.",
            "lote": target_lote
        })

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


# ==============================================================
# ENDPOINTS FIELD DATA: REGISTROS DIRECTOS Y CONFIRMACIÓN DE IA
# ==============================================================

@csrf_exempt
@require_http_methods(["POST"])
def api_movimiento_directo_view(request: HttpRequest):
    """
    Endpoint para formularios directos (Field Data) de combustible,
    traslados, compras y aplicación de insumos.
    """
    try:
        from app.services.stock_service import StockIntegrityService
        from app.models import Lote, Insumo, CicloCultivo
        from django.core.exceptions import ValidationError

        data = json.loads(request.body.decode("utf-8")) if request.body else request.POST
        tipo_accion = data.get("tipo_accion", "consumo_combustible").strip()
        operario = data.get("operario", "Productor").strip() or "Productor"
        observaciones = data.get("observaciones", "").strip()

        if tipo_accion == "consumo_combustible":
            litros = float(data.get("litros", 0))
            deposito_codigo = data.get("deposito_codigo", "tanque_grande")
            lote_id = data.get("lote_id")
            labor = data.get("labor", "Labor de campo").strip() or "Labor de campo"
            maquinaria = data.get("maquinaria", "").strip() or "Tractor de labor"

            lote_obj = Lote.objects.filter(id=lote_id).first() if lote_id else None
            res = StockIntegrityService.registrar_salida_combustible(
                litros=litros,
                deposito_codigo=deposito_codigo,
                lote=lote_obj,
                labor=labor,
                maquinaria=maquinaria,
                operario=operario,
                observaciones=observaciones
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        elif tipo_accion == "traslado_combustible":
            litros = float(data.get("litros", 0))
            origen = data.get("origen_codigo")
            destino = data.get("destino_codigo")

            res = StockIntegrityService.registrar_traslado_combustible(
                litros=litros,
                origen_codigo=origen,
                destino_codigo=destino,
                operario=operario,
                observaciones=observaciones
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        elif tipo_accion == "ingreso_combustible":
            litros = float(data.get("litros", 0))
            destino = data.get("destino_codigo", "cisterna_planta")
            proveedor = data.get("proveedor", "YPF Directo")
            remito = data.get("documento_referencia", "").strip()

            res = StockIntegrityService.registrar_ingreso_compra_combustible(
                litros=litros,
                destino_codigo=destino,
                proveedor=proveedor,
                nro_remito=remito,
                operario=operario,
                observaciones=observaciones
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        elif tipo_accion == "consumo_insumo":
            insumo_id = int(data.get("insumo_id"))
            cantidad = float(data.get("cantidad", 0))
            lote_id = data.get("lote_id")
            labor = data.get("labor", "Aplicación agronómica").strip()
            maquinaria = data.get("maquinaria", "").strip()

            lote_obj = Lote.objects.filter(id=lote_id).first() if lote_id else None
            res = StockIntegrityService.registrar_consumo_insumo(
                insumo_id=insumo_id,
                cantidad=cantidad,
                lote=lote_obj,
                labor=labor,
                maquinaria=maquinaria,
                operario=operario
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        else:
            return JsonResponse({"status": "error", "message": f"Tipo de acción '{tipo_accion}' no reconocida."}, status=400)

    except ValidationError as ve:
        return JsonResponse({"status": "error", "message": str(ve.messages if hasattr(ve, 'messages') else ve)}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_confirmar_propuesta_ia_view(request: HttpRequest):
    """
    Endpoint de confirmación explícita para propuestas de la IA.
    Solo impacta la base de datos cuando el usuario hace clic en [Confirmar].
    """
    try:
        from app.services.stock_service import StockIntegrityService
        from app.models import Lote, Insumo

        data = json.loads(request.body.decode("utf-8"))
        prop = data.get("proposal", {})
        idempotency_token = data.get("idempotency_token") or prop.get("idempotency_token")

        if not prop:
            return JsonResponse({"status": "error", "message": "Datos de propuesta requeridos."}, status=400)

        action = prop.get("action_type", "consumo_combustible")
        operario = prop.get("operario", "Productor")

        if action == "consumo_combustible":
            litros = float(prop.get("litros", 0))
            deposito = prop.get("deposito_codigo", "tanque_grande")
            lote_nombre = prop.get("lote_nombre", "")
            lote_obj = Lote.objects.filter(nombre__icontains=lote_nombre.replace("Lote", "").strip()).first() if lote_nombre else None

            res = StockIntegrityService.registrar_salida_combustible(
                litros=litros,
                deposito_codigo=deposito,
                lote=lote_obj,
                labor=prop.get("labor", "Labor de campo"),
                maquinaria=prop.get("maquinaria", "Tractor"),
                operario=operario,
                observaciones="Confirmado por usuario desde chat",
                idempotency_token=idempotency_token
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        elif action == "traslado_combustible":
            litros = float(prop.get("litros", 0))
            origen = prop.get("origen_codigo")
            destino = prop.get("destino_codigo")

            res = StockIntegrityService.registrar_traslado_combustible(
                litros=litros,
                origen_codigo=origen,
                destino_codigo=destino,
                operario=operario,
                observaciones="Traslado confirmado desde chat",
                idempotency_token=idempotency_token
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        elif action == "ingreso_combustible":
            litros = float(prop.get("litros", 0))
            destino = prop.get("destino_codigo", "cisterna_planta")
            proveedor = prop.get("proveedor", "YPF Directo")

            res = StockIntegrityService.registrar_ingreso_compra_combustible(
                litros=litros,
                destino_codigo=destino,
                proveedor=proveedor,
                operario=operario,
                observaciones="Ingreso de compra confirmado desde chat",
                idempotency_token=idempotency_token
            )
            return JsonResponse({
                "status": "success",
                "message": res["mensaje"],
                "data": res,
                "stock_data": get_dashboard_summary()
            })

        else:
            return JsonResponse({"status": "error", "message": f"Acción '{action}' no soportada para confirmación."}, status=400)

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
