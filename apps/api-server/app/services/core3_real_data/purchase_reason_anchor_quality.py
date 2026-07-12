"""Anchor-scoped quality policy for M12D evidence scoring."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from app.services.core3_real_data.constants import (
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DIssueSeverity,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DSkuPurchaseReasonContext,
)


@dataclass(frozen=True)
class M12DAnchorIssuePolicy:
    affected_domain: M12DEvidenceDomain | None = None
    score_penalty: Decimal = Decimal("0.0000")
    confidence_penalty: Decimal = Decimal("0.0000")
    confidence_cap: Decimal | None = None
    role_cap: M12DAnchorRole | None = None
    hard_risk: bool = False


@dataclass(frozen=True)
class M12DAnchorQualityAssessment:
    score_penalty: Decimal = Decimal("0.0000")
    confidence_penalty: Decimal = Decimal("0.0000")
    confidence_cap: Decimal | None = None
    role_cap: M12DAnchorRole | None = None
    hard_risk: bool = False
    risk_flags: tuple[str, ...] = ()
    applied_issues: tuple[dict[str, Any], ...] = ()


_EXACT_POLICIES: Mapping[str, M12DAnchorIssuePolicy] = {
    "m03b_true_param_conflict": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.PARAM_FACT,
        confidence_cap=Decimal("0.3000"),
        role_cap=M12DAnchorRole.SUPPORTING,
    ),
    "m03b_param_review_required": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.PARAM_FACT,
        score_penalty=Decimal("1.0000"),
        confidence_penalty=Decimal("0.0500"),
    ),
    "comment_claim_contradiction": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.COMMENT_PERCEPTION,
        score_penalty=Decimal("2.0000"),
        confidence_penalty=Decimal("0.1000"),
    ),
    "comment_negative_dominates": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.COMMENT_PERCEPTION,
        score_penalty=Decimal("2.0000"),
        confidence_penalty=Decimal("0.1000"),
        confidence_cap=Decimal("0.3000"),
        hard_risk=True,
    ),
    "market_sample_insufficient": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.MARKET_ACCEPTANCE,
        score_penalty=Decimal("1.0000"),
        confidence_penalty=Decimal("0.0500"),
    ),
    "m09c_primary_relation_unavailable": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.SEMANTIC_SCENE,
        score_penalty=Decimal("1.0000"),
        confidence_penalty=Decimal("0.0500"),
    ),
    "m10c_primary_relation_unavailable": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.SEMANTIC_SCENE,
        score_penalty=Decimal("1.0000"),
        confidence_penalty=Decimal("0.0500"),
    ),
    "m11c_primary_relation_unavailable": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.SEMANTIC_SCENE,
        score_penalty=Decimal("1.0000"),
        confidence_penalty=Decimal("0.0500"),
    ),
    "m11d_relation_confidence_low": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.MARKET_ACCEPTANCE,
        score_penalty=Decimal("1.0000"),
        confidence_penalty=Decimal("0.0500"),
    ),
    "m12c_related_claim_negative": M12DAnchorIssuePolicy(
        affected_domain=M12DEvidenceDomain.CLAIM_VALUE,
        score_penalty=Decimal("2.0000"),
        confidence_penalty=Decimal("0.1000"),
    ),
}


def assess_anchor_input_quality(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> M12DAnchorQualityAssessment:
    """Apply only issues explicitly scoped to the current anchor."""

    domain_score_penalties: dict[str, Decimal] = {}
    unbound_score_penalty = Decimal("0.0000")
    warning_confidence_penalty = Decimal("0.0000")
    confidence_cap: Decimal | None = None
    role_cap: M12DAnchorRole | None = None
    hard_risk = False
    risk_flags: list[str] = []
    applied_issues: list[dict[str, Any]] = []

    for module_code, quality in context.input_quality_json.items():
        for issue in quality.issues:
            affected_anchor_codes = {str(code) for code in issue.affected_anchor_codes}
            if not affected_anchor_codes or candidate.anchor_code not in affected_anchor_codes:
                continue
            severity = str(issue.severity)
            policy = _policy_for_issue(str(issue.code), severity)
            applied = severity == M12DIssueSeverity.BLOCKING.value or _has_effect(policy)
            applied_issues.append(
                {
                    "module_code": module_code,
                    "issue_code": str(issue.code),
                    "severity": severity,
                    "scope": str(issue.scope),
                    "affected_domain": (
                        policy.affected_domain.value if policy.affected_domain is not None else None
                    ),
                    "score_penalty": str(policy.score_penalty),
                    "confidence_penalty": str(policy.confidence_penalty),
                    "confidence_cap": str(policy.confidence_cap) if policy.confidence_cap is not None else None,
                    "role_cap": policy.role_cap.value if policy.role_cap is not None else None,
                    "applied": applied,
                    "message_cn": issue.message_cn,
                }
            )
            if not applied:
                continue
            if policy.affected_domain is not None:
                domain_code = policy.affected_domain.value
                domain_score_penalties[domain_code] = max(
                    domain_score_penalties.get(domain_code, Decimal("0.0000")),
                    policy.score_penalty,
                )
            else:
                unbound_score_penalty += policy.score_penalty
            warning_confidence_penalty += policy.confidence_penalty
            confidence_cap = _lower_cap(confidence_cap, policy.confidence_cap)
            role_cap = _stricter_role_cap(role_cap, policy.role_cap)
            hard_risk = hard_risk or policy.hard_risk
            if severity == M12DIssueSeverity.BLOCKING.value:
                risk_flags.extend((str(issue.code), "anchor_quality_blocking"))
            elif policy.hard_risk or policy.score_penalty or policy.confidence_penalty:
                risk_flags.append(str(issue.code))

    return M12DAnchorQualityAssessment(
        score_penalty=sum(domain_score_penalties.values(), unbound_score_penalty),
        confidence_penalty=min(Decimal("0.1500"), warning_confidence_penalty),
        confidence_cap=confidence_cap,
        role_cap=role_cap,
        hard_risk=hard_risk,
        risk_flags=tuple(_dedupe(risk_flags)),
        applied_issues=tuple(applied_issues),
    )


def _policy_for_issue(code: str, severity: str) -> M12DAnchorIssuePolicy:
    if severity == M12DIssueSeverity.INFO.value:
        return M12DAnchorIssuePolicy()
    if code in _EXACT_POLICIES:
        return _EXACT_POLICIES[code]
    if code.startswith(("market_pool_", "price_band_sample_", "size_pool_")):
        return M12DAnchorIssuePolicy(
            affected_domain=M12DEvidenceDomain.MARKET_ACCEPTANCE,
            score_penalty=Decimal("1.0000"),
            confidence_penalty=Decimal("0.0500"),
        )
    if severity == M12DIssueSeverity.BLOCKING.value:
        return M12DAnchorIssuePolicy(
            confidence_cap=Decimal("0.3000"),
            role_cap=M12DAnchorRole.SUPPORTING,
        )
    return M12DAnchorIssuePolicy()


def _has_effect(policy: M12DAnchorIssuePolicy) -> bool:
    return bool(
        policy.score_penalty
        or policy.confidence_penalty
        or policy.confidence_cap is not None
        or policy.role_cap is not None
        or policy.hard_risk
    )


def _lower_cap(current: Decimal | None, candidate: Decimal | None) -> Decimal | None:
    if candidate is None:
        return current
    return candidate if current is None else min(current, candidate)


def _stricter_role_cap(
    current: M12DAnchorRole | None,
    candidate: M12DAnchorRole | None,
) -> M12DAnchorRole | None:
    order = {
        M12DAnchorRole.CORE_PAYMENT: 3,
        M12DAnchorRole.SUPPORTING: 2,
        M12DAnchorRole.WEAK_EXPRESSION: 1,
        M12DAnchorRole.RISK_DRAG: 0,
    }
    if candidate is None:
        return current
    if current is None or order[candidate] < order[current]:
        return candidate
    return current


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
