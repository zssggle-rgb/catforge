"""M13 component scoring contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M13_COMPONENT_RULE_VERSION,
    CORE3_M13_ROLE_RULE_VERSION,
    CORE3_M13_RULE_VERSION,
    Core3CategoryCode,
    Core3RunStatus,
    M13ComponentCode,
    M13IssueLevel,
    M13IssueScope,
    M13RoleCode,
    M13SampleStatus,
    M13SupportLevel,
)


class M13BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M13CandidateComponentScoreRecord(M13BaseModel):
    candidate_component_score_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    feature_snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    same_brand_flag: bool = False
    candidate_relation_types_json: list[str] = Field(default_factory=list)
    candidate_role_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    recall_strength: str = "weak"
    base_comparability_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    battlefield_fit_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    task_overlap_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    audience_overlap_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_position_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_advantage_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    size_fit_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    channel_overlap_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    param_similarity_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    param_superiority_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    claim_confrontation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    claim_superiority_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    claim_threshold_sufficiency_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    market_threat_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sales_amount_strength_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_perception_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_trend_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_completeness_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    component_scores_json: dict[str, Any] = Field(default_factory=dict)
    component_total_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    direct_fight_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_volume_pressure_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    benchmark_potential_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    configuration_pressure_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    service_reference_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sample_status: M13SampleStatus = M13SampleStatus.UNKNOWN
    main_strengths_json: list[dict[str, Any] | str] = Field(default_factory=list)
    main_gaps_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    positive_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    target_profile_hash: str = Field(min_length=1)
    candidate_profile_hash: str = Field(min_length=1)
    feature_snapshot_hash: str = Field(min_length=1)
    component_rule_version: str = CORE3_M13_COMPONENT_RULE_VERSION
    role_rule_version: str = CORE3_M13_ROLE_RULE_VERSION
    rule_version: str = CORE3_M13_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M13CandidateRoleScoreRecord(M13BaseModel):
    candidate_role_score_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    feature_snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    role_code: M13RoleCode
    role_name_cn: str = Field(min_length=1)
    role_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    role_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    role_rank_hint: int | None = None
    auto_select_eligible: bool = False
    auto_select_block_reason: str | None = None
    role_business_reason_cn: str = Field(min_length=1)
    role_business_reason_short_cn: str = Field(min_length=1)
    formula_version: str = CORE3_M13_ROLE_RULE_VERSION
    component_contribution_json: dict[str, Any] = Field(default_factory=dict)
    positive_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    rule_version: str = CORE3_M13_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M13CandidateComponentExplanationRecord(M13BaseModel):
    candidate_component_explanation_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    feature_snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    component_code: M13ComponentCode
    component_name_cn: str = Field(min_length=1)
    score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    support_level: M13SupportLevel = M13SupportLevel.WEAK
    business_explanation_cn: str = Field(min_length=1)
    positive_summary_cn: str | None = None
    gap_summary_cn: str | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence_reasons_json: list[dict[str, Any] | str] = Field(default_factory=list)
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    rule_version: str = CORE3_M13_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M13CandidateScoreReviewIssueRecord(M13BaseModel):
    candidate_score_review_issue_id: str = Field(min_length=1)
    candidate_component_score_id: str | None = None
    candidate_role_score_id: str | None = None
    candidate_pool_id: str | None = None
    feature_snapshot_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = ""
    issue_scope: M13IssueScope = M13IssueScope.PAIR
    component_code: str = ""
    role_code: str = ""
    issue_type: str = Field(min_length=1)
    issue_level: M13IssueLevel = M13IssueLevel.WARNING
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str | None = None
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    resolved_by: str | None = None
    resolution_note: str | None = None
    rule_version: str = CORE3_M13_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M13BuildArtifacts:
    component_score: M13CandidateComponentScoreRecord
    role_scores: tuple[M13CandidateRoleScoreRecord, ...] = field(default_factory=tuple)
    explanations: tuple[M13CandidateComponentExplanationRecord, ...] = field(default_factory=tuple)
    review_issues: tuple[M13CandidateScoreReviewIssueRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class M13ServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    warnings: list[str]
    component_scores: list[M13CandidateComponentScoreRecord]
    role_scores: list[M13CandidateRoleScoreRecord]
    explanations: list[M13CandidateComponentExplanationRecord]
    review_issues: list[M13CandidateScoreReviewIssueRecord]
    summary: dict[str, Any]
