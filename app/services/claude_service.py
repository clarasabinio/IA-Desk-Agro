import requests
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from django.conf import settings
import anthropic

from .campo_service import normalizar_texto
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
        "description": "Lee el contenido íntegro de un archivo en files_storage/ ('stock_gasoil.json', 'stock_insumos.json', 'stock_granos_silos.json', 'registro_lotes.json', 'registro_campos.json', 'INDEX.md', 'MEMORY.md').",
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


OPENROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"]
        }
    }
    for t in CLAUDE_TOOLS
]

def load_system_prompt() -> str:
    prompt_path = settings.BASE_DIR / "app" / "prompts" / "system_prompt.txt"
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            base_prompt = f.read()
    else:
        base_prompt = "Eres IA Desk Agro, copiloto de operaciones rurales."

    try:
        from .campo_service import obtener_campos_con_lotes, normalizar_texto
        campos = obtener_campos_con_lotes()
        if campos:
            base_prompt += "\n\n=======================================================\n"
            base_prompt += "CAMPOS Y ESTABLECIMIENTOS ACTIVOS EN IA DESK AGRO (SINCRONIZADOS EN VIVO):\n"
            base_prompt += "=======================================================\n"
            base_prompt += "El usuario tiene cargados los siguientes campos en el sistema. Si consulta por cualquiera de ellos o por sus lotes (por ejemplo 'Establecimiento Don Lorenzo', 'Campo Don Alfredo', 'Campo La Paulina', etc.), debes responder CON EXACTITUD basándote en estos datos reales cargados:\n"
            for c in campos:
                c_nom = c.get('nombre', 'Campo')
                c_ha = c.get('superficie_ha', '-')
                c_ubi = c.get('ubicacion', '-')
                c_sec = c.get('sector', '-')
                c_tit = c.get('titular', '-')
                c_ten = c.get('tenencia', '-')
                c_gps = c.get('coordenadas_gps', '-')
                c_cult = c.get('cultivos_campana', '-')
                c_lotes = c.get('lotes', [])
                c_diag = c.get('diagrama_url', '')
                c_diag_nom = c.get('diagrama_nombre', f'Plano de {c_nom}')
                l_str = "; ".join(c_lotes) if c_lotes else "Sin lotes"
                base_prompt += f"\n- **{c_nom}** (ID: {c.get('id', '-')})\n"
                base_prompt += f"  • Superficie: {c_ha} ha | Ubicación: {c_ubi} (Sector: {c_sec})\n"
                base_prompt += f"  • Titular: {c_tit} | Tenencia: {c_ten} | GPS: {c_gps}\n"
                base_prompt += f"  • Cultivos: {c_cult}\n"
                base_prompt += f"  • Lotes: {l_str}\n"
                if c_diag:
                    base_prompt += f"  • Diagrama / Cartografía: ![{c_diag_nom}]({c_diag})\n"
    except Exception as e:
        print(f"Error appending dynamic campos to system prompt: {e}")

    return base_prompt

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

        # Fertilizantes en Kilogramos (kg) con desglose en galpón y por retirar
        summary["fertilizantes"] = ins.get("fertilizantes", [])
        summary["fertilizantes_totales"] = ins.get("fertilizantes_totales", {
            "en_galpon_kg": 29600.0,
            "por_retirar_kg": 20000.0,
            "total_general_kg": 49600.0
        })

        # Insumos / Fitosanitarios con dos opciones: en galpón o a retirar
        summary["fitosanitarios"] = ins.get("fitosanitarios", [])
        summary["fitosanitarios_totales"] = ins.get("fitosanitarios_totales", {
            "en_galpon_litros": 1190.0,
            "a_retirar_litros": 620.0,
            "total_general_litros": 1810.0
        })

        for f in ins.get("fertilizantes", []):
            if "MAP" in f.get("nombre", ""):
                summary["map_tn"] = round(f.get("total_kg", 22000.0) / 1000.0, 1)
        for f in ins.get("fitosanitarios", []):
            if "Glifosato" in f.get("nombre", ""):
                summary["glifosato_lts"] = f.get("total", 1200)
    except Exception as e:
        print(f"Error parsing stock_insumos.json: {e}")

    # 3. Granos en Silos de Guardado y Acopio (Toneladas)
    try:
        gr = json.loads(read_file("stock_granos_silos.json"))
        principales = gr.get("silos_principales", [])
        trilla = gr.get("silos_trilla", [])

        stock_princ = sum(s.get("stock_actual_tn", 0) for s in principales)
        cap_princ = sum(s.get("capacidad_max_tn", 0) for s in principales)
        stock_trilla = sum(s.get("stock_actual_tn", 0) for s in trilla)
        cap_trilla = sum(s.get("capacidad_max_tn", 0) for s in trilla)
        tot_stock = stock_princ + stock_trilla
        tot_cap = cap_princ + cap_trilla

        summary["granos_silos"] = {
            "silos_principales": principales,
            "silos_trilla": trilla,
            "stock_principales_tn": round(stock_princ, 1),
            "capacidad_principales_tn": round(cap_princ, 1),
            "stock_trilla_tn": round(stock_trilla, 1),
            "capacidad_trilla_tn": round(cap_trilla, 1),
            "total_general_tn": round(tot_stock, 1),
            "capacidad_total_tn": round(tot_cap, 1),
            "soja": gr.get("soja", {"total_tn": round(sum(s.get("stock_actual_tn", 0) for s in principales + trilla if s.get("cultivo") == "Soja"), 1)}),
            "trigo": gr.get("trigo", {"total_tn": round(sum(s.get("stock_actual_tn", 0) for s in principales + trilla if s.get("cultivo") == "Trigo"), 1)}),
        }
    except Exception as e:
        print(f"Error parsing stock_granos_silos.json: {e}")

    return summary

def extract_liters(msg: str, default: float = 300.0) -> float:
    """Extrae la cantidad de litros gastados/movidos con tolerancia a cualquier redacción"""
    m = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt\b|l\b)", msg, re.IGNORECASE)
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

    tokens = re.findall(r"\b\d+(?:[\.,]\d+)?\b", msg)
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
    if any(w in msg_low for w in ["acopio", "acpio", "ypf", "distribuidor", "por retirar", "saldo"]):
        return "acopio_por_retirar"
    return "tanque_grande"

def identify_destination_tank(msg: str, default: str = "cisterna_planta") -> str:
    """
    Identifica el tanque físico DESTINO para un movimiento o retiro de combustible.
    Nunca devuelve 'acopio_por_retirar' como destino.
    """
    msg_low = msg.lower()
    if any(w in msg_low for w in ["chico", "chiquito", "pequeño", "pequeno", "carretón", "carreton", "3000", "3.000", "3k", "auxilio"]):
        return "tanque_chico"
    if any(w in msg_low for w in ["grande", "5000", "5.000", "5k", "móvil", "movil", "cisterna móvil", "cisterna movil"]):
        return "tanque_grande"
    if any(w in msg_low for w in ["planta", "central", "22000", "22.000", "22k", "tanque fijo", "cisterna"]):
        return "cisterna_planta"
    return default

def is_fuel_transfer_or_acopio(msg: str) -> bool:
    """
    Detecta si el mensaje es un retiro desde acopio externo hacia tanques o una transferencia entre tanques.
    """
    msg_low = msg.lower()

    # 1. Retiro desde Acopio Externo / YPF hacia depósitos del campo
    has_acopio = any(w in msg_low for w in ["acopio", "acpio", "acoppio", "ypf", "distribuidor", "externo", "exteno", "por retirar"])
    has_move_action = any(w in msg_low for w in [
        "retir", "saqu", "sacar", "saco", "traer", "traje", "trajo", "trajimos",
        "pas", "carg", "llev", "guard", "mov", "traslad", "descarg", "poner", "puse"
    ])
    has_fuel_or_tank = any(w in msg_low for w in [
        "gasoil", "gas oil", "diesel", "combustible", "combustibles", "litros", "lts", "lt", "tanque", "cisterna"
    ])
    if has_acopio and has_move_action and has_fuel_or_tank:
        return True

    # 2. Transferencias internas explícitas entre tanques
    if any(w in msg_low for w in ["pasar", "pasé", "pase", "transferir", "transferí", "mover", "moví", "trasladar", "trasladé"]):
        return True

    tanks_mentioned = []
    if any(w in msg_low for w in ["chico", "3000"]):
        tanks_mentioned.append("tanque_chico")
    if any(w in msg_low for w in ["grande", "5000"]):
        tanks_mentioned.append("tanque_grande")
    if any(w in msg_low for w in ["cisterna", "planta", "22000"]):
        tanks_mentioned.append("cisterna_planta")
    if len(tanks_mentioned) >= 2 and any(p in msg_low for p in [" a ", " al ", " hacia ", " para el tanque", " y "]):
        return True

    return False


def _call_openrouter_agent(user_message: str, is_whatsapp: bool, sender_name: str, prompt_input: str, system_prompt: str, executed_tools_log: list) -> Dict[str, Any]:
    api_key = getattr(settings, "OPENROUTER_API_KEY", "")
    model = getattr(settings, "OPENROUTER_MODEL", "anthropic/claude-sonnet-5.5")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "IA Desk Agro",
        "Content-Type": "application/json"
    }

    history = get_sliding_history(limit=6)
    messages_payload: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt}
    ]

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

        payload = {
            "model": model,
            "max_tokens": 600,
            "messages": messages_payload,
            "tools": OPENROUTER_TOOLS
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        if resp.status_code != 200:
            err_data = resp.json() if resp.text else {}
            err_msg = err_data.get("error", {}).get("message", resp.text)
            raise RuntimeError(f"OpenRouter Error ({resp.status_code}): {err_msg}")

        res_data = resp.json()
        choice = res_data.get("choices", [{}])[0]
        choice_msg = choice.get("message", {})

        if choice.get("finish_reason") == "tool_calls" or choice_msg.get("tool_calls"):
            messages_payload.append(choice_msg)

            for tc in choice_msg.get("tool_calls", []):
                t_fn = tc.get("function", {})
                t_name = t_fn.get("name", "")
                t_args_raw = t_fn.get("arguments", "{}")
                try:
                    t_args = json.loads(t_args_raw) if isinstance(t_args_raw, str) else t_args_raw
                except Exception:
                    t_args = {}

                t_output, t_meta = execute_native_tool(t_name, t_args)
                executed_tools_log.append(t_meta)

                messages_payload.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "name": t_name,
                    "content": t_output
                })

        else:
            final_text = choice_msg.get("content", "")
            break

    if not final_text:
        final_text = "Se completaron las labores solicitadas en los registros del campo."

    final_text = re.sub(
        r"stock_gasoil\.json|stock_insumos\.json|stock_granos_silos\.json|registro_lotes\.json|registro_campos\.json|INDEX\.md|MEMORY\.md|files_storage/?",
        "los registros del campo",
        final_text
    )
    append_to_history(user_message, final_text, executed_tools_log)

    return {
        "response": final_text,
        "tool_calls": executed_tools_log,
        "is_demo": False,
        "provider": f"OpenRouter ({model})",
        "stock_data": get_dashboard_summary()
    }


WHATSAPP_RESTRICTION_REPLY = (
    "🔒 **Acción Restringida por WhatsApp • IA Desk Agro**\n\n"
    "Por motivos de seguridad y control operativo, la **creación, modificación estructural o eliminación de campos y parcelas** está habilitada exclusivamente desde el **panel web de IA Desk Agro** por el usuario administrador.\n\n"
    "📱 **Desde este canal de WhatsApp puedes:**\n"
    "• 🚜 **Cargar labores agrícolas:** registrar siembras, pasadas de implementos (disco, rastra), fertilizaciones, pulverizaciones y cosechas.\n"
    "• ⛽ **Registrar consumos:** reportar cargas y descargas de gasoil por tanque, o uso de semillas y fertilizantes.\n"
    "• 📊 **Consultar todo:** preguntar por saldos de combustible, stock de insumos, silos, superficies y datos de lotes existentes."
)

def is_prohibited_whatsapp_admin_action(raw_msg: str) -> bool:
    """
    Evalúa si un mensaje recibido por WhatsApp intenta realizar acciones
    administrativas restringidas (alta, modificación estructural o borrado de campos/lotes).
    WhatsApp solo permite:
    1. Cargar labores agrícolas (siembra, trilla, pulverización, fertilización, implementos)
    2. Cargar consumos (combustible/gasoil, semillas, fertilizantes, gastos)
    3. Consultar todo (saldos de tanques, insumos, silos, datos de campos y lotes)
    Cualquier creación o modificación estructural de campos/lotes debe hacerse desde la web.
    """
    msg = normalizar_texto(raw_msg)
    
    # 1. Si es claramente una consulta o pregunta sobre datos existentes -> PERMITIR ("consultar todo")
    is_query = any(msg.startswith(q) for q in [
        "que ", "como ", "cual ", "cuales ", "cuanto ", "cuantos ", "donde ", 
        "quien ", "info ", "datos ", "mostrar ", "mostrame ", "resumen ", "listar ",
        "consultar ", "ver "
    ]) or any(q in msg for q in [
        "cuales son", "que campos", "cuantos campos", "que lotes", "cuanto gasoil",
        "cuanto queda", "que stock", "info de", "datos de", "consultar", "mostrame",
        "ver campo", "ver lote", "ver parcela", "quien es el titular", "superficie tiene"
    ]) or raw_msg.strip().endswith("?")

    if is_query:
        return False

    # 2. Labores a campo y consumos (SIEMPRE PERMITIDOS por WhatsApp)
    labor_regex = re.compile(
        r'\b(sembr|siembra|cosech|trilla|trill|rastra|disco|fertiliz|pulveriz|fumig|aplic|barbecho|picado|cincel|rolo|descompactador|labor|labores|trabajo|pasada)\w*\b'
    )
    consumption_regex = re.compile(
        r'\b(gasoil|combustible|diesel|tanque|tanques|litro|litros|lts|bolsa|bolsas|kg|kilos|tonelada|toneladas|tn|urea|map|dap|fitosanitario|fitosanitarios|glifosato|insumo|insumos)\b'
    )
    
    has_labor = bool(labor_regex.search(msg))
    has_consumption = bool(consumption_regex.search(msg))

    # Si el mensaje es una labor o consumo de combustible/insumo:
    if has_labor or has_consumption:
        # Excepción estricta: solo si explícitamente pide crear/modificar/borrar la estructura de un campo/lote
        admin_explicit = any(p in msg for p in [
            "crear campo", "agregar campo", "nuevo campo", "alta de campo", "dar de alta campo",
            "registrar campo", "incorporar campo", "modificar campo", "editar campo", "eliminar campo",
            "borrar campo", "cambiar titular", "cambiar nombre del campo"
        ])
        if not admin_explicit:
            return False

    # 3. Detección de creación / alta de campo o lote
    wants_create_field = any(phrase in msg for phrase in [
        "crear campo", "agregar campo", "nuevo campo", "alta campo", "alta de campo",
        "dar de alta campo", "registrar campo", "incorporar campo", "sumar campo",
        "crear lote", "agregar lote", "nuevo lote", "crear parcela", "nueva parcela",
        "agregar parcela", "dar de alta lote", "registrar lote", "anotar campo",
        "cargar nuevo campo", "cargar campo"
    ]) or (
        any(v in msg for v in ["crear", "agregar", "dar de alta", "registrar", "incorporar"])
        and any(n in msg for n in ["campo", "establecimiento", "lote", "parcela"])
    )

    # 4. Detección de modificación / edición / borrado de campo o lote
    wants_modify_field = any(phrase in msg for phrase in [
        "modificar campo", "editar campo", "cambiar campo", "actualizar campo",
        "eliminar campo", "borrar campo", "quitar campo", "dar de baja campo",
        "modificar lote", "editar lote", "cambiar lote", "eliminar lote", "borrar lote",
        "cambiar hectareas", "cambiar superficie", "modificar hectareas",
        "modificar superficie", "cambiar titular", "editar titular",
        "cambiar nombre del campo", "renombrar campo", "modificar limites",
        "cambiar coordenadas", "editar parcela", "modificar parcela", "actualizar parcela"
    ]) or (
        any(v in msg for v in ["modificar", "editar", "cambiar", "actualizar", "eliminar", "borrar", "quitar"])
        and any(n in msg for n in ["campo", "establecimiento", "lote", "parcela", "hectareas", "superficie", "titular", "propietario"])
    )

    return bool(wants_create_field or wants_modify_field)


PENDING_PROPOSAL_FILE = "pending_labor_proposal.json"

def save_pending_labor_proposal(proposal: Dict[str, Any]) -> None:
    path = settings.BASE_DIR / "files_storage" / PENDING_PROPOSAL_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2, ensure_ascii=False)

def get_pending_labor_proposal() -> Optional[Dict[str, Any]]:
    path = settings.BASE_DIR / "files_storage" / PENDING_PROPOSAL_FILE
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def clear_pending_labor_proposal() -> None:
    path = settings.BASE_DIR / "files_storage" / PENDING_PROPOSAL_FILE
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

def is_affirmative_confirmation(raw_msg: str) -> bool:
    clean = re.sub(r'[^a-z0-9]+', ' ', normalizar_texto(raw_msg)).strip()
    affirmatives = [
        "si", "si confirmo", "confirmar", "confirmo", "confirmado", "confirmada",
        "dale", "ok", "correcto", "asentar", "dale nomas", "proceder",
        "de acuerdo", "afirmativo", "si dale", "si confirmar", "si por favor",
        "confirmar labor", "si por favor confirmar", "esta bien", "perfecto"
    ]
    if clean in affirmatives:
        return True
    return any(clean.startswith(a) for a in ["si ", "confirmar ", "confirmo "])

def is_cancel_message(raw_msg: str) -> bool:
    clean = re.sub(r'[^a-z0-9]+', ' ', normalizar_texto(raw_msg)).strip()
    cancels = [
        "no", "cancelar", "cancela", "cancelado", "no confirmar", "anular", "anula",
        "rechazar", "no registrar", "borrar", "incorrecto"
    ]
    if clean in cancels:
        return True
    return any(clean.startswith(c) for c in ["no ", "cancelar "])

def is_pure_fuel_movement(raw_msg: str) -> bool:
    clean = normalizar_texto(raw_msg)
    
    # 1. Si es pregunta o consulta -> NO es movimiento
    if clean.strip().endswith("?") or any(clean.startswith(q) for q in ["cuanto", "cuanto ", "que ", "mostrar ", "saldo"]):
        return False

    # 2. Si explícitamente se especifica un lote o una labor agronómica a campo -> NO es solo combustible
    has_explicit_lot = any(w in clean for w in [
        "lote 1", "lote 2", "lote 3", "lote 4", "lote 5", "lote 6", "lote 7", "lote 8", "lote 9",
        "lote-01", "lote-02", "lote-03", "lote-04", "lote-05", "lote-06", "lote-07", "lote-08",
        "en el lote", "al lote", "del lote", "parcela 1", "parcela 2", "parcela"
    ])
    
    labor_verbs_only = [
        "sembr", "siembra", "cosech", "trilla", "fumig", "pulveriz", "fertiliz",
        "voleo", "barbecho", "rastra", "disco", "cincel", "arado", "rolar", "picado", "descompactador"
    ]
    clean_no_machinery = clean.replace("sembradora", "maquina").replace("cosechadora", "maquina").replace("pulverizadora", "maquina")
    has_agri_field_labor = any(w in clean_no_machinery for w in labor_verbs_only)

    if has_explicit_lot or has_agri_field_labor:
        return False

    has_fuel_word = any(w in clean for w in [
        "gasoil", "gas oil", "combustible", "combustibles", "diesel",
        "cisterna", "tanque chico", "tanque grande", "acopio"
    ]) or (any(w in clean for w in ["tanque", "litro", "litros", "lts"]) and not any(w in clean for w in ["silo", "silobolsa"]))
    
    if not has_fuel_word:
        return False

    is_fuel_verb = any(w in clean for w in [
        "retir", "retiro", "retiramos", "retire", "sacamos", "saque", "saqué",
        "descargamos", "descargue", "descargué", "pasamos", "pase", "pasé",
        "transferir", "transferimos", "traslado", "trasladamos",
        "cargamos", "cargue", "cargué", "cargar", "llenamos",
        "consumo", "consumimos", "gastamos", "gasto", "gaste", "gasté", "eche", "eché", "echamos"
    ])

    return bool(is_fuel_verb)

def _execute_confirmed_labor(prop: Dict[str, Any], sender_name: str, executed_tools: list) -> Dict[str, Any]:
    from .agronomic_engine import calculate_seed_consumption, calculate_fertilizer_consumption
    today_str = datetime.now().strftime("%Y-%m-%d")
    campo_nombre = prop.get("campo_nombre", "Establecimiento Don Lorenzo")
    campo_display = prop.get("campo_display", campo_nombre)
    lote_id = prop.get("lote_id", "Lote 1")
    lote_display = prop.get("lote_display", lote_id)
    crop_key = prop.get("crop_key", "trigo")
    crop_name = prop.get("crop_name", "Trigo Pan")
    crop_icon = prop.get("crop_icon", "🌾")
    has_done = float(prop.get("has_done", 20.0))
    labor_nombre = prop.get("labor_nombre", "Siembra")
    maquinaria = prop.get("maquinaria", "Tractor John Deere")
    tank_key = prop.get("tank_key", "tanque_chico")
    liters_spent = float(prop.get("liters_spent", 250.0))
    sender_name = prop.get("sender_name", sender_name)

    # 1. Combustible: Leer stock_gasoil.json y descontar
    gasoil_raw, meta_g = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
    executed_tools.append(meta_g)
    gasoil_json = json.loads(gasoil_raw)
    deps = gasoil_json["depositos"]

    saldo_actual_dep = float(deps[tank_key].get("stock_actual_litros", 0))
    saldo_est = max(0.0, saldo_actual_dep - liters_spent)
    deps[tank_key]["stock_actual_litros"] = saldo_est
    gasoil_json["totales"]["stock_fisico_campo_litros"] = sum(
        float(v.get("stock_actual_litros", 0)) for k, v in deps.items() if k != "acopio_por_retirar"
    )
    gasoil_json["totales"]["total_disponible_litros"] = (
        gasoil_json["totales"]["stock_fisico_campo_litros"] +
        float(deps.get("acopio_por_retirar", {}).get("litros_disponibles", 0))
    )
    gasoil_json.setdefault("salidas", []).append({
        "fecha": today_str,
        "deposito_origen": deps[tank_key]["nombre"],
        "lote": lote_display,
        "campo": campo_display,
        "labor": f"{labor_nombre} ({has_done} ha)",
        "litros": liters_spent,
        "maquinaria": maquinaria,
        "operario": sender_name
    })
    _, meta_gw = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
    executed_tools.append(meta_gw)

    # 2. Django ORM: Registrar salida
    from .stock_service import StockIntegrityService
    from app.models import Lote
    target_lote_obj = Lote.objects.filter(nombre__icontains=lote_id.replace("Lote", "").strip()).first() or Lote.objects.first()

    try:
        StockIntegrityService.registrar_salida_combustible(
            litros=liters_spent,
            deposito_codigo=tank_key,
            lote=target_lote_obj,
            labor=f"{labor_nombre} en {lote_display} ({has_done} ha)",
            maquinaria=maquinaria,
            operario=sender_name,
            observaciones=f"Labor confirmada en {campo_display}"
        )
    except Exception as ex_stock:
        logger.warning(f"Aviso StockIntegrityService: {ex_stock}")

    # 3. Insumos: Descontar semillas / fertilizantes / fitosanitarios
    insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
    executed_tools.append(meta_i)
    insumos_json = json.loads(insumos_raw)

    detalles_insumos = []
    semilla_str = prop.get("semilla_str", "-")
    fert_str = prop.get("fert_str", "-")
    fito_str = prop.get("fito_str", "-")
    rinde_str = prop.get("rinde_str", "-")

    # Descuento de semillas si fue siembra
    bags_qty = prop.get("bags_qty")
    if bags_qty:
        if crop_key == "maiz":
            hibridos = insumos_json.get("semillas_maiz", {}).get("hibridos", [])
            target_h = next((h for h in hibridos if h.get("en_planta_bolsas", 0) >= bags_qty), (hibridos[0] if hibridos else None))
            if target_h:
                target_h["en_planta_bolsas"] = max(0, target_h.get("en_planta_bolsas", 0) - bags_qty)
                target_h["total_bolsas"] = target_h["en_planta_bolsas"] + target_h.get("por_retirar_bolsas", 0)
                insumos_json["semillas_maiz"]["totales"]["total_general_bolsas"] = sum(h["total_bolsas"] for h in hibridos)
                insumos_json["semillas_maiz"]["totales"]["bolsas_en_planta"] = sum(h["en_planta_bolsas"] for h in hibridos)
                semilla_str = f"{target_h.get('hibrido', 'Maíz')} ({bags_qty} bolsas)"
                detalles_insumos.append(f"🌱 Semilla: {bags_qty} bolsas de {target_h.get('hibrido', 'Maíz')} (Restante: {target_h['en_planta_bolsas']} bolsas)")
        elif "trigo" in crop_key:
            var_trigo = insumos_json.get("semillas_trigo", {}).get("variedades", [])
            if var_trigo:
                target_trigo = var_trigo[0]
                target_trigo["en_planta_bolsas"] = max(0, target_trigo.get("en_planta_bolsas", 0) - bags_qty)
                target_trigo["total_bolsas"] = target_trigo["en_planta_bolsas"] + target_trigo.get("por_retirar_bolsas", 0)
                tot_trigo_p = sum(v.get("en_planta_bolsas", 0) for v in var_trigo)
                insumos_json.setdefault("semillas_trigo", {}).setdefault("totales", {})
                insumos_json["semillas_trigo"]["totales"]["bolsas_en_planta"] = tot_trigo_p
                insumos_json["semillas_trigo"]["totales"]["total_general_bolsas"] = tot_trigo_p + insumos_json["semillas_trigo"]["totales"].get("bolsas_por_retirar", 0)
                semilla_str = f"{target_trigo.get('variedad', 'Trigo Pan')} ({bags_qty} bolsas)"
                detalles_insumos.append(f"🌱 Semilla: {bags_qty} bolsas de {target_trigo.get('variedad', 'Trigo Pan')} (Restante: {target_trigo['en_planta_bolsas']} bolsas)")
        elif "soja" in crop_key:
            var_soja = insumos_json.get("semillas_soja", {}).get("variedades", [])
            if var_soja:
                var_soja[0]["en_planta_bolsas"] = max(0, var_soja[0].get("en_planta_bolsas", 0) - bags_qty)
                var_soja[0]["total_bolsas"] = var_soja[0]["en_planta_bolsas"]
                insumos_json["semillas_soja"]["totales"] = {"bolsas_en_planta": var_soja[0]["en_planta_bolsas"], "bolsas_por_retirar": 0, "total_general_bolsas": var_soja[0]["en_planta_bolsas"]}
                semilla_str = f"{var_soja[0].get('variedad', 'DM 46R18')} ({bags_qty} bolsas)"
                detalles_insumos.append(f"🌱 Semilla: {bags_qty} bolsas de {var_soja[0].get('variedad', 'DM 46R18')} (Restante: {var_soja[0]['en_planta_bolsas']} bolsas)")

    # Descuento de fertilizante si aplica
    kg_spent = prop.get("fert_kg")
    fert_type = prop.get("fert_type")
    if kg_spent and fert_type:
        ferts = insumos_json.get("fertilizantes", [])
        target_f = ferts[0]
        if "urea" in fert_type:
            target_f = next((f for f in ferts if "Urea" in f["nombre"]), ferts[1] if len(ferts) > 1 else ferts[0])
        elif "micro" in fert_type:
            target_f = next((f for f in ferts if "Micro" in f["nombre"]), ferts[2] if len(ferts) > 2 else ferts[0])
        target_f["en_galpon_kg"] = max(0.0, float(target_f.get("en_galpon_kg", 0.0)) - kg_spent)
        target_f["total_kg"] = target_f["en_galpon_kg"] + target_f.get("por_retirar_kg", 0)
        insumos_json["fertilizantes_totales"]["en_galpon_kg"] = sum(f["en_galpon_kg"] for f in ferts)
        insumos_json["fertilizantes_totales"]["total_general_kg"] = sum(f["total_kg"] for f in ferts)
        fert_str = f"{target_f['nombre']} ({int(kg_spent):,} kg)"
        detalles_insumos.append(f"🧪 Fertilizante: {int(kg_spent):,} kg de {target_f['nombre']} (Restante: {int(target_f['en_galpon_kg']):,} kg)")

    # Descuento de fitosanitarios si aplica
    litros_fito = prop.get("fito_litros")
    fito_name = prop.get("fito_name")
    if litros_fito and fito_name:
        fitos = insumos_json.get("fitosanitarios", [])
        fito_match = next((f for f in fitos if fito_name.lower() in f.get("nombre", "").lower()), fitos[0] if fitos else None)
        if fito_match:
            fito_match["en_galpon"] = max(0.0, float(fito_match.get("en_galpon", 0.0)) - litros_fito)
            fito_match["total"] = fito_match["en_galpon"] + float(fito_match.get("a_retirar", 0.0))
            insumos_json.setdefault("fitosanitarios_totales", {})
            insumos_json["fitosanitarios_totales"]["en_galpon_litros"] = sum(float(f.get("en_galpon", 0)) for f in fitos)
            insumos_json["fitosanitarios_totales"]["total_general_litros"] = sum(float(f.get("total", 0)) for f in fitos)
            fito_str = f"{fito_match['nombre']} ({int(litros_fito)} L)"
            detalles_insumos.append(f"🛡️ Fitosanitario: {int(litros_fito)} L de {fito_match['nombre']} (Restante: {int(fito_match['en_galpon'])} L)")

    _, w_i = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
    executed_tools.append(w_i)

    # 4. Registrar en Lote y Regenerar Hoja de Cálculo del Cultivo
    from .crop_sheets_service import append_labor_to_crop
    labor_registro = {
        "fecha": today_str,
        "lote": lote_display,
        "superficie_ha": has_done,
        "labor": labor_nombre,
        "maquinaria": maquinaria,
        "operario": sender_name,
        "combustible_litros": liters_spent,
        "deposito_combustible": deps[tank_key]["nombre"],
        "semilla": semilla_str,
        "fertilizante": fert_str,
        "insumos": fito_str,
        "rinde": rinde_str,
        "observaciones": f"Labor confirmada en {campo_display}"
    }
    append_labor_to_crop(crop_key, campo_nombre, lote_id, labor_registro)

    # 5. Memoria de negocio
    memo_entry = f"Labor confirmada {labor_nombre} en {campo_display} ({lote_display} - {crop_name}): {has_done} ha, -{int(liters_spent)} L {deps[tank_key]['nombre']}"
    if semilla_str != "-":
        memo_entry += f", semilla: {semilla_str}"
    if fert_str != "-":
        memo_entry += f", fert: {fert_str}"
    if fito_str != "-":
        memo_entry += f", fito: {fito_str}"
    _, w_m = execute_native_tool("append_memory", {"entry": memo_entry})
    executed_tools.append(w_m)

    # 6. Sincronizar automáticamente hojas de cálculo
    try:
        from .google_sheets_service import on_movement_recorded
        on_movement_recorded()
    except Exception as e_sync:
        logger.error(f"Error sincronizando hojas: {e_sync}")

    # 7. Respuesta
    pct_filled = round((deps[tank_key]["stock_actual_litros"] / deps[tank_key]["capacidad_max_litros"]) * 100)
    detalles_texto = "\n".join([f"• {d}" for d in detalles_insumos]) if detalles_insumos else "• Laboreo mecánico de suelo con implemento sin insumos químicos."
    tot_campo = gasoil_json["totales"]["stock_fisico_campo_litros"]
    tot_gral = gasoil_json["totales"]["total_disponible_litros"]

    reply = (
        f"Perfecto, ya registré lo que pediste.\n\n"
        f"{crop_icon} **Labor Confirmada y Asentada en el Campo:**\n\n"
        f"📋 **Detalle de la Operación:**\n"
        f"• **Establecimiento:** **{campo_display}**\n"
        f"• **Lote asignado:** **{lote_display}** ({has_done} hectáreas trabajadas)\n"
        f"• **Cultivo:** **{crop_name}**\n"
        f"• **Labor realizada:** **{labor_nombre}** ({maquinaria})\n"
        f"• **Operario:** *{sender_name}*\n\n"
        f"📦 **Descuento de Insumos y Combustible Aplicado:**\n"
        f"{detalles_texto}\n"
        f"• ⛽ Combustible: **{int(liters_spent):,} Litros** descontados de **{deps[tank_key]['nombre']}**\n\n"
        f"📊 **Total de combustible que queda:**\n"
        f"• 🛢️ **Saldo restante en {deps[tank_key]['nombre']}:** **{int(deps[tank_key]['stock_actual_litros']):,} Litros** ({pct_filled}% lleno)\n"
        f"• 🏭 **Cisterna Planta:** **{int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L**\n"
        f"• 🚜 **Tanque Grande:** **{int(deps['tanque_grande']['stock_actual_litros']):,} / 5.000 L**\n"
        f"• 🛢️ **Tanque Chico:** **{int(deps['tanque_chico']['stock_actual_litros']):,} / 3.000 L**\n"
        f"• 📋 **Gasoil por Retirar (Acopio YPF):** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} L**\n\n"
        f"👉 **Total físico en campo:** **{int(tot_campo):,} Litros** | **Total con acopio:** **{int(tot_gral):,} Litros**."
    )
    append_to_history(prop.get("user_message", "Labor"), reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "is_demo": True,
        "stock_data": get_dashboard_summary()
    }


# ==============================================================
# MOTOR DE CONSULTAS Y RESPUESTA A CONSULTAS MÚLTIPLES (WHATSAPP & WEB)
# ==============================================================

def get_specific_tanks(msg: str) -> list:
    """Identifica si el usuario preguntó por un depósito de combustible específico"""
    clean = normalizar_texto(msg)
    if any(w in clean for w in ["todos", "cada tanque", "los tanques", "general", "total", "totales"]):
        return []

    has_chico = any(w in clean for w in ["tanque chico", "tanque chiquito", "chico", "chiquito", "carreton", "carretón", "3000", "3.000", "auxilio"])
    has_grande = any(w in clean for w in ["tanque grande", "5000", "5.000", "tanque movil", "tanque móvil", "movil grande"]) and not has_chico
    has_cisterna = any(w in clean for w in ["cisterna", "planta central", "22000", "22.000", "cisterna planta"]) and not (has_chico or has_grande)
    has_acopio = any(w in clean for w in ["acopio ypf", "ypf directo", "por retirar", "acopio", "saldo en ypf", "gasoil en ypf"]) and not (has_chico or has_grande or has_cisterna)

    specs = []
    if has_chico: specs.append("tanque_chico")
    if has_grande: specs.append("tanque_grande")
    if has_cisterna: specs.append("cisterna_planta")
    if has_acopio: specs.append("acopio_por_retirar")
    return specs

def format_single_tank(tank_key: str, deps: dict) -> str:
    """Formatea la respuesta exclusiva para un tanque de combustible particular"""
    if tank_key == "tanque_chico":
        tc = deps["tanque_chico"]
        pct = round(tc["stock_actual_litros"] / tc["capacidad_max_litros"] * 100)
        return (
            f"🛢️ **Tanque Chico (Móvil 3.000 L):**\n\n"
            f"• **Saldo disponible actual:** **{int(tc['stock_actual_litros']):,} / {tc['capacidad_max_litros']:,} Litros** ({pct}% lleno).\n"
            f"• **Ubicación operativa:** Carretón móvil de auxilio rápido en lotes."
        )
    elif tank_key == "tanque_grande":
        tg = deps["tanque_grande"]
        pct = round(tg["stock_actual_litros"] / tg["capacidad_max_litros"] * 100)
        return (
            f"🚜 **Tanque Grande (Móvil 5.000 L):**\n\n"
            f"• **Saldo disponible actual:** **{int(tg['stock_actual_litros']):,} / {tg['capacidad_max_litros']:,} Litros** ({pct}% lleno).\n"
            f"• **Ubicación operativa:** Tanque móvil para abastecimiento de maquinaria pesada en laboreo."
        )
    elif tank_key == "cisterna_planta":
        cp = deps["cisterna_planta"]
        pct = round(cp["stock_actual_litros"] / cp["capacidad_max_litros"] * 100)
        return (
            f"🏭 **Cisterna Planta (Capacidad 22.000 L):**\n\n"
            f"• **Saldo disponible actual:** **{int(cp['stock_actual_litros']):,} / {cp['capacidad_max_litros']:,} Litros** ({pct}% lleno).\n"
            f"• **Ubicación operativa:** Depósito nodriza en Planta Central del establecimiento."
        )
    elif tank_key == "acopio_por_retirar":
        ac = deps["acopio_por_retirar"]
        return (
            f"📋 **Gasoil por Retirar (Acopio YPF Directo):**\n\n"
            f"• **Saldo disponible para retirar:** **{int(ac['litros_disponibles']):,} Litros**.\n"
            f"• **Distribuidor:** YPF Directo - Junín (pendiente de flete a tanques del campo)."
        )
    return ""

def identify_specific_seed(msg: str):
    """Detecta si el usuario preguntó por un híbrido o cultivo de semilla específico"""
    clean = normalizar_texto(msg)
    if any(w in clean for w in ["dekalb", "dk 72", "dk72", "72-10", "7210", "dk"]):
        return "dekalb"
    if any(w in clean for w in ["pioneer", "p2089", "p 2089", "2089", "leptra"]):
        return "pioneer"
    if any(w in clean for w in ["nidera", "ax 7784", "ax7784", "7784", "vip3", "viptera"]):
        return "nidera"
    if any(w in clean for w in ["soja", "dm 46", "dm46", "don mario", "46r18"]):
        return "soja"
    if any(w in clean for w in ["trigo", "fina", "ms inta", "ms 119", "ms119", "klein"]):
        return "trigo"
    if any(w in clean for w in ["maiz", "maíz"]):
        return "maiz_general"
    return None

def identify_specific_fert(msg: str):
    """Detecta si el usuario preguntó por un fertilizante específico"""
    clean = normalizar_texto(msg)
    if any(w in clean for w in ["urea", "nitrogeno"]):
        return "urea"
    if any(w in clean for w in ["map", "monoamonico", "monoamónico", "11-52", "fosfato"]):
        return "map"
    if any(w in clean for w in ["micro", "microessentials", "micro essentials"]):
        return "microessentials"
    return None

def identify_specific_fito(msg: str):
    """Detecta si el usuario preguntó por un fitosanitario específico"""
    clean = normalizar_texto(msg)
    if any(w in clean for w in ["glifosato", "roundup", "glifo"]):
        return "glifosato"
    if any(w in clean for w in ["2,4-d", "2 4 d", "2,4 d", "2.4 d", "enlist", "colex"]):
        return "2,4-d"
    if any(w in clean for w in ["coadyuvante", "siliconado", "antideriva", "corrector hidrico", "corrector hídrico"]):
        return "coadyuvante"
    if any(w in clean for w in ["coragen", "clorantraniliprol"]):
        return "coragen"
    return None

def identify_specific_silo_or_crop(msg: str):
    """Detecta si el usuario preguntó por un silo o cereal específico"""
    clean = normalizar_texto(msg)
    if "soja" in clean: return ("crop", "soja")
    if "trigo" in clean: return ("crop", "trigo")
    if "maiz" in clean or "maíz" in clean: return ("crop", "maiz")
    if "silo 1" in clean: return ("silo", "Silo Principal 1")
    if "silo 2" in clean: return ("silo", "Silo Principal 2")
    if "silo 3" in clean: return ("silo", "Silo Principal 3")
    if "silo 4" in clean: return ("silo", "Silo Principal 4")
    if "silo 5" in clean: return ("silo", "Silo Principal 5")
    if "trilla 1" in clean or "silo 1 de trilla" in clean: return ("silo", "Silo 1 de Trilla")
    if "trilla 2" in clean or "silo 2 de trilla" in clean: return ("silo", "Silo 2 de Trilla")
    if "trilla" in clean: return ("silo_group", "trilla")
    return None

def _build_combustible_query_reply(msg: str, executed_tools: list) -> str:
    gasoil_raw, meta_g = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
    executed_tools.append(meta_g)
    gasoil_json = json.loads(gasoil_raw)
    deps = gasoil_json["depositos"]

    spec_tanks = get_specific_tanks(msg)
    if len(spec_tanks) == 1:
        return format_single_tank(spec_tanks[0], deps)
    elif 1 < len(spec_tanks) < 4:
        sub_items = [format_single_tank(t, deps) for t in spec_tanks]
        return "\n\n".join(sub_items)

    cp = deps["cisterna_planta"]
    tg = deps["tanque_grande"]
    tc = deps["tanque_chico"]
    ac = deps["acopio_por_retirar"]
    tot_campo = gasoil_json["totales"]["stock_fisico_campo_litros"]
    tot_gral = gasoil_json["totales"]["stock_total_con_acopio_litros"]

    return (
        f"⛽ **Estado de Combustibles (4 Depósitos y Acopio):**\n\n"
        f"1. 🏭 **Cisterna Planta:** **{int(cp['stock_actual_litros']):,} / {cp['capacidad_max_litros']:,} Litros** ({round(cp['stock_actual_litros']/cp['capacidad_max_litros']*100)}% lleno).\n"
        f"2. 🚜 **Tanque Grande:** **{int(tg['stock_actual_litros']):,} / {tg['capacidad_max_litros']:,} Litros** ({round(tg['stock_actual_litros']/tg['capacidad_max_litros']*100)}% lleno).\n"
        f"3. 🛢️ **Tanque Chico:** **{int(tc['stock_actual_litros']):,} / {tc['capacidad_max_litros']:,} Litros** ({round(tc['stock_actual_litros']/tc['capacidad_max_litros']*100)}% lleno).\n"
        f"4. 📋 **Gasoil por Retirar (Acopio YPF):** **{int(ac['litros_disponibles']):,} Litros** disponibles.\n\n"
        f"📊 **Totales:**\n"
        f"- **Stock físico en el campo:** **{int(tot_campo):,} Litros** (Capacidad máxima combinada: 30.000 L).\n"
        f"- **Total disponible con acopio:** **{int(tot_gral):,} Litros**."
    )

def _build_campo_query_reply(campo_obj: dict, msg: str, executed_tools: list) -> str:
    from .campo_service import generar_respuesta_campo
    _, meta_c = execute_native_tool("read_file", {"filename": "registro_campos.json"})
    executed_tools.append(meta_c)
    clean = normalizar_texto(msg)
    is_diag = any(w in clean for w in ["diagrama", "plano", "mapa", "cartografia", "foto", "imagen", "croquis", "gis"]) and not any(w in clean for w in ["cuantas ha", "cuantas hectareas", "superficie", "datos", "ficha"])
    return generar_respuesta_campo(campo_obj, is_diag_only=is_diag, query_prompt=msg)

def _build_campos_general_query_reply(msg: str, executed_tools: list) -> str:
    from .campo_service import obtener_campos_con_lotes, generar_resumen_todos_los_campos
    campos = obtener_campos_con_lotes()
    _, meta_c = execute_native_tool("read_file", {"filename": "registro_campos.json"})
    executed_tools.append(meta_c)
    clean = normalizar_texto(msg)
    is_diag = any(w in clean for w in ["diagrama", "plano", "mapa", "cartografia", "foto", "imagen", "croquis", "gis"])
    return generar_resumen_todos_los_campos(campos, show_diagrams=is_diag)

def _build_lote_query_reply(lote_obj_or_list, msg: str, executed_tools: list, matched_field: dict = None) -> str:
    _, meta_l = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
    executed_tools.append(meta_l)

    if isinstance(lote_obj_or_list, list):
        if len(lote_obj_or_list) == 1:
            target_lote = lote_obj_or_list[0]
        else:
            reply = "🌱 **Lotes encontrados con esa numeración en tus establecimientos:**\n\n"
            for l in lote_obj_or_list:
                ln = l.get("nombre", "Lote")
                lc = l.get("campo", "Campo")
                lh = l.get("superficie_ha", "-")
                lcult = l.get("cultivo", "-")
                lvar = l.get("variedad") or l.get("hibridos_plantados") or ""
                reply += f"• **{ln}** ({lc}): **{lh} ha** • Cultivo: *{lcult}* ({lvar})\n"
            return reply
    else:
        target_lote = lote_obj_or_list

    l_nom = target_lote.get("nombre", "Lote")
    l_campo = target_lote.get("campo", "Campo")
    l_sup = target_lote.get("superficie_ha", "-")
    l_cult = target_lote.get("cultivo", "-")
    l_hib = target_lote.get("hibridos_plantados") or target_lote.get("variedad") or "Sin híbrido especificado"
    l_estado = target_lote.get("estado_actual", "En seguimiento agronómico activo")
    l_diag_url = target_lote.get("diagrama_url", "")
    l_diag_nom = target_lote.get("diagrama_nombre") or f"Diagrama agronómico de {l_nom}"

    reply = (
        f"🌱 **Información Agronómica - {l_nom}:**\n\n"
        f"• 🌾 **Híbridos / Variedades:** **{l_hib}**\n"
        f"• 🚜 **Cultivo y Superficie:** {l_cult} ({l_sup} hectáreas)\n"
        f"• 📍 **Establecimiento:** {l_campo}\n"
        f"• 📋 **Estado actual:** {l_estado}\n"
    )
    if l_diag_url:
        reply += f"\n🗺️ **Diagrama / Cartografía:**\n![{l_diag_nom}]({l_diag_url})\n"
    return reply

def _build_silos_query_reply(msg: str, executed_tools: list) -> str:
    granos_raw, meta_gr = execute_native_tool("read_file", {"filename": "stock_granos_silos.json"})
    executed_tools.append(meta_gr)
    granos_json = json.loads(granos_raw)
    principales = granos_json.get("silos_principales", [])
    trilla = granos_json.get("silos_trilla", [])
    all_silos = principales + trilla

    spec_silo = identify_specific_silo_or_crop(msg)
    if spec_silo:
        stype, sval = spec_silo
        if stype == "crop":
            c_silos = [s for s in all_silos if sval in normalizar_texto(s.get("cultivo", ""))]
            if c_silos:
                c_stock = sum(s.get("stock_actual_tn", 0) for s in c_silos)
                c_cap = sum(s.get("capacidad_max_tn", 0) for s in c_silos)
                items = [f"• **{s['nombre']}:** **{s['stock_actual_tn']:,} Tn** ({s.get('humedad_pct', 13.0)}% hum. - Capacidad: {s['capacidad_max_tn']:,} Tn)" for s in c_silos]
                return (
                    f"🌾 **Acopio de {sval.capitalize()} en Silos:**\n\n" +
                    "\n".join(items) +
                    f"\n\n👉 **Total acopiado de {sval.capitalize()}:** **{c_stock:,.1f} Tn** sobre **{c_cap:,.0f} Tn** de capacidad."
                )
        elif stype == "silo":
            target = next((s for s in all_silos if normalizar_texto(sval) in normalizar_texto(s["nombre"])), None)
            if target:
                return (
                    f"🌾 **Estado de {target['nombre']}:**\n\n"
                    f"• **Grano acopiado:** {target.get('cultivo', 'Grano')}\n"
                    f"• **Stock actual:** **{target['stock_actual_tn']:,} Tn** / {target['capacidad_max_tn']:,} Tn ({round(target['stock_actual_tn']/target['capacidad_max_tn']*100)}% lleno).\n"
                    f"• **Calidad:** Humedad: {target.get('humedad_pct', 13.0)}% | Merma comercial: {target.get('merma_pct', 1.0)}%."
                )
        elif stype == "silo_group" and sval == "trilla":
            t_stock = sum(s.get("stock_actual_tn", 0) for s in trilla)
            t_cap = sum(s.get("capacidad_max_tn", 0) for s in trilla)
            items = [f"• **{s['nombre']}:** **{s['stock_actual_tn']:,} Tn** ({s.get('cultivo', 'Grano')} - {s.get('humedad_pct', 12.0)}% hum.)" for s in trilla]
            return (
                f"🚜 **Silos de Acopio para Trilla (2 unidades):**\n\n" +
                "\n".join(items) +
                f"\n\n👉 **Subtotal Silos de Trilla:** **{t_stock:,.1f} Tn** almacenadas / **{t_cap:,.0f} Tn** capacidad máx."
            )

    p_items = [f"  • **{s['nombre']}:** **{s['stock_actual_tn']:,} Tn** ({s.get('cultivo', 'Grano')} - {s.get('humedad_pct', 13.0)}% hum.)" for s in principales]
    t_items = [f"  • **{s['nombre']}:** **{s['stock_actual_tn']:,} Tn** ({s.get('cultivo', 'Grano')} - {s.get('humedad_pct', 12.0)}% hum.)" for s in trilla]

    tot_p_stock = sum(s.get("stock_actual_tn", 0) for s in principales)
    tot_p_cap = sum(s.get("capacidad_max_tn", 0) for s in principales)
    tot_t_stock = sum(s.get("stock_actual_tn", 0) for s in trilla)
    tot_t_cap = sum(s.get("capacidad_max_tn", 0) for s in trilla)
    tot_gen_stock = tot_p_stock + tot_t_stock
    tot_gen_cap = tot_p_cap + tot_t_cap

    return (
        f"🌾 **Estado y Capacidad de Silos de Guardado y Acopio (Toneladas):**\n\n"
        f"**1. 🏗️ Silos Principales (5 unidades):**\n" +
        "\n".join(p_items) +
        f"\n  👉 *Subtotal Silos Principales:* **{tot_p_stock:,.1f} Tn** almacenadas / **{tot_p_cap:,.0f} Tn** capacidad máx.\n\n"
        f"**2. 🚜 Silos de Acopio para Trilla (2 unidades adicionales):**\n" +
        "\n".join(t_items) +
        f"\n  👉 *Subtotal Silos de Trilla:* **{tot_t_stock:,.1f} Tn** almacenadas / **{tot_t_cap:,.0f} Tn** capacidad máx.\n\n"
        f"📊 **Capacidad Total del Establecimiento:** **{tot_gen_stock:,.1f} Tn** acopiadas sobre **{tot_gen_cap:,.0f} Tn** de capacidad combinada."
    )

def _build_semillas_query_reply(msg: str, executed_tools: list) -> str:
    insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
    executed_tools.append(meta_ins)
    insumos_json = json.loads(insumos_raw)
    mz_dict = insumos_json.get("semillas_maiz", {})
    hibridos = mz_dict.get("hibridos", [])

    spec_seed = identify_specific_seed(msg)
    if spec_seed == "dekalb":
        h = next((x for x in hibridos if "DK7210" in x["id"]), hibridos[0])
        return (
            f"🌽 **Semilla de Maíz - {h['hibrido']} ({h['proveedor']}):**\n\n"
            f"• 🏠 **En Planta Central:** **{h['en_planta_bolsas']} bolsas** ({h['presentacion']})\n"
            f"• 📍 **Por Retirar en acopio:** **{h['por_retirar_bolsas']} bolsas** en *{h['lugar_retiro']}*\n"
            f"👉 **Total disponible del híbrido:** **{h['total_bolsas']} bolsas** ({h.get('tratamiento', '')})."
        )
    elif spec_seed == "pioneer":
        h = next((x for x in hibridos if "P2089" in x["id"]), hibridos[1])
        return (
            f"🌽 **Semilla de Maíz - {h['hibrido']} ({h['proveedor']}):**\n\n"
            f"• 🏠 **En Planta Central:** **{h['en_planta_bolsas']} bolsas** ({h['presentacion']})\n"
            f"• 📍 **Por Retirar en acopio:** **{h['por_retirar_bolsas']} bolsas** en *{h['lugar_retiro']}*\n"
            f"👉 **Total disponible del híbrido:** **{h['total_bolsas']} bolsas** ({h.get('tratamiento', '')})."
        )
    elif spec_seed == "nidera":
        h = next((x for x in hibridos if "AX7784" in x["id"]), hibridos[2])
        return (
            f"🌽 **Semilla de Maíz - {h['hibrido']} ({h['proveedor']}):**\n\n"
            f"• 🏠 **En Planta Central:** **{h['en_planta_bolsas']} bolsas** ({h['presentacion']})\n"
            f"• 📍 **Por Retirar en acopio:** **{h['por_retirar_bolsas']} bolsas** en *{h['lugar_retiro']}*\n"
            f"👉 **Total disponible del híbrido:** **{h['total_bolsas']} bolsas** ({h.get('tratamiento', '')})."
        )
    elif spec_seed == "soja":
        sj = insumos_json.get("semillas_soja", {})
        var = sj.get("variedades", [{}])[0]
        tot = sj.get("totales", {})
        return (
            f"🌱 **Semillas de Soja - {var.get('variedad', 'Don Mario DM 46R18')}:**\n\n"
            f"• 🏠 **En Planta / Galpón:** **{tot.get('bolsas_en_planta', 178)} bolsas** ({var.get('presentacion', 'Bolsas de 40 kg')})\n"
            f"• 📍 **Por Retirar:** **{tot.get('bolsas_por_retirar', 0)} bolsas**\n"
            f"👉 **Total disponible de Soja:** **{tot.get('total_general_bolsas', 178)} bolsas** (Galpón 1 - Planta Central - PG: {var.get('poder_germinativo_pct', 94)}%)."
        )
    elif spec_seed == "trigo":
        tr = insumos_json.get("semillas_trigo", {})
        var = tr.get("variedades", [{}])[0]
        tot = tr.get("totales", {})
        return (
            f"🌾 **Semillas de Trigo Pan - {var.get('variedad', 'Trigo Pan MS INTA 119')}:**\n\n"
            f"• 🏠 **En Planta / Galpón:** **{tot.get('bolsas_en_planta', 100)} bolsas** ({var.get('presentacion', 'Bolsas de 40 kg')})\n"
            f"• 📍 **Por Retirar:** **{tot.get('bolsas_por_retirar', 120)} bolsas** en *{var.get('lugar_retiro', 'Cooperativa Agrícola Ganadera')}*\n"
            f"👉 **Total disponible de Trigo:** **{tot.get('total_general_bolsas', 220)} bolsas**."
        )
    elif spec_seed == "maiz_general":
        tot_planta = mz_dict.get("totales", {}).get("bolsas_en_planta", sum(h.get("en_planta_bolsas", 0) for h in hibridos))
        tot_retirar = mz_dict.get("totales", {}).get("bolsas_por_retirar", sum(h.get("por_retirar_bolsas", 0) for h in hibridos))
        tot_gral = mz_dict.get("totales", {}).get("total_general_bolsas", sum(h.get("total_bolsas", 0) for h in hibridos))
        h_items = []
        for h in hibridos:
            h_items.append(
                f"   • **{h['hibrido']}** ({h.get('proveedor', 'Semillero')} - {h.get('variedad', '')}):\n"
                f"     - 🏠 En Planta/Galpón: **{h.get('en_planta_bolsas', 0)} bolsas**\n"
                f"     - 📍 Por Retirar: **{h.get('por_retirar_bolsas', 0)} bolsas** en *{h.get('lugar_retiro', 'Acopio')}*\n"
                f"     - Subtotal híbrido: **{h.get('total_bolsas', 0)} bolsas**"
            )
        return (
            f"🌽 **Inventario de Semillas de Maíz por Híbrido (80.000 semillas/bolsa):**\n\n" +
            "\n".join(h_items) +
            f"\n\n📊 **Totales Consolidados de Maíz:**\n"
            f"• **Físico en Planta (Galpón):** **{tot_planta} bolsas**\n"
            f"• **Pendiente de Retiro en Acopio:** **{tot_retirar} bolsas**\n"
            f"👉 **Total General Disponible:** **{tot_gral} bolsas**."
        )

    # General (todas las semillas)
    tot_planta = mz_dict.get("totales", {}).get("bolsas_en_planta", sum(h.get("en_planta_bolsas", 0) for h in hibridos))
    tot_retirar = mz_dict.get("totales", {}).get("bolsas_por_retirar", sum(h.get("por_retirar_bolsas", 0) for h in hibridos))
    tot_gral = mz_dict.get("totales", {}).get("total_general_bolsas", sum(h.get("total_bolsas", 0) for h in hibridos))
    h_items = []
    for h in hibridos:
        h_items.append(
            f"   • **{h['hibrido']}** ({h.get('proveedor', 'Semillero')} - {h.get('variedad', '')}):\n"
            f"     - 🏠 En Planta/Galpón: **{h.get('en_planta_bolsas', 0)} bolsas**\n"
            f"     - 📍 Por Retirar: **{h.get('por_retirar_bolsas', 0)} bolsas** en *{h.get('lugar_retiro', 'Acopio')}*\n"
            f"     - Subtotal híbrido: **{h.get('total_bolsas', 0)} bolsas**"
        )
    sj_tot = insumos_json.get("semillas_soja", {}).get("totales", {}).get("total_general_bolsas", 178)
    tr_tot = insumos_json.get("semillas_trigo", {}).get("totales", {}).get("total_general_bolsas", 220)

    return (
        f"🌱 **Inventario General de Semillas:**\n\n"
        f"🌽 **Híbridos de Maíz (Bolsas de 80.000 semillas):**\n" +
        "\n".join(h_items) +
        f"\n  👉 *Subtotal Maíz:* **{tot_gral} bolsas** (Planta: {tot_planta} | Acopio: {tot_retirar})\n\n"
        f"🌱 **Semillas de Soja (Bolsas 40 kg):** **{sj_tot} bolsas** de DM 46R18 en galpón.\n"
        f"🌾 **Semillas de Trigo Pan (Bolsas 40 kg):** **{tr_tot} bolsas** de MS INTA 119."
    )

def _build_fertilizantes_query_reply(msg: str, executed_tools: list) -> str:
    insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
    executed_tools.append(meta_ins)
    insumos_json = json.loads(insumos_raw)
    ferts = insumos_json.get("fertilizantes", [])

    spec_fert = identify_specific_fert(msg)
    if spec_fert == "urea":
        f = next((x for x in ferts if "Urea" in x["nombre"]), ferts[1])
        return (
            f"🧪 **Fertilizante - {f['nombre']} ({f['formula']}):**\n\n"
            f"• 🏠 **En Galpón:** **{int(f['en_galpon_kg']):,} kg** ({round(f['en_galpon_kg']/1000.0, 1)} Tn - {f.get('ubicacion_galpon', 'Galpón 1')})\n"
            f"• 📍 **Por Retirar:** **{int(f['por_retirar_kg']):,} kg** ({round(f['por_retirar_kg']/1000.0, 1)} Tn) en *{f['lugar_retiro']}*\n"
            f"👉 **Total disponible de Urea:** **{int(f['total_kg']):,} kg** ({round(f['total_kg']/1000.0, 1)} Tn)."
        )
    elif spec_fert == "map":
        f = next((x for x in ferts if "MAP" in x["nombre"] or "Fosfato" in x["nombre"]), ferts[0])
        return (
            f"🧪 **Fertilizante - {f['nombre']} ({f['formula']}):**\n\n"
            f"• 🏠 **En Galpón:** **{int(f['en_galpon_kg']):,} kg** ({round(f['en_galpon_kg']/1000.0, 1)} Tn - {f.get('ubicacion_galpon', 'Galpón 1')})\n"
            f"• 📍 **Por Retirar:** **{int(f['por_retirar_kg']):,} kg** ({round(f['por_retirar_kg']/1000.0, 1)} Tn) en *{f['lugar_retiro']}*\n"
            f"👉 **Total disponible de MAP:** **{int(f['total_kg']):,} kg** ({round(f['total_kg']/1000.0, 1)} Tn)."
        )
    elif spec_fert == "microessentials":
        f = next((x for x in ferts if "Micro" in x["nombre"]), ferts[2])
        return (
            f"🧪 **Fertilizante - {f['nombre']} ({f['formula']}):**\n\n"
            f"• 🏠 **En Galpón:** **{int(f['en_galpon_kg']):,} kg** ({round(f['en_galpon_kg']/1000.0, 1)} Tn - {f.get('ubicacion_galpon', 'Galpón 2')})\n"
            f"• 📍 **Por Retirar:** **{int(f['por_retirar_kg']):,} kg** ({round(f['por_retirar_kg']/1000.0, 1)} Tn) en *{f['lugar_retiro']}*\n"
            f"👉 **Total disponible de MicroEssentials:** **{int(f['total_kg']):,} kg** ({round(f['total_kg']/1000.0, 1)} Tn)."
        )

    tot_g = insumos_json.get("fertilizantes_totales", {}).get("en_galpon_kg", sum(f.get("en_galpon_kg", 0) for f in ferts))
    tot_r = insumos_json.get("fertilizantes_totales", {}).get("por_retirar_kg", sum(f.get("por_retirar_kg", 0) for f in ferts))
    tot_gral = insumos_json.get("fertilizantes_totales", {}).get("total_general_kg", sum(f.get("total_kg", 0) for f in ferts))

    lines = []
    for f in ferts:
        lines.append(
            f"   • **{f['nombre']}** ({f['formula']}):\n"
            f"     - 🏠 En Galpón: **{int(f['en_galpon_kg']):,} kg** ({round(f['en_galpon_kg']/1000.0, 1)} Tn)\n"
            f"     - 📍 Por Retirar: **{int(f['por_retirar_kg']):,} kg** en *{f['lugar_retiro']}*\n"
            f"     - Subtotal: **{int(f['total_kg']):,} kg**"
        )

    return (
        f"🧪 **Stock de Fertilizantes en Galpón y Acopios:**\n\n" +
        "\n".join(lines) +
        f"\n\n📊 **Totales:**\n"
        f"- **Físico en Galpón:** **{int(tot_g):,} kg** ({round(tot_g/1000.0, 1)} Tn).\n"
        f"- **Por Retirar en Distribuidor:** **{int(tot_r):,} kg** ({round(tot_r/1000.0, 1)} Tn).\n"
        f"👉 **Total General:** **{int(tot_gral):,} kg** ({round(tot_gral/1000.0, 1)} Tn)."
    )

def _build_fitosanitarios_query_reply(msg: str, executed_tools: list) -> str:
    insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
    executed_tools.append(meta_ins)
    insumos_json = json.loads(insumos_raw)
    fitos = insumos_json.get("fitosanitarios", [])

    spec_fito = identify_specific_fito(msg)
    if spec_fito:
        f = None
        if spec_fito == "glifosato":
            f = next((x for x in fitos if "Glifosato" in x["nombre"]), fitos[0])
        elif spec_fito == "2,4-d":
            f = next((x for x in fitos if "2,4-D" in x["nombre"]), fitos[1])
        elif spec_fito == "coadyuvante":
            f = next((x for x in fitos if "Coadyuvante" in x["nombre"]), fitos[2])
        elif spec_fito == "coragen":
            f = next((x for x in fitos if "Coragen" in x["nombre"]), fitos[3])

        if f:
            return (
                f"🛡️ **Fitosanitario - {f['nombre']} ({f['tipo']}):**\n\n"
                f"• 🏠 **En Galpón:** **{int(f['en_galpon']):,} Litros**\n"
                f"• 📍 **A Retirar:** **{int(f['a_retirar']):,} Litros** en *{f['lugar_retiro']}*\n"
                f"👉 **Total disponible:** **{int(f['total']):,} Litros** ({f.get('proveedor', '')})."
            )

    tot_g = insumos_json.get("fitosanitarios_totales", {}).get("en_galpon_litros", sum(f.get("en_galpon", 0) for f in fitos))
    tot_r = insumos_json.get("fitosanitarios_totales", {}).get("a_retirar_litros", sum(f.get("a_retirar", 0) for f in fitos))
    tot_gral = insumos_json.get("fitosanitarios_totales", {}).get("total_general_litros", sum(f.get("total", 0) for f in fitos))

    lines = []
    for f in fitos:
        lines.append(
            f"   • **{f['nombre']}** ({f['tipo']}):\n"
            f"     - 🏠 En Galpón: **{int(f['en_galpon']):,} L**\n"
            f"     - 📍 A Retirar: **{int(f['a_retirar']):,} L** en *{f['proveedor']}*\n"
            f"     - Total: **{int(f['total']):,} L**"
        )

    return (
        f"🛡️ **Inventario de Fitosanitarios y Químicos:**\n\n" +
        "\n".join(lines) +
        f"\n\n📊 **Totales:**\n"
        f"- **En Galpón:** **{int(tot_g):,} Litros**.\n"
        f"- **A Retirar:** **{int(tot_r):,} Litros**.\n"
        f"👉 **Total Disponible:** **{int(tot_gral):,} Litros**."
    )

def detect_query_domains(user_message: str) -> List[Tuple[str, Any]]:
    clean = normalizar_texto(user_message)
    from .campo_service import obtener_campos_con_lotes
    campos_registrados = obtener_campos_con_lotes()

    path_lotes = settings.BASE_DIR / "files_storage" / "registro_lotes.json"
    lotes_registrados = []
    if path_lotes.exists():
        try:
            with open(path_lotes, "r", encoding="utf-8") as f:
                lotes_registrados = json.load(f).get("lotes", [])
        except Exception:
            pass

    detected = []

    # 1. Combustible
    is_comb = any(w in clean for w in [
        "gasoil", "gas oil", "combustible", "combustibles", "diesel", "gas-oil", "nafta",
        "cisterna", "tanque chico", "tanque grande", "tanques", "acopio ypf", "saldo de combustible",
        "cuanto gasoil", "cuanto combustible", "cuantos litros"
    ]) or (("tanque" in clean or "tanques" in clean) and not any(w in clean for w in ["silo", "silobolsa"]))
    if is_comb:
        detected.append(("combustible", None))

    # 2. Campos
    campos_found = []
    for c in campos_registrados:
        cn = normalizar_texto(c.get("nombre", ""))
        short_name = cn.replace("campo ", "").replace("establecimiento ", "")
        if short_name in clean or cn in clean:
            campos_found.append(c)
    for cf in campos_found:
        detected.append(("campo", cf))

    if not campos_found and any(p in clean for p in ["cuales son mis campos", "que campos tengo", "resumen de campos", "listar campos", "todos los campos", "cuantos campos tengo"]):
        detected.append(("campos_general", None))

    # 3. Lotes
    matched_lotes = []
    for l in lotes_registrados:
        ln = normalizar_texto(l.get("nombre", ""))
        m_lote = re.search(r'lote\s*([0-9a-zA-Z]+)', ln)
        if m_lote:
            l_num = m_lote.group(1)
            if re.search(r'\blote\s*' + re.escape(l_num) + r'\b', clean) or re.search(r'\bparcela\s*' + re.escape(l_num) + r'\b', clean):
                if campos_found:
                    c_noms = [normalizar_texto(cf.get("nombre", "")) for cf in campos_found]
                    if not any(cn in normalizar_texto(l.get("campo", "")) for cn in c_noms):
                        continue
                if l["id"] not in [x.get("id") for x in matched_lotes]:
                    matched_lotes.append(l)

    if matched_lotes:
        nums = set()
        for ml in matched_lotes:
            m_lote = re.search(r'lote\s*([0-9a-zA-Z]+)', normalizar_texto(ml.get("nombre", "")))
            num = m_lote.group(1) if m_lote else ml["id"]
            if num not in nums:
                nums.add(num)
                sub_group = [x for x in matched_lotes if re.search(r'lote\s*' + re.escape(num) + r'\b', normalizar_texto(x.get("nombre", "")))]
                detected.append(("lote", sub_group))

    # 4. Silos
    is_silos = any(w in clean for w in [
        "silo", "silos", "silobolsa", "silobolsas", "cereal", "cereales", "grano", "granos"
    ]) or ("acopio" in clean and not any(w in clean for w in ["ypf", "gasoil", "combustible", "fertilizante", "urea", "map", "insumo"])) or \
       (any(w in clean for w in ["tonelada", "toneladas", "tn"]) and any(w in clean for w in ["guardad", "acopiad", "cosecha", "cosechad", "trigo", "soja", "maiz"]))
    if is_silos:
        detected.append(("silos", None))

    # 5. Semillas
    is_semillas = any(w in clean for w in [
        "semilla", "semillas", "hibrido", "hibridos", "dk72", "dk 72", "dekalb", "pioneer", "p2089", "nidera", "ax7784", "ax 7784"
    ]) or (any(w in clean for w in ["bolsa", "bolsas"]) and any(w in clean for w in ["maiz", "soja", "trigo", "semilla"]))
    if is_semillas:
        detected.append(("semillas", None))

    # 6. Fertilizantes
    is_fert = any(w in clean for w in [
        "fertilizante", "fertilizantes", "urea", "map", "microessentials", "micro essentials", "fosfato", "nitrogeno"
    ])
    if is_fert:
        detected.append(("fertilizantes", None))

    # 7. Fitosanitarios
    is_fito = any(w in clean for w in [
        "fitosanitario", "fitosanitarios", "insumo", "insumos", "glifosato", "2,4-d", "2 4 d", "enlist", "coadyuvante", "coragen", "herbicida", "agroquimico"
    ])
    if is_fito:
        detected.append(("fitosanitarios", None))

    # Ordenar dominios por la posición en que aparecen en el mensaje
    def get_pos(d):
        dom, data = d
        if dom == "campo":
            cn = normalizar_texto(data.get("nombre", ""))
            short_name = cn.replace("campo ", "").replace("establecimiento ", "")
            p = clean.find(short_name)
            return p if p != -1 else clean.find(cn)
        elif dom == "combustible":
            for kw in ["gasoil", "gas oil", "combustible", "diesel", "tanque", "cisterna", "acopio"]:
                p = clean.find(kw)
                if p != -1: return p
        elif dom == "semillas":
            for kw in ["semilla", "semillas", "maiz", "hibrido", "bolsa"]:
                p = clean.find(kw)
                if p != -1: return p
        elif dom == "silos":
            for kw in ["silo", "silos", "cereal", "grano", "trilla"]:
                p = clean.find(kw)
                if p != -1: return p
        elif dom == "lote":
            p = clean.find("lote")
            return p if p != -1 else clean.find("parcela")
        elif dom == "fertilizantes":
            for kw in ["fertilizante", "urea", "map", "microessentials", "fosfato"]:
                p = clean.find(kw)
                if p != -1: return p
        elif dom == "fitosanitarios":
            for kw in ["fitosanitario", "insumo", "glifosato", "2,4-d", "enlist"]:
                p = clean.find(kw)
                if p != -1: return p
        return 9999

    detected.sort(key=get_pos)
    return detected

def process_multi_query(user_message: str, is_whatsapp: bool, sender_name: str, executed_tools: list) -> Optional[Dict[str, Any]]:
    detected = detect_query_domains(user_message)
    if len(detected) < 2:
        return None

    sections = []
    num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

    for idx, (dom, data) in enumerate(detected):
        prefix = f"{num_emojis[idx]} " if idx < len(num_emojis) else f"{idx+1}️⃣ "
        if dom == "combustible":
            sections.append(prefix + _build_combustible_query_reply(user_message, executed_tools))
        elif dom == "campo":
            sections.append(prefix + _build_campo_query_reply(data, user_message, executed_tools))
        elif dom == "campos_general":
            sections.append(prefix + _build_campos_general_query_reply(user_message, executed_tools))
        elif dom == "lote":
            sections.append(prefix + _build_lote_query_reply(data, user_message, executed_tools))
        elif dom == "silos":
            sections.append(prefix + _build_silos_query_reply(user_message, executed_tools))
        elif dom == "semillas":
            sections.append(prefix + _build_semillas_query_reply(user_message, executed_tools))
        elif dom == "fertilizantes":
            sections.append(prefix + _build_fertilizantes_query_reply(user_message, executed_tools))
        elif dom == "fitosanitarios":
            sections.append(prefix + _build_fitosanitarios_query_reply(user_message, executed_tools))

    if len(sections) >= 2:
        header = "📋 **Respuestas a tus consultas:**\n\n"
        divider = "\n\n" + "─" * 44 + "\n\n"
        combined_text = header + divider.join(sections)
        return {
            "response": combined_text,
            "tool_calls": executed_tools,
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    return None

def process_agro_chat(user_message: str, is_whatsapp: bool = False, sender_name: str = "Productor") -> Dict[str, Any]:
    # Control estricto de permisos WhatsApp:
    # WhatsApp SOLO permite cargar labores, consumos o consultar todo.
    # Creación y modificación estructural de campos/lotes está restringida al panel web.
    if is_whatsapp and is_prohibited_whatsapp_admin_action(user_message):
        append_to_history(user_message, WHATSAPP_RESTRICTION_REPLY, [])
        return {
            "response": WHATSAPP_RESTRICTION_REPLY,
            "tool_calls": [],
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    api_key = settings.ANTHROPIC_API_KEY
    system_prompt = load_system_prompt()
    executed_tools_log = []

    # Saludo inicial: solo saludar al usuario sin datos de combustible ni inventario
    clean_msg = user_message.lower().strip().strip("¡!¿?. ")
    is_pure_greeting = (
        clean_msg in ["hola", "buen dia", "buen día", "buenos dias", "buenos días", "buenas", "buenas tardes", "buenas noches", "saludos", "hola que tal", "hola qué tal", "que tal", "qué tal", "hola como estas", "hola cómo estás", "hola esteban"] or
        (any(clean_msg.startswith(g) for g in ["hola", "buen dia", "buen día", "buenos dias", "buenas"]) and len(clean_msg.split()) <= 3 and not any(w in clean_msg for w in ["lote", "tanque", "gasoil", "combustible", "silo", "urea", "map", "gasto", "siembra", "trilla", "retir", "cuanto", "cuánto"]))
    )
    if is_pure_greeting and not is_whatsapp:
        reply = "¡Hola! Bienvenido a **IA Desk Agro**, tu copiloto operativo.\n\n¿En qué puedo ayudarte hoy?"
        append_to_history(user_message, reply, [])
        return {
            "response": reply,
            "tool_calls": [],
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    if is_whatsapp:
        prompt_input = f"[REPORTE DE WHATSAPP DE: {sender_name}]:\n\"{user_message}\"\n\nInterpreta las labores, haz los descuentos matemáticos precisos en los depósitos de combustible, semillas por híbrido o granos en silos usando las herramientas nativas, y confirma sin nombrar archivos técnicos."
    else:
        prompt_input = user_message

    openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "")
    if openrouter_key:
        try:
            return _call_openrouter_agent(user_message, is_whatsapp, sender_name, prompt_input, system_prompt, executed_tools_log)
        except Exception as e:
            print(f"[OpenRouter API Warning]: {e}")
            sim_res = _simulate_agro_engine(user_message, is_whatsapp, sender_name)
            sim_res["warning"] = f"Aviso OpenRouter API: {str(e)}"
            return sim_res

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
    if is_whatsapp and is_prohibited_whatsapp_admin_action(user_message):
        append_to_history(user_message, WHATSAPP_RESTRICTION_REPLY, [])
        return {
            "response": WHATSAPP_RESTRICTION_REPLY,
            "tool_calls": [],
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    # Verificación prioritaria de confirmación o cancelación de labor agrícola pendiente
    pending_prop = get_pending_labor_proposal()
    if pending_prop:
        if is_cancel_message(user_message):
            clear_pending_labor_proposal()
            cancel_reply = "Entendido, he cancelado la propuesta de labor. Ningún registro ni stock fue modificado en el campo."
            append_to_history(user_message, cancel_reply, [])
            return {
                "response": cancel_reply,
                "tool_calls": [],
                "is_demo": True,
                "stock_data": get_dashboard_summary()
            }
        elif is_affirmative_confirmation(user_message):
            clear_pending_labor_proposal()
            return _execute_confirmed_labor(pending_prop, sender_name, [])

    msg = user_message.lower()
    today_str = datetime.now().strftime("%Y-%m-%d")
    executed_tools = []

    # Detección contextual prioritaria de consultas sobre combustibles
    is_fuel_context = any(w in msg for w in [
        "gasoil", "gas oil", "combustible", "combustibles", "diesel", "gas-oil", "nafta", "cisterna", "depósito", "depositos", "depósitos", "deposito"
    ]) or (("tanque" in msg or "tanques" in msg) and not any(w in msg for w in ["silo", "silobolsa"]))

    # Saludo inicial: solo saludar al usuario
    clean_msg = msg.strip().strip("¡!¿?. ")
    is_pure_greeting = (
        clean_msg in ["hola", "buen dia", "buen día", "buenos dias", "buenos días", "buenas", "buenas tardes", "buenas noches", "saludos", "hola que tal", "hola qué tal", "que tal", "qué tal", "hola como estas", "hola cómo estás", "hola esteban"] or
        (any(clean_msg.startswith(g) for g in ["hola", "buen dia", "buen día", "buenos dias", "buenas"]) and len(clean_msg.split()) <= 3 and not any(w in clean_msg for w in ["lote", "tanque", "gasoil", "combustible", "silo", "urea", "map", "gasto", "siembra", "trilla", "retir", "cuanto", "cuánto"]))
    )
    if is_pure_greeting and not is_whatsapp:
        reply = "¡Hola! Bienvenido a **IA Desk Agro**, tu copiloto operativo.\n\n¿En qué puedo ayudarte hoy?"
        append_to_history(user_message, reply, [])
        return {
            "response": reply,
            "tool_calls": [],
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    # ==============================================================
    # ==============================================================
        # ==============================================================
    # 0. REGISTRO INTEGRAL DE LABORES A CAMPO (SIEMBRA, IMPLEMENTOS, RASTRA/DISCO, FERTILIZACIÓN, PULVERIZACIÓN, TRILLA)
    # Vinculado a descuento automático de gasoil, semillas, fertilizantes, fitosanitarios,
    # registro en Lote/Campo en registro_lotes.json, Django ORM, y hojas de cálculo por cultivo.
    # ==============================================================
    from .campo_service import (
        obtener_campos_con_lotes,
        buscar_campo_en_mensaje,
        buscar_lote_en_campo,
        generar_respuesta_campo,
        generar_resumen_todos_los_campos,
        normalizar_texto
    )

    is_labor_verb = any(w in msg for w in [
        "disco", "rastra", "descompactador", "cincel", "arado", "laboreo", "labranza",
        "sembr", "siembr", "siembra", "sembrando",
        "fertiliz", "refertiliz", "fertilizando", "voleo",
        "pulveriz", "pulverizando", "fumig", "barbecho",
        "trill", "trillando", "cosech", "cosechando",
        "implemento", "pasada", "pase ", "pasé ", "pasamos",
        "hice ", "realice ", "realicé ", "efectue ", "efectué ",
        "aplique ", "apliqué ", "aplicamos", "tiramos", "tire ", "tiré ",
        "rolo", "rolar", "subsolador", "cultivador", "desmalezadora", "picado", "picar"
    ]) or ("labor" in msg and any(w in msg for w in ["hice", "hicimos", "realic", "pase", "pasé", "efectu", "registr", "carg"]))

    campos_registrados_labor = obtener_campos_con_lotes()
    matched_campo_labor = buscar_campo_en_mensaje(user_message, campos_registrados_labor)

    has_lot_or_ha = (
        matched_campo_labor is not None or
        any(w in msg for w in [
            "lote", "ha", "has", "hect", "campo", "esperanza", "ombu", "ombú", "san jose", "san josé",
            "alfredo", "paulina", "lorenzo", "parcela", "chacra"
        ])
    )

    has_spending = any(w in msg for w in [
        "gast", "us", "consum", "aplic", "carg", "tir", "met", "pasamos", "hicimos",
        "rind", "qq", "utilic", "descont", "puse", "eche", "eché", "echamos", "litros", "bolsas", "kg", "kilos", "lts"
    ])

    is_query_msg = (
        any(w in msg for w in ["?", "¿", "cuanto", "cuánto", "saldo", "listar", "ver", "stock", "estado", "mostrar", "planos", "diagrama", "foto", "mapa", "imagen"]) or
        msg.strip().startswith("que ") or msg.strip().startswith("qué ") or
        msg.strip().startswith("como ") or msg.strip().startswith("cómo ")
    )

    is_field_labor_action = (is_labor_verb and (has_lot_or_ha or has_spending)) and not is_query_msg and not is_pure_fuel_movement(user_message)

    # ==============================================================
    # DETECCIÓN Y RESOLUCIÓN DE CONSULTAS MÚLTIPLES O COMPUESTAS (WhatsApp & Web)
    # Si el usuario hace dos o más preguntas en un mismo mensaje (ej: gasoil y semillas,
    # campo y combustible, silos y lote), el copiloto responde a TODAS de forma numerada.
    # ==============================================================
    if not is_field_labor_action and not is_pure_fuel_movement(user_message):
        multi_res = process_multi_query(user_message, is_whatsapp, sender_name, executed_tools)
        if multi_res:
            append_to_history(user_message, multi_res["response"], executed_tools)
            return multi_res

    if is_field_labor_action:
        from .crop_sheets_service import append_labor_to_crop, generate_crop_workbook

        # 1. Determinar Campo y Lote
        specific_lote = None
        if matched_campo_labor:
            campo_nombre = matched_campo_labor.get("nombre", "Campo")
            campo_display = matched_campo_labor.get("nombre", "Campo")
            specific_lote = buscar_lote_en_campo(user_message, matched_campo_labor)
        else:
            if any(w in msg for w in ["ombu", "ombú"]):
                campo_nombre = "Campo El Ombú"
                campo_display = "Campo El Ombú"
            elif any(w in msg for w in ["san jose", "san josé"]):
                campo_nombre = "Campo San José"
                campo_display = "Campo San José"
            elif any(w in msg for w in ["alfredo"]):
                campo_nombre = "Campo Don Alfredo"
                campo_display = "Campo Don Alfredo"
            elif any(w in msg for w in ["paulina"]):
                campo_nombre = "Campo La Paulina"
                campo_display = "Campo La Paulina"
            elif any(w in msg for w in ["lorenzo"]):
                campo_nombre = "Establecimiento Don Lorenzo"
                campo_display = "Establecimiento Don Lorenzo"
            else:
                campo_nombre = "Campo La Esperanza"
                campo_display = "Campo La Esperanza"

            for c_reg in campos_registrados_labor:
                if c_reg.get("nombre", "").lower() in campo_nombre.lower() or campo_nombre.lower() in c_reg.get("nombre", "").lower():
                    matched_campo_labor = c_reg
                    specific_lote = buscar_lote_en_campo(user_message, matched_campo_labor)
                    break

        # Si aún no tenemos specific_lote, buscar en registro_lotes.json
        lotes_raw_all, meta_l_all = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.append(meta_l_all)
        try:
            lotes_data_all = json.loads(lotes_raw_all).get("lotes", [])
        except Exception:
            lotes_data_all = []

        if not specific_lote:
            req_l_id = "Lote 1"
            if "lote 2" in msg:
                req_l_id = "Lote 2"
            elif "lote 3" in msg:
                req_l_id = "Lote 3"
            elif "lote a" in msg or "norte a" in msg:
                req_l_id = "Lote A"
            elif "lote b" in msg or "norte b" in msg:
                req_l_id = "Lote B"

            for l_cand in lotes_data_all:
                c_cand = l_cand.get("campo", "").lower()
                n_cand = l_cand.get("nombre", "").lower()
                if (campo_nombre.lower() in c_cand or c_cand in campo_nombre.lower()) and (req_l_id.lower() in n_cand or req_l_id.lower() in l_cand.get("id", "").lower()):
                    specific_lote = l_cand
                    break

        if specific_lote:
            lote_id = specific_lote.get("nombre", "Lote 1")
            lote_display = specific_lote.get("nombre", lote_id)
            if specific_lote.get("campo"):
                campo_nombre = specific_lote.get("campo")
                campo_display = campo_nombre
        else:
            lote_id = "Lote 1"
            if "lote 2" in msg:
                lote_id = "Lote 2"
            elif "lote 3" in msg:
                lote_id = "Lote 3"
            elif "lote a" in msg:
                lote_id = "Lote A"
            elif "lote b" in msg:
                lote_id = "Lote B"
            lote_display = f"{lote_id} - {campo_display}"

        # 2. Determinar Cultivo
        lote_cultivo = (specific_lote.get("cultivo") if specific_lote else "").lower()

        if any(w in msg for w in ["maiz", "maíz", "dk", "pioneer", "nidera", "ax7784"]):
            crop_key = "maiz"
            crop_name = "Maíz"
            crop_icon = "🌽"
            sheet_name = "IA_Desk_Agro_Maiz.xlsx"
        elif any(w in msg for w in ["segunda", "2da", "rastrojo"]) or ("soja" in msg and any(w in msg for w in ["trigo", "segunda", "2da"])):
            crop_key = "soja_segunda"
            crop_name = "Soja de Segunda"
            crop_icon = "🌿"
            sheet_name = "IA_Desk_Agro_Soja_Segunda.xlsx"
        elif any(w in msg for w in ["trigo", "fina", "pan"]):
            crop_key = "trigo"
            crop_name = "Trigo Pan"
            crop_icon = "🌾"
            sheet_name = "IA_Desk_Agro_Trigo.xlsx"
        elif any(w in msg for w in ["soja", "dm46"]):
            crop_key = "soja_primera"
            crop_name = "Soja de Primera"
            crop_icon = "🌱"
            sheet_name = "IA_Desk_Agro_Soja_Primera.xlsx"
        elif "trigo" in lote_cultivo:
            crop_key = "trigo"
            crop_name = "Trigo Pan"
            crop_icon = "🌾"
            sheet_name = "IA_Desk_Agro_Trigo.xlsx"
        elif "maiz" in lote_cultivo or "maíz" in lote_cultivo:
            crop_key = "maiz"
            crop_name = "Maíz"
            crop_icon = "🌽"
            sheet_name = "IA_Desk_Agro_Maiz.xlsx"
        elif "segunda" in lote_cultivo or "2da" in lote_cultivo:
            crop_key = "soja_segunda"
            crop_name = "Soja de Segunda"
            crop_icon = "🌿"
            sheet_name = "IA_Desk_Agro_Soja_Segunda.xlsx"
        else:
            crop_key = "soja_primera"
            crop_name = "Soja de Primera"
            crop_icon = "🌱"
            sheet_name = "IA_Desk_Agro_Soja_Primera.xlsx"

        # 3. Hectáreas trabajadas
        ha_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:hect[áa]reas?|has?\b)", msg)
        if ha_match:
            has_done = float(ha_match.group(1).replace(".", "").replace(",", "."))
        elif specific_lote and specific_lote.get("superficie_ha"):
            try:
                has_done = float(str(specific_lote.get("superficie_ha")).replace("ha", "").strip())
            except Exception:
                has_done = 20.0
        else:
            has_done = 20.0

        # 4. Labor y Maquinaria
        if any(w in msg for w in ["disco", "rastra", "descompactador", "cincel", "arado", "laboreo", "implemento"]):
            labor_nombre = "Pasada de Rastra de Discos" if any(w in msg for w in ["disco", "rastra"]) else "Labor con Implemento Agrícola"
            maquinaria = "Tractor John Deere 7200R + Rastra de Discos" if "disco" in msg or "rastra" in msg else "Tractor JD 7200R + Implemento"
        elif any(w in msg for w in ["sembr", "siembra"]):
            labor_nombre = "Siembra"
            maquinaria = "Tractor JD 7200R + Sembradora Crucianelli 27 líneas"
        elif any(w in msg for w in ["fertiliz", "urea", "map", "voleo", "nitrogeno", "fosfato"]):
            labor_nombre = "Fertilización a Campo"
            maquinaria = "Fertilizadora al voleo Altina"
        elif any(w in msg for w in ["pulveriz", "fumig", "barbecho", "quimico", "herbicida"]):
            labor_nombre = "Pulverización / Barbecho Químico"
            maquinaria = "Pulverizadora Pla MAP 3 3300"
        elif any(w in msg for w in ["trill", "cosech"]):
            labor_nombre = "Trilla y Cosecha"
            maquinaria = "Cosechadora Case IH 7250 + Draper 35 pies"
        else:
            labor_nombre = "Labor Agrícola con Implemento"
            maquinaria = "Tractor John Deere 7200R + Implemento"

        # 5. Descuento de Combustible (Gasoil) calculado con norma técnica INTA CostoMaq y Open-Meteo
        from .agronomic_engine import (
            calculate_fuel_consumption,
            calculate_seed_consumption,
            calculate_fertilizer_consumption
        )

        has_explicit_liters = bool(re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt\b)", msg))
        user_liters = extract_liters(user_message, default=0.0) if has_explicit_liters else None

        fuel_calc = calculate_fuel_consumption(
            labor_type=labor_nombre,
            hectares=has_done,
            crop_key=crop_key,
            user_specified_liters=user_liters
        )
        liters_spent = fuel_calc["litros_finales"]
        maquinaria = fuel_calc.get("maquinaria", maquinaria)
        tank_key = identify_tank(user_message)
        if tank_key == "acopio_por_retirar":
            tank_key = "tanque_grande"

        gasoil_raw, meta_g = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
        executed_tools.append(meta_g)
        gasoil_json = json.loads(gasoil_raw)
        deps = gasoil_json["depositos"]

        saldo_actual_dep = float(deps[tank_key].get("stock_actual_litros", 0))
        if liters_spent > saldo_actual_dep:
            reply = (
                f"❌ **No es posible registrar la labor porque no hay stock suficiente de combustible.**\n\n"
                f"- **Depósito:** **{deps[tank_key]['nombre']}**\n"
                f"- **Stock disponible actual:** **{int(saldo_actual_dep):,} Litros**\n"
                f"- **Gasoil requerido para la labor:** **{int(liters_spent):,} Litros** ({labor_nombre} en {lote_display})\n\n"
                f"⚠️ *Por favor recarga combustible en el depósito o transfiere desde otro tanque antes de asentar esta labor.*"
            )
            append_to_history(user_message, reply, executed_tools)
            return {
                "response": reply,
                "tool_calls": executed_tools,
                "is_demo": True,
                "stock_data": get_dashboard_summary()
            }

        # DOBLE VERIFICACIÓN EXCLUSIVA PARA WHATSAPP:
        # Se solicita confirmación explícita del campo y la labor para evitar cualquier malinterpretación operativa.
        if is_whatsapp:
            insumos_prev = []
            parsed_bags = None
            if "siembr" in labor_nombre.lower() or any(w in msg for w in ["semill", "bolsa", "bolsas"]):
                bags_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa\b)", msg)
                user_bags = int(float(bags_match.group(1).replace(".", "").replace(",", "."))) if bags_match else None
                seed_calc = calculate_seed_consumption(crop_key, has_done, user_specified_bags=user_bags)
                parsed_bags = seed_calc["bolsas_finales"]
                insumos_prev.append(f"{parsed_bags} bolsas de semilla {crop_name}")

            parsed_kg = None
            parsed_fert_type = None
            if any(w in msg for w in ["fertiliz", "map", "urea", "microessentials", "fosfato", "nitrogeno"]):
                kg_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:kg|kilos?|kilogramos?)", msg)
                user_kg = float(kg_match.group(1).replace(".", "").replace(",", ".")) if kg_match else None
                parsed_fert_type = "urea" if "urea" in msg else ("microessentials" if "micro" in msg else "map")
                fert_calc = calculate_fertilizer_consumption(parsed_fert_type, has_done, user_specified_kg=user_kg)
                parsed_kg = fert_calc["kg_finales"]
                insumos_prev.append(f"{int(parsed_kg):,} kg de fertilizante ({parsed_fert_type.upper()})")

            parsed_fito_lits = None
            parsed_fito_name = None
            if any(w in msg for w in ["pulveriz", "fumig", "barbecho", "glifosato", "2,4-d", "enlist", "coadyuvante", "coragen"]):
                parsed_fito_name = "Glifosato" if "glifosato" in msg else ("2,4-D" if "2,4-d" in msg else "Fitosanitario")
                litros_fito_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt\b)", msg)
                parsed_fito_lits = float(litros_fito_match.group(1).replace(".", "").replace(",", ".")) if litros_fito_match else round(has_done * 2.5, 1)
                insumos_prev.append(f"{int(parsed_fito_lits)} L de fitosanitario ({parsed_fito_name})")

            insumos_str_disp = ", ".join(insumos_prev) if insumos_prev else "Laboreo mecánico de suelo sin insumos químicos"

            import uuid
            prop_token = uuid.uuid4().hex[:8]
            proposal_data = {
                "idempotency_token": prop_token,
                "action_type": "labor_agricola",
                "campo_nombre": campo_nombre,
                "campo_display": campo_display,
                "lote_id": lote_id,
                "lote_display": lote_display,
                "crop_key": crop_key,
                "crop_name": crop_name,
                "crop_icon": crop_icon,
                "has_done": has_done,
                "labor_nombre": labor_nombre,
                "maquinaria": maquinaria,
                "tank_key": tank_key,
                "liters_spent": liters_spent,
                "sender_name": sender_name,
                "user_message": user_message,
                "bags_qty": parsed_bags,
                "fert_kg": parsed_kg,
                "fert_type": parsed_fert_type,
                "fito_litros": parsed_fito_lits,
                "fito_name": parsed_fito_name,
                "semilla_str": f"{crop_name} ({parsed_bags} bolsas)" if parsed_bags else "-",
                "fert_str": f"{parsed_fert_type} ({int(parsed_kg)} kg)" if parsed_kg else "-",
                "fito_str": f"{parsed_fito_name} ({int(parsed_fito_lits)} L)" if parsed_fito_lits else "-"
            }
            save_pending_labor_proposal(proposal_data)

            double_verif_reply = (
                f"⚠️ **Doble Verificación de Labor Agrícola • IA Desk Agro**\n\n"
                f"Para asegurar que no haya malinterpretaciones operativas en los registros, por favor confirma el campo y la labor antes de asentarla:\n\n"
                f"📋 **Resumen de la labor detectada:**\n"
                f"• 📍 **Campo / Establecimiento:** **{campo_display}**\n"
                f"• 🗺️ **Lote:** **{lote_display}** ({has_done} Has de {crop_name})\n"
                f"• 🌾 **Labor a registrar:** **{labor_nombre}** ({maquinaria})\n"
                f"• ⛽ **Combustible a descontar:** **{int(liters_spent):,} Litros** de **{deps[tank_key]['nombre']}**\n"
                f"• 📦 **Insumos a descontar:** {insumos_str_disp}\n"
                f"• 👤 **Operario reportante:** *{sender_name}*\n\n"
                f"👉 **¿Confirmas registrar esta labor de {labor_nombre} en {campo_display} ({lote_display})?**\n"
                f"*(Responde \"Sí, confirmar\" o pulsa el botón para asentar definitivamente el registro).*"
            )
            append_to_history(user_message, double_verif_reply, executed_tools)
            return {
                "response": double_verif_reply,
                "proposal": proposal_data,
                "tool_calls": executed_tools,
                "is_demo": True,
                "stock_data": get_dashboard_summary()
            }

        # Descontar combustible en JSON
        saldo_est = max(0.0, saldo_actual_dep - liters_spent)
        deps[tank_key]["stock_actual_litros"] = saldo_est
        gasoil_json["totales"]["stock_fisico_campo_litros"] = sum(
            float(v.get("stock_actual_litros", 0)) for k, v in deps.items() if k != "acopio_por_retirar"
        )
        gasoil_json["totales"]["total_disponible_litros"] = (
            gasoil_json["totales"]["stock_fisico_campo_litros"] +
            float(deps.get("acopio_por_retirar", {}).get("litros_disponibles", 0))
        )
        _, meta_gw = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
        executed_tools.append(meta_gw)

        # Asentar en Django ORM (Deposito, Insumo, MovimientoStock)
        from .stock_service import StockIntegrityService
        from app.models import Lote
        target_lote_obj = Lote.objects.filter(nombre__icontains=lote_id.replace("Lote", "").strip()).first() or Lote.objects.first()

        try:
            StockIntegrityService.registrar_salida_combustible(
                litros=liters_spent,
                deposito_codigo=tank_key,
                lote=target_lote_obj,
                labor=f"{labor_nombre} en {lote_display} ({has_done} ha)",
                maquinaria=maquinaria,
                operario=sender_name,
                observaciones=f"Labor reportada en {campo_display}"
            )
        except Exception as ex_stock:
            logger.warning(f"Aviso StockIntegrityService en Section 0: {ex_stock}")

        # 6. Descuento de Insumos (Semillas, Fertilizantes, Fitosanitarios)
        insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_i)
        insumos_json = json.loads(insumos_raw)

        detalles_insumos = []
        semilla_str = "-"
        fert_str = "-"
        fito_str = "-"
        rinde_str = "-"

        # Descuento de Semilla si es siembra o se indican bolsas
        if "siembr" in labor_nombre.lower() or any(w in msg for w in ["semill", "bolsa", "bolsas"]):
            bags_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa\b)", msg)
            user_bags = int(float(bags_match.group(1).replace(".", "").replace(",", "."))) if bags_match else None
            seed_calc = calculate_seed_consumption(crop_key, has_done, user_specified_bags=user_bags)
            bags_qty = seed_calc["bolsas_finales"]

            if crop_key == "maiz":
                hibridos = insumos_json.get("semillas_maiz", {}).get("hibridos", [])
                target_h = next((h for h in hibridos if "DK" in h["id"] and h.get("en_planta_bolsas", 0) >= bags_qty), None)
                if not target_h:
                    target_h = next((h for h in hibridos if h.get("en_planta_bolsas", 0) >= bags_qty), (hibridos[0] if hibridos else None))
                if target_h:
                    if bags_qty > target_h.get("en_planta_bolsas", 0):
                        reply = (
                            f"❌ **No es posible registrar la siembra porque no hay stock suficiente de semillas de maíz.**\n\n"
                            f"- **Híbrido:** **{target_h['hibrido']}**\n"
                            f"- **Stock disponible en Planta:** **{target_h.get('en_planta_bolsas', 0)} bolsas**\n"
                            f"- **Bolsas requeridas:** **{bags_qty} bolsas** (para {has_done} ha en {lote_display})\n\n"
                            f"⚠️ *Tienes {target_h.get('por_retirar_bolsas', 0)} bolsas por retirar en {target_h.get('lugar_retiro', 'distribuidor')}. Trasládalas a Planta antes de sembrar.*"
                        )
                        append_to_history(user_message, reply, executed_tools)
                        return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
                    target_h["en_planta_bolsas"] = target_h["en_planta_bolsas"] - bags_qty
                    target_h["total_bolsas"] = target_h["en_planta_bolsas"] + target_h["por_retirar_bolsas"]
                    tot_p = sum(h["en_planta_bolsas"] for h in hibridos)
                    insumos_json["semillas_maiz"]["totales"]["bolsas_en_planta"] = tot_p
                    insumos_json["semillas_maiz"]["totales"]["total_general_bolsas"] = tot_p + insumos_json["semillas_maiz"]["totales"]["bolsas_por_retirar"]
                    semilla_str = f"{target_h['hibrido']} ({bags_qty} bolsas)"
                    detalles_insumos.append(f"🌱 Semilla: {bags_qty} bolsas de {target_h['hibrido']} ({seed_calc['detalle']}). Quedan {target_h['en_planta_bolsas']} bolsas en galpón.")

            elif "soja" in crop_key:
                var_soja = insumos_json.get("semillas_soja", {}).get("variedades", [])
                if var_soja:
                    disp_soja = var_soja[0].get("en_planta_bolsas", 0)
                    if bags_qty > disp_soja:
                        reply = (
                            f"❌ **No es posible registrar la siembra porque no hay stock suficiente de semillas de soja.**\n\n"
                            f"- **Variedad:** **{var_soja[0].get('variedad', 'DM 46R18')}**\n"
                            f"- **Stock disponible en galpón:** **{disp_soja} bolsas**\n"
                            f"- **Bolsas requeridas:** **{bags_qty} bolsas**\n\n"
                            f"⚠️ *No es posible gastar más semillas de las disponibles en inventario.*"
                        )
                        append_to_history(user_message, reply, executed_tools)
                        return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
                    var_soja[0]["en_planta_bolsas"] = disp_soja - bags_qty
                    var_soja[0]["total_bolsas"] = var_soja[0]["en_planta_bolsas"]
                    insumos_json["semillas_soja"]["totales"] = {"bolsas_en_planta": var_soja[0]["en_planta_bolsas"], "bolsas_por_retirar": 0, "total_general_bolsas": var_soja[0]["en_planta_bolsas"]}
                    semilla_str = f"{var_soja[0].get('variedad', 'DM 46R18')} ({bags_qty} bolsas)"
                    detalles_insumos.append(f"🌱 Semilla: {bags_qty} bolsas de {var_soja[0].get('variedad', 'DM 46R18')} ({seed_calc['detalle']}). Quedan {var_soja[0]['en_planta_bolsas']} bolsas en galpón.")

            elif "trigo" in crop_key:
                var_trigo = insumos_json.get("semillas_trigo", {}).get("variedades", [])
                if var_trigo:
                    target_trigo = var_trigo[0]
                    disp_trigo = target_trigo.get("en_planta_bolsas", 0)
                    if bags_qty > disp_trigo:
                        reply = (
                            f"❌ **No es posible registrar la siembra porque no hay stock suficiente de semillas de trigo.**\n\n"
                            f"- **Variedad:** **{target_trigo.get('variedad', 'Trigo Pan')}**\n"
                            f"- **Stock disponible en Planta:** **{disp_trigo} bolsas**\n"
                            f"- **Bolsas requeridas:** **{bags_qty} bolsas** (para {has_done} ha en {lote_display})\n\n"
                            f"⚠️ *Tienes {target_trigo.get('por_retirar_bolsas', 0)} bolsas por retirar en {target_trigo.get('lugar_retiro', 'distribuidor')}.*"
                        )
                        append_to_history(user_message, reply, executed_tools)
                        return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
                    target_trigo["en_planta_bolsas"] = disp_trigo - bags_qty
                    target_trigo["total_bolsas"] = target_trigo["en_planta_bolsas"] + target_trigo.get("por_retirar_bolsas", 0)
                    tot_trigo_p = sum(v.get("en_planta_bolsas", 0) for v in var_trigo)
                    insumos_json.setdefault("semillas_trigo", {}).setdefault("totales", {})
                    insumos_json["semillas_trigo"]["totales"]["bolsas_en_planta"] = tot_trigo_p
                    insumos_json["semillas_trigo"]["totales"]["total_general_bolsas"] = tot_trigo_p + insumos_json["semillas_trigo"]["totales"].get("bolsas_por_retirar", 0)
                    semilla_str = f"{target_trigo.get('variedad', 'Trigo Pan')} ({bags_qty} bolsas)"
                    detalles_insumos.append(f"🌱 Semilla: {bags_qty} bolsas de {target_trigo.get('variedad', 'Trigo Pan')} ({seed_calc['detalle']}). Quedan {target_trigo['en_planta_bolsas']} bolsas en galpón.")

        # Descuento de Fertilizante si se indica
        if any(w in msg for w in ["fertiliz", "map", "urea", "microessentials", "fosfato", "nitrogeno"]):
            kg_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:kg|kilos?|kilogramos?)", msg)
            user_kg = float(kg_match.group(1).replace(".", "").replace(",", ".")) if kg_match else None
            fert_type = "urea" if "urea" in msg else ("microessentials" if "micro" in msg else "map")
            fert_calc = calculate_fertilizer_consumption(fert_type, has_done, user_specified_kg=user_kg)
            kg_spent = fert_calc["kg_finales"]
            ferts = insumos_json.get("fertilizantes", [])
            target_f = ferts[0]
            if "urea" in msg:
                target_f = next((f for f in ferts if "Urea" in f["nombre"]), ferts[1] if len(ferts) > 1 else ferts[0])
            elif "micro" in msg:
                target_f = next((f for f in ferts if "Micro" in f["nombre"]), ferts[2] if len(ferts) > 2 else ferts[0])

            disp_fert = target_f.get("en_galpon_kg", 0.0)
            if kg_spent > disp_fert:
                reply = (
                    f"❌ **No es posible registrar la aplicación porque no hay stock suficiente de fertilizante.**\n\n"
                    f"- **Producto:** **{target_f['nombre']}**\n"
                    f"- **Stock disponible en galpón:** **{int(disp_fert):,} kg**\n"
                    f"- **Cantidad requerida:** **{int(kg_spent):,} kg**\n\n"
                    f"⚠️ *Tienes {int(target_f.get('por_retirar_kg', 0)):,} kg pendientes de retiro en {target_f.get('lugar_retiro', 'distribuidor')}.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
            target_f["en_galpon_kg"] = disp_fert - kg_spent
            target_f["total_kg"] = target_f["en_galpon_kg"] + target_f.get("por_retirar_kg", 0)
            insumos_json["fertilizantes_totales"]["en_galpon_kg"] = sum(f["en_galpon_kg"] for f in ferts)
            insumos_json["fertilizantes_totales"]["total_general_kg"] = sum(f["total_kg"] for f in ferts)
            fert_str = f"{target_f['nombre']} ({int(kg_spent):,} kg)"
            detalles_insumos.append(f"🧪 Fertilizante aplicado: {int(kg_spent):,} kg de {target_f['nombre']} (Quedan {int(target_f['en_galpon_kg']):,} kg en galpón)")

        # Descuento de Fitosanitarios si se indica
        if any(w in msg for w in ["pulveriz", "fumig", "barbecho", "glifosato", "2,4-d", "enlist", "coadyuvante", "coragen"]):
            fitos = insumos_json.get("fitosanitarios", [])
            fito_match = None
            if "glifosato" in msg:
                fito_match = next((f for f in fitos if "Glifosato" in f.get("nombre", "")), fitos[0] if fitos else None)
            elif "2,4-d" in msg or "enlist" in msg:
                fito_match = next((f for f in fitos if "2,4-D" in f.get("nombre", "")), fitos[1] if len(fitos) > 1 else None)
            elif "coragen" in msg:
                fito_match = next((f for f in fitos if "Coragen" in f.get("nombre", "")), None)
            elif "coadyuvante" in msg:
                fito_match = next((f for f in fitos if "Coadyuvante" in f.get("nombre", "")), None)
            else:
                fito_match = fitos[0] if fitos else None

            if fito_match:
                litros_fito_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt\b)\s*(?:de\s+)?(?:glifosato|2,4-d|enlist|coadyuvante|coragen|quimico|herbicida|producto)", msg)
                if not litros_fito_match:
                    all_lits = re.findall(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt\b)", msg)
                    if len(all_lits) > 1:
                        litros_fito = float(all_lits[1].replace(".", "").replace(",", "."))
                    else:
                        litros_fito = round(has_done * 2.5, 1)
                else:
                    litros_fito = float(litros_fito_match.group(1).replace(".", "").replace(",", "."))

                disp_fito = float(fito_match.get("en_galpon", 0.0))
                if litros_fito <= disp_fito:
                    fito_match["en_galpon"] = disp_fito - litros_fito
                    fito_match["total"] = fito_match["en_galpon"] + float(fito_match.get("a_retirar", 0.0))
                    insumos_json.setdefault("fitosanitarios_totales", {})
                    insumos_json["fitosanitarios_totales"]["en_galpon_litros"] = sum(float(f.get("en_galpon", 0)) for f in fitos)
                    insumos_json["fitosanitarios_totales"]["total_general_litros"] = sum(float(f.get("total", 0)) for f in fitos)
                    fito_str = f"{fito_match['nombre']} ({int(litros_fito)} L)"
                    detalles_insumos.append(f"🛡️ Fitosanitario aplicado: {int(litros_fito)} L de {fito_match['nombre']} (Quedan {int(fito_match['en_galpon'])} L en galpón)")

        # Cosecha / Trilla si aplica
        if "trill" in labor_nombre.lower() or "cosech" in labor_nombre.lower():
            qq_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:qq|quintales?)", msg)
            rinde_qq = float(qq_match.group(1).replace(".", "").replace(",", ".")) if qq_match else 39.0
            tn_total = round((has_done * rinde_qq * 100) / 1000.0, 1)
            rinde_str = f"{rinde_qq} qq/ha ({tn_total} Tn)"
            detalles_insumos.append(f"🌾 Cosecha obtenida: {rinde_qq} qq/ha ({tn_total} Toneladas totales)")

        _, w_i = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
        executed_tools.append(w_i)

        # 7. Registrar Labor en el Lote y Regenerar Hoja de Cálculo del Cultivo
        labor_registro = {
            "fecha": today_str,
            "lote": lote_display,
            "superficie_ha": has_done,
            "labor": labor_nombre,
            "maquinaria": maquinaria,
            "operario": sender_name,
            "combustible_litros": liters_spent,
            "deposito_combustible": deps[tank_key]["nombre"],
            "semilla": semilla_str,
            "fertilizante": fert_str,
            "insumos": fito_str,
            "rinde": rinde_str,
            "observaciones": f"Labor registrada automáticamente en {campo_display}"
        }
        append_labor_to_crop(crop_key, campo_nombre, lote_id, labor_registro)

        # 8. Memoria de negocio
        memo_entry = f"Labor {labor_nombre} en {campo_display} ({lote_display} - {crop_name}): {has_done} ha, -{int(liters_spent)} L {deps[tank_key]['nombre']}"
        if semilla_str != "-":
            memo_entry += f", semilla: {semilla_str}"
        if fert_str != "-":
            memo_entry += f", fert: {fert_str}"
        if fito_str != "-":
            memo_entry += f", fito: {fito_str}"
        _, w_m = execute_native_tool("append_memory", {"entry": memo_entry})
        executed_tools.append(w_m)

        # 9. Respuesta afirmativa y detallada
        detalles_texto = "\n".join([f"• {d}" for d in detalles_insumos]) if detalles_insumos else "• Laboreo mecánico de suelo con implemento sin insumos químicos."
        reply = (
            f"{crop_icon} **Labor Registrada y Asentada en el Campo:**\n\n"
            f"📋 **Detalle de la Operación:**\n"
            f"- **Establecimiento:** **{campo_display}**\n"
            f"- **Lote asignado:** **{lote_display}** ({has_done} hectáreas trabajadas)\n"
            f"- **Cultivo:** **{crop_name}**\n"
            f"- **Labor realizada:** **{labor_nombre}** ({maquinaria})\n"
            f"- **Operario a cargo:** *{sender_name}*\n\n"
            f"⛽ **Descuento de Combustible (Gasoil):**\n"
            f"- **Gasoil consumido:** **{int(liters_spent):,} Litros** descontados de **{deps[tank_key]['nombre']}**\n"
            f"- **Remanente en {deps[tank_key]['nombre']}:** **{int(deps[tank_key]['stock_actual_litros']):,} Litros** ({round(deps[tank_key]['stock_actual_litros']/deps[tank_key]['capacidad_max_litros']*100)}% lleno)\n"
            f"- **Stock físico total en campo:** {int(gasoil_json['totales']['stock_fisico_campo_litros']):,} Litros\n\n"
            f"📦 **Descuento de Insumos / Semillas / Fertilizantes:**\n"
            f"{detalles_texto}\n\n"
            f"📊 **Hojas de Cálculo y Base de Datos Actualizadas:**\n"
            f"• Solapa **'Campo {campo_nombre}'** en **{sheet_name}** actualizada con la labor.\n"
            f"• Libro Maestro **IA_Desk_Agro_Consolidado.xlsx** recalculado con nuevos saldos.\n"
            f"• Registro histórico asentado en la bitácora operativa de **IA Desk Agro**."
        )

        append_to_history(user_message, reply, executed_tools)
        return {
            "response": reply,
            "tool_calls": executed_tools,
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }


    # ==============================================================
    # 0.05 CONSULTAS DINÁMICAS DE CAMPOS Y ESTABLECIMIENTOS REGISTRADOS
    # ==============================================================
    from .campo_service import (
        obtener_campos_con_lotes,
        buscar_campo_en_mensaje,
        buscar_lote_en_campo,
        generar_respuesta_campo,
        generar_resumen_todos_los_campos,
        normalizar_texto
    )

    # Identificar si es un reporte de labor que debe procesarse con descuento de combustible/insumos
    is_labor_report = any(w in msg for w in ["sembr", "siembra", "trill", "cosech", "fertiliz", "pulveriz", "disco", "rastra", "fumig"]) and \
                      any(w in msg for w in ["litro", "litros", "lts", "ha", "has", "hectarea", "hectareas", "kg", "kilos", "bolsa", "bolsas"]) and \
                      any(w in msg for w in ["gaste", "gasto", "use", "uso", "consumi", "consumo", "cargue", "cargamos", "aplicamos", "tiramos", "hicimos"])

    if not is_field_labor_action:
        campos_registrados = obtener_campos_con_lotes()
        target_campo = buscar_campo_en_mensaje(user_message, campos_registrados)

        is_diag_word = any(w in msg for w in [
            "diagrama", "diagramas", "plano", "planos", "mapa", "mapas", "cartografia", "cartografía",
            "esquema", "esquemas", "foto", "fotos", "imagen", "imagenes", "imágenes", "croquis", "gis"
        ])

        is_general_campos_query = any(p in msg for p in [
            "cuales son mis campos", "cuáles son mis campos", "que campos tengo", "qué campos tengo",
            "que campos agregue", "qué campos agregué", "que campos cargue", "qué campos cargué",
            "campos cargados", "campos registrados", "mis campos", "mis establecimientos",
            "resumen de campos", "listar campos", "todos los campos", "diagramas de campos",
            "planos de campos", "cartografia de campos", "cartografía de campos", "cuantos campos tengo",
            "cuántos campos tengo", "establecimientos que tengo", "establecimientos cargados"
        ]) or (any(w in msg for w in ["campo", "campos", "establecimiento", "establecimientos"]) and any(w in msg for w in ["cuales", "cuáles", "que", "qué", "cuantos", "cuántos", "lista", "listar", "todos", "resumen", "mis"]))

        # Caso A: Se menciona un campo específico (ej: "establecimiento don lorenzo", "don lorenzo", "campo don alfredo", etc.)
        if target_campo:
            _, meta_c = execute_native_tool("read_file", {"filename": "registro_campos.json"})
            executed_tools.append(meta_c)

            specific_lote = buscar_lote_en_campo(user_message, target_campo)
            reply = generar_respuesta_campo(target_campo, specific_lote=specific_lote, is_diag_only=is_diag_word, query_prompt=user_message)

            append_to_history(user_message, reply, executed_tools)
            return {
                "response": reply,
                "tool_calls": executed_tools,
                "is_demo": True,
                "stock_data": get_dashboard_summary()
            }

        # Caso B: Consulta general sobre todos los campos del productor
        elif is_general_campos_query:
            _, meta_c = execute_native_tool("read_file", {"filename": "registro_campos.json"})
            executed_tools.append(meta_c)

            reply = generar_resumen_todos_los_campos(campos_registrados, show_diagrams=is_diag_word)
            append_to_history(user_message, reply, executed_tools)
            return {
                "response": reply,
                "tool_calls": executed_tools,
                "is_demo": True,
                "stock_data": get_dashboard_summary()
            }

    # ==============================================================
    # 0.1 CONSULTAS GENÉRICAS DE LOTES (CUANDO NO SE ESPECIFICÓ CAMPO)
    # ==============================================================
    is_lote_query = ("lote" in msg or "parcela" in msg) and not is_fuel_context and not is_field_labor_action and not any(w in msg for w in ["gaste", "consumo", "litros"])
    if is_lote_query:
        lotes_raw, meta_l = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.append(meta_l)
        try:
            lotes_data = json.loads(lotes_raw).get("lotes", [])
        except Exception:
            lotes_data = []

        m_clean = normalizar_texto(msg)
        # Buscar coincidencias entre todos los lotes
        matched_lotes = []
        for l in lotes_data:
            ln = normalizar_texto(l.get("nombre", ""))
            if ln in m_clean:
                matched_lotes.append(l)
                continue
            # Buscar número o letra de lote
            match_num = re.search(r'(?:lote|parcela)\s*([0-9a-zA-Z]+)', ln)
            if match_num:
                val = match_num.group(1)
                if re.search(r'\b(?:lote|parcela)\s*' + re.escape(val) + r'\b', m_clean) or re.search(r'\blote' + re.escape(val) + r'\b', m_clean):
                    matched_lotes.append(l)

        if len(matched_lotes) == 1:
            target_lote = matched_lotes[0]
            l_nom = target_lote.get("nombre", "Lote")
            l_campo = target_lote.get("campo", "Campo")
            l_sup = target_lote.get("superficie_ha", "-")
            l_cult = target_lote.get("cultivo", "-")
            l_hib = target_lote.get("hibridos_plantados") or target_lote.get("variedad") or "Sin híbrido especificado"
            l_diag_url = target_lote.get("diagrama_url", "")
            l_diag_nom = target_lote.get("diagrama_nombre") or f"Diagrama agronómico de {l_nom}"
            l_estado = target_lote.get("estado_actual", "En seguimiento agronómico activo")

            reply = (
                f"🌱 **Información Agronómica - {l_nom}:**\n\n"
                f"• 🌾 **Híbridos / Variedades:** **{l_hib}**\n"
                f"• 🚜 **Cultivo y Superficie:** {l_cult} ({l_sup} hectáreas)\n"
                f"• 📍 **Establecimiento:** {l_campo}\n"
                f"• 📋 **Estado actual:** {l_estado}\n\n"
            )
            if l_diag_url:
                reply += (
                    f"🗺️ **Diagrama / Cartografía Asociada:**\n"
                    f"![{l_diag_nom}]({l_diag_url})\n\n"
                    f"*Esquema registrado: `{l_diag_nom}`.*"
                )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        elif len(matched_lotes) > 1:
            reply = (
                f"🌱 **He encontrado varios lotes con esa denominación en tus campos:**\n\n"
            )
            for idx, l in enumerate(matched_lotes, 1):
                ln = l.get("nombre", "Lote")
                lc = l.get("campo", "Campo")
                lh = l.get("superficie_ha", "-")
                lcult = l.get("cultivo", "-")
                lvar = l.get("variedad") or l.get("hibridos_plantados") or ""
                v_str = f" - {lvar}" if lvar and lvar != "S/D" else ""
                reply += f"{idx}. 🌾 **{ln}** ({lc}): **{lh} ha** • Cultivo: **{lcult}**{v_str}\n"

            reply += f"\n💡 *Puedes consultarme indicando el campo (por ejemplo: 'Lote 1 de Don Lorenzo' o 'Lote 1 de La Esperanza') para ver su plano y detalles.*"
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
 # ==============================================================
    # 0.0 CONSULTAS DE CALIBRACIÓN DE INSUMOS, NORMAS INTA Y APIS GRATUITAS
    # ==============================================================
    is_agronomic_calc_or_api_query = any(w in msg for w in [
        "api gratuita", "apis gratuitas", "api libre", "apis libres", "open-meteo", "open meteo",
        "datos.gob.ar", "costomaq", "norma inta", "normas inta", "coeficiente", "coeficientes",
        "calculo de gasoil", "cálculo de gasoil", "calculo de semillas", "cálculo de semillas",
        "cantidad de semillas utilizadas", "consumo por labor", "consumo de gasoil por labor",
        "como se calcula el gasoil", "cómo se calcula el gasoil", "como se calculan las semillas",
        "como calculas el gasoil", "cómo calculas el gasoil"
    ]) or (
        any(w in msg for w in ["calculo", "cálculo", "consumo", "gasto", "erroneo", "erróneo", "erroneao"]) and
        any(w in msg for w in ["gasoil", "combustible", "diesel", "semilla", "semillas", "insumo", "insumos"]) and
        any(w in msg for w in ["api", "apis", "libre", "libres", "gratis", "gratuita", "gratuitas", "descontar", "vincular", "norma", "por labor"])
    )

    if is_agronomic_calc_or_api_query:
        from .agronomic_engine import get_agronomic_standards_report
        reply = get_agronomic_standards_report()
        append_to_history(user_message, reply, executed_tools)
        return {
            "response": reply,
            "tool_calls": executed_tools,
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    # ==============================================================
    # 0.9 RETIRO DE SEMILLAS DE ACOPIO EXTERNO HACIA GALPÓN / PLANTA
    # ==============================================================
    has_seed_word = any(w in msg for w in [
        "semilla", "semillas", "bolsa", "bolsas", "hibrido", "híbrido", "hibridos", "híbridos",
        "maiz", "maíz", "soja", "dk", "dekalb", "pioneer", "p2089", "nidera", "ax7784", "ax 7784",
        "don mario", "dm46", "dm 46"
    ])
    has_seed_acopio = any(w in msg for w in [
        "acopio", "acpio", "acoppio", "proveedor", "distribuidor", "externo", "exteno", "por retirar",
        "bayer", "corteva", "cooperativa", "semilleria", "semillería"
    ])
    has_seed_move = any(w in msg for w in [
        "retir", "saqu", "sacar", "saco", "traer", "traje", "trajo", "trajimos",
        "pas", "carg", "llev", "guard", "almacen", "pon", "pus"
    ])

    is_seed_withdrawal = (
        (has_seed_word and has_seed_acopio and has_seed_move) or
        (has_seed_word and ("acopio" in msg or "acpio" in msg) and any(w in msg for w in ["retir", "saqu", "trae", "guard"])) or
        ("semilla" in msg and any(w in msg for w in ["retiré", "retire", "retiramos", "traje", "trajimos", "traer"]) and any(w in msg for w in ["planta", "galpon", "galpón", "guard", "tanque", "lugar"]))
    )

    if is_seed_withdrawal:
        insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_ins)
        insumos_json = json.loads(insumos_raw)
        mz_dict = insumos_json.get("semillas_maiz", {})
        hibridos = mz_dict.get("hibridos", [])
        soja_dict = insumos_json.get("semillas_soja", {})
        variedades = soja_dict.get("variedades", [])

        target_seed = None
        crop_type = "maiz"

        if any(w in msg for w in ["soja", "dm", "don mario", "46r18"]):
            crop_type = "soja"
            target_seed = variedades[0] if variedades else None
        elif "dk" in msg or "72-10" in msg or "7210" in msg or "dekalb" in msg:
            target_seed = next((h for h in hibridos if "DK" in h["id"]), None)
        elif "pioneer" in msg or "2089" in msg:
            target_seed = next((h for h in hibridos if "P2089" in h["id"]), None)
        elif "nidera" in msg or "7784" in msg or "ax" in msg:
            target_seed = next((h for h in hibridos if "AX7784" in h["id"]), None)

        if not target_seed:
            cand = next((h for h in hibridos if h.get("por_retirar_bolsas", 0) > 0), None)
            if cand:
                target_seed = cand
                crop_type = "maiz"
            elif variedades and variedades[0].get("por_retirar_bolsas", 0) > 0:
                target_seed = variedades[0]
                crop_type = "soja"
            else:
                target_seed = hibridos[0] if hibridos else None

        bags_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa )", msg)
        if bags_match:
            bags_qty = int(float(bags_match.group(1).replace(".", "").replace(",", ".")))
        else:
            m_num = re.search(r"\b(\d+)\b", msg)
            bags_qty = int(m_num.group(1)) if m_num else (target_seed.get("por_retirar_bolsas", 20) if target_seed else 20)

        seed_name = target_seed.get("hibrido") or target_seed.get("variedad", "Semilla Fiscalizada") if target_seed else "Semilla"
        available_acopio = target_seed.get("por_retirar_bolsas", 0) if target_seed else 0
        lugar_dest = "Galpón Central de Insumos (Planta)" if not any(w in msg for w in ["lote"]) else "Depósito de Campo"

        # Validación estricta: No permitir retirar más del stock disponible en acopio
        if bags_qty > available_acopio:
            reply = (
                f"❌ **No es posible realizar el retiro porque no hay suficientes bolsas en el acopio externo.**\n\n"
                f"- **Semilla:** **{seed_name}**\n"
                f"- **Bolsas disponibles en acopio proveedor:** **{available_acopio} bolsas**\n"
                f"- **Intentaste retirar:** **{bags_qty} bolsas**\n\n"
                f"⚠️ *No es posible retirar más bolsas de las compradas y disponibles en acopio.*"
            )
            append_to_history(user_message, reply, executed_tools)
            return {
                "response": reply,
                "tool_calls": executed_tools,
                "is_demo": True,
                "stock_data": get_dashboard_summary()
            }

        # Actualización de inventario: RESTA de acopio y SUMA a la planta / galpón
        target_seed["por_retirar_bolsas"] -= bags_qty
        target_seed["en_planta_bolsas"] += bags_qty
        target_seed["total_bolsas"] = target_seed["en_planta_bolsas"] + target_seed["por_retirar_bolsas"]

        if crop_type == "maiz":
            tot_planta = sum(h["en_planta_bolsas"] for h in hibridos)
            tot_retiro = sum(h["por_retirar_bolsas"] for h in hibridos)
            mz_dict["totales"]["bolsas_en_planta"] = tot_planta
            mz_dict["totales"]["bolsas_por_retirar"] = tot_retiro
            mz_dict["totales"]["total_general_bolsas"] = tot_planta + tot_retiro
        else:
            tot_planta = sum(v["en_planta_bolsas"] for v in variedades)
            tot_retiro = sum(v["por_retirar_bolsas"] for v in variedades)
            soja_dict["totales"]["bolsas_en_planta"] = tot_planta
            soja_dict["totales"]["bolsas_por_retirar"] = tot_retiro
            soja_dict["totales"]["total_general_bolsas"] = tot_planta + tot_retiro

        _, meta_w = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
        executed_tools.append(meta_w)

        motivo = f"Retiro de {bags_qty} bolsas de semilla {seed_name} desde acopio proveedor hacia {lugar_dest}"
        _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
        executed_tools.append(meta_m)

        # Persistir en base de datos relacional y sincronizar planillas de Google Drive
        try:
            from app.services.stock_service import StockIntegrityService
            StockIntegrityService.registrar_retiro_acopio_semilla(
                bolsas=bags_qty,
                hibrido_o_nombre=seed_name,
                deposito_destino_nombre=lugar_dest,
                operario=sender_name,
                observaciones=motivo
            )
        except Exception as e:
            print(f"Error registrando retiro de semilla en DB: {e}")

        reply = (
            f"📦 **Retiro de Semillas de Acopio Externo Asentado con Éxito:**\n\n"
            f"- **Híbrido / Variedad:** **{seed_name}** ({target_seed.get('proveedor', 'Proveedor')}).\n"
            f"- **Bolsas retiradas del acopio:** **{bags_qty} bolsas**.\n"
            f"- **Guardado en:** **{lugar_dest}** (+{bags_qty} bolsas sumadas al stock físico disponible).\n"
            f"- **Nuevo stock disponible en campo:** **{target_seed['en_planta_bolsas']} bolsas**.\n"
            f"- **Saldo restante por retirar en proveedor:** **{target_seed['por_retirar_bolsas']} bolsas**."
        )
        append_to_history(user_message, reply, executed_tools)
        return {
            "response": reply,
            "tool_calls": executed_tools,
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }

    # ==============================================================
    # 1. CASO SEMILLAS DE MAÍZ POR HÍBRIDO (BOLSAS EN PLANTA O POR RETIRAR)
    # ==============================================================
    is_corn_seed_query_or_action = not is_fuel_context and (
        any(w in msg for w in ["maiz", "maíz", "dk7210", "dk 72", "dekalb", "pioneer", "p2089", "nidera", "ax7784", "ax 7784", "hibrido", "híbrido", "hibridos", "híbridos"]) or
        (("semilla" in msg or "semillas" in msg or "bolsa" in msg or "bolsas" in msg) and any(w in msg for w in ["maiz", "maíz", "soja", "trigo", "dm46", "stock", "saldo", "cuanto", "cuánto", "que", "hibrido"])) or
        (any(w in msg for w in ["soja", "trigo"]) and any(w in msg for w in ["semilla", "semillas", "bolsa", "bolsas"]))
    )

    if is_corn_seed_query_or_action:
        insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_ins)
        insumos_json = json.loads(insumos_raw)
        mz_dict = insumos_json.get("semillas_maiz", {})
        hibridos = mz_dict.get("hibridos", [])

        target_hibrido = None
        if "dk" in msg or "72-10" in msg or "7210" in msg or "dekalb" in msg:
            target_hibrido = next((h for h in hibridos if "DK" in h["id"]), hibridos[0])
        elif "pioneer" in msg or "2089" in msg:
            target_hibrido = next((h for h in hibridos if "P2089" in h["id"]), hibridos[1])
        elif "nidera" in msg or "7784" in msg or "ax" in msg:
            target_hibrido = next((h for h in hibridos if "AX7784" in h["id"]), hibridos[2])
        elif hibridos:
            target_hibrido = hibridos[0]

        bags_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa )", msg)
        bags_qty = int(float(bags_match.group(1).replace(".", "").replace(",", "."))) if bags_match else 40

        is_moving_to_planta = any(w in msg for w in ["retiré", "retire", "retiramos", "trajimos", "traje", "trasladamos"]) and any(w in msg for w in ["planta", "galpon", "galpón", "bayer", "semillería", "semilleria", "cooperativa"])
        is_query_seeds = any(w in msg for w in ["?", "¿", "cuanto", "cuánto", "saldo", "stock", "estado", "listar", "ver", "tenemos", "informe"]) or msg.strip().startswith("que ") or msg.strip().startswith("qué ")
        is_sowing_corn = (not is_query_seeds) and any(w in msg for w in ["sembr", "siembra", "lote 2", "gastamos", "usamos"]) and not is_moving_to_planta

        if is_moving_to_planta and target_hibrido:
            moved = min(target_hibrido["por_retirar_bolsas"], bags_qty)
            target_hibrido["por_retirar_bolsas"] -= moved
            target_hibrido["en_planta_bolsas"] += moved

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
            if bags_qty > target_hibrido["en_planta_bolsas"]:
                reply = (
                    f"❌ **No es posible registrar la siembra porque no hay stock suficiente de semillas.**\n\n"
                    f"- **Híbrido de Maíz:** **{target_hibrido['hibrido']}**\n"
                    f"- **Stock disponible en Planta:** **{target_hibrido['en_planta_bolsas']} bolsas**\n"
                    f"- **Intentaste gastar:** **{bags_qty} bolsas**\n\n"
                    f"⚠️ *No es posible gastar más bolsas de las existentes en Planta Central.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
            used = bags_qty
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
            reply = _build_semillas_query_reply(user_message, executed_tools)
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 2. CASO GRANOS EN SILOS DE GUARDADO Y ACOPIO (5 PRINCIPALES + 2 DE TRILLA)
    # ==============================================================
    is_grain_silo_query_or_action = not is_fuel_context and (
        any(w in msg for w in ["silo", "silos", "trilla", "grano", "granos", "silobolsa", "silobolsas"]) or
        ("acopio" in msg and not any(w in msg for w in ["fertilizante", "urea", "map", "insumo"])) or
        (any(w in msg for w in ["soja", "trigo", "maiz", "maíz"]) and any(w in msg for w in ["tonelada", "toneladas", "tn", "acopiad", "guardad", "cosechad", "capacidad"]))
    ) and not any(w in msg for w in ["sembr", "siembra", "sembrando"])

    if is_grain_silo_query_or_action:
        granos_raw, meta_gr = execute_native_tool("read_file", {"filename": "stock_granos_silos.json"})
        executed_tools.append(meta_gr)
        granos_json = json.loads(granos_raw)

        principales = granos_json.get("silos_principales", [])
        trilla = granos_json.get("silos_trilla", [])
        all_silos = principales + trilla

        is_dispatch = any(w in msg for w in ["carg", "vend", "entreg", "despach", "sacar", "retiro", "descarg"]) and any(char.isdigit() for char in user_message)

        if is_dispatch:
            tn_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:toneladas?|tn )?", msg)
            tn_qty = float(tn_match.group(1).replace(".", "").replace(",", ".")) if tn_match else 30.0

            # Buscar silo por nombre o número
            target_silo = None
            if "trilla 4" in msg or "silo 4 de trilla" in msg:
                target_silo = next((s for s in trilla if "4" in s.get("nombre", "")), None)
            elif "trilla 3" in msg or "silo 3 de trilla" in msg or "trilla" in msg:
                target_silo = next((s for s in trilla if "3" in s.get("nombre", "")), trilla[0] if trilla else None)
            elif "silo 5" in msg:
                target_silo = next((s for s in principales if "5" in s.get("nombre", "")), None)
            elif "silo 4" in msg:
                target_silo = next((s for s in principales if "4" in s.get("nombre", "")), None)
            elif "silo 3" in msg:
                target_silo = next((s for s in principales if "3" in s.get("nombre", "")), None)
            elif "silo 2" in msg:
                target_silo = next((s for s in principales if "2" in s.get("nombre", "")), None)
            elif "silo 1" in msg:
                target_silo = next((s for s in principales if "1" in s.get("nombre", "")), None)

            if not target_silo:
                # Si se menciona un cultivo, buscar el primer silo con stock de ese cultivo
                if "trigo" in msg:
                    target_silo = next((s for s in all_silos if s.get("cultivo") == "Trigo" and s.get("stock_actual_tn", 0) > 0), all_silos[2])
                elif "maiz" in msg or "maíz" in msg:
                    target_silo = next((s for s in all_silos if s.get("cultivo") == "Maíz" and s.get("stock_actual_tn", 0) > 0), all_silos[4])
                else:
                    target_silo = next((s for s in all_silos if s.get("cultivo") == "Soja" and s.get("stock_actual_tn", 0) > 0), all_silos[0])

            if tn_qty > target_silo.get("stock_actual_tn", 0):
                disp_silo = target_silo.get("stock_actual_tn", 0)
                reply = (
                    f"❌ **No es posible realizar el despacho porque no hay stock suficiente en el silo.**\n\n"
                    f"- **Silo de Origen:** **{target_silo['nombre']}** ({target_silo.get('cultivo', 'Grano')})\n"
                    f"- **Stock disponible:** **{disp_silo:,} Toneladas**\n"
                    f"- **Intentaste despachar:** **{tn_qty:,} Toneladas**\n\n"
                    f"⚠️ *No es posible despachar una carga superior a los granos almacenados en el silo.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
            dispatched = tn_qty
            target_silo["stock_actual_tn"] = round(target_silo["stock_actual_tn"] - dispatched, 1)

            # Recalcular totales
            stock_p = sum(s.get("stock_actual_tn", 0) for s in principales)
            stock_t = sum(s.get("stock_actual_tn", 0) for s in trilla)
            granos_json["totales_generales"]["stock_principales_tn"] = round(stock_p, 1)
            granos_json["totales_generales"]["stock_trilla_tn"] = round(stock_t, 1)
            granos_json["totales_generales"]["total_granos_almacenados_tn"] = round(stock_p + stock_t, 1)

            _, meta_w = execute_native_tool("write_file", {"filename": "stock_granos_silos.json", "content": json.dumps(granos_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)

            # Generar CSV y hojas en segundo plano
            try:
                from .sheets_export_service import generate_consolidated_workbook
                generate_consolidated_workbook()
            except Exception:
                pass

            motivo = f"Despacho/Carga de {dispatched} Tn desde {target_silo['nombre']} ({target_silo.get('cultivo', 'Grano')}) a camión puerto"
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"🚛 **Despacho de Granos Registrado:**\n\n"
                f"- **Origen:** **{target_silo['nombre']}** ({target_silo.get('tipo', 'Silo')}).\n"
                f"- **Cultivo:** **{target_silo.get('cultivo', 'Grano')}**.\n"
                f"- **Toneladas despachadas:** **{dispatched} Tn**.\n"
                f"- **Stock remanente en ese silo:** **{target_silo['stock_actual_tn']:,} Tn** (Cap. máx: {int(target_silo['capacidad_max_tn'])} Tn).\n\n"
                f"📊 **Subtotal Silos Principales:** **{stock_p:,} Tn** | **Subtotal Silos Trilla:** **{stock_t:,} Tn**.\n"
                f"👉 **Total Acopio Almacenado:** **{round(stock_p + stock_t, 1):,} Toneladas** (de 2.980 Tn capacidad total)."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        else:
            reply = _build_silos_query_reply(user_message, executed_tools)
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 3. CASO COMBINADO FERTILIZANTES E INSUMOS (CUANDO SE CONSULTAN AMBOS)
    # ==============================================================
    is_fert_flag = any(w in msg for w in [
        "fertilizante", "fertilizantes", "map", "urea", "microessentials", "micro essentials",
        "fosfato", "fosfatos", "fósforo", "fosforo", "nitrogeno", "nitrógeno"
    ]) and not any(w in msg for w in ["gasoil", "diesel"])

    is_fito_flag = any(w in msg for w in [
        "insumo", "insumos", "fitosanitario", "fitosanitarios", "agroquimico", "agroquimicos",
        "agroquímico", "agroquímicos", "glifosato", "2,4-d", "enlist", "coadyuvante", "coragen",
        "herbicida", "herbicidas", "insecticida", "insecticidas"
    ])

    if is_fert_flag and is_fito_flag:
        insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_ins)
        insumos_json = json.loads(insumos_raw)

        ferts = insumos_json.get("fertilizantes", [])
        fitos = insumos_json.get("fitosanitarios", [])

        tot_fg_kg = insumos_json.get("fertilizantes_totales", {}).get("en_galpon_kg", 29600.0)
        tot_fr_kg = insumos_json.get("fertilizantes_totales", {}).get("por_retirar_kg", 20000.0)
        tot_fgral_kg = insumos_json.get("fertilizantes_totales", {}).get("total_general_kg", 49600.0)

        tot_ig_l = insumos_json.get("fitosanitarios_totales", {}).get("en_galpon_litros", 1190.0)
        tot_ir_l = insumos_json.get("fitosanitarios_totales", {}).get("a_retirar_litros", 620.0)
        tot_igral_l = insumos_json.get("fitosanitarios_totales", {}).get("total_general_litros", 1810.0)

        fert_lines = []
        for f in ferts:
            fert_lines.append(
                f"   • **{f['nombre']}** ({f['formula']}):\n"
                f"     - 🏠 En Galpón: **{int(f['en_galpon_kg']):,} kg** ({round(f['en_galpon_kg']/1000.0, 1)} Tn)\n"
                f"     - 📍 Por Retirar: **{int(f['por_retirar_kg']):,} kg** en *{f['lugar_retiro']}*\n"
                f"     - Total: **{int(f['total_kg']):,} kg**"
            )

        fito_lines = []
        for f in fitos:
            fito_lines.append(
                f"   • **{f['nombre']}** ({f['tipo']}):\n"
                f"     - 🏠 En Galpón: **{int(f['en_galpon']):,} Litros**\n"
                f"     - 📍 A Retirar: **{int(f['a_retirar']):,} Litros** en *{f['lugar_retiro']}*\n"
                f"     - Total: **{int(f['total']):,} Litros**"
            )

        reply = (
            f"🧪 **INVENTARIO DE FERTILIZANTES (EN KILOGRAMOS) & INSUMOS (GALPÓN VS RETIRO):**\n\n"
            f"**1. 🧪 FERTILIZANTES (Kilogramos - kg):**\n" +
            "\n".join(fert_lines) +
            f"\n   *Subtotales Fertilizantes:* 🏠 En Galpón: **{int(tot_fg_kg):,} kg** | 📍 Por Retirar: **{int(tot_fr_kg):,} kg** | **Total: {int(tot_fgral_kg):,} kg**.\n\n"
            f"**2. 📦 INSUMOS Y FITOSANITARIOS (Litros):**\n" +
            "\n".join(fito_lines) +
            f"\n   *Subtotales Insumos:* 🏠 En Galpón: **{int(tot_ig_l):,} L** | 📍 A Retirar: **{int(tot_ir_l):,} L** | **Total: {int(tot_igral_l):,} L**.\n\n"
            f"📌 Todos los productos cuentan con lugar determinado de retiro y seguimiento de existencias en galpón."
        )
        append_to_history(user_message, reply, executed_tools)
        return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 4. CASO FERTILIZANTES EN KILOGRAMOS (EN GALPÓN & POR RETIRAR)
    # ==============================================================
    elif is_fert_flag:
        insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_ins)
        insumos_json = json.loads(insumos_raw)
        ferts = insumos_json.get("fertilizantes", [])

        is_moving_fert = any(w in msg for w in ["retiré", "retire", "retiramos", "trajimos", "traje", "trasladamos", "cargamos", "pasar"]) and any(w in msg for w in ["galpon", "galpón", "planta", "ypf", "aca", "bunge"])
        is_query_fert = any(w in msg for w in ["?", "¿", "cuanto", "cuánto", "saldo", "stock", "estado", "listar", "ver", "tenemos", "informe", "aparezca", "aparezcan"]) or msg.strip().startswith("que ") or msg.strip().startswith("qué ")

        target_fert = ferts[0]
        if "urea" in msg:
            target_fert = next((f for f in ferts if "Urea" in f["nombre"]), ferts[1])
        elif "micro" in msg:
            target_fert = next((f for f in ferts if "Micro" in f["nombre"]), ferts[2])

        if is_moving_fert and not is_query_fert:
            kg_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:kg|kilos?|kilogramos?)?", msg)
            kg_val = float(kg_match.group(1).replace(".", "").replace(",", ".")) if kg_match else 4000.0

            moved_kg = min(target_fert["por_retirar_kg"], kg_val)
            target_fert["por_retirar_kg"] -= moved_kg
            target_fert["en_galpon_kg"] += moved_kg

            tot_g_kg = sum(f["en_galpon_kg"] for f in ferts)
            tot_r_kg = sum(f["por_retirar_kg"] for f in ferts)
            insumos_json["fertilizantes_totales"] = {
                "en_galpon_kg": tot_g_kg,
                "por_retirar_kg": tot_r_kg,
                "total_general_kg": tot_g_kg + tot_r_kg
            }

            _, meta_w = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)

            motivo = f"Traslado de {int(moved_kg):,} kg de {target_fert['nombre']} desde {target_fert['lugar_retiro']} al Galpón Central"
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"🧪 **Traslado de Fertilizante Asentado (en Kilogramos):**\n\n"
                f"- **Producto:** **{target_fert['nombre']}** ({target_fert['formula']}).\n"
                f"- **Kilogramos trasladados al galpón:** **{int(moved_kg):,} kg**.\n"
                f"- **Origen:** *{target_fert['lugar_retiro']}*.\n"
                f"- **Stock actual del fertilizante:**\n"
                f"  • 🏠 **En Galpón:** **{int(target_fert['en_galpon_kg']):,} kg** ({round(target_fert['en_galpon_kg']/1000.0, 1)} Tn).\n"
                f"  • 📍 **Por Retirar en distribuidor:** **{int(target_fert['por_retirar_kg']):,} kg** en *{target_fert['lugar_retiro']}*.\n"
                f"  • **Total del fertilizante:** {int(target_fert['total_kg']):,} kg ({round(target_fert['total_kg']/1000.0, 1)} Tn).\n\n"
                f"📊 **Totales consolidados de Fertilizantes:**\n"
                f"• En Galpón: **{int(tot_g_kg):,} kg** | Por Retirar: **{int(tot_r_kg):,} kg** | **Total General: {int(tot_g_kg + tot_r_kg):,} kg**."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        else:
            reply = _build_fertilizantes_query_reply(user_message, executed_tools)
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 5. CASO INSUMOS Y FITOSANITARIOS (DOS OPCIONES: EN GALPÓN O A RETIRAR)
    # ==============================================================
    elif is_fito_flag:
        insumos_raw, meta_ins = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        executed_tools.append(meta_ins)
        insumos_json = json.loads(insumos_raw)
        fitos = insumos_json.get("fitosanitarios", [])

        is_moving_fito = any(w in msg for w in ["retiré", "retire", "retiramos", "trajimos", "traje", "trasladamos", "pasar"]) and any(w in msg for w in ["galpon", "galpón", "planta", "agroquimica", "agroquímica", "corteva", "rizobacter", "fmc"])
        is_query_fito = any(w in msg for w in ["?", "¿", "cuanto", "cuánto", "saldo", "stock", "estado", "listar", "ver", "tenemos", "informe", "opciones", "opcion", "opción", "aparezca", "aparezcan"]) or msg.strip().startswith("que ") or msg.strip().startswith("qué ")

        target_fito = fitos[0]
        if "2,4-d" in msg or "enlist" in msg:
            target_fito = next((f for f in fitos if "2,4-D" in f["nombre"]), fitos[1])
        elif "coadyuvante" in msg:
            target_fito = next((f for f in fitos if "Coadyuvante" in f["nombre"]), fitos[2])
        elif "coragen" in msg:
            target_fito = next((f for f in fitos if "Coragen" in f["nombre"]), fitos[3])

        if is_moving_fito and not is_query_fito:
            l_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|l )?", msg)
            l_val = float(l_match.group(1).replace(".", "").replace(",", ".")) if l_match else 200.0

            moved_l = min(target_fito["a_retirar"], l_val)
            target_fito["a_retirar"] -= moved_l
            target_fito["en_galpon"] += moved_l

            tot_g_l = sum(f["en_galpon"] for f in fitos)
            tot_r_l = sum(f["a_retirar"] for f in fitos)
            insumos_json["fitosanitarios_totales"] = {
                "en_galpon_litros": tot_g_l,
                "a_retirar_litros": tot_r_l,
                "total_general_litros": tot_g_l + tot_r_l
            }

            _, meta_w = execute_native_tool("write_file", {"filename": "stock_insumos.json", "content": json.dumps(insumos_json, indent=2, ensure_ascii=False)})
            executed_tools.append(meta_w)

            motivo = f"Traslado de {int(moved_l):,} L de {target_fito['nombre']} desde {target_fito['lugar_retiro']} al Galpón Central"
            _, meta_m = execute_native_tool("append_memory", {"entry": motivo})
            executed_tools.append(meta_m)

            reply = (
                f"📦 **Traslado de Insumos al Galpón Asentado:**\n\n"
                f"- **Producto:** **{target_fito['nombre']}** ({target_fito['tipo']}).\n"
                f"- **Litros ingresados al galpón:** **{int(moved_l):,} L**.\n"
                f"- **Origen:** *{target_fito['lugar_retiro']}*.\n"
                f"- **Stock actual:**\n"
                f"  • 🏠 **En Galpón:** **{int(target_fito['en_galpon']):,} Litros**.\n"
                f"  • 📍 **A Retirar remanente:** **{int(target_fito['a_retirar']):,} Litros** en *{target_fito['lugar_retiro']}*.\n"
                f"  • **Total disponible:** {int(target_fito['total']):,} Litros.\n\n"
                f"📊 **Totales consolidados:** {int(tot_g_l):,} L en galpón | {int(tot_r_l):,} L a retirar."
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        else:
            reply = _build_fitosanitarios_query_reply(user_message, executed_tools)
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 6. CASO RENDIMIENTOS Y LOTES
    # ==============================================================
    elif any(w in msg for w in ["rinde", "rendimiento", "cosecha", "trilla", "qq"]) and not any(w in msg for w in ["gasoil", "combustible"]):
        _, meta = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.append(meta)

        reply = (
            f"🌾 **Rendimientos y Datos de Cosecha (Campaña 2026/2027):**\n\n"
            f"- **Lote 1 (Soja 1ra - 120 ha):** En siembra activa. Rinde proyectado: 3.800 kg/ha (38 qq/ha).\n"
            f"- **Lote 2 (Maíz Tardío - 85 ha):** En barbecho. Rinde objetivo: 9.500 kg/ha (95 qq/ha).\n"
            f"- **Lote 3 (Trigo Cosechado - 210 ha):** Total: 819.000 kg (**3.900 kg/ha / 39 qq/ha**), almacenado en silobolsa norte y silo planta.\n\n"
            f"Datos consolidados en los registros de lotes."
        )
        append_to_history(user_message, reply, executed_tools)
        return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

    # ==============================================================
    # 7. COMBUSTIBLES (GASOIL): RETIRO / GASTO / TRANSFERENCIA
    # ==============================================================
    gasoil_raw, meta_g_read = execute_native_tool("read_file", {"filename": "stock_gasoil.json"})
    executed_tools.append(meta_g_read)
    gasoil_json = json.loads(gasoil_raw)
    deps = gasoil_json["depositos"]

    # Detectar labor de siembra combinada (insumos soja + combustible)
    has_real_bags = bool(re.search(r"(?<!silo) bolsas? ", msg))
    is_sowing_soy = any(w in msg for w in ["sembr", "siembra", "sembrando"]) and any(w in msg for w in ["soja", "dm46"]) and (has_real_bags or any(w in msg for w in ["ha", "hect", "lote"])) and not is_grain_silo_query_or_action
    is_purchase = any(w in msg for w in ["llegó", "llego", "compra", "compramos", "descargaron", "descarga", "entró", "entro", "remito"]) and not any(w in msg for w in ["gaste", "gasté", "gastamos", "retire", "retiré", "saque", "saqué", "consum", "salida", "descont"])
    is_transfer = is_fuel_transfer_or_acopio(user_message)

    has_numbers = any(char.isdigit() for char in user_message)
    has_fuel_word = any(w in msg for w in ["litros", "lts", "lt", "gasoil", "diesel", "combustible", "combustibles", "nafta"])
    has_spending_stem = any(w in msg for w in [
        "gast", "consum", "retir", "saqu", "sacar", "saco", "descont", "baj", "rest", "chup", "salida"
    ])
    is_question_query = any(w in msg for w in ["?", "¿", "cuanto", "cuánto", "cuántos", "cuantos", "saldo", "estado", "listar", "informe", "ver saldo"]) or msg.strip().startswith("que ") or msg.strip().startswith("qué ")
    has_spending_action = (has_spending_stem and has_numbers) or (has_spending_stem and (has_fuel_word or "tanque" in msg or "cisterna" in msg) and not is_question_query)
    is_fuel_query = is_question_query or (any(w in msg for w in ["saldo", "stock", "estado", "listar", "ver", "tenemos", "informe"]) and not has_spending_action)
    has_spending_verb = has_spending_action or ((not is_fuel_query) and (
        has_spending_stem or
        (has_fuel_word and has_numbers) or
        ("tanque" in msg and has_numbers)
    ))

    if is_sowing_soy:
        insumos_raw, meta_i = execute_native_tool("read_file", {"filename": "stock_insumos.json"})
        lotes_raw, meta_l = execute_native_tool("read_file", {"filename": "registro_lotes.json"})
        executed_tools.extend([meta_i, meta_l])

        insumos = json.loads(insumos_raw)
        lotes = json.loads(lotes_raw)

        from .agronomic_engine import calculate_fuel_consumption, calculate_seed_consumption

        has_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:hect[áa]reas?|has? )", msg)
        has_done = float(has_match.group(1).replace(".", "").replace(",", ".")) if has_match else 25.0

        has_explicit_liters = bool(re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:litros?|lts?|lt\b)", msg))
        user_liters = extract_liters(user_message, default=0.0) if has_explicit_liters else None
        fuel_calc = calculate_fuel_consumption(
            labor_type="Siembra",
            hectares=has_done,
            crop_key="soja_primera",
            user_specified_liters=user_liters
        )
        liters_out = fuel_calc["litros_finales"]

        seeds_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*(?:bolsas?|bolsa )", msg)
        user_bags = int(float(seeds_match.group(1).replace(".", "").replace(",", "."))) if seeds_match else None
        seed_calc = calculate_seed_consumption("soja_primera", has_done, user_specified_bags=user_bags)
        bolsas_out = seed_calc["bolsas_finales"]

        tank_key = identify_tank(user_message)
        if tank_key == "acopio_por_retirar":
            tank_key = "tanque_grande"

        current_fuel = deps[tank_key]["stock_actual_litros"]
        if liters_out > current_fuel:
            reply = (
                f"❌ **No es posible realizar la labor porque no hay stock suficiente de combustible.**\n\n"
                f"- **Depósito:** **{deps[tank_key]['nombre']}**\n"
                f"- **Stock disponible:** **{int(current_fuel):,} Litros**\n"
                f"- **Requerido para la labor:** **{int(liters_out):,} Litros**\n\n"
                f"⚠️ *Por favor recarga el depósito o utiliza otro tanque con saldo suficiente.*"
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        current_seeds = sj_variedades[0].get("en_planta_bolsas", 0) if sj_variedades else 0
        if bolsas_out > current_seeds:
            reply = (
                f"❌ **No es posible realizar la siembra porque no hay stock suficiente de semillas de soja.**\n\n"
                f"- **Variedad:** **DM 46R18**\n"
                f"- **Disponible en galpón:** **{current_seeds} bolsas**\n"
                f"- **Requerido para la siembra:** **{bolsas_out} bolsas**\n\n"
                f"⚠️ *No es posible gastar más semillas de las disponibles en galpón.*"
            )
            append_to_history(user_message, reply, executed_tools)
            return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

        deps[tank_key]["stock_actual_litros"] = current_fuel - liters_out

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
            tank_target = identify_tank(user_message)
            if tank_target == "acopio_por_retirar":
                tank_target = "cisterna_planta"
            deps[tank_target]["stock_actual_litros"] = min(
                deps[tank_target]["capacidad_max_litros"],
                deps[tank_target]["stock_actual_litros"] + liters_in
            )
            descrip = f"Ingreso de {int(liters_in):,} L descargados en {deps[tank_target]['nombre']}"

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
            "remito": "REM-YPF-2026-NUEVO",
            "descripcion": descrip,
            "litros": liters_in,
            "operario": sender_name
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
        liters_to_move = extract_liters(user_message, default=1000.0)

        is_from_acopio = any(w in msg for w in ["acopio", "acpio", "acoppio", "externo", "exteno", "ypf", "distribuidor", "por retirar"])

        if is_from_acopio:
            origen_key = "acopio_por_retirar"
            destino_key = identify_destination_tank(user_message, default="cisterna_planta")
            actual_acopio = deps["acopio_por_retirar"]["litros_disponibles"]

            # Validación estricta de stock en acopio externo
            if liters_to_move > actual_acopio:
                reply = (
                    f"❌ **No es posible realizar el retiro porque no hay stock suficiente en el acopio externo.**\n\n"
                    f"- **Stock disponible en acopio YPF:** **{int(actual_acopio):,} Litros**\n"
                    f"- **Intentaste retirar:** **{int(liters_to_move):,} Litros**\n\n"
                    f"⚠️ *No es posible retirar más combustible del disponible en el acopio externo.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

            espacio_libre = deps[destino_key]["capacidad_max_litros"] - deps[destino_key]["stock_actual_litros"]
            if liters_to_move > espacio_libre:
                # Si el usuario no especificó tanque y se desborda, probar cisterna_planta si tiene espacio
                if not any(w in msg for w in ["chico", "grande", "cisterna", "planta"]) and (deps["cisterna_planta"]["capacidad_max_litros"] - deps["cisterna_planta"]["stock_actual_litros"]) >= liters_to_move:
                    destino_key = "cisterna_planta"
                else:
                    reply = (
                        f"❌ **El depósito de destino ({deps[destino_key]['nombre']}) no tiene suficiente capacidad.**\n\n"
                        f"- **Capacidad máxima:** **{int(deps[destino_key]['capacidad_max_litros']):,} Litros**\n"
                        f"- **Stock actual:** **{int(deps[destino_key]['stock_actual_litros']):,} Litros**\n"
                        f"- **Espacio libre para guardar:** **{int(espacio_libre):,} Litros**\n\n"
                        f"⚠️ *No es posible guardar {int(liters_to_move):,} L sin exceder la capacidad física del tanque.*"
                    )
                    append_to_history(user_message, reply, executed_tools)
                    return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

            liters_moved = liters_to_move
            deps["acopio_por_retirar"]["litros_disponibles"] -= liters_moved
            deps[destino_key]["stock_actual_litros"] += liters_moved
            motivo = f"Retiro de {int(liters_moved):,} L de acopio YPF hacia {deps[destino_key]['nombre']}"

            # Impacto atómico en base de datos relacional y sincronización con Google Drive
            try:
                from app.services.stock_service import StockIntegrityService
                StockIntegrityService.registrar_retiro_acopio_combustible(
                    litros=liters_moved,
                    destino_codigo=destino_key,
                    operario=sender_name,
                    observaciones=motivo
                )
            except Exception as e:
                print(f"Error registrando retiro acopio combustible en DB: {e}")

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

            actual_origen = deps[origen_key]["stock_actual_litros"]
            if liters_to_move > actual_origen:
                reply = (
                    f"❌ **No es posible realizar la transferencia porque no hay stock suficiente en {deps[origen_key]['nombre']}.**\n\n"
                    f"- **Stock disponible en origen:** **{int(actual_origen):,} Litros**\n"
                    f"- **Intentaste transferir:** **{int(liters_to_move):,} Litros**\n\n"
                    f"⚠️ *No es posible transferir más combustible del disponible en el depósito de origen.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

            espacio_libre = deps[destino_key]["capacidad_max_litros"] - deps[destino_key]["stock_actual_litros"]
            if liters_to_move > espacio_libre:
                reply = (
                    f"❌ **El depósito de destino ({deps[destino_key]['nombre']}) no tiene suficiente capacidad.**\n\n"
                    f"- **Capacidad máxima:** **{int(deps[destino_key]['capacidad_max_litros']):,} Litros**\n"
                    f"- **Stock actual:** **{int(deps[destino_key]['stock_actual_litros']):,} Litros**\n"
                    f"- **Espacio libre:** **{int(espacio_libre):,} Litros**\n\n"
                    f"⚠️ *No es posible transferir {int(liters_to_move):,} L sin exceder la capacidad del tanque.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

            liters_moved = liters_to_move
            deps[origen_key]["stock_actual_litros"] -= liters_moved
            deps[destino_key]["stock_actual_litros"] += liters_moved
            motivo = f"Transferencia interna de {int(liters_moved):,} L desde {deps[origen_key]['nombre']} hacia {deps[destino_key]['nombre']}"

            # Impacto atómico en DB y sincronización con Google Drive
            try:
                from app.services.stock_service import StockIntegrityService
                StockIntegrityService.registrar_traslado_combustible(
                    litros=liters_moved,
                    origen_codigo=origen_key,
                    destino_codigo=destino_key,
                    operario=sender_name,
                    observaciones=motivo
                )
            except Exception as e:
                print(f"Error registrando traslado de combustible en DB: {e}")

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

        tot_campo = gasoil_json["totales"]["stock_fisico_campo_litros"]
        tot_gral = gasoil_json["totales"]["stock_total_con_acopio_litros"]
        reply = (
            f"Perfecto, ya registré lo que pediste.\n\n"
            f"⛽ **Resumen del Movimiento de Combustible:**\n"
            f"• **Operación:** {motivo}\n"
            f"• **Depósito origen:** {deps[origen_key]['nombre']} (-{int(liters_moved):,} L)\n"
            f"• **Depósito destino:** {deps[destino_key]['nombre']} (+{int(liters_moved):,} L)\n"
            f"• **Operario:** {sender_name}\n\n"
            f"📊 **Total de combustible que queda:**\n"
            f"• 🏭 **Cisterna Planta:** **{int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L**\n"
            f"• 🚜 **Tanque Grande:** **{int(deps['tanque_grande']['stock_actual_litros']):,} / 5.000 L**\n"
            f"• 🛢️ **Tanque Chico:** **{int(deps['tanque_chico']['stock_actual_litros']):,} / 3.000 L**\n"
            f"• 📋 **Gasoil por Retirar (Acopio YPF):** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} L**\n\n"
            f"👉 **Total físico en campo:** **{int(tot_campo):,} Litros** | **Total con acopio:** **{int(tot_gral):,} Litros**."
        )

    elif has_spending_action or has_spending_verb or (has_fuel_word and has_numbers and not is_fuel_query) or ("tanque" in msg and has_numbers and not is_fuel_query):
        liters_out = extract_liters(user_message, default=300.0)

        # Identificar si el usuario mencionó un tanque explícito
        has_explicit_tank = any(w in msg for w in [
            "chico", "chiquito", "pequeño", "pequeno", "carretón", "carreton", "3000", "3.000", "auxilio",
            "planta", "central", "22000", "22.000", "cisterna",
            "grande", "5000", "5.000", "móvil", "movil",
            "acopio", "ypf", "distribuidor", "por retirar"
        ])

        if has_explicit_tank:
            tank_key = identify_tank(user_message)
        else:
            # Seleccionar automáticamente el tanque que tenga stock suficiente disponible
            tg_stk = float(deps.get("tanque_grande", {}).get("stock_actual_litros", 0))
            cp_stk = float(deps.get("cisterna_planta", {}).get("stock_actual_litros", 0))
            tc_stk = float(deps.get("tanque_chico", {}).get("stock_actual_litros", 0))

            if tg_stk >= liters_out:
                tank_key = "tanque_grande"
            elif cp_stk >= liters_out:
                tank_key = "cisterna_planta"
            elif tc_stk >= liters_out:
                tank_key = "tanque_chico"
            else:
                # Si ninguno cubre el gasto de forma completa, elegir el de mayor saldo para que el validador informe con precisión
                tank_key = max({"cisterna_planta": cp_stk, "tanque_grande": tg_stk, "tanque_chico": tc_stk}, key=lambda k: deps[k]["stock_actual_litros"])

        if tank_key == "acopio_por_retirar":
            target_field = "cisterna_planta"
            actual_acopio = deps["acopio_por_retirar"]["litros_disponibles"]
            if liters_out > actual_acopio:
                reply = (
                    f"❌ **No es posible realizar el retiro porque no hay stock suficiente en Acopio YPF.**\n\n"
                    f"- **Stock disponible en Acopio:** **{int(actual_acopio):,} Litros**\n"
                    f"- **Intentaste retirar:** **{int(liters_out):,} Litros**\n\n"
                    f"⚠️ *No es posible retirar una cantidad superior a los litros pendientes en acopio.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}
            liters_moved = liters_out
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

            try:
                from .google_sheets_service import on_movement_recorded
                on_movement_recorded()
            except Exception:
                pass

            tot_campo = gasoil_json["totales"]["stock_fisico_campo_litros"]
            tot_gral = gasoil_json["totales"]["stock_total_con_acopio_litros"]
            reply = (
                f"Perfecto, ya registré lo que pediste.\n\n"
                f"⛽ **Resumen del Movimiento de Combustible:**\n"
                f"• **Operación:** {motivo}\n"
                f"• **Volumen retirado:** {int(liters_moved):,} Litros de Acopio YPF Directo\n"
                f"• **Depósito destino:** Cisterna Planta (+{int(liters_moved):,} L)\n"
                f"• **Operario:** {sender_name}\n\n"
                f"📊 **Total de combustible que queda:**\n"
                f"• 🏭 **Cisterna Planta:** **{int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L**\n"
                f"• 🚜 **Tanque Grande:** **{int(deps['tanque_grande']['stock_actual_litros']):,} / 5.000 L**\n"
                f"• 🛢️ **Tanque Chico:** **{int(deps['tanque_chico']['stock_actual_litros']):,} / 3.000 L**\n"
                f"• 📋 **Gasoil por Retirar (Acopio YPF):** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} L**\n\n"
                f"👉 **Total físico en campo:** **{int(tot_campo):,} Litros** | **Total con acopio:** **{int(tot_gral):,} Litros**."
            )
        else:
            current_tank_stock = deps[tank_key]["stock_actual_litros"]
            if liters_out > current_tank_stock:
                tot_fisico = float(gasoil_json["totales"]["stock_fisico_campo_litros"])
                reply = (
                    f"❌ **No es posible realizar la operación porque no hay stock suficiente.**\n\n"
                    f"- **Depósito:** **{deps[tank_key]['nombre']}**\n"
                    f"- **Stock disponible en este depósito:** **{int(current_tank_stock):,} Litros**\n"
                    f"- **Intentaste gastar/retirar:** **{int(liters_out):,} Litros**\n"
                    f"- **Stock físico total en campo:** **{int(tot_fisico):,} Litros**\n\n"
                    f"⚠️ *No es posible gastar más combustible del disponible en este depósito.*"
                )
                append_to_history(user_message, reply, executed_tools)
                return {"response": reply, "tool_calls": executed_tools, "is_demo": True, "stock_data": get_dashboard_summary()}

            # Impactar descuento en memoria de cálculo
            deps[tank_key]["stock_actual_litros"] = round(current_tank_stock - liters_out, 1)

            gasoil_json["totales"]["stock_fisico_campo_litros"] = (
                deps["cisterna_planta"]["stock_actual_litros"] +
                deps["tanque_grande"]["stock_actual_litros"] +
                deps["tanque_chico"]["stock_actual_litros"]
            )
            gasoil_json["totales"]["stock_total_con_acopio_litros"] = (
                gasoil_json["totales"]["stock_fisico_campo_litros"] +
                deps["acopio_por_retirar"]["litros_disponibles"]
            )

            machinery = "Uso operativo general"
            if "tractor" in msg:
                machinery = "Tractor John Deere"
            elif "cosechadora" in msg or "trilla" in msg:
                machinery = "Cosechadora"
            elif "pulverizadora" in msg or "mosquito" in msg:
                machinery = "Pulverizadora"
            elif "camioneta" in msg or "chata" in msg:
                machinery = "Camioneta"

            labor_desc = "Consumo general de combustible"
            if any(w in msg for w in ["labor", "trabajo", "tarea", "campo"]):
                labor_desc = "Labor operativa de campo"
            elif any(w in msg for w in ["viaje", "traslado", "recorrida"]):
                labor_desc = "Recorrida operativa / Traslado"

            # 1. Registrar salida en stock_gasoil.json
            gasoil_json.setdefault("salidas", []).append({
                "fecha": today_str,
                "deposito_origen": deps[tank_key]["nombre"],
                "maquinaria": machinery,
                "labor": labor_desc,
                "litros": liters_out,
                "operario": sender_name
            })

            _, w_g = execute_native_tool("write_file", {"filename": "stock_gasoil.json", "content": json.dumps(gasoil_json, indent=2, ensure_ascii=False)})
            executed_tools.append(w_g)

            # 2. Registrar en MEMORY.md
            entry_mem = f"Consumo general registrado ({machinery}) por {sender_name}: -{int(liters_out):,} L de {deps[tank_key]['nombre']}. Saldo restante: {int(deps[tank_key]['stock_actual_litros']):,} L."
            _, w_m = execute_native_tool("append_memory", {"entry": entry_mem})
            executed_tools.append(w_m)

            # 3. Asentar atómicamente en Base de Datos Relacional Django (MovimientoStock)
            try:
                from .stock_service import StockIntegrityService
                from app.models import Deposito, Insumo, MovimientoStock
                from django.utils import timezone

                dep_obj = Deposito.objects.filter(codigo=tank_key).first()
                if dep_obj:
                    dep_obj.stock_actual = max(0.0, float(dep_obj.stock_actual) - liters_out)
                    dep_obj.save(update_fields=["stock_actual"])

                insumo_gasoil = StockIntegrityService.get_or_create_gasoil_insumo()
                insumo_gasoil.stock_actual = max(0.0, float(insumo_gasoil.stock_actual) - liters_out)
                insumo_gasoil.save(update_fields=["stock_actual"])

                MovimientoStock.objects.create(
                    insumo=insumo_gasoil,
                    tipo_movimiento="consumo_labor",
                    estado="confirmado",
                    cantidad=liters_out,
                    fecha=timezone.now().date(),
                    deposito_origen_fk=dep_obj,
                    deposito_origen=deps[tank_key]["nombre"],
                    labor_realizada=labor_desc,
                    maquinaria=machinery,
                    operario=sender_name,
                    saldo_anterior=current_tank_stock,
                    saldo_posterior=deps[tank_key]["stock_actual_litros"],
                    observaciones=f"Gasto directo registrado por {sender_name}: {user_message}"
                )
            except Exception as e_bd:
                logger.error(f"Error registrando movimiento en BD: {e_bd}")

            # 4. Sincronizar automáticamente hojas de cálculo y Google Drive
            try:
                from .google_sheets_service import on_movement_recorded
                on_movement_recorded()
            except Exception as e_sync:
                logger.error(f"Error sincronizando hojas Google Drive: {e_sync}")

            pct_filled = round((deps[tank_key]["stock_actual_litros"] / deps[tank_key]["capacidad_max_litros"]) * 100)

            tot_campo = gasoil_json["totales"]["stock_fisico_campo_litros"]
            tot_gral = gasoil_json["totales"]["stock_total_con_acopio_litros"]
            reply = (
                f"Perfecto, ya registré lo que pediste.\n\n"
                f"⛽ **Resumen del Movimiento de Combustible:**\n"
                f"• **Operación:** Retiro de combustible ({int(liters_out):,} Litros)\n"
                f"• **Depósito de origen:** {deps[tank_key]['nombre']}\n"
                f"• **Destino / Maquinaria:** {machinery}\n"
                f"• **Operario:** {sender_name}\n\n"
                f"📊 **Total de combustible que queda:**\n"
                f"• 🛢️ **Saldo restante en {deps[tank_key]['nombre']}:** **{int(deps[tank_key]['stock_actual_litros']):,} Litros** ({pct_filled}% lleno)\n"
                f"• 🏭 **Cisterna Planta:** **{int(deps['cisterna_planta']['stock_actual_litros']):,} / 22.000 L**\n"
                f"• 🚜 **Tanque Grande:** **{int(deps['tanque_grande']['stock_actual_litros']):,} / 5.000 L**\n"
                f"• 🛢️ **Tanque Chico:** **{int(deps['tanque_chico']['stock_actual_litros']):,} / 3.000 L**\n"
                f"• 📋 **Gasoil por Retirar (Acopio YPF):** **{int(deps['acopio_por_retirar']['litros_disponibles']):,} L**\n\n"
                f"👉 **Total físico en campo:** **{int(tot_campo):,} Litros** | **Total con acopio:** **{int(tot_gral):,} Litros**."
            )

    elif is_fuel_context or any(w in msg for w in ["gasoil", "gas oil", "combustible", "combustibles", "diesel", "gas-oil", "tanque", "cisterna", "acopio"]):
        reply = _build_combustible_query_reply(user_message, executed_tools)
        append_to_history(user_message, reply, executed_tools)
        return {
            "response": reply,
            "tool_calls": executed_tools,
            "is_demo": True,
            "stock_data": get_dashboard_summary()
        }
    elif any(w in msg for w in ["hoja", "hojas", "calculo", "cálculo", "drive", "google drive", "excel", "spreadsheet", "link", "subilas", "carpeta"]):
        try:
            from .sheets_export_service import generate_consolidated_workbook
            xlsx_path = generate_consolidated_workbook()
        except Exception as e:
            print(f"Error generando hojas: {e}")

        folder_url = "https://drive.google.com/drive/folders/11XiJ4FtA-8KOU3BvZWr6yDbxOwVoUvkw?usp=sharing"
        reply = (
            f"📊 **Hojas de Cálculo Generadas y Vinculadas Online:**\n\n"
            f"Se ha estructurado el libro maestro consolidado para tu carpeta compartida de Google Drive:\n"
            f"🔗 **Carpeta Destino en Drive:** [{folder_url}]({folder_url})\n\n"
            f"📋 **Estructura de las 7 Hojas de Cálculo Generadas:**\n"
            f"1. 📊 **Tablero General:** Visión global y métricas consolidadas del establecimiento.\n"
            f"2. ⛽ **Combustibles:** Cisterna Planta (22.000 L), Tanque Grande (5.000 L), Tanque Chico (3.000 L), Acopio YPF, salidas y transferencias.\n"
            f"3. 🧪 **Fertilizantes (en kg):** MAP, Urea y MicroEssentials en kilogramos, con existencias en Galpón y Por Retirar en comercios específicos (YPF Agro Junín, ACA Junín, Bunge Pergamino).\n"
            f"4. 📦 **Insumos y Fitosanitarios:** Glifosato, 2,4-D, Coadyuvante y Coragen con dos opciones claras: En Galpón o A Retirar en comercio determinado.\n"
            f"5. 🌽 **Semillas de Maíz:** Híbridos Dekalb, Pioneer y Nidera en bolsas (en Planta vs por retirar).\n"
            f"6. 🌾 **Granos en Silos (Tn):** Soja y Trigo en toneladas por silobolsa y silo de chapa, con humedad y calidad comercial.\n"
            f"7. 📝 **Bitácora de Labores:** Registro histórico de movimientos asentados por la IA.\n\n"
            f"🔄 **Sincronización Dinámica Activa:**\n"
            f"Cada vez que informes un movimiento, retiro o consumo en IA Desk, los archivos maestros se recalculan y actualizan automáticamente al instante.\n"
            f"📥 Puedes descargar el archivo listo desde el panel superior o directamente en: [Descargar Excel Consolidado](/api/sheets/download/)."
        )

    else:
        summary = get_dashboard_summary()
        reply = (
            f"🚜 **IA Desk Agro - Copiloto de Operaciones:**\n\n"
            f"He verificado los registros generales del establecimiento:\n"
            f"- **Silos Principales (5 unidades):** {summary['granos_silos']['stock_principales_tn']} / {summary['granos_silos']['capacidad_principales_tn']} Tn.\n"
            f"- **Silos de Trilla (2 unidades):** {summary['granos_silos']['stock_trilla_tn']} / {summary['granos_silos']['capacidad_trilla_tn']} Tn.\n"
            f"- **Fertilizantes:** {int(summary['fertilizantes_totales']['total_general_kg']):,} kg disponibles.\n"
            f"- **Insumos/Fitosanitarios:** {int(summary['fitosanitarios_totales']['total_general_litros']):,} L disponibles.\n"
            f"- **Semillas de Maíz:** {summary['semillas_maiz']} bolsas totales.\n\n"
            f"¿Qué labor, movimiento de insumos, fertilizantes, silos o combustible deseas consultar o registrar?"
        )

    append_to_history(user_message, reply, executed_tools)
    return {
        "response": reply,
        "tool_calls": executed_tools,
        "is_demo": True,
        "stock_data": get_dashboard_summary()
    }
