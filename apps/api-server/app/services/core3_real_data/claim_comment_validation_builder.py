"""Build M04b comment validation records from base claims and M06 signals."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import mean

from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimCommentValidationRecord,
    M04bClaimBaseInput,
    M04bClaimValidationSignalInput,
    M04bSkuInputBundle,
    clamp_decimal,
    confidence_level,
)
from app.services.core3_real_data.claim_type_policy_service import ClaimTypePolicyService
from app.services.core3_real_data.constants import (
    CORE3_M04B_RULE_VERSION,
    CORE3_M04B_SEED_VERSION,
    ClaimCommentEffect,
    ClaimCommentEnhancedType,
    ClaimPerceptionStatus,
    CommentHardSpecPolicy,
    CommentSignalPolarity,
    CommentSignalStrengthLevel,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


class ClaimCommentValidationBuilder:
    def __init__(self, policy_service: ClaimTypePolicyService) -> None:
        self.policy_service = policy_service

    def build(
        self,
        bundle: M04bSkuInputBundle,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str = CORE3_M04B_RULE_VERSION,
        seed_version: str = CORE3_M04B_SEED_VERSION,
    ) -> list[ClaimCommentValidationRecord]:
        base_by_claim = {item.claim_code: item for item in bundle.base_claims}
        signals_by_claim: dict[str, list[M04bClaimValidationSignalInput]] = defaultdict(list)
        for signal in bundle.claim_validation_signals:
            signals_by_claim[signal.claim_code].append(signal)
        claim_codes = sorted(set(base_by_claim) | set(signals_by_claim))

        records: list[ClaimCommentValidationRecord] = []
        for claim_code in claim_codes:
            base = base_by_claim.get(claim_code)
            signals = signals_by_claim.get(claim_code, [])
            records.append(
                self._build_one(
                    bundle,
                    claim_code=claim_code,
                    base=base,
                    signals=signals,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        return records

    def _build_one(
        self,
        bundle: M04bSkuInputBundle,
        *,
        claim_code: str,
        base: M04bClaimBaseInput | None,
        signals: list[M04bClaimValidationSignalInput],
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        seed_version: str,
    ) -> ClaimCommentValidationRecord:
        definition = self.policy_service.claim(claim_code)
        policy = self.policy_service.policy(claim_code)
        source_status = bundle.source_status
        claim_name = base.claim_name if base is not None else (definition.claim_name if definition else signals[0].claim_name)
        claim_group = base.claim_group if base is not None else (definition.claim_group if definition else (signals[0].claim_group or "unknown"))
        claim_type = ClaimCommentEnhancedType(policy.m04b_claim_type)
        service_mismatch = any(signal.service_guardrail_flag for signal in signals) and claim_type != ClaimCommentEnhancedType.SERVICE
        hard_spec_flag = policy.hard_spec_protection_flag
        comment_only = base is None
        mention_count = max([signal.mention_count for signal in signals], default=0)
        sentence_count = sum(signal.sentence_count for signal in signals)
        valid_units = max([signal.valid_comment_unit_count for signal in signals], default=0)
        positive_count = sum(signal.positive_count for signal in signals)
        negative_count = sum(signal.negative_count for signal in signals)
        mention_rate = _max_decimal([signal.mention_rate for signal in signals], places="0.000001")
        positive_rate = _ratio(positive_count, max(mention_count, positive_count + negative_count))
        negative_rate = _ratio(negative_count, max(mention_count, positive_count + negative_count))
        specificity_avg = _avg_decimal([signal.specificity_avg for signal in signals])
        evidence_quality = _avg_decimal([signal.evidence_quality_score for signal in signals])
        domain_match = _domain_match(claim_type, signals, service_mismatch)
        validation_score = _validation_score(mention_rate, positive_rate, specificity_avg, evidence_quality, domain_match)
        risk_score = _risk_score(negative_rate, specificity_avg, evidence_quality, mention_count)
        effect, perception = _effect_and_perception(
            base=base,
            claim_type=claim_type,
            signals=signals,
            service_mismatch=service_mismatch,
            comment_only=comment_only,
            validation_score=validation_score,
            risk_score=risk_score,
            positive_rate=positive_rate,
            negative_rate=negative_rate,
        )
        weak_perception = perception == ClaimPerceptionStatus.WEAK_PERCEPTION
        contradiction = perception == ClaimPerceptionStatus.CONTRADICTED
        quality_flags = _quality_flags(
            base=base,
            signals=signals,
            service_mismatch=service_mismatch,
            comment_only=comment_only,
            hard_spec_flag=hard_spec_flag,
            weak_perception=weak_perception,
            contradiction=contradiction,
        )
        confidence = _validation_confidence(validation_score, risk_score, signals, comment_only, service_mismatch)
        key_payload = {
            "batch_id": bundle.batch_id,
            "sku_code": bundle.sku_code,
            "claim_code": claim_code,
            "rule_version": rule_version,
            "seed_version": seed_version,
        }
        validation_key = stable_hash(key_payload, version="m04b_validation_key_v1")
        result_payload = {
            **key_payload,
            "base_hash": base.activation_hash if base else None,
            "source_status_hash": source_status.status_hash if source_status else None,
            "signal_hashes": sorted(signal.result_hash for signal in signals),
            "scores": {
                "validation": str(validation_score),
                "risk": str(risk_score),
                "effect": effect.value,
                "perception": perception.value,
            },
            "quality_flags": quality_flags,
        }
        result_hash = stable_hash(result_payload, version="m04b_validation_result_v1")
        return ClaimCommentValidationRecord(
            claim_comment_validation_id=_id("m04bcv", validation_key),
            project_id=bundle.project_id,
            category_code=bundle.category_code,
            batch_id=bundle.batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=bundle.sku_code,
            model_name=base.model_name if base else bundle.model_name,
            brand_name=bundle.brand_name,
            validation_key=validation_key,
            claim_activation_base_id=base.claim_activation_base_id if base else None,
            claim_source_status_id=source_status.claim_source_status_id if source_status else None,
            claim_code=claim_code,
            claim_name=claim_name,
            claim_group=claim_group,
            m04b_claim_type=claim_type,
            base_activation_score=base.base_activation_score if base else Decimal("0.0000"),
            base_activation_level=base.base_activation_level if base else "unknown",
            base_activation_basis=base.base_activation_basis if base else "insufficient",
            param_score=base.param_score if base else Decimal("0.0000"),
            promo_score=base.promo_score if base else Decimal("0.0000"),
            claim_source_status=source_status.claim_source_status if source_status else "claim_data_insufficient",
            mention_count=mention_count,
            sentence_count=sentence_count,
            valid_comment_unit_count=valid_units,
            mention_rate=mention_rate,
            positive_count=positive_count,
            negative_count=negative_count,
            positive_rate=positive_rate,
            negative_rate=negative_rate,
            specificity_avg=specificity_avg,
            evidence_quality_score=evidence_quality,
            domain_match_score=domain_match,
            comment_validation_score=validation_score,
            comment_risk_score=risk_score,
            comment_effect=effect,
            perception_status=perception,
            hard_spec_protection_flag=hard_spec_flag,
            service_guardrail_flag=any(signal.service_guardrail_flag for signal in signals),
            comment_only_flag=comment_only,
            weak_perception_flag=weak_perception,
            contradiction_flag=contradiction,
            representative_phrases=_representative_phrases(signals),
            comment_signal_ids=[signal.signal_id for signal in signals],
            comment_candidate_ids=_dedupe([candidate_id for signal in signals for candidate_id in signal.top_candidate_ids]),
            comment_evidence_ids=_dedupe([evidence_id for signal in signals for evidence_id in signal.evidence_ids]),
            base_evidence_ids=base.evidence_ids if base else [],
            param_evidence_ids=base.param_evidence_ids if base else [],
            promo_evidence_ids=base.promo_evidence_ids if base else [],
            quality_flags=quality_flags,
            confidence=confidence,
            confidence_level=confidence_level(confidence),
            rule_version=rule_version,
            seed_version=seed_version,
            input_fingerprint=bundle.input_fingerprint,
            result_hash=result_hash,
            processing_status="review_required" if service_mismatch or comment_only else "success",
            review_required=service_mismatch or comment_only,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if service_mismatch or comment_only else Core3ReviewStatus.AUTO_PASS,
            review_reason_json={"quality_flags": quality_flags} if service_mismatch or comment_only else {},
        )


def _validation_score(
    mention_rate: Decimal,
    positive_rate: Decimal,
    specificity: Decimal,
    evidence_quality: Decimal,
    domain_match: Decimal,
) -> Decimal:
    score = (
        min(mention_rate * Decimal("5"), Decimal("1")) * Decimal("0.30")
        + positive_rate * Decimal("0.25")
        + specificity * Decimal("0.20")
        + evidence_quality * Decimal("0.15")
        + domain_match * Decimal("0.10")
    )
    return clamp_decimal(score)


def _risk_score(negative_rate: Decimal, specificity: Decimal, evidence_quality: Decimal, mention_count: int) -> Decimal:
    repeated_issue = Decimal("1.0000") if mention_count >= 3 else Decimal("0.3000") if mention_count > 0 else Decimal("0.0000")
    score = (
        negative_rate * Decimal("0.40")
        + specificity * Decimal("0.30")
        + evidence_quality * Decimal("0.20")
        + repeated_issue * Decimal("0.10")
    )
    return clamp_decimal(score)


def _effect_and_perception(
    *,
    base: M04bClaimBaseInput | None,
    claim_type: ClaimCommentEnhancedType,
    signals: list[M04bClaimValidationSignalInput],
    service_mismatch: bool,
    comment_only: bool,
    validation_score: Decimal,
    risk_score: Decimal,
    positive_rate: Decimal,
    negative_rate: Decimal,
) -> tuple[ClaimCommentEffect, ClaimPerceptionStatus]:
    if service_mismatch:
        return ClaimCommentEffect.BLOCKED, ClaimPerceptionStatus.SERVICE_GUARDED
    if comment_only:
        return ClaimCommentEffect.COMMENT_ONLY_HINT, ClaimPerceptionStatus.COMMENT_ONLY_PENDING
    if not signals:
        if base and base.base_activation_score >= Decimal("0.7000") and claim_type in {
            ClaimCommentEnhancedType.EXPERIENCE_SCENARIO,
            ClaimCommentEnhancedType.TECHNICAL_EXPERIENCE_MIXED,
        }:
            return ClaimCommentEffect.NEUTRAL, ClaimPerceptionStatus.WEAK_PERCEPTION
        return ClaimCommentEffect.NEUTRAL, ClaimPerceptionStatus.INSUFFICIENT_COMMENT
    if negative_rate >= Decimal("0.350000") and risk_score >= Decimal("0.4500"):
        return ClaimCommentEffect.WEAKEN, ClaimPerceptionStatus.CONTRADICTED
    if positive_rate >= Decimal("0.500000") and validation_score >= Decimal("0.4500"):
        return ClaimCommentEffect.ENHANCE, ClaimPerceptionStatus.VALIDATED
    if any(signal.signal_level == CommentSignalStrengthLevel.BLOCKED for signal in signals):
        return ClaimCommentEffect.BLOCKED, ClaimPerceptionStatus.NOT_APPLICABLE
    return ClaimCommentEffect.NEUTRAL, ClaimPerceptionStatus.INSUFFICIENT_COMMENT


def _domain_match(claim_type: ClaimCommentEnhancedType, signals: list[M04bClaimValidationSignalInput], service_mismatch: bool) -> Decimal:
    if not signals:
        return Decimal("0.0000")
    if service_mismatch:
        return Decimal("0.0000")
    has_service = any(signal.service_guardrail_flag or signal.hard_spec_policy == CommentHardSpecPolicy.SERVICE_ONLY for signal in signals)
    if claim_type == ClaimCommentEnhancedType.SERVICE:
        return Decimal("1.0000") if has_service else Decimal("0.6500")
    if has_service:
        return Decimal("0.0000")
    return Decimal("0.8500") if claim_type == ClaimCommentEnhancedType.TECHNICAL_HARD else Decimal("0.9000")


def _validation_confidence(
    validation_score: Decimal,
    risk_score: Decimal,
    signals: list[M04bClaimValidationSignalInput],
    comment_only: bool,
    service_mismatch: bool,
) -> Decimal:
    signal_confidence = _avg_decimal([signal.confidence for signal in signals])
    confidence = (validation_score * Decimal("0.50")) + (signal_confidence * Decimal("0.35")) + ((Decimal("1") - risk_score) * Decimal("0.15"))
    if comment_only:
        confidence -= Decimal("0.2500")
    if service_mismatch:
        confidence = Decimal("0.0000")
    return clamp_decimal(confidence)


def _quality_flags(
    *,
    base: M04bClaimBaseInput | None,
    signals: list[M04bClaimValidationSignalInput],
    service_mismatch: bool,
    comment_only: bool,
    hard_spec_flag: bool,
    weak_perception: bool,
    contradiction: bool,
) -> list[str]:
    flags: list[str] = []
    if base is None:
        flags.append("comment_only")
    elif base.base_activation_basis == "param_only":
        flags.append("param_only")
    elif base.base_activation_basis == "promo_only":
        flags.append("promo_only")
    if service_mismatch:
        flags.append("service_mismatch")
    if comment_only and hard_spec_flag:
        flags.append("spec_claimed_by_comment")
    if weak_perception:
        flags.append("weak_perception")
    if contradiction:
        flags.append("comment_contradiction")
    if any(signal.signal_level == CommentSignalStrengthLevel.BLOCKED for signal in signals):
        flags.append("blocked_comment_signal")
    return _dedupe(flags)


def _representative_phrases(signals: list[M04bClaimValidationSignalInput]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for signal in sorted(signals, key=lambda item: item.signal_score, reverse=True):
        for phrase in signal.representative_phrases:
            text = phrase.strip() if isinstance(phrase, str) else str(phrase).strip()
            if not text:
                continue
            item = {
                "phrase": text[:160],
                "polarity": signal.polarity.value if hasattr(signal.polarity, "value") else str(signal.polarity),
                "signal_id": signal.signal_id,
                "evidence_ids": signal.evidence_ids[:5],
                "specificity_score": str(signal.specificity_avg),
            }
            if item not in result:
                result.append(item)
            if len(result) >= 5:
                return result
    return result


def _avg_decimal(values: list[Decimal], places: str = "0.0000") -> Decimal:
    if not values:
        return Decimal(places)
    return Decimal(str(mean(float(value) for value in values))).quantize(Decimal(places))


def _max_decimal(values: list[Decimal], places: str) -> Decimal:
    if not values:
        return Decimal(places)
    return max(values).quantize(Decimal(places))


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{value.split(':')[-1][:32]}"
