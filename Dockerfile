# ==============================================================================
# Dockerfile para IA Desk Agro (100% Open Source / Python 3.11 Slim)
# Optimizado para desarrollo local y despliegue gratuito en Render/Railway
# ==============================================================================
FROM python:3.11-slim

# Evitar generación de archivos bytecode .pyc y forzar salida inmediata de logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar librerías de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . /app/

# Crear directorios para datos y estáticos
RUN mkdir -p /app/files_storage /app/media /app/staticfiles

# Asignar permisos al entrypoint
RUN chmod +x /app/scripts/entrypoint.sh

# Exponer el puerto por defecto de Django
EXPOSE 8000

# Punto de entrada y comando de arranque con Gunicorn
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
