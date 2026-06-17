"""M08 SKU signal profile contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M08_FEATURE_VERSION,
    CORE3_M08_RULE_VERSION,
    CORE3_M08_VIEW_SCHEMA_VERSION,
    M08CoverageStatus,
    M08ForModule,
    M08ProfileScope,
    M08ProfileStatus,
    M08SignalDomain,
    M08ViewRole,
    Core3CategoryCode,
    Core3ConfidenceLevel,
)


class M08BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def m08_confidence_level(score: Decimal | float | int | None) -> Core3ConfidenceLevel:
    value = float(score or 0)
    if value >= 0.75:
        return Core3ConfidenceLevel.HIGH
    if value >= 0.55:
        return Core3ConfidenceLevel.MEDIUM
    if value > 0:
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


class M08SkuSignalProfileRecord(M08BaseModel):
    sku_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    profile_scope: M08ProfileScope = M08ProfileScope.SKU_DEFAULT
    analysis_window: str = "full_observed_window"
    source_coverage_json: dict[str, Any] = Field(default_factory=dict)
    source_profile_refs_json: dict[str, Any] = Field(default_factory=dict)
    sku_master_json: dict[str, Any] = Field(default_factory=dict)
    core_params_json: dict[str, Any] = Field(default_factory=dict)
    param_profile_json: dict[str, Any] = Field(default_factory=dict)
    claim_activation_summary_json: dict[str, Any] = Field(default_factory=dict)
    claim_evidence_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    comment_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    comment_quality_json: dict[str, Any] = Field(default_factory=dict)
    market_summary_json: dict[str, Any] = Field(default_factory=dict)
    market_recent_windows_json: dict[str, Any] = Field(default_factory=dict)
    market_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    comparable_pool_summary_json: dict[str, Any] = Field(default_factory=dict)
    business_signal_index_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any]] = Field(default_factory=list)
    risk_signals_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_completeness_json: dict[str, Any] = Field(default_factory=dict)
    data_completeness_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    domain_confidence_json: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    profile_status: M08ProfileStatus = M08ProfileStatus.LIMITED
    downstream_ready_json: dict[str, Any] = Field(default_factory=dict)
    evidence_summary_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    profile_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M08_RULE_VERSION
    feature_version: str = CORE3_M08_FEATURE_VERSION
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M08SkuSignalEvidenceMatrixRecord(M08BaseModel):
    sku_signal_evidence_matrix_id: str = Field(min_length=1)
    sku_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    domain: M08SignalDomain
    sub_domain: str = Field(min_length=1)
    feature_code: str | None = None
    evidence_role: str = "representative"
    coverage_status: M08CoverageStatus = M08CoverageStatus.UNKNOWN
    evidence_count: int = Field(default=0, ge=0)
    high_confidence_count: int = Field(default=0, ge=0)
    medium_confidence_count: int = Field(default=0, ge=0)
    low_confidence_count: int = Field(default=0, ge=0)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    evidence_query_json: dict[str, Any] = Field(default_factory=dict)
    source_record_refs_json: dict[str, Any] = Field(default_factory=dict)
    missing_flag: bool = False
    missing_reason_code: str | None = None
    risk_flags_json: list[str] = Field(default_factory=list)
    domain_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M08_RULE_VERSION
    feature_version: str = CORE3_M08_FEATURE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M08SkuDownstreamFeatureViewRecord(M08BaseModel):
    sku_downstream_feature_view_id: str = Field(min_length=1)
    sku_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    for_module: M08ForModule
    view_role: M08ViewRole = M08ViewRole.PRIMARY_INPUT
    view_schema_version: str = CORE3_M08_VIEW_SCHEMA_VERSION
    required_feature_codes_json: list[str] = Field(default_factory=list)
    optional_feature_codes_json: list[str] = Field(default_factory=list)
    feature_payload_json: dict[str, Any] = Field(default_factory=dict)
    feature_quality_flags_json: list[str] = Field(default_factory=list)
    required_missing_fields_json: list[str] = Field(default_factory=list)
    optional_missing_fields_json: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[str] = Field(default_factory=list)
    profile_hash: str = Field(min_length=1)
    view_hash: str = Field(min_length=1)
    dependency_hash_json: dict[str, Any] = Field(default_factory=dict)
    ready_for_module: bool = False
    block_reason_json: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M08_RULE_VERSION
    feature_version: str = CORE3_M08_FEATURE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M08QualityIssue(M08BaseModel):
    issue_code: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    severity: str = "medium"
    message_cn: str = Field(min_length=1)
    suggestion_cn: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = True
