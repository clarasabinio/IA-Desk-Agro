import json
import csv
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.conf import settings

# Paletas de color por cultivo
THEMES = {
    "maiz": {
        "title": "MAÍZ - CONTROL INTEGRAL DE LABORES POR CAMPO Y LOTE",
        "header_fill": PatternFill(start_color="B45309", end_color="B45309", fill_type="solid"), # Ámbar dorado maíz
        "sub_fill": PatternFill(start_color="D97706", end_color="D97706", fill_type="solid"),
        "total_fill": PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"),
        "icon": "🌽",
        "color_title": "B45309"
    },
    "soja_primera": {
        "title": "SOJA DE PRIMERA - CONTROL DE LABORES POR CAMPO Y LOTE",
        "header_fill": PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid"), # Verde esmeralda soja
        "sub_fill": PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid"),
        "total_fill": PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid"),
        "icon": "🌱",
        "color_title": "1B5E20"
    },
    "soja_segunda": {
        "title": "SOJA DE SEGUNDA - CONTROL DE LABORES POR CAMPO Y LOTE",
        "header_fill": PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid"), # Verde azulado / teal
        "sub_fill": PatternFill(start_color="14B8A6", end_color="14B8A6", fill_type="solid"),
        "total_fill": PatternFill(start_color="CCFBF1", end_color="CCFBF1", fill_type="solid"),
        "icon": "🌿",
        "color_title": "0F766E"
    },
    "trigo": {
        "title": "TRIGO PAN - CONTROL DE LABORES Y COSECHA POR CAMPO Y LOTE",
        "header_fill": PatternFill(start_color="92400E", end_color="92400E", fill_type="solid"), # Dorado trigo maduro
        "sub_fill": PatternFill(start_color="B45309", end_color="B45309", fill_type="solid"),
        "total_fill": PatternFill(start_color="FDE68A", end_color="FDE68A", fill_type="solid"),
        "icon": "🌾",
        "color_title": "92400E"
    }
}

HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
BOLD_FONT = Font(name="Calibri", size=10, bold=True, color="000000")
REGULAR_FONT = Font(name="Calibri", size=10, color="000000")
SMALL_FONT = Font(name="Calibri", size=9, italic=True, color="555555")

THIN_SIDE = Side(border_style="thin", color="CCCCCC")
DOUBLE_BOTTOM = Side(border_style="double", color="333333")
BORDER_CELL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
BORDER_TOTAL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=DOUBLE_BOTTOM)

HEADERS_LABORES = [
    "FECHA",
    "LOTE",
    "SUPERFICIE (HA)",
    "LABOR REALIZADA",
    "MAQUINARIA / EQUIPO",
    "OPERARIO",
    "GASOIL (L)",
    "DEPÓSITO ORIGEN",
    "SEMILLA USADA",
    "FERTILIZANTE (KG)",
    "INSUMOS / FITO (L)",
    "RINDE / COSECHA",
    "ESTADO / OBSERVACIONES"
]

def auto_adjust_columns(ws, min_width=12):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if chr(10) in val_str:
                val_str = max(val_str.split(chr(10)), key=len)
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(min(max_len + 3, 40), min_width)

def get_lotes_data() -> Dict[str, Any]:
    path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def get_base_labores_rows(crop_key: str, campo_nombre: str) -> List[List[Any]]:
    """Retorna las labores históricas de base para cada cultivo y campo"""
    if crop_key == "maiz":
        if campo_nombre == "La Esperanza":
            return [
                ["2026-09-20", "Lote 2", 85, "Barbecho Químico Primavera", "Pla MAP 3 3300", "Esteban", 120, "Tanque Chico", "-", "-", "Glifosato (255 L) + 2,4-D (68 L)", "-", "Barbecho limpio"],
                ["2026-10-02", "Lote 2", 85, "Pasada de Rastra de Discos", "John Deere 7200R + Disco Excéntrico", "Juan González", 280, "Tanque Grande", "-", "-", "-", "-", "Cama de siembra nivelada"],
                ["2026-10-08", "Lote 2", 45, "Siembra Maíz Dekalb", "JD 7200R + Crucianelli 27 líneas", "Juan González", 200, "Tanque Grande", "DK 72-10 (60 bolsas)", "MAP (4.500 kg)", "-", "-", "Siembra en fecha óptima"],
                ["2026-10-09", "Lote 2", 40, "Siembra Maíz (Cierre lote)", "JD 7200R + Crucianelli 27 líneas", "Juan González", 150, "Tanque Grande", "DK 72-10 (50 bolsas)", "MAP (4.000 kg)", "-", "-", "Lote 2 100% completado"]
            ]
        elif campo_nombre == "El Ombu":
            return [
                ["2026-09-18", "Lote Norte A", 95, "Pasada de Disco y Cincel", "Tractor John Deere + Rastra", "Esteban", 340, "Tanque Grande", "-", "-", "-", "-", "Descompactación previa"],
                ["2026-10-04", "Lote Norte A", 95, "Siembra Maíz Temprano", "JD 7200R + Crucianelli", "Juan González", 310, "Cisterna Planta", "Pioneer P2089 (125 bolsas)", "MicroEssentials (9.500 kg)", "-", "-", "Implantación excelente"],
                ["2026-10-10", "Lote Norte A", 95, "Refertilización Nitrogenada", "Fertilizadora al voleo Altina", "Esteban", 200, "Tanque Chico", "-", "Urea Granulada (11.400 kg)", "-", "-", "Incorporado con lluvia"]
            ]
        else: # San Jose
            return [
                ["2026-09-25", "Lote Sur 3", 75, "Barbecho y Control Malezas", "Pulverizadora Pla MAP 3", "Esteban", 110, "Tanque Chico", "-", "-", "Glifosato (225 L) + Coadyuvante", "-", "Control maleza difícil"],
                ["2026-10-07", "Lote Sur 3", 75, "Siembra Maíz Tardío Nidera", "JD 7200R + Sembradora", "Juan González", 260, "Tanque Grande", "Nidera AX 7784 (95 bolsas)", "MAP (7.500 kg)", "-", "-", "Siembra con buena humedad"],
                ["2026-10-09", "Lote Sur 3", 75, "Aplicación Insecticida Preventivo", "Pla MAP 3 3300", "Esteban", 95, "Tanque Chico", "-", "-", "Coragen (15 L)", "-", "Protección cogollero"]
            ]

    elif crop_key == "soja_primera":
        if campo_nombre == "La Esperanza":
            return [
                ["2026-09-15", "Lote 1", 120, "Barbecho Químico Total", "Pla MAP 3 3300", "Esteban", 140, "Tanque Chico", "-", "-", "Glifosato (300 L) + 2,4-D (96 L)", "-", "Lote libre de rama negra"],
                ["2026-10-06", "Lote 1", 60, "Siembra Soja 1ra DM46", "JD 7200R + Crucianelli", "Juan González", 280, "Tanque Grande", "DM 46R18 (75 bolsas)", "MicroEssentials (4.800 kg)", "-", "-", "Avanzando en lote 1"],
                ["2026-10-08", "Lote 1", 35, "Siembra Soja 1ra (Continuación)", "JD 7200R + Crucianelli", "Juan González", 160, "Tanque Grande", "DM 46R18 (45 bolsas)", "MicroEssentials (2.800 kg)", "-", "-", "Faltan 25 ha"],
                ["2026-10-10", "Lote 1", 25, "Siembra Soja 1ra (Finalización)", "JD 7200R + Crucianelli", "Juan González", 120, "Tanque Grande", "DM 46R18 (30 bolsas)", "MicroEssentials (2.000 kg)", "-", "-", "Lote 1 sembrado 100%"]
            ]
        elif campo_nombre == "El Ombu":
            return [
                ["2026-09-22", "Lote Norte B", 140, "Pasada de Disco Nivelador", "John Deere 7200R + Disco", "Esteban", 420, "Tanque Grande", "-", "-", "-", "-", "Cama de siembra perfecta"],
                ["2026-10-05", "Lote Norte B", 140, "Siembra Soja Don Mario", "JD 7200R + Crucianelli", "Juan González", 480, "Cisterna Planta", "DM 46R18 (175 bolsas)", "MicroEssentials (11.200 kg)", "-", "-", "Siembra completa"],
                ["2026-10-09", "Lote Norte B", 140, "Aplicación Preemergente", "Pla MAP 3 3300", "Esteban", 180, "Tanque Chico", "-", "-", "Herbicida residual + Coadyuvante", "-", "Lote sellado"]
            ]
        else: # San Jose
            return [
                ["2026-09-28", "Lote Sur 1B", 60, "Barbecho y Acondicionamiento", "Pla MAP 3 3300", "Esteban", 90, "Tanque Chico", "-", "-", "Glifosato (150 L) + 2,4-D (48 L)", "-", "Lote listo"],
                ["2026-10-07", "Lote Sur 1B", 60, "Siembra Soja Primera", "JD 7200R + Crucianelli", "Juan González", 210, "Tanque Grande", "DM 46R18 (75 bolsas)", "MAP (4.800 kg)", "-", "-", "Excelente nacimiento"]
            ]

    elif crop_key == "soja_segunda":
        if campo_nombre == "La Esperanza":
            return [
                ["2026-01-12", "Lote 3", 110, "Control Malezas Post-Trigo", "Pla MAP 3 3300", "Esteban", 120, "Tanque Chico", "-", "-", "Glifosato (275 L) + 2,4-D", "-", "Rastrojo de trigo limpio"],
                ["2026-01-15", "Lote 3", 110, "Siembra Directa Soja 2da", "JD 7200R + Crucianelli", "Juan González", 330, "Tanque Grande", "DM 46R18 (130 bolsas)", "MicroEssentials (4.400 kg)", "-", "-", "Siembra sobre rastrojo trigo"],
                ["2026-02-10", "Lote 3", 110, "Aplicación Insecticida Orugas", "Pla MAP 3 3300", "Esteban", 100, "Tanque Chico", "-", "-", "Coragen (22 L) + Coadyuvante", "-", "Control oruga medidora"]
            ]
        elif campo_nombre == "El Ombu":
            return [
                ["2026-01-14", "Lote Norte C", 65, "Siembra Soja 2da", "JD 7200R + Crucianelli", "Juan González", 195, "Tanque Grande", "DM 46R18 (80 bolsas)", "MAP (2.600 kg)", "-", "-", "Siembra con humedad"],
                ["2026-02-12", "Lote Norte C", 65, "Protección Fitosanitaria", "Pla MAP 3 3300", "Esteban", 70, "Tanque Chico", "-", "-", "Coragen (13 L)", "-", "Monitoreo favorable"]
            ]
        else: # San Jose
            return [
                ["2026-01-18", "Lote Sur 2", 80, "Siembra Directa Soja 2da", "JD 7200R + Sembradora", "Juan González", 240, "Tanque Grande", "DM 46R18 (95 bolsas)", "MAP (3.200 kg)", "-", "-", "Siembra post cosecha fina"],
                ["2026-02-15", "Lote Sur 2", 80, "Fungicida Fin de Ciclo", "Pla MAP 3 3300", "Esteban", 85, "Tanque Chico", "-", "-", "Fungicida estrobirulina", "-", "Sanidad de hoja óptima"]
            ]

    else: # trigo
        if campo_nombre == "La Esperanza":
            return [
                ["2025-05-20", "Lote 3", 210, "Pasada de Disco y Nivelación", "John Deere 7200R + Disco", "Esteban", 630, "Cisterna Planta", "-", "-", "-", "-", "Preparación fina"],
                ["2025-06-05", "Lote 3", 210, "Siembra Trigo Pan Grado 1", "JD 7200R + Crucianelli", "Juan González", 680, "Cisterna Planta", "Trigo Algarrobo (260 bolsas)", "MAP (16.800 kg)", "-", "-", "Densidad 280 pl/m2"],
                ["2025-08-15", "Lote 3", 210, "Refertilización Urea en Macollaje", "Fertilizadora Altina", "Esteban", 210, "Tanque Chico", "-", "Urea Granulada (8.400 kg)", "-", "-", "Antes de lluvia 25 mm"],
                ["2026-01-08", "Lote 3", 110, "Trilla y Cosecha Trigo (Frente 1)", "Cosechadora Case 7250 + Tolva", "Juan González", 450, "Cisterna Planta", "-", "-", "-", "39.2 qq/ha (431 Tn)", "Ingresado a Silobolsa Norte"],
                ["2026-01-10", "Lote 3", 100, "Trilla y Cosecha Trigo (Frente 2)", "Cosechadora Case 7250 + Tolva", "Juan González", 410, "Cisterna Planta", "-", "-", "-", "38.8 qq/ha (388 Tn)", "Ingresado a Silo Chapa Planta"]
            ]
        elif campo_nombre == "El Ombu":
            return [
                ["2025-06-02", "Lote Trigo Norte", 90, "Siembra Trigo Ciclo Intermedio", "JD 7200R + Sembradora", "Juan González", 310, "Tanque Grande", "Trigo (110 bolsas)", "MicroEssentials (7.200 kg)", "-", "-", "Implantación lograda"],
                ["2025-08-20", "Lote Trigo Norte", 90, "Fertilización Nitrogenada", "Altina", "Esteban", 100, "Tanque Chico", "-", "Urea (3.600 kg)", "-", "-", "Buena respuesta macollaje"],
                ["2026-01-05", "Lote Trigo Norte", 90, "Trilla y Cosecha Trigo Norte", "Cosechadora Case 7250", "Esteban", 370, "Tanque Grande", "-", "-", "-", "38.5 qq/ha (346 Tn)", "Entregado a acopio zonal"]
            ]
        else: # San Jose
            return [
                ["2025-06-10", "Lote Sur 1", 110, "Siembra Trigo Ciclo Corto", "JD 7200R + Crucianelli", "Juan González", 360, "Tanque Grande", "Trigo (135 bolsas)", "MAP (8.800 kg)", "-", "-", "Siembra en fecha"],
                ["2025-08-25", "Lote Sur 1", 110, "Fertilización Nitrógeno", "Altina", "Esteban", 120, "Tanque Chico", "-", "Urea (4.400 kg)", "-", "-", "Aporte de rinde y proteína"],
                ["2026-01-07", "Lote Sur 1", 110, "Trilla y Cosecha Trigo Sur", "Cosechadora Case 7250", "Juan González", 440, "Tanque Grande", "-", "-", "-", "39.2 qq/ha (431 Tn)", "Guardado en silobolsa"]
            ]

def get_labores_rows(crop_key: str, campo_nombre: str, lotes_json: dict) -> List[List[Any]]:
    """
    Retorna la lista completa de labores para el cultivo y campo solicitados,
    combinando el historial base con todas las labores registradas dinámicamente en tiempo real.
    """
    rows = [list(r) for r in get_base_labores_rows(crop_key, campo_nombre)]
    existing_keys = { (str(r[0]), str(r[1]), str(r[3]), float(r[2])) for r in rows }

    # Cargar labores dinámicas desde registro_lotes.json
    for lote in lotes_json.get("lotes", []):
        for lab in lote.get("labores", []):
            if not isinstance(lab, dict):
                continue

            # Determinar cultivo de la labor
            lab_crop = lab.get("crop_key")
            if not lab_crop:
                desc = (lab.get("labor", "") + " " + str(lab)).lower()
                if any(w in desc for w in ["maiz", "maíz", "dk", "pioneer", "nidera"]):
                    lab_crop = "maiz"
                elif any(w in desc for w in ["trigo", "fina"]):
                    lab_crop = "trigo"
                elif any(w in desc for w in ["segunda", "2da", "rastrojo"]):
                    lab_crop = "soja_segunda"
                else:
                    lab_crop = "soja_primera"

            # Determinar campo de la labor
            lab_campo = lab.get("campo_nombre")
            if not lab_campo:
                lote_nom = (lote.get("nombre", "") + " " + lab.get("lote", "")).lower()
                if "ombu" in lote_nom or "ombú" in lote_nom or "norte" in lote_nom:
                    lab_campo = "El Ombu"
                elif "san jose" in lote_nom or "san josé" in lote_nom or "sur" in lote_nom:
                    lab_campo = "San Jose"
                else:
                    lab_campo = "La Esperanza"

            # Coincidencia con el cultivo y el campo actual
            if lab_crop == crop_key and (campo_nombre.lower().replace(" ", "") in lab_campo.lower().replace(" ", "") or lab_campo.lower().replace(" ", "") in campo_nombre.lower().replace(" ", "")):
                f_fecha = lab.get("fecha", datetime.now().strftime("%Y-%m-%d"))
                f_lote = lab.get("lote", lote.get("id", "Lote"))
                f_labor = lab.get("labor", lab.get("tipo", "Labor Agrícola"))
                f_ha = float(lab.get("superficie_ha", 0))

                key = (str(f_fecha), str(f_lote), str(f_labor), f_ha)
                if key not in existing_keys:
                    existing_keys.add(key)
                    rows.append([
                        f_fecha,
                        f_lote,
                        f_ha,
                        f_labor,
                        lab.get("maquinaria", "Tractor / Equipo asignado"),
                        lab.get("operario", "Operario"),
                        float(lab.get("combustible_litros", 0)),
                        lab.get("deposito_combustible", "-"),
                        lab.get("semilla", "-"),
                        lab.get("fertilizante", "-"),
                        lab.get("insumos", "-"),
                        lab.get("rinde", "-"),
                        lab.get("observaciones", "Registro dinámico IA Desk Agro")
                    ])

    return rows

def extract_number_from_text(txt: Any) -> float:
    if isinstance(txt, (int, float)):
        return float(txt)
    txt_str = str(txt or "")
    m = re.search(r"(\d+(?:[\.,]\d+)?)", txt_str)
    if m:
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            pass
    return 0.0

def get_resumen_rows_for_crop(crop_key: str, lotes_json: dict) -> List[List[Any]]:
    """Calcula el resumen ejecutivo por campo con acumulados reales de hectáreas, combustible y fertilizante"""
    campos_meta = [
        {"nombre": "La Esperanza", "display": "La Esperanza", "lotes_desc": "Lotes Centrales", "estado": "En seguimiento activo", "rinde": "Rinde c/cámara"},
        {"nombre": "El Ombu", "display": "El Ombú", "lotes_desc": "Lotes Norte", "estado": "Vegetativo / Manejo", "rinde": "Rinde objetivo"},
        {"nombre": "San Jose", "display": "San José", "lotes_desc": "Lotes Sur", "estado": "Manejo de lote", "rinde": "Rinde proyectado"}
    ]

    resumen_filas = []
    for c in campos_meta:
        labores = get_labores_rows(crop_key, c["nombre"], lotes_json)
        tot_ha = 0
        tot_gasoil = 0
        tot_fert = 0
        tot_sem = 0

        # Lotes únicos asignados
        lotes_en_campo = set()
        for r in labores:
            lotes_en_campo.add(str(r[1]))
            tot_ha += float(r[2]) if isinstance(r[2], (int, float)) else extract_number_from_text(r[2])
            tot_gasoil += float(r[6]) if isinstance(r[6], (int, float)) else extract_number_from_text(r[6])
            
            # Fertilizante kg
            f_val = str(r[9])
            if f_val != "-":
                tot_fert += extract_number_from_text(f_val)
            # Semilla bolsas
            s_val = str(r[8])
            if s_val != "-":
                tot_sem += extract_number_from_text(s_val)

        # Ajustes de etiqueta según cultivo
        if crop_key == "maiz":
            estado = "Emergencia / V4" if c["nombre"] == "La Esperanza" else ("Vegetativo V6" if c["nombre"] == "El Ombu" else "Siembra / Emergencia")
            rinde_txt = "95.0 qq/ha obj." if c["nombre"] == "La Esperanza" else ("100.0 qq/ha obj." if c["nombre"] == "El Ombu" else "92.0 qq/ha obj.")
        elif crop_key == "soja_primera":
            estado = "Siembra R1" if c["nombre"] == "La Esperanza" else ("Vegetativo V4" if c["nombre"] == "El Ombu" else "Vegetativo V2")
            rinde_txt = "38.0 qq/ha obj." if c["nombre"] == "La Esperanza" else ("40.0 qq/ha obj." if c["nombre"] == "El Ombu" else "36.0 qq/ha obj.")
        elif crop_key == "soja_segunda":
            estado = "Rastrojo trigo" if c["nombre"] == "La Esperanza" else ("Planificación" if c["nombre"] == "El Ombu" else "Siembra directa")
            rinde_txt = "28.0 qq/ha obj." if c["nombre"] == "La Esperanza" else ("30.0 qq/ha obj." if c["nombre"] == "El Ombu" else "27.0 qq/ha obj.")
        else: # trigo
            estado = "Cosecha Concluida"
            rinde_txt = "39.0 qq/ha (819 Tn)" if c["nombre"] == "La Esperanza" else ("38.5 qq/ha (346 Tn)" if c["nombre"] == "El Ombu" else "39.2 qq/ha (431 Tn)")

        lotes_str = ", ".join(sorted(list(lotes_en_campo))) if lotes_en_campo else c["lotes_desc"]

        resumen_filas.append([
            c["display"],
            f"{lotes_str}",
            round(tot_ha, 1),
            estado,
            round(tot_gasoil, 0),
            round(tot_fert, 0),
            round(tot_sem, 0),
            rinde_txt
        ])

    return resumen_filas

def generate_crop_workbook(crop_key: str) -> Path:
    """
    Genera el libro Excel de un cultivo específico ('maiz', 'soja_primera', 'soja_segunda', 'trigo')
    con solapas divididas por cada campo y registro de labores por lote.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active) # Quitar hoja vacía

    theme = THEMES.get(crop_key, THEMES["maiz"])
    lotes_json = get_lotes_data()
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # Campos del establecimiento
    campos = [
        {"nombre": "La Esperanza", "subtitulo": "Campo Central - Casco Principal"},
        {"nombre": "El Ombu", "subtitulo": "Campo Norte - Lotes Agrícolas"},
        {"nombre": "San Jose", "subtitulo": "Campo Sur - Cuenca Productiva"}
    ]

    # ==============================================================
    # SOLAPA 1: 📊 Resumen Ejecutivo del Cultivo
    # ==============================================================
    ws_res = wb.create_sheet(title=f"Resumen {theme['icon']}")
    ws_res.views.sheetView[0].showGridLines = True

    ws_res["A1"] = f"{theme['icon']} {theme['title']}"
    ws_res["A1".format()].font = Font(name="Calibri", size=14, bold=True, color=theme["color_title"])
    ws_res["A2"] = f"Campaña 2026/2027 | Actualizado al: {now_str}"
    ws_res["A2"].font = SMALL_FONT

    ws_res.append([])
    headers_res = ["CAMPO", "LOTES ASIGNADOS", "SUPERFICIE ACUM. (HA)", "ESTADO FENOLÓGICO", "GASOIL ACUMULADO (L)", "FERTILIZANTE ACUM. (KG)", "SEMILLA ACUM. (BOLSAS)", "RINDE ESTIMADO / LOGRADO"]
    ws_res.append(headers_res)
    for c in range(1, len(headers_res) + 1):
        cell = ws_res.cell(row=4, column=c)
        cell.fill = theme["header_fill"]
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Cargar datos por campo para este cultivo
    resumen_filas = get_resumen_rows_for_crop(crop_key, lotes_json)
    for r in resumen_filas:
        ws_res.append(r)
        curr = ws_res.max_row
        for c in range(1, len(r) + 1):
            cell = ws_res.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [3, 5, 6, 7]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 8:
                cell.alignment = Alignment(horizontal="center")

    # Fila de Totales del Cultivo
    ws_res.append([
        "TOTAL GENERAL CULTIVO",
        "Todos los campos",
        "=SUM(C5:C7)",
        "En seguimiento activo",
        "=SUM(E5:E7)",
        "=SUM(F5:F7)",
        "=SUM(G5:G7)",
        "Promedio consolidado"
    ])
    curr = ws_res.max_row
    for c in range(1, 9):
        cell = ws_res.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = theme["total_fill"]
        cell.border = BORDER_TOTAL
        if c in [3, 5, 6, 7]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")
        elif c in [1, 2, 4, 8]:
            cell.alignment = Alignment(horizontal="center")

    auto_adjust_columns(ws_res)

    # ==============================================================
    # SOLAPAS 2, 3, 4: 🏡 Una solapa por cada Campo
    # ==============================================================
    for campo in campos:
        ws_campo = wb.create_sheet(title=f"Campo {campo['nombre']}")
        ws_campo.views.sheetView[0].showGridLines = True

        ws_campo["A1"] = f"{theme['icon']} {theme['title']} - CAMPO {campo['nombre'].upper()}"
        ws_campo["A1"].font = Font(name="Calibri", size=13, bold=True, color=theme["color_title"])
        ws_campo["A2"] = f"{campo['subtitulo']} | Registro de Labores y Gastos Asociados | {now_str}"
        ws_campo["A2"].font = SMALL_FONT

        ws_campo.append([])
        ws_campo.append(HEADERS_LABORES)
        for c in range(1, len(HEADERS_LABORES) + 1):
            cell = ws_campo.cell(row=4, column=c)
            cell.fill = theme["header_fill"]
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Cargar labores históricas y registradas para este campo y cultivo
        labores_rows = get_labores_rows(crop_key, campo["nombre"], lotes_json)
        start_row = 5
        for row_data in labores_rows:
            ws_campo.append(row_data)
            curr = ws_campo.max_row
            for c in range(1, len(row_data) + 1):
                cell = ws_campo.cell(row=curr, column=c)
                cell.font = REGULAR_FONT
                cell.border = BORDER_CELL
                if c in [3, 7]: # Superficie y gasoil
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right")
                elif c in [1, 2, 8, 12]:
                    cell.alignment = Alignment(horizontal="center")

        end_row = ws_campo.max_row
        if end_row >= start_row:
            # Fila de Totales de Labores en ese Campo
            ws_campo.append([
                "TOTALES CAMPO",
                "Consolidado",
                f"=SUM(C{start_row}:C{end_row})",
                f"{len(labores_rows)} labores realizadas",
                "-",
                "-",
                f"=SUM(G{start_row}:G{end_row})",
                "-",
                "Total Semilla",
                "Total Fertilizante",
                "Total Insumos",
                "-",
                "Operaciones al día"
            ])
            curr_tot = ws_campo.max_row
            for c in range(1, len(HEADERS_LABORES) + 1):
                cell = ws_campo.cell(row=curr_tot, column=c)
                cell.font = BOLD_FONT
                cell.fill = theme["total_fill"]
                cell.border = BORDER_TOTAL
                if c in [3, 7]:
                    cell.number_format = "#,##0"
                    cell.alignment = Alignment(horizontal="right")
                elif c in [1, 2, 4, 13]:
                    cell.alignment = Alignment(horizontal="center")

        auto_adjust_columns(ws_campo)

    # Guardar en files_storage/
    crop_filename_map = {
        "maiz": "IA_Desk_Agro_Maiz.xlsx",
        "soja_primera": "IA_Desk_Agro_Soja_Primera.xlsx",
        "soja_segunda": "IA_Desk_Agro_Soja_Segunda.xlsx",
        "trigo": "IA_Desk_Agro_Trigo.xlsx"
    }
    out_filename = crop_filename_map.get(crop_key, f"IA_Desk_Agro_{crop_key}.xlsx")
    out_path = settings.FILES_STORAGE_DIR / out_filename
    wb.save(out_path)
    return out_path

def generate_all_crop_workbooks() -> Dict[str, Path]:
    """Genera los 4 libros Excel y los guarda en files_storage/"""
    results = {}
    for crop_key in ["maiz", "soja_primera", "soja_segunda", "trigo"]:
        path = generate_crop_workbook(crop_key)
        results[crop_key] = path
    return results

def append_labor_to_crop(crop_key: str, campo_nombre: str, lote_id: str, labor_data: dict):
    """
    Registra una nueva labor efectuada en un lote de un cultivo y campo determinado,
    asociando el combustible, fertilizante o semilla utilizada, y regenera las hojas.
    """
    path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
    data = get_lotes_data()

    # Asegurar metadatos en la labor
    labor_data["crop_key"] = crop_key
    labor_data["campo_nombre"] = campo_nombre

    lotes = data.get("lotes", [])
    target_lote = None
    for l in lotes:
        if lote_id.lower() in l.get("nombre", "").lower() or lote_id.lower() in l.get("id", "").lower():
            target_lote = l
            break

    if target_lote:
        target_lote.setdefault("labores", []).append(labor_data)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # Regenerar el libro específico del cultivo y el consolidado
    generate_crop_workbook(crop_key)
    from .sheets_export_service import generate_consolidated_workbook
    generate_consolidated_workbook()
