"""프로젝트의 저장 안 된 변경 전체: 보기, diff, Claude 커밋 메시지 초안, 승인 후 커밋."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from .commit_message import CommitMessageError, draft_commit_message, last_usage
from .db import get_session
from .gitops import GitError, all_changes, as_dict, commit, file_diff
from .gitops import fetch as git_fetch
from .gitops import push as git_push
from .models import Project
from .sync import refresh_project
from .usage import UsageIn, record_usage
from .tasks_api import FileChangeOut

router = APIRouter(prefix="/api/projects/{project_id}")


class FilesIn(BaseModel):
    files: list[str] = Field(min_length=1, max_length=2000)


class CommitIn(FilesIn):
    message: str = Field(min_length=1, max_length=10000)
    push: bool = False  # 커밋한 뒤 바로 push


def push_and_refresh(project_id: int, repo: str) -> dict:
    """push 결과를 돌려준다. 실패해도 예외 대신 오류 메시지를 담는다 (커밋은 이미 끝났으므로)."""
    try:
        output = git_push(repo)
        result = {"pushed": True, "push_output": output, "push_error": None}
    except GitError as exc:
        result = {"pushed": False, "push_output": None, "push_error": str(exc)}
    refresh_project(project_id)
    return result


def _repo(db: Session, project_id: int) -> str:
    project = db.get(Project, project_id)
    if project is None or not project.exists:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    return project.path


def _changes(repo: str):
    try:
        return all_changes(repo)
    except GitError as exc:
        raise HTTPException(409, f"변경 사항을 읽지 못했습니다: {exc}") from exc


def _pick(repo: str, files: list[str]):
    by_path = {c.path: c for c in _changes(repo)}
    unknown = [p for p in files if p not in by_path]
    if unknown:
        raise HTTPException(400, f"저장 안 된 변경이 아닌 파일이 있습니다: {', '.join(unknown[:5])}")
    return [by_path[p] for p in files]


@router.get("/changes", response_model=list[FileChangeOut])
def project_changes(project_id: int, db: Session = Depends(get_session)) -> list[FileChangeOut]:
    return [FileChangeOut(**as_dict(c)) for c in _changes(_repo(db, project_id))]


@router.get("/diff")
def project_diff(project_id: int, path: str, db: Session = Depends(get_session)) -> dict:
    repo = _repo(db, project_id)
    change = _pick(repo, [path])[0]
    return {"path": path, "diff": file_diff(repo, path, change.status)}


@router.post("/commit-message")
def project_commit_message(project_id: int, body: FilesIn, db: Session = Depends(get_session)) -> dict:
    repo = _repo(db, project_id)
    picked = _pick(repo, body.files)
    try:
        message, cost = draft_commit_message(repo, [as_dict(c) for c in picked])
    except CommitMessageError as exc:
        raise HTTPException(502, str(exc)) from exc
    # 세션 기록을 남기지 않는 실행이라 사용량을 직접 기록한다.
    u = last_usage()
    record_usage(db, UsageIn(
        provider="claude", unit="token", model=u.get("model"), project=repo, cost_usd=cost,
        input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
        cache_write_tokens=u.get("cache_write_tokens", 0), cache_read_tokens=u.get("cache_read_tokens", 0),
        source="commit_draft", meta={"purpose": "commit message draft"},
    ))
    return {"message": message, "cost_usd": cost}


@router.post("/commit")
def project_commit(project_id: int, body: CommitIn, db: Session = Depends(get_session)) -> dict:
    repo = _repo(db, project_id)
    _pick(repo, body.files)
    try:
        sha = commit(repo, body.files, body.message)
    except GitError as exc:
        raise HTTPException(409, f"커밋하지 못했습니다: {exc}") from exc
    result = {"sha": sha, "pushed": False, "push_output": None, "push_error": None}
    if body.push:
        result.update(push_and_refresh(project_id, repo))
    else:
        refresh_project(project_id)
    return result


@router.post("/push")
def project_push(project_id: int, db: Session = Depends(get_session)) -> dict:
    repo = _repo(db, project_id)
    result = push_and_refresh(project_id, repo)
    if not result["pushed"]:
        raise HTTPException(409, result["push_error"])
    project = db.get(Project, project_id)
    db.refresh(project)
    return {**result, "ahead": project.ahead, "behind": project.behind, "upstream": project.upstream}


@router.post("/fetch")
def project_fetch(project_id: int, db: Session = Depends(get_session)) -> dict:
    """원격의 최신 상태를 가져와 '원격에 새 커밋 N'을 갱신한다 (내 파일은 바꾸지 않음)."""
    repo = _repo(db, project_id)
    try:
        output = git_fetch(repo)
    except GitError as exc:
        raise HTTPException(409, str(exc)) from exc
    refresh_project(project_id)
    project = db.get(Project, project_id)
    db.refresh(project)
    return {"output": output, "ahead": project.ahead, "behind": project.behind, "upstream": project.upstream}


def web_url(remote: str) -> str | None:
    """git 원격 주소를 브라우저 주소로 바꾼다. (git@github.com:a/b.git, https://user:token@github.com/a/b.git → https://github.com/a/b)"""
    import re

    remote = remote.strip()
    m = re.match(r"^(?:ssh://)?[\w.\-]+@([\w.\-]+)(?::\d+)?[:/](.+?)(?:\.git)?/?$", remote)
    if m and not remote.startswith(("http://", "https://")):
        return f"https://{m.group(1)}/{m.group(2)}"
    m = re.match(r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$", remote)
    if m:
        return f"https://{m.group(1)}/{m.group(2)}"
    return None


@router.get("/remote")
def remote_info(project_id: int, db: Session = Depends(get_session)) -> dict:
    """원격 저장소의 웹 주소 (GitHub 등). 주소에 들어 있는 사용자 이름·토큰은 돌려주지 않는다."""
    import os
    import subprocess

    project = db.get(Project, project_id)
    if project is None or not project.exists:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")

    def git(*args: str) -> str:
        try:
            out = subprocess.run(["git", "-C", project.path, *args], capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return out.stdout.strip() if out.returncode == 0 else ""

    remotes = git("remote").split()
    # upstream(origin/main)의 원격을 먼저, 없으면 origin, 그다음 첫 번째 원격
    name = project.upstream.split("/", 1)[0] if project.upstream and "/" in project.upstream else None
    name = name if name in remotes else ("origin" if "origin" in remotes else (remotes[0] if remotes else None))
    if not name:
        return {"remote": None, "web_url": None, "branch_url": None, "host": None}
    url = web_url(git("remote", "get-url", name))
    branch = project.upstream.split("/", 1)[1] if project.upstream and "/" in project.upstream else None
    host = url.split("/")[2] if url else None
    branch_url = f"{url}/tree/{branch}" if url and branch and host in ("github.com", "gitlab.com") else None
    return {"remote": name, "web_url": url, "branch_url": branch_url, "host": host}
