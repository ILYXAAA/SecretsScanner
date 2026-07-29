import hashlib
from urllib.parse import urlparse

DEVZONE_REPOSITORY_PREFIX = "/devzone_repository/"


def normalize_path_for_ci_hash(file_path: str) -> str:
    """
    Normalize file path for CI hash matching.
    Strips DevZone internal prefix and ensures a leading slash.
    """
    path = (file_path or "").replace(DEVZONE_REPOSITORY_PREFIX, "")
    if path and not path.startswith("/"):
        path = "/" + path
    return path


def normalize_path_for_forbidden_hash(file_path: str) -> str:
    """Relative path without leading slash for forbidden check falses hash."""
    path = (file_path or "").replace(DEVZONE_REPOSITORY_PREFIX, "")
    path = path.replace("\\", "/").lstrip("/")
    return path


def extract_repo_suffix(repo_url: str) -> str:
    """
    Extract collection[/project]/_git/reponame suffix from a repository URL.
    Strips trailing .git from the repository name segment.
    """
    url = (repo_url or "").strip().rstrip("/")
    if not url:
        return ""

    if "?" in url:
        url = url.split("?", 1)[0].rstrip("/")

    parsed = urlparse(url)
    path = parsed.path or ""
    segments = [s for s in path.split("/") if s]

    if "_git" not in segments:
        return ""

    git_index = segments.index("_git")
    if git_index + 1 >= len(segments):
        return ""

    repo_name = segments[git_index + 1]
    if repo_name.lower().endswith(".git"):
        repo_name = repo_name[:-4]

    suffix_segments = segments[:git_index] + ["_git", repo_name]
    return "/".join(suffix_segments)


def build_hash_from_ci(
    project_name: str,
    file_path: str,
    secret_value: str,
    line_number: int,
) -> str:
    """
    SHA-256 hash for external CI matching:
    project_name + normalized file path + secret value + line number (concatenated, no delimiter).
    """
    normalized_path = normalize_path_for_ci_hash(file_path)
    raw = f"{project_name or ''}{normalized_path}{secret_value or ''}{line_number}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_forbidden_hash_from_ci(repo_url: str, file_path: str) -> str:
    """
    SHA-256 hash for forbidden-check falses:
    repo_suffix + relative file path (no delimiter).
    """
    repo_suffix = extract_repo_suffix(repo_url)
    relative_path = normalize_path_for_forbidden_hash(file_path)
    raw = f"{repo_suffix}{relative_path}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
