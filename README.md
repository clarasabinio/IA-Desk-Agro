# 🌾 IA Desk Agro

**Copiloto Digital y Gestión Integral de Operaciones Agropecuarias**  
*Establecimiento "La Esperanza" — Campaña Gruesa 2026/2027*

---

## 📖 Descripción General

**IA Desk Agro** es una plataforma web inteligente diseñada para la gestión, control y registro en tiempo real de operaciones agropecuarias. Combina un panel interactivo (Dashboard) con un asistente de Inteligencia Artificial que ejecuta acciones de lectura y actualización sobre el inventario, labores de campo y registros de insumos mediante procesamiento de lenguaje natural y ejecución de herramientas (*tool calling*).

---

## 🚀 Características Principales

### ⛽ 1. Control de Combustibles (Gasoil)
Monitoreo dinámico de stock y transferencias en 4 ubicaciones clave:
- **Cisterna Planta:** Tanque principal de 22.000 L.
- **Tanque Grande:** Cisterna móvil de 5.000 L para apoyo en siembra y cosecha.
- **Tanque Chico:** Carretón móvil de 3.000 L para auxilio rápido en lote.
- **Gasoil por Retirar:** Saldo acopiado en proveedor (YPF Directo).
*Permite registrar consumos directos por tanque, transferencias internas y retiros de acopio.*

### 📦 2. Insumos y Fitosanitarios
- Control dual: existencias físicas **en galpón** vs. existencias compradas **a retirar** por proveedor / punto de retiro.
- Seguimiento de agroquímicos (Glifosato, 2,4-D Enlist, etc.) y fertilizantes en kilogramos (Urea, MAP, MicroEssentials SZ).

### 🌽 3. Semillas e Híbridos
- Control de bolsas por híbrido y variedad (Dekalb, Pioneer, Nidera, Don Mario).
- Diferenciación clara entre stock disponible en planta y órdenes pendientes de retiro en semilleras/cooperativas.

### 🌾 4. Silos y Almacenamiento de Granos
- Monitoreo en toneladas (Tn) y porcentaje de capacidad utilizada.
- Control de humedad por grano (Soja, Maíz, Trigo).
- Soporte para silos principales fijos y silos de acopio para trilla.

### 🤖 5. Asistente IA Conversacional
- Capaz de interpretar lenguaje coloquial de campo (ej: *"le saqué 400 litros al tanque grande"*, *"llegaron 50 bolsas de maíz al galpón"*).
- Ejecución automática de herramientas (*Tool Calling*):
  - `read_file`: Consulta de stock y parámetros actuales.
  - `write_file`: Modificación precisa y segura de los registros JSON.
  - `append_memory` / `update_memory`: Bitácora histórica de eventos en `MEMORY.md`.

### 📊 6. Integración y Exportación de Datos
- Sincronización y exportación a **Google Sheets**, **Google Drive** y planillas **Excel (.xlsx / .csv)**.

---

## 📁 Estructura del Proyecto

```text
IA Desk Agro/
├── app/                        # Aplicación principal Django
│   ├── prompts/                # Prompts del sistema para el asistente IA
│   │   └── system_prompt.txt
│   ├── services/               # Lógica de negocio e integraciones externas
│   │   ├── claude_service.py         # Cliente IA y ejecución de herramientas
│   │   ├── crop_sheets_service.py    # Gestión de planillas por cultivo
│   │   ├── google_sheets_service.py  # Conector API Google Sheets
│   │   ├── sheets_export_service.py  # Exportación de datos
│   │   └── storage_service.py        # Almacenamiento local de archivos
│   ├── static/                 # Archivos estáticos (CSS, JS, iconos)
│   ├── templates/app/          # Plantillas HTML de la interfaz (index.html)
│   ├── views.py                # Controladores y endpoints REST
│   └── urls.py                 # Enrutamiento de la app
├── core/                       # Configuración global del proyecto Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── files_storage/              # Base de datos viva en archivos JSON, MD y hojas
│   ├── stock_gasoil.json       # Stock de combustible en tanques
│   ├── stock_insumos.json      # Stock de agroquímicos, fertilizantes y semillas
│   ├── stock_granos_silos.json # Capacidad y stock de silos
│   ├── registro_lotes.json     # Labores y registros agronómicos
│   ├── INDEX.md                # Resumen ejecutivo de capacidades y stock
│   └── MEMORY.md               # Bitácora operativa acumulada
├── requirements.txt            # Dependencias del entorno Python
├── manage.py                   # Script de gestión de Django
└── README.md                   # Esta documentación
```

---

## 🛠️ Requisitos e Instalación

### Requisitos previos
- **Python 3.9** o superior.
- Navegador web moderno (Chrome, Safari, Edge, Firefox).

### Pasos para iniciar el sistema

1. **Abrir una terminal** y dirigirse a la carpeta del proyecto:
   ```bash
   cd "/Users/clarasabinio/Desktop/IA Desk Agro"
   ```

2. **Activar el entorno virtual**:
   ```bash
   source venv/bin/activate
   ```
   *(Si el entorno no existiera, se crea con `python3 -m venv venv` e instalan dependencias con `pip install -r requirements.txt`)*.

3. **Verificar variables de entorno (`.env`)**:
   Asegúrate de contar con las claves necesarias en el archivo `.env`:
   - `ANTHROPIC_API_KEY`: Clave de API de Anthropic Claude para el asistente.
   - Credenciales de Google Drive / Sheets (si se utilizan sincronizaciones en la nube).

4. **Iniciar el servidor local**:
   ```bash
   python3 manage.py runserver
   ```

5. **Acceder a la aplicación**:
   Abre en tu navegador la dirección:
   👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## 💡 Ejemplos de Consultas y Comandos al Asistente

- **Combustibles:**
  - *"¿Cuánto gasoil queda en la cisterna de planta?"*
  - *"Retiré 350 litros del tanque grande para el tractor."*
  - *"Pasamos 2.000 litros de la cisterna al tanque grande."*
- **Insumos y Fertilizantes:**
  - *"¿Qué cantidad de urea tenemos en galpón y cuánto falta retirar?"*
  - *"Se aplicaron 20 litros de 2,4-D Enlist en el Lote 4."*
- **Silos y Granos:**
  - *"Mostrame el estado de los silos y la humedad del maíz."*
- **Exportación:**
  - *"Exportar balance general a Excel."*

---

## 📄 Licencia y Uso
Desarrollado para uso exclusivo y optimización operativa de la empresa agropecuaria **La Esperanza**.
