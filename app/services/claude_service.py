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
        "description": "Lee el contenido íntegro de un archivo en files_storage/ ('stock_gasoil.json', 'stock_insumos.json', 'stock_granos_silos.json', 'registro_lotes.json', 'INDEX.md', 'MEMORY.md').",
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
                    "description": "Nombre del archivo a escribir ('stock_gasoil.json', 'stock_insumos.json', 'stock_granos_silos.json', 'registro_lotes.json')."
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
    """Lee las planillas físicas y consolida gasoil, híbridos de maíz, granos en silos e insumos"""
    summary = {
        "cisterna_planta": {"actual": 12800, "max": 22000},
        "tanque_grande": {"actual": 4000, "max": 5000},
        "tanque_chico": {"actual": 2750, "max": 3000},
        "acopio_por_retirar": 4000,
        "total_campo": 19550,
        "total_con_acopio": 23550,
        "maiz_hibridos": [],
        "maiz_totales": {"en_planta": 240, "por_retirar": 190, "total_general": 430},
        "granos_silos": {
            "soja": {"total_tn": 540.0, "ubicaciones": []},
            "trigo": {"total_tn": 819.0, "ubicaciones": []},
            "total_general_tn": 1359.0
        },
        "semillas_soja": 440,
        "semillas_maiz": 430,
        "map_tn": 22.0,
        "glifosato_lts": 1200
    }

    # 1. Combustibles
    try:
        g = json.loads(read_file("stock_gasoil.json"))
        deps = g.get("depositos", {})
        cp = deps.get("cisterna_planta", {})
        tg = deps.get("tanque_grande", {})
        tc = deps.get("tanque_chico", {})
        ac = deps.get("acopio_por_retirar", {})

        summary["cisterna_planta"] = {"actual": cp.get("stock_actual_litros", 12800), "max": cp.get("capacidad_max_litros", 22000)}
        summary["tanque_grande"] = {"actual": tg.get("stock_actual_litros", 4000), "max": tg.get("capacidad_max_litros", 5000)}
        summary["tanque_chico"] = {"actual": tc.get("stock_actual_litros", 2750), "max": tc.get("capacidad_max_litros", 3000)}
        summary["acopio_por_retirar"] = ac.get("litros_disponibles", 4000)

        totales = g.get("totales", {})
        summary["total_campo"] = totales.get("stock_fisico_campo_litros", summary["cisterna_planta"]["actual"] + summary["tanque_grande"]["actual"] + summary["tanque_chico"]["actual"])
        summary["total_con_acopio"] = totales.get("stock_total_con_acopio_litros", summary["total_campo"] + summary["acopio_por_retirar"])
    except Exception as e:
        print(f"Error parsing stock_gasoil.json: {e}")

    # 2. Insumos y Semillas por Híbrido
    try:
        ins = json.loads(read_file("stock_insumos.json"))
        mz = ins.get("semillas_maiz", {})
        summary["maiz_hibridos"] = mz.get("hibridos", [])
        summary["maiz_totales"] = mz.get("totales", {"en_planta": 240, "por_retirar": 190, "total_general": 430})
        summary["semillas_maiz"] = summary["maiz_totales"].get("total_general_bolsas", 430)

        sj = ins.get("semillas_soja", {})
        summary["semillas_soja"] = sj.get("totales", {}).get("total_general_bolsas", 440)

        for f in ins.get("fertilizantes", []):
            if "MAP" in f.get("nombre", ""):
                summary["map_tn"] = f.get("stock_actual_tn", 22.0)
        for f in ins.get("fitosanitarios", []):
            if "Glifosato" in f.get("nombre", ""):
                summary["glifosato_lts"] = f.get("stock_actual", 1200)
    except Exception as e:
        print(f"Error parsing stock_insumos.json: {e}")

    # 3. Granos en Silos y Silobolsas (Toneladas)
    try:
        gr = json.loads(read_file("stock_granos_silos.json"))
        summary["granos_silos"] = {
            "soja": {
                "total_tn": gr.get("soja", {}).get("total_tn", 540.0),
                "ubicaciones": gr.get("soja", {}).get("ubicaciones", [])
            },
            "trigo": {
                "total_tn": gr.get("trigo", {}).get("total_tn", 819.0),
                "ubicaciones": gr.get("trigo", {}).get("ubicaciones", [])
            },
            "total_general_tn": gr.get("totales_generales", {}).get("total_granos_almacenados_tn", 1359.0)
        }
    except Exception as e:
        print(f"Error parsing stock_granos_silos.json: {e}")

    return summary

def extract_liters(msg: str, default: float = 300.0) -> float:
    """Extrae la cantidad de litros gastados/movidos con tolerancia a cualquier redacción"""
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt|l)", msg, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1).replace(".", "").replace(",", "."))
            if val > 0:
                return val
        except ValueError:
            pass

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
    """Identifica de forma flexible el depósito mencionado"""
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
        prompt_input = f"[REPORTE DE WHATSAPP DE: {sender_name}]:\n\"{user_message}\"\n\nInterpreta las labores, haz los descuentos matemáticos precisos en los depósitos de combustible, semillas por híbrido o granos en silos usando las herramientas nativas, y confirma sin nombrar archivos técnicos."
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

        final_text = re.sub(r"stock_gasoil\.json|stock_insumos\.json|stock_granos_silos\.json|registro_lotes\.json|INDEX\.md|MEMORY\.md|files_storage/?", "los registros del campo", final_text)
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

    # ==============================================================
    # 1. CASO SEMILLAS DE MAÍZ POR HÍBRIDO (BOLSAS EN PLANTA O POR RETIRAR)
    # ==============================================================
    is_corn_query_or_action = ("maiz" in msg or "maíz" in msg or "dekalb" in msg or "dk 72" in msg or "72-10" in msg or "pioneer" in msg or "p2089" in msg or "nidera" in msg or "ax 7784" in msg or ("hibrid" in msg and "semilla" in msg))
    # Excluir si es consulta de granos en silo o siembra de soja
    if is_corn_query_or_action and not ("soja" in msg and "sembr" in msg and not "maiz" in msg):
        insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_ins)
        insumos_json = json.loads(insumos_raw)
        mz_dict = insumos_json.get("semillas_maiz", {})
        hibridos = mz_dict.get("hibridos", [])

        # Identificar híbrido específico si se menciona
        target_hibrido = None
        if "dekalb" in msg or "dk" in msg or "72-10" in msg:
            target_hibrido = next((h for h in hibridos if "DK" in h["id"] or "Dekalb" in h["hibrido"]), None)
        elif "pioneer" in msg or "2089" in msg:
            target_hibrido = next((h for h in hibridos if "P2089" in h["id"] or "Pioneer" in h["hibrido"]), None)
        elif "nidera" in msg or "7784" in msg or "ax" in msg:
            target_hibrido = next((h for h in hibridos if "AX" in h["id"] or "Nidera" in h["hibrido"]), None)
        if not target_hibrido and hibridos:
            target_hibrido = hibridos[0]

        # Extraer cantidad de bolsas
        bags_match = re.search(r"(\d+)\s*(?:bolsas?|bolsa)?", msg)
        bags_qty = int(bags_match.group(1)) if (bags_match and bags_match.group(1) not in ["72", "10", "2089", "7784"]) else 40

        is_query_seeds = any(w in msg for w in ["?", "que", "qué", "cuanto", "cuánto", "saldo", "stock", "estado", "listar", "ver", "tenemos", "informe", "donde", "dónde"])
        is_moving_to_planta = (not is_query_seeds) and any(w in msg for w in ["retiré", "retire", "retiramos", "trajimos", "traje", "trasladamos", "llevamos", "pasamos", "cargar"]) and any(w in msg for w in ["planta", "campo", "galpon", "galpón", "bayer", "agronorte", "cooperativa"])
        is_sowing_corn = (not is_query_seeds) and any(w in msg for w in ["sembr", "siembra", "lote 2", "gastamos", "usamos"]) and not is_moving_to_planta

        if is_moving_to_planta and target_hibrido:
            # Trasladar bolsas de por_retirar a en_planta
            moved = min(target_hibrido["por_retirar_bolsas"], bags_qty)
            target_hibrido["por_retirar_bolsas"] -= moved
            target_hibrido["en_planta_bolsas"] += moved

            # Recalcular totales
            tot_planta = sum(h["en_planta_bolsas"] for h in hibridos)
            tot_retiro = sum(h["por_retirar_bolsas"] for h in hibridos)
            mz_dict["totales"]["bolsas_en_planta"] = tot_planta
            mz_dict["totales"]["bolsas_por_retirar"] = tot_retiro
            mz_dict["totales"]["total_general_bolsas"] = tot_planta + tot_retiro

            _, meta_w = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)

            motivo = f"Traslado de {moved} bolsas de maíz {target_hibrido['hibrido']} desde {target_hibrido['lugar_retiro']} a Planta Central"
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"🌽 **Traslado de Bolsas de Maíz Registrado:**\n\n"
                f"- **Híbrido:** **{target_hibrido['hibrido']}** ({target_hibrido['proveedor']}).\n"
                f"- **Bolsas retiradas y traídas a Planta:** **{moved} bolsas**.\n"
                f"- **Origen del retiro:** *{target_hibrido['lugar_retiro']}*.\n"
                f"- **Stock actual del híbrido:**\n"
                f"  • 🏭 **En Planta Central:** **{target_hibrido['en_planta_bolsas']} bolsas**.\n"
                f"  • 📍 **Por Retirar remanente:** **{target_hibrido['por_retirar_bolsas']} bolsas** en *{target_hibrido['lugar_retiro']}*.\n"
                f"  • **Total del híbrido:** {target_hibrido['total_bolsas']} bolsas.\n\n"
                f"📊 **Totales consolidados de Maíz:**\n"
                f"• Bolsas en Planta: **{tot_planta}** | Bolsas por retirar: **{tot_retiro}** | **Total: {tot_planta + tot_retiro} bolsas**."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        elif is_sowing_corn and target_hibrido:
            # Descontar bolsas usadas en siembra de en_planta
            used = min(target_hibrido["en_planta_bolsas"], bags_qty)
            target_hibrido["en_planta_bolsas"] -= used
            target_hibrido["total_bolsas"] -= used

            tot_planta = sum(h["en_planta_bolsas"] for h in hibridos)
            tot_retiro = sum(h["por_retirar_bolsas"] for h in hibridos)
            mz_dict["totales"]["bolsas_en_planta"] = tot_planta
            mz_dict["totales"]["bolsas_por_retirar"] = tot_retiro
            mz_dict["totales"]["total_general_bolsas"] = tot_planta + tot_retiro

            _, meta_w = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)

            motivo = f"Siembra de {used} bolsas de maíz {target_hibrido['hibrido']} en Lote 2 reportado por {sender_name}."
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"🚜 **Consumo de Semilla de Maíz Asentado:**\n\n"
                f"- **Híbrido utilizado:** **{target_hibrido['hibrido']}**.\n"
                f"- **Bolsas sembradas:** **{used} bolsas**.\n"
                f"- **Remanente en Planta:** **{target_hibrido['en_planta_bolsas']} bolsas**.\n"
                f"- **Bolsas pendientes por retirar:** **{target_hibrido['por_retirar_bolsas']} bolsas** en *{target_hibrido['lugar_retiro']}*.\n\n"
                f"Las planillas del establecimiento han sido actualizadas."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        else:
            # Consulta detallada de semillas de maíz por híbrido
            tot_planta = mz_dict.get("totales", {}).get("bolsas_en_planta", 240)
            tot_retiro = mz_dict.get("totales", {}).get("bolsas_por_retirar", 190)
            tot_gral = mz_dict.get("totales", {}).get("total_general_bolsas", 430)

            items_str = []
            for h in hibridos:
                items_str.append(
                    f"🌽 **{h['hibrido']}** ({h['proveedor']}):\n"
                    f"   • 🏭 **En Planta Central:** **{h['en_planta_bolsas']} bolsas** ({h['presentacion']})\n"
                    f"   • 📍 **Por Retirar:** **{h['por_retirar_bolsas']} bolsas** en *{h['lugar_retiro']}*\n"
                    f"   • Subtotal híbrido: **{h['total_bolsas']} bolsas**."
                )

            reply = (
                f"🌽 **Stock de Semillas de Maíz por Híbrido y Ubicación:**\n\n" +
                "\n\n".join(items_str) +
                f"\n\n📊 **Consolidado General de Maíz:**\n"
                f"• 🏭 **Bolsas físicas en Planta:** **{tot_planta} bolsas**\n"
                f"• 📍 **Bolsas por retirar en distribuidores:** **{tot_retiro} bolsas**\n"
                f"👉 **Total Acopiado de Maíz:** **{tot_gral} bolsas**."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 2. CASO GRANOS EN TONELADAS EN SILOS / SILOBOLSAS (SOJA Y TRIGO)
    # ==============================================================
    is_grain_silo_query_or_action = (
        any(w in msg for w in ["silobolsa", "silobolsas", "silo", "silos", "grano", "granos"]) or
        (any(w in msg for w in ["soja", "trigo"]) and any(w in msg for w in ["tonelada", "toneladas", "tn", "acopiad", "guardad", "cosechad"]))
    ) and not any(w in msg for w in ["sembr", "siembra", "sembrando"])
    if is_grain_silo_query_or_action:
        granos_raw, meta_gr = execute_native_tool("read_file", {"filename": "stock_granos_silos.json"})
        executed_tools.append(meta_gr)
        granos_json = json.loads(granos_raw)

        soja_dict = granos_json.get("soja", {})
        trigo_dict = granos_json.get("trigo", {})

        is_dispatch = any(w in msg for w in ["carg", "vend", "entreg", "despach", "sacar", "retiro"]) and any(char.isdigit() for char in user_message)

        if is_dispatch:
            tn_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:toneladas?|tn)?", msg)
            tn_qty = float(tn_match.group(1).replace(".", "").replace(",", ".")) if tn_match else 30.0

            if "trigo" in msg:
                target_crop = trigo_dict
                crop_name = "Trigo"
            else:
                target_crop = soja_dict
                crop_name = "Soja"

            target_silo = target_crop["ubicaciones"][0]
            for s in target_crop["ubicaciones"]:
                if "1" in msg and "1" in s["identificador"]:
                    target_silo = s
                    break
                elif "2" in msg and "2" in s["identificador"]:
                    target_silo = s
                    break
                elif "aéreo" in msg or "aereo" in msg or "chapa" in msg:
                    target_silo = s
                    break

            target_silo["stock_actual_tn"] = max(0.0, target_silo["stock_actual_tn"] - tn_qty)
            target_crop["total_tn"] = sum(s["stock_actual_tn"] for s in target_crop["ubicaciones"])
            granos_json["totales_generales"]["total_granos_almacenados_tn"] = soja_dict["total_tn"] + trigo_dict["total_tn"]

            _, meta_w = execute_native_tool("write_file", {"filename": "stock_granos_silos.json", "content": json.dumps(granos_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)

            motivo = f"Despacho/Venta de {tn_qty} Tn de {crop_name} desde {target_silo['identificador']} reportado por {sender_name}."
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"🌾 **Despacho de Granos Asentado:**\n\n"
                f"- **Cultivo:** **{crop_name}**.\n"
                f"- **Toneladas despachadas:** **{tn_qty:,} Tn**.\n"
                f"- **Ubicación afectada:** **{target_silo['identificador']}** (Remanente: **{target_silo['stock_actual_tn']:,} Tn**).\n\n"
                f"📊 **Totales de Granos en Silos y Silobolsas:**\n"
                f"• Soja: **{soja_dict['total_tn']:,} Tn**\n"
                f"• Trigo: **{trigo_dict['total_tn']:,} Tn**\n"
                f"👉 **Total Granos Almacenados en Campo:** **{granos_json['totales_generales']['total_granos_almacenados_tn']:,} Toneladas**."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        else:
            # Consulta general de silos y silobolsas
            soja_items = [f"  • {s['identificador']}: **{s['stock_actual_tn']:,} Tn** ({s.get('humedad_pct', 13.0)}% humedad - {s['tipo']})" for s in soja_dict.get("ubicaciones", [])]
            trigo_items = [f"  • {s['identificador']}: **{s['stock_actual_tn']:,} Tn** ({s.get('humedad_pct', 12.2)}% humedad - PH {s.get('peso_hectolitrico', 80.5)})" for s in trigo_dict.get("ubicaciones", [])]

            reply = (
                f"🌾 **Inventario de Granos en Silos y Silobolsas (Toneladas):**\n\n"
                f"**1. 🌱 Soja Comercial:** **{soja_dict['total_tn']:,} Toneladas**\n" +
                "\n".join(soja_items) +
                f"\n\n**2. 🌾 Trigo Pan Grado 1:** **{trigo_dict['total_tn']:,} Toneladas**\n" +
                "\n".join(trigo_items) +
                f"\n\n📊 **Total Granos Almacenados en el Establecimiento:** **{granos_json['totales_generales']['total_granos_almacenados_tn']:,} Toneladas**.\n\n"
                f"Todos los silobolsas y silos se encuentran bajo monitoreo de humedad y temperatura."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 3. COMBUSTIBLES (GASOIL): RETIRO / GASTO / TRANSFERENCIA
    # ==============================================================
    gasoil_raw, meta_g_read = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
    executed_tools.append(meta_g_read)
    gasoil_json = json.loads(gasoil_raw)
    deps = gasoil_json["depositos"]

    # Detectar labor de siembra combinada (insumos soja + combustible)
    has_real_bags = bool(re.search(r"(?<!silo)bolsas?", msg))
    is_sowing_soy = any(w in msg for w in ["sembr", "siembra", "sembrando"]) and any(w in msg for w in ["soja", "dm46"]) and (has_real_bags or any(w in msg for w in ["ha", "hect", "lote"])) and not is_grain_silo_query_or_action
    is_purchase = any(w in msg for w in ["llegó", "llego", "compra", "compramos", "descargaron", "descarga", "entró", "entro", "remito"]) and not any(w in msg for w in ["gaste", "gasté", "gastamos", "retire", "retiré", "saque", "saqué", "consum", "salida"])
    is_transfer = is_fuel_transfer_or_acopio(user_message)
    has_spending_verb = any(w in msg for w in ["retir", "saqu", "sacar", "saco", "gast", "consum", "us", "chup", "carg", "descont", "baj", "rest", "llev"])
    has_fuel_word = any(w in msg for w in ["litros", "lts", "lt", "gasoil", "diesel", "combustible"])
    has_numbers = any(char.isdigit() for char in user_message)

    if is_sowing_soy:
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

        gasoil_json.setdefault("salidas", []).append({
            "fecha": today_str,
            "deposito_origen": deps[tank_key]["nombre"],
            "labor": f"Siembra soja ({has_done} ha)",
            "litros": liters_out,
            "operario": sender_name
        })

        _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(w_g)

        # Descontar semillas soja
        sj_variedades = insumos.get("semillas_soja", {}).get("variedades", [])
        nuevo_stk_bolsas = 440
        if sj_variedades:
            sj_variedades[0]["en_planta_bolsas"] = max(0, sj_variedades[0].get("en_planta_bolsas", 440) - bolsas_out)
            sj_variedades[0]["total_bolsas"] = sj_variedades[0]["en_planta_bolsas"]
            nuevo_stk_bolsas = sj_variedades[0]["en_planta_bolsas"]
            insumos["semillas_soja"]["totales"] = {"bolsas_en_planta": nuevo_stk_bolsas, "bolsas_por_retirar": 0, "total_general_bolsas": nuevo_stk_bolsas}

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
            f"- **Stock remanente de semillas soja:** **{nuevo_stk_bolsas} bolsas** en galpón.\n"
            f"- **Combustible descontado:** **{int(liters_out):,} Litros** desde **{deps[tank_key]['nombre']}** (Remanente: **{int(deps[tank_key]['stock_actual_litros']):,} L**).\n"
            f"- **Stock total físico en campo:** **{int(gasoil_json['totales']['stock_fisico_campo_litros']):,} Litros**.\n\n"
            f"Los registros de insumos, combustible y lote han sido actualizados."
        )

    elif is_purchase:
        liters_in = extract_liters(user_message, default=5000.0)

        if "acopio" in msg:
            deps["acopio_por_retirar"]["litros_disponibles"] += liters_in
            descrip = f"Compra de {int(liters_in):,} L sumados a la cuenta de Gasoil por Retirar en YPF Directo"
        else:
            target_dep = "cisterna_planta"
            deps[target_dep]["stock_actual_litros"] = min(
                deps[target_dep]["capacidad_max_litros"],
                deps[target_dep]["stock_actual_litros"] + liters_in
            )
            descrip = f"Descarga de {int(liters_in):,} L en Cisterna Planta (remito asentado)"

        gasoil_json["totales"]["stock_fisico_campo_litros"] = (
            deps["cisterna_planta"]["stock_actual_litros"] +
            deps["tanque_grande"]["stock_actual_litros"] +
            deps["tanque_chico"]["stock_actual_litros"]
        )
        gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
            gasoil_json["totales"]["stock_fisico_campo_litros"] +
            deps["acopio_por_retirar"]["litros_disponibles"]
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

    elif is_transfer:
        liters_to_move = extract_liters(user_message, default=2000.0)

        if "acopio" in msg:
            destino_key = "tanque_chico" if "chico" in msg else ("tanque_grande" if "grande" in msg else "cisterna_planta")
            actual_acopio = deps["acopio_por_retirar"]["litros_disponibles"]
            liters_moved = min(actual_acopio, liters_to_move)

            deps["acopio_por_retirar"]["litros_disponibles"] -= liters_moved
            deps[destino_key]["stock_actual_litros"] = min(
                deps[destino_key]["capacidad_max_litros"],
                deps[destino_key]["stock_actual_litros"] + liters_moved
            )
            motivo = f"Retiro de {int(liters_moved):,} L de acopio YPF hacia {deps[destino_key]['nombre']}"
        else:
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

            liters_moved = min(deps[origen_key]["stock_actual_litros"], liters_to_move)
            deps[origen_key]["stock_actual_litros"] -= liters_moved
            deps[destino_key]["stock_actual_litros"] = min(
                deps[destino_key]["capacidad_max_litros"],
                deps[destino_key]["stock_actual_litros"] + liters_moved
            )
            motivo = f"Transferencia interna de {int(liters_moved):,} L desde {deps[origen_key]['nombre']} hacia {deps[destino_key]['nombre']}"

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

    elif has_spending_verb or (has_fuel_word and has_numbers) or ("tanque" in msg and has_numbers):
        liters_out = extract_liters(user_message, default=300.0)
        tank_key = identify_tank(user_message)

        if tank_key == "acopio_por_retirar":
            target_field = "cisterna_planta"
            liters_moved = min(deps["acopio_por_retirar"]["litros_disponibles"], liters_out)
            deps["acopio_por_retirar"]["litros_disponibles"] -= liters_moved
            deps[target_field]["stock_actual_litros"] = min(
                deps[target_field]["capacidad_max_litros"],
                deps[target_field]["stock_actual_litros"] + liters_moved
            )
            motivo = f"Retiro de {int(liters_moved):,} L de acopio YPF ingresados a Cisterna Planta"
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
                f"📦 **Retiro de Acopio Asentado:**\n\n"
                f"- **Operación:** {motivo}.\n"
                f"- **Saldo remanente en Acopio YPF:** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} Litros**.\n"
                f"- **Cisterna Planta actualizada:** **{int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L**.\n\n"
                f"**Total físico en campo:** {int(gasoil_json['totales']['stock_fisico_campo_litros']):,} L."
            )
        else:
            current_tank_stock = deps[tank_key]["stock_actual_litros"]
            deps[tank_key]["stock_actual_litros"] = max(0.0, current_tank_stock - liters_out)

            gasoil_json["totales"]["stock_fisico_campo_litros"] = (
                deps["cisterna_planta"]["stock_actual_litros"] +
                deps["tanque_grande"]["stock_actual_litros"] +
                deps["tanque_chico"]["stock_actual_litros"]
            )
            gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
                gasoil_json["totales"]["stock_fisico_campo_litros"] +
                deps["acopio_por_retirar"]["litros_disponibles"]
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
                "deposito_origen": deps[tank_key]["nombre"],
                "maquinaria": machinery,
                "litros": liters_out,
                "operario": sender_name
            })

            _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
            executed_tools.append(w_g)

            entry_mem = f"Consumo/Retiro de {int(liters_out):,} L desde {deps[tank_key]['nombre']} ({machinery}) reportado por {sender_name}."
            _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
            executed_tools.append(w_m)

            pct_filled = round((deps[tank_key]["stock_actual_litros"] / deps[tank_key]["capacidad_max_litros"]) * 100)

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

    elif any(w in msg for w in ["gasoil", "gas oil", "combustible", "tanque", "cisterna", "acopio", "saldo", "cuanto", "cuánto"]) and ("combustible" in msg or "gasoil" in msg or "tanque" in msg or "cisterna" in msg):
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
            f"- **Total disponible con acopio:** **{int(tot_gral):,} Litros**."
        )

    elif any(w in msg for w in ["rinde", "rendimiento", "cosecha", "trilla", "qq", "kilos"]):
        _, meta = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.append(meta)

        reply = (
            f"🌾 **Rendimientos y Datos de Cosecha (Campaña 2026/2027):**\n\n"
            f"- **Lote 1 (Soja 1ra - 120 ha):** En siembra activa. Rinde proyectado: 3.800 kg/ha (38 qq/ha).\n"
            f"- **Lote 2 (Maíz Tardío - 85 ha):** En barbecho. Rinde objetivo: 9.500 kg/ha (95 qq/ha).\n"
            f"- **Lote 3 (Trigo Cosechado - 210 ha):** Total: 819.000 kg (**3.900 kg/ha / 39 qq/ha**), almacenado en silobolsa norte y silo planta.\n\n"
            f"Datos consolidados en los registros de lotes."
        )

    elif any(w in msg for w in ["fertilizante", "quimico", "químico", "glifosato", "map", "urea", "galpon", "galpón"]):
        summary = get_dashboard_summary()
        reply = (
            f"🌱 **Inventario de Agroquímicos y Fertilizantes en Galpón:**\n\n"
            f"- **Fertilizante MAP:** {summary['map_tn']} toneladas a granel.\n"
            f"- **Glifosato Concentrado:** {summary['glifosato_lts']} litros en bidones.\n"
            f"- **Semilla de Soja DM 46R18:** {summary['semillas_soja']} bolsas en galpón.\n"
            f"- **Semilla de Maíz Total:** {summary['semillas_maiz']} bolsas acopiadas (en planta y por retirar).\n\n"
            f"Insumos disponibles para abastecimiento de labores."
        )

    else:
        summary = get_dashboard_summary()
        reply = (
            f"🚜 **IA Desk Agro - Copiloto de Operaciones:**\n\n"
            f"He verificado los inventarios del establecimiento:\n"
            f"- **Combustible:** {summary['total_campo']:,} L en campo | {summary['total_con_acopio']:,} L con acopio YPF.\n"
            f"- **Maíz por Híbrido:** {summary['maiz_totales']['en_planta']} bolsas en Planta | {summary['maiz_totales']['por_retirar']} bolsas por retirar ({summary['semillas_maiz']} total).\n"
            f"- **Granos en Silos/Silobolsas:** {summary['granos_silos']['soja']['total_tn']:,} Tn de Soja | {summary['granos_silos']['trigo']['total_tn']:,} Tn de Trigo.\n\n"
            f"¿Qué labor, movimiento de bolsas o grano deseas consultar o registrar?"
        )

    append_to_history(user_message, reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "is_demo": True,
        "stock_data": get_dashboard_summary()
    }
