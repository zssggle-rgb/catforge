"""M06 signal extractors.

Each extractor returns downstream-specific comment signals. They deliberately
stop at signal candidates and do not emit final business conclusions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.services.core3_real_data.comment_downstream_signal_schemas import (
    CommentDownstreamSignalRecord,
    CommentSignalCandidateRecord,
    SignalExtractionContext,
    SignalTargetDefinition,
    confidence_level,
    signal_strength_level,
)
from app.services.core3_real_data.constants import (
    CORE3_M06_RULE_VERSION,
    CommentDomainHint,
    CommentHardSpecPolicy,
    CommentSentimentHint,
    CommentSignalCueBasis,
    CommentSignalPolarity,
    CommentSignalType,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


SERVICE_CLAIM_CODE = "CLAIM_INSTALLATION_SERVICE_ASSURANCE"
PRODUCT_SIGNAL_TYPES = {
    CommentSignalType.CLAIM_VALIDATION,
    CommentSignalType.TASK_CUE,
    CommentSignalType.TARGET_GROUP_CUE,
    CommentSignalType.BATTLEFIELD_SUPPORT,
}


class CommentSignalExtractionPipeline:
    def __init__(self) -> None:
        self.extractors = [
            ClaimValidationSignalExtractor(),
            TaskCueSignalExtractor(),
            TargetGroupCueSignalExtractor(),
            BattlefieldSupportSignalExtractor(),
            PainPointSignalExtractor(),
            PricePerceptionSignalExtractor(),
            ServiceSignalExtractor(),
        ]

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        candidates: list[CommentSignalCandidateRecord] = []
        for extractor in self.extractors:
            candidates.extend(extractor.extract(context, run_id=run_id, module_run_id=module_run_id))
        return _dedupe_candidates(candidates)


class BaseSignalExtractor:
    signal_type: CommentSignalType

    def extract(
        self,
        context: SignalExtractionContext,
        *,
        run_id: str | None,
        module_run_id: str | None,
    ) -> list[CommentSignalCandidateRecord]:
        raise NotImplementedError

    def _candidate(
        self,
        context: SignalExtractionContext,
        target: SignalTargetDefinition,
        *,
        run_id: str | None,
        module_run_id: str | None,
        cue_basis: CommentSignalCueBasis,
        polarity: CommentSignalPolarity,
        strength: Decimal,
        hard_spec_policy: CommentHardSpecPolicy,
        service_guardrail_flag: bool = False,
        eligible_for_product_claim: bool = False,
        eligible_for_service_claim: bool = False,
        eligible_for_task: bool = False,
        eligible_for_group: bool = False,
        eligible_for_battlefield: bool = False,
        blocked_reasons: list[str] | None = None,
        matched_rule: str = "keyword_rule_v1",
    ) -> CommentSignalCandidateRecord:
        blocked_reasons = list(blocked_reasons or [])
        if context.atom.low_value_flag and "low_value_comment" not in blocked_reasons:
            blocked_reasons.append("low_value_comment")
        if blocked_reasons:
            strength = min(strength, Decimal("0.3400"))
        confidence = _candidate_confidence(context, strength, service_guardrail_flag, blocked_reasons)
        key_payload = {
            "batch_id": context.bundle.batch_id,
            "sku_code": context.bundle.sku_code,
            "comment_evidence_id": context.atom.comment_evidence_id,
            "signal_type": self.signal_type.value,
            "target_code": target.code,
            "polarity": polarity.value,
            "rule_version": CORE3_M06_RULE_VERSION,
        }
        candidate_key = stable_hash(key_payload, version="m06_signal_candidate_key_v1")
        result_payload = {
            **key_payload,
            "sentence_text": context.atom.sentence_text,
            "cue_basis": cue_basis.value,
            "strength": strength,
            "matched_entities": context.entities.model_dump(mode="json"),
            "topic_codes": [topic.topic_code for topic in context.topic_hints],
            "blocked_reasons": blocked_reasons,
        }
        result_hash = stable_hash(result_payload, version="m06_signal_candidate_result_v1")
        level = signal_strength_level(strength, blocked=bool(blocked_reasons))
        return CommentSignalCandidateRecord(
            signal_candidate_id=_id("m06cand", candidate_key),
            project_id=context.bundle.project_id,
            category_code=context.bundle.category_code,
            batch_id=context.bundle.batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=context.bundle.sku_code,
            model_name=context.bundle.model_name,
            brand_name=context.bundle.brand_name,
            signal_candidate_key=candidate_key,
            comment_unit_id=context.atom.comment_unit_id,
            comment_evidence_id=context.atom.comment_evidence_id,
            comment_text_hash=context.atom.comment_text_hash,
            sentence_hash=context.atom.sentence_hash,
            sentence_text=context.atom.sentence_text,
            signal_type=self.signal_type,
            target_code_hint=target.code,
            target_name_hint=target.name,
            target_group_hint=target.group_hint,
            polarity=polarity,
            signal_strength=strength,
            signal_strength_level=level,
            confidence=confidence,
            confidence_level=confidence_level(confidence),
            specificity_score=context.atom.specificity_score,
            sentiment_hint=context.atom.sentiment_hint,
            domain_hints=context.atom.domain_hints,
            primary_domain_hint=context.atom.primary_domain_hint,
            topic_hints_json=[topic.model_dump(mode="json") for topic in context.topic_hints],
            matched_entities_json=context.entities.model_dump(mode="json"),
            matched_rules_json={
                "signal_rule": matched_rule,
                "seed_sources": ["comment_topics", target.metadata_json.get("source", "builtin")],
                "matched_topic_codes": [topic.topic_code for topic in context.topic_hints],
                "matched_keywords": _target_matches(context, target),
                "target_mapping_reason": _target_mapping_reason(self.signal_type, cue_basis),
                "rule_weight_snapshot": {"topic": 0.35, "entity": 0.30, "sentiment": 0.15, "specificity": 0.20},
            },
            cue_basis=cue_basis,
            hard_spec_policy=hard_spec_policy,
            service_guardrail_flag=service_guardrail_flag,
            eligible_for_product_claim=eligible_for_product_claim,
            eligible_for_service_claim=eligible_for_service_claim,
            eligible_for_task=eligible_for_task,
            eligible_for_group=eligible_for_group,
            eligible_for_battlefield=eligible_for_battlefield,
            low_value_flag=context.atom.low_value_flag,
            duplicate_group_id=context.atom.duplicate_group_id,
            quality_flags=context.atom.quality_flags,
            blocked_reasons=blocked_reasons,
            source_m05_evidence_ids=context.atom.source_m05_evidence_ids,
            source_m02_evidence_ids=context.atom.source_m02_evidence_ids,
            optional_param_context_json=context.bundle.optional_param_context_json,
            optional_claim_context_json=context.bundle.optional_claim_context_json,
            rule_version=CORE3_M06_RULE_VERSION,
            asset_version=context.seed.asset_version,
            input_fingerprint=context.bundle.input_fingerprint,
            result_hash=result_hash,
            processing_status="review_required" if blocked_reasons else "success",
            review_required=bool(blocked_reasons),
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if blocked_reasons else Core3ReviewStatus.AUTO_PASS,
            review_reason_json={"blocked_reasons": blocked_reasons} if blocked_reasons else {},
        )


class ClaimValidationSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.CLAIM_VALIDATION

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        targets = _targets_from_topic_codes(context, self.signal_type, "mapped_claim_codes_snapshot")
        targets.extend(_keyword_targets(context, self.signal_type))
        candidates: list[CommentSignalCandidateRecord] = []
        service_only = _is_service_only(context)
        for target in _unique_targets(targets):
            is_service_claim = target.code == SERVICE_CLAIM_CODE
            blocked = []
            if service_only and not is_service_claim:
                blocked.append("service_to_product_claim_blocked")
            hard_policy = CommentHardSpecPolicy.SERVICE_ONLY if is_service_claim else CommentHardSpecPolicy.EXPERIENCE_ONLY
            candidates.append(
                self._candidate(
                    context,
                    target,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    cue_basis=CommentSignalCueBasis.TOPIC_MAPPING,
                    polarity=_polarity(context),
                    strength=_base_strength(context, target),
                    hard_spec_policy=hard_policy,
                    service_guardrail_flag=service_only or is_service_claim,
                    eligible_for_product_claim=not service_only and not is_service_claim,
                    eligible_for_service_claim=is_service_claim,
                    blocked_reasons=blocked,
                    matched_rule="claim_experience_validation_v1",
                )
            )
        return candidates


class TaskCueSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.TASK_CUE

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        if _is_service_only(context):
            return []
        targets = _targets_from_topic_codes(context, self.signal_type, "mapped_task_codes_snapshot")
        targets.extend(_keyword_targets(context, self.signal_type))
        if _entity_depth(context) < 2:
            targets = [target for target in targets if _target_matches(context, target)]
        return [
            self._candidate(
                context,
                target,
                run_id=run_id,
                module_run_id=module_run_id,
                cue_basis=CommentSignalCueBasis.SCENARIO_ACTION_RESULT,
                polarity=_polarity(context),
                strength=_base_strength(context, target),
                hard_spec_policy=CommentHardSpecPolicy.EXPERIENCE_ONLY,
                eligible_for_task=True,
                matched_rule="task_cue_scene_action_result_v1",
            )
            for target in _unique_targets(targets)
        ]


class TargetGroupCueSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.TARGET_GROUP_CUE

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        targets = _keyword_targets(context, self.signal_type)
        basis = CommentSignalCueBasis.EXPLICIT_PEOPLE if context.entities.people else CommentSignalCueBasis.SCENARIO_INFERENCE
        if not context.entities.people and not context.entities.scenarios:
            return []
        return [
            self._candidate(
                context,
                target,
                run_id=run_id,
                module_run_id=module_run_id,
                cue_basis=basis,
                polarity=_polarity(context),
                strength=_base_strength(context, target, floor=Decimal("0.4200")),
                hard_spec_policy=CommentHardSpecPolicy.EXPERIENCE_ONLY,
                service_guardrail_flag=_is_service_only(context),
                eligible_for_group=True,
                matched_rule="target_group_cue_v1",
            )
            for target in _unique_targets(targets)
        ]


class BattlefieldSupportSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.BATTLEFIELD_SUPPORT

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        targets = _targets_from_topic_codes(context, self.signal_type, "mapped_battlefield_codes_snapshot")
        targets.extend(_keyword_targets(context, self.signal_type))
        service_only = _is_service_only(context)
        if service_only:
            targets = [target for target in targets if target.code == "BF_SERVICE_ASSURANCE"]
        return [
            self._candidate(
                context,
                target,
                run_id=run_id,
                module_run_id=module_run_id,
                cue_basis=CommentSignalCueBasis.TOPIC_MAPPING,
                polarity=_polarity(context),
                strength=_base_strength(context, target),
                hard_spec_policy=CommentHardSpecPolicy.SERVICE_ONLY if service_only else CommentHardSpecPolicy.EXPERIENCE_ONLY,
                service_guardrail_flag=service_only,
                eligible_for_battlefield=True,
                matched_rule="battlefield_comment_support_v1",
            )
            for target in _unique_targets(targets)
        ]


class PainPointSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.PAIN_POINT

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        if not context.entities.negative_terms and context.atom.sentiment_hint != CommentSentimentHint.NEGATIVE:
            return []
        return [
            self._candidate(
                context,
                target,
                run_id=run_id,
                module_run_id=module_run_id,
                cue_basis=CommentSignalCueBasis.NEGATIVE_RISK_PATTERN,
                polarity=CommentSignalPolarity.WEAKEN,
                strength=_base_strength(context, target, floor=Decimal("0.5000")),
                hard_spec_policy=CommentHardSpecPolicy.EXPERIENCE_ONLY,
                service_guardrail_flag=target.code == "RISK_SERVICE_DELIVERY",
                matched_rule="pain_point_risk_pattern_v1",
            )
            for target in _unique_targets(_keyword_targets(context, self.signal_type))
        ]


class PricePerceptionSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.PRICE_PERCEPTION

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        if not context.entities.price_terms:
            return []
        polarity = CommentSignalPolarity.WEAKEN if any(term in context.entities.negative_terms for term in ("太贵", "不值", "降价", "背刺")) else CommentSignalPolarity.SUPPORT
        return [
            self._candidate(
                context,
                target,
                run_id=run_id,
                module_run_id=module_run_id,
                cue_basis=CommentSignalCueBasis.PRICE_PATTERN,
                polarity=polarity,
                strength=_base_strength(context, target, floor=Decimal("0.4800")),
                hard_spec_policy=CommentHardSpecPolicy.MARKET_FACT_REQUIRED,
                matched_rule="price_perception_pattern_v1",
            )
            for target in _unique_targets(_keyword_targets(context, self.signal_type))
        ]


class ServiceSignalExtractor(BaseSignalExtractor):
    signal_type = CommentSignalType.SERVICE_SIGNAL

    def extract(self, context: SignalExtractionContext, *, run_id: str | None, module_run_id: str | None) -> list[CommentSignalCandidateRecord]:
        if not context.entities.service_terms and not _is_service_only(context):
            return []
        polarity = CommentSignalPolarity.WEAKEN if any(term in context.entities.negative_terms for term in ("配送慢", "安装差", "客服差", "售后差")) else CommentSignalPolarity.SUPPORT
        return [
            self._candidate(
                context,
                target,
                run_id=run_id,
                module_run_id=module_run_id,
                cue_basis=CommentSignalCueBasis.SERVICE_PATTERN,
                polarity=polarity,
                strength=_base_strength(context, target, floor=Decimal("0.5000")),
                hard_spec_policy=CommentHardSpecPolicy.SERVICE_ONLY,
                service_guardrail_flag=True,
                eligible_for_service_claim=True,
                matched_rule="service_signal_pattern_v1",
            )
            for target in _unique_targets(_keyword_targets(context, self.signal_type))
        ]


def _targets_from_topic_codes(
    context: SignalExtractionContext,
    signal_type: CommentSignalType,
    snapshot_field: str,
) -> list[SignalTargetDefinition]:
    by_code = context.seed.target_by_code(signal_type)
    result: list[SignalTargetDefinition] = []
    for topic in context.topic_hints:
        codes = getattr(topic, snapshot_field)
        for code in codes:
            target = by_code.get(code)
            if target is not None:
                result.append(target)
    return result


def _keyword_targets(context: SignalExtractionContext, signal_type: CommentSignalType) -> list[SignalTargetDefinition]:
    result: list[SignalTargetDefinition] = []
    for target in context.seed.targets_for(signal_type):
        if _target_matches(context, target):
            result.append(target)
    return result


def _target_matches(context: SignalExtractionContext, target: SignalTargetDefinition) -> list[str]:
    text = context.atom.sentence_text.lower()
    matched: list[str] = []
    for term in [*target.keywords, *target.aliases]:
        if term and term.lower() in text and term not in matched:
            matched.append(term)
    topic_codes = {topic.topic_code for topic in context.topic_hints}
    for topic_code in target.topic_codes:
        if topic_code in topic_codes and topic_code not in matched:
            matched.append(topic_code)
    return matched


def _unique_targets(targets: Iterable[SignalTargetDefinition]) -> list[SignalTargetDefinition]:
    result: list[SignalTargetDefinition] = []
    seen: set[str] = set()
    for target in targets:
        if target.code not in seen:
            seen.add(target.code)
            result.append(target)
    return result


def _dedupe_candidates(candidates: list[CommentSignalCandidateRecord]) -> list[CommentSignalCandidateRecord]:
    result: list[CommentSignalCandidateRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for candidate in candidates:
        key = (
            candidate.comment_evidence_id,
            str(candidate.signal_type),
            candidate.target_code_hint,
            str(candidate.polarity),
        )
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _polarity(context: SignalExtractionContext) -> CommentSignalPolarity:
    if context.atom.sentiment_hint == CommentSentimentHint.NEGATIVE or context.entities.negative_terms:
        return CommentSignalPolarity.WEAKEN
    if context.atom.sentiment_hint == CommentSentimentHint.POSITIVE or context.entities.experience_results:
        return CommentSignalPolarity.SUPPORT
    if context.atom.sentiment_hint == CommentSentimentHint.CONFLICT:
        return CommentSignalPolarity.MIXED
    if context.atom.sentiment_hint == CommentSentimentHint.NEUTRAL:
        return CommentSignalPolarity.NEUTRAL
    return CommentSignalPolarity.UNKNOWN


def _base_strength(
    context: SignalExtractionContext,
    target: SignalTargetDefinition,
    *,
    floor: Decimal = Decimal("0.3800"),
) -> Decimal:
    matched_terms = _target_matches(context, target)
    topic_bonus = Decimal("0.1200") if any(topic.topic_code in target.topic_codes for topic in context.topic_hints) else Decimal("0.0000")
    keyword_bonus = min(Decimal("0.1800"), Decimal("0.0400") * len(matched_terms))
    entity_bonus = min(Decimal("0.1500"), Decimal("0.0300") * _entity_depth(context))
    sentiment_bonus = Decimal("0.0800") if _polarity(context) in {CommentSignalPolarity.SUPPORT, CommentSignalPolarity.WEAKEN} else Decimal("0.0000")
    specificity = Decimal(str(context.atom.specificity_score)) * Decimal("0.2500")
    score = floor + topic_bonus + keyword_bonus + entity_bonus + sentiment_bonus + specificity
    if context.atom.low_value_flag:
        score -= Decimal("0.2500")
    return max(Decimal("0.0000"), min(Decimal("0.9500"), score.quantize(Decimal("0.0001"))))


def _candidate_confidence(
    context: SignalExtractionContext,
    strength: Decimal,
    service_guardrail_flag: bool,
    blocked_reasons: list[str],
) -> Decimal:
    confidence = (strength * Decimal("0.80")) + (Decimal(str(context.bundle.quality_profile.comment_usability_score)) * Decimal("0.20"))
    if context.atom.low_value_flag:
        confidence -= Decimal("0.2000")
    if service_guardrail_flag:
        confidence -= Decimal("0.0500")
    if blocked_reasons:
        confidence = min(confidence, Decimal("0.3400"))
    return max(Decimal("0.0000"), min(Decimal("0.9500"), confidence.quantize(Decimal("0.0001"))))


def _entity_depth(context: SignalExtractionContext) -> int:
    entities = context.entities
    groups = [
        entities.scenarios,
        entities.actions,
        entities.people,
        entities.objects,
        entities.experience_results,
        entities.constraints,
        entities.price_terms,
        entities.service_terms,
        entities.negative_terms,
    ]
    return sum(1 for group in groups if group)


def _is_service_only(context: SignalExtractionContext) -> bool:
    return (
        bool(context.entities.service_terms)
        and context.atom.primary_domain_hint
        in {
            CommentDomainHint.SERVICE_EXPERIENCE,
            CommentDomainHint.LOGISTICS_INSTALLATION,
        }
    ) or any(topic.service_guardrail_flag for topic in context.topic_hints)


def _target_mapping_reason(signal_type: CommentSignalType, cue_basis: CommentSignalCueBasis) -> str:
    return f"{signal_type.value} by {cue_basis.value}; M06 signal only, not final conclusion"


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{value.split(':')[-1][:32]}"


__all__ = [
    "BattlefieldSupportSignalExtractor",
    "ClaimValidationSignalExtractor",
    "CommentDownstreamSignalRecord",
    "CommentSignalExtractionPipeline",
    "PainPointSignalExtractor",
    "PricePerceptionSignalExtractor",
    "ServiceSignalExtractor",
    "TargetGroupCueSignalExtractor",
    "TaskCueSignalExtractor",
]
