"""core3 real data sku business profile

Revision ID: 0026_core3_sku_business_profile
Revises: 0025_market_profile_legacy_fk
Create Date: 2026-06-14
"""

from alembic import op

from app.models.entities import (
    Core3SkuBusinessProfile,
    Core3SkuBusinessProfileDimension,
    Core3SkuBusinessProfileReviewIssue,
    Core3SkuBusinessProfileSalesAllocation,
)

revision = "0026_core3_sku_business_profile"
down_revision = "0025_market_profile_legacy_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3SkuBusinessProfile.__table__,
        Core3SkuBusinessProfileDimension.__table__,
        Core3SkuBusinessProfileSalesAllocation.__table__,
        Core3SkuBusinessProfileReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3SkuBusinessProfileReviewIssue.__table__,
        Core3SkuBusinessProfileSalesAllocation.__table__,
        Core3SkuBusinessProfileDimension.__table__,
        Core3SkuBusinessProfile.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
