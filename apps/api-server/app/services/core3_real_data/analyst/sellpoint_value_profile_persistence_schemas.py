"""Typed persistence contracts for versioned sellpoint-value profiles."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CandidateEligibilityStatus,
    CandidateQuestion,
    InvestmentClassification,
    SellpointValueEvidenceRef,
    SellpointValueProfileBaseModel,
)


SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION = "sku_sellpoint_value_decision_profile_v1"
SELLPOINT_VALUE_PROFILE_RULE_VERSION = "sellpoint_value_profile_materializer_v1"
SELLPOINT_VALUE_PROFILE_METHOD_VERSION = "sellpoint_value_pm_v5_profile_v1"
PROFILE_AUTO_PASS_MIN_CONFIDENCE = Decimal("0.6000")
FORBIDDEN_FACTORY_EXPORT_KEYS = frozenset(
    {
        "prompt",
        "prompt_template",
        "prompt_templates",
        "gold_set",
        "gold_sets",
        "benchmark_gold",
    }
)


class SellpointValueReleaseStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class SellpointValueReleaseQualityStatus(str, Enum):
    UNASSESSED = "unassessed"
    READY = "ready"
    LIMITED = "limited"
    BLOCKED = "blocked"


class SellpointValuePersistenceBaseModel(SellpointValueProfileBaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)

    @model_validator(mode="after")
    def validate_runtime_boundary(self) -> "SellpointValuePersistenceBaseModel":
        _assert_no_factory_only_keys(self.model_dump(mode="python"))
        return self


class SellpointValueVersionDraftCreate(SellpointValuePersistenceBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    profile_version: str = Field(min_length=1)
    schema_version: str = SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION
    rule_version: str = SELLPOINT_VALUE_PROFILE_RULE_VERSION
    method_version: str = SELLPOINT_VALUE_PROFILE_METHOD_VERSION
    method_versions_json: dict[str, str] = Field(default_factory=dict)
    release_status: Literal["draft"] = "draft"
    release_quality_status: SellpointValueReleaseQualityStatus = (
        SellpointValueReleaseQualityStatus.UNASSESSED
    )
    is_current: Literal[False] = False
    generated_by: str = Field(default="system", min_length=1)
    source_batch_ids_json: list[str] = Field(default_factory=list)
    source_scope_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    validation_summary_json: dict[str, Any] = Field(default_factory=dict)
    sku_count: int = Field(default=0, ge=0)
    ready_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    input_fingerprint: str = Field(min_length=1)
    candidate_universe_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = Field(default="success", min_length=1)
    review_required: bool = False
    review_status: str = Field(default="auto_pass", min_length=1)
    review_reason_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scope_and_review(self) -> "SellpointValueVersionDraftCreate":
        if self.category_code != self.product_category:
            raise ValueError("category_code and product_category must match")
        if self.review_required and self.review_status == "auto_pass":
            raise ValueError("review-required versions cannot be auto-pass")
        return self


class SellpointValueVersionRecord(SellpointValuePersistenceBaseModel):
    sellpoint_value_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    profile_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    method_versions_json: dict[str, str] = Field(default_factory=dict)
    release_status: SellpointValueReleaseStatus
    release_quality_status: SellpointValueReleaseQualityStatus
    is_current: bool
    generated_at: datetime
    generated_by: str = Field(min_length=1)
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    published_at: datetime | None = None
    published_by: str | None = None
    deprecated_at: datetime | None = None
    deprecated_by: str | None = None
    release_note_cn: str | None = None
    source_batch_ids_json: list[str] = Field(default_factory=list)
    source_scope_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    validation_summary_json: dict[str, Any] = Field(default_factory=dict)
    sku_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    input_fingerprint: str = Field(min_length=1)
    candidate_universe_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = Field(min_length=1)
    review_required: bool
    review_status: str = Field(min_length=1)
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class SellpointValuePersistedScope(SellpointValuePersistenceBaseModel):
    sellpoint_value_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    profile_version: str = Field(min_length=1)
    schema_version: str = SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION
    rule_version: str = SELLPOINT_VALUE_PROFILE_RULE_VERSION
    method_version: str = SELLPOINT_VALUE_PROFILE_METHOD_VERSION
    release_status: Literal["draft"] = "draft"
    is_current: Literal[False] = False
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = Field(default="success", min_length=1)
    review_required: bool = False
    review_status: str = Field(default="auto_pass", min_length=1)
    review_reason_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_persisted_scope(self) -> "SellpointValuePersistedScope":
        if self.category_code != self.product_category:
            raise ValueError("category_code and product_category must match")
        if self.review_required and self.review_status == "auto_pass":
            raise ValueError("review-required records cannot be auto-pass")
        return self


class SkuSellpointValueProfileDraft(SellpointValuePersistedScope):
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    analysis_state: Literal["ready", "partial", "blocked"]
    freshness_status: Literal["current", "stale", "unknown"] = "unknown"
    profile_confidence: Decimal = Field(ge=0, le=1)
    target_market_summary_json: dict[str, Any] = Field(default_factory=dict)
    source_lineage_json: list[dict[str, Any]] = Field(default_factory=list)
    candidate_universe_summary_json: dict[str, Any] = Field(default_factory=dict)
    threshold_summary_json: dict[str, Any] = Field(default_factory=dict)
    question_analyses_json: list[dict[str, Any]] = Field(default_factory=list)
    investment_decisions_json: list[dict[str, Any]] = Field(default_factory=list)
    price_role_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_options_json: list[dict[str, Any]] = Field(default_factory=list)
    pm_decisions_json: dict[str, Any] = Field(default_factory=dict)
    qa_index_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary_json: dict[str, Any] = Field(default_factory=dict)
    evidence_refs_json: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    limitations_json: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_profile_quality(self) -> "SkuSellpointValueProfileDraft":
        _validate_low_confidence_review(
            self.profile_confidence,
            self.review_required,
            self.review_status,
        )
        if self.analysis_state == "blocked" and not self.review_required:
            raise ValueError("blocked profiles require review")
        return self


class SkuSellpointValueCandidateDraft(SellpointValuePersistedScope):
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    candidate_brand_name: str | None = None
    candidate_model_name: str | None = None
    pool_type: Literal["competitor", "reference"]
    primary_relation_type: str = Field(min_length=1)
    relation_types_json: list[str] = Field(default_factory=list)
    eligibility_status: CandidateEligibilityStatus
    m12_summary_json: dict[str, Any] = Field(default_factory=dict)
    m13_summary_json: dict[str, Any] = Field(default_factory=dict)
    m14_summary_json: dict[str, Any] = Field(default_factory=dict)
    eligible_questions_json: list[CandidateQuestion] = Field(default_factory=list)
    data_availability_json: dict[str, bool] = Field(default_factory=dict)
    market_summary_json: dict[str, Any] = Field(default_factory=dict)
    selected_questions_json: list[CandidateQuestion] = Field(default_factory=list)
    selection_reasons_json: dict[str, str] = Field(default_factory=dict)
    confidence: Decimal = Field(ge=0, le=1)
    evidence_refs_json: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    limitations_json: list[str] = Field(default_factory=list)
    risk_flags_json: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate_quality(self) -> "SkuSellpointValueCandidateDraft":
        _validate_low_confidence_review(
            self.confidence,
            self.review_required,
            self.review_status,
        )
        if self.pool_type == "reference" and not set(
            self.eligible_questions_json
        ).issubset({"parameter_conversion", "battlefield_expansion"}):
            raise ValueError(
                "reference rows can only drive parameter or battlefield questions"
            )
        if not set(self.selected_questions_json).issubset(
            set(self.eligible_questions_json)
        ):
            raise ValueError("selected questions must be eligible")
        return self


class SkuSellpointValueItemDraft(SellpointValuePersistedScope):
    sku_code: str = Field(min_length=1)
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str | None = None
    purchase_reason_code: str | None = None
    purchase_reason_name_cn: str | None = None
    value_bundle_code: str = Field(min_length=1)
    value_bundle_name_cn: str = Field(min_length=1)
    normalized_bundle_code: str = Field(min_length=1)
    perceived_outcome_cn: str = Field(min_length=1)
    perceived_value_status: str = Field(min_length=1)
    capability_codes_json: list[str] = Field(default_factory=list)
    investment_decisions_json: list[dict[str, Any]] = Field(default_factory=list)
    investment_classifications_json: list[InvestmentClassification] = Field(
        default_factory=list
    )
    question_result_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    question_codes_json: list[str] = Field(default_factory=list)
    price_realization_json: dict[str, Any] = Field(default_factory=dict)
    volume_realization_json: dict[str, Any] = Field(default_factory=dict)
    evidence_refs_json: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    evidence_boundary_cn: str = Field(min_length=1)
    limitations_json: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_item_quality(self) -> "SkuSellpointValueItemDraft":
        _validate_low_confidence_review(
            self.confidence,
            self.review_required,
            self.review_status,
        )
        return self


class SkuSellpointValueProfileRecord(SkuSellpointValueProfileDraft):
    sku_sellpoint_value_profile_id: str = Field(min_length=1)
    release_status: SellpointValueReleaseStatus
    is_current: bool
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class SkuSellpointValueProfileProgressRecord(SellpointValuePersistenceBaseModel):
    """Small projection used by batch progress accounting.

    Full profile rows contain multi-megabyte evidence JSON. Batch scheduling only
    needs these three fields and must not hydrate the analytical payload for every
    completed SKU at each checkpoint.
    """

    sku_code: str = Field(min_length=1)
    analysis_state: Literal["ready", "partial", "blocked"]
    review_required: bool


class SkuSellpointValueCandidateRecord(SkuSellpointValueCandidateDraft):
    sku_sellpoint_value_candidate_id: str = Field(min_length=1)
    sku_sellpoint_value_profile_id: str = Field(min_length=1)
    release_status: SellpointValueReleaseStatus
    is_current: bool
    created_at: datetime
    updated_at: datetime


class SkuSellpointValueItemRecord(SkuSellpointValueItemDraft):
    sku_sellpoint_value_item_id: str = Field(min_length=1)
    sku_sellpoint_value_profile_id: str = Field(min_length=1)
    release_status: SellpointValueReleaseStatus
    is_current: bool
    created_at: datetime
    updated_at: datetime


class SellpointValueDraftBundle(SellpointValuePersistenceBaseModel):
    profile: SkuSellpointValueProfileDraft
    candidates: list[SkuSellpointValueCandidateDraft] = Field(default_factory=list)
    value_items: list[SkuSellpointValueItemDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bundle_scope(self) -> "SellpointValueDraftBundle":
        profile = self.profile
        candidate_keys: set[tuple[str, str]] = set()
        for row in self.candidates:
            _validate_child_scope(profile, row, row.target_sku_code)
            key = (row.candidate_sku_code, row.pool_type)
            if key in candidate_keys:
                raise ValueError("candidate rows must be unique by sku and pool type")
            candidate_keys.add(key)
        item_keys: set[tuple[str, str]] = set()
        for row in self.value_items:
            _validate_child_scope(profile, row, row.sku_code)
            key = (row.battlefield_code, row.normalized_bundle_code)
            if key in item_keys:
                raise ValueError("value items must be unique by battlefield and bundle")
            item_keys.add(key)
        return self


class SellpointValueProfileReadBundle(SellpointValuePersistenceBaseModel):
    version: SellpointValueVersionRecord
    profile: SkuSellpointValueProfileRecord
    candidates: list[SkuSellpointValueCandidateRecord]
    value_items: list[SkuSellpointValueItemRecord]


def _validate_child_scope(
    profile: SkuSellpointValueProfileDraft,
    row: SellpointValuePersistedScope,
    target_sku_code: str,
) -> None:
    for field_name in (
        "sellpoint_value_profile_version_id",
        "project_id",
        "category_code",
        "batch_id",
        "product_category",
        "profile_version",
        "schema_version",
        "rule_version",
        "method_version",
        "input_fingerprint",
    ):
        if getattr(profile, field_name) != getattr(row, field_name):
            raise ValueError(f"child {field_name} must match profile")
    if target_sku_code != profile.sku_code:
        raise ValueError("child target SKU must match profile")


def _validate_low_confidence_review(
    confidence: Decimal,
    review_required: bool,
    review_status: str,
) -> None:
    if confidence < PROFILE_AUTO_PASS_MIN_CONFIDENCE and (
        not review_required or review_status == "auto_pass"
    ):
        raise ValueError("low-confidence records must require review")


def _assert_no_factory_only_keys(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_FACTORY_EXPORT_KEYS & {
            str(key).strip().lower() for key in value
        }
        if forbidden:
            raise ValueError(
                f"factory-only keys cannot enter profile persistence: {sorted(forbidden)}"
            )
        for child in value.values():
            _assert_no_factory_only_keys(child)
    elif isinstance(value, list | tuple):
        for child in value:
            _assert_no_factory_only_keys(child)


__all__ = [
    "FORBIDDEN_FACTORY_EXPORT_KEYS",
    "PROFILE_AUTO_PASS_MIN_CONFIDENCE",
    "SELLPOINT_VALUE_PROFILE_METHOD_VERSION",
    "SELLPOINT_VALUE_PROFILE_RULE_VERSION",
    "SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION",
    "SellpointValueDraftBundle",
    "SellpointValueProfileReadBundle",
    "SellpointValueReleaseQualityStatus",
    "SellpointValueReleaseStatus",
    "SellpointValueVersionDraftCreate",
    "SellpointValueVersionRecord",
    "SkuSellpointValueCandidateDraft",
    "SkuSellpointValueCandidateRecord",
    "SkuSellpointValueItemDraft",
    "SkuSellpointValueItemRecord",
    "SkuSellpointValueProfileDraft",
    "SkuSellpointValueProfileProgressRecord",
    "SkuSellpointValueProfileRecord",
]
