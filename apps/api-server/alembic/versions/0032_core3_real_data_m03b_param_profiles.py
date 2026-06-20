"""core3 real data M03B parameter profiles

Revision ID: 0032_core3_m03b_param_profiles
Revises: 0031_core3_param_taxonomy
Create Date: 2026-06-20
"""

from alembic import op

from app.models.entities import Core3ParamTierCoverage, Core3SkuParamDimensionTier


revision = "0032_core3_m03b_param_profiles"
down_revision = "0031_core3_param_taxonomy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuParamDimensionTier.__table__,
        Core3ParamTierCoverage.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ParamTierCoverage.__table__,
        Core3SkuParamDimensionTier.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
