"""Low-gate direct market and parameter-group comparisons for SPV V5.1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    CandidateSourceType,
    DirectMarketComparisonInput,
    DirectMarketComparisonResult,
    MarketComparatorObservation,
    MarketComparisonDirection,
    MarketMetricCode,
    MarketMetricComparison,
    MetricCandidateDisposition,
    ParameterCandidateDisposition,
    ParameterGroupComparisonInput,
    ParameterGroupComparisonResult,
    ParameterValueGroup,
    ParameterValueObservation,
    QuestionConclusionStatus,
    QuestionConclusionStrength,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_DIRECT_MARKET_METHOD_VERSION = "sellpoint_value_direct_market_gap_v5_1"
SPV_V5_1_PARAMETER_GROUP_METHOD_VERSION = "sellpoint_value_parameter_group_v5_1"

_PRICE_QUANTUM = Decimal("0.0001")
_SALES_QUANTUM = Decimal("0.000001")
_RATIO_QUANTUM = Decimal("0.000001")


def calculate_direct_market_comparison(
    item: DirectMarketComparisonInput,
) -> DirectMarketComparisonResult:
    """Compare independent weekly averages with metric-local missing handling."""

    item = DirectMarketComparisonInput.model_validate(item.model_dump(mode="python"))
    chosen, dispositions = _direct_candidate_dispositions(item)
    target_price = item.target_market.weighted_price
    target_sales = item.target_market.avg_weekly_sales_volume
    price_rows = [
        row
        for row in chosen
        if target_price is not None and row.market.weighted_price is not None
    ]
    sales_rows = [
        row
        for row in chosen
        if target_sales is not None and row.market.avg_weekly_sales_volume is not None
    ]
    price_comparison = (
        _metric_comparison(
            MarketMetricCode.PRICE,
            target_price,
            [(row.market.sku_code, row.market.weighted_price) for row in price_rows],
        )
        if target_price is not None and price_rows
        else None
    )
    sales_comparison = (
        _metric_comparison(
            MarketMetricCode.WEEKLY_SALES,
            target_sales,
            [
                (row.market.sku_code, row.market.avg_weekly_sales_volume)
                for row in sales_rows
            ],
        )
        if target_sales is not None and sales_rows
        else None
    )
    used_codes = sorted(
        {
            *(
                price_comparison.comparator_sku_codes
                if price_comparison is not None
                else []
            ),
            *(
                sales_comparison.comparator_sku_codes
                if sales_comparison is not None
                else []
            ),
        }
    )
    status = _direct_status(price_comparison, sales_comparison)
    strength = _direct_strength(price_comparison, sales_comparison)
    limitations = _direct_limitations(
        item,
        price_comparison=price_comparison,
        sales_comparison=sales_comparison,
        dispositions=dispositions,
    )
    evidence_refs = _dedupe_evidence_refs(
        [
            *item.target_evidence_refs,
            *(
                ref
                for row in item.comparators
                for ref in [*row.candidate_use.evidence_refs, *row.evidence_refs]
            ),
        ]
    )
    payload: dict[str, Any] = {
        "project_id": item.project_id,
        "category_code": item.category_code,
        "target_sku_code": item.target_sku_code,
        "value_bundle_code": item.value_bundle_code,
        "method": item.method,
        "status": status,
        "strength": strength,
        "used_comparator_sku_codes": used_codes,
        "comparator_count": len(used_codes),
        "price_comparison": price_comparison,
        "sales_comparison": sales_comparison,
        "candidate_dispositions": dispositions,
        "business_conclusion_cn": _direct_business_conclusion(
            price_comparison,
            sales_comparison,
        ),
        "causal_claim": False,
        "limitations": limitations,
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": evidence_refs,
    }
    return DirectMarketComparisonResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_DIRECT_MARKET_METHOD_VERSION,
        ),
    )


def calculate_parameter_group_comparison(
    item: ParameterGroupComparisonInput,
) -> ParameterGroupComparisonResult:
    """Compare every observed normalized parameter value without ordinal tiers."""

    item = ParameterGroupComparisonInput.model_validate(item.model_dump(mode="python"))
    selected, dispositions = _parameter_candidate_dispositions(item.comparators)
    target_value = _normalized_parameter_value(item.target.normalized_value)
    observations = [
        item.target.model_copy(update={"normalized_value": target_value}),
        *selected,
    ]
    grouped: dict[str, list[ParameterValueObservation]] = defaultdict(list)
    for row in observations:
        value = _normalized_parameter_value(row.normalized_value)
        if value is not None:
            grouped[value].append(row.model_copy(update={"normalized_value": value}))
    raw_groups = {
        value: _parameter_group(
            normalized_value=value,
            rows=rows,
            target_value=target_value,
        )
        for value, rows in grouped.items()
    }
    target_group = raw_groups.get(target_value) if target_value is not None else None
    groups = [
        _with_target_group_gaps(row, target_group)
        for _, row in sorted(raw_groups.items())
    ]
    different_rows = (
        [
            row
            for row in selected
            if _normalized_parameter_value(row.normalized_value)
            not in {None, target_value}
        ]
        if target_value is not None
        else []
    )
    different_count = len({row.sku_code for row in different_rows})
    status = _parameter_status(groups, target_value, different_count)
    strength = _parameter_strength(different_count)
    limitations = _parameter_limitations(
        item,
        groups=groups,
        target_value=target_value,
        different_count=different_count,
        dispositions=dispositions,
    )
    evidence_refs = _dedupe_evidence_refs(
        [
            *item.target.evidence_refs,
            *(
                ref
                for row in item.comparators
                for ref in [
                    *(row.candidate_use.evidence_refs if row.candidate_use else []),
                    *row.evidence_refs,
                ]
            ),
        ]
    )
    payload: dict[str, Any] = {
        "project_id": item.project_id,
        "category_code": item.category_code,
        "target_sku_code": item.target_sku_code,
        "value_bundle_code": item.value_bundle_code,
        "parameter_code": item.parameter_code,
        "parameter_name_cn": item.parameter_name_cn,
        "unit": item.unit,
        "target_value": target_value,
        "status": status,
        "strength": strength,
        "distinct_values": sorted(raw_groups),
        "different_value_comparator_count": different_count,
        "groups": groups,
        "candidate_dispositions": dispositions,
        "core_highlight_eligible": not item.exclude_from_core_sellpoints,
        "business_conclusion_cn": _parameter_business_conclusion(
            item,
            groups=groups,
            target_value=target_value,
            different_count=different_count,
        ),
        "causal_claim": False,
        "limitations": limitations,
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": evidence_refs,
    }
    return ParameterGroupComparisonResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_PARAMETER_GROUP_METHOD_VERSION,
        ),
    )


def calculate_parameter_group_comparisons(
    items: Sequence[ParameterGroupComparisonInput],
) -> list[ParameterGroupComparisonResult]:
    """Calculate independent parameters deterministically."""

    keys = [
        (
            row.project_id,
            row.category_code,
            row.target_sku_code,
            row.value_bundle_code,
            row.parameter_code,
        )
        for row in items
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("parameter comparison inputs must be unique by local scope")
    return [
        calculate_parameter_group_comparison(row)
        for row in sorted(
            items,
            key=lambda row: (
                row.project_id,
                row.category_code,
                row.target_sku_code,
                row.value_bundle_code,
                row.parameter_code,
            ),
        )
    ]


def _direct_candidate_dispositions(
    item: DirectMarketComparisonInput,
) -> tuple[list[MarketComparatorObservation], list[MetricCandidateDisposition]]:
    selected = [row for row in item.comparators if row.candidate_use.selected]
    chosen_by_sku: dict[str, MarketComparatorObservation] = {}
    for row in sorted(selected, key=_market_observation_sort_key):
        chosen_by_sku.setdefault(row.market.sku_code, row)
    chosen = list(chosen_by_sku.values())
    dispositions = []
    for row in sorted(item.comparators, key=_market_observation_sort_key):
        used_metrics: list[MarketMetricCode] = []
        skipped_metrics: list[MarketMetricCode] = []
        reasons: list[str] = []
        effective = chosen_by_sku.get(row.market.sku_code) is row
        if not row.candidate_use.selected:
            skipped_metrics = [MarketMetricCode.PRICE, MarketMetricCode.WEEKLY_SALES]
            reasons = [
                "question_candidate_not_selected",
                *row.candidate_use.rejection_reasons,
            ]
        elif not effective:
            skipped_metrics = [MarketMetricCode.PRICE, MarketMetricCode.WEEKLY_SALES]
            reasons = ["duplicate_sku_identity_not_counted"]
        else:
            for metric, target_value, candidate_value in (
                (
                    MarketMetricCode.PRICE,
                    item.target_market.weighted_price,
                    row.market.weighted_price,
                ),
                (
                    MarketMetricCode.WEEKLY_SALES,
                    item.target_market.avg_weekly_sales_volume,
                    row.market.avg_weekly_sales_volume,
                ),
            ):
                if target_value is None:
                    skipped_metrics.append(metric)
                    reasons.append(f"target_{metric.value}_missing")
                elif candidate_value is None:
                    skipped_metrics.append(metric)
                    reasons.append(f"candidate_{metric.value}_missing")
                else:
                    used_metrics.append(metric)
        dispositions.append(
            MetricCandidateDisposition(
                candidate_sku_code=row.market.sku_code,
                source_type=row.candidate_use.source_type,
                used_metrics=sorted(used_metrics, key=lambda value: value.value),
                skipped_metrics=sorted(skipped_metrics, key=lambda value: value.value),
                skip_reasons=sorted(set(reasons)),
            )
        )
    return chosen, dispositions


def _metric_comparison(
    metric: MarketMetricCode,
    target_value: Decimal,
    rows: Sequence[tuple[str, Decimal | None]],
) -> MarketMetricComparison:
    values = [(code, value) for code, value in rows if value is not None]
    quantum = _PRICE_QUANTUM if metric == MarketMetricCode.PRICE else _SALES_QUANTUM
    comparator_average = _mean([value for _, value in values], quantum)
    normalized_target = target_value.quantize(quantum)
    gap = (normalized_target - comparator_average).quantize(quantum)
    gap_pct = (
        (gap / comparator_average).quantize(_RATIO_QUANTUM)
        if comparator_average > 0
        else None
    )
    return MarketMetricComparison(
        metric=metric,
        strength=_comparator_count_strength(len(values)),
        target_value=normalized_target,
        comparator_average=comparator_average,
        comparator_sku_codes=sorted(code for code, _ in values),
        comparator_count=len(values),
        gap_abs=gap,
        gap_pct=gap_pct,
        direction=_direction(gap),
    )


def _direct_status(
    price: MarketMetricComparison | None,
    sales: MarketMetricComparison | None,
) -> QuestionConclusionStatus:
    available_count = sum(row is not None for row in (price, sales))
    if available_count == 2:
        return QuestionConclusionStatus.CONCLUSION_AVAILABLE
    if available_count == 1:
        return QuestionConclusionStatus.PARTIAL_CONCLUSION
    return QuestionConclusionStatus.NO_CONCLUSION


def _direct_strength(
    price: MarketMetricComparison | None,
    sales: MarketMetricComparison | None,
) -> QuestionConclusionStrength:
    comparisons = [row for row in (price, sales) if row is not None]
    if not comparisons:
        return QuestionConclusionStrength.NONE
    rank = {
        QuestionConclusionStrength.SINGLE: 1,
        QuestionConclusionStrength.SMALL_GROUP: 2,
        QuestionConclusionStrength.GROUP: 3,
    }
    return min(comparisons, key=lambda row: rank[row.strength]).strength


def _comparator_count_strength(count: int) -> QuestionConclusionStrength:
    if count == 1:
        return QuestionConclusionStrength.SINGLE
    if count <= 4:
        return QuestionConclusionStrength.SMALL_GROUP
    return QuestionConclusionStrength.GROUP


def _direct_limitations(
    item: DirectMarketComparisonInput,
    *,
    price_comparison: MarketMetricComparison | None,
    sales_comparison: MarketMetricComparison | None,
    dispositions: Sequence[MetricCandidateDisposition],
) -> list[str]:
    limitations = {
        "common_platforms_not_required",
        "common_weeks_not_required",
        "full_window_weekly_average",
        "market_association_not_causal",
    }
    if price_comparison is None:
        limitations.add("price_comparison_unavailable")
    if sales_comparison is None:
        limitations.add("weekly_sales_comparison_unavailable")
    skipped_count = sum(bool(row.skipped_metrics) for row in dispositions)
    if skipped_count:
        limitations.add(f"candidate_rows_with_metric_skips:{skipped_count}")
    if not item.comparators:
        limitations.add("no_comparator_observations")
    return sorted(limitations)


def _direct_business_conclusion(
    price: MarketMetricComparison | None,
    sales: MarketMetricComparison | None,
) -> str:
    parts = []
    if price is not None:
        parts.append(
            f"本品周均价较{price.comparator_count}款参照的平均水平"
            f"{_direction_cn(price.direction)}{_number_cn(abs(price.gap_abs))}元"
        )
    if sales is not None:
        parts.append(
            f"周均销量较{sales.comparator_count}款参照的平均水平"
            f"{_direction_cn(sales.direction)}{_number_cn(abs(sales.gap_abs))}台"
        )
    if not parts:
        return "本品与现有参照尚未形成可计算的周均价格或销量比较。"
    return "，".join(parts) + "；该结果用于判断市场表现，不归因于单一卖点。"


def _parameter_candidate_dispositions(
    observations: Sequence[ParameterValueObservation],
) -> tuple[list[ParameterValueObservation], list[ParameterCandidateDisposition]]:
    selected = [
        row
        for row in observations
        if row.candidate_use is not None and row.candidate_use.selected
    ]
    chosen_by_sku: dict[str, ParameterValueObservation] = {}
    for row in sorted(selected, key=_parameter_observation_sort_key):
        chosen_by_sku.setdefault(row.sku_code, row)
    used = []
    dispositions = []
    for row in sorted(observations, key=_parameter_observation_sort_key):
        reasons: list[str] = []
        effective = chosen_by_sku.get(row.sku_code) is row
        if row.candidate_use is None or not row.candidate_use.selected:
            reasons = [
                "question_candidate_not_selected",
                *(row.candidate_use.rejection_reasons if row.candidate_use else []),
            ]
        elif not effective:
            reasons = ["duplicate_sku_identity_not_counted"]
        elif _normalized_parameter_value(row.normalized_value) is None:
            reasons = ["parameter_value_missing"]
        else:
            used.append(
                row.model_copy(
                    update={
                        "normalized_value": _normalized_parameter_value(
                            row.normalized_value
                        )
                    }
                )
            )
        dispositions.append(
            ParameterCandidateDisposition(
                candidate_sku_code=row.sku_code,
                source_type=CandidateSourceType(row.source_type.value),
                used=not reasons,
                skip_reasons=sorted(set(reasons)),
            )
        )
    return used, dispositions


def _parameter_group(
    *,
    normalized_value: str,
    rows: Sequence[ParameterValueObservation],
    target_value: str | None,
) -> ParameterValueGroup:
    ordered = sorted(rows, key=lambda row: row.sku_code)
    price_rows = [row for row in ordered if row.weighted_price is not None]
    sales_rows = [row for row in ordered if row.avg_weekly_sales_volume is not None]
    return ParameterValueGroup(
        normalized_value=normalized_value,
        is_target_group=normalized_value == target_value,
        sku_codes=sorted({row.sku_code for row in ordered}),
        sku_count=len({row.sku_code for row in ordered}),
        price_sku_codes=sorted({row.sku_code for row in price_rows}),
        average_price=(
            _mean(
                [
                    row.weighted_price
                    for row in price_rows
                    if row.weighted_price is not None
                ],
                _PRICE_QUANTUM,
            )
            if price_rows
            else None
        ),
        sales_sku_codes=sorted({row.sku_code for row in sales_rows}),
        average_weekly_sales=(
            _mean(
                [
                    row.avg_weekly_sales_volume
                    for row in sales_rows
                    if row.avg_weekly_sales_volume is not None
                ],
                _SALES_QUANTUM,
            )
            if sales_rows
            else None
        ),
    )


def _with_target_group_gaps(
    row: ParameterValueGroup,
    target: ParameterValueGroup | None,
) -> ParameterValueGroup:
    if target is None:
        return row
    price_gap, price_pct = _group_gap(
        row.average_price, target.average_price, _PRICE_QUANTUM
    )
    sales_gap, sales_pct = _group_gap(
        row.average_weekly_sales,
        target.average_weekly_sales,
        _SALES_QUANTUM,
    )
    return row.model_copy(
        update={
            "price_gap_to_target_group": price_gap,
            "price_gap_pct_to_target_group": price_pct,
            "sales_gap_to_target_group": sales_gap,
            "sales_gap_pct_to_target_group": sales_pct,
        }
    )


def _group_gap(
    value: Decimal | None,
    target_value: Decimal | None,
    quantum: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    if value is None or target_value is None:
        return None, None
    gap = (value - target_value).quantize(quantum)
    pct = (gap / target_value).quantize(_RATIO_QUANTUM) if target_value > 0 else None
    return gap, pct


def _parameter_status(
    groups: Sequence[ParameterValueGroup],
    target_value: str | None,
    different_count: int,
) -> QuestionConclusionStatus:
    if target_value is None or different_count == 0:
        return QuestionConclusionStatus.NO_CONCLUSION
    alternate = [row for row in groups if not row.is_target_group]
    has_price = any(row.price_gap_to_target_group is not None for row in alternate)
    has_sales = any(row.sales_gap_to_target_group is not None for row in alternate)
    if has_price and has_sales:
        return QuestionConclusionStatus.CONCLUSION_AVAILABLE
    return QuestionConclusionStatus.PARTIAL_CONCLUSION


def _parameter_strength(count: int) -> QuestionConclusionStrength:
    if count == 0:
        return QuestionConclusionStrength.NONE
    if count == 1:
        return QuestionConclusionStrength.DIRECTIONAL
    if count <= 4:
        return QuestionConclusionStrength.SMALL_GROUP
    return QuestionConclusionStrength.GROUP


def _parameter_limitations(
    item: ParameterGroupComparisonInput,
    *,
    groups: Sequence[ParameterValueGroup],
    target_value: str | None,
    different_count: int,
    dispositions: Sequence[ParameterCandidateDisposition],
) -> list[str]:
    limitations = {
        "common_platforms_not_required",
        "common_weeks_not_required",
        "full_window_weekly_average",
        "market_association_not_causal",
        "ordinal_tiers_not_required",
    }
    if target_value is None:
        limitations.add("target_parameter_value_missing")
    elif different_count == 0:
        limitations.add("no_different_normalized_parameter_value")
    alternate = [row for row in groups if not row.is_target_group]
    if alternate and not any(
        row.price_gap_to_target_group is not None for row in alternate
    ):
        limitations.add("parameter_price_group_comparison_unavailable")
    if alternate and not any(
        row.sales_gap_to_target_group is not None for row in alternate
    ):
        limitations.add("parameter_sales_group_comparison_unavailable")
    skipped_count = sum(not row.used for row in dispositions)
    if skipped_count:
        limitations.add(f"parameter_candidate_rows_skipped:{skipped_count}")
    if item.exclude_from_core_sellpoints:
        limitations.add("confirmed_table_stake_not_core_highlight")
    return sorted(limitations)


def _parameter_business_conclusion(
    item: ParameterGroupComparisonInput,
    *,
    groups: Sequence[ParameterValueGroup],
    target_value: str | None,
    different_count: int,
) -> str:
    if target_value is None:
        return f"本品{item.parameter_name_cn}取值缺失，暂不能与其他参数取值比较。"
    if different_count == 0:
        return f"现有参照未出现区别于本品{target_value}的{item.parameter_name_cn}取值。"
    prefix = f"本品{item.parameter_name_cn}为{target_value}，已与其他实际取值分组比较"
    if item.exclude_from_core_sellpoints:
        return (
            prefix
            + "；该能力已是基础配置，不作为核心卖点，但量价表现仍保留供产品取舍。"
        )
    alternate = [row for row in groups if not row.is_target_group]
    sales_rows = [row for row in alternate if row.sales_gap_to_target_group is not None]
    if sales_rows:
        leader = max(
            sales_rows,
            key=lambda row: (
                row.sales_gap_to_target_group or Decimal("0"),
                row.normalized_value,
            ),
        )
        gap = leader.sales_gap_to_target_group or Decimal("0")
        relation = "高" if gap > 0 else "低" if gap < 0 else "相当"
        return (
            prefix
            + f"；其中{leader.normalized_value}组周均销量较本品参数组{relation}"
            + f"{_number_cn(abs(gap))}台，可作为参数投入优先级参照。"
        )
    return prefix + "；现有价格和销量信息不足，先保留为配置差异，不作为量价卖点。"


def _market_observation_sort_key(
    row: MarketComparatorObservation,
) -> tuple[str, int, str]:
    return (
        row.market.sku_code,
        0 if row.candidate_use.source_type == CandidateSourceType.COMPETITOR else 1,
        row.candidate_use.source_type.value,
    )


def _parameter_observation_sort_key(
    row: ParameterValueObservation,
) -> tuple[str, int, str]:
    return (
        row.sku_code,
        0 if row.source_type.value == CandidateSourceType.COMPETITOR.value else 1,
        row.source_type.value,
    )


def _normalized_parameter_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _mean(values: Sequence[Decimal], quantum: Decimal) -> Decimal:
    return (sum(values, Decimal("0")) / Decimal(len(values))).quantize(quantum)


def _direction(gap: Decimal) -> MarketComparisonDirection:
    if gap > 0:
        return MarketComparisonDirection.TARGET_HIGHER
    if gap < 0:
        return MarketComparisonDirection.TARGET_LOWER
    return MarketComparisonDirection.EQUAL


def _direction_cn(direction: MarketComparisonDirection) -> str:
    if direction == MarketComparisonDirection.TARGET_HIGHER:
        return "高"
    if direction == MarketComparisonDirection.TARGET_LOWER:
        return "低"
    return "相当，差异为"


def _number_cn(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _dedupe_evidence_refs(
    rows: Sequence[SellpointValueEvidenceRef],
) -> list[SellpointValueEvidenceRef]:
    by_key = {
        (
            row.module_code,
            row.record_type,
            row.record_id,
            row.result_hash,
        ): row
        for row in rows
    }
    return [by_key[key] for key in sorted(by_key)]


def _json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (
            value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else [
                row.model_dump(mode="json") if hasattr(row, "model_dump") else row
                for row in value
            ]
            if isinstance(value, list)
            else value.value
            if hasattr(value, "value")
            else value
        )
        for key, value in payload.items()
    }


__all__ = [
    "SPV_V5_1_DIRECT_MARKET_METHOD_VERSION",
    "SPV_V5_1_PARAMETER_GROUP_METHOD_VERSION",
    "calculate_direct_market_comparison",
    "calculate_parameter_group_comparison",
    "calculate_parameter_group_comparisons",
]
