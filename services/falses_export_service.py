import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import distinct

from config import FALSES_REFRESH_INTERVAL_HOURS
from models import Scan, Secret
from services.database import SessionLocal

falses_logger = logging.getLogger("falses_export")

FALSES_EXPORT_DIR = "./generated"
FALSES_FILE_NAME = "falses.txt"
FALSES_AUTO_VERSION = "auto"
FALSES_FILE_PATH = Path(FALSES_EXPORT_DIR) / FALSES_FILE_NAME


def _push_falses_if_configured(refresh_result: dict) -> None:
    if not refresh_result.get("written"):
        return

    try:
        from services.falses_git_push_service import is_falses_git_push_configured, push_falses_file_to_git

        if not is_falses_git_push_configured():
            falses_logger.info(
                "falses.txt git push skipped: FALSES_GIT_REPO_URL or FALSES_GIT_PAT is not set"
            )
            return

        falses_logger.info("falses.txt git push starting...")
        push_result = push_falses_file_to_git(
            FALSES_FILE_PATH,
            refresh_result["hash"],
            refresh_result.get("hash_count", 0),
            force_push=refresh_result.get("on_startup", False),
        )
        refresh_result["git_push"] = push_result
        if push_result.get("pushed"):
            falses_logger.info(
                "falses.txt git push done (method=%s, branch=%s)",
                push_result.get("method", "?"),
                push_result.get("branch", "?"),
            )
        elif push_result.get("skipped"):
            falses_logger.info(
                "falses.txt git push skipped: %s",
                push_result.get("reason", "unknown"),
            )
        else:
            falses_logger.warning("falses.txt git push finished without success: %s", push_result)
    except Exception as e:
        falses_logger.error("Failed to push falses.txt to Azure DevOps: %s", e, exc_info=True)
        refresh_result["git_push"] = {"pushed": False, "error": str(e)}


def sanitize_falses_version(version: str) -> str:
    version = (version or "").strip()
    version = version.replace("\r", " ").replace("\n", " ")
    version = version.replace("[", "").replace("]", "")
    if len(version) > 80:
        version = version[:80]
    return version or "unknown"


def fetch_refuted_hashes(db):
    rows = db.query(distinct(Secret.hash_from_ci)).join(
        Scan, Secret.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Secret.status == "Refuted",
        Secret.hash_from_ci.isnot(None),
        Secret.hash_from_ci != "",
    ).all()

    return sorted({row[0] for row in rows if row and row[0]})


def build_falses_txt_content(hashes, version):
    safe_version = sanitize_falses_version(version)
    return f"[{safe_version}]\n" + ";".join(hashes)


def compute_content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def refresh_falses_file(version=None, on_startup=False):
    """Rebuild falses.txt and overwrite only when file content hash changes.

    On service startup (on_startup=True) the existing file is removed first so
    content is always regenerated and pushed.
    """
    export_version = version or FALSES_AUTO_VERSION
    db = SessionLocal()
    try:
        hashes = fetch_refuted_hashes(db)
        content = build_falses_txt_content(hashes, export_version)
        content_hash = compute_content_sha256(content)

        FALSES_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        if on_startup and FALSES_FILE_PATH.exists():
            FALSES_FILE_PATH.unlink()
            falses_logger.info("falses.txt removed for startup refresh at %s", FALSES_FILE_PATH)

        if not on_startup and FALSES_FILE_PATH.exists():
            existing_content = FALSES_FILE_PATH.read_text(encoding="utf-8")
            if compute_content_sha256(existing_content) == content_hash:
                falses_logger.info(
                    "falses.txt unchanged (sha256=%s), skipping write (%s hashes)",
                    content_hash[:16],
                    len(hashes),
                )
                return {
                    "written": False,
                    "hash": content_hash,
                    "path": str(FALSES_FILE_PATH),
                    "hash_count": len(hashes),
                }

        FALSES_FILE_PATH.write_text(content, encoding="utf-8")
        falses_logger.info(
            "falses.txt updated at %s (%s hashes, sha256=%s)",
            FALSES_FILE_PATH,
            len(hashes),
            content_hash[:16],
        )
        result = {
            "written": True,
            "hash": content_hash,
            "path": str(FALSES_FILE_PATH),
            "hash_count": len(hashes),
            "on_startup": on_startup,
        }
        _push_falses_if_configured(result)
        return result
    finally:
        db.close()


async def falses_refresh_scheduler():
    """Background task: refresh falses.txt on a fixed interval."""
    try:
        refresh_falses_file(on_startup=True)
    except Exception as e:
        falses_logger.error("Initial falses.txt refresh failed: %s", e, exc_info=True)

    while True:
        try:
            await asyncio.sleep(FALSES_REFRESH_INTERVAL_HOURS * 3600)
            refresh_falses_file()
        except Exception as e:
            falses_logger.error("falses refresh scheduler error: %s", e, exc_info=True)
            await asyncio.sleep(3600)
