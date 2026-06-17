from decimal import Decimal

from app.services.core3_real_data.param_field_matcher import ParamFieldNormalizer
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler


def test_m03_field_profiler_outputs_all_attribute_fields_without_dropping_unknowns():
    records = [
        _param_raw(f"ev_{index:02d}", sku_code=f"SKU{index % 3}", field_name=f"属性{index:02d}", value="-")
        for index in range(84)
    ]

    profiles = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(records)

    assert len(profiles) == 84
    assert {profile.clean_param_name for profile in profiles} == {f"属性{index:02d}" for index in range(84)}
    assert all(profile.occurrence_count == 1 for profile in profiles)
    assert all(profile.unknown_count == 1 for profile in profiles)
    assert all(profile.top_values_json == [] for profile in profiles)


def test_m03_field_profiler_calculates_coverage_unknown_rate_top_values_and_patterns():
    records = [
        _param_raw("ev_size_1", sku_code="SKU1", field_name="尺寸", value="85英寸"),
        _param_raw("ev_size_2", sku_code="SKU2", field_name="尺寸", value="85英寸"),
        _param_raw("ev_size_3", sku_code="SKU2", field_name="尺寸", value="-", value_presence="dash"),
        _param_raw("ev_size_4", sku_code="SKU3", field_name="尺寸", value=None, value_presence="null"),
    ]

    [profile] = ParamFieldProfiler(
        project_id="core3_mvp",
        batch_id="batch_m03",
    ).build_profiles(records, total_sku_count=3)

    assert profile.clean_param_name == "尺寸"
    assert profile.normalized_param_name == "尺寸"
    assert profile.occurrence_count == 4
    assert profile.sku_coverage_count == 3
    assert profile.sku_coverage_rate == Decimal("1.000000")
    assert profile.present_count == 2
    assert profile.unknown_count == 2
    assert profile.unknown_rate == Decimal("0.500000")
    assert profile.top_values_json == [{"value": "85英寸", "count": 2}]
    assert profile.value_pattern_summary_json["number_like_count"] == 2
    assert profile.value_pattern_summary_json["unit_candidates"] == ["inch"]
    assert profile.evidence_ids == ["ev_size_1", "ev_size_2", "ev_size_3", "ev_size_4"]
    assert profile.to_record_payload()["match_type"] == "unmapped"


def test_m03_field_profiler_normalizes_miniled_variants_and_filters_non_param_evidence():
    records = [
        _param_raw("ev_1", sku_code="SKU1", field_name="MINILED", value="支持"),
        _param_raw("ev_2", sku_code="SKU2", field_name="Mini LED", value="支持"),
        _param_raw("ev_3", sku_code="SKU3", field_name="MiniLED", value="不支持"),
        _param_raw(
            "ev_comment",
            sku_code="SKU1",
            field_name="MINILED",
            value="评论里说 Mini LED 不错",
            evidence_type="comment_sentence",
        ),
    ]

    [profile] = ParamFieldProfiler(
        project_id="core3_mvp",
        batch_id="batch_m03",
    ).build_profiles(records, total_sku_count=3)

    assert ParamFieldNormalizer.normalize("Mini LED") == "miniled"
    assert profile.normalized_param_name == "miniled"
    assert profile.occurrence_count == 3
    assert profile.sku_coverage_count == 3
    assert profile.value_pattern_summary_json["boolean_like_count"] == 3
    assert "ev_comment" not in profile.evidence_ids


def _param_raw(
    evidence_id: str,
    *,
    sku_code: str,
    field_name: str,
    value: object,
    value_presence: str = "present",
    evidence_type: str = "param_raw",
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "sku_code": sku_code,
        "evidence_type": evidence_type,
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": field_name,
        "clean_value": value,
        "value_presence": value_presence,
    }
