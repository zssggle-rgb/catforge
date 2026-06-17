"""M01 cleaning-quality Pydantic contracts.

These schemas describe the typed boundary between M00 source registration and
the M01 cleaning service. They intentionally do not include evidence, profile,
candidate, score, selection, or report payloads from later modules.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    CORE3_M01_MODULE_VERSION,
    CORE3_RAW_SOURCE_TABLES,
    Core3CategoryCode,
    Core3CleanQualityStatus,
    Core3CleanRecordStatus,
    Core3DataDomain,
    Core3ModuleCode,
    Core3QualityIssueSeverity,
    Core3QualityIssueType,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchType,
    Core3SourceOperationType,
    Core3ValuePresenceStatus,
)


ValuePresence = Core3ValuePresenceStatus
CleanRecordStatus = Core3CleanRecordStatus
CleanQualityStatus = Core3CleanQualityStatus
ReviewStatus = Core3ReviewStatus
QualityIssueSeverity = Core3QualityIssueSeverity
QualityIssueType = Core3QualityIssueType


class Core3CleaningBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class CleaningRunRequest(Core3CleaningBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M01_MODULE_VERSION
    clean_version: str = CORE3_M01_CLEAN_VERSION
    hash_version: str = CORE3_M01_CLEAN_HASH_VERSION
    triggered_by: str = "system"
    force_rebuild: bool = False


class CleaningCounts(Core3CleaningBaseModel):
    sku: int = Field(default=0, ge=0)
    market: int = Field(default=0, ge=0)
    attribute: int = Field(default=0, ge=0)
    claim: int = Field(default=0, ge=0)
    claim_sentence: int = Field(default=0, ge=0)
    comment: int = Field(default=0, ge=0)
    comment_sentence: int = Field(default=0, ge=0)
    comment_dimension: int = Field(default=0, ge=0)
    quality_issue: int = Field(default=0, ge=0)


class QualityIssueCounts(Core3CleaningBaseModel):
    info: int = Field(default=0, ge=0)
    warning: int = Field(default=0, ge=0)
    error: int = Field(default=0, ge=0)
    review_required: int = Field(default=0, ge=0)
    by_type: dict[str, int] = Field(default_factory=dict)

    @field_validator("by_type")
    @classmethod
    def validate_by_type(cls, by_type: dict[str, int]) -> dict[str, int]:
        for issue_type, count in by_type.items():
            if issue_type not in {item.value for item in Core3QualityIssueType}:
                raise ValueError(f"unknown issue_type: {issue_type}")
            if count < 0:
                raise ValueError(f"negative issue count for {issue_type}")
        return by_type


class CleaningRunResult(Core3CleaningBaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M01
    status: Core3RunStatus
    clean_counts: CleaningCounts = Field(default_factory=CleaningCounts)
    issue_counts: QualityIssueCounts = Field(default_factory=QualityIssueCounts)
    review_required: bool = False
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CleanCoverageSummary(Core3CleaningBaseModel):
    market: dict[str, Any] = Field(default_factory=dict)
    attribute: dict[str, Any] = Field(default_factory=dict)
    claim: dict[str, Any] = Field(default_factory=dict)
    comment: dict[str, Any] = Field(default_factory=dict)
    missing_signals: dict[str, Any] = Field(default_factory=dict)
    field_conflicts: dict[str, Any] = Field(default_factory=dict)


class CleanSkuSummary(Core3CleaningBaseModel):
    clean_sku_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    category_name: str | None = None
    source_tables: list[str] = Field(default_factory=list)
    coverage: CleanCoverageSummary = Field(default_factory=CleanCoverageSummary)
    quality_status: Core3CleanQualityStatus = Core3CleanQualityStatus.OK
    quality_flags: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    clean_hash: str

    @field_validator("source_tables")
    @classmethod
    def validate_source_tables(cls, source_tables: list[str]) -> list[str]:
        unknown_tables = sorted(set(source_tables) - set(CORE3_RAW_SOURCE_TABLES))
        if unknown_tables:
            raise ValueError(f"unknown source_tables: {', '.join(unknown_tables)}")
        return source_tables


class CleanReadBase(Core3CleaningBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    source_table: str = Field(min_length=1)
    source_pk: str = Field(min_length=1)
    source_row_id: str = Field(min_length=1)
    source_row_hash: str | None = None
    source_operation_type: Core3SourceOperationType
    sku_code: str | None = None
    clean_record_key: str = Field(min_length=1)
    clean_hash: str = Field(min_length=1)
    clean_version: str = CORE3_M01_CLEAN_VERSION
    hash_version: str = CORE3_M01_CLEAN_HASH_VERSION
    quality_status: Core3CleanQualityStatus = Core3CleanQualityStatus.OK
    quality_flags: list[str] = Field(default_factory=list)
    created_at: datetime

    @field_validator("source_table")
    @classmethod
    def validate_source_table(cls, source_table: str) -> str:
        if source_table not in CORE3_RAW_SOURCE_TABLES:
            raise ValueError(f"unknown source_table: {source_table}")
        return source_table


class CleanMarketRead(CleanReadBase):
    clean_market_id: str = Field(min_length=1)
    period_raw: str | None = None
    period_type: str | None = None
    period_parse_status: str
    channel_type: str | None = None
    platform_type: str | None = None
    sales_volume: Decimal | None = None
    sales_amount: Decimal | None = None
    avg_price: Decimal | None = None
    avg_price_expected: Decimal | None = None
    price_check_status: str
    price_check_delta: Decimal | None = None
    record_status: Core3CleanRecordStatus = Core3CleanRecordStatus.ACTIVE
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS


class CleanAttributeRead(CleanReadBase):
    clean_attribute_id: str = Field(min_length=1)
    raw_attr_name: str | None = None
    clean_attr_name: str | None = None
    raw_attr_value: str | None = None
    clean_attr_value: str | None = None
    value_presence: Core3ValuePresenceStatus
    value_number_candidates: list[dict[str, Any]] = Field(default_factory=list)
    value_unit_candidates: list[str] = Field(default_factory=list)
    conflict_group_key: str | None = None
    record_status: Core3CleanRecordStatus = Core3CleanRecordStatus.ACTIVE
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS


class CleanClaimRead(CleanReadBase):
    clean_claim_id: str = Field(min_length=1)
    claim_seq: int | None = Field(default=None, ge=0)
    raw_claim_text: str | None = None
    clean_claim_text: str | None = None
    claim_text_presence: Core3ValuePresenceStatus
    title_hint: str | None = None
    structure_hints: dict[str, Any] = Field(default_factory=dict)
    record_status: Core3CleanRecordStatus = Core3CleanRecordStatus.ACTIVE
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS


class CleanCommentRead(CleanReadBase):
    clean_comment_id: str = Field(min_length=1)
    comment_id: str | None = None
    comment_time: datetime | None = None
    comment_time_parse_status: str
    clean_comment_text: str | None = None
    comment_text_presence: Core3ValuePresenceStatus
    segment_text_clean: str | None = None
    sentiment_clean: str = "unknown"
    low_value_flag: bool = False
    low_value_reason: str | None = None
    duplicate_group_key: str | None = None
    dimension_available: bool = False
    record_status: Core3CleanRecordStatus = Core3CleanRecordStatus.ACTIVE
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS


class CleanQualityIssueRead(Core3CleaningBaseModel):
    issue_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M01
    domain: Core3DataDomain
    source_table: str | None = None
    source_row_id: str | None = None
    clean_table: str | None = None
    clean_record_key: str | None = None
    sku_code: str | None = None
    issue_type: Core3QualityIssueType
    severity: Core3QualityIssueSeverity
    issue_detail: str = Field(min_length=1)
    issue_payload_json: dict[str, Any] = Field(default_factory=dict)
    suggested_downstream_action: str | None = None
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    created_at: datetime

    @field_validator("source_table")
    @classmethod
    def validate_source_table(cls, source_table: str | None) -> str | None:
        if source_table is not None and source_table not in CORE3_RAW_SOURCE_TABLES:
            raise ValueError(f"unknown source_table: {source_table}")
        return source_table
