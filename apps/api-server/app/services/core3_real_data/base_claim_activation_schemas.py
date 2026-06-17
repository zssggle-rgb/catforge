"""M04a base claim activation Pydantic contracts.

M04a schemas describe standard-claim seed definitions, promo/param claim hits,
claim-source coverage, and base claim activation only. They intentionally stop
before comment validation, task, target-group, battlefield, competitor,
selection, score, and report conclusions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.core3_real_data.constants import (
    CORE3_M04A_MODULE_VERSION,
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3ModuleCode,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchType,
)


class ClaimGroup(StrEnum):
    PICTURE = "picture"
    GAMING = "gaming"
    MOTION = "motion"
    EYE_CARE = "eye_care"
    SMART = "smart"
    AUDIO = "audio"
    DESIGN = "design"
    VALUE = "value"
    SERVICE = "service"


class ClaimType(StrEnum):
    TECHNICAL = "technical"
    EXPERIENCE = "experience"
    SERVICE = "service"
    VALUE = "value"
    DESIGN = "design"
    MIXED = "mixed"


class ClaimHitSourceType(StrEnum):
    PROMO_RAW = "promo_raw"
    PROMO_SENTENCE = "promo_sentence"
    PARAM_SUPPORT = "param_support"
    QUALITY_GAP = "quality_gap"


class ClaimMatchMethod(StrEnum):
    EXACT_ALIAS = "exact_alias"
    KEYWORD = "keyword"
    ENTITY = "entity"
    PARAM_SUPPORT = "param_support"
    QUALITY_GAP = "quality_gap"


class ClaimSeedSourceType(StrEnum):
    STANDARD_PARAM = "standard_param"
    CLAIM_TEXT = "claim_text"
    RAW_PARAM = "raw_param"


class ClaimSourceStatus(StrEnum):
    HAS_STRUCTURED_CLAIM = "has_structured_claim"
    MISSING_STRUCTURED_CLAIM = "missing_structured_claim"
    CLAIM_DATA_INSUFFICIENT = "claim_data_insufficient"
    CLAIM_CONFLICT = "claim_conflict"


class ClaimActivationBasis(StrEnum):
    PARAM_AND_PROMO = "param_and_promo"
    PARAM_ONLY = "param_only"
    PROMO_ONLY = "promo_only"
    INSUFFICIENT = "insufficient"


class ClaimActivationLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


ClaimConfidenceLevel = Core3ConfidenceLevel
ClaimReviewStatus = Core3ReviewStatus


class Core3BaseClaimBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def _validate_non_empty_strings(values: list[str], field_name: str) -> list[str]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain empty values")
    return values


class StdClaimDefinition(Core3BaseClaimBaseModel):
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: ClaimGroup
    claim_type: ClaimType = ClaimType.MIXED
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    promo_keywords: list[str] = Field(default_factory=list)
    source_types: list[ClaimSeedSourceType] = Field(default_factory=list)
    evidence_requirement: list[str] = Field(default_factory=list)
    supporting_param_codes: list[str] = Field(default_factory=list)
    mapped_param_codes: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)
    comment_topic_codes: list[str] = Field(default_factory=list)
    activation_rule: dict[str, Any] = Field(default_factory=dict)
    activation_weights: dict[str, Decimal] = Field(default_factory=dict)
    param_only_allowed: bool = False
    description_cn: str | None = None
    priority: int = Field(default=0, ge=0)

    @field_validator(
        "aliases",
        "keywords",
        "promo_keywords",
        "evidence_requirement",
        "supporting_param_codes",
        "mapped_param_codes",
        "mapped_task_codes",
        "mapped_battlefield_codes",
        "comment_topic_codes",
    )
    @classmethod
    def validate_non_empty_list_values(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "claim seed list values")

    @field_validator("activation_weights")
    @classmethod
    def validate_activation_weights(cls, weights: dict[str, Decimal]) -> dict[str, Decimal]:
        unsupported_keys = sorted(set(weights) - {"param", "promo"})
        if unsupported_keys:
            raise ValueError(f"activation_weights has unsupported keys for M04a: {', '.join(unsupported_keys)}")
        if any(weight < 0 for weight in weights.values()):
            raise ValueError("activation_weights must not contain negative values")
        return weights


class StdClaimSeed(Core3BaseClaimBaseModel):
    seed_version: str = CORE3_M04A_SEED_VERSION
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    standard_claims: list[StdClaimDefinition] = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_claim_codes(self) -> "StdClaimSeed":
        claim_codes = [item.claim_code for item in self.standard_claims]
        if len(claim_codes) != len(set(claim_codes)):
            raise ValueError("claim_code must be unique in standard_claims")
        return self


class BaseClaimActivationRunRequest(Core3BaseClaimBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M04A_MODULE_VERSION
    seed_version: str = CORE3_M04A_SEED_VERSION
    rule_version: str = CORE3_M04A_RULE_VERSION
    target_sku_codes: list[str] = Field(default_factory=list)
    include_param_only_claims: bool = True
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("target_sku_codes")
    @classmethod
    def validate_target_sku_codes(cls, target_sku_codes: list[str]) -> list[str]:
        return _validate_non_empty_strings(target_sku_codes, "target_sku_codes")


class BaseClaimActivationRunResult(Core3BaseClaimBaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M04A
    status: Core3RunStatus
    source_status_count: int = Field(default=0, ge=0)
    claim_hit_count: int = Field(default=0, ge=0)
    activation_count: int = Field(default=0, ge=0)
    param_only_claim_count: int = Field(default=0, ge=0)
    missing_structured_claim_sku_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    review_required: bool = False
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ClaimReadBase(Core3BaseClaimBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ClaimHitRead(ClaimReadBase):
    claim_hit_id: str = Field(min_length=1)
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: ClaimGroup
    hit_source_type: ClaimHitSourceType
    source_sentence_key: str | None = None
    claim_seq: int | None = Field(default=None, ge=0)
    sentence_seq: int | None = Field(default=None, ge=0)
    claim_fragment: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    title_hint: str | None = None
    extracted_entity_json: dict[str, Any] = Field(default_factory=dict)
    matched_param_codes: list[str] = Field(default_factory=list)
    match_method: ClaimMatchMethod
    promo_evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    quality_evidence_ids: list[str] = Field(default_factory=list)
    match_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_status: ClaimReviewStatus = ClaimReviewStatus.AUTO_PASS
    hit_hash: str = Field(min_length=1)
    seed_version: str = CORE3_M04A_SEED_VERSION
    rule_version: str = CORE3_M04A_RULE_VERSION

    @field_validator(
        "matched_keywords",
        "matched_param_codes",
        "promo_evidence_ids",
        "param_evidence_ids",
        "quality_evidence_ids",
        "quality_flags",
    )
    @classmethod
    def validate_string_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "claim hit list values")


class ClaimSourceStatusRead(ClaimReadBase):
    claim_source_status_id: str = Field(min_length=1)
    claim_source_status: ClaimSourceStatus
    structured_claim_count: int = Field(default=0, ge=0)
    claim_sentence_count: int = Field(default=0, ge=0)
    promo_evidence_count: int = Field(default=0, ge=0)
    param_only_claim_count: int = Field(default=0, ge=0)
    quality_evidence_ids: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    conflict_summary_json: dict[str, Any] = Field(default_factory=dict)
    status_note: str = ""
    review_required: bool = False
    review_status: ClaimReviewStatus = ClaimReviewStatus.AUTO_PASS
    status_hash: str = Field(min_length=1)
    seed_version: str = CORE3_M04A_SEED_VERSION
    rule_version: str = CORE3_M04A_RULE_VERSION

    @field_validator("quality_evidence_ids", "missing_signals")
    @classmethod
    def validate_status_string_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "claim source status list values")


class ClaimActivationBaseRead(ClaimReadBase):
    claim_activation_base_id: str = Field(min_length=1)
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: ClaimGroup
    claim_type: ClaimType
    param_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    promo_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    base_activation_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    activation_level: ClaimActivationLevel = ClaimActivationLevel.UNKNOWN
    activation_basis: ClaimActivationBasis = ClaimActivationBasis.INSUFFICIENT
    param_support_json: dict[str, Any] = Field(default_factory=dict)
    promo_support_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals: list[str] = Field(default_factory=list)
    conflict_flags: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: ClaimConfidenceLevel = ClaimConfidenceLevel.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    promo_evidence_ids: list[str] = Field(default_factory=list)
    quality_evidence_ids: list[str] = Field(default_factory=list)
    claim_hit_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_status: ClaimReviewStatus = ClaimReviewStatus.AUTO_PASS
    review_reason: str | None = None
    activation_hash: str = Field(min_length=1)
    seed_version: str = CORE3_M04A_SEED_VERSION
    rule_version: str = CORE3_M04A_RULE_VERSION

    @field_validator(
        "missing_signals",
        "conflict_flags",
        "evidence_ids",
        "param_evidence_ids",
        "promo_evidence_ids",
        "quality_evidence_ids",
        "claim_hit_ids",
    )
    @classmethod
    def validate_activation_string_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "claim activation list values")


class SkuClaimBaseResponse(Core3BaseClaimBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    source_status: ClaimSourceStatusRead | None = None
    base_claims: list[ClaimActivationBaseRead] = Field(default_factory=list)
    claim_hits: list[ClaimHitRead] = Field(default_factory=list)
    total_base_claim_count: int = Field(default=0, ge=0)
    param_only_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    summary_cn: str | None = None


class ClaimHitQuery(Core3BaseClaimBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str | None = None
    claim_codes: list[str] = Field(default_factory=list)
    hit_source_types: list[ClaimHitSourceType] = Field(default_factory=list)
    match_methods: list[ClaimMatchMethod] = Field(default_factory=list)
    review_required: bool | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @field_validator("claim_codes")
    @classmethod
    def validate_claim_codes(cls, claim_codes: list[str]) -> list[str]:
        return _validate_non_empty_strings(claim_codes, "claim_codes")


class ClaimSourceStatusQuery(Core3BaseClaimBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_codes: list[str] = Field(default_factory=list)
    statuses: list[ClaimSourceStatus] = Field(default_factory=list)
    review_required: bool | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @field_validator("sku_codes")
    @classmethod
    def validate_sku_codes(cls, sku_codes: list[str]) -> list[str]:
        return _validate_non_empty_strings(sku_codes, "sku_codes")
