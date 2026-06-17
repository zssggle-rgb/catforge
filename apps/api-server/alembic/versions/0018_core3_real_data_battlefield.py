"""core3 real data battlefield

Revision ID: 0018_core3_battlefield
Revises: 0017_core3_target_group
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3SkuBattlefieldCandidate,
    Core3SkuBattlefieldEvidenceBreakdown,
    Core3SkuBattlefieldPortfolio,
    Core3SkuBattlefieldReviewIssue,
    Core3SkuBattlefieldScore,
)

revision = "0018_core3_battlefield"
down_revision = "0017_core3_target_group"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuBattlefieldCandidate.__table__,
        Core3SkuBattlefieldScore.__table__,
        Core3SkuBattlefieldEvidenceBreakdown.__table__,
        Core3SkuBattlefieldPortfolio.__table__,
        Core3SkuBattlefieldReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuBattlefieldReviewIssue.__table__,
        Core3SkuBattlefieldPortfolio.__table__,
        Core3SkuBattlefieldEvidenceBreakdown.__table__,
        Core3SkuBattlefieldScore.__table__,
        Core3SkuBattlefieldCandidate.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
