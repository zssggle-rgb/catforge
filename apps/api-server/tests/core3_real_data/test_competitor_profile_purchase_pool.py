from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_purchase_pool as purchase_pool_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool import (
    PurchasePoolEvaluationError,
    PurchasePoolSemanticEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    BattlefieldCodeAssessment,
    PurchasePoolSemanticBundle,
    PurchasePoolSemanticConfig,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)


def _pair_features(bundle, target: str = "TV000001"):
    pipeline = CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, target),
    )
    return PairFeatureBuilder().build(pipeline)


def _config(
    category: str = "TV",
    *,
    generic: tuple[str, ...] = (),
    table_stake: tuple[str, ...] = (),
    discriminative: tuple[str, ...] = ("picture",),
    coverage: dict[str, Decimal] | None = None,
    version: str = "purchase-pool-test-v1",
) -> PurchasePoolSemanticConfig:
    values = coverage if coverage is not None else {"picture": Decimal("0.20")}
    return PurchasePoolSemanticConfig(
        config_version=version,
        product_category=category,
        same_budget_max_gap_ratio=Decimal("0.15"),
        adjacent_budget_max_gap_ratio=Decimal("0.35"),
        generic_coverage_threshold=Decimal("0.80"),
        generic_value_codes=sorted(generic),
        table_stake_value_codes=sorted(table_stake),
        discriminative_value_codes=sorted(discriminative),
        value_coverage_ratios={key: values[key] for key in sorted(values)},
    )


def _evaluate(bundle, config=None, target: str = "TV000001"):
    pair_features = _pair_features(bundle, target)
    return PurchasePoolSemanticEvaluator().evaluate(
        pair_features,
        config or _config(pair_features.product_category),
    )


def _pair(result: PurchasePoolSemanticBundle, sku_code: str):
    return next(row for row in result.pairs if row.candidate.sku_code == sku_code)


def _two_specs(
    category: str,
    *,
    target_updates: dict | None = None,
    candidate_updates: dict | None = None,
):
    target = _default_spec(category, 1)
    candidate = _default_spec(category, 2)
    target.update(
        {
            "brand": "海信",
            "task_primary": "cinema" if category == "TV" else "sleep",
            "battlefield_primary": "picture" if category == "TV" else "comfort",
            "price": Decimal("5000"),
            **(target_updates or {}),
        }
    )
    candidate.update(
        {
            "brand": "TCL",
            "task_primary": "cinema" if category == "TV" else "sleep",
            "battlefield_primary": "picture" if category == "TV" else "comfort",
            "price": Decimal("5100"),
            **(candidate_updates or {}),
        }
    )
    return [target, candidate]


def test_p0_requires_same_form_segment_budget_core_task_and_specific_value() -> None:
    result = _evaluate(_category_bundle())
    direct = _pair(result, "TV000002")

    assert direct.purchase_pool.level == "P0"
    assert direct.purchase_pool.confidence_level == "high"
    assert direct.shared_primary_task_codes == ["cinema"]
    assert direct.budget_band == "same"
    assert direct.same_product_form is True
    assert direct.same_size_or_capacity_segment is True
    picture = next(
        row
        for row in direct.battlefield_overlap.assessments
        if row.battlefield_code == "picture"
    )
    assert picture.overlap_type == "shared_primary"
    assert picture.classification == "discriminative"
    assert picture.supports_purchase_pool_overlap is True
    assert all(gate.known and gate.passed for gate in direct.purchase_pool.gate_results)


def test_p1_is_same_shape_and_segment_with_adjacent_budget_but_different_route() -> (
    None
):
    specs = _two_specs(
        "TV",
        candidate_updates={
            "price": Decimal("5800"),
            "battlefield_primary": "gaming",
        },
    )
    config = _config(
        discriminative=("gaming", "picture"),
        coverage={"gaming": Decimal("0.25"), "picture": Decimal("0.20")},
    )
    result = _evaluate(_category_bundle(specs=specs), config)
    pair = result.pairs[0]

    assert pair.purchase_pool.level == "P1"
    assert pair.budget_band == "adjacent"
    assert pair.battlefield_overlap.value_route_status == "different"
    assert pair.shared_primary_task_codes == ["cinema"]


def test_p2_handles_cross_size_or_cross_form_shared_scenario() -> None:
    tv_specs = _two_specs(
        "TV",
        candidate_updates={"screen_size": Decimal("75"), "size_segment": "75"},
    )
    tv = _evaluate(_category_bundle(specs=tv_specs)).pairs[0]
    assert tv.purchase_pool.level == "P2"
    assert tv.same_product_form is True
    assert tv.same_size_or_capacity_segment is False

    ac_specs = _two_specs(
        "AC",
        candidate_updates={"ac_form": "floor_standing"},
    )
    ac = _evaluate(
        _category_bundle("AC", ac_specs),
        _config(
            "AC",
            discriminative=("comfort",),
            coverage={"comfort": Decimal("0.30")},
        ),
        "AC000001",
    ).pairs[0]
    assert ac.purchase_pool.level == "P2"
    assert ac.same_product_form is False
    assert ac.same_size_or_capacity_segment is True
    form_gate = next(
        gate
        for gate in ac.purchase_pool.gate_results
        if gate.gate_code == "category_product_form_compatibility"
    )
    assert form_gate.reason_code == "cross_form_shared_primary_task_scenario"


def test_p3_is_reference_only_when_known_gates_do_not_support_purchase_choice() -> None:
    config = _config(
        discriminative=("gaming", "picture"),
        coverage={
            "gaming": Decimal("0.10"),
            "picture": Decimal("0.20"),
        },
    )
    pair = _pair(_evaluate(_category_bundle(), config), "TV000003")

    assert pair.purchase_pool.level == "P3"
    assert pair.purchase_pool.confidence_level == "low"
    assert "market_reference_only_not_purchase_choice" in pair.limitations
    assert "no_shared_primary_task" in pair.limitations
    assert pair.relation_status == "not_evaluated"
    assert pair.competitor_member is False


def test_unknown_required_gate_never_serializes_missing_as_false() -> None:
    sparse = _pair(_evaluate(_category_bundle()), "TV000006")
    overlap_gate = next(
        gate
        for gate in sparse.purchase_pool.gate_results
        if gate.gate_code == "task_value_scene_overlap"
    )

    assert sparse.purchase_pool.level == "unknown"
    assert overlap_gate.known is False
    assert overlap_gate.passed is None
    assert overlap_gate.reason_code == "task_and_value_scene_sources_unknown"
    assert sparse.purchase_pool.confidence_level == "unknown"


def test_zero_or_missing_price_keeps_budget_gate_unknown() -> None:
    specs = _two_specs("TV", target_updates={"price": Decimal("0")})
    pair = _evaluate(_category_bundle(specs=specs)).pairs[0]
    gate = next(
        row
        for row in pair.purchase_pool.gate_results
        if row.gate_code == "budget_reachability"
    )

    assert pair.budget_band == "unknown"
    assert pair.purchase_pool.level == "unknown"
    assert gate.known is False
    assert gate.passed is None


@pytest.mark.parametrize(
    ("candidate_price", "expected_band"),
    [
        (Decimal("5750"), "same"),
        (Decimal("6750"), "adjacent"),
    ],
)
def test_budget_threshold_boundaries_are_inclusive(
    candidate_price: Decimal,
    expected_band: str,
) -> None:
    specs = _two_specs("TV", candidate_updates={"price": candidate_price})
    pair = _evaluate(_category_bundle(specs=specs)).pairs[0]

    assert pair.budget_band == expected_band
    gate = next(
        row
        for row in pair.purchase_pool.gate_results
        if row.gate_code == "budget_reachability"
    )
    assert gate.known is True
    assert gate.passed is True


def test_generic_table_stake_and_unknown_coverage_are_supporting_only() -> None:
    generic_pair = _evaluate(
        _category_bundle(),
        _config(
            generic=("picture",),
            discriminative=(),
            coverage={"picture": Decimal("0.20")},
        ),
    ).pairs[0]
    generic_picture = next(
        row
        for row in generic_pair.battlefield_overlap.assessments
        if row.battlefield_code == "picture"
    )
    assert generic_picture.classification == "generic"
    assert generic_picture.supports_purchase_pool_overlap is False
    assert generic_pair.purchase_pool.level == "P3"

    table_pair = _evaluate(
        _category_bundle(),
        _config(
            table_stake=("picture",),
            discriminative=(),
            coverage={"picture": Decimal("0.20")},
        ),
    ).pairs[0]
    table_picture = next(
        row
        for row in table_pair.battlefield_overlap.assessments
        if row.battlefield_code == "picture"
    )
    assert table_picture.classification == "table_stake"
    assert table_picture.supports_purchase_pool_overlap is False

    unknown_coverage = _evaluate(
        _category_bundle(),
        _config(discriminative=("picture",), coverage={}),
    ).pairs[0]
    unknown_picture = next(
        row
        for row in unknown_coverage.battlefield_overlap.assessments
        if row.battlefield_code == "picture"
    )
    assert unknown_picture.classification == "supporting"
    assert unknown_picture.classification_reason_code == (
        "coverage_unknown_not_discriminative"
    )
    assert unknown_picture.supports_purchase_pool_overlap is False

    coverage_generic = _evaluate(
        _category_bundle(),
        _config(
            discriminative=(),
            coverage={"picture": Decimal("0.85")},
        ),
    ).pairs[0]
    coverage_picture = next(
        row
        for row in coverage_generic.battlefield_overlap.assessments
        if row.battlefield_code == "picture"
    )
    assert coverage_picture.classification == "generic"
    assert coverage_picture.classification_reason_code == (
        "serving_scope_coverage_generic"
    )


def test_drag_requires_explicit_upstream_role_and_role_conflict_requires_review() -> (
    None
):
    bundle = _category_bundle()
    row = bundle.modules["M11D"].records_by_sku["TV000002"][0]
    row.facts["allocation_role"] = "drag_factor_battlefield"
    pair = _pair(_evaluate(bundle), "TV000002")
    picture = next(
        row
        for row in pair.battlefield_overlap.assessments
        if row.battlefield_code == "picture"
    )

    assert picture.explicit_drag is True
    assert picture.overlap_type == "role_conflict"
    assert picture.positive_overlap is False
    assert picture.review_required is True
    assert pair.battlefield_overlap.candidate_drag_codes == ["picture"]
    assert pair.review_required is True
    assert "battlefield_role_conflict_requires_review" in pair.review_reason_codes


def test_only_g15_relevant_review_and_evidence_are_carried_forward() -> None:
    bundle = _category_bundle()
    bundle.modules["M03B"].records_by_sku["TV000002"][0].facts["conflict_count"] = 1
    bundle.modules["M12D"].records_by_sku["TV000002"][0].facts["review_required"] = True
    pair = _pair(_evaluate(bundle), "TV000002")

    assert "candidate_m03b_conflict_count_positive" in pair.review_reason_codes
    assert all("m12d" not in reason for reason in pair.review_reason_codes)
    assert pair.review_required is True
    assert {ref.module_code for ref in pair.evidence_refs} <= {
        "M03B",
        "M07",
        "M09C",
        "M11C",
        "M11D",
        "M12C",
    }


def test_candidate_conservation_and_all_four_gates_hold_for_tv_and_ac() -> None:
    tv_features = _pair_features(_category_bundle())
    tv = PurchasePoolSemanticEvaluator().evaluate(tv_features, _config())
    assert tv.candidate_count == tv_features.candidate_count == 4
    assert [row.candidate.sku_code for row in tv.pairs] == [
        row.candidate.sku_code for row in tv_features.pairs
    ]
    assert all(len(row.purchase_pool.gate_results) == 4 for row in tv.pairs)

    ac_specs = _two_specs("AC")
    ac_features = _pair_features(_category_bundle("AC", ac_specs), "AC000001")
    ac = PurchasePoolSemanticEvaluator().evaluate(
        ac_features,
        _config(
            "AC",
            discriminative=("comfort",),
            coverage={"comfort": Decimal("0.20")},
        ),
    )
    assert ac.candidate_count == ac_features.candidate_count == 1
    assert ac.pairs[0].purchase_pool.level == "P0"


def test_input_order_is_stable_and_config_or_fact_changes_update_hash() -> None:
    first = _evaluate(_category_bundle())
    reordered = _evaluate(_category_bundle(reorder_semantic_values=True))
    assert reordered.result_hash == first.result_hash
    assert [row.result_hash for row in reordered.pairs] == [
        row.result_hash for row in first.pairs
    ]

    changed_config = _evaluate(
        _category_bundle(),
        _config(version="purchase-pool-test-v2"),
    )
    assert changed_config.result_hash != first.result_hash

    changed_bundle = _category_bundle()
    changed_bundle.modules["M11C"].records_by_sku["TV000002"][0].facts[
        "primary_battlefield_code"
    ] = "gaming"
    changed_fact = _evaluate(
        changed_bundle,
        _config(
            discriminative=("gaming", "picture"),
            coverage={"gaming": Decimal("0.20"), "picture": Decimal("0.20")},
        ),
    )
    assert changed_fact.result_hash != first.result_hash


def test_scope_and_schema_contradictions_fail_closed() -> None:
    features = _pair_features(_category_bundle())
    with pytest.raises(PurchasePoolEvaluationError, match="categories must match"):
        PurchasePoolSemanticEvaluator().evaluate(features, _config("AC"))

    with pytest.raises(ValidationError, match="cannot overlap"):
        _config(
            generic=("picture",),
            discriminative=("picture",),
        )

    direct = _pair(_evaluate(_category_bundle()), "TV000002")
    assessment = direct.battlefield_overlap.assessments[0]
    with pytest.raises(ValidationError, match="explicit upstream role"):
        BattlefieldCodeAssessment.model_validate(
            {
                **assessment.model_dump(mode="python"),
                "explicit_drag": not assessment.explicit_drag,
            }
        )

    payload = _evaluate(_category_bundle()).model_dump(mode="python")
    payload["candidate_count"] += 1
    with pytest.raises(ValidationError, match="candidate count"):
        PurchasePoolSemanticBundle.model_validate(payload)


def test_purchase_pool_evaluator_has_no_database_llm_or_relation_dependency() -> None:
    source = inspect.getsource(purchase_pool_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
    assert "direct_substitute" not in source
    assert "price_volume_pressure" not in source
