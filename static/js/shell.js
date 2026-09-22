/* shell.js v6 — streaming command execution via HTTP */
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
        const cancelUrl = body.dataset.cancelUrl;
        const lockUrl = body.dataset.lockUrl;
        const outputEl = document.getElementById('shellOutput');
        const form = document.getElementById('commandForm');
        const input = document.getElementById('commandInput');
        const runBtn = document.getElementById('runBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        const statusEl = document.getElementById('shellStatus');
        const lockBtn = document.getElementById('lockBtn');

        let cwd = '~';
        let running = false;
        let activeJobId = null;
        let activeAbortController = null;
        const history = [];
        let historyIndex = -1;

        function setStatus(text, cls) {
            statusEl.textContent = text;
            statusEl.className = 'shell-status' + (cls ? ' ' + cls : '');
        }

        function setRunningState(isRunning) {
            running = isRunning;
            runBtn.disabled = isRunning;
            input.disabled = isRunning;
            if (cancelBtn) {
                cancelBtn.hidden = !isRunning;
            }
        }

        function normalizeStreamText(text) {
            return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
        }

        function createStreamWriter(outContainer) {
            const state = { pending: '', partialEl: null };

            function append(text) {
                if (!text) {
                    return;
                }
                state.pending += normalizeStreamText(text);
                const parts = state.pending.split('\n');
                state.pending = parts.pop() ?? '';

                for (const part of parts) {
                    const lineEl = document.createElement('div');
                    lineEl.className = 'shell-result-line';
                    lineEl.textContent = part;
                    outContainer.appendChild(lineEl);
                }

                if (state.partialEl) {
                    state.partialEl.remove();
                    state.partialEl = null;
                }

                if (state.pending) {
                    state.partialEl = document.createElement('div');
                    state.partialEl.className = 'shell-result-line shell-result-partial';
                    state.partialEl.textContent = state.pending;
                    outContainer.appendChild(state.partialEl);
                }

                outputEl.scrollTop = outputEl.scrollHeight;
            }

            function flush() {
                if (!state.pending) {
                    if (state.partialEl) {
                        state.partialEl.classList.remove('shell-result-partial');
                        state.partialEl = null;
                    }
                    return;
                }

                if (state.partialEl) {
                    state.partialEl.classList.remove('shell-result-partial');
                    state.partialEl = null;
                } else {
                    const lineEl = document.createElement('div');
                    lineEl.className = 'shell-result-line';
                    lineEl.textContent = state.pending;
                    outContainer.appendChild(lineEl);
                }
                state.pending = '';
                outputEl.scrollTop = outputEl.scrollHeight;
            }

            return { append, flush };
        }

        function createCommandBlock(command) {
            const block = document.createElement('div');
            block.className = 'shell-block';

            const cmdLine = document.createElement('div');
            cmdLine.className = 'shell-cmd';
            cmdLine.textContent = '$ ' + command;
            block.appendChild(cmdLine);

            const outContainer = document.createElement('div');
            outContainer.className = 'shell-result shell-result-stream';
            block.appendChild(outContainer);

            outputEl.appendChild(block);
            outputEl.scrollTop = outputEl.scrollHeight;

            return { block, outContainer, writer: createStreamWriter(outContainer) };
        }

        function finalizeCommandBlock(block, outContainer, writer, exitCode, options = {}) {
            const { cancelled = false, timedOut = false } = options;

            writer.flush();

            if (exitCode !== 0 && exitCode !== null) {
                outContainer.classList.add('error');
            }

            if (cancelled) {
                const note = document.createElement('div');
                note.className = 'shell-exit-code';
                note.textContent = '[прервано пользователем]';
                block.appendChild(note);
            } else if (timedOut) {
                const note = document.createElement('div');
                note.className = 'shell-exit-code';
                note.textContent = '[превышено время ожидания]';
                block.appendChild(note);
            } else if (exitCode !== 0 && exitCode !== null) {
                const codeLine = document.createElement('div');
                codeLine.className = 'shell-exit-code';
                codeLine.textContent = '[exit ' + exitCode + ']';
                block.appendChild(codeLine);
            }

            outputEl.scrollTop = outputEl.scrollHeight;
        }

        function appendStaticBlock(command, output, exitCode) {
            const { block, outContainer, writer } = createCommandBlock(command);
            if (output) {
                writer.append(output);
            }
            finalizeCommandBlock(block, outContainer, writer, exitCode);
        }

        async function parseNdjsonStream(response, onEvent) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    break;
                }
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed) {
                        continue;
                    }
                    let event;
                    try {
                        event = JSON.parse(trimmed);
                    } catch {
                        continue;
                    }
                    await onEvent(event);
                }
            }

            const tail = buffer.trim();
            if (tail) {
                try {
                    await onEvent(JSON.parse(tail));
                } catch {
                    // ignore malformed tail
                }
            }
        }

        async function cancelActiveCommand() {
            if (!running) {
                return;
            }

            if (activeJobId && cancelUrl) {
                try {
                    await fetch(cancelUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ job_id: activeJobId }),
                    });
                } catch {
                    // stream will still close or show cancelled state
                }
            }

            if (activeAbortController) {
                activeAbortController.abort();
            }
        }

        async function runCommand(command) {
            if (!command || running) {
                return;
            }

            setRunningState(true);
            activeJobId = null;
            activeAbortController = new AbortController();
            setStatus('Выполняется...', 'running');

            if (history[history.length - 1] !== command) {
                history.push(command);
            }
            historyIndex = history.length;

            const { block, outContainer, writer } = createCommandBlock(command);
            let exitCode = null;
            let streamFinished = false;

            try {
                const resp = await fetch(execUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ command: command }),
                    signal: activeAbortController.signal,
                });

                if (resp.status === 401) {
                    writer.append('Сессия истекла. Обновите страницу.\n');
                    finalizeCommandBlock(block, outContainer, writer, 1);
                    setStatus('Не авторизован', 'error');
                    return;
                }

                const contentType = resp.headers.get('content-type') || '';
                if (!resp.ok && !contentType.includes('ndjson')) {
                    let message = 'Ошибка';
                    try {
                        const data = await resp.json();
                        message = data.error || message;
                    } catch {
                        // ignore
                    }
                    writer.append(message + '\n');
                    finalizeCommandBlock(block, outContainer, writer, 1);
                    setStatus('Ошибка', 'error');
                    return;
                }

                if (!contentType.includes('ndjson')) {
                    writer.append('Неверный формат ответа сервера\n');
                    finalizeCommandBlock(block, outContainer, writer, 1);
                    setStatus('Ошибка', 'error');
                    return;
                }

                await parseNdjsonStream(resp, async (event) => {
                    if (event.type === 'start') {
                        activeJobId = event.job_id || null;
                        if (event.cwd) {
                            cwd = event.cwd;
                            setStatus('Выполняется: ' + cwd, 'running');
                        }
                    } else if (event.type === 'output' && event.text) {
                        writer.append(event.text);
                        setStatus('Выполняется: ' + cwd, 'running');
                    } else if (event.type === 'done') {
                        streamFinished = true;
                        exitCode = event.exit_code;
                        if (event.cwd) {
                            cwd = event.cwd;
                        }
                        finalizeCommandBlock(block, outContainer, writer, exitCode, {
                            cancelled: Boolean(event.cancelled),
                            timedOut: Boolean(event.timed_out),
                        });
                        setStatus(cwd, event.cancelled ? 'error' : '');
                    } else if (event.type === 'error') {
                        streamFinished = true;
                        writer.append((event.message || 'Ошибка') + '\n');
                        finalizeCommandBlock(block, outContainer, writer, 1);
                        setStatus('Ошибка', 'error');
                    }
                });

                if (!streamFinished) {
                    finalizeCommandBlock(block, outContainer, writer, exitCode ?? 1, { cancelled: true });
                    setStatus(cwd, 'error');
                }
            } catch (error) {
                if (error.name === 'AbortError') {
                    if (!streamFinished) {
                        finalizeCommandBlock(block, outContainer, writer, 130, { cancelled: true });
                        setStatus(cwd, 'error');
                    }
                } else {
                    writer.append('Ошибка соединения\n');
                    finalizeCommandBlock(block, outContainer, writer, 1);
                    setStatus('Ошибка соединения', 'error');
                }
            } finally {
                activeJobId = null;
                activeAbortController = null;
                setRunningState(false);
                input.focus();
            }
        }

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            const command = input.value.trim();
            if (!command) {
                return;
            }
            input.value = '';
            runCommand(command);
        });

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                cancelActiveCommand();
            });
        }

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && running) {
                e.preventDefault();
                cancelActiveCommand();
                return;
            }

            if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (history.length === 0) {
                    return;
                }
                if (historyIndex <= 0) {
                    historyIndex = 0;
                } else {
                    historyIndex -= 1;
                }
                input.value = history[historyIndex] || '';
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (history.length === 0) {
                    return;
                }
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

        appendStaticBlock('', 'Введите команду и нажмите Enter. Поддерживается cd. Esc — прервать выполнение.\n', null);
        input.focus();
    }
})();
