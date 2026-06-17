"""core3 real data sku signal profile

Revision ID: 0015_core3_sku_signal
Revises: 0014_core3_market_profile
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3SkuDownstreamFeatureView,
    Core3SkuSignalEvidenceMatrix,
    Core3SkuSignalProfile,
)

revision = "0015_core3_sku_signal"
down_revision = "0014_core3_market_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuSignalProfile.__table__,
        Core3SkuSignalEvidenceMatrix.__table__,
        Core3SkuDownstreamFeatureView.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuDownstreamFeatureView.__table__,
        Core3SkuSignalEvidenceMatrix.__table__,
        Core3SkuSignalProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
