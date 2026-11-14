import base64
import unicodedata
import os
import json
import re
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.utils.text import slugify
from app.models import Campo, Lote

def generar_diagrama_campo_svg(campo_data: dict, lotes_list: list, imagen_fondo_path: str = None) -> str:
    """
    Genera un plano cartografico y parcelario profesional en formato SVG.
    Si se suministra o existe una fotografia satelital/aerea (.jpg/.png), la proyecta de fondo
    y delimita sobre ella las parcelas y lotes con colores, hectareas y cultivos.
    """
    nombre = campo_data.get("nombre", "Campo Sin Nombre")
    ha_total = campo_data.get("superficie_ha", 0)
    sector = campo_data.get("sector", "Sector Agricola")
    provincia = campo_data.get("provincia", "Buenos Aires")
    ubicacion = campo_data.get("ubicacion", "Zona Nucleo")
    coords = campo_data.get("coordenadas_gps", "-33.8900, -60.5700")
    tenencia = campo_data.get("tenencia", "Propio")
    partida = campo_data.get("partida", "S/D")
    renspa = campo_data.get("renspa", "S/D")
    slug = slugify(nombre).replace("-", "_") or "campo_agro"

    campos_media_dir = settings.BASE_DIR / "media" / "campos"

    # Buscar imagen de fondo si no se especifico directamente
    if not imagen_fondo_path or not os.path.exists(imagen_fondo_path):
        for candidate_ext in [".jpg", ".jpeg", ".png", ".webp"]:
            c_p = campos_media_dir / f"{slug}{candidate_ext}"
            if c_p.exists():
                imagen_fondo_path = str(c_p)
                break

    colores_cultivos = {
        "soja": ("#059669", "#10b981", "#047857"),
        "maiz": ("#d97706", "#f59e0b", "#b45309"),
        "trigo": ("#0284c7", "#38bdf8", "#0369a1"),
        "girasol": ("#ca8a04", "#eab308", "#a16207"),
        "barbecho": ("#475569", "#64748b", "#334155"),
        "default": ("#0d9488", "#14b8a6", "#0f766e")
    }

    n_lotes = len(lotes_list) if lotes_list else 1
    start_x = 55
    start_y = 135
    total_w = 690
    total_h = 330

    if n_lotes == 1:
        layout = [(start_x, start_y, total_w, total_h)]
    elif n_lotes == 2:
        w_half = (total_w - 20) // 2
        layout = [
            (start_x, start_y, w_half, total_h),
            (start_x + w_half + 20, start_y, w_half, total_h)
        ]
    elif n_lotes == 3:
        w_half = (total_w - 20) // 2
        h_half = (total_h - 20) // 2
        layout = [
            (start_x, start_y, w_half, total_h),
            (start_x + w_half + 20, start_y, w_half, h_half),
            (start_x + w_half + 20, start_y + h_half + 20, w_half, h_half)
        ]
    elif n_lotes == 4:
        w_half = (total_w - 20) // 2
        h_half = (total_h - 20) // 2
        layout = [
            (start_x, start_y, w_half, h_half),
            (start_x + w_half + 20, start_y, w_half, h_half),
            (start_x, start_y + h_half + 20, w_half, h_half),
            (start_x + w_half + 20, start_y + h_half + 20, w_half, h_half)
        ]
    else:
        cols = 3
        rows = (n_lotes + cols - 1) // cols
        pw = (total_w - (cols - 1) * 15) // cols
        ph = (total_h - (rows - 1) * 15) // rows
        layout = []
        for i in range(n_lotes):
            c_idx = i % cols
            r_idx = i // cols
            layout.append((start_x + c_idx * (pw + 15), start_y + r_idx * (ph + 15), pw, ph))

    # Base64 image embedding
    image_bg_xml = ""
    badge_satelital = "CARTOGRAFÍA DIGITAL GEOREFERENCIADA"
    has_real_photo = False

    if imagen_fondo_path and os.path.exists(imagen_fondo_path):
        try:
            with open(imagen_fondo_path, "rb") as img_f:
                b64_data = base64.b64encode(img_f.read()).decode("utf-8")
            ext = os.path.splitext(imagen_fondo_path)[1].lower()
            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
            image_bg_xml = f"""
        <!-- Fotografia Satelital Aerea de Base -->
        <image href="data:{mime};base64,{b64_data}" 
               x="40" y="125" width="720" height="345" 
               preserveAspectRatio="xMidYMid slice" 
               clip-path="url(#mapViewportClip)" 
               opacity="0.95"/>
        <rect x="40" y="125" width="720" height="345" rx="12" fill="#020617" fill-opacity="0.25" clip-path="url(#mapViewportClip)"/>
            """
            badge_satelital = "FOTOGRAFÍA SATELITAL AÉREA + LOTES DELIMITADOS"
            has_real_photo = True
        except Exception as e:
            print(f"Error procesando imagen de fondo: {e}")

    parcelas_svg = []
    for idx, (lx, ly, lw, lh) in enumerate(layout[:n_lotes]):
        l_info = lotes_list[idx] if idx < len(lotes_list) else {"nombre": f"Lote {idx+1}", "superficie_ha": ha_total}
        l_nombre = l_info.get("nombre", f"Lote {idx+1}")
        l_ha = l_info.get("superficie_ha", 0)
        l_cultivo = l_info.get("cultivo", "Agricola").lower()
        l_variedad = l_info.get("variedad", "")

        color_key = "default"
        for k in colores_cultivos:
            if k in l_cultivo:
                color_key = k
                break
        fill_col, stroke_col, dark_col = colores_cultivos[color_key]

        cx = lx + lw // 2
        cy = ly + lh // 2

        fill_op = "0.32" if has_real_photo else "0.22"
        stroke_w = "3" if has_real_photo else "2"

        parcela = f"""
        <!-- Parcela {l_nombre} -->
        <g class="lote-parcel">
            <rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="12" 
                  fill="{fill_col}" fill-opacity="{fill_op}" stroke="{stroke_col}" stroke-width="{stroke_w}" 
                  stroke-dasharray="8 4" filter="url(#glowFilter)" />
            <rect x="{lx+4}" y="{ly+4}" width="{lw-8}" height="{lh-8}" rx="10" 
                  fill="none" stroke="{dark_col}" stroke-width="1.5" opacity="0.7" />
            
            <!-- Pin de Identificacion -->
            <circle cx="{lx + 20}" cy="{ly + 20}" r="11" fill="#0f172a" stroke="{stroke_col}" stroke-width="2" />
            <text x="{lx + 20}" y="{ly + 24}" font-family="'JetBrains Mono', monospace" font-size="11" fill="#ffffff" font-weight="bold" text-anchor="middle">{idx+1}</text>
            
            <!-- Tarjeta Flotante Glassmorphism del Lote -->
            <rect x="{cx - 75}" y="{cy - 40}" width="150" height="78" rx="10" 
                  fill="#090d16" fill-opacity="0.85" stroke="{stroke_col}" stroke-width="1.5" />
            
            <text x="{cx}" y="{cy - 20}" font-family="'Outfit', sans-serif" font-size="16" fill="#ffffff" font-weight="800" text-anchor="middle">{l_nombre}</text>
            
            <!-- Badge de Hectareas -->
            <rect x="{cx - 50}" y="{cy - 12}" width="100" height="22" rx="11" fill="{fill_col}" fill-opacity="0.3" stroke="{stroke_col}" stroke-width="1" />
            <text x="{cx}" y="{cy + 3}" font-family="'JetBrains Mono', monospace" font-size="12" fill="#ffffff" font-weight="700" text-anchor="middle">{l_ha} Has</text>
            
            <text x="{cx}" y="{cy + 24}" font-family="'Outfit', sans-serif" font-size="12" fill="#38bdf8" font-weight="600" text-anchor="middle">{l_info.get('cultivo', 'Agricola')}</text>"""
        if l_variedad:
            parcela += f"""
            <text x="{cx}" y="{cy + 35}" font-family="'JetBrains Mono', monospace" font-size="9" fill="#94a3b8" text-anchor="middle">{l_variedad[:22]}</text>"""
        parcela += "\n        </g>"
        parcelas_svg.append(parcela)

    parcelas_xml = "\n".join(parcelas_svg)

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 520" width="100%" height="100%" style="background:#060e0a; border-radius:12px; font-family:'Outfit',sans-serif;">
    <defs>
        <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
            <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(16,185,129,0.07)" stroke-width="1"/>
        </pattern>
        <linearGradient id="topBannerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#091811" stop-opacity="0.95"/>
            <stop offset="100%" stop-color="#040b07" stop-opacity="0.95"/>
        </linearGradient>
        <linearGradient id="borderGlow" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#10b981"/>
            <stop offset="50%" stop-color="#059669"/>
            <stop offset="100%" stop-color="#38bdf8"/>
        </linearGradient>
        <clipPath id="mapViewportClip">
            <rect x="40" y="125" width="720" height="345" rx="12"/>
        </clipPath>
        <filter id="glowFilter" x="-10%" y="-10%" width="120%" height="120%">
            <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="#10b981" flood-opacity="0.3"/>
        </filter>
    </defs>

    <!-- Fondo y Grilla Cartografica Base -->
    <rect width="800" height="520" fill="#040a07"/>
    <rect width="800" height="520" fill="url(#grid)"/>

    <!-- Marco Perimetral -->
    <rect x="15" y="15" width="770" height="490" rx="14" fill="none" stroke="url(#borderGlow)" stroke-width="2" stroke-opacity="0.5"/>

    <!-- Header / Banner Cartografico Superior -->
    <rect x="25" y="25" width="750" height="92" rx="10" fill="url(#topBannerGrad)" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
    
    <!-- Insignia IA Desk Agro -->
    <rect x="40" y="36" width="100" height="22" rx="11" fill="rgba(16,185,129,0.2)" stroke="#10b981" stroke-width="1"/>
    <text x="90" y="51" font-family="'JetBrains Mono', monospace" font-size="10" fill="#10b981" font-weight="bold" text-anchor="middle">IA DESK AGRO</text>

    <!-- Titulo del Campo y Datos Principales -->
    <text x="150" y="53" font-size="20" fill="#ffffff" font-weight="800">{nombre}</text>
    <rect x="645" y="35" width="115" height="26" rx="13" fill="#10b981" fill-opacity="0.2" stroke="#10b981" stroke-width="1.5"/>
    <text x="702" y="52" font-family="'JetBrains Mono', monospace" font-size="13" fill="#34d399" font-weight="bold" text-anchor="middle">{ha_total} Has</text>

    <!-- Subtitulos de Ubicacion, Tenencia y GPS -->
    <text x="40" y="78" font-size="11" fill="#94a3b8">📍 {ubicacion} • {provincia} | Tenencia: <tspan fill="#f59e0b" font-weight="600">{tenencia}</tspan></text>
    <text x="40" y="98" font-size="11" fill="#64748b">🌐 GPS: <tspan fill="#38bdf8">{coords}</tspan> | Partida: {partida} | RENSPA: {renspa}</text>

    <!-- Ventana de Visualizacion del Mapa / Imagen Satelital -->
    <rect x="40" y="125" width="720" height="345" rx="12" fill="#09140f" stroke="rgba(255,255,255,0.1)" stroke-width="1.5"/>
    
    {image_bg_xml}

    <!-- Parcelas de los Lotes Delimitadas -->
    {parcelas_xml}

    <!-- Rosa de los vientos / Brujula Cartografica -->
    <g transform="translate(735, 155)">
        <circle cx="0" cy="0" r="18" fill="rgba(0,0,0,0.7)" stroke="rgba(255,255,255,0.25)" stroke-width="1.5"/>
        <path d="M 0 -13 L 4 0 L 0 3 L -4 0 Z" fill="#ef4444"/>
        <path d="M 0 13 L 4 0 L 0 -3 L -4 0 Z" fill="#94a3b8"/>
        <text x="0" y="-15" font-family="'JetBrains Mono', monospace" font-size="9" fill="#ef4444" font-weight="bold" text-anchor="middle">N</text>
    </g>

    <!-- Barra Inferior de Escala y Resumen -->
    <rect x="25" y="475" width="750" height="30" rx="6" fill="rgba(0,0,0,0.6)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
    <text x="40" y="495" font-size="10" fill="#94a3b8">🌾 Total Lotes: <tspan fill="#ffffff" font-weight="bold">{n_lotes}</tspan> | Cartografía Agronómica IA Desk Agro 2026/2027</text>
    <text x="760" y="495" font-family="'JetBrains Mono', monospace" font-size="10" fill="#10b981" text-anchor="end">● {badge_satelital}</text>
</svg>"""
    return svg_content


def obtener_campos_con_lotes() -> list:
    """
    Retorna la lista de todos los campos registrados con su información completa
    y sus lotes desglosados en objetos estructurados para facilitar la edición.
    """
    campos_json_path = settings.FILES_STORAGE_DIR / "registro_campos.json"
    try:
        with open(campos_json_path, "r", encoding="utf-8") as f:
            campos_doc = json.load(f)
    except Exception:
        campos_doc = {"campos": []}

    campos_lista = campos_doc.get("campos", [])

    # Cargar lotes de registro_lotes.json para emparejar
    lotes_json_path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
    try:
        with open(lotes_json_path, "r", encoding="utf-8") as f:
            lotes_doc = json.load(f)
            lotes_globales = lotes_doc.get("lotes", [])
    except Exception:
        lotes_globales = []

    for c in campos_lista:
        c_nombre = c.get("nombre", "")
        c_id = c.get("id", "")
        
        # Buscar en base de datos ORM primero
        campo_orm = Campo.objects.filter(nombre=c_nombre).first()
        lotes_detallados = []
        
        if campo_orm:
            if not c.get("titular") and campo_orm.titular:
                c["titular"] = campo_orm.titular
            if not c.get("tenencia") and campo_orm.tenencia:
                c["tenencia"] = campo_orm.tenencia
            if not c.get("provincia") and campo_orm.provincia:
                c["provincia"] = campo_orm.provincia
            if not c.get("coordenadas_gps") and campo_orm.coordenadas_gps:
                c["coordenadas_gps"] = campo_orm.coordenadas_gps
            if not c.get("partida") and campo_orm.partida_inmobiliaria:
                c["partida"] = campo_orm.partida_inmobiliaria
            if not c.get("renspa") and campo_orm.renspa:
                c["renspa"] = campo_orm.renspa

            for lote_orm in campo_orm.lotes.all():
                lotes_detallados.append({
                    "nombre": lote_orm.nombre,
                    "superficie_ha": float(lote_orm.superficie_ha),
                    "cultivo": lote_orm.cultivo_actual or "Soja de 1ra",
                    "variedad": lote_orm.variedad_hibrido or ""
                })

        if not lotes_detallados:
            for lg in lotes_globales:
                lg_campo = lg.get("campo", "")
                if lg_campo.lower() == c_nombre.lower() or lg.get("nombre", "").lower().endswith(c_nombre.lower()):
                    l_nom = lg.get("nombre", "").replace(f" - {c_nombre}", "")
                    lotes_detallados.append({
                        "nombre": l_nom,
                        "superficie_ha": float(lg.get("superficie_ha", 0)),
                        "cultivo": lg.get("cultivo", "Agrícola"),
                        "variedad": lg.get("variedad", "")
                    })

        if not lotes_detallados and c.get("lotes"):
            for l_str in c.get("lotes", []):
                m = re.match(r'^(.*?)\s*\(([\d\.]+)\s*ha(?:\s*-\s*(.*?))?\)', str(l_str))
                if m:
                    lotes_detallados.append({
                        "nombre": m.group(1).strip(),
                        "superficie_ha": float(m.group(2)),
                        "cultivo": (m.group(3) or "Soja de 1ra").strip(),
                        "variedad": ""
                    })
                else:
                    lotes_detallados.append({
                        "nombre": str(l_str),
                        "superficie_ha": float(c.get("superficie_ha", 100)),
                        "cultivo": "Agrícola",
                        "variedad": ""
                    })

        # Reconciliar superficie_ha y lotes si estaban en 0 o vacios
        try:
            cur_sup = float(str(c.get("superficie_ha", 0)).replace(",", "."))
        except Exception:
            cur_sup = 0.0

        if cur_sup <= 0.0 and lotes_detallados:
            tot_sup = sum(float(l.get("superficie_ha", 0)) for l in lotes_detallados)
            c["superficie_ha"] = tot_sup
            c["superficie_agricola_ha"] = tot_sup
            c["lotes"] = [f"{l['nombre']} ({l['superficie_ha']} ha - {l['cultivo']})" for l in lotes_detallados]

        # Descubrir foto aerea original subida
        slug_c = slugify(c_nombre).replace("-", "_")
        for candidate_ext in [".jpg", ".jpeg", ".png", ".webp"]:
            f_p = settings.BASE_DIR / "media" / "campos" / f"{slug_c}{candidate_ext}"
            if f_p.exists():
                c["foto_url"] = f"/media/campos/{slug_c}{candidate_ext}"
                break

        c["lotes_detallados"] = lotes_detallados

    return campos_lista


def registrar_nuevo_campo(datos: dict, archivo_diagrama=None) -> dict:
    """
    Registra o Modifica un campo completo en el sistema IA Desk Agro:
    1. Base de datos SQLite Django (Modelo Campo y Lote)
    2. files_storage/registro_campos.json (leido por el dashboard e IA)
    3. files_storage/registro_lotes.json (para los lotes del campo)
    4. files_storage/MEMORY.md (memoria de negocio del agente IA)
    5. Media (guarda diagrama cargado o regenera SVG cartografico actualizado)
    """
    nombre = datos.get("nombre", "").strip()
    if not nombre:
        raise ValueError("El nombre del campo es obligatorio.")

    campo_id = datos.get("campo_id", "").strip()
    original_nombre = datos.get("original_nombre", "").strip()
    es_modificacion = bool(campo_id or (original_nombre and original_nombre != nombre))

    try:
        superficie_total = Decimal(str(datos.get("superficie_total_ha", "0")).replace(",", "."))
    except Exception:
        superficie_total = Decimal("0.00")

    try:
        superficie_agricola = Decimal(str(datos.get("superficie_agricola_ha", superficie_total)).replace(",", "."))
    except Exception:
        superficie_agricola = superficie_total

    titular = datos.get("titular", "Propio").strip() or "Propio"
    tenencia = datos.get("tenencia", "Propio").strip() or "Propio"
    sector = datos.get("sector", "Sector Agricola Operativo").strip() or "Sector Agricola Operativo"
    ubicacion = datos.get("ubicacion", "").strip()
    provincia = datos.get("provincia", "Buenos Aires").strip() or "Buenos Aires"
    partida = datos.get("partida_inmobiliaria", "").strip()
    renspa = datos.get("renspa", "").strip()
    coordenadas_gps = datos.get("coordenadas_gps", "").strip()
    tipo_suelo = datos.get("tipo_suelo", "").strip() or "Argiudol tipico con drenaje optimo"
    indice_productividad = datos.get("indice_productividad", "").strip()
    instalaciones = datos.get("instalaciones_clave", "").strip()
    cultivos = datos.get("cultivos_campana", "").strip()
    descripcion = datos.get("descripcion", "").strip()

    lotes_raw = datos.get("lotes", [])
    if isinstance(lotes_raw, str):
        try:
            lotes_list = json.loads(lotes_raw)
        except Exception:
            lotes_list = []
    else:
        lotes_list = lotes_raw or []

    # 1. Guardar o Modificar en SQLite Django ORM (Campo)
    campo_orm = None
    if original_nombre:
        campo_orm = Campo.objects.filter(nombre=original_nombre).first()
    if not campo_orm and nombre:
        campo_orm = Campo.objects.filter(nombre=nombre).first()

    defaults_dict = {
        "nombre": nombre,
        "titular": titular,
        "tenencia": tenencia,
        "sector": sector,
        "ubicacion": ubicacion,
        "provincia": provincia,
        "superficie_total_ha": superficie_total,
        "superficie_agricola_ha": superficie_agricola,
        "partida_inmobiliaria": partida,
        "renspa": renspa,
        "coordenadas_gps": coordenadas_gps,
        "tipo_suelo": tipo_suelo,
        "indice_productividad": indice_productividad,
        "instalaciones": instalaciones,
        "cultivos_principales": cultivos,
        "descripcion": descripcion,
    }

    if campo_orm:
        for k, v in defaults_dict.items():
            setattr(campo_orm, k, v)
        campo_orm.save()
        es_modificacion = True
    else:
        campo_orm = Campo.objects.create(**defaults_dict)

    # 2. Guardar o Generar Diagrama / Cartografia
    campos_media_dir = settings.BASE_DIR / "media" / "campos"
    campos_media_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(nombre).replace("-", "_") or "campo_agro"

    # Guardar archivo si fue subido
    saved_img_path = None
    if archivo_diagrama:
        ext = os.path.splitext(archivo_diagrama.name)[1].lower() or ".jpg"
        file_path = campos_media_dir / f"{slug}{ext}"
        with open(file_path, "wb+") as dest:
            for chunk in archivo_diagrama.chunks():
                dest.write(chunk)
        saved_img_path = str(file_path)
    else:
        # Si no se subio archivo nuevo, verificar si ya existe foto aerea previa
        for candidate_ext in [".jpg", ".jpeg", ".png", ".webp"]:
            c_p = campos_media_dir / f"{slug}{candidate_ext}"
            if c_p.exists():
                saved_img_path = str(c_p)
                break

    # Siempre generar el plano cartografico vectorial proyectando los lotes sobre la imagen aerea si existe
    svg_code = generar_diagrama_campo_svg({
        "nombre": nombre,
        "superficie_ha": float(superficie_total),
        "sector": sector,
        "provincia": provincia,
        "ubicacion": ubicacion,
        "coordenadas_gps": coordenadas_gps or "-33.8942, -60.5731",
        "tenencia": tenencia,
        "partida": partida or "S/D",
        "renspa": renspa or "S/D"
    }, lotes_list, imagen_fondo_path=saved_img_path)

    svg_path = campos_media_dir / f"{slug}_cartografia.svg"
    with open(svg_path, "w", encoding="utf-8") as sf:
        sf.write(svg_code)

    diagrama_url = f"/media/campos/{slug}_cartografia.svg"
    diagrama_nombre = f"Cartografia y Parcelas IA Desk Agro - {nombre} ({superficie_total} Has)"

    campo_orm.diagrama_url = diagrama_url
    campo_orm.save(update_fields=["diagrama_url"])

    # 3. Guardar / Actualizar Lotes en Django ORM
    for l_item in lotes_list:
        l_nombre = l_item.get("nombre", "").strip()
        if not l_nombre:
            continue
        try:
            l_ha = Decimal(str(l_item.get("superficie_ha", "0")).replace(",", "."))
        except Exception:
            l_ha = Decimal("10.00")
        
        Lote.objects.update_or_create(
            campo=campo_orm,
            nombre=l_nombre,
            defaults={
                "superficie_ha": l_ha,
                "tipo_suelo": tipo_suelo,
                "cultivo_actual": l_item.get("cultivo", ""),
                "variedad_hibrido": l_item.get("variedad", ""),
                "activo": True
            }
        )

    # 4. Actualizar files_storage/registro_campos.json
    campos_json_path = settings.FILES_STORAGE_DIR / "registro_campos.json"
    try:
        with open(campos_json_path, "r", encoding="utf-8") as f:
            campos_doc = json.load(f)
    except Exception:
        campos_doc = {"establecimiento_general": "IA Desk Agro", "campana": "2026/2027", "campos": []}

    lista_campos = campos_doc.get("campos", [])
    
    existing_campo = None
    if campo_id:
        existing_campo = next((c for c in lista_campos if c.get("id") == campo_id), None)
    if not existing_campo and original_nombre:
        existing_campo = next((c for c in lista_campos if c.get("nombre", "").lower() == original_nombre.lower()), None)
    if not existing_campo and nombre:
        existing_campo = next((c for c in lista_campos if c.get("nombre", "").lower() == nombre.lower()), None)

    if existing_campo:
        campo_assigned_id = existing_campo.get("id", f"CAMPO-{len(lista_campos):02d}")
        es_modificacion = True
    else:
        campo_assigned_id = f"CAMPO-{len(lista_campos) + 1:02d}"

    lotes_formatted = []
    for l in lotes_list:
        ln = l.get("nombre", "Lote")
        lh = l.get("superficie_ha", "")
        lc = l.get("cultivo", "")
        desc_lote = f"{ln} ({lh} ha - {lc})" if lc else f"{ln} ({lh} ha)"
        lotes_formatted.append(desc_lote)

    if not lotes_formatted:
        lotes_formatted = [f"Lote Principal ({superficie_agricola} ha - {cultivos or 'Agricola'})"]

    campo_entry = {
        "id": campo_assigned_id,
        "nombre": nombre,
        "sector": sector,
        "ubicacion": f"{ubicacion} ({provincia})" if (ubicacion and provincia and provincia.lower() not in ubicacion.lower()) else (ubicacion or provincia),
        "superficie_ha": float(superficie_total),
        "superficie_agricola_ha": float(superficie_agricola),
        "tenencia": tenencia,
        "titular": titular,
        "coordenadas_gps": coordenadas_gps,
        "partida": partida,
        "renspa": renspa,
        "lotes": lotes_formatted,
        "instalaciones_clave": instalaciones or "Puesto de control, caminos afirmados",
        "tipo_suelo": tipo_suelo,
        "cultivos_campana": cultivos or "Soja / Maiz",
        "diagrama_url": diagrama_url,
        "diagrama_nombre": diagrama_nombre,
        "descripcion": descripcion or f"Establecimiento agropecuario {nombre} registrado en IA Desk Agro."
    }

    if existing_campo:
        existing_campo.update(campo_entry)
    else:
        lista_campos.append(campo_entry)

    campos_doc["campos"] = lista_campos
    with open(campos_json_path, "w", encoding="utf-8") as f:
        json.dump(campos_doc, f, indent=2, ensure_ascii=False)

    # 5. Actualizar files_storage/registro_lotes.json con los lotes
    lotes_json_path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
    try:
        with open(lotes_json_path, "r", encoding="utf-8") as f:
            lotes_doc = json.load(f)
    except Exception:
        lotes_doc = {"campana": "2026/2027", "lotes": []}

    lista_lotes = lotes_doc.get("lotes", [])
    for idx, l in enumerate(lotes_list):
        ln = l.get("nombre", f"Lote {idx+1}")
        try:
            lha = float(str(l.get("superficie_ha", "0")).replace(",", "."))
        except Exception:
            lha = 0.0

        target_lote_name = f"{ln} - {nombre}"
        existing_l = next((x for x in lista_lotes if x.get("nombre", "").lower() == target_lote_name.lower() or 
                           (original_nombre and x.get("nombre", "").lower() == f"{ln} - {original_nombre}".lower())), None)
        
        lote_entry_data = {
            "nombre": target_lote_name,
            "superficie_ha": lha,
            "cultivo": l.get("cultivo", "Agricola"),
            "variedad": l.get("variedad", "S/D"),
            "estado_actual": "Registrado en IA Desk Agro",
            "hibridos_plantados": l.get("variedad", "S/D"),
            "diagrama_url": diagrama_url,
            "diagrama_nombre": f"Cartografia {ln} ({nombre})",
            "campo": nombre
        }

        if existing_l:
            existing_l.update(lote_entry_data)
        else:
            lote_entry_data["id"] = f"LOTE-{len(lista_lotes) + 1:02d}"
            lote_entry_data["labores"] = []
            lote_entry_data["cosecha"] = {"fecha": None, "humedad_pct": None, "rinde_total_kg": None, "rinde_kg_ha": None, "rinde_qq_ha": None}
            lista_lotes.append(lote_entry_data)

    lotes_doc["lotes"] = lista_lotes
    with open(lotes_json_path, "w", encoding="utf-8") as f:
        json.dump(lotes_doc, f, indent=2, ensure_ascii=False)

    # 6. Registrar en MEMORY.md
    memory_path = settings.FILES_STORAGE_DIR / "MEMORY.md"
    if memory_path.exists():
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                mem_text = f.read()
            action_desc = "Actualizado / Modificado" if es_modificacion else "Nuevo Campo Incorporado"
            note = f"\n- **{action_desc} ({datetime.now().strftime('%Y-%m-%d %H:%M')}):** {nombre} ({superficie_total} ha) ubicado en {ubicacion} ({provincia}). Tenencia: {tenencia}. Lotes: {', '.join(lotes_formatted)}.\n"
            with open(memory_path, "a", encoding="utf-8") as f:
                f.write(note)
        except Exception:
            pass

    campo_entry["lotes_detallados"] = lotes_list
    campo_entry["es_modificacion"] = es_modificacion
    return campo_entry


# ==============================================================
# ASISTENCIA Y CONSULTAS INTELIGENTES DE CAMPOS Y LOTES
# ==============================================================

def normalizar_texto(text: str) -> str:
    """Normaliza texto a minusculas y sin acentos para comparaciones robustas."""
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return text.strip()


def buscar_campo_en_mensaje(msg: str, campos_list: list = None) -> dict:
    """
    Identifica de forma inteligente y dinamica si el mensaje del usuario refiere
    a alguno de los campos o establecimientos cargados en el sistema.
    """
    if campos_list is None:
        campos_list = obtener_campos_con_lotes()

    m = normalizar_texto(msg)
    prefixes = ['campo ', 'establecimiento ', 'estancia ', 'finca ', 'predio ', 'lote ']

    # 1. Coincidencia exacta con nombre completo normalizado
    for c in campos_list:
        c_full = normalizar_texto(c.get('nombre', ''))
        if c_full and c_full in m:
            return c

    # 2. Coincidencia con nombre limpio de prefijos (ej: "don lorenzo", "don alfredo", "la paulina")
    for c in campos_list:
        c_clean = normalizar_texto(c.get('nombre', ''))
        for p in prefixes:
            if c_clean.startswith(p):
                c_clean = c_clean[len(p):].strip()
        if len(c_clean) >= 3 and c_clean in m:
            return c

    # 3. Coincidencia por palabra clave distintiva (>= 4 caracteres que no sean stopwords)
    stopwords = {'para', 'sobre', 'todo', 'gran', 'alta', 'norte', 'este', 'oeste', 'lote', 'zona', 'base', 'pata'}
    for c in campos_list:
        c_clean = normalizar_texto(c.get('nombre', ''))
        for p in prefixes:
            if c_clean.startswith(p):
                c_clean = c_clean[len(p):].strip()
        words = [w for w in c_clean.split() if len(w) >= 4 and w not in stopwords]
        for w in words:
            if re.search(r'\b' + re.escape(w) + r'\b', m):
                return c

    # 4. Aliases historicos o de zona
    if 'bajo grande' in m:
        for c in campos_list:
            if 'san jose' in normalizar_texto(c.get('nombre', '')):
                return c

    return None


def buscar_lote_en_campo(msg: str, campo: dict) -> dict:
    """
    Busca si el mensaje menciona una parcela o lote particular perteneciente al campo.
    """
    m = normalizar_texto(msg)
    lotes_det = campo.get("lotes_detallados", [])
    if not lotes_det:
        lotes_str = campo.get("lotes", [])
        for ls in lotes_str:
            if normalizar_texto(ls) in m:
                return {"nombre": ls, "superficie_ha": "-", "cultivo": "-", "variedad": "-"}

    for l in lotes_det:
        l_nom = normalizar_texto(l.get("nombre", ""))
        if l_nom and l_nom in m:
            return l

        # Extraccion de digito o letra de lote (ej: "lote 1", "lote 2", "lote a")
        match_num = re.search(r'(?:lote|parcela)\s*([0-9a-zA-Z]+)', l_nom)
        if match_num:
            val = match_num.group(1)
            if re.search(r'\b(?:lote|parcela)\s*' + re.escape(val) + r'\b', m) or re.search(r'\blote' + re.escape(val) + r'\b', m):
                return l

    return None


def generar_respuesta_campo(target_campo: dict, specific_lote: dict = None, is_diag_only: bool = False, query_prompt: str = "") -> str:
    """
    Genera una respuesta en Markdown completa, profesional y rica sobre el campo o lote consultado.
    """
    c_nom = target_campo.get("nombre", "Campo")
    c_sec = target_campo.get("sector", "Sector Productivo")
    c_ubi = target_campo.get("ubicacion", "-")
    c_sup = target_campo.get("superficie_ha", "-")
    c_sup_agri = target_campo.get("superficie_agricola_ha") or c_sup
    c_ten = target_campo.get("tenencia") or "Propio"
    c_tit = target_campo.get("titular") or "Titular Registrado"
    c_gps = target_campo.get("coordenadas_gps") or "S/D"
    c_partida = target_campo.get("partida") or "S/D"
    c_renspa = target_campo.get("renspa") or "S/D"
    c_infra = target_campo.get("instalaciones_clave", "-")
    c_suelo = target_campo.get("tipo_suelo", "-")
    c_cult = target_campo.get("cultivos_campana", "-")
    c_desc = target_campo.get("descripcion", "")
    c_diag_url = target_campo.get("diagrama_url", "")
    c_diag_nom = target_campo.get("diagrama_nombre") or f"Cartografia de {c_nom}"

    m_prompt = normalizar_texto(query_prompt)

    # 1. Caso Lote Especifico
    if specific_lote:
        l_nom = specific_lote.get("nombre", "Lote")
        l_sup = specific_lote.get("superficie_ha", "-")
        l_cult = specific_lote.get("cultivo", "-")
        l_var = specific_lote.get("variedad") or specific_lote.get("hibridos_plantados") or "Sin variedad especificada"
        l_est = specific_lote.get("estado_actual", "Registrado en IA Desk Agro")

        # Buscar foto original subida
        slug_c = slugify(c_nom).replace("-", "_")
        c_foto_url = target_campo.get("foto_url")
        if not c_foto_url:
            for candidate_ext in [".jpg", ".jpeg", ".png", ".webp"]:
                f_p = settings.BASE_DIR / "media" / "campos" / f"{slug_c}{candidate_ext}"
                if f_p.exists():
                    c_foto_url = f"/media/campos/{slug_c}{candidate_ext}"
                    break

        reply = (
            f"🌱 **Información Agronómica - {l_nom} ({c_nom}):**\n\n"
            f"• 🌾 **Cultivo / Variedad:** **{l_cult}**" + (f" ({l_var})" if l_var and l_var != l_cult and l_var != "S/D" else "") + f"\n"
            f"• 📐 **Superficie de la Parcela:** **{l_sup} hectáreas**\n"
            f"• 📍 **Establecimiento:** {c_nom} ({c_sec} - {c_ubi})\n"
            f"• 📋 **Estado Actual:** {l_est}\n"
            f"• 🔬 **Tipo de Suelo:** {c_suelo}\n\n"
        )

        # Labores del lote
        lotes_json_path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
        if lotes_json_path.exists():
            try:
                with open(lotes_json_path, "r", encoding="utf-8") as fl:
                    for lr in json.load(fl).get("lotes", []):
                        if (c_nom.lower() in lr.get("campo", "").lower() or lr.get("campo", "").lower() in c_nom.lower()) and (l_nom.lower() in lr.get("nombre", "").lower() or lr.get("nombre", "").lower() in l_nom.lower()):
                            labores = lr.get("labores", [])
                            if labores:
                                reply += "🚜 **Historial de Labores Registradas en este Lote:**\n"
                                for lab in labores[-3:]:
                                    reply += f"• **{lab.get('fecha')} - {lab.get('labor')}:** {lab.get('combustible_litros', 0)} L gasoil"
                                    if lab.get('semilla') and lab.get('semilla') != "-":
                                        reply += f" | Semilla: {lab.get('semilla')}"
                                    if lab.get('fertilizante') and lab.get('fertilizante') != "-":
                                        reply += f" | Fertilizante: {lab.get('fertilizante')}"
                                    reply += "\n"
                                reply += "\n"
                            break
            except Exception:
                pass

        if c_foto_url:
            reply += (
                f"📸 **Fotografía Aérea del Establecimiento (Imagen Original Subida):**\n"
                f"![Fotografía Aérea de {c_nom}]({c_foto_url})\n\n"
            )

        if c_diag_url and c_diag_url != c_foto_url:
            reply += (
                f"🗺️ **Plano y Cartografía Parcelaria:**\n"
                f"![{c_diag_nom}]({c_diag_url})\n\n"
                f"*Plano cartográfico oficial de {c_nom} con delimitación de parcelas.*"
            )
        return reply

    # 2. Caso Ficha Completa de Campo
    lotes_det = target_campo.get("lotes_detallados", [])
    
    # Reconciliar superficie total si figuraba en 0
    try:
        c_sup_num = float(str(c_sup).replace("Has", "").replace("ha", "").replace(",", ".").strip())
    except Exception:
        c_sup_num = 0.0

    if c_sup_num <= 0.0 and lotes_det:
        c_sup_num = sum(float(l.get("superficie_ha", 0)) for l in lotes_det)
        c_sup = f"{c_sup_num:,.1f}".replace(".0", "")
        c_sup_agri = c_sup

    # Cargar labores registradas por lote para enriquecer descripcion
    lotes_json_path = settings.FILES_STORAGE_DIR / "registro_lotes.json"
    lotes_registrados_dict = {}
    if lotes_json_path.exists():
        try:
            with open(lotes_json_path, "r", encoding="utf-8") as fl:
                for lr in json.load(fl).get("lotes", []):
                    l_key = lr.get("nombre", "").lower()
                    lotes_registrados_dict[l_key] = lr
        except Exception:
            pass

    if lotes_det:
        lotes_lines = []
        for l in lotes_det:
            ln = l.get("nombre", "Lote")
            lh = l.get("superficie_ha", "-")
            lc = l.get("cultivo", "Agrícola")
            lv = l.get("variedad") or l.get("hibridos_plantados") or ""
            var_str = f" • Variedad: **{lv}**" if lv and lv != "S/D" and lv != lc else ""

            # Labores realizadas en este lote
            lr_data = next((v for k, v in lotes_registrados_dict.items() if (c_nom.lower() in v.get("campo", "").lower() or v.get("campo", "").lower() in c_nom.lower()) and (ln.lower() in k or k in ln.lower())), None)
            lab_str = ""
            if lr_data and lr_data.get("labores"):
                lab_noms = [str(x.get("labor", "Labor")) for x in lr_data.get("labores", [])]
                if len(lab_noms) <= 2:
                    lab_str = " • *Labores:* " + ", ".join(lab_noms)
                else:
                    lab_str = f" • *Labores:* {len(lab_noms)} registradas ({lab_noms[-1]})"

            lotes_lines.append(f"  - 🔹 **{ln}:** **{lh} ha** • Cultivo: **{lc}**{var_str}{lab_str}")
        lotes_str = "\n".join(lotes_lines)
    else:
        lotes_raw = target_campo.get("lotes", [])
        lotes_str = "\n".join([f"  - 🔹 {l}" for l in lotes_raw]) if lotes_raw else "  - 🔹 Lote general sin subdividir"

    intro = ""
    if any(w in m_prompt for w in ["permite preguntar", "recien pregunte", "no la que cargue", "agregue", "cargue"]):
        intro = f"¡Por supuesto! En **IA Desk Agro** puedes consultar en todo momento la información de todos los campos que cargues o modifiques.\n\n"

    reply = (
        intro +
        f"🗺️ **Ficha Operativa y Cartografía - {c_nom} ({c_sup} Has):**\n\n"
        f"• 📍 **Ubicación & Sector:** {c_sec} ({c_ubi})\n"
        f"• 📐 **Superficie:** **{c_sup} Has Totales** (Agrícola: **{c_sup_agri} Has**)\n"
        f"• 👤 **Titular & Tenencia:** **{c_tit}** • Régimen: **{c_ten}**\n"
        f"• 🌐 **Coordenadas GPS:** `{c_gps}`\n"
    )

    if c_partida != "S/D" or c_renspa != "S/D":
        reply += f"• 📑 **Datos Catastrales:** Partida: `{c_partida}` | RENSPA: `{c_renspa}`\n"

    reply += (
        f"• 🌾 **Cultivo Principal de Campaña:** **{c_cult}**\n"
        f"• 🚜 **Lotes y Parcelas Registradas:**\n{lotes_str}\n"
        f"• 🏗️ **Infraestructura:** {c_infra}\n"
        f"• 🔬 **Tipo de Suelo:** {c_suelo}\n"
        f"• 📋 **Detalle Operativo:** {c_desc}\n\n"
    )

    # Identificar foto aerea original subida
    slug_c = slugify(c_nom).replace("-", "_")
    c_foto_url = target_campo.get("foto_url")
    if not c_foto_url:
        for candidate_ext in [".jpg", ".jpeg", ".png", ".webp"]:
            f_p = settings.BASE_DIR / "media" / "campos" / f"{slug_c}{candidate_ext}"
            if f_p.exists():
                c_foto_url = f"/media/campos/{slug_c}{candidate_ext}"
                break

    # Mostrar la fotografia aerea tal como la subio el productor
    if c_foto_url:
        reply += (
            f"📸 **Fotografía Aérea del Establecimiento (Imagen Original Subida):**\n"
            f"![Fotografía Aérea de {c_nom}]({c_foto_url})\n\n"
        )

    # Mostrar tambien la cartografia parcelaria georreferenciada con los lotes delimitados
    if c_diag_url and c_diag_url != c_foto_url:
        reply += (
            f"🗺️ **Plano Cartográfico de Parcelas y Lotes Georreferenciados:**\n"
            f"![{c_diag_nom}]({c_diag_url})\n\n"
            f"*Cartografía georreferenciada oficial de {c_nom} con delimitación de parcelas.*"
        )
    elif not c_foto_url and not c_diag_url:
        reply += "📷 *Este campo aún no tiene plano o diagrama registrado.*"

    return reply


def generar_resumen_todos_los_campos(campos_list: list = None, show_diagrams: bool = False) -> str:
    """
    Genera un resumen consolidado de todos los campos activos en IA Desk Agro.
    """
    if campos_list is None:
        campos_list = obtener_campos_con_lotes()

    total_ha = sum(float(c.get("superficie_ha", 0) or 0) for c in campos_list)
    total_agri = sum(float(c.get("superficie_agricola_ha", 0) or c.get("superficie_ha", 0) or 0) for c in campos_list)

    intro = (
        f"🗺️ **Campos y Establecimientos Registrados en IA Desk Agro:**\n\n"
        f"Tienes actualmente **{len(campos_list)} establecimientos** registrados con una superficie total de **{total_ha:,.1f} Has** (**{total_agri:,.1f} Has agrícolas**):\n\n"
    )
    sections = []
    for idx, c in enumerate(campos_list, 1):
        c_nom = c.get("nombre", "Campo")
        c_sup = c.get("superficie_ha", "-")
        c_ubi = c.get("ubicacion", "-")
        c_sec = c.get("sector", "")
        c_cult = c.get("cultivos_campana", "-")
        c_ten = c.get("tenencia", "Propio")
        c_tit = c.get("titular", "-")
        c_lotes = c.get("lotes", [])
        l_summary = ", ".join(c_lotes[:3]) if c_lotes else "Sin lotes subdivididos"
        if len(c_lotes) > 3:
            l_summary += f" y {len(c_lotes) - 3} más..."
        c_diag_url = c.get("diagrama_url", "")
        c_diag_nom = c.get("diagrama_nombre", f"Plano {c_nom}")

        sec_text = (
            f"### {idx}. 🌾 **{c_nom}** ({c_sup} Has)\n"
            f"• 📍 **Ubicación:** {c_ubi} • *Sector:* {c_sec}\n"
            f"• 👤 **Titular & Tenencia:** {c_tit} ({c_ten})\n"
            f"• 🌾 **Cultivo principal:** {c_cult}\n"
            f"• 🚜 **Lotes:** {l_summary}\n"
        )
        if show_diagrams and c_diag_url:
            sec_text += f"\n![{c_diag_nom}]({c_diag_url})\n"
        sections.append(sec_text)

    footer = (
        f"\n💡 *Puedes consultarme en detalle por cualquiera de ellos (por ejemplo: '¿Qué información tengo de Establecimiento Don Lorenzo?' o 'Lote 1 de Don Lorenzo') o pedirme registrar nuevas labores sobre sus parcelas.*"
    )
    return intro + "\n".join(sections) + footer
