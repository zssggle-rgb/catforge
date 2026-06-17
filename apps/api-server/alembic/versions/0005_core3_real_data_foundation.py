"""core3 real data v2 foundation

Revision ID: 0005_core3_foundation
Revises: 0004_tv_core3_mvp
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3V2ModuleDependencySnapshot,
    Core3V2ModuleRun,
    Core3V2PipelineRun,
    Core3V2PipelineWatermark,
)

revision = "0005_core3_foundation"
down_revision = "0004_tv_core3_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3V2PipelineRun.__table__,
        Core3V2ModuleRun.__table__,
        Core3V2ModuleDependencySnapshot.__table__,
        Core3V2PipelineWatermark.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3V2PipelineWatermark.__table__,
        Core3V2ModuleDependencySnapshot.__table__,
        Core3V2ModuleRun.__table__,
        Core3V2PipelineRun.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
