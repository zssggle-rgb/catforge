"""goal1 core analysis engine

Revision ID: 0002_goal1_core_engine
Revises: 0001_baseline
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.models.entities import (
    AnalysisRun,
    CalibrationRun,
    EvaluationRun,
    GoldLabel,
    RuleSet,
    SkuCompetitorResult,
)

revision = "0002_goal1_core_engine"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in [
        RuleSet.__table__,
        AnalysisRun.__table__,
        SkuCompetitorResult.__table__,
        GoldLabel.__table__,
        EvaluationRun.__table__,
        CalibrationRun.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)

    _add_missing_columns("evidence_item", [sa.Column("source_ref", sa.JSON(), nullable=True)])
    _add_missing_columns(
        "sku_param_normalized",
        [
            sa.Column("rule_version", sa.String(length=40), nullable=False, server_default="1.0.0"),
            sa.Column("asset_version", sa.String(length=40), nullable=False, server_default="0.1.0"),
        ],
    )
    _add_missing_columns(
        "sku_claim_result",
        [
            sa.Column("score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("rule_version", sa.String(length=40), nullable=False, server_default="1.0.0"),
            sa.Column("asset_version", sa.String(length=40), nullable=False, server_default="0.1.0"),
        ],
    )
    _add_missing_columns(
        "sku_comment_topic_result",
        [
            sa.Column("review_status", sa.String(length=40), nullable=False, server_default="auto_pass"),
            sa.Column("rule_version", sa.String(length=40), nullable=False, server_default="1.0.0"),
            sa.Column("asset_version", sa.String(length=40), nullable=False, server_default="0.1.0"),
        ],
    )
    _add_missing_columns(
        "sku_task_score",
        [
            sa.Column("review_status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("rule_version", sa.String(length=40), nullable=False, server_default="1.0.0"),
            sa.Column("asset_version", sa.String(length=40), nullable=False, server_default="0.1.0"),
        ],
    )
    _add_missing_columns(
        "sku_battlefield_score",
        [
            sa.Column("review_status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("rule_version", sa.String(length=40), nullable=False, server_default="1.0.0"),
            sa.Column("asset_version", sa.String(length=40), nullable=False, server_default="0.1.0"),
        ],
    )


def downgrade() -> None:
    for table_name, columns in [
        ("sku_battlefield_score", ["asset_version", "rule_version", "review_status"]),
        ("sku_task_score", ["asset_version", "rule_version", "review_status"]),
        ("sku_comment_topic_result", ["asset_version", "rule_version", "review_status"]),
        ("sku_claim_result", ["asset_version", "rule_version", "score"]),
        ("sku_param_normalized", ["asset_version", "rule_version"]),
        ("evidence_item", ["source_ref"]),
    ]:
        with op.batch_alter_table(table_name) as batch:
            for column in columns:
                batch.drop_column(column)

    bind = op.get_bind()
    for table in [
        CalibrationRun.__table__,
        EvaluationRun.__table__,
        GoldLabel.__table__,
        SkuCompetitorResult.__table__,
        AnalysisRun.__table__,
        RuleSet.__table__,
    ]:
        table.drop(bind=bind, checkfirst=True)


def _add_missing_columns(table_name: str, columns: list[sa.Column]) -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns(table_name)}
    missing = [column for column in columns if column.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table_name) as batch:
        for column in missing:
            batch.add_column(column)
