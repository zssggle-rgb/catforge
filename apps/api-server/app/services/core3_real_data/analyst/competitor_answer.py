"""Business-facing competitor answer generation.

This module turns the lower-level analyst atoms into a compact XiaoAo answer
and a detailed report payload. It is deterministic and does not call an LLM.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from hashlib import sha256
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal


ReportMode = Literal["none", "markdown", "feishu-doc"]
FeishuCardPublishStatus = Literal["disabled", "sent", "failed"]

PRICE_BAND_ORDER = {
    "low": 0,
    "mid_low": 1,
    "mid": 2,
    "mid_high": 3,
    "high": 4,
}

SCORE_WEIGHTS = {
    "purchase_pool": Decimal("0.20"),
    "battlefield": Decimal("0.15"),
    "user_task": Decimal("0.20"),
    "target_group": Decimal("0.20"),
    "value_anchor": Decimal("0.15"),
    "replacement_pressure": Decimal("0.05"),
    "market_validation": Decimal("0.05"),
}

ROLE_WEIGHTS = {
    "primary": Decimal("1.00"),
    "primary_user_task": Decimal("1.00"),
    "primary_target_group": Decimal("1.00"),
    "primary_battlefield": Decimal("1.00"),
    "secondary": Decimal("0.75"),
    "secondary_user_task": Decimal("0.75"),
    "secondary_target_group": Decimal("0.75"),
    "secondary_battlefield": Decimal("0.75"),
    "comment_observed": Decimal("0.45"),
    "user_observed": Decimal("0.45"),
    "user_observed_battlefield": Decimal("0.45"),
    "opportunity": Decimal("0.35"),
    "opportunity_battlefield": Decimal("0.35"),
    "latent": Decimal("0.35"),
    "latent_capability": Decimal("0.35"),
    "brand_claimed": Decimal("0.25"),
    "brand_claimed_battlefield": Decimal("0.25"),
    "drag_factor": Decimal("-0.30"),
    "drag_factor_battlefield": Decimal("-0.30"),
    "unmet_need": Decimal("-0.30"),
}

BATTLEFIELD_NAMES = {
    "BF_SMALL_SCREEN_ESSENTIAL_VALUE": "小屏刚需性价比",
    "BF_SMALL_SMART_EASY_USE": "小屏智能易用",
    "BF_MAINSTREAM_FAMILY_VALUE": "主流家庭性价比",
    "BF_MAINSTREAM_LIVING_BALANCE": "主流客厅均衡体验",
    "BF_LARGE_SCREEN_VALUE_UPGRADE": "大屏换新性价比",
    "BF_LARGE_SCREEN_FAMILY_CINEMA": "大屏家庭影院",
    "BF_PREMIUM_PICTURE_UPGRADE": "高端画质升级",
    "BF_PREMIUM_VALUE_DOWNTRADE": "高配下探价值",
    "BF_GAMING_SPORTS_FLUENCY": "游戏体育流畅",
    "BF_EYE_CARE_FAMILY_COMFORT": "家庭护眼舒适",
    "BF_SMART_CONNECTED_EXPERIENCE": "智能互联体验",
    "BF_GIANT_HOME_THEATER_FLAGSHIP": "巨幕家庭影院旗舰",
    "BF_GIANT_SCREEN_VALUE": "巨幕价值下探",
    "BF_WALL_SMALL_ENTRY_VALUE": "1匹及以下挂机入门价值",
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

TASK_NAMES = {
    "TASK_MAINSTREAM_LIVING_VIEWING": "主流客厅日常观影",
    "TASK_CINEMA_IMMERSION": "影院沉浸观影",
    "TASK_PREMIUM_PICTURE_EXPERIENCE": "高端画质体验",
    "TASK_LARGE_SCREEN_UPGRADE": "大屏换新升级",
    "TASK_GAMING_CONSOLE_ENTERTAINMENT": "主机游戏娱乐",
    "TASK_SPORTS_MOTION_WATCHING": "体育赛事观看",
    "TASK_EYE_CARE_LONG_WATCHING": "长时间护眼观看",
    "TASK_SENIOR_EASY_OPERATION": "长辈易用操作",
    "TASK_BEDROOM_SECOND_SCREEN": "卧室/副屏小空间",
    "TASK_SMART_CASTING_IOT": "投屏互联与智能控制",
    "TASK_HOME_DECOR_SPACE_FIT": "新家装修与空间融合",
    "TASK_VALUE_FOR_MONEY_PURCHASE": "预算内高性价比购买",
    "TASK_FAST_COOL_HEAT": "快速制冷制热",
    "TASK_STABLE_TEMPERATURE": "稳定控温",
    "TASK_SLEEP_QUIET": "睡眠静音",
    "TASK_ENERGY_SAVING_LONG_USE": "长时使用省电",
    "TASK_SOFT_WIND_NO_DIRECT": "柔风防直吹",
    "TASK_LARGE_SPACE_COVERAGE": "大空间覆盖",
    "TASK_HEALTH_CLEAN_AIR": "健康洁净空气",
    "TASK_DEHUMIDIFY_HUMID_CLIMATE": "潮湿除湿",
    "TASK_SMART_REMOTE_CONTROL": "智能远程控制",
    "TASK_INSTALL_SPACE_FIT": "安装空间适配",
    "TASK_VALUE_SUBSIDY_PURCHASE": "价格补贴划算购买",
    "TASK_RELIABLE_LONG_TERM_USE": "长期可靠使用",
}

GROUP_NAMES = {
    "TG_MAINSTREAM_FAMILY_VIEWER": "主流家庭观影用户",
    "TG_LARGE_SCREEN_UPGRADER": "大屏换新升级用户",
    "TG_PREMIUM_AV_ENTHUSIAST": "高端影音体验用户",
    "TG_GIANT_HOME_THEATER_BUYER": "巨幕家庭影院用户",
    "TG_VALUE_MAXIMIZER": "性价比理性用户",
    "TG_GAMING_SPORTS_USER": "游戏体育娱乐用户",
    "TG_CHILD_FAMILY_LONG_WATCH": "儿童家庭长看用户",
    "TG_SENIOR_PARENT_FRIENDLY": "长辈友好使用用户",
    "TG_BEDROOM_RENTAL_SECOND_SCREEN": "卧室副屏/租房用户",
    "TG_SMART_CONNECTED_USER": "投屏互联智能用户",
    "TG_RENTER_SMALL_ROOM": "租房小空间用户",
    "TG_VALUE_REPLACEMENT_BUYER": "换新性价比用户",
    "TG_BEDROOM_SLEEP_SENSITIVE": "卧室睡眠敏感用户",
    "TG_FAMILY_LONG_USE_SAVER": "家庭长时使用省电用户",
    "TG_CHILD_ELDER_COMFORT": "儿童老人舒适敏感家庭",
    "TG_LIVING_ROOM_LARGE_SPACE": "客厅大空间用户",
    "TG_SMART_REMOTE_USER": "智能远程控制用户",
    "TG_HOME_DECOR_SPACE_FIT": "新家装修空间适配用户",
    "TG_HUMID_SOUTH_USER": "南方潮湿除湿用户",
    "TG_BRAND_QUALITY_TRUST_BUYER": "品牌品质信任用户",
}

ROLE_CN = {
    "primary_direct": "首选直接竞品",
    "strong_direct": "强配置对标竞品",
    "price_adjacent": "价格贴身竞品",
    "downtrade_diversion": "价格下探分流竞品",
    "uptrade_alternative": "上探替代竞品",
    "scenario_alternative": "场景替代竞品",
    "excluded": "排除候选",
}

CLAIM_LABELS_CN = {
    "tv_claim_ai_large_model": "AI 大模型/智能能力",
    "tv_claim_camera_interaction": "摄像头互动",
    "tv_claim_casting_connectivity": "投屏互联",
    "tv_claim_chip_performance": "芯片性能",
    "tv_claim_dolby_audio_video": "杜比音画",
    "tv_claim_energy_efficiency": "能效表现",
    "tv_claim_eye_care_display": "护眼显示",
    "tv_claim_flush_wall_mount": "贴墙安装",
    "tv_claim_full_screen_design": "全面屏设计",
    "tv_claim_gaming_low_latency": "游戏低延迟",
    "tv_claim_hdmi21_connectivity": "HDMI 2.1 连接",
    "tv_claim_hdr_high_brightness": "高亮度 HDR",
    "tv_claim_high_refresh": "高刷新率",
    "tv_claim_high_refresh_rate": "高刷新率",
    "tv_claim_local_dimming": "分区控光",
    "tv_claim_memory_storage": "内存/存储",
    "tv_claim_miniled": "MiniLED 显示",
    "tv_claim_miniled_display": "MiniLED 显示",
    "tv_claim_oled_self_lit": "OLED 自发光",
    "tv_claim_picture_engine_ai": "AI 画质引擎",
    "tv_claim_premium_material_design": "高端材质外观",
    "tv_claim_qd_miniled_display": "量子点 MiniLED",
    "tv_claim_rgb_miniled_display": "RGB MiniLED",
    "tv_claim_slim_body": "超薄机身",
    "tv_claim_slim_full_screen": "超薄全面屏",
    "tv_claim_smart_home_iot": "智能家居互联",
    "tv_claim_smart_iot": "智能互联",
    "tv_claim_speaker_sound": "音响效果",
    "tv_claim_theater_scene": "影院音画体验",
    "tv_claim_ultra_thin_design": "超薄设计",
    "tv_claim_value_price": "性价比",
    "tv_claim_voice_control": "语音控制",
    "tv_claim_wide_color_accuracy": "广色域/色彩还原",
    "ac_claim_energy_efficiency_apf": "高能效/APF/省电",
    "ac_claim_ai_energy_saving": "AI 省电算法",
    "ac_claim_fast_cooling_heating": "速冷速热",
    "ac_claim_wide_temperature_operation": "宽温域可靠运行",
    "ac_claim_large_airflow_coverage": "大风量/全域送风",
    "ac_claim_soft_wind_no_direct": "柔风/防直吹",
    "ac_claim_quiet_sleep": "静音睡眠",
    "ac_claim_precision_temperature_control": "精准控温/恒温",
    "ac_claim_humidity_dehumidification": "除湿/温湿双控",
    "ac_claim_fresh_air": "新风换气",
    "ac_claim_purification_antibacterial": "净化/除菌/抗菌",
    "ac_claim_self_cleaning": "自清洁/自洁",
    "ac_claim_smart_app_voice_iot": "APP/语音/IoT 智控",
    "ac_claim_installation_space_design": "外观/空间适配",
    "ac_claim_durability_core_material": "耐用品质/核心材料",
    "ac_claim_warranty_install_service": "包修/安装/售后服务",
    "ac_claim_authority_sales_certification": "行业背书/认证/销量",
    "ac_claim_price_value_subsidy": "价格/补贴/性价比",
}

PARAM_LABELS_CN = {
    "ai_capability_flag": "AI 能力",
    "ai_model_capability_flag": "AI 大模型能力",
    "body_thickness_mm": "机身厚度",
    "camera_flag": "摄像头",
    "declared_brightness_nit_or_band": "亮度",
    "declared_refresh_rate_hz": "刷新率",
    "display_technology": "显示技术",
    "display_tech_class": "显示技术",
    "backlight_source": "背光源",
    "hdmi21_port_count": "HDMI 2.1 接口",
    "hdr_capability_flag": "HDR 能力",
    "local_dimming_zone_count": "控光分区",
    "memory_storage": "内存/存储",
    "mini_led_flag": "MiniLED",
    "mini_led_type": "MiniLED 类型",
    "processor_chip_model": "芯片",
    "quantum_dot_flag": "量子点",
    "resolution_label": "分辨率",
    "resolution_pixels": "分辨率像素",
    "screen_size_inch": "尺寸",
    "slim_design_label": "超薄标签",
    "speaker_power_w": "音响功率",
    "wall_mount_flush_flag": "贴墙安装",
    "wide_color_gamut_pct": "色域覆盖",
    "wifi_capability_flag": "无线连接",
    "airflow_volume_m3h": "循环风量",
    "comfort_airflow_flag": "舒适风",
    "cooling_capacity_w": "制冷量",
    "energy_efficiency_ratio": "能效比/APF",
    "energy_grade_normalized": "能效等级",
    "fresh_air_flag": "新风",
    "heat_cool_mode": "冷暖类型",
    "heating_capacity_w": "制热量",
    "horsepower_hp": "匹数",
    "installation_hp_segment": "安装匹数段",
    "installation_type": "安装形态",
    "inverter_flag": "变频",
    "purification_flag": "净化除菌",
    "self_cleaning_flag": "自清洁",
    "smart_sensing_flag": "智能感应",
    "voice_control_flag": "语音控制",
    "wifi_control_flag": "WiFi/APP 控制",
}

PARAM_GROUP_NAMES = {
    "core_picture_params": "画质显示",
    "core_gaming_params": "游戏流畅",
    "core_system_params": "系统智能",
    "core_eye_care_params": "护眼舒适",
    "picture": "画质显示",
    "gaming": "游戏流畅",
    "system": "系统智能",
    "eye_care": "护眼舒适",
}

SIZE_TIER_NAMES = {
    "small_32_45": "32-45 寸小屏段",
    "medium_46_59": "46-59 寸中屏段",
    "large_60_69": "60-69 寸主流大屏段",
    "xlarge_70_85": "70-85 寸大屏升级段",
    "giant_98_plus": "98 寸及以上巨幕段",
    "wall_hp_1_or_below": "1匹及以下挂机",
    "wall_hp_1_5": "1.5匹挂机",
    "wall_hp_2": "2匹挂机",
    "wall_hp_3": "3匹挂机",
    "floor_hp_2": "2匹柜机",
    "floor_hp_3": "3匹柜机",
    "floor_hp_3_plus": "3匹及以上柜机",
}

PRICE_BAND_NAMES = {
    "low": "低价带",
    "mid_low": "中低价带",
    "mid": "中价带",
    "mid_high": "中高价带",
    "high": "高价带",
}

INDEX_CN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一"]

CLAIM_VALUE_ROLE_CN = {
    "premium_driver_estimated": "强溢价卖点",
    "sales_driver_estimated": "强销量卖点",
    "basic_threshold": "基础门槛卖点",
    "value_bundle_claim": "组合型增值卖点",
    "weak_user_perception_claim": "用户感知不足卖点",
    "high_price_competitor_intercept": "高价竞品拦截卖点",
    "price_up_opportunity": "价格上探机会卖点",
    "user_validated_need": "用户验证需求",
    "brand_claim_only": "厂家主张卖点",
    "opportunity_gap": "机会缺口",
    "drag_factor": "拖后腿卖点",
    "sample_insufficient": "样本不足待复核",
}

CLAIM_VALUE_ROLE_BASE = {
    "premium_driver_estimated": Decimal("70"),
    "sales_driver_estimated": Decimal("60"),
    "value_bundle_claim": Decimal("55"),
    "basic_threshold": Decimal("35"),
    "weak_user_perception_claim": Decimal("25"),
    "high_price_competitor_intercept": Decimal("40"),
    "price_up_opportunity": Decimal("40"),
    "user_validated_need": Decimal("45"),
    "brand_claim_only": Decimal("25"),
    "opportunity_gap": Decimal("30"),
    "drag_factor": Decimal("15"),
    "sample_insufficient": Decimal("10"),
}

CLAIM_VALUE_CATEGORY_ORDER = [
    "强溢价卖点",
    "强销量卖点",
    "组合型增值卖点",
    "基础门槛卖点",
    "本品优势卖点（待量化）",
    "竞品优势/本品短板",
    "用户感知风险/拖后腿",
    "厂家主张待市场验证",
]

CLAIM_VALUE_CATEGORY_RANK = {label: index for index, label in enumerate(CLAIM_VALUE_CATEGORY_ORDER)}
CLAIM_VALUE_TEXT_ONLY_CATEGORIES = {
    "本品优势卖点（待量化）",
    "竞品优势/本品短板",
    "用户感知风险/拖后腿",
    "厂家主张待市场验证",
}


@dataclass(frozen=True)
class ReportPublishResult:
    status: str
    url: str | None = None
    message_cn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "url": self.url, "message_cn": self.message_cn}


@dataclass(frozen=True)
class FeishuCardPublishResult:
    status: FeishuCardPublishStatus
    message_cn: str
    message_id: str | None = None
    chat_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message_cn": self.message_cn,
            "message_id": self.message_id,
            "chat_id": self.chat_id,
        }


def build_competitor_answer(
    *,
    target: dict[str, Any],
    target_fact_brief: dict[str, Any],
    target_claim_value: dict[str, Any] | None = None,
    target_claim_contribution: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]],
    top_n: int = 3,
    max_chat_chars: int = 600,
    with_report: str = "none",
    report_title: str | None = None,
) -> dict[str, Any]:
    enriched = [_enrich_competitor(target, target_fact_brief, item) for item in competitors]
    enriched = sorted(enriched, key=_sort_key, reverse=True)
    _assign_top_roles(enriched)
    buckets = _bucket_competitors(enriched)
    top_competitors = _select_top_competitors(enriched, target=target, top_n=max(top_n, 0))
    title = report_title or f"{_display_name(target)} 重点竞品分析报告"
    dashboard_payload_for_report = build_competitor_dashboard_payload(
        target=target,
        target_fact_brief=target_fact_brief,
        top_competitors=top_competitors,
        report_url=None,
    )
    markdown = render_competitor_report(
        title=title,
        target=target,
        target_fact_brief=target_fact_brief,
        target_claim_value=target_claim_value,
        target_claim_contribution=target_claim_contribution,
        top_competitors=top_competitors,
        all_competitors=enriched,
        dashboard_payload=dashboard_payload_for_report,
    )
    publish_result = _publish_report(title=title, markdown=markdown, with_report=with_report)
    short_answer = render_short_answer(
        target=target,
        target_fact_brief=target_fact_brief,
        top_competitors=top_competitors,
        report_url=publish_result.url,
        max_chat_chars=max_chat_chars,
    )
    dashboard_payload = build_competitor_dashboard_payload(
        target=target,
        target_fact_brief=target_fact_brief,
        top_competitors=top_competitors,
        report_url=publish_result.url,
    )
    feishu_card_payload = render_feishu_card_payload(dashboard_payload)
    return {
        "short_answer": short_answer,
        "report_url": publish_result.url,
        "report_status": publish_result.status,
        "report_message_cn": publish_result.message_cn,
        "report_payload": {
            "title": title,
            "markdown": markdown if with_report == "markdown" else None,
            "url": publish_result.url,
            "status": publish_result.status,
        },
        "dashboard_payload": dashboard_payload,
        "feishu_card_payload": feishu_card_payload,
        "top_competitors": top_competitors,
        "candidate_buckets": buckets,
        "selection_policy_cn": [
            "先限定同一购买池，再比较主辅价值战场、用户任务、目标客群的加权重合。",
            "关键价值锚点用于判断候选是否会改变目标 SKU 的成交理由。",
            "销量只用于验证候选具备真实市场分流能力，不作为首选竞品的主排序依据。",
        ],
        "display_policy": {
            "send_short_answer_as_is": True,
            "prefer_feishu_card": True,
            "card_delivery_stdout": True,
            "fallback_to_short_answer": False,
            "report_as_evidence": True,
            "max_chat_chars": max_chat_chars,
            "hide_internal_fields": True,
        },
        "all_candidates": enriched,
    }


def weighted_overlap_from_roles(overlap: dict[str, Any]) -> dict[str, Any]:
    target_items = overlap.get("target_items") or []
    candidate_items = overlap.get("candidate_items") or []
    target_weights = {str(item.get("code")): _role_weight(item.get("roles") or []) for item in target_items if item.get("code")}
    candidate_weights = {str(item.get("code")): _role_weight(item.get("roles") or []) for item in candidate_items if item.get("code")}
    positive_codes = set(target_weights) | set(candidate_weights)
    intersection = Decimal("0")
    union = Decimal("0")
    for code in positive_codes:
        target_weight = max(target_weights.get(code, Decimal("0")), Decimal("0"))
        candidate_weight = max(candidate_weights.get(code, Decimal("0")), Decimal("0"))
        intersection += min(target_weight, candidate_weight)
        union += max(target_weight, candidate_weight)
    negative_codes = {
        code
        for code in set(target_weights) & set(candidate_weights)
        if target_weights.get(code, Decimal("0")) < 0 or candidate_weights.get(code, Decimal("0")) < 0
    }
    primary_hits = [
        code
        for code in positive_codes
        if _is_primary(target_items, code) and code in candidate_weights and candidate_weights.get(code, Decimal("0")) > 0
    ]
    weighted_score = intersection / union if union else Decimal("0")
    target_positive_count = len([value for value in target_weights.values() if value > 0])
    risk_score = Decimal(len(negative_codes)) / Decimal(max(target_positive_count, 1))
    return {
        "weighted_overlap_score": _float(weighted_score),
        "positive_weighted_intersection": _float(intersection),
        "positive_weighted_union": _float(union),
        "risk_overlap_score": _float(risk_score),
        "primary_hit_count": len(primary_hits),
        "primary_hit_codes": sorted(primary_hits),
        "negative_overlap_codes": sorted(negative_codes),
    }


def render_short_answer(
    *,
    target: dict[str, Any],
    target_fact_brief: dict[str, Any],
    top_competitors: list[dict[str, Any]],
    report_url: str | None,
    max_chat_chars: int,
) -> str:
    target_name = _display_name(target)
    if not top_competitors:
        suffix = _report_suffix(report_url)
        return f"{target_name} 当前没有足够证据形成稳定重点竞品。{suffix}"
    evidence_state = _target_evidence_state(target_fact_brief)
    names = "、".join(_display_name(item.get("candidate") or {}) for item in top_competitors)
    lines = [f"{target_name} 的重点竞品建议看{len(top_competitors)}款：{names}。"]
    for index, item in enumerate(top_competitors, start=1):
        name = _display_name(item.get("candidate") or {})
        anchors = _join_cn(item["value_anchor"]["shared_anchors"][:4]) or "关键价值锚点"
        if index == 1:
            if evidence_state["semantic_verified"]:
                lines.append(
                    f"{name}排第一，核心原因是同一购买池内替代关系最完整，"
                    f"主辅价值战场、用户任务和目标客群的有效重合更完整，"
                    f"共同价值锚点集中在{anchors}，"
                    f"形成{item['replacement_pressure']['type_cn']}。"
                )
            else:
                lines.append(
                    f"{name}排第一，主要因为它与{target_name}处在同一购买池，"
                    f"参数和卖点可替代性最强；共同锚点集中在{anchors}。"
                )
        else:
            pressure = item["replacement_pressure"]["type_cn"]
            if not evidence_state["semantic_verified"] and pressure == "价值替代压力":
                pressure = "参数/卖点替代压力"
            lines.append(
                f"{name}属于{item['role_cn']}，主要压力来自{pressure}。"
            )
    if not evidence_state["semantic_verified"]:
        lines.append("当前缺少用户评论或语义图谱验证，以上排序更偏同池配置、卖点和价格替代判断。")
    lines.append(_report_suffix(report_url))
    text = "".join(lines)
    return _compress_answer(text, target=target, top_competitors=top_competitors, report_url=report_url, max_chat_chars=max_chat_chars)


def build_competitor_dashboard_payload(
    *,
    target: dict[str, Any],
    target_fact_brief: dict[str, Any],
    top_competitors: list[dict[str, Any]],
    report_url: str | None,
) -> dict[str, Any]:
    """Build the business dashboard consumed by Feishu cards and XiaoAo."""

    target_name = _display_name(target)
    competitors = [
        _dashboard_competitor_payload(index, item, report_url=report_url)
        for index, item in enumerate(top_competitors[:3], start=1)
    ]
    report_links = _dashboard_report_links(report_url)
    summary_cn = _dashboard_summary(target_name, competitors, target_fact_brief)
    return {
        "schema_version": "competitor_dashboard_v1",
        "title": f"{target_name} 重点竞品看板",
        "target": {
            "sku_code": target.get("sku_code"),
            "brand_name": target.get("brand_name"),
            "model_name": target.get("model_name"),
            "display_name": target_name,
            "summary": _dashboard_target_summary(target, target_fact_brief),
            "market": _dashboard_target_market_snapshot(target, target_fact_brief),
        },
        "summary_cn": summary_cn,
        "competitors": competitors,
        "report_evidence_links": report_links,
        "display_policy": {
            "main_answer": "feishu_card",
            "report_as_evidence": True,
            "card_delivery_stdout": True,
            "fallback_to_short_answer": False,
            "link_preview_optional": True,
        },
    }


def render_feishu_card_payload(dashboard_payload: dict[str, Any]) -> dict[str, Any]:
    """Render a Feishu interactive-card payload from the dashboard contract."""

    title = str(dashboard_payload.get("title") or "重点竞品看板")
    target = dashboard_payload.get("target") or {}
    competitors = [item for item in dashboard_payload.get("competitors") or [] if isinstance(item, dict)]
    elements: list[dict[str, Any]] = [
        _feishu_markdown(_dashboard_conclusion_markdown(dashboard_payload, competitors))
    ]
    if competitors:
        elements.append({"tag": "hr"})
        elements.append(_feishu_markdown("**多维评分雷达图**"))
        elements.append(_feishu_score_radar_chart(competitors))
        battlefield_chart_values = _dashboard_battlefield_chart_values(competitors)
        if battlefield_chart_values:
            elements.append({"tag": "hr"})
            elements.append(_feishu_markdown("**价值战场重合结构**"))
            elements.append(_feishu_battlefield_overlap_chart(battlefield_chart_values))
        elements.append({"tag": "hr"})
        elements.append(_feishu_markdown("**竞品与市场表现**"))
        elements.append(_feishu_competitor_market_table(target, competitors))
    action = _feishu_report_action(dashboard_payload)
    if action:
        elements.append({"tag": "hr"})
        elements.append(action)
    card = {
        "schema": "2.0",
        "config": {
            "summary": {"content": title},
            "width_mode": "fill",
            "update_multi": True,
        },
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": str(target.get("summary") or "")[:80]},
        },
        "body": {"elements": elements},
    }
    return _trim_feishu_card(card)


def render_competitor_dashboard_markdown(dashboard_payload: dict[str, Any]) -> list[str]:
    """Render the dashboard contract as the first screen of the evidence report."""

    competitors = [item for item in dashboard_payload.get("competitors") or [] if isinstance(item, dict)]
    lines = [
        "## 重点竞品看板",
        "",
        _dashboard_conclusion_markdown(dashboard_payload, competitors),
        "",
    ]
    if not competitors:
        return lines
    lines.extend(
        [
            "### 重点竞品 Top 3",
            "",
            *_dashboard_competitor_ranking_lines(competitors),
            "",
            "### 多维评分雷达图数据",
            "",
            *_dashboard_score_dimension_lines(competitors),
            "",
            "### 市场验证条形图",
            "",
            *_dashboard_market_chart_lines(competitors),
        ]
    )
    return lines


def render_competitor_report(
    *,
    title: str,
    target: dict[str, Any],
    target_fact_brief: dict[str, Any],
    target_claim_value: dict[str, Any] | None = None,
    target_claim_contribution: dict[str, Any] | None = None,
    top_competitors: list[dict[str, Any]],
    all_competitors: list[dict[str, Any]],
    dashboard_payload: dict[str, Any] | None = None,
) -> str:
    target_name = _display_name(target)
    target_sections = _fact_sections(target_fact_brief)
    lines = [
        f"# {title}",
        "",
    ]
    if dashboard_payload:
        lines.extend(render_competitor_dashboard_markdown(dashboard_payload))
        lines.append("")
    lines.extend(["## 一、分析结论", ""])
    if top_competitors:
        lines.extend(_analysis_conclusion_lines(target_name, target, target_sections, top_competitors, all_competitors))
    else:
        lines.append(f"{target_name} 当前没有足够证据形成稳定重点竞品。")
    lines.extend(
        [
            "",
            "## 二、分析过程",
            "",
            "竞品排序采用 100 分制，重点解释候选 SKU 是否会进入同一批用户的最终候选清单。评分不是单纯参数相似度，也不是销量排名，而是把购买池、价值战场、用户任务、目标客群、关键价值锚点和市场验证合并判断。",
            "",
        ]
    )
    lines.extend(_scoring_method_lines(target))
    lines.extend(["", "### 2.1 候选 SKU 综合评分", ""])
    lines.extend(_candidate_score_table_lines(top_competitors, all_competitors))
    lines.extend(["", "### 2.2 购买池评分依据", ""])
    lines.extend(_purchase_pool_score_lines(top_competitors, all_competitors))
    lines.extend(["", "### 2.3 价值战场评分依据", ""])
    lines.extend(_dimension_score_lines(top_competitors, all_competitors, dimension="battlefield"))
    lines.extend(["", "### 2.4 用户任务和目标客群评分依据", ""])
    lines.extend(_task_group_score_lines(top_competitors, all_competitors))
    lines.extend(["", "### 2.5 关键价值锚点、替代压力和市场验证依据", ""])
    lines.extend(_anchor_market_score_lines(top_competitors, all_competitors))
    lines.extend(["", "## 三、四个产品详情链接", ""])
    lines.append(f"- [{target_name} 产品画像](#profile-target)")
    for index, item in enumerate(top_competitors[:3], start=1):
        lines.append(f"- [{_display_name(item.get('candidate') or {})} 产品画像](#profile-competitor-{index})")
    lines.extend(["", "## 四、四个产品横向详细对比", ""])
    lines.extend(
        _product_comparison_lines(
            target_name,
            target,
            target_sections,
            target_claim_value=target_claim_value,
            target_claim_contribution=target_claim_contribution,
            top_competitors=top_competitors[:3],
        )
    )
    lines.extend(["", '<a id="profile-target"></a>', f"## 五、{target_name} 产品画像", ""])
    lines.extend(
        _product_profile_lines(
            "5",
            target_name,
            target,
            target_sections,
            competitor_item=None,
            claim_value=target_claim_value,
            claim_contribution=target_claim_contribution,
        )
    )
    for index, item in enumerate(top_competitors[:3], start=1):
        candidate = item.get("candidate") or {}
        candidate_name = _display_name(candidate)
        candidate_sections = _fact_sections(item.get("candidate_fact_brief") or {})
        lines.extend(
            [
                "",
                f'<a id="profile-competitor-{index}"></a>',
                f"## {INDEX_CN[index + 4]}、{candidate_name} 产品画像",
                "",
            ]
        )
        lines.extend(
            _product_profile_lines(
                str(index + 5),
                candidate_name,
                candidate,
                candidate_sections,
                competitor_item=item,
                claim_value=item.get("candidate_claim_value") or {},
                claim_contribution=item.get("candidate_claim_contribution") or {},
            )
        )
    return "\n".join(lines)


def _analysis_conclusion_lines(
    target_name: str,
    target: dict[str, Any],
    target_sections: dict[str, Any],
    top_competitors: list[dict[str, Any]],
    all_competitors: list[dict[str, Any]],
) -> list[str]:
    category_noun = _category_noun(target)
    price_context = _price_context_noun(target)
    names = [_display_name(item.get("candidate") or {}) for item in top_competitors[:3]]
    roles = [f"{_display_name(item.get('candidate') or {})} 是{_report_role_cn(item)}" for item in top_competitors[:3]]
    lines = [
        f"{target_name} 的前三个重点竞品建议锁定为：{_join_cn(names)}。三者分别代表三种竞争压力：{_join_cn(roles)}。",
        "",
    ]
    first = top_competitors[0] if top_competitors else None
    if first:
        first_name = _display_name(first.get("candidate") or {})
        first_sections = _fact_sections(first.get("candidate_fact_brief") or {})
        target_battlefields = _primary_secondary_text(target_sections.get("value_battlefield") or {}, "battlefield")
        first_battlefields = _primary_secondary_text(first_sections.get("value_battlefield") or {}, "battlefield")
        target_tasks = _primary_secondary_text(target_sections.get("user_task") or {}, "task")
        first_tasks = _primary_secondary_text(first_sections.get("user_task") or {}, "task")
        target_groups = _primary_secondary_text(target_sections.get("target_group") or {}, "group")
        first_groups = _primary_secondary_text(first_sections.get("target_group") or {}, "group")
        shared_anchors = _join_cn(first["value_anchor"]["shared_anchors"][:5]) or "关键价值锚点"
        target_stronger = _join_cn(first["value_anchor"]["target_stronger_anchors"][:4]) or "技术型高端体验"
        candidate_stronger = _join_cn(first["value_anchor"]["candidate_stronger_anchors"][:4]) or "场景型高端体验"
        lines.extend(
            [
                f"{first_name} 排第一，核心原因不是单项参数最接近，而是它在 {target_name} 的主要竞争结构里形成了最完整的替代关系。{first['purchase_pool']['reason_cn']}，用户会在同一次升级型{category_noun}购买中把它们放进候选清单。",
                "",
                f"从价值战场看，{target_name} 的竞争重心是{target_battlefields or '当前主战场'}，{first_name} 的竞争重心是{first_battlefields or '当前主战场'}。{first_name} 没有偏离 {target_name} 的核心战场，而是切入目标 SKU 的主竞争范围。",
                "",
                f"从用户任务看，{target_name} 主要承接{target_tasks or '当前主要用户任务'}；{first_name} 主要承接{first_tasks or '当前主要用户任务'}。两者不完全相同，但高度交叉，交叉点正好是{price_context}最核心的购买场景。",
                "",
                f"从目标客群看，{target_name} 覆盖{target_groups or '当前核心客群'}，{first_name} 覆盖{first_groups or '当前核心客群'}。共同客群越靠近主客群，竞品成立强度越高。",
                "",
                f"从关键价值锚点看，两款共同争夺{shared_anchors}。{target_name} 的成交理由更偏{target_stronger}，{first_name} 的成交理由更偏{candidate_stronger}。用户比较时，本质上是在比较两套高端体验解释方式。",
                "",
                f"从替代压力看，{first_name} 对 {target_name} 的威胁来自{first['replacement_pressure']['type_cn']}。{first['replacement_pressure']['reason_cn']}，因此它最可能影响 {target_name} 的最终成交判断。",
                "",
            ]
        )
    for index, item in enumerate(top_competitors[1:3], start=2):
        candidate_name = _display_name(item.get("candidate") or {})
        dimensions = _join_cn(item["shared_business_context"][:5]) or "核心购买场景"
        lines.extend(
            [
                f"{candidate_name} 排第{index}。它同样处在 {item['purchase_pool']['reason_cn']}，在{dimensions}上与 {target_name} 形成重合，对 {target_name} 的压力主要来自{item['replacement_pressure']['type_cn']}。",
                "",
            ]
        )
    price_adjacent = _first_candidate_by_role(all_competitors, excluded=top_competitors, roles={"price_adjacent"})
    if price_adjacent:
        name = _display_name(price_adjacent.get("candidate") or {})
        lines.extend(
            [
                f"{name} 虽然价格最贴近 {target_name}，但竞品强度不应只按价格排序。它在主辅价值战场、主辅任务和核心客群上的有效重合弱于前三重点竞品，因此更适合归为价格贴身竞品，而不是前三重点防守对象。",
                "",
            ]
        )
    market_parts = [
        f"{_display_name(item.get('candidate') or {})} 周均约{_format_unit_count(item['market_validation'].get('avg_weekly_sales_volume')) or '未知'}台"
        for item in top_competitors[:3]
    ]
    lines.append(
        f"市场验证方面，{_join_cn(market_parts)}，说明重点竞品具备真实分流能力。销量只用于验证竞品有效性，不用于决定竞品成立；排序核心仍然是购买池、价值战场、用户任务、目标客群和价值锚点对 {target_name} 成交理由的替代强度。"
    )
    return lines


def _scoring_method_lines(target: dict[str, Any]) -> list[str]:
    category_noun = _category_noun(target)
    return [
        "| 评分维度 | 权重 | 判断问题 |",
        "| --- | ---: | --- |",
        "| 购买池 | 20 | 是否同尺寸、同价位或相邻价位，是否会进入同一次购买决策 |",
        "| 价值战场 | 15 | 主辅价值战场是否重合，是否争夺同一类付费场景 |",
        f"| 用户任务 | 20 | 用户买{category_noun}要完成的使用任务是否高度交叉 |",
        "| 目标客群 | 20 | 是否争夺同一批核心人群和相邻人群 |",
        "| 关键价值锚点 | 15 | 参数、卖点、评论能否形成可替代的成交理由 |",
        "| 替代压力 | 5 | 是否会改变用户对目标 SKU 价值判断 |",
        "| 市场验证 | 5 | 是否具备真实线上成交能力，能否形成实际分流 |",
    ]


def _candidate_score_table_lines(top_competitors: list[dict[str, Any]], all_competitors: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| 排名 | 候选 SKU | 竞争角色 | 购买池 20 | 价值战场 15 | 用户任务 20 | 目标客群 20 | 价值锚点 15 | 替代压力 5 | 市场验证 5 | 综合分 | 排序判断 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for rank, item in enumerate(_report_candidates(top_competitors, all_competitors), start=1):
        score = _candidate_score_breakdown(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    _display_name(item.get("candidate") or {}),
                    _report_role_cn(item),
                    str(score["purchase_pool"]),
                    str(score["battlefield"]),
                    str(score["user_task"]),
                    str(score["target_group"]),
                    str(score["value_anchor"]),
                    str(score["replacement_pressure"]),
                    str(score["market_validation"]),
                    str(score["total"]),
                    _candidate_sort_reason(item),
                ]
            )
            + " |"
        )
    return lines


def _purchase_pool_score_lines(top_competitors: list[dict[str, Any]], all_competitors: list[dict[str, Any]]) -> list[str]:
    lines = ["| 候选 SKU | 分数 | 依据 |", "| --- | ---: | --- |"]
    for item in _report_candidates(top_competitors, all_competitors):
        score = _candidate_score_breakdown(item)
        candidate = item.get("candidate") or {}
        lines.append(
            f"| {_display_name(candidate)} | {score['purchase_pool']} | {item['purchase_pool']['reason_cn']}；价格关系为{_price_gap_phrase(candidate.get('price_gap_pct_to_target'))} |"
        )
    return lines


def _dimension_score_lines(top_competitors: list[dict[str, Any]], all_competitors: list[dict[str, Any]], *, dimension: str) -> list[str]:
    label = {"battlefield": "价值战场"}.get(dimension, dimension)
    lines = [f"| 候选 SKU | 分数 | {label}重合判断 |", "| --- | ---: | --- |"]
    for item in _report_candidates(top_competitors, all_competitors):
        score = _candidate_score_breakdown(item)
        matched = _join_cn(item["matched_dimensions"].get(dimension, [])[:6]) or "重合不足"
        lines.append(f"| {_display_name(item.get('candidate') or {})} | {score[dimension]} | {matched} |")
    return lines


def _task_group_score_lines(top_competitors: list[dict[str, Any]], all_competitors: list[dict[str, Any]]) -> list[str]:
    lines = ["| 候选 SKU | 用户任务分 | 目标客群分 | 依据 |", "| --- | ---: | ---: | --- |"]
    for item in _report_candidates(top_competitors, all_competitors):
        score = _candidate_score_breakdown(item)
        tasks = _join_cn(item["matched_dimensions"].get("user_task", [])[:4]) or "用户任务重合不足"
        groups = _join_cn(item["matched_dimensions"].get("target_group", [])[:4]) or "目标客群重合不足"
        lines.append(f"| {_display_name(item.get('candidate') or {})} | {score['user_task']} | {score['target_group']} | 用户任务：{tasks}；目标客群：{groups} |")
    return lines


def _anchor_market_score_lines(top_competitors: list[dict[str, Any]], all_competitors: list[dict[str, Any]]) -> list[str]:
    lines = ["| 候选 SKU | 价值锚点分 | 替代压力分 | 市场验证分 | 依据 |", "| --- | ---: | ---: | ---: | --- |"]
    for item in _report_candidates(top_competitors, all_competitors):
        score = _candidate_score_breakdown(item)
        anchors = _join_cn(item["value_anchor"]["shared_anchors"][:5]) or "关键价值锚点不足"
        lines.append(
            f"| {_display_name(item.get('candidate') or {})} | {score['value_anchor']} | {score['replacement_pressure']} | {score['market_validation']} | {anchors}；{item['replacement_pressure']['reason_cn']}；{item['market_validation']['summary_cn']} |"
        )
    return lines


def _product_comparison_lines(
    target_name: str,
    target: dict[str, Any],
    target_sections: dict[str, Any],
    *,
    target_claim_value: dict[str, Any] | None,
    target_claim_contribution: dict[str, Any] | None,
    top_competitors: list[dict[str, Any]],
) -> list[str]:
    products = _comparison_products(
        target_name,
        target,
        target_sections,
        target_claim_value=target_claim_value,
        target_claim_contribution=target_claim_contribution,
        top_competitors=top_competitors,
    )
    lines: list[str] = [
        "本节把本品和前三重点竞品放在同一张业务比较表里：纵轴是比较内容，横轴是四个产品，重点看同一购买池中的市场位置、价值战场、用户任务、目标客群、卖点和参数证据差异。",
        "",
        "### 4.1 市场画像",
        "",
    ]
    lines.extend(_comparison_table_lines(products, ["尺寸", "尺寸价格池", "均价", "周均销量", "所在池空间", "池内销量表现", "相对本品", "市场角色"], _market_comparison_values))
    lines.extend(["", "### 4.2 价值战场画像", ""])
    lines.extend(_comparison_table_lines(products, ["命中的固定价值战场", "主价值战场", "辅价值战场", "补充证据判断", "主价值战场市场空间", "本品在主战场销量承接", "与本品重合"], lambda product: _semantic_comparison_values(product, profile_type="battlefield")))
    lines.extend(["", "### 4.3 用户任务画像", ""])
    lines.extend(_comparison_table_lines(products, ["命中的固定用户任务", "主用户任务", "辅用户任务", "补充证据判断", "主用户任务市场空间", "本品在主任务销量承接", "与本品重合"], lambda product: _semantic_comparison_values(product, profile_type="task")))
    lines.extend(["", "### 4.4 目标客群画像", ""])
    lines.extend(_comparison_table_lines(products, ["命中的固定目标客群", "主目标客群", "辅目标客群", "补充证据判断", "主目标客群市场空间", "本品在主客群销量承接", "与本品重合"], lambda product: _semantic_comparison_values(product, profile_type="group")))
    lines.extend(["", "### 4.5 卖点画像", ""])
    lines.extend(
        _comparison_table_lines(
            products,
            ["事实卖点", "评论支持卖点", "评论反向卖点", "参数支撑状态", "需复核表达", "共同价值锚点"],
            _claim_fact_comparison_values,
        )
    )
    lines.extend(["", "### 4.6 参数画像", ""])
    lines.extend(
        _comparison_table_lines(
            products,
            _parameter_comparison_dimensions(target),
            _param_comparison_values,
        )
    )
    lines.extend(["", "### 4.7 卖点价值量化", ""])
    lines.extend(_claim_value_comparison_table_lines(products))
    lines.extend(["", _claim_value_footnote()])
    return lines


def _comparison_products(
    target_name: str,
    target: dict[str, Any],
    target_sections: dict[str, Any],
    *,
    target_claim_value: dict[str, Any] | None,
    target_claim_contribution: dict[str, Any] | None,
    top_competitors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    products = [
        {
            "name": target_name,
            "sku": target,
            "sections": target_sections,
            "competitor_item": None,
            "claim_value": _extract_claim_value_payload(target_claim_value),
            "claim_contribution": _extract_claim_contribution_payload(target_claim_contribution),
        }
    ]
    for item in top_competitors[:3]:
        candidate = item.get("candidate") or {}
        products.append(
            {
                "name": _display_name(candidate),
                "sku": candidate,
                "sections": _fact_sections(item.get("candidate_fact_brief") or {}),
                "competitor_item": item,
                "claim_value": _extract_claim_value_payload(item.get("candidate_claim_value") or {}),
                "claim_contribution": _extract_claim_contribution_payload(item.get("candidate_claim_contribution") or {}),
            }
        )
    return products


def _comparison_table_lines(
    products: list[dict[str, Any]],
    row_labels: list[str],
    value_builder: Any,
    *,
    skip_empty_rows: bool = False,
) -> list[str]:
    value_maps = [value_builder(product) for product in products]
    lines = [
        "| 比较内容 | " + " | ".join(_markdown_cell(product["name"]) for product in products) + " |",
        "| --- | " + " | ".join("---" for _product in products) + " |",
    ]
    for label in row_labels:
        raw_values = [values.get(label) for values in value_maps]
        if skip_empty_rows and all(_is_empty_claim_value_cell(value) for value in raw_values):
            continue
        values = [_markdown_cell(value if value else "未形成稳定量化证据") for value in raw_values]
        lines.append("| " + " | ".join([_markdown_cell(label), *values]) + " |")
    return lines


def _claim_value_comparison_table_lines(products: list[dict[str, Any]]) -> list[str]:
    if not products:
        return ["卖点价值量化待生成。"]
    product_groups = [_claim_value_category_groups(_claim_value_rows_with_index(product.get("claim_value") or {}, dedupe=False)) for product in products]
    target_groups = product_groups[0] if product_groups else []
    if not target_groups:
        return ["卖点价值量化待生成。"]
    group_maps = [_claim_value_group_map(groups) for groups in product_groups]
    rows: list[dict[str, Any]] = []
    by_category = _claim_value_groups_by_category(target_groups)
    for category in CLAIM_VALUE_CATEGORY_ORDER:
        for group in by_category.get(category, [])[:5]:
            rows.append(group)
    if not rows:
        return ["卖点价值量化待生成。"]
    lines = [
        "| 本品分类与卖点 | " + " | ".join(_markdown_cell(product["name"]) for product in products) + " |",
        "| --- | " + " | ".join("---" for _product in products) + " |",
    ]
    for group in rows[:12]:
        category = str(group.get("category") or "")
        claim_key = str(group.get("claim_code") or group.get("claim_name") or "")
        label = f"{category}：{group.get('claim_name') or claim_key}"
        cells: list[str] = []
        for index, group_map in enumerate(group_maps):
            matched = group_map.get((category, claim_key))
            if matched:
                cells.append(_claim_value_group_summary_cell(matched))
            elif index == 0:
                cells.append("本品该分类量化待生成")
            else:
                cells.append(f"未进入{category}")
        lines.append("| " + " | ".join([_markdown_cell(label), *[_markdown_cell(cell) for cell in cells]]) + " |")
    lines.append("")
    lines.append("横向比较口径：本表以本品的业务分类和具体卖点为基准；竞品只有在同一卖点、同一分类下形成量化结果时才展示，竞品同一卖点如落入其他分类不混列。")
    return lines


def _is_empty_claim_value_cell(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text in {"暂无稳定证据", "未形成稳定量化证据"}


def _market_comparison_values(product: dict[str, Any]) -> dict[str, str]:
    sku = product.get("sku") or {}
    sections = product.get("sections") or {}
    competitor_item = product.get("competitor_item")
    metrics = _market_metrics(sections)
    position = _market_position(sections)
    price = metrics.get("price_wavg") or metrics.get("price_latest") or sku.get("weighted_price")
    weekly_sales = metrics.get("avg_weekly_sales_volume") or sku.get("avg_weekly_sales_volume")
    size = position.get("screen_size_inch") or sku.get("screen_size_inch")
    price_band = PRICE_BAND_NAMES.get(str(position.get("price_band_in_size_tier") or sku.get("price_band_in_size_tier")), "价格带未知")
    size_tier = SIZE_TIER_NAMES.get(str(position.get("size_tier") or sku.get("size_tier")), "尺寸段未知")
    pool = (sections.get("market") or {}).get("market_pool") or {}
    if competitor_item:
        candidate = competitor_item.get("candidate") or {}
        relative = f"{_price_gap_phrase(candidate.get('price_gap_pct_to_target'))}；{(competitor_item.get('market_validation') or {}).get('summary_cn') or '市场验证待补充'}"
        role = _report_role_cn(competitor_item)
    else:
        relative = "本品基准"
        role = f"{price_band}核心 SKU"
    return {
        "尺寸": _size_cell(size, size_tier, sku),
        "尺寸价格池": f"{size_tier} × {price_band}",
        "均价": _format_money(price) or "未知",
        "周均销量": f"{_format_unit_count(weekly_sales) or '未知'} 台",
        "所在池空间": f"{_format_unit_count(pool.get('total_sales_volume')) or '未知'}台；周均{_format_unit_count(pool.get('total_avg_weekly_sales_volume')) or '未知'}台；SKU数{_format_number(pool.get('sku_count')) or '未知'}",
        "池内销量表现": f"第{_format_number(pool.get('target_rank_by_avg_weekly_sales')) or '未知'}名；占池内销量{_pct_or_unknown(pool.get('target_sales_volume_share'))}",
        "相对本品": relative,
        "市场角色": role,
    }


def _size_cell(size: Any, size_tier: str, sku: dict[str, Any]) -> str:
    formatted_size = _format_number(size)
    if formatted_size:
        return f"{formatted_size} 寸"
    if _is_ac_context(sku, size_tier):
        return size_tier if size_tier and size_tier != "尺寸段未知" else "匹数/安装形态未知"
    return "未知 寸"


def _semantic_comparison_values(product: dict[str, Any], *, profile_type: str) -> dict[str, str]:
    sections = product.get("sections") or {}
    profile_key = {"battlefield": "value_battlefield", "task": "user_task", "group": "target_group"}[profile_type]
    dimension_key = {"battlefield": "battlefield", "task": "user_task", "group": "target_group"}[profile_type]
    rows = _semantic_rows(sections.get(profile_key) or {}, profile_type=profile_type)
    positions = _semantic_position_by_code(sections, profile_type=profile_type)
    primary_marker = {"battlefield": "主战场", "task": "主任务", "group": "主客群"}[profile_type]
    secondary_marker = {"battlefield": "辅战场", "task": "辅任务", "group": "辅客群"}[profile_type]
    primary_codes = [code for code, _label, relation, _reason in rows if primary_marker in relation]
    primary_code = primary_codes[0] if primary_codes else (rows[0][0] if rows else "")
    primary_position = positions.get(primary_code, {})
    competitor_item = product.get("competitor_item")
    if competitor_item:
        matched = _join_cn((competitor_item.get("matched_dimensions") or {}).get(dimension_key, [])[:6]) or "重合不足"
        overlap = _pct_or_unknown((competitor_item.get("weighted_overlap") or {}).get(dimension_key))
        overlap_text = f"{matched}；加权重合{overlap}"
    else:
        overlap_text = "本品基准"
    return {
        "命中的固定价值战场": _semantic_dimensions_with_relation(rows),
        "主价值战场": _labels_by_relation(rows, primary_marker),
        "辅价值战场": _labels_by_relation(rows, secondary_marker),
        "补充证据判断": _relation_status_detail(rows, primary_marker, secondary_marker),
        "主价值战场市场空间": _semantic_space_with_label(rows, primary_code, primary_position),
        "本品在主战场销量承接": _semantic_performance_with_label(rows, primary_code, primary_position),
        "命中的固定用户任务": _semantic_dimensions_with_relation(rows),
        "主用户任务": _labels_by_relation(rows, primary_marker),
        "辅用户任务": _labels_by_relation(rows, secondary_marker),
        "主用户任务市场空间": _semantic_space_with_label(rows, primary_code, primary_position),
        "本品在主任务销量承接": _semantic_performance_with_label(rows, primary_code, primary_position),
        "命中的固定目标客群": _semantic_dimensions_with_relation(rows),
        "主目标客群": _labels_by_relation(rows, primary_marker),
        "辅目标客群": _labels_by_relation(rows, secondary_marker),
        "主目标客群市场空间": _semantic_space_with_label(rows, primary_code, primary_position),
        "本品在主客群销量承接": _semantic_performance_with_label(rows, primary_code, primary_position),
        "与本品重合": overlap_text,
    }


def _labels_by_relation(rows: list[tuple[str, str, str, str]], *markers: str) -> str:
    labels = [label for _code, label, relation, _reason in rows if any(marker in relation for marker in markers)]
    return _join_cn(labels[:6]) or "暂无稳定证据"


def _semantic_dimensions_with_relation(rows: list[tuple[str, str, str, str]]) -> str:
    items = [f"{label}（{relation}）" for _code, label, relation, _reason in rows]
    return _join_cn(items[:8]) or "暂无稳定证据"


def _relation_status_detail(rows: list[tuple[str, str, str, str]], *excluded_markers: str) -> str:
    grouped: dict[str, list[str]] = {}
    for _code, label, relation, _reason in rows:
        relation_labels = [item.strip() for item in re.split(r"[、和]", relation) if item.strip()]
        for relation_label in relation_labels:
            if any(marker == relation_label for marker in excluded_markers):
                continue
            grouped.setdefault(relation_label, [])
            if label not in grouped[relation_label]:
                grouped[relation_label].append(label)
    if not grouped:
        return "暂无补充证据判断"
    return "；".join(f"{relation}：{_join_cn(labels[:5])}" for relation, labels in grouped.items())


def _label_for_semantic_code(rows: list[tuple[str, str, str, str]], code: str) -> str:
    for row_code, label, _relation, _reason in rows:
        if row_code == code:
            return label
    return _label_code(code)


def _semantic_space_with_label(rows: list[tuple[str, str, str, str]], code: str, position: dict[str, Any]) -> str:
    label = _label_for_semantic_code(rows, code)
    prefix = f"{label}：" if label else ""
    return f"{prefix}{_semantic_market_space_text(position)}"


def _semantic_performance_with_label(rows: list[tuple[str, str, str, str]], code: str, position: dict[str, Any]) -> str:
    label = _label_for_semantic_code(rows, code)
    prefix = f"{label}：" if label else ""
    relation = _relation_for_semantic_code(rows, code)
    return f"{prefix}{_semantic_sku_performance_text(position, relation=relation)}"


def _relation_for_semantic_code(rows: list[tuple[str, str, str, str]], code: str) -> str:
    for row_code, _label, relation, _reason in rows:
        if row_code == code:
            return relation
    return ""


def _extract_claim_value_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return {}
    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("sku_claim_value")
        return nested if isinstance(nested, dict) else {}
    nested = payload.get("sku_claim_value")
    if isinstance(nested, dict):
        return nested
    if isinstance(payload.get("claim_values"), list) or isinstance(payload.get("role_counts"), dict):
        return payload
    return {}


def _extract_claim_contribution_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        return {}
    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("claim_contribution")
        return nested if isinstance(nested, dict) else {}
    nested = payload.get("claim_contribution")
    if isinstance(nested, dict):
        return nested
    if isinstance(payload.get("attributions"), list):
        return payload
    return {}


def _claim_value_rows_with_index(payload: dict[str, Any], *, dedupe: bool = True) -> list[dict[str, Any]]:
    rows = [dict(row) for row in payload.get("claim_values") or [] if isinstance(row, dict)]
    if not rows:
        return []
    max_price = max([_positive_decimal(((row.get("pool_effect") or {}).get("pool_claim_price_delta_abs"))) for row in rows] or [Decimal("0")])
    max_sales = max([_positive_decimal(((row.get("pool_effect") or {}).get("pool_claim_weekly_sales_delta_abs"))) for row in rows] or [Decimal("0")])
    max_amount = max([_positive_decimal(((row.get("pool_effect") or {}).get("pool_claim_weekly_sales_amount_delta_abs"))) for row in rows] or [Decimal("0")])
    for row in rows:
        pool_effect = row.get("pool_effect") or {}
        sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
        role = str(row.get("claim_value_role") or "")
        label = str(row.get("business_value_label") or _claim_role_cn(role))
        price_score = _ratio_score(_positive_decimal(pool_effect.get("pool_claim_price_delta_abs")), max_price, Decimal("15"))
        sales_score = _ratio_score(_positive_decimal(pool_effect.get("pool_claim_weekly_sales_delta_abs")), max_sales, Decimal("10"))
        amount_score = _ratio_score(_positive_decimal(pool_effect.get("pool_claim_weekly_sales_amount_delta_abs")), max_amount, Decimal("10"))
        share_score = min(_positive_decimal(sku_excess.get("contribution_share_in_sku")), Decimal("1")) * Decimal("10")
        confidence_score = min(_positive_decimal(row.get("attribution_confidence")), Decimal("1")) * Decimal("5")
        score = CLAIM_VALUE_ROLE_BASE.get(role, Decimal("10")) + price_score + sales_score + amount_score + share_score + confidence_score
        row["claim_value_index"] = int(min(Decimal("100"), max(Decimal("0"), score)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        row["claim_premium_index"] = row["claim_value_index"]
        row["business_value_label"] = label
        row.setdefault("business_value_meaning_cn", _claim_business_meaning(label))
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            -int(row.get("claim_value_index") or 0),
            str(row.get("claim_name") or row.get("claim_code") or ""),
        ),
    )
    return _dedupe_claim_value_rows(sorted_rows) if dedupe else sorted_rows


def _claim_value_category_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        category = _claim_value_display_category(row)
        claim_key = str(row.get("claim_code") or row.get("claim_name") or "")
        if not claim_key:
            claim_key = f"claim-{len(grouped)}"
        key = (category, claim_key)
        if key not in grouped:
            grouped[key] = {
                "category": category,
                "claim_code": row.get("claim_code"),
                "claim_key": claim_key,
                "claim_name": _claim_value_name(row),
                "rows": [],
                "battlefield_rows": [],
                "evidence_rows": [],
                "max_index": 0,
            }
        group = grouped[key]
        group["rows"].append(row)
        group["max_index"] = max(int(group.get("max_index") or 0), int(row.get("claim_value_index") or 0))
        if str(row.get("context_type") or "") == "battlefield":
            group["battlefield_rows"].append(row)
        else:
            group["evidence_rows"].append(row)
    result: list[dict[str, Any]] = []
    claim_keys_with_quantified_battlefields = {
        str(group.get("claim_key") or "")
        for group in grouped.values()
        if group.get("battlefield_rows")
        and str(group.get("category") or "") in {"强溢价卖点", "强销量卖点", "组合型增值卖点", "基础门槛卖点"}
    }
    for group in grouped.values():
        battlefield_rows = _dedupe_claim_value_battlefield_rows(group["battlefield_rows"])
        group["battlefield_rows"] = battlefield_rows
        if _claim_value_group_needs_nonquantified_category(group):
            if str(group.get("claim_key") or "") in claim_keys_with_quantified_battlefields:
                continue
            group["category"] = "本品优势卖点（待量化）"
        quant_groups = _claim_value_quant_groups(battlefield_rows)
        quant_rows = [item["representative"] for item in quant_groups if item.get("representative")]
        group["quant_groups"] = quant_groups
        group["total_price_explained"] = _sum_sku_excess_metric(quant_rows, "sku_excess_price_explained_abs", "price_premium_abs")
        group["total_sales_explained"] = _sum_sku_excess_metric(quant_rows, "sku_excess_weekly_sales_explained_abs", "weekly_sales_lift_abs")
        group["total_amount_explained"] = _sum_sku_excess_metric(quant_rows, "sku_excess_weekly_sales_amount_explained_abs", "weekly_sales_amount_lift_abs")
        group["battlefield_names"] = _unique_texts([_claim_context_text(row) for row in battlefield_rows])
        group["evidence_contexts"] = _unique_texts([_claim_context_text(row) for row in group["evidence_rows"]])
        group["representative"] = _best_claim_value_group_row(group)
        result.append(group)
    return sorted(
        result,
        key=lambda group: (
            CLAIM_VALUE_CATEGORY_RANK.get(str(group.get("category") or ""), 99),
            -int(group.get("max_index") or 0),
            str(group.get("claim_name") or ""),
        ),
    )


def _claim_value_group_needs_nonquantified_category(group: dict[str, Any]) -> bool:
    if group.get("battlefield_rows"):
        return False
    category = str(group.get("category") or "")
    if category not in {"强溢价卖点", "强销量卖点", "组合型增值卖点", "基础门槛卖点"}:
        return False
    return any(_claim_value_has_strong_fact_evidence(row) for row in group.get("rows") or [])


def _dedupe_claim_value_battlefield_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_context: dict[str, dict[str, Any]] = {}
    for row in rows:
        context_key = str(row.get("context_code") or row.get("context_name") or "")
        if not context_key:
            context_key = f"context-{len(best_by_context)}"
        existing = best_by_context.get(context_key)
        if existing is None or _claim_value_row_rank(row) > _claim_value_row_rank(existing):
            best_by_context[context_key] = row
    return list(best_by_context.values())


def _claim_value_row_rank(row: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
    return (
        _decimal(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")) or Decimal("0"),
        _decimal(sku_excess.get("sku_excess_weekly_sales_amount_explained_abs") or sku_excess.get("weekly_sales_amount_lift_abs")) or Decimal("0"),
        _decimal(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")) or Decimal("0"),
        _decimal(row.get("attribution_confidence")) or Decimal("0"),
    )


def _claim_value_groups_by_category(groups: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for group in groups:
        by_category.setdefault(str(group.get("category") or ""), []).append(group)
    return by_category


def _claim_value_group_map(groups: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        claim_key = str(group.get("claim_code") or group.get("claim_name") or "")
        if claim_key:
            result[(str(group.get("category") or ""), claim_key)] = group
    return result


def _claim_value_display_category(row: dict[str, Any]) -> str:
    label = _base_claim_value_label(str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role"))))
    if label in {"强溢价卖点", "强销量卖点", "组合型增值卖点", "基础门槛卖点"} and _claim_value_has_weak_sample_flag(row):
        return "本品优势卖点（待量化）" if _claim_value_has_strong_fact_evidence(row) else "样本不足待复核"
    if label in {"样本不足", "样本不足待复核"} and _claim_value_has_strong_fact_evidence(row):
        return "本品优势卖点（待量化）"
    if label in {"高价竞品拦截卖点", "价格上探机会卖点", "机会缺口"}:
        return "竞品优势/本品短板"
    if label in {"用户感知不足卖点", "拖后腿卖点"}:
        return "用户感知风险/拖后腿"
    if label == "厂家主张卖点":
        return "厂家主张待市场验证"
    return label


def _claim_value_has_weak_sample_flag(row: dict[str, Any]) -> bool:
    flags = {str(item) for item in (row.get("quality_flags") or row.get("quality_flags_json") or [])}
    return bool(flags & {"insufficient_comparison_group", "sample_weak", "sample_insufficient"})


def _claim_value_has_strong_fact_evidence(row: dict[str, Any]) -> bool:
    evidence = row.get("evidence_strength") or {}
    param = _decimal(evidence.get("param"))
    comment = _decimal(evidence.get("comment"))
    claim = _decimal(evidence.get("claim"))
    strong_values = [value for value in (param, comment, claim) if value is not None]
    return bool(strong_values) and sum(1 for value in strong_values if value >= Decimal("0.75")) >= 2


def _sum_sku_excess_metric(rows: list[dict[str, Any]], primary_key: str, fallback_key: str) -> Decimal:
    total = Decimal("0")
    for row in rows:
        sku_excess = row.get("sku_excess_explanation") or {}
        fallback = row.get("estimated_contribution") or {}
        number = _decimal(sku_excess.get(primary_key))
        if number is None:
            number = _decimal(fallback.get(fallback_key))
        if number is not None:
            total += number
    return total


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _best_claim_value_group_row(group: dict[str, Any]) -> dict[str, Any]:
    rows = group.get("battlefield_rows") or group.get("rows") or []
    if not rows:
        return {}
    return sorted(
        rows,
        key=lambda row: (
            -int(row.get("claim_value_index") or 0),
            -_positive_decimal((row.get("sku_excess_explanation") or {}).get("sku_excess_price_explained_abs") or (row.get("estimated_contribution") or {}).get("price_premium_abs")),
            _claim_context_text(row),
        ),
    )[0]


def _claim_value_group_summary_cell(group: dict[str, Any]) -> str:
    category = str(group.get("category") or "")
    battlefields = group.get("battlefield_names") or []
    price = _format_money(group.get("total_price_explained"))
    sales = _format_unit_count(group.get("total_sales_explained"))
    amount = _format_money(group.get("total_amount_explained"))
    if category == "本品优势卖点（待量化）":
        contexts = _join_cn((group.get("evidence_contexts") or [])[:4])
        return f"本品事实证据成立，当前价值战场对照样本不足，暂不做金额量化{f'；证据场景：{contexts}' if contexts else ''}"
    if category == "竞品优势/本品短板":
        return _claim_value_group_reason(group) or "竞品或同池强 SKU 表达更强，本品缺失或表达偏弱，当前不作为本品正向量化"
    if category == "用户感知风险/拖后腿":
        return _claim_value_group_reason(group) or "当前证据不足或存在负向信号，不进入正向价销量解释"
    if category == "厂家主张待市场验证":
        return _claim_value_group_reason(group) or "厂家表达存在，但评论或市场验证不足，不作为溢价或销量结论"
    if battlefields:
        parts = [
            f"战场价差合计{price or '0元'}",
            f"战场销量合计{sales or '0'}台/周",
            f"战场销额合计{amount or '0元'}/周",
            f"覆盖{_join_cn(battlefields[:4])}",
        ]
        return "；".join(parts)
    return _claim_value_group_reason(group) or "当前价值战场量化不足，需结合事实和评论继续观察"


def _claim_value_group_reason(group: dict[str, Any]) -> str:
    category = str(group.get("category") or "")
    if category == "本品优势卖点（待量化）":
        contexts = _join_cn((group.get("evidence_contexts") or [])[:4])
        return f"该卖点有参数、卖点事实和评论支撑，可作为本品优势表达；当前价值战场对照样本不足，暂不写金额量化{f'；证据场景：{contexts}' if contexts else ''}。"
    if category == "竞品优势/本品短板":
        return "同池竞品或高成交 SKU 在该卖点上表达更强，本品缺失或表达偏弱；该项用于识别补强方向，不作为本品正向价销量分摊。"
    if category == "用户感知风险/拖后腿":
        return "该卖点存在用户感知不足、负向反馈或证据支撑不足，可能削弱相关场景的成交解释。"
    if category == "厂家主张待市场验证":
        return "厂家表达存在，但当前评论和市场验证不足，暂不作为溢价或销量支撑。"
    row = group.get("representative") or {}
    return _claim_value_reason_text(row) if row else ""


def _claim_value_category_section_lines(category: str, groups: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = [f"#### {category}", ""]
    lines.extend(
        [
            "| 卖点 | 战场可解释价差合计 | 战场可解释销量合计 | 战场可解释销额合计 | 覆盖价值战场 | 证据 | 业务解释 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for group in groups:
        representative = group.get("representative") or {}
        battlefield_names = group.get("battlefield_names") or []
        quantified = bool(battlefield_names) and str(group.get("category") or "") not in CLAIM_VALUE_TEXT_ONLY_CATEGORIES
        lines.append(
            "| "
            + " | ".join(
                [
                    _claim_value_group_name(group),
                    _format_money(group.get("total_price_explained")) if quantified else "不作为正向量化",
                    f"{_format_unit_count(group.get('total_sales_explained')) or '暂不量化'}台/周" if quantified else "不作为正向量化",
                    f"{_format_money(group.get('total_amount_explained')) or '暂不量化'}/周" if quantified else "不作为正向量化",
                    _join_cn(battlefield_names[:5]) or "价值战场暂未形成稳定量化",
                    _claim_evidence_status_text(representative) if representative else "证据待补充",
                    _claim_value_group_reason(group) or _claim_value_group_summary_cell(group),
                ]
            )
            + " |"
        )
    detail_lines = [] if category in CLAIM_VALUE_TEXT_ONLY_CATEGORIES else _claim_value_battlefield_detail_lines(groups)
    if detail_lines:
        lines.extend(["", "价值战场明细：", "", *detail_lines])
    return lines


def _claim_value_group_name(group: dict[str, Any]) -> str:
    return str(group.get("claim_name") or group.get("claim_code") or "未命名卖点")


def _claim_value_representative_rows_for_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        representative = dict(group.get("representative") or {})
        if not representative:
            continue
        representative["business_value_label"] = str(group.get("category") or representative.get("business_value_label") or "")
        rows.append(representative)
    return rows


def _claim_value_battlefield_detail_lines(groups: list[dict[str, Any]]) -> list[str]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        for quant_group in (group.get("quant_groups") or [])[:5]:
            rows.append({"group": group, "quant_group": quant_group})
    if not rows:
        return []
    lines = [
        "| 卖点 | 价值战场 | 可比池价格差异 | 可比池销量差异 | 本品可解释价差份额 | 本品可解释销量份额 | 说明 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        group = item["group"]
        quant_group = item["quant_group"]
        row = quant_group["representative"]
        pool = row.get("pool_effect") or {}
        sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _claim_value_group_name(group),
                    _join_cn((quant_group.get("battlefield_names") or [])[:5]) or _claim_context_text(row),
                    _claim_pool_price_text(row),
                    _claim_pool_sales_text(pool.get("pool_claim_weekly_sales_delta_abs")),
                    _claim_sku_excess_price_text(row, sku_excess) or "不作为正向分摊",
                    _claim_sku_excess_sales_text(row, sku_excess) or "不作为正向分摊",
                    _claim_value_reason_text(row),
                ]
            )
            + " |"
        )
    return lines


def _claim_value_quant_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    order: list[tuple[str, ...]] = []
    for row in rows:
        signature = _claim_value_quant_signature(row)
        if signature is None:
            signature = (
                str(row.get("claim_code") or row.get("claim_name") or "claim"),
                str(row.get("context_code") or row.get("context_name") or len(order)),
            )
        if signature not in grouped:
            grouped[signature] = {"rows": [], "battlefield_names": []}
            order.append(signature)
        item = grouped[signature]
        item["rows"].append(row)
        context = _claim_context_text(row)
        if context and context not in item["battlefield_names"]:
            item["battlefield_names"].append(context)
    result: list[dict[str, Any]] = []
    for signature in order:
        item = grouped[signature]
        item["representative"] = _best_claim_value_quant_row(item["rows"])
        result.append(item)
    return sorted(
        result,
        key=lambda item: (
            -int((item.get("representative") or {}).get("claim_value_index") or 0),
            _join_cn(item.get("battlefield_names") or []),
        ),
    )


def _best_claim_value_quant_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return sorted(
        rows,
        key=lambda row: (
            -int(row.get("claim_value_index") or 0),
            _claim_context_text(row),
        ),
    )[0]


def _claim_value_quant_signature(row: dict[str, Any]) -> tuple[str, ...] | None:
    pool = row.get("pool_effect") or {}
    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
    metric_keys = (
        _claim_value_metric_key(pool.get("pool_claim_price_delta_abs")),
        _claim_value_metric_key(pool.get("pool_claim_weekly_sales_delta_abs")),
        _claim_value_metric_key(pool.get("pool_claim_weekly_sales_amount_delta_abs")),
        _claim_value_metric_key(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")),
        _claim_value_metric_key(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")),
        _claim_value_metric_key(sku_excess.get("sku_excess_weekly_sales_amount_explained_abs") or sku_excess.get("weekly_sales_amount_lift_abs")),
    )
    if not any(metric_keys):
        return None
    return (
        _base_claim_value_label(str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))),
        str(row.get("size_tier") or ""),
        str(row.get("price_band_group") or ""),
        *metric_keys,
    )


def _claim_value_display_rows(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    selected = rows[: max(limit, 0)] if limit else rows
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    order: list[tuple[str, ...]] = []
    for row in selected:
        signature = _claim_value_bundle_signature(row)
        if not signature:
            signature = (str(row.get("claim_code") or row.get("claim_name") or f"claim-{len(order)}"),)
        if signature not in grouped:
            grouped[signature] = []
            order.append(signature)
        grouped[signature].append(row)
    display_rows: list[dict[str, Any]] = []
    for signature in order:
        bundle = grouped[signature]
        display_rows.append(_claim_value_bundle_row(bundle) if len(bundle) > 1 else bundle[0])
    return display_rows


def _claim_value_bundle_signature(row: dict[str, Any]) -> tuple[str, ...] | None:
    pool = row.get("pool_effect") or {}
    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
    metric_keys = (
        _claim_value_metric_key(pool.get("pool_claim_price_delta_abs")),
        _claim_value_metric_key(pool.get("pool_claim_weekly_sales_delta_abs")),
        _claim_value_metric_key(pool.get("pool_claim_weekly_sales_amount_delta_abs")),
        _claim_value_metric_key(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")),
        _claim_value_metric_key(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")),
    )
    if not any(metric_keys):
        return None
    return (
        _base_claim_value_label(str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))),
        str(row.get("context_type") or ""),
        str(row.get("context_code") or ""),
        str(row.get("size_tier") or ""),
        str(row.get("price_band_group") or ""),
        *metric_keys,
    )


def _claim_value_metric_key(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return str(number.quantize(Decimal("0.0001")))


def _claim_value_bundle_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = dict(rows[0])
    names = [_claim_value_name(row) for row in rows]
    base_label = _base_claim_value_label(str(first.get("business_value_label") or _claim_role_cn(first.get("claim_value_role"))))
    pool = first.get("pool_effect") or {}
    sku_excess = {
        "sku_excess_price_explained_abs": _sum_claim_metric(rows, "sku_excess_explanation", "sku_excess_price_explained_abs", "estimated_contribution", "price_premium_abs"),
        "sku_excess_weekly_sales_explained_abs": _sum_claim_metric(rows, "sku_excess_explanation", "sku_excess_weekly_sales_explained_abs", "estimated_contribution", "weekly_sales_lift_abs"),
        "sku_excess_weekly_sales_amount_explained_abs": _sum_claim_metric(rows, "sku_excess_explanation", "sku_excess_weekly_sales_amount_explained_abs", "estimated_contribution", "weekly_sales_amount_lift_abs"),
        "contribution_share_in_sku": _sum_claim_metric(rows, "sku_excess_explanation", "contribution_share_in_sku", "estimated_contribution", "contribution_share_in_sku"),
    }
    first.update(
        {
            "claim_name": f"{_join_cn(names)}（组合）",
            "display_claim_names": names,
            "bundle_claim_count": len(rows),
            "bundle_rows": rows,
            "business_value_label": f"{base_label}组合",
            "market_contexts": _claim_value_bundle_contexts(rows),
            "pool_effect": pool,
            "sku_excess_explanation": sku_excess,
            "estimated_contribution": {
                "price_premium_abs": sku_excess["sku_excess_price_explained_abs"],
                "weekly_sales_lift_abs": sku_excess["sku_excess_weekly_sales_explained_abs"],
                "weekly_sales_amount_lift_abs": sku_excess["sku_excess_weekly_sales_amount_explained_abs"],
                "contribution_share_in_sku": sku_excess["contribution_share_in_sku"],
            },
            "evidence_strength": _claim_value_bundle_evidence(rows),
        }
    )
    return first


def _sum_claim_metric(
    rows: list[dict[str, Any]],
    primary_container: str,
    primary_key: str,
    fallback_container: str,
    fallback_key: str,
) -> Decimal:
    total = Decimal("0")
    for row in rows:
        primary = row.get(primary_container) or {}
        fallback = row.get(fallback_container) or {}
        number = _decimal(primary.get(primary_key))
        if number is None:
            number = _decimal(fallback.get(fallback_key))
        if number is not None:
            total += number
    return total


def _claim_value_bundle_contexts(rows: list[dict[str, Any]]) -> list[str]:
    contexts: list[str] = []
    for row in rows:
        for context in [*_listify(row.get("market_contexts")), _claim_context_text(row)]:
            text = str(context or "").strip()
            if text and text not in contexts:
                contexts.append(text)
    return contexts


def _claim_value_bundle_evidence(rows: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in ("claim", "param", "comment", "semantic"):
        values = [_decimal((row.get("evidence_strength") or {}).get(key)) for row in rows]
        numbers = [value for value in values if value is not None]
        if numbers:
            result[key] = float(min(numbers))
    return result


def _listify(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _base_claim_value_label(label: str) -> str:
    return label[:-2] if label.endswith("组合") else label


def _dedupe_claim_value_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("claim_code") or row.get("claim_name") or "")
        if not key:
            key = f"claim-{len(deduped)}"
        context = _claim_context_text(row)
        if key not in deduped:
            item = dict(row)
            item["market_contexts"] = [context] if context else []
            item["value_role_labels"] = [str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))]
            deduped[key] = item
            continue
        item = deduped[key]
        contexts = item.setdefault("market_contexts", [])
        if context and context not in contexts:
            contexts.append(context)
        labels = item.setdefault("value_role_labels", [])
        label = str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))
        if label and label not in labels:
            labels.append(label)
    return sorted(
        deduped.values(),
        key=lambda row: (
            -int(row.get("claim_value_index") or 0),
            str(row.get("claim_name") or row.get("claim_code") or ""),
        ),
    )


def _positive_decimal(value: Any) -> Decimal:
    number = _decimal(value)
    if number is None:
        return Decimal("0")
    return max(number, Decimal("0"))


def _ratio_score(value: Decimal, denominator: Decimal, weight: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return min(Decimal("1"), value / denominator) * weight


def _claim_value_name(row: dict[str, Any]) -> str:
    if row.get("bundle_claim_count"):
        return str(row.get("claim_name") or "卖点组合")
    return str(row.get("claim_name") or _label_code(row.get("claim_code")) or "未命名卖点")


def _claim_role_cn(value: Any) -> str:
    return CLAIM_VALUE_ROLE_CN.get(str(value or ""), str(value or "未分类"))


def _claim_business_meaning(label: str) -> str:
    if label.endswith("组合"):
        base_label = _base_claim_value_label(label)
        return f"多项卖点在同一可比市场中共同成立，适合作为组合支付理由；{_claim_business_meaning(base_label)}"
    return {
        "强溢价卖点": "可比产品中具备该卖点的一组 SKU 价格更高，能支撑更高定价解释",
        "强销量卖点": "价格不一定更高，但更能解释可比产品中的周均销量或销额优势",
        "基础门槛卖点": "可比产品普遍具备，有了不加价，缺失会削弱入围资格",
        "组合型增值卖点": "单点不一定独立溢价，但与一组高价值卖点组合后支撑高端解释",
        "用户感知不足卖点": "参数或卖点存在，但评论验证弱、负向明显，或弱于高价竞品",
        "高价竞品拦截卖点": "可比高价竞品具备并能成交，本品缺失、表达弱或评论弱",
        "价格上探机会卖点": "高价 SKU 反复具备且有市场价值，本品补强后可能提升上探空间",
        "拖后腿卖点": "厂家主张、参数或评论之间不一致，削弱关键战场、任务或客群",
        "本品优势卖点（待量化）": "本品有明确参数、卖点事实和评论支撑，适合作为差异化表达，但当前可比池对照样本不足，暂不做金额量化",
        "竞品优势/本品短板": "竞品或同池强 SKU 表达更强，本品缺失或表达偏弱，适合作为补强方向",
        "用户感知风险/拖后腿": "参数、卖点或评论之间支撑不足，可能削弱关键场景的成交解释",
        "厂家主张待市场验证": "厂家表达存在，但评论或市场验证不足，不作为溢价或销量结论",
    }.get(label, "当前证据不足，需要结合样本和评论继续复核")


def _claim_rows_by_role(rows: list[dict[str, Any]], *roles: str) -> list[dict[str, Any]]:
    role_set = set(roles)
    return [row for row in rows if str(row.get("claim_value_role") or "") in role_set]


def _claim_rows_by_business_label(rows: list[dict[str, Any]], *labels: str) -> list[dict[str, Any]]:
    label_set = set(labels)
    return [row for row in rows if _base_claim_value_label(str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))) in label_set]


def _claim_index_text(rows: list[dict[str, Any]], *, limit: int = 3) -> str:
    if not rows:
        return ""
    return "；".join(f"{_claim_value_name(row)} {row.get('claim_premium_index')}" for row in rows[:limit])


def _claim_money_text(rows: list[dict[str, Any]], *, limit: int = 3) -> str:
    values = []
    for row in rows[:limit]:
        price = ((row.get("estimated_contribution") or {}).get("price_premium_abs"))
        values.append(f"{_claim_value_name(row)}约{_format_money(price) or '0元'}")
    return "；".join(values)


def _claim_sales_text(rows: list[dict[str, Any]], *, limit: int = 3) -> str:
    values = []
    for row in rows[:limit]:
        sales = ((row.get("estimated_contribution") or {}).get("weekly_sales_lift_abs"))
        values.append(f"{_claim_value_name(row)}约{_format_unit_count(sales) or '0'}台/周")
    return "；".join(values)


def _claim_value_top_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values = []
    for row in rows[:limit]:
        label = str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))
        values.append(f"{_claim_value_name(row)}（{label}）")
    return "；".join(values)


def _claim_value_label_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values = []
    for row in rows[:limit]:
        pool = row.get("pool_effect") or {}
        sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
        parts = [_claim_value_name(row)]
        price = _claim_pool_price_text(row)
        sales = _claim_pool_sales_text(pool.get("pool_claim_weekly_sales_delta_abs"))
        sku_price = _claim_sku_excess_price_text(row, sku_excess)
        if price:
            parts.append(f"可比价格差{price}")
        if sales:
            parts.append(f"可比销量差{sales}")
        if sku_price:
            parts.append(f"可解释价差份额{sku_price}")
        values.append("，".join(parts))
    return "；".join(values)


def _claim_effective_market_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    markets: list[str] = []
    for row in rows:
        market = _claim_market_text(row)
        if market and market not in markets:
            markets.append(market)
    return "；".join(markets[:limit])


def _claim_value_pool_price_delta_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values: list[str] = []
    for row in rows[:limit]:
        values.append(f"{_claim_value_name(row)}：{_claim_pool_price_text(row)}")
    return "；".join(values)


def _claim_value_pool_sales_delta_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values: list[str] = []
    for row in rows[:limit]:
        pool = row.get("pool_effect") or {}
        values.append(f"{_claim_value_name(row)}：{_claim_pool_sales_text(pool.get('pool_claim_weekly_sales_delta_abs'))}")
    return "；".join(values)


def _claim_value_sku_price_explain_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values: list[str] = []
    for row in rows[:limit]:
        sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
        values.append(f"{_claim_value_name(row)}：{_claim_sku_excess_price_text(row, sku_excess) or '不作为正向分摊'}")
    return "；".join(values)


def _claim_value_evidence_summary_text(rows: list[dict[str, Any]], *, limit: int = 5) -> str:
    values: list[str] = []
    for row in rows[:limit]:
        values.append(f"{_claim_value_name(row)}：{_claim_evidence_status_text(row)}")
    return "；".join(values)


def _claim_value_footnote() -> str:
    return (
        "说明：战场可解释价差/销量/销额合计，只汇总同一分类、同一卖点在价值战场中的去重量化结果；"
        "多个战场共用同一组可比池差异和本品解释份额时，合并展示、只计一次；"
        "目标客群、用户任务和整体市场池只作为解释证据，不参与求和。"
        "可比产品价格差异/销量差异是有卖点组与对照组的可观测差异，不是单一卖点因果贡献；"
        "本品可解释价差份额和销量差份额，是把本品相对可比产品基准的价格、销量、销额表现按卖点证据权重做解释性分摊，"
        "不能理解为“一个卖点单独增加 X 元或 X 台/周”。"
    )


def _claim_value_reason_text(row: dict[str, Any]) -> str:
    label = _claim_value_display_category(row)
    if label == "本品优势卖点（待量化）":
        return "本品有参数、卖点事实和评论支撑，可作为优势表达；当前可比池对照样本不足或样本偏弱，暂不写金额、销量或销额量化。"
    if label == "竞品优势/本品短板":
        return "同池竞品或高成交 SKU 在该卖点上表达更强，本品缺失或表达偏弱；该项用于识别补强方向，不作为本品正向价销量分摊。"
    if label == "用户感知风险/拖后腿":
        return "该卖点存在用户感知不足、负向反馈或证据支撑不足，可能削弱相关场景的成交解释。"
    if label == "厂家主张待市场验证":
        return "厂家表达存在，但当前评论和市场验证不足，暂不作为溢价或销量支撑。"
    if label in {"样本不足", "样本不足待复核"}:
        return "当前可比池对照样本不足或样本偏弱，只保留观察，不输出强溢价、强销量或门槛结论。"
    if row.get("bundle_claim_count"):
        return (
            f"{_claim_value_name(row)}共享同一可比市场中的量价差异，适合作为{_base_claim_value_label(label)}的组合解释；"
            "报告按组合展示，避免把同一组市场差异重复拆给每个单独卖点。"
        )
    reason = str(row.get("reason_cn") or "").strip()
    if reason and "价格溢价约" not in reason and "估算价格支撑" not in reason:
        return (
            reason.replace("估算溢价卖点", "强溢价卖点")
            .replace("估算销量卖点", "强销量卖点")
            .replace("机会缺口", "竞品优势/本品短板")
            .replace("用户感知不足卖点", "用户感知风险")
            .replace("厂家主张卖点", "厂家主张待市场验证")
        )
    return f"{label}，依据来自可比产品量价差异、参数/卖点证据、评论验证，以及价值战场、用户任务和目标客群匹配；数值用于排序和解释，不作单点因果归因。"


def _claim_pool_price_text(row: dict[str, Any]) -> str:
    label = str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))
    if _base_claim_value_label(label) in {"拖后腿卖点", "用户感知不足卖点"}:
        return "不作为价格支撑"
    pool = row.get("pool_effect") or {}
    return _format_money(pool.get("pool_claim_price_delta_abs")) or "未知"


def _claim_pool_sales_text(value: Any) -> str:
    formatted = _format_unit_count(value)
    return f"{formatted}台/周" if formatted else "未知"


def _claim_pool_amount_text(value: Any) -> str:
    formatted = _format_money(value)
    return f"{formatted}/周" if formatted else "未知"


def _claim_sku_excess_price_text(row: dict[str, Any], sku_excess: dict[str, Any]) -> str:
    label = str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))
    if _base_claim_value_label(label) in {"拖后腿卖点", "用户感知不足卖点", "机会缺口", "高价竞品拦截卖点", "价格上探机会卖点", "厂家主张卖点"}:
        return ""
    return _format_money(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")) or "0元"


def _claim_sku_excess_sales_text(row: dict[str, Any], sku_excess: dict[str, Any]) -> str:
    label = str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))
    if _base_claim_value_label(label) in {"拖后腿卖点", "用户感知不足卖点", "机会缺口", "高价竞品拦截卖点", "价格上探机会卖点", "厂家主张卖点"}:
        return ""
    formatted = _format_unit_count(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs"))
    return f"{formatted}台/周" if formatted else "0台/周"


def _claim_context_text(row: dict[str, Any]) -> str:
    return str(row.get("context_name") or row.get("context_code") or "当前可比市场")


def _claim_market_text(row: dict[str, Any]) -> str:
    contexts = [str(item) for item in row.get("market_contexts") or [] if item]
    context_text = _join_cn(contexts[:3]) or _claim_context_text(row)
    size_tier = SIZE_TIER_NAMES.get(str(row.get("size_tier") or ""), str(row.get("size_tier") or ""))
    price_band = PRICE_BAND_NAMES.get(str(row.get("price_band_group") or ""), str(row.get("price_band_group") or ""))
    market_pool = " × ".join(part for part in [size_tier, price_band] if part)
    if market_pool and context_text:
        return f"{market_pool}；{context_text}"
    return market_pool or context_text or "当前可比市场"


def _claim_evidence_status_text(row: dict[str, Any]) -> str:
    evidence = row.get("evidence_strength") or {}
    parts = []
    for key, label in (("param", "参数"), ("comment", "评论"), ("semantic", "市场场景")):
        level = _evidence_level_cn(evidence.get(key))
        if level:
            parts.append(f"{label}{level}")
    text = "，".join(parts) or "证据待补充"
    if row.get("bundle_claim_count"):
        return f"{row.get('bundle_claim_count')}个卖点组合；{text}"
    return text


def _evidence_level_cn(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    if number >= Decimal("0.75"):
        return "强"
    if number >= Decimal("0.50"):
        return "中"
    if number > 0:
        return "弱"
    return "缺"


def _claim_value_business_notes(rows: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for row in rows:
        label = str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role")))
        if label and label not in labels:
            labels.append(label)
    lines: list[str] = []
    if labels:
        lines.append("业务类型说明：")
        lines.extend([f"- {label}：{_claim_business_meaning(label)}。" for label in labels])
    explanations = []
    for row in rows[:5]:
        explanations.append(f"- {_claim_value_name(row)}：{_claim_value_reason_text(row)}")
    if explanations:
        lines.extend(["", "卖点解释：", *explanations])
    return lines


def _claim_value_action_lines(rows: list[dict[str, Any]]) -> list[str]:
    by_label: dict[str, list[str]] = {}
    for row in rows:
        label = _base_claim_value_label(str(row.get("business_value_label") or _claim_role_cn(row.get("claim_value_role"))))
        by_label.setdefault(label, []).append(_claim_value_name(row))
    actions: list[str] = []
    premium = by_label.get("强溢价卖点", [])
    sales = by_label.get("强销量卖点", [])
    basic = by_label.get("基础门槛卖点", [])
    weak = [*by_label.get("用户感知不足卖点", []), *by_label.get("拖后腿卖点", [])]
    opportunity = [*by_label.get("高价竞品拦截卖点", []), *by_label.get("价格上探机会卖点", []), *by_label.get("机会缺口", [])]
    if premium:
        actions.append(f"- 价格溢价表达：{_join_cn(premium[:5])}，用于解释本品在可比产品中的高价理由。")
    if sales:
        actions.append(f"- 销量转化支撑：{_join_cn(sales[:5])}，用于强化用户选择理由和转化效率。")
    if basic:
        actions.append(f"- 基础门槛保持完整：{_join_cn(basic[:5])}，具备不一定加价，缺失会削弱入围资格。")
    if weak:
        actions.append(f"- 证据复核与表达降级：{_join_cn(weak[:5])}，避免把用户未认可的点包装成溢价点。")
    if opportunity:
        actions.append(f"- 竞品拦截与补强：{_join_cn(opportunity[:5])}，适合对标高价竞品补强参数、评论证据或详情页表达。")
    return actions


def _claim_fact_comparison_values(product: dict[str, Any]) -> dict[str, str]:
    sections = product.get("sections") or {}
    claim = sections.get("claim_fact") or {}
    comment = sections.get("comment_fact") or {}
    fact_claims = set(str(code) for code in claim.get("fact_claim_codes") or [])
    supported = set(str(code) for code in comment.get("supported_claim_codes") or [])
    contradicted = set(str(code) for code in comment.get("contradicted_claim_codes") or [])
    unsupported = set(str(code) for code in claim.get("unsupported_claim_codes") or [])
    competitor_item = product.get("competitor_item") or {}
    shared_anchors = (competitor_item.get("value_anchor") or {}).get("shared_anchors") or []
    return {
        "事实卖点": _join_cn(_labels_for_codes(sorted(fact_claims))[:10]) or "暂无稳定证据",
        "评论支持卖点": _join_cn(_labels_for_codes(sorted(supported))[:10]) or "暂无稳定证据",
        "评论反向卖点": _join_cn(_labels_for_codes(sorted(contradicted))[:10]) or "暂无稳定证据",
        "参数支撑状态": _claim_param_support_text(claim),
        "需复核表达": _join_cn(_labels_for_codes(sorted(unsupported))[:10]) or "暂无稳定证据",
        "共同价值锚点": _join_cn(shared_anchors[:8]) if shared_anchors else "本品基准",
    }


def _claim_value_comparison_values(product: dict[str, Any]) -> dict[str, str]:
    claim_value_rows = _claim_value_rows_with_index(product.get("claim_value") or {})
    if not claim_value_rows:
        return {"Top5 核心卖点商业价值": "卖点价值量化待生成"}
    top_display_rows = _claim_value_display_rows(claim_value_rows, limit=5)
    premium_rows = _claim_value_display_rows(_claim_rows_by_business_label(claim_value_rows, "强溢价卖点"), limit=5)
    sales_rows = _claim_value_display_rows(_claim_rows_by_business_label(claim_value_rows, "强销量卖点"), limit=5)
    bundle_rows = _claim_value_display_rows(_claim_rows_by_business_label(claim_value_rows, "组合型增值卖点"), limit=5)
    basic_rows = _claim_value_display_rows(_claim_rows_by_business_label(claim_value_rows, "基础门槛卖点"), limit=5)
    weak_rows = _claim_value_display_rows(_claim_rows_by_business_label(claim_value_rows, "用户感知不足卖点", "拖后腿卖点"), limit=5)
    intercept_rows = _claim_value_display_rows(_claim_rows_by_business_label(claim_value_rows, "高价竞品拦截卖点", "价格上探机会卖点", "机会缺口"), limit=5)
    return {
        "Top5 核心卖点商业价值": _claim_value_top_text(top_display_rows, limit=5),
        "价格溢价卖点": _claim_value_label_text(premium_rows),
        "销量驱动卖点": _claim_value_label_text(sales_rows),
        "基础门槛卖点": _claim_value_label_text(basic_rows),
        "组合型增值卖点": _claim_value_label_text(bundle_rows),
        "竞品拦截与补强建议": _claim_value_label_text([*intercept_rows, *weak_rows]),
        "卖点有效市场": _claim_effective_market_text(top_display_rows),
        "可比产品价格差异": _claim_value_pool_price_delta_text(top_display_rows),
        "可比产品销量差异": _claim_value_pool_sales_delta_text(top_display_rows),
        "本品可解释价差份额": _claim_value_sku_price_explain_text(top_display_rows),
        "证据支撑强度": _claim_value_evidence_summary_text(top_display_rows),
    }


def _claim_param_support_text(claim: dict[str, Any]) -> str:
    profile = claim.get("dimension_profile_json") or claim.get("dimension_profile") or {}
    if isinstance(profile, dict) and profile:
        parts = []
        for key, value in list(profile.items())[:6]:
            if isinstance(value, dict):
                count = value.get("fact_claim_count") or value.get("matched_claim_count") or value.get("count")
                label = _label_code(key)
                parts.append(f"{label}{f'({count})' if count is not None else ''}")
            else:
                parts.append(_label_code(key))
        if parts:
            return _join_cn(parts)
    fact_claims = claim.get("fact_claim_codes") or []
    unsupported = claim.get("unsupported_claim_codes") or []
    if fact_claims or unsupported:
        return f"事实卖点{len(fact_claims)}个，需复核{len(unsupported)}个"
    return "暂无稳定证据"


def _parameter_comparison_dimensions(target: dict[str, Any]) -> list[str]:
    if _is_ac_context(target):
        return [
            "匹数/安装能力",
            "能效与省电",
            "制冷制热能力",
            "送风舒适能力",
            "健康洁净能力",
            "智能控制能力",
            "噪音与睡眠舒适",
            "安装与服务能力",
        ]
    return ["尺寸空间", "清晰度规格", "画质技术路线", "亮度控光能力", "动态与游戏能力", "智能系统能力", "外观安装能力", "护眼舒适能力"]


def _param_comparison_values(product: dict[str, Any]) -> dict[str, str]:
    sections = product.get("sections") or {}
    param = sections.get("parameter_fact") or {}
    param_values = _param_value_map(param)
    rows = _business_param_profile_rows(sections)
    values: dict[str, str] = {}
    for dimension, judgement, evidence, business_meaning in rows:
        detail = _join_evidence([judgement, evidence, business_meaning])
        values[dimension] = detail or "暂无稳定证据"
    contradicted = _labels_for_codes((sections.get("comment_fact") or {}).get("contradicted_param_codes") or [])
    if contradicted:
        contradiction_dimension = "制冷制热能力" if _is_ac_param_context(param_values, param) else "护眼舒适能力"
        values[contradiction_dimension] = _join_evidence([values.get(contradiction_dimension, ""), f"评论质疑：{_join_cn(contradicted[:5])}"])
    return values


def _markdown_cell(value: Any) -> str:
    text = str(value or "").replace("\n", "<br>").replace("|", "｜").strip()
    return text or "暂无稳定证据"


def _product_profile_lines(
    section_no: str,
    sku_name: str,
    sku: dict[str, Any],
    sections: dict[str, Any],
    *,
    competitor_item: dict[str, Any] | None,
    claim_value: dict[str, Any] | None,
    claim_contribution: dict[str, Any] | None,
) -> list[str]:
    lines: list[str] = []
    lines.extend([f"### {section_no}.1 市场画像", ""])
    lines.extend(_product_market_profile_lines(sku_name, sku, sections, competitor_item=competitor_item))
    lines.extend(["", f"### {section_no}.2 价值战场画像", ""])
    lines.extend(_semantic_profile_table_lines(sections.get("value_battlefield") or {}, profile_type="battlefield", sections=sections))
    lines.extend(["", f"### {section_no}.3 用户任务画像", ""])
    lines.extend(_semantic_profile_table_lines(sections.get("user_task") or {}, profile_type="task", sections=sections))
    lines.extend(["", f"### {section_no}.4 目标客群画像", ""])
    lines.extend(_semantic_profile_table_lines(sections.get("target_group") or {}, profile_type="group", sections=sections))
    lines.extend(["", f"### {section_no}.5 卖点画像", ""])
    lines.extend(_product_claim_profile_lines(sections))
    lines.extend(["", f"### {section_no}.6 参数画像", ""])
    lines.extend(_product_param_profile_lines(sections))
    lines.extend(["", f"### {section_no}.7 卖点价值量化", ""])
    lines.extend(_product_claim_value_quantification_lines(claim_value=claim_value, claim_contribution=claim_contribution))
    return lines


def _product_market_profile_lines(
    sku_name: str,
    sku: dict[str, Any],
    sections: dict[str, Any],
    *,
    competitor_item: dict[str, Any] | None,
) -> list[str]:
    metrics = _market_metrics(sections)
    position = _market_position(sections)
    price = metrics.get("price_wavg") or metrics.get("price_latest") or sku.get("weighted_price")
    weekly_sales = metrics.get("avg_weekly_sales_volume") or sku.get("avg_weekly_sales_volume")
    size = position.get("screen_size_inch") or sku.get("screen_size_inch")
    price_band = PRICE_BAND_NAMES.get(str(position.get("price_band_in_size_tier") or sku.get("price_band_in_size_tier")), "价格带未知")
    size_tier = SIZE_TIER_NAMES.get(str(position.get("size_tier") or sku.get("size_tier")), "")
    pool = (sections.get("market") or {}).get("market_pool") or {}
    role = _report_role_cn(competitor_item) if competitor_item else f"{price_band}核心 SKU"
    rows = [
        ("尺寸", _size_cell(size, size_tier, sku)),
        ("均价", _format_money(price) or "未知"),
        ("周均销量", f"{_format_unit_count(weekly_sales) or '未知'} 台"),
        ("尺寸价格池", f"{size_tier or '尺寸段未知'} × {price_band}"),
        (
            "所在池空间",
            f"{_format_unit_count(pool.get('total_sales_volume')) or '未知'}台，周均{_format_unit_count(pool.get('total_avg_weekly_sales_volume')) or '未知'}台，SKU数{_format_number(pool.get('sku_count')) or '未知'}",
        ),
        (
            "池内销量表现",
            f"第{_format_number(pool.get('target_rank_by_avg_weekly_sales')) or '未知'}名，占池内销量{_pct_or_unknown(pool.get('target_sales_volume_share'))}",
        ),
        ("市场角色", role),
    ]
    lines = ["| 指标 | 表现 |", "| --- | --- |"]
    lines.extend([f"| {key} | {value} |" for key, value in rows])
    lines.extend(
        [
            "",
            f"市场解读：{sku_name} 当前处在{size_tier or '目标尺寸段'}的{price_band}，周均销量约{_format_unit_count(weekly_sales) or '未知'}台；所在尺寸价格池总销量约{_format_unit_count(pool.get('total_sales_volume')) or '未知'}台，本品占池内销量{_pct_or_unknown(pool.get('target_sales_volume_share'))}。",
        ]
    )
    return lines


def _semantic_profile_table_lines(profile: dict[str, Any], *, profile_type: str, sections: dict[str, Any]) -> list[str]:
    columns = {
        "battlefield": ("战场", "业务含义"),
        "task": ("用户任务", "支撑证据"),
        "group": ("目标客群", "购买动机"),
    }[profile_type]
    positions = _semantic_position_by_code(sections, profile_type=profile_type)
    rows = _semantic_rows(profile, profile_type=profile_type)
    lines = [f"| {columns[0]} | 关系 | 维度总空间 | 本品销量表现 | {columns[1]} |", "| --- | --- | --- | --- | --- |"]
    if not rows:
        lines.append(f"| 暂无稳定画像 | 待确认 | 暂无 | 暂无 | 当前事实不足，无法形成稳定{columns[0]}判断 |")
        return lines
    for code, label, relation, reason in rows:
        position = positions.get(code, {})
        lines.append(
            f"| {label} | {relation} | {_semantic_market_space_text(position)} | {_semantic_sku_performance_text(position, relation=relation)} | {reason} |"
        )
    return lines


def _product_claim_profile_lines(sections: dict[str, Any]) -> list[str]:
    claim = sections.get("claim_fact") or {}
    comment = sections.get("comment_fact") or {}
    fact_claims = set(str(code) for code in claim.get("fact_claim_codes") or [])
    supported = set(str(code) for code in comment.get("supported_claim_codes") or [])
    contradicted = set(str(code) for code in comment.get("contradicted_claim_codes") or [])
    unsupported = set(str(code) for code in claim.get("unsupported_claim_codes") or [])
    premium = sorted((fact_claims & supported) - contradicted)
    basic = sorted(fact_claims - supported - contradicted)
    rows: list[tuple[str, list[str], str]] = []
    if premium:
        rows.append(("溢价卖点", premium, "同时具备事实卖点和评论支撑，可支撑主/辅价值战场的支付理由"))
    if basic:
        rows.append(("基础支撑卖点", basic, "具备事实卖点，但评论侧支撑仍需继续观察"))
    if contradicted:
        rows.append(("拖后腿卖点", sorted(contradicted), "评论侧存在负向或质疑信号，会削弱对应战场的溢价效率"))
    if unsupported:
        rows.append(("需复核表达", sorted(unsupported), "当前参数或评论支撑不足，不宜直接作为核心溢价依据"))
    lines = ["| 卖点类型 | 卖点 | 判断 |", "| --- | --- | --- |"]
    if not rows:
        lines.append("| 暂无稳定卖点 | 暂无 | 当前卖点事实不足 |")
        return lines
    for claim_type, codes, reason in rows:
        lines.append(f"| {claim_type} | {_join_cn(_labels_for_codes(codes))} | {reason} |")
    return lines


def _product_claim_value_quantification_lines(
    *,
    claim_value: dict[str, Any] | None,
    claim_contribution: dict[str, Any] | None,
) -> list[str]:
    claim_value_payload = _extract_claim_value_payload(claim_value)
    claim_rows = _claim_value_rows_with_index(claim_value_payload, dedupe=False)
    if not claim_rows:
        return ["卖点价值量化待生成。"]
    groups = _claim_value_category_groups(claim_rows)
    lines: list[str] = []
    by_category = _claim_value_groups_by_category(groups)
    rendered_groups: list[dict[str, Any]] = []
    for category in CLAIM_VALUE_CATEGORY_ORDER:
        category_groups = by_category.get(category, [])
        if not category_groups:
            continue
        selected_groups = category_groups[:5]
        rendered_groups.extend(selected_groups)
        lines.extend(_claim_value_category_section_lines(category, selected_groups))
    attribution_payload = _extract_claim_contribution_payload(claim_contribution)
    attribution_lines = _claim_contribution_profile_lines(attribution_payload)
    lines.extend(["", _claim_value_footnote()])
    representative_rows = _claim_value_representative_rows_for_groups(rendered_groups)
    lines.extend(["", *_claim_value_business_notes(representative_rows)])
    action_lines = _claim_value_action_lines(representative_rows[:10])
    if action_lines:
        lines.extend(["", "竞品拦截与补强建议：", "", *action_lines])
    if attribution_lines:
        lines.extend(["", "本品相对可比产品表现差异：", "", *attribution_lines])
    return lines


def _claim_contribution_profile_lines(payload: dict[str, Any]) -> list[str]:
    rows = [row for row in payload.get("attributions") or [] if isinstance(row, dict)]
    if not rows:
        return []
    lines = ["| 市场场景 | 参与解释的正向卖点 | 高于可比产品基准的均价差 | 高于可比产品基准的周均销量差 | 解释置信度 |", "| --- | --- | --- | --- | --- |"]
    for row in rows[:5]:
        positive_claims = row.get("positive_claims") or []
        names = _join_cn([str(item.get("claim_name") or _label_code(item.get("claim_code"))) for item in positive_claims[:4] if isinstance(item, dict)]) or "未形成高置信正向卖点"
        gap = row.get("sku_gap_vs_baseline") or {}
        lines.append(
            f"| {row.get('context_name') or row.get('context_code') or '当前可比市场'} | {names} | {_format_money(gap.get('price_premium_abs')) or '0元'} | {_format_unit_count(gap.get('weekly_sales_lift_abs')) or '0'}台/周 | {_pct_or_unknown(row.get('confidence'))} |"
        )
    return lines


def _product_param_profile_lines(sections: dict[str, Any]) -> list[str]:
    param = sections.get("parameter_fact") or {}
    rows = _business_param_profile_rows(sections)
    lines = ["| 参数维度 | 业务判断 | 关键证据 | 对成交价值的含义 |", "| --- | --- | --- | --- |"]
    if not rows:
        lines.append("| 暂无稳定参数 | 暂无 | 当前参数事实不足 | 需要补齐核心规格后再判断产品力 |")
        return lines
    for dimension, judgement, evidence, business_meaning in rows:
        lines.append(f"| {dimension} | {judgement} | {evidence} | {business_meaning} |")
    contradicted = _labels_for_codes((sections.get("comment_fact") or {}).get("contradicted_param_codes") or [])
    if contradicted:
        lines.append(f"| 拖后腿参数 | {_join_cn(contradicted)} | 评论侧存在负向或质疑信号 | 需要结合原始评论复核，避免把被质疑能力包装成溢价点 |")
    return lines


def _primary_secondary_text(profile: dict[str, Any], profile_type: str) -> str:
    rows = _semantic_rows(profile, profile_type=profile_type)
    primary_markers = ("主战场", "主任务", "主客群", "辅战场", "辅任务", "辅客群")
    labels = [label for _code, label, relation, _reason in rows if any(marker in relation for marker in primary_markers)]
    return _join_cn(labels[:5])


def _semantic_rows(profile: dict[str, Any], *, profile_type: str) -> list[tuple[str, str, str, str]]:
    if profile_type == "battlefield":
        specs = [
            ("primary_battlefield_code", "主战场", "产品当前最核心的价值竞争位置"),
            ("secondary_battlefield_codes", "辅战场", "对主战场形成补充的价值竞争位置"),
            ("opportunity_battlefield_codes", "机会战场", "已有一定事实基础但尚未成为主竞争位置"),
            ("drag_factor_battlefield_codes", "拖后腿战场", "用户有需求但产品或评论支撑不足"),
        ]
    elif profile_type == "task":
        specs = [
            ("primary_user_task_code", "主任务", "用户最核心的使用或购买任务"),
            ("secondary_user_task_codes", "辅任务", "对主任务形成补充的使用任务"),
            ("comment_observed_task_codes", "评论观察任务", "评论侧出现的真实用户任务"),
            ("brand_claimed_task_codes", "厂家主张任务", "卖点侧表达但评论验证相对不足的任务"),
        ]
    else:
        specs = [
            ("primary_target_group_code", "主客群", "当前最核心的目标用户"),
            ("secondary_target_group_codes", "辅客群", "与主客群相邻或补充的人群"),
            ("comment_observed_group_codes", "评论观察客群", "评论侧出现的真实人群"),
            ("brand_claimed_group_codes", "厂家主张客群", "卖点侧表达但评论验证相对不足的人群"),
        ]
    row_by_code: dict[str, dict[str, Any]] = {}
    for key, relation, reason in specs:
        value = profile.get(key)
        values = value if isinstance(value, list) else [value]
        for code in values:
            label = _label_code(code)
            if label:
                code_text = str(code)
                row = row_by_code.setdefault(code_text, {"label": label, "relations": [], "reasons": []})
                if relation not in row["relations"]:
                    row["relations"].append(relation)
                if reason not in row["reasons"]:
                    row["reasons"].append(reason)
    return [
        (code, str(payload["label"]), _join_cn(payload["relations"]), "；".join(payload["reasons"]))
        for code, payload in row_by_code.items()
    ]


def _semantic_position_by_code(sections: dict[str, Any], *, profile_type: str) -> dict[str, dict[str, Any]]:
    dimension_type = {"battlefield": "battlefield", "task": "user_task", "group": "target_group"}[profile_type]
    result: dict[str, dict[str, Any]] = {}
    for item in sections.get("semantic_dimension_positions") or []:
        if not isinstance(item, dict) or item.get("dimension_type") != dimension_type:
            continue
        code = str(item.get("dimension_code") or "")
        if code:
            result[code] = item
    return result


def _semantic_market_space_text(position: dict[str, Any]) -> str:
    market_space = position.get("market_space") or {}
    if not market_space:
        return "未纳入当前销量空间测算"
    parts = [
        f"空间{_format_unit_count(market_space.get('estimated_sales_volume')) or '未知'}台",
        f"周均{_format_unit_count(market_space.get('estimated_avg_weekly_sales_volume')) or '未知'}台",
        f"覆盖{_format_number(market_space.get('allocated_sku_count')) or '未知'}个SKU",
    ]
    share = _pct_or_unknown(market_space.get("sales_volume_share"))
    if share != "未知":
        parts.append(f"市场占比{share}")
    return "；".join(parts)


def _semantic_sku_performance_text(position: dict[str, Any], *, relation: str = "") -> str:
    allocation = position.get("sku_allocation") or {}
    contribution = position.get("sku_contribution") or {}
    if not allocation:
        if any(marker in relation for marker in ("机会", "拖后腿", "厂家主张", "评论观察", "用户观察")):
            return "未分配销量，仅作机会或观察证据"
        return "当前图谱未分配本品销量"
    share = contribution.get("sku_share_in_dimension_volume")
    if share is None:
        market_space = position.get("market_space") or {}
        allocated = _decimal(allocation.get("allocated_sales_volume"))
        total = _decimal(market_space.get("estimated_sales_volume"))
        share = allocated / total if allocated is not None and total else None
    parts = [
        f"分配{_format_unit_count(allocation.get('allocated_sales_volume')) or '未知'}台",
        f"周均{_format_unit_count(allocation.get('allocated_avg_weekly_sales_volume')) or '未知'}台",
        f"权重{_pct_or_unknown(allocation.get('allocation_weight'))}",
    ]
    rank = contribution.get("sku_rank_in_dimension")
    if rank:
        parts.append(f"维度内第{_format_number(rank)}名")
    share_text = _pct_or_unknown(share)
    if share_text != "未知":
        parts.append(f"占维度销量{share_text}")
    return "；".join(parts)


def _first_candidate_by_role(
    all_competitors: list[dict[str, Any]],
    *,
    excluded: list[dict[str, Any]],
    roles: set[str],
) -> dict[str, Any] | None:
    excluded_codes = {str((item.get("candidate") or {}).get("sku_code")) for item in excluded}
    for item in all_competitors:
        code = str((item.get("candidate") or {}).get("sku_code"))
        if code not in excluded_codes and item.get("role") in roles:
            return item
    return None


def _report_role_cn(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    role = str(item.get("role") or "")
    return {
        "primary_direct": "首选直接竞品",
        "strong_direct": "强配置对标竞品",
        "downtrade_diversion": "价格下探分流竞品",
        "price_adjacent": "价格贴身竞品",
        "uptrade_alternative": "上探品牌替代竞品",
        "scenario_alternative": "场景替代竞品",
        "excluded": "排除候选",
    }.get(role, str(item.get("role_cn") or role))


def _report_candidates(top_competitors: list[dict[str, Any]], all_competitors: list[dict[str, Any]], limit: int = 7) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in (top_competitors, all_competitors):
        for item in group:
            code = str((item.get("candidate") or {}).get("sku_code") or _display_name(item.get("candidate") or {}))
            if code in seen:
                continue
            selected.append(item)
            seen.add(code)
            if len(selected) >= limit:
                return selected
    return selected


def _candidate_score_breakdown(item: dict[str, Any]) -> dict[str, int]:
    purchase_pool = _bounded_points(item.get("purchase_pool", {}).get("score"), 20)
    battlefield = _bounded_points((item.get("weighted_overlap") or {}).get("battlefield"), 15)
    user_task = _bounded_points((item.get("weighted_overlap") or {}).get("user_task"), 20)
    target_group = _bounded_points((item.get("weighted_overlap") or {}).get("target_group"), 20)
    value_anchor = _bounded_points((item.get("value_anchor") or {}).get("score"), 15)
    replacement_pressure = _bounded_points((item.get("replacement_pressure") or {}).get("score"), 5)
    market_validation = _market_validation_points((item.get("market_validation") or {}).get("level"))
    total = purchase_pool + battlefield + user_task + target_group + value_anchor + replacement_pressure + market_validation
    role = str(item.get("role") or "")
    if role == "strong_direct":
        total += 4
    elif role == "primary_direct":
        total += 5
    elif role == "downtrade_diversion":
        total -= 3
    elif role == "price_adjacent":
        total -= 8
    elif role == "uptrade_alternative":
        total -= 5
    total = max(0, min(100, total))
    return {
        "purchase_pool": purchase_pool,
        "battlefield": battlefield,
        "user_task": user_task,
        "target_group": target_group,
        "value_anchor": value_anchor,
        "replacement_pressure": replacement_pressure,
        "market_validation": market_validation,
        "total": total,
    }


def _bounded_points(value: Any, weight: int) -> int:
    number = _decimal(value) or Decimal("0")
    number = max(Decimal("0"), min(Decimal("1"), number))
    return int((number * Decimal(weight)).quantize(Decimal("1")))


def _market_validation_points(level: Any) -> int:
    return {"strong": 5, "medium": 4, "weak": 1}.get(str(level or ""), 1)


def _market_validation_score(level: Any) -> Decimal:
    return {"strong": Decimal("1.00"), "medium": Decimal("0.80"), "weak": Decimal("0.20")}.get(str(level or ""), Decimal("0.20"))


def _candidate_sort_reason(item: dict[str, Any]) -> str:
    role = str(item.get("role") or "")
    if role == "primary_direct":
        return "同预算池内替代关系最完整，对目标 SKU 成交理由形成直接拦截"
    if role == "strong_direct":
        return "购买池和核心价值重合度高，形成强正面对标"
    if role == "downtrade_diversion":
        return "价格明显下探，同时保留部分核心体验，拦截预算敏感用户"
    if role == "price_adjacent":
        return "价格最贴近，但价值战场、任务或客群有效重合不足"
    if role == "uptrade_alternative":
        return "价格上探明显，更多影响追加预算用户"
    return item.get("exclusion_reason_cn") or "综合替代压力低于前三候选"


def _param_group_business_role(group: str) -> str:
    normalized = group.lower()
    if "picture" in normalized or "display" in normalized:
        return "支撑画质、亮度、控光、色彩和高端画质感"
    if "gaming" in normalized or "motion" in normalized:
        return "支撑游戏、体育赛事和高速画面流畅度"
    if "system" in normalized or "smart" in normalized:
        return "支撑系统流畅、智能交互和日常易用"
    if "eye" in normalized or "care" in normalized:
        return "支撑护眼、长时间观看和家庭舒适体验"
    return "支撑对应产品能力和卖点表达"


def _business_param_profile_rows(sections: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    param = sections.get("parameter_fact") or {}
    values = _param_value_map(param)
    if _is_ac_param_context(values, param):
        return _ac_business_param_profile_rows(values, param)
    rows: list[tuple[str, str, str, str]] = []

    size_value = _first_param(values, "screen_size_inch", "size_inch", "screen_size", "尺寸")
    size_tier = (param.get("dimension_tier_profile") or {}).get("size") if isinstance(param.get("dimension_tier_profile"), dict) else None
    if size_value is not None or size_tier:
        size_text = f"{_format_number(size_value)}寸" if size_value is not None else "尺寸已识别"
        tier_text = _label_code(size_tier) if size_tier else ""
        rows.append(
            (
                "尺寸空间",
                f"{size_text}{'，' + tier_text if tier_text else ''}",
                _join_evidence([item for item in (size_text, tier_text) if item]),
                "决定产品进入哪个尺寸购买池，是客厅观影、影院沉浸和同尺寸竞品比较的基础。",
            )
        )

    resolution_text = _resolution_business_text(values)
    if resolution_text:
        rows.append(
            (
                "清晰度规格",
                f"{resolution_text} 显示规格",
                resolution_text,
                "属于当前大屏电视的基础清晰度门槛，可支撑高清片源、客厅观影和高端画质叙事。",
            )
        )

    picture_row = _picture_technology_row(values)
    if picture_row:
        rows.append(picture_row)

    brightness = _first_param(values, "declared_brightness_nit_or_band", "brightness_nit", "peak_brightness_nit", "亮度")
    dimming = _first_param(values, "local_dimming_zone_count", "dimming_zone_count", "控光分区")
    hdr = _first_param(values, "hdr_capability_flag", "hdr_flag", "hdr")
    if brightness is not None or dimming is not None or hdr is not None:
        evidence = []
        if brightness is not None:
            evidence.append(f"亮度：{_format_business_value(brightness)}")
        if dimming is not None:
            evidence.append(f"控光分区：{_format_business_value(dimming)}")
        if hdr is not None:
            evidence.append(f"HDR：{'支持' if _truthy_param(hdr) else '未见明确支持'}")
        rows.append(
            (
                "亮度控光能力",
                "高亮控光证据已出现" if brightness is not None or dimming is not None else "HDR 能力已出现",
                _join_evidence(evidence),
                "直接影响暗场层次、明暗对比和高端画质感，是高端画质升级战场的重要溢价证据。",
            )
        )

    refresh = _first_param(values, "declared_refresh_rate_hz", "refresh_rate_hz", "screen_refresh_rate_hz", "刷新率")
    hdmi21 = _first_param(values, "hdmi21_port_count", "hdmi_2_1_port_count", "hdmi2_1_port_count")
    if refresh is not None or hdmi21 is not None:
        evidence = []
        if refresh is not None:
            evidence.append(f"刷新率：{_format_business_value(refresh)}Hz")
        if hdmi21 is not None:
            evidence.append(f"HDMI 2.1：{_format_business_value(hdmi21)}个")
        rows.append(
            (
                "动态与游戏能力",
                "高刷娱乐能力已成立" if refresh is not None else "游戏连接能力有证据",
                _join_evidence(evidence),
                "支撑游戏、体育赛事和高速画面流畅，是游戏体育流畅战场的核心产品证据。",
            )
        )

    ai_capability = _first_param(values, "ai_capability_flag", "ai_model_capability_flag", "ai_flag", "ai能力")
    chip = _first_param(values, "processor_chip_model", "chip_model", "芯片")
    wifi = _first_param(values, "wifi_capability_flag", "wifi_flag")
    if ai_capability is not None or chip is not None or wifi is not None:
        evidence = []
        if ai_capability is not None:
            evidence.append(f"AI：{'有' if _truthy_param(ai_capability) else '未见明确能力'}")
        if chip is not None:
            evidence.append(f"芯片：{_format_business_value(chip)}")
        if wifi is not None:
            evidence.append(f"无线连接：{'有' if _truthy_param(wifi) else '未见明确能力'}")
        rows.append(
            (
                "智能系统能力",
                "智能交互和系统能力有参数支撑",
                _join_evidence(evidence),
                "影响投屏互联、语音控制、系统流畅和日常易用，是智能互联与家庭使用体验的基础。",
            )
        )

    slim = _first_param(values, "slim_design_label", "body_thickness_mm", "ultra_thin_flag", "超薄")
    flush = _first_param(values, "wall_mount_flush_flag", "flush_wall_mount_flag", "贴墙安装")
    if slim is not None or flush is not None:
        evidence = []
        if slim is not None:
            evidence.append(f"外观：{_format_business_value(slim)}")
        if flush is not None:
            evidence.append(f"贴墙安装：{'支持' if _truthy_param(flush) else '未见支持'}")
        rows.append(
            (
                "外观安装能力",
                "家装融合能力有参数支撑",
                _join_evidence(evidence),
                "支撑新家装修、客厅空间融合和高端外观感，可把技术参数转译成家庭场景价值。",
            )
        )

    eye_care = _first_param(values, "low_blue_light_flag", "flicker_free_flag", "eye_care_flag", "护眼")
    if eye_care is not None:
        rows.append(
            (
                "护眼舒适能力",
                "护眼长看能力有参数支撑" if _truthy_param(eye_care) else "未见明确护眼参数",
                f"护眼：{'有' if _truthy_param(eye_care) else '未见明确支持'}",
                "影响儿童家庭、长时间观看和舒适体验；若评论同步正向，可成为家庭客群的溢价支撑。",
            )
        )

    return rows


def _is_ac_param_context(values: dict[str, Any], param: dict[str, Any]) -> bool:
    size_tier = (param.get("dimension_tier_profile") or {}).get("size") if isinstance(param.get("dimension_tier_profile"), dict) else None
    if str(size_tier or "").startswith(("wall_hp_", "floor_hp_")):
        return True
    ac_param_codes = {
        "horsepower_hp",
        "installation_hp_segment",
        "installation_type",
        "cooling_capacity_w",
        "heating_capacity_w",
        "heat_cool_mode",
        "energy_grade_normalized",
        "energy_efficiency_ratio",
        "airflow_volume_m3h",
        "self_cleaning_flag",
        "purification_flag",
        "wifi_control_flag",
        "voice_control_flag",
    }
    normalized_codes = {_param_lookup_key(code) for code in values}
    return any(_param_lookup_key(code) in normalized_codes for code in ac_param_codes)


def _ac_business_param_profile_rows(values: dict[str, Any], param: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    size_tier = (param.get("dimension_tier_profile") or {}).get("size") if isinstance(param.get("dimension_tier_profile"), dict) else None
    tier_text = _label_code(size_tier) if size_tier else ""
    horsepower = _first_param(values, "horsepower_hp", "installation_hp_segment", "匹数")
    installation = _first_param(values, "installation_type", "安装形态")
    if horsepower is not None or installation is not None or tier_text:
        evidence = []
        if horsepower is not None:
            evidence.append(f"匹数：{_format_hp_value(horsepower)}")
        if installation is not None:
            evidence.append(f"安装形态：{_format_business_value(installation)}")
        if tier_text:
            evidence.append(f"匹数段：{tier_text}")
        rows.append(
            (
                "匹数/安装能力",
                _join_cn([item for item in (_format_hp_value(horsepower) if horsepower is not None else "", _format_business_value(installation) if installation is not None else "", tier_text) if item]) or "匹数与安装形态已识别",
                _join_evidence(evidence),
                "决定产品进入挂机/柜机和匹数购买池，是同预算、同空间竞品比较的基础。",
            )
        )

    energy_grade = _first_param(values, "energy_grade_normalized", "energy_grade", "能效等级")
    efficiency = _first_param(values, "energy_efficiency_ratio", "apf", "APF")
    inverter = _first_param(values, "inverter_flag", "变频")
    if energy_grade is not None or efficiency is not None or inverter is not None:
        evidence = []
        if energy_grade is not None:
            evidence.append(f"能效等级：{_format_business_value(energy_grade)}")
        if efficiency is not None:
            evidence.append(f"APF/能效比：{_format_business_value(efficiency)}")
        if inverter is not None:
            evidence.append(f"变频：{'支持' if _truthy_param(inverter) else '未见明确支持'}")
        rows.append(
            (
                "能效与省电",
                "省电能力有参数支撑",
                _join_evidence(evidence),
                "支撑长时使用省电和家庭用电成本解释，是空调高频购买理由。",
            )
        )

    cooling = _first_param(values, "cooling_capacity_w", "制冷量")
    heating = _first_param(values, "heating_capacity_w", "制热量")
    mode = _first_param(values, "heat_cool_mode", "冷暖类型")
    if cooling is not None or heating is not None or mode is not None:
        evidence = []
        if cooling is not None:
            evidence.append(f"制冷量：{_format_business_value(cooling)}W")
        if heating is not None:
            evidence.append(f"制热量：{_format_business_value(heating)}W")
        if mode is not None:
            evidence.append(f"冷暖类型：{_format_business_value(mode)}")
        rows.append(
            (
                "制冷制热能力",
                "冷热能力有参数支撑",
                _join_evidence(evidence),
                "影响大空间覆盖、快速制冷制热和冬夏两用的成交判断。",
            )
        )

    airflow = _first_param(values, "airflow_volume_m3h", "循环风量", "风量")
    comfort = _first_param(values, "comfort_airflow_flag", "soft_wind_flag", "舒适风")
    if airflow is not None or comfort is not None:
        evidence = []
        if airflow is not None:
            evidence.append(f"循环风量：{_format_business_value(airflow)}m3/h")
        if comfort is not None:
            evidence.append(f"舒适风：{'支持' if _truthy_param(comfort) else '未见明确支持'}")
        rows.append(
            (
                "送风舒适能力",
                "送风覆盖和舒适性有参数支撑",
                _join_evidence(evidence),
                "支撑客厅大空间、柔风防直吹和体感舒适，是柜机竞争的关键体验证据。",
            )
        )

    fresh_air = _first_param(values, "fresh_air_flag", "新风")
    purification = _first_param(values, "purification_flag", "净化除菌")
    self_cleaning = _first_param(values, "self_cleaning_flag", "自清洁")
    if fresh_air is not None or purification is not None or self_cleaning is not None:
        evidence = []
        if fresh_air is not None:
            evidence.append(f"新风：{'支持' if _truthy_param(fresh_air) else '未见明确支持'}")
        if purification is not None:
            evidence.append(f"净化除菌：{'支持' if _truthy_param(purification) else '未见明确支持'}")
        if self_cleaning is not None:
            evidence.append(f"自清洁：{'支持' if _truthy_param(self_cleaning) else '未见明确支持'}")
        rows.append(
            (
                "健康洁净能力",
                "健康洁净能力有参数支撑",
                _join_evidence(evidence),
                "支撑健康空气、自清洁和母婴老人敏感家庭的安心理由。",
            )
        )

    wifi = _first_param(values, "wifi_control_flag", "wifi_capability_flag", "WiFi/APP 控制")
    voice = _first_param(values, "voice_control_flag", "语音控制")
    sensing = _first_param(values, "smart_sensing_flag", "智能感应")
    if wifi is not None or voice is not None or sensing is not None:
        evidence = []
        if wifi is not None:
            evidence.append(f"WiFi/APP：{'支持' if _truthy_param(wifi) else '未见明确支持'}")
        if voice is not None:
            evidence.append(f"语音控制：{'支持' if _truthy_param(voice) else '未见明确支持'}")
        if sensing is not None:
            evidence.append(f"智能感应：{'支持' if _truthy_param(sensing) else '未见明确支持'}")
        rows.append(
            (
                "智能控制能力",
                "远程和智能控制有参数支撑",
                _join_evidence(evidence),
                "影响远程开关、语音操控和家庭智能化体验，是中高价空调的差异化证据。",
            )
        )

    noise = _first_param(values, "indoor_noise_db", "noise_db", "静音")
    if noise is not None:
        rows.append(
            (
                "噪音与睡眠舒适",
                "静音体验有参数支撑",
                f"噪音：{_format_business_value(noise)}dB",
                "支撑睡眠静音和卧室舒适场景，需结合评论验证实际体感。",
            )
        )

    return rows


def _format_hp_value(value: Any) -> str:
    number = _decimal(value)
    if number is not None:
        return f"{_format_number(number)}匹"
    return _format_business_value(value)


def _param_value_map(param: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    core_params = param.get("core_params") or {}
    if isinstance(core_params, dict):
        for group_value in core_params.values():
            if not isinstance(group_value, dict):
                continue
            for code, payload in group_value.items():
                value = _extract_param_value(payload)
                if value is not None:
                    result[str(code)] = value
    dimension_tier = param.get("dimension_tier_profile") or {}
    if isinstance(dimension_tier, dict):
        for code, value in dimension_tier.items():
            if value is not None:
                result.setdefault(str(code), value)
    return result


def _extract_param_value(payload: Any) -> Any:
    if isinstance(payload, dict):
        if "normalized_value" in payload and payload.get("normalized_value") is not None:
            return payload.get("normalized_value")
        if "raw_value" in payload and payload.get("raw_value") is not None:
            return payload.get("raw_value")
        if any(key in payload for key in ("width", "height", "resolution_label")):
            return payload
        return None
    return payload


def _first_param(values: dict[str, Any], *codes: str) -> Any:
    normalized_map = {_param_lookup_key(key): value for key, value in values.items()}
    for code in codes:
        if code in values:
            return values[code]
        key = _param_lookup_key(code)
        if key in normalized_map:
            return normalized_map[key]
    return None


def _param_lookup_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _resolution_business_text(values: dict[str, Any]) -> str:
    label = _first_param(values, "resolution_label", "分辨率")
    pixels = _first_param(values, "resolution_pixels")
    width = height = None
    if isinstance(pixels, dict):
        width = pixels.get("width")
        height = pixels.get("height")
        label = label or pixels.get("resolution_label")
    label_text = _format_business_value(label) if label is not None else ""
    if width and height:
        pixel_text = f"{_format_resolution_axis(width)}x{_format_resolution_axis(height)}"
        return f"{label_text}（{pixel_text}）" if label_text else pixel_text
    return label_text


def _format_resolution_axis(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return str(value or "").strip()
    return str(int(number)) if number == number.to_integral_value() else str(number)


def _picture_technology_row(values: dict[str, Any]) -> tuple[str, str, str, str] | None:
    mini_led = _first_param(values, "mini_led_flag", "miniled_flag")
    mini_led_type = _first_param(values, "mini_led_type", "miniled_type")
    backlight = _first_param(values, "backlight_source", "背光源")
    quantum_dot = _first_param(values, "quantum_dot_flag", "qled_flag", "量子点")
    display_tech = _first_param(values, "display_tech_class", "display_technology", "display_type")
    picture_score = _first_param(values, "picture_quality_score", "premium_picture_score", "高端画质")
    if all(value is None for value in (mini_led, mini_led_type, backlight, quantum_dot, display_tech, picture_score)):
        return None

    evidence: list[str] = []
    if mini_led is not None:
        evidence.append("MiniLED 方案已成立" if _truthy_param(mini_led) else "未见 MiniLED 方案")
    if mini_led_type is not None:
        evidence.append(f"画质定位：{_format_business_value(mini_led_type)}")
    if backlight is not None:
        evidence.append(f"背光源：{_format_business_value(backlight)}")
    if quantum_dot is not None:
        evidence.append("量子点：有" if _truthy_param(quantum_dot) else "量子点：未见")
    if display_tech is not None:
        evidence.append(f"显示技术：{_format_business_value(display_tech)}")
    if picture_score is not None:
        evidence.append(f"高端画质评分：{_format_business_value(picture_score)}")

    if _truthy_param(mini_led):
        judgement = "MiniLED 高端画质路线"
        meaning = "这是高端画质升级和影院沉浸的核心硬件锚点；背光源只作为技术底座，不应单独包装成溢价卖点"
        if quantum_dot is not None and not _truthy_param(quantum_dot):
            meaning += "；未见量子点加成，色彩增强叙事需要依赖其他参数或卖点证据"
    elif display_tech is not None or backlight is not None:
        judgement = f"{_format_business_value(display_tech or backlight)} 显示路线"
        meaning = "可说明基础显示技术路线，但是否构成溢价还要看亮度、控光、色彩和评论验证。"
    else:
        judgement = "画质能力有参数证据"
        meaning = "可作为画质卖点的辅助证据，需和卖点、评论共同判断是否形成溢价。"
    return ("画质技术路线", judgement, _join_evidence(evidence), meaning)


def _truthy_param(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)) != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "有", "是", "支持", "supported", "yes_supported"}


def _format_business_value(value: Any) -> str:
    if isinstance(value, dict):
        if "value" in value:
            unit = _business_unit(value.get("unit"))
            formatted = _format_unit_number(value.get("value")) if unit else _format_business_value(value.get("value"))
            return f"{formatted}{unit}" if unit else formatted
        resolution = _resolution_business_text({"resolution_pixels": value})
        return resolution or str(value)
    if isinstance(value, bool):
        return "有" if value else "无"
    if isinstance(value, (int, float, Decimal)):
        return _format_number(value)
    text = str(value or "").strip()
    mapping = {
        "miniled": "MiniLED",
        "mini_led": "MiniLED",
        "led": "LED",
        "lcd": "LCD",
        "oled": "OLED",
        "qled": "QLED",
        "4k": "4K",
        "8k": "8K",
        "high_end_picture": "高端画质",
    }
    return mapping.get(text.lower(), _label_code(text) or text)


def _business_unit(value: Any) -> str:
    text = str(value or "").strip().lower()
    mapping = {
        "nit": "尼特",
        "nits": "尼特",
        "hz": "Hz",
        "w": "W",
        "mm": "mm",
        "%": "%",
    }
    return mapping.get(text, str(value or "").strip())


def _format_unit_number(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return str(value or "").strip()
    return str(int(number)) if number == number.to_integral_value() else str(number.normalize())


def _join_evidence(items: list[str]) -> str:
    return "；".join(item for item in items if item)


def _fact_sections(fact_brief: dict[str, Any]) -> dict[str, Any]:
    sections = fact_brief.get("sections") if isinstance(fact_brief, dict) else None
    return sections if isinstance(sections, dict) else {}


def _market_metrics(sections: dict[str, Any]) -> dict[str, Any]:
    market = sections.get("market") or {}
    metrics = market.get("market_metrics") or {}
    return metrics if isinstance(metrics, dict) else {}


def _market_position(sections: dict[str, Any]) -> dict[str, Any]:
    market = sections.get("market") or {}
    position = market.get("market_position") or {}
    return position if isinstance(position, dict) else {}


def _percentile_phrase(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    if number <= 1:
        number *= Decimal("100")
    return f"{number.quantize(Decimal('1'))}%"


def _flatten_core_params(core_params: dict[str, Any]) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    for group_value in core_params.values():
        if not isinstance(group_value, dict):
            continue
        for code, payload in group_value.items():
            if isinstance(payload, dict):
                value = payload.get("normalized_value")
                if value is None:
                    value = payload.get("raw_value")
            else:
                value = payload
            if value is not None:
                result.append((str(code), value))
    return result


def _dimension_tier_text(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    values: list[str] = []
    for key, value in payload.items():
        label = _label_code(key)
        value_label = _label_code(value)
        if label and value_label:
            values.append(f"{label}={value_label}")
    return _join_cn(values[:8])


def _format_param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "有" if value else "无"
    if isinstance(value, (int, float, Decimal)):
        return _format_number(value)
    text = str(value or "").strip()
    return _label_code(text) or text


def _labels_for_codes(codes: list[Any]) -> list[str]:
    return _unique_strings([_label_code(code) for code in codes])


def _market_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    mapping = {
        "online": "线上",
        "offline": "线下",
        "platform_ecommerce": "平台电商",
        "professional_ecommerce": "专业电商",
        "test_platform": "测试平台",
    }
    return mapping.get(text.lower(), text)


def _label_code(code: Any) -> str:
    if code is None:
        return ""
    text = str(code).strip()
    if not text:
        return ""
    if text in BATTLEFIELD_NAMES:
        return BATTLEFIELD_NAMES[text]
    if text in TASK_NAMES:
        return TASK_NAMES[text]
    if text in GROUP_NAMES:
        return GROUP_NAMES[text]
    if text in CLAIM_LABELS_CN:
        return CLAIM_LABELS_CN[text]
    if text in PARAM_LABELS_CN:
        return PARAM_LABELS_CN[text]
    if text in SIZE_TIER_NAMES:
        return SIZE_TIER_NAMES[text]
    if text in PRICE_BAND_NAMES:
        return PRICE_BAND_NAMES[text]
    lowered = text.lower()
    inferred = _anchor_for_code(lowered)
    if inferred:
        return inferred
    if text.startswith(("BF_", "TASK_", "TG_", "tv_claim_", "tv_param_")):
        return "未命名业务维度"
    return text


def _is_ac_context(sku: dict[str, Any], size_tier: Any = None) -> bool:
    sku_code = str((sku or {}).get("sku_code") or "").upper()
    tier = str(size_tier or (sku or {}).get("size_tier") or "")
    return sku_code.startswith("AC") or tier.startswith(("wall_hp_", "floor_hp_"))


def _category_noun(sku: dict[str, Any]) -> str:
    if _is_ac_context(sku):
        return "空调"
    category = str((sku or {}).get("category_code") or (sku or {}).get("product_category") or "").upper()
    if category == "TV" or str((sku or {}).get("sku_code") or "").upper().startswith("TV"):
        return "电视"
    return "产品"


def _price_context_noun(sku: dict[str, Any]) -> str:
    if _is_ac_context(sku):
        return "该匹数价格段空调"
    if _category_noun(sku) == "电视":
        return "该尺寸价格段电视"
    return "该规格价格段产品"


def _evidence_text(examples: list[Any]) -> str:
    if not examples:
        return ""
    first = examples[0]
    if isinstance(first, dict):
        text = str(first.get("text") or first.get("comment") or "").strip()
    else:
        text = str(first or "").strip()
    if not text:
        return ""
    if len(text) > 80:
        text = text[:79] + "。"
    return f"“{text}”。"


def _top_competitor_summary_lines(target_name: str, top_competitors: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(top_competitors[:3], start=1):
        candidate_name = _display_name(item.get("candidate") or {})
        context = _join_cn(item["shared_business_context"][:5]) or "核心成交理由"
        anchors = _join_cn(item["value_anchor"]["shared_anchors"][:4]) or "关键价值锚点"
        lines.append(
            f"{index}. {candidate_name}：{item['role_cn']}。{item['purchase_pool']['reason_cn']}，"
            f"在{context}上与 {target_name} 形成同场比较；共享价值锚点集中在{anchors}，"
            f"{item['market_validation']['summary_cn']}。"
        )
    return lines


def _sku_profile_lines(
    sku_name: str,
    sku: dict[str, Any],
    sections: dict[str, Any],
    *,
    role: str,
    competitor_item: dict[str, Any] | None = None,
) -> list[str]:
    heading_prefix = "3." if role == "target" else ""
    heading_level = "###" if role == "target" else "####"
    lines: list[str] = []
    lines.extend([f"{heading_level} {heading_prefix + '1 ' if heading_prefix else ''}市场事实", ""])
    lines.extend(_market_fact_lines(sku, sections, competitor_item=competitor_item))
    lines.extend(["", f"{heading_level} {heading_prefix + '2 ' if heading_prefix else ''}参数事实", ""])
    lines.extend(_parameter_fact_lines(sections))
    lines.extend(["", f"{heading_level} {heading_prefix + '3 ' if heading_prefix else ''}卖点事实", ""])
    lines.extend(_claim_fact_lines(sections))
    lines.extend(["", f"{heading_level} {heading_prefix + '4 ' if heading_prefix else ''}评论事实", ""])
    lines.extend(_comment_fact_lines(sections))
    lines.extend(["", f"{heading_level} {heading_prefix + '5 ' if heading_prefix else ''}用户任务、目标客群、价值战场", ""])
    lines.extend(_semantic_fact_lines(sections))
    if role == "competitor":
        lines.extend(["", f"#### 对 {sku_name} 的竞争含义", ""])
        lines.extend(_competitor_meaning_lines(competitor_item or {}))
    return lines


def _market_fact_lines(
    sku: dict[str, Any],
    sections: dict[str, Any],
    *,
    competitor_item: dict[str, Any] | None = None,
) -> list[str]:
    metrics = _market_metrics(sections)
    position = _market_position(sections)
    size = position.get("screen_size_inch") or sku.get("screen_size_inch")
    size_tier = position.get("size_tier") or sku.get("size_tier")
    price_band = position.get("price_band_in_size_tier") or sku.get("price_band_in_size_tier")
    price = metrics.get("price_wavg") or metrics.get("price_latest") or sku.get("weighted_price")
    weekly_sales = metrics.get("avg_weekly_sales_volume") or sku.get("avg_weekly_sales_volume")
    lines = [
        _size_price_fact_line(size=size, size_tier=size_tier, price_band=price_band, price=price, sku=sku),
        f"- 市场表现：周均销量约{_format_unit_count(weekly_sales) or '未知'}台；主渠道为{_market_label(metrics.get('main_channel_type')) or '未知'}，主平台为{_market_label(metrics.get('main_platform')) or '未知'}。",
    ]
    price_percentile = _percentile_phrase(position.get("price_percentile_in_size"))
    volume_percentile = _percentile_phrase(position.get("volume_percentile_in_size"))
    if price_percentile or volume_percentile:
        lines.append(f"- 同尺寸段位置：价格分位{price_percentile or '未知'}，销量分位{volume_percentile or '未知'}，同池 SKU 数{_format_number(position.get('same_pool_sku_count')) or '未知'}。")
    if competitor_item:
        candidate = competitor_item.get("candidate") or {}
        lines.append(f"- 相对本品：{_price_gap_phrase(candidate.get('price_gap_pct_to_target'))}；{competitor_item['market_validation']['summary_cn']}。")
    return lines


def _size_price_fact_line(*, size: Any, size_tier: Any, price_band: Any, price: Any, sku: dict[str, Any]) -> str:
    size_tier_label = SIZE_TIER_NAMES.get(str(size_tier), "尺寸段未知")
    price_band_label = PRICE_BAND_NAMES.get(str(price_band), "价格带未知")
    if _is_ac_context(sku, size_tier):
        return f"- 匹数价格：{size_tier_label}，{price_band_label}，线上均价约{_format_money(price) or '未知'}。"
    return f"- 尺寸价格：{_format_number(size) or '未知'}英寸，{size_tier_label}，{price_band_label}，线上均价约{_format_money(price) or '未知'}。"


def _parameter_fact_lines(sections: dict[str, Any]) -> list[str]:
    param = sections.get("parameter_fact") or {}
    summary = param.get("summary") or {}
    rows = _business_param_profile_rows(sections)
    if not rows:
        return ["- 当前参数事实不足，需要补齐核心参数后再做产品力判断。"]
    highlights = [f"{dimension}：{judgement}" for dimension, judgement, _evidence, _meaning in rows[:4]]
    lines = [f"- 参数解读：{_join_cn(highlights)}。"]
    meanings = _unique_strings([meaning for _dimension, _judgement, _evidence, meaning in rows[:3]])
    if meanings:
        lines.append(f"- 业务含义：{_join_cn(meanings[:2])}。")
    completeness = _decimal(summary.get("param_completeness") or param.get("param_completeness"))
    known = summary.get("known_param_count") or param.get("known_param_count")
    conflict = summary.get("conflict_count") or param.get("conflict_count")
    if completeness is not None or known is not None or conflict is not None:
        lines.append(
            f"- 参数质量：已知参数{_format_number(known) or '未知'}项，完整度{_pct(completeness) if completeness is not None else '未知'}，冲突项{_format_number(conflict) or '0'}。"
        )
    dimension_tiers = _dimension_tier_text(param.get("dimension_tier_profile") or {})
    if dimension_tiers:
        lines.append(f"- 参数档位：{dimension_tiers}。")
    return lines


def _claim_fact_lines(sections: dict[str, Any]) -> list[str]:
    claim = sections.get("claim_fact") or {}
    comment = sections.get("comment_fact") or {}
    fact_claims = _labels_for_codes(claim.get("fact_claim_codes") or [])[:10]
    unsupported = _labels_for_codes(claim.get("unsupported_claim_codes") or [])[:5]
    supported = _labels_for_codes(comment.get("supported_claim_codes") or [])[:8]
    contradicted = _labels_for_codes(comment.get("contradicted_claim_codes") or [])[:8]
    lines = [f"- 事实卖点：{_join_cn(fact_claims) or '当前无稳定事实卖点'}。"]
    if supported:
        lines.append(f"- 评论支撑卖点：{_join_cn(supported)}。")
    if contradicted:
        lines.append(f"- 评论负向或拖后腿卖点：{_join_cn(contradicted)}。")
    if unsupported:
        lines.append(f"- 需复核表达：{_join_cn(unsupported)}，当前参数或评论支撑不足。")
    return lines


def _comment_fact_lines(sections: dict[str, Any]) -> list[str]:
    comment = sections.get("comment_fact") or {}
    summary = comment.get("summary") or {}
    count = summary.get("comment_sentence_count") or comment.get("comment_sentence_count")
    product_count = summary.get("product_fact_sentence_count") or comment.get("product_fact_sentence_count")
    positive = summary.get("positive_sentence_count") or comment.get("positive_sentence_count")
    negative = summary.get("negative_sentence_count") or comment.get("negative_sentence_count")
    examples = comment.get("evidence_examples") or []
    supported_params = _labels_for_codes(comment.get("supported_param_codes") or [])[:6]
    contradicted_params = _labels_for_codes(comment.get("contradicted_param_codes") or [])[:6]
    lines = [
        f"- 评论样本：有效评论句约{_format_number(count) or '未知'}句，其中产品事实句约{_format_number(product_count) or '未知'}句，正向{_format_number(positive) or '未知'}句，负向{_format_number(negative) or '未知'}句。"
    ]
    if supported_params:
        lines.append(f"- 评论支撑参数：{_join_cn(supported_params)}。")
    if contradicted_params:
        lines.append(f"- 评论质疑参数：{_join_cn(contradicted_params)}。")
    example_text = _evidence_text(examples)
    if example_text:
        lines.append(f"- 典型用户声音：{example_text}")
    return lines


def _semantic_fact_lines(sections: dict[str, Any]) -> list[str]:
    task = sections.get("user_task") or {}
    group = sections.get("target_group") or {}
    battlefield = sections.get("value_battlefield") or {}
    lines = [
        f"- 主用户任务：{_label_code(task.get('primary_user_task_code')) or '暂未形成稳定主任务'}；辅用户任务：{_join_cn(_labels_for_codes(task.get('secondary_user_task_codes') or [])[:5]) or '暂无'}。",
        f"- 主目标客群：{_label_code(group.get('primary_target_group_code')) or '暂未形成稳定主客群'}；辅目标客群：{_join_cn(_labels_for_codes(group.get('secondary_target_group_codes') or [])[:5]) or '暂无'}。",
        f"- 主价值战场：{_label_code(battlefield.get('primary_battlefield_code')) or '暂未形成稳定主战场'}；辅价值战场：{_join_cn(_labels_for_codes(battlefield.get('secondary_battlefield_codes') or [])[:5]) or '暂无'}。",
    ]
    opportunities = _labels_for_codes(battlefield.get("opportunity_battlefield_codes") or [])[:5]
    drags = _labels_for_codes(battlefield.get("drag_factor_battlefield_codes") or [])[:5]
    if opportunities:
        lines.append(f"- 机会战场：{_join_cn(opportunities)}。")
    if drags:
        lines.append(f"- 拖后腿战场：{_join_cn(drags)}。")
    return lines


def _target_strength_risk_lines(target: dict[str, Any], sections: dict[str, Any], top_competitors: list[dict[str, Any]]) -> list[str]:
    metrics = _market_metrics(sections)
    position = _market_position(sections)
    anchors = _unique_strings(*[item["value_anchor"]["shared_anchors"] for item in top_competitors])[:6]
    supported_claims = _labels_for_codes((sections.get("comment_fact") or {}).get("supported_claim_codes") or [])[:6]
    contradicted_claims = _labels_for_codes((sections.get("comment_fact") or {}).get("contradicted_claim_codes") or [])[:6]
    lines = [
        f"- 优势：{_display_name(target)} 已经站在{SIZE_TIER_NAMES.get(str(position.get('size_tier') or target.get('size_tier')), '目标尺寸段')}的{PRICE_BAND_NAMES.get(str(position.get('price_band_in_size_tier') or target.get('price_band_in_size_tier')), '目标价格带')}，周均销量约{_format_unit_count(metrics.get('avg_weekly_sales_volume') or target.get('avg_weekly_sales_volume')) or '未知'}台，具备真实成交基础。",
        f"- 优势：与重点竞品共同争夺的价值锚点集中在{_join_cn(anchors) or '高端画质、娱乐体验和智能互联'}，显示本品已经进入真实购买场景中的同池比较，具备可被用户理解的支付理由。",
    ]
    if supported_claims:
        lines.append(f"- 优势：评论已经支撑{_join_cn(supported_claims)}，这些卖点可作为导购端的溢价解释入口。")
    if contradicted_claims:
        lines.append(f"- 短板：{_join_cn(contradicted_claims)}存在评论负向信号，需要在详情页、导购话术和实际体验中补强。")
    unsupported = _labels_for_codes((sections.get("claim_fact") or {}).get("unsupported_claim_codes") or [])[:5]
    if unsupported:
        lines.append(f"- 短板：{_join_cn(unsupported)}当前支撑不足，容易被竞品用更直观的场景表达截流。")
    return lines


def _competitor_table_lines(top_competitors: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| 竞品 | 竞争角色 | 购买池 | 价值战场重合 | 用户任务重合 | 目标客群重合 | 关键价值锚点 | 市场验证 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for item in top_competitors:
        lines.append(
            "| "
            + " | ".join(
                [
                    _display_name(item.get("candidate") or {}),
                    item["role_cn"],
                    item["purchase_pool"]["reason_cn"],
                    _pct(item["weighted_overlap"].get("battlefield")),
                    _pct(item["weighted_overlap"].get("user_task")),
                    _pct(item["weighted_overlap"].get("target_group")),
                    _join_cn(item["value_anchor"]["shared_anchors"][:3]) or "-",
                    item["market_validation"]["level_cn"],
                ]
            )
            + " |"
        )
    return lines


def _competitor_meaning_lines(item: dict[str, Any]) -> list[str]:
    if not item:
        return ["- 当前竞品重合关系不足，暂不能输出稳定竞争含义。"]
    return [
        f"- 购买池：{item['purchase_pool']['reason_cn']}。",
        f"- 重合场景：价值战场{_pct(item['weighted_overlap'].get('battlefield'))}、用户任务{_pct(item['weighted_overlap'].get('user_task'))}、目标客群{_pct(item['weighted_overlap'].get('target_group'))}。",
        f"- 替代逻辑：{item['replacement_pressure']['reason_cn']}。",
    ]


def _competitor_advantage_risk_lines(item: dict[str, Any]) -> list[str]:
    candidate = item.get("candidate") or {}
    shared = item["value_anchor"]["shared_anchors"]
    candidate_stronger = item["value_anchor"]["candidate_stronger_anchors"]
    target_stronger = item["value_anchor"]["target_stronger_anchors"]
    lines = [
        f"- 优势：{_display_name(candidate)} 在{_join_cn(shared[:5]) or '核心成交价值'}上可与目标 SKU 同台比较，用户不需要切换购买场景即可完成替代判断。",
        f"- 优势：{item['market_validation']['summary_cn']}，具备真实分流能力。",
    ]
    if candidate_stronger:
        lines.append(f"- 竞争压力：竞品在{_join_cn(candidate_stronger[:4])}上表达更突出，会抬高用户对同价位产品的期望。")
    if target_stronger:
        lines.append(f"- 可反击点：目标 SKU 在{_join_cn(target_stronger[:4])}上仍有差异化空间，应转化成清晰的用户收益表达。")
    if not candidate_stronger and not target_stronger:
        lines.append("- 短板：双方关键价值锚点接近，竞品更容易把比较拉回价格和促销，需要目标 SKU 主动解释溢价理由。")
    return lines


def _competitor_response_lines(target_name: str, item: dict[str, Any]) -> list[str]:
    candidate_name = _display_name(item.get("candidate") or {})
    pressure = item["replacement_pressure"]["type"]
    shared = _join_cn(item["value_anchor"]["shared_anchors"][:4]) or "核心价值锚点"
    if pressure == "downtrade_diversion":
        return [
            f"- 对 {candidate_name} 不宜只打价格战，应把 {target_name} 的{shared}讲成可感知体验，避免用户把两款简单归为同类低价替代。",
            "- 促销策略上可用限时补贴、以旧换新和安装服务权益缩小到手价感知差，避免长期下调标价。",
        ]
    if pressure == "uptrade_alternative":
        return [
            f"- 对 {candidate_name} 应强调 {target_name} 在同预算内已经覆盖的{shared}，把追加预算的必要性降下来。",
            "- 产品页和导购端要给出“多花的钱买到什么”的反向比较，限制用户上探预算。",
        ]
    if pressure == "scenario_or_config_benchmark":
        return [
            f"- 对 {candidate_name} 要补齐场景解释，把 {target_name} 的技术参数转译成客厅观影、游戏流畅、家庭长看的实际收益。",
            "- 如果竞品在外观、贴墙、音响或智能场景上更容易被理解，市场素材应增加场景化对比，避免只堆参数表。",
        ]
    return [
        f"- 对 {candidate_name} 应直接管理同池替代关系，围绕{shared}明确海信的差异化支付理由。",
        "- 详情页首屏、导购话术和直播讲解要先讲用户收益，再讲参数证据，降低用户把两款视为等价替代的概率。",
    ]


def _sales_talk_lines(target_name: str, item: dict[str, Any]) -> list[str]:
    candidate_name = _display_name(item.get("candidate") or {})
    shared = _join_cn(item["value_anchor"]["shared_anchors"][:4]) or "画质、娱乐和智能体验"
    target_stronger = _join_cn(item["value_anchor"]["target_stronger_anchors"][:3])
    candidate_stronger = _join_cn(item["value_anchor"]["candidate_stronger_anchors"][:3])
    lines = [
        f"- 开场：如果用户在 {candidate_name} 和 {target_name} 之间比较，先确认他的核心用途是客厅观影、游戏娱乐、家庭长看还是智能互联，再把比较收束到{shared}。",
        f"- 价值解释：{target_name} 的讲法应围绕“同尺寸同预算下，哪些体验能长期感知”，避免只说型号和参数名。",
    ]
    if target_stronger:
        lines.append(f"- 反击话术：可以重点讲 {target_stronger}，把海信的差异化从配置项转成用户收益。")
    if candidate_stronger:
        lines.append(f"- 风险话术：当用户提到竞品的 {candidate_stronger}，需要承认其优势，再回到海信在主用途上的综合体验和售后服务承诺。")
    return lines


def _target_growth_lines(
    target_name: str,
    target: dict[str, Any],
    sections: dict[str, Any],
    top_competitors: list[dict[str, Any]],
) -> list[str]:
    supported = _labels_for_codes((sections.get("comment_fact") or {}).get("supported_claim_codes") or [])[:5]
    contradicted = _labels_for_codes((sections.get("comment_fact") or {}).get("contradicted_claim_codes") or [])[:5]
    shared_anchors = _unique_strings(*[item["value_anchor"]["shared_anchors"] for item in top_competitors])[:6]
    lines = [
        f"- 市场打法：{target_name} 应把资源集中在{_join_cn(shared_anchors) or '当前核心成交锚点'}，这些是用户会拿竞品横向比较的付费点。",
        "- 价格策略：保留高价段形象，但在重点竞品贴身促销时使用短周期权益包、换新补贴和渠道专项价，减少“配置接近但价格更顺”的分流。",
    ]
    if supported:
        lines.append(f"- 卖点策略：把评论已验证的{_join_cn(supported)}前置为核心溢价卖点，形成“用户认可 + 参数支撑 + 场景收益”的闭环。")
    if contradicted:
        lines.append(f"- 口碑策略：优先处理{_join_cn(contradicted)}的负向体验，负向评论会直接削弱主战场卖点的溢价能力。")
    lines.append("- 产品策略：下一轮迭代要围绕主战场和辅战场补强用户能感知的差异点，尤其是竞品更容易讲清楚的外观、空间融合、音画氛围或智能连接。")
    return lines


def _product_manager_lines(target_name: str, sections: dict[str, Any], top_competitors: list[dict[str, Any]]) -> list[str]:
    battlefield = sections.get("value_battlefield") or {}
    claim = sections.get("claim_fact") or {}
    comment = sections.get("comment_fact") or {}
    primary_battlefield = _label_code(battlefield.get("primary_battlefield_code")) or "主价值战场"
    premium_claims = _labels_for_codes(comment.get("supported_claim_codes") or claim.get("fact_claim_codes") or [])[:5]
    lines = [
        f"- 围绕{primary_battlefield}重写 {target_name} 的价值表达：先定义用户愿意付费的场景，再挂接参数和卖点证据。",
        f"- 将{_join_cn(premium_claims) or '已验证卖点'}设为核心溢价卖点池，所有详情页、直播和导购材料保持同一解释口径。",
        "- 建立前三竞品的常态监控：价格变化、主图卖点、直播话术、用户评论新增负向点，每周更新一次。",
    ]
    for item in top_competitors[:3]:
        lines.append(f"- 对 {_display_name(item.get('candidate') or {})}：跟踪其{_join_cn(item['value_anchor']['candidate_stronger_anchors'][:3]) or item['replacement_pressure']['type_cn']}，判断是否需要补素材、补权益或补产品配置。")
    return lines


def _enrich_competitor(target: dict[str, Any], target_fact_brief: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    semantic = item.get("semantic_overlap") or {}
    param_claim = item.get("param_claim_overlap") or {}
    sales = item.get("sales_overlap") or {}
    candidate = item.get("candidate") or {}
    purchase_pool = _purchase_pool(target, candidate)
    battlefield = _dimension_score(semantic.get("value_battlefield") or {})
    task = _dimension_score(semantic.get("user_task") or {})
    group = _dimension_score(semantic.get("target_group") or {})
    value_anchor = _value_anchor(param_claim, target_fact_brief)
    market_validation = _market_validation(sales, candidate)
    replacement = _replacement_pressure(purchase_pool, battlefield, task, group, value_anchor, candidate)
    market_score = _market_validation_score(market_validation.get("level"))
    business_score = (
        purchase_pool["score"] * SCORE_WEIGHTS["purchase_pool"]
        + battlefield["score"] * SCORE_WEIGHTS["battlefield"]
        + task["score"] * SCORE_WEIGHTS["user_task"]
        + group["score"] * SCORE_WEIGHTS["target_group"]
        + value_anchor["score"] * SCORE_WEIGHTS["value_anchor"]
        + replacement["score"] * SCORE_WEIGHTS["replacement_pressure"]
        + market_score * SCORE_WEIGHTS["market_validation"]
    )
    role = _base_role(target, purchase_pool, replacement, candidate)
    matched_dimensions = {
        "battlefield": _dimension_labels(semantic.get("value_battlefield") or {}, BATTLEFIELD_NAMES),
        "user_task": _dimension_labels(semantic.get("user_task") or {}, TASK_NAMES),
        "target_group": _dimension_labels(semantic.get("target_group") or {}, GROUP_NAMES),
    }
    shared_business_context = _unique_strings(
        matched_dimensions["battlefield"][:2],
        matched_dimensions["user_task"][:2],
        matched_dimensions["target_group"][:2],
        value_anchor["shared_anchors"][:2],
    )
    enriched = {
        **item,
        "business_score": _float(business_score),
        "role": role,
        "role_cn": ROLE_CN.get(role, role),
        "purchase_pool": {
            "level": purchase_pool["level"],
            "score": _float(purchase_pool["score"]),
            "reason_cn": purchase_pool["reason_cn"],
        },
        "weighted_overlap": {
            "battlefield": _float(battlefield["score"]),
            "user_task": _float(task["score"]),
            "target_group": _float(group["score"]),
        },
        "matched_dimensions": matched_dimensions,
        "shared_business_context": shared_business_context,
        "value_anchor": {
            "score": _float(value_anchor["score"]),
            "shared_anchors": value_anchor["shared_anchors"],
            "target_stronger_anchors": value_anchor["target_stronger_anchors"],
            "candidate_stronger_anchors": value_anchor["candidate_stronger_anchors"],
        },
        "replacement_pressure": {
            "type": replacement["type"],
            "type_cn": replacement["type_cn"],
            "score": _float(replacement["score"]),
            "reason_cn": replacement["reason_cn"],
        },
        "market_validation": market_validation,
        "exclusion_reason_cn": _exclusion_reason(purchase_pool, battlefield, task, group, value_anchor, candidate),
    }
    return enriched


def _purchase_pool(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    target_size = _decimal(target.get("screen_size_inch"))
    candidate_size = _decimal(candidate.get("screen_size_inch"))
    exact_size = target_size is not None and candidate_size is not None and abs(target_size - candidate_size) <= Decimal("0.5")
    same_tier = bool(target.get("size_tier")) and target.get("size_tier") == candidate.get("size_tier")
    target_band = str(target.get("price_band_in_size_tier") or "").lower()
    candidate_band = str(candidate.get("price_band_in_size_tier") or "").lower()
    same_band = target_band and target_band == candidate_band
    adjacent_band = _adjacent_price_band(target_band, candidate_band)
    if exact_size and same_band:
        return {"level": "P0", "score": Decimal("1.00"), "reason_cn": f"同{_format_number(target_size)}英寸、同价格带购买池"}
    if exact_size and adjacent_band:
        return {"level": "P1", "score": Decimal("0.85"), "reason_cn": f"同{_format_number(target_size)}英寸、邻近价格带购买池"}
    if same_tier and same_band:
        return {"level": "P2", "score": Decimal("0.70"), "reason_cn": "同尺寸段、同价格带购买池"}
    if same_tier and adjacent_band:
        return {"level": "P3", "score": Decimal("0.55"), "reason_cn": "同尺寸段、邻近价格带购买池"}
    return {"level": "P4", "score": Decimal("0.35"), "reason_cn": "语义相关但购买池偏离"}


def _dimension_score(overlap: dict[str, Any]) -> dict[str, Any]:
    weighted = _decimal(overlap.get("weighted_overlap_score"))
    if weighted is None:
        weighted = _decimal(overlap.get("overlap_score")) or Decimal("0")
    risk = _decimal(overlap.get("risk_overlap_score")) or Decimal("0")
    return {"score": max(Decimal("0"), weighted - risk * Decimal("0.25"))}


def _value_anchor(param_claim: dict[str, Any], target_fact_brief: dict[str, Any]) -> dict[str, Any]:
    del target_fact_brief
    parameter = param_claim.get("parameter_overlap") or {}
    claim = param_claim.get("claim_overlap") or {}
    position = param_claim.get("claim_position_overlap") or {}
    shared = _anchors_from_codes(parameter.get("matched_codes") or [], claim.get("matched_codes") or [], position.get("matched_codes") or [])
    target_only = _anchors_from_codes(parameter.get("target_only_codes") or [], claim.get("target_only_codes") or [], position.get("target_only_codes") or [])
    candidate_only = _anchors_from_codes(
        parameter.get("candidate_only_codes") or [],
        claim.get("candidate_only_codes") or [],
        position.get("candidate_only_codes") or [],
    )
    param_score = _decimal(parameter.get("overlap_score")) or Decimal("0")
    claim_score = _decimal(claim.get("overlap_score")) or Decimal("0")
    position_score = _decimal(position.get("overlap_score")) or Decimal("0")
    anchor_score = Decimal(len(shared)) / Decimal(max(len(set(shared + target_only + candidate_only)), 1))
    score = max(anchor_score, param_score * Decimal("0.25") + claim_score * Decimal("0.45") + position_score * Decimal("0.30"))
    return {
        "score": min(score, Decimal("1")),
        "shared_anchors": shared,
        "target_stronger_anchors": [item for item in target_only if item not in shared],
        "candidate_stronger_anchors": [item for item in candidate_only if item not in shared],
    }


def _replacement_pressure(
    purchase_pool: dict[str, Any],
    battlefield: dict[str, Any],
    task: dict[str, Any],
    group: dict[str, Any],
    value_anchor: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    gap = _decimal(candidate.get("price_gap_pct_to_target")) or Decimal("0")
    semantic_strength = battlefield["score"] * Decimal("0.25") + task["score"] * Decimal("0.35") + group["score"] * Decimal("0.40")
    score = min(Decimal("1"), purchase_pool["score"] * Decimal("0.35") + semantic_strength * Decimal("0.35") + value_anchor["score"] * Decimal("0.30"))
    if gap <= Decimal("-0.15"):
        return {
            "type": "downtrade_diversion",
            "type_cn": "下探分流压力",
            "score": score,
            "reason_cn": "价格明显更顺，同时保留部分核心体验，会分流预算敏感用户",
        }
    if gap >= Decimal("0.15"):
        return {
            "type": "uptrade_alternative",
            "type_cn": "上探替代压力",
            "score": score,
            "reason_cn": "价格或定位上探，会吸走愿意追加预算的高端用户",
        }
    if value_anchor["candidate_stronger_anchors"]:
        return {
            "type": "scenario_or_config_benchmark",
            "type_cn": "配置/场景标杆压力",
            "score": score,
            "reason_cn": f"在{_join_cn(value_anchor['candidate_stronger_anchors'][:2])}上形成更清晰的对比",
        }
    return {
        "type": "value_substitution",
        "type_cn": "价值替代压力",
        "score": score,
        "reason_cn": "在同一购买池内承接相近成交理由，会削弱目标 SKU 的价值解释空间",
    }


def _market_validation(sales: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    overlap_week_count = int(sales.get("overlap_week_count") or 0)
    candidate_side = sales.get("candidate") or {}
    avg_weekly = (
        _decimal(candidate_side.get("avg_weekly_sales_volume_on_overlap_weeks"))
        or _decimal(candidate_side.get("avg_weekly_sales_volume"))
        or _decimal(candidate.get("avg_weekly_sales_volume"))
    )
    if overlap_week_count >= 4 and avg_weekly and avg_weekly > 0:
        level = "strong"
        level_cn = "强验证"
    elif avg_weekly and avg_weekly > 0:
        level = "medium"
        level_cn = "有成交验证"
    else:
        level = "weak"
        level_cn = "验证不足"
    if overlap_week_count > 0:
        summary = f"重叠在售周{overlap_week_count}周，候选周均销量约{_format_unit_count(avg_weekly) or '未知'}台"
    else:
        summary = f"候选周均销量约{_format_unit_count(avg_weekly) or '未知'}台，重叠在售周验证不足"
    return {
        "level": level,
        "level_cn": level_cn,
        "overlap_week_count": overlap_week_count,
        "avg_weekly_sales_volume": _float(avg_weekly),
        "summary_cn": summary,
    }


def _base_role(target: dict[str, Any], purchase_pool: dict[str, Any], replacement: dict[str, Any], candidate: dict[str, Any]) -> str:
    gap = _decimal(candidate.get("price_gap_pct_to_target")) or Decimal("0")
    if _is_ac_context(target) and purchase_pool["score"] < Decimal("0.55"):
        if abs(gap) <= Decimal("0.08") and replacement["score"] >= Decimal("0.45"):
            return "price_adjacent"
        if abs(gap) <= Decimal("0.15") and replacement["score"] >= Decimal("0.50"):
            return "scenario_alternative"
    if gap <= Decimal("-0.15"):
        return "downtrade_diversion"
    if gap >= Decimal("0.15"):
        return "uptrade_alternative"
    if abs(gap) <= Decimal("0.03") and purchase_pool["score"] >= Decimal("0.55"):
        return "price_adjacent"
    if purchase_pool["score"] >= Decimal("0.85") and replacement["score"] >= Decimal("0.60"):
        return "strong_direct"
    if purchase_pool["score"] >= Decimal("0.55"):
        return "scenario_alternative"
    return "excluded"


def _assign_top_roles(enriched: list[dict[str, Any]]) -> None:
    for item in enriched:
        if item["role"] in {"strong_direct", "price_adjacent", "scenario_alternative"} and item["business_score"] >= 0.48:
            item["role"] = "strong_direct"
            item["role_cn"] = ROLE_CN["strong_direct"]
    for item in enriched:
        if item["role"] == "strong_direct":
            item["role"] = "primary_direct"
            item["role_cn"] = ROLE_CN["primary_direct"]
            return


def _bucket_competitors(enriched: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in ROLE_CN}
    for item in enriched:
        buckets.setdefault(item["role"], []).append(_bucket_item(item))
    return buckets


def _bucket_item(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("candidate") or {}
    return {
        "sku_code": candidate.get("sku_code"),
        "brand_name": candidate.get("brand_name"),
        "model_name": candidate.get("model_name"),
        "role_cn": item.get("role_cn"),
        "business_score": item.get("business_score"),
        "purchase_pool": item.get("purchase_pool"),
        "replacement_pressure": item.get("replacement_pressure"),
    }


def _select_top_competitors(enriched: list[dict[str, Any]], *, target: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    if top_n <= 0:
        return []
    selected: list[dict[str, Any]] = []
    direct = [item for item in enriched if item["role"] in {"primary_direct", "strong_direct"}]
    for item in direct[:2]:
        if item not in selected:
            selected.append(item)
    if _is_ac_context(target):
        strategic_roles = ["price_adjacent", "scenario_alternative", "downtrade_diversion", "uptrade_alternative"]
    else:
        strategic_roles = ["downtrade_diversion", "uptrade_alternative", "price_adjacent", "scenario_alternative"]
    for role in strategic_roles:
        if len(selected) >= top_n:
            break
        for item in enriched:
            if item["role"] == role and item not in selected:
                selected.append(item)
                break
    for item in enriched:
        if len(selected) >= top_n:
            break
        if item not in selected and item["role"] != "excluded":
            selected.append(item)
    return selected[:top_n]


def _dashboard_competitor_payload(index: int, item: dict[str, Any], *, report_url: str | None) -> dict[str, Any]:
    candidate = item.get("candidate") or {}
    name = _display_name(candidate)
    overlap_rows = [
        _dashboard_overlap_row(item, dimension_key="battlefield", dimension_cn="价值战场"),
        _dashboard_overlap_row(item, dimension_key="user_task", dimension_cn="用户任务"),
        _dashboard_overlap_row(item, dimension_key="target_group", dimension_cn="目标客群"),
    ]
    shared_anchors = (item.get("value_anchor") or {}).get("shared_anchors") or []
    return {
        "rank": index,
        "sku_code": candidate.get("sku_code"),
        "brand_name": candidate.get("brand_name"),
        "model_name": candidate.get("model_name"),
        "name": name,
        "role_cn": item.get("role_cn") or ROLE_CN.get(str(item.get("role") or ""), "重点竞品"),
        "pressure_cn": ((item.get("replacement_pressure") or {}).get("type_cn") or "替代压力待复核"),
        "score_cn": _dashboard_score_cn(item.get("business_score")),
        "strength_cn": _dashboard_strength_cn(item.get("business_score")),
        "score_dimensions": _dashboard_score_dimensions(item),
        "battlefield_overlap_structure": _dashboard_battlefield_overlap_structure(item),
        "reason_cn": _dashboard_reason_cn(item),
        "overlap_rows": overlap_rows,
        "shared_anchors_cn": [str(value) for value in shared_anchors[:5] if value],
        "market_validation_cn": (item.get("market_validation") or {}).get("summary_cn") or "市场验证待补充",
        "market": _dashboard_market_snapshot(candidate),
        "evidence_refs": _dashboard_evidence_refs(item),
        "action_links": _dashboard_action_links(report_url),
    }


def _dashboard_overlap_row(item: dict[str, Any], *, dimension_key: str, dimension_cn: str) -> dict[str, Any]:
    overlap = item.get("weighted_overlap") or {}
    matched_dimensions = item.get("matched_dimensions") or {}
    matched = [str(value) for value in (matched_dimensions.get(dimension_key) or [])[:5] if value]
    score = overlap.get(dimension_key)
    return {
        "dimension_cn": dimension_cn,
        "strength_cn": _dashboard_strength_cn(score),
        "score_cn": _dashboard_score_cn(score),
        "matched_points_cn": matched or ["证据不足，需复核"],
        "impact_cn": _dashboard_overlap_impact(dimension_cn, matched),
    }


def _dashboard_score_dimensions(item: dict[str, Any]) -> list[dict[str, Any]]:
    overlap = item.get("weighted_overlap") or {}
    return [
        {"dimension_cn": "购买池", "score": _dashboard_score_value((item.get("purchase_pool") or {}).get("score"))},
        {"dimension_cn": "价值战场", "score": _dashboard_score_value(overlap.get("battlefield"))},
        {"dimension_cn": "用户任务", "score": _dashboard_score_value(overlap.get("user_task"))},
        {"dimension_cn": "目标客群", "score": _dashboard_score_value(overlap.get("target_group"))},
        {"dimension_cn": "价值锚点", "score": _dashboard_score_value((item.get("value_anchor") or {}).get("score"))},
        {"dimension_cn": "市场验证", "score": _dashboard_score_value(_market_validation_score((item.get("market_validation") or {}).get("level")))},
    ]


def _dashboard_battlefield_overlap_structure(item: dict[str, Any]) -> dict[str, Any]:
    battlefield = ((item.get("semantic_overlap") or {}).get("value_battlefield") or {})
    target_items = {
        str(row.get("code")): [str(role) for role in row.get("roles") or []]
        for row in battlefield.get("target_items") or []
        if row.get("code")
    }
    candidate_items = {
        str(row.get("code")): [str(role) for role in row.get("roles") or []]
        for row in battlefield.get("candidate_items") or []
        if row.get("code")
    }
    codes = set(target_items) | set(candidate_items)
    union = _decimal(battlefield.get("positive_weighted_union")) or Decimal("0")
    if union <= 0:
        return {"score": 0, "segments": [], "loss": 0, "notes_cn": []}

    grouped: dict[str, dict[str, Any]] = {
        "主战场重合": {"segment_cn": "主战场重合", "value": Decimal("0"), "battlefields_cn": []},
        "辅战场重合": {"segment_cn": "辅战场重合", "value": Decimal("0"), "battlefields_cn": []},
        "机会战场重合": {"segment_cn": "机会战场重合", "value": Decimal("0"), "battlefields_cn": []},
    }
    loss = Decimal("0")
    notes: list[str] = []
    for code in sorted(codes):
        target_weight = max(_role_weight(target_items.get(code, [])), Decimal("0"))
        candidate_weight = max(_role_weight(candidate_items.get(code, [])), Decimal("0"))
        contribution = min(target_weight, candidate_weight)
        segment_loss = max(target_weight, candidate_weight) - contribution
        name = BATTLEFIELD_NAMES.get(code, code)
        if contribution > 0:
            bucket = _battlefield_overlap_segment_bucket(target_weight)
            grouped[bucket]["value"] += contribution
            grouped[bucket]["battlefields_cn"].append(name)
        if segment_loss > 0:
            loss += segment_loss
            if target_weight > 0 and candidate_weight > 0:
                notes.append(f"{name}主辅/机会错位")
            elif target_weight > 0:
                notes.append(f"{name}目标独有")
            elif candidate_weight > 0:
                notes.append(f"{name}竞品独有")

    segments = [
        {
            "segment_cn": row["segment_cn"],
            "value": _dashboard_pct_value(row["value"], union),
            "battlefields_cn": row["battlefields_cn"],
        }
        for row in grouped.values()
        if row["value"] > 0
    ]
    if loss > 0:
        segments.append({"segment_cn": "错位/缺口", "value": _dashboard_pct_value(loss, union), "battlefields_cn": notes[:5]})
    return {
        "score": _dashboard_score_value(battlefield.get("weighted_overlap_score")),
        "segments": segments,
        "loss": _dashboard_pct_value(loss, union),
        "notes_cn": notes[:5],
    }


def _battlefield_overlap_segment_bucket(target_weight: Decimal) -> str:
    if target_weight >= Decimal("1"):
        return "主战场重合"
    if target_weight >= Decimal("0.75"):
        return "辅战场重合"
    return "机会战场重合"


def _dashboard_pct_value(value: Decimal, denominator: Decimal) -> float:
    if denominator <= 0:
        return 0.0
    return float((value / denominator * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _dashboard_score_value(value: Any) -> int:
    score = _decimal(value)
    if score is None:
        return 0
    score = max(Decimal("0"), min(Decimal("1"), score))
    return int((score * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _dashboard_reason_cn(item: dict[str, Any]) -> str:
    name = _display_name(item.get("candidate") or {})
    role = item.get("role_cn") or "重点竞品"
    pressure = (item.get("replacement_pressure") or {}).get("type_cn") or "替代压力"
    context = _join_cn((item.get("shared_business_context") or [])[:4])
    if context:
        return f"{name}是{role}，在{context}上与目标 SKU 重合，主要形成{pressure}。"
    return f"{name}是{role}，主要形成{pressure}，详细重合依据需查看报告佐证。"


def _dashboard_overlap_impact(dimension_cn: str, matched_points: list[str]) -> str:
    if not matched_points:
        return f"{dimension_cn}证据不足，当前只能作为复核点，不能单独支撑核心竞品判断。"
    points = _join_cn(matched_points[:3])
    if dimension_cn == "价值战场":
        return f"两款产品共同争夺{points}等价值诉求，用户会在同一购买池里横向比较。"
    if dimension_cn == "用户任务":
        return f"用户购买时要完成的核心任务集中在{points}，会影响同一批用户的最终候选清单。"
    if dimension_cn == "目标客群":
        return f"共同覆盖{points}，客群重叠会放大配置、价格和卖点表达的直接对比。"
    return f"共同命中{points}，会提高同场比较概率。"


def _dashboard_summary(target_name: str, competitors: list[dict[str, Any]], target_fact_brief: dict[str, Any]) -> str:
    if not competitors:
        return f"{target_name} 当前没有足够证据形成稳定重点竞品。"
    first = competitors[0]
    evidence_state = _target_evidence_state(target_fact_brief)
    suffix = "" if evidence_state["semantic_verified"] else " 当前语义或评论验证不完整，排序需结合报告复核。"
    return f"当前识别出 {len(competitors)} 个重点竞品，首选是{first.get('name')}；看板重点展示战场、任务和客群的重合结构。{suffix}".strip()


def _dashboard_target_summary(target: dict[str, Any], target_fact_brief: dict[str, Any]) -> str:
    sections = _fact_sections(target_fact_brief)
    market_position = _market_position(sections)
    size = _format_number(market_position.get("screen_size_inch") or target.get("screen_size_inch"))
    band = PRICE_BAND_NAMES.get(str(market_position.get("price_band_in_size_tier") or target.get("price_band_in_size_tier")), "")
    parts = []
    if size:
        parts.append(f"{size}寸")
    if band:
        parts.append(band)
    return f"当前可观测线上样本内的{'、'.join(parts)}目标 SKU。" if parts else "当前可观测线上样本内的目标 SKU。"


def _dashboard_target_market_snapshot(target: dict[str, Any], target_fact_brief: dict[str, Any]) -> dict[str, Any]:
    sections = _fact_sections(target_fact_brief)
    metrics = _market_metrics(sections)
    return _dashboard_market_snapshot({**target, **metrics})


def _dashboard_market_snapshot(source: dict[str, Any]) -> dict[str, Any]:
    price = _decimal(source.get("price_wavg") or source.get("price_latest") or source.get("weighted_price"))
    weekly_sales = _decimal(source.get("avg_weekly_sales_volume"))
    if weekly_sales is None:
        total_sales = _decimal(source.get("sales_volume_total"))
        active_weeks = _decimal(source.get("active_week_count"))
        if total_sales is not None and active_weeks is not None and active_weeks > 0:
            weekly_sales = total_sales / active_weeks
    return {
        "price": _float(price) if price is not None else None,
        "avg_weekly_sales_volume": _float(weekly_sales) if weekly_sales is not None else None,
    }


def _dashboard_score_cn(value: Any) -> str:
    score = _decimal(value)
    if score is None:
        return "待复核"
    return f"{(score * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)}分"


def _dashboard_strength_cn(value: Any) -> str:
    score = _decimal(value)
    if score is None:
        return "待复核"
    if score >= Decimal("0.75"):
        return "强重合"
    if score >= Decimal("0.55"):
        return "中高重合"
    if score >= Decimal("0.35"):
        return "中重合"
    if score > 0:
        return "弱重合"
    return "证据不足"


def _dashboard_evidence_refs(item: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    if any((item.get("matched_dimensions") or {}).get(key) for key in ("battlefield", "user_task", "target_group")):
        refs.append("语义证据")
    if (item.get("value_anchor") or {}).get("shared_anchors"):
        refs.append("参数卖点证据")
    if (item.get("market_validation") or {}).get("level") != "weak":
        refs.append("市场证据")
    return refs or ["证据待复核"]


def _dashboard_report_links(report_url: str | None) -> list[dict[str, Any]]:
    if not report_url:
        return []
    return [{"label": "完整竞品分析报告", "url": report_url, "type": "report"}]


def _dashboard_action_links(report_url: str | None) -> list[dict[str, Any]]:
    links = [{"label": "查看重合依据", "section_code": "overlap_rows", "type": "section"}]
    if report_url:
        links.insert(0, {"label": "查看完整报告", "url": report_url, "type": "report"})
    return links


def _feishu_markdown(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _dashboard_conclusion_markdown(dashboard_payload: dict[str, Any], competitors: list[dict[str, Any]]) -> str:
    target = dashboard_payload.get("target") or {}
    target_name = str(target.get("display_name") or "目标 SKU")
    if not competitors:
        return f"**结论：{target_name} 当前没有稳定重点竞品**\n缺少可支撑看板的 Top 3 竞品结果，请查看报告证据缺口。"
    first = competitors[0]
    other_parts = [
        f"{_dashboard_competitor_alias(item)}偏{_dashboard_role_short(item)}"
        for item in competitors[1:3]
        if isinstance(item, dict)
    ]
    tail = f"；另外，{'、'.join(other_parts)}。" if other_parts else "。"
    return (
        f"**结论：优先盯 {_dashboard_competitor_alias(first)}**\n"
        f"{_dashboard_competitor_alias(first)}与{target_name}在战场、任务和客群三层重合最完整，"
        f"会形成{first.get('pressure_cn') or '替代压力'}{tail}"
    )


def _feishu_score_radar_chart(competitors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tag": "chart",
        "element_id": "score_radar",
        "aspect_ratio": "1:1",
        "height": "320px",
        "preview": False,
        "color_theme": "brand",
        "chart_spec": {
            "type": "radar",
            "data": {"values": _dashboard_radar_values(competitors)},
            "categoryField": "dimension",
            "valueField": "score",
            "seriesField": "competitor",
            "area": {"visible": True},
            "outerRadius": 0.78,
            "axes": [
                {
                    "orient": "radius",
                    "min": 0,
                    "max": 100,
                    "label": {"visible": True, "style": {"textAlign": "center"}},
                }
            ],
            "legends": {"visible": True, "orient": "bottom"},
        },
    }


def _dashboard_radar_values(competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in competitors[:3]:
        competitor_name = _dashboard_competitor_alias(item)
        for dimension in _dashboard_score_dimension_rows(item):
            values.append(
                {
                    "competitor": competitor_name,
                    "dimension": dimension["dimension_cn"],
                    "score": dimension["score"],
                }
            )
    return values


def _dashboard_score_dimension_rows(competitor: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {"dimension_cn": str(row.get("dimension_cn") or ""), "score": int(row.get("score") or 0)}
        for row in competitor.get("score_dimensions") or []
        if isinstance(row, dict) and row.get("dimension_cn")
    ]
    if rows:
        return rows
    fallback: list[dict[str, Any]] = []
    for row in competitor.get("overlap_rows") or []:
        if isinstance(row, dict):
            fallback.append({"dimension_cn": str(row.get("dimension_cn") or ""), "score": _score_cn_to_int(row.get("score_cn"))})
    fallback.append({"dimension_cn": "价值锚点", "score": 0})
    fallback.append({"dimension_cn": "市场验证", "score": _market_validation_score_from_text(str(competitor.get("market_validation_cn") or ""))})
    return [row for row in fallback if row["dimension_cn"]]


def _feishu_battlefield_overlap_chart(values: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tag": "chart",
        "element_id": "battlefield_overlap",
        "aspect_ratio": "16:9",
        "height": "260px",
        "preview": False,
        "chart_spec": {
            "type": "bar",
            "data": {"values": values},
            "direction": "horizontal",
            "xField": "value",
            "yField": "competitor",
            "seriesField": "segment",
            "stack": True,
            "color": ["#155E75", "#0F9F8F", "#F59E0B", "#CBD5E1"],
            "bar": {"style": {"cornerRadius": 3}},
            "label": {
                "visible": True,
                "position": "inside",
                "formatter": "{label}",
                "smartInvert": True,
                "style": {"fontSize": 11, "fontWeight": "500", "lineHeight": 14},
            },
            "axes": [
                {"orient": "bottom", "min": 0, "max": 100, "title": {"visible": True, "text": "占总并集权重比例"}},
                {"orient": "left", "label": {"visible": True}},
            ],
            "legends": {"visible": True, "orient": "bottom"},
            "tooltip": {"visible": True},
        },
    }


def _dashboard_battlefield_chart_values(competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for item in competitors[:3]:
        competitor_name = _dashboard_competitor_alias(item)
        structure = item.get("battlefield_overlap_structure") or {}
        for row in structure.get("segments") or []:
            if not isinstance(row, dict):
                continue
            segment = str(row.get("segment_cn") or "")
            value = _decimal(row.get("value"))
            if not segment or value is None or value <= 0:
                continue
            values.append(
                {
                    "competitor": competitor_name,
                    "segment": segment,
                    "value": float(value),
                    "battlefields": "、".join(str(name) for name in (row.get("battlefields_cn") or [])[:4]),
                    "label": _battlefield_chart_label(row, value),
                    "score": structure.get("score"),
                }
            )
    return values


def _battlefield_chart_label(row: dict[str, Any], value: Decimal) -> str:
    names = [str(name) for name in row.get("battlefields_cn") or [] if name]
    compact_names = _compact_battlefield_names(names)
    value_text = f"{value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"
    return f"{compact_names} {value_text}" if compact_names else value_text


def _compact_battlefield_names(names: list[str]) -> str:
    if not names:
        return ""
    display_names: list[str] = []
    aliases = {
        "高端画质升级": "高端画质",
        "家庭护眼舒适": "护眼舒适",
        "游戏体育流畅": "游戏流畅",
        "主流客厅均衡体验": "客厅均衡",
        "智能互联体验": "智能互联",
        "家装融合": "家装融合",
        "尺寸升级": "尺寸升级",
    }
    for name in names:
        clean = (
            name.replace("主辅/机会错位", "错位")
            .replace("目标独有", "目标独有")
            .replace("竞品独有", "竞品独有")
        )
        base = clean.replace("错位", "").replace("目标独有", "").replace("竞品独有", "")
        display = aliases.get(base, clean)
        if "错位" in clean and "错位" not in display:
            display = f"{display}错位"
        if display and display not in display_names:
            display_names.append(display)
    result = "/".join(display_names[:2])
    if len(display_names) > 2:
        result += "等"
    return result


def _score_cn_to_int(value: Any) -> int:
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        return 0
    return max(0, min(100, int(match.group(1))))


def _market_validation_score_from_text(value: str) -> int:
    if "重叠" in value and "周均" in value:
        return 100
    if "周均" in value:
        return 80
    return 20


def _feishu_competitor_market_table(target: dict[str, Any], competitors: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        {
            "name": _dashboard_target_alias(target),
            "position": "被比较目标",
            "price": _format_dashboard_market_price((target.get("market") or {}).get("price")),
            "sales": _format_dashboard_market_sales((target.get("market") or {}).get("avg_weekly_sales_volume")),
        }
    ]
    for item in competitors[:3]:
        market = item.get("market") or {}
        rows.append(
            {
                "name": _dashboard_competitor_alias(item),
                "position": f"{_dashboard_role_short(item)} / {_dashboard_pressure_short(item)} / {_dashboard_strength_short(item)}",
                "price": _format_dashboard_market_price(market.get("price")),
                "sales": _format_dashboard_market_sales(market.get("avg_weekly_sales_volume")),
            }
        )
    return _feishu_table(
        element_id="competitor_market_table",
        columns=[
            _feishu_text_column("name", "竞品/目标"),
            _feishu_text_column("position", "定位"),
            _feishu_text_column("price", "均价"),
            _feishu_text_column("sales", "周均销量"),
        ],
        rows=rows,
    )


def _dashboard_target_alias(target: dict[str, Any]) -> str:
    return str(target.get("display_name") or _display_name(target) or "目标 SKU")


def _format_dashboard_market_price(value: Any) -> str:
    return _format_money(value) or "待复核"


def _format_dashboard_market_sales(value: Any) -> str:
    formatted = _format_unit_count(value)
    return f"{formatted}台" if formatted else "待复核"


def _feishu_competitor_ranking_table(competitors: list[dict[str, Any]]) -> dict[str, Any]:
    return _feishu_table(
        element_id="rank_table",
        columns=[
            _feishu_text_column("rank", "#"),
            _feishu_text_column("name", "竞品"),
            _feishu_text_column("position", "定位"),
            _feishu_text_column("strength", "重合"),
        ],
        rows=[
            {
                "rank": str(item.get("rank") or ""),
                "name": _dashboard_competitor_alias(item),
                "position": f"{_dashboard_role_short(item)} / {_dashboard_pressure_short(item)}",
                "strength": f"{_dashboard_strength_bar(str(item.get('strength_cn') or ''))} {_dashboard_strength_short(item)}",
            }
            for item in competitors[:3]
        ],
    )


def _dashboard_competitor_ranking_lines(competitors: list[dict[str, Any]]) -> list[str]:
    lines = ["| 排名 | 竞品 | 角色 | 压力 | 重合 |", "| ---: | --- | --- | --- | --- |"]
    for item in competitors[:3]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(item.get("rank")),
                    _markdown_cell(_dashboard_competitor_alias(item)),
                    _markdown_cell(_dashboard_role_short(item)),
                    _markdown_cell(_dashboard_pressure_short(item)),
                    _markdown_cell(f"{_dashboard_strength_bar(str(item.get('strength_cn') or ''))} {_dashboard_strength_short(item)}"),
                ]
            )
            + " |"
        )
    return lines


def _dashboard_score_dimension_lines(competitors: list[dict[str, Any]]) -> list[str]:
    headers = [_dashboard_competitor_alias(item) for item in competitors[:3]]
    lines = [
        "| 维度 | " + " | ".join(_markdown_cell(header) for header in headers) + " |",
        "| --- | " + " | ".join("---:" for _ in headers) + " |",
    ]
    dimension_names = [row["dimension_cn"] for row in _dashboard_score_dimension_rows(competitors[0])] if competitors else []
    for dimension_name in dimension_names:
        cells = []
        for item in competitors[:3]:
            row = next(
                (entry for entry in _dashboard_score_dimension_rows(item) if entry["dimension_cn"] == dimension_name),
                {"score": 0},
            )
            cells.append(f"{row['score']}分")
        lines.append("| " + " | ".join([_markdown_cell(dimension_name), *[_markdown_cell(cell) for cell in cells]]) + " |")
    return lines


def _feishu_market_chart_table(competitors: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [_dashboard_market_metric(item) for item in competitors[:3]]
    max_sales = max((metric["sales"] or 0 for metric in metrics), default=0)
    return _feishu_table(
        element_id="market_chart",
        columns=[
            _feishu_text_column("name", "竞品"),
            _feishu_text_column("sales", "周均"),
            _feishu_text_column("weeks", "周期"),
            _feishu_text_column("bar", "量级"),
        ],
        rows=[
            {
                "name": metric["name"],
                "sales": f"{_format_market_number(metric['sales'])}台",
                "weeks": f"{_format_market_number(metric['weeks'])}周" if metric["weeks"] is not None else "待复核",
                "bar": _dashboard_market_bar(metric["sales"], max_sales),
            }
            for metric in metrics
        ],
    )


def _dashboard_market_chart_lines(competitors: list[dict[str, Any]]) -> list[str]:
    metrics = [_dashboard_market_metric(item) for item in competitors[:3]]
    max_sales = max((metric["sales"] or 0 for metric in metrics), default=0)
    lines = ["| 竞品 | 周均销量 | 重叠周 | 量级 |", "| --- | ---: | ---: | --- |"]
    for metric in metrics:
        sales = metric["sales"]
        weeks = metric["weeks"]
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_cell(metric["name"]),
                    _markdown_cell(f"{_format_market_number(sales)}台"),
                    _markdown_cell(f"{_format_market_number(weeks)}周" if weeks is not None else "待复核"),
                    _markdown_cell(_dashboard_market_bar(sales, max_sales)),
                ]
            )
            + " |"
        )
    return lines


def _compact_market_validation(value: str) -> str:
    match = re.search(r"重叠在售周(?P<weeks>[\d.]+)周.*?周均销量约(?P<sales>[\d.]+)台", value)
    if match:
        return f"重叠{match.group('weeks')}周，周均{match.group('sales')}台"
    return value.strip()


def _dashboard_competitor_alias(competitor: dict[str, Any]) -> str:
    return str(competitor.get("name") or competitor.get("model_name") or "竞品")


def _dashboard_role_short(competitor: dict[str, Any]) -> str:
    role = str(competitor.get("role_cn") or "重点竞品")
    return role.replace("竞品", "")


def _dashboard_pressure_short(competitor: dict[str, Any]) -> str:
    pressure = str(competitor.get("pressure_cn") or "替代压力待复核")
    return pressure.replace("压力", "").replace("配置/场景标杆", "配置标杆")


def _dashboard_strength_short(competitor: dict[str, Any]) -> str:
    return _dashboard_strength_short_value(str(competitor.get("strength_cn") or "强度待复核"))


def _dashboard_strength_short_value(strength: str) -> str:
    return strength.replace("重合", "")


def _dashboard_strength_bar(strength: str) -> str:
    if "强" in strength and "中高" not in strength:
        return "■■■"
    if "中高" in strength:
        return "■■□"
    if "中" in strength:
        return "■□□"
    if "弱" in strength:
        return "□□□"
    return "待复核"


def _dashboard_market_metric(competitor: dict[str, Any]) -> dict[str, Any]:
    value = _compact_market_validation(str(competitor.get("market_validation_cn") or ""))
    weeks_match = re.search(r"重叠(?:在售周)?(?P<weeks>[\d.]+)周", value)
    sales_match = re.search(r"(?:周均销量约|周均)(?P<sales>[\d.]+)台", value)
    return {
        "name": _dashboard_competitor_alias(competitor),
        "weeks": _to_float_or_none(weeks_match.group("weeks") if weeks_match else None),
        "sales": _to_float_or_none(sales_match.group("sales") if sales_match else None),
    }


def _to_float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _format_market_number(value: float | None) -> str:
    if value is None:
        return "待复核"
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _dashboard_market_bar(sales: float | None, max_sales: float) -> str:
    if not sales or max_sales <= 0:
        return "待复核"
    filled = max(1, min(8, round(sales / max_sales * 8)))
    return "■" * filled + "□" * (8 - filled)


def _feishu_table(*, element_id: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "tag": "table",
        "element_id": element_id,
        "page_size": max(1, min(5, len(rows) or 1)),
        "row_height": "auto",
        "header_style": {
            "text_align": "left",
            "text_size": "normal",
            "background_style": "none",
            "text_color": "grey",
            "bold": True,
            "lines": 1,
        },
        "columns": columns,
        "rows": rows,
    }


def _feishu_text_column(name: str, display_name: str) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": display_name,
        "data_type": "text",
        "horizontal_align": "left",
        "vertical_align": "top",
        "width": "auto",
    }


def _feishu_report_action(dashboard_payload: dict[str, Any]) -> dict[str, Any] | None:
    links = dashboard_payload.get("report_evidence_links") or []
    report_url = ""
    for item in links:
        if isinstance(item, dict) and str(item.get("url") or "").startswith("http"):
            report_url = str(item["url"])
            break
    if not report_url:
        return None
    return {
        "tag": "button",
        "element_id": "view_report",
        "type": "primary",
        "size": "medium",
        "width": "fill",
        "text": {"tag": "plain_text", "content": "查看完整报告"},
        "behaviors": [
            {
                "type": "open_url",
                "default_url": report_url,
                "pc_url": report_url,
                "ios_url": report_url,
                "android_url": report_url,
            }
        ],
    }


def _trim_feishu_card(card: dict[str, Any]) -> dict[str, Any]:
    max_bytes = 30_000
    if len(json.dumps(card, ensure_ascii=False).encode("utf-8")) <= max_bytes:
        return card
    elements = list(((card.get("body") or {}).get("elements") or [])[:4])
    compact = {**card, "body": {"elements": elements}}
    if len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) <= max_bytes:
        return compact
    summary = ((card.get("config") or {}).get("summary") or {}).get("content") or "重点竞品看板"
    return {
        "schema": "2.0",
        "config": {"summary": {"content": summary}},
        "header": card.get("header") or {},
        "body": {"elements": [{"tag": "markdown", "content": "卡片内容过长，已降级为摘要。请查看短回答或完整报告。"}]},
    }


def _sort_key(item: dict[str, Any]) -> tuple[float, float, float, float]:
    overlap = item.get("weighted_overlap") or {}
    semantic_balance = min(
        float(overlap.get("battlefield") or 0),
        float(overlap.get("user_task") or 0),
        float(overlap.get("target_group") or 0),
    )
    gap = abs(float(_decimal((item.get("candidate") or {}).get("price_gap_pct_to_target")) or Decimal("1")))
    return (float(item["business_score"]), semantic_balance, float(item["purchase_pool"]["score"]), -gap)


def _exclusion_reason(
    purchase_pool: dict[str, Any],
    battlefield: dict[str, Any],
    task: dict[str, Any],
    group: dict[str, Any],
    value_anchor: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    gap = _decimal(candidate.get("price_gap_pct_to_target")) or Decimal("0")
    if purchase_pool["score"] < Decimal("0.55"):
        return "购买池偏离，难以进入同一批用户最终候选清单。"
    if max(battlefield["score"], task["score"], group["score"]) < Decimal("0.30"):
        return "主辅价值战场、用户任务或目标客群重合不足。"
    if value_anchor["score"] < Decimal("0.25"):
        return "关键价值锚点替代性不足，更多是局部参数相似。"
    if abs(gap) <= Decimal("0.03"):
        return "价格贴身但成交理由重合度不足，适合做价格参考而非首选竞品。"
    return "综合替代压力低于前三候选。"


def _publish_report(*, title: str, markdown: str, with_report: str) -> ReportPublishResult:
    if with_report == "none":
        return ReportPublishResult(status="disabled", message_cn="未请求生成外部报告。")
    if with_report == "markdown":
        return ReportPublishResult(status="markdown_ready", message_cn="已生成 Markdown 报告。")
    if with_report != "feishu-doc":
        return ReportPublishResult(status="disabled", message_cn="不支持的报告生成模式。")
    if os.environ.get("CATFORGE_ANALYST_REPORT_PUBLISHER") != "feishu_cli":
        return ReportPublishResult(status="disabled", message_cn="飞书报告发布器未启用。")
    cli_bin = os.environ.get("CATFORGE_FEISHU_CLI_BIN") or shutil.which("lark-cli")
    if not cli_bin:
        return ReportPublishResult(status="failed", message_cn="当前环境未安装飞书 CLI。")
    try:
        command = [
            cli_bin,
            "docs",
            "+create",
            "--api-version",
            "v2",
            "--as",
            os.environ.get("CATFORGE_FEISHU_AS", "user"),
            "--doc-format",
            "markdown",
            "--content",
            "-",
            "--format",
            "json",
        ]
        env = os.environ.copy()
        cli_dir = os.path.dirname(cli_bin)
        if cli_dir:
            env["PATH"] = f"{cli_dir}:{env.get('PATH', '')}"
        completed = subprocess.run(command, input=markdown, check=False, capture_output=True, text=True, timeout=60, env=env)
        if completed.returncode != 0:
            return ReportPublishResult(status="failed", message_cn=_feishu_failure_message(completed.stderr or completed.stdout))
        url = _extract_url(completed.stdout)
        if not url:
            return ReportPublishResult(status="failed", message_cn="飞书文档已请求创建，但未返回可用链接。")
        permission_result = _publish_feishu_public_permission(cli_bin=cli_bin, url=url, env=env)
        if permission_result is not None and not permission_result["ok"]:
            return ReportPublishResult(
                status="created_permission_failed",
                url=url,
                message_cn=f"已生成《{title}》，但链接公开权限设置失败：{permission_result['message_cn']}",
            )
        return ReportPublishResult(status="created", url=url, message_cn=f"已生成《{title}》。")
    except Exception:
        return ReportPublishResult(status="failed", message_cn="飞书文档创建失败。")


def publish_feishu_card_reply(
    *,
    card: dict[str, Any] | None,
    reply_message_id: str | None = None,
    reply_in_thread: bool = False,
    idempotency_key: str | None = None,
) -> FeishuCardPublishResult:
    if not reply_message_id or not reply_message_id.strip():
        return FeishuCardPublishResult(status="disabled", message_cn="未提供飞书消息 ID，未发送卡片。")
    if not card:
        return FeishuCardPublishResult(status="failed", message_cn="飞书卡片发送失败：没有可发送的卡片内容。")
    cli_bin = os.environ.get("CATFORGE_FEISHU_CLI_BIN") or shutil.which("lark-cli")
    if not cli_bin:
        return FeishuCardPublishResult(status="failed", message_cn="飞书卡片发送失败：当前环境未安装飞书 CLI。")
    content = json.dumps(card, ensure_ascii=False, separators=(",", ":"))
    command = [
        cli_bin,
        "im",
        "+messages-reply",
        "--message-id",
        reply_message_id.strip(),
        "--msg-type",
        "interactive",
        "--content",
        content,
        "--as",
        os.environ.get("CATFORGE_FEISHU_IM_AS") or os.environ.get("CATFORGE_FEISHU_AS", "bot"),
        "--format",
        "json",
    ]
    if reply_in_thread:
        command.append("--reply-in-thread")
    normalized_idempotency_key = _feishu_idempotency_key(idempotency_key)
    if normalized_idempotency_key:
        command.extend(["--idempotency-key", normalized_idempotency_key])
    env = os.environ.copy()
    cli_dir = os.path.dirname(cli_bin)
    if cli_dir:
        env["PATH"] = f"{cli_dir}:{env.get('PATH', '')}"
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30, env=env)
    except FileNotFoundError:
        return FeishuCardPublishResult(status="failed", message_cn="飞书卡片发送失败：当前环境找不到飞书 CLI。")
    except subprocess.TimeoutExpired:
        return FeishuCardPublishResult(status="failed", message_cn="飞书卡片发送失败：飞书消息接口超时。")
    except Exception:
        return FeishuCardPublishResult(status="failed", message_cn="飞书卡片发送失败。")
    if completed.returncode != 0:
        return FeishuCardPublishResult(status="failed", message_cn=_feishu_im_failure_message(completed.stderr or completed.stdout))
    message_id, chat_id = _extract_feishu_message_result(completed.stdout)
    return FeishuCardPublishResult(
        status="sent",
        message_cn="已发送飞书竞品看板卡片。",
        message_id=message_id,
        chat_id=chat_id,
    )


def _publish_feishu_public_permission(*, cli_bin: str, url: str, env: dict[str, str]) -> dict[str, Any] | None:
    link_share_entity = os.environ.get("CATFORGE_FEISHU_LINK_SHARE_ENTITY", "").strip()
    if not link_share_entity:
        return None
    token_info = _extract_feishu_doc_token(url)
    if token_info is None:
        return {"ok": False, "message_cn": "未能从飞书链接中解析文档 token。"}
    token, doc_type = token_info
    data = {
        "external_access": _env_bool("CATFORGE_FEISHU_EXTERNAL_ACCESS", default=True),
        "link_share_entity": link_share_entity,
        "security_entity": os.environ.get("CATFORGE_FEISHU_SECURITY_ENTITY", "anyone_can_view"),
        "comment_entity": os.environ.get("CATFORGE_FEISHU_COMMENT_ENTITY", "anyone_can_view"),
        "share_entity": os.environ.get("CATFORGE_FEISHU_SHARE_ENTITY", "only_full_access"),
        "invite_external": _env_bool("CATFORGE_FEISHU_INVITE_EXTERNAL", default=True),
    }
    command = [
        cli_bin,
        "drive",
        "permission.public",
        "patch",
        "--as",
        os.environ.get("CATFORGE_FEISHU_AS", "user"),
        "--params",
        json.dumps({"token": token, "type": doc_type}, ensure_ascii=False),
        "--data",
        json.dumps(data, ensure_ascii=False),
        "--format",
        "json",
        "--yes",
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60, env=env)
    if completed.returncode != 0:
        return {"ok": False, "message_cn": _feishu_public_permission_failure_message(completed.stderr or completed.stdout)}
    return {"ok": True, "message_cn": "已设置为获得链接的人可阅读。"}


def _extract_feishu_doc_token(url: str) -> tuple[str, str] | None:
    match = re.search(r"/(docx|doc|sheets|bitable|slides)/([^/?#]+)", url)
    if not match:
        return None
    doc_type = {"sheets": "sheet"}.get(match.group(1), match.group(1))
    return match.group(2), doc_type


def _extract_feishu_message_result(output: str) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(output)
    except Exception:
        return None, None
    message_id = _first_string_value(payload, ("message_id", "messageId", "id"))
    chat_id = _first_string_value(payload, ("chat_id", "chatId"))
    return message_id, chat_id


def _first_string_value(payload: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for value in payload.values():
            found = _first_string_value(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _first_string_value(item, keys)
            if found:
                return found
    return None


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _extract_url(output: str) -> str | None:
    try:
        payload = json.loads(output)
    except Exception:
        payload = {}
    candidates = [
        payload.get("url") if isinstance(payload, dict) else None,
        payload.get("document_url") if isinstance(payload, dict) else None,
        payload.get("doc_url") if isinstance(payload, dict) else None,
    ]
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        candidates.extend([data.get("url"), data.get("document_url"), data.get("doc_url")])
    for value in candidates:
        if isinstance(value, str) and value.startswith("http"):
            return value
    for value in _walk_json_values(payload):
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None


def _walk_json_values(payload: Any) -> list[Any]:
    values: list[Any] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.append(value)
            values.extend(_walk_json_values(value))
    elif isinstance(payload, list):
        for value in payload:
            values.append(value)
            values.extend(_walk_json_values(value))
    return values


def _feishu_failure_message(output: str) -> str:
    normalized = output.lower()
    if "not found" in normalized or "no such file" in normalized:
        return "飞书文档创建失败：当前环境找不到飞书 CLI。"
    if "not_configured" in normalized or "not configured" in normalized:
        return "飞书文档创建失败：API 容器未加载飞书 CLI 配置或密钥目录。请检查 CATFORGE_FEISHU_CONFIG_DIR 和 CATFORGE_FEISHU_DATA_DIR 挂载。"
    if "scope" in normalized or "permission" in normalized or "forbidden" in normalized:
        scopes = _extract_missing_scopes(output)
        console_url = _extract_console_url(output)
        scope_text = f"（缺少 {scopes}）" if scopes else ""
        url_text = f" 请在飞书开发者后台开通后重试：{console_url}" if console_url else ""
        return f"飞书文档创建失败：飞书应用或用户缺少文档创建权限{scope_text}。{url_text}".strip()
    if "auth" in normalized or "login" in normalized or "user identity" in normalized:
        return "飞书文档创建失败：飞书用户身份未授权或授权已失效。"
    return "飞书文档创建失败：请检查飞书 CLI 配置、授权和网络连通性。"


def _feishu_im_failure_message(output: str) -> str:
    normalized = output.lower()
    if "not found" in normalized or "no such file" in normalized:
        return "飞书卡片发送失败：当前环境找不到飞书 CLI。"
    if "not_configured" in normalized or "not configured" in normalized:
        return "飞书卡片发送失败：API 容器未加载飞书 CLI 配置或密钥目录。请检查 CATFORGE_FEISHU_CONFIG_DIR 和 CATFORGE_FEISHU_DATA_DIR 挂载。"
    if "scope" in normalized or "permission" in normalized or "forbidden" in normalized:
        scopes = _extract_missing_scopes(output)
        console_url = _extract_console_url(output)
        scope_text = f"（缺少 {scopes}）" if scopes else ""
        url_text = f" 请在飞书开发者后台开通后重试：{console_url}" if console_url else ""
        return f"飞书卡片发送失败：飞书应用或用户缺少消息发送权限{scope_text}。{url_text}".strip()
    if "invalid message" in normalized or "message_id" in normalized or "message id" in normalized:
        return "飞书卡片发送失败：当前消息 ID 不可回复或已失效。"
    if "field validation failed" in normalized or "field_violations" in normalized:
        return "飞书卡片发送失败：飞书消息字段校验未通过。"
    if "auth" in normalized or "login" in normalized or "user identity" in normalized:
        return "飞书卡片发送失败：飞书用户身份未授权或授权已失效。"
    return "飞书卡片发送失败：请检查飞书 CLI 配置、机器人是否在会话中以及消息发送权限。"


def _feishu_idempotency_key(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    key = value.strip()
    if len(key) <= 50:
        return key
    return f"cf-card-{sha256(key.encode('utf-8')).hexdigest()[:32]}"


def _feishu_public_permission_failure_message(output: str) -> str:
    code = _extract_error_code(output)
    if code == "91009":
        return "组织对外分享被租户安全策略管控，需要管理员打开组织级对外分享。"
    if code == "91010":
        return "当前文档对外分享未打开，需要先打开对外分享能力。"
    if code == "91011":
        return "文档密级拦截了对外分享，需要在文档内申请密级豁免或降级。"
    if code == "91012":
        return "文档密级拦截了权限设置，需要在文档内申请密级豁免或降级。"
    if "scope" in output.lower() or "permission" in output.lower() or "forbidden" in output.lower():
        return "飞书应用缺少文档权限设置 scope，需开通 docs:permission.setting:write_only 等权限后重试。"
    return "请检查飞书应用权限、租户对外分享策略和文档密级。"


def _extract_error_code(output: str) -> str:
    try:
        payload = json.loads(output)
    except Exception:
        match = re.search(r"\b(91009|91010|91011|91012)\b", output)
        return match.group(1) if match else ""
    for value in _walk_json_values(payload):
        if str(value) in {"91009", "91010", "91011", "91012"}:
            return str(value)
    return ""


def _extract_missing_scopes(output: str) -> str:
    try:
        payload = json.loads(output)
    except Exception:
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    scopes = error.get("missing_scopes") if isinstance(error, dict) else None
    if not isinstance(scopes, list):
        return ""
    values = [str(scope) for scope in scopes if scope]
    return "、".join(values[:8])


def _extract_console_url(output: str) -> str:
    try:
        payload = json.loads(output)
    except Exception:
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    url = error.get("console_url") if isinstance(error, dict) else None
    return url if isinstance(url, str) and url.startswith("http") else ""


def _role_weight(roles: list[Any]) -> Decimal:
    weights = [ROLE_WEIGHTS.get(str(role), Decimal("0")) for role in roles]
    positives = [weight for weight in weights if weight > 0]
    if positives:
        return max(positives)
    negatives = [weight for weight in weights if weight < 0]
    return min(negatives) if negatives else Decimal("0")


def _is_primary(items: list[dict[str, Any]], code: str) -> bool:
    for item in items:
        if str(item.get("code")) == code and "primary" in {str(role) for role in item.get("roles") or []}:
            return True
    return False


def _dimension_labels(overlap: dict[str, Any], mapping: dict[str, str]) -> list[str]:
    return _unique_strings([mapping.get(str(code), str(code)) for code in overlap.get("matched_codes") or []])


def _anchors_from_codes(*groups: list[Any]) -> list[str]:
    anchors: list[str] = []
    for group in groups:
        for code in group:
            anchor = _anchor_for_code(str(code))
            if anchor and anchor not in anchors:
                anchors.append(anchor)
    return anchors


def _anchor_for_code(code: str) -> str | None:
    normalized = code.lower()
    if any(token in normalized for token in ("screen_size", "large_screen", "size", "inch")):
        return "尺寸升级"
    if any(token in normalized for token in ("miniled", "oled", "qled", "hdr", "brightness", "dimming", "color", "picture", "display", "chip")):
        return "高端画质"
    if any(token in normalized for token in ("refresh", "gaming", "game", "hdmi", "vrr", "latency", "motion")):
        return "游戏流畅"
    if any(token in normalized for token in ("dolby", "audio", "sound", "theater", "cinema")):
        return "影院沉浸"
    if any(token in normalized for token in ("ai", "voice", "cast", "iot", "smart", "wifi", "connect")):
        return "智能互联"
    if any(token in normalized for token in ("eye", "blue", "flicker", "care")):
        return "护眼长看"
    if any(token in normalized for token in ("wall", "thin", "fullscreen", "design", "decor", "flush")):
        return "家装融合"
    if any(token in normalized for token in ("price", "value", "money")):
        return "预算价值"
    return None


def _adjacent_price_band(target_band: str, candidate_band: str) -> bool:
    if target_band not in PRICE_BAND_ORDER or candidate_band not in PRICE_BAND_ORDER:
        return False
    return abs(PRICE_BAND_ORDER[target_band] - PRICE_BAND_ORDER[candidate_band]) <= 1


def _display_name(payload: dict[str, Any]) -> str:
    brand = str(payload.get("brand_name") or "").strip()
    model = str(payload.get("model_name") or payload.get("sku_code") or "").strip()
    if brand and model:
        return f"{brand} {model}"
    return brand or model or "该 SKU"


def _report_suffix(report_url: str | None) -> str:
    return f"详细分析报告见飞书链接：{report_url}" if report_url else "详细分析报告暂未生成。"


def _compress_answer(text: str, *, target: dict[str, Any], top_competitors: list[dict[str, Any]], report_url: str | None, max_chat_chars: int) -> str:
    forbidden = ("M00", "M03B", "BF_", "TG_", "TASK_", "catforge", "CLI", "JSON", "stderr")
    if len(text) <= max_chat_chars and not any(token in text for token in forbidden):
        return text
    target_name = _display_name(target)
    parts = [f"{target_name} 的重点竞品建议看{len(top_competitors)}款：{_join_cn([_display_name(item.get('candidate') or {}) for item in top_competitors])}。"]
    for item in top_competitors:
        parts.append(f"{_display_name(item.get('candidate') or {})}是{item['role_cn']}，主要压力来自{item['replacement_pressure']['type_cn']}。")
    parts.append(_report_suffix(report_url))
    compact = "".join(parts)
    if len(compact) <= max_chat_chars:
        return compact
    return compact[: max(0, max_chat_chars - 1)] + "。"


def _target_evidence_state(target_fact_brief: dict[str, Any]) -> dict[str, bool]:
    sections = target_fact_brief.get("sections") if isinstance(target_fact_brief, dict) else {}
    if not isinstance(sections, dict):
        sections = {}
    comment = sections.get("comment_fact") or {}
    task = sections.get("user_task") or {}
    group = sections.get("target_group") or {}
    battlefield = sections.get("value_battlefield") or {}
    allocation = sections.get("sales_allocation") or {}
    positions = sections.get("semantic_dimension_positions") or {}
    comment_summary = comment.get("summary") or {}
    has_comment = bool(
        comment.get("supported_claim_codes")
        or comment.get("contradicted_claim_codes")
        or comment_summary.get("product_fact_sentence_count")
        or comment_summary.get("matched_sentence_count")
    )
    has_semantics = bool(
        task.get("primary_user_task_code")
        or group.get("primary_target_group_code")
        or battlefield.get("primary_battlefield_code")
    )
    has_graph = bool(allocation or positions)
    return {
        "has_comment": has_comment,
        "has_semantics": has_semantics,
        "has_graph": has_graph,
        "semantic_verified": bool(has_comment and has_semantics and has_graph),
    }


def _unique_strings(*groups: list[Any]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for value in group:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
    return result


def _join_cn(items: list[Any]) -> str:
    values = [str(item) for item in items if item]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "、".join(values[:-1]) + "和" + values[-1]


def _price_gap_phrase(value: Any) -> str:
    gap = _decimal(value)
    if gap is None:
        return "价格关系未知"
    pct = f"{abs(gap * Decimal('100')).quantize(Decimal('1'))}%"
    if abs(gap) <= Decimal("0.03"):
        return "几乎同价"
    if gap < 0:
        return f"比目标低约{pct}"
    return f"比目标高约{pct}"


def _format_money(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{number.quantize(Decimal('1')):,}元"


def _format_number(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    if number == number.to_integral_value():
        return f"{number.quantize(Decimal('1')):,}"
    return f"{number.quantize(Decimal('0.1')):,}"


def _format_unit_count(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    return f"{number.quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"


def _pct(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return "-"
    return f"{(number * Decimal('100')).quantize(Decimal('1'))}%"


def _pct_or_unknown(value: Any) -> str:
    text = _pct(value)
    return "未知" if text == "-" else text


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _float(value: Any) -> float | None:
    number = _decimal(value)
    return float(number) if number is not None else None
