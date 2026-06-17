"""core3 real data base claim activation

Revision ID: 0010_core3_base_claim
Revises: 0009_core3_param
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3ExtractClaimHit,
    Core3SkuClaimActivationBase,
    Core3SkuClaimSourceStatus,
)

revision = "0010_core3_base_claim"
down_revision = "0009_core3_param"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ExtractClaimHit.__table__,
        Core3SkuClaimSourceStatus.__table__,
        Core3SkuClaimActivationBase.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuClaimActivationBase.__table__,
        Core3SkuClaimSourceStatus.__table__,
        Core3ExtractClaimHit.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
