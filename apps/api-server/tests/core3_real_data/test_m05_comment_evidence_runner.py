from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.comment_evidence_runner import CommentEvidenceRunner
from app.services.core3_real_data.constants import (
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3SourceBatchStatus,
    Core3TargetScopeType,
)
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130005"
RUN_ID = "run-m05-o"
MODULE_RUN_ID_M02 = "module-run-m02-for-m05-o"
MODULE_RUN_ID_M05 = "module-run-m05-o"
SKU_CODE = "TV00029115"
EMPTY_SKU_CODE = "TV_NO_COMMENT"


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
        entities.Core3CommentUnit.__table__,
        entities.Core3CommentUnitEvidenceLink.__table__,
        entities.Core3CommentEvidenceAtom.__table__,
        entities.Core3CommentTopicHint.__table__,
        entities.Core3CommentQualityProfile.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    seed_foundation(session)
    return session


def seed_foundation(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3V2PipelineRun(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_mode="daily_incremental",
            ruleset_version="tv-core3-real-data-v2-0.1.0",
        )
    )
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=MODULE_RUN_ID_M02,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M02",
            batch_id=BATCH_ID,
            status="success",
        )
    )
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=MODULE_RUN_ID_M05,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M05",
            batch_id=BATCH_ID,
            status="pending",
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_id=RUN_ID,
            module_run_id=MODULE_RUN_ID_M02,
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
            review_status="auto_pass",
        )
    )
    session.flush()


def seed_comment_evidence(session: Session) -> None:
    session.add_all(
        [
            entities.Core3EvidenceAtom(**evidence("ev_raw", "comment_raw", "row", "comment_raw", "游戏模式延迟低，玩主机很流畅。")),
            entities.Core3EvidenceAtom(
                **evidence(
                    "ev_sentence",
                    "comment_sentence",
                    "sentence",
                    "comment_sentence:0",
                    "游戏模式延迟低，玩主机很流畅",
                    segment_text_hash="sha256:sentence:gaming",
                    sentence_seq=0,
                )
            ),
            entities.Core3EvidenceAtom(
                **evidence(
                    "ev_dimension",
                    "comment_dimension",
                    "dimension",
                    "comment_dimension",
                    "产品体验/游戏流畅",
                    dimension_path_raw="产品体验/游戏流畅",
                )
            ),
            entities.Core3EvidenceAtom(
                **evidence(
                    "ev_param_ignored",
                    "param_raw",
                    "field",
                    "刷新率",
                    "144Hz",
                    source_table="attribute_data",
                    clean_table="core3_clean_attribute",
                    comment_id=None,
                    comment_text_hash=None,
                )
            ),
        ]
    )
    session.flush()


def evidence(
    evidence_id: str,
    evidence_type: str,
    evidence_grain: str,
    evidence_field: str,
    clean_value: str,
    *,
    source_table: str = "comment_data",
    clean_table: str = "core3_clean_comment",
    comment_id: str | None = "c-001",
    comment_text_hash: str | None = "sha256:comment:001",
    segment_text_hash: str | None = None,
    sentence_seq: int | None = None,
    dimension_path_raw: str | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_key": f"{BATCH_ID}:{SKU_CODE}:{evidence_type}:{evidence_field}:{evidence_id}",
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID_M02,
        "sku_code": SKU_CODE,
        "model_name": "85E7Q",
        "brand_name": "海信",
        "evidence_type": evidence_type,
        "evidence_grain": evidence_grain,
        "evidence_field": evidence_field,
        "evidence_title": evidence_field,
        "source_table": source_table,
        "source_pk": evidence_id,
        "source_row_id": f"{source_table}:{evidence_id}",
        "source_row_hash": f"sha256:m00_row_hash_v1:{evidence_id}",
        "clean_table": clean_table,
        "clean_record_key": f"{clean_table}:{evidence_id}",
        "clean_hash": f"sha256:m01_clean_hash_v1:{evidence_id}",
        "clean_version": "m01_clean_v1",
        "raw_field": evidence_field,
        "raw_value": clean_value,
        "clean_field": evidence_field,
        "clean_value": clean_value,
        "value_presence": "present",
        "text_value": clean_value,
        "text_hash": f"sha256:text:{evidence_id}",
        "comment_id": comment_id,
        "comment_text_hash": comment_text_hash,
        "segment_text_hash": segment_text_hash,
        "sentence_seq": sentence_seq,
        "dimension_path_raw": dimension_path_raw,
        "numeric_values_json": [],
        "quality_status": "ok",
        "quality_flags": [],
        "base_confidence": Decimal("0.9000"),
        "confidence_level": "high",
        "evidence_payload_json": {"sentiment_clean": "正面", "clean_value": clean_value},
        "evidence_status": "current",
        "is_current": True,
        "evidence_version": "m02_evidence_v1",
        "confidence_rule_version": "m02_confidence_v1",
        "asset_version": "default",
        "review_required": False,
        "review_status": "auto_pass",
    }


def make_run_context():
    return build_run_context(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )


def make_target(*sku_codes: str):
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(sku_codes),
        metadata={"batch_id": BATCH_ID, "module_run_id": MODULE_RUN_ID_M05},
    )


def test_m05_comment_evidence_runner_writes_outputs_from_m02_comment_evidence():
    session = make_session()
    seed_comment_evidence(session)
    runner = CommentEvidenceRunner(session)

    first = runner.run(make_run_context(), make_target())
    second = runner.run(make_run_context(), make_target())

    assert first.module_code == "M05"
    assert first.status == "warning"
    assert first.input_count == 3
    assert first.summary_json["sku_count"] == 1
    assert first.summary_json["comment_unit_count"] == 1
    assert first.summary_json["unit_link_count"] == 3
    assert first.summary_json["evidence_atom_count"] == 1
    assert first.summary_json["topic_hint_count"] >= 1
    assert first.summary_json["downstream_ready_sku_count"] == 1
    assert "m05_comment_evidence_review_required" in first.warnings
    assert {impact["module_code"] for impact in first.downstream_impacts} >= {"M06", "M16"}
    assert second.summary_json["comment_unit_count"] == first.summary_json["comment_unit_count"]
    assert second.summary_json["evidence_atom_count"] == first.summary_json["evidence_atom_count"]
    assert second.summary_json["topic_hint_count"] == first.summary_json["topic_hint_count"]
    assert second.summary_json["quality_profile_count"] == first.summary_json["quality_profile_count"]

    assert count_rows(session, entities.Core3CommentUnit) == 1
    assert count_rows(session, entities.Core3CommentEvidenceAtom) == 1
    assert count_rows(session, entities.Core3CommentQualityProfile) == 1
    assert count_rows(session, entities.Core3CommentTopicHint) >= 1
    assert count_rows(session, entities.Core3CommentUnitEvidenceLink) == 3

    profile = session.execute(select(entities.Core3CommentQualityProfile)).scalar_one()
    assert profile.sku_code == SKU_CODE
    assert profile.downstream_ready is True
    assert profile.comment_unit_count == 1


def test_m05_comment_evidence_runner_target_sku_without_comment_evidence_writes_blocked_profile():
    session = make_session()
    seed_comment_evidence(session)
    runner = CommentEvidenceRunner(session)

    result = runner.run(make_run_context(), make_target(EMPTY_SKU_CODE))

    assert result.module_code == "M05"
    assert result.status == "review_required"
    assert result.input_count == 0
    assert result.output_count == 1
    assert result.summary_json["sku_count"] == 1
    assert result.summary_json["blocked_sku_count"] == 1
    assert "m05_comment_evidence_blocked" in result.warnings
    assert "m05_m02_comment_trace_missing" in result.warnings
    assert count_rows(session, entities.Core3CommentUnit) == 0
    assert count_rows(session, entities.Core3CommentEvidenceAtom) == 0
    assert count_rows(session, entities.Core3CommentQualityProfile) == 1

    profile = session.execute(select(entities.Core3CommentQualityProfile)).scalar_one()
    assert profile.sku_code == EMPTY_SKU_CODE
    assert profile.downstream_ready is False
    assert set(profile.blocked_reasons) == {"no_comment_unit", "no_sentence_atom"}


def count_rows(session: Session, model_cls) -> int:
    return session.execute(select(func.count()).select_from(model_cls)).scalar_one()
