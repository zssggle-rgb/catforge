"""Build SKU-level M06 comment signal profiles."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from statistics import mean

from app.services.core3_real_data.comment_downstream_signal_schemas import (
    CommentDownstreamSignalRecord,
    M06SkuInputBundle,
    SkuCommentSignalProfileRecord,
    confidence_level,
)
from app.services.core3_real_data.constants import (
    CORE3_M06_RULE_VERSION,
    CommentSignalStrengthLevel,
    CommentSignalType,
)
from app.services.core3_real_data.hash_utils import stable_hash


class SkuCommentSignalProfileBuilder:
    def build(
        self,
        bundle: M06SkuInputBundle,
        signals: list[CommentDownstreamSignalRecord],
        *,
        run_id: str | None,
        module_run_id: str | None,
        asset_version: str,
        rule_version: str = CORE3_M06_RULE_VERSION,
    ) -> SkuCommentSignalProfileRecord:
        by_type: dict[str, list[CommentDownstreamSignalRecord]] = defaultdict(list)
        for signal in signals:
            by_type[str(signal.signal_type)].append(signal)
        level_counts = Counter(str(signal.signal_level) for signal in signals)
        evidence_ids = _dedupe([evidence_id for signal in signals for evidence_id in signal.evidence_ids])
        confidence = _profile_confidence(signals, bundle.quality_profile.comment_usability_score)
        summary = {
            "sku_code": bundle.sku_code,
            "comment_unit_count": bundle.quality_profile.comment_unit_count,
            "usable_sentence_count": bundle.quality_profile.usable_sentence_count,
            "signal_count": len(signals),
            "signal_type_counts": {signal_type: len(items) for signal_type, items in sorted(by_type.items())},
            "top_signals": [_signal_summary(signal) for signal in sorted(signals, key=lambda item: item.signal_score, reverse=True)[:8]],
            "boundary_note": "评论信号仅证明体验感知，不输出最终任务、客群、战场或竞品结论。",
        }
        result_payload = {
            "batch_id": bundle.batch_id,
            "sku_code": bundle.sku_code,
            "signal_hashes": sorted(signal.result_hash for signal in signals),
            "quality_profile_hash": bundle.quality_profile.result_hash,
            "rule_version": rule_version,
            "asset_version": asset_version,
        }
        result_hash = stable_hash(result_payload, version="m06_sku_comment_signal_profile_result_v1")
        profile_key = stable_hash(
            {
                "batch_id": bundle.batch_id,
                "sku_code": bundle.sku_code,
                "rule_version": rule_version,
                "asset_version": asset_version,
            },
            version="m06_sku_comment_signal_profile_key_v1",
        )
        review_issues = _review_summary(bundle, signals)
        return SkuCommentSignalProfileRecord(
            sku_comment_signal_profile_id=_id("m06prof", profile_key),
            project_id=bundle.project_id,
            category_code=bundle.category_code,
            batch_id=bundle.batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=bundle.sku_code,
            model_name=bundle.model_name,
            brand_name=bundle.brand_name,
            profile_key=profile_key,
            comment_signal_summary_json=summary,
            claim_validation_summary_json=_typed_summary(by_type, CommentSignalType.CLAIM_VALIDATION),
            task_cue_summary_json=_typed_summary(by_type, CommentSignalType.TASK_CUE),
            target_group_cue_summary_json=_typed_summary(by_type, CommentSignalType.TARGET_GROUP_CUE),
            battlefield_support_summary_json=_typed_summary(by_type, CommentSignalType.BATTLEFIELD_SUPPORT),
            pain_risk_summary_json=_typed_summary(by_type, CommentSignalType.PAIN_POINT),
            price_perception_summary_json=_typed_summary(by_type, CommentSignalType.PRICE_PERCEPTION),
            service_signal_summary_json=_typed_summary(by_type, CommentSignalType.SERVICE_SIGNAL),
            strong_signal_count=level_counts[CommentSignalStrengthLevel.STRONG.value],
            medium_signal_count=level_counts[CommentSignalStrengthLevel.MEDIUM.value],
            weak_signal_count=level_counts[CommentSignalStrengthLevel.WEAK.value],
            blocked_signal_count=level_counts[CommentSignalStrengthLevel.BLOCKED.value],
            claim_validation_ready=any(signal.signal_type == CommentSignalType.CLAIM_VALIDATION for signal in signals),
            task_cue_ready=any(signal.signal_type == CommentSignalType.TASK_CUE for signal in signals),
            target_group_cue_ready=any(signal.signal_type == CommentSignalType.TARGET_GROUP_CUE for signal in signals),
            battlefield_support_ready=any(signal.signal_type == CommentSignalType.BATTLEFIELD_SUPPORT for signal in signals),
            comment_signal_confidence=confidence,
            confidence_level=confidence_level(confidence),
            quality_flags=_dedupe([*bundle.quality_profile.warning_flags, *[flag for signal in signals for flag in signal.comment_quality_flags]]),
            review_issue_summary_json=review_issues,
            evidence_ids=evidence_ids,
            rule_version=rule_version,
            asset_version=asset_version,
            input_fingerprint=bundle.input_fingerprint,
            result_hash=result_hash,
            processing_status="review_required" if review_issues.get("review_required") else "success",
            review_required=bool(review_issues.get("review_required")),
            review_status="review_required" if review_issues.get("review_required") else "auto_pass",
            review_reason_json=review_issues,
        )


def _typed_summary(
    by_type: dict[str, list[CommentDownstreamSignalRecord]],
    signal_type: CommentSignalType,
) -> dict[str, object]:
    items = sorted(by_type.get(signal_type.value, []), key=lambda item: item.signal_score, reverse=True)
    return {
        "signal_type": signal_type.value,
        "count": len(items),
        "top": [_signal_summary(item) for item in items[:5]],
        "ready": bool(items),
    }


def _signal_summary(signal: CommentDownstreamSignalRecord) -> dict[str, object]:
    return {
        "target_code": signal.target_code_hint,
        "target_name": signal.target_name_hint,
        "polarity": str(signal.polarity),
        "signal_score": float(signal.signal_score),
        "mention_rate": float(signal.mention_rate),
        "signal_level": str(signal.signal_level),
        "representative_phrases": signal.representative_phrases[:3],
        "service_guardrail_flag": signal.service_guardrail_flag,
    }


def _profile_confidence(signals: list[CommentDownstreamSignalRecord], usability_score: Decimal) -> Decimal:
    if not signals:
        return Decimal("0.0000")
    avg_signal_confidence = Decimal(str(mean(float(signal.confidence) for signal in signals)))
    value = (avg_signal_confidence * Decimal("0.75")) + (Decimal(str(usability_score)) * Decimal("0.25"))
    return max(Decimal("0.0000"), min(Decimal("0.9500"), value.quantize(Decimal("0.0001"))))


def _review_summary(bundle: M06SkuInputBundle, signals: list[CommentDownstreamSignalRecord]) -> dict[str, object]:
    issues: list[str] = []
    if not bundle.quality_profile.downstream_ready:
        issues.append("m05_profile_not_downstream_ready")
    if not signals and bundle.quality_profile.usable_sentence_count > 0:
        issues.append("no_comment_signal_matched")
    if bundle.quality_profile.usable_sentence_count == 0:
        issues.append("no_usable_comment_sentence")
    return {
        "review_required": bool(issues),
        "issues": issues,
        "message_cn": "评论信号需要复核。" if issues else "评论信号画像可供后续模块消费。",
    }


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result[:80]


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{value.split(':')[-1][:32]}"
