from __future__ import annotations

import json
from pathlib import Path

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketImpliedWtp,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldAllocation,
    IntervalEstimate,
    RealizationAccountingInput,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_realization import (
    build_bundle_price_interval,
    build_realization_accounting,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_service import (
    build_market_synthetic_control,
)
from tests.core3_real_data.test_claim_value_pm_v5_counterfactuals import (
    _v5_context,
)
from tests.core3_real_data.test_claim_value_pm_v5_market_reference import (
    _synthetic_candidate,
    _synthetic_cells,
)


def _available_synthetic():
    donors = [f"DONOR-{index}" for index in range(5)]
    return build_market_synthetic_control(
        _v5_context(),
        _synthetic_candidate(donors),
        bundle_code="picture",
        market_cells=_synthetic_cells(donors),
    )


def _allocation(code: str, weight: float, sales: float) -> BattlefieldAllocation:
    return BattlefieldAllocation(
        battlefield_code=code,
        allocated_sales_volume=sales,
        allocated_sales_amount=sales * 6000,
        allocation_weight=weight,
        incremental=False,
        source_lineage_hash=f"hash-{code}",
        lineage_status="aligned",
    )


def _available_wtp() -> MarketImpliedWtp:
    return MarketImpliedWtp(
        status="available",
        method="matched_equal_choice_price_gap",
        method_config_version="sellpoint_value_pm_v4_matched_wtp_config_v2",
        estimate_low=400,
        estimate_high=600,
        reference_price=5000,
        pair_count=2,
        model_family_count=2,
        sensitivity_summary={
            "leave_one_week_out": {"A": {"stable": True}, "B": {"stable": True}},
            "cluster_week_bootstrap": {"A": {"stable": True}, "B": {"stable": True}},
            "joint_crossing_stability": {"A": {"stable": True}, "B": {"stable": True}},
            "pair_quality_weights": {"A": 0.5, "B": 0.5},
            "weighted_median_center": 500,
            "conservative_interval_components": {"low": 400, "high": 600},
        },
        causal_claim=False,
        psychological_max_price=False,
    )


def _accounting_input(
    *,
    synthetic=True,
    cannibalization: IntervalEstimate | None = None,
    wtp: MarketImpliedWtp | None = None,
    current_sales: float = 120,
) -> RealizationAccountingInput:
    return RealizationAccountingInput(
        current_price=6000,
        current_sales_volume=current_sales,
        price_percentile=0.96,
        volume_percentile=0.13,
        amount_percentile=0.70,
        direct_and_pool_gaps=[{"peer": "A", "price_gap": 0.05}],
        own_price_curve={"status": "available", "observed_only": True},
        controlled_residual=None,
        choice_association={"status": "available", "same_price_advantage_pp": 2},
        synthetic_control=_available_synthetic() if synthetic else None,
        battlefield_allocations=[
            _allocation("BF_PICTURE", 0.5, 60),
            _allocation("BF_GAME", 0.3, 36),
            _allocation("BF_EYE", 0.2, 24),
        ],
        cannibalization=cannibalization,
        overlap_risk="medium",
        strict_market_wtp=wtp,
    )


def test_price_and_volume_realization_are_parallel_not_one_label() -> None:
    result = build_realization_accounting(_accounting_input(synthetic=False))

    assert result.price.market_position["price_percentile"] == 0.96
    assert result.volume.raw_market_position["volume_percentile"] == 0.13
    assert result.price.status == "available"
    assert result.volume.status == "available"
    assert result.volume.synthetic_difference is None
    assert result.price.strict_bundle_interval is not None
    assert result.price.strict_bundle_interval.estimate is None


def test_synthetic_difference_is_gross_but_not_net_without_cannibalization() -> None:
    result = build_realization_accounting(_accounting_input())

    assert result.increment.gross_status == "available"
    assert result.increment.gross is not None
    assert result.increment.gross.estimate == 20
    assert result.increment.cannibalization_status == "unidentifiable"
    assert result.increment.net_status == "unidentifiable"
    assert result.increment.net is None
    assert result.increment.claim_types == ["observational_gross"]
    assert result.increment.causal_claim is False


def test_net_uses_conservative_interval_arithmetic() -> None:
    cannibalization = IntervalEstimate(
        estimate=5,
        low=2,
        high=8,
        unit="sales_per_cell",
        observational=True,
    )
    result = build_realization_accounting(
        _accounting_input(cannibalization=cannibalization)
    )

    assert result.increment.net is not None
    assert result.increment.net.estimate == 15
    assert result.increment.net.low == 12
    assert result.increment.net.high == 18
    assert result.increment.claim_types == [
        "observational_gross",
        "observational_cannibalization",
        "observational_net",
    ]


def test_unit_mismatch_or_allocation_mismatch_never_fills_net() -> None:
    cannibalization = IntervalEstimate(
        estimate=5,
        low=2,
        high=8,
        unit="sales_per_week",
        observational=True,
    )
    result = build_realization_accounting(
        _accounting_input(cannibalization=cannibalization, current_sales=100)
    )

    assert result.increment.net is None
    assert "gross_cannibalization_unit_mismatch" in result.increment.limitations
    assert "m11d_allocation_total_mismatch" in result.limitations


def test_m11d_allocations_remain_current_sales_not_increment() -> None:
    result = build_realization_accounting(_accounting_input())

    assert sum(row.allocated_sales_volume or 0 for row in result.battlefield_allocations) == 120
    assert all(row.incremental is False for row in result.battlefield_allocations)
    assert "current_allocation" not in result.increment.claim_types


def test_strict_bundle_interval_only_wraps_v4_available_wtp() -> None:
    available = build_bundle_price_interval(_available_wtp())

    assert available.status == "available"
    assert available.estimate is not None
    assert available.estimate.estimate == 500
    assert available.estimate.low == 400
    assert available.estimate.high == 600
    assert available.pair_count == 2
    assert available.model_family_count == 2
    assert available.causal_claim is False
    assert available.psychological_max_price is False

    insufficient = MarketImpliedWtp(
        status="insufficient",
        method="none",
        method_config_version="sellpoint_value_pm_v4_matched_wtp_config_v2",
        pair_count=0,
        model_family_count=0,
        causal_claim=False,
        psychological_max_price=False,
    )
    unavailable = build_bundle_price_interval(insufficient)
    assert unavailable.status == "unidentifiable"
    assert unavailable.estimate is None
    assert unavailable.reference_price is None


def test_realization_accounting_is_deterministic() -> None:
    accounting = _accounting_input(wtp=_available_wtp())
    first = build_realization_accounting(accounting)
    second = build_realization_accounting(accounting)

    assert first.result_hash == second.result_hash
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_g01_65e7q_keeps_strict_amount_empty(repo_root: Path) -> None:
    fixture = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v5/G01_65E7Q_fixture.json"
        ).read_text(encoding="utf-8")
    )

    assert fixture["quantification_boundary"]["m11d_allocation_is_incremental"] is False
    assert fixture["quantification_boundary"]["synthetic_increment_allowed_now"] is False
    assert fixture["quantification_boundary"]["strict_amount_allowed_now"] is False


def test_g06_source_does_not_consume_legacy_amount_or_market_space_as_lift(
    repo_root: Path,
) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/claim_value_pm_v5_realization.py"
    ).read_text(encoding="utf-8")
    section = source.split("def build_realization_accounting", 1)[1]

    for forbidden in (
        "estimated_price_premium_abs",
        "weekly_sales_lift_abs",
        "estimated_sales_volume",
        "allocated_sales_volume *",
        "M12C",
    ):
        assert forbidden not in section
