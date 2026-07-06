import logging

from config import (
    FALSES_GIT_PAT,
    LANGUAGE_SEARCH_GIT_BRANCH,
    LANGUAGE_SEARCH_GIT_CONFIG_PATH,
    LANGUAGE_SEARCH_GIT_FALSES_PATH,
    LANGUAGE_SEARCH_GIT_REPO_URL,
)
from services.ado_git_push_service import GitPushOptions, is_git_push_configured_for, push_content_to_git

language_search_git_logger = logging.getLogger("language_search_git_push")


def language_search_git_options() -> GitPushOptions:
    return GitPushOptions(
        repo_url=LANGUAGE_SEARCH_GIT_REPO_URL,
        branch=LANGUAGE_SEARCH_GIT_BRANCH or "main",
        pat=FALSES_GIT_PAT or "",
    )


def is_language_search_git_push_configured() -> bool:
    return is_git_push_configured_for(language_search_git_options())


def push_language_search_file_to_git(content: str, repo_file_path: str, commit_message: str) -> dict:
    if not is_language_search_git_push_configured():
        return {"pushed": False, "skipped": True, "reason": "git push not configured"}

    language_search_git_logger.info("Pushing %s to LANGUAGE_SEARCH", repo_file_path)
    result = push_content_to_git(
        content,
        repo_file_path,
        commit_message,
        options=language_search_git_options(),
    )
    result["path"] = repo_file_path
    return result


def push_forbidden_falses_to_git(content: str, content_hash: str, hash_count: int) -> dict:
    commit_message = "chore: update falses.txt (sha256=%s, count=%s)" % (content_hash[:16], hash_count)
    return push_language_search_file_to_git(content, LANGUAGE_SEARCH_GIT_FALSES_PATH, commit_message)


def push_languages_config_to_git(content: str, username: str) -> dict:
    commit_message = "automatic update languages_repo_config.yml by %s" % username
    return push_language_search_file_to_git(content, LANGUAGE_SEARCH_GIT_CONFIG_PATH, commit_message)
