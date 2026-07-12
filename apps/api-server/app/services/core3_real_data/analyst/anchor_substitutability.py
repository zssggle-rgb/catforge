"""M12D-driven value anchor substitutability for competitor pairs."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Literal

from app.services.core3_real_data.analyst.purchase_reason_profile_reader import (
    PurchaseReasonProfileUsageDecision,
    decide_candidate_m12d_usage,
    decide_target_m12d_usage,
)
from app.services.core3_real_data.constants import (
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DReasonEstablishmentStatus,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamAnchorContract,
    M12DDownstreamProfileContract,
    M12DDownstreamReadContract,
)

AnchorMatchType = Literal[
    "exact_substitute",
    "adjacent_substitute",
    "candidate_stronger",
    "target_only",
    "candidate_only",
    "proposition_only",
    "weak_expression",
    "unsupported",
]

AnchorSubstitutabilityLevel = Literal[
    "strong", "medium", "partial", "insufficient", "blocked"
]

CORE_ROLE = M12DAnchorRole.CORE_PAYMENT.value
SUPPORTING_ROLE = M12DAnchorRole.SUPPORTING.value
WEAK_ROLE = M12DAnchorRole.WEAK_EXPRESSION.value
RISK_ROLE = M12DAnchorRole.RISK_DRAG.value

EVIDENCE_STRENGTH_SCORE = {
    M12DEvidenceStrength.INSUFFICIENT.value: Decimal("0"),
    M12DEvidenceStrength.WEAK.value: Decimal("1"),
    M12DEvidenceStrength.MEDIUM.value: Decimal("2"),
    M12DEvidenceStrength.STRONG.value: Decimal("3"),
}


@dataclass(frozen=True)
class AnchorSubstitutabilityBreakdown:
    target_core_anchor_coverage: Decimal = Decimal("0")
    evidence_parity: Decimal = Decimal("0")
    candidate_relative_advantage: Decimal = Decimal("0")
    scenario_task_audience_fit: Decimal = Decimal("0")
    market_comment_validation: Decimal = Decimal("0")
    penalties: Decimal = Decimal("0")

    @property
    def total_before_penalty(self) -> Decimal:
        return (
            self.target_core_anchor_coverage
            + self.evidence_parity
            + self.candidate_relative_advantage
            + self.scenario_task_audience_fit
            + self.market_comment_validation
        )


@dataclass(frozen=True)
class AnchorMatchDetail:
    target_anchor_code: str
    target_anchor_cn: str
    candidate_anchor_code: str | None
    candidate_anchor_cn: str | None
    match_type: AnchorMatchType
    score: Decimal
    target_role: str
    candidate_role: str | None
    target_evidence_strength: str
    candidate_evidence_strength: str | None
    evidence_comparison_cn: str


@dataclass(frozen=True)
class AnchorSubstitutabilityResult:
    anchor_substitutability_score: int
    anchor_substitutability_score_raw: Decimal
    anchor_substitutability_level: AnchorSubstitutabilityLevel
    score_breakdown: AnchorSubstitutabilityBreakdown
    shared_core_anchors: list[str] = field(default_factory=list)
    target_only_anchors: list[str] = field(default_factory=list)
    candidate_stronger_anchors: list[str] = field(default_factory=list)
    weak_expression_anchors: list[str] = field(default_factory=list)
    candidate_only_anchors: list[str] = field(default_factory=list)
    proposition_only_anchors: list[str] = field(default_factory=list)
    risk_drag_anchors: list[str] = field(default_factory=list)
    match_details: list[AnchorMatchDetail] = field(default_factory=list)
    anchor_substitution_summary_cn: str = ""
    target_usage_decision: PurchaseReasonProfileUsageDecision | None = None
    candidate_usage_decision: PurchaseReasonProfileUsageDecision | None = None
    pair_scoring_allowed: bool = True
    primary_direct_eligible: bool = True
    requires_review: bool = False
    gate_reasons: list[str] = field(default_factory=list)

    @property
    def normalized_score(self) -> Decimal:
        return (Decimal(self.anchor_substitutability_score) / Decimal("15")).quantize(
            Decimal("0.0001")
        )

    def to_legacy_value_anchor(self) -> dict[str, Any]:
        return {
            "score": self.normalized_score,
            "shared_anchors": list(self.shared_core_anchors),
            "target_stronger_anchors": list(self.target_only_anchors),
            "candidate_stronger_anchors": list(self.candidate_stronger_anchors),
            "anchor_substitutability_score": self.anchor_substitutability_score,
            "anchor_substitutability_level": self.anchor_substitutability_level,
            "weak_expression_anchors": list(self.weak_expression_anchors),
            "proposition_only_anchors": list(self.proposition_only_anchors),
            "match_details": [
                {
                    "target_anchor_cn": detail.target_anchor_cn,
                    "candidate_anchor_cn": detail.candidate_anchor_cn,
                    "match_type": detail.match_type,
                    "score": _decimal_to_number(detail.score),
                    "evidence_comparison_cn": detail.evidence_comparison_cn,
                }
                for detail in self.match_details
            ],
            "anchor_substitution_summary_cn": self.anchor_substitution_summary_cn,
            "pair_scoring_allowed": self.pair_scoring_allowed,
            "primary_direct_eligible": self.primary_direct_eligible,
            "candidate_top3_eligible": (
                self.candidate_usage_decision.top3_eligible
                if self.candidate_usage_decision is not None
                else True
            ),
            "requires_review": self.requires_review,
            "gate_reasons": list(self.gate_reasons),
        }


class ValueAnchorMatcher:
    """Compare target and candidate M12D purchase-reason profiles at pair level."""

    def match(
        self,
        *,
        target_contract: M12DDownstreamReadContract,
        candidate_contract: M12DDownstreamReadContract,
    ) -> AnchorSubstitutabilityResult:
        target_decision = decide_target_m12d_usage(target_contract)
        candidate_decision = decide_candidate_m12d_usage(candidate_contract)
        if not target_decision.pair_scoring_allowed:
            return _blocked_result(
                target_decision=target_decision,
                candidate_decision=candidate_decision,
                summary_cn=target_decision.message_cn,
            )
        if not candidate_decision.pair_scoring_allowed:
            target_profile = target_contract.profile
            return _blocked_result(
                target_decision=target_decision,
                candidate_decision=candidate_decision,
                target_only_anchors=_core_anchor_names(target_profile),
                summary_cn=candidate_decision.message_cn,
            )

        target_profile = target_contract.profile
        candidate_profile = candidate_contract.profile
        if target_profile is None or candidate_profile is None:
            return _blocked_result(
                target_decision=target_decision,
                candidate_decision=candidate_decision,
                summary_cn="目标或候选 SKU 成交理由画像缺失，不能计算关键价值锚点可替代性。",
            )

        target_core_anchors = [
            anchor
            for anchor in _anchors_by_codes(
                target_profile, target_profile.core_payment_anchors
            )
            if _is_established_reason(anchor)
        ]
        if not target_core_anchors:
            return _insufficient_result(
                target_decision=target_decision,
                candidate_decision=candidate_decision,
                summary_cn="目标 SKU 没有可消费的核心成交理由锚点，关键价值锚点可替代性不足。",
            )

        candidate_anchor_index = _anchor_index(candidate_profile)
        candidate_family_index = _anchor_family_index(candidate_profile)
        detail_scores: list[_DetailScore] = []
        shared_core_anchors: list[str] = []
        target_only_anchors: list[str] = []
        candidate_stronger_anchors: list[str] = []
        weak_expression_anchors: list[str] = []
        proposition_only_anchors: list[str] = []
        risk_drag_anchors: list[str] = []

        for target_anchor in target_core_anchors:
            detail_score = self._match_target_anchor(
                target_anchor=target_anchor,
                candidate_anchor_index=candidate_anchor_index,
                candidate_family_index=candidate_family_index,
            )
            detail_scores.append(detail_score)
            detail = detail_score.detail
            if detail.match_type in {
                "exact_substitute",
                "adjacent_substitute",
                "candidate_stronger",
            }:
                shared_core_anchors.append(detail.target_anchor_cn)
            elif detail.match_type == "target_only":
                target_only_anchors.append(detail.target_anchor_cn)
            elif detail.match_type == "weak_expression":
                weak_expression_anchors.append(detail.target_anchor_cn)
            elif detail.match_type == "proposition_only":
                proposition_only_anchors.append(detail.target_anchor_cn)
            elif detail.match_type == "unsupported":
                risk_drag_anchors.append(detail.target_anchor_cn)
            if detail.match_type == "candidate_stronger" and detail.candidate_anchor_cn:
                candidate_stronger_anchors.append(detail.candidate_anchor_cn)

        matched_candidate_codes = {
            score.detail.candidate_anchor_code
            for score in detail_scores
            if score.detail.candidate_anchor_code
        }
        candidate_only_anchors = [
            anchor.anchor_cn
            for anchor in _anchors_by_codes(
                candidate_profile, candidate_profile.core_payment_anchors
            )
            if anchor.anchor_code not in matched_candidate_codes
            and _is_established_reason(anchor)
        ]

        breakdown = _score_breakdown(
            detail_scores,
            target_decision=target_decision,
            candidate_decision=candidate_decision,
        )
        raw_score = max(
            Decimal("0"),
            min(Decimal("15"), breakdown.total_before_penalty - breakdown.penalties),
        )
        score = _round_points(raw_score)
        level = _level(
            score,
            blocked=not target_decision.strong_ranking_allowed
            or not candidate_decision.strong_ranking_allowed,
        )
        primary_direct_eligible = (
            score >= 7
            and any(
                item.detail.match_type in {"exact_substitute", "candidate_stronger"}
                for item in detail_scores
            )
            and candidate_decision.strong_ranking_allowed
        )
        gate_reasons = _gate_reasons(
            target_decision=target_decision,
            candidate_decision=candidate_decision,
            primary_direct_eligible=primary_direct_eligible,
            detail_scores=detail_scores,
        )

        return AnchorSubstitutabilityResult(
            anchor_substitutability_score=score,
            anchor_substitutability_score_raw=raw_score.quantize(Decimal("0.0001")),
            anchor_substitutability_level=level,
            score_breakdown=breakdown,
            shared_core_anchors=_dedupe(shared_core_anchors),
            target_only_anchors=_dedupe(target_only_anchors),
            candidate_stronger_anchors=_dedupe(candidate_stronger_anchors),
            weak_expression_anchors=_dedupe(weak_expression_anchors),
            candidate_only_anchors=_dedupe(candidate_only_anchors),
            proposition_only_anchors=_dedupe(proposition_only_anchors),
            risk_drag_anchors=_dedupe(risk_drag_anchors),
            match_details=[item.detail for item in detail_scores],
            anchor_substitution_summary_cn=_summary_cn(
                score=score,
                shared_core_anchors=shared_core_anchors,
                target_only_anchors=target_only_anchors,
                candidate_stronger_anchors=candidate_stronger_anchors,
                weak_expression_anchors=weak_expression_anchors,
                proposition_only_anchors=proposition_only_anchors,
                requires_review=target_decision.requires_review
                or candidate_decision.requires_review,
            ),
            target_usage_decision=target_decision,
            candidate_usage_decision=candidate_decision,
            pair_scoring_allowed=True,
            primary_direct_eligible=primary_direct_eligible,
            requires_review=target_decision.requires_review
            or candidate_decision.requires_review,
            gate_reasons=gate_reasons,
        )

    def _match_target_anchor(
        self,
        *,
        target_anchor: M12DDownstreamAnchorContract,
        candidate_anchor_index: dict[str, M12DDownstreamAnchorContract],
        candidate_family_index: dict[str, list[M12DDownstreamAnchorContract]],
    ) -> "_DetailScore":
        candidate_anchor = candidate_anchor_index.get(target_anchor.anchor_code)
        if candidate_anchor is None and target_anchor.anchor_family_code:
            candidate_anchor = _best_family_anchor(
                candidate_family_index.get(target_anchor.anchor_family_code) or []
            )

        if candidate_anchor is None:
            return _detail_score(
                target_anchor=target_anchor,
                candidate_anchor=None,
                match_type="target_only",
                coverage_weight=Decimal("0"),
                advantage_weight=Decimal("0"),
                evidence_comparison_cn="候选没有覆盖该目标核心成交理由。",
            )

        candidate_role = _value(candidate_anchor.role)
        establishment_status = _value(candidate_anchor.establishment_status)
        same_code = candidate_anchor.anchor_code == target_anchor.anchor_code
        if establishment_status == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value:
            return _detail_score(
                target_anchor=target_anchor,
                candidate_anchor=candidate_anchor,
                match_type="proposition_only",
                coverage_weight=Decimal("0"),
                advantage_weight=Decimal("0"),
                evidence_comparison_cn="候选希望传达该产品价值，但尚未观察到用户承接，不能计为购买理由替代。",
            )
        if not _is_established_reason(candidate_anchor):
            return _detail_score(
                target_anchor=target_anchor,
                candidate_anchor=candidate_anchor,
                match_type="unsupported",
                coverage_weight=Decimal("0"),
                advantage_weight=Decimal("0"),
                evidence_comparison_cn="候选在该锚点上的购买理由未成立，不能作为正向替代。",
            )
        if candidate_role == WEAK_ROLE:
            return _detail_score(
                target_anchor=target_anchor,
                candidate_anchor=candidate_anchor,
                match_type="weak_expression",
                coverage_weight=Decimal("0"),
                advantage_weight=Decimal("0"),
                evidence_comparison_cn="候选只是在弱表达层命中该锚点，不能推高可替代性。",
            )
        if candidate_role == RISK_ROLE:
            return _detail_score(
                target_anchor=target_anchor,
                candidate_anchor=candidate_anchor,
                match_type="unsupported",
                coverage_weight=Decimal("0"),
                advantage_weight=Decimal("0"),
                evidence_comparison_cn="候选在该锚点上存在风险或拖累信号，不能作为正向替代。",
            )

        coverage_weight = _coverage_weight(
            same_code=same_code, candidate_role=candidate_role
        )
        candidate_is_stronger = _candidate_is_stronger(target_anchor, candidate_anchor)
        if candidate_is_stronger and candidate_role == CORE_ROLE:
            match_type: AnchorMatchType = "candidate_stronger"
        elif same_code and candidate_role == CORE_ROLE:
            match_type = "exact_substitute"
        else:
            match_type = "adjacent_substitute"

        return _detail_score(
            target_anchor=target_anchor,
            candidate_anchor=candidate_anchor,
            match_type=match_type,
            coverage_weight=coverage_weight,
            advantage_weight=_advantage_weight(
                match_type, candidate_role=candidate_role
            ),
            evidence_comparison_cn=_evidence_comparison_cn(
                target_anchor, candidate_anchor, match_type=match_type
            ),
        )


@dataclass(frozen=True)
class _DetailScore:
    detail: AnchorMatchDetail
    coverage_weight: Decimal
    parity_weight: Decimal
    advantage_weight: Decimal
    scenario_fit_weight: Decimal
    market_comment_weight: Decimal
    penalty: Decimal


def _detail_score(
    *,
    target_anchor: M12DDownstreamAnchorContract,
    candidate_anchor: M12DDownstreamAnchorContract | None,
    match_type: AnchorMatchType,
    coverage_weight: Decimal,
    advantage_weight: Decimal,
    evidence_comparison_cn: str,
) -> _DetailScore:
    penalty = Decimal("0")
    if match_type == "weak_expression":
        penalty += Decimal("0.75")
    elif match_type == "unsupported":
        penalty += Decimal("1.25")
    candidate_role = (
        _value(candidate_anchor.role) if candidate_anchor is not None else None
    )
    detail = AnchorMatchDetail(
        target_anchor_code=target_anchor.anchor_code,
        target_anchor_cn=target_anchor.anchor_cn,
        candidate_anchor_code=candidate_anchor.anchor_code
        if candidate_anchor is not None
        else None,
        candidate_anchor_cn=candidate_anchor.anchor_cn
        if candidate_anchor is not None
        else None,
        match_type=match_type,
        score=(coverage_weight * Decimal("5")).quantize(Decimal("0.0001")),
        target_role=_value(target_anchor.role),
        candidate_role=candidate_role,
        target_evidence_strength=_value(target_anchor.evidence_strength),
        candidate_evidence_strength=_value(candidate_anchor.evidence_strength)
        if candidate_anchor is not None
        else None,
        evidence_comparison_cn=evidence_comparison_cn,
    )
    return _DetailScore(
        detail=detail,
        coverage_weight=coverage_weight,
        parity_weight=_parity_weight(
            target_anchor, candidate_anchor, coverage_weight=coverage_weight
        ),
        advantage_weight=advantage_weight,
        scenario_fit_weight=_scenario_fit_weight(
            target_anchor, candidate_anchor, coverage_weight=coverage_weight
        ),
        market_comment_weight=_market_comment_weight(
            candidate_anchor, coverage_weight=coverage_weight
        ),
        penalty=penalty,
    )


def _score_breakdown(
    detail_scores: list[_DetailScore],
    *,
    target_decision: PurchaseReasonProfileUsageDecision,
    candidate_decision: PurchaseReasonProfileUsageDecision,
) -> AnchorSubstitutabilityBreakdown:
    denominator = Decimal(max(len(detail_scores), 1))
    target_core_anchor_coverage = (
        sum((item.coverage_weight for item in detail_scores), Decimal("0"))
        / denominator
        * Decimal("5")
    )
    evidence_parity = (
        sum((item.parity_weight for item in detail_scores), Decimal("0"))
        / denominator
        * Decimal("4")
    )
    candidate_relative_advantage = (
        sum((item.advantage_weight for item in detail_scores), Decimal("0"))
        / denominator
        * Decimal("3")
    )
    scenario_task_audience_fit = (
        sum((item.scenario_fit_weight for item in detail_scores), Decimal("0"))
        / denominator
        * Decimal("2")
    )
    market_comment_validation = (
        sum((item.market_comment_weight for item in detail_scores), Decimal("0"))
        / denominator
        * Decimal("1")
    )
    penalties = sum((item.penalty for item in detail_scores), Decimal("0"))
    if target_decision.confidence_state == "degraded":
        penalties += Decimal("1.00")
    if candidate_decision.confidence_state == "degraded":
        penalties += Decimal("1.00")
    return AnchorSubstitutabilityBreakdown(
        target_core_anchor_coverage=target_core_anchor_coverage.quantize(
            Decimal("0.0001")
        ),
        evidence_parity=evidence_parity.quantize(Decimal("0.0001")),
        candidate_relative_advantage=candidate_relative_advantage.quantize(
            Decimal("0.0001")
        ),
        scenario_task_audience_fit=scenario_task_audience_fit.quantize(
            Decimal("0.0001")
        ),
        market_comment_validation=market_comment_validation.quantize(Decimal("0.0001")),
        penalties=penalties.quantize(Decimal("0.0001")),
    )


def _coverage_weight(*, same_code: bool, candidate_role: str) -> Decimal:
    if same_code and candidate_role == CORE_ROLE:
        return Decimal("1.00")
    if same_code and candidate_role == SUPPORTING_ROLE:
        return Decimal("0.55")
    if candidate_role == CORE_ROLE:
        return Decimal("0.70")
    if candidate_role == SUPPORTING_ROLE:
        return Decimal("0.35")
    return Decimal("0")


def _parity_weight(
    target_anchor: M12DDownstreamAnchorContract,
    candidate_anchor: M12DDownstreamAnchorContract | None,
    *,
    coverage_weight: Decimal,
) -> Decimal:
    if candidate_anchor is None or coverage_weight <= 0:
        return Decimal("0")
    target_strength = max(_strength_score(target_anchor), Decimal("1"))
    candidate_strength = _strength_score(candidate_anchor)
    strength_ratio = min(Decimal("1.00"), candidate_strength / target_strength)
    target_confidence = max(_decimal(target_anchor.confidence), Decimal("0.0001"))
    candidate_confidence = _decimal(candidate_anchor.confidence)
    confidence_ratio = min(Decimal("1.00"), candidate_confidence / target_confidence)
    return (
        coverage_weight
        * (strength_ratio * Decimal("0.70") + confidence_ratio * Decimal("0.30"))
    ).quantize(Decimal("0.0001"))


def _advantage_weight(match_type: AnchorMatchType, *, candidate_role: str) -> Decimal:
    if match_type == "candidate_stronger":
        return Decimal("1.00")
    if match_type == "exact_substitute" and candidate_role == CORE_ROLE:
        return Decimal("0.50")
    if match_type == "adjacent_substitute" and candidate_role == CORE_ROLE:
        return Decimal("0.35")
    if match_type == "adjacent_substitute" and candidate_role == SUPPORTING_ROLE:
        return Decimal("0.15")
    return Decimal("0")


def _scenario_fit_weight(
    target_anchor: M12DDownstreamAnchorContract,
    candidate_anchor: M12DDownstreamAnchorContract | None,
    *,
    coverage_weight: Decimal,
) -> Decimal:
    if candidate_anchor is None or coverage_weight <= 0:
        return Decimal("0")
    target_domains = _domains(target_anchor)
    candidate_domains = _domains(candidate_anchor)
    semantic_domain = M12DEvidenceDomain.SEMANTIC_SCENE.value
    if semantic_domain in target_domains and semantic_domain in candidate_domains:
        return coverage_weight
    if semantic_domain in target_domains or semantic_domain in candidate_domains:
        return coverage_weight * Decimal("0.50")
    return Decimal("0")


def _market_comment_weight(
    candidate_anchor: M12DDownstreamAnchorContract | None,
    *,
    coverage_weight: Decimal,
) -> Decimal:
    if candidate_anchor is None or coverage_weight <= 0:
        return Decimal("0")
    candidate_domains = _domains(candidate_anchor)
    validation_domains = {
        M12DEvidenceDomain.COMMENT_PERCEPTION.value,
        M12DEvidenceDomain.MARKET_ACCEPTANCE.value,
    }
    if validation_domains <= candidate_domains:
        return coverage_weight
    if candidate_domains & validation_domains:
        return coverage_weight * Decimal("0.70")
    if M12DEvidenceDomain.CLAIM_VALUE.value in candidate_domains:
        return coverage_weight * Decimal("0.40")
    return Decimal("0")


def _candidate_is_stronger(
    target_anchor: M12DDownstreamAnchorContract,
    candidate_anchor: M12DDownstreamAnchorContract,
) -> bool:
    return _strength_score(candidate_anchor) > _strength_score(
        target_anchor
    ) or _decimal(candidate_anchor.confidence) >= _decimal(
        target_anchor.confidence
    ) + Decimal("0.1000")


def _evidence_comparison_cn(
    target_anchor: M12DDownstreamAnchorContract,
    candidate_anchor: M12DDownstreamAnchorContract,
    *,
    match_type: AnchorMatchType,
) -> str:
    target_strength = _strength_cn(target_anchor.evidence_strength)
    candidate_strength = _strength_cn(candidate_anchor.evidence_strength)
    if match_type == "candidate_stronger":
        return f"候选在该锚点上证据更强或置信度更高：目标为{target_strength}，候选为{candidate_strength}。"
    if match_type == "exact_substitute":
        return f"候选覆盖同一核心成交理由，证据强度为{candidate_strength}，可与目标的{target_strength}形成同类替代。"
    return f"候选覆盖同族或辅助成交理由，证据强度为{candidate_strength}，只能作为相邻替代。"


def _blocked_result(
    *,
    target_decision: PurchaseReasonProfileUsageDecision,
    candidate_decision: PurchaseReasonProfileUsageDecision,
    summary_cn: str,
    target_only_anchors: list[str] | None = None,
) -> AnchorSubstitutabilityResult:
    return AnchorSubstitutabilityResult(
        anchor_substitutability_score=0,
        anchor_substitutability_score_raw=Decimal("0.0000"),
        anchor_substitutability_level="blocked",
        score_breakdown=AnchorSubstitutabilityBreakdown(),
        target_only_anchors=list(target_only_anchors or []),
        anchor_substitution_summary_cn=summary_cn,
        target_usage_decision=target_decision,
        candidate_usage_decision=candidate_decision,
        pair_scoring_allowed=False,
        primary_direct_eligible=False,
        requires_review=True,
        gate_reasons=_dedupe(
            list(target_decision.reasons) + list(candidate_decision.reasons)
        ),
    )


def _insufficient_result(
    *,
    target_decision: PurchaseReasonProfileUsageDecision,
    candidate_decision: PurchaseReasonProfileUsageDecision,
    summary_cn: str,
) -> AnchorSubstitutabilityResult:
    return AnchorSubstitutabilityResult(
        anchor_substitutability_score=0,
        anchor_substitutability_score_raw=Decimal("0.0000"),
        anchor_substitutability_level="insufficient",
        score_breakdown=AnchorSubstitutabilityBreakdown(),
        anchor_substitution_summary_cn=summary_cn,
        target_usage_decision=target_decision,
        candidate_usage_decision=candidate_decision,
        pair_scoring_allowed=True,
        primary_direct_eligible=False,
        requires_review=True,
        gate_reasons=["target_core_payment_missing"],
    )


def _summary_cn(
    *,
    score: int,
    shared_core_anchors: list[str],
    target_only_anchors: list[str],
    candidate_stronger_anchors: list[str],
    weak_expression_anchors: list[str],
    proposition_only_anchors: list[str],
    requires_review: bool,
) -> str:
    level_text = (
        "强" if score >= 13 else "中" if score >= 10 else "弱" if score >= 7 else "不足"
    )
    parts = [f"关键价值锚点可替代性为{level_text}，得分{score}/15。"]
    if shared_core_anchors:
        parts.append(f"候选覆盖目标核心成交理由：{_join_cn(shared_core_anchors[:5])}。")
    if candidate_stronger_anchors:
        parts.append(f"候选更强锚点：{_join_cn(candidate_stronger_anchors[:4])}。")
    if target_only_anchors:
        parts.append(f"目标独有或候选未覆盖：{_join_cn(target_only_anchors[:4])}。")
    if weak_expression_anchors:
        parts.append(f"弱表达不计强替代：{_join_cn(weak_expression_anchors[:4])}。")
    if proposition_only_anchors:
        parts.append(
            f"候选希望传达但尚未观察到用户承接：{_join_cn(proposition_only_anchors[:4])}，不计购买理由替代。"
        )
    if requires_review:
        parts.append("当前 M12D 画像存在降级或复核标记，排序结论必须同步降置信度。")
    return "".join(parts)


def _level(score: int, *, blocked: bool) -> AnchorSubstitutabilityLevel:
    if blocked and score == 0:
        return "blocked"
    if score >= 13:
        return "strong"
    if score >= 10:
        return "medium"
    if score >= 7:
        return "partial"
    return "insufficient"


def _gate_reasons(
    *,
    target_decision: PurchaseReasonProfileUsageDecision,
    candidate_decision: PurchaseReasonProfileUsageDecision,
    primary_direct_eligible: bool,
    detail_scores: list[_DetailScore],
) -> list[str]:
    reasons = list(target_decision.reasons) + list(candidate_decision.reasons)
    if target_decision.confidence_state == "degraded":
        reasons.append("target_m12d_degraded")
    if candidate_decision.confidence_state == "degraded":
        reasons.append("candidate_m12d_degraded")
    if not any(
        item.detail.match_type in {"exact_substitute", "candidate_stronger"}
        for item in detail_scores
    ):
        reasons.append("target_core_anchor_not_exactly_covered")
    if not primary_direct_eligible:
        reasons.append("not_primary_direct_eligible")
    return _dedupe(reasons)


def _anchors_by_codes(
    profile: M12DDownstreamProfileContract, codes: list[str]
) -> list[M12DDownstreamAnchorContract]:
    index = _anchor_index(profile)
    return [index[code] for code in codes if code in index]


def _core_anchor_names(profile: M12DDownstreamProfileContract | None) -> list[str]:
    if profile is None:
        return []
    return [
        anchor.anchor_cn
        for anchor in _anchors_by_codes(profile, profile.core_payment_anchors)
        if _is_established_reason(anchor)
    ]


def _anchor_index(
    profile: M12DDownstreamProfileContract,
) -> dict[str, M12DDownstreamAnchorContract]:
    return {anchor.anchor_code: anchor for anchor in profile.anchors}


def _anchor_family_index(
    profile: M12DDownstreamProfileContract,
) -> dict[str, list[M12DDownstreamAnchorContract]]:
    result: dict[str, list[M12DDownstreamAnchorContract]] = {}
    for anchor in profile.anchors:
        if anchor.anchor_family_code:
            result.setdefault(anchor.anchor_family_code, []).append(anchor)
    return result


def _best_family_anchor(
    anchors: list[M12DDownstreamAnchorContract],
) -> M12DDownstreamAnchorContract | None:
    usable = [
        anchor
        for anchor in anchors
        if _value(anchor.role) in {CORE_ROLE, SUPPORTING_ROLE, WEAK_ROLE, RISK_ROLE}
    ]
    if not usable:
        return None
    return sorted(
        usable,
        key=lambda anchor: (
            _establishment_rank(anchor),
            _role_rank(_value(anchor.role)),
            _strength_score(anchor),
            _decimal(anchor.confidence),
            -anchor.anchor_rank,
        ),
        reverse=True,
    )[0]


def _is_established_reason(anchor: M12DDownstreamAnchorContract) -> bool:
    return _value(anchor.establishment_status) in {
        M12DReasonEstablishmentStatus.UNASSESSED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
    }


def _establishment_rank(anchor: M12DDownstreamAnchorContract) -> Decimal:
    status = _value(anchor.establishment_status)
    if status in {
        M12DReasonEstablishmentStatus.ESTABLISHED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
    }:
        return Decimal("3")
    if status == M12DReasonEstablishmentStatus.UNASSESSED.value:
        return Decimal("2")
    if status == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value:
        return Decimal("1")
    return Decimal("0")


def _role_rank(role: str) -> Decimal:
    return {
        CORE_ROLE: Decimal("4"),
        SUPPORTING_ROLE: Decimal("3"),
        WEAK_ROLE: Decimal("1"),
        RISK_ROLE: Decimal("0"),
    }.get(role, Decimal("0"))


def _strength_score(anchor: M12DDownstreamAnchorContract) -> Decimal:
    return EVIDENCE_STRENGTH_SCORE.get(_value(anchor.evidence_strength), Decimal("0"))


def _domains(anchor: M12DDownstreamAnchorContract) -> set[str]:
    return {_value(domain) for domain in anchor.evidence_domains}


def _strength_cn(value: Any) -> str:
    return {
        M12DEvidenceStrength.STRONG.value: "强证据",
        M12DEvidenceStrength.MEDIUM.value: "中证据",
        M12DEvidenceStrength.WEAK.value: "弱证据",
        M12DEvidenceStrength.INSUFFICIENT.value: "证据不足",
    }.get(_value(value), str(value))


def _round_points(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _join_cn(values: list[str]) -> str:
    return "、".join(_dedupe(values))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _decimal_to_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


__all__ = [
    "AnchorMatchDetail",
    "AnchorSubstitutabilityBreakdown",
    "AnchorSubstitutabilityResult",
    "ValueAnchorMatcher",
]
