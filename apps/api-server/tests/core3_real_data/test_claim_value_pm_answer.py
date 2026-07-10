from __future__ import annotations

from copy import deepcopy

from app.services.core3_real_data.analyst.claim_value_pm_answer import (
    build_claim_value_pm_answer,
    build_claim_value_pm_dashboard_payload,
    render_claim_value_pm_feishu_card_payload,
    render_claim_value_pm_report,
    render_claim_value_pm_short_answer,
)


def _target() -> dict:
    return {"sku_code": "TV00029112", "brand_name": "海信", "model_name": "65E7Q"}


def _analysis() -> dict:
    return {
        "schema_version": "sellpoint_value_pm_v1",
        "analysis_status": "partial",
        "target": _target(),
        "data_gate": {
            "status": "partial",
            "status_cn": "数据需修复，卖点结论暂停",
            "issues": [
                {
                    "code": "m03b_m04c_presence_conflict",
                    "severity": "blocking",
                    "scope": "product_fact",
                    "message_cn": "参数画像已经存在，但卖点事实仍声明参数画像缺失；受影响卖点暂停做价格归因。",
                    "source_modules": ["M03B", "M04C"],
                    "affected_unit_codes": ["tv_bright_room_dark_detail"],
                }
            ],
            "available_sources": ["M03B", "M04C", "M05C", "M07"],
            "missing_sources": [],
            "review_required": True,
        },
        "headline_cn": "当前配置事实链存在冲突，整机市场选择仍可观察，但不能把结果归到具体卖点；先修事实链。",
        "decision_summary": [
            {
                "priority": 1,
                "action_type": "数据核验",
                "action_cn": "先修参数事实与卖点事实链，再讨论单项卖点的价格作用。",
                "why_cn": "关键产品事实冲突。",
                "success_signal_cn": "参数事实与卖点事实对关键能力一致。",
            }
        ],
        "value_units": [
            {
                "unit_code": "tv_bright_room_dark_detail",
                "unit_name_cn": "明亮环境与明暗层次",
                "unit_type": "experience_bundle",
                "product_claim_cn": "MiniLED=有、标称亮度=5200nits、控光分区=1920",
                "linked_param_codes": ["mini_led_flag"],
                "linked_claim_codes": ["tv_claim_miniled_display"],
                "product_fact_status": "conflict",
                "product_fact_status_cn": "产品事实链存在冲突",
                "product_fact_items": ["MiniLED=有"],
                "user_understanding": {
                    "status": "unrecognized",
                    "status_cn": "本批评论只有泛化评价，尚未认到具体价值",
                    "eligible_sentence_count": 52,
                    "direct_sentence_count": 0,
                    "indirect_sentence_count": 0,
                    "unattributable_sentence_count": 22,
                    "negative_sentence_count": 0,
                    "perception_weight": 0,
                    "positive_examples": [],
                    "negative_examples": [],
                    "evidence_ids": ["ev-comment-1"],
                },
                "weights": {
                    "product_fact_weight": None,
                    "user_perception_weight": 0,
                    "pricing_readiness": "not_ready",
                    "pricing_readiness_cn": "先修产品事实链，不进入价格测试",
                },
                "purchase_role": {
                    "status": "not_proven",
                    "status_cn": "尚未证明影响选购",
                    "basis_cn": "当前只有产品事实或泛化评价，没有直接选购证据。",
                },
                "evidence_stage": "E0",
                "competitor_comparison": [
                    {
                        "sku_code": "TV-COMP-1",
                        "display_name": "竞品 A",
                        "selection_role_cn": "首选直接竞品",
                        "fact_relation": "different",
                        "target_fact_cn": "本品事实冲突",
                        "competitor_fact_cn": "竞品事实已确认",
                        "competitor_user_status_cn": "用户说到了体验结果",
                        "market_position_cn": "同尺寸价格分位约60%",
                        "isolation_grade": "C",
                    }
                ],
                "decision_code": "BLOCKED_DATA",
                "decision_cn": "先修配置事实链，本轮不做卖点取舍或加价判断。",
                "next_validation_cn": "核对 SKU 版本、参数来源与卖点事实映射后重跑。",
                "limitations": ["泛化好评只保留在体验组合，不拆给具体技术参数。"],
                "evidence_ids": ["ev-comment-1"],
            }
        ],
        "market_pricing": {
            "method_level": "L2",
            "method_name_cn": "直接竞品条件选择曲线",
            "attribution_status": "whole_product_only",
            "attribution_status_cn": "当前数值只说明整机方案相对直接竞品的选择，不拆给单个卖点。",
            "current_price": 6999,
            "valid_pair_count": 2,
            "strong_pair_count": 1,
            "direction_consistency": 1,
            "same_price_choice_share": 0.58,
            "same_price_choice_advantage_pp": 8,
            "same_price_competitor_interval_pp": [5, 11],
            "selection_holding_gap_amount_range": [],
            "selection_holding_gap_ratio_range": [],
            "holding_gap_status_cn": "样本不足，暂不计算选择保持价差。",
            "current_price_acceptance_status": "mostly_captured",
            "current_price_acceptance_status_cn": "价格已基本承接",
            "current_price_acceptance_basis_cn": "当前价格下条件销量份额已接近五五开。",
            "pair_curves": [],
            "price_scenarios": [
                {
                    "label_cn": "当前价格",
                    "price": 7000,
                    "price_change_pct": 0,
                    "pair_count": 2,
                    "weight_coverage": 1,
                    "comparison_choice_share": 0.55,
                    "choice_index": 100,
                    "comparison_revenue_index": 100,
                    "status_cn": "历史直接竞品条件选择观察。",
                }
            ],
            "limitations": ["未达到 L3 门槛。"],
        },
        "competitor_boundary": {
            "source": "M14",
            "competitor_count": 1,
            "sku_codes": ["TV-COMP-1"],
            "policy_cn": "只复用既有竞品集合和事实，不在本报告重选竞品。",
        },
        "test_backlog": [
            {
                "priority": 1,
                "action_type": "组合测试",
                "action_cn": "验证明亮环境与明暗层次是否提高选择。",
                "why_cn": "目前只有泛化评论。",
                "success_signal_cn": "固定其他配置后，同价选择率提升。",
            }
        ],
        "limitations": ["评论来自购买后用户，不能代表未购买用户。"],
        "audit": {
            "generated_at": "2026-07-10T00:00:00+00:00",
            "project_id": "core3_mvp",
            "category_code": "TV",
            "batch_id": "batch-test",
            "target_sku_code": "TV00029112",
            "schema_version": "sellpoint_value_pm_v1",
            "method_level": "L2",
            "source_versions": {"M03B": "v1"},
            "sample_summary": {},
            "evidence_ids": ["ev-comment-1"],
        },
    }


def test_report_leads_with_decisions_and_keeps_whole_product_market_boundary() -> None:
    dashboard = build_claim_value_pm_dashboard_payload(
        target=_target(),
        analysis=_analysis(),
        report_url="https://example.feishu.cn/docx/report",
    )
    markdown = render_claim_value_pm_report(title="海信 65E7Q 卖点经营盘", dashboard=dashboard)

    assert "# 海信 65E7Q 卖点经营盘" in markdown
    assert "## 一、本周先做这几件事" in markdown
    assert "## 二、卖点称重总表" in markdown
    assert "## 三、当前价格承接与价格情景" in markdown
    assert "整机方案相对直接竞品的选择，不拆给单个卖点" in markdown
    assert "泛化好评只保留在体验组合" in markdown
    assert "选择保持价差" in markdown
    assert "WTP" not in markdown
    assert "价值棒" not in markdown
    assert "5200nits值" not in markdown
    assert "M03B" not in markdown
    assert "L2" not in markdown
    assert "隔离等级" not in markdown
    assert "差异过多，不能归到本项" in markdown
    assert "既有竞品智能体已确认的竞品" in markdown
    assert "当前价格承接状态" in markdown
    assert "价格已基本承接" in markdown
    assert "条件销量份额" in markdown
    assert "销量承接指数" in markdown
    assert "对比选择份额" not in markdown
    assert "选择指数" not in markdown


def test_short_answer_uses_product_manager_language() -> None:
    dashboard = build_claim_value_pm_dashboard_payload(target=_target(), analysis=_analysis(), report_url=None)
    short = render_claim_value_pm_short_answer(dashboard, max_chat_chars=600)

    assert "卖点称重结论：数据需修复，卖点结论暂停" in short
    assert "整机同价条件销量份额约 58.0%" in short
    assert "没有拆给单个卖点" in short
    assert "当前价格承接：价格已基本承接" in short
    assert "先修参数事实与卖点事实链" in short


def test_feishu_card_and_markdown_fallback_are_built_in_parallel() -> None:
    result = build_claim_value_pm_answer(
        target=_target(),
        analysis=_analysis(),
        with_report="markdown",
    )

    assert result["dashboard_payload"]["dashboard_schema_version"] == "sellpoint_value_pm_dashboard_v1"
    assert result["report"]["status"] == "markdown_ready"
    assert result["report"]["markdown_path"].endswith(".md")
    assert result["markdown"].startswith("# 海信 65E7Q 卖点经营盘")
    card = result["feishu_card_payload"]
    assert card["schema"] == "2.0"
    assert card["header"]["template"] == "orange"
    assert "卖点称重" in str(card)
    assert "L2" not in str(card)


def test_card_contains_report_button_when_document_url_exists() -> None:
    dashboard = build_claim_value_pm_dashboard_payload(
        target=_target(),
        analysis=_analysis(),
        report_url="https://example.feishu.cn/docx/report",
    )
    card = render_claim_value_pm_feishu_card_payload(dashboard)

    buttons = [item for item in card["body"]["elements"] if item.get("tag") == "button"]
    assert len(buttons) == 1
    assert buttons[0]["text"]["content"] == "查看完整报告"


def test_card_keeps_conflicted_units_out_of_other_buckets_and_reports_all() -> None:
    analysis = deepcopy(_analysis())
    base = analysis["value_units"][0]
    analysis["value_units"] = [
        {**deepcopy(base), "unit_code": f"unit-{index}", "unit_name_cn": f"价值组合{index}"}
        for index in range(1, 7)
    ]
    dashboard = build_claim_value_pm_dashboard_payload(target=_target(), analysis=analysis, report_url=None)

    card_text = str(render_claim_value_pm_feishu_card_payload(dashboard))

    assert "有配置但未形成具体结果：无" in card_text
    assert "暂停判断：价值组合1、价值组合2、价值组合3等6项" in card_text
    assert "当前价格：价格已基本承接" in card_text
    assert "价格测试准备：先修产品事实，本轮不下发涨价动作" in card_text
