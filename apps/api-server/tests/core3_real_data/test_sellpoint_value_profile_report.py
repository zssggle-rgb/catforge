from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SellpointValueDraftBundle,
    SellpointValueReleaseQualityStatus,
    SkuSellpointValueCandidateDraft,
    SkuSellpointValueItemDraft,
    SkuSellpointValueProfileDraft,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_report import (
    build_stored_profile_answer_artifacts,
    build_stored_profile_pm_report,
    render_stored_profile_markdown,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_qa import (
    SellpointValueProfileQaService,
)
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators
from app.services.core3_real_data.constants import Core3CategoryCode
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
        if name.startswith("sellpoint_value") or name in {
            "resolve_sku",
            "same_size_price_candidates",
        }:
            self.call_count += 1
            raise AssertionError(f"V5 must not read upstream atom: {name}")
        raise AttributeError(name)


@pytest.fixture
def profile_session() -> Session:
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
            entities.CategoryProject(
                project_id="project-ac", name="AC project", category_code="AC"
            ),
            _source_batch("batch-tv", "project-tv", "TV"),
            _source_batch("batch-ac", "project-ac", "AC"),
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _context(category_code: str = "TV") -> AnalystContext:
    suffix = category_code.lower()
    return AnalystContext(
        project_id=f"project-{suffix}",
        category_code=category_code,
        batch_id=f"batch-{suffix}",
        product_category=category_code,
    )


def _business_bundle(version_id: str, profile_version: str) -> SellpointValueDraftBundle:
    bundle = _bundle(version_id, profile_version=profile_version)
    profile = bundle.profile.model_copy(
        update={
            "investment_decisions_json": [
                {
                    "capability_code": "local_dimming",
                    "capability_name_cn": "分区控光",
                    "classification": "retain",
                    "business_reason_cn": "用户已感知到暗场层次改善，且价格表现不弱。",
                    "boundary_cn": "结论来自同市场产品表现比较。",
                    "confidence": 0.84,
                    "review_status": "auto_pass",
                },
                {
                    "capability_code": "hdmi_21",
                    "capability_name_cn": "HDMI 2.1",
                    "classification": "table_stake",
                    "business_reason_cn": "同档产品已普及，保留即可。",
                    "boundary_cn": "不把普及配置解释成溢价来源。",
                    "confidence": 0.91,
                    "review_status": "auto_pass",
                },
            ],
            "pm_decisions_json": {
                "investments_to_retain": ["分区控光"],
                "investments_not_converted": ["AI 画质"],
                "configurations_not_to_follow": ["超薄艺术外观"],
                "missing_competitive_gaps": ["高亮客厅画质表达"],
                "table_stakes_to_maintain": ["HDMI 2.1"],
                "current_price_support_cn": "当前均价高于多数同预算产品，但画质兑现和销量共同提供了支撑。",
                "growth_action_cn": "若优先追求销量，应先调整价格位置，再强化高亮与控光的用户表达。",
            },
        }
    )
    candidates = []
    for candidate in bundle.candidates:
        market = dict(candidate.market_summary_json)
        market["avg_weekly_sales_volume"] = 38.0
        candidates.append(candidate.model_copy(update={"market_summary_json": market}))
    value = bundle.value_items[0].model_copy(
        update={
            "capability_codes_json": ["local_dimming", "hdmi_21"],
            "question_result_refs_json": [
                {
                    "question": "relative_highlight",
                    "eligible_candidate_sku_codes": ["TV-COMPETITOR"],
                },
                {
                    "question": "without_value_baseline",
                    "eligible_candidate_sku_codes": ["TV-REFERENCE"],
                },
            ],
            "price_realization_json": {
                "status": "available",
                "current_price": 5000,
            },
            "volume_realization_json": {
                "status": "available",
                "raw_market_position": {"avg_weekly_sales_volume": 42.0},
            },
        }
    )
    return SellpointValueDraftBundle(
        profile=profile,
        candidates=candidates,
        value_items=[value],
    )


def _write_profile(
    repository: SellpointValueProfileRepository,
    *,
    profile_version: str,
    publish: bool,
) -> None:
    version = repository.create_version(_version_payload(profile_version))
    repository.write_draft(
        _business_bundle(version.sellpoint_value_profile_version_id, profile_version)
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


def test_v5_requires_published_profile_unless_preview_is_explicit(
    profile_session: Session,
) -> None:
    repository = _repository(profile_session)
    _write_profile(repository, profile_version="spv-draft", publish=False)
    handlers = _NoUpstreamHandlers()
    orchestrator = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    )

    default = orchestrator.sellpoint_value_pm_v5(
        _context(), sku_code="TV001", enable_v5=True
    )
    preview = orchestrator.sellpoint_value_pm_v5(
        _context(),
        sku_code="TV001",
        enable_v5=True,
        preview_profile_version="spv-draft",
    )

    assert default["status"] == "not_found"
    assert "不会临时重算" in default["limitations"][0]
    assert preview["status"] == "ok"
    assert preview["result"]["sellpoint_value_pm_v5"]["release_status"] == "draft"
    assert handlers.call_count == 0


def test_published_profile_drives_all_report_formats_with_one_hash(
    profile_session: Session,
) -> None:
    repository = _repository(profile_session)
    _write_profile(repository, profile_version="spv-published", publish=True)
    handlers = _NoUpstreamHandlers()
    result = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    ).sellpoint_value_pm_v5(
        _context(),
        model_name="65E7Q",
        enable_v5=True,
        selection_compare_url="https://example.com/compare",
        evidence_report_url="https://example.com/evidence",
    )

    assert result["status"] == "ok"
    payload = result["result"]
    report = payload["sellpoint_value_pm_v5"]
    answer = payload["sellpoint_value_pm_v5_answer"]
    assert report["profile_version"] == "spv-published"
    assert report["generated_at"]
    assert report["published_at"]
    assert report["candidate_manifest_hash"] == "candidate-spv-published"
    assert report["candidate_count"] == 1
    assert report["reference_count"] == 1
    assert len(report["first_screen"]) == 5
    assert report["profile_result_hash"] == answer["result_hash"]
    assert answer["report_ref"]["result_hash"] == answer["result_hash"]
    assert answer["feishu_card_payload"]["result_hash"] == answer["result_hash"]
    assert answer["result_hash"] in answer["short_answer"]
    assert report["candidate_manifest_hash"] in answer["short_answer"]
    assert "发布时间" in answer["short_answer"]
    assert answer["result_hash"] in json.dumps(
        answer["feishu_card_payload"], ensure_ascii=False
    )
    assert answer["feishu_card_payload"]["release_status"] == "published"
    assert (
        answer["feishu_card_payload"]["candidate_manifest_hash"]
        == report["candidate_manifest_hash"]
    )
    assert [item["label"] for item in answer["report_links"]] == [
        "查看用户选择对比",
        "查看完整画像",
    ]
    rendered = json.dumps(payload, ensure_ascii=False)
    for forbidden in ("反事实", "合成对照", "合成控制", "门禁", "M12", "M13", "M14"):
        assert forbidden not in rendered
    assert "HDMI 2.1：保持基础竞争能力" in rendered
    assert "TCL 65Q9L PRO" in rendered
    assert handlers.call_count == 0


def test_stale_blocked_preview_is_honest_and_does_not_recompute(
    profile_session: Session,
) -> None:
    repository = _repository(profile_session)
    version = repository.create_version(_version_payload("spv-stale"))
    bundle = _business_bundle(
        version.sellpoint_value_profile_version_id, "spv-stale"
    )
    profile = bundle.profile.model_copy(
        update={
            "analysis_state": "blocked",
            "freshness_status": "stale",
            "review_required": True,
            "review_status": "review_required",
            "limitations_json": ["竞品证据冲突，需要复核。"],
        }
    )
    repository.write_draft(bundle.model_copy(update={"profile": profile}))
    handlers = _NoUpstreamHandlers()
    result = SopOrchestrators(
        handlers,  # type: ignore[arg-type]
        sellpoint_value_profile_repository=repository,
    ).sellpoint_value_pm_v5(
        _context(),
        sku_code="TV001",
        enable_v5=True,
        preview_profile_version="spv-stale",
    )

    assert result["status"] == "ok"
    assert any("不能作为当前产品决策依据" in item for item in result["limitations"])
    assert any("不能形成正式产品取舍" in item for item in result["limitations"])
    assert handlers.call_count == 0


def test_report_adapter_supports_ac_profile_without_tv_language(
    profile_session: Session,
) -> None:
    repository = SellpointValueProfileRepository(
        _repository(
            profile_session,
            project_id="project-ac",
            category_code=Core3CategoryCode.AC,
        ).context
    )
    version = repository.create_version(
        _version_payload(
            "spv-ac",
            project_id="project-ac",
            category_code="AC",
            batch_id="batch-ac",
        )
    )
    tv = _business_bundle(version.sellpoint_value_profile_version_id, "spv-ac")
    common = {
        "project_id": "project-ac",
        "category_code": "AC",
        "batch_id": "batch-ac",
        "product_category": "AC",
    }
    profile_payload = {**tv.profile.model_dump(mode="python"), **common}
    profile_payload.update(
        {
            "sku_code": "AC001",
            "model_name": "KFR-72LW",
            "brand_name": "海信",
            "display_name_cn": "海信 KFR-72LW",
        }
    )
    candidate_rows = []
    for index, row in enumerate(tv.candidates):
        payload = {**row.model_dump(mode="python"), **common}
        payload.update(
            {
                "target_sku_code": "AC001",
                "candidate_sku_code": f"AC-CANDIDATE-{index}",
            }
        )
        candidate_rows.append(SkuSellpointValueCandidateDraft.model_validate(payload))
    item_payload = {**tv.value_items[0].model_dump(mode="python"), **common}
    item_payload.update(
        {
            "sku_code": "AC001",
            "battlefield_code": "BF_AC_COMFORT",
            "battlefield_name_cn": "舒适送风",
            "value_bundle_code": "comfort_air",
            "value_bundle_name_cn": "无风感舒适",
            "normalized_bundle_code": "comfort_air",
            "perceived_outcome_cn": "制冷时不直吹，夜间体感更舒适",
            "question_result_refs_json": [],
        }
    )
    repository.write_draft(
        SellpointValueDraftBundle(
            profile=SkuSellpointValueProfileDraft.model_validate(profile_payload),
            candidates=candidate_rows,
            value_items=[SkuSellpointValueItemDraft.model_validate(item_payload)],
        )
    )
    bundle = repository.get_profile(
        batch_id="batch-ac",
        profile_version="spv-ac",
        sku_code="AC001",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    )

    assert bundle is not None
    report = build_stored_profile_pm_report(bundle)
    markdown = render_stored_profile_markdown(report, title="空调用户卖点价值")
    artifacts = build_stored_profile_answer_artifacts(report)
    qa_answer = SellpointValueProfileQaService(repository).answer(
        batch_id="batch-ac",
        sku_code="AC001",
        profile_version="spv-ac",
        question="哪些投入值得保留",
    )
    assert report.target["product_category"] == "AC"
    assert "舒适送风" in markdown
    assert "不直吹" in markdown
    assert artifacts["result_hash"] == report.profile_result_hash
    assert qa_answer is not None
    assert qa_answer.category_code == "AC"
    assert qa_answer.answer_status == "answered"
