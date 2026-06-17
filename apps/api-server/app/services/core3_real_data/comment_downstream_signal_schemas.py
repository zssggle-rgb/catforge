"""M06 comment downstream signal contracts.

M06 turns M05 comment evidence into downstream-specific signals. It does not
produce final tasks, target groups, battlefields, competitors, or report
conclusions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.core3_real_data.constants import (
    COMMENT_SIGNAL_TARGET_PREFIX,
    CORE3_M06_MODULE_VERSION,
    CORE3_M06_RULE_VERSION,
    CORE3_M06_SEED_VERSION,
    CommentDomainHint,
    CommentHardSpecPolicy,
    CommentSampleStatus,
    CommentSentimentHint,
    CommentSignalCueBasis,
    CommentSignalPolarity,
    CommentSignalReviewReasonCode,
    CommentSignalStrengthLevel,
    CommentSignalType,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3ModuleCode,
    Core3ReviewSeverity,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchType,
)


class M06BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def _non_empty(values: list[str], field_name: str) -> list[str]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain empty values")
    return values


def confidence_level(score: Decimal | float) -> Core3ConfidenceLevel:
    value = float(score)
    if value >= 0.75:
        return Core3ConfidenceLevel.HIGH
    if value >= 0.55:
        return Core3ConfidenceLevel.MEDIUM
    if value > 0:
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def signal_strength_level(score: Decimal | float, blocked: bool = False) -> CommentSignalStrengthLevel:
    if blocked:
        return CommentSignalStrengthLevel.BLOCKED
    value = float(score)
    if value >= 0.75:
        return CommentSignalStrengthLevel.STRONG
    if value >= 0.55:
        return CommentSignalStrengthLevel.MEDIUM
    if value >= 0.35:
        return CommentSignalStrengthLevel.WEAK
    return CommentSignalStrengthLevel.BLOCKED


class M06RunRequest(M06BaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M06_MODULE_VERSION
    seed_version: str = CORE3_M06_SEED_VERSION
    rule_version: str = CORE3_M06_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    signal_types: list[CommentSignalType] = Field(default_factory=list)
    sku_batch_size: int = Field(default=1, ge=1, le=20)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_sku_scope(cls, values: list[str]) -> list[str]:
        return _non_empty(values, "sku_scope")


class M06RunResult(M06BaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M06
    status: Core3RunStatus
    candidate_count: int = Field(default=0, ge=0)
    downstream_signal_count: int = Field(default=0, ge=0)
    sku_profile_count: int = Field(default=0, ge=0)
    ready_sku_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SignalTargetDefinition(M06BaseModel):
    signal_type: CommentSignalType
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    group_hint: str | None = None
    keywords: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    topic_codes: list[str] = Field(default_factory=list)
    mapped_claim_codes: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_code_prefix(self) -> "SignalTargetDefinition":
        expected_prefix = COMMENT_SIGNAL_TARGET_PREFIX[CommentSignalType(self.signal_type)]
        if not self.code.startswith(expected_prefix):
            raise ValueError(f"{self.code} must start with {expected_prefix} for {self.signal_type}")
        return self


class M06SignalSeedBundle(M06BaseModel):
    seed_version: str = CORE3_M06_SEED_VERSION
    asset_version: str = "default"
    seed_content_hash: str = Field(min_length=1)
    targets: dict[CommentSignalType, list[SignalTargetDefinition]]
    topic_to_claim_codes: dict[str, list[str]] = Field(default_factory=dict)
    topic_to_task_codes: dict[str, list[str]] = Field(default_factory=dict)
    topic_to_battlefield_codes: dict[str, list[str]] = Field(default_factory=dict)
    topic_to_service_guardrail: dict[str, bool] = Field(default_factory=dict)

    def targets_for(self, signal_type: CommentSignalType | str) -> list[SignalTargetDefinition]:
        return list(self.targets.get(CommentSignalType(signal_type), []))

    def target_by_code(self, signal_type: CommentSignalType | str) -> dict[str, SignalTargetDefinition]:
        return {target.code: target for target in self.targets_for(signal_type)}


class M06CommentAtomInput(M06BaseModel):
    comment_evidence_id: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_text_hash: str | None = None
    sentence_hash: str | None = None
    sentence_text: str = Field(min_length=1)
    normalized_sentence_text: str = Field(min_length=1)
    specificity_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    domain_hints: list[dict[str, Any]] = Field(default_factory=list)
    primary_domain_hint: CommentDomainHint = CommentDomainHint.UNKNOWN
    low_value_flag: bool = False
    duplicate_group_id: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    source_m05_evidence_ids: list[str] = Field(default_factory=list)
    source_m02_evidence_ids: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)


class M06TopicHintInput(M06BaseModel):
    topic_hint_id: str = Field(min_length=1)
    comment_evidence_id: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    topic_code: str = Field(min_length=1)
    topic_name: str = Field(min_length=1)
    topic_group: str = Field(min_length=1)
    matched_terms: list[str] = Field(default_factory=list)
    polarity_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    topic_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    service_guardrail_flag: bool = False
    mapped_claim_codes_snapshot: list[str] = Field(default_factory=list)
    mapped_task_codes_snapshot: list[str] = Field(default_factory=list)
    mapped_battlefield_codes_snapshot: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)


class M06QualityProfileInput(M06BaseModel):
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_unit_count: int = Field(default=0, ge=0)
    usable_sentence_count: int = Field(default=0, ge=0)
    sample_status: CommentSampleStatus = CommentSampleStatus.UNKNOWN
    comment_usability_score: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    warning_flags: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    downstream_ready: bool = False
    result_hash: str = Field(min_length=1)


class M06SkuInputBundle(M06BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    quality_profile: M06QualityProfileInput
    atoms: list[M06CommentAtomInput] = Field(default_factory=list)
    topic_hints_by_atom: dict[str, list[M06TopicHintInput]] = Field(default_factory=dict)
    optional_param_context_json: dict[str, Any] = Field(default_factory=dict)
    optional_claim_context_json: dict[str, Any] = Field(default_factory=dict)
    input_fingerprint: str = Field(min_length=1)


class CommentEntityExtraction(M06BaseModel):
    scenarios: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    experience_results: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    price_terms: list[str] = Field(default_factory=list)
    service_terms: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)


class SignalExtractionContext(M06BaseModel):
    bundle: M06SkuInputBundle
    atom: M06CommentAtomInput
    topic_hints: list[M06TopicHintInput] = Field(default_factory=list)
    entities: CommentEntityExtraction
    seed: M06SignalSeedBundle


class CommentSignalCandidateRecord(M06BaseModel):
    signal_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    signal_candidate_key: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    comment_evidence_id: str = Field(min_length=1)
    comment_text_hash: str | None = None
    sentence_hash: str | None = None
    sentence_text: str = Field(min_length=1)
    signal_type: CommentSignalType
    target_code_hint: str = Field(min_length=1)
    target_name_hint: str = Field(min_length=1)
    target_group_hint: str | None = None
    polarity: CommentSignalPolarity = CommentSignalPolarity.UNKNOWN
    signal_strength: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    signal_strength_level: CommentSignalStrengthLevel = CommentSignalStrengthLevel.BLOCKED
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    specificity_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    domain_hints: list[dict[str, Any]] = Field(default_factory=list)
    primary_domain_hint: CommentDomainHint = CommentDomainHint.UNKNOWN
    topic_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    matched_entities_json: dict[str, Any] = Field(default_factory=dict)
    matched_rules_json: dict[str, Any] = Field(default_factory=dict)
    cue_basis: CommentSignalCueBasis
    hard_spec_policy: CommentHardSpecPolicy = CommentHardSpecPolicy.EXPERIENCE_ONLY
    service_guardrail_flag: bool = False
    eligible_for_product_claim: bool = False
    eligible_for_service_claim: bool = False
    eligible_for_task: bool = False
    eligible_for_group: bool = False
    eligible_for_battlefield: bool = False
    low_value_flag: bool = False
    duplicate_group_id: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    source_m05_evidence_ids: list[str] = Field(default_factory=list)
    source_m02_evidence_ids: list[str] = Field(default_factory=list)
    optional_param_context_json: dict[str, Any] = Field(default_factory=dict)
    optional_claim_context_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M06_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_target_prefix(self) -> "CommentSignalCandidateRecord":
        expected = COMMENT_SIGNAL_TARGET_PREFIX[CommentSignalType(self.signal_type)]
        if not self.target_code_hint.startswith(expected):
            raise ValueError(f"target_code_hint must start with {expected}")
        return self


class CommentDownstreamSignalRecord(M06BaseModel):
    signal_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    signal_key: str = Field(min_length=1)
    signal_type: CommentSignalType
    target_code_hint: str = Field(min_length=1)
    target_name_hint: str = Field(min_length=1)
    target_group_hint: str | None = None
    polarity: CommentSignalPolarity = CommentSignalPolarity.UNKNOWN
    mention_count: int = Field(default=0, ge=0)
    sentence_count: int = Field(default=0, ge=0)
    valid_comment_unit_count: int = Field(default=0, ge=0)
    usable_sentence_count: int = Field(default=0, ge=0)
    mention_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    sentence_mention_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    neutral_count: int = Field(default=0, ge=0)
    positive_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    negative_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    mixed_flag: bool = False
    signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    signal_level: CommentSignalStrengthLevel = CommentSignalStrengthLevel.BLOCKED
    specificity_avg: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_quality_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sample_status: CommentSampleStatus = CommentSampleStatus.UNKNOWN
    comment_quality_flags: list[str] = Field(default_factory=list)
    representative_phrases: list[str] = Field(default_factory=list)
    top_candidate_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    service_guardrail_flag: bool = False
    hard_spec_policy: CommentHardSpecPolicy = CommentHardSpecPolicy.EXPERIENCE_ONLY
    downstream_usage_policy_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary: str = ""
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    rule_version: str = CORE3_M06_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkuCommentSignalProfileRecord(M06BaseModel):
    sku_comment_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    profile_key: str = Field(min_length=1)
    comment_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    claim_validation_summary_json: dict[str, Any] = Field(default_factory=dict)
    task_cue_summary_json: dict[str, Any] = Field(default_factory=dict)
    target_group_cue_summary_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_support_summary_json: dict[str, Any] = Field(default_factory=dict)
    pain_risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    price_perception_summary_json: dict[str, Any] = Field(default_factory=dict)
    service_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    strong_signal_count: int = Field(default=0, ge=0)
    medium_signal_count: int = Field(default=0, ge=0)
    weak_signal_count: int = Field(default=0, ge=0)
    blocked_signal_count: int = Field(default=0, ge=0)
    claim_validation_ready: bool = False
    task_cue_ready: bool = False
    target_group_cue_ready: bool = False
    battlefield_support_ready: bool = False
    comment_signal_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    quality_flags: list[str] = Field(default_factory=list)
    review_issue_summary_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M06_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SignalExtractorResult(M06BaseModel):
    candidates: list[CommentSignalCandidateRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CommentSignalReviewIssue(M06BaseModel):
    issue_code: str = Field(min_length=1)
    reason_code: CommentSignalReviewReasonCode
    severity: Core3ReviewSeverity
    object_type: str = Field(min_length=1)
    object_id: str | None = None
    sku_code: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    message_cn: str = Field(min_length=1)
    suggestion_cn: str | None = None
    review_required: bool = True
    confidence: Decimal | None = Field(default=None, ge=0, le=1)


class M06DownstreamImpact(M06BaseModel):
    source_module: Core3ModuleCode = Core3ModuleCode.M06
    target_module: Core3ModuleCode
    impact_type: str = Field(min_length=1)
    sku_code: str | None = None
    reason_cn: str = Field(min_length=1)
    source_record_ids: list[str] = Field(default_factory=list)
    impact_level: str = "medium"
