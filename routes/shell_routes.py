SHELL = True

SHELL_PASSWORD_HASH = "$2b$12$lE1QFZo.me6JCmZQxCB0e.Jq/tdDj5y7DZpMpJRxMo2UdXAkOXLIK"

import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import struct
import time
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from passlib.context import CryptContext
from starlette.responses import Response

from config import SECRET_KEY, get_full_url
from services.templates import templates

logger = logging.getLogger("main")
user_logger = logging.getLogger("user_actions")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SHELL_SESSION_COOKIE = "shell_session"
SHELL_SESSION_MAX_AGE = 3600

router = APIRouter()


def _create_shell_session_token() -> str:
    ts = str(int(time.time()))
    sig = hmac.new(
        SECRET_KEY.encode(), f"shell:{ts}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{ts}.{sig}"


def _verify_shell_session_token(token: Optional[str]) -> bool:
    if not token:
        return False
    try:
        ts, sig = token.split(".", 1)
        expected = hmac.new(
            SECRET_KEY.encode(), f"shell:{ts}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        return int(time.time()) - int(ts) <= SHELL_SESSION_MAX_AGE
    except (ValueError, TypeError):
        return False


def _get_shell_session(request: Request) -> bool:
    return _verify_shell_session_token(request.cookies.get(SHELL_SESSION_COOKIE))


def _set_shell_session_cookie(response: Response) -> None:
    response.set_cookie(
        key=SHELL_SESSION_COOKIE,
        value=_create_shell_session_token(),
        httponly=True,
        max_age=SHELL_SESSION_MAX_AGE,
        samesite="lax",
    )


if SHELL:

    @router.get("/shell", response_class=HTMLResponse)
    async def shell_page(request: Request):
        authenticated = _get_shell_session(request)
        return templates.TemplateResponse(
            "shell.html",
            {
                "request": request,
                "authenticated": authenticated,
                "ws_url": get_full_url("shell/ws"),
            },
        )

    @router.post("/shell/unlock")
    async def shell_unlock(request: Request):
        body = await request.json()
        password = body.get("password", "")
        if not pwd_context.verify(password, SHELL_PASSWORD_HASH):
            user_logger.warning("Shell access denied: invalid password")
            return JSONResponse({"success": False, "error": "Неверный пароль"}, status_code=401)

        user_logger.info("Shell access granted")
        response = JSONResponse({"success": True})
        _set_shell_session_cookie(response)
        return response

    @router.post("/shell/lock")
    async def shell_lock():
        response = JSONResponse({"success": True})
        response.delete_cookie(SHELL_SESSION_COOKIE)
        return response

    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        import fcntl
        import termios

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    async def _run_pty_shell(websocket: WebSocket) -> None:
        import fcntl
        import pty
        import termios

        master_fd, slave_fd = pty.openpty()

        shell = os.environ.get("SHELL", "/bin/bash")
        pid = os.fork()
        if pid == 0:
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.chdir(os.getcwd())
            os.execvp(shell, [shell, "-i"])
        else:
            os.close(slave_fd)
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            loop = asyncio.get_running_loop()
            output_queue: asyncio.Queue[bytes] = asyncio.Queue()

            def on_pty_readable():
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        output_queue.put_nowait(data)
                    else:
                        loop.remove_reader(master_fd)
                        output_queue.put_nowait(None)
                except OSError:
                    loop.remove_reader(master_fd)
                    output_queue.put_nowait(None)

            loop.add_reader(master_fd, on_pty_readable)

            async def forward_pty_output():
                while True:
                    data = await output_queue.get()
                    if data is None:
                        break
                    await websocket.send_bytes(data)

            async def forward_ws_input():
                try:
                    while True:
                        msg = await websocket.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if msg.get("bytes"):
                            os.write(master_fd, msg["bytes"])
                        elif msg.get("text"):
                            try:
                                payload = json.loads(msg["text"])
                                if payload.get("type") == "resize":
                                    _set_winsize(
                                        master_fd,
                                        payload.get("rows", 24),
                                        payload.get("cols", 80),
                                    )
                                else:
                                    os.write(master_fd, msg["text"].encode())
                            except json.JSONDecodeError:
                                os.write(master_fd, msg["text"].encode())
                except WebSocketDisconnect:
                    pass

            try:
                await asyncio.gather(forward_pty_output(), forward_ws_input())
            finally:
                loop.remove_reader(master_fd)
                os.close(master_fd)
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass

    async def _run_subprocess_shell(websocket: WebSocket) -> None:
        if os.name == "nt":
            shell_cmd = "cmd.exe"
        else:
            shell_cmd = os.environ.get("SHELL", "/bin/bash")

        process = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.getcwd(),
        )

        async def forward_stdout():
            assert process.stdout is not None
            while True:
                data = await process.stdout.read(4096)
                if not data:
                    break
                await websocket.send_bytes(data)

        async def forward_stdin():
            try:
                while True:
                    msg = await websocket.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    if msg.get("bytes") and process.stdin:
                        process.stdin.write(msg["bytes"])
                        await process.stdin.drain()
                    elif msg.get("text") and process.stdin:
                        process.stdin.write(msg["text"].encode())
                        await process.stdin.drain()
            except WebSocketDisconnect:
                pass

        try:
            await asyncio.gather(forward_stdout(), forward_stdin())
        finally:
            if process.stdin:
                process.stdin.close()
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    @router.websocket("/shell/ws")
    async def shell_websocket(websocket: WebSocket):
        if not _verify_shell_session_token(websocket.cookies.get(SHELL_SESSION_COOKIE)):
            await websocket.close(code=4401, reason="Unauthorized")
            return

        await websocket.accept()
        user_logger.info("Shell WebSocket session started")

        try:
            if hasattr(os, "fork"):
                await _run_pty_shell(websocket)
            else:
                await _run_subprocess_shell(websocket)
        except Exception as e:
            logger.error(f"Shell session error: {e}")
            try:
                await websocket.send_text(f"\r\n[Session error: {e}]\r\n")
            except Exception:
                pass
        finally:
            user_logger.info("Shell WebSocket session ended")
