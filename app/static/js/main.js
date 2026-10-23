document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    // Disable browser and OS autocorrect, autocapitalize, and spellcheck on user input
    if (userInput) {
        userInput.setAttribute('autocomplete', 'off');
        userInput.setAttribute('autocorrect', 'off');
        userInput.setAttribute('autocapitalize', 'none');
        userInput.setAttribute('spellcheck', 'false');
        userInput.setAttribute('data-gramm', 'false');
        userInput.setAttribute('data-enable-grammarly', 'false');
        userInput.setAttribute('data-ms-editor', 'false');
    }

    const btnSend = document.getElementById('btn-send');
    const messagesList = document.getElementById('messages-list');
    const btnClearChat = document.getElementById('btn-clear-chat');
    const quickChips = document.querySelectorAll('.chip-btn');
    
    // Live metrics elements for the 4 fuel tanks
    const metricCisterna = document.getElementById('metric-cisterna');
    const barCisterna = document.getElementById('bar-cisterna');
    const metricTGrande = document.getElementById('metric-t-grande');
    const barTGrande = document.getElementById('bar-t-grande');
    const metricTChico = document.getElementById('metric-t-chico');
    const barTChico = document.getElementById('bar-t-chico');
    const metricAcopio = document.getElementById('metric-acopio');
    const metricTotCampo = document.getElementById('metric-tot-campo');
    const metricTotAcopio = document.getElementById('metric-tot-acopio');

    // Agricultural inputs metrics
    const metricSemSoja = document.getElementById('metric-sem-soja');
    const metricMap = document.getElementById('metric-map');
    const metricGlifo = document.getElementById('metric-glifo');

    // WhatsApp Simulator elements
    const btnOpenWhatsapp = document.getElementById('btn-open-whatsapp');
    const whatsappModal = document.getElementById('whatsapp-modal');
    const waModalCloseBtn = document.getElementById('wa-modal-close-btn');
    const waPresetBtns = document.querySelectorAll('.wa-preset-btn');
    const waCustomMsg = document.getElementById('wa-custom-msg');
    const btnSendWaCustom = document.getElementById('btn-send-wa-custom');

    // Storage Inspector elements
    const inspectorModal = document.getElementById('inspector-modal');
    const btnOpenInspector = document.getElementById('btn-open-inspector');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalFileTabs = document.getElementById('modal-file-tabs');
    const modalFileContent = document.getElementById('modal-file-content');
    const btnRefreshInspector = document.getElementById('btn-refresh-inspector');
    const storageFileRows = document.querySelectorAll('.storage-file-row');

    let currentInspectedFile = 'stock_gasoil.json';

    const scrollToBottom = () => {
        messagesList.scrollTop = messagesList.scrollHeight;
    };

    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
    });

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    const updateLiveMetrics = (stockData) => {
        if (!stockData) return;

        // 1. Cisterna Planta
        if (stockData.cisterna_planta) {
            const actual = Number(stockData.cisterna_planta.actual);
            const max = Number(stockData.cisterna_planta.max) || 22000;
            if (metricCisterna) metricCisterna.textContent = `${actual.toLocaleString('es-AR')} L`;
            if (barCisterna) barCisterna.style.width = `${Math.min(100, Math.round((actual / max) * 100))}%`;
        }

        // 2. Tanque Grande
        if (stockData.tanque_grande) {
            const actual = Number(stockData.tanque_grande.actual);
            const max = Number(stockData.tanque_grande.max) || 5000;
            if (metricTGrande) metricTGrande.textContent = `${actual.toLocaleString('es-AR')} L`;
            if (barTGrande) barTGrande.style.width = `${Math.min(100, Math.round((actual / max) * 100))}%`;
        }

        // 3. Tanque Chico
        if (stockData.tanque_chico) {
            const actual = Number(stockData.tanque_chico.actual);
            const max = Number(stockData.tanque_chico.max) || 3000;
            if (metricTChico) metricTChico.textContent = `${actual.toLocaleString('es-AR')} L`;
            if (barTChico) barTChico.style.width = `${Math.min(100, Math.round((actual / max) * 100))}%`;
        }

        // 4. Acopio por Retirar
        if (stockData.acopio_por_retirar !== undefined && metricAcopio) {
            metricAcopio.textContent = `${Number(stockData.acopio_por_retirar).toLocaleString('es-AR')} L`;
        }

        // Totales
        if (stockData.total_campo !== undefined && metricTotCampo) {
            metricTotCampo.textContent = `${Number(stockData.total_campo).toLocaleString('es-AR')} L`;
        }
        if (stockData.total_con_acopio !== undefined && metricTotAcopio) {
            metricTotAcopio.textContent = `${Number(stockData.total_con_acopio).toLocaleString('es-AR')} L`;
        }

        // Insumos
        if (metricSemSoja && stockData.semillas_soja !== undefined) {
            metricSemSoja.textContent = stockData.semillas_soja;
        }
        if (metricMap && stockData.map_tn !== undefined) {
            metricMap.textContent = `${stockData.map_tn} tn`;
        }
        if (metricGlifo && stockData.glifosato_lts !== undefined) {
            metricGlifo.textContent = `${stockData.glifosato_lts} L`;
        }

        // Maíz por Híbrido (Bolsas en Planta vs Por Retirar)
        if (stockData.maiz_totales) {
            const mPlanta = document.getElementById("metric-maiz-planta");
            const mRetiro = document.getElementById("metric-maiz-retiro");
            const mTotal = document.getElementById("metric-maiz-total");
            const mBadge = document.getElementById("metric-maiz-total-badge");
            if (mPlanta) mPlanta.textContent = stockData.maiz_totales.bolsas_en_planta;
            if (mRetiro) mRetiro.textContent = stockData.maiz_totales.bolsas_por_retirar;
            if (mTotal) mTotal.textContent = `${stockData.maiz_totales.total_general_bolsas} bolsas`;
            if (mBadge) mBadge.textContent = `${stockData.maiz_totales.total_general_bolsas} bolsas`;
        }
        if (stockData.maiz_hibridos && Array.isArray(stockData.maiz_hibridos)) {
            stockData.maiz_hibridos.forEach(h => {
                const elP = document.getElementById(`val-${h.id}-planta`);
                const elR = document.getElementById(`val-${h.id}-retiro`);
                if (elP) elP.textContent = `${h.en_planta_bolsas} b.`;
                if (elR) elR.textContent = `${h.por_retirar_bolsas} b.`;
            });
        }

        // Granos en Silos de Guardado y Acopio (Toneladas)
        if (stockData.granos_silos) {
            const gs = stockData.granos_silos;
            const elTotal = document.getElementById("metric-granos-total-tn");
            const elBadge = document.getElementById("metric-granos-total-badge");
            const elPrinc = document.getElementById("metric-principales-tn");
            const elTrilla = document.getElementById("metric-trilla-tn");

            if (elTotal && gs.total_general_tn !== undefined) {
                elTotal.textContent = `${Number(gs.total_general_tn).toLocaleString("es-AR")} Tn`;
            }
            if (elBadge && gs.total_general_tn !== undefined && gs.capacidad_total_tn !== undefined) {
                elBadge.textContent = `${Number(gs.total_general_tn).toLocaleString("es-AR")} / ${Number(gs.capacidad_total_tn).toLocaleString("es-AR")} Tn`;
            }
            if (elPrinc && gs.stock_principales_tn !== undefined && gs.capacidad_principales_tn !== undefined) {
                elPrinc.textContent = `${Number(gs.stock_principales_tn).toLocaleString("es-AR")} / ${Number(gs.capacidad_principales_tn).toLocaleString("es-AR")} Tn`;
            }
            if (elTrilla && gs.stock_trilla_tn !== undefined && gs.capacidad_trilla_tn !== undefined) {
                elTrilla.textContent = `${Number(gs.stock_trilla_tn).toLocaleString("es-AR")} / ${Number(gs.capacidad_trilla_tn).toLocaleString("es-AR")} Tn`;
            }

            if (gs.silos_principales && Array.isArray(gs.silos_principales)) {
                gs.silos_principales.forEach(s => {
                    const elS = document.getElementById(`val-silo-${s.id}`);
                    if (elS) elS.textContent = `${Number(s.stock_actual_tn).toLocaleString("es-AR")} Tn`;
                });
            }
            if (gs.silos_trilla && Array.isArray(gs.silos_trilla)) {
                gs.silos_trilla.forEach(s => {
                    const elS = document.getElementById(`val-silo-${s.id}`);
                    if (elS) elS.textContent = `${Number(s.stock_actual_tn).toLocaleString("es-AR")} Tn`;
                });
            }
        }

        // Fertilizantes en Kilogramos (kg)
        if (stockData.fertilizantes_totales) {
            const elFG = document.getElementById("metric-fert-galpon");
            const elFR = document.getElementById("metric-fert-retiro");
            const elFT = document.getElementById("metric-fert-total");
            const elFB = document.getElementById("metric-fert-total-badge");
            if (elFG) elFG.textContent = `${Number(stockData.fertilizantes_totales.en_galpon_kg).toLocaleString("es-AR")} kg`;
            if (elFR) elFR.textContent = `${Number(stockData.fertilizantes_totales.por_retirar_kg).toLocaleString("es-AR")} kg`;
            if (elFT) elFT.textContent = `${Number(stockData.fertilizantes_totales.total_general_kg).toLocaleString("es-AR")} kg`;
            if (elFB) elFB.textContent = `${Number(stockData.fertilizantes_totales.total_general_kg).toLocaleString("es-AR")} kg`;
        }
        if (stockData.fertilizantes && Array.isArray(stockData.fertilizantes)) {
            stockData.fertilizantes.forEach(f => {
                const elG = document.getElementById(`val-fert-${f.id}-galpon`);
                const elR = document.getElementById(`val-fert-${f.id}-retiro`);
                if (elG) elG.textContent = `${Number(f.en_galpon_kg).toLocaleString("es-AR")} kg`;
                if (elR) elR.textContent = `${Number(f.por_retirar_kg).toLocaleString("es-AR")} kg`;
            });
        }

        // Insumos & Fitosanitarios (En Galpón vs A Retirar)
        if (stockData.fitosanitarios_totales) {
            const elPG = document.getElementById("metric-fito-galpon");
            const elPR = document.getElementById("metric-fito-retiro");
            const elPB = document.getElementById("metric-fito-total-badge");
            if (elPG) elPG.textContent = `${Number(stockData.fitosanitarios_totales.en_galpon_litros).toLocaleString("es-AR")} L`;
            if (elPR) elPR.textContent = `${Number(stockData.fitosanitarios_totales.a_retirar_litros).toLocaleString("es-AR")} L`;
            if (elPB) elPB.textContent = `${Number(stockData.fitosanitarios_totales.total_general_litros).toLocaleString("es-AR")} L`;
        }
        if (stockData.fitosanitarios && Array.isArray(stockData.fitosanitarios)) {
            stockData.fitosanitarios.forEach(f => {
                const elG = document.getElementById(`val-fito-${f.id}-galpon`);
                const elR = document.getElementById(`val-fito-${f.id}-retiro`);
                if (elG) elG.textContent = `${Number(f.en_galpon).toLocaleString("es-AR")} L`;
                if (elR) elR.textContent = `${Number(f.a_retirar).toLocaleString("es-AR")} L`;
            });
        }
    };

    const appendUserMessage = (text) => {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const card = document.createElement('div');
        card.className = 'message-card user-card';
        card.innerHTML = `
            <div class="avatar user-avatar">👨‍🌾</div>
            <div class="message-body">
                <div class="message-meta">
                    <span class="sender-name">Productor</span>
                    <span class="timestamp">${time}</span>
                </div>
                <div class="message-content">
                    <p>${escapeHtml(text)}</p>
                </div>
            </div>
        `;
        messagesList.appendChild(card);
        scrollToBottom();
    };

    const appendWhatsAppMessage = (text, sender = "Juan (Tractorista)") => {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const card = document.createElement('div');
        card.className = 'message-card user-card';
        card.innerHTML = `
            <div class="avatar user-avatar" style="background: linear-gradient(135deg, #10b981, #059669);">📱</div>
            <div class="message-body wa-chat-bubble">
                <div class="wa-chat-header">
                    <span>🟢 Reporte de WhatsApp • ${escapeHtml(sender)}</span>
                    <span class="timestamp" style="margin-left: auto;">${time}</span>
                </div>
                <div class="wa-waveform">
                    <span>▶ ılılıllı Nota de voz transcrita</span>
                </div>
                <div class="message-content">
                    <p><em>"${escapeHtml(text)}"</em></p>
                </div>
            </div>
        `;
        messagesList.appendChild(card);
        scrollToBottom();
    };

    const appendBotMessage = (text, toolCalls = [], proposal = null) => {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const card = document.createElement('div');
        card.className = 'message-card bot-card';

        let toolHtml = '';
        if (toolCalls && toolCalls.length > 0) {
            toolHtml = `<div class="tool-call-banner">`;
            const hasWrite = toolCalls.some(tc => tc.tool === 'write_file' || tc.tool === 'append_memory' || tc.tool === 'update_memory');
            const hasRead = toolCalls.some(tc => tc.tool === 'read_file');

            if (hasRead) {
                toolHtml += `
                    <div class="tool-header-row">
                        <span class="tool-icon">🔍</span>
                        <span>Consultando planillas de combustible e inventarios del campo...</span>
                    </div>
                `;
            }
            if (hasWrite) {
                toolHtml += `
                    <div class="tool-header-row" style="margin-top: 4px;">
                        <span class="tool-icon">💾</span>
                        <span>Actualizando depósitos de gasoil y bitácora operativa en tiempo real...</span>
                    </div>
                `;
            }
            toolHtml += `</div>`;
        }

        const formattedText = formatMarkdownLike(text);

        let proposalHtml = '';
        if (proposal) {
            proposalHtml = `
                <div class="proposal-box-interactive" id="prop-box-${proposal.idempotency_token}">
                    <div class="proposal-badge-header">
                        <span>⚠️ Vista Previa de Movimiento — Requiere Confirmación</span>
                    </div>
                    <table class="proposal-table-mini">
                        <tr><td><strong>Operación:</strong></td><td>${escapeHtml(proposal.labor || 'Consumo reportado')}</td></tr>
                        <tr><td><strong>Depósito:</strong></td><td>${escapeHtml(proposal.deposito_nombre || 'Tanque')}</td></tr>
                        <tr><td><strong>Cantidad:</strong></td><td><strong style="color: #6ee7b7;">${proposal.litros || proposal.cantidad} L</strong></td></tr>
                        <tr><td><strong>Saldo Actual:</strong></td><td>${proposal.saldo_actual ? Number(proposal.saldo_actual).toLocaleString('es-AR') + ' L' : '-'}</td></tr>
                        <tr><td><strong>Saldo Resultante:</strong></td><td><strong style="color: #38bdf8;">${proposal.saldo_proyectado ? Number(proposal.saldo_proyectado).toLocaleString('es-AR') + ' L' : '-'}</strong></td></tr>
                        ${proposal.lote_nombre ? `<tr><td><strong>Lote:</strong></td><td>${escapeHtml(proposal.lote_nombre)}</td></tr>` : ''}
                    </table>
                    <div class="proposal-buttons-row">
                        <button type="button" class="btn-confirm-prop" data-token="${proposal.idempotency_token}">
                            ✅ Confirmar y Asentar en Base de Datos
                        </button>
                        <button type="button" class="btn-cancel-prop" data-token="${proposal.idempotency_token}">
                            ❌ Descartar
                        </button>
                    </div>
                </div>
            `;
        }

        card.innerHTML = `
            <div class="avatar bot-avatar">🌾</div>
            <div class="message-body">
                <div class="message-meta">
                    <span class="sender-name">IA Desk Agro</span>
                    <span class="timestamp">${time}</span>
                </div>
                ${toolHtml}
                <div class="message-content">
                    ${formattedText}
                    ${proposalHtml}
                </div>
            </div>
        `;

        if (proposal) {
            const btnConf = card.querySelector('.btn-confirm-prop');
            const btnCanc = card.querySelector('.btn-cancel-prop');
            if (btnConf) {
                btnConf.addEventListener('click', async () => {
                    btnConf.disabled = true;
                    btnConf.textContent = 'Asentando en BD...';
                    try {
                        const cRes = await fetch('/api/chat/confirmar/', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ proposal: proposal, idempotency_token: btnConf.dataset.token })
                        });
                        const cData = await cRes.json();
                        if (cData.status === 'success') {
                            const box = document.getElementById(`prop-box-${btnConf.dataset.token}`);
                            if (box) {
                                box.innerHTML = `<div style="color: #10b981; font-weight: 700; padding: 6px 0;">✓ Movimiento asentado exitosamente en Base de Datos (Asiento #${cData.data.movimiento_id || 'OK'})</div>`;
                            }
                            if (cData.stock_data) updateLiveMetrics(cData.stock_data);
                        } else {
                            alert('Error al confirmar: ' + cData.message);
                            btnConf.disabled = false;
                            btnConf.textContent = 'Reintentar Confirmación';
                        }
                    } catch (e) {
                        alert('Error de conexión.');
                        btnConf.disabled = false;
                    }
                });
            }
            if (btnCanc) {
                btnCanc.addEventListener('click', () => {
                    const box = document.getElementById(`prop-box-${btnCanc.dataset.token}`);
                    if (box) {
                        box.innerHTML = `<div style="color: var(--text-muted); font-size: 0.82rem; font-style: italic;">Propuesta descartada sin modificar existencias.</div>`;
                    }
                });
            }
        }

        messagesList.appendChild(card);
        scrollToBottom();
    };

    const showLoading = () => {
        const loadingCard = document.createElement('div');
        loadingCard.id = 'chat-loading-card';
        loadingCard.className = 'message-card bot-card';
        loadingCard.innerHTML = `
            <div class="avatar bot-avatar">🌾</div>
            <div class="message-body">
                <div class="loading-indicator">
                    <span class="spinner-dot">⚙️</span>
                    <span>Procesando depósitos y ejecutando cálculos matemáticos con Claude...</span>
                </div>
            </div>
        `;
        messagesList.appendChild(loadingCard);
        scrollToBottom();
    };

    const removeLoading = () => {
        const loadingCard = document.getElementById('chat-loading-card');
        if (loadingCard) loadingCard.remove();
    };

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = userInput.value.trim();
        if (!text) return;

        appendUserMessage(text);
        userInput.value = '';
        userInput.style.height = 'auto';
        btnSend.disabled = true;
        showLoading();

        try {
            const res = await fetch('/api/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            const data = await res.json();
            removeLoading();

            if (data.status === 'success') {
                appendBotMessage(data.data.response, data.data.tool_calls, data.data.proposal);
                if (data.data.stock_data) updateLiveMetrics(data.data.stock_data);
            } else {
                appendBotMessage('⚠️ Error: ' + (data.message || 'No se pudo procesar la consulta'));
            }
        } catch (err) {
            removeLoading();
            appendBotMessage('⚠️ Error de conexión con el servidor local.');
            console.error(err);
        } finally {
            btnSend.disabled = false;
        }
    });

    const sendWhatsAppReport = async (msg, sender) => {
        whatsappModal.classList.add('hidden');
        appendWhatsAppMessage(msg, sender);
        showLoading();

        try {
            const res = await fetch('/api/whatsapp-simulator/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg, sender: sender, is_audio: true })
            });

            const data = await res.json();
            removeLoading();

            if (data.status === 'success') {
                appendBotMessage(data.data.response, data.data.tool_calls, data.data.proposal);
                if (data.data.stock_data) updateLiveMetrics(data.data.stock_data);
            } else {
                appendBotMessage('⚠️ Error procesando reporte de WhatsApp: ' + (data.message || 'Error'));
            }
        } catch (err) {
            removeLoading();
            appendBotMessage('⚠️ Error de conexión con el simulador.');
            console.error(err);
        }
    };

    btnOpenWhatsapp.addEventListener('click', () => {
        whatsappModal.classList.remove('hidden');
    });

    waModalCloseBtn.addEventListener('click', () => {
        whatsappModal.classList.add('hidden');
    });

    waPresetBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const msg = btn.dataset.msg;
            const sender = btn.dataset.sender;
            sendWhatsAppReport(msg, sender);
        });
    });

    btnSendWaCustom.addEventListener('click', () => {
        const msg = waCustomMsg.value.trim();
        if (!msg) return;
        waCustomMsg.value = '';
        sendWhatsAppReport(msg, "Encargado de Campo");
    });

    quickChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.dataset.query;
            if (query) {
                userInput.value = query;
                chatForm.dispatchEvent(new Event('submit'));
            }
        });
    });

    btnClearChat.addEventListener('click', async () => {
        if (!confirm('¿Deseas reiniciar la memoria de conversación?')) return;
        try {
            const res = await fetch('/api/reset-history/', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                messagesList.innerHTML = `
                    <div class="message-card bot-card">
                        <div class="avatar bot-avatar">🌾</div>
                        <div class="message-body">
                            <div class="message-meta">
                                <span class="sender-name">IA Desk Agro</span>
                                <span class="timestamp">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                            </div>
                            <div class="message-content">
                                <p>¡Hola! Bienvenido a IA Desk Agro, tu copiloto operativo.</p>
                                <p>¿En qué puedo ayudarte hoy?</p>
                            </div>
                        </div>
                    </div>
                `;
            }
        } catch (e) {
            alert('Error al reiniciar.');
        }
    });

    // Planillas Inspector
    const availableFiles = ['stock_gasoil.json', 'stock_insumos.json', 'registro_lotes.json', 'INDEX.md', 'MEMORY.md'];

    const renderTabs = () => {
        modalFileTabs.innerHTML = '';
        availableFiles.forEach(file => {
            const btn = document.createElement('button');
            btn.className = `modal-tab-btn ${file === currentInspectedFile ? 'active' : ''}`;
            btn.textContent = file;
            btn.addEventListener('click', () => {
                currentInspectedFile = file;
                renderTabs();
                loadInspectFile(file);
            });
            modalFileTabs.appendChild(btn);
        });
    };

    const loadInspectFile = async (filename) => {
        modalFileContent.textContent = `Cargando ${filename}...`;
        document.getElementById('modal-file-title').textContent = `Inspeccionando: ${filename}`;
        try {
            const res = await fetch(`/api/storage/${filename}/`);
            const data = await res.json();
            if (data.status === 'success') {
                modalFileContent.textContent = data.content;
            } else {
                modalFileContent.textContent = 'Error cargando archivo.';
            }
        } catch (e) {
            modalFileContent.textContent = 'Error de conexión.';
        }
    };

    btnOpenInspector.addEventListener('click', () => {
        renderTabs();
        loadInspectFile(currentInspectedFile);
        inspectorModal.classList.remove('hidden');
    });

    modalCloseBtn.addEventListener('click', () => {
        inspectorModal.classList.add('hidden');
    });

    btnRefreshInspector.addEventListener('click', () => {
        loadInspectFile(currentInspectedFile);
    });

    storageFileRows.forEach(row => {
        row.addEventListener('click', () => {
            const fname = row.dataset.filename;
            if (fname) {
                currentInspectedFile = fname;
                renderTabs();
                loadInspectFile(fname);
                inspectorModal.classList.remove('hidden');
            }
        });
    });

    function formatMarkdownLike(str) {
        if (!str) return '';
        let html = escapeHtml(str);
        // Soporte para imágenes / diagramas de lotes
        html = html.replace(/!\[(.*?)\]\((.*?)\)/g, 
            '<div class="chat-diagram-card">' +
                '<img src="$2" alt="$1" class="chat-diagram-img" onclick="window.open(\'$2\', \'_blank\')">' +
                '<div class="chat-diagram-caption">' +
                    '<span>🗺️ <strong>$1</strong></span> <span class="caption-zoom">(Clic para ver en tamaño completo)</span>' +
                '</div>' +
            '</div>'
        );
        html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="chat-link" style="color:#6ee7b7;text-decoration:underline;">$1</a>');
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/`(.*?)`/g, '<code>$1</code>');
        const lines = html.split('\n');
        let formatted = '';
        lines.forEach(line => {
            const trimmed = line.trim();
            if (trimmed.startsWith('<div class="chat-diagram-card">') || trimmed.startsWith('</div>') || trimmed.startsWith('<div') || trimmed.startsWith('<img') || trimmed.startsWith('<span')) {
                formatted += trimmed;
            } else if (trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
                formatted += `<p style="margin-left: 14px;">• ${trimmed.substring(2)}</p>`;
            } else if (trimmed.startsWith('#')) {
                const headerText = trimmed.replace(/^#+\s*/, '');
                formatted += `<h4 style="margin: 8px 0 4px; color: #a7f3d0;">${headerText}</h4>`;
            } else if (trimmed) {
                formatted += `<p>${trimmed}</p>`;
            }
        });
        return formatted;
    }

    const btnSyncSheets = document.getElementById('btn-sync-sheets-now');
    const driveLastSync = document.getElementById('drive-last-sync');

    if (btnSyncSheets) {
        btnSyncSheets.addEventListener('click', async () => {
            const originalText = btnSyncSheets.innerHTML;
            btnSyncSheets.innerHTML = '🔄 Sincronizando...';
            btnSyncSheets.disabled = true;

            try {
                const res = await fetch('/api/sheets/sync/', { method: 'POST' });
                const json = await res.json();
                if (json.status === 'success') {
                    if (driveLastSync) {
                        const now = new Date();
                        driveLastSync.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    }
                    alert('✅ Hojas de cálculo sincronizadas con éxito.\nEl archivo IA_Desk_Agro_Consolidado.xlsx y los CSVs han sido actualizados con los últimos movimientos.');
                }
            } catch (err) {
                console.error('Error sincronizando hojas:', err);
                alert('⚠️ Error al sincronizar hojas de cálculo.');
            } finally {
                btnSyncSheets.innerHTML = originalText;
                btnSyncSheets.disabled = false;
            }
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ==============================================================
    // CARTOGRAFÍA Y DIAGRAMAS DE CAMPOS: PESTAÑAS Y CONSULTA RÁPIDA
    // ==============================================================
    const campoTabBtns = document.querySelectorAll('.campo-tab-btn');
    campoTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.targetCampo;
            campoTabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.campo-panel-content').forEach(panel => {
                if (panel.id === targetId) {
                    panel.classList.remove('hidden');
                } else {
                    panel.classList.add('hidden');
                }
            });
        });
    });

    document.querySelectorAll('.btn-consult-campo').forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.dataset.campoQuery;
            if (query && userInput) {
                userInput.value = query;
                chatForm.dispatchEvent(new Event('submit'));
                const chatCard = document.querySelector('.chat-card');
                if (chatCard) chatCard.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });

    // ==============================================================
    // GESTIÓN DE LOTES: PESTAÑAS, PREVIEW Y GUARDADO DE HÍBRIDOS / PLANOS
    // ==============================================================
    const loteTabBtns = document.querySelectorAll('.lote-tab-btn');
    loteTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.targetLote;
            loteTabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.lote-panel-content').forEach(panel => {
                if (panel.id === targetId) {
                    panel.classList.remove('hidden');
                } else {
                    panel.classList.add('hidden');
                }
            });
        });
    });

    document.querySelectorAll('.lote-file-input').forEach(input => {
        input.addEventListener('change', () => {
            const loteId = input.dataset.loteId;
            const labelEl = document.getElementById(`file-name-${loteId}`);
            if (input.files && input.files[0]) {
                const file = input.files[0];
                if (labelEl) labelEl.textContent = file.name;

                const reader = new FileReader();
                reader.onload = (re) => {
                    const previewBox = document.getElementById(`preview-box-${loteId}`);
                    if (previewBox) {
                        previewBox.innerHTML = `
                            <div class="current-diagram-wrapper">
                                <img src="${re.target.result}" alt="Vista previa" class="lote-thumb-img" onclick="window.open('${re.target.result}', '_blank')">
                                <div class="diagram-info-meta">
                                    <span class="diagram-filename">📷 ${file.name} (Por guardar)</span>
                                    <span class="diagram-hint">Presiona 'Guardar Lote' para confirmar el almacenamiento</span>
                                </div>
                            </div>
                        `;
                    }
                };
                reader.readAsDataURL(file);
            }
        });
    });

    document.querySelectorAll('.lote-update-form').forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const loteId = form.dataset.loteId;
            const statusEl = document.getElementById(`save-status-${loteId}`);
            const submitBtn = form.querySelector('.btn-save-lote');

            const formData = new FormData(form);
            formData.append('lote_id', loteId);

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = '⏳ Guardando...';
            }

            try {
                const res = await fetch('/api/lotes/update/', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.status === 'success') {
                    if (statusEl) {
                        statusEl.textContent = '✓ Guardado exitosamente';
                        statusEl.classList.remove('hidden');
                        setTimeout(() => statusEl.classList.add('hidden'), 3500);
                    }
                    if (data.lote && data.lote.diagrama_url) {
                        const previewBox = document.getElementById(`preview-box-${loteId}`);
                        if (previewBox) {
                            previewBox.innerHTML = `
                                <div class="current-diagram-wrapper">
                                    <img src="${data.lote.diagrama_url}" alt="Diagrama ${data.lote.nombre}" class="lote-thumb-img" onclick="window.open('${data.lote.diagrama_url}', '_blank')">
                                    <div class="diagram-info-meta">
                                        <span class="diagram-filename">🗺️ ${data.lote.diagrama_nombre || 'Plano guardado'}</span>
                                        <span class="diagram-hint">(Clic en la imagen para ampliar en pestaña nueva)</span>
                                    </div>
                                </div>
                            `;
                        }
                    }
                } else {
                    alert('Error: ' + (data.message || 'No se pudo guardar el lote.'));
                }
            } catch (err) {
                alert('Error al comunicar con el servidor.');
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = '💾 Guardar Lote';
                }
            }
        });
    });


    // ==============================================================
    // FIELD DATA MULTI-MODULE NAVIGATION & DIRECT FORMS
    // ==============================================================

    window.switchTab = function(tabName) {
        document.querySelectorAll('.nav-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        document.querySelectorAll('.module-tab-content').forEach(sec => {
            sec.classList.toggle('hidden', sec.id !== `module-${tabName}`);
        });
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    document.querySelectorAll('.nav-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.tab) switchTab(btn.dataset.tab);
        });
    });

    window.openDirectForm = function(formType) {
        switchTab('registros');
        let targetId = 'form-consumo';
        if (formType.includes('traslado')) targetId = 'form-traslado';
        else if (formType.includes('ingreso') || formType.includes('compra')) targetId = 'form-ingreso';
        else if (formType.includes('insumo')) targetId = 'form-insumos';

        document.querySelectorAll('.subnav-btn').forEach(b => {
            b.classList.toggle('active', b.dataset.form === targetId);
        });
        document.querySelectorAll('.direct-form-card').forEach(card => {
            card.classList.toggle('hidden', card.id !== targetId);
        });
    };

    // Subtabs in Registros
    document.querySelectorAll('.subnav-btn').forEach(b => {
        b.addEventListener('click', () => {
            const formId = b.dataset.form;
            document.querySelectorAll('.subnav-btn').forEach(btn => btn.classList.remove('active'));
            b.classList.add('active');
            document.querySelectorAll('.direct-form-card').forEach(card => {
                card.classList.toggle('hidden', card.id !== formId);
            });
        });
    });

    // Handle AJAX Direct Forms submission
    const handleDirectFormSubmit = async (formElement) => {
        const feedback = document.getElementById('form-feedback-alert');
        feedback.className = 'form-feedback hidden';
        feedback.textContent = '';

        const formData = new FormData(formElement);
        const payload = {};
        formData.forEach((val, key) => payload[key] = val);

        const submitBtn = formElement.querySelector('button[type="submit"]');
        const origText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Procesando asiento...';

        try {
            const res = await fetch('/api/movimientos/crear/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();

            if (data.status === 'success') {
                feedback.className = 'form-feedback success';
                feedback.textContent = `✓ ${data.message}`;
                formElement.reset();
                if (data.stock_data) updateLiveMetrics(data.stock_data);

                // Add to table if present
                if (data.data) {
                    const tbody = document.querySelector('#table-movimientos tbody');
                    if (tbody) {
                        const tr = document.createElement('tr');
                        tr.className = 'mov-row';
                        tr.innerHTML = `
                            <td>Hoy</td>
                            <td><span class="badge-tipo">Movimiento Reciente</span></td>
                            <td><strong>${payload.insumo_id ? 'Insumo' : 'Gasoil Grado 2'}</strong></td>
                            <td><strong class="text-emerald">${payload.litros || payload.cantidad} L</strong></td>
                            <td>${payload.lote_id || '-'}</td>
                            <td>${payload.deposito_codigo || payload.destino_codigo || '-'}</td>
                            <td>${payload.labor || 'Asiento directo'}</td>
                            <td>${payload.operario || 'Productor'}</td>
                            <td><span class="text-cyan">${data.data.saldo_posterior || '-'}</span></td>
                        `;
                        tbody.insertBefore(tr, tbody.firstChild);
                    }
                }
            } else {
                feedback.className = 'form-feedback error';
                feedback.textContent = `⚠️ Error: ${data.message || 'No se pudo registrar'}`;
            }
        } catch (err) {
            feedback.className = 'form-feedback error';
            feedback.textContent = '⚠️ Error de conexión con el servidor.';
            console.error(err);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = origText;
        }
    };

    ['ajax-form-consumo', 'ajax-form-traslado', 'ajax-form-ingreso', 'ajax-form-insumos'].forEach(id => {
        const form = document.getElementById(id);
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                handleDirectFormSubmit(form);
            });
        }
    });

    // Real-time Search and Filter on Movements Table
    const searchInput = document.getElementById('filter-search-input');
    const filterTipo = document.getElementById('filter-tipo-mov');
    const filterLote = document.getElementById('filter-lote-select');

    const applyTableFilters = () => {
        const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
        const tipoVal = (filterTipo ? filterTipo.value : '').toLowerCase();
        const loteVal = (filterLote ? filterLote.value : '').toLowerCase();

        document.querySelectorAll('.mov-row').forEach(row => {
            const textSearch = (row.dataset.search || row.textContent).toLowerCase();
            const rowTipo = (row.dataset.tipo || '').toLowerCase();
            const rowLote = (row.dataset.lote || '').toLowerCase();

            const matchesQuery = !query || textSearch.includes(query);
            const matchesTipo = !tipoVal || rowTipo.includes(tipoVal);
            const matchesLote = !loteVal || rowLote.includes(loteVal);

            row.style.display = (matchesQuery && matchesTipo && matchesLote) ? '' : 'none';
        });
    };

    if (searchInput) searchInput.addEventListener('input', applyTableFilters);
    if (filterTipo) filterTipo.addEventListener('change', applyTableFilters);
    if (filterLote) filterLote.addEventListener('change', applyTableFilters);
});
