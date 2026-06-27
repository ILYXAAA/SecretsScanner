(function () {
    const body = document.body;
    const authenticated = body.dataset.authenticated === 'true';

    if (!authenticated) {
        initAuthForm();
        return;
    }

    initTerminal();

    function initAuthForm() {
        const form = document.getElementById('unlockForm');
        const passwordInput = document.getElementById('passwordInput');
        const unlockBtn = document.getElementById('unlockBtn');
        const authError = document.getElementById('authError');
        const unlockUrl = body.dataset.unlockUrl;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            authError.hidden = true;
            unlockBtn.disabled = true;
            unlockBtn.textContent = 'Подключение...';

            try {
                const resp = await fetch(unlockUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: passwordInput.value }),
                });

                if (resp.ok) {
                    window.location.reload();
                } else {
                    const data = await resp.json();
                    authError.textContent = data.error || 'Неверный пароль';
                    authError.hidden = false;
                    passwordInput.value = '';
                    passwordInput.focus();
                }
            } catch {
                authError.textContent = 'Ошибка соединения';
                authError.hidden = false;
            } finally {
                unlockBtn.disabled = false;
                unlockBtn.textContent = 'Подключиться';
            }
        });

        passwordInput.focus();
    }

    function initTerminal() {
        const wsUrl = body.dataset.wsUrl;
        const lockUrl = body.dataset.lockUrl;
        const statusEl = document.getElementById('terminalStatus');
        const lockBtn = document.getElementById('lockBtn');

        const term = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: 'Consolas, "Courier New", monospace',
            theme: {
                background: '#0d1117',
                foreground: '#c9d1d9',
                cursor: '#58a6ff',
                selectionBackground: '#264f78',
            },
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));
        fitAddon.fit();

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsFullUrl = protocol + '//' + window.location.host + wsUrl;

        let ws = null;
        let reconnectTimer = null;

        function setStatus(text, cls) {
            statusEl.textContent = text;
            statusEl.className = 'terminal-status' + (cls ? ' ' + cls : '');
        }

        function sendResize() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'resize',
                    rows: term.rows,
                    cols: term.cols,
                }));
            }
        }

        function connect() {
            setStatus('Подключение...', '');
            ws = new WebSocket(wsFullUrl);
            ws.binaryType = 'arraybuffer';

            ws.onopen = () => {
                setStatus('Подключено', 'connected');
                fitAddon.fit();
                sendResize();
                term.focus();
            };

            ws.onmessage = (event) => {
                if (event.data instanceof ArrayBuffer) {
                    term.write(new Uint8Array(event.data));
                } else {
                    term.write(event.data);
                }
            };

            ws.onclose = (event) => {
                setStatus('Отключено' + (event.code === 4401 ? ' (не авторизован)' : ''), 'disconnected');
                if (event.code !== 4401) {
                    reconnectTimer = setTimeout(connect, 3000);
                }
            };

            ws.onerror = () => {
                setStatus('Ошибка соединения', 'disconnected');
            };
        }

        term.onData((data) => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(data);
            }
        });

        window.addEventListener('resize', () => {
            fitAddon.fit();
            sendResize();
        });

        if (lockBtn) {
            lockBtn.addEventListener('click', async () => {
                if (ws) {
                    ws.close();
                }
                await fetch(lockUrl, { method: 'POST' });
                window.location.reload();
            });
        }

        connect();

        window.addEventListener('beforeunload', () => {
            if (reconnectTimer) clearTimeout(reconnectTimer);
            if (ws) ws.close();
        });
    }
})();
