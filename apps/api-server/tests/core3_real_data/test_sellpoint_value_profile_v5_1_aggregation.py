from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_aggregation import (
    aggregate_sku_conclusion,
    aggregate_value_conclusion,
    aggregate_value_conclusions,
    aggregate_version_release_quality,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    QuestionConclusionSignal,
    SkuConclusionAggregationInput,
    ValueConclusionAggregationInput,
    VersionConclusionAggregationInput,
)


def _evidence(code: str) -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code="SPV51",
        record_type="question_result",
        record_id=code,
        result_hash=f"evidence-{code}",
    )


def _signal(
    code: str,
    status: str,
    *,
    confidence: Decimal | None = None,
    limitation: str | None = None,
) -> QuestionConclusionSignal:
    invalid = status == "invalid"
    return QuestionConclusionSignal(
        question_code=code,
        status=status,
        confidence=confidence,
        limitations=[limitation] if limitation else [],
        review_required=invalid,
        review_reasons=["direct_fact_conflict"] if invalid else [],
        evidence_refs=[_evidence(code)],
        source_result_hash=f"source-{code}-{status}",
    )


def _value(
    code: str,
    signals: list[QuestionConclusionSignal],
    *,
    category_code: str = "TV",
    target_sku_code: str | None = None,
):
    return aggregate_value_conclusion(
        ValueConclusionAggregationInput(
            project_id="project-1",
            category_code=category_code,
            target_sku_code=target_sku_code or f"{category_code}-TARGET",
            value_bundle_code=code,
            question_signals=signals,
        )
    )


def _sku(
    code: str,
    values,
    *,
    category_code: str = "TV",
    structural_invalid_reasons: list[str] | None = None,
):
    return aggregate_sku_conclusion(
        SkuConclusionAggregationInput(
            project_id="project-1",
            category_code=category_code,
            target_sku_code=code,
            value_results=values,
            structural_invalid_reasons=structural_invalid_reasons or [],
        )
    )


def test_value_status_follows_invalid_available_partial_no_conclusion_precedence() -> (
    None
):
    invalid = _value(
        "VALUE-INVALID",
        [
            _signal("direct_market", "conclusion_available", confidence=Decimal("0.9")),
            _signal("user_value", "invalid"),
        ],
    )
    available = _value(
        "VALUE-AVAILABLE",
        [
            _signal("direct_market", "conclusion_available", confidence=Decimal("0.8")),
            _signal("strict_wtp", "no_conclusion", limitation="strict_gate_failed"),
        ],
    )
    partial = _value(
        "VALUE-PARTIAL",
        [_signal("parameter_group", "partial_conclusion", confidence=Decimal("0.6"))],
    )
    empty = _value("VALUE-EMPTY", [])

    assert invalid.status == "invalid"
    assert invalid.review_required is True
    assert available.status == "conclusion_available"
    assert available.review_required is False
    assert partial.status == "partial_conclusion"
    assert empty.status == "no_conclusion"
    assert empty.review_required is False


def test_optional_enhancement_failure_does_not_override_direct_conclusion() -> None:
    result = _value(
        "VALUE-1",
        [
            _signal(
                "direct_market", "conclusion_available", confidence=Decimal("0.82")
            ),
            _signal("synthetic", "no_conclusion", limitation="donor_gate_failed"),
            _signal("strict_wtp", "no_conclusion", limitation="strict_gate_failed"),
        ],
    )

    assert result.status == "conclusion_available"
    assert result.conclusion_available_count == 1
    assert result.no_conclusion_count == 2
    assert result.confidence_min == Decimal("0.82")
    assert result.confidence_median == Decimal("0.82")
    assert result.review_required is False


def test_confidence_uses_only_direct_conclusion_signals_not_all_investments() -> None:
    result = _value(
        "VALUE-1",
        [
            _signal("user_value", "conclusion_available", confidence=Decimal("0.9")),
            _signal("direct_market", "partial_conclusion", confidence=Decimal("0.5")),
            _signal("investment_unknown", "no_conclusion"),
        ],
    )

    assert result.conclusion_confidences == [Decimal("0.5"), Decimal("0.9")]
    assert result.confidence_min == Decimal("0.5")
    assert result.confidence_median == Decimal("0.7")
    assert result.status == "conclusion_available"


def test_no_conclusion_signal_cannot_smuggle_confidence_or_review() -> None:
    with pytest.raises(ValidationError, match="cannot carry confidence"):
        QuestionConclusionSignal(
            question_code="strict_wtp",
            status="no_conclusion",
            confidence=Decimal("0.4"),
            source_result_hash="strict-hash",
        )


def test_local_invalid_value_does_not_invalidate_sku_with_another_conclusion() -> None:
    valid = _value(
        "VALUE-VALID",
        [_signal("direct_market", "conclusion_available", confidence=Decimal("0.8"))],
    )
    conflicted = _value(
        "VALUE-CONFLICT",
        [_signal("user_value", "invalid")],
    )

    result = _sku("TV-TARGET", [conflicted, valid])

    assert result.status == "conclusion_available"
    assert result.consumer_status == "usable_conclusion"
    assert result.invalid_value_codes == ["VALUE-CONFLICT"]
    assert result.local_review_value_codes == ["VALUE-CONFLICT"]
    assert result.review_required is False
    assert result.confidence_min == Decimal("0.8")


def test_all_invalid_values_or_structural_error_make_sku_invalid() -> None:
    conflicted = _value("VALUE-CONFLICT", [_signal("user_value", "invalid")])

    all_invalid = _sku("TV-TARGET", [conflicted])
    structural = _sku(
        "TV-TARGET",
        [
            _value(
                "VALUE-VALID",
                [
                    _signal(
                        "direct_market",
                        "conclusion_available",
                        confidence=Decimal("0.8"),
                    )
                ],
            )
        ],
        structural_invalid_reasons=["result_hash_mismatch"],
    )

    assert all_invalid.status == "invalid"
    assert all_invalid.review_reasons == ["all_value_items_invalid"]
    assert structural.status == "invalid"
    assert structural.review_reasons == ["structural:result_hash_mismatch"]


def test_partial_or_empty_sku_remains_formally_consumable() -> None:
    partial = _sku(
        "TV-PARTIAL",
        [
            _value(
                "VALUE-PARTIAL",
                [_signal("parameter", "partial_conclusion", confidence=Decimal("0.6"))],
                target_sku_code="TV-PARTIAL",
            )
        ],
    )
    empty = _sku("TV-EMPTY", [])

    assert partial.status == "partial_conclusion"
    assert partial.consumer_status == "usable_partial"
    assert partial.review_required is False
    assert empty.status == "no_conclusion"
    assert empty.consumer_status == "data_insufficient"
    assert empty.review_required is False


def test_value_batch_is_deterministic_and_keeps_tv_ac_isolated() -> None:
    tv = ValueConclusionAggregationInput(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="TV-VALUE",
        question_signals=[_signal("q", "no_conclusion")],
    )
    ac = ValueConclusionAggregationInput(
        project_id="project-1",
        category_code="AC",
        target_sku_code="AC-TARGET",
        value_bundle_code="AC-VALUE",
        question_signals=[_signal("q", "no_conclusion")],
    )

    first = aggregate_value_conclusions([tv, ac])
    second = aggregate_value_conclusions([ac, tv])

    assert first == second
    assert [(row.category_code, row.value_bundle_code) for row in first] == [
        ("AC", "AC-VALUE"),
        ("TV", "TV-VALUE"),
    ]


def test_sku_input_rejects_cross_scope_value() -> None:
    ac_value = _value(
        "AC-VALUE",
        [_signal("q", "no_conclusion")],
        category_code="AC",
    )

    with pytest.raises(ValidationError, match="within scope"):
        SkuConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            target_sku_code="TV-TARGET",
            value_results=[ac_value],
        )


def test_version_is_ready_only_when_complete_and_all_skus_have_conclusions() -> None:
    value = _value(
        "VALUE-1",
        [_signal("direct", "conclusion_available", confidence=Decimal("0.8"))],
        target_sku_code="TV-1",
    )
    sku = _sku("TV-1", [value])

    result = aggregate_version_release_quality(
        VersionConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            expected_sku_codes=["TV-1"],
            sku_results=[sku],
        )
    )

    assert result.release_quality_status == "ready"
    assert result.integrity.generated_sku_count == 1
    assert result.conclusion_distribution.conclusion_available_count == 1
    assert result.confidence_min == Decimal("0.8")


def test_missing_optional_confidence_does_not_block_an_established_conclusion() -> None:
    value = _value(
        "VALUE-1",
        [_signal("direct", "conclusion_available")],
        target_sku_code="TV-1",
    )
    sku = _sku("TV-1", [value])

    result = aggregate_version_release_quality(
        VersionConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            expected_sku_codes=["TV-1"],
            sku_results=[sku],
        )
    )

    assert sku.status == "conclusion_available"
    assert sku.confidence_min is None
    assert result.release_quality_status == "ready"
    assert result.confidence_min is None


def test_partial_no_conclusion_and_local_review_make_version_limited_not_blocked() -> (
    None
):
    usable_with_local_review = _sku(
        "TV-1",
        [
            _value(
                "VALUE-VALID",
                [_signal("direct", "conclusion_available", confidence=Decimal("0.8"))],
                target_sku_code="TV-1",
            ),
            _value(
                "VALUE-CONFLICT",
                [_signal("user_value", "invalid")],
                target_sku_code="TV-1",
            ),
        ],
    )
    partial = _sku(
        "TV-2",
        [
            _value(
                "VALUE-PARTIAL",
                [_signal("parameter", "partial_conclusion", confidence=Decimal("0.6"))],
                target_sku_code="TV-2",
            )
        ],
    )
    empty = _sku("TV-3", [])

    result = aggregate_version_release_quality(
        VersionConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            expected_sku_codes=["TV-1", "TV-2", "TV-3"],
            sku_results=[empty, partial, usable_with_local_review],
        )
    )

    assert result.release_quality_status == "limited"
    assert result.integrity.invalid_profile_count == 0
    assert result.local_review_item_count == 1
    assert result.partial_conclusion_sku_codes == ["TV-2"]
    assert result.no_conclusion_sku_codes == ["TV-3"]


@pytest.mark.parametrize(
    "mutation",
    [
        "coverage",
        "generation_failure",
        "invalid",
        "cross_category",
        "duplicate",
        "dangling",
        "hash_mismatch",
    ],
)
def test_real_integrity_failures_block_version(mutation: str) -> None:
    value = _value(
        "VALUE-1",
        [_signal("direct", "conclusion_available", confidence=Decimal("0.8"))],
        target_sku_code="TV-1",
    )
    sku = _sku("TV-1", [value])
    expected = ["TV-1"]
    results = [sku]
    failures: list[str] = []
    dangling = 0
    hash_mismatch = 0
    if mutation == "coverage":
        expected = ["TV-1", "TV-2"]
    elif mutation == "generation_failure":
        expected = ["TV-1", "TV-2"]
        failures = ["TV-2"]
    elif mutation == "invalid":
        invalid_value = _value(
            "VALUE-BAD",
            [_signal("q", "invalid")],
            target_sku_code="TV-1",
        )
        results = [_sku("TV-1", [invalid_value])]
    elif mutation == "cross_category":
        ac_value = _value(
            "VALUE-AC",
            [_signal("q", "conclusion_available", confidence=Decimal("0.7"))],
            category_code="AC",
            target_sku_code="AC-1",
        )
        results.append(_sku("AC-1", [ac_value], category_code="AC"))
    elif mutation == "duplicate":
        results.append(sku)
    elif mutation == "dangling":
        dangling = 1
    elif mutation == "hash_mismatch":
        hash_mismatch = 1

    result = aggregate_version_release_quality(
        VersionConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            expected_sku_codes=expected,
            sku_results=results,
            generation_failure_sku_codes=failures,
            dangling_reference_count=dangling,
            hash_mismatch_count=hash_mismatch,
        )
    )

    assert result.release_quality_status == "blocked"


def test_version_result_is_deterministic_across_sku_order() -> None:
    sku1 = _sku(
        "TV-1",
        [
            _value(
                "VALUE-1",
                [_signal("q1", "conclusion_available", confidence=Decimal("0.8"))],
                target_sku_code="TV-1",
            )
        ],
    )
    sku2 = _sku("TV-2", [])
    payload = {
        "project_id": "project-1",
        "category_code": "TV",
        "expected_sku_codes": ["TV-1", "TV-2"],
    }

    first = aggregate_version_release_quality(
        VersionConclusionAggregationInput(**payload, sku_results=[sku1, sku2])
    )
    second = aggregate_version_release_quality(
        VersionConclusionAggregationInput(**payload, sku_results=[sku2, sku1])
    )

    assert first == second
