"""M11.5 claim value layer contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M11_5_BATTLEFIELD_SEED_VERSION,
    CORE3_M11_5_CLAIM_SEED_VERSION,
    CORE3_M11_5_RULE_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M115BattlefieldRelevanceRole,
    M115ClaimCandidateStatus,
    M115ClaimValueEvidenceDomain,
    M115ClaimValueLayer,
    M115ClaimValueSupportLevel,
    M115SampleSufficiency,
)


class M115BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M115SkuBattlefieldClaimCandidateRecord(M115BaseModel):
    sku_battlefield_claim_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_signal_profile_id: str | None = None
    sku_downstream_feature_view_id: str | None = None
    sku_battlefield_score_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_relation_level: str = Field(min_length=1)
    claim_code: str = Field(min_length=1)
    claim_name_cn: str = Field(min_length=1)
    claim_group: str | None = None
    candidate_source_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    candidate_initial_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    candidate_reason_cn: str = Field(min_length=1)
    candidate_status: M115ClaimCandidateStatus = M115ClaimCandidateStatus.ACTIVE
    reject_reason_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    battlefield_score_fingerprint: str = Field(min_length=1)
    claim_seed_version: str = CORE3_M11_5_CLAIM_SEED_VERSION
    claim_seed_file_version: str = Field(min_length=1)
    claim_seed_hash: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_5_BATTLEFIELD_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_5_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M115SkuClaimValueLayerRecord(M115BaseModel):
    sku_claim_value_layer_id: str = Field(min_length=1)
    sku_battlefield_claim_candidate_id: str | None = None
    sku_signal_profile_id: str | None = None
    sku_downstream_feature_view_id: str | None = None
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
    battlefield_relation_level: str = Field(min_length=1)
    claim_code: str = Field(min_length=1)
    claim_name_cn: str = Field(min_length=1)
    claim_group: str | None = None
    claim_activation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    activation_basis_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_relevance_role: M115BattlefieldRelevanceRole = M115BattlefieldRelevanceRole.NOT_APPLICABLE
    comparable_pool_id: str | None = None
    pool_type: str | None = None
    pool_sku_count: int = Field(default=0, ge=0)
    with_claim_count: int = Field(default=0, ge=0)
    without_claim_count: int = Field(default=0, ge=0)
    coverage_rate: Decimal | None = None
    coverage_position_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    psi: Decimal | None = None
    ssi: Decimal | None = None
    sai: Decimal | None = None
    cpi: Decimal | None = None
    positive_mention_rate: Decimal | None = None
    negative_mention_rate: Decimal | None = None
    neutral_mention_rate: Decimal | None = None
    price_support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sales_support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_perception_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    risk_penalty: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    claim_value_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    layer: M115ClaimValueLayer = M115ClaimValueLayer.INSUFFICIENT_SAMPLE
    layer_reason_json: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_sufficiency: M115SampleSufficiency = M115SampleSufficiency.UNKNOWN
    sample_sufficiency_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    next_module_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    battlefield_score_fingerprint: str = Field(min_length=1)
    claim_seed_version: str = CORE3_M11_5_CLAIM_SEED_VERSION
    claim_seed_file_version: str = Field(min_length=1)
    claim_seed_hash: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_5_BATTLEFIELD_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_5_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M115SkuClaimValueEvidenceBreakdownRecord(M115BaseModel):
    sku_claim_value_evidence_breakdown_id: str = Field(min_length=1)
    sku_claim_value_layer_id: str | None = None
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
    claim_code: str = Field(min_length=1)
    claim_name_cn: str = Field(min_length=1)
    evidence_domain: M115ClaimValueEvidenceDomain
    support_level: M115ClaimValueSupportLevel = M115ClaimValueSupportLevel.MISSING
    support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    domain_weight: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    weighted_contribution: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    support_summary_cn: str = Field(min_length=1)
    source_signal_codes_json: list[str] = Field(default_factory=list)
    source_values_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    missing_reason_code: str | None = None
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    battlefield_score_fingerprint: str = Field(min_length=1)
    claim_seed_version: str = CORE3_M11_5_CLAIM_SEED_VERSION
    claim_seed_file_version: str = Field(min_length=1)
    claim_seed_hash: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_5_BATTLEFIELD_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_5_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M115SkuBattlefieldClaimValueSummaryRecord(M115BaseModel):
    sku_battlefield_claim_value_summary_id: str = Field(min_length=1)
    sku_signal_profile_id: str | None = None
    sku_downstream_feature_view_id: str | None = None
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
    battlefield_relation_level: str = Field(min_length=1)
    premium_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    performance_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    threshold_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    weak_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    insufficient_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    not_applicable_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    claim_value_profile_cn: str = Field(min_length=1)
    comparison_focus_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    summary_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    summary_risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    claim_value_layer_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = Field(min_length=1)
    battlefield_score_fingerprint: str = Field(min_length=1)
    claim_seed_version: str = CORE3_M11_5_CLAIM_SEED_VERSION
    claim_seed_file_version: str = Field(min_length=1)
    claim_seed_hash: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_5_BATTLEFIELD_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_5_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M115SkuClaimValueReviewIssueRecord(M115BaseModel):
    sku_claim_value_review_issue_id: str = Field(min_length=1)
    related_layer_id: str | None = None
    related_candidate_id: str | None = None
    related_battlefield_score_id: str | None = None
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
    claim_code: str = ""
    claim_name_cn: str | None = None
    issue_type: str = Field(min_length=1)
    issue_level: str = "warning"
    issue_message_cn: str = Field(min_length=1)
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    feature_view_hash: str = ""
    battlefield_score_fingerprint: str = Field(min_length=1)
    claim_seed_version: str = CORE3_M11_5_CLAIM_SEED_VERSION
    claim_seed_file_version: str = Field(min_length=1)
    claim_seed_hash: str = Field(min_length=1)
    battlefield_seed_version: str = CORE3_M11_5_BATTLEFIELD_SEED_VERSION
    battlefield_seed_file_version: str = Field(min_length=1)
    battlefield_seed_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M11_5_RULE_VERSION
    resolved_status: str = "open"
    resolved_by: str | None = None
    resolved_at: Any | None = None
    resolution_note: str | None = None
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M115BuildResult:
    candidates: tuple[M115SkuBattlefieldClaimCandidateRecord, ...] = ()
    layers: tuple[M115SkuClaimValueLayerRecord, ...] = ()
    breakdowns: tuple[M115SkuClaimValueEvidenceBreakdownRecord, ...] = ()
    summaries: tuple[M115SkuBattlefieldClaimValueSummaryRecord, ...] = ()
    review_issues: tuple[M115SkuClaimValueReviewIssueRecord, ...] = ()


@dataclass(frozen=True)
class M115ServiceResult:
    status: Core3RunStatus
    input_count: int
    candidates: tuple[M115SkuBattlefieldClaimCandidateRecord, ...] = ()
    layers: tuple[M115SkuClaimValueLayerRecord, ...] = ()
    breakdowns: tuple[M115SkuClaimValueEvidenceBreakdownRecord, ...] = ()
    summaries: tuple[M115SkuBattlefieldClaimValueSummaryRecord, ...] = ()
    review_issues: tuple[M115SkuClaimValueReviewIssueRecord, ...] = ()
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_output_count: int = 0
    updated_output_count: int = 0
    reused_output_count: int = 0

    @property
    def output_count(self) -> int:
        return (
            len(self.candidates)
            + len(self.layers)
            + len(self.breakdowns)
            + len(self.summaries)
            + len(self.review_issues)
        )
