from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.core3_real_data import (
    ExtractParamValueRead,
    ParamAliasCandidateRead,
    ParamCandidateStatus,
    ParamConfidenceLevel,
    ParamConflictType,
    ParamDataType,
    ParamExtractionRunRequest,
    ParamExtractionRunResult,
    ParamFieldProfileRead,
    ParamGroup,
    ParamMatchType,
    ParamParserStatus,
    ParamReviewStatus,
    ParamSourceType,
    ParamValueConflictRead,
    SkuParamProfileRead,
    SkuParamQuery,
    StdParamDefinition,
    StdParamSeed,
)
from app.services.core3_real_data.constants import (
    CORE3_M03_MODULE_VERSION,
    CORE3_M03_PARSER_VERSION,
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    Core3RunStatus,
)


CREATED_AT = "2026-06-13T00:00:00Z"
UPDATED_AT = "2026-06-13T00:00:01Z"
BASE_READ = {
    "project_id": "core3_mvp",
    "category_code": "TV",
    "batch_id": "m00_202606130001",
    "run_id": "run-m03",
    "module_run_id": "module-run-m03",
    "created_at": CREATED_AT,
    "updated_at": UPDATED_AT,
}
FORBIDDEN_M03_BUSINESS_FIELDS = {
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "business_conclusion",
    "report_payload",
    "report_content",
    "score",
    "rank",
}


def test_m03_param_enums_match_sop_contract():
    assert [item.value for item in ParamSourceType] == ["raw_param", "derived_from_claim", "model_name"]
    assert [item.value for item in ParamMatchType] == [
        "exact_alias",
        "standard_name",
        "contains_alias",
        "keyword",
        "value_pattern",
        "unmapped",
    ]
    assert [item.value for item in ParamParserStatus] == [
        "parsed",
        "unknown",
        "failed",
        "scope_uncertain",
        "unit_uncertain",
        "conflict",
    ]
    assert [item.value for item in ParamConflictType] == [
        "same_param_multi_value",
        "raw_param_vs_claim_conflict",
        "unit_uncertain",
        "scope_uncertain",
        "boolean_unknown",
        "hdmi_version_count_mixed",
    ]
    assert [item.value for item in ParamConfidenceLevel] == ["high", "medium", "low", "unknown"]
    assert {item.value for item in ParamDataType} >= {"number", "string", "boolean", "enum", "list"}
    assert {item.value for item in ParamGroup} >= {"picture", "gaming", "system", "eye_care"}
    assert [item.value for item in ParamReviewStatus] == [
        "auto_pass",
        "review_required",
        "approved",
        "rejected",
        "waived",
    ]
    assert {item.value for item in ParamCandidateStatus} >= {"candidate", "review_required", "approved", "rejected"}


def test_std_param_seed_validates_required_structure_and_unique_codes():
    definition = StdParamDefinition(
        param_code="native_refresh_rate_hz",
        param_name="原生刷新率",
        data_type=ParamDataType.NUMBER,
        param_group=ParamGroup.GAMING,
        aliases=["原生刷新率", "屏幕刷新率"],
        value_parsers=["hz"],
        unit="Hz",
        source_types=[ParamSourceType.RAW_PARAM],
        required_for_core=True,
    )
    seed = StdParamSeed(standard_params=[definition])

    assert seed.seed_version == CORE3_M03_SEED_VERSION
    assert seed.model_dump()["standard_params"][0]["param_code"] == "native_refresh_rate_hz"

    with pytest.raises(ValidationError, match="standard_params"):
        StdParamSeed(standard_params=[])
    with pytest.raises(ValidationError, match="param_code must be unique"):
        StdParamSeed(standard_params=[definition, definition])
    with pytest.raises(ValidationError, match="list values"):
        StdParamDefinition(
            param_code="bad_alias",
            param_name="坏别名",
            data_type="string",
            param_group="other",
            aliases=[""],
            value_parsers=["string"],
        )


def test_param_extraction_run_request_and_result_defaults():
    request = ParamExtractionRunRequest(project_id="core3_mvp", batch_id="m00_202606130001")
    result = ParamExtractionRunResult(
        batch_id="m00_202606130001",
        status=Core3RunStatus.WARNING,
        field_profile_count=84,
        param_value_count=1200,
        sku_profile_count=35,
        alias_candidate_count=12,
        conflict_count=8,
        review_required_count=5,
        review_required=True,
        warnings=["m03_review_required"],
    )

    assert request.model_dump() == {
        "project_id": "core3_mvp",
        "batch_id": "m00_202606130001",
        "category_code": "TV",
        "run_id": None,
        "module_run_id": None,
        "mode": "incremental",
        "module_version": CORE3_M03_MODULE_VERSION,
        "seed_version": CORE3_M03_SEED_VERSION,
        "parser_version": CORE3_M03_PARSER_VERSION,
        "rule_version": CORE3_M03_RULE_VERSION,
        "target_sku_codes": [],
        "force_rebuild": False,
        "triggered_by": "system",
    }
    assert result.model_dump()["module_code"] == "M03"
    assert result.review_required is True

    with pytest.raises(ValidationError):
        ParamExtractionRunRequest(project_id="", batch_id="m00_202606130001")
    with pytest.raises(ValidationError, match="target_sku_codes"):
        ParamExtractionRunRequest(project_id="core3_mvp", batch_id="m00_202606130001", target_sku_codes=[""])
    with pytest.raises(ValidationError):
        ParamExtractionRunResult(batch_id="m00_202606130001", status="success", param_value_count=-1)


def test_param_field_profile_and_value_read_contracts():
    field_profile = ParamFieldProfileRead(
        **BASE_READ,
        field_profile_id="m03fp_refresh_rate",
        raw_param_name="刷新率",
        clean_param_name="刷新率",
        normalized_param_name="刷新率",
        occurrence_count=12,
        sku_coverage_count=10,
        sku_coverage_rate=Decimal("0.800000"),
        unknown_count=1,
        unknown_rate=Decimal("0.083333"),
        present_count=11,
        top_values_json=[{"value": "144Hz", "count": 8}],
        value_pattern_summary_json={"number_like": 12, "unit_candidates": ["Hz"]},
        matched_param_code="native_refresh_rate_hz",
        matched_param_name="原生刷新率",
        param_group=ParamGroup.GAMING,
        match_type=ParamMatchType.EXACT_ALIAS,
        alias_confidence=Decimal("0.9500"),
        candidate_status=ParamCandidateStatus.MATCHED,
        review_required=False,
        review_status=ParamReviewStatus.AUTO_PASS,
        evidence_ids=["m02ev_param_001"],
        field_profile_hash="sha256:m03:field",
    )
    value = ExtractParamValueRead(
        **BASE_READ,
        param_value_id="m03pv_refresh_rate",
        sku_code="TV00029115",
        model_name="85E7Q",
        param_code="native_refresh_rate_hz",
        param_name="原生刷新率",
        param_group=ParamGroup.GAMING,
        data_type=ParamDataType.NUMBER,
        normalized_value={"value": 144, "unit": "Hz"},
        numeric_value=Decimal("144.000000"),
        value_text="144Hz",
        unit="Hz",
        value_presence="present",
        source_type=ParamSourceType.RAW_PARAM,
        source_priority_rank=1,
        raw_param_name="刷新率",
        raw_param_value="144Hz",
        match_type=ParamMatchType.EXACT_ALIAS,
        parser_type="hz",
        parser_status=ParamParserStatus.PARSED,
        confidence=Decimal("0.9500"),
        confidence_level=ParamConfidenceLevel.HIGH,
        evidence_ids=["m02ev_param_001"],
        primary_evidence_id="m02ev_param_001",
        quality_flags=[],
        param_value_hash="sha256:m03:param_value",
    )

    assert field_profile.model_dump()["param_group"] == "gaming"
    assert value.model_dump()["normalized_value"] == {"value": 144, "unit": "Hz"}

    with pytest.raises(ValidationError):
        ParamFieldProfileRead(**{**field_profile.model_dump(), "sku_coverage_rate": Decimal("1.2")})
    with pytest.raises(ValidationError):
        ExtractParamValueRead(**{**value.model_dump(), "confidence": Decimal("1.2")})
    with pytest.raises(ValidationError):
        ExtractParamValueRead(**{**value.model_dump(), "task_code": "TASK_GAMING"})


def test_alias_conflict_sku_profile_and_query_contracts_do_not_cross_m03_boundary():
    alias = ParamAliasCandidateRead(
        **BASE_READ,
        alias_candidate_id="m03alias_unknown",
        clean_param_name="屏幕流畅度",
        sku_coverage_rate=Decimal("0.700000"),
        unknown_rate=Decimal("0.100000"),
        top_values_json=[{"value": "流畅", "count": 4}],
        value_pattern_summary_json={"string_like": 4},
        suggested_param_code="native_refresh_rate_hz",
        suggestion_reason="字段语义接近刷新率，需复核",
        confidence=Decimal("0.5500"),
    )
    conflict = ParamValueConflictRead(
        **BASE_READ,
        conflict_id="m03conflict_hdmi",
        sku_code="TV00029115",
        param_code="hdmi_2_1_ports",
        conflict_type=ParamConflictType.HDMI_VERSION_COUNT_MIXED,
        candidate_values_json=[{"value": "HDMI2.1"}, {"value": 4}],
        preferred_value_json=None,
        confidence=Decimal("0.3000"),
        evidence_ids=["m02ev_hdmi_version", "m02ev_hdmi_count"],
        quality_flags=["hdmi_version_count_mixed"],
    )
    profile = SkuParamProfileRead(
        **BASE_READ,
        sku_param_profile_id="m03sku_85e7q",
        sku_code="TV00029115",
        model_name="85E7Q",
        param_values_json={"native_refresh_rate_hz": {"value": 144, "unit": "Hz"}},
        core_picture_params_json={"mini_led_flag": {"value_presence": "unknown"}},
        core_gaming_params_json={"native_refresh_rate_hz": {"value": 144, "unit": "Hz"}},
        core_system_params_json={},
        core_eye_care_params_json={},
        param_completeness=Decimal("0.720000"),
        known_param_count=18,
        unknown_param_count=4,
        conflict_count=1,
        review_required_count=2,
        evidence_ids=["m02ev_param_001"],
        quality_summary_json={"review_required": 2},
        profile_hash="sha256:m03:sku_profile",
    )
    query = SkuParamQuery(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        param_groups=[ParamGroup.GAMING],
        source_types=[ParamSourceType.RAW_PARAM],
        review_required=False,
    )

    for payload in [alias.model_dump(), conflict.model_dump(), profile.model_dump(), query.model_dump()]:
        assert_no_forbidden_business_fields(payload)
    assert conflict.conflict_type == "hdmi_version_count_mixed"
    assert profile.param_values_json["native_refresh_rate_hz"]["value"] == 144
    assert query.model_dump()["param_groups"] == ["gaming"]

    with pytest.raises(ValidationError):
        SkuParamQuery(project_id="core3_mvp", param_groups=["battlefield"])
    with pytest.raises(ValidationError):
        SkuParamProfileRead(**{**profile.model_dump(), "param_completeness": Decimal("1.2")})


def assert_no_forbidden_business_fields(payload):
    if isinstance(payload, dict):
        assert FORBIDDEN_M03_BUSINESS_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_forbidden_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_business_fields(item)
