from __future__ import annotations

import json
from pathlib import Path
import time

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketCellRow,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    CounterfactualCandidate,
    SellpointValueV5Context,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_service import (
    build_market_synthetic_control,
    build_performance_archetypes,
)
from tests.core3_real_data.test_claim_value_pm_v5_counterfactuals import (
    _snapshot,
    _v5_context,
)


def _synthetic_candidate(donor_codes: list[str]) -> CounterfactualCandidate:
    return CounterfactualCandidate(
        method="market_synthetic",
        question="without_value_baseline",
        stage="recalled" if len(donor_codes) >= 5 else "rejected",
        candidate_key="market_synthetic:picture",
        candidate_sku_codes=donor_codes,
        provenance="market_universe_broad_recall",
        control_dimensions={"balanced": False},
        reject_reasons=([] if len(donor_codes) >= 5 else ["broad_donor_pool_insufficient"]),
        sample_manifest_hash="candidate-sample",
    )


def _synthetic_cells(
    donor_codes: list[str],
    *,
    donor_prices: list[float] | None = None,
) -> list[MarketCellRow]:
    prices = donor_prices or [5800, 5900, 6000, 6100, 6200][: len(donor_codes)]
    result = []
    for week in range(1, 9):
        for platform in ("jd", "tmall"):
            result.append(
                MarketCellRow(
                    sku_code="TARGET",
                    battlefield_code="BF_PREMIUM_PICTURE_UPGRADE",
                    period_week_index=week,
                    platform_type=platform,
                    avg_price=6000,
                    sales_volume=120,
                    sales_amount=720000,
                    value_bundle_tiers={"picture": "premium"},
                    price_check_status="ok",
                    promotion_suspect=False,
                    inventory_status="unavailable",
                )
            )
            for donor_code, price in zip(donor_codes, prices, strict=True):
                result.append(
                    MarketCellRow(
                        sku_code=donor_code,
                        battlefield_code="BF_PREMIUM_PICTURE_UPGRADE",
                        period_week_index=week,
                        platform_type=platform,
                        avg_price=price,
                        sales_volume=100,
                        sales_amount=price * 100,
                        value_bundle_tiers={"picture": "enhanced"},
                        price_check_status="ok",
                        promotion_suspect=False,
                        inventory_status="unavailable",
                    )
                )
    return result


def test_market_synthetic_recovers_stable_observational_difference() -> None:
    context = _v5_context()
    donors = [f"DONOR-{index}" for index in range(5)]
    result = build_market_synthetic_control(
        context,
        _synthetic_candidate(donors),
        bundle_code="picture",
        market_cells=_synthetic_cells(donors),
    )

    assert result.status == "available"
    assert result.causal_claim is False
    assert result.sales_difference is not None
    assert result.sales_difference.estimate == 20
    assert result.sales_difference.low == 20
    assert result.sales_difference.high == 20
    assert result.diagnostics.gate_pass is True
    assert result.diagnostics.leave_one_sign_consistency == 1
    assert result.diagnostics.placebo_percentile == 1
    assert result.effective_donor_count is not None
    assert result.effective_donor_count >= 3
    assert max(result.donor_weights.values()) <= 0.5
    assert "observational_not_causal" in result.limitations


def test_synthetic_donor_shortage_degrades_without_effect() -> None:
    context = _v5_context()
    donors = [f"DONOR-{index}" for index in range(3)]
    result = build_market_synthetic_control(
        context,
        _synthetic_candidate(donors),
        bundle_code="picture",
        market_cells=_synthetic_cells(donors),
    )

    assert result.status == "degraded"
    assert result.sales_difference is None
    assert result.donor_weights == {}
    assert "eligible_donor_count_insufficient" in result.diagnostics.failed_gates


def test_synthetic_outside_price_support_is_unidentifiable() -> None:
    context = _v5_context()
    donors = [f"DONOR-{index}" for index in range(5)]
    result = build_market_synthetic_control(
        context,
        _synthetic_candidate(donors),
        bundle_code="picture",
        market_cells=_synthetic_cells(donors, donor_prices=[5000] * 5),
    )

    assert result.status == "unidentifiable"
    assert result.sales_difference is None
    assert "target_outside_donor_price_support" in result.diagnostics.failed_gates


def test_synthetic_result_is_independent_of_cell_order() -> None:
    context = _v5_context()
    donors = [f"DONOR-{index}" for index in range(5)]
    cells = _synthetic_cells(donors)
    first = build_market_synthetic_control(
        context,
        _synthetic_candidate(donors),
        bundle_code="picture",
        market_cells=cells,
    )
    second = build_market_synthetic_control(
        context,
        _synthetic_candidate(list(reversed(donors))),
        bundle_code="picture",
        market_cells=list(reversed(cells)),
    )

    assert first.result_hash == second.result_hash
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_production_market_baseline_uses_full_window_weekly_averages() -> None:
    context = _v5_context()
    donors = [f"DONOR-{index}" for index in range(5)]

    result = build_market_synthetic_control(
        context,
        _synthetic_candidate(donors),
        bundle_code="picture",
    )

    assert result.status == "available"
    assert result.sales_difference is not None
    assert result.sales_difference.unit == "units_per_week"
    assert result.sales_difference.estimate == 41.666667
    assert result.diagnostics.common_week_count == 0
    assert result.diagnostics.common_platform_count == 0


def test_production_archetypes_split_small_pool_into_top_and_bottom_groups() -> None:
    result = build_performance_archetypes(
        _v5_context(),
        bundle_codes=["picture"],
    )

    assert [row.role for row in result] == ["high_performance", "low_performance"]
    assert [row.sku_count for row in result] == [3, 3]
    assert all(row.metric == "avg_weekly_sales_volume" for row in result)
    assert all(row.volume_interval is not None for row in result)


def _archetype_context_and_cells() -> tuple[SellpointValueV5Context, list[MarketCellRow]]:
    context = _v5_context()
    base = context.market_universe[0]
    snapshots = []
    cells = []
    for index in range(40):
        high = index < 20
        sku_code = f"ARCH-{index:02d}"
        snapshots.append(
            _snapshot(
                base,
                sku_code=sku_code,
                brand=f"品牌{index % 5}",
                price=5000,
                tier=3 if high else 1,
            )
        )
        for week in range(1, 13):
            for platform in ("jd", "tmall"):
                sales = 130 if high else 70
                cells.append(
                    MarketCellRow(
                        sku_code=sku_code,
                        battlefield_code="BF_PREMIUM_PICTURE_UPGRADE",
                        period_week_index=week,
                        platform_type=platform,
                        avg_price=5000,
                        sales_volume=sales,
                        sales_amount=5000 * sales,
                        value_bundle_tiers={"picture": "premium" if high else "absent"},
                        price_check_status="ok",
                        promotion_suspect=False,
                        inventory_status="unavailable",
                    )
                )
    payload = context.model_dump(mode="python")
    payload["market_universe"] = [
        context.v4_context.target_snapshot.model_dump(mode="python"),
        *(row.model_dump(mode="python") for row in snapshots),
    ]
    return SellpointValueV5Context(**payload), cells


def test_high_low_archetypes_use_controlled_residual_not_raw_bundle_amount() -> None:
    context, cells = _archetype_context_and_cells()
    started = time.perf_counter()
    result = build_performance_archetypes(
        context,
        bundle_codes=["picture"],
        market_cells=cells,
    )

    assert time.perf_counter() - started < 3
    assert [row.role for row in result] == ["high_performance", "low_performance"]
    high, low = result
    assert high.sku_count >= 10
    assert low.sku_count >= 10
    assert high.bundle_prevalence["picture"] == 1
    assert low.bundle_prevalence.get("picture", 0) == 0
    assert high.residual_interval is not None
    assert low.residual_interval is not None
    assert high.residual_interval.estimate > 0
    assert low.residual_interval.estimate < 0
    assert high.causal_claim is False
    assert "observational_bundle_archetype_not_causal" in high.limitations


def test_archetype_is_deterministic_and_degrades_small_population() -> None:
    context, cells = _archetype_context_and_cells()
    first = build_performance_archetypes(
        context,
        bundle_codes=["picture"],
        market_cells=cells,
    )
    second = build_performance_archetypes(
        context,
        bundle_codes=["picture"],
        market_cells=list(reversed(cells)),
    )

    assert [row.result_hash for row in first] == [row.result_hash for row in second]
    small = build_performance_archetypes(
        context,
        bundle_codes=["picture"],
        market_cells=cells[:100],
    )
    assert [row.role for row in small] == ["unstable"]
    assert small[0].bundle_prevalence == {}


def test_g01_c03_fixture_is_bound_to_market_reference_tests(repo_root: Path) -> None:
    manifest = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v5/G01_cohort_manifest.json"
        ).read_text(encoding="utf-8")
    )
    c03 = next(row for row in manifest["cohorts"] if row["cohort_id"] == "C03_SYNTHETIC_DONOR_RICH")

    assert c03["input_sha256"] == "781536cc1e2246255d3b16f1464b65eb1622dc045f32e527c2f5c7762f5c942d"
    assert len(c03["sku_codes"]) == 3


def test_g04_source_does_not_emit_strict_amount_or_causal_claim(repo_root: Path) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/claim_value_pm_v5_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "matched_equal_choice_price_gap",
        "psychological_max_price=True",
        "causal_claim=True",
        "estimated_price_premium_abs",
    ):
        assert forbidden not in source
