// ============================================================================
// IA DESK AGRO - SCRIPT DE AUTO-SINCRONIZACION GOOGLE SHEETS & DRIVE
// Compatible con:
// 1. Libro Consolidado General (Combustibles, Insumos, Granos, Bitacora)
// 2. Libros por Cultivo: Maíz, Soja Primera, Soja Segunda, Trigo (Solapas por Campo y Lote)
// Establecimiento Agropecuario "La Esperanza" (Campaña 2026/2027)
// ============================================================================

var DEFAULT_API_URL = "https://violet-years-carry.loca.lt/api/sheets/live-data/";

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('🚜 IA Desk Agro')
    .addItem('🔄 Sincronizar Esta Hoja (Detección Automática)', 'sincronizarIADesk')
    .addSeparator()
    .addItem('🌽 Sincronizar Cultivo Maíz (Por Campos)', 'sincronizarMaiz')
    .addItem('🌱 Sincronizar Soja Primera (Por Campos)', 'sincronizarSojaPrimera')
    .addItem('🌿 Sincronizar Soja Segunda (Por Campos)', 'sincronizarSojaSegunda')
    .addItem('🌾 Sincronizar Cultivo Trigo (Por Campos)', 'sincronizarTrigo')
    .addItem('📊 Sincronizar Consolidado General', 'sincronizarConsolidado')
    .addSeparator()
    .addItem('⏰ Activar Auto-Sincronización (Cada 5 min)', 'crearTriggerAutomatico')
    .addItem('🛑 Desactivar Auto-Sincronización', 'eliminarTriggers')
    .addSeparator()
    .addItem('⚙️ Configurar URL Servidor IA Desk', 'configurarUrl')
    .addToUi();
}

function getApiUrl() {
  var props = PropertiesService.getScriptProperties();
  return props.getProperty('API_URL') || DEFAULT_API_URL;
}

function configurarUrl() {
  var ui = SpreadsheetApp.getUi();
  var actual = getApiUrl();
  var respuesta = ui.prompt(
    'Configuración de Servidor IA Desk Agro',
    'Ingresa la URL pública de live-data (ej. https://violet-years-carry.loca.lt/api/sheets/live-data/):',
    ui.ButtonSet.OK_CANCEL
  );

  if (respuesta.getSelectedButton() == ui.Button.OK) {
    var nuevaUrl = respuesta.getResponseText().trim();
    if (nuevaUrl) {
      PropertiesService.getScriptProperties().setProperty('API_URL', nuevaUrl);
      ui.alert('URL guardada exitosamente: ' + nuevaUrl);
    }
  }
}

function fetchIADeskData() {
  var url = getApiUrl();
  var options = {
    muteHttpExceptions: true,
    headers: {
      "Bypass-Tunnel-Reminder": "true"
    }
  };
  var response = UrlFetchApp.fetch(url, options);
  if (response.getResponseCode() !== 200) {
    throw new Error('No se pudo conectar con IA Desk Agro (Código ' + response.getResponseCode() + '). Verifica que el túnel esté activo.');
  }
  var data = JSON.parse(response.getContentText());
  if (data.status !== "success") {
    throw new Error('Respuesta no válida del servidor.');
  }
  return data;
}

function sincronizarIADesk() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var name = ss.getName().toLowerCase();

  try {
    var data = fetchIADeskData();

    if (name.indexOf('maiz') !== -1 || name.indexOf('maíz') !== -1) {
      actualizarCultivo(ss, 'maiz', data.cultivos ? data.cultivos.maiz : null);
    } else if (name.indexOf('segunda') !== -1 || name.indexOf('2da') !== -1) {
      actualizarCultivo(ss, 'soja_segunda', data.cultivos ? data.cultivos.soja_segunda : null);
    } else if (name.indexOf('soja') !== -1) {
      actualizarCultivo(ss, 'soja_primera', data.cultivos ? data.cultivos.soja_primera : null);
    } else if (name.indexOf('trigo') !== -1) {
      actualizarCultivo(ss, 'trigo', data.cultivos ? data.cultivos.trigo : null);
    } else {
      // Por defecto o consolidado maestro
      actualizarConsolidado(ss, data);
    }

    SpreadsheetApp.getActiveSpreadsheet().toast('Hoja sincronizada correctamente con IA Desk Agro', '✅ IA Desk Agro', 5);
  } catch (err) {
    SpreadsheetApp.getUi().alert('Error al sincronizar: ' + err.message);
  }
}

function sincronizarMaiz() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var data = fetchIADeskData();
    actualizarCultivo(ss, 'maiz', data.cultivos ? data.cultivos.maiz : null);
    ss.toast('Cultivo de Maíz sincronizado por campos', '🌽 Maíz', 5);
  } catch(e) { SpreadsheetApp.getUi().alert('Error: ' + e.message); }
}

function sincronizarSojaPrimera() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var data = fetchIADeskData();
    actualizarCultivo(ss, 'soja_primera', data.cultivos ? data.cultivos.soja_primera : null);
    ss.toast('Soja 1ra sincronizada por campos', '🌱 Soja 1ra', 5);
  } catch(e) { SpreadsheetApp.getUi().alert('Error: ' + e.message); }
}

function sincronizarSojaSegunda() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var data = fetchIADeskData();
    actualizarCultivo(ss, 'soja_segunda', data.cultivos ? data.cultivos.soja_segunda : null);
    ss.toast('Soja 2da sincronizada por campos', '🌿 Soja 2da', 5);
  } catch(e) { SpreadsheetApp.getUi().alert('Error: ' + e.message); }
}

function sincronizarTrigo() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var data = fetchIADeskData();
    actualizarCultivo(ss, 'trigo', data.cultivos ? data.cultivos.trigo : null);
    ss.toast('Cultivo de Trigo sincronizado por campos', '🌾 Trigo', 5);
  } catch(e) { SpreadsheetApp.getUi().alert('Error: ' + e.message); }
}

function sincronizarConsolidado() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var data = fetchIADeskData();
    actualizarConsolidado(ss, data);
    ss.toast('Consolidado general maestro sincronizado', '📊 Consolidado', 5);
  } catch(e) { SpreadsheetApp.getUi().alert('Error: ' + e.message); }
}

// -------------------------------------------------------------
// ACTUALIZACION DE SOLAPAS POR CAMPO PARA UN CULTIVO
// -------------------------------------------------------------
function actualizarCultivo(ss, cropKey, cData) {
  if (!cData) return;

  var campos = ['La Esperanza', 'El Ombu', 'San Jose'];
  var headersLabores = [
    'FECHA', 'LOTE', 'SUPERFICIE (HA)', 'LABOR REALIZADA', 'MAQUINARIA / EQUIPO',
    'OPERARIO', 'GASOIL (L)', 'DEPÓSITO ORIGEN', 'SEMILLA USADA', 'FERTILIZANTE (KG)',
    'INSUMOS / FITO (L)', 'RINDE / COSECHA', 'ESTADO / OBSERVACIONES'
  ];

  for (var i = 0; i < campos.length; i++) {
    var campoNom = campos[i];
    var sheetNom = 'Campo ' + campoNom;
    var sheet = ss.getSheetByName(sheetNom);
    if (!sheet) {
      sheet = ss.insertSheet(sheetNom);
    }

    var filas = (cData.campos && cData.campos[campoNom]) ? cData.campos[campoNom] : [];
    
    // Encabezados en fila 4 si no existen
    if (sheet.getRange(4, 1).getValue() === "") {
      sheet.getRange(4, 1, 1, headersLabores.length).setValues([headersLabores]);
      sheet.getRange(4, 1, 1, headersLabores.length).setFontWeight("bold");
    }

    // Escribir labores
    if (filas.length > 0) {
      sheet.getRange(5, 1, filas.length, headersLabores.length).setValues(filas);
    }
  }

  // Actualizar Resumen si existe solapa
  var resSheet = ss.getSheetByName('Resumen 🌽') || ss.getSheetByName('Resumen 🌱') || ss.getSheetByName('Resumen 🌿') || ss.getSheetByName('Resumen 🌾') || ss.getSheetByName('Resumen');
  if (resSheet && cData.resumen && cData.resumen.length > 0) {
    resSheet.getRange(5, 1, cData.resumen.length, cData.resumen[0].length).setValues(cData.resumen);
  }
}

// -------------------------------------------------------------
// ACTUALIZACION DEL LIBRO CONSOLIDADO GENERAL
// -------------------------------------------------------------
function actualizarConsolidado(ss, data) {
  actualizarCombustibles(ss, data.combustibles);
  if (data.insumos_fertilizantes) {
    if (data.insumos_fertilizantes.fertilizantes) {
      actualizarFertilizantes(ss, data.insumos_fertilizantes.fertilizantes, data.insumos_fertilizantes.fertilizantes_totales);
    }
    if (data.insumos_fertilizantes.fitosanitarios) {
      actualizarInsumos(ss, data.insumos_fertilizantes.fitosanitarios, data.insumos_fertilizantes.fitosanitarios_totales);
    }
    if (data.insumos_fertilizantes.semillas_maiz) {
      actualizarSemillas(ss, data.insumos_fertilizantes.semillas_maiz);
    }
  }
  if (data.granos_silos) actualizarGranos(ss, data.granos_silos);
  if (data.bitacora_reciente) actualizarBitacora(ss, data.bitacora_reciente);
}

function actualizarCombustibles(ss, cData) {
  var sheet = ss.getSheetByName('Combustibles');
  if (!sheet || !cData) return;
  var deps = cData.depositos || {};

  sheet.getRange("D5").setValue(deps.cisterna_planta ? deps.cisterna_planta.stock_actual_litros : 0);
  sheet.getRange("D6").setValue(deps.tanque_grande ? deps.tanque_grande.stock_actual_litros : 0);
  sheet.getRange("D7").setValue(deps.tanque_chico ? deps.tanque_chico.stock_actual_litros : 0);
  sheet.getRange("D8").setValue(deps.acopio_por_retirar ? deps.acopio_por_retirar.litros_disponibles : 0);
}

function actualizarFertilizantes(ss, ferts, totales) {
  var sheet = ss.getSheetByName('Fertilizantes (kg)');
  if (!sheet || !ferts) return;

  for (var i = 0; i < ferts.length; i++) {
    var row = 5 + i;
    sheet.getRange(row, 4).setValue(ferts[i].en_galpon_kg || 0);
    sheet.getRange(row, 5).setValue(ferts[i].por_retirar_kg || 0);
    sheet.getRange(row, 7).setValue(ferts[i].total_kg || 0);
    sheet.getRange(row, 8).setValue((ferts[i].total_kg || 0) / 1000.0);
  }
}

function actualizarInsumos(ss, fitos, totales) {
  var sheet = ss.getSheetByName('Insumos y Fitosanitarios');
  if (!sheet || !fitos) return;

  for (var i = 0; i < fitos.length; i++) {
    var row = 5 + i;
    sheet.getRange(row, 4).setValue(fitos[i].en_galpon || 0);
    sheet.getRange(row, 5).setValue(fitos[i].a_retirar || 0);
    sheet.getRange(row, 7).setValue(fitos[i].total || 0);
  }
}

function actualizarSemillas(ss, mData) {
  var sheet = ss.getSheetByName('Semillas Maiz');
  if (!sheet || !mData || !mData.hibridos) return;
  var h = mData.hibridos;

  for (var i = 0; i < h.length; i++) {
    var row = 5 + i;
    sheet.getRange(row, 4).setValue(h[i].en_planta_bolsas || 0);
    sheet.getRange(row, 5).setValue(h[i].por_retirar_bolsas || 0);
    sheet.getRange(row, 7).setValue(h[i].total_bolsas || 0);
  }
}

function actualizarGranos(ss, gData) {
  var sheet = ss.getSheetByName('Granos Silos (Tn)');
  if (!sheet || !gData) return;

  var principales = gData.silos_principales || [];
  var trilla = gData.silos_trilla || [];
  var allUbic = principales.concat(trilla);
  if (allUbic.length === 0) {
    var sojaUbic = (gData.soja && gData.soja.ubicaciones) || [];
    var trigoUbic = (gData.trigo && gData.trigo.ubicaciones) || [];
    allUbic = sojaUbic.concat(trigoUbic);
  }

  for (var i = 0; i < allUbic.length; i++) {
    var row = 5 + i;
    sheet.getRange(row, 4).setValue(allUbic[i].stock_actual_tn || 0);
    sheet.getRange(row, 5).setValue(allUbic[i].capacidad_max_tn || 0);
  }
}

function actualizarBitacora(ss, lineas) {
  var sheet = ss.getSheetByName('Bitacora de Labores');
  if (!sheet || !lineas) return;

  for (var i = 0; i < lineas.length; i++) {
    var row = 5 + i;
    var line = lineas[lineas.length - 1 - i];
    var parts = line.split("] ");
    var dt = parts.length > 1 ? parts[0].replace("- [", "") : "Reciente";
    var desc = parts.length > 1 ? parts[1] : line;
    sheet.getRange(row, 1).setValue(dt);
    sheet.getRange(row, 2).setValue(desc);
    sheet.getRange(row, 4).setValue("Asentado");
  }
}

function crearTriggerAutomatico() {
  eliminarTriggers();
  ScriptApp.newTrigger('sincronizarIADesk')
    .timeBased()
    .everyMinutes(5)
    .create();
  SpreadsheetApp.getUi().alert('Sincronización automática activada cada 5 minutos.');
}

function eliminarTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  SpreadsheetApp.getUi().alert('Sincronización automática detenida.');
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    actualizarConsolidado(ss, data);
    return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "Hojas actualizadas" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
