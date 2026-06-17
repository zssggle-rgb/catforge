"""core3 real data pipeline governance

Revision ID: 0024_core3_pipeline_governance
Revises: 0023_evidence_report
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3V2AcceptanceReport,
    Core3V2RecomputePlan,
    Core3V2ReleaseGate,
    Core3V2ReviewDecision,
    Core3V2ReviewQueue,
)

revision = "0024_core3_pipeline_governance"
down_revision = "0023_evidence_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3V2RecomputePlan.__table__,
        Core3V2ReviewQueue.__table__,
        Core3V2ReviewDecision.__table__,
        Core3V2AcceptanceReport.__table__,
        Core3V2ReleaseGate.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3V2ReleaseGate.__table__,
        Core3V2AcceptanceReport.__table__,
        Core3V2ReviewDecision.__table__,
        Core3V2ReviewQueue.__table__,
        Core3V2RecomputePlan.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
