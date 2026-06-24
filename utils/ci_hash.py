import hashlib

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


def build_hash_from_ci(file_path: str, secret_value: str, line_number: int) -> str:
    """
    SHA-256 hash for external CI matching:
    normalized file path + secret value + line number (concatenated, no delimiter).
    """
    normalized_path = normalize_path_for_ci_hash(file_path)
    raw = f"{normalized_path}{secret_value or ''}{line_number}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
