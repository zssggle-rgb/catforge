from decimal import Decimal

from app.services.core3_real_data.param_conflicts import ParamConflictDetector
from app.services.core3_real_data.param_extraction_service import ParamValueExtractor
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_profile_builder import SkuParamProfileBuilder
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m03"


def test_m03_sku_param_profile_builder_outputs_complete_core_profile_and_hash():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_size", sku_code="SKU1", field_name="尺寸", value="85英寸"),
        _evidence("ev_resolution", sku_code="SKU1", field_name="分辨率", value="4K"),
        _evidence("ev_refresh", sku_code="SKU1", field_name="原生刷新率", value="144Hz"),
        _evidence("ev_brightness", sku_code="SKU1", field_name="峰值亮度", value="5200nits"),
        _evidence("ev_miniled", sku_code="SKU1", field_name="Mini LED", value="支持"),
        _evidence("ev_zones", sku_code="SKU1", field_name="控光分区", value="3500分区"),
        _evidence("ev_hdmi", sku_code="SKU1", field_name="HDMI2.1", value="4个HDMI2.1"),
        _evidence("ev_ram", sku_code="SKU1", field_name="运行内存", value="4+64GB"),
        _evidence("ev_storage", sku_code="SKU1", field_name="存储容量", value="4+64GB"),
    ]
    values, conflicts = _extract_values_and_conflicts(records, seed)

    [profile] = SkuParamProfileBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).build_profiles(
        values,
        conflicts,
    )

    assert profile.sku_param_profile_id.startswith("m03profile_")
    assert profile.sku_code == "SKU1"
    assert profile.model_name == "85E7Q"
    assert profile.known_param_count == 9
    assert profile.unknown_param_count == 0
    assert profile.conflict_count == 0
    assert profile.review_required_count == 0
    assert profile.param_completeness == Decimal("1.000000")
    assert profile.profile_hash.startswith("sha256:m03-sku-param-profile-v1:")
    assert profile.param_values_json["screen_size_inch"]["normalized_value"] == {"value": 85, "unit": "inch"}
    assert profile.core_picture_params_json["mini_led_flag"]["normalized_value"] is True
    assert profile.core_gaming_params_json["hdmi_2_1_ports"]["normalized_value"] == {
        "hdmi_version": "2.1",
        "port_count": 4,
    }
    assert profile.core_system_params_json["ram_gb"]["normalized_value"]["value"] == 4
    assert profile.core_system_params_json["storage_gb"]["normalized_value"]["value"] == 64
    assert profile.core_eye_care_params_json == {}
    assert profile.quality_summary_json["missing_core_param_codes"] == []
    assert set(profile.evidence_ids) == {record["evidence_id"] for record in records}
    assert profile.to_record_payload()["sku_code"] == "SKU1"


def test_m03_sku_param_profile_builder_preserves_conflict_and_review_summary():
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
    values, conflicts = _extract_values_and_conflicts(records, seed, profile_records=[records[0]])

    [profile] = SkuParamProfileBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).build_profiles(
        values,
        conflicts,
    )

    assert profile.conflict_count == 2
    assert profile.review_required_count >= 1
    assert profile.param_values_json["native_refresh_rate_hz"]["conflict_flag"] is True
    assert profile.param_values_json["native_refresh_rate_hz"]["candidates"]
    assert profile.quality_summary_json["conflict_type_counts"] == {
        "raw_param_vs_claim_conflict": 1,
        "scope_uncertain": 1,
    }
    assert "native_refresh_rate_hz" in profile.quality_summary_json["review_required_param_codes"]
    assert profile.core_picture_params_json["native_refresh_rate_hz"]["conflict_flag"] is True


def test_m03_sku_param_profile_builder_counts_unknown_boolean_and_missing_core_params():
    seed = StdParamSeedLoader().load_seed()
    records = [_evidence("ev_miniled", sku_code="SKU1", field_name="MINILED", value="-")]
    values, conflicts = _extract_values_and_conflicts(records, seed)

    [profile] = SkuParamProfileBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).build_profiles(
        values,
        conflicts,
    )

    assert profile.known_param_count == 0
    assert profile.unknown_param_count == 1
    assert profile.conflict_count == 1
    assert profile.param_completeness == Decimal("0.000000")
    assert profile.param_values_json["mini_led_flag"]["value_presence"] == "unknown"
    assert "boolean_unknown" in profile.quality_summary_json["quality_flag_counts"]
    assert "mini_led_flag" not in profile.quality_summary_json["missing_core_param_codes"]
    assert "screen_size_inch" in profile.quality_summary_json["missing_core_param_codes"]


def test_m03_sku_param_profile_builder_groups_multiple_skus_independently():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_sku1_size", sku_code="SKU1", field_name="尺寸", value="85英寸"),
        _evidence("ev_sku2_size", sku_code="SKU2", field_name="尺寸", value="75英寸"),
        _evidence("ev_sku2_ram", sku_code="SKU2", field_name="运行内存", value="4+64GB"),
    ]
    values, conflicts = _extract_values_and_conflicts(records, seed)

    profiles = SkuParamProfileBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).build_profiles(
        values,
        conflicts,
    )

    assert [profile.sku_code for profile in profiles] == ["SKU1", "SKU2"]
    profile_by_sku = {profile.sku_code: profile for profile in profiles}
    assert profile_by_sku["SKU1"].known_param_count == 1
    assert profile_by_sku["SKU2"].known_param_count == 2
    assert profile_by_sku["SKU1"].param_values_json["screen_size_inch"]["normalized_value"]["value"] == 85
    assert profile_by_sku["SKU2"].param_values_json["screen_size_inch"]["normalized_value"]["value"] == 75


def test_m03_sku_param_profile_builder_prefers_exact_size_over_zero_and_range():
    seed = StdParamSeedLoader().load_seed()
    records = [
        _evidence("ev_zero_screen_size", sku_code="SKU1", field_name="屏幕尺寸", value="0"),
        _evidence("ev_size_range", sku_code="SKU1", field_name="尺寸段", value="≥70"),
        _evidence("ev_exact_size", sku_code="SKU1", field_name="尺寸", value="85英寸"),
    ]
    values, conflicts = _extract_values_and_conflicts(records, seed)

    [profile] = SkuParamProfileBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).build_profiles(
        values,
        conflicts,
    )

    screen_size = profile.param_values_json["screen_size_inch"]
    assert screen_size["numeric_value"] == "85"
    assert screen_size["normalized_value"] == {"value": 85, "unit": "inch"}
    assert screen_size["param_value_id"] != next(
        value.param_value_id for value in values if value.raw_param_name == "屏幕尺寸"
    )


def _extract_values_and_conflicts(records, seed, profile_records=None):
    source_for_profiles = profile_records if profile_records is not None else records
    profiles = ParamFieldProfiler(project_id=PROJECT_ID, batch_id=BATCH_ID).build_profiles(source_for_profiles)
    matched_profiles = ParamAliasMatcher(seed).apply_matches(profiles)
    values = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed).extract_values(
        records,
        matched_profiles,
    )
    return ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).apply_conflicts(values)


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
