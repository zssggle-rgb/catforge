"""core3 semantic market graph and allocation

Revision ID: 0039_core3_semantic_market
Revises: 0038_core3_semantic_id_width
Create Date: 2026-06-22
"""

from alembic import op

from app.models.entities import (
    Core3SemanticMarketAllocation,
    Core3SemanticMarketDimensionSummary,
    Core3SemanticMarketGraphSnapshot,
    Core3SemanticMarketReconciliationCheck,
    Core3SemanticMarketSkuContribution,
)


revision = "0039_core3_semantic_market"
down_revision = "0038_core3_semantic_id_width"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SemanticMarketAllocation.__table__,
        Core3SemanticMarketDimensionSummary.__table__,
        Core3SemanticMarketSkuContribution.__table__,
        Core3SemanticMarketGraphSnapshot.__table__,
        Core3SemanticMarketReconciliationCheck.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SemanticMarketReconciliationCheck.__table__,
        Core3SemanticMarketGraphSnapshot.__table__,
        Core3SemanticMarketSkuContribution.__table__,
        Core3SemanticMarketDimensionSummary.__table__,
        Core3SemanticMarketAllocation.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
