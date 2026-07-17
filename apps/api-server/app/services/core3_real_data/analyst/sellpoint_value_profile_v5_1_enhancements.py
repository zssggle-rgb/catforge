"""Optional market-archetype, synthetic, and strict-WTP adapters for V5.1."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketImpliedWtp,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_realization import (
    build_bundle_price_interval,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldPortfolioOption,
    PerformanceArchetype,
    SyntheticControlResult,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    DirectMarketComparisonResult,
    MarketArchetypeEnhancementResult,
    MarketArchetypeGroupSnapshot,
    MarketArchetypeMethod,
    QuestionConclusionStatus,
    QuestionConclusionStrength,
    StrictMarketImpliedWtpResult,
    SyntheticMarketBaselineResult,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_ARCHETYPE_ADAPTER_VERSION = "sellpoint_value_market_archetype_v5_1"
SPV_V5_1_SYNTHETIC_ADAPTER_VERSION = "sellpoint_value_synthetic_baseline_v5_1"
SPV_V5_1_STRICT_WTP_ADAPTER_VERSION = "sellpoint_value_strict_wtp_v5_1"


def adapt_same_budget_market_archetype(
    direct: DirectMarketComparisonResult,
) -> MarketArchetypeEnhancementResult:
    """Promote a saved same-budget direct result into the archetype layer."""

    direct = DirectMarketComparisonResult.model_validate(
        direct.model_dump(mode="python")
    )
    if direct.method != "same_budget_pool":
        raise ValueError("same-budget archetype requires same_budget_pool result")
    available = direct.status in {
        QuestionConclusionStatus.CONCLUSION_AVAILABLE,
        QuestionConclusionStatus.PARTIAL_CONCLUSION,
    }
    groups = (
        [
            MarketArchetypeGroupSnapshot(
                role="same_budget",
                sku_codes=direct.used_comparator_sku_codes,
                sku_count=direct.comparator_count,
                average_price=(
                    direct.price_comparison.comparator_average
                    if direct.price_comparison is not None
                    else None
                ),
                average_weekly_sales=(
                    direct.sales_comparison.comparator_average
                    if direct.sales_comparison is not None
                    else None
                ),
                facts={
                    "price_comparison": _model_payload(direct.price_comparison),
                    "sales_comparison": _model_payload(direct.sales_comparison),
                },
                limitations=list(direct.limitations),
            )
        ]
        if available
        else []
    )
    payload: dict[str, Any] = {
        "project_id": direct.project_id,
        "category_code": direct.category_code,
        "target_sku_code": direct.target_sku_code,
        "value_bundle_code": direct.value_bundle_code,
        "method": MarketArchetypeMethod.SAME_BUDGET,
        "status": direct.status,
        "strength": _archetype_strength_from_direct(direct.strength),
        "groups": groups,
        "business_conclusion_cn": (
            f"同预算产品的市场表现显示：{direct.business_conclusion_cn}"
            if available
            else "当前同预算参照尚未形成可用量价结果。"
        ),
        "visible_by_default": available,
        "causal_claim": False,
        "limitations": sorted(
            {
                *direct.limitations,
                "same_budget_market_association_not_causal",
            }
        ),
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": list(direct.evidence_refs),
        "source_result_hashes": [direct.result_hash],
    }
    return _market_archetype_result(payload)


def adapt_performance_archetypes(
    *,
    project_id: str,
    category_code: str,
    target_sku_code: str,
    value_bundle_code: str,
    archetypes: Sequence[PerformanceArchetype],
    evidence_refs: Sequence[SellpointValueEvidenceRef] = (),
) -> MarketArchetypeEnhancementResult:
    """Wrap saved high/low value combinations without rerunning their model."""

    if category_code not in {"TV", "AC"}:
        raise ValueError("performance archetype category must be TV or AC")
    rows = [
        PerformanceArchetype.model_validate(row.model_dump(mode="python"))
        for row in archetypes
    ]
    roles = [row.role for row in rows]
    if len(roles) != len(set(roles)):
        raise ValueError("performance archetype roles must be unique")
    usable = [
        row
        for row in rows
        if row.role in {"high_performance", "low_performance"} and row.sku_count > 0
    ]
    usable_roles = {row.role for row in usable}
    if {"high_performance", "low_performance"} <= usable_roles:
        status = QuestionConclusionStatus.CONCLUSION_AVAILABLE
    elif usable:
        status = QuestionConclusionStatus.PARTIAL_CONCLUSION
    else:
        status = QuestionConclusionStatus.NO_CONCLUSION
    strength = (
        _sample_strength(min(row.sku_count for row in usable))
        if usable
        else QuestionConclusionStrength.NONE
    )
    groups = [
        MarketArchetypeGroupSnapshot(
            role=row.role,
            sku_codes=sorted(set(row.representative_sku_codes)),
            sku_count=max(row.sku_count, len(set(row.representative_sku_codes))),
            average_price=_interval_estimate(row.price_interval),
            average_weekly_sales=_interval_estimate(row.volume_interval),
            value_bundle_prevalence={
                key: _decimal(value)
                for key, value in sorted(row.bundle_prevalence.items())
            },
            user_outcome_prevalence={
                key: _decimal(value)
                for key, value in sorted(row.user_outcome_prevalence.items())
            },
            facts={
                "metric": row.metric,
                "stability": row.stability,
                "residual_interval": _model_payload(row.residual_interval),
            },
            limitations=sorted(set(row.limitations)),
        )
        for row in sorted(usable, key=lambda item: item.role)
    ]
    limitations = sorted(
        {
            "performance_archetype_market_association_not_causal",
            *(item for row in rows for item in row.limitations),
            *(
                ["high_low_performance_pair_incomplete"]
                if status != QuestionConclusionStatus.CONCLUSION_AVAILABLE
                else []
            ),
        }
    )
    payload: dict[str, Any] = {
        "project_id": project_id,
        "category_code": category_code,
        "target_sku_code": target_sku_code,
        "value_bundle_code": value_bundle_code,
        "method": MarketArchetypeMethod.PERFORMANCE_CONTRAST,
        "status": status,
        "strength": strength,
        "groups": groups,
        "business_conclusion_cn": _performance_business_conclusion(
            value_bundle_code,
            usable,
        ),
        "visible_by_default": status != QuestionConclusionStatus.NO_CONCLUSION,
        "causal_claim": False,
        "limitations": limitations,
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": _dedupe_evidence_refs(evidence_refs),
        "source_result_hashes": sorted({row.result_hash for row in rows}),
    }
    return _market_archetype_result(payload)


def adapt_battlefield_portfolio_option(
    *,
    project_id: str,
    category_code: str,
    target_sku_code: str,
    value_bundle_code: str,
    option: BattlefieldPortfolioOption,
    source_result_hash: str,
    evidence_refs: Sequence[SellpointValueEvidenceRef] = (),
) -> MarketArchetypeEnhancementResult:
    """Separate strengthening an entered battlefield from entering a new one."""

    if category_code not in {"TV", "AC"}:
        raise ValueError("battlefield archetype category must be TV or AC")
    option = BattlefieldPortfolioOption.model_validate(option.model_dump(mode="python"))
    eligible = option.option_type == "strengthen_existing" or (
        option.expansion_eligibility is not None
        and option.expansion_eligibility.eligible
    )
    stage = (
        option.strengthen_path
        if option.option_type == "strengthen_existing"
        else option.expansion_eligibility.stage
        if option.expansion_eligibility is not None
        else "unknown"
    )
    group = MarketArchetypeGroupSnapshot(
        role=f"{option.option_type}:{option.battlefield_code}",
        sku_codes=[],
        sku_count=0,
        facts={
            "battlefield_code": option.battlefield_code,
            "current_membership": option.current_membership,
            "option_type": option.option_type,
            "stage": stage,
            "market_space": option.market_space,
            "current_allocation": _model_payload(option.current_allocation),
            "price_reference": _model_payload(option.price_reference),
            "volume_reference": _model_payload(option.volume_reference),
        },
        limitations=sorted(set(option.limitations)),
    )
    status = (
        QuestionConclusionStatus.CONCLUSION_AVAILABLE
        if eligible
        else QuestionConclusionStatus.NO_CONCLUSION
    )
    payload: dict[str, Any] = {
        "project_id": project_id,
        "category_code": category_code,
        "target_sku_code": target_sku_code,
        "value_bundle_code": value_bundle_code,
        "method": MarketArchetypeMethod.ADJACENT_BATTLEFIELD,
        "status": status,
        "strength": (
            QuestionConclusionStrength.DIRECTIONAL
            if eligible
            else QuestionConclusionStrength.NONE
        ),
        "groups": [group],
        "business_conclusion_cn": option.evidence_boundary,
        "visible_by_default": eligible,
        "causal_claim": False,
        "limitations": sorted(
            {
                *option.limitations,
                "battlefield_market_reference_not_causal",
            }
        ),
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": _dedupe_evidence_refs(evidence_refs),
        "source_result_hashes": [source_result_hash],
    }
    return _market_archetype_result(payload)


def adapt_synthetic_market_baseline(
    *,
    project_id: str,
    category_code: str,
    source: SyntheticControlResult,
    evidence_refs: Sequence[SellpointValueEvidenceRef] = (),
) -> SyntheticMarketBaselineResult:
    """Keep strict synthetic diagnostics local to the synthetic method."""

    if category_code not in {"TV", "AC"}:
        raise ValueError("synthetic baseline category must be TV or AC")
    source = SyntheticControlResult.model_validate(source.model_dump(mode="python"))
    price = _interval_estimate(source.price_difference)
    sales = _interval_estimate(source.sales_difference)
    available = (
        source.status == "available"
        and source.diagnostics.gate_pass
        and (price is not None or sales is not None)
    )
    donor_codes = sorted(source.donor_weights)
    payload: dict[str, Any] = {
        "project_id": project_id,
        "category_code": category_code,
        "target_sku_code": source.target_sku_code,
        "value_bundle_code": source.bundle_code,
        "status": (
            QuestionConclusionStatus.CONCLUSION_AVAILABLE
            if available
            else QuestionConclusionStatus.NO_CONCLUSION
        ),
        "strength": (
            _sample_strength(len(donor_codes))
            if available
            else QuestionConclusionStrength.NONE
        ),
        "source_status": source.status,
        "donor_sku_codes": donor_codes,
        "donor_count": len(donor_codes),
        "effective_donor_count": (
            _decimal(source.effective_donor_count)
            if source.effective_donor_count is not None
            else None
        ),
        "price_difference_estimate": price if available else None,
        "sales_difference_estimate": sales if available else None,
        "gate_pass": source.diagnostics.gate_pass,
        "failed_gates": sorted(set(source.diagnostics.failed_gates)),
        "business_conclusion_cn": _synthetic_business_conclusion(
            price, sales, available
        ),
        "visible_by_default": available,
        "causal_claim": False,
        "limitations": sorted(
            {
                *source.limitations,
                *source.diagnostics.failed_gates,
                "synthetic_market_baseline_not_causal",
            }
        ),
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": _dedupe_evidence_refs(evidence_refs),
        "source_result_hash": source.result_hash,
    }
    return SyntheticMarketBaselineResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_SYNTHETIC_ADAPTER_VERSION,
        ),
    )


def adapt_strict_market_implied_wtp(
    *,
    project_id: str,
    category_code: str,
    target_sku_code: str,
    value_bundle_code: str,
    source: MarketImpliedWtp | None,
    evidence_refs: Sequence[SellpointValueEvidenceRef] = (),
) -> StrictMarketImpliedWtpResult:
    """Expose amounts only when the existing strict WTP contract passed."""

    if category_code not in {"TV", "AC"}:
        raise ValueError("strict WTP category must be TV or AC")
    if source is not None:
        source = MarketImpliedWtp.model_validate(source.model_dump(mode="python"))
    interval = build_bundle_price_interval(source)
    available = interval.status == "available" and interval.estimate is not None
    estimate = interval.estimate
    payload: dict[str, Any] = {
        "project_id": project_id,
        "category_code": category_code,
        "target_sku_code": target_sku_code,
        "value_bundle_code": value_bundle_code,
        "status": (
            QuestionConclusionStatus.CONCLUSION_AVAILABLE
            if available
            else QuestionConclusionStatus.NO_CONCLUSION
        ),
        "method": interval.method,
        "estimate_low": _decimal(estimate.low)
        if available and estimate is not None
        else None,
        "estimate_center": (
            _decimal(estimate.estimate) if available and estimate is not None else None
        ),
        "estimate_high": _decimal(estimate.high)
        if available and estimate is not None
        else None,
        "reference_price": (
            _decimal(interval.reference_price)
            if available and interval.reference_price is not None
            else None
        ),
        "currency": (
            estimate.currency
            if available and estimate is not None and estimate.currency
            else source.currency
            if source is not None
            else "CNY"
        ),
        "pair_count": interval.pair_count,
        "model_family_count": interval.model_family_count,
        "gate_results": dict(sorted(interval.gate_results.items())),
        "business_conclusion_cn": (
            f"该组用户价值对应的严格市场隐含支付意愿为"
            f"{_number_cn(_decimal(estimate.low))}—{_number_cn(_decimal(estimate.high))}元。"
            if available and estimate is not None
            else "严格金额结果尚未形成；直接量价、用户价值和产品取舍结论继续有效。"
        ),
        "visible_by_default": available,
        "causal_claim": False,
        "psychological_max_price": False,
        "limitations": sorted(set(interval.limitations)),
        "review_required": False,
        "review_reasons": [],
        "evidence_refs": _dedupe_evidence_refs(evidence_refs),
        "source_status": source.status if source is not None else "missing",
    }
    return StrictMarketImpliedWtpResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_STRICT_WTP_ADAPTER_VERSION,
        ),
    )


def _market_archetype_result(
    payload: dict[str, Any],
) -> MarketArchetypeEnhancementResult:
    return MarketArchetypeEnhancementResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_ARCHETYPE_ADAPTER_VERSION,
        ),
    )


def _performance_business_conclusion(
    value_bundle_code: str,
    rows: Sequence[PerformanceArchetype],
) -> str:
    by_role = {row.role: row for row in rows}
    high = by_role.get("high_performance")
    low = by_role.get("low_performance")
    if high is None or low is None:
        return "当前仅形成单侧销量组，先作为方向性市场参照。"
    high_prevalence = high.bundle_prevalence.get(value_bundle_code, 0.0)
    low_prevalence = low.bundle_prevalence.get(value_bundle_code, 0.0)
    if high_prevalence > low_prevalence:
        return "该用户价值在高销量组合中更常见，应优先核对本品是否具备同等体验兑现。"
    if high_prevalence < low_prevalence:
        return "该用户价值在低销量组合中更常见，不能仅凭配置名称继续追加投入。"
    return "该用户价值在高、低销量组合中的出现率相近，当前不构成规模差异线索。"


def _synthetic_business_conclusion(
    price: Decimal | None,
    sales: Decimal | None,
    available: bool,
) -> str:
    if not available:
        return "市场合成基线未通过自身诊断，本方法不输出量价差。"
    parts = []
    if price is not None:
        parts.append(f"本品价格相对无该组价值的市场基线相差{_number_cn(price)}元")
    if sales is not None:
        parts.append(f"周均销量相差{_number_cn(sales)}台")
    return "，".join(parts) + "；这是观察性市场基线，不是单卖点因果增量。"


def _archetype_strength_from_direct(
    strength: QuestionConclusionStrength,
) -> QuestionConclusionStrength:
    return (
        QuestionConclusionStrength.DIRECTIONAL
        if strength == QuestionConclusionStrength.SINGLE
        else strength
    )


def _sample_strength(count: int) -> QuestionConclusionStrength:
    if count <= 0:
        return QuestionConclusionStrength.NONE
    if count == 1:
        return QuestionConclusionStrength.DIRECTIONAL
    if count <= 4:
        return QuestionConclusionStrength.SMALL_GROUP
    return QuestionConclusionStrength.GROUP


def _interval_estimate(value: Any | None) -> Decimal | None:
    if value is None or value.estimate is None:
        return None
    return _decimal(value.estimate)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _number_cn(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _model_payload(value: Any | None) -> Any:
    return value.model_dump(mode="json") if value is not None else None


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
    "SPV_V5_1_ARCHETYPE_ADAPTER_VERSION",
    "SPV_V5_1_STRICT_WTP_ADAPTER_VERSION",
    "SPV_V5_1_SYNTHETIC_ADAPTER_VERSION",
    "adapt_battlefield_portfolio_option",
    "adapt_performance_archetypes",
    "adapt_same_budget_market_archetype",
    "adapt_strict_market_implied_wtp",
    "adapt_synthetic_market_baseline",
]
