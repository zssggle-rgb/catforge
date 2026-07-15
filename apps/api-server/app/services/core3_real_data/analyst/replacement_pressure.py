"""Pair-level replacement pressure scoring for competitor analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from app.services.core3_real_data.analyst.anchor_substitutability import (
    AnchorSubstitutabilityResult,
)

PressureType = Literal[
    "value_substitution",
    "price_suppression",
    "configuration_benchmark",
    "scenario_mindshare",
    "brand_ecosystem",
    "downtrade_diversion",
    "uptrade_alternative",
    "low_pressure_review",
]

PressureLevel = Literal["high", "medium", "low", "insufficient"]

PRESSURE_TYPE_CN: dict[PressureType, str] = {
    "value_substitution": "价值替代压力",
    "price_suppression": "价格压制压力",
    "configuration_benchmark": "配置标杆压力",
    "scenario_mindshare": "场景心智压力",
    "brand_ecosystem": "品牌/生态压力",
    "downtrade_diversion": "下探分流压力",
    "uptrade_alternative": "上探替代压力",
    "low_pressure_review": "低替代压力复核",
}

REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION = (
    "replacement_pressure_classifier_v1"
)
REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION = (
    "replacement_pressure_score_10_v1"
)


@dataclass(frozen=True)
class ReplacementPressureBreakdown:
    purchase_pool_pressure: Decimal = Decimal("0")
    purchase_reason_pressure: Decimal = Decimal("0")
    price_or_config_impact: Decimal = Decimal("0")
    scenario_mindshare_shift: Decimal = Decimal("0")
    market_diversion_validation: Decimal = Decimal("0")
    confidence_adjustment: Decimal = Decimal("0")

    @property
    def total_before_cap(self) -> Decimal:
        return (
            self.purchase_pool_pressure
            + self.purchase_reason_pressure
            + self.price_or_config_impact
            + self.scenario_mindshare_shift
            + self.market_diversion_validation
            + self.confidence_adjustment
        )


@dataclass(frozen=True)
class PressureTypeCandidate:
    pressure_type: PressureType
    pressure_type_cn: str
    score: Decimal
    reason_cn: str


@dataclass(frozen=True)
class ReplacementPressureInput:
    purchase_pool_level: str
    purchase_pool_score: Decimal | int | float | str | None
    anchor_substitutability: AnchorSubstitutabilityResult
    price_gap_pct_to_target: Decimal | int | float | str | None = None
    weighted_overlap: dict[str, Decimal | int | float | str | None] = field(
        default_factory=dict
    )
    market_validation_level: str | None = None
    candidate_config_advantage_score: Decimal | int | float | str | None = None
    candidate_scenario_mindshare_score: Decimal | int | float | str | None = None
    brand_ecosystem_score: Decimal | int | float | str | None = None
    risk_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReplacementPressureResult:
    replacement_pressure_score: int
    replacement_pressure_score_raw: Decimal
    replacement_pressure_level: PressureLevel
    score_breakdown: ReplacementPressureBreakdown
    primary_pressure_type: PressureType
    primary_pressure_type_cn: str
    auxiliary_pressure_types: list[PressureTypeCandidate] = field(default_factory=list)
    strong_pressure_allowed: bool = False
    requires_review: bool = False
    reason_cn: str = ""
    risk_notes: list[str] = field(default_factory=list)

    @property
    def normalized_score(self) -> Decimal:
        return (Decimal(self.replacement_pressure_score) / Decimal("10")).quantize(
            Decimal("0.0001")
        )

    def to_legacy_replacement_pressure(self) -> dict[str, Any]:
        return {
            "type": self.primary_pressure_type,
            "type_cn": self.primary_pressure_type_cn,
            "score": self.normalized_score,
            "replacement_pressure_score": self.replacement_pressure_score,
            "replacement_pressure_level": self.replacement_pressure_level,
            "score_breakdown": {
                "purchase_pool_pressure": _decimal_to_number(
                    self.score_breakdown.purchase_pool_pressure
                ),
                "purchase_reason_pressure": _decimal_to_number(
                    self.score_breakdown.purchase_reason_pressure
                ),
                "price_or_config_impact": _decimal_to_number(
                    self.score_breakdown.price_or_config_impact
                ),
                "scenario_mindshare_shift": _decimal_to_number(
                    self.score_breakdown.scenario_mindshare_shift
                ),
                "market_diversion_validation": _decimal_to_number(
                    self.score_breakdown.market_diversion_validation
                ),
                "confidence_adjustment": _decimal_to_number(
                    self.score_breakdown.confidence_adjustment
                ),
            },
            "auxiliary_pressure_types": [
                {
                    "type": item.pressure_type,
                    "type_cn": item.pressure_type_cn,
                    "score": _decimal_to_number(item.score),
                    "reason_cn": item.reason_cn,
                }
                for item in self.auxiliary_pressure_types
            ],
            "strong_pressure_allowed": self.strong_pressure_allowed,
            "requires_review": self.requires_review,
            "reason_cn": self.reason_cn,
        }


class ReplacementPressureClassifier:
    """Score how a candidate can pressure the target SKU's purchase decision."""

    def classify(self, payload: ReplacementPressureInput) -> ReplacementPressureResult:
        anchor = payload.anchor_substitutability
        breakdown = ReplacementPressureBreakdown(
            purchase_pool_pressure=_purchase_pool_pressure(
                payload.purchase_pool_level, payload.purchase_pool_score
            ),
            purchase_reason_pressure=_purchase_reason_pressure(anchor),
            price_or_config_impact=_price_or_config_impact(payload),
            scenario_mindshare_shift=_scenario_mindshare_shift(payload),
            market_diversion_validation=_market_diversion_validation(
                payload.market_validation_level
            ),
            confidence_adjustment=_confidence_adjustment(payload),
        )
        raw_score = max(Decimal("0"), min(Decimal("10"), breakdown.total_before_cap))
        score = _round_points(raw_score)
        level = _level(score)
        type_candidates = _pressure_type_candidates(payload, breakdown=breakdown)
        primary = (
            type_candidates[0]
            if score >= 5 and type_candidates
            else _low_pressure_candidate(score)
        )
        auxiliaries = [
            candidate
            for candidate in type_candidates
            if candidate.pressure_type != primary.pressure_type and candidate.score > 0
        ][:2]
        requires_review = (
            anchor.requires_review or breakdown.confidence_adjustment < 0 or score < 5
        )
        strong_pressure_allowed = score >= 5 and anchor.pair_scoring_allowed
        reason_cn = _reason_cn(
            score=score,
            primary=primary,
            auxiliaries=auxiliaries,
            strong_pressure_allowed=strong_pressure_allowed,
            anchor=anchor,
        )
        return ReplacementPressureResult(
            replacement_pressure_score=score,
            replacement_pressure_score_raw=raw_score.quantize(Decimal("0.0001")),
            replacement_pressure_level=level,
            score_breakdown=breakdown,
            primary_pressure_type=primary.pressure_type,
            primary_pressure_type_cn=primary.pressure_type_cn,
            auxiliary_pressure_types=auxiliaries,
            strong_pressure_allowed=strong_pressure_allowed,
            requires_review=requires_review,
            reason_cn=reason_cn,
            risk_notes=_risk_notes(payload, score=score),
        )


def _purchase_pool_pressure(
    level: str, score: Decimal | int | float | str | None
) -> Decimal:
    normalized = str(level or "").upper()
    by_level = {
        "P0": Decimal("2.0000"),
        "P1": Decimal("1.7000"),
        "P2": Decimal("1.3000"),
        "P3": Decimal("0.9000"),
        "P4": Decimal("0.4000"),
    }
    if normalized in by_level:
        return by_level[normalized]
    return (_clamp01(_decimal(score)) * Decimal("2")).quantize(Decimal("0.0001"))


def _purchase_reason_pressure(anchor: AnchorSubstitutabilityResult) -> Decimal:
    if not anchor.pair_scoring_allowed:
        return Decimal("0.0000")
    return (
        Decimal(anchor.anchor_substitutability_score) / Decimal("15") * Decimal("3")
    ).quantize(Decimal("0.0001"))


def _price_or_config_impact(payload: ReplacementPressureInput) -> Decimal:
    anchor_score = payload.anchor_substitutability.anchor_substitutability_score
    price_gap = _decimal(payload.price_gap_pct_to_target)
    config_advantage = _clamp01(_decimal(payload.candidate_config_advantage_score))
    candidate_stronger = bool(
        payload.anchor_substitutability.candidate_stronger_anchors
    )
    options: list[Decimal] = [config_advantage * Decimal("2")]
    if price_gap <= Decimal("-0.15") and anchor_score >= 7:
        options.append(Decimal("1.7000"))
    elif price_gap <= Decimal("-0.08") and anchor_score >= 7:
        options.append(Decimal("1.3000"))
    if abs(price_gap) <= Decimal("0.08") and (
        candidate_stronger or config_advantage >= Decimal("0.60")
    ):
        options.append(Decimal("1.5000"))
    if price_gap >= Decimal("0.15") and anchor_score >= 10:
        options.append(Decimal("1.3000"))
    return min(Decimal("2.0000"), max(options)).quantize(Decimal("0.0001"))


def _scenario_mindshare_shift(payload: ReplacementPressureInput) -> Decimal:
    semantic_score = _semantic_overlap_score(payload.weighted_overlap)
    explicit_score = _clamp01(_decimal(payload.candidate_scenario_mindshare_score))
    candidate_has_stronger_anchor = bool(
        payload.anchor_substitutability.candidate_stronger_anchors
    )
    if candidate_has_stronger_anchor and semantic_score >= Decimal("0.65"):
        return Decimal("1.0000")
    if semantic_score >= Decimal("0.50"):
        return max(Decimal("0.7000"), explicit_score).quantize(Decimal("0.0001"))
    return explicit_score.quantize(Decimal("0.0001"))


def _market_diversion_validation(level: str | None) -> Decimal:
    return {
        "strong": Decimal("1.0000"),
        "medium": Decimal("0.7000"),
        "weak": Decimal("0.2500"),
        "missing": Decimal("0.0000"),
        "none": Decimal("0.0000"),
    }.get(str(level or "weak").lower(), Decimal("0.2500"))


def _confidence_adjustment(payload: ReplacementPressureInput) -> Decimal:
    anchor = payload.anchor_substitutability
    adjustment = Decimal("0.5000")
    if anchor.requires_review:
        adjustment -= Decimal("0.7500")
    if not anchor.pair_scoring_allowed:
        adjustment -= Decimal("1.0000")
    if anchor.anchor_substitutability_score < 7:
        adjustment -= Decimal("0.3000")
    for flag in payload.risk_flags:
        lowered = str(flag).lower()
        if lowered in {
            "sample_limited",
            "market_missing",
            "evidence_conflict",
            "claim_only",
            "service_signal_overweight",
        }:
            adjustment -= Decimal("0.3000")
    if (
        str(payload.market_validation_level or "").lower() == "strong"
        and not anchor.requires_review
    ):
        adjustment += Decimal("0.5000")
    return max(Decimal("-1.0000"), min(Decimal("1.0000"), adjustment)).quantize(
        Decimal("0.0001")
    )


def _pressure_type_candidates(
    payload: ReplacementPressureInput,
    *,
    breakdown: ReplacementPressureBreakdown,
) -> list[PressureTypeCandidate]:
    anchor = payload.anchor_substitutability
    anchor_score = Decimal(anchor.anchor_substitutability_score)
    price_gap = _decimal(payload.price_gap_pct_to_target)
    semantic = _semantic_overlap_score(payload.weighted_overlap)
    config_advantage = _clamp01(_decimal(payload.candidate_config_advantage_score))
    scenario = _clamp01(_decimal(payload.candidate_scenario_mindshare_score))
    brand = _clamp01(_decimal(payload.brand_ecosystem_score))
    pool_is_close = str(payload.purchase_pool_level or "").upper() in {"P0", "P1"}

    candidates: list[PressureTypeCandidate] = []
    candidates.append(
        _type_candidate(
            "value_substitution",
            (breakdown.purchase_pool_pressure / Decimal("2") * Decimal("0.35"))
            + (breakdown.purchase_reason_pressure / Decimal("3") * Decimal("0.45"))
            + (semantic * Decimal("0.20")),
            "同一购买池内承接目标核心成交理由，形成价值解释替代。",
        )
    )
    candidates.append(
        _type_candidate(
            "price_suppression",
            (_price_pressure_signal(price_gap) * Decimal("0.55"))
            + (breakdown.purchase_reason_pressure / Decimal("3") * Decimal("0.45")),
            "候选以更低价格保留目标核心成交理由，削弱目标溢价解释。",
        )
    )
    candidates.append(
        _type_candidate(
            "configuration_benchmark",
            max(
                config_advantage,
                Decimal("1.00") if anchor.candidate_stronger_anchors else Decimal("0"),
            )
            * Decimal("0.70")
            + (Decimal("0.30") if abs(price_gap) <= Decimal("0.12") else Decimal("0")),
            "候选配置或成交理由表达更强，抬高同价位用户预期。",
        )
    )
    candidates.append(
        _type_candidate(
            "scenario_mindshare",
            max(
                scenario,
                semantic if anchor.candidate_stronger_anchors else Decimal("0"),
            )
            * Decimal("0.90")
            + Decimal("0.10"),
            "候选把同类锚点转译成更清晰的场景心智。",
        )
    )
    candidates.append(
        _type_candidate(
            "brand_ecosystem",
            brand,
            "品牌心智、系统生态或渠道表达使候选进入同一候选清单。",
        )
    )
    candidates.append(
        _type_candidate(
            "downtrade_diversion",
            (Decimal("1.00") if price_gap <= Decimal("-0.15") else Decimal("0"))
            * (
                Decimal("0.40")
                + min(anchor_score / Decimal("15"), Decimal("1")) * Decimal("0.60")
            ),
            "用户降低预算后仍能满足部分核心需求，形成下探分流。",
        )
    )
    candidates.append(
        _type_candidate(
            "uptrade_alternative",
            (Decimal("1.00") if price_gap >= Decimal("0.15") else Decimal("0"))
            * (
                Decimal("0.30")
                + min(anchor_score / Decimal("15"), Decimal("1")) * Decimal("0.70")
            ),
            "用户追加预算后可获得更明确高端理由，形成上探替代。",
        )
    )
    if pool_is_close and anchor_score >= 10:
        candidates[0] = _type_candidate(
            "value_substitution",
            candidates[0].score + Decimal("0.1500"),
            candidates[0].reason_cn,
        )
    if price_gap <= Decimal("-0.15") and anchor_score >= 7:
        candidates[1] = _type_candidate(
            "price_suppression",
            candidates[1].score + Decimal("0.1500"),
            candidates[1].reason_cn,
        )
    return sorted(
        candidates, key=lambda item: (item.score, item.pressure_type), reverse=True
    )


def _type_candidate(
    pressure_type: PressureType, score: Decimal, reason_cn: str
) -> PressureTypeCandidate:
    return PressureTypeCandidate(
        pressure_type=pressure_type,
        pressure_type_cn=PRESSURE_TYPE_CN[pressure_type],
        score=max(Decimal("0"), min(Decimal("1"), score)).quantize(Decimal("0.0001")),
        reason_cn=reason_cn,
    )


def _low_pressure_candidate(score: int) -> PressureTypeCandidate:
    return PressureTypeCandidate(
        pressure_type="low_pressure_review",
        pressure_type_cn=PRESSURE_TYPE_CN["low_pressure_review"],
        score=Decimal(score) / Decimal("10"),
        reason_cn="替代压力低于强阈值，只能作为候选观察或复核对象。",
    )


def _reason_cn(
    *,
    score: int,
    primary: PressureTypeCandidate,
    auxiliaries: list[PressureTypeCandidate],
    strong_pressure_allowed: bool,
    anchor: AnchorSubstitutabilityResult,
) -> str:
    if not strong_pressure_allowed:
        return (
            f"替代压力较弱，得分{score}/10。候选与本品的购买理由重合或市场分流证据有限，"
            "当前更适合作为参考竞品。"
        )
    aux_text = (
        "，辅压力为" + "、".join(item.pressure_type_cn for item in auxiliaries)
        if auxiliaries
        else ""
    )
    anchor_text = (
        "，成交理由可替代性较强"
        if anchor.anchor_substitutability_score >= 10
        else "，成交理由只形成局部替代"
    )
    return f"{primary.pressure_type_cn}为主压力，得分{score}/10{aux_text}{anchor_text}。{primary.reason_cn}"


def _risk_notes(payload: ReplacementPressureInput, *, score: int) -> list[str]:
    notes = list(payload.risk_flags)
    if payload.anchor_substitutability.requires_review:
        notes.append("anchor_substitutability_requires_review")
    if not payload.anchor_substitutability.pair_scoring_allowed:
        notes.append("anchor_pair_scoring_blocked")
    if score < 5:
        notes.append("low_replacement_pressure_score")
    return _dedupe(notes)


def _semantic_overlap_score(values: dict[str, Any]) -> Decimal:
    scores = [
        _clamp01(_decimal(values.get(key)))
        for key in ("battlefield", "user_task", "target_group")
        if values.get(key) is not None
    ]
    if not scores:
        return Decimal("0")
    return (sum(scores, Decimal("0")) / Decimal(len(scores))).quantize(
        Decimal("0.0001")
    )


def _price_pressure_signal(price_gap: Decimal) -> Decimal:
    if price_gap <= Decimal("-0.15"):
        return Decimal("1.0000")
    if price_gap <= Decimal("-0.08"):
        return Decimal("0.7000")
    return Decimal("0.0000")


def _level(score: int) -> PressureLevel:
    if score >= 8:
        return "high"
    if score >= 5:
        return "medium"
    if score >= 3:
        return "low"
    return "insufficient"


def _round_points(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _clamp01(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


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
    "PRESSURE_TYPE_CN",
    "PressureTypeCandidate",
    "REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION",
    "REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION",
    "ReplacementPressureBreakdown",
    "ReplacementPressureClassifier",
    "ReplacementPressureInput",
    "ReplacementPressureResult",
]
