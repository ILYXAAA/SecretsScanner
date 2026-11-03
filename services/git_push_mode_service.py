"""Способ доставки файлов в репозиторий: direct (прямой push) или pr (Pull Request).

Хранится в таблице settings (ключ git_push_mode) и переключается в админке.
Пока в админке ничего не выбрано, используется GIT_PUSH_MODE из .env (по умолчанию direct).
"""
import logging
from datetime import datetime

from config import GIT_PUSH_MODE
from models import Settings
from services.database import SessionLocal

git_push_mode_logger = logging.getLogger("git_push_mode")

GIT_PUSH_MODE_KEY = "git_push_mode"
GIT_PUSH_MODES = ("direct", "pr")


def _default_mode() -> str:
    return GIT_PUSH_MODE if GIT_PUSH_MODE in GIT_PUSH_MODES else "direct"


def get_git_push_mode_info() -> dict:
    db = SessionLocal()
    try:
        setting = db.query(Settings).filter(Settings.key == GIT_PUSH_MODE_KEY).first()
        if setting and setting.value in GIT_PUSH_MODES:
            return {
                "mode": setting.value,
                "source": "admin",
                "updated_by": setting.updated_by,
                "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
            }
    except Exception as e:
        # Без доступа к БД не блокируем доставку — берём значение по умолчанию
        git_push_mode_logger.error("Failed to read git push mode, using default: %s", e)
    finally:
        db.close()
    return {"mode": _default_mode(), "source": "env", "updated_by": None, "updated_at": None}


def get_git_push_mode() -> str:
    return get_git_push_mode_info()["mode"]


def set_git_push_mode(mode: str, updated_by: str) -> None:
    if mode not in GIT_PUSH_MODES:
        raise ValueError(f"Unknown git push mode: {mode}")

    db = SessionLocal()
    try:
        setting = db.query(Settings).filter(Settings.key == GIT_PUSH_MODE_KEY).first()
        if setting:
            setting.value = mode
            setting.updated_by = updated_by
            setting.updated_at = datetime.now()
        else:
            db.add(Settings(key=GIT_PUSH_MODE_KEY, value=mode, updated_by=updated_by, updated_at=datetime.now()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
