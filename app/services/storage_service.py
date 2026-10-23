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
    if not str(target_path).startswith(str(STORAGE_DIR.resolve())):
        raise PermissionError(f"Acceso denegado: {filename} está fuera de files_storage/")
    return target_path

# ==========================================
# 4 HERRAMIENTAS NATIVAS REQUERIDAS
# ==========================================

def read_file(filename: str) -> str:
    """Lee el contenido íntegro de un archivo en files_storage/"""
    file_path = _get_safe_path(filename)
    if not file_path.exists():
        return f"[ERROR] El archivo '{filename}' no existe en files_storage/."
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"[ERROR] No se pudo leer '{filename}': {str(e)}"

def write_file(filename: str, content: str) -> str:
    """Crea o sobrescribe un archivo en files_storage/ y regenera las hojas de cálculo"""
    file_path = _get_safe_path(filename)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Disparar auto-sincronización y regeneración de hojas de cálculo
        if any(k in filename for k in ["stock_", "registro_lotes", "MEMORY"]):
            try:
                from .google_sheets_service import on_movement_recorded
                on_movement_recorded()
            except Exception as ex:
                print(f"[AUTO-SYNC NOTICE] No se pudo ejecutar sincronización automática: {ex}")

        return f"[OK] Archivo '{filename}' guardado exitosamente ({len(content)} bytes)."
    except Exception as e:
        return f"[ERROR] No se pudo escribir '{filename}': {str(e)}"

def append_memory(entry: str) -> str:
    """Agrega una nueva entrada fechada a MEMORY.md y actualiza la bitácora de las hojas"""
    memory_path = STORAGE_DIR / 'MEMORY.md'
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_entry = f"\n- [{timestamp}] {entry.strip()}"
    try:
        with open(memory_path, 'a', encoding='utf-8') as f:
            f.write(formatted_entry)

        try:
            from .google_sheets_service import on_movement_recorded
            on_movement_recorded()
        except Exception:
            pass

        return f"[OK] Entrada agregada a la memoria de negocio ({timestamp})."
    except Exception as e:
        return f"[ERROR] No se pudo agregar a MEMORY.md: {str(e)}"

def update_memory(content: str) -> str:
    """Actualiza o reescribe completamente el contenido de MEMORY.md"""
    memory_path = STORAGE_DIR / 'MEMORY.md'
    try:
        with open(memory_path, 'w', encoding='utf-8') as f:
            f.write(content)

        try:
            from .google_sheets_service import on_movement_recorded
            on_movement_recorded()
        except Exception:
            pass

        return f"[OK] MEMORY.md actualizado exitosamente."
    except Exception as e:
        return f"[ERROR] No se pudo actualizar MEMORY.md: {str(e)}"

# ==========================================
# UTILIDADES ADICIONALES DE PERSISTENCIA
# ==========================================

def list_storage_files() -> list:
    """Devuelve inventario detallado de files_storage/"""
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
    history_file = STORAGE_DIR / 'CHAT_HISTORY.json'
    if not history_file.exists():
        return []
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("messages", [])[-limit:]
    except Exception:
        return []

def append_to_history(user_text: str, assistant_text: str, tool_calls: list = None, max_turns: int = 10):
    history_file = STORAGE_DIR / 'CHAT_HISTORY.json'
    data = {"max_history_turns": max_turns, "messages": []}
    if history_file.exists():
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            pass

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data.setdefault("messages", []).append({
        "role": "user",
        "content": user_text,
        "timestamp": timestamp
    })
    data["messages"].append({
        "role": "assistant",
        "content": assistant_text,
        "tools_invoked": tool_calls or [],
        "timestamp": timestamp
    })
    data["messages"] = data["messages"][-(max_turns * 2):]

    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando historial: {e}")

def reset_chat_history() -> bool:
    history_file = STORAGE_DIR / 'CHAT_HISTORY.json'
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump({"max_history_turns": 10, "messages": []}, f, indent=2)
        return True
    except Exception:
        return False
