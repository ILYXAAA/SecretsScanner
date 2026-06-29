import base64
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from config import (
    FALSES_GIT_BINARY,
    FALSES_GIT_BRANCH,
    FALSES_GIT_COMMITTER_EMAIL,
    FALSES_GIT_COMMITTER_NAME,
    FALSES_GIT_PAT,
    FALSES_GIT_REPO_URL,
    FALSES_GIT_SSL_VERIFY,
)

ado_git_logger = logging.getLogger("ado_git_push")

ADO_API_VERSION = "6.1-preview"
NULL_OID = "0" * 40
MAX_PUSH_ATTEMPTS = 3
MAX_REST_PUSH_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class AdoGitTarget:
    apis_base: str
    project: str
    repo_name: str


def is_ado_git_push_configured() -> bool:
    return bool(FALSES_GIT_REPO_URL and FALSES_GIT_PAT)


def parse_ado_git_repo_url(repo_url: str) -> AdoGitTarget:
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
    path = (file_path or "").strip()
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


class AzureDevOpsGitPusher:
    def __init__(self, target: AdoGitTarget, client: httpx.Client):
        self.target = target
        self.client = client
        self._repo_id = None

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

    def push_file(self, branch_name: str, file_path: str, content: str, commit_message: str) -> dict:
        self.get_repository_id()
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
        ref_name = f"refs/heads/{branch_name}"

        last_error = "unknown push error"
        for attempt in range(1, MAX_PUSH_ATTEMPTS + 1):
            old_object_id = self.get_branch_object_id(branch_name)
            change_type = (
                "edit"
                if old_object_id != NULL_OID and self.file_exists_on_branch(branch_name, file_path)
                else "add"
            )

            payload = {
                "refUpdates": [{"name": ref_name, "oldObjectId": old_object_id}],
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
                ado_git_logger.info(
                    "Pushed %s to %s@%s (commit=%s, attempt=%s)",
                    file_path,
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
                ado_git_logger.warning(
                    "Azure DevOps push rejected (attempt %s/%s), retrying: %s",
                    attempt,
                    MAX_PUSH_ATTEMPTS,
                    response.status_code,
                )
                continue

            response.raise_for_status()

        raise RuntimeError(f"Failed to push {file_path} after {MAX_PUSH_ATTEMPTS} attempts: {last_error}")


def build_git_repo_url(repo_url):
    url = repo_url.strip().rstrip("/")
    if url.lower().endswith(".git"):
        url = url[:-4]
    return url


def _normalize_pat(pat):
    return (pat or "").strip().strip('"').strip("'")


def _git_auth_url():
    url = build_git_repo_url(FALSES_GIT_REPO_URL)
    parsed = urlparse(url)
    host = "%s:%s" % (parsed.hostname, parsed.port) if parsed.port else parsed.hostname
    pat = _normalize_pat(FALSES_GIT_PAT)
    return "%s://:%s@%s%s" % (parsed.scheme, quote(pat, safe=""), host, parsed.path)


def _git_basic_b64():
    pat = _normalize_pat(FALSES_GIT_PAT)
    return base64.b64encode((":%s" % pat).encode("utf-8")).decode("ascii")


def _resolve_git_binary():
    configured = (FALSES_GIT_BINARY or "").strip()
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise RuntimeError("FALSES_GIT_BINARY not found: %s" % configured)
        return str(path)
    found = shutil.which("git")
    if found:
        return found
    for candidate in ("/usr/bin/git", "/usr/local/bin/git", "/bin/git"):
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError(
        "git executable not found. Install git or set FALSES_GIT_BINARY=/usr/bin/git"
    )


def _git_cmd(use_extraheader=False):
    cmd = [_resolve_git_binary()]
    if not FALSES_GIT_SSL_VERIFY:
        cmd.extend(["-c", "http.sslVerify=false"])
    if use_extraheader:
        cmd.extend(["-c", "http.extraheader=AUTHORIZATION: basic %s" % _git_basic_b64()])
    return cmd


def _run_git(args, cwd, check=True, timeout=600):
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git command timed out after %ss: %s" % (timeout, " ".join(args))) from exc

    if check and result.returncode != 0:
        if result.returncode < 0:
            signal_hint = " (process killed by signal %s)" % (-result.returncode,)
        else:
            signal_hint = ""
        raise RuntimeError(
            "git command failed (%s)%s: %s\n%s"
            % (result.returncode, signal_hint, " ".join(args), result.stderr or result.stdout)
        )
    return result


def _git_run(args, cwd, check=True, timeout=600, use_extraheader=False):
    _run_git(_git_cmd(use_extraheader) + list(args), cwd, check=check, timeout=timeout)


def _git_clone_repo(repo_dir, branch_name, work_dir):
    if repo_dir.exists():
        shutil.rmtree(repo_dir, ignore_errors=True)

    clone_attempts = [
        ("url", _git_auth_url(), False),
        ("extraheader", build_git_repo_url(FALSES_GIT_REPO_URL), True),
    ]

    for auth_name, clone_url, use_extraheader in clone_attempts:
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        try:
            _git_run(
                ["clone", "-b", branch_name, clone_url, str(repo_dir)],
                work_dir,
                use_extraheader=use_extraheader,
            )
            ado_git_logger.info("git clone ok (auth=%s): clone -b %s", auth_name, branch_name)
            return True, use_extraheader
        except RuntimeError:
            pass

        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)
        try:
            _git_run(["clone", clone_url, str(repo_dir)], work_dir, use_extraheader=use_extraheader)
            _git_run(["checkout", "-b", branch_name], repo_dir, use_extraheader=use_extraheader)
            ado_git_logger.info("git clone ok new branch (auth=%s)", auth_name)
            return False, use_extraheader
        except RuntimeError:
            continue

    raise RuntimeError("git clone failed (check FALSES_GIT_PAT and FALSES_GIT_REPO_URL)")


def push_content_via_git_cli(content: str, repo_file_path: str, commit_message: str, force_push=False):
    branch_name = (FALSES_GIT_BRANCH or "script_with_Docker").strip()
    repo_rel_path = _normalize_repo_file_path(repo_file_path).lstrip("/")

    with tempfile.TemporaryDirectory(prefix="ado_git_push_") as tmp:
        repo_dir = Path(tmp) / "repo"
        work_dir = Path(tmp)
        local_file = Path(tmp) / "payload"
        local_file.write_text(content, encoding="utf-8")

        ado_git_logger.info("git clone starting (branch=%s)", branch_name)
        branch_remote, use_extraheader = _git_clone_repo(repo_dir, branch_name, work_dir)

        dest = repo_dir / repo_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        ado_git_logger.info("copying file into clone at %s", dest)
        shutil.copy2(local_file, dest)

        _git_run(["config", "user.name", FALSES_GIT_COMMITTER_NAME], repo_dir)
        _git_run(["config", "user.email", FALSES_GIT_COMMITTER_EMAIL], repo_dir)
        _git_run(["config", "http.postBuffer", "524288000"], repo_dir)
        ado_git_logger.info("git add %s", repo_rel_path)
        _git_run(["add", repo_rel_path], repo_dir)

        diff = _run_git(_git_cmd(use_extraheader) + ["diff", "--cached", "--quiet"], repo_dir, check=False)
        if diff.returncode == 0:
            if not force_push:
                ado_git_logger.info("git push skipped: remote already has identical content for %s", repo_rel_path)
                return {"pushed": False, "skipped": True, "reason": "no changes", "method": "git"}
            _git_run(["commit", "--allow-empty", "-m", commit_message], repo_dir, use_extraheader=use_extraheader)
        else:
            _git_run(["commit", "-m", commit_message], repo_dir, use_extraheader=use_extraheader)

        push_args = ["push", "-u", "origin", branch_name] if not branch_remote else ["push", "origin", branch_name]
        ado_git_logger.info("git push starting (%s)", " ".join(push_args))
        _git_run(push_args, repo_dir, timeout=1800, use_extraheader=use_extraheader)

        target = parse_ado_git_repo_url(FALSES_GIT_REPO_URL)
        ado_git_logger.info("Pushed %s via git to %s@%s", repo_rel_path, target.repo_name, branch_name)
        return {
            "pushed": True,
            "method": "git",
            "branch": branch_name,
            "repository": target.repo_name,
        }


def push_content_to_git(content: str, repo_file_path: str, commit_message: str, force_push=False):
    if not is_ado_git_push_configured():
        return {"pushed": False, "skipped": True, "reason": "git push not configured"}

    content_size = len(content.encode("utf-8"))
    if content_size > MAX_REST_PUSH_BYTES:
        ado_git_logger.info(
            "File %s is %s MB — using git CLI push, git=%s",
            repo_file_path,
            round(content_size / (1024 * 1024), 1),
            _resolve_git_binary(),
        )
        return push_content_via_git_cli(content, repo_file_path, commit_message, force_push=force_push)

    target = parse_ado_git_repo_url(FALSES_GIT_REPO_URL)
    api_file_path = _normalize_repo_file_path(repo_file_path)
    branch_name = (FALSES_GIT_BRANCH or "script_with_Docker").strip()

    with httpx.Client(timeout=60.0, verify=FALSES_GIT_SSL_VERIFY) as client:
        pusher = AzureDevOpsGitPusher(target, client)
        result = pusher.push_file(branch_name, api_file_path, content, commit_message)
        result["method"] = "rest"
        return result
