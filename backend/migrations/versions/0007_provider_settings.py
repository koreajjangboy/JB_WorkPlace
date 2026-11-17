"""provider: 수집 방법, 기본 단위, 코드 감지 패턴, 메모 (설정 화면)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("provider", sa.Column("collection", sa.String(), nullable=False, server_default="app"))
    op.add_column("provider", sa.Column("default_unit", sa.String(), nullable=True))
    op.add_column("provider", sa.Column("detect", sa.String(), nullable=True))
    op.add_column("provider", sa.Column("website", sa.String(), nullable=True))
    op.add_column("provider", sa.Column("notes", sa.String(), nullable=True))
    op.execute(
        "UPDATE provider SET collection = 'claude_logs', default_unit = 'token', "
        "detect = 'anthropic|@anthropic-ai/sdk|ANTHROPIC_API_KEY', website = 'https://www.anthropic.com/pricing' "
        "WHERE name = 'claude'"
    )


def downgrade() -> None:
    for col in ("notes", "website", "detect", "default_unit", "collection"):
        op.drop_column("provider", col)
