"""M11.6 SKU business profile contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import CORE3_M11_6_RULE_VERSION, Core3CategoryCode, Core3RunStatus


class M116BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M116SkuBusinessProfileRecord(M116BaseModel):
    sku_business_profile_id: str = Field(min_length=1)
    sku_signal_profile_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    series_name: str | None = None
    screen_size_inch: Decimal | None = None
    size_segment: str = "unknown"
    price_band: str = "unknown"
    main_platform: str | None = None
    sales_volume_total: Decimal | None = None
    sales_amount_total: Decimal | None = None
    price_wavg: Decimal | None = None
    price_latest: Decimal | None = None
    price_percentile_in_pool: Decimal | None = None
    sales_percentile_in_pool: Decimal | None = None
    amount_percentile_in_pool: Decimal | None = None
    price_gap_to_pool_median: Decimal | None = None
    market_sample_status: str = "unknown"
    market_source: str = "M08"
    primary_task_code: str | None = None
    primary_task_name: str | None = None
    primary_task_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    primary_task_evidence_level: str = "unknown"
    primary_task_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    primary_target_group_code: str | None = None
    primary_target_group_name: str | None = None
    primary_target_group_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    primary_target_group_evidence_level: str = "unknown"
    primary_target_group_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    primary_battlefield_code: str | None = None
    primary_battlefield_name: str | None = None
    primary_battlefield_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    primary_battlefield_evidence_level: str = "unknown"
    primary_battlefield_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    secondary_tasks_json: list[dict[str, Any]] = Field(default_factory=list)
    secondary_target_groups_json: list[dict[str, Any]] = Field(default_factory=list)
    secondary_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    core_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    claim_value_summary_json: dict[str, Any] = Field(default_factory=dict)
    claim_value_strength: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    premium_position: str = "unknown"
    premium_type: str = "unknown"
    premium_support_level: str = "unknown"
    premium_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    premium_reason_cn: str = Field(min_length=1)
    premium_risk_json: list[dict[str, Any] | str] = Field(default_factory=list)
    market_role: str = "unknown"
    market_role_reason_cn: str = Field(min_length=1)
    competitive_role_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    candidate_recall_priority_json: dict[str, Any] = Field(default_factory=dict)
    same_brand_competition_policy: str = "allow"
    sales_allocation_summary_json: dict[str, Any] = Field(default_factory=dict)
    evidence_strength: str = "unknown"
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: str = "unknown"
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    business_summary_cn: str = Field(min_length=1)
    rule_version: str = CORE3_M11_6_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M116SkuBusinessProfileDimensionRecord(M116BaseModel):
    profile_dimension_id: str = Field(min_length=1)
    sku_business_profile_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    dimension_type: str = Field(min_length=1)
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    dimension_rank: int = Field(default=0, ge=0)
    dimension_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    normalized_weight: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    evidence_level: str = "unknown"
    relation_level: str = "unknown"
    value_layer: str | None = None
    source_module: str = Field(min_length=1)
    source_record_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    support_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    business_reason_cn: str = Field(min_length=1)
    rule_version: str = CORE3_M11_6_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M116SkuBusinessProfileSalesAllocationRecord(M116BaseModel):
    sales_allocation_id: str = Field(min_length=1)
    sku_business_profile_id: str | None = None
    profile_dimension_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    dimension_type: str = Field(min_length=1)
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    allocation_method: str = "score_normalized_with_market_volume"
    allocation_weight: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    allocated_sales_volume: Decimal | None = None
    allocated_sales_amount: Decimal | None = None
    allocation_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    allocation_basis_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M11_6_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True


class M116SkuBusinessProfileReviewIssueRecord(M116BaseModel):
    sku_business_profile_review_issue_id: str = Field(min_length=1)
    sku_business_profile_id: str | None = None
    profile_dimension_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    dimension_type: str = ""
    dimension_code: str = ""
    issue_type: str = Field(min_length=1)
    issue_level: str = "warning"
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str = Field(min_length=1)
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M11_6_RULE_VERSION
    resolved_status: str = "open"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M116BuildArtifacts:
    profiles: tuple[M116SkuBusinessProfileRecord, ...] = field(default_factory=tuple)
    dimensions: tuple[M116SkuBusinessProfileDimensionRecord, ...] = field(default_factory=tuple)
    allocations: tuple[M116SkuBusinessProfileSalesAllocationRecord, ...] = field(default_factory=tuple)
    review_issues: tuple[M116SkuBusinessProfileReviewIssueRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class M116ServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    updated_output_count: int
    reused_output_count: int
    warnings: list[str]
    profiles: tuple[M116SkuBusinessProfileRecord, ...]
    dimensions: tuple[M116SkuBusinessProfileDimensionRecord, ...]
    allocations: tuple[M116SkuBusinessProfileSalesAllocationRecord, ...]
    review_issues: tuple[M116SkuBusinessProfileReviewIssueRecord, ...]
    summary: dict[str, Any]
