from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_price_volume_pressure as pressure_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure import (
    PriceVolumePressureEvaluationError,
    PriceVolumePressureEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureBundle,
    PriceVolumePressureConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool import (
    PurchasePoolSemanticEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution import (
    ValueSubstitutionEvidenceEvaluator,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)
from tests.core3_real_data.test_competitor_profile_purchase_pool import (
    _config as _pool_config,
)
from tests.core3_real_data.test_competitor_profile_value_substitution import (
    _config as _value_config,
)


def _config(
    category: str = "TV",
    *,
    version: str = "price-volume-test-v1",
) -> PriceVolumePressureConfig:
    return PriceVolumePressureConfig(
        config_version=version,
        product_category=category,
        same_budget_max_gap_ratio=Decimal("0.15"),
        adjacent_budget_max_gap_ratio=Decimal("0.35"),
        material_higher_volume_ratio=Decimal("1.10"),
        material_lower_volume_ratio=Decimal("0.90"),
    )


def _evaluate(
    bundle,
    *,
    target: str = "TV000001",
    config: PriceVolumePressureConfig | None = None,
    pool_config=None,
    value_config=None,
):
    pipeline = CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, target),
    )
    features = PairFeatureBuilder().build(pipeline)
    pool = PurchasePoolSemanticEvaluator().evaluate(
        features,
        pool_config or _pool_config(features.product_category),
    )
    value = ValueSubstitutionEvidenceEvaluator().evaluate(
        features,
        pool,
        value_config or _value_config(features.product_category),
    )
    pressure = PriceVolumePressureEvaluator().evaluate(
        features,
        pool,
        value,
        config or _config(features.product_category),
    )
    return features, pool, value, pressure


def _pair(result: PriceVolumePressureBundle, sku_code: str):
    return next(row for row in result.pairs if row.candidate.sku_code == sku_code)


def _two_specs(
    *,
    candidate_price: Decimal,
    candidate_volume: Decimal,
    different_route: bool = False,
    shared_reason: bool = True,
):
    target = _default_spec("TV", 1)
    candidate = _default_spec("TV", 2)
    target.update(
        {
            "brand": "海信",
            "price": Decimal("5000"),
            "weekly_volume": Decimal("100"),
            "task_primary": "cinema",
            "battlefield_primary": "picture",
            "purchase_reasons": ["reason-shared"],
            "claim_values": ["value-target"],
        }
    )
    candidate.update(
        {
            "brand": "TCL",
            "price": candidate_price,
            "weekly_volume": candidate_volume,
            "task_primary": "cinema",
            "battlefield_primary": "gaming" if different_route else "picture",
            "purchase_reasons": (
                ["reason-shared"] if shared_reason else ["reason-candidate"]
            ),
            "claim_values": (
                ["value-candidate"] if different_route else ["value-target"]
            ),
        }
    )
    return [target, candidate]


def _route_configs(category: str = "TV"):
    return (
        _pool_config(
            category,
            discriminative=("gaming", "picture"),
            coverage={"gaming": Decimal("0.20"), "picture": Decimal("0.20")},
        ),
        _value_config(
            category,
            discriminative=("reason-shared",),
            coverage={"reason-shared": Decimal("0.20")},
        ),
    )


def test_default_same_budget_higher_volume_is_direct_budget_pressure() -> None:
    _, _, _, result = _evaluate(_category_bundle())
    pair = _pair(result, "TV000002")

    assert pair.market_pattern == "same_budget_candidate_higher_volume"
    assert pair.pressure_direction == "direct_budget_pressure"
    assert pair.target_weighted_price == Decimal("5000")
    assert pair.candidate_weighted_price == Decimal("5100")
    assert pair.weekly_volume_ratio == Decimal("1.200000")
    assert pair.confidence_level == "high"
    assert {ref.module_code for ref in pair.evidence_refs} == {"M07"}
    assert pair.causal_claim is False
    assert pair.wtp_claim is False
    assert pair.price_change_sales_increment_claim is False
    assert pair.formal_relation_status == "not_evaluated"


@pytest.mark.parametrize(
    ("price", "volume", "expected_pattern"),
    [
        (Decimal("4000"), Decimal("150"), "lower_price_candidate_higher_volume"),
        (Decimal("6000"), Decimal("150"), "higher_price_candidate_higher_volume"),
        (Decimal("6000"), Decimal("70"), "higher_price_lower_volume"),
        (Decimal("4000"), Decimal("70"), "lower_price_lower_volume"),
        (Decimal("5200"), Decimal("105"), "volume_parity"),
    ],
)
def test_all_descriptive_price_volume_patterns(
    price: Decimal,
    volume: Decimal,
    expected_pattern: str,
) -> None:
    pool_config, value_config = _route_configs()
    specs = _two_specs(
        candidate_price=price,
        candidate_volume=volume,
        different_route=True,
    )
    _, _, _, result = _evaluate(
        _category_bundle(specs=specs),
        pool_config=pool_config,
        value_config=value_config,
    )

    assert result.pairs[0].market_pattern == expected_pattern


def test_lower_price_higher_volume_is_downtrade_market_pressure_not_causal_sales() -> (
    None
):
    pair = _pair(_evaluate(_category_bundle())[3], "TV000004")

    assert pair.market_pattern == "lower_price_candidate_higher_volume"
    assert pair.pressure_direction == "downtrade_volume_pressure"
    assert "descriptive_market_association_not_causal_increment" in pair.limitations
    assert pair.price_change_sales_increment_claim is False


def test_higher_price_higher_volume_with_shared_value_is_uptrade_acceptance() -> None:
    pool_config, value_config = _route_configs()
    specs = _two_specs(
        candidate_price=Decimal("6000"),
        candidate_volume=Decimal("150"),
        different_route=True,
        shared_reason=True,
    )
    pair = _evaluate(
        _category_bundle(specs=specs),
        pool_config=pool_config,
        value_config=value_config,
    )[3].pairs[0]

    assert pair.purchase_pool_level == "P1"
    assert pair.value_evidence_status == "limited_overlap"
    assert pair.market_pattern == "higher_price_candidate_higher_volume"
    assert pair.pressure_direction == "uptrade_market_acceptance"
    assert pair.wtp_claim is False


def test_same_budget_higher_volume_with_different_value_route_is_route_pressure() -> (
    None
):
    pool_config, value_config = _route_configs()
    specs = _two_specs(
        candidate_price=Decimal("5100"),
        candidate_volume=Decimal("150"),
        different_route=True,
        shared_reason=False,
    )
    pair = _evaluate(
        _category_bundle(specs=specs),
        pool_config=pool_config,
        value_config=value_config,
    )[3].pairs[0]

    assert pair.purchase_pool_level == "P1"
    assert pair.value_evidence_status == "different_route"
    assert pair.pressure_direction == "value_route_pressure"


def test_lower_price_lower_volume_never_claims_that_price_cut_would_raise_sales() -> (
    None
):
    pool_config, value_config = _route_configs()
    specs = _two_specs(
        candidate_price=Decimal("4000"),
        candidate_volume=Decimal("70"),
        different_route=True,
    )
    pair = _evaluate(
        _category_bundle(specs=specs),
        pool_config=pool_config,
        value_config=value_config,
    )[3].pairs[0]

    assert pair.market_pattern == "lower_price_lower_volume"
    assert pair.pressure_direction == "no_observed_pressure"
    assert "lower_price_did_not_show_higher_market_acceptance" in pair.limitations
    assert pair.price_change_sales_increment_claim is False


def test_p3_and_unknown_purchase_pools_are_reference_or_unassessable() -> None:
    result = _evaluate(_category_bundle())[3]
    p3 = _pair(result, "TV000003")
    unknown = _pair(result, "TV000006")

    assert p3.purchase_pool_level == "P3"
    assert p3.pressure_direction == "reference_only"
    assert unknown.purchase_pool_level == "unknown"
    assert unknown.pressure_direction == "unassessable"


@pytest.mark.parametrize(
    ("target_price", "target_volume", "candidate_price", "candidate_volume"),
    [
        (Decimal("0"), Decimal("100"), Decimal("5000"), Decimal("120")),
        (Decimal("5000"), Decimal("0"), Decimal("5100"), Decimal("120")),
        (Decimal("5000"), Decimal("100"), Decimal("5100"), Decimal("0")),
    ],
)
def test_zero_price_or_weekly_volume_is_explicitly_unassessable(
    target_price: Decimal,
    target_volume: Decimal,
    candidate_price: Decimal,
    candidate_volume: Decimal,
) -> None:
    specs = _two_specs(
        candidate_price=candidate_price,
        candidate_volume=candidate_volume,
    )
    specs[0]["price"] = target_price
    specs[0]["weekly_volume"] = target_volume
    pair = _evaluate(_category_bundle(specs=specs))[3].pairs[0]

    assert pair.market_pattern == "no_market_comparison"
    assert pair.pressure_direction == "unassessable"
    assert pair.confidence_level == "unknown"


def test_common_week_platform_and_percentiles_are_diagnostics_not_gates() -> None:
    bundle = _category_bundle()
    for sku_code in ("TV000001", "TV000002"):
        facts = bundle.modules["M07"].records_by_sku[sku_code][0].facts
        facts.update(
            {
                "common_week_count": 1,
                "common_platform_count": 1,
                "price_percentile": Decimal("0.60"),
                "sales_percentile": Decimal("0.70"),
            }
        )
    pair = _pair(_evaluate(bundle)[3], "TV000002")

    assert pair.pressure_direction == "direct_budget_pressure"
    assert pair.common_week_count == 1
    assert pair.common_platform_count == 1
    assert pair.target_price_percentile == Decimal("0.60")
    assert pair.candidate_volume_percentile == Decimal("0.70")
    assert pair.diagnostic_only_fields == [
        "common_platform_count_diagnostic_only",
        "common_week_count_diagnostic_only",
    ]


def test_m07_review_or_budget_config_mismatch_requires_review() -> None:
    bundle = _category_bundle()
    bundle.modules["M07"].records_by_sku["TV000002"][0].facts["conflict_count"] = 1
    reviewed = _pair(_evaluate(bundle)[3], "TV000002")
    assert reviewed.market_pattern == "review_required"
    assert reviewed.pressure_direction == "unassessable"
    assert reviewed.review_required is True

    narrow = _config().model_copy(update={"same_budget_max_gap_ratio": Decimal("0.01")})
    mismatch = _pair(_evaluate(_category_bundle(), config=narrow)[3], "TV000002")
    assert mismatch.review_required is True
    assert "purchase_pool_and_pressure_budget_band_mismatch" in (
        mismatch.review_reason_codes
    )


def test_candidate_conservation_tv_ac_hash_scope_and_no_db_llm_relation() -> None:
    features, pool, value, result = _evaluate(_category_bundle())
    assert result.candidate_count == features.candidate_count == 4
    assert [row.candidate.sku_code for row in result.pairs] == [
        row.candidate.sku_code for row in value.pairs
    ]

    target = _default_spec("AC", 1)
    candidate = _default_spec("AC", 2)
    candidate.update(
        {
            "task_primary": target["task_primary"],
            "battlefield_primary": target["battlefield_primary"],
            "purchase_reasons": target["purchase_reasons"],
            "claim_values": target["claim_values"],
            "weekly_volume": Decimal("150"),
        }
    )
    ac = _evaluate(
        _category_bundle("AC", [target, candidate]),
        target="AC000001",
        config=_config("AC"),
        pool_config=_pool_config(
            "AC",
            discriminative=("battlefield-1",),
            coverage={"battlefield-1": Decimal("0.20")},
        ),
        value_config=_value_config(
            "AC",
            discriminative=("reason-1",),
            coverage={"reason-1": Decimal("0.20")},
        ),
    )[3]
    assert ac.product_category == "AC"
    assert ac.candidate_count == 1

    changed = _evaluate(
        _category_bundle(),
        config=_config(version="price-volume-test-v2"),
    )[3]
    assert changed.result_hash != result.result_hash

    with pytest.raises(PriceVolumePressureEvaluationError, match="category"):
        PriceVolumePressureEvaluator().evaluate(
            features,
            pool,
            value,
            _config("AC"),
        )

    with pytest.raises(ValidationError, match="candidate count"):
        payload = result.model_dump(mode="python")
        payload["candidate_count"] += 1
        PriceVolumePressureBundle.model_validate(payload)

    source = inspect.getsource(pressure_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
    assert "direct_substitute" not in source
    assert "same_value_substitute" not in source
