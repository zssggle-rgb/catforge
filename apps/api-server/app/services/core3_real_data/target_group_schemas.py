"""M10 target-group contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M10_RULE_VERSION,
    CORE3_M10_SEED_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M10TargetGroupCandidateStatus,
    M10TargetGroupEvidenceDomain,
    M10TargetGroupRelationLevel,
    M10TargetGroupSupportLevel,
)


class M10BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M10SkuTargetGroupCandidateRecord(M10BaseModel):
    sku_target_group_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_signal_profile_id: str | None = None
    sku_downstream_feature_view_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str = Field(min_length=1)
    target_group_name_cn: str = Field(min_length=1)
    target_group_definition_cn: str = Field(min_length=1)
    candidate_source_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    source_task_codes_json: list[str] = Field(default_factory=list)
    candidate_initial_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    candidate_reason_cn: str = Field(min_length=1)
    candidate_status: M10TargetGroupCandidateStatus = M10TargetGroupCandidateStatus.ACTIVE
    reject_reason_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_seed_version: str = CORE3_M10_SEED_VERSION
    target_group_seed_file_version: str = Field(min_length=1)
    target_group_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M10_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M10SkuTargetGroupScoreRecord(M10BaseModel):
    sku_target_group_score_id: str = Field(min_length=1)
    sku_target_group_candidate_id: str | None = None
    sku_signal_profile_id: str | None = None
    sku_downstream_feature_view_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str = Field(min_length=1)
    target_group_name_cn: str = Field(min_length=1)
    target_group_definition_cn: str = Field(min_length=1)
    task_support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_group_signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_channel_fit_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    market_validation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    service_side_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    raw_target_group_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    risk_penalty: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    target_group_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    relation_level: M10TargetGroupRelationLevel = M10TargetGroupRelationLevel.INSUFFICIENT
    relation_reason_json: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    evidence_domain_count: int = Field(default=0, ge=0)
    effective_domain_json: dict[str, Any] = Field(default_factory=dict)
    source_task_scores_json: list[dict[str, Any]] = Field(default_factory=list)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    cap_rule_applied_json: list[dict[str, Any]] = Field(default_factory=list)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_seed_version: str = CORE3_M10_SEED_VERSION
    target_group_seed_file_version: str = Field(min_length=1)
    target_group_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M10_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M10SkuTargetGroupEvidenceBreakdownRecord(M10BaseModel):
    sku_target_group_evidence_breakdown_id: str = Field(min_length=1)
    sku_target_group_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str = Field(min_length=1)
    target_group_name_cn: str = Field(min_length=1)
    evidence_domain: M10TargetGroupEvidenceDomain
    support_level: M10TargetGroupSupportLevel = M10TargetGroupSupportLevel.MISSING
    domain_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    domain_weight: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    weighted_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    source_feature_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_reason_cn: str = Field(min_length=1)
    domain_risk_json: dict[str, Any] = Field(default_factory=dict)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_seed_version: str = CORE3_M10_SEED_VERSION
    target_group_seed_file_version: str = Field(min_length=1)
    target_group_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M10_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M10SkuTargetGroupReviewIssueRecord(M10BaseModel):
    sku_target_group_review_issue_id: str = Field(min_length=1)
    sku_target_group_score_id: str | None = None
    sku_target_group_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str | None = None
    target_group_name_cn: str | None = None
    issue_type: str = Field(min_length=1)
    issue_severity: str = "warning"
    issue_status: str = "open"
    issue_reason_cn: str = Field(min_length=1)
    issue_detail_json: dict[str, Any] = Field(default_factory=dict)
    affected_output_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_action_cn: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_seed_version: str = CORE3_M10_SEED_VERSION
    target_group_seed_file_version: str = Field(min_length=1)
    target_group_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M10_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M10TargetGroupDomainEvidence:
    domain: M10TargetGroupEvidenceDomain
    support_level: M10TargetGroupSupportLevel
    score: Decimal
    weight: Decimal
    reason_cn: str
    evidence_ids: list[str] = field(default_factory=list)
    source_feature_refs: list[dict[str, Any]] = field(default_factory=list)
    risk_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class M10TargetGroupBuildResult:
    candidate: M10SkuTargetGroupCandidateRecord
    score: M10SkuTargetGroupScoreRecord
    breakdowns: list[M10SkuTargetGroupEvidenceBreakdownRecord]
    review_issues: list[M10SkuTargetGroupReviewIssueRecord]


@dataclass(frozen=True)
class M10ServiceResult:
    candidates: list[M10SkuTargetGroupCandidateRecord]
    scores: list[M10SkuTargetGroupScoreRecord]
    breakdowns: list[M10SkuTargetGroupEvidenceBreakdownRecord]
    review_issues: list[M10SkuTargetGroupReviewIssueRecord]
    summary: dict[str, Any]
    warnings: list[str]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
