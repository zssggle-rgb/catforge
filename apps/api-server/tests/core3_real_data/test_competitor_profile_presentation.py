from __future__ import annotations

import json

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
    assert "不重新召回" in answer.boundary_cn
    assert answer.answer_cn


def test_presentation_rejects_unavailable_or_partial_context() -> None:
    context = CompetitorProfileConsumptionContext(
        status="profile_unavailable",
        message_cn="当前没有可用画像。",
    )

    with pytest.raises(ValueError, match="requires one available context"):
        build_competitor_profile_presentation(context)
