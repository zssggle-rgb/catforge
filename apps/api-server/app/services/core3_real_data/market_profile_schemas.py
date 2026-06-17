"""M07 market profile and comparable pool contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.core3_real_data.constants import (
    CORE3_M07_MODULE_VERSION,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    M07AnalysisWindow,
    M07MarketSignalCode,
    M07Polarity,
    M07PoolType,
    M07PriceBand,
    M07SampleStatus,
    M07SignalLevel,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3ModuleCode,
    Core3RunStatus,
    Core3SourceBatchType,
)


class M07BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def confidence_level(score: Decimal | float | None) -> Core3ConfidenceLevel:
    value = float(score or 0)
    if value >= 0.75:
        return Core3ConfidenceLevel.HIGH
    if value >= 0.55:
        return Core3ConfidenceLevel.MEDIUM
    if value > 0:
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def signal_level(score: Decimal | float | None, *, blocked: bool = False) -> M07SignalLevel:
    if blocked:
        return M07SignalLevel.BLOCKED
    value = float(score or 0)
    if value >= 0.75:
        return M07SignalLevel.STRONG
    if value >= 0.55:
        return M07SignalLevel.MEDIUM
    if value >= 0.35:
        return M07SignalLevel.WEAK
    return M07SignalLevel.BLOCKED


class M07RunRequest(M07BaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M07_MODULE_VERSION
    rule_version: str = CORE3_M07_RULE_VERSION
    price_band_rule_version: str = CORE3_M07_PRICE_BAND_RULE_VERSION
    pool_rule_version: str = CORE3_M07_POOL_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    analysis_windows: list[M07AnalysisWindow] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_sku_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class M07RunResult(M07BaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M07
    status: Core3RunStatus
    processed_sku_count: int = Field(default=0, ge=0)
    market_profile_count: int = Field(default=0, ge=0)
    market_signal_count: int = Field(default=0, ge=0)
    comparable_pool_count: int = Field(default=0, ge=0)
    pool_member_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class M07AnalysisWindowSpec(M07BaseModel):
    analysis_window: M07AnalysisWindow
    period_start_week_index: int | None = None
    period_end_week_index: int | None = None
    period_start_raw: str | None = None
    period_end_raw: str | None = None


class M07MarketEvidenceRef(M07BaseModel):
    evidence_id: str = Field(min_length=1)
    clean_record_key: str | None = None
    clean_hash: str | None = None
    source_row_id: str | None = None
    evidence_field: str | None = None
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)


class M07MarketInputRow(M07BaseModel):
    clean_market_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    category_name: str | None = None
    period_raw: str | None = None
    period_week_index: int | None = None
    channel_type: str | None = None
    platform_type: str | None = None
    sales_volume: Decimal | None = None
    sales_amount: Decimal | None = None
    avg_price: Decimal | None = None
    price_check_status: str | None = None
    clean_hash: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class M07SkuSizeInput(M07BaseModel):
    sku_code: str = Field(min_length=1)
    screen_size_inch: Decimal | None = None
    size_segment: str = "unknown"
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    profile_hash: str | None = None


class M07SkuMarketMetrics(M07BaseModel):
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    category_name: str | None = None
    analysis_window: M07AnalysisWindow
    period_start_raw: str | None = None
    period_end_raw: str | None = None
    period_start_week_index: int | None = None
    period_end_week_index: int | None = None
    global_latest_week_index: int | None = None
    sku_latest_week_index: int | None = None
    latest_week_gap: int | None = None
    active_week_count: int = Field(default=0, ge=0)
    market_row_count: int = Field(default=0, ge=0)
    platform_count: int = Field(default=0, ge=0)
    screen_size_inch: Decimal | None = None
    size_segment: str = "unknown"
    screen_size_class: str = "unknown"
    market_pool_key: str | None = None
    size_param_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sales_volume_total: Decimal | None = None
    sales_amount_total: Decimal | None = None
    price_wavg: Decimal | None = None
    price_latest: Decimal | None = None
    price_median: Decimal | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    price_per_inch: Decimal | None = None
    main_channel_type: str | None = None
    main_platform: str | None = None
    channel_share_json: dict[str, Any] = Field(default_factory=dict)
    platform_share_json: dict[str, Any] = Field(default_factory=dict)
    price_change_recent_4w: Decimal | None = None
    sales_growth_recent_4w: Decimal | None = None
    amount_growth_recent_4w: Decimal | None = None
    price_volatility: Decimal | None = None
    sales_volatility: Decimal | None = None
    promotion_suspect_flag: bool = False
    price_percentile_in_category: Decimal | None = None
    volume_percentile_in_category: Decimal | None = None
    amount_percentile_in_category: Decimal | None = None
    price_percentile_in_size: Decimal | None = None
    volume_percentile_in_size: Decimal | None = None
    amount_percentile_in_size: Decimal | None = None
    same_pool_price_percentile: Decimal | None = None
    same_pool_volume_percentile: Decimal | None = None
    same_pool_amount_percentile: Decimal | None = None
    price_per_inch_percentile: Decimal | None = None
    same_pool_sku_count: int = Field(default=0, ge=0)
    price_band_category: M07PriceBand = M07PriceBand.UNKNOWN
    price_band_size: M07PriceBand = M07PriceBand.UNKNOWN
    price_gap_to_category_median: Decimal | None = None
    price_gap_to_size_median: Decimal | None = None
    volume_gap_to_size_median: Decimal | None = None
    amount_gap_to_size_median: Decimal | None = None
    market_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    market_evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)


class M07SkuMarketProfileRecord(M07SkuMarketMetrics):
    sku_market_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    profile_key: str = Field(min_length=1)
    category_name: str | None = None
    price_band_method: str = "category_and_size_quantile"
    rule_version: str = CORE3_M07_RULE_VERSION
    price_band_rule_version: str = CORE3_M07_PRICE_BAND_RULE_VERSION
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M07PercentileResult(M07BaseModel):
    percentile: Decimal | None = None
    sample_count: int = Field(default=0, ge=0)
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    median_value: Decimal | None = None


class M07MarketSignalRecord(M07BaseModel):
    market_signal_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_market_profile_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    signal_key: str = Field(min_length=1)
    analysis_window: M07AnalysisWindow
    signal_code: M07MarketSignalCode
    signal_name: str = Field(min_length=1)
    signal_value: Decimal | None = None
    signal_strength: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    signal_level: M07SignalLevel = M07SignalLevel.WEAK
    basis_metric: str = Field(min_length=1)
    basis_value_json: dict[str, Any] = Field(default_factory=dict)
    comparison_scope: str = Field(min_length=1)
    comparison_scope_key: str | None = None
    polarity: M07Polarity = M07Polarity.NEUTRAL
    downstream_usage_json: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M07_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M07ComparablePoolRecord(M07BaseModel):
    pool_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    pool_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    analysis_window: M07AnalysisWindow
    pool_type: M07PoolType
    pool_condition_json: dict[str, Any] = Field(default_factory=dict)
    candidate_sku_codes: list[str] = Field(default_factory=list)
    pool_sku_count: int = Field(default=0, ge=0)
    valid_member_count: int = Field(default=0, ge=0)
    target_included: bool = False
    target_size_segment: str = "unknown"
    target_price_band: M07PriceBand = M07PriceBand.UNKNOWN
    median_price: Decimal | None = None
    median_volume: Decimal | None = None
    median_amount: Decimal | None = None
    price_distribution_json: dict[str, Any] = Field(default_factory=dict)
    volume_distribution_json: dict[str, Any] = Field(default_factory=dict)
    amount_distribution_json: dict[str, Any] = Field(default_factory=dict)
    platform_distribution_json: dict[str, Any] = Field(default_factory=dict)
    pool_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    basis: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M07_RULE_VERSION
    pool_rule_version: str = CORE3_M07_POOL_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M07MarketPoolMemberRecord(M07BaseModel):
    pool_member_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    pool_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    member_sku_code: str = Field(min_length=1)
    analysis_window: M07AnalysisWindow
    member_model_name: str | None = None
    member_brand_name: str | None = None
    is_target_self: bool = False
    size_relation: str = "unknown"
    price_band_relation: str = "unknown"
    platform_overlap_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    channel_overlap_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    price_gap_to_target: Decimal | None = None
    price_gap_pct_to_target: Decimal | None = None
    volume_gap_to_target: Decimal | None = None
    amount_gap_to_target: Decimal | None = None
    member_price_percentile_in_pool: Decimal | None = None
    member_volume_percentile_in_pool: Decimal | None = None
    member_amount_percentile_in_pool: Decimal | None = None
    member_market_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    relation_strength: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M07_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M07QualityIssue(M07BaseModel):
    issue_code: str = Field(min_length=1)
    sku_code: str | None = None
    severity: str = "warning"
    message_cn: str = Field(min_length=1)
    suggestion_cn: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False


class M07DownstreamImpact(M07BaseModel):
    sku_code: str = Field(min_length=1)
    module_codes: list[str] = Field(default_factory=list)
    data_domains: list[str] = Field(default_factory=list)
    reason_cn: str = Field(min_length=1)
