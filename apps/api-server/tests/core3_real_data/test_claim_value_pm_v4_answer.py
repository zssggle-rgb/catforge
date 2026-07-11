from __future__ import annotations

import json
from pathlib import Path

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_answer import (
    build_product_value_answer_artifacts,
    build_product_value_realization_report,
    pm_business_output_issue,
    render_product_value_feishu_card,
    render_product_value_markdown,
    render_product_value_short_answer,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    SellpointValueV4Context,
)
from tests.core3_real_data.test_claim_value_pm_v4_counterfactual import (
    _base_context,
    _candidate,
)
from tests.core3_real_data.test_claim_value_pm_v4_linkage import _atom, _context
from tests.core3_real_data.test_claim_value_pm_v4_quantification import (
    _synthetic_context,
)


def test_report_builds_one_pm_value_account_from_the_same_analysis() -> None:
    context = _synthetic_context()

    first = build_product_value_realization_report(context)
    second = build_product_value_realization_report(context)

    assert first == second
    assert first.schema_version == "sellpoint_value_pm_v4_result_v1"
    assert first.analysis_status == "ready"
    assert len(first.value_structure_rows) == 1
    row = first.value_structure_rows[0]
    assert row.purchase_reason["name_cn"] == "画质配置解释加价"
    assert row.battlefield["scope_cn"] == "65-75 英寸档、完整观察期、jd+tmall 平台"
    assert row.realized_user_value["status_cn"] == "用户已实际感知到这项价值"
    assert row.selection_price_realization.wtp.status == "available"
    assert row.selection_price_realization.wtp.estimate_low == 400
    assert row.selection_price_realization.wtp.estimate_high == 500
    assert row.product_role == "core_differentiated_value"
    assert (
        first.overall_quantification_boundary["market_implied_payment_available_count"]
        == 1
    )


def test_markdown_is_the_fixed_seven_column_pm_table_without_internal_codes() -> None:
    report = build_product_value_realization_report(_synthetic_context())

    markdown = render_product_value_markdown(report)

    assert (
        "| 价值战场及市场空间 | 本品核心采购理由 | 用户实际获得的价值 | 支撑卖点组合 | 相对基础与同价值竞品 | 选择和价格兑现 | 产品角色 |"
        in markdown
    )
    assert "画质配置解释加价" in markdown
    assert "65-75 英寸档、完整观察期、jd+tmall 平台" in markdown
    assert "市场隐含支付区间约 400-500 元" in markdown
    assert "无法量化不等于没有价值" in markdown
    assert pm_business_output_issue(markdown) is None
    for forbidden in (
        "M11C",
        "M12D",
        "Q5_",
        "isolation_grade",
        "evidence_id",
        "下一步工作清单",
        "建议涨价",
        "建议降价",
        "增配",
        "减配",
    ):
        assert forbidden not in markdown


def test_short_markdown_and_card_consume_the_same_row_and_dual_links() -> None:
    report = build_product_value_realization_report(_synthetic_context())
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

    short = render_product_value_short_answer(report, links=links, max_chat_chars=900)
    markdown = render_product_value_markdown(report, links=links)
    card = render_product_value_feishu_card(report, links=links)

    reason = report.value_structure_rows[0].purchase_reason["name_cn"]
    assert reason in short
    assert reason in markdown
    assert reason in json.dumps(card, ensure_ascii=False)
    assert "查看用户选择对比：https://example.com/compare" in short
    assert "[查看分析依据](https://example.com/evidence)" in markdown
    buttons = [item for item in card["body"]["elements"] if item.get("tag") == "button"]
    assert [item["text"]["content"] for item in buttons] == [
        "查看用户选择对比",
        "查看分析依据",
    ]


def test_unquantifiable_value_is_not_rendered_as_zero_value() -> None:
    report = build_product_value_realization_report(
        _synthetic_context(single_week=True)
    )

    markdown = render_product_value_markdown(report)
    row = report.value_structure_rows[0]

    assert row.selection_price_realization.value_status == "established"
    assert row.selection_price_realization.wtp.estimate_low is None
    assert "用户已实际感知到这项价值" in markdown
    assert "市场选择或价格样本不足" in markdown
    assert "价值为零" not in markdown
    assert "该卖点没有价值" not in markdown


def test_market_curve_cannot_make_unobserved_user_value_look_established() -> None:
    context = _synthetic_context()
    payload = context.model_dump(mode="python")
    payload["target_snapshot"]["comment_outcomes"] = []
    for candidate in payload["candidate_snapshots"]:
        candidate["comment_outcomes"] = []
    payload.pop("input_hash")
    context = SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )

    report = build_product_value_realization_report(context)
    markdown = render_product_value_markdown(report)

    assert report.value_structure_rows[0].selection_price_realization.level == (
        "Q0_NOT_OBSERVED"
    )
    assert "现有购后证据尚未观察到这项价值" in markdown
    assert "不能进入卖点选择和价格量化" in markdown


def test_missing_published_reason_returns_a_blocked_empty_report() -> None:
    report = build_product_value_realization_report(_context(purchase_found=False))

    assert report.analysis_status == "blocked"
    assert report.value_structure_rows == []
    assert "不能形成产品价值账" in report.headline_cn


def test_negative_user_experience_is_a_business_result_not_a_data_conflict() -> None:
    context = _context(
        atoms=[
            _atom(
                "暗场漏光明显",
                key="negative-bright",
                polarity="negative",
                contradicted_params=["local_dimming_zone_count"],
            ),
            _atom(
                "颜色偏得厉害",
                key="negative-color",
                subdimension="picture_color_accuracy",
                polarity="negative",
                contradicted_params=["wide_color_gamut_pct"],
            ),
        ]
    )

    report = build_product_value_realization_report(context)
    markdown = render_product_value_markdown(report)

    assert (
        report.value_structure_rows[0].selection_price_realization.value_status
        == "negative"
    )
    assert "用户实际获得的是负向体验" in markdown
    assert "用户实际获得的是负向体验，市场量化已暂停" in markdown
    assert "正反并存" not in markdown
    assert "存在事实冲突，受影响判断已暂停" not in markdown


def test_mixed_user_experience_is_distinct_from_pure_negative() -> None:
    context = _context(
        atoms=[
            _atom("白天画面很清楚", key="positive-bright"),
            _atom(
                "暗场漏光明显",
                key="negative-bright",
                polarity="negative",
                contradicted_params=["local_dimming_zone_count"],
            ),
        ]
    )

    report = build_product_value_realization_report(context)
    markdown = render_product_value_markdown(report)

    assert report.value_structure_rows[0].selection_price_realization.value_status == "mixed"
    assert "不同用户或场景的实际体验正反并存" in markdown
    assert "用户实际获得的是负向体验，市场量化已暂停" not in markdown


def test_65e7q_redacted_fixture_keeps_value_and_amount_unobserved(
    repo_root: Path,
) -> None:
    fixture = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G01_65E7Q_fixture.json"
        ).read_text(encoding="utf-8")
    )
    context = _base_context(lineage_conflict=True)
    tier_by_role = {
        "base_value": "base",
        "same_value": "premium",
        "stretch_benchmark": "flagship",
    }
    candidates = [
        _candidate(
            context,
            sku_code=item["sku_code"],
            role=item["role"],
            provenance="competitor_set_fallback",
            tier=tier_by_role[item["role"]],
            size=item["screen_size_inch"],
            brightness=item["capability"].get("brightness_nit"),
            zones=item["capability"].get("local_dimming_zones"),
        ).model_copy(update={"comment_outcomes": []})
        for item in fixture["counterfactual_candidates"]
    ]
    payload = context.model_dump(mode="python")
    payload["target_snapshot"]["comment_outcomes"] = []
    payload["candidate_snapshots"] = [
        item.model_dump(mode="python") for item in candidates
    ]
    payload["market_cells"] = []
    payload.pop("input_hash")
    context = SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )

    report = build_product_value_realization_report(context)
    markdown = render_product_value_markdown(report)
    row = report.value_structure_rows[0]

    assert report.analysis_status == "partial"
    assert row.selection_price_realization.value_status == "not_observed"
    assert row.selection_price_realization.wtp.status == "blocked"
    assert row.selection_price_realization.wtp.estimate_low is None
    assert "市场隐含支付区间约" not in markdown
    assert "不能进入卖点选择和价格量化" in markdown
    assert pm_business_output_issue(markdown) is None


def test_answer_artifacts_keep_report_hash_independent_of_delivery_links() -> None:
    report = build_product_value_realization_report(_synthetic_context())

    first = build_product_value_answer_artifacts(
        report,
        with_report="markdown",
        selection_compare_url="https://example.com/a",
        evidence_report_url="https://example.com/b",
    )
    second = build_product_value_answer_artifacts(
        report,
        with_report="none",
        selection_compare_url="https://example.com/c",
        evidence_report_url="https://example.com/d",
    )

    assert first["result_hash"] == second["result_hash"] == report.result_hash
    assert first["markdown"] is not None
    assert Path(first["markdown_path"]).exists()
    assert first["report_delivery"]["status"] == "markdown_ready"
    assert second["report_delivery"]["status"] == "disabled"


def test_g07_models_match_frozen_contract(repo_root: Path) -> None:
    from app.services.core3_real_data.analyst import claim_value_pm_v4_schemas

    contract = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G02_schema_contract.json"
        ).read_text(encoding="utf-8")
    )["models"]
    for name in ("ProductValueStructureRow", "SkuProductValueRealizationReport"):
        model = getattr(claim_value_pm_v4_schemas, name)
        assert set(model.model_fields) == set(contract[name]["fields"])
        assert {
            key for key, field in model.model_fields.items() if field.is_required()
        } == set(contract[name]["required"])


def test_qa_appendix_may_hold_internal_audit_but_renderers_never_leak_it() -> None:
    report = build_product_value_realization_report(_synthetic_context())

    assert "quantification_level" in report.qa_appendix["relations"][0]
    markdown = render_product_value_markdown(report)
    short = render_product_value_short_answer(report)
    card = json.dumps(render_product_value_feishu_card(report), ensure_ascii=False)

    assert "Q5_MARKET_IMPLIED_WTP" not in markdown
    assert "Q5_MARKET_IMPLIED_WTP" not in short
    assert "Q5_MARKET_IMPLIED_WTP" not in card
