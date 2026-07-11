"""Observational market references for sellpoint-value V5.

The functions in this module are deterministic and side-effect free.  Market
synthetic results are descriptive controls, never causal estimates.  High/low
archetypes describe bundle prevalence after a cross-fitted market baseline and
never allocate an amount to an individual sellpoint.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import hashlib
import json
import math
from typing import Any

import numpy as np

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketCellRow,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BalanceMetric,
    BattlefieldPortfolioInput,
    BattlefieldPortfolioOption,
    CounterfactualCandidate,
    ExpansionEligibility,
    IntervalEstimate,
    PerformanceArchetype,
    SellpointValueV5Context,
    SyntheticControlResult,
    SyntheticDiagnostics,
)


SYNTHETIC_CONFIG_VERSION = "sellpoint_value_pm_v5_synthetic_control_v1"
ARCHETYPE_CONFIG_VERSION = "sellpoint_value_pm_v5_performance_archetype_v1"
EXPANSION_CONFIG_VERSION = "sellpoint_value_pm_v5_expansion_gate_v1"
MIN_DONORS = 5
MIN_EFFECTIVE_DONORS = 3.0
MAX_DONOR_WEIGHT = 0.50
MIN_COMMON_WEEKS = 8
MIN_COMMON_PLATFORMS = 2
BALANCED_SMD = 0.10
FAILED_SMD = 0.20
MIN_LEAVE_ONE_CONSISTENCY = 0.75
HIGHLIGHT_PLACEBO_PERCENTILE = 0.80
BOOTSTRAP_REPETITIONS = 500
MAX_MARKET_ROWS = 20_000
MIN_ARCHETYPE_GROUP = 10
MIN_ARCHETYPE_STABILITY = 0.70
MIN_PREVALENCE_GAP = 0.15
RIDGE_LAMBDA = 1.0


def build_market_synthetic_control(
    context: SellpointValueV5Context,
    candidate: CounterfactualCandidate,
    *,
    bundle_code: str,
    market_cells: Sequence[MarketCellRow] | None = None,
) -> SyntheticControlResult:
    """Balance a recalled donor pool and estimate observational differences."""

    target_code = context.v4_context.target.sku_code
    cells = list(market_cells if market_cells is not None else context.v4_context.market_cells)
    source_hash = _sample_manifest_hash(context, candidate, cells)
    if len(cells) > MAX_MARKET_ROWS:
        return _failed_synthetic(
            target_code,
            bundle_code,
            source_hash,
            donor_count=len(candidate.candidate_sku_codes),
            failures=["market_row_cap_exceeded"],
        )
    if candidate.method != "market_synthetic":
        return _failed_synthetic(
            target_code,
            bundle_code,
            source_hash,
            donor_count=0,
            failures=["counterfactual_method_not_synthetic"],
        )

    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    donor_codes = [
        code
        for code in sorted(set(candidate.candidate_sku_codes))
        if code != target_code and code in snapshots
    ]
    clean_cells = [
        row
        for row in cells
        if row.sku_code in {target_code, *donor_codes}
        and row.price_check_status == "ok"
        and not row.promotion_suspect
        and row.avg_price is not None
        and row.avg_price > 0
        and row.sales_volume is not None
        and row.sales_volume >= 0
    ]
    tier_by_sku = _bundle_tiers(clean_cells, bundle_code)
    target_tier = tier_by_sku.get(target_code)
    failures: list[str] = []
    if target_tier is None:
        failures.append("target_bundle_tier_unknown")
        eligible_donors: list[str] = []
    else:
        eligible_donors = [
            code
            for code in donor_codes
            if tier_by_sku.get(code) is not None and tier_by_sku[code] < target_tier
        ]
    if len(eligible_donors) < MIN_DONORS:
        failures.append("eligible_donor_count_insufficient")

    cell_keys = _supported_cell_keys(clean_cells, target_code, eligible_donors)
    common_weeks = len({week for week, _ in cell_keys})
    common_platforms = len({platform for _, platform in cell_keys})
    if common_weeks < MIN_COMMON_WEEKS:
        failures.append("common_weeks_insufficient")
    if common_platforms < MIN_COMMON_PLATFORMS:
        failures.append("common_platforms_insufficient")
    if failures:
        return _failed_synthetic(
            target_code,
            bundle_code,
            source_hash,
            donor_count=len(eligible_donors),
            failures=failures,
            common_weeks=common_weeks,
            common_platforms=common_platforms,
        )

    summaries = _covariate_summaries(
        snapshots,
        clean_cells,
        [target_code, *eligible_donors],
        focus_bundle=bundle_code,
    )
    if target_code not in summaries:
        return _failed_synthetic(
            target_code,
            bundle_code,
            source_hash,
            donor_count=len(eligible_donors),
            failures=["target_market_summary_missing"],
            common_weeks=common_weeks,
            common_platforms=common_platforms,
        )
    covariates = sorted(
        set(summaries[target_code]).intersection(
            *(set(summaries.get(code, {})) for code in eligible_donors)
        )
    )
    if not covariates:
        return _failed_synthetic(
            target_code,
            bundle_code,
            source_hash,
            donor_count=len(eligible_donors),
            failures=["balance_covariates_missing"],
            common_weeks=common_weeks,
            common_platforms=common_platforms,
        )

    target_vector = np.array([summaries[target_code][key] for key in covariates])
    donor_matrix = np.array(
        [[summaries[code][key] for key in covariates] for code in eligible_donors],
        dtype=float,
    )
    scaled_target, scaled_donors, scales = _scale_covariates(target_vector, donor_matrix)
    weights = _balanced_weights(scaled_target, scaled_donors)
    before = np.full(len(eligible_donors), 1 / len(eligible_donors))
    balance = _balance_metrics(
        covariates,
        target_vector,
        donor_matrix,
        before,
        weights,
        scales,
    )
    max_weight = float(np.max(weights))
    effective_donors = float(1.0 / np.sum(weights**2))
    price_support = _target_in_price_support(summaries, target_code, eligible_donors)

    gate_failures: list[str] = []
    if not price_support:
        gate_failures.append("target_outside_donor_price_support")
    if effective_donors < MIN_EFFECTIVE_DONORS:
        gate_failures.append("effective_donor_count_insufficient")
    if max_weight > MAX_DONOR_WEIGHT:
        gate_failures.append("single_donor_weight_too_high")
    if any(row.status == "failed" for row in balance):
        gate_failures.append("covariate_balance_failed")
    elif any(row.status == "limited" for row in balance):
        gate_failures.append("covariate_balance_limited")

    weights_by_code = {
        code: float(weight)
        for code, weight in zip(eligible_donors, weights, strict=True)
    }
    series = _effect_series(clean_cells, target_code, weights_by_code)
    if not series["sales"]:
        gate_failures.append("common_target_donor_cells_missing")
    leave_consistency = _leave_one_consistency(
        clean_cells, target_code, weights_by_code, series["sales"]
    )
    if leave_consistency is None or leave_consistency < MIN_LEAVE_ONE_CONSISTENCY:
        gate_failures.append("leave_one_direction_unstable")
    placebo = _placebo_percentile(clean_cells, target_code, weights_by_code, series["sales"])

    diagnostics = SyntheticDiagnostics(
        donor_count=len(eligible_donors),
        max_weight=max_weight,
        overlap_pass=price_support,
        balance_pass=all(row.status == "balanced" for row in balance),
        leave_one_sign_consistency=leave_consistency,
        placebo_percentile=placebo,
        common_week_count=common_weeks,
        common_platform_count=common_platforms,
        gate_pass=not gate_failures,
        failed_gates=sorted(set(gate_failures)),
    )
    if gate_failures:
        return SyntheticControlResult(
            status="unidentifiable",
            target_sku_code=target_code,
            bundle_code=bundle_code,
            donor_weights=weights_by_code,
            effective_donor_count=effective_donors,
            balance=balance,
            observed_window={
                "common_week_count": common_weeks,
                "common_platform_count": common_platforms,
            },
            diagnostics=diagnostics,
            limitations=sorted(set(gate_failures)),
            causal_claim=False,
            method_config_version=SYNTHETIC_CONFIG_VERSION,
            sample_manifest_hash=source_hash,
            result_hash=_canonical_hash(
                {"sample": source_hash, "failures": sorted(set(gate_failures))}
            ),
        )

    intervals = {
        name: _bootstrap_interval(values, source_hash, name)
        for name, values in series.items()
    }
    limitations = ["observational_not_causal", "inventory_unavailable"]
    if any(
        _snapshot_numeric(snapshots[code], "brand_tier_rank") is None
        for code in [target_code, *eligible_donors]
    ):
        limitations.append("brand_tier_unknown_for_some_skus")
    if placebo is None or placebo < HIGHLIGHT_PLACEBO_PERCENTILE:
        limitations.append("placebo_not_distinct_for_highlight")
    result_payload = {
        "target": target_code,
        "bundle": bundle_code,
        "weights": weights_by_code,
        "intervals": {
            key: value.model_dump(mode="json") for key, value in intervals.items()
        },
        "diagnostics": diagnostics.model_dump(mode="json"),
        "sample": source_hash,
    }
    return SyntheticControlResult(
        status="available",
        target_sku_code=target_code,
        bundle_code=bundle_code,
        donor_weights=weights_by_code,
        effective_donor_count=effective_donors,
        balance=balance,
        observed_window={
            "common_week_count": common_weeks,
            "common_platform_count": common_platforms,
        },
        price_difference=intervals["price"],
        sales_difference=intervals["sales"],
        share_difference=intervals["share"],
        amount_difference=intervals["amount"],
        diagnostics=diagnostics,
        limitations=limitations,
        causal_claim=False,
        method_config_version=SYNTHETIC_CONFIG_VERSION,
        sample_manifest_hash=source_hash,
        result_hash=_canonical_hash(result_payload),
    )


def build_performance_archetypes(
    context: SellpointValueV5Context,
    *,
    bundle_codes: Sequence[str],
    market_cells: Sequence[MarketCellRow] | None = None,
) -> list[PerformanceArchetype]:
    """Build high/low bundle archetypes after a cross-fitted market baseline."""

    cells = list(market_cells if market_cells is not None else context.v4_context.market_cells)
    sample_hash = _archetype_sample_hash(context, cells, bundle_codes)
    if len(cells) > MAX_MARKET_ROWS:
        return [_unstable_archetype(sample_hash, "market_row_cap_exceeded")]
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    clean = [
        row
        for row in cells
        if row.sku_code in snapshots
        and row.price_check_status == "ok"
        and not row.promotion_suspect
        and row.avg_price is not None
        and row.avg_price > 0
        and row.sales_volume is not None
        and row.sales_volume >= 0
    ]
    records = _cross_fitted_residuals(clean, snapshots)
    if len(records) < MIN_ARCHETYPE_GROUP * 4:
        return [_unstable_archetype(sample_hash, "archetype_population_insufficient")]

    by_sku: dict[str, list[dict[str, float]]] = defaultdict(list)
    for row in records:
        by_sku[row["sku_code"]].append(row)
    sku_rows = []
    for sku_code in sorted(by_sku):
        rows = by_sku[sku_code]
        residuals = np.array([row["residual"] for row in rows])
        center = float(np.median(residuals))
        sign = 1 if center >= 0 else -1
        stability = float(np.mean([1 if value * sign >= 0 else 0 for value in residuals]))
        sku_rows.append(
            {
                "sku_code": sku_code,
                "residual": center,
                "stability": stability,
                "price": float(np.mean([row["price"] for row in rows])),
                "sales": float(np.mean([row["sales"] for row in rows])),
            }
        )
    stable = [row for row in sku_rows if row["stability"] >= MIN_ARCHETYPE_STABILITY]
    if len(stable) < MIN_ARCHETYPE_GROUP * 4:
        return [_unstable_archetype(sample_hash, "stable_sku_population_insufficient")]
    residual_values = np.array([row["residual"] for row in stable])
    low_cut = float(np.quantile(residual_values, 0.25))
    high_cut = float(np.quantile(residual_values, 0.75))
    low = [row for row in stable if row["residual"] <= low_cut]
    high = [row for row in stable if row["residual"] >= high_cut]
    if len(low) < MIN_ARCHETYPE_GROUP or len(high) < MIN_ARCHETYPE_GROUP:
        return [_unstable_archetype(sample_hash, "archetype_group_insufficient")]

    prevalence_high = _bundle_prevalence(clean, high, bundle_codes)
    prevalence_low = _bundle_prevalence(clean, low, bundle_codes)
    material_codes = [
        code
        for code in sorted(set(prevalence_high) | set(prevalence_low))
        if abs(prevalence_high.get(code, 0.0) - prevalence_low.get(code, 0.0))
        >= MIN_PREVALENCE_GAP
        and _prevalence_direction_consistency(
            clean,
            high,
            low,
            code,
            sample_hash,
        )
        >= 0.80
    ]
    outcomes_high = _user_outcome_prevalence(snapshots, high)
    outcomes_low = _user_outcome_prevalence(snapshots, low)
    brand_tier_unknown = any(
        _snapshot_numeric(snapshots[row["sku_code"]], "brand_tier_rank") is None
        for row in [*high, *low]
    )
    return [
        _archetype(
            "high_performance",
            high,
            {code: prevalence_high.get(code, 0.0) for code in material_codes},
            outcomes_high,
            sample_hash,
            brand_tier_unknown=brand_tier_unknown,
        ),
        _archetype(
            "low_performance",
            low,
            {code: prevalence_low.get(code, 0.0) for code in material_codes},
            outcomes_low,
            sample_hash,
            brand_tier_unknown=brand_tier_unknown,
        ),
    ]


def build_battlefield_portfolio_options(
    context: SellpointValueV5Context,
    inputs: Sequence[BattlefieldPortfolioInput],
) -> list[BattlefieldPortfolioOption]:
    """Separate existing-battlefield strengthening from true expansion."""

    memberships = _target_battlefield_memberships(context.v4_context.target_snapshot)
    options: list[BattlefieldPortfolioOption] = []
    seen: set[str] = set()
    for row in sorted(inputs, key=lambda item: item.battlefield_code):
        if row.battlefield_code in seen:
            raise ValueError(f"duplicate battlefield input: {row.battlefield_code}")
        seen.add(row.battlefield_code)
        actual_membership = memberships.get(row.battlefield_code, "excluded")
        if actual_membership != row.source_membership:
            raise ValueError(
                "battlefield membership mismatch: "
                f"{row.battlefield_code} context={actual_membership} input={row.source_membership}"
            )
        if actual_membership == "excluded":
            options.append(_expansion_option(row))
        else:
            options.append(_strengthening_option(row, actual_membership))
    return sorted(
        options,
        key=lambda item: (
            0 if item.option_type == "strengthen_existing" else 1,
            item.battlefield_code,
        ),
    )


def _strengthening_option(
    row: BattlefieldPortfolioInput,
    membership: str,
) -> BattlefieldPortfolioOption:
    if row.role_capped:
        path = "portfolio_priority"
    elif row.capability_status in {"partial", "missing"}:
        path = "capability_completion"
    elif (
        row.user_value_status in {"observed_positive", "observed_mixed", "partial"}
        and row.claim_support in {"weak", "missing"}
    ):
        path = "communication_activation"
    elif (
        row.user_value_status in {"observed_positive", "observed_mixed", "partial"}
        and row.market_realization_status != "available"
    ):
        path = "market_activation"
    else:
        path = "maintain_or_cap"
    boundary = {
        "portfolio_priority": "该价值战场已经成立，当前问题是产品组合中的优先级，而不是进入新战场。",
        "capability_completion": "该价值战场已经进入，但能力仍有缺口；当前只能比较补全路径，不能承诺新增销量。",
        "communication_activation": "用户价值已有观察，但产品表达支撑偏弱；这是已有战场的表达激活。",
        "market_activation": "能力和用户价值已存在，但市场量价承接不足；这是已有战场的市场激活。",
        "maintain_or_cap": "该战场已进入，当前没有证据支持继续加码，先保持或控制重叠。",
    }[path]
    limitations = []
    if row.lineage_blocking:
        limitations.append("battlefield_lineage_conflict")
    if membership == "drag":
        limitations.append("drag_battlefield_not_positive_growth_option")
    return BattlefieldPortfolioOption(
        option_type="strengthen_existing",
        battlefield_code=row.battlefield_code,
        current_membership=membership,  # type: ignore[arg-type]
        strengthen_path=path,  # type: ignore[arg-type]
        market_space=row.market_space,
        current_allocation=row.current_allocation,
        evidence_boundary=boundary,
        limitations=limitations,
    )


def _expansion_option(row: BattlefieldPortfolioInput) -> BattlefieldPortfolioOption:
    hard_reasons: list[str] = []
    unknown_reasons: list[str] = []
    recall_reasons: list[str] = []
    if row.immutable_market_gate_pass is False:
        hard_reasons.append("immutable_size_price_market_gate_failed")
    elif row.immutable_market_gate_pass is None:
        unknown_reasons.append("immutable_size_price_market_gate_unknown")
    if row.product_form_gate_pass is False:
        hard_reasons.append("product_form_gate_failed")
    elif row.product_form_gate_pass is None:
        unknown_reasons.append("product_form_gate_unknown")
    if row.lineage_blocking:
        hard_reasons.append("battlefield_lineage_conflict")
    for gap in row.capability_gaps:
        if gap.status == "blocking" or (
            gap.status in {"missing", "unknown"} and not gap.mutable_in_scope
        ):
            hard_reasons.append(f"immutable_gap:{gap.gap_code}")
        elif gap.status == "unknown":
            unknown_reasons.append(f"gap_unknown:{gap.gap_code}")
    if row.task_group_adjacency is None:
        unknown_reasons.append("task_group_adjacency_unknown")
    elif row.task_group_adjacency < 0.50:
        recall_reasons.append("task_group_adjacency_insufficient")
    if row.donor_count < MIN_DONORS:
        recall_reasons.append("expansion_donor_count_insufficient")
    if not _has_positive_market_space(row.market_space):
        hard_reasons.append("battlefield_market_space_missing")

    combined_market_gate = (
        True
        if row.immutable_market_gate_pass is True and row.product_form_gate_pass is True
        else False
        if row.immutable_market_gate_pass is False or row.product_form_gate_pass is False
        else None
    )
    reasons = sorted(set([*hard_reasons, *unknown_reasons, *recall_reasons]))
    if hard_reasons:
        stage = "rejected"
    elif unknown_reasons:
        stage = "deferred_unknown"
    elif recall_reasons:
        stage = "recalled"
    else:
        stage = "eligible"
    eligibility = ExpansionEligibility(
        stage=stage,  # type: ignore[arg-type]
        current_membership="excluded",
        immutable_market_gate_pass=combined_market_gate,
        task_group_adjacency=row.task_group_adjacency,
        gaps=row.capability_gaps,
        donor_count=row.donor_count,
        overlap_risk=row.overlap_risk,
        eligible=stage == "eligible",
        reasons=reasons,
    )
    boundary = {
        "eligible": "当前是可比较的新战场拓展候选；只允许展示进入条件和观察性市场参照。",
        "recalled": "当前只召回了相邻战场，真实市场对照或任务相邻性仍不足，不能作为拓展方案。",
        "deferred_unknown": "关键进入条件仍未知，暂不能判断是否可拓展。",
        "rejected": "当前存在不可改变的尺寸、形态、能力或市场门槛，不属于本 SKU 的可拓展战场。",
    }[stage]
    return BattlefieldPortfolioOption(
        option_type="expand_excluded",
        battlefield_code=row.battlefield_code,
        current_membership="excluded",
        expansion_eligibility=eligibility,
        market_space=row.market_space,
        evidence_boundary=boundary,
        limitations=[EXPANSION_CONFIG_VERSION, *reasons],
    )


def _failed_synthetic(
    target_code: str,
    bundle_code: str,
    sample_hash: str,
    *,
    donor_count: int,
    failures: Sequence[str],
    common_weeks: int = 0,
    common_platforms: int = 0,
) -> SyntheticControlResult:
    failures = sorted(set(failures))
    diagnostics = SyntheticDiagnostics(
        donor_count=donor_count,
        max_weight=None,
        overlap_pass=False,
        balance_pass=False,
        leave_one_sign_consistency=None,
        placebo_percentile=None,
        common_week_count=common_weeks,
        common_platform_count=common_platforms,
        gate_pass=False,
        failed_gates=failures,
    )
    return SyntheticControlResult(
        status="degraded",
        target_sku_code=target_code,
        bundle_code=bundle_code,
        donor_weights={},
        effective_donor_count=None,
        balance=[],
        observed_window={
            "common_week_count": common_weeks,
            "common_platform_count": common_platforms,
        },
        diagnostics=diagnostics,
        limitations=failures,
        causal_claim=False,
        method_config_version=SYNTHETIC_CONFIG_VERSION,
        sample_manifest_hash=sample_hash,
        result_hash=_canonical_hash({"sample": sample_hash, "failures": failures}),
    )


def _covariate_summaries(
    snapshots: dict[str, SkuEvidenceSnapshot],
    cells: Sequence[MarketCellRow],
    sku_codes: Sequence[str],
    *,
    focus_bundle: str,
) -> dict[str, dict[str, float]]:
    rows_by_sku: dict[str, list[MarketCellRow]] = defaultdict(list)
    for row in cells:
        if row.sku_code in sku_codes:
            rows_by_sku[row.sku_code].append(row)
    other_bundle_codes = sorted(
        {
            code
            for row in cells
            for code in row.value_bundle_tiers
            if code != focus_bundle
        }
    )
    result: dict[str, dict[str, float]] = {}
    for sku_code in sku_codes:
        rows = rows_by_sku.get(sku_code, [])
        snapshot = snapshots.get(sku_code)
        if not rows or snapshot is None:
            continue
        prices = [float(row.avg_price) for row in rows if row.avg_price is not None]
        summary = {
            "log_price": float(math.log(max(np.mean(prices), 1e-9))),
            "screen_size": float(snapshot.identity.screen_size_inch or 0),
            "brand_tier": float(_snapshot_numeric(snapshot, "brand_tier_rank") or 0),
            "active_weeks": float(len({row.period_week_index for row in rows})),
        }
        for code in other_bundle_codes:
            values = [
                _tier_rank(row.value_bundle_tiers.get(code))
                for row in rows
                if _tier_rank(row.value_bundle_tiers.get(code)) is not None
            ]
            if values:
                summary[f"bundle:{code}"] = float(np.median(values))
        result[sku_code] = summary
    return result


def _scale_covariates(
    target: np.ndarray, donors: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    scales = np.std(donors, axis=0)
    scales = np.where(scales < 1e-9, 1.0, scales)
    center = np.mean(donors, axis=0)
    return (target - center) / scales, (donors - center) / scales, scales


def _balanced_weights(target: np.ndarray, donors: np.ndarray) -> np.ndarray:
    count = donors.shape[0]
    weights = np.full(count, 1.0 / count)
    spectral = float(np.linalg.norm(donors, ord=2) ** 2)
    step = 0.2 / max(1.0, 2 * spectral + 2 * RIDGE_LAMBDA)
    for _ in range(1000):
        gradient = 2 * donors @ (donors.T @ weights - target) + 2 * RIDGE_LAMBDA * weights
        updated = _project_simplex(weights - step * gradient)
        if float(np.max(np.abs(updated - weights))) < 1e-10:
            weights = updated
            break
        weights = updated
    return weights


def _project_simplex(values: np.ndarray) -> np.ndarray:
    ordered = np.sort(values)[::-1]
    cumulative = np.cumsum(ordered)
    indices = np.arange(1, len(values) + 1)
    valid = ordered - (cumulative - 1) / indices > 0
    rho = int(np.nonzero(valid)[0][-1])
    theta = (cumulative[rho] - 1) / (rho + 1)
    return np.maximum(values - theta, 0)


def _balance_metrics(
    names: Sequence[str],
    target: np.ndarray,
    donors: np.ndarray,
    before: np.ndarray,
    after: np.ndarray,
    scales: np.ndarray,
) -> list[BalanceMetric]:
    result = []
    for index, name in enumerate(names):
        denominator = float(scales[index])
        before_smd = float((target[index] - before @ donors[:, index]) / denominator)
        after_smd = float((target[index] - after @ donors[:, index]) / denominator)
        absolute = abs(after_smd)
        status = "balanced" if absolute <= BALANCED_SMD else "limited" if absolute <= FAILED_SMD else "failed"
        result.append(
            BalanceMetric(
                covariate_code=name,
                before_smd=round(before_smd, 6),
                after_smd=round(after_smd, 6),
                status=status,
            )
        )
    return result


def _target_in_price_support(
    summaries: dict[str, dict[str, float]], target: str, donors: Sequence[str]
) -> bool:
    target_price = summaries[target]["log_price"]
    donor_prices = [summaries[code]["log_price"] for code in donors]
    return min(donor_prices) <= target_price <= max(donor_prices)


def _effect_series(
    cells: Sequence[MarketCellRow],
    target_code: str,
    weights: dict[str, float],
) -> dict[str, list[tuple[int, float]]]:
    by_cell: dict[tuple[int, str], dict[str, MarketCellRow]] = defaultdict(dict)
    for row in cells:
        if row.sku_code == target_code or row.sku_code in weights:
            by_cell[(row.period_week_index, row.platform_type)][row.sku_code] = row
    result: dict[str, list[tuple[int, float]]] = {
        "price": [],
        "sales": [],
        "share": [],
        "amount": [],
    }
    for (week, _), rows in sorted(by_cell.items()):
        target = rows.get(target_code)
        available = {code: weight for code, weight in weights.items() if code in rows}
        if target is None or len(available) < int(MIN_EFFECTIVE_DONORS):
            continue
        total_weight = sum(available.values())
        normalized = {code: weight / total_weight for code, weight in available.items()}
        synthetic_price = sum(normalized[code] * float(rows[code].avg_price or 0) for code in normalized)
        synthetic_sales = sum(normalized[code] * float(rows[code].sales_volume or 0) for code in normalized)
        synthetic_amount = sum(normalized[code] * float(rows[code].sales_amount or 0) for code in normalized)
        target_price = float(target.avg_price or 0)
        target_sales = float(target.sales_volume or 0)
        target_amount = float(target.sales_amount or 0)
        denominator = target_sales + synthetic_sales
        share_difference = (target_sales / denominator - 0.5) * 100 if denominator > 0 else 0.0
        result["price"].append((week, target_price - synthetic_price))
        result["sales"].append((week, target_sales - synthetic_sales))
        result["share"].append((week, share_difference))
        result["amount"].append((week, target_amount - synthetic_amount))
    return result


def _leave_one_consistency(
    cells: Sequence[MarketCellRow],
    target_code: str,
    weights: dict[str, float],
    baseline: Sequence[tuple[int, float]],
) -> float | None:
    if not baseline:
        return None
    base_value = float(np.mean([value for _, value in baseline]))
    base_sign = 1 if base_value >= 0 else -1
    signs: list[bool] = []
    for removed in sorted(weights):
        remaining = {code: weight for code, weight in weights.items() if code != removed}
        total = sum(remaining.values())
        if total <= 0:
            continue
        remaining = {code: weight / total for code, weight in remaining.items()}
        values = _effect_series(cells, target_code, remaining)["sales"]
        if values:
            signs.append(float(np.mean([value for _, value in values])) * base_sign >= 0)
    weeks = sorted({week for week, _ in baseline})
    for removed_week in weeks:
        values = [value for week, value in baseline if week != removed_week]
        if values:
            signs.append(float(np.mean(values)) * base_sign >= 0)
    return float(np.mean(signs)) if signs else None


def _placebo_percentile(
    cells: Sequence[MarketCellRow],
    target_code: str,
    weights: dict[str, float],
    target_series: Sequence[tuple[int, float]],
) -> float | None:
    if not target_series or len(weights) < 3:
        return None
    target_effect = abs(float(np.mean([value for _, value in target_series])))
    placebo_effects = []
    donor_codes = sorted(weights)
    for pseudo in donor_codes:
        others = [code for code in donor_codes if code != pseudo]
        pseudo_weights = {code: 1 / len(others) for code in others}
        values = _effect_series(cells, pseudo, pseudo_weights)["sales"]
        if values:
            placebo_effects.append(abs(float(np.mean([value for _, value in values]))))
    if not placebo_effects:
        return None
    return float(np.mean([effect <= target_effect for effect in placebo_effects]))


def _bootstrap_interval(
    values: Sequence[tuple[int, float]], sample_hash: str, metric: str
) -> IntervalEstimate:
    by_week: dict[int, list[float]] = defaultdict(list)
    for week, value in values:
        by_week[week].append(value)
    weeks = sorted(by_week)
    observed = float(np.mean([value for _, value in values]))
    seed = int(hashlib.sha256(f"{sample_hash}:{metric}".encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        sampled = rng.choice(weeks, size=len(weeks), replace=True)
        draws.append(float(np.mean([value for week in sampled for value in by_week[int(week)]])))
    low, high = np.quantile(np.array(draws), [0.025, 0.975])
    unit = {
        "price": "CNY",
        "sales": "sales_per_cell",
        "share": "percentage_points",
        "amount": "CNY_per_cell",
    }[metric]
    return IntervalEstimate(
        estimate=round(observed, 6),
        low=round(float(low), 6),
        high=round(float(high), 6),
        unit=unit,
        observational=True,
        currency="CNY" if metric in {"price", "amount"} else None,
    )


def _cross_fitted_residuals(
    cells: Sequence[MarketCellRow], snapshots: dict[str, SkuEvidenceSnapshot]
) -> list[dict[str, Any]]:
    raw = []
    by_market_cell: dict[tuple[int, str], list[MarketCellRow]] = defaultdict(list)
    for row in cells:
        by_market_cell[(row.period_week_index, row.platform_type)].append(row)
    for key, group in by_market_cell.items():
        if len(group) < 5:
            continue
        log_sales = [math.log1p(float(row.sales_volume or 0)) for row in group]
        log_prices = [math.log(float(row.avg_price or 1)) for row in group]
        for index, row in enumerate(group):
            peer_sales = log_sales[:index] + log_sales[index + 1 :]
            peer_prices = log_prices[:index] + log_prices[index + 1 :]
            snapshot = snapshots[row.sku_code]
            raw.append(
                {
                    "sku_code": row.sku_code,
                    "week": key[0],
                    "platform": key[1],
                    "y": log_sales[index] - float(np.mean(peer_sales)),
                    "log_price_relative": log_prices[index] - float(np.mean(peer_prices)),
                    "size": float(snapshot.identity.screen_size_inch or 0),
                    "brand_tier": float(_snapshot_numeric(snapshot, "brand_tier_rank") or 0),
                    "active_week": float(_snapshot_numeric(snapshot, "active_week_count") or 0),
                    "price": float(row.avg_price or 0),
                    "sales": float(row.sales_volume or 0),
                }
            )
    if not raw:
        return []
    feature_names = ("log_price_relative", "size", "brand_tier", "active_week")
    matrix = np.array([[row[name] for name in feature_names] for row in raw], dtype=float)
    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale = np.where(scale < 1e-9, 1.0, scale)
    matrix = (matrix - mean) / scale
    result = []
    weeks = sorted({int(row["week"]) for row in raw})
    for held_week in weeks:
        train = np.array([int(row["week"]) != held_week for row in raw])
        test = ~train
        if int(np.sum(train)) < len(feature_names) + 2:
            continue
        x_train = np.column_stack([np.ones(int(np.sum(train))), matrix[train]])
        y_train = np.array([row["y"] for row, keep in zip(raw, train, strict=True) if keep])
        penalty = np.eye(x_train.shape[1]) * RIDGE_LAMBDA
        penalty[0, 0] = 0
        coefficients = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ y_train)
        x_test = np.column_stack([np.ones(int(np.sum(test))), matrix[test]])
        predictions = x_test @ coefficients
        for row, prediction in zip(
            [row for row, keep in zip(raw, test, strict=True) if keep],
            predictions,
            strict=True,
        ):
            result.append(
                {
                    "sku_code": row["sku_code"],
                    "week": row["week"],
                    "price": row["price"],
                    "sales": row["sales"],
                    "residual": float(row["y"] - prediction),
                }
            )
    return result


def _bundle_prevalence(
    cells: Sequence[MarketCellRow],
    group: Sequence[dict[str, Any]],
    bundle_codes: Sequence[str],
) -> dict[str, float]:
    group_codes = {row["sku_code"] for row in group}
    by_sku: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in cells:
        if row.sku_code not in group_codes:
            continue
        for code in bundle_codes:
            rank = _tier_rank(row.value_bundle_tiers.get(code))
            if rank is not None:
                by_sku[row.sku_code][code].append(rank)
    result = {}
    for code in bundle_codes:
        observed = [
            bool(values.get(code) and np.median(values[code]) > 0)
            for values in by_sku.values()
        ]
        if observed:
            result[code] = float(np.mean(observed))
    return result


def _prevalence_direction_consistency(
    cells: Sequence[MarketCellRow],
    high: Sequence[dict[str, Any]],
    low: Sequence[dict[str, Any]],
    bundle_code: str,
    sample_hash: str,
) -> float:
    presence: dict[str, bool] = {}
    values_by_sku: dict[str, list[int]] = defaultdict(list)
    for row in cells:
        rank = _tier_rank(row.value_bundle_tiers.get(bundle_code))
        if rank is not None:
            values_by_sku[row.sku_code].append(rank)
    for sku_code, values in values_by_sku.items():
        presence[sku_code] = bool(np.median(values) > 0)
    high_values = [int(presence[row["sku_code"]]) for row in high if row["sku_code"] in presence]
    low_values = [int(presence[row["sku_code"]]) for row in low if row["sku_code"] in presence]
    if len(high_values) < MIN_ARCHETYPE_GROUP or len(low_values) < MIN_ARCHETYPE_GROUP:
        return 0.0
    observed = float(np.mean(high_values) - np.mean(low_values))
    direction = 1 if observed >= 0 else -1
    seed = int(
        hashlib.sha256(f"{sample_hash}:prevalence:{bundle_code}".encode()).hexdigest()[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    consistent = []
    high_array = np.array(high_values)
    low_array = np.array(low_values)
    for _ in range(BOOTSTRAP_REPETITIONS):
        high_draw = rng.choice(high_array, size=len(high_array), replace=True)
        low_draw = rng.choice(low_array, size=len(low_array), replace=True)
        consistent.append(float(np.mean(high_draw) - np.mean(low_draw)) * direction >= 0)
    return float(np.mean(consistent))


def _user_outcome_prevalence(
    snapshots: dict[str, SkuEvidenceSnapshot], group: Sequence[dict[str, Any]]
) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    group_codes = [row["sku_code"] for row in group]
    for sku_code in group_codes:
        values = _string_values(snapshots[sku_code].facts, "supported_claim_codes")
        for code in values:
            counts[code] += 1
    return {
        code: round(count / len(group_codes), 6)
        for code, count in sorted(counts.items())
    }


def _archetype(
    role: str,
    rows: Sequence[dict[str, Any]],
    prevalence: dict[str, float],
    outcomes: dict[str, float],
    sample_hash: str,
    *,
    brand_tier_unknown: bool,
) -> PerformanceArchetype:
    result_payload = {
        "role": role,
        "skus": sorted(row["sku_code"] for row in rows),
        "prevalence": prevalence,
        "sample": sample_hash,
    }
    return PerformanceArchetype(
        role=role,  # type: ignore[arg-type]
        metric="log1p_sales_residual",
        sku_count=len(rows),
        representative_sku_codes=[
            row["sku_code"]
            for row in sorted(rows, key=lambda item: (-abs(item["residual"]), item["sku_code"]))[:5]
        ],
        bundle_prevalence=prevalence,
        user_outcome_prevalence=outcomes,
        price_interval=_distribution_interval([row["price"] for row in rows], "CNY"),
        volume_interval=_distribution_interval([row["sales"] for row in rows], "sales_per_cell"),
        residual_interval=_distribution_interval([row["residual"] for row in rows], "log1p_sales_residual"),
        stability=round(float(np.mean([row["stability"] for row in rows])), 6),
        limitations=[
            "observational_bundle_archetype_not_causal",
            *(["brand_tier_unknown_for_some_skus"] if brand_tier_unknown else []),
        ],
        causal_claim=False,
        method_config_version=ARCHETYPE_CONFIG_VERSION,
        sample_manifest_hash=sample_hash,
        result_hash=_canonical_hash(result_payload),
    )


def _unstable_archetype(sample_hash: str, reason: str) -> PerformanceArchetype:
    return PerformanceArchetype(
        role="unstable",
        metric="log1p_sales_residual",
        sku_count=0,
        representative_sku_codes=[],
        bundle_prevalence={},
        user_outcome_prevalence={},
        stability=0,
        limitations=[reason],
        causal_claim=False,
        method_config_version=ARCHETYPE_CONFIG_VERSION,
        sample_manifest_hash=sample_hash,
        result_hash=_canonical_hash({"sample": sample_hash, "reason": reason}),
    )


def _distribution_interval(values: Sequence[float], unit: str) -> IntervalEstimate:
    array = np.array(values, dtype=float)
    return IntervalEstimate(
        estimate=round(float(np.median(array)), 6),
        low=round(float(np.quantile(array, 0.10)), 6),
        high=round(float(np.quantile(array, 0.90)), 6),
        unit=unit,
        observational=True,
        currency="CNY" if unit == "CNY" else None,
    )


def _bundle_tiers(
    cells: Sequence[MarketCellRow], bundle_code: str
) -> dict[str, int]:
    values: dict[str, list[int]] = defaultdict(list)
    for row in cells:
        rank = _tier_rank(row.value_bundle_tiers.get(bundle_code))
        if rank is not None:
            values[row.sku_code].append(rank)
    return {code: int(np.median(ranks)) for code, ranks in values.items()}


def _tier_rank(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return {
            "absent": 0,
            "base": 1,
            "enhanced": 2,
            "premium": 3,
            "flagship": 4,
        }.get(value.lower())
    return None


def _target_battlefield_memberships(
    snapshot: SkuEvidenceSnapshot,
) -> dict[str, str]:
    memberships: dict[str, str] = {}
    priority = {
        "primary": 0,
        "secondary": 1,
        "user_observed": 2,
        "opportunity": 3,
        "drag": 4,
    }

    def assign(code: Any, membership: str) -> None:
        if not isinstance(code, str) or not code:
            return
        existing = memberships.get(code)
        if existing is None or priority[membership] < priority[existing]:
            memberships[code] = membership

    for row in snapshot.battlefields:
        assign(row.get("primary_battlefield_code"), "primary")
        for code in _as_string_list(
            row.get("secondary_battlefield_codes")
            or row.get("secondary_battlefield_codes_json")
        ):
            assign(code, "secondary")
        for code in _as_string_list(
            row.get("opportunity_battlefield_codes")
            or row.get("opportunity_battlefield_codes_json")
        ):
            assign(code, "opportunity")
        for code in _as_string_list(row.get("user_observed_battlefield_codes")):
            assign(code, "user_observed")
        for code in _as_string_list(
            row.get("drag_factor_battlefield_codes")
            or row.get("drag_factor_battlefield_codes_json")
        ):
            assign(code, "drag")
        for detail in row.get("battlefield_rows") or []:
            relation = detail.get("relation_status")
            membership = {
                "primary_battlefield": "primary",
                "secondary_battlefield": "secondary",
                "opportunity_battlefield": "opportunity",
                "user_observed_battlefield": "user_observed",
                "drag_factor_battlefield": "drag",
            }.get(relation)
            if membership:
                assign(detail.get("battlefield_code"), membership)
    return memberships


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _has_positive_market_space(market_space: dict[str, Any]) -> bool:
    for key in (
        "estimated_sales_volume",
        "estimated_sales_amount",
        "estimated_avg_weekly_sales_volume",
    ):
        value = market_space.get(key)
        try:
            if value is not None and float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _supported_cell_keys(
    cells: Sequence[MarketCellRow],
    target_code: str,
    donor_codes: Sequence[str],
) -> set[tuple[int, str]]:
    by_cell: dict[tuple[int, str], set[str]] = defaultdict(set)
    for row in cells:
        if row.sku_code == target_code or row.sku_code in donor_codes:
            by_cell[(row.period_week_index, row.platform_type)].add(row.sku_code)
    return {
        key
        for key, sku_codes in by_cell.items()
        if target_code in sku_codes
        and len(set(donor_codes) & sku_codes) >= int(MIN_EFFECTIVE_DONORS)
    }


def _snapshot_numeric(snapshot: SkuEvidenceSnapshot, key: str) -> float | None:
    value = _recursive_value(snapshot.market, key)
    if value is None:
        value = _recursive_value(snapshot.facts, key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _recursive_value(payload: Any, key: str) -> Any:
    queue = [payload]
    while queue:
        value = queue.pop(0)
        if isinstance(value, dict):
            if key in value:
                return value[key]
            queue.extend(value[name] for name in sorted(value) if isinstance(value[name], (dict, list)))
        elif isinstance(value, list):
            queue.extend(item for item in value if isinstance(item, (dict, list)))
    return None


def _string_values(payload: Any, key: str) -> set[str]:
    value = _recursive_value(payload, key)
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _sample_manifest_hash(
    context: SellpointValueV5Context,
    candidate: CounterfactualCandidate,
    cells: Sequence[MarketCellRow],
) -> str:
    return _canonical_hash(
        {
            "context": context.input_hash,
            "candidate": candidate.sample_manifest_hash,
            "cells": [
                (
                    row.sku_code,
                    row.period_week_index,
                    row.platform_type,
                    row.avg_price,
                    row.sales_volume,
                    row.sales_amount,
                    row.price_check_status,
                    row.promotion_suspect,
                    sorted(row.value_bundle_tiers.items()),
                )
                for row in sorted(
                    cells,
                    key=lambda item: (
                        item.sku_code,
                        item.period_week_index,
                        item.platform_type,
                    ),
                )
            ],
        }
    )


def _archetype_sample_hash(
    context: SellpointValueV5Context,
    cells: Sequence[MarketCellRow],
    bundle_codes: Sequence[str],
) -> str:
    return _canonical_hash(
        {
            "context": context.input_hash,
            "bundles": sorted(set(bundle_codes)),
            "snapshots": {
                row.identity.sku_code: row.snapshot_hash
                for row in sorted(context.market_universe, key=lambda item: item.identity.sku_code)
            },
            "cells": [
                (
                    row.sku_code,
                    row.period_week_index,
                    row.platform_type,
                    row.avg_price,
                    row.sales_volume,
                    sorted(row.value_bundle_tiers.items()),
                )
                for row in sorted(
                    cells,
                    key=lambda item: (
                        item.sku_code,
                        item.period_week_index,
                        item.platform_type,
                    ),
                )
            ],
        }
    )


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "ARCHETYPE_CONFIG_VERSION",
    "EXPANSION_CONFIG_VERSION",
    "SYNTHETIC_CONFIG_VERSION",
    "build_battlefield_portfolio_options",
    "build_market_synthetic_control",
    "build_performance_archetypes",
]
