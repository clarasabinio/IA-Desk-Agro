document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const btnSend = document.getElementById('btn-send');
    const messagesList = document.getElementById('messages-list');
    const btnClearChat = document.getElementById('btn-clear-chat');
    const quickChips = document.querySelectorAll('.chip-btn');
    
    // Live metrics
    const metricGasoil = document.getElementById('metric-gasoil');
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
        if (metricGasoil && stockData.gasoil_stock !== undefined) {
            metricGasoil.textContent = `${Number(stockData.gasoil_stock).toLocaleString('es-AR')} L`;
        }
        if (metricSemSoja && stockData.semillas_soja !== undefined) {
            metricSemSoja.textContent = `${stockData.semillas_soja} bolsas`;
        }
        if (metricMap && stockData.map_tn !== undefined) {
            metricMap.textContent = `${stockData.map_tn} tn`;
        }
        if (metricGlifo && stockData.glifosato_lts !== undefined) {
            metricGlifo.textContent = `${stockData.glifosato_lts} L`;
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

    const appendBotMessage = (text, toolCalls = []) => {
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
                        <span>Consultando planillas de stock y registros agronómicos...</span>
                    </div>
                `;
            }
            if (hasWrite) {
                toolHtml += `
                    <div class="tool-header-row" style="margin-top: 4px;">
                        <span class="tool-icon">💾</span>
                        <span>Actualizando inventarios y bitácora de lote en tiempo real...</span>
                    </div>
                `;
            }
            toolHtml += `</div>`;
        }

        const formattedText = formatMarkdownLike(text);

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
                </div>
            </div>
        `;
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
                    <span>Procesando labores y ejecutando cálculos matemáticos con Claude...</span>
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

    // Chat submit
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
                appendBotMessage(data.data.response, data.data.tool_calls);
                updateLiveMetrics(data.data.stock_data);
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

    // WhatsApp Simulation Handler
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
                appendBotMessage(data.data.response, data.data.tool_calls);
                updateLiveMetrics(data.data.stock_data);
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

    // Quick chips
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
                                <p>Historial reiniciado. ¿Qué dato de stock o labor deseas consultar?</p>
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
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/`(.*?)`/g, '<code>$1</code>');
        const lines = html.split('\n');
        let formatted = '';
        lines.forEach(line => {
            if (line.trim().startsWith('- ')) {
                formatted += `<p style="margin-left: 14px;">• ${line.trim().substring(2)}</p>`;
            } else if (line.trim().startsWith('#')) {
                const headerText = line.replace(/^#+\s*/, '');
                formatted += `<h4 style="margin: 8px 0 4px; color: #a7f3d0;">${headerText}</h4>`;
            } else if (line.trim()) {
                formatted += `<p>${line}</p>`;
            }
        });
        return formatted;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
