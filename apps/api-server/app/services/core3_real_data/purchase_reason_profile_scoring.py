"""Evidence scoring and role classification for M12D purchase reasons."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    Core3ConfidenceLevel,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputStatus,
    M12DProfileStatus,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DAnchorCandidateSet,
    M12DProfileScoreResult,
    M12DScoredPurchaseReasonAnchor,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
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
    "ac_missing_m12c_core_cap",
    "ac_scene_input_missing",
    "ac_market_acceptance_weak_or_missing",
    "ac_claim_value_risk_role_dominant",
    "ac_service_signal_only",
}


class EvidenceStrengthScorer:
    def score(
        self,
        candidate: M12DAnchorCandidate,
        context: M12DSkuPurchaseReasonContext,
    ) -> M12DScoredPurchaseReasonAnchor:
        domains = _domains(candidate.evidence_domains_json)
        domain_scores = {
            domain.value: DOMAIN_MAX_SCORES[domain]
            for domain in domains
            if domain in DOMAIN_MAX_SCORES
        }
        raw_score = _sum_decimals(domain_scores.values())
        risk_flags = _risk_flags(candidate, context)
        conflict_penalty = _conflict_penalty(risk_flags)
        adjusted_score = max(Decimal("0.0000"), raw_score - conflict_penalty)
        evidence_strength = _evidence_strength(
            adjusted_score=adjusted_score,
            domains=domains,
            candidate=candidate,
            risk_flags=risk_flags,
        )
        confidence = _anchor_confidence(evidence_strength, risk_flags, context)
        role_reason = {
            "raw_evidence_score": _q(raw_score),
            "conflict_penalty": _q(conflict_penalty),
            "adjusted_evidence_score": _q(adjusted_score),
            "matched_domain_count": len(domains),
            "strong_domain_count": len(domains & STRONG_EVIDENCE_DOMAINS),
            "role_cap": str(candidate.role_cap) if candidate.role_cap else None,
            "role_cap_reasons": candidate.role_cap_reasons,
        }
        if _is_ac_category(candidate.product_category):
            role_reason.update(
                {
                    "claim_value_status": str(context.claim_value_status),
                    "semantic_profile_status": str(context.semantic_profile_status),
                    "semantic_market_status": str(context.semantic_market_status),
                    "market_profile_status": str(context.market_profile_status),
                    "claim_value_roles": sorted(_claim_value_roles(context.claim_value_profile.summary)),
                    "ac_core_block_flags": [flag for flag in risk_flags if flag in AC_CORE_BLOCK_FLAGS],
                }
            )
        weakness_summary = _weakness_summary(candidate, risk_flags, context)
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
    def classify(self, scored_anchor: M12DScoredPurchaseReasonAnchor) -> M12DScoredPurchaseReasonAnchor:
        if _is_ac_category(scored_anchor.product_category):
            return _classify_ac_role(scored_anchor)

        role = M12DAnchorRole.WEAK_EXPRESSION
        downgrade_reason_code = scored_anchor.downgrade_reason_code
        if scored_anchor.role_reason_json.get("role_cap") == M12DAnchorRole.WEAK_EXPRESSION.value:
            role = M12DAnchorRole.WEAK_EXPRESSION
            downgrade_reason_code = "role_cap_weak_expression"
        elif any(flag in HARD_RISK_FLAGS for flag in scored_anchor.risk_flags_json):
            role = M12DAnchorRole.RISK_DRAG
            downgrade_reason_code = "hard_risk_signal"
        elif scored_anchor.evidence_strength == M12DEvidenceStrength.STRONG.value and _has_scene_fit(scored_anchor):
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
        core_payment = _anchor_codes(scored_anchors, M12DAnchorRole.CORE_PAYMENT)
        supporting = _anchor_codes(scored_anchors, M12DAnchorRole.SUPPORTING)
        weak_expression = _anchor_codes(scored_anchors, M12DAnchorRole.WEAK_EXPRESSION)
        risk_drag = _anchor_codes(scored_anchors, M12DAnchorRole.RISK_DRAG)
        risk_flags = _dedupe(flag for anchor in scored_anchors for flag in anchor.risk_flags_json)
        confidence = _profile_confidence(scored_anchors, context)
        confidence_level = _confidence_level(confidence)
        missing_input = _missing_input_count(context)
        if not scored_anchors and missing_input:
            status = M12DProfileStatus.MISSING_INPUT
        elif risk_drag:
            status = M12DProfileStatus.REVIEW_REQUIRED
        elif core_payment:
            status = M12DProfileStatus.READY if confidence >= Decimal("0.7000") else M12DProfileStatus.READY_DEGRADED
        elif weak_expression and not supporting:
            status = M12DProfileStatus.WEAK_EXPRESSION_ONLY
        else:
            status = M12DProfileStatus.READY_DEGRADED

        review_reasons: list[str] = []
        if risk_drag:
            review_reasons.append("risk_drag_anchor_present")
        if not core_payment:
            review_reasons.append("core_payment_missing")
        if confidence < Decimal("0.5000"):
            review_reasons.append("low_profile_confidence")
        if missing_input:
            review_reasons.append("missing_or_partial_inputs")

        return M12DProfileScoreResult(
            taxonomy_version=candidate_set.taxonomy_version,
            product_category=candidate_set.product_category,
            sku_code=candidate_set.sku_code,
            status=status,
            profile_confidence=_q(confidence),
            confidence_level=confidence_level,
            scored_anchors=list(scored_anchors),
            core_payment_anchors_json=core_payment,
            supporting_anchors_json=supporting,
            weak_expression_anchors_json=weak_expression,
            risk_drag_anchors_json=risk_drag,
            risk_flags_json=risk_flags,
            role_downgrade_reasons_json=[
                {"anchor_code": anchor.anchor_code, "reason_code": anchor.downgrade_reason_code}
                for anchor in scored_anchors
                if anchor.downgrade_reason_code
            ],
            review_required=bool(review_reasons),
            review_reason_json={"reasons": review_reasons},
            input_fingerprint=context.input_fingerprint,
        )


class PurchaseReasonProfileScoringService:
    def __init__(
        self,
        *,
        evidence_scorer: EvidenceStrengthScorer | None = None,
        role_classifier: ReasonRoleClassifier | None = None,
        profile_confidence_scorer: ProfileConfidenceScorer | None = None,
    ) -> None:
        self.evidence_scorer = evidence_scorer or EvidenceStrengthScorer()
        self.role_classifier = role_classifier or ReasonRoleClassifier()
        self.profile_confidence_scorer = profile_confidence_scorer or ProfileConfidenceScorer()

    def score(
        self,
        *,
        candidate_set: M12DAnchorCandidateSet,
        context: M12DSkuPurchaseReasonContext,
    ) -> M12DProfileScoreResult:
        scored_anchors = [
            self.role_classifier.classify(self.evidence_scorer.score(candidate, context))
            for candidate in candidate_set.purchase_reason_candidates
        ]
        return self.profile_confidence_scorer.score(
            candidate_set=candidate_set,
            context=context,
            scored_anchors=sorted(scored_anchors, key=lambda item: (item.anchor_rank, item.anchor_code)),
        )


def _domains(values: Iterable[M12DEvidenceDomain | str]) -> set[M12DEvidenceDomain]:
    result: set[M12DEvidenceDomain] = set()
    for value in values:
        try:
            result.add(M12DEvidenceDomain(str(value)))
        except ValueError:
            continue
    return result


def _risk_flags(candidate: M12DAnchorCandidate, context: M12DSkuPurchaseReasonContext) -> list[str]:
    flags: list[str] = []
    comment_summary = context.comment_profile.summary
    positive = _decimal(comment_summary.get("positive_sentence_count"))
    negative = _decimal(comment_summary.get("negative_sentence_count"))
    if negative >= Decimal("3") and negative >= positive:
        flags.append("comment_negative_dominates")
    contradicted_claims = {str(value) for value in comment_summary.get("contradicted_claim_codes", [])}
    candidate_keys = {match.match_key for match in candidate.evidence_matches}
    if contradicted_claims & candidate_keys:
        flags.append("comment_claim_contradiction")

    claim_value_summary = context.claim_value_profile.summary
    drag_claims = _flatten_strings(claim_value_summary.get("drag_claims_json", []))
    if drag_claims and (candidate_keys & drag_claims or "drag_factor" in drag_claims):
        flags.append("claim_value_drag_factor")
    if _is_ac_category(context.product_category):
        flags.extend(_ac_risk_flags(candidate, context))

    market_summary = context.market_profile.summary
    if str(market_summary.get("sample_status") or "").lower() in {"unknown", "insufficient", "sample_insufficient"}:
        flags.append("market_sample_insufficient")
    input_statuses = [
        context.param_profile_status,
        context.claim_fact_status,
        context.comment_profile_status,
        context.market_profile_status,
        context.semantic_profile_status,
        context.semantic_market_status,
        context.claim_value_status,
    ]
    if any(str(status) in {M12DInputStatus.MISSING.value, M12DInputStatus.PARTIAL.value} for status in input_statuses):
        flags.append("missing_or_partial_inputs")
    return _dedupe(flags)


def _conflict_penalty(risk_flags: Sequence[str]) -> Decimal:
    penalty = Decimal("0.0000")
    if "comment_negative_dominates" in risk_flags:
        penalty += Decimal("2.0000")
    if "comment_claim_contradiction" in risk_flags:
        penalty += Decimal("2.0000")
    if "claim_value_drag_factor" in risk_flags:
        penalty += Decimal("3.0000")
    if "market_sample_insufficient" in risk_flags:
        penalty += Decimal("1.0000")
    if "missing_or_partial_inputs" in risk_flags:
        penalty += Decimal("1.0000")
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
    context: M12DSkuPurchaseReasonContext,
) -> Decimal:
    base_by_strength = {
        M12DEvidenceStrength.STRONG: Decimal("0.8500"),
        M12DEvidenceStrength.MEDIUM: Decimal("0.6500"),
        M12DEvidenceStrength.WEAK: Decimal("0.4200"),
        M12DEvidenceStrength.INSUFFICIENT: Decimal("0.2000"),
    }
    confidence = base_by_strength[evidence_strength]
    if "missing_or_partial_inputs" in risk_flags:
        confidence -= Decimal("0.1000")
    if "market_sample_insufficient" in risk_flags:
        confidence -= Decimal("0.0500")
    if "comment_claim_contradiction" in risk_flags:
        confidence -= Decimal("0.1000")
    if any(flag in HARD_RISK_FLAGS for flag in risk_flags):
        confidence = min(confidence, Decimal("0.3000"))
    if context.claim_value_status == M12DInputStatus.MISSING.value:
        confidence = min(confidence, Decimal("0.6500"))
    if "ac_missing_m12c_core_cap" in risk_flags:
        confidence = min(confidence, Decimal("0.6000"))
    if "ac_claim_value_risk_role_dominant" in risk_flags:
        confidence = min(confidence, Decimal("0.5500"))
    return _q(min(Decimal("0.9500"), max(Decimal("0.0500"), confidence)))


def _has_scene_fit(scored_anchor: M12DScoredPurchaseReasonAnchor) -> bool:
    domains = _domains(scored_anchor.evidence_domains_json)
    return M12DEvidenceDomain.SEMANTIC_SCENE in domains or (
        M12DEvidenceDomain.COMMENT_PERCEPTION in domains and M12DEvidenceDomain.MARKET_ACCEPTANCE in domains
    )


def _weakness_summary(
    candidate: M12DAnchorCandidate,
    risk_flags: Sequence[str],
    context: M12DSkuPurchaseReasonContext,
) -> str:
    parts: list[str] = []
    if candidate.role_cap == M12DAnchorRole.WEAK_EXPRESSION:
        parts.append("候选只命中弱表达来源，角色封顶为弱表达。")
    if "comment_negative_dominates" in risk_flags:
        parts.append("评论负向信号占优，需要降级或复核。")
    if "comment_claim_contradiction" in risk_flags:
        parts.append("评论中存在与相关卖点冲突的信号。")
    if "claim_value_drag_factor" in risk_flags:
        parts.append("M12C 存在拖累或价格压力信号。")
    if "ac_missing_m12c_core_cap" in risk_flags:
        parts.append("AC 的 M12C 缺失，只能作为降级成交理由，不能强判核心支付理由。")
    if "ac_scene_input_missing" in risk_flags:
        parts.append("AC 的场景/人群或语义市场输入缺失，核心成交理由需降级。")
    if "ac_market_acceptance_weak_or_missing" in risk_flags:
        parts.append("AC 的市场承接弱或缺失，不能强判核心支付理由。")
    if "ac_claim_value_risk_role_dominant" in risk_flags:
        parts.append("AC 的 M12C 角色以风险或弱支撑为主，不能作为核心成交理由。")
    if "ac_service_signal_only" in risk_flags:
        parts.append("安装、服务或补贴信号只能作为辅助，不能单独构成核心成交理由。")
    if context.claim_value_status == M12DInputStatus.MISSING.value:
        parts.append("M12C 缺失，不能强判支付价值。")
    return "".join(parts)


def _profile_confidence(
    scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor],
    context: M12DSkuPurchaseReasonContext,
) -> Decimal:
    if not scored_anchors:
        return Decimal("0.1500")
    top_confidences = sorted((anchor.confidence for anchor in scored_anchors), reverse=True)[:3]
    confidence = _sum_decimals(top_confidences) / Decimal(len(top_confidences))
    missing_count = _missing_input_count(context)
    if missing_count:
        confidence -= min(Decimal("0.2500"), Decimal("0.0500") * Decimal(missing_count))
    return _q(min(Decimal("0.9500"), max(Decimal("0.0500"), confidence)))


def _confidence_level(confidence: Decimal) -> Core3ConfidenceLevel:
    if confidence >= Decimal("0.7500"):
        return Core3ConfidenceLevel.HIGH
    if confidence >= Decimal("0.5000"):
        return Core3ConfidenceLevel.MEDIUM
    if confidence >= Decimal("0.2500"):
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def _missing_input_count(context: M12DSkuPurchaseReasonContext) -> int:
    statuses = [
        context.param_profile_status,
        context.claim_fact_status,
        context.comment_profile_status,
        context.market_profile_status,
        context.semantic_profile_status,
        context.semantic_market_status,
        context.claim_value_status,
    ]
    return sum(
        1
        for status in statuses
        if str(status) in {M12DInputStatus.MISSING.value, M12DInputStatus.PARTIAL.value, M12DInputStatus.UNKNOWN.value}
    )


def _anchor_codes(scored_anchors: Sequence[M12DScoredPurchaseReasonAnchor], role: M12DAnchorRole) -> list[str]:
    return [anchor.anchor_code for anchor in scored_anchors if anchor.role == role.value]


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


def _classify_ac_role(scored_anchor: M12DScoredPurchaseReasonAnchor) -> M12DScoredPurchaseReasonAnchor:
    role = M12DAnchorRole.WEAK_EXPRESSION
    downgrade_reason_code = scored_anchor.downgrade_reason_code
    flags = set(scored_anchor.risk_flags_json)
    if scored_anchor.role_reason_json.get("role_cap") == M12DAnchorRole.WEAK_EXPRESSION.value:
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
        downgrade_reason_code = downgrade_reason_code or _first_ac_core_block_reason(flags)
    elif scored_anchor.evidence_strength == M12DEvidenceStrength.INSUFFICIENT.value:
        downgrade_reason_code = downgrade_reason_code or "insufficient_evidence"
    else:
        downgrade_reason_code = downgrade_reason_code or _first_ac_core_block_reason(flags)

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
        "ac_missing_m12c_core_cap",
        "ac_scene_input_missing",
        "ac_market_acceptance_weak_or_missing",
        "ac_claim_value_risk_role_dominant",
        "ac_service_signal_only",
    ):
        if reason in flags:
            return reason
    return None


def _ac_risk_flags(candidate: M12DAnchorCandidate, context: M12DSkuPurchaseReasonContext) -> list[str]:
    flags: list[str] = []
    domains = _domains(candidate.evidence_domains_json)
    claim_value_roles = _claim_value_roles(context.claim_value_profile.summary)
    if _is_missing_or_unknown(context.claim_value_status):
        flags.append("ac_missing_m12c_core_cap")
    if _is_missing_or_unknown(context.semantic_profile_status) or _is_missing_or_unknown(context.semantic_market_status):
        flags.append("ac_scene_input_missing")
    if _is_ac_market_weak_or_missing(context):
        flags.append("ac_market_acceptance_weak_or_missing")
    if "drag_factor" in claim_value_roles:
        flags.append("claim_value_drag_factor")
    if claim_value_roles & AC_CLAIM_VALUE_RISK_OR_WEAK_ROLES and not claim_value_roles & AC_CLAIM_VALUE_POSITIVE_ROLES:
        flags.append("ac_claim_value_risk_role_dominant")
    if domains and domains <= {M12DEvidenceDomain.SERVICE_SIGNAL, M12DEvidenceDomain.CLAIM_POSITION}:
        flags.append("ac_service_signal_only")
    return flags


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
    if str(market_summary.get("sample_status") or "").lower() in {"unknown", "insufficient", "sample_insufficient"}:
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
