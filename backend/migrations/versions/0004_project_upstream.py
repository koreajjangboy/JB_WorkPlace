"""project: 원격 브랜치(upstream)와 push 안 된 커밋 수

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project", sa.Column("upstream", sa.String(), nullable=True))
    op.add_column("project", sa.Column("ahead", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("project", sa.Column("behind", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("project", sa.Column("has_remote", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("project", "has_remote")
    op.drop_column("project", "behind")
    op.drop_column("project", "ahead")
    op.drop_column("project", "upstream")
