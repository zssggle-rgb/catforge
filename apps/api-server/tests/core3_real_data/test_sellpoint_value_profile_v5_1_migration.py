from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0048_core3_sellpoint_value_profile_v5_1.py"
)
VERSION_TABLE = "core3_sellpoint_value_profile_version"
PROFILE_TABLE = "core3_sku_sellpoint_value_profile"
CANDIDATE_TABLE = "core3_sku_sellpoint_value_candidate"
ITEM_TABLE = "core3_sku_sellpoint_value_item"


class BoundOp:
    def __init__(self, bind: Any) -> None:
        self.bind = bind

    def get_bind(self) -> Any:
        return self.bind


def _migration():
    spec = importlib.util.spec_from_file_location(
        "core3_sellpoint_value_profile_v5_1_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine() -> sa.Engine:
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _create_schema(connection: sa.Connection) -> None:
    entities.CategoryProject.__table__.create(bind=connection, checkfirst=True)
    entities.Core3V2PipelineRun.__table__.create(bind=connection, checkfirst=True)
    entities.Core3V2ModuleRun.__table__.create(bind=connection, checkfirst=True)
    entities.Core3SourceBatch.__table__.create(bind=connection, checkfirst=True)
    for table in (
        entities.Core3SellpointValueProfileVersion.__table__,
        entities.Core3SkuSellpointValueProfile.__table__,
        entities.Core3SkuSellpointValueCandidate.__table__,
        entities.Core3SkuSellpointValueItem.__table__,
    ):
        table.create(bind=connection, checkfirst=True)


def _seed_v5_history(connection: sa.Connection) -> None:
    session = Session(bind=connection, autoflush=False, future=True)
    session.add(
        entities.CategoryProject(
            project_id="project-tv",
            name="TV project",
            category_code="TV",
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id="batch-tv",
            project_id="project-tv",
            category_code="TV",
            source_system="fixture",
            source_database="fixture",
            source_tables=[],
            ruleset_version="rules-v1",
            module_version="module-v1",
            hash_version="hash-v1",
            scan_started_at=datetime.now(timezone.utc),
            status="completed",
        )
    )
    session.flush()
    common = {
        "sellpoint_value_profile_version_id": "spv-version-v5",
        "project_id": "project-tv",
        "category_code": "TV",
        "batch_id": "batch-tv",
        "product_category": "TV",
        "profile_version": "spv-v5-history",
        "schema_version": SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
        "rule_version": SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        "method_version": SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        "input_fingerprint": "history-input",
        "result_hash": "history-result",
    }
    version = entities.Core3SellpointValueProfileVersion(
        **{
            key: value
            for key, value in common.items()
            if key != "sellpoint_value_profile_version_id"
        },
        sellpoint_value_profile_version_id="spv-version-v5",
        candidate_universe_fingerprint="history-candidates",
    )
    profile = entities.Core3SkuSellpointValueProfile(
        **common,
        sku_sellpoint_value_profile_id="spv-profile-v5",
        sku_code="TV00029112",
        display_name_cn="海信 65E7Q",
        analysis_state="partial",
        profile_confidence=Decimal("0.5971"),
    )
    candidate = entities.Core3SkuSellpointValueCandidate(
        **common,
        sku_sellpoint_value_candidate_id="spv-candidate-v5",
        sku_sellpoint_value_profile_id="spv-profile-v5",
        target_sku_code="TV00029112",
        candidate_sku_code="TV00027801",
        pool_type="reference",
        primary_relation_type="same_size_market",
        eligibility_status="limited",
        confidence=Decimal("0.7000"),
    )
    item = entities.Core3SkuSellpointValueItem(
        **common,
        sku_sellpoint_value_item_id="spv-item-v5",
        sku_sellpoint_value_profile_id="spv-profile-v5",
        sku_code="TV00029112",
        battlefield_code="BF-PICTURE",
        value_bundle_code="picture",
        value_bundle_name_cn="画质价值",
        normalized_bundle_code="picture",
        perceived_outcome_cn="强光清晰、暗场有层次",
        evidence_boundary_cn="观察性市场比较",
        confidence=Decimal("0.8000"),
    )
    session.add_all([version, profile])
    session.flush()
    session.add_all([candidate, item])
    session.flush()
    session.close()


def _column_names(connection: sa.Connection, table_name: str) -> set[str]:
    return {
        str(column["name"]) for column in sa.inspect(connection).get_columns(table_name)
    }


def _check_names(connection: sa.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in sa.inspect(connection).get_check_constraints(table_name)
        if row.get("name")
    }


def _index_names(connection: sa.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in sa.inspect(connection).get_indexes(table_name)
        if row.get("name")
    }


def _raw_state(
    connection: sa.Connection,
    table_name: str,
    *,
    exclude: set[str],
) -> list[dict[str, Any]]:
    columns = [
        str(row["name"])
        for row in sa.inspect(connection).get_columns(table_name)
        if row["name"] not in exclude
    ]
    select_columns = ", ".join(f'"{name}"' for name in columns)
    primary_key = sa.inspect(connection).get_pk_constraint(table_name)[
        "constrained_columns"
    ]
    order_by = ", ".join(f'"{name}"' for name in primary_key)
    rows = connection.exec_driver_sql(
        f'SELECT {select_columns} FROM "{table_name}" ORDER BY {order_by}'
    ).mappings()
    return [dict(row) for row in rows]


def _run_migration(connection: sa.Connection, action: str):
    migration = _migration()
    original_op = migration.op
    migration.op = BoundOp(connection)
    try:
        getattr(migration, action)()
    finally:
        migration.op = original_op
    return migration


def _assert_integrity_error(
    connection: sa.Connection,
    statement: sa.Executable,
) -> None:
    savepoint = connection.begin_nested()
    with pytest.raises(IntegrityError):
        connection.execute(statement)
    savepoint.rollback()


def _normalized_sql(value: Any) -> str:
    return " ".join(str(value).lower().split())


def _type_signature(column: sa.Column[Any]) -> tuple[Any, ...]:
    return (
        column.type._type_affinity,
        getattr(column.type, "length", None),
        getattr(column.type, "precision", None),
        getattr(column.type, "scale", None),
        column.nullable,
    )


def test_entities_and_migration_expose_only_the_frozen_v51_extensions() -> None:
    migration = _migration()
    assert migration.revision == "0048_core3_sellpoint_value_profile_v5_1"
    assert migration.down_revision == "0047_core3_competitor_profile_v1_1"

    expected = {
        VERSION_TABLE: (
            set(migration.VERSION_COLUMNS),
            set(migration.VERSION_CHECKS),
            set(migration.VERSION_INDEXES),
        ),
        PROFILE_TABLE: (
            set(migration.PROFILE_COLUMNS),
            set(migration.PROFILE_CHECKS),
            set(migration.PROFILE_INDEXES),
        ),
        ITEM_TABLE: (
            set(migration.ITEM_COLUMNS),
            set(migration.ITEM_CHECKS),
            set(migration.ITEM_INDEXES),
        ),
    }
    for table_name, (columns, checks, indexes) in expected.items():
        table = entities.Base.metadata.tables[table_name]
        assert columns <= set(table.c.keys())
        entity_checks = {
            str(constraint.name): _normalized_sql(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, sa.CheckConstraint) and constraint.name
        }
        assert checks <= set(entity_checks)
        assert indexes <= {str(index.name) for index in table.indexes}
        desired_checks = {
            VERSION_TABLE: migration.VERSION_CHECKS,
            PROFILE_TABLE: migration.PROFILE_CHECKS,
            ITEM_TABLE: migration.ITEM_CHECKS,
        }[table_name]
        for check_name, condition in desired_checks.items():
            assert entity_checks[check_name] == _normalized_sql(condition)

    migration_columns = {
        VERSION_TABLE: migration._version_columns(),
        PROFILE_TABLE: migration._profile_columns(),
        ITEM_TABLE: migration._item_columns(),
    }
    for table_name, columns in migration_columns.items():
        table = entities.Base.metadata.tables[table_name]
        for column in columns:
            assert _type_signature(column) == _type_signature(table.c[column.name])

    source_column = entities.Core3SellpointValueProfileVersion.__table__.c[
        "source_competitor_profile_version_id"
    ]
    assert not source_column.foreign_keys
    assert not set(migration.PROFILE_COLUMNS) & set(
        entities.Core3SkuSellpointValueCandidate.__table__.c.keys()
    )


def test_sqlite_v5_history_survives_upgrade_downgrade_and_idempotent_replay() -> None:
    migration = _migration()
    extension_columns = {
        VERSION_TABLE: set(migration.VERSION_COLUMNS),
        PROFILE_TABLE: set(migration.PROFILE_COLUMNS),
        CANDIDATE_TABLE: set(),
        ITEM_TABLE: set(migration.ITEM_COLUMNS),
    }
    engine = _engine()
    with engine.begin() as connection:
        _create_schema(connection)
        _seed_v5_history(connection)
        before = {
            table_name: _raw_state(
                connection,
                table_name,
                exclude=extension_columns[table_name],
            )
            for table_name in extension_columns
        }
        for table_name, columns in extension_columns.items():
            if columns:
                assert (
                    connection.scalar(
                        sa.text(
                            f'SELECT COUNT(*) FROM "{table_name}" WHERE '
                            + " OR ".join(f'"{name}" IS NOT NULL' for name in columns)
                        )
                    )
                    == 0
                )

        _run_migration(connection, "downgrade")
        for table_name, columns in extension_columns.items():
            assert not columns & _column_names(connection, table_name)
        after_first_downgrade = {
            table_name: _raw_state(connection, table_name, exclude=set())
            for table_name in extension_columns
        }
        assert after_first_downgrade == before

        upgraded = _run_migration(connection, "upgrade")
        _run_migration(connection, "upgrade")
        for table_name, columns in extension_columns.items():
            assert columns <= _column_names(connection, table_name)
        assert set(upgraded.VERSION_CHECKS) <= _check_names(connection, VERSION_TABLE)
        assert set(upgraded.PROFILE_CHECKS) <= _check_names(connection, PROFILE_TABLE)
        assert set(upgraded.ITEM_CHECKS) <= _check_names(connection, ITEM_TABLE)
        assert set(upgraded.VERSION_INDEXES) <= _index_names(connection, VERSION_TABLE)
        assert set(upgraded.PROFILE_INDEXES) <= _index_names(connection, PROFILE_TABLE)
        assert set(upgraded.ITEM_INDEXES) <= _index_names(connection, ITEM_TABLE)
        assert "uq_core3_spv_current_published" in _index_names(
            connection, VERSION_TABLE
        )
        after_upgrade = {
            table_name: _raw_state(
                connection,
                table_name,
                exclude=extension_columns[table_name],
            )
            for table_name in extension_columns
        }
        assert after_upgrade == before

        _run_migration(connection, "downgrade")
        after_second_downgrade = {
            table_name: _raw_state(connection, table_name, exclude=set())
            for table_name in extension_columns
        }
        assert after_second_downgrade == before
    engine.dispose()


def test_v51_constraints_current_isolation_and_downgrade_blocker() -> None:
    migration = _migration()
    engine = _engine()
    with engine.begin() as connection:
        _create_schema(connection)
        _seed_v5_history(connection)

        _assert_integrity_error(
            connection,
            sa.text(
                f"UPDATE {VERSION_TABLE} SET method_version = :method_version "
                "WHERE sellpoint_value_profile_version_id = 'spv-version-v5'"
            ).bindparams(method_version=migration.V51_METHOD_VERSION),
        )
        connection.execute(
            sa.text(
                f"UPDATE {VERSION_TABLE} SET "
                "method_version = :method_version, "
                "source_competitor_profile_version_id = 'cp-version', "
                "source_competitor_profile_method_version = :source_method, "
                "source_competitor_profile_result_hash = 'cp-version-hash', "
                "sku_count = 1, conclusion_available_count = 0, "
                "partial_conclusion_count = 1, no_conclusion_count = 0, "
                "invalid_count = 0, integrity_error_count = 0 "
                "WHERE sellpoint_value_profile_version_id = 'spv-version-v5'"
            ),
            {
                "method_version": migration.V51_METHOD_VERSION,
                "source_method": migration.COMPETITOR_SOURCE_METHOD_VERSION,
            },
        )

        _assert_integrity_error(
            connection,
            sa.text(
                f"UPDATE {PROFILE_TABLE} SET method_version = :method_version "
                "WHERE sku_sellpoint_value_profile_id = 'spv-profile-v5'"
            ).bindparams(method_version=migration.V51_METHOD_VERSION),
        )
        connection.execute(
            sa.text(
                f"UPDATE {PROFILE_TABLE} SET method_version = :method_version, "
                "conclusion_status = 'partial_conclusion', "
                "conclusion_available_count = 0, partial_conclusion_count = 1, "
                "no_conclusion_count = 0, invalid_count = 0 "
                "WHERE sku_sellpoint_value_profile_id = 'spv-profile-v5'"
            ),
            {"method_version": migration.V51_METHOD_VERSION},
        )
        _assert_integrity_error(
            connection,
            sa.text(
                f"UPDATE {PROFILE_TABLE} SET conclusion_status = 'invalid' "
                "WHERE sku_sellpoint_value_profile_id = 'spv-profile-v5'"
            ),
        )

        _assert_integrity_error(
            connection,
            sa.text(
                f"UPDATE {ITEM_TABLE} SET method_version = :method_version "
                "WHERE sku_sellpoint_value_item_id = 'spv-item-v5'"
            ).bindparams(method_version=migration.V51_METHOD_VERSION),
        )
        connection.execute(
            sa.text(
                f"UPDATE {ITEM_TABLE} SET method_version = :method_version, "
                "conclusion_status = 'conclusion_available', "
                "direct_market_result_available = 1 "
                "WHERE sku_sellpoint_value_item_id = 'spv-item-v5'"
            ),
            {"method_version": migration.V51_METHOD_VERSION},
        )

        version = sa.Table(VERSION_TABLE, sa.MetaData(), autoload_with=connection)
        first = dict(
            connection.execute(
                sa.select(version).where(
                    version.c.sellpoint_value_profile_version_id == "spv-version-v5"
                )
            )
            .mappings()
            .one()
        )
        connection.execute(
            version.update()
            .where(version.c.sellpoint_value_profile_version_id == "spv-version-v5")
            .values(release_status="published", is_current=True)
        )
        first.update(
            sellpoint_value_profile_version_id="spv-version-v51-duplicate",
            profile_version="spv-v51-duplicate",
            rule_version="rule-v51-duplicate",
            input_fingerprint="duplicate-input",
            result_hash="duplicate-result",
            release_status="published",
            is_current=True,
        )
        _assert_integrity_error(connection, version.insert().values(**first))

        columns_before = _column_names(connection, VERSION_TABLE)
        checks_before = _check_names(connection, VERSION_TABLE)
        indexes_before = _index_names(connection, VERSION_TABLE)
        original_op = migration.op
        migration.op = BoundOp(connection)
        try:
            with pytest.raises(RuntimeError, match="removing V5.1 drafts first"):
                migration.downgrade()
        finally:
            migration.op = original_op
        assert _column_names(connection, VERSION_TABLE) == columns_before
        assert _check_names(connection, VERSION_TABLE) == checks_before
        assert _index_names(connection, VERSION_TABLE) == indexes_before
    engine.dispose()


def test_v51_tables_and_indexes_compile_for_sqlite_and_postgresql() -> None:
    migration = _migration()
    tables = {
        VERSION_TABLE: entities.Core3SellpointValueProfileVersion.__table__,
        PROFILE_TABLE: entities.Core3SkuSellpointValueProfile.__table__,
        ITEM_TABLE: entities.Core3SkuSellpointValueItem.__table__,
    }
    expected_checks = {
        VERSION_TABLE: set(migration.VERSION_CHECKS),
        PROFILE_TABLE: set(migration.PROFILE_CHECKS),
        ITEM_TABLE: set(migration.ITEM_CHECKS),
    }
    expected_indexes = {
        VERSION_TABLE: set(migration.VERSION_INDEXES),
        PROFILE_TABLE: set(migration.PROFILE_INDEXES),
        ITEM_TABLE: set(migration.ITEM_INDEXES),
    }
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        for table_name, table in tables.items():
            table_ddl = str(CreateTable(table).compile(dialect=dialect))
            for check_name in expected_checks[table_name]:
                assert check_name in table_ddl
            for index in table.indexes:
                if str(index.name) in expected_indexes[table_name]:
                    index_ddl = str(CreateIndex(index).compile(dialect=dialect))
                    assert str(index.name) in index_ddl


def test_upgrade_refuses_partial_v5_schema_before_any_v51_ddl() -> None:
    engine = _engine()
    with engine.begin() as connection:
        entities.CategoryProject.__table__.create(bind=connection)
        entities.Core3V2PipelineRun.__table__.create(bind=connection)
        entities.Core3V2ModuleRun.__table__.create(bind=connection)
        entities.Core3SourceBatch.__table__.create(bind=connection)
        entities.Core3SellpointValueProfileVersion.__table__.create(bind=connection)
        columns_before = _column_names(connection, VERSION_TABLE)
        checks_before = _check_names(connection, VERSION_TABLE)
        indexes_before = _index_names(connection, VERSION_TABLE)
        migration = _migration()
        original_op = migration.op
        migration.op = BoundOp(connection)
        try:
            with pytest.raises(RuntimeError, match=CANDIDATE_TABLE):
                migration.upgrade()
        finally:
            migration.op = original_op
        assert _column_names(connection, VERSION_TABLE) == columns_before
        assert _check_names(connection, VERSION_TABLE) == checks_before
        assert _index_names(connection, VERSION_TABLE) == indexes_before
    engine.dispose()
