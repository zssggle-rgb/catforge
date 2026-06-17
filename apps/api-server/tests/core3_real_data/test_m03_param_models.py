import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0009_core3_real_data_param_extraction.py"

M03_TABLES = {
    "core3_param_field_profile",
    "core3_extract_param_value",
    "core3_param_alias_candidate",
    "core3_param_value_conflict",
    "core3_sku_param_profile",
}
M03_DEPENDENCY_TABLES = {
    "category_project",
    "core3_v2_pipeline_run",
    "core3_v2_module_run",
    "core3_source_batch",
    "core3_evidence_atom",
}
RAW_SOURCE_TABLES = {
    "week_sales_data",
    "attribute_data",
    "selling_points_data",
    "comment_data",
}
M00_M02_TABLES = {
    "core3_source_row_registry",
    "core3_source_impacted_sku",
    "core3_clean_sku",
    "core3_clean_market_weekly",
    "core3_clean_attribute",
    "core3_clean_claim",
    "core3_clean_claim_sentence",
    "core3_clean_comment",
    "core3_clean_comment_sentence",
    "core3_clean_comment_dimension",
    "core3_data_quality_issue",
    "core3_evidence_link",
}
FUTURE_RESULT_TABLES = {
    "core3_claim_activation",
    "core3_comment_signal",
    "core3_market_profile",
    "core3_sku_profile",
    "core3_task_candidate",
    "core3_target_group_profile",
    "core3_battlefield_profile",
    "core3_competitor_selection",
}


class BoundOp:
    def __init__(self, bind):
        self.bind = bind

    def get_bind(self):
        return self.bind


def load_m03_migration():
    spec = importlib.util.spec_from_file_location("core3_param_extraction_migration", MIGRATION_PATH)
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


def create_m03_dependencies(connection) -> None:
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
    ]:
        table.create(bind=connection, checkfirst=True)


def test_m03_param_models_are_registered():
    assert entities.Core3ParamFieldProfile.__tablename__ == "core3_param_field_profile"
    assert entities.Core3ExtractParamValue.__tablename__ == "core3_extract_param_value"
    assert entities.Core3ParamAliasCandidate.__tablename__ == "core3_param_alias_candidate"
    assert entities.Core3ParamValueConflict.__tablename__ == "core3_param_value_conflict"
    assert entities.Core3SkuParamProfile.__tablename__ == "core3_sku_param_profile"

    assert M03_TABLES.issubset(set(Base.metadata.tables))


def test_m03_model_columns_match_contract():
    expected_columns = {
        "core3_param_field_profile": {
            "field_profile_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "raw_param_name",
            "clean_param_name",
            "normalized_param_name",
            "occurrence_count",
            "sku_coverage_count",
            "sku_coverage_rate",
            "unknown_count",
            "unknown_rate",
            "present_count",
            "top_values_json",
            "value_pattern_summary_json",
            "matched_param_code",
            "matched_param_name",
            "param_group",
            "match_type",
            "alias_confidence",
            "candidate_status",
            "review_required",
            "review_status",
            "review_reason",
            "evidence_ids",
            "field_profile_hash",
            "seed_version",
            "rule_version",
            "created_at",
            "updated_at",
        },
        "core3_extract_param_value": {
            "param_value_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "sku_code",
            "model_name",
            "param_code",
            "param_name",
            "param_group",
            "data_type",
            "normalized_value",
            "numeric_value",
            "value_text",
            "unit",
            "value_level",
            "value_presence",
            "source_type",
            "source_priority_rank",
            "raw_param_name",
            "raw_param_value",
            "match_type",
            "parser_type",
            "parser_status",
            "confidence",
            "confidence_level",
            "evidence_ids",
            "primary_evidence_id",
            "quality_flags",
            "conflict_flag",
            "conflict_id",
            "review_required",
            "review_status",
            "param_value_hash",
            "seed_version",
            "parser_version",
            "rule_version",
            "created_at",
            "updated_at",
        },
        "core3_param_alias_candidate": {
            "alias_candidate_id",
            "project_id",
            "category_code",
            "batch_id",
            "raw_param_name",
            "clean_param_name",
            "sku_coverage_rate",
            "unknown_rate",
            "top_values_json",
            "value_pattern_summary_json",
            "suggested_param_code",
            "suggestion_reason",
            "confidence",
            "candidate_type",
            "review_required",
            "review_status",
            "review_decision_json",
            "seed_version",
            "created_at",
            "updated_at",
        },
        "core3_param_value_conflict": {
            "conflict_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "sku_code",
            "param_code",
            "conflict_type",
            "candidate_values_json",
            "preferred_value_json",
            "preferred_source_type",
            "confidence",
            "evidence_ids",
            "quality_flags",
            "review_required",
            "review_status",
            "review_reason",
            "rule_version",
            "created_at",
            "updated_at",
        },
        "core3_sku_param_profile": {
            "sku_param_profile_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "sku_code",
            "model_name",
            "param_values_json",
            "core_picture_params_json",
            "core_gaming_params_json",
            "core_system_params_json",
            "core_eye_care_params_json",
            "param_completeness",
            "known_param_count",
            "unknown_param_count",
            "conflict_count",
            "review_required_count",
            "evidence_ids",
            "quality_summary_json",
            "profile_hash",
            "seed_version",
            "rule_version",
            "created_at",
            "updated_at",
        },
    }

    for table_name, columns in expected_columns.items():
        table_columns = set(Base.metadata.tables[table_name].columns.keys())
        assert columns.issubset(table_columns)


def test_m03_constraints_and_indexes_match_contract():
    expected_unique_constraints = {
        "core3_param_field_profile": "uq_core3_param_field_profile_batch_clean_seed_rule",
        "core3_extract_param_value": "uq_core3_extract_param_value_batch_sku_param_src_ev_rule",
        "core3_param_alias_candidate": "uq_core3_param_alias_candidate_batch_clean_seed",
        "core3_param_value_conflict": "uq_core3_param_value_conflict_batch_sku_param_type_rule",
        "core3_sku_param_profile": "uq_core3_sku_param_profile_batch_sku_seed_rule",
    }
    expected_indexes = {
        "core3_param_field_profile": {
            "ix_core3_param_field_profile_project_category_batch",
            "ix_core3_param_field_profile_matched_param_code",
            "ix_core3_param_field_profile_candidate_status",
            "ix_core3_param_field_profile_review_required",
        },
        "core3_extract_param_value": {
            "ix_core3_extract_param_value_project_category_batch",
            "ix_core3_extract_param_value_sku_param",
            "ix_core3_extract_param_value_param_group",
            "ix_core3_extract_param_value_source_type",
            "ix_core3_extract_param_value_review_required",
            "ix_core3_extract_param_value_hash",
        },
        "core3_param_alias_candidate": {
            "ix_core3_param_alias_candidate_project_category_batch",
            "ix_core3_param_alias_candidate_suggested_param_code",
            "ix_core3_param_alias_candidate_type",
            "ix_core3_param_alias_candidate_review_status",
        },
        "core3_param_value_conflict": {
            "ix_core3_param_value_conflict_project_category_batch",
            "ix_core3_param_value_conflict_sku_param",
            "ix_core3_param_value_conflict_type",
            "ix_core3_param_value_conflict_review_required",
        },
        "core3_sku_param_profile": {
            "ix_core3_sku_param_profile_project_category_batch",
            "ix_core3_sku_param_profile_sku_code",
            "ix_core3_sku_param_profile_hash",
        },
    }

    for table_name, unique_name in expected_unique_constraints.items():
        table = Base.metadata.tables[table_name]
        assert unique_name in {constraint.name for constraint in table.constraints}
        assert expected_indexes[table_name].issubset({index.name for index in table.indexes})


def test_m03_identifiers_are_postgresql_safe():
    for table_name in M03_TABLES:
        table = Base.metadata.tables[table_name]
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63
        for index in table.indexes:
            assert index.name is not None
            assert len(index.name) <= 63


def test_m03_migration_imports_with_expected_revision_chain():
    migration = load_m03_migration()

    assert migration.revision == "0009_core3_param"
    assert migration.down_revision == "0008_core3_evidence"


def test_m03_migration_only_mentions_param_models_not_raw_or_future_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in RAW_SOURCE_TABLES | M00_M02_TABLES | FUTURE_RESULT_TABLES:
        assert table_name not in source
    for model_name in [
        "Core3ParamFieldProfile",
        "Core3ExtractParamValue",
        "Core3ParamAliasCandidate",
        "Core3ParamValueConflict",
        "Core3SkuParamProfile",
    ]:
        assert model_name in source


def test_m03_migration_creates_and_drops_only_m03_tables():
    migration = load_m03_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        create_m03_dependencies(connection)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            inspector = inspect(connection)
            table_names_after_upgrade = set(inspector.get_table_names())

            assert M03_TABLES.issubset(table_names_after_upgrade)
            assert M03_DEPENDENCY_TABLES.issubset(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)
            assert not M00_M02_TABLES.intersection(table_names_after_upgrade)
            assert not FUTURE_RESULT_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            inspector = inspect(connection)
            table_names_after_downgrade = set(inspector.get_table_names())

            assert not M03_TABLES.intersection(table_names_after_downgrade)
            assert M03_DEPENDENCY_TABLES.issubset(table_names_after_downgrade)
        finally:
            migration.op = original_op


def test_m03_json_and_decimal_fields_round_trip_on_sqlite():
    engine = make_sqlite_engine()
    with engine.begin() as connection:
        create_m03_dependencies(connection)
        for table_name in M03_TABLES:
            Base.metadata.tables[table_name].create(bind=connection, checkfirst=True)

    with Session(engine) as session:
        _seed_dependencies(session)
        session.add(
            entities.Core3EvidenceAtom(
                evidence_id="m02ev_param_001",
                evidence_key="sha256:m02:param",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                evidence_type="param_raw",
                evidence_grain="field",
                evidence_field="clean_attr_value",
                clean_table="core3_clean_attribute",
                clean_record_key="attribute:1",
                clean_hash="sha256:m01:attribute",
                clean_version="m01_clean_v1",
                base_confidence=Decimal("0.9000"),
                confidence_level="high",
                evidence_payload_json={"clean_attr_name": "刷新率", "clean_attr_value": "144Hz"},
            )
        )
        session.add(
            entities.Core3ParamFieldProfile(
                field_profile_id="m03fp_refresh_rate",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                clean_param_name="刷新率",
                occurrence_count=1,
                sku_coverage_count=1,
                sku_coverage_rate=Decimal("1.000000"),
                present_count=1,
                top_values_json=[{"value": "144Hz", "count": 1}],
                value_pattern_summary_json={"unit": "Hz"},
                matched_param_code="refresh_rate",
                matched_param_name="刷新率",
                param_group="gaming",
                match_type="seed_alias",
                alias_confidence=Decimal("0.9500"),
                evidence_ids=["m02ev_param_001"],
                field_profile_hash="sha256:m03:field",
                seed_version="tv_param_seed_v1",
                rule_version="m03_param_extraction_v1",
            )
        )
        session.add(
            entities.Core3ExtractParamValue(
                param_value_id="m03pv_refresh_rate",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                param_code="refresh_rate",
                param_name="刷新率",
                param_group="gaming",
                data_type="number",
                normalized_value={"value": 144, "unit": "Hz"},
                numeric_value=Decimal("144.000000"),
                value_text="144Hz",
                unit="Hz",
                value_presence="present",
                source_type="raw_param",
                raw_param_name="刷新率",
                raw_param_value="144Hz",
                match_type="seed_alias",
                parser_status="parsed",
                confidence=Decimal("0.9500"),
                confidence_level="high",
                evidence_ids=["m02ev_param_001"],
                primary_evidence_id="m02ev_param_001",
                quality_flags=[],
                param_value_hash="sha256:m03:param_value",
                seed_version="tv_param_seed_v1",
                parser_version="m03_parser_v1",
                rule_version="m03_param_extraction_v1",
            )
        )
        session.commit()

        field_profile = session.execute(select(entities.Core3ParamFieldProfile)).scalar_one()
        param_value = session.execute(select(entities.Core3ExtractParamValue)).scalar_one()

        assert field_profile.top_values_json == [{"value": "144Hz", "count": 1}]
        assert field_profile.evidence_ids == ["m02ev_param_001"]
        assert param_value.normalized_value == {"value": 144, "unit": "Hz"}
        assert param_value.numeric_value == Decimal("144.000000")


def _seed_dependencies(session: Session) -> None:
    session.add(entities.CategoryProject(project_id="core3_mvp", name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3SourceBatch(
            batch_id="m00_202606130001",
            project_id="core3_mvp",
            category_code="TV",
            batch_type="full",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["attribute_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            status="registered",
            review_status="auto_pass",
        )
    )
    session.flush()
