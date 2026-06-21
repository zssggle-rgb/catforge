"""core3 real data M04C claim fact profiles

Revision ID: 0033_core3_m04c_claim_profiles
Revises: 0032_core3_m03b_param_profiles
Create Date: 2026-06-21
"""

from alembic import op

from app.models.entities import (
    Core3ClaimPositionCoverage,
    Core3SkuClaimDimensionPosition,
    Core3SkuClaimFact,
    Core3SkuClaimFactProfile,
)


revision = "0033_core3_m04c_claim_profiles"
down_revision = "0032_core3_m03b_param_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuClaimFactProfile.__table__,
        Core3SkuClaimFact.__table__,
        Core3SkuClaimDimensionPosition.__table__,
        Core3ClaimPositionCoverage.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ClaimPositionCoverage.__table__,
        Core3SkuClaimDimensionPosition.__table__,
        Core3SkuClaimFact.__table__,
        Core3SkuClaimFactProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
