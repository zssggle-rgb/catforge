from app.services.core3_real_data.param_extraction_schemas import ParamCandidateStatus
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m03_guard"


def test_m03_mapping_guard_blocks_wifi_from_audio_power():
    [profile] = _profiles([_param_raw("ev_wifi", "SKU1", "内置WIFI", "10W")])

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code is None
    assert match.candidate_status == ParamCandidateStatus.CANDIDATE
    assert match.review_required is True
    assert "param_mapping_guard_blocked" in match.review_reason["reason_codes"]
    assert "speaker_power_w" in match.review_reason["blocked_param_codes"]
    assert "wifi_field_cannot_support_audio_param" in match.review_reason["reason_codes"]


def test_m03_mapping_guard_routes_hdmi_count_to_port_count_not_color_depth():
    [profile] = _profiles([_param_raw("ev_hdmi_count", "SKU1", "HDMI数量", "4")])

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code == "hdmi_port_count"
    assert match.match_type == "exact_alias"
    assert match.review_required is False


def test_m03_mapping_guard_routes_hdr_to_hdr_format_not_brightness():
    [profile] = _profiles([_param_raw("ev_hdr", "SKU1", "HDR", "HDR10/HLG")])

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code == "hdr_format_list"
    assert match.match_type == "exact_alias"
    assert match.review_required is False


def test_m03_mapping_guard_routes_backlight_source_to_backlight_type():
    [profile] = _profiles([_param_raw("ev_backlight", "SKU1", "背光源细分", "Mini LED")])

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code == "backlight_type"
    assert match.match_type == "exact_alias"


def test_m03_mapping_guard_blocks_panel_type_for_refresh_field():
    [profile] = _profiles([_param_raw("ev_panel_refresh", "SKU1", "面板刷新率", "120Hz")])

    match = ParamAliasMatcher(StdParamSeedLoader().load_seed()).match_profile(profile)

    assert match.matched_param_code in {"native_refresh_rate_hz", "system_refresh_rate_hz", "refresh_rate_hz"}
    assert match.matched_param_code != "panel_type"
    assert match.review_required is True
    assert "param_mapping_guard_removed_conflicting_candidate" in match.review_reason["reason_codes"]
    assert "panel_type" in match.review_reason["guard_blocked_param_codes"]


def test_m03_mapping_guard_routes_design_and_energy_proxy_fields():
    profiles = _profiles(
        [
            _param_raw("ev_energy", "SKU1", "能效等级", "一级能效"),
            _param_raw("ev_full_screen", "SKU1", "全面屏", "是"),
            _param_raw("ev_slim", "SKU1", "SLIM", "是"),
            _param_raw("ev_thickness", "SKU1", "机身厚度", "38"),
        ]
    )
    matcher = ParamAliasMatcher(StdParamSeedLoader().load_seed())
    matches = {profile.clean_param_name: matcher.match_profile(profile) for profile in profiles}

    assert matches["能效等级"].matched_param_code == "energy_efficiency_level"
    assert matches["全面屏"].matched_param_code == "full_screen_flag"
    assert matches["SLIM"].matched_param_code == "slim_design_flag"
    assert matches["机身厚度"].matched_param_code == "body_thickness_mm"


def test_m03_mapping_guard_blocks_generic_boolean_fields_from_product_params():
    profiles = _profiles(
        [
            _param_raw("ev_ai", "SKU1", "人工智能", "支持"),
            _param_raw("ev_smart_home", "SKU1", "全屋智控", "支持"),
        ]
    )
    matcher = ParamAliasMatcher(StdParamSeedLoader().load_seed())
    matches = {profile.clean_param_name: matcher.match_profile(profile) for profile in profiles}

    for match in matches.values():
        assert match.matched_param_code is None
        assert match.candidate_status in {ParamCandidateStatus.CANDIDATE, ParamCandidateStatus.IGNORED}


def test_m03_mapping_guard_blocks_width_and_led_count_from_neighbor_params():
    profiles = _profiles(
        [
            _param_raw("ev_width", "SKU1", "整机宽度", "1890mm"),
            _param_raw("ev_led_count", "SKU1", "灯珠数量", "400颗"),
        ]
    )
    matcher = ParamAliasMatcher(StdParamSeedLoader().load_seed())
    matches = {profile.clean_param_name: matcher.match_profile(profile) for profile in profiles}

    assert matches["整机宽度"].matched_param_code != "body_thickness_mm"
    assert matches["灯珠数量"].matched_param_code != "mini_led_flag"


def _profiles(records: list[dict[str, object]]):
    return ParamFieldProfiler(project_id=PROJECT_ID, batch_id=BATCH_ID).build_profiles(
        records,
        total_sku_count=1,
    )


def _param_raw(evidence_id: str, sku_code: str, field_name: str, value: object) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "sku_code": sku_code,
        "evidence_type": "param_raw",
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": field_name,
        "clean_value": value,
        "raw_value": value,
        "value_presence": "present",
    }
