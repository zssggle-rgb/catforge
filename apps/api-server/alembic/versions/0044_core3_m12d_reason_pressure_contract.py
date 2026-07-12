"""core3 M12D reason establishment and pressure contract

Revision ID: 0044_core3_m12d_reason_pressure
Revises: 0043_core3_m12d_quality
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0044_core3_m12d_reason_pressure"
down_revision = "0043_core3_m12d_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    profile_table = "core3_sku_purchase_reason_profile"
    if inspector.has_table(profile_table):
        profile_columns = {column["name"] for column in inspector.get_columns(profile_table)}
        _add_column_if_missing(
            profile_table,
            profile_columns,
            sa.Column("established_anchors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
        _add_column_if_missing(
            profile_table,
            profile_columns,
            sa.Column("proposition_anchors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
        _add_column_if_missing(
            profile_table,
            profile_columns,
            sa.Column("pressure_summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )
        _add_column_if_missing(
            profile_table,
            profile_columns,
            sa.Column("comparison_limitations_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_core3_m12d_profile_established_gin "
                "ON core3_sku_purchase_reason_profile "
                "USING gin ((established_anchors_json::jsonb))"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_core3_m12d_profile_proposition_gin "
                "ON core3_sku_purchase_reason_profile "
                "USING gin ((proposition_anchors_json::jsonb))"
            )
        )

    anchor_table = "core3_sku_purchase_reason_anchor"
    if inspector.has_table(anchor_table):
        anchor_columns = {column["name"] for column in inspector.get_columns(anchor_table)}
        for column in (
            sa.Column("establishment_status", sa.String(length=60), nullable=False, server_default="unassessed"),
            sa.Column("establishment_score", sa.Numeric(8, 4), nullable=True),
            sa.Column("establishment_domains_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("user_validation_status", sa.String(length=60), nullable=False, server_default="unassessed"),
            sa.Column("core_eligible", sa.Boolean(), nullable=True),
            sa.Column("core_ineligible_reasons_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("proposition_evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("user_support_evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("pressure_level", sa.String(length=60), nullable=False, server_default="unassessed"),
            sa.Column("pressure_tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("pressure_summary_cn", sa.Text(), nullable=False, server_default=""),
            sa.Column("comparison_limitations_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        ):
            _add_column_if_missing(anchor_table, anchor_columns, column)

        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_core3_m12d_anchor_establishment "
                "ON core3_sku_purchase_reason_anchor "
                "(project_id, category_code, establishment_status, core_eligible)"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_core3_m12d_anchor_pressure "
                "ON core3_sku_purchase_reason_anchor (project_id, category_code, pressure_level)"
            )
        )


def downgrade() -> None:
    # Published historical profiles may already depend on unassessed compatibility values.
    pass


def _add_column_if_missing(table_name: str, existing: set[str], column: sa.Column) -> None:
    if column.name in existing:
        return
    op.add_column(table_name, column)
    existing.add(str(column.name))
