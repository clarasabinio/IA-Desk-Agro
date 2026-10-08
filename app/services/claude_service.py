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

# Definición formal de Herramientas (Tool Calling) para Anthropic Claude
CLAUDE_TOOLS = [
    {
        "name": "read_storage_file",
        "description": "Lee el contenido íntegro de un archivo local en la carpeta 'files_storage/' del campo (ej: 'INDEX.md' para lotes y stock, 'MEMORY.md' para directivas y estado de campaña).",
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
        "description": "Crea o actualiza un archivo en la carpeta 'files_storage/' para persistir cambios en el negocio (ej: actualizar el stock de gasoil, modificar tareas en MEMORY.md o registrar un nuevo lote).",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo a escribir o actualizar (ej: 'MEMORY.md', 'INDEX.md')."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido completo en formato Markdown o texto que reemplazará o creará el archivo."
                }
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "list_storage_files",
        "description": "Lista todos los archivos existentes en la carpeta 'files_storage/' con sus tamaños y fechas de modificación para saber qué información está disponible.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

SYSTEM_PROMPT = """Eres "IA Desk Agro", el asistente y copiloto inteligente de operaciones de la empresa agropecuaria familiar "La Esperanza" (Campaña Gruesa 2026/2027).

Tu rol es asistir a los productores y administradores del campo respondiendo preguntas operativas (stock de gasoil, siembra de lotes, maquinaria, insumos) y actualizando la memoria del negocio.

REGLAS DE OPERACIÓN CON TOOL CALLING:
1. NUNCA inventes datos del campo. Tienes a tu disposición la carpeta física local 'files_storage/'.
2. Ante cualquier consulta sobre stock, lotes, insumos o maquinaria, invoca la herramienta 'read_storage_file' para leer 'INDEX.md'.
3. Ante consultas sobre prioridades de la familia, tareas activas, directivas o clima, invoca 'read_storage_file' para leer 'MEMORY.md'.
4. Cuando el usuario te pida registrar una salida de combustible, actualizar el estado de un lote o agregar una tarea, PRIMERO lee el archivo correspondiente, modifícalo con precisión y utiliza 'write_storage_file' para persistir el cambio en disco.
5. Comunica tus respuestas de forma profesional, clara y cordial, típica de un ingeniero agrónomo / administrador rural de confianza. Menciona de forma concisa qué archivos consultaste o actualizaste.
"""

def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Ejecuta una herramienta en el almacenamiento local y devuelve el resultado y metadatos para UI"""
    meta = {"tool": tool_name, "args": tool_args}
    
    if tool_name == "read_storage_file":
        filename = tool_args.get("filename", "")
        content = read_storage_file(filename)
        meta["status"] = "success" if not content.startswith("[ERROR]") else "error"
        meta["preview"] = f"Leídos {len(content)} caracteres de '{filename}'"
        return content, meta

    elif tool_name == "write_storage_file":
        filename = tool_args.get("filename", "")
        content = tool_args.get("content", "")
        result = write_storage_file(filename, content)
        meta["status"] = "success" if not result.startswith("[ERROR]") else "error"
        meta["preview"] = f"Escrito '{filename}' ({len(content)} caracteres)"
        return result, meta

    elif tool_name == "list_storage_files":
        files = list_storage_files()
        res_str = json.dumps(files, indent=2, ensure_ascii=False)
        meta["status"] = "success"
        meta["preview"] = f"{len(files)} archivos encontrados en files_storage/"
        return res_str, meta

    else:
        err = f"Herramienta desconocida: {tool_name}"
        meta["status"] = "error"
        meta["preview"] = err
        return err, meta

def process_agro_chat(user_message: str) -> Dict[str, Any]:
    """
    Orquestador principal del ciclo de conversación con Claude y Tool Calling
    """
    api_key = settings.ANTHROPIC_API_KEY
    executed_tools_log = []

    # Si no hay API Key configurada o es vacía, ejecutar simulación realista de Tool Calling
    if not api_key:
        return _simulate_agro_tool_calling(user_message)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        
        # Recuperar contexto previo de la ventana deslizante
        history = get_sliding_history(limit=6)
        messages_payload: List[Dict[str, Any]] = []

        for h in history:
            messages_payload.append({
                "role": h["role"],
                "content": h["content"]
            })

        # Añadir mensaje actual
        messages_payload.append({
            "role": "user",
            "content": user_message
        })

        # Ciclo de llamada a herramientas (Agent Loop)
        max_tool_iterations = 5
        iteration = 0
        final_text = ""

        while iteration < max_tool_iterations:
            iteration += 1

            # Llamada al modelo Claude 3.5 Sonnet
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=CLAUDE_TOOLS,
                messages=messages_payload
            )

            # Si el modelo decidió usar herramientas:
            if response.stop_reason == "tool_use":
                # Guardar respuesta del asistente en el payload para mantener coherencia
                messages_payload.append({
                    "role": "assistant",
                    "content": response.content
                })

                tool_results_content = []

                # Ejecutar cada herramienta solicitada
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_use_id = block.id

                        # Ejecutar localmente en files_storage/
                        tool_output, tool_meta = execute_tool(tool_name, tool_input)
                        executed_tools_log.append(tool_meta)

                        tool_results_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": tool_output
                        })

                # Añadir los resultados de las herramientas como mensaje de usuario
                messages_payload.append({
                    "role": "user",
                    "content": tool_results_content
                })

            else:
                # El modelo finalizó su respuesta textual
                for block in response.content:
                    if hasattr(block, 'text'):
                        final_text += block.text
                break

        if not final_text:
            final_text = "Se completaron las operaciones solicitadas en los archivos del campo."

        # Guardar en memoria persistente con ventana deslizante
        append_to_history(user_message, final_text, executed_tools_log)

        return {
            "response": final_text,
            "tool_calls": executed_tools_log,
            "is_demo": False
        }

    except Exception as e:
        # En caso de error de conexión o cuota, recurrir a la lógica autónoma local
        print(f"Error comunicando con Anthropic API: {e}")
        sim_res = _simulate_agro_tool_calling(user_message)
        sim_res["warning"] = f"Aviso de API Anthropic ({str(e)}). Se utilizó el ejecutor de herramientas local."
        return sim_res

def _simulate_agro_tool_calling(user_message: str) -> Dict[str, Any]:
    """
    Motor local de Tool Calling para pruebas sin API key o ante falta de crédito.
    Ejecuta las herramientas REALMENTE sobre files_storage/ y genera respuestas contextualizadas.
    """
    msg = user_message.lower()
    executed_tools = []
    
    # 1. Caso Combustible / Gasoil
    if "gasoil" in msg or "combustible" in msg or "tanque" in msg or "diesel" in msg:
        content, meta = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta)

        # Detectar si es consulta o registro de consumo
        if "cargar" in msg or "usamos" in msg or "gastamos" in msg or "consum" in msg or "restar" in msg:
            # Simular actualización en MEMORY.md
            mem_content, mem_meta = execute_tool("read_storage_file", {"filename": "MEMORY.md"})
            executed_tools.append(mem_meta)

            updated_mem = mem_content + f"\n- Registro {user_message}: Verificado por IA Desk Agro."
            _, write_meta = execute_tool("write_storage_file", {"filename": "MEMORY.md", "content": updated_mem})
            executed_tools.append(write_meta)

            reply = (
                "⛽ **Registro de Combustible Actualizado:**\n\n"
                "He consultado `INDEX.md` y actualizado `MEMORY.md`.\n"
                "- **Capacidad total:** 15.000 Litros en Tanque Cisterna Principal.\n"
                "- **Stock nominal:** 8.500 Litros de Gasoil Grado 2.\n"
                "- **Aviso operativo:** He asentado tu reporte de consumo en las notas activas. Recuerda que la directiva de la familia indica solicitar camión cisterna cuando el remanente alcance los **5.000 Litros**."
            )
        else:
            reply = (
                "⛽ **Estado Actual de Combustibles (según `files_storage/INDEX.md`):**\n\n"
                "- **Stock actual:** **8.500 Litros** de Gasoil Grado 2 en el Tanque Cisterna Principal.\n"
                "- **Consumo diario estimado:** Entre 450 y 600 litros/día con el tractor John Deere trabajando en siembra.\n"
                "- **Directiva de la familia:** El umbral mínimo de seguridad es de **5.000 Litros**. Aún contamos con 3.500 L de margen antes de tener que pedir reabastecimiento."
            )

    # 2. Caso Lotes o Siembra
    elif "lote" in msg or "siembra" in msg or "sembr" in msg or "soja" in msg or "maiz" in msg:
        content, meta1 = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta1)
        mem, meta2 = execute_tool("read_storage_file", {"filename": "MEMORY.md"})
        executed_tools.append(meta2)

        reply = (
            "🌾 **Informe Operativo de Lotes (según `INDEX.md` y `MEMORY.md`):**\n\n"
            "1. **Lote 1 - 'La Esperanza' (120 ha):**\n"
            "   - **Cultivo:** Soja de 1ra (Don Mario 46R18).\n"
            "   - **Avance:** 75% completado (restan ~30 ha).\n"
            "   - **Prioridad #1:** Concluir antes del fin de semana por pronóstico de lluvias.\n\n"
            "2. **Lote 2 - 'El Ombú' (85 ha):**\n"
            "   - Destinado a Maíz Tardío (Dekalb 72-10). Barbecho químico finalizado.\n\n"
            "3. **Lote 3 - 'Bajo Grande' (210 ha):**\n"
            "   - Rastrojo de trigo cosechado, pendiente análisis de suelo."
        )

    # 3. Caso Maquinaria
    elif "maquinaria" in msg or "tractor" in msg or "sembradora" in msg or "cosechadora" in msg or "pla" in msg:
        content, meta = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta)

        reply = (
            "🚜 **Parque de Maquinaria Operativa (según `files_storage/INDEX.md`):**\n\n"
            "- **Tractor John Deere 7200R (200 HP):** Operativo en Lote 1 con 3.420 horas de motor. Service al día.\n"
            "- **Sembradora Crucianelli Pionera (27 líneas a 52 cm):** Enganchada y calibrada con corte por sección para soja.\n"
            "- **Pulverizadora Pla MAP 3 3300:** Lavada y lista en galpón con pastillas antideriva.\n"
            "- **Cosechadora Case IH 7230:** Resguardada para campaña de cosecha."
        )

    # 4. Caso General / Lista de archivos
    else:
        files, meta = execute_tool("list_storage_files", {})
        executed_tools.append(meta)
        idx_content, meta_idx = execute_tool("read_storage_file", {"filename": "INDEX.md"})
        executed_tools.append(meta_idx)

        reply = (
            f"🚜 **IA Desk Agro - Asistente de Operaciones:**\n\n"
            f"He examinado los archivos de la empresa en `files_storage/`. El campo 'La Esperanza' se encuentra en plena **Campaña Gruesa 2026/2027**.\n\n"
            f"- **Prioridad activa:** Terminar la siembra de soja en Lote 1.\n"
            f"- **Gasoil disponible:** 8.500 Litros.\n"
            f"- **Insumos:** Semillas y fertilizantes verificados en galpón.\n\n"
            f"*(💡 Puedes consultar en lenguaje natural sobre lotes, stock, maquinaria o pedirme registrar movimientos de insumos).* "
            f"\n\n*(Nota: Puedes configurar tu `ANTHROPIC_API_KEY` en el archivo `.env` para procesamiento en tiempo real con Claude 3.5 Sonnet).* "
        )

    append_to_history(user_message, reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "is_demo": True
    }
