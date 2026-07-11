"""Independent price, volume, allocation, and increment accounts for V5."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketImpliedWtp,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BundlePriceInterval,
    IncrementDecomposition,
    IntervalEstimate,
    PriceRealization,
    RealizationAccountingInput,
    RealizationAccountingResult,
    VolumeRealization,
)


def build_realization_accounting(
    accounting: RealizationAccountingInput,
) -> RealizationAccountingResult:
    """Build five independent value-realization accounts without cross-fill."""

    strict_interval = build_bundle_price_interval(accounting.strict_market_wtp)
    price_limitations = list(accounting.limitations)
    if strict_interval.status != "available":
        price_limitations.append("strict_bundle_price_interval_unavailable")
    price = PriceRealization(
        status="available" if accounting.current_price is not None else "unidentifiable",
        current_price=accounting.current_price,
        market_position={
            "price_percentile": accounting.price_percentile,
            "amount_percentile": accounting.amount_percentile,
        },
        direct_and_pool_gaps=accounting.direct_and_pool_gaps,
        own_price_curve=accounting.own_price_curve,
        strict_bundle_interval=strict_interval,
        limitations=sorted(set(price_limitations)),
    )

    synthetic_sales = (
        accounting.synthetic_control.sales_difference
        if accounting.synthetic_control is not None
        and accounting.synthetic_control.status == "available"
        else None
    )
    volume_available = any(
        value is not None
        for value in (
            accounting.volume_percentile,
            accounting.controlled_residual,
            synthetic_sales,
            accounting.choice_association,
        )
    )
    volume_limitations = list(accounting.limitations)
    if accounting.synthetic_control is not None:
        volume_limitations.extend(accounting.synthetic_control.limitations)
    volume = VolumeRealization(
        status="available" if volume_available else "unidentifiable",
        raw_market_position={
            "volume_percentile": accounting.volume_percentile,
            "amount_percentile": accounting.amount_percentile,
        },
        controlled_residual=accounting.controlled_residual,
        synthetic_difference=synthetic_sales,
        choice_association=accounting.choice_association,
        limitations=sorted(set(volume_limitations)),
    )

    increment = _increment_decomposition(accounting)
    limitations = list(accounting.limitations)
    allocated_total = sum(
        row.allocated_sales_volume or 0 for row in accounting.battlefield_allocations
    )
    if (
        accounting.current_sales_volume is not None
        and accounting.battlefield_allocations
        and abs(allocated_total - accounting.current_sales_volume)
        > max(1e-6, abs(accounting.current_sales_volume) * 0.01)
    ):
        limitations.append("m11d_allocation_total_mismatch")
    payload = {
        "price": price.model_dump(mode="json"),
        "volume": volume.model_dump(mode="json"),
        "allocations": [
            row.model_dump(mode="json") for row in accounting.battlefield_allocations
        ],
        "increment": increment.model_dump(mode="json"),
        "limitations": sorted(set(limitations)),
    }
    return RealizationAccountingResult(
        price=price,
        volume=volume,
        battlefield_allocations=accounting.battlefield_allocations,
        increment=increment,
        limitations=sorted(set(limitations)),
        result_hash=_canonical_hash(payload),
    )


def build_bundle_price_interval(wtp: MarketImpliedWtp | None) -> BundlePriceInterval:
    """Wrap only a V4 amount that already passed the full strict contract."""

    config_version = (
        wtp.method_config_version
        if wtp is not None
        else "sellpoint_value_pm_v4_matched_wtp_config_v2"
    )
    if wtp is None or wtp.status != "available":
        status = (
            "blocked"
            if wtp is not None and wtp.status == "blocked"
            else "unidentifiable"
        )
        return BundlePriceInterval(
            status=status,
            method="none",
            estimate=None,
            reference_price=None,
            pair_count=wtp.pair_count if wtp is not None else 0,
            model_family_count=wtp.model_family_count if wtp is not None else 0,
            gate_results={},
            limitations=sorted(
                set(
                    ["v4_strict_amount_gate_not_passed"]
                    + (list(wtp.exclusion_reasons) if wtp is not None else [])
                )
            ),
            causal_claim=False,
            psychological_max_price=False,
            method_config_version=config_version,
        )
    center = wtp.sensitivity_summary.get("weighted_median_center")
    if not isinstance(center, (int, float)):
        center = (float(wtp.estimate_low) + float(wtp.estimate_high)) / 2
    estimate = IntervalEstimate(
        estimate=float(center),
        low=float(wtp.estimate_low),
        high=float(wtp.estimate_high),
        unit="CNY",
        observational=True,
        currency=wtp.currency,
    )
    return BundlePriceInterval(
        status="available",
        method="matched_equal_choice_price_gap",
        estimate=estimate,
        reference_price=wtp.reference_price,
        pair_count=wtp.pair_count,
        model_family_count=wtp.model_family_count,
        gate_results={
            "v4_schema_gate": True,
            "base_counterfactual_gate": True,
            "independent_variation_gate": True,
            "price_choice_stability_gate": True,
            "non_extrapolation_gate": True,
        },
        limitations=[
            "historical_market_implied_not_psychological_max_price",
            "observational_not_causal",
        ],
        causal_claim=False,
        psychological_max_price=False,
        method_config_version=config_version,
    )


def _increment_decomposition(
    accounting: RealizationAccountingInput,
) -> IncrementDecomposition:
    synthetic = accounting.synthetic_control
    gross = (
        synthetic.sales_difference
        if synthetic is not None and synthetic.status == "available"
        else None
    )
    gross_status = "available" if gross is not None else "unidentifiable"
    cannibalization = accounting.cannibalization
    cannibalization_status = (
        "available" if cannibalization is not None else "unidentifiable"
    )
    limitations = []
    if synthetic is not None:
        limitations.extend(synthetic.limitations)
    if gross is None:
        limitations.append("observational_gross_unavailable")
    if cannibalization is None:
        limitations.append("cannibalization_quantity_unavailable")
    net = None
    if gross is not None and cannibalization is not None:
        if gross.unit != cannibalization.unit:
            limitations.append("gross_cannibalization_unit_mismatch")
        else:
            net = IntervalEstimate(
                estimate=float(gross.estimate) - float(cannibalization.estimate),
                low=float(gross.low) - float(cannibalization.high),
                high=float(gross.high) - float(cannibalization.low),
                unit=gross.unit,
                observational=True,
                currency=gross.currency,
            )
    claim_types: list[
        Literal[
            "observational_gross",
            "observational_cannibalization",
            "observational_net",
        ]
    ] = []
    if gross is not None:
        claim_types.append("observational_gross")
    if cannibalization is not None:
        claim_types.append("observational_cannibalization")
    if net is not None:
        claim_types.append("observational_net")
    return IncrementDecomposition(
        gross_status=gross_status,
        cannibalization_status=cannibalization_status,
        net_status="available" if net is not None else "unidentifiable",
        gross=gross,
        cannibalization=cannibalization,
        net=net,
        claim_types=claim_types,
        overlap_risk=accounting.overlap_risk,
        limitations=sorted(set(limitations)),
        causal_claim=False,
    )


def _canonical_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


__all__ = ["build_bundle_price_interval", "build_realization_accounting"]
