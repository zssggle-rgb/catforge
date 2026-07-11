from __future__ import annotations

import json

from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    adapt_v4_context_to_v5,
    build_perceived_value_market_report,
    build_v5_answer_artifacts,
    pm_v5_business_output_issue,
    render_v5_feishu_card,
    render_v5_markdown,
    render_v5_short_answer,
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
    assert "未识别出" in summary.expansion_summary_cn


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


def test_no_evidence_does_not_force_a_highlight() -> None:
    report = build_perceived_value_market_report(_v5_context())

    assert report.decision_summary.highlights == []
    assert report.decision_summary.no_highlight_reason_cn == (
        "当前未识别出同时具备具体用户结果和可靠相对证据的亮点。"
    )


def test_opportunity_is_existing_and_unknown_excluded_is_not_expansion() -> None:
    report = _report()
    opportunity = next(
        row for row in report.battlefield_options if row.current_membership == "opportunity"
    )

    assert opportunity.option_type == "strengthen_existing"
    assert opportunity.strengthen_path == "portfolio_priority"
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


def test_report_and_renderers_are_deterministic() -> None:
    first = _report()
    second = _report()

    assert first == second
    assert render_v5_short_answer(first) == render_v5_short_answer(second)
    assert render_v5_markdown(first) == render_v5_markdown(second)
    assert render_v5_feishu_card(first) == render_v5_feishu_card(second)
