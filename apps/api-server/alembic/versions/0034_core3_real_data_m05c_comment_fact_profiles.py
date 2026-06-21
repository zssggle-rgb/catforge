"""core3 real data M05C comment fact profiles

Revision ID: 0034_core3_m05c_comment_profiles
Revises: 0033_core3_m04c_claim_profiles
Create Date: 2026-06-21
"""

from alembic import op

from app.models.entities import (
    Core3CommentFactAtom,
    Core3CommentFactCoverage,
    Core3CommentFactReviewIssue,
    Core3SkuCommentFactProfile,
)


revision = "0034_core3_m05c_comment_profiles"
down_revision = "0033_core3_m04c_claim_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3CommentFactAtom.__table__,
        Core3SkuCommentFactProfile.__table__,
        Core3CommentFactCoverage.__table__,
        Core3CommentFactReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3CommentFactReviewIssue.__table__,
        Core3CommentFactCoverage.__table__,
        Core3SkuCommentFactProfile.__table__,
        Core3CommentFactAtom.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
