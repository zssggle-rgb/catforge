"""core3 real data M11C value battlefield profiles

Revision ID: 0035_core3_m11c_value_battlefields
Revises: 0034_core3_m05c_comment_profiles
Create Date: 2026-06-21
"""

from alembic import op

from app.models.entities import (
    Core3SkuValueBattlefieldProfile,
    Core3SkuValueBattlefieldScore,
    Core3ValueBattlefieldGraphSnapshot,
)


revision = "0035_core3_m11c_value_battlefields"
down_revision = "0034_core3_m05c_comment_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3SkuValueBattlefieldProfile.__table__,
        Core3SkuValueBattlefieldScore.__table__,
        Core3ValueBattlefieldGraphSnapshot.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3ValueBattlefieldGraphSnapshot.__table__,
        Core3SkuValueBattlefieldScore.__table__,
        Core3SkuValueBattlefieldProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
