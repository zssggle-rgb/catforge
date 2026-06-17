"""core3 real data comment evidence

Revision ID: 0011_core3_comment_evidence
Revises: 0010_core3_base_claim
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3CommentEvidenceAtom,
    Core3CommentQualityProfile,
    Core3CommentTopicHint,
    Core3CommentUnit,
    Core3CommentUnitEvidenceLink,
)

revision = "0011_core3_comment_evidence"
down_revision = "0010_core3_base_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3CommentUnit.__table__,
        Core3CommentUnitEvidenceLink.__table__,
        Core3CommentEvidenceAtom.__table__,
        Core3CommentTopicHint.__table__,
        Core3CommentQualityProfile.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3CommentTopicHint.__table__,
        Core3CommentEvidenceAtom.__table__,
        Core3CommentUnitEvidenceLink.__table__,
        Core3CommentQualityProfile.__table__,
        Core3CommentUnit.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
