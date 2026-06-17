import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0006_core3_real_data_source_registry.py"

M00_TABLES = {
    "core3_source_batch",
    "core3_source_row_registry",
    "core3_source_impacted_sku",
}
DEPENDENCY_TABLES = {
    "category_project",
    "core3_v2_pipeline_run",
    "core3_v2_module_run",
}
LEGACY_CORE3_TABLES = {
    "core3_pipeline_run",
    "core3_sku_market_profile",
    "core3_sku_feature_profile",
    "core3_competitor_candidate",
    "core3_competitor_result",
    "core3_evidence_card",
}
RAW_SOURCE_TABLES = {
    "week_sales_data",
    "attribute_data",
    "selling_points_data",
    "comment_data",
}


class BoundOp:
    def __init__(self, bind):
        self.bind = bind

    def get_bind(self):
        return self.bind


def load_m00_migration():
    spec = importlib.util.spec_from_file_location("core3_real_data_source_registry_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def create_m00_dependencies(connection):
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
    ]:
        table.create(bind=connection, checkfirst=True)


def test_m00_source_registry_models_are_registered():
    assert entities.Core3SourceBatch.__tablename__ == "core3_source_batch"
    assert entities.Core3SourceRowRegistry.__tablename__ == "core3_source_row_registry"
    assert entities.Core3SourceImpactedSku.__tablename__ == "core3_source_impacted_sku"

    assert M00_TABLES.issubset(set(Base.metadata.tables))


def test_m00_source_registry_model_columns_match_contract():
    expected_columns = {
        "core3_source_batch": {
            "batch_id",
            "project_id",
            "category_code",
            "run_id",
            "module_run_id",
            "batch_type",
            "source_system",
            "source_database",
            "source_schema",
            "source_tables",
            "ruleset_version",
            "module_version",
            "hash_version",
            "scan_started_at",
            "scan_finished_at",
            "input_watermark_json",
            "row_counts_json",
            "write_time_range_json",
            "source_pk_range_json",
            "schema_snapshot_json",
            "impacted_sku_count",
            "affected_module_summary_json",
            "quality_summary_json",
            "status",
            "review_required",
            "review_status",
            "review_reason",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
        },
        "core3_source_row_registry": {
            "row_registry_id",
            "batch_id",
            "project_id",
            "category_code",
            "source_table",
            "source_pk",
            "source_pk_strategy",
            "source_row_id",
            "row_hash",
            "hash_version",
            "previous_batch_id",
            "previous_row_hash",
            "previous_operation_type",
            "sku_code_candidate",
            "model_name_raw",
            "brand_raw",
            "category_raw",
            "write_time",
            "business_key_json",
            "source_field_presence_json",
            "operation_type",
            "change_reason",
            "affected_modules",
            "quality_hint",
            "review_required",
            "review_status",
            "created_at",
        },
        "core3_source_impacted_sku": {
            "impacted_sku_id",
            "batch_id",
            "project_id",
            "category_code",
            "sku_code_candidate",
            "model_name_raw",
            "brand_raw",
            "source_tables",
            "operation_summary_json",
            "affected_modules",
            "impact_reason",
            "impact_level",
            "needs_recompute",
            "review_required",
            "review_status",
            "review_reason",
            "created_at",
        },
    }

    for table_name, columns in expected_columns.items():
        assert columns.issubset(set(Base.metadata.tables[table_name].columns.keys()))


def test_m00_source_registry_constraints_and_indexes_match_contract():
    row_table = Base.metadata.tables["core3_source_row_registry"]
    impacted_sku_table = Base.metadata.tables["core3_source_impacted_sku"]

    assert "uq_core3_source_row_registry_batch_table_pk" in {
        constraint.name for constraint in row_table.constraints
    }
    assert "uq_core3_source_impacted_sku_batch_sku" in {
        constraint.name for constraint in impacted_sku_table.constraints
    }

    batch_index_names = {index.name for index in Base.metadata.tables["core3_source_batch"].indexes}
    row_index_names = {index.name for index in row_table.indexes}
    impacted_index_names = {index.name for index in impacted_sku_table.indexes}

    assert "ix_core3_source_batch_project_category_created" in batch_index_names
    assert "ix_core3_source_batch_project_category_status" in batch_index_names
    assert "ix_core3_source_row_registry_project_category_batch" in row_index_names
    assert "ix_core3_source_impacted_sku_project_category_batch" in impacted_index_names


def test_m00_migration_imports_with_expected_revision_chain():
    migration = load_m00_migration()

    assert migration.revision == "0006_core3_source_registry"
    assert migration.down_revision == "0005_core3_foundation"


def test_m00_migration_only_mentions_m00_models_not_raw_or_legacy_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in RAW_SOURCE_TABLES | LEGACY_CORE3_TABLES:
        assert table_name not in source
    for model_name in ["Core3SourceBatch", "Core3SourceRowRegistry", "Core3SourceImpactedSku"]:
        assert model_name in source


def test_m00_migration_creates_and_drops_m00_tables_only():
    migration = load_m00_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        create_m00_dependencies(connection)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            table_names_after_upgrade = set(inspect(connection).get_table_names())

            assert M00_TABLES.issubset(table_names_after_upgrade)
            assert DEPENDENCY_TABLES.issubset(table_names_after_upgrade)
            assert not LEGACY_CORE3_TABLES.intersection(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            table_names_after_downgrade = set(inspect(connection).get_table_names())

            assert not M00_TABLES.intersection(table_names_after_downgrade)
            assert DEPENDENCY_TABLES.issubset(table_names_after_downgrade)
        finally:
            migration.op = original_op


def test_m00_tables_do_not_depend_on_legacy_core3_mvp_or_raw_tables():
    allowed_external_tables = {
        "category_project",
        "core3_v2_pipeline_run",
        "core3_v2_module_run",
        "core3_source_batch",
    }

    for table_name in M00_TABLES:
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            referred_table_name = foreign_key.column.table.name
            assert referred_table_name in allowed_external_tables
