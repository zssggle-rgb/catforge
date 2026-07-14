"""Build conclusion-free target×candidate facts from the canonical input bundle."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineRun,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    COMPETITOR_PROFILE_SOURCE_MODULES,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairAlignedFeature,
    PairFeatureBundle,
    PairFeatureRecord,
    PairModuleAvailability,
    PairProductFormFacts,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    EvidenceRef,
    PairMarketComparison,
)
from app.services.core3_real_data.hash_utils import stable_hash


_REVIEW_STATUSES = {
    "blocked",
    "failed",
    "needs_review",
    "pending_review",
    "review_required",
}
_LINEAGE_CONFLICT_STATUSES = {"ambiguous", "conflict", "invalid", "mismatch"}
_MISSING_TEXT_VALUES = {"", "-", "n/a", "none", "null", "unknown"}


class PairFeatureError(RuntimeError):
    """Raised when pair inputs do not preserve the canonical candidate pipeline."""


@dataclass
class _FeatureObservation:
    values: set[str] = field(default_factory=set)
    refs: dict[tuple[str, str, str, str, str], EvidenceRef] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class _MarketFacts:
    price: Decimal | None
    weekly_volume: Decimal | None
    total_volume: Decimal | None
    sales_amount: Decimal | None
    screen_size: Decimal | None
    size_segment: str | None
    price_percentile: Decimal | None
    volume_percentile: Decimal | None
    active_week_count: int | None
    platform_count: int | None
    common_week_count: int | None
    common_platform_count: int | None
    diagnostics: Mapping[str, Any]


class PairFeatureBuilder:
    """Materialize factual pair DTOs without evaluating purchase or relation gates."""

    def build(self, pipeline: CandidatePipelineRun) -> PairFeatureBundle:
        self._assert_pipeline(pipeline)
        category = pipeline.category_bundle
        target_bundle = pipeline.target_bundle
        recall = pipeline.recall_manifest
        eligibility = pipeline.eligibility_manifest
        target_code = target_bundle.target_sku_code
        target_records = _records_for_sku(pipeline, target_code)
        target_identity = _target_identity(pipeline, target_records)
        recalled_by_sku = {row.candidate.sku_code: row for row in recall.candidates}
        eligible_by_sku = {
            row.candidate.sku_code: row for row in eligibility.candidates
        }

        pairs = [
            self._pair(
                pipeline=pipeline,
                target_identity=target_identity,
                target_records=target_records,
                recalled=recalled_by_sku[candidate_code],
                eligibility=eligible_by_sku[candidate_code],
            )
            for candidate_code in sorted(recalled_by_sku)
        ]
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category.input_fingerprint,
                "target_input_fingerprint": target_bundle.input_fingerprint,
                "recall_result_hash": recall.result_hash,
                "eligibility_result_hash": eligibility.result_hash,
                "determinism_result_hash": pipeline.receipt.result_hash,
            },
            version="competitor_profile_pair_feature_input_v1",
        )
        return PairFeatureBundle(
            project_id=category.serving_scope.project_id,
            category_code=category.serving_scope.category_code,
            product_category=category.serving_scope.product_category,
            release_scope_key=category.serving_scope.release_scope_key,
            target=target_identity,
            candidate_count=len(pairs),
            pairs=pairs,
            recall_result_hash=recall.result_hash,
            eligibility_result_hash=eligibility.result_hash,
            determinism_result_hash=pipeline.receipt.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "input_fingerprint": input_fingerprint,
                    "pair_hashes": {
                        row.candidate.sku_code: row.result_hash for row in pairs
                    },
                },
                version="competitor_profile_pair_feature_result_v1",
            ),
        )

    @staticmethod
    def _assert_pipeline(pipeline: CandidatePipelineRun) -> None:
        category = pipeline.category_bundle
        target = pipeline.target_bundle
        recall = pipeline.recall_manifest
        eligibility = pipeline.eligibility_manifest
        receipt = pipeline.receipt
        if category.serving_scope != target.serving_scope:
            raise PairFeatureError("pair feature inputs must share one serving scope")
        recall_codes = [row.candidate.sku_code for row in recall.candidates]
        eligibility_codes = [row.candidate.sku_code for row in eligibility.candidates]
        if recall_codes != eligibility_codes:
            raise PairFeatureError(
                "pair feature inputs do not conserve eligibility candidates"
            )
        if (
            receipt.recall_result_hash != recall.result_hash
            or receipt.eligibility_result_hash != eligibility.result_hash
        ):
            raise PairFeatureError(
                "pair feature inputs are not chained to the determinism receipt"
            )
        if receipt.target_sku_code != target.target_sku_code:
            raise PairFeatureError(
                "pair feature target conflicts with determinism receipt"
            )

    def _pair(
        self,
        *,
        pipeline: CandidatePipelineRun,
        target_identity: CandidateIdentity,
        target_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
        recalled: Any,
        eligibility: Any,
    ) -> PairFeatureRecord:
        candidate_code = recalled.candidate.sku_code
        candidate_records = _records_for_sku(pipeline, candidate_code)
        module_availability = [
            _module_availability(
                pipeline,
                module_code,
                candidate_code,
                target_records[module_code],
                candidate_records[module_code],
            )
            for module_code in COMPETITOR_PROFILE_SOURCE_MODULES
        ]
        module_availability.sort(key=lambda row: row.module_code)
        aligned_features = _aligned_features(target_records, candidate_records)
        product_form = _product_form_facts(
            pipeline,
            target_records,
            candidate_records,
        )
        market = _market_comparison(
            pipeline,
            target_records["M07"],
            candidate_records["M07"],
        )
        all_records = [
            record
            for module_code in COMPETITOR_PROFILE_SOURCE_MODULES
            for record in (
                *target_records[module_code],
                *candidate_records[module_code],
            )
        ]
        evidence_refs = _dedupe_refs(_evidence_ref(record) for record in all_records)
        review_reasons = sorted(
            {
                *eligibility.review_reason_codes,
                *(
                    reason
                    for availability in module_availability
                    for reason in availability.review_reason_codes
                ),
            }
        )
        conflict_reasons = sorted(
            {
                reason
                for availability in module_availability
                for reason in availability.lineage_conflict_reason_codes
            }
        )
        unknown_reasons = sorted(
            {
                *recalled.unknown_reason_codes,
                *product_form.unknown_reason_codes,
                *market.unknown_reasons,
                *(
                    availability.target_missing_reason_code
                    for availability in module_availability
                    if availability.target_missing_reason_code
                ),
                *(
                    availability.candidate_missing_reason_code
                    for availability in module_availability
                    if availability.candidate_missing_reason_code
                ),
            }
        )
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": pipeline.category_bundle.input_fingerprint,
                "target_input_fingerprint": pipeline.target_bundle.input_fingerprint,
                "recalled_candidate_result_hash": recalled.result_hash,
                "eligibility_candidate_result_hash": eligibility.result_hash,
                "evidence_refs": [_ref_key(ref) for ref in evidence_refs],
            },
            version="competitor_profile_pair_feature_pair_input_v1",
        )
        payload = {
            "target": target_identity.model_dump(mode="python"),
            "candidate": recalled.candidate.model_dump(mode="python"),
            "candidate_status": eligibility.candidate_status,
            "relation_evaluation_member": eligibility.relation_evaluation_member,
            "competitor_member": False,
            "reference_member": eligibility.reference_member,
            "recall_sources": recalled.recall_sources,
            "module_hashes": [row.result_hash for row in module_availability],
            "product_form_hash": product_form.result_hash,
            "market_hash": market.result_hash,
            "aligned_feature_hashes": [row.result_hash for row in aligned_features],
            "unknown_reason_codes": unknown_reasons,
            "review_reason_codes": review_reasons,
            "lineage_conflict_reason_codes": conflict_reasons,
            "evidence_refs": [_ref_key(ref) for ref in evidence_refs],
            "recall_result_hash": recalled.result_hash,
            "eligibility_result_hash": eligibility.result_hash,
            "input_fingerprint": input_fingerprint,
        }
        return PairFeatureRecord(
            target=target_identity,
            candidate=recalled.candidate,
            candidate_status=eligibility.candidate_status,
            relation_evaluation_member=eligibility.relation_evaluation_member,
            competitor_member=False,
            reference_member=eligibility.reference_member,
            recall_sources=recalled.recall_sources,
            module_availability=module_availability,
            product_form_facts=product_form,
            market_comparison=market,
            aligned_features=aligned_features,
            unknown_reason_codes=unknown_reasons,
            review_reason_codes=review_reasons,
            lineage_conflict_reason_codes=conflict_reasons,
            evidence_refs=evidence_refs,
            relation_status="not_evaluated",
            business_conclusion_allowed=False,
            causal_claim=False,
            recall_result_hash=recalled.result_hash,
            eligibility_result_hash=eligibility.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                payload,
                version="competitor_profile_pair_feature_pair_result_v1",
            ),
        )


def _records_for_sku(
    pipeline: CandidatePipelineRun,
    sku_code: str,
) -> dict[str, tuple[UpstreamRecordSnapshot, ...]]:
    return {
        module_code: tuple(module.records_by_sku.get(sku_code, []))
        for module_code, module in pipeline.category_bundle.modules.items()
    }


def _target_identity(
    pipeline: CandidatePipelineRun,
    records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
) -> CandidateIdentity:
    source = pipeline.target_bundle.target_identity
    market = _first_facts(records["M07"])
    brand = _known_text(
        source.get("brand_name") or market.get("brand_name") or market.get("brand")
    )
    model = _known_text(source.get("model_name") or market.get("model_name"))
    display_name = _known_text(source.get("display_name_cn")) or " ".join(
        value for value in (brand, model) if value
    )
    return CandidateIdentity(
        sku_code=pipeline.target_bundle.target_sku_code,
        brand_name=brand,
        model_name=model,
        display_name_cn=display_name or pipeline.target_bundle.target_sku_code,
        product_category=pipeline.category_bundle.serving_scope.product_category,
    )


def _module_availability(
    pipeline: CandidatePipelineRun,
    module_code: str,
    candidate_code: str,
    target_records: Sequence[UpstreamRecordSnapshot],
    candidate_records: Sequence[UpstreamRecordSnapshot],
) -> PairModuleAvailability:
    target_module = pipeline.target_bundle.modules[module_code]
    target_availability = "present" if target_records else "unknown"
    candidate_availability = "present" if candidate_records else "unknown"
    target_missing = (
        None
        if target_records
        else target_module.missing_reason_code
        or f"target_{module_code.lower()}_unknown"
    )
    candidate_missing = (
        None
        if candidate_records
        else f"candidate_{module_code.lower()}_not_covered_by_locked_authority"
    )
    review, conflicts = _quality_reasons(
        (("target", record) for record in target_records),
        (("candidate", record) for record in candidate_records),
    )
    evidence_refs = _dedupe_refs(
        _evidence_ref(record) for record in (*target_records, *candidate_records)
    )
    model_payload = {
        "module_code": module_code,
        "target_availability": target_availability,
        "candidate_availability": candidate_availability,
        "target_record_count": len(target_records),
        "candidate_record_count": len(candidate_records),
        "target_missing_reason_code": target_missing,
        "candidate_missing_reason_code": candidate_missing,
        "review_reason_codes": review,
        "lineage_conflict_reason_codes": conflicts,
    }
    return PairModuleAvailability(
        **model_payload,
        evidence_refs=evidence_refs,
        result_hash=stable_hash(
            {
                **model_payload,
                "evidence_refs": [_ref_key(ref) for ref in evidence_refs],
            },
            version="competitor_profile_pair_module_availability_v1",
        ),
    )


def _quality_reasons(
    *groups: Iterable[tuple[str, UpstreamRecordSnapshot]],
) -> tuple[list[str], list[str]]:
    reviews: set[str] = set()
    conflicts: set[str] = set()
    for group in groups:
        for side, record in group:
            module = record.module_code.lower()
            for key, value in _walk_items(record.facts):
                text = _known_text(value)
                if key == "review_required" and value is True:
                    reviews.add(f"{side}_{module}_review_required")
                elif key == "review_required_count" and (_decimal(value) or 0) > 0:
                    reviews.add(f"{side}_{module}_review_required_count_positive")
                elif (
                    key in {"processing_status", "review_status"}
                    and text in _REVIEW_STATUSES
                ):
                    reviews.add(f"{side}_{module}_{key}_{text}")
                elif key == "conflict_count" and (_decimal(value) or 0) > 0:
                    conflicts.add(f"{side}_{module}_conflict_count_positive")
                elif (
                    key
                    in {
                        "evidence_lineage_status",
                        "lineage_status",
                        "source_lineage_status",
                    }
                    and text in _LINEAGE_CONFLICT_STATUSES
                ):
                    conflicts.add(f"{side}_{module}_lineage_{text}")
                elif (
                    key in {"quality_flags", "risk_flags"}
                    and text
                    and ("lineage_conflict" in text or "source_mismatch" in text)
                ):
                    conflicts.add(f"{side}_{module}_{text}")
    return sorted(reviews), sorted(conflicts)


def _aligned_features(
    target_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
    candidate_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
) -> list[PairAlignedFeature]:
    result: list[PairAlignedFeature] = []
    for module_code in COMPETITOR_PROFILE_SOURCE_MODULES:
        target = _module_features(module_code, target_records[module_code])
        candidate = _module_features(module_code, candidate_records[module_code])
        for feature_group, feature_code in sorted(set(target) | set(candidate)):
            target_observation = target.get(
                (feature_group, feature_code), _FeatureObservation()
            )
            candidate_observation = candidate.get(
                (feature_group, feature_code), _FeatureObservation()
            )
            target_values = sorted(target_observation.values)
            candidate_values = sorted(candidate_observation.values)
            common_values = sorted(
                target_observation.values & candidate_observation.values
            )
            if target_values and candidate_values:
                status = "shared" if common_values else "different"
            else:
                status = "target_only" if target_values else "candidate_only"
            target_refs = [
                target_observation.refs[key] for key in sorted(target_observation.refs)
            ]
            candidate_refs = [
                candidate_observation.refs[key]
                for key in sorted(candidate_observation.refs)
            ]
            model_payload = {
                "feature_group": feature_group,
                "module_code": module_code,
                "feature_code": feature_code,
                "target_values": target_values,
                "candidate_values": candidate_values,
                "common_values": common_values,
                "comparison_status": status,
                "factual_only": True,
                "advantage_claim": False,
                "relation_claim": False,
            }
            result.append(
                PairAlignedFeature(
                    **model_payload,
                    target_evidence_refs=target_refs,
                    candidate_evidence_refs=candidate_refs,
                    result_hash=stable_hash(
                        {
                            **model_payload,
                            "target_evidence_refs": [
                                _ref_key(ref) for ref in target_refs
                            ],
                            "candidate_evidence_refs": [
                                _ref_key(ref) for ref in candidate_refs
                            ],
                        },
                        version="competitor_profile_pair_aligned_feature_v1",
                    ),
                )
            )
    return sorted(
        result,
        key=lambda row: (row.feature_group, row.module_code, row.feature_code),
    )


def _module_features(
    module_code: str,
    records: Sequence[UpstreamRecordSnapshot],
) -> dict[tuple[str, str], _FeatureObservation]:
    result: dict[tuple[str, str], _FeatureObservation] = {}
    for record in records:
        ref = _evidence_ref(record)
        facts = record.facts
        if module_code == "M03B":
            _parameter_features(result, facts, ref)
        elif module_code == "M04C":
            _role_features(
                result,
                "claim_expression",
                facts,
                ref,
                {
                    "claim_codes": "expressed",
                    "fact_claim_codes": "fact_supported",
                    "service_claim_codes": "service_separate",
                    "supported_claim_codes": "supported",
                    "unsupported_claim_codes": "unsupported",
                },
                single_code_key="claim_code",
                single_role_key="claim_status",
            )
        elif module_code == "M05C":
            _role_features(
                result,
                "user_realization",
                facts,
                ref,
                {
                    "supported_claim_codes": "user_supported",
                    "supported_param_codes": "user_supported",
                    "contradicted_claim_codes": "user_contradicted",
                    "contradicted_param_codes": "user_contradicted",
                    "unmentioned_claim_codes": "not_observed",
                    "unmentioned_param_codes": "not_observed",
                    "topic_codes": "observed_topic",
                    "value_codes": "observed_value",
                },
                single_code_key="topic_code",
                single_role_key="support_status",
            )
        elif module_code == "M09C":
            _role_features(
                result,
                "task",
                facts,
                ref,
                {
                    "primary_user_task_code": "primary",
                    "secondary_user_task_codes_json": "secondary",
                    "comment_observed_task_codes_json": "comment_observed",
                    "latent_capability_task_codes_json": "latent_capability",
                },
            )
        elif module_code == "M10C":
            _role_features(
                result,
                "audience",
                facts,
                ref,
                {
                    "primary_target_group_code": "primary",
                    "secondary_target_group_codes_json": "secondary",
                    "comment_observed_group_codes_json": "comment_observed",
                    "latent_group_codes_json": "latent",
                },
            )
        elif module_code == "M11C":
            _role_features(
                result,
                "battlefield",
                facts,
                ref,
                {
                    "primary_battlefield_code": "primary",
                    "secondary_battlefield_codes_json": "secondary",
                    "opportunity_battlefield_codes_json": "opportunity",
                },
            )
        elif module_code == "M11D":
            code = _known_text(facts.get("dimension_code"))
            role = _known_text(facts.get("allocation_role"))
            if code and role:
                _add_feature(result, "market_position", code, role, ref)
        elif module_code == "M12C":
            code = _known_text(facts.get("claim_code"))
            role = _known_text(facts.get("claim_value_role"))
            if code and role:
                _add_feature(result, "claim_value", code, f"role:{role}", ref)
            context_type = _known_text(facts.get("context_type"))
            context_code = _known_text(facts.get("context_code"))
            if code and context_type and context_code:
                _add_feature(
                    result,
                    "claim_value",
                    code,
                    f"context:{context_type}:{context_code}",
                    ref,
                )
        elif module_code == "M12D":
            _purchase_reason_features(result, facts, ref)
    return result


def _parameter_features(
    result: dict[tuple[str, str], _FeatureObservation],
    facts: Mapping[str, Any],
    ref: EvidenceRef,
) -> None:
    payload_keys = [
        "param_values_json",
        "core_picture_params_json",
        "core_gaming_params_json",
        "core_system_params_json",
        "core_eye_care_params_json",
    ]
    for payload_key in payload_keys:
        payload = facts.get(payload_key)
        if not isinstance(payload, Mapping):
            continue
        for code, value in payload.items():
            normalized_code = _known_text(code)
            normalized_value = _parameter_value(value)
            if normalized_code and normalized_value:
                _add_feature(
                    result,
                    "parameter",
                    normalized_code,
                    normalized_value,
                    ref,
                )
    code = _known_text(facts.get("param_code"))
    value = _parameter_value(
        _first_not_none(
            facts.get("normalized_value"),
            facts.get("param_value"),
            facts.get("value"),
        )
    )
    if code and value:
        _add_feature(result, "parameter", code, value, ref)


def _role_features(
    result: dict[tuple[str, str], _FeatureObservation],
    feature_group: str,
    facts: Mapping[str, Any],
    ref: EvidenceRef,
    fields: Mapping[str, str],
    *,
    single_code_key: str | None = None,
    single_role_key: str | None = None,
) -> None:
    for field_name, role in fields.items():
        for code in _codes(facts.get(field_name)):
            _add_feature(result, feature_group, code, role, ref)
    if single_code_key:
        code = _known_text(facts.get(single_code_key))
        role = _known_text(facts.get(single_role_key)) if single_role_key else None
        if code:
            _add_feature(result, feature_group, code, role or "observed", ref)


def _purchase_reason_features(
    result: dict[tuple[str, str], _FeatureObservation],
    facts: Mapping[str, Any],
    ref: EvidenceRef,
) -> None:
    fields = {
        "core_reasons_json": "core_reason",
        "core_payment_anchors_json": "core_payment_anchor",
        "supporting_anchors_json": "supporting_anchor",
        "weak_expression_anchors_json": "weak_expression_anchor",
        "risk_drag_anchors_json": "risk_drag_anchor",
        "established_anchors_json": "established_anchor",
        "proposition_anchors_json": "proposition_anchor",
    }
    for field_name, role in fields.items():
        for code in _codes(facts.get(field_name)):
            _add_feature(result, "purchase_reason", code, role, ref)


def _add_feature(
    result: dict[tuple[str, str], _FeatureObservation],
    feature_group: str,
    feature_code: str,
    value: str,
    ref: EvidenceRef,
) -> None:
    key = (feature_group, feature_code)
    observation = result.setdefault(key, _FeatureObservation())
    observation.values.add(value)
    observation.refs[_ref_key(ref)] = ref


def _product_form_facts(
    pipeline: CandidatePipelineRun,
    target_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
    candidate_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
) -> PairProductFormFacts:
    category = pipeline.category_bundle.serving_scope.product_category
    target_market = _market_facts(target_records["M07"])
    candidate_market = _market_facts(candidate_records["M07"])
    unknown: set[str] = set()
    payload: dict[str, Any] = {
        "product_category": category,
        "target_screen_size_inch": None,
        "candidate_screen_size_inch": None,
        "target_size_segment": target_market.size_segment,
        "candidate_size_segment": candidate_market.size_segment,
        "target_ac_form": None,
        "candidate_ac_form": None,
        "target_ac_capacity": None,
        "candidate_ac_capacity": None,
        "compatibility_status": "not_evaluated",
    }
    if category == "TV":
        payload["target_screen_size_inch"] = target_market.screen_size
        payload["candidate_screen_size_inch"] = candidate_market.screen_size
        if target_market.screen_size is None and not target_market.size_segment:
            unknown.add("target_tv_size_unknown")
        if candidate_market.screen_size is None and not candidate_market.size_segment:
            unknown.add("candidate_tv_size_unknown")
    else:
        target_params = _parameter_map(target_records["M03B"])
        candidate_params = _parameter_map(candidate_records["M03B"])
        config = pipeline.recall_manifest.config
        payload["target_ac_form"] = _first_param(
            target_params, config.ac_form_param_codes
        )
        payload["candidate_ac_form"] = _first_param(
            candidate_params, config.ac_form_param_codes
        )
        payload["target_ac_capacity"] = _first_param(
            target_params, config.ac_capacity_param_codes
        )
        payload["candidate_ac_capacity"] = _first_param(
            candidate_params, config.ac_capacity_param_codes
        )
        for field_name in (
            "target_ac_form",
            "candidate_ac_form",
            "target_ac_capacity",
            "candidate_ac_capacity",
        ):
            if payload[field_name] is None:
                unknown.add(f"{field_name}_unknown")
    payload["unknown_reason_codes"] = sorted(unknown)
    return PairProductFormFacts(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_pair_product_form_facts_v1",
        ),
    )


def _market_comparison(
    pipeline: CandidatePipelineRun,
    target_records: Sequence[UpstreamRecordSnapshot],
    candidate_records: Sequence[UpstreamRecordSnapshot],
) -> PairMarketComparison:
    target = _market_facts(target_records)
    candidate = _market_facts(candidate_records)
    unknown: set[str] = set()
    if not target_records:
        unknown.add("target_market_unknown")
    if not candidate_records:
        unknown.add("candidate_market_unknown")
    for side, facts in (("target", target), ("candidate", candidate)):
        if facts.price is None:
            unknown.add(f"{side}_weighted_price_unknown")
        if facts.weekly_volume is None:
            unknown.add(f"{side}_avg_weekly_volume_unknown")
    price_gap = None
    price_gap_pct = None
    if target.price is not None and candidate.price is not None:
        price_gap = _quantize(candidate.price - target.price, "0.0001")
        if target.price > 0:
            price_gap_pct = _quantize(price_gap / target.price, "0.000001")
        else:
            unknown.add("target_weighted_price_zero_for_ratio")
    volume_gap = None
    volume_ratio = None
    if target.weekly_volume is not None and candidate.weekly_volume is not None:
        volume_gap = _quantize(
            candidate.weekly_volume - target.weekly_volume,
            "0.000001",
        )
        if target.weekly_volume > 0:
            volume_ratio = _quantize(
                candidate.weekly_volume / target.weekly_volume,
                "0.000001",
            )
        else:
            unknown.add("target_avg_weekly_volume_zero_for_ratio")
    if not target_records or not candidate_records:
        comparability = "unknown"
    elif not unknown:
        comparability = "comparable"
    else:
        comparability = "limited"
    common_week = _same_known_int(
        target.common_week_count,
        candidate.common_week_count,
    )
    common_platform = _same_known_int(
        target.common_platform_count,
        candidate.common_platform_count,
    )
    diagnostics = {
        key: value
        for key, value in {
            "target": dict(target.diagnostics),
            "candidate": dict(candidate.diagnostics),
        }.items()
        if value
    }
    payload = {
        "source_authority": pipeline.category_bundle.modules[
            "M07"
        ].authority.model_dump(mode="python"),
        "analysis_population": pipeline.category_bundle.serving_scope.analysis_population,
        "market_window": pipeline.category_bundle.serving_scope.market_window,
        "comparability_status": comparability,
        "target_weighted_price": target.price,
        "candidate_weighted_price": candidate.price,
        "price_gap": price_gap,
        "price_gap_pct": price_gap_pct,
        "target_avg_weekly_volume": target.weekly_volume,
        "candidate_avg_weekly_volume": candidate.weekly_volume,
        "weekly_volume_gap": volume_gap,
        "weekly_volume_ratio": volume_ratio,
        "target_price_percentile": target.price_percentile,
        "candidate_price_percentile": candidate.price_percentile,
        "target_volume_percentile": target.volume_percentile,
        "candidate_volume_percentile": candidate.volume_percentile,
        "target_total_sales": target.total_volume,
        "candidate_total_sales": candidate.total_volume,
        "target_sales_amount": target.sales_amount,
        "candidate_sales_amount": candidate.sales_amount,
        "common_week_count": common_week,
        "common_platform_count": common_platform,
        "diagnostics": diagnostics,
        "unknown_reasons": sorted(unknown),
        "causal_claim": False,
    }
    return PairMarketComparison(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_pair_market_comparison_v1",
        ),
    )


def _market_facts(records: Sequence[UpstreamRecordSnapshot]) -> _MarketFacts:
    facts = _first_facts(records)
    total_volume = _decimal(facts.get("sales_volume_total"))
    active_weeks = _int(facts.get("active_week_count"))
    weekly_volume = _decimal(
        _first_not_none(
            facts.get("avg_weekly_volume"),
            facts.get("weekly_volume"),
        )
    )
    if (
        weekly_volume is None
        and total_volume is not None
        and active_weeks
        and active_weeks > 0
    ):
        weekly_volume = _quantize(total_volume / Decimal(active_weeks), "0.000001")
    diagnostics = {
        key: value
        for key, value in {
            "active_week_count": active_weeks,
            "platform_count": _int(facts.get("platform_count")),
            "promotion_suspect_flag": (
                facts.get("promotion_suspect_flag")
                if isinstance(facts.get("promotion_suspect_flag"), bool)
                else None
            ),
            "market_row_count": _int(facts.get("market_row_count")),
        }.items()
        if value is not None
    }
    return _MarketFacts(
        price=_decimal(
            _first_not_none(facts.get("price_wavg"), facts.get("weighted_price"))
        ),
        weekly_volume=weekly_volume,
        total_volume=total_volume,
        sales_amount=_decimal(
            _first_not_none(
                facts.get("sales_amount_total"),
                facts.get("sales_amount"),
            )
        ),
        screen_size=_decimal(facts.get("screen_size_inch")),
        size_segment=_known_text(facts.get("size_segment")),
        price_percentile=_decimal(
            _first_not_none(
                facts.get("same_pool_price_percentile"),
                facts.get("price_percentile_in_size"),
                facts.get("price_percentile"),
            )
        ),
        volume_percentile=_decimal(
            _first_not_none(
                facts.get("same_pool_volume_percentile"),
                facts.get("volume_percentile_in_size"),
                facts.get("sales_percentile"),
            )
        ),
        active_week_count=active_weeks,
        platform_count=_int(facts.get("platform_count")),
        common_week_count=_int(facts.get("common_week_count")),
        common_platform_count=_int(facts.get("common_platform_count")),
        diagnostics=diagnostics,
    )


def _parameter_map(
    records: Sequence[UpstreamRecordSnapshot],
) -> dict[str, list[str]]:
    features = _module_features("M03B", records)
    return {
        code: sorted(observation.values)
        for (group, code), observation in features.items()
        if group == "parameter"
    }


def _first_param(values: Mapping[str, list[str]], codes: Sequence[str]) -> str | None:
    for code in codes:
        known = values.get(code.lower())
        if known:
            return known[0]
    return None


def _parameter_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in (
            "normalized_value",
            "tier_code",
            "value",
            "text",
            "raw_value",
        ):
            normalized = _known_text(value.get(key))
            if normalized:
                return normalized
        return None
    return _known_text(value)


def _codes(value: Any) -> list[str]:
    result: set[str] = set()
    _collect_codes(value, result)
    return sorted(result)


def _collect_codes(value: Any, result: set[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        normalized = _known_text(value)
        if normalized:
            result.add(normalized)
        return
    if isinstance(value, Mapping):
        found = False
        for key in (
            "anchor_code",
            "reason_code",
            "claim_code",
            "value_code",
            "task_code",
            "group_code",
            "battlefield_code",
            "code",
        ):
            if key in value:
                found = True
                _collect_codes(value[key], result)
        if not found:
            for nested in value.values():
                if isinstance(nested, (Mapping, list, tuple, set)):
                    _collect_codes(nested, result)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for nested in value:
            _collect_codes(nested, result)


def _walk_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if not isinstance(nested, (Mapping, list, tuple, set)):
                yield normalized_key, nested
            elif isinstance(nested, (list, tuple, set)):
                for item in nested:
                    if not isinstance(item, (Mapping, list, tuple, set)):
                        yield normalized_key, item
            yield from _walk_items(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _walk_items(nested)


def _same_known_int(left: int | None, right: int | None) -> int | None:
    return left if left is not None and left == right else None


def _first_facts(records: Sequence[UpstreamRecordSnapshot]) -> dict[str, Any]:
    return dict(records[0].facts) if records else {}


def _first_not_none(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _known_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized not in _MISSING_TEXT_VALUES else None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int | None:
    decimal = _decimal(value)
    if decimal is None or decimal != decimal.to_integral_value():
        return None
    return int(decimal)


def _quantize(value: Decimal, precision: str) -> Decimal:
    return value.quantize(Decimal(precision))


def _evidence_ref(record: UpstreamRecordSnapshot) -> EvidenceRef:
    return EvidenceRef(
        module_code=record.module_code,
        profile_version=record.profile_version,
        rule_version=record.rule_version,
        taxonomy_version=record.taxonomy_version,
        record_type=record.record_type,
        record_id=record.record_id,
        result_hash=record.result_hash,
        source_batch_id=record.source_batch_id,
    )


def _dedupe_refs(values: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {_ref_key(ref): ref for ref in values}
    return [by_key[key] for key in sorted(by_key)]


def _ref_key(ref: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        ref.module_code,
        ref.source_batch_id or "",
        ref.record_type,
        ref.record_id,
        ref.result_hash,
    )


__all__ = ["PairFeatureBuilder", "PairFeatureError"]
