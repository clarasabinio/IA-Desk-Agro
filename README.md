# 🌾 IA Desk Agro

**Copiloto Digital Inteligente y Gestión Integral de Operaciones Agropecuarias**  
*Establecimiento "La Esperanza" — Campaña Gruesa 2026/2027*

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.0%2B-darkgreen.svg)](https://www.djangoproject.com/)
[![Docker](https://img.shields.io/badge/Docker-Compatible-2496ED.svg)](https://www.docker.com/)
[![License: Open Source](https://img.shields.io/badge/License-Open%20Source-green.svg)](LICENSE)

---

## 📖 Fundamento General y Arquitectura

**IA Desk Agro** es una plataforma web agropecuaria full-stack diseñada para la administración, control y registro en tiempo real de operaciones de campo. Combina una arquitectura híbrida:

1. **Dashboard Operativo Interactivo:** Visualización en vivo de los depósitos de combustible, inventario de insumos (agroquímicos, fertilizantes y semillas), capacidad de silos de granos y estado de lotes por cultivo (Maíz, Soja 1ra, Soja 2da, Trigo).
2. **Copiloto IA y Motor Agronómico:** Asistente inteligente capaz de procesar lenguaje coloquial de productores y maquinistas mediante ejecución de herramientas (*tool calling*), calculando consumos basados en normas técnicas (INTA CostoMaq y AAPRESID).
3. **Integridad Transaccional y Control de Stock:** Protección estricta que **impide registrar consumos o retiros superiores al stock real disponible**, evitando saldos negativos en depósitos físicos, galpones y silos.
4. **Sincronización Continua con Google Drive & Google Sheets:** Cada movimiento asienta automáticamente en la base de datos relacional (SQLite), en archivos de proyección JSON/CSV y regenera las 5 planillas maestras en Excel (`.xlsx`), sincronizables con Google Drive mediante Google Apps Script.
5. **Canal de Comunicación WhatsApp Cloud API (Meta):** Webhook oficial preparado para la capa 100% gratuita de Meta for Developers para recibir reportes directos de operarios en lote (Field Data).

---

## 🚀 Características Principales

### ⛽ 1. Control de Combustibles (Gasoil) en 4 Ubicaciones
* **Cisterna Planta:** Tanque nodriza principal de 22.000 Litros.
* **Tanque Grande:** Cisterna móvil de 5.000 Litros para abastecimiento en trilla y siembra.
* **Tanque Chico:** Carretón móvil de 3.000 Litros para auxilio rápido en lote.
* **Gasoil por Retirar (Acopio YPF Directo):** Saldo de combustible prepagado en distribuidor.
* **Gasto directo flexible:** Si indicas un gasto de combustible sin especificar la labor (ej: *"Gasté 200 litros"*), el sistema detecta qué depósito tiene saldo disponible y lo asienta directamente como consumido.

### 🛡️ 2. Validación Estricta de Stock
* El sistema **rechaza de forma automática cualquier intento de gastar más de lo existente en stock**.
* Si intentas retirar 100 L de un tanque que solo tiene 49 L, o sembrar 50 bolsas cuando solo quedan 20, la operación se bloquea y el asistente te notifica el saldo real disponible.

### 📦 3. Insumos, Fertilizantes y Semillas
* **Doble balance:** Existencias físicas **en galpón** vs. órdenes compradas **por retirar** en proveedores (Corteva, Rizobacter, Bayer, etc.).
* **Fertilizantes:** Urea granulada, MAP y MicroEssentials en kilogramos (kg) y toneladas (Tn).
* **Semillas:** Monitoreo por híbrido (DK 72-10, P2089, AX 7784) y variedad de soja (DM 46R18).

### 🌾 4. Silos de Acopio y Granos
* Monitoreo de 5 Silos Principales fijos (hasta 500 Tn c/u) y 2 Silos de Trilla auxiliares.
* Control de humedad comercial (%) y toneladas almacenadas por cultivo (Soja, Maíz, Trigo).
* Validación de cupos y despachos hacia camiones a puerto.

### 📱 5. Webhook y Simulador de WhatsApp Cloud API
* Endpoint listo para producción en `/api/webhook/whatsapp/` y `/webhook/whatsapp/`.
* Soporta el desafío `hub.challenge` de Meta for Developers (Token de verificación: `ia_desk_agro_meta_verify_2026`).
* Incluye simulador visual integrado en el Dashboard para evaluar mensajes de campo sin costo.

---

## 📁 Estructura del Repositorio

```text
IA-Desk-Agro/
├── app/                        # Aplicación principal Django
│   ├── models.py               # Modelos relacionales (Campo, Lote, Insumo, Deposito, MovimientoStock)
│   ├── views.py                # Endpoints de Dashboard, APIs REST y Webhook WhatsApp
│   ├── urls.py                 # Enrutamiento de la aplicación
│   ├── forms.py                # Formularios para carga directa de movimientos
│   ├── prompts/
│   │   └── system_prompt.txt   # Prompt del sistema y reglas de integridad para la IA
│   ├── services/
│   │   ├── stock_service.py         # Integridad transaccional y prevención de saldos negativos
│   │   ├── claude_service.py        # Copiloto conversacional, simulación y tool calling
│   │   ├── agronomic_engine.py      # Cálculos técnicos INTA CostoMaq y factores de suelo
│   │   ├── google_sheets_service.py # Sincronización con Google Sheets API y live-data
│   │   ├── sheets_export_service.py # Exportación del libro maestro consolidado (.xlsx)
│   │   ├── crop_sheets_service.py   # Libros de cultivo por campo (Maíz, Soja, Trigo)
│   │   ├── whatsapp_service.py      # Servicio de WhatsApp Cloud API (Meta)
│   │   └── storage_service.py       # Gestión de archivos locales
│   ├── static/                 # Estilos CSS modernos y Javascript interactivo
│   └── templates/app/          # Vistas HTML (Dashboard interactivo)
├── core/                       # Configuración del proyecto Django (settings, asgi, wsgi)
├── files_storage/              # Registros vivos en JSON, bitácoras y hojas Excel
│   ├── stock_gasoil.json       # Balance de combustibles
│   ├── stock_insumos.json      # Balance de insumos y fertilizantes
│   ├── stock_granos_silos.json # Granos en silos
│   ├── registro_lotes.json     # Datos de lotes y hectáreas
│   ├── MEMORY.md               # Bitácora histórica de labores
│   ├── Google_Apps_Script_IA_Desk_Agro.js # Código para sincronizar Google Sheets
│   └── IA_Desk_Agro_Consolidado.xlsx      # Libro Maestro Excel con 7 pestañas
├── scripts/                    # Scripts de despliegue y arranque
├── Dockerfile                  # Contenedor Docker para ejecución aislada
├── docker-compose.yml          # Orquestación local en contenedor
├── .env.example                # Plantilla de variables de entorno seguras
├── requirements.txt            # Dependencias de Python
├── manage.py                   # CLI de Django
├── DEPLOYMENT_FREE_TIER.md     # Guía de despliegue en capas gratuitas
├── WHATSAPP_META_SETUP.md      # Guía paso a paso para WhatsApp de Meta
└── README.md                   # Esta documentación
```

---

## 💻 Instrucciones para Ejecutar en Otra Computadora

Puedes ejecutar el proyecto en cualquier computadora (macOS, Windows o Linux) utilizando **Python directo** o **Docker**.

### 🐳 Opción A: Ejecución Rápida con Docker (Recomendada)

Si tienes Docker instalado (Docker Desktop u OrbStack):

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/clarasabinio/IA-Desk-Agro.git
   cd IA-Desk-Agro
   ```

2. **Crear el archivo de configuración `.env`:**
   ```bash
   cp .env.example .env
   ```

3. **Construir y levantar los contenedores:**
   ```bash
   docker compose up --build
   ```

4. **Abrir en tu navegador:**
   👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

### 🐍 Opción B: Ejecución Local con Python y Django

#### 1. Requisitos Previos
* **Python 3.9** o superior ([Descargar Python](https://www.python.org/downloads/)).
* Git instalado.

#### 2. Clonar el Repositorio
```bash
git clone https://github.com/clarasabinio/IA-Desk-Agro.git
cd IA-Desk-Agro
```

#### 3. Crear y Activar el Entorno Virtual
* **En macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
* **En Windows (PowerShell):**
  ```powershell
  python -m venv venv
  venv\Scripts\Activate.ps1
  ```
* **En Windows (CMD):**
  ```cmd
  python -m venv venv
  venv\Scripts\activate.bat
  ```

#### 4. Instalar Dependencias
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 5. Configurar Variables de Entorno
Copia la plantilla `.env.example` para crear tu `.env`:
* En macOS / Linux:
  ```bash
  cp .env.example .env
  ```
* En Windows:
  ```cmd
  copy .env.example .env
  ```

*(El archivo `.env.example` ya viene preconfigurado con valores por defecto funcionales para desarrollo local; no requiere tarjetas ni suscripciones pagas).*

#### 6. Ejecutar Migraciones de Base de Datos
```bash
python manage.py migrate
```

*(Opcional) Crear usuario administrador para el panel de Django:*
```bash
python manage.py createsuperuser
```

#### 7. Iniciar el Servidor de Desarrollo
```bash
python manage.py runserver
```

#### 8. Abrir la Aplicación
Ingresa desde cualquier navegador a:
👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

Para acceder al Panel de Administración de Django:
👉 **[http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)**

---

## 💡 Ejemplos de Interacción con el Asistente

Puedes escribirle en lenguaje natural a través del chat o del simulador de WhatsApp:

* **Gasto sin labor aclarada:**
  * *"Gasté 200 litros de combustible"* ➔ El sistema busca el depósito con saldo disponible y asienta el consumo de inmediato.
* **Gasto con maquinaria:**
  * *"Cargamos 40 litros de gasoil en la camioneta"* ➔ Descuenta y etiqueta el gasto a la camioneta.
* **Control de stock insuficiente:**
  * *"Gasté 50.000 litros de gasoil del tanque chico"* ➔ **Rechazado:** Avisa que no hay stock suficiente indicando el saldo real.
* **Transferencias entre tanques:**
  * *"Pasamos 1.500 litros de la cisterna al tanque grande"* ➔ Asienta el traslado y verifica la capacidad máxima del tanque de destino.
* **Semillas y siembra:**
  * *"Sembré 40 bolsas de maíz DK 72-10 en Lote 2"* ➔ Descuenta las bolsas de Planta Central y asienta la labor en la hoja de Maíz.
* **Granos y silos:**
  * *"Despachar 30 toneladas de soja del Silo 1 a camión puerto"* ➔ Registra el despacho y recalcula la ocupación del silo.

---

## ☁️ Integración con Google Sheets & Google Drive

* El archivo [upload_to_google_drive.py](upload_to_google_drive.py) permite subir automáticamente las 5 planillas Excel a tu carpeta de Google Drive.
* El script [Google_Apps_Script_IA_Desk_Agro.js](files_storage/Google_Apps_Script_IA_Desk_Agro.js) puede pegarse en **Extensiones > Apps Script** en cualquier hoja de Google Sheets para mantenerla sincronizada en tiempo real mediante el endpoint `/api/sheets/live-data/`.

---

## 🔒 Seguridad y Buenas Prácticas
* El archivo `.gitignore` excluye todas las bases de datos locales (`*.sqlite3`), archivos de entorno (`.env`), claves privadas (`*.pem`, `*.key`) y cachés.
* Ninguna clave confidencial ni credencial privada se encuentra expuesta en el código fuente.

---

## 📄 Licencia y Créditos
Proyecto desarrollado para la gestión operativa y agrícola del establecimiento **La Esperanza** (Campaña 2026/2027). Código libre y de uso abierto.
