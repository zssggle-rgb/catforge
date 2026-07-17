"""Local-to-version conclusion aggregation for sellpoint-value V5.1."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median
from typing import Any

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    ConclusionDistribution,
    ProfileReleaseAssessment,
    QuestionConclusionStatus,
    ReleaseIntegritySummary,
    SkuConclusionAggregationInput,
    SkuConclusionResult,
    ValueConclusionAggregationInput,
    ValueConclusionResult,
    VersionConclusionAggregationInput,
    VersionConclusionResult,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_VALUE_AGGREGATION_VERSION = "sellpoint_value_value_status_v5_1"
SPV_V5_1_SKU_AGGREGATION_VERSION = "sellpoint_value_sku_status_v5_1"
SPV_V5_1_VERSION_AGGREGATION_VERSION = "sellpoint_value_version_status_v5_1"


def aggregate_value_conclusion(
    item: ValueConclusionAggregationInput,
) -> ValueConclusionResult:
    """Aggregate only questions belonging to one value bundle."""

    item = ValueConclusionAggregationInput.model_validate(
        item.model_dump(mode="python")
    )
    signals = sorted(item.question_signals, key=lambda row: row.question_code)
    counts = {
        status: sum(row.status == status for row in signals)
        for status in QuestionConclusionStatus
    }
    status = (
        QuestionConclusionStatus.INVALID
        if counts[QuestionConclusionStatus.INVALID]
        else QuestionConclusionStatus.CONCLUSION_AVAILABLE
        if counts[QuestionConclusionStatus.CONCLUSION_AVAILABLE]
        else QuestionConclusionStatus.PARTIAL_CONCLUSION
        if counts[QuestionConclusionStatus.PARTIAL_CONCLUSION]
        else QuestionConclusionStatus.NO_CONCLUSION
    )
    confidences = sorted(
        row.confidence
        for row in signals
        if row.status
        in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }
        and row.confidence is not None
    )
    review_reasons = sorted(
        {
            f"{row.question_code}:{reason}"
            for row in signals
            if row.status == QuestionConclusionStatus.INVALID
            for reason in row.review_reasons
        }
    )
    payload: dict[str, Any] = {
        "project_id": item.project_id,
        "category_code": item.category_code,
        "target_sku_code": item.target_sku_code,
        "value_bundle_code": item.value_bundle_code,
        "status": status,
        "question_count": len(signals),
        "conclusion_available_count": counts[
            QuestionConclusionStatus.CONCLUSION_AVAILABLE
        ],
        "partial_conclusion_count": counts[QuestionConclusionStatus.PARTIAL_CONCLUSION],
        "no_conclusion_count": counts[QuestionConclusionStatus.NO_CONCLUSION],
        "invalid_count": counts[QuestionConclusionStatus.INVALID],
        "conclusion_confidences": confidences,
        "confidence_min": min(confidences) if confidences else None,
        "confidence_median": median(confidences) if confidences else None,
        "limitations": sorted({item for row in signals for item in row.limitations}),
        "review_required": status == QuestionConclusionStatus.INVALID,
        "review_reasons": review_reasons,
        "evidence_refs": _dedupe_evidence_refs(
            [ref for row in signals for ref in row.evidence_refs]
        ),
        "source_result_hashes": sorted({row.source_result_hash for row in signals}),
    }
    return ValueConclusionResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_VALUE_AGGREGATION_VERSION,
        ),
    )


def aggregate_value_conclusions(
    items: Sequence[ValueConclusionAggregationInput],
) -> list[ValueConclusionResult]:
    """Aggregate multiple value bundles deterministically and independently."""

    keys = [
        (
            row.project_id,
            row.category_code,
            row.target_sku_code,
            row.value_bundle_code,
        )
        for row in items
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("value aggregation inputs must be unique by local scope")
    return [
        aggregate_value_conclusion(row)
        for row in sorted(
            items,
            key=lambda row: (
                row.project_id,
                row.category_code,
                row.target_sku_code,
                row.value_bundle_code,
            ),
        )
    ]


def aggregate_sku_conclusion(
    item: SkuConclusionAggregationInput,
) -> SkuConclusionResult:
    """Keep invalid values local when another value still answers the SKU."""

    item = SkuConclusionAggregationInput.model_validate(item.model_dump(mode="python"))
    values = sorted(item.value_results, key=lambda row: row.value_bundle_code)
    codes_by_status = {
        status: sorted(row.value_bundle_code for row in values if row.status == status)
        for status in QuestionConclusionStatus
    }
    if item.structural_invalid_reasons:
        status = QuestionConclusionStatus.INVALID
    elif codes_by_status[QuestionConclusionStatus.CONCLUSION_AVAILABLE]:
        status = QuestionConclusionStatus.CONCLUSION_AVAILABLE
    elif codes_by_status[QuestionConclusionStatus.PARTIAL_CONCLUSION]:
        status = QuestionConclusionStatus.PARTIAL_CONCLUSION
    elif (
        codes_by_status[QuestionConclusionStatus.INVALID]
        and not codes_by_status[QuestionConclusionStatus.NO_CONCLUSION]
    ):
        status = QuestionConclusionStatus.INVALID
    else:
        status = QuestionConclusionStatus.NO_CONCLUSION
    usable_values = [
        row
        for row in values
        if row.status
        in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }
    ]
    confidences = sorted(
        confidence for row in usable_values for confidence in row.conclusion_confidences
    )
    review_reasons = []
    if item.structural_invalid_reasons:
        review_reasons = [
            f"structural:{reason}" for reason in item.structural_invalid_reasons
        ]
    elif status == QuestionConclusionStatus.INVALID:
        review_reasons = ["all_value_items_invalid"]
    limitations = {
        *item.structural_invalid_reasons,
        *(limitation for row in values for limitation in row.limitations),
    }
    if codes_by_status[QuestionConclusionStatus.INVALID]:
        limitations.add(
            f"local_invalid_value_items:{len(codes_by_status[QuestionConclusionStatus.INVALID])}"
        )
    payload: dict[str, Any] = {
        "project_id": item.project_id,
        "category_code": item.category_code,
        "target_sku_code": item.target_sku_code,
        "status": status,
        "consumer_status": {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE: "usable_conclusion",
            QuestionConclusionStatus.PARTIAL_CONCLUSION: "usable_partial",
            QuestionConclusionStatus.NO_CONCLUSION: "data_insufficient",
            QuestionConclusionStatus.INVALID: "invalid",
        }[status],
        "value_count": len(values),
        "conclusion_available_value_codes": codes_by_status[
            QuestionConclusionStatus.CONCLUSION_AVAILABLE
        ],
        "partial_conclusion_value_codes": codes_by_status[
            QuestionConclusionStatus.PARTIAL_CONCLUSION
        ],
        "no_conclusion_value_codes": codes_by_status[
            QuestionConclusionStatus.NO_CONCLUSION
        ],
        "invalid_value_codes": codes_by_status[QuestionConclusionStatus.INVALID],
        "local_review_value_codes": codes_by_status[QuestionConclusionStatus.INVALID],
        "conclusion_confidences": confidences,
        "confidence_min": min(confidences) if confidences else None,
        "confidence_median": median(confidences) if confidences else None,
        "limitations": sorted(limitations),
        "review_required": status == QuestionConclusionStatus.INVALID,
        "review_reasons": sorted(review_reasons),
        "structural_invalid_reasons": item.structural_invalid_reasons,
        "source_result_hashes": sorted({row.result_hash for row in values}),
    }
    return SkuConclusionResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_SKU_AGGREGATION_VERSION,
        ),
    )


def aggregate_version_release_quality(
    item: VersionConclusionAggregationInput,
) -> VersionConclusionResult:
    """Derive ready/limited/blocked from integrity and real invalid states only."""

    item = VersionConclusionAggregationInput.model_validate(
        item.model_dump(mode="python")
    )
    expected = set(item.expected_sku_codes)
    rows = sorted(
        item.sku_results,
        key=lambda row: (
            row.target_sku_code,
            row.category_code,
            row.project_id,
            row.result_hash,
        ),
    )
    cross_scope_rows = [
        row
        for row in rows
        if row.project_id != item.project_id or row.category_code != item.category_code
    ]
    in_scope = [
        row
        for row in rows
        if row.project_id == item.project_id and row.category_code == item.category_code
    ]
    duplicate_count = len(in_scope) - len({row.target_sku_code for row in in_scope})
    by_code: dict[str, SkuConclusionResult] = {}
    for row in in_scope:
        by_code.setdefault(row.target_sku_code, row)
    canonical = [by_code[code] for code in sorted(expected & set(by_code))]
    unexpected_count = len(set(by_code) - expected)
    codes_by_status = {
        status: sorted(row.target_sku_code for row in canonical if row.status == status)
        for status in QuestionConclusionStatus
    }
    distribution = ConclusionDistribution(
        total_count=len(canonical),
        conclusion_available_count=len(
            codes_by_status[QuestionConclusionStatus.CONCLUSION_AVAILABLE]
        ),
        partial_conclusion_count=len(
            codes_by_status[QuestionConclusionStatus.PARTIAL_CONCLUSION]
        ),
        no_conclusion_count=len(
            codes_by_status[QuestionConclusionStatus.NO_CONCLUSION]
        ),
        invalid_count=len(codes_by_status[QuestionConclusionStatus.INVALID]),
    )
    integrity = ReleaseIntegritySummary(
        expected_sku_count=len(item.expected_sku_codes),
        generated_sku_count=len(canonical),
        generation_failure_count=len(item.generation_failure_sku_codes),
        invalid_profile_count=len(codes_by_status[QuestionConclusionStatus.INVALID]),
        cross_category_count=len(cross_scope_rows),
        duplicate_sku_count=duplicate_count,
        dangling_reference_count=item.dangling_reference_count + unexpected_count,
        hash_mismatch_count=item.hash_mismatch_count,
    )
    limitations = set(item.limitations)
    missing_count = len(expected - set(by_code))
    if missing_count:
        limitations.add(f"expected_sku_coverage_mismatch:{missing_count}")
    if cross_scope_rows:
        limitations.add(f"cross_scope_rows:{len(cross_scope_rows)}")
    if duplicate_count:
        limitations.add(f"duplicate_sku_rows:{duplicate_count}")
    if unexpected_count:
        limitations.add(f"unexpected_sku_rows:{unexpected_count}")
    local_review_item_count = sum(
        len(row.local_review_value_codes) for row in canonical
    )
    blocking = any(
        (
            integrity.generated_sku_count != integrity.expected_sku_count,
            integrity.generation_failure_count,
            integrity.invalid_profile_count,
            integrity.cross_category_count,
            integrity.duplicate_sku_count,
            integrity.dangling_reference_count,
            integrity.hash_mismatch_count,
            distribution.invalid_count,
        )
    )
    limited = any(
        (
            distribution.partial_conclusion_count,
            distribution.no_conclusion_count,
            local_review_item_count,
            bool(limitations),
        )
    )
    quality = "blocked" if blocking else "limited" if limited else "ready"
    assessment = ProfileReleaseAssessment(
        release_quality_status=quality,
        conclusion_distribution=distribution,
        integrity=integrity,
        review_item_count=local_review_item_count,
        limitations=sorted(limitations),
    )
    confidences = sorted(
        confidence for row in canonical for confidence in row.conclusion_confidences
    )
    payload: dict[str, Any] = {
        "project_id": item.project_id,
        "category_code": item.category_code,
        "release_quality_status": assessment.release_quality_status,
        "conclusion_distribution": distribution,
        "integrity": integrity,
        "conclusion_available_sku_codes": codes_by_status[
            QuestionConclusionStatus.CONCLUSION_AVAILABLE
        ],
        "partial_conclusion_sku_codes": codes_by_status[
            QuestionConclusionStatus.PARTIAL_CONCLUSION
        ],
        "no_conclusion_sku_codes": codes_by_status[
            QuestionConclusionStatus.NO_CONCLUSION
        ],
        "invalid_sku_codes": codes_by_status[QuestionConclusionStatus.INVALID],
        "generation_failure_sku_codes": item.generation_failure_sku_codes,
        "local_review_item_count": local_review_item_count,
        "confidence_min": min(confidences) if confidences else None,
        "confidence_median": median(confidences) if confidences else None,
        "limitations": assessment.limitations,
        "source_result_hashes": sorted({row.result_hash for row in rows}),
    }
    return VersionConclusionResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_VERSION_AGGREGATION_VERSION,
        ),
    )


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
    "SPV_V5_1_SKU_AGGREGATION_VERSION",
    "SPV_V5_1_VALUE_AGGREGATION_VERSION",
    "SPV_V5_1_VERSION_AGGREGATION_VERSION",
    "aggregate_sku_conclusion",
    "aggregate_value_conclusion",
    "aggregate_value_conclusions",
    "aggregate_version_release_quality",
]
