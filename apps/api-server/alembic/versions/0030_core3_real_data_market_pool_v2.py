"""core3 real data market pool v2 fields

Revision ID: 0030_core3_market_pool_v2
Revises: 0029_core3_native_dim
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_core3_market_pool_v2"
down_revision = "0029_core3_native_dim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "core3_sku_market_profile"
    if not inspector.has_table(table_name):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    columns = [
        sa.Column("screen_size_class", sa.String(length=60), nullable=True),
        sa.Column("market_pool_key", sa.String(length=220), nullable=True),
        sa.Column("same_pool_price_percentile", sa.Numeric(8, 6), nullable=True),
        sa.Column("same_pool_volume_percentile", sa.Numeric(8, 6), nullable=True),
        sa.Column("same_pool_amount_percentile", sa.Numeric(8, 6), nullable=True),
        sa.Column("price_per_inch_percentile", sa.Numeric(8, 6), nullable=True),
        sa.Column("same_pool_sku_count", sa.Integer(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing_columns:
            op.add_column(table_name, column)
            existing_columns.add(column.name)

    bind.execute(sa.text("UPDATE core3_sku_market_profile SET screen_size_class = 'unknown' WHERE screen_size_class IS NULL"))
    bind.execute(sa.text("UPDATE core3_sku_market_profile SET same_pool_sku_count = 0 WHERE same_pool_sku_count IS NULL"))
    _create_index(bind, "ix_core3_m07_profile_screen_size_class", table_name, "screen_size_class")
    _create_index(bind, "ix_core3_m07_profile_market_pool_key", table_name, "market_pool_key")


def downgrade() -> None:
    # Keep downgrade conservative because these columns may be consumed by persisted v2 runs.
    pass


def _create_index(bind, index_name: str, table_name: str, column_name: str) -> None:
    bind.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table_name} ({column_name})"
        )
    )
