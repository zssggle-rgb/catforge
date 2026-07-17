"""Deterministic assembly of one persisted sellpoint-value V5.1 SKU draft."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
    SellpointValueDraftBundle,
    SkuSellpointValueCandidateDraft,
    SkuSellpointValueItemDraft,
    SkuSellpointValueProfileDraft,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51MaterializationInput,
    SellpointValueV51MaterializedDraft,
    SellpointValueV51Profile,
    SellpointValueV51SourceLineage,
    SellpointValueV51ValueInput,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    CandidateSourceType,
    QuestionConclusionStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_PROFILE_INPUT_HASH_VERSION = "sellpoint_value_profile_input_v5_1"
SPV_V5_1_PROFILE_RESULT_HASH_VERSION = "sellpoint_value_profile_result_v5_1"
SPV_V5_1_VALUE_ITEM_HASH_VERSION = "sellpoint_value_value_item_v5_1"
SPV_V5_1_CANDIDATE_HASH_VERSION = "sellpoint_value_candidate_v5_1"
SPV_V5_1_CONFIG_HASH_VERSION = "sellpoint_value_config_v5_1"


def build_v5_1_profile_input_fingerprint(
    source: SellpointValueV51MaterializationInput,
) -> str:
    """Bind every saved source and rule while ignoring incidental list order."""

    return stable_hash(
        _profile_input_payload(
            project_id=source.project_id,
            category_code=source.category_code,
            batch_id=source.batch_id,
            release_scope_key=source.release_scope_key,
            profile_version=source.profile_version,
            target=source.target.model_dump(mode="json"),
            competitor_source=source.competitor_source.model_dump(mode="json"),
            candidate_pools=source.candidate_pools.model_dump(mode="json"),
            method_config=source.method_config.model_dump(mode="json"),
            source_lineage=_resolved_lineage(source),
            values=source.values,
            sku_conclusion=source.sku_conclusion.model_dump(mode="json"),
            limitations=source.limitations,
        ),
        version=SPV_V5_1_PROFILE_INPUT_HASH_VERSION,
    )


def build_v5_1_profile_input_fingerprint_from_profile(
    profile: SellpointValueV51Profile,
) -> str:
    """Recompute the input fingerprint from a typed persistence readback."""

    return stable_hash(
        _profile_input_payload(
            project_id=profile.project_id,
            category_code=profile.category_code,
            batch_id=profile.batch_id,
            release_scope_key=profile.release_scope_key,
            profile_version=profile.profile_version,
            target=profile.target.model_dump(mode="json"),
            competitor_source=profile.competitor_source.model_dump(mode="json"),
            candidate_pools=profile.candidate_pools.model_dump(mode="json"),
            method_config=profile.method_config.model_dump(mode="json"),
            source_lineage=profile.source_lineage,
            values=profile.values,
            sku_conclusion=profile.sku_conclusion.model_dump(mode="json"),
            limitations=profile.limitations,
        ),
        version=SPV_V5_1_PROFILE_INPUT_HASH_VERSION,
    )


def build_v5_1_profile_result_hash(profile: SellpointValueV51Profile) -> str:
    payload = profile.model_dump(mode="json", exclude={"result_hash"})
    return stable_hash(
        _canonical_profile_payload(payload),
        version=SPV_V5_1_PROFILE_RESULT_HASH_VERSION,
    )


def materialize_sellpoint_value_profile_v5_1(
    source: SellpointValueV51MaterializationInput,
    *,
    sellpoint_value_profile_version_id: str,
) -> SellpointValueV51MaterializedDraft:
    """Assemble a new V5.1 typed profile and its existing-table projections."""

    lineage = _resolved_lineage(source)
    values = sorted(source.values, key=lambda row: row.value_bundle_code)
    evidence_refs = _dedupe_evidence_refs(
        [
            *(ref for row in lineage for ref in row.evidence_refs),
            *(ref for row in values for ref in _value_evidence_refs(row)),
        ]
    )
    input_fingerprint = build_v5_1_profile_input_fingerprint(source)
    profile_payload = {
        "project_id": source.project_id,
        "category_code": source.category_code,
        "batch_id": source.batch_id,
        "release_scope_key": source.release_scope_key,
        "profile_version": source.profile_version,
        "target": source.target,
        "competitor_source": source.competitor_source,
        "candidate_pools": source.candidate_pools,
        "method_config": source.method_config,
        "source_lineage": lineage,
        "values": values,
        "sku_conclusion": source.sku_conclusion,
        "evidence_refs": evidence_refs,
        "limitations": sorted(set(source.limitations)),
        "input_fingerprint": input_fingerprint,
    }
    unhashed_profile = SellpointValueV51Profile(
        **profile_payload,
        result_hash="pending",
    )
    profile = unhashed_profile.model_copy(
        update={"result_hash": build_v5_1_profile_result_hash(unhashed_profile)}
    )
    persistence_bundle = project_v5_1_profile_to_persistence(
        profile,
        sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
    )
    return SellpointValueV51MaterializedDraft(
        profile=profile,
        persistence_bundle=persistence_bundle,
    )


def project_v5_1_profile_to_persistence(
    profile: SellpointValueV51Profile,
    *,
    sellpoint_value_profile_version_id: str,
) -> SellpointValueDraftBundle:
    """Rebuild deterministic table projections for persistence verification."""

    common = {
        "sellpoint_value_profile_version_id": sellpoint_value_profile_version_id,
        "project_id": profile.project_id,
        "category_code": profile.category_code,
        "batch_id": profile.batch_id,
        "product_category": profile.category_code,
        "profile_version": profile.profile_version,
        "schema_version": SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
        "rule_version": SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
        "method_version": SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
        "input_fingerprint": profile.input_fingerprint,
    }
    candidates = _candidate_drafts(profile, common)
    value_items = _value_item_drafts(profile, common)
    persisted_profile = _profile_draft(
        profile,
        common,
        candidate_hashes=[row.result_hash for row in candidates],
        value_hashes=[row.result_hash for row in value_items],
    )
    return SellpointValueDraftBundle(
        profile=persisted_profile,
        candidates=candidates,
        value_items=value_items,
    )


def _profile_draft(
    profile: SellpointValueV51Profile,
    common: Mapping[str, Any],
    *,
    candidate_hashes: Sequence[str],
    value_hashes: Sequence[str],
) -> SkuSellpointValueProfileDraft:
    conclusion = profile.sku_conclusion
    review_required = conclusion.status == QuestionConclusionStatus.INVALID
    analysis_state = {
        QuestionConclusionStatus.CONCLUSION_AVAILABLE: "ready",
        QuestionConclusionStatus.PARTIAL_CONCLUSION: "partial",
        QuestionConclusionStatus.NO_CONCLUSION: "partial",
        QuestionConclusionStatus.INVALID: "blocked",
    }[conclusion.status]
    value_statuses = [row.value_conclusion.status for row in profile.values]
    direct_results = [
        row.model_dump(mode="json")
        for value in profile.values
        for row in value.direct_market_results
    ]
    return SkuSellpointValueProfileDraft(
        **common,
        result_hash=profile.result_hash,
        sku_code=profile.target.sku_code,
        model_code=profile.target.model_code,
        model_name=profile.target.model_name,
        brand_name=profile.target.brand_name,
        display_name_cn=profile.target.display_name_cn,
        analysis_state=analysis_state,
        conclusion_status=conclusion.status,
        freshness_status="current",
        profile_confidence=conclusion.confidence_median or Decimal("0"),
        conclusion_available_count=sum(
            status == QuestionConclusionStatus.CONCLUSION_AVAILABLE
            for status in value_statuses
        ),
        partial_conclusion_count=sum(
            status == QuestionConclusionStatus.PARTIAL_CONCLUSION
            for status in value_statuses
        ),
        no_conclusion_count=sum(
            status == QuestionConclusionStatus.NO_CONCLUSION
            for status in value_statuses
        ),
        invalid_count=(
            max(
                1,
                sum(
                    status == QuestionConclusionStatus.INVALID
                    for status in value_statuses
                ),
            )
            if conclusion.status == QuestionConclusionStatus.INVALID
            else 0
        ),
        target_market_summary_json=profile.competitor_source.target_market.model_dump(
            mode="json"
        ),
        source_lineage_json=[
            {
                "record_type": "competitor_source",
                "payload": profile.competitor_source.model_dump(mode="json"),
            },
            *(
                {
                    "record_type": "source_lineage",
                    "payload": row.model_dump(mode="json"),
                }
                for row in profile.source_lineage
            ),
        ],
        candidate_universe_summary_json={
            "record_type": "candidate_pools",
            "payload": profile.candidate_pools.model_dump(mode="json"),
        },
        threshold_summary_json={
            "record_type": "method_config",
            "payload": profile.method_config.model_dump(mode="json"),
        },
        question_analyses_json=[
            {
                "record_type": "value_analysis",
                "payload": row.model_dump(mode="json"),
            }
            for row in profile.values
        ],
        investment_decisions_json=[
            {
                "value_bundle_code": value.value_bundle_code,
                "decisions": [
                    row.model_dump(mode="json") for row in value.investment_decisions
                ],
                "reviews": [
                    row.model_dump(mode="json") for row in value.investment_reviews
                ],
            }
            for value in profile.values
        ],
        price_role_json={"direct_market_results": direct_results},
        battlefield_options_json=[
            {
                "value_bundle_code": value.value_bundle_code,
                "market_archetype_results": [
                    row.model_dump(mode="json")
                    for row in value.market_archetype_results
                ],
                "synthetic_market_baseline": (
                    value.synthetic_market_baseline.model_dump(mode="json")
                    if value.synthetic_market_baseline is not None
                    else None
                ),
            }
            for value in profile.values
        ],
        pm_decisions_json={
            "record_type": "sku_conclusion",
            "payload": conclusion.model_dump(mode="json"),
        },
        qa_index_json=[
            {"record_type": "candidate", "result_hash": value}
            for value in sorted(candidate_hashes)
        ]
        + [
            {"record_type": "value", "result_hash": value}
            for value in sorted(value_hashes)
        ],
        evidence_summary_json={
            "source_lineage_count": len(profile.source_lineage),
            "formal_competitor_count": len(profile.candidate_pools.formal_competitors),
            "analysis_reference_count": len(
                profile.candidate_pools.analysis_references
            ),
            "value_count": len(profile.values),
            "local_invalid_value_count": sum(
                status == QuestionConclusionStatus.INVALID for status in value_statuses
            ),
            "evidence_ref_count": len(profile.evidence_refs),
        },
        evidence_refs_json=profile.evidence_refs,
        limitations_json=profile.limitations,
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        review_reason_json={"reasons": conclusion.review_reasons}
        if review_required
        else {},
    )


def _candidate_drafts(
    profile: SellpointValueV51Profile,
    common: Mapping[str, Any],
) -> list[SkuSellpointValueCandidateDraft]:
    result: list[SkuSellpointValueCandidateDraft] = []
    pools = profile.candidate_pools
    for candidate in pools.formal_competitors:
        result.append(
            _candidate_draft(
                profile,
                common,
                candidate_sku_code=candidate.candidate_sku_code,
                pool_type="competitor",
                brand_name=candidate.market.brand_name,
                model_name=candidate.market.model_name,
                primary_relation_type=candidate.role,
                relation_types=[candidate.role],
                confidence=candidate.business_score,
                market_payload={
                    "source": "competitor_profile_agent_snapshot_v2",
                    "source_rank": candidate.source_rank,
                    "priority_rank": candidate.selected_rank,
                    "pair_result_hash": candidate.pair_result_hash,
                    "market": candidate.market.model_dump(mode="json"),
                    "pair_facts": candidate.pair_facts.model_dump(mode="json"),
                },
            )
        )
    for reference in pools.analysis_references:
        result.append(
            _candidate_draft(
                profile,
                common,
                candidate_sku_code=reference.reference_sku_code,
                pool_type="reference",
                brand_name=reference.brand_name,
                model_name=reference.model_name,
                primary_relation_type=reference.purposes[0].value,
                relation_types=[row.value for row in reference.purposes],
                confidence=Decimal("0"),
                market_payload={
                    "source": "analysis_reference",
                    "purposes": [row.value for row in reference.purposes],
                    "also_competitor": reference.also_competitor,
                    "market": reference.market.model_dump(mode="json"),
                    "parameter_facts": reference.parameter_facts,
                    "battlefield_facts": reference.battlefield_facts,
                    "value_facts": reference.value_facts,
                    "source_hashes": dict(sorted(reference.source_hashes.items())),
                },
                direct_evidence=reference.evidence_refs,
            )
        )
    return sorted(
        result,
        key=lambda row: (row.pool_type, row.candidate_sku_code),
    )


def _candidate_draft(
    profile: SellpointValueV51Profile,
    common: Mapping[str, Any],
    *,
    candidate_sku_code: str,
    pool_type: str,
    brand_name: str | None,
    model_name: str | None,
    primary_relation_type: str,
    relation_types: list[str],
    confidence: Decimal,
    market_payload: dict[str, Any],
    direct_evidence: Sequence[SellpointValueEvidenceRef] = (),
) -> SkuSellpointValueCandidateDraft:
    source_type = (
        CandidateSourceType.COMPETITOR
        if pool_type == "competitor"
        else CandidateSourceType.MARKET_REFERENCE
    )
    uses = [
        (question.question_code, use)
        for question in profile.candidate_pools.question_candidate_sets
        for use in question.candidate_uses
        if use.source_type == source_type
        and use.candidate_sku_code == candidate_sku_code
    ]
    selected_questions = [question for question, use in uses if use.selected]
    evidence_refs = _dedupe_evidence_refs(
        [*direct_evidence, *(ref for _, use in uses for ref in use.evidence_refs)]
    )
    candidate_payload = {
        "candidate_sku_code": candidate_sku_code,
        "pool_type": pool_type,
        "primary_relation_type": primary_relation_type,
        "relation_types": sorted(set(relation_types)),
        "question_uses": [
            {
                "question_code": question,
                "use": use.model_dump(mode="json"),
            }
            for question, use in sorted(uses, key=lambda row: row[0])
        ],
        "market": market_payload,
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
    }
    result_hash = stable_hash(
        candidate_payload,
        version=SPV_V5_1_CANDIDATE_HASH_VERSION,
    )
    return SkuSellpointValueCandidateDraft(
        **common,
        result_hash=result_hash,
        target_sku_code=profile.target.sku_code,
        candidate_sku_code=candidate_sku_code,
        candidate_brand_name=brand_name,
        candidate_model_name=model_name,
        pool_type=pool_type,
        primary_relation_type=primary_relation_type,
        relation_types_json=sorted(set(relation_types)),
        eligibility_status="eligible" if selected_questions else "recalled_only",
        eligible_questions_json=sorted(selected_questions),
        data_availability_json={
            question: bool(use.usable_dimensions) for question, use in uses
        },
        market_summary_json=market_payload,
        selected_questions_json=sorted(selected_questions),
        selection_reasons_json={
            question: ";".join(use.selection_reasons or use.rejection_reasons)
            for question, use in uses
        },
        confidence=confidence.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        evidence_refs_json=evidence_refs,
        limitations_json=sorted(
            {reason for _, use in uses for reason in use.rejection_reasons}
        ),
        risk_flags_json=[],
    )


def _value_item_drafts(
    profile: SellpointValueV51Profile,
    common: Mapping[str, Any],
) -> list[SkuSellpointValueItemDraft]:
    result: list[SkuSellpointValueItemDraft] = []
    for value in profile.values:
        conclusion = value.value_conclusion
        review_required = conclusion.status == QuestionConclusionStatus.INVALID
        evidence_refs = _value_evidence_refs(value)
        payload_entries = _value_payload_entries(value)
        direct_market_available = any(
            row.status
            in {
                QuestionConclusionStatus.CONCLUSION_AVAILABLE,
                QuestionConclusionStatus.PARTIAL_CONCLUSION,
            }
            for row in value.direct_market_results
        )
        result_hash = stable_hash(
            _canonical_value_payload(value),
            version=SPV_V5_1_VALUE_ITEM_HASH_VERSION,
        )
        result.append(
            SkuSellpointValueItemDraft(
                **common,
                result_hash=result_hash,
                sku_code=profile.target.sku_code,
                battlefield_code=value.battlefield_code,
                battlefield_name_cn=value.battlefield_name_cn,
                purchase_reason_code=value.purchase_reason_code,
                purchase_reason_name_cn=value.purchase_reason_name_cn,
                value_bundle_code=value.value_bundle_code,
                value_bundle_name_cn=value.value_bundle_name_cn,
                normalized_bundle_code=value.normalized_bundle_code,
                perceived_outcome_cn=value.perceived_outcome_cn,
                perceived_value_status=conclusion.status,
                conclusion_status=conclusion.status,
                capability_codes_json=value.capability_codes,
                investment_decisions_json=[
                    {
                        "record_type": "investment_decision",
                        "payload": row.model_dump(mode="json"),
                    }
                    for row in value.investment_decisions
                ]
                + [
                    {
                        "record_type": "investment_review",
                        "payload": row.model_dump(mode="json"),
                    }
                    for row in value.investment_reviews
                ],
                investment_classifications_json=sorted(
                    {row.classification for row in value.investment_decisions}
                ),
                question_result_refs_json=payload_entries,
                question_codes_json=sorted(
                    row.question_code for row in value.question_signals
                ),
                price_realization_json={
                    "direct_market_results": [
                        row.model_dump(mode="json")
                        for row in value.direct_market_results
                        if row.price_comparison is not None
                    ],
                    "strict_market_implied_wtp": (
                        value.strict_market_implied_wtp.model_dump(mode="json")
                        if value.strict_market_implied_wtp is not None
                        else None
                    ),
                },
                volume_realization_json={
                    "direct_market_results": [
                        row.model_dump(mode="json")
                        for row in value.direct_market_results
                        if row.sales_comparison is not None
                    ],
                    "synthetic_market_baseline": (
                        value.synthetic_market_baseline.model_dump(mode="json")
                        if value.synthetic_market_baseline is not None
                        else None
                    ),
                },
                direct_market_result_available=direct_market_available,
                evidence_refs_json=evidence_refs,
                evidence_boundary_cn=value.evidence_boundary_cn,
                limitations_json=sorted(
                    set([*value.limitations, *conclusion.limitations])
                ),
                confidence=conclusion.confidence_median or Decimal("0"),
                review_required=review_required,
                review_status=("review_required" if review_required else "auto_pass"),
                review_reason_json={"reasons": conclusion.review_reasons}
                if review_required
                else {},
            )
        )
    return result


def _value_payload_entries(value: SellpointValueV51ValueInput) -> list[dict[str, Any]]:
    entries = [
        {
            "record_type": "question_signal",
            "record_id": row.question_code,
            "result_hash": row.source_result_hash,
            "payload": row.model_dump(mode="json"),
        }
        for row in value.question_signals
    ]
    entries.extend(
        {
            "record_type": "quantification",
            "record_id": row.layer.value,
            "result_hash": row.result_hash,
            "payload": row.model_dump(mode="json"),
        }
        for row in value.quantification_stack.results
    )
    for record_type, rows in (
        ("direct_market", value.direct_market_results),
        ("parameter_group", value.parameter_group_results),
        ("market_archetype", value.market_archetype_results),
    ):
        entries.extend(
            {
                "record_type": record_type,
                "record_id": row.result_hash,
                "result_hash": row.result_hash,
                "payload": row.model_dump(mode="json"),
            }
            for row in rows
        )
    for record_type, row in (
        ("synthetic_market_baseline", value.synthetic_market_baseline),
        ("strict_market_implied_wtp", value.strict_market_implied_wtp),
    ):
        if row is not None:
            entries.append(
                {
                    "record_type": record_type,
                    "record_id": row.result_hash,
                    "result_hash": row.result_hash,
                    "payload": row.model_dump(mode="json"),
                }
            )
    return sorted(
        entries,
        key=lambda row: (row["record_type"], row["record_id"]),
    )


def _resolved_lineage(
    source: SellpointValueV51MaterializationInput,
) -> list[SellpointValueV51SourceLineage]:
    rows = [
        *source.source_lineage,
        SellpointValueV51SourceLineage(
            source_code="candidate_pools",
            source_type="derived",
            version_id=source.competitor_source.competitor_profile_version_id,
            method_version="sellpoint_value_candidate_pools_v5_1",
            result_hash=source.candidate_pools.result_hash,
        ),
        SellpointValueV51SourceLineage(
            source_code="competitor_profile_sku",
            source_type="authority",
            version_id=source.competitor_source.competitor_profile_version_id,
            method_version=source.competitor_source.method_version,
            result_hash=source.competitor_source.source_result_hash,
            record_ids=[source.target.sku_code],
        ),
        SellpointValueV51SourceLineage(
            source_code="competitor_profile_version",
            source_type="authority",
            version_id=source.competitor_source.competitor_profile_version_id,
            method_version=source.competitor_source.method_version,
            result_hash=source.competitor_source.source_version_result_hash,
        ),
        SellpointValueV51SourceLineage(
            source_code="method_config",
            source_type="rule",
            version_id=source.method_config.config_version,
            method_version=source.method_config.config_version,
            result_hash=stable_hash(
                source.method_config.model_dump(mode="json"),
                version=SPV_V5_1_CONFIG_HASH_VERSION,
            ),
        ),
    ]
    codes = [row.source_code for row in rows]
    if len(codes) != len(set(codes)):
        raise ValueError("resolved source lineage codes must be unique")
    return sorted(rows, key=lambda row: row.source_code)


def _profile_input_payload(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    release_scope_key: str,
    profile_version: str,
    target: dict[str, Any],
    competitor_source: dict[str, Any],
    candidate_pools: dict[str, Any],
    method_config: dict[str, Any],
    source_lineage: Sequence[SellpointValueV51SourceLineage],
    values: Sequence[SellpointValueV51ValueInput],
    sku_conclusion: dict[str, Any],
    limitations: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
        "rule_version": SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
        "method_version": SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "release_scope_key": release_scope_key,
        "profile_version": profile_version,
        "target": target,
        "competitor_source": competitor_source,
        "candidate_pools": candidate_pools,
        "candidate_pools_hash": candidate_pools["result_hash"],
        "method_config": method_config,
        "source_lineage": [
            row.model_dump(mode="json")
            for row in sorted(source_lineage, key=lambda item: item.source_code)
        ],
        "values": [
            _canonical_value_payload(row)
            for row in sorted(values, key=lambda item: item.value_bundle_code)
        ],
        "sku_conclusion": sku_conclusion,
        "limitations": sorted(set(limitations)),
    }


def _canonical_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["source_lineage"] = sorted(
        result.get("source_lineage") or [],
        key=lambda row: row["source_code"],
    )
    result["values"] = sorted(
        result.get("values") or [],
        key=lambda row: row["value_bundle_code"],
    )
    result["evidence_refs"] = sorted(
        result.get("evidence_refs") or [],
        key=_evidence_payload_key,
    )
    result["limitations"] = sorted(set(result.get("limitations") or []))
    return result


def _canonical_value_payload(
    value: SellpointValueV51ValueInput,
) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    for field_name, key in (
        ("question_signals", lambda row: row["question_code"]),
        ("direct_market_results", lambda row: row["result_hash"]),
        ("parameter_group_results", lambda row: row["result_hash"]),
        ("market_archetype_results", lambda row: row["result_hash"]),
        (
            "investment_decisions",
            lambda row: (
                row["question_code"],
                row["capability_code"],
                row["result_hash"],
            ),
        ),
        (
            "investment_reviews",
            lambda row: (row["question_code"], row["result_hash"]),
        ),
    ):
        payload[field_name] = sorted(payload[field_name], key=key)
    payload["capability_codes"] = sorted(set(payload["capability_codes"]))
    payload["limitations"] = sorted(set(payload["limitations"]))
    payload["quantification_stack"]["results"] = sorted(
        payload["quantification_stack"]["results"],
        key=lambda row: row["layer"],
    )
    return payload


def _value_evidence_refs(
    value: SellpointValueV51ValueInput,
) -> list[SellpointValueEvidenceRef]:
    return _dedupe_evidence_refs(
        [
            *(ref for row in value.question_signals for ref in row.evidence_refs),
            *(ref for row in value.direct_market_results for ref in row.evidence_refs),
            *(
                ref
                for row in value.parameter_group_results
                for ref in row.evidence_refs
            ),
            *(
                ref
                for row in value.market_archetype_results
                for ref in row.evidence_refs
            ),
            *(ref for row in value.investment_decisions for ref in row.evidence_refs),
            *(ref for row in value.investment_reviews for ref in row.evidence_refs),
            *(
                value.synthetic_market_baseline.evidence_refs
                if value.synthetic_market_baseline is not None
                else []
            ),
            *(
                value.strict_market_implied_wtp.evidence_refs
                if value.strict_market_implied_wtp is not None
                else []
            ),
            *value.value_conclusion.evidence_refs,
        ]
    )


def _dedupe_evidence_refs(
    values: Iterable[SellpointValueEvidenceRef],
) -> list[SellpointValueEvidenceRef]:
    rows: dict[tuple[Any, ...], SellpointValueEvidenceRef] = {}
    for row in values:
        payload = row.model_dump(mode="json")
        rows[_evidence_payload_key(payload)] = row
    return [rows[key] for key in sorted(rows)]


def _evidence_payload_key(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        payload.get("module_code"),
        payload.get("record_type"),
        payload.get("record_id"),
        payload.get("result_hash"),
    )


__all__ = [
    "SPV_V5_1_CANDIDATE_HASH_VERSION",
    "SPV_V5_1_PROFILE_INPUT_HASH_VERSION",
    "SPV_V5_1_PROFILE_RESULT_HASH_VERSION",
    "SPV_V5_1_VALUE_ITEM_HASH_VERSION",
    "build_v5_1_profile_input_fingerprint",
    "build_v5_1_profile_input_fingerprint_from_profile",
    "build_v5_1_profile_result_hash",
    "materialize_sellpoint_value_profile_v5_1",
    "project_v5_1_profile_to_persistence",
]
