// IA DESK AGRO - SCRIPT DE AUTO-SINCRONIZACION GOOGLE SHEETS
// Establecimiento Agropecuario "La Esperanza" (Campana 2026/2027)

var DEFAULT_API_URL = "https://violet-years-carry.loca.lt/api/sheets/live-data/";

function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('IA Desk Agro')
    .addItem('Sincronizar Todo Ahora', 'sincronizarIADesk')
    .addSeparator()
    .addItem('Activar Auto-Sincronizacion (Cada 5 min)', 'crearTriggerAutomatico')
    .addItem('Desactivar Auto-Sincronizacion', 'eliminarTriggers')
    .addSeparator()
    .addItem('Configurar URL Servidor', 'configurarUrl')
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
    'Configuracion de Servidor IA Desk Agro',
    'Ingresa la URL del endpoint live-data:',
    ui.ButtonSet.OK_CANCEL
  );

  if (respuesta.getSelectedButton() == ui.Button.OK) {
    var nuevaUrl = respuesta.getResponseText().trim();
    if (nuevaUrl) {
      PropertiesService.getScriptProperties().setProperty('API_URL', nuevaUrl);
      ui.alert('URL guardada: ' + nuevaUrl);
    }
  }
}

function sincronizarIADesk() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var url = getApiUrl();

  try {
    var options = {
      muteHttpExceptions: true,
      headers: {
        "Bypass-Tunnel-Reminder": "true"
      }
    };
    var response = UrlFetchApp.fetch(url, options);
    if (response.getResponseCode() !== 200) {
      SpreadsheetApp.getUi().alert(
        'No se pudo conectar con IA Desk Agro (' + response.getResponseCode() + ').\n\n' +
        'Verifica que el servidor local este ejecutandose.'
      );
      return;
    }

    var data = JSON.parse(response.getContentText());
    if (data.status !== "success") {
      throw new Error("Respuesta no valida del servidor.");
    }

    // 1. Actualizar Combustibles
    actualizarCombustibles(ss, data.combustibles);

    // 2. Actualizar Fertilizantes
    if (data.insumos_fertilizantes && data.insumos_fertilizantes.fertilizantes) {
      actualizarFertilizantes(ss, data.insumos_fertilizantes.fertilizantes, data.insumos_fertilizantes.fertilizantes_totales);
    }

    // 3. Actualizar Insumos y Fitosanitarios
    if (data.insumos_fertilizantes && data.insumos_fertilizantes.fitosanitarios) {
      actualizarInsumos(ss, data.insumos_fertilizantes.fitosanitarios, data.insumos_fertilizantes.fitosanitarios_totales);
    }

    // 4. Actualizar Semillas Maiz
    if (data.insumos_fertilizantes && data.insumos_fertilizantes.semillas_maiz) {
      actualizarSemillas(ss, data.insumos_fertilizantes.semillas_maiz);
    }

    // 5. Actualizar Granos en Silos
    if (data.granos_silos) {
      actualizarGranos(ss, data.granos_silos);
    }

    // 6. Actualizar Bitacora
    if (data.bitacora_reciente) {
      actualizarBitacora(ss, data.bitacora_reciente);
    }

    SpreadsheetApp.getActiveSpreadsheet().toast('Datos de IA Desk Agro sincronizados con exito', 'IA Desk Agro', 5);

  } catch (err) {
    SpreadsheetApp.getUi().alert('Error al sincronizar: ' + err.message);
  }
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

  var sojaUbic = (gData.soja && gData.soja.ubicaciones) || [];
  var trigoUbic = (gData.trigo && gData.trigo.ubicaciones) || [];
  var allUbic = sojaUbic.concat(trigoUbic);

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
  SpreadsheetApp.getUi().alert('Sincronizacion automatica activada cada 5 minutos.');
}

function eliminarTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  SpreadsheetApp.getUi().alert('Sincronizacion automatica detenida.');
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    if (data.combustibles) actualizarCombustibles(ss, data.combustibles);
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

    return ContentService.createTextOutput(JSON.stringify({ status: "success", message: "Hojas actualizadas" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
