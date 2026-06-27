/* shell.js v4 — command execution via HTTP */
(function () {
    const body = document.body;
    const authenticated = body.dataset.authenticated === 'true';

    if (!authenticated) {
        initAuthForm();
        return;
    }

    initShell();

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
            unlockBtn.textContent = 'Вход...';

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
                unlockBtn.textContent = 'Войти';
            }
        });

        passwordInput.focus();
    }

    function initShell() {
        const execUrl = body.dataset.execUrl;
        const lockUrl = body.dataset.lockUrl;
        const outputEl = document.getElementById('shellOutput');
        const form = document.getElementById('commandForm');
        const input = document.getElementById('commandInput');
        const runBtn = document.getElementById('runBtn');
        const statusEl = document.getElementById('shellStatus');
        const lockBtn = document.getElementById('lockBtn');

        let cwd = '~';
        let running = false;
        const history = [];
        let historyIndex = -1;

        function setStatus(text, cls) {
            statusEl.textContent = text;
            statusEl.className = 'shell-status' + (cls ? ' ' + cls : '');
        }

        function appendBlock(command, output, exitCode) {
            const block = document.createElement('div');
            block.className = 'shell-block';

            const cmdLine = document.createElement('div');
            cmdLine.className = 'shell-cmd';
            cmdLine.textContent = '$ ' + command;
            block.appendChild(cmdLine);

            if (output) {
                const outLine = document.createElement('pre');
                outLine.className = 'shell-result' + (exitCode !== 0 ? ' error' : '');
                outLine.textContent = output;
                block.appendChild(outLine);
            }

            if (exitCode !== 0 && exitCode !== null) {
                const codeLine = document.createElement('div');
                codeLine.className = 'shell-exit-code';
                codeLine.textContent = '[exit ' + exitCode + ']';
                block.appendChild(codeLine);
            }

            outputEl.appendChild(block);
            outputEl.scrollTop = outputEl.scrollHeight;
        }

        async function runCommand(command) {
            if (!command || running) return;

            running = true;
            runBtn.disabled = true;
            setStatus('Выполняется...', 'running');

            if (history[history.length - 1] !== command) {
                history.push(command);
            }
            historyIndex = history.length;

            try {
                const resp = await fetch(execUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: command }),
                });

                const data = await resp.json();

                if (resp.status === 401) {
                    appendBlock(command, 'Сессия истекла. Обновите страницу.\n', 1);
                    setStatus('Не авторизован', 'error');
                    return;
                }

                if (!resp.ok) {
                    appendBlock(command, (data.error || 'Ошибка') + '\n', 1);
                    setStatus('Ошибка', 'error');
                    return;
                }

                if (data.cwd) {
                    cwd = data.cwd;
                    setStatus(cwd, '');
                }

                appendBlock(command, data.output || '', data.exit_code);
                if (data.cwd) {
                    setStatus(data.cwd, '');
                }
            } catch {
                appendBlock(command, 'Ошибка соединения\n', 1);
                setStatus('Ошибка соединения', 'error');
            } finally {
                running = false;
                runBtn.disabled = false;
                input.focus();
            }
        }

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const command = input.value.trim();
            if (!command) return;
            input.value = '';
            runCommand(command);
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (history.length === 0) return;
                if (historyIndex <= 0) {
                    historyIndex = 0;
                } else {
                    historyIndex -= 1;
                }
                input.value = history[historyIndex] || '';
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (history.length === 0) return;
                if (historyIndex >= history.length - 1) {
                    historyIndex = history.length;
                    input.value = '';
                } else {
                    historyIndex += 1;
                    input.value = history[historyIndex] || '';
                }
            }
        });

        if (lockBtn) {
            lockBtn.addEventListener('click', async () => {
                await fetch(lockUrl, { method: 'POST' });
                window.location.reload();
            });
        }

        appendBlock('', 'Введите команду и нажмите Enter. Поддерживается cd.\n', null);
        input.focus();
    }
})();
