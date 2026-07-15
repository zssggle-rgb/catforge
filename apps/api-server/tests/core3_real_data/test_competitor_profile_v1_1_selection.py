from __future__ import annotations

import gzip
import inspect
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
    COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
    COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION,
    CandidateScopeClassifier,
    PairGateEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    PRIMARY_DIMENSION_WEIGHTS,
    PRIMARY_SCORE_DIMENSIONS,
    DimensionScore,
    ReviewItem,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    CompetitorProfileV11Selector,
    CompetitorSelectionInputError,
    LegacyTopCompetitorReference,
    PairSelectionInput,
)
from app.services.core3_real_data.hash_utils import stable_hash
from tests.core3_real_data.test_competitor_profile_v1_1_gate_evaluation import (
    _legacy_relations,
    _scope,
    _with_only_market_or_configuration,
)
from tests.core3_real_data.test_competitor_profile_v1_1_pair_analysis import (
    _assemble,
    _source,
)


def _pair(
    category: str = "TV",
    *,
    mode: str | None = None,
    candidate_m12d: str = "complete",
) -> PairSelectionInput:
    source = _source(category, candidate_m12d=candidate_m12d)
    _, assembly = _assemble(source)
    if mode is not None:
        assembly = _with_only_market_or_configuration(assembly, mode)
    gate = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )
    return PairSelectionInput(assembly=assembly, gate_evaluation=gate)


def _clone_pair(
    value: PairSelectionInput,
    sku_code: str,
    *,
    recall_rank: int,
) -> PairSelectionInput:
    assert value.assembly is not None
    assembly = value.assembly.model_copy(
        update={
            "candidate_sku_code": sku_code,
            "candidate_snapshot_ref": f"snapshot:{sku_code}",
            "recall_rank": recall_rank,
            "result_hash": "pending-clone-assembly-hash",
        }
    )
    assembly = _rehash_assembly(assembly)
    scope = value.gate_evaluation.scope.model_copy(
        update={
            "candidate_sku_code": sku_code,
            "candidate_snapshot_ref": f"snapshot:{sku_code}",
            "result_hash": "pending-clone-scope-hash",
        }
    )
    scope = _rehash_scope(scope)
    gate = value.gate_evaluation.model_copy(
        update={
            "candidate_sku_code": sku_code,
            "scope": scope,
            "input_fingerprint": "pending-clone-gate-input",
            "result_hash": "pending-clone-gate-result",
        }
    )
    gate = _rehash_gate(gate, assembly)
    return PairSelectionInput(assembly=assembly, gate_evaluation=gate)


def _rehash_assembly(assembly):
    payload = assembly.model_dump(mode="json", exclude={"result_hash"})
    return assembly.model_copy(
        update={
            "result_hash": stable_hash(
                {
                    "assembler_method_version": PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
                    **payload,
                },
                version=PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
            )
        }
    )


def _rehash_scope(scope):
    payload = {
        "project_id": scope.project_id,
        "category_code": str(scope.category_code),
        "competitor_profile_version_id": scope.competitor_profile_version_id,
        "release_scope_key": scope.release_scope_key,
        "target_sku_code": scope.target_sku_code,
        "candidate_sku_code": scope.candidate_sku_code,
        "target_snapshot_ref": scope.target_snapshot_ref,
        "candidate_snapshot_ref": scope.candidate_snapshot_ref,
        "scope_status": str(scope.scope_status),
        "exclusion_reason_code": scope.exclusion_reason_code,
        "review_items": [row.model_dump(mode="json") for row in scope.review_items],
        "input_fingerprint": scope.input_fingerprint,
    }
    return scope.model_copy(
        update={
            "result_hash": stable_hash(
                payload,
                version="competitor_profile_v1_1_scope_result_v1",
            )
        }
    )


def _rehash_gate(gate, assembly):
    relation_hashes = {
        str(row.relation_code): gate.relation_source_hashes[str(row.relation_code)]
        for row in gate.relation_assessments
    }
    input_fingerprint = stable_hash(
        {
            "scope_result_hash": gate.scope.result_hash,
            "assembly_result_hash": assembly.result_hash,
            "relation_source_hashes": relation_hashes,
            "relation_calculator_method_version": (
                COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION
            ),
            "method_version": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
            "config_version": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
        },
        version="competitor_profile_v1_1_gate_input_v1",
    )
    result_hash = stable_hash(
        {
            "input_fingerprint": input_fingerprint,
            "dimension_hashes": {
                str(row.dimension_code): row.source_result_hash
                for row in gate.dimension_states
            },
            "relation_hashes": {
                str(row.relation_code): row.result_hash
                for row in gate.relation_assessments
            },
            "question_hashes": {
                str(row.question_code): row.result_hash
                for row in gate.business_questions
            },
            "review_items": [row.model_dump(mode="json") for row in gate.review_items],
        },
        version="competitor_profile_v1_1_gate_result_v1",
    )
    return gate.model_copy(
        update={
            "input_fingerprint": input_fingerprint,
            "result_hash": result_hash,
        }
    )


def _set_question_strength(
    value: PairSelectionInput,
    strength: str,
) -> PairSelectionInput:
    assert value.assembly is not None
    questions = []
    for row in value.gate_evaluation.business_questions:
        if row.answerable and str(row.question_code) != "key_competitor_selection":
            conclusion = row.conclusion.model_copy(update={"strength": strength})
            row = row.model_copy(
                update={
                    "conclusion_strength": strength,
                    "conclusion": conclusion,
                    "result_hash": stable_hash(
                        {
                            "question_code": str(row.question_code),
                            "strength": strength,
                            "candidate": value.gate_evaluation.candidate_sku_code,
                        },
                        version="g35-question-strength-fixture-v1",
                    ),
                }
            )
        questions.append(row)
    gate = value.gate_evaluation.model_copy(
        update={
            "business_questions": questions,
            "result_hash": "pending-question-strength-gate",
        }
    )
    gate = _rehash_gate(gate, value.assembly)
    return PairSelectionInput(assembly=value.assembly, gate_evaluation=gate)


def _set_purchase_pool_score(
    value: PairSelectionInput,
    score_value: Decimal,
) -> PairSelectionInput:
    assert value.assembly is not None
    weight = PRIMARY_DIMENSION_WEIGHTS["purchase_pool"]
    score = DimensionScore(
        configured_weight=weight,
        raw_score=score_value,
        available_weight=weight,
        normalized_score=score_value,
        weighted_contribution=score_value * weight,
    )
    pool = value.assembly.purchase_pool.model_copy(
        update={
            "score": score,
            "result_hash": stable_hash(
                str(score_value),
                version="g35-purchase-pool-score-fixture-v1",
            ),
        }
    )
    assembly = _rehash_assembly(
        value.assembly.model_copy(
            update={"purchase_pool": pool, "result_hash": "pending-score-assembly"}
        )
    )
    states = [
        row.model_copy(update={"source_result_hash": pool.result_hash})
        if str(row.dimension_code) == "purchase_pool"
        else row
        for row in value.gate_evaluation.dimension_states
    ]
    gate = _rehash_gate(
        value.gate_evaluation.model_copy(
            update={
                "dimension_states": states,
                "result_hash": "pending-score-gate",
            }
        ),
        assembly,
    )
    return PairSelectionInput(assembly=assembly, gate_evaluation=gate)


def _excluded_pair() -> PairSelectionInput:
    source = _source()
    scope = CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=None,
        authoritative_manifest_sku_codes=[],
        candidate_identity_token="broken-candidate-token",
    )
    gate = PairGateEvaluator().evaluate(
        scope=scope,
        project_id=source.target_snapshot.project_id,
        category_code=source.target_snapshot.category_code,
        competitor_profile_version_id=(
            source.target_snapshot.competitor_profile_version_id
        ),
        release_scope_key=source.target_snapshot.release_scope_key,
    )
    return PairSelectionInput(gate_evaluation=gate)


def _pair_with_local_review_or_conflict(case: str) -> PairSelectionInput:
    source = _source()
    _, assembly = _assemble(source)
    if case == "m05c_review":
        field_name = "user_realization_comparison"
        original = getattr(assembly.dimensions, field_name)
        review_item = ReviewItem(
            review_code="g35_m05c_local_review",
            dimension_code=field_name,
            reason_cn="M05C 用户兑现维度需要局部复核。",
            evidence_refs=original.evidence_refs,
        )
        changed = original.model_copy(
            update={
                "review_required": True,
                "review_items": [review_item],
                "result_hash": "g35-m05c-local-review",
            }
        )
    else:
        field_name = "battlefield_overlap"
        original = getattr(assembly.dimensions, field_name)
        review_item = ReviewItem(
            review_code="g35_battlefield_local_conflict",
            dimension_code=field_name,
            reason_cn="价值战场维度存在局部冲突。",
            evidence_refs=original.evidence_refs,
        )
        changed = original.model_copy(
            update={
                "availability": "conflict",
                "score": DimensionScore(
                    configured_weight=PRIMARY_DIMENSION_WEIGHTS[field_name],
                    raw_score=None,
                    available_weight=Decimal("0"),
                    normalized_score=None,
                    weighted_contribution=Decimal("0"),
                ),
                "conclusion_strength": "unknown",
                "conclusion": original.conclusion.model_copy(
                    update={"strength": "unknown", "direction": "unknown"}
                ),
                "review_required": True,
                "review_items": [review_item],
                "result_hash": "g35-battlefield-local-conflict",
            }
        )
    assembly = _rehash_assembly(
        assembly.model_copy(
            update={
                "dimensions": assembly.dimensions.model_copy(
                    update={field_name: changed}
                ),
                "result_hash": f"pending-{case}-assembly",
            }
        )
    )
    gate = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )
    return PairSelectionInput(assembly=assembly, gate_evaluation=gate)


def test_score_breakdown_uses_frozen_six_dimension_formula() -> None:
    pair = _pair()
    result = CompetitorProfileV11Selector().select([pair])
    decision = result.pair_decisions[0]
    assert decision.score_breakdown is not None
    score = decision.score_breakdown

    assert tuple(row.dimension_code for row in score.components) == (
        PRIMARY_SCORE_DIMENSIONS
    )
    assert score.raw_total == sum(
        (row.weighted_contribution for row in score.components), Decimal("0")
    )
    assert score.available_weight == sum(
        (
            row.weight
            for row in score.components
            if str(row.availability) not in {"unknown", "conflict"}
        ),
        Decimal("0"),
    )
    assert score.normalized_total == score.raw_total / score.available_weight
    assert score.ranking_score == score.normalized_total
    assert result.score_policy.coverage_minimum_gate is None


def test_question_strength_precedes_higher_normalized_score() -> None:
    base = _pair()
    strong = _set_question_strength(
        _clone_pair(_pair(mode="market"), "TV000010", recall_rank=2),
        "strong",
    )
    reference = _set_question_strength(
        _clone_pair(base, "TV000011", recall_rank=1),
        "reference",
    )

    result = CompetitorProfileV11Selector().select([reference, strong])

    assert result.priority_competitors[0].candidate_sku_code == "TV000010"
    assert result.priority_competitors[0].selection_score == Decimal("0")
    scores = {
        row.candidate_sku_code: row.score_breakdown.ranking_score
        for row in result.pair_decisions
        if row.score_breakdown
    }
    assert scores["TV000011"] is not None
    assert scores["TV000010"] is None


def test_role_diversity_keeps_market_and_configuration_only_candidates() -> None:
    full = _set_question_strength(
        _clone_pair(_pair(), "TV000020", recall_rank=1), "supported"
    )
    duplicate = _set_question_strength(
        _clone_pair(_pair(), "TV000021", recall_rank=2), "supported"
    )
    market = _set_question_strength(
        _clone_pair(_pair(mode="market"), "TV000022", recall_rank=4), "reference"
    )
    configuration = _set_question_strength(
        _clone_pair(_pair(mode="configuration"), "TV000023", recall_rank=3),
        "reference",
    )

    result = CompetitorProfileV11Selector().select(
        [duplicate, market, full, configuration]
    )

    selected = [row.candidate_sku_code for row in result.priority_competitors]
    assert selected[0] == "TV000020"
    assert set(selected[1:]) == {"TV000022", "TV000023"}
    assert result.selected_count == 3
    assert len(result.pair_decisions) == 4
    assert {
        row.selection_reason_code for row in result.pair_decisions if not row.selected
    } == {"stronger_candidate_covers_same_decision_role"}


@pytest.mark.parametrize("category", ["TV", "AC"])
@pytest.mark.parametrize(
    "candidate_m12d", ["complete", "partial", "missing", "conflict"]
)
def test_tv_ac_partial_missing_conflict_still_enter_selection_process(
    category: str,
    candidate_m12d: str,
) -> None:
    pair = _pair(category, candidate_m12d=candidate_m12d)

    result = CompetitorProfileV11Selector().select([pair])
    decision = result.pair_decisions[0]

    assert result.analysis_candidate_count == 1
    assert decision.scope_status == "analyzable"
    assert decision.score_breakdown is not None
    assert decision.selection_reason_code != "scope_excluded"


@pytest.mark.parametrize("case", ["m05c_review", "battlefield_conflict"])
def test_g28_local_review_or_conflict_does_not_remove_candidate(case: str) -> None:
    result = CompetitorProfileV11Selector().select(
        [_pair_with_local_review_or_conflict(case)]
    )
    decision = result.pair_decisions[0]

    assert result.analysis_candidate_count == 1
    assert decision.scope_status == "analyzable"
    assert decision.score_breakdown is not None
    assert decision.review_required is True


def test_hard_excluded_candidate_is_preserved_but_not_scored() -> None:
    result = CompetitorProfileV11Selector().select([_excluded_pair()])
    decision = result.pair_decisions[0]

    assert result.analysis_candidate_count == 0
    assert result.selected_count == 0
    assert decision.scope_status == "excluded"
    assert decision.score_breakdown is None
    assert decision.selection_reason_code == "scope_excluded_identity_decode_failed"


def test_legacy_top3_all_participate_and_machine_diff_is_complete() -> None:
    base = _pair()
    pairs = [
        _clone_pair(base, "TV000030", recall_rank=1),
        _clone_pair(base, "TV000031", recall_rank=2),
        _clone_pair(_pair(mode="configuration"), "TV000032", recall_rank=3),
        _clone_pair(_pair(mode="market"), "TV000033", recall_rank=4),
    ]
    legacy = [
        LegacyTopCompetitorReference(
            candidate_sku_code=f"TV00003{index}",
            legacy_rank=index + 1,
            legacy_role=f"legacy-role-{index + 1}",
        )
        for index in range(3)
    ]

    result = CompetitorProfileV11Selector().select(pairs, legacy_top3=legacy)

    by_sku = {row.candidate_sku_code: row for row in result.pair_decisions}
    assert all(by_sku[row.candidate_sku_code].legacy_rank for row in legacy)
    assert {row.candidate_sku_code for row in result.legacy_selection_diffs} == {
        *[row.candidate_sku_code for row in legacy],
        *[row.candidate_sku_code for row in result.priority_competitors],
    }
    assert {row.diff_status for row in result.legacy_selection_diffs} <= {
        "retained",
        "added",
        "dropped",
    }


def test_65e7q_all_legacy_candidates_enter_one_untruncated_selection_universe() -> None:
    fixture_path = (
        Path(__file__).parents[4]
        / "docs/core3_mvp/real_data_v2/current_implementation/competitor_profile_v1"
        / "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz"
    )
    with gzip.open(fixture_path, "rt", encoding="utf-8") as handle:
        fixture = json.load(handle)
    candidate_codes = [
        row["candidate"]["sku_code"]
        for row in fixture["legacy_analysis"]["all_candidates"]
    ]
    legacy_top3 = [
        LegacyTopCompetitorReference(
            candidate_sku_code=row["candidate"]["sku_code"],
            legacy_rank=rank,
            legacy_role=row.get("role") or row.get("primary_role"),
        )
        for rank, row in enumerate(
            fixture["legacy_analysis"]["top_competitors"], start=1
        )
    ]
    base = _pair()
    pairs = [
        _clone_pair(base, sku_code, recall_rank=rank)
        for rank, sku_code in enumerate(candidate_codes, start=1)
    ]

    result = CompetitorProfileV11Selector().select(
        pairs,
        legacy_top3=legacy_top3,
    )

    assert len(result.pair_decisions) == len(candidate_codes) == 20
    assert {row.candidate_sku_code for row in result.pair_decisions} == set(
        candidate_codes
    )
    assert result.analysis_candidate_count == 20
    assert result.selected_count == 3
    assert all(
        next(
            row
            for row in result.pair_decisions
            if row.candidate_sku_code == legacy.candidate_sku_code
        ).legacy_rank
        == legacy.legacy_rank
        for legacy in legacy_top3
    )


def test_missing_legacy_top3_candidate_fails_closed() -> None:
    with pytest.raises(CompetitorSelectionInputError, match="must participate"):
        CompetitorProfileV11Selector().select(
            [_pair()],
            legacy_top3=[
                LegacyTopCompetitorReference(
                    candidate_sku_code="TV-NOT-IN-UNIVERSE",
                    legacy_rank=1,
                )
            ],
        )


def test_selection_is_deterministic_and_input_order_independent() -> None:
    base = _pair()
    pairs = [
        _clone_pair(base, "TV000040", recall_rank=2),
        _clone_pair(base, "TV000041", recall_rank=1),
        _clone_pair(_pair(mode="market"), "TV000042", recall_rank=3),
    ]
    selector = CompetitorProfileV11Selector()

    first = selector.select(pairs)
    second = selector.select(list(reversed(pairs)))

    assert first == second
    assert first.result_hash == second.result_hash


def test_equal_strength_and_score_use_recall_rank_then_sku_code() -> None:
    base = _pair()
    pairs = [
        _set_question_strength(
            _clone_pair(base, "TV000052", recall_rank=2), "supported"
        ),
        _set_question_strength(
            _clone_pair(base, "TV000051", recall_rank=1), "supported"
        ),
        _set_question_strength(
            _clone_pair(base, "TV000050", recall_rank=1), "supported"
        ),
    ]

    result = CompetitorProfileV11Selector().select(pairs)

    assert [row.candidate_sku_code for row in result.priority_competitors] == [
        "TV000050",
        "TV000051",
        "TV000052",
    ]


def test_tampered_g33_or_g34_hash_fails_closed() -> None:
    pair = _pair()
    assert pair.assembly is not None

    with pytest.raises(CompetitorSelectionInputError, match="G33 assembly result hash"):
        CompetitorProfileV11Selector().select(
            [
                PairSelectionInput(
                    assembly=pair.assembly.model_copy(
                        update={"result_hash": "tampered-g33-hash"}
                    ),
                    gate_evaluation=pair.gate_evaluation,
                )
            ]
        )
    with pytest.raises(CompetitorSelectionInputError, match="G34 gate result hash"):
        CompetitorProfileV11Selector().select(
            [
                PairSelectionInput(
                    assembly=pair.assembly,
                    gate_evaluation=pair.gate_evaluation.model_copy(
                        update={"result_hash": "tampered-g34-hash"}
                    ),
                )
            ]
        )


def test_selection_has_no_legacy_global_or_market_overlap_gate() -> None:
    from app.services.core3_real_data.analyst import (
        competitor_profile_v1_1_selection as module,
    )

    source = inspect.getsource(module)
    for forbidden in (
        "candidate_status",
        "relation_evaluation_member",
        "common_week_count",
        "common_platform_count",
        "formal_direct_competitor",
        "coverage_minimum_gate >",
        "top_k",
        "sqlalchemy",
        "Repository",
        "openai",
        "requests.",
    ):
        assert forbidden not in source
