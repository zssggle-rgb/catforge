from __future__ import annotations

import json

from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    _bundle_claim_codes,
    _dedupe_value_account_rows,
    _market_fraction,
    _market_number,
    _overall_price_summary,
    _parameter_dimension,
    _parameter_value_is_valid,
    _parameter_value_conclusion,
    _realization_market_comparisons,
    _select_highlights,
    _supported_claim_gaps,
    adapt_v4_context_to_v5,
    build_perceived_value_market_report,
    build_v5_answer_artifacts,
    pm_v5_business_output_issue,
    render_v5_feishu_card,
    render_v5_markdown,
    render_v5_short_answer,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_counterfactuals import (
    build_v5_counterfactual_sets,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    RealizationMarketComparison,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    LineageIssue,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    _value_unit_by_code,
    build_reason_value_bundle_links,
)
from tests.core3_real_data.test_claim_value_pm_v4_quantification import (
    _synthetic_context,
)
from tests.core3_real_data.test_claim_value_pm_v5_counterfactuals import (
    _v5_context,
)


def _report():
    return build_perceived_value_market_report(
        adapt_v4_context_to_v5(_synthetic_context())
    )


def test_v4_adapter_is_deterministic_and_reuses_only_existing_snapshots() -> None:
    v4 = _synthetic_context()

    first = adapt_v4_context_to_v5(v4)
    second = adapt_v4_context_to_v5(v4)

    assert first == second
    assert first.v4_context.input_hash == v4.input_hash
    assert {row.identity.sku_code for row in first.market_universe} == {
        v4.target.sku_code,
        *(row.identity.sku_code for row in v4.candidate_snapshots),
    }
    assert first.method_configs.amount_version == (
        "sellpoint_value_pm_v4_matched_wtp_config_v2"
    )
    assert len(first.battlefield_taxonomy) >= 13


def test_v4_adapter_does_not_treat_task_or_group_dimensions_as_battlefields() -> None:
    v4 = _synthetic_context()
    target = v4.target_snapshot.model_copy(
        update={
            "semantic_market": [
                *v4.target_snapshot.semantic_market,
                {
                    "dimension_type": "user_task",
                    "dimension_code": "TASK_WATCH_MOVIES",
                    "dimension_name": "影音观看任务",
                    "market_space": {"estimated_sales_volume": 1000},
                },
            ]
        }
    )

    context = adapt_v4_context_to_v5(
        v4.model_copy(update={"target_snapshot": target})
    )

    assert "TASK_WATCH_MOVIES" not in {
        row.battlefield_code for row in context.battlefield_taxonomy
    }


def test_report_first_screen_answers_four_pm_questions() -> None:
    report = _report()
    summary = report.decision_summary

    assert report.schema_version == "sellpoint_value_pm_v5_report_v1"
    assert report.analysis_state == "ready"
    assert len(summary.highlights) == 1
    assert summary.highlights[0].title_cn == "画质升级感"
    assert "价格溢价" in summary.highlights[0].reason_cn
    assert "1 组用户价值" in summary.price_summary_cn
    assert "当前没有形成可展示" in summary.volume_summary_cn
    assert "本品已覆盖 4 类用户价值" in summary.existing_battlefield_summary_cn
    assert "产品组合重点" in summary.existing_battlefield_summary_cn
    assert "优先比较" not in summary.existing_battlefield_summary_cn
    assert "没有明确的新用户价值方向" in summary.expansion_summary_cn


def test_report_uses_question_driven_comparisons_instead_of_pairwise_inventory() -> None:
    report = build_perceived_value_market_report(_v5_context())
    questions = report.market_reference["question_driven_comparisons"]
    short = render_v5_short_answer(report, max_chat_chars=10_000)

    assert "additional_comparisons" not in report.market_reference
    assert questions
    assert {row["question_cn"] for row in questions} == {
        "卖得好和卖得差的产品有什么不同"
    }
    assert "更多比较" not in short
    assert "逐一比较" not in short
    assert "不同参数组合" not in short


def test_shortfall_gap_requires_repeated_peer_support() -> None:
    context = _v5_context()
    snapshots = {row.identity.sku_code: row for row in context.market_universe}

    assert _supported_claim_gaps(
        snapshots,
        "DIRECT-LOWER",
        ["TARGET", "SAME-CLAIM"],
        {"CLAIM-PICTURE"},
    ) == ["CLAIM-PICTURE"]
    assert _supported_claim_gaps(
        snapshots,
        "DIRECT-LOWER",
        ["SAME-CLAIM", "BRAND-LOWER"],
        {"CLAIM-PICTURE"},
    ) == []


def test_parameter_value_comparison_never_crosses_parameter_dimensions() -> None:
    context = _v5_context()
    report = build_perceived_value_market_report(context)
    bundle = report.value_account_rows[0].sellpoint_bundle
    definitions = _value_unit_by_code(context.category_code)
    claim_codes = {
        claim_code
        for member in bundle.members
        for claim_code in definitions[member.capability_code].claim_codes
    }
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    for sku_code in ("DIRECT-LOWER", "SAME-CLAIM"):
        snapshot = snapshots[sku_code]
        snapshots[sku_code] = snapshot.model_copy(
            update={
                "facts": {
                    **snapshot.facts,
                    "supported_claim_codes": sorted(claim_codes),
                }
            }
        )
    comparisons = [
        RealizationMarketComparison(
            method="parameter_configuration",
            comparison_basis_cn=basis,
            comparator_sku_codes=codes,
            comparator_names=codes,
            comparator_count=2,
            evidence_strength="candidate",
            causal_claim=False,
        )
        for basis, codes in (
            ("参数组合：backlight_subtype=Q-LED", ["DIRECT-LOWER", "SAME-CLAIM"]),
            ("参数组合：backlight_subtype=MiniLED", ["BRAND-LOWER", "DONOR-0"]),
            ("参数组合：local_dimming_zone_count=0", ["BRAND-LOWER", "DONOR-1"]),
        )
    ]

    result = _parameter_value_conclusion(
        snapshots,
        {
            "bundle": bundle,
            "value_name_cn": "画质升级感",
            "comparisons": comparisons,
        },
        definitions,
    )

    assert _parameter_dimension("参数组合：backlight_subtype=Q-LED") == "backlight_subtype"
    assert _parameter_value_is_valid("参数组合：backlight_subtype=Q-LED") is True
    assert _parameter_value_is_valid("参数组合：color_gamut_ratio=0") is False
    assert _parameter_value_is_valid("参数组合：local_dimming_zone_count=0") is True
    assert result is not None
    assert "背光类型=Q-LED" in result["conclusion_cn"]
    assert "分区数" not in result["conclusion_cn"]


def test_highlight_summary_keeps_one_specific_result_per_battlefield() -> None:
    base = _report().value_account_rows[0]
    concise = base.model_copy(
        update={
            "value_status": "partial",
            "highlight_types": ["relative_value"],
            "perceived_user_value": {
                **base.perceived_user_value,
                "name_cn": "画质升级感",
                "outcome_cn": "用户购后反馈只部分支持：明暗层次更清楚。",
            },
            "sellpoint_bundle": base.sellpoint_bundle.model_copy(
                update={"bundle_code": "bundle:picture-specific"}
            ),
        }
    )
    overlapping = concise.model_copy(
        update={
            "perceived_user_value": {
                **concise.perceived_user_value,
                "name_cn": "客厅沉浸感＋画质升级感",
            },
            "sellpoint_bundle": concise.sellpoint_bundle.model_copy(
                update={"bundle_code": "bundle:picture-overlap"}
            ),
        }
    )

    highlights = _select_highlights([overlapping, concise])

    assert len(highlights) == 1
    assert highlights[0].title_cn == "画质升级感"
    assert "用户实际体验认可了“明暗层次更清楚”" in highlights[0].reason_cn
    assert "用户购后反馈只部分支持" not in highlights[0].reason_cn


def test_value_account_separates_user_value_price_and_volume() -> None:
    row = _report().value_account_rows[0]

    assert row.perceived_user_value["name_cn"] == "画质升级感"
    assert row.perceived_user_value["outcome_cn"]
    assert row.value_status == "observed_positive"
    assert row.price_realization.strict_bundle_interval is not None
    assert row.price_realization.strict_bundle_interval.status == "available"
    assert row.volume_realization.synthetic_difference is None
    assert row.increment is not None
    assert row.increment.net is None
    assert row.increment.cannibalization is None


def test_nested_m07_market_payload_reaches_realization_accounting() -> None:
    v4 = _synthetic_context()
    target = v4.target_snapshot.model_copy(
        update={
            "market": {
                "market_metrics": {
                    "price_wavg": 5949.39,
                    "sales_volume_total": 6023,
                },
                "market_position": {
                    "same_pool_price_percentile": 0.72,
                    "same_pool_volume_percentile": 0.64,
                    "same_pool_amount_percentile": 0.68,
                },
            }
        }
    )
    context = adapt_v4_context_to_v5(
        v4.model_copy(update={"target_snapshot": target})
    )

    assert _market_number(context, "price_wavg", "avg_price") == 5949.39
    assert _market_number(context, "sales_volume_total", "sales_volume") == 6023
    assert _market_fraction(
        context, "same_pool_price_percentile", "price_percentile"
    ) == 0.72
    assert _market_fraction(
        context, "same_pool_volume_percentile", "volume_percentile"
    ) == 0.64
    assert _market_fraction(
        context, "same_pool_amount_percentile", "amount_percentile"
    ) == 0.68


def test_bundle_capabilities_expand_to_value_specific_claim_codes() -> None:
    context = _synthetic_context()
    link = build_reason_value_bundle_links(context)[0]

    claims = _bundle_claim_codes(link, context.category_code)

    assert claims
    assert all(code.startswith("tv_claim_") for code in claims)


def test_same_claim_different_realization_quantifies_price_and_sales() -> None:
    context = _v5_context()
    sets = build_v5_counterfactual_sets(
        context,
        bundle_code="picture_bundle",
        focus_dimension_codes=["picture"],
        focus_claim_codes=["CLAIM-PICTURE"],
    )

    comparison = _realization_market_comparisons(context, sets)[0]

    assert comparison.comparator_sku_codes == ["SAME-CLAIM"]
    assert comparison.evidence_strength == "confirmed"
    assert comparison.price_gap_abs == 500
    assert comparison.price_gap_pct == 0.090909
    assert comparison.sales_volume_gap_abs == 41.666666
    assert comparison.sales_volume_gap_pct == 1.0


def test_market_realization_highlight_answers_sales_contribution() -> None:
    row = _report().value_account_rows[0]
    comparison = RealizationMarketComparison(
        method="same_claim_different_realization",
        comparator_sku_codes=["PEER"],
        comparator_names=["可比机型"],
        comparator_count=1,
        shared_claim_codes=["tv_claim_picture"],
        evidence_strength="confirmed",
        target_price=6000,
        comparator_price_median=5500,
        price_gap_abs=500,
        price_gap_pct=0.090909,
        target_sales_volume=2000,
        comparator_sales_volume_median=1000,
        sales_volume_gap_abs=1000,
        sales_volume_gap_pct=1.0,
        causal_claim=False,
    )
    row = row.model_copy(
        update={
            "highlight_types": ["market_realization"],
            "price_realization": row.price_realization.model_copy(
                update={"realization_comparisons": [comparison]}
            ),
            "volume_realization": row.volume_realization.model_copy(
                update={"realization_comparisons": [comparison]}
            ),
        }
    )

    highlight = _select_highlights([row])[0]

    assert highlight.highlight_type == "market_realization"
    assert "500元（9.1%）的价格溢价" in highlight.reason_cn
    assert "1000.0台/周（100.0%）的销量优势" in highlight.reason_cn
    assert "应继续保留并强化" in highlight.reason_cn


def test_overall_price_summary_does_not_call_a_negative_gap_premium() -> None:
    row = _report().value_account_rows[0]
    comparison = RealizationMarketComparison(
        method="same_claim_different_realization",
        comparator_sku_codes=["PEER"],
        comparator_names=["可比机型"],
        comparator_count=1,
        shared_claim_codes=["tv_claim_picture"],
        evidence_strength="confirmed",
        target_price=1790,
        comparator_price_median=1821,
        price_gap_abs=-31,
        price_gap_pct=-0.017,
        target_sales_volume=100,
        comparator_sales_volume_median=120,
        sales_volume_gap_abs=-20,
        sales_volume_gap_pct=-0.166667,
        causal_claim=False,
    )
    row = row.model_copy(
        update={
            "price_realization": row.price_realization.model_copy(
                update={"realization_comparisons": [comparison]}
            )
        }
    )

    summary = _overall_price_summary([row])

    assert "没有形成“均价更高且销量不弱”的价格支撑" in summary
    assert "最具体一组均价低 31元（1.7%）" in summary
    assert "带来价格溢价" not in summary


def test_no_evidence_does_not_force_a_highlight() -> None:
    report = build_perceived_value_market_report(_v5_context())

    assert report.decision_summary.highlights == []
    assert all(
        not row.price_realization.realization_comparisons
        for row in report.value_account_rows
    )
    assert report.decision_summary.no_highlight_reason_cn == (
        "当前未识别出同时具备具体用户结果和可靠相对证据的亮点。"
    )


def test_blocked_lineage_suppresses_all_highlights() -> None:
    v4 = _synthetic_context()
    gate = v4.lineage_gate.model_copy(
        update={
            "status": "stale_conflict",
            "issues": [
                LineageIssue(
                    code="version_lineage_conflict",
                    severity="blocking",
                    scope="report",
                    message_cn="来源版本冲突",
                    affected_module_codes=["M05C"],
                )
            ],
            "blocked_reason_codes": ["version_lineage_conflict"],
        }
    )
    report = build_perceived_value_market_report(
        adapt_v4_context_to_v5(v4.model_copy(update={"lineage_gate": gate}))
    )

    assert report.analysis_state == "blocked"
    assert report.decision_summary.highlights == []
    assert "来源版本存在冲突" in report.decision_summary.no_highlight_reason_cn


def test_opportunity_is_existing_and_unknown_excluded_is_not_expansion() -> None:
    report = _report()
    opportunity = next(
        row for row in report.battlefield_options if row.current_membership == "opportunity"
    )

    assert opportunity.option_type == "strengthen_existing"
    assert opportunity.strengthen_path == "portfolio_priority"
    assert any(row.option_type == "expand_excluded" for row in report.battlefield_options)
    assert not any(
        row.expansion_eligibility and row.expansion_eligibility.eligible
        for row in report.battlefield_options
    )


def test_markdown_is_pm_value_account_without_internal_or_causal_language() -> None:
    markdown = render_v5_markdown(_report())

    assert (
        "| 用户价值 | 用户实际怎么感知 | 哪些卖点共同形成 | 对比哪些同类产品 | 带来多少价格溢价 | 带来多少销量优势 | 产品判断 |"
        in markdown
    )
    assert "高/低表现组合" not in markdown
    assert "已有用户价值" in markdown
    assert "家庭护眼舒适" in markdown
    assert pm_v5_business_output_issue(markdown) is None
    for forbidden in (
        "BF_",
        "M11D",
        "WTP",
        "反事实",
        "用户兑现",
        "市场隐含支付意愿",
        "价格承接",
        "销量承接",
        "战场",
        "门槛",
        "任务相邻",
        "增加销量",
        "下一步工作清单",
        "建议涨价",
        "建议减配",
    ):
        assert forbidden not in markdown


def test_markdown_collapses_repeated_unavailable_market_references() -> None:
    report = _report()
    repeated = "当前合成池未通过共同市场、平衡或样本门槛，不能输出销量差。"
    market_reference = {
        **report.market_reference,
        "synthetic_baselines": [
            {
                "bundle_name_cn": f"价值组合 {index}",
                "summary_cn": repeated,
                "donor_count": 0,
            }
            for index in range(5)
        ],
        "high_performance": {"summary_cn": "当前样本不足以形成稳定的高表现价值组合原型。"},
        "low_performance": {"summary_cn": "当前样本不足以形成稳定的低表现价值组合原型。"},
    }

    markdown = render_v5_markdown(
        report.model_copy(update={"market_reference": market_reference})
    )

    assert markdown.count(repeated) == 0
    assert "同类产品市场基准（覆盖 5 组用户价值）" not in markdown
    assert "高/低表现组合" not in markdown


def test_short_markdown_and_card_consume_same_report_and_dual_links() -> None:
    report = _report()
    links = [
        {
            "label": "查看用户选择对比",
            "url": "https://example.com/compare",
            "type": "selection_compare",
        },
        {
            "label": "查看分析依据",
            "url": "https://example.com/evidence",
            "type": "evidence_report",
        },
    ]

    short = render_v5_short_answer(report, links=links)
    markdown = render_v5_markdown(report, links=links)
    card = render_v5_feishu_card(report, links=links)

    assert report.decision_summary.highlights[0].title_cn in short
    assert report.decision_summary.highlights[0].title_cn in markdown
    assert report.decision_summary.highlights[0].title_cn in json.dumps(
        card, ensure_ascii=False
    )
    assert "查看用户选择对比：https://example.com/compare" in short
    assert "[查看分析依据](https://example.com/evidence)" in markdown
    buttons = [item for item in card["body"]["elements"] if item.get("tag") == "button"]
    assert [item["text"]["content"] for item in buttons] == [
        "查看用户选择对比",
        "查看分析依据",
    ]


def test_artifacts_share_one_result_hash_and_renderers_do_not_recalculate() -> None:
    report = _report()
    artifacts = build_v5_answer_artifacts(
        report,
        selection_compare_url="https://example.com/compare",
        evidence_report_url="https://example.com/evidence",
    )

    assert artifacts["result_hash"] == report.result_hash
    assert artifacts["report_ref"]["result_hash"] == report.result_hash
    assert artifacts["report_delivery"]["status"] == "disabled"
    assert artifacts["markdown"] is None


def test_business_dto_does_not_duplicate_large_evidence_payloads() -> None:
    report = _report()
    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert len(payload.encode("utf-8")) < 1_000_000
    assert all(
        not candidate.source_refs
        for row in report.value_account_rows
        for counterfactual_set in row.counterfactual_sets
        for candidate in counterfactual_set.candidates
    )
    assert all(not row.source_refs for row in report.value_account_rows)
    assert all(
        not member.source_refs
        for row in report.value_account_rows
        for member in row.sellpoint_bundle.members
    )


def test_same_battlefield_and_capability_combination_is_one_value_account() -> None:
    row = _report().value_account_rows[0]
    duplicate = row.model_copy(
        update={
            "perceived_user_value": {
                **row.perceived_user_value,
                "name_cn": "客厅沉浸感＋画质升级感",
            },
            "sellpoint_bundle": row.sellpoint_bundle.model_copy(
                update={"bundle_code": "duplicate-purchase-reason-bundle"}
            ),
        }
    )

    result = _dedupe_value_account_rows([row, duplicate])

    assert len(result) == 1


def test_report_and_renderers_are_deterministic() -> None:
    first = _report()
    second = _report()

    assert first == second
    assert render_v5_short_answer(first) == render_v5_short_answer(second)
    assert render_v5_markdown(first) == render_v5_markdown(second)
    assert render_v5_feishu_card(first) == render_v5_feishu_card(second)
