"""Evaluate seven formal competitor relations and eight business questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairFeatureBundle,
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureAssessment,
    PriceVolumePressureBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticBundle,
    PurchasePoolSemanticPairAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationConfig,
    CompetitorRelationEvaluationBundle,
    CompetitorRelationPairEvaluation,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceFamilyAssessment,
    EvidenceRef,
    GateResult,
    QuestionEligibility,
    RelationAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionEvidenceBundle,
    ValueSubstitutionEvidencePair,
)
from app.services.core3_real_data.hash_utils import stable_hash_json


_RELATION_QUESTIONS = {
    "direct_substitute": [
        "configuration_follow",
        "key_competitor_selection",
        "price_volume_pressure",
        "purchase_choice",
        "value_substitution",
    ],
    "same_budget_alternative": [
        "configuration_follow",
        "key_competitor_selection",
        "price_volume_pressure",
        "purchase_choice",
    ],
    "downtrade_diversion": [
        "configuration_follow",
        "key_competitor_selection",
        "price_ladder_defense",
        "price_volume_pressure",
        "value_substitution",
    ],
    "uptrade_alternative": [
        "configuration_follow",
        "key_competitor_selection",
        "price_ladder_defense",
        "price_volume_pressure",
        "value_substitution",
    ],
    "same_brand_ladder": [
        "key_competitor_selection",
        "price_volume_pressure",
        "same_brand_portfolio_role",
    ],
    "scenario_substitute": [
        "key_competitor_selection",
        "price_volume_pressure",
        "scenario_solution",
    ],
    "same_value_substitute": [
        "configuration_follow",
        "key_competitor_selection",
        "value_substitution",
    ],
}
_FAMILY_ORDER = (
    "F1_purchase_reason",
    "F2_task_value_scene",
    "F3_audience_need",
    "F4_user_realization",
    "F5_capability_expression",
)


class CompetitorRelationEvaluationError(RuntimeError):
    """Raised when upstream result scopes or hash chains do not match."""


@dataclass(frozen=True)
class _RelationDraft:
    code: str
    gates: list[GateResult]
    status: str
    confidence: str
    family_codes: list[str]
    reason_codes: list[str]
    limitations: list[str]
    evidence_refs: list[EvidenceRef]
    business_effect: dict[str, object]


class CompetitorRelationEvaluator:
    """Build formal relation and question contracts without selecting top competitors."""

    def evaluate(
        self,
        pair_bundle: PairFeatureBundle,
        pool_bundle: PurchasePoolSemanticBundle,
        value_bundle: ValueSubstitutionEvidenceBundle,
        pressure_bundle: PriceVolumePressureBundle,
        config: CompetitorRelationConfig,
    ) -> CompetitorRelationEvaluationBundle:
        self._assert_inputs(
            pair_bundle,
            pool_bundle,
            value_bundle,
            pressure_bundle,
            config,
        )
        pool_by_sku = {row.candidate.sku_code: row for row in pool_bundle.pairs}
        value_by_sku = {row.candidate.sku_code: row for row in value_bundle.pairs}
        pressure_by_sku = {row.candidate.sku_code: row for row in pressure_bundle.pairs}
        pairs = [
            self._evaluate_pair(
                pair,
                pool_by_sku[pair.candidate.sku_code],
                value_by_sku[pair.candidate.sku_code],
                pressure_by_sku[pair.candidate.sku_code],
                config,
            )
            for pair in pair_bundle.pairs
        ]
        input_fingerprint = stable_hash_json(
            {
                "pair_feature_result_hash": pair_bundle.result_hash,
                "purchase_pool_result_hash": pool_bundle.result_hash,
                "value_substitution_result_hash": value_bundle.result_hash,
                "price_volume_pressure_result_hash": pressure_bundle.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_relation_evaluation_input_v1",
        )
        return CompetitorRelationEvaluationBundle(
            project_id=pair_bundle.project_id,
            category_code=pair_bundle.category_code,
            product_category=pair_bundle.product_category,
            release_scope_key=pair_bundle.release_scope_key,
            target=pair_bundle.target,
            candidate_count=len(pairs),
            pairs=pairs,
            config=config,
            pair_feature_result_hash=pair_bundle.result_hash,
            purchase_pool_result_hash=pool_bundle.result_hash,
            value_substitution_result_hash=value_bundle.result_hash,
            price_volume_pressure_result_hash=pressure_bundle.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash_json(
                {
                    "input_fingerprint": input_fingerprint,
                    "pair_hashes": {
                        row.candidate.sku_code: row.result_hash for row in pairs
                    },
                },
                version="competitor_profile_relation_evaluation_result_v1",
            ),
        )

    @staticmethod
    def _assert_inputs(
        pair_bundle: PairFeatureBundle,
        pool_bundle: PurchasePoolSemanticBundle,
        value_bundle: ValueSubstitutionEvidenceBundle,
        pressure_bundle: PriceVolumePressureBundle,
        config: CompetitorRelationConfig,
    ) -> None:
        scopes = {
            (
                bundle.project_id,
                bundle.category_code,
                bundle.product_category,
                bundle.release_scope_key,
                bundle.target.sku_code,
            )
            for bundle in (
                pair_bundle,
                pool_bundle,
                value_bundle,
                pressure_bundle,
            )
        }
        if len(scopes) != 1:
            raise CompetitorRelationEvaluationError(
                "pair, pool, value, and pressure scopes must match"
            )
        if config.product_category != pair_bundle.product_category:
            raise CompetitorRelationEvaluationError(
                "relation config category must match inputs"
            )
        if pool_bundle.pair_feature_result_hash != pair_bundle.result_hash:
            raise CompetitorRelationEvaluationError("purchase-pool hash chain mismatch")
        if (
            value_bundle.pair_feature_result_hash != pair_bundle.result_hash
            or value_bundle.purchase_pool_result_hash != pool_bundle.result_hash
        ):
            raise CompetitorRelationEvaluationError(
                "value evidence hash chain mismatch"
            )
        if (
            pressure_bundle.pair_feature_result_hash != pair_bundle.result_hash
            or pressure_bundle.purchase_pool_result_hash != pool_bundle.result_hash
            or pressure_bundle.value_substitution_result_hash
            != value_bundle.result_hash
        ):
            raise CompetitorRelationEvaluationError("pressure hash chain mismatch")
        candidate_lists = {
            tuple(row.candidate.sku_code for row in bundle.pairs)
            for bundle in (
                pair_bundle,
                pool_bundle,
                value_bundle,
                pressure_bundle,
            )
        }
        if len(candidate_lists) != 1:
            raise CompetitorRelationEvaluationError(
                "pair, pool, value, and pressure candidates must match"
            )

    def _evaluate_pair(
        self,
        pair: PairFeatureRecord,
        pool: PurchasePoolSemanticPairAssessment,
        value: ValueSubstitutionEvidencePair,
        pressure: PriceVolumePressureAssessment,
        config: CompetitorRelationConfig,
    ) -> CompetitorRelationPairEvaluation:
        families = _evidence_families(pair, pool, value)
        independent = _independent_formal_families(families)
        review_reasons = set(pool.review_reason_codes)
        review_reasons.update(value.review_reason_codes)
        review_reasons.update(pressure.review_reason_codes)
        if pair.candidate_status == "blocked":
            review_reasons.add("upstream_candidate_blocked")
        upstream_review = bool(review_reasons)
        if pair.relation_evaluation_member:
            drafts = _relation_drafts(
                pair,
                pool,
                value,
                pressure,
                families,
                independent,
                config,
                upstream_review,
            )
            primary = _primary_relation(drafts, config)
            candidate_status = _candidate_status(
                pair,
                drafts,
                upstream_review=upstream_review,
            )
        else:
            drafts = _held_relation_drafts(pair)
            primary = None
            candidate_status = pair.candidate_status
        relation_assessments = [
            _relation_model(draft, is_primary=draft.code == primary)
            for draft in sorted(drafts, key=lambda row: row.code)
        ]
        pair_review_required = upstream_review or candidate_status in {
            "review_required",
            "blocked",
        }
        if candidate_status == "review_required" and not upstream_review:
            review_reasons.update(
                f"{draft.code}_insufficient_independent_evidence"
                for draft in drafts
                if draft.status == "review_required"
            )
        overall_confidence = _overall_confidence(drafts, candidate_status)
        questions = _question_eligibility(
            drafts=drafts,
            candidate_status=candidate_status,
            confidence=overall_confidence,
            pool=pool,
            value=value,
            pressure=pressure,
            families=families,
            pair=pair,
        )
        evidence_refs = _merge_refs(
            *(row.evidence_refs for row in families),
            *(draft.evidence_refs for draft in drafts),
        )
        limitations = sorted(
            {limitation for draft in drafts for limitation in draft.limitations}
        )
        input_fingerprint = stable_hash_json(
            {
                "pair_feature_result_hash": pair.result_hash,
                "purchase_pool_result_hash": pool.result_hash,
                "value_substitution_result_hash": value.result_hash,
                "price_volume_pressure_result_hash": pressure.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_relation_evaluation_pair_input_v1",
        )
        payload = {
            "target_sku_code": pair.target.sku_code,
            "candidate_sku_code": pair.candidate.sku_code,
            "candidate_status": candidate_status,
            "competitor_member": candidate_status in {"eligible", "limited"},
            "reference_member": pair.reference_member,
            "primary_relation_code": primary,
            "relation_hashes": [row.result_hash for row in relation_assessments],
            "family_payloads": [row.model_dump(mode="json") for row in families],
            "question_hashes": [row.result_hash for row in questions],
            "overall_confidence_level": overall_confidence,
            "review_required": pair_review_required,
            "review_reason_codes": sorted(review_reasons),
            "limitations": limitations,
            "pair_feature_result_hash": pair.result_hash,
            "purchase_pool_result_hash": pool.result_hash,
            "value_substitution_result_hash": value.result_hash,
            "price_volume_pressure_result_hash": pressure.result_hash,
            "config_version": config.config_version,
            "input_fingerprint": input_fingerprint,
        }
        return CompetitorRelationPairEvaluation(
            target=pair.target,
            candidate=pair.candidate,
            candidate_status=candidate_status,
            competitor_member=candidate_status in {"eligible", "limited"},
            reference_member=pair.reference_member,
            primary_relation_code=primary,
            relation_assessments=relation_assessments,
            evidence_family_assessments=families,
            question_eligibility=questions,
            overall_confidence_level=overall_confidence,
            review_required=pair_review_required,
            review_reason_codes=sorted(review_reasons),
            limitations=limitations,
            evidence_refs=evidence_refs,
            pair_feature_result_hash=pair.result_hash,
            purchase_pool_result_hash=pool.result_hash,
            value_substitution_result_hash=value.result_hash,
            price_volume_pressure_result_hash=pressure.result_hash,
            config_version=config.config_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash_json(
                payload,
                version="competitor_profile_relation_evaluation_pair_result_v1",
            ),
        )


def _evidence_families(
    pair: PairFeatureRecord,
    pool: PurchasePoolSemanticPairAssessment,
    value: ValueSubstitutionEvidencePair,
) -> list[EvidenceFamilyAssessment]:
    rows = [
        _family_f1(value),
        _family_f2(pair, pool),
        _family_f3(pair),
        _family_f4(value),
        _family_f5(pair, value),
    ]
    return sorted(rows, key=lambda row: _enum_value(row.family))


def _family_f1(value: ValueSubstitutionEvidencePair) -> EvidenceFamilyAssessment:
    reasons = value.purchase_reason_assessments
    conflict = any(row.comparison_status == "conflict" for row in reasons)
    matched = sorted(row.reason_code for row in reasons if row.positive_overlap)
    discriminative = sorted(
        row.reason_code
        for row in reasons
        if row.positive_overlap and row.classification == "discriminative"
    )
    refs = _merge_refs(*(row.evidence_refs for row in reasons))
    if conflict:
        status, confidence = "conflict", "unknown"
    elif discriminative:
        status, confidence = "discriminative", "high"
    elif matched or reasons:
        status, confidence = "supporting", "medium"
    else:
        status, confidence = "missing", "unknown"
    return EvidenceFamilyAssessment(
        family="F1_purchase_reason",
        status=status,
        matched_codes=[] if status == "missing" else discriminative or matched,
        direction=_reason_direction(reasons),
        independent_lineage_keys=[] if status == "missing" else _lineage_keys(refs),
        evidence_refs=refs,
        confidence_level=confidence,
    )


def _family_f2(
    pair: PairFeatureRecord,
    pool: PurchasePoolSemanticPairAssessment,
) -> EvidenceFamilyAssessment:
    matched = sorted(
        set(pool.shared_primary_task_codes)
        | set(pool.battlefield_overlap.shared_discriminative_codes)
    )
    refs = _refs_for_modules(pair, "M09C", "M11C", "M11D")
    if pool.purchase_pool.level == "unknown" and not matched:
        status, confidence = "missing", "unknown"
    elif matched:
        status, confidence = "discriminative", "high"
    else:
        status, confidence = "supporting", "low"
    return EvidenceFamilyAssessment(
        family="F2_task_value_scene",
        status=status,
        matched_codes=[] if status == "missing" else matched,
        direction="parity" if matched else "unknown",
        independent_lineage_keys=[] if status == "missing" else _lineage_keys(refs),
        evidence_refs=refs,
        confidence_level=confidence,
    )


def _family_f3(pair: PairFeatureRecord) -> EvidenceFamilyAssessment:
    features = [row for row in pair.aligned_features if row.feature_group == "audience"]
    matched = sorted(
        row.feature_code
        for row in features
        if row.target_values and row.candidate_values and row.common_values
    )
    refs = _merge_refs(
        *(row.target_evidence_refs for row in features),
        *(row.candidate_evidence_refs for row in features),
    )
    known = _module_pair_known(pair, "M10C")
    status = "discriminative" if matched else ("supporting" if known else "missing")
    return EvidenceFamilyAssessment(
        family="F3_audience_need",
        status=status,
        matched_codes=[] if status == "missing" else matched,
        direction="parity" if matched else "unknown",
        independent_lineage_keys=[] if status == "missing" else _lineage_keys(refs),
        evidence_refs=refs,
        confidence_level="medium" if matched else ("low" if known else "unknown"),
    )


def _family_f4(value: ValueSubstitutionEvidencePair) -> EvidenceFamilyAssessment:
    relevant = [
        row
        for row in value.value_assessments
        if any(layer.layer_code.startswith("F4_") for layer in row.layers)
    ]
    matched = sorted(
        row.value_code
        for row in relevant
        if row.positive_overlap and row.classification == "discriminative"
    )
    conflict = any(
        row.conflict and row.classification == "discriminative" for row in relevant
    )
    refs = _merge_refs(*(row.evidence_refs for row in relevant))
    if conflict:
        status, confidence = "conflict", "unknown"
    elif matched:
        status, confidence = "discriminative", "high"
    elif relevant and value.evidence_status != "unassessable":
        status, confidence = "supporting", "medium"
    else:
        status, confidence = "missing", "unknown"
    return EvidenceFamilyAssessment(
        family="F4_user_realization",
        status=status,
        matched_codes=[] if status == "missing" else matched,
        direction=_value_direction(value),
        independent_lineage_keys=[] if status == "missing" else _lineage_keys(refs),
        evidence_refs=refs,
        confidence_level=confidence,
    )


def _family_f5(
    pair: PairFeatureRecord,
    value: ValueSubstitutionEvidencePair,
) -> EvidenceFamilyAssessment:
    features = [
        row
        for row in pair.aligned_features
        if row.feature_group in {"parameter", "claim_expression"}
    ]
    matched = sorted(
        row.feature_code
        for row in features
        if row.target_values and row.candidate_values and row.common_values
    )
    refs = _merge_refs(
        *(row.target_evidence_refs for row in features),
        *(row.candidate_evidence_refs for row in features),
    )
    known = _module_pair_known(pair, "M03B") or _module_pair_known(pair, "M04C")
    status = "supporting" if known else "missing"
    return EvidenceFamilyAssessment(
        family="F5_capability_expression",
        status=status,
        matched_codes=[] if status == "missing" else matched,
        direction="different_route" if _has_f5_difference(value) else "parity",
        independent_lineage_keys=[] if status == "missing" else _lineage_keys(refs),
        evidence_refs=refs,
        confidence_level="medium" if known else "unknown",
    )


def _independent_formal_families(
    rows: Sequence[EvidenceFamilyAssessment],
) -> list[str]:
    available: list[str] = []
    seen_lineage: set[str] = set()
    for family_code in _FAMILY_ORDER[:-1]:
        row = next(item for item in rows if _enum_value(item.family) == family_code)
        if _enum_value(row.status) != "discriminative":
            continue
        lineage = set(row.independent_lineage_keys)
        if lineage and lineage <= seen_lineage:
            continue
        available.append(family_code)
        seen_lineage.update(lineage)
    return available


def _relation_drafts(
    pair: PairFeatureRecord,
    pool: PurchasePoolSemanticPairAssessment,
    value: ValueSubstitutionEvidencePair,
    pressure: PriceVolumePressureAssessment,
    families: Sequence[EvidenceFamilyAssessment],
    independent: Sequence[str],
    config: CompetitorRelationConfig,
    upstream_review: bool,
) -> list[_RelationDraft]:
    family_set = set(independent)
    has_f1_f4 = bool(family_set & {"F1_purchase_reason", "F4_user_realization"})
    market_known = pressure.market_comparability_status in {"comparable", "limited"}
    market_pass = market_known and pressure.pressure_direction != "unassessable"
    weak_reason = any(
        row.target_strength == "weak" or row.candidate_strength == "weak"
        for row in value.purchase_reason_assessments
    )
    shared_audience = _shared_feature_codes(pair, "audience")
    f5_threshold_known, f5_threshold_pass = _threshold_capability(pair, config)
    no_hard_conflict = not (
        pool.review_required
        or value.evidence_status == "conflict"
        or pressure.review_required
    )
    shared_primary_task = bool(pool.shared_primary_task_codes)
    route_distinct = (
        pool.battlefield_overlap.value_route_status == "different"
        or value.evidence_status == "different_route"
        or _has_value_path_difference(value)
    )
    both_value_routes = bool(
        _positive_side_codes(value, "target")
        and _positive_side_codes(value, "candidate")
    )
    price_gap_pct = pressure.price_gap_pct
    weekly_ratio = pressure.weekly_volume_ratio
    candidate_stronger = _candidate_stronger_families(value)
    candidate_stronger_set = set(candidate_stronger)
    candidate_unique_discriminative = any(
        row.value_code in value.candidate_only_positive_value_codes
        and row.classification == "discriminative"
        for row in value.value_assessments
    )
    same_brand_known = bool(pair.target.brand_name and pair.candidate.brand_name)
    same_brand = same_brand_known and _brand(pair.target.brand_name) == _brand(
        pair.candidate.brand_name
    )
    same_brand_entry = "same_brand_ladder" in pair.recall_sources
    form_gate = _pool_gate(pool, "category_product_form_compatibility")
    size_gate = _pool_gate(pool, "size_capacity_task_substitutability")
    budget_gate = _pool_gate(pool, "budget_reachability")

    direct_gates = [
        _gate(
            "purchase_pool_p0",
            pool.purchase_pool.level != "unknown",
            pool.purchase_pool.level == "P0",
            "purchase_pool_p0_required",
            pool.evidence_refs,
        ),
        _gate(
            "two_independent_families",
            value.evidence_status != "unassessable",
            len(family_set) >= 2,
            "at_least_two_independent_families",
            _family_refs(families),
        ),
        _gate(
            "f1_or_f4",
            value.evidence_status != "unassessable",
            has_f1_f4,
            "f1_or_f4_required",
            _family_refs(families),
        ),
        _gate(
            "shared_discriminative_value",
            value.evidence_status != "unassessable",
            bool(value.shared_discriminative_value_codes),
            "shared_discriminative_value_required",
            value.evidence_refs,
        ),
        _gate(
            "market_comparable",
            pressure.market_comparability_status != "unknown",
            market_pass,
            "m07_market_comparability_required",
            pressure.evidence_refs,
        ),
        _gate(
            "no_hard_conflict",
            True,
            no_hard_conflict,
            "no_form_task_reason_conflict",
            _merge_refs(pool.evidence_refs, value.evidence_refs),
        ),
    ]
    same_budget_gates = [
        _gate(
            "same_budget",
            pressure.budget_band != "unknown",
            pressure.budget_band == "same",
            "same_budget_required",
            pressure.evidence_refs,
        ),
        _gate(
            "purchase_pool_p0_p1",
            pool.purchase_pool.level != "unknown",
            pool.purchase_pool.level in {"P0", "P1"},
            "purchase_pool_p0_or_p1_required",
            pool.evidence_refs,
        ),
        _gate(
            "shared_primary_task",
            _module_pair_known(pair, "M09C"),
            shared_primary_task,
            "shared_primary_task_required",
            _refs_for_modules(pair, "M09C"),
        ),
        _gate(
            "both_value_routes",
            value.evidence_status != "unassessable",
            both_value_routes,
            "both_value_routes_required",
            value.evidence_refs,
        ),
        _gate(
            "route_or_path_difference",
            value.evidence_status != "unassessable",
            route_distinct,
            "different_value_route_or_path_required",
            value.evidence_refs,
        ),
        _gate(
            "market_comparable",
            pressure.market_comparability_status != "unknown",
            market_pass,
            "m07_market_comparability_required",
            pressure.evidence_refs,
        ),
    ]
    downtrade_gates = [
        _gate(
            "candidate_price_lower_8pct",
            price_gap_pct is not None,
            price_gap_pct is not None
            and price_gap_pct <= -config.downtrade_min_price_gap_pct,
            "candidate_price_at_least_8pct_lower",
            pressure.evidence_refs,
        ),
        _gate(
            "purchase_or_task_comparable",
            pool.purchase_pool.level != "unknown" or _module_pair_known(pair, "M09C"),
            pool.purchase_pool.level in {"P0", "P1"} or shared_primary_task,
            "p0_p1_or_shared_primary_task",
            pool.evidence_refs,
        ),
        _gate(
            "base_value_family",
            value.evidence_status != "unassessable" or bool(family_set),
            bool(
                family_set
                & {"F1_purchase_reason", "F2_task_value_scene", "F4_user_realization"}
            ),
            "f1_f2_or_f4_base_value_required",
            _family_refs(families),
        ),
        _gate(
            "threshold_capability",
            f5_threshold_known,
            f5_threshold_pass,
            "known_f5_threshold_capability_required",
            _refs_for_modules(pair, "M03B"),
        ),
        _gate(
            "no_task_or_capability_block",
            True,
            no_hard_conflict and form_gate.passed is True and size_gate.passed is True,
            "no_known_task_or_capability_block",
            pool.evidence_refs,
        ),
        _gate(
            "market_volume_not_lower",
            weekly_ratio is not None,
            weekly_ratio is not None and weekly_ratio >= 1,
            "candidate_weekly_volume_not_lower",
            pressure.evidence_refs,
        ),
    ]
    uptrade_gates = [
        _gate(
            "candidate_price_higher_8pct",
            price_gap_pct is not None,
            price_gap_pct is not None
            and price_gap_pct >= config.uptrade_min_price_gap_pct,
            "candidate_price_at_least_8pct_higher",
            pressure.evidence_refs,
        ),
        _gate(
            "purchase_task_audience_comparable",
            pool.purchase_pool.level != "unknown"
            or (_module_pair_known(pair, "M09C") and _module_pair_known(pair, "M10C")),
            pool.purchase_pool.level in {"P0", "P1"}
            or (shared_primary_task and bool(shared_audience)),
            "p0_p1_or_shared_task_audience",
            pool.evidence_refs,
        ),
        _gate(
            "two_candidate_stronger_families",
            value.evidence_status != "unassessable",
            len(candidate_stronger_set) >= 2,
            "candidate_stronger_in_two_families",
            value.evidence_refs,
        ),
        _gate(
            "candidate_stronger_f1_or_f4",
            value.evidence_status != "unassessable",
            bool(
                candidate_stronger_set & {"F1_purchase_reason", "F4_user_realization"}
            ),
            "candidate_stronger_f1_or_f4",
            value.evidence_refs,
        ),
        _gate(
            "non_generic_stronger_value",
            value.evidence_status != "unassessable",
            candidate_unique_discriminative,
            "non_generic_candidate_value_required",
            value.evidence_refs,
        ),
        _gate(
            "valid_market_acceptance",
            pressure.market_comparability_status != "unknown",
            market_known
            and pressure.candidate_avg_weekly_volume is not None
            and pressure.candidate_avg_weekly_volume > 0,
            "valid_candidate_market_acceptance",
            pressure.evidence_refs,
        ),
    ]
    same_brand_gates = [
        _gate(
            "same_normalized_brand",
            same_brand_known,
            same_brand,
            "same_normalized_brand_required",
            pair.evidence_refs,
        ),
        _gate(
            "compatible_product_form",
            form_gate.known,
            form_gate.passed,
            "compatible_product_form_required",
            form_gate.evidence_refs,
        ),
        _gate(
            "adjacent_ladder_entry",
            True,
            same_brand_entry and pressure.budget_band in {"same", "adjacent"},
            "same_brand_adjacent_ladder_entry_required",
            pair.evidence_refs,
        ),
        _gate(
            "market_position_known",
            pressure.market_comparability_status != "unknown",
            market_known,
            "m07_market_position_required",
            pressure.evidence_refs,
        ),
        _gate(
            "portfolio_value_family",
            value.evidence_status != "unassessable" or bool(family_set),
            bool(family_set),
            "f1_to_f4_portfolio_value_required",
            _family_refs(families),
        ),
    ]
    scenario_gates = [
        _gate(
            "purchase_pool_p2",
            pool.purchase_pool.level != "unknown",
            pool.purchase_pool.level == "P2",
            "purchase_pool_p2_required",
            pool.evidence_refs,
        ),
        _gate(
            "f2_required",
            pool.purchase_pool.level != "unknown",
            "F2_task_value_scene" in family_set,
            "f2_task_value_scene_required",
            _family_refs(families),
        ),
        _gate(
            "second_semantic_family",
            value.evidence_status != "unassessable" or bool(shared_audience),
            bool(
                family_set
                & {"F1_purchase_reason", "F3_audience_need", "F4_user_realization"}
            ),
            "f1_f3_or_f4_required",
            _family_refs(families),
        ),
        _gate(
            "budget_or_scenario_reachable",
            budget_gate.known,
            budget_gate.passed,
            "budget_or_scenario_reachability_required",
            budget_gate.evidence_refs,
        ),
        _gate(
            "no_form_size_block",
            True,
            no_hard_conflict and form_gate.passed is True and size_gate.passed is True,
            "no_form_installation_capacity_block",
            pool.evidence_refs,
        ),
    ]
    same_value_gates = [
        _gate(
            "shared_discriminative_value",
            value.evidence_status != "unassessable",
            bool(value.shared_discriminative_value_codes),
            "shared_discriminative_value_required",
            value.evidence_refs,
        ),
        _gate(
            "two_independent_families",
            value.evidence_status != "unassessable",
            len(family_set) >= 2,
            "at_least_two_independent_families",
            _family_refs(families),
        ),
        _gate(
            "f1_or_f4",
            value.evidence_status != "unassessable",
            has_f1_f4,
            "f1_or_f4_required",
            _family_refs(families),
        ),
        _gate(
            "two_comparable_layers",
            value.evidence_status != "unassessable",
            value.evidence_status == "strong_overlap",
            "two_comparable_value_layers_required",
            value.evidence_refs,
        ),
        _gate(
            "market_comparable",
            pressure.market_comparability_status != "unknown",
            market_pass,
            "m07_market_comparability_required",
            pressure.evidence_refs,
        ),
    ]

    drafts = [
        _draft(
            "direct_substitute",
            direct_gates,
            family_set,
            upstream_review,
            limited=weak_reason or pressure.market_comparability_status == "limited",
            effect={"effect_code": "purchase_choice_overlap"},
        ),
        _draft(
            "same_budget_alternative",
            same_budget_gates,
            family_set,
            upstream_review,
            limited=False,
            effect={"effect_code": "same_budget_route_competition"},
        ),
        _draft(
            "downtrade_diversion",
            downtrade_gates,
            family_set,
            upstream_review,
            limited=False,
            effect={
                "effect_code": "observed_downtrade_market_pressure",
                "strong_pressure": bool(
                    price_gap_pct is not None
                    and price_gap_pct <= -config.strong_price_gap_pct
                    and weekly_ratio is not None
                    and weekly_ratio >= config.strong_volume_ratio
                ),
                "causal_claim": False,
            },
        ),
        _draft(
            "uptrade_alternative",
            uptrade_gates,
            candidate_stronger_set,
            upstream_review,
            limited=False,
            effect={
                "effect_code": "observed_uptrade_market_acceptance",
                "causal_claim": False,
            },
        ),
        _draft(
            "same_brand_ladder",
            same_brand_gates,
            family_set,
            upstream_review,
            limited=False,
            effect={"effect_code": "same_brand_portfolio_overlap"},
        ),
        _draft(
            "scenario_substitute",
            scenario_gates,
            family_set,
            upstream_review,
            limited=False,
            effect={"effect_code": "same_scenario_solution_switch"},
        ),
        _draft(
            "same_value_substitute",
            same_value_gates,
            family_set,
            upstream_review,
            limited=pool.purchase_pool.level == "P3",
            effect={
                "effect_code": "same_value_research"
                if pool.purchase_pool.level == "P3"
                else "same_value_competition",
                "purchase_choice_allowed": pool.purchase_pool.level in {"P0", "P1"},
            },
        ),
    ]
    return drafts


def _draft(
    code: str,
    gates: Sequence[GateResult],
    families: Iterable[str],
    upstream_review: bool,
    *,
    limited: bool,
    effect: dict[str, object],
) -> _RelationDraft:
    family_codes = sorted(set(families))
    if upstream_review:
        status = "review_required"
    elif any(not gate.known for gate in gates):
        status = "unassessable"
    elif any(gate.passed is False for gate in gates):
        status = "failed"
    elif len(family_codes) < 2:
        status = "review_required"
    else:
        status = "limited" if limited else "passed"
    reason_codes = sorted(
        {gate.reason_code for gate in gates if not gate.known or gate.passed is False}
    )
    if status == "review_required":
        reason_codes.append(
            "upstream_evidence_requires_review"
            if upstream_review
            else "insufficient_independent_evidence_for_auto_use"
        )
    reason_codes = sorted(set(reason_codes))
    limitations = []
    if limited:
        limitations.append("relation_evidence_limited")
    if status == "review_required" and not upstream_review:
        limitations.append("relation_requires_manual_evidence_review")
    confidence = (
        "high"
        if status == "passed"
        and len(family_codes) >= 3
        and bool(set(family_codes) & {"F1_purchase_reason", "F4_user_realization"})
        else "medium"
        if status in {"passed", "limited"}
        else "low"
        if status == "failed" or (status == "review_required" and not upstream_review)
        else "unknown"
    )
    return _RelationDraft(
        code=code,
        gates=list(gates),
        status=status,
        confidence=confidence,
        family_codes=family_codes,
        reason_codes=reason_codes,
        limitations=limitations,
        evidence_refs=_merge_refs(*(gate.evidence_refs for gate in gates)),
        business_effect=effect,
    )


def _relation_model(
    draft: _RelationDraft,
    *,
    is_primary: bool,
) -> RelationAssessment:
    payload = {
        "relation_code": draft.code,
        "status": draft.status,
        "is_primary": is_primary,
        "confidence_level": draft.confidence,
        "gate_results": [row.model_dump(mode="json") for row in draft.gates],
        "supporting_evidence_families": draft.family_codes,
        "business_effect": draft.business_effect,
        "eligible_question_codes": (
            _RELATION_QUESTIONS[draft.code]
            if draft.status in {"passed", "limited"}
            else []
        ),
        "reason_codes": draft.reason_codes,
        "limitations": draft.limitations,
        "evidence_refs": [row.model_dump(mode="json") for row in draft.evidence_refs],
    }
    return RelationAssessment(
        relation_code=draft.code,
        status=draft.status,
        is_primary=is_primary,
        confidence_level=draft.confidence,
        gate_results=draft.gates,
        supporting_evidence_families=draft.family_codes,
        business_effect=draft.business_effect,
        eligible_question_codes=(
            _RELATION_QUESTIONS[draft.code]
            if draft.status in {"passed", "limited"}
            else []
        ),
        reason_codes=draft.reason_codes,
        evidence_refs=draft.evidence_refs,
        limitations=draft.limitations,
        result_hash=stable_hash_json(
            payload,
            version="competitor_profile_relation_assessment_v1",
        ),
    )


def _primary_relation(
    drafts: Sequence[_RelationDraft],
    config: CompetitorRelationConfig,
) -> str | None:
    by_code = {row.code: row for row in drafts}
    for desired_status in ("passed", "limited"):
        for code in config.primary_relation_priority:
            if by_code[code].status == desired_status:
                return code
    return None


def _candidate_status(
    pair: PairFeatureRecord,
    drafts: Sequence[_RelationDraft],
    *,
    upstream_review: bool,
) -> str:
    if pair.candidate_status == "blocked":
        return "blocked"
    if upstream_review:
        return "review_required"
    if any(row.status == "passed" for row in drafts):
        return "eligible"
    if any(row.status == "limited" for row in drafts):
        return "limited"
    if any(row.status == "review_required" for row in drafts):
        return "review_required"
    return "reference_only" if pair.reference_member else "recalled_only"


def _held_relation_drafts(pair: PairFeatureRecord) -> list[_RelationDraft]:
    """Preserve all seven relation rows without upgrading an ineligible candidate."""

    review = pair.candidate_status in {"review_required", "blocked"}
    status = (
        "review_required"
        if review
        else "unassessable"
        if pair.unknown_reason_codes
        else "failed"
    )
    reason = (
        "candidate_requires_review_before_relation_evaluation"
        if review
        else "candidate_not_admitted_to_relation_evaluation"
    )
    return [
        _RelationDraft(
            code=code,
            gates=[
                GateResult(
                    gate_code="candidate_relation_evaluation_eligibility",
                    required=True,
                    known=True,
                    passed=False,
                    reason_code=reason,
                    evidence_refs=pair.evidence_refs,
                )
            ],
            status=status,
            confidence="unknown" if review else "low",
            family_codes=[],
            reason_codes=[reason],
            limitations=[reason],
            evidence_refs=pair.evidence_refs,
            business_effect={},
        )
        for code in sorted(_RELATION_QUESTIONS)
    ]


def _overall_confidence(
    drafts: Sequence[_RelationDraft],
    candidate_status: str,
) -> str:
    if candidate_status == "eligible":
        return "high" if any(row.confidence == "high" for row in drafts) else "medium"
    if candidate_status == "limited":
        return "medium"
    if candidate_status in {"reference_only", "recalled_only"}:
        return "low"
    return "unknown"


def _question_eligibility(
    *,
    drafts: Sequence[_RelationDraft],
    candidate_status: str,
    confidence: str,
    pool: PurchasePoolSemanticPairAssessment,
    value: ValueSubstitutionEvidencePair,
    pressure: PriceVolumePressureAssessment,
    families: Sequence[EvidenceFamilyAssessment],
    pair: PairFeatureRecord,
) -> list[QuestionEligibility]:
    relation_status = {row.code: row.status for row in drafts}
    formal = {
        code
        for code, status in relation_status.items()
        if status in {"passed", "limited"}
    }
    passed = {code for code, status in relation_status.items() if status == "passed"}
    available_families = set(_independent_formal_families(families))
    has_f5_difference = _has_f5_difference(value)
    if has_f5_difference and any(
        _enum_value(row.family) == "F5_capability_expression"
        and _enum_value(row.status) == "supporting"
        for row in families
    ):
        available_families.add("F5_capability_expression")
    purchase_choice_evidence_ready = (
        len(
            available_families
            & {
                "F1_purchase_reason",
                "F2_task_value_scene",
                "F3_audience_need",
                "F4_user_realization",
            }
        )
        >= 2
    )
    specs = {
        "purchase_choice": (
            ["direct_substitute", "same_budget_alternative"],
            ["F1_purchase_reason", "F2_task_value_scene", "F4_user_realization"],
            (
                "eligible"
                if "direct_substitute" in passed
                or (
                    "same_budget_alternative" in passed
                    and pool.purchase_pool.level in {"P0", "P1"}
                )
                and purchase_choice_evidence_ready
                else "limited"
                if formal & {"direct_substitute", "same_budget_alternative"}
                and pool.purchase_pool.level in {"P0", "P1"}
                and purchase_choice_evidence_ready
                else "unavailable"
            ),
            "用户选择问题仅在直接或同预算关系及购买池成立时可用",
        ),
        "price_volume_pressure": (
            sorted(formal),
            [],
            "eligible"
            if formal and pressure.pressure_direction != "unassessable" and passed
            else "limited"
            if formal and pressure.pressure_direction != "unassessable"
            else "unavailable",
            "量价问题只描述同口径市场承接，不回答降价增量",
        ),
        "value_substitution": (
            [
                "direct_substitute",
                "downtrade_diversion",
                "same_value_substitute",
                "uptrade_alternative",
            ],
            ["F1_purchase_reason", "F4_user_realization"],
            "eligible"
            if passed
            & {
                "direct_substitute",
                "downtrade_diversion",
                "same_value_substitute",
                "uptrade_alternative",
            }
            and available_families & {"F1_purchase_reason", "F4_user_realization"}
            else "limited"
            if formal
            & {
                "direct_substitute",
                "downtrade_diversion",
                "same_value_substitute",
                "uptrade_alternative",
            }
            else "unavailable",
            "价值替代不输出单卖点因果WTP",
        ),
        "configuration_follow": (
            sorted(formal),
            [
                "F1_purchase_reason",
                "F2_task_value_scene",
                "F4_user_realization",
                "F5_capability_expression",
            ],
            "eligible"
            if formal
            and has_f5_difference
            and available_families
            & {"F1_purchase_reason", "F2_task_value_scene", "F4_user_realization"}
            else "unavailable",
            "配置差异必须连接用户价值或市场压力，不能见差就跟",
        ),
        "same_brand_portfolio_role": (
            ["same_brand_ladder"],
            ["F1_purchase_reason", "F2_task_value_scene", "F4_user_realization"],
            "eligible"
            if "same_brand_ladder" in passed
            else "limited"
            if "same_brand_ladder" in formal
            else "unavailable",
            "同品牌关系成立后才回答产品线分流",
        ),
        "scenario_solution": (
            ["scenario_substitute"],
            [
                "F1_purchase_reason",
                "F2_task_value_scene",
                "F3_audience_need",
                "F4_user_realization",
            ],
            "eligible"
            if "scenario_substitute" in passed
            else "limited"
            if "scenario_substitute" in formal
            else "unavailable",
            "场景方案必须有F2及另一独立语义证据",
        ),
        "price_ladder_defense": (
            ["downtrade_diversion", "uptrade_alternative"],
            ["F1_purchase_reason", "F2_task_value_scene", "F4_user_realization"],
            "eligible"
            if passed & {"downtrade_diversion", "uptrade_alternative"}
            else "limited"
            if formal & {"downtrade_diversion", "uptrade_alternative"}
            else "unavailable",
            "上探下探只回答观察到的价格梯度与价值路线压力",
        ),
        "key_competitor_selection": (
            sorted(formal),
            [],
            "eligible"
            if candidate_status == "eligible" and confidence in {"high", "medium"}
            else "limited"
            if candidate_status == "limited" and formal
            else "unavailable",
            "是否进入重点集合由G19按独立决策信息继续判断",
        ),
    }
    results = []
    for question_code, (usable, required, availability, reason_cn) in sorted(
        specs.items()
    ):
        required_set = set(required)
        available = sorted(required_set & available_families)
        missing = []
        if availability == "unavailable":
            missing = sorted(required_set - available_families)
            if not usable:
                missing.append("formal_relation")
        boundary = _question_boundary(question_code, availability, pool, value)
        payload = {
            "question_code": question_code,
            "availability": availability,
            "usable_relation_codes": sorted(set(usable) & formal),
            "required_evidence_families": sorted(required_set),
            "available_evidence_families": available,
            "missing_inputs": sorted(set(missing)),
            "business_boundary_code": boundary,
            "reason_cn": reason_cn,
        }
        results.append(
            QuestionEligibility(
                **payload,
                result_hash=stable_hash_json(
                    payload,
                    version="competitor_profile_question_eligibility_v1",
                ),
            )
        )
    return results


def _question_boundary(
    question_code: str,
    availability: str,
    pool: PurchasePoolSemanticPairAssessment,
    value: ValueSubstitutionEvidencePair,
) -> str:
    if question_code == "purchase_choice" and pool.purchase_pool.level == "P3":
        return "p3_value_research_not_purchase_choice"
    if question_code == "value_substitution":
        return "single_claim_causal_wtp_forbidden"
    if question_code in {"price_volume_pressure", "price_ladder_defense"}:
        return "causal_sales_increment_forbidden"
    if value.evidence_status == "conflict":
        return "value_evidence_review_required"
    return (
        "formal_relation_and_evidence_available"
        if availability == "eligible"
        else "limited_evidence_only"
        if availability == "limited"
        else "required_relation_or_evidence_unavailable"
    )


def _gate(
    code: str,
    known: bool,
    passed: bool | None,
    reason: str,
    refs: Sequence[EvidenceRef],
) -> GateResult:
    return GateResult(
        gate_code=code,
        required=True,
        known=known,
        passed=passed if known else None,
        reason_code=reason,
        evidence_refs=_merge_refs(refs),
    )


def _pool_gate(
    pool: PurchasePoolSemanticPairAssessment,
    code: str,
) -> GateResult:
    return next(row for row in pool.purchase_pool.gate_results if row.gate_code == code)


def _threshold_capability(
    pair: PairFeatureRecord,
    config: CompetitorRelationConfig,
) -> tuple[bool, bool]:
    if not _module_pair_known(pair, "M03B"):
        return False, False
    rows = [
        row
        for row in pair.aligned_features
        if row.feature_group == "parameter"
        and row.feature_code in config.threshold_parameter_codes
    ]
    if not rows:
        return False, False
    return True, any(row.common_values for row in rows)


def _candidate_stronger_families(
    value: ValueSubstitutionEvidencePair,
) -> list[str]:
    result: set[str] = set()
    seen_lineage: set[str] = set()
    for row in value.value_assessments:
        if row.classification != "discriminative":
            continue
        for layer in row.layers:
            if layer.evidence_family == "F5_capability_expression":
                continue
            if layer.candidate_status not in {"positive", "supporting"}:
                continue
            if layer.target_status not in {"absent", "weak", "risk"}:
                continue
            lineage = set(layer.independent_lineage_keys)
            if lineage and lineage <= seen_lineage:
                continue
            result.add(layer.evidence_family)
            seen_lineage.update(lineage)
    return sorted(result)


def _positive_side_codes(
    value: ValueSubstitutionEvidencePair,
    side: str,
) -> set[str]:
    return {
        row.value_code
        for row in value.value_assessments
        if any(
            layer.layer_code.startswith(("F1_", "F4_"))
            and getattr(layer, f"{side}_status") in {"positive", "supporting"}
            for layer in row.layers
        )
    }


def _has_value_path_difference(value: ValueSubstitutionEvidencePair) -> bool:
    return any(
        row.positive_overlap
        and any(
            layer.comparison_status == "different"
            for layer in row.layers
            if layer.layer_code
            in {
                "F4_claim_value",
                "F4_user_realization",
                "F5_claim_expression",
                "F5_parameter",
            }
        )
        for row in value.value_assessments
    )


def _has_f5_difference(value: ValueSubstitutionEvidencePair) -> bool:
    return any(
        layer.comparison_status in {"different", "target_only", "candidate_only"}
        for row in value.value_assessments
        for layer in row.layers
        if layer.layer_code in {"F5_claim_expression", "F5_parameter"}
    )


def _shared_feature_codes(pair: PairFeatureRecord, group: str) -> list[str]:
    return sorted(
        row.feature_code
        for row in pair.aligned_features
        if row.feature_group == group and row.common_values
    )


def _reason_direction(rows) -> str:
    if any(
        row.comparison_status in {"shared_strong", "shared_limited"} for row in rows
    ):
        return "parity"
    if any(
        row.candidate_strength == "strong" and row.target_strength != "strong"
        for row in rows
    ):
        return "candidate_stronger"
    if any(
        row.target_strength == "strong" and row.candidate_strength != "strong"
        for row in rows
    ):
        return "target_stronger"
    return "unknown"


def _value_direction(value: ValueSubstitutionEvidencePair) -> str:
    if value.shared_discriminative_value_codes:
        return "parity"
    if (
        value.candidate_only_positive_value_codes
        and not value.target_only_positive_value_codes
    ):
        return "candidate_stronger"
    if (
        value.target_only_positive_value_codes
        and not value.candidate_only_positive_value_codes
    ):
        return "target_stronger"
    return (
        "different_route" if value.evidence_status == "different_route" else "unknown"
    )


def _brand(value: str | None) -> str:
    return "".join((value or "").lower().split())


def _module_pair_known(pair: PairFeatureRecord, module: str) -> bool:
    row = next(item for item in pair.module_availability if item.module_code == module)
    return (
        row.target_availability == "present" and row.candidate_availability == "present"
    )


def _refs_for_modules(pair: PairFeatureRecord, *modules: str) -> list[EvidenceRef]:
    allowed = set(modules)
    return _merge_refs(ref for ref in pair.evidence_refs if ref.module_code in allowed)


def _family_refs(rows: Sequence[EvidenceFamilyAssessment]) -> list[EvidenceRef]:
    return _merge_refs(*(row.evidence_refs for row in rows))


def _lineage_keys(refs: Sequence[EvidenceRef]) -> list[str]:
    return sorted({key for ref in refs for key in _ref_lineage_keys(ref)})


def _ref_lineage_keys(ref: EvidenceRef) -> list[str]:
    if ref.evidence_ids:
        return [f"evidence:{value}" for value in ref.evidence_ids]
    if ref.raw_row_ids:
        return [f"raw-row:{value}" for value in ref.raw_row_ids]
    if ref.source_file_ids:
        return [f"source-file:{value}" for value in ref.source_file_ids]
    return [
        f"derived:{ref.source_batch_id or ref.profile_version}:"
        f"{ref.result_hash}"
    ]


def _merge_refs(*groups: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    unique: dict[tuple[str, str, str, str, str], EvidenceRef] = {}
    for group in groups:
        for ref in group:
            key = (
                ref.module_code,
                ref.source_batch_id or "",
                ref.record_type,
                ref.record_id,
                ref.result_hash,
            )
            unique[key] = ref
    return [unique[key] for key in sorted(unique)]


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


__all__ = [
    "CompetitorRelationEvaluationError",
    "CompetitorRelationEvaluator",
]
