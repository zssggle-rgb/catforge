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
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal


ReportMode = Literal["none", "markdown", "feishu-doc"]

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
}

PRICE_BAND_NAMES = {
    "low": "低价带",
    "mid_low": "中低价带",
    "mid": "中价带",
    "mid_high": "中高价带",
    "high": "高价带",
}

INDEX_CN = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一"]


@dataclass(frozen=True)
class ReportPublishResult:
    status: str
    url: str | None = None
    message_cn: str | None = None


def build_competitor_answer(
    *,
    target: dict[str, Any],
    target_fact_brief: dict[str, Any],
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
    top_competitors = _select_top_competitors(enriched, top_n=max(top_n, 0))
    title = report_title or f"{_display_name(target)} 重点竞品分析报告"
    markdown = render_competitor_report(
        title=title,
        target=target,
        target_fact_brief=target_fact_brief,
        top_competitors=top_competitors,
        all_competitors=enriched,
    )
    publish_result = _publish_report(title=title, markdown=markdown, with_report=with_report)
    short_answer = render_short_answer(
        target=target,
        target_fact_brief=target_fact_brief,
        top_competitors=top_competitors,
        report_url=publish_result.url,
        max_chat_chars=max_chat_chars,
    )
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
        "top_competitors": top_competitors,
        "candidate_buckets": buckets,
        "selection_policy_cn": [
            "先限定同一购买池，再比较主辅价值战场、用户任务、目标客群的加权重合。",
            "关键价值锚点用于判断候选是否会改变目标 SKU 的成交理由。",
            "销量只用于验证候选具备真实市场分流能力，不作为首选竞品的主排序依据。",
        ],
        "display_policy": {
            "send_short_answer_as_is": True,
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


def render_competitor_report(
    *,
    title: str,
    target: dict[str, Any],
    target_fact_brief: dict[str, Any],
    top_competitors: list[dict[str, Any]],
    all_competitors: list[dict[str, Any]],
) -> str:
    target_name = _display_name(target)
    target_sections = _fact_sections(target_fact_brief)
    lines = [
        f"# {title}",
        "",
        "## 一、分析结论",
        "",
    ]
    if top_competitors:
        lines.extend(_analysis_conclusion_lines(target_name, target_sections, top_competitors, all_competitors))
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
    lines.extend(_scoring_method_lines())
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
    lines.extend(["", '<a id="profile-target"></a>', f"## 四、{target_name} 产品画像", ""])
    lines.extend(_product_profile_lines("4", target_name, target, target_sections, competitor_item=None))
    for index, item in enumerate(top_competitors[:3], start=1):
        candidate = item.get("candidate") or {}
        candidate_name = _display_name(candidate)
        candidate_sections = _fact_sections(item.get("candidate_fact_brief") or {})
        lines.extend(
            [
                "",
                f'<a id="profile-competitor-{index}"></a>',
                f"## {INDEX_CN[index + 3]}、{candidate_name} 产品画像",
                "",
            ]
        )
        lines.extend(_product_profile_lines(str(index + 4), candidate_name, candidate, candidate_sections, competitor_item=item))
    return "\n".join(lines)


def _analysis_conclusion_lines(
    target_name: str,
    target_sections: dict[str, Any],
    top_competitors: list[dict[str, Any]],
    all_competitors: list[dict[str, Any]],
) -> list[str]:
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
                f"{first_name} 排第一，核心原因不是单项参数最接近，而是它在 {target_name} 的主要竞争结构里形成了最完整的替代关系。{first['purchase_pool']['reason_cn']}，用户会在同一次升级型电视购买中把它们放进候选清单。",
                "",
                f"从价值战场看，{target_name} 的竞争重心是{target_battlefields or '当前主战场'}，{first_name} 的竞争重心是{first_battlefields or '当前主战场'}。{first_name} 没有偏离 {target_name} 的核心战场，而是切入目标 SKU 的主竞争范围。",
                "",
                f"从用户任务看，{target_name} 主要承接{target_tasks or '当前主要用户任务'}；{first_name} 主要承接{first_tasks or '当前主要用户任务'}。两者不完全相同，但高度交叉，交叉点正好是该尺寸价格段电视最核心的购买场景。",
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
        f"{_display_name(item.get('candidate') or {})} 周均约{_format_number(item['market_validation'].get('avg_weekly_sales_volume')) or '未知'}台"
        for item in top_competitors[:3]
    ]
    lines.append(
        f"市场验证方面，{_join_cn(market_parts)}，说明重点竞品具备真实分流能力。销量只用于验证竞品有效性，不用于决定竞品成立；排序核心仍然是购买池、价值战场、用户任务、目标客群和价值锚点对 {target_name} 成交理由的替代强度。"
    )
    return lines


def _scoring_method_lines() -> list[str]:
    return [
        "| 评分维度 | 权重 | 判断问题 |",
        "| --- | ---: | --- |",
        "| 购买池 | 20 | 是否同尺寸、同价位或相邻价位，是否会进入同一次购买决策 |",
        "| 价值战场 | 15 | 主辅价值战场是否重合，是否争夺同一类付费场景 |",
        "| 用户任务 | 20 | 用户买电视要完成的使用任务是否高度交叉 |",
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


def _product_profile_lines(
    section_no: str,
    sku_name: str,
    sku: dict[str, Any],
    sections: dict[str, Any],
    *,
    competitor_item: dict[str, Any] | None,
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
        ("尺寸", f"{_format_number(size) or '未知'} 寸"),
        ("均价", _format_money(price) or "未知"),
        ("周均销量", f"{_format_number(weekly_sales) or '未知'} 台"),
        ("尺寸价格池", f"{size_tier or '尺寸段未知'} × {price_band}"),
        (
            "所在池空间",
            f"{_format_number(pool.get('total_sales_volume')) or '未知'}台，周均{_format_number(pool.get('total_avg_weekly_sales_volume')) or '未知'}台，SKU数{_format_number(pool.get('sku_count')) or '未知'}",
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
            f"市场解读：{sku_name} 当前处在{size_tier or '目标尺寸段'}的{price_band}，周均销量约{_format_number(weekly_sales) or '未知'}台；所在尺寸价格池总销量约{_format_number(pool.get('total_sales_volume')) or '未知'}台，本品占池内销量{_pct_or_unknown(pool.get('target_sales_volume_share'))}。",
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
            f"| {label} | {relation} | {_semantic_market_space_text(position)} | {_semantic_sku_performance_text(position)} | {reason} |"
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
        return "图谱空间待生成"
    parts = [
        f"空间{_format_number(market_space.get('estimated_sales_volume')) or '未知'}台",
        f"周均{_format_number(market_space.get('estimated_avg_weekly_sales_volume')) or '未知'}台",
        f"覆盖{_format_number(market_space.get('allocated_sku_count')) or '未知'}个SKU",
    ]
    share = _pct_or_unknown(market_space.get("sales_volume_share"))
    if share != "未知":
        parts.append(f"市场占比{share}")
    return "；".join(parts)


def _semantic_sku_performance_text(position: dict[str, Any]) -> str:
    allocation = position.get("sku_allocation") or {}
    contribution = position.get("sku_contribution") or {}
    if not allocation:
        return "未进入销量分配"
    share = contribution.get("sku_share_in_dimension_volume")
    if share is None:
        market_space = position.get("market_space") or {}
        allocated = _decimal(allocation.get("allocated_sales_volume"))
        total = _decimal(market_space.get("estimated_sales_volume"))
        share = allocated / total if allocated is not None and total else None
    parts = [
        f"分配{_format_number(allocation.get('allocated_sales_volume')) or '未知'}台",
        f"周均{_format_number(allocation.get('allocated_avg_weekly_sales_volume')) or '未知'}台",
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
        f"- 尺寸价格：{_format_number(size) or '未知'}英寸，{SIZE_TIER_NAMES.get(str(size_tier), '尺寸段未知')}，{PRICE_BAND_NAMES.get(str(price_band), '价格带未知')}，线上均价约{_format_money(price) or '未知'}。",
        f"- 市场表现：周均销量约{_format_number(weekly_sales) or '未知'}台；主渠道为{_market_label(metrics.get('main_channel_type')) or '未知'}，主平台为{_market_label(metrics.get('main_platform')) or '未知'}。",
    ]
    price_percentile = _percentile_phrase(position.get("price_percentile_in_size"))
    volume_percentile = _percentile_phrase(position.get("volume_percentile_in_size"))
    if price_percentile or volume_percentile:
        lines.append(f"- 同尺寸段位置：价格分位{price_percentile or '未知'}，销量分位{volume_percentile or '未知'}，同池 SKU 数{_format_number(position.get('same_pool_sku_count')) or '未知'}。")
    if competitor_item:
        candidate = competitor_item.get("candidate") or {}
        lines.append(f"- 相对本品：{_price_gap_phrase(candidate.get('price_gap_pct_to_target'))}；{competitor_item['market_validation']['summary_cn']}。")
    return lines


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
        f"- 优势：{_display_name(target)} 已经站在{SIZE_TIER_NAMES.get(str(position.get('size_tier') or target.get('size_tier')), '目标尺寸段')}的{PRICE_BAND_NAMES.get(str(position.get('price_band_in_size_tier') or target.get('price_band_in_size_tier')), '目标价格带')}，周均销量约{_format_number(metrics.get('avg_weekly_sales_volume') or target.get('avg_weekly_sales_volume')) or '未知'}台，具备真实成交基础。",
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
    role = _base_role(purchase_pool, replacement, candidate)
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
        summary = f"重叠在售周{overlap_week_count}周，候选周均销量约{_format_number(avg_weekly) or '未知'}台"
    else:
        summary = f"候选周均销量约{_format_number(avg_weekly) or '未知'}台，重叠在售周验证不足"
    return {
        "level": level,
        "level_cn": level_cn,
        "overlap_week_count": overlap_week_count,
        "avg_weekly_sales_volume": _float(avg_weekly),
        "summary_cn": summary,
    }


def _base_role(purchase_pool: dict[str, Any], replacement: dict[str, Any], candidate: dict[str, Any]) -> str:
    gap = _decimal(candidate.get("price_gap_pct_to_target")) or Decimal("0")
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


def _select_top_competitors(enriched: list[dict[str, Any]], *, top_n: int) -> list[dict[str, Any]]:
    if top_n <= 0:
        return []
    selected: list[dict[str, Any]] = []
    direct = [item for item in enriched if item["role"] in {"primary_direct", "strong_direct"}]
    for item in direct[:2]:
        if item not in selected:
            selected.append(item)
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
    if "scope" in normalized or "permission" in normalized or "forbidden" in normalized:
        scopes = _extract_missing_scopes(output)
        console_url = _extract_console_url(output)
        scope_text = f"（缺少 {scopes}）" if scopes else ""
        url_text = f" 请在飞书开发者后台开通后重试：{console_url}" if console_url else ""
        return f"飞书文档创建失败：飞书应用或用户缺少文档创建权限{scope_text}。{url_text}".strip()
    if "auth" in normalized or "login" in normalized or "user identity" in normalized:
        return "飞书文档创建失败：飞书用户身份未授权或授权已失效。"
    return "飞书文档创建失败：请检查飞书 CLI 配置、授权和网络连通性。"


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
