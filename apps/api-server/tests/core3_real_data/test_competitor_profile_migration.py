from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from app.models import entities


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0046_core3_competitor_profile.py"
)
TABLES = (
    entities.Core3CompetitorProfileVersion.__table__,
    entities.Core3SkuCompetitorProfile.__table__,
    entities.Core3SkuCompetitorProfilePair.__table__,
    entities.Core3SkuCompetitorProfileRelation.__table__,
    entities.Core3SkuCompetitorProfileSelection.__table__,
)
TABLE_NAMES = {table.name for table in TABLES}


class BoundOp:
    def __init__(self, bind: Any) -> None:
        self.bind = bind

    def get_bind(self) -> Any:
        return self.bind


def _migration():
    spec = importlib.util.spec_from_file_location(
        "core3_competitor_profile_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _create_dependencies(connection: Any) -> None:
    entities.CategoryProject.__table__.create(bind=connection, checkfirst=True)
    entities.Core3V2PipelineRun.__table__.create(bind=connection, checkfirst=True)
    entities.Core3V2ModuleRun.__table__.create(bind=connection, checkfirst=True)
    entities.Core3SourceBatch.__table__.create(bind=connection, checkfirst=True)
    connection.execute(
        entities.CategoryProject.__table__.insert().values(
            project_id="project-tv",
            name="TV project",
            category_code="TV",
        )
    )
    connection.execute(
        entities.Core3SourceBatch.__table__.insert().values(
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


def _version_values(**overrides: Any) -> dict[str, Any]:
    values = {
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
        "method_versions_json": {"recall": "v1"},
        "serving_scope_json": {"source_batch_ids": ["batch-tv"]},
        "source_authorities_json": {"M07": {"rule_version": "m07-v2"}},
        "source_batch_ids_json": ["batch-tv"],
        "authoritative_sku_manifest_hash": "manifest-hash",
        "release_status": "draft",
        "release_quality_status": "unassessed",
        "is_current": False,
        "freshness_status": "current",
        "generated_by": "system",
        "sku_count": 1,
        "ready_count": 1,
        "partial_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "pair_count": 1,
        "relation_count": 7,
        "selection_count": 1,
        "input_fingerprint": "input-hash",
        "candidate_universe_fingerprint": "candidate-hash",
        "result_hash": "result-hash",
        "processing_status": "completed",
        "review_required": False,
        "review_status": "auto_pass",
    }
    values.update(overrides)
    return values


def _profile_values(**overrides: Any) -> dict[str, Any]:
    values = {
        "sku_competitor_profile_id": "profile-1",
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
        "display_name_cn": "海信 65E7Q",
        "analysis_state": "ready",
        "conclusion_state": "available",
        "freshness_status": "current",
        "profile_confidence": 0.8,
        "input_fingerprint": "profile-input",
        "result_hash": "profile-result",
    }
    values.update(overrides)
    return values


def _pair_values(**overrides: Any) -> dict[str, Any]:
    values = {
        "sku_competitor_profile_pair_id": "pair-1",
        "sku_competitor_profile_id": "profile-1",
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
        "competitor_member": True,
        "reference_member": False,
        "candidate_status": "eligible",
        "purchase_pool_level": "P0",
        "selected": True,
        "confidence_level": "high",
        "confidence": 0.8,
        "input_fingerprint": "pair-input",
        "result_hash": "pair-result",
    }
    values.update(overrides)
    return values


def test_migration_allows_auditable_non_member_recalled_pair() -> None:
    migration = _migration()
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        migration.op = BoundOp(connection)
        migration.upgrade()
        connection.execute(
            entities.Core3CompetitorProfileVersion.__table__.insert().values(
                **_version_values()
            )
        )
        connection.execute(
            entities.Core3SkuCompetitorProfile.__table__.insert().values(
                **_profile_values()
            )
        )
        connection.execute(
            entities.Core3SkuCompetitorProfilePair.__table__.insert().values(
                **_pair_values(
                    competitor_member=False,
                    reference_member=False,
                    candidate_status="recalled_only",
                    selected=False,
                )
            )
        )
    engine.dispose()


def test_migration_revision_chain_and_upgrade_downgrade() -> None:
    migration = _migration()
    assert migration.revision == "0046_core3_competitor_profile"
    assert migration.down_revision == "0045_core3_sellpoint_value_profile"
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        migration.op = BoundOp(connection)
        migration.upgrade()
        assert TABLE_NAMES <= set(inspect(connection).get_table_names())
        migration.downgrade()
        assert not TABLE_NAMES & set(inspect(connection).get_table_names())
    engine.dispose()


def test_migration_refuses_downgrade_when_profile_data_exists() -> None:
    migration = _migration()
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        migration.op = BoundOp(connection)
        migration.upgrade()
        connection.execute(TABLES[0].insert().values(**_version_values()))
        with pytest.raises(RuntimeError, match="refusing to downgrade"):
            migration.downgrade()
        assert TABLE_NAMES <= set(inspect(connection).get_table_names())
    engine.dispose()


def test_expected_tables_constraints_and_indexes_exist() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        for table in TABLES:
            table.create(bind=connection)
        db_inspector = inspect(connection)
        assert TABLE_NAMES <= set(db_inspector.get_table_names())
        version_indexes = {
            row["name"]
            for row in db_inspector.get_indexes("core3_competitor_profile_version")
        }
        assert "uq_core3_cp_current_published" in version_indexes
        pair_indexes = {
            row["name"]
            for row in db_inspector.get_indexes("core3_sku_competitor_profile_pair")
        }
        assert {
            "ix_core3_cp_pair_target_candidate",
            "ix_core3_cp_pair_candidate_target",
            "ix_core3_cp_pair_selected",
        } <= pair_indexes
        selection_uniques = {
            tuple(row["column_names"])
            for row in db_inspector.get_unique_constraints(
                "core3_sku_competitor_profile_selection"
            )
        }
        assert ("sku_competitor_profile_id", "selection_rank") in selection_uniques
        assert ("sku_competitor_profile_id", "candidate_sku_code") in selection_uniques
    engine.dispose()


@pytest.mark.parametrize(
    "invalid",
    [
        {"category_code": "TV", "product_category": "AC"},
        {"release_status": "draft", "is_current": True},
        {"ready_count": 2, "sku_count": 1},
        {"selection_count": 4, "sku_count": 1},
        {"relation_count": 8, "pair_count": 1},
    ],
)
def test_version_check_constraints_reject_invalid_rows(invalid: dict[str, Any]) -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        TABLES[0].create(bind=connection)
        with pytest.raises(IntegrityError):
            connection.execute(TABLES[0].insert().values(**_version_values(**invalid)))
    engine.dispose()


def test_pair_relation_selection_constraints_and_uniqueness() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        for table in TABLES:
            table.create(bind=connection)
        connection.execute(TABLES[0].insert().values(**_version_values()))
        connection.execute(TABLES[1].insert().values(**_profile_values()))
        connection.execute(TABLES[2].insert().values(**_pair_values()))

        with pytest.raises(IntegrityError):
            connection.execute(
                TABLES[2].insert().values(
                    **_pair_values(
                        sku_competitor_profile_pair_id="pair-self",
                        candidate_sku_code="TV-TARGET",
                    )
                )
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                TABLES[2].insert().values(
                    **_pair_values(
                        sku_competitor_profile_pair_id="pair-reference-selected",
                        candidate_sku_code="TV-C2",
                        competitor_member=False,
                        reference_member=True,
                        candidate_status="reference_only",
                        selected=True,
                    )
                )
            )
        relation_values = {
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
            "relation_code": "invalid_relation",
            "relation_status": "passed",
            "is_primary": True,
            "confidence_level": "high",
            "input_fingerprint": "relation-input",
            "result_hash": "relation-result",
        }
        with pytest.raises(IntegrityError):
            connection.execute(TABLES[3].insert().values(**relation_values))
        selection_values = {
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
            "selection_rank": 4,
            "primary_decision_topic": "purchase_choice",
            "primary_relation_code": "direct_substitute",
            "selection_reason_cn": "reason",
            "independent_information_reason_cn": "independent",
            "confidence_level": "high",
            "input_fingerprint": "selection-input",
            "result_hash": "selection-result",
        }
        with pytest.raises(IntegrityError):
            connection.execute(TABLES[4].insert().values(**selection_values))
    engine.dispose()


def test_draft_version_delete_cascades_all_children() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        for table in TABLES:
            table.create(bind=connection)
        connection.execute(TABLES[0].insert().values(**_version_values()))
        connection.execute(TABLES[1].insert().values(**_profile_values()))
        connection.execute(TABLES[2].insert().values(**_pair_values()))
        connection.execute(
            TABLES[0].delete().where(
                TABLES[0].c.competitor_profile_version_id == "version-1"
            )
        )
        assert connection.scalar(select(TABLES[1].c.sku_competitor_profile_id)) is None
        assert connection.scalar(select(TABLES[2].c.sku_competitor_profile_pair_id)) is None
    engine.dispose()
