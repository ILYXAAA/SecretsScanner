SHELL = True

SHELL_PASSWORD_HASH = "$2b$12$lE1QFZo.me6JCmZQxCB0e.Jq/tdDj5y7DZpMpJRxMo2UdXAkOXLIK"

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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
_shell_jobs: Dict[str, Tuple[str, asyncio.subprocess.Process]] = {}

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


def _ndjson_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


async def _kill_shell_job(job_id: str) -> None:
    entry = _shell_jobs.pop(job_id, None)
    if not entry:
        return
    _, process = entry
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except Exception:
            logger.exception("Failed to kill shell job %s", job_id)


async def _stream_shell_command(
    request: Request,
    token: str,
    command: str,
    cwd: str,
):
    job_id = str(uuid.uuid4())
    process = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=_shell_env(),
    )
    _shell_jobs[job_id] = (token, process)

    async def event_generator():
        cancelled = False
        try:
            yield _ndjson_line({"type": "start", "job_id": job_id, "cwd": cwd})
            deadline = time.monotonic() + SHELL_EXEC_TIMEOUT

            while True:
                if await request.is_disconnected():
                    cancelled = True
                    await _kill_shell_job(job_id)
                    break

                if job_id not in _shell_jobs:
                    cancelled = True
                    break

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await _kill_shell_job(job_id)
                    yield _ndjson_line({
                        "type": "output",
                        "text": f"\nCommand timed out after {SHELL_EXEC_TIMEOUT}s\n",
                    })
                    yield _ndjson_line({
                        "type": "done",
                        "exit_code": 124,
                        "cwd": cwd,
                        "timed_out": True,
                    })
                    cancelled = False
                    return

                try:
                    chunk = await asyncio.wait_for(
                        process.stdout.read(4096),
                        timeout=min(1.0, remaining),
                    )
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

                if not chunk:
                    break

                text = chunk.decode("utf-8", errors="replace")
                if text:
                    yield _ndjson_line({"type": "output", "text": text})

            if process.returncode is None:
                await process.wait()
            exit_code = process.returncode if process.returncode is not None else 1
            if cancelled or job_id not in _shell_jobs:
                yield _ndjson_line({
                    "type": "done",
                    "exit_code": 130,
                    "cwd": cwd,
                    "cancelled": True,
                })
            else:
                yield _ndjson_line({
                    "type": "done",
                    "exit_code": exit_code,
                    "cwd": cwd,
                })
        except Exception as e:
            logger.error("Shell stream error: %s", e)
            yield _ndjson_line({"type": "error", "message": str(e)})
        finally:
            _shell_jobs.pop(job_id, None)
            if process.returncode is None:
                try:
                    process.kill()
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
    )


if SHELL:

    @router.get("/shrek", response_class=HTMLResponse)
    async def shell_page(request: Request):
        authenticated = _get_shell_session(request)
        return templates.TemplateResponse(
            "shell.html",
            {
                "request": request,
                "authenticated": authenticated,
                "exec_url": get_full_url("shrek/exec"),
                "cancel_url": get_full_url("shrek/cancel"),
            },
        )

    @router.post("/shrek/unlock")
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

    @router.post("/shrek/lock")
    async def shell_lock(request: Request):
        token = request.cookies.get(SHELL_SESSION_COOKIE)
        if token:
            _shell_cwd.pop(token, None)
        response = JSONResponse({"success": True})
        response.delete_cookie(SHELL_SESSION_COOKIE)
        return response

    @router.post("/shrek/cancel")
    async def shell_cancel(request: Request):
        token = _require_shell_session(request)
        if not token:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        body = await request.json()
        job_id = body.get("job_id", "").strip()
        if not job_id:
            return JSONResponse({"error": "job_id required"}, status_code=400)

        entry = _shell_jobs.get(job_id)
        if not entry:
            return JSONResponse({"success": False, "error": "Команда не найдена или уже завершена"}, status_code=404)

        job_token, _process = entry
        if job_token != token:
            return JSONResponse({"error": "Forbidden"}, status_code=403)

        await _kill_shell_job(job_id)
        user_logger.info("Shell command cancelled: job_id=%s", job_id)
        return JSONResponse({"success": True})

    @router.post("/shrek/exec")
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
                output = f"cd: {label}: No such file or directory\n"

                async def cd_error_stream():
                    yield _ndjson_line({"type": "start", "job_id": None, "cwd": cwd})
                    yield _ndjson_line({"type": "output", "text": output})
                    yield _ndjson_line({"type": "done", "exit_code": 1, "cwd": cwd})

                return StreamingResponse(cd_error_stream(), media_type="application/x-ndjson")

            _shell_cwd[token] = new_cwd
            user_logger.info(f"Shell cd: {new_cwd}")

            async def cd_ok_stream():
                yield _ndjson_line({"type": "start", "job_id": None, "cwd": new_cwd})
                yield _ndjson_line({"type": "done", "exit_code": 0, "cwd": new_cwd})

            return StreamingResponse(cd_ok_stream(), media_type="application/x-ndjson")

        user_logger.info(f"Shell exec: {command!r} (cwd={cwd})")

        try:
            return await _stream_shell_command(request, token, command, cwd)
        except Exception as e:
            logger.error(f"Shell exec error: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)
