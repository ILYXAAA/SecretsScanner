SHELL = True

SHELL_PASSWORD_HASH = "$2b$12$lE1QFZo.me6JCmZQxCB0e.Jq/tdDj5y7DZpMpJRxMo2UdXAkOXLIK"

import asyncio
import hashlib
import hmac
import logging
import os
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
SHELL_EXEC_TIMEOUT = 120

router = APIRouter()
_shell_cwd: Dict[str, str] = {}

DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _shell_env() -> dict:
    env = os.environ.copy()
    env["PATH"] = DEFAULT_PATH + ":" + env.get("PATH", "")
    env.setdefault("HOME", "/root")
    env["TERM"] = "dumb"
    env["LANG"] = "C.UTF-8"
    return env


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


def _get_cwd(token: str) -> str:
    return _shell_cwd.get(token, os.getcwd())


def _resolve_cd(cwd: str, target: str) -> Optional[str]:
    target = target.strip() or os.path.expanduser("~")
    if target == "-":
        return None
    if target.startswith("/"):
        new_cwd = os.path.normpath(target)
    elif target == "~":
        new_cwd = os.path.expanduser("~")
    else:
        new_cwd = os.path.normpath(os.path.join(cwd, target))
    return new_cwd if os.path.isdir(new_cwd) else None


if SHELL:

    @router.get("/shell", response_class=HTMLResponse)
    async def shell_page(request: Request):
        authenticated = _get_shell_session(request)
        return templates.TemplateResponse(
            "shell.html",
            {
                "request": request,
                "authenticated": authenticated,
                "exec_url": get_full_url("shell/exec"),
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
        if token:
            _shell_cwd.pop(token, None)
        response = JSONResponse({"success": True})
        response.delete_cookie(SHELL_SESSION_COOKIE)
        return response

    @router.post("/shell/exec")
    async def shell_exec(request: Request):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        body = await request.json()
        command = body.get("command", "").strip()
        if not command:
            return JSONResponse({"error": "Пустая команда"}, status_code=400)

        cwd = _get_cwd(token)

        if command == "cd" or command.startswith("cd "):
            target = command[2:].strip() if command.startswith("cd ") else ""
            new_cwd = _resolve_cd(cwd, target)
            if new_cwd is None:
                label = target or "~"
                return JSONResponse({
                    "output": f"cd: {label}: No such file or directory\n",
                    "exit_code": 1,
                    "cwd": cwd,
                })
            _shell_cwd[token] = new_cwd
            user_logger.info(f"Shell cd: {new_cwd}")
            return JSONResponse({"output": "", "exit_code": 0, "cwd": new_cwd})

        user_logger.info(f"Shell exec: {command!r} (cwd={cwd})")

        try:
            process = await asyncio.create_subprocess_exec(
                "/bin/bash",
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
                env=_shell_env(),
            )
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=SHELL_EXEC_TIMEOUT
            )
            output = stdout.decode("utf-8", errors="replace")
            if output and not output.endswith("\n"):
                output += "\n"

            return JSONResponse({
                "output": output,
                "exit_code": process.returncode,
                "cwd": cwd,
            })
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            return JSONResponse({
                "output": f"Command timed out after {SHELL_EXEC_TIMEOUT}s\n",
                "exit_code": 124,
                "cwd": cwd,
            }, status_code=408)
        except Exception as e:
            logger.error(f"Shell exec error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
