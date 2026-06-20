"""core3 real data parameter taxonomy

Revision ID: 0031_core3_param_taxonomy
Revises: 0030_core3_market_pool_v2
Create Date: 2026-06-20
"""

from alembic import op

from app.models.entities import (
    Core3ParamConceptCandidate,
    Core3ParamDefinition,
    Core3ParamFieldCluster,
    Core3ParamFieldMappingRule,
    Core3ParamRawFieldInventory,
    Core3ParamTaxonomyReviewItem,
    Core3ParamTaxonomyVersion,
)


revision = "0031_core3_param_taxonomy"
down_revision = "0030_core3_market_pool_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ParamTaxonomyVersion.__table__,
        Core3ParamRawFieldInventory.__table__,
        Core3ParamFieldCluster.__table__,
        Core3ParamConceptCandidate.__table__,
        Core3ParamDefinition.__table__,
        Core3ParamFieldMappingRule.__table__,
        Core3ParamTaxonomyReviewItem.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ParamTaxonomyReviewItem.__table__,
        Core3ParamFieldMappingRule.__table__,
        Core3ParamDefinition.__table__,
        Core3ParamConceptCandidate.__table__,
        Core3ParamFieldCluster.__table__,
        Core3ParamRawFieldInventory.__table__,
        Core3ParamTaxonomyVersion.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
