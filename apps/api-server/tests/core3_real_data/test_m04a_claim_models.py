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
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0010_core3_real_data_base_claim_activation.py"

M04A_TABLES = {
    "core3_extract_claim_hit",
    "core3_sku_claim_source_status",
    "core3_sku_claim_activation_base",
}
M04A_DEPENDENCY_TABLES = {
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
M00_M03_TABLES = {
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
    "core3_evidence_atom",
    "core3_evidence_link",
    "core3_param_field_profile",
    "core3_extract_param_value",
    "core3_param_alias_candidate",
    "core3_param_value_conflict",
    "core3_sku_param_profile",
}
FUTURE_RESULT_TABLES = {
    "core3_sku_claim_activation",
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


def load_m04a_migration():
    spec = importlib.util.spec_from_file_location("core3_base_claim_activation_migration", MIGRATION_PATH)
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


def create_m04a_dependencies(connection) -> None:
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
    ]:
        table.create(bind=connection, checkfirst=True)


def test_m04a_models_are_registered():
    assert entities.Core3ExtractClaimHit.__tablename__ == "core3_extract_claim_hit"
    assert entities.Core3SkuClaimSourceStatus.__tablename__ == "core3_sku_claim_source_status"
    assert entities.Core3SkuClaimActivationBase.__tablename__ == "core3_sku_claim_activation_base"

    assert M04A_TABLES.issubset(set(Base.metadata.tables))


def test_m04a_model_columns_match_contract():
    expected_columns = {
        "core3_extract_claim_hit": {
            "claim_hit_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "sku_code",
            "model_name",
            "claim_code",
            "claim_name",
            "claim_group",
            "hit_source_type",
            "source_sentence_key",
            "claim_seq",
            "sentence_seq",
            "claim_fragment",
            "matched_keywords",
            "title_hint",
            "extracted_entity_json",
            "matched_param_codes",
            "match_method",
            "promo_evidence_ids",
            "param_evidence_ids",
            "quality_evidence_ids",
            "match_confidence",
            "quality_flags",
            "review_required",
            "review_status",
            "hit_hash",
            "seed_version",
            "rule_version",
            "created_at",
            "updated_at",
        },
        "core3_sku_claim_source_status": {
            "claim_source_status_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "sku_code",
            "model_name",
            "claim_source_status",
            "structured_claim_count",
            "claim_sentence_count",
            "promo_evidence_count",
            "param_only_claim_count",
            "quality_evidence_ids",
            "missing_signals",
            "conflict_summary_json",
            "status_note",
            "review_required",
            "review_status",
            "status_hash",
            "seed_version",
            "rule_version",
            "created_at",
            "updated_at",
        },
        "core3_sku_claim_activation_base": {
            "claim_activation_base_id",
            "project_id",
            "category_code",
            "batch_id",
            "run_id",
            "module_run_id",
            "sku_code",
            "model_name",
            "claim_code",
            "claim_name",
            "claim_group",
            "claim_type",
            "param_score",
            "promo_score",
            "base_activation_score",
            "activation_level",
            "activation_basis",
            "param_support_json",
            "promo_support_json",
            "missing_signals",
            "conflict_flags",
            "confidence",
            "confidence_level",
            "evidence_ids",
            "param_evidence_ids",
            "promo_evidence_ids",
            "quality_evidence_ids",
            "claim_hit_ids",
            "review_required",
            "review_status",
            "review_reason",
            "activation_hash",
            "seed_version",
            "rule_version",
            "created_at",
            "updated_at",
        },
    }

    for table_name, columns in expected_columns.items():
        table_columns = set(Base.metadata.tables[table_name].columns.keys())
        assert columns.issubset(table_columns)


def test_m04a_constraints_and_indexes_match_contract():
    expected_unique_constraints = {
        "core3_extract_claim_hit": "uq_core3_claim_hit_batch_sku_claim_src_key_rule",
        "core3_sku_claim_source_status": "uq_core3_claim_source_status_batch_sku_seed_rule",
        "core3_sku_claim_activation_base": "uq_core3_claim_activation_base_batch_sku_claim_seed",
    }
    expected_indexes = {
        "core3_extract_claim_hit": {
            "ix_core3_claim_hit_project_category_batch",
            "ix_core3_claim_hit_sku_claim",
            "ix_core3_claim_hit_source_type",
            "ix_core3_claim_hit_review_required",
        },
        "core3_sku_claim_source_status": {
            "ix_core3_claim_source_project_category_batch",
            "ix_core3_claim_source_sku_code",
            "ix_core3_claim_source_status",
            "ix_core3_claim_source_review_required",
        },
        "core3_sku_claim_activation_base": {
            "ix_core3_claim_base_project_category_batch",
            "ix_core3_claim_base_sku_claim",
            "ix_core3_claim_base_group",
            "ix_core3_claim_base_level",
            "ix_core3_claim_base_basis",
            "ix_core3_claim_base_review_required",
            "ix_core3_claim_base_hash",
        },
    }

    for table_name, unique_name in expected_unique_constraints.items():
        table = Base.metadata.tables[table_name]
        assert unique_name in {constraint.name for constraint in table.constraints}
        assert expected_indexes[table_name].issubset({index.name for index in table.indexes})


def test_m04a_identifiers_are_postgresql_safe():
    for table_name in M04A_TABLES:
        table = Base.metadata.tables[table_name]
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63
        for index in table.indexes:
            assert index.name is not None
            assert len(index.name) <= 63


def test_m04a_migration_imports_with_expected_revision_chain():
    migration = load_m04a_migration()

    assert migration.revision == "0010_core3_base_claim"
    assert migration.down_revision == "0009_core3_param"


def test_m04a_migration_only_mentions_m04a_models_not_raw_or_other_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in RAW_SOURCE_TABLES | M00_M03_TABLES | FUTURE_RESULT_TABLES:
        assert table_name not in source
    for model_name in [
        "Core3ExtractClaimHit",
        "Core3SkuClaimSourceStatus",
        "Core3SkuClaimActivationBase",
    ]:
        assert model_name in source


def test_m04a_migration_creates_and_drops_only_m04a_tables():
    migration = load_m04a_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        create_m04a_dependencies(connection)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            inspector = inspect(connection)
            table_names_after_upgrade = set(inspector.get_table_names())

            assert M04A_TABLES.issubset(table_names_after_upgrade)
            assert M04A_DEPENDENCY_TABLES.issubset(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)
            assert not M00_M03_TABLES.intersection(table_names_after_upgrade)
            assert not FUTURE_RESULT_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            inspector = inspect(connection)
            table_names_after_downgrade = set(inspector.get_table_names())

            assert not M04A_TABLES.intersection(table_names_after_downgrade)
            assert M04A_DEPENDENCY_TABLES.issubset(table_names_after_downgrade)
        finally:
            migration.op = original_op


def test_m04a_json_and_decimal_fields_round_trip_on_sqlite():
    engine = make_sqlite_engine()
    with engine.begin() as connection:
        create_m04a_dependencies(connection)
        for table_name in M04A_TABLES:
            Base.metadata.tables[table_name].create(bind=connection, checkfirst=True)

    with Session(engine) as session:
        _seed_dependencies(session)
        session.add(
            entities.Core3ExtractClaimHit(
                claim_hit_id="m04ahit_refresh",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                model_name="85E7Q",
                claim_code="CLAIM_HIGH_REFRESH_RATE",
                claim_name="高刷新率",
                claim_group="gaming",
                hit_source_type="param_support",
                source_sentence_key="",
                matched_keywords=["高刷"],
                extracted_entity_json={"numeric_entities": [{"value": 144, "unit": "Hz"}]},
                matched_param_codes=["native_refresh_rate_hz"],
                match_method="param_support",
                promo_evidence_ids=[],
                param_evidence_ids=["m02ev_param_refresh"],
                quality_evidence_ids=[],
                match_confidence=Decimal("0.9000"),
                quality_flags=[],
                hit_hash="sha256:m04a:hit",
                seed_version="tv_core3_mvp_seed_v0_2",
                rule_version="m04a_claim_activation_v1",
            )
        )
        session.add(
            entities.Core3SkuClaimSourceStatus(
                claim_source_status_id="m04asrc_85e7q",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                model_name="85E7Q",
                claim_source_status="missing_structured_claim",
                structured_claim_count=0,
                claim_sentence_count=0,
                promo_evidence_count=0,
                param_only_claim_count=1,
                quality_evidence_ids=["m02ev_quality_claim_missing"],
                missing_signals=["structured_claim_missing"],
                conflict_summary_json={"claim_conflict_count": 0},
                status_note="该 SKU 本批没有结构化宣传卖点数据。",
                status_hash="sha256:m04a:status",
                seed_version="tv_core3_mvp_seed_v0_2",
                rule_version="m04a_claim_activation_v1",
            )
        )
        session.add(
            entities.Core3SkuClaimActivationBase(
                claim_activation_base_id="m04abase_refresh",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                model_name="85E7Q",
                claim_code="CLAIM_HIGH_REFRESH_RATE",
                claim_name="高刷新率",
                claim_group="gaming",
                claim_type="technical",
                param_score=Decimal("0.9000"),
                promo_score=Decimal("0.0000"),
                base_activation_score=Decimal("0.6300"),
                activation_level="medium",
                activation_basis="param_only",
                param_support_json={"matched_params": [{"param_code": "native_refresh_rate_hz"}]},
                promo_support_json={"matched_sentences": []},
                missing_signals=["promo_missing"],
                conflict_flags=[],
                confidence=Decimal("0.8000"),
                confidence_level="medium",
                evidence_ids=["m02ev_param_refresh"],
                param_evidence_ids=["m02ev_param_refresh"],
                promo_evidence_ids=[],
                quality_evidence_ids=[],
                claim_hit_ids=["m04ahit_refresh"],
                activation_hash="sha256:m04a:activation",
                seed_version="tv_core3_mvp_seed_v0_2",
                rule_version="m04a_claim_activation_v1",
            )
        )
        session.commit()

        hit = session.execute(select(entities.Core3ExtractClaimHit)).scalar_one()
        status = session.execute(select(entities.Core3SkuClaimSourceStatus)).scalar_one()
        activation = session.execute(select(entities.Core3SkuClaimActivationBase)).scalar_one()

        assert hit.matched_keywords == ["高刷"]
        assert hit.match_confidence == Decimal("0.9000")
        assert status.missing_signals == ["structured_claim_missing"]
        assert status.conflict_summary_json == {"claim_conflict_count": 0}
        assert activation.param_support_json == {"matched_params": [{"param_code": "native_refresh_rate_hz"}]}
        assert activation.base_activation_score == Decimal("0.6300")
        assert activation.claim_hit_ids == ["m04ahit_refresh"]


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
            source_tables=["attribute_data", "selling_points_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            status="registered",
            review_status="auto_pass",
        )
    )
    session.flush()
