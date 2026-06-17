from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.core3_real_data import (
    BaseClaimActivationRunRequest,
    BaseClaimActivationRunResult,
    ClaimActivationBaseRead,
    ClaimActivationBasis,
    ClaimActivationLevel,
    ClaimConfidenceLevel,
    ClaimGroup,
    ClaimHitQuery,
    ClaimHitRead,
    ClaimHitSourceType,
    ClaimMatchMethod,
    ClaimReviewStatus,
    ClaimSourceStatus,
    ClaimSourceStatusQuery,
    ClaimSourceStatusRead,
    ClaimType,
    Core3BaseClaimActivationRunApiRequest,
    Core3ClaimActivationBaseListOut,
    Core3ClaimHitListOut,
    Core3ClaimSourceStatusListOut,
    SkuClaimBaseResponse,
    StdClaimDefinition,
    StdClaimSeed,
)
from app.services.core3_real_data.constants import (
    CORE3_M04A_MODULE_VERSION,
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    Core3RunStatus,
)


CREATED_AT = "2026-06-13T00:00:00Z"
UPDATED_AT = "2026-06-13T00:00:01Z"
BASE_READ = {
    "project_id": "core3_mvp",
    "category_code": "TV",
    "batch_id": "m00_202606130001",
    "run_id": "run-m04a",
    "module_run_id": "module-run-m04a",
    "sku_code": "TV00029115",
    "model_name": "85E7Q",
    "created_at": CREATED_AT,
    "updated_at": UPDATED_AT,
}
FORBIDDEN_M04A_BUSINESS_FIELDS = {
    "comment_signal",
    "comment_validation_score",
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "business_conclusion",
    "report_payload",
    "report_content",
    "rank",
    "score",
}


def test_m04a_claim_enums_match_sop_contract():
    assert [item.value for item in ClaimHitSourceType] == [
        "promo_raw",
        "promo_sentence",
        "param_support",
        "quality_gap",
    ]
    assert [item.value for item in ClaimSourceStatus] == [
        "has_structured_claim",
        "missing_structured_claim",
        "claim_data_insufficient",
        "claim_conflict",
    ]
    assert [item.value for item in ClaimActivationBasis] == [
        "param_and_promo",
        "param_only",
        "promo_only",
        "insufficient",
    ]
    assert [item.value for item in ClaimActivationLevel] == ["high", "medium", "low", "unknown"]
    assert [item.value for item in ClaimMatchMethod] == [
        "exact_alias",
        "keyword",
        "entity",
        "param_support",
        "quality_gap",
    ]
    assert {item.value for item in ClaimGroup} >= {"picture", "gaming", "eye_care", "smart", "service"}
    assert [item.value for item in ClaimType] == [
        "technical",
        "experience",
        "service",
        "value",
        "design",
        "mixed",
    ]
    assert [item.value for item in ClaimConfidenceLevel] == ["high", "medium", "low", "unknown"]
    assert [item.value for item in ClaimReviewStatus] == [
        "auto_pass",
        "review_required",
        "approved",
        "rejected",
        "waived",
    ]


def test_std_claim_seed_validates_required_structure_and_unique_codes():
    definition = StdClaimDefinition(
        claim_code="claim_high_refresh_rate",
        claim_name="高刷新率",
        claim_group=ClaimGroup.GAMING,
        claim_type=ClaimType.TECHNICAL,
        aliases=["高刷", "高刷新率"],
        keywords=["刷新率", "流畅"],
        promo_keywords=["144Hz", "高刷"],
        supporting_param_codes=["native_refresh_rate_hz", "system_refresh_rate_hz"],
        mapped_param_codes=["native_refresh_rate_hz"],
        mapped_task_codes=["task_gaming"],
        mapped_battlefield_codes=["battlefield_game_sport"],
        activation_rule={"param_threshold": {"native_refresh_rate_hz": 120}},
        param_only_allowed=True,
        priority=10,
    )
    seed = StdClaimSeed(standard_claims=[definition])

    assert seed.seed_version == CORE3_M04A_SEED_VERSION
    assert seed.model_dump()["standard_claims"][0]["claim_group"] == "gaming"

    with pytest.raises(ValidationError, match="standard_claims"):
        StdClaimSeed(standard_claims=[])
    with pytest.raises(ValidationError, match="claim_code must be unique"):
        StdClaimSeed(standard_claims=[definition, definition])
    with pytest.raises(ValidationError, match="claim seed list values"):
        StdClaimDefinition(
            claim_code="bad_claim",
            claim_name="坏卖点",
            claim_group="picture",
            aliases=[""],
        )


def test_base_claim_activation_run_request_result_and_api_defaults():
    request = BaseClaimActivationRunRequest(project_id="core3_mvp", batch_id="m00_202606130001")
    api_request = Core3BaseClaimActivationRunApiRequest(target_sku_codes=["TV00029115"])
    result = BaseClaimActivationRunResult(
        batch_id="m00_202606130001",
        status=Core3RunStatus.REVIEW_REQUIRED,
        source_status_count=35,
        claim_hit_count=12,
        activation_count=70,
        param_only_claim_count=58,
        missing_structured_claim_sku_count=30,
        review_required_count=6,
        review_required=True,
        warnings=["85E7Q 缺少结构化宣传卖点"],
    )

    assert request.model_dump() == {
        "project_id": "core3_mvp",
        "batch_id": "m00_202606130001",
        "category_code": "TV",
        "run_id": None,
        "module_run_id": None,
        "mode": "incremental",
        "module_version": CORE3_M04A_MODULE_VERSION,
        "seed_version": CORE3_M04A_SEED_VERSION,
        "rule_version": CORE3_M04A_RULE_VERSION,
        "target_sku_codes": [],
        "include_param_only_claims": True,
        "force_rebuild": False,
        "triggered_by": "system",
    }
    assert api_request.model_dump()["target_sku_codes"] == ["TV00029115"]
    assert "project_id" not in api_request.model_dump()
    assert "batch_id" not in api_request.model_dump()
    assert result.model_dump()["module_code"] == "M04a"
    assert result.review_required is True

    with pytest.raises(ValidationError):
        BaseClaimActivationRunRequest(project_id="", batch_id="m00_202606130001")
    with pytest.raises(ValidationError, match="target_sku_codes"):
        BaseClaimActivationRunRequest(project_id="core3_mvp", batch_id="m00_202606130001", target_sku_codes=[""])
    with pytest.raises(ValidationError):
        BaseClaimActivationRunResult(batch_id="m00_202606130001", status="success", activation_count=-1)


def test_claim_hit_source_status_and_activation_read_contracts():
    hit = ClaimHitRead(
        **BASE_READ,
        claim_hit_id="m04ahit_refresh_rate",
        claim_code="claim_high_refresh_rate",
        claim_name="高刷新率",
        claim_group=ClaimGroup.GAMING,
        hit_source_type=ClaimHitSourceType.PARAM_SUPPORT,
        source_sentence_key="",
        matched_keywords=["刷新率"],
        extracted_entity_json={"numeric_entities": [{"raw": "144Hz", "value": 144, "unit": "Hz"}]},
        matched_param_codes=["native_refresh_rate_hz"],
        match_method=ClaimMatchMethod.PARAM_SUPPORT,
        param_evidence_ids=["m02ev_refresh_rate"],
        match_confidence=Decimal("0.8500"),
        hit_hash="sha256:m04a:hit",
    )
    source_status = ClaimSourceStatusRead(
        **BASE_READ,
        claim_source_status_id="m04asrc_85e7q",
        claim_source_status=ClaimSourceStatus.MISSING_STRUCTURED_CLAIM,
        structured_claim_count=0,
        claim_sentence_count=0,
        promo_evidence_count=0,
        param_only_claim_count=5,
        quality_evidence_ids=["m02ev_claim_missing"],
        missing_signals=["structured_claim_missing"],
        status_note="结构化宣传卖点数据缺失，不代表没有卖点。",
        review_required=True,
        review_status=ClaimReviewStatus.REVIEW_REQUIRED,
        status_hash="sha256:m04a:source",
    )
    activation = ClaimActivationBaseRead(
        **BASE_READ,
        claim_activation_base_id="m04abase_refresh_rate",
        claim_code="claim_high_refresh_rate",
        claim_name="高刷新率",
        claim_group=ClaimGroup.GAMING,
        claim_type=ClaimType.TECHNICAL,
        param_score=Decimal("0.8500"),
        promo_score=Decimal("0.0000"),
        base_activation_score=Decimal("0.6500"),
        activation_level=ClaimActivationLevel.MEDIUM,
        activation_basis=ClaimActivationBasis.PARAM_ONLY,
        param_support_json={"matched_params": [{"param_code": "native_refresh_rate_hz", "value": 144}]},
        promo_support_json={"promo_status": "missing_structured_claim"},
        missing_signals=["promo_evidence_missing"],
        confidence=Decimal("0.6500"),
        confidence_level=ClaimConfidenceLevel.MEDIUM,
        evidence_ids=["m02ev_refresh_rate"],
        param_evidence_ids=["m02ev_refresh_rate"],
        quality_evidence_ids=["m02ev_claim_missing"],
        claim_hit_ids=["m04ahit_refresh_rate"],
        review_required=True,
        review_status=ClaimReviewStatus.REVIEW_REQUIRED,
        review_reason="参数-only 卖点需复核。",
        activation_hash="sha256:m04a:activation",
    )

    assert hit.model_dump()["hit_source_type"] == "param_support"
    assert source_status.model_dump()["claim_source_status"] == "missing_structured_claim"
    assert activation.model_dump()["activation_basis"] == "param_only"

    for payload in [hit.model_dump(), source_status.model_dump(), activation.model_dump()]:
        assert_no_forbidden_business_fields(payload)

    with pytest.raises(ValidationError):
        ClaimHitRead(**{**hit.model_dump(), "match_confidence": Decimal("1.2")})
    with pytest.raises(ValidationError):
        ClaimSourceStatusRead(**{**source_status.model_dump(), "structured_claim_count": -1})
    with pytest.raises(ValidationError):
        ClaimActivationBaseRead(**{**activation.model_dump(), "confidence": Decimal("1.2")})
    with pytest.raises(ValidationError):
        ClaimActivationBaseRead(**{**activation.model_dump(), "comment_validation_score": Decimal("0.9")})


def test_sku_claim_response_queries_and_list_outputs_do_not_cross_m04a_boundary():
    source_status = ClaimSourceStatusRead(
        **BASE_READ,
        claim_source_status_id="m04asrc_85e7q",
        claim_source_status=ClaimSourceStatus.MISSING_STRUCTURED_CLAIM,
        status_hash="sha256:m04a:source",
    )
    activation = ClaimActivationBaseRead(
        **BASE_READ,
        claim_activation_base_id="m04abase_refresh_rate",
        claim_code="claim_high_refresh_rate",
        claim_name="高刷新率",
        claim_group=ClaimGroup.GAMING,
        claim_type=ClaimType.TECHNICAL,
        param_score=Decimal("0.8500"),
        base_activation_score=Decimal("0.6500"),
        activation_level=ClaimActivationLevel.MEDIUM,
        activation_basis=ClaimActivationBasis.PARAM_ONLY,
        confidence=Decimal("0.6500"),
        confidence_level=ClaimConfidenceLevel.MEDIUM,
        activation_hash="sha256:m04a:activation",
    )
    response = SkuClaimBaseResponse(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        model_name="85E7Q",
        source_status=source_status,
        base_claims=[activation],
        total_base_claim_count=1,
        param_only_count=1,
        review_required_count=1,
        summary_cn="85E7Q 当前仅有参数支撑的基础卖点，评论验证待 M04b。",
    )
    hit_query = ClaimHitQuery(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        claim_codes=["claim_high_refresh_rate"],
        hit_source_types=[ClaimHitSourceType.PARAM_SUPPORT],
        match_methods=[ClaimMatchMethod.PARAM_SUPPORT],
    )
    status_query = ClaimSourceStatusQuery(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        statuses=[ClaimSourceStatus.MISSING_STRUCTURED_CLAIM],
    )
    hit_list = Core3ClaimHitListOut(items=[], total=0, limit=100, offset=0)
    source_list = Core3ClaimSourceStatusListOut(items=[source_status], total=1, limit=100, offset=0)
    activation_list = Core3ClaimActivationBaseListOut(items=[activation], total=1, limit=100, offset=0)

    assert response.model_dump()["base_claims"][0]["claim_code"] == "claim_high_refresh_rate"
    assert hit_query.model_dump()["hit_source_types"] == ["param_support"]
    assert status_query.model_dump()["statuses"] == ["missing_structured_claim"]
    assert hit_list.total == 0
    assert source_list.items[0].claim_source_status == "missing_structured_claim"
    assert activation_list.items[0].activation_basis == "param_only"

    for payload in [
        response.model_dump(),
        hit_query.model_dump(),
        status_query.model_dump(),
        hit_list.model_dump(),
        source_list.model_dump(),
        activation_list.model_dump(),
    ]:
        assert_no_forbidden_business_fields(payload)

    with pytest.raises(ValidationError):
        ClaimHitQuery(project_id="core3_mvp", batch_id="m00_202606130001", claim_codes=[""])
    with pytest.raises(ValidationError):
        ClaimSourceStatusQuery(project_id="core3_mvp", batch_id="m00_202606130001", limit=0)
    with pytest.raises(ValidationError):
        Core3ClaimActivationBaseListOut(items=[], total=0, limit=0, offset=0)
    with pytest.raises(ValidationError):
        SkuClaimBaseResponse(
            project_id="core3_mvp",
            batch_id="m00_202606130001",
            sku_code="TV00029115",
            battlefield_code="battlefield_game_sport",
        )


def assert_no_forbidden_business_fields(payload):
    if isinstance(payload, dict):
        assert FORBIDDEN_M04A_BUSINESS_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_forbidden_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_business_fields(item)
