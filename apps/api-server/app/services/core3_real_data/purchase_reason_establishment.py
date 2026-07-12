"""Positive-only establishment and user validation for M12D purchase reasons."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DReasonEstablishmentStatus,
    M12DUserValidationStatus,
)
from app.services.core3_real_data.purchase_reason_pressure import (
    COMMENT_SCOPE_BY_REASON,
    M12C_CLAIM_SCOPE_BY_REASON,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DProfileScoreResult,
    M12DScoredPurchaseReasonAnchor,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
)


DOMAIN_ESTABLISHMENT_SCORES: Mapping[M12DEvidenceDomain, Decimal] = {
    M12DEvidenceDomain.PARAM_FACT: Decimal("3.0000"),
    M12DEvidenceDomain.FACT_CLAIM: Decimal("2.0000"),
    M12DEvidenceDomain.COMMENT_PERCEPTION: Decimal("2.0000"),
    M12DEvidenceDomain.CLAIM_VALUE: Decimal("3.0000"),
    M12DEvidenceDomain.SEMANTIC_SCENE: Decimal("2.0000"),
    M12DEvidenceDomain.MARKET_ACCEPTANCE: Decimal("2.0000"),
    M12DEvidenceDomain.CLAIM_POSITION: Decimal("1.0000"),
    M12DEvidenceDomain.SERVICE_SIGNAL: Decimal("0.5000"),
    M12DEvidenceDomain.RISK_SIGNAL: Decimal("0.0000"),
}
STRONG_ESTABLISHMENT_DOMAINS = {
    M12DEvidenceDomain.PARAM_FACT,
    M12DEvidenceDomain.COMMENT_PERCEPTION,
    M12DEvidenceDomain.CLAIM_VALUE,
    M12DEvidenceDomain.MARKET_ACCEPTANCE,
}
M12C_POSITIVE_ROLES = {
    "premium_driver",
    "premium_driver_estimated",
    "sales_driver",
    "sales_driver_estimated",
    "unique_payment_potential",
    "user_validated_need",
    "value_bundle_claim",
}
M12C_NEUTRAL_ESTABLISHMENT_ROLES = {"basic_threshold"}
M12C_ESTABLISHMENT_ROLES = M12C_POSITIVE_ROLES | M12C_NEUTRAL_ESTABLISHMENT_ROLES
OBJECTIVE_MARKET_REASON_CODES: Mapping[str, frozenset[str]] = {
    "TV": frozenset(
        {
            "low_price_core_experience_intact",
            "same_price_core_config_gain",
            "same_size_picture_step_up",
            "big_screen_cinema_substitution",
            "living_room_upgrade_one_step",
        }
    ),
    "AC": frozenset(
        {
            "room_size_capacity_match_reduces_risk",
            "large_space_one_step_cooling_heating",
            "cooling_heating_performance_justifies_price",
            "long_term_energy_saving_offsets_price",
            "same_price_efficiency_capacity_gain",
            "low_price_core_ac_experience_intact",
            "small_room_installation_fit",
        }
    ),
}
TV_SUBJECTIVE_PRICE_REASON_CODES = {
    "picture_upgrade_justifies_price",
    "worth_paying_more_for_experience_upgrade",
    "av_user_willing_to_pay_for_picture",
}
TV_GAME_REASON_CODES = {
    "gaming_device_fit_reduces_risk",
    "sports_motion_stability",
}
TV_PROPOSITION_SENSITIVE_REASON_CODES = {
    "family_operation_less_friction",
    "new_home_aesthetic_fit",
}
AC_PRICE_REASON_CODES = {
    "cooling_heating_performance_justifies_price",
    "long_term_energy_saving_offsets_price",
    "same_price_efficiency_capacity_gain",
    "low_price_core_ac_experience_intact",
}
AC_COMMENT_DECISION_REASON_CODES = {
    "sleep_room_quiet_comfort_assurance",
    "elderly_child_soft_wind_comfort",
    "fresh_air_health_reduces_stuffy_risk",
    "humidity_dehumidification_reassurance",
    "self_cleaning_reduces_maintenance_risk",
    "small_room_installation_fit",
    "smart_remote_control_less_friction",
}


@dataclass(frozen=True)
class PositiveEvidenceAssessment:
    domains: frozenset[M12DEvidenceDomain]
    proposition_refs: tuple[M12DSourceRef, ...]
    user_support_refs: tuple[M12DSourceRef, ...]
    aligned_positive_comment: bool
    aligned_comment_dimension: bool
    positive_m12c: bool
    market_acceptance: bool
    product_fact_or_claim: bool
    semantic_scene: bool


@dataclass(frozen=True)
class BusinessBoundaryAssessment:
    passed: bool
    reason_code: str | None = None


class UserValidationClassifier:
    """Classify product proposition and observed user/market acceptance."""

    def assess_positive_evidence(
        self,
        *,
        candidate: M12DAnchorCandidate,
        context: M12DSkuPurchaseReasonContext,
    ) -> PositiveEvidenceAssessment:
        candidate_domains = _domains(candidate.evidence_domains_json)
        comment = _positive_comment_evidence(candidate, context)
        m12c = _positive_m12c_evidence(candidate, context)

        domains = set(candidate_domains)
        if M12DEvidenceDomain.COMMENT_PERCEPTION in domains and not comment.positive:
            domains.remove(M12DEvidenceDomain.COMMENT_PERCEPTION)
        if M12DEvidenceDomain.CLAIM_VALUE in domains and not m12c.establishment_supported:
            domains.remove(M12DEvidenceDomain.CLAIM_VALUE)

        product_domains = {
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.FACT_CLAIM,
        }
        product_fact_or_claim = bool(domains & product_domains)
        semantic_scene = M12DEvidenceDomain.SEMANTIC_SCENE in domains
        market_acceptance = M12DEvidenceDomain.MARKET_ACCEPTANCE in domains
        proposition_refs = _candidate_refs_for_domains(
            candidate,
            product_domains | {M12DEvidenceDomain.SEMANTIC_SCENE},
        )
        support_refs = list(comment.refs)
        if market_acceptance:
            support_refs.extend(
                _candidate_refs_for_domains(
                    candidate,
                    {M12DEvidenceDomain.MARKET_ACCEPTANCE},
                )
            )
        if m12c.positive:
            support_refs.extend(m12c.refs)

        return PositiveEvidenceAssessment(
            domains=frozenset(domains),
            proposition_refs=tuple(_dedupe_refs(proposition_refs)),
            user_support_refs=tuple(_dedupe_refs(support_refs)),
            aligned_positive_comment=comment.positive,
            aligned_comment_dimension=comment.aligned_dimension,
            positive_m12c=m12c.positive,
            market_acceptance=market_acceptance,
            product_fact_or_claim=product_fact_or_claim,
            semantic_scene=semantic_scene,
        )

    def classify(
        self,
        *,
        candidate: M12DAnchorCandidate,
        evidence: PositiveEvidenceAssessment,
    ) -> M12DUserValidationStatus:
        category = _category(candidate.product_category)
        objective_market_reason = candidate.anchor_code in OBJECTIVE_MARKET_REASON_CODES[category]
        product_or_scene = evidence.product_fact_or_claim or evidence.semantic_scene
        if evidence.aligned_positive_comment and (
            evidence.market_acceptance or evidence.positive_m12c
        ):
            return M12DUserValidationStatus.USER_VALIDATED
        if evidence.aligned_positive_comment and product_or_scene:
            return M12DUserValidationStatus.USER_SUPPORTED
        if evidence.positive_m12c and product_or_scene:
            return M12DUserValidationStatus.USER_SUPPORTED
        if (
            objective_market_reason
            and evidence.market_acceptance
            and evidence.product_fact_or_claim
            and evidence.semantic_scene
        ):
            return M12DUserValidationStatus.MARKET_SUPPORTED
        return M12DUserValidationStatus.NOT_OBSERVED


class ReasonEstablishmentScorer:
    """Score only positive, anchor-aligned evidence and apply 9/8/7 gates."""

    def __init__(
        self,
        *,
        user_validation_classifier: UserValidationClassifier | None = None,
    ) -> None:
        self.user_validation_classifier = (
            user_validation_classifier or UserValidationClassifier()
        )

    def score(
        self,
        *,
        candidate: M12DAnchorCandidate,
        context: M12DSkuPurchaseReasonContext,
        scored_anchor: M12DScoredPurchaseReasonAnchor,
        baseline_core_count: int,
    ) -> M12DScoredPurchaseReasonAnchor:
        evidence = self.user_validation_classifier.assess_positive_evidence(
            candidate=candidate,
            context=context,
        )
        validation = self.user_validation_classifier.classify(
            candidate=candidate,
            evidence=evidence,
        )
        score = _q(
            sum(
                (DOMAIN_ESTABLISHMENT_SCORES[domain] for domain in evidence.domains),
                Decimal("0.0000"),
            )
        )
        strong_domain_count = len(evidence.domains & STRONG_ESTABLISHMENT_DOMAINS)
        scene_fit = evidence.semantic_scene or (
            evidence.aligned_positive_comment and evidence.market_acceptance
        )
        boundary = _business_boundary(
            candidate=candidate,
            context=context,
            evidence=evidence,
            validation=validation,
        )
        objective_falsification = _has_issue(
            context,
            module_code="M03B",
            anchor_code=candidate.anchor_code,
            issue_code="m03b_true_param_conflict",
        )
        comment_domain_claimed = M12DEvidenceDomain.COMMENT_PERCEPTION in _domains(
            candidate.evidence_domains_json
        )
        comment_evidence_exists = bool(
            context.comment_profile.summary.get("dimension_summary_json")
            or _comment_records(context)
        )
        evidence_misalignment = (
            comment_domain_claimed
            and comment_evidence_exists
            and not evidence.aligned_comment_dimension
        )
        blocking_reasons = []
        if objective_falsification:
            blocking_reasons.append("objective_falsification")
        if evidence_misalignment:
            blocking_reasons.append("evidence_misalignment")

        threshold_path: str | None = None
        accepted_validation = validation in {
            M12DUserValidationStatus.USER_SUPPORTED,
            M12DUserValidationStatus.USER_VALIDATED,
        }
        fallback_validation = accepted_validation or (
            validation == M12DUserValidationStatus.MARKET_SUPPORTED
        )
        candidate_role_capped = candidate.role_cap == M12DAnchorRole.WEAK_EXPRESSION
        common_gate = (
            strong_domain_count >= 2
            and scene_fit
            and boundary.passed
            and not candidate_role_capped
            and not blocking_reasons
        )
        if score >= Decimal("9.0000") and common_gate and accepted_validation:
            threshold_path = "standard_9"
        elif (
            baseline_core_count == 0
            and score >= Decimal("8.0000")
            and common_gate
            and fallback_validation
        ):
            threshold_path = "no_core_8"
        elif (
            baseline_core_count == 0
            and score >= Decimal("7.0000")
            and common_gate
            and fallback_validation
        ):
            threshold_path = "reason_specific_7"

        proposition_exists = evidence.product_fact_or_claim and evidence.semantic_scene
        limited_reason_exists = (
            score >= Decimal("7.0000")
            and strong_domain_count >= 2
            and scene_fit
            and boundary.passed
            and fallback_validation
            and not blocking_reasons
        )
        if blocking_reasons:
            status = M12DReasonEstablishmentStatus.REJECTED
        elif threshold_path == "standard_9":
            status = M12DReasonEstablishmentStatus.ESTABLISHED
        elif threshold_path in {"no_core_8", "reason_specific_7"}:
            status = M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED
        elif limited_reason_exists:
            status = M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED
        elif proposition_exists and validation == M12DUserValidationStatus.NOT_OBSERVED:
            status = M12DReasonEstablishmentStatus.PROPOSITION_ONLY
        else:
            status = M12DReasonEstablishmentStatus.REJECTED

        core_eligible = threshold_path is not None
        ineligible_reasons = list(blocking_reasons)
        if not boundary.passed and boundary.reason_code:
            ineligible_reasons.append(boundary.reason_code)
        if score < Decimal("7.0000"):
            ineligible_reasons.append("establishment_score_below_7")
        if strong_domain_count < 2:
            ineligible_reasons.append("strong_domain_count_below_2")
        if not scene_fit:
            ineligible_reasons.append("scene_fit_missing")
        if validation == M12DUserValidationStatus.NOT_OBSERVED:
            ineligible_reasons.append("user_or_market_support_not_observed")
        if candidate_role_capped:
            ineligible_reasons.append("candidate_role_cap_weak_expression")
        if limited_reason_exists and baseline_core_count > 0 and threshold_path is None:
            ineligible_reasons.append("fallback_requires_baseline_no_core")

        return scored_anchor.model_copy(
            update={
                "establishment_status": status,
                "establishment_score": score,
                "establishment_domains_json": sorted(
                    evidence.domains,
                    key=lambda domain: domain.value,
                ),
                "user_validation_status": validation,
                "core_eligible": core_eligible,
                "core_ineligible_reasons_json": _dedupe_strings(ineligible_reasons),
                "proposition_evidence_json": list(evidence.proposition_refs),
                "user_support_evidence_json": list(evidence.user_support_refs),
                "role_reason_json": {
                    **scored_anchor.role_reason_json,
                    "establishment_score": str(score),
                    "establishment_strong_domain_count": strong_domain_count,
                    "establishment_scene_fit": scene_fit,
                    "user_validation_status": validation.value,
                    "business_boundary_passed": boundary.passed,
                    "business_boundary_reason_code": boundary.reason_code,
                    "establishment_threshold_path": threshold_path,
                    "baseline_core_count": baseline_core_count,
                },
            }
        )

    def summarize_profile(self, result: M12DProfileScoreResult) -> M12DProfileScoreResult:
        established = [
            anchor.anchor_code
            for anchor in result.scored_anchors
            if str(anchor.establishment_status)
            in {
                M12DReasonEstablishmentStatus.ESTABLISHED.value,
                M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
            }
        ]
        propositions = [
            anchor.anchor_code
            for anchor in result.scored_anchors
            if str(anchor.establishment_status)
            == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
        ]
        return result.model_copy(
            update={
                "established_anchors_json": established,
                "proposition_anchors_json": propositions,
            }
        )


@dataclass(frozen=True)
class _CommentEvidence:
    positive: bool
    aligned_dimension: bool
    refs: tuple[M12DSourceRef, ...]


@dataclass(frozen=True)
class _M12CEvidence:
    establishment_supported: bool
    positive: bool
    refs: tuple[M12DSourceRef, ...]


def _positive_comment_evidence(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> _CommentEvidence:
    category = _category(context.product_category)
    scope = COMMENT_SCOPE_BY_REASON.get(category, {}).get(candidate.anchor_code, frozenset())
    scope_by_dimension: dict[str, set[str | None]] = defaultdict(set)
    for dimension_code, subdimension_code in scope:
        scope_by_dimension[dimension_code].add(subdimension_code)
    summary_payload = context.comment_profile.summary.get("dimension_summary_json") or {}
    dimension_summary = summary_payload if isinstance(summary_payload, Mapping) else {}
    aligned_dimension = False
    positive = False
    refs: list[M12DSourceRef] = []

    for dimension_code, target_subdimensions in scope_by_dimension.items():
        summary = dimension_summary.get(dimension_code)
        if not isinstance(summary, Mapping):
            continue
        observed_subdimensions = {
            str(code)
            for code in summary.get("subdimension_codes") or []
            if str(code)
        }
        whole_dimension = None in target_subdimensions
        exact_subdimensions = {
            str(code) for code in target_subdimensions if code is not None
        }
        dimension_aligned = whole_dimension or bool(
            observed_subdimensions & exact_subdimensions
        )
        if not dimension_aligned:
            continue
        aligned_dimension = True
        aggregate_is_scoped = whole_dimension or (
            bool(observed_subdimensions)
            and observed_subdimensions.issubset(exact_subdimensions)
        )
        polarity_counts = summary.get("polarity_counts") or {}
        positive_count = _int_value(
            polarity_counts.get("positive") if isinstance(polarity_counts, Mapping) else 0
        )
        if aggregate_is_scoped and positive_count > 0:
            positive = True
            refs.extend(_comment_profile_refs(context, dimension_code, summary))

    for record in _comment_records(context):
        if not _comment_record_aligns(scope, record):
            continue
        aligned_dimension = True
        if str(record.get("polarity") or "").lower() != "positive":
            continue
        positive = True
        ref = _record_ref("M05C", record)
        if ref is not None:
            refs.append(ref)

    return _CommentEvidence(
        positive=positive,
        aligned_dimension=aligned_dimension,
        refs=tuple(_dedupe_refs(refs)),
    )


def _positive_m12c_evidence(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> _M12CEvidence:
    category = _category(context.product_category)
    claim_scope = set(
        M12C_CLAIM_SCOPE_BY_REASON.get(category, {}).get(
            candidate.anchor_code,
            frozenset(),
        )
    )
    anchor_roles_payload = context.claim_value_profile.summary.get(
        "anchor_claim_value_roles"
    ) or {}
    anchor_roles = (
        anchor_roles_payload.get(candidate.anchor_code) or {}
        if isinstance(anchor_roles_payload, Mapping)
        else {}
    )
    establishment_supported = False
    positive = False
    qualifying_roles: dict[str, set[str]] = {}
    if isinstance(anchor_roles, Mapping):
        for claim_code, raw_roles in anchor_roles.items():
            if str(claim_code) not in claim_scope:
                continue
            roles = _string_set(raw_roles)
            matched_roles = roles & M12C_ESTABLISHMENT_ROLES
            if matched_roles:
                qualifying_roles[str(claim_code)] = matched_roles
                establishment_supported = True
            if roles & M12C_POSITIVE_ROLES:
                positive = True

    refs = _m12c_role_refs(context, qualifying_roles)
    return _M12CEvidence(
        establishment_supported=establishment_supported,
        positive=positive,
        refs=tuple(refs),
    )


def _business_boundary(
    *,
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
    evidence: PositiveEvidenceAssessment,
    validation: M12DUserValidationStatus,
) -> BusinessBoundaryAssessment:
    category = _category(context.product_category)
    code = candidate.anchor_code
    market = context.market_profile.summary
    if validation == M12DUserValidationStatus.NOT_OBSERVED:
        return BusinessBoundaryAssessment(False, "user_or_market_support_not_observed")
    if category == "TV":
        if code == "big_screen_cinema_substitution":
            if _decimal_value(market.get("screen_size_inch")) < Decimal("75"):
                return BusinessBoundaryAssessment(False, "tv_big_screen_below_75_inch")
            if not (evidence.aligned_positive_comment or evidence.market_acceptance):
                return BusinessBoundaryAssessment(False, "tv_big_screen_acceptance_missing")
        elif code == "low_price_core_experience_intact":
            if _normalized(market.get("price_band_category")) not in {"low", "mid_low"}:
                return BusinessBoundaryAssessment(False, "tv_low_price_band_mismatch")
            if not (evidence.aligned_positive_comment or evidence.market_acceptance):
                return BusinessBoundaryAssessment(False, "tv_price_value_acceptance_missing")
        elif code in TV_SUBJECTIVE_PRICE_REASON_CODES:
            if _normalized(market.get("price_band_size")) not in {"mid_high", "high"}:
                return BusinessBoundaryAssessment(False, "tv_premium_size_price_band_mismatch")
            if not evidence.aligned_positive_comment:
                return BusinessBoundaryAssessment(False, "tv_picture_positive_comment_missing")
        elif code in TV_GAME_REASON_CODES and not evidence.aligned_positive_comment:
            return BusinessBoundaryAssessment(False, "tv_game_positive_comment_missing")
        elif (
            code in TV_PROPOSITION_SENSITIVE_REASON_CODES
            and not evidence.aligned_positive_comment
            and not evidence.positive_m12c
        ):
            return BusinessBoundaryAssessment(False, "tv_proposition_user_support_missing")
        return BusinessBoundaryAssessment(True)

    if code in {"room_size_capacity_match_reduces_risk", "large_space_one_step_cooling_heating"}:
        if not (evidence.aligned_positive_comment or evidence.market_acceptance):
            return BusinessBoundaryAssessment(False, "ac_capacity_acceptance_missing")
    elif code in AC_PRICE_REASON_CODES:
        comment_market = evidence.aligned_positive_comment and evidence.market_acceptance
        if not (evidence.positive_m12c or comment_market):
            return BusinessBoundaryAssessment(False, "ac_price_value_support_missing")
    elif code in AC_COMMENT_DECISION_REASON_CODES and not evidence.aligned_positive_comment:
        return BusinessBoundaryAssessment(False, "ac_function_positive_comment_missing")
    return BusinessBoundaryAssessment(True)


def _comment_records(context: M12DSkuPurchaseReasonContext) -> list[Mapping[str, Any]]:
    return [
        record
        for record in context.comment_profile.records
        if str(record.get("table_name") or "") == "core3_comment_fact_atom"
    ]


def _comment_record_aligns(
    scope: Iterable[tuple[str, str | None]],
    record: Mapping[str, Any],
) -> bool:
    dimension = str(record.get("dimension_code") or "")
    subdimension = str(record.get("subdimension_code") or "")
    return any(
        dimension == target_dimension
        and (target_subdimension is None or subdimension == target_subdimension)
        for target_dimension, target_subdimension in scope
    )


def _comment_profile_refs(
    context: M12DSkuPurchaseReasonContext,
    dimension_code: str,
    summary: Mapping[str, Any],
) -> list[M12DSourceRef]:
    result = []
    for ref in context.comment_profile.source_refs:
        if ref.table_name != "core3_sku_comment_fact_profile":
            continue
        extra = dict(ref.extra)
        extra.update(
            {
                "dimension_code": dimension_code,
                "polarity_counts": summary.get("polarity_counts") or {},
                "positive_examples": [
                    {
                        key: raw.get(key)
                        for key in (
                            "comment_text",
                            "subdimension_code",
                            "evidence_ids",
                        )
                        if raw.get(key) not in (None, "", [])
                    }
                    for raw in summary.get("examples") or []
                    if isinstance(raw, Mapping)
                    and str(raw.get("polarity") or "").lower() == "positive"
                ][:3],
            }
        )
        result.append(ref.model_copy(update={"extra": extra}))
    return result


def _m12c_role_refs(
    context: M12DSkuPurchaseReasonContext,
    qualifying_roles: Mapping[str, set[str]],
) -> list[M12DSourceRef]:
    refs: list[M12DSourceRef] = []
    for record in context.claim_value_profile.records:
        claim_code = str(record.get("claim_code") or "")
        role = str(record.get("claim_value_role") or "")
        if role not in qualifying_roles.get(claim_code, set()):
            continue
        ref = _record_ref("M12C", record)
        if ref is not None:
            refs.append(ref)
    payload = context.claim_value_profile.summary.get("claim_value_role_evidence") or {}
    if isinstance(payload, Mapping):
        for claim_code, roles in qualifying_roles.items():
            claim_payload = payload.get(claim_code) or {}
            if not isinstance(claim_payload, Mapping):
                continue
            for role in roles:
                for raw in claim_payload.get(role) or []:
                    if not isinstance(raw, Mapping):
                        continue
                    table_name = str(raw.get("table_name") or "")
                    record_id = str(raw.get("record_id") or "")
                    if not table_name or not record_id:
                        continue
                    refs.append(
                        M12DSourceRef(
                            module_code="M12C",
                            table_name=table_name,
                            record_id=record_id,
                            result_hash=(
                                str(raw.get("result_hash"))
                                if raw.get("result_hash")
                                else None
                            ),
                            evidence_ids=[
                                str(value)
                                for value in raw.get("evidence_ids") or []
                                if str(value)
                            ],
                            extra={
                                "claim_code": claim_code,
                                "claim_value_role": role,
                                "reason_cn": raw.get("reason_cn"),
                            },
                        )
                    )
    return _dedupe_refs(refs)


def _candidate_refs_for_domains(
    candidate: M12DAnchorCandidate,
    domains: set[M12DEvidenceDomain],
) -> list[M12DSourceRef]:
    return _dedupe_refs(
        ref
        for match in candidate.evidence_matches
        if M12DEvidenceDomain(str(match.evidence_domain)) in domains
        for ref in match.source_refs_json
    )


def _record_ref(module_code: str, record: Mapping[str, Any]) -> M12DSourceRef | None:
    table_name = str(record.get("table_name") or "")
    record_id = str(record.get("record_id") or "")
    if not table_name or not record_id:
        return None
    extra = {
        key: record.get(key)
        for key in (
            "dimension_code",
            "subdimension_code",
            "polarity",
            "raw_comment_text",
            "claim_code",
            "claim_value_role",
            "reason_cn",
        )
        if record.get(key) not in (None, "")
    }
    return M12DSourceRef(
        module_code=module_code,
        table_name=table_name,
        record_id=record_id,
        result_hash=str(record.get("result_hash")) if record.get("result_hash") else None,
        extra=extra,
    )


def _has_issue(
    context: M12DSkuPurchaseReasonContext,
    *,
    module_code: str,
    anchor_code: str,
    issue_code: str,
) -> bool:
    quality = context.input_quality_json.get(module_code)
    if quality is None:
        return False
    return any(
        str(issue.code) == issue_code
        and anchor_code in {str(value) for value in issue.affected_anchor_codes}
        for issue in quality.issues
    )


def _domains(values: Iterable[M12DEvidenceDomain | str]) -> set[M12DEvidenceDomain]:
    result = set()
    for value in values:
        try:
            result.add(M12DEvidenceDomain(str(value)))
        except ValueError:
            continue
    return result


def _string_set(value: Any) -> set[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return {str(item) for item in value if str(item)}
    return {str(value)} if value else set()


def _category(value: str) -> str:
    return "AC" if str(value).strip().upper() == "AC" else "TV"


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _int_value(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _decimal_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _dedupe_refs(refs: Iterable[M12DSourceRef]) -> list[M12DSourceRef]:
    result = []
    seen = set()
    for ref in refs:
        key = (str(ref.module_code), ref.table_name, ref.record_id)
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return result


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


__all__ = [
    "BusinessBoundaryAssessment",
    "PositiveEvidenceAssessment",
    "ReasonEstablishmentScorer",
    "UserValidationClassifier",
]
