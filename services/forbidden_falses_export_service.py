import asyncio
import logging
from pathlib import Path

from sqlalchemy import distinct

from config import FALSES_REFRESH_INTERVAL_HOURS
from models import ForbiddenViolation, Scan
from services.database import SessionLocal
from services.falses_export_service import (
    build_falses_export_version,
    build_falses_txt_content,
    compute_payload_sha256,
    extract_falses_payload,
    falses_payload_from_hashes,
)

forbidden_falses_logger = logging.getLogger("forbidden_falses_export")

FORBIDDEN_FALSES_FILE_PATH = Path("./generated/language_search_falses.txt")


def fetch_refuted_forbidden_hashes(db):
    rows = db.query(distinct(ForbiddenViolation.hash_from_ci)).join(
        Scan, ForbiddenViolation.scan_id == Scan.id
    ).filter(
        Scan.status == "completed",
        Scan.scan_type == "forbidden",
        ForbiddenViolation.status == "Refuted",
        ForbiddenViolation.hash_from_ci.isnot(None),
        ForbiddenViolation.hash_from_ci != "",
    ).all()

    return sorted({row[0] for row in rows if row and row[0]})


def _push_forbidden_falses_if_configured(refresh_result: dict) -> None:
    if not refresh_result.get("written"):
        return

    try:
        from services.language_search_git_push_service import (
            is_language_search_git_push_configured,
            push_forbidden_falses_to_git,
        )

        if not is_language_search_git_push_configured():
            forbidden_falses_logger.info(
                "language_search falses.txt git push skipped: repo URL or PAT not set"
            )
            return

        content = FORBIDDEN_FALSES_FILE_PATH.read_text(encoding="utf-8")
        push_result = push_forbidden_falses_to_git(
            content,
            refresh_result["hash"],
            refresh_result.get("hash_count", 0),
        )
        refresh_result["git_push"] = push_result
    except Exception as e:
        forbidden_falses_logger.error("Failed to push forbidden falses.txt: %s", e, exc_info=True)
        refresh_result["git_push"] = {"pushed": False, "error": str(e)}


def refresh_forbidden_falses_file(version=None):
    try:
        return _refresh_forbidden_falses_file_impl(version)
    except Exception as e:
        forbidden_falses_logger.error("forbidden falses.txt refresh failed: %s", e, exc_info=True)
        return {"written": False, "error": str(e)}


def _refresh_forbidden_falses_file_impl(version=None):
    db = SessionLocal()
    try:
        hashes = fetch_refuted_forbidden_hashes(db)
        payload = falses_payload_from_hashes(hashes)
        payload_hash = compute_payload_sha256(payload)

        FORBIDDEN_FALSES_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        if FORBIDDEN_FALSES_FILE_PATH.exists():
            existing_content = FORBIDDEN_FALSES_FILE_PATH.read_text(encoding="utf-8")
            existing_payload = extract_falses_payload(existing_content)
            if compute_payload_sha256(existing_payload) == payload_hash:
                return {
                    "written": False,
                    "hash": payload_hash,
                    "path": str(FORBIDDEN_FALSES_FILE_PATH),
                    "hash_count": len(hashes),
                }

        export_version = version or build_falses_export_version()
        content = build_falses_txt_content(hashes, export_version)
        FORBIDDEN_FALSES_FILE_PATH.write_text(content, encoding="utf-8")
        forbidden_falses_logger.info(
            "language_search falses.txt updated (%s hashes)", len(hashes)
        )
        result = {
            "written": True,
            "hash": payload_hash,
            "path": str(FORBIDDEN_FALSES_FILE_PATH),
            "hash_count": len(hashes),
        }
    finally:
        db.close()

    _push_forbidden_falses_if_configured(result)
    return result


async def forbidden_falses_refresh_scheduler():
    forbidden_falses_logger.info("forbidden falses.txt background scheduler started")
    loop = asyncio.get_event_loop()
    await asyncio.sleep(15)

    try:
        await loop.run_in_executor(None, refresh_forbidden_falses_file)
    except Exception as e:
        forbidden_falses_logger.error("Initial forbidden falses refresh failed: %s", e, exc_info=True)

    while True:
        try:
            await asyncio.sleep(FALSES_REFRESH_INTERVAL_HOURS * 3600)
            await loop.run_in_executor(None, refresh_forbidden_falses_file)
        except Exception as e:
            forbidden_falses_logger.error("forbidden falses scheduler error: %s", e, exc_info=True)
            await asyncio.sleep(3600)
