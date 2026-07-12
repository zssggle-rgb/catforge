from __future__ import annotations

import json

from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    _dedupe_value_account_rows,
    _market_fraction,
    _market_number,
    _select_highlights,
    adapt_v4_context_to_v5,
    build_perceived_value_market_report,
    build_v5_answer_artifacts,
    pm_v5_business_output_issue,
    render_v5_feishu_card,
    render_v5_markdown,
    render_v5_short_answer,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    LineageIssue,
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
    assert "稳定价格承接" in summary.highlights[0].reason_cn
    assert "1 组价值" in summary.price_summary_cn
    assert "无法识别销量承接" in summary.volume_summary_cn
    assert "已进入 4 个" in summary.existing_battlefield_summary_cn
    assert "组合优先级问题" in summary.existing_battlefield_summary_cn
    assert "优先比较" not in summary.existing_battlefield_summary_cn
    assert "未识别出" in summary.expansion_summary_cn


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
    assert "用户购后反馈显示“明暗层次更清楚”" in highlights[0].reason_cn
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


def test_no_evidence_does_not_force_a_highlight() -> None:
    report = build_perceived_value_market_report(_v5_context())

    assert report.decision_summary.highlights == []
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
        "| 用户价值 | 用户实际怎么感知 | 哪些卖点共同形成 | 相对市场是什么位置 | 价格承接 | 销量承接 | 当前结论边界 |"
        in markdown
    )
    assert "高表现组合" in markdown
    assert "已有战场增强" in markdown
    assert "家庭护眼舒适" in markdown
    assert pm_v5_business_output_issue(markdown) is None
    for forbidden in (
        "BF_",
        "M11D",
        "WTP",
        "增加销量",
        "下一步工作清单",
        "建议涨价",
        "建议减配",
    ):
        assert forbidden not in markdown


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
