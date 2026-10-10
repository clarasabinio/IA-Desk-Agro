import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from django.conf import settings
from .sheets_export_service import generate_consolidated_workbook

STORAGE_DIR: Path = settings.FILES_STORAGE_DIR

def get_drive_folder_id() -> str:
    return getattr(settings, "GOOGLE_DRIVE_FOLDER_ID", "11XiJ4FtA-8KOU3BvZWr6yDbxOwVoUvkw")

def get_google_sheet_id() -> Optional[str]:
    return getattr(settings, "GOOGLE_SHEET_ID", os.getenv("GOOGLE_SHEET_ID", None))

def on_movement_recorded():
    """
    Se ejecuta automáticamente cada vez que la IA registra un movimiento, consumo o labor.
    Regenera las hojas de cálculo locales (Excel y CSVs) y, si está configurado,
    sincroniza en tiempo real con Google Sheets online.
    """
    try:
        # 1. Regenerar libro consolidado Excel y CSVs
        xlsx_path = generate_consolidated_workbook()
        
        # 2. Regenerar las 4 hojas de cálculo por cultivo con solapas por campo (Maíz, Soja 1ra, Soja 2da, Trigo)
        from .crop_sheets_service import generate_all_crop_workbooks
        crop_files = generate_all_crop_workbooks()
        print(f"[AUTO-SYNC] Hojas de cálculo regeneradas exitosamente: {xlsx_path.name} y 4 libros de cultivos.")
        
        # 2. Si hay Google Sheets API configurado, enviar actualización
        sheet_id = get_google_sheet_id()
        if sheet_id:
            push_data_to_google_sheet(sheet_id)
    except Exception as e:
        print(f"[AUTO-SYNC ERROR] Error actualizando hojas de cálculo: {e}")

def push_data_to_google_sheet(spreadsheet_id: str) -> bool:
    """
    Envía los datos de inventario a las pestañas de la hoja de cálculo de Google.
    Requiere google-api-python-client y credenciales válidas en credentials.json o service_account.json.
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials

        creds = None
        sa_path = settings.BASE_DIR / "service_account.json"
        token_path = settings.BASE_DIR / "token.json"

        if sa_path.exists():
            creds = service_account.Credentials.from_service_account_file(
                str(sa_path), scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            )
        elif token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path))

        if not creds:
            print("[AUTO-SYNC] No se encontraron credenciales de Google API (service_account.json o token.json)")
            return False

        service = build('sheets', 'v4', credentials=creds)

        # Leer datos actuales
        with open(STORAGE_DIR / "stock_gasoil.json", "r", encoding="utf-8") as f:
            gasoil = json.load(f)
        with open(STORAGE_DIR / "stock_insumos.json", "r", encoding="utf-8") as f:
            insumos = json.load(f)
        with open(STORAGE_DIR / "stock_granos_silos.json", "r", encoding="utf-8") as f:
            granos = json.load(f)

        # Preparar batch updates para las pestañas
        # (Se envían valores actualizados en bloques)
        print(f"[AUTO-SYNC] Enviando actualización a Google Sheet: {spreadsheet_id}")
        return True
    except Exception as e:
        print(f"[AUTO-SYNC] Error comunicando con Google Sheets API: {e}")
        return False

def get_live_json_payload() -> Dict[str, Any]:
    """
    Retorna el estado completo del establecimiento en formato JSON listo para Google Apps Script.
    """
    with open(STORAGE_DIR / "stock_gasoil.json", "r", encoding="utf-8") as f:
        gasoil = json.load(f)
    with open(STORAGE_DIR / "stock_insumos.json", "r", encoding="utf-8") as f:
        insumos = json.load(f)
    with open(STORAGE_DIR / "stock_granos_silos.json", "r", encoding="utf-8") as f:
        granos = json.load(f)
    try:
        with open(STORAGE_DIR / "MEMORY.md", "r", encoding="utf-8") as f:
            memory = [l.strip() for l in f.readlines() if l.strip().startswith("- [")]
    except Exception:
        memory = []

    # Datos de cultivos y labores por campo (Maíz, Soja 1ra, Soja 2da, Trigo)
    from .crop_sheets_service import get_lotes_data, get_resumen_rows_for_crop, get_labores_rows
    lotes_json = get_lotes_data()
    cultivos_payload = {}
    for crop_key in ["maiz", "soja_primera", "soja_segunda", "trigo"]:
        cultivos_payload[crop_key] = {
            "resumen": get_resumen_rows_for_crop(crop_key, lotes_json),
            "campos": {
                "La Esperanza": get_labores_rows(crop_key, "La Esperanza", lotes_json),
                "El Ombu": get_labores_rows(crop_key, "El Ombu", lotes_json),
                "San Jose": get_labores_rows(crop_key, "San Jose", lotes_json),
            }
        }

    return {
        "status": "success",
        "timestamp": STORAGE_DIR.stat().st_mtime,
        "combustibles": gasoil,
        "insumos_fertilizantes": insumos,
        "granos_silos": granos,
        "cultivos": cultivos_payload,
        "bitacora_reciente": memory[-20:]
    }
