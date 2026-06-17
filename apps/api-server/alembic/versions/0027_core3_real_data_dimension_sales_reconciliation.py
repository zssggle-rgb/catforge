"""core3 real data dimension sales reconciliation

Revision ID: 0027_core3_sales_recon
Revises: 0026_core3_sku_business_profile
Create Date: 2026-06-14
"""

from alembic import op

from app.models.entities import (
    Core3BusinessDimensionSalesSummary,
    Core3BusinessDimensionSkuContribution,
    Core3BusinessSalesReconciliationCheck,
    Core3BusinessSalesReconciliationIssue,
)

revision = "0027_core3_sales_recon"
down_revision = "0026_core3_sku_business_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        Core3BusinessDimensionSalesSummary.__table__,
        Core3BusinessDimensionSkuContribution.__table__,
        Core3BusinessSalesReconciliationCheck.__table__,
        Core3BusinessSalesReconciliationIssue.__table__,
    ):
        table.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    for table in (
        Core3BusinessSalesReconciliationIssue.__table__,
        Core3BusinessSalesReconciliationCheck.__table__,
        Core3BusinessDimensionSkuContribution.__table__,
        Core3BusinessDimensionSalesSummary.__table__,
    ):
        table.drop(op.get_bind(), checkfirst=True)
