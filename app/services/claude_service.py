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
    prompt_path = settings.BASE_DIR / 'app' / 'prompts' / 'system_prompt.txt'
    if prompt_path.exists():
        with open(prompt_path, 'r', encoding='utf-8') as f:
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

        summary["cisterna_planta"] = {"actual": cp.get("stock_actual_litros", 14500), "max": cp.get("capacidad_max_litros", 22000)}
        summary["tanque_grande"] = {"actual": tg.get("stock_actual_litros", 3500), "max": tg.get("capacidad_max_litros", 5000)}
        summary["tanque_chico"] = {"actual": tc.get("stock_actual_litros", 1800), "max": tc.get("capacidad_max_litros", 3000)}
        summary["acopio_por_retirar"] = ac.get("litros_disponibles", 8000)

        totales = g.get("totales", {})
        summary["total_campo"] = totales.get("stock_fisico_campo_litros", summary["cisterna_planta"]["actual"] + summary["tanque_grande"]["actual"] + summary["tanque_chico"]["actual"])
        summary["total_con_acopio"] = totales.get("stock_total_con_acopio_litros", summary["total_campo"] + summary["acopio_por_retirar"])
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
                    if hasattr(block, 'text'):
                        final_text += block.text
                break

        if not final_text:
            final_text = "Se completaron las labores solicitadas en los registros del campo."

        final_text = re.sub(r'stock_gasoil\.json|stock_insumos\.json|registro_lotes\.json|INDEX\.md|MEMORY\.md|files_storage/?', 'los registros del campo', final_text)
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

    fuel_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|l\b)', msg)
    seeds_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa\b)', msg)
    has_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:hect[áa]reas?|has?\b)', msg)
    general_nums = re.findall(r'(\d+(?:[\.,]\d+)?)', user_message)

    # Cargar stock_gasoil.json
    gasoil_raw, meta_g_read = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
    executed_tools.append(meta_g_read)
    gasoil_json = json.loads(gasoil_raw)

    deps = gasoil_json["depositos"]

    # 1. CASO TRANSFERENCIA ENTRE TANQUES O RETIRO DE ACOPIO
    # ej: "retirar 3000 lts del acopio", "pasar 1500 lts de cisterna a tanque grande"
    if any(w in msg for w in ["pasar", "transferir", "mover", "retirar", "traer"]) and ("acopio" in msg or "tanque" in msg or "cisterna" in msg):
        liters = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else 2000.0

        if "acopio" in msg:
            # Retirar del acopio hacia Cisterna Planta o Tanque Grande
            destino_key = "tanque_chico" if "chico" in msg else ("tanque_grande" if "grande" in msg else "cisterna_planta")
            actual_acopio = deps["acopio_por_retirar"]["litros_disponibles"]
            liters_moved = min(actual_acopio, liters)

            deps["acopio_por_retirar"]["litros_disponibles"] -= liters_moved
            deps[destino_key]["stock_actual_litros"] = min(
                deps[destino_key]["capacidad_max_litros"],
                deps[destino_key]["stock_actual_litros"] + liters_moved
            )
            motivo = f"Retiro de {int(liters_moved):,} L de acopio YPF hacia {deps[destino_key]['nombre']}"
        else:
            # Transferencia interna (ej: de Cisterna Planta a Tanque Grande / Chico)
            origen_key = "cisterna_planta"
            destino_key = "tanque_chico" if "chico" in msg else "tanque_grande"
            liters_moved = min(deps[origen_key]["stock_actual_litros"], liters)

            deps[origen_key]["stock_actual_litros"] -= liters_moved
            deps[destino_key]["stock_actual_litros"] = min(
                deps[destino_key]["capacidad_max_litros"],
                deps[destino_key]["stock_actual_litros"] + liters_moved
            )
            motivo = f"Transferencia interna de {int(liters_moved):,} L desde {deps[origen_key]['nombre']} hacia {deps[destino_key]['nombre']}"

        # Recalcular totales
        gasoil_json["totales"]["stock_fisico_campo_litros"] = (
            deps["cisterna_planta"]["stock_actual_litros"] +
            deps["tanque_grande"]["stock_actual_litros"] +
            deps["tanque_chico"]["stock_actual_litros"]
        )
        gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
            gasoil_json["totales"]["stock_fisico_campo_litros"] +
            deps["acopio_por_retirar"]["litros_disponibles"]
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

    # 2. CASO COMPRA DE GASOIL O NUEVO ACOPIO
    elif ("llegó" in msg or "llego" in msg or "compra" in msg or "descargaron" in msg or "compramos" in msg) and ("gasoil" in msg or "acopio" in msg or "camión" in msg):
        liters_in = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else (float(general_nums[0]) if general_nums else 5000.0)

        if "acopio" in msg:
            deps["acopio_por_retirar"]["litros_disponibles"] += liters_in
            descrip = f"Compra de {int(liters_in):,} L sumados a la cuenta de Gasoil por Retirar en YPF Directo."
        else:
            # Descarga en Cisterna Planta
            target_dep = "cisterna_planta"
            deps[target_dep]["stock_actual_litros"] = min(
                deps[target_dep]["capacidad_max_litros"],
                deps[target_dep]["stock_actual_litros"] + liters_in
            )
            descrip = f"Descarga de {int(liters_in):,} L en Cisterna Planta (remito asentado)."

        gasoil_json["totales"]["stock_fisico_campo_litros"] = (
            deps["cisterna_planta"]["stock_actual_litros"] +
            deps["tanque_grande"]["stock_actual_litros"] +
            deps["tanque_chico"]["stock_actual_litros"]
        )
        gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
            gasoil_json["totales"]["stock_fisico_campo_litros"] +
            deps["acopio_por_retirar"]["litros_disponibles"]
        )

        gasoil_json["entradas"].append({
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

    # 3. CASO REPORTE MIXTO O LABOR DE CAMPO (Siembra + Gasoil)
    elif ("sembr" in msg or "bolsa" in msg or "dm46" in msg or "soja" in msg) and (fuel_match or "gasoil" in msg or "tanque" in msg):
        insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        lotes_raw, meta_l = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.extend([meta_i, meta_l])

        insumos = json.loads(insumos_raw)
        lotes = json.loads(lotes_raw)

        liters_out = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else 280.0
        bolsas_out = int(float(seeds_match.group(1))) if seeds_match else 40
        has_done = float(has_match.group(1)) if has_match else 25.0

        # Descontar del Tanque Grande (o Tanque Chico si se menciona)
        tank_key = "tanque_chico" if "chico" in msg else "tanque_grande"
        deps[tank_key]["stock_actual_litros"] = max(0.0, deps[tank_key]["stock_actual_litros"] - liters_out)

        gasoil_json["totales"]["stock_fisico_campo_litros"] = (
            deps["cisterna_planta"]["stock_actual_litros"] +
            deps["tanque_grande"]["stock_actual_litros"] +
            deps["tanque_chico"]["stock_actual_litros"]
        )
        gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
            gasoil_json["totales"]["stock_fisico_campo_litros"] +
            deps["acopio_por_retirar"]["litros_disponibles"]
        )

        gasoil_json["salidas"].append({
            "fecha": today_str,
            "deposito_origen": deps[tank_key]["nombre"],
            "labor": f"Siembra soja ({has_done} ha)",
            "litros": liters_out,
            "operario": sender_name
        })

        _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(w_g)

        # Descontar semillas
        nuevo_stk_bolsas = 440
        for s in insumos["semillas"]:
            if "Soja" in s["especie"]:
                s["stock_actual_bolsas"] = max(0, s["stock_actual_bolsas"] - bolsas_out)
                s["stock_total_kg"] = s["stock_actual_bolsas"] * 40
                nuevo_stk_bolsas = s["stock_actual_bolsas"]

        _, w_i = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos, indent=2, ensure_ascii=False)})
        executed_tools.append(w_i)

        # Actualizar lote
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
            f"- **Stock de semillas:** **{nuevo_stk_bolsas} bolsas** en galpón.\n"
            f"- **Combustible descontado:** {int(liters_out)} Litros desde **{deps[tank_key]['nombre']}** (Remanente: **{int(deps[tank_key]['stock_actual_litros']):,} L**).\n"
            f"- **Stock total físico en campo:** **{int(gasoil_json['totales']['stock_fisico_campo_litros']):,} Litros**.\n\n"
            f"Planillas de insumos, combustible y registro de lote actualizadas."
        )

    # 4. CASO GASTO DE COMBUSTIBLE ESPECÍFICO
    elif any(w in msg for w in ["gaste", "gasté", "gastamos", "consum", "cargar", "cargamos", "usamos"]) and any(w in msg for w in ["gasoil", "gas oil", "combustible", "diesel"]):
        liters_out = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else (float(general_nums[0]) if general_nums else 300.0)

        # Identificar depósito de origen
        if "chico" in msg:
            tank_key = "tanque_chico"
        elif "planta" in msg or "cisterna" in msg:
            tank_key = "cisterna_planta"
        else:
            tank_key = "tanque_grande"

        deps[tank_key]["stock_actual_litros"] = max(0.0, deps[tank_key]["stock_actual_litros"] - liters_out)

        gasoil_json["totales"]["stock_fisico_campo_litros"] = (
            deps["cisterna_planta"]["stock_actual_litros"] +
            deps["tanque_grande"]["stock_actual_litros"] +
            deps["tanque_chico"]["stock_actual_litros"]
        )
        gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
            gasoil_json["totales"]["stock_fisico_campo_litros"] +
            deps["acopio_por_retirar"]["litros_disponibles"]
        )

        gasoil_json["salidas"].append({
            "fecha": today_str,
            "deposito_origen": deps[tank_key]["nombre"],
            "litros": liters_out,
            "operario": sender_name
        })

        _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(w_g)

        entry_mem = f"Consumo de {liters_out} L desde {deps[tank_key]['nombre']} reportado por {sender_name}."
        _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
        executed_tools.append(w_m)

        reply = (
            f"⛽ **Registro de Consumo de Combustible:**\n\n"
            f"- **Depósito descontado:** **{deps[tank_key]['nombre']}** (Capacidad: {deps[tank_key]['capacidad_max_litros']:,} L).\n"
            f"- **Consumo reportado:** {int(liters_out):,} Litros.\n"
            f"- **Stock remanente en {deps[tank_key]['nombre']}:** **{int(deps[tank_key]['stock_actual_litros']):,} Litros**.\n\n"
            f"**Totales consolidados:**\n"
            f"• Cisterna Planta: {int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L\n"
            f"• Tanque Grande: {int(deps['tanque_grande']['stock_actual_litros']):,} / 5.000 L\n"
            f"• Tanque Chico: {int(deps['tanque_chico']['stock_actual_litros']):,} / 3.000 L\n"
            f"• Gasoil por Retirar (Acopio): {int(deps['acopio_por_retirar']['litros_disponibles']):,} L\n"
            f"👉 **Total físico en campo:** **{int(gasoil_json['totales']['stock_fisico_campo_litros']):,} L** | **Total con acopio:** **{int(gasoil_json['totales']['stock_total_con_acopio_litros']):,} L**."
        )

    # 5. CASO CONSULTA DE COMBUSTIBLE (ESTADO DE LOS 4 DEPÓSITOS)
    elif any(w in msg for w in ["gasoil", "gas oil", "combustible", "tanque", "cisterna", "acopio"]):
        cp = deps["cisterna_planta"]
        tg = deps["tanque_grande"]
        tc = deps["tanque_chico"]
        ac = deps["acopio_por_retirar"]
        tot_campo = gasoil_json["totales"]["stock_fisico_campo_litros"]
        tot_gral = gasoil_json["totales"]["stock_total_con_acopio_litros"]

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

    # 6. CASO RENDIMIENTOS
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

    # 7. DEFAULT
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
