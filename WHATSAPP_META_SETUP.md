# 📱 Guía Oficial: Configuración del Webhook de WhatsApp Cloud API (100% Gratuito)

IA Desk Agro incluye soporte nativo para conectarse a la **API Oficial de WhatsApp Cloud de Meta** utilizando su **capa gratuita (Free Tier)**, la cual otorga **hasta 1.000 conversaciones por mes sin costo alguno** y un número de prueba para desarrollo.

---

## 🛠️ Paso 1: Crear una App Gratuita en Meta for Developers

1. Ingresá a [Meta for Developers](https://developers.facebook.com/) e iniciá sesión con tu cuenta de Facebook personal (es 100% gratuito).
2. Andá a **Mis Apps (My Apps)** en la esquina superior derecha y presioná **Crear App (Create App)**.
3. Seleccioná el caso de uso **Otro (Other)** ➔ tipo de app **Negocio (Business)**.
4. Escribí un nombre para tu aplicación (ej: `IA Desk Agro Campo`) y tu correo electrónico.
5. En el panel de control de la app, buscá la tarjeta de **WhatsApp** y hacé clic en **Configurar (Set up)**.

---

## 🔑 Paso 2: Obtener las Credenciales de Prueba Gratuitas

1. En el menú lateral izquierdo de WhatsApp, hacé clic en **Configuración de la API (API Setup)**:
   - **Token de acceso temporal (Temporary Access Token):** Copiá este valor (`EAAG...`).
   - **Identificador de número de teléfono (Phone number ID):** Copiá este número (ej: `100609346426845`).
   - **Identificador de cuenta de WhatsApp Business:** Copiá este número.
2. En el campo **"Para" (To)**, agregá tu número de teléfono personal (con código de país, ej: `+549...`) y completá el código de verificación que te enviará Meta por WhatsApp.
3. Hacé clic en **"Enviar mensaje"** para verificar que recibas el mensaje de bienvenida de prueba de Meta.

---

## 🌐 Paso 3: Exponer tu Servidor Local con un Túnel Gratuito

Meta requiere una URL segura (`https://`) accesible desde Internet para enviar los mensajes. Podés usar cualquiera de estas dos herramientas **gratuitas**:

### Opción A: Cloudflare Tunnel (cloudflared) - *Recomendada (Sin registro ni límite de tiempo)*
```bash
# Si tenés brew en Mac:
brew install cloudflared
# Iniciar el túnel al puerto 8000:
cloudflared tunnel --url http://localhost:8000
```
Te dará una URL pública como: `https://palabra-aleatoria.trycloudflare.com`

### Opción B: Ngrok
```bash
ngrok http 8000
```
Te dará una URL como: `https://abc-123.ngrok-free.app`

---

## 🔗 Paso 4: Configurar el Webhook en Meta for Developers

1. En el menú de WhatsApp en Meta for Developers, seleccioná **Configuración (Configuration)**.
2. En la sección **Webhook**, hacé clic en **Editar (Edit)**:
   - **URL de devolución de llamada (Callback URL):**
     `https://tu-url-del-tunel/api/webhook/whatsapp/`
     *(Ejemplo: `https://mi-agro.trycloudflare.com/api/webhook/whatsapp/`)*
   - **Identificador de verificación (Verify Token):**
     Escribí el token configurado en tu `.env`:
     `ia_desk_agro_meta_verify_2026`
3. Hacé clic en **Verificar y Guardar**. Django responderá automáticamente con el desafío `hub.challenge` en milisegundos.
4. En **Campos de webhook (Webhook fields)**, hacé clic en **Administrar (Manage)** y activá la casilla **`messages`**.

---

## 📲 Paso 5: Probar el Flujo FieldData desde tu WhatsApp

1. Abrí WhatsApp en tu celular y enviá un mensaje al número de prueba de Meta:
   > *"Hola, cargamos 250 litros del Tanque Chico al John Deere y sembramos 20 hectáreas en el Lote 1."*
2. **Qué sucede internamente:**
   - Meta envía el evento a `/api/webhook/whatsapp/`.
   - `WhatsAppCloudService` y el motor agronómico procesan el texto.
   - `StockIntegrityService` valida y asienta el movimiento en `db.sqlite3` y descuenta el stock del tanque indicado.
   - La IA responde de vuelta por WhatsApp al operario con el balance de stock resultante.

---

## ⚙️ Variables de Entorno en `.env`
```env
WHATSAPP_VERIFY_TOKEN=ia_desk_agro_meta_verify_2026
WHATSAPP_API_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=tu_phone_number_id
```
