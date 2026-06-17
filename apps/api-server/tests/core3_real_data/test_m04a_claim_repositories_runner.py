from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.base_claim_activation_repositories import (
    ClaimActivationRepository,
    ClaimActivationRepositoryHashConflictError,
    ClaimEvidenceReader,
)
from app.services.core3_real_data.base_claim_activation_runner import BaseClaimActivationRunner
from app.services.core3_real_data.base_claim_seed_loader import StdClaimSeedLoader
from app.services.core3_real_data.constants import (
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3SourceBatchStatus,
    Core3TargetScopeType,
)
from app.services.core3_real_data.param_extraction_runner import ParamExtractionRunner
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130004a"
RUN_ID = "run-m04a-h"
MODULE_RUN_ID_M03 = "module-run-m03-for-m04a-h"
MODULE_RUN_ID_M04A = "module-run-m04a-h"
SKU_CODE = "TV00029115"


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
        entities.Core3ParamFieldProfile.__table__,
        entities.Core3ExtractParamValue.__table__,
        entities.Core3ParamAliasCandidate.__table__,
        entities.Core3ParamValueConflict.__table__,
        entities.Core3SkuParamProfile.__table__,
        entities.Core3ExtractClaimHit.__table__,
        entities.Core3SkuClaimSourceStatus.__table__,
        entities.Core3SkuClaimActivationBase.__table__,
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
            module_run_id=MODULE_RUN_ID_M03,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M03",
            batch_id=BATCH_ID,
        )
    )
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=MODULE_RUN_ID_M04A,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M04a",
            batch_id=BATCH_ID,
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_id=RUN_ID,
            module_run_id=MODULE_RUN_ID_M03,
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


def seed_m04a_evidence(session: Session) -> None:
    records = [
        evidence("ev_miniled", evidence_field="Mini LED", clean_value="支持"),
        evidence("ev_size", evidence_field="尺寸", clean_value="85英寸"),
        evidence("ev_refresh", evidence_field="刷新率", clean_value="144Hz"),
        evidence("ev_hdmi", evidence_field="HDMI2.1", clean_value="2个"),
        evidence(
            "ev_promo_game",
            evidence_type="promo_sentence",
            evidence_grain="sentence",
            evidence_field="卖点句",
            clean_value="Mini LED 背光配合 144Hz 高刷和 HDMI2.1 游戏接口，观影游戏都流畅。",
            source_table="selling_points_data",
            clean_table="core3_clean_claim_sentence",
            base_confidence=Decimal("0.9000"),
            evidence_payload_json={
                "claim_seq": 1,
                "sentence_seq": 0,
                "sentence_text": "Mini LED 背光配合 144Hz 高刷和 HDMI2.1 游戏接口，观影游戏都流畅。",
            },
        ),
        evidence(
            "ev_quality",
            evidence_type="quality_issue",
            evidence_grain="quality",
            evidence_field="UNKNOWN_VALUE",
            clean_value="参数值存在未知文字",
            clean_table="core3_data_quality_issue",
            quality_status="warning",
            quality_flags=["unknown_value"],
            evidence_payload_json={"domain": "param", "issue_type": "unknown_value"},
        ),
        evidence(
            "ev_comment",
            evidence_type="comment_sentence",
            evidence_grain="sentence",
            evidence_field="评论",
            clean_value="打游戏很流畅",
            source_table="comment_data",
            clean_table="core3_clean_comment_sentence",
        ),
        evidence(
            "ev_market",
            evidence_type="market_fact",
            evidence_grain="row",
            evidence_field="销量",
            clean_value="100",
            source_table="week_sales_data",
            clean_table="core3_clean_market_weekly",
        ),
        evidence("ev_old", evidence_field="刷新率", clean_value="120Hz", evidence_status="superseded", is_current=False),
    ]
    session.add_all(entities.Core3EvidenceAtom(**record) for record in records)
    session.flush()


def evidence(
    evidence_id: str,
    *,
    evidence_type: str = "param_raw",
    evidence_grain: str = "field",
    evidence_field: str,
    clean_value: str,
    source_table: str = "attribute_data",
    clean_table: str = "core3_clean_attribute",
    base_confidence: Decimal = Decimal("0.9000"),
    quality_status: str = "ok",
    quality_flags: list[str] | None = None,
    evidence_status: str = "current",
    is_current: bool = True,
    evidence_payload_json: dict | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_key": f"{BATCH_ID}:{SKU_CODE}:{evidence_type}:{evidence_field}:{evidence_id}",
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID_M03,
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
        "numeric_values_json": [],
        "quality_status": quality_status,
        "quality_flags": quality_flags or [],
        "base_confidence": base_confidence,
        "confidence_level": "high" if base_confidence >= Decimal("0.8500") else "medium",
        "evidence_payload_json": evidence_payload_json or {"clean_value": clean_value},
        "evidence_status": evidence_status,
        "is_current": is_current,
        "evidence_version": "m02_evidence_v1",
        "confidence_rule_version": "m02_confidence_v1",
        "asset_version": "default",
        "review_required": quality_status != "ok",
        "review_status": "review_required" if quality_status != "ok" else "auto_pass",
    }


def make_context(session: Session) -> Core3RepositoryContext:
    return Core3RepositoryContext(db=session, project_id=PROJECT_ID)


def make_run_context():
    return build_run_context(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )


def make_target(module_run_id: str, *, force_rebuild: bool = False):
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        metadata={"batch_id": BATCH_ID, "module_run_id": module_run_id, "force_rebuild": force_rebuild},
    )


def test_m04a_claim_evidence_reader_consumes_only_claim_param_quality_current_evidence():
    session = make_session()
    seed_m04a_evidence(session)

    records = ClaimEvidenceReader(make_context(session)).list_claim_evidence(BATCH_ID)

    evidence_ids = {record.evidence_id for record in records}
    assert evidence_ids == {
        "ev_miniled",
        "ev_size",
        "ev_refresh",
        "ev_hdmi",
        "ev_promo_game",
        "ev_quality",
    }
    assert {record.evidence_type for record in records} == {"param_raw", "promo_sentence", "quality_issue"}
    assert "ev_comment" not in evidence_ids
    assert "ev_market" not in evidence_ids
    assert "ev_old" not in evidence_ids


def test_m04a_claim_activation_repository_reuses_same_hash_and_blocks_changed_hash():
    session = make_session()
    repository = ClaimActivationRepository(make_context(session))
    payload = {
        "claim_source_status_id": "m04asrc_test",
        "batch_id": BATCH_ID,
        "sku_code": SKU_CODE,
        "model_name": "85E7Q",
        "claim_source_status": "has_structured_claim",
        "structured_claim_count": 1,
        "claim_sentence_count": 1,
        "promo_evidence_count": 1,
        "param_only_claim_count": 0,
        "quality_evidence_ids": [],
        "missing_signals": [],
        "conflict_summary_json": {},
        "status_note": "该 SKU 本批有可用结构化宣传卖点。",
        "review_required": False,
        "review_status": "auto_pass",
        "status_hash": "hash_same",
        "seed_version": "tv_core3_mvp_seed_v0_2",
        "rule_version": "m04a_claim_activation_v1",
    }

    first = repository.save_source_statuses([payload])
    second = repository.save_source_statuses([payload])

    assert first.created_count == 1
    assert second.reused_count == 1

    with pytest.raises(ClaimActivationRepositoryHashConflictError):
        repository.save_source_statuses(
            [{**payload, "claim_source_status_id": "m04asrc_changed", "status_hash": "hash_changed"}]
        )

    rebuilt = repository.save_source_statuses(
        [{**payload, "claim_source_status_id": "m04asrc_changed", "status_hash": "hash_changed"}],
        replace_on_hash_conflict=True,
    )

    assert rebuilt.reused_count == 1
    source_status = session.execute(select(entities.Core3SkuClaimSourceStatus)).scalar_one()
    assert source_status.claim_source_status_id == "m04asrc_test"
    assert source_status.status_hash == "hash_changed"


def test_m04a_base_claim_activation_runner_writes_outputs_and_is_idempotent():
    session = make_session()
    seed_m04a_evidence(session)
    ParamExtractionRunner(session).run(make_run_context(), make_target(MODULE_RUN_ID_M03))
    runner = BaseClaimActivationRunner(session)

    first = runner.run(make_run_context(), make_target(MODULE_RUN_ID_M04A))
    second = runner.run(make_run_context(), make_target(MODULE_RUN_ID_M04A))

    seed_claim_count = len(StdClaimSeedLoader().load_seed().standard_claims)
    assert first.module_code == "M04a"
    assert first.status == "warning"
    assert second.status == "warning"
    assert second.changed_input_count == 0
    assert second.summary_json["write_summary"]["source_statuses"]["reused_count"] == 1
    assert second.summary_json["write_summary"]["activation_bases"]["reused_count"] == seed_claim_count
    assert "m04a_claim_activation_review_required" in first.warnings
    assert {impact["module_code"] for impact in first.downstream_impacts} >= {"M04b", "M08", "M11.5", "M13", "M16"}

    assert count_rows(session, entities.Core3SkuClaimSourceStatus) == 1
    assert count_rows(session, entities.Core3ExtractClaimHit) >= 3
    assert count_rows(session, entities.Core3SkuClaimActivationBase) == seed_claim_count

    source_status = session.execute(select(entities.Core3SkuClaimSourceStatus)).scalar_one()
    assert source_status.claim_source_status == "has_structured_claim"
    assert source_status.promo_evidence_count == 1
    assert source_status.param_only_claim_count >= 0

    mini_led = session.execute(
        select(entities.Core3SkuClaimActivationBase).where(
            entities.Core3SkuClaimActivationBase.claim_code == "CLAIM_MINI_LED_BACKLIGHT"
        )
    ).scalar_one()
    assert mini_led.activation_basis == "param_and_promo"
    assert mini_led.activation_level in {"medium", "high"}
    assert set(mini_led.evidence_ids) >= {"ev_miniled", "ev_promo_game"}


def test_m04a_base_claim_activation_runner_can_force_rebuild_hash_conflict():
    session = make_session()
    seed_m04a_evidence(session)
    ParamExtractionRunner(session).run(make_run_context(), make_target(MODULE_RUN_ID_M03))
    runner = BaseClaimActivationRunner(session)

    first = runner.run(make_run_context(), make_target(MODULE_RUN_ID_M04A))
    source_status = session.execute(select(entities.Core3SkuClaimSourceStatus)).scalar_one()
    original_hash = source_status.status_hash
    source_status.status_hash = "stale_hash_from_previous_partial_run"
    session.flush()

    blocked = runner.run(make_run_context(), make_target(MODULE_RUN_ID_M04A))
    rebuilt = runner.run(make_run_context(), make_target(MODULE_RUN_ID_M04A, force_rebuild=True))

    assert first.status == "warning"
    assert blocked.status == "failed"
    assert blocked.summary_json["error_code"] == "m04a_claim_activation_hash_conflict"
    assert rebuilt.status == "warning"
    assert rebuilt.summary_json["write_summary"]["source_statuses"]["reused_count"] == 1
    assert source_status.status_hash == original_hash


def count_rows(session: Session, model_cls) -> int:
    return session.execute(select(func.count()).select_from(model_cls)).scalar_one()
