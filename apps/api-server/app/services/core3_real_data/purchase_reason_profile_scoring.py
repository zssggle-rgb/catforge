"""Evidence scoring and role classification for M12D purchase reasons."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    Core3ConfidenceLevel,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputAvailability,
    M12DInputStatus,
    M12DIssueScope,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DReasonEstablishmentStatus,
    M12DUserValidationStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_quality import (
    M12DAnchorQualityAssessment,
    assess_anchor_input_quality,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DAnchorCandidateSet,
    M12DProfileScoreResult,
    M12DScoredPurchaseReasonAnchor,
    M12DSkuPurchaseReasonContext,
)
from app.services.core3_real_data.purchase_reason_pressure import (
    PurchasePressureClassifier,
)
from app.services.core3_real_data.purchase_reason_establishment import (
    ReasonEstablishmentScorer,
)


DOMAIN_MAX_SCORES: Mapping[M12DEvidenceDomain, Decimal] = {
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
STRONG_EVIDENCE_DOMAINS = {
    M12DEvidenceDomain.PARAM_FACT,
    M12DEvidenceDomain.COMMENT_PERCEPTION,
    M12DEvidenceDomain.CLAIM_VALUE,
    M12DEvidenceDomain.MARKET_ACCEPTANCE,
}
HARD_RISK_FLAGS = {
    "comment_negative_dominates",
    "claim_value_drag_factor",
}
ANCHOR_CORE_BLOCK_FLAGS = {
    "anchor_quality_blocking",
    "price_value_core_evidence_missing",
}
AC_CLAIM_VALUE_POSITIVE_ROLES = {
    "sales_driver_estimated",
    "premium_driver_estimated",
    "sales_driver",
    "premium_driver",
}
AC_CLAIM_VALUE_RISK_OR_WEAK_ROLES = {
    "basic_threshold",
    "drag_factor",
    "high_price_competitor_intercept",
    "opportunity_gap",
    "price_up_opportunity",
    "weak_user_perception_claim",
}
AC_CORE_BLOCK_FLAGS = {
    *ANCHOR_CORE_BLOCK_FLAGS,
    "ac_claim_value_risk_role_dominant",
    "ac_service_signal_only",
}
PRICE_VALUE_REASON_CODES: Mapping[str, frozenset[str]] = {
    "TV": frozenset(
        {
            "picture_upgrade_justifies_price",
            "low_price_core_experience_intact",
            "same_price_core_config_gain",
            "same_size_picture_step_up",
            "worth_paying_more_for_experience_upgrade",
            "av_user_willing_to_pay_for_picture",
        }
    ),
    "AC": frozenset(
        {
            "cooling_heating_performance_justifies_price",
            "long_term_energy_saving_offsets_price",
            "same_price_efficiency_capacity_gain",
            "low_price_core_ac_experience_intact",
        }
    ),
}
CORE_ANCHOR_LIMIT = 3
CORE_RANK_WEIGHTS = (Decimal("0.6000"), Decimal("0.2500"), Decimal("0.1500"))
PROFILE_READY_CONFIDENCE = Decimal("0.7000")
SUPPORTING_READY_CONFIDENCE = Decimal("0.6000")


class EvidenceStrengthScorer:
    def score(
        self,
        candidate: M12DAnchorCandidate,
        context: M12DSkuPurchaseReasonContext,
    ) -> M12DScoredPurchaseReasonAnchor:
        domains = _scoring_domains(candidate, context)
        domain_scores = {
            domain.value: DOMAIN_MAX_SCORES[domain]
            for domain in domains
            if domain in DOMAIN_MAX_SCORES
        }
        raw_score = _sum_decimals(domain_scores.values())
        quality_assessment = assess_anchor_input_quality(candidate, context)
        direct_risk_flags = _risk_flags(candidate, context)
        risk_flags = _dedupe([*direct_risk_flags, *quality_assessment.risk_flags])
        quality_score_penalty = quality_assessment.score_penalty
        if (
            "claim_value_drag_factor" in direct_risk_flags
            and "m12c_related_claim_negative" in quality_assessment.risk_flags
        ):
            quality_score_penalty = max(
                Decimal("0.0000"),
                quality_score_penalty - Decimal("2.0000"),
            )
        conflict_penalty = _conflict_penalty(risk_flags) + quality_score_penalty
        adjusted_score = max(Decimal("0.0000"), raw_score - conflict_penalty)
        evidence_strength = _evidence_strength(
            adjusted_score=adjusted_score,
            domains=domains,
            candidate=candidate,
            risk_flags=risk_flags,
        )
        confidence = _anchor_confidence(
            evidence_strength, risk_flags, quality_assessment
        )
        role_reason = {
            "raw_evidence_score": _q(raw_score),
            "conflict_penalty": _q(conflict_penalty),
            "adjusted_evidence_score": _q(adjusted_score),
            "matched_domain_count": len(domains),
            "strong_domain_count": len(domains & STRONG_EVIDENCE_DOMAINS),
            "role_cap": str(candidate.role_cap) if candidate.role_cap else None,
            "role_cap_reasons": candidate.role_cap_reasons,
            "quality_role_cap": (
                quality_assessment.role_cap.value
                if quality_assessment.role_cap is not None
                else None
            ),
            "quality_score_penalty": _q(quality_score_penalty),
            "quality_confidence_penalty": _q(quality_assessment.confidence_penalty),
            "quality_confidence_cap": (
                _q(quality_assessment.confidence_cap)
                if quality_assessment.confidence_cap is not None
                else None
            ),
            "applied_quality_issues": list(quality_assessment.applied_issues),
        }
        if _is_ac_category(candidate.product_category):
            role_reason.update(
                {
                    "claim_value_status": str(context.claim_value_status),
                    "semantic_profile_status": str(context.semantic_profile_status),
                    "semantic_market_status": str(context.semantic_market_status),
                    "market_profile_status": str(context.market_profile_status),
                    "claim_value_roles": sorted(
                        _candidate_claim_value_roles(
                            candidate, context.claim_value_profile.summary
                        )
                    ),
                    "ac_core_block_flags": [
                        flag for flag in risk_flags if flag in AC_CORE_BLOCK_FLAGS
                    ],
                }
            )
        weakness_summary = _weakness_summary(candidate, risk_flags, quality_assessment)
        return M12DScoredPurchaseReasonAnchor(
            taxonomy_version=candidate.taxonomy_version,
            product_category=candidate.product_category,
            sku_code=candidate.sku_code,
            anchor_code=candidate.anchor_code,
            anchor_cn=candidate.anchor_cn,
            anchor_family_code=candidate.anchor_family_code,
            anchor_family_cn=candidate.anchor_family_cn,
            anchor_rank=candidate.candidate_rank,
            related_value_theme_codes=candidate.related_value_theme_codes,
            role=M12DAnchorRole.WEAK_EXPRESSION,
            evidence_strength=evidence_strength,
            confidence=confidence,
            raw_evidence_score=_q(raw_score),
            conflict_penalty=_q(conflict_penalty),
            adjusted_evidence_score=_q(adjusted_score),
            evidence_domains_json=sorted(domains, key=lambda item: item.value),
            domain_scores_json={key: _q(value) for key, value in domain_scores.items()},
            support_summary_cn=candidate.support_summary_cn,
            weakness_summary_cn=weakness_summary,
            source_refs_json=candidate.source_refs_json,
            risk_flags_json=risk_flags,
            role_reason_json=role_reason,
            downgrade_reason_code=None,
            input_fingerprint=candidate.input_fingerprint,
        )


class ReasonRoleClassifier:
    def classify(
        self, scored_anchor: M12DScoredPurchaseReasonAnchor
    ) -> M12DScoredPurchaseReasonAnchor:
        if (
            str(scored_anchor.establishment_status)
            != M12DReasonEstablishmentStatus.UNASSESSED.value
        ):
            return _classify_establishment_role(scored_anchor)
        if _is_ac_category(scored_anchor.product_category):
            return _classify_ac_role(scored_anchor)

        role = M12DAnchorRole.WEAK_EXPRESSION
        downgrade_reason_code = scored_anchor.downgrade_reason_code
        if (
            scored_anchor.role_reason_json.get("role_cap")
            == M12DAnchorRole.WEAK_EXPRESSION.value
        ):
            role = M12DAnchorRole.WEAK_EXPRESSION
            downgrade_reason_code = "role_cap_weak_expression"
        elif any(flag in HARD_RISK_FLAGS for flag in scored_anchor.risk_flags_json):
            role = M12DAnchorRole.RISK_DRAG
            downgrade_reason_code = "hard_risk_signal"
        elif _quality_or_business_role_cap(scored_anchor) == M12DAnchorRole.SUPPORTING:
            role = (
                M12DAnchorRole.SUPPORTING
                if scored_anchor.evidence_strength
                in {
                    M12DEvidenceStrength.STRONG.value,
                    M12DEvidenceStrength.MEDIUM.value,
                }
                else M12DAnchorRole.WEAK_EXPRESSION
            )
            downgrade_reason_code = _first_anchor_core_block_reason(scored_anchor)
        elif (
            scored_anchor.evidence_strength == M12DEvidenceStrength.STRONG.value
            and _has_scene_fit(scored_anchor)
        ):
            role = M12DAnchorRole.CORE_PAYMENT
        elif scored_anchor.evidence_strength in {
            M12DEvidenceStrength.STRONG.value,
            M12DEvidenceStrength.MEDIUM.value,
        }:
            role = M12DAnchorRole.SUPPORTING
        elif scored_anchor.evidence_strength == M12DEvidenceStrength.INSUFFICIENT.value:
            downgrade_reason_code = downgrade_reason_code or "insufficient_evidence"

        update = scored_anchor.model_copy(
            update={
                "role": role,
                "downgrade_reason_code": downgrade_reason_code,
                "role_reason_json": {
                    **scored_anchor.role_reason_json,
                    "role_decision": role.value,
                    "downgrade_reason_code": downgrade_reason_code,
                },
            }
        )
        return update


class ProfileConfidenceScorer:
    def score(
        self,
        *,
        candidate_set: M12DAnchorCandidateSet,
        context: M12DSkuPurchaseReasonContext,
        scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
    ) -> M12DProfileScoreResult:
        converged_anchors, selected_core = _converge_core_anchors(scored_anchors)
        core_payment = [anchor.anchor_code for anchor in selected_core]
        supporting = _anchor_codes(converged_anchors, M12DAnchorRole.SUPPORTING)
        weak_expression = _anchor_codes(
            converged_anchors, M12DAnchorRole.WEAK_EXPRESSION
        )
        risk_drag = _anchor_codes(converged_anchors, M12DAnchorRole.RISK_DRAG)
        risk_flags = _dedupe(
            flag for anchor in converged_anchors for flag in anchor.risk_flags_json
        )
        confidence, normalized_weights = _profile_confidence(selected_core)
        limited_confidence = _limited_confidence(converged_anchors)
        confidence_level = _confidence_level(confidence)
        profile_blocking_issues = _blocking_issues(
            context,
            scopes={M12DIssueScope.PROFILE.value},
        )
        release_blocking_issues = _blocking_issues(
            context,
            scopes={M12DIssueScope.RELEASE.value},
        )
        core_candidate_blocking_issues = _core_candidate_blocking_issues(
            converged_anchors
        )

        if profile_blocking_issues:
            status = M12DProfileStatus.FAILED
        elif core_payment:
            status = (
                M12DProfileStatus.READY
                if _uses_establishment_contract(converged_anchors)
                or confidence >= PROFILE_READY_CONFIDENCE
                else M12DProfileStatus.READY_LIMITED
            )
        elif _has_limited_business_value(converged_anchors):
            status = M12DProfileStatus.READY_LIMITED
        elif converged_anchors:
            status = M12DProfileStatus.WEAK_EXPRESSION_ONLY
        elif _required_input_missing(context):
            status = M12DProfileStatus.MISSING_INPUT
        else:
            status = M12DProfileStatus.WEAK_EXPRESSION_ONLY

        review_reasons: list[str] = []
        if profile_blocking_issues:
            review_reasons.append("profile_blocking_issue")
        if release_blocking_issues:
            review_reasons.append("release_blocking_issue")
        if core_candidate_blocking_issues:
            review_reasons.append("core_candidate_blocked_by_input_issue")

        return M12DProfileScoreResult(
            taxonomy_version=candidate_set.taxonomy_version,
            product_category=candidate_set.product_category,
            sku_code=candidate_set.sku_code,
            status=status,
            profile_confidence=_q(confidence),
            confidence_level=confidence_level,
            scored_anchors=converged_anchors,
            core_payment_anchors_json=core_payment,
            supporting_anchors_json=supporting,
            weak_expression_anchors_json=weak_expression,
            risk_drag_anchors_json=risk_drag,
            risk_flags_json=risk_flags,
            confidence_basis_json={
                "basis": "selected_established_core_anchors",
                "selected_core_anchor_codes": core_payment,
                "rank_weights": [str(weight) for weight in CORE_RANK_WEIGHTS],
                "normalized_available_weights": [
                    str(weight) for weight in normalized_weights
                ],
                "limited_confidence": str(_q(limited_confidence)),
            },
            role_downgrade_reasons_json=[
                {
                    "anchor_code": anchor.anchor_code,
                    "reason_code": anchor.downgrade_reason_code,
                }
                for anchor in converged_anchors
                if anchor.downgrade_reason_code
            ],
            review_required=bool(review_reasons),
            review_reason_json={
                "reasons": review_reasons,
                "profile_blocking_issues": profile_blocking_issues,
                "release_blocking_issues": release_blocking_issues,
                "core_candidate_blocking_issues": core_candidate_blocking_issues,
            },
            input_fingerprint=context.input_fingerprint,
        )


class PurchaseReasonProfileScoringService:
    def __init__(
        self,
        *,
        evidence_scorer: EvidenceStrengthScorer | None = None,
        role_classifier: ReasonRoleClassifier | None = None,
        profile_confidence_scorer: ProfileConfidenceScorer | None = None,
        pressure_classifier: PurchasePressureClassifier | None = None,
        establishment_scorer: ReasonEstablishmentScorer | None = None,
    ) -> None:
        self.evidence_scorer = evidence_scorer or EvidenceStrengthScorer()
        self.role_classifier = role_classifier or ReasonRoleClassifier()
        self.profile_confidence_scorer = (
            profile_confidence_scorer or ProfileConfidenceScorer()
        )
        self.pressure_classifier = pressure_classifier or PurchasePressureClassifier()
        self.establishment_scorer = establishment_scorer or ReasonEstablishmentScorer()

    def score(
        self,
        *,
        candidate_set: M12DAnchorCandidateSet,
        context: M12DSkuPurchaseReasonContext,
    ) -> M12DProfileScoreResult:
        legacy_scored_anchors = [
            (
                candidate,
                self.role_classifier.classify(
                    self.evidence_scorer.score(candidate, context)
                ),
            )
            for candidate in candidate_set.purchase_reason_candidates
        ]
        baseline_core_count = sum(
            anchor.role == M12DAnchorRole.CORE_PAYMENT.value
            for _, anchor in legacy_scored_anchors
        )
        scored_anchors = []
        for candidate, legacy_scored in legacy_scored_anchors:
            established = self.establishment_scorer.score(
                candidate=candidate,
                context=context,
                scored_anchor=legacy_scored,
                baseline_core_count=baseline_core_count,
            )
            pressured = self.pressure_classifier.classify(
                candidate=candidate,
                context=context,
                scored_anchor=established,
            )
            scored_anchors.append(self.role_classifier.classify(pressured))
        result = self.profile_confidence_scorer.score(
            candidate_set=candidate_set,
            context=context,
            scored_anchors=sorted(
                scored_anchors, key=lambda item: (item.anchor_rank, item.anchor_code)
            ),
        )
        result = self.pressure_classifier.summarize_profile(result)
        return self.establishment_scorer.summarize_profile(result)


def _domains(values: Iterable[M12DEvidenceDomain | str]) -> set[M12DEvidenceDomain]:
    result: set[M12DEvidenceDomain] = set()
    for value in values:
        try:
            result.add(M12DEvidenceDomain(str(value)))
        except ValueError:
            continue
    return result


def _risk_flags(
    candidate: M12DAnchorCandidate, context: M12DSkuPurchaseReasonContext
) -> list[str]:
    flags: list[str] = []
    candidate_keys = {match.match_key for match in candidate.evidence_matches}

    claim_value_summary = context.claim_value_profile.summary
    drag_claims = _flatten_strings(claim_value_summary.get("drag_claims_json", []))
    candidate_claim_codes = _candidate_claim_value_codes(
        candidate,
        claim_value_summary,
    )
    if drag_claims and (candidate_keys | candidate_claim_codes) & drag_claims:
        flags.append("claim_value_drag_factor")
    if _is_ac_category(context.product_category):
        flags.extend(_ac_risk_flags(candidate, context))
    if _price_value_evidence_gate_missing(candidate, context):
        flags.append("price_value_core_evidence_missing")
    return _dedupe(flags)


def _conflict_penalty(risk_flags: Sequence[str]) -> Decimal:
    penalty = Decimal("0.0000")
    if "claim_value_drag_factor" in risk_flags:
        penalty += Decimal("3.0000")
    if "ac_market_acceptance_weak_or_missing" in risk_flags:
        penalty += Decimal("1.0000")
    if "ac_scene_input_missing" in risk_flags:
        penalty += Decimal("1.0000")
    if "ac_claim_value_risk_role_dominant" in risk_flags:
        penalty += Decimal("2.0000")
    if "ac_service_signal_only" in risk_flags:
        penalty += Decimal("1.0000")
    return penalty


def _evidence_strength(
    *,
    adjusted_score: Decimal,
    domains: set[M12DEvidenceDomain],
    candidate: M12DAnchorCandidate,
    risk_flags: Sequence[str],
) -> M12DEvidenceStrength:
    if candidate.role_cap == M12DAnchorRole.WEAK_EXPRESSION:
        return M12DEvidenceStrength.WEAK
    if any(flag in HARD_RISK_FLAGS for flag in risk_flags):
        return M12DEvidenceStrength.INSUFFICIENT
    strong_domain_count = len(domains & STRONG_EVIDENCE_DOMAINS)
    if adjusted_score >= Decimal("9.0000") and strong_domain_count >= 2:
        return M12DEvidenceStrength.STRONG
    if adjusted_score >= Decimal("6.0000"):
        return M12DEvidenceStrength.MEDIUM
    if adjusted_score >= Decimal("3.0000"):
        return M12DEvidenceStrength.WEAK
    return M12DEvidenceStrength.INSUFFICIENT


def _anchor_confidence(
    evidence_strength: M12DEvidenceStrength,
    risk_flags: Sequence[str],
    quality_assessment: M12DAnchorQualityAssessment,
) -> Decimal:
    base_by_strength = {
        M12DEvidenceStrength.STRONG: Decimal("0.8500"),
        M12DEvidenceStrength.MEDIUM: Decimal("0.6500"),
        M12DEvidenceStrength.WEAK: Decimal("0.4200"),
        M12DEvidenceStrength.INSUFFICIENT: Decimal("0.2000"),
    }
    confidence = base_by_strength[evidence_strength]
    confidence -= quality_assessment.confidence_penalty
    if any(flag in HARD_RISK_FLAGS for flag in risk_flags):
        confidence = min(confidence, Decimal("0.3000"))
    if "ac_claim_value_risk_role_dominant" in risk_flags:
        confidence = min(confidence, Decimal("0.5500"))
    if quality_assessment.confidence_cap is not None:
        confidence = min(confidence, quality_assessment.confidence_cap)
    return _q(min(Decimal("0.9500"), max(Decimal("0.0500"), confidence)))


def _has_scene_fit(scored_anchor: M12DScoredPurchaseReasonAnchor) -> bool:
    domains = _domains(scored_anchor.evidence_domains_json)
    return M12DEvidenceDomain.SEMANTIC_SCENE in domains or (
        M12DEvidenceDomain.COMMENT_PERCEPTION in domains
        and M12DEvidenceDomain.MARKET_ACCEPTANCE in domains
    )


def _weakness_summary(
    candidate: M12DAnchorCandidate,
    risk_flags: Sequence[str],
    quality_assessment: M12DAnchorQualityAssessment,
) -> str:
    parts: list[str] = []
    if candidate.role_cap == M12DAnchorRole.WEAK_EXPRESSION:
        parts.append("候选只命中弱表达来源，角色封顶为弱表达。")
    if "comment_claim_contradiction" in risk_flags:
        parts.append("评论中存在与相关卖点冲突的信号。")
    if "claim_value_drag_factor" in risk_flags:
        parts.append("M12C 存在拖累或价格压力信号。")
    if "price_value_core_evidence_missing" in risk_flags:
        parts.append(
            "价格或支付类理由缺少 M12C，且评论与价格市场承接的替代证据未同时成立。"
        )
    if "ac_market_acceptance_weak_or_missing" in risk_flags:
        parts.append("AC 的市场承接弱或缺失，不能强判核心支付理由。")
    if "ac_claim_value_risk_role_dominant" in risk_flags:
        parts.append("AC 的 M12C 角色以风险或弱支撑为主，不能作为核心成交理由。")
    if "ac_service_signal_only" in risk_flags:
        parts.append("安装、服务或补贴信号只能作为辅助，不能单独构成核心成交理由。")
    for issue in quality_assessment.applied_issues:
        if issue.get("applied") and issue.get("message_cn"):
            parts.append(str(issue["message_cn"]))
    return "".join(parts)


def _converge_core_anchors(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
) -> tuple[list[M12DScoredPurchaseReasonAnchor], list[M12DScoredPurchaseReasonAnchor]]:
    core_candidates = sorted(
        (
            anchor
            for anchor in scored_anchors
            if anchor.role == M12DAnchorRole.CORE_PAYMENT.value
        ),
        key=_core_selection_sort_key,
    )
    selected_codes: list[str] = []
    selected_families: set[str] = set()
    demotions: dict[str, str] = {}
    for anchor in core_candidates:
        family_code = anchor.anchor_family_code or anchor.anchor_code
        if family_code in selected_families:
            demotions[anchor.anchor_code] = "family_dedup"
            continue
        if len(selected_codes) >= CORE_ANCHOR_LIMIT:
            demotions[anchor.anchor_code] = "core_limit"
            continue
        selected_codes.append(anchor.anchor_code)
        selected_families.add(family_code)

    selected_order = {code: index + 1 for index, code in enumerate(selected_codes)}
    converged: list[M12DScoredPurchaseReasonAnchor] = []
    for anchor in scored_anchors:
        if anchor.anchor_code in demotions:
            demotion_reason = demotions[anchor.anchor_code]
            anchor = anchor.model_copy(
                update={
                    "role": M12DAnchorRole.SUPPORTING,
                    "downgrade_reason_code": "core_limit_or_family_dedup",
                    "role_reason_json": {
                        **anchor.role_reason_json,
                        "role_decision": M12DAnchorRole.SUPPORTING.value,
                        "downgrade_reason_code": "core_limit_or_family_dedup",
                        "core_selection_demotion_reason": demotion_reason,
                    },
                }
            )
        elif anchor.anchor_code in selected_order:
            anchor = anchor.model_copy(
                update={
                    "role_reason_json": {
                        **anchor.role_reason_json,
                        "core_selection_rank": selected_order[anchor.anchor_code],
                    },
                }
            )
        converged.append(anchor)

    by_code = {anchor.anchor_code: anchor for anchor in converged}
    return converged, [by_code[code] for code in selected_codes]


def _core_selection_sort_key(anchor: M12DScoredPurchaseReasonAnchor) -> tuple[Any, ...]:
    if (
        str(anchor.establishment_status)
        != M12DReasonEstablishmentStatus.UNASSESSED.value
    ):
        validation_rank = {
            M12DUserValidationStatus.USER_VALIDATED.value: 0,
            M12DUserValidationStatus.USER_SUPPORTED.value: 1,
            M12DUserValidationStatus.MARKET_SUPPORTED.value: 2,
            M12DUserValidationStatus.NOT_OBSERVED.value: 3,
            M12DUserValidationStatus.UNASSESSED.value: 4,
        }
        return (
            validation_rank.get(str(anchor.user_validation_status), 4),
            -_decimal(anchor.establishment_score),
            -int(
                anchor.role_reason_json.get("establishment_strong_domain_count", 0) or 0
            ),
            anchor.anchor_rank,
            anchor.anchor_code,
        )
    strong_domain_count = int(
        anchor.role_reason_json.get("strong_domain_count", 0) or 0
    )
    return (
        -anchor.adjusted_evidence_score,
        -anchor.confidence,
        -strong_domain_count,
        anchor.anchor_rank,
        anchor.anchor_code,
    )


def _profile_confidence(
    selected_core: Sequence[M12DScoredPurchaseReasonAnchor],
) -> tuple[Decimal, tuple[Decimal, ...]]:
    if not selected_core:
        return Decimal("0.0000"), ()
    available_weights = CORE_RANK_WEIGHTS[: len(selected_core)]
    weight_total = _sum_decimals(available_weights)
    normalized_weights = tuple(
        _q(weight / weight_total) for weight in available_weights
    )
    confidence = _sum_decimals(
        _profile_anchor_confidence(anchor) * weight
        for anchor, weight in zip(selected_core, normalized_weights, strict=True)
    )
    return _q(
        min(Decimal("0.9500"), max(Decimal("0.0000"), confidence))
    ), normalized_weights


def _limited_confidence(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
) -> Decimal:
    return max(
        (
            _profile_anchor_confidence(anchor)
            for anchor in scored_anchors
            if anchor.role == M12DAnchorRole.SUPPORTING.value
        ),
        default=Decimal("0.0000"),
    )


def _profile_anchor_confidence(anchor: M12DScoredPurchaseReasonAnchor) -> Decimal:
    if (
        str(anchor.establishment_status)
        == M12DReasonEstablishmentStatus.UNASSESSED.value
    ):
        return anchor.confidence
    score = _decimal(anchor.establishment_score)
    return _q(
        min(Decimal("0.9500"), max(Decimal("0.0000"), score / Decimal("10.0000")))
    )


def _has_limited_business_value(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
) -> bool:
    return any(
        str(anchor.establishment_status)
        in {
            M12DReasonEstablishmentStatus.ESTABLISHED.value,
            M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
            M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value,
        }
        for anchor in scored_anchors
    ) or any(
        str(anchor.establishment_status)
        == M12DReasonEstablishmentStatus.UNASSESSED.value
        and anchor.role == M12DAnchorRole.SUPPORTING.value
        and anchor.confidence >= SUPPORTING_READY_CONFIDENCE
        for anchor in scored_anchors
    )


def _uses_establishment_contract(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
) -> bool:
    return any(
        str(anchor.establishment_status)
        != M12DReasonEstablishmentStatus.UNASSESSED.value
        for anchor in scored_anchors
    )


def _confidence_level(confidence: Decimal) -> Core3ConfidenceLevel:
    if confidence >= Decimal("0.7500"):
        return Core3ConfidenceLevel.HIGH
    if confidence >= Decimal("0.5000"):
        return Core3ConfidenceLevel.MEDIUM
    if confidence >= Decimal("0.2500"):
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def _required_input_missing(context: M12DSkuPurchaseReasonContext) -> bool:
    if any(
        str(quality.availability) == M12DInputAvailability.MISSING.value
        for quality in context.input_quality_json.values()
    ):
        return True
    statuses = (
        context.param_profile_status,
        context.claim_fact_status,
        context.comment_profile_status,
        context.market_profile_status,
        context.semantic_profile_status,
        context.semantic_market_status,
        context.claim_value_status,
    )
    return any(str(status) == M12DInputStatus.MISSING.value for status in statuses)


def _blocking_issues(
    context: M12DSkuPurchaseReasonContext,
    *,
    scopes: set[str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for module_code, quality in sorted(context.input_quality_json.items()):
        for issue in quality.issues:
            if (
                str(issue.severity) != M12DIssueSeverity.BLOCKING.value
                or str(issue.scope) not in scopes
            ):
                continue
            issues.append(
                {
                    "module_code": module_code,
                    "issue_code": str(issue.code),
                    "scope": str(issue.scope),
                }
            )
    return issues


def _core_candidate_blocking_issues(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for anchor in scored_anchors:
        if not _blocking_changed_core_decision(anchor):
            continue
        for issue in anchor.role_reason_json.get("applied_quality_issues", []):
            if not isinstance(issue, Mapping):
                continue
            if str(issue.get("severity")) != M12DIssueSeverity.BLOCKING.value:
                continue
            issues.append(
                {
                    "anchor_code": anchor.anchor_code,
                    "module_code": str(issue.get("module_code") or "unknown"),
                    "issue_code": str(issue.get("issue_code") or "unknown"),
                }
            )
    return issues


def _blocking_changed_core_decision(anchor: M12DScoredPurchaseReasonAnchor) -> bool:
    applied_issues = anchor.role_reason_json.get("applied_quality_issues", [])
    has_blocking = any(
        isinstance(issue, Mapping)
        and bool(issue.get("applied"))
        and str(issue.get("severity")) == M12DIssueSeverity.BLOCKING.value
        for issue in applied_issues
    )
    if not has_blocking:
        return False
    if anchor.role_reason_json.get("role_cap") == M12DAnchorRole.WEAK_EXPRESSION.value:
        return False
    if (
        anchor.evidence_strength != M12DEvidenceStrength.STRONG.value
        or not _has_scene_fit(anchor)
    ):
        return False
    business_block_flags = {
        "price_value_core_evidence_missing",
        "ac_claim_value_risk_role_dominant",
        "ac_service_signal_only",
        *HARD_RISK_FLAGS,
    }
    return not bool(set(anchor.risk_flags_json) & business_block_flags)


def _anchor_codes(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor], role: M12DAnchorRole
) -> list[str]:
    return [
        anchor.anchor_code for anchor in scored_anchors if anchor.role == role.value
    ]


def _flatten_strings(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        result: set[str] = set()
        for key, nested in value.items():
            result.add(str(key))
            result.update(_flatten_strings(nested))
        return result
    if isinstance(value, list | tuple | set):
        result: set[str] = set()
        for item in value:
            result.update(_flatten_strings(item))
        return result
    return {str(value)}


def _classify_establishment_role(
    scored_anchor: M12DScoredPurchaseReasonAnchor,
) -> M12DScoredPurchaseReasonAnchor:
    status = str(scored_anchor.establishment_status)
    blocking_reasons = set(scored_anchor.core_ineligible_reasons_json)
    downgrade_reason_code: str | None = None
    semantic_role = "weak_expression"

    if status == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value:
        role = M12DAnchorRole.SUPPORTING
        semantic_role = "proposition"
        downgrade_reason_code = "proposition_only_not_user_reason"
    elif status in {
        M12DReasonEstablishmentStatus.ESTABLISHED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
    }:
        semantic_role = "established_reason"
        if scored_anchor.core_eligible is True:
            role = M12DAnchorRole.CORE_PAYMENT
        else:
            role = M12DAnchorRole.SUPPORTING
            downgrade_reason_code = "established_supporting_not_core_eligible"
    elif blocking_reasons & {"objective_falsification", "evidence_misalignment"}:
        role = M12DAnchorRole.RISK_DRAG
        semantic_role = "rejected"
        downgrade_reason_code = "objective_rejection"
    else:
        role = M12DAnchorRole.WEAK_EXPRESSION
        downgrade_reason_code = "positive_establishment_insufficient"

    return scored_anchor.model_copy(
        update={
            "role": role,
            "downgrade_reason_code": downgrade_reason_code,
            "role_reason_json": {
                **scored_anchor.role_reason_json,
                "role_decision_basis": "reason_establishment_status",
                "semantic_role": semantic_role,
                "role_decision": role.value,
                "downgrade_reason_code": downgrade_reason_code,
                "pressure_affects_role": False,
            },
        }
    )


def _classify_ac_role(
    scored_anchor: M12DScoredPurchaseReasonAnchor,
) -> M12DScoredPurchaseReasonAnchor:
    role = M12DAnchorRole.WEAK_EXPRESSION
    downgrade_reason_code = scored_anchor.downgrade_reason_code
    flags = set(scored_anchor.risk_flags_json)
    if (
        scored_anchor.role_reason_json.get("role_cap")
        == M12DAnchorRole.WEAK_EXPRESSION.value
    ):
        role = M12DAnchorRole.WEAK_EXPRESSION
        downgrade_reason_code = "role_cap_weak_expression"
    elif any(flag in HARD_RISK_FLAGS for flag in flags):
        role = M12DAnchorRole.RISK_DRAG
        downgrade_reason_code = "hard_risk_signal"
    elif "ac_service_signal_only" in flags:
        role = M12DAnchorRole.WEAK_EXPRESSION
        downgrade_reason_code = "ac_service_signal_only"
    elif _has_ac_core_payment_gate(scored_anchor):
        role = M12DAnchorRole.CORE_PAYMENT
    elif scored_anchor.evidence_strength in {
        M12DEvidenceStrength.STRONG.value,
        M12DEvidenceStrength.MEDIUM.value,
    }:
        role = M12DAnchorRole.SUPPORTING
        downgrade_reason_code = downgrade_reason_code or _first_ac_core_block_reason(
            flags
        )
    elif scored_anchor.evidence_strength == M12DEvidenceStrength.INSUFFICIENT.value:
        downgrade_reason_code = downgrade_reason_code or "insufficient_evidence"
    else:
        downgrade_reason_code = downgrade_reason_code or _first_ac_core_block_reason(
            flags
        )

    return scored_anchor.model_copy(
        update={
            "role": role,
            "downgrade_reason_code": downgrade_reason_code,
            "role_reason_json": {
                **scored_anchor.role_reason_json,
                "role_decision": role.value,
                "downgrade_reason_code": downgrade_reason_code,
            },
        }
    )


def _has_ac_core_payment_gate(scored_anchor: M12DScoredPurchaseReasonAnchor) -> bool:
    if scored_anchor.evidence_strength != M12DEvidenceStrength.STRONG.value:
        return False
    flags = set(scored_anchor.risk_flags_json)
    if flags & AC_CORE_BLOCK_FLAGS:
        return False
    if any(flag in HARD_RISK_FLAGS for flag in flags):
        return False
    domains = _domains(scored_anchor.evidence_domains_json)
    if len(domains) < 2:
        return False
    if not domains & STRONG_EVIDENCE_DOMAINS:
        return False
    return _has_scene_fit(scored_anchor)


def _first_ac_core_block_reason(flags: set[str]) -> str | None:
    for reason in (
        "anchor_quality_blocking",
        "price_value_core_evidence_missing",
        "ac_claim_value_risk_role_dominant",
        "ac_service_signal_only",
    ):
        if reason in flags:
            return reason
    return None


def _ac_risk_flags(
    candidate: M12DAnchorCandidate, context: M12DSkuPurchaseReasonContext
) -> list[str]:
    flags: list[str] = []
    domains = _scoring_domains(candidate, context)
    claim_value_roles = _candidate_claim_value_roles(
        candidate,
        context.claim_value_profile.summary,
    )
    if _is_price_value_reason(candidate) and _is_ac_market_weak_or_missing(context):
        flags.append("ac_market_acceptance_weak_or_missing")
    if (
        M12DEvidenceDomain.CLAIM_VALUE in domains
        and claim_value_roles & AC_CLAIM_VALUE_RISK_OR_WEAK_ROLES
        and not claim_value_roles & AC_CLAIM_VALUE_POSITIVE_ROLES
    ):
        flags.append("ac_claim_value_risk_role_dominant")
    if domains and domains <= {
        M12DEvidenceDomain.SERVICE_SIGNAL,
        M12DEvidenceDomain.CLAIM_POSITION,
    }:
        flags.append("ac_service_signal_only")
    return flags


def _price_value_evidence_gate_missing(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> bool:
    if not _is_price_value_reason(candidate):
        return False
    domains = _scoring_domains(candidate, context)
    if M12DEvidenceDomain.CLAIM_VALUE in domains:
        return False
    return (
        not {
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
        }
        <= domains
    )


def _is_price_value_reason(candidate: M12DAnchorCandidate) -> bool:
    category = "AC" if _is_ac_category(candidate.product_category) else "TV"
    return candidate.anchor_code in PRICE_VALUE_REASON_CODES[category]


def _scoring_domains(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> set[M12DEvidenceDomain]:
    domains = _domains(candidate.evidence_domains_json)
    role_map = context.claim_value_profile.summary.get("claim_value_roles")
    if (
        M12DEvidenceDomain.CLAIM_VALUE in domains
        and isinstance(role_map, Mapping)
        and not _candidate_claim_value_roles(
            candidate, context.claim_value_profile.summary
        )
    ):
        domains.remove(M12DEvidenceDomain.CLAIM_VALUE)
    return domains


def _candidate_claim_value_roles(
    candidate: M12DAnchorCandidate,
    summary: Mapping[str, Any],
) -> set[str]:
    anchor_role_map = summary.get("anchor_claim_value_roles")
    if isinstance(anchor_role_map, Mapping):
        candidate_role_map = anchor_role_map.get(candidate.anchor_code)
        if isinstance(candidate_role_map, Mapping):
            return {
                str(role)
                for role_value in candidate_role_map.values()
                for role in _flatten_strings(role_value)
                if str(role)
            }
        return set()
    candidate_tokens = {
        str(token)
        for match in candidate.evidence_matches
        if str(match.module_code) == "M12C"
        for token in (match.match_key, match.match_value)
        if str(token)
    }
    role_value = summary.get("claim_value_roles")
    if isinstance(role_value, Mapping):
        return {
            str(role)
            for claim_code, role in role_value.items()
            if str(claim_code) in candidate_tokens and str(role)
        }
    return _claim_value_roles(summary) & candidate_tokens


def _candidate_claim_value_codes(
    candidate: M12DAnchorCandidate,
    summary: Mapping[str, Any],
) -> set[str]:
    anchor_role_map = summary.get("anchor_claim_value_roles")
    if not isinstance(anchor_role_map, Mapping):
        return set()
    candidate_role_map = anchor_role_map.get(candidate.anchor_code)
    if not isinstance(candidate_role_map, Mapping):
        return set()
    return {str(claim_code) for claim_code in candidate_role_map if str(claim_code)}


def _quality_or_business_role_cap(
    scored_anchor: M12DScoredPurchaseReasonAnchor,
) -> M12DAnchorRole | None:
    quality_cap = scored_anchor.role_reason_json.get("quality_role_cap")
    if quality_cap:
        return M12DAnchorRole(str(quality_cap))
    if set(scored_anchor.risk_flags_json) & ANCHOR_CORE_BLOCK_FLAGS:
        return M12DAnchorRole.SUPPORTING
    return None


def _first_anchor_core_block_reason(
    scored_anchor: M12DScoredPurchaseReasonAnchor,
) -> str:
    flags = set(scored_anchor.risk_flags_json)
    for reason in ("anchor_quality_blocking", "price_value_core_evidence_missing"):
        if reason in flags:
            return reason
    return "quality_role_cap"


def _claim_value_roles(summary: Mapping[str, Any]) -> set[str]:
    roles: set[str] = set()
    for key in (
        "claim_value_role",
        "claim_value_roles",
        "claim_value_role_counts",
        "claim_value_role_counts_json",
        "role_counts",
        "role_counts_json",
        "value_role_counts_json",
    ):
        roles.update(_flatten_strings(summary.get(key)))
    return {role for role in roles if role and not role.isdigit()}


def _is_ac_market_weak_or_missing(context: M12DSkuPurchaseReasonContext) -> bool:
    if _is_missing_or_unknown(context.market_profile_status):
        return True
    market_summary = context.market_profile.summary
    if str(market_summary.get("sample_status") or "").lower() in {
        "unknown",
        "insufficient",
        "sample_insufficient",
    }:
        return True
    percentile = str(market_summary.get("same_pool_volume_percentile") or "").lower()
    if percentile in {"none", "unknown", "very_low", "low", "mid_low"}:
        return True
    sales_volume = market_summary.get("sales_volume_total")
    return sales_volume is not None and _decimal(sales_volume) <= Decimal("0.0000")


def _is_missing_or_partial(status: Any) -> bool:
    return str(status) in {
        M12DInputStatus.MISSING.value,
        M12DInputStatus.PARTIAL.value,
        M12DInputStatus.UNKNOWN.value,
    }


def _is_missing_or_unknown(status: Any) -> bool:
    return str(status) in {
        M12DInputStatus.MISSING.value,
        M12DInputStatus.UNKNOWN.value,
    }


def _is_ac_category(value: Any) -> bool:
    category = str(value).upper()
    return category == "AC" or category.endswith(".AC")


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _sum_decimals(values: Iterable[Decimal]) -> Decimal:
    total = Decimal("0.0000")
    for value in values:
        total += value
    return total


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
