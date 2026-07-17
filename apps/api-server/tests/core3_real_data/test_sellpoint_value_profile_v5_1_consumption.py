from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.ability_registry import get_ability
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_aggregation import (
    aggregate_sku_conclusion,
    aggregate_value_conclusion,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_consumer import (
    SellpointValueV51ConsumerReadRequest,
    SellpointValueV51ConsumerReader,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_enhancements import (
    adapt_strict_market_implied_wtp,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SellpointValueV51GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_qa import (
    _investment_work_implication,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_report import (
    StoredSellpointValuePmReport,
    _v5_1_first_screen,
    render_stored_profile_markdown,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    QuestionConclusionStatus,
    QuestionConclusionStrength,
    SkuConclusionAggregationInput,
    ValueConclusionAggregationInput,
)
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_materialization import (
    FixtureProvider,
    _materialization_input,
    _repository,
    _request,
    session as _materialization_session,
)


class NoUpstreamHandlers:
    def __init__(self) -> None:
        self.call_count = 0

    def __getattr__(self, name: str) -> Any:
        self.call_count += 1
        raise AssertionError(f"V5.1 consumer attempted upstream analysis: {name}")


@pytest.fixture
def consumer_session():
    fixture = _materialization_session.__wrapped__()
    db = next(fixture)
    try:
        yield db
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass


def _context() -> AnalystContext:
    return AnalystContext(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        product_category="TV",
    )


def _generate(consumer_session, source):
    repository = _repository(consumer_session)
    readback = SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider({source.target.sku_code: source}),
    ).generate_draft(_request(source), sku_code=source.target.sku_code)
    return repository, readback


def _mark_published_current(consumer_session, version_id: str) -> None:
    now = datetime.now(timezone.utc)
    version = consumer_session.get(
        entities.Core3SellpointValueProfileVersion,
        version_id,
    )
    assert version is not None
    historical = consumer_session.get(
        entities.Core3SellpointValueProfileVersion,
        "spv-v5-published",
    )
    assert historical is not None
    historical.is_current = False
    consumer_session.flush()
    version.release_status = "published"
    version.is_current = True
    version.published_at = now
    for entity in (
        entities.Core3SkuSellpointValueProfile,
        entities.Core3SkuSellpointValueCandidate,
        entities.Core3SkuSellpointValueItem,
    ):
        rows = list(
            consumer_session.execute(
                select(entity).where(
                    entity.sellpoint_value_profile_version_id == version_id
                )
            ).scalars()
        )
        for row in rows:
            row.release_status = "published"
            row.is_current = True
    consumer_session.commit()


def _without_strict_wtp(source):
    value = source.values[0]
    unavailable = adapt_strict_market_implied_wtp(
        project_id=source.project_id,
        category_code=source.category_code,
        target_sku_code=source.target.sku_code,
        value_bundle_code=value.value_bundle_code,
        source=None,
    )
    old_hash = value.strict_market_implied_wtp.result_hash
    signals = [
        signal.model_copy(
            update={
                "status": QuestionConclusionStatus.NO_CONCLUSION,
                "confidence": None,
                "review_required": False,
                "review_reasons": [],
                "source_result_hash": unavailable.result_hash,
            }
        )
        if signal.source_result_hash == old_hash
        or signal.question_code == "quant_strict_wtp"
        else signal
        for signal in value.question_signals
    ]
    quantifications = [
        row.model_copy(
            update={
                "status": QuestionConclusionStatus.NO_CONCLUSION,
                "strength": QuestionConclusionStrength.NONE,
                "result": {},
                "direct_market_gaps": [],
                "review_required": False,
                "review_reasons": [],
                "result_hash": unavailable.result_hash,
            }
        )
        if str(getattr(row.layer, "value", row.layer)) == "strict_market_implied_wtp"
        else row
        for row in value.quantification_stack.results
    ]
    conclusion = aggregate_value_conclusion(
        ValueConclusionAggregationInput(
            project_id=source.project_id,
            category_code=source.category_code,
            target_sku_code=source.target.sku_code,
            value_bundle_code=value.value_bundle_code,
            question_signals=signals,
        )
    )
    updated_value = value.model_copy(
        update={
            "question_signals": signals,
            "quantification_stack": value.quantification_stack.model_copy(
                update={"results": quantifications}
            ),
            "strict_market_implied_wtp": unavailable,
            "value_conclusion": conclusion,
        }
    )
    sku = aggregate_sku_conclusion(
        SkuConclusionAggregationInput(
            project_id=source.project_id,
            category_code=source.category_code,
            target_sku_code=source.target.sku_code,
            value_results=[conclusion],
        )
    )
    return source.model_copy(update={"values": [updated_value], "sku_conclusion": sku})


def _no_conclusion(source):
    value = source.values[0]
    signals = [
        signal.model_copy(
            update={
                "status": QuestionConclusionStatus.NO_CONCLUSION,
                "confidence": None,
                "review_required": False,
                "review_reasons": [],
            }
        )
        for signal in value.question_signals
    ]
    conclusion = aggregate_value_conclusion(
        ValueConclusionAggregationInput(
            project_id=source.project_id,
            category_code=source.category_code,
            target_sku_code=source.target.sku_code,
            value_bundle_code=value.value_bundle_code,
            question_signals=signals,
        )
    )
    updated_value = value.model_copy(
        update={"question_signals": signals, "value_conclusion": conclusion}
    )
    sku = aggregate_sku_conclusion(
        SkuConclusionAggregationInput(
            project_id=source.project_id,
            category_code=source.category_code,
            target_sku_code=source.target.sku_code,
            value_results=[conclusion],
        )
    )
    return source.model_copy(update={"values": [updated_value], "sku_conclusion": sku})


def _invalid(source):
    sku = aggregate_sku_conclusion(
        SkuConclusionAggregationInput(
            project_id=source.project_id,
            category_code=source.category_code,
            target_sku_code=source.target.sku_code,
            value_results=[row.value_conclusion for row in source.values],
            structural_invalid_reasons=["fixture_integrity_error"],
        )
    )
    return source.model_copy(update={"sku_conclusion": sku})


def test_formal_reader_does_not_fallback_to_published_v5(consumer_session) -> None:
    result = SellpointValueV51ConsumerReader(_repository(consumer_session)).read(
        SellpointValueV51ConsumerReadRequest(
            project_id="project-1",
            category_code="TV",
            batch_id="batch-1",
            sku_code="TV-TARGET",
        )
    )

    assert result.status == "profile_unavailable"
    assert consumer_session.get(
        entities.Core3SellpointValueProfileVersion,
        "spv-v5-published",
    ).is_current


def test_preview_requires_profile_version_and_immutable_version_id() -> None:
    with pytest.raises(ValidationError):
        SellpointValueV51ConsumerReadRequest(
            project_id="project-1",
            category_code="TV",
            batch_id="batch-1",
            access_mode="preview",
            sku_code="TV-TARGET",
            profile_version="spv-v51-r1",
        )


def test_unknown_investments_are_not_reported_as_no_conversion_shortfall() -> None:
    screen = _v5_1_first_screen(
        SimpleNamespace(
            values=[],
            competitor_source=SimpleNamespace(
                target_market=SimpleNamespace(screen_size_inch=None)
            ),
        ),
        [],
        consumer_status="usable_conclusion",
        unknown_investments=[
            "冷暖能力与空间匹配",
            "长期用电成本可控",
            "远程控制与操作省事",
        ],
    )

    assert "尚不能判断冷暖能力与空间匹配等3类投入中哪些值得继续加码" in (
        screen.retain_cn
    )
    assert "尚不能判断冷暖能力与空间匹配等3类投入中哪些已转化" in (
        screen.unconverted_cn
    )
    assert "不能把未知解释成没有短板" in screen.unconverted_cn
    assert "均未出现明确" not in screen.unconverted_cn
    assert "先补齐现有投入的用户价值转化判断" in screen.competitor_action_cn


def test_unknown_investment_qa_does_not_claim_a_confirmed_resource_priority() -> (
    None
):
    implication = _investment_work_implication([])
    explicit_unknown = _investment_work_implication(
        [SimpleNamespace(action_code="unknown")]
    )

    assert "补齐投入与用户价值转化判断前" in implication
    assert "已确认" not in implication
    assert explicit_unknown == implication


def test_preview_report_and_qa_consume_one_saved_hash_without_upstream(
    consumer_session,
) -> None:
    source = _without_strict_wtp(_materialization_input())
    repository, readback = _generate(consumer_session, source)
    version_id = readback.persisted.version.sellpoint_value_profile_version_id
    handlers = NoUpstreamHandlers()
    orchestrator = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )

    report_result = orchestrator.sellpoint_value_pm_v5(
        _context(),
        sku_code="TV-TARGET",
        enable_v5=True,
        preview_profile_version=source.profile_version,
        preview_sellpoint_value_profile_version_id=version_id,
    )
    qa_result = orchestrator.sellpoint_value_profile_ask(
        _context(),
        sku_code="TV-TARGET",
        question="当前价格为什么撑得住",
        profile_access_mode="preview",
        profile_version=source.profile_version,
        sellpoint_value_profile_version_id=version_id,
        expected_result_hash=readback.profile.result_hash,
    )

    assert report_result["status"] == "ok"
    assert qa_result["status"] == "ok"
    report = report_result["result"]["sellpoint_value_pm_v5"]
    artifacts = report_result["result"]["sellpoint_value_pm_v5_answer"]
    answer = qa_result["result"]["sellpoint_value_profile_answer"]
    assert report["schema_version"] == "sku_sellpoint_value_pm_report_v1_1"
    assert report["profile_result_hash"] == readback.profile.result_hash
    assert artifacts["result_hash"] == readback.profile.result_hash
    assert artifacts["feishu_card_payload"]["result_hash"] == (
        readback.profile.result_hash
    )
    assert answer["result_hash"] == readback.profile.result_hash
    assert report["candidate_manifest_hash"] == source.candidate_pools.result_hash
    assert report["candidate_count"] == len(source.candidate_pools.formal_competitors)
    assert report["reference_count"] == len(source.candidate_pools.analysis_references)
    assert report["value_accounts"][0]["core_sellpoints_cn"] == ["picture_quality"]
    assert "当前价格支撑存在压力" in report["first_screen"]["price_support_cn"]
    assert "若销量优先" in report["first_screen"]["growth_action_cn"]
    assert "定位取舍" in report["first_screen"]["sku_role_cn"]
    rendered = str(report_result)
    assert "严格 WTP" not in rendered
    assert "无法计算" not in rendered
    assert "高1000元" in rendered
    visible_outputs = "\n".join(
        (
            artifacts["short_answer"],
            render_stored_profile_markdown(
                StoredSellpointValuePmReport.model_validate(report),
                title="用户卖点价值分析",
            ),
            artifacts["feishu_card_payload"]["body"]["elements"][0]["content"],
        )
    )
    bounded_markdown = render_stored_profile_markdown(
        StoredSellpointValuePmReport.model_validate(report).model_copy(
            update={
                "limitations": [
                    "market_association_not_randomized_causality",
                    "common_weeks_not_required",
                    "v4_strict_amount_gate_not_passed",
                ]
            }
        ),
        title="用户卖点价值分析",
    )
    assert "market_association_not_randomized_causality" not in bounded_markdown
    assert "common_weeks_not_required" not in bounded_markdown
    assert "v4_strict_amount_gate_not_passed" not in bounded_markdown
    assert "## 五、结论边界" in bounded_markdown
    assert "不代表单一卖点的实验因果增量" in bounded_markdown
    assert source.profile_version not in visible_outputs
    assert readback.profile.result_hash not in visible_outputs
    assert source.candidate_pools.result_hash not in visible_outputs
    assert "**SKU角色**" in visible_outputs
    assert handlers.call_count == 0


def test_preview_qa_projects_every_saved_business_topic_without_recomputation(
    consumer_session,
) -> None:
    source = _materialization_input(profile_version="spv-v51-qa-topics")
    repository, readback = _generate(consumer_session, source)
    version_id = readback.persisted.version.sellpoint_value_profile_version_id
    handlers = NoUpstreamHandlers()
    orchestrator = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )
    topics = {
        "retain_investment": "哪些投入值得保留",
        "capability_investment": "画质能力是否继续投入",
        "unconverted_investment": "哪些投入没有转化",
        "do_not_follow": "哪些竞品配置不用跟",
        "missing_gap": "当前还缺什么竞争能力",
        "price_support": "当前价格有用户价值支撑吗",
        "volume_action": "如果追求销量应该先做什么",
        "sku_role": "这个 SKU 应该承担什么产品角色",
        "price_volume_increment": "降价能增加多少销量",
        "competitor_selection": "为什么选择这些竞品",
        "source_pool": "正式竞品和分析参照分别有哪些",
        "battlefield_action": "应该增强已有价值战场还是进入新战场",
        "table_stake": "哪些只是基础竞争能力",
        "version_change": "相比上一版有什么变化",
        "unsupported": "请预测明年的行业政策",
    }

    answers = {}
    for topic_code, question in topics.items():
        result = orchestrator.sellpoint_value_profile_ask(
            _context(),
            sku_code="TV-TARGET",
            question=question,
            profile_access_mode="preview",
            profile_version=source.profile_version,
            sellpoint_value_profile_version_id=version_id,
            expected_result_hash=readback.profile.result_hash,
            topic_code=topic_code,
        )
        assert result["status"] == "ok"
        answer = result["result"]["sellpoint_value_profile_answer"]
        assert answer["topic_code"] == topic_code
        assert answer["result_hash"] == readback.profile.result_hash
        answers[topic_code] = answer

    assert answers["price_support"]["profile_facts"]
    assert answers["volume_action"]["profile_facts"]
    assert answers["sku_role"]["profile_facts"]
    assert "角色" in answers["sku_role"]["direct_answer_cn"]
    assert (
        "市场关联不解释为随机实验因果"
        in answers["price_volume_increment"]["evidence_boundary_cn"]
    )
    assert answers["competitor_selection"]["profile_facts"]
    assert "正式竞品" in answers["source_pool"]["direct_answer_cn"]
    assert answers["battlefield_action"]["profile_facts"]
    assert "本品当前已形成的用户价值战场：画质体验" in (
        answers["battlefield_action"]["direct_answer_cn"]
    )
    assert any(
        row["record_type"] == "value_item"
        for row in answers["battlefield_action"]["profile_facts"]
    )
    assert answers["table_stake"]["answer_status"] == "limited"
    assert answers["version_change"]["answer_status"] == "unknown"
    assert answers["unsupported"]["answer_status"] == "unknown"

    missing_candidate = orchestrator.sellpoint_value_profile_ask(
        _context(),
        sku_code="TV-TARGET",
        question="为什么没有选择这个竞品",
        profile_access_mode="preview",
        profile_version=source.profile_version,
        sellpoint_value_profile_version_id=version_id,
        topic_code="competitor_selection",
        candidate_sku_code="TV-NOT-IN-POOL",
    )["result"]["sellpoint_value_profile_answer"]
    assert missing_candidate["answer_status"] == "limited"
    assert "candidate_not_in_formal_pool" in missing_candidate["limitations"]

    hash_mismatch = orchestrator.sellpoint_value_profile_ask(
        _context(),
        sku_code="TV-TARGET",
        question="当前价格有支撑吗",
        profile_access_mode="preview",
        profile_version=source.profile_version,
        sellpoint_value_profile_version_id=version_id,
        expected_result_hash="sha256:not-the-current-profile",
    )["result"]["sellpoint_value_profile_answer"]
    assert hash_mismatch["answer_status"] == "unknown"
    assert "expected_result_hash_mismatch" in hash_mismatch["limitations"]
    assert handlers.call_count == 0


def test_formal_report_reads_only_current_published_v5_1(consumer_session) -> None:
    source = _materialization_input(profile_version="spv-v51-formal")
    repository, readback = _generate(consumer_session, source)
    version_id = readback.persisted.version.sellpoint_value_profile_version_id
    _mark_published_current(consumer_session, version_id)
    handlers = NoUpstreamHandlers()

    result = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    ).sellpoint_value_pm_v5(
        _context(),
        sku_code="TV-TARGET",
        enable_v5=True,
    )

    assert result["status"] == "ok"
    report = result["result"]["sellpoint_value_pm_v5"]
    assert report["release_status"] == "published"
    assert report["profile_version"] == "spv-v51-formal"
    assert report["profile_result_hash"] == readback.profile.result_hash
    assert handlers.call_count == 0


def test_no_conclusion_returns_one_business_message_without_recomputation(
    consumer_session,
) -> None:
    source = _no_conclusion(
        _materialization_input(profile_version="spv-v51-no-conclusion")
    )
    repository, readback = _generate(consumer_session, source)
    version_id = readback.persisted.version.sellpoint_value_profile_version_id
    handlers = NoUpstreamHandlers()
    result = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    ).sellpoint_value_pm_v5(
        _context(),
        sku_code="TV-TARGET",
        enable_v5=True,
        preview_profile_version=source.profile_version,
        preview_sellpoint_value_profile_version_id=version_id,
    )

    assert result["status"] == "ok"
    report = result["result"]["sellpoint_value_pm_v5"]
    answer = result["result"]["sellpoint_value_pm_v5_answer"]
    assert report["consumer_status"] == "data_insufficient"
    assert report["value_accounts"] == []
    assert (
        answer["short_answer"].count(
            "现有数据不足，暂不能形成该 SKU 的用户卖点价值结论。"
        )
        == 1
    )
    assert handlers.call_count == 0


def test_preview_with_only_profile_version_is_rejected_by_agent(
    consumer_session,
) -> None:
    source = _materialization_input(profile_version="spv-v51-lock-required")
    repository, _ = _generate(consumer_session, source)
    result = SopOrchestrators(
        NoUpstreamHandlers(),  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    ).sellpoint_value_pm_v5(
        _context(),
        sku_code="TV-TARGET",
        enable_v5=True,
        preview_profile_version=source.profile_version,
    )

    assert result["status"] == "error"
    assert "version id" in result["limitations"][0]


def test_version_comparison_is_rejected_instead_of_silently_ignored(
    consumer_session,
) -> None:
    source = _materialization_input(profile_version="spv-v51-no-version-diff")
    repository, _ = _generate(consumer_session, source)
    handlers = NoUpstreamHandlers()

    result = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    ).sellpoint_value_profile_ask(
        _context(),
        sku_code="TV-TARGET",
        question="相比上一版有什么变化",
        compare_profile_version="spv-v51-previous",
    )

    assert result["status"] == "error"
    assert "双版本 id 锁定合同" in result["limitations"][0]
    assert handlers.call_count == 0


def test_invalid_profile_returns_data_error_without_product_conclusion(
    consumer_session,
) -> None:
    source = _invalid(_materialization_input(profile_version="spv-v51-invalid"))
    repository, readback = _generate(consumer_session, source)
    version_id = readback.persisted.version.sellpoint_value_profile_version_id
    orchestrator = SopOrchestrators(
        NoUpstreamHandlers(),  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )

    report_result = orchestrator.sellpoint_value_pm_v5(
        _context(),
        sku_code="TV-TARGET",
        enable_v5=True,
        preview_profile_version=source.profile_version,
        preview_sellpoint_value_profile_version_id=version_id,
    )
    qa_result = orchestrator.sellpoint_value_profile_ask(
        _context(),
        sku_code="TV-TARGET",
        question="哪些投入值得保留",
        profile_access_mode="preview",
        profile_version=source.profile_version,
        sellpoint_value_profile_version_id=version_id,
    )

    report = report_result["result"]["sellpoint_value_pm_v5"]
    answer = qa_result["result"]["sellpoint_value_profile_answer"]
    assert report["consumer_status"] == "invalid"
    assert "画像数据完整性异常" in report_result["answer_outline"][0]
    assert answer["answer_status"] == "unknown"
    assert answer["direct_answer_cn"].startswith("画像数据完整性异常")


def test_v51_consumer_abilities_and_modules_have_zero_analysis_sources() -> None:
    assert get_ability("sellpoint-value-pm-v5").source_modules == ()
    assert get_ability("sellpoint-value-profile-ask").source_modules == ()
    root = Path(__file__).resolve().parents[2]
    forbidden = {
        "sellpoint_value_profile_input_provider",
        "sellpoint_value_profile_candidate_service",
        "claim_value_pm_v5_service",
        "claim_value_pm_v5_counterfactuals",
        "competitor_set",
    }
    imported: set[str] = set()
    for relative in (
        "app/services/core3_real_data/analyst/sellpoint_value_profile_v5_1_consumer.py",
        "app/services/core3_real_data/analyst/sellpoint_value_profile_v5_1_qa.py",
    ):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.rsplit(".", 1)[-1])
            elif isinstance(node, ast.Import):
                imported.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
    assert imported.isdisjoint(forbidden)
