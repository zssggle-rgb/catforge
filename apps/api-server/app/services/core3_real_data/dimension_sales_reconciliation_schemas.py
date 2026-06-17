"""M11.7 dimension sales reconciliation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import CORE3_M11_7_RULE_VERSION, Core3CategoryCode, Core3RunStatus


class M117BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M117BusinessDimensionSalesSummaryRecord(M117BaseModel):
    dimension_sales_summary_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    source_m11_6_module_run_id: str | None = None
    dimension_type: str = Field(min_length=1)
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    standard_dimension_rank: int = Field(default=0, ge=0)
    sku_count: int = Field(default=0, ge=0)
    primary_sku_count: int = Field(default=0, ge=0)
    estimated_sales_volume: Decimal = Decimal("0.0000")
    estimated_sales_amount: Decimal = Decimal("0.0000")
    total_market_sales_volume: Decimal = Decimal("0.0000")
    total_market_sales_amount: Decimal = Decimal("0.0000")
    sales_volume_share: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    sales_amount_share: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    avg_allocation_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    top_sku_contribution_json: list[dict[str, Any]] = Field(default_factory=list)
    reconciliation_status: str = "matched"
    business_summary_cn: str = Field(min_length=1)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M117BusinessDimensionSkuContributionRecord(M117BaseModel):
    dimension_sku_contribution_id: str = Field(min_length=1)
    dimension_sales_summary_id: str | None = None
    sku_business_profile_id: str | None = None
    sales_allocation_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    dimension_type: str = Field(min_length=1)
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    allocation_weight: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    allocated_sales_volume: Decimal = Decimal("0.0000")
    allocated_sales_amount: Decimal = Decimal("0.0000")
    sku_share_in_dimension_volume: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    sku_share_in_dimension_amount: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    is_primary_dimension: bool = False
    allocation_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_level: str = "unknown"
    contribution_reason_cn: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"


class M117BusinessSalesReconciliationCheckRecord(M117BaseModel):
    reconciliation_check_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    source_m11_6_module_run_id: str | None = None
    check_type: str = Field(min_length=1)
    sku_code: str = ""
    dimension_type: str = ""
    dimension_code: str = ""
    expected_value: Decimal = Decimal("0.000000")
    actual_value: Decimal = Decimal("0.000000")
    gap_value: Decimal = Decimal("0.000000")
    gap_ratio: Decimal = Decimal("0.00000000")
    tolerance_value: Decimal = Decimal("0.000000")
    status: str = "passed"
    failure_reason_code: str = ""
    failure_reason_cn: str = ""
    check_payload_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M117BusinessSalesReconciliationIssueRecord(M117BaseModel):
    reconciliation_issue_id: str = Field(min_length=1)
    reconciliation_check_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    issue_scope: str = "global"
    sku_code: str = ""
    dimension_type: str = ""
    dimension_code: str = ""
    issue_code: str = Field(min_length=1)
    severity: str = "warning"
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str = Field(min_length=1)
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    resolved_status: str = "open"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M117BuildArtifacts:
    summaries: tuple[M117BusinessDimensionSalesSummaryRecord, ...] = field(default_factory=tuple)
    contributions: tuple[M117BusinessDimensionSkuContributionRecord, ...] = field(default_factory=tuple)
    checks: tuple[M117BusinessSalesReconciliationCheckRecord, ...] = field(default_factory=tuple)
    issues: tuple[M117BusinessSalesReconciliationIssueRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class M117ServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    updated_output_count: int
    reused_output_count: int
    warnings: list[str]
    summaries: tuple[M117BusinessDimensionSalesSummaryRecord, ...]
    contributions: tuple[M117BusinessDimensionSkuContributionRecord, ...]
    checks: tuple[M117BusinessSalesReconciliationCheckRecord, ...]
    issues: tuple[M117BusinessSalesReconciliationIssueRecord, ...]
    summary: dict[str, Any]
