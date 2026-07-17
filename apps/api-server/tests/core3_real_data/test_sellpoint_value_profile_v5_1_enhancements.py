from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketImpliedWtp,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldPortfolioOption,
    ExpansionEligibility,
    IntervalEstimate,
    PerformanceArchetype,
    SyntheticControlResult,
    SyntheticDiagnostics,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_enhancements import (
    adapt_battlefield_portfolio_option,
    adapt_performance_archetypes,
    adapt_same_budget_market_archetype,
    adapt_strict_market_implied_wtp,
    adapt_synthetic_market_baseline,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_market_comparison import (
    calculate_direct_market_comparison,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    CompetitorProfileSkuMarketFacts,
    DirectMarketComparisonInput,
    MarketComparatorObservation,
    QuestionCandidateUse,
)


def _evidence(code: str) -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code="M07",
        record_type="market_reference",
        record_id=code,
        result_hash=f"hash-{code}",
    )


def _same_budget_direct(*, available: bool = True):
    use = QuestionCandidateUse(
        candidate_sku_code="TV-C1",
        source_type="market_reference",
        selected=True,
        usable_dimensions=["market_price", "weekly_sales"],
        selection_reasons=["same_budget_reference"],
    )
    return calculate_direct_market_comparison(
        DirectMarketComparisonInput(
            project_id="project-1",
            category_code="TV",
            target_sku_code="TV-TARGET",
            value_bundle_code="VALUE-1",
            method="same_budget_pool",
            target_market=CompetitorProfileSkuMarketFacts(
                sku_code="TV-TARGET",
                product_category="TV",
                weighted_price=Decimal("6000"),
                avg_weekly_sales_volume=Decimal("40"),
            ),
            comparators=[
                MarketComparatorObservation(
                    category_code="TV",
                    candidate_use=use,
                    market=CompetitorProfileSkuMarketFacts(
                        sku_code="TV-C1",
                        product_category="TV",
                        weighted_price=Decimal("5800") if available else None,
                        avg_weekly_sales_volume=Decimal("60") if available else None,
                    ),
                    evidence_refs=[_evidence("same-budget")],
                )
            ],
        )
    )


def _interval(value: float, *, unit: str) -> IntervalEstimate:
    return IntervalEstimate(
        estimate=value,
        low=value,
        high=value,
        unit=unit,
        observational=True,
        currency="CNY" if unit == "CNY" else None,
    )


def _archetype(
    role: str,
    *,
    prevalence: float,
    sales: float,
    count: int = 3,
) -> PerformanceArchetype:
    return PerformanceArchetype(
        role=role,
        metric="avg_weekly_sales_volume",
        sku_count=count,
        representative_sku_codes=[f"{role}-{index}" for index in range(count)],
        bundle_prevalence={"VALUE-1": prevalence},
        user_outcome_prevalence={"clear_picture": prevalence},
        price_interval=_interval(5500, unit="CNY"),
        volume_interval=_interval(sales, unit="units_per_week"),
        residual_interval=_interval(sales - 50, unit="units_per_week"),
        stability=1.0,
        limitations=["full_window_weekly_average_ranking"],
        causal_claim=False,
        method_config_version="archetype-v1",
        sample_manifest_hash=f"sample-{role}",
        result_hash=f"result-{role}",
    )


def _synthetic(*, available: bool) -> SyntheticControlResult:
    donors = {f"DONOR-{index}": 0.2 for index in range(5)} if available else {}
    return SyntheticControlResult(
        status="available" if available else "degraded",
        target_sku_code="TV-TARGET",
        bundle_code="VALUE-1",
        donor_weights=donors,
        effective_donor_count=5 if available else None,
        balance=[],
        observed_window={"basis": "full_window_weekly_average"},
        price_difference=_interval(300, unit="CNY") if available else None,
        sales_difference=(_interval(20, unit="units_per_week") if available else None),
        diagnostics=SyntheticDiagnostics(
            donor_count=5 if available else 3,
            max_weight=0.2 if available else None,
            overlap_pass=available,
            balance_pass=available,
            leave_one_sign_consistency=1.0 if available else None,
            placebo_percentile=1.0 if available else None,
            gate_pass=available,
            failed_gates=[] if available else ["eligible_donor_count_insufficient"],
        ),
        limitations=["observational_not_causal"],
        causal_claim=False,
        method_config_version="synthetic-v1",
        sample_manifest_hash="synthetic-sample",
        result_hash=f"synthetic-{available}",
    )


def _available_wtp() -> MarketImpliedWtp:
    stable = {"pair-a": {"stable": True}, "pair-b": {"stable": True}}
    return MarketImpliedWtp(
        status="available",
        method="matched_equal_choice_price_gap",
        method_config_version="sellpoint_value_pm_v4_matched_wtp_config_v2",
        estimate_low=400,
        estimate_high=600,
        reference_price=5500,
        pair_count=2,
        model_family_count=2,
        sensitivity_summary={
            "leave_one_week_out": {},
            "cluster_week_bootstrap": stable,
            "joint_crossing_stability": stable,
            "pair_quality_weights": {},
            "weighted_median_center": 500,
            "conservative_interval_components": {},
        },
        causal_claim=False,
        psychological_max_price=False,
    )


def test_same_budget_single_reference_becomes_visible_directional_archetype() -> None:
    direct = _same_budget_direct()

    result = adapt_same_budget_market_archetype(direct)

    assert result.status == "conclusion_available"
    assert result.strength == "directional"
    assert result.visible_by_default is True
    assert result.groups[0].role == "same_budget"
    assert result.groups[0].average_price == Decimal("5800.0000")
    assert result.source_result_hashes == [direct.result_hash]
    assert result.causal_claim is False


def test_unavailable_same_budget_result_stays_local_and_hidden() -> None:
    direct = _same_budget_direct(available=False)

    result = adapt_same_budget_market_archetype(direct)

    assert direct.status == "no_conclusion"
    assert result.status == "no_conclusion"
    assert result.visible_by_default is False
    assert result.review_required is False


def test_high_low_archetype_explains_value_combination_and_is_deterministic() -> None:
    high = _archetype("high_performance", prevalence=0.8, sales=90)
    low = _archetype("low_performance", prevalence=0.2, sales=30)

    first = adapt_performance_archetypes(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        archetypes=[high, low],
        evidence_refs=[_evidence("performance")],
    )
    second = adapt_performance_archetypes(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        archetypes=[low, high],
        evidence_refs=[_evidence("performance")],
    )

    assert first == second
    assert first.status == "conclusion_available"
    assert first.strength == "small_group"
    assert [row.role for row in first.groups] == [
        "high_performance",
        "low_performance",
    ]
    assert "高销量组合中更常见" in first.business_conclusion_cn


def test_unstable_performance_archetype_is_hidden_without_review() -> None:
    unstable = _archetype("unstable", prevalence=0, sales=0, count=0)

    result = adapt_performance_archetypes(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        archetypes=[unstable],
    )

    assert result.status == "no_conclusion"
    assert result.strength == "none"
    assert result.visible_by_default is False
    assert result.review_required is False


def test_available_synthetic_baseline_is_observational_and_visible() -> None:
    result = adapt_synthetic_market_baseline(
        project_id="project-1",
        category_code="TV",
        source=_synthetic(available=True),
        evidence_refs=[_evidence("synthetic")],
    )

    assert result.status == "conclusion_available"
    assert result.strength == "group"
    assert result.donor_count == 5
    assert result.price_difference_estimate == Decimal("300.0")
    assert result.sales_difference_estimate == Decimal("20.0")
    assert result.visible_by_default is True
    assert result.causal_claim is False


def test_failed_synthetic_is_hidden_and_does_not_change_direct_market_result() -> None:
    direct = _same_budget_direct()
    result = adapt_synthetic_market_baseline(
        project_id="project-1",
        category_code="TV",
        source=_synthetic(available=False),
    )

    assert result.status == "no_conclusion"
    assert result.visible_by_default is False
    assert result.review_required is False
    assert result.failed_gates == ["eligible_donor_count_insufficient"]
    assert direct.status == "conclusion_available"


def test_available_strict_wtp_exposes_amount_only_after_all_gates() -> None:
    result = adapt_strict_market_implied_wtp(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        source=_available_wtp(),
        evidence_refs=[_evidence("wtp")],
    )

    assert result.status == "conclusion_available"
    assert result.estimate_low == Decimal("400.0")
    assert result.estimate_center == Decimal("500.0")
    assert result.estimate_high == Decimal("600.0")
    assert result.visible_by_default is True
    assert all(result.gate_results.values())
    assert result.psychological_max_price is False


def test_unavailable_strict_wtp_has_no_amount_review_or_default_surface() -> None:
    source = MarketImpliedWtp(
        status="insufficient",
        method="none",
        method_config_version="sellpoint_value_pm_v4_matched_wtp_config_v2",
        pair_count=0,
        model_family_count=0,
        exclusion_reasons=["pair_count_insufficient"],
        causal_claim=False,
        psychological_max_price=False,
    )

    result = adapt_strict_market_implied_wtp(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        source=source,
    )

    assert result.status == "no_conclusion"
    assert result.estimate_low is None
    assert result.estimate_high is None
    assert result.visible_by_default is False
    assert result.review_required is False


def test_entered_battlefield_returns_strengthening_path_not_new_entry() -> None:
    option = BattlefieldPortfolioOption(
        option_type="strengthen_existing",
        battlefield_code="BF-PICTURE",
        current_membership="primary",
        strengthen_path="portfolio_priority",
        expansion_eligibility=None,
        market_space={"weekly_sales": 100},
        current_allocation=None,
        price_reference=None,
        volume_reference=None,
        increment=None,
        evidence_boundary="该战场已经进入，当前应优化产品组合中的优先级。",
        limitations=[],
    )

    result = adapt_battlefield_portfolio_option(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        option=option,
        source_result_hash="battlefield-hash",
    )

    assert result.status == "conclusion_available"
    assert result.visible_by_default is True
    assert result.groups[0].facts["option_type"] == "strengthen_existing"
    assert "已经进入" in result.business_conclusion_cn


def test_unready_new_battlefield_is_hidden_without_blocking_existing_results() -> None:
    eligibility = ExpansionEligibility(
        stage="deferred_unknown",
        current_membership="excluded",
        immutable_market_gate_pass=None,
        task_group_adjacency=None,
        gaps=[],
        donor_count=0,
        overlap_risk="unknown",
        eligible=False,
        reasons=["immutable_market_gate_unknown"],
    )
    option = BattlefieldPortfolioOption(
        option_type="expand_excluded",
        battlefield_code="BF-NEW",
        current_membership="excluded",
        strengthen_path=None,
        expansion_eligibility=eligibility,
        market_space={},
        current_allocation=None,
        price_reference=None,
        volume_reference=None,
        increment=None,
        evidence_boundary="关键进入条件仍未知，暂不能判断是否可拓展。",
        limitations=["immutable_market_gate_unknown"],
    )

    result = adapt_battlefield_portfolio_option(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        option=option,
        source_result_hash="battlefield-new-hash",
    )

    assert result.status == "no_conclusion"
    assert result.visible_by_default is False
    assert result.review_required is False
    assert _same_budget_direct().status == "conclusion_available"


@pytest.mark.parametrize("category_code", ["REFRIGERATOR", "WASHER"])
def test_enhancement_adapters_reject_unsupported_category(category_code: str) -> None:
    with pytest.raises(ValueError, match="TV or AC"):
        adapt_synthetic_market_baseline(
            project_id="project-1",
            category_code=category_code,
            source=_synthetic(available=False),
        )
