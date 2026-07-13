"""Build the full sellpoint-value competitor universe and reference manifest."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Iterable, Sequence

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CandidateDataAvailability,
    CandidateQuestion,
    CandidateRoleScore,
    CandidateUniverseManifest,
    SellpointValueCandidateManifestItem,
    SellpointValueReferenceManifestItem,
)
from app.services.core3_real_data.constants import (
    CORE3_M12_RULE_VERSION,
    CORE3_M13_RULE_VERSION,
    CORE3_M14_RULE_VERSION,
)


ALL_CANDIDATE_QUESTIONS: tuple[CandidateQuestion, ...] = (
    "current_price_support",
    "value_relative_advantage",
    "same_brand_role",
    "scale_conversion",
    "configuration_follow",
    "specific_competitor",
)


def build_candidate_universe_manifest(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    target_sku_code: str,
    candidate_records: Sequence[dict[str, Any]],
    market_references: Sequence[dict[str, Any]] = (),
) -> CandidateUniverseManifest:
    """Create a deterministic manifest without imposing a business count limit."""

    candidates = [
        _candidate_item(record)
        for record in candidate_records
        if str(record.get("candidate_sku_code") or "").strip() != target_sku_code
    ]
    candidates = sorted(candidates, key=_candidate_sort_key)
    candidate_codes = {row.candidate_sku_code for row in candidates}
    references = sorted(
        _reference_items(market_references, candidate_codes, target_sku_code),
        key=lambda row: (row.reference_sku_code, tuple(row.reference_purposes)),
    )
    counts = dict(Counter(row.eligibility_status for row in candidates))
    limitations = []
    if not candidates:
        limitations.append("competitor_universe_unavailable")
    payload = {
        "schema_version": "sellpoint_value_candidate_universe_v1",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "target_sku_code": target_sku_code,
        "competitor_universe_status": "available" if candidates else "unavailable",
        "competitor_candidates": [row.model_dump(mode="json") for row in candidates],
        "analysis_references": [row.model_dump(mode="json") for row in references],
        "candidate_count_by_status": counts,
        "m12_rule_version": CORE3_M12_RULE_VERSION,
        "m13_rule_version": CORE3_M13_RULE_VERSION,
        "m14_rule_version": CORE3_M14_RULE_VERSION,
        "limitations": limitations,
    }
    return CandidateUniverseManifest(
        **payload,
        candidate_manifest_hash=canonical_v4_hash(payload),
    )


def candidate_manifest_as_v4_fallback(
    manifest: CandidateUniverseManifest,
) -> list[dict[str, Any]]:
    """Adapt all non-blocked manifest items to the transitional V4 context loader."""

    result = []
    for row in manifest.competitor_candidates:
        if row.eligibility_status not in {"eligible", "limited"}:
            continue
        result.append(
            {
                "candidate": {
                    "sku_code": row.candidate_sku_code,
                    "brand_name": row.brand_name,
                    "model_name": row.model_name,
                },
                "competitor_role": row.primary_relation_type,
                "competitor_role_cn": row.m14_slot_name_cn,
                "confidence": row.component_total_score,
                "candidate_source": "M12_M13_candidate_universe",
                "authority_eligible": True,
            }
        )
    return result


def candidate_manifest_as_v4_context_pool(
    manifest: CandidateUniverseManifest,
) -> list[dict[str, Any]]:
    """Expose competitors and references to V4 while keeping their roles explicit."""

    result = candidate_manifest_as_v4_fallback(manifest)
    included = {
        str((row.get("candidate") or {}).get("sku_code") or "") for row in result
    }
    for row in manifest.analysis_references:
        if row.reference_sku_code in included:
            continue
        result.append(
            {
                "candidate": {
                    "sku_code": row.reference_sku_code,
                    "brand_name": row.brand_name,
                    "model_name": row.model_name,
                },
                "competitor_role": "analysis_reference",
                "competitor_role_cn": "分析参考产品",
                "confidence": None,
                "candidate_source": "analysis_reference",
                "authority_eligible": False,
                "reference_purposes": list(row.reference_purposes),
            }
        )
    return result


def _candidate_item(record: dict[str, Any]) -> SellpointValueCandidateManifestItem:
    component = record.get("component") if isinstance(record.get("component"), dict) else None
    feature = record.get("feature") if isinstance(record.get("feature"), dict) else {}
    role_rows = record.get("roles") if isinstance(record.get("roles"), list) else []
    selection = record.get("selection") if isinstance(record.get("selection"), dict) else None
    availability = CandidateDataAvailability(
        market=bool(feature.get("market_feature")),
        parameters=bool(feature.get("param_feature")),
        claim_value=bool(feature.get("claim_value_overlap")),
        battlefield=bool(feature.get("battlefield_overlap")),
        user_task=bool(feature.get("task_overlap")),
        audience=bool(feature.get("audience_overlap")),
    )
    roles = sorted(
        [
            CandidateRoleScore(
                role_code=str(item.get("role_code") or "unknown"),
                role_name_cn=str(item.get("role_name_cn") or ""),
                score=_bounded_number(item.get("role_score")),
                confidence=_bounded_number(item.get("role_confidence")),
                auto_select_eligible=bool(item.get("auto_select_eligible")),
                review_required=bool(item.get("review_required")),
            )
            for item in role_rows
        ],
        key=lambda item: (-item.score, item.role_code),
    )
    eligible_questions = _eligible_questions(record, availability, component)
    status, review_reasons = _eligibility_status(
        record,
        component,
        roles,
        eligible_questions,
        availability,
    )
    if status in {"blocked", "review_required", "recalled_only"}:
        eligible_questions = []
    unavailable = [
        question for question in ALL_CANDIDATE_QUESTIONS if question not in eligible_questions
    ]
    relation_types = _dedupe_strings(
        [
            str(record.get("primary_relation_type") or "scenario_substitute"),
            *(record.get("relation_types") or []),
            *(item.role_code for item in roles),
        ]
    )
    return SellpointValueCandidateManifestItem(
        candidate_sku_code=str(record.get("candidate_sku_code") or "").strip(),
        brand_name=_optional_text(record.get("candidate_brand_name")),
        model_name=_optional_text(record.get("candidate_model_name")),
        primary_relation_type=str(
            record.get("primary_relation_type") or "scenario_substitute"
        ),
        relation_types=relation_types,
        recall_sources=_dedupe_strings(record.get("recall_sources") or []),
        recall_strength=str(record.get("recall_strength") or "unknown"),
        recall_priority_score=_optional_bounded_number(
            record.get("recall_priority_score")
        ),
        component_total_score=(
            _optional_bounded_number(component.get("component_total_score"))
            if component
            else None
        ),
        role_scores=roles,
        m14_selected=selection is not None,
        m14_slot_code=_optional_text((selection or {}).get("slot_code")),
        m14_slot_name_cn=_optional_text((selection or {}).get("slot_name_cn")),
        m14_selection_rank=(
            int(selection["selection_rank"])
            if selection and selection.get("selection_rank") is not None
            else None
        ),
        eligibility_status=status,
        eligible_questions=eligible_questions,
        unavailable_questions=unavailable,
        data_availability=availability,
        same_brand=bool(record.get("same_brand_flag")),
        market_summary=(
            feature.get("market_feature")
            if isinstance(feature.get("market_feature"), dict)
            else {}
        ),
        review_required=status == "review_required",
        review_reasons=review_reasons,
        source_hashes={
            key: str(value)
            for key, value in {
                "M12": record.get("pool_result_hash"),
                "M13": (component or {}).get("result_hash"),
                "M14": (selection or {}).get("result_hash"),
                "M12_FEATURE": feature.get("feature_snapshot_hash"),
            }.items()
            if value
        },
        source_record_ids={
            key: str(value)
            for key, value in {
                "M12": record.get("pool_record_id"),
                "M12_FEATURE": feature.get("record_id"),
                "M13": (component or {}).get("record_id"),
                "M14": (selection or {}).get("record_id"),
            }.items()
            if value
        },
        source_evidence_ids={
            key: _dedupe_strings(value or [])
            for key, value in {
                "M12": record.get("pool_evidence_ids"),
                "M12_FEATURE": feature.get("evidence_ids"),
                "M13": (component or {}).get("evidence_ids"),
                "M14": (selection or {}).get("evidence_ids"),
            }.items()
            if value
        },
    )


def _eligible_questions(
    record: dict[str, Any],
    availability: CandidateDataAvailability,
    component: dict[str, Any] | None,
) -> list[CandidateQuestion]:
    if component is None:
        return []
    result: list[CandidateQuestion] = ["specific_competitor"]
    if availability.market:
        result.extend(["current_price_support", "scale_conversion"])
    if availability.claim_value or availability.battlefield:
        result.append("value_relative_advantage")
    if bool(record.get("same_brand_flag")) and availability.market:
        result.append("same_brand_role")
    if availability.parameters:
        result.append("configuration_follow")
    return [question for question in ALL_CANDIDATE_QUESTIONS if question in result]


def _eligibility_status(
    record: dict[str, Any],
    component: dict[str, Any] | None,
    roles: Sequence[CandidateRoleScore],
    eligible_questions: Sequence[CandidateQuestion],
    availability: CandidateDataAvailability,
) -> tuple[str, list[str]]:
    reasons = _dedupe_strings(
        [
            *(record.get("review_reasons") or []),
            *((component or {}).get("review_reasons") or []),
        ]
    )
    pool_processing = str(record.get("processing_status") or "success")
    component_processing = str((component or {}).get("processing_status") or "success")
    if pool_processing not in {"success", "warning"} or (
        component is not None and component_processing not in {"success", "warning"}
    ):
        return "blocked", _dedupe_strings([*reasons, "processing_blocked"])
    if (
        bool(record.get("review_required"))
        or bool((component or {}).get("review_required"))
        or any(role.review_required for role in roles)
    ):
        return "review_required", _dedupe_strings([*reasons, "review_required"])
    if component is None:
        return "recalled_only", _dedupe_strings([*reasons, "m13_missing"])
    if not eligible_questions:
        return "blocked", _dedupe_strings([*reasons, "no_eligible_question"])
    full_families = (
        availability.market
        and availability.parameters
        and (availability.claim_value or availability.battlefield)
    )
    if full_families:
        return "eligible", reasons
    return "limited", _dedupe_strings([*reasons, "partial_question_coverage"])


def _reference_items(
    records: Sequence[dict[str, Any]],
    competitor_codes: set[str],
    target_sku_code: str,
) -> list[SellpointValueReferenceManifestItem]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in records:
        candidate = raw.get("candidate") if isinstance(raw.get("candidate"), dict) else raw
        sku_code = str((candidate or {}).get("sku_code") or "").strip()
        if not sku_code or sku_code == target_sku_code:
            continue
        grouped.setdefault(sku_code, []).append(raw)
    result = []
    for sku_code in sorted(grouped):
        group = grouped[sku_code]
        raw = min(group, key=canonical_v4_hash)
        candidate = raw.get("candidate") if isinstance(raw.get("candidate"), dict) else raw
        purposes = _dedupe_strings(
            purpose
            for item in group
            for purpose in (
                (
                    item.get("candidate").get("reference_purposes")
                    if isinstance(item.get("candidate"), dict)
                    else None
                )
                or item.get("reference_purposes")
                or ["same_size_market"]
            )
        )
        result.append(
            SellpointValueReferenceManifestItem(
                reference_sku_code=sku_code,
                brand_name=_optional_text((candidate or {}).get("brand_name")),
                model_name=_optional_text((candidate or {}).get("model_name")),
                reference_purposes=purposes or ["same_size_market"],
                also_competitor=sku_code in competitor_codes,
                market_summary={
                    key: value
                    for key, value in (candidate or {}).items()
                    if key
                    in {
                        "avg_price",
                        "price_wavg",
                        "avg_weekly_sales_volume",
                        "sales_volume_total",
                        "screen_size_inch",
                        "price_band_size",
                    }
                },
                source_hashes=(
                    {"M07": str((candidate or {}).get("result_hash"))}
                    if (candidate or {}).get("result_hash")
                    else {}
                ),
            )
        )
    return result


def _candidate_sort_key(row: SellpointValueCandidateManifestItem) -> tuple[Any, ...]:
    status_order = {
        "eligible": 0,
        "limited": 1,
        "review_required": 2,
        "recalled_only": 3,
        "blocked": 4,
    }
    return (
        status_order[row.eligibility_status],
        0 if row.m14_selected else 1,
        row.primary_relation_type,
        -(row.component_total_score or 0.0),
        row.candidate_sku_code,
    )


def _bounded_number(value: Any) -> float:
    number = _optional_bounded_number(value)
    return number if number is not None else 0.0


def _optional_bounded_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(Decimal(str(value)))
    except (ValueError, TypeError, ArithmeticError):
        return None
    return max(0.0, min(1.0, number))


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


__all__ = [
    "ALL_CANDIDATE_QUESTIONS",
    "build_candidate_universe_manifest",
    "candidate_manifest_as_v4_context_pool",
    "candidate_manifest_as_v4_fallback",
]
