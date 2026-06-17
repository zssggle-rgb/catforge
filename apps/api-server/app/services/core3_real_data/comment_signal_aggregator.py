"""Aggregate M06 sentence-level candidates into SKU downstream signals."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import mean

from app.services.core3_real_data.comment_downstream_signal_schemas import (
    CommentDownstreamSignalRecord,
    CommentSignalCandidateRecord,
    M06SkuInputBundle,
    confidence_level,
    signal_strength_level,
)
from app.services.core3_real_data.constants import (
    CORE3_M06_RULE_VERSION,
    CommentHardSpecPolicy,
    CommentSignalPolarity,
    CommentSignalStrengthLevel,
    CommentSignalType,
)
from app.services.core3_real_data.hash_utils import stable_hash


class CommentSignalAggregator:
    def aggregate(
        self,
        bundle: M06SkuInputBundle,
        candidates: list[CommentSignalCandidateRecord],
        *,
        run_id: str | None,
        module_run_id: str | None,
        asset_version: str,
        rule_version: str = CORE3_M06_RULE_VERSION,
    ) -> list[CommentDownstreamSignalRecord]:
        groups: dict[tuple[str, str, str], list[CommentSignalCandidateRecord]] = defaultdict(list)
        for candidate in candidates:
            groups[
                (
                    str(candidate.signal_type),
                    candidate.target_code_hint,
                    str(candidate.polarity),
                )
            ].append(candidate)

        records: list[CommentDownstreamSignalRecord] = []
        for (signal_type, target_code, polarity), group in sorted(groups.items()):
            valid_units = max(1, bundle.quality_profile.comment_unit_count)
            usable_sentences = max(1, bundle.quality_profile.usable_sentence_count)
            unit_ids = {candidate.comment_unit_id for candidate in group}
            positive_units = {
                candidate.comment_unit_id
                for candidate in group
                if candidate.polarity == CommentSignalPolarity.SUPPORT
            }
            negative_units = {
                candidate.comment_unit_id
                for candidate in group
                if candidate.polarity == CommentSignalPolarity.WEAKEN
            }
            neutral_units = unit_ids - positive_units - negative_units
            mention_rate = _ratio(len(unit_ids), valid_units)
            sentence_rate = _ratio(len(group), usable_sentences)
            score = _signal_score(group, mention_rate)
            level = signal_strength_level(score)
            confidence = _signal_confidence(group, score, bundle.quality_profile.comment_usability_score)
            key_payload = {
                "batch_id": bundle.batch_id,
                "sku_code": bundle.sku_code,
                "signal_type": signal_type,
                "target_code": target_code,
                "polarity": polarity,
                "rule_version": rule_version,
                "asset_version": asset_version,
            }
            signal_key = stable_hash(key_payload, version="m06_downstream_signal_key_v1")
            result_payload = {
                **key_payload,
                "mention_count": len(unit_ids),
                "sentence_count": len(group),
                "signal_score": score,
                "candidate_hashes": sorted(candidate.result_hash for candidate in group),
            }
            result_hash = stable_hash(result_payload, version="m06_downstream_signal_result_v1")
            records.append(
                CommentDownstreamSignalRecord(
                    signal_id=_id("m06sig", signal_key),
                    project_id=bundle.project_id,
                    category_code=bundle.category_code,
                    batch_id=bundle.batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_code=bundle.sku_code,
                    model_name=bundle.model_name,
                    brand_name=bundle.brand_name,
                    signal_key=signal_key,
                    signal_type=CommentSignalType(signal_type),
                    target_code_hint=target_code,
                    target_name_hint=group[0].target_name_hint,
                    target_group_hint=group[0].target_group_hint,
                    polarity=CommentSignalPolarity(polarity),
                    mention_count=len(unit_ids),
                    sentence_count=len(group),
                    valid_comment_unit_count=bundle.quality_profile.comment_unit_count,
                    usable_sentence_count=bundle.quality_profile.usable_sentence_count,
                    mention_rate=mention_rate,
                    sentence_mention_rate=sentence_rate,
                    positive_count=len(positive_units),
                    negative_count=len(negative_units),
                    neutral_count=len(neutral_units),
                    positive_rate=_ratio(len(positive_units), len(unit_ids)),
                    negative_rate=_ratio(len(negative_units), len(unit_ids)),
                    mixed_flag=bool(positive_units and negative_units),
                    signal_score=score,
                    signal_level=level,
                    specificity_avg=_avg_decimal([candidate.specificity_score for candidate in group]),
                    evidence_quality_score=_avg_decimal([candidate.confidence for candidate in group]),
                    sample_status=bundle.quality_profile.sample_status,
                    comment_quality_flags=_dedupe([flag for candidate in group for flag in candidate.quality_flags]),
                    representative_phrases=_representative_phrases(group),
                    top_candidate_ids=[candidate.signal_candidate_id for candidate in sorted(group, key=lambda item: item.signal_strength, reverse=True)[:5]],
                    evidence_ids=_dedupe(
                        [
                            evidence_id
                            for candidate in group
                            for evidence_id in [*candidate.source_m05_evidence_ids, *candidate.source_m02_evidence_ids]
                        ]
                    ),
                    service_guardrail_flag=any(candidate.service_guardrail_flag for candidate in group),
                    hard_spec_policy=_hard_spec_policy(group),
                    downstream_usage_policy_json=_downstream_policy(signal_type, group),
                    quality_summary=_quality_summary_cn(signal_type, group, level),
                    confidence=confidence,
                    confidence_level=confidence_level(confidence),
                    rule_version=rule_version,
                    asset_version=asset_version,
                    input_fingerprint=bundle.input_fingerprint,
                    result_hash=result_hash,
                    processing_status="success" if level != CommentSignalStrengthLevel.BLOCKED else "warning",
                    review_required=level == CommentSignalStrengthLevel.BLOCKED,
                    review_status="review_required" if level == CommentSignalStrengthLevel.BLOCKED else "auto_pass",
                    review_reason_json={"reason": "blocked_signal"} if level == CommentSignalStrengthLevel.BLOCKED else {},
                )
            )
        return records


def _signal_score(group: list[CommentSignalCandidateRecord], mention_rate: Decimal) -> Decimal:
    strength_avg = _avg_decimal([candidate.signal_strength for candidate in group])
    score = (strength_avg * Decimal("0.70")) + (min(mention_rate * Decimal("5"), Decimal("1.0")) * Decimal("0.30"))
    return max(Decimal("0.0000"), min(Decimal("0.9500"), score.quantize(Decimal("0.0001"))))


def _signal_confidence(
    group: list[CommentSignalCandidateRecord],
    score: Decimal,
    usability_score: Decimal,
) -> Decimal:
    confidence_avg = _avg_decimal([candidate.confidence for candidate in group])
    value = (confidence_avg * Decimal("0.55")) + (score * Decimal("0.30")) + (Decimal(str(usability_score)) * Decimal("0.15"))
    return max(Decimal("0.0000"), min(Decimal("0.9500"), value.quantize(Decimal("0.0001"))))


def _avg_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.0000")
    return Decimal(str(mean(float(value) for value in values))).quantize(Decimal("0.0001"))


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _representative_phrases(group: list[CommentSignalCandidateRecord]) -> list[str]:
    result: list[str] = []
    for candidate in sorted(group, key=lambda item: item.signal_strength, reverse=True):
        phrase = candidate.sentence_text.strip()
        if phrase and phrase not in result:
            result.append(phrase[:160])
        if len(result) >= 5:
            break
    return result


def _hard_spec_policy(group: list[CommentSignalCandidateRecord]) -> CommentHardSpecPolicy:
    policies = {CommentHardSpecPolicy(candidate.hard_spec_policy) for candidate in group}
    if CommentHardSpecPolicy.SERVICE_ONLY in policies:
        return CommentHardSpecPolicy.SERVICE_ONLY
    if CommentHardSpecPolicy.MARKET_FACT_REQUIRED in policies:
        return CommentHardSpecPolicy.MARKET_FACT_REQUIRED
    if CommentHardSpecPolicy.HARD_SPEC_NOT_PROVEN in policies:
        return CommentHardSpecPolicy.HARD_SPEC_NOT_PROVEN
    return CommentHardSpecPolicy.EXPERIENCE_ONLY


def _downstream_policy(signal_type: str, group: list[CommentSignalCandidateRecord]) -> dict[str, dict[str, object]]:
    service_guardrail = any(candidate.service_guardrail_flag for candidate in group)
    return {
        "M04b": {
            "allowed": signal_type == CommentSignalType.CLAIM_VALIDATION.value,
            "allowed_scope": "product_claim_experience_validation",
            "blocked_if_service_guardrail": service_guardrail,
        },
        "M09": {
            "allowed": signal_type in {CommentSignalType.TASK_CUE.value, CommentSignalType.PRICE_PERCEPTION.value, CommentSignalType.PAIN_POINT.value},
            "allowed_scope": "task_cue_only",
        },
        "M10": {
            "allowed": signal_type in {CommentSignalType.TARGET_GROUP_CUE.value, CommentSignalType.SERVICE_SIGNAL.value},
            "allowed_scope": "target_group_cue_only",
        },
        "M11": {
            "allowed": signal_type in {CommentSignalType.BATTLEFIELD_SUPPORT.value, CommentSignalType.PAIN_POINT.value, CommentSignalType.SERVICE_SIGNAL.value},
            "allowed_scope": "battlefield_comment_support_only",
        },
        "M13": {
            "allowed": signal_type in {CommentSignalType.BATTLEFIELD_SUPPORT.value, CommentSignalType.PAIN_POINT.value, CommentSignalType.PRICE_PERCEPTION.value},
            "allowed_scope": "component_score_comment_evidence_only",
        },
        "hard_spec_policy": {"value": str(_hard_spec_policy(group))},
    }


def _quality_summary_cn(signal_type: str, group: list[CommentSignalCandidateRecord], level: CommentSignalStrengthLevel) -> str:
    return f"{signal_type} 形成 {len(group)} 条句级评论信号，强度为 {level.value}；评论仅作为体验感知证据。"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result[:50]


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{value.split(':')[-1][:32]}"
