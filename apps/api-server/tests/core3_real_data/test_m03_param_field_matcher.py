from decimal import Decimal

from app.services.core3_real_data.param_extraction_schemas import (
    ParamDataType,
    ParamGroup,
    ParamSourceType,
    StdParamDefinition,
    StdParamSeed,
)
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher, ParamFieldNormalizer
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader


def test_m03_alias_matcher_exact_alias_uses_real_seed_and_boosts_parser_confidence():
    [profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [
            _param_raw("ev_1", sku_code="SKU1", field_name="尺寸", value="85英寸"),
            _param_raw("ev_2", sku_code="SKU2", field_name="尺寸", value="75英寸"),
        ],
        total_sku_count=2,
    )
    matcher = ParamAliasMatcher(StdParamSeedLoader().load_seed())

    matched_profile = matcher.apply_match(profile)

    assert matched_profile.matched_param_code == "screen_size_inch"
    assert matched_profile.matched_param_name == "屏幕尺寸"
    assert matched_profile.match_type == "exact_alias"
    assert matched_profile.alias_confidence == Decimal("0.9800")
    assert matched_profile.candidate_status == "matched"
    assert matched_profile.review_required is False


def test_m03_alias_matcher_standard_name_has_own_match_step():
    seed = StdParamSeed(
        standard_params=[
            StdParamDefinition(
                param_code="demo_param",
                param_name="标准字段名",
                data_type=ParamDataType.STRING,
                param_group=ParamGroup.OTHER,
                aliases=["业务别名"],
                value_parsers=["string"],
                source_types=[ParamSourceType.RAW_PARAM],
            )
        ]
    )
    [profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [_param_raw("ev_1", sku_code="SKU1", field_name="标准字段名", value="A")],
        total_sku_count=1,
    )

    match = ParamAliasMatcher(seed).match_profile(profile)

    assert match.matched_param_code == "demo_param"
    assert match.match_type == "standard_name"
    assert match.alias_confidence == Decimal("0.9300")
    assert match.review_required is False


def test_m03_alias_matcher_contains_alias_for_core_param_requires_review():
    [profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [_param_raw("ev_1", sku_code="SKU1", field_name="屏幕尺寸参数", value="85英寸")],
        total_sku_count=1,
    )

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code == "screen_size_inch"
    assert match.match_type == "contains_alias"
    assert match.review_required is True
    assert match.review_status == "review_required"
    assert "core_param_requires_exact_or_standard_review" in match.review_reason["reason_codes"]


def test_m03_alias_matcher_keyword_and_value_pattern_match_after_alias_steps():
    seed = StdParamSeedLoader().load_seed()
    matcher = ParamAliasMatcher(seed)
    [keyword_profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [_param_raw("ev_keyword", sku_code="SKU1", field_name="流畅能力", value="144Hz 高刷")],
        total_sku_count=1,
    )
    [pattern_profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [_param_raw("ev_pattern", sku_code="SKU1", field_name="未命名参数", value="165Hz")],
        total_sku_count=1,
    )
    pattern_seed = StdParamSeed(
        standard_params=[
            StdParamDefinition(
                param_code="demo_hz_param",
                param_name="演示刷新字段",
                data_type=ParamDataType.NUMBER,
                param_group=ParamGroup.OTHER,
                aliases=["演示别名"],
                value_parsers=["hz"],
                source_types=[ParamSourceType.RAW_PARAM],
                required_for_core=True,
            )
        ]
    )

    keyword_match = matcher.match_profile(keyword_profile)
    pattern_match = ParamAliasMatcher(pattern_seed).match_profile(pattern_profile)

    assert keyword_match.matched_param_code == "native_refresh_rate_hz"
    assert keyword_match.match_type == "keyword"
    assert keyword_match.review_required is True
    assert pattern_match.matched_param_code == "demo_hz_param"
    assert pattern_match.match_type == "value_pattern"
    assert pattern_match.review_required is True


def test_m03_alias_matcher_unmapped_high_coverage_enters_alias_candidate():
    [profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [
            _param_raw("ev_1", sku_code="SKU1", field_name="包装清单", value="遥控器"),
            _param_raw("ev_2", sku_code="SKU2", field_name="包装清单", value="遥控器"),
        ],
        total_sku_count=4,
    )

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code is None
    assert match.match_type == "unmapped"
    assert match.candidate_status == "candidate"
    assert match.review_required is True
    assert "unmapped_high_coverage_or_core_tech_field" in match.review_reason["reason_codes"]


def test_m03_alias_matcher_multiple_candidates_reduce_confidence_and_require_review():
    seed = StdParamSeed(
        standard_params=[
            _std_param("demo_param_a", aliases=["共同字段"]),
            _std_param("demo_param_b", aliases=["共同字段"]),
        ]
    )
    [profile] = ParamFieldProfiler(project_id="core3_mvp", batch_id="batch_m03").build_profiles(
        [_param_raw("ev_1", sku_code="SKU1", field_name="共同字段", value="A")],
        total_sku_count=1,
    )

    match = ParamAliasMatcher(seed).match_profile(profile)

    assert match.matched_param_code == "demo_param_a"
    assert match.match_type == "exact_alias"
    assert match.alias_confidence == Decimal("0.8000")
    assert match.review_required is True
    assert match.review_reason["candidate_param_codes"] == ["demo_param_a", "demo_param_b"]


def test_m03_field_normalizer_preserves_matching_semantics_only():
    assert ParamFieldNormalizer.normalize(" Mini_LED（单位） ") == "miniled"
    assert ParamFieldNormalizer.normalize("Mini LED") == "miniled"
    assert ParamFieldNormalizer.normalize("MINILED") == "miniled"


def _std_param(param_code: str, *, aliases: list[str]) -> StdParamDefinition:
    return StdParamDefinition(
        param_code=param_code,
        param_name=f"{param_code}_name",
        data_type=ParamDataType.STRING,
        param_group=ParamGroup.OTHER,
        aliases=aliases,
        value_parsers=["string"],
        source_types=[ParamSourceType.RAW_PARAM],
    )


def _param_raw(
    evidence_id: str,
    *,
    sku_code: str,
    field_name: str,
    value: object,
    value_presence: str = "present",
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "sku_code": sku_code,
        "evidence_type": "param_raw",
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": field_name,
        "clean_value": value,
        "value_presence": value_presence,
    }
