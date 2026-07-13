"""Pure assembly of one auditable SKU sellpoint-value profile draft."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer_schemas import (
    MaterializedSellpointValueDraft,
    ProfileQaTopic,
    ProfileSourceLineage,
    SellpointValueDecisionValueItem,
    SellpointValueFivePmDecisions,
    SellpointValueMaterializationInput,
    SkuSellpointValueDecisionProfile,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    PROFILE_AUTO_PASS_MIN_CONFIDENCE,
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
    SellpointValueDraftBundle,
    SkuSellpointValueCandidateDraft,
    SkuSellpointValueItemDraft,
    SkuSellpointValueProfileDraft,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CapabilityInvestmentDecision,
    SellpointValueCandidateManifestItem,
    SellpointValueEvidenceRef,
    SellpointValueReferenceManifestItem,
)
from app.services.core3_real_data.hash_utils import stable_hash


PROFILE_INPUT_HASH_VERSION = "sellpoint_value_profile_input_v1"
PROFILE_RESULT_HASH_VERSION = "sellpoint_value_profile_result_v1"
PROFILE_VALUE_ITEM_HASH_VERSION = "sellpoint_value_profile_value_item_v1"
PROFILE_CANDIDATE_HASH_VERSION = "sellpoint_value_profile_candidate_v1"

CRITICAL_SOURCE_MODULES = frozenset({"M03B", "M04C", "M05C", "M07", "M12D"})


def build_profile_input_fingerprint(
    source: SellpointValueMaterializationInput,
) -> str:
    """Hash every upstream authority and method without hiding missing sources."""

    lineage = [
        {
            **row.model_dump(mode="json"),
            "rule_versions": sorted(row.rule_versions),
            "result_hashes": sorted(row.result_hashes),
            "record_ids": sorted(row.record_ids),
            "limitations": sorted(row.limitations),
        }
        for row in sorted(source.source_lineage, key=lambda item: item.module_code)
    ]
    return stable_hash(
        {
            "project_id": source.project_id,
            "category_code": source.category_code,
            "batch_id": source.batch_id,
            "target_sku_code": source.target.sku_code,
            "source_lineage": lineage,
            "candidate_manifest_hash": source.candidate_universe.candidate_manifest_hash,
            "threshold_config": source.threshold_config.model_dump(mode="json"),
            "investment_decision_hashes": sorted(
                row.decision_hash for row in source.investment_decisions
            ),
            "v5_report_hash": source.v5_report.result_hash,
            "method_versions": dict(sorted(source.method_versions.items())),
        },
        version=PROFILE_INPUT_HASH_VERSION,
    )


def materialize_sellpoint_value_profile(
    source: SellpointValueMaterializationInput,
    *,
    sellpoint_value_profile_version_id: str,
) -> MaterializedSellpointValueDraft:
    input_fingerprint = build_profile_input_fingerprint(source)
    freshness_status, freshness_reasons = _freshness(source)
    analysis_state, state_reasons = _analysis_state(source)
    value_items = _value_items(source)
    question_analyses = _question_analyses(value_items)
    investment_decisions = sorted(
        source.investment_decisions,
        key=lambda row: row.capability_code,
    )
    pm_decisions = _pm_decisions(source, investment_decisions)
    qa_index = _qa_index()
    review_reasons = _dedupe(
        [
            *freshness_reasons,
            *state_reasons,
            *source.limitations,
            *(
                f"investment_review:{row.capability_code}"
                for row in investment_decisions
                if row.review_status == "review_required"
            ),
        ]
    )
    profile_confidence = _profile_confidence(value_items, investment_decisions)
    if profile_confidence < float(PROFILE_AUTO_PASS_MIN_CONFIDENCE):
        review_reasons = _dedupe([*review_reasons, "profile_confidence_low"])
    review_required = bool(review_reasons) or analysis_state != "ready"
    evidence_refs = _profile_evidence_refs(source.source_lineage)
    limitations = _dedupe(
        [
            *source.limitations,
            *(reason for row in source.source_lineage for reason in row.limitations),
            *(reason for row in value_items for reason in row.limitations),
        ]
    )
    profile_payload: dict[str, Any] = {
        "schema_version": SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
        "project_id": source.project_id,
        "category_code": source.category_code,
        "batch_id": source.batch_id,
        "profile_version": source.profile_version,
        "rule_version": SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        "method_version": SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        "method_versions": dict(sorted(source.method_versions.items())),
        "target": source.target,
        "analysis_state": analysis_state,
        "freshness_status": freshness_status,
        "profile_confidence": profile_confidence,
        "source_lineage": sorted(
            source.source_lineage,
            key=lambda row: row.module_code,
        ),
        "target_market_summary": dict(source.v5_report.market_reference),
        "candidate_universe": source.candidate_universe,
        "threshold_config": source.threshold_config,
        "investment_decisions": investment_decisions,
        "value_items": value_items,
        "question_analyses": question_analyses,
        "price_role": {
            "summary_cn": source.v5_report.decision_summary.price_summary_cn,
            "report_result_hash": source.v5_report.result_hash,
        },
        "battlefield_options": [
            row.model_dump(mode="json")
            for row in source.v5_report.battlefield_options
        ],
        "pm_decisions": pm_decisions,
        "qa_index": qa_index,
        "evidence_summary": {
            "source_module_count": len(source.source_lineage),
            "present_source_count": sum(
                row.status == "present" for row in source.source_lineage
            ),
            "evidence_ref_count": len(evidence_refs),
            "candidate_count": len(source.candidate_universe.competitor_candidates),
            "reference_count": len(source.candidate_universe.analysis_references),
            "value_item_count": len(value_items),
        },
        "limitations": limitations,
        "review_required": review_required,
        "review_reasons": review_reasons,
        "input_fingerprint": input_fingerprint,
    }
    result_hash = stable_hash(
        _json_payload(profile_payload),
        version=PROFILE_RESULT_HASH_VERSION,
    )
    profile = SkuSellpointValueDecisionProfile(
        **profile_payload,
        result_hash=result_hash,
    )
    common = {
        "sellpoint_value_profile_version_id": sellpoint_value_profile_version_id,
        "project_id": source.project_id,
        "category_code": source.category_code,
        "batch_id": source.batch_id,
        "product_category": source.category_code,
        "profile_version": source.profile_version,
        "schema_version": SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
        "rule_version": SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        "method_version": SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        "input_fingerprint": input_fingerprint,
    }
    review_status = "review_required" if review_required else "auto_pass"
    persisted_profile = SkuSellpointValueProfileDraft(
        **common,
        result_hash=result_hash,
        sku_code=source.target.sku_code,
        model_code=None,
        model_name=source.target.model_name,
        brand_name=source.target.brand_name,
        display_name_cn=(
            f"{source.target.brand_name or ''} "
            f"{source.target.model_name or source.target.sku_code}"
        ).strip(),
        analysis_state=analysis_state,
        freshness_status=freshness_status,
        profile_confidence=Decimal(str(profile_confidence)),
        target_market_summary_json=profile.target_market_summary,
        source_lineage_json=[
            row.model_dump(mode="json") for row in profile.source_lineage
        ],
        candidate_universe_summary_json={
            "candidate_manifest_hash": source.candidate_universe.candidate_manifest_hash,
            "competitor_universe_status": source.candidate_universe.competitor_universe_status,
            "competitor_count": len(source.candidate_universe.competitor_candidates),
            "reference_count": len(source.candidate_universe.analysis_references),
            "candidate_count_by_status": source.candidate_universe.candidate_count_by_status,
        },
        threshold_summary_json=source.threshold_config.model_dump(mode="json"),
        question_analyses_json=question_analyses,
        investment_decisions_json=[
            row.model_dump(mode="json") for row in investment_decisions
        ],
        price_role_json=profile.price_role,
        battlefield_options_json=profile.battlefield_options,
        pm_decisions_json=pm_decisions.model_dump(mode="json"),
        qa_index_json=[row.model_dump(mode="json") for row in qa_index],
        evidence_summary_json=profile.evidence_summary,
        evidence_refs_json=evidence_refs,
        limitations_json=limitations,
        review_required=review_required,
        review_status=review_status,
        review_reason_json={"reasons": review_reasons},
    )
    candidates = [
        *_competitor_drafts(source, common),
        *_reference_drafts(source, common),
    ]
    persisted_items = _value_item_drafts(source, common, value_items)
    return MaterializedSellpointValueDraft(
        profile=profile,
        persistence_bundle=SellpointValueDraftBundle(
            profile=persisted_profile,
            candidates=candidates,
            value_items=persisted_items,
        ),
    )


def _value_items(
    source: SellpointValueMaterializationInput,
) -> list[SellpointValueDecisionValueItem]:
    decisions = {row.capability_code: row for row in source.investment_decisions}
    result = []
    for row in source.v5_report.value_account_rows:
        battlefield_code = str(
            row.battlefield.get("battlefield_code")
            or row.battlefield.get("code")
            or "unknown_battlefield"
        )
        battlefield_name = str(
            row.battlefield.get("battlefield_name_cn")
            or row.battlefield.get("name_cn")
            or ""
        )
        perceived = row.perceived_user_value
        capability_codes = sorted(
            {member.capability_code for member in row.sellpoint_bundle.members}
        )
        linked_decisions = [
            decisions[code] for code in capability_codes if code in decisions
        ]
        questions = [
            {
                "question": item.question,
                "highest_available_method": item.highest_available_method,
                "eligible_candidate_sku_codes": sorted(
                    {
                        sku_code
                        for candidate in item.candidates
                        if candidate.stage == "eligible"
                        for sku_code in candidate.candidate_sku_codes
                    }
                ),
                "selection_reasons": item.selection_reasons,
                "degradation_reasons": item.degradation_reasons,
                "set_hash": item.set_hash,
            }
            for item in sorted(
                row.counterfactual_sets,
                key=lambda item: (item.question, item.bundle_code),
            )
        ]
        payload: dict[str, Any] = {
            "battlefield_code": battlefield_code,
            "battlefield_name_cn": battlefield_name,
            "purchase_reason_code": perceived.get("purchase_reason_code"),
            "purchase_reason_name_cn": perceived.get("purchase_reason_name_cn"),
            "value_bundle_code": row.sellpoint_bundle.bundle_code,
            "value_bundle_name_cn": row.sellpoint_bundle.bundle_name_cn,
            "perceived_value_name_cn": str(
                perceived.get("name_cn")
                or perceived.get("value_name_cn")
                or row.sellpoint_bundle.bundle_name_cn
            ),
            "perceived_outcome_cn": str(
                perceived.get("outcome_cn")
                or perceived.get("summary_cn")
                or "现有证据未形成更具体的用户结果表述。"
            ),
            "value_status": row.value_status,
            "capability_codes": capability_codes,
            "investment_decisions": linked_decisions,
            "question_analyses": questions,
            "price_realization": row.price_realization.model_dump(mode="json"),
            "volume_realization": row.volume_realization.model_dump(mode="json"),
            "battlefield_allocation": (
                row.battlefield_allocation.model_dump(mode="json")
                if row.battlefield_allocation
                else None
            ),
            "increment": (
                row.increment.model_dump(mode="json") if row.increment else None
            ),
            "boundary_cn": row.boundary_cn,
            "confidence": _value_confidence(row.value_status),
            "limitations": sorted(set(row.limitations)),
        }
        result.append(
            SellpointValueDecisionValueItem(
                **payload,
                value_item_hash=stable_hash(
                    _json_payload(payload),
                    version=PROFILE_VALUE_ITEM_HASH_VERSION,
                ),
            )
        )
    return sorted(
        result,
        key=lambda item: (item.battlefield_code, item.value_bundle_code),
    )


def _question_analyses(
    value_items: Sequence[SellpointValueDecisionValueItem],
) -> list[dict[str, Any]]:
    result = []
    for item in value_items:
        for analysis in item.question_analyses:
            result.append(
                {
                    "battlefield_code": item.battlefield_code,
                    "value_bundle_code": item.value_bundle_code,
                    **analysis,
                }
            )
    return sorted(
        result,
        key=lambda row: (
            str(row.get("question")),
            str(row.get("battlefield_code")),
            str(row.get("value_bundle_code")),
        ),
    )


def _pm_decisions(
    source: SellpointValueMaterializationInput,
    decisions: Sequence[CapabilityInvestmentDecision],
) -> SellpointValueFivePmDecisions:
    by_class: dict[str, list[str]] = {}
    for row in decisions:
        by_class.setdefault(row.classification, []).append(row.capability_name_cn)
    summary = source.v5_report.decision_summary
    return SellpointValueFivePmDecisions(
        investments_to_retain=sorted(by_class.get("retain", [])),
        investments_not_converted=sorted(by_class.get("unconverted", [])),
        configurations_not_to_follow=sorted(by_class.get("do_not_follow", [])),
        missing_competitive_gaps=sorted(
            by_class.get("missing_competitive_gap", [])
        ),
        table_stakes_to_maintain=sorted(by_class.get("table_stake", [])),
        current_price_support_cn=summary.price_summary_cn,
        growth_action_cn=(
            f"{summary.volume_summary_cn} {summary.existing_battlefield_summary_cn} "
            f"{summary.expansion_summary_cn}"
        ).strip(),
    )


def _qa_index() -> list[ProfileQaTopic]:
    return [
        ProfileQaTopic(
            topic_code="investment",
            question_examples_cn=["哪些投入值得保留", "哪些投入没有转化"],
            fact_paths=["investment_decisions", "value_items"],
        ),
        ProfileQaTopic(
            topic_code="price",
            question_examples_cn=["当前价格是否获得用户价值支撑"],
            fact_paths=["price_role", "value_items.*.price_realization"],
        ),
        ProfileQaTopic(
            topic_code="volume",
            question_examples_cn=["如果追求销量应该改价格还是卖点"],
            fact_paths=["pm_decisions.growth_action_cn", "value_items.*.volume_realization"],
        ),
        ProfileQaTopic(
            topic_code="competitor",
            question_examples_cn=["为什么选择这个对照产品"],
            fact_paths=["candidate_universe", "question_analyses"],
        ),
        ProfileQaTopic(
            topic_code="battlefield",
            question_examples_cn=["应增强已有战场还是进入新战场"],
            fact_paths=["battlefield_options", "value_items"],
        ),
        ProfileQaTopic(
            topic_code="version",
            question_examples_cn=["与上一版画像相比发生了什么"],
            fact_paths=["profile_version", "result_hash"],
        ),
    ]


def _freshness(
    source: SellpointValueMaterializationInput,
) -> tuple[str, list[str]]:
    mismatches = []
    unknown = []
    for row in source.source_lineage:
        if row.status != "present":
            continue
        current = source.current_source_hashes.get(row.module_code)
        if current is None:
            unknown.append(row.module_code)
        elif sorted(current) != sorted(row.result_hashes):
            mismatches.append(row.module_code)
    if mismatches:
        return "stale", [f"stale_source:{code}" for code in sorted(mismatches)]
    if unknown:
        return "unknown", [
            f"current_source_hash_unknown:{code}" for code in sorted(unknown)
        ]
    return "current", []


def _analysis_state(
    source: SellpointValueMaterializationInput,
) -> tuple[str, list[str]]:
    conflicts = sorted(
        row.module_code for row in source.source_lineage if row.status == "conflict"
    )
    if source.v5_report.analysis_state == "blocked" or conflicts:
        return "blocked", [f"source_conflict:{code}" for code in conflicts]
    missing_critical = sorted(
        row.module_code
        for row in source.source_lineage
        if row.module_code in CRITICAL_SOURCE_MODULES and row.status == "missing"
    )
    partial_reasons = [
        *(f"critical_source_missing:{code}" for code in missing_critical),
        *(
            ["competitor_universe_unavailable"]
            if source.candidate_universe.competitor_universe_status == "unavailable"
            else []
        ),
        *(
            ["v5_report_partial"]
            if source.v5_report.analysis_state == "partial"
            else []
        ),
    ]
    return ("partial", partial_reasons) if partial_reasons else ("ready", [])


def _profile_confidence(
    value_items: Sequence[SellpointValueDecisionValueItem],
    decisions: Sequence[CapabilityInvestmentDecision],
) -> float:
    values = [
        *(row.confidence for row in value_items),
        *(row.confidence for row in decisions),
    ]
    return round(sum(values) / len(values), 4) if values else 0.4


def _value_confidence(value_status: str) -> float:
    return {
        "observed_positive": 0.86,
        "observed_mixed": 0.7,
        "observed_negative": 0.76,
        "partial": 0.66,
        "not_observed": 0.5,
        "conflicted": 0.45,
        "unknown": 0.4,
    }.get(value_status, 0.5)


def _competitor_drafts(
    source: SellpointValueMaterializationInput,
    common: dict[str, Any],
) -> list[SkuSellpointValueCandidateDraft]:
    result = []
    for row in source.candidate_universe.competitor_candidates:
        confidence = row.component_total_score or row.recall_priority_score or 0.0
        needs_review = (
            row.review_required
            or row.eligibility_status
            in {"review_required", "blocked", "recalled_only"}
            or confidence < float(PROFILE_AUTO_PASS_MIN_CONFIDENCE)
        )
        payload = {
            **common,
            "target_sku_code": source.target.sku_code,
            "candidate_sku_code": row.candidate_sku_code,
            "candidate_brand_name": row.brand_name,
            "candidate_model_name": row.model_name,
            "pool_type": "competitor",
            "primary_relation_type": row.primary_relation_type,
            "relation_types_json": row.relation_types,
            "eligibility_status": row.eligibility_status,
            "m12_summary_json": {
                "recall_sources": row.recall_sources,
                "recall_strength": row.recall_strength,
                "recall_priority_score": row.recall_priority_score,
            },
            "m13_summary_json": {
                "component_total_score": row.component_total_score,
                "role_scores": [
                    item.model_dump(mode="json") for item in row.role_scores
                ],
            },
            "m14_summary_json": {
                "selected": row.m14_selected,
                "slot_code": row.m14_slot_code,
                "slot_name_cn": row.m14_slot_name_cn,
                "selection_rank": row.m14_selection_rank,
            },
            "eligible_questions_json": row.eligible_questions,
            "data_availability_json": row.data_availability.model_dump(mode="json"),
            "market_summary_json": row.market_summary,
            "selected_questions_json": [],
            "selection_reasons_json": {},
            "confidence": Decimal(str(confidence)),
            "evidence_refs_json": _manifest_evidence_refs(row),
            "limitations_json": row.unavailable_questions,
            "risk_flags_json": row.review_reasons,
            "review_required": needs_review,
            "review_status": "review_required" if needs_review else "auto_pass",
            "review_reason_json": {"reasons": row.review_reasons},
        }
        result_hash = stable_hash(
            _json_payload(payload),
            version=PROFILE_CANDIDATE_HASH_VERSION,
        )
        result.append(
            SkuSellpointValueCandidateDraft(
                **payload,
                result_hash=result_hash,
            )
        )
    return result


def _reference_drafts(
    source: SellpointValueMaterializationInput,
    common: dict[str, Any],
) -> list[SkuSellpointValueCandidateDraft]:
    result = []
    for row in source.candidate_universe.analysis_references:
        confidence = 0.7 if row.market_summary else 0.6
        payload = {
            **common,
            "target_sku_code": source.target.sku_code,
            "candidate_sku_code": row.reference_sku_code,
            "candidate_brand_name": row.brand_name,
            "candidate_model_name": row.model_name,
            "pool_type": "reference",
            "primary_relation_type": "+".join(row.reference_purposes),
            "relation_types_json": row.reference_purposes,
            "eligibility_status": "limited",
            "m12_summary_json": {},
            "m13_summary_json": {},
            "m14_summary_json": {},
            "eligible_questions_json": [],
            "data_availability_json": {"market": bool(row.market_summary)},
            "market_summary_json": row.market_summary,
            "selected_questions_json": [],
            "selection_reasons_json": {},
            "confidence": Decimal(str(confidence)),
            "evidence_refs_json": _reference_evidence_refs(row),
            "limitations_json": ["analysis_reference_not_competitor"],
            "risk_flags_json": [],
            "review_required": False,
            "review_status": "auto_pass",
            "review_reason_json": {},
        }
        result.append(
            SkuSellpointValueCandidateDraft(
                **payload,
                result_hash=stable_hash(
                    _json_payload(payload),
                    version=PROFILE_CANDIDATE_HASH_VERSION,
                ),
            )
        )
    return result


def _value_item_drafts(
    source: SellpointValueMaterializationInput,
    common: dict[str, Any],
    value_items: Sequence[SellpointValueDecisionValueItem],
) -> list[SkuSellpointValueItemDraft]:
    result = []
    for row in value_items:
        linked_review = any(
            item.review_status == "review_required"
            for item in row.investment_decisions
        )
        needs_review = (
            row.confidence < float(PROFILE_AUTO_PASS_MIN_CONFIDENCE)
            or linked_review
        )
        result.append(
            SkuSellpointValueItemDraft(
                **common,
                result_hash=row.value_item_hash,
                sku_code=source.target.sku_code,
                battlefield_code=row.battlefield_code,
                battlefield_name_cn=row.battlefield_name_cn,
                purchase_reason_code=row.purchase_reason_code,
                purchase_reason_name_cn=row.purchase_reason_name_cn,
                value_bundle_code=row.value_bundle_code,
                value_bundle_name_cn=row.value_bundle_name_cn,
                normalized_bundle_code=row.value_bundle_code.strip().lower(),
                perceived_outcome_cn=row.perceived_outcome_cn,
                perceived_value_status=row.value_status,
                capability_codes_json=row.capability_codes,
                investment_decisions_json=[
                    item.model_dump(mode="json")
                    for item in row.investment_decisions
                ],
                investment_classifications_json=[
                    item.classification for item in row.investment_decisions
                ],
                question_result_refs_json=row.question_analyses,
                question_codes_json=sorted(
                    {
                        str(item.get("question"))
                        for item in row.question_analyses
                        if item.get("question")
                    }
                ),
                price_realization_json=row.price_realization,
                volume_realization_json=row.volume_realization,
                evidence_refs_json=[],
                evidence_boundary_cn=row.boundary_cn,
                limitations_json=row.limitations,
                confidence=Decimal(str(row.confidence)),
                review_required=needs_review,
                review_status="review_required" if needs_review else "auto_pass",
                review_reason_json={
                    "reasons": ["linked_investment_review"]
                    if linked_review
                    else ["value_confidence_low"]
                    if needs_review
                    else []
                },
            )
        )
    return result


def _profile_evidence_refs(
    rows: Sequence[ProfileSourceLineage],
) -> list[SellpointValueEvidenceRef]:
    result = []
    for row in rows:
        for index, result_hash in enumerate(sorted(row.result_hashes)):
            result.append(
                SellpointValueEvidenceRef(
                    module_code=row.module_code,
                    record_type="profile_source_lineage",
                    record_id=(
                        sorted(row.record_ids)[index]
                        if index < len(row.record_ids)
                        else f"{row.module_code}:{index}"
                    ),
                    result_hash=result_hash,
                )
            )
    return sorted(
        result,
        key=lambda row: (row.module_code, row.record_id, row.result_hash),
    )


def _manifest_evidence_refs(
    row: SellpointValueCandidateManifestItem,
) -> list[SellpointValueEvidenceRef]:
    return [
        SellpointValueEvidenceRef(
            module_code=module_code,
            record_type="candidate_manifest_source",
            record_id=f"{row.candidate_sku_code}:{module_code}",
            result_hash=result_hash,
        )
        for module_code, result_hash in sorted(row.source_hashes.items())
    ]


def _reference_evidence_refs(
    row: SellpointValueReferenceManifestItem,
) -> list[SellpointValueEvidenceRef]:
    return [
        SellpointValueEvidenceRef(
            module_code=module_code,
            record_type="reference_manifest_source",
            record_id=f"{row.reference_sku_code}:{module_code}",
            result_hash=result_hash,
        )
        for module_code, result_hash in sorted(row.source_hashes.items())
    ]


def _json_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_payload(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_payload(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def _dedupe(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


__all__ = [
    "CRITICAL_SOURCE_MODULES",
    "PROFILE_CANDIDATE_HASH_VERSION",
    "PROFILE_INPUT_HASH_VERSION",
    "PROFILE_RESULT_HASH_VERSION",
    "PROFILE_VALUE_ITEM_HASH_VERSION",
    "build_profile_input_fingerprint",
    "materialize_sellpoint_value_profile",
]
