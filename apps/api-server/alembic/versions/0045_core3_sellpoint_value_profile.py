"""core3 sellpoint value decision profile persistence

Revision ID: 0045_core3_sellpoint_value_profile
Revises: 0044_core3_m12d_reason_pressure
Create Date: 2026-07-13
"""

from alembic import op

from app.models.entities import (
    Core3SellpointValueProfileVersion,
    Core3SkuSellpointValueCandidate,
    Core3SkuSellpointValueItem,
    Core3SkuSellpointValueProfile,
)


revision = "0045_core3_sellpoint_value_profile"
down_revision = "0044_core3_m12d_reason_pressure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in (
        Core3SellpointValueProfileVersion.__table__,
        Core3SkuSellpointValueProfile.__table__,
        Core3SkuSellpointValueCandidate.__table__,
        Core3SkuSellpointValueItem.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        Core3SkuSellpointValueItem.__table__,
        Core3SkuSellpointValueCandidate.__table__,
        Core3SkuSellpointValueProfile.__table__,
        Core3SellpointValueProfileVersion.__table__,
    ):
        table.drop(bind=bind, checkfirst=True)
