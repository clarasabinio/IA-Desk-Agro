import json
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest
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

def index_view(request: HttpRequest):
    """Renderiza el panel de control principal de IA Desk Agro"""
    storage_files = list_storage_files()
    has_anthropic_key = bool(settings.ANTHROPIC_API_KEY)
    stock_data = get_dashboard_summary()
    
    context = {
        "storage_files": storage_files,
        "has_anthropic_key": has_anthropic_key,
        "field_name": "Campo La Esperanza",
        "season": "Campaña Gruesa 2026/2027",
        "stock": stock_data
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
    enviados por el personal de campo (tractoristas, capataces) para actualizar stock y labores.
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
