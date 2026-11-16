import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from .config import get_settings
from .db import engine, get_session
from .models import Project, Run, RunEvent, Task
from .gitops import GitError, as_dict, commit, file_diff, task_changes
from .runner import RunnerError, make_title, running_count, start_run, stop_run

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- 스키마


class RunOut(BaseModel):
    id: int
    task_id: int
    prompt: str
    status: str
    session_id: str | None
    resumed_from: str | None
    started_at: datetime
    ended_at: datetime | None
    exit_code: int | None
    error: str | None
    model: str | None
    num_turns: int | None
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost_usd: float | None


class TaskOut(BaseModel):
    id: int
    project_id: int
    project_name: str | None
    title: str
    prompt: str
    status: str
    session_id: str | None
    created_at: datetime
    updated_at: datetime
    run_count: int
    total_cost_usd: float | None
    last_run: RunOut | None
    commit_message: str | None
    commit_sha: str | None
    committed_at: datetime | None


class TaskDetail(TaskOut):
    project_path: str | None
    project_dirty_files: int
    runs: list[RunOut]


class TaskCreate(BaseModel):
    project_id: int
    prompt: str = Field(min_length=1, max_length=20000)
    title: str | None = Field(default=None, max_length=200)
    run_now: bool = False


class RunCreate(BaseModel):
    prompt: str | None = Field(default=None, max_length=20000)


class EventOut(BaseModel):
    seq: int
    ts: datetime
    kind: str
    payload: dict[str, Any]


class RunnerStatus(BaseModel):
    claude_found: bool
    claude_path: str | None
    running: int
    max_concurrent: int
    max_minutes: int
    max_budget_usd: float
    model: str | None
    allowed_tools: list[str]
    disallowed_tools: list[str]


# ---------------------------------------------------------------- 도우미


def _run_out(r: Run) -> RunOut:
    return RunOut(**r.model_dump(include=set(RunOut.model_fields)))


def _task_outs(db: Session, tasks: list[Task]) -> list[TaskOut]:
    if not tasks:
        return []
    ids = [t.id for t in tasks]
    runs: dict[int, list[Run]] = {}
    for r in db.exec(select(Run).where(Run.task_id.in_(ids)).order_by(Run.id)).all():
        runs.setdefault(r.task_id, []).append(r)
    names = {p.id: p.name for p in db.exec(select(Project).where(Project.id.in_({t.project_id for t in tasks}))).all()}
    out = []
    for t in tasks:
        task_runs = runs.get(t.id, [])
        costs = [r.cost_usd for r in task_runs if r.cost_usd is not None]
        out.append(TaskOut(
            **t.model_dump(include=set(TaskOut.model_fields)),
            project_name=names.get(t.project_id),
            run_count=len(task_runs),
            total_cost_usd=sum(costs) if costs else None,
            last_run=_run_out(task_runs[-1]) if task_runs else None,
        ))
    return out


def _get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다")
    return task


def _start(task_id: int, prompt: str | None) -> RunOut:
    try:
        return _run_out(start_run(task_id, prompt))
    except RunnerError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


# ---------------------------------------------------------------- 엔드포인트


@router.get("/runner", response_model=RunnerStatus)
def runner_status(db: Session = Depends(get_session)) -> RunnerStatus:
    s = get_settings()
    exe = s.resolved_claude_exe
    return RunnerStatus(
        claude_found=exe is not None,
        claude_path=exe,
        running=running_count(db),
        max_concurrent=s.runner_max_concurrent,
        max_minutes=s.runner_max_minutes,
        max_budget_usd=s.runner_max_budget_usd,
        model=s.runner_model or None,
        allowed_tools=_split(s.runner_allowed_tools),
        disallowed_tools=_split(s.runner_disallowed_tools),
    )


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: int | None = None,
    status: str | None = None,
    limit: int = Query(200, le=500),
    db: Session = Depends(get_session),
) -> list[TaskOut]:
    query = select(Task)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status.in_(_split(status)))
    tasks = db.exec(query.order_by(Task.updated_at.desc()).limit(limit)).all()
    return _task_outs(db, list(tasks))


@router.get("/tasks/counts")
def task_counts(db: Session = Depends(get_session)) -> dict[str, int]:
    rows = db.exec(select(Task.status, func.count()).group_by(Task.status)).all()
    return {status: count for status, count in rows}


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_session)) -> TaskOut:
    project = db.get(Project, body.project_id)
    if project is None or not project.exists:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    now = datetime.now(UTC)
    prompt = body.prompt.strip()
    task = Task(
        project_id=project.id,
        title=(body.title or "").strip() or make_title(prompt),
        prompt=prompt,
        status="todo",
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if body.run_now:
        try:
            start_run(task.id)
        except RunnerError as exc:
            # 작업은 만들어졌으니 할 일로 남기고, 실행 실패 이유만 알린다.
            raise HTTPException(exc.status_code, f"작업은 등록했지만 실행하지 못했습니다: {exc}") from exc
        db.refresh(task)
    return _task_outs(db, [task])[0]


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: int, db: Session = Depends(get_session)) -> TaskDetail:
    task = _get_task(db, task_id)
    base = _task_outs(db, [task])[0]
    project = db.get(Project, task.project_id)
    runs = db.exec(select(Run).where(Run.task_id == task.id).order_by(Run.id)).all()
    return TaskDetail(
        **base.model_dump(),
        project_path=project.path if project else None,
        project_dirty_files=project.dirty_files if project else 0,
        runs=[_run_out(r) for r in runs],
    )


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_session)) -> None:
    task = _get_task(db, task_id)
    if task.status == "running":
        raise HTTPException(409, "실행 중인 작업은 지울 수 없습니다. 먼저 중단하세요.")
    run_ids = [r.id for r in db.exec(select(Run).where(Run.task_id == task.id)).all()]
    if run_ids:
        for ev in db.exec(select(RunEvent).where(RunEvent.run_id.in_(run_ids))).all():
            db.delete(ev)
        for r in db.exec(select(Run).where(Run.id.in_(run_ids))).all():
            db.delete(r)
    db.delete(task)
    db.commit()


@router.post("/tasks/{task_id}/runs", response_model=RunOut, status_code=201)
def create_run(task_id: int, body: RunCreate) -> RunOut:
    return _start(task_id, body.prompt)


@router.post("/runs/{run_id}/stop")
def stop(run_id: int, db: Session = Depends(get_session)) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "실행을 찾을 수 없습니다")
    if run.status != "running":
        raise HTTPException(409, "이미 끝난 실행입니다")
    if not stop_run(run_id):
        raise HTTPException(409, "실행 중인 프로세스를 찾지 못했습니다")
    return {"ok": True}


def _events_after(run_id: int, after: int, limit: int = 500) -> list[EventOut]:
    with Session(engine) as db:
        rows = db.exec(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after).order_by(RunEvent.seq).limit(limit)
        ).all()
        return [EventOut(seq=r.seq, ts=r.ts, kind=r.kind, payload=r.payload) for r in rows]


def _run_snapshot(run_id: int) -> RunOut | None:
    with Session(engine) as db:
        run = db.get(Run, run_id)
        return _run_out(run) if run else None


@router.get("/runs/{run_id}/events", response_model=list[EventOut])
def run_events(run_id: int, after: int = -1) -> list[EventOut]:
    return _events_after(run_id, after, limit=5000)


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: int, request: Request, after: int = -1) -> StreamingResponse:
    """실행 기록을 SSE로 보낸다. 처음엔 after 이후 기록을 모두 보내고, 실행이 끝날 때까지 새 기록을 이어 보낸다."""
    if await run_in_threadpool(_run_snapshot, run_id) is None:
        raise HTTPException(404, "실행을 찾을 수 없습니다")

    async def gen():
        last = after
        last_status = None
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            events = await run_in_threadpool(_events_after, run_id, last)
            for ev in events:
                last = ev.seq
                yield f"id: {ev.seq}\nevent: event\ndata: {ev.model_dump_json()}\n\n"
            run = await run_in_threadpool(_run_snapshot, run_id)
            if run and run.status != last_status:
                last_status = run.status
                yield f"event: run\ndata: {run.model_dump_json()}\n\n"
            if run and run.status != "running" and not events:
                yield "event: end\ndata: {}\n\n"
                return
            idle = 0 if events else idle + 1
            if idle and idle % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- 검토: 변경 파일, diff, 커밋


class FileChangeOut(BaseModel):
    path: str
    status: str
    kind: str
    pre_existing: bool
    additions: int | None
    deletions: int | None
    binary: bool = False
    size_bytes: int | None = None


class ChangesOut(BaseModel):
    tracked: bool  # 첫 실행 전 상태를 기록해 둔 작업인지 (아니면 어떤 파일을 Claude가 바꿨는지 모름)
    files: list[FileChangeOut]
    commit_message: str | None
    commit_sha: str | None
    committed_at: datetime | None


class CommitIn(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    files: list[str] = Field(min_length=1, max_length=2000)


def _project_repo(db: Session, task: Task) -> str:
    project = db.get(Project, task.project_id)
    if project is None or not project.exists:
        raise HTTPException(409, "프로젝트 폴더가 없습니다")
    return project.path


def _changes(db: Session, task: Task) -> list:
    try:
        return task_changes(_project_repo(db, task), task.baseline)
    except GitError as exc:
        raise HTTPException(409, f"변경 사항을 읽지 못했습니다: {exc}") from exc


@router.get("/tasks/{task_id}/changes", response_model=ChangesOut)
def get_changes(task_id: int, db: Session = Depends(get_session)) -> ChangesOut:
    task = _get_task(db, task_id)
    files = _changes(db, task)
    return ChangesOut(
        tracked=task.baseline is not None,
        files=[FileChangeOut(**as_dict(f)) for f in files],
        commit_message=task.commit_message,
        commit_sha=task.commit_sha,
        committed_at=task.committed_at,
    )


@router.get("/tasks/{task_id}/diff")
def get_diff(task_id: int, path: str, db: Session = Depends(get_session)) -> dict:
    task = _get_task(db, task_id)
    match = next((f for f in _changes(db, task) if f.path == path), None)
    if match is None:
        raise HTTPException(404, "이 작업의 변경 파일이 아닙니다")
    return {"path": path, "diff": file_diff(_project_repo(db, task), path, match.status)}


@router.post("/tasks/{task_id}/commit", response_model=TaskOut)
def commit_task(task_id: int, body: CommitIn, db: Session = Depends(get_session)) -> TaskOut:
    task = _get_task(db, task_id)
    if task.status == "running":
        raise HTTPException(409, "실행 중에는 커밋할 수 없습니다")
    allowed = {f.path for f in _changes(db, task)}
    unknown = [p for p in body.files if p not in allowed]
    if unknown:
        raise HTTPException(400, f"이 작업의 변경 파일이 아닌 항목이 있습니다: {', '.join(unknown[:5])}")
    try:
        sha = commit(_project_repo(db, task), body.files, body.message)
    except GitError as exc:
        raise HTTPException(409, f"커밋하지 못했습니다: {exc}") from exc
    now = datetime.now(UTC)
    task.commit_message = body.message.strip()
    task.commit_sha = sha
    task.committed_at = now
    task.status = "done"
    task.updated_at = now
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_outs(db, [task])[0]


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(task_id: int, db: Session = Depends(get_session)) -> TaskOut:
    """커밋하지 않고 완료로 표시한다 (직접 커밋했거나, 바꾼 파일이 없는 작업)."""
    task = _get_task(db, task_id)
    if task.status == "running":
        raise HTTPException(409, "실행 중인 작업입니다")
    task.status = "done"
    task.updated_at = datetime.now(UTC)
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_outs(db, [task])[0]
