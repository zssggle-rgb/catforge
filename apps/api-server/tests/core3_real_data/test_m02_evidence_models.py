import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0008_core3_real_data_evidence.py"

M02_TABLES = {
    "core3_evidence_atom",
    "core3_evidence_link",
}
M02_VIEW = "core3_current_evidence_atom"
M02_DEPENDENCY_TABLES = {
    "category_project",
    "core3_v2_pipeline_run",
    "core3_v2_module_run",
    "core3_source_batch",
}
RAW_SOURCE_TABLES = {
    "week_sales_data",
    "attribute_data",
    "selling_points_data",
    "comment_data",
}
M01_CLEANING_TABLES = {
    "core3_clean_sku",
    "core3_clean_market_weekly",
    "core3_clean_attribute",
    "core3_clean_claim",
    "core3_clean_claim_sentence",
    "core3_clean_comment",
    "core3_clean_comment_sentence",
    "core3_clean_comment_dimension",
    "core3_data_quality_issue",
}
LEGACY_CORE3_TABLES = {
    "core3_pipeline_run",
    "core3_sku_market_profile",
    "core3_sku_feature_profile",
    "core3_competitor_candidate",
    "core3_competitor_result",
    "core3_evidence_card",
}
BUSINESS_RESULT_TABLES = {
    "core3_param_profile",
    "core3_comment_evidence",
    "core3_market_profile",
    "core3_competitor_selection",
}


class BoundOp:
    def __init__(self, bind):
        self.bind = bind

    def get_bind(self):
        return self.bind


def load_m02_migration():
    spec = importlib.util.spec_from_file_location("core3_real_data_evidence_migration", MIGRATION_PATH)
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


def create_m02_dependencies(connection) -> None:
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
    ]:
        table.create(bind=connection, checkfirst=True)


def test_m02_evidence_models_are_registered():
    assert entities.Core3EvidenceAtom.__tablename__ == "core3_evidence_atom"
    assert entities.Core3EvidenceLink.__tablename__ == "core3_evidence_link"

    assert M02_TABLES.issubset(set(Base.metadata.tables))


def test_m02_evidence_atom_columns_match_contract():
    expected_columns = {
        "evidence_id",
        "evidence_key",
        "project_id",
        "category_code",
        "batch_id",
        "run_id",
        "module_run_id",
        "sku_code",
        "model_name",
        "brand_name",
        "evidence_type",
        "evidence_grain",
        "evidence_field",
        "evidence_title",
        "source_table",
        "source_pk",
        "source_row_id",
        "source_row_hash",
        "clean_table",
        "clean_record_key",
        "clean_hash",
        "clean_version",
        "raw_field",
        "raw_value",
        "clean_field",
        "clean_value",
        "value_presence",
        "numeric_value",
        "numeric_values_json",
        "unit_value",
        "text_value",
        "text_hash",
        "evidence_time",
        "period_raw",
        "period_week_index",
        "channel_type",
        "platform_type",
        "comment_id",
        "comment_text_hash",
        "segment_text_hash",
        "sentence_seq",
        "dimension_path_raw",
        "quality_status",
        "quality_flags",
        "base_confidence",
        "confidence_level",
        "sample_status",
        "evidence_payload_json",
        "evidence_status",
        "inactive_reason",
        "is_current",
        "evidence_version",
        "confidence_rule_version",
        "asset_version",
        "review_required",
        "review_status",
        "created_at",
        "updated_at",
    }

    table_columns = set(Base.metadata.tables["core3_evidence_atom"].columns.keys())

    assert expected_columns.issubset(table_columns)


def test_m02_evidence_link_columns_match_contract():
    expected_columns = {
        "link_id",
        "project_id",
        "category_code",
        "batch_id",
        "from_evidence_id",
        "to_evidence_id",
        "from_evidence_key",
        "to_evidence_key",
        "link_type",
        "link_payload_json",
        "confidence",
        "link_status",
        "created_at",
        "updated_at",
    }

    table_columns = set(Base.metadata.tables["core3_evidence_link"].columns.keys())

    assert expected_columns.issubset(table_columns)


def test_m02_evidence_constraints_and_indexes_match_contract():
    atom_table = Base.metadata.tables["core3_evidence_atom"]
    link_table = Base.metadata.tables["core3_evidence_link"]

    assert "uq_core3_evidence_atom_key_hash_version" in {
        constraint.name for constraint in atom_table.constraints
    }
    assert "uq_core3_evidence_link_from_to_type" in {
        constraint.name for constraint in link_table.constraints
    }

    atom_index_names = {index.name for index in atom_table.indexes}
    link_index_names = {index.name for index in link_table.indexes}

    assert "ix_core3_evidence_atom_project_category_batch" in atom_index_names
    assert "ix_core3_evidence_atom_sku_type" in atom_index_names
    assert "ix_core3_evidence_atom_clean_record" in atom_index_names
    assert "ix_core3_evidence_atom_key_current" in atom_index_names
    assert "ix_core3_evidence_atom_status" in atom_index_names
    assert "ix_core3_evidence_atom_comment_text_hash" in atom_index_names
    assert "ix_core3_evidence_atom_segment_text_hash" in atom_index_names
    assert "ix_core3_evidence_link_project_category_batch" in link_index_names
    assert "ix_core3_evidence_link_from_evidence" in link_index_names
    assert "ix_core3_evidence_link_to_evidence" in link_index_names
    assert "ix_core3_evidence_link_type" in link_index_names


def test_m02_migration_imports_with_expected_revision_chain():
    migration = load_m02_migration()

    assert migration.revision == "0008_core3_evidence"
    assert migration.down_revision == "0007_core3_cleaning"


def test_m02_migration_only_mentions_evidence_models_not_raw_cleaning_or_business_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in RAW_SOURCE_TABLES | M01_CLEANING_TABLES | LEGACY_CORE3_TABLES | BUSINESS_RESULT_TABLES:
        assert table_name not in source
    for model_name in ["Core3EvidenceAtom", "Core3EvidenceLink"]:
        assert model_name in source


def test_m02_migration_creates_current_view_and_drops_m02_objects_only():
    migration = load_m02_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        create_m02_dependencies(connection)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            inspector = inspect(connection)
            table_names_after_upgrade = set(inspector.get_table_names())
            view_names_after_upgrade = set(inspector.get_view_names())

            assert M02_TABLES.issubset(table_names_after_upgrade)
            assert M02_VIEW in view_names_after_upgrade
            assert M02_DEPENDENCY_TABLES.issubset(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)
            assert not M01_CLEANING_TABLES.intersection(table_names_after_upgrade)
            assert not LEGACY_CORE3_TABLES.intersection(table_names_after_upgrade)
            assert not BUSINESS_RESULT_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            inspector = inspect(connection)
            table_names_after_downgrade = set(inspector.get_table_names())
            view_names_after_downgrade = set(inspector.get_view_names())

            assert not M02_TABLES.intersection(table_names_after_downgrade)
            assert M02_VIEW not in view_names_after_downgrade
            assert M02_DEPENDENCY_TABLES.issubset(table_names_after_downgrade)
        finally:
            migration.op = original_op


def test_m02_tables_do_not_depend_on_raw_m01_or_business_tables():
    allowed_external_tables = {
        "category_project",
        "core3_v2_pipeline_run",
        "core3_v2_module_run",
        "core3_source_batch",
        "core3_evidence_atom",
    }

    for table_name in M02_TABLES:
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            referred_table_name = foreign_key.column.table.name
            assert referred_table_name in allowed_external_tables
