import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0007_core3_cleaning_quality.py"

M01_TABLES = {
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
M01_DEPENDENCY_TABLES = {
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
LEGACY_CORE3_TABLES = {
    "core3_pipeline_run",
    "core3_sku_market_profile",
    "core3_sku_feature_profile",
    "core3_competitor_candidate",
    "core3_competitor_result",
    "core3_evidence_card",
}
FUTURE_RESULT_TABLES = {
    "core3_evidence_atom",
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


def load_m01_migration():
    spec = importlib.util.spec_from_file_location("core3_cleaning_quality_migration", MIGRATION_PATH)
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


def create_m01_dependencies(connection) -> None:
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
    ]:
        table.create(bind=connection, checkfirst=True)


def test_m01_cleaning_models_are_registered():
    assert entities.Core3CleanSku.__tablename__ == "core3_clean_sku"
    assert entities.Core3CleanMarketWeekly.__tablename__ == "core3_clean_market_weekly"
    assert entities.Core3CleanAttribute.__tablename__ == "core3_clean_attribute"
    assert entities.Core3CleanClaim.__tablename__ == "core3_clean_claim"
    assert entities.Core3CleanClaimSentence.__tablename__ == "core3_clean_claim_sentence"
    assert entities.Core3CleanComment.__tablename__ == "core3_clean_comment"
    assert entities.Core3CleanCommentSentence.__tablename__ == "core3_clean_comment_sentence"
    assert entities.Core3CleanCommentDimension.__tablename__ == "core3_clean_comment_dimension"
    assert entities.Core3DataQualityIssue.__tablename__ == "core3_data_quality_issue"

    assert M01_TABLES.issubset(set(Base.metadata.tables))


def test_m01_cleaning_model_columns_match_contract():
    expected_columns = {
        "core3_clean_sku": {
            "clean_sku_id",
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "sku_code_raw_values",
            "coverage_json",
            "field_conflicts_json",
            "missing_signals_json",
            "clean_record_key",
            "clean_hash",
            "clean_version",
            "hash_version",
            "quality_status",
            "quality_flags",
            "review_required",
            "review_status",
        },
        "core3_clean_market_weekly": {
            "clean_market_id",
            "source_table",
            "source_pk",
            "source_row_id",
            "source_row_hash",
            "source_operation_type",
            "period_raw",
            "sales_volume",
            "sales_amount",
            "avg_price",
            "price_check_status",
            "price_check_delta",
            "record_status",
            "clean_hash",
        },
        "core3_clean_attribute": {
            "clean_attribute_id",
            "raw_attr_name",
            "clean_attr_name",
            "raw_attr_value",
            "clean_attr_value",
            "value_presence",
            "value_number_candidates",
            "value_unit_candidates",
            "conflict_group_key",
            "record_status",
            "clean_hash",
        },
        "core3_clean_claim": {
            "clean_claim_id",
            "claim_seq_raw",
            "claim_seq",
            "raw_claim_text",
            "clean_claim_text",
            "claim_text_presence",
            "title_hint",
            "structure_hints",
            "record_status",
            "clean_hash",
        },
        "core3_clean_claim_sentence": {
            "claim_sentence_id",
            "clean_claim_id",
            "sentence_seq",
            "sentence_text",
            "sentence_text_hash",
            "sentence_role_hint",
            "split_rule",
            "clean_hash",
        },
        "core3_clean_comment": {
            "clean_comment_id",
            "comment_id",
            "comment_time_raw",
            "comment_time",
            "raw_comment_text",
            "clean_comment_text",
            "comment_text_presence",
            "comment_text_hash",
            "segment_text_raw",
            "segment_text_hash",
            "sentiment_clean",
            "low_value_flag",
            "duplicate_group_key",
            "dimension_available",
            "record_status",
            "clean_hash",
        },
        "core3_clean_comment_sentence": {
            "comment_sentence_id",
            "clean_comment_id",
            "sentence_source",
            "sentence_seq",
            "sentence_text",
            "sentence_text_hash",
            "source_segment_text",
            "is_from_existing_segment",
            "split_rule",
            "clean_hash",
        },
        "core3_clean_comment_dimension": {
            "comment_dimension_id",
            "clean_comment_id",
            "primary_dim_raw",
            "secondary_dim_raw",
            "third_dim_raw",
            "dimension_path_raw",
            "dimension_available",
            "dimension_quality_flag",
            "clean_hash",
        },
        "core3_data_quality_issue": {
            "issue_id",
            "module_code",
            "domain",
            "source_table",
            "source_row_id",
            "clean_table",
            "clean_record_key",
            "sku_code",
            "issue_type",
            "severity",
            "issue_detail",
            "issue_payload_json",
            "suggested_downstream_action",
            "review_required",
            "review_status",
        },
    }

    common_columns = {
        "project_id",
        "category_code",
        "batch_id",
        "clean_record_key",
        "clean_hash",
        "clean_version",
        "hash_version",
        "quality_status",
        "quality_flags",
        "created_at",
    }
    for table_name, columns in expected_columns.items():
        table_columns = set(Base.metadata.tables[table_name].columns.keys())
        assert columns.issubset(table_columns)
        assert common_columns.intersection(table_columns)


def test_m01_cleaning_constraints_and_indexes_match_contract():
    expected_unique_constraints = {
        "core3_clean_sku": "uq_core3_clean_sku_batch_sku",
        "core3_clean_market_weekly": "uq_core3_clean_market_batch_source_row",
        "core3_clean_attribute": "uq_core3_clean_attribute_batch_source_row",
        "core3_clean_claim": "uq_core3_clean_claim_batch_source_row",
        "core3_clean_claim_sentence": "uq_core3_clean_claim_sentence_batch_source_seq",
        "core3_clean_comment": "uq_core3_clean_comment_batch_source_row",
        "core3_clean_comment_sentence": "uq_core3_clean_comment_sentence_batch_source_seq",
        "core3_clean_comment_dimension": "uq_core3_clean_comment_dimension_batch_source",
        "core3_data_quality_issue": "uq_core3_data_quality_issue_dedupe",
    }

    for table_name, constraint_name in expected_unique_constraints.items():
        constraint_names = {
            constraint.name for constraint in Base.metadata.tables[table_name].constraints
        }
        assert constraint_name in constraint_names

    assert "ix_core3_clean_sku_project_category_batch" in {
        index.name for index in Base.metadata.tables["core3_clean_sku"].indexes
    }
    assert "ix_core3_clean_comment_text_hash" in {
        index.name for index in Base.metadata.tables["core3_clean_comment"].indexes
    }
    assert "ix_core3_data_quality_issue_domain_type" in {
        index.name for index in Base.metadata.tables["core3_data_quality_issue"].indexes
    }


def test_m01_migration_imports_with_expected_revision_chain():
    migration = load_m01_migration()

    assert migration.revision == "0007_core3_cleaning"
    assert migration.down_revision == "0006_core3_source_registry"


def test_m01_migration_only_mentions_cleaning_models_not_raw_or_future_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in RAW_SOURCE_TABLES | LEGACY_CORE3_TABLES | FUTURE_RESULT_TABLES:
        assert table_name not in source
    for model_name in [
        "Core3CleanSku",
        "Core3CleanMarketWeekly",
        "Core3CleanAttribute",
        "Core3CleanClaim",
        "Core3CleanClaimSentence",
        "Core3CleanComment",
        "Core3CleanCommentSentence",
        "Core3CleanCommentDimension",
        "Core3DataQualityIssue",
    ]:
        assert model_name in source


def test_m01_migration_creates_and_drops_m01_tables_only():
    migration = load_m01_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        create_m01_dependencies(connection)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            table_names_after_upgrade = set(inspect(connection).get_table_names())

            assert M01_TABLES.issubset(table_names_after_upgrade)
            assert M01_DEPENDENCY_TABLES.issubset(table_names_after_upgrade)
            assert not LEGACY_CORE3_TABLES.intersection(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)
            assert not FUTURE_RESULT_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            table_names_after_downgrade = set(inspect(connection).get_table_names())

            assert not M01_TABLES.intersection(table_names_after_downgrade)
            assert M01_DEPENDENCY_TABLES.issubset(table_names_after_downgrade)
        finally:
            migration.op = original_op


def test_m01_tables_do_not_depend_on_raw_or_legacy_tables():
    allowed_external_tables = {
        "category_project",
        "core3_v2_pipeline_run",
        "core3_v2_module_run",
        "core3_source_batch",
        "core3_clean_claim",
        "core3_clean_comment",
    }

    for table_name in M01_TABLES:
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            referred_table_name = foreign_key.column.table.name
            assert referred_table_name in allowed_external_tables
