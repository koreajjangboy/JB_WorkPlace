from datetime import datetime

from typing import Any

from sqlalchemy import BigInteger, Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _ts(**kwargs) -> datetime | None:
    """시간대 정보가 있는 timestamp 컬럼 (PostgreSQL timestamptz)."""
    return Field(sa_type=DateTime(timezone=True), **kwargs)


class Project(SQLModel, table=True):
    """C:\\dev 같은 스캔 폴더 아래에서 찾은 git 저장소."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    path: str = Field(unique=True)
    branch: str | None = None
    dirty_files: int = 0
    last_commit_at: datetime | None = _ts(default=None)
    last_activity_at: datetime | None = _ts(default=None, index=True)  # 마지막 커밋과 마지막 세션 중 늦은 시각
    exists: bool = True  # 다음 스캔에서 사라졌으면 False
    upstream: str | None = None  # 연결된 원격 브랜치 (예: origin/main)
    ahead: int = 0  # push 안 된 커밋 수
    behind: int = 0  # 원격에만 있는 커밋 수 (마지막 fetch 기준)
    has_remote: bool = False
    scanned_at: datetime = _ts()


class ClaudeSession(SQLModel, table=True):
    """Claude Code 세션 기록(JSONL)의 요약 색인. 대화 내용 자체는 파일에서 바로 읽는다."""

    __tablename__ = "claude_session"

    id: str = Field(primary_key=True)  # sessionId
    project_id: int | None = Field(default=None, foreign_key="project.id", index=True)
    file_path: str = Field(unique=True)
    file_mtime: float
    cwd: str | None = None
    git_branch: str | None = None
    title: str | None = None
    first_prompt: str | None = None
    started_at: datetime | None = _ts(default=None)
    ended_at: datetime | None = _ts(default=None, index=True)
    user_messages: int = 0
    assistant_messages: int = 0
    models: str | None = None  # 쉼표로 구분
    input_tokens: int = Field(default=0, sa_type=BigInteger)
    output_tokens: int = Field(default=0, sa_type=BigInteger)
    cache_creation_tokens: int = Field(default=0, sa_type=BigInteger)
    cache_read_tokens: int = Field(default=0, sa_type=BigInteger)
    cost_usd: float | None = None  # 기록에 비용 정보가 있을 때만


class Task(SQLModel, table=True):
    """사람이 내린 작업 하나. 실행(Run)이 여러 번 붙을 수 있다."""

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    title: str
    prompt: str
    status: str = Field(default="todo", index=True)  # todo | running | review | done | failed
    session_id: str | None = None  # 다시 지시할 때 이어 갈 Claude 세션
    created_at: datetime = _ts()
    updated_at: datetime = _ts(index=True)
    # 첫 실행 직전의 저장 안 된 변경 {경로: {"status", "hash"}}. 이 작업이 바꾼 파일을 가려내는 기준.
    baseline: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    commit_message: str | None = None  # Claude가 제안한 커밋 메시지 (사람이 고칠 수 있음)
    commit_sha: str | None = None
    committed_at: datetime | None = _ts(default=None)
    # 이 작업의 실행 한도. 비어 있으면 .env 의 기본값(RUNNER_MAX_BUDGET_USD / RUNNER_MAX_MINUTES)
    max_budget_usd: float | None = None
    max_minutes: int | None = None


class Run(SQLModel, table=True):
    """Claude Code 실행 1회."""

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    prompt: str
    status: str = Field(default="running", index=True)  # running | succeeded | failed | stopped
    session_id: str | None = None
    resumed_from: str | None = None  # --resume 로 이어 간 세션
    pid: int | None = None
    started_at: datetime = _ts()
    ended_at: datetime | None = _ts(default=None)
    exit_code: int | None = None
    error: str | None = None
    stop_reason: str | None = None  # budget | timeout | stopped | error | restart (성공이면 None)
    max_budget_usd: float | None = None  # 이 실행에 적용한 한도
    max_minutes: int | None = None
    model: str | None = None
    num_turns: int | None = None
    input_tokens: int = Field(default=0, sa_type=BigInteger)
    output_tokens: int = Field(default=0, sa_type=BigInteger)
    cache_creation_tokens: int = Field(default=0, sa_type=BigInteger)
    cache_read_tokens: int = Field(default=0, sa_type=BigInteger)
    cost_usd: float | None = None


class RunEvent(SQLModel, table=True):
    """실행 중 일어난 일 한 건 (메시지, 도구 호출, 도구 결과, 오류 등)."""

    __tablename__ = "run_event"

    id: int | None = Field(default=None, primary_key=True, sa_type=BigInteger)
    run_id: int = Field(foreign_key="run.id", index=True)
    seq: int
    ts: datetime = _ts()
    kind: str  # init | text | tool_use | tool_result | result | error | stderr
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))


class RateLimitSnapshot(SQLModel, table=True):
    """Claude Code가 실행 중에 알려주는 구독 사용 한도 사용률 (0~1)."""

    __tablename__ = "rate_limit_snapshot"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = _ts(index=True)
    run_id: int | None = Field(default=None, foreign_key="run.id")
    status: str | None = None
    five_hour_utilization: float | None = None
    five_hour_resets_at: datetime | None = _ts(default=None)
    seven_day_utilization: float | None = None
    seven_day_resets_at: datetime | None = _ts(default=None)
    overage_status: str | None = None
