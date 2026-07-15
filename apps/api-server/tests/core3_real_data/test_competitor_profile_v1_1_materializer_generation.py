from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_config import (
    build_production_materialization_config,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure import (
    PriceVolumePressureEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool import (
    PurchasePoolSemanticEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    CandidateScopeClassifier,
    PairGateEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_generation import (
    CompetitorProfileV11GenerationService,
    CompetitorProfileV11GenerationWorkItem,
    CompetitorProfileV11ImmutableDraftError,
    InMemoryCompetitorProfileV11DraftStore,
    RepositoryCompetitorProfileV11DraftStore,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_materializer import (
    CompetitorProfileV11MaterializationError,
    CompetitorProfileV11Materializer,
    HardExcludedPairMaterializationInput,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PairAnalysisAssembler,
    PairAnalysisCalculator,
    PairAnalysisCalculatorInput,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    DimensionScore,
    MachineReadableConclusion,
    ProfileVersionAnalysisContext,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    CompetitorProfileV11Selector,
    CompetitorSelectionInputError,
    LegacyTopCompetitorReference,
    PairSelectionInput,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11IntegrityError,
    _assert_compact_selection,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_snapshot_builder import (
    VersionSkuAnalysisSnapshotBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution import (
    ValueSubstitutionEvidenceEvaluator,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)
from tests.core3_real_data.test_competitor_profile_v1_1_gate_evaluation import (
    _legacy_relations,
    _scope,
)
from tests.core3_real_data.test_competitor_profile_v1_1_pair_analysis import (
    _assemble,
    _source,
)
from tests.core3_real_data.test_competitor_profile_v1_1_schemas import _budget
from tests.core3_real_data.test_competitor_profile_v1_1_selection import (
    _rehash_assembly,
)


def _work_item(category: str = "TV") -> CompetitorProfileV11GenerationWorkItem:
    source = _source(category)
    _, assembly = _assemble(source)
    gate = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )
    selection = CompetitorProfileV11Selector().select(
        [PairSelectionInput(assembly=assembly, gate_evaluation=gate)],
        legacy_top3=[
            LegacyTopCompetitorReference(
                candidate_sku_code=assembly.candidate_sku_code,
                legacy_rank=1,
                legacy_role="direct_competitor",
            )
        ],
    )
    profile_version = ProfileVersionAnalysisContext(
        competitor_profile_version_id=assembly.competitor_profile_version_id,
        project_id=assembly.project_id,
        category_code=category,
        product_category=category,
        release_scope_key=assembly.release_scope_key,
        source_batch_ids=["batch-1"],
        market_window="fixture-window",
        analysis_population="fixture-population",
        score_policy=selection.score_policy,
        performance_storage_budget=_budget(),
    )
    return CompetitorProfileV11GenerationWorkItem(
        profile_version=profile_version,
        target_snapshot=source.target_snapshot,
        candidate_snapshots=[source.candidate_snapshot],
        pair_assemblies=[assembly],
        gate_evaluations=[gate],
        selection_result=selection,
    )


def _profile_context(item: PairSelectionInput) -> ProfileVersionAnalysisContext:
    assert item.assembly is not None
    selection = CompetitorProfileV11Selector().select([item])
    return ProfileVersionAnalysisContext(
        competitor_profile_version_id=item.assembly.competitor_profile_version_id,
        project_id=item.assembly.project_id,
        category_code=item.assembly.category_code,
        product_category=item.assembly.category_code,
        release_scope_key=item.assembly.release_scope_key,
        source_batch_ids=["batch-1"],
        market_window="fixture-window",
        analysis_population="fixture-population",
        score_policy=selection.score_policy,
        performance_storage_budget=_budget(),
    )


def _unknown_conclusion(code: str, subject: str) -> MachineReadableConclusion:
    return MachineReadableConclusion(
        conclusion_code=f"fixture_unknown_{code}",
        subject=subject,
        direction="unknown",
        strength="unknown",
        limitations=[f"{code}_fixture_unknown"],
        audit_summary_cn=f"{code} 在该测试中无可用事实。",
    )


def _valid_market_only_assembly(base):
    subject = base.candidate_sku_code
    dimension_updates = {}
    for code in (
        "battlefield_overlap",
        "user_task_overlap",
        "target_group_overlap",
        "parameter_comparison",
        "claim_comparison",
        "user_realization_comparison",
        "purchase_reason_comparison",
    ):
        row = getattr(base.dimensions, code)
        dimension_updates[code] = row.__class__.model_validate(
            {
                **row.model_dump(mode="json"),
                "availability": "unknown",
                "score": DimensionScore(
                    configured_weight=row.score.configured_weight,
                    raw_score=None,
                    available_weight=0,
                    normalized_score=None,
                    weighted_contribution=0,
                ).model_dump(mode="json"),
                "conclusion_strength": "unknown",
                "conclusion": _unknown_conclusion(code, subject).model_dump(
                    mode="json"
                ),
                "review_required": False,
                "review_items": [],
                "limitations": [f"{code}_fixture_unknown"],
                "result_hash": f"{code}-fixture-unknown-hash",
            }
        )
    first_gate, *remaining_gates = base.purchase_pool.gate_facts
    unknown_gate = first_gate.model_copy(
        update={
            "known": False,
            "passed": None,
            "facts": {},
            "reason_code": "fixture_unknown",
        }
    )
    pool = base.purchase_pool.__class__.model_validate(
        {
            **base.purchase_pool.model_dump(mode="json"),
            "level": "unknown",
            "gate_facts": [
                unknown_gate.model_dump(mode="json"),
                *[row.model_dump(mode="json") for row in remaining_gates],
            ],
            "score": DimensionScore(
                configured_weight=base.purchase_pool.score.configured_weight,
                raw_score=None,
                available_weight=0,
                normalized_score=None,
                weighted_contribution=0,
            ).model_dump(mode="json"),
            "conclusion": _unknown_conclusion("purchase_pool", subject).model_dump(
                mode="json"
            ),
            "result_hash": "market-only-purchase-pool-unknown",
        }
    )
    anchor = base.value_anchor_analysis.__class__.model_validate(
        {
            **base.value_anchor_analysis.model_dump(mode="json"),
            "anchor_substitutability_score": None,
            "anchor_substitutability_level": "unknown",
            "score": DimensionScore(
                configured_weight=base.value_anchor_analysis.score.configured_weight,
                raw_score=None,
                available_weight=0,
                normalized_score=None,
                weighted_contribution=0,
            ).model_dump(mode="json"),
            "conclusion_strength": "unknown",
            "conclusion": _unknown_conclusion("value_anchor", subject).model_dump(
                mode="json"
            ),
            "result_hash": "market-only-value-anchor-unknown",
        }
    )
    replacement = base.replacement_pressure_analysis.__class__.model_validate(
        {
            **base.replacement_pressure_analysis.model_dump(mode="json"),
            "primary_pressure_type": "unknown",
            "replacement_pressure_score": None,
            "replacement_pressure_level": "unknown",
            "score": DimensionScore(
                configured_weight=(
                    base.replacement_pressure_analysis.score.configured_weight
                ),
                raw_score=None,
                available_weight=0,
                normalized_score=None,
                weighted_contribution=0,
            ).model_dump(mode="json"),
            "conclusion_strength": "unknown",
            "conclusion": _unknown_conclusion(
                "replacement_pressure", subject
            ).model_dump(mode="json"),
            "result_hash": "market-only-replacement-pressure-unknown",
        }
    )
    dimensions = base.dimensions.__class__.model_validate(
        {
            **base.dimensions.model_dump(mode="json"),
            **{
                code: row.model_dump(mode="json")
                for code, row in dimension_updates.items()
            },
        }
    )
    return _rehash_assembly(
        base.model_copy(
            update={
                "purchase_pool": pool,
                "dimensions": dimensions,
                "value_anchor_analysis": anchor,
                "replacement_pressure_analysis": replacement,
                "result_hash": "pending-market-only-assembly-hash",
            }
        )
    )


def _max_candidate_work_item(
    category: str,
    candidate_count: int,
    *,
    target_sku_code: str | None = None,
    target_brand: str | None = None,
    target_model: str | None = None,
    version_id: str | None = None,
) -> CompetitorProfileV11GenerationWorkItem:
    if category not in {"TV", "AC"}:
        raise ValueError("category must be TV or AC")
    if candidate_count < 1:
        raise ValueError("candidate_count must be positive")
    specs = []
    for number in range(1, candidate_count + 2):
        spec = _default_spec(category, number)
        spec.update(
            {
                "market_pool": f"{category.lower()}-main",
                "task_primary": "cinema",
                "task_secondary": ["gaming"],
                "audience_primary": "family-av",
                "battlefield_primary": "picture",
                "battlefield_secondary": ["smooth"],
                "battlefield_opportunity": ["gaming"],
                "purchase_reasons": ["clear-picture", "dark-detail"],
                "claim_values": ["picture-quality", f"claim-{number}"],
                "price": Decimal("4500") + number * Decimal("100"),
                "weekly_volume": Decimal("50") + number,
            }
        )
        if number == 1:
            if target_sku_code is not None:
                spec["sku_code"] = target_sku_code
            if target_brand is not None:
                spec["brand"] = target_brand
            if target_model is not None:
                spec["model"] = target_model
        specs.append(spec)
    bundle = _category_bundle(category, specs)
    resolved_target_sku_code = str(specs[0]["sku_code"])
    config = build_production_materialization_config(bundle)
    pipeline = CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, resolved_target_sku_code),
        recall_config=config.recall,
        eligibility_config=config.eligibility,
    )
    features = PairFeatureBuilder().build(pipeline)
    pools = PurchasePoolSemanticEvaluator().evaluate(features, config.purchase_pool)
    values = ValueSubstitutionEvidenceEvaluator().evaluate(
        features,
        pools,
        config.value_substitution,
    )
    pressures = PriceVolumePressureEvaluator().evaluate(
        features,
        pools,
        values,
        config.price_volume,
    )
    resolved_version_id = version_id or (
        f"competitor-profile-v11-{category.lower()}-{candidate_count}-test"
    )
    snapshots = {
        row.identity_market.sku_code: row
        for row in VersionSkuAnalysisSnapshotBuilder().build_many(
            bundle,
            competitor_profile_version_id=resolved_version_id,
        )
    }
    feature_by_code = {row.candidate.sku_code: row for row in features.pairs}
    pool_by_code = {row.candidate.sku_code: row for row in pools.pairs}
    value_by_code = {row.candidate.sku_code: row for row in values.pairs}
    pressure_by_code = {row.candidate.sku_code: row for row in pressures.pairs}
    pair_inputs = []
    assemblies = []
    gates = []
    for rank, recalled in enumerate(pipeline.recall_manifest.candidates, start=1):
        code = recalled.candidate.sku_code
        source = PairAnalysisCalculatorInput(
            competitor_profile_version_id=resolved_version_id,
            pair_feature=feature_by_code[code],
            purchase_pool=pool_by_code[code],
            value_substitution=value_by_code[code],
            price_volume_pressure=pressure_by_code[code],
            target_snapshot=snapshots[resolved_target_sku_code],
            candidate_snapshot=snapshots[code],
            recalled_candidate=recalled,
            recall_rank=rank,
        )
        assembly = PairAnalysisAssembler().assemble(
            PairAnalysisCalculator().calculate(source)
        )
        gate = PairGateEvaluator().evaluate(
            scope=_scope(source),
            assembly=assembly,
            legacy_relation_assessments=_legacy_relations(assembly),
        )
        assemblies.append(assembly)
        gates.append(gate)
        pair_inputs.append(
            PairSelectionInput(assembly=assembly, gate_evaluation=gate)
        )
    legacy = [
        LegacyTopCompetitorReference(
            candidate_sku_code=row.assembly.candidate_sku_code,
            legacy_rank=rank,
            legacy_role="direct_competitor",
        )
        for rank, row in enumerate(pair_inputs[:3], start=1)
        if row.assembly is not None
    ]
    selection = CompetitorProfileV11Selector().select(
        pair_inputs,
        legacy_top3=legacy,
    )
    context = ProfileVersionAnalysisContext(
        competitor_profile_version_id=resolved_version_id,
        project_id=bundle.serving_scope.project_id,
        category_code=category,
        product_category=category,
        release_scope_key=bundle.serving_scope.release_scope_key,
        source_batch_ids=["batch-1"],
        market_window="fixture-window",
        analysis_population=f"{category.lower()}-{candidate_count}-candidate-fixture",
        score_policy=selection.score_policy,
        performance_storage_budget=_budget(),
    )
    decision_codes = {
        row.candidate_sku_code
        for row in selection.pair_decisions
        if row.candidate_sku_code is not None
    }
    return CompetitorProfileV11GenerationWorkItem(
        profile_version=context,
        target_snapshot=snapshots[resolved_target_sku_code],
        candidate_snapshots=[
            snapshots[code] for code in sorted(decision_codes)
        ],
        pair_assemblies=assemblies,
        gate_evaluations=gates,
        selection_result=selection,
    )


def _twenty_candidate_65e7q_item() -> CompetitorProfileV11GenerationWorkItem:
    return _max_candidate_work_item(
        "TV",
        20,
        target_sku_code="TV00029112",
        target_brand="海信",
        target_model="65E7Q",
        version_id="competitor-profile-v11-65e7q-g36-test",
    )


@pytest.mark.parametrize("category", ["TV", "AC"])
def test_materializer_preserves_frozen_pair_process_and_selection(category: str) -> None:
    item = _work_item(category)
    materialized = CompetitorProfileV11Materializer().materialize(
        profile_version=item.profile_version,
        target_snapshot=item.target_snapshot,
        candidate_snapshots=item.candidate_snapshots,
        pair_assemblies=item.pair_assemblies,
        gate_evaluations=item.gate_evaluations,
        selection_result=item.selection_result,
    )

    assert materialized.dto.profile_version.category_code == category
    assert len(materialized.dto.pair_analyses) == 1
    pair = materialized.dto.pair_analyses[0]
    assert pair.analysis_process is not None
    assert pair.analysis_process.aligned_features == item.pair_assemblies[0].aligned_features
    assert pair.selection_assessment is not None
    assert pair.selection_assessment.selection_reason_code
    assert materialized.dto.sku_summary.legacy_selection_diffs[0].diff_status == "retained"
    assert materialized.dto.full_pair_index[0].pair_result_hash == pair.result_hash
    assert materialized.dto.fact_index
    assert materialized.dto.evidence_index


def test_single_generation_is_idempotent_and_never_overwrites() -> None:
    item = _work_item()
    service = CompetitorProfileV11GenerationService(
        draft_store=InMemoryCompetitorProfileV11DraftStore()
    )

    first_status, first = service.generate_draft(item)
    second_status, second = service.generate_draft(item)

    assert first_status == "generated"
    assert second_status == "reused"
    assert first.result_hash == second.result_hash

    changed = replace(
        item,
        profile_version=item.profile_version.model_copy(
            update={"market_window": "different-window"}
        ),
    )
    with pytest.raises(CompetitorProfileV11ImmutableDraftError, match="differs"):
        service.generate_draft(changed)


def test_market_only_priority_preserves_null_pair_score_and_zero_selection_score() -> None:
    source = _source()
    _, base = _assemble(source)
    assembly = _valid_market_only_assembly(base)
    gate = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )
    pair_input = PairSelectionInput(assembly=assembly, gate_evaluation=gate)
    selection = CompetitorProfileV11Selector().select([pair_input])
    context = _profile_context(pair_input)

    materialized = CompetitorProfileV11Materializer().materialize(
        profile_version=context,
        target_snapshot=source.target_snapshot,
        candidate_snapshots=[source.candidate_snapshot],
        pair_assemblies=[assembly],
        gate_evaluations=[gate],
        selection_result=selection,
    )

    pair = materialized.dto.pair_analyses[0]
    assert pair.score_breakdown is not None
    assert pair.score_breakdown.ranking_score is None
    assert materialized.dto.priority_selections[0].selection_score == Decimal("0")
    assert materialized.dto.priority_selections[0].selection_available_weight == 0

    saved_selection = materialized.dto.priority_selections[0]
    selection_row = SimpleNamespace(
        selection_score=saved_selection.selection_score,
        selection_available_weight=saved_selection.selection_available_weight,
        selection_conclusion_strength=str(
            saved_selection.selection_conclusion_strength
        ),
        selection_role_codes_json=[str(row) for row in saved_selection.role_codes],
        selection_rank=saved_selection.selection_rank,
        selection_score_breakdown_json=pair.score_breakdown.model_dump(mode="json"),
    )
    pair_header = SimpleNamespace(
        analysis_result_hash=pair.result_hash,
        analysis_score=None,
        analysis_available_weight=Decimal("0"),
        selection_conclusion_strength=str(
            saved_selection.selection_conclusion_strength
        ),
    )
    index_item = materialized.dto.full_pair_index[0].model_dump(mode="json")
    _assert_compact_selection(
        saved_selection.model_dump(mode="json"),
        selection_row,
        pair_header,
        index_item,
    )
    with pytest.raises(CompetitorProfileV11IntegrityError):
        _assert_compact_selection(
            saved_selection.model_dump(mode="json"),
            selection_row,
            SimpleNamespace(
                **{
                    **pair_header.__dict__,
                    "analysis_score": Decimal("0"),
                }
            ),
            index_item,
        )


def test_self_pair_hard_exclusion_is_saved_with_shared_snapshot_and_reason() -> None:
    source = _source()
    target = source.target_snapshot
    scope = CandidateScopeClassifier().classify(
        target_snapshot=target,
        candidate_snapshot=target,
        authoritative_manifest_sku_codes=[target.identity_market.sku_code],
    )
    gate = PairGateEvaluator().evaluate(
        scope=scope,
        project_id=target.project_id,
        category_code=target.category_code,
        competitor_profile_version_id=target.competitor_profile_version_id,
        release_scope_key=target.release_scope_key,
    )
    selection = CompetitorProfileV11Selector().select(
        [PairSelectionInput(gate_evaluation=gate)]
    )
    context = ProfileVersionAnalysisContext(
        competitor_profile_version_id=target.competitor_profile_version_id,
        project_id=target.project_id,
        category_code=target.category_code,
        product_category=target.category_code,
        release_scope_key=target.release_scope_key,
        source_batch_ids=["batch-1"],
        market_window="fixture-window",
        analysis_population="fixture-population",
        score_policy=selection.score_policy,
        performance_storage_budget=_budget(),
    )
    materialized = CompetitorProfileV11Materializer().materialize(
        profile_version=context,
        target_snapshot=target,
        candidate_snapshots=[target],
        pair_assemblies=[],
        gate_evaluations=[gate],
        selection_result=selection,
        hard_excluded_inputs=[
            HardExcludedPairMaterializationInput(
                candidate_sku_code=target.identity_market.sku_code,
                candidate_snapshot_ref=target.snapshot_ref,
                recall_sources=["authoritative_manifest"],
                recall_rank=1,
            )
        ],
    )

    pair = materialized.dto.pair_analyses[0]
    assert pair.scope_status == "excluded"
    assert pair.exclusion_reason_code == "self_pair"
    assert pair.selection_assessment is not None
    assert pair.selection_assessment.selection_reason_code == "scope_excluded_self_pair"
    assert materialized.dto.candidate_snapshots[0] is target
    assert materialized.dto.sku_summary.analyzable_candidate_count == 0
    assert materialized.dto.sku_summary.excluded_candidate_count == 1


def test_batch_isolates_one_failure_and_resumes_from_checkpoint() -> None:
    good = _work_item()
    bad = replace(
        _work_item("AC"),
        candidate_snapshots=[],
    )
    service = CompetitorProfileV11GenerationService(
        draft_store=InMemoryCompetitorProfileV11DraftStore()
    )

    first = service.batch_generate([bad, good])
    assert first.failed_count == 1
    assert first.succeeded_count == 1

    resumed = service.batch_generate([bad, good], checkpoint=first.checkpoint)
    statuses = {row.target_sku_code: row.status for row in resumed.statuses}
    assert statuses[good.target_sku_code] == "skipped"
    assert statuses[bad.target_sku_code] == "failed"


def test_resume_does_not_skip_changed_inputs_for_the_same_version_and_sku() -> None:
    item = _work_item()
    service = CompetitorProfileV11GenerationService(
        draft_store=InMemoryCompetitorProfileV11DraftStore()
    )
    first = service.batch_generate([item])
    changed = replace(
        item,
        profile_version=item.profile_version.model_copy(
            update={"market_window": "changed-after-checkpoint"}
        ),
    )

    resumed = service.batch_generate([changed], checkpoint=first.checkpoint)

    assert resumed.statuses[0].status == "failed"
    assert resumed.statuses[0].error_code == "CompetitorProfileV11ImmutableDraftError"


def test_repository_store_commits_success_and_rolls_back_failure() -> None:
    materialized_item = _work_item()
    dto = CompetitorProfileV11Materializer().materialize(
        profile_version=materialized_item.profile_version,
        target_snapshot=materialized_item.target_snapshot,
        candidate_snapshots=materialized_item.candidate_snapshots,
        pair_assemblies=materialized_item.pair_assemblies,
        gate_evaluations=materialized_item.gate_evaluations,
        selection_result=materialized_item.selection_result,
    ).dto

    class FakeDb:
        commits = 0
        rollbacks = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    class FakeRepository:
        def __init__(self):
            self.db = FakeDb()
            self.fail = False

        def get_profile(self, **_kwargs):
            if self.fail:
                raise RuntimeError("read failure")
            return SimpleNamespace(full=dto)

        def write_draft(self, value):
            if self.fail:
                raise RuntimeError("write failure")
            return value

    repository = FakeRepository()
    store = RepositoryCompetitorProfileV11DraftStore(repository)

    assert store.get_draft(
        competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        target_sku_code=dto.sku_summary.target_sku_code,
    ) == dto
    assert store.write_draft(dto) == dto
    assert repository.db.commits == 2

    repository.fail = True
    with pytest.raises(RuntimeError, match="read failure"):
        store.get_draft(
            competitor_profile_version_id=(
                dto.profile_version.competitor_profile_version_id
            ),
            target_sku_code=dto.sku_summary.target_sku_code,
        )
    assert repository.db.rollbacks == 1


def test_65e7q_complete_twenty_candidate_universe_is_not_truncated() -> None:
    item = _twenty_candidate_65e7q_item()
    materialized = CompetitorProfileV11Materializer().materialize(
        profile_version=item.profile_version,
        target_snapshot=item.target_snapshot,
        candidate_snapshots=item.candidate_snapshots,
        pair_assemblies=item.pair_assemblies,
        gate_evaluations=item.gate_evaluations,
        selection_result=item.selection_result,
    )

    assert item.target_sku_code == "TV00029112"
    assert len(materialized.dto.candidate_snapshots) == 20
    assert len(materialized.dto.pair_analyses) == 20
    assert len(materialized.dto.full_pair_index) == 20
    assert materialized.dto.sku_summary.analysis_candidate_count == 20
    assert len(materialized.dto.priority_selections) <= 3
    assert all(
        row.selection_assessment is not None
        and row.selection_assessment.selection_reason_code
        for row in materialized.dto.pair_analyses
    )


def test_materializer_never_reruns_analysis_gate_or_selection(monkeypatch) -> None:
    item = _work_item()

    def fail(*_args, **_kwargs):
        raise AssertionError("G36 materializer attempted to rerun analysis")

    monkeypatch.setattr(PairAnalysisCalculator, "calculate", fail)
    monkeypatch.setattr(PairGateEvaluator, "evaluate", fail)
    monkeypatch.setattr(CompetitorProfileV11Selector, "select", fail)

    materialized = CompetitorProfileV11Materializer().materialize(
        profile_version=item.profile_version,
        target_snapshot=item.target_snapshot,
        candidate_snapshots=item.candidate_snapshots,
        pair_assemblies=item.pair_assemblies,
        gate_evaluations=item.gate_evaluations,
        selection_result=item.selection_result,
    )

    assert materialized.dto.pair_analyses


def test_materializer_fails_closed_on_mutated_g35_decision_hash() -> None:
    item = _work_item()
    decision = item.selection_result.pair_decisions[0]
    mutated = item.selection_result.model_copy(
        update={
            "pair_decisions": [
                decision.model_copy(
                    update={"selection_reason_cn": "未重算 hash 的篡改内容"}
                )
            ]
        }
    )

    with pytest.raises(CompetitorSelectionInputError, match="hash does not close"):
        CompetitorProfileV11Materializer().materialize(
            profile_version=item.profile_version,
            target_snapshot=item.target_snapshot,
            candidate_snapshots=item.candidate_snapshots,
            pair_assemblies=item.pair_assemblies,
            gate_evaluations=item.gate_evaluations,
            selection_result=mutated,
        )


def test_materializer_fails_closed_on_mutated_g32_snapshot_hash() -> None:
    item = _work_item()
    mutated_target = item.target_snapshot.model_copy(
        update={
            "limitations": sorted(
                [*item.target_snapshot.limitations, "mutated_after_hash"]
            )
        }
    )

    with pytest.raises(
        CompetitorProfileV11MaterializationError,
        match="G32 SKU snapshot hash does not close",
    ):
        CompetitorProfileV11Materializer().materialize(
            profile_version=item.profile_version,
            target_snapshot=mutated_target,
            candidate_snapshots=item.candidate_snapshots,
            pair_assemblies=item.pair_assemblies,
            gate_evaluations=item.gate_evaluations,
            selection_result=item.selection_result,
        )
