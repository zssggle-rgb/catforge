"""M09 user task contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M09_RULE_VERSION,
    CORE3_M09_SEED_VERSION,
    Core3CategoryCode,
    Core3RunStatus,
    M09TaskCandidateStatus,
    M09TaskEvidenceDomain,
    M09TaskRelationLevel,
    M09TaskSupportLevel,
)


class M09BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M09SkuTaskCandidateRecord(M09BaseModel):
    sku_task_candidate_id: str = Field(min_length=1)
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
    task_code: str = Field(min_length=1)
    task_name_cn: str = Field(min_length=1)
    task_definition_cn: str = Field(min_length=1)
    candidate_status: M09TaskCandidateStatus = M09TaskCandidateStatus.ACTIVE
    candidate_sources_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    initial_candidate_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    candidate_reason_cn: str = Field(min_length=1)
    candidate_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    candidate_evidence_refs_json: list[str] = Field(default_factory=list)
    rejected_reason_json: dict[str, Any] = Field(default_factory=dict)
    blocked_reason_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M09_RULE_VERSION
    task_seed_version: str = CORE3_M09_SEED_VERSION
    task_seed_file_version: str = Field(min_length=1)
    task_seed_hash: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M09SkuTaskScoreRecord(M09BaseModel):
    sku_task_score_id: str = Field(min_length=1)
    sku_task_candidate_id: str | None = None
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
    task_code: str = Field(min_length=1)
    task_name_cn: str = Field(min_length=1)
    task_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    raw_task_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    relation_level: M09TaskRelationLevel = M09TaskRelationLevel.INSUFFICIENT
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    param_signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    claim_signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    market_signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    risk_penalty: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    cap_applied_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_domain_coverage_json: dict[str, Any] = Field(default_factory=dict)
    business_reason_cn: str = Field(min_length=1)
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    next_module_payload_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M09_RULE_VERSION
    task_seed_version: str = CORE3_M09_SEED_VERSION
    task_seed_file_version: str = Field(min_length=1)
    task_seed_hash: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M09SkuTaskEvidenceBreakdownRecord(M09BaseModel):
    sku_task_evidence_breakdown_id: str = Field(min_length=1)
    sku_task_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    task_code: str = Field(min_length=1)
    task_name_cn: str = Field(min_length=1)
    evidence_domain: M09TaskEvidenceDomain
    support_level: M09TaskSupportLevel = M09TaskSupportLevel.MISSING
    domain_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    domain_weight: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    weighted_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    dedup_comment_count: int = Field(default=0, ge=0)
    effective_sentence_count: int = Field(default=0, ge=0)
    evidence_refs_json: list[str] = Field(default_factory=list)
    source_feature_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_reason_cn: str = Field(min_length=1)
    domain_risk_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M09_RULE_VERSION
    task_seed_version: str = CORE3_M09_SEED_VERSION
    task_seed_file_version: str = Field(min_length=1)
    task_seed_hash: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M09SkuTaskReviewIssueRecord(M09BaseModel):
    sku_task_review_issue_id: str = Field(min_length=1)
    sku_task_score_id: str | None = None
    sku_task_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    task_code: str | None = None
    task_name_cn: str | None = None
    issue_type: str = Field(min_length=1)
    issue_severity: str = "warning"
    issue_status: str = "open"
    issue_reason_cn: str = Field(min_length=1)
    issue_detail_json: dict[str, Any] = Field(default_factory=dict)
    affected_output_json: dict[str, Any] = Field(default_factory=dict)
    evidence_refs_json: list[str] = Field(default_factory=list)
    suggested_action_cn: str = Field(min_length=1)
    rule_version: str = CORE3_M09_RULE_VERSION
    task_seed_version: str = CORE3_M09_SEED_VERSION
    task_seed_file_version: str = Field(min_length=1)
    task_seed_hash: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M09TaskDomainEvidence:
    domain: M09TaskEvidenceDomain
    support_level: M09TaskSupportLevel
    score: Decimal
    weight: Decimal
    reason_cn: str
    evidence_refs: list[str] = field(default_factory=list)
    source_feature_refs: list[dict[str, Any]] = field(default_factory=list)
    risk_json: dict[str, Any] = field(default_factory=dict)
    dedup_comment_count: int = 0
    effective_sentence_count: int = 0


@dataclass(frozen=True)
class M09TaskBuildResult:
    candidate: M09SkuTaskCandidateRecord
    score: M09SkuTaskScoreRecord
    breakdowns: list[M09SkuTaskEvidenceBreakdownRecord]
    review_issues: list[M09SkuTaskReviewIssueRecord]


@dataclass(frozen=True)
class M09ServiceResult:
    candidates: list[M09SkuTaskCandidateRecord]
    scores: list[M09SkuTaskScoreRecord]
    breakdowns: list[M09SkuTaskEvidenceBreakdownRecord]
    review_issues: list[M09SkuTaskReviewIssueRecord]
    summary: dict[str, Any]
    warnings: list[str]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
