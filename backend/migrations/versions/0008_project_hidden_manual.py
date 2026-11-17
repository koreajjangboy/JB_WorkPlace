"""project: 목록에서 제외(hidden), 직접 추가(manual)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project", sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("project", sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("project", "manual")
    op.drop_column("project", "hidden")
