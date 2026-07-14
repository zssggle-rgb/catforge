"""Evaluate value-substitution evidence without creating competitor relations."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairAlignedFeature,
    PairFeatureBundle,
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticBundle,
    PurchasePoolSemanticPairAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import EvidenceRef
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    PurchaseReasonAssessment,
    ValueCodeAssessment,
    ValueLayerAssessment,
    ValueSubstitutionConfig,
    ValueSubstitutionEvidenceBundle,
    ValueSubstitutionEvidencePair,
)
from app.services.core3_real_data.hash_utils import stable_hash


_LAYER_META = (
    ("F1_purchase_reason", "purchase_reason", "M12D", "F1_purchase_reason"),
    ("F4_claim_value", "claim_value", "M12C", "F4_user_realization"),
    ("F4_user_realization", "user_realization", "M05C", "F4_user_realization"),
    ("F5_claim_expression", "claim_expression", "M04C", "F5_capability_expression"),
    ("F5_parameter", "parameter", "M03B", "F5_capability_expression"),
)
_SEMANTIC_GROUPS = frozenset({"purchase_reason", "claim_value", "user_realization"})
_RELEVANT_REVIEW_MODULES = frozenset({"m03b", "m04c", "m05c", "m12c", "m12d"})


class ValueSubstitutionEvaluationError(RuntimeError):
    """Raised when G14, G15, and G16 scopes do not align."""


class ValueSubstitutionEvidenceEvaluator:
    """Build evidence-only value substitution assessments from locked facts."""

    def evaluate(
        self,
        pair_bundle: PairFeatureBundle,
        purchase_pool_bundle: PurchasePoolSemanticBundle,
        config: ValueSubstitutionConfig,
    ) -> ValueSubstitutionEvidenceBundle:
        self._assert_inputs(pair_bundle, purchase_pool_bundle, config)
        pool_by_sku = {
            row.candidate.sku_code: row for row in purchase_pool_bundle.pairs
        }
        pairs = [
            self._evaluate_pair(pair, pool_by_sku[pair.candidate.sku_code], config)
            for pair in pair_bundle.pairs
        ]
        input_fingerprint = stable_hash(
            {
                "pair_feature_result_hash": pair_bundle.result_hash,
                "purchase_pool_result_hash": purchase_pool_bundle.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_value_substitution_input_v1",
        )
        return ValueSubstitutionEvidenceBundle(
            project_id=pair_bundle.project_id,
            category_code=pair_bundle.category_code,
            product_category=pair_bundle.product_category,
            release_scope_key=pair_bundle.release_scope_key,
            target=pair_bundle.target,
            candidate_count=len(pairs),
            pairs=pairs,
            config=config,
            pair_feature_result_hash=pair_bundle.result_hash,
            purchase_pool_result_hash=purchase_pool_bundle.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "input_fingerprint": input_fingerprint,
                    "pair_hashes": {
                        row.candidate.sku_code: row.result_hash for row in pairs
                    },
                },
                version="competitor_profile_value_substitution_result_v1",
            ),
        )

    @staticmethod
    def _assert_inputs(
        pair_bundle: PairFeatureBundle,
        pool_bundle: PurchasePoolSemanticBundle,
        config: ValueSubstitutionConfig,
    ) -> None:
        if not (
            pair_bundle.project_id == pool_bundle.project_id
            and pair_bundle.category_code == pool_bundle.category_code
            and pair_bundle.product_category == pool_bundle.product_category
            and pair_bundle.release_scope_key == pool_bundle.release_scope_key
            and pair_bundle.target == pool_bundle.target
        ):
            raise ValueSubstitutionEvaluationError(
                "pair feature and purchase pool scopes must match"
            )
        if config.product_category != pair_bundle.product_category:
            raise ValueSubstitutionEvaluationError(
                "value substitution config category must match inputs"
            )
        if pool_bundle.pair_feature_result_hash != pair_bundle.result_hash:
            raise ValueSubstitutionEvaluationError(
                "purchase pool must consume the supplied pair feature result"
            )
        pair_codes = [row.candidate.sku_code for row in pair_bundle.pairs]
        pool_codes = [row.candidate.sku_code for row in pool_bundle.pairs]
        if pair_codes != pool_codes:
            raise ValueSubstitutionEvaluationError(
                "pair feature and purchase pool candidates must match exactly"
            )

    def _evaluate_pair(
        self,
        pair: PairFeatureRecord,
        pool: PurchasePoolSemanticPairAssessment,
        config: ValueSubstitutionConfig,
    ) -> ValueSubstitutionEvidencePair:
        feature_index = {
            (row.feature_group, row.feature_code): row for row in pair.aligned_features
        }
        reason_codes = sorted(
            code for group, code in feature_index if group == "purchase_reason"
        )
        reason_assessments = [
            _reason_assessment(feature_index[("purchase_reason", code)], config)
            for code in reason_codes
        ]
        semantic_codes = sorted(
            {code for group, code in feature_index if group in _SEMANTIC_GROUPS}
        )
        value_assessments = [
            _value_assessment(code, pair, feature_index, config)
            for code in semantic_codes
        ]

        conflict_codes = sorted(
            row.value_code
            for row in value_assessments
            if row.conflict and row.classification == "discriminative"
        )
        shared_discriminative = sorted(
            row.value_code
            for row in value_assessments
            if row.positive_overlap and row.classification == "discriminative"
        )
        strong_codes = sorted(
            row.value_code
            for row in value_assessments
            if row.value_code in shared_discriminative
            and len(row.matched_layer_codes) >= 2
            and len(row.matched_evidence_families) >= 2
            and set(row.matched_evidence_families)
            & {"F1_purchase_reason", "F4_user_realization"}
        )
        target_positive = _side_positive_codes(value_assessments, "target")
        candidate_positive = _side_positive_codes(value_assessments, "candidate")
        target_only = sorted(target_positive - candidate_positive)
        candidate_only = sorted(candidate_positive - target_positive)
        status = _evidence_status(
            conflict_codes=conflict_codes,
            strong_codes=strong_codes,
            shared_discriminative=shared_discriminative,
            target_positive=target_positive,
            candidate_positive=candidate_positive,
            has_semantic_sources=_has_semantic_evidence(pair),
        )
        families = sorted(
            {
                family
                for row in value_assessments
                if row.positive_overlap
                for family in row.matched_evidence_families
            }
        )
        value_research_allowed = status != "unassessable" and bool(value_assessments)
        future_relation_support = status in {
            "strong_overlap",
            "limited_overlap",
        } and bool(shared_discriminative)
        boundary_code, limitations = _business_boundary(
            pool.purchase_pool.level,
            status,
            future_relation_support,
        )
        review_reasons = {
            reason
            for reason in [
                *pair.review_reason_codes,
                *pair.lineage_conflict_reason_codes,
            ]
            if _is_relevant_review_reason(reason)
        }
        if conflict_codes:
            review_reasons.add("discriminative_value_evidence_conflict")
        review_required = bool(review_reasons)
        evidence_refs = _merge_refs(
            *(row.evidence_refs for row in reason_assessments),
            *(row.evidence_refs for row in value_assessments),
        )
        input_fingerprint = stable_hash(
            {
                "pair_feature_result_hash": pair.result_hash,
                "purchase_pool_result_hash": pool.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_value_substitution_pair_input_v1",
        )
        payload = {
            "target_sku_code": pair.target.sku_code,
            "candidate_sku_code": pair.candidate.sku_code,
            "purchase_pool_level": pool.purchase_pool.level,
            "reason_hashes": [row.result_hash for row in reason_assessments],
            "value_hashes": [row.result_hash for row in value_assessments],
            "evidence_status": status,
            "shared_discriminative_value_codes": shared_discriminative,
            "target_only_positive_value_codes": target_only,
            "candidate_only_positive_value_codes": candidate_only,
            "independent_evidence_families": families,
            "value_research_allowed": value_research_allowed,
            "future_relation_support_possible": future_relation_support,
            "business_boundary_code": boundary_code,
            "review_required": review_required,
            "review_reason_codes": sorted(review_reasons),
            "limitations": limitations,
            "pair_feature_result_hash": pair.result_hash,
            "purchase_pool_result_hash": pool.result_hash,
            "config_version": config.config_version,
            "input_fingerprint": input_fingerprint,
        }
        return ValueSubstitutionEvidencePair(
            target=pair.target,
            candidate=pair.candidate,
            purchase_pool_level=pool.purchase_pool.level,
            purchase_reason_assessments=reason_assessments,
            value_assessments=value_assessments,
            evidence_status=status,
            shared_discriminative_value_codes=shared_discriminative,
            target_only_positive_value_codes=target_only,
            candidate_only_positive_value_codes=candidate_only,
            independent_evidence_families=families,
            value_research_allowed=value_research_allowed,
            future_relation_support_possible=future_relation_support,
            business_boundary_code=boundary_code,
            review_required=review_required,
            review_reason_codes=sorted(review_reasons),
            limitations=limitations,
            evidence_refs=evidence_refs,
            pair_feature_result_hash=pair.result_hash,
            purchase_pool_result_hash=pool.result_hash,
            config_version=config.config_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                payload,
                version="competitor_profile_value_substitution_pair_result_v1",
            ),
        )


def _reason_assessment(
    feature: PairAlignedFeature,
    config: ValueSubstitutionConfig,
) -> PurchaseReasonAssessment:
    target_strength = _m12d_strength(feature.target_values, config)
    candidate_strength = _m12d_strength(feature.candidate_values, config)
    comparison, positive = _reason_comparison(target_strength, candidate_strength)
    classification, classification_reason, coverage = _classify_code(
        feature.feature_code,
        config,
    )
    refs = _merge_refs(feature.target_evidence_refs, feature.candidate_evidence_refs)
    lineage = _lineage_keys(refs)
    payload = {
        "reason_code": feature.feature_code,
        "target_roles": feature.target_values,
        "candidate_roles": feature.candidate_values,
        "target_strength": target_strength,
        "candidate_strength": candidate_strength,
        "comparison_status": comparison,
        "classification": classification,
        "classification_reason_code": classification_reason,
        "coverage_ratio": str(coverage) if coverage is not None else None,
        "positive_overlap": positive,
        "evidence_refs": [_ref_payload(ref) for ref in refs],
        "independent_lineage_keys": lineage,
    }
    return PurchaseReasonAssessment(
        reason_code=feature.feature_code,
        target_roles=feature.target_values,
        candidate_roles=feature.candidate_values,
        target_strength=target_strength,
        candidate_strength=candidate_strength,
        comparison_status=comparison,
        classification=classification,
        classification_reason_code=classification_reason,
        coverage_ratio=coverage,
        positive_overlap=positive,
        evidence_refs=refs,
        independent_lineage_keys=lineage,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_purchase_reason_assessment_v1",
        ),
    )


def _value_assessment(
    code: str,
    pair: PairFeatureRecord,
    feature_index: Mapping[tuple[str, str], PairAlignedFeature],
    config: ValueSubstitutionConfig,
) -> ValueCodeAssessment:
    layers = [
        _value_layer(
            code=code,
            pair=pair,
            feature=feature_index.get((feature_group, code)),
            layer_code=layer_code,
            module_code=module_code,
            family=family,
            config=config,
        )
        for layer_code, feature_group, module_code, family in _LAYER_META
    ]
    classification, classification_reason, coverage = _classify_code(code, config)
    comparable = [
        row
        for row in layers
        if row.target_status in {"positive", "supporting"}
        and row.candidate_status in {"positive", "supporting"}
        and row.comparison_status not in {"conflict", "unknown"}
    ]
    matched_layers = sorted(row.layer_code for row in comparable)
    families = _independent_families(comparable)
    positive_overlap = any(
        row.layer_code
        in {"F1_purchase_reason", "F4_claim_value", "F4_user_realization"}
        for row in comparable
    )
    conflict = any(row.comparison_status == "conflict" for row in layers)
    refs = _merge_refs(*(row.evidence_refs for row in layers))
    payload = {
        "value_code": code,
        "classification": classification,
        "classification_reason_code": classification_reason,
        "coverage_ratio": str(coverage) if coverage is not None else None,
        "layer_hashes": [row.result_hash for row in layers],
        "matched_layer_codes": matched_layers,
        "matched_evidence_families": families,
        "positive_overlap": positive_overlap,
        "conflict": conflict,
    }
    return ValueCodeAssessment(
        value_code=code,
        classification=classification,
        classification_reason_code=classification_reason,
        coverage_ratio=coverage,
        layers=layers,
        matched_layer_codes=matched_layers,
        matched_evidence_families=families,
        positive_overlap=positive_overlap,
        conflict=conflict,
        evidence_refs=refs,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_value_code_assessment_v1",
        ),
    )


def _value_layer(
    *,
    code: str,
    pair: PairFeatureRecord,
    feature: PairAlignedFeature | None,
    layer_code: str,
    module_code: str,
    family: str,
    config: ValueSubstitutionConfig,
) -> ValueLayerAssessment:
    target_values = feature.target_values if feature else []
    candidate_values = feature.candidate_values if feature else []
    target_known, candidate_known = _module_side_known(pair, module_code)
    target_status = _layer_side_status(
        layer_code,
        target_values,
        target_known,
        config,
    )
    candidate_status = _layer_side_status(
        layer_code,
        candidate_values,
        candidate_known,
        config,
    )
    comparison = _layer_comparison(
        target_status,
        candidate_status,
        target_values,
        candidate_values,
    )
    refs = _merge_refs(
        feature.target_evidence_refs if feature else [],
        feature.candidate_evidence_refs if feature else [],
    )
    lineage = _lineage_keys(refs)
    payload = {
        "value_code": code,
        "layer_code": layer_code,
        "target_values": target_values,
        "candidate_values": candidate_values,
        "target_status": target_status,
        "candidate_status": candidate_status,
        "comparison_status": comparison,
        "evidence_family": family,
        "independent_lineage_keys": lineage,
        "evidence_refs": [_ref_payload(ref) for ref in refs],
    }
    return ValueLayerAssessment(
        value_code=code,
        layer_code=layer_code,
        target_values=target_values,
        candidate_values=candidate_values,
        target_status=target_status,
        candidate_status=candidate_status,
        comparison_status=comparison,
        evidence_family=family,
        independent_lineage_keys=lineage,
        evidence_refs=refs,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_value_layer_assessment_v1",
        ),
    )


def _m12d_strength(values: Sequence[str], config: ValueSubstitutionConfig) -> str:
    if not values:
        return "absent"
    groups = {
        "strong": set(config.m12d_strong_roles),
        "supporting": set(config.m12d_supporting_roles),
        "weak": set(config.m12d_weak_roles),
        "risk": set(config.m12d_risk_roles),
    }
    matched = {name for name, roles in groups.items() if set(values) & roles}
    if "risk" in matched and matched & {"strong", "supporting"}:
        return "conflict"
    for strength in ("risk", "strong", "supporting", "weak"):
        if strength in matched:
            return strength
    return "unknown"


def _reason_comparison(target: str, candidate: str) -> tuple[str, bool]:
    if (
        "conflict" in {target, candidate}
        or (target == "risk" and candidate in {"strong", "supporting"})
        or (candidate == "risk" and target in {"strong", "supporting"})
    ):
        return "conflict", False
    if target == "strong" and candidate == "strong":
        return "shared_strong", True
    if target in {"strong", "supporting"} and candidate in {
        "strong",
        "supporting",
    }:
        return "shared_limited", True
    if candidate == "absent":
        return "target_only", False
    if target == "absent":
        return "candidate_only", False
    return "different_role", False


def _layer_side_status(
    layer_code: str,
    values: Sequence[str],
    module_known: bool,
    config: ValueSubstitutionConfig,
) -> str:
    if not values:
        return "absent" if module_known else "unknown"
    if layer_code == "F1_purchase_reason":
        strength = _m12d_strength(values, config)
        return {
            "strong": "positive",
            "supporting": "supporting",
            "weak": "weak",
            "risk": "risk",
            "conflict": "conflict",
            "unknown": "unknown",
        }[strength]
    if layer_code == "F4_claim_value":
        roles = {
            value.removeprefix("role:") for value in values if value.startswith("role:")
        }
        positive = roles & set(config.m12c_positive_roles)
        risk = roles & set(config.m12c_risk_roles)
        if positive and risk:
            return "conflict"
        if risk:
            return "risk"
        if positive:
            return "positive"
        if roles & set(config.m12c_supporting_roles):
            return "supporting"
        if roles & set(config.m12c_opportunity_roles):
            return "weak"
        if roles & set(config.m12c_unknown_roles):
            return "unknown"
        return "supporting" if roles else "unknown"
    if layer_code == "F4_user_realization":
        values_set = set(values)
        positive = values_set & {"user_supported", "observed_value"}
        risk = values_set & {"user_contradicted"}
        if positive and risk:
            return "conflict"
        if risk:
            return "risk"
        if positive:
            return "positive"
        if values_set & {"observed_topic"}:
            return "supporting"
        return "weak" if values_set & {"not_observed"} else "supporting"
    if layer_code == "F5_claim_expression":
        values_set = set(values)
        positive = values_set & {"fact_supported", "supported"}
        risk = values_set & {"unsupported"}
        if positive and risk:
            return "conflict"
        if risk:
            return "risk"
        return "positive" if positive else "supporting"
    return "positive"


def _layer_comparison(
    target_status: str,
    candidate_status: str,
    target_values: Sequence[str],
    candidate_values: Sequence[str],
) -> str:
    if "unknown" in {target_status, candidate_status}:
        return "unknown"
    if (
        "conflict" in {target_status, candidate_status}
        or (target_status == "risk" and candidate_status in {"positive", "supporting"})
        or (candidate_status == "risk" and target_status in {"positive", "supporting"})
    ):
        return "conflict"
    if target_status == "absent" and candidate_status == "absent":
        return "absent_both"
    if candidate_status == "absent":
        return "target_only"
    if target_status == "absent":
        return "candidate_only"
    return "matched" if set(target_values) & set(candidate_values) else "different"


def _classify_code(
    code: str,
    config: ValueSubstitutionConfig,
) -> tuple[str, str, Decimal | None]:
    coverage = config.value_coverage_ratios.get(code)
    if code in config.table_stake_value_codes:
        return "table_stake", "taxonomy_table_stake", coverage
    if code in config.generic_value_codes:
        return "generic", "taxonomy_generic", coverage
    if coverage is not None and coverage >= config.generic_coverage_threshold:
        return "generic", "serving_scope_coverage_generic", coverage
    if code in config.discriminative_value_codes and coverage is not None:
        return (
            "discriminative",
            "taxonomy_specific_and_coverage_below_threshold",
            coverage,
        )
    if code in config.discriminative_value_codes:
        return "supporting", "coverage_unknown_not_discriminative", None
    return "supporting", "taxonomy_unclassified_supporting_only", coverage


def _side_positive_codes(
    assessments: Sequence[ValueCodeAssessment],
    side: str,
) -> set[str]:
    return {
        row.value_code
        for row in assessments
        if any(
            layer.layer_code
            in {"F1_purchase_reason", "F4_claim_value", "F4_user_realization"}
            and getattr(layer, f"{side}_status") in {"positive", "supporting"}
            for layer in row.layers
        )
    }


def _independent_families(
    layers: Sequence[ValueLayerAssessment],
) -> list[str]:
    families: set[str] = set()
    seen_lineage: set[str] = set()
    for layer in layers:
        lineage = set(layer.independent_lineage_keys)
        if lineage and lineage <= seen_lineage:
            continue
        families.add(layer.evidence_family)
        seen_lineage.update(lineage)
    return sorted(families)


def _evidence_status(
    *,
    conflict_codes: Sequence[str],
    strong_codes: Sequence[str],
    shared_discriminative: Sequence[str],
    target_positive: set[str],
    candidate_positive: set[str],
    has_semantic_sources: bool,
) -> str:
    if conflict_codes:
        return "conflict"
    if strong_codes:
        return "strong_overlap"
    if shared_discriminative:
        return "limited_overlap"
    if (
        target_positive
        and candidate_positive
        and not (target_positive & candidate_positive)
    ):
        return "different_route"
    return (
        "limited_overlap"
        if target_positive & candidate_positive
        else ("unassessable" if not has_semantic_sources else "different_route")
    )


def _business_boundary(
    pool_level: str,
    status: str,
    future_relation_support: bool,
) -> tuple[str, list[str]]:
    limitations: set[str] = set()
    if pool_level == "P3":
        limitations.add("purchase_pool_p3_reference_only")
        return "value_research_only_purchase_choice_forbidden", sorted(limitations)
    if pool_level == "unknown":
        limitations.add("purchase_pool_unknown")
        return "purchase_pool_unknown_relation_forbidden", sorted(limitations)
    if status == "conflict":
        limitations.add("value_evidence_conflict_requires_review")
        return "evidence_conflict_relation_pending", sorted(limitations)
    if not future_relation_support:
        limitations.add("insufficient_discriminative_shared_value")
        return "insufficient_value_evidence_relation_pending", sorted(limitations)
    return "evidence_only_formal_relation_pending", []


def _has_semantic_evidence(pair: PairFeatureRecord) -> bool:
    semantic = [
        row for row in pair.aligned_features if row.feature_group in _SEMANTIC_GROUPS
    ]
    return any(row.target_values for row in semantic) and any(
        row.candidate_values for row in semantic
    )


def _module_side_known(
    pair: PairFeatureRecord,
    module_code: str,
) -> tuple[bool, bool]:
    row = next(
        item for item in pair.module_availability if item.module_code == module_code
    )
    return row.target_availability == "present", row.candidate_availability == "present"


def _is_relevant_review_reason(reason: str) -> bool:
    normalized = reason.lower()
    return any(
        f"_{module}_" in normalized or normalized.startswith(f"{module}_")
        for module in _RELEVANT_REVIEW_MODULES
    )


def _lineage_keys(refs: Sequence[EvidenceRef]) -> list[str]:
    keys: set[str] = set()
    for ref in refs:
        if ref.evidence_ids:
            keys.update(f"evidence:{value}" for value in ref.evidence_ids)
        elif ref.raw_row_ids:
            keys.update(f"raw-row:{value}" for value in ref.raw_row_ids)
        elif ref.source_file_ids:
            keys.update(f"source-file:{value}" for value in ref.source_file_ids)
        else:
            keys.add(
                f"derived:{ref.source_batch_id or ref.profile_version}:"
                f"{ref.result_hash}"
            )
    return sorted(keys)


def _merge_refs(*groups: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    unique: dict[tuple[str, str, str, str, str], EvidenceRef] = {}
    for group in groups:
        for ref in group:
            unique[_ref_key(ref)] = ref
    return [unique[key] for key in sorted(unique)]


def _ref_key(ref: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        ref.module_code,
        ref.source_batch_id or "",
        ref.record_type,
        ref.record_id,
        ref.result_hash,
    )


def _ref_payload(ref: EvidenceRef) -> Mapping[str, object]:
    return ref.model_dump(mode="json")


__all__ = [
    "ValueSubstitutionEvaluationError",
    "ValueSubstitutionEvidenceEvaluator",
]
