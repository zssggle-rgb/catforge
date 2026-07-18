from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.services.core3_real_data.analyst import sellpoint_value_profile_report
from app.services.core3_real_data.analyst.sellpoint_value_profile_report import (
    build_v5_2_stored_profile_pm_report,
    render_stored_profile_feishu_card,
    render_stored_profile_markdown,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_generation import (
    SellpointValueV52GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_qa import (
    SellpointValueV52QaService,
)
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
        "白天客厅不用拉窗帘也能看清，暗场层次更完整"
    ]
    assert "picture_quality" not in markdown
    assert "tv_bright_room_dark_detail" not in markdown
    assert "1920分区控光" not in markdown
    assert "产品原始卖点" in markdown
    assert "用户感知价值" in markdown
    assert "支撑参数" in markdown


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
            "本品的用户卖点价值是什么",
            "卖点怎么分类和处理",
            "参数在卖点中起什么作用",
            "价格和销量怎么决策",
            "产品卖点修改建议",
        ),
        start=1,
    ):
        assert f"{index}. **{title}**" in markdown
        assert f"## {'一二三四五'[index - 1]}、{title}" in markdown
    assert "279元" in visible
    assert "62台" in visible
    assert "278.8606元" not in visible
    assert "61.916666台" not in visible
    assert card["schema"] == "2.0"
    assert card["header"]["template"] == "turquoise"
    assert "产品卖点修改建议" in visible
    assert "下一代产品怎么定义" not in visible
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
