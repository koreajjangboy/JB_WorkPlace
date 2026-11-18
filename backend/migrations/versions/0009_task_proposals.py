"""task: Claude가 제안한 작업(proposals)과 제안한 작업(source_task_id)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("proposals", JSONB(), nullable=True))
    op.add_column("task", sa.Column("source_task_id", sa.Integer(), nullable=True))
    op.create_index("ix_task_source_task_id", "task", ["source_task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_source_task_id", table_name="task")
    op.drop_column("task", "source_task_id")
    op.drop_column("task", "proposals")
