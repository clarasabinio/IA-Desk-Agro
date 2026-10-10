import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
XLSX_PATH = BASE_DIR / "files_storage" / "IA_Desk_Agro_Consolidado.xlsx"
FOLDER_ID = "11XiJ4FtA-8KOU3BvZWr6yDbxOwVoUvkw"
FOLDER_URL = f"https://drive.google.com/drive/folders/{FOLDER_ID}?usp=sharing"

def main():
    print("=" * 70)
    print("🚜 IA DESK AGRO - ASISTENTE DE SUBIDA A GOOGLE DRIVE")
    print(f"Carpeta Destino: {FOLDER_URL}")
    print("=" * 70)

    # 1. Asegurar que el archivo consolidado esté generado
    if not XLSX_PATH.exists():
        print("Generando archivo consolidado Excel...")
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
        import django
        django.setup()
        from app.services.sheets_export_service import generate_consolidated_workbook
        generate_consolidated_workbook()

    print(f"✅ Archivo listo: {XLSX_PATH} ({XLSX_PATH.stat().st_size:,} bytes)")

    # 2. Verificar si existen credenciales de API
    creds_oauth = BASE_DIR / "credentials.json"
    creds_sa = BASE_DIR / "service_account.json"

    if creds_oauth.exists() or creds_sa.exists():
        print("\n🔑 Credenciales de Google API detectadas. Iniciando subida directa...")
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

            file_metadata = {
                'name': 'IA Desk Agro - Hojas de Cálculo Consolidado',
                'parents': [FOLDER_ID],
                'mimeType': 'application/vnd.google-apps.spreadsheet'  # Convierte automáticamente a Google Sheet
            }

            media = MediaFileUpload(
                str(XLSX_PATH),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                resumable=True
            )

            file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
            sheet_id = file.get('id')
            web_link = file.get('webViewLink')

            print("\n" + "🎉" * 25)
            print(f"✅ ¡Hoja de cálculo creada y subida a Google Drive con éxito!")
            print(f"📄 ID de la Hoja: {sheet_id}")
            print(f"🔗 Enlace directo en Drive: {web_link}")
            print("🎉" * 25)
            return

        except Exception as e:
            print(f"⚠️ Error durante la subida con API: {e}")
            print("Procediendo con la apertura directa para subida asistida...")

    # 3. Flujo asistido en macOS
    print("\n📋 INSTRUCCIONES PARA SUBIDA DIRECTA A LA CARPETA COMPARTIDA:")
    print(f"1. Abre la carpeta de Google Drive: {FOLDER_URL}")
    print(f"2. Arrastra o sube el archivo generado:")
    print(f"   📁 {XLSX_PATH}")
    print("3. Google Drive lo abrirá como una Hoja de Cálculo de Google completa.")
    print("=" * 70)

    # Abrir la carpeta en el navegador predeterminado y revelar el archivo en Finder
    try:
        subprocess.run(["open", FOLDER_URL], check=False)
        subprocess.run(["open", "-R", str(XLSX_PATH)], check=False)
        print("🚀 Se ha abierto la carpeta de Google Drive en tu navegador y se ha seleccionado el archivo en tu Finder.")
    except Exception:
        pass

if __name__ == "__main__":
    main()
