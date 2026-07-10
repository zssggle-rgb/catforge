"""core3 purchase reason profile

Revision ID: 0042_core3_m12d_purchase_reason
Revises: 0041_core3_m04c_wtp_gate
Create Date: 2026-07-08
"""

from alembic import op

from app.models.entities import (
    Core3PurchaseReasonProfileVersion,
    Core3SkuPurchaseReasonAnchor,
    Core3SkuPurchaseReasonProfile,
)


revision = "0042_core3_m12d_purchase_reason"
down_revision = "0041_core3_m04c_wtp_gate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3PurchaseReasonProfileVersion.__table__,
        Core3SkuPurchaseReasonProfile.__table__,
        Core3SkuPurchaseReasonAnchor.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuPurchaseReasonAnchor.__table__,
        Core3SkuPurchaseReasonProfile.__table__,
        Core3PurchaseReasonProfileVersion.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
