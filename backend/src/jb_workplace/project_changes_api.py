"""프로젝트의 저장 안 된 변경 전체: 보기, diff, Claude 커밋 메시지 초안, 승인 후 커밋."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from .commit_message import CommitMessageError, draft_commit_message
from .db import get_session
from .gitops import GitError, all_changes, as_dict, commit, file_diff
from .gitops import push as git_push
from .models import Project
from .sync import refresh_project
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
