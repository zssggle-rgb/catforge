"""Product-manager report assembly and renderers for sellpoint-value V5."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, Sequence

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    ReasonValueBundleLink,
    SellpointValueV4Context,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    build_counterfactual_assessments,
    build_reason_value_bundle_links,
    quantify_sellpoint_value,
)
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
from app.services.core3_real_data.analyst.competitor_answer import _publish_report


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
    "primary": "主战场",
    "secondary": "辅战场",
    "opportunity": "机会战场（本品已进入）",
    "user_observed": "用户已观察战场",
    "drag": "拖累战场",
    "excluded": "当前未进入战场",
}
METHOD_CN = {
    "direct_sku": "直接竞品",
    "same_budget_pool": "同预算产品",
    "same_brand_size_ladder": "同品牌同尺寸梯度",
    "param_tier_pool": "参数档位产品",
    "same_claim_realization": "同宣传、不同用户兑现产品",
    "own_price_curve": "本品历史价格变化",
    "market_synthetic": "市场合成基线",
    "performance_archetype": "高低表现组合",
}
STRENGTHEN_CN = {
    "communication_activation": "表达激活",
    "capability_completion": "能力补全",
    "market_activation": "市场承接复核",
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


def adapt_v4_context_to_v5(v4_context: SellpointValueV4Context) -> SellpointValueV5Context:
    """Reuse the immutable V4 evidence context without querying another source."""

    universe = [v4_context.target_snapshot, *v4_context.candidate_snapshots]
    by_code = {row.identity.sku_code: row for row in universe}
    ordered = [by_code[code] for code in sorted(by_code)]
    battlefield_names: dict[str, str] = {}
    for snapshot in ordered:
        for item in snapshot.semantic_market:
            code = str(item.get("dimension_code") or "").strip()
            if code:
                battlefield_names.setdefault(
                    code, str(item.get("dimension_name") or TV_BATTLEFIELD_CN.get(code) or "")
                )
        for item in snapshot.battlefields:
            for code in _entered_codes(item):
                battlefield_names.setdefault(code, TV_BATTLEFIELD_CN.get(code, ""))
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
            recall_version="sellpoint_value_pm_v5_counterfactual_recall_v1",
            synthetic_version="sellpoint_value_pm_v5_synthetic_control_v1",
            archetype_version="sellpoint_value_pm_v5_performance_archetype_v1",
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
    qa_relations: list[dict[str, Any]] = []
    allocations = _battlefield_allocations(context)
    for link in links:
        focus_dimensions = [member.capability_code for member in link.bundle.members]
        focus_claims = _bundle_claim_codes(link)
        sets = build_v5_counterfactual_sets(
            context,
            bundle_code=link.bundle.bundle_code,
            focus_dimension_codes=focus_dimensions,
            focus_claim_codes=focus_claims,
        )
        synthetic = _synthetic_for_bundle(context, link.bundle.bundle_code, sets)
        synthetic_by_bundle[link.bundle.bundle_code] = synthetic
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
                direct_and_pool_gaps=[],
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
                limitations=[],
            )
        )
        value_status = _v5_value_status(link)
        row_allocation = next(
            (item for item in allocations if item.battlefield_code == link.battlefield_code),
            None,
        )
        rows.append(
            ValueAccountRow(
                battlefield={
                    "code": link.battlefield_code,
                    "name_cn": link.battlefield_name_cn
                    or TV_BATTLEFIELD_CN.get(link.battlefield_code)
                    or "未命名价值战场",
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
                counterfactual_summary_cn=_counterfactual_summary_cn(sets),
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
    market_reference = _market_reference_cn(rows, synthetic_by_bundle, archetypes)
    payload: dict[str, Any] = {
        "schema_version": "sellpoint_value_pm_v5_report_v1",
        "target": context.v4_context.target,
        "analysis_state": analysis_state,
        "decision_summary": decision,
        "value_account_rows": rows,
        "market_reference": market_reference,
        "battlefield_options": options,
        "overall_boundary_cn": (
            "本报告只说明用户购后感知、可比市场中的选择与量价承接；"
            "观察性差异不是因果增量，无法识别时不补数字。"
        ),
        "data_scope_cn": (
            "使用已发布采购理由、产品事实、用户购后体验、周度市场量价和当前战场分配；"
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
    title = report_title or f"{_display_name(report)} 用户感知价值与市场兑现"
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
    lines.extend(
        [
            f"价格承接｜{report.decision_summary.price_summary_cn}",
            f"销量承接｜{report.decision_summary.volume_summary_cn}",
            f"已有战场｜{report.decision_summary.existing_battlefield_summary_cn}",
            f"新战场｜{report.decision_summary.expansion_summary_cn}",
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
    title = title or f"{_display_name(report)} 用户感知价值与市场兑现"
    lines = [f"# {_md(title)}", "", "## 一、产品经理现在能用的结论", ""]
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
    lines.extend(
        [
            f"- **价格承接**：{_md(report.decision_summary.price_summary_cn)}",
            f"- **销量承接**：{_md(report.decision_summary.volume_summary_cn)}",
            f"- **已有战场**：{_md(report.decision_summary.existing_battlefield_summary_cn)}",
            f"- **新战场**：{_md(report.decision_summary.expansion_summary_cn)}",
            "",
            "## 二、用户价值账",
            "",
            "| 用户价值 | 用户实际怎么感知 | 哪些卖点共同形成 | 相对市场是什么位置 | 价格承接 | 销量承接 | 当前结论边界 |",
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
    lines.extend(["", "## 三、市场参照", ""])
    for item in report.market_reference.get("synthetic_baselines", []):
        lines.append(f"- **{_md(item['bundle_name_cn'])}**：{_md(item['summary_cn'])}")
    lines.extend(
        [
            f"- **高表现组合**：{_md(report.market_reference['high_performance']['summary_cn'])}",
            f"- **低表现组合**：{_md(report.market_reference['low_performance']['summary_cn'])}",
            "",
            "## 四、价值战场组合",
            "",
            "| 已有战场增强 | 当前判断 | 新战场拓展 | 当前判断 |",
            "| --- | --- | --- | --- |",
        ]
    )
    existing = [row for row in report.battlefield_options if row.option_type == "strengthen_existing"]
    expansion = [row for row in report.battlefield_options if row.option_type == "expand_excluded"]
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


def render_v5_feishu_card(
    report: SkuPerceivedValueMarketRealizationReport,
    *,
    title: str | None = None,
    links: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    title = title or f"{_display_name(report)} 用户感知价值与市场兑现"
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


def _battlefield_allocations(context: SellpointValueV5Context) -> list[BattlefieldAllocation]:
    result = []
    for item in context.v4_context.target_snapshot.semantic_market:
        code = str(item.get("dimension_code") or "").strip()
        if not code:
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
                battlefield_name_cn=names.get(code) or TV_BATTLEFIELD_CN.get(code) or "未命名价值战场",
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
    candidates: list[tuple[float, ValueHighlight]] = []
    for row in rows:
        types = row.highlight_types
        if not types:
            continue
        value_name = str(row.perceived_user_value.get("name_cn") or "").strip()
        outcome = str(row.perceived_user_value.get("outcome_cn") or "").strip()
        if not value_name or not outcome:
            continue
        if "relative_value" in types:
            highlight_type = "relative_value"
            reason = f"用户实际获得“{outcome}”，且同类市场中存在同宣传但兑现较弱的可比产品。"
            score = 4.0
        elif "volume_realization" in types:
            highlight_type = "volume_realization"
            reason = f"用户实际获得“{outcome}”，并在控制基础条件后的市场基线中表现出更强销量承接。"
            score = 3.0
        elif "price_realization" in types:
            highlight_type = "price_realization"
            reason = f"用户实际获得“{outcome}”，可比市场支持这组价值存在稳定价格承接。"
            score = 2.5
        else:
            highlight_type = "user_realization"
            reason = f"用户实际获得“{outcome}”，不是仅由技术参数推演出的好处。"
            score = 2.0
        candidates.append(
            (
                score,
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
    candidates.sort(key=lambda item: (-item[0], item[1].bundle_code))
    result = []
    seen: set[str] = set()
    for _, item in candidates:
        key = "＋".join(sorted(part.strip() for part in item.title_cn.split("＋")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) == 3:
            break
    return result


def _no_highlight_reason_cn(context, analysis_state):
    if analysis_state == "blocked" and context.v4_context.lineage_gate.status == "stale_conflict":
        return "当前来源版本存在冲突，亮点判断已暂停；不能把尚未对齐的用户价值与市场参照合并成结论。"
    return "当前未识别出同时具备具体用户结果和可靠相对证据的亮点。"


def _eligible_highlight_types(value_status, sets, accounting, synthetic_control):
    if value_status not in {"observed_positive", "partial"}:
        return []
    result = ["user_realization"] if value_status == "observed_positive" else []
    user_set = next(row for row in sets if row.question == "user_realization")
    if user_set.highest_available_method == "same_claim_realization":
        result.append("relative_value")
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


def _market_reference_cn(rows, synthetic_by_bundle, archetypes):
    baselines = []
    names = {row.sellpoint_bundle.bundle_code: row.sellpoint_bundle.bundle_name_cn for row in rows}
    for code, result in sorted(synthetic_by_bundle.items()):
        if result.status == "available" and result.sales_difference is not None:
            summary = (
                "与较弱该组价值的合成市场相比，本品每个共同市场单元的观察性销量差约 "
                f"{_interval_text(result.sales_difference)}；这不是因果新增销量。"
            )
        else:
            summary = "当前合成池未通过共同市场、平衡或样本门槛，不能输出销量差。"
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
        "high_performance": _archetype_cn(high, "高表现"),
        "low_performance": _archetype_cn(low, "低表现"),
    }


def _archetype_cn(row: PerformanceArchetype | None, label: str) -> dict[str, Any]:
    if row is None or row.role == "unstable":
        return {"summary_cn": f"当前样本不足以形成稳定的{label}价值组合原型。"}
    return {
        "summary_cn": (
            f"{label}组包含 {row.sku_count} 个稳定样本；只展示组合共现，"
            "不能拆成单卖点因果贡献。"
        ),
        "sku_count": row.sku_count,
    }


def _overall_price_summary(rows: Sequence[ValueAccountRow]) -> str:
    available = [
        row.price_realization.strict_bundle_interval
        for row in rows
        if row.price_realization.strict_bundle_interval is not None
        and row.price_realization.strict_bundle_interval.status == "available"
    ]
    if available:
        return f"{len(available)} 组价值通过严格可比门槛形成市场价格承接区间；其余组合不补金额。"
    percentile = next(
        (
            _fraction(row.price_realization.market_position.get("price_percentile"))
            for row in rows
            if _fraction(row.price_realization.market_position.get("price_percentile")) is not None
        ),
        None,
    )
    if percentile is not None:
        return f"整机价格约处于同池第 {round(percentile * 100)} 百分位，但尚不能拆出单组价值金额。"
    return "现有数据无法识别价格承接，未用销量或评论数量代填。"


def _overall_volume_summary(rows: Sequence[ValueAccountRow]) -> str:
    positive = [
        row
        for row in rows
        if row.volume_realization.synthetic_difference is not None
        and row.volume_realization.synthetic_difference.low is not None
        and row.volume_realization.synthetic_difference.low > 0
    ]
    if positive:
        return f"{len(positive)} 组价值相对合成市场基线呈正向观察性销量差；不等于因果新增。"
    percentile = next(
        (
            _fraction(row.volume_realization.raw_market_position.get("volume_percentile"))
            for row in rows
            if _fraction(row.volume_realization.raw_market_position.get("volume_percentile")) is not None
        ),
        None,
    )
    if percentile is not None:
        return f"整机销量约处于同池第 {round(percentile * 100)} 百分位，控制后差异尚不可识别。"
    return "现有数据无法识别销量承接，当前战场分配不作为新增销量。"


def _existing_summary(options, context):
    existing = [row for row in options if row.option_type == "strengthen_existing"]
    if not existing:
        return "当前没有可用的已进入战场资料。"
    first = existing[0]
    return (
        f"已进入 {len(existing)} 个可复核战场；优先比较“{_battlefield_name(context, first.battlefield_code)}”"
        f"的{STRENGTHEN_CN[first.strengthen_path]}方案，不自动下达增减配指令。"
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
        return f"识别出 {len(eligible)} 个真实可达的未进入战场候选：{names}；仅作为方案比较。"
    return "当前未识别出同时通过市场门槛、任务相邻性、能力缺口和对照样本的新战场候选。"


def _counterfactual_summary_cn(sets: Sequence[CounterfactualSet]) -> str:
    methods = []
    for row in sets:
        if row.highest_available_method is not None:
            name = METHOD_CN[row.highest_available_method]
            if name not in methods:
                methods.append(name)
    if methods:
        return "可用参照：" + "、".join(methods[:3])
    return "当前只有召回候选，没有通过可比门槛的相对参照。"


def _row_boundary_cn(value_status, price: PriceRealization, volume: VolumeRealization) -> str:
    if value_status in {"not_observed", "unknown", "conflicted"}:
        return "用户价值尚未稳定成立，不能进入价格或销量归因。"
    if price.strict_bundle_interval and price.strict_bundle_interval.status == "available":
        return "价值已被用户感知，金额只代表可比市场中的组合价格承接，不代表用户个人的最高接受价格。"
    if volume.synthetic_difference is not None:
        return "价值已被用户感知，销量差为观察性市场参照，不是因果新增。"
    return "价值感知与金额可识别是两个维度；当前价值可复核，但独立量化仍不足。"


def _price_cn(price: PriceRealization) -> str:
    interval = price.strict_bundle_interval
    if interval and interval.status == "available" and interval.estimate is not None:
        return f"价值组合的市场价格承接区间约 {_interval_text(interval.estimate)}"
    percentile = _fraction(price.market_position.get("price_percentile"))
    if percentile is not None:
        return f"整机价格位于同池第 {round(percentile * 100)} 百分位，组合金额不可识别"
    return "现有数据无法识别价格承接"


def _volume_cn(volume: VolumeRealization) -> str:
    if volume.synthetic_difference is not None:
        return f"相对合成市场的观察性销量差约 {_interval_text(volume.synthetic_difference)}"
    percentile = _fraction(volume.raw_market_position.get("volume_percentile"))
    if percentile is not None:
        return f"整机销量位于同池第 {round(percentile * 100)} 百分位，控制后差异不可识别"
    return "现有数据无法识别销量承接"


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


def _bundle_claim_codes(link: ReasonValueBundleLink) -> list[str]:
    result = []
    for member in link.bundle.members:
        code = member.capability_code
        if code.upper().startswith("CLAIM"):
            result.append(code)
    return result


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
            if str(item.get("dimension_code") or "") == code and item.get("market_space"):
                return item["market_space"]
    return {}


def _battlefield_name(context, code):
    for row in context.battlefield_taxonomy:
        if row.battlefield_code == code:
            return row.battlefield_name_cn or TV_BATTLEFIELD_CN.get(code) or "未命名价值战场"
    return TV_BATTLEFIELD_CN.get(code) or "未命名价值战场"


def _option_name(option, report):
    for row in report.value_account_rows:
        if row.battlefield.get("code") == option.battlefield_code:
            return str(row.battlefield.get("name_cn") or "未命名价值战场")
    return TV_BATTLEFIELD_CN.get(option.battlefield_code) or "未命名价值战场"


def _option_summary(option):
    if option.option_type == "strengthen_existing":
        return f"{MEMBERSHIP_CN[option.current_membership]}；{STRENGTHEN_CN[option.strengthen_path]}"
    eligibility = option.expansion_eligibility
    if eligibility and eligibility.eligible:
        return "当前进入条件和可比样本均满足，可作为拓展方案比较"
    return option.evidence_boundary


def _market_number(context, *keys):
    market = context.v4_context.target_snapshot.market
    for key in keys:
        value = _number(market.get(key))
        if value is not None:
            return value
    return None


def _market_fraction(context, *keys):
    market = context.v4_context.target_snapshot.market
    for key in keys:
        value = _fraction(market.get(key))
        if value is not None:
            return value
    return None


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
