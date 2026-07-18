"""Typed contracts for source-grounded sellpoint-value profile V5.2.

Product sellpoints in this contract must originate from saved M04C claim facts.
Parameters, capabilities, value bundles, and internal value themes cannot
populate source-sellpoint fields.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
    SellpointValueProfileBaseModel,
)


SPV_V5_2_SCHEMA_VERSION = "sku_sellpoint_value_decision_profile_v1_2"
SPV_V5_2_RULE_VERSION = "sellpoint_value_profile_rule_v5_2"
SPV_V5_2_METHOD_VERSION = "sellpoint_value_profile_method_v5_2"


class SellpointClassification(str, Enum):
    CORE_SELLPOINT = "core_sellpoint"
    BASIC_SELLPOINT = "basic_sellpoint"
    USER_UNRECOGNIZED_SELLPOINT = "user_unrecognized_sellpoint"
    PENDING_SELLPOINT = "pending_sellpoint"


class ParameterClassification(str, Enum):
    DIFFERENTIATING_PARAMETER = "differentiating_parameter"
    BASIC_PARAMETER = "basic_parameter"
    PARAMETER_GAP = "parameter_gap"
    NON_KEY_PARAMETER_DIFFERENCE = "non_key_parameter_difference"
    PENDING_PARAMETER = "pending_parameter"


class CompetitorSellpointFindingType(str, Enum):
    SELLPOINT_OPPORTUNITY = "sellpoint_opportunity"
    NON_KEY_COMPETITOR_SELLPOINT = "non_key_competitor_sellpoint"


class SourceSellpointState(str, Enum):
    AVAILABLE = "available"
    NO_SOURCE_SELLPOINT = "no_source_sellpoint"


class SellpointParameterSupportRole(str, Enum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    GENERIC = "generic"


class M04CSourceLineage(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    claim_profile_id: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    evidence_ref: SellpointValueEvidenceRef


class SourceSellpointFact(SellpointValueProfileBaseModel):
    """One source-grounded standard claim under one original claim row."""

    source_claim_key: str = Field(min_length=1)
    claim_fact_id: str = Field(min_length=1)
    merged_claim_fact_ids: list[str] = Field(min_length=1)
    raw_claim_text: str = Field(min_length=1)
    clean_claim_text: str | None = None
    exact_quote_cn: str | None = None
    normalized_claim_code: str = Field(min_length=1)
    normalized_claim_name_cn: str = Field(min_length=1)
    claim_dimension: str = Field(min_length=1)
    claim_kind: str = Field(min_length=1)
    claim_subtype: str = Field(min_length=1)
    param_support_status: str = Field(min_length=1)
    param_support_level: str = Field(min_length=1)
    param_support_specificity: str = Field(min_length=1)
    primary_supporting_param_codes: list[str] = Field(default_factory=list)
    supporting_param_codes: list[str] = Field(default_factory=list)
    generic_support_param_codes: list[str] = Field(default_factory=list)
    service_separate: bool = False
    fact_claim: bool = False
    confidence: Decimal = Field(ge=0, le=1)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_fact(self) -> "SourceSellpointFact":
        raw = self.raw_claim_text.strip()
        if raw != self.raw_claim_text:
            raise ValueError("raw claim text must be stripped")
        if self.clean_claim_text is not None:
            cleaned = self.clean_claim_text.strip()
            if not cleaned:
                raise ValueError("clean claim text cannot be blank")
            if cleaned != self.clean_claim_text:
                raise ValueError("clean claim text must be stripped")
        if self.exact_quote_cn is not None:
            quote = self.exact_quote_cn.strip()
            if not quote or quote != self.exact_quote_cn:
                raise ValueError("exact quote must be non-blank and stripped")
            if quote not in raw:
                raise ValueError("exact quote must be a continuous source substring")
        if self.claim_fact_id not in self.merged_claim_fact_ids:
            raise ValueError("canonical claim fact must be included in merged ids")
        for values in (
            self.merged_claim_fact_ids,
            self.primary_supporting_param_codes,
            self.supporting_param_codes,
            self.generic_support_param_codes,
        ):
            if values != sorted(set(values)):
                raise ValueError("source sellpoint code lists must be sorted and unique")
        return self


class SourceSellpointReadResult(SellpointValueProfileBaseModel):
    status: SourceSellpointState
    lineage: M04CSourceLineage | None = None
    source_sellpoints: list[SourceSellpointFact] = Field(default_factory=list)
    discarded_claim_fact_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_read_result(self) -> "SourceSellpointReadResult":
        if self.status == SourceSellpointState.AVAILABLE:
            if self.lineage is None or not self.source_sellpoints:
                raise ValueError("available source sellpoints require lineage and facts")
        elif self.source_sellpoints:
            raise ValueError("no-source results cannot contain source sellpoints")
        identities = [
            (row.source_claim_key, row.normalized_claim_code)
            for row in self.source_sellpoints
        ]
        if identities != sorted(set(identities)):
            raise ValueError("source sellpoints must be unique and sorted")
        if self.discarded_claim_fact_ids != sorted(
            set(self.discarded_claim_fact_ids)
        ):
            raise ValueError("discarded fact ids must be sorted and unique")
        if self.limitations != sorted(set(self.limitations)):
            raise ValueError("limitations must be sorted and unique")
        return self


class SellpointParameterLink(SellpointValueProfileBaseModel):
    sellpoint_fact_id: str = Field(min_length=1)
    parameter_code: str = Field(min_length=1)
    parameter_name_cn: str = Field(min_length=1)
    normalized_value: str | None = None
    support_role: SellpointParameterSupportRole
    evidence_refs: list[SellpointValueEvidenceRef] = Field(min_length=1)


class SellpointUserValueLink(SellpointValueProfileBaseModel):
    sellpoint_fact_id: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    user_value_cn: str = Field(min_length=1)
    perceived_status: str = Field(min_length=1)
    internal_value_theme_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_internal_themes(self) -> "SellpointUserValueLink":
        if self.internal_value_theme_codes != sorted(
            set(self.internal_value_theme_codes)
        ):
            raise ValueError("internal value themes must be sorted and unique")
        return self


class ProductSellpointAssessment(SellpointValueProfileBaseModel):
    source_claim_key: str = Field(min_length=1)
    normalized_claim_code: str = Field(min_length=1)
    source_sellpoint_fact_ids: list[str] = Field(min_length=1)
    classification: SellpointClassification
    parameter_codes: list[str] = Field(default_factory=list)
    value_bundle_codes: list[str] = Field(default_factory=list)
    user_value_summaries_cn: list[str] = Field(default_factory=list)
    market_result_refs: list[str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    product_action_cn: str = Field(min_length=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "ProductSellpointAssessment":
        for values in (
            self.source_sellpoint_fact_ids,
            self.parameter_codes,
            self.value_bundle_codes,
            self.market_result_refs,
        ):
            if values != sorted(set(values)):
                raise ValueError("sellpoint assessment references must be sorted and unique")
        return self


class ProductParameterAssessment(SellpointValueProfileBaseModel):
    parameter_code: str = Field(min_length=1)
    parameter_name_cn: str = Field(min_length=1)
    normalized_value: str | None = None
    classification: ParameterClassification
    linked_sellpoint_fact_ids: list[str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "ProductParameterAssessment":
        if self.linked_sellpoint_fact_ids != sorted(
            set(self.linked_sellpoint_fact_ids)
        ):
            raise ValueError("linked sellpoint facts must be sorted and unique")
        return self


class CompetitorSellpointFinding(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_sellpoint_fact_id: str = Field(min_length=1)
    normalized_claim_code: str = Field(min_length=1)
    normalized_claim_name_cn: str = Field(min_length=1)
    finding_type: CompetitorSellpointFindingType
    linked_value_bundle_codes: list[str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finding(self) -> "CompetitorSellpointFinding":
        if self.linked_value_bundle_codes != sorted(
            set(self.linked_value_bundle_codes)
        ):
            raise ValueError("competitor value bundle codes must be sorted and unique")
        return self


class LayerIntegritySummary(SellpointValueProfileBaseModel):
    displayed_sellpoint_count: int = Field(ge=0)
    sourced_sellpoint_count: int = Field(ge=0)
    unsourced_sellpoint_count: int = Field(ge=0)
    parameter_as_sellpoint_count: int = Field(ge=0)
    value_theme_as_sellpoint_count: int = Field(ge=0)
    exact_quote_mismatch_count: int = Field(ge=0)
    dangling_sellpoint_link_count: int = Field(ge=0)
    source_profile_hash_mismatch_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "LayerIntegritySummary":
        if self.displayed_sellpoint_count != (
            self.sourced_sellpoint_count + self.unsourced_sellpoint_count
        ):
            raise ValueError("displayed sellpoint count must reconcile to source counts")
        return self


class LayeredSellpointAnalysis(SellpointValueProfileBaseModel):
    schema_version: Literal["sku_sellpoint_value_decision_profile_v1_2"] = (
        SPV_V5_2_SCHEMA_VERSION
    )
    method_version: Literal["sellpoint_value_profile_method_v5_2"] = (
        SPV_V5_2_METHOD_VERSION
    )
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    source_sellpoint_state: SourceSellpointState
    source_lineage: M04CSourceLineage | None = None
    source_sellpoints: list[SourceSellpointFact] = Field(default_factory=list)
    sellpoint_parameter_links: list[SellpointParameterLink] = Field(
        default_factory=list
    )
    sellpoint_user_value_links: list[SellpointUserValueLink] = Field(
        default_factory=list
    )
    sellpoint_assessments: list[ProductSellpointAssessment] = Field(
        default_factory=list
    )
    parameter_assessments: list[ProductParameterAssessment] = Field(
        default_factory=list
    )
    competitor_sellpoint_findings: list[CompetitorSellpointFinding] = Field(
        default_factory=list
    )
    integrity: LayerIntegritySummary
    limitations: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_layered_analysis(self) -> "LayeredSellpointAnalysis":
        if self.source_sellpoint_state == SourceSellpointState.AVAILABLE:
            if self.source_lineage is None or not self.source_sellpoints:
                raise ValueError("available layered analysis requires source sellpoints")
        elif self.source_sellpoints or self.sellpoint_assessments:
            raise ValueError("no-source analysis cannot contain sellpoint assessments")
        if self.limitations != sorted(set(self.limitations)):
            raise ValueError("layered limitations must be sorted and unique")
        return self


__all__ = [
    "CompetitorSellpointFinding",
    "CompetitorSellpointFindingType",
    "LayerIntegritySummary",
    "LayeredSellpointAnalysis",
    "M04CSourceLineage",
    "ParameterClassification",
    "ProductParameterAssessment",
    "ProductSellpointAssessment",
    "SPV_V5_2_METHOD_VERSION",
    "SPV_V5_2_RULE_VERSION",
    "SPV_V5_2_SCHEMA_VERSION",
    "SellpointClassification",
    "SellpointParameterLink",
    "SellpointParameterSupportRole",
    "SellpointUserValueLink",
    "SourceSellpointFact",
    "SourceSellpointReadResult",
    "SourceSellpointState",
]
