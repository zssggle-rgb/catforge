"""core3 real data evidence atom

Revision ID: 0008_core3_evidence
Revises: 0007_core3_cleaning
Create Date: 2026-06-13
"""

from alembic import op
from sqlalchemy import text

from app.models.entities import Core3EvidenceAtom, Core3EvidenceLink

revision = "0008_core3_evidence"
down_revision = "0007_core3_cleaning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Core3EvidenceAtom.__table__.create(bind=bind, checkfirst=True)
    Core3EvidenceLink.__table__.create(bind=bind, checkfirst=True)
    bind.execute(
        text(
            "CREATE VIEW core3_current_evidence_atom AS "
            "SELECT * FROM core3_evidence_atom "
            "WHERE is_current = true AND evidence_status = 'current'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP VIEW IF EXISTS core3_current_evidence_atom"))
    Core3EvidenceLink.__table__.drop(bind=bind, checkfirst=True)
    Core3EvidenceAtom.__table__.drop(bind=bind, checkfirst=True)
