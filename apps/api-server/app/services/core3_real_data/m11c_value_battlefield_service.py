"""M11C value battlefield profiles and graph snapshots.

M11C is deterministic. It consumes M03B parameter facts, M04C claim facts,
M05C comment facts, and M07 market facts. It does not call an LLM and it does
not reuse old M11 seed outputs as input.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_MODULE_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_extraction_repositories import (
    ParamExtractionRepository,
    ParamRepositoryHashConflictError,
    ParamRepositoryWriteResult,
)
from app.services.core3_real_data.repositories import (
    Core3BaseRepository,
    Core3RepositoryContext,
)
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


M11C_PROFILE_ID_HASH_VERSION = "m11c-value-battlefield-profile-id-v1"
M11C_PROFILE_HASH_VERSION = "m11c-value-battlefield-profile-v1"
M11C_SCORE_ID_HASH_VERSION = "m11c-value-battlefield-score-id-v1"
M11C_SCORE_HASH_VERSION = "m11c-value-battlefield-score-v1"
M11C_GRAPH_ID_HASH_VERSION = "m11c-value-battlefield-graph-id-v1"
M11C_GRAPH_HASH_VERSION = "m11c-value-battlefield-graph-v1"

PRICE_BANDS = ("low", "mid_low", "mid", "mid_high", "high")
TV_CANONICAL_SIZE_TIERS = (
    "small_32_45",
    "medium_46_59",
    "large_60_69",
    "xlarge_70_85",
    "giant_98_plus",
)
AC_CANONICAL_SIZE_TIERS = (
    "wall_hp_1_or_below",
    "wall_hp_1_5",
    "wall_hp_2",
    "wall_hp_3",
    "floor_hp_2",
    "floor_hp_3",
    "floor_hp_3_plus",
)
CANONICAL_SIZE_TIERS = TV_CANONICAL_SIZE_TIERS
ALL_CANONICAL_SIZE_TIERS = TV_CANONICAL_SIZE_TIERS + AC_CANONICAL_SIZE_TIERS
SIZE_TIER_ORDER = {tier: index for index, tier in enumerate(ALL_CANONICAL_SIZE_TIERS)}
COMPARABLE_MARKET_POLICY_VERSION = "m11c_comparable_weekly_overlap_v1"

REL_PRIMARY = "primary_battlefield"
REL_SECONDARY = "secondary_battlefield"
REL_OPPORTUNITY = "opportunity_battlefield"
REL_BRAND_CLAIMED = "brand_claimed_battlefield"
REL_USER_OBSERVED = "user_observed_battlefield"
REL_DRAG = "drag_factor_battlefield"
REL_EXCLUDED = "excluded"

VALUE_PREMIUM = "premium_driver"
VALUE_BASIC = "basic_support"
VALUE_BRAND_ONLY = "brand_claim_only"
VALUE_USER_NEED = "user_observed_need"
VALUE_DRAG = "drag_factor"
VALUE_UNMET = "unmet_need"
VALUE_NA = "not_applicable"


@dataclass(frozen=True)
class M11CBattlefieldDefinition:
    battlefield_code: str
    battlefield_name: str
    definition: str
    allowed_size_tiers: tuple[str, ...]
    allowed_price_bands: tuple[str, ...]
    primary_task_codes: tuple[str, ...]
    secondary_task_codes: tuple[str, ...]
    primary_target_group_codes: tuple[str, ...]
    comment_subdimension_codes: tuple[str, ...]
    claim_codes: tuple[str, ...]
    param_codes: tuple[str, ...]
    adjacent_size_tiers: tuple[str, ...] = ()
    adjacent_price_bands: tuple[str, ...] = ()


@dataclass(frozen=True)
class M11CValueBattlefieldTaxonomy:
    taxonomy_version: str
    product_category: str
    product_category_label_cn: str
    sku_code_prefix: str
    battlefields: tuple[M11CBattlefieldDefinition, ...]

    @property
    def battlefields_by_code(self) -> dict[str, M11CBattlefieldDefinition]:
        return {item.battlefield_code: item for item in self.battlefields}


@dataclass(frozen=True)
class M11CSkuInput:
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
class M11CWritePayload:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M11CServiceResult:
    input_count: int
    profile_count: int
    score_count: int
    graph_snapshot_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item["created_count"] for item in self.write_summary.values())


def tv_value_battlefield_taxonomy_v0_2() -> M11CValueBattlefieldTaxonomy:
    """Published TV M11C taxonomy confirmed in the business design thread."""

    return M11CValueBattlefieldTaxonomy(
        taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
        product_category="TV",
        product_category_label_cn="彩电",
        sku_code_prefix="TV",
        battlefields=(
            _bf(
                "BF_SMALL_SCREEN_ESSENTIAL_VALUE",
                "小屏刚需性价比战场",
                "小屏、低价、卧室/租房/副屏刚需，核心是便宜够用和尺寸适配。",
                ("small_32_45",),
                ("low", "mid_low"),
                ("TASK_BEDROOM_SECOND_SCREEN", "TASK_VALUE_FOR_MONEY_PURCHASE"),
                ("TASK_SENIOR_EASY_OPERATION", "TASK_SMART_CASTING_IOT"),
                ("TG_BEDROOM_RENTAL_SECOND_SCREEN", "TG_VALUE_MAXIMIZER"),
                (
                    "use_bedroom",
                    "audience_rental_room",
                    "value_price",
                    "appearance_size_fit",
                ),
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
                ),
            ),
            _bf(
                "BF_SMALL_SMART_EASY_USE",
                "小屏智能易用战场",
                "小屏但强调语音、投屏、智能连接和长辈友好。",
                ("small_32_45",),
                ("mid", "mid_high"),
                ("TASK_SENIOR_EASY_OPERATION", "TASK_SMART_CASTING_IOT"),
                ("TASK_BEDROOM_SECOND_SCREEN",),
                ("TG_SENIOR_PARENT_FRIENDLY", "TG_SMART_CONNECTED_USER"),
                (
                    "audience_senior",
                    "use_bedroom",
                    "use_casting_online",
                    "interaction_voice_casting",
                    "system_smooth_ads",
                ),
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
                adjacent_price_bands=("mid_low", "high"),
            ),
            _bf(
                "BF_MAINSTREAM_FAMILY_VALUE",
                "主流家庭性价比战场",
                "中大尺寸家庭日常观看，强调价格效率、够用画质和销量口碑。",
                ("medium_46_59", "large_60_69"),
                ("low", "mid_low", "mid"),
                ("TASK_MAINSTREAM_LIVING_VIEWING", "TASK_VALUE_FOR_MONEY_PURCHASE"),
                ("TASK_EYE_CARE_LONG_WATCHING",),
                ("TG_MAINSTREAM_FAMILY_VIEWER", "TG_VALUE_MAXIMIZER"),
                (
                    "use_living_room_cinema",
                    "audience_child_family",
                    "value_price",
                    "picture_clarity_resolution",
                ),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_value_price",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_full_screen_design",
                ),
                (
                    "screen_size_inch",
                    "resolution_class",
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                ),
                adjacent_size_tiers=("small_32_45", "xlarge_70_85"),
                adjacent_price_bands=("mid_high",),
            ),
            _bf(
                "BF_MAINSTREAM_LIVING_BALANCE",
                "主流客厅均衡体验战场",
                "中大尺寸客厅均衡体验，强调画质、系统、护眼、音效多项不偏科。",
                ("medium_46_59", "large_60_69"),
                ("mid", "mid_high"),
                ("TASK_MAINSTREAM_LIVING_VIEWING", "TASK_EYE_CARE_LONG_WATCHING"),
                ("TASK_CINEMA_IMMERSION", "TASK_SMART_CASTING_IOT"),
                ("TG_MAINSTREAM_FAMILY_VIEWER", "TG_CHILD_FAMILY_LONG_WATCH"),
                (
                    "use_living_room_cinema",
                    "audience_child_family",
                    "picture_clarity_resolution",
                    "picture_eye_care_reflection",
                    "system_smooth_ads",
                    "audio_quality",
                ),
                (
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_wide_color_accuracy",
                    "tv_claim_speaker_sound",
                    "tv_claim_eye_care_display",
                    "tv_claim_voice_control",
                ),
                (
                    "resolution_class",
                    "hdr_support_flag",
                    "declared_refresh_rate_hz",
                    "memory_capacity_gb",
                    "speaker_power_w",
                ),
                adjacent_price_bands=("mid_low", "high"),
            ),
            _bf(
                "BF_LARGE_SCREEN_VALUE_UPGRADE",
                "大屏换新性价比战场",
                "70-85 寸大屏换新，强调大尺寸、价格/英寸、补贴和销量验证。",
                ("xlarge_70_85",),
                ("low", "mid_low", "mid"),
                ("TASK_LARGE_SCREEN_UPGRADE", "TASK_VALUE_FOR_MONEY_PURCHASE"),
                ("TASK_CINEMA_IMMERSION",),
                ("TG_LARGE_SCREEN_UPGRADER", "TG_VALUE_MAXIMIZER"),
                (
                    "use_living_room_cinema",
                    "appearance_size_fit",
                    "value_price",
                    "replacement_source",
                ),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_value_price",
                    "tv_claim_full_screen_design",
                ),
                ("screen_size_inch", "resolution_class", "price_per_inch"),
                adjacent_size_tiers=("large_60_69", "giant_98_plus"),
                adjacent_price_bands=("mid_high",),
            ),
            _bf(
                "BF_LARGE_SCREEN_FAMILY_CINEMA",
                "大屏家庭影院战场",
                "70-85 寸家庭影院，强调大屏沉浸、HDR、音效和家庭观影。",
                ("xlarge_70_85",),
                ("mid", "mid_high"),
                ("TASK_CINEMA_IMMERSION", "TASK_MAINSTREAM_LIVING_VIEWING"),
                ("TASK_LARGE_SCREEN_UPGRADE",),
                ("TG_LARGE_SCREEN_UPGRADER", "TG_MAINSTREAM_FAMILY_VIEWER"),
                (
                    "use_living_room_cinema",
                    "audio_quality",
                    "picture_clarity_resolution",
                    "picture_brightness_hdr",
                    "appearance_size_fit",
                ),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_dolby_audio_video",
                    "tv_claim_speaker_sound",
                ),
                (
                    "screen_size_inch",
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                    "speaker_power_w",
                    "dolby_audio_flag",
                ),
                adjacent_price_bands=("mid_low", "high"),
            ),
            _bf(
                "BF_PREMIUM_PICTURE_UPGRADE",
                "高端画质升级战场",
                "中大/超大尺寸高端画质，核心是 MiniLED/OLED/QD、亮度、控光、色域、画质芯片。",
                ("large_60_69", "xlarge_70_85"),
                ("mid_high", "high"),
                ("TASK_PREMIUM_PICTURE_EXPERIENCE", "TASK_CINEMA_IMMERSION"),
                ("TASK_LARGE_SCREEN_UPGRADE",),
                ("TG_PREMIUM_AV_ENTHUSIAST",),
                (
                    "picture_clarity_resolution",
                    "picture_brightness_hdr",
                    "picture_color_accuracy",
                    "picture_local_dimming_black",
                    "use_living_room_cinema",
                ),
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
                    "mini_led_flag",
                    "mini_led_type",
                    "quantum_dot_flag",
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                    "local_dimming_zone_count",
                    "color_gamut_ratio",
                    "processor_chip_model",
                ),
                adjacent_price_bands=("mid",),
            ),
            _bf(
                "BF_PREMIUM_VALUE_DOWNTRADE",
                "高配下探价值战场",
                "70-85 寸在中高价格带提供高端配置，强调同价位更强或高配下探。",
                ("xlarge_70_85",),
                ("mid", "mid_high"),
                (
                    "TASK_PREMIUM_PICTURE_EXPERIENCE",
                    "TASK_LARGE_SCREEN_UPGRADE",
                    "TASK_VALUE_FOR_MONEY_PURCHASE",
                ),
                ("TASK_CINEMA_IMMERSION",),
                ("TG_VALUE_MAXIMIZER", "TG_PREMIUM_AV_ENTHUSIAST"),
                (
                    "value_price",
                    "picture_clarity_resolution",
                    "picture_brightness_hdr",
                    "competitor_compare",
                ),
                (
                    "tv_claim_value_price",
                    "tv_claim_miniled_display",
                    "tv_claim_hdr_high_brightness",
                    "tv_claim_high_refresh_rate",
                    "tv_claim_speaker_sound",
                ),
                (
                    "display_tech_class",
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                    "declared_refresh_rate_hz",
                    "local_dimming_zone_count",
                ),
                adjacent_price_bands=("low", "high"),
            ),
            _bf(
                "BF_GAMING_SPORTS_FLUENCY",
                "游戏体育流畅战场",
                "中大尺寸 mid 以上，强调高刷、HDMI2.1、VRR/MEMC、低延迟和运动流畅。",
                ("medium_46_59", "large_60_69", "xlarge_70_85"),
                ("mid", "mid_high", "high"),
                ("TASK_GAMING_CONSOLE_ENTERTAINMENT", "TASK_SPORTS_MOTION_WATCHING"),
                ("TASK_MAINSTREAM_LIVING_VIEWING",),
                ("TG_GAMING_SPORTS_USER",),
                (
                    "use_gaming_sports",
                    "gaming_high_refresh_motion",
                    "system_smooth_ads",
                ),
                (
                    "tv_claim_high_refresh_rate",
                    "tv_claim_gaming_low_latency",
                    "tv_claim_hdmi21_connectivity",
                ),
                (
                    "declared_refresh_rate_hz",
                    "hdmi_version_mix",
                    "hdmi_2_1_port_count",
                    "memc_flag",
                    "memory_capacity_gb",
                ),
                adjacent_size_tiers=("small_32_45",),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_EYE_CARE_FAMILY_COMFORT",
                "家庭护眼舒适战场",
                "小/中/大尺寸 mid_low 以上，强调儿童、长时间观看、护眼和舒适度。",
                ("small_32_45", "medium_46_59", "large_60_69"),
                ("mid_low", "mid", "mid_high", "high"),
                ("TASK_EYE_CARE_LONG_WATCHING", "TASK_MAINSTREAM_LIVING_VIEWING"),
                ("TASK_SENIOR_EASY_OPERATION",),
                (
                    "TG_CHILD_FAMILY_LONG_WATCH",
                    "TG_MAINSTREAM_FAMILY_VIEWER",
                    "TG_SENIOR_PARENT_FRIENDLY",
                ),
                (
                    "audience_child_family",
                    "audience_senior",
                    "picture_eye_care_reflection",
                    "use_living_room_cinema",
                ),
                ("tv_claim_eye_care_display",),
                (
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                    "declared_refresh_rate_hz",
                    "eye_care_flag",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("low",),
            ),
            _bf(
                "BF_SMART_CONNECTED_EXPERIENCE",
                "智能互联体验战场",
                "中尺寸及以上 mid 以上，强调投屏、AI 语音、家电联动、摄像头互动和系统流畅。",
                ("medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus"),
                ("mid", "mid_high", "high"),
                ("TASK_SMART_CASTING_IOT", "TASK_SENIOR_EASY_OPERATION"),
                ("TASK_MAINSTREAM_LIVING_VIEWING",),
                ("TG_SMART_CONNECTED_USER",),
                (
                    "use_casting_online",
                    "interaction_voice_casting",
                    "system_smooth_ads",
                    "audience_senior",
                ),
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
                    "voice_recognition_flag",
                    "far_field_voice_flag",
                    "ai_capability_flag",
                    "ai_model_capability_flag",
                    "smart_home_iot_flag",
                    "camera_flag",
                    "memory_capacity_gb",
                ),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_GIANT_SCREEN_VALUE_DOWNTRADE",
                "巨幕下探性价比战场",
                "98 寸以上巨幕但非旗舰定价，强调巨幕入门、价格/英寸、大屏换新和家庭影院下探。",
                ("giant_98_plus",),
                ("low", "mid", "mid_high"),
                (
                    "TASK_LARGE_SCREEN_UPGRADE",
                    "TASK_CINEMA_IMMERSION",
                    "TASK_VALUE_FOR_MONEY_PURCHASE",
                ),
                ("TASK_HOME_DECOR_SPACE_FIT",),
                (
                    "TG_GIANT_HOME_THEATER_BUYER",
                    "TG_LARGE_SCREEN_UPGRADER",
                    "TG_VALUE_MAXIMIZER",
                ),
                (
                    "use_living_room_cinema",
                    "appearance_size_fit",
                    "value_price",
                    "replacement_source",
                ),
                (
                    "tv_claim_theater_scene",
                    "tv_claim_value_price",
                    "tv_claim_full_screen_design",
                ),
                (
                    "screen_size_inch",
                    "resolution_class",
                    "price_per_inch",
                    "hdr_support_flag",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("mid_low", "high"),
            ),
            _bf(
                "BF_GIANT_HOME_THEATER_FLAGSHIP",
                "巨幕家庭影院旗舰战场",
                "98 寸以上巨幕旗舰，强调大客厅/新家、影院感、旗舰画质和空间融合。",
                ("giant_98_plus",),
                ("mid_high", "high"),
                ("TASK_CINEMA_IMMERSION", "TASK_HOME_DECOR_SPACE_FIT"),
                ("TASK_PREMIUM_PICTURE_EXPERIENCE",),
                ("TG_GIANT_HOME_THEATER_BUYER", "TG_PREMIUM_AV_ENTHUSIAST"),
                (
                    "use_living_room_cinema",
                    "appearance_size_fit",
                    "appearance_slim_wall",
                    "picture_brightness_hdr",
                    "audio_quality",
                ),
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
                    "hdr_support_flag",
                    "declared_brightness_nit_or_band",
                    "local_dimming_zone_count",
                    "speaker_power_w",
                    "flush_wall_mount_flag",
                ),
                adjacent_size_tiers=("xlarge_70_85",),
                adjacent_price_bands=("mid",),
            ),
        ),
    )


def tv_value_battlefield_taxonomy_v0_1() -> M11CValueBattlefieldTaxonomy:
    """Backward-compatible alias for callers that import the old factory name."""

    return tv_value_battlefield_taxonomy_v0_2()


def ac_value_battlefield_taxonomy_v0_1() -> M11CValueBattlefieldTaxonomy:
    """Published AC M11C taxonomy derived from AC fact profiles."""

    return M11CValueBattlefieldTaxonomy(
        taxonomy_version=CORE3_M11C_AC_TAXONOMY_VERSION,
        product_category="AC",
        product_category_label_cn="空调",
        sku_code_prefix="AC",
        battlefields=(
            _bf(
                "BF_WALL_SMALL_ENTRY_VALUE",
                "1匹及以下挂机刚需性价比战场",
                "1匹及以下挂机、低到中低价格带，面向小房间、租房和预算刚需，核心是便宜够用、冷暖有效和安装空间适配。",
                ("wall_hp_1_or_below",),
                ("low", "mid_low"),
                ("TASK_VALUE_SUBSIDY_PURCHASE", "TASK_INSTALL_SPACE_FIT"),
                ("TASK_FAST_COOL_HEAT", "TASK_ENERGY_SAVING_LONG_USE"),
                ("TG_RENTER_SMALL_ROOM", "TG_VALUE_REPLACEMENT_BUYER"),
                (
                    "value_positive",
                    "subsidy_promotion",
                    "use_rental_dorm",
                    "space_fit_area",
                    "cooling_effect",
                    "heating_effect",
                ),
                (
                    "ac_claim_price_value_subsidy",
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_fast_cooling_heating",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "cooling_capacity_w",
                    "energy_grade_normalized",
                    "inverter_flag",
                ),
                adjacent_size_tiers=("wall_hp_1_5",),
                adjacent_price_bands=("mid",),
            ),
            _bf(
                "BF_WALL_SMALL_COMFORT_UPGRADE",
                "1匹及以下挂机舒适升级战场",
                "1匹及以下挂机、中价以上，强调小空间静音、智能、洁净和外观升级，而不是单纯低价。",
                ("wall_hp_1_or_below",),
                ("mid", "mid_high", "high"),
                ("TASK_SLEEP_QUIET", "TASK_SMART_REMOTE_CONTROL"),
                ("TASK_HEALTH_CLEAN_AIR", "TASK_SOFT_WIND_NO_DIRECT"),
                ("TG_BEDROOM_SLEEP_SENSITIVE", "TG_SMART_REMOTE_USER"),
                (
                    "quiet_positive",
                    "sleep_scene",
                    "smart_app_remote",
                    "appearance_design",
                    "self_cleaning",
                    "soft_wind_no_direct",
                ),
                (
                    "ac_claim_quiet_sleep",
                    "ac_claim_smart_app_voice_iot",
                    "ac_claim_self_cleaning",
                    "ac_claim_soft_wind_no_direct",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "wifi_control_flag",
                    "self_cleaning_flag",
                    "comfort_airflow_flag",
                ),
                adjacent_size_tiers=("wall_hp_1_5",),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_WALL_1_5_MAINSTREAM_VALUE",
                "1.5匹挂机主流性价比战场",
                "1.5匹挂机、低到中价位，是卧室和中小房间主流购买带，核心是冷暖、省电、价格和口碑均衡。",
                ("wall_hp_1_5",),
                ("low", "mid_low", "mid"),
                ("TASK_FAST_COOL_HEAT", "TASK_VALUE_SUBSIDY_PURCHASE"),
                ("TASK_ENERGY_SAVING_LONG_USE", "TASK_INSTALL_SPACE_FIT"),
                ("TG_VALUE_REPLACEMENT_BUYER", "TG_FAMILY_LONG_USE_SAVER"),
                (
                    "cooling_effect",
                    "heating_effect",
                    "fast_cooling_heating",
                    "value_positive",
                    "energy_saving_usage",
                    "brand_recommendation",
                ),
                (
                    "ac_claim_fast_cooling_heating",
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_price_value_subsidy",
                    "ac_claim_authority_sales_certification",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "cooling_capacity_w",
                    "heating_capacity_w",
                    "energy_grade_normalized",
                    "inverter_flag",
                ),
                adjacent_size_tiers=("wall_hp_1_or_below", "wall_hp_2"),
                adjacent_price_bands=("mid_high",),
            ),
            _bf(
                "BF_WALL_1_5_SLEEP_COMFORT_UPGRADE",
                "1.5匹挂机睡眠舒适升级战场",
                "1.5匹挂机、中高价位，竞争重点从够用转向睡眠静音、柔风防直吹、智控和洁净能力。",
                ("wall_hp_1_5",),
                ("mid", "mid_high", "high"),
                ("TASK_SLEEP_QUIET", "TASK_SOFT_WIND_NO_DIRECT"),
                (
                    "TASK_SMART_REMOTE_CONTROL",
                    "TASK_HEALTH_CLEAN_AIR",
                    "TASK_ENERGY_SAVING_LONG_USE",
                ),
                (
                    "TG_BEDROOM_SLEEP_SENSITIVE",
                    "TG_CHILD_ELDER_COMFORT",
                    "TG_SMART_REMOTE_USER",
                ),
                (
                    "quiet_positive",
                    "sleep_scene",
                    "soft_wind_no_direct",
                    "airflow_even_swing",
                    "smart_app_remote",
                    "self_cleaning",
                ),
                (
                    "ac_claim_quiet_sleep",
                    "ac_claim_soft_wind_no_direct",
                    "ac_claim_smart_app_voice_iot",
                    "ac_claim_self_cleaning",
                    "ac_claim_ai_energy_saving",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "comfort_airflow_flag",
                    "wifi_control_flag",
                    "self_cleaning_flag",
                    "energy_efficiency_ratio",
                ),
                adjacent_size_tiers=("wall_hp_1_or_below", "wall_hp_2"),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_WALL_2_LARGE_ROOM_BALANCE",
                "2匹挂机大房间均衡战场",
                "2匹及以上挂机、中价以上，面向大卧室、小客厅或特殊安装约束，平衡匹数、风量、冷暖和外观空间。",
                ("wall_hp_2", "wall_hp_3"),
                ("mid", "mid_high", "high"),
                ("TASK_LARGE_SPACE_COVERAGE", "TASK_FAST_COOL_HEAT"),
                ("TASK_INSTALL_SPACE_FIT", "TASK_ENERGY_SAVING_LONG_USE"),
                ("TG_HOME_DECOR_SPACE_FIT", "TG_LIVING_ROOM_LARGE_SPACE"),
                (
                    "space_fit_area",
                    "airflow_volume_coverage",
                    "cooling_effect",
                    "fast_cooling_heating",
                    "installation_constraint",
                    "appearance_design",
                ),
                (
                    "ac_claim_large_airflow_coverage",
                    "ac_claim_fast_cooling_heating",
                    "ac_claim_installation_space_design",
                    "ac_claim_energy_efficiency_apf",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "cooling_capacity_w",
                    "airflow_volume_m3h",
                    "indoor_unit_dimensions_mm",
                ),
                adjacent_size_tiers=("wall_hp_1_5", "floor_hp_2"),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_FLOOR_2_ENTRY_LIVING_VALUE",
                "2匹柜机客厅入门战场",
                "2匹柜机、低到中价位，面向小客厅和入门柜机需求，核心是客厅覆盖、价格和安装形态。",
                ("floor_hp_2",),
                ("low", "mid_low", "mid"),
                ("TASK_LARGE_SPACE_COVERAGE", "TASK_VALUE_SUBSIDY_PURCHASE"),
                ("TASK_FAST_COOL_HEAT", "TASK_INSTALL_SPACE_FIT"),
                ("TG_LIVING_ROOM_LARGE_SPACE", "TG_VALUE_REPLACEMENT_BUYER"),
                (
                    "use_living_room_large",
                    "airflow_volume_coverage",
                    "value_positive",
                    "space_fit_area",
                    "cooling_effect",
                ),
                (
                    "ac_claim_large_airflow_coverage",
                    "ac_claim_price_value_subsidy",
                    "ac_claim_fast_cooling_heating",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "cooling_capacity_w",
                    "airflow_volume_m3h",
                ),
                adjacent_size_tiers=("wall_hp_2", "floor_hp_3"),
                adjacent_price_bands=("mid_high",),
            ),
            _bf(
                "BF_FLOOR_3_LIVING_VALUE_UPGRADE",
                "3匹柜机客厅性价比升级战场",
                "3匹柜机、中低到中高价位，是客厅柜机主力带，强调大风量、速冷速热、能效和补贴价值。",
                ("floor_hp_3",),
                ("mid_low", "mid", "mid_high"),
                ("TASK_LARGE_SPACE_COVERAGE", "TASK_FAST_COOL_HEAT"),
                ("TASK_ENERGY_SAVING_LONG_USE", "TASK_VALUE_SUBSIDY_PURCHASE"),
                (
                    "TG_LIVING_ROOM_LARGE_SPACE",
                    "TG_VALUE_REPLACEMENT_BUYER",
                    "TG_FAMILY_LONG_USE_SAVER",
                ),
                (
                    "use_living_room_large",
                    "airflow_volume_coverage",
                    "fast_cooling_heating",
                    "energy_saving_usage",
                    "value_positive",
                    "subsidy_promotion",
                ),
                (
                    "ac_claim_large_airflow_coverage",
                    "ac_claim_fast_cooling_heating",
                    "ac_claim_energy_efficiency_apf",
                    "ac_claim_price_value_subsidy",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "cooling_capacity_w",
                    "airflow_volume_m3h",
                    "energy_grade_normalized",
                ),
                adjacent_size_tiers=("floor_hp_2", "floor_hp_3_plus"),
                adjacent_price_bands=("low", "high"),
            ),
            _bf(
                "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH",
                "3匹及以上柜机高端舒适健康战场",
                "3匹及以上柜机、高价位，竞争重点是大空间舒适风、健康洁净、智能和品质信任。",
                ("floor_hp_3", "floor_hp_3_plus"),
                ("mid_high", "high"),
                ("TASK_LARGE_SPACE_COVERAGE", "TASK_HEALTH_CLEAN_AIR"),
                (
                    "TASK_SOFT_WIND_NO_DIRECT",
                    "TASK_SMART_REMOTE_CONTROL",
                    "TASK_RELIABLE_LONG_TERM_USE",
                ),
                (
                    "TG_LIVING_ROOM_LARGE_SPACE",
                    "TG_CHILD_ELDER_COMFORT",
                    "TG_BRAND_QUALITY_TRUST_BUYER",
                ),
                (
                    "use_living_room_large",
                    "airflow_volume_coverage",
                    "soft_wind_no_direct",
                    "self_cleaning",
                    "purification_antibacterial",
                    "brand_trust",
                ),
                (
                    "ac_claim_large_airflow_coverage",
                    "ac_claim_soft_wind_no_direct",
                    "ac_claim_self_cleaning",
                    "ac_claim_purification_antibacterial",
                    "ac_claim_smart_app_voice_iot",
                    "ac_claim_durability_core_material",
                ),
                (
                    "installation_type",
                    "horsepower_hp",
                    "airflow_volume_m3h",
                    "comfort_airflow_flag",
                    "purification_flag",
                    "wifi_control_flag",
                ),
                adjacent_size_tiers=("floor_hp_2",),
                adjacent_price_bands=("mid",),
            ),
            _bf(
                "BF_MID_HIGH_SMART_CONTROL_UPGRADE",
                "中高价智能控制升级战场",
                "各匹数中高价位中，围绕 APP 远程、WiFi、语音和智能感应形成的控制便利性升级。",
                AC_CANONICAL_SIZE_TIERS,
                ("mid", "mid_high", "high"),
                ("TASK_SMART_REMOTE_CONTROL",),
                ("TASK_SLEEP_QUIET", "TASK_INSTALL_SPACE_FIT"),
                ("TG_SMART_REMOTE_USER", "TG_CHILD_ELDER_COMFORT"),
                (
                    "smart_app_remote",
                    "remote_panel_easy_use",
                    "voice_iot",
                    "smart_negative",
                ),
                ("ac_claim_smart_app_voice_iot",),
                ("wifi_control_flag", "voice_control_flag", "smart_sensing_flag"),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_MID_HIGH_HEALTH_CLEAN_AIR_UPGRADE",
                "中高价健康洁净升级战场",
                "各匹数中高价位中，围绕自清洁、净化除菌、新风、异味霉味治理形成的健康升级。",
                AC_CANONICAL_SIZE_TIERS,
                ("mid", "mid_high", "high"),
                ("TASK_HEALTH_CLEAN_AIR",),
                ("TASK_DEHUMIDIFY_HUMID_CLIMATE", "TASK_SLEEP_QUIET"),
                ("TG_CHILD_ELDER_COMFORT", "TG_HUMID_SOUTH_USER"),
                (
                    "self_cleaning",
                    "purification_antibacterial",
                    "fresh_air_ventilation",
                    "odor_mold_risk",
                ),
                (
                    "ac_claim_self_cleaning",
                    "ac_claim_purification_antibacterial",
                    "ac_claim_fresh_air",
                ),
                ("self_cleaning_flag", "purification_flag", "fresh_air_flag"),
                adjacent_price_bands=("mid_low",),
            ),
            _bf(
                "BF_HUMID_CLIMATE_DEHUMIDIFY",
                "潮湿除湿场景战场",
                "各匹数中低价以上，南方潮湿、独立除湿和温湿双控场景；当前事实量较少，默认偏机会战场。",
                AC_CANONICAL_SIZE_TIERS,
                ("mid_low", "mid", "mid_high", "high"),
                ("TASK_DEHUMIDIFY_HUMID_CLIMATE", "TASK_HEALTH_CLEAN_AIR"),
                ("TASK_STABLE_TEMPERATURE",),
                ("TG_HUMID_SOUTH_USER",),
                (
                    "dehumidification",
                    "humid_weather",
                    "use_humid_south",
                    "odor_mold_risk",
                ),
                ("ac_claim_humidity_dehumidification", "ac_claim_self_cleaning"),
                ("self_cleaning_flag", "purification_flag"),
                adjacent_price_bands=("low",),
            ),
        ),
    )


class M11CValueBattlefieldTaxonomyLoader:
    def load(
        self, taxonomy_version: str, *, product_category: str
    ) -> M11CValueBattlefieldTaxonomy:
        normalized_category = str(product_category or "").upper()
        if (
            normalized_category == "TV"
            and taxonomy_version == CORE3_M11C_TV_TAXONOMY_VERSION
        ):
            return tv_value_battlefield_taxonomy_v0_2()
        if (
            normalized_category == "AC"
            and taxonomy_version == CORE3_M11C_AC_TAXONOMY_VERSION
        ):
            return ac_value_battlefield_taxonomy_v0_1()
        raise ValueError(
            f"{normalized_category or product_category} 价值战场 taxonomy 未发布，不能生成 M11C 价值战场画像。"
        )


def fact_rule_versions_for_product_category(product_category: str) -> dict[str, str]:
    normalized_category = str(product_category or "").upper()
    if normalized_category == "AC":
        return {
            "param_rule_version": CORE3_M03B_AC_RULE_VERSION,
            "claim_rule_version": CORE3_M04C_AC_RULE_VERSION,
            "comment_rule_version": CORE3_M05C_AC_RULE_VERSION,
        }
    return {
        "param_rule_version": CORE3_M03B_RULE_VERSION,
        "claim_rule_version": CORE3_M04C_TV_RULE_VERSION,
        "comment_rule_version": CORE3_M05C_TV_RULE_VERSION,
    }


class M11CValueBattlefieldRepository(ParamExtractionRepository):
    def save_profiles(
        self, profiles: Sequence[Any], *, replace_on_hash_conflict: bool = False
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuValueBattlefieldProfile,
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
            entities.Core3SkuValueBattlefieldScore,
            scores,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "sku_code",
                "battlefield_code",
                "rule_version",
                "is_current",
            ),
            hash_field="result_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_graph_snapshots(
        self, snapshots: Sequence[Any], *, replace_on_hash_conflict: bool = False
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ValueBattlefieldGraphSnapshot,
            snapshots,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "rule_version",
                "is_current",
            ),
            hash_field="graph_hash",
            replace_existing=replace_on_hash_conflict,
        )


class M11CInputReader(Core3BaseRepository):
    def list_param_profiles(
        self,
        batch_id: str,
        *,
        sku_code_prefix: str,
        param_rule_version: str = CORE3_M03B_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
    ) -> list[entities.Core3SkuParamProfile]:
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(
                entities.Core3SkuParamProfile.category_code == self.category_code.value
            )
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.rule_version == param_rule_version)
            .where(entities.Core3SkuParamProfile.sku_code.like(f"{sku_code_prefix}%"))
            .order_by(entities.Core3SkuParamProfile.sku_code)
        )
        if target_sku_codes:
            stmt = stmt.where(
                entities.Core3SkuParamProfile.sku_code.in_(tuple(target_sku_codes))
            )
        return list(self.db.execute(stmt).scalars())

    def list_market_profiles(
        self, batch_id: str, sku_codes: Sequence[str]
    ) -> list[entities.Core3SkuMarketProfile]:
        if not sku_codes:
            return []
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(
                entities.Core3SkuMarketProfile.category_code == self.category_code.value
            )
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(
                entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION
            )
            .where(
                entities.Core3SkuMarketProfile.analysis_window == "full_observed_window"
            )
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .where(entities.Core3SkuMarketProfile.sku_code.in_(tuple(sku_codes)))
            .order_by(entities.Core3SkuMarketProfile.sku_code)
        )
        return list(self.db.execute(stmt).scalars())

    def list_clean_market_weekly(
        self, batch_id: str, sku_codes: Sequence[str]
    ) -> list[entities.Core3CleanMarketWeekly]:
        if not sku_codes:
            return []
        stmt = (
            select(entities.Core3CleanMarketWeekly)
            .where(entities.Core3CleanMarketWeekly.project_id == self.project_id)
            .where(
                entities.Core3CleanMarketWeekly.category_code
                == self.category_code.value
            )
            .where(entities.Core3CleanMarketWeekly.batch_id == batch_id)
            .where(entities.Core3CleanMarketWeekly.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3CleanMarketWeekly.period_week_index.is_not(None))
            .where(entities.Core3CleanMarketWeekly.record_status == "active")
            .where(entities.Core3CleanMarketWeekly.quality_status == "ok")
            .order_by(
                entities.Core3CleanMarketWeekly.sku_code,
                entities.Core3CleanMarketWeekly.period_week_index,
            )
        )
        return list(self.db.execute(stmt).scalars())

    def list_claim_profiles(
        self,
        batch_id: str,
        sku_codes: Sequence[str],
        *,
        claim_rule_version: str = CORE3_M04C_TV_RULE_VERSION,
    ) -> list[entities.Core3SkuClaimFactProfile]:
        if not sku_codes:
            return []
        stmt = (
            select(entities.Core3SkuClaimFactProfile)
            .where(entities.Core3SkuClaimFactProfile.project_id == self.project_id)
            .where(
                entities.Core3SkuClaimFactProfile.category_code
                == self.category_code.value
            )
            .where(entities.Core3SkuClaimFactProfile.batch_id == batch_id)
            .where(entities.Core3SkuClaimFactProfile.rule_version == claim_rule_version)
            .where(entities.Core3SkuClaimFactProfile.is_current.is_(True))
            .where(entities.Core3SkuClaimFactProfile.sku_code.in_(tuple(sku_codes)))
            .order_by(entities.Core3SkuClaimFactProfile.sku_code)
        )
        return list(self.db.execute(stmt).scalars())

    def list_claim_facts(
        self,
        batch_id: str,
        sku_codes: Sequence[str],
        *,
        claim_rule_version: str = CORE3_M04C_TV_RULE_VERSION,
    ) -> list[entities.Core3SkuClaimFact]:
        if not sku_codes:
            return []
        stmt = (
            select(entities.Core3SkuClaimFact)
            .where(entities.Core3SkuClaimFact.project_id == self.project_id)
            .where(entities.Core3SkuClaimFact.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimFact.batch_id == batch_id)
            .where(entities.Core3SkuClaimFact.rule_version == claim_rule_version)
            .where(entities.Core3SkuClaimFact.is_current.is_(True))
            .where(entities.Core3SkuClaimFact.sku_code.in_(tuple(sku_codes)))
            .order_by(
                entities.Core3SkuClaimFact.sku_code,
                entities.Core3SkuClaimFact.claim_code,
            )
        )
        return list(self.db.execute(stmt).scalars())

    def list_comment_profiles(
        self,
        batch_id: str,
        sku_codes: Sequence[str],
        *,
        comment_rule_version: str = CORE3_M05C_TV_RULE_VERSION,
    ) -> list[entities.Core3SkuCommentFactProfile]:
        if not sku_codes:
            return []
        stmt = (
            select(entities.Core3SkuCommentFactProfile)
            .where(entities.Core3SkuCommentFactProfile.project_id == self.project_id)
            .where(
                entities.Core3SkuCommentFactProfile.category_code
                == self.category_code.value
            )
            .where(entities.Core3SkuCommentFactProfile.batch_id == batch_id)
            .where(
                entities.Core3SkuCommentFactProfile.rule_version == comment_rule_version
            )
            .where(entities.Core3SkuCommentFactProfile.is_current.is_(True))
            .where(entities.Core3SkuCommentFactProfile.sku_code.in_(tuple(sku_codes)))
            .order_by(entities.Core3SkuCommentFactProfile.sku_code)
        )
        return list(self.db.execute(stmt).scalars())

    def list_comment_facts(
        self,
        batch_id: str,
        sku_codes: Sequence[str],
        *,
        comment_rule_version: str = CORE3_M05C_TV_RULE_VERSION,
    ) -> list[entities.Core3CommentFactAtom]:
        if not sku_codes:
            return []
        stmt = (
            select(entities.Core3CommentFactAtom)
            .where(entities.Core3CommentFactAtom.project_id == self.project_id)
            .where(
                entities.Core3CommentFactAtom.category_code == self.category_code.value
            )
            .where(entities.Core3CommentFactAtom.batch_id == batch_id)
            .where(entities.Core3CommentFactAtom.rule_version == comment_rule_version)
            .where(entities.Core3CommentFactAtom.is_current.is_(True))
            .where(entities.Core3CommentFactAtom.sku_code.in_(tuple(sku_codes)))
            .order_by(
                entities.Core3CommentFactAtom.sku_code,
                entities.Core3CommentFactAtom.subdimension_code,
            )
        )
        return list(self.db.execute(stmt).scalars())


class M11CRunner:
    module_code = Core3ModuleCode.M11C

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
                message_cn="M11C 缺少 M00 batch_id，无法生成价值战场画像。",
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
                or CORE3_M11C_TV_TAXONOMY_VERSION
            ),
            rule_version=str(
                target.metadata.get("rule_version") or CORE3_M11C_TV_RULE_VERSION
            ),
            target_sku_codes=target.target_ids,
            battlefield_codes=target.metadata.get("battlefield_codes") or (),
            force_rebuild=bool(target.metadata.get("force_rebuild")),
            graph_mode=str(target.metadata.get("graph_mode") or "inline"),
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
        taxonomy_version: str = CORE3_M11C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M11C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        battlefield_codes: Sequence[str] = (),
        force_rebuild: bool = False,
        graph_mode: str = "inline",
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
                service_result = M11CService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    taxonomy_version=taxonomy_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    battlefield_codes=battlefield_codes,
                    force_rebuild=force_rebuild,
                    graph_mode=graph_mode,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m11c_value_battlefield_hash_conflict",
                message_cn="M11C 价值战场画像结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m11c_value_battlefield_failed",
                message_cn="M11C 价值战场画像生成失败，请检查 M03B/M04C/M05C/M07 事实层是否已生成。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M11C_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
            "product_category": product_category,
            "target_sku_codes": list(target_sku_codes),
            "battlefield_codes": list(battlefield_codes),
            "graph_mode": graph_mode,
            **service_result.summary,
        }
        status = (
            Core3RunStatus.WARNING
            if service_result.warnings
            else Core3RunStatus.SUCCESS
        )
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M11C,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.profile_count
            + service_result.score_count
            + service_result.graph_snapshot_count,
            output_hash=stable_hash(
                summary_json, version="m11c_value_battlefield_summary_v1"
            ),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {
                    "module_code": "M12",
                    "reason": "价值战场变化会影响竞品库和候选竞品召回。",
                },
                {
                    "module_code": "M11.5",
                    "reason": "主价值战场会影响卖点溢价/拖后腿分层。",
                },
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M11CService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M11C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M11C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        battlefield_codes: Sequence[str] = (),
        force_rebuild: bool = False,
        graph_mode: str = "inline",
    ) -> M11CServiceResult:
        taxonomy = M11CValueBattlefieldTaxonomyLoader().load(
            taxonomy_version, product_category=product_category
        )
        selected_battlefields = _filter_battlefields(taxonomy, battlefield_codes)
        fact_versions = fact_rule_versions_for_product_category(
            taxonomy.product_category
        )
        reader = M11CInputReader(self.context)
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
        profiles, scores, graph_snapshot, summary = M11CProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            battlefields=selected_battlefields,
            rule_version=rule_version,
        ).build(sku_inputs, graph_mode=graph_mode)

        repository = M11CValueBattlefieldRepository(self.context)
        write_results = {
            "value_battlefield_profiles": repository.save_profiles(
                profiles, replace_on_hash_conflict=force_rebuild
            ),
            "value_battlefield_scores": repository.save_scores(
                scores, replace_on_hash_conflict=force_rebuild
            ),
        }
        if graph_snapshot is not None:
            write_results["value_battlefield_graphs"] = repository.save_graph_snapshots(
                [graph_snapshot],
                replace_on_hash_conflict=force_rebuild,
            )

        warnings: list[str] = []
        if not sku_inputs:
            warnings.append(
                "M11C 没有读取到 M03B 参数画像，无法生成 SKU 价值战场画像。"
            )
        if sku_inputs and not any(item.market_profile for item in sku_inputs):
            warnings.append(
                "M11C 没有读取到 M07 full_observed_window 市场画像，价格带和市场验证降级。"
            )
        if sku_inputs and not any(
            item.comparable_market_context for item in sku_inputs
        ):
            warnings.append(
                "M11C 没有读取到 M01 周度量价事实，市场验证降级为 M07 累计窗口兼容口径。"
            )
        if sku_inputs and not any(item.comment_profile for item in sku_inputs):
            warnings.append("M11C 没有读取到 M05C 评论事实画像，用户声音降级为弱证据。")
        return M11CServiceResult(
            input_count=len(sku_inputs),
            profile_count=len(profiles),
            score_count=len(scores),
            graph_snapshot_count=1 if graph_snapshot is not None else 0,
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


class M11CProfileBuilder:
    def __init__(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        taxonomy: M11CValueBattlefieldTaxonomy,
        battlefields: tuple[M11CBattlefieldDefinition, ...],
        rule_version: str,
    ) -> None:
        self.project_id = project_id
        self.category_code = category_code
        self.batch_id = batch_id
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.taxonomy = taxonomy
        self.battlefields = battlefields
        self.rule_version = rule_version

    def build(
        self,
        sku_inputs: Sequence[M11CSkuInput],
        *,
        graph_mode: str = "inline",
    ) -> tuple[
        list[M11CWritePayload],
        list[M11CWritePayload],
        M11CWritePayload | None,
        dict[str, Any],
    ]:
        profiles: list[M11CWritePayload] = []
        scores: list[M11CWritePayload] = []
        status_counts: Counter[str] = Counter()
        primary_counts: Counter[str] = Counter()
        size_price_counts: Counter[str] = Counter()

        for sku_input in sku_inputs:
            sku_scores = [
                self._score_battlefield(sku_input, battlefield)
                for battlefield in self.battlefields
            ]
            sku_scores = self._assign_primary_secondary(sku_scores)
            scores.extend(M11CWritePayload(payload) for payload in sku_scores)
            profiles.append(
                M11CWritePayload(self._profile_payload(sku_input, sku_scores))
            )
            for payload in sku_scores:
                status_counts[payload["relation_status"]] += 1
                if payload["relation_status"] == REL_PRIMARY:
                    primary_counts[payload["battlefield_code"]] += 1
            size_price_counts[
                f"{sku_input.size_tier}:{sku_input.price_band_in_size_tier}"
            ] += 1

        graph_snapshot = None
        if graph_mode in {"inline", "rebuild-only"}:
            graph_snapshot = M11CWritePayload(
                self._graph_payload(sku_inputs, [score.payload for score in scores])
            )
        summary = {
            "sku_count": len(sku_inputs),
            "profile_count": len(profiles),
            "score_count": len(scores),
            "graph_snapshot_count": 1 if graph_snapshot is not None else 0,
            "battlefield_count": len(self.battlefields),
            "relation_status_counts": dict(sorted(status_counts.items())),
            "primary_battlefield_counts": dict(sorted(primary_counts.items())),
            "size_price_counts": dict(sorted(size_price_counts.items())),
            "taxonomy_codes": [
                battlefield.battlefield_code for battlefield in self.battlefields
            ],
            "size_tier_policy": "M03B canonical five-tier size policy; 86-97 inch gap remains unknown for M11C until business approves a bucket.",
            "price_band_policy": "Derived within M11C size_tier from M07 full_observed_window weighted price percentile.",
            "market_validation_policy": "Use pairwise overlapping weekly average volume/amount within M03B size_tier; cumulative sales are retained only as display context.",
        }
        return profiles, scores, graph_snapshot, summary

    def _score_battlefield(
        self, sku_input: M11CSkuInput, battlefield: M11CBattlefieldDefinition
    ) -> dict[str, Any]:
        market_gate_status = _market_gate_status(sku_input, battlefield)
        comment_match = _comment_match(sku_input.comment_facts, battlefield)
        claim_match = _claim_match(
            sku_input.claim_facts, sku_input.claim_profile, battlefield
        )
        param_match = _param_match(
            sku_input.param_profile, sku_input.market_profile, battlefield
        )
        user_voice_score = comment_match["score"]
        task_group_fit_score = _task_group_fit_score(
            comment_match, user_voice_score, market_gate_status
        )
        claim_alignment_score = claim_match["score"]
        param_capability_score = param_match["score"]
        market_pool_fit_score = {
            "matched": Decimal("1.0000"),
            "adjacent": Decimal("0.5500"),
            "unknown": Decimal("0.2500"),
        }.get(
            market_gate_status,
            Decimal("0.0000"),
        )
        market_validation_score = _market_validation_score(
            sku_input.market_profile, sku_input.comparable_market_context
        )
        battlefield_score = _clamp_decimal(
            user_voice_score * Decimal("0.30")
            + task_group_fit_score * Decimal("0.20")
            + claim_alignment_score * Decimal("0.15")
            + param_capability_score * Decimal("0.15")
            + market_pool_fit_score * Decimal("0.15")
            + market_validation_score * Decimal("0.05")
        )
        relation_status = _initial_relation_status(
            market_gate_status=market_gate_status,
            score=battlefield_score,
            user_voice_score=user_voice_score,
            claim_score=claim_alignment_score,
            param_score=param_capability_score,
            positive_count=comment_match["positive_count"],
            negative_count=comment_match["negative_count"],
        )
        value_effect = _value_effect(
            relation_status=relation_status,
            market_gate_status=market_gate_status,
            user_voice_score=user_voice_score,
            claim_score=claim_alignment_score,
            param_score=param_capability_score,
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
        status_reason_cn = _status_reason_cn(
            battlefield,
            market_gate_status=market_gate_status,
            relation_status=relation_status,
            user_voice_score=user_voice_score,
            claim_score=claim_alignment_score,
            param_score=param_capability_score,
            comment_match=comment_match,
        )
        payload = {
            "score_id": _score_id(
                self.project_id,
                self.batch_id,
                self.taxonomy.taxonomy_version,
                sku_input.sku_code,
                battlefield.battlefield_code,
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
            "battlefield_code": battlefield.battlefield_code,
            "battlefield_name": battlefield.battlefield_name,
            "battlefield_definition": battlefield.definition,
            "relation_status": relation_status,
            "value_effect": value_effect,
            "battlefield_score": battlefield_score,
            "market_gate_status": market_gate_status,
            "market_pool_fit_score": market_pool_fit_score,
            "user_voice_score": user_voice_score,
            "task_group_fit_score": task_group_fit_score,
            "claim_alignment_score": claim_alignment_score,
            "param_capability_score": param_capability_score,
            "market_validation_score": market_validation_score,
            "sentiment_polarity": comment_match["sentiment_polarity"],
            "size_tier": sku_input.size_tier,
            "price_band_in_size_tier": sku_input.price_band_in_size_tier,
            "price_percentile_in_size_tier": sku_input.price_percentile_in_size_tier,
            "score_breakdown_json": _json_safe(
                {
                    "user_voice": comment_match,
                    "claim_alignment": claim_match,
                    "param_capability": param_match,
                    "market": _market_snapshot(
                        sku_input.market_profile, sku_input.comparable_market_context
                    ),
                }
            ),
            "status_reason_cn": status_reason_cn,
            "evidence_ids_json": evidence_ids[:80],
            "review_required": relation_status in {REL_DRAG, REL_USER_OBSERVED}
            or market_gate_status == "unknown",
            "review_status": "review_required"
            if relation_status in {REL_DRAG, REL_USER_OBSERVED}
            or market_gate_status == "unknown"
            else "auto_pass",
            "review_reason_json": _json_safe(
                _review_reason(
                    relation_status,
                    market_gate_status,
                    comment_match,
                    claim_match,
                    param_match,
                )
            ),
            "confidence": _confidence(
                market_gate_status,
                user_voice_score,
                claim_alignment_score,
                param_capability_score,
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
            and payload["market_gate_status"] == "matched"
            and payload["battlefield_score"] >= Decimal("0.6800")
        ]
        eligible.sort(
            key=lambda item: (
                item["battlefield_score"],
                item["user_voice_score"],
                item["claim_alignment_score"],
            ),
            reverse=True,
        )
        if eligible:
            eligible[0]["relation_status"] = REL_PRIMARY
            eligible[0]["value_effect"] = _value_effect(
                relation_status=REL_PRIMARY,
                market_gate_status=eligible[0]["market_gate_status"],
                user_voice_score=eligible[0]["user_voice_score"],
                claim_score=eligible[0]["claim_alignment_score"],
                param_score=eligible[0]["param_capability_score"],
            )
            eligible[0]["status_reason_cn"] = eligible[0]["status_reason_cn"].replace(
                "可作为候选战场", "作为主价值战场"
            )
            eligible[0]["result_hash"] = _score_result_hash(
                eligible[0], self.taxonomy.taxonomy_version, self.rule_version
            )

        secondary = [
            payload
            for payload in score_payloads
            if payload["relation_status"] == REL_SECONDARY
        ]
        secondary.sort(key=lambda item: item["battlefield_score"], reverse=True)
        for payload in secondary[2:]:
            payload["relation_status"] = REL_OPPORTUNITY
            payload["value_effect"] = VALUE_BASIC
            payload["status_reason_cn"] = (
                f"{payload['battlefield_name']}证据成立但已超出最多两个辅战场限制，降为机会战场。"
            )
            payload["result_hash"] = _score_result_hash(
                payload, self.taxonomy.taxonomy_version, self.rule_version
            )
        return score_payloads

    def _profile_payload(
        self, sku_input: M11CSkuInput, score_payloads: Sequence[dict[str, Any]]
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
            key=lambda item: item["battlefield_score"],
            reverse=True,
        )[:2]
        opportunities = sorted(
            [
                item
                for item in score_payloads
                if item["relation_status"]
                in {REL_OPPORTUNITY, REL_BRAND_CLAIMED, REL_USER_OBSERVED}
            ],
            key=lambda item: item["battlefield_score"],
            reverse=True,
        )
        drags = sorted(
            [item for item in score_payloads if item["relation_status"] == REL_DRAG],
            key=lambda item: item["battlefield_score"],
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
        battlefield_summary = {
            "primary": _compact_score(primary) if primary else None,
            "secondary": [_compact_score(item) for item in secondary],
            "opportunity": [_compact_score(item) for item in opportunities[:8]],
            "drag_factor": [_compact_score(item) for item in drags[:8]],
            "no_primary_reason_cn": no_primary_reason,
            "user_voice_summary": _user_voice_summary(score_payloads),
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
            "primary_battlefield_code": primary["battlefield_code"]
            if primary
            else None,
            "primary_relation_status": primary["relation_status"] if primary else None,
            "secondary_battlefield_codes_json": [
                item["battlefield_code"] for item in secondary
            ],
            "opportunity_battlefield_codes_json": [
                item["battlefield_code"] for item in opportunities
            ],
            "drag_factor_battlefield_codes_json": [
                item["battlefield_code"] for item in drags
            ],
            "battlefield_summary_json": battlefield_summary,
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
                    if item["relation_status"] != REL_EXCLUDED
                ]
            ),
            "evidence_ids_json": evidence_ids[:100],
            "is_current": True,
        }
        payload["profile_hash"] = stable_hash(
            {
                "sku_code": payload["sku_code"],
                "primary": payload["primary_battlefield_code"],
                "secondary": payload["secondary_battlefield_codes_json"],
                "opportunity": payload["opportunity_battlefield_codes_json"],
                "drag": payload["drag_factor_battlefield_codes_json"],
                "summary": payload["battlefield_summary_json"],
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M11C_PROFILE_HASH_VERSION,
        )
        return payload

    def _graph_payload(
        self,
        sku_inputs: Sequence[M11CSkuInput],
        score_payloads: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        active_scores = [
            item for item in score_payloads if item["relation_status"] != REL_EXCLUDED
        ]
        battlefield_nodes = []
        coverage_summary = {}
        for battlefield in self.battlefields:
            rows = [
                item
                for item in active_scores
                if item["battlefield_code"] == battlefield.battlefield_code
            ]
            status_counts = Counter(item["relation_status"] for item in rows)
            top_skus = sorted(
                rows, key=lambda item: item["battlefield_score"], reverse=True
            )[:20]
            battlefield_nodes.append(
                {
                    "id": battlefield.battlefield_code,
                    "type": "battlefield",
                    "name": battlefield.battlefield_name,
                    "definition": battlefield.definition,
                    "sku_count": len({item["sku_code"] for item in rows}),
                    "status_counts": dict(sorted(status_counts.items())),
                    "primary_task_codes": list(battlefield.primary_task_codes),
                    "primary_target_group_codes": list(
                        battlefield.primary_target_group_codes
                    ),
                    "claim_codes": list(battlefield.claim_codes),
                    "param_codes": list(battlefield.param_codes),
                }
            )
            coverage_summary[battlefield.battlefield_code] = {
                "battlefield_name": battlefield.battlefield_name,
                "sku_count": len({item["sku_code"] for item in rows}),
                "status_counts": dict(sorted(status_counts.items())),
                "top_skus": [_compact_score(item) for item in top_skus],
                "primary_sku_codes": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_PRIMARY
                ],
                "secondary_sku_codes": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_SECONDARY
                ],
                "opportunity_sku_codes": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"]
                    in {REL_OPPORTUNITY, REL_BRAND_CLAIMED, REL_USER_OBSERVED}
                ],
                "drag_factor_sku_codes": [
                    item["sku_code"]
                    for item in rows
                    if item["relation_status"] == REL_DRAG
                ],
            }
        sku_nodes = [
            {
                "id": sku_input.sku_code,
                "type": "sku",
                "model_name": sku_input.model_name,
                "brand_name": sku_input.brand_name,
                "size_tier": sku_input.size_tier,
                "price_band_in_size_tier": sku_input.price_band_in_size_tier,
            }
            for sku_input in sku_inputs
        ]
        edges = [
            {
                "source": item["battlefield_code"],
                "target": item["sku_code"],
                "type": "battlefield_sku",
                "relation_status": item["relation_status"],
                "value_effect": item["value_effect"],
                "score": _decimal_to_float(item["battlefield_score"]),
            }
            for item in active_scores
        ]
        graph_json = {
            "nodes": [*battlefield_nodes, *sku_nodes],
            "edges": edges,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "rule_version": self.rule_version,
        }
        payload = {
            "graph_snapshot_id": _graph_id(
                self.project_id,
                self.batch_id,
                self.taxonomy.taxonomy_version,
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
            "node_count": len(graph_json["nodes"]),
            "edge_count": len(edges),
            "battlefield_count": len(self.battlefields),
            "sku_count": len(sku_inputs),
            "graph_json": graph_json,
            "coverage_summary_json": coverage_summary,
            "is_current": True,
        }
        payload["graph_hash"] = stable_hash(
            {
                "nodes": graph_json["nodes"],
                "edges": graph_json["edges"],
                "coverage_summary": coverage_summary,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M11C_GRAPH_HASH_VERSION,
        )
        return payload


def _bf(
    battlefield_code: str,
    battlefield_name: str,
    definition: str,
    allowed_size_tiers: tuple[str, ...],
    allowed_price_bands: tuple[str, ...],
    primary_task_codes: tuple[str, ...],
    secondary_task_codes: tuple[str, ...],
    primary_target_group_codes: tuple[str, ...],
    comment_subdimension_codes: tuple[str, ...],
    claim_codes: tuple[str, ...],
    param_codes: tuple[str, ...],
    *,
    adjacent_size_tiers: tuple[str, ...] = (),
    adjacent_price_bands: tuple[str, ...] = (),
) -> M11CBattlefieldDefinition:
    return M11CBattlefieldDefinition(
        battlefield_code=battlefield_code,
        battlefield_name=battlefield_name,
        definition=definition,
        allowed_size_tiers=allowed_size_tiers,
        allowed_price_bands=allowed_price_bands,
        primary_task_codes=primary_task_codes,
        secondary_task_codes=secondary_task_codes,
        primary_target_group_codes=primary_target_group_codes,
        comment_subdimension_codes=comment_subdimension_codes,
        claim_codes=claim_codes,
        param_codes=param_codes,
        adjacent_size_tiers=adjacent_size_tiers,
        adjacent_price_bands=adjacent_price_bands,
    )


def _filter_battlefields(
    taxonomy: M11CValueBattlefieldTaxonomy,
    battlefield_codes: Sequence[str],
) -> tuple[M11CBattlefieldDefinition, ...]:
    if not battlefield_codes:
        return taxonomy.battlefields
    code_set = {str(code) for code in battlefield_codes}
    missing = sorted(code_set - set(taxonomy.battlefields_by_code))
    if missing:
        raise ValueError(f"M11C 未找到价值战场 code：{', '.join(missing)}")
    return tuple(
        item for item in taxonomy.battlefields if item.battlefield_code in code_set
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
) -> list[M11CSkuInput]:
    base_inputs: list[tuple[entities.Core3SkuParamProfile, str]] = [
        (profile, _canonical_size_tier(profile)) for profile in param_profiles
    ]
    price_bands = _derive_price_bands(base_inputs, market_profiles)
    comparable_market_contexts = _derive_comparable_market_contexts(
        base_inputs, market_weekly_rows
    )
    result: list[M11CSkuInput] = []
    for profile, size_tier in base_inputs:
        market_profile = market_profiles.get(profile.sku_code)
        price_band, percentile = price_bands.get(profile.sku_code, ("unknown", None))
        result.append(
            M11CSkuInput(
                sku_code=profile.sku_code,
                model_name=profile.model_name
                or (market_profile.model_name if market_profile else None),
                brand_name=(market_profile.brand_name if market_profile else None)
                or (
                    claim_profiles.get(profile.sku_code).brand_name
                    if claim_profiles.get(profile.sku_code)
                    else None
                ),
                param_profile=profile,
                market_profile=market_profile,
                claim_profile=claim_profiles.get(profile.sku_code),
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


def _canonical_size_tier(profile: entities.Core3SkuParamProfile) -> str:
    param_values = profile.param_values_json or {}
    tier = (
        (param_values.get("dimension_tier_profile") or {}).get("size") or ""
    ).strip()
    if tier in ALL_CANONICAL_SIZE_TIERS:
        return tier
    ac_tier = _canonical_ac_size_tier(param_values)
    if ac_tier != "unknown":
        return ac_tier
    size = _param_numeric(param_values, "screen_size_inch")
    if size is None:
        return "unknown"
    if size <= Decimal("45"):
        return "small_32_45"
    if size <= Decimal("59"):
        return "medium_46_59"
    if size <= Decimal("69"):
        return "large_60_69"
    if size <= Decimal("85"):
        return "xlarge_70_85"
    if size >= Decimal("98"):
        return "giant_98_plus"
    return "unknown"


def _canonical_ac_size_tier(param_values: Mapping[str, Any]) -> str:
    dimension_tier = param_values.get("dimension_tier_profile") or {}
    installation = str(
        dimension_tier.get("installation")
        or _param_normalized_text(param_values, "installation_type")
    ).lower()
    horsepower_label = str(dimension_tier.get("horsepower") or "").lower()
    horsepower = _param_numeric(param_values, "horsepower_hp")
    is_floor = "floor" in installation or "柜" in installation
    is_wall = "wall" in installation or "挂" in installation
    if not is_floor and not is_wall:
        custom_label = _param_normalized_text(
            param_values, "installation_hp_segment"
        ) or _param_normalized_text(param_values, "custom_hp_segment")
        custom_label_norm = custom_label.lower()
        is_floor = "floor" in custom_label_norm or "柜" in custom_label_norm
        is_wall = "wall" in custom_label_norm or "挂" in custom_label_norm
    if not is_floor and not is_wall:
        return "unknown"
    if horsepower is None:
        if "hp_1_or_below" in horsepower_label:
            horsepower = Decimal("1.0")
        elif "hp_1_5" in horsepower_label:
            horsepower = Decimal("1.5")
        elif "hp_2" in horsepower_label:
            horsepower = Decimal("2.0")
        elif "hp_3" in horsepower_label:
            horsepower = Decimal("3.0")
        else:
            horsepower = _parse_hp_from_text(
                _param_normalized_text(param_values, "installation_hp_segment")
                or _param_normalized_text(param_values, "custom_hp_segment")
                or _param_normalized_text(param_values, "horsepower_segment")
            )
    if horsepower is None:
        return "unknown"
    if is_floor:
        if horsepower > Decimal("3.0"):
            return "floor_hp_3_plus"
        if horsepower >= Decimal("2.5"):
            return "floor_hp_3"
        return "floor_hp_2"
    if horsepower <= Decimal("1.2"):
        return "wall_hp_1_or_below"
    if horsepower <= Decimal("1.8"):
        return "wall_hp_1_5"
    if horsepower <= Decimal("2.4"):
        return "wall_hp_2"
    return "wall_hp_3"


def _derive_price_bands(
    base_inputs: Sequence[tuple[entities.Core3SkuParamProfile, str]],
    market_profiles: Mapping[str, entities.Core3SkuMarketProfile],
) -> dict[str, tuple[str, Decimal | None]]:
    grouped: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    for profile, size_tier in base_inputs:
        market_profile = market_profiles.get(profile.sku_code)
        price = _decimal(market_profile.price_wavg if market_profile else None)
        if size_tier in ALL_CANONICAL_SIZE_TIERS and price is not None:
            grouped[size_tier].append((profile.sku_code, price))
    result: dict[str, tuple[str, Decimal | None]] = {}
    for values in grouped.values():
        values_sorted = sorted(values, key=lambda item: (item[1], item[0]))
        n = len(values_sorted)
        if n < 2:
            for sku_code, _ in values_sorted:
                result[sku_code] = ("unknown", None)
            continue
        for index, (sku_code, _) in enumerate(values_sorted):
            percentile = Decimal(index) / Decimal(n - 1)
            result[sku_code] = (_price_band(percentile), _quantize4(percentile))
    return result


def _derive_comparable_market_contexts(
    base_inputs: Sequence[tuple[entities.Core3SkuParamProfile, str]],
    weekly_rows: Sequence[entities.Core3CleanMarketWeekly],
) -> dict[str, dict[str, Any]]:
    sku_size_tiers = {
        profile.sku_code: size_tier
        for profile, size_tier in base_inputs
        if size_tier in ALL_CANONICAL_SIZE_TIERS
    }
    if not sku_size_tiers or not weekly_rows:
        return {}

    weekly_by_sku: dict[str, dict[int, dict[str, Decimal]]] = defaultdict(dict)
    for row in weekly_rows:
        sku_code = str(row.sku_code or "")
        if sku_code not in sku_size_tiers:
            continue
        week_index = row.period_week_index
        if week_index is None:
            continue
        volume = _decimal(row.sales_volume) or Decimal("0")
        amount = _decimal(row.sales_amount) or Decimal("0")
        bucket = weekly_by_sku[sku_code].setdefault(
            int(week_index), {"volume": Decimal("0"), "amount": Decimal("0")}
        )
        bucket["volume"] += volume
        bucket["amount"] += amount

    skus_by_tier: dict[str, list[str]] = defaultdict(list)
    for sku_code, size_tier in sku_size_tiers.items():
        if sku_code in weekly_by_sku:
            skus_by_tier[size_tier].append(sku_code)

    result: dict[str, dict[str, Any]] = {}
    for size_tier, sku_codes in skus_by_tier.items():
        for sku_code in sku_codes:
            target_weeks = set(weekly_by_sku.get(sku_code, {}))
            if not target_weeks:
                continue
            target_volume_total = sum(
                (weekly_by_sku[sku_code][week]["volume"] for week in target_weeks),
                Decimal("0"),
            )
            target_amount_total = sum(
                (weekly_by_sku[sku_code][week]["amount"] for week in target_weeks),
                Decimal("0"),
            )
            pairwise_volume_positions: list[Decimal] = []
            pairwise_amount_positions: list[Decimal] = []
            overlap_week_counts: list[int] = []
            sample_peers: list[dict[str, Any]] = []

            for peer_code in sku_codes:
                if peer_code == sku_code:
                    continue
                peer_weeks = set(weekly_by_sku.get(peer_code, {}))
                overlap_weeks = sorted(target_weeks & peer_weeks)
                if not overlap_weeks:
                    continue
                overlap_count = len(overlap_weeks)
                target_overlap_volume = _avg_decimal_raw(
                    [weekly_by_sku[sku_code][week]["volume"] for week in overlap_weeks]
                )
                peer_overlap_volume = _avg_decimal_raw(
                    [weekly_by_sku[peer_code][week]["volume"] for week in overlap_weeks]
                )
                target_overlap_amount = _avg_decimal_raw(
                    [weekly_by_sku[sku_code][week]["amount"] for week in overlap_weeks]
                )
                peer_overlap_amount = _avg_decimal_raw(
                    [weekly_by_sku[peer_code][week]["amount"] for week in overlap_weeks]
                )
                pairwise_volume_positions.append(
                    _pairwise_position(target_overlap_volume, peer_overlap_volume)
                )
                pairwise_amount_positions.append(
                    _pairwise_position(target_overlap_amount, peer_overlap_amount)
                )
                overlap_week_counts.append(overlap_count)
                if len(sample_peers) < 8:
                    sample_peers.append(
                        {
                            "peer_sku_code": peer_code,
                            "overlap_week_count": overlap_count,
                            "target_avg_weekly_volume_on_overlap": _decimal_to_float(
                                _quantize4(target_overlap_volume)
                            ),
                            "peer_avg_weekly_volume_on_overlap": _decimal_to_float(
                                _quantize4(peer_overlap_volume)
                            ),
                            "target_avg_weekly_amount_on_overlap": _decimal_to_float(
                                _quantize4(target_overlap_amount)
                            ),
                            "peer_avg_weekly_amount_on_overlap": _decimal_to_float(
                                _quantize4(peer_overlap_amount)
                            ),
                        }
                    )

            result[sku_code] = {
                "policy_version": COMPARABLE_MARKET_POLICY_VERSION,
                "method": "pairwise_peer_overlap_active_week_average",
                "size_tier": size_tier,
                "size_tier_peer_count": max(0, len(sku_codes) - 1),
                "qualified_peer_count": len(pairwise_volume_positions),
                "target_observed_week_count": len(target_weeks),
                "target_week_start": min(target_weeks),
                "target_week_end": max(target_weeks),
                "target_sales_volume_total_display_only": _decimal_to_float(
                    _quantize4(target_volume_total)
                ),
                "target_sales_amount_total_display_only": _decimal_to_float(
                    _quantize4(target_amount_total)
                ),
                "target_avg_weekly_volume": _decimal_to_float(
                    _quantize4(target_volume_total / Decimal(len(target_weeks)))
                ),
                "target_avg_weekly_amount": _decimal_to_float(
                    _quantize4(target_amount_total / Decimal(len(target_weeks)))
                ),
                "comparable_volume_percentile": _decimal_to_float(
                    _avg_decimal(pairwise_volume_positions)
                ),
                "comparable_amount_percentile": _decimal_to_float(
                    _avg_decimal(pairwise_amount_positions)
                ),
                "min_overlap_week_count": min(overlap_week_counts)
                if overlap_week_counts
                else 0,
                "avg_overlap_week_count": _decimal_to_float(
                    _avg_decimal([Decimal(item) for item in overlap_week_counts])
                ),
                "max_overlap_week_count": max(overlap_week_counts)
                if overlap_week_counts
                else 0,
                "sample_peer_comparisons": sample_peers,
                "note_cn": "销量/销额验证使用同尺寸 SKU 两两重叠在售周的周均表现；累计销量仅用于展示，不参与判断。",
            }
    return result


def _avg_decimal_raw(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _pairwise_position(target_value: Decimal, peer_value: Decimal) -> Decimal:
    if target_value > peer_value:
        return Decimal("1.0000")
    if target_value == peer_value:
        return Decimal("0.5000")
    return Decimal("0.0000")


def _price_band(percentile: Decimal) -> str:
    if percentile < Decimal("0.20"):
        return "low"
    if percentile < Decimal("0.40"):
        return "mid_low"
    if percentile < Decimal("0.65"):
        return "mid"
    if percentile < Decimal("0.85"):
        return "mid_high"
    return "high"


def _market_gate_status(
    sku_input: M11CSkuInput, battlefield: M11CBattlefieldDefinition
) -> str:
    if (
        sku_input.size_tier == "unknown"
        or sku_input.price_band_in_size_tier == "unknown"
    ):
        return "unknown"
    size_ok = sku_input.size_tier in battlefield.allowed_size_tiers
    price_ok = sku_input.price_band_in_size_tier in battlefield.allowed_price_bands
    if size_ok and price_ok:
        return "matched"
    if (
        size_ok
        and sku_input.price_band_in_size_tier in battlefield.adjacent_price_bands
    ) or (price_ok and sku_input.size_tier in battlefield.adjacent_size_tiers):
        return "adjacent"
    return "mismatch"


def _comment_match(
    comment_facts: Sequence[entities.Core3CommentFactAtom],
    battlefield: M11CBattlefieldDefinition,
) -> dict[str, Any]:
    wanted = set(battlefield.comment_subdimension_codes)
    rows = [
        row
        for row in comment_facts
        if row.dimension_type != "service_fulfillment_excluded"
        and (
            row.subdimension_code in wanted
            or _comment_text_matches(row.clean_comment_text, battlefield)
        )
    ]
    polarity_counts = Counter(row.polarity or "neutral" for row in rows)
    positive_count = int(polarity_counts.get("positive", 0))
    negative_count = int(polarity_counts.get("negative", 0))
    mixed_count = int(polarity_counts.get("mixed", 0))
    neutral_count = int(polarity_counts.get("neutral", 0))
    raw_score = (
        Decimal(positive_count) * Decimal("1.00")
        + Decimal(mixed_count) * Decimal("0.75")
        + Decimal(neutral_count) * Decimal("0.45")
        + Decimal(negative_count) * Decimal("0.55")
    ) / Decimal("3")
    if negative_count and negative_count >= positive_count:
        raw_score = max(raw_score, Decimal("0.4500"))
    score = _clamp_decimal(raw_score)
    return {
        "score": score,
        "fact_count": len(rows),
        "positive_count": positive_count,
        "negative_count": negative_count,
        "mixed_count": mixed_count,
        "neutral_count": neutral_count,
        "matched_subdimension_codes": sorted({row.subdimension_code for row in rows}),
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


def _comment_text_matches(
    text: str | None, battlefield: M11CBattlefieldDefinition
) -> bool:
    normalized = str(text or "").lower()
    if not normalized:
        return False
    for token in battlefield.battlefield_name.replace("/", " ").split():
        if token and token.lower() in normalized:
            return True
    return False


def _task_group_fit_score(
    comment_match: Mapping[str, Any], user_voice_score: Decimal, market_gate_status: str
) -> Decimal:
    matched_subdimensions = set(comment_match.get("matched_subdimension_codes") or [])
    if matched_subdimensions & {
        "use_living_room_cinema",
        "use_bedroom",
        "use_gaming_sports",
        "use_casting_online",
        "audience_senior",
        "audience_child_family",
        "audience_rental_room",
        "use_bedroom_sleep",
        "use_living_room_large",
        "use_rental_dorm",
        "use_humid_south",
        "audience_senior_parent",
        "audience_family",
        "audience_child_baby",
        "audience_rental_young",
        "audience_sensitive",
    }:
        return Decimal("0.8000")
    if user_voice_score >= Decimal("0.5500"):
        return Decimal("0.6000")
    if market_gate_status == "matched" and user_voice_score > Decimal("0.0000"):
        return Decimal("0.4500")
    if market_gate_status == "matched":
        return Decimal("0.2500")
    return Decimal("0.0000")


def _claim_match(
    claim_facts: Sequence[entities.Core3SkuClaimFact],
    claim_profile: entities.Core3SkuClaimFactProfile | None,
    battlefield: M11CBattlefieldDefinition,
) -> dict[str, Any]:
    wanted = set(battlefield.claim_codes)
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
    supported_count = len({row.claim_code for row in supported} | profile_claim_codes)
    claimed_count = len({row.claim_code for row in rows} | profile_claim_codes)
    denominator = Decimal(max(1, min(3, len(wanted))))
    score = _clamp_decimal(
        (
            Decimal(supported_count)
            + Decimal(max(0, claimed_count - supported_count)) * Decimal("0.35")
        )
        / denominator
    )
    return {
        "score": score,
        "matched_claim_codes": sorted(
            {row.claim_code for row in rows} | profile_claim_codes
        ),
        "supported_claim_codes": sorted(
            {row.claim_code for row in supported} | profile_claim_codes
        ),
        "unsupported_claim_codes": sorted({row.claim_code for row in unsupported}),
        "evidence_ids": _unique(
            evidence_id
            for row in rows
            for evidence_id in _list_or_empty(row.evidence_ids)
        ),
    }


def _param_match(
    param_profile: entities.Core3SkuParamProfile,
    market_profile: entities.Core3SkuMarketProfile | None,
    battlefield: M11CBattlefieldDefinition,
) -> dict[str, Any]:
    param_values = param_profile.param_values_json or {}
    supported: list[str] = []
    unknown: list[str] = []
    for param_code in battlefield.param_codes:
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
    denominator = Decimal(max(1, min(4, len(battlefield.param_codes))))
    score = _clamp_decimal(Decimal(len(supported)) / denominator)
    return {
        "score": score,
        "supported_param_codes": sorted(set(supported)),
        "unknown_param_codes": sorted(set(unknown)),
    }


def _param_entry_supported(param_code: str, entry: Mapping[str, Any]) -> bool:
    if entry.get("value_presence") == "unknown":
        return False
    value = entry.get("normalized_value")
    numeric = _decimal(entry.get("numeric_value"))
    if param_code == "declared_refresh_rate_hz":
        return numeric is not None and numeric >= Decimal("120")
    if param_code == "declared_brightness_nit_or_band":
        return numeric is not None and numeric >= Decimal("300")
    if param_code == "local_dimming_zone_count":
        return numeric is not None and numeric > Decimal("0")
    if isinstance(value, bool):
        return value
    if numeric is not None:
        return numeric > Decimal("0")
    if isinstance(value, Mapping):
        return any(bool(item) for item in value.values())
    return str(value or "").strip().lower() not in {
        "",
        "-",
        "unknown",
        "none",
        "false",
        "否",
        "无",
        "不支持",
    }


def _market_validation_score(
    market_profile: entities.Core3SkuMarketProfile | None,
    comparable_market_context: Mapping[str, Any] | None = None,
) -> Decimal:
    if comparable_market_context:
        percentiles = [
            _decimal(comparable_market_context.get("comparable_volume_percentile")),
            _decimal(comparable_market_context.get("comparable_amount_percentile")),
        ]
        present = [item for item in percentiles if item is not None]
        if present:
            score = _clamp_decimal(max(present))
            qualified_peer_count = int(
                comparable_market_context.get("qualified_peer_count") or 0
            )
            avg_overlap_week_count = _decimal(
                comparable_market_context.get("avg_overlap_week_count")
            ) or Decimal("0")
            if qualified_peer_count < 2 or avg_overlap_week_count < Decimal("2"):
                return min(score, Decimal("0.4500"))
            return score
    if market_profile is None:
        return Decimal("0.0000")
    percentiles = [
        _decimal(market_profile.volume_percentile_in_size),
        _decimal(market_profile.amount_percentile_in_size),
        _decimal(market_profile.same_pool_volume_percentile),
        _decimal(market_profile.same_pool_amount_percentile),
    ]
    present = [item for item in percentiles if item is not None]
    if present:
        return _clamp_decimal(max(present))
    if _decimal(market_profile.sales_volume_total) and _decimal(
        market_profile.sales_volume_total
    ) > Decimal("0"):
        return Decimal("0.3500")
    return Decimal("0.1500")


def _initial_relation_status(
    *,
    market_gate_status: str,
    score: Decimal,
    user_voice_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    positive_count: int,
    negative_count: int,
) -> str:
    if market_gate_status == "mismatch":
        return REL_EXCLUDED
    if (
        negative_count > 0
        and negative_count >= max(1, positive_count)
        and user_voice_score >= Decimal("0.4000")
    ):
        return REL_DRAG
    if (
        market_gate_status == "matched"
        and score >= Decimal("0.5800")
        and user_voice_score >= Decimal("0.3500")
        and (claim_score >= Decimal("0.3000") or param_score >= Decimal("0.3000"))
    ):
        return REL_SECONDARY
    if user_voice_score >= Decimal("0.5500") and (
        claim_score < Decimal("0.3000") or param_score < Decimal("0.3000")
    ):
        return REL_USER_OBSERVED
    if (
        claim_score >= Decimal("0.5500")
        and param_score >= Decimal("0.4500")
        and user_voice_score < Decimal("0.3500")
    ):
        return REL_BRAND_CLAIMED
    if market_gate_status in {"matched", "adjacent", "unknown"} and score >= Decimal(
        "0.4200"
    ):
        return REL_OPPORTUNITY
    return REL_EXCLUDED


def _value_effect(
    *,
    relation_status: str,
    market_gate_status: str,
    user_voice_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
) -> str:
    if relation_status in {REL_PRIMARY, REL_SECONDARY}:
        if (
            market_gate_status == "matched"
            and user_voice_score >= Decimal("0.5500")
            and claim_score >= Decimal("0.5000")
            and param_score >= Decimal("0.5000")
        ):
            return VALUE_PREMIUM
        return VALUE_BASIC
    if relation_status == REL_BRAND_CLAIMED:
        return VALUE_BRAND_ONLY
    if relation_status == REL_USER_OBSERVED:
        return VALUE_USER_NEED
    if relation_status == REL_DRAG:
        return VALUE_DRAG
    if relation_status == REL_OPPORTUNITY:
        return (
            VALUE_UNMET
            if user_voice_score >= Decimal("0.5000")
            and (claim_score < Decimal("0.3000") or param_score < Decimal("0.3000"))
            else VALUE_BASIC
        )
    return VALUE_NA


def _status_reason_cn(
    battlefield: M11CBattlefieldDefinition,
    *,
    market_gate_status: str,
    relation_status: str,
    user_voice_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    comment_match: Mapping[str, Any],
) -> str:
    if relation_status == REL_EXCLUDED:
        return f"{battlefield.battlefield_name}未成立，主要原因是尺寸价格门槛或证据强度不足。"
    if relation_status == REL_DRAG:
        return f"{battlefield.battlefield_name}有用户需求，但负向评论集中，暂按拖后腿战场处理。"
    if relation_status == REL_BRAND_CLAIMED:
        return f"{battlefield.battlefield_name}厂家卖点和参数有表达，但用户评论验证不足，暂按厂家主打战场处理。"
    if relation_status == REL_USER_OBSERVED:
        return f"{battlefield.battlefield_name}用户评论有明显需求，但卖点或参数支撑不足，暂按用户观察战场处理。"
    return (
        f"{battlefield.battlefield_name}可作为候选战场：市场门槛 {market_gate_status}，"
        f"用户声音 {user_voice_score}，卖点支撑 {claim_score}，参数支撑 {param_score}；"
        f"评论匹配 {comment_match.get('fact_count', 0)} 条。"
    )


def _review_reason(
    relation_status: str,
    market_gate_status: str,
    comment_match: Mapping[str, Any],
    claim_match: Mapping[str, Any],
    param_match: Mapping[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    if market_gate_status == "unknown":
        reasons.append("missing_size_or_price_band")
    if relation_status == REL_DRAG:
        reasons.append("negative_comment_drag_factor")
    if relation_status == REL_USER_OBSERVED:
        reasons.append("comment_strong_claim_or_param_weak")
    if claim_match.get("unsupported_claim_codes"):
        reasons.append("unsupported_claim_codes_present")
    if param_match.get("unknown_param_codes"):
        reasons.append("unknown_param_codes_present")
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
    market_gate_status: str,
    user_voice_score: Decimal,
    claim_score: Decimal,
    param_score: Decimal,
    sku_input: M11CSkuInput,
) -> Decimal:
    domain_count = 0
    if market_gate_status in {"matched", "adjacent"}:
        domain_count += 1
    if user_voice_score > Decimal("0.0000"):
        domain_count += 1
    if claim_score > Decimal("0.0000"):
        domain_count += 1
    if param_score > Decimal("0.0000"):
        domain_count += 1
    if sku_input.market_profile is not None:
        domain_count += 1
    return _clamp_decimal(Decimal(domain_count) / Decimal("5"))


def _sentiment_polarity(
    positive_count: int, negative_count: int, mixed_count: int, neutral_count: int
) -> str:
    if mixed_count and positive_count and negative_count:
        return "mixed"
    if negative_count > positive_count:
        return "negative"
    if positive_count > negative_count:
        return "positive"
    if mixed_count:
        return "mixed"
    if neutral_count:
        return "neutral"
    return "unknown"


def _market_snapshot(
    market_profile: entities.Core3SkuMarketProfile | None,
    comparable_market_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if market_profile is None:
        return (
            {"comparable_market_context": _json_safe(comparable_market_context or {})}
            if comparable_market_context
            else {}
        )
    snapshot = {
        "analysis_window": market_profile.analysis_window,
        "price_wavg": _decimal_to_float(market_profile.price_wavg),
        "sales_volume_total_display_only": _decimal_to_float(
            market_profile.sales_volume_total
        ),
        "sales_amount_total_display_only": _decimal_to_float(
            market_profile.sales_amount_total
        ),
        "volume_percentile_in_size": _decimal_to_float(
            market_profile.volume_percentile_in_size
        ),
        "amount_percentile_in_size": _decimal_to_float(
            market_profile.amount_percentile_in_size
        ),
        "sample_status": market_profile.sample_status,
    }
    if comparable_market_context:
        snapshot["market_validation_policy"] = COMPARABLE_MARKET_POLICY_VERSION
        snapshot["comparable_market_context"] = _json_safe(comparable_market_context)
    else:
        snapshot["market_validation_policy"] = "legacy_full_observed_window_fallback"
    return snapshot


def _compact_score(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        "sku_code": payload.get("sku_code"),
        "battlefield_code": payload.get("battlefield_code"),
        "battlefield_name": payload.get("battlefield_name"),
        "relation_status": payload.get("relation_status"),
        "value_effect": payload.get("value_effect"),
        "battlefield_score": _decimal_to_float(payload.get("battlefield_score")),
        "status_reason_cn": payload.get("status_reason_cn"),
    }


def _no_primary_reason(
    score_payloads: Sequence[Mapping[str, Any]], sku_input: M11CSkuInput
) -> str:
    if (
        sku_input.size_tier == "unknown"
        or sku_input.price_band_in_size_tier == "unknown"
    ):
        return "缺少 M03B 五档尺寸或 M11C 尺寸内价格带，无法高置信判断主价值战场。"
    active = [
        item for item in score_payloads if item["relation_status"] != REL_EXCLUDED
    ]
    if not active:
        return "没有战场同时满足尺寸价格门槛、用户声音和产品支撑。"
    return "有局部机会或厂家表达，但尚未形成用户声音、卖点和参数共同支撑的主价值战场。"


def _user_voice_summary(score_payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    active = [
        item for item in score_payloads if item["user_voice_score"] > Decimal("0.0000")
    ]
    return {
        "matched_battlefield_count": len(active),
        "top_user_voice": [
            _compact_score(item)
            for item in sorted(
                active, key=lambda item: item["user_voice_score"], reverse=True
            )[:5]
        ],
    }


def _claim_param_summary(score_payloads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "claim_strong_battlefield_codes": [
            item["battlefield_code"]
            for item in score_payloads
            if item["claim_alignment_score"] >= Decimal("0.5500")
        ],
        "param_strong_battlefield_codes": [
            item["battlefield_code"]
            for item in score_payloads
            if item["param_capability_score"] >= Decimal("0.5500")
        ],
    }


def _by_sku(rows: Sequence[Any]) -> dict[str, Any]:
    return {row.sku_code: row for row in rows}


def _group_by_sku(rows: Sequence[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[row.sku_code].append(row)
    return grouped


def _param_numeric(param_values: Mapping[str, Any], param_code: str) -> Decimal | None:
    entry = param_values.get(param_code)
    if not isinstance(entry, Mapping):
        return None
    return _decimal(entry.get("numeric_value") or entry.get("normalized_value"))


def _param_normalized_text(param_values: Mapping[str, Any], param_code: str) -> str:
    entry = param_values.get(param_code)
    if not isinstance(entry, Mapping):
        return ""
    return str(
        entry.get("normalized_value")
        or entry.get("value_text")
        or entry.get("raw_param_value")
        or ""
    ).strip()


def _parse_hp_from_text(value: str | None) -> Decimal | None:
    text = str(value or "")
    if not text:
        return None
    if "1匹半" in text:
        return Decimal("1.5")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:HP|hp|匹)", text)
    if match:
        return _decimal(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        return _decimal(match.group(1))
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _clamp_decimal(value: Decimal) -> Decimal:
    return _quantize4(max(Decimal("0.0000"), min(Decimal("1.0000"), value)))


def _quantize4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _avg_decimal(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.0000")
    return _quantize4(sum(values, Decimal("0.0000")) / Decimal(len(values)))


def _list_or_empty(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _unique(values: Sequence[Any] | Any) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if value is None:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _decimal_to_float(value: Any) -> float | None:
    decimal_value = _decimal(value)
    return float(decimal_value) if decimal_value is not None else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


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
        version=M11C_PROFILE_ID_HASH_VERSION,
    )[:120]


def _score_id(
    project_id: str,
    batch_id: str,
    taxonomy_version: str,
    sku_code: str,
    battlefield_code: str,
    rule_version: str,
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "sku_code": sku_code,
            "battlefield_code": battlefield_code,
            "rule_version": rule_version,
        },
        version=M11C_SCORE_ID_HASH_VERSION,
    )[:120]


def _score_result_hash(
    payload: Mapping[str, Any], taxonomy_version: str, rule_version: str
) -> str:
    return stable_hash(
        {
            "sku_code": payload["sku_code"],
            "battlefield_code": payload["battlefield_code"],
            "relation_status": payload["relation_status"],
            "value_effect": payload["value_effect"],
            "battlefield_score": payload["battlefield_score"],
            "market_gate_status": payload["market_gate_status"],
            "score_breakdown_json": payload["score_breakdown_json"],
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
        },
        version=M11C_SCORE_HASH_VERSION,
    )


def _graph_id(
    project_id: str, batch_id: str, taxonomy_version: str, rule_version: str
) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
        },
        version=M11C_GRAPH_ID_HASH_VERSION,
    )[:120]


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
        module_code=Core3ModuleCode.M11C,
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
        module_code=Core3ModuleCode.M11C,
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
