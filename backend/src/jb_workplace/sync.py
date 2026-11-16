"""스캔 결과를 DB에 반영한다. 서버 시작 시와 [다시 스캔] 버튼에서 호출된다."""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from .config import get_settings
from .db import engine
from .models import ClaudeSession, Project
from .scanner.projects import scan_repos
from .scanner.sessions import list_session_files, summarize_session

log = logging.getLogger(__name__)
_lock = threading.Lock()


@dataclass
class ScanResult:
    projects: int
    sessions: int
    sessions_updated: int
    unmatched_sessions: int
    finished_at: datetime


_last_result: ScanResult | None = None


def last_result() -> ScanResult | None:
    return _last_result


def _norm(path: str) -> str:
    return str(Path(path)).rstrip("\\/").lower()


def _match_project(cwd: str | None, projects: list[Project]) -> int | None:
    """세션의 작업 폴더(cwd)를 포함하는 가장 깊은 프로젝트를 고른다."""
    if not cwd:
        return None
    target = _norm(cwd)
    best: Project | None = None
    for project in projects:
        root = _norm(project.path)
        if target == root or target.startswith(root + "\\"):
            if best is None or len(root) > len(_norm(best.path)):
                best = project
    return best.id if best else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def _sync_projects(db: Session) -> list[Project]:
    settings = get_settings()
    now = datetime.now(UTC)
    repos = scan_repos(settings.scan_root_paths)
    existing = {_norm(p.path): p for p in db.exec(select(Project)).all()}
    seen: set[str] = set()

    for repo in repos:
        key = _norm(repo.path)
        seen.add(key)
        project = existing.get(key) or Project(name=repo.name, path=repo.path, scanned_at=now)
        project.name = repo.name
        project.branch = repo.branch
        project.dirty_files = repo.dirty_files
        project.last_commit_at = _as_utc(repo.last_commit_at)
        project.exists = True
        project.scanned_at = now
        db.add(project)

    for key, project in existing.items():
        if key not in seen:
            project.exists = False
            db.add(project)

    db.commit()
    return list(db.exec(select(Project).where(Project.exists == True)).all())  # noqa: E712


def _sync_sessions(db: Session, projects: list[Project]) -> tuple[int, int, int]:
    settings = get_settings()
    files = list_session_files(settings.claude_projects_dir)
    stored = {s.file_path: s for s in db.exec(select(ClaudeSession)).all()}
    seen_files: set[str] = set()
    updated = 0

    for path in files:
        key = str(path)
        seen_files.add(key)
        row = stored.get(key)
        mtime = path.stat().st_mtime
        if row is None:
            # 같은 세션이 폴더를 옮겨 두 파일로 남은 경우, 이미 색인된 파일 하나만 계속 쓴다.
            other = db.get(ClaudeSession, path.stem)
            if other and other.file_path != key and Path(other.file_path).exists():
                continue
        if row is None or row.file_mtime != mtime:
            try:
                summary = summarize_session(path)
            except OSError as exc:
                log.warning("세션 기록을 읽지 못함 %s: %s", path, exc)
                continue
            if summary is None:
                continue
            if row is None:
                # 같은 sessionId가 다른 파일에 이미 있으면 (폴더 이동 등) 그 행을 이어서 쓴다.
                row = db.get(ClaudeSession, summary.id) or ClaudeSession(
                    id=summary.id, file_path=key, file_mtime=mtime
                )
            row.file_path = key
            row.file_mtime = mtime
            row.cwd = summary.cwd
            row.git_branch = summary.git_branch
            row.title = summary.title
            row.first_prompt = summary.first_prompt
            row.started_at = _as_utc(summary.started_at)
            row.ended_at = _as_utc(summary.ended_at)
            row.user_messages = summary.user_messages
            row.assistant_messages = summary.assistant_messages
            row.models = ",".join(summary.models) or None
            row.input_tokens = summary.input_tokens
            row.output_tokens = summary.output_tokens
            row.cache_creation_tokens = summary.cache_creation_tokens
            row.cache_read_tokens = summary.cache_read_tokens
            row.cost_usd = summary.cost_usd
            updated += 1
        # 프로젝트 목록이 바뀌었을 수 있으니 연결은 매번 다시 계산한다.
        row.project_id = _match_project(row.cwd, projects)
        db.add(row)
        db.flush()

    for key, row in stored.items():
        # 파일이 사라진 세션은 지운다. 다른 파일로 옮겨 간 행(file_path가 바뀐 행)은 남긴다.
        if key not in seen_files and row.file_path == key and not Path(key).exists():
            db.delete(row)

    db.commit()
    sessions = db.exec(select(ClaudeSession)).all()
    unmatched = sum(1 for s in sessions if s.project_id is None)
    return len(sessions), updated, unmatched


def _promote_session_folders(db: Session, projects: list[Project]) -> list[Project]:
    """git 저장소가 아니어도 스캔 폴더 바로 아래에서 Claude 세션을 연 폴더는 프로젝트로 등록한다."""
    roots = [_norm(str(r)) for r in get_settings().scan_root_paths]
    known = {_norm(p.path) for p in projects}
    now = datetime.now(UTC)
    added = False
    for row in db.exec(select(ClaudeSession).where(ClaudeSession.project_id == None)).all():  # noqa: E711
        if not row.cwd:
            continue
        cwd = Path(row.cwd)
        for root in roots:
            rel = _norm(str(cwd))
            if not rel.startswith(root + "\\"):
                continue
            top = Path(root) / Path(rel[len(root) + 1 :]).parts[0]
            key = _norm(str(top))
            if key in known or not top.is_dir():
                break
            folder = Path(row.cwd[: len(str(top))])  # 원래 대소문자 유지
            project = db.exec(select(Project).where(func.lower(Project.path) == key)).first()
            if project is None:
                project = Project(name=folder.name, path=str(folder), scanned_at=now)
            project.exists = True
            project.scanned_at = now
            db.add(project)
            known.add(key)
            added = True
            break
    if not added:
        return projects
    db.commit()
    projects = list(db.exec(select(Project).where(Project.exists == True)).all())  # noqa: E712
    for row in db.exec(select(ClaudeSession).where(ClaudeSession.project_id == None)).all():  # noqa: E711
        row.project_id = _match_project(row.cwd, projects)
        db.add(row)
    db.commit()
    return projects


def _update_activity(db: Session, projects: list[Project]) -> None:
    for project in projects:
        last_session = db.exec(
            select(ClaudeSession.ended_at)
            .where(ClaudeSession.project_id == project.id)
            .order_by(ClaudeSession.ended_at.desc().nulls_last())
            .limit(1)
        ).first()
        candidates = [t for t in (project.last_commit_at, last_session) if t]
        project.last_activity_at = max(candidates) if candidates else None
        db.add(project)
    db.commit()


def run_scan() -> ScanResult:
    global _last_result
    with _lock, Session(engine) as db:
        projects = _sync_projects(db)
        total, updated, _ = _sync_sessions(db, projects)
        projects = _promote_session_folders(db, projects)
        unmatched = len(db.exec(select(ClaudeSession.id).where(ClaudeSession.project_id == None)).all())  # noqa: E711
        _update_activity(db, projects)
        _last_result = ScanResult(
            projects=len(projects),
            sessions=total,
            sessions_updated=updated,
            unmatched_sessions=unmatched,
            finished_at=datetime.now(UTC),
        )
        log.info("스캔 완료: %s", _last_result)
        return _last_result


def refresh_project(project_id: int) -> None:
    """커밋 직후처럼 한 프로젝트의 git 상태만 다시 읽는다."""
    from .scanner.projects import _read_repo

    with Session(engine) as db:
        project = db.get(Project, project_id)
        if project is None or not Path(project.path).is_dir():
            return
        info = _read_repo(Path(project.path))
        project.branch = info.branch
        project.dirty_files = info.dirty_files
        project.last_commit_at = _as_utc(info.last_commit_at)
        if project.last_commit_at and (project.last_activity_at is None or project.last_commit_at > project.last_activity_at):
            project.last_activity_at = project.last_commit_at
        project.scanned_at = datetime.now(UTC)
        db.add(project)
        db.commit()
