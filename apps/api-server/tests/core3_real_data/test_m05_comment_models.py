import importlib.util
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0011_core3_real_data_comment_evidence.py"

M05_TABLES = {
    "core3_comment_unit",
    "core3_comment_unit_evidence_link",
    "core3_comment_evidence_atom",
    "core3_comment_topic_hint",
    "core3_comment_quality_profile",
}
M05_DEPENDENCY_TABLES = {
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
FUTURE_RESULT_TABLES = {
    "core3_comment_downstream_signal",
    "core3_user_task_candidate",
    "core3_target_group_profile",
    "core3_battlefield_profile",
    "core3_competitor_selection",
}


class BoundOp:
    def __init__(self, bind):
        self.bind = bind

    def get_bind(self):
        return self.bind


def load_m05_migration():
    spec = importlib.util.spec_from_file_location("core3_comment_evidence_migration", MIGRATION_PATH)
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


def create_m05_dependencies(connection) -> None:
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
    ]:
        table.create(bind=connection, checkfirst=True)


def test_m05_models_are_registered():
    assert entities.Core3CommentUnit.__tablename__ == "core3_comment_unit"
    assert entities.Core3CommentUnitEvidenceLink.__tablename__ == "core3_comment_unit_evidence_link"
    assert entities.Core3CommentEvidenceAtom.__tablename__ == "core3_comment_evidence_atom"
    assert entities.Core3CommentTopicHint.__tablename__ == "core3_comment_topic_hint"
    assert entities.Core3CommentQualityProfile.__tablename__ == "core3_comment_quality_profile"

    assert M05_TABLES.issubset(set(Base.metadata.tables))


def test_m05_common_columns_match_contract():
    common_columns = {
        "project_id",
        "category_code",
        "batch_id",
        "run_id",
        "module_run_id",
        "sku_code",
        "model_name",
        "brand_name",
        "rule_version",
        "asset_version",
        "input_fingerprint",
        "result_hash",
        "is_current",
        "processing_status",
        "review_required",
        "review_status",
        "review_reason_json",
        "created_at",
        "updated_at",
    }

    for table_name in M05_TABLES:
        assert common_columns.issubset(set(Base.metadata.tables[table_name].columns.keys()))


def test_m05_table_specific_columns_match_contract():
    expected_columns = {
        "core3_comment_unit": {
            "comment_unit_id",
            "comment_unit_key",
            "dedup_strategy",
            "comment_id",
            "comment_text_hash",
            "canonical_comment_text",
            "source_comment_evidence_ids",
            "source_sentence_evidence_ids",
            "source_dimension_evidence_ids",
            "source_quality_evidence_ids",
            "raw_dimension_paths",
            "sentiment_hint",
            "low_value_flag",
            "comment_unit_status",
            "confidence",
        },
        "core3_comment_unit_evidence_link": {
            "unit_link_id",
            "comment_unit_id",
            "source_evidence_id",
            "source_evidence_type",
            "link_role",
            "source_row_id",
            "comment_id",
            "comment_text_hash",
            "sentence_hash",
            "dimension_path_raw",
            "quality_issue_type",
        },
        "core3_comment_evidence_atom": {
            "comment_evidence_id",
            "comment_evidence_key",
            "comment_unit_id",
            "sentence_hash",
            "sentence_source_priority",
            "sentence_text",
            "normalized_sentence_text",
            "domain_hints",
            "primary_domain_hint",
            "sentiment_hint",
            "sentiment_source",
            "specificity_score",
            "usable_for_downstream",
            "downstream_block_reasons",
            "confidence",
        },
        "core3_comment_topic_hint": {
            "topic_hint_id",
            "comment_evidence_id",
            "comment_unit_id",
            "topic_code",
            "topic_name",
            "topic_group",
            "match_method",
            "matched_terms",
            "match_source_json",
            "polarity_hint",
            "topic_confidence",
            "is_weak_hint",
            "activates_product_claim",
            "service_guardrail_flag",
            "topic_hint_status",
        },
        "core3_comment_quality_profile": {
            "comment_quality_profile_id",
            "profile_key",
            "raw_comment_row_count",
            "comment_unit_count",
            "sentence_count",
            "usable_sentence_count",
            "duplicate_text_rate",
            "sentiment_distribution_json",
            "domain_distribution_json",
            "topic_distribution_json",
            "sample_status",
            "comment_usability_score",
            "warning_flags",
            "blocked_reasons",
            "downstream_ready",
        },
    }

    for table_name, columns in expected_columns.items():
        assert columns.issubset(set(Base.metadata.tables[table_name].columns.keys()))


def test_m05_constraints_and_indexes_match_contract():
    expected_unique_constraints = {
        "core3_comment_unit": "uq_core3_comment_unit_batch_key_rule",
        "core3_comment_unit_evidence_link": "uq_core3_comment_unit_link_unit_ev_role",
        "core3_comment_evidence_atom": "uq_core3_comment_atom_batch_key_rule",
        "core3_comment_topic_hint": "uq_core3_comment_topic_hint_ev_topic_method",
        "core3_comment_quality_profile": "uq_core3_comment_quality_batch_sku_rule_asset",
    }
    expected_indexes = {
        "core3_comment_unit": {
            "ix_core3_comment_unit_project_category_batch",
            "ix_core3_comment_unit_sku_comment",
            "ix_core3_comment_unit_sku_text_hash",
            "ix_core3_comment_unit_review_required",
        },
        "core3_comment_unit_evidence_link": {
            "ix_core3_comment_unit_link_project_batch",
            "ix_core3_comment_unit_link_source_ev",
            "ix_core3_comment_unit_link_ev_type",
        },
        "core3_comment_evidence_atom": {
            "ix_core3_comment_atom_project_batch",
            "ix_core3_comment_atom_sku_unit",
            "ix_core3_comment_atom_primary_domain",
            "ix_core3_comment_atom_downstream",
        },
        "core3_comment_topic_hint": {
            "ix_core3_comment_topic_project_batch",
            "ix_core3_comment_topic_sku_topic",
            "ix_core3_comment_topic_group",
            "ix_core3_comment_topic_status",
        },
        "core3_comment_quality_profile": {
            "ix_core3_comment_quality_project_batch",
            "ix_core3_comment_quality_sku_sample",
            "ix_core3_comment_quality_downstream_ready",
            "ix_core3_comment_quality_review_required",
        },
    }

    for table_name, unique_name in expected_unique_constraints.items():
        table = Base.metadata.tables[table_name]
        assert unique_name in {constraint.name for constraint in table.constraints}
        assert expected_indexes[table_name].issubset({index.name for index in table.indexes})


def test_m05_identifiers_are_postgresql_safe():
    for table_name in M05_TABLES:
        table = Base.metadata.tables[table_name]
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63
        for index in table.indexes:
            assert index.name is not None
            assert len(index.name) <= 63


def test_m05_migration_imports_with_expected_revision_chain():
    migration = load_m05_migration()

    assert migration.revision == "0011_core3_comment_evidence"
    assert migration.down_revision == "0010_core3_base_claim"


def test_m05_migration_only_mentions_m05_models_not_raw_or_future_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table_name in RAW_SOURCE_TABLES | FUTURE_RESULT_TABLES:
        assert table_name not in source
    for model_name in [
        "Core3CommentUnit",
        "Core3CommentUnitEvidenceLink",
        "Core3CommentEvidenceAtom",
        "Core3CommentTopicHint",
        "Core3CommentQualityProfile",
    ]:
        assert model_name in source


def test_m05_migration_creates_and_drops_only_m05_tables():
    migration = load_m05_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        create_m05_dependencies(connection)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            inspector = inspect(connection)
            table_names_after_upgrade = set(inspector.get_table_names())

            assert M05_TABLES.issubset(table_names_after_upgrade)
            assert M05_DEPENDENCY_TABLES.issubset(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)
            assert not FUTURE_RESULT_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            inspector = inspect(connection)
            table_names_after_downgrade = set(inspector.get_table_names())

            assert not M05_TABLES.intersection(table_names_after_downgrade)
            assert M05_DEPENDENCY_TABLES.issubset(table_names_after_downgrade)
        finally:
            migration.op = original_op


def test_m05_json_and_decimal_fields_round_trip_on_sqlite():
    engine = make_sqlite_engine()
    with engine.begin() as connection:
        create_m05_dependencies(connection)
        for table_name in M05_TABLES:
            Base.metadata.tables[table_name].create(bind=connection, checkfirst=True)

    with Session(engine) as session:
        session.add(
            entities.Core3CommentUnit(
                comment_unit_id="m05unit_85e7q_1",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                model_name="85E7Q",
                brand_name="海信",
                comment_unit_key="comment_unit:TV00029115:hash1",
                dedup_strategy="text_hash",
                comment_text_hash="hash1",
                canonical_comment_text="画质清晰，打游戏流畅",
                canonical_text_length=10,
                source_row_count=2,
                source_sentence_count=1,
                source_dimension_count=1,
                source_quality_issue_count=0,
                source_comment_evidence_ids=["m02_comment_1"],
                source_sentence_evidence_ids=["m02_sentence_1"],
                source_dimension_evidence_ids=["m02_dimension_1"],
                source_quality_evidence_ids=[],
                raw_dimension_paths=["产品体验/画质"],
                sentiment_raw_set=["positive"],
                sentiment_hint="positive",
                low_value_reasons=[],
                duplicate_source_count=2,
                comment_unit_status="usable",
                quality_flags=[],
                confidence=Decimal("0.9000"),
                confidence_level="high",
                input_fingerprint="sha256:m05:input",
                result_hash="sha256:m05:unit",
            )
        )
        session.add(
            entities.Core3CommentQualityProfile(
                comment_quality_profile_id="m05quality_85e7q",
                project_id="core3_mvp",
                category_code="TV",
                batch_id="m00_202606130001",
                sku_code="TV00029115",
                model_name="85E7Q",
                brand_name="海信",
                profile_key="comment_quality:TV00029115",
                raw_comment_row_count=3621,
                comment_unit_count=3000,
                distinct_comment_id_count=3000,
                distinct_comment_text_count=2800,
                sentence_count=5000,
                usable_sentence_count=4100,
                low_value_unit_count=200,
                low_value_sentence_count=260,
                duplicate_text_rate=Decimal("0.120000"),
                duplicate_row_rate=Decimal("0.080000"),
                empty_dimension_count=100,
                empty_dimension_rate=Decimal("0.030000"),
                sentiment_distribution_json={"positive": 3200, "negative": 500, "unknown": 1300},
                sentiment_unknown_rate=Decimal("0.260000"),
                sentiment_conflict_rate=Decimal("0.010000"),
                domain_distribution_json={"product_experience": 2800},
                topic_distribution_json={"TOPIC_PICTURE_QUALITY": 1200},
                service_installation_share=Decimal("0.050000"),
                product_experience_share=Decimal("0.560000"),
                negative_sentence_rate=Decimal("0.100000"),
                sample_status="sufficient",
                comment_usability_score=Decimal("0.820000"),
                quality_summary={"ready_reason": "评论样本充足"},
                warning_flags=[],
                blocked_reasons=[],
                downstream_ready=True,
                input_fingerprint="sha256:m05:input",
                result_hash="sha256:m05:quality",
            )
        )
        session.commit()

        unit = session.execute(select(entities.Core3CommentUnit)).scalar_one()
        profile = session.execute(select(entities.Core3CommentQualityProfile)).scalar_one()

        assert unit.raw_dimension_paths == ["产品体验/画质"]
        assert unit.confidence == Decimal("0.9000")
        assert profile.sentiment_distribution_json["positive"] == 3200
        assert profile.comment_usability_score == Decimal("0.820000")
