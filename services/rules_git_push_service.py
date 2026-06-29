import logging

from services.ado_git_push_service import is_ado_git_push_configured, push_content_to_git

rules_git_logger = logging.getLogger("rules_git_push")

RULES_REPO_DIR = "src/rules"

RULES_GIT_FILES = {
    "rules": "rules.yml",
    "fp_rules": "false-positive.yml",
    "extensions": "excluded_extensions.yml",
}


def is_rules_git_push_configured() -> bool:
    return is_ado_git_push_configured()


def push_rules_file_to_git(content: str, rules_key: str, username: str) -> dict:
    filename = RULES_GIT_FILES.get(rules_key)
    if not filename:
        raise ValueError(f"Unknown rules file key: {rules_key}")

    if not is_rules_git_push_configured():
        return {"pushed": False, "skipped": True, "reason": "git push not configured"}

    repo_path = f"{RULES_REPO_DIR}/{filename}"
    commit_message = f"automatic update {filename} by {username}"
    rules_git_logger.info("Pushing %s to git (user=%s)", repo_path, username)
    result = push_content_to_git(content, repo_path, commit_message)
    result["file"] = filename
    result["path"] = repo_path
    return result
