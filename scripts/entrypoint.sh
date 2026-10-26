#!/bin/sh
set -e

echo "==> [IA Desk Agro] Verificando directorios de persistencia..."
mkdir -p /app/files_storage /app/media /app/staticfiles

echo "==> [IA Desk Agro] Ejecutando migraciones de base de datos..."
python manage.py migrate --noinput

echo "==> [IA Desk Agro] Recolectando archivos estáticos con WhiteNoise..."
python manage.py collectstatic --noinput || true

echo "==> [IA Desk Agro] Iniciando servicio..."
exec "$@"
