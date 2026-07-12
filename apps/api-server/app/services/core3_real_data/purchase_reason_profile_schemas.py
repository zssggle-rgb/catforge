"""M12D SKU purchase reason profile contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M12D_RULE_VERSION,
    CORE3_M12D_SCHEMA_VERSION,
    CORE3_M12D_INPUT_QUALITY_POLICY_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputAvailability,
    M12DInputStatus,
    M12DInputUsability,
    M12DIssueScope,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DPurchasePressureLevel,
    M12DPurchasePressureType,
    M12DReasonEstablishmentStatus,
    M12DReleaseQualityStatus,
    M12DReleaseStatus,
    M12DUserValidationStatus,
)


class M12DBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", from_attributes=True, use_enum_values=True
    )


class M12DSourceRef(M12DBaseModel):
    module_code: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    result_hash: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class M12DPurchasePressureTag(M12DBaseModel):
    pressure_type: M12DPurchasePressureType
    pressure_level: M12DPurchasePressureLevel
    affected_aspect_code: str | None = None
    affected_anchor_code: str = Field(min_length=1)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    mixed_count: int = Field(default=0, ge=0)
    dominance: Literal["positive", "negative", "mixed", "unknown"] = "unknown"
    limits_establishment: bool = False
    limits_comparison: bool = False
    summary_cn: str = ""
    source_refs: list[M12DSourceRef] = Field(default_factory=list)


class M12DComparisonLimitation(M12DBaseModel):
    limitation_code: str = Field(min_length=1)
    scope: Literal["anchor", "market", "amount_wtp", "replacement", "ranking"]
    limits_comparison: bool = True
    summary_cn: str = ""
    source_refs: list[M12DSourceRef] = Field(default_factory=list)


class M12DInputQualityIssue(M12DBaseModel):
    code: str = Field(min_length=1)
    severity: M12DIssueSeverity
    scope: M12DIssueScope
    message_cn: str = ""
    affected_anchor_codes: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    details_json: dict[str, Any] = Field(default_factory=dict)


class M12DInputQuality(M12DBaseModel):
    module_code: str = Field(min_length=1)
    availability: M12DInputAvailability
    usability: M12DInputUsability
    issues: list[M12DInputQualityIssue] = Field(default_factory=list)


class M12DFocusSkuValidationResult(M12DBaseModel):
    sku_code: str = Field(min_length=1)
    passed: bool
    reason_cn: str = ""


class M12DReleaseThresholdResult(M12DBaseModel):
    metric_code: str = Field(min_length=1)
    numerator: int = Field(default=0, ge=0)
    denominator: int = Field(default=0, ge=0)
    observed_rate: Decimal | None = Field(default=None, ge=0, le=1)
    operator: Literal[">=", "<=", "="]
    threshold: Decimal = Field(ge=0, le=1)
    applicable: bool = True
    passed: bool = False
    reason_cn: str = ""


class M12DReleaseSystemIssue(M12DBaseModel):
    code: str = Field(min_length=1)
    severity: M12DIssueSeverity = M12DIssueSeverity.BLOCKING
    scope: M12DIssueScope = M12DIssueScope.RELEASE
    source_issue_code: str | None = None
    affected_sku_count: int = Field(default=0, ge=0)
    total_sku_count: int = Field(default=0, ge=0)
    coverage_rate: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    message_cn: str = ""


class M12DReleaseQualityEvaluation(M12DBaseModel):
    category_code: Core3CategoryCode
    product_category: str = Field(min_length=1)
    expected_sku_count: int = Field(ge=0)
    profile_count: int = Field(ge=0)
    release_quality_status: M12DReleaseQualityStatus
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    threshold_results: list[M12DReleaseThresholdResult] = Field(default_factory=list)
    blocking_issue_coverage_json: list[dict[str, Any]] = Field(default_factory=list)
    system_issues: list[M12DReleaseSystemIssue] = Field(default_factory=list)
    failure_reason_codes: list[str] = Field(default_factory=list)


class M12DPurchaseReasonProfileVersionRecord(M12DBaseModel):
    purchase_reason_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    product_category: str = Field(default="TV", min_length=1)
    m12d_profile_version: str = Field(min_length=1)
    schema_version: str = CORE3_M12D_SCHEMA_VERSION
    rule_version: str = CORE3_M12D_RULE_VERSION
    release_status: M12DReleaseStatus = M12DReleaseStatus.DRAFT
    release_quality_status: M12DReleaseQualityStatus = (
        M12DReleaseQualityStatus.UNASSESSED
    )
    is_current: bool = False
    published_at: datetime | None = None
    published_by: str | None = None
    deprecated_at: datetime | None = None
    deprecated_by: str | None = None
    release_note_cn: str | None = None
    generated_by: str = "system"
    source_batch_ids_json: list[str] = Field(default_factory=list)
    input_scope_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    validation_summary_json: dict[str, Any] = Field(default_factory=dict)
    sku_count: int = Field(default=0, ge=0)
    ready_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    missing_input_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    low_confidence_count: int = Field(default=0, ge=0)
    core_payment_missing_count: int = Field(default=0, ge=0)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)


class M12DSkuPurchaseReasonProfileRecord(M12DBaseModel):
    purchase_reason_profile_id: str = Field(min_length=1)
    purchase_reason_version_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    product_category: str = Field(default="TV", min_length=1)
    m12d_profile_version: str = Field(min_length=1)
    schema_version: str = CORE3_M12D_SCHEMA_VERSION
    rule_version: str = CORE3_M12D_RULE_VERSION
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    status: M12DProfileStatus = M12DProfileStatus.MISSING_INPUT
    profile_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    core_reasons_json: list[str] = Field(default_factory=list)
    core_payment_anchors_json: list[str] = Field(default_factory=list)
    supporting_anchors_json: list[str] = Field(default_factory=list)
    weak_expression_anchors_json: list[str] = Field(default_factory=list)
    risk_drag_anchors_json: list[str] = Field(default_factory=list)
    established_anchors_json: list[str] = Field(default_factory=list)
    proposition_anchors_json: list[str] = Field(default_factory=list)
    pressure_summary_json: dict[str, Any] = Field(default_factory=dict)
    comparison_limitations_json: list[M12DComparisonLimitation] = Field(
        default_factory=list
    )
    evidence_summary_json: dict[str, Any] = Field(default_factory=dict)
    input_status_json: dict[str, Any] = Field(default_factory=dict)
    input_quality_json: dict[str, M12DInputQuality] = Field(default_factory=dict)
    param_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    claim_fact_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    comment_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    market_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    semantic_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    semantic_market_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    claim_value_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    source_batch_ids_json: list[str] = Field(default_factory=list)
    source_merge_strategy: str = "unknown"
    missing_input_reasons_json: list[dict[str, Any] | str] = Field(default_factory=list)
    role_downgrade_reasons_json: list[dict[str, Any] | str] = Field(
        default_factory=list
    )
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    source_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    release_status: M12DReleaseStatus = M12DReleaseStatus.DRAFT
    generated_at: datetime | None = None
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M12DPurchaseReasonAnchorRecord(M12DBaseModel):
    purchase_reason_anchor_id: str = Field(min_length=1)
    purchase_reason_profile_id: str | None = None
    purchase_reason_version_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    product_category: str = Field(default="TV", min_length=1)
    m12d_profile_version: str = Field(min_length=1)
    schema_version: str = CORE3_M12D_SCHEMA_VERSION
    rule_version: str = CORE3_M12D_RULE_VERSION
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    anchor_code: str = Field(min_length=1)
    anchor_cn: str = Field(min_length=1)
    anchor_family_code: str | None = None
    anchor_rank: int = Field(default=0, ge=0)
    role: M12DAnchorRole
    evidence_strength: M12DEvidenceStrength = M12DEvidenceStrength.INSUFFICIENT
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    establishment_status: M12DReasonEstablishmentStatus = (
        M12DReasonEstablishmentStatus.UNASSESSED
    )
    establishment_score: Decimal | None = Field(default=None, ge=0)
    establishment_domains_json: list[M12DEvidenceDomain] = Field(default_factory=list)
    user_validation_status: M12DUserValidationStatus = (
        M12DUserValidationStatus.UNASSESSED
    )
    core_eligible: bool | None = None
    core_ineligible_reasons_json: list[str] = Field(default_factory=list)
    proposition_evidence_json: list[M12DSourceRef] = Field(default_factory=list)
    user_support_evidence_json: list[M12DSourceRef] = Field(default_factory=list)
    pressure_level: M12DPurchasePressureLevel = M12DPurchasePressureLevel.UNASSESSED
    pressure_tags_json: list[M12DPurchasePressureTag] = Field(default_factory=list)
    pressure_summary_cn: str = ""
    comparison_limitations_json: list[M12DComparisonLimitation] = Field(
        default_factory=list
    )
    evidence_domains_json: list[M12DEvidenceDomain] = Field(default_factory=list)
    domain_scores_json: dict[str, Decimal | int | float | str | None] = Field(
        default_factory=dict
    )
    support_summary_cn: str = Field(min_length=1)
    weakness_summary_cn: str = ""
    source_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    role_reason_json: dict[str, Any] = Field(default_factory=dict)
    downgrade_reason_code: str | None = None
    release_status: M12DReleaseStatus = M12DReleaseStatus.DRAFT
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M12DInputSnapshot(M12DBaseModel):
    module_code: str = Field(min_length=1)
    status: M12DInputStatus = M12DInputStatus.UNKNOWN
    record_count: int = Field(default=0, ge=0)
    summary: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[M12DSourceRef] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    quality: M12DInputQuality | None = None


class M12DSkuPurchaseReasonContext(M12DBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    product_category: str = Field(default="TV", min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    param_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    claim_fact_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    comment_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    market_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    semantic_profile_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    semantic_market_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    claim_value_status: M12DInputStatus = M12DInputStatus.UNKNOWN
    param_profile: M12DInputSnapshot
    claim_fact_profile: M12DInputSnapshot
    comment_profile: M12DInputSnapshot
    market_profile: M12DInputSnapshot
    semantic_profile: M12DInputSnapshot
    semantic_market_profile: M12DInputSnapshot
    claim_value_profile: M12DInputSnapshot
    input_status_json: dict[str, Any] = Field(default_factory=dict)
    input_quality_json: dict[str, M12DInputQuality] = Field(default_factory=dict)
    input_quality_policy_version: str = CORE3_M12D_INPUT_QUALITY_POLICY_VERSION
    missing_input_reasons_json: list[str] = Field(default_factory=list)
    source_refs_json: list[M12DSourceRef] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)


class M12DAnchorEvidencePattern(M12DBaseModel):
    module_code: str = Field(min_length=1)
    evidence_domain: M12DEvidenceDomain
    summary_keys: list[str] = Field(default_factory=list)
    exact_codes: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    support_label_cn: str = Field(min_length=1)
    weak_expression_only: bool = False


class M12DStandardValueThemeDefinition(M12DBaseModel):
    value_theme_code: str = Field(min_length=1)
    value_theme_cn: str = Field(min_length=1)
    value_theme_family_code: str = Field(min_length=1)
    value_theme_family_cn: str = Field(min_length=1)
    definition_cn: str = Field(min_length=1)
    candidate_rank: int = Field(ge=0)
    evidence_patterns: list[M12DAnchorEvidencePattern] = Field(default_factory=list)


class M12DStandardPurchaseReasonDefinition(M12DBaseModel):
    purchase_reason_code: str = Field(min_length=1)
    purchase_reason_cn: str = Field(min_length=1)
    purchase_reason_family_code: str = Field(min_length=1)
    purchase_reason_family_cn: str = Field(min_length=1)
    related_value_theme_codes: list[str] = Field(default_factory=list)
    definition_cn: str = Field(min_length=1)
    required_logic_cn: str = Field(min_length=1)
    weak_boundary_cn: str = Field(min_length=1)
    decision_question_cn: str = Field(min_length=1)
    candidate_rank: int = Field(ge=0)
    evidence_patterns: list[M12DAnchorEvidencePattern] = Field(default_factory=list)
    candidate_gate_domain_groups: list[list[M12DEvidenceDomain]] = Field(
        default_factory=list
    )


class M12DAnchorTaxonomy(M12DBaseModel):
    taxonomy_version: str = Field(min_length=1)
    product_category: str = Field(min_length=1)
    product_category_label_cn: str = Field(min_length=1)
    source_note_cn: str = Field(min_length=1)
    value_themes: list[M12DStandardValueThemeDefinition] = Field(default_factory=list)
    purchase_reasons: list[M12DStandardPurchaseReasonDefinition] = Field(
        default_factory=list
    )

    @property
    def anchors(self) -> list[M12DStandardPurchaseReasonDefinition]:
        return self.purchase_reasons

    def value_themes_by_code(self) -> dict[str, M12DStandardValueThemeDefinition]:
        return {theme.value_theme_code: theme for theme in self.value_themes}

    def purchase_reasons_by_code(
        self,
    ) -> dict[str, M12DStandardPurchaseReasonDefinition]:
        return {reason.purchase_reason_code: reason for reason in self.purchase_reasons}

    def anchors_by_code(self) -> dict[str, M12DStandardPurchaseReasonDefinition]:
        return self.purchase_reasons_by_code()


class M12DAnchorEvidenceMatch(M12DBaseModel):
    module_code: str = Field(min_length=1)
    evidence_domain: M12DEvidenceDomain
    match_source: str = Field(min_length=1)
    match_key: str = Field(min_length=1)
    match_value: str = Field(min_length=1)
    support_label_cn: str = Field(min_length=1)
    weak_expression_only: bool = False
    source_refs_json: list[M12DSourceRef] = Field(default_factory=list)


class M12DAnchorCandidate(M12DBaseModel):
    taxonomy_version: str = Field(min_length=1)
    product_category: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    candidate_type: Literal["value_theme", "purchase_reason"] = "purchase_reason"
    anchor_code: str = Field(min_length=1)
    anchor_cn: str = Field(min_length=1)
    anchor_family_code: str = Field(min_length=1)
    anchor_family_cn: str = Field(min_length=1)
    related_value_theme_codes: list[str] = Field(default_factory=list)
    required_logic_cn: str | None = None
    weak_boundary_cn: str | None = None
    decision_question_cn: str | None = None
    candidate_rank: int = Field(ge=0)
    evidence_matches: list[M12DAnchorEvidenceMatch] = Field(default_factory=list)
    evidence_domains_json: list[M12DEvidenceDomain] = Field(default_factory=list)
    role_cap: M12DAnchorRole | None = None
    role_cap_reasons: list[str] = Field(default_factory=list)
    support_summary_cn: str = Field(min_length=1)
    source_refs_json: list[M12DSourceRef] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)


class M12DAnchorCandidateSet(M12DBaseModel):
    taxonomy_version: str = Field(min_length=1)
    product_category: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    value_theme_candidates: list[M12DAnchorCandidate] = Field(default_factory=list)
    purchase_reason_candidates: list[M12DAnchorCandidate] = Field(default_factory=list)


class M12DScoredPurchaseReasonAnchor(M12DBaseModel):
    taxonomy_version: str = Field(min_length=1)
    product_category: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    anchor_code: str = Field(min_length=1)
    anchor_cn: str = Field(min_length=1)
    anchor_family_code: str | None = None
    anchor_family_cn: str | None = None
    anchor_rank: int = Field(default=0, ge=0)
    related_value_theme_codes: list[str] = Field(default_factory=list)
    role: M12DAnchorRole
    evidence_strength: M12DEvidenceStrength = M12DEvidenceStrength.INSUFFICIENT
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    establishment_status: M12DReasonEstablishmentStatus = (
        M12DReasonEstablishmentStatus.UNASSESSED
    )
    establishment_score: Decimal | None = Field(default=None, ge=0)
    establishment_domains_json: list[M12DEvidenceDomain] = Field(default_factory=list)
    user_validation_status: M12DUserValidationStatus = (
        M12DUserValidationStatus.UNASSESSED
    )
    core_eligible: bool | None = None
    core_ineligible_reasons_json: list[str] = Field(default_factory=list)
    proposition_evidence_json: list[M12DSourceRef] = Field(default_factory=list)
    user_support_evidence_json: list[M12DSourceRef] = Field(default_factory=list)
    pressure_level: M12DPurchasePressureLevel = M12DPurchasePressureLevel.UNASSESSED
    pressure_tags_json: list[M12DPurchasePressureTag] = Field(default_factory=list)
    pressure_summary_cn: str = ""
    comparison_limitations_json: list[M12DComparisonLimitation] = Field(
        default_factory=list
    )
    raw_evidence_score: Decimal = Field(default=Decimal("0.0000"), ge=0)
    conflict_penalty: Decimal = Field(default=Decimal("0.0000"), ge=0)
    adjusted_evidence_score: Decimal = Field(default=Decimal("0.0000"), ge=0)
    evidence_domains_json: list[M12DEvidenceDomain] = Field(default_factory=list)
    domain_scores_json: dict[str, Decimal] = Field(default_factory=dict)
    support_summary_cn: str = Field(min_length=1)
    weakness_summary_cn: str = ""
    source_refs_json: list[M12DSourceRef] = Field(default_factory=list)
    risk_flags_json: list[str] = Field(default_factory=list)
    role_reason_json: dict[str, Any] = Field(default_factory=dict)
    downgrade_reason_code: str | None = None
    input_fingerprint: str = Field(min_length=1)


class M12DProfileScoreResult(M12DBaseModel):
    taxonomy_version: str = Field(min_length=1)
    product_category: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    status: M12DProfileStatus
    profile_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    scored_anchors: list[M12DScoredPurchaseReasonAnchor] = Field(default_factory=list)
    core_payment_anchors_json: list[str] = Field(default_factory=list)
    supporting_anchors_json: list[str] = Field(default_factory=list)
    weak_expression_anchors_json: list[str] = Field(default_factory=list)
    risk_drag_anchors_json: list[str] = Field(default_factory=list)
    established_anchors_json: list[str] = Field(default_factory=list)
    proposition_anchors_json: list[str] = Field(default_factory=list)
    pressure_summary_json: dict[str, Any] = Field(default_factory=dict)
    comparison_limitations_json: list[M12DComparisonLimitation] = Field(
        default_factory=list
    )
    risk_flags_json: list[str] = Field(default_factory=list)
    confidence_basis_json: dict[str, Any] = Field(default_factory=dict)
    role_downgrade_reasons_json: list[dict[str, Any] | str] = Field(
        default_factory=list
    )
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    input_fingerprint: str = Field(min_length=1)


@dataclass(frozen=True)
class M12DPublishedProfile:
    version: Any
    profile: Any
    anchors: tuple[Any, ...] = field(default_factory=tuple)


class M12DDownstreamAnchorContract(M12DBaseModel):
    anchor_code: str = Field(min_length=1)
    anchor_cn: str = Field(min_length=1)
    anchor_family_code: str | None = None
    anchor_rank: int = Field(default=0, ge=0)
    role: M12DAnchorRole
    evidence_strength: M12DEvidenceStrength
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    establishment_status: M12DReasonEstablishmentStatus = (
        M12DReasonEstablishmentStatus.UNASSESSED
    )
    establishment_score: Decimal | None = Field(default=None, ge=0)
    establishment_domains: list[M12DEvidenceDomain] = Field(default_factory=list)
    user_validation_status: M12DUserValidationStatus = (
        M12DUserValidationStatus.UNASSESSED
    )
    core_eligible: bool | None = None
    core_ineligible_reasons: list[str] = Field(default_factory=list)
    proposition_evidence: list[M12DSourceRef] = Field(default_factory=list)
    user_support_evidence: list[M12DSourceRef] = Field(default_factory=list)
    pressure_level: M12DPurchasePressureLevel = M12DPurchasePressureLevel.UNASSESSED
    pressure_tags: list[M12DPurchasePressureTag] = Field(default_factory=list)
    pressure_summary_cn: str = ""
    comparison_limitations: list[M12DComparisonLimitation] = Field(default_factory=list)
    evidence_domains: list[M12DEvidenceDomain] = Field(default_factory=list)
    support_summary_cn: str = ""
    weakness_summary_cn: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class M12DDownstreamProfileContract(M12DBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    product_category: str = Field(default="TV", min_length=1)
    m12d_profile_version: str = Field(min_length=1)
    schema_version: str = CORE3_M12D_SCHEMA_VERSION
    rule_version: str = CORE3_M12D_RULE_VERSION
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    status: M12DProfileStatus
    profile_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    core_reasons_cn: list[str] = Field(default_factory=list)
    core_payment_anchors: list[str] = Field(default_factory=list)
    supporting_anchors: list[str] = Field(default_factory=list)
    weak_expression_anchors: list[str] = Field(default_factory=list)
    risk_drag_anchors: list[str] = Field(default_factory=list)
    established_anchors: list[str] = Field(default_factory=list)
    proposition_anchors: list[str] = Field(default_factory=list)
    pressure_summary: dict[str, Any] = Field(default_factory=dict)
    comparison_limitations: list[M12DComparisonLimitation] = Field(default_factory=list)
    anchors: list[M12DDownstreamAnchorContract] = Field(default_factory=list)
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reasons: list[str] = Field(default_factory=list)
    degradation_reasons: list[str] = Field(default_factory=list)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    input_quality: dict[str, M12DInputQuality] = Field(default_factory=dict)
    source_batch_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class M12DConsumptionCapabilities(M12DBaseModel):
    comparison_mode: Literal["strong", "limited", "facts_only", "blocked"] = "blocked"
    fact_dimensions_allowed: bool = False
    proposition_comparison_allowed: bool = False
    established_reason_comparison_allowed: bool = False
    strong_reason_comparison_allowed: bool = False
    pressure_comparison_allowed: bool = False


class M12DDownstreamReadContract(M12DBaseModel):
    found: bool = False
    lookup_key: dict[str, str] = Field(default_factory=dict)
    consumption_state: Literal[
        "published_ready", "published_degraded", "published_unusable", "not_found"
    ] = "not_found"
    downstream_action: Literal[
        "normal_pair_scoring",
        "degraded_pair_scoring",
        "block_target_or_drop_candidate",
    ] = "block_target_or_drop_candidate"
    message_cn: str = ""
    release_quality_status: M12DReleaseQualityStatus = (
        M12DReleaseQualityStatus.UNASSESSED
    )
    version_quality_notes: list[str] = Field(default_factory=list)
    capabilities: M12DConsumptionCapabilities = Field(
        default_factory=M12DConsumptionCapabilities
    )
    profile: M12DDownstreamProfileContract | None = None


@dataclass(frozen=True)
class M12DWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


@dataclass(frozen=True)
class M12DServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    updated_output_count: int
    reused_output_count: int
    warnings: list[str]
    profiles: tuple[M12DSkuPurchaseReasonProfileRecord, ...]
    anchors: tuple[M12DPurchaseReasonAnchorRecord, ...]
    summary: dict[str, Any]
