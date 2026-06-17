"""core3 real data candidate recall

Revision ID: 0020_core3_candidate_recall
Revises: 0019_core3_claim_value
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3CandidateFeatureSnapshot,
    Core3CandidatePool,
    Core3CandidateRecallReason,
    Core3CandidateRecallReviewIssue,
    Core3CandidateRecallRun,
)

revision = "0020_core3_candidate_recall"
down_revision = "0019_core3_claim_value"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3CandidateRecallRun.__table__,
        Core3CandidatePool.__table__,
        Core3CandidateRecallReason.__table__,
        Core3CandidateFeatureSnapshot.__table__,
        Core3CandidateRecallReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3CandidateRecallReviewIssue.__table__,
        Core3CandidateFeatureSnapshot.__table__,
        Core3CandidateRecallReason.__table__,
        Core3CandidatePool.__table__,
        Core3CandidateRecallRun.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
