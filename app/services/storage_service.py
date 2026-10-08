import os
import json
from pathlib import Path
from datetime import datetime
from django.conf import settings

STORAGE_DIR: Path = settings.FILES_STORAGE_DIR

def _get_safe_path(filename: str) -> Path:
    """Evita path traversal y restringe el acceso estrictamente a files_storage/"""
    safe_name = os.path.basename(filename.strip().replace('\\', '/'))
    target_path = (STORAGE_DIR / safe_name).resolve()
    
    # Validar que la ruta resuelta permanezca dentro del directorio de almacenamiento
    if not str(target_path).startswith(str(STORAGE_DIR.resolve())):
        raise PermissionError(f"Acceso denegado: {filename} está fuera de files_storage/")
    return target_path

def read_storage_file(filename: str) -> str:
    """Lee el contenido de un archivo dentro de files_storage/"""
    file_path = _get_safe_path(filename)
    if not file_path.exists():
        return f"[ERROR] El archivo '{filename}' no existe en files_storage/."
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[ERROR] No se pudo leer '{filename}': {str(e)}"

def write_storage_file(filename: str, content: str) -> str:
    """Escribe o actualiza un archivo en files_storage/"""
    file_path = _get_safe_path(filename)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"[OK] Archivo '{filename}' guardado y actualizado exitosamente en files_storage/ ({len(content)} caracteres)."
    except Exception as e:
        return f"[ERROR] No se pudo guardar '{filename}': {str(e)}"

def list_storage_files() -> list:
    """Lista todos los archivos presentes en files_storage/ con su metainformación"""
    results = []
    if not STORAGE_DIR.exists():
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        return results

    for item in sorted(STORAGE_DIR.iterdir()):
        if item.is_file() and not item.name.startswith('.'):
            stat = item.stat()
            results.append({
                "name": item.name,
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    return results

def get_sliding_history(limit: int = 10) -> list:
    """Obtiene los últimos N mensajes del archivo CHAT_HISTORY.json (Ventana deslizante)"""
    history_file = STORAGE_DIR / 'CHAT_HISTORY.json'
    if not history_file.exists():
        return []

    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            messages = data.get("messages", [])
            return messages[-limit:]
    except Exception:
        return []

def append_to_history(user_text: str, assistant_text: str, tool_calls: list = None, max_turns: int = 10) -> None:
    """Guarda el nuevo intercambio en la ventana deslizante para no desbordar tokens"""
    history_file = STORAGE_DIR / 'CHAT_HISTORY.json'
    data = {"max_history_turns": max_turns, "messages": []}
    
    if history_file.exists():
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Registro de turno de usuario
    data.setdefault("messages", []).append({
        "role": "user",
        "content": user_text,
        "timestamp": timestamp
    })
    
    # Registro de turno de asistente con herramientas registradas
    data["messages"].append({
        "role": "assistant",
        "content": assistant_text,
        "tools_invoked": tool_calls or [],
        "timestamp": timestamp
    })

    # Aplicar ventana deslizante (conservar los últimos 2 * max_turns mensajes)
    data["messages"] = data["messages"][-(max_turns * 2):]

    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando CHAT_HISTORY.json: {e}")

def reset_chat_history() -> bool:
    """Reinicia el historial de conversación en CHAT_HISTORY.json"""
    history_file = STORAGE_DIR / 'CHAT_HISTORY.json'
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump({"max_history_turns": 10, "messages": []}, f, indent=2)
        return True
    except Exception:
        return False
