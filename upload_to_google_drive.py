import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "files_storage"
FOLDER_ID = "11XiJ4FtA-8KOU3BvZWr6yDbxOwVoUvkw"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}?usp=sharing"

FILES_TO_UPLOAD = [
    {
        "filename": "IA_Desk_Agro_Consolidado.xlsx",
        "name_drive": "IA Desk Agro - Consolidado General",
        "desc": "Libro Maestro con las 7 pestañas de control integral"
    },
    {
        "filename": "IA_Desk_Agro_Maiz.xlsx",
        "name_drive": "IA Desk Agro - Maíz (Labores por Campo y Lote)",
        "desc": "Solapas: Campo La Esperanza, Campo El Ombú, Campo San José, Resumen Maíz"
    },
    {
        "filename": "IA_Desk_Agro_Soja_Primera.xlsx",
        "name_drive": "IA Desk Agro - Soja Primera (Labores por Campo y Lote)",
        "desc": "Solapas: Campo La Esperanza, Campo El Ombú, Campo San José, Resumen Soja 1ra"
    },
    {
        "filename": "IA_Desk_Agro_Soja_Segunda.xlsx",
        "name_drive": "IA Desk Agro - Soja Segunda (Labores por Campo y Lote)",
        "desc": "Solapas: Campo La Esperanza, Campo El Ombú, Campo San José, Resumen Soja 2da"
    },
    {
        "filename": "IA_Desk_Agro_Trigo.xlsx",
        "name_drive": "IA Desk Agro - Trigo (Labores y Cosecha por Campo y Lote)",
        "desc": "Solapas: Campo La Esperanza, Campo El Ombú, Campo San José, Resumen Trigo"
    }
]

def main():
    print("=" * 75)
    print("🚜 IA DESK AGRO - ASISTENTE DE HOJAS DE CÁLCULO & GOOGLE DRIVE")
    print(f"Carpeta Destino en Drive: {FOLDER_URL}")
    print("=" * 75)

    # 1. Asegurar que todos los libros estén generados
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    import django
    django.setup()
    from app.services.sheets_export_service import generate_consolidated_workbook
    from app.services.crop_sheets_service import generate_all_crop_workbooks

    print("Generando y actualizando las 5 hojas de cálculo...")
    generate_consolidated_workbook()
    generate_all_crop_workbooks()

    print("\n✅ Archivos listos en files_storage/:")
    for f_info in FILES_TO_UPLOAD:
        p = STORAGE_DIR / f_info["filename"]
        size_kb = round(p.stat().st_size / 1024, 1)
        print(f"  • {f_info['name_drive']}: {p.name} ({size_kb} KB)")

    # 2. Verificar si existen credenciales de Google API
    creds_oauth = BASE_DIR / "credentials.json"
    creds_sa = BASE_DIR / "service_account.json"

    if creds_oauth.exists() or creds_sa.exists():
        print("\n🔑 Credenciales de Google API detectadas. Subiendo las 5 hojas a Google Drive...")
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload
            from google.oauth2 import service_account
            from google_auth_oauthlib.flow import InstalledAppFlow

            SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']

            if creds_sa.exists():
                creds = service_account.Credentials.from_service_account_file(str(creds_sa), scopes=SCOPES)
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_oauth), SCOPES)
                creds = flow.run_local_server(port=0)

            service = build('drive', 'v3', credentials=creds)

            for f_info in FILES_TO_UPLOAD:
                local_path = STORAGE_DIR / f_info["filename"]
                metadata = {
                    'name': f_info["name_drive"],
                    'parents': [FOLDER_ID],
                    'mimeType': 'application/vnd.google-apps.spreadsheet'
                }
                media = MediaFileUpload(str(local_path), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', resumable=True)
                uploaded = service.files().create(body=metadata, media_body=media, fields='id, webViewLink').execute()
                print(f"  ✅ Subida exitosa: {f_info['name_drive']} -> {uploaded.get('webViewLink')}")

            print("\n🎉 ¡Todas las hojas de cálculo han sido subidas y convertidas a Google Sheets en tu carpeta!")
            return

        except Exception as e:
            print(f"⚠️ Error durante la subida con API: {e}")

    # 3. Flujo asistido en macOS
    print("\n📋 INSTRUCCIONES PARA SUBIDA DIRECTA A LA CARPETA COMPARTIDA:")
    print(f"1. Abre tu carpeta de Google Drive: {FOLDER_URL}")
    print(f"2. Arrastra los 5 archivos generados a la ventana de Google Drive:")
    for f_info in FILES_TO_UPLOAD:
        print(f"   📁 files_storage/{f_info['filename']}")
    print("3. Google Drive los abrirá automáticamente como Hojas de cálculo con solapas por campo.")
    print("=" * 75)

    try:
        subprocess.run(["open", FOLDER_URL], check=False)
        first_file = STORAGE_DIR / FILES_TO_UPLOAD[1]["filename"] # IA_Desk_Agro_Maiz.xlsx
        subprocess.run(["open", "-R", str(first_file)], check=False)
        print("🚀 Se ha abierto la carpeta de Drive en tu navegador y se ha seleccionado la carpeta de archivos en Finder.")
    except Exception:
        pass

if __name__ == "__main__":
    main()
