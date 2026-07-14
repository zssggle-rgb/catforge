"""core3 versioned competitor profile persistence

Revision ID: 0046_core3_competitor_profile
Revises: 0045_core3_sellpoint_value_profile
Create Date: 2026-07-14
"""

from alembic import op
from sqlalchemy import func, inspect, select

from app.models.entities import (
    Core3CompetitorProfileVersion,
    Core3SkuCompetitorProfile,
    Core3SkuCompetitorProfilePair,
    Core3SkuCompetitorProfileRelation,
    Core3SkuCompetitorProfileSelection,
)


revision = "0046_core3_competitor_profile"
down_revision = "0045_core3_sellpoint_value_profile"
branch_labels = None
depends_on = None


PROFILE_TABLES = (
    Core3CompetitorProfileVersion.__table__,
    Core3SkuCompetitorProfile.__table__,
    Core3SkuCompetitorProfilePair.__table__,
    Core3SkuCompetitorProfileRelation.__table__,
    Core3SkuCompetitorProfileSelection.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in PROFILE_TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    populated = []
    for table in PROFILE_TABLES:
        if table.name not in existing:
            continue
        count = int(bind.scalar(select(func.count()).select_from(table)) or 0)
        if count:
            populated.append(f"{table.name}={count}")
    if populated:
        raise RuntimeError(
            "refusing to downgrade competitor profile tables with persisted data: "
            + ", ".join(populated)
        )
    for table in reversed(PROFILE_TABLES):
        table.drop(bind=bind, checkfirst=True)
