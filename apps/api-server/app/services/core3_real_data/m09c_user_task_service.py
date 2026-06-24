"""M09C user task profiles.

M09C is deterministic. It consumes M03B parameter facts, M04C claim facts,
M05C comment facts, and M07 market facts. It does not call an LLM and does not
reuse old M09 task outputs as input.
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
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_MODULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.m11c_value_battlefield_service import (
    AC_CANONICAL_SIZE_TIERS,
    CANONICAL_SIZE_TIERS,
    M11CInputReader,
    PRICE_BANDS,
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


M09C_PROFILE_ID_HASH_VERSION = "m09c-user-task-profile-id-v1"
M09C_PROFILE_HASH_VERSION = "m09c-user-task-profile-v1"
M09C_SCORE_ID_HASH_VERSION = "m09c-user-task-score-id-v1"
M09C_SCORE_HASH_VERSION = "m09c-user-task-score-v1"
M09C_COVERAGE_ID_HASH_VERSION = "m09c-user-task-coverage-id-v1"
M09C_COVERAGE_HASH_VERSION = "m09c-user-task-coverage-v1"

REL_PRIMARY = "primary_user_task"
REL_SECONDARY = "secondary_user_task"
REL_COMMENT_OBSERVED = "comment_observed_task"
REL_BRAND_CLAIMED = "brand_claimed_task"
REL_LATENT = "latent_capability_task"
REL_DRAG = "drag_factor_task"
REL_NOT_SUPPORTED = "not_supported"

SERVICE_SUBDIMENSION_CODES = (
    "service_delivery_install",
    "service_fulfillment_excluded",
)


@dataclass(frozen=True)
class M09CUserTaskDefinition:
    user_task_code: str
    user_task_name: str
    definition: str
    comment_subdimension_codes: tuple[str, ...]
    comment_keywords: tuple[str, ...]
    allowed_size_tiers: tuple[str, ...]
    allowed_price_bands: tuple[str, ...]
    claim_codes: tuple[str, ...]
    param_codes: tuple[str, ...]
    adjacent_size_tiers: tuple[str, ...] = ()
    adjacent_price_bands: tuple[str, ...] = ()


@dataclass(frozen=True)
class M09CUserTaskTaxonomy:
    taxonomy_version: str
    product_category: str
    product_category_label_cn: str
    sku_code_prefix: str
    user_tasks: tuple[M09CUserTaskDefinition, ...]

    @property
    def user_tasks_by_code(self) -> dict[str, M09CUserTaskDefinition]:
        return {item.user_task_code: item for item in self.user_tasks}


@dataclass(frozen=True)
class M09CSkuInput:
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
class M09CWritePayload:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M09CServiceResult:
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


def tv_user_task_taxonomy_v0_1() -> M09CUserTaskTaxonomy:
    """Published TV M09C user-task taxonomy confirmed in the business thread."""

    return M09CUserTaskTaxonomy(
        taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
        product_category="TV",
        product_category_label_cn="彩电",
        sku_code_prefix="TV",
        user_tasks=(
            _task(
                "TASK_MAINSTREAM_LIVING_VIEWING",
                "主流客厅日常观影",
                "家庭日常看电视、追剧、综艺，要求尺寸合适、画质够用、系统稳定。",
                (
                    "use_living_room_cinema",
                    "audience_child_family",
                    "picture_clarity_resolution",
                    "system_smooth_ads",
                    "audio_quality",
                ),
                ("客厅", "家庭", "全家", "追剧", "综艺", "日常看", "看电视"),
                ("medium_46_59", "large_60_69", "xlarge_70_85"),
                ("low", "mid_low", "mid", "mid_high"),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_speaker_sound",
                    "tv_claim_eye_care_display",
                    "tv_claim_voice_control",
                    "tv_claim_value_price",
                ),
                (
                    "screen_size_inch",
                    "resolution_class",
                    "hdr_support_flag",
                    "memory_capacity_gb",
                    "speaker_power_w",
                    "smart_tv_flag",
                ),
                adjacent_size_tiers=("small_32_45",),
                adjacent_price_bands=("high",),
            ),
            _task(
                "TASK_CINEMA_IMMERSION",
                "影院沉浸观影",
                "在客厅或大空间看电影、大片、剧集，追求大屏、HDR、音效、沉浸感。",
                (
                    "use_living_room_cinema",
                    "audio_quality",
                    "picture_brightness_hdr",
                    "picture_local_dimming_black",
                    "appearance_size_fit",
                ),
                ("电影", "影院", "大片", "沉浸", "震撼", "大屏", "音效"),
                ("large_60_69", "xlarge_70_85", "giant_98_plus"),
                ("mid", "mid_high", "high"),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_dolby_audio_video",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_local_dimming",
                    "tv_claim_speaker_sound",
                    "tv_claim_miniled_display",
                ),
                (
                    "screen_size_inch",
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                    "speaker_power_w",
                    "display_tech_class",
                    "local_dimming_zone_count",
                ),
                adjacent_size_tiers=("medium_46_59",),
                adjacent_price_bands=("mid_low",),
            ),
            _task(
                "TASK_PREMIUM_PICTURE_EXPERIENCE",
                "高端画质体验",
                "重点追求亮度、控光、色彩、MiniLED/OLED/QD、画质芯片。",
                (
                    "picture_clarity_resolution",
                    "picture_brightness_hdr",
                    "picture_color_accuracy",
                    "picture_local_dimming_black",
                ),
                (
                    "画质",
                    "亮度",
                    "控光",
                    "色彩",
                    "黑位",
                    "miniled",
                    "oled",
                    "量子点",
                    "画质芯片",
                ),
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
                ),
                (
                    "display_tech_class",
                    "declared_brightness_nit_or_band",
                    "local_dimming_zone_count",
                    "color_gamut_percent",
                    "picture_engine_chip",
                    "hdr_support_flag",
                ),
                adjacent_size_tiers=("giant_98_plus",),
                adjacent_price_bands=("mid",),
            ),
            _task(
                "TASK_LARGE_SCREEN_UPGRADE",
                "大屏换新升级",
                "从小屏或旧电视升级到 70/75/85/98 寸以上，核心是屏幕变大和换新价值。",
                (
                    "replacement_source",
                    "appearance_size_fit",
                    "use_living_room_cinema",
                    "value_price",
                ),
                (
                    "换新",
                    "换电视",
                    "旧电视",
                    "升级",
                    "大屏",
                    "75",
                    "85",
                    "98",
                    "尺寸大",
                ),
                ("xlarge_70_85", "giant_98_plus"),
                ("low", "mid_low", "mid", "mid_high"),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_value_price",
                    "tv_claim_full_screen_design",
                    "tv_claim_hdr_high_brightness",
                ),
                (
                    "screen_size_inch",
                    "resolution_class",
                    "price_per_inch",
                    "full_screen_design_flag",
                ),
                adjacent_size_tiers=("large_60_69",),
                adjacent_price_bands=("high",),
            ),
            _task(
                "TASK_GAMING_CONSOLE_ENTERTAINMENT",
                "主机游戏娱乐",
                "连接游戏主机或高帧娱乐，关注高刷、HDMI2.1、VRR、低延迟。",
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
                    "switch",
                    "高刷",
                    "低延迟",
                    "hdmi2.1",
                    "vrr",
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
                    "vrr_allm_flag",
                    "memc_motion_flag",
                    "memory_capacity_gb",
                ),
                adjacent_price_bands=("mid_low",),
            ),
            _task(
                "TASK_SPORTS_MOTION_WATCHING",
                "体育赛事观看",
                "看球赛、运动、赛车等高速画面，关注流畅、拖影、运动补偿。",
                (
                    "use_gaming_sports",
                    "gaming_high_refresh_motion",
                    "picture_clarity_resolution",
                ),
                (
                    "体育",
                    "赛事",
                    "看球",
                    "足球",
                    "篮球",
                    "运动",
                    "赛车",
                    "流畅",
                    "拖影",
                ),
                ("medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus"),
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "tv_claim_high_refresh_rate",
                    "tv_claim_gaming_low_latency",
                    "tv_claim_hdr_high_brightness",
                ),
                (
                    "declared_refresh_rate_hz",
                    "memc_motion_flag",
                    "vrr_allm_flag",
                    "declared_brightness_nit_or_band",
                ),
            ),
            _task(
                "TASK_EYE_CARE_LONG_WATCHING",
                "长时间护眼观看",
                "儿童、家庭、长时间观看场景，关注护眼、低蓝光、无频闪、舒适度。",
                (
                    "audience_child_family",
                    "picture_eye_care_reflection",
                    "use_living_room_cinema",
                ),
                (
                    "孩子",
                    "儿童",
                    "护眼",
                    "低蓝光",
                    "无频闪",
                    "不刺眼",
                    "长时间",
                    "眼睛",
                    "舒服",
                ),
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
                    "declared_refresh_rate_hz",
                    "hdr_support_flag",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("low",),
            ),
            _task(
                "TASK_SENIOR_EASY_OPERATION",
                "长辈易用操作",
                "给父母或老人使用，关注语音、遥控简单、系统清爽、少广告。",
                (
                    "audience_senior",
                    "interaction_voice_casting",
                    "system_smooth_ads",
                    "use_living_room_cinema",
                ),
                (
                    "老人",
                    "父母",
                    "爸妈",
                    "长辈",
                    "语音",
                    "遥控",
                    "广告少",
                    "操作简单",
                    "系统清爽",
                ),
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
            _task(
                "TASK_BEDROOM_SECOND_SCREEN",
                "卧室/副屏小空间",
                "卧室、租房、第二台电视，小尺寸、低价、易用、够用。",
                (
                    "audience_rental_room",
                    "use_bedroom",
                    "value_price",
                    "appearance_size_fit",
                ),
                ("卧室", "租房", "宿舍", "第二台", "副屏", "小房间", "小尺寸", "够用"),
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
                    "price_per_inch",
                    "voice_recognition_flag",
                ),
                adjacent_size_tiers=("medium_46_59",),
                adjacent_price_bands=("mid",),
            ),
            _task(
                "TASK_SMART_CASTING_IOT",
                "投屏互联与智能控制",
                "手机投屏、无线连接、AI 语音、家电联动、摄像头互动等智能场景。",
                (
                    "use_casting_online",
                    "interaction_voice_casting",
                    "system_smooth_ads",
                    "audience_senior",
                ),
                (
                    "投屏",
                    "连接",
                    "联网",
                    "语音",
                    "ai",
                    "智能",
                    "家电联动",
                    "摄像头",
                    "手机",
                ),
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
                ),
                adjacent_size_tiers=("small_32_45",),
                adjacent_price_bands=("mid_low",),
            ),
            _task(
                "TASK_HOME_DECOR_SPACE_FIT",
                "新家装修与空间融合",
                "新家、客厅布置、贴墙、超薄、全面屏、外观和空间适配。",
                (
                    "appearance_slim_wall",
                    "appearance_size_fit",
                    "use_living_room_cinema",
                ),
                ("新家", "装修", "客厅布置", "贴墙", "超薄", "全面屏", "外观", "空间"),
                CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "tv_claim_full_screen_design",
                    "tv_claim_flush_wall_mount",
                    "tv_claim_ultra_thin_design",
                    "tv_claim_theater_scene",
                ),
                (
                    "full_screen_design_flag",
                    "flush_wall_mount_flag",
                    "ultra_thin_flag",
                    "screen_size_inch",
                ),
                adjacent_price_bands=("low",),
            ),
            _task(
                "TASK_VALUE_FOR_MONEY_PURCHASE",
                "预算内高性价比购买",
                "在预算内追求更大尺寸、更好配置、更高销量口碑或补贴价格。",
                ("value_price", "replacement_source", "use_living_room_cinema"),
                ("性价比", "划算", "便宜", "优惠", "补贴", "价格合适", "值", "预算"),
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
        ),
    )


def ac_user_task_taxonomy_v0_1() -> M09CUserTaskTaxonomy:
    """Published AC M09C user-task taxonomy derived from AC fact profiles."""

    return M09CUserTaskTaxonomy(
        taxonomy_version=CORE3_M09C_AC_TAXONOMY_VERSION,
        product_category="AC",
        product_category_label_cn="空调",
        sku_code_prefix="AC",
        user_tasks=(
            _task(
                "TASK_FAST_COOL_HEAT",
                "快速制冷制热",
                "用户希望空调快速达到冷暖效果，夏季制冷、冬季制热都有明确体验反馈。",
                (
                    "cooling_effect",
                    "heating_effect",
                    "fast_cooling_heating",
                    "use_summer_winter",
                ),
                ("制冷", "制热", "速冷", "速热", "冷暖", "降温", "升温"),
                AC_CANONICAL_SIZE_TIERS,
                PRICE_BANDS,
                (
                    "ac_claim_fast_cooling_heating",
                    "ac_claim_wide_temperature_operation",
                    "ac_claim_precision_temperature_control",
                ),
                (
                    "cooling_capacity_w",
                    "heating_capacity_w",
                    "heat_cool_mode",
                    "heating_function_flag",
                ),
            ),
            _task(
                "TASK_STABLE_TEMPERATURE",
                "稳定控温",
                "用户关注温度稳定、恒温、体感不忽冷忽热和控温准确。",
                ("temperature_stability", "cooling_effect", "heating_effect"),
                ("恒温", "控温", "温度稳定", "忽冷忽热", "精准"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                (
                    "ac_claim_precision_temperature_control",
                    "ac_claim_wide_temperature_operation",
                ),
                (
                    "energy_efficiency_ratio",
                    "smart_sensing_flag",
                    "cooling_capacity_w",
                    "heating_capacity_w",
                ),
                adjacent_price_bands=("low",),
            ),
            _task(
                "TASK_SLEEP_QUIET",
                "睡眠静音",
                "卧室和夜间睡眠使用，要求噪音低、睡眠模式舒适，噪音反证进入拖后腿。",
                ("quiet_positive", "sleep_scene", "noise_risk", "use_bedroom_sleep"),
                ("静音", "睡眠", "晚上", "卧室", "噪音", "安静"),
                ("wall_hp_1_or_below", "wall_hp_1_5", "wall_hp_2"),
                ("mid_low", "mid", "mid_high", "high"),
                ("ac_claim_quiet_sleep", "ac_claim_soft_wind_no_direct"),
                ("installation_type", "comfort_airflow_flag", "smart_sensing_flag"),
                adjacent_size_tiers=("floor_hp_2",),
                adjacent_price_bands=("low",),
            ),
            _task(
                "TASK_ENERGY_SAVING_LONG_USE",
                "长时使用省电",
                "用户关注长时间开机后的电费、能效等级、APF 和省电体验。",
                (
                    "energy_saving_usage",
                    "energy_grade_apf",
                    "electricity_cost",
                    "energy_saving_negative",
                ),
                ("省电", "电费", "能效", "一级", "APF", "耗电"),
                AC_CANONICAL_SIZE_TIERS,
                PRICE_BANDS,
                (
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_ai_energy_saving",
                    "ac_claim_price_value_subsidy",
                ),
                ("energy_grade_normalized", "energy_efficiency_ratio", "inverter_flag"),
            ),
            _task(
                "TASK_SOFT_WIND_NO_DIRECT",
                "柔风防直吹",
                "用户关注风感柔和、不直吹、扫风均匀和舒适送风。",
                ("soft_wind_no_direct", "airflow_even_swing", "airflow_negative"),
                ("柔风", "不直吹", "直吹", "扫风", "风感", "舒服"),
                (
                    "wall_hp_1_or_below",
                    "wall_hp_1_5",
                    "wall_hp_2",
                    "floor_hp_2",
                    "floor_hp_3",
                ),
                ("mid", "mid_high", "high"),
                ("ac_claim_soft_wind_no_direct", "ac_claim_large_airflow_coverage"),
                ("comfort_airflow_flag", "airflow_volume_m3h", "smart_sensing_flag"),
                adjacent_price_bands=("mid_low",),
            ),
            _task(
                "TASK_LARGE_SPACE_COVERAGE",
                "大空间覆盖",
                "客厅、大卧室或门店等大空间使用，关注匹数、风量、覆盖速度和柜机能力。",
                (
                    "use_living_room_large",
                    "airflow_volume_coverage",
                    "space_fit_area",
                    "cooling_effect",
                    "fast_cooling_heating",
                ),
                ("客厅", "大空间", "大风量", "覆盖", "柜机", "风量"),
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
            _task(
                "TASK_HEALTH_CLEAN_AIR",
                "健康洁净空气",
                "用户关注自清洁、除菌净化、新风、异味霉味等空气健康体验。",
                (
                    "self_cleaning",
                    "purification_antibacterial",
                    "fresh_air_ventilation",
                    "odor_mold_risk",
                ),
                ("自清洁", "自洁", "除菌", "净化", "新风", "异味", "霉味"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid", "mid_high", "high"),
                (
                    "ac_claim_self_cleaning",
                    "ac_claim_purification_antibacterial",
                    "ac_claim_fresh_air",
                ),
                ("self_cleaning_flag", "purification_flag", "fresh_air_flag"),
                adjacent_price_bands=("mid_low",),
            ),
            _task(
                "TASK_DEHUMIDIFY_HUMID_CLIMATE",
                "潮湿除湿",
                "南方潮湿、梅雨季或湿度控制场景，关注除湿和温湿双控。",
                (
                    "dehumidification",
                    "humid_weather",
                    "use_humid_south",
                    "odor_mold_risk",
                ),
                ("除湿", "潮湿", "南方", "梅雨", "湿度", "干爽"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                ("ac_claim_humidity_dehumidification", "ac_claim_self_cleaning"),
                ("self_cleaning_flag", "purification_flag"),
                adjacent_price_bands=("low",),
            ),
            _task(
                "TASK_SMART_REMOTE_CONTROL",
                "智能远程控制",
                "用户关注 APP 远程、WiFi、语音、IoT 和遥控面板易用。",
                (
                    "smart_app_remote",
                    "remote_panel_easy_use",
                    "voice_iot",
                    "smart_negative",
                ),
                ("APP", "远程", "WiFi", "语音", "智能", "遥控", "联网"),
                AC_CANONICAL_SIZE_TIERS,
                ("mid", "mid_high", "high"),
                ("ac_claim_smart_app_voice_iot",),
                ("wifi_control_flag", "voice_control_flag", "smart_sensing_flag"),
                adjacent_price_bands=("mid_low",),
            ),
            _task(
                "TASK_INSTALL_SPACE_FIT",
                "安装空间适配",
                "安装方式、内机尺寸、外观颜值和面积适配；配送安装服务评价不进入任务成立证据。",
                (
                    "appearance_design",
                    "space_fit_area",
                    "installation_form",
                    "installation_constraint",
                ),
                ("安装", "空间", "面积", "外观", "颜值", "柜机", "挂机", "尺寸"),
                AC_CANONICAL_SIZE_TIERS,
                PRICE_BANDS,
                ("ac_claim_installation_space_design", "ac_claim_price_value_subsidy"),
                (
                    "installation_type",
                    "indoor_unit_dimensions_mm",
                    "installation_hp_segment",
                ),
            ),
            _task(
                "TASK_VALUE_SUBSIDY_PURCHASE",
                "价格补贴划算购买",
                "用户关注价格、补贴、性价比、同价位价值和旧机换新。",
                (
                    "value_positive",
                    "subsidy_promotion",
                    "same_price_value",
                    "price_negative",
                    "replacement_source",
                ),
                ("性价比", "划算", "补贴", "优惠", "价格", "同价位", "换新"),
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
            _task(
                "TASK_RELIABLE_LONG_TERM_USE",
                "长期可靠使用",
                "用户关注品牌信任、复购推荐、耐用品质、核心部件和故障风险。",
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


class M09CUserTaskTaxonomyLoader:
    def load(
        self, taxonomy_version: str, *, product_category: str
    ) -> M09CUserTaskTaxonomy:
        normalized_category = str(product_category or "").upper()
        if (
            normalized_category == "TV"
            and taxonomy_version == CORE3_M09C_TV_TAXONOMY_VERSION
        ):
            return tv_user_task_taxonomy_v0_1()
        if (
            normalized_category == "AC"
            and taxonomy_version == CORE3_M09C_AC_TAXONOMY_VERSION
        ):
            return ac_user_task_taxonomy_v0_1()
        raise ValueError(
            f"{normalized_category or product_category} 用户任务 taxonomy 未发布，不能生成 M09C 用户任务画像。"
        )


class M09CUserTaskRepository(ParamExtractionRepository):
    def save_profiles(
        self, profiles: Sequence[Any], *, replace_on_hash_conflict: bool = False
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3M09cSkuUserTaskProfile,
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
            entities.Core3M09cSkuUserTaskScore,
            scores,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "sku_code",
                "user_task_code",
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
            entities.Core3M09cUserTaskCoverage,
            coverages,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "user_task_code",
                "rule_version",
                "is_current",
            ),
            hash_field="coverage_hash",
            replace_existing=replace_on_hash_conflict,
        )


class M09CInputReader(M11CInputReader):
    """M09C consumes the same fact-layer tables and versions as M10C/M11C."""


class M09CRunner:
    module_code = Core3ModuleCode.M09C

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
                message_cn="M09C 缺少 M00 batch_id，无法生成用户任务画像。",
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
                or CORE3_M09C_TV_TAXONOMY_VERSION
            ),
            rule_version=str(
                target.metadata.get("rule_version") or CORE3_M09C_TV_RULE_VERSION
            ),
            target_sku_codes=target.target_ids,
            user_task_codes=target.metadata.get("user_task_codes") or (),
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
        taxonomy_version: str = CORE3_M09C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M09C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        user_task_codes: Sequence[str] = (),
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
                service_result = M09CService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    taxonomy_version=taxonomy_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    user_task_codes=user_task_codes,
                    force_rebuild=force_rebuild,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m09c_user_task_hash_conflict",
                message_cn="M09C 用户任务画像结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m09c_user_task_failed",
                message_cn="M09C 用户任务画像生成失败，请检查 M03B/M04C/M05C/M07 事实层是否已生成。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M09C_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
            "product_category": product_category,
            "target_sku_codes": list(target_sku_codes),
            "user_task_codes": list(user_task_codes),
            **service_result.summary,
        }
        status = (
            Core3RunStatus.WARNING
            if service_result.warnings
            else Core3RunStatus.SUCCESS
        )
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M09C,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.profile_count
            + service_result.score_count
            + service_result.coverage_count,
            output_hash=stable_hash(summary_json, version="m09c_user_task_summary_v1"),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {"module_code": "M10C", "reason": "用户任务变化会影响目标客群推导。"},
                {
                    "module_code": "M11C",
                    "reason": "用户任务变化会影响价值战场解释和后续竞品库。",
                },
                {
                    "module_code": "M12",
                    "reason": "用户任务变化会影响竞品召回和候选池解释。",
                },
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M09CService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M09C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M09C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        user_task_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> M09CServiceResult:
        taxonomy = M09CUserTaskTaxonomyLoader().load(
            taxonomy_version, product_category=product_category
        )
        selected_tasks = _filter_user_tasks(taxonomy, user_task_codes)
        fact_versions = fact_rule_versions_for_product_category(
            taxonomy.product_category
        )
        reader = M09CInputReader(self.context)
        param_profiles = reader.list_param_profiles(
            batch_id,
            sku_code_prefix=taxonomy.sku_code_prefix,
            param_rule_version=fact_versions["param_rule_version"],
            target_sku_codes=target_sku_codes,
        )
        sku_codes = [profile.sku_code for profile in param_profiles]
        market_profiles = _by_sku(reader.list_market_profiles(batch_id, sku_codes))
        market_weekly_rows = reader.list_clean_market_weekly(batch_id, sku_codes)
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
        )
        profiles, scores, coverages, summary = M09CProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            user_tasks=selected_tasks,
            rule_version=rule_version,
        ).build(sku_inputs)

        repository = M09CUserTaskRepository(self.context)
        write_results = {
            "user_task_profiles": repository.save_profiles(
                profiles, replace_on_hash_conflict=force_rebuild
            ),
            "user_task_scores": repository.save_scores(
                scores, replace_on_hash_conflict=force_rebuild
            ),
            "user_task_coverages": repository.save_coverages(
                coverages, replace_on_hash_conflict=force_rebuild
            ),
        }
        warnings: list[str] = []
        if not sku_inputs:
            warnings.append(
                "M09C 没有读取到 M03B 参数画像，无法生成 SKU 用户任务画像。"
            )
        if sku_inputs and not any(item.market_profile for item in sku_inputs):
            warnings.append(
                "M09C 没有读取到 M07 full_observed_window 市场画像，价格带和市场验证降级。"
            )
        if sku_inputs and not any(
            item.comparable_market_context for item in sku_inputs
        ):
            warnings.append(
                "M09C 没有读取到 M01 周度量价事实，市场验证降级为 M07 累计窗口兼容口径。"
            )
        if sku_inputs and not any(item.comment_profile for item in sku_inputs):
            warnings.append("M09C 没有读取到 M05C 评论事实画像，真实用户任务证据降级。")
        return M09CServiceResult(
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


class M09CProfileBuilder:
    def __init__(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        taxonomy: M09CUserTaskTaxonomy,
        user_tasks: tuple[M09CUserTaskDefinition, ...],
        rule_version: str,
    ) -> None:
        self.project_id = project_id
        self.category_code = category_code
        self.batch_id = batch_id
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.taxonomy = taxonomy
        self.user_tasks = user_tasks
        self.rule_version = rule_version

    def build(
        self,
        sku_inputs: Sequence[M09CSkuInput],
    ) -> tuple[
        list[M09CWritePayload],
        list[M09CWritePayload],
        list[M09CWritePayload],
        dict[str, Any],
    ]:
        profiles: list[M09CWritePayload] = []
        scores: list[M09CWritePayload] = []
        status_counts: Counter[str] = Counter()
        primary_counts: Counter[str] = Counter()
        size_price_counts: Counter[str] = Counter()

        for sku_input in sku_inputs:
            sku_scores = [
                self._score_user_task(sku_input, user_task)
                for user_task in self.user_tasks
            ]
            sku_scores = self._assign_primary_secondary(sku_scores)
            scores.extend(M09CWritePayload(payload) for payload in sku_scores)
            profiles.append(
                M09CWritePayload(self._profile_payload(sku_input, sku_scores))
            )
            for payload in sku_scores:
                status_counts[payload["relation_status"]] += 1
                if payload["relation_status"] == REL_PRIMARY:
                    primary_counts[payload["user_task_code"]] += 1
            size_price_counts[
                f"{sku_input.size_tier}:{sku_input.price_band_in_size_tier}"
            ] += 1

        score_payloads = [score.payload for score in scores]
        coverages = [
            M09CWritePayload(payload)
            for payload in self._coverage_payloads(score_payloads)
        ]
        summary = {
            "sku_count": len(sku_inputs),
            "profile_count": len(profiles),
            "score_count": len(scores),
            "coverage_count": len(coverages),
            "user_task_count": len(self.user_tasks),
            "relation_status_counts": dict(sorted(status_counts.items())),
            "primary_user_task_counts": dict(sorted(primary_counts.items())),
            "size_price_counts": dict(sorted(size_price_counts.items())),
            "taxonomy_codes": [
                user_task.user_task_code for user_task in self.user_tasks
            ],
            "size_tier_policy": size_tier_policy_for_product_category(
                self.taxonomy.product_category, "M09C"
            ),
            "price_band_policy": price_band_policy_for_product_category(
                self.taxonomy.product_category, "M09C"
            ),
            "market_validation_policy": market_validation_policy_for_product_category(
                self.taxonomy.product_category
            ),
        }
        return profiles, scores, coverages, summary

    def _score_user_task(
        self, sku_input: M09CSkuInput, user_task: M09CUserTaskDefinition
    ) -> dict[str, Any]:
        size_price_gate_status = _size_price_gate_status(sku_input, user_task)
        size_price_fit_score = _size_price_fit_score(size_price_gate_status)
        comment_match = _comment_match(sku_input.comment_facts, user_task)
        claim_match = _claim_match(
            sku_input.claim_facts, sku_input.claim_profile, user_task
        )
        param_match = _param_match(
            sku_input.param_profile, sku_input.market_profile, user_task
        )
        comment_score = comment_match["score"]
        claim_score = claim_match["score"]
        param_score = param_match["score"]
        market_validation_score = _market_validation_score(
            sku_input.market_profile, sku_input.comparable_market_context
        )
        negative_drag_score = _negative_drag_score(
            comment_match, claim_match, param_match
        )
        user_task_score = _clamp_decimal(
            comment_score * Decimal("0.40")
            + claim_score * Decimal("0.20")
            + param_score * Decimal("0.18")
            + size_price_fit_score * Decimal("0.10")
            + market_validation_score * Decimal("0.07")
            - negative_drag_score * Decimal("0.05")
        )
        relation_status = _initial_relation_status(
            size_price_gate_status=size_price_gate_status,
            score=user_task_score,
            comment_score=comment_score,
            claim_score=claim_score,
            param_score=param_score,
            negative_drag_score=negative_drag_score,
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
            negative_drag_score,
        )
        review_required = bool(review_reason["reason_codes"])
        payload = {
            "score_id": _score_id(
                self.project_id,
                self.batch_id,
                self.taxonomy.taxonomy_version,
                sku_input.sku_code,
                user_task.user_task_code,
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
            "user_task_code": user_task.user_task_code,
            "user_task_name": user_task.user_task_name,
            "user_task_definition": user_task.definition,
            "relation_status": relation_status,
            "user_task_score": user_task_score,
            "comment_task_need_score": comment_score,
            "claim_task_alignment_score": claim_score,
            "param_capability_score": param_score,
            "size_price_fit_score": size_price_fit_score,
            "market_validation_score": market_validation_score,
            "negative_drag_score": negative_drag_score,
            "sentiment_polarity": comment_match["sentiment_polarity"],
            "size_tier": sku_input.size_tier,
            "price_band_in_size_tier": sku_input.price_band_in_size_tier,
            "price_percentile_in_size_tier": sku_input.price_percentile_in_size_tier,
            "score_breakdown_json": _json_safe(
                {
                    "comment_task_need": comment_match,
                    "claim_alignment": claim_match,
                    "param_capability": param_match,
                    "size_price": {
                        "gate_status": size_price_gate_status,
                        "allowed_size_tiers": user_task.allowed_size_tiers,
                        "allowed_price_bands": user_task.allowed_price_bands,
                        "score": size_price_fit_score,
                    },
                    "market": _market_snapshot(
                        sku_input.market_profile, sku_input.comparable_market_context
                    ),
                    "negative_drag_score": negative_drag_score,
                }
            ),
            "status_reason_cn": _status_reason_cn(
                user_task,
                relation_status=relation_status,
                size_price_gate_status=size_price_gate_status,
                comment_score=comment_score,
                claim_score=claim_score,
                param_score=param_score,
                negative_drag_score=negative_drag_score,
                comment_match=comment_match,
            ),
            "evidence_ids_json": evidence_ids[:80],
            "review_required": review_required,
            "review_status": "review_required" if review_required else "auto_pass",
            "review_reason_json": _json_safe(review_reason),
            "confidence": _confidence(
                size_price_fit_score, comment_score, claim_score, param_score, sku_input
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
            and payload["user_task_score"] >= Decimal("0.5500")
            and payload["comment_task_need_score"] >= Decimal("0.5200")
            and payload["score_breakdown_json"]["size_price"]["gate_status"]
            in {"matched", "adjacent", "unknown"}
        ]
        eligible.sort(
            key=lambda item: (
                item["user_task_score"],
                item["comment_task_need_score"],
                item["claim_task_alignment_score"],
                item["param_capability_score"],
            ),
            reverse=True,
        )
        if eligible:
            eligible[0]["relation_status"] = REL_PRIMARY
            eligible[0]["status_reason_cn"] = eligible[0]["status_reason_cn"].replace(
                "可作为候选用户任务", "作为主用户任务"
            )
            eligible[0]["result_hash"] = _score_result_hash(
                eligible[0], self.taxonomy.taxonomy_version, self.rule_version
            )

        secondary = [
            payload
            for payload in score_payloads
            if payload["relation_status"] == REL_SECONDARY
        ]
        secondary.sort(key=lambda item: item["user_task_score"], reverse=True)
        for payload in secondary[2:]:
            payload["relation_status"] = REL_LATENT
            payload["status_reason_cn"] = (
                f"{payload['user_task_name']}证据成立但已超出最多两个次用户任务限制，降为潜在能力任务。"
            )
            payload["result_hash"] = _score_result_hash(
                payload, self.taxonomy.taxonomy_version, self.rule_version
            )
        return score_payloads

    def _profile_payload(
        self, sku_input: M09CSkuInput, score_payloads: Sequence[dict[str, Any]]
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
            key=lambda item: item["user_task_score"],
            reverse=True,
        )[:2]
        observed = sorted(
            [
                item
                for item in score_payloads
                if item["relation_status"] == REL_COMMENT_OBSERVED
            ],
            key=lambda item: item["user_task_score"],
            reverse=True,
        )
        claimed = sorted(
            [
                item
                for item in score_payloads
                if item["relation_status"] == REL_BRAND_CLAIMED
            ],
            key=lambda item: item["user_task_score"],
            reverse=True,
        )
        latent = sorted(
            [item for item in score_payloads if item["relation_status"] == REL_LATENT],
            key=lambda item: item["user_task_score"],
            reverse=True,
        )
        drag = sorted(
            [item for item in score_payloads if item["relation_status"] == REL_DRAG],
            key=lambda item: item["negative_drag_score"],
            reverse=True,
        )
        evidence_ids = _unique(
            evidence_id
            for item in score_payloads
            for evidence_id in item["evidence_ids_json"]
        )
        no_primary_reason = (
            None if primary else _no_primary_reason(score_payloads, sku_input)
        )
        summary = {
            "primary": _compact_score(primary) if primary else None,
            "secondary": [_compact_score(item) for item in secondary],
            "comment_observed": [_compact_score(item) for item in observed[:8]],
            "brand_claimed": [_compact_score(item) for item in claimed[:8]],
            "latent_capability": [_compact_score(item) for item in latent[:8]],
            "drag_factor": [_compact_score(item) for item in drag[:8]],
            "no_primary_reason_cn": no_primary_reason,
            "comment_summary": _comment_summary(score_payloads),
            "claim_param_summary": _claim_param_summary(score_payloads),
        }
        review_required = bool(no_primary_reason) or any(
            item["review_required"] for item in score_payloads
        )
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
            "primary_user_task_code": primary["user_task_code"] if primary else None,
            "primary_relation_status": primary["relation_status"] if primary else None,
            "secondary_user_task_codes_json": [
                item["user_task_code"] for item in secondary
            ],
            "comment_observed_task_codes_json": [
                item["user_task_code"] for item in observed
            ],
            "brand_claimed_task_codes_json": [
                item["user_task_code"] for item in claimed
            ],
            "latent_capability_task_codes_json": [
                item["user_task_code"] for item in latent
            ],
            "drag_factor_task_codes_json": [item["user_task_code"] for item in drag],
            "user_task_summary_json": _json_safe(summary),
            "no_primary_reason": no_primary_reason,
            "review_required": review_required,
            "review_status": "review_required" if review_required else "auto_pass",
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
                "primary": payload["primary_user_task_code"],
                "secondary": payload["secondary_user_task_codes_json"],
                "comment_observed": payload["comment_observed_task_codes_json"],
                "brand_claimed": payload["brand_claimed_task_codes_json"],
                "latent": payload["latent_capability_task_codes_json"],
                "drag": payload["drag_factor_task_codes_json"],
                "summary": payload["user_task_summary_json"],
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M09C_PROFILE_HASH_VERSION,
        )
        return payload

    def _coverage_payloads(
        self, score_payloads: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for user_task in self.user_tasks:
            rows = [
                item
                for item in score_payloads
                if item["user_task_code"] == user_task.user_task_code
                and item["relation_status"] != REL_NOT_SUPPORTED
            ]
            status_counts = Counter(item["relation_status"] for item in rows)
            top_skus = sorted(
                rows, key=lambda item: item["user_task_score"], reverse=True
            )[:30]
            payload = {
                "coverage_id": _coverage_id(
                    self.project_id,
                    self.batch_id,
                    self.taxonomy.taxonomy_version,
                    user_task.user_task_code,
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
                "user_task_code": user_task.user_task_code,
                "user_task_name": user_task.user_task_name,
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
                "latent_capability_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_LATENT
                ],
                "drag_factor_sku_codes_json": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_DRAG
                ],
                "top_skus_json": [_compact_score(item) for item in top_skus],
                "is_current": True,
            }
            payload["coverage_hash"] = stable_hash(
                {
                    "user_task_code": payload["user_task_code"],
                    "sku_count": payload["sku_count"],
                    "status_counts": payload["relation_status_counts_json"],
                    "top_skus": payload["top_skus_json"],
                    "taxonomy_version": self.taxonomy.taxonomy_version,
                    "rule_version": self.rule_version,
                },
                version=M09C_COVERAGE_HASH_VERSION,
            )
            payloads.append(payload)
        return payloads


def _task(
    user_task_code: str,
    user_task_name: str,
    definition: str,
    comment_subdimension_codes: tuple[str, ...],
    comment_keywords: tuple[str, ...],
    allowed_size_tiers: tuple[str, ...],
    allowed_price_bands: tuple[str, ...],
    claim_codes: tuple[str, ...],
    param_codes: tuple[str, ...],
    *,
    adjacent_size_tiers: tuple[str, ...] = (),
    adjacent_price_bands: tuple[str, ...] = (),
) -> M09CUserTaskDefinition:
    return M09CUserTaskDefinition(
        user_task_code=user_task_code,
        user_task_name=user_task_name,
        definition=definition,
        comment_subdimension_codes=comment_subdimension_codes,
        comment_keywords=comment_keywords,
        allowed_size_tiers=allowed_size_tiers,
        allowed_price_bands=allowed_price_bands,
        claim_codes=claim_codes,
        param_codes=param_codes,
        adjacent_size_tiers=adjacent_size_tiers,
        adjacent_price_bands=adjacent_price_bands,
    )


def _filter_user_tasks(
    taxonomy: M09CUserTaskTaxonomy,
    user_task_codes: Sequence[str],
) -> tuple[M09CUserTaskDefinition, ...]:
    if not user_task_codes:
        return taxonomy.user_tasks
    code_set = {str(code) for code in user_task_codes}
    missing = sorted(code_set - set(taxonomy.user_tasks_by_code))
    if missing:
        raise ValueError(f"M09C 未找到用户任务 code：{', '.join(missing)}")
    return tuple(
        item for item in taxonomy.user_tasks if item.user_task_code in code_set
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
) -> list[M09CSkuInput]:
    base_inputs = [
        (profile, _canonical_size_tier(profile)) for profile in param_profiles
    ]
    price_bands = _derive_price_bands(base_inputs, market_profiles)
    comparable_market_contexts = _derive_comparable_market_contexts(
        base_inputs, market_weekly_rows
    )
    result: list[M09CSkuInput] = []
    for profile, size_tier in base_inputs:
        market_profile = market_profiles.get(profile.sku_code)
        claim_profile = claim_profiles.get(profile.sku_code)
        price_band, percentile = price_bands.get(profile.sku_code, ("unknown", None))
        result.append(
            M09CSkuInput(
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
    sku_input: M09CSkuInput, user_task: M09CUserTaskDefinition
) -> str:
    if (
        sku_input.size_tier == "unknown"
        or sku_input.price_band_in_size_tier == "unknown"
    ):
        return "unknown"
    size_ok = sku_input.size_tier in user_task.allowed_size_tiers
    price_ok = sku_input.price_band_in_size_tier in user_task.allowed_price_bands
    if size_ok and price_ok:
        return "matched"
    if (
        size_ok and sku_input.price_band_in_size_tier in user_task.adjacent_price_bands
    ) or (price_ok and sku_input.size_tier in user_task.adjacent_size_tiers):
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
    user_task: M09CUserTaskDefinition,
) -> dict[str, Any]:
    wanted = set(user_task.comment_subdimension_codes)
    rows = [
        row
        for row in comment_facts
        if not _is_service_comment(row)
        and (
            row.subdimension_code in wanted
            or _keyword_match(row.clean_comment_text, user_task.comment_keywords)
        )
    ]
    service_rows = [row for row in comment_facts if _is_service_comment(row)]
    direct_rows = [
        row
        for row in rows
        if row.dimension_type in {"use_case_signal", "audience_signal"}
        or row.subdimension_code.startswith("use_")
        or row.subdimension_code.startswith("audience_")
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
        + Decimal(negative_count) * Decimal("0.70")
    )
    raw_score = weighted / Decimal("2.0") if direct_rows else weighted / Decimal("3.0")
    if direct_rows:
        raw_score = max(raw_score, Decimal("0.6200"))
    if len(direct_rows) >= 2:
        raw_score = max(raw_score, Decimal("0.8200"))
    if len(rows) >= 2 and not direct_rows:
        raw_score = max(raw_score, Decimal("0.5500"))
    if negative_count and negative_count >= positive_count:
        raw_score = min(max(raw_score, Decimal("0.5200")), Decimal("0.7200"))
    return {
        "score": _clamp_decimal(raw_score),
        "fact_count": len(rows),
        "direct_count": len(direct_rows),
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
    user_task: M09CUserTaskDefinition,
) -> dict[str, Any]:
    wanted = set(user_task.claim_codes)
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
    user_task: M09CUserTaskDefinition,
) -> dict[str, Any]:
    param_values = param_profile.param_values_json or {}
    supported: list[str] = []
    unknown: list[str] = []
    for param_code in user_task.param_codes:
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
    denominator = Decimal(max(1, min(5, len(user_task.param_codes))))
    return {
        "score": _clamp_decimal(Decimal(len(supported)) / denominator),
        "supported_param_codes": sorted(set(supported)),
        "unknown_param_codes": sorted(set(unknown)),
    }


def _negative_drag_score(
    comment_match: Mapping[str, Any],
    claim_match: Mapping[str, Any],
    param_match: Mapping[str, Any],
) -> Decimal:
    negative_count = int(comment_match.get("negative_count") or 0)
    positive_count = int(comment_match.get("positive_count") or 0)
    if negative_count <= 0:
        return Decimal("0.0000")
    base = (
        Decimal("0.4500")
        if negative_count >= max(1, positive_count)
        else Decimal("0.2500")
    )
    if set(comment_match.get("contradicted_claim_codes") or []) & set(
        claim_match.get("matched_claim_codes") or []
    ):
        base += Decimal("0.2500")
    if set(comment_match.get("contradicted_param_codes") or []) & set(
        param_match.get("supported_param_codes") or []
    ):
        base += Decimal("0.2500")
    if comment_match.get("fact_count", 0) >= 2:
        base += Decimal("0.1000")
    return _clamp_decimal(base)


def _initial_relation_status(
    *,
    size_price_gate_status: str,
    score: Decimal,
    comment_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    negative_drag_score: Decimal,
    positive_count: int,
    negative_count: int,
    service_only: bool,
) -> str:
    if service_only:
        return REL_NOT_SUPPORTED
    if (
        negative_count > 0
        and negative_count >= max(1, positive_count)
        and comment_score >= Decimal("0.5000")
    ):
        return REL_DRAG
    if size_price_gate_status == "mismatch" and comment_score < Decimal("0.6500"):
        return REL_NOT_SUPPORTED
    if (
        score >= Decimal("0.5200")
        and comment_score >= Decimal("0.5200")
        and size_price_gate_status in {"matched", "adjacent", "unknown"}
        and (claim_score >= Decimal("0.2500") or param_score >= Decimal("0.2500"))
        and negative_drag_score < Decimal("0.4500")
    ):
        return REL_SECONDARY
    if comment_score >= Decimal("0.6200") and (
        claim_score < Decimal("0.2500") or param_score < Decimal("0.2500")
    ):
        return REL_COMMENT_OBSERVED
    if (
        claim_score >= Decimal("0.5000")
        and param_score >= Decimal("0.4000")
        and comment_score < Decimal("0.3500")
    ):
        return REL_BRAND_CLAIMED
    if (
        param_score >= Decimal("0.4500")
        and size_price_gate_status in {"matched", "adjacent"}
        and comment_score < Decimal("0.3500")
    ):
        return REL_LATENT
    if score >= Decimal("0.4000") and size_price_gate_status in {
        "matched",
        "adjacent",
        "unknown",
    }:
        return REL_LATENT
    return REL_NOT_SUPPORTED


def _status_reason_cn(
    user_task: M09CUserTaskDefinition,
    *,
    relation_status: str,
    size_price_gate_status: str,
    comment_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    negative_drag_score: Decimal,
    comment_match: Mapping[str, Any],
) -> str:
    if relation_status == REL_NOT_SUPPORTED:
        return f"{user_task.user_task_name}未成立，主要原因是用户评论、卖点、参数或尺寸价格证据不足。"
    if relation_status == REL_DRAG:
        return f"{user_task.user_task_name}有用户需求，但负向评论集中或产品支撑不足，按拖后腿任务处理。"
    if relation_status == REL_COMMENT_OBSERVED:
        return f"{user_task.user_task_name}在评论中被观察到，但卖点或参数支撑不足，暂不作为主用户任务。"
    if relation_status == REL_BRAND_CLAIMED:
        return f"{user_task.user_task_name}有厂家卖点和参数支撑，但用户评论验证不足，暂按厂家主打任务处理。"
    if relation_status == REL_LATENT:
        return f"{user_task.user_task_name}有尺寸价格或参数适配，但用户评论和卖点证据不足，暂按潜在能力任务处理。"
    return (
        f"{user_task.user_task_name}可作为候选用户任务：尺寸价格 {size_price_gate_status}，"
        f"评论 {comment_score}，卖点 {claim_score}，参数 {param_score}，拖后腿 {negative_drag_score}；"
        f"评论匹配 {comment_match.get('fact_count', 0)} 条。"
    )


def _review_reason(
    relation_status: str,
    size_price_gate_status: str,
    comment_match: Mapping[str, Any],
    claim_match: Mapping[str, Any],
    param_match: Mapping[str, Any],
    negative_drag_score: Decimal,
) -> dict[str, Any]:
    reasons: list[str] = []
    if size_price_gate_status == "unknown":
        reasons.append("missing_size_or_price_band")
    if comment_match.get("service_excluded_count"):
        reasons.append("service_signal_excluded")
    if relation_status == REL_DRAG:
        reasons.append("negative_comment_drag_factor")
    if relation_status == REL_COMMENT_OBSERVED:
        reasons.append("comment_strong_claim_param_weak")
    if relation_status == REL_BRAND_CLAIMED and param_match.get("unknown_param_codes"):
        reasons.append("brand_claim_param_weak")
    if claim_match.get("unsupported_claim_codes"):
        reasons.append("unsupported_claim_codes_present")
    if param_match.get("unknown_param_codes"):
        reasons.append("unknown_param_codes_present")
    if negative_drag_score >= Decimal("0.6500"):
        reasons.append("high_negative_drag_score")
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
    claim_score: Decimal,
    param_score: Decimal,
    sku_input: M09CSkuInput,
) -> Decimal:
    domain_count = 0
    if size_price_fit_score >= Decimal("0.5500"):
        domain_count += 1
    if comment_score > Decimal("0.0000"):
        domain_count += 1
    if claim_score > Decimal("0.0000"):
        domain_count += 1
    if param_score > Decimal("0.0000"):
        domain_count += 1
    if sku_input.market_profile is not None:
        domain_count += 1
    return _clamp_decimal(Decimal(domain_count) / Decimal("5"))


def _no_primary_reason(
    score_payloads: Sequence[dict[str, Any]], sku_input: M09CSkuInput
) -> str:
    comment_hits = [
        item
        for item in score_payloads
        if item["comment_task_need_score"] >= Decimal("0.5200")
    ]
    brand_hits = [
        item for item in score_payloads if item["relation_status"] == REL_BRAND_CLAIMED
    ]
    drag_hits = [item for item in score_payloads if item["relation_status"] == REL_DRAG]
    if drag_hits and not comment_hits:
        return "评论中有负向任务需求，但没有形成足够正向主用户任务证据。"
    if comment_hits:
        return "评论中有任务需求，但卖点、参数或尺寸价格支撑不足，未形成主用户任务。"
    if brand_hits:
        return "厂家卖点和参数有任务指向，但缺少用户评论验证，未形成主用户任务。"
    if not sku_input.comment_profile:
        return "缺少该 SKU 评论事实画像，无法确认真实用户主观任务。"
    return "评论、卖点、参数和市场证据均不足，允许该 SKU 暂无主用户任务。"


def _comment_summary(score_payloads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    supported = [
        item
        for item in score_payloads
        if item["comment_task_need_score"] > Decimal("0.0000")
        and item["relation_status"] != REL_NOT_SUPPORTED
    ]
    return {
        "matched_task_count": len(supported),
        "top_comment_tasks": [
            _compact_score(item)
            for item in sorted(
                supported, key=lambda row: row["comment_task_need_score"], reverse=True
            )[:5]
        ],
    }


def _claim_param_summary(score_payloads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "brand_claimed_task_count": sum(
            1 for item in score_payloads if item["relation_status"] == REL_BRAND_CLAIMED
        ),
        "latent_capability_task_count": sum(
            1 for item in score_payloads if item["relation_status"] == REL_LATENT
        ),
        "drag_factor_task_count": sum(
            1 for item in score_payloads if item["relation_status"] == REL_DRAG
        ),
    }


def _compact_score(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return {
        "user_task_code": payload["user_task_code"],
        "user_task_name": payload["user_task_name"],
        "relation_status": payload["relation_status"],
        "score": _decimal_to_float(payload["user_task_score"]),
        "comment_score": _decimal_to_float(payload["comment_task_need_score"]),
        "claim_score": _decimal_to_float(payload["claim_task_alignment_score"]),
        "param_score": _decimal_to_float(payload["param_capability_score"]),
        "negative_drag_score": _decimal_to_float(payload["negative_drag_score"]),
        "size_tier": payload["size_tier"],
        "price_band_in_size_tier": payload["price_band_in_size_tier"],
        "sentiment_polarity": payload["sentiment_polarity"],
    }


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
        version=M09C_PROFILE_ID_HASH_VERSION,
    )


def _score_id(
    project_id: str,
    batch_id: str,
    taxonomy_version: str,
    sku_code: str,
    user_task_code: str,
    rule_version: str,
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "sku_code": sku_code,
            "user_task_code": user_task_code,
            "rule_version": rule_version,
        },
        version=M09C_SCORE_ID_HASH_VERSION,
    )


def _coverage_id(
    project_id: str,
    batch_id: str,
    taxonomy_version: str,
    user_task_code: str,
    rule_version: str,
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "user_task_code": user_task_code,
            "rule_version": rule_version,
        },
        version=M09C_COVERAGE_ID_HASH_VERSION,
    )


def _score_result_hash(
    payload: Mapping[str, Any], taxonomy_version: str, rule_version: str
) -> str:
    return stable_hash(
        {
            "sku_code": payload["sku_code"],
            "user_task_code": payload["user_task_code"],
            "relation_status": payload["relation_status"],
            "score": str(payload["user_task_score"]),
            "breakdown": payload["score_breakdown_json"],
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
        },
        version=M09C_SCORE_HASH_VERSION,
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
        module_code=Core3ModuleCode.M09C,
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
            "message_cn": message_cn,
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
        module_code=Core3ModuleCode.M09C,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=[message_cn],
        review_issues=[
            {
                "issue_code": error_code,
                "issue_type": error_code,
                "severity": "blocker",
                "source_module": Core3ModuleCode.M09C,
                "object_type": "module_run",
                "object_id": run_id,
                "message_cn": message_cn,
                "suggestion_cn": error_message,
            }
        ],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error_code": error_code,
            "message_cn": message_cn,
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
