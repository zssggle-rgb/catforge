"""M04a base claim activation scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.base_claim_activation_schemas import (
    ClaimActivationBasis,
    ClaimActivationLevel,
    ClaimReviewStatus,
    ClaimType,
    StdClaimDefinition,
)
from app.services.core3_real_data.claim_support_scorer import ClaimSupportScore
from app.services.core3_real_data.constants import (
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash


CLAIM_ACTIVATION_ID_HASH_VERSION = "m04a-claim-activation-id-v1"
CLAIM_ACTIVATION_HASH_VERSION = "m04a-claim-activation-v1"
TECHNICAL_PARAM_WEIGHT = Decimal("0.6500")
TECHNICAL_PROMO_WEIGHT = Decimal("0.3500")
BUSINESS_PARAM_WEIGHT = Decimal("0.3500")
BUSINESS_PROMO_WEIGHT = Decimal("0.6500")
CONFLICT_PENALTY = Decimal("0.1500")
MISSING_REQUIRED_PARAM_PENALTY = Decimal("0.0800")
MISSING_PROMO_PENALTY = Decimal("0.0300")
UNCERTAIN_PENALTY = Decimal("0.0400")
PARAM_ONLY_NOT_ALLOWED_CAP = ClaimActivationLevel.LOW.value
TECHNICAL_PROMO_ONLY_CAP = ClaimActivationLevel.MEDIUM.value


@dataclass(frozen=True)
class ClaimActivationBaseDraft:
    claim_activation_base_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    sku_code: str
    model_name: str | None
    claim_code: str
    claim_name: str
    claim_group: str
    claim_type: str
    param_score: Decimal
    promo_score: Decimal
    base_activation_score: Decimal
    activation_level: str
    activation_basis: str
    param_support_json: dict[str, Any]
    promo_support_json: dict[str, Any]
    missing_signals: list[str]
    conflict_flags: list[str]
    confidence: Decimal
    confidence_level: str
    evidence_ids: list[str]
    param_evidence_ids: list[str]
    promo_evidence_ids: list[str]
    quality_evidence_ids: list[str]
    claim_hit_ids: list[str]
    review_required: bool
    review_status: str
    review_reason: str | None
    activation_hash: str
    seed_version: str
    rule_version: str

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "claim_activation_base_id": self.claim_activation_base_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "model_name": self.model_name,
            "claim_code": self.claim_code,
            "claim_name": self.claim_name,
            "claim_group": self.claim_group,
            "claim_type": self.claim_type,
            "param_score": self.param_score,
            "promo_score": self.promo_score,
            "base_activation_score": self.base_activation_score,
            "activation_level": self.activation_level,
            "activation_basis": self.activation_basis,
            "param_support_json": self.param_support_json,
            "promo_support_json": self.promo_support_json,
            "missing_signals": self.missing_signals,
            "conflict_flags": self.conflict_flags,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "evidence_ids": self.evidence_ids,
            "param_evidence_ids": self.param_evidence_ids,
            "promo_evidence_ids": self.promo_evidence_ids,
            "quality_evidence_ids": self.quality_evidence_ids,
            "claim_hit_ids": self.claim_hit_ids,
            "review_required": self.review_required,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "activation_hash": self.activation_hash,
            "seed_version": self.seed_version,
            "rule_version": self.rule_version,
        }


class ClaimActivationBaseScorer:
    """Compute M04a base claim activation without persistence."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M04A_SEED_VERSION,
        rule_version: str = CORE3_M04A_RULE_VERSION,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.seed_version = seed_version
        self.rule_version = rule_version

    def score_claim(
        self,
        claim: StdClaimDefinition,
        support: ClaimSupportScore,
        *,
        sku_code: str,
        model_name: str | None = None,
        source_status: Any | None = None,
    ) -> ClaimActivationBaseDraft:
        param_score = support.param_score
        promo_score = support.promo_score
        activation_basis = _activation_basis(param_score, promo_score)
        weights = _activation_weights(claim)
        missing_signals = _missing_signals(claim, support, activation_basis, source_status)
        conflict_flags = _unique_preserve_order(support.conflict_flags)
        raw_score = _weighted_score(param_score, promo_score, weights) - _penalty(missing_signals, conflict_flags)
        base_score = _clamp_score(raw_score)
        activation_level = _activation_level(base_score)
        activation_level = _cap_activation_level(
            activation_level,
            claim=claim,
            activation_basis=activation_basis,
            missing_signals=missing_signals,
        )
        review_reasons = _review_reasons(
            claim=claim,
            support=support,
            activation_basis=activation_basis,
            missing_signals=missing_signals,
            conflict_flags=conflict_flags,
            source_status=source_status,
        )
        review_required = bool(review_reasons)
        evidence_ids = _unique_preserve_order(
            [
                *support.evidence_ids,
                *_string_list(_field_value(source_status, "quality_evidence_ids")),
            ]
        )
        quality_evidence_ids = _unique_preserve_order(
            [*support.quality_evidence_ids, *_string_list(_field_value(source_status, "quality_evidence_ids"))]
        )
        activation_hash = _build_activation_hash(
            sku_code=sku_code,
            claim_code=claim.claim_code,
            param_score=param_score,
            promo_score=promo_score,
            base_activation_score=base_score,
            activation_basis=activation_basis,
            missing_signals=missing_signals,
            conflict_flags=conflict_flags,
            evidence_ids=evidence_ids,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )
        return ClaimActivationBaseDraft(
            claim_activation_base_id=_build_activation_id(
                project_id=self.project_id,
                batch_id=self.batch_id,
                sku_code=sku_code,
                claim_code=claim.claim_code,
                seed_version=self.seed_version,
                rule_version=self.rule_version,
            ),
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            sku_code=sku_code,
            model_name=model_name or _optional_string(_field_value(source_status, "model_name")),
            claim_code=claim.claim_code,
            claim_name=claim.claim_name,
            claim_group=_enum_value(claim.claim_group),
            claim_type=_enum_value(claim.claim_type),
            param_score=param_score,
            promo_score=promo_score,
            base_activation_score=base_score,
            activation_level=activation_level,
            activation_basis=activation_basis,
            param_support_json={
                **support.param_support_json,
                "activation_weight": _decimal_text(weights["param"]),
            },
            promo_support_json={
                **support.promo_support_json,
                "activation_weight": _decimal_text(weights["promo"]),
            },
            missing_signals=missing_signals,
            conflict_flags=conflict_flags,
            confidence=base_score,
            confidence_level=_confidence_level(base_score),
            evidence_ids=evidence_ids,
            param_evidence_ids=support.param_evidence_ids,
            promo_evidence_ids=support.promo_evidence_ids,
            quality_evidence_ids=quality_evidence_ids,
            claim_hit_ids=support.claim_hit_ids,
            review_required=review_required,
            review_status=(
                ClaimReviewStatus.REVIEW_REQUIRED.value if review_required else ClaimReviewStatus.AUTO_PASS.value
            ),
            review_reason="；".join(review_reasons) if review_reasons else None,
            activation_hash=activation_hash,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )

    def score_many(
        self,
        claims_by_code: Mapping[str, StdClaimDefinition],
        supports: Iterable[ClaimSupportScore],
        *,
        sku_code: str,
        model_name: str | None = None,
        source_status: Any | None = None,
    ) -> list[ClaimActivationBaseDraft]:
        drafts: list[ClaimActivationBaseDraft] = []
        for support in supports:
            claim = claims_by_code.get(support.claim_code)
            if claim is None:
                continue
            drafts.append(
                self.score_claim(
                    claim,
                    support,
                    sku_code=sku_code,
                    model_name=model_name,
                    source_status=source_status,
                )
            )
        return sorted(drafts, key=lambda item: item.claim_code)


def _activation_basis(param_score: Decimal, promo_score: Decimal) -> str:
    if param_score > 0 and promo_score > 0:
        return ClaimActivationBasis.PARAM_AND_PROMO.value
    if param_score > 0:
        return ClaimActivationBasis.PARAM_ONLY.value
    if promo_score > 0:
        return ClaimActivationBasis.PROMO_ONLY.value
    return ClaimActivationBasis.INSUFFICIENT.value


def _activation_weights(claim: StdClaimDefinition) -> dict[str, Decimal]:
    if _enum_value(claim.claim_type) == ClaimType.TECHNICAL.value:
        return {"param": TECHNICAL_PARAM_WEIGHT, "promo": TECHNICAL_PROMO_WEIGHT}
    return {"param": BUSINESS_PARAM_WEIGHT, "promo": BUSINESS_PROMO_WEIGHT}


def _weighted_score(param_score: Decimal, promo_score: Decimal, weights: Mapping[str, Decimal]) -> Decimal:
    return param_score * weights["param"] + promo_score * weights["promo"]


def _missing_signals(
    claim: StdClaimDefinition,
    support: ClaimSupportScore,
    activation_basis: str,
    source_status: Any | None,
) -> list[str]:
    signals = [*_normalized_source_missing_signals(source_status), *support.missing_signals]
    if "missing_promo_evidence" in signals and "missing_structured_claim" in signals:
        signals = [signal for signal in signals if signal != "missing_promo_evidence"]
    if activation_basis == ClaimActivationBasis.PROMO_ONLY.value and _enum_value(claim.claim_type) == ClaimType.TECHNICAL.value:
        signals.append("missing_required_param")
    if _enum_value(claim.claim_type) in {
        ClaimType.EXPERIENCE.value,
        ClaimType.MIXED.value,
        ClaimType.SERVICE.value,
        ClaimType.VALUE.value,
    }:
        signals.append("comment_validation_pending")
    if _enum_value(claim.claim_type) == ClaimType.VALUE.value:
        signals.append("market_value_pending")
    for flag in support.quality_flags:
        if flag in {"scope_uncertain", "refresh_scope_uncertain", "brightness_scope_uncertain"}:
            signals.append("scope_uncertain")
        if flag == "unit_uncertain":
            signals.append("unit_uncertain")
    return _unique_preserve_order(signals)


def _normalized_source_missing_signals(source_status: Any | None) -> list[str]:
    raw_signals = _string_list(_field_value(source_status, "missing_signals"))
    normalized: list[str] = []
    for signal in raw_signals:
        if signal == "structured_claim_missing":
            normalized.append("missing_structured_claim")
        else:
            normalized.append(signal)
    return normalized


def _penalty(missing_signals: list[str], conflict_flags: list[str]) -> Decimal:
    penalty = Decimal("0.0000")
    if conflict_flags:
        penalty += CONFLICT_PENALTY
    if "missing_required_param" in missing_signals or "param_unknown" in missing_signals:
        penalty += MISSING_REQUIRED_PARAM_PENALTY
    if "missing_promo_evidence" in missing_signals or "missing_structured_claim" in missing_signals:
        penalty += MISSING_PROMO_PENALTY
    if {"scope_uncertain", "unit_uncertain"} & set(missing_signals):
        penalty += UNCERTAIN_PENALTY
    return penalty


def _activation_level(score: Decimal) -> str:
    if score >= Decimal("0.7500"):
        return ClaimActivationLevel.HIGH.value
    if score >= Decimal("0.5500"):
        return ClaimActivationLevel.MEDIUM.value
    if score >= Decimal("0.3500"):
        return ClaimActivationLevel.LOW.value
    return ClaimActivationLevel.UNKNOWN.value


def _cap_activation_level(
    level: str,
    *,
    claim: StdClaimDefinition,
    activation_basis: str,
    missing_signals: list[str],
) -> str:
    if activation_basis == ClaimActivationBasis.PARAM_ONLY.value and bool(claim.param_only_allowed):
        return _min_level(level, ClaimActivationLevel.MEDIUM.value)
    if activation_basis == ClaimActivationBasis.PARAM_ONLY.value and not bool(claim.param_only_allowed):
        return _min_level(level, PARAM_ONLY_NOT_ALLOWED_CAP)
    if activation_basis == ClaimActivationBasis.PROMO_ONLY.value and _enum_value(claim.claim_type) == ClaimType.TECHNICAL.value:
        return _min_level(level, TECHNICAL_PROMO_ONLY_CAP)
    if "market_value_pending" in missing_signals:
        return _min_level(level, ClaimActivationLevel.LOW.value)
    return level


def _min_level(level: str, cap: str) -> str:
    order = {
        ClaimActivationLevel.UNKNOWN.value: 0,
        ClaimActivationLevel.LOW.value: 1,
        ClaimActivationLevel.MEDIUM.value: 2,
        ClaimActivationLevel.HIGH.value: 3,
    }
    if order[level] <= order[cap]:
        return level
    return cap


def _confidence_level(score: Decimal) -> str:
    if score >= Decimal("0.7500"):
        return Core3ConfidenceLevel.HIGH.value
    if score >= Decimal("0.5500"):
        return Core3ConfidenceLevel.MEDIUM.value
    if score >= Decimal("0.3500"):
        return Core3ConfidenceLevel.LOW.value
    return Core3ConfidenceLevel.UNKNOWN.value


def _review_reasons(
    *,
    claim: StdClaimDefinition,
    support: ClaimSupportScore,
    activation_basis: str,
    missing_signals: list[str],
    conflict_flags: list[str],
    source_status: Any | None,
) -> list[str]:
    reasons: list[str] = []
    if support.review_required:
        reasons.append("上游参数或宣传支撑需要复核")
    if bool(_field_value(source_status, "review_required")):
        reasons.append("SKU 卖点来源状态需要复核")
    if conflict_flags:
        reasons.append("参数、宣传或质量证据存在冲突")
    if activation_basis == ClaimActivationBasis.PARAM_ONLY.value:
        reasons.append("param-only 卖点会影响核心竞品判断")
    if activation_basis == ClaimActivationBasis.PROMO_ONLY.value and _enum_value(claim.claim_type) == ClaimType.TECHNICAL.value:
        reasons.append("技术型卖点只有宣传没有参数支撑")
    if activation_basis == ClaimActivationBasis.INSUFFICIENT.value:
        reasons.append("参数和宣传均不足以激活基础卖点")
    if "missing_structured_claim" in missing_signals:
        reasons.append("结构化宣传卖点缺失")
    if "comment_validation_pending" in missing_signals:
        reasons.append("用户感知仍待评论验证")
    if "market_value_pending" in missing_signals:
        reasons.append("价值判断仍待市场验证")
    if {"scope_uncertain", "unit_uncertain"} & set(missing_signals):
        reasons.append("参数口径或单位不明确")
    return _unique_preserve_order(reasons)


def _build_activation_id(
    *,
    project_id: str,
    batch_id: str,
    sku_code: str,
    claim_code: str,
    seed_version: str,
    rule_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "claim_code": claim_code,
            "seed_version": seed_version,
            "rule_version": rule_version,
        },
        version=CLAIM_ACTIVATION_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m04abase_{digest[:32]}"


def _build_activation_hash(**payload: Any) -> str:
    return stable_hash(payload, version=CLAIM_ACTIVATION_HASH_VERSION)


def _field_value(record: Any, field_name: str) -> Any:
    if record is None:
        return None
    if isinstance(record, Mapping):
        return record.get(field_name)
    if hasattr(record, "model_dump"):
        return record.model_dump().get(field_name)
    return getattr(record, field_name, None)


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value or "")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def _clamp_score(score: Decimal) -> Decimal:
    return min(Decimal("1.0000"), max(Decimal("0.0000"), score)).quantize(Decimal("0.0001"))


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
