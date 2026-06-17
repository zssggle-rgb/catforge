"""core3 real data cleaning quality

Revision ID: 0007_core3_cleaning
Revises: 0006_core3_source_registry
Create Date: 2026-06-13
"""

from alembic import op

from app.models.entities import (
    Core3CleanAttribute,
    Core3CleanClaim,
    Core3CleanClaimSentence,
    Core3CleanComment,
    Core3CleanCommentDimension,
    Core3CleanCommentSentence,
    Core3CleanMarketWeekly,
    Core3CleanSku,
    Core3DataQualityIssue,
)

revision = "0007_core3_cleaning"
down_revision = "0006_core3_source_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3CleanSku.__table__,
        Core3CleanMarketWeekly.__table__,
        Core3CleanAttribute.__table__,
        Core3CleanClaim.__table__,
        Core3CleanClaimSentence.__table__,
        Core3CleanComment.__table__,
        Core3CleanCommentSentence.__table__,
        Core3CleanCommentDimension.__table__,
        Core3DataQualityIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in [
        Core3DataQualityIssue.__table__,
        Core3CleanCommentDimension.__table__,
        Core3CleanCommentSentence.__table__,
        Core3CleanComment.__table__,
        Core3CleanClaimSentence.__table__,
        Core3CleanClaim.__table__,
        Core3CleanAttribute.__table__,
        Core3CleanMarketWeekly.__table__,
        Core3CleanSku.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)
