import re
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime
from django.conf import settings
import anthropic

from .storage_service import (
    read_file,
    write_file,
    append_memory,
    update_memory,
    list_storage_files,
    get_sliding_history,
    append_to_history
)

CLAUDE_TOOLS = [
    {
        "name": "read_file",
        "description": "Lee el contenido íntegro de un archivo en files_storage/ ('stock_gasoil.json', 'stock_insumos.json', 'registro_lotes.json', 'INDEX.md', 'MEMORY.md').",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre exacto del archivo a leer."
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "write_file",
        "description": "Crea o actualiza un archivo en files_storage/ con el contenido JSON o Markdown actualizado con cálculos matemáticos precisos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo a escribir (ej: 'stock_gasoil.json', 'stock_insumos.json', 'registro_lotes.json')."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido completo estructurado a guardar."
                }
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "append_memory",
        "description": "Agrega una nueva anotación o reporte de labor con fecha al final de 'MEMORY.md'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry": {
                    "type": "string",
                    "description": "Texto descriptivo de la labor o evento para la memoria de negocio."
                }
            },
            "required": ["entry"]
        }
    },
    {
        "name": "update_memory",
        "description": "Actualiza o reescribe completamente la memoria de negocio en 'MEMORY.md'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Nuevo contenido en Markdown para MEMORY.md."
                }
            },
            "required": ["content"]
        }
    }
]

def load_system_prompt() -> str:
    prompt_path = settings.BASE_DIR / "app" / "prompts" / "system_prompt.txt"
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return "Eres IA Desk Agro, copiloto de operaciones rurales."

def execute_native_tool(tool_name: str, tool_args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    meta = {"tool": tool_name, "args": tool_args}

    if tool_name == "read_file":
        filename = tool_args.get("filename", "")
        output = read_file(filename)
        meta["preview"] = f"Lectura de {filename} ({len(output)} bytes)"
        return output, meta

    elif tool_name == "write_file":
        filename = tool_args.get("filename", "")
        content = tool_args.get("content", "")
        output = write_file(filename, content)
        meta["preview"] = f"Actualización de {filename} ({len(content)} bytes)"
        return output, meta

    elif tool_name == "append_memory":
        entry = tool_args.get("entry", "")
        output = append_memory(entry)
        meta["preview"] = f"Registro en memoria: {entry[:60]}..."
        return output, meta

    elif tool_name == "update_memory":
        content = tool_args.get("content", "")
        output = update_memory(content)
        meta["preview"] = "Memoria operativa reescrita"
        return output, meta

    else:
        err = f"Herramienta no reconocida: {tool_name}"
        meta["preview"] = err
        return err, meta

def get_dashboard_summary() -> Dict[str, Any]:
    """Lee las planillas físicas y consolida los 4 depósitos de gasoil e insumos"""
    summary = {
        "cisterna_planta": {"actual": 14500, "max": 22000},
        "tanque_grande": {"actual": 3500, "max": 5000},
        "tanque_chico": {"actual": 1800, "max": 3000},
        "acopio_por_retirar": 8000,
        "total_campo": 19800,
        "total_con_acopio": 27800,
        "semillas_soja": 440,
        "semillas_maiz": 220,
        "map_tn": 22.0,
        "glifosato_lts": 1200
    }

    try:
        g = json.loads(read_file("stock_gasoil.json"))
        deps = g.get("depositos", {})
        cp = deps.get("cisterna_planta", {})
        tg = deps.get("tanque_grande", {})
        tc = deps.get("tanque_chico", {})
        ac = deps.get("acopio_por_retirar", {})

        summary['cisterna_planta'] = {"actual": cp.get("stock_actual_litros", 14500), "max": cp.get("capacidad_max_litros", 22000)}
        summary['tanque_grande'] = {"actual": tg.get("stock_actual_litros", 3500), "max": tg.get("capacidad_max_litros", 5000)}
        summary['tanque_chico'] = {"actual": tc.get("stock_actual_litros", 1800), "max": tc.get("capacidad_max_litros", 3000)}
        summary['acopio_por_retirar'] = ac.get("litros_disponibles", 8000)

        totales = g.get("totales", {})
        summary["total_campo"] = totales.get("stock_fisico_campo_litros", summary['cisterna_planta']["actual"] + summary['tanque_grande']["actual"] + summary['tanque_chico']["actual"])
        summary["total_con_acopio"] = totales.get("stock_total_con_acopio_litros", summary["total_campo"] + summary['acopio_por_retirar'])
    except Exception as e:
        print(f"Error parsing stock_gasoil.json: {e}")

    try:
        ins = json.loads(read_file("stock_insumos.json"))
        for s in ins.get("semillas", []):
            if "Soja" in s.get("especie", ""):
                summary["semillas_soja"] = s.get("stock_actual_bolsas", 440)
            elif "Maíz" in s.get("especie", ""):
                summary["semillas_maiz"] = s.get("stock_actual_bolsas", 220)
        for f in ins.get("fitosanitarios", []):
            if "Glifosato" in f.get("nombre", ""):
                summary["glifosato_lts"] = f.get("stock_actual", 1200)
    except Exception:
        pass

    return summary

def extract_liters(msg: str, default: float = 300.0) -> float:
    """
    Extrae la cantidad de litros gastados/movidos con tolerancia a cualquier redacción:
    - Con unidades: '400 litros', '400 lts', '400 l', '1.500 lts'
    - Sin unidades: 'retiré 400 del grande', 'saqué 250', 'gasté 300'
    - Discrimina números de capacidad ('tanque de 5000') para no confundir la capacidad con el gasto.
    """
    # 1. Búsqueda explícita con unidad de volumen
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt|l)", msg, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1).replace(".", "").replace(",", "."))
            if val > 0:
                return val
        except ValueError:
            pass

    # 2. Número inmediatamente posterior al verbo de acción
    verb_pattern = (
        r"(?:retir(?:[eé]|ar|amos|o|aron)?|"
        r"saqu(?:[eé]|ar|amos|o|aron)?|"
        r"sac(?:ar|o|amos|aron)?|"
        r"gast(?:[eé]|ar|amos|o|aron|ados)?|"
        r"consum(?:[ií]|ir|imos|ieron|o)?|"
        r"carg(?:[eé]|ar|amos|o|aron)?|"
        r"descont(?:[aá]|ar|ame|aron)?|"
        r"rest(?:[aá]|ar|amos)?|"
        r"baj(?:[aá]|ar|amos)?|"
        r"llev(?:[eé]|ar|amos|aron)?|"
        r"us(?:[eé]|ar|amos|aron|o)?)\s+(?:unos\s+|aprox\s+)?(\d+(?:[\.,]\d+)?)"
    )
    m_verb = re.search(verb_pattern, msg, re.IGNORECASE)
    if m_verb:
        try:
            val = float(m_verb.group(1).replace(".", "").replace(",", "."))
            if val > 0:
                return val
        except ValueError:
            pass

    # 3. Filtrado de números generales descartando capacidades de tanques o identificadores
    tokens = re.findall(r"\d+(?:[\.,]\d+)?", msg)
    cleaned = []
    for t in tokens:
        try:
            val = float(t.replace(".", "").replace(",", "."))
            if val in [22000.0, 5000.0, 3000.0] and re.search(rf"(?:de|del|capacidad|tanque)\s+{re.escape(t)}", msg, re.IGNORECASE):
                continue
            if val in [1.0, 2.0, 3.0, 4.0] and re.search(rf"(?:tanque|deposito|lote)\s+{re.escape(t)}", msg, re.IGNORECASE):
                continue
            cleaned.append(val)
        except ValueError:
            pass

    return cleaned[0] if cleaned else default

def identify_tank(msg: str) -> str:
    """
    Identifica de forma flexible el depósito mencionado:
    - tanque_chico: 'chico', 'chiquito', 'pequeño', 'carretón', '3000', '3k'
    - cisterna_planta: 'cisterna', 'planta', 'central', '22000', '22k'
    - tanque_grande: 'grande', '5000', '5k', 'móvil'
    - acopio_por_retirar: 'acopio', 'ypf', 'distribuidor', 'saldo'
    Por defecto ante mención genérica: tanque_grande (cisterna de apoyo estándar en campo).
    """
    msg_low = msg.lower()
    if any(w in msg_low for w in ["chico", "chiquito", "pequeño", "pequeno", "carretón", "carreton", "3000", "3.000", "3k", "auxilio"]):
        return "tanque_chico"
    if any(w in msg_low for w in ["planta", "central", "22000", "22.000", "22k"]):
        return "cisterna_planta"
    if "cisterna" in msg_low and not any(w in msg_low for w in ["movil", "móvil", "grande"]):
        return "cisterna_planta"
    if any(w in msg_low for w in ["grande", "5000", "5.000", "5k", "móvil", "movil"]):
        return "tanque_grande"
    if any(w in msg_low for w in ["acopio", "ypf", "distribuidor", "por retirar", "saldo"]):
        return "acopio_por_retirar"
    return "tanque_grande"

def is_fuel_transfer_or_acopio(msg: str) -> bool:
    """
    Determina si la intención es mover combustible entre depósitos o traer de acopio,
    diferenciándolo de un retiro/gasto de consumo físico.
    """
    msg_low = msg.lower()
    if any(w in msg_low for w in ["pasar", "transferir", "mover", "trasladar"]):
        return True
    if "acopio" in msg_low and any(w in msg_low for w in ["traer", "retirar", "flete", "mandar", "cargar", "llevar", "pasar"]):
        return True
    tanks_mentioned = []
    if any(w in msg_low for w in ["chico", "3000"]):
        tanks_mentioned.append("tanque_chico")
    if any(w in msg_low for w in ["grande", "5000"]):
        tanks_mentioned.append("tanque_grande")
    if any(w in msg_low for w in ["cisterna", "planta", "22000"]):
        tanks_mentioned.append("cisterna_planta")
    if len(tanks_mentioned) >= 2 and any(p in msg_low for p in [" a ", " al ", " hacia ", " para el tanque"]):
        return True
    return False

def process_agro_chat(user_message: str, is_whatsapp: bool = False, sender_name: str = "Productor") -> Dict[str, Any]:
    api_key = settings.ANTHROPIC_API_KEY
    system_prompt = load_system_prompt()
    executed_tools_log = []

    if is_whatsapp:
        prompt_input = f"[REPORTE DE WHATSAPP DE: {sender_name}]:\n\"{user_message}\"\n\nInterpreta las labores, haz los descuentos matemáticos precisos en los depósitos de stock_gasoil.json (Cisterna Planta, Tanque Grande, Tanque Chico, Acopio) o insumos usando las herramientas nativas, y confirma sin nombrar archivos técnicos."
    else:
        prompt_input = user_message

    if not api_key:
        return _simulate_agro_engine(user_message, is_whatsapp, sender_name)

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
            "content": prompt_input
        })

        max_iterations = 6
        iteration = 0
        final_text = ""

        while iteration < max_iterations:
            iteration += 1

            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1800,
                system=system_prompt,
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

                        tool_output, tool_meta = execute_native_tool(tool_name, tool_input)
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
                    if hasattr(block, "text"):
                        final_text += block.text
                break

        if not final_text:
            final_text = "Se completaron las labores solicitadas en los registros del campo."

        final_text = re.sub(r"stock_gasoil\.json|stock_insumos\.json|registro_lotes\.json|INDEX\.md|MEMORY\.md|files_storage/?", "los registros del campo", final_text)
        append_to_history(user_message, final_text, executed_tools_log)

        return {
            "response": final_text,
            "tool_calls": executed_tools_log,
            "is_demo": False,
            "stock_data": get_dashboard_summary()
        }

    except Exception as e:
        print(f"Error Anthropic API: {e}")
        sim_res = _simulate_agro_engine(user_message, is_whatsapp, sender_name)
        sim_res["warning"] = f"Aviso API: {str(e)}"
        return sim_res

def _simulate_agro_engine(user_message: str, is_whatsapp: bool, sender_name: str) -> Dict[str, Any]:
    msg = user_message.lower()
    executed_tools = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Cargar stock_gasoil.json
    gasoil_raw, meta_g_read = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
    executed_tools.append(meta_g_read)
    gasoil_json = json.loads(gasoil_raw)
    deps = gasoil_json["depositos"]

    # Detectar labor de siembra combinada (insumos + combustible)
    is_sowing = any(w in msg for w in ["sembr", "soja", "maíz", "maiz", "dm46"]) and any(w in msg for w in ["bolsa", "ha", "hect", "lote", "insumo"])
    # Detectar compra o nuevo acopio
    is_purchase = any(w in msg for w in ["llegó", "llego", "compra", "compramos", "descargaron", "descarga", "entró", "entro", "remito"]) and not any(w in msg for w in ["gaste", "gasté", "gastamos", "retire", "retiré", "saque", "saqué", "consum", "salida"])
    # Detectar transferencia interna o retiro de acopio a tanque
    is_transfer = is_fuel_transfer_or_acopio(user_message)
    # Detectar retiro, gasto o consumo de combustible (salida de un tanque)
    has_spending_verb = any(w in msg for w in ["retir", "saqu", "sacar", "saco", "gast", "consum", "us", "chup", "carg", "descont", "baj", "rest", "llev"])
    has_fuel_word = any(w in msg for w in ["litros", "lts", "lt", "gasoil", "diesel", "combustible"])
    has_numbers = any(char.isdigit() for char in user_message)

    # ==============================================================
    # 1. CASO SIEMBRA COMBINADA (SEMILLA + COMBUSTIBLE)
    # ==============================================================
    if is_sowing:
        insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        lotes_raw, meta_l = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.extend([meta_i, meta_l])

        insumos = json.loads(insumos_raw)
        lotes = json.loads(lotes_raw)

        seeds_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa)", msg)
        has_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:hect[áa]reas?|has?)", msg)

        liters_out = extract_liters(user_message, default=280.0)
        bolsas_out = int(float(seeds_match.group(1))) if seeds_match else 40
        has_done = float(has_match.group(1)) if has_match else 25.0

        tank_key = identify_tank(user_message)
        if tank_key == "acopio_por_retirar":
            tank_key = "tanque_grande"

        deps[tank_key]['stock_actual_litros'] = max(0.0, deps[tank_key]['stock_actual_litros'] - liters_out)

        gasoil_json['totales']['stock_fisico_campo_litros'] = (
            deps['cisterna_planta']['stock_actual_litros'] +
            deps['tanque_grande']['stock_actual_litros'] +
            deps['tanque_chico']['stock_actual_litros']
        )
        gasoil_json['totales']['stock_total_con_acopio_litros'] = (
            gasoil_json['totales']['stock_fisico_campo_litros'] +
            deps['acopio_por_retirar']['litros_disponibles']
        )

        gasoil_json.setdefault("salidas", []).append({
            "fecha": today_str,
            "deposito_origen": deps[tank_key]['nombre'],
            "labor": f"Siembra soja ({has_done} ha)",
            "litros": liters_out,
            "operario": sender_name
        })

        _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(w_g)

        nuevo_stk_bolsas = 440
        for s in insumos.get("semillas", []):
            if "Soja" in s.get("especie", ""):
                s["stock_actual_bolsas"] = max(0, s.get("stock_actual_bolsas", 440) - bolsas_out)
                s["stock_total_kg"] = s["stock_actual_bolsas"] * 40
                nuevo_stk_bolsas = s["stock_actual_bolsas"]

        _, w_i = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos, indent=2, ensure_ascii=False)})
        executed_tools.append(w_i)

        lote1 = lotes["lotes"][0]
        lote1["estado_actual"] = f"Siembra en progreso: {has_done} ha sumadas hoy"
        _, w_l = execute_native_tool("write_file", {"filename": "registro_lotes.json", "content": json.dumps(lotes, indent=2, ensure_ascii=False)})
        executed_tools.append(w_l)

        entry_mem = f"Labor Siembra Lote 1 por {sender_name}: {has_done} ha, -{bolsas_out} bolsas soja, -{liters_out} L de {deps[tank_key]['nombre']}."
        _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
        executed_tools.append(w_m)

        reply = (
            f"🚜 **Reporte de Siembra Asentado:**\n\n"
            f"- **Labor:** Siembra de soja en Lote 1 ({has_done} hectáreas).\n"
            f"- **Semilla descontada:** {bolsas_out} bolsas de DM 46R18 ({bolsas_out * 40:,} kg).\n"
            f"- **Stock remanente de semillas:** **{nuevo_stk_bolsas} bolsas** en galpón.\n"
            f"- **Combustible descontado:** **{int(liters_out):,} Litros** desde **{deps[tank_key]['nombre']}** (Remanente: **{int(deps[tank_key]['stock_actual_litros']):,} L**).\n"
            f"- **Stock total físico en campo:** **{int(gasoil_json['totales']['stock_fisico_campo_litros']):,} Litros**.\n\n"
            f"Los registros de insumos, combustible y lote han sido actualizados."
        )

    # ==============================================================
    # 2. CASO COMPRA DE GASOIL O NUEVO ACOPIO
    # ==============================================================
    elif is_purchase:
        liters_in = extract_liters(user_message, default=5000.0)

        if "acopio" in msg:
            deps['acopio_por_retirar']['litros_disponibles'] += liters_in
            descrip = f"Compra de {int(liters_in):,} L sumados a la cuenta de Gasoil por Retirar en YPF Directo"
        else:
            target_dep = "cisterna_planta"
            deps[target_dep]['stock_actual_litros'] = min(
                deps[target_dep]['capacidad_max_litros'],
                deps[target_dep]['stock_actual_litros'] + liters_in
            )
            descrip = f"Descarga de {int(liters_in):,} L en Cisterna Planta (remito asentado)"

        gasoil_json['totales']['stock_fisico_campo_litros'] = (
            deps['cisterna_planta']['stock_actual_litros'] +
            deps['tanque_grande']['stock_actual_litros'] +
            deps['tanque_chico']['stock_actual_litros']
        )
        gasoil_json['totales']['stock_total_con_acopio_litros'] = (
            gasoil_json['totales']['stock_fisico_campo_litros'] +
            deps['acopio_por_retirar']['litros_disponibles']
        )

        gasoil_json.setdefault("entradas", []).append({
            "fecha": today_str,
            "detalle": descrip,
            "litros": liters_in,
            "registrado_por": sender_name
        })

        _, meta_w = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(meta_w)

        _, meta_m = execute_native_tool("append_memory", {"entry": descrip})
        executed_tools.append(meta_m)

        reply = (
            f"⛽ **Ingreso de Combustible Registrado:**\n\n"
            f"- **Operación:** {descrip}.\n"
            f"- **Cisterna Planta (Máx 22.000 L):** {int(deps['cisterna_planta']['stock_actual_litros']):,} Litros.\n"
            f"- **Tanque Grande (Máx 5.000 L):** {int(deps['tanque_grande']['stock_actual_litros']):,} Litros.\n"
            f"- **Tanque Chico (Máx 3.000 L):** {int(deps['tanque_chico']['stock_actual_litros']):,} Litros.\n"
            f"- **Gasoil por Retirar (Acopio):** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} Litros**.\n\n"
            f"**Total disponible con acopio:** {int(gasoil_json['totales']['stock_total_con_acopio_litros']):,} Litros."
        )

    # ==============================================================
    # 3. CASO TRANSFERENCIA ENTRE TANQUES O RETIRO DE ACOPIO A TANQUE
    # ==============================================================
    elif is_transfer:
        liters_to_move = extract_liters(user_message, default=2000.0)

        if "acopio" in msg:
            # Traer de Acopio YPF hacia uno de los tanques del campo
            destino_key = "tanque_chico" if "chico" in msg else ("tanque_grande" if "grande" in msg else "cisterna_planta")
            actual_acopio = deps['acopio_por_retirar']['litros_disponibles']
            liters_moved = min(actual_acopio, liters_to_move)

            deps['acopio_por_retirar']['litros_disponibles'] -= liters_moved
            deps[destino_key]['stock_actual_litros'] = min(
                deps[destino_key]['capacidad_max_litros'],
                deps[destino_key]['stock_actual_litros'] + liters_moved
            )
            motivo = f"Retiro de {int(liters_moved):,} L de acopio YPF hacia {deps[destino_key]['nombre']}"
        else:
            # Transferencia interna entre tanques de campo
            if "chico" in msg and ("cisterna" in msg or "planta" in msg):
                origen_key = "cisterna_planta"
                destino_key = "tanque_chico"
            elif "grande" in msg and ("cisterna" in msg or "planta" in msg):
                origen_key = "cisterna_planta"
                destino_key = "tanque_grande"
            elif "chico" in msg and "grande" in msg:
                origen_key = "tanque_grande"
                destino_key = "tanque_chico"
            else:
                origen_key = "cisterna_planta"
                destino_key = "tanque_grande"

            liters_moved = min(deps[origen_key]['stock_actual_litros'], liters_to_move)
            deps[origen_key]['stock_actual_litros'] -= liters_moved
            deps[destino_key]['stock_actual_litros'] = min(
                deps[destino_key]['capacidad_max_litros'],
                deps[destino_key]['stock_actual_litros'] + liters_moved
            )
            motivo = f"Transferencia interna de {int(liters_moved):,} L desde {deps[origen_key]['nombre']} hacia {deps[destino_key]['nombre']}"

        # Recalcular totales
        gasoil_json['totales']['stock_fisico_campo_litros'] = (
            deps['cisterna_planta']['stock_actual_litros'] +
            deps['tanque_grande']['stock_actual_litros'] +
            deps['tanque_chico']['stock_actual_litros']
        )
        gasoil_json['totales']['stock_total_con_acopio_litros'] = (
            gasoil_json['totales']['stock_fisico_campo_litros'] +
            deps['acopio_por_retirar']['litros_disponibles']
        )

        gasoil_json.setdefault("transferencias_internas", []).append({
            "fecha": today_str,
            "motivo": motivo,
            "litros": liters_moved,
            "operario": sender_name
        })

        _, meta_w = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(meta_w)

        _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
        executed_tools.append(meta_m)

        reply = (
            f"🚚 **Movimiento de Combustible Registrado con Éxito:**\n\n"
            f"- **Operación:** {motivo}.\n"
            f"- **Cisterna Planta (Máx 22.000 L):** {int(deps['cisterna_planta']['stock_actual_litros']):,} Litros.\n"
            f"- **Tanque Grande (Máx 5.000 L):** {int(deps['tanque_grande']['stock_actual_litros']):,} Litros.\n"
            f"- **Tanque Chico (Máx 3.000 L):** {int(deps['tanque_chico']['stock_actual_litros']):,} Litros.\n"
            f"- **Gasoil por Retirar (Acopio YPF):** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} Litros**.\n\n"
            f"**Total físico en campo:** {int(gasoil_json['totales']['stock_fisico_campo_litros']):,} Litros | **Total con acopio:** {int(gasoil_json['totales']['stock_total_con_acopio_litros']):,} Litros."
        )

    # ==============================================================
    # 4. CASO RETIRO / GASTO / CONSUMO DE UN TANQUE (SALIDA)
    # ==============================================================
    elif has_spending_verb or (has_fuel_word and has_numbers) or ("tanque" in msg and has_numbers):
        liters_out = extract_liters(user_message, default=300.0)
        tank_key = identify_tank(user_message)

        # Si el usuario dijo específicamente "retiré del acopio", se interpreta como traslado al campo
        if tank_key == "acopio_por_retirar":
            target_field = "cisterna_planta"
            liters_moved = min(deps['acopio_por_retirar']['litros_disponibles'], liters_out)
            deps['acopio_por_retirar']['litros_disponibles'] -= liters_moved
            deps[target_field]['stock_actual_litros'] = min(
                deps[target_field]['capacidad_max_litros'],
                deps[target_field]['stock_actual_litros'] + liters_moved
            )
            motivo = f"Retiro de {int(liters_moved):,} L de acopio YPF ingresados a Cisterna Planta"
            gasoil_json['totales']['stock_fisico_campo_litros'] = (
                deps['cisterna_planta']['stock_actual_litros'] +
                deps['tanque_grande']['stock_actual_litros'] +
                deps['tanque_chico']['stock_actual_litros']
            )
            gasoil_json['totales']['stock_total_con_acopio_litros'] = (
                gasoil_json['totales']['stock_fisico_campo_litros'] +
                deps['acopio_por_retirar']['litros_disponibles']
            )
            gasoil_json.setdefault("transferencias_internas", []).append({
                "fecha": today_str,
                "motivo": motivo,
                "litros": liters_moved,
                "operario": sender_name
            })
            _, meta_w = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"📦 **Retiro de Acopio Asentado:**\n\n"
                f"- **Operación:** {motivo}.\n"
                f"- **Saldo remanente en Acopio YPF:** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} Litros**.\n"
                f"- **Cisterna Planta actualizada:** **{int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L**.\n\n"
                f"**Total físico en campo:** {int(gasoil_json['totales']['stock_fisico_campo_litros']):,} L."
            )
        else:
            # Descuento matemático del tanque físico
            current_tank_stock = deps[tank_key]['stock_actual_litros']
            deps[tank_key]['stock_actual_litros'] = max(0.0, current_tank_stock - liters_out)

            gasoil_json['totales']['stock_fisico_campo_litros'] = (
                deps['cisterna_planta']['stock_actual_litros'] +
                deps['tanque_grande']['stock_actual_litros'] +
                deps['tanque_chico']['stock_actual_litros']
            )
            gasoil_json['totales']['stock_total_con_acopio_litros'] = (
                gasoil_json['totales']['stock_fisico_campo_litros'] +
                deps['acopio_por_retirar']['litros_disponibles']
            )

            machinery = "Maquinaria de labor"
            if "tractor" in msg:
                machinery = "Tractor John Deere"
            elif "cosechadora" in msg or "trilla" in msg:
                machinery = "Cosechadora"
            elif "pulverizadora" in msg or "mosquito" in msg:
                machinery = "Pulverizadora"
            elif "camioneta" in msg or "chata" in msg:
                machinery = "Camioneta"

            gasoil_json.setdefault("salidas", []).append({
                "fecha": today_str,
                "deposito_origen": deps[tank_key]['nombre'],
                "maquinaria": machinery,
                "litros": liters_out,
                "operario": sender_name
            })

            _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
            executed_tools.append(w_g)

            entry_mem = f"Consumo/Retiro de {int(liters_out):,} L desde {deps[tank_key]['nombre']} ({machinery}) reportado por {sender_name}."
            _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
            executed_tools.append(w_m)

            pct_filled = round((deps[tank_key]['stock_actual_litros'] / deps[tank_key]['capacidad_max_litros']) * 100)

            reply = (
                f"⛽ **Registro de Combustible Gastado:**\n\n"
                f"- **Depósito descontado:** **{deps[tank_key]['nombre']}** (Capacidad: {deps[tank_key]['capacidad_max_litros']:,} L).\n"
                f"- **Litros gastados / retirados:** **{int(liters_out):,} Litros** ({machinery}).\n"
                f"- **Stock remanente en {deps[tank_key]['nombre']}:** **{int(deps[tank_key]['stock_actual_litros']):,} Litros** ({pct_filled}% disponible).\n\n"
                f"📊 **Totales consolidados del campo:**\n"
                f"• 🏭 Cisterna Planta: **{int(deps['cisterna_planta']['stock_actual_litros']):,}** / 22.000 L\n"
                f"• 🚜 Tanque Grande: **{int(deps['tanque_grande']['stock_actual_litros']):,}** / 5.000 L\n"
                f"• 🛢️ Tanque Chico: **{int(deps['tanque_chico']['stock_actual_litros']):,}** / 3.000 L\n"
                f"• 📋 Gasoil por Retirar (Acopio YPF): **{int(deps['acopio_por_retirar']['litros_disponibles']):,} L**\n\n"
                f"👉 **Total físico en campo:** **{int(gasoil_json['totales']['stock_fisico_campo_litros']):,} L** | **Total con acopio:** **{int(gasoil_json['totales']['stock_total_con_acopio_litros']):,} L**.\n\n"
                f"Los registros del campo han sido actualizados con los litros gastados."
            )

    # ==============================================================
    # 5. CASO CONSULTA DE COMBUSTIBLE (ESTADO DE LOS 4 DEPÓSITOS)
    # ==============================================================
    elif any(w in msg for w in ["gasoil", "gas oil", "combustible", "tanque", "cisterna", "acopio", "saldo", "cuanto", "cuánto"]):
        cp = deps['cisterna_planta']
        tg = deps['tanque_grande']
        tc = deps['tanque_chico']
        ac = deps['acopio_por_retirar']
        tot_campo = gasoil_json['totales']['stock_fisico_campo_litros']
        tot_gral = gasoil_json['totales']['stock_total_con_acopio_litros']

        reply = (
            f"⛽ **Estado de Combustibles (4 Depósitos y Acopio):**\n\n"
            f"1. 🏭 **Cisterna Planta:** **{int(cp['stock_actual_litros']):,} / {cp['capacidad_max_litros']:,} Litros** ({round(cp['stock_actual_litros']/cp['capacidad_max_litros']*100)}% lleno).\n"
            f"2. 🚜 **Tanque Grande:** **{int(tg['stock_actual_litros']):,} / {tg['capacidad_max_litros']:,} Litros** ({round(tg['stock_actual_litros']/tg['capacidad_max_litros']*100)}% lleno).\n"
            f"3. 🛢️ **Tanque Chico:** **{int(tc['stock_actual_litros']):,} / {tc['capacidad_max_litros']:,} Litros** ({round(tc['stock_actual_litros']/tc['capacidad_max_litros']*100)}% lleno).\n"
            f"4. 📋 **Gasoil por Retirar (Acopio YPF):** **{int(ac['litros_disponibles']):,} Litros** disponibles.\n\n"
            f"📊 **Totales:**\n"
            f"- **Stock físico en el campo:** **{int(tot_campo):,} Litros** (Capacidad máxima combinada: 30.000 L).\n"
            f"- **Total disponible con acopio:** **{int(tot_gral):,} Litros**.\n\n"
            f"Todos los depósitos se encuentran registrados según los movimientos del establecimiento."
        )

    # ==============================================================
    # 6. CASO RENDIMIENTOS Y LOTES
    # ==============================================================
    elif any(w in msg for w in ["rinde", "rendimiento", "cosecha", "trilla", "qq", "kilos"]):
        _, meta = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.append(meta)

        reply = (
            f"🌾 **Rendimientos y Datos de Cosecha (Campaña 2026/2027):**\n\n"
            f"- **Lote 1 (Soja 1ra - 120 ha):** En siembra activa. Rinde proyectado: 3.800 kg/ha (38 qq/ha).\n"
            f"- **Lote 2 (Maíz Tardío - 85 ha):** En barbecho. Rinde objetivo: 9.500 kg/ha (95 qq/ha).\n"
            f"- **Lote 3 (Trigo Cosechado - 210 ha):** Total: 819.000 kg (**3.900 kg/ha / 39 qq/ha**).\n\n"
            f"Datos consolidados en las planillas del campo."
        )

    # ==============================================================
    # 7. CASO INSUMOS EN GALPÓN
    # ==============================================================
    elif any(w in msg for w in ["insumos", "semilla", "glifosato", "fertilizante", "map", "galpón", "galpon"]):
        summary = get_dashboard_summary()
        reply = (
            f"🌱 **Inventario de Insumos en Galpón:**\n\n"
            f"- **Semilla de Soja (DM 46R18):** {summary['semillas_soja']} bolsas ({summary['semillas_soja'] * 40:,} kg).\n"
            f"- **Semilla de Maíz (DK 72-10):** {summary['semillas_maiz']} bolsas ({summary['semillas_maiz'] * 80:,} kg).\n"
            f"- **Fertilizante MAP:** {summary['map_tn']} toneladas a granel.\n"
            f"- **Glifosato Concentrado:** {summary['glifosato_lts']} litros en bidones.\n\n"
            f"Todos los insumos listos para despacho a lotes."
        )

    # ==============================================================
    # 8. CASO DEFAULT
    # ==============================================================
    else:
        summary = get_dashboard_summary()
        reply = (
            f"🚜 **IA Desk Agro - Copiloto de Operaciones:**\n\n"
            f"He verificado los 4 depósitos de combustible y el inventario del campo:\n"
            f"- **Cisterna Planta:** {summary['cisterna_planta']['actual']:,} / 22.000 L\n"
            f"- **Tanque Grande:** {summary['tanque_grande']['actual']:,} / 5.000 L\n"
            f"- **Tanque Chico:** {summary['tanque_chico']['actual']:,} / 3.000 L\n"
            f"- **Gasoil por Retirar (Acopio):** {summary['acopio_por_retirar']:,} L\n"
            f"- **Semillas:** {summary['semillas_soja']} bolsas de Soja y {summary['semillas_maiz']} bolsas de Maíz.\n\n"
            f"¿Qué labor o movimiento de combustible deseas consultar o registrar?"
        )

    append_to_history(user_message, reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "is_demo": True,
        "stock_data": get_dashboard_summary()
    }
