"""core3 M12D quality contract fields

Revision ID: 0043_core3_m12d_quality
Revises: 0042_core3_m12d_purchase_reason
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0043_core3_m12d_quality"
down_revision = "0042_core3_m12d_purchase_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    version_table = "core3_purchase_reason_profile_version"
    if inspector.has_table(version_table):
        columns = {column["name"] for column in inspector.get_columns(version_table)}
        if "release_quality_status" not in columns:
            op.add_column(
                version_table,
                sa.Column(
                    "release_quality_status",
                    sa.String(length=40),
                    nullable=False,
                    server_default="unassessed",
                ),
            )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_core3_m12d_version_release_quality "
                "ON core3_purchase_reason_profile_version (release_quality_status)"
            )
        )

    profile_table = "core3_sku_purchase_reason_profile"
    if inspector.has_table(profile_table):
        columns = {column["name"] for column in inspector.get_columns(profile_table)}
        if "input_quality_json" not in columns:
            op.add_column(
                profile_table,
                sa.Column("input_quality_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            )


def downgrade() -> None:
    # Keep downgrade conservative because published profile contracts may use these fields.
    pass
