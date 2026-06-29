import logging

from config import FALSES_GIT_FILE_PATH
from services.ado_git_push_service import (
    is_ado_git_push_configured,
    push_content_to_git,
    push_content_via_git_cli,
    MAX_REST_PUSH_BYTES,
    _resolve_git_binary,
)

falses_git_logger = logging.getLogger("falses_export")


def is_falses_git_push_configured() -> bool:
    return is_ado_git_push_configured()


def push_falses_via_git_cli(file_path, content_hash, hash_count, force_push=False):
    content = file_path.read_text(encoding="utf-8")
    commit_message = "chore: update falses.txt (sha256=%s, count=%s)" % (content_hash[:16], hash_count)
    return push_content_via_git_cli(
        content,
        FALSES_GIT_FILE_PATH,
        commit_message,
        force_push=force_push,
    )


def push_falses_file_to_git(file_path, content_hash, hash_count, force_push=False):
    if not is_falses_git_push_configured():
        return {"pushed": False, "skipped": True, "reason": "git push not configured"}

    content = file_path.read_text(encoding="utf-8")
    content_size = len(content.encode("utf-8"))
    if content_size > MAX_REST_PUSH_BYTES:
        falses_git_logger.info(
            "falses.txt is %s MB — using git CLI push (REST limit is 25 MB), git=%s",
            round(content_size / (1024 * 1024), 1),
            _resolve_git_binary(),
        )
        return push_falses_via_git_cli(file_path, content_hash, hash_count, force_push=force_push)

    commit_message = "chore: update falses.txt (sha256=%s, count=%s)" % (content_hash[:16], hash_count)
    return push_content_to_git(content, FALSES_GIT_FILE_PATH, commit_message, force_push=force_push)
