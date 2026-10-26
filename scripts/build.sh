#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "==> Instalando dependencias de Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

echo "==> Aplicando migraciones de base de datos..."
python manage.py migrate --noinput

echo "==> Build finalizado exitosamente."
