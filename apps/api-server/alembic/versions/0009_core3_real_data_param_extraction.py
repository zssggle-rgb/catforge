"""core3 real data parameter extraction

Revision ID: 0009_core3_param
Revises: 0008_core3_evidence
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3ExtractParamValue,
    Core3ParamAliasCandidate,
    Core3ParamFieldProfile,
    Core3ParamValueConflict,
    Core3SkuParamProfile,
)

revision = "0009_core3_param"
down_revision = "0008_core3_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ParamFieldProfile.__table__,
        Core3ParamValueConflict.__table__,
        Core3ExtractParamValue.__table__,
        Core3ParamAliasCandidate.__table__,
        Core3SkuParamProfile.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuParamProfile.__table__,
        Core3ParamAliasCandidate.__table__,
        Core3ExtractParamValue.__table__,
        Core3ParamValueConflict.__table__,
        Core3ParamFieldProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
