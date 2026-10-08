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
        meta["preview"] = f"Registro agregado a la memoria: {entry[:60]}..."
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

def process_agro_chat(user_message: str, is_whatsapp: bool = False, sender_name: str = "Productor") -> Dict[str, Any]:
    api_key = settings.ANTHROPIC_API_KEY
    system_prompt = load_system_prompt()
    executed_tools_log = []

    if is_whatsapp:
        prompt_input = f"[REPORTE INFORMAL DE WHATSAPP DE: {sender_name}]:\n\"{user_message}\"\n\nInterpreta las labores, haz los descuentos matemáticos precisos en stock_gasoil.json, stock_insumos.json o registro_lotes.json usando las herramientas nativas, y confirma la operación sin nombrar archivos."
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

def get_dashboard_summary() -> Dict[str, Any]:
    gasoil_raw = read_file("stock_gasoil.json")
    insumos_raw = read_file("stock_insumos.json")
    lotes_raw = read_file("registro_lotes.json")

    summary = {
        "gasoil_stock": 8000,
        "semillas_soja": 480,
        "semillas_maiz": 220,
        "map_tn": 22.0,
        "glifosato_lts": 1200,
        "lote1_avance": "90 ha / 120 ha"
    }

    try:
        g = json.loads(gasoil_raw)
        summary["gasoil_stock"] = g.get("tanque_cisterna", {}).get("stock_actual_litros", 8000)
    except Exception:
        pass

    try:
        ins = json.loads(insumos_raw)
        for s in ins.get("semillas", []):
            if "Soja" in s.get("especie", ""):
                summary["semillas_soja"] = s.get("stock_actual_bolsas", 480)
            elif "Maíz" in s.get("especie", ""):
                summary["semillas_maiz"] = s.get("stock_actual_bolsas", 220)
        for f in ins.get("fitosanitarios", []):
            if "Glifosato" in f.get("nombre", ""):
                summary["glifosato_lts"] = f.get("stock_actual", 1200)
    except Exception:
        pass

    return summary

def _simulate_agro_engine(user_message: str, is_whatsapp: bool, sender_name: str) -> Dict[str, Any]:
    msg = user_message.lower()
    executed_tools = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Extraer cantidades específicas por unidad
    fuel_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|l\b)', msg)
    seeds_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa\b)', msg)
    has_match = re.search(r'(\d+(?:[\.,]\d+)?)\s*(?:hect[áa]reas?|has?\b)', msg)
    general_nums = re.findall(r'(\d+(?:[\.,]\d+)?)', user_message)

    # 1. CASO COMPRA DE GASOIL (Camión cisterna)
    if ("llegó" in msg or "llego" in msg or "compra" in msg or "descargaron" in msg) and ("gasoil" in msg or "camión" in msg or "cisterna" in msg):
        gasoil_raw, read_meta = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
        executed_tools.append(read_meta)
        gasoil_json = json.loads(gasoil_raw)

        liters_in = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else (float(general_nums[0]) if general_nums else 4000.0)

        current_liters = gasoil_json["tanque_cisterna"]["stock_actual_litros"]
        new_liters = min(gasoil_json["tanque_cisterna"]["capacidad_litros"], current_liters + liters_in)
        gasoil_json["tanque_cisterna"]["stock_actual_litros"] = new_liters
        gasoil_json["tanque_cisterna"]["ultima_actualizacion"] = today_str

        gasoil_json["entradas"].append({
            "fecha": today_str,
            "proveedor": "YPF Directo",
            "litros": liters_in,
            "remito_nro": "R-0048-2026",
            "registrado_por": sender_name
        })

        new_json_str = json.dumps(gasoil_json, indent=2, ensure_ascii=False)
        _, write_meta = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": new_json_str})
        executed_tools.append(write_meta)

        entry_mem = f"Ingreso de combustible: {liters_in} L de gasoil descargados en tanque cisterna por {sender_name}. Stock: {new_liters} L."
        _, mem_meta = execute_native_tool("append_memory", {"entry": entry_mem})
        executed_tools.append(mem_meta)

        reply = (
            f"⛽ **Ingreso de Combustible Registrado:**\n\n"
            f"- **Cantidad ingresada:** {int(liters_in):,} Litros.\n"
            f"- **Nuevo stock en tanque cisterna:** **{int(new_liters):,} Litros** (Capacidad: 15.000 L).\n"
            f"- **Proveedor:** YPF Directo asentado en el inventario central.\n\n"
            f"El stock ha sido actualizado exitosamente y la entrada quedó asentada en la bitácora."
        )

    # 2. CASO REPORTE MIXTO O LABOR DE CAMPO (Siembra + Gasoil + Hectáreas)
    elif ("sembr" in msg or "bolsa" in msg or "dm46" in msg or "soja" in msg) and (fuel_match or "gasoil" in msg or "tanque" in msg):
        gasoil_raw, meta_g = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
        insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        lotes_raw, meta_l = execute_native_tool("read_file", {"filename": "registro_lotes.json"})

        executed_tools.extend([meta_g, meta_i, meta_l])

        gasoil_json = json.loads(gasoil_raw)
        insumos = json.loads(insumos_raw)
        lotes = json.loads(lotes_raw)

        liters_out = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else 280.0
        bolsas_out = int(float(seeds_match.group(1))) if seeds_match else 40
        has_done = float(has_match.group(1)) if has_match else 25.0

        # Descontar gasoil
        curr_g = gasoil_json["tanque_cisterna"]["stock_actual_litros"]
        new_g = max(0.0, curr_g - liters_out)
        gasoil_json["tanque_cisterna"]["stock_actual_litros"] = new_g
        gasoil_json["salidas"].append({
            "fecha": today_str,
            "maquinaria": "Tractor John Deere 7200R",
            "lote": "Lote 1 - La Esperanza",
            "labor": f"Siembra de soja ({has_done} ha)",
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

        entry_mem = f"Labor Lote 1 por {sender_name}: {has_done} ha sembradas, -{bolsas_out} bolsas soja, -{liters_out} L gasoil. Tanque: {new_g} L."
        _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
        executed_tools.append(w_m)

        reply = (
            f"🚜 **Reporte de Siembra Procesado con Éxito:**\n\n"
            f"- **Labor:** Siembra de soja en Lote 1 ({has_done} hectáreas avanzadas).\n"
            f"- **Semilla descontada:** {bolsas_out} bolsas de DM 46R18 ({bolsas_out * 40:,} kg).\n"
            f"- **Stock remanente de semillas:** **{nuevo_stk_bolsas} bolsas** en galpón.\n"
            f"- **Combustible consumido:** {int(liters_out)} Litros de gasoil.\n"
            f"- **Nuevo stock en tanque cisterna:** **{int(new_g):,} Litros**.\n\n"
            f"Todas las planillas de insumos, combustible y registro del lote han sido actualizadas."
        )

    # 3. CASO GASTO DE COMBUSTIBLE SOLO
    elif any(w in msg for w in ["gaste", "gasté", "gastamos", "consum", "cargar", "cargamos", "usamos"]) and any(w in msg for w in ["gasoil", "gas oil", "combustible", "diesel"]):
        gasoil_raw, meta_g = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
        executed_tools.append(meta_g)
        gasoil_json = json.loads(gasoil_raw)

        liters_out = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else (float(general_nums[0]) if general_nums else 350.0)

        current_liters = gasoil_json["tanque_cisterna"]["stock_actual_litros"]
        new_liters = max(0.0, current_liters - liters_out)
        gasoil_json["tanque_cisterna"]["stock_actual_litros"] = new_liters
        gasoil_json["tanque_cisterna"]["ultima_actualizacion"] = today_str

        gasoil_json["salidas"].append({
            "fecha": today_str,
            "maquinaria": "Tractor / Pulverizadora",
            "lote": "Lote en laboreo",
            "litros": liters_out,
            "operario": sender_name
        })

        _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(w_g)

        entry_mem = f"Consumo de combustible: {liters_out} L de gasoil reportados por {sender_name}. Remanente: {new_liters} L."
        _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
        executed_tools.append(w_m)

        alerta = "⚠️ **ALERTA:** Nivel crítico en tanque cisterna (<= 5.000 L). Coordinar pedido de camión." if new_liters <= 5000 else "✅ Nivel óptimo por encima del umbral de reserva."

        reply = (
            f"⛽ **Registro de Consumo de Combustible:**\n\n"
            f"- **Consumo descontado:** {int(liters_out):,} Litros.\n"
            f"- **Stock actual en el tanque:** **{int(new_liters):,} Litros**.\n"
            f"- **Estado de reserva:** {alerta}\n\n"
            f"He actualizado las planillas de inventario y asentado el consumo en la bitácora operativa."
        )

    # 4. CASO FUMIGACIÓN / PULVERIZACIÓN (Glifosato, 2,4-D)
    elif any(w in msg for w in ["pulveriz", "fumig", "glifo", "glifosato", "enlist", "pla"]):
        insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        gasoil_raw, meta_g = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})

        executed_tools.extend([meta_i, meta_g])
        insumos = json.loads(insumos_raw)
        gasoil_json = json.loads(gasoil_raw)

        glifo_out = 170
        liters_out = float(fuel_match.group(1).replace('.', '').replace(',', '.')) if fuel_match else 110.0

        for f in insumos["fitosanitarios"]:
            if "Glifosato" in f["nombre"]:
                f["stock_actual"] = max(0, f["stock_actual"] - glifo_out)
                stk_glifo_rem = f["stock_actual"]

        curr_g = gasoil_json["tanque_cisterna"]["stock_actual_litros"]
        new_g = max(0.0, curr_g - liters_out)
        gasoil_json["tanque_cisterna"]["stock_actual_litros"] = new_g

        _, w_i = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos, indent=2, ensure_ascii=False)})
        _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.extend([w_i, w_g])

        entry_mem = f"Fumigación Lote 2 por {sender_name}: -{glifo_out} L glifosato, -{liters_out} L gasoil. Remanente glifo: {stk_glifo_rem} L."
        _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
        executed_tools.append(w_m)

        reply = (
            f"🧪 **Labor de Pulverización Registrada:**\n\n"
            f"- **Lote tratado:** Lote 2 'El Ombú' (85 hectáreas con Pla MAP 3).\n"
            f"- **Herbicida aplicado:** {glifo_out} Litros de Glifosato 66%.\n"
            f"- **Stock remanente de glifosato:** **{stk_glifo_rem} Litros**.\n"
            f"- **Combustible consumido:** {int(liters_out)} Litros de gasoil (Tanque: **{int(new_g):,} L**).\n\n"
            f"El libro de campo y el stock de fitosanitarios han sido actualizados."
        )

    # 5. CASO RENDIMIENTOS / TRILLA / COSECHA
    elif any(w in msg for w in ["rinde", "rendimiento", "cosecha", "trilla", "qq", "kilos"]):
        _, meta = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.append(meta)

        reply = (
            f"🌾 **Rendimientos y Datos de Cosecha (Campaña 2026/2027):**\n\n"
            f"- **Lote 1 (Soja 1ra - 120 ha):** En siembra finalizada. Rinde proyectado: 3.800 kg/ha (38 qq/ha).\n"
            f"- **Lote 2 (Maíz Tardío - 85 ha):** En barbecho. Rinde objetivo: 9.500 kg/ha (95 qq/ha).\n"
            f"- **Lote 3 (Trigo Cosechado - 210 ha):**\n"
            f"  • Cosecha total: 819.000 kg.\n"
            f"  • Rendimiento obtenido: **3.900 kg/ha (39 quintales/ha)**.\n\n"
            f"Todos los datos de lotes y pesadas se encuentran al día en el registro agronómico."
        )

    # 6. CASO CONSULTA DE STOCK DE INSUMOS
    elif any(w in msg for w in ["insumo", "insumos", "semilla", "fertilizante", "map", "urea"]):
        insumos_raw, meta = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta)
        insumos = json.loads(insumos_raw)

        reply = (
            f"📦 **Inventario Consolidado de Insumos:**\n\n"
            f"1. **Semillas en Galpón:**\n"
            f"   - Soja DM 46R18: **{insumos['semillas'][0]['stock_actual_bolsas']} bolsas** ({insumos['semillas'][0]['stock_total_kg']:,} kg).\n"
            f"   - Maíz Dekalb 72-10: **{insumos['semillas'][1]['stock_actual_bolsas']} bolsas** curadas.\n\n"
            f"2. **Fertilizantes:**\n"
            f"   - MAP (11-52-0): **{insumos['fertilizantes'][0]['stock_actual_tn']} Toneladas**.\n"
            f"   - Urea Granulada: **{insumos['fertilizantes'][1]['stock_actual_tn']} Toneladas**.\n\n"
            f"3. **Fitosanitarios:**\n"
            f"   - Glifosato 66%: **{insumos['fitosanitarios'][0]['stock_actual']} Litros**.\n"
            f"   - 2,4-D Enlist: **{insumos['fitosanitarios'][1]['stock_actual']} Litros**."
        )

    # 7. CASO CONSULTA DE GASOIL
    elif any(w in msg for w in ["gasoil", "gas oil", "combustible", "diesel", "tanque"]):
        gasoil_raw, meta = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
        executed_tools.append(meta)
        gasoil_json = json.loads(gasoil_raw)
        stk = gasoil_json["tanque_cisterna"]["stock_actual_litros"]

        reply = (
            f"⛽ **Estado Actual del Combustible:**\n\n"
            f"- **Stock disponible:** **{int(stk):,} Litros** en tanque cisterna principal.\n"
            f"- **Capacidad máxima:** 15.000 Litros.\n"
            f"- **Umbral mínimo de advertencia:** 5.000 Litros.\n"
            f"- **Estado de reserva:** {'✅ Nivel seguro con margen adecuado.' if stk > 5000 else '⚠️ Advertencia: coordinar compra.'}\n\n"
            f"El suministro se encuentra registrado según los movimientos del establecimiento."
        )

    # 8. DEFAULT
    else:
        _, meta = execute_native_tool("read_file", {"filename": "INDEX.md"})
        executed_tools.append(meta)
        summary = get_dashboard_summary()

        reply = (
            f"🚜 **IA Desk Agro - Copiloto de Operaciones:**\n\n"
            f"He consultado el inventario y estado de la empresa 'La Esperanza'.\n\n"
            f"- **Gasoil en cisterna:** {summary['gasoil_stock']:,} Litros.\n"
            f"- **Semillas en galpón:** {summary['semillas_soja']} bolsas de Soja y {summary['semillas_maiz']} bolsas de Maíz.\n"
            f"- **Lotes:** Lote 1 con siembra activa, Lote 2 con barbecho listo.\n\n"
            f"Puedes hacerme cualquier consulta de stock, consultar rendimientos de trilla o usar el simulador de WhatsApp para reportar labores de campo."
        )

    append_to_history(user_message, reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "is_demo": True,
        "stock_data": get_dashboard_summary()
    }
