"""core3 real data M10C target group profiles

Revision ID: 0036_core3_m10c_target_groups
Revises: 0035_core3_m11c_value_battlefields
Create Date: 2026-06-21
"""

from alembic import op

from app.models.entities import (
    Core3M10cSkuTargetGroupProfile,
    Core3M10cSkuTargetGroupScore,
    Core3M10cTargetGroupCoverage,
)


revision = "0036_core3_m10c_target_groups"
down_revision = "0035_core3_m11c_value_battlefields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3M10cSkuTargetGroupProfile.__table__,
        Core3M10cSkuTargetGroupScore.__table__,
        Core3M10cTargetGroupCoverage.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3M10cTargetGroupCoverage.__table__,
        Core3M10cSkuTargetGroupScore.__table__,
        Core3M10cSkuTargetGroupProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
