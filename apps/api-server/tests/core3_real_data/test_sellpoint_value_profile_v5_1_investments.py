from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CapabilityCandidateFact,
    CapabilityComparisonScope,
    CapabilityInvestmentInput,
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_threshold_config import (
    capability_threshold_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_investments import (
    assess_capability_table_stake,
    build_local_investment_review_overlays,
    classify_local_capability_investment,
    classify_local_capability_investments,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    CapabilityInvestmentQuestionInput,
)


def _facts(statuses: list[str]) -> list[CapabilityCandidateFact]:
    return [
        CapabilityCandidateFact(
            candidate_sku_code=f"CANDIDATE-{index:02d}",
            fact_status=status,
            normalized_value=(
                True
                if status == "known_present"
                else False
                if status == "known_absent"
                else None
            ),
        )
        for index, status in enumerate(statuses)
    ]


def _scope(
    facts: list[CapabilityCandidateFact],
    *,
    category_code: str = "TV",
    complete: bool = True,
) -> CapabilityComparisonScope:
    return CapabilityComparisonScope(
        category_code=category_code,
        price_band="mid" if complete else None,
        product_form=(
            "wall_mounted"
            if category_code == "AC" and complete
            else "television"
            if complete
            else None
        ),
        size_relation=(
            "same_horsepower"
            if category_code == "AC" and complete
            else "same_size"
            if complete
            else None
        ),
        battlefield_codes=["BF-1"],
        competitor_roles=["direct"],
        candidate_scope_ids=[row.candidate_sku_code for row in facts],
        scope_hash=f"scope-{category_code}-{complete}",
    )


def _investment(
    *,
    capability_code: str = "CAP-1",
    facts: list[CapabilityCandidateFact] | None = None,
    category_code: str = "TV",
    complete_scope: bool = True,
    **overrides: Any,
) -> CapabilityInvestmentInput:
    facts = facts or _facts(
        [
            "known_present",
            "known_present",
            "known_absent",
            "known_absent",
            "known_absent",
        ]
    )
    payload: dict[str, Any] = {
        "capability_code": capability_code,
        "capability_name_cn": capability_code,
        "capability_kind": "capability",
        "target_fact_status": "known_present",
        "target_value": True,
        "investment_level": "standard",
        "candidate_facts": facts,
        "comparison_scope": _scope(
            facts,
            category_code=category_code,
            complete=complete_scope,
        ),
        "user_feedback_status": "unknown",
        "relative_experience_status": "unknown",
        "competitor_experience_stronger": None,
        "price_support": "unknown",
        "volume_support": "unknown",
        "choice_support": "unknown",
        "current_competitive_performance": "unknown",
    }
    payload.update(overrides)
    return CapabilityInvestmentInput.model_validate(payload)


def _scoped(
    *,
    question_code: str = "investment_conversion",
    value_bundle_code: str = "VALUE-1",
    item: CapabilityInvestmentInput | None = None,
    project_id: str = "project-1",
    target_sku_code: str | None = None,
) -> CapabilityInvestmentQuestionInput:
    item = item or _investment()
    category_code = item.comparison_scope.category_code
    return CapabilityInvestmentQuestionInput(
        project_id=project_id,
        category_code=category_code,
        target_sku_code=target_sku_code or f"{category_code}-TARGET",
        question_code=question_code,
        value_bundle_code=value_bundle_code,
        investment=item,
    )


def test_table_stake_counts_known_missing_and_not_assessed_without_review() -> None:
    item = _investment(
        facts=_facts(
            [
                "known_present",
                "known_present",
                "known_present",
                "known_absent",
                "missing",
                "missing",
            ]
        )
    )

    assessment = assess_capability_table_stake(item)

    assert assessment.status == "not_assessed"
    assert assessment.known_count == 4
    assert assessment.present_count == 3
    assert assessment.absent_count == 1
    assert assessment.missing_count == 2
    assert assessment.contradicted_count == 0
    assert assessment.prevalence == 0.75
    assert assessment.exclude_from_core_sellpoints is False
    assert assessment.review_required is False
    assert assessment.review_reasons == []


def test_incomplete_scope_is_not_assessed_and_not_reviewed() -> None:
    item = _investment(
        facts=_facts(["known_present"] * 5),
        complete_scope=False,
    )

    assessment = assess_capability_table_stake(item)

    assert assessment.status == "not_assessed"
    assert assessment.scope_complete is False
    assert assessment.review_required is False
    assert assessment.limitations == ["comparison_scope_incomplete"]


def test_confirmed_table_stake_only_excludes_that_capability_from_core_sellpoints() -> (
    None
):
    item = _investment(
        capability_code="hdmi_2_1",
        facts=_facts(
            [
                "known_present",
                "known_present",
                "known_present",
                "known_present",
                "known_absent",
            ]
        ),
        user_feedback_status="realized_advantage",
        relative_experience_status="advantage",
        price_support="positive",
    )

    decision = classify_local_capability_investment(_scoped(item=item))

    assert decision.table_stake_assessment.status == "confirmed_table_stake"
    assert decision.table_stake_assessment.exclude_from_core_sellpoints is True
    assert decision.classification == "table_stake"
    assert decision.status == "conclusion_available"
    assert decision.review_required is False


def test_unknown_investment_is_no_conclusion_not_review() -> None:
    decision = classify_local_capability_investment(_scoped())

    assert decision.classification == "unknown"
    assert decision.status == "no_conclusion"
    assert decision.confidence is None
    assert decision.review_required is False
    assert decision.review_reasons == []


def test_missing_target_fact_is_no_conclusion_not_review() -> None:
    decision = classify_local_capability_investment(
        _scoped(item=_investment(target_fact_status="missing", target_value=None))
    )

    assert decision.status == "no_conclusion"
    assert decision.review_required is False
    assert "target_fact" in decision.unavailable_dimensions


def test_direct_target_conflict_creates_only_local_invalid_review() -> None:
    decision = classify_local_capability_investment(
        _scoped(item=_investment(target_fact_status="contradicted"))
    )

    assert decision.status == "invalid"
    assert decision.classification == "unknown"
    assert decision.review_required is True
    assert decision.review_reasons == ["target_fact_contradicted"]


def test_candidate_fact_conflict_stays_inside_table_stake_assessment() -> None:
    item = _investment(
        facts=_facts(
            [
                "known_present",
                "known_present",
                "known_absent",
                "known_absent",
                "contradicted",
            ]
        ),
        user_feedback_status="realized_advantage",
        relative_experience_status="advantage",
        price_support="positive",
    )

    decision = classify_local_capability_investment(_scoped(item=item))

    assert decision.table_stake_assessment.status == "invalid"
    assert decision.table_stake_assessment.review_required is True
    assert decision.classification == "retain"
    assert decision.status == "conclusion_available"
    assert decision.review_required is False


def test_retain_and_unconverted_use_value_evidence_without_global_confidence_gate() -> (
    None
):
    retained = classify_local_capability_investment(
        _scoped(
            value_bundle_code="VALUE-RETAIN",
            item=_investment(
                capability_code="picture_quality",
                user_feedback_status="realized_advantage",
                relative_experience_status="advantage",
                price_support="positive",
            ),
        )
    )
    unconverted = classify_local_capability_investment(
        _scoped(
            value_bundle_code="VALUE-UNCONVERTED",
            item=_investment(
                capability_code="ai_picture",
                investment_level="high",
                user_feedback_status="not_observed",
                relative_experience_status="weaker",
                competitor_experience_stronger=True,
            ),
        )
    )

    assert retained.classification == "retain"
    assert retained.status == "conclusion_available"
    assert unconverted.classification == "unconverted"
    assert unconverted.status == "conclusion_available"
    assert retained.review_required is unconverted.review_required is False


@pytest.mark.parametrize(
    ("performance", "expected"),
    [
        ("stronger", "do_not_follow"),
        ("not_weaker", "do_not_follow"),
        ("weaker", "missing_competitive_gap"),
    ],
)
def test_configuration_follow_uses_only_absence_comparators_and_performance(
    performance: str,
    expected: str,
) -> None:
    item = _investment(
        target_fact_status="known_absent",
        target_value=False,
        current_competitive_performance=performance,
    )

    decision = classify_local_capability_investment(
        _scoped(question_code="configuration_follow", item=item)
    )

    assert decision.classification == expected
    assert decision.status == "conclusion_available"
    assert decision.used_dimensions == [
        "candidate_capability_facts",
        "current_competitive_performance",
        "target_fact",
    ]


def test_conflict_only_affects_the_question_that_directly_uses_it() -> None:
    investment = _investment(
        capability_code="CAP-CONFLICT-LOCAL",
        target_fact_status="known_absent",
        target_value=False,
        user_feedback_status="conflicted",
        current_competitive_performance="stronger",
    )

    conversion = classify_local_capability_investment(
        _scoped(question_code="investment_conversion", item=investment)
    )
    follow = classify_local_capability_investment(
        _scoped(question_code="configuration_follow", item=investment)
    )

    assert conversion.status == "invalid"
    assert conversion.review_reasons == ["user_feedback_conflicted"]
    assert follow.classification == "do_not_follow"
    assert follow.review_required is False


def test_candidate_conflict_is_review_only_for_configuration_question() -> None:
    investment = _investment(
        capability_code="CAP-CANDIDATE-CONFLICT",
        facts=_facts(
            [
                "known_present",
                "known_present",
                "known_absent",
                "known_absent",
                "contradicted",
            ]
        ),
        target_fact_status="known_absent",
        target_value=False,
        current_competitive_performance="stronger",
    )

    conversion = classify_local_capability_investment(
        _scoped(question_code="investment_conversion", item=investment)
    )
    follow = classify_local_capability_investment(
        _scoped(question_code="configuration_follow", item=investment)
    )

    assert conversion.status == "no_conclusion"
    assert conversion.review_required is False
    assert follow.status == "invalid"
    assert follow.review_reasons == ["candidate_fact_contradiction"]


def test_local_review_overlay_does_not_cross_value_or_question_scope() -> None:
    conflicted = classify_local_capability_investment(
        _scoped(
            value_bundle_code="VALUE-A",
            item=_investment(
                capability_code="CAP-A",
                user_feedback_status="conflicted",
            ),
        )
    )
    unknown_other_value = classify_local_capability_investment(
        _scoped(
            value_bundle_code="VALUE-B",
            item=_investment(capability_code="CAP-A"),
        )
    )
    valid_other_question = classify_local_capability_investment(
        _scoped(
            question_code="configuration_follow",
            value_bundle_code="VALUE-A",
            item=_investment(
                capability_code="CAP-A",
                target_fact_status="known_absent",
                target_value=False,
                current_competitive_performance="stronger",
            ),
        )
    )

    overlays = build_local_investment_review_overlays(
        [conflicted, unknown_other_value, valid_other_question]
    )
    by_scope = {
        (row.question_code.value, row.value_bundle_code): row for row in overlays
    }

    assert by_scope[("investment_conversion", "VALUE-A")].review_required is True
    assert by_scope[("investment_conversion", "VALUE-B")].review_required is False
    assert by_scope[("configuration_follow", "VALUE-A")].review_required is False
    assert all("linked_investment_review" not in row.review_reasons for row in overlays)


def test_batch_is_deterministic_and_keeps_tv_ac_isolated() -> None:
    tv = _scoped(
        value_bundle_code="VALUE-TV",
        item=_investment(capability_code="TV-CAP"),
    )
    ac = _scoped(
        value_bundle_code="VALUE-AC",
        item=_investment(capability_code="AC-CAP", category_code="AC"),
    )

    first = classify_local_capability_investments([tv, ac])
    second = classify_local_capability_investments(
        [ac, tv],
        configs={
            "TV": capability_threshold_config("TV"),
            "AC": capability_threshold_config("AC"),
        },
    )

    assert first == second
    assert [(row.category_code, row.capability_code) for row in first] == [
        ("AC", "AC-CAP"),
        ("TV", "TV-CAP"),
    ]


def test_evidence_is_preserved_only_on_the_local_decision_and_overlay() -> None:
    evidence = SellpointValueEvidenceRef(
        module_code="M03B",
        record_type="capability_fact",
        record_id="fact-1",
        result_hash="fact-hash-1",
    )
    decision = classify_local_capability_investment(
        _scoped(
            item=_investment(
                target_fact_status="contradicted",
                evidence_refs=[evidence],
            )
        )
    )
    overlay = build_local_investment_review_overlays([decision])[0]

    assert decision.evidence_refs == [evidence]
    assert overlay.evidence_refs == [evidence]


def test_question_input_rejects_cross_category_investment() -> None:
    with pytest.raises(ValidationError, match="stay within category"):
        CapabilityInvestmentQuestionInput(
            project_id="project-1",
            category_code="AC",
            target_sku_code="AC-TARGET",
            question_code="investment_conversion",
            value_bundle_code="VALUE-1",
            investment=_investment(category_code="TV"),
        )
