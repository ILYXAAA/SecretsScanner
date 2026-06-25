import base64
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

import httpx

from config import (
    FALSES_GIT_BINARY,
    FALSES_GIT_BRANCH,
    FALSES_GIT_COMMITTER_EMAIL,
    FALSES_GIT_COMMITTER_NAME,
    FALSES_GIT_FILE_PATH,
    FALSES_GIT_PAT,
    FALSES_GIT_REPO_URL,
    FALSES_GIT_SSL_VERIFY,
    FALSES_GIT_USERNAME,
)

falses_git_logger = logging.getLogger("falses_export")

ADO_API_VERSION = "6.1-preview"
NULL_OID = "0" * 40
MAX_PUSH_ATTEMPTS = 3
# Azure DevOps REST Push limit is 25 MB; use git CLI above this threshold.
MAX_REST_PUSH_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class AdoGitTarget:
    apis_base: str
    project: str
    repo_name: str


def is_falses_git_push_configured() -> bool:
    return bool(FALSES_GIT_REPO_URL and FALSES_GIT_PAT)


def parse_ado_git_repo_url(repo_url: str) -> AdoGitTarget:
    """Parse Azure DevOps Git remote URL into REST API base and repo name."""
    url = repo_url.strip().rstrip("/")
    if url.lower().endswith(".git"):
        url = url[:-4]

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid repository URL: {repo_url}")

    segments = [segment for segment in parsed.path.split("/") if segment]
    if "_git" not in segments:
        raise ValueError(f"URL does not look like an Azure DevOps git repository: {repo_url}")

    git_index = segments.index("_git")
    if git_index < 1 or git_index + 1 >= len(segments):
        raise ValueError(f"Could not parse repository name from URL: {repo_url}")

    repo_name = segments[git_index + 1]
    project = segments[git_index - 1]
    host = f"{parsed.scheme}://{parsed.netloc}"

    if parsed.netloc.lower() == "dev.azure.com":
        organization = segments[0]
        apis_base = f"{host}/{organization}/{project}/_apis"
    else:
        collection_path = "/".join(segments[:git_index - 1])
        apis_base = f"{host}/{collection_path}/{project}/_apis"

    return AdoGitTarget(apis_base=apis_base, project=project, repo_name=repo_name)


def _normalize_repo_file_path(file_path: str) -> str:
    path = (file_path or "/src/storage/falses.txt").strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _auth_headers() -> dict:
    token = (FALSES_GIT_PAT or "").strip()
    encoded = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


class AzureDevOpsFalsesPusher:
    def __init__(self, target: AdoGitTarget, client: httpx.Client):
        self.target = target
        self.client = client
        self._repo_id: Optional[str] = None

    def _repo_url(self, suffix: str) -> str:
        return f"{self.target.apis_base}/git/repositories/{suffix}?api-version={ADO_API_VERSION}"

    def get_repository_id(self) -> str:
        if self._repo_id:
            return self._repo_id

        response = self.client.get(
            self._repo_url(self.target.repo_name),
            headers=_auth_headers(),
        )
        response.raise_for_status()
        repo_id = response.json().get("id")
        if not repo_id:
            raise RuntimeError(f"Repository '{self.target.repo_name}' not found in Azure DevOps")
        self._repo_id = repo_id
        return repo_id

    def get_branch_object_id(self, branch_name: str) -> str:
        self.get_repository_id()
        response = self.client.get(
            self._repo_url(f"{self.target.repo_name}/refs"),
            headers=_auth_headers(),
            params={"filter": f"heads/{branch_name}"},
        )
        response.raise_for_status()
        refs = response.json().get("value", [])
        if not refs:
            return NULL_OID
        return refs[0].get("objectId") or NULL_OID

    def file_exists_on_branch(self, branch_name: str, file_path: str) -> bool:
        self.get_repository_id()
        response = self.client.get(
            self._repo_url(f"{self.target.repo_name}/items"),
            headers=_auth_headers(),
            params={
                "path": file_path,
                "includeContent": "false",
                "versionDescriptor.version": branch_name,
                "versionDescriptor.versionType": "branch",
            },
        )
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def push_file(self, branch_name: str, file_path: str, content: str, content_hash: str, hash_count: int) -> dict:
        self.get_repository_id()
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
        ref_name = f"refs/heads/{branch_name}"
        commit_message = f"chore: update falses.txt (sha256={content_hash[:16]}, count={hash_count})"

        last_error = "unknown push error"
        for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
            old_object_id = self.get_branch_object_id(branch_name)
            change_type = "edit" if old_object_id != NULL_OID and self.file_exists_on_branch(branch_name, file_path) else "add"

            payload = {
                "refUpdates": [
                    {
                        "name": ref_name,
                        "oldObjectId": old_object_id,
                    }
                ],
                "commits": [
                    {
                        "comment": commit_message,
                        "author": {
                            "name": FALSES_GIT_COMMITTER_NAME,
                            "email": FALSES_GIT_COMMITTER_EMAIL,
                            "date": datetime.now(timezone.utc).isoformat(),
                        },
                        "changes": [
                            {
                                "changeType": change_type,
                                "item": {"path": file_path},
                                "newContent": {
                                    "content": encoded_content,
                                    "contentType": "base64encoded",
                                },
                            }
                        ],
                    }
                ],
            }

            response = self.client.post(
                self._repo_url(f"{self.target.repo_name}/pushes"),
                headers=_auth_headers(),
                json=payload,
            )

            if response.status_code < 400:
                body = response.json()
                commits = body.get("commits") or []
                commit_id = commits[0].get("commitId") if commits else None
                falses_git_logger.info(
                    "Pushed falses.txt to %s@%s (commit=%s, attempt=%s)",
                    self.target.repo_name,
                    branch_name,
                    (commit_id or "")[:12],
                    attempt,
                )
                return {
                    "pushed": True,
                    "branch": branch_name,
                    "commit_id": commit_id,
                    "repository": self.target.repo_name,
                    "attempt": attempt,
                }

            last_error = response.text
            if response.status_code in (409, 412) and attempt < MAX_PUSH_ATTEMPTS:
                falses_git_logger.warning(
                    "Azure DevOps push rejected (attempt %s/%s), retrying: %s",
                    attempt,
                    MAX_PUSH_ATTEMPTS,
                    response.status_code,
                )
                continue

            response.raise_for_status()

        raise RuntimeError(f"Failed to push falses.txt after {MAX_PUSH_ATTEMPTS} attempts: {last_error}")


def build_git_repo_url(repo_url: str) -> str:
    """Normalize Azure DevOps web URL (no credentials embedded)."""
    url = repo_url.strip().rstrip("/")
    if url.lower().endswith(".git"):
        url = url[:-4]
    return url


def _git_basic_auth_header(pat: str) -> str:
    """Same Basic auth as Azure DevOps REST API (:PAT base64)."""
    token = (pat or "").strip().strip('"').strip("'")
    encoded = base64.b64encode(f":{token}".encode("utf-8")).decode("ascii")
    return f"Authorization: Basic {encoded}"


def build_git_auth_url(repo_url: str, pat: str, username: Optional[str] = None) -> str:
    """Fallback: embed credentials in URL (some old git versions)."""
    url = build_git_repo_url(repo_url)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    user = quote((username if username is not None else FALSES_GIT_USERNAME) or "git", safe="")
    password = quote((pat or "").strip().strip('"').strip("'"), safe="")
    return f"{parsed.scheme}://{user}:{password}@{host}{parsed.path}"


def _git_config_prefix(*, with_auth: bool = True) -> list[str]:
    configs: list[str] = []
    if not FALSES_GIT_SSL_VERIFY:
        configs.extend(["-c", "http.sslVerify=false"])
    if with_auth and FALSES_GIT_PAT:
        configs.extend(["-c", f"http.extraHeader={_git_basic_auth_header(FALSES_GIT_PAT)}"])
    return configs


def _git_cmd(*args: str, with_auth: bool = True) -> list[str]:
    git = _resolve_git_binary()
    return [git, *_git_config_prefix(with_auth=with_auth), *args]


def _resolve_git_binary() -> str:
    """Find git executable; service processes often have a minimal PATH."""
    configured = (FALSES_GIT_BINARY or "").strip()
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise RuntimeError(f"FALSES_GIT_BINARY not found: {configured}")
        return str(path)

    found = shutil.which("git")
    if found:
        return found

    for candidate in ("/usr/bin/git", "/usr/local/bin/git", "/bin/git"):
        if Path(candidate).is_file():
            return candidate

    raise RuntimeError(
        "git executable not found. Install git or set FALSES_GIT_BINARY in .env "
        "(e.g. FALSES_GIT_BINARY=/usr/bin/git)"
    )


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stderr or result.stdout}"
        )
    return result


def _try_clone_variants(
    clone_url: str,
    repo_dir: Path,
    branch_name: str,
    work_dir: Path,
    *,
    with_auth_header: bool,
) -> Optional[bool]:
    """Returns True if remote branch exists, False if new branch, None if all strategies failed."""
    with_branch = [
        ["clone", "--filter=blob:none", "--sparse", "--depth", "1", "-b", branch_name, clone_url, str(repo_dir)],
        ["clone", "--filter=blob:none", "--depth", "1", "-b", branch_name, clone_url, str(repo_dir)],
        ["clone", "--depth", "1", "-b", branch_name, clone_url, str(repo_dir)],
    ]
    for clone_args in with_branch:
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        try:
            _run_git(_git_cmd(*clone_args, with_auth=with_auth_header), cwd=work_dir)
            falses_git_logger.info("git clone ok: %s", " ".join(clone_args[:6]))
            return True
        except RuntimeError:
            continue

    without_branch = [
        ["clone", "--filter=blob:none", "--sparse", "--depth", "1", clone_url, str(repo_dir)],
        ["clone", "--filter=blob:none", "--depth", "1", clone_url, str(repo_dir)],
        ["clone", "--depth", "1", clone_url, str(repo_dir)],
    ]
    for clone_args in without_branch:
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        try:
            _run_git(_git_cmd(*clone_args, with_auth=with_auth_header), cwd=work_dir)
            _run_git(_git_cmd("checkout", "-b", branch_name, with_auth=False), cwd=repo_dir)
            falses_git_logger.info("git clone ok (new branch): %s", " ".join(clone_args[:5]))
            return False
        except RuntimeError:
            continue

    return None


def _clone_ado_repo(repo_dir: Path, branch_name: str, work_dir: Path) -> bool:
    """Clone Azure DevOps repo; returns True when remote branch exists."""
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)

    auth_attempts = [
        ("header", build_git_repo_url(FALSES_GIT_REPO_URL), True),
        ("url", build_git_auth_url(FALSES_GIT_REPO_URL, FALSES_GIT_PAT), False),
    ]
    last_error: Optional[RuntimeError] = None
    for auth_mode, clone_url, with_auth_header in auth_attempts:
        try:
            result = _try_clone_variants(
                clone_url, repo_dir, branch_name, work_dir, with_auth_header=with_auth_header
            )
            if result is not None:
                falses_git_logger.info("git clone auth mode: %s", auth_mode)
                return result
        except RuntimeError as exc:
            last_error = exc

    raise last_error or RuntimeError("git clone failed (check FALSES_GIT_PAT and FALSES_GIT_REPO_URL)")


def _try_sparse_checkout(repo_dir: Path, sparse_dir: str) -> None:
    if not sparse_dir or sparse_dir == ".":
        return
    result = _run_git(
        _git_cmd("sparse-checkout", "set", sparse_dir, with_auth=False),
        cwd=repo_dir,
        check=False,
    )
    if result.returncode != 0:
        falses_git_logger.info(
            "sparse-checkout unavailable, continuing with full shallow clone"
        )


def push_falses_via_git_cli(
    file_path: Path, content_hash: str, hash_count: int, *, force_push: bool = False
) -> dict:
    """Push via native git (no 25 MB REST API limit)."""
    branch_name = (FALSES_GIT_BRANCH or "script_with_Docker").strip()
    repo_file_path = _normalize_repo_file_path(FALSES_GIT_FILE_PATH).lstrip("/")
    sparse_dir = str(Path(repo_file_path).parent).replace("\\", "/")
    commit_message = f"chore: update falses.txt (sha256={content_hash[:16]}, count={hash_count})"

    with tempfile.TemporaryDirectory(prefix="falses_git_push_") as tmp:
        repo_dir = Path(tmp) / "repo"
        work_dir = Path(tmp)
        branch_exists_remotely = _clone_ado_repo(repo_dir, branch_name, work_dir)
        _try_sparse_checkout(repo_dir, sparse_dir)

        dest = repo_dir / repo_file_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)

        _run_git(_git_cmd("config", "user.name", FALSES_GIT_COMMITTER_NAME, with_auth=False), cwd=repo_dir)
        _run_git(_git_cmd("config", "user.email", FALSES_GIT_COMMITTER_EMAIL, with_auth=False), cwd=repo_dir)
        _run_git(_git_cmd("add", repo_file_path, with_auth=False), cwd=repo_dir)

        diff = _run_git(_git_cmd("diff", "--cached", "--quiet", with_auth=False), cwd=repo_dir, check=False)
        if diff.returncode == 0:
            if not force_push:
                falses_git_logger.info(
                    "falses.txt git push skipped: remote already has identical content"
                )
                return {"pushed": False, "skipped": True, "reason": "no changes", "method": "git"}
            falses_git_logger.info(
                "falses.txt unchanged on remote, creating startup sync commit"
            )
            _run_git(_git_cmd("commit", "--allow-empty", "-m", commit_message, with_auth=False), cwd=repo_dir)
        else:
            _run_git(_git_cmd("commit", "-m", commit_message, with_auth=False), cwd=repo_dir)
        if branch_exists_remotely:
            _run_git(_git_cmd("push", "origin", branch_name), cwd=repo_dir)
        else:
            _run_git(_git_cmd("push", "-u", "origin", branch_name), cwd=repo_dir)

        falses_git_logger.info(
            "Pushed falses.txt via git to %s@%s",
            parse_ado_git_repo_url(FALSES_GIT_REPO_URL).repo_name,
            branch_name,
        )
        return {
            "pushed": True,
            "method": "git",
            "branch": branch_name,
            "repository": parse_ado_git_repo_url(FALSES_GIT_REPO_URL).repo_name,
        }


def push_falses_file_to_git(
    file_path: Path, content_hash: str, hash_count: int, *, force_push: bool = False
) -> dict:
    """Push generated falses.txt to the configured Azure DevOps branch."""
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

    target = parse_ado_git_repo_url(FALSES_GIT_REPO_URL)
    repo_file_path = _normalize_repo_file_path(FALSES_GIT_FILE_PATH)
    branch_name = (FALSES_GIT_BRANCH or "script_with_Docker").strip()

    with httpx.Client(timeout=60.0, verify=FALSES_GIT_SSL_VERIFY) as client:
        pusher = AzureDevOpsFalsesPusher(target, client)
        result = pusher.push_file(branch_name, repo_file_path, content, content_hash, hash_count)
        result["method"] = "rest"
        return result
