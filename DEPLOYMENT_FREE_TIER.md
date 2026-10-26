# 🚀 Guía de Despliegue y Ejecución en Capas Gratuitas (100% Free Tier)

Esta guía explica cómo ejecutar **IA Desk Agro** utilizando herramientas y plataformas **100% gratuitas, de código abierto y sin tarjeta de crédito**.

---

## 🐳 Método 1: Ejecución Local con Docker & Docker Compose

Ideal para correr todo en tu computadora en un entorno aislado y reproducible.

### Requisitos:
- Tener instalado Docker / Docker Desktop o [OrbStack](https://orbstack.dev/) (alternativa libre y ultra-liviana para Mac).

### Comandos de Ejecución:
```bash
# 1. Copiar archivo de entorno si aún no existe
cp .env.example .env

# 2. Construir la imagen e iniciar los contenedores
docker compose up --build

# 3. En una nueva terminal, para ver los logs en tiempo real:
docker compose logs -f

# 4. Para detener la aplicación:
docker compose down
```

### Características de este contenedor:
- **Persistencia garantizada:** `db.sqlite3`, `files_storage` y `media` están montados como volúmenes en tu disco local. Nada se pierde al reiniciar el contenedor.
- **Servidor de producción Gunicorn:** Corre con 2 workers y soporte de concurrencia.
- **WhiteNoise integrado:** Los archivos CSS, JS e imágenes se sirven de forma óptima sin requerir Nginx ni servicios externos.

---

## ☁️ Método 2: Despliegue en la Nube con Render (Free Tier)

Render ofrece una capa gratuita permanente para aplicaciones web en Python.

### Pasos:
1. Subí tu proyecto a un repositorio en **GitHub** o **GitLab** (público o privado).
2. Creá una cuenta gratuita en [Render.com](https://render.com/).
3. Hacé clic en **New +** ➔ **Web Service**.
4. Conectá tu repositorio de GitHub.
5. Configurá los parámetros:
   - **Environment:** `Python 3`
   - **Region:** Elige la más cercana (ej: `Ohio` o `Frankfurt`).
   - **Branch:** `main`
   - **Build Command:** `./scripts/build.sh`
   - **Start Command:** `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT`
   - **Plan:** `Free ($0 / mes)`
6. En la sección **Environment Variables**, agregá:
   - `DEBUG`: `False`
   - `SECRET_KEY`: `(genera una clave aleatoria o presiona Generate)`
   - `ALLOWED_HOSTS`: `.onrender.com,localhost,127.0.0.1`
   - `CSRF_TRUSTED_ORIGINS`: `https://*.onrender.com`
   - `WHATSAPP_VERIFY_TOKEN`: `ia_desk_agro_meta_verify_2026`
7. Presioná **Create Web Service**. En 3 minutos tu sistema estará en vivo en una URL pública `https://ia-desk-agro.onrender.com`.

---

## 🚂 Método 3: Despliegue en Railway (Hobby / Free Trial)

1. En [Railway.app](https://railway.app/), hacé clic en **New Project** ➔ **Deploy from GitHub repo**.
2. Railway detectará automáticamente el `Dockerfile` del proyecto.
3. En las variables del servicio, agregá las mismas variables de `.env.example`.
4. Generá un dominio público en la pestaña **Settings ➔ Generate Domain**.

---

## 🌐 Método 4: Exposición Local Segura para Probar Webhooks (Sin Subir a la Nube)

Si preferís correr la app en tu máquina (`http://127.0.0.1:8000`) pero necesitás que Meta o WhatsApp envíen peticiones:

### Con Cloudflare Tunnel (100% Gratuito y sin registro):
```bash
# 1. Instalar (en Mac con Homebrew):
brew install cloudflared

# 2. Exponer el puerto 8000:
cloudflared tunnel --url http://localhost:8000
```
Obtendrás una URL HTTPS gratuita y estable lista para pegar en Meta for Developers.
