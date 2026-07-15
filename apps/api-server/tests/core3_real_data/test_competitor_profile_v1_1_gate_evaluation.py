from __future__ import annotations

import gzip
import inspect
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    GateResult,
    RelationAssessment as LegacyRelationAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    ALL_GATE_DIMENSION_CODES,
    CandidateEligibilityClassifier,
    CandidateScopeClassifier,
    PairGateEvaluator,
    PairGateInputError,
    V11RelationEvidenceCalculator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    ALL_QUESTION_CODES,
    ALL_RELATION_CODES,
    HARD_EXCLUSION_CODES,
    ReviewItem,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationConfig,
)
from app.services.core3_real_data.hash_utils import stable_hash
from tests.core3_real_data.test_competitor_profile_v1_1_pair_analysis import (
    _assemble,
    _source,
)


def _scope(source, *, candidate_snapshot=None, manifest=None, token=None):
    candidate = candidate_snapshot or source.candidate_snapshot
    return CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=candidate,
        authoritative_manifest_sku_codes=(
            manifest
            if manifest is not None
            else [
                source.target_snapshot.identity_market.sku_code,
                candidate.identity_market.sku_code,
            ]
        ),
        candidate_identity_token=token,
    )


def _rehash_assembly(assembly):
    payload = assembly.model_dump(mode="json", exclude={"result_hash"})
    return assembly.model_copy(
        update={
            "result_hash": stable_hash(
                {
                    "assembler_method_version": (
                        PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION
                    ),
                    **payload,
                },
                version=PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
            )
        }
    )


def _legacy_relations(
    assembly,
    *,
    status: str = "passed",
    gate_passed: bool | None = True,
) -> list[LegacyRelationAssessment]:
    rows = []
    for code in ALL_RELATION_CODES:
        gate = GateResult(
            gate_code=f"{code}_fixture_gate",
            required=True,
            known=gate_passed is not None,
            passed=gate_passed,
            reason_code=f"{code}_fixture_gate_result",
            evidence_refs=assembly.evidence_refs,
        )
        driving = status in {"passed", "limited"}
        rows.append(
            LegacyRelationAssessment(
                relation_code=code,
                status=status,
                confidence_level="medium" if driving else "unknown",
                gate_results=[gate],
                supporting_evidence_families=[],
                business_effect={},
                eligible_question_codes=(
                    ["key_competitor_selection"] if driving else []
                ),
                reason_codes=(
                    []
                    if driving
                    else [
                        "upstream_evidence_requires_review"
                        if status == "review_required"
                        else f"{code}_{status}"
                    ]
                ),
                evidence_refs=assembly.evidence_refs,
                limitations=(
                    ["legacy_relation_directional_only"] if status == "limited" else []
                ),
                result_hash=stable_hash(
                    {
                        "relation_code": code,
                        "status": status,
                        "gate_passed": gate_passed,
                    },
                    version="g34_legacy_relation_fixture_v1",
                ),
            )
        )
    return rows


def _relation_config(category: str = "TV") -> CompetitorRelationConfig:
    return CompetitorRelationConfig(
        config_version="g34-v11-relation-calculation-test-v1",
        product_category=category,
        downtrade_min_price_gap_pct=Decimal("0.08"),
        uptrade_min_price_gap_pct=Decimal("0.08"),
        strong_price_gap_pct=Decimal("0.15"),
        strong_volume_ratio=Decimal("1.25"),
        threshold_parameter_codes=sorted(
            ["ac_product_form", "cooling_capacity_segment"]
        ),
        primary_relation_priority=[
            "direct_substitute",
            "same_budget_alternative",
            "downtrade_diversion",
            "uptrade_alternative",
            "same_brand_ladder",
            "scenario_substitute",
            "same_value_substitute",
        ],
    )


def _unknown_dimension(value, code: str):
    return value.model_copy(
        update={
            "availability": "unknown",
            "conclusion_strength": "unknown",
            "conclusion": value.conclusion.model_copy(
                update={"strength": "unknown", "direction": "unknown"}
            ),
            "review_required": False,
            "review_items": [],
            "limitations": [f"{code}_fixture_unknown"],
            "result_hash": f"{code}-fixture-unknown-hash",
        }
    )


def _with_only_market_or_configuration(assembly, mode: str):
    dimensions = assembly.dimensions
    keep = (
        {"claim_comparison", "parameter_comparison", "user_task_overlap"}
        if mode == "configuration"
        else set()
    )
    updates = {
        code: (
            getattr(dimensions, code)
            if code in keep
            else _unknown_dimension(getattr(dimensions, code), code)
        )
        for code in (
            "battlefield_overlap",
            "claim_comparison",
            "parameter_comparison",
            "purchase_reason_comparison",
            "target_group_overlap",
            "user_realization_comparison",
            "user_task_overlap",
        )
    }
    pool = assembly.purchase_pool.model_copy(
        update={
            "level": "unknown",
            "conclusion": assembly.purchase_pool.conclusion.model_copy(
                update={"strength": "unknown", "direction": "unknown"}
            ),
            "result_hash": f"{mode}-only-purchase-pool-unknown",
        }
    )
    anchor = assembly.value_anchor_analysis.model_copy(
        update={
            "anchor_substitutability_score": None,
            "conclusion_strength": "unknown",
            "conclusion": assembly.value_anchor_analysis.conclusion.model_copy(
                update={"strength": "unknown", "direction": "unknown"}
            ),
            "review_required": False,
            "review_items": [],
            "result_hash": f"{mode}-only-value-anchor-unknown",
        }
    )
    replacement = assembly.replacement_pressure_analysis.model_copy(
        update={
            "replacement_pressure_score": None,
            "conclusion_strength": "unknown",
            "conclusion": (
                assembly.replacement_pressure_analysis.conclusion.model_copy(
                    update={"strength": "unknown", "direction": "unknown"}
                )
            ),
            "review_required": False,
            "review_items": [],
            "result_hash": f"{mode}-only-replacement-unknown",
        }
    )
    market = assembly.market_validation
    if mode == "configuration":
        market = market.model_copy(
            update={
                "market_validation_strength": "unknown",
                "conclusion": market.conclusion.model_copy(
                    update={"strength": "unknown", "direction": "unknown"}
                ),
                "result_hash": "configuration-only-market-unknown",
            }
        )
    return _rehash_assembly(
        assembly.model_copy(
            update={
                "purchase_pool": pool,
                "dimensions": dimensions.model_copy(update=updates),
                "value_anchor_analysis": anchor,
                "replacement_pressure_analysis": replacement,
                "market_validation": market,
                "result_hash": f"{mode}-only-assembly-result",
            }
        )
    )


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("identity", "identity_decode_failed"),
        ("self", "self_pair"),
        ("project", "project_mismatch"),
        ("category", "category_mismatch"),
        ("manifest", "candidate_outside_manifest"),
    ],
)
def test_scope_classifier_allows_only_five_hard_exclusions(
    case: str,
    expected: str,
) -> None:
    source = _source()
    candidate = source.candidate_snapshot
    token = candidate.identity_market.sku_code
    manifest = [
        source.target_snapshot.identity_market.sku_code,
        candidate.identity_market.sku_code,
    ]
    if case == "identity":
        candidate = None
        token = "damaged-candidate-token"
    elif case == "self":
        candidate = source.target_snapshot
        token = source.target_snapshot.identity_market.sku_code
    elif case == "project":
        candidate = candidate.model_copy(update={"project_id": "other-project"})
    elif case == "category":
        candidate = candidate.model_copy(update={"category_code": "AC"})
    elif case == "manifest":
        manifest = [source.target_snapshot.identity_market.sku_code]

    assessment = CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=candidate,
        authoritative_manifest_sku_codes=manifest,
        candidate_identity_token=token,
    )

    assert assessment.scope_status == "excluded"
    assert assessment.exclusion_reason_code == expected
    assert expected in HARD_EXCLUSION_CODES
    assert assessment.review_required is False


def test_scope_classifier_compatibility_name_uses_v11_scope_semantics() -> None:
    assert CandidateEligibilityClassifier is CandidateScopeClassifier


def test_authority_taxonomy_lineage_and_conflict_are_review_not_exclusion() -> None:
    source = _source()
    candidate = source.candidate_snapshot.model_copy(
        update={
            "limitations": [
                "authority_missing",
                "battlefield_conflict",
                "lineage_missing",
                "taxonomy_unknown",
            ]
        }
    )

    assessment = _scope(source, candidate_snapshot=candidate)

    assert assessment.scope_status == "analyzable"
    assert assessment.exclusion_reason_code is None
    assert assessment.review_required is True
    assert {row.review_code for row in assessment.review_items} == {
        "candidate_scope_authority_missing",
        "candidate_scope_lineage_missing",
        "candidate_scope_taxonomy_unknown",
    }


@pytest.mark.parametrize("token", ["", "   ", "wrong-decoded-sku"])
def test_explicit_invalid_identity_token_is_not_silently_replaced(token: str) -> None:
    source = _source()
    assessment = CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=source.candidate_snapshot,
        authoritative_manifest_sku_codes=[
            source.target_snapshot.identity_market.sku_code,
            source.candidate_snapshot.identity_market.sku_code,
        ],
        candidate_identity_token=token,
    )

    assert assessment.scope_status == "excluded"
    assert assessment.exclusion_reason_code == "identity_decode_failed"


def test_excluded_scope_saves_audit_identity_without_analysis() -> None:
    source = _source()
    scope = CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=None,
        authoritative_manifest_sku_codes=[],
        candidate_identity_token="broken-token",
    )

    result = PairGateEvaluator().evaluate(
        scope=scope,
        project_id=source.target_snapshot.project_id,
        category_code=source.target_snapshot.category_code,
        competitor_profile_version_id=(
            source.target_snapshot.competitor_profile_version_id
        ),
        release_scope_key=source.target_snapshot.release_scope_key,
    )

    assert result.scope.scope_status == "excluded"
    assert result.dimension_states == []
    assert result.relation_assessments == []
    assert result.business_questions == []


def test_excluded_scope_rejects_fabricated_pair_analysis() -> None:
    source = _source()
    _, assembly = _assemble(source)
    scope = CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=None,
        authoritative_manifest_sku_codes=[],
        candidate_identity_token="broken-token",
    )

    with pytest.raises(PairGateInputError, match="hard-excluded"):
        PairGateEvaluator().evaluate(scope=scope, assembly=assembly)


@pytest.mark.parametrize("category", ["TV", "AC"])
@pytest.mark.parametrize(
    "candidate_m12d", ["complete", "partial", "missing", "conflict"]
)
def test_tv_ac_complete_partial_missing_conflict_keep_all_gates(
    category: str,
    candidate_m12d: str,
) -> None:
    source = _source(category, candidate_m12d=candidate_m12d)
    _, assembly = _assemble(source)
    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )

    assert result.scope.scope_status == "analyzable"
    assert tuple(str(row.dimension_code) for row in result.dimension_states) == (
        ALL_GATE_DIMENSION_CODES
    )
    assert tuple(str(row.relation_code) for row in result.relation_assessments) == (
        ALL_RELATION_CODES
    )
    assert tuple(str(row.question_code) for row in result.business_questions) == (
        ALL_QUESTION_CODES
    )
    assert {str(row.status) for row in result.relation_assessments} <= {
        "passed",
        "limited",
        "unassessable",
        "failed",
    }


def test_legacy_global_review_status_does_not_stop_relations_or_questions() -> None:
    source = _source()
    _, assembly = _assemble(source)
    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(
            assembly,
            status="review_required",
            gate_passed=True,
        ),
    )

    assert all(
        str(row.status) in {"passed", "limited"} for row in result.relation_assessments
    )
    assert result.answerable_question_codes
    assert "key_competitor_selection" in result.answerable_question_codes


@pytest.mark.parametrize("legacy_status", ["failed", "review_required"])
def test_legacy_candidate_control_gate_is_ignored_not_replayed(
    legacy_status: str,
) -> None:
    source = _source()
    _, assembly = _assemble(source)
    relations = _legacy_relations(
        assembly,
        status=legacy_status,
        gate_passed=False,
    )
    relations = [
        row.model_copy(
            update={
                "gate_results": [
                    row.gate_results[0].model_copy(
                        update={
                            "gate_code": "candidate_relation_evaluation_eligibility",
                            "reason_code": "candidate_not_admitted_to_relation_evaluation",
                        }
                    )
                ],
                "reason_codes": ["candidate_not_admitted_to_relation_evaluation"],
                "result_hash": f"held-{row.relation_code}-{legacy_status}",
            }
        )
        for row in relations
    ]

    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=relations,
    )

    assert all(
        str(row.status) in {"limited", "unassessable"}
        for row in result.relation_assessments
    )
    assert all(
        "legacy_candidate_control_gate_ignored" in row.limitations
        for row in result.relation_assessments
    )
    assert result.answerable_question_codes


def test_v11_calculates_all_mature_relations_for_legacy_held_candidate() -> None:
    source = _source()
    held_pair = source.pair_feature.model_copy(
        update={
            "candidate_status": "blocked",
            "relation_evaluation_member": False,
        }
    )
    calculator = V11RelationEvidenceCalculator()

    calculated = calculator.calculate(
        pair_feature=held_pair,
        purchase_pool=source.purchase_pool,
        value_substitution=source.value_substitution,
        price_volume_pressure=source.price_volume_pressure,
        config=_relation_config(),
    )
    admitted = calculator.calculate(
        pair_feature=source.pair_feature.model_copy(
            update={
                "candidate_status": "recalled_only",
                "relation_evaluation_member": True,
            }
        ),
        purchase_pool=source.purchase_pool,
        value_substitution=source.value_substitution,
        price_volume_pressure=source.price_volume_pressure,
        config=_relation_config(),
    )

    assert calculated == admitted
    assert len(calculated) == len(ALL_RELATION_CODES)
    assert {row.relation_code for row in calculated} == set(ALL_RELATION_CODES)
    assert all(row.gate_results for row in calculated)
    assert all(
        gate.gate_code != "candidate_relation_evaluation_eligibility"
        for row in calculated
        for gate in row.gate_results
    )


def test_v11_relation_calculation_rejects_broken_pair_hash_chain() -> None:
    source = _source()

    with pytest.raises(PairGateInputError, match="purchase-pool pair hash chain"):
        V11RelationEvidenceCalculator().calculate(
            pair_feature=source.pair_feature,
            purchase_pool=source.purchase_pool.model_copy(
                update={"pair_feature_result_hash": "wrong-pair-hash"}
            ),
            value_substitution=source.value_substitution,
            price_volume_pressure=source.price_volume_pressure,
            config=_relation_config(),
        )


def test_v11_relation_calculation_rejects_identity_metadata_mismatch() -> None:
    source = _source()

    with pytest.raises(PairGateInputError, match="identities must match"):
        V11RelationEvidenceCalculator().calculate(
            pair_feature=source.pair_feature,
            purchase_pool=source.purchase_pool.model_copy(
                update={
                    "candidate": source.purchase_pool.candidate.model_copy(
                        update={"brand_name": "OTHER-BRAND"}
                    )
                }
            ),
            value_substitution=source.value_substitution,
            price_volume_pressure=source.price_volume_pressure,
            config=_relation_config(),
        )


def test_m05c_review_stays_on_user_realization_dimension() -> None:
    source = _source()
    _, assembly = _assemble(source)
    original = assembly.dimensions.user_realization_comparison
    review_item = ReviewItem(
        review_code="m05c_user_realization_review",
        dimension_code="user_realization_comparison",
        reason_cn="M05C 用户兑现需要复核。",
        evidence_refs=original.evidence_refs,
    )
    conflict = original.model_copy(
        update={
            "availability": "conflict",
            "conclusion_strength": "unknown",
            "conclusion": original.conclusion.model_copy(
                update={"strength": "unknown", "direction": "unknown"}
            ),
            "review_required": True,
            "review_items": [review_item],
            "result_hash": "m05c-local-review-result",
        }
    )
    assembly = _rehash_assembly(
        assembly.model_copy(
            update={
                "dimensions": assembly.dimensions.model_copy(
                    update={"user_realization_comparison": conflict}
                ),
                "result_hash": "assembly-with-m05c-local-review",
            }
        )
    )

    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )

    by_dimension = {str(row.dimension_code): row for row in result.dimension_states}
    assert by_dimension["user_realization_comparison"].review_required is True
    assert result.review_required is True
    assert all(not row.review_required for row in result.relation_assessments)
    assert result.answerable_question_codes


def test_m12d_conflict_reviews_only_relations_that_use_affected_dimensions() -> None:
    source = _source(candidate_m12d="conflict")
    _, assembly = _assemble(source)
    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )

    reviewed = {
        str(row.relation_code)
        for row in result.relation_assessments
        if row.review_required
    }
    assert reviewed
    assert reviewed != set(ALL_RELATION_CODES)
    assert "direct_substitute" not in reviewed


def test_battlefield_conflict_only_reviews_direct_relation_and_other_questions_continue() -> (
    None
):
    source = _source()
    _, assembly = _assemble(source)
    original = assembly.dimensions.battlefield_overlap
    review_item = ReviewItem(
        review_code="battlefield_role_conflict",
        dimension_code="battlefield_overlap",
        reason_cn="战场角色存在局部冲突。",
        evidence_refs=original.evidence_refs,
    )
    conflict = original.model_copy(
        update={
            "availability": "conflict",
            "conclusion_strength": "unknown",
            "conclusion": original.conclusion.model_copy(
                update={"strength": "unknown", "direction": "unknown"}
            ),
            "review_required": True,
            "review_items": [review_item],
            "result_hash": "battlefield-local-conflict-result",
        }
    )
    assembly = _rehash_assembly(
        assembly.model_copy(
            update={
                "dimensions": assembly.dimensions.model_copy(
                    update={"battlefield_overlap": conflict}
                ),
                "result_hash": "assembly-with-battlefield-conflict",
            }
        )
    )

    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )

    reviewed = [
        str(row.relation_code)
        for row in result.relation_assessments
        if row.review_required
    ]
    assert reviewed == ["direct_substitute"]
    assert "purchase_choice" not in result.answerable_question_codes
    assert "price_volume_pressure" in result.answerable_question_codes
    assert "key_competitor_selection" in result.answerable_question_codes


def test_relation_local_independent_evidence_review_is_not_global() -> None:
    source = _source()
    _, assembly = _assemble(source)
    relations = _legacy_relations(assembly)
    first = relations[0]
    relations[0] = first.model_copy(
        update={
            "status": "review_required",
            "eligible_question_codes": [],
            "reason_codes": ["insufficient_independent_evidence_for_auto_use"],
            "limitations": ["relation_requires_manual_evidence_review"],
            "result_hash": "direct-relation-local-review-source",
        }
    )

    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=relations,
    )
    by_code = {str(row.relation_code): row for row in result.relation_assessments}

    assert by_code["direct_substitute"].status == "limited"
    assert by_code["direct_substitute"].review_required is True
    assert all(
        not row.review_required
        for code, row in by_code.items()
        if code != "direct_substitute"
    )
    assert result.review_required is True


def test_reviewed_alternative_evidence_caps_only_its_question_strength() -> None:
    source = _source()
    _, assembly = _assemble(source)
    original = assembly.dimensions.user_task_overlap
    review_item = ReviewItem(
        review_code="m09c_task_review",
        dimension_code="user_task_overlap",
        reason_cn="任务语义需要复核。",
        evidence_refs=original.evidence_refs,
    )
    reviewed = original.model_copy(
        update={
            "review_required": True,
            "review_items": [review_item],
            "result_hash": "reviewed-user-task-result",
        }
    )
    assembly = _rehash_assembly(
        assembly.model_copy(
            update={
                "dimensions": assembly.dimensions.model_copy(
                    update={"user_task_overlap": reviewed}
                ),
                "result_hash": "assembly-with-reviewed-user-task",
            }
        )
    )

    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )
    questions = {str(row.question_code): row for row in result.business_questions}

    assert questions["configuration_follow"].answerable is True
    assert questions["configuration_follow"].conclusion_strength in {
        "reference",
        "directional",
    }
    assert questions["price_volume_pressure"].answerable is True


def test_available_weight_and_legacy_candidate_status_are_not_gate_inputs() -> None:
    source_text = inspect.getsource(PairGateEvaluator)
    assert "coverage_minimum_gate" not in source_text
    assert "relation_evaluation_member" not in source_text
    assert "candidate_status in" not in source_text
    assert "reference_only" not in source_text


def test_all_65e7q_legacy_candidates_remain_analyzable_without_hard_error() -> None:
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
    source = _source()
    template = source.candidate_snapshot
    manifest = sorted(
        {
            source.target_snapshot.identity_market.sku_code,
            *candidate_codes,
        }
    )

    assessments = []
    for code in candidate_codes:
        snapshot = template.model_copy(
            update={
                "snapshot_ref": f"snapshot:{code}",
                "identity_market": template.identity_market.model_copy(
                    update={"sku_code": code}
                ),
                "result_hash": stable_hash(
                    code,
                    version="g34_65e7q_candidate_snapshot_fixture_v1",
                ),
            }
        )
        assessments.append(
            CandidateScopeClassifier().classify(
                target_snapshot=source.target_snapshot,
                candidate_snapshot=snapshot,
                authoritative_manifest_sku_codes=manifest,
            )
        )

    assert len(assessments) == fixture["legacy_input"]["candidate_count"] == 20
    assert all(row.scope_status == "analyzable" for row in assessments)
    assert all(row.exclusion_reason_code is None for row in assessments)


@pytest.mark.parametrize(
    ("mode", "expected_question"),
    [
        ("market", "price_volume_pressure"),
        ("configuration", "configuration_follow"),
    ],
)
def test_market_only_or_config_only_facts_can_still_answer_one_question(
    mode: str,
    expected_question: str,
) -> None:
    source = _source()
    _, assembly = _assemble(source)
    assembly = _with_only_market_or_configuration(assembly, mode)
    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )

    assert result.scope.scope_status == "analyzable"
    assert expected_question in result.answerable_question_codes
    assert "key_competitor_selection" in result.answerable_question_codes


def test_g28_gate_matrix_is_executable_scope_contract_not_a_candidate_gate() -> None:
    fixture_path = (
        Path(__file__).parents[4]
        / "docs/core3_mvp/real_data_v2/current_implementation/competitor_profile_v1"
        / "G28_gate_fixture_matrix.json"
    )
    matrix = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert set(matrix["hard_exclusion_codes"]) == HARD_EXCLUSION_CODES
    assert [row["case_code"] for row in matrix["cases"]] == [
        "tv_complete",
        "tv_m12d_missing",
        "tv_m05c_review",
        "tv_battlefield_conflict",
        "tv_market_only",
        "tv_configuration_only",
        "ac_complete",
        "ac_partial",
    ]
    assert all(row["scope_status"] == "analyzable" for row in matrix["cases"])
    assert all(row["must_continue"] for row in matrix["cases"])


def test_gate_result_hash_is_deterministic_and_source_bound() -> None:
    source = _source()
    _, assembly = _assemble(source)
    scope = _scope(source)
    relations = _legacy_relations(assembly)

    first = PairGateEvaluator().evaluate(
        scope=scope,
        assembly=assembly,
        legacy_relation_assessments=relations,
    )
    second = PairGateEvaluator().evaluate(
        scope=scope,
        assembly=assembly,
        legacy_relation_assessments=relations,
    )
    changed_relations = list(relations)
    changed_relations[0] = changed_relations[0].model_copy(
        update={"result_hash": "changed-source-relation-hash"}
    )
    changed = PairGateEvaluator().evaluate(
        scope=scope,
        assembly=assembly,
        legacy_relation_assessments=changed_relations,
    )

    assert first == second
    assert first.result_hash == second.result_hash
    assert changed.result_hash != first.result_hash


def test_tampered_g33_assembly_or_scope_authority_fails_closed() -> None:
    source = _source()
    _, assembly = _assemble(source)
    scope = _scope(source)
    relations = _legacy_relations(assembly)

    with pytest.raises(PairGateInputError, match="result hash"):
        PairGateEvaluator().evaluate(
            scope=scope,
            assembly=assembly.model_copy(
                update={"result_hash": "tampered-assembly-hash"}
            ),
            legacy_relation_assessments=relations,
        )
    with pytest.raises(PairGateInputError, match="scope result hash"):
        PairGateEvaluator().evaluate(
            scope=scope.model_copy(update={"target_snapshot_ref": "wrong-ref"}),
            assembly=assembly,
            legacy_relation_assessments=relations,
        )
    mismatched_scope = CandidateScopeClassifier().classify(
        target_snapshot=source.target_snapshot,
        candidate_snapshot=source.candidate_snapshot.model_copy(
            update={"snapshot_ref": "wrong-candidate-ref"}
        ),
        authoritative_manifest_sku_codes=[
            source.target_snapshot.identity_market.sku_code,
            source.candidate_snapshot.identity_market.sku_code,
        ],
    )
    with pytest.raises(PairGateInputError, match="authority chain"):
        PairGateEvaluator().evaluate(
            scope=mismatched_scope,
            assembly=assembly,
            legacy_relation_assessments=relations,
        )


def test_known_failed_legacy_relation_is_not_upgraded_by_passing_gate_fixture() -> None:
    source = _source()
    _, assembly = _assemble(source)
    relations = _legacy_relations(assembly)
    first = relations[0]
    relations[0] = first.model_copy(
        update={
            "status": "failed",
            "gate_results": [
                first.gate_results[0].model_copy(update={"passed": False})
            ],
            "eligible_question_codes": [],
            "reason_codes": ["known_relation_gate_failed"],
            "result_hash": "known-failed-source-relation",
        }
    )

    result = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=relations,
    )

    assert result.relation_assessments[0].status == "failed"


def test_gate_input_requires_exactly_one_source_relation_per_code() -> None:
    source = _source()
    _, assembly = _assemble(source)
    rows = _legacy_relations(assembly)

    with pytest.raises(PairGateInputError, match="all seven"):
        PairGateEvaluator().evaluate(
            scope=_scope(source),
            assembly=assembly,
            legacy_relation_assessments=rows[:-1],
        )


def test_gate_module_has_no_repository_llm_selection_or_materializer_dependency() -> (
    None
):
    from app.services.core3_real_data.analyst import (
        competitor_profile_v1_1_gate_evaluation as module,
    )

    source_text = inspect.getsource(module)
    for forbidden in (
        "sqlalchemy",
        "Repository",
        "openai",
        "requests.",
        "KeyCompetitorSelector",
        "CompetitorProfileMaterializer",
    ):
        assert forbidden not in source_text
