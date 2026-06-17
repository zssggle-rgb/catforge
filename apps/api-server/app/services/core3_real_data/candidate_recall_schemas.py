"""M12 candidate recall contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M12_RULE_VERSION,
    Core3CategoryCode,
    Core3RunStatus,
    M12PriceRelation,
    M12RecallSource,
    M12RecallStatus,
    M12RecallStrength,
    M12RelationType,
    M12SampleStatus,
    M12SizeRelation,
    M12SupportLevel,
)


class M12BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M12CandidateRecallRunRecord(M12BaseModel):
    candidate_recall_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    run_key: str = Field(min_length=1)
    target_sku_count: int = Field(default=0, ge=0)
    candidate_pair_count: int = Field(default=0, ge=0)
    reason_count: int = Field(default=0, ge=0)
    feature_snapshot_count: int = Field(default=0, ge=0)
    review_issue_count: int = Field(default=0, ge=0)
    strong_pair_count: int = Field(default=0, ge=0)
    medium_pair_count: int = Field(default=0, ge=0)
    weak_pair_count: int = Field(default=0, ge=0)
    review_only_pair_count: int = Field(default=0, ge=0)
    recall_status: M12RecallStatus = M12RecallStatus.SUCCESS
    target_scope_json: list[str] = Field(default_factory=list)
    source_module_versions_json: dict[str, Any] = Field(default_factory=dict)
    summary_json: dict[str, Any] = Field(default_factory=dict)
    warning_json: list[str] = Field(default_factory=list)
    boundary_note_cn: str = Field(min_length=1)
    rule_version: str = CORE3_M12_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M12CandidatePoolRecord(M12BaseModel):
    candidate_pool_id: str = Field(min_length=1)
    candidate_recall_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    same_brand_flag: bool = False
    primary_relation_type: M12RelationType = M12RelationType.SCENARIO_SUBSTITUTE
    relation_types_json: list[str] = Field(default_factory=list)
    recall_sources_json: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    recall_strength: M12RecallStrength = M12RecallStrength.WEAK
    recall_priority_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_quality_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_relation: M12PriceRelation = M12PriceRelation.UNKNOWN
    size_relation: M12SizeRelation = M12SizeRelation.UNKNOWN
    sample_status: M12SampleStatus = M12SampleStatus.UNKNOWN
    role_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    score_parts_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    target_profile_hash: str = Field(min_length=1)
    candidate_profile_hash: str = Field(min_length=1)
    feature_snapshot_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M12_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M12CandidateRecallReasonRecord(M12BaseModel):
    candidate_recall_reason_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    candidate_recall_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    recall_source: M12RecallSource
    relation_type: M12RelationType
    reason_code: str = Field(min_length=1)
    support_level: M12SupportLevel = M12SupportLevel.WEAK
    support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    reason_summary_cn: str = Field(min_length=1)
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    rule_version: str = CORE3_M12_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M12CandidateFeatureSnapshotRecord(M12BaseModel):
    candidate_feature_snapshot_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    candidate_recall_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    size_feature_json: dict[str, Any] = Field(default_factory=dict)
    price_feature_json: dict[str, Any] = Field(default_factory=dict)
    channel_feature_json: dict[str, Any] = Field(default_factory=dict)
    market_feature_json: dict[str, Any] = Field(default_factory=dict)
    param_feature_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_overlap_json: dict[str, Any] = Field(default_factory=dict)
    task_overlap_json: dict[str, Any] = Field(default_factory=dict)
    audience_overlap_json: dict[str, Any] = Field(default_factory=dict)
    claim_value_overlap_json: dict[str, Any] = Field(default_factory=dict)
    quality_feature_json: dict[str, Any] = Field(default_factory=dict)
    m13_component_input_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    target_profile_hash: str = Field(min_length=1)
    candidate_profile_hash: str = Field(min_length=1)
    feature_snapshot_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M12_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M12CandidateRecallReviewIssueRecord(M12BaseModel):
    candidate_recall_review_issue_id: str = Field(min_length=1)
    candidate_pool_id: str | None = None
    candidate_feature_snapshot_id: str | None = None
    candidate_recall_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = ""
    issue_type: str = Field(min_length=1)
    issue_level: str = "warning"
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str = Field(min_length=1)
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M12_RULE_VERSION
    resolved_status: str = "open"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M12BuildArtifacts:
    run: M12CandidateRecallRunRecord
    pools: tuple[M12CandidatePoolRecord, ...] = field(default_factory=tuple)
    reasons: tuple[M12CandidateRecallReasonRecord, ...] = field(default_factory=tuple)
    snapshots: tuple[M12CandidateFeatureSnapshotRecord, ...] = field(default_factory=tuple)
    review_issues: tuple[M12CandidateRecallReviewIssueRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class M12ServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    warnings: list[str]
    run: M12CandidateRecallRunRecord
    pools: list[M12CandidatePoolRecord]
    reasons: list[M12CandidateRecallReasonRecord]
    snapshots: list[M12CandidateFeatureSnapshotRecord]
    review_issues: list[M12CandidateRecallReviewIssueRecord]
    summary: dict[str, Any]
