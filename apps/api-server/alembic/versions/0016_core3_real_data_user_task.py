"""core3 real data user task

Revision ID: 0016_core3_user_task
Revises: 0015_core3_sku_signal
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3SkuTaskCandidate,
    Core3SkuTaskEvidenceBreakdown,
    Core3SkuTaskReviewIssue,
    Core3SkuTaskScore,
)

revision = "0016_core3_user_task"
down_revision = "0015_core3_sku_signal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuTaskCandidate.__table__,
        Core3SkuTaskScore.__table__,
        Core3SkuTaskEvidenceBreakdown.__table__,
        Core3SkuTaskReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuTaskReviewIssue.__table__,
        Core3SkuTaskEvidenceBreakdown.__table__,
        Core3SkuTaskScore.__table__,
        Core3SkuTaskCandidate.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
