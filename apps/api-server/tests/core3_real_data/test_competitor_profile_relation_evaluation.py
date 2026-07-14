from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_relation_evaluation as relation_module,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation import (
    CompetitorRelationEvaluationError,
    CompetitorRelationEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationConfig,
    CompetitorRelationEvaluationBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceFamilyAssessment,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
)
from tests.core3_real_data.test_competitor_profile_price_volume_pressure import (
    _evaluate as _pressure_chain,
    _route_configs,
    _two_specs,
)
from tests.core3_real_data.test_competitor_profile_value_substitution import (
    _align_value_layers,
    _config as _value_config,
)


def _config(
    category: str = "TV",
    *,
    version: str = "relation-test-v1",
) -> CompetitorRelationConfig:
    return CompetitorRelationConfig(
        config_version=version,
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


def _evaluate(
    bundle,
    *,
    target: str = "TV000001",
    config: CompetitorRelationConfig | None = None,
    pool_config=None,
    value_config=None,
):
    features, pool, value, pressure = _pressure_chain(
        bundle,
        target=target,
        pool_config=pool_config,
        value_config=value_config,
    )
    result = CompetitorRelationEvaluator().evaluate(
        features,
        pool,
        value,
        pressure,
        config or _config(features.product_category),
    )
    return features, pool, value, pressure, result


def _pair(result: CompetitorRelationEvaluationBundle, sku_code: str):
    return next(row for row in result.pairs if row.candidate.sku_code == sku_code)


def _relation(pair, code: str):
    return next(row for row in pair.relation_assessments if row.relation_code == code)


def _question(pair, code: str):
    return next(row for row in pair.question_eligibility if row.question_code == code)


def test_direct_and_same_value_pass_with_two_independent_families_and_layers() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    pair = _pair(_evaluate(bundle)[4], "TV000002")

    assert _relation(pair, "direct_substitute").status == "passed"
    assert _relation(pair, "same_value_substitute").status == "passed"
    assert pair.candidate_status == "eligible"
    assert pair.competitor_member is True
    assert pair.primary_relation_code == "direct_substitute"
    direct = _relation(pair, "direct_substitute")
    assert direct.is_primary is True
    assert direct.confidence_level == "high"
    assert direct.evidence_refs
    assert all(gate.reason_code and gate.evidence_refs for gate in direct.gate_results)
    assert len(pair.relation_assessments) == 7
    assert len(pair.evidence_family_assessments) == 5
    assert len(pair.question_eligibility) == 8


def test_weak_expression_caps_direct_relation_at_limited_not_absent() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    reason = bundle.modules["M12D"].records_by_sku["TV000002"][0]
    reason.facts["core_payment_anchors_json"] = []
    reason.facts["weak_expression_anchors_json"] = [{"anchor_code": "clear-picture"}]
    pair = _pair(_evaluate(bundle)[4], "TV000002")
    direct = _relation(pair, "direct_substitute")

    assert direct.status == "limited"
    assert "relation_evidence_limited" in direct.limitations
    assert pair.candidate_status == "eligible"
    assert any(
        row.status == "passed" and row.relation_code != "direct_substitute"
        for row in pair.relation_assessments
    )


def test_same_budget_relation_passes_for_same_task_and_different_value_route() -> None:
    pool_config, value_config = _route_configs()
    specs = _two_specs(
        candidate_price=Decimal("5100"),
        candidate_volume=Decimal("150"),
        different_route=True,
        shared_reason=False,
    )
    specs[1]["audience_primary"] = specs[0]["audience_primary"]
    pair = _evaluate(
        _category_bundle(specs=specs),
        pool_config=pool_config,
        value_config=value_config,
    )[4].pairs[0]

    assert pair.candidate_status == "eligible"
    same_budget = _relation(pair, "same_budget_alternative")
    assert same_budget.status == "passed"
    assert same_budget.confidence_level == "medium"
    assert _question(pair, "purchase_choice").availability == "eligible"


def test_default_downtrade_passes_only_with_price_value_capability_and_volume() -> None:
    specs = _two_specs(
        candidate_price=Decimal("4000"),
        candidate_volume=Decimal("180"),
    )
    for spec in specs:
        spec["purchase_reasons"] = ["clear-picture"]
        spec["claim_values"] = ["clear-picture"]
    bundle = _category_bundle(specs=specs)
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    pair = _evaluate(bundle)[4].pairs[0]
    relation = _relation(pair, "downtrade_diversion")

    assert relation.status == "passed"
    assert relation.business_effect["strong_pressure"] is True
    assert relation.business_effect["causal_claim"] is False
    assert _question(pair, "price_ladder_defense").availability == "eligible"


def test_uptrade_passes_with_two_candidate_stronger_families_and_market_acceptance() -> (
    None
):
    pool_config, _ = _route_configs()
    specs = _two_specs(
        candidate_price=Decimal("6000"),
        candidate_volume=Decimal("150"),
        different_route=True,
        shared_reason=False,
    )
    specs[0]["purchase_reasons"] = ["target-value"]
    specs[0]["claim_values"] = ["target-value"]
    specs[1]["purchase_reasons"] = ["candidate-value"]
    specs[1]["claim_values"] = ["candidate-value"]
    bundle = _category_bundle(specs=specs)
    _align_value_layers(bundle, ("TV000002",), code="candidate-value")
    value_config = _value_config(
        discriminative=("candidate-value",),
        coverage={"candidate-value": Decimal("0.20")},
    )
    pair = _evaluate(
        bundle,
        pool_config=pool_config,
        value_config=value_config,
    )[4].pairs[0]

    assert _relation(pair, "uptrade_alternative").status == "passed"
    assert _question(pair, "price_ladder_defense").availability == "eligible"


def test_same_brand_requires_ladder_entry_and_semantic_family_not_brand_alone() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000003"),
        code="dark-detail",
    )
    value_config = _value_config(
        discriminative=("dark-detail",),
        coverage={"dark-detail": Decimal("0.20")},
    )
    result = _evaluate(bundle, value_config=value_config)[4]
    same_brand = _pair(result, "TV000003")
    assert _relation(same_brand, "same_brand_ladder").status == "passed"
    assert _question(same_brand, "same_brand_portfolio_role").availability == (
        "eligible"
    )

    specs = _two_specs(
        candidate_price=Decimal("9000"),
        candidate_volume=Decimal("100"),
        different_route=True,
        shared_reason=False,
    )
    specs[1]["brand"] = specs[0]["brand"]
    far = _evaluate(_category_bundle(specs=specs))[4]
    assert far.candidate_count == 0 or all(
        _relation(pair, "same_brand_ladder").status != "passed" for pair in far.pairs
    )


def test_scenario_relation_passes_for_p2_f2_and_second_semantic_family() -> None:
    specs = _two_specs(
        candidate_price=Decimal("5100"),
        candidate_volume=Decimal("120"),
        different_route=False,
        shared_reason=True,
    )
    specs[1]["screen_size"] = Decimal("75")
    specs[1]["size_segment"] = "75"
    bundle = _category_bundle(specs=specs)
    pool_config, value_config = _route_configs()
    pair = _evaluate(
        bundle,
        pool_config=pool_config,
        value_config=value_config,
    )[4].pairs[0]

    assert pair.relation_assessments
    assert _relation(pair, "scenario_substitute").status == "passed"
    assert _question(pair, "scenario_solution").availability == "eligible"


def test_p3_same_value_can_support_value_research_but_not_purchase_choice() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000003"),
        code="dark-detail",
    )
    value_config = _value_config(
        discriminative=("dark-detail",),
        coverage={"dark-detail": Decimal("0.20")},
    )
    pair = _pair(
        _evaluate(bundle, value_config=value_config)[4],
        "TV000003",
    )

    assert pair.primary_relation_code in {
        "same_brand_ladder",
        "same_value_substitute",
    }
    assert _relation(pair, "same_value_substitute").status == "limited"
    assert _question(pair, "purchase_choice").availability == "unavailable"
    assert _question(pair, "purchase_choice").business_boundary_code == (
        "p3_value_research_not_purchase_choice"
    )
    assert _question(pair, "value_substitution").availability in {
        "eligible",
        "limited",
    }


def test_p3_same_value_is_a_limited_candidate_when_no_other_relation_passes() -> None:
    specs = _two_specs(
        candidate_price=Decimal("7000"),
        candidate_volume=Decimal("100"),
    )
    bundle = _category_bundle(specs=specs)
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="reason-shared",
    )
    value_config = _value_config(
        discriminative=("reason-shared",),
        coverage={"reason-shared": Decimal("0.20")},
    )
    pair = _evaluate(bundle, value_config=value_config)[4].pairs[0]

    assert pair.candidate_status == "limited"
    assert pair.primary_relation_code == "same_value_substitute"
    assert _relation(pair, "same_value_substitute").status == "limited"
    assert _question(pair, "purchase_choice").availability == "unavailable"


@pytest.mark.parametrize(
    ("price", "expected_status"),
    [
        (Decimal("4600"), "passed"),
        (Decimal("4601"), "failed"),
    ],
)
def test_downtrade_price_gap_boundary_is_inclusive_at_eight_percent(
    price: Decimal,
    expected_status: str,
) -> None:
    specs = _two_specs(candidate_price=price, candidate_volume=Decimal("130"))
    for spec in specs:
        spec["purchase_reasons"] = ["clear-picture"]
        spec["claim_values"] = ["clear-picture"]
    bundle = _category_bundle(specs=specs)
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )

    assert (
        _relation(
            _evaluate(bundle)[4].pairs[0],
            "downtrade_diversion",
        ).status
        == expected_status
    )


@pytest.mark.parametrize(
    ("price", "expected_status"),
    [
        (Decimal("5400"), "passed"),
        (Decimal("5399"), "failed"),
    ],
)
def test_uptrade_price_gap_boundary_is_inclusive_at_eight_percent(
    price: Decimal,
    expected_status: str,
) -> None:
    pool_config, _ = _route_configs()
    specs = _two_specs(
        candidate_price=price,
        candidate_volume=Decimal("150"),
        different_route=True,
        shared_reason=False,
    )
    specs[0]["purchase_reasons"] = ["target-value"]
    specs[0]["claim_values"] = ["target-value"]
    specs[1]["purchase_reasons"] = ["candidate-value"]
    specs[1]["claim_values"] = ["candidate-value"]
    bundle = _category_bundle(specs=specs)
    _align_value_layers(bundle, ("TV000002",), code="candidate-value")
    value_config = _value_config(
        discriminative=("candidate-value",),
        coverage={"candidate-value": Decimal("0.20")},
    )

    assert (
        _relation(
            _evaluate(
                bundle,
                pool_config=pool_config,
                value_config=value_config,
            )[4].pairs[0],
            "uptrade_alternative",
        ).status
        == expected_status
    )


@pytest.mark.parametrize(
    ("price", "strong_pressure"),
    [
        (Decimal("4250"), True),
        (Decimal("4251"), False),
    ],
)
def test_strong_downtrade_marker_is_inclusive_at_fifteen_percent(
    price: Decimal,
    strong_pressure: bool,
) -> None:
    specs = _two_specs(candidate_price=price, candidate_volume=Decimal("125"))
    for spec in specs:
        spec["purchase_reasons"] = ["clear-picture"]
        spec["claim_values"] = ["clear-picture"]
    bundle = _category_bundle(specs=specs)
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    relation = _relation(
        _evaluate(bundle)[4].pairs[0],
        "downtrade_diversion",
    )

    assert relation.status == "passed"
    assert relation.business_effect["strong_pressure"] is strong_pressure


def test_generic_value_and_f5_support_cannot_form_a_formal_relation() -> None:
    specs = _two_specs(
        candidate_price=Decimal("5100"),
        candidate_volume=Decimal("120"),
    )
    for spec in specs:
        spec["purchase_reasons"] = ["generic-value"]
        spec["claim_values"] = ["generic-value"]
    bundle = _category_bundle(specs=specs)
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="generic-value",
    )
    value_config = _value_config(
        generic=("generic-value",),
        discriminative=(),
        coverage={"generic-value": Decimal("0.90")},
    )
    pair = _evaluate(bundle, value_config=value_config)[4].pairs[0]

    direct = _relation(pair, "direct_substitute")
    assert direct.status == "failed"
    assert "F5_capability_expression" not in direct.supporting_evidence_families
    assert _relation(pair, "same_value_substitute").status == "failed"
    assert not any(
        row.status in {"passed", "limited"} for row in pair.relation_assessments
    )


def test_independent_family_count_deduplicates_lineage_and_never_counts_f5() -> None:
    families = [
        EvidenceFamilyAssessment(
            family="F1_purchase_reason",
            status="discriminative",
            matched_codes=["value-a"],
            independent_lineage_keys=["shared-lineage"],
            confidence_level="high",
        ),
        EvidenceFamilyAssessment(
            family="F4_user_realization",
            status="discriminative",
            matched_codes=["value-a"],
            independent_lineage_keys=["shared-lineage"],
            confidence_level="high",
        ),
        EvidenceFamilyAssessment(
            family="F2_task_value_scene",
            status="missing",
            confidence_level="unknown",
        ),
        EvidenceFamilyAssessment(
            family="F3_audience_need",
            status="missing",
            confidence_level="unknown",
        ),
        EvidenceFamilyAssessment(
            family="F5_capability_expression",
            status="supporting",
            matched_codes=["parameter-a"],
            independent_lineage_keys=["different-lineage"],
            confidence_level="medium",
        ),
    ]

    assert relation_module._independent_formal_families(families) == [
        "F1_purchase_reason"
    ]


def test_explicit_failure_unknown_and_review_are_not_collapsed() -> None:
    result = _evaluate(_category_bundle())[4]
    direct = _pair(result, "TV000002")
    low_evidence = _pair(result, "TV000003")
    sparse = _pair(result, "TV000006")
    assert _relation(direct, "uptrade_alternative").status == "failed"
    assert _relation(low_evidence, "same_brand_ladder").status == "review_required"
    assert _relation(low_evidence, "same_brand_ladder").confidence_level == "low"
    assert low_evidence.candidate_status == "review_required"
    assert low_evidence.review_required is True
    assert _relation(sparse, "direct_substitute").status == "unassessable"
    assert sparse.candidate_status == "reference_only"
    assert sparse.competitor_member is False
    assert not any(
        row.status in {"passed", "limited"}
        for row in sparse.relation_assessments
    )

    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    bundle.modules["M05C"].records_by_sku["TV000002"][0].facts[
        "supported_claim_codes"
    ] = []
    bundle.modules["M05C"].records_by_sku["TV000002"][0].facts[
        "contradicted_claim_codes"
    ] = ["clear-picture"]
    reviewed = _pair(_evaluate(bundle)[4], "TV000002")
    assert reviewed.candidate_status == "review_required"
    assert all(row.status == "review_required" for row in reviewed.relation_assessments)


def test_question_eligibility_keeps_configuration_and_causal_boundaries_separate() -> (
    None
):
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    target_claim = bundle.modules["M04C"].records_by_sku["TV000001"][0]
    candidate_claim = bundle.modules["M04C"].records_by_sku["TV000002"][0]
    target_claim.facts["claim_codes"] = []
    target_claim.facts["supported_claim_codes"] = ["clear-picture"]
    candidate_claim.facts["claim_codes"] = ["clear-picture"]
    candidate_claim.facts["supported_claim_codes"] = []
    pair = _pair(_evaluate(bundle)[4], "TV000002")

    assert _question(pair, "configuration_follow").availability == "eligible"
    assert _question(pair, "price_volume_pressure").business_boundary_code == (
        "causal_sales_increment_forbidden"
    )
    assert _question(pair, "value_substitution").business_boundary_code == (
        "single_claim_causal_wtp_forbidden"
    )
    assert pair.causal_claim is False
    assert pair.wtp_claim is False
    assert pair.price_change_sales_increment_claim is False
    assert pair.selection_status == "not_evaluated"


def test_candidate_conservation_tv_ac_config_hash_scope_schema_and_no_db_llm() -> None:
    features, _, _, _, result = _evaluate(_category_bundle())
    assert result.candidate_count == features.candidate_count == 4
    assert [row.candidate.sku_code for row in result.pairs] == [
        row.candidate.sku_code for row in features.pairs
    ]
    reordered = _evaluate(_category_bundle(reorder_semantic_values=True))[4]
    assert reordered.input_fingerprint == result.input_fingerprint
    assert reordered.result_hash == result.result_hash

    target = _default_spec("AC", 1)
    candidate = _default_spec("AC", 2)
    candidate.update(
        {
            "task_primary": target["task_primary"],
            "battlefield_primary": target["battlefield_primary"],
            "purchase_reasons": target["purchase_reasons"],
            "claim_values": target["claim_values"],
        }
    )
    ac = _evaluate(
        _category_bundle("AC", [target, candidate]),
        target="AC000001",
        config=_config("AC"),
    )[4]
    assert ac.product_category == "AC"
    assert ac.candidate_count == 1

    changed = _evaluate(
        _category_bundle(),
        config=_config(version="relation-test-v2"),
    )[4]
    assert changed.result_hash != result.result_hash

    changed_bundle = _category_bundle()
    changed_bundle.modules["M10C"].records_by_sku["TV000002"][0].facts[
        "primary_target_group_code"
    ] = "new-audience"
    fact_changed = _evaluate(changed_bundle)[4]
    assert fact_changed.input_fingerprint != result.input_fingerprint
    assert fact_changed.result_hash != result.result_hash

    with pytest.raises(CompetitorRelationEvaluationError, match="category"):
        upstream = _pressure_chain(_category_bundle())
        CompetitorRelationEvaluator().evaluate(*upstream, _config("AC"))

    with pytest.raises(ValidationError, match="candidate count"):
        payload = result.model_dump(mode="python")
        payload["candidate_count"] += 1
        CompetitorRelationEvaluationBundle.model_validate(payload)

    source = inspect.getsource(relation_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
    assert "top 3" not in source
    assert "selected = true" not in source
