"""core3 claim value quantification

Revision ID: 0040_core3_m12c_claim_value
Revises: 0039_core3_semantic_market
Create Date: 2026-06-24
"""

from alembic import op

from app.models.entities import (
    Core3ClaimValueContextPool,
    Core3ClaimValueDimensionSummary,
    Core3ClaimValuePoolMetric,
    Core3ClaimValueReviewIssue,
    Core3SkuClaimContributionAttribution,
    Core3SkuClaimValueQuantification,
)


revision = "0040_core3_m12c_claim_value"
down_revision = "0039_core3_semantic_market"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ClaimValueContextPool.__table__,
        Core3ClaimValuePoolMetric.__table__,
        Core3SkuClaimValueQuantification.__table__,
        Core3SkuClaimContributionAttribution.__table__,
        Core3ClaimValueDimensionSummary.__table__,
        Core3ClaimValueReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ClaimValueReviewIssue.__table__,
        Core3ClaimValueDimensionSummary.__table__,
        Core3SkuClaimContributionAttribution.__table__,
        Core3SkuClaimValueQuantification.__table__,
        Core3ClaimValuePoolMetric.__table__,
        Core3ClaimValueContextPool.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
