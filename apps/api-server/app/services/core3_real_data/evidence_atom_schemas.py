"""M02 evidence atom Pydantic contracts.

M02 schemas describe reusable data evidence only. They intentionally avoid
task, target-group, battlefield, competitor, score, and report conclusions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.core3_real_data.constants import (
    CORE3_M02_CLEAN_SOURCE_TABLES,
    CORE3_M02_CONFIDENCE_RULE_VERSION,
    CORE3_M02_EVIDENCE_VERSION,
    CORE3_M02_MODULE_VERSION,
    CORE3_RAW_SOURCE_TABLES,
    Core3CategoryCode,
    Core3CleanQualityStatus,
    Core3ConfidenceLevel,
    Core3EvidenceGrain,
    Core3EvidenceInactiveReason,
    Core3EvidenceLinkStatus,
    Core3EvidenceLinkType,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchType,
)


EvidenceType = Core3EvidenceType
EvidenceGrain = Core3EvidenceGrain
EvidenceStatus = Core3EvidenceStatus
EvidenceInactiveReason = Core3EvidenceInactiveReason
EvidenceLinkType = Core3EvidenceLinkType
EvidenceLinkStatus = Core3EvidenceLinkStatus
ConfidenceLevel = Core3ConfidenceLevel


class Core3EvidenceBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def _validate_count_map(values: dict[str, int], allowed_values: set[str], label: str) -> dict[str, int]:
    for key, count in values.items():
        if key not in allowed_values:
            raise ValueError(f"unknown {label}: {key}")
        if count < 0:
            raise ValueError(f"negative count for {key}")
    return values


class EvidenceRunRequest(Core3EvidenceBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M02_MODULE_VERSION
    evidence_version: str = CORE3_M02_EVIDENCE_VERSION
    confidence_rule_version: str = CORE3_M02_CONFIDENCE_RULE_VERSION
    target_sku_codes: list[str] = Field(default_factory=list)
    include_inactive_clean_records: bool = False
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("target_sku_codes")
    @classmethod
    def validate_target_sku_codes(cls, target_sku_codes: list[str]) -> list[str]:
        if any(not sku_code.strip() for sku_code in target_sku_codes):
            raise ValueError("target_sku_codes must not contain empty values")
        return target_sku_codes


class EvidenceCounts(Core3EvidenceBaseModel):
    sku_fact: int = Field(default=0, ge=0)
    market_fact: int = Field(default=0, ge=0)
    param_raw: int = Field(default=0, ge=0)
    promo_raw: int = Field(default=0, ge=0)
    promo_sentence: int = Field(default=0, ge=0)
    comment_raw: int = Field(default=0, ge=0)
    comment_sentence: int = Field(default=0, ge=0)
    comment_dimension: int = Field(default=0, ge=0)
    quality_issue: int = Field(default=0, ge=0)
    link: int = Field(default=0, ge=0)
    current: int = Field(default=0, ge=0)
    inactive: int = Field(default=0, ge=0)
    superseded: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    low_confidence: int = Field(default=0, ge=0)
    review_required: int = Field(default=0, ge=0)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    by_confidence_level: dict[str, int] = Field(default_factory=dict)

    @field_validator("by_type")
    @classmethod
    def validate_by_type(cls, by_type: dict[str, int]) -> dict[str, int]:
        return _validate_count_map(by_type, {item.value for item in Core3EvidenceType}, "evidence_type")

    @field_validator("by_status")
    @classmethod
    def validate_by_status(cls, by_status: dict[str, int]) -> dict[str, int]:
        return _validate_count_map(by_status, {item.value for item in Core3EvidenceStatus}, "evidence_status")

    @field_validator("by_confidence_level")
    @classmethod
    def validate_by_confidence_level(cls, by_confidence_level: dict[str, int]) -> dict[str, int]:
        return _validate_count_map(
            by_confidence_level,
            {item.value for item in Core3ConfidenceLevel},
            "confidence_level",
        )


class EvidenceSummary(Core3EvidenceBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    evidence_counts: EvidenceCounts = Field(default_factory=EvidenceCounts)
    source_clean_tables: list[str] = Field(default_factory=list)
    missing_clean_tables: list[str] = Field(default_factory=list)
    low_confidence_reasons: dict[str, int] = Field(default_factory=dict)
    quality_summary_cn: str | None = None
    review_required: bool = False

    @field_validator("source_clean_tables", "missing_clean_tables")
    @classmethod
    def validate_clean_tables(cls, clean_tables: list[str]) -> list[str]:
        unknown_tables = sorted(set(clean_tables) - set(CORE3_M02_CLEAN_SOURCE_TABLES))
        if unknown_tables:
            raise ValueError(f"unknown clean_table: {', '.join(unknown_tables)}")
        return clean_tables


class EvidenceRunResult(Core3EvidenceBaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M02
    status: Core3RunStatus
    evidence_counts: EvidenceCounts = Field(default_factory=EvidenceCounts)
    summary: EvidenceSummary | None = None
    review_required: bool = False
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class EvidenceAtomRead(Core3EvidenceBaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_key: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    evidence_type: Core3EvidenceType
    evidence_grain: Core3EvidenceGrain
    evidence_field: str = Field(min_length=1)
    evidence_title: str | None = None
    source_table: str | None = None
    source_pk: str | None = None
    source_row_id: str | None = None
    source_row_hash: str | None = None
    clean_table: str = Field(min_length=1)
    clean_record_key: str = Field(min_length=1)
    clean_hash: str = Field(min_length=1)
    clean_version: str = Field(min_length=1)
    raw_field: str | None = None
    raw_value: str | None = None
    clean_field: str | None = None
    clean_value: str | None = None
    value_presence: str | None = None
    numeric_value: Decimal | None = None
    numeric_values_json: list[Any] = Field(default_factory=list)
    unit_value: str | None = None
    text_value: str | None = None
    text_hash: str | None = None
    evidence_time: datetime | None = None
    period_raw: str | None = None
    period_week_index: int | None = None
    channel_type: str | None = None
    platform_type: str | None = None
    comment_id: str | None = None
    comment_text_hash: str | None = None
    segment_text_hash: str | None = None
    sentence_seq: int | None = Field(default=None, ge=0)
    dimension_path_raw: str | None = None
    quality_status: Core3CleanQualityStatus = Core3CleanQualityStatus.OK
    quality_flags: list[str] = Field(default_factory=list)
    base_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_status: str | None = None
    evidence_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_status: Core3EvidenceStatus = Core3EvidenceStatus.CURRENT
    inactive_reason: Core3EvidenceInactiveReason | None = None
    is_current: bool = True
    evidence_version: str = CORE3_M02_EVIDENCE_VERSION
    confidence_rule_version: str = CORE3_M02_CONFIDENCE_RULE_VERSION
    asset_version: str = "default"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    created_at: datetime
    updated_at: datetime

    @field_validator("source_table")
    @classmethod
    def validate_source_table(cls, source_table: str | None) -> str | None:
        if source_table is not None and source_table not in CORE3_RAW_SOURCE_TABLES:
            raise ValueError(f"unknown source_table: {source_table}")
        return source_table

    @field_validator("clean_table")
    @classmethod
    def validate_clean_table(cls, clean_table: str) -> str:
        if clean_table not in CORE3_M02_CLEAN_SOURCE_TABLES:
            raise ValueError(f"unknown clean_table: {clean_table}")
        return clean_table


class EvidenceAtomListItem(Core3EvidenceBaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_key: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    evidence_type: Core3EvidenceType
    evidence_grain: Core3EvidenceGrain
    evidence_field: str = Field(min_length=1)
    evidence_title: str | None = None
    clean_table: str = Field(min_length=1)
    clean_record_key: str = Field(min_length=1)
    source_row_id: str | None = None
    quality_status: Core3CleanQualityStatus = Core3CleanQualityStatus.OK
    quality_flags: list[str] = Field(default_factory=list)
    base_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    evidence_status: Core3EvidenceStatus = Core3EvidenceStatus.CURRENT
    is_current: bool = True
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    created_at: datetime

    @field_validator("clean_table")
    @classmethod
    def validate_clean_table(cls, clean_table: str) -> str:
        if clean_table not in CORE3_M02_CLEAN_SOURCE_TABLES:
            raise ValueError(f"unknown clean_table: {clean_table}")
        return clean_table


class EvidenceLinkRead(Core3EvidenceBaseModel):
    link_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    from_evidence_id: str = Field(min_length=1)
    to_evidence_id: str = Field(min_length=1)
    from_evidence_key: str = Field(min_length=1)
    to_evidence_key: str = Field(min_length=1)
    link_type: Core3EvidenceLinkType
    link_payload_json: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal("1.0000"), ge=0, le=1)
    link_status: Core3EvidenceLinkStatus = Core3EvidenceLinkStatus.CURRENT
    created_at: datetime
    updated_at: datetime


class SkuEvidenceQuery(Core3EvidenceBaseModel):
    project_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    evidence_types: list[Core3EvidenceType] = Field(default_factory=list)
    evidence_statuses: list[Core3EvidenceStatus] = Field(
        default_factory=lambda: [Core3EvidenceStatus.CURRENT]
    )
    min_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    include_links: bool = True
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SkuEvidenceResponse(Core3EvidenceBaseModel):
    query: SkuEvidenceQuery
    items: list[EvidenceAtomListItem] = Field(default_factory=list)
    links: list[EvidenceLinkRead] = Field(default_factory=list)
    summary: EvidenceSummary | None = None
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class EvidenceTraceResponse(Core3EvidenceBaseModel):
    evidence: EvidenceAtomRead
    upstream_links: list[EvidenceLinkRead] = Field(default_factory=list)
    downstream_links: list[EvidenceLinkRead] = Field(default_factory=list)
    related_evidence: list[EvidenceAtomListItem] = Field(default_factory=list)
    trace_summary_cn: str | None = None
