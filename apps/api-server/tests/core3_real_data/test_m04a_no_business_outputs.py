from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.base_claim_activation_runner import BaseClaimActivationRunner
from app.services.core3_real_data.constants import (
    CORE3_TARGET_SKU_85E7Q,
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3TargetScopeType,
)
from app.services.core3_real_data.param_extraction_runner import ParamExtractionRunner
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget

from .test_m02_no_business_outputs import run_85e7q_no_claim_m02_fixture


PROJECT_ID = "core3_mvp"
RUN_ID = "run-m04a-j"
MODULE_RUN_ID_M03 = "module-run-m03-for-m04a-j"
MODULE_RUN_ID_M04A = "module-run-m04a-j"

FORBIDDEN_M04A_DOWNSTREAM_FIELDS = {
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "candidate_id",
    "competitor_type",
    "component_scores",
    "selection_slot",
    "business_conclusion",
    "business_conclusion_cn",
    "report_payload",
    "report_content",
    "evidence_card",
    "comment_score",
    "market_score",
    "final_claim_score",
}


def test_m04a_85e7q_fixture_missing_claim_uses_param_only_and_never_fabricates_promo_evidence():
    session, _batch_id, result = run_85e7q_m04a_fixture()

    assert result.module_code == "M04a"
    assert result.status == "warning"
    assert result.summary_json["claim_hit_count"] == 0
    assert result.summary_json["missing_structured_claim_sku_count"] == 1
    assert result.summary_json["by_evidence_type"] == {
        "param_raw": 6,
        "quality_issue": 5,
    }
    assert "comment_raw" not in result.summary_json["by_evidence_type"]
    assert "comment_sentence" not in result.summary_json["by_evidence_type"]
    assert "comment_dimension" not in result.summary_json["by_evidence_type"]
    assert "market_fact" not in result.summary_json["by_evidence_type"]

    source_status = session.execute(select(entities.Core3SkuClaimSourceStatus)).scalar_one()
    assert source_status.sku_code == CORE3_TARGET_SKU_85E7Q
    assert source_status.model_name == "85E7Q"
    assert source_status.claim_source_status == "missing_structured_claim"
    assert source_status.structured_claim_count == 0
    assert source_status.claim_sentence_count == 0
    assert source_status.promo_evidence_count == 0
    assert source_status.param_only_claim_count == 4
    assert "structured_claim_missing" in source_status.missing_signals
    assert "claim_coverage_missing" in source_status.missing_signals
    assert "不代表没有卖点" in source_status.status_note

    claim_hits = session.execute(select(entities.Core3ExtractClaimHit)).scalars().all()
    assert claim_hits == []

    claims_by_code = _base_claims_by_code(session)
    assert len(claims_by_code) == 20
    assert all(claim.promo_evidence_ids == [] for claim in claims_by_code.values())
    assert all(claim.claim_hit_ids == [] for claim in claims_by_code.values())

    large_screen = claims_by_code["CLAIM_LARGE_SCREEN_IMMERSION"]
    high_refresh = claims_by_code["CLAIM_HIGH_REFRESH_RATE"]
    assert large_screen.activation_basis == "param_only"
    assert large_screen.activation_level in {"low", "medium"}
    assert large_screen.param_evidence_ids
    assert high_refresh.activation_basis == "param_only"
    assert high_refresh.activation_level in {"low", "medium"}
    assert high_refresh.param_evidence_ids

    for claim_code in [
        "CLAIM_INSTALLATION_SERVICE_ASSURANCE",
        "CLAIM_VALUE_FOR_MONEY",
        "CLAIM_SPORTS_MOTION_SMOOTH",
        "CLAIM_ELDER_FRIENDLY_SMART",
        "CLAIM_NO_AD_OR_CLEAN_SYSTEM",
    ]:
        assert claims_by_code[claim_code].activation_level != "high"


def test_m04a_ignores_comment_and_market_changes_for_runner_output_hash():
    session, batch_id, result = run_85e7q_m04a_fixture()
    baseline = BaseClaimActivationRunner(session).run(
        _make_run_context(batch_id),
        _make_target(batch_id, "module-run-m04a-j-baseline"),
    )
    baseline_hashes = _activation_hashes(session)

    _add_out_of_scope_evidence(session, batch_id)
    after_out_of_scope = BaseClaimActivationRunner(session).run(
        _make_run_context(batch_id),
        _make_target(batch_id, "module-run-m04a-j-after-out-of-scope"),
    )

    assert baseline.changed_input_count == 0
    assert after_out_of_scope.changed_input_count == 0
    assert after_out_of_scope.output_hash == baseline.output_hash
    assert after_out_of_scope.summary_json["input_evidence_count"] == result.summary_json["input_evidence_count"]
    assert after_out_of_scope.summary_json["by_evidence_type"] == result.summary_json["by_evidence_type"]
    assert _activation_hashes(session) == baseline_hashes


def test_m04a_outputs_stay_inside_base_claim_boundary():
    session, _, result = run_85e7q_m04a_fixture()

    assert _m04b_output_count(session, entities.Core3SkuClaimCommentValidation) == 0
    assert _m04b_output_count(session, entities.Core3SkuClaimActivation) == 0
    assert _m04b_output_count(session, entities.Core3ClaimCommentReviewIssue) == 0
    assert_no_m04a_downstream_fields(result.model_dump())

    for source_status in session.execute(select(entities.Core3SkuClaimSourceStatus)).scalars():
        assert_no_m04a_downstream_fields(_record_payload(source_status))
    for claim_hit in session.execute(select(entities.Core3ExtractClaimHit)).scalars():
        assert_no_m04a_downstream_fields(_record_payload(claim_hit))
    for base_claim in session.execute(select(entities.Core3SkuClaimActivationBase)).scalars():
        assert_no_m04a_downstream_fields(_record_payload(base_claim))
        assert_no_m04a_downstream_fields(base_claim.param_support_json)
        assert_no_m04a_downstream_fields(base_claim.promo_support_json)


def run_85e7q_m04a_fixture() -> tuple[Session, str, Any]:
    session, batch_id, _ = run_85e7q_no_claim_m02_fixture()
    _create_m03_m04a_tables(session)

    m03_result = ParamExtractionRunner(session).run(
        _make_run_context(batch_id),
        _make_target(batch_id, MODULE_RUN_ID_M03),
    )
    assert m03_result.module_code == "M03"
    assert m03_result.status == "warning"
    assert m03_result.summary_json["by_evidence_type"] == {
        "param_raw": 6,
        "quality_issue": 5,
    }

    m04a_result = BaseClaimActivationRunner(session).run(
        _make_run_context(batch_id),
        _make_target(batch_id, MODULE_RUN_ID_M04A),
    )
    assert m04a_result.status == "warning"
    return session, batch_id, m04a_result


def _create_m03_m04a_tables(session: Session) -> None:
    bind = session.get_bind()
    for table in [
        entities.Core3ParamFieldProfile.__table__,
        entities.Core3ExtractParamValue.__table__,
        entities.Core3ParamAliasCandidate.__table__,
        entities.Core3ParamValueConflict.__table__,
        entities.Core3SkuParamProfile.__table__,
        entities.Core3ExtractClaimHit.__table__,
        entities.Core3SkuClaimSourceStatus.__table__,
        entities.Core3SkuClaimActivationBase.__table__,
        entities.Core3SkuClaimCommentValidation.__table__,
        entities.Core3SkuClaimActivation.__table__,
        entities.Core3ClaimCommentReviewIssue.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)


def _m04b_output_count(session: Session, model_cls: Any) -> int:
    return len(session.execute(select(model_cls)).scalars().all())


def _make_run_context(batch_id: str):
    return build_run_context(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )


def _make_target(batch_id: str, module_run_id: str) -> Core3ModuleTarget:
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=(CORE3_TARGET_SKU_85E7Q,),
        metadata={"batch_id": batch_id, "module_run_id": module_run_id},
    )


def _base_claims_by_code(session: Session) -> dict[str, entities.Core3SkuClaimActivationBase]:
    rows = session.execute(select(entities.Core3SkuClaimActivationBase)).scalars().all()
    return {row.claim_code: row for row in rows}


def _activation_hashes(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(entities.Core3SkuClaimActivationBase).order_by(entities.Core3SkuClaimActivationBase.claim_code)
    ).scalars()
    return {row.claim_code: row.activation_hash for row in rows}


def _record_payload(record: Any) -> dict[str, Any]:
    return {column.name: getattr(record, column.name) for column in record.__table__.columns}


def assert_no_m04a_downstream_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        assert FORBIDDEN_M04A_DOWNSTREAM_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_m04a_downstream_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_m04a_downstream_fields(item)


def _add_out_of_scope_evidence(session: Session, batch_id: str) -> None:
    records = [
        _evidence(
            batch_id,
            "m04a_j_comment_raw",
            evidence_type="comment_raw",
            evidence_grain="row",
            evidence_field="comment_content",
            clean_value="游戏很流畅，安装也很快",
            source_table="comment_data",
            clean_table="core3_clean_comment",
        ),
        _evidence(
            batch_id,
            "m04a_j_comment_sentence",
            evidence_type="comment_sentence",
            evidence_grain="sentence",
            evidence_field="comment_sentence",
            clean_value="看球赛没有拖影",
            source_table="comment_data",
            clean_table="core3_clean_comment_sentence",
        ),
        _evidence(
            batch_id,
            "m04a_j_comment_dimension",
            evidence_type="comment_dimension",
            evidence_grain="dimension",
            evidence_field="comment_dimension",
            clean_value="产品体验/画质体验",
            source_table="comment_data",
            clean_table="core3_clean_comment_dimension",
            evidence_payload_json={"primary_dim_raw": "产品体验", "secondary_dim_raw": "画质体验"},
        ),
        _evidence(
            batch_id,
            "m04a_j_market_fact",
            evidence_type="market_fact",
            evidence_grain="row",
            evidence_field="sales_volume",
            clean_value="9999",
            source_table="week_sales_data",
            clean_table="core3_clean_market_weekly",
        ),
    ]
    session.add_all(entities.Core3EvidenceAtom(**record) for record in records)
    session.flush()


def _evidence(
    batch_id: str,
    evidence_id: str,
    *,
    evidence_type: str,
    evidence_grain: str,
    evidence_field: str,
    clean_value: str,
    source_table: str,
    clean_table: str,
    evidence_payload_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "evidence_key": f"{batch_id}:{CORE3_TARGET_SKU_85E7Q}:{evidence_type}:{evidence_field}:{evidence_id}",
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": batch_id,
        "run_id": RUN_ID,
        "module_run_id": "module-run-m04a-j-out-of-scope",
        "sku_code": CORE3_TARGET_SKU_85E7Q,
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
        "text_value": clean_value,
        "value_presence": "present",
        "numeric_values_json": [],
        "quality_status": "ok",
        "quality_flags": [],
        "base_confidence": Decimal("0.9000"),
        "confidence_level": "high",
        "evidence_payload_json": evidence_payload_json or {"clean_value": clean_value},
        "evidence_status": "current",
        "is_current": True,
        "evidence_version": "m02_evidence_v1",
        "confidence_rule_version": "m02_confidence_v1",
        "asset_version": "default",
        "review_required": False,
        "review_status": "auto_pass",
        "created_at": datetime(2026, 6, 13, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 13, tzinfo=timezone.utc),
    }
