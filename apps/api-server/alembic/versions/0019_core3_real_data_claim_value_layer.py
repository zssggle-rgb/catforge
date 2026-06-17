"""core3 real data claim value layer

Revision ID: 0019_core3_claim_value
Revises: 0018_core3_battlefield
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3SkuBattlefieldClaimCandidate,
    Core3SkuBattlefieldClaimValueSummary,
    Core3SkuClaimValueEvidenceBreakdown,
    Core3SkuClaimValueLayer,
    Core3SkuClaimValueReviewIssue,
)

revision = "0019_core3_claim_value"
down_revision = "0018_core3_battlefield"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3SkuBattlefieldClaimCandidate.__table__,
        Core3SkuClaimValueLayer.__table__,
        Core3SkuClaimValueEvidenceBreakdown.__table__,
        Core3SkuBattlefieldClaimValueSummary.__table__,
        Core3SkuClaimValueReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3SkuClaimValueReviewIssue.__table__,
        Core3SkuBattlefieldClaimValueSummary.__table__,
        Core3SkuClaimValueEvidenceBreakdown.__table__,
        Core3SkuClaimValueLayer.__table__,
        Core3SkuBattlefieldClaimCandidate.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
