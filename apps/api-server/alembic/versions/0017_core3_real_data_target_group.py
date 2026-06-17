"""core3 real data target group

Revision ID: 0017_core3_target_group
Revises: 0016_core3_user_task
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3SkuTargetGroupCandidate,
    Core3SkuTargetGroupEvidenceBreakdown,
    Core3SkuTargetGroupReviewIssue,
    Core3SkuTargetGroupScore,
)

revision = "0017_core3_target_group"
down_revision = "0016_core3_user_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuTargetGroupCandidate.__table__,
        Core3SkuTargetGroupScore.__table__,
        Core3SkuTargetGroupEvidenceBreakdown.__table__,
        Core3SkuTargetGroupReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuTargetGroupReviewIssue.__table__,
        Core3SkuTargetGroupEvidenceBreakdown.__table__,
        Core3SkuTargetGroupScore.__table__,
        Core3SkuTargetGroupCandidate.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
