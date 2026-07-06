import json
import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import ForbiddenViolation, Project, Scan
from services.database import sanitize_string
from utils.ci_hash import build_forbidden_hash_from_ci, normalize_path_for_ci_hash

logger = logging.getLogger("main")

_HASH_LOOKUP_CHUNK_SIZE = 500

FORBIDDEN_TASK_TYPES = frozenset({"forbidden_check", "local_forbidden_check"})


def normalize_scan_type(scan_type: str | None) -> str:
    value = (scan_type or "secrets").strip().lower()
    return "forbidden" if value == "forbidden" else "secrets"


def is_forbidden_callback(data: dict, scan: Scan | None = None) -> bool:
    task_type = (data.get("TaskType") or "").strip().lower()
    if task_type in FORBIDDEN_TASK_TYPES:
        return True
    if scan and normalize_scan_type(scan.scan_type) == "forbidden":
        return True
    return False


def load_latest_violation_decisions_by_hash(
    db_session: Session,
    project_name: str,
    exclude_scan_id: str,
    hash_values: set,
) -> dict:
    if not hash_values:
        return {}

    decisions = {}
    hash_list = list(hash_values)

    for i in range(0, len(hash_list), _HASH_LOOKUP_CHUNK_SIZE):
        chunk = hash_list[i:i + _HASH_LOOKUP_CHUNK_SIZE]
        rows = (
            db_session.query(ForbiddenViolation)
            .join(Scan, ForbiddenViolation.scan_id == Scan.id)
            .filter(
                Scan.project_name == project_name,
                Scan.id != exclude_scan_id,
                Scan.status == "completed",
                Scan.scan_type == "forbidden",
                Scan.completed_at.isnot(None),
                ForbiddenViolation.hash_from_ci.in_(chunk),
                ForbiddenViolation.status.in_(("Refuted", "Confirmed")),
            )
            .order_by(Scan.completed_at.desc())
            .all()
        )

        for violation in rows:
            if violation.hash_from_ci and violation.hash_from_ci not in decisions:
                decisions[violation.hash_from_ci] = violation

    return decisions


def resolve_forbidden_passed_from_violations(violations: list) -> bool:
    blocking = [
        item for item in violations
        if bool(item.get("is_blocking", True))
    ]
    return len(blocking) == 0


def resolve_forbidden_passed_from_callback(data: dict) -> bool | None:
    if "Passed" in data:
        return bool(data.get("Passed"))
    if "passed" in data:
        return bool(data.get("passed"))

    results = data.get("Results") or {}
    summary = results.get("summary") or {}
    if "passed" in summary:
        return bool(summary.get("passed"))
    if "Passed" in summary:
        return bool(summary.get("Passed"))

    violations = results.get("violations")
    if violations is not None:
        return resolve_forbidden_passed_from_violations(violations)
    return None


def refresh_forbidden_passed(db: Session, scan_id: str):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        return

    blocking_count = db.query(func.count(ForbiddenViolation.id)).filter(
        ForbiddenViolation.scan_id == scan_id,
        ForbiddenViolation.is_blocking == True,
        ForbiddenViolation.is_exception == False,
    ).scalar() or 0
    scan.forbidden_passed = blocking_count == 0


def update_forbidden_scan_counters(db: Session, scan_id: str):
    try:
        count = db.query(func.count(ForbiddenViolation.id)).filter(
            ForbiddenViolation.scan_id == scan_id,
            ForbiddenViolation.is_exception == False,
        ).scalar() or 0

        scan = db.query(Scan).filter(Scan.id == scan_id).first()
        if scan:
            scan.violations_count = count
            refresh_forbidden_passed(db, scan_id)
            db.commit()
    except Exception as error:
        logger.critical("Ошибка обновления счетчика violations: %s", error, exc_info=True)


def apply_violation_status(
    violation: ForbiddenViolation,
    status: str,
    comment: str,
    current_user: str,
    changed_at: datetime,
):
    violation.status = status
    if status == "Refuted":
        violation.is_exception = True
        violation.exception_comment = comment
        violation.refuted_at = changed_at
        violation.refuted_by = current_user
        violation.confirmed_by = None
    elif status == "Confirmed":
        violation.is_exception = False
        violation.exception_comment = None
        violation.refuted_at = None
        violation.confirmed_by = current_user
        violation.refuted_by = None
    else:
        violation.is_exception = False
        violation.exception_comment = None
        violation.refuted_at = None
        violation.confirmed_by = None
        violation.refuted_by = None


def propagate_violation_status_to_newer_scans(
    db: Session,
    source_violation: ForbiddenViolation,
    status: str,
    comment: str,
    current_user: str,
    changed_at: datetime,
) -> set:
    source_scan = db.query(Scan).filter(Scan.id == source_violation.scan_id).first()
    if not source_scan:
        return set()

    source_scan_date = source_scan.completed_at or source_scan.started_at
    if not source_scan_date:
        return set()

    matching_query = db.query(ForbiddenViolation).join(
        Scan, ForbiddenViolation.scan_id == Scan.id
    ).filter(
        Scan.project_name == source_scan.project_name,
        Scan.status == "completed",
        Scan.scan_type == "forbidden",
        Scan.completed_at.isnot(None),
        Scan.completed_at > source_scan_date,
    )

    if source_violation.hash_from_ci:
        matching_query = matching_query.filter(
            ForbiddenViolation.hash_from_ci == source_violation.hash_from_ci
        )
    else:
        matching_query = matching_query.filter(
            ForbiddenViolation.path == source_violation.path,
            ForbiddenViolation.extension == source_violation.extension,
        )

    affected_scan_ids = set()
    for matching in matching_query.all():
        apply_violation_status(matching, status, comment, current_user, changed_at)
        affected_scan_ids.add(matching.scan_id)

    return affected_scan_ids


async def process_forbidden_results_background(scan_id: str, data: dict, db_session: Session):
    start_time = datetime.now()

    try:
        scan = db_session.query(Scan).filter(Scan.id == scan_id).first()
        if not scan:
            logger.error("Forbidden scan not found: %s", scan_id)
            return

        project = db_session.query(Project).filter(Project.name == scan.project_name).first()
        repo_url = project.repo_url if project else ""

        if data.get("Status") == "Error":
            scan.status = "failed"
            scan.completed_at = datetime.now()
            scan.error_message = data.get("Message", "Unknown error during forbidden check")
            db_session.commit()
            return

        if data.get("Status") != "completed":
            logger.error("Unknown forbidden callback status for %s: %s", scan_id, data.get("Status"))
            return

        logger.info("Forbidden check completed for scan %s", scan_id)
        scan.status = "completed"
        scan.scan_type = "forbidden"
        if data.get("RepoCommit"):
            scan.repo_commit = data.get("RepoCommit")
        scan.completed_at = datetime.now()

        results = data.get("Results") or {}
        summary = results.get("summary") or {}
        scan.files_scanned = summary.get("total_files") or results.get("total_files")

        forbidden_summary = {
            "languages": results.get("languages", {}),
            "categories": results.get("categories", {}),
            "extensions_found": results.get("extensions_found", {}),
            "blocking_extensions": results.get("blocking_extensions", {}),
            "non_blocking_extensions": results.get("non_blocking_extensions", {}),
            "summary": summary,
        }
        scan.forbidden_summary = json.dumps(forbidden_summary, ensure_ascii=False)
        db_session.commit()

        db_session.query(ForbiddenViolation).filter(ForbiddenViolation.scan_id == scan_id).delete()
        db_session.commit()

        violations = results.get("violations") or []
        batch_size = 1000
        total_processed = 0

        for i in range(0, len(violations), batch_size):
            batch = violations[i:i + batch_size]
            batch_hashes = {
                build_forbidden_hash_from_ci(repo_url, item.get("path", ""))
                for item in batch
            }
            previous_decisions = load_latest_violation_decisions_by_hash(
                db_session, scan.project_name, scan_id, batch_hashes
            )

            batch_rows = []
            for item in batch:
                path = normalize_path_for_ci_hash(sanitize_string(item.get("path", "")))
                violation_hash = build_forbidden_hash_from_ci(repo_url, path)
                previous = previous_decisions.get(violation_hash)

                if previous:
                    if previous.status == "Refuted":
                        status = "Refuted"
                        is_exception = True
                        exception_comment = previous.exception_comment
                        refuted_at = previous.refuted_at
                        refuted_by = previous.refuted_by
                        confirmed_by = None
                    elif previous.status == "Confirmed":
                        status = "Confirmed"
                        is_exception = False
                        exception_comment = None
                        refuted_at = None
                        refuted_by = None
                        confirmed_by = previous.confirmed_by
                    else:
                        status = "No status"
                        is_exception = False
                        exception_comment = None
                        refuted_at = None
                        refuted_by = None
                        confirmed_by = None
                else:
                    status = "No status"
                    is_exception = False
                    exception_comment = None
                    refuted_at = None
                    refuted_by = None
                    confirmed_by = None

                reasons = item.get("violation_reasons") or []
                batch_rows.append(
                    ForbiddenViolation(
                        scan_id=scan_id,
                        path=path,
                        size=item.get("size"),
                        category=sanitize_string(item.get("category", "")),
                        language=sanitize_string(item.get("language", "")),
                        extension=sanitize_string(item.get("extension", "")),
                        is_binary=bool(item.get("is_binary", False)),
                        binary_reason=sanitize_string(item.get("binary_reason", "")),
                        is_blocking=bool(item.get("is_blocking", True)),
                        violation_reasons=json.dumps(reasons, ensure_ascii=False),
                        hash_from_ci=violation_hash,
                        status=status,
                        is_exception=is_exception,
                        exception_comment=sanitize_string(exception_comment) if exception_comment else None,
                        refuted_at=refuted_at,
                        confirmed_by=confirmed_by,
                        refuted_by=refuted_by,
                    )
                )

            if batch_rows:
                db_session.add_all(batch_rows)
                db_session.commit()
                total_processed += len(batch_rows)

        update_forbidden_scan_counters(db_session, scan_id)
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            "Forbidden scan %s processed: %s violations in %.2fs",
            scan_id,
            total_processed,
            elapsed,
        )

    except Exception as e:
        logger.error("Forbidden results processing failed for %s: %s", scan_id, e, exc_info=True)
        try:
            scan = db_session.query(Scan).filter(Scan.id == scan_id).first()
            if scan:
                scan.status = "failed"
                scan.completed_at = datetime.now()
                scan.error_message = f"Forbidden processing error: {e}"
                db_session.commit()
        except Exception:
            pass
