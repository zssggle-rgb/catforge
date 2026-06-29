"""Business-facing claim value report generation.

This module turns existing M12C atom payloads into a short answer and a
Markdown report. It does not recalculate M12C values.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal

from app.services.core3_real_data.analyst.competitor_answer import ReportPublishResult, _publish_report


ReportMode = Literal["none", "markdown", "feishu-doc"]

CATEGORY_ORDER = (
    "高溢价卖点",
    "份额转化卖点",
    "客户获得价值卖点",
    "人无我有型支付价值卖点",
    "门槛卖点",
    "待激活卖点",
    "厂家主张卖点",
    "竞品拦截卖点",
    "价格压力卖点",
    "样本不足待复核",
)

POSITIVE_CATEGORIES = {"高溢价卖点", "份额转化卖点", "客户获得价值卖点"}
RISK_CATEGORIES = {"竞品拦截卖点", "价格压力卖点"}
DASHBOARD_TOP_CATEGORIES = ("高溢价卖点", "份额转化卖点", "客户获得价值卖点", "人无我有型支付价值卖点")
DASHBOARD_RISK_CATEGORIES = ("门槛卖点", "待激活卖点", "厂家主张卖点", "竞品拦截卖点", "价格压力卖点", "样本不足待复核")


@dataclass(frozen=True)
class ClaimValueReportFile:
    status: str
    path: str | None = None
    message_cn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "path": self.path, "message_cn": self.message_cn}


def build_claim_value_answer(
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    with_report: ReportMode = "none",
    max_chat_chars: int = 600,
    report_title: str | None = None,
) -> dict[str, Any]:
    title = report_title or f"{_display_name(target)} 用户卖点价值分析报告"
    report_dashboard_payload = build_claim_value_dashboard_payload(target=target, payload=payload, report_url=None)
    markdown = render_claim_value_report(title=title, target=target, payload=payload, dashboard_payload=report_dashboard_payload)
    report_file = _write_markdown_report(title=title, markdown=markdown) if with_report in {"markdown", "feishu-doc"} else ClaimValueReportFile(status="disabled", message_cn="未请求生成 Markdown 文件。")
    publish_result = _publish_report(title=title, markdown=markdown, with_report=with_report)
    report_location = _business_report_location(with_report=with_report, publish_result=publish_result, report_file=report_file)
    report_message = _business_report_message(with_report=with_report, publish_result=publish_result)
    dashboard_payload = build_claim_value_dashboard_payload(target=target, payload=payload, report_url=publish_result.url)
    feishu_card_payload = render_claim_value_feishu_card_payload(dashboard_payload)
    short_answer = render_claim_value_short_answer(
        target=target,
        payload=payload,
        report_location=report_location,
        report_message=report_message,
        max_chat_chars=max_chat_chars,
    )
    report = publish_result.to_dict()
    report["markdown_path"] = report_file.path
    if report_file.message_cn:
        report["markdown_message_cn"] = report_file.message_cn
    return {
        "short_answer": short_answer,
        "dashboard_payload": dashboard_payload,
        "feishu_card_payload": feishu_card_payload,
        "report": report,
        "markdown": markdown if with_report == "markdown" else None,
        "report_title": title,
    }


def render_claim_value_short_answer(
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    report_location: str | None = None,
    report_message: str | None = None,
    max_chat_chars: int = 600,
) -> str:
    name = _display_name(target)
    summary_rows = _sorted_summary_rows(payload)
    target_rows = _target_claim_rows(summary_rows)
    gap_rows = _non_target_claim_rows(summary_rows)
    premium = _rows_by_category(target_rows, "高溢价卖点")[:4]
    share = _rows_by_category(target_rows, "份额转化卖点")[:3]
    unique = _rows_by_category(target_rows, "人无我有型支付价值卖点")[:3]
    threshold = _rows_by_category(target_rows, "门槛卖点")[:4]
    pending = _rows_by_category(target_rows, "待激活卖点")[:3]
    target_risks = [row for category in RISK_CATEGORIES for row in _rows_by_category(target_rows, category)][:3]
    competitor_gaps = [row for row in gap_rows if _category(row) == "竞品拦截卖点"][:3]
    lines: list[str] = [f"{name} 的用户卖点价值结论："]
    if premium:
        lines.append(f"高溢价卖点主要是{_claim_names(premium)}，当前可解释金额约 {_range_or_total(premium, 'sku_level_user_payment_value_abs')}。")
    else:
        lines.append("当前没有形成稳定高溢价卖点，正向价值更多需要看份额转化、客户获得价值或待激活卖点。")
    if share:
        lines.append(f"份额转化卖点包括{_claim_names(share)}，更适合解释同价位下的销量承接。")
    if unique:
        lines.append(f"人无我有型支付价值卖点包括{_claim_names(unique)}，具备提高用户最高支付意愿的潜力，但当前同战场对照不足，暂不量化金额。")
    if threshold:
        lines.append(f"门槛卖点包括{_claim_names(threshold)}，有助于进入购买清单，但不作为单独加价理由。")
    if pending:
        lines.append(f"待激活卖点包括{_claim_names(pending)}，产品事实或厂家表达存在，但用户感知和市场验证仍需加强。")
    if target_risks:
        lines.append(f"本品价格压力或风险卖点集中在{_claim_names(target_risks)}。")
    if competitor_gaps:
        lines.append(f"竞品侧拦截/机会缺口集中在{_claim_names(competitor_gaps)}，这些不是本品当前已成立卖点。")
    if report_location:
        lines.append(f"详细报告：{report_location}")
    elif report_message:
        lines.append(report_message)
    return _compress_text("\n".join(lines), max_chat_chars=max_chat_chars)


def build_claim_value_dashboard_payload(
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    report_url: str | None = None,
) -> dict[str, Any]:
    summary_rows = _sorted_summary_rows(payload)
    detail_rows = [row for row in payload.get("claim_values") or [] if isinstance(row, dict)]
    target_rows = _target_claim_rows(summary_rows)
    gap_rows = _non_target_claim_rows(summary_rows)
    top_claims = _dashboard_top_claims(target_rows)
    structure_rows = _dashboard_claim_structure(target_rows + gap_rows)
    battlefield_sources = _dashboard_battlefield_sources(_target_claim_rows(detail_rows))
    activation_and_risk = _dashboard_activation_and_risk(target_rows=target_rows, gap_rows=gap_rows)
    links = [{"label": "查看完整报告", "url": report_url, "type": "report"}] if report_url else []
    title = f"{_display_name(target)} 用户卖点价值看板"
    return {
        "schema_version": "claim_value_dashboard_v1",
        "title": title,
        "target": {
            "sku_code": target.get("sku_code"),
            "brand_name": target.get("brand_name"),
            "model_name": target.get("model_name"),
            "display_name": _display_name(target),
            "market_summary": _target_market_summary(target),
        },
        "summary_cn": _dashboard_summary_cn(_display_name(target), top_claims, activation_and_risk),
        "claim_structure": structure_rows,
        "top_claims": top_claims,
        "battlefield_sources": battlefield_sources,
        "activation_and_risk": activation_and_risk,
        "report_evidence_links": links,
        "display_policy": {
            "main_answer": "feishu_card",
            "report_as_evidence": True,
            "card_delivery_stdout": True,
            "fallback_to_short_answer": True,
            "hide_internal_fields": True,
        },
    }


def render_claim_value_feishu_card_payload(dashboard_payload: dict[str, Any]) -> dict[str, Any]:
    title = str(dashboard_payload.get("title") or "用户卖点价值看板")
    target = dashboard_payload.get("target") or {}
    top_claims = [row for row in dashboard_payload.get("top_claims") or [] if isinstance(row, dict)]
    structure = [row for row in dashboard_payload.get("claim_structure") or [] if isinstance(row, dict)]
    battlefield_sources = [row for row in dashboard_payload.get("battlefield_sources") or [] if isinstance(row, dict)]
    risks = [row for row in dashboard_payload.get("activation_and_risk") or [] if isinstance(row, dict)]
    elements: list[dict[str, Any]] = [
        _feishu_markdown(_dashboard_card_conclusion(dashboard_payload)),
    ]
    if structure:
        elements.append({"tag": "hr"})
        elements.append(_feishu_markdown("**卖点价值结构**"))
        elements.append(_feishu_claim_structure_chart(structure, str(target.get("display_name") or "目标 SKU")))
    if top_claims:
        elements.append({"tag": "hr"})
        elements.append(_feishu_markdown("**Top 卖点价值**"))
        elements.append(_feishu_top_claims_table(top_claims))
    if battlefield_sources:
        elements.append({"tag": "hr"})
        elements.append(_feishu_markdown("**价值战场来源**"))
        elements.append(_feishu_battlefield_source_table(battlefield_sources))
    if risks:
        elements.append({"tag": "hr"})
        elements.append(_feishu_markdown(_dashboard_risk_markdown(risks)))
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
            "template": "turquoise",
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": str(target.get("market_summary") or "")[:80]},
        },
        "body": {"elements": elements},
    }
    return _trim_feishu_card(card)


def render_claim_value_dashboard_markdown(dashboard_payload: dict[str, Any]) -> list[str]:
    lines = [
        "## 用户卖点价值看板",
        "",
        _dashboard_card_conclusion(dashboard_payload),
        "",
    ]
    structure = [row for row in dashboard_payload.get("claim_structure") or [] if isinstance(row, dict)]
    if structure:
        lines.extend(["### 卖点价值结构", "", _dashboard_structure_text(structure), ""])
    top_claims = [row for row in dashboard_payload.get("top_claims") or [] if isinstance(row, dict)]
    if top_claims:
        lines.extend(
            [
                "### Top 卖点价值",
                "",
                "| 卖点 | 分类 | 成立战场 | 价值 | 证据 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in top_claims:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("claim_name")),
                        _md(row.get("business_type")),
                        _md("、".join(row.get("main_contexts") or []) or "相关战场待复核"),
                        _md(row.get("explainable_amount_cn") or row.get("potential_cn") or "暂不量化"),
                        _md(row.get("evidence_cn")),
                    ]
                )
                + " |"
            )
        lines.append("")
    battlefield_sources = [row for row in dashboard_payload.get("battlefield_sources") or [] if isinstance(row, dict)]
    if battlefield_sources:
        lines.extend(["### 价值战场来源", "", "| 战场 | 正向卖点 | 可解释价值 | 可解释销量 |", "| --- | --- | ---: | ---: |"])
        for row in battlefield_sources:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("battlefield_name")),
                        _md("、".join(row.get("positive_claims") or [])),
                        _md(row.get("amount_sum_cn") or "暂不量化"),
                        _md(row.get("sales_lift_sum_cn") or "暂不量化"),
                    ]
                )
                + " |"
            )
        lines.append("")
    risks = [row for row in dashboard_payload.get("activation_and_risk") or [] if isinstance(row, dict)]
    if risks:
        lines.extend(["### 待激活与风险提示", ""])
        for row in risks:
            claims = "、".join(str(item) for item in (row.get("claims") or [])[:5]) or "暂无"
            lines.append(f"- {row.get('category') or '风险项'}：{claims}。{row.get('meaning_cn') or ''}")
        lines.append("")
    return lines


def render_claim_value_report(
    *,
    title: str,
    target: dict[str, Any],
    payload: dict[str, Any],
    dashboard_payload: dict[str, Any] | None = None,
) -> str:
    summary_rows = _sorted_summary_rows(payload)
    detail_rows = [row for row in payload.get("claim_values") or [] if isinstance(row, dict)]
    target_summary_rows = _target_claim_rows(summary_rows)
    target_detail_rows = _target_claim_rows(detail_rows)
    dashboard = dashboard_payload or build_claim_value_dashboard_payload(target=target, payload=payload, report_url=None)
    lines = [
        f"# {title}",
        "",
        *render_claim_value_dashboard_markdown(dashboard),
        "",
        "## 一、分析结论",
        "",
        *_conclusion_lines(target, summary_rows),
        "",
        "## 二、本品已成立卖点价值总榜",
        "",
        *_summary_table_lines(target_summary_rows),
        "",
        "## 三、高溢价卖点明细",
        "",
        *_positive_detail_lines(target_summary_rows, category="高溢价卖点"),
        "",
        "## 四、人无我有型支付价值卖点",
        "",
        *_unique_potential_lines(target_summary_rows),
        "",
        "## 五、分价值战场拆解",
        "",
        *_battlefield_breakdown_lines(target_detail_rows),
        "",
        "## 六、门槛、待激活和风险卖点",
        "",
        *_non_positive_lines(target_summary_rows),
        "",
        "## 七、竞品拦截与机会缺口",
        "",
        *_competitor_gap_lines(summary_rows),
        "",
        "## 八、可追溯计算依据",
        "",
        *_method_lines(payload),
        "",
        "## 九、口径说明",
        "",
        "本报告把本品已成立卖点和竞品拦截/机会缺口分开呈现。本品已成立卖点以 M04C 卖点事实为边界；竞品侧机会项用于识别外部拦截方向，不计入本品当前卖点数量。可解释金额和可解释销量是基于可比市场池、价值战场权重和证据强度得到的解释性分摊，用于判断卖点价值强弱和排序，不代表该卖点单独导致价格或销量变化。人无我有型支付价值卖点只输出潜力等级和证据链，不输出金额。",
    ]
    return "\n".join(lines).strip() + "\n"


def _conclusion_lines(target: dict[str, Any], summary_rows: list[dict[str, Any]]) -> list[str]:
    name = _display_name(target)
    target_rows = _target_claim_rows(summary_rows)
    gap_rows = _non_target_claim_rows(summary_rows)
    premium = _rows_by_category(target_rows, "高溢价卖点")[:5]
    unique = _rows_by_category(target_rows, "人无我有型支付价值卖点")[:5]
    threshold = _rows_by_category(target_rows, "门槛卖点")[:5]
    pending = _rows_by_category(target_rows, "待激活卖点")[:5]
    risks = [row for category in RISK_CATEGORIES for row in _rows_by_category(target_rows, category)][:5]
    competitor_gaps = [row for row in gap_rows if _category(row) == "竞品拦截卖点"][:5]
    lines = [
        f"{name} 的用户卖点价值应按价值战场来理解：先判断本品进入哪些主/辅价值战场，再看每个战场里用户真正愿意为哪些已成立卖点支付更高价格或给出销量承接。",
    ]
    if premium:
        lines.append(f"当前稳定高溢价卖点为：{_claim_names(premium)}。这些卖点在对应价值战场内同时具备参数支撑、用户评论感知和市场承接。")
    else:
        lines.append("当前没有稳定高溢价卖点，说明本品卖点更多表现为入围门槛、份额转化或待激活能力。")
    if threshold:
        lines.append(f"门槛卖点为：{_claim_names(threshold)}。这些能力有助于进入用户候选清单，但不宜直接解释为加价来源。")
    if unique:
        lines.append(f"人无我有型支付价值卖点为：{_claim_names(unique)}。这些能力可能提高用户最高支付意愿，但当前同战场缺少稳定对照样本，因此只输出潜力和验证条件，不输出金额。")
    if pending:
        lines.append(f"待激活卖点为：{_claim_names(pending)}。这些卖点需要通过导购表达、内容教育或产品证据强化，才能转化为用户支付理由。")
    if risks:
        lines.append(f"需要关注的风险/拦截卖点为：{_claim_names(risks)}。这些方向可能影响本品在同战场中的成交解释力。")
    if competitor_gaps:
        lines.append(f"竞品侧拦截/机会缺口为：{_claim_names(competitor_gaps)}。这些不是本品当前已成立卖点，用于判断竞品可能从哪些方向分流。")
    return lines


def _summary_table_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["当前 SKU 没有本品已成立卖点价值量化结果。"]
    lines = [
        "| 卖点 | 归属口径 | 业务分类 | 主要成立战场 | 关键参数竞争力 | 可解释金额 | 可解释销量 | 证据摘要 |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in rows[:40]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row.get("claim_name") or row.get("claim_code") or "未命名卖点"),
                    _md(_claim_source_label(row)),
                    _md(_category(row)),
                    _md("、".join(str(item) for item in (row.get("main_contexts") or [])[:4]) or "待形成稳定战场"),
                    _md(_parameter_competitiveness_label(row)),
                    _md(_money(row.get("sku_level_user_payment_value_abs")) or "不作为正向量化"),
                    _md((_volume(row.get("sku_level_weekly_sales_lift_abs")) + "台/周") if _volume(row.get("sku_level_weekly_sales_lift_abs")) else "不作为正向量化"),
                    _md(row.get("evidence_summary_cn") or _claim_type_meaning(_category(row))),
                ]
            )
            + " |"
        )
    return lines


def _positive_detail_lines(rows: list[dict[str, Any]], *, category: str) -> list[str]:
    items = _rows_by_category(rows, category)
    if not items:
        return [f"当前没有形成稳定{category}。"]
    lines: list[str] = []
    for row in items:
        claim_name = str(row.get("claim_name") or row.get("claim_code") or "未命名卖点")
        lines.append(f"### {claim_name}")
        lines.append("")
        lines.append(
            f"- 整机口径：可解释金额 {_money(row.get('sku_level_user_payment_value_abs')) or '暂不量化'}，"
            f"可解释销量 {(_volume(row.get('sku_level_weekly_sales_lift_abs')) + '台/周') if _volume(row.get('sku_level_weekly_sales_lift_abs')) else '暂不量化'}。"
        )
        contexts = [item for item in (row.get("context_values") or []) if isinstance(item, dict)]
        if contexts:
            lines.append("- 分战场来源：")
            for context in contexts[:6]:
                lines.append(
                    f"  - {context.get('context_name') or context.get('context_code') or '当前价值战场'}："
                    f"可解释金额 {_money(context.get('price_premium_abs')) or '暂不量化'}，"
                    f"可解释销量 {(_volume(context.get('weekly_sales_lift_abs')) + '台/周') if _volume(context.get('weekly_sales_lift_abs')) else '暂不量化'}。"
                )
        evidence = str(row.get("evidence_summary_cn") or "").strip()
        if evidence:
            lines.append(f"- 证据解释：{evidence}")
        parameter_summary = _parameter_competitiveness_detail(row)
        if parameter_summary:
            lines.append(f"- 参数竞争力：{parameter_summary}")
        lines.append("")
    return lines


def _unique_potential_lines(rows: list[dict[str, Any]]) -> list[str]:
    items = _rows_by_category(rows, "人无我有型支付价值卖点")
    if not items:
        return ["当前没有人无我有型支付价值卖点。"]
    lines = [
        "这类卖点代表本品在同价值战场里具备稀缺能力或关键参数优势，可能提高用户最高支付意愿；但由于同战场缺少稳定对照样本，当前不输出金额。",
        "",
        "| 卖点 | 主要成立战场 | 潜力等级/分数 | 关键参数竞争力 | 当前不量化原因 | 验证条件 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in items[:12]:
        scorecard = _unique_scorecard(row)
        score = _decimal(scorecard.get("total_score"))
        potential = str(scorecard.get("potential_level_cn") or "").strip()
        score_text = f"{potential}（{score.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}分）" if score is not None else potential or "潜力待复核"
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row.get("claim_name") or row.get("claim_code") or "未命名卖点"),
                    _md("、".join(str(item) for item in (row.get("main_contexts") or [])[:4]) or "相关战场待复核"),
                    _md(score_text),
                    _md(_parameter_competitiveness_label(row)),
                    _md(str(scorecard.get("no_amount_reason_cn") or "同战场对照样本不足，不能量化金额。")),
                    _md(str(scorecard.get("verification_required_cn") or "需要后续观察竞品跟进、评论和市场承接。")),
                ]
            )
            + " |"
        )
    return lines


def _battlefield_breakdown_lines(rows: list[dict[str, Any]]) -> list[str]:
    battlefield_rows = [row for row in rows if str(row.get("context_type") or "") == "battlefield"]
    if not battlefield_rows:
        return ["当前没有可展示的价值战场明细。"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in battlefield_rows:
        key = str(row.get("context_name") or row.get("context_code") or "未命名价值战场")
        grouped.setdefault(key, []).append(row)
    lines: list[str] = []
    for battlefield, items in sorted(grouped.items()):
        lines.append(f"### {battlefield}")
        lines.append("")
        lines.append("| 卖点 | 业务分类 | 本品可解释金额/潜力等级 | 本品可解释销量 | 参数竞争力 | 证据说明 |")
        lines.append("| --- | --- | ---: | ---: | --- | --- |")
        for row in _sort_detail_rows(items)[:12]:
            sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
            unique_row = _category(row) == "人无我有型支付价值卖点"
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("claim_name") or row.get("claim_code") or "未命名卖点"),
                        _md(_category(row)),
                        _md(_unique_potential_text(row) if unique_row else (_money(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")) or "不作为正向分摊")),
                        _md("暂不量化" if unique_row else ((_volume(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")) + "台/周") if _volume(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")) else "不作为正向分摊")),
                        _md(_parameter_competitiveness_label(row)),
                        _md(row.get("evidence_summary_cn") or _claim_type_meaning(_category(row))),
                    ]
                )
                + " |"
            )
        lines.append("")
        lines.append("说明：本表展示分摊到本品卖点的业务解释结果，不展示有卖点组与对照组的原始可比池价差。原始组间差只作为评分和复核输入，不能直接理解为单个卖点带来的溢价。")
        lines.append("")
    return lines


def _non_positive_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for category in ("门槛卖点", "待激活卖点", "厂家主张卖点", "价格压力卖点", "样本不足待复核"):
        items = _rows_by_category(rows, category)
        if not items:
            continue
        lines.append(f"### {category}")
        lines.append("")
        lines.append(_claim_type_meaning(category))
        lines.append("")
        for row in items[:8]:
            contexts = "、".join(str(item) for item in (row.get("main_contexts") or [])[:4]) or "相关场景待复核"
            lines.append(f"- {row.get('claim_name') or row.get('claim_code') or '未命名卖点'}：{contexts}。{row.get('evidence_summary_cn') or ''}")
        lines.append("")
    return lines or ["当前没有门槛、待激活或风险卖点结果。"]


def _competitor_gap_lines(rows: list[dict[str, Any]]) -> list[str]:
    gap_rows = [row for row in _non_target_claim_rows(rows) if _category(row) == "竞品拦截卖点"]
    if not gap_rows:
        return ["当前没有竞品侧拦截或机会缺口结果。"]
    lines = [
        "以下项目不是本品当前已成立卖点，而是同一价值战场内竞品已经形成表达或市场验证、本品缺失或表达较弱的方向。",
        "",
    ]
    for row in gap_rows[:12]:
        contexts = "、".join(str(item) for item in (row.get("main_contexts") or [])[:4]) or "相关场景待复核"
        lines.append(f"- {row.get('claim_name') or row.get('claim_code') or '未命名方向'}：{contexts}。{row.get('evidence_summary_cn') or ''}")
    return lines


def _method_lines(payload: dict[str, Any]) -> list[str]:
    note = str(payload.get("method_note_cn") or "").strip()
    lines = [
        "1. 先识别 SKU 的主/辅价值战场，正向量化以价值战场为主轴。",
        "2. 在同价值战场、同尺寸层级、同价格带中建立可比市场池，并区分有该卖点组与对照组。",
        "3. 观察可比池中有卖点组与对照组的价格差异、销量差异和销额差异。",
        "4. 再判断本品相对直接可比基准的市场位置，是溢价承接、份额转化、客户获得价值、价格压力，还是支付价值未验证。",
        "5. 对卖点下的支撑参数做战场内竞争力判断，区分领先优势、较强优势、基础门槛、弱或缺失、样本不足。",
        "6. 如果目标 SKU 是有卖点组孤例，或有卖点组/对照组不足，则进入人无我有型支付价值判断，只输出潜力和验证条件，不分配金额。",
        "7. 最后结合参数竞争力、评论感知、竞品差异、样本充分性和战场权重，把可解释金额和销量分摊到可量化卖点。",
    ]
    if note:
        lines.append(f"补充口径：{note}")
    return lines


def _write_markdown_report(*, title: str, markdown: str) -> ClaimValueReportFile:
    try:
        base_dir = Path(os.environ.get("CATFORGE_ANALYST_REPORT_DIR") or Path(tempfile.gettempdir()) / "catforge_reports")
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        filename = f"{timestamp}_{_slug(title)}.md"
        path = base_dir / filename
        path.write_text(markdown, encoding="utf-8")
        return ClaimValueReportFile(status="created", path=str(path), message_cn="已生成 Markdown 报告文件。")
    except Exception:
        return ClaimValueReportFile(status="failed", message_cn="Markdown 报告文件写入失败。")


def _business_report_location(*, with_report: ReportMode, publish_result: ReportPublishResult, report_file: ClaimValueReportFile) -> str | None:
    if with_report == "feishu-doc":
        return publish_result.url
    if with_report == "markdown":
        return report_file.path
    return None


def _business_report_message(*, with_report: ReportMode, publish_result: ReportPublishResult) -> str | None:
    if with_report != "feishu-doc":
        return None
    if publish_result.url:
        return None
    message = publish_result.message_cn or "飞书文档生成失败。"
    return f"飞书文档未生成：{message}"


def _dashboard_top_claims(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for category in DASHBOARD_TOP_CATEGORIES:
        category_rows = _rows_by_category(rows, category)
        category_rows = sorted(category_rows, key=_dashboard_claim_sort_key)
        for row in category_rows:
            if len(selected) >= limit:
                break
            selected.append(row)
        if len(selected) >= limit:
            break
    payload: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        category = _category(row)
        amount = _decimal(row.get("sku_level_user_payment_value_abs")) or Decimal("0")
        sales = _decimal(row.get("sku_level_weekly_sales_lift_abs")) or Decimal("0")
        payload.append(
            {
                "rank": index,
                "claim_code": row.get("claim_code"),
                "claim_name": str(row.get("claim_name") or row.get("claim_code") or "未命名卖点"),
                "business_type": category,
                "main_contexts": [str(item) for item in (row.get("main_contexts") or [])[:2] if item],
                "explainable_amount_cn": _dashboard_value_text(row),
                "explainable_sales_cn": _approx_volume(sales) if sales > 0 and category != "人无我有型支付价值卖点" else "暂不量化",
                "potential_cn": _unique_potential_text(row) if category == "人无我有型支付价值卖点" else "",
                "parameter_strength_cn": _parameter_strength_short(row),
                "evidence_cn": _dashboard_evidence_text(row),
                "amount_value": _float(amount),
                "sales_lift_value": _float(sales),
            }
        )
    return payload


def _dashboard_claim_structure(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        items = _rows_by_category(rows, category)
        if not items:
            continue
        amount_sum = sum((_decimal(row.get("sku_level_user_payment_value_abs")) or Decimal("0")) for row in items)
        sales_sum = sum((_decimal(row.get("sku_level_weekly_sales_lift_abs")) or Decimal("0")) for row in items)
        result.append(
            {
                "category": category,
                "category_short": _category_short(category),
                "count": len(items),
                "amount_sum": _float(amount_sum),
                "sales_lift_sum": _float(sales_sum),
            }
        )
    return result


def _dashboard_battlefield_sources(rows: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("context_type") or "") != "battlefield":
            continue
        if _category(row) not in POSITIVE_CATEGORIES:
            continue
        battlefield = str(row.get("context_name") or row.get("context_code") or "未命名价值战场")
        if not battlefield:
            continue
        sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
        amount = _decimal(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs")) or Decimal("0")
        sales = _decimal(sku_excess.get("sku_excess_weekly_sales_explained_abs") or sku_excess.get("weekly_sales_lift_abs")) or Decimal("0")
        bucket = grouped.setdefault(
            battlefield,
            {
                "battlefield_name": battlefield,
                "positive_claims": [],
                "amount_sum": Decimal("0"),
                "sales_lift_sum": Decimal("0"),
            },
        )
        claim_name = str(row.get("claim_name") or row.get("claim_code") or "未命名卖点")
        if claim_name not in bucket["positive_claims"]:
            bucket["positive_claims"].append(claim_name)
        bucket["amount_sum"] += amount
        bucket["sales_lift_sum"] += sales
    result: list[dict[str, Any]] = []
    for bucket in sorted(grouped.values(), key=lambda item: (-(item["amount_sum"]), str(item["battlefield_name"])))[:limit]:
        result.append(
            {
                "battlefield_name": bucket["battlefield_name"],
                "positive_claims": bucket["positive_claims"][:5],
                "amount_sum_cn": _approx_money(bucket["amount_sum"]) if bucket["amount_sum"] > 0 else "暂不量化",
                "sales_lift_sum_cn": _approx_volume(bucket["sales_lift_sum"]) if bucket["sales_lift_sum"] > 0 else "暂不量化",
                "amount_sum": _float(bucket["amount_sum"]),
                "sales_lift_sum": _float(bucket["sales_lift_sum"]),
            }
        )
    return result


def _dashboard_activation_and_risk(*, target_rows: list[dict[str, Any]], gap_rows: list[dict[str, Any]], limit_per_category: int = 5) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for category in DASHBOARD_RISK_CATEGORIES:
        rows = gap_rows if category == "竞品拦截卖点" else target_rows
        items = _rows_by_category(rows, category)
        if not items:
            continue
        sorted_items = sorted(items, key=_dashboard_claim_sort_key)[:limit_per_category]
        result.append(
            {
                "category": category,
                "claims": [str(row.get("claim_name") or row.get("claim_code") or "未命名卖点") for row in sorted_items],
                "meaning_cn": _claim_type_meaning(category),
            }
        )
    return result


def _dashboard_summary_cn(target_name: str, top_claims: list[dict[str, Any]], risks: list[dict[str, Any]]) -> str:
    positive = [row for row in top_claims if row.get("business_type") in POSITIVE_CATEGORIES]
    unique = [row for row in top_claims if row.get("business_type") == "人无我有型支付价值卖点"]
    names = [str(row.get("claim_name") or "") for row in positive[:4] if row.get("claim_name")]
    if names:
        first_sentence = f"{target_name} 的正向支付价值集中在{_join_cn(names)}。"
    elif unique:
        first_sentence = f"{target_name} 当前以人无我有型支付价值卖点为主，需继续验证金额承接。"
    else:
        first_sentence = f"{target_name} 当前没有稳定正向支付价值卖点。"
    battlefield_names = _unique_texts(
        [
            str(context)
            for row in top_claims[:5]
            for context in (row.get("main_contexts") or [])
            if context
        ]
    )
    second_sentence = f"主要成立场景为{_join_cn(battlefield_names[:3])}。" if battlefield_names else ""
    risk_parts: list[str] = []
    for category in ("门槛卖点", "待激活卖点", "竞品拦截卖点"):
        row = next((item for item in risks if item.get("category") == category), None)
        if row and row.get("claims"):
            risk_parts.append(f"{category.replace('卖点', '')}包括{_join_cn([str(item) for item in row['claims'][:3]])}")
    risk_sentence = "；".join(risk_parts[:2]) + "。" if risk_parts else ""
    return (first_sentence + second_sentence + risk_sentence).strip()


def _dashboard_value_text(row: dict[str, Any]) -> str:
    if _category(row) == "人无我有型支付价值卖点":
        return _unique_potential_text(row)
    amount = _decimal(row.get("sku_level_user_payment_value_abs")) or Decimal("0")
    return _approx_money(amount) if amount > 0 else "暂不量化"


def _dashboard_evidence_text(row: dict[str, Any]) -> str:
    evidence = str(row.get("evidence_summary_cn") or "").strip()
    if evidence:
        return _compact_cn(evidence, limit=42)
    strength = _parameter_strength_short(row)
    category = _claim_type_meaning(_category(row))
    if strength and strength != "参数待补充":
        return _compact_cn(f"{strength}；{category}", limit=42)
    return _compact_cn(category, limit=42)


def _dashboard_claim_sort_key(row: dict[str, Any]) -> tuple[int, Decimal, Decimal, Decimal, str]:
    category_rank = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    unique_score = _decimal(_unique_scorecard(row).get("total_score")) or Decimal("0")
    param_score = _decimal(_parameter_competitiveness_snapshot(row).get("overall_parameter_competitiveness_score")) or Decimal("0")
    return (
        category_rank.get(_category(row), 99),
        -(_decimal(row.get("sku_level_user_payment_value_abs")) or Decimal("0")),
        -(_decimal(row.get("sku_level_weekly_sales_lift_abs")) or Decimal("0")),
        -(unique_score or param_score),
        str(row.get("claim_name") or row.get("claim_code") or ""),
    )


def _dashboard_card_conclusion(dashboard_payload: dict[str, Any]) -> str:
    summary = str(dashboard_payload.get("summary_cn") or "").strip()
    if not summary:
        summary = "当前没有足够证据形成稳定用户卖点价值看板。"
    return f"**结论：{summary}**"


def _dashboard_structure_text(structure: list[dict[str, Any]]) -> str:
    parts = []
    for row in structure:
        category = str(row.get("category_short") or row.get("category") or "")
        count = int(row.get("count") or 0)
        if category and count:
            parts.append(f"{category} {count} 个")
    return "｜".join(parts) if parts else "暂无卖点价值结构。"


def _dashboard_risk_markdown(risks: list[dict[str, Any]]) -> str:
    lines = ["**待激活与风险提示**"]
    for row in risks[:4]:
        claims = _join_cn([str(item) for item in (row.get("claims") or [])[:4]]) or "暂无"
        lines.append(f"- {row.get('category') or '风险项'}：{claims}。{_compact_cn(row.get('meaning_cn'), limit=40)}")
    return "\n".join(lines)


def _target_market_summary(target: dict[str, Any]) -> str:
    size = _decimal(target.get("screen_size_inch"))
    price = _decimal(target.get("weighted_price"))
    sales = _decimal(target.get("avg_weekly_sales_volume"))
    price_band = str(target.get("price_band_in_size_tier") or "").strip()
    parts: list[str] = []
    if size is not None and size > 0:
        parts.append(f"{size.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}寸")
    if price_band:
        parts.append(_price_band_cn(price_band))
    if price is not None and price > 0:
        parts.append(f"均价约{price.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}元")
    if sales is not None and sales > 0:
        parts.append(f"周均约{_volume(sales)}台")
    return "，".join(parts)


def _feishu_markdown(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _feishu_claim_structure_chart(structure: list[dict[str, Any]], target_name: str) -> dict[str, Any]:
    values = [
        {
            "target": target_name,
            "category": str(row.get("category_short") or row.get("category") or ""),
            "count": int(row.get("count") or 0),
        }
        for row in structure
        if int(row.get("count") or 0) > 0
    ]
    return {
        "tag": "chart",
        "element_id": "claim_value_structure",
        "aspect_ratio": "16:9",
        "height": "220px",
        "preview": False,
        "chart_spec": {
            "type": "bar",
            "data": {"values": values},
            "direction": "horizontal",
            "xField": "count",
            "yField": "target",
            "seriesField": "category",
            "stack": True,
            "color": ["#0F9F8F", "#155E75", "#F59E0B", "#64748B", "#94A3B8", "#DC2626", "#7C3AED"],
            "bar": {"style": {"cornerRadius": 3}},
            "label": {"visible": True, "position": "inside", "formatter": "{count}", "smartInvert": True},
            "axes": [
                {"orient": "bottom", "min": 0, "title": {"visible": True, "text": "卖点数量"}},
                {"orient": "left", "label": {"visible": False}},
            ],
            "legends": {"visible": True, "orient": "bottom"},
            "tooltip": {"visible": True},
        },
    }


def _feishu_top_claims_table(top_claims: list[dict[str, Any]]) -> dict[str, Any]:
    return _feishu_table(
        element_id="claim_value_top_claims",
        columns=[
            _feishu_text_column("claim", "卖点"),
            _feishu_text_column("category", "分类", width="120px"),
            _feishu_text_column("context", "战场"),
            _feishu_text_column("value", "价值", width="120px"),
            _feishu_text_column("evidence", "证据"),
        ],
        rows=[
            {
                "claim": str(row.get("claim_name") or ""),
                "category": str(row.get("business_type") or ""),
                "context": "、".join(str(item) for item in (row.get("main_contexts") or [])[:2]) or "待复核",
                "value": str(row.get("explainable_amount_cn") or row.get("potential_cn") or "暂不量化"),
                "evidence": str(row.get("evidence_cn") or ""),
            }
            for row in top_claims[:5]
        ],
    )


def _feishu_battlefield_source_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return _feishu_table(
        element_id="claim_value_battlefield_sources",
        columns=[
            _feishu_text_column("battlefield", "战场"),
            _feishu_text_column("claims", "正向卖点"),
            _feishu_text_column("amount", "可解释价值", width="120px"),
            _feishu_text_column("sales", "可解释销量", width="120px"),
        ],
        rows=[
            {
                "battlefield": str(row.get("battlefield_name") or ""),
                "claims": "、".join(str(item) for item in (row.get("positive_claims") or [])[:4]),
                "amount": str(row.get("amount_sum_cn") or "暂不量化"),
                "sales": str(row.get("sales_lift_sum_cn") or "暂不量化"),
            }
            for row in rows[:5]
        ],
    )


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
        "element_id": "view_claim_value_report",
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


def _feishu_text_column(name: str, display_name: str, *, width: str = "auto") -> dict[str, Any]:
    return {
        "name": name,
        "display_name": display_name,
        "data_type": "text",
        "horizontal_align": "left",
        "vertical_align": "top",
        "width": width,
    }


def _trim_feishu_card(card: dict[str, Any]) -> dict[str, Any]:
    elements = ((card.get("body") or {}).get("elements") or [])
    if len(str(card)) <= 25000:
        return card
    trimmed = dict(card)
    body = dict(trimmed.get("body") or {})
    body["elements"] = elements[:8]
    trimmed["body"] = body
    return trimmed


def _sorted_summary_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in payload.get("sku_level_claim_values") or [] if isinstance(row, dict)]
    return sorted(rows, key=_summary_sort_key)


def _target_claim_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _target_has_claim(row)]


def _non_target_claim_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if not _target_has_claim(row)]


def _target_has_claim(row: dict[str, Any]) -> bool:
    if "target_has_claim" in row:
        return bool(row.get("target_has_claim"))
    source_type = str(row.get("claim_source_type") or "").strip()
    if source_type == "competitor_opportunity_gap":
        return False
    if _category(row) == "竞品拦截卖点":
        return False
    evidence = row.get("evidence_strength") or {}
    claim_strength = _decimal(evidence.get("claim")) or Decimal("0")
    if claim_strength > 0:
        return True
    return True


def _claim_source_label(row: dict[str, Any]) -> str:
    label = str(row.get("claim_source_type_cn") or "").strip()
    if label:
        return label
    return "本品已成立卖点" if _target_has_claim(row) else "竞品拦截/机会缺口"


def _parameter_competitiveness_label(row: dict[str, Any]) -> str:
    snapshot = _parameter_competitiveness_snapshot(row)
    if not snapshot:
        return "参数竞争力待补充"
    level = str(snapshot.get("overall_parameter_competitiveness_level_cn") or "").strip() or "未判断"
    score = _decimal(snapshot.get("overall_parameter_competitiveness_score"))
    score_text = f"{score.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}分" if score is not None else "未评分"
    key_params = _key_param_labels(snapshot)[:2]
    suffix = f"；关键参数：{'、'.join(key_params)}" if key_params else ""
    return f"{level}（{score_text}）{suffix}"


def _parameter_competitiveness_detail(row: dict[str, Any]) -> str:
    snapshot = _parameter_competitiveness_snapshot(row)
    if not snapshot:
        return ""
    explanation = str(snapshot.get("explanation_cn") or "").strip()
    key_params = _key_param_labels(snapshot)[:4]
    parts: list[str] = []
    if explanation:
        parts.append(explanation)
    if key_params:
        parts.append("关键参数：" + "、".join(key_params))
    return "；".join(parts)


def _parameter_competitiveness_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = row.get("parameter_competitiveness")
    if isinstance(snapshot, dict) and snapshot:
        return snapshot
    supporting = row.get("supporting_dimensions") or {}
    if isinstance(supporting, dict) and isinstance(supporting.get("parameter_competitiveness"), dict):
        return supporting.get("parameter_competitiveness") or {}
    contexts = [item for item in (row.get("context_values") or []) if isinstance(item, dict)]
    snapshots = [item.get("parameter_competitiveness") for item in contexts if isinstance(item.get("parameter_competitiveness"), dict)]
    snapshots = [item for item in snapshots if item]
    if not snapshots:
        return {}
    return max(snapshots, key=lambda item: _decimal(item.get("overall_parameter_competitiveness_score")) or Decimal("0"))


def _unique_scorecard(row: dict[str, Any]) -> dict[str, Any]:
    supporting = row.get("supporting_dimensions") or {}
    if isinstance(supporting, dict) and isinstance(supporting.get("unique_payment_potential_scorecard"), dict):
        scorecard = supporting.get("unique_payment_potential_scorecard") or {}
        if scorecard:
            return scorecard
    scorecard = row.get("unique_payment_potential_scorecard")
    if isinstance(scorecard, dict) and scorecard:
        return scorecard
    contexts = [item for item in (row.get("context_values") or []) if isinstance(item, dict)]
    candidates: list[dict[str, Any]] = []
    for item in contexts:
        supporting_item = item.get("supporting_dimensions") if isinstance(item.get("supporting_dimensions"), dict) else {}
        scorecard = supporting_item.get("unique_payment_potential_scorecard") if isinstance(supporting_item, dict) else None
        if isinstance(scorecard, dict) and scorecard:
            candidates.append(scorecard)
        direct = item.get("unique_payment_potential_scorecard")
        if isinstance(direct, dict) and direct:
            candidates.append(direct)
        nested = (item.get("scorecard") or {}).get("unique_payment_potential") if isinstance(item.get("scorecard"), dict) else None
        if isinstance(nested, dict) and nested:
            candidates.append(nested)
    if not candidates:
        return {}
    return max(candidates, key=lambda item: _decimal(item.get("total_score")) or Decimal("0"))


def _unique_potential_text(row: dict[str, Any]) -> str:
    scorecard = _unique_scorecard(row)
    potential = str(scorecard.get("potential_level_cn") or "").strip()
    score = _decimal(scorecard.get("total_score"))
    if potential and score is not None:
        return f"{potential}（{score.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}分）"
    if potential:
        return potential
    return "暂不量化"


def _key_param_labels(snapshot: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for item in snapshot.get("key_param_results") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("source_param_code") or item.get("param_code") or "").strip()
        value = item.get("target_value")
        level = str(item.get("level_cn") or "").strip()
        if not name:
            continue
        value_text = "" if value is None else f"={value}"
        labels.append(f"{name}{value_text}{f'（{level}）' if level else ''}")
    return labels


def _summary_sort_key(row: dict[str, Any]) -> tuple[int, Decimal, Decimal, str]:
    category_rank = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    return (
        category_rank.get(_category(row), 99),
        -(_decimal(row.get("sku_level_user_payment_value_abs")) or Decimal("0")),
        -(_decimal(row.get("sku_level_weekly_sales_lift_abs")) or Decimal("0")),
        str(row.get("claim_name") or row.get("claim_code") or ""),
    )


def _sort_detail_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            CATEGORY_ORDER.index(_category(row)) if _category(row) in CATEGORY_ORDER else 99,
            -(_detail_price(row) or Decimal("0")),
            str(row.get("claim_name") or row.get("claim_code") or ""),
        ),
    )


def _detail_price(row: dict[str, Any]) -> Decimal | None:
    sku_excess = row.get("sku_excess_explanation") or row.get("estimated_contribution") or {}
    return _decimal(sku_excess.get("sku_excess_price_explained_abs") or sku_excess.get("price_premium_abs"))


def _rows_by_category(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [row for row in rows if _category(row) == category]


def _category(row: dict[str, Any]) -> str:
    value = str(row.get("business_claim_type_cn") or row.get("claim_value_role_cn") or "").strip()
    return value if value else "未分类卖点"


def _claim_names(rows: list[dict[str, Any]]) -> str:
    names = [str(row.get("claim_name") or row.get("claim_code") or "未命名卖点") for row in rows if row]
    return "、".join(names)


def _range_or_total(rows: list[dict[str, Any]], key: str) -> str:
    values = [_decimal(row.get(key)) for row in rows]
    values = [value for value in values if value is not None and value > 0]
    if not values:
        return "暂不量化"
    if len(values) == 1:
        return _money(values[0]) or "暂不量化"
    return f"{_money(min(values))}-{_money(max(values))}"


def _display_name(target: dict[str, Any]) -> str:
    brand = str(target.get("brand_name") or "").strip()
    model = str(target.get("model_name") or "").strip()
    sku = str(target.get("sku_code") or "").strip()
    return " ".join(part for part in (brand, model) if part) or sku or "目标 SKU"


def _claim_type_meaning(category: str) -> str:
    return {
        "高溢价卖点": "用户愿意为该卖点支付更高价格，并且参数、评论和市场验证共同成立。",
        "份额转化卖点": "该卖点不一定抬高价格，但能解释同价或相近价格下的销量/份额优势。",
        "客户获得价值卖点": "该卖点让用户觉得产品更值，主要体现为价格压力更小或销量承接更强。",
        "人无我有型支付价值卖点": "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿，但当前缺少稳定对照样本，不能量化金额。",
        "门槛卖点": "该卖点是进入购买清单的基础要求，有了不一定加价，缺了会掉队。",
        "待激活卖点": "本品有参数或厂家表达，但用户评论或市场验证还不足，需要继续激活。",
        "厂家主张卖点": "当前主要是厂家主张，尚未形成稳定用户支付价值。",
        "竞品拦截卖点": "竞品具备并形成市场验证，本品缺失或表达弱，会影响购买转化。",
        "价格压力卖点": "卖点表达、参数或用户反馈没有支撑当前价格，可能削弱成交理由。",
        "样本不足待复核": "样本或对照组不足，只能作为观察线索。",
    }.get(category, "当前分类尚未定义。")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _money(value: Any) -> str:
    number = _decimal(value)
    if number is None or number <= 0:
        return ""
    return f"{number.quantize(Decimal('1'), rounding=ROUND_HALF_UP)}元"


def _volume(value: Any) -> str:
    number = _decimal(value)
    if number is None or number <= 0:
        return ""
    quantized = number.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral_value():
        return str(quantized.to_integral_value())
    return str(quantized)


def _float(value: Any) -> float:
    number = _decimal(value)
    if number is None:
        return 0.0
    return float(number)


def _approx_money(value: Any) -> str:
    text = _money(value)
    return f"约{text}" if text else "暂不量化"


def _approx_volume(value: Any) -> str:
    text = _volume(value)
    return f"约{text}台/周" if text else "暂不量化"


def _parameter_strength_short(row: dict[str, Any]) -> str:
    snapshot = _parameter_competitiveness_snapshot(row)
    if not snapshot:
        return "参数待补充"
    level = str(snapshot.get("overall_parameter_competitiveness_level_cn") or "").strip()
    return level or "参数待补充"


def _category_short(category: str) -> str:
    return {
        "高溢价卖点": "高溢价",
        "份额转化卖点": "份额转化",
        "客户获得价值卖点": "客户获得价值",
        "人无我有型支付价值卖点": "人无我有",
        "门槛卖点": "门槛",
        "待激活卖点": "待激活",
        "厂家主张卖点": "厂家主张",
        "竞品拦截卖点": "竞品拦截",
        "价格压力卖点": "价格压力",
        "样本不足待复核": "样本待复核",
    }.get(category, category)


def _price_band_cn(value: str) -> str:
    return {
        "low": "低价带",
        "mid_low": "中低价带",
        "mid": "中价带",
        "mid_high": "中高价带",
        "high": "高价带",
    }.get(value, value)


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _join_cn(values: list[str]) -> str:
    clean = _unique_texts(values)
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return "和".join(clean)
    return "、".join(clean[:-1]) + "和" + clean[-1]


def _compact_cn(value: Any, *, limit: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _md(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _slug(value: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", value, flags=re.UNICODE).strip("_")
    return text[:80] or "claim_value_report"


def _compress_text(text: str, *, max_chat_chars: int) -> str:
    if max_chat_chars <= 0 or len(text) <= max_chat_chars:
        return text
    return text[: max(0, max_chat_chars - 1)].rstrip() + "…"
