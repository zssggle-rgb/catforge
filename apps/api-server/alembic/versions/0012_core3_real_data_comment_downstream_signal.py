"""core3 real data comment downstream signal

Revision ID: 0012_core3_comment_signal
Revises: 0011_core3_comment_evidence
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3CommentDownstreamSignal,
    Core3CommentSignalCandidate,
    Core3SkuCommentSignalProfile,
)

revision = "0012_core3_comment_signal"
down_revision = "0011_core3_comment_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3CommentSignalCandidate.__table__,
        Core3CommentDownstreamSignal.__table__,
        Core3SkuCommentSignalProfile.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuCommentSignalProfile.__table__,
        Core3CommentDownstreamSignal.__table__,
        Core3CommentSignalCandidate.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
