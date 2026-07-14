from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.core3_real_data.analyst import competitor_profile_presentation
from app.services.core3_real_data.analyst.competitor_answer import (
    ReportPublishResult,
)
from app.services.core3_real_data.analyst.competitor_profile_consumption import (
    CompetitorProfileConsumptionService,
)
from app.services.core3_real_data.analyst.competitor_profile_consumption_schemas import (
    CompetitorProfileConsumptionContext,
)
from app.services.core3_real_data.analyst.competitor_profile_presentation import (
    _action_summary,
    _configuration_summary,
    _pressure_summary,
    _selection_summary,
    _substitution_summary,
    answer_competitor_profile_question,
    build_competitor_profile_presentation,
)
from app.services.core3_real_data.analyst.competitor_profile_reader import (
    CompetitorProfileReader,
)
from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileReadRequest,
)
from tests.core3_real_data.test_competitor_profile_reader import _generated


pytest_plugins = ("tests.core3_real_data.test_competitor_profile_generation",)


def _context(session) -> CompetitorProfileConsumptionContext:
    category, repository, readback = _generated(session)
    return CompetitorProfileConsumptionService(
        CompetitorProfileReader(repository)
    ).load(
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
            mode="preview",
            competitor_profile_version_id=(
                readback.persisted.version.competitor_profile_version_id
            ),
            allow_draft_preview=True,
        )
    )


def test_presentation_consumers_share_one_saved_profile_version(
    session,
    monkeypatch,
) -> None:
    context = _context(session)
    published_titles: list[str] = []

    def fake_publish(*, title: str, markdown: str, with_report: str):
        assert with_report == "feishu-doc"
        assert markdown
        published_titles.append(title)
        return ReportPublishResult(
            status="published",
            url=f"https://example.test/report/{len(published_titles)}",
        )

    monkeypatch.setattr(
        competitor_profile_presentation,
        "_publish_report",
        fake_publish,
    )
    result = build_competitor_profile_presentation(
        context,
        with_report="feishu-doc",
    )

    assert len(published_titles) == 2
    assert result.competitor_profile_version_id == context.competitor_profile_version_id
    assert result.profile_result_hash == context.evidence.profile_result_hash
    assert len(result.qa_answers) == 6
    assert {
        answer.competitor_profile_version_id for answer in result.qa_answers
    } == {context.competitor_profile_version_id}
    assert {answer.profile_result_hash for answer in result.qa_answers} == {
        context.evidence.profile_result_hash
    }
    assert result.sellpoint_value_consumption["competitor_profile_version_id"] == (
        context.competitor_profile_version_id
    )
    assert result.sellpoint_value_consumption["read_only"] is True
    assert result.sellpoint_value_consumption["sellpoint_profile_write"] is False
    assert result.sellpoint_value_consumption["fallback_used"] is False
    assert result.pm_report_delivery["status"] == "published"
    assert result.evidence_report_delivery["status"] == "published"


def test_business_surfaces_hide_runtime_trace_and_internal_vocabulary(session) -> None:
    context = _context(session)
    result = build_competitor_profile_presentation(context, with_report="markdown")
    visible_card = json.dumps(
        result.feishu_card_payload,
        ensure_ascii=False,
        sort_keys=True,
    )
    visible = "\n".join(
        [
            result.short_answer,
            result.pm_report_markdown,
            result.evidence_report_markdown,
            visible_card,
        ]
    )

    assert context.evidence.profile_result_hash not in visible
    assert context.competitor_profile_version_id not in visible
    for internal in ("core3_", "sha256:", "反事实", "门禁", "M12", "result_hash"):
        assert internal not in visible
    assert "产品经理怎么做" in result.pm_report_markdown
    assert "用户会比较谁" in result.pm_report_markdown
    assert "查看用户选择对比" not in visible_card


def test_question_answer_uses_saved_business_view_and_keeps_boundary(session) -> None:
    context = _context(session)
    answer = answer_competitor_profile_question(
        context,
        "当前价格和销量受到谁的压力？",
    )

    assert answer.competitor_profile_version_id == context.competitor_profile_version_id
    assert answer.profile_result_hash == context.evidence.profile_result_hash
    assert "不临时改变比较对象或重点名单" in answer.boundary_cn
    assert answer.answer_cn
    assert answer.answer_cn != _selection_summary(context.business)


def test_presentation_rejects_unavailable_or_partial_context() -> None:
    context = CompetitorProfileConsumptionContext(
        status="profile_unavailable",
        message_cn="当前没有可用画像。",
    )

    with pytest.raises(ValueError, match="requires one available context"):
        build_competitor_profile_presentation(context)


def test_pm_summaries_turn_saved_rows_into_product_decisions() -> None:
    business = SimpleNamespace(
        目标产品="海信 65E7Q",
        重点竞品=[
            {
                "产品": "海信 75E7Q",
                "主要回答": "产品线与使用场景",
            }
        ],
        本品优势=[],
        可替代价值=[
            {
                "参照产品": "TV-75",
                "用户价值": ["相关产品价值", "客厅换新一步到位", "HDMI 2.1连接"],
            },
            {
                "参照产品": "TV-85",
                "用户价值": ["客厅换新一步到位", "游戏低延迟"],
            },
        ],
        价格销量压力=[
            {
                "参照产品": "TV-75",
                "价格差幅": "0.197289",
                "周均销量倍数": "2.452165",
                "市场压力方向": "更高价格获得市场接受",
            },
            {
                "参照产品": "TV-85",
                "价格差幅": "0.014307",
                "周均销量倍数": "3.336986",
                "市场压力方向": "同预算竞争压力",
            },
        ],
        同品牌产品线=[],
        配置决策=[
            {
                "参照产品": "TV-75",
                "差异配置": ["HDMI 2.1连接", "局部控光"],
                "建议动作": "评估是否值得跟进",
            },
            {
                "参照产品": "TV-85",
                "差异配置": ["屏幕尺寸英寸", "局部控光", "游戏低延迟"],
                "建议动作": "评估是否值得跟进",
            },
        ],
        竞品对比=[
            {
                "产品编号": "TV-75",
                "产品": "海信 75E7Q",
                "可以回答": ["产品线与使用场景", "价格与销量压力"],
            },
            {
                "产品编号": "TV-85",
                "产品": "雷鸟 85R69A ULTRA",
                "可以回答": ["价格与销量压力"],
            },
        ],
    )

    selection = _selection_summary(business)
    substitution = _substitution_summary(business)
    pressure = _pressure_summary(business)
    configuration = _configuration_summary(business)
    action = _action_summary(business)

    assert "不能把任何一款产品列为本品的直接二选一对象" in selection
    assert "海信 75E7Q" in selection
    assert "客厅换新一步到位（2款）" in substitution
    assert "相关产品价值" not in substitution
    assert "HDMI 2.1" not in substitution
    assert "海信 75E7Q均价比本品高19.7%" in pressure
    assert "周均销量是本品2.45倍" in pressure
    assert "雷鸟 85R69A ULTRA均价比本品高1.4%" in pressure
    assert "TV-75" not in pressure
    assert "局部控光（2款）" in configuration
    assert "游戏低延迟（1款）" in configuration
    assert "HDMI 2.1" not in configuration
    assert "先明确本品与海信 75E7Q的产品角色分工" in action
    assert "不把降价作为第一动作" in action


def test_cross_brand_action_uses_market_positioning_language() -> None:
    business = SimpleNamespace(
        目标产品="海信 KFR-35GW/S550-X1",
        重点竞品=[{"产品": "华凌 KFR-35GW/N8HA1III-P"}],
        可替代价值=[],
        价格销量压力=[],
        竞品对比=[],
    )

    action = _action_summary(business)

    assert "本品相对华凌 KFR-35GW/N8HA1III-P的目标用户和价值取舍" in action
    assert "产品角色分工" not in action
