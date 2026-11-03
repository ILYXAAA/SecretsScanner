"""Доставка файлов в репозиторий через Pull Request (GIT_PUSH_MODE=pr).

Для каждого файла бот держит свою ветку <GIT_PR_BRANCH_PREFIX>/<путь-файла>.
При каждом обновлении ветка пересобирается от текущей головы целевой ветки
(force push только в ветку бота), поэтому конфликтов с целевой веткой не бывает.
Открытый PR переиспользуется — новые обновления становятся новыми итерациями.
"""
import logging
import re
import shutil
import tempfile
from pathlib import Path

import httpx

from config import (
    GIT_PR_AUTO_COMPLETE,
    GIT_PR_BRANCH_PREFIX,
    GIT_PR_MERGE_STRATEGY,
)
from services.ado_git_push_service import (
    AzureDevOpsGitPusher,
    GitPushOptions,
    _auth_headers_for,
    _git_clone_repo,
    _git_cmd,
    _git_run,
    _normalize_repo_file_path,
    _run_git,
    parse_ado_git_repo_url,
)

ado_git_pr_logger = logging.getLogger("ado_git_pr")


def bot_branch_for(repo_file_path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", repo_file_path.strip("/")).strip("-")
    return f"{GIT_PR_BRANCH_PREFIX}/{slug}"


def _push_bot_branch(content, repo_rel_path, commit_message, target_branch, bot_branch, opts):
    """Коммитит файл поверх целевой ветки и force-push'ит в ветку бота.

    Возвращает "no changes" (целевая ветка уже содержит этот файл),
    "up to date" (ветка бота уже содержит тот же результат) или "pushed".
    """
    with tempfile.TemporaryDirectory(prefix="ado_git_pr_") as tmp:
        repo_dir = Path(tmp) / "repo"
        work_dir = Path(tmp)
        local_file = Path(tmp) / "payload"
        local_file.write_text(content, encoding="utf-8")

        ado_git_pr_logger.info("git clone starting (target=%s)", target_branch)
        target_exists, use_extraheader = _git_clone_repo(repo_dir, target_branch, work_dir, options=opts)
        if not target_exists:
            raise RuntimeError("Target branch '%s' not found — PR mode needs an existing branch" % target_branch)

        dest = repo_dir / repo_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_file, dest)

        _git_run(["config", "user.name", opts.committer_name], repo_dir, pat=opts.pat)
        _git_run(["config", "user.email", opts.committer_email], repo_dir, pat=opts.pat)
        _git_run(["config", "http.postBuffer", "524288000"], repo_dir, pat=opts.pat)
        _git_run(["add", repo_rel_path], repo_dir, pat=opts.pat)

        git = _git_cmd(use_extraheader, pat=opts.pat)
        diff = _run_git(git + ["diff", "--cached", "--quiet"], repo_dir, check=False)
        if diff.returncode == 0:
            return "no changes"

        _git_run(["commit", "-m", commit_message], repo_dir, use_extraheader=use_extraheader, pat=opts.pat)

        # Не пушим, если ветка бота уже собрана от той же головы с тем же содержимым:
        # лишняя итерация PR может сбросить уже поставленные одобрения
        fetch = _run_git(git + ["fetch", "origin", f"refs/heads/{bot_branch}"], repo_dir, check=False)
        if fetch.returncode == 0:
            local = _run_git(git + ["rev-parse", "HEAD^{tree}", "HEAD^"], repo_dir).stdout.split()
            remote = _run_git(git + ["rev-parse", "FETCH_HEAD^{tree}", "FETCH_HEAD^"], repo_dir, check=False).stdout.split()
            if local == remote:
                return "up to date"

        push_args = ["push", "--force", "origin", f"HEAD:refs/heads/{bot_branch}"]
        ado_git_pr_logger.info("git push starting (%s)", " ".join(push_args))
        _git_run(push_args, repo_dir, timeout=1800, use_extraheader=use_extraheader, pat=opts.pat)
        return "pushed"


def _find_active_pr(pusher: AzureDevOpsGitPusher, source_ref: str, target_ref: str):
    response = pusher.client.get(
        pusher._repo_url(f"{pusher.target.repo_name}/pullrequests"),
        headers=_auth_headers_for(pusher.options.pat),
        params={
            "searchCriteria.sourceRefName": source_ref,
            "searchCriteria.targetRefName": target_ref,
            "searchCriteria.status": "active",
        },
    )
    response.raise_for_status()
    prs = response.json().get("value", [])
    return prs[0] if prs else None


def _create_pr(pusher: AzureDevOpsGitPusher, source_ref, target_ref, title, repo_file_path):
    response = pusher.client.post(
        pusher._repo_url(f"{pusher.target.repo_name}/pullrequests"),
        headers=_auth_headers_for(pusher.options.pat),
        json={
            "sourceRefName": source_ref,
            "targetRefName": target_ref,
            "title": title[:400],
            "description": (
                "Автоматическое обновление `%s` от SecretsScanner.\n\n"
                "PR переиспользуется: последующие обновления файла приходят новыми итерациями." % repo_file_path
            ),
        },
    )
    response.raise_for_status()
    return response.json()


def _set_auto_complete(pusher: AzureDevOpsGitPusher, pr: dict):
    creator_id = (pr.get("createdBy") or {}).get("id")
    if not creator_id:
        return
    response = pusher.client.patch(
        pusher._repo_url(f"{pusher.target.repo_name}/pullrequests/{pr['pullRequestId']}"),
        headers=_auth_headers_for(pusher.options.pat),
        json={
            "autoCompleteSetBy": {"id": creator_id},
            "completionOptions": {
                "deleteSourceBranch": True,
                "mergeStrategy": GIT_PR_MERGE_STRATEGY,
                "mergeCommitMessage": pr.get("title", ""),
            },
        },
    )
    if response.status_code >= 400:
        # PR уже создан — без автозавершения его просто закроют вручную
        ado_git_pr_logger.warning(
            "Failed to enable auto-complete for PR #%s: %s %s",
            pr["pullRequestId"],
            response.status_code,
            response.text[:500],
        )


def _abandon_pr(pusher: AzureDevOpsGitPusher, pr: dict):
    response = pusher.client.patch(
        pusher._repo_url(f"{pusher.target.repo_name}/pullrequests/{pr['pullRequestId']}"),
        headers=_auth_headers_for(pusher.options.pat),
        json={"status": "abandoned"},
    )
    if response.status_code >= 400:
        ado_git_pr_logger.warning(
            "Failed to abandon stale PR #%s: %s %s",
            pr["pullRequestId"],
            response.status_code,
            response.text[:500],
        )
    else:
        ado_git_pr_logger.info("Abandoned stale PR #%s", pr["pullRequestId"])


def _pr_web_url(pr: dict) -> str | None:
    web_url = (pr.get("repository") or {}).get("webUrl")
    if not web_url:
        return None
    return f"{web_url}/pullrequest/{pr['pullRequestId']}"


def push_content_via_pull_request(
    content: str,
    repo_file_path: str,
    commit_message: str,
    options: GitPushOptions,
):
    target_branch = (options.branch or "script_with_Docker").strip()
    repo_rel_path = _normalize_repo_file_path(repo_file_path).lstrip("/")
    bot_branch = bot_branch_for(repo_rel_path)
    target = parse_ado_git_repo_url(options.repo_url)

    status = _push_bot_branch(content, repo_rel_path, commit_message, target_branch, bot_branch, options)
    source_ref = f"refs/heads/{bot_branch}"
    target_ref = f"refs/heads/{target_branch}"

    with httpx.Client(timeout=60.0, verify=options.ssl_verify) as client:
        pusher = AzureDevOpsGitPusher(target, client, options=options)
        pusher.get_repository_id()
        pr = _find_active_pr(pusher, source_ref, target_ref)

        if status == "no changes":
            # Целевая ветка уже совпадает с актуальным файлом — открытый PR со старым
            # содержимым больше не нужен, иначе после одобрения он откатит файл
            if pr:
                _abandon_pr(pusher, pr)
            ado_git_pr_logger.info("PR skipped: %s@%s already up to date", repo_rel_path, target_branch)
            return {"pushed": False, "skipped": True, "reason": "no changes", "method": "pr"}

        created = pr is None
        if created:
            pr = _create_pr(pusher, source_ref, target_ref, commit_message, repo_rel_path)
        if GIT_PR_AUTO_COMPLETE and not pr.get("autoCompleteSetBy"):
            _set_auto_complete(pusher, pr)

    pr_url = _pr_web_url(pr)
    ado_git_pr_logger.info(
        "%s PR #%s %s -> %s for %s (%s)",
        "Created" if created else "Updated",
        pr["pullRequestId"],
        bot_branch,
        target_branch,
        repo_rel_path,
        pr_url or "no url",
    )
    return {
        "pushed": True,
        "method": "pr",
        "branch": bot_branch,
        "target_branch": target_branch,
        "repository": target.repo_name,
        "pull_request_id": pr["pullRequestId"],
        "pull_request_url": pr_url,
        "pull_request_created": created,
        "bot_branch_updated": status == "pushed",
    }
