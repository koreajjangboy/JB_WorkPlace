"""project, claude_session 테이블 생성 (M1)

Revision ID: 0001
Revises:
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False, unique=True),
        sa.Column("branch", sa.String(), nullable=True),
        sa.Column("dirty_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_commit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exists", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_name", "project", ["name"])
    op.create_index("ix_project_last_activity_at", "project", ["last_activity_at"])

    op.create_table(
        "claude_session",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id"), nullable=True),
        sa.Column("file_path", sa.String(), nullable=False, unique=True),
        sa.Column("file_mtime", sa.Float(), nullable=False),
        sa.Column("cwd", sa.String(), nullable=True),
        sa.Column("git_branch", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("first_prompt", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assistant_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("models", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_creation_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=True),
    )
    op.create_index("ix_claude_session_project_id", "claude_session", ["project_id"])
    op.create_index("ix_claude_session_ended_at", "claude_session", ["ended_at"])


def downgrade() -> None:
    op.drop_table("claude_session")
    op.drop_table("project")
