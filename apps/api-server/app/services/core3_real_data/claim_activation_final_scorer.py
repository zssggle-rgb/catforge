"""Score final M04b SKU claim activation."""

from __future__ import annotations

from decimal import Decimal

from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimCommentValidationRecord,
    SkuClaimActivationRecord,
    clamp_decimal,
    confidence_level,
)
from app.services.core3_real_data.claim_type_policy_service import ClaimTypePolicyService
from app.services.core3_real_data.constants import (
    CORE3_M04B_RULE_VERSION,
    CORE3_M04B_SEED_VERSION,
    ClaimCommentActivationBasis,
    ClaimCommentActivationLevel,
    ClaimCommentEffect,
    ClaimCommentEnhancedType,
    ClaimPerceptionStatus,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


class ClaimActivationFinalScorer:
    def __init__(self, policy_service: ClaimTypePolicyService) -> None:
        self.policy_service = policy_service

    def score(
        self,
        validation: ClaimCommentValidationRecord,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str = CORE3_M04B_RULE_VERSION,
        seed_version: str = CORE3_M04B_SEED_VERSION,
    ) -> SkuClaimActivationRecord:
        policy = self.policy_service.policy(validation.claim_code)
        conflict_penalty = _conflict_penalty(validation)
        final_score = clamp_decimal(
            (validation.base_activation_score * policy.base_weight)
            + (validation.comment_validation_score * policy.comment_weight)
            - (validation.comment_risk_score * policy.risk_penalty_weight)
            - conflict_penalty
        )
        flags = _activation_flags(validation, policy.m04b_claim_type)
        activation_level = _activation_level(final_score, validation, flags)
        activation_basis = _activation_basis(validation)
        confidence = _confidence(final_score, validation, flags)
        downstream_policy = self.policy_service.downstream_policy_json(
            claim_code=validation.claim_code,
            param_only_flag=flags["param_only_flag"],
            comment_only_flag=flags["comment_only_flag"],
            missing_structured_claim_flag=flags["missing_structured_claim_flag"],
            value_requires_market_validation=flags["value_requires_market_validation"],
            hard_spec_protection_flag=validation.hard_spec_protection_flag,
        )
        score_breakdown = {
            "claim_type": str(policy.m04b_claim_type),
            "weights": {
                "base": str(policy.base_weight),
                "comment": str(policy.comment_weight),
                "risk_penalty": str(policy.risk_penalty_weight),
            },
            "base_activation_score": str(validation.base_activation_score),
            "comment_validation_score": str(validation.comment_validation_score),
            "comment_risk_score": str(validation.comment_risk_score),
            "conflict_penalty": str(conflict_penalty),
            "final_activation_score": str(final_score),
            "score_caps": _score_caps(validation, flags),
        }
        key_payload = {
            "batch_id": validation.batch_id,
            "sku_code": validation.sku_code,
            "claim_code": validation.claim_code,
            "rule_version": rule_version,
            "seed_version": seed_version,
        }
        activation_key = stable_hash(key_payload, version="m04b_activation_key_v1")
        result_payload = {
            **key_payload,
            "validation_hash": validation.result_hash,
            "final_score": str(final_score),
            "activation_level": activation_level.value,
            "activation_basis": activation_basis.value,
            "flags": flags,
            "downstream_policy": downstream_policy,
        }
        result_hash = stable_hash(result_payload, version="m04b_activation_result_v1")
        review_required = activation_level == ClaimCommentActivationLevel.REVIEW_REQUIRED or any(
            flags[key]
            for key in (
                "comment_only_flag",
                "contradiction_flag",
                "value_requires_market_validation",
            )
        )
        return SkuClaimActivationRecord(
            claim_activation_id=_id("m04bact", activation_key),
            project_id=validation.project_id,
            category_code=validation.category_code,
            batch_id=validation.batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=validation.sku_code,
            model_name=validation.model_name,
            brand_name=validation.brand_name,
            activation_key=activation_key,
            claim_activation_base_id=validation.claim_activation_base_id,
            claim_comment_validation_id=validation.claim_comment_validation_id,
            claim_source_status_id=validation.claim_source_status_id,
            claim_code=validation.claim_code,
            claim_name=validation.claim_name,
            claim_group=validation.claim_group,
            m04b_claim_type=policy.m04b_claim_type,
            param_score=validation.param_score,
            promo_score=validation.promo_score,
            base_activation_score=validation.base_activation_score,
            comment_validation_score=validation.comment_validation_score,
            comment_risk_score=validation.comment_risk_score,
            final_activation_score=final_score,
            base_activation_level=validation.base_activation_level,
            activation_level=activation_level,
            activation_basis=activation_basis,
            perception_status=validation.perception_status,
            claim_source_status=validation.claim_source_status,
            comment_effect=validation.comment_effect,
            hard_spec_protection_flag=validation.hard_spec_protection_flag,
            service_guardrail_flag=validation.service_guardrail_flag,
            downstream_usage_policy_json=downstream_policy,
            score_breakdown_json=score_breakdown,
            missing_signals=_dedupe(validation.quality_flags + (["missing_structured_claim"] if flags["missing_structured_claim_flag"] else [])),
            conflict_flags=_dedupe(["comment_contradiction"] if validation.contradiction_flag else []),
            quality_flags=_dedupe(validation.quality_flags),
            evidence_ids=_dedupe(validation.base_evidence_ids + validation.comment_evidence_ids),
            param_evidence_ids=validation.param_evidence_ids,
            promo_evidence_ids=validation.promo_evidence_ids,
            comment_evidence_ids=validation.comment_evidence_ids,
            comment_signal_ids=validation.comment_signal_ids,
            representative_phrases=validation.representative_phrases,
            confidence=confidence,
            confidence_level=confidence_level(confidence),
            rule_version=rule_version,
            seed_version=seed_version,
            input_fingerprint=validation.input_fingerprint,
            result_hash=result_hash,
            processing_status="review_required" if review_required else "success",
            review_required=review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
            review_reason_json={"score_caps": score_breakdown["score_caps"], "flags": flags} if review_required else {},
            **flags,
        )


def _activation_flags(validation: ClaimCommentValidationRecord, claim_type: ClaimCommentEnhancedType | str) -> dict[str, bool]:
    normalized_type = ClaimCommentEnhancedType(claim_type)
    return {
        "missing_structured_claim_flag": validation.claim_source_status == "missing_structured_claim",
        "param_only_flag": validation.base_activation_basis == "param_only",
        "promo_only_flag": validation.base_activation_basis == "promo_only",
        "comment_only_flag": validation.comment_only_flag,
        "weak_perception_flag": validation.weak_perception_flag,
        "contradiction_flag": validation.contradiction_flag,
        "value_requires_market_validation": normalized_type == ClaimCommentEnhancedType.VALUE
        and validation.comment_effect == ClaimCommentEffect.ENHANCE,
    }


def _activation_level(
    score: Decimal,
    validation: ClaimCommentValidationRecord,
    flags: dict[str, bool],
) -> ClaimCommentActivationLevel:
    if validation.comment_effect == ClaimCommentEffect.BLOCKED or flags["contradiction_flag"]:
        return ClaimCommentActivationLevel.REVIEW_REQUIRED
    if flags["comment_only_flag"]:
        return ClaimCommentActivationLevel.LOW if score >= Decimal("0.2500") else ClaimCommentActivationLevel.REVIEW_REQUIRED
    if score >= Decimal("0.7800") and not flags["param_only_flag"] and not flags["missing_structured_claim_flag"]:
        return ClaimCommentActivationLevel.HIGH
    if score >= Decimal("0.5500"):
        return ClaimCommentActivationLevel.MEDIUM
    if score > Decimal("0.1500"):
        return ClaimCommentActivationLevel.LOW
    return ClaimCommentActivationLevel.UNKNOWN


def _activation_basis(validation: ClaimCommentValidationRecord) -> ClaimCommentActivationBasis:
    if validation.comment_only_flag:
        return ClaimCommentActivationBasis.COMMENT_ONLY_HINT
    if validation.hard_spec_protection_flag:
        try:
            return ClaimCommentActivationBasis(validation.base_activation_basis)
        except ValueError:
            return ClaimCommentActivationBasis.INSUFFICIENT
    if validation.comment_effect == ClaimCommentEffect.WEAKEN:
        return ClaimCommentActivationBasis.COMMENT_WEAKENED
    if validation.m04b_claim_type == ClaimCommentEnhancedType.SERVICE and validation.comment_effect == ClaimCommentEffect.ENHANCE:
        return ClaimCommentActivationBasis.SERVICE_COMMENT_VALIDATED
    if validation.comment_effect == ClaimCommentEffect.ENHANCE:
        return ClaimCommentActivationBasis.COMMENT_ENHANCED
    try:
        return ClaimCommentActivationBasis(validation.base_activation_basis)
    except ValueError:
        return ClaimCommentActivationBasis.INSUFFICIENT


def _confidence(score: Decimal, validation: ClaimCommentValidationRecord, flags: dict[str, bool]) -> Decimal:
    evidence_completeness = Decimal("1.0000")
    if flags["missing_structured_claim_flag"]:
        evidence_completeness -= Decimal("0.1500")
    if flags["param_only_flag"] or flags["promo_only_flag"]:
        evidence_completeness -= Decimal("0.1000")
    if flags["comment_only_flag"]:
        evidence_completeness -= Decimal("0.3000")
    review_inverse = Decimal("0.3000") if flags["contradiction_flag"] or flags["comment_only_flag"] else Decimal("0.9000")
    source_status = Decimal("0.7000") if flags["missing_structured_claim_flag"] else Decimal("0.9500")
    confidence = (
        score * Decimal("0.35")
        + validation.confidence * Decimal("0.20")
        + evidence_completeness * Decimal("0.15")
        + source_status * Decimal("0.10")
        + validation.domain_match_score * Decimal("0.10")
        + review_inverse * Decimal("0.10")
    )
    return clamp_decimal(confidence)


def _conflict_penalty(validation: ClaimCommentValidationRecord) -> Decimal:
    if validation.contradiction_flag:
        return Decimal("0.2000")
    if validation.weak_perception_flag:
        return Decimal("0.0500")
    return Decimal("0.0000")


def _score_caps(validation: ClaimCommentValidationRecord, flags: dict[str, bool]) -> list[str]:
    caps: list[str] = []
    if flags["param_only_flag"]:
        caps.append("param_only_cap_medium")
    if flags["missing_structured_claim_flag"]:
        caps.append("missing_structured_claim_report_gap")
    if flags["comment_only_flag"]:
        caps.append("comment_only_cap_low")
    if validation.hard_spec_protection_flag:
        caps.append("hard_spec_not_proven_by_comment")
    if flags["value_requires_market_validation"]:
        caps.append("value_requires_market_validation")
    return caps


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{value.split(':')[-1][:32]}"
