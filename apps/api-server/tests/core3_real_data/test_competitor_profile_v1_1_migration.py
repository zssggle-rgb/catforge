from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.pool import StaticPool

from app.models import entities


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0047_core3_competitor_profile_v1_1.py"
)
V1_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0046_core3_competitor_profile.py"
)
V1_MIGRATION_TEST_PATH = (
    Path(__file__).resolve().parent / "test_competitor_profile_migration.py"
)

VERSION_TABLE = "core3_competitor_profile_version"
SNAPSHOT_TABLE = "core3_competitor_profile_sku_snapshot"
PROFILE_TABLE = "core3_sku_competitor_profile"
PAIR_TABLE = "core3_sku_competitor_profile_pair"
RELATION_TABLE = "core3_sku_competitor_profile_relation"
SELECTION_TABLE = "core3_sku_competitor_profile_selection"


class BoundOp:
    def __init__(self, bind: Any) -> None:
        self.bind = bind

    def get_bind(self) -> Any:
        return self.bind


def _migration():
    spec = importlib.util.spec_from_file_location(
        "core3_competitor_profile_v1_1_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v1_migration():
    spec = importlib.util.spec_from_file_location(
        "core3_competitor_profile_v1_migration_for_v11",
        V1_MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v1_migration_fixture_module():
    spec = importlib.util.spec_from_file_location(
        "core3_competitor_profile_v1_migration_fixture",
        V1_MIGRATION_TEST_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine():
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _create_v1_schema(connection: sa.Connection) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "category_project",
        metadata,
        sa.Column("project_id", sa.String(36), primary_key=True),
    )
    version = sa.Table(
        VERSION_TABLE,
        metadata,
        sa.Column("competitor_profile_version_id", sa.String(120), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("category_code", sa.String(40), nullable=False),
        sa.Column("release_scope_key", sa.String(200), nullable=False),
        sa.Column("profile_version", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.String(160), nullable=False),
        sa.Column("rule_version", sa.String(160), nullable=False),
        sa.Column("method_version", sa.String(160), nullable=False),
    )
    profile = sa.Table(
        PROFILE_TABLE,
        metadata,
        sa.Column("sku_competitor_profile_id", sa.String(120), primary_key=True),
        sa.Column("competitor_profile_version_id", sa.String(120), nullable=False),
        sa.Column("target_sku_code", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.String(160), nullable=False),
    )
    pair = sa.Table(
        PAIR_TABLE,
        metadata,
        sa.Column("sku_competitor_profile_pair_id", sa.String(120), primary_key=True),
        sa.Column("sku_competitor_profile_id", sa.String(120), nullable=False),
        sa.Column("competitor_profile_version_id", sa.String(120), nullable=False),
        sa.Column("target_sku_code", sa.String(160), nullable=False),
        sa.Column("candidate_sku_code", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.String(160), nullable=False),
        sa.Column("candidate_status", sa.String(60), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False, default=False),
        sa.CheckConstraint(
            "target_sku_code <> candidate_sku_code",
            name="ck_core3_cp_pair_distinct",
        ),
        sa.CheckConstraint(
            "NOT selected OR candidate_status in ('eligible','limited')",
            name="ck_core3_cp_pair_selected_status",
        ),
    )
    relation = sa.Table(
        RELATION_TABLE,
        metadata,
        sa.Column(
            "sku_competitor_profile_relation_id", sa.String(120), primary_key=True
        ),
        sa.Column("sku_competitor_profile_pair_id", sa.String(120), nullable=False),
        sa.Column("competitor_profile_version_id", sa.String(120), nullable=False),
        sa.Column("relation_code", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(160), nullable=False),
        sa.Column("relation_status", sa.String(40), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, default=False),
        sa.CheckConstraint(
            "NOT is_primary OR relation_status in ('passed','limited')",
            name="ck_core3_cp_relation_primary",
        ),
    )
    selection = sa.Table(
        SELECTION_TABLE,
        metadata,
        sa.Column(
            "sku_competitor_profile_selection_id",
            sa.String(120),
            primary_key=True,
        ),
        sa.Column("sku_competitor_profile_id", sa.String(120), nullable=False),
        sa.Column("sku_competitor_profile_pair_id", sa.String(120), nullable=False),
        sa.Column("competitor_profile_version_id", sa.String(120), nullable=False),
        sa.Column("target_sku_code", sa.String(160), nullable=False),
        sa.Column("selection_rank", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(160), nullable=False),
    )
    metadata.create_all(connection)
    connection.execute(
        metadata.tables["category_project"].insert().values(project_id="project-tv")
    )
    assert version is not None
    assert profile is not None
    assert pair is not None
    assert relation is not None
    assert selection is not None


def _create_full_dependencies(connection: sa.Connection) -> None:
    for table in (
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
    ):
        table.create(bind=connection, checkfirst=True)


def _insert_version(
    connection: sa.Connection,
    *,
    version_id: str = "version-v1",
    schema_version: str = "sku_competitor_decision_profile_v1",
    rule_version: str = "competitor_profile_materializer_v1",
    method_version: str = "competitor_profile_method_v1",
) -> None:
    connection.execute(
        sa.text(
            f"INSERT INTO {VERSION_TABLE} "
            "(competitor_profile_version_id, project_id, category_code, "
            "release_scope_key, profile_version, schema_version, rule_version, "
            "method_version) VALUES "
            "(:version_id, 'project-tv', 'TV', 'scope-tv', :profile_version, "
            ":schema_version, :rule_version, :method_version)"
        ),
        {
            "version_id": version_id,
            "profile_version": f"profile-{version_id}",
            "schema_version": schema_version,
            "rule_version": rule_version,
            "method_version": method_version,
        },
    )


def _insert_v1_rows(connection: sa.Connection) -> None:
    _insert_version(connection)
    connection.execute(
        sa.text(
            f"INSERT INTO {PROFILE_TABLE} VALUES "
            "('profile-v1', 'version-v1', 'TV-TARGET', "
            "'sku_competitor_decision_profile_v1')"
        )
    )
    connection.execute(
        sa.text(
            f"INSERT INTO {PAIR_TABLE} VALUES "
            "('pair-v1', 'profile-v1', 'version-v1', 'TV-TARGET', 'TV-C1', "
            "'sku_competitor_decision_profile_v1', 'eligible', 1)"
        )
    )
    connection.execute(
        sa.text(
            f"INSERT INTO {RELATION_TABLE} VALUES "
            "('relation-v1', 'pair-v1', 'version-v1', 'direct_substitute', "
            "'sku_competitor_decision_profile_v1', 'passed', 1)"
        )
    )
    connection.execute(
        sa.text(
            f"INSERT INTO {SELECTION_TABLE} VALUES "
            "('selection-v1', 'profile-v1', 'pair-v1', 'version-v1', "
            "'TV-TARGET', 1, 'sku_competitor_decision_profile_v1')"
        )
    )


def _full_v1_relation_values() -> dict[str, Any]:
    return {
        "sku_competitor_profile_relation_id": "relation-1",
        "sku_competitor_profile_pair_id": "pair-1",
        "competitor_profile_version_id": "version-1",
        "project_id": "project-tv",
        "category_code": "TV",
        "product_category": "TV",
        "storage_batch_id": "batch-tv",
        "release_scope_key": "scope-tv",
        "profile_version": "competitor-v1",
        "schema_version": "schema-v1",
        "rule_version": "rule-v1",
        "method_version": "method-v1",
        "target_sku_code": "TV-TARGET",
        "candidate_sku_code": "TV-C1",
        "relation_code": "direct_substitute",
        "relation_status": "passed",
        "is_primary": True,
        "confidence_level": "high",
        "input_fingerprint": "relation-input",
        "result_hash": "relation-result",
    }


def _full_v1_selection_values() -> dict[str, Any]:
    return {
        "sku_competitor_profile_selection_id": "selection-1",
        "sku_competitor_profile_id": "profile-1",
        "sku_competitor_profile_pair_id": "pair-1",
        "competitor_profile_version_id": "version-1",
        "project_id": "project-tv",
        "category_code": "TV",
        "product_category": "TV",
        "storage_batch_id": "batch-tv",
        "release_scope_key": "scope-tv",
        "profile_version": "competitor-v1",
        "schema_version": "schema-v1",
        "rule_version": "rule-v1",
        "method_version": "method-v1",
        "target_sku_code": "TV-TARGET",
        "candidate_sku_code": "TV-C1",
        "selection_rank": 1,
        "primary_decision_topic": "purchase_choice",
        "primary_relation_code": "direct_substitute",
        "selection_reason_cn": "reason",
        "independent_information_reason_cn": "independent",
        "confidence_level": "high",
        "input_fingerprint": "selection-input",
        "result_hash": "selection-result",
    }


def _upgrade(connection: sa.Connection):
    migration = _migration()
    migration.op = BoundOp(connection)
    migration.upgrade()
    return migration


def _column_names(connection: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(connection).get_columns(table_name)}


def _check_names(connection: sa.Connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in sa.inspect(connection).get_check_constraints(table_name)
        if row.get("name")
    }


def _normalized_sql(value: Any) -> str:
    return " ".join(str(value).lower().split())


def _type_signature(column: sa.Column[Any]) -> tuple[Any, ...]:
    column_type = column.type
    return (
        column_type._type_affinity,
        getattr(column_type, "length", None),
        getattr(column_type, "precision", None),
        getattr(column_type, "scale", None),
    )


def _sqlite_table_state(
    connection: sa.Connection,
    table_name: str,
) -> list[dict[str, Any]]:
    table = sa.Table(table_name, sa.MetaData(), autoload_with=connection)
    json_columns = {
        column.name for column in table.c if isinstance(column.type, sa.JSON)
    }
    primary_key = [column.name for column in table.primary_key.columns]
    order_sql = ", ".join(f'"{column}"' for column in primary_key)
    rows = connection.execute(
        sa.text(f'SELECT * FROM "{table_name}" ORDER BY {order_sql}')
    ).mappings()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        values: dict[str, Any] = {}
        for key, value in row.items():
            if key not in json_columns:
                values[key] = value
            elif value is None:
                values[key] = ("sql_null", None)
            else:
                decoded = json.loads(value)
                null_kind = "json_null" if decoded is None else "json_value"
                values[key] = (null_kind, decoded)
        normalized.append(values)
    return normalized


def test_revision_chain_upgrade_preserves_v1_and_downgrade_allows_only_v1() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        _insert_v1_rows(connection)
        migration = _upgrade(connection)
        assert migration.revision == "0047_core3_competitor_profile_v1_1"
        assert migration.down_revision == "0046_core3_competitor_profile"

        inspector = sa.inspect(connection)
        assert SNAPSHOT_TABLE in inspector.get_table_names()
        assert set(migration.PROFILE_COLUMNS) <= _column_names(
            connection, PROFILE_TABLE
        )
        assert set(migration.PAIR_COLUMNS) <= _column_names(connection, PAIR_TABLE)
        assert set(migration.RELATION_COLUMNS) <= _column_names(
            connection, RELATION_TABLE
        )
        assert set(migration.SELECTION_COLUMNS) <= _column_names(
            connection, SELECTION_TABLE
        )
        assert set(migration.PROFILE_CHECKS) <= _check_names(connection, PROFILE_TABLE)
        assert set(migration.PAIR_CHECKS) <= _check_names(connection, PAIR_TABLE)
        assert set(migration.RELATION_CHECKS) <= _check_names(
            connection, RELATION_TABLE
        )
        assert set(migration.SELECTION_CHECKS) <= _check_names(
            connection, SELECTION_TABLE
        )

        migration.downgrade()
        inspector = sa.inspect(connection)
        assert SNAPSHOT_TABLE not in inspector.get_table_names()
        assert not set(migration.PROFILE_COLUMNS) & _column_names(
            connection, PROFILE_TABLE
        )
        assert not set(migration.PAIR_COLUMNS) & _column_names(connection, PAIR_TABLE)
        assert connection.scalar(sa.text(f"SELECT COUNT(*) FROM {VERSION_TABLE}")) == 1
        for table_name in (
            PROFILE_TABLE,
            PAIR_TABLE,
            RELATION_TABLE,
            SELECTION_TABLE,
        ):
            assert connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table_name}")) == 1
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {PAIR_TABLE} VALUES "
                    "('pair-invalid', 'profile-v1', 'version-v1', 'TV-TARGET', "
                    "'TV-C2', 'sku_competitor_decision_profile_v1', "
                    "'reference_only', 1)"
                )
            )
    engine.dispose()


def test_frozen_0046_shapes_match_the_v1_portion_of_current_entities() -> None:
    v1_migration = _v1_migration()
    v11_migration = _migration()
    current_tables = {
        VERSION_TABLE: entities.Core3CompetitorProfileVersion.__table__,
        PROFILE_TABLE: entities.Core3SkuCompetitorProfile.__table__,
        PAIR_TABLE: entities.Core3SkuCompetitorProfilePair.__table__,
        RELATION_TABLE: entities.Core3SkuCompetitorProfileRelation.__table__,
        SELECTION_TABLE: entities.Core3SkuCompetitorProfileSelection.__table__,
    }
    extension_columns = {
        VERSION_TABLE: set(),
        PROFILE_TABLE: set(v11_migration.PROFILE_COLUMNS),
        PAIR_TABLE: set(v11_migration.PAIR_COLUMNS),
        RELATION_TABLE: set(v11_migration.RELATION_COLUMNS),
        SELECTION_TABLE: set(v11_migration.SELECTION_COLUMNS),
    }
    extension_checks = {
        VERSION_TABLE: set(),
        PROFILE_TABLE: set(v11_migration.PROFILE_CHECKS),
        PAIR_TABLE: set(v11_migration.PAIR_CHECKS)
        - {
            "ck_core3_cp_pair_distinct",
            "ck_core3_cp_pair_selected_status",
        },
        RELATION_TABLE: set(v11_migration.RELATION_CHECKS)
        - {"ck_core3_cp_relation_primary"},
        SELECTION_TABLE: set(v11_migration.SELECTION_CHECKS),
    }
    extension_indexes = {
        VERSION_TABLE: {v11_migration.VERSION_SCOPE_INDEX},
        PROFILE_TABLE: {"ix_core3_cp_profile_v11_read"},
        PAIR_TABLE: {
            "ix_core3_cp_pair_v11_scope",
            "ix_core3_cp_pair_v11_candidate",
        },
        RELATION_TABLE: {"ix_core3_cp_relation_v11_status"},
        SELECTION_TABLE: {"ix_core3_cp_selection_v11_read"},
    }

    for frozen, current in zip(
        v1_migration.PROFILE_TABLES,
        current_tables.values(),
        strict=True,
    ):
        expected_columns = set(current.c.keys()) - extension_columns[current.name]
        assert set(frozen.c.keys()) == expected_columns
        for column_name in expected_columns:
            assert _type_signature(frozen.c[column_name]) == _type_signature(
                current.c[column_name]
            )
            assert frozen.c[column_name].nullable == current.c[column_name].nullable
            assert (
                frozen.c[column_name].primary_key == current.c[column_name].primary_key
            )

        frozen_checks = {
            constraint.name
            for constraint in frozen.constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        current_v1_checks = {
            constraint.name
            for constraint in current.constraints
            if isinstance(constraint, sa.CheckConstraint)
        } - extension_checks[current.name]
        assert frozen_checks == current_v1_checks
        assert {index.name for index in frozen.indexes} == {
            index.name for index in current.indexes
        } - extension_indexes[current.name]


def test_frozen_migration_tables_compile_for_sqlite_and_postgresql() -> None:
    v1_migration = _v1_migration()
    v11_migration = _migration()
    tables = (*v1_migration.PROFILE_TABLES, v11_migration._snapshot_table())
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        for table in tables:
            assert str(CreateTable(table).compile(dialect=dialect))
            for index in table.indexes:
                assert str(CreateIndex(index).compile(dialect=dialect))


def test_deployed_0046_ddl_has_frozen_sqlite_and_postgresql_golden_hashes() -> (
    None
):
    tables = _v1_migration().PROFILE_TABLES
    expected = {
        "sqlite": "b6255c8a223fe0f52baa24c4acce7e23f86bb097fc9b1e377cd2ac5f331f2cae",
        "postgresql": "5d1782ea8bf178a05c819a785ab9773341e2c978a2a446c6b98f80048b12d174",
    }
    for dialect_name, dialect in (
        ("sqlite", sqlite.dialect()),
        ("postgresql", postgresql.dialect()),
    ):
        statements: list[str] = []
        for table in sorted(tables, key=lambda row: row.name):
            statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
            statements.extend(
                str(CreateIndex(index).compile(dialect=dialect)).strip()
                for index in sorted(table.indexes, key=lambda row: str(row.name))
            )
        canonical_ddl = "\n-- statement --\n".join(statements).encode("utf-8")
        assert hashlib.sha256(canonical_ddl).hexdigest() == expected[dialect_name]


def test_upgrade_refuses_partial_0046_schema_before_any_v11_ddl() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        connection.execute(sa.text(f"DROP TABLE {SELECTION_TABLE}"))
        migration = _migration()
        migration.op = BoundOp(connection)
        with pytest.raises(RuntimeError, match=SELECTION_TABLE):
            migration.upgrade()
        assert SNAPSHOT_TABLE not in sa.inspect(connection).get_table_names()
        assert "uq_core3_cp_version_scope_identity" not in {
            row["name"] for row in sa.inspect(connection).get_indexes(VERSION_TABLE)
        }
    engine.dispose()


def test_real_0046_to_0047_chain_is_idempotent_and_reversible_when_empty() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_full_dependencies(connection)
        v1_migration = _v1_migration()
        v1_migration.op = BoundOp(connection)
        v1_migration.upgrade()

        assert SNAPSHOT_TABLE not in sa.inspect(connection).get_table_names()
        assert not set(_migration().PROFILE_COLUMNS) & _column_names(
            connection, PROFILE_TABLE
        )
        assert not set(_migration().PAIR_COLUMNS) & _column_names(
            connection, PAIR_TABLE
        )
        assert not {
            "ck_core3_cp_pair_v11_scope",
            "ck_core3_cp_pair_v11_self",
        } & _check_names(connection, PAIR_TABLE)
        assert "uq_core3_cp_version_scope_identity" not in {
            row["name"] for row in sa.inspect(connection).get_indexes(VERSION_TABLE)
        }

        migration = _upgrade(connection)
        assert SNAPSHOT_TABLE in sa.inspect(connection).get_table_names()
        assert set(migration.PAIR_COLUMNS) <= _column_names(connection, PAIR_TABLE)

        migration.downgrade()
        assert SNAPSHOT_TABLE not in sa.inspect(connection).get_table_names()
        assert not set(migration.PAIR_COLUMNS) & _column_names(connection, PAIR_TABLE)

        v1_migration.downgrade()
        remaining = set(sa.inspect(connection).get_table_names())
        assert (
            not {
                VERSION_TABLE,
                PROFILE_TABLE,
                PAIR_TABLE,
                RELATION_TABLE,
                SELECTION_TABLE,
            }
            & remaining
        )
    engine.dispose()


def test_real_0046_v1_rows_survive_0047_upgrade_and_downgrade() -> None:
    fixture = _v1_migration_fixture_module()
    engine = _engine()
    with engine.begin() as connection:
        fixture._create_dependencies(connection)
        v1_migration = _v1_migration()
        v1_migration.op = BoundOp(connection)
        v1_migration.upgrade()
        connection.execute(
            fixture.TABLES[0].insert().values(**fixture._version_values())
        )
        connection.execute(
            fixture.TABLES[1].insert().values(**fixture._profile_values())
        )
        connection.execute(fixture.TABLES[2].insert().values(**fixture._pair_values()))
        connection.execute(
            fixture.TABLES[3].insert().values(**_full_v1_relation_values())
        )
        connection.execute(
            fixture.TABLES[4].insert().values(**_full_v1_selection_values())
        )
        for table_name, primary_key, payload_column, primary_key_value in (
            (
                PROFILE_TABLE,
                "sku_competitor_profile_id",
                "profile_payload_json",
                "profile-1",
            ),
            (
                PAIR_TABLE,
                "sku_competitor_profile_pair_id",
                "pair_payload_json",
                "pair-1",
            ),
            (
                RELATION_TABLE,
                "sku_competitor_profile_relation_id",
                "relation_payload_json",
                "relation-1",
            ),
            (
                SELECTION_TABLE,
                "sku_competitor_profile_selection_id",
                "selection_payload_json",
                "selection-1",
            ),
        ):
            connection.execute(
                sa.text(
                    f'UPDATE "{table_name}" SET "{payload_column}" = json(\'null\') '
                    f'WHERE "{primary_key}" = :primary_key_value'
                ),
                {"primary_key_value": primary_key_value},
            )
        before = {
            table_name: _sqlite_table_state(connection, table_name)
            for table_name in (
                VERSION_TABLE,
                PROFILE_TABLE,
                PAIR_TABLE,
                RELATION_TABLE,
                SELECTION_TABLE,
            )
        }

        migration = _upgrade(connection)
        assert (
            connection.scalar(
                sa.text(
                    f"SELECT analysis_summary_json IS NULL FROM {PROFILE_TABLE} "
                    "WHERE sku_competitor_profile_id = 'profile-1'"
                )
            )
            == 1
        )
        migration.upgrade()
        captured = migration._capture_sqlite_child_rows(connection)
        for table_name in (
            SELECTION_TABLE,
            RELATION_TABLE,
            PAIR_TABLE,
            PROFILE_TABLE,
        ):
            connection.execute(sa.text(f'DELETE FROM "{table_name}"'))
        migration._restore_sqlite_child_rows(connection, captured)
        for table_name, column_name, primary_key, primary_key_value in (
            (
                PROFILE_TABLE,
                "analysis_summary_json",
                "sku_competitor_profile_id",
                "profile-1",
            ),
            (
                PAIR_TABLE,
                "analysis_snapshot_json",
                "sku_competitor_profile_pair_id",
                "pair-1",
            ),
            (
                RELATION_TABLE,
                "analysis_review_items_json",
                "sku_competitor_profile_relation_id",
                "relation-1",
            ),
            (
                SELECTION_TABLE,
                "selection_role_codes_json",
                "sku_competitor_profile_selection_id",
                "selection-1",
            ),
        ):
            assert (
                connection.scalar(
                    sa.text(
                        f'SELECT typeof("{column_name}") FROM "{table_name}" '
                        f'WHERE "{primary_key}" = :primary_key_value'
                    ),
                    {"primary_key_value": primary_key_value},
                )
                == "null"
            )
        migration.downgrade()

        after = {
            table_name: _sqlite_table_state(connection, table_name)
            for table_name in before
        }
        assert after == before
        assert not set(migration.PAIR_COLUMNS) & _column_names(connection, PAIR_TABLE)
        connection.execute(
            sa.text(
                f"DELETE FROM {VERSION_TABLE} "
                "WHERE competitor_profile_version_id = 'version-1'"
            )
        )
        v1_migration.downgrade()
    engine.dispose()


def test_upgrade_is_idempotent_and_does_not_duplicate_or_drop_v1_rows() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        _insert_v1_rows(connection)
        migration = _upgrade(connection)
        migration.upgrade()
        for table_name in (
            VERSION_TABLE,
            PROFILE_TABLE,
            PAIR_TABLE,
            RELATION_TABLE,
            SELECTION_TABLE,
        ):
            assert connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table_name}")) == 1
        assert [
            row["name"] for row in sa.inspect(connection).get_indexes(VERSION_TABLE)
        ].count("uq_core3_cp_version_scope_identity") == 1
    engine.dispose()


def test_snapshot_scope_fk_audit_fields_unique_key_and_cascade() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        _insert_version(connection, version_id="version-snapshot")
        _upgrade(connection)
        inspector = sa.inspect(connection)
        snapshot_columns = _column_names(connection, SNAPSHOT_TABLE)
        assert {
            "competitor_profile_sku_snapshot_id",
            "competitor_profile_version_id",
            "project_id",
            "category_code",
            "release_scope_key",
            "sku_code",
            "schema_version",
            "snapshot_json",
            "module_availability_json",
            "evidence_refs_json",
            "source_lineage_json",
            "input_fingerprint",
            "result_hash",
            "created_at",
            "updated_at",
        } <= snapshot_columns
        version_indexes = {
            row["name"]: row for row in inspector.get_indexes(VERSION_TABLE)
        }
        assert version_indexes["uq_core3_cp_version_scope_identity"]["unique"]
        assert version_indexes["uq_core3_cp_version_scope_identity"][
            "column_names"
        ] == [
            "competitor_profile_version_id",
            "project_id",
            "category_code",
            "release_scope_key",
        ]
        scope_fk = next(
            row
            for row in inspector.get_foreign_keys(SNAPSHOT_TABLE)
            if row["name"] == "fk_core3_cp_snapshot_version_scope"
        )
        assert scope_fk["constrained_columns"] == [
            "competitor_profile_version_id",
            "project_id",
            "category_code",
            "release_scope_key",
        ]
        assert scope_fk["options"].get("ondelete") == "CASCADE"

        snapshot_values = {
            "competitor_profile_sku_snapshot_id": "snapshot-1",
            "competitor_profile_version_id": "version-snapshot",
            "project_id": "project-tv",
            "category_code": "TV",
            "release_scope_key": "scope-tv",
            "sku_code": "TV-TARGET",
            "profile_version": "profile-version-snapshot",
            "schema_version": "sku_competitor_decision_profile_v1_1",
            "rule_version": "competitor_profile_materializer_v1_1",
            "method_version": "competitor_profile_method_v1_1",
            "snapshot_json": {},
            "module_availability_json": [],
            "evidence_refs_json": [],
            "source_lineage_json": {},
            "limitations_json": [],
            "input_fingerprint": "snapshot-input",
            "result_hash": "snapshot-result",
        }
        connection.execute(
            entities.Core3CompetitorProfileSkuSnapshot.__table__.insert().values(
                **snapshot_values
            )
        )
        persisted_shape = connection.execute(
            sa.select(
                entities.Core3CompetitorProfileSkuSnapshot.__table__.c.module_availability_json,
                entities.Core3CompetitorProfileSkuSnapshot.__table__.c.source_lineage_json,
            )
        ).one()
        assert persisted_shape.module_availability_json == []
        assert persisted_shape.source_lineage_json == {}
        with pytest.raises(IntegrityError):
            connection.execute(
                entities.Core3CompetitorProfileSkuSnapshot.__table__.insert().values(
                    **{
                        **snapshot_values,
                        "competitor_profile_sku_snapshot_id": "snapshot-duplicate",
                    }
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                entities.Core3CompetitorProfileSkuSnapshot.__table__.insert().values(
                    **{
                        **snapshot_values,
                        "competitor_profile_sku_snapshot_id": "snapshot-v1-schema",
                        "sku_code": "TV-C0",
                        "schema_version": "sku_competitor_decision_profile_v1",
                    }
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                entities.Core3CompetitorProfileSkuSnapshot.__table__.insert().values(
                    **{
                        **snapshot_values,
                        "competitor_profile_sku_snapshot_id": "snapshot-bad-scope",
                        "sku_code": "TV-C1",
                        "release_scope_key": "wrong-scope",
                    }
                )
            )
        connection.execute(
            sa.text(
                f"DELETE FROM {VERSION_TABLE} "
                "WHERE competitor_profile_version_id = 'version-snapshot'"
            )
        )
        assert connection.scalar(sa.text(f"SELECT COUNT(*) FROM {SNAPSHOT_TABLE}")) == 0
    engine.dispose()


def test_v11_pair_and_relation_use_new_axes_not_legacy_statuses() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        _insert_version(
            connection,
            version_id="version-v11",
            schema_version="sku_competitor_decision_profile_v1_1",
            rule_version="competitor_profile_materializer_v1_1",
            method_version="competitor_profile_method_v1_1",
        )
        _upgrade(connection)
        connection.execute(
            sa.text(
                f"INSERT INTO {PROFILE_TABLE} "
                "(sku_competitor_profile_id, competitor_profile_version_id, "
                "target_sku_code, schema_version, analysis_summary_json, "
                "analysis_fact_index_json, analysis_evidence_index_json, "
                "analysis_result_hash, analysis_candidate_count, "
                "analysis_available_dimension_count, analysis_review_item_count) "
                "VALUES ('profile-v11', 'version-v11', 'TV-TARGET', "
                "'sku_competitor_decision_profile_v1_1', '{}', '{}', '{}', "
                "'summary-hash', 1, 7, 0)"
            )
        )
        connection.execute(
            sa.text(
                f"INSERT INTO {PAIR_TABLE} "
                "(sku_competitor_profile_pair_id, sku_competitor_profile_id, "
                "competitor_profile_version_id, target_sku_code, candidate_sku_code, "
                "schema_version, candidate_status, selected, scope_status, "
                "target_snapshot_ref, candidate_snapshot_ref, analysis_snapshot_json, "
                "analysis_conclusion_strength, analysis_score, "
                "analysis_available_weight, analysis_result_hash, "
                "analysis_review_required, selection_question_code, "
                "selection_conclusion_strength) VALUES "
                "('pair-v11', 'profile-v11', 'version-v11', 'TV-TARGET', 'TV-C1', "
                "'sku_competitor_decision_profile_v1_1', 'reference_only', 1, "
                "'analyzable', 'snapshot-target', 'snapshot-candidate', '{}', "
                "'directional', 0.75, 0.40, 'pair-hash', 1, "
                "'key_competitor_selection', 'directional')"
            )
        )
        connection.execute(
            sa.text(
                f"INSERT INTO {RELATION_TABLE} "
                "(sku_competitor_profile_relation_id, "
                "sku_competitor_profile_pair_id, competitor_profile_version_id, "
                "relation_code, schema_version, relation_status, is_primary, "
                "analysis_relation_status, analysis_review_items_json) VALUES "
                "('relation-v11', 'pair-v11', 'version-v11', 'direct_substitute', "
                "'sku_competitor_decision_profile_v1_1', 'review_required', 1, "
                "'limited', '[]')"
            )
        )
        connection.execute(
            sa.text(
                f"INSERT INTO {SELECTION_TABLE} "
                "(sku_competitor_profile_selection_id, sku_competitor_profile_id, "
                "sku_competitor_profile_pair_id, competitor_profile_version_id, "
                "target_sku_code, selection_rank, schema_version, "
                "selection_policy_version, selection_score, "
                "selection_available_weight, selection_conclusion_strength, "
                "selection_role_codes_json, selection_score_breakdown_json) VALUES "
                "('selection-v11', 'profile-v11', 'pair-v11', 'version-v11', "
                "'TV-TARGET', 1, 'sku_competitor_decision_profile_v1_1', "
                "'competitor_profile_score_v1_1', 0.75, 0.40, 'directional', "
                "'[]', '{}')"
            )
        )

        invalid_updates = (
            f"UPDATE {PROFILE_TABLE} SET analysis_candidate_count = -1 "
            "WHERE sku_competitor_profile_id = 'profile-v11'",
            f"UPDATE {PAIR_TABLE} SET analysis_available_weight = 1.1 "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET scope_status = NULL "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET analysis_conclusion_strength = NULL "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET analysis_available_weight = NULL "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET analysis_score = NULL "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET selection_question_code = NULL "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET selection_conclusion_strength = NULL "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET scope_status = 'excluded', "
            "exclusion_reason_code = 'authority_missing', selected = 0, "
            "analysis_score = NULL, analysis_available_weight = NULL, "
            "analysis_conclusion_strength = 'unknown' "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {PAIR_TABLE} SET scope_status = 'excluded', "
            "exclusion_reason_code = NULL, selected = 0, "
            "analysis_score = NULL, analysis_available_weight = NULL, "
            "analysis_conclusion_strength = 'unknown' "
            "WHERE sku_competitor_profile_pair_id = 'pair-v11'",
            f"UPDATE {RELATION_TABLE} SET analysis_relation_status = NULL "
            "WHERE sku_competitor_profile_relation_id = 'relation-v11'",
            f"UPDATE {RELATION_TABLE} SET analysis_review_items_json = NULL "
            "WHERE sku_competitor_profile_relation_id = 'relation-v11'",
            f"UPDATE {SELECTION_TABLE} SET selection_score = 1.1 "
            "WHERE sku_competitor_profile_selection_id = 'selection-v11'",
            f"UPDATE {SELECTION_TABLE} SET selection_conclusion_strength = NULL "
            "WHERE sku_competitor_profile_selection_id = 'selection-v11'",
        )
        for statement in invalid_updates:
            with pytest.raises(IntegrityError):
                connection.execute(sa.text(statement))

        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {PAIR_TABLE} "
                    "(sku_competitor_profile_pair_id, sku_competitor_profile_id, "
                    "competitor_profile_version_id, target_sku_code, "
                    "candidate_sku_code, schema_version, candidate_status, selected, "
                    "scope_status, exclusion_reason_code, target_snapshot_ref, "
                    "candidate_snapshot_ref, analysis_snapshot_json, "
                    "analysis_conclusion_strength, analysis_result_hash, "
                    "analysis_review_required) VALUES "
                    "('pair-self-invalid', 'profile-v11', 'version-v11', "
                    "'TV-TARGET', 'TV-TARGET', "
                    "'sku_competitor_decision_profile_v1_1', 'reference_only', 0, "
                    "'analyzable', NULL, 'snapshot-target', 'snapshot-target', '{}', "
                    "'unknown', 'pair-self-invalid-hash', 0)"
                )
            )
        connection.execute(
            sa.text(
                f"INSERT INTO {PAIR_TABLE} "
                "(sku_competitor_profile_pair_id, sku_competitor_profile_id, "
                "competitor_profile_version_id, target_sku_code, "
                "candidate_sku_code, schema_version, candidate_status, selected, "
                "scope_status, exclusion_reason_code, target_snapshot_ref, "
                "candidate_snapshot_ref, analysis_snapshot_json, "
                "analysis_conclusion_strength, analysis_score, "
                "analysis_available_weight, analysis_result_hash, "
                "analysis_review_required) VALUES "
                "('pair-self-v11', 'profile-v11', 'version-v11', 'TV-TARGET', "
                "'TV-TARGET', 'sku_competitor_decision_profile_v1_1', "
                "'reference_only', 0, 'excluded', 'self_pair', 'snapshot-target', "
                "'snapshot-target', '{}', 'unknown', NULL, NULL, "
                "'pair-self-hash', 0)"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {PAIR_TABLE} "
                    "(sku_competitor_profile_pair_id, sku_competitor_profile_id, "
                    "competitor_profile_version_id, target_sku_code, "
                    "candidate_sku_code, schema_version, candidate_status, selected, "
                    "scope_status, exclusion_reason_code, target_snapshot_ref, "
                    "candidate_snapshot_ref, analysis_snapshot_json, "
                    "analysis_conclusion_strength, analysis_score, "
                    "analysis_available_weight, analysis_result_hash, "
                    "analysis_review_required) VALUES "
                    "('pair-non-self-invalid', 'profile-v11', 'version-v11', "
                    "'TV-TARGET', 'TV-C3', "
                    "'sku_competitor_decision_profile_v1_1', 'reference_only', 0, "
                    "'excluded', 'self_pair', 'snapshot-target', 'snapshot-c3', '{}', "
                    "'unknown', NULL, NULL, 'pair-non-self-invalid-hash', 0)"
                )
            )

        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {PAIR_TABLE} "
                    "(sku_competitor_profile_pair_id, sku_competitor_profile_id, "
                    "competitor_profile_version_id, target_sku_code, "
                    "candidate_sku_code, schema_version, candidate_status, selected, "
                    "scope_status, target_snapshot_ref, candidate_snapshot_ref, "
                    "analysis_snapshot_json, analysis_conclusion_strength, "
                    "analysis_available_weight, analysis_result_hash, "
                    "analysis_review_required) VALUES "
                    "('pair-invalid', 'profile-v11', 'version-v11', 'TV-TARGET', "
                    "'TV-C2', 'sku_competitor_decision_profile_v1_1', 'eligible', 1, "
                    "'excluded', 'snapshot-target', 'snapshot-candidate', '{}', "
                    "'unknown', NULL, 'pair-invalid-hash', 0)"
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {RELATION_TABLE} "
                    "(sku_competitor_profile_relation_id, "
                    "sku_competitor_profile_pair_id, competitor_profile_version_id, "
                    "relation_code, schema_version, relation_status, is_primary, "
                    "analysis_relation_status, analysis_review_items_json) VALUES "
                    "('relation-invalid', 'pair-v11', 'version-v11', "
                    "'same_budget_alternative', "
                    "'sku_competitor_decision_profile_v1_1', 'limited', 0, "
                    "'review_required', '[]')"
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {SELECTION_TABLE} "
                    "(sku_competitor_profile_selection_id, "
                    "sku_competitor_profile_id, sku_competitor_profile_pair_id, "
                    "competitor_profile_version_id, target_sku_code, selection_rank, "
                    "schema_version) VALUES ('selection-invalid', 'profile-v11', "
                    "'pair-v11', 'version-v11', 'TV-TARGET', 2, "
                    "'sku_competitor_decision_profile_v1_1')"
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    f"INSERT INTO {PROFILE_TABLE} "
                    "(sku_competitor_profile_id, competitor_profile_version_id, "
                    "target_sku_code, schema_version) VALUES "
                    "('profile-invalid', 'version-v11', 'TV-OTHER', "
                    "'sku_competitor_decision_profile_v1_1')"
                )
            )
    engine.dispose()


@pytest.mark.parametrize(
    ("blocker", "expected"),
    [
        ("version", "v1_1_versions=1"),
        ("snapshot", f"{SNAPSHOT_TABLE}=1"),
        ("profile", f"{PROFILE_TABLE}.v1_1_analysis_rows=1"),
        ("pair", f"{PAIR_TABLE}.v1_1_analysis_rows=1"),
        ("relation", f"{RELATION_TABLE}.v1_1_analysis_rows=1"),
        ("selection", f"{SELECTION_TABLE}.v1_1_analysis_rows=1"),
    ],
)
def test_downgrade_guard_rejects_each_v11_data_surface(
    blocker: str,
    expected: str,
) -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        _insert_v1_rows(connection)
        migration = _upgrade(connection)
        if blocker == "version":
            _insert_version(
                connection,
                version_id="version-v11",
                schema_version="sku_competitor_decision_profile_v1_1",
            )
        elif blocker == "snapshot":
            connection.execute(
                entities.Core3CompetitorProfileSkuSnapshot.__table__.insert().values(
                    competitor_profile_sku_snapshot_id="snapshot-v11",
                    competitor_profile_version_id="version-v1",
                    project_id="project-tv",
                    category_code="TV",
                    release_scope_key="scope-tv",
                    sku_code="TV-TARGET",
                    profile_version="profile-v1",
                    schema_version="sku_competitor_decision_profile_v1_1",
                    rule_version="competitor_profile_materializer_v1_1",
                    method_version="competitor_profile_method_v1_1",
                    snapshot_json={},
                    module_availability_json=[],
                    evidence_refs_json=[],
                    source_lineage_json={},
                    limitations_json=[],
                    input_fingerprint="snapshot-input",
                    result_hash="snapshot-result",
                )
            )
        else:
            updates = {
                "profile": (PROFILE_TABLE, "analysis_result_hash", "profile-v11"),
                "pair": (PAIR_TABLE, "analysis_result_hash", "pair-v11"),
                "relation": (
                    RELATION_TABLE,
                    "analysis_relation_status",
                    "limited",
                ),
                "selection": (
                    SELECTION_TABLE,
                    "selection_policy_version",
                    "policy-v11",
                ),
            }
            table_name, column_name, value = updates[blocker]
            connection.execute(
                sa.text(f"UPDATE {table_name} SET {column_name} = :value"),
                {"value": value},
            )
        with pytest.raises(RuntimeError, match=expected):
            migration.downgrade()
        assert SNAPSHOT_TABLE in sa.inspect(connection).get_table_names()
    engine.dispose()


@pytest.mark.parametrize(
    "version_override",
    [
        {"schema_version": "sku_competitor_decision_profile_v1_1"},
        {"rule_version": "competitor_profile_materializer_v1_1"},
        {"method_version": "competitor_profile_method_v1_1"},
    ],
)
def test_downgrade_guard_recognizes_each_frozen_v11_version_axis(
    version_override: dict[str, str],
) -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_v1_schema(connection)
        migration = _upgrade(connection)
        _insert_version(connection, version_id="version-v11-axis", **version_override)
        with pytest.raises(RuntimeError, match="v1_1_versions=1"):
            migration.downgrade()
    engine.dispose()


def test_entity_contract_matches_migration_and_keeps_v1_columns_nullable() -> None:
    migration = _migration()
    assert entities.COMPETITOR_PROFILE_V11_SCHEMA_VERSION == (
        migration.V11_SCHEMA_VERSION
    )
    snapshot = entities.Core3CompetitorProfileSkuSnapshot.__table__
    migration_snapshot = migration._snapshot_table()
    assert set(migration_snapshot.c.keys()) == set(snapshot.c.keys())
    for column_name in snapshot.c.keys():
        assert _type_signature(migration_snapshot.c[column_name]) == _type_signature(
            snapshot.c[column_name]
        )
        assert (
            migration_snapshot.c[column_name].nullable
            == snapshot.c[column_name].nullable
        )
    assert {constraint.name for constraint in migration_snapshot.constraints} == {
        constraint.name for constraint in snapshot.constraints
    }
    assert {index.name for index in migration_snapshot.indexes} == {
        index.name for index in snapshot.indexes
    }
    assert {"created_at", "updated_at"} <= set(snapshot.c.keys())
    assert snapshot.c.snapshot_json.nullable is False
    assert snapshot.c.module_availability_json.nullable is False

    expected_checks = {
        PROFILE_TABLE: set(migration.PROFILE_CHECKS),
        PAIR_TABLE: set(migration.PAIR_CHECKS),
        RELATION_TABLE: set(migration.RELATION_CHECKS),
        SELECTION_TABLE: set(migration.SELECTION_CHECKS),
    }
    g30_index_names = {
        "ix_core3_cp_profile_v11_read",
        "ix_core3_cp_pair_v11_scope",
        "ix_core3_cp_pair_v11_candidate",
        "ix_core3_cp_relation_v11_status",
        "ix_core3_cp_selection_v11_read",
    }
    for table_name, names in expected_checks.items():
        table = entities.Base.metadata.tables[table_name]
        actual = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        assert names <= actual
        actual_sql = {
            constraint.name: _normalized_sql(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, sa.CheckConstraint) and constraint.name in names
        }
        expected_sql = {
            name: _normalized_sql(sql)
            for name, sql in {
                **migration.PROFILE_CHECKS,
                **migration.PAIR_CHECKS,
                **migration.RELATION_CHECKS,
                **migration.SELECTION_CHECKS,
            }.items()
            if name in names
        }
        assert actual_sql == expected_sql
    for table_name, columns in (
        (PROFILE_TABLE, migration.PROFILE_COLUMNS),
        (PAIR_TABLE, migration.PAIR_COLUMNS),
        (RELATION_TABLE, migration.RELATION_COLUMNS),
        (SELECTION_TABLE, migration.SELECTION_COLUMNS),
    ):
        table = entities.Base.metadata.tables[table_name]
        assert all(table.c[column].nullable for column in columns)
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63
        for index in table.indexes:
            if index.name in g30_index_names:
                assert len(index.name) <= 63
    for index in snapshot.indexes:
        assert index.name is not None and len(index.name) <= 63
