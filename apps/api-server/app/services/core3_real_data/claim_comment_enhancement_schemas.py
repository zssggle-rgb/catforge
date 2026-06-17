"""M04b claim comment enhancement typed contracts.

M04b combines M04a base claim activation with M06 claim-validation comment
signals. It does not produce final task, target-group, battlefield,
competitor, selection, or report conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.core3_real_data.constants import (
    CORE3_M04B_MODULE_VERSION,
    CORE3_M04B_RULE_VERSION,
    CORE3_M04B_SEED_VERSION,
    ClaimCommentActivationBasis,
    ClaimCommentActivationLevel,
    ClaimCommentDownstreamPolicy,
    ClaimCommentEffect,
    ClaimCommentEnhancedType,
    ClaimCommentIssueSeverity,
    ClaimCommentIssueStatus,
    ClaimCommentIssueType,
    ClaimPerceptionStatus,
    CommentHardSpecPolicy,
    CommentSignalPolarity,
    CommentSignalStrengthLevel,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3ModuleCode,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchType,
)


class M04bBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def _non_empty(values: list[str], field_name: str) -> list[str]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain empty values")
    return values


def clamp_decimal(value: Decimal | float | int | str, places: str = "0.0000") -> Decimal:
    numeric = Decimal(str(value))
    numeric = max(Decimal("0"), min(Decimal("1"), numeric))
    return numeric.quantize(Decimal(places))


def confidence_level(score: Decimal | float) -> Core3ConfidenceLevel:
    value = float(score)
    if value >= 0.75:
        return Core3ConfidenceLevel.HIGH
    if value >= 0.55:
        return Core3ConfidenceLevel.MEDIUM
    if value > 0:
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


class M04bRunRequest(M04bBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M04B_MODULE_VERSION
    seed_version: str = CORE3_M04B_SEED_VERSION
    rule_version: str = CORE3_M04B_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    claim_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope", "claim_scope")
    @classmethod
    def validate_string_lists(cls, values: list[str]) -> list[str]:
        return _non_empty(values, "M04b scope list values")


class M04bRunResult(M04bBaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M04B
    status: Core3RunStatus
    processed_sku_count: int = Field(default=0, ge=0)
    validation_count: int = Field(default=0, ge=0)
    activation_count: int = Field(default=0, ge=0)
    issue_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    blocked_claim_count: int = Field(default=0, ge=0)
    changed_sku_codes: list[str] = Field(default_factory=list)
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ClaimDefinitionInput(M04bBaseModel):
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str = Field(min_length=1)
    claim_type: str = "mixed"
    m04b_claim_type: ClaimCommentEnhancedType = ClaimCommentEnhancedType.UNKNOWN
    hard_spec_protection_flag: bool = False
    value_requires_market_validation: bool = False
    service_claim_flag: bool = False
    keywords: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)

    @field_validator("claim_code")
    @classmethod
    def validate_claim_code(cls, value: str) -> str:
        if not value.startswith("CLAIM_"):
            raise ValueError("claim_code must start with CLAIM_")
        return value


class ClaimTypePolicy(M04bBaseModel):
    claim_code: str = Field(min_length=1)
    m04b_claim_type: ClaimCommentEnhancedType
    base_weight: Decimal = Field(ge=0, le=1)
    comment_weight: Decimal = Field(ge=0, le=1)
    risk_penalty_weight: Decimal = Field(ge=0, le=1)
    hard_spec_protection_flag: bool = False
    value_requires_market_validation: bool = False
    service_claim_flag: bool = False


class M04bClaimBaseInput(M04bBaseModel):
    claim_activation_base_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str = Field(min_length=1)
    claim_type: str = "mixed"
    param_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    promo_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    base_activation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    base_activation_level: str = "unknown"
    base_activation_basis: str = "insufficient"
    missing_signals: list[str] = Field(default_factory=list)
    conflict_flags: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    promo_evidence_ids: list[str] = Field(default_factory=list)
    quality_evidence_ids: list[str] = Field(default_factory=list)
    activation_hash: str = Field(min_length=1)

    @field_validator("claim_code")
    @classmethod
    def validate_claim_code(cls, value: str) -> str:
        if not value.startswith("CLAIM_"):
            raise ValueError("claim_code must start with CLAIM_")
        return value


class M04bClaimSourceStatusInput(M04bBaseModel):
    claim_source_status_id: str | None = None
    sku_code: str = Field(min_length=1)
    claim_source_status: str = "claim_data_insufficient"
    structured_claim_count: int = Field(default=0, ge=0)
    param_only_claim_count: int = Field(default=0, ge=0)
    missing_signals: list[str] = Field(default_factory=list)
    conflict_summary_json: dict[str, Any] = Field(default_factory=dict)
    status_hash: str = Field(min_length=1)


class M04bClaimValidationSignalInput(M04bBaseModel):
    signal_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str | None = None
    polarity: CommentSignalPolarity = CommentSignalPolarity.UNKNOWN
    mention_count: int = Field(default=0, ge=0)
    sentence_count: int = Field(default=0, ge=0)
    valid_comment_unit_count: int = Field(default=0, ge=0)
    mention_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    positive_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    negative_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    signal_level: CommentSignalStrengthLevel = CommentSignalStrengthLevel.WEAK
    specificity_avg: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_quality_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    representative_phrases: list[str] = Field(default_factory=list)
    top_candidate_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    service_guardrail_flag: bool = False
    hard_spec_policy: CommentHardSpecPolicy = CommentHardSpecPolicy.EXPERIENCE_ONLY
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    result_hash: str = Field(min_length=1)

    @field_validator("claim_code")
    @classmethod
    def validate_claim_code(cls, value: str) -> str:
        if not value.startswith("CLAIM_"):
            raise ValueError("M04b only accepts CLAIM_* comment-validation signals")
        return value


class M04bSkuInputBundle(M04bBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    source_status: M04bClaimSourceStatusInput | None = None
    base_claims: list[M04bClaimBaseInput] = Field(default_factory=list)
    claim_validation_signals: list[M04bClaimValidationSignalInput] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)


class ClaimCommentValidationRecord(M04bBaseModel):
    claim_comment_validation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    validation_key: str = Field(min_length=1)
    claim_activation_base_id: str | None = None
    claim_source_status_id: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str = Field(min_length=1)
    m04b_claim_type: ClaimCommentEnhancedType = ClaimCommentEnhancedType.UNKNOWN
    base_activation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    base_activation_level: str = "unknown"
    base_activation_basis: str = "insufficient"
    param_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    promo_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    claim_source_status: str = "claim_data_insufficient"
    mention_count: int = Field(default=0, ge=0)
    sentence_count: int = Field(default=0, ge=0)
    valid_comment_unit_count: int = Field(default=0, ge=0)
    mention_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    positive_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    negative_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    specificity_avg: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_quality_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    domain_match_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_validation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_risk_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_effect: ClaimCommentEffect = ClaimCommentEffect.NEUTRAL
    perception_status: ClaimPerceptionStatus = ClaimPerceptionStatus.INSUFFICIENT_COMMENT
    hard_spec_protection_flag: bool = False
    service_guardrail_flag: bool = False
    comment_only_flag: bool = False
    weak_perception_flag: bool = False
    contradiction_flag: bool = False
    representative_phrases: list[dict[str, Any] | str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    comment_candidate_ids: list[str] = Field(default_factory=list)
    comment_evidence_ids: list[str] = Field(default_factory=list)
    base_evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    promo_evidence_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    rule_version: str = CORE3_M04B_RULE_VERSION
    seed_version: str = CORE3_M04B_SEED_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class SkuClaimActivationRecord(M04bBaseModel):
    claim_activation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    activation_key: str = Field(min_length=1)
    claim_activation_base_id: str | None = None
    claim_comment_validation_id: str | None = None
    claim_source_status_id: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str = Field(min_length=1)
    m04b_claim_type: ClaimCommentEnhancedType = ClaimCommentEnhancedType.UNKNOWN
    param_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    promo_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    base_activation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_validation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_risk_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    final_activation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    base_activation_level: str = "unknown"
    activation_level: ClaimCommentActivationLevel = ClaimCommentActivationLevel.UNKNOWN
    activation_basis: ClaimCommentActivationBasis = ClaimCommentActivationBasis.INSUFFICIENT
    perception_status: ClaimPerceptionStatus = ClaimPerceptionStatus.INSUFFICIENT_COMMENT
    claim_source_status: str = "claim_data_insufficient"
    comment_effect: ClaimCommentEffect = ClaimCommentEffect.NEUTRAL
    hard_spec_protection_flag: bool = False
    service_guardrail_flag: bool = False
    missing_structured_claim_flag: bool = False
    param_only_flag: bool = False
    promo_only_flag: bool = False
    comment_only_flag: bool = False
    weak_perception_flag: bool = False
    contradiction_flag: bool = False
    value_requires_market_validation: bool = False
    downstream_usage_policy_json: dict[str, Any] = Field(default_factory=dict)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals: list[str] = Field(default_factory=list)
    conflict_flags: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    promo_evidence_ids: list[str] = Field(default_factory=list)
    comment_evidence_ids: list[str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    representative_phrases: list[dict[str, Any] | str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    rule_version: str = CORE3_M04B_RULE_VERSION
    seed_version: str = CORE3_M04B_SEED_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_level_caps(self) -> "SkuClaimActivationRecord":
        if self.comment_only_flag and self.activation_level == ClaimCommentActivationLevel.HIGH:
            raise ValueError("comment_only activation must not be high")
        if self.param_only_flag and self.activation_level == ClaimCommentActivationLevel.HIGH:
            raise ValueError("param_only activation must not be high")
        return self


class ClaimCommentReviewIssueRecord(M04bBaseModel):
    issue_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    issue_key: str = Field(min_length=1)
    claim_activation_id: str | None = None
    claim_comment_validation_id: str | None = None
    claim_activation_base_id: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    issue_type: ClaimCommentIssueType
    severity: ClaimCommentIssueSeverity = ClaimCommentIssueSeverity.WARNING
    business_note: str = Field(min_length=1)
    technical_note: str | None = None
    suggested_action: str = Field(min_length=1)
    downstream_policy: ClaimCommentDownstreamPolicy = ClaimCommentDownstreamPolicy.CONTINUE_WITH_WARNING
    evidence_ids: list[str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    issue_status: ClaimCommentIssueStatus = ClaimCommentIssueStatus.OPEN
    rule_version: str = CORE3_M04B_RULE_VERSION
    seed_version: str = CORE3_M04B_SEED_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = True
    review_status: Core3ReviewStatus = Core3ReviewStatus.REVIEW_REQUIRED
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ClaimCommentEnhancementBuildResult:
    validations: list[ClaimCommentValidationRecord]
    activations: list[SkuClaimActivationRecord]
    issues: list[ClaimCommentReviewIssueRecord]
    warnings: list[str]
    summary: dict[str, Any]
