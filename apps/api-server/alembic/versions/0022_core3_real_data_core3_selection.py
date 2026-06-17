"""core3 real data core competitor selection

Revision ID: 0022_core3_selection
Revises: 0021_core3_component_scoring
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3CompetitorSelection,
    Core3CompetitorSelectionAudit,
    Core3CompetitorSelectionReviewIssue,
    Core3CompetitorSelectionRun,
    Core3CompetitorSlotDecision,
)

revision = "0022_core3_selection"
down_revision = "0021_core3_component_scoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3CompetitorSelectionRun.__table__,
        Core3CompetitorSelection.__table__,
        Core3CompetitorSlotDecision.__table__,
        Core3CompetitorSelectionAudit.__table__,
        Core3CompetitorSelectionReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3CompetitorSelectionReviewIssue.__table__,
        Core3CompetitorSelectionAudit.__table__,
        Core3CompetitorSlotDecision.__table__,
        Core3CompetitorSelection.__table__,
        Core3CompetitorSelectionRun.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
