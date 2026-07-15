"""core3 competitor profile V1.1 analysis persistence

Revision ID: 0047_core3_competitor_profile_v1_1
Revises: 0046_core3_competitor_profile
Create Date: 2026-07-15
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import sqlalchemy as sa
from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects.postgresql import JSONB

revision = "0047_core3_competitor_profile_v1_1"
down_revision = "0046_core3_competitor_profile"
branch_labels = None
depends_on = None


V11_SCHEMA_VERSION = "sku_competitor_decision_profile_v1_1"
V11_RULE_VERSION = "competitor_profile_materializer_v1_1"
V11_METHOD_VERSION = "competitor_profile_method_v1_1"

VERSION_TABLE = "core3_competitor_profile_version"
SNAPSHOT_TABLE = "core3_competitor_profile_sku_snapshot"
PROFILE_TABLE = "core3_sku_competitor_profile"
PAIR_TABLE = "core3_sku_competitor_profile_pair"
RELATION_TABLE = "core3_sku_competitor_profile_relation"
SELECTION_TABLE = "core3_sku_competitor_profile_selection"

VERSION_SCOPE_INDEX = "uq_core3_cp_version_scope_identity"
_SQL_NULL = object()

PROFILE_COLUMNS = (
    "analysis_summary_json",
    "analysis_fact_index_json",
    "analysis_evidence_index_json",
    "analysis_result_hash",
    "analysis_candidate_count",
    "analysis_available_dimension_count",
    "analysis_review_item_count",
)
PAIR_COLUMNS = (
    "scope_status",
    "exclusion_reason_code",
    "target_snapshot_ref",
    "candidate_snapshot_ref",
    "analysis_snapshot_json",
    "analysis_conclusion_strength",
    "analysis_score",
    "analysis_available_weight",
    "analysis_result_hash",
    "analysis_review_required",
    "selection_question_code",
    "selection_conclusion_strength",
)
RELATION_COLUMNS = (
    "analysis_relation_status",
    "analysis_review_items_json",
)
SELECTION_COLUMNS = (
    "selection_policy_version",
    "selection_score",
    "selection_available_weight",
    "selection_conclusion_strength",
    "selection_role_codes_json",
    "selection_score_breakdown_json",
)

PROFILE_CHECKS = {
    "ck_core3_cp_profile_v11_complete": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(analysis_summary_json IS NOT NULL "
        "AND analysis_fact_index_json IS NOT NULL "
        "AND analysis_evidence_index_json IS NOT NULL "
        "AND analysis_result_hash IS NOT NULL "
        "AND analysis_candidate_count IS NOT NULL "
        "AND analysis_available_dimension_count IS NOT NULL "
        "AND analysis_review_item_count IS NOT NULL)"
    ),
    "ck_core3_cp_profile_v11_counts": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(analysis_candidate_count >= 0 "
        "AND analysis_available_dimension_count >= 0 "
        "AND analysis_review_item_count >= 0)"
    ),
}
PAIR_CHECKS = {
    "ck_core3_cp_pair_distinct": (
        f"schema_version = '{V11_SCHEMA_VERSION}' "
        "OR target_sku_code <> candidate_sku_code"
    ),
    "ck_core3_cp_pair_selected_status": (
        f"NOT selected OR schema_version = '{V11_SCHEMA_VERSION}' "
        "OR candidate_status in ('eligible','limited')"
    ),
    "ck_core3_cp_pair_v11_scope": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(scope_status IS NOT NULL "
        "AND scope_status in ('analyzable','excluded'))"
    ),
    "ck_core3_cp_pair_v11_exclusion": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "((scope_status = 'excluded' AND exclusion_reason_code IS NOT NULL "
        "AND exclusion_reason_code in "
        "('self_pair','project_mismatch','category_mismatch',"
        "'candidate_outside_manifest','identity_decode_failed')) "
        "OR (scope_status = 'analyzable' AND exclusion_reason_code IS NULL))"
    ),
    "ck_core3_cp_pair_v11_self": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "((target_sku_code = candidate_sku_code "
        "AND scope_status = 'excluded' "
        "AND exclusion_reason_code = 'self_pair') "
        "OR (target_sku_code <> candidate_sku_code "
        "AND (exclusion_reason_code IS NULL "
        "OR exclusion_reason_code <> 'self_pair')))"
    ),
    "ck_core3_cp_pair_v11_complete": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(target_snapshot_ref IS NOT NULL AND candidate_snapshot_ref IS NOT NULL "
        "AND analysis_snapshot_json IS NOT NULL "
        "AND analysis_conclusion_strength IS NOT NULL "
        "AND analysis_conclusion_strength in "
        "('strong','supported','directional','reference','unknown') "
        "AND analysis_result_hash IS NOT NULL "
        "AND analysis_review_required IS NOT NULL)"
    ),
    "ck_core3_cp_pair_v11_score": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "((scope_status = 'excluded' AND analysis_score IS NULL "
        "AND analysis_available_weight IS NULL "
        "AND analysis_conclusion_strength IS NOT NULL "
        "AND analysis_conclusion_strength = 'unknown') "
        "OR (scope_status = 'analyzable' "
        "AND analysis_available_weight IS NOT NULL "
        "AND analysis_available_weight >= 0 AND analysis_available_weight <= 1 "
        "AND ((analysis_available_weight = 0 AND analysis_score IS NULL) "
        "OR (analysis_available_weight > 0 AND analysis_score IS NOT NULL "
        "AND analysis_score >= 0 "
        "AND analysis_score <= 1))))"
    ),
    "ck_core3_cp_pair_v11_selected": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR NOT selected OR "
        "(scope_status = 'analyzable' "
        "AND selection_question_code IS NOT NULL "
        "AND selection_question_code in "
        "('purchase_choice','price_volume_pressure','value_substitution',"
        "'configuration_follow','same_brand_portfolio_role','scenario_solution',"
        "'price_ladder_defense','key_competitor_selection') "
        "AND selection_conclusion_strength IS NOT NULL "
        "AND selection_conclusion_strength in "
        "('strong','supported','directional','reference'))"
    ),
}
RELATION_CHECKS = {
    "ck_core3_cp_relation_primary": (
        f"NOT is_primary OR schema_version = '{V11_SCHEMA_VERSION}' "
        "OR relation_status in ('passed','limited')"
    ),
    "ck_core3_cp_relation_v11_status": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(analysis_relation_status IS NOT NULL "
        "AND analysis_relation_status in ('passed','limited','unassessable','failed') "
        "AND analysis_review_items_json IS NOT NULL)"
    ),
    "ck_core3_cp_relation_v11_primary": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR NOT is_primary OR "
        "(analysis_relation_status IS NOT NULL "
        "AND analysis_relation_status in ('passed','limited'))"
    ),
}
SELECTION_CHECKS = {
    "ck_core3_cp_selection_v11_complete": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(selection_policy_version IS NOT NULL "
        "AND selection_score IS NOT NULL "
        "AND selection_available_weight IS NOT NULL "
        "AND selection_conclusion_strength IS NOT NULL "
        "AND selection_conclusion_strength in "
        "('strong','supported','directional','reference') "
        "AND selection_role_codes_json IS NOT NULL "
        "AND selection_score_breakdown_json IS NOT NULL)"
    ),
    "ck_core3_cp_selection_v11_score": (
        f"schema_version <> '{V11_SCHEMA_VERSION}' OR "
        "(selection_score >= 0 AND selection_score <= 1 "
        "AND selection_available_weight >= 0 "
        "AND selection_available_weight <= 1)"
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    operations = _operations(bind)
    sqlite_rows = _capture_sqlite_child_rows(bind)
    inspector = sa.inspect(bind)
    required = {
        VERSION_TABLE,
        PROFILE_TABLE,
        PAIR_TABLE,
        RELATION_TABLE,
        SELECTION_TABLE,
    }
    missing = sorted(required - set(inspector.get_table_names()))
    if missing:
        raise RuntimeError(
            "competitor profile V1.1 requires the complete 0046 schema; missing: "
            + ", ".join(missing)
        )

    _create_index_if_missing(
        bind,
        operations,
        VERSION_TABLE,
        VERSION_SCOPE_INDEX,
        (
            "competitor_profile_version_id",
            "project_id",
            "category_code",
            "release_scope_key",
        ),
        unique=True,
    )
    _snapshot_table().create(bind=bind, checkfirst=True)

    _add_columns_if_missing(
        bind,
        operations,
        PROFILE_TABLE,
        (
            sa.Column("analysis_summary_json", _json_type(), nullable=True),
            sa.Column("analysis_fact_index_json", _json_type(), nullable=True),
            sa.Column("analysis_evidence_index_json", _json_type(), nullable=True),
            sa.Column("analysis_result_hash", sa.String(length=200), nullable=True),
            sa.Column("analysis_candidate_count", sa.Integer(), nullable=True),
            sa.Column(
                "analysis_available_dimension_count", sa.Integer(), nullable=True
            ),
            sa.Column("analysis_review_item_count", sa.Integer(), nullable=True),
        ),
    )
    _add_columns_if_missing(
        bind,
        operations,
        PAIR_TABLE,
        (
            sa.Column("scope_status", sa.String(length=40), nullable=True),
            sa.Column("exclusion_reason_code", sa.String(length=80), nullable=True),
            sa.Column("target_snapshot_ref", sa.String(length=120), nullable=True),
            sa.Column("candidate_snapshot_ref", sa.String(length=120), nullable=True),
            sa.Column("analysis_snapshot_json", _json_type(), nullable=True),
            sa.Column(
                "analysis_conclusion_strength", sa.String(length=40), nullable=True
            ),
            sa.Column("analysis_score", sa.Numeric(8, 6), nullable=True),
            sa.Column("analysis_available_weight", sa.Numeric(8, 6), nullable=True),
            sa.Column("analysis_result_hash", sa.String(length=200), nullable=True),
            sa.Column("analysis_review_required", sa.Boolean(), nullable=True),
            sa.Column("selection_question_code", sa.String(length=80), nullable=True),
            sa.Column(
                "selection_conclusion_strength", sa.String(length=40), nullable=True
            ),
        ),
    )
    _add_columns_if_missing(
        bind,
        operations,
        RELATION_TABLE,
        (
            sa.Column("analysis_relation_status", sa.String(length=40), nullable=True),
            sa.Column("analysis_review_items_json", _json_type(), nullable=True),
        ),
    )
    _add_columns_if_missing(
        bind,
        operations,
        SELECTION_TABLE,
        (
            sa.Column("selection_policy_version", sa.String(length=160), nullable=True),
            sa.Column("selection_score", sa.Numeric(8, 6), nullable=True),
            sa.Column("selection_available_weight", sa.Numeric(8, 6), nullable=True),
            sa.Column(
                "selection_conclusion_strength", sa.String(length=40), nullable=True
            ),
            sa.Column("selection_role_codes_json", _json_type(), nullable=True),
            sa.Column("selection_score_breakdown_json", _json_type(), nullable=True),
        ),
    )

    _reconcile_checks(bind, operations, PROFILE_TABLE, PROFILE_CHECKS)
    _reconcile_checks(
        bind,
        operations,
        PAIR_TABLE,
        PAIR_CHECKS,
        replace_names={
            "ck_core3_cp_pair_distinct",
            "ck_core3_cp_pair_selected_status",
        },
    )
    _reconcile_checks(
        bind,
        operations,
        RELATION_TABLE,
        RELATION_CHECKS,
        replace_names={"ck_core3_cp_relation_primary"},
    )
    _reconcile_checks(bind, operations, SELECTION_TABLE, SELECTION_CHECKS)

    for table_name, index_name, columns in (
        (
            PROFILE_TABLE,
            "ix_core3_cp_profile_v11_read",
            (
                "competitor_profile_version_id",
                "target_sku_code",
                "analysis_result_hash",
            ),
        ),
        (
            PAIR_TABLE,
            "ix_core3_cp_pair_v11_scope",
            ("competitor_profile_version_id", "target_sku_code", "scope_status"),
        ),
        (
            PAIR_TABLE,
            "ix_core3_cp_pair_v11_candidate",
            (
                "competitor_profile_version_id",
                "target_sku_code",
                "candidate_sku_code",
                "analysis_result_hash",
            ),
        ),
        (
            RELATION_TABLE,
            "ix_core3_cp_relation_v11_status",
            (
                "competitor_profile_version_id",
                "relation_code",
                "analysis_relation_status",
            ),
        ),
        (
            SELECTION_TABLE,
            "ix_core3_cp_selection_v11_read",
            (
                "competitor_profile_version_id",
                "target_sku_code",
                "selection_rank",
                "selection_conclusion_strength",
            ),
        ),
    ):
        _create_index_if_missing(
            bind,
            operations,
            table_name,
            index_name,
            columns,
        )
    _restore_sqlite_child_rows(bind, sqlite_rows)


def downgrade() -> None:
    bind = op.get_bind()
    operations = _operations(bind)
    blockers = _downgrade_blockers(bind)
    if blockers:
        raise RuntimeError(
            "refusing to downgrade competitor profile V1.1 with persisted V1.1 data: "
            + ", ".join(blockers)
        )

    sqlite_rows = _capture_sqlite_child_rows(bind)

    if sa.inspect(bind).has_table(SNAPSHOT_TABLE):
        _snapshot_table().drop(bind=bind, checkfirst=True)

    _drop_extension(
        bind,
        operations,
        SELECTION_TABLE,
        column_names=SELECTION_COLUMNS,
        check_names=tuple(SELECTION_CHECKS),
        index_names=("ix_core3_cp_selection_v11_read",),
    )
    _drop_extension(
        bind,
        operations,
        RELATION_TABLE,
        column_names=RELATION_COLUMNS,
        check_names=tuple(RELATION_CHECKS),
        index_names=("ix_core3_cp_relation_v11_status",),
        replacement_checks={
            "ck_core3_cp_relation_primary": (
                "NOT is_primary OR relation_status in ('passed','limited')"
            )
        },
    )
    _drop_extension(
        bind,
        operations,
        PAIR_TABLE,
        column_names=PAIR_COLUMNS,
        check_names=tuple(PAIR_CHECKS),
        index_names=(
            "ix_core3_cp_pair_v11_scope",
            "ix_core3_cp_pair_v11_candidate",
        ),
        replacement_checks={
            "ck_core3_cp_pair_distinct": ("target_sku_code <> candidate_sku_code"),
            "ck_core3_cp_pair_selected_status": (
                "NOT selected OR candidate_status in ('eligible','limited')"
            ),
        },
    )
    _drop_extension(
        bind,
        operations,
        PROFILE_TABLE,
        column_names=PROFILE_COLUMNS,
        check_names=tuple(PROFILE_CHECKS),
        index_names=("ix_core3_cp_profile_v11_read",),
    )
    _drop_index_if_present(bind, operations, VERSION_TABLE, VERSION_SCOPE_INDEX)
    _restore_sqlite_child_rows(bind, sqlite_rows)


def _json_type() -> sa.types.TypeEngine[Any]:
    return sa.JSON().with_variant(JSONB, "postgresql")


def _snapshot_table() -> sa.Table:
    metadata = sa.MetaData()
    sa.Table(
        "category_project",
        metadata,
        sa.Column("project_id", sa.String(length=36), primary_key=True),
    )
    sa.Table(
        VERSION_TABLE,
        metadata,
        sa.Column(
            "competitor_profile_version_id",
            sa.String(length=120),
            primary_key=True,
        ),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("category_code", sa.String(length=40), nullable=False),
        sa.Column("release_scope_key", sa.String(length=200), nullable=False),
    )
    return sa.Table(
        SNAPSHOT_TABLE,
        metadata,
        sa.Column(
            "competitor_profile_sku_snapshot_id",
            sa.String(length=120),
            primary_key=True,
        ),
        sa.Column(
            "competitor_profile_version_id",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey("category_project.project_id"),
            nullable=False,
            index=True,
        ),
        sa.Column("category_code", sa.String(length=40), nullable=False, index=True),
        sa.Column(
            "release_scope_key", sa.String(length=200), nullable=False, index=True
        ),
        sa.Column("sku_code", sa.String(length=160), nullable=False, index=True),
        sa.Column("profile_version", sa.String(length=160), nullable=False, index=True),
        sa.Column("schema_version", sa.String(length=160), nullable=False, index=True),
        sa.Column("rule_version", sa.String(length=160), nullable=False, index=True),
        sa.Column("method_version", sa.String(length=160), nullable=False, index=True),
        sa.Column("snapshot_json", _json_type(), nullable=False),
        sa.Column("module_availability_json", _json_type(), nullable=False),
        sa.Column("evidence_refs_json", _json_type(), nullable=False),
        sa.Column("source_lineage_json", _json_type(), nullable=False),
        sa.Column("limitations_json", _json_type(), nullable=False),
        sa.Column(
            "input_fingerprint", sa.String(length=200), nullable=False, index=True
        ),
        sa.Column("result_hash", sa.String(length=200), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "competitor_profile_version_id",
            "sku_code",
            name="uq_core3_cp_snapshot_version_sku",
        ),
        sa.ForeignKeyConstraint(
            (
                "competitor_profile_version_id",
                "project_id",
                "category_code",
                "release_scope_key",
            ),
            (
                f"{VERSION_TABLE}.competitor_profile_version_id",
                f"{VERSION_TABLE}.project_id",
                f"{VERSION_TABLE}.category_code",
                f"{VERSION_TABLE}.release_scope_key",
            ),
            name="fk_core3_cp_snapshot_version_scope",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"schema_version = '{V11_SCHEMA_VERSION}'",
            name="ck_core3_cp_snapshot_schema_v11",
        ),
        sa.CheckConstraint(
            "category_code in ('TV','AC')",
            name="ck_core3_cp_snapshot_category",
        ),
        sa.Index(
            "ix_core3_cp_snapshot_scope_sku",
            "competitor_profile_version_id",
            "project_id",
            "category_code",
            "release_scope_key",
            "sku_code",
        ),
        sa.Index(
            "ix_core3_cp_snapshot_result_hash",
            "competitor_profile_version_id",
            "result_hash",
        ),
    )


def _operations(bind: sa.Connection) -> Any:
    if hasattr(op, "add_column"):
        return op
    return Operations(MigrationContext.configure(bind))


def _add_columns_if_missing(
    bind: sa.Connection,
    operations: Any,
    table_name: str,
    columns: Iterable[sa.Column[Any]],
) -> None:
    existing = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
    for column in columns:
        if column.name in existing:
            continue
        operations.add_column(table_name, column)
        existing.add(str(column.name))


def _create_index_if_missing(
    bind: sa.Connection,
    operations: Any,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    *,
    unique: bool = False,
) -> None:
    indexes = {row["name"] for row in sa.inspect(bind).get_indexes(table_name)}
    if index_name in indexes:
        return
    operations.create_index(index_name, table_name, list(columns), unique=unique)


def _reconcile_checks(
    bind: sa.Connection,
    operations: Any,
    table_name: str,
    desired: Mapping[str, str],
    *,
    replace_names: set[str] | None = None,
) -> None:
    replace_names = replace_names or set()
    existing = {
        row["name"]: str(row.get("sqltext") or "")
        for row in sa.inspect(bind).get_check_constraints(table_name)
        if row.get("name")
    }
    replace_required = {
        name
        for name in replace_names
        if name in existing and V11_SCHEMA_VERSION not in existing[name]
    }
    create_names = [
        name for name in desired if name not in existing or name in replace_required
    ]
    drop_names = sorted(set(existing) & replace_required)
    if not create_names and not drop_names:
        return
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with operations.batch_alter_table(table_name, recreate=recreate) as batch:
        for name in drop_names:
            batch.drop_constraint(name, type_="check")
        for name in create_names:
            batch.create_check_constraint(name, desired[name])


def _downgrade_blockers(bind: sa.Connection) -> list[str]:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    blockers: list[str] = []
    if VERSION_TABLE in tables:
        count = _count_where(
            bind,
            VERSION_TABLE,
            (
                "schema_version = :schema_version "
                "OR rule_version = :rule_version "
                "OR method_version = :method_version"
            ),
            {
                "schema_version": V11_SCHEMA_VERSION,
                "rule_version": V11_RULE_VERSION,
                "method_version": V11_METHOD_VERSION,
            },
        )
        if count:
            blockers.append(f"{VERSION_TABLE}.v1_1_versions={count}")
    if SNAPSHOT_TABLE in tables:
        count = _count_where(bind, SNAPSHOT_TABLE, "1 = 1", {})
        if count:
            blockers.append(f"{SNAPSHOT_TABLE}={count}")
    for table_name, expected_columns in (
        (PROFILE_TABLE, PROFILE_COLUMNS),
        (PAIR_TABLE, PAIR_COLUMNS),
        (RELATION_TABLE, RELATION_COLUMNS),
        (SELECTION_TABLE, SELECTION_COLUMNS),
    ):
        if table_name not in tables:
            continue
        actual_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        analysis_columns = [
            column for column in expected_columns if column in actual_columns
        ]
        if not analysis_columns:
            continue
        predicate = " OR ".join(
            f'"{column}" IS NOT NULL' for column in analysis_columns
        )
        count = _count_where(bind, table_name, predicate, {})
        if count:
            blockers.append(f"{table_name}.v1_1_analysis_rows={count}")
    return blockers


def _count_where(
    bind: sa.Connection,
    table_name: str,
    predicate: str,
    parameters: Mapping[str, Any],
) -> int:
    statement = sa.text(f'SELECT COUNT(*) FROM "{table_name}" WHERE {predicate}')
    return int(bind.scalar(statement, parameters) or 0)


def _capture_sqlite_child_rows(
    bind: sa.Connection,
) -> dict[str, list[dict[str, Any]]]:
    if bind.dialect.name != "sqlite":
        return {}
    tables = set(sa.inspect(bind).get_table_names())
    captured: dict[str, list[dict[str, Any]]] = {}
    for table_name in (
        PROFILE_TABLE,
        PAIR_TABLE,
        RELATION_TABLE,
        SELECTION_TABLE,
    ):
        if table_name not in tables:
            continue
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        json_columns = [
            column for column in table.c if isinstance(column.type, sa.JSON)
        ]
        marker_labels = {
            column.name: f"__json_literal_null__{column.name}"
            for column in json_columns
        }
        statement = sa.select(
            *table.c,
            *(
                (sa.func.json_type(column) == "null").label(marker_labels[column.name])
                for column in json_columns
            ),
        )
        rows: list[dict[str, Any]] = []
        for result in bind.execute(statement).mappings():
            values = {column.name: result[column.name] for column in table.c}
            for column in json_columns:
                if result[marker_labels[column.name]]:
                    values[column.name] = sa.JSON.NULL
                elif values[column.name] is None:
                    values[column.name] = _SQL_NULL
            rows.append(values)
        captured[table_name] = rows
    return captured


def _restore_sqlite_child_rows(
    bind: sa.Connection,
    captured: Mapping[str, list[dict[str, Any]]],
) -> None:
    if not captured:
        return
    reflected = {
        table_name: sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        for table_name in captured
        if sa.inspect(bind).has_table(table_name)
    }
    if all(
        len(rows)
        == int(
            bind.scalar(sa.select(sa.func.count()).select_from(reflected[table_name]))
            or 0
        )
        for table_name, rows in captured.items()
        if table_name in reflected
    ):
        return
    for table_name in (
        SELECTION_TABLE,
        RELATION_TABLE,
        PAIR_TABLE,
        PROFILE_TABLE,
    ):
        table = reflected.get(table_name)
        if table is not None:
            bind.execute(table.delete())
    for table_name in (
        PROFILE_TABLE,
        PAIR_TABLE,
        RELATION_TABLE,
        SELECTION_TABLE,
    ):
        table = reflected.get(table_name)
        rows = captured.get(table_name, [])
        if table is None or not rows:
            continue
        column_names = set(table.c.keys())
        for row in rows:
            payload = {
                key: sa.null() if value is _SQL_NULL else value
                for key, value in row.items()
                if key in column_names
            }
            bind.execute(table.insert().values(**payload))


def _drop_extension(
    bind: sa.Connection,
    operations: Any,
    table_name: str,
    *,
    column_names: tuple[str, ...],
    check_names: tuple[str, ...],
    index_names: tuple[str, ...],
    replacement_checks: Mapping[str, str] | None = None,
) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    existing_indexes = {row["name"] for row in inspector.get_indexes(table_name)}
    for index_name in index_names:
        if index_name in existing_indexes:
            operations.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    existing_columns = {row["name"] for row in inspector.get_columns(table_name)}
    existing_checks = {
        row["name"]
        for row in inspector.get_check_constraints(table_name)
        if row.get("name")
    }
    drops = [name for name in check_names if name in existing_checks]
    columns = [name for name in column_names if name in existing_columns]
    replacement_checks = replacement_checks or {}
    if not drops and not columns and not replacement_checks:
        return
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with operations.batch_alter_table(table_name, recreate=recreate) as batch:
        for name in drops:
            batch.drop_constraint(name, type_="check")
        for name, condition in replacement_checks.items():
            if name not in drops and name in existing_checks:
                batch.drop_constraint(name, type_="check")
            batch.create_check_constraint(name, condition)
        for column_name in columns:
            batch.drop_column(column_name)


def _drop_index_if_present(
    bind: sa.Connection,
    operations: Any,
    table_name: str,
    index_name: str,
) -> None:
    if not sa.inspect(bind).has_table(table_name):
        return
    indexes = {row["name"] for row in sa.inspect(bind).get_indexes(table_name)}
    if index_name in indexes:
        operations.drop_index(index_name, table_name=table_name)
