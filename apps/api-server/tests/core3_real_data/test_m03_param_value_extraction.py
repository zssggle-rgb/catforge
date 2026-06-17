from decimal import Decimal

from app.services.core3_real_data.param_conflicts import ParamConflictDetector
from app.services.core3_real_data.param_extraction_service import ParamValueExtractor
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m03"


def test_m03_param_value_extractor_extracts_raw_exact_alias_value_with_evidence_and_hash():
    seed = StdParamSeedLoader().load_seed()
    records = [_evidence("ev_size", sku_code="SKU1", field_name="尺寸", value="85英寸")]
    profiles = _matched_profiles(records, seed)

    [value] = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        profiles,
    )

    assert value.param_value_id.startswith("m03val_")
    assert value.param_code == "screen_size_inch"
    assert value.param_name == "屏幕尺寸"
    assert value.normalized_value == {"value": 85, "unit": "inch"}
    assert value.numeric_value == Decimal("85")
    assert value.value_presence == "present"
    assert value.source_type == "raw_param"
    assert value.source_priority_rank == 1
    assert value.match_type == "exact_alias"
    assert value.parser_type == "inch"
    assert value.parser_status == "parsed"
    assert value.confidence == Decimal("0.9500")
    assert value.confidence_level == "high"
    assert value.evidence_ids == ["ev_size"]
    assert value.primary_evidence_id == "ev_size"
    assert value.review_required is False
    assert value.param_value_hash.startswith("sha256:m03-param-value-v1:")
    assert value.to_record_payload()["param_code"] == "screen_size_inch"


def test_m03_param_value_extractor_preserves_boolean_unknown_and_conflict_detector_flags_it():
    seed = StdParamSeedLoader().load_seed()
    records = [_evidence("ev_miniled", sku_code="SKU1", field_name="MINILED", value="-")]
    profiles = _matched_profiles(records, seed)
    [value] = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        profiles,
    )

    assert value.param_code == "mini_led_flag"
    assert value.data_type == "boolean"
    assert value.parser_status == "unknown"
    assert value.value_presence == "unknown"
    assert value.normalized_value is None
    assert value.confidence == Decimal("0.3000")
    assert value.review_required is True

    updated_values, conflicts = ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).apply_conflicts(
        [value]
    )

    assert [conflict.conflict_type for conflict in conflicts] == ["boolean_unknown"]
    assert updated_values[0].conflict_flag is True
    assert updated_values[0].conflict_id == conflicts[0].conflict_id
    assert "boolean_unknown" in updated_values[0].quality_flags


def test_m03_param_value_extractor_marks_unit_and_scope_uncertain_for_review():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_brightness", sku_code="SKU1", field_name="亮度", value="5200"),
        _evidence("ev_refresh", sku_code="SKU1", field_name="屏幕刷新率", value="300HZ"),
    ]
    profiles = _matched_profiles(records, seed)
    values = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        profiles,
    )
    by_param = {value.param_code: value for value in values}

    brightness = by_param["peak_brightness_nits"]
    refresh = by_param["native_refresh_rate_hz"]

    assert brightness.parser_status == "unit_uncertain"
    assert brightness.confidence == Decimal("0.7000")
    assert "unit_inferred" in brightness.quality_flags
    assert brightness.review_required is True
    assert refresh.parser_status == "scope_uncertain"
    assert refresh.normalized_value == {"value": 300, "unit": "Hz", "scope": "system"}
    assert refresh.confidence == Decimal("0.7200")
    assert "scope_uncertain" in refresh.quality_flags

    _, conflicts = ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).apply_conflicts(values)
    assert {conflict.conflict_type for conflict in conflicts} >= {"unit_uncertain", "scope_uncertain"}


def test_m03_param_conflict_detector_detects_raw_vs_claim_conflict_and_prefers_raw_param():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_refresh_raw", sku_code="SKU1", field_name="刷新率", value="144Hz"),
        _evidence(
            "ev_refresh_claim",
            sku_code="SKU1",
            field_name="刷新率",
            value="300Hz",
            evidence_type="promo_sentence",
            base_confidence="0.80",
        ),
    ]
    profiles = _matched_profiles([records[0]], seed)
    values = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        profiles,
    )

    updated_values, conflicts = ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).apply_conflicts(
        values
    )
    conflict_by_type = {conflict.conflict_type: conflict for conflict in conflicts}

    assert "raw_param_vs_claim_conflict" in conflict_by_type
    raw_vs_claim = conflict_by_type["raw_param_vs_claim_conflict"]
    assert raw_vs_claim.preferred_value_json == {"value": 144, "unit": "Hz", "scope": "native"}
    assert raw_vs_claim.preferred_source_type == "raw_param"
    assert raw_vs_claim.confidence == Decimal("0.6000")
    assert set(raw_vs_claim.evidence_ids) == {"ev_refresh_raw", "ev_refresh_claim"}
    assert all(value.conflict_flag for value in updated_values)


def test_m03_param_conflict_detector_detects_same_source_multi_value():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_brightness_1", sku_code="SKU1", field_name="峰值亮度", value="5000nits"),
        _evidence("ev_brightness_2", sku_code="SKU1", field_name="峰值亮度", value="5200nits"),
    ]
    profiles = _matched_profiles(records, seed)
    values = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        profiles,
    )

    conflicts = ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).detect_conflicts(values)

    assert "same_param_multi_value" in {conflict.conflict_type for conflict in conflicts}
    conflict = next(item for item in conflicts if item.conflict_type == "same_param_multi_value")
    assert conflict.param_code == "peak_brightness_nits"
    assert len(conflict.candidate_values_json) == 2


def test_m03_param_conflict_detector_detects_hdmi_version_count_mixed_without_synthesis():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_hdmi_version", sku_code="SKU1", field_name="HDMI2.1", value="HDMI2.1"),
        _evidence("ev_hdmi_count", sku_code="SKU1", field_name="HDMI接口", value="4"),
    ]
    profiles = _matched_profiles(records, seed)
    values = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        profiles,
    )
    by_evidence = {value.primary_evidence_id: value for value in values}

    assert by_evidence["ev_hdmi_version"].normalized_value == {"hdmi_version": "2.1", "port_count": None}
    assert by_evidence["ev_hdmi_count"].normalized_value == {"hdmi_version": None, "port_count": 4}

    conflicts = ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).detect_conflicts(values)

    assert "hdmi_version_count_mixed" in {conflict.conflict_type for conflict in conflicts}
    hdmi_conflict = next(item for item in conflicts if item.conflict_type == "hdmi_version_count_mixed")
    assert hdmi_conflict.param_code == "hdmi_2_1_ports"
    assert "不能合成为 HDMI2.1 接口数" in hdmi_conflict.review_reason["message_cn"]


def _matched_profiles(records: list[dict[str, object]], seed):
    profiles = ParamFieldProfiler(project_id=PROJECT_ID, batch_id=BATCH_ID).build_profiles(records)
    matcher = ParamAliasMatcher(seed)
    return matcher.apply_matches(profiles)


def _evidence(
    evidence_id: str,
    *,
    sku_code: str,
    field_name: str,
    value: object,
    evidence_type: str = "param_raw",
    base_confidence: str = "1.00",
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "sku_code": sku_code,
        "model_name": "85E7Q",
        "evidence_type": evidence_type,
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": field_name,
        "clean_value": value,
        "raw_value": value,
        "value_presence": "present",
        "base_confidence": Decimal(base_confidence),
    }
