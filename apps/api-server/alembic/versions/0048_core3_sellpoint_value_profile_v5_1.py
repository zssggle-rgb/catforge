"""core3 sellpoint value profile V5.1 persistence contract

Revision ID: 0048_core3_sellpoint_value_profile_v5_1
Revises: 0047_core3_competitor_profile_v1_1
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations


revision = "0048_core3_sellpoint_value_profile_v5_1"
down_revision = "0047_core3_competitor_profile_v1_1"
branch_labels = None
depends_on = None


V51_METHOD_VERSION = "sellpoint_value_profile_method_v5_1"
COMPETITOR_SOURCE_METHOD_VERSION = "competitor_profile_agent_snapshot_v2"

VERSION_TABLE = "core3_sellpoint_value_profile_version"
PROFILE_TABLE = "core3_sku_sellpoint_value_profile"
CANDIDATE_TABLE = "core3_sku_sellpoint_value_candidate"
ITEM_TABLE = "core3_sku_sellpoint_value_item"

VERSION_COLUMNS = (
    "source_competitor_profile_version_id",
    "source_competitor_profile_method_version",
    "source_competitor_profile_result_hash",
    "conclusion_available_count",
    "partial_conclusion_count",
    "no_conclusion_count",
    "invalid_count",
    "integrity_error_count",
)
PROFILE_COLUMNS = (
    "conclusion_status",
    "conclusion_available_count",
    "partial_conclusion_count",
    "no_conclusion_count",
    "invalid_count",
)
ITEM_COLUMNS = (
    "conclusion_status",
    "direct_market_result_available",
)

VERSION_CHECKS = {
    "ck_core3_spv_version_v51_available": (
        "conclusion_available_count IS NULL OR conclusion_available_count >= 0"
    ),
    "ck_core3_spv_version_v51_partial": (
        "partial_conclusion_count IS NULL OR partial_conclusion_count >= 0"
    ),
    "ck_core3_spv_version_v51_no_conclusion": (
        "no_conclusion_count IS NULL OR no_conclusion_count >= 0"
    ),
    "ck_core3_spv_version_v51_invalid": ("invalid_count IS NULL OR invalid_count >= 0"),
    "ck_core3_spv_version_v51_integrity": (
        "integrity_error_count IS NULL OR integrity_error_count >= 0"
    ),
    "ck_core3_spv_version_v51_complete": (
        f"method_version <> '{V51_METHOD_VERSION}' OR "
        "(source_competitor_profile_version_id IS NOT NULL "
        "AND source_competitor_profile_version_id <> '' "
        f"AND source_competitor_profile_method_version = "
        f"'{COMPETITOR_SOURCE_METHOD_VERSION}' "
        "AND source_competitor_profile_result_hash IS NOT NULL "
        "AND source_competitor_profile_result_hash <> '' "
        "AND conclusion_available_count IS NOT NULL "
        "AND partial_conclusion_count IS NOT NULL "
        "AND no_conclusion_count IS NOT NULL "
        "AND invalid_count IS NOT NULL "
        "AND integrity_error_count IS NOT NULL)"
    ),
    "ck_core3_spv_version_v51_distribution": (
        f"method_version <> '{V51_METHOD_VERSION}' OR "
        "(conclusion_available_count + partial_conclusion_count + "
        "no_conclusion_count + invalid_count <= sku_count "
        "AND invalid_count <= sku_count)"
    ),
}
PROFILE_CHECKS = {
    "ck_core3_spv_profile_v51_status": (
        "conclusion_status IS NULL OR conclusion_status in "
        "('conclusion_available','partial_conclusion','no_conclusion','invalid')"
    ),
    "ck_core3_spv_profile_v51_available": (
        "conclusion_available_count IS NULL OR conclusion_available_count >= 0"
    ),
    "ck_core3_spv_profile_v51_partial": (
        "partial_conclusion_count IS NULL OR partial_conclusion_count >= 0"
    ),
    "ck_core3_spv_profile_v51_no_conclusion": (
        "no_conclusion_count IS NULL OR no_conclusion_count >= 0"
    ),
    "ck_core3_spv_profile_v51_invalid": ("invalid_count IS NULL OR invalid_count >= 0"),
    "ck_core3_spv_profile_v51_complete": (
        f"method_version <> '{V51_METHOD_VERSION}' OR "
        "(conclusion_status IS NOT NULL "
        "AND conclusion_available_count IS NOT NULL "
        "AND partial_conclusion_count IS NOT NULL "
        "AND no_conclusion_count IS NOT NULL "
        "AND invalid_count IS NOT NULL)"
    ),
    "ck_core3_spv_profile_v51_invalid_state": (
        f"method_version <> '{V51_METHOD_VERSION}' OR "
        "((conclusion_status = 'invalid' AND invalid_count > 0) OR "
        "(conclusion_status <> 'invalid' AND invalid_count = 0))"
    ),
}
ITEM_CHECKS = {
    "ck_core3_spv_item_v51_status": (
        "conclusion_status IS NULL OR conclusion_status in "
        "('conclusion_available','partial_conclusion','no_conclusion','invalid')"
    ),
    "ck_core3_spv_item_v51_complete": (
        f"method_version <> '{V51_METHOD_VERSION}' OR "
        "(conclusion_status IS NOT NULL "
        "AND direct_market_result_available IS NOT NULL)"
    ),
}

VERSION_INDEXES = {
    "ix_core3_spv_version_competitor_source": (
        "project_id",
        "category_code",
        "source_competitor_profile_version_id",
    ),
}
PROFILE_INDEXES = {
    "ix_core3_spv_profile_v51_conclusion": (
        "project_id",
        "category_code",
        "batch_id",
        "conclusion_status",
    ),
}
ITEM_INDEXES = {
    "ix_core3_spv_item_v51_conclusion": (
        "sku_sellpoint_value_profile_id",
        "conclusion_status",
        "direct_market_result_available",
    ),
}

_SQL_NULL = object()


def upgrade() -> None:
    bind = op.get_bind()
    operations = _operations(bind)
    _require_complete_v5_schema(bind)
    sqlite_rows = _capture_sqlite_child_rows(bind)
    _clear_sqlite_child_rows(bind, sqlite_rows)

    _add_columns(bind, operations, VERSION_TABLE, _version_columns())
    _add_columns(bind, operations, PROFILE_TABLE, _profile_columns())
    _add_columns(bind, operations, ITEM_TABLE, _item_columns())
    _reconcile_checks(bind, operations, VERSION_TABLE, VERSION_CHECKS)
    _reconcile_checks(bind, operations, PROFILE_TABLE, PROFILE_CHECKS)
    _reconcile_checks(bind, operations, ITEM_TABLE, ITEM_CHECKS)
    _create_indexes(bind, operations, VERSION_TABLE, VERSION_INDEXES)
    _create_indexes(bind, operations, PROFILE_TABLE, PROFILE_INDEXES)
    _create_indexes(bind, operations, ITEM_TABLE, ITEM_INDEXES)

    _restore_sqlite_child_rows(bind, sqlite_rows)


def downgrade() -> None:
    bind = op.get_bind()
    blockers = _downgrade_blockers(bind)
    if blockers:
        raise RuntimeError(
            "sellpoint value V5.1 downgrade requires removing V5.1 drafts first; "
            + "; ".join(blockers)
        )

    operations = _operations(bind)
    sqlite_rows = _capture_sqlite_child_rows(bind)
    _clear_sqlite_child_rows(bind, sqlite_rows)
    _drop_extension(
        bind,
        operations,
        ITEM_TABLE,
        column_names=ITEM_COLUMNS,
        check_names=tuple(ITEM_CHECKS),
        index_names=tuple(ITEM_INDEXES),
    )
    _drop_extension(
        bind,
        operations,
        PROFILE_TABLE,
        column_names=PROFILE_COLUMNS,
        check_names=tuple(PROFILE_CHECKS),
        index_names=tuple(PROFILE_INDEXES),
    )
    _drop_extension(
        bind,
        operations,
        VERSION_TABLE,
        column_names=VERSION_COLUMNS,
        check_names=tuple(VERSION_CHECKS),
        index_names=tuple(VERSION_INDEXES),
    )
    _restore_sqlite_child_rows(bind, sqlite_rows)


def _version_columns() -> tuple[sa.Column[Any], ...]:
    return (
        sa.Column("source_competitor_profile_version_id", sa.String(120)),
        sa.Column("source_competitor_profile_method_version", sa.String(120)),
        sa.Column("source_competitor_profile_result_hash", sa.String(200)),
        sa.Column("conclusion_available_count", sa.Integer()),
        sa.Column("partial_conclusion_count", sa.Integer()),
        sa.Column("no_conclusion_count", sa.Integer()),
        sa.Column("invalid_count", sa.Integer()),
        sa.Column("integrity_error_count", sa.Integer()),
    )


def _profile_columns() -> tuple[sa.Column[Any], ...]:
    return (
        sa.Column("conclusion_status", sa.String(40)),
        sa.Column("conclusion_available_count", sa.Integer()),
        sa.Column("partial_conclusion_count", sa.Integer()),
        sa.Column("no_conclusion_count", sa.Integer()),
        sa.Column("invalid_count", sa.Integer()),
    )


def _item_columns() -> tuple[sa.Column[Any], ...]:
    return (
        sa.Column("conclusion_status", sa.String(40)),
        sa.Column("direct_market_result_available", sa.Boolean()),
    )


def _operations(bind: sa.Connection) -> Operations:
    return Operations(MigrationContext.configure(bind))


def _require_complete_v5_schema(bind: sa.Connection) -> None:
    required = {VERSION_TABLE, PROFILE_TABLE, CANDIDATE_TABLE, ITEM_TABLE}
    missing = sorted(required - set(sa.inspect(bind).get_table_names()))
    if missing:
        raise RuntimeError(
            "sellpoint value V5.1 requires the complete 0045 schema; missing: "
            + ", ".join(missing)
        )


def _add_columns(
    bind: sa.Connection,
    operations: Operations,
    table_name: str,
    columns: tuple[sa.Column[Any], ...],
) -> None:
    existing = {
        str(column["name"]) for column in sa.inspect(bind).get_columns(table_name)
    }
    for column in columns:
        if str(column.name) in existing:
            continue
        operations.add_column(table_name, column)
        existing.add(str(column.name))


def _reconcile_checks(
    bind: sa.Connection,
    operations: Operations,
    table_name: str,
    desired: Mapping[str, str],
) -> None:
    existing = {
        row["name"]
        for row in sa.inspect(bind).get_check_constraints(table_name)
        if row.get("name")
    }
    missing = [name for name in desired if name not in existing]
    if not missing:
        return
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with operations.batch_alter_table(table_name, recreate=recreate) as batch:
        for name in missing:
            batch.create_check_constraint(name, desired[name])


def _create_indexes(
    bind: sa.Connection,
    operations: Operations,
    table_name: str,
    desired: Mapping[str, tuple[str, ...]],
) -> None:
    existing = {row["name"] for row in sa.inspect(bind).get_indexes(table_name)}
    for name, columns in desired.items():
        if name not in existing:
            operations.create_index(name, table_name, list(columns), unique=False)


def _downgrade_blockers(bind: sa.Connection) -> list[str]:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    blockers: list[str] = []
    for table_name, extension_columns in (
        (VERSION_TABLE, VERSION_COLUMNS),
        (PROFILE_TABLE, PROFILE_COLUMNS),
        (ITEM_TABLE, ITEM_COLUMNS),
    ):
        if table_name not in tables:
            continue
        actual_columns = {
            str(column["name"]) for column in inspector.get_columns(table_name)
        }
        if "method_version" in actual_columns:
            count = _count_where(
                bind,
                table_name,
                "method_version = :method_version",
                {"method_version": V51_METHOD_VERSION},
            )
            if count:
                blockers.append(f"{table_name}.v5_1_rows={count}")
        present = [name for name in extension_columns if name in actual_columns]
        if not present:
            continue
        predicate = " OR ".join(f'"{name}" IS NOT NULL' for name in present)
        count = _count_where(bind, table_name, predicate, {})
        if count:
            blockers.append(f"{table_name}.v5_1_payload_rows={count}")
    return blockers


def _count_where(
    bind: sa.Connection,
    table_name: str,
    predicate: str,
    parameters: Mapping[str, Any],
) -> int:
    return int(
        bind.scalar(
            sa.text(f'SELECT COUNT(*) FROM "{table_name}" WHERE {predicate}'),
            parameters,
        )
        or 0
    )


def _capture_sqlite_child_rows(
    bind: sa.Connection,
) -> dict[str, list[dict[str, Any]]]:
    if bind.dialect.name != "sqlite":
        return {}
    tables = set(sa.inspect(bind).get_table_names())
    captured: dict[str, list[dict[str, Any]]] = {}
    for table_name in (PROFILE_TABLE, CANDIDATE_TABLE, ITEM_TABLE):
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
    for table_name in (ITEM_TABLE, CANDIDATE_TABLE, PROFILE_TABLE):
        table = reflected.get(table_name)
        if table is not None:
            bind.execute(table.delete())
    for table_name in (PROFILE_TABLE, CANDIDATE_TABLE, ITEM_TABLE):
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


def _clear_sqlite_child_rows(
    bind: sa.Connection,
    captured: Mapping[str, list[dict[str, Any]]],
) -> None:
    if not captured:
        return
    for table_name in (ITEM_TABLE, CANDIDATE_TABLE, PROFILE_TABLE):
        if captured.get(table_name) and sa.inspect(bind).has_table(table_name):
            table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
            bind.execute(table.delete())


def _drop_extension(
    bind: sa.Connection,
    operations: Operations,
    table_name: str,
    *,
    column_names: tuple[str, ...],
    check_names: tuple[str, ...],
    index_names: tuple[str, ...],
) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return
    existing_indexes = {row["name"] for row in inspector.get_indexes(table_name)}
    for index_name in index_names:
        if index_name in existing_indexes:
            operations.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    existing_columns = {str(row["name"]) for row in inspector.get_columns(table_name)}
    existing_checks = {
        row["name"]
        for row in inspector.get_check_constraints(table_name)
        if row.get("name")
    }
    columns = [name for name in column_names if name in existing_columns]
    checks = [name for name in check_names if name in existing_checks]
    if not columns and not checks:
        return
    recreate = "always" if bind.dialect.name == "sqlite" else "auto"
    with operations.batch_alter_table(table_name, recreate=recreate) as batch:
        for name in checks:
            batch.drop_constraint(name, type_="check")
        for name in columns:
            batch.drop_column(name)
