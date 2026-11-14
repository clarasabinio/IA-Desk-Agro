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
5. **Canal de Comunicación WhatsApp Cloud API (Meta):** Webhook oficial preparado para la capa 100% gratuita de Meta for Developers para recibir reportes directos de operarios en lote (Reportes Operativos).

---

## 🌟 Mejoras y Nuevas Funcionalidades Implementadas

A continuación se detallan las mejoras clave incorporadas al sistema para optimizar la operación diaria a campo y el control administrativo:

* **📱 Conexión con WhatsApp y Simulador Interactivo de Mensajes:**
  * Integración con la **WhatsApp Cloud API de Meta** mediante webhook oficial para producción (`/api/webhook/whatsapp/`).
  * **Simulador de WhatsApp integrado en el Dashboard web:** Permite realizar y verificar pruebas completas de mensajería y flujos conversacionales de campo en tiempo real, sin requerir una línea telefónica activa ni incurrir en costos de mensajería.

* **🛡️ Restricción de Acciones por WhatsApp y Doble Verificación Operativa:**
  * **Permisos controlados por canal:** Por WhatsApp únicamente se permite consultar información y asentar **datos y registros operativos menores** (labores agrícolas, consumos de insumos y retiros de combustible). Se **restringe estrictamente la creación o alteración de campos**, garantizando que la estructura de los establecimientos solo pueda ser gestionada desde la interfaz web por el administrador.
  * **Doble verificación previa de labores:** Al reportar una labor agrícola vía WhatsApp, el sistema no descuenta insumos a ciegas; genera una propuesta con el resumen de la operación (campo, lote, hectáreas, labor, maquinaria, combustible estimado e insumos a descontar) y **solicita confirmación expresa (*"Sí, confirmar"* o *"Confirmar"*)** antes de asentar los cambios, previniendo malinterpretaciones o errores de tipeo.
  * **Retiros de combustible limpios:** Los movimientos y retiros de combustible se asientan de inmediato con respuesta directa (*"Perfecto, ya registré lo que pediste."*) y resumen de saldos restantes, sin asociarse erróneamente a lotes agrícolas.

* **🎯 Consultas Específicas Inteligentes y Soporte Multi-Consulta:**
  * **Respuestas precisas a preguntas puntuales:** El copiloto reconoce exactamente qué se le está consultando y devuelve **únicamente el dato solicitado**, evitando listados innecesarios:
    * Si preguntas por el **Tanque Chico de gasoil**, informa exclusivamente el saldo y estado de ese tanque, sin listar los demás depósitos.
    * Si consultas por una **semilla o híbrido puntual** (ej: *Pioneer P2089*, *Dekalb DK 72-10*, *Nidera*, *Soja* o *Trigo*), responde solo sobre esa variedad (bolsas en planta vs. por retirar en acopio).
    * Si consultas por un **fertilizante o químico específico** (ej: solo *Urea* o solo *Glifosato*), responde únicamente las existencias de ese producto.
    * Si consultas por un **cereal en silos** (ej: *Soja* o *Trigo*), responde solo las toneladas de ese grano.
  * **Soporte para consultas compuestas (Multi-Query):** Si en un mismo mensaje de WhatsApp se realizan dos o más preguntas (ej: *"¿Cuánto gasoil queda en el tanque chico y cuántas semillas de Pioneer tenemos?"*), el motor detecta todos los temas y responde a **ambas consultas de manera completa, ordenada y numerada (`1️⃣`, `2️⃣`, etc.)**.
  * **Modo general disponible:** Si la consulta es amplia (ej: *"¿cuánto gasoil queda?"* o *"¿qué semillas tenemos?"*), continúa entregando el consolidado general de todos los depósitos y variedades.

* **🚜 Cálculo Automático de Consumos y Cuentas de Labores (Motor Agronómico INTA):**
  * **Cuentas automáticas sobre labores realizadas:** Al reportar una labor en un lote (ej: pasada de rastra de discos, siembra, fertilización, pulverización o trilla), el sistema **calcula automáticamente el gasto de gasoil** multiplicando las hectáreas trabajadas por la tasa técnica oficial (**INTA CostoMaq / AAPRESID**).
  * **Ajuste dinámico en vivo por suelo y clima:** Conexión con la **Open-Meteo Agro API** para obtener la humedad edáfica superficial en tiempo real, ajustando el factor de tracción y resistencia al avance (+8% a +15% de combustible en suelos pesados/húmedos).
  * **Cálculo de dosis y descuento de insumos:** Determina y descuenta automáticamente las bolsas de semillas recomendadas (densidad agronómica en maíz, soja o trigo) y los kilogramos de fertilizantes requeridos (MAP, Urea, MicroEssentials). Si el maquinista especifica los litros o bolsas reales gastadas, el sistema respeta con prioridad el dato real informado.

* **🗺️ Botón "Agregar Campo", Modificación de Lotes, Fotos/Croquis y Hojas Conectadas:**
  * **Alta y modificación web completa:** Se incorporó el botón **"Agregar Campo"** en el panel principal y la funcionalidad para **editar y modificar en cualquier momento los datos de campos y lotes existentes**, permitiendo corregir errores de carga fácilmente.
  * **Subida de croquis y fotos reales:** Permite adjuntar imágenes reales (`.jpg`, `.png`), mapas y croquis del establecimiento, mostrándolos en la ficha técnica del campo junto con la descripción detallada de cada parcela y sus hectáreas.
  * **Coordenadas geográficas GPS:** Posibilidad de cargar coordenadas GPS a cada lote para una trazabilidad satelital exacta.
  * **Sincronización con Hojas de Cálculo Conectadas:** Toda labor, consumo o modificación de campos y lotes se asienta automáticamente en el libro maestro consolidado de Excel (`IA_Desk_Agro_Consolidado.xlsx` con 7 pestañas) y en las planillas por cultivo (Maíz, Soja 1ra, Soja 2da, Trigo), manteniendo sincronización con Google Drive y Google Sheets.

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

* **Consultas Específicas:**
  * *"¿Cuánto gas oil queda en el tanque chico?"* ➔ Responde únicamente sobre el Tanque Chico (sin listar los demás tanques).
  * *"¿Cuántas bolsas de Pioneer tenemos?"* ➔ Responde exclusivamente las bolsas del híbrido Pioneer P2089 (en planta vs por retirar).
  * *"¿Cuánta urea queda?"* ➔ Detalla únicamente las existencias de Urea Granulada en galpón y acopio.
* **Consultas Múltiples (Multi-Query):**
  * *"¿Cuánto gasoil queda en el tanque chico y cuántas semillas de Pioneer tenemos?"* ➔ Responde de forma estructurada a ambas preguntas (`1️⃣` Tanque Chico, `2️⃣` Pioneer P2089).
* **Cálculo Automático de Labores con Doble Verificación:**
  * *"Pasé la rastra de discos en el Lote 1 (50 ha)"* ➔ Calcula automáticamente el consumo de gasoil ($50 \text{ ha} \times 8.5 \text{ L/ha} = 425 \text{ L}$, ajustado por suelo Open-Meteo) y solicita confirmación antes de asentar.
  * *"Sí, confirmar"* ➔ Descuenta el combustible del tanque, asienta la labor en el lote y actualiza las planillas.
* **Retiro de Combustible Limpio:**
  * *"Retiré 300 litros del tanque grande para el tractor"* ➔ Responde: *"Perfecto, ya registré lo que pediste"* y detalla el saldo restante sin asociarlo a lotes.
* **Control de stock insuficiente:**
  * *"Gasté 50.000 litros de gasoil del tanque chico"* ➔ **Rechazado:** Avisa que no hay stock suficiente indicando el saldo real disponible.
* **Transferencias entre tanques:**
  * *"Pasamos 1.500 litros de la cisterna al tanque grande"* ➔ Asienta el traslado interno y verifica la capacidad máxima del tanque destino.

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
