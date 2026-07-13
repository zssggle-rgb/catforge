from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.cli import catforge_analyst
from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.ability_registry import get_ability
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SellpointValueReleaseQualityStatus,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_qa import (
    ProfileQaTargetAmbiguousError,
    SellpointValueProfileQaService,
    route_profile_question,
)
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators
from tests.core3_real_data.test_sellpoint_value_profile_persistence import (
    _bundle,
    _create_dependencies,
    _create_profile_tables,
    _engine,
    _repository,
    _mark_version_ready,
    _source_batch,
    _version_payload,
)


class _NoUpstreamHandlers:
    def __init__(self) -> None:
        self.call_count = 0

    def __getattr__(self, name: str) -> Any:
        self.call_count += 1
        raise AssertionError(f"profile Q&A must not call upstream: {name}")


@pytest.fixture
def qa_session() -> Session:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        _create_profile_tables(connection)
    db = Session(engine, autoflush=False, future=True)
    db.add_all(
        [
            entities.CategoryProject(
                project_id="project-tv", name="TV project", category_code="TV"
            ),
            _source_batch("batch-tv", "project-tv", "TV"),
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _context() -> AnalystContext:
    return AnalystContext(
        project_id="project-tv",
        category_code="TV",
        batch_id="batch-tv",
        product_category="TV",
    )


def _decision(
    capability_code: str,
    capability_name_cn: str,
    classification: str,
) -> dict[str, Any]:
    return {
        "capability_code": capability_code,
        "capability_name_cn": capability_name_cn,
        "classification": classification,
        "candidate_scope_ids": ["TV-COMPETITOR", "TV-REJECTED"],
        "business_reason_cn": f"{capability_name_cn} 已按当前用户价值和市场表现完成判断。",
        "boundary_cn": "只适用于当前画像保存的产品范围。",
        "confidence": 0.86,
        "review_status": "auto_pass",
    }


def _question_analyses() -> list[dict[str, Any]]:
    common = {
        "business_question_cn": "这项用户价值相对其他产品是否形成优势",
        "battlefield_code": "BF-PREMIUM-PICTURE",
        "value_bundle_code": "picture_bundle",
        "candidate_pool_type": "competitor",
        "eligible_candidate_ids": ["TV-COMPETITOR"],
        "selected_candidate_ids": ["TV-COMPETITOR"],
        "rejected_candidates": [
            {
                "candidate_sku_codes": ["TV-REJECTED"],
                "method": "same_budget_pool",
                "reasons": ["用户价值组合不同"],
            }
        ],
        "method": "direct_sku",
        "selection_reasons": ["用户价值接近且预算重叠"],
        "degradation_reasons": [],
        "metrics": ["price", "volume"],
        "conclusion_boundary_cn": "当前市场表现比较，不作随机实验解释。",
        "sample_manifest_hash": "question-set-hash",
        "result_hash": "question-result-hash",
    }
    return [
        {
            **common,
            "question_code": "value_relative_advantage",
            "source_question_code": "relative_highlight",
        },
        {
            **common,
            "question_code": "current_price_support",
            "source_question_code": "price_realization",
            "business_question_cn": "当前价格是否得到用户价值支撑",
            "result_hash": "price-question-result-hash",
        },
        {
            **common,
            "question_code": "scale_conversion",
            "source_question_code": "volume_realization",
            "business_question_cn": "当前用户价值是否转化成销量",
            "result_hash": "volume-question-result-hash",
        },
    ]


def _rich_bundle(
    version_id: str,
    *,
    profile_version: str,
    variant: str = "current",
) -> SellpointValueDraftBundle:
    source = _bundle(version_id, profile_version=profile_version)
    decisions = [
        _decision("local_dimming", "分区控光", "retain"),
        _decision("ai_picture", "AI 画质", "unconverted"),
        _decision("quantum_dot", "量子点", "do_not_follow"),
        _decision("bright_room", "高亮客厅画质", "missing_competitive_gap"),
        _decision("hdmi_21", "HDMI 2.1", "table_stake"),
    ]
    if variant == "previous":
        decisions[0] = _decision("local_dimming", "分区控光", "unconverted")
    profile = source.profile.model_copy(
        update={
            "investment_decisions_json": decisions,
            "pm_decisions_json": {
                "investments_to_retain": ["分区控光"],
                "investments_not_converted": ["AI 画质"],
                "configurations_not_to_follow": ["量子点"],
                "missing_competitive_gaps": ["高亮客厅画质"],
                "table_stakes_to_maintain": ["HDMI 2.1"],
                "current_price_support_cn": "当前价格由画质用户价值和不弱的销量表现共同支撑。",
                "growth_action_cn": "如果优先走量，应先评估价格位置，再强化画质用户表达。",
            },
            "question_analyses_json": _question_analyses(),
            "battlefield_options_json": [
                {
                    "battlefield_code": "BF-PREMIUM-PICTURE",
                    "option_type": "strengthen_existing",
                    "summary_cn": "先增强已有高端画质价值",
                }
            ],
            "candidate_universe_summary_json": {
                "candidate_manifest_hash": f"candidate-{profile_version}",
                "competitor_count": 2,
                "reference_count": 1,
            },
        }
    )
    competitor = source.candidates[0].model_copy(
        update={
            "eligible_questions_json": [
                "current_price_support",
                "value_relative_advantage",
                "scale_conversion",
                "specific_competitor",
            ],
            "selected_questions_json": [
                "current_price_support",
                "value_relative_advantage",
                "scale_conversion",
            ],
            "selection_reasons_json": {
                "current_price_support": "用户价值接近且预算重叠",
                "value_relative_advantage": "用户价值接近且预算重叠",
                "scale_conversion": "用户价值接近且预算重叠",
            },
            "market_summary_json": {
                "price_wavg": 4800,
                "avg_weekly_sales_volume": 38,
            },
        }
    )
    rejected = competitor.model_copy(
        update={
            "result_hash": f"rejected-{profile_version}",
            "candidate_sku_code": "TV-REJECTED",
            "candidate_brand_name": "小米",
            "candidate_model_name": "S Pro",
            "selected_questions_json": [],
            "selection_reasons_json": {},
        }
    )
    reference = source.candidates[1].model_copy(
        update={
            "market_summary_json": {
                "price_wavg": 5200,
                "avg_weekly_sales_volume": 25,
            }
        }
    )
    item = source.value_items[0].model_copy(
        update={
            "capability_codes_json": [row["capability_code"] for row in decisions],
            "investment_decisions_json": decisions,
            "investment_classifications_json": [
                row["classification"] for row in decisions
            ],
            "question_result_refs_json": _question_analyses(),
            "question_codes_json": [
                "current_price_support",
                "scale_conversion",
                "value_relative_advantage",
            ],
            "price_realization_json": {
                "status": "available",
                "current_price": 5000,
                "own_price_curve": None,
            },
            "volume_realization_json": {
                "status": "available",
                "raw_market_position": {"avg_weekly_sales_volume": 42},
            },
        }
    )
    candidates = [competitor, reference]
    if variant != "previous":
        candidates.insert(1, rejected)
    return SellpointValueDraftBundle(
        profile=profile,
        candidates=candidates,
        value_items=[item],
    )


def _write_version(
    session: Session,
    *,
    profile_version: str,
    variant: str,
    publish: bool,
):
    repository = _repository(session)
    version = repository.create_version(_version_payload(profile_version))
    repository.write_draft(
        _rich_bundle(
            version.sellpoint_value_profile_version_id,
            profile_version=profile_version,
            variant=variant,
        )
    )
    if publish:
        _mark_version_ready(repository, version.sellpoint_value_profile_version_id)
        repository.review_version(
            sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
            reviewed_by="reviewer",
            release_quality_status=SellpointValueReleaseQualityStatus.READY,
        )
        repository.publish_version(
            sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
            published_by="approver",
        )
    session.commit()
    return repository


@pytest.mark.parametrize(
    ("question", "topic"),
    [
        ("哪些投入值得保留", "retain_investment"),
        ("哪些投入还没有转化成用户价值", "unconverted_investment"),
        ("哪个竞品配置不用跟", "do_not_follow"),
        ("有哪些缺口必须补齐", "missing_gap"),
        ("当前价格为什么撑得住", "price_support"),
        ("降价能增加多少销量", "price_volume_increment"),
        ("如果要走量应该改卖点还是改价格", "volume_action"),
        ("为什么选 TCL 作为对照", "competitor_selection"),
        ("哪些结论来自竞品，哪些来自分析参照", "source_pool"),
        ("应该增强已有价值战场还是进入新战场", "battlefield_action"),
        ("HDMI 2.1 是不是基础竞争能力", "table_stake"),
        ("与上一版相比候选发生了什么变化", "version_change"),
        ("利润率是多少", "unsupported"),
    ],
)
def test_router_covers_product_manager_topics(question: str, topic: str) -> None:
    assert route_profile_question(question) == topic


def test_profile_qa_ability_is_explicit_and_reads_no_upstream_modules() -> None:
    ability = get_ability("sellpoint-value-profile-ask")

    assert ability is not None
    assert ability.status == "implemented"
    assert ability.source_modules == ()


def test_profile_qa_answers_ten_business_topics_from_one_published_profile(
    qa_session: Session,
) -> None:
    repository = _write_version(
        qa_session,
        profile_version="spv-current",
        variant="current",
        publish=True,
    )
    service = SellpointValueProfileQaService(repository)
    cases = [
        ("哪些投入值得保留", "retain_investment", "分区控光", None),
        ("哪些投入没有转化", "unconverted_investment", "AI 画质", None),
        ("哪些配置不用跟", "do_not_follow", "量子点", None),
        ("需要补齐哪些缺口", "missing_gap", "高亮客厅画质", None),
        ("HDMI 2.1 是否只是基础竞争能力", "table_stake", "HDMI 2.1", None),
        ("当前价格为什么获得支撑", "price_support", "价格", None),
        ("如果要走量应该改什么", "volume_action", "价格位置", None),
        (
            "为什么选 TCL 作为对照",
            "competitor_selection",
            "TCL 65Q9L PRO",
            "TV-COMPETITOR",
        ),
        ("哪些来自分析参照", "source_pool", "市场与产品设计参照", None),
        ("应该增强已有价值战场还是进入新战场", "battlefield_action", "价格位置", None),
    ]

    for question, topic, expected, candidate_code in cases:
        answer = service.answer(
            batch_id="batch-tv",
            sku_code="TV001",
            question=question,
            candidate_sku_code=candidate_code,
        )
        assert answer is not None
        assert answer.topic_code == topic
        assert answer.answer_status == "answered"
        assert expected in answer.direct_answer_cn
        assert answer.profile_version == "spv-current"
        assert answer.release_status == "published"
        assert answer.result_hash == "profile-result-TV001"
        assert answer.answer_hash
        assert answer.fact_paths
        assert "反事实" not in answer.model_dump_json()


def test_candidate_rejection_exact_increment_and_unknown_topic_are_honest(
    qa_session: Session,
) -> None:
    repository = _write_version(
        qa_session,
        profile_version="spv-current",
        variant="current",
        publish=True,
    )
    service = SellpointValueProfileQaService(repository)

    rejected = service.answer(
        batch_id="batch-tv",
        sku_code="TV001",
        question="为什么没有选小米作为对照",
        candidate_sku_code="TV-REJECTED",
    )
    increment = service.answer(
        batch_id="batch-tv",
        sku_code="TV001",
        question="降价能增加多少销量",
    )
    unsupported = service.answer(
        batch_id="batch-tv",
        sku_code="TV001",
        question="这款产品的利润率是多少",
    )

    assert rejected is not None and "没有被当前问题最终采用" in rejected.direct_answer_cn
    assert "用户价值组合不同" in rejected.direct_answer_cn
    assert rejected.candidate_record_ids
    assert increment is not None and increment.answer_status == "unknown"
    assert "不能量化" in increment.direct_answer_cn
    assert "own_price_curve" in increment.limitations[0]
    assert unsupported is not None and unsupported.topic_code == "unsupported"
    assert unsupported.answer_status == "unknown"


def test_answer_locks_hash_and_version_diff_reads_saved_profiles_only(
    qa_session: Session,
) -> None:
    _write_version(
        qa_session,
        profile_version="spv-previous",
        variant="previous",
        publish=True,
    )
    repository = _write_version(
        qa_session,
        profile_version="spv-current",
        variant="current",
        publish=True,
    )
    service = SellpointValueProfileQaService(repository)

    mismatch = service.answer(
        batch_id="batch-tv",
        sku_code="TV001",
        question="哪些投入值得保留",
        expected_result_hash="wrong-report-hash",
    )
    diff = service.answer(
        batch_id="batch-tv",
        sku_code="TV001",
        question="与上一版相比发生了什么变化",
        compare_profile_version="spv-previous",
    )
    missing_version = service.answer(
        batch_id="batch-tv",
        sku_code="TV001",
        question="与上一版相比发生了什么变化",
    )

    assert mismatch is not None and mismatch.answer_status == "unknown"
    assert "不是同一份结果" in mismatch.direct_answer_cn
    assert diff is not None and diff.answer_status == "answered"
    assert "候选新增 1 款" in diff.direct_answer_cn
    assert "投入判断变化 1 项" in diff.direct_answer_cn
    assert missing_version is not None and missing_version.answer_status == "unknown"


def test_orchestrator_has_zero_upstream_calls_and_formats_four_sections(
    qa_session: Session,
) -> None:
    repository = _write_version(
        qa_session,
        profile_version="spv-current",
        variant="current",
        publish=True,
    )
    handlers = _NoUpstreamHandlers()
    orchestrator = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )

    result = orchestrator.sellpoint_value_profile_ask(
        _context(),
        sku_code="TV001",
        question="当前价格为什么获得支撑",
    )
    text = catforge_analyst.format_business_text(result)

    assert result["status"] == "ok"
    assert result["atoms_used"] == []
    assert handlers.call_count == 0
    assert "画像事实｜" in text
    assert "产品工作含义｜" in text
    assert "证据边界｜" in text
    answer = result["result"]["sellpoint_value_profile_answer"]
    assert result["evidence"][0]["result_hash"] == answer["result_hash"]


def test_cli_exposes_explicit_profile_lock_arguments() -> None:
    args = catforge_analyst.build_parser().parse_args(
        [
            "sellpoint-value-profile-ask",
            "--sku-code",
            "TV001",
            "--question",
            "为什么选这款竞品",
            "--profile-version",
            "spv-draft",
            "--expected-result-hash",
            "result-hash",
            "--candidate-sku-code",
            "TV-COMPETITOR",
            "--compare-profile-version",
            "spv-previous",
        ]
    )

    assert args.profile_question == "为什么选这款竞品"
    assert args.profile_version == "spv-draft"
    assert args.expected_result_hash == "result-hash"
    assert args.candidate_sku_code == "TV-COMPETITOR"
    assert args.compare_profile_version == "spv-previous"


def test_qa_does_not_read_draft_without_explicit_version(qa_session: Session) -> None:
    repository = _write_version(
        qa_session,
        profile_version="spv-draft",
        variant="current",
        publish=False,
    )
    handlers = _NoUpstreamHandlers()
    orchestrator = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )

    default = orchestrator.sellpoint_value_profile_ask(
        _context(), sku_code="TV001", question="哪些投入值得保留"
    )
    preview = orchestrator.sellpoint_value_profile_ask(
        _context(),
        sku_code="TV001",
        profile_version="spv-draft",
        question="哪些投入值得保留",
    )

    assert default["status"] == "not_found"
    assert "不会临时重算" in default["limitations"][0]
    assert preview["status"] == "ok"
    assert preview["result"]["sellpoint_value_profile_answer"]["release_status"] == "draft"
    assert handlers.call_count == 0


def test_cli_forwards_profile_qa_lock_arguments(monkeypatch, capsys) -> None:
    captured = {}

    class _SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

    def _run(_db, **kwargs):
        captured.update(kwargs)
        return {"status": "not_found", "result": {}}

    monkeypatch.setattr(catforge_analyst, "SessionLocal", _SessionContext)
    monkeypatch.setattr(catforge_analyst, "run_analyst_command", _run)

    exit_code = catforge_analyst.main(
        [
            "sellpoint-value-profile-ask",
            "--sku-code",
            "TV001",
            "--question",
            "为什么选这款产品",
            "--profile-version",
            "spv-draft",
            "--expected-result-hash",
            "result-hash",
            "--candidate-sku-code",
            "TV-COMPETITOR",
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    assert captured["question"] == "为什么选这款产品"
    assert captured["profile_version"] == "spv-draft"
    assert captured["expected_result_hash"] == "result-hash"
    assert captured["candidate_sku_code"] == "TV-COMPETITOR"
    assert "not_found" in capsys.readouterr().out


def test_stale_blocked_explicit_preview_is_limited(qa_session: Session) -> None:
    repository = _repository(qa_session)
    version = repository.create_version(_version_payload("spv-blocked"))
    source = _rich_bundle(
        version.sellpoint_value_profile_version_id,
        profile_version="spv-blocked",
    )
    profile = source.profile.model_copy(
        update={
            "analysis_state": "blocked",
            "freshness_status": "stale",
            "review_required": True,
            "review_status": "review_required",
        }
    )
    repository.write_draft(source.model_copy(update={"profile": profile}))

    answer = SellpointValueProfileQaService(repository).answer(
        batch_id="batch-tv",
        sku_code="TV001",
        profile_version="spv-blocked",
        question="哪些投入值得保留",
    )

    assert answer is not None and answer.answer_status == "limited"
    assert "只能用于回看" in answer.evidence_boundary_cn
    assert "不能形成正式产品取舍" in answer.evidence_boundary_cn


def test_ambiguous_saved_profile_target_requires_sku_code() -> None:
    class _AmbiguousRepository:
        def resolve_profile_targets(self, **kwargs):
            del kwargs
            return [
                {"sku_code": "TV001", "model_name": "65E7Q"},
                {"sku_code": "TV002", "model_name": "65E7Q Pro"},
            ]

    service = SellpointValueProfileQaService(_AmbiguousRepository())  # type: ignore[arg-type]

    with pytest.raises(ProfileQaTargetAmbiguousError) as exc_info:
        service.answer(
            batch_id="batch-tv",
            query="65E7Q",
            question="哪些投入值得保留",
        )

    assert [row["sku_code"] for row in exc_info.value.candidates] == [
        "TV001",
        "TV002",
    ]
