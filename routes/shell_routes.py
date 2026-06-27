SHELL = True

SHELL_PASSWORD_HASH = "$2b$12$lE1QFZo.me6JCmZQxCB0e.Jq/tdDj5y7DZpMpJRxMo2UdXAkOXLIK"

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import signal
import struct
import time
from typing import Dict, Optional

from fastapi import APIRouter, Request
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
_shell_instances: Dict[str, "ShellInstance"] = {}


class ShellInstance:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self.alive = False
        self._master_fd: Optional[int] = None
        self._pid: Optional[int] = None
        self._read_task: Optional[asyncio.Task] = None
        self._process: Optional[asyncio.subprocess.Process] = None

    def append_output(self, data: bytes) -> None:
        self._buffer.extend(data)

    def read_from(self, offset: int) -> tuple[bytes, int]:
        offset = max(0, offset)
        if offset >= len(self._buffer):
            return b"", len(self._buffer)
        return bytes(self._buffer[offset:]), len(self._buffer)

    async def write_input(self, data: bytes) -> None:
        if not self.alive:
            return
        if self._master_fd is not None:
            os.write(self._master_fd, data)
        elif self._process and self._process.stdin:
            self._process.stdin.write(data)
            await self._process.stdin.drain()

    async def resize(self, rows: int, cols: int) -> None:
        if self._master_fd is not None:
            _set_winsize(self._master_fd, rows, cols)

    async def stop(self) -> None:
        self.alive = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self._pid = None

        if self._process is not None:
            if self._process.stdin:
                self._process.stdin.close()
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
            await self._process.wait()
            self._process = None


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


def _require_shell_session(request: Request) -> Optional[str]:
    token = request.cookies.get(SHELL_SESSION_COOKIE)
    if not _verify_shell_session_token(token):
        return None
    return token


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    import fcntl
    import termios

    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


async def _start_pty_shell(instance: ShellInstance) -> None:
    import fcntl
    import pty

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

        instance._master_fd = master_fd
        instance._pid = pid
        instance.alive = True

        loop = asyncio.get_running_loop()

        async def read_loop() -> None:
            while instance.alive:
                try:
                    data = await loop.run_in_executor(None, os.read, master_fd, 4096)
                    if not data:
                        break
                    instance.append_output(data)
                except OSError:
                    break
            instance.alive = False

        instance._read_task = asyncio.create_task(read_loop())


async def _start_subprocess_shell(instance: ShellInstance) -> None:
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

    instance._process = process
    instance.alive = True

    async def read_loop() -> None:
        assert process.stdout is not None
        while instance.alive:
            data = await process.stdout.read(4096)
            if not data:
                break
            instance.append_output(data)
        instance.alive = False

    instance._read_task = asyncio.create_task(read_loop())


async def _get_or_create_shell(token: str) -> ShellInstance:
    instance = _shell_instances.get(token)
    if instance and instance.alive:
        return instance

    if instance:
        await instance.stop()

    instance = ShellInstance()
    if hasattr(os, "fork"):
        await _start_pty_shell(instance)
    else:
        await _start_subprocess_shell(instance)

    _shell_instances[token] = instance
    user_logger.info("Shell HTTP session started")
    return instance


async def _stop_shell(token: Optional[str]) -> None:
    if not token:
        return
    instance = _shell_instances.pop(token, None)
    if instance:
        await instance.stop()
        user_logger.info("Shell HTTP session stopped")


if SHELL:

    @router.get("/shell", response_class=HTMLResponse)
    async def shell_page(request: Request):
        authenticated = _get_shell_session(request)
        return templates.TemplateResponse(
            "shell.html",
            {
                "request": request,
                "authenticated": authenticated,
                "start_url": get_full_url("shell/start"),
                "poll_url": get_full_url("shell/poll"),
                "input_url": get_full_url("shell/input"),
                "resize_url": get_full_url("shell/resize"),
                "stop_url": get_full_url("shell/stop"),
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
    async def shell_lock(request: Request):
        token = request.cookies.get(SHELL_SESSION_COOKIE)
        await _stop_shell(token)
        response = JSONResponse({"success": True})
        response.delete_cookie(SHELL_SESSION_COOKIE)
        return response

    @router.post("/shell/start")
    async def shell_start(request: Request):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            await _get_or_create_shell(token)
            return JSONResponse({"success": True})
        except Exception as e:
            logger.error(f"Shell start error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @router.get("/shell/poll")
    async def shell_poll(request: Request, offset: int = 0):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        instance = _shell_instances.get(token)
        if not instance:
            return JSONResponse({"output": "", "offset": 0, "alive": False})

        data, new_offset = instance.read_from(offset)
        return JSONResponse({
            "output": base64.b64encode(data).decode("ascii"),
            "offset": new_offset,
            "alive": instance.alive,
        })

    @router.post("/shell/input")
    async def shell_input(request: Request):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        instance = _shell_instances.get(token)
        if not instance or not instance.alive:
            return JSONResponse({"error": "Shell not running"}, status_code=400)

        body = await request.json()
        raw = body.get("data", "")
        data = base64.b64decode(raw) if body.get("encoding") == "base64" else raw.encode()

        try:
            await instance.write_input(data)
            return JSONResponse({"success": True})
        except Exception as e:
            logger.error(f"Shell input error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @router.post("/shell/resize")
    async def shell_resize(request: Request):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        instance = _shell_instances.get(token)
        if not instance or not instance.alive:
            return JSONResponse({"success": False})

        body = await request.json()
        await instance.resize(body.get("rows", 24), body.get("cols", 80))
        return JSONResponse({"success": True})

    @router.post("/shell/stop")
    async def shell_stop(request: Request):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        await _stop_shell(token)
        return JSONResponse({"success": True})
