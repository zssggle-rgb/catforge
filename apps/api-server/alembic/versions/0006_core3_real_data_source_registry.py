"""core3 real data source registry

Revision ID: 0006_core3_source_registry
Revises: 0005_core3_foundation
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3SourceBatch,
    Core3SourceImpactedSku,
    Core3SourceRowRegistry,
)

revision = "0006_core3_source_registry"
down_revision = "0005_core3_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SourceBatch.__table__,
        Core3SourceRowRegistry.__table__,
        Core3SourceImpactedSku.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SourceImpactedSku.__table__,
        Core3SourceRowRegistry.__table__,
        Core3SourceBatch.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
