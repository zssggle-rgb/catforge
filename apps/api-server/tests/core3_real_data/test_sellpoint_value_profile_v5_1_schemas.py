from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_config import (
    sellpoint_value_v5_1_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_COMPETITOR_FACT_GROUPS,
    CompetitorProfileCandidateRef,
    CompetitorProfilePairFacts,
    CompetitorProfileSkuMarketFacts,
    ConclusionDistribution,
    DirectMarketGap,
    ProfileReleaseAssessment,
    QuantificationResult,
    QuestionCandidateUse,
    ReleaseIntegritySummary,
    SellpointValueCompetitorSource,
    TableStakeAssessment,
    ValueQuantificationStack,
)


def _pair_facts() -> CompetitorProfilePairFacts:
    values = {group: {} for group in SPV_V5_1_COMPETITOR_FACT_GROUPS}
    values["basis"] = {"same_market": True}
    values["ranking_gate_reasons"] = []
    values["shared_business_context"] = []
    return CompetitorProfilePairFacts(
        **values,
        available_fact_groups=["basis"],
        unavailable_fact_groups=[
            group for group in SPV_V5_1_COMPETITOR_FACT_GROUPS if group != "basis"
        ],
    )


def _candidate(
    rank: int,
    *,
    selected_rank: int | None = None,
) -> CompetitorProfileCandidateRef:
    return CompetitorProfileCandidateRef(
        candidate_sku_code=f"TV-C{rank}",
        source_rank=rank,
        selected_rank=selected_rank,
        role="primary_direct" if selected_rank == 1 else "downtrade_diversion",
        role_cn="核心正面竞争" if selected_rank == 1 else "价格下探分流",
        business_score=Decimal("0.8"),
        pair_result_hash=f"pair-{rank}",
        market=CompetitorProfileSkuMarketFacts(
            sku_code=f"TV-C{rank}",
            product_category="TV",
            weighted_price=Decimal("5000"),
            avg_weekly_sales_volume=Decimal("50"),
        ),
        pair_facts=_pair_facts(),
    )


def _competitor_source(**overrides) -> SellpointValueCompetitorSource:
    candidates = [
        _candidate(1, selected_rank=2),
        _candidate(2),
        _candidate(3, selected_rank=1),
        _candidate(4, selected_rank=3),
        _candidate(5),
    ]
    payload = {
        "source": "competitor_profile_agent_snapshot_v2",
        "access_mode": "formal",
        "competitor_profile_version_id": "cp-version-1",
        "profile_version": "cp-profile-v2",
        "method_version": "competitor_profile_agent_snapshot_v2",
        "release_status": "published",
        "is_current": True,
        "project_id": "project-1",
        "category_code": "TV",
        "release_scope_key": "project-1:TV",
        "target_sku_code": "TV-TARGET",
        "target_market": {
            "sku_code": "TV-TARGET",
            "product_category": "TV",
            "weighted_price": 6000,
            "avg_weekly_sales_volume": 40,
        },
        "candidates": candidates,
        "priority_order": ["TV-C3", "TV-C1", "TV-C4"],
        "source_version_result_hash": "version-hash-1",
        "source_result_hash": "profile-hash-1",
    }
    payload.update(overrides)
    return SellpointValueCompetitorSource.model_validate(payload)


def _selected_use(code: str = "TV-C1") -> QuestionCandidateUse:
    return QuestionCandidateUse(
        candidate_sku_code=code,
        source_type="competitor",
        selected=True,
        usable_dimensions=["market"],
        unavailable_dimensions=["parameter"],
        selection_reasons=["market_available"],
    )


def test_saved_empty_fact_group_is_not_automatically_treated_as_missing() -> None:
    values = {group: {} for group in SPV_V5_1_COMPETITOR_FACT_GROUPS}
    values["ranking_gate_reasons"] = []
    values["shared_business_context"] = []

    facts = CompetitorProfilePairFacts(
        **values,
        available_fact_groups=list(SPV_V5_1_COMPETITOR_FACT_GROUPS),
        unavailable_fact_groups=[],
    )

    assert "parameter_claim_overlap" in facts.available_fact_groups


def _gap(count: int) -> DirectMarketGap:
    return DirectMarketGap(
        method="direct_comparable",
        comparator_sku_codes=[f"TV-C{index}" for index in range(1, count + 1)],
        comparator_count=count,
        strength="single" if count == 1 else "small_group" if count <= 4 else "group",
        target_price=Decimal("6000"),
        comparator_price=Decimal("5500"),
        price_gap_abs=Decimal("500"),
        price_gap_pct=Decimal("0.0909"),
    )


def _integrity(**overrides) -> ReleaseIntegritySummary:
    payload = {
        "expected_sku_count": 10,
        "generated_sku_count": 10,
        "generation_failure_count": 0,
        "invalid_profile_count": 0,
        "cross_category_count": 0,
        "duplicate_sku_count": 0,
        "dangling_reference_count": 0,
        "hash_mismatch_count": 0,
    }
    payload.update(overrides)
    return ReleaseIntegritySummary.model_validate(payload)


def test_formal_competitor_source_keeps_all_candidates_and_saved_top_three() -> None:
    source = _competitor_source()

    assert len(source.candidates) == 5
    assert source.priority_order == ["TV-C3", "TV-C1", "TV-C4"]
    assert [row.source_rank for row in source.candidates] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    ("release_status", "is_current"),
    [("draft", False), ("published", False)],
)
def test_formal_competitor_source_requires_current_published(
    release_status: str,
    is_current: bool,
) -> None:
    with pytest.raises(ValidationError, match="current published"):
        _competitor_source(release_status=release_status, is_current=is_current)


def test_explicit_preview_accepts_non_current_draft() -> None:
    source = _competitor_source(
        access_mode="preview",
        release_status="draft",
        is_current=False,
    )

    assert source.access_mode == "preview"


def test_preview_rejects_non_current_published_version() -> None:
    with pytest.raises(ValidationError, match="non-current draft or current published"):
        _competitor_source(
            access_mode="preview",
            release_status="published",
            is_current=False,
        )


def test_priority_order_must_match_saved_selection_ranks() -> None:
    with pytest.raises(ValidationError, match="priority order"):
        _competitor_source(priority_order=["TV-C1", "TV-C3", "TV-C4"])


def test_question_candidate_missing_dimension_does_not_block_available_dimension() -> (
    None
):
    use = _selected_use()

    assert use.selected is True
    assert use.usable_dimensions == ["market"]
    assert use.unavailable_dimensions == ["parameter"]


def test_unselected_candidate_requires_question_local_rejection_reason() -> None:
    with pytest.raises(ValidationError, match="question-local reasons"):
        QuestionCandidateUse(
            candidate_sku_code="TV-C1",
            source_type="competitor",
            selected=False,
            usable_dimensions=["market"],
        )


@pytest.mark.parametrize(
    ("count", "strength"),
    [(1, "single"), (2, "small_group"), (4, "small_group"), (5, "group")],
)
def test_direct_market_gap_strength_uses_low_comparator_threshold(
    count: int,
    strength: str,
) -> None:
    gap = _gap(count)

    assert gap.strength == strength
    assert gap.causal_claim is False


def test_direct_market_gap_rejects_strength_inconsistent_with_count() -> None:
    with pytest.raises(ValidationError, match="strength"):
        DirectMarketGap(
            method="direct_comparable",
            comparator_sku_codes=["TV-C1"],
            comparator_count=1,
            strength="group",
            target_weekly_sales=Decimal("20"),
            comparator_weekly_sales=Decimal("10"),
            sales_gap_abs=Decimal("10"),
            sales_gap_pct=Decimal("1"),
        )


def test_strict_wtp_no_conclusion_does_not_invalidate_direct_market_gap() -> None:
    direct = QuantificationResult(
        layer="direct_market_gap",
        method="direct_comparable",
        status="conclusion_available",
        strength="single",
        candidate_uses=[_selected_use()],
        facts={"target_weekly_average": "available"},
        result={"price_direction": "target_higher"},
        direct_market_gaps=[_gap(1)],
        result_hash="direct-hash",
    )
    strict = QuantificationResult(
        layer="strict_market_implied_wtp",
        method="matched_equal_choice_price_gap",
        status="no_conclusion",
        strength="none",
        limitations=["strict_gate_not_passed"],
        result_hash="strict-hash",
    )
    stack = ValueQuantificationStack(
        value_bundle_code="VALUE-1",
        results=[direct, strict],
    )

    assert stack.results[0].status == "conclusion_available"
    assert stack.results[1].status == "no_conclusion"
    assert stack.results[1].review_required is False


def test_no_conclusion_cannot_be_converted_to_automatic_review() -> None:
    with pytest.raises(ValidationError, match="not an automatic review"):
        QuantificationResult(
            layer="strict_market_implied_wtp",
            method="strict",
            status="no_conclusion",
            strength="none",
            limitations=["insufficient"],
            review_required=True,
            review_reasons=["insufficient"],
            result_hash="strict-hash",
        )


def test_table_stake_insufficient_sample_is_not_assessed_without_review() -> None:
    assessment = TableStakeAssessment(
        capability_code="hdmi_2_1",
        status="not_assessed",
        total_count=3,
        known_count=2,
        present_count=2,
        absent_count=0,
        missing_count=1,
        contradicted_count=0,
        minimum_known_count=5,
        prevalence_threshold=Decimal("0.8"),
        prevalence=Decimal("1"),
    )

    assert assessment.status == "not_assessed"
    assert assessment.review_required is False


def test_confirmed_table_stake_requires_positive_threshold() -> None:
    with pytest.raises(ValidationError, match="positive threshold"):
        TableStakeAssessment(
            capability_code="hdmi_2_1",
            status="confirmed_table_stake",
            total_count=5,
            known_count=5,
            present_count=3,
            absent_count=2,
            missing_count=0,
            contradicted_count=0,
            minimum_known_count=5,
            prevalence_threshold=Decimal("0.8"),
            prevalence=Decimal("0.6"),
        )


def test_insufficient_table_stake_sample_cannot_be_called_not_table_stake() -> None:
    with pytest.raises(ValidationError, match="sufficient known samples"):
        TableStakeAssessment(
            capability_code="hdmi_2_1",
            status="not_table_stake",
            total_count=3,
            known_count=2,
            present_count=1,
            absent_count=1,
            missing_count=1,
            contradicted_count=0,
            minimum_known_count=5,
            prevalence_threshold=Decimal("0.8"),
            prevalence=Decimal("0.5"),
        )


def test_partial_and_no_conclusion_profiles_are_limited_not_blocked() -> None:
    assessment = ProfileReleaseAssessment(
        release_quality_status="limited",
        conclusion_distribution=ConclusionDistribution(
            total_count=10,
            conclusion_available_count=4,
            partial_conclusion_count=3,
            no_conclusion_count=3,
            invalid_count=0,
        ),
        integrity=_integrity(),
        review_item_count=0,
    )

    assert assessment.release_quality_status == "limited"


def test_integrity_error_is_the_only_blocking_release_axis() -> None:
    assessment = ProfileReleaseAssessment(
        release_quality_status="blocked",
        conclusion_distribution=ConclusionDistribution(
            total_count=10,
            conclusion_available_count=10,
            partial_conclusion_count=0,
            no_conclusion_count=0,
            invalid_count=0,
        ),
        integrity=_integrity(hash_mismatch_count=1),
        review_item_count=0,
    )

    assert assessment.release_quality_status == "blocked"


def test_low_gate_defaults_are_non_blocking_for_both_categories() -> None:
    for category in ("TV", "AC"):
        config = sellpoint_value_v5_1_config(category)
        assert config.direct_market_gap.minimum_comparator_count == 1
        assert config.direct_market_gap.require_common_weeks is False
        assert config.direct_market_gap.require_common_platforms is False
        assert config.direct_market_gap.allow_weekly_average is True
        assert config.value_realization.minimum_shared_anchor_count == 1
        assert config.parameter_group.minimum_skus_per_value == 1
        assert config.parameter_group.require_ordinal_tier is False
        assert config.table_stake.insufficient_sample_requires_review is False
        assert config.synthetic_control.required_for_profile is False
        assert config.strict_market_implied_wtp.required_for_release is False


def test_default_config_returns_a_copy_and_rejects_unknown_category() -> None:
    first = sellpoint_value_v5_1_config("tv")
    second = sellpoint_value_v5_1_config("TV")
    first.table_stake.minimum_known_count = 10

    assert second.table_stake.minimum_known_count == 5
    with pytest.raises(ValueError, match="unsupported V5.1 category"):
        sellpoint_value_v5_1_config("REFRIGERATOR")
