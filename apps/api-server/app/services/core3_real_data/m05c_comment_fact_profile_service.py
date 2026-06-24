"""M05C SKU comment fact profiles and comment-dimension coverage.

M05C consumes M02 comment-sentence evidence plus the current M03B parameter
profile and M04C claim facts. It does not create the category taxonomy; the
taxonomy is a published category asset prepared outside this runner.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

import httpx
from sqlalchemy import delete, func, select
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
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_MODULE_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_extraction_repositories import (
    ParamRepositoryHashConflictError,
    ParamRepositoryWriteResult,
)
from app.services.core3_real_data.repositories import Core3BaseRepository, Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


M05C_PROFILE_ID_HASH_VERSION = "m05c-comment-profile-id-v1"
M05C_PROFILE_HASH_VERSION = "m05c-comment-profile-v1"
M05C_FACT_ID_HASH_VERSION = "m05c-comment-fact-id-v1"
M05C_FACT_HASH_VERSION = "m05c-comment-fact-v1"
M05C_COVERAGE_ID_HASH_VERSION = "m05c-comment-coverage-id-v1"
M05C_COVERAGE_HASH_VERSION = "m05c-comment-coverage-v1"
M05C_REVIEW_ID_HASH_VERSION = "m05c-comment-review-id-v1"

DIMENSION_TYPE_PRODUCT = "product_experience"
DIMENSION_TYPE_AUDIENCE = "audience_signal"
DIMENSION_TYPE_USE_CASE = "use_case_signal"
DIMENSION_TYPE_BRAND = "brand_power_signal"
DIMENSION_TYPE_COMPETITOR = "competitor_comparison_signal"
DIMENSION_TYPE_SERVICE = "service_fulfillment_excluded"
DIMENSION_TYPE_PRODUCT_RISK = "product_risk"
DIMENSION_TYPE_PRICE_VALUE = "price_value"
DIMENSION_TYPE_QUALITY_REVIEW = "quality_review"

POLARITY_POSITIVE = "positive"
POLARITY_NEGATIVE = "negative"
POLARITY_MIXED = "mixed"
POLARITY_NEUTRAL = "neutral"

RELATION_SUPPORTS = "supports_sku_param_claim"
RELATION_CONTRADICTS = "contradicts_sku_param_claim"
RELATION_MENTION_ONLY = "comment_signal_only"
RELATION_SERVICE_EXCLUDED = "service_excluded"

LLM_MODE_AUTO = "auto"
LLM_MODE_REQUIRED = "required"
LLM_MODE_OFF = "off"
M05C_DEFAULT_LLM_BATCH_SIZE = 20
M05C_DEFAULT_LLM_MODEL = "deepseek-v4-pro"
M05C_DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"


@dataclass(frozen=True)
class M05CSubdimensionDefinition:
    subdimension_code: str
    subdimension_name: str
    dimension_code: str
    dimension_name: str
    dimension_type: str
    patterns: tuple[str, ...]
    linked_param_codes: tuple[str, ...] = ()
    linked_claim_codes: tuple[str, ...] = ()
    rule_summary: str = ""


@dataclass(frozen=True)
class M05CDimensionDefinition:
    dimension_code: str
    dimension_name: str
    dimension_type: str
    rule_summary: str


@dataclass(frozen=True)
class M05CCommentTaxonomy:
    taxonomy_version: str
    product_category: str
    product_category_label_cn: str
    raw_category_label_cn: str
    sku_code_prefix: str
    dimensions: tuple[M05CDimensionDefinition, ...]
    subdimensions: tuple[M05CSubdimensionDefinition, ...]

    @property
    def dimensions_by_code(self) -> dict[str, M05CDimensionDefinition]:
        return {dimension.dimension_code: dimension for dimension in self.dimensions}

    @property
    def subdimensions_by_code(self) -> dict[str, M05CSubdimensionDefinition]:
        return {item.subdimension_code: item for item in self.subdimensions}


@dataclass(frozen=True)
class M05CCommentRecord:
    sku_code: str
    model_name: str | None
    brand_name: str | None
    comment_text: str
    raw_comment_text: str | None = None
    source_comment_key: str | None = None
    source_comment_id: str | None = None
    evidence_id: str | None = None
    sentence_seq: int | None = None
    sample_status: str | None = None


@dataclass(frozen=True)
class M05CLlmAnnotation:
    source_comment_key: str
    subdimension_codes: tuple[str, ...]
    polarity: str | None = None
    confidence: float | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class M05CLlmExtractionResult:
    annotations: dict[str, M05CLlmAnnotation]
    stats: dict[str, Any]
    warnings: list[str]


@dataclass(frozen=True)
class M05CWritePayload:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M05CServiceResult:
    input_count: int
    sku_profile_count: int
    comment_fact_count: int
    comment_coverage_count: int
    review_issue_count: int
    matched_sentence_count: int
    service_excluded_sentence_count: int
    contradicted_fact_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item["created_count"] for item in self.write_summary.values())


def tv_comment_fact_taxonomy_v0_1() -> M05CCommentTaxonomy:
    dimensions = (
        _dimension("picture_screen_experience", "画质屏幕体验", DIMENSION_TYPE_PRODUCT, "评价清晰度、亮度、色彩、控光、护眼和运动画面。"),
        _dimension("audio_cinema_experience", "音响影音体验", DIMENSION_TYPE_PRODUCT, "评价音质、声场和观影沉浸感。"),
        _dimension("system_interaction_experience", "系统交互体验", DIMENSION_TYPE_PRODUCT, "评价系统流畅、广告、语音、投屏和连接体验。"),
        _dimension("gaming_motion_experience", "游戏运动体验", DIMENSION_TYPE_PRODUCT, "评价高刷、游戏、运动场景和低延迟体验。"),
        _dimension("appearance_installation_space", "外观安装空间", DIMENSION_TYPE_PRODUCT, "评价尺寸适配、超薄、贴墙和外观空间体验。"),
        _dimension("price_value_perception", "价格价值感知", DIMENSION_TYPE_PRODUCT, "评价价格、性价比、值得买和促销价值感。"),
        _dimension("audience_signal", "人群信号", DIMENSION_TYPE_AUDIENCE, "识别老人、儿童、家庭、租房等目标客群线索。"),
        _dimension("use_case_signal", "用途信号", DIMENSION_TYPE_USE_CASE, "识别客厅影院、卧室、游戏、投屏、体育等用户任务线索。"),
        _dimension("brand_power_signal", "品牌力信号", DIMENSION_TYPE_BRAND, "识别本品牌信任、复购、推荐等品牌力表现。"),
        _dimension("competitor_comparison_signal", "竞品对比信号", DIMENSION_TYPE_COMPETITOR, "识别评论中提及的其他品牌、替换来源和直接比较。"),
        _dimension("service_fulfillment_excluded", "服务履约排除项", DIMENSION_TYPE_SERVICE, "识别送装、售后、物流等服务履约内容，不进入商品事实分析。"),
    )
    subdimensions = (
        _sub(
            "picture_clarity_resolution",
            "清晰度/分辨率",
            "picture_screen_experience",
            "画质屏幕体验",
            DIMENSION_TYPE_PRODUCT,
            ("清晰", "高清", "4k", "8k", "分辨率", "细腻", "画质", "画面", "图像"),
            linked_param_codes=("resolution_class", "display_technology_family", "display_tech_class"),
            linked_claim_codes=("tv_claim_miniled_display", "tv_claim_oled_self_lit"),
        ),
        _sub(
            "picture_brightness_hdr",
            "亮度/HDR",
            "picture_screen_experience",
            "画质屏幕体验",
            DIMENSION_TYPE_PRODUCT,
            ("亮度", "hdr", "刺眼", "暗", "太亮", "阳光", "反光"),
            linked_param_codes=("hdr_support_flag", "declared_brightness_nit_or_band"),
            linked_claim_codes=("tv_claim_hdr_high_brightness", "tv_claim_eye_care_display"),
        ),
        _sub(
            "picture_color_accuracy",
            "色彩还原",
            "picture_screen_experience",
            "画质屏幕体验",
            DIMENSION_TYPE_PRODUCT,
            ("色彩", "颜色", "色域", "色准", "偏色", "鲜艳", "真实"),
            linked_param_codes=("color_gamut_ratio", "high_color_gamut_flag", "quantum_dot_flag"),
            linked_claim_codes=("tv_claim_wide_color_accuracy", "tv_claim_qd_miniled_display"),
        ),
        _sub(
            "picture_local_dimming_black",
            "分区控光/黑位",
            "picture_screen_experience",
            "画质屏幕体验",
            DIMENSION_TYPE_PRODUCT,
            ("分区", "控光", "黑位", "漏光", "光晕", "背光"),
            linked_param_codes=("local_dimming_zone_count", "backlight_subtype"),
            linked_claim_codes=("tv_claim_local_dimming", "tv_claim_miniled_display"),
        ),
        _sub(
            "picture_eye_care_reflection",
            "护眼/防反光",
            "picture_screen_experience",
            "画质屏幕体验",
            DIMENSION_TYPE_PRODUCT,
            ("护眼", "蓝光", "频闪", "不累眼", "累眼", "反光", "刺眼"),
            linked_param_codes=("hdr_support_flag", "declared_brightness_nit_or_band", "declared_refresh_rate_hz"),
            linked_claim_codes=("tv_claim_eye_care_display",),
        ),
        _sub(
            "audio_quality",
            "音质表现",
            "audio_cinema_experience",
            "音响影音体验",
            DIMENSION_TYPE_PRODUCT,
            ("音质", "音响", "声音", "低音", "喇叭", "杜比", "环绕", "影院"),
            linked_param_codes=("speaker_power_w", "speaker_system", "dolby_audio_flag"),
            linked_claim_codes=("tv_claim_speaker_sound", "tv_claim_dolby_audio_video", "tv_claim_theater_scene"),
        ),
        _sub(
            "system_smooth_ads",
            "系统流畅/广告",
            "system_interaction_experience",
            "系统交互体验",
            DIMENSION_TYPE_PRODUCT,
            ("系统", "流畅", "不卡", "卡顿", "开机", "广告", "内存", "运行"),
            linked_param_codes=("processor_chip_model", "memory_capacity_gb", "storage_capacity_gb"),
            linked_claim_codes=("tv_claim_chip_performance", "tv_claim_memory_storage"),
        ),
        _sub(
            "interaction_voice_casting",
            "语音/投屏/互联",
            "system_interaction_experience",
            "系统交互体验",
            DIMENSION_TYPE_PRODUCT,
            ("语音", "遥控", "投屏", "wifi", "蓝牙", "互联", "智能家居", "家电联动"),
            linked_param_codes=("voice_recognition_flag", "wifi_support_flag", "bluetooth_support_flag", "smart_home_iot_flag"),
            linked_claim_codes=("tv_claim_voice_control", "tv_claim_smart_home_iot", "tv_claim_camera_interaction"),
        ),
        _sub(
            "gaming_high_refresh_motion",
            "高刷游戏/运动流畅",
            "gaming_motion_experience",
            "游戏运动体验",
            DIMENSION_TYPE_PRODUCT,
            ("游戏", "高刷", "刷新率", "120hz", "144hz", "240hz", "电竞", "拖影", "球赛", "体育"),
            linked_param_codes=("declared_refresh_rate_hz", "hdmi_version_mix", "hdmi_2_1_port_count"),
            linked_claim_codes=("tv_claim_high_refresh_rate", "tv_claim_gaming_low_latency", "tv_claim_hdmi21_connectivity"),
        ),
        _sub(
            "appearance_size_fit",
            "尺寸/空间适配",
            "appearance_installation_space",
            "外观安装空间",
            DIMENSION_TYPE_PRODUCT,
            ("尺寸", "大小", "客厅", "卧室", "距离", "墙", "空间", "屏幕大"),
            linked_param_codes=("screen_size_inch", "size_segment", "wall_mount_fit_flag"),
            linked_claim_codes=("tv_claim_large_screen_immersive", "tv_claim_flush_wall_mount"),
        ),
        _sub(
            "appearance_slim_wall",
            "超薄/贴墙/外观",
            "appearance_installation_space",
            "外观安装空间",
            DIMENSION_TYPE_PRODUCT,
            ("超薄", "薄", "贴墙", "无缝", "全面屏", "边框", "颜值", "外观"),
            linked_param_codes=("thin_body_flag", "flush_wall_mount_flag", "full_screen_design_flag"),
            linked_claim_codes=("tv_claim_flush_wall_mount", "tv_claim_slim_full_screen"),
        ),
        _sub(
            "value_price",
            "价格/性价比",
            "price_value_perception",
            "价格价值感知",
            DIMENSION_TYPE_PRODUCT,
            ("价格", "便宜", "贵", "划算", "性价比", "值得", "优惠", "促销", "不值"),
            linked_claim_codes=("tv_claim_value_price",),
        ),
        _sub("audience_senior", "老人/长辈", "audience_signal", "人群信号", DIMENSION_TYPE_AUDIENCE, ("老人", "父母", "爸妈", "长辈", "老年")),
        _sub("audience_child_family", "儿童/家庭", "audience_signal", "人群信号", DIMENSION_TYPE_AUDIENCE, ("孩子", "儿童", "小孩", "一家", "家庭", "全家")),
        _sub("audience_rental_room", "租房/小空间", "audience_signal", "人群信号", DIMENSION_TYPE_AUDIENCE, ("租房", "出租屋", "宿舍", "小房间", "卧室")),
        _sub("use_living_room_cinema", "客厅观影", "use_case_signal", "用途信号", DIMENSION_TYPE_USE_CASE, ("客厅", "观影", "电影", "影院", "追剧", "大屏")),
        _sub("use_bedroom", "卧室使用", "use_case_signal", "用途信号", DIMENSION_TYPE_USE_CASE, ("卧室", "房间", "睡前", "床")),
        _sub("use_gaming_sports", "游戏/体育", "use_case_signal", "用途信号", DIMENSION_TYPE_USE_CASE, ("游戏", "电竞", "switch", "ps5", "球赛", "体育", "世界杯")),
        _sub("use_casting_online", "投屏/在线视频", "use_case_signal", "用途信号", DIMENSION_TYPE_USE_CASE, ("投屏", "网课", "视频", "会员", "电视盒子")),
        _sub("brand_trust", "本品牌信任", "brand_power_signal", "品牌力信号", DIMENSION_TYPE_BRAND, ("大品牌", "老品牌", "老牌", "信赖", "信任", "相信", "质量有保证", "质量保证", "值得购买", "放心购买", "靠谱")),
        _sub("brand_repurchase", "复购/再次购买", "brand_power_signal", "品牌力信号", DIMENSION_TYPE_BRAND, ("复购", "再次购买", "第二台", "一直用", "用了很多年", "回购")),
        _sub("brand_recommendation", "推荐/口碑", "brand_power_signal", "品牌力信号", DIMENSION_TYPE_BRAND, ("推荐", "朋友推荐", "口碑", "值得推荐", "种草")),
        _sub("competitor_compare", "竞品比较", "competitor_comparison_signal", "竞品对比信号", DIMENSION_TYPE_COMPETITOR, ("比索尼", "比三星", "比小米", "比tcl", "比海信", "比创维", "对比", "竞品")),
        _sub("replacement_source", "替换来源", "competitor_comparison_signal", "竞品对比信号", DIMENSION_TYPE_COMPETITOR, ("换掉", "替换", "原来", "之前用", "上一台")),
        _sub(
            "service_delivery_install",
            "送装/物流/售后",
            "service_fulfillment_excluded",
            "服务履约排除项",
            DIMENSION_TYPE_SERVICE,
            ("安装", "送货", "物流", "快递", "师傅", "客服", "售后", "上门", "发货"),
        ),
    )
    return M05CCommentTaxonomy(
        taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
        product_category="TV",
        product_category_label_cn="彩电",
        raw_category_label_cn="彩电",
        sku_code_prefix="TV",
        dimensions=dimensions,
        subdimensions=subdimensions,
    )


def ac_comment_fact_taxonomy_v0_1() -> M05CCommentTaxonomy:
    dimensions = (
        _dimension("temperature_effect_experience", "冷暖效果与温度响应", DIMENSION_TYPE_PRODUCT, "评价制冷、制热、速冷速热、恒温和宽温域体验。"),
        _dimension("energy_cost_experience", "能效、电费与长期使用成本", DIMENSION_TYPE_PRODUCT, "评价能效等级、APF、省电、电费和长期使用成本。"),
        _dimension("airflow_comfort_experience", "送风舒适与覆盖", DIMENSION_TYPE_PRODUCT, "评价风量、扫风、覆盖、柔风和防直吹体验。"),
        _dimension("noise_sleep_experience", "静音与睡眠体验", DIMENSION_TYPE_PRODUCT, "评价运行噪音、夜间卧室和睡眠体验。"),
        _dimension("health_clean_air_experience", "健康洁净空气", DIMENSION_TYPE_PRODUCT, "评价新风、净化、除菌、自清洁和异味空气体验。"),
        _dimension("humidity_control_experience", "除湿与湿度控制", DIMENSION_TYPE_PRODUCT, "评价除湿、防潮、干爽和湿度舒适体验。"),
        _dimension("smart_control_experience", "智控交互体验", DIMENSION_TYPE_PRODUCT, "评价 APP、语音、遥控、WiFi、远程和智能模式体验。"),
        _dimension("appearance_installation_space", "外观、安装形态与空间适配", DIMENSION_TYPE_PRODUCT, "评价外观、挂机柜机、占地、尺寸、安装位置和面积适配。"),
        _dimension("quality_reliability_risk", "质量稳定性与产品风险", DIMENSION_TYPE_PRODUCT_RISK, "识别耐用、故障、漏水、异响和核心部件风险。"),
        _dimension("price_value_perception", "价格、补贴与价值感知", DIMENSION_TYPE_PRICE_VALUE, "评价价格、性价比、优惠、国补和同价位价值感。"),
        _dimension("audience_signal", "人群线索", DIMENSION_TYPE_AUDIENCE, "识别老人、儿童、家庭、租房、敏感人群等购买或使用者线索。"),
        _dimension("use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, "识别卧室、客厅、租房、办公、潮湿和冬夏冷暖场景。"),
        _dimension("brand_power_signal", "品牌力与复购推荐", DIMENSION_TYPE_BRAND, "识别品牌信任、复购、推荐、长期使用和品牌情绪。"),
        _dimension("competitor_comparison_signal", "竞品比较与替换来源", DIMENSION_TYPE_COMPETITOR, "识别跨品牌比较、旧机替换、同价位比较和能力对比。"),
        _dimension("service_fulfillment_excluded", "服务履约隔离维度", DIMENSION_TYPE_SERVICE, "识别物流、安装、客服、售后等服务履约内容，不进入商品事实支撑。"),
        _dimension("template_campaign_review", "模板/营销文案复核维度", DIMENSION_TYPE_QUALITY_REVIEW, "识别疑似营销稿、模板化长句和平台活动宣传，进入降权或复核。"),
    )
    subdimensions = (
        _sub(
            "cooling_effect",
            "制冷效果",
            "temperature_effect_experience",
            "冷暖效果与温度响应",
            DIMENSION_TYPE_PRODUCT,
            ("制冷", "凉快", "降温", "冷气", "冷得快", "制冷效果", "冷量"),
            linked_param_codes=("cooling_capacity_w", "horsepower_hp", "heat_cool_mode"),
            linked_claim_codes=("ac_claim_fast_cooling_heating",),
        ),
        _sub(
            "heating_effect",
            "制热效果",
            "temperature_effect_experience",
            "冷暖效果与温度响应",
            DIMENSION_TYPE_PRODUCT,
            ("制热", "暖和", "升温", "热风", "冬天", "制热效果", "暖气"),
            linked_param_codes=("heating_capacity_w", "heating_function_flag", "heat_cool_mode"),
            linked_claim_codes=("ac_claim_fast_cooling_heating", "ac_claim_wide_temperature_operation"),
        ),
        _sub(
            "fast_cooling_heating",
            "速冷速热",
            "temperature_effect_experience",
            "冷暖效果与温度响应",
            DIMENSION_TYPE_PRODUCT,
            ("速冷", "速热", "很快凉", "很快热", "几分钟", "一会儿", "见效快", "开机就"),
            linked_param_codes=("cooling_capacity_w", "heating_capacity_w", "horsepower_hp"),
            linked_claim_codes=("ac_claim_fast_cooling_heating",),
        ),
        _sub(
            "temperature_stability",
            "温度稳定/控温",
            "temperature_effect_experience",
            "冷暖效果与温度响应",
            DIMENSION_TYPE_PRODUCT,
            ("恒温", "控温", "温控", "忽冷忽热", "过冷", "过热", "自动模式"),
            linked_param_codes=("inverter_flag", "smart_sensing_flag"),
            linked_claim_codes=("ac_claim_precision_temperature_control",),
        ),
        _sub(
            "wide_temperature_operation",
            "极端环境/宽温域",
            "temperature_effect_experience",
            "冷暖效果与温度响应",
            DIMENSION_TYPE_PRODUCT,
            ("高温", "低温", "极寒", "极热", "宽温", "外机环境", "严寒", "酷暑"),
            linked_claim_codes=("ac_claim_wide_temperature_operation",),
        ),
        _sub(
            "energy_grade_apf",
            "一级能效/APF",
            "energy_cost_experience",
            "能效、电费与长期使用成本",
            DIMENSION_TYPE_PRODUCT,
            ("一级能效", "新一级", "apf", "能效比", "能效等级"),
            linked_param_codes=("energy_grade_normalized", "energy_efficiency_ratio", "inverter_flag"),
            linked_claim_codes=("ac_claim_energy_efficiency_apf",),
        ),
        _sub(
            "energy_saving_usage",
            "省电体验",
            "energy_cost_experience",
            "能效、电费与长期使用成本",
            DIMENSION_TYPE_PRODUCT,
            ("省电", "节能", "耗电低", "eco", "省电模式", "变频", "不费电"),
            linked_param_codes=("energy_grade_normalized", "energy_efficiency_ratio", "inverter_flag"),
            linked_claim_codes=("ac_claim_energy_efficiency_apf", "ac_claim_ai_energy_saving"),
        ),
        _sub(
            "electricity_cost",
            "电费成本",
            "energy_cost_experience",
            "能效、电费与长期使用成本",
            DIMENSION_TYPE_PRODUCT,
            ("电费", "几度电", "一晚", "每月", "长期成本", "用电", "耗电量"),
            linked_claim_codes=("ac_claim_energy_efficiency_apf", "ac_claim_price_value_subsidy"),
        ),
        _sub(
            "energy_saving_negative",
            "省电反证",
            "energy_cost_experience",
            "能效、电费与长期使用成本",
            DIMENSION_TYPE_PRODUCT,
            ("不省电", "耗电", "费电", "电费高", "耗电大"),
            linked_param_codes=("energy_grade_normalized", "energy_efficiency_ratio"),
            linked_claim_codes=("ac_claim_energy_efficiency_apf", "ac_claim_ai_energy_saving"),
        ),
        _sub(
            "airflow_volume_coverage",
            "风量覆盖",
            "airflow_comfort_experience",
            "送风舒适与覆盖",
            DIMENSION_TYPE_PRODUCT,
            ("风量", "风大", "循环风", "全屋", "覆盖", "客厅", "大空间", "送风远"),
            linked_param_codes=("airflow_volume_m3h", "installation_type", "horsepower_hp"),
            linked_claim_codes=("ac_claim_large_airflow_coverage",),
        ),
        _sub(
            "airflow_even_swing",
            "出风均匀/扫风",
            "airflow_comfort_experience",
            "送风舒适与覆盖",
            DIMENSION_TYPE_PRODUCT,
            ("出风", "扫风", "上下风", "左右风", "角落", "均匀", "风道"),
            linked_param_codes=("airflow_volume_m3h", "comfort_airflow_flag"),
            linked_claim_codes=("ac_claim_large_airflow_coverage",),
        ),
        _sub(
            "soft_wind_no_direct",
            "柔风不直吹",
            "airflow_comfort_experience",
            "送风舒适与覆盖",
            DIMENSION_TYPE_PRODUCT,
            ("柔风", "无风感", "不直吹", "防直吹", "风感舒服", "冷风不直吹"),
            linked_param_codes=("comfort_airflow_flag",),
            linked_claim_codes=("ac_claim_soft_wind_no_direct",),
        ),
        _sub(
            "airflow_negative",
            "风感负向",
            "airflow_comfort_experience",
            "送风舒适与覆盖",
            DIMENSION_TYPE_PRODUCT,
            ("风小", "风太硬", "吹得头疼", "不均匀", "吹不到", "风不大"),
            linked_param_codes=("airflow_volume_m3h", "comfort_airflow_flag"),
            linked_claim_codes=("ac_claim_large_airflow_coverage", "ac_claim_soft_wind_no_direct"),
        ),
        _sub(
            "quiet_positive",
            "静音正向",
            "noise_sleep_experience",
            "静音与睡眠体验",
            DIMENSION_TYPE_PRODUCT,
            ("静音", "安静", "声音小", "低噪", "不吵", "没噪音"),
            linked_param_codes=("inverter_flag",),
            linked_claim_codes=("ac_claim_quiet_sleep",),
        ),
        _sub(
            "sleep_scene",
            "睡眠场景",
            "noise_sleep_experience",
            "静音与睡眠体验",
            DIMENSION_TYPE_PRODUCT,
            ("卧室", "夜间", "晚上", "睡觉", "睡眠", "休息", "不影响睡眠"),
            linked_claim_codes=("ac_claim_quiet_sleep", "ac_claim_soft_wind_no_direct"),
        ),
        _sub(
            "noise_risk",
            "噪音风险",
            "noise_sleep_experience",
            "静音与睡眠体验",
            DIMENSION_TYPE_PRODUCT,
            ("噪音", "声音大", "异响", "外机响", "吵", "轰鸣", "震动"),
            linked_param_codes=("inverter_flag",),
            linked_claim_codes=("ac_claim_quiet_sleep", "ac_claim_durability_core_material"),
        ),
        _sub(
            "self_cleaning",
            "自清洁/自洁",
            "health_clean_air_experience",
            "健康洁净空气",
            DIMENSION_TYPE_PRODUCT,
            ("自清洁", "自洁", "内机自洁", "高温清洁", "56", "清洁省心"),
            linked_param_codes=("self_cleaning_flag",),
            linked_claim_codes=("ac_claim_self_cleaning",),
        ),
        _sub(
            "purification_antibacterial",
            "净化除菌",
            "health_clean_air_experience",
            "健康洁净空气",
            DIMENSION_TYPE_PRODUCT,
            ("净化", "杀菌", "除菌", "抗菌", "防霉", "pm2.5", "空气杀菌"),
            linked_param_codes=("purification_flag",),
            linked_claim_codes=("ac_claim_purification_antibacterial",),
        ),
        _sub(
            "fresh_air_ventilation",
            "新风换气",
            "health_clean_air_experience",
            "健康洁净空气",
            DIMENSION_TYPE_PRODUCT,
            ("新风", "换气", "鲜氧", "空气流通", "通风", "空气新鲜"),
            linked_param_codes=("fresh_air_flag",),
            linked_claim_codes=("ac_claim_fresh_air",),
        ),
        _sub(
            "odor_mold_risk",
            "异味/霉味",
            "health_clean_air_experience",
            "健康洁净空气",
            DIMENSION_TYPE_PRODUCT,
            ("异味", "霉味", "味道", "不清新", "发霉", "臭味"),
            linked_param_codes=("self_cleaning_flag", "purification_flag"),
            linked_claim_codes=("ac_claim_self_cleaning", "ac_claim_purification_antibacterial"),
        ),
        _sub(
            "dehumidification",
            "独立除湿",
            "humidity_control_experience",
            "除湿与湿度控制",
            DIMENSION_TYPE_PRODUCT,
            ("除湿", "抽湿", "独立除湿", "干爽", "湿度"),
            linked_claim_codes=("ac_claim_humidity_dehumidification",),
        ),
        _sub(
            "humid_weather",
            "潮湿环境",
            "humidity_control_experience",
            "除湿与湿度控制",
            DIMENSION_TYPE_PRODUCT,
            ("潮湿", "梅雨", "回南天", "防潮", "不闷"),
            linked_claim_codes=("ac_claim_humidity_dehumidification",),
        ),
        _sub(
            "smart_app_remote",
            "APP/远程",
            "smart_control_experience",
            "智控交互体验",
            DIMENSION_TYPE_PRODUCT,
            ("app", "手机", "远程", "wifi", "联网", "小程序"),
            linked_param_codes=("wifi_control_flag",),
            linked_claim_codes=("ac_claim_smart_app_voice_iot",),
        ),
        _sub(
            "voice_iot",
            "语音/生态",
            "smart_control_experience",
            "智控交互体验",
            DIMENSION_TYPE_PRODUCT,
            ("语音", "小爱", "米家", "天猫精灵", "智能家居", "生态"),
            linked_param_codes=("voice_control_flag", "smart_sensing_flag"),
            linked_claim_codes=("ac_claim_smart_app_voice_iot",),
        ),
        _sub(
            "remote_panel_easy_use",
            "遥控/面板易用",
            "smart_control_experience",
            "智控交互体验",
            DIMENSION_TYPE_PRODUCT,
            ("遥控", "面板", "操作简单", "老人会用", "按键", "控制方便"),
            linked_claim_codes=("ac_claim_smart_app_voice_iot",),
        ),
        _sub(
            "smart_negative",
            "交互反证",
            "smart_control_experience",
            "智控交互体验",
            DIMENSION_TYPE_PRODUCT,
            ("连接失败", "app难用", "遥控不灵", "联网失败", "自动模式不舒服"),
            linked_param_codes=("wifi_control_flag", "voice_control_flag", "smart_sensing_flag"),
            linked_claim_codes=("ac_claim_smart_app_voice_iot", "ac_claim_ai_energy_saving"),
        ),
        _sub(
            "appearance_design",
            "外观颜值",
            "appearance_installation_space",
            "外观、安装形态与空间适配",
            DIMENSION_TYPE_PRODUCT,
            ("外观", "好看", "颜值", "颜色", "质感", "漂亮", "简洁"),
            linked_param_codes=("indoor_unit_dimensions_mm", "product_type_combo"),
            linked_claim_codes=("ac_claim_installation_space_design",),
        ),
        _sub(
            "installation_form",
            "安装形态",
            "appearance_installation_space",
            "外观、安装形态与空间适配",
            DIMENSION_TYPE_PRODUCT,
            ("挂机", "柜机", "立柜", "移动空调", "外机", "内机", "挂墙"),
            linked_param_codes=("installation_type", "product_type_combo"),
            linked_claim_codes=("ac_claim_installation_space_design",),
        ),
        _sub(
            "space_fit_area",
            "空间/面积适配",
            "appearance_installation_space",
            "外观、安装形态与空间适配",
            DIMENSION_TYPE_PRODUCT,
            ("占地", "体积", "尺寸", "平方", "平米", "房间", "够用", "不够用", "面积"),
            linked_param_codes=("installation_type", "indoor_unit_dimensions_mm", "horsepower_hp"),
            linked_claim_codes=("ac_claim_installation_space_design", "ac_claim_large_airflow_coverage"),
        ),
        _sub(
            "installation_constraint",
            "安装约束",
            "appearance_installation_space",
            "外观、安装形态与空间适配",
            DIMENSION_TYPE_PRODUCT,
            ("铜管", "打孔", "支架", "高空", "孔位", "外机位置", "位置远", "延长管"),
            linked_param_codes=("installation_type",),
            linked_claim_codes=("ac_claim_installation_space_design", "ac_claim_warranty_install_service"),
        ),
        _sub(
            "durability_positive",
            "耐用品质",
            "quality_reliability_risk",
            "质量稳定性与产品风险",
            DIMENSION_TYPE_PRODUCT_RISK,
            ("耐用", "质量好", "做工", "扎实", "真材实料", "稳定"),
            linked_claim_codes=("ac_claim_durability_core_material",),
        ),
        _sub(
            "core_component",
            "核心部件",
            "quality_reliability_risk",
            "质量稳定性与产品风险",
            DIMENSION_TYPE_PRODUCT_RISK,
            ("压缩机", "铜管", "冷媒", "外机", "内机", "蒸发器", "冷凝器"),
            linked_param_codes=("refrigerant_type",),
            linked_claim_codes=("ac_claim_durability_core_material",),
        ),
        _sub(
            "failure_risk",
            "故障风险",
            "quality_reliability_risk",
            "质量稳定性与产品风险",
            DIMENSION_TYPE_PRODUCT_RISK,
            ("故障", "坏", "漏水", "漏氟", "不制冷", "不制热", "异响", "报错"),
            linked_param_codes=("refrigerant_type",),
            linked_claim_codes=("ac_claim_durability_core_material",),
        ),
        _sub(
            "quality_pending",
            "质量待观察",
            "quality_reliability_risk",
            "质量稳定性与产品风险",
            DIMENSION_TYPE_PRODUCT_RISK,
            ("待观察", "刚买", "希望耐用", "用久再看", "质量如何"),
            linked_claim_codes=("ac_claim_durability_core_material",),
        ),
        _sub(
            "value_positive",
            "性价比正向",
            "price_value_perception",
            "价格、补贴与价值感知",
            DIMENSION_TYPE_PRICE_VALUE,
            ("性价比", "划算", "值得", "实惠", "便宜", "物有所值"),
            linked_claim_codes=("ac_claim_price_value_subsidy",),
        ),
        _sub(
            "price_negative",
            "价格负向",
            "price_value_perception",
            "价格、补贴与价值感知",
            DIMENSION_TYPE_PRICE_VALUE,
            ("贵", "降价", "买亏", "差价", "坑", "不值"),
            linked_claim_codes=("ac_claim_price_value_subsidy",),
        ),
        _sub(
            "subsidy_promotion",
            "补贴优惠",
            "price_value_perception",
            "价格、补贴与价值感知",
            DIMENSION_TYPE_PRICE_VALUE,
            ("国补", "以旧换新", "优惠", "券", "活动", "补贴", "百亿补贴"),
            linked_claim_codes=("ac_claim_price_value_subsidy",),
        ),
        _sub(
            "same_price_value",
            "同价位判断",
            "price_value_perception",
            "价格、补贴与价值感知",
            DIMENSION_TYPE_PRICE_VALUE,
            ("同价位", "比价", "配置", "价格对得起", "平台对比"),
            linked_claim_codes=("ac_claim_price_value_subsidy", "ac_claim_energy_efficiency_apf"),
        ),
        _sub("audience_senior_parent", "老人/父母", "audience_signal", "人群线索", DIMENSION_TYPE_AUDIENCE, ("老人", "父母", "爸妈", "长辈", "老人家")),
        _sub("audience_child_baby", "孩子/宝宝", "audience_signal", "人群线索", DIMENSION_TYPE_AUDIENCE, ("孩子", "小孩", "宝宝", "儿童", "母婴", "防直吹")),
        _sub("audience_family", "家庭/全家", "audience_signal", "人群线索", DIMENSION_TYPE_AUDIENCE, ("家人", "一家人", "全家", "父母孩子", "家庭")),
        _sub("audience_rental_young", "租房/年轻用户", "audience_signal", "人群线索", DIMENSION_TYPE_AUDIENCE, ("租房", "宿舍", "单间", "年轻人", "出租屋")),
        _sub("audience_sensitive", "特殊敏感人群", "audience_signal", "人群线索", DIMENSION_TYPE_AUDIENCE, ("鼻炎", "怕冷", "怕直吹", "睡眠不好", "过敏")),
        _sub("use_bedroom_sleep", "卧室睡眠", "use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, ("卧室", "睡觉", "夜间", "小房间", "主卧")),
        _sub("use_living_room_large", "客厅大空间", "use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, ("客厅", "大空间", "全屋", "3p", "三匹", "柜机")),
        _sub("use_rental_dorm", "租房/宿舍", "use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, ("租房", "宿舍", "移动空调", "安装简单", "出租屋")),
        _sub("use_office_shop", "办公/门店", "use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, ("办公室", "办公", "店里", "商用", "小店", "门店")),
        _sub("use_humid_south", "南方潮湿", "use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, ("除湿", "防潮", "梅雨", "回南天", "南方")),
        _sub("use_summer_winter", "冬夏冷暖", "use_case_signal", "用途与使用场景线索", DIMENSION_TYPE_USE_CASE, ("夏天", "冬天", "冷暖", "降温", "制热", "制冷")),
        _sub("brand_trust", "品牌信任", "brand_power_signal", "品牌力与复购推荐", DIMENSION_TYPE_BRAND, ("大品牌", "老品牌", "老牌", "信赖", "信任", "放心", "靠谱", "质量有保证")),
        _sub("brand_repurchase", "复购/长期使用", "brand_power_signal", "品牌力与复购推荐", DIMENSION_TYPE_BRAND, ("复购", "再次选择", "又买", "买了多台", "一直用", "回购")),
        _sub("brand_recommendation", "口碑推荐", "brand_power_signal", "品牌力与复购推荐", DIMENSION_TYPE_BRAND, ("推荐", "朋友推荐", "家人推荐", "口碑", "种草")),
        _sub("brand_sentiment", "品牌情绪", "brand_power_signal", "品牌力与复购推荐", DIMENSION_TYPE_BRAND, ("喜欢", "不再买", "粉丝", "忠实", "失望")),
        _sub("competitor_brand_compare", "跨品牌对比", "competitor_comparison_signal", "竞品比较与替换来源", DIMENSION_TYPE_COMPETITOR, ("比格力", "比美的", "比海尔", "比小米", "比奥克斯", "比tcl", "对比", "竞品")),
        _sub("replacement_source", "旧机替换", "competitor_comparison_signal", "竞品比较与替换来源", DIMENSION_TYPE_COMPETITOR, ("换掉", "替换", "原来", "之前用", "旧空调", "老空调")),
        _sub("same_price_comparison", "同价位比较", "competitor_comparison_signal", "竞品比较与替换来源", DIMENSION_TYPE_COMPETITOR, ("同价位", "同价格", "平台比价", "配置比较", "差不多价格")),
        _sub("capability_comparison", "能力对比", "competitor_comparison_signal", "竞品比较与替换来源", DIMENSION_TYPE_COMPETITOR, ("制冷更快", "更省电", "声音更小", "更划算", "效果更好", "不如")),
        _sub(
            "service_delivery_install",
            "配送/安装/客服/售后",
            "service_fulfillment_excluded",
            "服务履约隔离维度",
            DIMENSION_TYPE_SERVICE,
            ("安装师傅", "安装", "配送", "送货", "物流", "客服", "售后", "上门", "包修", "退换货", "发货"),
            linked_claim_codes=("ac_claim_warranty_install_service",),
        ),
        _sub(
            "campaign_template_review",
            "模板/营销文案",
            "template_campaign_review",
            "模板/营销文案复核维度",
            DIMENSION_TYPE_QUALITY_REVIEW,
            ("官方旗舰", "详情页", "新品上市", "全新升级", "强烈推荐购买", "活动力度", "宣传", "文案"),
        ),
    )
    return M05CCommentTaxonomy(
        taxonomy_version=CORE3_M05C_AC_TAXONOMY_VERSION,
        product_category="AC",
        product_category_label_cn="空调",
        raw_category_label_cn="空调",
        sku_code_prefix="AC",
        dimensions=dimensions,
        subdimensions=subdimensions,
    )


class M05CCommentTaxonomyLoader:
    def load(self, taxonomy_version: str, *, product_category: str) -> M05CCommentTaxonomy:
        normalized_category = str(product_category or "").upper()
        if normalized_category == "TV" and taxonomy_version == CORE3_M05C_TV_TAXONOMY_VERSION:
            return tv_comment_fact_taxonomy_v0_1()
        if normalized_category == "AC" and taxonomy_version == CORE3_M05C_AC_TAXONOMY_VERSION:
            return ac_comment_fact_taxonomy_v0_1()
        raise ValueError(f"{normalized_category or product_category} 评论事实 taxonomy 未发布，不能生成 SKU 评论事实画像。")


@dataclass(frozen=True)
class M05CLlmConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 90.0

    @classmethod
    def from_env(cls) -> "M05CLlmConfig | None":
        api_key = (
            os.getenv("CATFORGE_M05C_LLM_API_KEY")
            or os.getenv("CATFORGE_LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            return None
        return cls(
            base_url=(
                os.getenv("CATFORGE_M05C_LLM_BASE_URL")
                or os.getenv("CATFORGE_LLM_BASE_URL")
                or os.getenv("OPENAI_BASE_URL")
                or M05C_DEFAULT_LLM_BASE_URL
            ),
            api_key=api_key,
            model=(
                os.getenv("CATFORGE_M05C_LLM_MODEL")
                or os.getenv("CATFORGE_LLM_MODEL")
                or os.getenv("OPENAI_MODEL")
                or M05C_DEFAULT_LLM_MODEL
            ),
            timeout_seconds=float(os.getenv("CATFORGE_M05C_LLM_TIMEOUT_SECONDS") or "90"),
        )


class M05CLlmClient:
    def __init__(self, config: M05CLlmConfig) -> None:
        self.config = config

    def annotate_batch(
        self,
        *,
        taxonomy: M05CCommentTaxonomy,
        items: Sequence[dict[str, Any]],
    ) -> list[M05CLlmAnnotation]:
        if not items:
            return []
        response = httpx.post(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是 CatForge 的品类评论事实抽取器。只依据给定 taxonomy 从中文电视评论句子中选择评论事实子维度，"
                            "识别情感极性。不要输出业务结论，不要发明 taxonomy 之外的 code。只返回 JSON。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "task": "classify_tv_comment_fact_dimensions",
                                "polarity_values": [POLARITY_POSITIVE, POLARITY_NEGATIVE, POLARITY_MIXED, POLARITY_NEUTRAL],
                                "output_schema": {
                                    "items": [
                                        {
                                            "source_comment_key": "string",
                                            "subdimension_codes": ["taxonomy subdimension_code"],
                                            "polarity": "positive|negative|mixed|neutral",
                                            "confidence": "0-1 number",
                                            "rationale": "short Chinese reason",
                                        }
                                    ]
                                },
                                "taxonomy": _llm_taxonomy_payload(taxonomy),
                                "comments": items,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                ],
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = str(payload["choices"][0]["message"]["content"])
        parsed = _parse_llm_json_object(content)
        annotations = []
        for item in parsed.get("items") or []:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get("source_comment_key") or "")
            if not key:
                continue
            codes = tuple(str(code) for code in item.get("subdimension_codes") or [] if code)
            annotations.append(
                M05CLlmAnnotation(
                    source_comment_key=key,
                    subdimension_codes=codes,
                    polarity=_normalize_polarity(item.get("polarity")),
                    confidence=_float_or_none(item.get("confidence")),
                    rationale=str(item.get("rationale") or "")[:300] or None,
                )
            )
        return annotations


class M05CCommentClassifier:
    def __init__(
        self,
        *,
        taxonomy: M05CCommentTaxonomy,
        llm_mode: str,
        llm_batch_size: int,
    ) -> None:
        self.taxonomy = taxonomy
        self.llm_mode = _normalize_llm_mode(llm_mode)
        self.llm_batch_size = max(int(llm_batch_size or M05C_DEFAULT_LLM_BATCH_SIZE), 1)
        self.subdimensions_by_code = taxonomy.subdimensions_by_code

    def classify_sku(
        self,
        sku_code: str,
        records: Sequence[M05CCommentRecord],
    ) -> M05CLlmExtractionResult:
        rule_annotations = self._rule_annotations(sku_code, records)
        if self.llm_mode == LLM_MODE_OFF:
            return M05CLlmExtractionResult(
                annotations=rule_annotations,
                stats={
                    "llm_mode": LLM_MODE_OFF,
                    "llm_called": False,
                    "llm_item_count": 0,
                    "rule_item_count": len(rule_annotations),
                },
                warnings=[],
            )

        config = M05CLlmConfig.from_env()
        if config is None:
            if self.llm_mode == LLM_MODE_REQUIRED:
                raise ValueError("M05C-B 需要 LLM，但未配置 CATFORGE_M05C_LLM_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY。")
            return M05CLlmExtractionResult(
                annotations=rule_annotations,
                stats={
                    "llm_mode": self.llm_mode,
                    "llm_called": False,
                    "llm_item_count": 0,
                    "rule_item_count": len(rule_annotations),
                },
                warnings=["m05c_llm_not_configured_rule_fallback"],
            )

        client = M05CLlmClient(config)
        llm_annotations: dict[str, M05CLlmAnnotation] = {}
        items = self._llm_items(sku_code, records, rule_annotations)
        try:
            for batch in _chunks(items, self.llm_batch_size):
                for annotation in client.annotate_batch(taxonomy=self.taxonomy, items=batch):
                    valid_codes = tuple(code for code in annotation.subdimension_codes if code in self.subdimensions_by_code)
                    llm_annotations[annotation.source_comment_key] = M05CLlmAnnotation(
                        source_comment_key=annotation.source_comment_key,
                        subdimension_codes=valid_codes,
                        polarity=annotation.polarity,
                        confidence=annotation.confidence,
                        rationale=annotation.rationale,
                    )
        except Exception as exc:
            if self.llm_mode == LLM_MODE_REQUIRED:
                raise ValueError(f"M05C-B LLM 调用失败：{exc}") from exc
            return M05CLlmExtractionResult(
                annotations=rule_annotations,
                stats={
                    "llm_mode": self.llm_mode,
                    "llm_called": True,
                    "llm_item_count": len(items),
                    "rule_item_count": len(rule_annotations),
                    "llm_error": str(exc),
                },
                warnings=["m05c_llm_failed_rule_fallback"],
            )

        merged = dict(rule_annotations)
        for key, annotation in llm_annotations.items():
            if annotation.subdimension_codes:
                merged[key] = annotation
            elif key in merged:
                del merged[key]
        return M05CLlmExtractionResult(
            annotations=merged,
            stats={
                "llm_mode": self.llm_mode,
                "llm_called": True,
                "llm_model": config.model,
                "llm_base_url": _redact_base_url(config.base_url),
                "llm_item_count": len(items),
                "llm_annotation_count": len(llm_annotations),
                "rule_item_count": len(rule_annotations),
                "merged_annotation_count": len(merged),
            },
            warnings=[],
        )

    def _rule_annotations(
        self,
        sku_code: str,
        records: Sequence[M05CCommentRecord],
    ) -> dict[str, M05CLlmAnnotation]:
        annotations: dict[str, M05CLlmAnnotation] = {}
        for index, record in enumerate(records, start=1):
            source_comment_key = _record_source_comment_key(record, sku_code, index)
            codes = tuple(item.subdimension_code for item in self._match_subdimensions(record.comment_text))
            if not codes:
                continue
            annotations[source_comment_key] = M05CLlmAnnotation(
                source_comment_key=source_comment_key,
                subdimension_codes=codes,
                polarity=_detect_polarity(record.comment_text),
                confidence=None,
                rationale=None,
            )
        return annotations

    def _match_subdimensions(self, text_value: str) -> list[M05CSubdimensionDefinition]:
        normalized_text = _normalize_comment_text(text_value)
        matches = []
        for definition in self.taxonomy.subdimensions:
            if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in definition.patterns):
                matches.append(definition)
        return matches

    def _llm_items(
        self,
        sku_code: str,
        records: Sequence[M05CCommentRecord],
        rule_annotations: Mapping[str, M05CLlmAnnotation],
    ) -> list[dict[str, Any]]:
        items = []
        for index, record in enumerate(records, start=1):
            source_comment_key = _record_source_comment_key(record, sku_code, index)
            rule_annotation = rule_annotations.get(source_comment_key)
            items.append(
                {
                    "source_comment_key": source_comment_key,
                    "sku_code": sku_code,
                    "comment_text": record.comment_text,
                    "rule_candidate_subdimension_codes": list(rule_annotation.subdimension_codes) if rule_annotation else [],
                    "rule_candidate_polarity": rule_annotation.polarity if rule_annotation else _detect_polarity(record.comment_text),
                }
            )
        return items


class M05CCommentEvidenceReader(Core3BaseRepository):
    def list_target_sku_codes(
        self,
        batch_id: str,
        *,
        sku_code_prefix: str,
        target_sku_codes: Sequence[str] = (),
    ) -> list[str]:
        if target_sku_codes:
            return sorted({str(code) for code in target_sku_codes if str(code).startswith(sku_code_prefix)})
        rows = self.db.execute(
            select(entities.Core3EvidenceAtom.sku_code)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type == Core3EvidenceType.COMMENT_SENTENCE.value)
            .where(entities.Core3EvidenceAtom.sku_code.like(f"{sku_code_prefix}%"))
            .distinct()
            .order_by(entities.Core3EvidenceAtom.sku_code)
        ).scalars()
        return [str(row) for row in rows if row]

    def list_comment_records(
        self,
        batch_id: str,
        *,
        sku_code_prefix: str,
        target_sku_codes: Sequence[str] = (),
        max_sentences_per_sku: int = 500,
    ) -> list[M05CCommentRecord]:
        sku_codes = self.list_target_sku_codes(batch_id, sku_code_prefix=sku_code_prefix, target_sku_codes=target_sku_codes)
        records: list[M05CCommentRecord] = []
        for sku_code in sku_codes:
            stmt = (
                select(entities.Core3EvidenceAtom)
                .where(entities.Core3EvidenceAtom.project_id == self.project_id)
                .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
                .where(entities.Core3EvidenceAtom.batch_id == batch_id)
                .where(entities.Core3EvidenceAtom.is_current.is_(True))
                .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
                .where(entities.Core3EvidenceAtom.evidence_type == Core3EvidenceType.COMMENT_SENTENCE.value)
                .where(entities.Core3EvidenceAtom.sku_code == sku_code)
                .order_by(entities.Core3EvidenceAtom.comment_id, entities.Core3EvidenceAtom.sentence_seq, entities.Core3EvidenceAtom.evidence_id)
                .limit(max(max_sentences_per_sku, 1))
            )
            records.extend(_record_from_evidence(row) for row in self.db.execute(stmt).scalars())
        return _dedupe_comment_records(records)


class M05CCommentFactRepository(Core3BaseRepository):
    def delete_outputs(
        self,
        *,
        batch_id: str,
        taxonomy_version: str,
        rule_version: str,
        product_category: str,
        target_sku_codes: Sequence[str] = (),
    ) -> None:
        sku_codes = tuple(str(code) for code in target_sku_codes if code)
        model_classes = [
            entities.Core3CommentFactReviewIssue,
            entities.Core3SkuCommentFactProfile,
            entities.Core3CommentFactAtom,
        ]
        if not sku_codes:
            model_classes.insert(1, entities.Core3CommentFactCoverage)
        for model_cls in model_classes:
            stmt = (
                delete(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(model_cls.batch_id == batch_id)
                .where(model_cls.taxonomy_version == taxonomy_version)
                .where(model_cls.rule_version == rule_version)
                .where(model_cls.product_category == product_category)
            )
            if sku_codes and hasattr(model_cls, "sku_code"):
                stmt = stmt.where(model_cls.sku_code.in_(sku_codes))
            self.db.execute(stmt)
        self.db.flush()

    def delete_coverages(
        self,
        *,
        batch_id: str,
        taxonomy_version: str,
        rule_version: str,
        product_category: str,
    ) -> None:
        stmt = (
            delete(entities.Core3CommentFactCoverage)
            .where(entities.Core3CommentFactCoverage.project_id == self.project_id)
            .where(entities.Core3CommentFactCoverage.category_code == self.category_code.value)
            .where(entities.Core3CommentFactCoverage.batch_id == batch_id)
            .where(entities.Core3CommentFactCoverage.taxonomy_version == taxonomy_version)
            .where(entities.Core3CommentFactCoverage.rule_version == rule_version)
            .where(entities.Core3CommentFactCoverage.product_category == product_category)
        )
        self.db.execute(stmt)
        self.db.flush()

    def save_profiles(self, profiles: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuCommentFactProfile,
            profiles,
            unique_fields=("batch_id", "taxonomy_version", "sku_code", "rule_version", "is_current"),
            hash_field="profile_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_facts(self, facts: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentFactAtom,
            facts,
            unique_fields=("batch_id", "taxonomy_version", "sku_code", "source_comment_key", "subdimension_code", "rule_version", "is_current"),
            hash_field="fact_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_coverages(self, coverages: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentFactCoverage,
            coverages,
            unique_fields=("batch_id", "product_category", "taxonomy_version", "coverage_type", "coverage_key", "rule_version", "is_current"),
            hash_field="coverage_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_review_issues(self, issues: Sequence[Any], *, replace_on_hash_conflict: bool = False) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentFactReviewIssue,
            issues,
            unique_fields=("batch_id", "taxonomy_version", "sku_code", "issue_type", "issue_hash", "rule_version", "is_current"),
            hash_field="issue_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool,
    ) -> ParamRepositoryWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        for payload in payloads:
            record, created = self._save_one(
                model_cls,
                payload,
                unique_fields=unique_fields,
                hash_field=hash_field,
                replace_existing=replace_existing,
            )
            records.append(record)
            created_count += 1 if created else 0
            reused_count += 0 if created else 1
        return ParamRepositoryWriteResult(records=tuple(records), created_count=created_count, reused_count=reused_count)

    def _save_one(
        self,
        model_cls: Any,
        payload: Any,
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool,
    ) -> tuple[Any, bool]:
        normalized_payload = _normalize_payload(model_cls, payload, project_id=self.project_id, category_code=self.category_code.value)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is not None:
            if replace_existing:
                _update_existing(existing, normalized_payload)
                self.db.flush()
                return existing, False
            _assert_same_hash(existing, normalized_payload, hash_field=hash_field, unique_fields=unique_fields, model_name=model_cls.__tablename__)
            return existing, False
        record = model_cls(**_jsonable(normalized_payload))
        self.db.add(record)
        self.db.flush()
        return record, True

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = select(model_cls).where(model_cls.project_id == self.project_id).where(model_cls.category_code == self.category_code.value)
        for field_name in unique_fields:
            field_value = payload.get(field_name)
            if field_value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required for idempotent write")
            stmt = stmt.where(getattr(model_cls, field_name) == field_value)
        return self.db.execute(stmt).scalars().first()


class M05CRunner:
    module_code = Core3ModuleCode.M05C

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(
                project_id=context.project_id,
                category_code=context.category_code.value,
                batch_id=None,
                run_id=context.run_id,
                message_cn="M05C 缺少 M00 batch_id，无法生成 SKU 评论事实画像。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        product_category = str(target.metadata.get("product_category") or context.category_code.value)
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            product_category=product_category,
            taxonomy_version=str(target.metadata.get("taxonomy_version") or _comment_taxonomy_version_for_product_category(product_category)),
            rule_version=str(target.metadata.get("rule_version") or _comment_rule_version_for_product_category(product_category)),
            target_sku_codes=target.target_ids,
            max_sentences_per_sku=int(target.metadata.get("max_sentences_per_sku") or 500),
            llm_mode=str(target.metadata.get("llm_mode") or LLM_MODE_AUTO),
            llm_batch_size=int(target.metadata.get("llm_batch_size") or M05C_DEFAULT_LLM_BATCH_SIZE),
            force_rebuild=bool(target.metadata.get("force_rebuild")),
            build_coverage=bool(target.metadata.get("build_coverage", True)),
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
        taxonomy_version: str = CORE3_M05C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M05C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        max_sentences_per_sku: int = 500,
        llm_mode: str = LLM_MODE_AUTO,
        llm_batch_size: int = M05C_DEFAULT_LLM_BATCH_SIZE,
        force_rebuild: bool = False,
        build_coverage: bool = True,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(db=self.db, project_id=project_id, category_code=category_code)
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
                service_result = M05CService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    taxonomy_version=taxonomy_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    max_sentences_per_sku=max_sentences_per_sku,
                    llm_mode=llm_mode,
                    llm_batch_size=llm_batch_size,
                    force_rebuild=force_rebuild,
                    build_coverage=build_coverage,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m05c_comment_hash_conflict",
                message_cn="M05C 评论事实画像结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m05c_comment_profile_failed",
                message_cn="M05C 评论事实画像生成失败，请检查 M02 评论证据、M03B 参数画像、M04C 卖点画像或评论 taxonomy 配置。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M05C_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
            "product_category": product_category,
            "target_sku_codes": list(target_sku_codes),
            "max_sentences_per_sku": max_sentences_per_sku,
            "llm_mode": _normalize_llm_mode(llm_mode),
            "llm_batch_size": llm_batch_size,
            "build_coverage": build_coverage,
            **service_result.summary,
        }
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M05C,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.sku_profile_count + service_result.comment_fact_count + service_result.comment_coverage_count + service_result.review_issue_count,
            output_hash=stable_hash(summary_json, version="m05c_comment_fact_profile_summary_v1"),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {"module_code": "M08", "reason": "SKU 评论事实变化会影响综合事实画像、目标客群和用户任务判断。"},
                {"module_code": "M12", "reason": "评论支撑/反证变化会影响价值战场和竞品证据展示。"},
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    def rebuild_coverage(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M05C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M05C_TV_RULE_VERSION,
        force_rebuild: bool = True,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(db=self.db, project_id=project_id, category_code=category_code)
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
                service_result = M05CService(repository_context).rebuild_coverages(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    taxonomy_version=taxonomy_version,
                    rule_version=rule_version,
                    force_rebuild=force_rebuild,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m05c_comment_coverage_hash_conflict",
                message_cn="M05C 评论事实覆盖统计与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m05c_comment_coverage_rebuild_failed",
                message_cn="M05C 评论事实覆盖统计重算失败，请检查已落库的评论事实原子。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M05C_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
            "product_category": product_category,
            "coverage_rebuild": True,
            **service_result.summary,
        }
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M05C,
            status=Core3RunStatus.SUCCESS,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.comment_coverage_count,
            output_hash=stable_hash(summary_json, version="m05c_comment_coverage_rebuild_summary_v1"),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {"module_code": "M08", "reason": "批次级评论事实覆盖统计变化会影响综合事实画像和后续竞品证据展示。"},
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M05CService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M05C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M05C_TV_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        max_sentences_per_sku: int = 500,
        llm_mode: str = LLM_MODE_AUTO,
        llm_batch_size: int = M05C_DEFAULT_LLM_BATCH_SIZE,
        force_rebuild: bool = False,
        build_coverage: bool = True,
    ) -> M05CServiceResult:
        taxonomy = M05CCommentTaxonomyLoader().load(taxonomy_version, product_category=product_category)
        records = M05CCommentEvidenceReader(self.context).list_comment_records(
            batch_id,
            sku_code_prefix=taxonomy.sku_code_prefix,
            target_sku_codes=target_sku_codes,
            max_sentences_per_sku=max_sentences_per_sku,
        )
        sku_codes = sorted({record.sku_code for record in records})
        param_profiles = self._read_param_profiles(
            batch_id,
            sku_codes=sku_codes,
            rule_version=_param_rule_version_for_product_category(taxonomy.product_category),
        )
        claim_facts = self._read_claim_facts(
            batch_id,
            sku_codes=sku_codes,
            rule_version=_claim_rule_version_for_product_category(taxonomy.product_category),
        )
        profiles, facts, coverages, review_issues, summary = M05CProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            rule_version=rule_version,
            llm_mode=llm_mode,
            llm_batch_size=llm_batch_size,
        ).build(records, param_profiles, claim_facts, build_coverage=build_coverage)
        repository = M05CCommentFactRepository(self.context)
        if force_rebuild:
            repository.delete_outputs(
                batch_id=batch_id,
                taxonomy_version=taxonomy.taxonomy_version,
                rule_version=rule_version,
                product_category=taxonomy.product_category,
                target_sku_codes=sku_codes,
            )
        write_results = {
            "sku_comment_profiles": repository.save_profiles(profiles, replace_on_hash_conflict=force_rebuild),
            "comment_facts": repository.save_facts(facts, replace_on_hash_conflict=force_rebuild),
            "review_issues": repository.save_review_issues(review_issues, replace_on_hash_conflict=force_rebuild),
        }
        if build_coverage:
            write_results["comment_coverages"] = repository.save_coverages(coverages, replace_on_hash_conflict=force_rebuild)
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        warnings = _warnings(summary, param_profiles=param_profiles, claim_facts=claim_facts, sku_codes=sku_codes)
        return M05CServiceResult(
            input_count=len(records),
            sku_profile_count=len(profiles),
            comment_fact_count=len(facts),
            comment_coverage_count=len(coverages),
            review_issue_count=len(review_issues),
            matched_sentence_count=int(summary["matched_sentence_count"]),
            service_excluded_sentence_count=int(summary["service_excluded_sentence_count"]),
            contradicted_fact_count=int(summary["contradicted_fact_count"]),
            warnings=warnings,
            write_summary=write_summary,
            summary={**summary, "write_summary": write_summary, "category_boundary_filter": f"sku_code_prefix_{taxonomy.sku_code_prefix}"},
        )

    def rebuild_coverages(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M05C_TV_TAXONOMY_VERSION,
        rule_version: str = CORE3_M05C_TV_RULE_VERSION,
        force_rebuild: bool = True,
    ) -> M05CServiceResult:
        taxonomy = M05CCommentTaxonomyLoader().load(taxonomy_version, product_category=product_category)
        fact_rows = list(
            self.context.db.execute(
                select(entities.Core3CommentFactAtom)
                .where(entities.Core3CommentFactAtom.project_id == self.context.project_id)
                .where(entities.Core3CommentFactAtom.category_code == self.context.category_code.value)
                .where(entities.Core3CommentFactAtom.batch_id == batch_id)
                .where(entities.Core3CommentFactAtom.product_category == taxonomy.product_category)
                .where(entities.Core3CommentFactAtom.taxonomy_version == taxonomy.taxonomy_version)
                .where(entities.Core3CommentFactAtom.rule_version == rule_version)
                .where(entities.Core3CommentFactAtom.is_current.is_(True))
                .order_by(
                    entities.Core3CommentFactAtom.sku_code,
                    entities.Core3CommentFactAtom.source_comment_key,
                    entities.Core3CommentFactAtom.subdimension_code,
                )
            ).scalars()
        )
        facts = [M05CWritePayload(_fact_row_payload(row)) for row in fact_rows]
        profile_sku_count = (
            self.context.db.execute(
                select(func.count(func.distinct(entities.Core3SkuCommentFactProfile.sku_code)))
                .where(entities.Core3SkuCommentFactProfile.project_id == self.context.project_id)
                .where(entities.Core3SkuCommentFactProfile.category_code == self.context.category_code.value)
                .where(entities.Core3SkuCommentFactProfile.batch_id == batch_id)
                .where(entities.Core3SkuCommentFactProfile.product_category == taxonomy.product_category)
                .where(entities.Core3SkuCommentFactProfile.taxonomy_version == taxonomy.taxonomy_version)
                .where(entities.Core3SkuCommentFactProfile.rule_version == rule_version)
                .where(entities.Core3SkuCommentFactProfile.is_current.is_(True))
            ).scalar()
            or 0
        )
        total_sku_count = max(int(profile_sku_count), len({fact.payload["sku_code"] for fact in facts}))
        coverages = M05CProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            rule_version=rule_version,
            llm_mode=LLM_MODE_OFF,
        )._build_coverages(facts, total_sku_count=total_sku_count)
        repository = M05CCommentFactRepository(self.context)
        if force_rebuild:
            repository.delete_coverages(
                batch_id=batch_id,
                taxonomy_version=taxonomy.taxonomy_version,
                rule_version=rule_version,
                product_category=taxonomy.product_category,
            )
        write_results = {"comment_coverages": repository.save_coverages(coverages, replace_on_hash_conflict=force_rebuild)}
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        polarity_distribution = Counter(fact.payload["polarity"] for fact in facts)
        dimension_distribution = Counter(fact.payload["dimension_code"] for fact in facts)
        relation_distribution = Counter(fact.payload["support_relation"] for fact in facts)
        summary = {
            "input_comment_sentence_count": 0,
            "sku_profile_count": total_sku_count,
            "comment_fact_count": len(facts),
            "comment_coverage_count": len(coverages),
            "review_issue_count": 0,
            "matched_sentence_count": len({fact.payload["source_comment_key"] for fact in facts}),
            "service_excluded_sentence_count": len({fact.payload["source_comment_key"] for fact in facts if fact.payload["dimension_type"] == DIMENSION_TYPE_SERVICE}),
            "contradicted_fact_count": sum(1 for fact in facts if fact.payload["support_relation"] == RELATION_CONTRADICTS),
            "polarity_distribution": dict(sorted(polarity_distribution.items())),
            "dimension_distribution": dict(sorted(dimension_distribution.items())),
            "support_relation_distribution": dict(sorted(relation_distribution.items())),
            "taxonomy_hash": stable_hash(_taxonomy_summary(taxonomy), version="m05c_comment_taxonomy_asset_hash_v1"),
            "extraction_method": "coverage_rebuild_from_existing_comment_facts",
            "coverage_build_mode": "rebuild_only",
            "write_summary": write_summary,
            "category_boundary_filter": f"sku_code_prefix_{taxonomy.sku_code_prefix}",
        }
        return M05CServiceResult(
            input_count=len(facts),
            sku_profile_count=0,
            comment_fact_count=len(facts),
            comment_coverage_count=len(coverages),
            review_issue_count=0,
            matched_sentence_count=int(summary["matched_sentence_count"]),
            service_excluded_sentence_count=int(summary["service_excluded_sentence_count"]),
            contradicted_fact_count=int(summary["contradicted_fact_count"]),
            warnings=[],
            write_summary=write_summary,
            summary=summary,
        )

    def _read_param_profiles(
        self,
        batch_id: str,
        *,
        sku_codes: Sequence[str],
        rule_version: str,
    ) -> dict[str, entities.Core3SkuParamProfile]:
        if not sku_codes:
            return {}
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.context.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.context.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .where(entities.Core3SkuParamProfile.sku_code.in_(tuple(sku_codes)))
            .order_by(entities.Core3SkuParamProfile.updated_at.desc(), entities.Core3SkuParamProfile.created_at.desc())
        )
        result: dict[str, entities.Core3SkuParamProfile] = {}
        for profile in self.context.db.execute(stmt).scalars():
            result.setdefault(profile.sku_code, profile)
        return result

    def _read_claim_facts(
        self,
        batch_id: str,
        *,
        sku_codes: Sequence[str],
        rule_version: str,
    ) -> dict[str, dict[str, list[entities.Core3SkuClaimFact]]]:
        if not sku_codes:
            return {}
        stmt = (
            select(entities.Core3SkuClaimFact)
            .where(entities.Core3SkuClaimFact.project_id == self.context.project_id)
            .where(entities.Core3SkuClaimFact.category_code == self.context.category_code.value)
            .where(entities.Core3SkuClaimFact.batch_id == batch_id)
            .where(entities.Core3SkuClaimFact.rule_version == rule_version)
            .where(entities.Core3SkuClaimFact.sku_code.in_(tuple(sku_codes)))
            .where(entities.Core3SkuClaimFact.fact_claim_flag.is_(True))
            .where(entities.Core3SkuClaimFact.is_current.is_(True))
            .order_by(entities.Core3SkuClaimFact.sku_code, entities.Core3SkuClaimFact.claim_code)
        )
        result: dict[str, dict[str, list[entities.Core3SkuClaimFact]]] = defaultdict(lambda: defaultdict(list))
        for row in self.context.db.execute(stmt).scalars():
            result[row.sku_code][row.claim_code].append(row)
        return {sku_code: dict(claims) for sku_code, claims in result.items()}


class M05CProfileBuilder:
    def __init__(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        taxonomy: M05CCommentTaxonomy,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M05C_TV_RULE_VERSION,
        llm_mode: str = LLM_MODE_AUTO,
        llm_batch_size: int = M05C_DEFAULT_LLM_BATCH_SIZE,
    ) -> None:
        self.project_id = project_id
        self.category_code = category_code
        self.batch_id = batch_id
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.taxonomy = taxonomy
        self.rule_version = rule_version
        self.llm_mode = _normalize_llm_mode(llm_mode)
        self.llm_batch_size = max(int(llm_batch_size or M05C_DEFAULT_LLM_BATCH_SIZE), 1)

    def build(
        self,
        records: Iterable[M05CCommentRecord],
        param_profiles: Mapping[str, entities.Core3SkuParamProfile],
        claim_facts_by_sku: Mapping[str, Mapping[str, Sequence[entities.Core3SkuClaimFact]]],
        *,
        build_coverage: bool = True,
    ) -> tuple[list[M05CWritePayload], list[M05CWritePayload], list[M05CWritePayload], list[M05CWritePayload], dict[str, Any]]:
        clean_records = [record for record in records if _sku_allowed(record.sku_code, self.taxonomy.sku_code_prefix) and _present_text(record.comment_text)]
        records_by_sku: dict[str, list[M05CCommentRecord]] = defaultdict(list)
        for record in clean_records:
            records_by_sku[record.sku_code].append(record)

        profiles: list[M05CWritePayload] = []
        facts: list[M05CWritePayload] = []
        review_issues: list[M05CWritePayload] = []
        matched_sentence_keys: set[str] = set()
        service_sentence_keys: set[str] = set()
        contradiction_count = 0
        classifier = M05CCommentClassifier(taxonomy=self.taxonomy, llm_mode=self.llm_mode, llm_batch_size=self.llm_batch_size)
        llm_warnings: list[str] = []
        llm_stats: Counter[str] = Counter()
        llm_detail_stats: dict[str, Any] = {"llm_mode": self.llm_mode, "llm_batch_size": self.llm_batch_size}

        for sku_code in sorted(records_by_sku):
            classification = classifier.classify_sku(sku_code, records_by_sku[sku_code])
            llm_warnings.extend(classification.warnings)
            llm_stats.update(
                {
                    key: value
                    for key, value in classification.stats.items()
                    if isinstance(value, int) and not isinstance(value, bool)
                }
            )
            for key, value in classification.stats.items():
                if key not in llm_detail_stats and (not isinstance(value, int) or isinstance(value, bool)):
                    llm_detail_stats[key] = value
            sku_result = self._build_sku(
                sku_code,
                records_by_sku[sku_code],
                param_profiles.get(sku_code),
                claim_facts_by_sku.get(sku_code, {}),
                classification.annotations,
            )
            profiles.append(sku_result["profile"])
            facts.extend(sku_result["facts"])
            review_issues.extend(sku_result["review_issues"])
            matched_sentence_keys.update(sku_result["matched_sentence_keys"])
            service_sentence_keys.update(sku_result["service_sentence_keys"])
            contradiction_count += int(sku_result["contradicted_fact_count"])

        coverages = self._build_coverages(facts, total_sku_count=len(records_by_sku)) if build_coverage else []
        polarity_distribution = Counter(fact.payload["polarity"] for fact in facts)
        dimension_distribution = Counter(fact.payload["dimension_code"] for fact in facts)
        relation_distribution = Counter(fact.payload["support_relation"] for fact in facts)
        summary = {
            "input_comment_sentence_count": len(clean_records),
            "sku_profile_count": len(profiles),
            "comment_fact_count": len(facts),
            "comment_coverage_count": len(coverages),
            "review_issue_count": len(review_issues),
            "matched_sentence_count": len(matched_sentence_keys),
            "service_excluded_sentence_count": len(service_sentence_keys),
            "contradicted_fact_count": contradiction_count,
            "polarity_distribution": dict(sorted(polarity_distribution.items())),
            "dimension_distribution": dict(sorted(dimension_distribution.items())),
            "support_relation_distribution": dict(sorted(relation_distribution.items())),
            "taxonomy_hash": stable_hash(_taxonomy_summary(self.taxonomy), version="m05c_comment_taxonomy_asset_hash_v1"),
            "extraction_method": "llm_classification_with_rule_candidates" if self.llm_mode != LLM_MODE_OFF else "taxonomy_rule_only",
            "coverage_build_mode": "inline" if build_coverage else "skipped",
            "llm_stats": {**llm_detail_stats, **dict(sorted(llm_stats.items()))},
            "llm_warnings": _unique_preserve_order(llm_warnings),
        }
        return profiles, facts, coverages, review_issues, summary

    def _build_sku(
        self,
        sku_code: str,
        records: list[M05CCommentRecord],
        param_profile: entities.Core3SkuParamProfile | None,
        claim_facts: Mapping[str, Sequence[entities.Core3SkuClaimFact]],
        annotations: Mapping[str, M05CLlmAnnotation],
    ) -> dict[str, Any]:
        model_name = _first_present(record.model_name for record in records) or getattr(param_profile, "model_name", None)
        brand_name = _first_present(record.brand_name for record in records)
        facts: list[M05CWritePayload] = []
        review_issues: list[M05CWritePayload] = []
        matched_sentence_keys: set[str] = set()
        service_sentence_keys: set[str] = set()
        contradicted_fact_count = 0

        for index, record in enumerate(records, start=1):
            source_comment_key = _record_source_comment_key(record, sku_code, index)
            annotation = annotations.get(source_comment_key)
            matches = self._annotation_subdimensions(annotation, record.comment_text)
            if not matches:
                continue
            matched_sentence_keys.add(source_comment_key)
            polarity = annotation.polarity if annotation and annotation.polarity else _detect_polarity(record.comment_text)
            for definition in matches:
                fact_payload = self._fact_payload(
                    sku_code=sku_code,
                    model_name=record.model_name or model_name,
                    brand_name=record.brand_name or brand_name,
                    source_comment_key=source_comment_key,
                    source_comment_id=record.source_comment_id,
                    sentence_seq=record.sentence_seq,
                    raw_comment_text=record.raw_comment_text or record.comment_text,
                    clean_comment_text=record.comment_text,
                    evidence_id=record.evidence_id,
                    sample_status=record.sample_status,
                    definition=definition,
                    polarity=polarity,
                    param_profile=param_profile,
                    claim_facts=claim_facts,
                    annotation=annotation,
                )
                facts.append(M05CWritePayload(fact_payload))
                if definition.dimension_type == DIMENSION_TYPE_SERVICE:
                    service_sentence_keys.add(source_comment_key)
                if fact_payload["support_relation"] == RELATION_CONTRADICTS:
                    contradicted_fact_count += 1
                    review_issues.append(self._review_issue_payload(fact_payload))

        profile = M05CWritePayload(
            self._profile_payload(
                sku_code=sku_code,
                model_name=model_name,
                brand_name=brand_name,
                records=records,
                facts=facts,
                review_issues=review_issues,
                param_profile=param_profile,
                claim_facts=claim_facts,
            )
        )
        return {
            "profile": profile,
            "facts": facts,
            "review_issues": review_issues,
            "matched_sentence_keys": matched_sentence_keys,
            "service_sentence_keys": service_sentence_keys,
            "contradicted_fact_count": contradicted_fact_count,
        }

    def _match_subdimensions(self, text_value: str) -> list[M05CSubdimensionDefinition]:
        normalized_text = _normalize_comment_text(text_value)
        matches = []
        for definition in self.taxonomy.subdimensions:
            if any(re.search(pattern, normalized_text, flags=re.IGNORECASE) for pattern in definition.patterns):
                matches.append(definition)
        return matches

    def _annotation_subdimensions(self, annotation: M05CLlmAnnotation | None, text_value: str) -> list[M05CSubdimensionDefinition]:
        if annotation is None:
            return []
        result = []
        by_code = self.taxonomy.subdimensions_by_code
        for code in annotation.subdimension_codes:
            definition = by_code.get(code)
            if definition is not None:
                if definition.subdimension_code == "brand_trust" and not _brand_trust_supported(text_value):
                    continue
                result.append(definition)
        return result

    def _fact_payload(
        self,
        *,
        sku_code: str,
        model_name: str | None,
        brand_name: str | None,
        source_comment_key: str,
        source_comment_id: str | None,
        sentence_seq: int | None,
        raw_comment_text: str,
        clean_comment_text: str,
        evidence_id: str | None,
        sample_status: str | None,
        definition: M05CSubdimensionDefinition,
        polarity: str,
        param_profile: entities.Core3SkuParamProfile | None,
        claim_facts: Mapping[str, Sequence[entities.Core3SkuClaimFact]],
        annotation: M05CLlmAnnotation | None,
    ) -> dict[str, Any]:
        support = _comment_support(definition, polarity, param_profile, claim_facts)
        evidence_ids = [evidence_id] if evidence_id else []
        quality_flags = []
        if definition.dimension_type == DIMENSION_TYPE_SERVICE:
            quality_flags.append("service_fulfillment_excluded")
        if support["relation"] == RELATION_CONTRADICTS:
            quality_flags.append("comment_contradicts_existing_param_or_claim")
        if not support["param_snapshot"] and definition.linked_param_codes:
            quality_flags.append("linked_param_not_found_or_unknown")
        payload = {
            "comment_fact_id": _comment_fact_id(self.project_id, self.batch_id, sku_code, source_comment_key, definition.subdimension_code, self.rule_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "sku_code": sku_code,
            "model_name": model_name,
            "brand_name": brand_name,
            "source_comment_key": source_comment_key,
            "source_comment_id": source_comment_id,
            "sentence_seq": sentence_seq,
            "raw_comment_text": raw_comment_text,
            "clean_comment_text": clean_comment_text,
            "dimension_code": definition.dimension_code,
            "dimension_name": definition.dimension_name,
            "subdimension_code": definition.subdimension_code,
            "subdimension_name": definition.subdimension_name,
            "dimension_type": definition.dimension_type,
            "polarity": polarity,
            "evidence_strength": _evidence_strength(clean_comment_text, polarity),
            "support_relation": support["relation"],
            "support_target_type": support["target_type"],
            "supported_param_codes": support["supported_param_codes"],
            "contradicted_param_codes": support["contradicted_param_codes"],
            "supported_claim_codes": support["supported_claim_codes"],
            "contradicted_claim_codes": support["contradicted_claim_codes"],
            "param_snapshot_json": support["param_snapshot"],
            "claim_snapshot_json": support["claim_snapshot"],
            "signal_payload_json": {
                "sample_status": sample_status,
                "rule_summary": definition.rule_summary,
                "linked_param_codes": list(definition.linked_param_codes),
                "linked_claim_codes": list(definition.linked_claim_codes),
            },
            "extraction_payload_json": {
                "method": "llm" if annotation and annotation.confidence is not None else "taxonomy_rule",
                "matched_patterns": _matched_patterns(clean_comment_text, definition.patterns),
                "llm_confidence": annotation.confidence if annotation else None,
                "llm_rationale": annotation.rationale if annotation else None,
            },
            "evidence_ids": evidence_ids,
            "quality_flags": quality_flags,
            "confidence": _fact_confidence(polarity, support["relation"], definition.dimension_type),
            "is_current": True,
            "rule_version": self.rule_version,
        }
        payload["fact_hash"] = stable_hash(
            {
                "sku_code": sku_code,
                "source_comment_key": source_comment_key,
                "subdimension_code": definition.subdimension_code,
                "polarity": polarity,
                "support": support,
                "comment_text": clean_comment_text,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M05C_FACT_HASH_VERSION,
        )
        return payload

    def _profile_payload(
        self,
        *,
        sku_code: str,
        model_name: str | None,
        brand_name: str | None,
        records: Sequence[M05CCommentRecord],
        facts: Sequence[M05CWritePayload],
        review_issues: Sequence[M05CWritePayload],
        param_profile: entities.Core3SkuParamProfile | None,
        claim_facts: Mapping[str, Sequence[entities.Core3SkuClaimFact]],
    ) -> dict[str, Any]:
        fact_payloads = [fact.payload for fact in facts]
        source_keys_by_polarity = _source_keys_by_polarity(fact_payloads)
        service_keys = {row["source_comment_key"] for row in fact_payloads if row["dimension_type"] == DIMENSION_TYPE_SERVICE}
        evidence_ids = _unique_preserve_order(evidence_id for row in fact_payloads for evidence_id in row["evidence_ids"])
        supported_param_codes = sorted({code for row in fact_payloads for code in row["supported_param_codes"]})
        contradicted_param_codes = sorted({code for row in fact_payloads for code in row["contradicted_param_codes"]})
        supported_claim_codes = sorted({code for row in fact_payloads for code in row["supported_claim_codes"]})
        contradicted_claim_codes = sorted({code for row in fact_payloads for code in row["contradicted_claim_codes"]})
        known_param_codes = sorted((param_profile.param_values_json or {}).keys()) if param_profile is not None else []
        known_claim_codes = sorted(claim_facts.keys())
        dimension_summary = _dimension_summary(fact_payloads)
        signal_summary = _signal_summary(fact_payloads)
        payload = {
            "comment_profile_id": _comment_profile_id(self.project_id, self.batch_id, sku_code, self.taxonomy.taxonomy_version, self.rule_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "sku_code": sku_code,
            "model_name": model_name,
            "brand_name": brand_name,
            "comment_sentence_count": len(records),
            "matched_sentence_count": len({row["source_comment_key"] for row in fact_payloads}),
            "fact_atom_count": len(fact_payloads),
            "product_fact_sentence_count": len({row["source_comment_key"] for row in fact_payloads if row["dimension_type"] != DIMENSION_TYPE_SERVICE}),
            "positive_sentence_count": len(source_keys_by_polarity[POLARITY_POSITIVE]),
            "negative_sentence_count": len(source_keys_by_polarity[POLARITY_NEGATIVE]),
            "mixed_sentence_count": len(source_keys_by_polarity[POLARITY_MIXED]),
            "neutral_sentence_count": len(source_keys_by_polarity[POLARITY_NEUTRAL]),
            "service_excluded_sentence_count": len(service_keys),
            "dimension_summary_json": dimension_summary,
            "signal_summary_json": signal_summary,
            "param_comment_support_json": _support_summary(fact_payloads, code_field="supported_param_codes", contradiction_field="contradicted_param_codes"),
            "claim_comment_support_json": _support_summary(fact_payloads, code_field="supported_claim_codes", contradiction_field="contradicted_claim_codes"),
            "polarity_summary_json": {key: len(values) for key, values in sorted(source_keys_by_polarity.items())},
            "evidence_examples_json": _sample_examples(fact_payloads, limit=10),
            "supported_param_codes": supported_param_codes,
            "contradicted_param_codes": contradicted_param_codes,
            "unmentioned_param_codes": [code for code in known_param_codes if code not in set(supported_param_codes) | set(contradicted_param_codes)],
            "supported_claim_codes": supported_claim_codes,
            "contradicted_claim_codes": contradicted_claim_codes,
            "unmentioned_claim_codes": [code for code in known_claim_codes if code not in set(supported_claim_codes) | set(contradicted_claim_codes)],
            "evidence_ids": evidence_ids,
            "quality_flags": _profile_quality_flags(fact_payloads, param_profile=param_profile, claim_facts=claim_facts),
            "review_required_count": len(review_issues),
            "confidence": Decimal("0.8500") if fact_payloads else Decimal("0.0000"),
            "is_current": True,
            "rule_version": self.rule_version,
        }
        payload["profile_hash"] = stable_hash(
            {
                "sku_code": sku_code,
                "dimension_summary": dimension_summary,
                "signal_summary": signal_summary,
                "supported_param_codes": supported_param_codes,
                "contradicted_param_codes": contradicted_param_codes,
                "supported_claim_codes": supported_claim_codes,
                "contradicted_claim_codes": contradicted_claim_codes,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "rule_version": self.rule_version,
            },
            version=M05C_PROFILE_HASH_VERSION,
        )
        return payload

    def _build_coverages(self, facts: Sequence[M05CWritePayload], *, total_sku_count: int) -> list[M05CWritePayload]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        names: dict[tuple[str, str], str] = {}
        dimension_codes: dict[tuple[str, str], str | None] = {}
        subdimension_codes: dict[tuple[str, str], str | None] = {}
        rule_summaries: dict[tuple[str, str], str] = {}
        for fact in facts:
            payload = fact.payload
            self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, ("dimension", payload["dimension_code"]), payload, payload["dimension_name"], payload["dimension_code"], None)
            self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, ("subdimension", payload["subdimension_code"]), payload, payload["subdimension_name"], payload["dimension_code"], payload["subdimension_code"])
            if payload["dimension_type"] != DIMENSION_TYPE_PRODUCT:
                self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, (payload["dimension_code"], payload["subdimension_code"]), payload, payload["subdimension_name"], payload["dimension_code"], payload["subdimension_code"])
            for code in payload["supported_param_codes"]:
                self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, ("param_support", code), payload, code, payload["dimension_code"], payload["subdimension_code"])
            for code in payload["contradicted_param_codes"]:
                self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, ("param_contradiction", code), payload, code, payload["dimension_code"], payload["subdimension_code"])
            for code in payload["supported_claim_codes"]:
                self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, ("claim_support", code), payload, code, payload["dimension_code"], payload["subdimension_code"])
            for code in payload["contradicted_claim_codes"]:
                self._add_coverage_group(grouped, names, dimension_codes, subdimension_codes, rule_summaries, ("claim_contradiction", code), payload, code, payload["dimension_code"], payload["subdimension_code"])

        coverages: list[M05CWritePayload] = []
        for key in sorted(grouped):
            coverage_type, coverage_key = key
            rows = grouped[key]
            sku_codes = sorted({row["sku_code"] for row in rows})
            sample_status_counts = Counter(_nested_get(row, "signal_payload_json", "sample_status") or "unknown" for row in rows)
            top_skus = [
                {"sku_code": sku_code, "fact_atom_count": count}
                for sku_code, count in Counter(row["sku_code"] for row in rows).most_common(20)
            ]
            supported_param_codes = sorted({code for row in rows for code in row["supported_param_codes"]})
            contradicted_param_codes = sorted({code for row in rows for code in row["contradicted_param_codes"]})
            supported_claim_codes = sorted({code for row in rows for code in row["supported_claim_codes"]})
            contradicted_claim_codes = sorted({code for row in rows for code in row["contradicted_claim_codes"]})
            review_flags = []
            if contradicted_param_codes or contradicted_claim_codes:
                review_flags.append("comment_contradicts_existing_param_or_claim")
            if coverage_type == DIMENSION_TYPE_SERVICE:
                review_flags.append("service_fulfillment_excluded")
            payload = {
                "comment_coverage_id": _comment_coverage_id(self.project_id, self.batch_id, self.taxonomy.taxonomy_version, coverage_type, coverage_key, self.rule_version),
                "project_id": self.project_id,
                "category_code": self.category_code,
                "batch_id": self.batch_id,
                "run_id": self.run_id,
                "module_run_id": self.module_run_id,
                "product_category": self.taxonomy.product_category,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "coverage_type": coverage_type,
                "coverage_key": coverage_key,
                "coverage_name": names[key],
                "dimension_code": dimension_codes[key],
                "subdimension_code": subdimension_codes[key],
                "rule_summary": rule_summaries[key],
                "fact_atom_count": len(rows),
                "positive_sentence_count": _distinct_sentence_count(rows, POLARITY_POSITIVE),
                "negative_sentence_count": _distinct_sentence_count(rows, POLARITY_NEGATIVE),
                "mixed_sentence_count": _distinct_sentence_count(rows, POLARITY_MIXED),
                "neutral_sentence_count": _distinct_sentence_count(rows, POLARITY_NEUTRAL),
                "strong_evidence_count": sum(1 for row in rows if row["evidence_strength"] == "strong"),
                "supported_param_count": len(supported_param_codes),
                "contradicted_param_count": len(contradicted_param_codes),
                "supported_claim_count": len(supported_claim_codes),
                "contradicted_claim_count": len(contradicted_claim_codes),
                "sku_count": len(sku_codes),
                "sku_ratio": _ratio(len(sku_codes), total_sku_count),
                "sku_codes": sku_codes,
                "sample_sku_codes": sku_codes[:20],
                "top_skus_json": top_skus,
                "supported_param_codes": supported_param_codes,
                "contradicted_param_codes": contradicted_param_codes,
                "supported_claim_codes": supported_claim_codes,
                "contradicted_claim_codes": contradicted_claim_codes,
                "sample_evidence_json": _sample_examples(rows, limit=8),
                "sample_status_counts_json": dict(sorted(sample_status_counts.items())),
                "review_flags": review_flags,
                "coverage_status": "covered" if sku_codes else "empty",
                "is_current": True,
                "rule_version": self.rule_version,
            }
            payload["coverage_hash"] = stable_hash(
                {
                    "coverage_type": coverage_type,
                    "coverage_key": coverage_key,
                    "sku_codes": sku_codes,
                    "polarity": {
                        "positive": payload["positive_sentence_count"],
                        "negative": payload["negative_sentence_count"],
                        "mixed": payload["mixed_sentence_count"],
                        "neutral": payload["neutral_sentence_count"],
                    },
                    "taxonomy_version": self.taxonomy.taxonomy_version,
                    "rule_version": self.rule_version,
                },
                version=M05C_COVERAGE_HASH_VERSION,
            )
            coverages.append(M05CWritePayload(payload))
        return coverages

    def _add_coverage_group(
        self,
        grouped: dict[tuple[str, str], list[dict[str, Any]]],
        names: dict[tuple[str, str], str],
        dimension_codes: dict[tuple[str, str], str | None],
        subdimension_codes: dict[tuple[str, str], str | None],
        rule_summaries: dict[tuple[str, str], str],
        key: tuple[str, str],
        payload: dict[str, Any],
        coverage_name: str,
        dimension_code: str | None,
        subdimension_code: str | None,
    ) -> None:
        grouped[key].append(payload)
        names.setdefault(key, coverage_name)
        dimension_codes.setdefault(key, dimension_code)
        subdimension_codes.setdefault(key, subdimension_code)
        rule_summaries.setdefault(key, _nested_get(payload, "signal_payload_json", "rule_summary") or "按评论事实 atom 聚合。")

    def _review_issue_payload(self, fact_payload: Mapping[str, Any]) -> M05CWritePayload:
        issue_hash = stable_hash(
            {
                "sku_code": fact_payload["sku_code"],
                "source_comment_key": fact_payload["source_comment_key"],
                "subdimension_code": fact_payload["subdimension_code"],
                "contradicted_param_codes": fact_payload["contradicted_param_codes"],
                "contradicted_claim_codes": fact_payload["contradicted_claim_codes"],
                "rule_version": self.rule_version,
            },
            version=M05C_REVIEW_ID_HASH_VERSION,
        )
        payload = {
            "review_issue_id": issue_hash[:120],
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "product_category": self.taxonomy.product_category,
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "sku_code": fact_payload["sku_code"],
            "model_name": fact_payload["model_name"],
            "brand_name": fact_payload["brand_name"],
            "issue_type": "comment_contradicts_existing_param_or_claim",
            "severity": "medium",
            "issue_detail": "评论负向评价与该 SKU 已有参数或卖点事实存在反向关系，需要后续复核是否为体验短板。",
            "issue_payload_json": {
                "source_comment_key": fact_payload["source_comment_key"],
                "comment_text": fact_payload["clean_comment_text"],
                "subdimension_code": fact_payload["subdimension_code"],
                "contradicted_param_codes": fact_payload["contradicted_param_codes"],
                "contradicted_claim_codes": fact_payload["contradicted_claim_codes"],
            },
            "evidence_ids": fact_payload["evidence_ids"],
            "review_required": True,
            "review_status": "review_required",
            "issue_hash": issue_hash,
            "is_current": True,
            "rule_version": self.rule_version,
        }
        return M05CWritePayload(payload)


def _dimension(dimension_code: str, dimension_name: str, dimension_type: str, rule_summary: str) -> M05CDimensionDefinition:
    return M05CDimensionDefinition(
        dimension_code=dimension_code,
        dimension_name=dimension_name,
        dimension_type=dimension_type,
        rule_summary=rule_summary,
    )


def _sub(
    subdimension_code: str,
    subdimension_name: str,
    dimension_code: str,
    dimension_name: str,
    dimension_type: str,
    patterns: Sequence[str],
    *,
    linked_param_codes: Sequence[str] = (),
    linked_claim_codes: Sequence[str] = (),
    rule_summary: str | None = None,
) -> M05CSubdimensionDefinition:
    return M05CSubdimensionDefinition(
        subdimension_code=subdimension_code,
        subdimension_name=subdimension_name,
        dimension_code=dimension_code,
        dimension_name=dimension_name,
        dimension_type=dimension_type,
        patterns=tuple(patterns),
        linked_param_codes=tuple(linked_param_codes),
        linked_claim_codes=tuple(linked_claim_codes),
        rule_summary=rule_summary or f"评论出现 {subdimension_name} 相关表达时归入该评论事实子维度。",
    )


def _record_from_evidence(row: entities.Core3EvidenceAtom) -> M05CCommentRecord:
    comment_text = str(row.clean_value or row.text_value or row.raw_value or "")
    return M05CCommentRecord(
        sku_code=str(row.sku_code or ""),
        model_name=row.model_name,
        brand_name=row.brand_name,
        comment_text=comment_text,
        raw_comment_text=str(row.raw_value or comment_text),
        source_comment_key=f"evidence:{row.evidence_id}",
        source_comment_id=row.comment_id,
        evidence_id=row.evidence_id,
        sentence_seq=row.sentence_seq,
        sample_status=row.sample_status,
    )


def _fact_row_payload(row: entities.Core3CommentFactAtom) -> dict[str, Any]:
    return {
        "comment_fact_id": row.comment_fact_id,
        "project_id": row.project_id,
        "category_code": row.category_code,
        "batch_id": row.batch_id,
        "run_id": row.run_id,
        "module_run_id": row.module_run_id,
        "product_category": row.product_category,
        "taxonomy_version": row.taxonomy_version,
        "sku_code": row.sku_code,
        "model_name": row.model_name,
        "brand_name": row.brand_name,
        "source_comment_key": row.source_comment_key,
        "source_comment_id": row.source_comment_id,
        "sentence_seq": row.sentence_seq,
        "raw_comment_text": row.raw_comment_text,
        "clean_comment_text": row.clean_comment_text,
        "dimension_code": row.dimension_code,
        "dimension_name": row.dimension_name,
        "subdimension_code": row.subdimension_code,
        "subdimension_name": row.subdimension_name,
        "dimension_type": row.dimension_type,
        "polarity": row.polarity,
        "evidence_strength": row.evidence_strength,
        "support_relation": row.support_relation,
        "support_target_type": row.support_target_type,
        "supported_param_codes": row.supported_param_codes or [],
        "contradicted_param_codes": row.contradicted_param_codes or [],
        "supported_claim_codes": row.supported_claim_codes or [],
        "contradicted_claim_codes": row.contradicted_claim_codes or [],
        "param_snapshot_json": row.param_snapshot_json or {},
        "claim_snapshot_json": row.claim_snapshot_json or {},
        "signal_payload_json": row.signal_payload_json or {},
        "extraction_payload_json": row.extraction_payload_json or {},
        "evidence_ids": row.evidence_ids or [],
        "quality_flags": row.quality_flags or [],
        "confidence": row.confidence,
        "fact_hash": row.fact_hash,
        "is_current": row.is_current,
        "rule_version": row.rule_version,
    }


def _dedupe_comment_records(records: Sequence[M05CCommentRecord]) -> list[M05CCommentRecord]:
    seen = set()
    result = []
    for record in records:
        key = (record.sku_code, _normalize_comment_text(record.comment_text))
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _record_source_comment_key(record: M05CCommentRecord, sku_code: str, index: int) -> str:
    return record.source_comment_key or _source_comment_key(sku_code, record.sentence_seq, record.comment_text, index)


def _normalize_llm_mode(value: Any) -> str:
    normalized = str(value or LLM_MODE_AUTO).strip().lower()
    if normalized in {"false", "none", "no", "disabled"}:
        normalized = LLM_MODE_OFF
    if normalized not in {LLM_MODE_AUTO, LLM_MODE_REQUIRED, LLM_MODE_OFF}:
        raise ValueError(f"unsupported M05C llm_mode: {value}")
    return normalized


def _llm_taxonomy_payload(taxonomy: M05CCommentTaxonomy) -> list[dict[str, Any]]:
    return [
        {
            "subdimension_code": item.subdimension_code,
            "subdimension_name": item.subdimension_name,
            "dimension_code": item.dimension_code,
            "dimension_name": item.dimension_name,
            "dimension_type": item.dimension_type,
            "positive_or_negative_examples": list(item.patterns),
            "linked_param_codes": list(item.linked_param_codes),
            "linked_claim_codes": list(item.linked_claim_codes),
            "rule_summary": item.rule_summary,
        }
        for item in taxonomy.subdimensions
    ]


def _parse_llm_json_object(content: str) -> dict[str, Any]:
    text_value = str(content or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?", "", text_value, flags=re.IGNORECASE).strip()
        text_value = re.sub(r"```$", "", text_value).strip()
    parsed = _load_llm_json_value(text_value)
    if isinstance(parsed, str):
        parsed = _load_llm_json_value(parsed.strip())
    if isinstance(parsed, list):
        return {"items": parsed}
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON root must be an object or array")
    if "items" not in parsed and isinstance(parsed.get("facts"), list):
        parsed = {**parsed, "items": parsed["facts"]}
    return parsed


def _load_llm_json_value(text_value: str) -> Any:
    try:
        return json.loads(text_value)
    except json.JSONDecodeError:
        candidates: list[tuple[int, str]] = []
        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = text_value.find(start_char)
            end = text_value.rfind(end_char)
            if start >= 0 and end > start:
                candidates.append((start, text_value[start : end + 1]))
        for _, candidate in sorted(candidates, key=lambda item: item[0]):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise ValueError("LLM response is not JSON")


def _normalize_polarity(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    mapping = {
        "正向": POLARITY_POSITIVE,
        "positive": POLARITY_POSITIVE,
        "好评": POLARITY_POSITIVE,
        "负向": POLARITY_NEGATIVE,
        "negative": POLARITY_NEGATIVE,
        "差评": POLARITY_NEGATIVE,
        "混合": POLARITY_MIXED,
        "mixed": POLARITY_MIXED,
        "中性": POLARITY_NEUTRAL,
        "neutral": POLARITY_NEUTRAL,
    }
    return mapping.get(normalized)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _chunks(values: Sequence[dict[str, Any]], chunk_size: int) -> list[Sequence[dict[str, Any]]]:
    size = max(int(chunk_size or M05C_DEFAULT_LLM_BATCH_SIZE), 1)
    return [values[index : index + size] for index in range(0, len(values), size)]


def _redact_base_url(value: str) -> str:
    return str(value or "").rstrip("/")


def _comment_support(
    definition: M05CSubdimensionDefinition,
    polarity: str,
    param_profile: entities.Core3SkuParamProfile | None,
    claim_facts: Mapping[str, Sequence[entities.Core3SkuClaimFact]],
) -> dict[str, Any]:
    if definition.dimension_type == DIMENSION_TYPE_SERVICE:
        return {
            "relation": RELATION_SERVICE_EXCLUDED,
            "target_type": "service",
            "supported_param_codes": [],
            "contradicted_param_codes": [],
            "supported_claim_codes": [],
            "contradicted_claim_codes": [],
            "param_snapshot": {},
            "claim_snapshot": {},
        }
    param_values = param_profile.param_values_json if param_profile is not None else {}
    present_params = [code for code in definition.linked_param_codes if _param_entry_present((param_values or {}).get(code))]
    present_claims = [code for code in definition.linked_claim_codes if claim_facts.get(code)]
    param_snapshot = {code: _compact_param_entry((param_values or {}).get(code)) for code in present_params}
    claim_snapshot = {code: [_compact_claim_fact(row) for row in claim_facts.get(code, [])[:3]] for code in present_claims}

    supported_param_codes: list[str] = []
    contradicted_param_codes: list[str] = []
    supported_claim_codes: list[str] = []
    contradicted_claim_codes: list[str] = []
    if polarity in {POLARITY_POSITIVE, POLARITY_MIXED}:
        supported_param_codes = present_params
        supported_claim_codes = present_claims
    if polarity in {POLARITY_NEGATIVE, POLARITY_MIXED}:
        contradicted_param_codes = present_params
        contradicted_claim_codes = present_claims

    if contradicted_param_codes or contradicted_claim_codes:
        relation = RELATION_CONTRADICTS
    elif supported_param_codes or supported_claim_codes:
        relation = RELATION_SUPPORTS
    else:
        relation = RELATION_MENTION_ONLY
    if present_params and present_claims:
        target_type = "param_claim"
    elif present_params:
        target_type = "param"
    elif present_claims:
        target_type = "claim"
    else:
        target_type = "signal"
    return {
        "relation": relation,
        "target_type": target_type,
        "supported_param_codes": supported_param_codes,
        "contradicted_param_codes": contradicted_param_codes,
        "supported_claim_codes": supported_claim_codes,
        "contradicted_claim_codes": contradicted_claim_codes,
        "param_snapshot": param_snapshot,
        "claim_snapshot": claim_snapshot,
    }


def _param_entry_present(entry: Any) -> bool:
    if not isinstance(entry, Mapping):
        return False
    value_presence = str(entry.get("value_presence") or "").lower()
    if value_presence in {"unknown", "missing", "missing_column", "empty"}:
        return False
    normalized_value = entry.get("normalized_value")
    if normalized_value is None and not str(entry.get("value_text") or "").strip():
        return False
    return True


def _compact_param_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return {}
    return {key: entry[key] for key in ("normalized_value", "numeric_value", "value_text", "value_presence", "quality_flags") if key in entry}


def _compact_claim_fact(row: entities.Core3SkuClaimFact) -> dict[str, Any]:
    return {
        "claim_code": row.claim_code,
        "claim_name": row.claim_name,
        "claim_dimension": row.claim_dimension,
        "param_support_status": row.param_support_status,
        "supporting_param_codes": row.supporting_param_codes or [],
        "confidence": row.confidence,
    }


def _detect_polarity(text_value: str) -> str:
    normalized = _normalize_comment_text(text_value)
    positive = _has_positive(normalized)
    negative = _has_negative(normalized)
    if positive and negative:
        return POLARITY_MIXED
    if negative:
        return POLARITY_NEGATIVE
    if positive:
        return POLARITY_POSITIVE
    return POLARITY_NEUTRAL


def _has_positive(normalized_text: str) -> bool:
    return any(
        token in normalized_text
        for token in (
            "好",
            "清晰",
            "流畅",
            "不卡",
            "不错",
            "满意",
            "喜欢",
            "值得",
            "划算",
            "便宜",
            "信赖",
            "相信",
            "推荐",
            "复购",
            "真实",
            "鲜艳",
            "震撼",
            "安静",
            "省电",
            "凉快",
            "暖和",
            "舒服",
        )
    )


def _has_negative(normalized_text: str) -> bool:
    guarded = (
        ("卡顿", ("不卡", "不卡顿", "没卡", "不卡机")),
        ("广告", ("无广告", "没广告", "没有广告", "广告少")),
        ("反光", ("不反光", "无反光")),
        ("拖影", ("无拖影", "没有拖影", "不拖影")),
        ("刺眼", ("不刺眼", "不太刺眼")),
    )
    for token, guards in guarded:
        if token in normalized_text and not any(guard in normalized_text for guard in guards):
            return True
    return any(
        token in normalized_text
        for token in (
            "太差",
            "不好",
            "不清楚",
            "模糊",
            "卡死",
            "慢",
            "失望",
            "不值",
            "后悔",
            "差劲",
            "偏色",
            "漏光",
            "暗",
            "音质差",
        )
    )


def _evidence_strength(text_value: str, polarity: str) -> str:
    if polarity == POLARITY_NEGATIVE:
        return "strong"
    if re.search(r"\d{2,}", text_value) or any(token in text_value for token in ("非常", "特别", "很", "太", "明显")):
        return "strong"
    if len(str(text_value)) >= 12:
        return "medium"
    return "weak"


def _fact_confidence(polarity: str, relation: str, dimension_type: str) -> Decimal:
    if dimension_type == DIMENSION_TYPE_SERVICE:
        return Decimal("0.7000")
    if relation == RELATION_CONTRADICTS:
        return Decimal("0.7600")
    if relation == RELATION_SUPPORTS and polarity == POLARITY_POSITIVE:
        return Decimal("0.8500")
    if polarity == POLARITY_NEUTRAL:
        return Decimal("0.6200")
    return Decimal("0.7300")


def _source_keys_by_polarity(rows: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        result[row["polarity"]].add(row["source_comment_key"])
    for polarity in (POLARITY_POSITIVE, POLARITY_NEGATIVE, POLARITY_MIXED, POLARITY_NEUTRAL):
        result.setdefault(polarity, set())
    return result


def _dimension_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["dimension_code"]].append(row)
    return {
        dimension_code: {
            "dimension_name": group_rows[0]["dimension_name"],
            "dimension_type": group_rows[0]["dimension_type"],
            "fact_atom_count": len(group_rows),
            "sentence_count": len({row["source_comment_key"] for row in group_rows}),
            "polarity_counts": dict(sorted(Counter(row["polarity"] for row in group_rows).items())),
            "subdimension_codes": sorted({row["subdimension_code"] for row in group_rows}),
            "supported_param_codes": sorted({code for row in group_rows for code in row["supported_param_codes"]}),
            "contradicted_param_codes": sorted({code for row in group_rows for code in row["contradicted_param_codes"]}),
            "supported_claim_codes": sorted({code for row in group_rows for code in row["supported_claim_codes"]}),
            "contradicted_claim_codes": sorted({code for row in group_rows for code in row["contradicted_claim_codes"]}),
            "examples": _sample_examples(group_rows, limit=3),
        }
        for dimension_code, group_rows in sorted(grouped.items())
    }


def _signal_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    signal_rows = [row for row in rows if row["dimension_type"] in {DIMENSION_TYPE_AUDIENCE, DIMENSION_TYPE_USE_CASE, DIMENSION_TYPE_BRAND, DIMENSION_TYPE_COMPETITOR}]
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        grouped[row["dimension_type"]].append(row)
    return {
        dimension_type: {
            "signal_count": len(group_rows),
            "sku_sentence_count": len({row["source_comment_key"] for row in group_rows}),
            "subdimension_counts": dict(sorted(Counter(row["subdimension_code"] for row in group_rows).items())),
            "polarity_counts": dict(sorted(Counter(row["polarity"] for row in group_rows).items())),
            "examples": _sample_examples(group_rows, limit=3),
        }
        for dimension_type, group_rows in sorted(grouped.items())
    }


def _support_summary(rows: Sequence[Mapping[str, Any]], *, code_field: str, contradiction_field: str) -> dict[str, Any]:
    support_counter: Counter[str] = Counter()
    contradiction_counter: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for code in row[code_field]:
            support_counter[code] += 1
            if len(examples[code]) < 3:
                examples[code].append(_example_payload(row))
        for code in row[contradiction_field]:
            contradiction_counter[code] += 1
            if len(examples[code]) < 3:
                examples[code].append(_example_payload(row))
    return {
        "supported_counts": dict(sorted(support_counter.items())),
        "contradicted_counts": dict(sorted(contradiction_counter.items())),
        "examples": dict(sorted(examples.items())),
    }


def _profile_quality_flags(
    rows: Sequence[Mapping[str, Any]],
    *,
    param_profile: entities.Core3SkuParamProfile | None,
    claim_facts: Mapping[str, Sequence[entities.Core3SkuClaimFact]],
) -> list[str]:
    flags = []
    if not rows:
        flags.append("no_comment_fact_matched")
    if param_profile is None:
        flags.append("param_profile_missing")
    if not claim_facts:
        flags.append("claim_fact_profile_missing")
    if any(row["support_relation"] == RELATION_CONTRADICTS for row in rows):
        flags.append("comment_contradicts_existing_param_or_claim")
    if any(row["dimension_type"] == DIMENSION_TYPE_SERVICE for row in rows):
        flags.append("service_fulfillment_comment_excluded")
    return flags


def _distinct_sentence_count(rows: Sequence[Mapping[str, Any]], polarity: str) -> int:
    return len({row["source_comment_key"] for row in rows if row["polarity"] == polarity})


def _sample_examples(rows: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for row in rows:
        key = (row["sku_code"], row["source_comment_key"], row["subdimension_code"])
        if key in seen:
            continue
        seen.add(key)
        result.append(_example_payload(row))
        if len(result) >= limit:
            break
    return result


def _example_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": row["sku_code"],
        "source_comment_key": row["source_comment_key"],
        "subdimension_code": row["subdimension_code"],
        "subdimension_name": row["subdimension_name"],
        "polarity": row["polarity"],
        "comment_text": row["clean_comment_text"],
        "evidence_ids": list(row["evidence_ids"] or []),
    }


def _matched_patterns(text_value: str, patterns: Sequence[str]) -> list[str]:
    normalized = _normalize_comment_text(text_value)
    return [pattern for pattern in patterns if re.search(pattern, normalized, flags=re.IGNORECASE)]


def _brand_trust_supported(text_value: str) -> bool:
    normalized = _normalize_comment_text(text_value)
    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in (
            "大品牌",
            "老品牌",
            "老牌",
            "信赖",
            "信任",
            "相信",
            "质量.{0,4}保证",
            "值得购买",
            "放心购买",
            "放心入",
            "靠谱",
        )
    )


def _warnings(
    summary: Mapping[str, Any],
    *,
    param_profiles: Mapping[str, Any],
    claim_facts: Mapping[str, Any],
    sku_codes: Sequence[str],
) -> list[str]:
    warnings = []
    if int(summary.get("input_comment_sentence_count") or 0) == 0:
        warnings.append("m05c_empty_comment_input")
    if int(summary.get("sku_profile_count") or 0) == 0:
        warnings.append("m05c_empty_sku_profile_output")
    if sku_codes and len(param_profiles) < len(set(sku_codes)):
        warnings.append("m05c_param_profile_missing_for_some_skus")
    if sku_codes and len(claim_facts) < len(set(sku_codes)):
        warnings.append("m05c_claim_fact_profile_missing_for_some_skus")
    if int(summary.get("contradicted_fact_count") or 0) > 0:
        warnings.append("m05c_comment_contradiction_review_required")
    warnings.extend(str(item) for item in summary.get("llm_warnings") or [])
    return warnings


def _param_rule_version_for_product_category(product_category: str) -> str:
    return CORE3_M03B_AC_RULE_VERSION if str(product_category or "").upper() == "AC" else CORE3_M03B_RULE_VERSION


def _claim_rule_version_for_product_category(product_category: str) -> str:
    return CORE3_M04C_AC_RULE_VERSION if str(product_category or "").upper() == "AC" else CORE3_M04C_TV_RULE_VERSION


def _comment_taxonomy_version_for_product_category(product_category: str) -> str:
    return CORE3_M05C_AC_TAXONOMY_VERSION if str(product_category or "").upper() == "AC" else CORE3_M05C_TV_TAXONOMY_VERSION


def _comment_rule_version_for_product_category(product_category: str) -> str:
    return CORE3_M05C_AC_RULE_VERSION if str(product_category or "").upper() == "AC" else CORE3_M05C_TV_RULE_VERSION


def _write_summary(result: ParamRepositoryWriteResult) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "record_count": len(result.records),
    }


def _normalize_comment_text(value: Any) -> str:
    return str(value or "").lower().replace(" ", "").replace("_", "").replace("-", "")


def _present_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _sku_allowed(sku_code: str | None, prefix: str | None) -> bool:
    if not sku_code:
        return False
    return not prefix or str(sku_code).startswith(prefix)


def _first_present(values: Iterable[Any]) -> Any | None:
    for value in values:
        if value is not None and str(value).strip():
            return value
    return None


def _unique_preserve_order(values: Iterable[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _nested_get(row: Mapping[str, Any], outer_key: str, inner_key: str) -> Any:
    outer = row.get(outer_key)
    if isinstance(outer, Mapping):
        return outer.get(inner_key)
    return None


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _comment_profile_id(project_id: str, batch_id: str, sku_code: str, taxonomy_version: str, rule_version: str) -> str:
    return stable_hash(
        {"project_id": project_id, "batch_id": batch_id, "sku_code": sku_code, "taxonomy_version": taxonomy_version, "rule_version": rule_version},
        version=M05C_PROFILE_ID_HASH_VERSION,
    )[:120]


def _comment_fact_id(project_id: str, batch_id: str, sku_code: str, source_comment_key: str, subdimension_code: str, rule_version: str) -> str:
    return stable_hash(
        {"project_id": project_id, "batch_id": batch_id, "sku_code": sku_code, "source_comment_key": source_comment_key, "subdimension_code": subdimension_code, "rule_version": rule_version},
        version=M05C_FACT_ID_HASH_VERSION,
    )[:120]


def _comment_coverage_id(project_id: str, batch_id: str, taxonomy_version: str, coverage_type: str, coverage_key: str, rule_version: str) -> str:
    return stable_hash(
        {"project_id": project_id, "batch_id": batch_id, "taxonomy_version": taxonomy_version, "coverage_type": coverage_type, "coverage_key": coverage_key, "rule_version": rule_version},
        version=M05C_COVERAGE_ID_HASH_VERSION,
    )[:120]


def _source_comment_key(sku_code: str, sentence_seq: int | None, comment_text: str, index: int) -> str:
    return "generated:" + stable_hash(
        {"sku_code": sku_code, "sentence_seq": sentence_seq, "comment_text": comment_text, "index": index},
        version="m05c-source-comment-key-v1",
    )[:40]


def _taxonomy_summary(taxonomy: M05CCommentTaxonomy) -> dict[str, Any]:
    return {
        "taxonomy_version": taxonomy.taxonomy_version,
        "product_category": taxonomy.product_category,
        "dimensions": [
            {
                "dimension_code": dimension.dimension_code,
                "dimension_name": dimension.dimension_name,
                "dimension_type": dimension.dimension_type,
            }
            for dimension in taxonomy.dimensions
        ],
        "subdimensions": [
            {
                "subdimension_code": item.subdimension_code,
                "subdimension_name": item.subdimension_name,
                "dimension_code": item.dimension_code,
                "dimension_type": item.dimension_type,
                "linked_param_codes": list(item.linked_param_codes),
                "linked_claim_codes": list(item.linked_claim_codes),
            }
            for item in taxonomy.subdimensions
        ],
    }


def _normalize_payload(model_cls: Any, payload: Any, *, project_id: str, category_code: str) -> dict[str, Any]:
    if hasattr(payload, "to_record_payload"):
        raw_payload = payload.to_record_payload()
    elif isinstance(payload, Mapping):
        raw_payload = dict(payload)
    else:
        raise TypeError("M05C repository payload must be a mapping or provide to_record_payload()")
    raw_payload.setdefault("project_id", project_id)
    raw_payload.setdefault("category_code", category_code)
    model_fields = set(model_cls.__table__.columns.keys())
    return {key: value for key, value in raw_payload.items() if key in model_fields}


def _update_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    immutable_fields = primary_keys | {"created_at"}
    for field_name, field_value in _jsonable(payload).items():
        if field_name in immutable_fields:
            continue
        if hasattr(existing, field_name):
            setattr(existing, field_name, field_value)


def _assert_same_hash(existing: Any, payload: Mapping[str, Any], *, hash_field: str | None, unique_fields: tuple[str, ...], model_name: str) -> None:
    if hash_field is None:
        return
    incoming_hash = payload.get(hash_field)
    existing_hash = getattr(existing, hash_field)
    if incoming_hash != existing_hash:
        unique_key = {field_name: payload.get(field_name) for field_name in unique_fields}
        raise ParamRepositoryHashConflictError(f"{model_name} unique key already exists with different {hash_field}: {unique_key}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


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
        module_code=Core3ModuleCode.M05C,
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
            "module_version": CORE3_M05C_MODULE_VERSION,
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
        module_code=Core3ModuleCode.M05C,
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
            "module_version": CORE3_M05C_MODULE_VERSION,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
