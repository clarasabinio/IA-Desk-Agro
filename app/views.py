import json
import os
from pathlib import Path
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
    stock_data = get_dashboard_summary()
    drive_folder_id = get_drive_folder_id()
    drive_url = f"https://drive.google.com/drive/folders/{drive_folder_id}?usp=sharing"
    
    context = {
        "storage_files": storage_files,
        "has_anthropic_key": has_anthropic_key,
        "field_name": "Campo La Esperanza",
        "season": "Campaña Gruesa 2026/2027",
        "stock": stock_data,
        "google_drive_folder_url": drive_url,
        "google_drive_folder_id": drive_folder_id
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
def api_sheets_download_view(request: HttpRequest):
    """Permite descargar directamente el archivo Excel .xlsx consolidado"""
    xlsx_path = settings.FILES_STORAGE_DIR / "IA_Desk_Agro_Consolidado.xlsx"
    if not xlsx_path.exists():
        xlsx_path = generate_consolidated_workbook()

    return FileResponse(
        open(xlsx_path, "rb"),
        as_attachment=True,
        filename="IA_Desk_Agro_Consolidado.xlsx",
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
    """Fuerza la regeneración de las hojas y devuelve el estado"""
    try:
        xlsx_path = generate_consolidated_workbook()
        folder_id = get_drive_folder_id()
        folder_url = f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing"
        return JsonResponse({
            "status": "success",
            "message": "Hojas de cálculo regeneradas y sincronizadas.",
            "file": xlsx_path.name,
            "google_drive_folder_url": folder_url
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
