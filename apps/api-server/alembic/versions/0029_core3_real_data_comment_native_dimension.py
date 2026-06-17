"""core3 real data comment native dimension discovery

Revision ID: 0029_core3_native_dim
Revises: 0028_core3_dimension_ontology
Create Date: 2026-06-15
"""

from alembic import op

from app.models.entities import (
    Core3CommentNativeSignal,
    Core3NativeDimensionAlignmentProposal,
    Core3NativeDimensionCandidate,
    Core3NativeDimensionReviewIssue,
    Core3NativeDimensionSkuSupport,
)

revision = "0029_core3_native_dim"
down_revision = "0028_core3_dimension_ontology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3CommentNativeSignal.__table__,
        Core3NativeDimensionCandidate.__table__,
        Core3NativeDimensionSkuSupport.__table__,
        Core3NativeDimensionAlignmentProposal.__table__,
        Core3NativeDimensionReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3NativeDimensionReviewIssue.__table__,
        Core3NativeDimensionAlignmentProposal.__table__,
        Core3NativeDimensionSkuSupport.__table__,
        Core3NativeDimensionCandidate.__table__,
        Core3CommentNativeSignal.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
