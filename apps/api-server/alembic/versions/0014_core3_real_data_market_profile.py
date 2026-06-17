"""core3 real data market profile

Revision ID: 0014_core3_market_profile
Revises: 0013_core3_claim_comment
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa

from app.models.entities import (
    Core3ComparablePoolBaseline,
    Core3MarketPoolMember,
    Core3MarketSignal,
    Core3SkuMarketProfile,
)

revision = "0014_core3_market_profile"
down_revision = "0013_core3_claim_comment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_sku_market_profile_compat(bind)
    for table in [
        Core3SkuMarketProfile.__table__,
        Core3MarketSignal.__table__,
        Core3ComparablePoolBaseline.__table__,
        Core3MarketPoolMember.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def _ensure_sku_market_profile_compat(bind) -> None:
    """Backfill columns when the old MVP market profile table already exists."""
    inspector = sa.inspect(bind)
    table_name = Core3SkuMarketProfile.__tablename__
    if not inspector.has_table(table_name):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    for column in Core3SkuMarketProfile.__table__.columns:
        if column.name in existing_columns:
            continue
        op.add_column(
            table_name,
            sa.Column(column.name, column.type, nullable=True),
        )
        existing_columns.add(column.name)

    if "sku_market_profile_id" in existing_columns:
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_core3_sku_market_profile_sku_market_profile_id "
                "ON core3_sku_market_profile (sku_market_profile_id)"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3MarketPoolMember.__table__,
        Core3ComparablePoolBaseline.__table__,
        Core3MarketSignal.__table__,
        Core3SkuMarketProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
