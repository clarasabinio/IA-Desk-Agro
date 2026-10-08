import json
from django.shortcuts import render
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .services.claude_service import process_agro_chat
from .services.storage_service import (
    read_storage_file,
    list_storage_files,
    reset_chat_history,
    get_sliding_history
)

def index_view(request: HttpRequest):
    """Renderiza la estación de trabajo local IA Desk Agro"""
    storage_files = list_storage_files()
    has_anthropic_key = bool(settings.ANTHROPIC_API_KEY)
    
    context = {
        "storage_files": storage_files,
        "has_anthropic_key": has_anthropic_key,
        "field_name": "Campo La Esperanza",
        "season": "Campaña Gruesa 2026/2027"
    }
    return render(request, "app/index.html", context)

@csrf_exempt
@require_http_methods(["POST"])
def api_chat_view(request: HttpRequest):
    """
    Endpoint REST JSON para procesar consultas en lenguaje natural con Claude y Tool Calling
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        user_message = data.get("message", "").strip()

        if not user_message:
            return JsonResponse({"status": "error", "message": "El mensaje no puede estar vacío."}, status=400)

        result = process_agro_chat(user_message)
        return JsonResponse({
            "status": "success",
            "data": result
        })

    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Formato JSON inválido."}, status=400)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@require_http_methods(["GET"])
def api_storage_list(request: HttpRequest):
    """Devuelve el inventario de archivos en files_storage/"""
    files = list_storage_files()
    return JsonResponse({"status": "success", "files": files})

@require_http_methods(["GET"])
def api_storage_file_content(request: HttpRequest, filename: str):
    """Permite al usuario inspeccionar en vivo el contenido de INDEX.md o MEMORY.md"""
    content = read_storage_file(filename)
    return JsonResponse({
        "status": "success",
        "filename": filename,
        "content": content
    })

@csrf_exempt
@require_http_methods(["POST"])
def api_reset_history(request: HttpRequest):
    """Reinicia la memoria de conversación de la ventana deslizante"""
    success = reset_chat_history()
    return JsonResponse({
        "status": "success" if success else "error",
        "message": "Historial de conversación reiniciado." if success else "Error al reiniciar."
    })
