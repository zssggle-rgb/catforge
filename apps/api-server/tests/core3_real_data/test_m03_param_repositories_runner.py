from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3SourceBatchStatus,
    Core3TargetScopeType,
)
from app.services.core3_real_data.param_extraction_repositories import (
    ParamEvidenceReader,
    ParamExtractionRepository,
    ParamRepositoryHashConflictError,
)
from app.services.core3_real_data.param_extraction_runner import ParamExtractionRunner
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
RUN_ID = "run-m03-h"
MODULE_RUN_ID = "module-run-m03-h"


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
            module_run_id=MODULE_RUN_ID,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M03",
            batch_id=BATCH_ID,
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_id=RUN_ID,
            module_run_id=MODULE_RUN_ID,
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


def seed_m03_evidence(session: Session) -> None:
    records = [
        evidence("ev_size", evidence_field="尺寸", clean_value="85英寸"),
        evidence("ev_refresh_raw", evidence_field="刷新率", clean_value="144Hz"),
        evidence(
            "ev_refresh_claim",
            evidence_type="promo_sentence",
            evidence_grain="sentence",
            evidence_field="刷新率",
            clean_value="全通道 300Hz 高刷",
            source_table="selling_points_data",
            clean_table="core3_clean_claim_sentence",
            base_confidence=Decimal("0.8000"),
        ),
        evidence("ev_brightness", evidence_field="峰值亮度", clean_value="5200"),
        evidence("ev_unknown_param", evidence_field="未知字段X", clean_value="abc"),
        evidence(
            "ev_quality",
            evidence_type="quality_issue",
            evidence_grain="quality",
            evidence_field="UNKNOWN_VALUE",
            clean_value="参数值存在未知文字",
            clean_table="core3_data_quality_issue",
            quality_status="warning",
            quality_flags=["unknown_value"],
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
    sku_code: str = "TV00029115",
    model_name: str = "85E7Q",
    brand_name: str = "海信",
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
) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_key": f"{BATCH_ID}:TV00029115:{evidence_type}:{evidence_field}:{evidence_id}",
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "sku_code": sku_code,
        "model_name": model_name,
        "brand_name": brand_name,
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
        "evidence_payload_json": {"clean_value": clean_value},
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


def make_target(target_sku_codes=(), *, force_rebuild: bool = False):
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(target_sku_codes),
        metadata={"batch_id": BATCH_ID, "module_run_id": MODULE_RUN_ID, "force_rebuild": force_rebuild},
    )


def test_m03_param_evidence_reader_consumes_only_param_claim_quality_current_evidence():
    session = make_session()
    seed_m03_evidence(session)

    records = ParamEvidenceReader(make_context(session)).list_param_evidence(BATCH_ID)

    evidence_ids = {record.evidence_id for record in records}
    assert evidence_ids == {
        "ev_brightness",
        "ev_size",
        "ev_unknown_param",
        "ev_refresh_raw",
        "ev_refresh_claim",
        "ev_quality",
    }
    assert {record.evidence_type for record in records} == {"param_raw", "promo_sentence", "quality_issue"}
    assert "ev_comment" not in evidence_ids
    assert "ev_market" not in evidence_ids
    assert "ev_old" not in evidence_ids


def test_m03_param_repository_reuses_same_hash_and_blocks_same_key_different_hash():
    session = make_session()
    repository = ParamExtractionRepository(make_context(session))
    payload = {
        "field_profile_id": "m03fp_test",
        "batch_id": BATCH_ID,
        "clean_param_name": "尺寸",
        "normalized_param_name": "尺寸",
        "occurrence_count": 1,
        "sku_coverage_count": 1,
        "sku_coverage_rate": Decimal("1.000000"),
        "unknown_count": 0,
        "unknown_rate": Decimal("0.000000"),
        "present_count": 1,
        "top_values_json": [{"value_text": "85英寸", "count": 1}],
        "value_pattern_summary_json": {"units": ["inch"]},
        "match_type": "exact_alias",
        "alias_confidence": Decimal("0.9500"),
        "candidate_status": "matched",
        "review_required": False,
        "review_status": "auto_pass",
        "evidence_ids": ["ev_size"],
        "field_profile_hash": "hash_same",
        "seed_version": "tv_core3_mvp_seed_v0_2",
        "rule_version": "m03_param_v1",
    }

    first = repository.save_field_profiles([payload])
    second = repository.save_field_profiles([payload])

    assert first.created_count == 1
    assert second.reused_count == 1

    with pytest.raises(ParamRepositoryHashConflictError):
        repository.save_field_profiles([{**payload, "field_profile_id": "m03fp_changed", "field_profile_hash": "hash_changed"}])


def test_m03_param_runner_writes_outputs_and_is_idempotent():
    session = make_session()
    seed_m03_evidence(session)
    runner = ParamExtractionRunner(session)

    first = runner.run(make_run_context(), make_target())
    second = runner.run(make_run_context(), make_target())

    assert first.module_code == "M03"
    assert first.status == "warning"
    assert second.status == "warning"
    assert second.changed_input_count == 0
    assert second.summary_json["write_summary"]["field_profiles"]["reused_count"] == first.summary_json[
        "field_profile_count"
    ]
    assert "m03_param_conflict_review_required" in first.warnings
    assert "m03_alias_candidate_review_required" in first.warnings
    assert {impact["module_code"] for impact in first.downstream_impacts} >= {"M04a", "M08", "M13", "M16"}

    assert count_rows(session, entities.Core3ParamFieldProfile) >= 4
    assert count_rows(session, entities.Core3ExtractParamValue) >= 4
    assert count_rows(session, entities.Core3ParamAliasCandidate) == 1
    assert count_rows(session, entities.Core3ParamValueConflict) >= 2
    assert count_rows(session, entities.Core3SkuParamProfile) == 1

    sku_profile = session.execute(select(entities.Core3SkuParamProfile)).scalar_one()
    assert sku_profile.sku_code == "TV00029115"
    assert "screen_size_inch" in sku_profile.param_values_json
    assert sku_profile.conflict_count >= 2
    assert sku_profile.review_required_count >= 2

    values = session.execute(select(entities.Core3ExtractParamValue)).scalars().all()
    by_param = {value.param_code for value in values}
    assert {"screen_size_inch", "native_refresh_rate_hz", "peak_brightness_nits"}.issubset(by_param)


def test_m03_param_runner_can_rebuild_wider_scope_without_hash_conflict():
    session = make_session()
    seed_m03_evidence(session)
    session.add(
        entities.Core3EvidenceAtom(
            **evidence(
                "ev_size_second_sku",
                sku_code="TV00027487",
                model_name="海信 85N",
                evidence_field="尺寸",
                clean_value="85英寸",
            )
        )
    )
    session.flush()
    runner = ParamExtractionRunner(session)

    first = runner.run(make_run_context(), make_target(["TV00029115"]))
    blocked = runner.run(make_run_context(), make_target())
    rebuilt = runner.run(make_run_context(), make_target(force_rebuild=True))

    assert first.status == "warning"
    assert blocked.status == "failed"
    assert blocked.summary_json["error_code"] == "m03_param_hash_conflict"
    assert rebuilt.status == "warning"
    assert rebuilt.summary_json["sku_profile_count"] == 2

    profile = session.execute(
        select(entities.Core3ParamFieldProfile).where(
            entities.Core3ParamFieldProfile.clean_param_name == "尺寸",
        )
    ).scalar_one()
    assert profile.sku_coverage_count == 2


def count_rows(session: Session, model_cls) -> int:
    return session.execute(select(func.count()).select_from(model_cls)).scalar_one()
