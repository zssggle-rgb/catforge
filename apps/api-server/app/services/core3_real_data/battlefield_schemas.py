"""M11 battlefield contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M11_RULE_VERSION,
    CORE3_M11_SEED_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M11BattlefieldCandidateStatus,
    M11BattlefieldEvidenceDomain,
    M11BattlefieldRelationLevel,
    M11BattlefieldSampleSufficiency,
    M11BattlefieldSupportLevel,
    M11CompetitorSelectionRole,
)


class M11BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M11SkuBattlefieldCandidateRecord(M11BaseModel):
    sku_battlefield_candidate_id: str = Field(min_length=1)
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
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_definition_cn: str = Field(min_length=1)
    candidate_source_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    source_task_codes_json: list[str] = Field(default_factory=list)
    source_target_group_codes_json: list[str] = Field(default_factory=list)
    source_claim_codes_json: list[str] = Field(default_factory=list)
    source_param_codes_json: list[str] = Field(default_factory=list)
    source_topic_codes_json: list[str] = Field(default_factory=list)
    candidate_initial_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    candidate_reason_cn: str = Field(min_length=1)
    candidate_status: M11BattlefieldCandidateStatus = M11BattlefieldCandidateStatus.ACTIVE
    reject_reason_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_score_fingerprint: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M11SkuBattlefieldScoreRecord(M11BaseModel):
    sku_battlefield_score_id: str = Field(min_length=1)
    sku_battlefield_candidate_id: str | None = None
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
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_definition_cn: str = Field(min_length=1)
    semantic_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    market_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    core_task_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    target_group_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    core_claim_combo_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    core_param_capability_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    pain_point_risk_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_position_fit: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sales_validation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sales_amount_validation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    channel_fit_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    trend_signal_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comparable_pool_strength: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    raw_battlefield_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    risk_penalty: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    battlefield_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    relation_level: M11BattlefieldRelationLevel = M11BattlefieldRelationLevel.INSUFFICIENT
    relation_reason_json: dict[str, Any] = Field(default_factory=dict)
    competitor_selection_role: M11CompetitorSelectionRole = M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH
    competitor_selection_role_cn: str = "不进入核心召回"
    sample_sufficiency: M11BattlefieldSampleSufficiency = M11BattlefieldSampleSufficiency.UNKNOWN
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    evidence_domain_count: int = Field(default=0, ge=0)
    effective_domain_json: dict[str, Any] = Field(default_factory=dict)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    cap_rule_applied_json: list[dict[str, Any]] = Field(default_factory=list)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    next_module_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_score_fingerprint: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M11SkuBattlefieldEvidenceBreakdownRecord(M11BaseModel):
    sku_battlefield_evidence_breakdown_id: str = Field(min_length=1)
    sku_battlefield_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    evidence_domain: M11BattlefieldEvidenceDomain
    support_level: M11BattlefieldSupportLevel = M11BattlefieldSupportLevel.MISSING
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
    target_group_score_fingerprint: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M11SkuBattlefieldPortfolioRecord(M11BaseModel):
    sku_battlefield_portfolio_id: str = Field(min_length=1)
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
    main_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    secondary_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    opportunity_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    weak_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    insufficient_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    primary_competitor_search_context_cn: str = Field(min_length=1)
    primary_search_battlefield_codes_json: list[str] = Field(default_factory=list)
    secondary_search_battlefield_codes_json: list[str] = Field(default_factory=list)
    opportunity_monitoring_codes_json: list[str] = Field(default_factory=list)
    risk_or_service_context_json: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    portfolio_risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    battlefield_score_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    task_score_fingerprint: str = Field(min_length=1)
    target_group_score_fingerprint: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M11SkuBattlefieldReviewIssueRecord(M11BaseModel):
    sku_battlefield_review_issue_id: str = Field(min_length=1)
    sku_battlefield_score_id: str | None = None
    sku_battlefield_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = ""
    battlefield_name_cn: str | None = None
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
    target_group_score_fingerprint: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M11BattlefieldDomainEvidence:
    domain: M11BattlefieldEvidenceDomain
    support_level: M11BattlefieldSupportLevel
    score: Decimal
    weight: Decimal
    reason_cn: str
    evidence_ids: list[str] = field(default_factory=list)
    source_feature_refs: list[dict[str, Any]] = field(default_factory=list)
    risk_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class M11BattlefieldBuildResult:
    candidate: M11SkuBattlefieldCandidateRecord
    score: M11SkuBattlefieldScoreRecord
    breakdowns: list[M11SkuBattlefieldEvidenceBreakdownRecord]
    review_issues: list[M11SkuBattlefieldReviewIssueRecord]


@dataclass(frozen=True)
class M11ServiceResult:
    candidates: list[M11SkuBattlefieldCandidateRecord]
    scores: list[M11SkuBattlefieldScoreRecord]
    breakdowns: list[M11SkuBattlefieldEvidenceBreakdownRecord]
    portfolios: list[M11SkuBattlefieldPortfolioRecord]
    review_issues: list[M11SkuBattlefieldReviewIssueRecord]
    summary: dict[str, Any]
    warnings: list[str]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
