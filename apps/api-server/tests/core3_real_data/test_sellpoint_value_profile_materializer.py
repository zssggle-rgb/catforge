from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    CounterfactualCandidate,
    CounterfactualSet,
    SkuPerceivedValueMarketRealizationReport,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_candidate_service import (
    build_candidate_universe_manifest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_lifecycle import (
    ProfileGenerationLock,
    SellpointValueGenerationAlreadyRunningError,
    SellpointValueProfileLifecycleService,
    SellpointValueReadbackHashMismatchError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer import (
    build_profile_input_fingerprint,
    materialize_sellpoint_value_profile,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer_schemas import (
    ProfileSourceLineage,
    REQUIRED_PROFILE_SOURCE_MODULES,
    SellpointValueMaterializationInput,
    SellpointValueVersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueImmutableVersionError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CapabilityCandidateFact,
    CapabilityComparisonScope,
    CapabilityInvestmentInput,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_threshold_config import (
    capability_threshold_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_thresholds import (
    classify_capability_investment,
)
from app.services.core3_real_data.hash_utils import stable_hash
from tests.core3_real_data.test_claim_value_pm_v5_answer import _report
from tests.core3_real_data.test_sellpoint_value_profile_persistence import (
    _create_dependencies,
    _create_profile_tables,
    _engine,
    _repository,
    _source_batch,
)


@pytest.fixture
def session() -> Session:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        _create_profile_tables(connection)
    db = Session(engine, autoflush=False, future=True)
    db.add_all(
        [
            entities.CategoryProject(
                project_id="project-tv",
                name="TV project",
                category_code="TV",
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


def _request(profile_version: str = "spv-v1") -> SellpointValueVersionRequest:
    return SellpointValueVersionRequest(
        project_id="project-tv",
        category_code="TV",
        batch_id="batch-tv",
        profile_version=profile_version,
        method_versions={
            "candidate": "candidate-v1",
            "threshold": "threshold-v1",
            "counterfactual": "counterfactual-v2",
            "amount": "amount-v2",
        },
        source_scope={"modules": list(REQUIRED_PROFILE_SOURCE_MODULES)},
        version_input_fingerprint=stable_hash(
            {"profile_version": profile_version, "scope": "fixture"},
            version="version-input-v1",
        ),
        candidate_universe_fingerprint=stable_hash(
            {"profile_version": profile_version, "candidates": "fixture"},
            version="version-candidate-v1",
        ),
        version_result_hash=stable_hash(
            {"profile_version": profile_version, "contract": "fixture"},
            version="version-result-v1",
        ),
    )


def _source_lineage(
    *,
    status_overrides: dict[str, str] | None = None,
) -> list[ProfileSourceLineage]:
    overrides = status_overrides or {}
    result = []
    for module_code in REQUIRED_PROFILE_SOURCE_MODULES:
        status = overrides.get(module_code, "present")
        result.append(
            ProfileSourceLineage(
                module_code=module_code,
                status=status,
                rule_versions=[f"{module_code.lower()}-rule-v1"],
                result_hashes=[f"{module_code.lower()}-hash-v1"]
                if status == "present"
                else [],
                record_ids=[f"{module_code.lower()}-record-1"]
                if status == "present"
                else [],
                limitations=[]
                if status == "present"
                else [f"{module_code.lower()}_{status}"],
            )
        )
    return result


def _candidate_record(sku_code: str, index: int) -> dict[str, Any]:
    return {
        "candidate_sku_code": f"{sku_code}-C{index}",
        "candidate_brand_name": f"品牌{index}",
        "candidate_model_name": f"型号{index}",
        "same_brand_flag": index == 0,
        "primary_relation_type": "direct_fight",
        "relation_types": ["direct_fight"],
        "recall_sources": ["M07", "M11C"],
        "recall_strength": "strong",
        "recall_priority_score": 0.9,
        "processing_status": "success",
        "review_required": False,
        "pool_result_hash": f"pool-{sku_code}-{index}",
        "component": {
            "component_total_score": 0.82,
            "processing_status": "success",
            "review_required": False,
            "result_hash": f"component-{sku_code}-{index}",
        },
        "roles": [
            {
                "role_code": "direct_fight",
                "role_name_cn": "直接竞争",
                "role_score": 0.8,
                "role_confidence": 0.9,
                "auto_select_eligible": True,
                "review_required": False,
            }
        ],
        "feature": {
            "market_feature": {"price_wavg": 4800 + index * 100},
            "param_feature": {"picture": True},
            "claim_value_overlap": {"picture": 0.8},
            "battlefield_overlap": {"BF_PREMIUM_PICTURE_UPGRADE": 0.8},
            "task_overlap": {"movie": 0.8},
            "audience_overlap": {"family": 0.7},
            "feature_snapshot_hash": f"feature-{sku_code}-{index}",
        },
        "selection": (
            {
                "slot_code": "same_value",
                "slot_name_cn": "重点竞品",
                "selection_rank": index + 1,
                "result_hash": f"selection-{sku_code}-{index}",
            }
            if index < 3
            else None
        ),
    }


def _candidate_manifest(
    sku_code: str,
    *,
    extra_candidate: bool = False,
):
    count = 6 if extra_candidate else 5
    return build_candidate_universe_manifest(
        project_id="project-tv",
        category_code="TV",
        batch_id="batch-tv",
        target_sku_code=sku_code,
        candidate_records=[_candidate_record(sku_code, index) for index in range(count)],
        market_references=[
            {
                "sku_code": f"{sku_code}-REFERENCE",
                "brand_name": "参考品牌",
                "model_name": "参考型号",
                "reference_purposes": ["same_size_market"],
                "price_wavg": 5100,
                "result_hash": f"reference-{sku_code}",
            }
        ],
    )


def _decision(
    sku_code: str,
    capability_code: str,
    *,
    mode: str,
):
    candidate_facts = [
        CapabilityCandidateFact(
            candidate_sku_code=f"{sku_code}-C{index}",
            fact_status=(
                "known_present"
                if (mode == "table_stake" and index < 4)
                or (mode != "table_stake" and index == 0)
                else "known_absent"
            ),
        )
        for index in range(5)
    ]
    payload: dict[str, Any] = {
        "capability_code": capability_code,
        "capability_name_cn": capability_code,
        "target_fact_status": "known_present",
        "target_value": True,
        "candidate_facts": candidate_facts,
        "comparison_scope": CapabilityComparisonScope(
            category_code="TV",
            price_band="premium",
            product_form="television",
            size_relation="same_size",
            candidate_scope_ids=[row.candidate_sku_code for row in candidate_facts],
            scope_hash=f"scope-{sku_code}-{capability_code}",
        ),
    }
    if mode == "retain":
        payload.update(
            user_feedback_status="realized_advantage",
            relative_experience_status="advantage",
            price_support="positive",
        )
    elif mode == "unconverted":
        payload.update(
            investment_level="high",
            user_feedback_status="not_observed",
            relative_experience_status="weaker",
            competitor_experience_stronger=True,
        )
    return classify_capability_investment(
        CapabilityInvestmentInput.model_validate(payload)
    )


def _report_for(
    sku_code: str,
    *,
    price_summary_suffix: str = "",
) -> SkuPerceivedValueMarketRealizationReport:
    report = _report()
    target = report.target.model_copy(
        update={
            "sku_code": sku_code,
            "model_name": f"型号-{sku_code}",
        }
    )
    decision_summary = report.decision_summary.model_copy(
        update={
            "price_summary_cn": (
                report.decision_summary.price_summary_cn + price_summary_suffix
            )
        }
    )
    return report.model_copy(
        update={
            "target": target,
            "decision_summary": decision_summary,
            "result_hash": stable_hash(
                {"sku_code": sku_code, "price_suffix": price_summary_suffix},
                version="fixture-v5-report-v1",
            ),
        }
    )


def _materialization_input(
    request: SellpointValueVersionRequest,
    sku_code: str,
    *,
    variant: str = "v1",
    status_overrides: dict[str, str] | None = None,
) -> SellpointValueMaterializationInput:
    lineage = _source_lineage(status_overrides=status_overrides)
    decisions = [
        _decision(
            sku_code,
            "tv_bright_room_dark_detail",
            mode="unconverted" if variant == "v2" else "retain",
        ),
        _decision(
            sku_code,
            "tv_color_picture_truth",
            mode="table_stake",
        ),
    ]
    return SellpointValueMaterializationInput(
        project_id=request.project_id,
        category_code=request.category_code,
        batch_id=request.batch_id,
        profile_version=request.profile_version,
        target=_report_for(sku_code).target,
        source_lineage=lineage,
        current_source_hashes={
            row.module_code: list(row.result_hashes)
            for row in lineage
            if row.status == "present"
        },
        candidate_universe=_candidate_manifest(
            sku_code,
            extra_candidate=variant == "v2",
        ),
        threshold_config=capability_threshold_config("TV"),
        investment_decisions=decisions,
        v5_report=_report_for(
            sku_code,
            price_summary_suffix="（新版）" if variant == "v2" else "",
        ),
        method_versions=request.method_versions,
    )


class FixtureProvider:
    def __init__(
        self,
        sku_codes: Sequence[str],
        *,
        fail_codes: set[str] | None = None,
    ) -> None:
        self.sku_codes = list(sku_codes)
        self.fail_codes = fail_codes or set()
        self.calls: list[str] = []
        self.variant_by_version: dict[str, str] = {}

    def list_authoritative_sku_codes(
        self,
        request: SellpointValueVersionRequest,
    ) -> Sequence[str]:
        del request
        return self.sku_codes

    def load_materialization_input(
        self,
        request: SellpointValueVersionRequest,
        sku_code: str,
    ) -> SellpointValueMaterializationInput:
        self.calls.append(sku_code)
        if sku_code in self.fail_codes:
            raise RuntimeError("fixture source failure with private detail")
        return _materialization_input(
            request,
            sku_code,
            variant=self.variant_by_version.get(request.profile_version, "v1"),
        )


def _service(
    session: Session,
    provider: FixtureProvider,
    *,
    generation_lock: ProfileGenerationLock | None = None,
) -> SellpointValueProfileLifecycleService:
    return SellpointValueProfileLifecycleService(
        repository=_repository(session),
        input_provider=provider,
        generation_lock=generation_lock,
    )


def test_materializer_builds_one_auditable_profile_and_is_deterministic() -> None:
    request = _request()
    source = _materialization_input(request, "TV001")

    first = materialize_sellpoint_value_profile(
        source,
        sellpoint_value_profile_version_id="version-id",
    )
    second = materialize_sellpoint_value_profile(
        source.model_copy(
            update={
                "source_lineage": list(reversed(source.source_lineage)),
                "investment_decisions": list(reversed(source.investment_decisions)),
            }
        ),
        sellpoint_value_profile_version_id="version-id",
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.profile.input_fingerprint == build_profile_input_fingerprint(source)
    assert first.profile.result_hash == first.persistence_bundle.profile.result_hash
    assert first.profile.analysis_state == "ready"
    assert first.profile.freshness_status == "current"
    assert first.profile.pm_decisions.investments_to_retain == [
        "tv_bright_room_dark_detail"
    ]
    assert first.profile.pm_decisions.table_stakes_to_maintain == [
        "tv_color_picture_truth"
    ]
    assert len(first.profile.value_items) == 1
    assert len(first.persistence_bundle.candidates) == 6
    reference = next(
        row
        for row in first.persistence_bundle.candidates
        if row.pool_type == "reference"
    )
    assert reference.eligible_questions_json == []


def test_materializer_persists_selected_and_rejected_candidates_by_question() -> None:
    request = _request()
    source = _materialization_input(request, "TV001")
    selected_code = "TV001-C0"
    rejected_code = "TV001-C1"
    counterfactual_set = CounterfactualSet(
        bundle_code="picture_bundle",
        question="relative_highlight",
        candidates=[
            CounterfactualCandidate(
                method="direct_sku",
                question="relative_highlight",
                stage="eligible",
                candidate_key="selected",
                candidate_sku_codes=[selected_code],
                provenance="saved_candidate_universe",
                control_dimensions={"budget": "same"},
                eligible_measures=["price", "volume"],
                reject_reasons=[],
                sample_manifest_hash="selected-manifest",
            ),
            CounterfactualCandidate(
                method="same_budget_pool",
                question="relative_highlight",
                stage="rejected",
                candidate_key="rejected",
                candidate_sku_codes=[rejected_code],
                provenance="saved_candidate_universe",
                control_dimensions={"budget": "same"},
                reject_reasons=["用户价值组合不同"],
                sample_manifest_hash="rejected-manifest",
            ),
        ],
        highest_available_method="direct_sku",
        selection_reasons=["用户价值相同且预算接近"],
        degradation_reasons=[],
        set_hash="question-set-hash",
    )
    value_row = source.v5_report.value_account_rows[0].model_copy(
        update={"counterfactual_sets": [counterfactual_set]}
    )
    report = source.v5_report.model_copy(
        update={"value_account_rows": [value_row]}
    )

    materialized = materialize_sellpoint_value_profile(
        source.model_copy(update={"v5_report": report}),
        sellpoint_value_profile_version_id="version-id",
    )

    analysis = materialized.profile.question_analyses[0]
    assert analysis["question_code"] == "value_relative_advantage"
    assert analysis["eligible_candidate_ids"] == [selected_code]
    assert analysis["selected_candidate_ids"] == [selected_code]
    assert analysis["rejected_candidates"] == [
        {
            "candidate_sku_codes": [rejected_code],
            "method": "same_budget_pool",
            "reasons": ["用户价值组合不同"],
        }
    ]
    selected = next(
        row
        for row in materialized.persistence_bundle.candidates
        if row.candidate_sku_code == selected_code
    )
    assert "value_relative_advantage" in selected.eligible_questions_json
    assert selected.selected_questions_json == ["value_relative_advantage"]
    assert selected.selection_reasons_json == {
        "value_relative_advantage": "用户价值相同且预算接近"
    }


def test_input_fingerprint_includes_missing_sources_and_all_method_versions() -> None:
    request = _request()
    complete = _materialization_input(request, "TV001")
    missing = _materialization_input(
        request,
        "TV001",
        status_overrides={"M14": "missing"},
    )

    assert build_profile_input_fingerprint(complete) != build_profile_input_fingerprint(
        missing
    )
    with pytest.raises(ValidationError, match="every required module"):
        SellpointValueMaterializationInput.model_validate(
            {
                **complete.model_dump(mode="python"),
                "source_lineage": complete.source_lineage[:-1],
            }
        )


def test_freshness_and_lineage_gates_degrade_honestly() -> None:
    request = _request()
    source = _materialization_input(request, "TV001")
    stale_hashes = dict(source.current_source_hashes)
    stale_hashes["M07"] = ["new-market-hash"]
    stale = materialize_sellpoint_value_profile(
        source.model_copy(update={"current_source_hashes": stale_hashes}),
        sellpoint_value_profile_version_id="version-id",
    )
    partial_source = _materialization_input(
        request,
        "TV001",
        status_overrides={"M03B": "missing"},
    )
    partial = materialize_sellpoint_value_profile(
        partial_source,
        sellpoint_value_profile_version_id="version-id",
    )
    conflict_source = _materialization_input(
        request,
        "TV001",
        status_overrides={"M07": "conflict"},
    )
    blocked = materialize_sellpoint_value_profile(
        conflict_source,
        sellpoint_value_profile_version_id="version-id",
    )

    assert stale.profile.freshness_status == "stale"
    assert stale.profile.review_required is True
    assert partial.profile.analysis_state == "partial"
    assert "critical_source_missing:M03B" in partial.profile.review_reasons
    assert blocked.profile.analysis_state == "blocked"
    assert blocked.profile.review_required is True


def test_single_generate_is_idempotent_and_readback_hashes_match(
    session: Session,
) -> None:
    provider = FixtureProvider(["TV001"])
    service = _service(session, provider)
    request = _request()

    first = service.generate_draft(request, sku_code="TV001")
    second = service.generate_draft(request, sku_code="TV001")

    assert first.profile.result_hash == second.profile.result_hash
    assert first.persisted.profile.result_hash == first.profile.result_hash
    assert len(service.list_profiles(
        sellpoint_value_profile_version_id=first.persisted.version.sellpoint_value_profile_version_id
    )) == 1
    assert service.get_profile(
        batch_id="batch-tv",
        profile_version="spv-v1",
        sku_code="TV001",
    ) is not None


def test_batch_failure_isolated_then_resume_only_runs_unfinished(
    session: Session,
) -> None:
    provider = FixtureProvider(
        ["TV003", "TV001", "TV002"],
        fail_codes={"TV002"},
    )
    service = _service(session, provider)
    request = _request()

    first = service.batch_generate(request, page_size=2)

    assert first.requested_sku_count == 3
    assert first.generated_count == 2
    assert first.failed_count == 1
    assert first.version.release_quality_status == "blocked"
    assert first.version.processing_status == "completed_with_errors"
    assert first.checkpoint_sku_code == "TV003"
    assert all(
        row.error_message != "fixture source failure with private detail"
        for row in first.statuses
    )
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 2

    provider.calls.clear()
    provider.fail_codes.clear()
    resumed = service.batch_generate(request, resume_unfinished_only=True, page_size=1)

    assert resumed.generated_count == 1
    assert resumed.skipped_count == 2
    assert resumed.failed_count == 0
    assert provider.calls == ["TV002"]
    assert resumed.version.release_quality_status == "ready"
    assert resumed.version.processing_status == "completed"
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 3


def test_batch_without_resume_reuses_all_existing_profiles(session: Session) -> None:
    provider = FixtureProvider(["TV001", "TV002"])
    service = _service(session, provider)
    request = _request()
    service.batch_generate(request)
    provider.calls.clear()

    rerun = service.batch_generate(request, resume_unfinished_only=False)

    assert rerun.reused_count == 2
    assert rerun.generated_count == 0
    assert provider.calls == ["TV001", "TV002"]


def test_changed_input_cannot_overwrite_same_profile_version(
    session: Session,
) -> None:
    provider = FixtureProvider(["TV001"])
    service = _service(session, provider)
    request = _request()
    service.generate_draft(request, sku_code="TV001")
    provider.variant_by_version["spv-v1"] = "v2"

    with pytest.raises(SellpointValueImmutableVersionError):
        service.generate_draft(request, sku_code="TV001")


class DenyGenerationLock:
    @contextmanager
    def acquire(self, key: str) -> Iterator[bool]:
        del key
        yield False


def test_same_version_generation_lock_rejects_concurrent_runner(
    session: Session,
) -> None:
    provider = FixtureProvider(["TV001"])
    service = _service(
        session,
        provider,
        generation_lock=DenyGenerationLock(),
    )

    with pytest.raises(SellpointValueGenerationAlreadyRunningError):
        service.batch_generate(_request())
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 0


def test_readback_hash_mismatch_rolls_back_sku_write(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FixtureProvider(["TV001"])
    service = _service(session, provider)
    original = service.repository.write_draft

    def tampered_write(bundle, **kwargs):
        result = original(bundle, **kwargs)
        return result.model_copy(
            update={
                "profile": result.profile.model_copy(
                    update={"result_hash": "tampered-result-hash"}
                )
            }
        )

    monkeypatch.setattr(service.repository, "write_draft", tampered_write)
    with pytest.raises(SellpointValueReadbackHashMismatchError):
        service.generate_draft(_request(), sku_code="TV001")
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 0


def test_historical_profile_diff_tracks_candidates_investments_and_price(
    session: Session,
) -> None:
    provider = FixtureProvider(["TV001"])
    provider.variant_by_version["spv-v2"] = "v2"
    service = _service(session, provider)
    service.generate_draft(_request("spv-v1"), sku_code="TV001")
    service.generate_draft(_request("spv-v2"), sku_code="TV001")

    diff = service.diff_profiles(
        batch_id="batch-tv",
        sku_code="TV001",
        from_profile_version="spv-v1",
        to_profile_version="spv-v2",
    )
    repeated = service.diff_profiles(
        batch_id="batch-tv",
        sku_code="TV001",
        from_profile_version="spv-v1",
        to_profile_version="spv-v2",
    )

    assert diff == repeated
    assert "competitor:TV001-C5" in diff.candidate_added
    assert diff.investment_classification_changes == [
        {
            "capability_code": "tv_bright_room_dark_detail",
            "from_classification": "retain",
            "to_classification": "unconverted",
        }
    ]
    assert diff.price_role_changed is True
    assert diff.pm_decisions_changed is True
    assert diff.diff_hash


def test_batch_rejects_invalid_page_size(session: Session) -> None:
    service = _service(session, FixtureProvider(["TV001"]))
    with pytest.raises(ValueError, match="page_size"):
        service.batch_generate(_request(), page_size=0)
