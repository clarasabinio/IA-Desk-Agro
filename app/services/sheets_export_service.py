import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.conf import settings

# Estilos de diseño para las Hojas de Cálculo
HEADER_FILL = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")  # Verde oscuro agro
SUBHEADER_FILL = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid") # Verde medio
ACCENT_FILL = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")    # Verde claro suave
ALERT_FILL = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")     # Naranja suave acopio
TOTAL_FILL = PatternFill(start_color="C8E6C9", end_color="C8E6C9", fill_type="solid")     # Verde total

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="1B5E20")
BOLD_FONT = Font(name="Calibri", size=11, bold=True, color="000000")
REGULAR_FONT = Font(name="Calibri", size=11, color="000000")
SMALL_FONT = Font(name="Calibri", size=9, italic=True, color="555555")

THIN_SIDE = Side(border_style="thin", color="CCCCCC")
THICK_BOTTOM = Side(border_style="medium", color="1B5E20")
DOUBLE_BOTTOM = Side(border_style="double", color="1B5E20")

BORDER_CELL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
BORDER_TOTAL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=DOUBLE_BOTTOM)

def get_storage_path() -> Path:
    return settings.BASE_DIR / "files_storage"

def auto_adjust_columns(ws, min_width=12):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if "\n" in val_str:
                val_str = max(val_str.split("\n"), key=len)
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 3, min_width)

def generate_consolidated_workbook() -> Path:
    storage_dir = get_storage_path()
    wb = openpyxl.Workbook()
    # Remover la hoja por defecto
    wb.remove(wb.active)

    # Cargar datos JSON
    try:
        with open(storage_dir / "stock_gasoil.json", "r", encoding="utf-8") as f:
            gasoil_data = json.load(f)
    except Exception:
        gasoil_data = {}

    try:
        with open(storage_dir / "stock_insumos.json", "r", encoding="utf-8") as f:
            insumos_data = json.load(f)
    except Exception:
        insumos_data = {}

    try:
        with open(storage_dir / "stock_granos_silos.json", "r", encoding="utf-8") as f:
            granos_data = json.load(f)
    except Exception:
        granos_data = {}

    try:
        with open(storage_dir / "MEMORY.md", "r", encoding="utf-8") as f:
            memory_lines = [line.strip() for line in f.readlines() if line.strip().startswith("- [")]
    except Exception:
        memory_lines = []

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    # ==============================================================
    # PESTAÑA 1: 📊 Tablero General
    # ==============================================================
    ws_tablero = wb.create_sheet(title="Tablero General")
    ws_tablero.views.sheetView[0].showGridLines = True

    ws_tablero["A1"] = "IA DESK AGRO - ESTABLECIMIENTO 'LA ESPERANZA'"
    ws_tablero["A1"].font = TITLE_FONT
    ws_tablero["A2"] = f"Campaña Gruesa 2026/2027 | Última actualización online: {now_str}"
    ws_tablero["A2"].font = SMALL_FONT

    headers_tablero = ["MÓDULO DE GESTIÓN", "INDICADOR PRINCIPAL", "EN CAMPO / PLANTA", "A RETIRAR / DISTRIBUIDOR", "TOTAL DISPONIBLE", "UNIDAD"]
    ws_tablero.append([])
    ws_tablero.append(headers_tablero)
    row_idx = 4
    for col_idx in range(1, 7):
        cell = ws_tablero.cell(row=row_idx, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Datos Tablero
    g_fisico = gasoil_data.get("totales", {}).get("stock_fisico_campo_litros", 0)
    g_acopio = gasoil_data.get("depositos", {}).get("acopio_por_retirar", {}).get("litros_disponibles", 0)
    g_total = gasoil_data.get("totales", {}).get("stock_total_con_acopio_litros", 0)

    f_galpon = insumos_data.get("fertilizantes_totales", {}).get("en_galpon_kg", 0)
    f_retiro = insumos_data.get("fertilizantes_totales", {}).get("por_retirar_kg", 0)
    f_total = insumos_data.get("fertilizantes_totales", {}).get("total_general_kg", 0)

    i_galpon = insumos_data.get("fitosanitarios_totales", {}).get("en_galpon_litros", 0)
    i_retiro = insumos_data.get("fitosanitarios_totales", {}).get("a_retirar_litros", 0)
    i_total = insumos_data.get("fitosanitarios_totales", {}).get("total_general_litros", 0)

    m_planta = insumos_data.get("semillas_maiz", {}).get("totales", {}).get("bolsas_en_planta", 0)
    m_retiro = insumos_data.get("semillas_maiz", {}).get("totales", {}).get("bolsas_por_retirar", 0)
    m_total = insumos_data.get("semillas_maiz", {}).get("totales", {}).get("total_general_bolsas", 0)

    gr_total_tn = granos_data.get("totales_generales", {}).get("total_granos_almacenados_tn", 0)
    soja_tn = granos_data.get("soja", {}).get("total_tn", 0)
    trigo_tn = granos_data.get("trigo", {}).get("total_tn", 0)

    tablero_rows = [
        ["Combustibles (Gasoil)", "Stock 4 Depósitos & Acopio YPF", g_fisico, g_acopio, g_total, "Litros"],
        ["Fertilizantes Granulados", "Fósforo, Nitrógeno & Zinc", f_galpon, f_retiro, f_total, "Kilogramos (kg)"],
        ["Insumos & Fitosanitarios", "Herbicidas, Insecticidas & Coadyuvante", i_galpon, i_retiro, i_total, "Litros"],
        ["Semillas de Maíz", "3 Híbridos Seleccionados", m_planta, m_retiro, m_total, "Bolsas (80k sem)"],
        ["Granos Almacenados (Soja)", "Silobolsas & Silos de Chapa", soja_tn, 0, soja_tn, "Toneladas (Tn)"],
        ["Granos Almacenados (Trigo)", "Silobolsa Norte & Silo Central", trigo_tn, 0, trigo_tn, "Toneladas (Tn)"]
    ]

    for r in tablero_rows:
        ws_tablero.append(r)
        curr_row = ws_tablero.max_row
        for c in range(1, 7):
            cell = ws_tablero.cell(row=curr_row, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [3, 4, 5]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 6:
                cell.alignment = Alignment(horizontal="center")

    auto_adjust_columns(ws_tablero)

    # ==============================================================
    # PESTAÑA 2: ⛽ Combustibles
    # ==============================================================
    ws_comb = wb.create_sheet(title="Combustibles")
    ws_comb.views.sheetView[0].showGridLines = True
    ws_comb["A1"] = "CONTROL INTEGRAL DE COMBUSTIBLES (GASOIL DIESEL)"
    ws_comb["A1"].font = TITLE_FONT
    ws_comb["A2"] = f"Actualizado al: {now_str} | Empresa Agropecuaria La Esperanza"
    ws_comb["A2"].font = SMALL_FONT

    ws_comb.append([])
    ws_comb.append(["DEPÓSITO / ACOPIO", "TIPO / ROL", "CAPACIDAD MÁX (L)", "STOCK ACTUAL (L)", "% OCUPACIÓN", "ESTADO", "OBSERVACIONES"])
    for c in range(1, 8):
        cell = ws_comb.cell(row=4, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    deps = gasoil_data.get("depositos", {})
    dep_rows = [
        ["Cisterna Planta", "Tanque Central Fijo", 22000, deps.get("cisterna_planta", {}).get("stock_actual_litros", 0), "=(D5/C5)", "Operativo", "Tanque nodriza en casco"],
        ["Tanque Grande", "Cisterna Móvil Siembra/Cosecha", 5000, deps.get("tanque_grande", {}).get("stock_actual_litros", 0), "=(D6/C6)", "Operativo", "Abastecimiento en lotes"],
        ["Tanque Chico", "Carretón Auxilio Rápido", 3000, deps.get("tanque_chico", {}).get("stock_actual_litros", 0), "=(D7/C7)", "Operativo", "Tractorista y pulverización"],
        ["Gasoil por Retirar", "Saldo Acopiado en Proveedor", 10000, deps.get("acopio_por_retirar", {}).get("litros_disponibles", 0), "=(D8/C8)", "Por retirar", "YPF Directo - Junín"]
    ]

    for r in dep_rows:
        ws_comb.append(r)
        curr = ws_comb.max_row
        for c in range(1, 8):
            cell = ws_comb.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [3, 4]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 5:
                cell.number_format = "0.0%"
                cell.alignment = Alignment(horizontal="center")
            elif c in [2, 6]:
                cell.alignment = Alignment(horizontal="center")

    # Fila de Totales Físicos en Campo
    ws_comb.append(["TOTAL FÍSICO EN CAMPO", "Suma de los 3 tanques", 30000, "=SUM(D5:D7)", "=(D9/C9)", "Disponible", "Combustible dentro del campo"])
    curr = ws_comb.max_row
    for c in range(1, 8):
        cell = ws_comb.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER_TOTAL
        if c in [3, 4]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")
        elif c == 5:
            cell.number_format = "0.0%"
            cell.alignment = Alignment(horizontal="center")

    # Fila Total General con Acopio
    ws_comb.append(["TOTAL DISPONIBLE CON ACOPIO", "Físico + Saldo YPF", 40000, "=D9+D8", "=(D10/C10)", "Total General", "Total auditado"])
    curr = ws_comb.max_row
    for c in range(1, 8):
        cell = ws_comb.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER_TOTAL
        if c in [3, 4]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")
        elif c == 5:
            cell.number_format = "0.0%"
            cell.alignment = Alignment(horizontal="center")

    # Sección de Salidas Recientes
    ws_comb.append([])
    ws_comb.append(["HISTORIAL DE SALIDAS Y CONSUMOS REGISTRADOS"])
    ws_comb.cell(row=ws_comb.max_row, column=1).font = Font(name="Calibri", size=12, bold=True, color="1B5E20")

    ws_comb.append(["FECHA", "DEPÓSITO ORIGEN", "MAQUINARIA / LABOR", "LITROS", "OPERARIO"])
    salidas_hdr_row = ws_comb.max_row
    for c in range(1, 6):
        cell = ws_comb.cell(row=salidas_hdr_row, column=c)
        cell.fill = SUBHEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")

    for s in gasoil_data.get("salidas", []):
        ws_comb.append([
            s.get("fecha", ""),
            s.get("deposito_origen", ""),
            s.get("maquinaria", s.get("labor", "")),
            s.get("litros", 0),
            s.get("operario", "")
        ])
        curr = ws_comb.max_row
        for c in range(1, 6):
            cell = ws_comb.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c == 4:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")

    auto_adjust_columns(ws_comb)

    # ==============================================================
    # PESTAÑA 3: 🧪 Fertilizantes (en kg)
    # ==============================================================
    ws_fert = wb.create_sheet(title="Fertilizantes (kg)")
    ws_fert.views.sheetView[0].showGridLines = True
    ws_fert["A1"] = "CONTROL DE FERTILIZANTES EN KILOGRAMOS (KG) Y LUGARES DE RETIRO"
    ws_fert["A1"].font = TITLE_FONT
    ws_fert["A2"] = f"Stock en Galpón vs Por Retirar en Distribuidor | Actualizado: {now_str}"
    ws_fert["A2"].font = SMALL_FONT

    ws_fert.append([])
    ws_fert.append(["PRODUCTO", "FÓRMULA", "FORMATO", "EN GALPÓN (KG)", "POR RETIRAR (KG)", "LUGAR DETERMINADO DE RETIRO", "TOTAL (KG)", "EQUIV. (TN)"])
    for c in range(1, 9):
        cell = ws_fert.cell(row=4, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ferts = insumos_data.get("fertilizantes", [])
    for f in ferts:
        en_g = f.get("en_galpon_kg", 0)
        p_ret = f.get("por_retirar_kg", 0)
        tot_k = f.get("total_kg", en_g + p_ret)
        ws_fert.append([
            f.get("nombre", ""),
            f.get("formula", ""),
            f.get("formato", ""),
            en_g,
            p_ret,
            f.get("lugar_retiro", ""),
            tot_k,
            round(tot_k / 1000.0, 2)
        ])
        curr = ws_fert.max_row
        for c in range(1, 9):
            cell = ws_fert.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [4, 5, 7]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 8:
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right")

    # Totales Fertilizantes
    tot_fg = insumos_data.get("fertilizantes_totales", {}).get("en_galpon_kg", 0)
    tot_fr = insumos_data.get("fertilizantes_totales", {}).get("por_retirar_kg", 0)
    tot_fgral = insumos_data.get("fertilizantes_totales", {}).get("total_general_kg", 0)

    ws_fert.append(["TOTAL CONSOLIDADO", "N-P-K-S-Zn", "Todos los formatos", tot_fg, tot_fr, "Varios distribuidores", tot_fgral, round(tot_fgral / 1000.0, 2)])
    curr = ws_fert.max_row
    for c in range(1, 9):
        cell = ws_fert.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER_TOTAL
        if c in [4, 5, 7]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")
        elif c == 8:
            cell.number_format = "#,##0.00"
            cell.alignment = Alignment(horizontal="right")

    auto_adjust_columns(ws_fert)

    # ==============================================================
    # PESTAÑA 4: 📦 Insumos & Fitosanitarios
    # ==============================================================
    ws_ins = wb.create_sheet(title="Insumos y Fitosanitarios")
    ws_ins.views.sheetView[0].showGridLines = True
    ws_ins["A1"] = "INVENTARIO DE INSUMOS Y FITOSANITARIOS (DOS OPCIONES)"
    ws_ins["A1"].font = TITLE_FONT
    ws_ins["A2"] = f"Existencias Físicas en Galpón vs A Retirar en Comercio Determinado | Actualizado: {now_str}"
    ws_ins["A2"].font = SMALL_FONT

    ws_ins.append([])
    ws_ins.append(["PRODUCTO / PRINCIPIO", "TIPO / ACCIÓN", "PROVEEDOR", "EN GALPÓN (L)", "A RETIRAR (L)", "LUGAR DETERMINADO DE RETIRO", "TOTAL (L)", "UNIDAD"])
    for c in range(1, 9):
        cell = ws_ins.cell(row=4, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    fitos = insumos_data.get("fitosanitarios", [])
    for f in fitos:
        en_g = f.get("en_galpon", 0)
        a_ret = f.get("a_retirar", 0)
        tot_l = f.get("total", en_g + a_ret)
        ws_ins.append([
            f.get("nombre", ""),
            f.get("tipo", ""),
            f.get("proveedor", ""),
            en_g,
            a_ret,
            f.get("lugar_retiro", ""),
            tot_l,
            f.get("unidad", "Litros")
        ])
        curr = ws_ins.max_row
        for c in range(1, 9):
            cell = ws_ins.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [4, 5, 7]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 8:
                cell.alignment = Alignment(horizontal="center")

    # Totales Fitosanitarios
    tot_ig = insumos_data.get("fitosanitarios_totales", {}).get("en_galpon_litros", 0)
    tot_ir = insumos_data.get("fitosanitarios_totales", {}).get("a_retirar_litros", 0)
    tot_igral = insumos_data.get("fitosanitarios_totales", {}).get("total_general_litros", 0)

    ws_ins.append(["TOTAL CONSOLIDADO", "Agroquímicos completos", "Multi-marca", tot_ig, tot_ir, "Comercios zonales", tot_igral, "Litros"])
    curr = ws_ins.max_row
    for c in range(1, 9):
        cell = ws_ins.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER_TOTAL
        if c in [4, 5, 7]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")
        elif c == 8:
            cell.alignment = Alignment(horizontal="center")

    auto_adjust_columns(ws_ins)

    # ==============================================================
    # PESTAÑA 5: 🌽 Semillas de Maíz por Híbrido
    # ==============================================================
    ws_mz = wb.create_sheet(title="Semillas Maiz")
    ws_mz.views.sheetView[0].showGridLines = True
    ws_mz["A1"] = "CONTROL DE SEMILLAS DE MAÍZ POR HÍBRIDO (BOLSAS)"
    ws_mz["A1"].font = TITLE_FONT
    ws_mz["A2"] = f"Bolsas en Planta Central vs Por Retirar en Semillería | Actualizado: {now_str}"
    ws_mz["A2"].font = SMALL_FONT

    ws_mz.append([])
    ws_mz.append(["HÍBRIDO / VARIEDAD", "PROVEEDOR", "PRESENTACIÓN", "EN PLANTA (BOLSAS)", "POR RETIRAR (BOLSAS)", "LUGAR DETERMINADO DE RETIRO", "TOTAL BOLSAS", "TRATAMIENTO"])
    for c in range(1, 9):
        cell = ws_mz.cell(row=4, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    hibridos = insumos_data.get("semillas_maiz", {}).get("hibridos", [])
    for h in hibridos:
        en_p = h.get("en_planta_bolsas", 0)
        p_ret = h.get("por_retirar_bolsas", 0)
        tot_b = h.get("total_bolsas", en_p + p_ret)
        ws_mz.append([
            f"{h.get('hibrido', '')} ({h.get('variedad', '')})",
            h.get("proveedor", ""),
            h.get("presentacion", ""),
            en_p,
            p_ret,
            h.get("lugar_retiro", ""),
            tot_b,
            h.get("tratamiento", "")
        ])
        curr = ws_mz.max_row
        for c in range(1, 9):
            cell = ws_mz.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [4, 5, 7]:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right")

    tot_mp = insumos_data.get("semillas_maiz", {}).get("totales", {}).get("bolsas_en_planta", 0)
    tot_mr = insumos_data.get("semillas_maiz", {}).get("totales", {}).get("bolsas_por_retirar", 0)
    tot_mgral = insumos_data.get("semillas_maiz", {}).get("totales", {}).get("total_general_bolsas", 0)

    ws_mz.append(["TOTAL CONSOLIDADO MAÍZ", "Bayer / Corteva / Nidera", "Bolsas 80k semillas", tot_mp, tot_mr, "Red de distribuidores", tot_mgral, "Tratamientos integrales"])
    curr = ws_mz.max_row
    for c in range(1, 9):
        cell = ws_mz.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER_TOTAL
        if c in [4, 5, 7]:
            cell.number_format = "#,##0"
            cell.alignment = Alignment(horizontal="right")

    auto_adjust_columns(ws_mz)

    # ==============================================================
    # PESTAÑA 6: 🌾 Granos en Silos y Silobolsas (Tn)
    # ==============================================================
    ws_gr = wb.create_sheet(title="Granos Silos (Tn)")
    ws_gr.views.sheetView[0].showGridLines = True
    ws_gr["A1"] = "INVENTARIO DE GRANOS EN SILOS Y SILOBOLSAS (TONELADAS)"
    ws_gr["A1"].font = TITLE_FONT
    ws_gr["A2"] = f"Monitoreo de Existencias de Soja y Trigo | Actualizado: {now_str}"
    ws_gr["A2"].font = SMALL_FONT

    ws_gr.append([])
    ws_gr.append(["CULTIVO", "TIPO ACOPIO", "IDENTIFICADOR / UBICACIÓN", "STOCK ACTUAL (TN)", "CAPACIDAD MÁX (TN)", "% OCUPACIÓN", "HUMEDAD %", "CALIDAD / PH", "OBSERVACIONES"])
    for c in range(1, 10):
        cell = ws_gr.cell(row=4, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for u in granos_data.get("soja", {}).get("ubicaciones", []):
        act = u.get("stock_actual_tn", 0)
        cap = u.get("capacidad_max_tn", act)
        ws_gr.append([
            "Soja Comercial",
            u.get("tipo", ""),
            u.get("identificador", ""),
            act,
            cap,
            (act / cap) if cap > 0 else 1.0,
            f"{u.get('humedad_pct', 13.0)}%",
            u.get("calidad", "Cámara"),
            u.get("fecha_embolsado", "")
        ])
        curr = ws_gr.max_row
        for c in range(1, 10):
            cell = ws_gr.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [4, 5]:
                cell.number_format = "#,##0.0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 6:
                cell.number_format = "0.0%"
                cell.alignment = Alignment(horizontal="center")

    for u in granos_data.get("trigo", {}).get("ubicaciones", []):
        act = u.get("stock_actual_tn", 0)
        cap = u.get("capacidad_max_tn", act)
        ws_gr.append([
            "Trigo Pan Grado 1",
            u.get("tipo", ""),
            u.get("identificador", ""),
            act,
            cap,
            (act / cap) if cap > 0 else 1.0,
            f"{u.get('humedad_pct', 12.0)}%",
            f"PH {u.get('peso_hectolitrico', 80.0)}",
            u.get("ubicacion_planta", "")
        ])
        curr = ws_gr.max_row
        for c in range(1, 10):
            cell = ws_gr.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [4, 5]:
                cell.number_format = "#,##0.0"
                cell.alignment = Alignment(horizontal="right")
            elif c == 6:
                cell.number_format = "0.0%"
                cell.alignment = Alignment(horizontal="center")

    # Total Granos
    tot_granos = granos_data.get("totales_generales", {}).get("total_granos_almacenados_tn", soja_tn + trigo_tn)
    ws_gr.append(["TOTAL GENERAL GRANOS", "Silos + Silobolsas", "Establecimiento completo", tot_granos, 1500.0, (tot_granos / 1500.0), "Bajo norma", "Grado Comercial Superior", "Monitoreo continuo"])
    curr = ws_gr.max_row
    for c in range(1, 10):
        cell = ws_gr.cell(row=curr, column=c)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER_TOTAL
        if c in [4, 5]:
            cell.number_format = "#,##0.0"
            cell.alignment = Alignment(horizontal="right")
        elif c == 6:
            cell.number_format = "0.0%"
            cell.alignment = Alignment(horizontal="center")

    auto_adjust_columns(ws_gr)

    # ==============================================================
    # PESTAÑA 7: 📝 Bitácora de Labores
    # ==============================================================
    ws_log = wb.create_sheet(title="Bitacora de Labores")
    ws_log.views.sheetView[0].showGridLines = True
    ws_log["A1"] = "BITÁCORA OPERATIVA Y MEMORIA HISTÓRICA DE LABORES"
    ws_log["A1"].font = TITLE_FONT
    ws_log["A2"] = f"Registro cronológico de movimientos realizados por la IA | Actualizado: {now_str}"
    ws_log["A2"].font = SMALL_FONT

    ws_log.append([])
    ws_log.append(["FECHA Y HORA", "DESCRIPCIÓN DE LA LABOR / MOVIMIENTO", "CATEGORÍA", "ESTADO"])
    for c in range(1, 5):
        cell = ws_log.cell(row=4, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for line in reversed(memory_lines):
        # Line format: "- [2026-10-08 21:20:24] Traslado de..."
        parts = line.split("] ", 1)
        if len(parts) == 2:
            dt_str = parts[0].replace("- [", "")
            desc = parts[1]
        else:
            dt_str = "Reciente"
            desc = line.replace("- ", "")

        cat = "Operativa"
        if "combustible" in desc.lower() or "tanque" in desc.lower() or "gasoil" in desc.lower() or "litros" in desc.lower():
            cat = "Combustible"
        elif "fertilizante" in desc.lower() or "map" in desc.lower() or "urea" in desc.lower():
            cat = "Fertilizantes"
        elif "2,4-d" in desc.lower() or "glifosato" in desc.lower() or "insumo" in desc.lower():
            cat = "Insumos"
        elif "maíz" in desc.lower() or "maiz" in desc.lower() or "bolsas" in desc.lower():
            cat = "Semillas"
        elif "soja" in desc.lower() or "trigo" in desc.lower() or "silo" in desc.lower():
            cat = "Granos"

        ws_log.append([dt_str, desc, cat, "Asentado"])
        curr = ws_log.max_row
        for c in range(1, 5):
            cell = ws_log.cell(row=curr, column=c)
            cell.font = REGULAR_FONT
            cell.border = BORDER_CELL
            if c in [1, 3, 4]:
                cell.alignment = Alignment(horizontal="center")

    auto_adjust_columns(ws_log)

    # Guardar archivo consolidado en files_storage/
    out_path = storage_dir / "IA_Desk_Agro_Consolidado.xlsx"
    wb.save(out_path)
    
    # También generar CSVs individuales para cada módulo (útil para fórmulas =IMPORTDATA)
    export_csv_modules(storage_dir, gasoil_data, insumos_data, granos_data)

    return out_path

def export_csv_modules(storage_dir: Path, gasoil_data: dict, insumos_data: dict, granos_data: dict):
    # 1. Combustibles CSV
    with open(storage_dir / "combustibles_live.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Deposito", "Capacidad_Max_L", "Stock_Actual_L", "Porcentaje_Ocupacion", "Estado"])
        deps = gasoil_data.get("depositos", {})
        for k, v in deps.items():
            cap = v.get("capacidad_max_litros", 10000)
            stk = v.get("stock_actual_litros", v.get("litros_disponibles", 0))
            writer.writerow([v.get("nombre", k), cap, stk, f"{(stk/cap*100):.1f}%", "Activo"])

    # 2. Fertilizantes CSV
    with open(storage_dir / "fertilizantes_live.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Producto", "Formula", "En_Galpon_kg", "Por_Retirar_kg", "Lugar_Retiro", "Total_kg"])
        for f_item in insumos_data.get("fertilizantes", []):
            writer.writerow([
                f_item.get("nombre", ""),
                f_item.get("formula", ""),
                f_item.get("en_galpon_kg", 0),
                f_item.get("por_retirar_kg", 0),
                f_item.get("lugar_retiro", ""),
                f_item.get("total_kg", 0)
            ])

    # 3. Insumos CSV
    with open(storage_dir / "insumos_live.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Producto", "Tipo", "En_Galpon_L", "A_Retirar_L", "Lugar_Retiro", "Total_L"])
        for f_item in insumos_data.get("fitosanitarios", []):
            writer.writerow([
                f_item.get("nombre", ""),
                f_item.get("tipo", ""),
                f_item.get("en_galpon", 0),
                f_item.get("a_retirar", 0),
                f_item.get("lugar_retiro", ""),
                f_item.get("total", 0)
            ])

    # 4. Semillas Maiz CSV
    with open(storage_dir / "semillas_maiz_live.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Hibrido", "Proveedor", "En_Planta_Bolsas", "Por_Retirar_Bolsas", "Lugar_Retiro", "Total_Bolsas"])
        for h in insumos_data.get("semillas_maiz", {}).get("hibridos", []):
            writer.writerow([
                h.get("hibrido", ""),
                h.get("proveedor", ""),
                h.get("en_planta_bolsas", 0),
                h.get("por_retirar_bolsas", 0),
                h.get("lugar_retiro", ""),
                h.get("total_bolsas", 0)
            ])

    # 5. Granos Silos CSV
    with open(storage_dir / "granos_silos_live.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Cultivo", "Tipo", "Identificador", "Stock_Actual_Tn", "Capacidad_Max_Tn", "Humedad_Pct"])
        for u in granos_data.get("soja", {}).get("ubicaciones", []):
            writer.writerow(["Soja", u.get("tipo", ""), u.get("identificador", ""), u.get("stock_actual_tn", 0), u.get("capacidad_max_tn", 0), u.get("humedad_pct", 13.0)])
        for u in granos_data.get("trigo", {}).get("ubicaciones", []):
            writer.writerow(["Trigo", u.get("tipo", ""), u.get("identificador", ""), u.get("stock_actual_tn", 0), u.get("capacidad_max_tn", 0), u.get("humedad_pct", 12.0)])
