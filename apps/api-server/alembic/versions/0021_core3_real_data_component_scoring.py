"""core3 real data component scoring

Revision ID: 0021_core3_component_scoring
Revises: 0020_core3_candidate_recall
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3CandidateComponentExplanation,
    Core3CandidateComponentScore,
    Core3CandidateRoleScore,
    Core3CandidateScoreReviewIssue,
)

revision = "0021_core3_component_scoring"
down_revision = "0020_core3_candidate_recall"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3CandidateComponentScore.__table__,
        Core3CandidateRoleScore.__table__,
        Core3CandidateComponentExplanation.__table__,
        Core3CandidateScoreReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3CandidateScoreReviewIssue.__table__,
        Core3CandidateComponentExplanation.__table__,
        Core3CandidateRoleScore.__table__,
        Core3CandidateComponentScore.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
