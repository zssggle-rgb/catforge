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
from app.services.core3_real_data.analyst.sellpoint_value_profile_thresholds import (
    classify_capability_investment,
    classify_capability_investments,
    compute_capability_prevalence,
)


def _facts(statuses: list[str]) -> list[CapabilityCandidateFact]:
    return [
        CapabilityCandidateFact(
            candidate_sku_code=f"CANDIDATE-{index}",
            fact_status=status,
            normalized_value=True if status == "known_present" else None,
        )
        for index, status in enumerate(statuses)
    ]


def _scope(
    facts: list[CapabilityCandidateFact],
    *,
    category_code: str = "TV",
    price_band: str | None = "premium",
    product_form: str | None = "television",
    size_relation: str | None = "same_size",
) -> CapabilityComparisonScope:
    return CapabilityComparisonScope(
        category_code=category_code,
        price_band=price_band,
        product_form=product_form,
        size_relation=size_relation,
        battlefield_codes=["BF-1"],
        competitor_roles=["direct_fight"],
        candidate_scope_ids=[row.candidate_sku_code for row in facts],
        scope_hash=f"scope-{category_code}-{price_band}-{product_form}-{size_relation}",
    )


def _input(
    *,
    capability_code: str = "CAPABILITY-1",
    facts: list[CapabilityCandidateFact] | None = None,
    category_code: str = "TV",
    scope: CapabilityComparisonScope | None = None,
    **overrides: Any,
) -> CapabilityInvestmentInput:
    facts = facts or _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_present",
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
        "comparison_scope": scope or _scope(facts, category_code=category_code),
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


def test_missing_and_contradicted_facts_never_become_absent() -> None:
    facts = _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_absent",
            "missing",
            "contradicted",
        ]
    )
    config = capability_threshold_config(
        "TV",
        overrides={"minimum_known_count": 4, "prevalence_threshold": 0.75},
    )

    summary = compute_capability_prevalence(
        candidate_facts=facts,
        comparison_scope=_scope(facts),
        config=config,
    )

    assert summary.total_candidate_count == 6
    assert summary.known_count == 4
    assert summary.present_count == 3
    assert summary.absent_count == 1
    assert summary.missing_count == 1
    assert summary.contradicted_count == 1
    assert summary.prevalence == 0.75
    assert summary.threshold_status == "meets_table_stake"


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (
            [
                "known_present",
                "known_present",
                "known_present",
                "known_present",
                "known_absent",
            ],
            "meets_table_stake",
        ),
        (
            [
                "known_present",
                "known_present",
                "known_present",
                "known_absent",
                "known_absent",
            ],
            "below_table_stake",
        ),
        (
            [
                "known_present",
                "known_present",
                "known_present",
                "known_present",
            ],
            "insufficient_known_sample",
        ),
    ],
)
def test_threshold_boundary_uses_known_count_and_inclusive_prevalence(
    statuses: list[str], expected: str
) -> None:
    facts = _facts(statuses)

    summary = compute_capability_prevalence(
        candidate_facts=facts,
        comparison_scope=_scope(facts),
        config=capability_threshold_config("TV"),
    )

    assert summary.threshold_status == expected


def test_hdmi_like_common_capability_is_table_stake_not_highlight() -> None:
    decision = classify_capability_investment(
        _input(
            capability_code="hdmi_2_1",
            user_feedback_status="realized_advantage",
            relative_experience_status="advantage",
            price_support="positive",
        )
    )

    assert decision.classification == "table_stake"
    assert decision.review_status == "auto_pass"
    assert "不应再把它作为核心溢价理由" in decision.business_reason_cn
    assert "用户体验结果仍需单独比较" in decision.boundary_cn


def test_experience_outcome_can_be_retained_even_when_parent_is_table_stake() -> None:
    decision = classify_capability_investment(
        _input(
            capability_code="gaming_connection_stability",
            capability_kind="experience_outcome",
            parent_capability_code="hdmi_2_1",
            user_feedback_status="realized_advantage",
            relative_experience_status="advantage",
            price_support="positive",
        )
    )

    assert decision.classification == "retain"
    assert decision.review_status == "auto_pass"


def test_partial_feedback_with_relative_and_market_advantage_is_retained() -> None:
    decision = classify_capability_investment(
        _input(
            capability_code="picture_experience_bundle",
            facts=_facts(
                [
                    "known_present",
                    "known_absent",
                    "known_absent",
                    "known_absent",
                    "known_absent",
                ]
            ),
            investment_level="high",
            user_feedback_status="partial",
            relative_experience_status="advantage",
            price_support="positive",
            volume_support="positive",
            current_competitive_performance="stronger",
        )
    )

    assert decision.classification == "retain"
    assert "用户可感知优势" in decision.business_reason_cn


def test_partial_bundle_signal_does_not_retain_unknown_component_investment() -> None:
    decision = classify_capability_investment(
        _input(
            capability_code="hdmi_2_1",
            facts=_facts(["known_present"]),
            investment_level="unknown",
            user_feedback_status="partial",
            relative_experience_status="advantage",
            price_support="positive",
            volume_support="positive",
            current_competitive_performance="stronger",
        )
    )

    assert decision.classification == "unknown"
    assert "present_capability_decision_evidence_insufficient" in (
        decision.review_reasons
    )
    assert "该能力缺少独立的用户价值或市场表现证据" in (
        decision.boundary_cn
    )
    assert "comparison_scope_incomplete" not in decision.boundary_cn


def test_high_zone_count_without_user_realization_is_unconverted() -> None:
    facts = _facts(
        [
            "known_present",
            "known_absent",
            "known_absent",
            "known_absent",
            "known_absent",
        ]
    )
    decision = classify_capability_investment(
        _input(
            capability_code="local_dimming_zone_count",
            facts=facts,
            investment_level="high",
            user_feedback_status="not_observed",
            relative_experience_status="weaker",
            competitor_experience_stronger=True,
        )
    )

    assert decision.classification == "unconverted"
    assert "先解决体验兑现" in decision.business_reason_cn
    assert "继续堆参数" in decision.business_reason_cn


def test_absent_quantum_dot_can_be_do_not_follow_with_concrete_winning_scope() -> None:
    facts = _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_absent",
            "known_absent",
        ]
    )
    decision = classify_capability_investment(
        _input(
            capability_code="quantum_dot",
            facts=facts,
            target_fact_status="known_absent",
            target_value=False,
            current_competitive_performance="stronger",
            price_support="positive",
            volume_support="not_weaker",
        )
    )

    assert decision.classification == "do_not_follow"
    assert decision.candidate_scope_ids
    assert "无需为了对齐参数而跟进" in decision.business_reason_cn


def test_absent_capability_is_gap_only_when_current_comparison_is_weaker() -> None:
    facts = _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_absent",
            "known_absent",
        ]
    )
    decision = classify_capability_investment(
        _input(
            capability_code="missing_feature",
            facts=facts,
            target_fact_status="known_absent",
            target_value=False,
            current_competitive_performance="weaker",
            volume_support="negative",
        )
    )

    assert decision.classification == "missing_competitive_gap"
    assert "产品定义缺口" in decision.business_reason_cn


@pytest.mark.parametrize("target_status", ["missing", "contradicted"])
def test_unknown_or_conflicted_target_fact_never_creates_hard_decision(
    target_status: str,
) -> None:
    decision = classify_capability_investment(
        _input(
            target_fact_status=target_status,
            current_competitive_performance="weaker",
        )
    )

    assert decision.classification == "unknown"
    assert decision.review_status == "review_required"


def test_conflicted_market_or_experience_signal_requires_review() -> None:
    decision = classify_capability_investment(
        _input(
            facts=_facts(
                [
                    "known_present",
                    "known_absent",
                    "known_absent",
                    "known_absent",
                    "known_absent",
                ]
            ),
            user_feedback_status="conflicted",
            relative_experience_status="advantage",
            price_support="positive",
        )
    )

    assert decision.classification == "unknown"
    assert "decision_signal_conflicted" in decision.review_reasons


def test_absent_capability_without_present_comparator_stays_unknown() -> None:
    facts = _facts(["known_absent"] * 5)
    decision = classify_capability_investment(
        _input(
            facts=facts,
            target_fact_status="known_absent",
            current_competitive_performance="stronger",
        )
    )

    assert decision.classification == "unknown"
    assert decision.review_status == "review_required"


def test_ac_threshold_requires_product_form_scope() -> None:
    facts = _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_present",
            "known_absent",
        ]
    )
    incomplete_scope = _scope(
        facts,
        category_code="AC",
        product_form=None,
        size_relation="same_horsepower",
    )

    incomplete = classify_capability_investment(
        _input(category_code="AC", facts=facts, scope=incomplete_scope)
    )
    complete = classify_capability_investment(
        _input(
            category_code="AC",
            facts=facts,
            scope=_scope(
                facts,
                category_code="AC",
                product_form="wall_mounted",
                size_relation="same_horsepower",
            ),
        )
    )

    assert incomplete.classification == "unknown"
    assert incomplete.prevalence_summary.threshold_status == "incomplete_scope"
    assert incomplete.review_status == "review_required"
    assert complete.classification == "table_stake"


def test_decision_and_batch_order_are_input_order_independent() -> None:
    facts = _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_present",
            "known_absent",
            "missing",
        ]
    )
    first = classify_capability_investment(_input(capability_code="B", facts=facts))
    second = classify_capability_investment(
        _input(capability_code="B", facts=list(reversed(facts)))
    )
    batch = classify_capability_investments(
        [_input(capability_code="B", facts=facts), _input(capability_code="A")]
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.decision_hash == second.decision_hash
    assert [row.capability_code for row in batch] == ["A", "B"]


def test_classification_depends_on_evidence_not_capability_name() -> None:
    hdmi = classify_capability_investment(_input(capability_code="hdmi_2_1"))
    arbitrary = classify_capability_investment(_input(capability_code="anything"))

    assert hdmi.classification == arbitrary.classification == "table_stake"


def test_evidence_refs_are_deduplicated_and_preserved() -> None:
    ref = SellpointValueEvidenceRef(
        module_code="M03B",
        record_type="core3_sku_param_profile",
        record_id="record-1",
        result_hash="hash-1",
        batch_id="batch-1",
        evidence_ids=["evidence-1"],
    )
    facts = _facts(
        [
            "known_present",
            "known_present",
            "known_present",
            "known_present",
            "known_absent",
        ]
    )
    facts[0] = facts[0].model_copy(update={"evidence_refs": [ref]})

    decision = classify_capability_investment(
        _input(facts=facts, evidence_refs=[ref])
    )

    assert decision.evidence_refs == [ref]


def test_threshold_config_is_validated_and_category_specific() -> None:
    tv = capability_threshold_config("tv")
    ac = capability_threshold_config("AC")

    assert "product_form" not in tv.required_scope_dimensions
    assert "product_form" in ac.required_scope_dimensions
    assert capability_threshold_config(
        "TV", overrides={"minimum_known_count": 7}
    ).minimum_known_count == 7
    with pytest.raises(ValidationError):
        capability_threshold_config("TV", overrides={"minimum_known_count": 0})
    with pytest.raises(ValueError, match="unsupported"):
        capability_threshold_config("REFRIGERATOR")


def test_schema_rejects_candidate_outside_scope_and_extra_fields() -> None:
    facts = _facts(["known_present"])
    with pytest.raises(ValidationError, match="comparison scope"):
        _input(
            facts=facts,
            scope=CapabilityComparisonScope(
                category_code="TV",
                price_band="premium",
                product_form="television",
                size_relation="same_size",
                candidate_scope_ids=[],
                scope_hash="scope-empty",
            ),
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        CapabilityCandidateFact.model_validate(
            {
                "candidate_sku_code": "CANDIDATE",
                "fact_status": "known_present",
                "unsupported": True,
            }
        )
