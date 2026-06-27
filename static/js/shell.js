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
        const startUrl = body.dataset.startUrl;
        const pollUrl = body.dataset.pollUrl;
        const inputUrl = body.dataset.inputUrl;
        const resizeUrl = body.dataset.resizeUrl;
        const stopUrl = body.dataset.stopUrl;
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

        let offset = 0;
        let polling = false;
        let pollTimer = null;
        let connected = false;

        function setStatus(text, cls) {
            statusEl.textContent = text;
            statusEl.className = 'terminal-status' + (cls ? ' ' + cls : '');
        }

        function base64ToBytes(b64) {
            const binary = atob(b64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }
            return bytes;
        }

        async function sendResize() {
            if (!connected) return;
            try {
                await fetch(resizeUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ rows: term.rows, cols: term.cols }),
                });
            } catch {
                // ignore resize errors
            }
        }

        async function sendInput(data) {
            if (!connected) return;
            try {
                await fetch(inputUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ data: data, encoding: 'text' }),
                });
            } catch {
                setStatus('Ошибка отправки', 'disconnected');
            }
        }

        async function poll() {
            if (!polling) return;

            try {
                const resp = await fetch(pollUrl + '?offset=' + offset);
                if (resp.status === 401) {
                    setStatus('Не авторизован', 'disconnected');
                    stopPolling();
                    return;
                }

                const data = await resp.json();
                if (data.output) {
                    term.write(base64ToBytes(data.output));
                }
                offset = data.offset;

                if (!data.alive && connected) {
                    setStatus('Shell завершён', 'disconnected');
                    connected = false;
                }
            } catch {
                setStatus('Ошибка опроса', 'disconnected');
            }

            pollTimer = setTimeout(poll, 200);
        }

        function startPolling() {
            polling = true;
            poll();
        }

        function stopPolling() {
            polling = false;
            if (pollTimer) {
                clearTimeout(pollTimer);
                pollTimer = null;
            }
        }

        async function connect() {
            setStatus('Подключение...', '');
            try {
                const resp = await fetch(startUrl, { method: 'POST' });
                if (!resp.ok) {
                    setStatus('Ошибка запуска shell', 'disconnected');
                    return;
                }

                connected = true;
                offset = 0;
                setStatus('Подключено', 'connected');
                fitAddon.fit();
                await sendResize();
                term.focus();
                startPolling();
            } catch {
                setStatus('Ошибка соединения', 'disconnected');
            }
        }

        term.onData((data) => {
            sendInput(data);
        });

        window.addEventListener('resize', () => {
            fitAddon.fit();
            sendResize();
        });

        if (lockBtn) {
            lockBtn.addEventListener('click', async () => {
                stopPolling();
                connected = false;
                await fetch(stopUrl, { method: 'POST' });
                await fetch(lockUrl, { method: 'POST' });
                window.location.reload();
            });
        }

        window.addEventListener('beforeunload', () => {
            stopPolling();
            navigator.sendBeacon(stopUrl, '');
        });

        connect();
    }
})();
