"""작업별 실행 한도, 실행 중단 사유, Claude 사용 한도(5시간·7일) 기록

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("max_budget_usd", sa.Float(), nullable=True))
    op.add_column("task", sa.Column("max_minutes", sa.Integer(), nullable=True))
    op.add_column("run", sa.Column("stop_reason", sa.String(), nullable=True))
    op.add_column("run", sa.Column("max_budget_usd", sa.Float(), nullable=True))
    op.add_column("run", sa.Column("max_minutes", sa.Integer(), nullable=True))
    op.create_table(
        "rate_limit_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("run.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("five_hour_utilization", sa.Float(), nullable=True),
        sa.Column("five_hour_resets_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seven_day_utilization", sa.Float(), nullable=True),
        sa.Column("seven_day_resets_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overage_status", sa.String(), nullable=True),
    )
    op.create_index("ix_rate_limit_snapshot_ts", "rate_limit_snapshot", ["ts"])


def downgrade() -> None:
    op.drop_table("rate_limit_snapshot")
    op.drop_column("run", "max_minutes")
    op.drop_column("run", "max_budget_usd")
    op.drop_column("run", "stop_reason")
    op.drop_column("task", "max_minutes")
    op.drop_column("task", "max_budget_usd")
