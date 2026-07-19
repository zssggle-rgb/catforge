from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.services.core3_real_data.analyst import sellpoint_value_profile_report
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueReleaseQualityStatus,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_report import (
    build_v5_2_stored_profile_pm_report,
    render_stored_profile_feishu_card,
    render_stored_profile_markdown,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_consumer import (
    SellpointValueV52ConsumerReadRequest,
    SellpointValueV52ConsumerReader,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_generation import (
    SellpointValueV52GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_mapping import (
    CompetitorSellpointObservation,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_qa import (
    SellpointValueV52QaService,
)
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_materialization import (
    session as _v5_1_session,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_2_materialization import (
    FixtureProvider,
    _repository,
    _v52_input,
    _v52_request,
)


@pytest.fixture(name="session")
def session_fixture():
    yield from _v5_1_session.__wrapped__()


def _source():
    source = _v52_input(profile_version="spv-v52-consumption")
    value = source.base.values[0]
    decision = value.investment_decisions[0].model_copy(
        update={
            "capability_code": "tv_bright_room_dark_detail",
            "capability_name_cn": "明亮环境与明暗层次",
        }
    )
    direct = value.direct_market_results[0]
    price = direct.price_comparison.model_copy(
        update={
            "target_value": Decimal("5278.8606"),
            "comparator_average": Decimal("5000"),
            "gap_abs": Decimal("278.8606"),
            "gap_pct": Decimal("278.8606") / Decimal("5000"),
            "direction": direct.price_comparison.direction.__class__.TARGET_HIGHER,
        }
    )
    sales = direct.sales_comparison.model_copy(
        update={
            "target_value": Decimal("111.916666"),
            "comparator_average": Decimal("50"),
            "gap_abs": Decimal("61.916666"),
            "gap_pct": Decimal("61.916666") / Decimal("50"),
            "direction": direct.sales_comparison.direction.__class__.TARGET_HIGHER,
        }
    )
    direct = direct.model_copy(
        update={
            "price_comparison": price,
            "sales_comparison": sales,
            "business_conclusion_cn": (
                "本品周均价较3款参照的平均水平高278.8606元，"
                "周均销量较3款参照的平均水平高61.916666台；"
                "该结果用于判断市场表现，不归因于单一卖点。"
            ),
        }
    )
    value = value.model_copy(
        update={
            "normalized_bundle_code": "tv_bright_room_dark_detail",
            "capability_codes": ["tv_bright_room_dark_detail"],
            "investment_decisions": [decision],
            "direct_market_results": [direct],
        }
    )
    return source.model_copy(
        update={"base": source.base.model_copy(update={"values": [value]})}
    )


def _readback(session):
    source = _source()
    return SellpointValueV52GenerationService(
        repository=_repository(session),
        input_provider=FixtureProvider({"TV-TARGET": source}),
    ).generate_draft(_v52_request(source), sku_code="TV-TARGET")


class _NoUpstreamHandlers:
    def __init__(self) -> None:
        self.call_count = 0

    def __getattr__(self, name: str):
        self.call_count += 1
        raise AssertionError(f"V5.2 consumer attempted upstream analysis: {name}")


def _publish_current(session, readback):
    repository = _repository(session)
    quality = SellpointValueReleaseQualityStatus(
        readback.persisted.version.release_quality_status
    )
    repository.review_version(
        sellpoint_value_profile_version_id=(
            readback.persisted.version.sellpoint_value_profile_version_id
        ),
        reviewed_by="v5-2-reviewer",
        release_quality_status=quality,
    )
    published = repository.publish_version(
        sellpoint_value_profile_version_id=(
            readback.persisted.version.sellpoint_value_profile_version_id
        ),
        published_by="v5-2-approver",
        allow_limited=quality == SellpointValueReleaseQualityStatus.LIMITED,
    )
    session.commit()
    return repository, published


def test_v5_2_report_uses_only_saved_source_sellpoints(
    session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readback = _readback(session)
    monkeypatch.setattr(
        sellpoint_value_profile_report,
        "_v5_1_product_sellpoint_cn",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("V5.2 must not use the legacy sellpoint fallback")
        ),
    )

    report = build_v5_2_stored_profile_pm_report(readback)
    markdown = render_stored_profile_markdown(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )

    assert report.schema_version == "sku_sellpoint_value_pm_report_v1_2"
    assert report.investment_decisions == []
    assert len(report.sellpoint_rows) == 1
    assert report.sellpoint_rows[0].raw_claim_text == (
        "【核心定位】65英寸Mini LED电视，呈现专业画质。"
    )
    assert report.sellpoint_rows[0].classification_cn == "核心卖点"
    assert report.sellpoint_rows[0].user_values_cn == [
        "白天客厅画面仍清楚，暗场层次更完整、光晕更少。"
    ]
    assert "picture_quality" not in markdown
    assert "tv_bright_room_dark_detail" not in markdown
    assert "1920分区控光" not in markdown
    assert "产品原始卖点" in markdown
    assert "用户卖点价值" in markdown
    assert "关键参数或能力" in markdown
    assert report.parameter_rows == []
    for hidden_parameter in (
        "mini_led_flag",
        "anti_glare_flag",
        "eye_care_certification",
        "usb_port_count",
        "待确认参数",
        "### 参数明细",
    ):
        assert hidden_parameter not in markdown


def test_v5_2_renderer_filters_legacy_internal_parameter_labels(session) -> None:
    report = build_v5_2_stored_profile_pm_report(_readback(session))
    polluted_row = report.sellpoint_rows[0].model_copy(
        update={
            "supporting_parameters_cn": [
                "anti_glare_flag",
                "eye_care_certification",
                "usb_port_count（2）",
                "控光分区（1920）",
            ]
        }
    )
    report = report.model_copy(update={"sellpoint_rows": [polluted_row]})

    markdown = render_stored_profile_markdown(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )

    assert "控光分区（1920）" in markdown
    assert "anti_glare_flag" not in markdown
    assert "eye_care_certification" not in markdown
    assert "usb_port_count" not in markdown


def test_formal_reader_and_agent_prefer_current_published_v5_2(session) -> None:
    readback = _readback(session)
    repository, published = _publish_current(session, readback)
    handlers = _NoUpstreamHandlers()
    context = AnalystContext(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        product_category="TV",
    )

    direct = SellpointValueV52ConsumerReader(repository).read(
        SellpointValueV52ConsumerReadRequest(
            project_id="project-1",
            category_code="TV",
            batch_id="later-context-batch",
            sku_code="TV-TARGET",
        )
    )
    orchestrator = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )
    report_result = orchestrator.sellpoint_value_pm_v5(
        context,
        sku_code="TV-TARGET",
        enable_v5=True,
    )
    qa_result = orchestrator.sellpoint_value_profile_ask(
        context,
        sku_code="TV-TARGET",
        question="这款产品的用户卖点价值是什么？",
    )

    assert published.release_status == "published"
    assert published.is_current is True
    assert direct.status == "available"
    assert direct.readback is not None
    assert direct.readback.profile.result_hash == readback.profile.result_hash
    assert report_result["status"] == "ok"
    report = report_result["result"]["sellpoint_value_pm_v5"]
    assert report["schema_version"] == "sku_sellpoint_value_pm_report_v1_2"
    assert report["profile_version"] == readback.profile.base_profile.profile_version
    assert report["profile_result_hash"] == readback.profile.result_hash
    assert qa_result["status"] == "ok"
    answer = qa_result["result"]["sellpoint_value_profile_answer"]
    assert answer["schema_version"] == "sellpoint_value_profile_answer_v1_2"
    assert answer["profile_version"] == readback.profile.base_profile.profile_version
    assert answer["result_hash"] == readback.profile.result_hash
    assert handlers.call_count == 0


def test_v5_2_total_and_detail_match_and_market_units_are_rounded(
    session,
) -> None:
    report = build_v5_2_stored_profile_pm_report(_readback(session))
    market_questions = (
        (
            "影音用户愿为画质升级付费支撑卖点组合",
            370,
            46,
            ["TCL 65Q9L PRO", "创维 65A7H PRO"],
        ),
        (
            "画质配置解释加价支撑卖点组合",
            427,
            57,
            ["TCL 65Q9L PRO"],
        ),
        (
            "同尺寸画质越级获得感支撑卖点组合",
            262,
            76,
            ["TCL 65Q9L PRO", "小米 L65MC-SP"],
        ),
        (
            "贵得值的体验升级支撑卖点组合",
            279,
            62,
            ["TCL 65Q9L PRO", "小米 L65MC-SP", "创维 65A7H PRO"],
        ),
    )
    market_rows = [
        report.value_accounts[0].model_copy(
            update={
                "value_bundle_code": f"market-question-{index}",
                "value_bundle_name_cn": name,
                "reference_sku_codes": [
                    f"TV-C{index}-{reference_index}"
                    for reference_index in range(1, len(references) + 1)
                ],
                "reference_sku_names_cn": references,
                "price_performance_cn": (
                    f"本品周均价较参照组平均水平高{price}.0000元。"
                ),
                "volume_performance_cn": (
                    f"本品周均销量较参照组平均水平高{sales}.0000台。"
                ),
            }
        )
        for index, (name, price, sales, references) in enumerate(
            market_questions,
            start=1,
        )
    ]
    report = report.model_copy(update={"value_accounts": market_rows})
    markdown = render_stored_profile_markdown(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    card = render_stored_profile_feishu_card(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    visible = markdown + json.dumps(card, ensure_ascii=False)

    assert "### 结论 1｜SKU 形成了什么用户卖点价值" in markdown
    assert "### 结论 2｜这些价值是否支撑当前价格和销量" in markdown
    assert "## 一、SKU 形成了什么用户卖点价值" in markdown
    assert "## 二、这些价值是否支撑当前价格和销量" in markdown
    assert "### 2.2 各价值问题的详细量化" in markdown
    assert "### 2.3 完整量化表" in markdown
    assert "## 三、产品卖点修改建议" in markdown
    assert "#### 2.2.1 影音用户是否愿意为画质升级付费" in markdown
    assert "**符合该价值问题的参照SKU：2款**" in markdown
    assert "在高端画质升级、影音性能和画质升级付费理由上与本品重合" in markdown
    assert "在高端画质、客厅影音和沉浸体验上与本品重合" in markdown
    assert "周均价高370元" in markdown
    assert "周均销量高46台" in markdown
    assert "“影音用户愿意为画质升级付费”这一用户卖点价值获得市场支撑" in markdown
    assert (
        "| 影音用户是否愿意为画质升级付费 | TCL 65Q9L PRO、创维 65A7H PRO |"
    ) in markdown
    assert "| 画质价值能否解释当前加价 | TCL 65Q9L PRO |" in markdown
    assert (
        "| 同尺寸产品是否形成画质越级感 | TCL 65Q9L PRO、小米 L65MC-SP |"
    ) in markdown
    assert (
        "| 整体体验升级是否让用户觉得贵得值 | "
        "TCL 65Q9L PRO、小米 L65MC-SP、创维 65A7H PRO |"
    ) in markdown
    assert "279元" in visible
    assert "62台" in visible
    assert "278.8606元" not in visible
    assert "61.916666台" not in visible
    assert card["schema"] == "2.0"
    assert card["header"]["template"] == "turquoise"
    card_visible = json.dumps(card, ensure_ascii=False)
    assert "结论 1｜SKU 形成了什么用户卖点价值" in card_visible
    assert "结论 2｜这些价值是否支撑当前价格和销量" in card_visible
    assert "核心用户卖点价值" not in card_visible
    assert "市场是否买单" not in card_visible
    assert "用户卖点价值量化" in card_visible
    for name, *_ in market_questions:
        assert name.removesuffix("支撑卖点组合") in card_visible
    assert "TCL 65Q9L PRO" not in card_visible
    assert "小米 L65MC-SP" not in card_visible
    assert "创维 65A7H PRO" not in card_visible
    assert "符合该问题的参照 SKU" not in card_visible
    assert "产品卖点修改建议" not in card_visible
    assert "用户尚未稳定认知" not in card_visible
    assert "参照产品选择逻辑" in markdown
    assert "为什么符合" in markdown
    assert "TCL 65Q9L PRO" in markdown
    assert "小米 L65MC-SP" in markdown
    assert "创维 65A7H PRO" in markdown
    assert "产品卖点修改建议" in markdown
    assert "下一代产品怎么定义" not in visible
    assert "已经成立的用户价值" not in card_visible
    assert "产品原始卖点 → 用户感知价值" not in card_visible
    assert "参数判断" not in card_visible
    assert "原文：" not in card_visible
    assert len(card["body"]["elements"]) <= 5
    assert (
        sum(element["tag"] == "column_set" for element in card["body"]["elements"]) >= 3
    )
    assert report.value_accounts[0].reference_sku_names_cn == [
        "TCL 65Q9L PRO",
        "创维 65A7H PRO",
    ]
    presentation_report = report.model_copy(
        update={
            "first_screen": report.first_screen.model_copy(
                update={
                    "sku_role_cn": (
                        "本品适合继续承担高端画质升级升级款角色：保持当前定位。"
                    ),
                    "price_support_cn": (
                        "当前价格有用户价值支撑：本品价高279元、量高62台；"
                        "该结果属于价值组合的市场表现，不拆给单项参数。"
                    ),
                }
            )
        }
    )
    presentation_card = render_stored_profile_feishu_card(
        presentation_report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    assert "升级升级款" not in presentation_card["header"]["subtitle"]["content"]
    assert "不拆给单项参数" not in json.dumps(
        presentation_card,
        ensure_ascii=False,
    )
    presentation_markdown = render_stored_profile_markdown(
        presentation_report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    assert "不拆给单项参数" not in presentation_markdown
    for internal_term in (
        "画像",
        "result_hash",
        "schema_version",
        "M04C",
        "internal_value_theme",
    ):
        assert internal_term not in visible


def test_v5_2_qa_answers_from_saved_sellpoint_and_rejects_invented_theme(
    session,
) -> None:
    readback = _readback(session)
    service = SellpointValueV52QaService()

    source_answer = service.answer(
        readback,
        question="MiniLED 显示是不是本品卖点？",
    )
    invented_answer = service.answer(
        readback,
        question="游戏流畅是本品卖点吗？",
    )

    assert source_answer.answer_status == "answered"
    assert "产品原始卖点" in source_answer.direct_answer_cn
    assert "核心卖点" in source_answer.direct_answer_cn
    assert source_answer.facts[0].evidence_record_ids == ["claim-fact-1"]
    assert invented_answer.answer_status == "unknown"
    assert "没有找到" in invented_answer.direct_answer_cn
    assert "用户价值主题" in invented_answer.product_manager_action_cn


def test_v5_2_report_projects_saved_competitor_sellpoint_opportunity(
    session,
) -> None:
    source = _source()
    competitor_fact = source.source_sellpoints.source_sellpoints[0].model_copy(
        update={
            "claim_fact_id": "competitor-claim-1",
            "merged_claim_fact_ids": ["competitor-claim-1"],
            "normalized_claim_code": "tv_claim_qd_miniled_display",
            "normalized_claim_name_cn": "量子点 MiniLED 显示",
            "raw_claim_text": "量子点MiniLED带来更丰富的色彩层次。",
            "clean_claim_text": "量子点MiniLED带来更丰富的色彩层次。",
            "exact_quote_cn": None,
        }
    )
    source = source.model_copy(
        update={
            "base": source.base.model_copy(
                update={"profile_version": "spv-v52-competitor-report"}
            ),
            "competitor_sellpoints": [
                CompetitorSellpointObservation(
                    candidate_sku_code="TV-C01",
                    source_sellpoint=competitor_fact,
                    target_has_matching_sellpoint=False,
                    competitor_value_advantage=True,
                    target_value_weakness=True,
                    market_support=True,
                    linked_value_bundle_codes=[source.base.values[0].value_bundle_code],
                    evidence_refs=competitor_fact.evidence_refs,
                )
            ],
        }
    )
    readback = SellpointValueV52GenerationService(
        repository=_repository(session),
        input_provider=FixtureProvider({"TV-TARGET": source}),
    ).generate_draft(_v52_request(source), sku_code="TV-TARGET")

    report = build_v5_2_stored_profile_pm_report(readback)
    markdown = render_stored_profile_markdown(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    card = render_stored_profile_feishu_card(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    visible = markdown + json.dumps(card, ensure_ascii=False)

    assert len(report.competitor_sellpoint_rows) == 1
    assert report.competitor_sellpoint_rows[0].finding_type_cn == "可借鉴的竞品卖点"
    assert "竞品卖点取舍" not in markdown
    assert "可补强的卖点方向" in markdown
    assert "量子点 MiniLED 显示" in visible
    assert "已经具备就补强宣传表达" in visible
    answer = SellpointValueV52QaService().answer(
        readback,
        question="有哪些竞品卖点值得借鉴？",
    )
    assert answer.topic_code == "competitor_sellpoint"
    assert answer.answer_status == "answered"
    assert "可借鉴的竞品卖点" in answer.direct_answer_cn
    assert answer.facts[0].evidence_record_ids
