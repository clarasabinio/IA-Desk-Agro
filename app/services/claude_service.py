import re
import json
from typing import Dict, Any, List, Tuple
from django.conf import settings
import anthropic

from .storage_service import (
    read_storage_file,
    write_storage_file,
    list_storage_files,
    get_sliding_history,
    append_to_history
)

# Definición formal de Herramientas para Anthropic Claude
CLAUDE_TOOLS = [
    {
        "name": "read_storage_file",
        "description": "Lee el contenido de un archivo del negocio en el almacenamiento local (ej: 'INDEX.md' para lotes y stock, 'MEMORY.md' para directivas).",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre exacto del archivo a leer (ej: 'INDEX.md', 'MEMORY.md')."
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "write_storage_file",
        "description": "Crea o actualiza un archivo en el almacenamiento local para persistir cambios (ej: actualizar el stock del tanque en 'INDEX.md' o registrar notas en 'MEMORY.md').",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo a actualizar (ej: 'INDEX.md', 'MEMORY.md')."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido completo en Markdown que reemplazará el archivo con los datos actualizados."
                }
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "list_storage_files",
        "description": "Lista los archivos del negocio para conocer qué registros existen.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

SYSTEM_PROMPT = """Eres "IA Desk Agro", el copiloto inteligente de operaciones de la empresa agropecuaria familiar "La Esperanza" (Campaña Gruesa 2026/2027).

Tu rol es asistir a los productores respondiendo consultas operativas y manteniendo al día el inventario de insumos, lotes y combustible.

REGLAS ESTRICTAS DE COMUNICACIÓN Y PRIVACIDAD DE ARCHIVOS:
1. NUNCA nombres los nombres técnicos de los archivos donde guardas la información (como INDEX.md, MEMORY.md, CHAT_HISTORY.json ni files_storage).
2. NUNCA envíes enlaces a los archivos.
3. Utiliza SIEMPRE frases genéricas y profesionales como:
   - "Consultando los registros del campo..."
   - "Según el inventario actual del establecimiento..."
   - "He actualizado el stock del tanque cisterna y la bitácora operativa..."
   - "De acuerdo a las directivas de la administración..."

REGLA CLAVE DE GESTIÓN DE COMBUSTIBLE:
4. Cuando el usuario indique que se gastó, consumió o cargó gasoil (ej. "gasté 500 litros de gas oil", "consumimos 400 L en siembra"):
   a) Consulta el inventario (INDEX.md) para saber el stock actual.
   b) Resta matemáticamente la cantidad exacta consumida al stock en el tanque.
   c) Escribe de inmediato el archivo INDEX.md con el NUEVO stock descontado usando 'write_storage_file'.
   d) Registra la anotación del gasto en MEMORY.md usando 'write_storage_file'.
   e) Confirma al usuario el consumo descontado y el nuevo stock restante en el tanque cisterna en litros, advirtiendo si cae cerca del umbral de seguridad de 5.000 Litros.
"""

def get_current_gasoil_stock() -> str:
    """Extrae el stock actual en formato string desde INDEX.md"""
    content = read_storage_file("INDEX.md")
    match = re.search(r'\*\*Stock actual:\*\*\s*([\d\.,]+)\s*Litros', content)
    if match:
        return match.group(1)
    return "8.500"

def deduct_gasoil_stock(liters: float) -> Tuple[float, float, str]:
    """
    Resta los litros consumidos directamente en INDEX.md y lo guarda físicamente.
    Devuelve (stock_anterior, stock_nuevo, nuevo_formateado)
    """
    content = read_storage_file("INDEX.md")
    match = re.search(r'\*\*Stock actual:\*\*\s*([\d\.,]+)\s*Litros', content)
    
    if match:
        raw_num = match.group(1).replace('.', '').replace(',', '.')
        try:
            current_stock = float(raw_num)
        except ValueError:
            current_stock = 8500.0
    else:
        current_stock = 8500.0

    new_stock = max(0.0, current_stock - liters)
    
    # Formato con puntos para miles (ej: 8.000)
    if new_stock.is_integer():
        formatted_new = f"{int(new_stock):,}".replace(',', '.')
    else:
        formatted_new = f"{new_stock:,.1f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    updated_content = re.sub(
        r'\*\*Stock actual:\*\*\s*([\d\.,]+)\s*Litros',
        f'**Stock actual:** {formatted_new} Litros',
        content,
        count=1
    )
    write_storage_file("INDEX.md", updated_content)
    return current_stock, new_stock, formatted_new

def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Ejecuta una herramienta en el almacenamiento local"""
    meta = {"tool": tool_name, "args": tool_args}
    
    if tool_name == "read_storage_file":
        filename = tool_args.get("filename", "")
        content = read_storage_file(filename)
        meta["status"] = "success" if not content.startswith("[ERROR]") else "error"
        meta["preview"] = "Datos consultados correctamente"
        return content, meta

    elif tool_name == "write_storage_file":
        filename = tool_args.get("filename", "")
        content = tool_args.get("content", "")
        result = write_storage_file(filename, content)
        meta["status"] = "success" if not result.startswith("[ERROR]") else "error"
        meta["preview"] = "Registros actualizados correctamente"
        return result, meta

    elif tool_name == "list_storage_files":
        files = list_storage_files()
        res_str = json.dumps(files, indent=2, ensure_ascii=False)
        meta["status"] = "success"
        meta["preview"] = "Registros verificados"
        return res_str, meta

    else:
        err = f"Herramienta desconocida: {tool_name}"
        meta["status"] = "error"
        meta["preview"] = err
        return err, meta

def process_agro_chat(user_message: str) -> Dict[str, Any]:
    """
    Orquestador del flujo con Claude y Tool Calling
    """
    api_key = settings.ANTHROPIC_API_KEY
    executed_tools_log = []

    if not api_key:
        return _simulate_agro_tool_calling(user_message)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        history = get_sliding_history(limit=6)
        messages_payload: List[Dict[str, Any]] = []

        for h in history:
            messages_payload.append({
                "role": h["role"],
                "content": h["content"]
            })

        messages_payload.append({
            "role": "user",
            "content": user_message
        })

        max_tool_iterations = 5
        iteration = 0
        final_text = ""

        while iteration < max_tool_iterations:
            iteration += 1

            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=CLAUDE_TOOLS,
                messages=messages_payload
            )

            if response.stop_reason == "tool_use":
                messages_payload.append({
                    "role": "assistant",
                    "content": response.content
                })

                tool_results_content = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_use_id = block.id

                        tool_output, tool_meta = execute_tool(tool_name, tool_input)
                        executed_tools_log.append(tool_meta)

                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": tool_output
                        })

                messages_payload.append({
                    "role": "user",
                    "content": tool_results_content
                })

            else:
                for block in response.content:
                    if hasattr(block, 'text'):
                        final_text += block.text
                break

        if not final_text:
            final_text = "Se completaron las operaciones solicitadas en los registros del establecimiento."

        # Limpiar cualquier mención involuntaria de archivos en la respuesta de Claude
        final_text = re.sub(r'INDEX\.md|MEMORY\.md|CHAT_HISTORY\.json|files_storage/?', 'los registros del campo', final_text)

        append_to_history(user_message, final_text, executed_tools_log)

        return {
            "response": final_text,
            "tool_calls": executed_tools_log,
            "current_gasoil": get_current_gasoil_stock(),
            "is_demo": False
        }

    except Exception as e:
        print(f"Error con Anthropic API: {e}")
        sim_res = _simulate_agro_tool_calling(user_message)
        sim_res["warning"] = f"Aviso: {str(e)}"
        return sim_res

def _simulate_agro_tool_calling(user_message: str) -> Dict[str, Any]:
    """
    Motor local de Tool Calling: descuenta el gasoil REAL en disco y responde sin nombres de archivos
    """
    msg = user_message.lower()
    executed_tools = []
    
    is_consumption = any(w in msg for w in ["gaste", "gasté", "gastamos", "consum", "cargar", "cargamos", "usamos", "descontar", "restar"])
    has_fuel_word = any(w in msg for w in ["gasoil", "gas oil", "combustible", "diesel", "tanque", "litro", "litros", "lts"])

    # 1. Caso Consumo o Gasto de Combustible
    if is_consumption and has_fuel_word:
        # Extraer cantidad de litros del mensaje
        numbers = re.findall(r'(\d+(?:[\.,]\d+)?)', user_message)
        liters = 0.0
        if numbers:
            # Tomar el primer número (ej: 500)
            liters = float(numbers[0].replace('.', '').replace(',', '.'))
        else:
            liters = 500.0  # valor por defecto si no especifica número

        # 1.1 Ejecutar Tool Call de lectura
        _, read_meta = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(read_meta)

        # 1.2 Ejecutar descuento real en INDEX.md
        old_stock, new_stock, formatted_new = deduct_gasoil_stock(liters)
        _, write_idx_meta = execute_tool("write_storage_file", {
            "filename": "INDEX.md", 
            "content": read_storage_file("INDEX.md")
        })
        executed_tools.append(write_idx_meta)

        # 1.3 Asentar registro en MEMORY.md
        mem_content = read_storage_file("MEMORY.md")
        mem_updated = mem_content + f"\n- Consumo registrado: {liters} L de gasoil reportados por el usuario. Nuevo stock en tanque: {formatted_new} L."
        write_storage_file("MEMORY.md", mem_updated)
        _, write_mem_meta = execute_tool("write_storage_file", {
            "filename": "MEMORY.md",
            "content": mem_updated
        })
        executed_tools.append(write_mem_meta)

        # Alerta de umbral de 5000 litros
        if new_stock <= 5000:
            alerta = f"⚠️ **ALERTA CRÍTICA:** El nivel del tanque ha bajado a {formatted_new} Litros, alcanzando el umbral mínimo de seguridad. Se recomienda contactar inmediatamente al distribuidor para pedir el camión cisterna."
        else:
            alerta = f"✅ El nivel permanece seguro por encima del umbral de reserva (margen actual: {int(new_stock - 5000):,} L por sobre el límite de aviso)."

        reply = (
            f"⛽ **Registro de Combustible Actualizado con Éxito:**\n\n"
            f"- **Consumo descontado:** {int(liters) if liters.is_integer() else liters} Litros.\n"
            f"- **Nuevo stock en el tanque cisterna:** **{formatted_new} Litros** (Capacidad total: 15.000 L).\n"
            f"- **Estado de reserva:** {alerta}\n\n"
            f"He actualizado el inventario central del campo y registrado el movimiento en la bitácora operativa."
        )

    # 2. Caso Consulta de Combustible (sin gasto)
    elif has_fuel_word:
        _, read_meta = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(read_meta)
        stock_str = get_current_gasoil_stock()

        reply = (
            f"⛽ **Estado Actual de Combustibles:**\n\n"
            f"- **Stock disponible en el tanque cisterna:** **{stock_str} Litros** de Gasoil Grado 2.\n"
            f"- **Capacidad máxima del tanque:** 15.000 Litros.\n"
            f"- **Consumo diario promedio:** Entre 450 y 600 litros/día en labores de siembra activa.\n"
            f"- **Directiva de seguridad:** Solicitar camión cisterna cuando el nivel baje a 5.000 Litros.\n\n"
            f"Según los registros del establecimiento, contamos con suministro suficiente para continuar las tareas programadas."
        )

    # 3. Caso Lotes o Siembra
    elif any(w in msg for w in ["lote", "siembra", "sembr", "soja", "maiz", "cultivo"]):
        _, meta1 = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta1)
        _, meta2 = execute_tool("read_storage_file", {"filename": "MEMORY.md"})
        executed_tools.append(meta2)

        reply = (
            "🌾 **Informe Operativo de Lotes y Siembra:**\n\n"
            "1. **Lote 1 - 'La Esperanza' (120 ha):**\n"
            "   - **Cultivo:** Soja de 1ra (Variedad Don Mario 46R18).\n"
            "   - **Avance:** 75% completado (restan unas 30 ha).\n"
            "   - **Prioridad:** Concluir antes de las precipitaciones pronosticadas para el fin de semana.\n\n"
            "2. **Lote 2 - 'El Ombú' (85 ha):**\n"
            "   - Maíz Tardío (Dekalb 72-10). Barbecho químico listo.\n\n"
            "3. **Lote 3 - 'Bajo Grande' (210 ha):**\n"
            "   - Rastrojo cosechado, pendiente de análisis de fertilidad de suelo.\n\n"
            "Según las directivas de la administración, la prioridad absoluta es finalizar el Lote 1."
        )

    # 4. Caso Maquinaria
    elif any(w in msg for w in ["maquinaria", "tractor", "sembradora", "cosechadora", "pla"]):
        _, meta = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta)

        reply = (
            "🚜 **Parque de Maquinaria y Equipamiento Activo:**\n\n"
            "- **Tractor John Deere 7200R (200 HP):** Operando en Lote 1 con 3.420 horas de motor. Service al día.\n"
            "- **Sembradora Crucianelli Pionera (27 líneas a 52 cm):** Calibrada con placa para soja y dosificación variable.\n"
            "- **Pulverizadora Pla MAP 3 3300:** Lista en galpón central con picos antideriva colocados.\n"
            "- **Cosechadora Case IH 7230:** Resguardada y lista para la cosecha.\n\n"
            "Toda la maquinaria principal se encuentra en estado operativo según los registros del campo."
        )

    # 5. Caso General
    else:
        _, meta = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta)
        stock_str = get_current_gasoil_stock()

        reply = (
            f"🚜 **IA Desk Agro - Copiloto de Campo:**\n\n"
            f"He consultado los registros operativos del campo. Estamos en plena **Campaña Gruesa 2026/2027**.\n\n"
            f"- **Prioridad activa:** Terminar la siembra de soja en el Lote 1 'La Esperanza'.\n"
            f"- **Combustible:** {stock_str} Litros disponibles en el tanque cisterna.\n"
            f"- **Maquinaria:** Tractor John Deere y sembradora Crucianelli operativos.\n\n"
            f"Puedes consultarme sobre cualquier lote, stock de insumos o indicarme gastos de combustible para actualizar el inventario automáticamente."
        )

    append_to_history(user_message, reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "current_gasoil": get_current_gasoil_stock(),
        "is_demo": True
    }
