"""widen core3 semantic result ids

Revision ID: 0038_core3_semantic_id_width
Revises: 0037_core3_m09c_user_tasks
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa


revision = "0038_core3_semantic_id_width"
down_revision = "0037_core3_m09c_user_tasks"
branch_labels = None
depends_on = None


ID_COLUMNS = {
    "core3_m09c_sku_user_task_profile": ("profile_id",),
    "core3_m09c_sku_user_task_score": ("score_id",),
    "core3_m09c_user_task_coverage": ("coverage_id",),
    "core3_m10c_sku_target_group_profile": ("profile_id",),
    "core3_m10c_sku_target_group_score": ("score_id",),
    "core3_m10c_target_group_coverage": ("coverage_id",),
    "core3_sku_value_battlefield_profile": ("profile_id",),
    "core3_sku_value_battlefield_score": ("score_id",),
    "core3_value_battlefield_graph_snapshot": ("graph_snapshot_id",),
}


def upgrade() -> None:
    for table_name, column_names in ID_COLUMNS.items():
        for column_name in column_names:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.String(length=36),
                type_=sa.String(length=120),
                existing_nullable=False,
            )


def downgrade() -> None:
    for table_name, column_names in ID_COLUMNS.items():
        for column_name in column_names:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.String(length=120),
                type_=sa.String(length=36),
                existing_nullable=False,
            )
