"""M03A parameter taxonomy contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


M03A_RULE_VERSION = "m03a_param_taxonomy_v1"
M03A_PROMPT_VERSION = "m03a_param_taxonomy_prompt_v1"
DOWNSTREAM_CODE_PREFIXES = ("CLAIM_", "TASK_", "TG_", "BF_", "BATTLEFIELD_")


class TaxonomyStatus(StrEnum):
    DRAFT = "draft"
    REVIEW_READY = "review_ready"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class RawFieldStatus(StrEnum):
    USABLE = "usable"
    METADATA = "metadata"
    WEAK_SIGNAL = "weak_signal"
    IGNORE = "ignore"
    REVIEW_REQUIRED = "review_required"


class ClusterMethod(StrEnum):
    NAME_SIMILARITY = "name_similarity"
    VALUE_PATTERN = "value_pattern"
    COOCCURRENCE = "cooccurrence"
    LLM_SEMANTIC = "llm_semantic"
    MANUAL = "manual"
    RULE = "rule"


class MappingType(StrEnum):
    DIRECT = "direct"
    ALIAS = "alias"
    DERIVED_HELPER = "derived_helper"
    METADATA = "metadata"
    WEAK_SIGNAL = "weak_signal"
    IGNORE = "ignore"
    REVIEW_REQUIRED = "review_required"


class ValuePolicy(StrEnum):
    USE_AS_VALUE = "use_as_value"
    USE_AS_HELPER = "use_as_helper"
    DO_NOT_EXTRACT = "do_not_extract"
    REQUIRES_RULE = "requires_rule"


class EvidenceRole(StrEnum):
    STRONG_PARAM_EVIDENCE = "strong_param_evidence"
    SUPPORTING_PARAM_EVIDENCE = "supporting_param_evidence"
    WEAK_SIGNAL = "weak_signal"
    METADATA_ONLY = "metadata_only"


class AnalysisStatus(StrEnum):
    ACTIVE = "active"
    UNSUPPORTED_IN_CURRENT_DATA = "unsupported_in_current_data"
    DEPRECATED = "deprecated"
    REVIEW_REQUIRED = "review_required"


class TaxonomyReviewSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class TaxonomyReviewStatus(StrEnum):
    AUTO_PASS = "auto_pass"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


class ParamTaxonomyBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class ParamTaxonomyDraftRequest(ParamTaxonomyBaseModel):
    category_code: str = Field(min_length=1)
    batch_ids: list[str] = Field(min_length=1)
    taxonomy_version: str | None = None
    use_llm: bool = True
    force_rebuild: bool = False
    created_by: str = "system"
    rule_version: str = M03A_RULE_VERSION

    @field_validator("category_code")
    @classmethod
    def normalize_category_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("category_code is required")
        return normalized

    @field_validator("batch_ids")
    @classmethod
    def validate_batch_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("batch_ids must not contain empty values")
        return normalized


class ParamTaxonomyDraftResult(ParamTaxonomyBaseModel):
    taxonomy_version: str
    status: TaxonomyStatus
    source_field_count: int = Field(ge=0)
    active_param_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    blocking_review_count: int = Field(ge=0)
    taxonomy_hash: str
    warnings: list[str] = Field(default_factory=list)


class ParamTaxonomyVersionRead(ParamTaxonomyBaseModel):
    taxonomy_version_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    status: TaxonomyStatus
    source_batch_ids: list[str] = Field(default_factory=list)
    source_field_count: int = Field(ge=0)
    active_param_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    blocking_review_count: int = Field(ge=0)
    llm_model_snapshot: str | None = None
    llm_prompt_version: str | None = None
    rule_version: str
    taxonomy_hash: str
    published_at: datetime | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class ParamRawFieldInventoryRead(ParamTaxonomyBaseModel):
    raw_field_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    raw_param_name: str
    clean_param_name: str
    normalized_param_name: str
    occurrence_count: int = Field(ge=0)
    sku_coverage_count: int = Field(ge=0)
    sku_coverage_rate: Decimal = Field(ge=0, le=1)
    unknown_count: int = Field(ge=0)
    unknown_rate: Decimal = Field(ge=0, le=1)
    top_values_json: list[Any] = Field(default_factory=list)
    sample_values_json: list[Any] = Field(default_factory=list)
    value_pattern_json: dict[str, Any] = Field(default_factory=dict)
    unit_candidates_json: list[Any] = Field(default_factory=list)
    cooccurrence_field_names: list[str] = Field(default_factory=list)
    field_status: RawFieldStatus
    field_hash: str


class ParamFieldClusterRead(ParamTaxonomyBaseModel):
    field_cluster_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    cluster_code: str
    cluster_name_candidate: str | None = None
    member_raw_fields: list[str] = Field(default_factory=list)
    cluster_method: ClusterMethod
    cluster_confidence: Decimal = Field(ge=0, le=1)
    cluster_reason_json: dict[str, Any] = Field(default_factory=dict)
    review_status: TaxonomyReviewStatus


class ParamConceptCandidateInput(ParamTaxonomyBaseModel):
    candidate_code: str = Field(min_length=1)
    candidate_name: str = Field(min_length=1)
    source_cluster_ids: list[str] = Field(default_factory=list)
    source_raw_fields: list[str] = Field(min_length=1)
    definition_candidate: str = Field(min_length=1)
    data_type_candidate: str = "string"
    unit_candidate: str | None = None
    parser_candidate: str | None = None
    capability_tags: list[str] = Field(default_factory=list)
    benefit_hints: list[str] = Field(default_factory=list)
    scenario_hints: list[str] = Field(default_factory=list)
    comparison_axis: str = "not_comparable"
    evidence_role: EvidenceRole = EvidenceRole.WEAK_SIGNAL
    risk_notes: list[str] = Field(default_factory=list)
    llm_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    rule_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    review_required: bool = True
    review_status: TaxonomyReviewStatus = TaxonomyReviewStatus.REVIEW_REQUIRED

    @field_validator("capability_tags")
    @classmethod
    def validate_capability_tags(cls, values: list[str]) -> list[str]:
        _reject_downstream_codes(values)
        return values


class ParamConceptCandidateRead(ParamConceptCandidateInput):
    concept_candidate_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    created_at: datetime
    updated_at: datetime


class ParamDefinitionInput(ParamTaxonomyBaseModel):
    param_code: str = Field(min_length=1)
    param_name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    param_group: str = "other"
    data_type: str = "string"
    unit: str | None = None
    value_parser: str = "string"
    parser_config_json: dict[str, Any] = Field(default_factory=dict)
    source_raw_fields: list[str] = Field(min_length=1)
    capability_tags: list[str] = Field(default_factory=list)
    benefit_hints: list[str] = Field(default_factory=list)
    scenario_hints: list[str] = Field(default_factory=list)
    comparison_axis: str = "not_comparable"
    evidence_role: EvidenceRole = EvidenceRole.WEAK_SIGNAL
    analysis_status: AnalysisStatus = AnalysisStatus.ACTIVE
    review_status: TaxonomyReviewStatus = TaxonomyReviewStatus.AUTO_PASS
    definition_hash: str

    @field_validator("capability_tags")
    @classmethod
    def validate_capability_tags(cls, values: list[str]) -> list[str]:
        _reject_downstream_codes(values)
        return values

    @model_validator(mode="after")
    def validate_active_has_source_fields(self) -> "ParamDefinitionInput":
        if self.analysis_status == AnalysisStatus.ACTIVE and not self.source_raw_fields:
            raise ValueError("active param definition must have source_raw_fields")
        return self


class ParamDefinitionRead(ParamDefinitionInput):
    param_definition_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    created_at: datetime
    updated_at: datetime


class ParamFieldMappingRuleInput(ParamTaxonomyBaseModel):
    raw_param_name: str = Field(min_length=1)
    param_code: str | None = None
    mapping_type: MappingType = MappingType.REVIEW_REQUIRED
    value_policy: ValuePolicy = ValuePolicy.REQUIRES_RULE
    parser_type: str | None = None
    parser_config_json: dict[str, Any] = Field(default_factory=dict)
    invalid_value_policy_json: dict[str, Any] = Field(default_factory=dict)
    source_priority: int = Field(default=100, ge=0)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    review_status: TaxonomyReviewStatus = TaxonomyReviewStatus.REVIEW_REQUIRED


class ParamFieldMappingRuleRead(ParamFieldMappingRuleInput):
    mapping_rule_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    created_at: datetime
    updated_at: datetime


class ParamTaxonomyReviewItemInput(ParamTaxonomyBaseModel):
    item_type: str = Field(min_length=1)
    severity: TaxonomyReviewSeverity = TaxonomyReviewSeverity.WARNING
    raw_param_name: str | None = None
    param_code: str | None = None
    issue_summary_cn: str = Field(min_length=1)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str = "review"
    review_decision_json: dict[str, Any] = Field(default_factory=dict)
    review_status: TaxonomyReviewStatus = TaxonomyReviewStatus.REVIEW_REQUIRED


class ParamTaxonomyReviewItemRead(ParamTaxonomyReviewItemInput):
    review_item_id: str
    taxonomy_version: str
    project_id: str
    category_code: str
    created_at: datetime
    updated_at: datetime


class ParamTaxonomyOut(ParamTaxonomyBaseModel):
    version: ParamTaxonomyVersionRead
    fields: list[ParamRawFieldInventoryRead] = Field(default_factory=list)
    clusters: list[ParamFieldClusterRead] = Field(default_factory=list)
    candidates: list[ParamConceptCandidateRead] = Field(default_factory=list)
    definitions: list[ParamDefinitionRead] = Field(default_factory=list)
    mapping_rules: list[ParamFieldMappingRuleRead] = Field(default_factory=list)
    review_items: list[ParamTaxonomyReviewItemRead] = Field(default_factory=list)


class ParamTaxonomyReviewItemListOut(ParamTaxonomyBaseModel):
    items: list[ParamTaxonomyReviewItemRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ParamTaxonomyReviewDecisionRequest(ParamTaxonomyBaseModel):
    review_item_id: str = Field(min_length=1)
    decision: TaxonomyReviewStatus
    decision_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: TaxonomyReviewStatus) -> TaxonomyReviewStatus:
        if value not in {
            TaxonomyReviewStatus.APPROVED,
            TaxonomyReviewStatus.REJECTED,
            TaxonomyReviewStatus.WAIVED,
        }:
            raise ValueError("decision must be approved, rejected, or waived")
        return value


class ParamTaxonomyPublishRequest(ParamTaxonomyBaseModel):
    published_by: str = "system"


def _reject_downstream_codes(values: list[str]) -> None:
    invalid = [
        value
        for value in values
        if any(value.upper().startswith(prefix) for prefix in DOWNSTREAM_CODE_PREFIXES)
    ]
    if invalid:
        raise ValueError(f"capability_tags must not contain downstream business codes: {', '.join(invalid)}")
