"""core3 real data claim comment enhancement

Revision ID: 0013_core3_claim_comment
Revises: 0012_core3_comment_signal
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3ClaimCommentReviewIssue,
    Core3SkuClaimActivation,
    Core3SkuClaimCommentValidation,
)

revision = "0013_core3_claim_comment"
down_revision = "0012_core3_comment_signal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuClaimCommentValidation.__table__,
        Core3SkuClaimActivation.__table__,
        Core3ClaimCommentReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ClaimCommentReviewIssue.__table__,
        Core3SkuClaimActivation.__table__,
        Core3SkuClaimCommentValidation.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
