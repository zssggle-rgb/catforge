"""core3 real data M09C user task profiles

Revision ID: 0037_core3_m09c_user_tasks
Revises: 0036_core3_m10c_target_groups
Create Date: 2026-06-21
"""

from alembic import op

from app.models.entities import (
    Core3M09cSkuUserTaskProfile,
    Core3M09cSkuUserTaskScore,
    Core3M09cUserTaskCoverage,
)


revision = "0037_core3_m09c_user_tasks"
down_revision = "0036_core3_m10c_target_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3M09cSkuUserTaskProfile.__table__,
        Core3M09cSkuUserTaskScore.__table__,
        Core3M09cUserTaskCoverage.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3M09cUserTaskCoverage.__table__,
        Core3M09cSkuUserTaskScore.__table__,
        Core3M09cSkuUserTaskProfile.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
