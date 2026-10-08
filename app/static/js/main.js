document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const btnSend = document.getElementById('btn-send');
    const messagesList = document.getElementById('messages-list');
    const btnClearChat = document.getElementById('btn-clear-chat');
    const quickChips = document.querySelectorAll('.chip-btn');
    
    // Modal elements
    const inspectorModal = document.getElementById('inspector-modal');
    const btnOpenInspector = document.getElementById('btn-open-inspector');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalFileTabs = document.getElementById('modal-file-tabs');
    const modalFileContent = document.getElementById('modal-file-content');
    const btnRefreshInspector = document.getElementById('btn-refresh-inspector');
    const storageFileRows = document.querySelectorAll('.storage-file-row');

    let currentInspectedFile = 'INDEX.md';

    // Auto-scroll chat to bottom
    const scrollToBottom = () => {
        messagesList.scrollTop = messagesList.scrollHeight;
    };

    // Auto-resize textarea
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
    });

    // Enter to submit (Shift+Enter for newline)
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Render User Message
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

    // Render Bot Message with Tool Calling Transparency
    const appendBotMessage = (text, toolCalls = [], isDemo = false) => {
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const card = document.createElement('div');
        card.className = 'message-card bot-card';

        // Construir badges de Tool Calling si Claude invocó herramientas
        let toolHtml = '';
        if (toolCalls && toolCalls.length > 0) {
            toolHtml = `<div class="tool-call-banner">`;
            toolCalls.forEach(tc => {
                const icon = tc.tool === 'write_storage_file' ? '💾' : tc.tool === 'read_storage_file' ? '🔍' : '📂';
                const fileTarget = tc.args?.filename ? `<code>${tc.args.filename}</code>` : '';
                toolHtml += `
                    <div class="tool-header-row">
                        <span class="tool-icon">${icon}</span>
                        <span>Tool Call: <strong>${tc.tool}</strong> ${fileTarget}</span>
                    </div>
                    <div class="tool-detail-row">
                        <span>➔ ${escapeHtml(tc.preview || 'Completado')}</span>
                    </div>
                `;
            });
            toolHtml += `</div>`;
        }

        // Formatear texto simple con párrafos y viñetas
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

    // Render Loading indicator
    const showLoading = () => {
        const loadingCard = document.createElement('div');
        loadingCard.id = 'chat-loading-card';
        loadingCard.className = 'message-card bot-card';
        loadingCard.innerHTML = `
            <div class="avatar bot-avatar">🌾</div>
            <div class="message-body">
                <div class="loading-indicator">
                    <span class="spinner-dot">⚙️</span>
                    <span>IA Desk Agro está consultando archivos y procesando con Claude...</span>
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

    // Handle form submit
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
                appendBotMessage(data.data.response, data.data.tool_calls, data.data.is_demo);
            } else {
                appendBotMessage('⚠️ Error: ' + (data.message || 'No se pudo procesar la consulta'));
            }
        } catch (err) {
            removeLoading();
            appendBotMessage('⚠️ Error de conexión con el servidor local Django.');
            console.error(err);
        } finally {
            btnSend.disabled = false;
        }
    });

    // Quick chips click
    quickChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.dataset.query;
            if (query) {
                userInput.value = query;
                chatForm.dispatchEvent(new Event('submit'));
            }
        });
    });

    // Clear history
    btnClearChat.addEventListener('click', async () => {
        if (!confirm('¿Deseas reiniciar la memoria de conversación y el archivo CHAT_HISTORY.json?')) return;
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
                                <p>Historial y ventana deslizante reiniciados. ¿Qué dato de las operaciones deseas consultar?</p>
                            </div>
                        </div>
                    </div>
                `;
            }
        } catch (e) {
            alert('Error al reiniciar historial.');
        }
    });

    // Storage Inspector Modal Logic
    const availableFiles = ['INDEX.md', 'MEMORY.md', 'CHAT_HISTORY.json'];

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
        document.getElementById('modal-file-title').textContent = `Inspeccionando files_storage/${filename}`;
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

    // Utility: Format simple markdown
    function formatMarkdownLike(str) {
        if (!str) return '';
        let html = escapeHtml(str);

        // Bold
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Inline code
        html = html.replace(/`(.*?)`/g, '<code>$1</code>');
        // Split by lines
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
