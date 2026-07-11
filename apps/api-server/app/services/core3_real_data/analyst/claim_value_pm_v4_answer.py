"""Product-manager business DTO and renderers for sellpoint value V4."""

from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    ComparabilityAssessment,
    ProductValueStructureRow,
    QuantificationResult,
    ReasonValueBundleLink,
    SellpointValueV4Context,
    SkuProductValueRealizationReport,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    build_counterfactual_assessments,
    build_reason_value_bundle_links,
    quantify_sellpoint_value,
)
from app.services.core3_real_data.analyst.competitor_answer import _publish_report


ROLE_CN = {
    "core_differentiated_value": "核心差异价值",
    "basic_threshold": "同档门槛价值",
    "supporting_choice_value": "辅助选择价值",
    "customer_captured_value": "已被价格承接的价值",
    "configuration_support": "配置支撑，尚未证明选择价值",
    "price_pressure": "存在价格压力",
    "undetermined": "尚不能判断",
}
TIER_CN = {
    "unknown": "档位未知",
    "base": "基础档",
    "enhanced": "增强档",
    "premium": "高阶档",
    "flagship": "旗舰档",
}
VALUE_STATUS_CN = {
    "established": "用户已实际感知到这项价值",
    "partial": "用户只感知到部分价值",
    "not_observed": "现有购后证据尚未观察到这项价值",
    "conflicted": "用户实际体验存在正反冲突",
}
WTP_EXCLUSION_CN = {
    "version_lineage_conflict": "事实版本存在冲突，价格归因暂停",
    "user_value_not_fully_established": "用户实际价值尚未完整成立",
    "relative_experience_not_comparable": "缺少可比的购后体验",
    "same_value_only": "只有同价值对照，不能识别增量支付",
    "base_counterfactual_missing": "没有较低价值档对照",
    "base_counterfactual_not_eligible": "较低价值档候选的可比性不足",
    "independent_a_pair_count_below_2": "独立高可比对照不足两组",
    "model_family_count_below_2": "独立产品族不足两组",
    "strong_pair_curve_count_below_2": "共同量价样本不足两组",
    "price_direction_consistency_failed": "价格与选择方向不稳定",
    "equal_choice_crossing_count_below_2": "观测范围内缺少稳定的五五开交点",
    "leave_one_week_out_stability_failed": "移除单周后结果不稳定",
    "qualified_model_family_count_below_2": "通过全部门禁的独立产品族不足",
}


def build_product_value_realization_report(
    context: SellpointValueV4Context,
) -> SkuProductValueRealizationReport:
    """Build one immutable report; every renderer consumes this object."""

    links = build_reason_value_bundle_links(context)
    rows: list[ProductValueStructureRow] = []
    qa_relations: list[dict[str, Any]] = []
    for link in links:
        assessments = build_counterfactual_assessments(context, link)
        quantification = quantify_sellpoint_value(context, link, assessments)
        rows.append(
            _build_business_row(
                context,
                link=link,
                assessments=assessments,
                quantification=quantification,
            )
        )
        qa_relations.append(
            {
                "relation_hash": link.relation_hash,
                "purchase_reason_code": link.purchase_reason_code,
                "quantification_level": quantification.level,
                "counterfactuals": [
                    item.model_dump(mode="json") for item in assessments
                ],
            }
        )
    status = _analysis_status(context, links)
    boundary = _overall_boundary(rows)
    payload: dict[str, Any] = {
        "schema_version": "sellpoint_value_pm_v4_result_v1",
        "analysis_status": status,
        "target": context.target,
        "headline_cn": _headline_cn(context, rows),
        "value_structure_rows": rows,
        "overall_quantification_boundary": boundary,
        "data_scope_note_cn": (
            "本结果只使用已发布采购理由、产品事实、用户购后体验和实际市场量价；"
            "不推测购买前传播心智，也不把评论数量折算成金额。"
        ),
        "limitations": _report_limitations(context, rows),
        "qa_appendix": {
            "lineage_status": context.lineage_gate.status,
            "relation_count": len(rows),
            "relations": qa_relations,
            "source_authority": [
                item.model_dump(mode="json") for item in context.authority_manifest
            ],
        },
        "input_hash": context.input_hash,
    }
    return SkuProductValueRealizationReport(
        **payload,
        result_hash=canonical_v4_hash(payload),
    )


def build_product_value_answer_artifacts(
    report: SkuProductValueRealizationReport,
    *,
    with_report: str = "none",
    max_chat_chars: int = 700,
    report_title: str | None = None,
    selection_compare_url: str | None = None,
    evidence_report_url: str | None = None,
) -> dict[str, Any]:
    title = report_title or f"{_display_name(report)} 用户价值结构与市场兑现"
    initial_links = _report_links(
        selection_compare_url=selection_compare_url,
        evidence_report_url=evidence_report_url,
    )
    markdown = render_product_value_markdown(report, title=title, links=initial_links)
    markdown_path = (
        _write_markdown_report(title, markdown)
        if with_report in {"markdown", "feishu-doc"}
        else None
    )
    publish_result = _publish_report(
        title=title,
        markdown=markdown,
        with_report=with_report,
    )
    links = _report_links(
        selection_compare_url=selection_compare_url,
        evidence_report_url=evidence_report_url or publish_result.url,
    )
    short_answer = render_product_value_short_answer(
        report,
        links=links,
        max_chat_chars=max_chat_chars,
    )
    card = render_product_value_feishu_card(report, title=title, links=links)
    return {
        "report": report.model_dump(mode="json"),
        "short_answer": short_answer,
        "markdown": markdown if with_report == "markdown" else None,
        "markdown_path": markdown_path,
        "feishu_card_payload": card,
        "report_links": links,
        "report_delivery": publish_result.to_dict(),
        "report_title": title,
        "result_hash": report.result_hash,
    }


def render_product_value_short_answer(
    report: SkuProductValueRealizationReport,
    *,
    links: Sequence[dict[str, str]] = (),
    max_chat_chars: int = 700,
) -> str:
    lines = [report.headline_cn]
    for row in report.value_structure_rows[:3]:
        lines.append(
            f"{_battlefield_cn(row)}｜{_dict_text(row.purchase_reason, 'name_cn')}："
            f"{_dict_text(row.realized_user_value, 'status_cn')}；"
            f"{_market_realization_cn(row.selection_price_realization)}。"
        )
    lines.append(str(report.overall_quantification_boundary.get("summary_cn") or ""))
    link_lines = [
        f"{item['label']}：{item['url']}"
        for item in links
        if item.get("url", "").startswith("http")
    ]
    suffix = "\n".join(link_lines)
    body_limit = max_chat_chars - len(suffix) - (1 if suffix else 0)
    body = _compress("\n".join(item for item in lines if item), max(1, body_limit))
    return f"{body}\n{suffix}" if suffix else body


def render_product_value_markdown(
    report: SkuProductValueRealizationReport,
    *,
    title: str | None = None,
    links: Sequence[dict[str, str]] = (),
) -> str:
    title = title or f"{_display_name(report)} 用户价值结构与市场兑现"
    lines = [
        f"# {_md(title)}",
        "",
        f"> {_md(report.headline_cn)}",
        "",
        "## 一、这张价值账回答什么",
        "",
        "- 产品投入最终有没有形成用户实际感知到的价值；",
        "- 这项价值在同价值和较低价值产品面前，是否表现为选择差异；",
        "- 市场量价最多支持到整机承接，还是已达到可识别的市场隐含支付区间。",
        "",
        "## 二、SKU 产品价值结构与市场兑现",
        "",
        "| 价值战场及市场空间 | 本品核心采购理由 | 用户实际获得的价值 | 支撑卖点组合 | 相对基础与同价值竞品 | 选择和价格兑现 | 产品角色 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.value_structure_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(_battlefield_cn(row)),
                    _md(_dict_text(row.purchase_reason, "name_cn")),
                    _md(_realized_value_cn(row)),
                    _md(_bundle_cn(row)),
                    _md(_dict_text(row.counterfactual_result, "summary_cn")),
                    _md(_market_realization_cn(row.selection_price_realization)),
                    _md(ROLE_CN[row.product_role]),
                ]
            )
            + " |"
        )
    if not report.value_structure_rows:
        lines.append("| 当前没有可用价值关系 | — | — | — | — | — | 尚不能判断 |")
    lines.extend(
        [
            "",
            "这张表把“价值是否成立”和“价值能否量化”分开；无法量化不等于没有价值。",
            "",
            "## 三、卖点组合下钻",
            "",
        ]
    )
    for index, row in enumerate(report.value_structure_rows, start=1):
        lines.extend(
            [
                f"### {index}. {_md(_dict_text(row.purchase_reason, 'name_cn'))}",
                "",
                f"- **用户场景**：{_md(_dict_text(row.realized_user_value, 'scenario_cn'))}",
                f"- **用户实际价值**：{_md(_realized_value_cn(row))}",
                f"- **卖点组合**：{_md(_bundle_cn(row))}",
                f"- **反事实边界**：{_md(_dict_text(row.counterfactual_result, 'summary_cn'))}",
                f"- **选择和价格兑现**：{_md(_market_realization_cn(row.selection_price_realization))}",
                f"- **产品角色**：{_md(ROLE_CN[row.product_role])}",
                f"- **证据完整度**：{_md(row.confidence_label_cn)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 四、量化边界",
            "",
            f"- {_md(report.overall_quantification_boundary.get('summary_cn'))}",
            f"- {_md(report.data_scope_note_cn)}",
        ]
    )
    for limitation in report.limitations:
        lines.append(f"- {_md(limitation)}")
    visible_links = [item for item in links if item.get("url", "").startswith("http")]
    if visible_links:
        lines.extend(["", "## 五、关联报告", ""])
        for item in visible_links:
            lines.append(f"- [{_md(item['label'])}]({item['url']})")
    markdown = "\n".join(lines).strip() + "\n"
    issue = pm_business_output_issue(markdown)
    if issue:
        raise ValueError(issue)
    return markdown


def render_product_value_feishu_card(
    report: SkuProductValueRealizationReport,
    *,
    title: str | None = None,
    links: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    title = title or f"{_display_name(report)} 用户价值结构与市场兑现"
    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": report.headline_cn},
        {"tag": "hr"},
    ]
    for row in report.value_structure_rows[:3]:
        elements.append(
            {
                "tag": "markdown",
                "content": (
                    f"**{_battlefield_cn(row)}｜{_dict_text(row.purchase_reason, 'name_cn')}**\n"
                    f"用户价值：{_realized_value_cn(row)}\n"
                    f"市场兑现：{_market_realization_cn(row.selection_price_realization)}\n"
                    f"产品角色：{ROLE_CN[row.product_role]}"
                ),
            }
        )
    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": str(
                    report.overall_quantification_boundary.get("summary_cn") or ""
                ),
            },
        ]
    )
    for item in links:
        url = item.get("url", "")
        if not url.startswith("http"):
            continue
        elements.append(
            {
                "tag": "button",
                "element_id": f"open_{item['type']}",
                "type": "primary" if item["type"] == "selection_compare" else "default",
                "size": "medium",
                "width": "fill",
                "text": {"tag": "plain_text", "content": item["label"]},
                "behaviors": [
                    {
                        "type": "open_url",
                        "default_url": url,
                        "pc_url": url,
                        "ios_url": url,
                        "android_url": url,
                    }
                ],
            }
        )
    return {
        "schema": "2.0",
        "config": {
            "summary": {"content": title},
            "width_mode": "fill",
            "update_multi": True,
        },
        "header": {
            "template": "turquoise" if report.analysis_status == "ready" else "orange",
            "title": {"tag": "plain_text", "content": title},
        },
        "body": {"elements": elements},
    }


def pm_business_output_issue(text: str) -> str | None:
    forbidden = {
        r"\bM(?:0[0-9]|1[0-9])[A-Z]?\b": "主表包含内部模块码",
        r"\bQ[0-5](?:_|\b)": "主表包含内部量化等级",
        r"isolation(?:_grade)?": "主表包含内部隔离等级",
        r"evidence[_ -]?id": "主表包含证据 ID",
        r"\bSQL\b": "主表包含 SQL",
        r"建议(?:涨价|降价|增配|减配)": "主表包含数据未授权的产品动作",
        r"下一步工作清单": "主表包含通用工作清单",
        r"购买前用户(?:认为|觉得|理解)": "主表推测购买前心智",
    }
    for pattern, message in forbidden.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            return message
    return None


def _build_business_row(
    context: SellpointValueV4Context,
    *,
    link: ReasonValueBundleLink,
    assessments: Sequence[ComparabilityAssessment],
    quantification: QuantificationResult,
) -> ProductValueStructureRow:
    candidates = {item.identity.sku_code: item for item in context.candidate_snapshots}
    by_role = {
        role: [item for item in assessments if item.role == role]
        for role in ("base_value", "same_value", "stretch_benchmark")
    }
    return ProductValueStructureRow(
        battlefield={
            "name_cn": link.battlefield_name_cn or "当前价值战场",
            "market_space_cn": _market_space_cn(link.battlefield_market_space),
        },
        purchase_reason={
            "name_cn": link.purchase_reason_name_cn,
            "source_status_cn": "来自已发布的本品核心采购理由画像",
        },
        realized_user_value={
            "name_cn": link.realized_value_name_cn,
            "scenario_cn": link.scenario_cn,
            "outcome_cn": link.outcome_cn,
            "status_cn": VALUE_STATUS_CN[link.value_status],
        },
        sellpoint_bundle={
            "name_cn": link.bundle.bundle_name_cn,
            "tier_cn": TIER_CN[link.bundle.business_tier],
            "member_names_cn": [
                item.capability_name_cn for item in link.bundle.members
            ],
            "identification_boundary_cn": (
                "当前只能按组合判断，不能拆成单项金额"
                if link.bundle.collinearity_group
                else "当前组合具备独立判断条件"
            ),
        },
        counterfactual_result={
            "summary_cn": _counterfactual_summary(by_role),
            "base_value_products": _candidate_names(by_role["base_value"], candidates),
            "same_value_products": _candidate_names(by_role["same_value"], candidates),
            "stretch_products": _candidate_names(
                by_role["stretch_benchmark"], candidates
            ),
        },
        selection_price_realization=quantification,
        product_role=quantification.product_role,
        confidence_label_cn=_confidence_label(link, quantification),
        drilldown={
            "comparison_scope_cn": (
                "同尺寸、同价值战场、共同周和平台；促销疑似单元不进入主量化。"
            ),
            "inventory_boundary_cn": "库存状态不可得，结果没有声称控制库存。",
            "market_claim_boundary_cn": "市场结果是观察性关联，不是因果效应或心理最高价。",
        },
    )


def _analysis_status(
    context: SellpointValueV4Context,
    links: Sequence[ReasonValueBundleLink],
) -> str:
    if not links:
        return "blocked"
    if context.lineage_gate.status in {"stale_conflict", "unresolved"} or any(
        item.link_status == "conflicted" for item in links
    ):
        return "partial"
    return "ready"


def _overall_boundary(rows: Sequence[ProductValueStructureRow]) -> dict[str, Any]:
    established = sum(
        row.selection_price_realization.value_status == "established" for row in rows
    )
    choice = sum(
        row.selection_price_realization.choice_association is not None
        and row.selection_price_realization.choice_association.status == "available"
        for row in rows
    )
    wtp = sum(row.selection_price_realization.wtp.status == "available" for row in rows)
    if not rows:
        summary = "当前没有可用的采购理由—用户价值关系，不能形成用户价值账。"
    elif wtp:
        summary = (
            f"{established} 项用户价值已完整成立，{choice} 项观察到选择/整机价格兑现，"
            f"其中 {wtp} 项达到严格的市场隐含支付区间门禁。"
        )
    else:
        summary = (
            f"{established} 项用户价值已完整成立，{choice} 项观察到选择或整机价格兑现；"
            "当前没有任何一项达到严格的市场隐含支付区间门禁，金额保持为空。"
        )
    return {
        "summary_cn": summary,
        "row_count": len(rows),
        "established_value_count": established,
        "choice_available_count": choice,
        "market_implied_payment_available_count": wtp,
        "real_sku_amount_claim_policy_cn": "只有全部识别门禁通过才显示区间，否则不显示金额。",
    }


def _headline_cn(
    context: SellpointValueV4Context,
    rows: Sequence[ProductValueStructureRow],
) -> str:
    name = _display_name_from_identity(context.target)
    established = sum(
        row.selection_price_realization.value_status == "established" for row in rows
    )
    if not rows:
        return f"{name} 当前没有可用的用户价值关系，不能形成产品价值账。"
    return (
        f"{name} 共形成 {len(rows)} 笔“采购理由—用户实际价值—卖点组合”价值账，"
        f"其中 {established} 笔用户价值已完整被观察；选择与价格结果按各自行显示，"
        "无法量化不会被写成没有价值。"
    )


def _report_limitations(
    context: SellpointValueV4Context,
    rows: Sequence[ProductValueStructureRow],
) -> list[str]:
    values = [
        "现有用户证据来自购买后体验，不回答购买前宣传让用户形成了什么心智。",
        "库存状态不可得；促销只有疑似标记，不能声称已完全控制。",
        "市场隐含支付区间只代表观察性市场承接，不代表用户心理最高价。",
    ]
    if context.lineage_gate.status in {"stale_conflict", "unresolved"}:
        values.append("部分事实版本存在冲突，受影响的价格归因已暂停。")
    if any(
        row.sellpoint_bundle.get("identification_boundary_cn", "").startswith(
            "当前只能"
        )
        for row in rows
    ):
        values.append("共同变化的卖点只按组合判断，不拆分单项金额。")
    return _dedupe_texts(values)


def _counterfactual_summary(
    by_role: dict[str, list[ComparabilityAssessment]],
) -> str:
    parts: list[str] = []
    base = by_role["base_value"]
    same = by_role["same_value"]
    stretch = by_role["stretch_benchmark"]
    if base:
        eligible = sum(item.eligible for item in base)
        parts.append(
            f"找到 {len(base)} 个较低价值档候选，其中 {eligible} 个可进入市场比较"
        )
    else:
        parts.append("没有较低价值档对照，无法识别本品增量价值")
    if same:
        parts.append(f"{len(same)} 个同价值对照只用于观察选择差异")
    if stretch:
        parts.append(f"{len(stretch)} 个更高价值标杆只用于观察上探位置")
    return "；".join(parts) + "。"


def _candidate_names(
    assessments: Sequence[ComparabilityAssessment],
    candidates: dict[str, Any],
) -> list[str]:
    result: list[str] = []
    for item in assessments:
        snapshot = candidates.get(item.candidate_sku_code)
        if snapshot is None:
            result.append(item.candidate_sku_code)
        else:
            result.append(_display_name_from_identity(snapshot.identity))
    return result


def _confidence_label(
    link: ReasonValueBundleLink,
    quantification: QuantificationResult,
) -> str:
    if link.value_status == "conflicted":
        return "用户体验正反并存，市场量化已暂停"
    if quantification.wtp.status == "blocked":
        return "存在事实冲突，受影响判断已暂停"
    if link.value_status == "established" and quantification.wtp.status == "available":
        return "用户价值和市场量价证据均通过严格门禁"
    if link.value_status == "established":
        return "用户价值证据完整，市场量化按当前样本边界输出"
    if link.value_status == "partial":
        return "用户只感知到部分价值"
    return "尚未观察到用户实际价值"


def _market_realization_cn(quantification: QuantificationResult) -> str:
    choice = quantification.choice_association
    wtp = quantification.wtp
    if wtp.status == "available":
        share = (
            f"同价条件销量份额约 {float(choice.same_price_choice_share) * 100:.1f}%；"
            if choice and choice.same_price_choice_share is not None
            else ""
        )
        return (
            f"{share}观察到的市场隐含支付区间约 {float(wtp.estimate_low):.0f}-"
            f"{float(wtp.estimate_high):.0f} 元；这是市场关联，不是心理最高价"
        )
    if choice is not None and choice.status == "available":
        share = float(choice.same_price_choice_share or 0) * 100
        state = _acceptance_state_cn(quantification.whole_product_price_acceptance)
        return (
            f"同价条件销量份额约 {share:.1f}%，{state}；"
            f"支付区间未识别：{_wtp_boundary_cn(wtp.exclusion_reasons)}"
        )
    if quantification.relative_experience is not None:
        return (
            "购后体验具备可比基础；市场选择或价格样本不足，"
            f"支付区间未识别：{_wtp_boundary_cn(wtp.exclusion_reasons)}"
        )
    if quantification.value_status == "not_observed":
        return "用户实际价值尚未观察到，不能进入卖点选择和价格量化"
    if quantification.value_status == "conflicted":
        return "用户实际体验存在冲突，不能进入卖点选择和价格量化"
    return "用户价值已观察，但缺少可比购后体验和市场对照，金额保持为空"


def _wtp_boundary_cn(reasons: Sequence[str]) -> str:
    translated = [WTP_EXCLUSION_CN.get(item) for item in reasons]
    return "；".join(item for item in translated if item) or "当前样本未通过严格门禁"


def _acceptance_state_cn(value: dict[str, Any] | None) -> str:
    state = str((value or {}).get("acceptance_state") or "")
    return {
        "advantage_remains": "当前整机价格下仍观察到选择优势",
        "market_balance": "当前整机价格已接近市场均衡",
        "price_pressure": "当前整机价格下观察到选择压力",
    }.get(state, "当前整机价格承接可观察")


def _battlefield_cn(row: ProductValueStructureRow) -> str:
    name = _dict_text(row.battlefield, "name_cn")
    space = _dict_text(row.battlefield, "market_space_cn")
    return f"{name}（{space}）" if space and space != "市场空间暂不可量化" else name


def _market_space_cn(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict) or not value:
        return "市场空间暂不可量化"
    amount = next(
        (
            value.get(key)
            for key in (
                "estimated_market_sales_amount",
                "estimated_sales_amount",
                "sales_amount",
            )
            if value.get(key) is not None
        ),
        None,
    )
    volume = next(
        (
            value.get(key)
            for key in (
                "estimated_market_sales_volume",
                "estimated_sales_volume",
                "sales_volume",
            )
            if value.get(key) is not None
        ),
        None,
    )
    parts: list[str] = []
    if amount is not None:
        amount_value = float(amount)
        parts.append(
            f"估算销额约 {amount_value / 100_000_000:.2f} 亿元"
            if amount_value >= 100_000_000
            else f"估算销额约 {amount_value / 10_000:.0f} 万元"
        )
    if volume is not None:
        parts.append(f"估算销量约 {float(volume):,.0f} 台")
    return "，".join(parts) or "市场空间暂不可量化"


def _realized_value_cn(row: ProductValueStructureRow) -> str:
    status = _dict_text(row.realized_user_value, "status_cn")
    outcome = _dict_text(row.realized_user_value, "outcome_cn")
    return f"{status}：{outcome}" if outcome else status


def _bundle_cn(row: ProductValueStructureRow) -> str:
    names = [str(item) for item in row.sellpoint_bundle.get("member_names_cn") or []]
    tier = _dict_text(row.sellpoint_bundle, "tier_cn")
    boundary = _dict_text(row.sellpoint_bundle, "identification_boundary_cn")
    return f"{'＋'.join(names) or _dict_text(row.sellpoint_bundle, 'name_cn')}（{tier}；{boundary}）"


def _report_links(
    *,
    selection_compare_url: str | None,
    evidence_report_url: str | None,
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if selection_compare_url:
        result.append(
            {
                "label": "查看用户选择对比",
                "url": selection_compare_url,
                "type": "selection_compare",
            }
        )
    if evidence_report_url:
        result.append(
            {
                "label": "查看分析依据",
                "url": evidence_report_url,
                "type": "evidence_report",
            }
        )
    return result


def _write_markdown_report(title: str, markdown: str) -> str:
    root = Path(tempfile.gettempdir()) / "catforge_analyst_reports"
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", title).strip("-")[:80]
    path = root / f"{timestamp}-{slug or 'sellpoint-value-v4'}.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def _display_name(report: SkuProductValueRealizationReport) -> str:
    return _display_name_from_identity(report.target)


def _display_name_from_identity(identity: Any) -> str:
    brand = str(getattr(identity, "brand_name", "") or "").strip()
    model = str(getattr(identity, "model_name", "") or "").strip()
    sku = str(getattr(identity, "sku_code", "") or "目标产品").strip()
    return " ".join(item for item in (brand, model) if item) or sku


def _dict_text(value: dict[str, Any], key: str) -> str:
    return str(value.get(key) or "").strip()


def _md(value: Any) -> str:
    return str(value or "—").replace("|", "\\|").replace("\n", " ")


def _compress(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _dedupe_texts(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


__all__ = [
    "build_product_value_answer_artifacts",
    "build_product_value_realization_report",
    "pm_business_output_issue",
    "render_product_value_feishu_card",
    "render_product_value_markdown",
    "render_product_value_short_answer",
]
