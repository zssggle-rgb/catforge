from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Decimal
import inspect

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.anchor_substitutability import (
    VALUE_ANCHOR_MATCHER_CONFIG_VERSION,
    VALUE_ANCHOR_MATCHER_METHOD_VERSION,
    ValueAnchorMatcher,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_config import (
    build_production_materialization_config,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
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
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PAIR_ANALYSIS_AUTHORITATIVE_PROJECTION_VERSION,
    PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
    PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
    PairAnalysisAssembler,
    PairAnalysisCalculator,
    PairAnalysisCalculatorInput,
    PairAnalysisInputError,
    build_authoritative_pair_projection,
    pair_analysis_assembly_expected_hash,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    LegacyScoreBasis,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_snapshot_builder import (
    VersionSkuAnalysisSnapshotBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution import (
    ValueSubstitutionEvidenceEvaluator,
)
from app.services.core3_real_data.analyst.purchase_pressure_comparison import (
    PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION,
    PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION,
    PurchasePressureComparator,
)
from app.services.core3_real_data.analyst.replacement_pressure import (
    REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION,
    REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION,
    ReplacementPressureClassifier,
)
from app.services.core3_real_data.hash_utils import stable_hash
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)


def _anchor(code: str, rank: int, *, pressure: str = "low") -> dict[str, object]:
    return {
        "anchor_code": code,
        "anchor_cn": code,
        "anchor_family_code": "picture_or_experience",
        "anchor_rank": rank,
        "role": "core_payment",
        "core_eligible": True,
        "establishment_score": "10.0000",
        "establishment_status": "established",
        "evidence_domains": [
            "param_fact",
            "fact_claim",
            "comment_perception",
            "market_acceptance",
        ],
        "evidence_strength": "strong",
        "user_validation_status": "user_validated",
        "pressure_level": pressure,
        "pressure_summary_cn": f"{code}存在{pressure}级顾虑。",
        "confidence": "0.8500",
        "support_summary_cn": f"{code}具有完整证据。",
    }


def _analysis_bundle(
    category: str = "TV",
    *,
    candidate_m12d: str = "complete",
) -> CompetitorProfileCategoryInputBundle:
    if category == "TV":
        bundle = _category_bundle()
        candidate_code = "TV000002"
    else:
        specs = [_default_spec("AC", number) for number in range(1, 4)]
        for spec in specs:
            spec.update(
                {
                    "market_pool": "ac-wall-1p5-main",
                    "task_primary": "fast_cooling",
                    "audience_primary": "family_comfort",
                    "battlefield_primary": "cooling_comfort",
                    "purchase_reasons": ["fast_cooling", "stable_comfort"],
                    "claim_values": ["cooling_efficiency"],
                }
            )
        bundle = _category_bundle("AC", specs)
        candidate_code = "AC000002"
    payload = copy.deepcopy(bundle.model_dump(mode="python"))
    m12d = payload["modules"]["M12D"]
    for sku_code, rows in m12d["records_by_sku"].items():
        facts = rows[0]["facts"]
        codes = [
            str(row.get("anchor_code"))
            for row in facts.get("core_payment_anchors_json") or []
            if row.get("anchor_code")
        ]
        facts.update(
            {
                "status": "ready",
                "profile_confidence": Decimal("0.8500"),
                "confidence_level": "high",
                "core_payment_anchors_json": [
                    _anchor(code, rank) for rank, code in enumerate(codes, start=1)
                ],
                "established_anchors_json": [],
                "proposition_anchors_json": [],
                "supporting_anchors_json": [],
                "weak_expression_anchors_json": [],
                "risk_drag_anchors_json": [],
            }
        )
    if candidate_m12d == "missing":
        m12d["records_by_sku"].pop(candidate_code)
        m12d["record_count"] -= 1
        m12d["sku_count"] -= 1
    elif candidate_m12d == "partial":
        facts = m12d["records_by_sku"][candidate_code][0]["facts"]
        facts["supporting_anchors_json"] = [
            {
                "anchor_code": "invalid_partial_anchor",
                "anchor_cn": "缺少必要字段的局部锚点",
            }
        ]
    elif candidate_m12d == "conflict":
        rows = m12d["records_by_sku"][candidate_code]
        duplicate = copy.deepcopy(rows[0])
        duplicate["record_id"] = f"{duplicate['record_id']}-conflict"
        duplicate["result_hash"] = stable_hash(
            candidate_code,
            version="m12d_conflict_fixture_v1",
        )
        duplicate["facts"]["status"] = "failed"
        rows.append(duplicate)
        rows.sort(key=lambda row: row["record_id"])
        m12d["record_count"] += 1
    return CompetitorProfileCategoryInputBundle.model_validate(payload)


def _source(
    category: str = "TV",
    *,
    candidate_m12d: str = "complete",
    legacy_basis: LegacyScoreBasis | None = None,
) -> PairAnalysisCalculatorInput:
    bundle = _analysis_bundle(category, candidate_m12d=candidate_m12d)
    target_code = f"{category}000001"
    candidate_code = f"{category}000002"
    config = build_production_materialization_config(bundle)
    pipeline = CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, target_code),
        recall_config=config.recall,
        eligibility_config=config.eligibility,
    )
    features = PairFeatureBuilder().build(pipeline)
    pool = PurchasePoolSemanticEvaluator().evaluate(
        features,
        config.purchase_pool,
    )
    value = ValueSubstitutionEvidenceEvaluator().evaluate(
        features,
        pool,
        config.value_substitution,
    )
    pressure = PriceVolumePressureEvaluator().evaluate(
        features,
        pool,
        value,
        config.price_volume,
    )
    version_id = f"competitor-profile-v11-{category.lower()}-test"
    snapshots = {
        row.identity_market.sku_code: row
        for row in VersionSkuAnalysisSnapshotBuilder().build_many(
            bundle,
            competitor_profile_version_id=version_id,
        )
    }

    def pick(rows):
        return next(row for row in rows if row.candidate.sku_code == candidate_code)

    recalled = pick(pipeline.recall_manifest.candidates)
    recall_rank = next(
        index
        for index, row in enumerate(pipeline.recall_manifest.candidates, start=1)
        if row.candidate.sku_code == candidate_code
    )
    return PairAnalysisCalculatorInput(
        competitor_profile_version_id=version_id,
        pair_feature=pick(features.pairs),
        purchase_pool=pick(pool.pairs),
        value_substitution=pick(value.pairs),
        price_volume_pressure=pick(pressure.pairs),
        target_snapshot=snapshots[target_code],
        candidate_snapshot=snapshots[candidate_code],
        recalled_candidate=recalled,
        recall_rank=recall_rank,
        legacy_basis=legacy_basis,
    )


def _assemble(source: PairAnalysisCalculatorInput):
    calculation = PairAnalysisCalculator().calculate(source)
    return calculation, PairAnalysisAssembler().assemble(calculation)


def test_complete_tv_pair_calls_mature_algorithms_and_preserves_full_payloads() -> None:
    source = _source()
    calculation, assembly = _assemble(source)

    assert assembly.category_code == "TV"
    assert assembly.value_anchor_analysis.anchor_substitutability_score == Decimal(
        calculation.value_anchor_result.anchor_substitutability_score
    )
    assert (
        assembly.value_anchor_analysis.legacy_matcher_payload[
            "anchor_substitutability_score"
        ]
        == calculation.value_anchor_result.anchor_substitutability_score
    )
    assert assembly.replacement_pressure_analysis.replacement_pressure_score == Decimal(
        calculation.replacement_pressure_result.replacement_pressure_score
    )
    assert assembly.purchase_pressure_comparison.comparison_allowed is True
    assert assembly.aligned_features == [
        row.model_dump(mode="json") for row in source.pair_feature.aligned_features
    ]
    assert assembly.purchase_reason_assessments == [
        row.model_dump(mode="json")
        for row in source.value_substitution.purchase_reason_assessments
    ]
    assert assembly.value_assessments == [
        row.model_dump(mode="json")
        for row in source.value_substitution.value_assessments
    ]
    assert assembly.price_volume_process == source.price_volume_pressure.model_dump(
        mode="json"
    )
    assert assembly.market_validation.sales_overlap_snapshot.method == (
        "full_observed_weekly_average"
    )
    assert assembly.purchase_pool == calculation.purchase_pool_analysis
    assert assembly.dimensions == calculation.dimensions
    assert assembly.value_anchor_analysis == calculation.value_anchor_analysis
    assert (
        assembly.replacement_pressure_analysis
        == calculation.replacement_pressure_analysis
    )
    assert (
        assembly.purchase_pressure_comparison == calculation.purchase_pressure_analysis
    )
    assert assembly.market_validation == calculation.market_validation
    assert assembly.calculation_result_hash == calculation.calculation_result_hash

    def evidence_key(row):
        return (
            row.module_code,
            row.source_batch_id or "",
            row.record_type,
            row.record_id,
            row.result_hash,
        )

    assert {
        evidence_key(row) for row in source.recalled_candidate.evidence_refs
    }.issubset({evidence_key(row) for row in assembly.evidence_refs})


def test_authoritative_projection_preserves_typed_graph_without_raw_duplicates() -> None:
    _calculation, full = _assemble(_source())

    projected = build_authoritative_pair_projection(full)

    assert projected.process_projection_mode == "authoritative_typed"
    assert projected.source_full_result_hash == full.result_hash
    assert projected.aligned_features == []
    assert projected.purchase_reason_assessments == []
    assert projected.value_assessments == []
    assert projected.price_volume_process == {
        "projection_version": PAIR_ANALYSIS_AUTHORITATIVE_PROJECTION_VERSION,
        "source_full_result_hash": full.result_hash,
    }
    assert projected.result_hash == pair_analysis_assembly_expected_hash(projected)

    def strip_raw_duplicates(value):
        if isinstance(value, dict):
            return {
                key: (
                    {}
                    if key == "raw_details"
                    or key == "legacy_payload"
                    or (key.startswith("legacy_") and key.endswith("_payload"))
                    else strip_raw_duplicates(child)
                )
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [strip_raw_duplicates(child) for child in value]
        return value

    for field_name in (
        "purchase_pool",
        "dimensions",
        "value_anchor_analysis",
        "replacement_pressure_analysis",
        "purchase_pressure_comparison",
        "market_validation",
        "legacy_basis",
        "source_lineage",
        "evidence_refs",
        "limitations",
        "calculator_versions",
    ):
        assert projected.model_dump(mode="json", include={field_name})[
            field_name
        ] == strip_raw_duplicates(
            full.model_dump(mode="json", include={field_name})[field_name]
        )

    def assert_no_nonempty_raw_bags(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "raw_details" or key == "legacy_payload" or (
                    key.startswith("legacy_") and key.endswith("_payload")
                ):
                    assert child == {}
                assert_no_nonempty_raw_bags(child)
        elif isinstance(value, list):
            for child in value:
                assert_no_nonempty_raw_bags(child)

    assert_no_nonempty_raw_bags(projected.model_dump(mode="json"))


def test_every_mature_calculator_version_is_explicit_and_frozen() -> None:
    calculation, assembly = _assemble(_source())
    assert calculation.calculator_versions == assembly.calculator_versions
    assert assembly.calculator_versions == dict(
        sorted(
            {
                "purchase_pressure_config": PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION,
                "purchase_pressure_method": PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION,
                "replacement_pressure_config": REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION,
                "replacement_pressure_method": REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION,
                "value_anchor_config": VALUE_ANCHOR_MATCHER_CONFIG_VERSION,
                "value_anchor_method": VALUE_ANCHOR_MATCHER_METHOD_VERSION,
            }.items()
        )
    )
    assert (
        assembly.value_anchor_analysis.calculator_method_version
        == VALUE_ANCHOR_MATCHER_METHOD_VERSION
    )
    assert (
        assembly.replacement_pressure_analysis.calculator_config_version
        == REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION
    )
    assert (
        assembly.purchase_pressure_comparison.calculator_method_version
        == PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION
    )


def test_legacy_unassessed_anchors_allow_anchor_matching_but_not_pressure_comparison() -> (
    None
):
    source = _source()

    def with_unassessed_anchors(snapshot):
        purchase = snapshot.purchase_reason_snapshot
        assert purchase is not None
        anchors = [
            row.model_copy(
                update={
                    "establishment_status": "unassessed",
                    "raw_details": {
                        **row.raw_details,
                        "establishment_status": "unassessed",
                    },
                }
            )
            for row in purchase.anchors
        ]
        updated_purchase = purchase.model_copy(update={"anchors": anchors})
        return snapshot.model_copy(
            update={
                "purchase_reason_snapshot": updated_purchase,
                "result_hash": stable_hash(
                    updated_purchase.model_dump(mode="json"),
                    version="legacy_unassessed_snapshot_fixture_v1",
                ),
            }
        )

    calculation, assembly = _assemble(
        replace(
            source,
            target_snapshot=with_unassessed_anchors(source.target_snapshot),
            candidate_snapshot=with_unassessed_anchors(source.candidate_snapshot),
        )
    )

    assert calculation.target_m12d_contract.capabilities.comparison_mode == "strong"
    assert (
        calculation.target_m12d_contract.capabilities.pressure_comparison_allowed
        is False
    )
    assert calculation.value_anchor_result.pair_scoring_allowed is True
    assert assembly.purchase_pressure_comparison.comparison_allowed is False
    assert assembly.purchase_pressure_comparison.conclusion.strength == "unknown"


def test_declared_m12d_mode_is_a_cap_and_never_widens_upstream_capability() -> None:
    source = _source()

    def with_declared_mode(snapshot, comparison_mode: str):
        purchase = snapshot.purchase_reason_snapshot
        assert purchase is not None
        updated_purchase = purchase.model_copy(
            update={"comparison_mode": comparison_mode}
        )
        return snapshot.model_copy(
            update={
                "purchase_reason_snapshot": updated_purchase,
                "result_hash": stable_hash(
                    updated_purchase.model_dump(mode="json"),
                    version=f"declared_{comparison_mode}_snapshot_fixture_v1",
                ),
            }
        )

    calculation, assembly = _assemble(
        replace(
            source,
            target_snapshot=with_declared_mode(source.target_snapshot, "blocked"),
            candidate_snapshot=with_declared_mode(
                source.candidate_snapshot,
                "strong",
            ),
        )
    )

    assert calculation.target_m12d_contract.capabilities.comparison_mode == "blocked"
    assert (
        calculation.target_m12d_contract.capabilities.fact_dimensions_allowed is False
    )
    assert calculation.value_anchor_result.pair_scoring_allowed is False
    assert assembly.value_anchor_analysis.anchor_substitutability_score is None


def test_assembler_evidence_closure_cannot_drop_child_evidence() -> None:
    _calculation, assembly = _assemble(_source())
    victim = assembly.purchase_pressure_comparison.evidence_refs[0]

    def is_victim(row: dict[str, object]) -> bool:
        return (
            row["module_code"],
            row.get("source_batch_id") or "",
            row["record_type"],
            row["record_id"],
            row["result_hash"],
        ) == (
            victim.module_code,
            victim.source_batch_id or "",
            victim.record_type,
            victim.record_id,
            victim.result_hash,
        )

    payload = assembly.model_dump(mode="json")
    payload["evidence_refs"] = [
        row for row in payload["evidence_refs"] if not is_victim(row)
    ]
    payload["source_lineage"]["evidence_refs"] = payload["evidence_refs"]
    with pytest.raises(ValidationError, match="missing child evidence refs"):
        type(assembly).model_validate(payload)


def test_calculator_calls_each_mature_algorithm_once_and_assembler_never_calls_them() -> (
    None
):
    class AnchorSpy:
        def __init__(self) -> None:
            self.calls = 0
            self.delegate = ValueAnchorMatcher()

        def match(self, **kwargs):
            self.calls += 1
            return self.delegate.match(**kwargs)

    class ReplacementSpy:
        def __init__(self) -> None:
            self.calls = 0
            self.delegate = ReplacementPressureClassifier()

        def classify(self, payload):
            self.calls += 1
            return self.delegate.classify(payload)

    class PurchaseSpy:
        def __init__(self) -> None:
            self.calls = 0
            self.delegate = PurchasePressureComparator()

        def compare(self, **kwargs):
            self.calls += 1
            return self.delegate.compare(**kwargs)

    anchor = AnchorSpy()
    replacement_spy = ReplacementSpy()
    purchase = PurchaseSpy()
    calculator = PairAnalysisCalculator(
        value_anchor_matcher=anchor,
        replacement_pressure_classifier=replacement_spy,
        purchase_pressure_comparator=purchase,
    )
    calculation = calculator.calculate(_source())
    assert (anchor.calls, replacement_spy.calls, purchase.calls) == (1, 1, 1)
    PairAnalysisAssembler().assemble(calculation)
    assert (anchor.calls, replacement_spy.calls, purchase.calls) == (1, 1, 1)
    assembler_source = inspect.getsource(PairAnalysisAssembler.assemble)
    for calculator_helper in (
        "_dimension_set(",
        "_purchase_pool_analysis(",
        "_purchase_pressure_analysis(",
        "_value_anchor_analysis(",
        "_replacement_pressure_analysis(",
        "_market_validation(",
        "_reconstructed_legacy_basis(",
    ):
        assert calculator_helper not in assembler_source


def test_missing_m12d_only_degrades_anchor_and_purchase_pressure_dimensions() -> None:
    calculation, assembly = _assemble(_source(candidate_m12d="missing"))

    assert calculation.value_anchor_result.pair_scoring_allowed is False
    assert assembly.value_anchor_analysis.anchor_substitutability_score is None
    assert assembly.value_anchor_analysis.anchor_substitutability_level == "unknown"
    assert assembly.value_anchor_analysis.score.raw_score is None
    assert assembly.purchase_pressure_comparison.comparison_allowed is False
    assert assembly.purchase_pressure_comparison.conclusion.strength == "unknown"
    assert assembly.dimensions.purchase_reason_comparison.availability == "unknown"
    assert assembly.dimensions.purchase_reason_comparison.score.raw_score is None
    assert assembly.dimensions.battlefield_overlap.score.raw_score is not None
    assert assembly.market_validation.conclusion.strength != "unknown"
    assert assembly.replacement_pressure_analysis.replacement_pressure_score is not None


def test_m12d_conflict_stays_local_and_never_becomes_a_fake_zero() -> None:
    _calculation, assembly = _assemble(_source(candidate_m12d="conflict"))

    assert assembly.value_anchor_analysis.anchor_substitutability_score is None
    assert assembly.dimensions.purchase_reason_comparison.availability == "conflict"
    assert assembly.dimensions.purchase_reason_comparison.score.raw_score is None
    assert assembly.dimensions.purchase_reason_comparison.review_required is True
    assert assembly.dimensions.user_task_overlap.score.raw_score is not None
    assert assembly.market_validation.target_weighted_price is not None


def test_partial_m12d_keeps_valid_anchor_result_with_review_overlay() -> None:
    calculation, assembly = _assemble(_source(candidate_m12d="partial"))

    assert calculation.value_anchor_result.pair_scoring_allowed is True
    assert assembly.value_anchor_analysis.anchor_substitutability_score is not None
    assert assembly.value_anchor_analysis.review_required is True
    assert assembly.dimensions.purchase_reason_comparison.availability == "partial"
    assert assembly.dimensions.purchase_reason_comparison.review_required is True


def test_ac_pair_uses_ac_snapshot_without_tv_product_form_leakage() -> None:
    source = _source("AC")
    _calculation, assembly = _assemble(source)

    assert assembly.category_code == "AC"
    assert source.target_snapshot.product_form_facts.screen_size_inch is None
    assert source.target_snapshot.product_form_facts.ac_product_form == "wall_mounted"
    assert assembly.market_validation.target_weighted_price is not None
    assert assembly.dimensions.battlefield_overlap.score.raw_score is not None


@pytest.mark.parametrize("candidate_m12d", ["partial", "missing", "conflict"])
def test_ac_pair_preserves_each_noncomplete_m12d_state_locally(
    candidate_m12d: str,
) -> None:
    _calculation, assembly = _assemble(_source("AC", candidate_m12d=candidate_m12d))

    assert assembly.category_code == "AC"
    assert assembly.market_validation.target_weighted_price is not None
    assert assembly.dimensions.user_task_overlap.score.raw_score is not None
    if candidate_m12d == "partial":
        assert assembly.value_anchor_analysis.anchor_substitutability_score is not None
        assert assembly.value_anchor_analysis.review_required is True
        assert assembly.dimensions.purchase_reason_comparison.availability == "partial"
    else:
        assert assembly.value_anchor_analysis.anchor_substitutability_score is None
        assert assembly.purchase_pressure_comparison.comparison_allowed is False
        expected = "conflict" if candidate_m12d == "conflict" else "unknown"
        assert assembly.dimensions.purchase_reason_comparison.availability == expected


def test_limited_market_input_cannot_produce_a_strong_market_conclusion() -> None:
    source = _source()
    limited_pressure = source.price_volume_pressure.model_copy(
        update={
            "market_comparability_status": "limited",
            "confidence_level": "high",
            "review_required": False,
            "result_hash": stable_hash(
                source.price_volume_pressure.model_dump(mode="json"),
                version="limited_market_pair_fixture_v1",
            ),
        }
    )
    calculation, assembly = _assemble(
        replace(source, price_volume_pressure=limited_pressure)
    )

    assert assembly.market_validation.market_validation_strength == "directional"
    assert assembly.market_validation.conclusion.strength == "directional"
    assert (
        calculation.replacement_pressure_result.score_breakdown.market_diversion_validation
        == Decimal("0.2500")
    )
    assert "sample_limited" in calculation.replacement_pressure_result.risk_notes


def test_same_input_is_deterministic_and_legacy_basis_is_preserved_exactly() -> None:
    legacy = LegacyScoreBasis(
        competitor_score=Decimal("0.7310"),
        semantic_overlap_score=Decimal("0.6420"),
        parameter_claim_overlap_score=Decimal("0.5150"),
        sales_closeness_score=Decimal("0.8330"),
        legacy_payload={"basis_source": "G28_exact_fixture"},
    )
    source = _source(legacy_basis=legacy)
    first_calculation, first = _assemble(source)
    second_calculation, second = _assemble(source)

    assert first_calculation.input_fingerprint == second_calculation.input_fingerprint
    assert (
        first_calculation.calculation_result_hash
        == second_calculation.calculation_result_hash
    )
    assert first == second
    assert first.result_hash == second.result_hash
    assert first.legacy_basis == legacy


def test_assembler_rejects_tampered_calculated_components_before_projection() -> None:
    calculation = PairAnalysisCalculator().calculate(_source())
    tampered = replace(
        calculation,
        value_anchor_analysis=calculation.value_anchor_analysis.model_copy(
            update={"result_hash": "hash:tampered-anchor-result"}
        ),
    )

    with pytest.raises(PairAnalysisInputError, match="does not close before assembly"):
        PairAnalysisAssembler().assemble(tampered)


def test_hash_chain_or_scope_mismatch_fails_closed() -> None:
    source = _source()
    bad_pressure = source.price_volume_pressure.model_copy(
        update={"pair_feature_result_hash": "hash:wrong-pair-feature"}
    )
    with pytest.raises(PairAnalysisInputError, match="price-volume hash chain"):
        PairAnalysisCalculator().calculate(
            replace(source, price_volume_pressure=bad_pressure)
        )

    bad_candidate = source.candidate_snapshot.model_copy(
        update={"competitor_profile_version_id": "another-version"}
    )
    with pytest.raises(PairAnalysisInputError, match="one exact version scope"):
        PairAnalysisCalculator().calculate(
            replace(source, candidate_snapshot=bad_candidate)
        )


def test_all_source_identity_and_hash_chain_guards_fail_closed() -> None:
    source = _source()
    wrong_identity = source.pair_feature.candidate.model_copy(
        update={"sku_code": "TV999999"}
    )
    bad_authority_lineage = {
        **source.candidate_snapshot.source_lineage,
        "source_result_hashes": {
            **source.candidate_snapshot.source_lineage["source_result_hashes"],
            "M12D": "hash:other-authority",
        },
    }
    cases = [
        (
            replace(source, competitor_profile_version_id=""),
            "version ID is required",
        ),
        (replace(source, recall_rank=0), "recall rank must be positive"),
        (
            replace(source, candidate_snapshot=source.target_snapshot),
            "self pairs belong",
        ),
        (
            replace(
                source,
                pair_feature=source.pair_feature.model_copy(
                    update={"candidate": wrong_identity}
                ),
            ),
            "stage identities",
        ),
        (
            replace(
                source,
                recalled_candidate=source.recalled_candidate.model_copy(
                    update={"candidate": wrong_identity}
                ),
            ),
            "recalled candidate",
        ),
        (
            replace(
                source,
                pair_feature=source.pair_feature.model_copy(
                    update={"recall_result_hash": "hash:wrong-recall"}
                ),
            ),
            "pair feature recall hash chain",
        ),
        (
            replace(
                source,
                purchase_pool=source.purchase_pool.model_copy(
                    update={"pair_feature_result_hash": "hash:wrong-feature"}
                ),
            ),
            "purchase-pool hash chain",
        ),
        (
            replace(
                source,
                value_substitution=source.value_substitution.model_copy(
                    update={"purchase_pool_result_hash": "hash:wrong-pool"}
                ),
            ),
            "value-substitution hash chain",
        ),
        (
            replace(
                source,
                candidate_snapshot=source.candidate_snapshot.model_copy(
                    update={"source_lineage": bad_authority_lineage}
                ),
            ),
            "authority lineage",
        ),
    ]

    for bad_source, message in cases:
        with pytest.raises(PairAnalysisInputError, match=message):
            PairAnalysisCalculator().calculate(bad_source)


def test_invalid_m12d_anchor_payload_degrades_only_m12d_outputs() -> None:
    source = _source()

    def without_anchor_codes(snapshot):
        purchase = snapshot.purchase_reason_snapshot
        assert purchase is not None
        anchors = [
            row.model_copy(
                update={"raw_details": {**row.raw_details, "anchor_code": ""}}
            )
            for row in purchase.anchors
        ]
        return snapshot.model_copy(
            update={
                "purchase_reason_snapshot": purchase.model_copy(
                    update={"anchors": anchors}
                ),
                "result_hash": stable_hash(
                    snapshot.identity_market.sku_code,
                    version="invalid_m12d_anchor_fixture_v1",
                ),
            }
        )

    calculation, assembly = _assemble(
        replace(
            source,
            target_snapshot=without_anchor_codes(source.target_snapshot),
            candidate_snapshot=without_anchor_codes(source.candidate_snapshot),
        )
    )

    assert calculation.target_m12d_contract.found is False
    assert assembly.value_anchor_analysis.anchor_substitutability_score is None
    assert assembly.purchase_pressure_comparison.comparison_allowed is False
    assert assembly.dimensions.user_task_overlap.score.raw_score is not None


def test_unknown_market_stays_unknown_and_contributes_no_replacement_market_signal() -> (
    None
):
    source = _source()
    unknown_pressure = source.price_volume_pressure.model_copy(
        update={
            "market_comparability_status": "unknown",
            "confidence_level": "unknown",
            "result_hash": stable_hash(
                source.price_volume_pressure.model_dump(mode="json"),
                version="unknown_market_pair_fixture_v1",
            ),
        }
    )
    calculation, assembly = _assemble(
        replace(source, price_volume_pressure=unknown_pressure)
    )

    assert assembly.market_validation.conclusion.strength == "unknown"
    assert (
        calculation.replacement_pressure_result.score_breakdown.market_diversion_validation
        == Decimal("0.0000")
    )
    assert "market_missing" in calculation.replacement_pressure_result.risk_notes


def test_evidence_deduplication_is_lossless_and_conflicts_fail_closed() -> None:
    from app.services.core3_real_data.analyst import (
        competitor_profile_v1_1_pair_analysis as module,
    )

    base = _source().recalled_candidate.evidence_refs[0]
    left = base.model_copy(
        update={
            "evidence_ids": ["evidence-a"],
            "source_file_ids": ["file-a"],
            "confidence": None,
        }
    )
    right = base.model_copy(
        update={
            "evidence_ids": ["evidence-b"],
            "raw_row_ids": ["row-b"],
            "confidence": Decimal("0.8"),
        }
    )

    merged = module._dedupe_evidence([left, right])
    assert len(merged) == 1
    assert merged[0].evidence_ids == ["evidence-a", "evidence-b"]
    assert merged[0].source_file_ids == ["file-a"]
    assert merged[0].raw_row_ids == ["row-b"]
    assert merged[0].confidence == Decimal("0.8")

    conflicting = right.model_copy(update={"taxonomy_version": "other-taxonomy"})
    with pytest.raises(ValueError, match="conflicting version metadata"):
        module._dedupe_evidence([left, conflicting])


def test_pair_analysis_module_has_no_database_repository_llm_or_downstream_stage_calls() -> (
    None
):
    from app.services.core3_real_data.analyst import (
        competitor_profile_v1_1_pair_analysis as module,
    )

    source = inspect.getsource(module)
    for forbidden in (
        "sqlalchemy",
        "Repository",
        "openai",
        "requests.",
        "KeyCompetitorSelector",
        "CompetitorRelationEvaluator",
        "CompetitorProfileMaterializer",
    ):
        assert forbidden not in source
    assert PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION in source
    assert PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION in source
