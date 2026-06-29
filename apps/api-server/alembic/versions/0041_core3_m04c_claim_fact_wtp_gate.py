"""core3 M04C claim fact WTP gate fields

Revision ID: 0041_core3_m04c_wtp_gate
Revises: 0040_core3_m12c_claim_value
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0041_core3_m04c_wtp_gate"
down_revision = "0040_core3_m12c_claim_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "core3_sku_claim_fact"
    if not inspector.has_table(table_name):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    columns = [
        sa.Column("param_support_level", sa.String(length=80), nullable=False, server_default="unknown"),
        sa.Column("param_support_specificity", sa.String(length=80), nullable=False, server_default="unknown"),
        sa.Column("primary_supporting_param_codes", sa.JSON(), nullable=True),
        sa.Column("generic_support_param_codes", sa.JSON(), nullable=True),
        sa.Column("source_claim_group_id", sa.String(length=160), nullable=True),
        sa.Column("same_source_param_group_id", sa.String(length=160), nullable=True),
        sa.Column("canonical_claim_code", sa.String(length=160), nullable=True),
        sa.Column("canonical_claim_name", sa.String(length=240), nullable=True),
        sa.Column("wtp_input_guard", sa.String(length=80), nullable=False, server_default="unknown"),
    ]
    for column in columns:
        if column.name not in existing_columns:
            op.add_column(table_name, column)
            existing_columns.add(column.name)

    bind.execute(sa.text("UPDATE core3_sku_claim_fact SET primary_supporting_param_codes = '[]' WHERE primary_supporting_param_codes IS NULL"))
    bind.execute(sa.text("UPDATE core3_sku_claim_fact SET generic_support_param_codes = '[]' WHERE generic_support_param_codes IS NULL"))
    bind.execute(sa.text("UPDATE core3_sku_claim_fact SET canonical_claim_code = claim_code WHERE canonical_claim_code IS NULL"))
    bind.execute(sa.text("UPDATE core3_sku_claim_fact SET canonical_claim_name = claim_name WHERE canonical_claim_name IS NULL"))
    _create_index(bind, "ix_core3_sku_claim_fact_support_level", table_name, "param_support_level")
    _create_index(bind, "ix_core3_sku_claim_fact_wtp_guard", table_name, "wtp_input_guard")
    _create_index(bind, "ix_core3_sku_claim_fact_canonical", table_name, "canonical_claim_code")
    _create_index(bind, "ix_core3_sku_claim_fact_source_group", table_name, "source_claim_group_id")
    _create_index(bind, "ix_core3_sku_claim_fact_param_group", table_name, "same_source_param_group_id")


def downgrade() -> None:
    # Keep downgrade conservative; persisted M12C runs can reference these fields.
    pass


def _create_index(bind: sa.Connection, index_name: str, table_name: str, column_name: str) -> None:
    bind.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"))
