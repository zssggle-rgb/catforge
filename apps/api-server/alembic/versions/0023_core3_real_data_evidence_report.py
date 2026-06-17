"""core3 real data evidence report

Revision ID: 0023_evidence_report
Revises: 0022_core3_selection
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3ReportEvidenceCard,
    Core3ReportExport,
    Core3ReportReviewIssue,
    Core3ReportSection,
    Core3TargetReportPayload,
)

revision = "0023_evidence_report"
down_revision = "0022_core3_selection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3ReportEvidenceCard.__table__,
        Core3TargetReportPayload.__table__,
        Core3ReportSection.__table__,
        Core3ReportExport.__table__,
        Core3ReportReviewIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3ReportReviewIssue.__table__,
        Core3ReportExport.__table__,
        Core3ReportSection.__table__,
        Core3TargetReportPayload.__table__,
        Core3ReportEvidenceCard.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
