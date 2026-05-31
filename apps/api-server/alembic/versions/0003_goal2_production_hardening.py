"""goal2 production hardening

Revision ID: 0003_goal2_production_hardening
Revises: 0002_goal1_core_engine
Create Date: 2026-05-31
"""

from alembic import op

from app.models.entities import (
    AssetDiff,
    AssetVersion,
    AuditEvent,
    JobAttempt,
    JobRun,
    RuntimeExport,
)

revision = "0003_goal2_production_hardening"
down_revision = "0002_goal1_core_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        JobRun.__table__,
        JobAttempt.__table__,
        AssetVersion.__table__,
        AssetDiff.__table__,
        AuditEvent.__table__,
        RuntimeExport.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        RuntimeExport.__table__,
        AuditEvent.__table__,
        AssetDiff.__table__,
        AssetVersion.__table__,
        JobAttempt.__table__,
        JobRun.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
