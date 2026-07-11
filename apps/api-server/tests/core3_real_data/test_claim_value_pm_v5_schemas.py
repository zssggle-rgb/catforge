from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldAllocation,
    BattlefieldPortfolioOption,
    BundlePriceInterval,
    CounterfactualCandidate,
    CounterfactualSet,
    ExpansionEligibility,
    ExpansionGap,
    IncrementDecomposition,
    IntervalEstimate,
    PmDecisionSummary,
    SellpointValueV5Context,
    SyntheticControlResult,
    SyntheticDiagnostics,
    ValueHighlight,
)


def test_eligible_candidate_requires_explicit_measure() -> None:
    with pytest.raises(ValidationError, match="eligible candidate requires"):
        CounterfactualCandidate(
            method="same_budget_pool",
            question="relative_highlight",
            stage="eligible",
            candidate_key="same-budget:peer",
            candidate_sku_codes=["PEER"],
            provenance="market_universe",
            control_dimensions={},
            reject_reasons=[],
        )


def test_rejected_candidate_can_represent_an_empty_synthetic_pool() -> None:
    result = CounterfactualCandidate(
        method="market_synthetic",
        question="without_value_baseline",
        stage="rejected",
        candidate_key="synthetic:empty",
        candidate_sku_codes=[],
        provenance="market_universe_broad_recall",
        control_dimensions={},
        reject_reasons=["broad_donor_pool_insufficient"],
    )

    assert result.candidate_sku_codes == []
    assert result.eligible_measures == []


def test_m11d_allocation_cannot_be_marked_incremental() -> None:
    with pytest.raises(ValidationError):
        BattlefieldAllocation(
            battlefield_code="BF_PICTURE",
            allocated_sales_volume=100,
            allocated_sales_amount=500000,
            allocation_weight=0.5,
            incremental=True,
            source_lineage_hash="hash",
            lineage_status="aligned",
        )


def test_net_increment_requires_gross_and_cannibalization() -> None:
    interval = IntervalEstimate(
        estimate=10,
        low=5,
        high=15,
        unit="sales_per_week",
        observational=True,
    )
    with pytest.raises(ValidationError, match="net requires"):
        IncrementDecomposition(
            gross_status="unidentifiable",
            cannibalization_status="unidentifiable",
            net_status="available",
            gross=None,
            cannibalization=None,
            net=interval,
            claim_types=["observational_net"],
            causal_claim=False,
        )


def test_empty_highlights_require_an_explicit_business_reason() -> None:
    with pytest.raises(ValidationError, match="empty highlights require"):
        PmDecisionSummary(
            highlights=[],
            price_summary_cn="当前价格承接待判断",
            volume_summary_cn="当前销量承接待判断",
            existing_battlefield_summary_cn="已有战场待判断",
            expansion_summary_cn="新战场待判断",
        )


def test_expansion_eligibility_requires_market_gate_and_donors() -> None:
    with pytest.raises(ValidationError, match="market gate"):
        ExpansionEligibility(
            stage="eligible",
            current_membership="excluded",
            immutable_market_gate_pass=False,
            gaps=[],
            donor_count=10,
            eligible=True,
            reasons=[],
        )


def test_g02_candidate_schema_matches_frozen_contract(repo_root: Path) -> None:
    from app.services.core3_real_data.analyst import claim_value_pm_v5_schemas

    contract = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v5/G02_schema_contract.json"
        ).read_text(encoding="utf-8")
    )["models"]["CounterfactualCandidate"]
    model = claim_value_pm_v5_schemas.CounterfactualCandidate

    assert set(model.model_fields) == set(contract["fields"])
    assert {
        key for key, field in model.model_fields.items() if field.is_required()
    } == set(contract["required"])


def test_all_models_match_contract_plus_g03_required_addendum(repo_root: Path) -> None:
    from app.services.core3_real_data.analyst import claim_value_pm_v5_schemas

    base = repo_root / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v5"
    contract = json.loads((base / "G02_schema_contract.json").read_text(encoding="utf-8"))
    addendum = json.loads(
        (base / "G03_schema_contract_addendum.json").read_text(encoding="utf-8")
    )
    additions = addendum["required_field_additions"]
    for name, spec in contract["models"].items():
        model = getattr(claim_value_pm_v5_schemas, name)
        assert set(model.model_fields) == set(spec["fields"]), name
        required = {
            key for key, field in model.model_fields.items() if field.is_required()
        }
        assert required == set(spec["required"]) | set(additions.get(name, [])), name


def test_all_v5_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CounterfactualCandidate(
            method="same_budget_pool",
            question="relative_highlight",
            stage="eligible",
            candidate_key="same-budget:peer",
            candidate_sku_codes=["PEER"],
            provenance="market_universe",
            control_dimensions={},
            eligible_measures=["market_position"],
            reject_reasons=[],
            hidden_amount=999,
        )


def _eligible_candidate() -> CounterfactualCandidate:
    return CounterfactualCandidate(
        method="same_budget_pool",
        question="relative_highlight",
        stage="eligible",
        candidate_key="same-budget:peer",
        candidate_sku_codes=["PEER"],
        provenance="market_universe",
        control_dimensions={},
        eligible_measures=["market_position"],
        reject_reasons=[],
    )


def _interval() -> IntervalEstimate:
    return IntervalEstimate(
        estimate=10,
        low=5,
        high=15,
        unit="sales_per_week",
        observational=True,
    )


def test_counterfactual_set_rejects_question_or_method_drift() -> None:
    candidate = _eligible_candidate()
    with pytest.raises(ValidationError, match="question must match"):
        CounterfactualSet(
            bundle_code="picture",
            question="price_realization",
            candidates=[candidate],
            highest_available_method=None,
            selection_reasons=[],
            set_hash="hash",
        )
    with pytest.raises(ValidationError, match="eligible candidate"):
        CounterfactualSet(
            bundle_code="picture",
            question="relative_highlight",
            candidates=[candidate],
            highest_available_method="direct_sku",
            selection_reasons=[],
            set_hash="hash",
        )


def test_interval_rejects_partial_or_reversed_values() -> None:
    with pytest.raises(ValidationError, match="all present or all null"):
        IntervalEstimate(
            estimate=10,
            low=None,
            high=15,
            unit="sales",
            observational=True,
        )
    with pytest.raises(ValidationError, match="inside low/high"):
        IntervalEstimate(
            estimate=20,
            low=5,
            high=15,
            unit="sales",
            observational=True,
        )


def test_synthetic_diagnostics_and_weights_guard_effects() -> None:
    with pytest.raises(ValidationError, match="cannot contain failed gates"):
        SyntheticDiagnostics(
            donor_count=5,
            max_weight=None,
            overlap_pass=True,
            balance_pass=True,
            leave_one_sign_consistency=None,
            placebo_percentile=None,
            gate_pass=True,
            failed_gates=["balance"],
        )
    with pytest.raises(ValidationError, match="require failed_gates"):
        SyntheticDiagnostics(
            donor_count=5,
            max_weight=None,
            overlap_pass=False,
            balance_pass=False,
            leave_one_sign_consistency=None,
            placebo_percentile=None,
            gate_pass=False,
            failed_gates=[],
        )
    passed = SyntheticDiagnostics(
        donor_count=5,
        max_weight=0.3,
        overlap_pass=True,
        balance_pass=True,
        leave_one_sign_consistency=0.9,
        placebo_percentile=0.9,
        gate_pass=True,
        failed_gates=[],
    )
    base = {
        "status": "available",
        "target_sku_code": "TARGET",
        "bundle_code": "picture",
        "donor_weights": {"A": 0.6, "B": 0.4},
        "balance": [],
        "observed_window": {},
        "sales_difference": _interval(),
        "diagnostics": passed,
        "causal_claim": False,
        "method_config_version": "v1",
        "sample_manifest_hash": "sample",
        "result_hash": "result",
    }
    assert SyntheticControlResult(**base).sales_difference is not None
    with pytest.raises(ValidationError, match="sum to one"):
        SyntheticControlResult(**{**base, "donor_weights": {"A": 0.8}})
    failed = SyntheticDiagnostics(
        donor_count=2,
        max_weight=None,
        overlap_pass=False,
        balance_pass=False,
        leave_one_sign_consistency=None,
        placebo_percentile=None,
        gate_pass=False,
        failed_gates=["donor_count"],
    )
    with pytest.raises(ValidationError, match="cannot expose effects"):
        SyntheticControlResult(
            **{**base, "status": "degraded", "diagnostics": failed}
        )


def test_bundle_price_interval_requires_all_strict_gates() -> None:
    estimate = IntervalEstimate(
        estimate=500,
        low=300,
        high=700,
        unit="CNY",
        observational=True,
        currency="CNY",
    )
    with pytest.raises(ValidationError, match="two pairs"):
        BundlePriceInterval(
            status="available",
            method="matched_equal_choice_price_gap",
            estimate=estimate,
            reference_price=5000,
            pair_count=1,
            model_family_count=1,
            gate_results={"stable": True},
            causal_claim=False,
            psychological_max_price=False,
            method_config_version="v2",
        )
    with pytest.raises(ValidationError, match="cannot expose amount"):
        BundlePriceInterval(
            status="unidentifiable",
            method="none",
            estimate=None,
            reference_price=5000,
            pair_count=0,
            model_family_count=0,
            gate_results={},
            causal_claim=False,
            psychological_max_price=False,
            method_config_version="v2",
        )


def test_available_increment_requires_each_matching_interval() -> None:
    with pytest.raises(ValidationError, match="available gross requires"):
        IncrementDecomposition(
            gross_status="available",
            cannibalization_status="unidentifiable",
            net_status="unidentifiable",
            gross=None,
            cannibalization=None,
            net=None,
            claim_types=[],
            causal_claim=False,
        )
    with pytest.raises(ValidationError, match="unavailable gross cannot"):
        IncrementDecomposition(
            gross_status="degraded",
            gross=_interval(),
            cannibalization_status="unidentifiable",
            net_status="unidentifiable",
            cannibalization=None,
            net=None,
            claim_types=["observational_gross"],
            causal_claim=False,
        )


def test_expansion_and_strengthening_options_are_mutually_exclusive() -> None:
    eligibility = ExpansionEligibility(
        stage="eligible",
        current_membership="excluded",
        immutable_market_gate_pass=True,
        gaps=[
            ExpansionGap(
                gap_code="claim",
                change_type="communication",
                mutable_in_scope=True,
                status="missing",
                evidence=[],
            )
        ],
        donor_count=5,
        eligible=True,
        reasons=[],
    )
    expansion = BattlefieldPortfolioOption(
        option_type="expand_excluded",
        battlefield_code="BF_NEW",
        current_membership="excluded",
        expansion_eligibility=eligibility,
        market_space={},
        evidence_boundary="观察性候选",
    )
    assert expansion.strengthen_path is None
    strengthening = BattlefieldPortfolioOption(
        option_type="strengthen_existing",
        battlefield_code="BF_EXISTING",
        current_membership="opportunity",
        strengthen_path="portfolio_priority",
        market_space={},
        evidence_boundary="已有战场",
    )
    assert strengthening.expansion_eligibility is None
    with pytest.raises(ValidationError, match="excluded membership"):
        BattlefieldPortfolioOption(
            option_type="expand_excluded",
            battlefield_code="BF_BAD",
            current_membership="opportunity",
            expansion_eligibility=eligibility,
            market_space={},
            evidence_boundary="bad",
        )


def test_nonempty_highlight_summary_cannot_carry_empty_reason() -> None:
    highlight = ValueHighlight(
        highlight_type="relative_value",
        bundle_code="picture",
        title_cn="画质组合形成相对亮点",
        reason_cn="同预算对照更强",
        comparison_basis_cn="同尺寸同预算",
        evidence_boundary_cn="观察性比较",
    )
    with pytest.raises(ValidationError, match="only valid for an empty"):
        PmDecisionSummary(
            highlights=[highlight],
            no_highlight_reason_cn="不应同时出现",
            price_summary_cn="价格",
            volume_summary_cn="销量",
            existing_battlefield_summary_cn="已有",
            expansion_summary_cn="拓展",
        )


def test_v5_context_rejects_scope_and_universe_drift() -> None:
    from tests.core3_real_data.test_claim_value_pm_v5_counterfactuals import (
        _v5_context,
    )

    context = _v5_context()
    payload = context.model_dump(mode="python")
    payload["project_id"] = "other-project"
    with pytest.raises(ValidationError, match="project_id"):
        SellpointValueV5Context(**payload)

    payload = context.model_dump(mode="python")
    payload["market_universe"].append(payload["market_universe"][0])
    with pytest.raises(ValidationError, match="unique"):
        SellpointValueV5Context(**payload)
