"""M10C target group profiles.

M10C is deterministic. It consumes M03B parameter facts, M04C claim facts,
M05C comment facts, and M07 market facts. It does not call an LLM and does not
reuse old M10 target-group outputs as input.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_MODULE_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.m11c_value_battlefield_service import (
    AC_CANONICAL_SIZE_TIERS,
    CANONICAL_SIZE_TIERS,
    PRICE_BANDS,
    M11CInputReader,
    _avg_decimal,
    _by_sku,
    _canonical_size_tier,
    _clamp_decimal,
    _decimal,
    _decimal_to_float,
    _derive_comparable_market_contexts,
    _derive_price_bands,
    fact_rule_versions_for_product_category,
    _group_by_sku,
    _json_safe,
    _list_or_empty,
    _market_snapshot,
    _market_validation_score,
    market_validation_policy_for_product_category,
    missing_size_price_reason_for_product_category,
    _param_entry_supported,
    price_band_policy_for_product_category,
    _sentiment_polarity,
    size_tier_policy_for_product_category,
    _unique,
)
from app.services.core3_real_data.param_extraction_repositories import (
    ParamExtractionRepository,
    ParamRepositoryHashConflictError,
    ParamRepositoryWriteResult,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


M10C_PROFILE_ID_HASH_VERSION = "m10c-target-group-profile-id-v1"
M10C_PROFILE_HASH_VERSION = "m10c-target-group-profile-v1"
M10C_SCORE_ID_HASH_VERSION = "m10c-target-group-score-id-v1"
M10C_SCORE_HASH_VERSION = "m10c-target-group-score-v1"
M10C_COVERAGE_ID_HASH_VERSION = "m10c-target-group-coverage-id-v1"
M10C_COVERAGE_HASH_VERSION = "m10c-target-group-coverage-v1"

REL_PRIMARY = "primary_target_group"
REL_SECONDARY = "secondary_target_group"
REL_COMMENT_OBSERVED = "comment_observed_group"
REL_BRAND_CLAIMED = "brand_claimed_group"
REL_LATENT = "latent_group"
REL_UNMET = "unmet_group_need"
REL_NOT_SUPPORTED = "not_supported"

BRAND_BOOST_CODES = ("brand_trust", "brand_repurchase", "brand_recommendation")
SERVICE_SUBDIMENSION_CODES = (
    "service_delivery_install",
    "service_fulfillment_excluded",
)


@dataclass(frozen=True)
class M10CTargetGroupDefinition:
    target_group_code: str
    target_group_name: str
    definition: str
    source_task_codes: tuple[str, ...]
    comment_subdimension_codes: tuple[str, ...]
    comment_keywords: tuple[str, ...]
    allowed_size_tiers: tuple[str, ...]
    allowed_price_bands: tuple[str, ...]
    claim_codes: tuple[str, ...]
    param_codes: tuple[str, ...]
    adjacent_size_tiers: tuple[str, ...] = ()
    adjacent_price_bands: tuple[str, ...] = ()


@dataclass(frozen=True)
class M10CTargetGroupTaxonomy:
    taxonomy_version: str
    product_category: str
    product_category_label_cn: str
    sku_code_prefix: str
    target_groups: tuple[M10CTargetGroupDefinition, ...]

    @property
    def target_groups_by_code(self) -> dict[str, M10CTargetGroupDefinition]:
        return {item.target_group_code: item for item in self.target_groups}


@dataclass(frozen=True)
class M10CSkuInput:
    sku_code: str
    model_name: str | None
    brand_name: str | None
    param_profile: entities.Core3SkuParamProfile
    market_profile: entities.Core3SkuMarketProfile | None
    claim_profile: entities.Core3SkuClaimFactProfile | None
    claim_facts: tuple[entities.Core3SkuClaimFact, ...]
    comment_profile: entities.Core3SkuCommentFactProfile | None
    comment_facts: tuple[entities.Core3CommentFactAtom, ...]
    size_tier: str
    price_band_in_size_tier: str
    price_percentile_in_size_tier: Decimal | None
    comparable_market_context: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class M10CWritePayload:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M10CServiceResult:
    input_count: int
    profile_count: int
    score_count: int
    coverage_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item["created_count"] for item in self.write_summary.values())


def tv_target_group_taxonomy_v0_1() -> M10CTargetGroupTaxonomy:
    """Published TV M10C target-group taxonomy confirmed in the business thread."""

    return M10CTargetGroupTaxonomy(
        taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
        product_category="TV",
        product_category_label_cn="彩电",
        sku_code_prefix="TV",
        target_groups=(
            _tg(
                "TG_MAINSTREAM_FAMILY_VIEWER",
                "主流家庭观影用户",
                "家庭客厅日常观影、追剧、综艺和全家观看，重视尺寸合适、画质够用、系统稳定。",
                ("TASK_MAINSTREAM_LIVING_VIEWING", "TASK_CINEMA_IMMERSION"),
                (
                    "audience_child_family",
                    "use_living_room_cinema",
                    "picture_clarity_resolution",
                    "audio_quality",
                    "system_smooth_ads",
                ),
                ("家庭", "客厅", "全家", "追剧", "日常看", "看电视"),
                ("medium_46_59", "large_60_69", "xlarge_70_85"),
                ("low", "mid_low", "mid", "mid_high"),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_speaker_sound",
                    "tv_claim_eye_care_display",
                    "tv_claim_voice_control",
                ),
                (
                    "screen_size_inch",
                    "resolution_class",
                    "hdr_support_flag",
                    "memory_capacity_gb",
                    "speaker_power_w",
                ),
                adjacent_size_tiers=("small_32_45",),
                adjacent_price_bands=("high",),
            ),
            _tg(
                "TG_LARGE_SCREEN_UPGRADER",
                "大屏换新升级用户",
                "从旧电视或小屏升级到 70/75/85 寸等大屏，核心关注屏幕变大、换新价值和大屏沉浸。",
                ("TASK_LARGE_SCREEN_UPGRADE", "TASK_CINEMA_IMMERSION"),
                (
                    "replacement_source",
                    "appearance_size_fit",
                    "use_living_room_cinema",
                    "value_price",
                ),
                ("换新", "换电视", "大屏", "升级", "75", "85", "尺寸大"),
                ("xlarge_70_85",),
                ("low", "mid_low", "mid", "mid_high"),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_value_price",
                    "tv_claim_full_screen_design",
                ),
                ("screen_size_inch", "price_per_inch", "full_screen_design_flag"),
                adjacent_size_tiers=("large_60_69", "giant_98_plus"),
                adjacent_price_bands=("high",),
            ),
            _tg(
                "TG_PREMIUM_AV_ENTHUSIAST",
                "高端影音体验用户",
                "追求高亮度、控光、色彩、MiniLED/OLED/QD、画质芯片和音画体验的高端影音人群。",
                ("TASK_PREMIUM_PICTURE_EXPERIENCE", "TASK_CINEMA_IMMERSION"),
                (
                    "picture_clarity_resolution",
                    "picture_brightness_hdr",
                    "picture_color_accuracy",
                    "picture_local_dimming_black",
                    "audio_quality",
                ),
                ("画质", "亮度", "控光", "色彩", "黑位", "miniled", "oled", "音效"),
                ("large_60_69", "xlarge_70_85"),
                ("mid_high", "high"),
                (
                    "tv_claim_miniled_display",
                    "tv_claim_qd_miniled_display",
                    "tv_claim_rgb_miniled_display",
                    "tv_claim_oled_self_lit",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_wide_color_accuracy",
                    "tv_claim_local_dimming",
                    "tv_claim_picture_engine_ai",
                    "tv_claim_dolby_audio_video",
                ),
                (
                    "display_tech_class",
                    "declared_brightness_nit_or_band",
                    "local_dimming_zone_count",
                    "color_gamut_percent",
                    "picture_engine_chip",
                    "speaker_power_w",
                ),
                adjacent_price_bands=("mid",),
            ),
            _tg(
                "TG_GIANT_HOME_THEATER_BUYER",
                "巨幕家庭影院用户",
                "98 寸及以上巨幕、大客厅或新家影院场景，重视旗舰体验、沉浸感和空间融合。",
                ("TASK_CINEMA_IMMERSION", "TASK_HOME_DECOR_SPACE_FIT"),
                (
                    "use_living_room_cinema",
                    "appearance_size_fit",
                    "appearance_slim_wall",
                    "audio_quality",
                ),
                ("巨幕", "98", "100", "大客厅", "新家", "影院", "上墙"),
                ("giant_98_plus",),
                ("mid_high", "high"),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_local_dimming",
                    "tv_claim_dolby_audio_video",
                    "tv_claim_flush_wall_mount",
                ),
                (
                    "screen_size_inch",
                    "display_tech_class",
                    "declared_brightness_nit_or_band",
                    "local_dimming_zone_count",
                    "speaker_power_w",
                    "flush_wall_mount_flag",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("mid",),
            ),
            _tg(
                "TG_VALUE_MAXIMIZER",
                "性价比理性用户",
                "预算内追求更大尺寸、更好配置、更高销量口碑和补贴价格的理性购买人群。",
                ("TASK_VALUE_FOR_MONEY_PURCHASE", "TASK_LARGE_SCREEN_UPGRADE"),
                ("value_price", "replacement_source", "use_living_room_cinema"),
                ("划算", "性价比", "便宜", "优惠", "补贴", "价格合适", "值"),
                CANONICAL_SIZE_TIERS,
                ("low", "mid_low", "mid"),
                (
                    "tv_claim_value_price",
                    "tv_claim_theater_scene",
                    "tv_claim_high_refresh_rate",
                    "tv_claim_hdr_high_brightness",
                ),
                (
                    "screen_size_inch",
                    "price_per_inch",
                    "resolution_class",
                    "declared_brightness_nit_or_band",
                    "declared_refresh_rate_hz",
                ),
                adjacent_price_bands=("mid_high",),
            ),
            _tg(
                "TG_GAMING_SPORTS_USER",
                "游戏体育娱乐用户",
                "连接主机游戏、看球赛或高速运动内容，关注高刷、低延迟、HDMI2.1、流畅和拖影。",
                ("TASK_GAMING_CONSOLE_ENTERTAINMENT", "TASK_SPORTS_MOTION_WATCHING"),
                (
                    "use_gaming_sports",
                    "gaming_high_refresh_motion",
                    "system_smooth_ads",
                ),
                (
                    "游戏",
                    "主机",
                    "ps5",
                    "xbox",
                    "看球",
                    "体育",
                    "高刷",
                    "低延迟",
                    "流畅",
                ),
                ("medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus"),
                ("mid", "mid_high", "high"),
                (
                    "tv_claim_high_refresh_rate",
                    "tv_claim_gaming_low_latency",
                    "tv_claim_hdmi21_connectivity",
                ),
                (
                    "declared_refresh_rate_hz",
                    "hdmi21_flag",
                    "memc_motion_flag",
                    "vrr_allm_flag",
                    "memory_capacity_gb",
                ),
                adjacent_price_bands=("mid_low",),
            ),
            _tg(
                "TG_CHILD_FAMILY_LONG_WATCH",
                "儿童家庭长看用户",
                "儿童、家庭或长时间观看场景，关注护眼、舒适、不刺眼、低蓝光和观看疲劳。",
                ("TASK_EYE_CARE_LONG_WATCHING", "TASK_MAINSTREAM_LIVING_VIEWING"),
                (
                    "audience_child_family",
                    "picture_eye_care_reflection",
                    "use_living_room_cinema",
                ),
                ("孩子", "儿童", "护眼", "不刺眼", "长时间", "眼睛", "舒服"),
                ("small_32_45", "medium_46_59", "large_60_69"),
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "tv_claim_eye_care_display",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_wide_color_accuracy",
                ),
                (
                    "eye_care_certification_flag",
                    "low_blue_light_flag",
                    "flicker_free_flag",
                    "declared_brightness_nit_or_band",
                    "declared_refresh_rate_hz",
                    "hdr_support_flag",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("low",),
            ),
            _tg(
                "TG_SENIOR_PARENT_FRIENDLY",
                "长辈友好使用用户",
                "给父母或老人使用，重视语音、遥控简单、系统清爽、广告少和操作门槛低。",
                ("TASK_SENIOR_EASY_OPERATION", "TASK_MAINSTREAM_LIVING_VIEWING"),
                (
                    "audience_senior",
                    "interaction_voice_casting",
                    "system_smooth_ads",
                    "use_living_room_cinema",
                ),
                ("老人", "父母", "爸妈", "长辈", "语音", "遥控", "广告少", "操作简单"),
                ("small_32_45", "medium_46_59", "large_60_69"),
                ("low", "mid_low", "mid"),
                (
                    "tv_claim_voice_control",
                    "tv_claim_casting_connectivity",
                    "tv_claim_ai_large_model",
                ),
                (
                    "voice_recognition_flag",
                    "far_field_voice_flag",
                    "network_tv_flag",
                    "wifi_builtin_flag",
                    "memory_capacity_gb",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("mid_high",),
            ),
            _tg(
                "TG_BEDROOM_RENTAL_SECOND_SCREEN",
                "卧室副屏/租房用户",
                "卧室、租房、宿舍或第二台电视，关注小尺寸、低价、够用、易用和空间适配。",
                ("TASK_BEDROOM_SECOND_SCREEN", "TASK_VALUE_FOR_MONEY_PURCHASE"),
                (
                    "audience_rental_room",
                    "use_bedroom",
                    "value_price",
                    "appearance_size_fit",
                ),
                ("卧室", "租房", "宿舍", "第二台", "小房间", "副屏", "小尺寸"),
                ("small_32_45",),
                ("low", "mid_low"),
                (
                    "tv_claim_value_price",
                    "tv_claim_full_screen_design",
                    "tv_claim_voice_control",
                ),
                (
                    "screen_size_inch",
                    "resolution_class",
                    "smart_tv_flag",
                    "voice_recognition_flag",
                    "price_per_inch",
                ),
                adjacent_size_tiers=("medium_46_59",),
                adjacent_price_bands=("mid",),
            ),
            _tg(
                "TG_SMART_CONNECTED_USER",
                "投屏互联智能用户",
                "手机投屏、无线连接、AI 语音、家电联动、摄像头互动等智能连接使用人群。",
                ("TASK_SMART_CASTING_IOT", "TASK_SENIOR_EASY_OPERATION"),
                (
                    "use_casting_online",
                    "interaction_voice_casting",
                    "system_smooth_ads",
                    "audience_senior",
                ),
                ("投屏", "连接", "联网", "语音", "AI", "家电联动", "摄像头", "智能"),
                ("medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus"),
                ("mid", "mid_high", "high"),
                (
                    "tv_claim_casting_connectivity",
                    "tv_claim_voice_control",
                    "tv_claim_ai_large_model",
                    "tv_claim_smart_home_iot",
                    "tv_claim_camera_interaction",
                ),
                (
                    "wifi_builtin_flag",
                    "network_tv_flag",
                    "smart_tv_flag",
                    "ai_large_model_flag",
                    "voice_recognition_flag",
                    "far_field_voice_flag",
                    "iot_control_flag",
                    "camera_builtin_flag",
                    "memory_capacity_gb",
                ),
                adjacent_size_tiers=("small_32_45",),
                adjacent_price_bands=("mid_low",),
            ),
        ),
    )


def ac_target_group_taxonomy_v0_1() -> M10CTargetGroupTaxonomy:
    """Published AC M10C target-group taxonomy derived from AC fact profiles."""

    return M10CTargetGroupTaxonomy(
        taxonomy_version=CORE3_M10C_AC_TAXONOMY_VERSION,
        product_category="AC",
        product_category_label_cn="空调",
        sku_code_prefix="AC",
        target_groups=(
            _tg(
                "TG_RENTER_SMALL_ROOM",
                "租房小空间用户",
                "租房、宿舍、小卧室等低安装复杂度场景，优先关注小匹数挂机、价格和空间适配。",
                (
                    "TASK_INSTALL_SPACE_FIT",
                    "TASK_VALUE_SUBSIDY_PURCHASE",
                    "TASK_FAST_COOL_HEAT",
                ),
                (
                    "use_rental_dorm",
                    "audience_rental_young",
                    "space_fit_area",
                    "value_positive",
                    "installation_form",
                ),
                ("租房", "宿舍", "小房间", "小卧室", "便宜", "安装"),
                ("wall_hp_1_or_below", "wall_hp_1_5"),
                ("low", "mid_low", "mid"),
                (
                    "ac_claim_price_value_subsidy",
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_installation_space_design",
                ),
                ("installation_type", "horsepower_hp", "energy_grade_normalized"),
                adjacent_price_bands=("mid_high",),
            ),
            _tg(
                "TG_VALUE_REPLACEMENT_BUYER",
                "换新性价比用户",
                "旧机替换、补贴和同价位价值敏感用户，关注价格、能效和基础冷暖能力。",
                (
                    "TASK_VALUE_SUBSIDY_PURCHASE",
                    "TASK_FAST_COOL_HEAT",
                    "TASK_ENERGY_SAVING_LONG_USE",
                ),
                (
                    "replacement_source",
                    "value_positive",
                    "subsidy_promotion",
                    "same_price_value",
                    "price_negative",
                ),
                ("换新", "补贴", "性价比", "优惠", "同价位", "划算"),
                AC_CANONICAL_SIZE_TIERS,
                ("low", "mid_low", "mid"),
                (
                    "ac_claim_price_value_subsidy",
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_authority_sales_certification",
                ),
                ("horsepower_hp", "energy_grade_normalized", "inverter_flag"),
                adjacent_price_bands=("mid_high",),
            ),
            _tg(
                "TG_BEDROOM_SLEEP_SENSITIVE",
                "卧室睡眠敏感用户",
                "卧室和夜间睡眠使用，关注静音、柔风、防直吹和省电。",
                (
                    "TASK_SLEEP_QUIET",
                    "TASK_SOFT_WIND_NO_DIRECT",
                    "TASK_ENERGY_SAVING_LONG_USE",
                ),
                (
                    "use_bedroom_sleep",
                    "quiet_positive",
                    "sleep_scene",
                    "noise_risk",
                    "soft_wind_no_direct",
                ),
                ("卧室", "睡眠", "静音", "不直吹", "柔风", "夜晚"),
                ("wall_hp_1_or_below", "wall_hp_1_5", "wall_hp_2"),
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "ac_claim_quiet_sleep",
                    "ac_claim_soft_wind_no_direct",
                    "ac_claim_ai_energy_saving",
                ),
                (
                    "installation_type",
                    "comfort_airflow_flag",
                    "energy_efficiency_ratio",
                ),
                adjacent_price_bands=("low",),
            ),
            _tg(
                "TG_FAMILY_LONG_USE_SAVER",
                "家庭长时使用省电用户",
                "家庭日常长时间使用，关注一级能效、APF、AI 省电和电费感知。",
                (
                    "TASK_ENERGY_SAVING_LONG_USE",
                    "TASK_STABLE_TEMPERATURE",
                    "TASK_FAST_COOL_HEAT",
                ),
                (
                    "audience_family",
                    "energy_saving_usage",
                    "energy_grade_apf",
                    "electricity_cost",
                    "use_summer_winter",
                ),
                ("家庭", "全家", "省电", "电费", "一级能效", "长时间"),
                AC_CANONICAL_SIZE_TIERS,
                PRICE_BANDS,
                (
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_ai_energy_saving",
                    "ac_claim_fast_cooling_heating",
                ),
                ("energy_grade_normalized", "energy_efficiency_ratio", "inverter_flag"),
            ),
            _tg(
                "TG_CHILD_ELDER_COMFORT",
                "儿童老人舒适敏感家庭",
                "孩子、老人和敏感人群，关注柔风、静音、洁净、除菌和易用。",
                (
                    "TASK_SOFT_WIND_NO_DIRECT",
                    "TASK_SLEEP_QUIET",
                    "TASK_HEALTH_CLEAN_AIR",
                ),
                (
                    "audience_child_baby",
                    "audience_senior_parent",
                    "audience_sensitive",
                    "soft_wind_no_direct",
                    "quiet_positive",
                    "purification_antibacterial",
                ),
                ("孩子", "老人", "父母", "宝宝", "敏感", "柔风", "除菌"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "ac_claim_soft_wind_no_direct",
                    "ac_claim_quiet_sleep",
                    "ac_claim_purification_antibacterial",
                    "ac_claim_self_cleaning",
                ),
                ("comfort_airflow_flag", "self_cleaning_flag", "purification_flag"),
                adjacent_price_bands=("low",),
            ),
            _tg(
                "TG_LIVING_ROOM_LARGE_SPACE",
                "客厅大空间用户",
                "客厅、大面积房间和门店空间，关注柜机、大匹数、大风量和冷暖覆盖。",
                (
                    "TASK_LARGE_SPACE_COVERAGE",
                    "TASK_FAST_COOL_HEAT",
                    "TASK_STABLE_TEMPERATURE",
                ),
                (
                    "use_living_room_large",
                    "airflow_volume_coverage",
                    "space_fit_area",
                    "cooling_effect",
                    "fast_cooling_heating",
                ),
                ("客厅", "大空间", "柜机", "大风量", "覆盖", "3匹"),
                (
                    "wall_hp_2",
                    "wall_hp_3",
                    "floor_hp_2",
                    "floor_hp_3",
                    "floor_hp_3_plus",
                ),
                PRICE_BANDS,
                (
                    "ac_claim_large_airflow_coverage",
                    "ac_claim_fast_cooling_heating",
                    "ac_claim_wide_temperature_operation",
                ),
                (
                    "horsepower_hp",
                    "cooling_capacity_w",
                    "airflow_volume_m3h",
                    "installation_type",
                ),
                adjacent_size_tiers=("wall_hp_1_5",),
            ),
            _tg(
                "TG_SMART_REMOTE_USER",
                "智能远程控制用户",
                "需要 APP 远程、WiFi、语音、IoT 或遥控面板易用的智能家居用户。",
                ("TASK_SMART_REMOTE_CONTROL", "TASK_SLEEP_QUIET"),
                (
                    "smart_app_remote",
                    "remote_panel_easy_use",
                    "voice_iot",
                    "smart_negative",
                ),
                ("APP", "远程", "WiFi", "语音", "智能家居", "遥控"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid", "mid_high", "high"),
                ("ac_claim_smart_app_voice_iot",),
                ("wifi_control_flag", "voice_control_flag", "smart_sensing_flag"),
                adjacent_price_bands=("mid_low",),
            ),
            _tg(
                "TG_HOME_DECOR_SPACE_FIT",
                "新家装修空间适配用户",
                "新家装修、外观颜值、安装形态和面积适配敏感用户。",
                ("TASK_INSTALL_SPACE_FIT", "TASK_LARGE_SPACE_COVERAGE"),
                (
                    "appearance_design",
                    "space_fit_area",
                    "installation_form",
                    "installation_constraint",
                ),
                ("新家", "装修", "外观", "颜值", "空间", "面积", "安装"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "ac_claim_installation_space_design",
                    "ac_claim_large_airflow_coverage",
                ),
                (
                    "installation_type",
                    "indoor_unit_dimensions_mm",
                    "installation_hp_segment",
                ),
                adjacent_price_bands=("low",),
            ),
            _tg(
                "TG_HUMID_SOUTH_USER",
                "南方潮湿除湿用户",
                "南方潮湿、梅雨季和湿度控制场景，关注除湿、自清洁和异味霉味。",
                ("TASK_DEHUMIDIFY_HUMID_CLIMATE", "TASK_HEALTH_CLEAN_AIR"),
                (
                    "use_humid_south",
                    "dehumidification",
                    "humid_weather",
                    "odor_mold_risk",
                    "self_cleaning",
                ),
                ("南方", "潮湿", "除湿", "梅雨", "霉味", "异味"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                ("ac_claim_humidity_dehumidification", "ac_claim_self_cleaning"),
                ("self_cleaning_flag", "purification_flag"),
                adjacent_price_bands=("low",),
            ),
            _tg(
                "TG_BRAND_QUALITY_TRUST_BUYER",
                "品牌品质信任用户",
                "重视品牌信任、复购推荐、耐用品质和核心部件可靠性的用户。",
                ("TASK_RELIABLE_LONG_TERM_USE", "TASK_FAST_COOL_HEAT"),
                (
                    "brand_trust",
                    "brand_repurchase",
                    "brand_recommendation",
                    "durability_positive",
                    "core_component",
                    "failure_risk",
                ),
                ("品牌", "复购", "推荐", "耐用", "品质", "故障", "核心部件"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "ac_claim_durability_core_material",
                    "ac_claim_authority_sales_certification",
                    "ac_claim_warranty_install_service",
                ),
                ("inverter_flag", "refrigerant_type", "energy_efficiency_ratio"),
                adjacent_price_bands=("low",),
            ),
        ),
    )


class M10CTargetGroupTaxonomyLoader:
    def load(
        self, taxonomy_version: str, *, product_category: str
    ) -> M10CTargetGroupTaxonomy:
        normalized_category = str(product_category or "").upper()
        if (
            normalized_category == "TV"
            and taxonomy_version == CORE3_M10C_TV_TAXONOMY_VERSION
        ):
            return tv_target_group_taxonomy_v0_1()
        if (
            normalized_category == "AC"
            and taxonomy_version == CORE3_M10C_AC_TAXONOMY_VERSION
        ):
            return ac_target_group_taxonomy_v0_1()
        raise ValueError(
            f"{normalized_category or product_category} 目标客群 taxonomy 未发布，不能生成 M10C 目标客群画像。"
        )


class M10CTargetGroupRepository(ParamExtractionRepository):
    def save_profiles(
        self, profiles: Sequence[Any], *, replace_on_hash_conflict: bool = False
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3M10cSkuTargetGroupProfile,
            profiles,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "sku_code",
                "rule_version",
                "is_current",
            ),
            hash_field="profile_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_scores(
        self, scores: Sequence[Any], *, replace_on_hash_conflict: bool = False
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3M10cSkuTargetGroupScore,
            scores,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "sku_code",
                "target_group_code",
                "rule_version",
                "is_current",
            ),
            hash_field="result_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_coverages(
        self, coverages: Sequence[Any], *, replace_on_hash_conflict: bool = False
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3M10cTargetGroupCoverage,
            coverages,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "target_group_code",
                "rule_version",
                "is_current",
            ),
            hash_field="coverage_hash",
            replace_existing=replace_on_hash_conflict,
        )


class M10CInputReader(M11CInputReader):
    """M10C and M11C consume the same fact-layer tables and versions."""


class M10CRunner:
    module_code = Core3ModuleCode.M10C

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(
        self, context: Core3RunContext, target: Core3ModuleTarget
    ) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(
                project_id=context.project_id,
                category_code=context.category_code.value,
                batch_id=None,
                run_id=context.run_id,
                message_cn="M10C 缺少 M00 batch_id，无法生成目标客群画像。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            product_category=str(target.metadata.get("product_category") or "TV"),
            taxonomy_version=str(
                target.metadata.get("taxonomy_version")
                or CORE3_M10C_TV_TAXONOMY_VERSION
            ),
            rule_version=str(
                target.metadata.get("rule_version") or CORE3_M10C_TV_RULE_VERSION
            ),
            target_sku_codes=target.target_ids,
            target_group_codes=target.metadata.get("target_group_codes") or (),
            force_rebuild=bool(target.metadata.get("force_rebuild")),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M10C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M10C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        target_group_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(
            db=self.db, project_id=project_id, category_code=category_code
        )
        try:
            SourceBatchReader(repository_context).get_consumable_batch(batch_id)
        except ValueError as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        try:
            with self.db.begin_nested():
                service_result = M10CService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    taxonomy_version=taxonomy_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    target_group_codes=target_group_codes,
                    force_rebuild=force_rebuild,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m10c_target_group_hash_conflict",
                message_cn="M10C 目标客群画像结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m10c_target_group_failed",
                message_cn="M10C 目标客群画像生成失败，请检查 M03B/M04C/M05C/M07 事实层是否已生成。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M10C_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
            "product_category": product_category,
            "target_sku_codes": list(target_sku_codes),
            "target_group_codes": list(target_group_codes),
            **service_result.summary,
        }
        status = (
            Core3RunStatus.WARNING
            if service_result.warnings
            else Core3RunStatus.SUCCESS
        )
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M10C,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.profile_count
            + service_result.score_count
            + service_result.coverage_count,
            output_hash=stable_hash(
                summary_json, version="m10c_target_group_summary_v1"
            ),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {
                    "module_code": "M11C",
                    "reason": "目标客群变化会影响价值战场解释和后续竞品库。",
                },
                {
                    "module_code": "M12",
                    "reason": "目标客群变化会影响竞品召回和候选池解释。",
                },
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M10CService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M10C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M10C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        target_group_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> M10CServiceResult:
        taxonomy = M10CTargetGroupTaxonomyLoader().load(
            taxonomy_version, product_category=product_category
        )
        selected_groups = _filter_target_groups(taxonomy, target_group_codes)
        fact_versions = fact_rule_versions_for_product_category(
            taxonomy.product_category
        )
        reader = M10CInputReader(self.context)
        param_profiles = reader.list_param_profiles(
            batch_id,
            sku_code_prefix=taxonomy.sku_code_prefix,
            param_rule_version=fact_versions["param_rule_version"],
            target_sku_codes=target_sku_codes,
        )
        sku_codes = [profile.sku_code for profile in param_profiles]
        context_param_profiles = param_profiles
        if target_sku_codes:
            context_param_profiles = reader.list_param_profiles(
                batch_id,
                sku_code_prefix=taxonomy.sku_code_prefix,
                param_rule_version=fact_versions["param_rule_version"],
            )
        context_sku_codes = [profile.sku_code for profile in context_param_profiles]
        market_profiles = _by_sku(reader.list_market_profiles(batch_id, sku_codes))
        market_weekly_rows = reader.list_clean_market_weekly(batch_id, sku_codes)
        context_market_profiles = market_profiles
        context_market_weekly_rows = market_weekly_rows
        if target_sku_codes:
            context_market_profiles = _by_sku(
                reader.list_market_profiles(batch_id, context_sku_codes)
            )
            context_market_weekly_rows = reader.list_clean_market_weekly(
                batch_id, context_sku_codes
            )
        claim_profiles = _by_sku(
            reader.list_claim_profiles(
                batch_id,
                sku_codes,
                claim_rule_version=fact_versions["claim_rule_version"],
            )
        )
        claim_facts = _group_by_sku(
            reader.list_claim_facts(
                batch_id,
                sku_codes,
                claim_rule_version=fact_versions["claim_rule_version"],
            )
        )
        comment_profiles = _by_sku(
            reader.list_comment_profiles(
                batch_id,
                sku_codes,
                comment_rule_version=fact_versions["comment_rule_version"],
            )
        )
        comment_facts = _group_by_sku(
            reader.list_comment_facts(
                batch_id,
                sku_codes,
                comment_rule_version=fact_versions["comment_rule_version"],
            )
        )
        sku_inputs = _build_sku_inputs(
            param_profiles=param_profiles,
            market_profiles=market_profiles,
            market_weekly_rows=market_weekly_rows,
            claim_profiles=claim_profiles,
            claim_facts=claim_facts,
            comment_profiles=comment_profiles,
            comment_facts=comment_facts,
            context_param_profiles=context_param_profiles,
            context_market_profiles=context_market_profiles,
            context_market_weekly_rows=context_market_weekly_rows,
        )
        profiles, scores, coverages, summary = M10CProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            target_groups=selected_groups,
            rule_version=rule_version,
        ).build(sku_inputs)

        repository = M10CTargetGroupRepository(self.context)
        write_results = {
            "target_group_profiles": repository.save_profiles(
                profiles, replace_on_hash_conflict=force_rebuild
            ),
            "target_group_scores": repository.save_scores(
                scores, replace_on_hash_conflict=force_rebuild
            ),
            "target_group_coverages": repository.save_coverages(
                coverages, replace_on_hash_conflict=force_rebuild
            ),
        }
        warnings: list[str] = []
        if not sku_inputs:
            warnings.append(
                "M10C 没有读取到 M03B 参数画像，无法生成 SKU 目标客群画像。"
            )
        if sku_inputs and not any(item.market_profile for item in sku_inputs):
            warnings.append(
                "M10C 没有读取到 M07 full_observed_window 市场画像，价格带和市场验证降级。"
            )
        if sku_inputs and not any(
            item.comparable_market_context for item in sku_inputs
        ):
            warnings.append(
                "M10C 没有读取到 M01 周度量价事实，市场验证降级为 M07 累计窗口兼容口径。"
            )
        if sku_inputs and not any(item.comment_profile for item in sku_inputs):
            warnings.append("M10C 没有读取到 M05C 评论事实画像，真实用户客群证据降级。")
        return M10CServiceResult(
            input_count=len(sku_inputs),
            profile_count=len(profiles),
            score_count=len(scores),
            coverage_count=len(coverages),
            warnings=warnings,
            write_summary={
                key: {
                    "created_count": value.created_count,
                    "reused_count": value.reused_count,
                }
                for key, value in write_results.items()
            },
            summary=summary,
        )


class M10CProfileBuilder:
    def __init__(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        taxonomy: M10CTargetGroupTaxonomy,
        target_groups: tuple[M10CTargetGroupDefinition, ...],
        rule_version: str,
    ) -> None:
        self.project_id = project_id
        self.category_code = category_code
        self.batch_id = batch_id
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.taxonomy = taxonomy
        self.target_groups = target_groups
        self.rule_version = rule_version

    def build(
        self,
        sku_inputs: Sequence[M10CSkuInput],
    ) -> tuple[
        list[M10CWritePayload],
        list[M10CWritePayload],
        list[M10CWritePayload],
        dict[str, Any],
    ]:
        profiles: list[M10CWritePayload] = []
        scores: list[M10CWritePayload] = []
        status_counts: Counter[str] = Counter()
        primary_counts: Counter[str] = Counter()
        size_price_counts: Counter[str] = Counter()

        for sku_input in sku_inputs:
            sku_scores = [
                self._score_target_group(sku_input, target_group)
                for target_group in self.target_groups
            ]
            sku_scores = self._assign_primary_secondary(sku_scores)
            scores.extend(M10CWritePayload(payload) for payload in sku_scores)
            profiles.append(
                M10CWritePayload(self._profile_payload(sku_input, sku_scores))
            )
            for payload in sku_scores:
                status_counts[payload["relation_status"]] += 1
                if payload["relation_status"] == REL_PRIMARY:
                    primary_counts[payload["target_group_code"]] += 1
            size_price_counts[
                f"{sku_input.size_tier}:{sku_input.price_band_in_size_tier}"
            ] += 1

        score_payloads = [score.payload for score in scores]
        coverages = [
            M10CWritePayload(payload)
            for payload in self._coverage_payloads(score_payloads)
        ]
        summary = {
            "sku_count": len(sku_inputs),
            "profile_count": len(profiles),
            "score_count": len(scores),
            "coverage_count": len(coverages),
            "target_group_count": len(self.target_groups),
            "relation_status_counts": dict(sorted(status_counts.items())),
            "primary_target_group_counts": dict(sorted(primary_counts.items())),
            "size_price_counts": dict(sorted(size_price_counts.items())),
            "taxonomy_codes": [
                target_group.target_group_code for target_group in self.target_groups
            ],
            "size_tier_policy": size_tier_policy_for_product_category(
                self.taxonomy.product_category, "M10C"
            ),
            "price_band_policy": price_band_policy_for_product_category(
                self.taxonomy.product_category, "M10C"
            ),
            "market_validation_policy": market_validation_policy_for_product_category(
                self.taxonomy.product_category
            ),
        }
        return profiles, scores, coverages, summary

    def _score_target_group(
        self, sku_input: M10CSkuInput, target_group: M10CTargetGroupDefinition
    ) -> dict[str, Any]:
        size_price_gate_status = _size_price_gate_status(sku_input, target_group)
        size_price_fit_score = _size_price_fit_score(size_price_gate_status)
        comment_match = _comment_match(sku_input.comment_facts, target_group)
        claim_match = _claim_match(
            sku_input.claim_facts, sku_input.claim_profile, target_group
        )
        param_match = _param_match(
            sku_input.param_profile, sku_input.market_profile, target_group
        )
        brand_trust_boost = _brand_trust_boost(sku_input.comment_facts)
        comment_score = comment_match["score"]
        claim_score = claim_match["score"]
        param_score = param_match["score"]
        task_support_score = _task_support_score(
            comment_score=comment_score,
            claim_score=claim_score,
            param_score=param_score,
            size_price_fit_score=size_price_fit_score,
            direct_comment_count=comment_match["direct_count"],
            use_case_count=comment_match["use_case_count"],
        )
        market_validation_score = _market_validation_score(
            sku_input.market_profile, sku_input.comparable_market_context
        )
        target_group_score = _clamp_decimal(
            comment_score * Decimal("0.30")
            + task_support_score * Decimal("0.20")
            + size_price_fit_score * Decimal("0.15")
            + claim_score * Decimal("0.12")
            + param_score * Decimal("0.10")
            + market_validation_score * Decimal("0.08")
            + brand_trust_boost * Decimal("0.05")
        )
        relation_status = _initial_relation_status(
            size_price_gate_status=size_price_gate_status,
            score=target_group_score,
            comment_score=comment_score,
            task_support_score=task_support_score,
            claim_score=claim_score,
            param_score=param_score,
            positive_count=comment_match["positive_count"],
            negative_count=comment_match["negative_count"],
            service_only=comment_match["service_only"],
        )
        evidence_ids = _unique(
            [
                *comment_match["evidence_ids"],
                *claim_match["evidence_ids"],
                *_list_or_empty(sku_input.param_profile.evidence_ids),
                *_list_or_empty(
                    sku_input.market_profile.evidence_ids
                    if sku_input.market_profile
                    else []
                ),
            ]
        )
        review_reason = _review_reason(
            relation_status,
            size_price_gate_status,
            comment_match,
            claim_match,
            param_match,
            brand_trust_boost,
        )
        review_required = bool(review_reason["reason_codes"])
        payload = {
            "score_id": _score_id(
                self.project_id,
                self.batch_id,
                self.taxonomy.taxonomy_version,
                sku_input.sku_code,
                target_group.target_group_code,
                self.rule_version,
            ),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "rule_version": self.rule_version,
            "sku_code": sku_input.sku_code,
            "model_name": sku_input.model_name,
            "brand_name": sku_input.brand_name,
            "target_group_code": target_group.target_group_code,
            "target_group_name": target_group.target_group_name,
            "target_group_definition": target_group.definition,
            "relation_status": relation_status,
            "target_group_score": target_group_score,
            "comment_audience_motivation_score": comment_score,
            "task_support_score": task_support_score,
            "size_price_fit_score": size_price_fit_score,
            "claim_alignment_score": claim_score,
            "param_capability_score": param_score,
            "market_validation_score": market_validation_score,
            "brand_trust_boost": brand_trust_boost,
            "sentiment_polarity": comment_match["sentiment_polarity"],
            "size_tier": sku_input.size_tier,
            "price_band_in_size_tier": sku_input.price_band_in_size_tier,
            "price_percentile_in_size_tier": sku_input.price_percentile_in_size_tier,
            "score_breakdown_json": _json_safe(
                {
                    "comment_audience_motivation": comment_match,
                    "task_proxy_support": {
                        "source_task_codes": target_group.source_task_codes,
                        "score": task_support_score,
                        "uses_m09c": False,
                    },
                    "size_price": {
                        "gate_status": size_price_gate_status,
                        "allowed_size_tiers": target_group.allowed_size_tiers,
                        "allowed_price_bands": target_group.allowed_price_bands,
                        "score": size_price_fit_score,
                    },
                    "claim_alignment": claim_match,
                    "param_capability": param_match,
                    "brand_trust_boost": brand_trust_boost,
                    "market": _market_snapshot(
                        sku_input.market_profile, sku_input.comparable_market_context
                    ),
                }
            ),
            "status_reason_cn": _status_reason_cn(
                target_group,
                relation_status=relation_status,
                size_price_gate_status=size_price_gate_status,
                comment_score=comment_score,
                task_support_score=task_support_score,
                claim_score=claim_score,
                param_score=param_score,
                comment_match=comment_match,
            ),
            "evidence_ids_json": evidence_ids[:80],
            "review_required": review_required,
            "review_status": "review_required" if review_required else "auto_pass",
            "review_reason_json": _json_safe(review_reason),
            "confidence": _confidence(
                size_price_fit_score,
                comment_score,
                task_support_score,
                claim_score,
                param_score,
                sku_input,
            ),
            "is_current": True,
        }
        payload["result_hash"] = _score_result_hash(
            payload, self.taxonomy.taxonomy_version, self.rule_version
        )
        return payload

    def _assign_primary_secondary(
        self, score_payloads: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        eligible = [
            payload
            for payload in score_payloads
            if payload["relation_status"] == REL_SECONDARY
            and payload["target_group_score"] >= Decimal("0.6800")
            and payload["score_breakdown_json"]["size_price"]["gate_status"]
            in {"matched", "adjacent"}
        ]
        eligible.sort(
            key=lambda item: (
                item["target_group_score"],
                item["comment_audience_motivation_score"],
                item["task_support_score"],
                item["claim_alignment_score"],
            ),
            reverse=True,
        )
        if eligible:
            eligible[0]["relation_status"] = REL_PRIMARY
            eligible[0]["status_reason_cn"] = eligible[0]["status_reason_cn"].replace(
                "可作为候选客群", "作为主目标客群"
            )
            eligible[0]["result_hash"] = _score_result_hash(
                eligible[0], self.taxonomy.taxonomy_version, self.rule_version
            )

        secondary = [
            payload
            for payload in score_payloads
            if payload["relation_status"] == REL_SECONDARY
        ]
        secondary.sort(key=lambda item: item["target_group_score"], reverse=True)
        for payload in secondary[3:]:
            payload["relation_status"] = REL_LATENT
            payload["status_reason_cn"] = (
                f"{payload['target_group_name']}证据成立但已超出最多三个次客群限制，降为潜在客群。"
            )
            payload["result_hash"] = _score_result_hash(
                payload, self.taxonomy.taxonomy_version, self.rule_version
            )
        return score_payloads

    def _profile_payload(
        self, sku_input: M10CSkuInput, score_payloads: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        primary = next(
            (item for item in score_payloads if item["relation_status"] == REL_PRIMARY),
            None,
        )
        secondary = sorted(
            [
                item
                for item in score_payloads
                if item["relation_status"] == REL_SECONDARY
            ],
            key=lambda item: item["target_group_score"],
            reverse=True,
        )[:3]
        observed = sorted(
            [
                item
                for item in score_payloads
                if item["relation_status"] == REL_COMMENT_OBSERVED
            ],
            key=lambda item: item["target_group_score"],
            reverse=True,
        )
        claimed = sorted(
            [
                item
                for item in score_payloads
                if item["relation_status"] == REL_BRAND_CLAIMED
            ],
            key=lambda item: item["target_group_score"],
            reverse=True,
        )
        latent = sorted(
            [item for item in score_payloads if item["relation_status"] == REL_LATENT],
            key=lambda item: item["target_group_score"],
            reverse=True,
        )
        unmet = sorted(
            [item for item in score_payloads if item["relation_status"] == REL_UNMET],
            key=lambda item: item["target_group_score"],
            reverse=True,
        )
        evidence_ids = _unique(
            evidence_id
            for item in score_payloads
            for evidence_id in item["evidence_ids_json"]
        )
        no_primary_reason = (
            None
            if primary
            else _no_primary_reason(
                score_payloads, sku_input, self.taxonomy.product_category
            )
        )
        summary = {
            "primary": _compact_score(primary) if primary else None,
            "secondary": [_compact_score(item) for item in secondary],
            "comment_observed": [_compact_score(item) for item in observed[:8]],
            "brand_claimed": [_compact_score(item) for item in claimed[:8]],
            "latent": [_compact_score(item) for item in latent[:8]],
            "unmet_group_need": [_compact_score(item) for item in unmet[:8]],
            "no_primary_reason_cn": no_primary_reason,
            "comment_summary": _comment_summary(score_payloads),
            "claim_param_summary": _claim_param_summary(score_payloads),
        }
        payload = {
            "profile_id": _profile_id(
                self.project_id,
                self.batch_id,
                self.taxonomy.taxonomy_version,
                sku_input.sku_code,
                self.rule_version,
            ),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "rule_version": self.rule_version,
            "sku_code": sku_input.sku_code,
            "model_name": sku_input.model_name,
            "brand_name": sku_input.brand_name,
            "size_tier": sku_input.size_tier,
            "price_band_in_size_tier": sku_input.price_band_in_size_tier,
            "price_percentile_in_size_tier": sku_input.price_percentile_in_size_tier,
            "primary_target_group_code": primary["target_group_code"]
            if primary
            else None,
            "primary_relation_status": primary["relation_status"] if primary else None,
            "secondary_target_group_codes_json": [
                item["target_group_code"] for item in secondary
            ],
            "comment_observed_group_codes_json": [
                item["target_group_code"] for item in observed
            ],
            "brand_claimed_group_codes_json": [
                item["target_group_code"] for item in claimed
            ],
            "latent_group_codes_json": [item["target_group_code"] for item in latent],
            "unmet_group_need_codes_json": [
                item["target_group_code"] for item in unmet
            ],
            "target_group_summary_json": _json_safe(summary),
            "review_required": bool(no_primary_reason)
            or any(item["review_required"] for item in score_payloads),
            "review_status": "review_required"
            if bool(no_primary_reason)
            or any(item["review_required"] for item in score_payloads)
            else "auto_pass",
            "review_reason_json": {"no_primary_reason_cn": no_primary_reason}
            if no_primary_reason
            else {},
            "confidence": _avg_decimal(
                [
                    item["confidence"]
                    for item in score_payloads
                    if item["relation_status"] != REL_NOT_SUPPORTED
                ]
            ),
            "evidence_ids_json": evidence_ids[:100],
            "is_current": True,
        }
        payload["profile_hash"] = stable_hash(
            {
                "sku_code": payload["sku_code"],
                "primary": payload["primary_target_group_code"],
                "secondary": payload["secondary_target_group_codes_json"],
                "comment_observed": payload["comment_observed_group_codes_json"],
                "brand_claimed": payload["brand_claimed_group_codes_json"],
                "latent": payload["latent_group_codes_json"],
                "unmet": payload["unmet_group_need_codes_json"],
                "summary": payload["target_group_summary_json"],
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M10C_PROFILE_HASH_VERSION,
        )
        return payload

    def _coverage_payloads(
        self, score_payloads: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for target_group in self.target_groups:
            rows = [
                item
                for item in score_payloads
                if item["target_group_code"] == target_group.target_group_code
                and item["relation_status"] != REL_NOT_SUPPORTED
            ]
            status_counts = Counter(item["relation_status"] for item in rows)
            top_skus = sorted(
                rows, key=lambda item: item["target_group_score"], reverse=True
            )[:30]
            payload = {
                "coverage_id": _coverage_id(
                    self.project_id,
                    self.batch_id,
                    self.taxonomy.taxonomy_version,
                    target_group.target_group_code,
                    self.rule_version,
                ),
                "project_id": self.project_id,
                "category_code": self.category_code,
                "batch_id": self.batch_id,
                "run_id": self.run_id,
                "module_run_id": self.module_run_id,
                "product_category": self.taxonomy.product_category,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
                "target_group_code": target_group.target_group_code,
                "target_group_name": target_group.target_group_name,
                "sku_count": len({item["sku_code"] for item in rows}),
                "relation_status_counts_json": dict(sorted(status_counts.items())),
                "primary_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_PRIMARY
                ],
                "secondary_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_SECONDARY
                ],
                "comment_observed_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_COMMENT_OBSERVED
                ],
                "brand_claimed_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_BRAND_CLAIMED
                ],
                "latent_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_LATENT
                ],
                "unmet_need_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_UNMET
                ],
                "top_skus_json": [_compact_score(item) for item in top_skus],
                "is_current": True,
            }
            payload["coverage_hash"] = stable_hash(
                {
                    "target_group_code": payload["target_group_code"],
                    "sku_count": payload["sku_count"],
                    "status_counts": payload["relation_status_counts_json"],
                    "top_skus": payload["top_skus_json"],
                    "taxonomy_version": self.taxonomy.taxonomy_version,
                    "rule_version": self.rule_version,
                },
                version=M10C_COVERAGE_HASH_VERSION,
            )
            payloads.append(payload)
        return payloads


def _tg(
    target_group_code: str,
    target_group_name: str,
    definition: str,
    source_task_codes: tuple[str, ...],
    comment_subdimension_codes: tuple[str, ...],
    comment_keywords: tuple[str, ...],
    allowed_size_tiers: tuple[str, ...],
    allowed_price_bands: tuple[str, ...],
    claim_codes: tuple[str, ...],
    param_codes: tuple[str, ...],
    *,
    adjacent_size_tiers: tuple[str, ...] = (),
    adjacent_price_bands: tuple[str, ...] = (),
) -> M10CTargetGroupDefinition:
    return M10CTargetGroupDefinition(
        target_group_code=target_group_code,
        target_group_name=target_group_name,
        definition=definition,
        source_task_codes=source_task_codes,
        comment_subdimension_codes=comment_subdimension_codes,
        comment_keywords=comment_keywords,
        allowed_size_tiers=allowed_size_tiers,
        allowed_price_bands=allowed_price_bands,
        claim_codes=claim_codes,
        param_codes=param_codes,
        adjacent_size_tiers=adjacent_size_tiers,
        adjacent_price_bands=adjacent_price_bands,
    )


def _filter_target_groups(
    taxonomy: M10CTargetGroupTaxonomy,
    target_group_codes: Sequence[str],
) -> tuple[M10CTargetGroupDefinition, ...]:
    if not target_group_codes:
        return taxonomy.target_groups
    code_set = {str(code) for code in target_group_codes}
    missing = sorted(code_set - set(taxonomy.target_groups_by_code))
    if missing:
        raise ValueError(f"M10C 未找到目标客群 code：{', '.join(missing)}")
    return tuple(
        item for item in taxonomy.target_groups if item.target_group_code in code_set
    )


def _build_sku_inputs(
    *,
    param_profiles: Sequence[entities.Core3SkuParamProfile],
    market_profiles: Mapping[str, entities.Core3SkuMarketProfile],
    market_weekly_rows: Sequence[entities.Core3CleanMarketWeekly],
    claim_profiles: Mapping[str, entities.Core3SkuClaimFactProfile],
    claim_facts: Mapping[str, Sequence[entities.Core3SkuClaimFact]],
    comment_profiles: Mapping[str, entities.Core3SkuCommentFactProfile],
    comment_facts: Mapping[str, Sequence[entities.Core3CommentFactAtom]],
    context_param_profiles: Sequence[entities.Core3SkuParamProfile] | None = None,
    context_market_profiles: Mapping[str, entities.Core3SkuMarketProfile] | None = None,
    context_market_weekly_rows: Sequence[entities.Core3CleanMarketWeekly] | None = None,
) -> list[M10CSkuInput]:
    base_inputs = [
        (profile, _canonical_size_tier(profile)) for profile in param_profiles
    ]
    context_base_inputs = [
        (profile, _canonical_size_tier(profile))
        for profile in (context_param_profiles or param_profiles)
    ]
    effective_market_profiles = context_market_profiles or market_profiles
    effective_weekly_rows = (
        context_market_weekly_rows
        if context_market_weekly_rows is not None
        else market_weekly_rows
    )
    price_bands = _derive_price_bands(context_base_inputs, effective_market_profiles)
    comparable_market_contexts = _derive_comparable_market_contexts(
        context_base_inputs, effective_weekly_rows
    )
    result: list[M10CSkuInput] = []
    for profile, size_tier in base_inputs:
        market_profile = market_profiles.get(profile.sku_code) or (
            context_market_profiles.get(profile.sku_code)
            if context_market_profiles
            else None
        )
        claim_profile = claim_profiles.get(profile.sku_code)
        price_band, percentile = price_bands.get(profile.sku_code, ("unknown", None))
        result.append(
            M10CSkuInput(
                sku_code=profile.sku_code,
                model_name=profile.model_name
                or (market_profile.model_name if market_profile else None),
                brand_name=(market_profile.brand_name if market_profile else None)
                or (claim_profile.brand_name if claim_profile else None),
                param_profile=profile,
                market_profile=market_profile,
                claim_profile=claim_profile,
                claim_facts=tuple(claim_facts.get(profile.sku_code, ())),
                comment_profile=comment_profiles.get(profile.sku_code),
                comment_facts=tuple(comment_facts.get(profile.sku_code, ())),
                size_tier=size_tier,
                price_band_in_size_tier=price_band,
                price_percentile_in_size_tier=percentile,
                comparable_market_context=comparable_market_contexts.get(
                    profile.sku_code
                ),
            )
        )
    return result


def _size_price_gate_status(
    sku_input: M10CSkuInput, target_group: M10CTargetGroupDefinition
) -> str:
    if (
        sku_input.size_tier == "unknown"
        or sku_input.price_band_in_size_tier == "unknown"
    ):
        return "unknown"
    size_ok = sku_input.size_tier in target_group.allowed_size_tiers
    price_ok = sku_input.price_band_in_size_tier in target_group.allowed_price_bands
    if size_ok and price_ok:
        return "matched"
    if (
        size_ok
        and sku_input.price_band_in_size_tier in target_group.adjacent_price_bands
    ) or (price_ok and sku_input.size_tier in target_group.adjacent_size_tiers):
        return "adjacent"
    return "mismatch"


def _size_price_fit_score(gate_status: str) -> Decimal:
    return {
        "matched": Decimal("1.0000"),
        "adjacent": Decimal("0.5500"),
        "unknown": Decimal("0.2500"),
    }.get(
        gate_status,
        Decimal("0.0000"),
    )


def _comment_match(
    comment_facts: Sequence[entities.Core3CommentFactAtom],
    target_group: M10CTargetGroupDefinition,
) -> dict[str, Any]:
    wanted = set(target_group.comment_subdimension_codes)
    rows = [
        row
        for row in comment_facts
        if not _is_service_comment(row)
        and (
            row.subdimension_code in wanted
            or _keyword_match(row.clean_comment_text, target_group.comment_keywords)
        )
    ]
    service_rows = [row for row in comment_facts if _is_service_comment(row)]
    direct_rows = [
        row
        for row in rows
        if row.dimension_type == "audience_signal"
        or row.subdimension_code.startswith("audience_")
    ]
    use_case_rows = [
        row
        for row in rows
        if row.dimension_type == "use_case_signal"
        or row.subdimension_code.startswith("use_")
    ]
    polarity_counts = Counter(row.polarity or "neutral" for row in rows)
    positive_count = int(polarity_counts.get("positive", 0))
    negative_count = int(polarity_counts.get("negative", 0))
    mixed_count = int(polarity_counts.get("mixed", 0))
    neutral_count = int(polarity_counts.get("neutral", 0))
    weighted = (
        Decimal(positive_count) * Decimal("1.00")
        + Decimal(mixed_count) * Decimal("0.75")
        + Decimal(neutral_count) * Decimal("0.55")
        + Decimal(negative_count) * Decimal("0.60")
    )
    denominator = Decimal("2.0") if direct_rows else Decimal("3.0")
    raw_score = weighted / denominator if rows else Decimal("0.0000")
    if direct_rows:
        raw_score = max(raw_score, Decimal("0.6500"))
    if len(direct_rows) >= 2:
        raw_score = max(raw_score, Decimal("0.8500"))
    if use_case_rows and not direct_rows:
        raw_score = max(raw_score, Decimal("0.4500"))
    if len(use_case_rows) >= 2 and not direct_rows:
        raw_score = max(raw_score, Decimal("0.6000"))
    if negative_count and negative_count >= positive_count:
        raw_score = min(max(raw_score, Decimal("0.4500")), Decimal("0.7000"))
    return {
        "score": _clamp_decimal(raw_score),
        "fact_count": len(rows),
        "direct_count": len(direct_rows),
        "use_case_count": len(use_case_rows),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "mixed_count": mixed_count,
        "neutral_count": neutral_count,
        "service_excluded_count": len(service_rows),
        "service_only": bool(service_rows) and not rows,
        "matched_subdimension_codes": sorted({row.subdimension_code for row in rows}),
        "supported_param_codes": sorted(
            {code for row in rows for code in _list_or_empty(row.supported_param_codes)}
        ),
        "contradicted_param_codes": sorted(
            {
                code
                for row in rows
                for code in _list_or_empty(row.contradicted_param_codes)
            }
        ),
        "supported_claim_codes": sorted(
            {code for row in rows for code in _list_or_empty(row.supported_claim_codes)}
        ),
        "contradicted_claim_codes": sorted(
            {
                code
                for row in rows
                for code in _list_or_empty(row.contradicted_claim_codes)
            }
        ),
        "sentiment_polarity": _sentiment_polarity(
            positive_count, negative_count, mixed_count, neutral_count
        ),
        "sample_comments": [row.clean_comment_text for row in rows[:5]],
        "evidence_ids": _unique(
            evidence_id
            for row in rows
            for evidence_id in _list_or_empty(row.evidence_ids)
        ),
    }


def _is_service_comment(row: entities.Core3CommentFactAtom) -> bool:
    return (
        row.dimension_type == "service_fulfillment_excluded"
        or row.subdimension_code in SERVICE_SUBDIMENSION_CODES
    )


def _keyword_match(text: str | None, keywords: Sequence[str]) -> bool:
    normalized = str(text or "").lower()
    return bool(normalized) and any(
        keyword.lower() in normalized for keyword in keywords
    )


def _claim_match(
    claim_facts: Sequence[entities.Core3SkuClaimFact],
    claim_profile: entities.Core3SkuClaimFactProfile | None,
    target_group: M10CTargetGroupDefinition,
) -> dict[str, Any]:
    wanted = set(target_group.claim_codes)
    rows = [
        row
        for row in claim_facts
        if row.claim_code in wanted and not row.service_separate_flag
    ]
    supported = [
        row
        for row in rows
        if row.fact_claim_flag
        and row.param_support_status
        in {"supported", "partially_supported", "not_param_applicable"}
    ]
    unsupported = [
        row for row in rows if row.param_support_status == "unsupported_by_param"
    ]
    profile_claim_codes = (
        set(_list_or_empty(claim_profile.fact_claim_codes if claim_profile else []))
        & wanted
    )
    supported_codes = {row.claim_code for row in supported} | profile_claim_codes
    claimed_codes = {row.claim_code for row in rows} | profile_claim_codes
    denominator = Decimal(max(1, min(4, len(wanted))))
    score = _clamp_decimal(
        (
            Decimal(len(supported_codes))
            + Decimal(max(0, len(claimed_codes - supported_codes))) * Decimal("0.35")
        )
        / denominator
    )
    return {
        "score": score,
        "matched_claim_codes": sorted(claimed_codes),
        "supported_claim_codes": sorted(supported_codes),
        "unsupported_claim_codes": sorted({row.claim_code for row in unsupported}),
        "service_excluded_claim_codes": sorted(
            {
                row.claim_code
                for row in claim_facts
                if row.claim_code in wanted and row.service_separate_flag
            }
        ),
        "evidence_ids": _unique(
            evidence_id
            for row in rows
            for evidence_id in _list_or_empty(row.evidence_ids)
        ),
    }


def _param_match(
    param_profile: entities.Core3SkuParamProfile,
    market_profile: entities.Core3SkuMarketProfile | None,
    target_group: M10CTargetGroupDefinition,
) -> dict[str, Any]:
    param_values = param_profile.param_values_json or {}
    supported: list[str] = []
    unknown: list[str] = []
    for param_code in target_group.param_codes:
        if param_code == "price_per_inch":
            if market_profile and _decimal(market_profile.price_per_inch) is not None:
                supported.append(param_code)
            else:
                unknown.append(param_code)
            continue
        entry = param_values.get(param_code)
        if entry is None:
            unknown.append(param_code)
        elif _param_entry_supported(param_code, entry):
            supported.append(param_code)
    denominator = Decimal(max(1, min(5, len(target_group.param_codes))))
    return {
        "score": _clamp_decimal(Decimal(len(supported)) / denominator),
        "supported_param_codes": sorted(set(supported)),
        "unknown_param_codes": sorted(set(unknown)),
    }


def _brand_trust_boost(
    comment_facts: Sequence[entities.Core3CommentFactAtom],
) -> Decimal:
    rows = [
        row
        for row in comment_facts
        if row.subdimension_code in BRAND_BOOST_CODES and not _is_service_comment(row)
    ]
    if not rows:
        return Decimal("0.0000")
    return min(Decimal("0.0500"), Decimal(len(rows)) * Decimal("0.0200"))


def _task_support_score(
    *,
    comment_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    size_price_fit_score: Decimal,
    direct_comment_count: int,
    use_case_count: int,
) -> Decimal:
    comment_direct = direct_comment_count > 0 or use_case_count > 0
    if (
        comment_direct
        and comment_score >= Decimal("0.6500")
        and (claim_score >= Decimal("0.3000") or param_score >= Decimal("0.3000"))
    ):
        return Decimal("0.8500")
    if comment_direct and comment_score >= Decimal("0.5500"):
        return Decimal("0.6500")
    if claim_score >= Decimal("0.5500") and param_score >= Decimal("0.4500"):
        return Decimal("0.4500")
    if size_price_fit_score >= Decimal("0.5500") and param_score >= Decimal("0.3500"):
        return Decimal("0.3000")
    if param_score >= Decimal("0.3000"):
        return Decimal("0.2000")
    return Decimal("0.0000")


def _initial_relation_status(
    *,
    size_price_gate_status: str,
    score: Decimal,
    comment_score: Decimal,
    task_support_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    positive_count: int,
    negative_count: int,
    service_only: bool,
) -> str:
    if service_only:
        return REL_NOT_SUPPORTED
    if (
        negative_count > 0
        and negative_count >= max(1, positive_count)
        and comment_score >= Decimal("0.4500")
    ):
        return REL_UNMET
    if size_price_gate_status == "mismatch" and comment_score < Decimal("0.6500"):
        return REL_NOT_SUPPORTED
    if (
        score >= Decimal("0.5800")
        and (
            comment_score >= Decimal("0.5500")
            or task_support_score >= Decimal("0.5500")
        )
        and size_price_gate_status in {"matched", "adjacent", "unknown"}
        and (claim_score >= Decimal("0.3000") or param_score >= Decimal("0.3000"))
    ):
        return REL_SECONDARY
    if comment_score >= Decimal("0.6500") and (
        claim_score < Decimal("0.3000") or param_score < Decimal("0.3000")
    ):
        return REL_COMMENT_OBSERVED
    if (
        claim_score >= Decimal("0.5500")
        and param_score >= Decimal("0.4500")
        and comment_score < Decimal("0.3500")
    ):
        return REL_BRAND_CLAIMED
    if (
        param_score >= Decimal("0.4500")
        and size_price_gate_status in {"matched", "adjacent"}
        and comment_score < Decimal("0.3500")
    ):
        return REL_LATENT
    if score >= Decimal("0.4200") and size_price_gate_status in {
        "matched",
        "adjacent",
        "unknown",
    }:
        return REL_LATENT
    return REL_NOT_SUPPORTED


def _status_reason_cn(
    target_group: M10CTargetGroupDefinition,
    *,
    relation_status: str,
    size_price_gate_status: str,
    comment_score: Decimal,
    task_support_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    comment_match: Mapping[str, Any],
) -> str:
    if relation_status == REL_NOT_SUPPORTED:
        return f"{target_group.target_group_name}未成立，主要原因是尺寸价格适配或真实用户/产品证据不足。"
    if relation_status == REL_UNMET:
        return f"{target_group.target_group_name}有用户需求，但负向评论集中或产品支撑不足，暂按未满足客群需求处理。"
    if relation_status == REL_COMMENT_OBSERVED:
        return f"{target_group.target_group_name}在评论中被观察到，但卖点或参数支撑不足，暂不作为主客群。"
    if relation_status == REL_BRAND_CLAIMED:
        return f"{target_group.target_group_name}有厂家卖点和参数支撑，但用户评论验证不足，暂按厂家主打客群处理。"
    if relation_status == REL_LATENT:
        return f"{target_group.target_group_name}有尺寸价格或参数适配，但用户评论和卖点证据不足，暂按潜在客群处理。"
    return (
        f"{target_group.target_group_name}可作为候选客群：尺寸价格 {size_price_gate_status}，"
        f"评论 {comment_score}，任务代理 {task_support_score}，卖点 {claim_score}，参数 {param_score}；"
        f"评论匹配 {comment_match.get('fact_count', 0)} 条。"
    )


def _review_reason(
    relation_status: str,
    size_price_gate_status: str,
    comment_match: Mapping[str, Any],
    claim_match: Mapping[str, Any],
    param_match: Mapping[str, Any],
    brand_trust_boost: Decimal,
) -> dict[str, Any]:
    reasons: list[str] = []
    if size_price_gate_status == "unknown":
        reasons.append("missing_size_or_price_band")
    if comment_match.get("service_excluded_count"):
        reasons.append("service_signal_excluded")
    if relation_status == REL_UNMET:
        reasons.append("negative_comment_unmet_need")
    if relation_status == REL_COMMENT_OBSERVED:
        reasons.append("comment_strong_claim_param_weak")
    if relation_status == REL_BRAND_CLAIMED and param_match.get("unknown_param_codes"):
        reasons.append("brand_claim_param_weak")
    if claim_match.get("unsupported_claim_codes"):
        reasons.append("unsupported_claim_codes_present")
    if param_match.get("unknown_param_codes"):
        reasons.append("unknown_param_codes_present")
    if (
        brand_trust_boost > Decimal("0.0000")
        and not comment_match.get("fact_count")
        and relation_status == REL_NOT_SUPPORTED
    ):
        reasons.append("brand_power_only_not_enough")
    return {
        "reason_codes": reasons,
        "comment_match": {
            key: value
            for key, value in comment_match.items()
            if key != "sample_comments"
        },
        "unsupported_claim_codes": claim_match.get("unsupported_claim_codes") or [],
        "unknown_param_codes": param_match.get("unknown_param_codes") or [],
    }


def _confidence(
    size_price_fit_score: Decimal,
    comment_score: Decimal,
    task_support_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    sku_input: M10CSkuInput,
) -> Decimal:
    domain_count = 0
    if size_price_fit_score >= Decimal("0.5500"):
        domain_count += 1
    if comment_score > Decimal("0.0000"):
        domain_count += 1
    if task_support_score > Decimal("0.0000"):
        domain_count += 1
    if claim_score > Decimal("0.0000"):
        domain_count += 1
    if param_score > Decimal("0.0000"):
        domain_count += 1
    if sku_input.market_profile is not None:
        domain_count += 1
    return _clamp_decimal(Decimal(domain_count) / Decimal("6"))


def _compact_score(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        "sku_code": payload.get("sku_code"),
        "target_group_code": payload.get("target_group_code"),
        "target_group_name": payload.get("target_group_name"),
        "relation_status": payload.get("relation_status"),
        "target_group_score": _decimal_to_float(payload.get("target_group_score")),
        "status_reason_cn": payload.get("status_reason_cn"),
    }


def _comment_summary(score_payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    active = [
        item
        for item in score_payloads
        if item["comment_audience_motivation_score"] > Decimal("0.0000")
    ]
    return {
        "matched_target_group_count": len(active),
        "top_comment_observed": [
            _compact_score(item)
            for item in sorted(
                active,
                key=lambda item: item["comment_audience_motivation_score"],
                reverse=True,
            )[:5]
        ],
    }


def _claim_param_summary(score_payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "claim_strong_target_group_codes": [
            item["target_group_code"]
            for item in score_payloads
            if item["claim_alignment_score"] >= Decimal("0.5500")
        ],
        "param_strong_target_group_codes": [
            item["target_group_code"]
            for item in score_payloads
            if item["param_capability_score"] >= Decimal("0.5500")
        ],
    }


def _no_primary_reason(
    score_payloads: Sequence[Mapping[str, Any]],
    sku_input: M10CSkuInput,
    product_category: str,
) -> str:
    if (
        sku_input.size_tier == "unknown"
        or sku_input.price_band_in_size_tier == "unknown"
    ):
        return missing_size_price_reason_for_product_category(
            product_category, "M10C", "目标客群"
        )
    active = [
        item for item in score_payloads if item["relation_status"] != REL_NOT_SUPPORTED
    ]
    if not active:
        return "没有客群同时满足真实用户声音、任务代理、尺寸价格和产品支撑。"
    return "有评论观察、厂家表达或潜在适配，但尚未形成用户声音、卖点和参数共同支撑的主目标客群。"


def _profile_id(
    project_id: str,
    batch_id: str,
    taxonomy_version: str,
    sku_code: str,
    rule_version: str,
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "sku_code": sku_code,
            "rule_version": rule_version,
        },
        version=M10C_PROFILE_ID_HASH_VERSION,
    )[:120]


def _score_id(
    project_id: str,
    batch_id: str,
    taxonomy_version: str,
    sku_code: str,
    target_group_code: str,
    rule_version: str,
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "sku_code": sku_code,
            "target_group_code": target_group_code,
            "rule_version": rule_version,
        },
        version=M10C_SCORE_ID_HASH_VERSION,
    )[:120]


def _coverage_id(
    project_id: str,
    batch_id: str,
    taxonomy_version: str,
    target_group_code: str,
    rule_version: str,
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "target_group_code": target_group_code,
            "rule_version": rule_version,
        },
        version=M10C_COVERAGE_ID_HASH_VERSION,
    )[:120]


def _score_result_hash(
    payload: Mapping[str, Any], taxonomy_version: str, rule_version: str
) -> str:
    return stable_hash(
        {
            "sku_code": payload["sku_code"],
            "target_group_code": payload["target_group_code"],
            "relation_status": payload["relation_status"],
            "target_group_score": payload["target_group_score"],
            "score_breakdown_json": payload["score_breakdown_json"],
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
        },
        version=M10C_SCORE_HASH_VERSION,
    )


def _blocked_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str | None,
    run_id: str | None,
    message_cn: str,
    started_at: datetime,
    finished_at: datetime,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M10C,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=[message_cn],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "blocked_reason": message_cn,
        },
        started_at=started_at,
        finished_at=finished_at,
    )


def _failed_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    started_at: datetime,
    error_code: str,
    message_cn: str,
    error_message: str,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M10C,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=[message_cn, error_message],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error_code": error_code,
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
