"""Product-manager report assembly and renderers for sellpoint-value V5."""

from __future__ import annotations

import re
from statistics import median
import tempfile
from pathlib import Path
from typing import Any, Sequence

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    ReasonValueBundleLink,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    _value_unit_by_code,
    build_counterfactual_assessments,
    build_reason_value_bundle_links,
    quantify_sellpoint_value,
)
from app.services.core3_real_data.analyst.claim_value_pm_category_config import AC_BATTLEFIELD_CN
from app.services.core3_real_data.analyst.claim_value_pm_v5_counterfactuals import (
    build_v5_counterfactual_sets,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_realization import (
    build_realization_accounting,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldAllocation,
    BattlefieldDefinitionSnapshot,
    BattlefieldPortfolioInput,
    CounterfactualSet,
    MethodConfigManifest,
    PerformanceArchetype,
    PmDecisionSummary,
    PriceRealization,
    RealizationMarketComparison,
    RealizationAccountingInput,
    SellpointValueV5Context,
    SkuPerceivedValueMarketRealizationReport,
    SyntheticControlResult,
    ValueAccountRow,
    ValueHighlight,
    VolumeRealization,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_service import (
    build_battlefield_portfolio_options,
    build_market_synthetic_control,
    build_performance_archetypes,
)
from app.services.core3_real_data.analyst.competitor_answer import (
    CLAIM_LABELS_CN,
    _publish_report,
)


VALUE_STATUS_CN = {
    "observed_positive": "用户已稳定感知到具体好处",
    "observed_mixed": "不同用户或场景的感知正反并存",
    "observed_negative": "用户实际感知以负向结果为主",
    "partial": "用户只感知到部分好处",
    "not_observed": "现有购后证据尚未观察到这项好处",
    "conflicted": "来源冲突，当前不能形成稳定判断",
    "unknown": "现有证据不足以判断",
}
MEMBERSHIP_CN = {
    "primary": "核心用户价值",
    "secondary": "辅助用户价值",
    "opportunity": "待验证用户价值（本品已覆盖）",
    "user_observed": "用户实际认可的价值",
    "drag": "用户负面体验",
    "excluded": "本品尚未覆盖的用户价值",
}
METHOD_CN = {
    "direct_sku": "直接竞品",
    "same_budget_pool": "同预算产品",
    "same_brand_size_ladder": "同品牌同尺寸梯度",
    "param_tier_pool": "参数档位产品",
    "same_claim_realization": "同类卖点产品用户评价对比",
    "own_price_curve": "本品历史价格变化",
    "market_synthetic": "市场合成基线",
    "performance_archetype": "高低表现组合",
}
STRENGTHEN_CN = {
    "communication_activation": "表达激活",
    "capability_completion": "能力补全",
    "market_activation": "市场表现验证",
    "portfolio_priority": "组合优先级调整",
    "maintain_or_cap": "保持或控制重叠",
}
TV_BATTLEFIELD_CN = {
    "BF_SMALL_SCREEN_ESSENTIAL_VALUE": "小屏基础实用",
    "BF_SMALL_SMART_EASY_USE": "小屏智能易用",
    "BF_MAINSTREAM_FAMILY_VALUE": "主流家庭性价比",
    "BF_MAINSTREAM_LIVING_BALANCE": "主流客厅均衡体验",
    "BF_LARGE_SCREEN_VALUE_UPGRADE": "大屏价值升级",
    "BF_LARGE_SCREEN_FAMILY_CINEMA": "大屏家庭影院",
    "BF_PREMIUM_PICTURE_UPGRADE": "高端画质升级",
    "BF_PREMIUM_VALUE_DOWNTRADE": "高端价值下探",
    "BF_GAMING_SPORTS_FLUENCY": "游戏与体育流畅",
    "BF_EYE_CARE_FAMILY_COMFORT": "家庭护眼舒适",
    "BF_SMART_CONNECTED_EXPERIENCE": "智能互联体验",
    "BF_GIANT_SCREEN_VALUE_DOWNTRADE": "巨幕价值下探",
    "BF_GIANT_HOME_THEATER_FLAGSHIP": "巨幕家庭影院旗舰",
}
ALL_BATTLEFIELD_CN = {**TV_BATTLEFIELD_CN, **AC_BATTLEFIELD_CN}


def adapt_v4_context_to_v5(v4_context: SellpointValueV4Context) -> SellpointValueV5Context:
    """Reuse the immutable V4 evidence context without querying another source."""

    universe = [v4_context.target_snapshot, *v4_context.candidate_snapshots]
    by_code = {row.identity.sku_code: row for row in universe}
    ordered = [by_code[code] for code in sorted(by_code)]
    battlefield_names: dict[str, str] = dict(
        AC_BATTLEFIELD_CN if v4_context.category_code == "AC" else TV_BATTLEFIELD_CN
    )
    for snapshot in ordered:
        for item in snapshot.semantic_market:
            code = str(item.get("dimension_code") or "").strip()
            if code and _is_battlefield_semantic(item):
                battlefield_names.setdefault(
                    code, str(item.get("dimension_name") or ALL_BATTLEFIELD_CN.get(code) or "")
                )
        for item in snapshot.battlefields:
            for code in _entered_codes(item):
                battlefield_names.setdefault(code, ALL_BATTLEFIELD_CN.get(code, ""))
    taxonomy = [
        BattlefieldDefinitionSnapshot(
            battlefield_code=code,
            battlefield_name_cn=name,
            source_hash=canonical_v4_hash({"code": code, "name": name}),
        )
        for code, name in sorted(battlefield_names.items())
    ]
    payload = {
        "schema_version": "sellpoint_value_v5_context_v1",
        "project_id": v4_context.project_id,
        "category_code": v4_context.category_code,
        "v4_context": v4_context,
        "market_universe": ordered,
        "battlefield_taxonomy": taxonomy,
        "method_configs": MethodConfigManifest(
            recall_version="sellpoint_value_pm_v5_counterfactual_recall_v2",
            synthetic_version="sellpoint_value_pm_v5_synthetic_control_v2",
            archetype_version="sellpoint_value_pm_v5_performance_archetype_v2",
            expansion_version="sellpoint_value_pm_v5_expansion_gate_v1",
            amount_version="sellpoint_value_pm_v4_matched_wtp_config_v2",
        ),
        "source_authorities": v4_context.authority_manifest,
        "evidence_refs": v4_context.evidence_refs,
    }
    return SellpointValueV5Context(
        **payload,
        input_hash=canonical_v4_hash(
            {
                "v4_input_hash": v4_context.input_hash,
                "market_universe": [row.snapshot_hash for row in ordered],
                "taxonomy": [row.model_dump(mode="json") for row in taxonomy],
            }
        ),
    )


def build_perceived_value_market_report(
    context: SellpointValueV5Context,
) -> SkuPerceivedValueMarketRealizationReport:
    """Build the single business DTO consumed by every V5 renderer."""

    links = build_reason_value_bundle_links(context.v4_context)
    rows: list[ValueAccountRow] = []
    synthetic_by_bundle: dict[str, SyntheticControlResult] = {}
    comparison_catalog: list[dict[str, Any]] = []
    qa_relations: list[dict[str, Any]] = []
    allocations = _battlefield_allocations(context)
    for link in links:
        focus_dimensions = [member.capability_code for member in link.bundle.members]
        focus_claims = _bundle_claim_codes(link, context.category_code)
        sets = build_v5_counterfactual_sets(
            context,
            bundle_code=link.bundle.bundle_code,
            focus_dimension_codes=focus_dimensions,
            focus_claim_codes=focus_claims,
        )
        synthetic = _synthetic_for_bundle(context, link.bundle.bundle_code, sets)
        synthetic_by_bundle[link.bundle.bundle_code] = synthetic
        value_status = _v5_value_status(link)
        all_realization_comparisons = (
            _realization_market_comparisons(context, sets)
            if value_status in {"observed_positive", "partial"}
            else []
        )
        realization_comparisons = [
            item
            for item in all_realization_comparisons
            if item.method == "same_claim_different_realization"
        ]
        comparison_catalog.append(
            {
                "value_name_cn": link.realized_value_name_cn
                or link.purchase_reason_name_cn,
                "value_status": value_status,
                "bundle": link.bundle,
                "comparisons": all_realization_comparisons,
            }
        )
        v4_assessments = build_counterfactual_assessments(context.v4_context, link)
        quantification = quantify_sellpoint_value(
            context.v4_context,
            link,
            v4_assessments,
        )
        accounting = build_realization_accounting(
            RealizationAccountingInput(
                current_price=_market_number(context, "price_wavg", "avg_price"),
                current_sales_volume=_market_number(
                    context, "sales_volume_total", "sales_volume"
                ),
                price_percentile=_market_fraction(
                    context, "same_pool_price_percentile", "price_percentile"
                ),
                volume_percentile=_market_fraction(
                    context, "same_pool_volume_percentile", "volume_percentile"
                ),
                amount_percentile=_market_fraction(
                    context, "same_pool_amount_percentile", "amount_percentile"
                ),
                direct_and_pool_gaps=[
                    item.model_dump(mode="json") for item in realization_comparisons
                ],
                own_price_curve=None,
                controlled_residual=None,
                choice_association=(
                    quantification.choice_association.model_dump(mode="json")
                    if quantification.choice_association is not None
                    else None
                ),
                synthetic_control=synthetic,
                battlefield_allocations=allocations,
                cannibalization=None,
                overlap_risk="unknown",
                strict_market_wtp=quantification.wtp,
                realization_comparisons=realization_comparisons,
                limitations=[],
            )
        )
        row_allocation = next(
            (item for item in allocations if item.battlefield_code == link.battlefield_code),
            None,
        )
        rows.append(
            ValueAccountRow(
                battlefield={
                    "code": link.battlefield_code,
                    "name_cn": _business_value_name(
                        link.battlefield_name_cn
                        or ALL_BATTLEFIELD_CN.get(link.battlefield_code)
                        or "未命名用户价值"
                    ),
                    "membership_cn": _membership_cn(context, link.battlefield_code),
                    "market_space": link.battlefield_market_space or {},
                },
                perceived_user_value={
                    "name_cn": link.realized_value_name_cn or link.purchase_reason_name_cn,
                    "scenario_cn": link.scenario_cn,
                    "outcome_cn": link.outcome_cn,
                    "status_cn": VALUE_STATUS_CN[value_status],
                },
                sellpoint_bundle=_pm_bundle(link.bundle),
                value_status=value_status,
                highlight_types=_eligible_highlight_types(
                    value_status, sets, accounting, synthetic
                ),
                counterfactual_sets=_pm_counterfactual_sets(sets),
                counterfactual_summary_cn=_counterfactual_summary_cn(
                    sets, realization_comparisons
                ),
                price_realization=accounting.price,
                volume_realization=accounting.volume,
                battlefield_allocation=row_allocation,
                increment=accounting.increment,
                boundary_cn=_row_boundary_cn(value_status, accounting.price, accounting.volume),
                confidence_label_cn=_confidence_cn(value_status, sets),
                limitations=sorted(
                    set([*link.limitations, *accounting.limitations])
                ),
                source_refs=[],
            )
        )
        qa_relations.append(
            {
                "relation_hash": link.relation_hash,
                "accounting_hash": accounting.result_hash,
                "counterfactual_set_hashes": [item.set_hash for item in sets],
                "synthetic_hash": synthetic.result_hash,
            }
        )
    rows.sort(
        key=lambda row: (
            -len(row.highlight_types),
            str(row.battlefield.get("name_cn") or ""),
            row.sellpoint_bundle.bundle_code,
        )
    )
    rows = _dedupe_value_account_rows(rows)
    archetypes = build_performance_archetypes(
        context,
        bundle_codes=[row.sellpoint_bundle.bundle_code for row in rows],
    )
    options = build_battlefield_portfolio_options(
        context,
        _portfolio_inputs(context, links, allocations),
    )
    analysis_state = _analysis_state(context, rows)
    highlights = [] if analysis_state == "blocked" else _select_highlights(rows)
    decision = PmDecisionSummary(
        highlights=highlights,
        no_highlight_reason_cn=(
            None
            if highlights
            else _no_highlight_reason_cn(context, analysis_state)
        ),
        price_summary_cn=_overall_price_summary(rows),
        volume_summary_cn=_overall_volume_summary(rows),
        existing_battlefield_summary_cn=_existing_summary(options, context),
        expansion_summary_cn=_expansion_summary(options, context),
    )
    market_reference = _market_reference_cn(
        context,
        rows,
        synthetic_by_bundle,
        archetypes,
        comparison_catalog,
    )
    payload: dict[str, Any] = {
        "schema_version": "sellpoint_value_pm_v5_report_v1",
        "target": context.v4_context.target,
        "analysis_state": analysis_state,
        "decision_summary": decision,
        "value_account_rows": rows,
        "market_reference": market_reference,
        "battlefield_options": options,
        "overall_boundary_cn": (
            "本报告从用户实际体验出发，通过同类卖点产品的价格和销量差异判断"
            "哪些卖点已经产生商业价值；无法形成有效比较的项目不进入主结论。"
        ),
        "data_scope_cn": (
            "使用已发布采购理由、产品事实、用户购后体验、周度市场量价和当前用户价值分配；"
            "不推断购买前传播心智，不使用成本或利润数据。"
        ),
        "audit": {
            "input_hash": context.input_hash,
            "v4_input_hash": context.v4_context.input_hash,
            "method_configs": context.method_configs.model_dump(mode="json"),
            "relations": qa_relations,
        },
    }
    return SkuPerceivedValueMarketRealizationReport(
        **payload,
        result_hash=canonical_v4_hash(payload),
    )


def build_v5_answer_artifacts(
    report: SkuPerceivedValueMarketRealizationReport,
    *,
    with_report: str = "none",
    max_chat_chars: int = 900,
    report_title: str | None = None,
    selection_compare_url: str | None = None,
    evidence_report_url: str | None = None,
) -> dict[str, Any]:
    title = report_title or f"{_display_name(report)} 用户卖点价值分析"
    initial_links = _report_links(selection_compare_url, evidence_report_url)
    markdown = render_v5_markdown(report, title=title, links=initial_links)
    markdown_path = (
        _write_markdown_report(title, markdown)
        if with_report in {"markdown", "feishu-doc"}
        else None
    )
    delivery = _publish_report(title=title, markdown=markdown, with_report=with_report)
    links = _report_links(selection_compare_url, evidence_report_url or delivery.url)
    return {
        "report_ref": {
            "schema_version": report.schema_version,
            "result_hash": report.result_hash,
        },
        "short_answer": render_v5_short_answer(
            report, links=links, max_chat_chars=max_chat_chars
        ),
        "markdown": markdown if with_report == "markdown" else None,
        "markdown_path": markdown_path,
        "feishu_card_payload": render_v5_feishu_card(report, title=title, links=links),
        "report_links": links,
        "report_delivery": delivery.to_dict(),
        "report_title": title,
        "result_hash": report.result_hash,
    }


def render_v5_short_answer(
    report: SkuPerceivedValueMarketRealizationReport,
    *,
    links: Sequence[dict[str, str]] = (),
    max_chat_chars: int = 900,
) -> str:
    lines = [f"{_display_name(report)} 用户价值账"]
    if report.decision_summary.highlights:
        for index, item in enumerate(report.decision_summary.highlights, start=1):
            lines.append(f"亮点{index}｜{item.title_cn}：{item.reason_cn}")
    else:
        lines.append(report.decision_summary.no_highlight_reason_cn or "")
    if _has_reportable_price(report.value_account_rows):
        lines.append(f"卖贵多少｜{report.decision_summary.price_summary_cn}")
    if _has_reportable_volume(report.value_account_rows):
        lines.append(f"多卖多少｜{report.decision_summary.volume_summary_cn}")
    for item in report.market_reference.get("question_driven_comparisons", []):
        question = str(item.get("question_cn") or "产品比较")
        conclusion = str(item.get("conclusion_cn") or "")
        if conclusion:
            lines.append(f"{question}｜{conclusion}")
    lines.extend(
        [
            f"产品取舍｜{report.decision_summary.existing_battlefield_summary_cn}",
            f"新增价值机会｜{report.decision_summary.expansion_summary_cn}",
        ]
    )
    suffix = "\n".join(
        f"{item['label']}：{item['url']}"
        for item in links
        if item.get("url", "").startswith("http")
    )
    body_limit = max_chat_chars - len(suffix) - (1 if suffix else 0)
    body = _compress("\n".join(item for item in lines if item), max(1, body_limit))
    return f"{body}\n{suffix}" if suffix else body


def render_v5_markdown(
    report: SkuPerceivedValueMarketRealizationReport,
    *,
    title: str | None = None,
    links: Sequence[dict[str, str]] = (),
) -> str:
    title = title or f"{_display_name(report)} 用户卖点价值分析"
    lines = [f"# {_md(title)}", "", "## 一、核心结论", ""]
    if report.decision_summary.highlights:
        for index, item in enumerate(report.decision_summary.highlights, start=1):
            lines.extend(
                [
                    f"### 亮点 {index}：{_md(item.title_cn)}",
                    "",
                    f"- {_md(item.reason_cn)}",
                    f"- 对照依据：{_md(item.comparison_basis_cn)}",
                    f"- 结论边界：{_md(item.evidence_boundary_cn)}",
                    "",
                ]
            )
    else:
        lines.extend([report.decision_summary.no_highlight_reason_cn or "", ""])
    if _has_reportable_price(report.value_account_rows):
        lines.append(f"- **卖贵多少**：{_md(report.decision_summary.price_summary_cn)}")
    if _has_reportable_volume(report.value_account_rows):
        lines.append(f"- **多卖多少**：{_md(report.decision_summary.volume_summary_cn)}")
    lines.extend(
        [
            f"- **产品取舍**：{_md(report.decision_summary.existing_battlefield_summary_cn)}",
            f"- **新增价值机会**：{_md(report.decision_summary.expansion_summary_cn)}",
            "",
            "## 二、用户价值与市场表现",
            "",
            "| 用户价值 | 用户实际怎么感知 | 哪些卖点共同形成 | 对比哪些同类产品 | 带来多少价格溢价 | 带来多少销量优势 | 产品判断 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.value_account_rows:
        value = row.perceived_user_value
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(str(value.get("name_cn") or "尚未形成具体用户价值")),
                    _md(_perceived_value_cn(row)),
                    _md(_bundle_cn(row)),
                    _md(row.counterfactual_summary_cn),
                    _md(_price_cn(row.price_realization)),
                    _md(_volume_cn(row.volume_realization)),
                    _md(row.boundary_cn),
                ]
            )
            + " |"
        )
    if not report.value_account_rows:
        lines.append("| 当前没有可用价值关系 | — | — | — | — | — | 当前证据不足 |")
    market_reference_lines = _market_reference_markdown_lines(report.market_reference)
    if market_reference_lines:
        lines.extend(["", "## 三、同类产品表现", "", *market_reference_lines])
    lines.extend(
        [
            "",
            "## 四、产品价值取舍",
            "",
            "| 已有用户价值 | 产品判断 | 新增用户价值 | 产品判断 |",
            "| --- | --- | --- | --- |",
        ]
    )
    existing = [row for row in report.battlefield_options if row.option_type == "strengthen_existing"]
    expansion = [
        row
        for row in report.battlefield_options
        if row.option_type == "expand_excluded"
        and row.expansion_eligibility is not None
        and row.expansion_eligibility.stage != "rejected"
    ]
    width = max(len(existing), len(expansion), 1)
    for index in range(width):
        left = existing[index] if index < len(existing) else None
        right = expansion[index] if index < len(expansion) else None
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(_option_name(left, report) if left else "—"),
                    _md(_option_summary(left) if left else "—"),
                    _md(_option_name(right, report) if right else "—"),
                    _md(_option_summary(right) if right else "—"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 五、证据边界",
            "",
            f"- {_md(report.overall_boundary_cn)}",
            f"- {_md(report.data_scope_cn)}",
        ]
    )
    for item in links:
        if item.get("url", "").startswith("http"):
            lines.append(f"- [{_md(item['label'])}]({item['url']})")
    return "\n".join(lines).strip() + "\n"


def _market_reference_markdown_lines(market_reference: dict[str, Any]) -> list[str]:
    baselines = market_reference.get("synthetic_baselines", [])
    by_summary: dict[str, list[str]] = {}
    for item in baselines:
        summary = str(item.get("summary_cn") or "").strip()
        name = str(item.get("bundle_name_cn") or "").strip()
        if summary and not summary.startswith("当前"):
            by_summary.setdefault(summary, []).append(name)
    lines = []
    for summary, names in by_summary.items():
        if len(names) == 1:
            label = names[0] or "同类产品市场基准"
        else:
            label = f"同类产品市场基准（覆盖 {len(names)} 组用户价值）"
        lines.append(f"- **{_md(label)}**：{_md(summary)}")

    high = str((market_reference.get("high_performance") or {}).get("summary_cn") or "")
    low = str((market_reference.get("low_performance") or {}).get("summary_cn") or "")
    if not (high.startswith("当前样本不足") and low.startswith("当前样本不足")):
        lines.extend(
            [
                f"- **高表现组合**：{_md(high)}",
                f"- **低表现组合**：{_md(low)}",
            ]
        )
    differences = market_reference.get("performance_value_differences") or []
    if differences:
        high_values = [
            f"{item['value_name_cn']}（高销量组{item['high_rate'] * 100:.0f}% / "
            f"低销量组{item['low_rate'] * 100:.0f}%）"
            for item in differences
            if item.get("direction") == "high"
        ]
        low_values = [
            f"{item['value_name_cn']}（高销量组{item['high_rate'] * 100:.0f}% / "
            f"低销量组{item['low_rate'] * 100:.0f}%）"
            for item in differences
            if item.get("direction") == "low"
        ]
        if high_values:
            lines.append(f"- **高销量产品更常具备**：{_md('、'.join(high_values))}")
        if low_values:
            lines.append(f"- **低销量产品更常具备**：{_md('、'.join(low_values))}")
    for item in market_reference.get("question_driven_comparisons", []):
        lines.append(
            f"- **{_md(str(item.get('question_cn') or '产品比较'))}**："
            f"{_md(str(item.get('conclusion_cn') or ''))}"
        )
    return lines


def _performance_comparison_summary(market_reference: dict[str, Any]) -> str:
    high = str((market_reference.get("high_performance") or {}).get("summary_cn") or "")
    low = str((market_reference.get("low_performance") or {}).get("summary_cn") or "")
    if not high or not low or high.startswith("当前样本不足"):
        return ""
    differences = market_reference.get("performance_value_differences") or []
    high_values = _value_themes(differences, direction="high")
    low_values = _value_themes(differences, direction="low")
    shared_values = high_values & low_values
    high_values -= shared_values
    low_values -= shared_values
    clauses = [high.rstrip("。"), low.rstrip("。")]
    if high_values:
        clauses.append(f"高销量组更突出{'、'.join(sorted(high_values))}")
    if low_values:
        clauses.append(f"低销量组更集中于{'、'.join(sorted(low_values))}")
    high_price = (market_reference.get("high_performance") or {}).get("price_median")
    low_price = (market_reference.get("low_performance") or {}).get("price_median")
    if low_values and high_price is not None and low_price is not None and low_price > high_price:
        clauses.append(
            "结合低销量组价格中位数更高，这些价值组合更像高价定位，"
            "不能直接当作走量配方"
        )
    return "；".join(clauses)


def _value_themes(
    differences: Sequence[dict[str, Any]], *, direction: str
) -> set[str]:
    result: set[str] = set()
    labels = (
        ("画质升级感", "画质升级"),
        ("客厅沉浸感", "客厅沉浸"),
        ("动态画面稳定感", "动态画面"),
        ("游戏操控顺滑感", "游戏操控"),
        ("日常使用省心感", "日常易用"),
    )
    for item in differences:
        if item.get("direction") != direction:
            continue
        name = str(item.get("value_name_cn") or "")
        matched = False
        for token, label in labels:
            if token in name:
                result.add(label)
                matched = True
        if name and not matched:
            result.add(name)
    return result


def render_v5_feishu_card(
    report: SkuPerceivedValueMarketRealizationReport,
    *,
    title: str | None = None,
    links: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    title = title or f"{_display_name(report)} 用户卖点价值分析"
    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": render_v5_short_answer(report, max_chat_chars=1200),
        }
    ]
    for item in links:
        if item.get("url", "").startswith("http"):
            elements.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": item["label"]},
                    "type": "primary" if item.get("type") == "selection_compare" else "default",
                    "url": item["url"],
                }
            )
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "body": {"elements": elements},
    }


def pm_v5_business_output_issue(text: str) -> str | None:
    forbidden = {
        "M11C": "内部模块码",
        "M11D": "内部模块码",
        "M12C": "旧量化模块码",
        "M12D": "内部模块码",
        "evidence_id": "内部证据字段",
        "BF_": "内部战场编码",
        "WTP": "内部方法术语",
        "反事实": "分析过程术语",
        "用户兑现": "分析过程术语",
        "市场隐含支付意愿": "分析过程术语",
        "价格承接": "分析过程术语",
        "销量承接": "分析过程术语",
        "战场": "内部分析框架术语",
        "门槛": "内部分析框架术语",
        "任务相邻": "内部分析框架术语",
        "心理最高价": "不支持的支付表述",
        "增加销量": "因果销量表述",
        "下一步工作清单": "泛化任务清单",
        "建议涨价": "自动定价指令",
        "建议降价": "自动定价指令",
        "建议增配": "自动增配指令",
        "建议减配": "自动减配指令",
    }
    for token, issue in forbidden.items():
        if token in text:
            return f"{issue}: {token}"
    return None


def _synthetic_for_bundle(
    context: SellpointValueV5Context,
    bundle_code: str,
    sets: Sequence[CounterfactualSet],
) -> SyntheticControlResult:
    baseline = next(row for row in sets if row.question == "without_value_baseline")
    candidate = next(
        (row for row in baseline.candidates if row.method == "market_synthetic"),
        None,
    )
    if candidate is None:
        from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import CounterfactualCandidate

        candidate = CounterfactualCandidate(
            method="market_synthetic",
            question="without_value_baseline",
            stage="rejected",
            candidate_key=f"market_synthetic:{bundle_code}:empty",
            candidate_sku_codes=[],
            provenance="market_universe_broad_recall",
            control_dimensions={"balanced": False},
            reject_reasons=["broad_donor_pool_insufficient"],
        )
    return build_market_synthetic_control(context, candidate, bundle_code=bundle_code)


def _pm_counterfactual_sets(
    sets: Sequence[CounterfactualSet],
) -> list[CounterfactualSet]:
    """Strip evidence payloads already represented by hashes in the PM DTO."""

    return [
        row.model_copy(
            update={
                "candidates": [
                    candidate.model_copy(update={"source_refs": []})
                    for candidate in row.candidates
                ]
            }
        )
        for row in sets
    ]


def _pm_bundle(bundle):
    return bundle.model_copy(
        update={
            "members": [
                member.model_copy(update={"source_refs": []})
                for member in bundle.members
            ]
        }
    )


def _dedupe_value_account_rows(
    rows: Sequence[ValueAccountRow],
) -> list[ValueAccountRow]:
    """Keep one account per battlefield and observable capability combination."""

    result: list[ValueAccountRow] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for row in rows:
        key = (
            str(row.battlefield.get("code") or ""),
            tuple(
                sorted(
                    member.capability_code for member in row.sellpoint_bundle.members
                )
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        value = dict(row.perceived_user_value)
        name = str(value.get("name_cn") or "")
        value["name_cn"] = "＋".join(
            sorted({part.strip() for part in name.split("＋") if part.strip()})
        ) or name
        result.append(row.model_copy(update={"perceived_user_value": value}))
    return result


def _battlefield_allocations(context: SellpointValueV5Context) -> list[BattlefieldAllocation]:
    result = []
    for item in context.v4_context.target_snapshot.semantic_market:
        code = str(item.get("dimension_code") or "").strip()
        if not code or not _is_battlefield_semantic(item):
            continue
        result.append(
            BattlefieldAllocation(
                battlefield_code=code,
                allocated_sales_volume=_number(item.get("allocated_sales_volume")),
                allocated_sales_amount=_number(item.get("allocated_sales_amount")),
                allocation_weight=_fraction(item.get("allocation_weight")),
                incremental=False,
                source_lineage_hash=canonical_v4_hash(item),
                lineage_status=context.v4_context.lineage_gate.status,
            )
        )
    return sorted(result, key=lambda row: row.battlefield_code)


def _portfolio_inputs(
    context: SellpointValueV5Context,
    links: Sequence[ReasonValueBundleLink],
    allocations: Sequence[BattlefieldAllocation],
) -> list[BattlefieldPortfolioInput]:
    memberships = _membership_map(context)
    link_by_battlefield = {row.battlefield_code: row for row in links}
    allocation_by_code = {row.battlefield_code: row for row in allocations}
    names = {row.battlefield_code: row.battlefield_name_cn for row in context.battlefield_taxonomy}
    for link in links:
        names[link.battlefield_code] = link.battlefield_name_cn
    codes = sorted(set(names) | set(memberships))
    rows = []
    for code in codes:
        link = link_by_battlefield.get(code)
        membership = memberships.get(code, "excluded")
        allocation = allocation_by_code.get(code)
        donors = sum(
            code in _membership_map_for_snapshot(snapshot)
            for snapshot in context.market_universe
            if snapshot.identity.sku_code != context.v4_context.target.sku_code
        )
        rows.append(
            BattlefieldPortfolioInput(
                battlefield_code=code,
                battlefield_name_cn=names.get(code) or ALL_BATTLEFIELD_CN.get(code) or "未命名价值战场",
                source_membership=membership,
                user_value_status=_v5_value_status(link) if link else "unknown",
                claim_support=(
                    "strong"
                    if link and link.link_status == "supported"
                    else "weak"
                    if link
                    else "unknown"
                ),
                capability_status=(
                    "complete"
                    if link
                    and link.bundle.members
                    and all(member.fact_status == "confirmed" for member in link.bundle.members)
                    else "partial"
                    if link
                    else "unknown"
                ),
                capability_gaps=[],
                market_realization_status="available" if allocation else "unidentifiable",
                role_capped=membership == "opportunity",
                immutable_market_gate_pass=True if membership != "excluded" else None,
                product_form_gate_pass=True if membership != "excluded" else None,
                task_group_adjacency=None if membership == "excluded" else 1.0,
                donor_count=donors,
                market_space=_market_space_for(context, code, link),
                current_allocation=allocation,
                overlap_risk="unknown",
                lineage_blocking=context.v4_context.lineage_gate.status == "stale_conflict",
                source_refs=link.source_refs if link else [],
            )
        )
    return rows


def _select_highlights(rows: Sequence[ValueAccountRow]) -> list[ValueHighlight]:
    candidates: list[tuple[float, int, str, ValueHighlight]] = []
    for row in rows:
        types = row.highlight_types
        if not types:
            continue
        value_name = str(row.perceived_user_value.get("name_cn") or "").strip()
        outcome = str(row.perceived_user_value.get("outcome_cn") or "").strip()
        if not value_name or not outcome:
            continue
        user_result = _highlight_user_result(outcome)
        if "market_realization" in types:
            highlight_type = "market_realization"
            reason = _market_realization_reason(row, user_result)
            score = 5.0
        elif "relative_value" in types:
            highlight_type = "relative_value"
            reason = (
                f"用户实际体验认可了“{user_result}”；与同样主打这项价值但用户评价较弱"
                "的同类产品相比，这组卖点已经形成用户优势。"
            )
            score = 4.0
        elif "candidate_relative_value" in types:
            highlight_type = "candidate_relative_value"
            reason = (
                f"用户实际体验认可了“{user_result}”；同类卖点产品的用户评价出现差异，"
                "可作为候选优势继续比较。"
            )
            score = 2.25
        elif "volume_realization" in types:
            highlight_type = "volume_realization"
            reason = (
                f"用户实际体验认可了“{user_result}”；与同类产品相比，这组卖点带来了"
                "更高销量。"
            )
            score = 3.0
        elif "price_realization" in types:
            highlight_type = "price_realization"
            reason = (
                f"用户实际体验认可了“{user_result}”；同类产品的量价表现显示这组卖点"
                "带来了价格溢价。"
            )
            score = 2.5
        else:
            highlight_type = "user_realization"
            reason = (
                f"用户实际体验认可了“{user_result}”；这项好处来自实际使用，"
                "不是仅由技术参数推演。"
            )
            score = 2.0
        battlefield_code = str(row.battlefield.get("code") or "").strip()
        component_count = len([part for part in value_name.split("＋") if part.strip()])
        candidates.append(
            (
                score,
                component_count,
                battlefield_code,
                ValueHighlight(
                    highlight_type=highlight_type,
                    bundle_code=row.sellpoint_bundle.bundle_code,
                    title_cn=value_name,
                    reason_cn=reason,
                    comparison_basis_cn=row.counterfactual_summary_cn,
                    price_realization_cn=_price_cn(row.price_realization),
                    volume_realization_cn=_volume_cn(row.volume_realization),
                    evidence_boundary_cn=row.boundary_cn,
                    internal_rank_components={"evidence_strength": score},
                ),
            )
        )
    candidates.sort(key=lambda item: (-item[0], item[1], item[3].bundle_code))
    result = []
    seen_titles: set[str] = set()
    seen_battlefields: set[str] = set()
    for _, _, battlefield_code, item in candidates:
        title_key = "＋".join(
            sorted(part.strip() for part in item.title_cn.split("＋"))
        )
        if title_key in seen_titles or (
            battlefield_code and battlefield_code in seen_battlefields
        ):
            continue
        seen_titles.add(title_key)
        if battlefield_code:
            seen_battlefields.add(battlefield_code)
        result.append(item)
        if len(result) == 3:
            break
    return result


def _highlight_user_result(outcome: str) -> str:
    result = outcome.strip()
    for prefix in (
        "用户购后反馈已观察到：",
        "用户购后反馈只部分支持：",
    ):
        if result.startswith(prefix):
            result = result.removeprefix(prefix).strip()
            break
    return result.rstrip("。")


def _market_realization_reason(row: ValueAccountRow, user_result: str) -> str:
    comparison = row.price_realization.realization_comparisons[0]
    value_name = str(row.perceived_user_value.get("name_cn") or "这项用户价值")
    if comparison.comparator_count == 1:
        basis = f"同样主打“{value_name}”但用户评价较弱的{comparison.comparator_names[0]}"
    else:
        basis = (
            f"{comparison.comparator_count} 款同样主打“{value_name}”但用户评价较弱"
            "的同类产品"
        )
    results = []
    if comparison.price_gap_abs is not None and comparison.price_gap_pct is not None:
        if (
            comparison.price_gap_abs > 0
            and comparison.sales_volume_gap_abs is not None
            and comparison.sales_volume_gap_abs >= 0
        ):
            results.append(
                f"{comparison.price_gap_abs:.0f}元"
                f"（{comparison.price_gap_pct * 100:.1f}%）的价格溢价"
            )
        else:
            results.append(
                _market_gap_cn(
                    comparison.price_gap_abs,
                    comparison.price_gap_pct,
                    metric="均价",
                    unit="元",
                )
            )
    if (
        comparison.sales_volume_gap_abs is not None
        and comparison.sales_volume_gap_pct is not None
    ):
        volume_unit = "台/周" if comparison.sales_volume_unit == "weekly_units" else "台"
        if comparison.sales_volume_gap_abs >= 0:
            results.append(
                f"{comparison.sales_volume_gap_abs:.1f}{volume_unit}"
                f"（{comparison.sales_volume_gap_pct * 100:.1f}%）的销量优势"
            )
        else:
            results.append(
                "销量未形成优势，较同类产品低 "
                f"{abs(comparison.sales_volume_gap_abs):.1f}{volume_unit}"
            )
    market_result = "、".join(results)
    return (
        f"用户实际体验认可了“{user_result}”。与{basis}相比，这项用户价值为本品带来"
        f"{market_result}。这是已经产生商业价值的核心卖点，应继续保留并强化。"
    )


def _market_gap_cn(gap_abs: float, gap_pct: float, *, metric: str, unit: str) -> str:
    direction = "高" if gap_abs >= 0 else "低"
    amount = abs(gap_abs)
    amount_text = f"{amount:.0f}" if amount >= 10 else f"{amount:.1f}"
    return f"{metric}{direction} {amount_text}{unit}（{abs(gap_pct) * 100:.1f}%）"


def _no_highlight_reason_cn(context, analysis_state):
    if analysis_state == "blocked" and context.v4_context.lineage_gate.status == "stale_conflict":
        return "当前来源版本存在冲突，亮点判断已暂停；不能把尚未对齐的用户价值与市场参照合并成结论。"
    return "当前未识别出同时具备具体用户结果和可靠相对证据的亮点。"


def _eligible_highlight_types(value_status, sets, accounting, synthetic_control):
    if value_status not in {"observed_positive", "partial"}:
        return []
    result = ["user_realization"] if value_status == "observed_positive" else []
    user_set = next(row for row in sets if row.question == "user_realization")
    realization_candidates = [
        row
        for row in user_set.candidates
        if row.method == "same_claim_realization" and row.stage == "eligible"
    ]
    confirmed = any(
        row.control_dimensions.get("peer_contradicted_claim_codes")
        for row in realization_candidates
    )
    if confirmed:
        result.append("relative_value")
    elif realization_candidates:
        result.append("candidate_relative_value")
    comparisons = accounting.price.realization_comparisons
    if confirmed and any(
        (item.price_gap_pct is not None and item.price_gap_pct > 0)
        or (item.sales_volume_gap_pct is not None and item.sales_volume_gap_pct > 0)
        for item in comparisons
    ):
        result.append("market_realization")
    interval = accounting.price.strict_bundle_interval
    if interval is not None and interval.status == "available":
        result.append("price_realization")
    synthetic = accounting.volume.synthetic_difference
    source = next(
        (
            row
            for row in sets
            if row.question == "without_value_baseline"
        ),
        None,
    )
    if (
        synthetic is not None
        and synthetic.low is not None
        and synthetic.low > 0
        and synthetic_control.diagnostics.placebo_percentile is not None
        and synthetic_control.diagnostics.placebo_percentile >= 0.80
        and source is not None
    ):
        result.append("volume_realization")
    return result


def _realization_market_comparisons(
    context: SellpointValueV5Context,
    sets: Sequence[CounterfactualSet],
) -> list[RealizationMarketComparison]:
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    target = snapshots.get(context.v4_context.target.sku_code)
    if target is None:
        return []
    user_set = next(
        (row for row in sets if row.question == "user_realization"),
        None,
    )
    relative_set = next(
        (row for row in sets if row.question == "relative_highlight"),
        None,
    )
    result: list[RealizationMarketComparison] = []
    same_claim_candidates = [
        row
        for row in (user_set.candidates if user_set is not None else [])
        if row.method == "same_claim_realization" and row.stage == "eligible"
    ]
    if same_claim_candidates:
        shared_claims = sorted(
            {
                str(code)
                for candidate in same_claim_candidates
                for code in candidate.control_dimensions.get(
                    "same_advertised_claim_codes", []
                )
                if str(code)
            }
        )
        confirmed = any(
            candidate.control_dimensions.get("peer_contradicted_claim_codes")
            for candidate in same_claim_candidates
        )
        comparison = _build_market_comparison(
            target,
            snapshots,
            same_claim_candidates,
            method="same_claim_different_realization",
            comparison_basis_cn="同样主打该卖点但用户评价较弱的产品",
            shared_claim_codes=shared_claims,
            evidence_strength="confirmed" if confirmed else "candidate",
        )
        if comparison is not None:
            result.append(comparison)

    relative_candidates = relative_set.candidates if relative_set is not None else []
    direct_candidates = [
        row
        for row in relative_candidates
        if row.method == "direct_sku" and row.stage == "eligible"
    ]
    for candidate in direct_candidates:
        comparison = _build_market_comparison(
            target,
            snapshots,
            [candidate],
            method="direct_comparable",
            comparison_basis_cn="系统识别的同类产品",
        )
        if comparison is not None:
            result.append(comparison)

    for candidate_method, output_method, basis in (
        ("same_budget_pool", "same_budget_pool", "同尺寸、同预算产品"),
        (
            "same_brand_size_ladder",
            "same_brand_size_ladder",
            "同品牌、同尺寸产品",
        ),
    ):
        candidates = [
            row
            for row in relative_candidates
            if row.method == candidate_method and row.stage == "eligible"
        ]
        comparison = _build_market_comparison(
            target,
            snapshots,
            candidates,
            method=output_method,
            comparison_basis_cn=basis,
        )
        if comparison is not None:
            result.append(comparison)

    parameter_candidates = [
        row
        for row in relative_candidates
        if row.method == "param_tier_pool" and row.stage == "eligible"
    ]
    parameter_groups: dict[tuple[str, str], list[Any]] = {}
    for candidate in parameter_candidates:
        configuration = candidate.control_dimensions.get(
            "peer_parameter_configuration"
        ) or {}
        target_configuration = candidate.control_dimensions.get(
            "target_parameter_configuration"
        ) or {}
        for parameter_code, parameter_value in sorted(configuration.items()):
            if target_configuration.get(parameter_code) == parameter_value:
                continue
            key = (str(parameter_code), str(parameter_value))
            parameter_groups.setdefault(key, []).append(candidate)
    for key in sorted(parameter_groups):
        candidates = parameter_groups[key]
        parameter_code, parameter_value = key
        summary = f"{parameter_code.split('.')[-1]}={parameter_value}"
        comparison = _build_market_comparison(
            target,
            snapshots,
            candidates,
            method="parameter_configuration",
            comparison_basis_cn=f"参数组合：{summary}" if summary else "不同参数组合",
        )
        if comparison is not None:
            result.append(comparison)
    return result


def _build_market_comparison(
    target: SkuEvidenceSnapshot,
    snapshots: dict[str, SkuEvidenceSnapshot],
    candidates: Sequence[Any],
    *,
    method: str,
    comparison_basis_cn: str,
    shared_claim_codes: Sequence[str] = (),
    evidence_strength: str = "candidate",
) -> RealizationMarketComparison | None:
    candidate_by_code = {
        code: candidate
        for candidate in candidates
        for code in candidate.candidate_sku_codes
        if code in snapshots and code != target.identity.sku_code
    }
    if not candidate_by_code:
        return None
    codes = sorted(candidate_by_code)
    peers = [snapshots[code] for code in codes]
    target_price = _snapshot_market_number(
        target, "price_wavg", "weighted_price", "avg_price", "price_wavg_12m"
    )
    peer_prices = [
        value
        for peer in peers
        if (
            value := _snapshot_market_number(
                peer,
                "price_wavg",
                "weighted_price",
                "avg_price",
                "price_wavg_12m",
            )
        )
        is not None
    ]
    target_volume = _snapshot_weekly_sales(target)
    peer_volumes = [
        value
        for peer in peers
        if (value := _snapshot_weekly_sales(peer)) is not None
    ]
    price_values = _comparison_values(target_price, peer_prices)
    volume_values = _comparison_values(target_volume, peer_volumes)
    if price_values is None and volume_values is None:
        return None

    limitations = []
    if len(codes) == 1:
        limitations.append("single_comparator_sensitive")
    return RealizationMarketComparison(
        method=method,
        comparison_basis_cn=comparison_basis_cn,
        comparator_sku_codes=codes,
        comparator_names=[
            snapshots[code].identity.model_name or code for code in codes
        ],
        comparator_count=len(codes),
        shared_claim_codes=sorted(set(shared_claim_codes)),
        evidence_strength=evidence_strength,
        target_price=price_values[0] if price_values else None,
        comparator_price_median=price_values[1] if price_values else None,
        price_gap_abs=price_values[2] if price_values else None,
        price_gap_pct=price_values[3] if price_values else None,
        target_sales_volume=volume_values[0] if volume_values else None,
        comparator_sales_volume_median=volume_values[1] if volume_values else None,
        sales_volume_gap_abs=volume_values[2] if volume_values else None,
        sales_volume_gap_pct=volume_values[3] if volume_values else None,
        sales_volume_unit="weekly_units",
        causal_claim=False,
        limitations=limitations,
    )


def _comparison_values(
    target_value: float | None,
    peer_values: Sequence[float],
) -> tuple[float, float, float, float] | None:
    if target_value is None or not peer_values:
        return None
    peer_median = float(median(peer_values))
    if peer_median == 0:
        return None
    gap = target_value - peer_median
    return (
        round(target_value, 6),
        round(peer_median, 6),
        round(gap, 6),
        round(gap / peer_median, 6),
    )


def _market_reference_cn(
    context,
    rows,
    synthetic_by_bundle,
    archetypes,
    comparison_catalog,
):
    baselines = []
    names = {row.sellpoint_bundle.bundle_code: row.sellpoint_bundle.bundle_name_cn for row in rows}
    active_codes = set(names)
    for code, result in sorted(synthetic_by_bundle.items()):
        if code not in active_codes:
            continue
        if result.status == "available" and result.sales_difference is not None:
            difference = result.sales_difference.estimate
            direction = "高" if difference is not None and difference >= 0 else "低"
            summary = (
                f"与 {result.diagnostics.donor_count} 款同尺寸、相近价格产品的中位表现相比，"
                f"本品周均销量{direction} {abs(difference or 0):.1f} 台/周。"
            )
            baselines.append(
                {
                    "bundle_name_cn": names.get(code) or code,
                    "summary_cn": summary,
                    "donor_count": result.diagnostics.donor_count,
                }
            )
    high = next((row for row in archetypes if row.role == "high_performance"), None)
    low = next((row for row in archetypes if row.role == "low_performance"), None)
    return {
        "synthetic_baselines": baselines,
        "high_performance": _archetype_cn(high, "高销量", context),
        "low_performance": _archetype_cn(low, "低销量", context),
        "performance_value_differences": _performance_value_differences(
            context, rows, high, low
        ),
        "question_driven_comparisons": _question_driven_comparisons(
            context,
            rows,
            comparison_catalog,
            high,
            low,
        ),
    }


def _question_driven_comparisons(
    context: SellpointValueV5Context,
    rows: Sequence[ValueAccountRow],
    comparison_catalog: Sequence[dict[str, Any]],
    high: PerformanceArchetype | None,
    low: PerformanceArchetype | None,
) -> list[dict[str, Any]]:
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    definitions = _value_unit_by_code(context.category_code)
    target_name = context.v4_context.target.model_name or "本品"
    target_brand = context.v4_context.target.brand_name or "本品牌"
    candidates = [
        item
        for item in comparison_catalog
        if item.get("value_status") in {"observed_positive", "partial"}
    ]
    candidates.sort(
        key=lambda item: (
            len(item["bundle"].members),
            str(item.get("value_name_cn") or ""),
        )
    )
    result: list[dict[str, Any]] = []
    budget_entry = next(
        (
            item
            for item in candidates
            if _catalog_comparison(item, "same_budget_pool") is not None
        ),
        None,
    )
    if budget_entry is not None:
        comparison = _catalog_comparison(budget_entry, "same_budget_pool")
        claims = _catalog_claim_codes(budget_entry, definitions)
        target_coverage = _group_claim_coverage(
            snapshots,
            [context.v4_context.target.sku_code],
            claims,
        )
        peer_coverage = _group_claim_coverage(
            snapshots, comparison.comparator_sku_codes, claims
        )
        value_name = str(budget_entry.get("value_name_cn") or "用户价值")
        coverage_gap = target_coverage - peer_coverage
        peer_advantages = _peer_advantage_claims(
            snapshots,
            context.v4_context.target.sku_code,
            comparison.comparator_sku_codes,
            claims,
        )
        conclusion = (
            f"选择{'、'.join(comparison.comparator_names)}作为同预算组。"
            f"“{value_name}”所包含的用户反馈要点，本品覆盖约"
            f"{target_coverage * 100:.0f}%，同预算组平均覆盖约"
            f"{peer_coverage * 100:.0f}%。"
        )
        if comparison.price_gap_abs is not None and comparison.sales_volume_gap_abs is not None:
            conclusion += (
                f"在此基础上，本品均价高{comparison.price_gap_abs:.0f}元，"
                f"周均销量高{comparison.sales_volume_gap_abs:.1f}台。"
            )
        if coverage_gap <= -0.05:
            improvement = ""
            if peer_advantages:
                improvement = (
                    "优先补强"
                    f"{'、'.join(CLAIM_LABELS_CN.get(code, code) for code in peer_advantages)}"
                    "对应的用户体验或卖点表达。"
                )
            conclusion += (
                f"本品的反馈覆盖反而少{abs(coverage_gap) * 100:.0f}个百分点，"
                "说明优势并不来自画质卖点覆盖更多，更可能来自少数关键体验或整机组合，"
                "不能把全部销量差都归因于这组画质卖点。"
                f"{improvement}"
            )
        elif coverage_gap >= 0.05:
            conclusion += (
                f"本品的反馈覆盖多{coverage_gap * 100:.0f}个百分点，"
                "价值反馈与量价表现方向一致，可作为同预算竞争的重点表达。"
            )
        else:
            conclusion += (
                "两组的反馈覆盖接近，量价优势不能用卖点数量解释，"
                "应继续比较具体体验和整机组合。"
            )
        result.append(
            {
                "question_cn": "同预算竞争中本品赢在哪里",
                "selected_products": comparison.comparator_names,
                "conclusion_cn": conclusion,
            }
        )

    brand_entry = next(
        (
            item
            for item in candidates
            if _catalog_comparison(item, "same_brand_size_ladder") is not None
        ),
        None,
    )
    if brand_entry is not None:
        comparison = _catalog_comparison(brand_entry, "same_brand_size_ladder")
        conclusion = (
            f"选择{'、'.join(comparison.comparator_names)}比较{target_brand}内部定位。"
        )
        if comparison.price_gap_abs is not None and comparison.sales_volume_gap_abs is not None:
            price_role = "建立了更高价格" if comparison.price_gap_abs > 0 else "价格更低"
            price_direction = "高" if comparison.price_gap_abs > 0 else "低"
            volume_role = (
                "但销量规模更小"
                if comparison.sales_volume_gap_abs < 0
                else "并获得更大销量"
            )
            conclusion += (
                f"{target_name}{price_role}（{price_direction}"
                f"{abs(comparison.price_gap_abs):.0f}元），"
                f"{volume_role}（相差{abs(comparison.sales_volume_gap_abs):.1f}台/周），"
                "因此承担高端溢价款而不是主走量款的角色。"
            )
        result.append(
            {
                "question_cn": f"{target_name}在{target_brand}产品线中的角色",
                "selected_products": comparison.comparator_names,
                "conclusion_cn": conclusion,
            }
        )

    weakness_result = _weakness_comparison(
        context,
        candidates,
        definitions,
        budget_entry=budget_entry,
        brand_entry=brand_entry,
        high=high,
    )
    if weakness_result is not None:
        result.append(weakness_result)
    scale_shortfall = _scale_shortfall_comparison(
        context,
        candidates,
        definitions,
    )
    if scale_shortfall is not None:
        result.append(scale_shortfall)

    parameter_entry = next(
        (
            item
            for item in candidates
            if any(
                comparison.method == "parameter_configuration"
                for comparison in item.get("comparisons") or []
            )
        ),
        None,
    )
    if parameter_entry is not None:
        parameter_result = _parameter_value_conclusion(
            snapshots,
            parameter_entry,
            definitions,
        )
        if parameter_result is not None:
            result.append(parameter_result)

    performance_summary = _performance_comparison_summary(
        {
            "high_performance": _archetype_cn(high, "高销量", context),
            "low_performance": _archetype_cn(low, "低销量", context),
            "performance_value_differences": _performance_value_differences(
                context,
                rows,
                high,
                low,
            ),
        }
    )
    if performance_summary:
        result.append(
            {
                "question_cn": "卖得好和卖得差的产品有什么不同",
                "selected_products": [
                    *(high.representative_sku_codes if high else []),
                    *(low.representative_sku_codes if low else []),
                ],
                "conclusion_cn": performance_summary,
            }
        )
    return result


def _catalog_comparison(
    entry: dict[str, Any], method: str
) -> RealizationMarketComparison | None:
    return next(
        (
            comparison
            for comparison in entry.get("comparisons") or []
            if comparison.method == method
        ),
        None,
    )


def _catalog_claim_codes(entry: dict[str, Any], definitions) -> set[str]:
    return {
        claim_code
        for member in entry["bundle"].members
        if (definition := definitions.get(member.capability_code)) is not None
        for claim_code in definition.claim_codes
    }


def _group_claim_coverage(
    snapshots: dict[str, SkuEvidenceSnapshot],
    sku_codes: Sequence[str],
    claim_codes: set[str],
) -> float:
    if not sku_codes or not claim_codes:
        return 0.0
    coverage = []
    for sku_code in sku_codes:
        snapshot = snapshots.get(sku_code)
        if snapshot is None:
            continue
        supported = _snapshot_code_set(snapshot, "supported_claim_codes")
        coverage.append(len(supported & claim_codes) / len(claim_codes))
    return round(sum(coverage) / len(coverage), 6) if coverage else 0.0


def _peer_advantage_claims(
    snapshots: dict[str, SkuEvidenceSnapshot],
    target_sku_code: str,
    peer_sku_codes: Sequence[str],
    claim_codes: set[str],
) -> list[str]:
    target = snapshots.get(target_sku_code)
    if target is None:
        return []
    target_supported = _snapshot_code_set(target, "supported_claim_codes")
    peer_snapshots = [
        snapshots[sku_code]
        for sku_code in peer_sku_codes
        if sku_code in snapshots
    ]
    if not peer_snapshots:
        return []
    scored = []
    for claim_code in claim_codes - target_supported:
        peer_rate = sum(
            claim_code in _snapshot_code_set(snapshot, "supported_claim_codes")
            for snapshot in peer_snapshots
        ) / len(peer_snapshots)
        if peer_rate >= 1 / len(peer_snapshots):
            scored.append((peer_rate, claim_code))
    return [code for _, code in sorted(scored, key=lambda item: (-item[0], item[1]))[:3]]


def _weakness_comparison(
    context: SellpointValueV5Context,
    catalog: Sequence[dict[str, Any]],
    definitions,
    *,
    budget_entry: dict[str, Any] | None,
    brand_entry: dict[str, Any] | None,
    high: PerformanceArchetype | None,
) -> dict[str, Any] | None:
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    target_code = context.v4_context.target.sku_code
    claim_codes = {
        claim_code
        for entry in catalog
        for claim_code in _catalog_claim_codes(entry, definitions)
    }
    groups: list[tuple[str, list[str], list[str]]] = []
    if budget_entry is not None:
        comparison = _catalog_comparison(budget_entry, "same_budget_pool")
        if comparison is not None:
            groups.append(
                (
                    "同预算产品",
                    comparison.comparator_sku_codes,
                    comparison.comparator_names,
                )
            )
    if brand_entry is not None:
        comparison = _catalog_comparison(brand_entry, "same_brand_size_ladder")
        if comparison is not None:
            groups.append(
                (
                    "同品牌走量款",
                    comparison.comparator_sku_codes,
                    comparison.comparator_names,
                )
            )
    lower_price_higher_sales = _lower_price_higher_sales_rows(catalog)
    if lower_price_higher_sales:
        groups.append(
            (
                "价格更低但销量更高的产品",
                sorted(lower_price_higher_sales),
                [
                    lower_price_higher_sales[code].comparator_names[0]
                    for code in sorted(lower_price_higher_sales)
                ],
            )
        )
    if high is not None:
        names = {
            snapshot.identity.sku_code: snapshot.identity.model_name
            or snapshot.identity.sku_code
            for snapshot in context.market_universe
        }
        groups.append(
            (
                "高销量产品",
                high.representative_sku_codes,
                [names.get(code, code) for code in high.representative_sku_codes],
            )
        )
    gap_contexts: dict[str, set[str]] = {}
    selected_products: set[str] = set()
    for label, sku_codes, product_names in groups:
        gaps = _supported_claim_gaps(
            snapshots,
            target_code,
            sku_codes,
            claim_codes,
        )
        if not gaps:
            continue
        selected_products.update(product_names)
        for claim_code in gaps[:3]:
            gap_contexts.setdefault(claim_code, set()).add(label)
    if not gap_contexts:
        return None
    clauses = [
        f"{CLAIM_LABELS_CN.get(claim_code, claim_code)}在"
        f"{'、'.join(sorted(labels))}中更常得到用户正向反馈，本品尚未形成同等覆盖"
        for claim_code, labels in sorted(
            gap_contexts.items(),
            key=lambda item: (-len(item[1]), CLAIM_LABELS_CN.get(item[0], item[0])),
        )
    ]
    return {
        "question_cn": "本品当前最明显的短板",
        "selected_products": sorted(selected_products),
        "conclusion_cn": (
            "；".join(clauses)
            + "。这些是用户反馈覆盖短板：能力已经具备的，应强化体验表达；"
            "能力尚未具备的，应回到产品定义补齐。"
        ),
    }


def _scale_shortfall_comparison(
    context: SellpointValueV5Context,
    catalog: Sequence[dict[str, Any]],
    definitions,
) -> dict[str, Any] | None:
    comparisons = _lower_price_higher_sales_rows(catalog)
    if not comparisons:
        return None
    rows = list(comparisons.values())
    comparator_prices = [
        row.comparator_price_median
        for row in rows
        if row.comparator_price_median is not None
    ]
    comparator_sales = [
        row.comparator_sales_volume_median
        for row in rows
        if row.comparator_sales_volume_median is not None
    ]
    target_prices = [row.target_price for row in rows if row.target_price is not None]
    target_sales = [
        row.target_sales_volume for row in rows if row.target_sales_volume is not None
    ]
    if not comparator_prices or not comparator_sales or not target_prices or not target_sales:
        return None
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    claim_codes = {
        claim_code
        for entry in catalog
        for claim_code in _catalog_claim_codes(entry, definitions)
    }
    gaps = _supported_claim_gaps(
        snapshots,
        context.v4_context.target.sku_code,
        sorted(comparisons),
        claim_codes,
    )
    target_price = median(target_prices)
    target_volume = median(target_sales)
    comparator_price = median(comparator_prices)
    comparator_volume = median(comparator_sales)
    conclusion = (
        f"从候选池中选出{len(rows)}款价格更低但销量更高的产品组成走量组。"
        f"该组均价中位数约{comparator_price:.0f}元，比本品低"
        f"{target_price - comparator_price:.0f}元；周均销量中位数约"
        f"{comparator_volume:.1f}台，比本品高{comparator_volume - target_volume:.1f}台。"
    )
    if gaps:
        conclusion += (
            "这组产品还更常获得"
            f"{'、'.join(CLAIM_LABELS_CN.get(code, code) for code in gaps[:3])}"
            "的用户正向反馈，是扩大规模时优先补强的价值方向。"
        )
    else:
        conclusion += (
            "这组产品没有稳定多出一项本品缺失的用户价值反馈，"
            "因此规模短板不是少一个常规卖点，而是高价画质定位没有转成同等销量规模。"
        )
    return {
        "question_cn": "本品的规模转化短板",
        "selected_products": [
            comparisons[code].comparator_names[0] for code in sorted(comparisons)
        ],
        "conclusion_cn": conclusion,
    }


def _lower_price_higher_sales_rows(
    catalog: Sequence[dict[str, Any]],
) -> dict[str, RealizationMarketComparison]:
    result: dict[str, RealizationMarketComparison] = {}
    for entry in catalog:
        for comparison in entry.get("comparisons") or []:
            if (
                comparison.method != "direct_comparable"
                or comparison.price_gap_abs is None
                or comparison.price_gap_abs <= 0
                or comparison.sales_volume_gap_abs is None
                or comparison.sales_volume_gap_abs >= 0
            ):
                continue
            for sku_code in comparison.comparator_sku_codes:
                result.setdefault(sku_code, comparison)
    return result


def _supported_claim_gaps(
    snapshots: dict[str, SkuEvidenceSnapshot],
    target_sku_code: str,
    peer_sku_codes: Sequence[str],
    claim_codes: set[str],
) -> list[str]:
    target = snapshots.get(target_sku_code)
    peers = [snapshots[code] for code in peer_sku_codes if code in snapshots]
    if target is None or not peers:
        return []
    target_supported = _snapshot_code_set(target, "supported_claim_codes")
    target_contradicted = _snapshot_code_set(target, "contradicted_claim_codes")
    scored = []
    for claim_code in claim_codes - target_supported:
        peer_rate = sum(
            claim_code in _snapshot_code_set(peer, "supported_claim_codes")
            for peer in peers
        ) / len(peers)
        if peer_rate < 0.5:
            continue
        contradiction_bonus = 1.0 if claim_code in target_contradicted else 0.0
        scored.append((contradiction_bonus + peer_rate, claim_code))
    return [code for _, code in sorted(scored, key=lambda item: (-item[0], item[1]))]


def _parameter_value_conclusion(
    snapshots: dict[str, SkuEvidenceSnapshot],
    entry: dict[str, Any],
    definitions,
) -> dict[str, Any] | None:
    claims = _catalog_claim_codes(entry, definitions)
    comparisons = [
        comparison
        for comparison in entry.get("comparisons") or []
        if comparison.method == "parameter_configuration"
        and comparison.comparator_count >= 2
        and _parameter_value_is_valid(comparison.comparison_basis_cn)
    ]
    by_dimension_and_products: dict[
        tuple[str, tuple[str, ...]], RealizationMarketComparison
    ] = {}
    for comparison in comparisons:
        dimension = _parameter_dimension(comparison.comparison_basis_cn)
        if not dimension:
            continue
        key = (dimension, tuple(comparison.comparator_sku_codes))
        by_dimension_and_products.setdefault(key, comparison)
    by_dimension: dict[
        str, list[tuple[float, RealizationMarketComparison]]
    ] = {}
    for (dimension, _), comparison in by_dimension_and_products.items():
        by_dimension.setdefault(dimension, []).append(
            (
                _group_claim_coverage(
                    snapshots, comparison.comparator_sku_codes, claims
                ),
                comparison,
            )
        )
    contrasts = []
    for dimension, scored in by_dimension.items():
        if len(scored) < 2:
            continue
        scored.sort(key=lambda item: (item[0], item[1].comparison_basis_cn))
        low_rate, low_group = scored[0]
        high_rate, high_group = scored[-1]
        contrasts.append(
            (
                high_rate - low_rate,
                _parameter_business_priority(dimension),
                low_rate,
                low_group,
                high_rate,
                high_group,
            )
        )
    if not contrasts:
        return None
    (
        coverage_gap,
        _,
        low_rate,
        low_group,
        high_rate,
        high_group,
    ) = max(
        contrasts,
        key=lambda item: (item[0], -item[1], item[5].comparison_basis_cn),
    )
    value_name = str(entry.get("value_name_cn") or "用户价值")
    if coverage_gap < 0.15:
        return None
    conclusion = (
        f"在同一参数的不同取值中，{_parameter_basis_cn(high_group.comparison_basis_cn)}"
        f"对应的“{value_name}”反馈要点覆盖度约{high_rate * 100:.0f}%，"
        f"高于{_parameter_basis_cn(low_group.comparison_basis_cn)}组的"
        f"{low_rate * 100:.0f}%。该参数与用户价值反馈同向，可作为配置取舍的优先验证项。"
    )
    return {
        "question_cn": "哪些参数真正转化成用户价值",
        "selected_products": sorted(
            set(high_group.comparator_names + low_group.comparator_names)
        ),
        "conclusion_cn": conclusion,
    }


def _parameter_business_priority(basis: str) -> int:
    tokens = (
        "backlight_subtype",
        "display_tech_class",
        "local_dimming_zone_count",
        "declared_brightness",
        "color_gamut_ratio",
        "declared_refresh_rate_hz",
    )
    return next((index for index, token in enumerate(tokens) if token in basis), len(tokens))


def _parameter_dimension(basis: str) -> str:
    return basis.removeprefix("参数组合：").partition("=")[0].strip()


def _parameter_value_is_valid(basis: str) -> bool:
    dimension, separator, raw_value = basis.removeprefix("参数组合：").partition("=")
    if not separator or not dimension.strip():
        return False
    value = raw_value.strip().lower()
    if not value or value in {"-", "--", "unknown", "none", "null", "nan"}:
        return False
    if dimension.strip() != "local_dimming_zone_count" and value in {
        "0",
        "0.0",
        "-1100",
        "-1100.0",
    }:
        return False
    return True


def _parameter_basis_cn(basis: str) -> str:
    result = basis.removeprefix("参数组合：")
    labels = {
        "backlight_subtype": "背光类型",
        "display_tech_class": "显示技术",
        "local_dimming_zone_count": "分区数",
        "declared_brightness_typical_nit": "标称亮度",
        "declared_brightness_peak_nit": "峰值亮度",
        "color_gamut_ratio": "色域",
        "declared_refresh_rate_hz": "刷新率",
    }
    for code, label in labels.items():
        result = result.replace(code, label)
    return result


def _performance_value_differences(
    context: SellpointValueV5Context,
    rows: Sequence[ValueAccountRow],
    high: PerformanceArchetype | None,
    low: PerformanceArchetype | None,
) -> list[dict[str, Any]]:
    if high is None or low is None or not high.sku_count or not low.sku_count:
        return []
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    definitions = _value_unit_by_code(context.category_code)
    result = []
    seen_names: set[str] = set()
    for row in rows:
        name = str(row.perceived_user_value.get("name_cn") or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        claims = {
            claim_code
            for member in row.sellpoint_bundle.members
            if (definition := definitions.get(member.capability_code)) is not None
            for claim_code in definition.claim_codes
        }
        if not claims:
            continue
        high_rate = _group_value_rate(
            snapshots, high.representative_sku_codes, claims
        )
        low_rate = _group_value_rate(
            snapshots, low.representative_sku_codes, claims
        )
        if high_rate is None or low_rate is None or abs(high_rate - low_rate) < 0.25:
            continue
        result.append(
            {
                "value_name_cn": name,
                "high_rate": high_rate,
                "low_rate": low_rate,
                "gap": round(high_rate - low_rate, 6),
                "direction": "high" if high_rate > low_rate else "low",
            }
        )
    return sorted(result, key=lambda item: (-abs(item["gap"]), item["value_name_cn"]))


def _group_value_rate(
    snapshots: dict[str, SkuEvidenceSnapshot],
    sku_codes: Sequence[str],
    claim_codes: set[str],
) -> float | None:
    observed = []
    for sku_code in sku_codes:
        snapshot = snapshots.get(sku_code)
        if snapshot is None:
            continue
        supported = _snapshot_code_set(snapshot, "supported_claim_codes")
        observed.append(bool(supported & claim_codes))
    return round(sum(observed) / len(observed), 6) if observed else None


def _snapshot_code_set(snapshot: SkuEvidenceSnapshot, key: str) -> set[str]:
    result: set[str] = set()
    queue: list[Any] = [snapshot.facts, snapshot.comment_outcomes]
    while queue:
        value = queue.pop(0)
        if isinstance(value, dict):
            for item_key, item in value.items():
                if item_key == key and isinstance(item, list):
                    result.update(str(code) for code in item if str(code))
                elif isinstance(item, (dict, list)):
                    queue.append(item)
        elif isinstance(value, list):
            queue.extend(item for item in value if isinstance(item, (dict, list)))
    return result


def _archetype_cn(
    row: PerformanceArchetype | None,
    label: str,
    context: SellpointValueV5Context,
) -> dict[str, Any]:
    if row is None or row.role == "unstable":
        return {"summary_cn": f"当前样本不足以形成稳定的{label}价值组合原型。"}
    names = {
        snapshot.identity.sku_code: snapshot.identity.model_name
        or snapshot.identity.sku_code
        for snapshot in context.market_universe
    }
    product_names = [
        names.get(code, code) for code in row.representative_sku_codes
    ]
    return {
        "summary_cn": (
            f"{label}组 {row.sku_count} 款产品（{'、'.join(product_names)}），周均销量中位数约 "
            f"{row.volume_interval.estimate:.1f} 台/周，均价中位数约 "
            f"{row.price_interval.estimate:.0f} 元。"
        ),
        "sku_count": row.sku_count,
        "sku_codes": row.representative_sku_codes,
        "product_names": product_names,
        "volume_median": row.volume_interval.estimate,
        "price_median": row.price_interval.estimate,
    }


def _overall_price_summary(rows: Sequence[ValueAccountRow]) -> str:
    comparison_rows = [
        (len(row.sellpoint_bundle.members), row.sellpoint_bundle.bundle_code, comparison)
        for row in rows
        for comparison in row.price_realization.realization_comparisons
        if comparison.method == "same_claim_different_realization"
        if comparison.price_gap_abs is not None and comparison.price_gap_pct is not None
    ]
    if comparison_rows:
        _, _, representative = min(
            comparison_rows,
            key=lambda item: (item[0], -(item[2].price_gap_pct or 0.0), item[1]),
        )
        strongest_text = _market_gap_cn(
            representative.price_gap_abs or 0.0,
            representative.price_gap_pct or 0.0,
            metric="均价",
            unit="元",
        )
        if (
            representative.price_gap_abs is not None
            and representative.price_gap_abs > 0
            and representative.sales_volume_gap_abs is not None
            and representative.sales_volume_gap_abs >= 0
        ):
            strongest_text = (
                f"最具体一组带来 {representative.price_gap_abs:.0f} 元"
                f"（{representative.price_gap_pct * 100:.1f}%）的价格溢价"
            )
        else:
            strongest_text = f"最具体一组{strongest_text}"
        return (
            f"{len(comparison_rows)} 组用户价值带来价格溢价；"
            f"{strongest_text}。"
        )
    available = [
        row.price_realization.strict_bundle_interval
        for row in rows
        if row.price_realization.strict_bundle_interval is not None
        and row.price_realization.strict_bundle_interval.status == "available"
    ]
    if available:
        return f"{len(available)} 组用户价值带来可识别的价格溢价。"
    return "当前没有形成可展示的用户价值价格比较。"


def _overall_volume_summary(rows: Sequence[ValueAccountRow]) -> str:
    comparison_rows = [
        (len(row.sellpoint_bundle.members), row.sellpoint_bundle.bundle_code, comparison)
        for row in rows
        for comparison in row.volume_realization.realization_comparisons
        if comparison.method == "same_claim_different_realization"
        if comparison.sales_volume_gap_abs is not None
        and comparison.sales_volume_gap_pct is not None
        and comparison.sales_volume_gap_abs > 0
    ]
    if comparison_rows:
        _, _, representative = min(
            comparison_rows,
            key=lambda item: (
                item[0],
                -(item[2].sales_volume_gap_abs or 0.0),
                item[1],
            ),
        )
        return (
            f"{len(comparison_rows)} 组用户价值带来销量优势；最具体一组约 "
            f"{representative.sales_volume_gap_abs:.1f} 台/周"
            f"（高 {representative.sales_volume_gap_pct * 100:.1f}%）。"
        )
    positive = [
        row
        for row in rows
        if row.volume_realization.synthetic_difference is not None
        and row.volume_realization.synthetic_difference.low is not None
        and row.volume_realization.synthetic_difference.low > 0
    ]
    if positive:
        return f"{len(positive)} 组用户价值比用户评价较弱的同类产品带来更高销量。"
    return "当前没有形成可展示的用户价值销量比较。"


def _has_reportable_price(rows: Sequence[ValueAccountRow]) -> bool:
    return any(
        row.price_realization.realization_comparisons
        or (
            row.price_realization.strict_bundle_interval is not None
            and row.price_realization.strict_bundle_interval.status == "available"
        )
        for row in rows
    )


def _has_reportable_volume(rows: Sequence[ValueAccountRow]) -> bool:
    return any(
        row.volume_realization.realization_comparisons
        or row.volume_realization.synthetic_difference is not None
        for row in rows
    )


def _existing_summary(options, context):
    existing = [row for row in options if row.option_type == "strengthen_existing"]
    if not existing:
        return "当前没有足够信息判断本品覆盖了哪些用户价值。"
    path_priority = {
        "capability_completion": 0,
        "communication_activation": 1,
        "market_activation": 2,
        "portfolio_priority": 3,
        "maintain_or_cap": 4,
    }
    actionable = sorted(
        [row for row in existing if row.strengthen_path != "maintain_or_cap"],
        key=lambda row: (
            path_priority[row.strengthen_path],
            _battlefield_name(context, row.battlefield_code),
        ),
    )
    clauses = []
    for row in actionable[:2]:
        name = _battlefield_name(context, row.battlefield_code)
        clauses.append(
            {
                "capability_completion": f"用户重视“{name}”，但产品能力仍有缺口",
                "communication_activation": f"“{name}”已得到用户认可，但卖点表达不够突出",
                "market_activation": f"“{name}”已得到用户认可，但尚未带来明显价格或销量优势",
                "portfolio_priority": f"需要判断是否继续把“{name}”作为产品组合重点",
            }[row.strengthen_path]
        )
    if clauses:
        detail = "；".join(clauses)
        return (
            f"本品已覆盖 {len(existing)} 类用户价值；{detail}。"
            "其余用户价值暂未显示继续投入的必要性。"
        )
    return (
        f"本品已覆盖 {len(existing)} 类用户价值；当前没有证据支持继续增加投入，"
        "先保持现有产品组合。"
    )


def _expansion_summary(options, context):
    eligible = [
        row
        for row in options
        if row.option_type == "expand_excluded"
        and row.expansion_eligibility is not None
        and row.expansion_eligibility.eligible
    ]
    if eligible:
        names = "、".join(_battlefield_name(context, row.battlefield_code) for row in eligible[:3])
        return f"发现 {len(eligible)} 个本品可以拓展的新用户价值方向：{names}。"
    return "当前没有明确的新用户价值方向，先聚焦已经产生商业价值的核心卖点。"


def _counterfactual_summary_cn(
    sets: Sequence[CounterfactualSet],
    comparisons: Sequence[RealizationMarketComparison] = (),
) -> str:
    if comparisons:
        same_claim = [
            item
            for item in comparisons
            if item.method == "same_claim_different_realization"
        ]
        if same_claim:
            count = sum(item.comparator_count for item in same_claim)
            return f"{count} 款同尺寸、同样主打该卖点但用户评价较弱的同类产品"
        methods = []
        for item in comparisons:
            if item.comparison_basis_cn and item.comparison_basis_cn not in methods:
                methods.append(item.comparison_basis_cn)
        if methods:
            return "已比较：" + "、".join(methods[:3])
    methods = []
    for row in sets:
        if row.highest_available_method is not None:
            name = METHOD_CN[row.highest_available_method]
            if name not in methods:
                methods.append(name)
    if methods:
        return "可用参照：" + "、".join(methods[:3])
    return "当前没有足够接近的同类产品可用于量价比较。"


def _row_boundary_cn(value_status, price: PriceRealization, volume: VolumeRealization) -> str:
    if value_status in {"not_observed", "unknown", "conflicted"}:
        return "用户尚未稳定认可这项价值，暂不列为有效卖点。"
    if price.realization_comparisons:
        return "与同样主打该卖点但用户评价较弱的同类产品相比，判断这项价值带来的价格溢价和销量优势。"
    if price.strict_bundle_interval and price.strict_bundle_interval.status == "available":
        return "用户已经认可这项价值，同类产品量价差显示其带来了价格溢价。"
    if volume.synthetic_difference is not None:
        return "与用户评价较弱的同类产品组合相比，估算这项价值带来的销量优势。"
    return "用户已感知到这项价值，但可比产品未显示显著量价优势，暂不列为量价亮点。"


def _price_cn(price: PriceRealization) -> str:
    comparison = next(
        (
            item
            for item in price.realization_comparisons
            if item.price_gap_abs is not None and item.price_gap_pct is not None
        ),
        None,
    )
    if comparison is not None:
        gap_text = _market_gap_cn(
            comparison.price_gap_abs,
            comparison.price_gap_pct,
            metric="均价",
            unit="元",
        )
        if (
            comparison.price_gap_abs > 0
            and comparison.sales_volume_gap_abs is not None
            and comparison.sales_volume_gap_abs >= 0
        ):
            return (
                f"这项价值带来 {comparison.price_gap_abs:.0f} 元"
                f"（{comparison.price_gap_pct * 100:.1f}%）的价格溢价"
            )
        return gap_text
    interval = price.strict_bundle_interval
    if interval and interval.status == "available" and interval.estimate is not None:
        return f"这组价值带来的价格溢价区间约 {_interval_text(interval.estimate)}"
    return "—"


def _volume_cn(volume: VolumeRealization) -> str:
    comparison = next(
        (
            item
            for item in volume.realization_comparisons
            if item.sales_volume_gap_abs is not None
            and item.sales_volume_gap_pct is not None
        ),
        None,
    )
    if comparison is not None:
        unit = "台/周" if comparison.sales_volume_unit == "weekly_units" else "台"
        if comparison.sales_volume_gap_abs >= 0:
            return (
                f"这项价值带来约 {comparison.sales_volume_gap_abs:.1f} {unit}销量优势"
                f"（高 {comparison.sales_volume_gap_pct * 100:.1f}%）"
            )
        return (
            f"这项价值未形成销量优势，较同类产品低 "
            f"{abs(comparison.sales_volume_gap_abs):.1f} {unit}"
        )
    if volume.synthetic_difference is not None:
        return f"与同类产品组合相比，销量优势约 {_interval_text(volume.synthetic_difference)}"
    return "—"


def _perceived_value_cn(row: ValueAccountRow) -> str:
    value = row.perceived_user_value
    scenario = str(value.get("scenario_cn") or "").strip()
    outcome = str(value.get("outcome_cn") or "").strip()
    status = str(value.get("status_cn") or "")
    detail = "；".join(item for item in (scenario, outcome) if item)
    return f"{status}：{detail}" if detail else status


def _bundle_cn(row: ValueAccountRow) -> str:
    names = [member.capability_name_cn for member in row.sellpoint_bundle.members]
    return "＋".join(names) if names else row.sellpoint_bundle.bundle_name_cn


def _v5_value_status(link: ReasonValueBundleLink | None):
    if link is None:
        return "unknown"
    return {
        "established": "observed_positive",
        "partial": "partial",
        "negative": "observed_negative",
        "mixed": "observed_mixed",
        "not_observed": "not_observed",
    }[link.value_status]


def _confidence_cn(value_status, sets):
    eligible = sum(row.highest_available_method is not None for row in sets)
    if value_status == "observed_positive" and eligible >= 2:
        return "证据较完整"
    if value_status in {"observed_positive", "partial", "observed_mixed"}:
        return "有用户证据，市场参照有限"
    return "证据不足或存在冲突"


def _analysis_state(context, rows):
    if context.v4_context.lineage_gate.status == "stale_conflict":
        return "blocked"
    if not rows:
        return "blocked"
    if any(row.value_status in {"observed_positive", "partial", "observed_mixed"} for row in rows):
        return "ready"
    return "partial"


def _bundle_claim_codes(
    link: ReasonValueBundleLink,
    product_category: str,
) -> list[str]:
    definitions = _value_unit_by_code(product_category)
    result: set[str] = set()
    for member in link.bundle.members:
        code = member.capability_code
        if code.upper().startswith("CLAIM"):
            result.add(code)
        definition = definitions.get(code)
        if definition is not None:
            result.update(definition.claim_codes)
    return sorted(result)


def _membership_map(context: SellpointValueV5Context) -> dict[str, str]:
    return _membership_map_for_snapshot(context.v4_context.target_snapshot)


def _membership_map_for_snapshot(snapshot) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in snapshot.battlefields:
        primary = str(item.get("primary_battlefield_code") or "").strip()
        if primary:
            result[primary] = "primary"
        for code in item.get("secondary_battlefield_codes") or []:
            result[str(code)] = "secondary"
        for code in item.get("opportunity_battlefield_codes") or []:
            result[str(code)] = "opportunity"
        for code in item.get("user_observed_battlefield_codes") or []:
            result[str(code)] = "user_observed"
        for code in item.get("drag_factor_battlefield_codes") or []:
            result[str(code)] = "drag"
    return result


def _entered_codes(item: dict[str, Any]) -> list[str]:
    result = []
    primary = str(item.get("primary_battlefield_code") or "").strip()
    if primary:
        result.append(primary)
    for key in (
        "secondary_battlefield_codes",
        "opportunity_battlefield_codes",
        "user_observed_battlefield_codes",
        "drag_factor_battlefield_codes",
    ):
        result.extend(str(code) for code in item.get(key) or [] if code)
    return result


def _membership_cn(context, code):
    return MEMBERSHIP_CN[_membership_map(context).get(code, "excluded")]


def _market_space_for(context, code, link):
    if link and link.battlefield_market_space:
        return link.battlefield_market_space
    for snapshot in context.market_universe:
        for item in snapshot.semantic_market:
            if (
                _is_battlefield_semantic(item)
                and str(item.get("dimension_code") or "") == code
                and item.get("market_space")
            ):
                return item["market_space"]
    return {}


def _battlefield_name(context, code):
    for row in context.battlefield_taxonomy:
        if row.battlefield_code == code:
            return _business_value_name(
                row.battlefield_name_cn or ALL_BATTLEFIELD_CN.get(code) or "未命名用户价值"
            )
    return _business_value_name(ALL_BATTLEFIELD_CN.get(code) or "未命名用户价值")


def _business_value_name(name: str) -> str:
    return str(name).replace("价值战场", "").replace("战场", "").strip() or "未命名用户价值"


def _is_battlefield_semantic(item: dict[str, Any]) -> bool:
    code = str(item.get("dimension_code") or "")
    dimension_type = str(item.get("dimension_type") or "battlefield").lower()
    return code.startswith("BF_") and dimension_type == "battlefield"


def _option_name(option, report):
    for row in report.value_account_rows:
        if row.battlefield.get("code") == option.battlefield_code:
            return str(row.battlefield.get("name_cn") or "未命名价值战场")
    return ALL_BATTLEFIELD_CN.get(option.battlefield_code) or "未命名价值战场"


def _option_summary(option):
    if option.option_type == "strengthen_existing":
        return f"{MEMBERSHIP_CN[option.current_membership]}；{STRENGTHEN_CN[option.strengthen_path]}"
    eligibility = option.expansion_eligibility
    if eligibility and eligibility.eligible:
        return "现有用户需求、产品能力和同类产品表现都支持，可作为新产品方向比较"
    return "现有信息不足，暂不作为新增用户价值方向。"


def _market_number(context, *keys):
    for value in _market_values(context, keys):
        value = _number(value)
        if value is not None:
            return value
    return None


def _snapshot_market_number(snapshot: SkuEvidenceSnapshot, *keys: str) -> float | None:
    queue: list[Any] = [snapshot.market]
    wanted = set(keys)
    while queue:
        value = queue.pop(0)
        if isinstance(value, dict):
            for key in sorted(value):
                item = value[key]
                if key in wanted:
                    number = _number(item)
                    if number is not None:
                        return number
                if isinstance(item, (dict, list)):
                    queue.append(item)
        elif isinstance(value, list):
            queue.extend(item for item in value if isinstance(item, (dict, list)))
    return None


def _snapshot_weekly_sales(snapshot: SkuEvidenceSnapshot) -> float | None:
    weekly = _snapshot_market_number(
        snapshot,
        "avg_weekly_sales_volume",
        "average_weekly_sales_volume",
    )
    if weekly is not None:
        return weekly
    total = _snapshot_market_number(
        snapshot,
        "sales_volume_total",
        "sales_volume",
        "volume_total",
    )
    active_weeks = _snapshot_market_number(snapshot, "active_week_count")
    if total is None or active_weeks is None or active_weeks <= 0:
        return None
    return round(total / active_weeks, 6)


def _market_fraction(context, *keys):
    for value in _market_values(context, keys):
        value = _fraction(value)
        if value is not None:
            return value
    return None


def _market_values(context, keys):
    market = context.v4_context.target_snapshot.market
    sections = [
        market,
        market.get("market_metrics") or {},
        market.get("market_position") or {},
    ]
    aliases = {
        "avg_price": ("price_wavg",),
        "sales_volume": ("sales_volume_total",),
        "price_percentile": ("price_percentile_in_size",),
        "volume_percentile": ("volume_percentile_in_size",),
        "amount_percentile": ("amount_percentile_in_size",),
    }
    for key in keys:
        lookup_keys = (key, *aliases.get(key, ()))
        for section in sections:
            for lookup_key in lookup_keys:
                if lookup_key in section:
                    yield section.get(lookup_key)


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _fraction(value):
    number = _number(value)
    return number if number is not None and 0 <= number <= 1 else None


def _interval_text(interval):
    if interval.low is None or interval.high is None:
        return "不可识别"
    unit = "元" if interval.currency == "CNY" or interval.unit == "CNY" else interval.unit
    return f"{interval.low:,.0f}—{interval.high:,.0f} {unit}"


def _display_name(report):
    return report.target.model_name or report.target.sku_code


def _report_links(selection_compare_url, evidence_report_url):
    result = []
    if selection_compare_url:
        result.append({"label": "查看用户选择对比", "url": selection_compare_url, "type": "selection_compare"})
    if evidence_report_url:
        result.append({"label": "查看分析依据", "url": evidence_report_url, "type": "evidence_report"})
    return result


def _write_markdown_report(title: str, markdown: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", title).strip("-") or "report"
    path = Path(tempfile.mkdtemp(prefix="catforge-v5-report-")) / f"{safe}.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def _md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _compress(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


__all__ = [
    "adapt_v4_context_to_v5",
    "build_perceived_value_market_report",
    "build_v5_answer_artifacts",
    "pm_v5_business_output_issue",
    "render_v5_feishu_card",
    "render_v5_markdown",
    "render_v5_short_answer",
]
