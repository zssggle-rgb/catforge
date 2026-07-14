from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_value_substitution as value_substitution_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool import (
    PurchasePoolSemanticEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution import (
    ValueSubstitutionEvaluationError,
    ValueSubstitutionEvidenceEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionConfig,
    ValueSubstitutionEvidenceBundle,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)
from tests.core3_real_data.test_competitor_profile_purchase_pool import (
    _config as _purchase_pool_config,
)


def _config(
    category: str = "TV",
    *,
    generic: tuple[str, ...] = (),
    table_stake: tuple[str, ...] = (),
    discriminative: tuple[str, ...] = ("clear-picture",),
    coverage: dict[str, Decimal] | None = None,
    version: str = "value-substitution-test-v1",
) -> ValueSubstitutionConfig:
    values = coverage if coverage is not None else {"clear-picture": Decimal("0.20")}
    return ValueSubstitutionConfig(
        config_version=version,
        product_category=category,
        generic_coverage_threshold=Decimal("0.80"),
        generic_value_codes=sorted(generic),
        table_stake_value_codes=sorted(table_stake),
        discriminative_value_codes=sorted(discriminative),
        value_coverage_ratios={key: values[key] for key in sorted(values)},
        m12d_strong_roles=sorted(
            ["core_payment_anchor", "core_reason", "established_anchor"]
        ),
        m12d_supporting_roles=["supporting_anchor"],
        m12d_weak_roles=sorted(["proposition_anchor", "weak_expression_anchor"]),
        m12d_risk_roles=["risk_drag_anchor"],
        m12c_positive_roles=sorted(
            [
                "premium_driver_estimated",
                "sales_driver_estimated",
                "unique_payment_potential",
                "value_bundle_claim",
            ]
        ),
        m12c_supporting_roles=sorted(
            [
                "basic_threshold",
                "brand_claim_only",
                "user_validated_need",
                "weak_user_perception_claim",
            ]
        ),
        m12c_opportunity_roles=sorted(
            [
                "high_price_competitor_intercept",
                "opportunity_gap",
                "price_up_opportunity",
            ]
        ),
        m12c_risk_roles=["drag_factor"],
        m12c_unknown_roles=["sample_insufficient"],
    )


def _features(bundle, target: str = "TV000001"):
    pipeline = CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, target),
    )
    return PairFeatureBuilder().build(pipeline)


def _evaluate(
    bundle,
    config: ValueSubstitutionConfig | None = None,
    *,
    target: str = "TV000001",
    pool_config=None,
):
    features = _features(bundle, target)
    pool = PurchasePoolSemanticEvaluator().evaluate(
        features,
        pool_config or _purchase_pool_config(features.product_category),
    )
    result = ValueSubstitutionEvidenceEvaluator().evaluate(
        features,
        pool,
        config or _config(features.product_category),
    )
    return features, pool, result


def _pair(result: ValueSubstitutionEvidenceBundle, sku_code: str):
    return next(row for row in result.pairs if row.candidate.sku_code == sku_code)


def _value(pair, code: str):
    return next(row for row in pair.value_assessments if row.value_code == code)


def _layer(value, layer_code: str):
    return next(row for row in value.layers if row.layer_code == layer_code)


def _align_value_layers(
    bundle,
    sku_codes: tuple[str, ...],
    *,
    code: str,
    m12c_role: str = "value_bundle_claim",
) -> None:
    for sku_code in sku_codes:
        claim_value = bundle.modules["M12C"].records_by_sku[sku_code][0]
        claim_value.facts["claim_code"] = code
        claim_value.facts["claim_value_role"] = m12c_role
        bundle.modules["M05C"].records_by_sku[sku_code][0].facts.update(
            {"supported_claim_codes": [code]}
        )
        bundle.modules["M04C"].records_by_sku[sku_code][0].facts.update(
            {
                "claim_codes": [code],
                "supported_claim_codes": [code],
            }
        )


def test_shared_established_reason_and_two_value_layers_form_strong_evidence() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    _, _, result = _evaluate(bundle)
    direct = _pair(result, "TV000002")
    reason = next(
        row
        for row in direct.purchase_reason_assessments
        if row.reason_code == "clear-picture"
    )
    value = _value(direct, "clear-picture")

    assert reason.comparison_status == "shared_strong"
    assert reason.positive_overlap is True
    assert value.classification == "discriminative"
    assert set(value.matched_layer_codes) >= {
        "F1_purchase_reason",
        "F4_claim_value",
        "F4_user_realization",
        "F5_claim_expression",
    }
    assert set(value.matched_evidence_families) == {
        "F1_purchase_reason",
        "F4_user_realization",
        "F5_capability_expression",
    }
    assert direct.evidence_status == "strong_overlap"
    assert direct.shared_discriminative_value_codes == ["clear-picture"]
    assert direct.future_relation_support_possible is True
    assert direct.purchase_choice_conclusion_allowed is False
    assert direct.relation_status == "not_evaluated"


def test_same_code_different_established_roles_remains_exact_limited_comparison() -> (
    None
):
    bundle = _category_bundle()
    candidate = bundle.modules["M12D"].records_by_sku["TV000002"][0]
    candidate.facts["core_payment_anchors_json"] = []
    candidate.facts["established_anchors_json"] = [{"anchor_code": "clear-picture"}]
    _, _, result = _evaluate(bundle)
    reason = next(
        row
        for row in _pair(result, "TV000002").purchase_reason_assessments
        if row.reason_code == "clear-picture"
    )

    assert reason.target_roles == ["core_payment_anchor"]
    assert reason.candidate_roles == ["established_anchor"]
    assert reason.comparison_status == "shared_strong"
    assert reason.exact_code_match is True


@pytest.mark.parametrize(
    ("candidate_field", "expected_strength", "expected_status"),
    [
        ("weak_expression_anchors_json", "weak", "different_role"),
        ("risk_drag_anchors_json", "risk", "conflict"),
    ],
)
def test_weak_expression_and_risk_drag_never_become_positive_reason_overlap(
    candidate_field: str,
    expected_strength: str,
    expected_status: str,
) -> None:
    bundle = _category_bundle()
    candidate = bundle.modules["M12D"].records_by_sku["TV000002"][0]
    candidate.facts["core_payment_anchors_json"] = []
    candidate.facts[candidate_field] = [{"anchor_code": "clear-picture"}]
    _, _, result = _evaluate(bundle)
    pair = _pair(result, "TV000002")
    reason = next(
        row
        for row in pair.purchase_reason_assessments
        if row.reason_code == "clear-picture"
    )

    assert reason.candidate_strength == expected_strength
    assert reason.comparison_status == expected_status
    assert reason.positive_overlap is False
    if expected_strength == "risk":
        assert pair.evidence_status == "conflict"


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [
        ("premium_driver_estimated", "positive"),
        ("basic_threshold", "supporting"),
        ("brand_claim_only", "supporting"),
        ("drag_factor", "risk"),
        ("opportunity_gap", "weak"),
        ("sample_insufficient", "unknown"),
    ],
)
def test_m12c_roles_keep_positive_supporting_risk_opportunity_and_unknown_separate(
    role: str,
    expected_status: str,
) -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
        m12c_role=role,
    )
    _, _, result = _evaluate(bundle)
    layer = _layer(_value(_pair(result, "TV000002"), "clear-picture"), "F4_claim_value")

    assert layer.target_status == expected_status
    assert layer.candidate_status == expected_status


def test_user_realization_contradiction_is_conflict_not_value_overlap() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    candidate = bundle.modules["M05C"].records_by_sku["TV000002"][0]
    candidate.facts["supported_claim_codes"] = []
    candidate.facts["contradicted_claim_codes"] = ["clear-picture"]
    _, _, result = _evaluate(bundle)
    pair = _pair(result, "TV000002")
    layer = _layer(_value(pair, "clear-picture"), "F4_user_realization")

    assert layer.target_status == "positive"
    assert layer.candidate_status == "risk"
    assert layer.comparison_status == "conflict"
    assert pair.evidence_status == "conflict"
    assert pair.review_required is True


@pytest.mark.parametrize(
    ("config", "classification", "reason"),
    [
        (
            _config(generic=("clear-picture",), discriminative=()),
            "generic",
            "taxonomy_generic",
        ),
        (
            _config(table_stake=("clear-picture",), discriminative=()),
            "table_stake",
            "taxonomy_table_stake",
        ),
        (
            _config(
                discriminative=(),
                coverage={"clear-picture": Decimal("0.85")},
            ),
            "generic",
            "serving_scope_coverage_generic",
        ),
        (
            _config(discriminative=("clear-picture",), coverage={}),
            "supporting",
            "coverage_unknown_not_discriminative",
        ),
    ],
)
def test_generic_table_high_coverage_and_unknown_coverage_cannot_be_discriminative(
    config: ValueSubstitutionConfig,
    classification: str,
    reason: str,
) -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    _, _, result = _evaluate(bundle, config)
    pair = _pair(result, "TV000002")
    value = _value(pair, "clear-picture")

    assert value.classification == classification
    assert value.classification_reason_code == reason
    assert pair.shared_discriminative_value_codes == []
    assert pair.future_relation_support_possible is False


def test_p3_shared_value_is_research_only_and_never_purchase_choice() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000003"),
        code="dark-detail",
    )
    config = _config(
        discriminative=("dark-detail",),
        coverage={"dark-detail": Decimal("0.20")},
    )
    _, _, result = _evaluate(
        bundle,
        config,
        pool_config=_purchase_pool_config(
            discriminative=("gaming", "picture"),
            coverage={"gaming": Decimal("0.20"), "picture": Decimal("0.20")},
        ),
    )
    pair = _pair(result, "TV000003")

    assert pair.purchase_pool_level == "P3"
    assert pair.evidence_status == "strong_overlap"
    assert pair.value_research_allowed is True
    assert pair.purchase_choice_conclusion_allowed is False
    assert pair.business_boundary_code == (
        "value_research_only_purchase_choice_forbidden"
    )
    assert "purchase_pool_p3_reference_only" in pair.limitations


def test_sparse_candidate_is_unassessable_and_unknown_is_not_absent() -> None:
    _, _, result = _evaluate(_category_bundle())
    pair = _pair(result, "TV000006")
    value = _value(pair, "clear-picture")
    layer = _layer(value, "F1_purchase_reason")

    assert pair.purchase_pool_level == "unknown"
    assert pair.evidence_status == "unassessable"
    assert layer.target_status == "positive"
    assert layer.candidate_status == "unknown"
    assert layer.comparison_status == "unknown"


def test_same_lineage_across_modules_is_not_counted_as_two_families() -> None:
    bundle = _category_bundle()
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="clear-picture",
    )
    shared_hash = "sha256:test-shared-lineage:abc"
    for module_code in ("M12D", "M12C", "M05C", "M04C"):
        for sku_code in ("TV000001", "TV000002"):
            bundle.modules[module_code].records_by_sku[sku_code][
                0
            ].result_hash = shared_hash
    _, _, result = _evaluate(bundle)
    value = _value(_pair(result, "TV000002"), "clear-picture")

    assert value.matched_evidence_families == ["F1_purchase_reason"]
    assert _pair(result, "TV000002").evidence_status == "limited_overlap"


def test_candidate_conservation_pool_levels_tv_ac_and_hash_changes() -> None:
    features, pool, result = _evaluate(_category_bundle())
    assert (
        result.candidate_count == pool.candidate_count == features.candidate_count == 4
    )
    assert [row.candidate.sku_code for row in result.pairs] == [
        row.candidate.sku_code for row in features.pairs
    ]
    assert {row.purchase_pool_level for row in result.pairs} >= {
        "P0",
        "P1",
        "P3",
        "unknown",
    }

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
    ac_config = _config(
        "AC",
        discriminative=("reason-1",),
        coverage={"reason-1": Decimal("0.20")},
    )
    _, _, ac = _evaluate(
        _category_bundle("AC", [target, candidate]),
        ac_config,
        target="AC000001",
        pool_config=_purchase_pool_config(
            "AC",
            discriminative=("battlefield-1",),
            coverage={"battlefield-1": Decimal("0.20")},
        ),
    )
    assert ac.product_category == "AC"
    assert ac.candidate_count == 1

    changed = _evaluate(
        _category_bundle(),
        _config(version="value-substitution-test-v2"),
    )[2]
    assert changed.result_hash != result.result_hash


def test_input_order_scope_schema_and_no_db_llm_or_relation_generation() -> None:
    first_features, first_pool, first = _evaluate(_category_bundle())
    _, _, reordered = _evaluate(_category_bundle(reorder_semantic_values=True))
    assert reordered.result_hash == first.result_hash

    with pytest.raises(ValueSubstitutionEvaluationError, match="category"):
        ValueSubstitutionEvidenceEvaluator().evaluate(
            first_features,
            first_pool,
            _config("AC"),
        )

    with pytest.raises(ValidationError, match="M12C roles cannot overlap"):
        payload = _config().model_dump(mode="python")
        payload["m12c_risk_roles"] = [payload["m12c_positive_roles"][0]]
        ValueSubstitutionConfig.model_validate(payload)

    result_payload = first.model_dump(mode="python")
    result_payload["candidate_count"] += 1
    with pytest.raises(ValidationError, match="candidate count"):
        ValueSubstitutionEvidenceBundle.model_validate(result_payload)

    source = inspect.getsource(value_substitution_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
    assert "same_value_substitute" not in source
    assert "direct_substitute" not in source
