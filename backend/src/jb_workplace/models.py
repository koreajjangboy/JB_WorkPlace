from datetime import datetime

from sqlalchemy import BigInteger, DateTime
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
