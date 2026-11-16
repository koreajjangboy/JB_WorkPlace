"""task: 변경 추적 기준(baseline)과 커밋 정보 (M3 일부)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("baseline", JSONB(), nullable=True))
    op.add_column("task", sa.Column("commit_message", sa.String(), nullable=True))
    op.add_column("task", sa.Column("commit_sha", sa.String(), nullable=True))
    op.add_column("task", sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("task", "committed_at")
    op.drop_column("task", "commit_sha")
    op.drop_column("task", "commit_message")
    op.drop_column("task", "baseline")
