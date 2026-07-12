"""Category semantics shared by sellpoint-value V4/V5.

The module contains deterministic, reviewed category mappings only.  It does
not query data or infer a value that is absent from the published profiles.
"""

from __future__ import annotations

from app.services.core3_real_data.analyst.claim_value_pm_service import (
    TvValueUnitDefinition,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    ac_purchase_reason_anchor_taxonomy_v0_1,
    tv_purchase_reason_anchor_taxonomy_v0_1,
)


AC_BATTLEFIELD_CN = {
    "BF_WALL_SMALL_ENTRY_VALUE": "1匹及以下挂机刚需性价比",
    "BF_WALL_SMALL_COMFORT_UPGRADE": "1匹及以下挂机舒适升级",
    "BF_WALL_1_5_MAINSTREAM_VALUE": "1.5匹挂机主流性价比",
    "BF_WALL_1_5_SLEEP_COMFORT_UPGRADE": "1.5匹挂机睡眠舒适升级",
    "BF_WALL_2_LARGE_ROOM_BALANCE": "2匹挂机大房间均衡",
    "BF_FLOOR_2_ENTRY_LIVING_VALUE": "2匹柜机客厅入门",
    "BF_FLOOR_3_LIVING_VALUE_UPGRADE": "3匹柜机客厅性价比升级",
    "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH": "3匹及以上柜机高端舒适健康",
    "BF_MID_HIGH_SMART_CONTROL_UPGRADE": "中高价智能控制升级",
    "BF_MID_HIGH_HEALTH_CLEAN_AIR_UPGRADE": "中高价健康洁净升级",
    "BF_HUMID_CLIMATE_DEHUMIDIFY": "潮湿除湿场景",
}

AC_CANONICAL_SIZE_TIERS = (
    "wall_hp_1_or_below",
    "wall_hp_1_5",
    "wall_hp_2",
    "wall_hp_3",
    "floor_hp_2",
    "floor_hp_3",
    "floor_hp_3_plus",
)
AC_SIZE_TIER_RANK = {
    code: float(index + 1) for index, code in enumerate(AC_CANONICAL_SIZE_TIERS)
}

AC_VALUE_UNITS: tuple[TvValueUnitDefinition, ...] = (
    TvValueUnitDefinition(
        code="ac_capacity_space_fit",
        name_cn="冷暖能力与空间匹配",
        param_codes=(
            "installation_type",
            "horsepower_hp",
            "cooling_capacity_w",
            "heating_capacity_w",
        ),
        claim_codes=(
            "ac_claim_fast_cooling_heating",
            "ac_claim_installation_space_design",
        ),
        subdimensions=(
            "cooling_effect",
            "heating_effect",
            "fast_cooling_heating",
            "space_fit_area",
        ),
        direct_patterns=(r"匹|制冷量|制热量|挂机|柜机",),
        outcome_patterns=(
            r"制冷.{0,4}(?:快|好)|制热.{0,4}(?:快|好)",
            r"房间.{0,6}(?:够用|合适|带得动)",
        ),
        generic_patterns=(r"冷暖.{0,3}(?:好|不错)|效果.{0,3}(?:好|不错)",),
    ),
    TvValueUnitDefinition(
        code="ac_energy_cost_control",
        name_cn="长期用电成本可控",
        param_codes=(
            "energy_grade_normalized",
            "energy_efficiency_ratio",
            "inverter_flag",
        ),
        claim_codes=("ac_claim_energy_efficiency_apf", "ac_claim_ai_energy_saving"),
        subdimensions=(
            "energy_grade_apf",
            "energy_saving_usage",
            "electricity_cost",
            "energy_saving_negative",
        ),
        direct_patterns=(r"一级能效|APF|能效比|变频",),
        outcome_patterns=(r"省电|电费.{0,4}(?:低|省|不高)|耗电.{0,4}(?:低|少)",),
        generic_patterns=(r"节能|能耗.{0,3}(?:低|不错)",),
    ),
    TvValueUnitDefinition(
        code="ac_sleep_quiet_comfort",
        name_cn="睡眠静音舒适",
        param_codes=("indoor_noise_db", "comfort_airflow_flag"),
        claim_codes=("ac_claim_quiet_sleep", "ac_claim_soft_wind_no_direct"),
        subdimensions=(
            "quiet_positive",
            "sleep_scene",
            "noise_risk",
            "soft_wind_no_direct",
        ),
        direct_patterns=(r"静音|低噪|睡眠模式|分贝",),
        outcome_patterns=(
            r"睡觉.{0,5}(?:安静|不吵)|夜里.{0,5}(?:不吵|安静)|声音.{0,4}(?:小|轻)",
        ),
        generic_patterns=(r"安静|噪音.{0,3}(?:小|低)",),
    ),
    TvValueUnitDefinition(
        code="ac_comfortable_airflow",
        name_cn="柔风不直吹",
        param_codes=("comfort_airflow_flag", "airflow_volume_m3h"),
        claim_codes=("ac_claim_soft_wind_no_direct", "ac_claim_large_airflow_coverage"),
        subdimensions=(
            "soft_wind_no_direct",
            "airflow_even_swing",
            "airflow_volume_coverage",
            "airflow_negative",
        ),
        direct_patterns=(r"柔风|无风感|防直吹|上下左右扫风",),
        outcome_patterns=(r"不直吹|风.{0,4}(?:柔|舒服|均匀)|不会.{0,3}吹人",),
        generic_patterns=(r"风感.{0,3}(?:好|舒服)|送风.{0,3}(?:好|远)",),
    ),
    TvValueUnitDefinition(
        code="ac_clean_air_health",
        name_cn="空气洁净与维护省心",
        param_codes=("self_cleaning_flag", "purification_flag", "fresh_air_flag"),
        claim_codes=(
            "ac_claim_self_cleaning",
            "ac_claim_purification_antibacterial",
            "ac_claim_fresh_air",
        ),
        subdimensions=(
            "self_cleaning",
            "purification_antibacterial",
            "fresh_air_ventilation",
            "odor_mold_risk",
        ),
        direct_patterns=(r"自清洁|除菌|净化|新风",),
        outcome_patterns=(
            r"空气.{0,4}(?:清新|干净)|没有.{0,3}(?:异味|霉味)|清洗.{0,4}(?:方便|省事)",
        ),
        generic_patterns=(r"健康|干净|省心",),
    ),
    TvValueUnitDefinition(
        code="ac_large_space_coverage",
        name_cn="大空间快速覆盖",
        param_codes=(
            "installation_type",
            "horsepower_hp",
            "cooling_capacity_w",
            "airflow_volume_m3h",
        ),
        claim_codes=(
            "ac_claim_large_airflow_coverage",
            "ac_claim_fast_cooling_heating",
        ),
        subdimensions=(
            "use_living_room_large",
            "airflow_volume_coverage",
            "fast_cooling_heating",
            "cooling_effect",
        ),
        direct_patterns=(r"大风量|大空间|客厅|\d(?:\.\d)?匹",),
        outcome_patterns=(
            r"客厅.{0,6}(?:够用|凉得快)|大房间.{0,6}(?:覆盖|够用)|全屋.{0,4}(?:凉|暖)",
        ),
        generic_patterns=(r"风量.{0,3}(?:大|足)|制冷.{0,3}快",),
    ),
    TvValueUnitDefinition(
        code="ac_installation_fit",
        name_cn="安装与空间适配",
        param_codes=("installation_type", "horsepower_hp", "indoor_unit_dimensions_mm"),
        claim_codes=("ac_claim_installation_space_design",),
        subdimensions=(
            "installation_form",
            "space_fit_area",
            "installation_constraint",
            "appearance_design",
        ),
        direct_patterns=(r"挂机|柜机|尺寸|安装|占地",),
        outcome_patterns=(r"装得下|不占地|位置.{0,4}(?:合适|刚好)|小房间.{0,4}合适",),
        generic_patterns=(r"安装.{0,3}(?:方便|合适)|外观.{0,3}(?:好看|协调)",),
    ),
    TvValueUnitDefinition(
        code="ac_smart_operation",
        name_cn="远程控制与操作省事",
        param_codes=("wifi_control_flag", "voice_control_flag", "smart_sensing_flag"),
        claim_codes=("ac_claim_smart_app_voice_iot",),
        subdimensions=(
            "smart_app_remote",
            "voice_iot",
            "remote_panel_easy_use",
            "smart_negative",
        ),
        direct_patterns=(r"APP|远程|WiFi|语音|智能感应",),
        outcome_patterns=(r"回家前.{0,5}打开|远程.{0,4}方便|操作.{0,4}(?:简单|省事)",),
        generic_patterns=(r"智能.{0,3}(?:方便|好用)|控制.{0,3}方便",),
    ),
    TvValueUnitDefinition(
        code="ac_seasonal_reliability",
        name_cn="极端天气与潮湿环境稳定",
        param_codes=("heating_capacity_w", "self_cleaning_flag", "purification_flag"),
        claim_codes=(
            "ac_claim_humidity_dehumidification",
            "ac_claim_fast_cooling_heating",
        ),
        subdimensions=(
            "wide_temperature_operation",
            "dehumidification",
            "humid_weather",
            "temperature_stability",
        ),
        direct_patterns=(r"低温制热|高温制冷|除湿|温湿双控",),
        outcome_patterns=(
            r"梅雨.{0,5}(?:干爽|不潮)|除湿.{0,4}(?:快|好)|冬天.{0,4}(?:暖|稳定)",
        ),
        generic_patterns=(r"除湿.{0,3}(?:好|不错)|温度.{0,3}稳定",),
    ),
)

AC_VALUE_THEME_UNIT_CODES: dict[str, tuple[str, ...]] = {
    "cooling_heating_capacity_assurance": ("ac_capacity_space_fit",),
    "energy_cost_efficiency": ("ac_energy_cost_control",),
    "sleep_quiet_comfort": ("ac_sleep_quiet_comfort",),
    "comfortable_airflow_health": ("ac_comfortable_airflow", "ac_clean_air_health"),
    "large_space_coverage": ("ac_large_space_coverage",),
    "installation_space_fit": ("ac_installation_fit",),
    "operation_maintenance_convenience": ("ac_smart_operation", "ac_clean_air_health"),
    "budget_configuration_efficiency": (
        "ac_capacity_space_fit",
        "ac_energy_cost_control",
    ),
    "seasonal_reliability": ("ac_seasonal_reliability",),
}

AC_VALUE_SCENARIOS: dict[str, tuple[str, str]] = {
    "cooling_heating_capacity_assurance": (
        "目标房间的日常制冷和制热",
        "匹数与空间匹配，冷得快、热得稳，降低买小风险",
    ),
    "energy_cost_efficiency": ("高频和长期使用", "能效与变频能力让长期电费更可控"),
    "sleep_quiet_comfort": (
        "卧室夜间和睡眠使用",
        "运行声音更轻、风感更舒适，不容易扰眠",
    ),
    "comfortable_airflow_health": (
        "老人儿童、长时间送风和空气健康场景",
        "减少直吹、闷、异味和清洁负担",
    ),
    "large_space_coverage": (
        "客厅、大卧室和大面积空间",
        "大风量与冷暖能力更快覆盖目标空间",
    ),
    "installation_space_fit": (
        "房型、安装位置和有限空间",
        "产品形态与尺寸更容易装得下、用得上",
    ),
    "operation_maintenance_convenience": (
        "远程控制、调温和日常清洁",
        "控制步骤和维护负担更少",
    ),
    "budget_configuration_efficiency": (
        "给定预算内选购",
        "核心冷暖、能效和舒适配置没有明显缺口",
    ),
    "seasonal_reliability": (
        "高温、低温和梅雨潮湿天气",
        "极端季节下的冷暖、除湿和温控更稳定",
    ),
}

AC_FAMILY_BATTLEFIELD_TOKENS: dict[str, tuple[str, ...]] = {
    "capacity_match": ("MAINSTREAM", "LARGE_ROOM", "LIVING"),
    "large_space": ("LARGE_ROOM", "LIVING"),
    "price_justification": ("PREMIUM", "UPGRADE"),
    "energy_cost": ("VALUE", "BALANCE"),
    "budget_configuration": ("VALUE", "MAINSTREAM"),
    "sleep_quiet": ("SLEEP", "COMFORT"),
    "airflow_health": ("COMFORT", "HEALTH"),
    "seasonal_reliability": ("HUMID", "DEHUMIDIFY"),
    "operation_maintenance": ("SMART", "HEALTH", "COMFORT"),
    "installation_space_fit": ("WALL_SMALL", "LARGE_ROOM", "LIVING"),
}

AC_THEME_TIER_KEYS: dict[str, tuple[str, ...]] = {
    "cooling_heating_capacity_assurance": ("horsepower", "cooling_capacity", "heating"),
    "energy_cost_efficiency": ("energy",),
    "sleep_quiet_comfort": ("comfort",),
    "comfortable_airflow_health": ("comfort", "airflow", "health"),
    "large_space_coverage": ("horsepower", "cooling_capacity", "airflow"),
    "installation_space_fit": ("installation", "horsepower"),
    "operation_maintenance_convenience": ("smart", "comfort", "health"),
    "budget_configuration_efficiency": ("horsepower", "energy", "cooling_capacity"),
    "seasonal_reliability": ("heating", "health", "comfort"),
}

AC_FAMILY_TIER_KEYS: dict[str, tuple[str, ...]] = {
    family: tuple(
        dict.fromkeys(
            token for theme in themes for token in AC_THEME_TIER_KEYS.get(theme, ())
        )
    )
    for family, themes in {
        "capacity_match": (
            "cooling_heating_capacity_assurance",
            "installation_space_fit",
        ),
        "large_space": ("large_space_coverage", "cooling_heating_capacity_assurance"),
        "price_justification": (
            "cooling_heating_capacity_assurance",
            "seasonal_reliability",
        ),
        "energy_cost": ("energy_cost_efficiency", "budget_configuration_efficiency"),
        "budget_configuration": (
            "budget_configuration_efficiency",
            "energy_cost_efficiency",
        ),
        "sleep_quiet": ("sleep_quiet_comfort", "comfortable_airflow_health"),
        "airflow_health": ("comfortable_airflow_health",),
        "seasonal_reliability": ("seasonal_reliability",),
        "operation_maintenance": ("operation_maintenance_convenience",),
        "installation_space_fit": ("installation_space_fit",),
    }.items()
}


def purchase_reason_taxonomy(product_category: str):
    return (
        ac_purchase_reason_anchor_taxonomy_v0_1()
        if str(product_category).upper() == "AC"
        else tv_purchase_reason_anchor_taxonomy_v0_1()
    )


def battlefield_names(product_category: str) -> dict[str, str]:
    return dict(AC_BATTLEFIELD_CN) if str(product_category).upper() == "AC" else {}


def same_product_form(left, right) -> bool:
    """Match TV by inches and AC by canonical installation/horsepower tier."""

    if left.identity.product_category.upper() == "AC":
        return (
            bool(left.identity.size_tier)
            and left.identity.size_tier == right.identity.size_tier
        )
    left_size = left.identity.screen_size_inch
    right_size = right.identity.screen_size_inch
    return (
        left_size is not None
        and right_size is not None
        and abs(left_size - right_size) <= 0.5
    )


def product_form_feature(snapshot) -> float:
    if snapshot.identity.product_category.upper() == "AC":
        return AC_SIZE_TIER_RANK.get(str(snapshot.identity.size_tier or ""), 0.0)
    return float(snapshot.identity.screen_size_inch or 0)
