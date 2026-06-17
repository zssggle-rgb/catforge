"""tv core3 mvp run context

Revision ID: 0004_tv_core3_mvp
Revises: 0003_goal2_production_hardening
Create Date: 2026-06-10
"""

from alembic import op

from app.models.entities import (
    Core3CompetitorCandidate,
    Core3CompetitorResult,
    Core3EvidenceCard,
    Core3PipelineRun,
    Core3SkuFeatureProfile,
    Core3SkuMarketProfile,
)

revision = "0004_tv_core3_mvp"
down_revision = "0003_goal2_production_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3PipelineRun.__table__,
        Core3SkuMarketProfile.__table__,
        Core3SkuFeatureProfile.__table__,
        Core3CompetitorCandidate.__table__,
        Core3CompetitorResult.__table__,
        Core3EvidenceCard.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3EvidenceCard.__table__,
        Core3CompetitorResult.__table__,
        Core3CompetitorCandidate.__table__,
        Core3SkuFeatureProfile.__table__,
        Core3SkuMarketProfile.__table__,
        Core3PipelineRun.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
