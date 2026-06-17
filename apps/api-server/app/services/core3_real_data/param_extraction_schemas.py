"""M03 parameter extraction Pydantic contracts.

M03 schemas describe parameter-field profiling and standard parameter extraction
only. They intentionally avoid task, target-group, battlefield, competitor,
selection, score, and report conclusions from downstream modules.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.core3_real_data.constants import (
    CORE3_M03_MODULE_VERSION,
    CORE3_M03_PARSER_VERSION,
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    Core3CategoryCode,
    Core3ModuleCode,
    Core3RunStatus,
    Core3SourceBatchType,
)


class ParamDataType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"
    LIST = "list"
    RANGE = "range"
    OBJECT = "object"


class ParamGroup(StrEnum):
    PICTURE = "picture"
    GAMING = "gaming"
    SYSTEM = "system"
    EYE_CARE = "eye_care"
    CONNECTIVITY = "connectivity"
    AUDIO = "audio"
    DESIGN = "design"
    ENERGY = "energy"
    OTHER = "other"


class ParamSourceType(StrEnum):
    RAW_PARAM = "raw_param"
    DERIVED_FROM_CLAIM = "derived_from_claim"
    MODEL_NAME = "model_name"


class ParamMatchType(StrEnum):
    EXACT_ALIAS = "exact_alias"
    STANDARD_NAME = "standard_name"
    CONTAINS_ALIAS = "contains_alias"
    KEYWORD = "keyword"
    VALUE_PATTERN = "value_pattern"
    UNMAPPED = "unmapped"


class ParamCandidateStatus(StrEnum):
    MATCHED = "matched"
    CANDIDATE = "candidate"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    IGNORED = "ignored"


class ParamReviewStatus(StrEnum):
    AUTO_PASS = "auto_pass"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


class ParamParserStatus(StrEnum):
    PARSED = "parsed"
    UNKNOWN = "unknown"
    FAILED = "failed"
    SCOPE_UNCERTAIN = "scope_uncertain"
    UNIT_UNCERTAIN = "unit_uncertain"
    CONFLICT = "conflict"


class ParamConflictType(StrEnum):
    SAME_PARAM_MULTI_VALUE = "same_param_multi_value"
    RAW_PARAM_VS_CLAIM_CONFLICT = "raw_param_vs_claim_conflict"
    UNIT_UNCERTAIN = "unit_uncertain"
    SCOPE_UNCERTAIN = "scope_uncertain"
    BOOLEAN_UNKNOWN = "boolean_unknown"
    HDMI_VERSION_COUNT_MIXED = "hdmi_version_count_mixed"


class ParamConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Core3ParamBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class StdParamDefinition(Core3ParamBaseModel):
    param_code: str = Field(min_length=1)
    param_name: str = Field(min_length=1)
    data_type: ParamDataType
    param_group: ParamGroup
    aliases: list[str] = Field(default_factory=list)
    value_parsers: list[str] = Field(default_factory=list)
    unit: str | None = None
    enum_values: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_types: list[ParamSourceType] = Field(default_factory=lambda: [ParamSourceType.RAW_PARAM])
    parser_config_json: dict[str, Any] = Field(default_factory=dict)
    description_cn: str | None = None
    required_for_core: bool = False
    priority: int = Field(default=0, ge=0)

    @field_validator("aliases", "value_parsers", "enum_values", "keywords")
    @classmethod
    def validate_non_empty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list values must not contain empty strings")
        return values


class StdParamSeed(Core3ParamBaseModel):
    seed_version: str = CORE3_M03_SEED_VERSION
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    standard_params: list[StdParamDefinition] = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_param_codes(self) -> "StdParamSeed":
        param_codes = [item.param_code for item in self.standard_params]
        if len(param_codes) != len(set(param_codes)):
            raise ValueError("param_code must be unique in standard_params")
        return self


class ParamExtractionRunRequest(Core3ParamBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M03_MODULE_VERSION
    seed_version: str = CORE3_M03_SEED_VERSION
    parser_version: str = CORE3_M03_PARSER_VERSION
    rule_version: str = CORE3_M03_RULE_VERSION
    target_sku_codes: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("target_sku_codes")
    @classmethod
    def validate_target_sku_codes(cls, target_sku_codes: list[str]) -> list[str]:
        if any(not sku_code.strip() for sku_code in target_sku_codes):
            raise ValueError("target_sku_codes must not contain empty values")
        return target_sku_codes


class ParamExtractionRunResult(Core3ParamBaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M03
    status: Core3RunStatus
    field_profile_count: int = Field(default=0, ge=0)
    param_value_count: int = Field(default=0, ge=0)
    sku_profile_count: int = Field(default=0, ge=0)
    alias_candidate_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    review_required: bool = False
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ParamReadBase(Core3ParamBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ParamFieldProfileRead(ParamReadBase):
    field_profile_id: str = Field(min_length=1)
    raw_param_name: str | None = None
    clean_param_name: str = Field(min_length=1)
    normalized_param_name: str | None = None
    occurrence_count: int = Field(default=0, ge=0)
    sku_coverage_count: int = Field(default=0, ge=0)
    sku_coverage_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    unknown_count: int = Field(default=0, ge=0)
    unknown_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    present_count: int = Field(default=0, ge=0)
    top_values_json: list[Any] = Field(default_factory=list)
    value_pattern_summary_json: dict[str, Any] = Field(default_factory=dict)
    matched_param_code: str | None = None
    matched_param_name: str | None = None
    param_group: ParamGroup | None = None
    match_type: ParamMatchType = ParamMatchType.UNMAPPED
    alias_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    candidate_status: ParamCandidateStatus = ParamCandidateStatus.CANDIDATE
    review_required: bool = False
    review_status: ParamReviewStatus = ParamReviewStatus.AUTO_PASS
    review_reason: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    field_profile_hash: str = Field(min_length=1)
    seed_version: str = CORE3_M03_SEED_VERSION
    rule_version: str = CORE3_M03_RULE_VERSION


class ExtractParamValueRead(ParamReadBase):
    param_value_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    param_code: str = Field(min_length=1)
    param_name: str = Field(min_length=1)
    param_group: ParamGroup | None = None
    data_type: ParamDataType
    normalized_value: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    numeric_value: Decimal | None = None
    value_text: str | None = None
    unit: str | None = None
    value_level: str | None = None
    value_presence: str | None = None
    source_type: ParamSourceType
    source_priority_rank: int = Field(default=0, ge=0)
    raw_param_name: str | None = None
    raw_param_value: str | None = None
    match_type: ParamMatchType = ParamMatchType.UNMAPPED
    parser_type: str | None = None
    parser_status: ParamParserStatus = ParamParserStatus.UNKNOWN
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: ParamConfidenceLevel = ParamConfidenceLevel.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    primary_evidence_id: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)
    conflict_flag: bool = False
    conflict_id: str | None = None
    review_required: bool = False
    review_status: ParamReviewStatus = ParamReviewStatus.AUTO_PASS
    param_value_hash: str = Field(min_length=1)
    seed_version: str = CORE3_M03_SEED_VERSION
    parser_version: str = CORE3_M03_PARSER_VERSION
    rule_version: str = CORE3_M03_RULE_VERSION


class ParamAliasCandidateRead(ParamReadBase):
    alias_candidate_id: str = Field(min_length=1)
    raw_param_name: str | None = None
    clean_param_name: str = Field(min_length=1)
    sku_coverage_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    unknown_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    top_values_json: list[Any] = Field(default_factory=list)
    value_pattern_summary_json: dict[str, Any] = Field(default_factory=dict)
    suggested_param_code: str | None = None
    suggestion_reason: str | None = None
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    candidate_type: str = "unmatched_field"
    review_required: bool = True
    review_status: ParamReviewStatus = ParamReviewStatus.REVIEW_REQUIRED
    review_decision_json: dict[str, Any] = Field(default_factory=dict)
    seed_version: str = CORE3_M03_SEED_VERSION


class ParamValueConflictRead(ParamReadBase):
    conflict_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    param_code: str = Field(min_length=1)
    conflict_type: ParamConflictType
    candidate_values_json: list[Any] = Field(default_factory=list)
    preferred_value_json: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    preferred_source_type: ParamSourceType | None = None
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    review_required: bool = True
    review_status: ParamReviewStatus = ParamReviewStatus.REVIEW_REQUIRED
    review_reason: dict[str, Any] | None = None
    rule_version: str = CORE3_M03_RULE_VERSION


class SkuParamProfileRead(ParamReadBase):
    sku_param_profile_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    param_values_json: dict[str, Any] = Field(default_factory=dict)
    core_picture_params_json: dict[str, Any] = Field(default_factory=dict)
    core_gaming_params_json: dict[str, Any] = Field(default_factory=dict)
    core_system_params_json: dict[str, Any] = Field(default_factory=dict)
    core_eye_care_params_json: dict[str, Any] = Field(default_factory=dict)
    param_completeness: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    known_param_count: int = Field(default=0, ge=0)
    unknown_param_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    profile_hash: str = Field(min_length=1)
    seed_version: str = CORE3_M03_SEED_VERSION
    rule_version: str = CORE3_M03_RULE_VERSION


class SkuParamQuery(Core3ParamBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    sku_code: str | None = None
    param_codes: list[str] = Field(default_factory=list)
    param_groups: list[ParamGroup] = Field(default_factory=list)
    source_types: list[ParamSourceType] = Field(default_factory=list)
    review_required: bool | None = None
    include_conflicts: bool = True
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @field_validator("param_codes")
    @classmethod
    def validate_param_codes(cls, param_codes: list[str]) -> list[str]:
        if any(not param_code.strip() for param_code in param_codes):
            raise ValueError("param_codes must not contain empty values")
        return param_codes
