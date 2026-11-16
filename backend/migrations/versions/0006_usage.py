"""provider, usage_record, price_rule 테이블과 Claude 기본 단가 (M4)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Anthropic 공식 단가 (USD / 100만 토큰, 2026-11 기준).
# cache_write 는 5분 캐시 기준 입력 단가의 1.25배 (1시간 캐시는 2배라 실제보다 조금 낮게 잡힐 수 있음).
CLAUDE_PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
    "claude-fable-5-2": (8.00, 40.00, 10.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 0.20),
}
UNITS = ("input_token", "output_token", "cache_write_token", "cache_read_token")


def upgrade() -> None:
    op.create_table(
        "provider",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False, server_default="text"),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "usage_record",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("provider.id"), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("project.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_name", sa.String(), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(), nullable=False, server_default="text"),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True, unique=True),
        sa.Column("meta", JSONB(), nullable=True),
    )
    op.create_index("ix_usage_record_ts", "usage_record", ["ts"])
    op.create_index("ix_usage_record_provider_ts", "usage_record", ["provider_id", "ts"])
    op.create_index("ix_usage_record_project_id", "usage_record", ["project_id"])
    op.create_table(
        "price_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("provider.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("price_per_unit", sa.Float(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
    )
    op.create_index("ix_price_rule_provider", "price_rule", ["provider_id", "unit"])

    now = datetime.now(UTC)
    since = datetime(2020, 1, 1, tzinfo=UTC)
    provider = sa.table(
        "provider",
        sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("display_name", sa.String),
        sa.column("kind", sa.String), sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(provider, [{"id": 1, "name": "claude", "display_name": "Claude", "kind": "text", "created_at": now}])
    op.execute("SELECT setval(pg_get_serial_sequence('provider', 'id'), 1)")
    price = sa.table(
        "price_rule",
        sa.column("provider_id", sa.Integer), sa.column("model", sa.String), sa.column("unit", sa.String),
        sa.column("price_per_unit", sa.Float), sa.column("valid_from", sa.DateTime(timezone=True)), sa.column("note", sa.String),
    )
    rows = []
    for model, prices in CLAUDE_PRICES.items():
        for unit, per_million in zip(UNITS, prices):
            rows.append({
                "provider_id": 1, "model": model, "unit": unit,
                "price_per_unit": per_million / 1_000_000, "valid_from": since, "note": "기본값 (Anthropic 공식 단가)",
            })
    op.bulk_insert(price, rows)


def downgrade() -> None:
    op.drop_table("price_rule")
    op.drop_table("usage_record")
    op.drop_table("provider")
