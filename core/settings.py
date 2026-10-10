import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde el archivo .env local
load_dotenv(BASE_DIR / '.env')

# Clave secreta y depuración
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-ia-desk-agro-local-default-key-2026')
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# Hosts permitidos para entorno local
allowed_hosts_raw = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = ['*']
if '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.extend(['127.0.0.1', 'localhost'])

# Credenciales de Inteligencia Artificial
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Ruta a la carpeta física dedicada para datos de la empresa agropecuaria
FILES_STORAGE_DIR = BASE_DIR / 'files_storage'

# Aplicaciones instaladas
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Aplicación interna del negocio agropecuario
    'app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Configuración de seguridad local
X_FRAME_OPTIONS = 'SAMEORIGIN'

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'app' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Base de datos SQLite ligera para sesiones locales
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Validación de contraseñas
AUTH_PASSWORD_VALIDATORS = []

# Internacionalización
LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Cordoba'
USE_I18N = True
USE_TZ = True

# Archivos estáticos
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'app' / 'static',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Sincronización Google Drive & Google Sheets
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID', '11XiJ4FtA-8KOU3BvZWr6yDbxOwVoUvkw')
GOOGLE_DRIVE_FOLDER_URL = f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}?usp=sharing"
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', None)
