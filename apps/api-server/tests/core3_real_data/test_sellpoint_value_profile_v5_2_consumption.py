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
        update={
            "base": source.base.model_copy(update={"values": [value]})
        }
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
    assert "支撑参数" in markdown


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
    markdown = render_stored_profile_markdown(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    card = render_stored_profile_feishu_card(
        report,
        title="海信 65E7Q 用户卖点价值分析",
    )
    visible = markdown + json.dumps(card, ensure_ascii=False)

    for index, title in enumerate(
        (
            "这款 SKU 的用户卖点价值",
            "卖点如何形成这些价值",
            "市场是否为这些价值买单",
            "产品卖点修改建议",
        ),
        start=1,
    ):
        assert f"{index}. **{title}**" in markdown
        assert f"## {'一二三四'[index - 1]}、{title}" in markdown
    assert "279元" in visible
    assert "62台" in visible
    assert "278.8606元" not in visible
    assert "61.916666台" not in visible
    assert card["schema"] == "2.0"
    assert card["header"]["template"] == "turquoise"
    card_visible = json.dumps(card, ensure_ascii=False)
    assert "本品已经形成1项用户卖点价值" in card_visible
    assert "核心用户卖点价值" not in card_visible
    assert "市场是否买单" in card_visible
    assert "产品卖点修改建议" in visible
    assert "下一代产品怎么定义" not in visible
    assert "已经成立的用户价值" not in card_visible
    assert "产品原始卖点 → 用户感知价值" not in card_visible
    assert "参数判断" not in card_visible
    assert "原文：" not in card_visible
    assert len(card["body"]["elements"]) <= 5
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
    competitor_fact = (
        source.source_sellpoints.source_sellpoints[0].model_copy(
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
                    linked_value_bundle_codes=[
                        source.base.values[0].value_bundle_code
                    ],
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
    assert (
        report.competitor_sellpoint_rows[0].finding_type_cn
        == "可借鉴的竞品卖点"
    )
    assert "竞品卖点取舍" in markdown
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
