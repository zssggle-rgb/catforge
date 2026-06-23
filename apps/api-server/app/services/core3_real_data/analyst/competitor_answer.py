"""Business-facing competitor answer generation.

This module turns the lower-level analyst atoms into a compact XiaoAo answer
and a detailed report payload. It is deterministic and does not call an LLM.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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
    "strong_direct": "强直接竞品",
    "price_adjacent": "价格贴身竞品",
    "downtrade_diversion": "下探分流竞品",
    "uptrade_alternative": "上探替代竞品",
    "scenario_alternative": "场景替代竞品",
    "excluded": "排除候选",
}


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
    top_competitors: list[dict[str, Any]],
    report_url: str | None,
    max_chat_chars: int,
) -> str:
    target_name = _display_name(target)
    if not top_competitors:
        suffix = _report_suffix(report_url)
        return f"{target_name} 当前没有足够证据形成稳定重点竞品。{suffix}"
    names = "、".join(_display_name(item.get("candidate") or {}) for item in top_competitors)
    lines = [f"{target_name} 的重点竞品建议看{len(top_competitors)}款：{names}。"]
    for index, item in enumerate(top_competitors, start=1):
        name = _display_name(item.get("candidate") or {})
        if index == 1:
            lines.append(
                f"{name}排第一，核心原因是{item['purchase_pool']['reason_cn']}，"
                f"并在{_join_cn(item['shared_business_context'][:3])}上覆盖目标 SKU 的核心成交理由，"
                f"形成{item['replacement_pressure']['type_cn']}。"
            )
        else:
            lines.append(
                f"{name}属于{item['role_cn']}，主要压力来自{item['replacement_pressure']['reason_cn']}。"
            )
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
    target_market = ((target_fact_brief.get("sections") or {}).get("market") or {}).get("market_metrics") or {}
    lines = [
        f"# {title}",
        "",
        "## 一、结论摘要",
        "",
    ]
    if top_competitors:
        lines.append(f"{target_name} 的重点竞品建议看：{_join_cn([_display_name(item.get('candidate') or {}) for item in top_competitors])}。")
    else:
        lines.append(f"{target_name} 当前没有足够证据形成稳定重点竞品。")
    lines.extend(
        [
            "",
            "## 二、为什么首选竞品成立",
            "",
        ]
    )
    if top_competitors:
        first = top_competitors[0]
        lines.append(
            f"{_display_name(first.get('candidate') or {})} 的首选竞品判断来自购买池、主辅语义重合、价值锚点替代压力和市场验证的共同结果。"
        )
        lines.append("")
        lines.append(f"- 购买池：{first['purchase_pool']['reason_cn']}。")
        lines.append(f"- 价值战场：{_join_cn(first['matched_dimensions']['battlefield'][:5]) or '当前无强重合'}。")
        lines.append(f"- 用户任务：{_join_cn(first['matched_dimensions']['user_task'][:5]) or '当前无强重合'}。")
        lines.append(f"- 目标客群：{_join_cn(first['matched_dimensions']['target_group'][:5]) or '当前无强重合'}。")
        lines.append(f"- 关键价值锚点：{_join_cn(first['value_anchor']['shared_anchors']) or '当前无明确共享锚点'}。")
        lines.append(f"- 市场验证：{first['market_validation']['summary_cn']}。")
    lines.extend(["", "## 三、Top 3 竞品卡", ""])
    for item in top_competitors:
        candidate = item.get("candidate") or {}
        lines.extend(
            [
                f"### {_display_name(candidate)}",
                "",
                f"- 业务角色：{item['role_cn']}",
                f"- 购买池：{item['purchase_pool']['reason_cn']}",
                f"- 价格关系：{_price_gap_phrase(candidate.get('price_gap_pct_to_target'))}",
                f"- 周均销量：{_format_number(candidate.get('avg_weekly_sales_volume')) or '未知'}",
                f"- 替代压力：{item['replacement_pressure']['reason_cn']}",
                f"- 关键价值锚点：{_join_cn(item['value_anchor']['shared_anchors']) or '当前无明确共享锚点'}",
                "",
            ]
        )
    lines.extend(["## 四、竞争关系矩阵", ""])
    lines.append("| 竞品 | 角色 | 购买池 | 战场重合 | 任务重合 | 客群重合 | 价值锚点 | 市场验证 |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | --- | --- |")
    for item in top_competitors:
        lines.append(
            "| "
            + " | ".join(
                [
                    _display_name(item.get("candidate") or {}),
                    item["role_cn"],
                    item["purchase_pool"]["level"],
                    _pct(item["weighted_overlap"]["battlefield"]),
                    _pct(item["weighted_overlap"]["user_task"]),
                    _pct(item["weighted_overlap"]["target_group"]),
                    _join_cn(item["value_anchor"]["shared_anchors"][:3]) or "-",
                    item["market_validation"]["level_cn"],
                ]
            )
            + " |"
        )
    lines.extend(["", "## 五、未入选候选说明", ""])
    excluded = [item for item in all_competitors if item not in top_competitors][:10]
    if not excluded:
        lines.append("当前候选较少，暂无更多未入选候选。")
    for item in excluded:
        lines.append(
            f"- {_display_name(item.get('candidate') or {})}：{item['exclusion_reason_cn']}"
        )
    lines.extend(
        [
            "",
            "## 六、对目标 SKU 的业务启示",
            "",
            "- 首选竞品用于判断目标 SKU 的溢价解释是否清晰。",
            "- 强直接竞品用于校准同预算层级下的配置和体验预期。",
            "- 下探或上探竞品用于判断预算迁移和替代压力。",
            "",
            "## 七、口径说明",
            "",
            f"- 目标 SKU 当前线上均价约 {_format_money(target.get('weighted_price') or target_market.get('price_wavg')) or '未知'}。",
            "- 竞品排序使用当前可观测线上样本，不覆盖线下渠道、广告投放、库存和促销资源。",
            "- 销量使用重叠在售周周均表现或市场画像周均表现做验证，累计销量不作为排序主依据。",
        ]
    )
    return "\n".join(lines)


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
    business_score = (
        purchase_pool["score"] * Decimal("0.20")
        + battlefield["score"] * Decimal("0.25")
        + task["score"] * Decimal("0.15")
        + group["score"] * Decimal("0.15")
        + value_anchor["score"] * Decimal("0.15")
        + replacement["score"] * Decimal("0.10")
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
    semantic_strength = battlefield["score"] * Decimal("0.45") + task["score"] * Decimal("0.25") + group["score"] * Decimal("0.30")
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
    summary = f"重叠在售周{overlap_week_count}周，候选周均销量约{_format_number(avg_weekly) or '未知'}台"
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


def _sort_key(item: dict[str, Any]) -> tuple[float, float, float]:
    market_bonus = {"strong": 0.03, "medium": 0.01, "weak": 0.0}.get(item["market_validation"]["level"], 0.0)
    gap = abs(float(_decimal((item.get("candidate") or {}).get("price_gap_pct_to_target")) or Decimal("1")))
    return (float(item["business_score"]) + market_bonus, item["purchase_pool"]["score"], -gap)


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
    return "综合替代压力低于 Top 3 候选。"


def _publish_report(*, title: str, markdown: str, with_report: str) -> ReportPublishResult:
    if with_report == "none":
        return ReportPublishResult(status="disabled", message_cn="未请求生成外部报告。")
    if with_report == "markdown":
        return ReportPublishResult(status="markdown_ready", message_cn="已生成 Markdown 报告。")
    if with_report != "feishu-doc":
        return ReportPublishResult(status="disabled", message_cn="不支持的报告生成模式。")
    if os.environ.get("CATFORGE_ANALYST_REPORT_PUBLISHER") != "feishu_cli":
        return ReportPublishResult(status="disabled", message_cn="飞书报告发布器未启用。")
    if not shutil.which("lark-cli"):
        return ReportPublishResult(status="failed", message_cn="当前环境未安装飞书 CLI。")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp:
        tmp.write(markdown)
        tmp_path = tmp.name
    try:
        command = [
            "lark-cli",
            "docs",
            "+create",
            "--api-version",
            "v2",
            "--as",
            os.environ.get("CATFORGE_FEISHU_AS", "user"),
            "--doc-format",
            "markdown",
            "--content",
            f"@{tmp_path}",
            "--format",
            "json",
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=60)
        if completed.returncode != 0:
            return ReportPublishResult(status="failed", message_cn="飞书文档创建失败。")
        url = _extract_url(completed.stdout)
        return ReportPublishResult(status="created", url=url, message_cn=f"已生成《{title}》。")
    except Exception:
        return ReportPublishResult(status="failed", message_cn="飞书文档创建失败。")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


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
    return None


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
    return _unique_strings([[mapping.get(str(code), str(code)) for code in overlap.get("matched_codes") or []]])


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
