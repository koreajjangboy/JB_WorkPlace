from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from .config import get_settings
from .db import get_session
from .models import ClaudeSession, Project
from .scanner.projects import list_folders
from .scanner.sessions import read_transcript
from .sync import add_project, hide_projects, last_result, run_scan

router = APIRouter(prefix="/api")


class ProjectOut(BaseModel):
    id: int
    name: str
    path: str
    branch: str | None
    dirty_files: int
    last_commit_at: datetime | None
    last_activity_at: datetime | None
    upstream: str | None
    ahead: int
    behind: int
    has_remote: bool
    session_count: int
    last_session_at: datetime | None
    input_tokens: int
    output_tokens: int


class SessionOut(BaseModel):
    id: str
    project_id: int | None
    project_name: str | None
    cwd: str | None
    git_branch: str | None
    title: str | None
    first_prompt: str | None
    started_at: datetime | None
    ended_at: datetime | None
    user_messages: int
    assistant_messages: int
    models: list[str]
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float | None


class ScanOut(BaseModel):
    projects: int
    sessions: int
    sessions_updated: int
    unmatched_sessions: int
    finished_at: datetime


def _session_out(s: ClaudeSession, project_name: str | None) -> SessionOut:
    return SessionOut(
        **s.model_dump(exclude={"file_path", "file_mtime", "models"}),
        project_name=project_name,
        models=s.models.split(",") if s.models else [],
    )


@router.get("/health")
def health(db: Session = Depends(get_session)) -> dict:
    db.exec(select(1)).one()
    result = last_result()
    return {"ok": True, "last_scan": result.finished_at if result else None}


@router.post("/scan", response_model=ScanOut)
def scan() -> ScanOut:
    return ScanOut(**run_scan().__dict__)


@router.get("/scan", response_model=ScanOut | None)
def scan_status() -> ScanOut | None:
    result = last_result()
    return ScanOut(**result.__dict__) if result else None


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_session)) -> list[ProjectOut]:
    stats = {
        row[0]: row[1:]
        for row in db.exec(
            select(
                ClaudeSession.project_id,
                func.count(ClaudeSession.id),
                func.max(ClaudeSession.ended_at),
                func.coalesce(func.sum(ClaudeSession.input_tokens), 0),
                func.coalesce(func.sum(ClaudeSession.output_tokens), 0),
            ).group_by(ClaudeSession.project_id)
        ).all()
    }
    projects = db.exec(
        select(Project)
        .where(Project.exists == True)  # noqa: E712
        .order_by(Project.last_activity_at.desc().nulls_last(), Project.name)
    ).all()
    out = []
    for p in projects:
        count, last_at, tin, tout = stats.get(p.id, (0, None, 0, 0))
        out.append(ProjectOut(
            **p.model_dump(include=set(ProjectOut.model_fields)),
            session_count=count,
            last_session_at=last_at,
            input_tokens=tin,
            output_tokens=tout,
        ))
    return out


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_session)) -> ProjectOut:
    for p in list_projects(db):
        if p.id == project_id:
            return p
    raise HTTPException(404, "프로젝트를 찾을 수 없습니다")


class ProjectAddIn(BaseModel):
    path: str


class ProjectHideIn(BaseModel):
    ids: list[int]


@router.post("/projects", response_model=ProjectOut)
def add_project_route(body: ProjectAddIn, db: Session = Depends(get_session)) -> ProjectOut:
    path = Path(body.path.strip())
    if not path.is_absolute() or not path.is_dir():
        raise HTTPException(400, "폴더를 찾을 수 없습니다")
    project = add_project(path)
    return get_project(project.id, db)


@router.post("/projects/hide")
def hide_projects_route(body: ProjectHideIn) -> dict:
    return {"hidden": hide_projects(body.ids)}


@router.get("/folders")
def browse_folders(path: str | None = None, db: Session = Depends(get_session)) -> dict:
    """프로젝트 추가 화면의 폴더 탐색. path가 없으면 스캔 폴더 목록부터 보여준다."""
    status = {p.path.rstrip("\\/").lower(): ("hidden" if p.hidden else "registered" if p.exists else None)
              for p in db.exec(select(Project)).all()}

    def entry(folder: Path, is_git: bool) -> dict:
        return {"name": folder.name or str(folder), "path": str(folder), "is_git": is_git,
                "status": status.get(str(folder).rstrip("\\/").lower())}

    if not path:
        roots = [r for r in get_settings().scan_root_paths if r.is_dir()]
        return {"path": None, "parent": None, "folders": [entry(r, (r / ".git").exists()) for r in roots]}
    folder = Path(path)
    if not folder.is_absolute() or not folder.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")
    parent = folder.parent if folder.parent != folder else None
    return {
        "path": str(folder),
        "parent": str(parent) if parent else None,
        "folders": [entry(f, g) for f, g in list_folders(folder)],
    }


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    project_id: int | None = None,
    unmatched: bool = False,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_session),
) -> list[SessionOut]:
    query = select(ClaudeSession, Project.name).join(Project, isouter=True)
    if project_id is not None:
        query = query.where(ClaudeSession.project_id == project_id)
    elif unmatched:
        query = query.where(ClaudeSession.project_id == None)  # noqa: E711
    query = query.order_by(ClaudeSession.ended_at.desc().nulls_last()).limit(limit)
    return [_session_out(s, name) for s, name in db.exec(query).all()]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session_detail(session_id: str, db: Session = Depends(get_session)) -> SessionOut:
    row = db.get(ClaudeSession, session_id)
    if row is None:
        raise HTTPException(404, "세션을 찾을 수 없습니다")
    project = db.get(Project, row.project_id) if row.project_id else None
    return _session_out(row, project.name if project else None)


@router.get("/sessions/{session_id}/transcript")
def get_transcript(
    session_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_session),
) -> dict:
    row = db.get(ClaudeSession, session_id)
    if row is None:
        raise HTTPException(404, "세션을 찾을 수 없습니다")
    path = Path(row.file_path)
    # 색인에 있는 경로라도 세션 기록 폴더 밖이면 읽지 않는다.
    base = get_settings().claude_projects_dir.resolve()
    if base not in path.resolve().parents or not path.is_file():
        raise HTTPException(404, "세션 기록 파일이 없습니다")
    entries = read_transcript(path)
    return {"total": len(entries), "offset": offset, "entries": entries[offset : offset + limit]}
