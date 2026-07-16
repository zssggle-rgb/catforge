"""Strict V1.1 analytical contracts for competitor-profile persistence.

This module intentionally contains schemas and invariant validation only.  It does
not read upstream modules, calculate competitor relationships, write persistence
rows, or render user-facing answers.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import Field, JsonValue, StrictBool, model_serializer, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
    EvidenceRef,
    QuestionCode,
    RelationCode,
)


COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION = "sku_competitor_decision_profile_v1_1"
COMPETITOR_PROFILE_V1_1_RULE_VERSION = "competitor_profile_materializer_v1_1"
COMPETITOR_PROFILE_V1_1_METHOD_VERSION = "competitor_profile_method_v1_1"
COMPETITOR_PROFILE_V1_1_ADAPTER_VERSION = "competitor_profile_agent_adapter_v1_1"
COMPETITOR_PROFILE_V1_1_SCORE_POLICY_VERSION = "competitor_profile_score_v1_1"
COMPETITOR_PROFILE_V1_1_PREVALENCE_VERSION = (
    "competitor_profile_foundational_prevalence_v1"
)

FOUNDATIONAL_FEATURE_MINIMUM_KNOWN_COUNT = 5
FOUNDATIONAL_FEATURE_PREVALENCE_THRESHOLD = Decimal("0.8000")
HARD_EXCLUSION_CODES = frozenset(
    {
        "self_pair",
        "project_mismatch",
        "category_mismatch",
        "candidate_outside_manifest",
        "identity_decode_failed",
    }
)

PRIMARY_SCORE_DIMENSIONS = (
    "purchase_pool",
    "battlefield_overlap",
    "user_task_overlap",
    "target_group_overlap",
    "value_anchor",
    "replacement_pressure",
)
PRIMARY_DIMENSION_WEIGHTS = {
    "purchase_pool": Decimal("0.20"),
    "battlefield_overlap": Decimal("0.25"),
    "user_task_overlap": Decimal("0.15"),
    "target_group_overlap": Decimal("0.15"),
    "value_anchor": Decimal("0.15"),
    "replacement_pressure": Decimal("0.10"),
}

ALL_RELATION_CODES = tuple(value.value for value in RelationCode)
ALL_QUESTION_CODES = tuple(value.value for value in QuestionCode)
RELATION_REQUIRED_DIMENSIONS = {
    "direct_substitute": ("battlefield_overlap", "purchase_pool"),
    "same_budget_alternative": ("market_validation", "purchase_pool"),
    "downtrade_diversion": ("market_validation", "replacement_pressure"),
    "uptrade_alternative": ("market_validation", "value_anchor"),
    "same_brand_ladder": ("market_validation", "purchase_reason_comparison"),
    "scenario_substitute": ("user_task_overlap", "value_anchor"),
    "same_value_substitute": ("purchase_reason_comparison", "value_anchor"),
}
QUESTION_REQUIRED_DIMENSIONS = {
    "purchase_choice": ("battlefield_overlap", "purchase_pool"),
    "price_volume_pressure": ("market_validation",),
    "value_substitution": ("purchase_reason_comparison", "value_anchor"),
    "configuration_follow": ("claim_comparison", "parameter_comparison"),
    "same_brand_portfolio_role": ("market_validation", "purchase_reason_comparison"),
    "scenario_solution": ("user_task_overlap",),
    "price_ladder_defense": ("market_validation", "replacement_pressure"),
    "key_competitor_selection": (),
}
QUESTION_ALTERNATIVE_EVIDENCE_GROUPS = {
    "configuration_follow": {
        "value_task_or_market": (
            "market_validation",
            "user_task_overlap",
            "value_anchor",
        )
    }
}

JsonObject = dict[str, JsonValue]


class PairScopeStatus(str, Enum):
    ANALYZABLE = "analyzable"
    EXCLUDED = "excluded"


class DimensionAvailability(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class ConclusionStrength(str, Enum):
    STRONG = "strong"
    SUPPORTED = "supported"
    DIRECTIONAL = "directional"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


class ComparisonRole(str, Enum):
    DIRECT_COMPETITOR = "direct_competitor"
    PRICE_ADJACENT = "price_adjacent"
    DOWNTRADE_DIVERSION = "downtrade_diversion"
    UPTRADE_ALTERNATIVE = "uptrade_alternative"
    SAME_BRAND_LADDER = "same_brand_ladder"
    SCENARIO_ALTERNATIVE = "scenario_alternative"
    VALUE_SUBSTITUTE = "value_substitute"
    CONFIGURATION_BENCHMARK = "configuration_benchmark"
    MARKET_REFERENCE = "market_reference"


class FeatureMarketStatus(str, Enum):
    FOUNDATIONAL = "foundational"
    DIFFERENTIATING = "differentiating"
    UNKNOWN = "unknown"


class FactSupportStatus(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ValuePresence(str, Enum):
    KNOWN = "known"
    EXPLICIT_NULL = "explicit_null"
    MISSING = "missing"
    CONFLICT = "conflict"


class ConclusionDirection(str, Enum):
    TARGET_STRONGER = "target_stronger"
    CANDIDATE_STRONGER = "candidate_stronger"
    PARITY = "parity"
    DIFFERENT_ROUTE = "different_route"
    POSITIVE_PRESSURE = "positive_pressure"
    NEGATIVE_PRESSURE = "negative_pressure"
    NO_MATERIAL_EFFECT = "no_material_effect"
    UNKNOWN = "unknown"


class DimensionCode(str, Enum):
    PURCHASE_POOL = "purchase_pool"
    BATTLEFIELD_OVERLAP = "battlefield_overlap"
    USER_TASK_OVERLAP = "user_task_overlap"
    TARGET_GROUP_OVERLAP = "target_group_overlap"
    PARAMETER_COMPARISON = "parameter_comparison"
    CLAIM_COMPARISON = "claim_comparison"
    USER_REALIZATION_COMPARISON = "user_realization_comparison"
    PURCHASE_REASON_COMPARISON = "purchase_reason_comparison"
    VALUE_ANCHOR = "value_anchor"
    REPLACEMENT_PRESSURE = "replacement_pressure"
    MARKET_VALIDATION = "market_validation"


class RelationStatusV11(str, Enum):
    PASSED = "passed"
    LIMITED = "limited"
    UNASSESSABLE = "unassessable"
    FAILED = "failed"


class LegacyValueType(str, Enum):
    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    ARRAY = "array"
    OBJECT = "object"


class CompetitorProfileV11BaseModel(CompetitorProfileBaseModel):
    """V1.1 base model retaining V1 runtime-boundary enforcement."""


class TypedFactValue(CompetitorProfileV11BaseModel):
    presence: ValuePresence
    value: JsonValue = None
    conflicting_values: list[JsonValue] = Field(default_factory=list)
    unit: str | None = None
    tier: str | None = None
    unknown_reason_code: str | None = None
    source_path: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_presence(self) -> "TypedFactValue":
        if self.presence == ValuePresence.KNOWN.value:
            if (
                self.value is None
                or self.conflicting_values
                or self.unknown_reason_code
            ):
                raise ValueError("known values require one non-null value only")
            if isinstance(self.value, str) and self.value.strip() in {"", "-"}:
                raise ValueError("empty-string missing markers cannot be known values")
        elif self.presence == ValuePresence.EXPLICIT_NULL.value:
            if (
                self.value is not None
                or self.conflicting_values
                or self.unknown_reason_code
            ):
                raise ValueError("explicit null must remain distinct from missing")
        elif self.presence == ValuePresence.MISSING.value:
            if (
                self.value is not None
                or self.conflicting_values
                or not self.unknown_reason_code
            ):
                raise ValueError(
                    "missing values require an unknown reason and no value"
                )
        elif self.value is not None or len(self.conflicting_values) < 2:
            raise ValueError(
                "conflicts require at least two values and no resolved value"
            )
        return self


class AnalysisItem(CompetitorProfileV11BaseModel):
    fact_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    values: list[TypedFactValue] = Field(min_length=1)
    support_status: FactSupportStatus = FactSupportStatus.UNKNOWN
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    legacy_payload: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_item(self) -> "AnalysisItem":
        _assert_sorted_unique(self.roles, "analysis item roles")
        return self


class NormalizedSourceOccurrence(CompetitorProfileV11BaseModel):
    occurrence_key: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    raw_value: JsonValue
    typed_value: TypedFactValue


class NormalizedSourceFact(AnalysisItem):
    entity_key: str = Field(min_length=1)
    source_atom: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    normalized_target_path: str = Field(min_length=1)
    source_occurrences: list[NormalizedSourceOccurrence] = Field(min_length=1)
    occurrence_count: int = Field(ge=1)
    source_value_hash: str = Field(min_length=1)
    resolved_value: TypedFactValue | None = None

    @model_validator(mode="after")
    def validate_occurrences(self) -> "NormalizedSourceFact":
        occurrence_keys = [row.occurrence_key for row in self.source_occurrences]
        ordinals = [row.ordinal for row in self.source_occurrences]
        if len(occurrence_keys) != len(set(occurrence_keys)):
            raise ValueError("normalized source occurrence keys must be unique")
        if ordinals != list(range(len(self.source_occurrences))):
            raise ValueError(
                "normalized source occurrence ordinals must preserve order"
            )
        if self.occurrence_count != len(self.source_occurrences):
            raise ValueError("normalized source occurrence count must be lossless")
        if self.values != [row.typed_value for row in self.source_occurrences]:
            raise ValueError("normalized source values must preserve occurrence order")
        for occurrence in self.source_occurrences:
            expected = _typed_fact_projection_from_raw(
                occurrence.raw_value,
                self.source_path,
            )
            actual = occurrence.typed_value
            if (
                actual.presence != expected["presence"]
                or _canonical_json_bytes(actual.value)
                != _canonical_json_bytes(expected.get("value"))
                or actual.conflicting_values
                or actual.unknown_reason_code != expected.get("unknown_reason_code")
                or actual.source_path != self.source_path
            ):
                raise ValueError(
                    "normalized typed values must be derived from raw occurrences"
                )
        hash_payload = [
            {
                "occurrence_key": row.occurrence_key,
                "raw_value": row.raw_value,
            }
            for row in self.source_occurrences
        ]
        expected_hash = hashlib.sha256(_canonical_json_bytes(hash_payload)).hexdigest()
        if self.source_value_hash != expected_hash:
            raise ValueError("normalized source value hash must bind raw occurrences")
        if self.resolved_value is not None:
            distinct_known_values: list[JsonValue] = []
            seen_values: set[bytes] = set()
            for occurrence in self.source_occurrences:
                typed = occurrence.typed_value
                if typed.presence != ValuePresence.KNOWN.value:
                    continue
                key = _canonical_json_bytes(typed.value)
                if key not in seen_values:
                    seen_values.add(key)
                    distinct_known_values.append(typed.value)
            if len(distinct_known_values) > 1:
                expected_presence = ValuePresence.CONFLICT.value
                expected_conflicts = sorted(
                    distinct_known_values,
                    key=_canonical_json_bytes,
                )
                if (
                    self.resolved_value.presence != expected_presence
                    or self.resolved_value.value is not None
                    or self.resolved_value.conflicting_values != expected_conflicts
                ):
                    raise ValueError(
                        "resolved source conflicts must preserve every distinct known value"
                    )
            elif len(distinct_known_values) == 1:
                if (
                    self.resolved_value.presence != ValuePresence.KNOWN.value
                    or _canonical_json_bytes(self.resolved_value.value)
                    != _canonical_json_bytes(distinct_known_values[0])
                ):
                    raise ValueError(
                        "resolved source value must equal the sole distinct known value"
                    )
            elif self.resolved_value != self.source_occurrences[0].typed_value:
                raise ValueError(
                    "resolved unknown source value must preserve the first occurrence"
                )
        return self


class ClaimFactItem(AnalysisItem):
    supporting_parameter_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_parameter_refs(self) -> "ClaimFactItem":
        _assert_sorted_unique(
            self.supporting_parameter_codes,
            "claim supporting parameter codes",
        )
        return self


class ClaimValueFactItem(AnalysisItem):
    value_role: str | None = None
    market_summary: JsonObject = Field(default_factory=dict)
    user_realization: JsonObject = Field(default_factory=dict)


class PurchaseReasonAnchorFact(AnalysisItem):
    anchor_role: str = Field(min_length=1)
    establishment: JsonObject = Field(default_factory=dict)
    user_validation: JsonObject = Field(default_factory=dict)
    purchase_pressure: JsonObject = Field(default_factory=dict)


class ReviewItem(CompetitorProfileV11BaseModel):
    review_code: str = Field(min_length=1)
    dimension_code: DimensionCode | None = None
    reason_cn: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class ConclusionMetric(CompetitorProfileV11BaseModel):
    metric_code: str = Field(min_length=1)
    value: JsonValue
    unit: str | None = None


class MachineReadableConclusion(CompetitorProfileV11BaseModel):
    conclusion_code: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    direction: ConclusionDirection
    metrics: list[ConclusionMetric] = Field(default_factory=list)
    supporting_fact_refs: list[str] = Field(default_factory=list)
    strength: ConclusionStrength
    limitations: list[str] = Field(default_factory=list)
    audit_summary_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_conclusion(self) -> "MachineReadableConclusion":
        _assert_sorted_unique(
            self.supporting_fact_refs,
            "conclusion supporting fact refs",
        )
        if self.strength == ConclusionStrength.UNKNOWN.value:
            if (
                self.supporting_fact_refs
                or self.metrics
                or self.direction != ConclusionDirection.UNKNOWN.value
            ):
                raise ValueError("unknown conclusions cannot claim facts or direction")
            if not self.limitations:
                raise ValueError("unknown conclusions require an explicit limitation")
        elif not self.supporting_fact_refs or not self.metrics:
            raise ValueError(
                "non-unknown conclusions require supporting facts and metrics"
            )
        return self


class DimensionScore(CompetitorProfileV11BaseModel):
    configured_weight: Decimal = Field(ge=0, le=1)
    raw_score: Decimal | None = Field(default=None, ge=0, le=1)
    available_weight: Decimal = Field(ge=0, le=1)
    normalized_score: Decimal | None = Field(default=None, ge=0, le=1)
    weighted_contribution: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_score(self) -> "DimensionScore":
        if self.available_weight == 0:
            if self.raw_score is not None or self.normalized_score is not None:
                raise ValueError("zero available weight cannot carry a score")
            if self.weighted_contribution != 0:
                raise ValueError("unknown dimensions contribute zero, not a fake score")
            return self
        if self.available_weight != self.configured_weight:
            raise ValueError("scored dimensions use their full configured weight")
        if self.raw_score is None or self.normalized_score is None:
            raise ValueError("available dimensions require raw and normalized scores")
        if not _decimal_equal(self.normalized_score, self.raw_score):
            raise ValueError("dimension normalized score must retain the raw 0-1 scale")
        expected = self.raw_score * self.configured_weight
        if not _decimal_equal(self.weighted_contribution, expected):
            raise ValueError("weighted contribution must equal raw score times weight")
        return self


class CalculationComponent(CompetitorProfileV11BaseModel):
    component_code: str = Field(min_length=1)
    known: StrictBool
    input_fact_refs: list[str] = Field(default_factory=list)
    value: Decimal | None = None
    weight: Decimal | None = Field(default=None, ge=0)
    weighted_value: Decimal | None = None
    unknown_reason_code: str | None = None

    @model_validator(mode="after")
    def validate_component(self) -> "CalculationComponent":
        _assert_sorted_unique(self.input_fact_refs, "calculation input fact refs")
        if self.known:
            if self.value is None or self.unknown_reason_code:
                raise ValueError("known calculation components require a value")
            if self.weight is not None:
                expected = self.value * self.weight
                if self.weighted_value is None or not _decimal_equal(
                    self.weighted_value,
                    expected,
                ):
                    raise ValueError("weighted component value is inconsistent")
        elif any(
            value is not None
            for value in (self.value, self.weight, self.weighted_value)
        ):
            raise ValueError(
                "unknown calculation components cannot contain zero-like values"
            )
        elif not self.unknown_reason_code:
            raise ValueError("unknown calculation components require a reason")
        return self


class FeaturePrevalenceContract(CompetitorProfileV11BaseModel):
    config_version: Literal["competitor_profile_foundational_prevalence_v1"] = (
        COMPETITOR_PROFILE_V1_1_PREVALENCE_VERSION
    )
    scope_dimensions: list[
        Literal["category_code", "price_band", "product_form", "size_relation"]
    ]
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    ratio: Decimal | None = Field(default=None, ge=0, le=1)
    minimum_known_count: Literal[5] = FOUNDATIONAL_FEATURE_MINIMUM_KNOWN_COUNT
    prevalence_threshold: Decimal = Field(
        default=FOUNDATIONAL_FEATURE_PREVALENCE_THRESHOLD,
        ge=0,
        le=1,
    )
    feature_market_status: FeatureMarketStatus
    source: str = Field(min_length=1)
    scope_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prevalence(self) -> "FeaturePrevalenceContract":
        required_scope = {
            "category_code",
            "price_band",
            "product_form",
            "size_relation",
        }
        if (
            set(self.scope_dimensions) != required_scope
            or len(self.scope_dimensions) != 4
        ):
            raise ValueError("feature prevalence must lock all four scope dimensions")
        if self.numerator > self.denominator:
            raise ValueError("prevalence numerator cannot exceed denominator")
        if self.prevalence_threshold != FOUNDATIONAL_FEATURE_PREVALENCE_THRESHOLD:
            raise ValueError("V1.1 foundational prevalence threshold is frozen at 80%")
        expected_ratio = (
            Decimal(self.numerator) / Decimal(self.denominator)
            if self.denominator
            else None
        )
        if expected_ratio is None:
            if self.ratio is not None:
                raise ValueError("zero known facts require an unknown prevalence ratio")
        elif self.ratio is None or not _decimal_equal(self.ratio, expected_ratio):
            raise ValueError(
                "prevalence ratio must equal numerator divided by denominator"
            )
        expected_status = _feature_market_status(self.denominator, expected_ratio)
        if self.feature_market_status != expected_status:
            raise ValueError(
                "feature market status conflicts with frozen prevalence rules"
            )
        return self


class FeatureRawDifference(CompetitorProfileV11BaseModel):
    target: TypedFactValue
    candidate: TypedFactValue
    comparison_code: str = Field(min_length=1)


class FeatureAnalysisItem(AnalysisItem):
    prevalence: FeaturePrevalenceContract
    raw_difference: FeatureRawDifference
    contributes_to_differentiation: StrictBool
    ranking_reason_eligible: StrictBool

    @model_validator(mode="after")
    def validate_foundational_behavior(self) -> "FeatureAnalysisItem":
        if (
            self.prevalence.feature_market_status
            == FeatureMarketStatus.FOUNDATIONAL.value
        ):
            if self.contributes_to_differentiation or self.ranking_reason_eligible:
                raise ValueError(
                    "foundational features retain facts but cannot drive differentiation"
                )
        return self


class DimensionAnalysisResult(CompetitorProfileV11BaseModel):
    dimension_code: DimensionCode
    availability: DimensionAvailability
    target_items: list[AnalysisItem] = Field(default_factory=list)
    candidate_items: list[AnalysisItem] = Field(default_factory=list)
    shared_items: list[AnalysisItem] = Field(default_factory=list)
    target_only_items: list[AnalysisItem] = Field(default_factory=list)
    candidate_only_items: list[AnalysisItem] = Field(default_factory=list)
    feature_items: list[FeatureAnalysisItem] = Field(default_factory=list)
    score: DimensionScore
    calculation_components: list[CalculationComponent] = Field(default_factory=list)
    conclusion_strength: ConclusionStrength
    conclusion: MachineReadableConclusion
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    legacy_payload: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dimension(self) -> "DimensionAnalysisResult":
        if self.conclusion_strength != self.conclusion.strength:
            raise ValueError("dimension conclusion strength must match conclusion")
        unavailable = self.availability in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable and self.score.available_weight != 0:
            raise ValueError("unknown or conflict dimensions cannot contribute a score")
        if not unavailable and self.score.available_weight == 0:
            raise ValueError("available or partial dimensions require a scored weight")
        if unavailable and self.conclusion_strength != ConclusionStrength.UNKNOWN.value:
            raise ValueError(
                "unknown or conflict dimensions require an unknown conclusion"
            )
        if self.availability == DimensionAvailability.CONFLICT.value and not (
            self.review_required
        ):
            raise ValueError("conflicting dimensions require a review overlay")
        if self.feature_items and self.dimension_code not in {
            DimensionCode.PARAMETER_COMPARISON.value,
            DimensionCode.CLAIM_COMPARISON.value,
        }:
            raise ValueError(
                "feature items belong only to parameter or claim dimensions"
            )
        if self.review_required and not self.review_items:
            raise ValueError("review-required dimensions require concrete review items")
        return self


class IdentityMarketSnapshot(CompetitorProfileV11BaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    product_category: Literal["TV", "AC"]
    screen_size_inch: Decimal | None = Field(default=None, ge=0)
    size_tier: str | None = None
    price_band_in_size_tier: str | None = None
    weighted_price: Decimal | None = Field(default=None, ge=0)
    avg_weekly_sales_volume: Decimal | None = Field(default=None, ge=0)
    total_sales_volume: Decimal | None = Field(default=None, ge=0)
    total_sales_amount: Decimal | None = Field(default=None, ge=0)
    source: str | None = None
    legacy_payload: JsonObject = Field(default_factory=dict)


class SkuMarketSnapshot(CompetitorProfileV11BaseModel):
    market_window: JsonValue
    weighted_price: Decimal | None = Field(default=None, ge=0)
    avg_weekly_sales_volume: Decimal | None = Field(default=None, ge=0)
    total_sales_volume: Decimal | None = Field(default=None, ge=0)
    total_sales_amount: Decimal | None = Field(default=None, ge=0)
    price_band_in_size_tier: str | None = None
    source: str | None = None
    legacy_payload: JsonObject = Field(default_factory=dict)


class ProductFormFacts(CompetitorProfileV11BaseModel):
    product_category: Literal["TV", "AC"]
    screen_size_inch: Decimal | None = Field(default=None, ge=0)
    size_segment: str | None = None
    ac_product_form: str | None = None
    cooling_capacity_segment: str | None = None
    unknown_reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_category(self) -> "ProductFormFacts":
        if self.product_category == "TV" and (
            self.ac_product_form is not None
            or self.cooling_capacity_segment is not None
        ):
            raise ValueError("TV product-form facts cannot contain AC fields")
        if self.product_category == "AC" and self.screen_size_inch is not None:
            raise ValueError("AC product-form facts cannot contain a TV screen size")
        _assert_sorted_unique(self.unknown_reason_codes, "product-form unknown reasons")
        return self


class FactSectionsSnapshot(CompetitorProfileV11BaseModel):
    parameter_items: list[AnalysisItem] = Field(default_factory=list)
    claim_items: list[ClaimFactItem] = Field(default_factory=list)
    battlefield_items: list[AnalysisItem] = Field(default_factory=list)
    task_items: list[AnalysisItem] = Field(default_factory=list)
    audience_items: list[AnalysisItem] = Field(default_factory=list)
    claim_value_items: list[ClaimValueFactItem] = Field(default_factory=list)
    purchase_reason_anchors: list[PurchaseReasonAnchorFact] = Field(
        default_factory=list
    )
    evidence_sources: list[JsonObject] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    sections: JsonObject = Field(default_factory=dict)
    sku: JsonObject = Field(default_factory=dict)
    legacy_payload: JsonObject = Field(default_factory=dict)


class ClaimMarketPosition(CompetitorProfileV11BaseModel):
    type: str = Field(min_length=1)
    summary_cn: str = Field(min_length=1)


class SkuExcessExplanationRecord(CompetitorProfileV11BaseModel):
    contribution_share_in_sku: Decimal | None = None
    sku_excess_price_explained_abs: Decimal | None = None
    sku_excess_weekly_sales_explained_abs: Decimal | None = None
    sku_excess_weekly_sales_amount_explained_abs: Decimal | None = None


class ClaimValueRecord(CompetitorProfileV11BaseModel):
    claim_code: str = Field(min_length=1)
    claim_name: str | None = None
    sku_code: str | None = None
    brand_name: str | None = None
    model_name: str | None = None
    claim_dimension: str | None = None
    claim_source_type: str | None = None
    claim_source_type_cn: str | None = None
    claim_value_role: str | None = None
    claim_value_score: Decimal | None = None
    business_claim_type: str | None = None
    business_claim_type_cn: str | None = None
    business_claim_type_definition_cn: str | None = None
    business_value_label: str | None = None
    business_value_meaning_cn: str | None = None
    context_code: str | None = None
    context_name: str | None = None
    context_type: str | None = None
    target_has_claim: StrictBool | None = None
    attribution_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_id_count: int | None = Field(default=None, ge=0)
    evidence_strength: JsonObject = Field(default_factory=dict)
    supporting_dimensions: JsonObject = Field(default_factory=dict)
    estimated_contribution: JsonObject = Field(default_factory=dict)
    pool_effect: JsonObject = Field(default_factory=dict)
    parameter_competitiveness: JsonObject = Field(default_factory=dict)
    market_position: ClaimMarketPosition | None = None
    sku_excess_explanation: SkuExcessExplanationRecord | None = None
    sku_excess_price_explained_abs: Decimal | None = None
    sku_excess_weekly_sales_explained_abs: Decimal | None = None
    price_band_group: str | None = None
    size_tier: str | None = None
    scorecard: JsonObject = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    reason_cn: str | None = None
    raw_details: JsonObject = Field(default_factory=dict)


class ClaimContributionRecord(CompetitorProfileV11BaseModel):
    claim_code: str = Field(min_length=1)
    claim_name: str | None = None
    sku_code: str | None = None
    brand_name: str | None = None
    model_name: str | None = None
    claim_value_role: str | None = None
    claim_value_score: Decimal | None = None
    business_claim_type: str | None = None
    business_claim_type_cn: str | None = None
    business_claim_type_definition_cn: str | None = None
    business_value_label: str | None = None
    business_value_meaning_cn: str | None = None
    attribution_confidence: Decimal | None = Field(default=None, ge=0, le=1)
    contribution_share_in_sku: Decimal | None = None
    estimated_price_premium_abs: Decimal | None = None
    estimated_weekly_sales_lift_abs: Decimal | None = None
    estimated_weekly_sales_amount_lift_abs: Decimal | None = None
    pool_claim_price_delta_abs: Decimal | None = None
    pool_claim_weekly_sales_delta_abs: Decimal | None = None
    pool_claim_weekly_sales_amount_delta_abs: Decimal | None = None
    market_position: ClaimMarketPosition | None = None
    sku_excess_explanation: SkuExcessExplanationRecord | None = None
    sku_excess_price_explained_abs: Decimal | None = None
    sku_excess_weekly_sales_explained_abs: Decimal | None = None
    reason_cn: str | None = None
    scorecard: JsonObject = Field(default_factory=dict)
    raw_details: JsonObject = Field(default_factory=dict)


class ClaimAttributionRecord(CompetitorProfileV11BaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    price_band_group: str | None = None
    size_tier: str | None = None
    context_code: str = Field(min_length=1)
    context_name: str | None = None
    context_type: str = Field(min_length=1)
    confidence: Decimal = Field(ge=0, le=1)
    baseline: JsonObject = Field(default_factory=dict)
    sku_observed: JsonObject = Field(default_factory=dict)
    sku_gap_vs_baseline: JsonObject = Field(default_factory=dict)
    positive_claims: list[ClaimContributionRecord] = Field(default_factory=list)
    drag_claims: list[ClaimContributionRecord] = Field(default_factory=list)
    opportunity_claims: list[ClaimContributionRecord] = Field(default_factory=list)
    attribution_summary_cn: str | None = None
    raw_details: JsonObject = Field(default_factory=dict)


class SkuLevelClaimValueRecord(CompetitorProfileV11BaseModel):
    claim_code: str = Field(min_length=1)
    claim_name: str | None = None
    claim_value_score: Decimal | None = None
    claim_source_type: str | None = None
    claim_source_type_cn: str | None = None
    business_claim_type: str | None = None
    business_claim_type_cn: str | None = None
    business_claim_type_definition_cn: str | None = None
    business_value_label: str | None = None
    business_value_meaning_cn: str | None = None
    target_has_claim: StrictBool | None = None
    main_contexts: list[str] = Field(default_factory=list)
    context_values: list[JsonObject] = Field(default_factory=list)
    parameter_competitiveness: JsonObject = Field(default_factory=dict)
    sku_level_user_payment_value_abs: Decimal | None = None
    sku_level_weekly_sales_lift_abs: Decimal | None = None
    sku_level_weekly_sales_amount_lift_abs: Decimal | None = None
    market_position: ClaimMarketPosition | None = None
    sku_excess_explanation: SkuExcessExplanationRecord | None = None
    sku_excess_price_explained_abs: Decimal | None = None
    sku_excess_weekly_sales_explained_abs: Decimal | None = None
    evidence_summary_cn: str | None = None
    raw_details: JsonObject = Field(default_factory=dict)


class ClaimValueSnapshot(CompetitorProfileV11BaseModel):
    sku_code: str = Field(min_length=1)
    analysis_population: str = Field(min_length=1)
    market_window: str = Field(min_length=1)
    filters: JsonObject = Field(default_factory=dict)
    role_counts: JsonObject = Field(default_factory=dict)
    attributions: list[ClaimAttributionRecord] = Field(default_factory=list)
    claim_values: list[ClaimValueRecord] = Field(default_factory=list)
    sku_level_claim_values: list[SkuLevelClaimValueRecord] = Field(default_factory=list)
    method_note_cn: str = Field(min_length=1)
    legacy_payload: JsonObject = Field(default_factory=dict)


class ClaimContributionSnapshot(CompetitorProfileV11BaseModel):
    sku_code: str = Field(min_length=1)
    analysis_population: str = Field(min_length=1)
    market_window: str = Field(min_length=1)
    attribution_count: int = Field(ge=0)
    attributions: list[ClaimAttributionRecord] = Field(default_factory=list)
    filters: JsonObject = Field(default_factory=dict)
    method_note_cn: str = Field(min_length=1)
    legacy_payload: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_count(self) -> "ClaimContributionSnapshot":
        if self.attribution_count != len(self.attributions):
            raise ValueError("claim contribution count must match attributions")
        return self


class PurchaseReasonAnchorRecord(CompetitorProfileV11BaseModel):
    anchor_cn: str = Field(min_length=1)
    role: str = Field(min_length=1)
    core_eligible: StrictBool
    establishment_score: Decimal = Field(ge=0)
    establishment_status: str = Field(min_length=1)
    evidence_domains: list[str] = Field(default_factory=list)
    evidence_strength: str = Field(min_length=1)
    user_validation_status: str = Field(min_length=1)
    support_summary_cn: str | None = None
    weakness_summary_cn: str | None = None
    pressure_level: str = Field(min_length=1)
    pressure_summary_cn: str | None = None
    raw_details: JsonObject = Field(default_factory=dict)


class PurchasePressureReasonRecord(CompetitorProfileV11BaseModel):
    anchor_cn: str = Field(min_length=1)
    pressure_level: str = Field(min_length=1)
    pressure_summary_cn: str | None = None
    raw_details: JsonObject = Field(default_factory=dict)


class PurchaseReasonSnapshot(CompetitorProfileV11BaseModel):
    found: StrictBool
    comparison_mode: str = Field(min_length=1)
    consumption_state: str = Field(min_length=1)
    profile_confidence: Decimal = Field(ge=0, le=1)
    anchors: list[PurchaseReasonAnchorRecord] = Field(default_factory=list)
    core_reasons_cn: list[str] = Field(default_factory=list)
    established_reasons_cn: list[str] = Field(default_factory=list)
    proposition_reasons_cn: list[str] = Field(default_factory=list)
    supporting_reasons_cn: list[str] = Field(default_factory=list)
    weak_expression_reasons_cn: list[str] = Field(default_factory=list)
    risk_drag_reasons_cn: list[str] = Field(default_factory=list)
    purchase_pressure_reasons: list[PurchasePressureReasonRecord] = Field(
        default_factory=list
    )
    legacy_payload: JsonObject = Field(default_factory=dict)


class ModuleAvailabilitySnapshot(CompetitorProfileV11BaseModel):
    module_code: str = Field(min_length=1)
    availability: DimensionAvailability
    authority: JsonObject = Field(default_factory=dict)
    source_lineage: JsonObject = Field(default_factory=dict)
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_review(self) -> "ModuleAvailabilitySnapshot":
        if self.review_required and not self.review_items:
            raise ValueError("review-required modules require review items")
        if self.availability == DimensionAvailability.CONFLICT.value and not (
            self.review_required
        ):
            raise ValueError("conflicting modules require a review overlay")
        return self


class VersionSkuAnalysisSnapshot(CompetitorProfileV11BaseModel):
    schema_version: Literal["sku_competitor_decision_profile_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    snapshot_ref: str = Field(min_length=1)
    identity_market: IdentityMarketSnapshot
    product_form_facts: ProductFormFacts
    market_snapshot: SkuMarketSnapshot
    fact_sections: FactSectionsSnapshot
    claim_value_snapshot: ClaimValueSnapshot | None = None
    claim_contribution_snapshot: ClaimContributionSnapshot | None = None
    purchase_reason_snapshot: PurchaseReasonSnapshot | None = None
    semantic_profiles: JsonObject = Field(default_factory=dict)
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    module_availability: list[ModuleAvailabilitySnapshot]
    source_lineage: JsonObject = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "VersionSkuAnalysisSnapshot":
        if self.identity_market.product_category != self.category_code:
            raise ValueError("snapshot identity category must match scope")
        if self.product_form_facts.product_category != self.category_code:
            raise ValueError("snapshot product form category must match scope")
        modules = [row.module_code for row in self.module_availability]
        if modules != sorted(set(modules)):
            raise ValueError("snapshot module availability must be sorted and unique")
        for payload in (self.claim_value_snapshot, self.claim_contribution_snapshot):
            if (
                payload is not None
                and payload.sku_code != self.identity_market.sku_code
            ):
                raise ValueError("snapshot child SKU must match identity")
        return self


class PurchasePoolGateFact(CompetitorProfileV11BaseModel):
    gate_code: str = Field(min_length=1)
    known: StrictBool
    passed: StrictBool | None = None
    facts: JsonObject = Field(default_factory=dict)
    reason_code: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gate(self) -> "PurchasePoolGateFact":
        if self.known == (self.passed is None):
            raise ValueError(
                "known gates require pass/fail; unknown gates require null"
            )
        return self


class PurchasePoolAnalysis(CompetitorProfileV11BaseModel):
    level: Literal["P0", "P1", "P2", "P3", "unknown"]
    gate_facts: list[PurchasePoolGateFact] = Field(min_length=1)
    score: DimensionScore
    conclusion: MachineReadableConclusion
    legacy_payload: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pool(self) -> "PurchasePoolAnalysis":
        codes = [row.gate_code for row in self.gate_facts]
        if codes != sorted(set(codes)):
            raise ValueError("purchase-pool gates must be sorted and unique")
        if self.level == "unknown" and all(row.known for row in self.gate_facts):
            raise ValueError("unknown purchase pool requires at least one unknown gate")
        if (
            self.level == "unknown"
            and self.conclusion.strength != ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError("unknown purchase pool requires an unknown conclusion")
        if self.level == "unknown" and self.score.available_weight != 0:
            raise ValueError("unknown purchase pool cannot contribute a fake score")
        if self.level != "unknown" and self.score.available_weight == 0:
            raise ValueError("known purchase pool requires its scored weight")
        if self.level != "unknown" and (
            self.conclusion.strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError("known purchase pool requires a non-unknown conclusion")
        if self.score.configured_weight != PRIMARY_DIMENSION_WEIGHTS["purchase_pool"]:
            raise ValueError("purchase-pool score must use the frozen 20% weight")
        return self


class ValueAnchorMatchDetail(CompetitorProfileV11BaseModel):
    target_anchor_code: str | None = None
    candidate_anchor_code: str | None = None
    match_type: str = Field(min_length=1)
    score: Decimal = Field(ge=0)
    evidence_comparison: JsonObject = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class PurchasePressureComparisonResult(CompetitorProfileV11BaseModel):
    comparison_allowed: StrictBool
    target_highest_pressure_level: str | None = None
    candidate_highest_pressure_level: str | None = None
    shared_anchor_comparisons: list[JsonObject] = Field(default_factory=list)
    conclusion: MachineReadableConclusion
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    calculator_method_version: str = Field(min_length=1)
    calculator_config_version: str = Field(min_length=1)
    legacy_payload: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_comparison(self) -> "PurchasePressureComparisonResult":
        if not self.comparison_allowed and (
            self.conclusion.strength != ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError(
                "unavailable purchase-pressure comparison must stay unknown"
            )
        if self.comparison_allowed and (
            self.conclusion.strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError(
                "available purchase-pressure comparison needs a conclusion"
            )
        evidence_keys = [
            (
                row.module_code,
                row.source_batch_id or "",
                row.record_type,
                row.record_id,
                row.result_hash,
            )
            for row in self.evidence_refs
        ]
        if evidence_keys != sorted(set(evidence_keys)):
            raise ValueError(
                "purchase-pressure evidence refs must be sorted and unique"
            )
        return self


class ValueAnchorAnalysisResult(CompetitorProfileV11BaseModel):
    target_core_anchors: list[AnalysisItem] = Field(default_factory=list)
    candidate_core_anchors: list[AnalysisItem] = Field(default_factory=list)
    shared_anchors: list[str] = Field(default_factory=list)
    target_stronger_anchors: list[str] = Field(default_factory=list)
    candidate_stronger_anchors: list[str] = Field(default_factory=list)
    weak_expression_anchors: list[str] = Field(default_factory=list)
    proposition_only_anchors: list[str] = Field(default_factory=list)
    purchase_pressure_comparison: PurchasePressureComparisonResult
    match_details: list[ValueAnchorMatchDetail] = Field(default_factory=list)
    anchor_substitutability_score: Decimal | None = Field(default=None, ge=0, le=15)
    anchor_substitutability_level: str = Field(min_length=1)
    score: DimensionScore
    conclusion_strength: ConclusionStrength
    conclusion: MachineReadableConclusion
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    calculator_method_version: str = Field(min_length=1)
    calculator_config_version: str = Field(min_length=1)
    legacy_matcher_payload: JsonObject = Field(default_factory=dict)
    legacy_payload: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_anchor(self) -> "ValueAnchorAnalysisResult":
        if self.conclusion_strength != self.conclusion.strength:
            raise ValueError("value-anchor conclusion strengths must match")
        if self.score.configured_weight != PRIMARY_DIMENSION_WEIGHTS["value_anchor"]:
            raise ValueError("value-anchor score must use the frozen 15% weight")
        if self.anchor_substitutability_score is None:
            if (
                self.score.available_weight != 0
                or (self.conclusion_strength != ConclusionStrength.UNKNOWN.value)
                or self.anchor_substitutability_level != "unknown"
            ):
                raise ValueError(
                    "unknown value-anchor analysis cannot contain a fake zero"
                )
        else:
            normalized = self.anchor_substitutability_score / Decimal("15")
            if self.score.normalized_score is None or not _decimal_equal(
                self.score.normalized_score,
                normalized,
            ):
                raise ValueError(
                    "value-anchor normalized score must use the 15-point scale"
                )
            if (
                self.conclusion_strength == ConclusionStrength.UNKNOWN.value
                or self.anchor_substitutability_level == "unknown"
            ):
                raise ValueError("known value-anchor scores require a known conclusion")
        for values in (
            self.shared_anchors,
            self.target_stronger_anchors,
            self.candidate_stronger_anchors,
            self.weak_expression_anchors,
            self.proposition_only_anchors,
        ):
            _assert_sorted_unique(values, "value-anchor code lists")
        if self.review_required and not self.review_items:
            raise ValueError("review-required value anchors need concrete review items")
        return self


class ReplacementPressureAnalysisResult(CompetitorProfileV11BaseModel):
    primary_pressure_type: str = Field(min_length=1)
    auxiliary_pressure_types: list[str] = Field(default_factory=list)
    pressure_components: list[CalculationComponent] = Field(default_factory=list)
    replacement_pressure_score: Decimal | None = Field(default=None, ge=0, le=10)
    replacement_pressure_level: str = Field(min_length=1)
    affected_purchase_reasons: list[str] = Field(default_factory=list)
    business_effect: JsonObject = Field(default_factory=dict)
    score: DimensionScore
    conclusion_strength: ConclusionStrength
    conclusion: MachineReadableConclusion
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    calculator_method_version: str = Field(min_length=1)
    calculator_config_version: str = Field(min_length=1)
    legacy_payload: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pressure(self) -> "ReplacementPressureAnalysisResult":
        if self.conclusion_strength != self.conclusion.strength:
            raise ValueError("replacement-pressure conclusion strengths must match")
        if (
            self.score.configured_weight
            != PRIMARY_DIMENSION_WEIGHTS["replacement_pressure"]
        ):
            raise ValueError(
                "replacement-pressure score must use the frozen 10% weight"
            )
        if self.replacement_pressure_score is None:
            if (
                self.score.available_weight != 0
                or (self.conclusion_strength != ConclusionStrength.UNKNOWN.value)
                or self.replacement_pressure_level != "unknown"
            ):
                raise ValueError(
                    "unknown replacement-pressure analysis cannot contain a fake zero"
                )
        else:
            normalized = self.replacement_pressure_score / Decimal("10")
            if self.score.normalized_score is None or not _decimal_equal(
                self.score.normalized_score,
                normalized,
            ):
                raise ValueError("replacement pressure must use the 10-point scale")
            if (
                self.conclusion_strength == ConclusionStrength.UNKNOWN.value
                or self.replacement_pressure_level == "unknown"
            ):
                raise ValueError(
                    "known replacement-pressure scores require a known conclusion"
                )
        _assert_sorted_unique(
            self.auxiliary_pressure_types,
            "auxiliary pressure types",
        )
        if self.review_required and not self.review_items:
            raise ValueError(
                "review-required replacement pressure needs concrete review items"
            )
        return self


class SalesOverlapSnapshot(CompetitorProfileV11BaseModel):
    method: str = Field(min_length=1)
    window: JsonValue
    overlap_weeks: list[str] = Field(default_factory=list)
    target_overall_weekly_volume: Decimal | None = Field(default=None, ge=0)
    candidate_overall_weekly_volume: Decimal | None = Field(default=None, ge=0)
    target_overlap_weekly_volume: Decimal | None = Field(default=None, ge=0)
    candidate_overlap_weekly_volume: Decimal | None = Field(default=None, ge=0)
    volume_gap: Decimal | None = None
    volume_ratio: Decimal | None = Field(default=None, ge=0)
    boundary: JsonObject = Field(default_factory=dict)
    legacy_payload: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_sales_overlap(self) -> "SalesOverlapSnapshot":
        _assert_sorted_unique(self.overlap_weeks, "sales overlap weeks")
        if self.target_overlap_weekly_volume in {None, Decimal("0")}:
            if self.volume_ratio is not None:
                raise ValueError("volume ratio requires non-zero target overlap volume")
        return self


class MarketValidationAnalysisResult(CompetitorProfileV11BaseModel):
    sales_overlap_snapshot: SalesOverlapSnapshot
    target_weighted_price: Decimal | None = Field(default=None, ge=0)
    candidate_weighted_price: Decimal | None = Field(default=None, ge=0)
    price_gap: Decimal | None = None
    price_ratio: Decimal | None = Field(default=None, ge=0)
    market_validation_strength: ConclusionStrength
    conclusion: MachineReadableConclusion
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    legacy_summary: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_market(self) -> "MarketValidationAnalysisResult":
        if self.market_validation_strength != self.conclusion.strength:
            raise ValueError("market-validation conclusion strengths must match")
        if (
            self.target_weighted_price in {None, Decimal("0")}
            and self.price_ratio is not None
        ):
            raise ValueError("price ratio requires a non-zero target price")
        return self


class PairDimensionSet(CompetitorProfileV11BaseModel):
    battlefield_overlap: DimensionAnalysisResult
    user_task_overlap: DimensionAnalysisResult
    target_group_overlap: DimensionAnalysisResult
    parameter_comparison: DimensionAnalysisResult
    claim_comparison: DimensionAnalysisResult
    user_realization_comparison: DimensionAnalysisResult
    purchase_reason_comparison: DimensionAnalysisResult
    legacy_semantic_overlap_payload: JsonObject = Field(default_factory=dict)
    legacy_parameter_claim_overlap_payload: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dimensions(self) -> "PairDimensionSet":
        expected = {
            "battlefield_overlap": DimensionCode.BATTLEFIELD_OVERLAP.value,
            "user_task_overlap": DimensionCode.USER_TASK_OVERLAP.value,
            "target_group_overlap": DimensionCode.TARGET_GROUP_OVERLAP.value,
            "parameter_comparison": DimensionCode.PARAMETER_COMPARISON.value,
            "claim_comparison": DimensionCode.CLAIM_COMPARISON.value,
            "user_realization_comparison": (
                DimensionCode.USER_REALIZATION_COMPARISON.value
            ),
            "purchase_reason_comparison": (
                DimensionCode.PURCHASE_REASON_COMPARISON.value
            ),
        }
        for field_name, dimension_code in expected.items():
            if getattr(self, field_name).dimension_code != dimension_code:
                raise ValueError(f"{field_name} carries the wrong dimension code")
        return self


class ScorePolicyComponent(CompetitorProfileV11BaseModel):
    dimension_code: Literal[
        "purchase_pool",
        "battlefield_overlap",
        "user_task_overlap",
        "target_group_overlap",
        "value_anchor",
        "replacement_pressure",
    ]
    weight: Decimal = Field(gt=0, le=1)


class ScorePolicyContract(CompetitorProfileV11BaseModel):
    policy_version: Literal["competitor_profile_score_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCORE_POLICY_VERSION
    )
    components: list[ScorePolicyComponent]
    missing_policy: Literal["exclude_unknown_from_available_weight"] = (
        "exclude_unknown_from_available_weight"
    )
    normalized_formula: Literal["raw_total_div_available_weight"] = (
        "raw_total_div_available_weight"
    )
    ranking_formula: Literal["conclusion_strength_then_normalized_total"] = (
        "conclusion_strength_then_normalized_total"
    )
    coverage_minimum_gate: Literal[None] = None
    market_role: Literal["validation_and_tiebreak_only"] = (
        "validation_and_tiebreak_only"
    )

    @model_validator(mode="after")
    def validate_policy(self) -> "ScorePolicyContract":
        codes = [row.dimension_code for row in self.components]
        if tuple(codes) != PRIMARY_SCORE_DIMENSIONS:
            raise ValueError("score policy must use the frozen six-dimension order")
        actual = {row.dimension_code: row.weight for row in self.components}
        if actual != PRIMARY_DIMENSION_WEIGHTS:
            raise ValueError("score policy weights must match the frozen V1.1 weights")
        if sum(actual.values(), Decimal("0")) != Decimal("1.00"):
            raise ValueError("score policy weights must total one")
        return self


class PairScoreComponent(CompetitorProfileV11BaseModel):
    dimension_code: Literal[
        "purchase_pool",
        "battlefield_overlap",
        "user_task_overlap",
        "target_group_overlap",
        "value_anchor",
        "replacement_pressure",
    ]
    availability: DimensionAvailability
    weight: Decimal = Field(gt=0, le=1)
    raw_score: Decimal | None = Field(default=None, ge=0, le=1)
    weighted_contribution: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_component(self) -> "PairScoreComponent":
        if self.weight != PRIMARY_DIMENSION_WEIGHTS[self.dimension_code]:
            raise ValueError("pair score component uses the wrong frozen weight")
        unavailable = self.availability in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable:
            if self.raw_score is not None or self.weighted_contribution != 0:
                raise ValueError("unknown/conflict score components contribute zero")
        elif self.raw_score is None or not _decimal_equal(
            self.weighted_contribution,
            self.raw_score * self.weight,
        ):
            raise ValueError("pair weighted contribution is inconsistent")
        return self


class PairScoreBreakdown(CompetitorProfileV11BaseModel):
    policy_version: Literal["competitor_profile_score_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCORE_POLICY_VERSION
    )
    components: list[PairScoreComponent]
    raw_total: Decimal = Field(ge=0, le=1)
    available_weight: Decimal = Field(ge=0, le=1)
    normalized_total: Decimal | None = Field(default=None, ge=0, le=1)
    coverage: Decimal = Field(ge=0, le=1)
    ranking_score: Decimal | None = Field(default=None, ge=0, le=1)
    ranking_tiebreakers: list[str]
    legacy_competitor_score: Decimal | None = None
    legacy_business_score: Decimal | None = None
    legacy_payload: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_breakdown(self) -> "PairScoreBreakdown":
        codes = [row.dimension_code for row in self.components]
        if tuple(codes) != PRIMARY_SCORE_DIMENSIONS:
            raise ValueError(
                "pair score breakdown must cover the frozen six dimensions"
            )
        expected_raw = sum(
            (row.weighted_contribution for row in self.components),
            Decimal("0"),
        )
        expected_available = sum(
            (
                row.weight
                for row in self.components
                if row.availability
                not in {
                    DimensionAvailability.UNKNOWN.value,
                    DimensionAvailability.CONFLICT.value,
                }
            ),
            Decimal("0"),
        )
        if not _decimal_equal(self.raw_total, expected_raw):
            raise ValueError("pair raw total must equal weighted contributions")
        if not _decimal_equal(self.available_weight, expected_available):
            raise ValueError("pair available weight is inconsistent")
        if not _decimal_equal(self.coverage, expected_available):
            raise ValueError(
                "coverage equals available weight because weights total one"
            )
        expected_normalized = (
            expected_raw / expected_available if expected_available else None
        )
        if expected_normalized is None:
            if self.normalized_total is not None or self.ranking_score is not None:
                raise ValueError("zero coverage cannot expose a normalized total")
        elif self.normalized_total is None or not _decimal_equal(
            self.normalized_total,
            expected_normalized,
        ):
            raise ValueError("normalized total must divide by available weight")
        if expected_normalized is not None and (
            self.ranking_score is None
            or not _decimal_equal(self.ranking_score, expected_normalized)
        ):
            raise ValueError("ranking score must retain normalized analytical strength")
        if self.ranking_tiebreakers != [
            "market_validation_strength",
            "available_weight",
            "recall_rank",
            "candidate_sku_code",
        ]:
            raise ValueError(
                "ranking tiebreakers must use the frozen deterministic order"
            )
        return self


class QuestionAlternativeEvidenceGroup(CompetitorProfileV11BaseModel):
    group_code: str = Field(min_length=1)
    any_of_dimensions: list[DimensionCode] = Field(min_length=1)
    satisfied_dimensions: list[DimensionCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_group(self) -> "QuestionAlternativeEvidenceGroup":
        any_of = [str(value) for value in self.any_of_dimensions]
        satisfied = [str(value) for value in self.satisfied_dimensions]
        if any_of != sorted(set(any_of)):
            raise ValueError(
                "alternative evidence dimensions must be sorted and unique"
            )
        if satisfied != sorted(set(satisfied)) or not set(satisfied).issubset(any_of):
            raise ValueError(
                "satisfied alternative dimensions must be a sorted any-of subset"
            )
        return self


class PairBusinessQuestionResult(CompetitorProfileV11BaseModel):
    question_code: QuestionCode
    answerable: StrictBool
    conclusion_strength: ConclusionStrength
    conclusion: MachineReadableConclusion
    required_dimensions: list[DimensionCode]
    missing_dimensions: list[DimensionCode] = Field(default_factory=list)
    alternative_evidence_groups: list[QuestionAlternativeEvidenceGroup] = Field(
        default_factory=list
    )
    legacy_payload: JsonObject = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_question(self) -> "PairBusinessQuestionResult":
        if self.conclusion_strength != self.conclusion.strength:
            raise ValueError("question conclusion strengths must match")
        if self.answerable == (
            self.conclusion_strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError("only non-unknown question conclusions are answerable")
        required = [str(value) for value in self.required_dimensions]
        missing = [str(value) for value in self.missing_dimensions]
        expected_required = list(QUESTION_REQUIRED_DIMENSIONS[self.question_code])
        if required != expected_required:
            raise ValueError(
                "question required dimensions must match the frozen contract"
            )
        if required != sorted(set(required)):
            raise ValueError("question required dimensions must be sorted and unique")
        if missing != sorted(set(missing)) or not set(missing).issubset(set(required)):
            raise ValueError(
                "question missing dimensions must be a sorted required subset"
            )
        expected_groups = QUESTION_ALTERNATIVE_EVIDENCE_GROUPS.get(
            self.question_code,
            {},
        )
        actual_group_codes = [
            row.group_code for row in self.alternative_evidence_groups
        ]
        if actual_group_codes != sorted(expected_groups):
            raise ValueError(
                "question alternative evidence groups must match the contract"
            )
        for group in self.alternative_evidence_groups:
            if (
                tuple(str(value) for value in group.any_of_dimensions)
                != expected_groups[group.group_code]
            ):
                raise ValueError("question alternative evidence dimensions are frozen")
        return self


class RelationAssessment(CompetitorProfileV11BaseModel):
    relation_code: RelationCode
    status: RelationStatusV11
    required_dimensions: list[DimensionCode]
    missing_dimensions: list[DimensionCode] = Field(default_factory=list)
    conclusion_strength: ConclusionStrength
    conclusion: MachineReadableConclusion
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    conflict_dimensions: list[DimensionCode] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relation(self) -> "RelationAssessment":
        required = [str(value) for value in self.required_dimensions]
        missing = [str(value) for value in self.missing_dimensions]
        conflicts = [str(value) for value in self.conflict_dimensions]
        if required != list(RELATION_REQUIRED_DIMENSIONS[self.relation_code]):
            raise ValueError(
                "relation required dimensions must match the frozen contract"
            )
        for values, label in (
            (missing, "relation missing dimensions"),
            (conflicts, "relation conflict dimensions"),
        ):
            if values != sorted(set(values)) or not set(values).issubset(set(required)):
                raise ValueError(f"{label} must be a sorted required subset")
        if self.conclusion_strength != self.conclusion.strength:
            raise ValueError("relation conclusion strengths must match")
        if (
            self.status == RelationStatusV11.PASSED.value
            and self.conclusion_strength
            not in {
                ConclusionStrength.STRONG.value,
                ConclusionStrength.SUPPORTED.value,
            }
        ):
            raise ValueError(
                "passed relations require a strong or supported conclusion"
            )
        if self.status == RelationStatusV11.PASSED.value and (missing or conflicts):
            raise ValueError(
                "passed relations cannot omit or conflict on required dimensions"
            )
        if (
            self.status == RelationStatusV11.LIMITED.value
            and self.conclusion_strength
            not in {
                ConclusionStrength.DIRECTIONAL.value,
                ConclusionStrength.REFERENCE.value,
            }
        ):
            raise ValueError(
                "limited relations require a directional/reference conclusion"
            )
        if self.status == RelationStatusV11.LIMITED.value and not (
            missing or conflicts or self.limitations
        ):
            raise ValueError("limited relations require a concrete evidence limitation")
        if self.status == RelationStatusV11.UNASSESSABLE.value and (
            self.conclusion_strength != ConclusionStrength.UNKNOWN.value
            or not (missing or conflicts)
        ):
            raise ValueError(
                "unassessable relations require unknown conclusion and unavailable facts"
            )
        if self.status == RelationStatusV11.FAILED.value and (
            self.conclusion_strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError("failed relations require known contradictory facts")
        if self.review_required and not self.review_items:
            raise ValueError("review-required relations need concrete review items")
        if conflicts and not self.review_required:
            raise ValueError("relation conflicts require a review overlay")
        return self


class PairAnalysisSourceLineage(CompetitorProfileV11BaseModel):
    source_module_versions: dict[str, str] = Field(min_length=1)
    source_result_hashes: dict[str, str] = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    legacy_m12d_consumption: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lineage(self) -> "PairAnalysisSourceLineage":
        if set(self.source_module_versions) != set(self.source_result_hashes):
            raise ValueError("source module versions and result hashes must align")
        return self


class PairAuditSummary(CompetitorProfileV11BaseModel):
    role_cn: str | None = None
    legacy_exclusion_reason_cn: str | None = None
    summary_cn: str = Field(min_length=1)


class LegacyScoreBasis(CompetitorProfileV11BaseModel):
    competitor_score: Decimal | None = Field(default=None, ge=0, le=1)
    semantic_overlap_score: Decimal | None = Field(default=None, ge=0, le=1)
    parameter_claim_overlap_score: Decimal | None = Field(default=None, ge=0, le=1)
    sales_closeness_score: Decimal | None = Field(default=None, ge=0, le=1)
    legacy_payload: JsonObject = Field(default_factory=dict)


class PairDimensionGateSnapshot(CompetitorProfileV11BaseModel):
    """Saved G34 dimension decision without importing the gate module."""

    dimension_code: DimensionCode
    availability: DimensionAvailability
    conclusion_strength: ConclusionStrength
    conclusion_direction: ConclusionDirection
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_gate(self) -> "PairDimensionGateSnapshot":
        unavailable = self.availability in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable != (
            self.conclusion_direction == ConclusionDirection.UNKNOWN.value
        ):
            raise ValueError(
                "unknown/conflict gate availability must align with unknown direction"
            )
        if self.review_required != bool(self.review_items):
            raise ValueError("dimension gate review flag must match review items")
        _assert_sorted_unique(self.limitations, "dimension gate limitations")
        return self


class PairAnalysisProcessSnapshot(CompetitorProfileV11BaseModel):
    """Lossless typed envelope for the already-calculated G33 process."""

    aligned_features: list[JsonObject] = Field(default_factory=list)
    purchase_reason_assessments: list[JsonObject] = Field(default_factory=list)
    value_assessments: list[JsonObject] = Field(default_factory=list)
    price_volume_process: JsonObject = Field(default_factory=dict)
    calculator_versions: dict[str, str] = Field(default_factory=dict)
    assembly_result_hash: str = Field(min_length=1)
    gate_result_hash: str = Field(min_length=1)


class PairSelectionAssessment(CompetitorProfileV11BaseModel):
    """Saved G35 decision for selected and unselected candidates alike."""

    answerable_question_codes: list[QuestionCode] = Field(default_factory=list)
    selection_eligible: StrictBool
    selected: StrictBool
    selection_rank: int | None = Field(default=None, ge=1, le=3)
    selection_reason_code: str = Field(min_length=1)
    selection_reason_cn: str = Field(min_length=1)
    selection_conclusion_strength: ConclusionStrength
    market_validation_strength: ConclusionStrength
    legacy_rank: int | None = Field(default=None, ge=1, le=3)
    legacy_role: str | None = None
    pair_selection_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection(self) -> "PairSelectionAssessment":
        question_codes = [str(value) for value in self.answerable_question_codes]
        if len(question_codes) != len(set(question_codes)):
            raise ValueError("pair selection answerable questions must be unique")
        if self.selection_eligible != bool(self.answerable_question_codes):
            raise ValueError(
                "pair selection eligibility must match answerable questions"
            )
        if self.selection_eligible == (
            self.selection_conclusion_strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError("only non-unknown conclusions may be selection eligible")
        if self.selected != (self.selection_rank is not None):
            raise ValueError("selected pair state must match its selection rank")
        if self.selected and not self.selection_eligible:
            raise ValueError("selected pairs must be selection eligible")
        return self


class LegacyPrioritySelectionDiff(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    legacy_rank: int | None = Field(default=None, ge=1, le=3)
    new_rank: int | None = Field(default=None, ge=1, le=3)
    diff_status: Literal["retained", "added", "dropped"]
    reason_code: str = Field(min_length=1)
    reason_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_diff(self) -> "LegacyPrioritySelectionDiff":
        expected = (
            "retained"
            if self.legacy_rank is not None and self.new_rank is not None
            else "dropped"
            if self.legacy_rank is not None
            else "added"
        )
        if self.diff_status != expected:
            raise ValueError("legacy selection diff status does not match ranks")
        return self


class PairAnalysisSnapshot(CompetitorProfileV11BaseModel):
    schema_version: Literal["sku_competitor_decision_profile_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    competitor_profile_version_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    target_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    scope_status: PairScopeStatus
    exclusion_reason_code: str | None = None
    recall_sources: list[str] = Field(min_length=1)
    recall_facts: JsonObject = Field(default_factory=dict)
    recall_rank: int = Field(ge=1)
    legacy_recall_basis: JsonObject = Field(default_factory=dict)
    legacy_basis: LegacyScoreBasis = Field(default_factory=LegacyScoreBasis)
    dimension_gates: list[PairDimensionGateSnapshot] = Field(default_factory=list)
    purchase_pool: PurchasePoolAnalysis | None = None
    dimensions: PairDimensionSet | None = None
    value_anchor_analysis: ValueAnchorAnalysisResult | None = None
    replacement_pressure_analysis: ReplacementPressureAnalysisResult | None = None
    purchase_pressure_comparison: PurchasePressureComparisonResult | None = None
    market_validation: MarketValidationAnalysisResult | None = None
    comparison_roles: list[ComparisonRole] = Field(default_factory=list)
    primary_role: ComparisonRole | None = None
    legacy_primary_role: str | None = None
    score_breakdown: PairScoreBreakdown | None = None
    analysis_process: PairAnalysisProcessSnapshot | None = None
    selection_assessment: PairSelectionAssessment | None = None
    relation_assessments: list[RelationAssessment] = Field(default_factory=list)
    business_questions: list[PairBusinessQuestionResult] = Field(default_factory=list)
    derived_facts: list[AnalysisItem] = Field(default_factory=list)
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    legacy_dimension_conclusions: JsonObject = Field(default_factory=dict)
    overall_conclusion_strength: ConclusionStrength
    overall_conclusion: MachineReadableConclusion
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    legacy_review_payload: JsonObject = Field(default_factory=dict)
    source_lineage: PairAnalysisSourceLineage
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    audit_summary: PairAuditSummary
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "PairAnalysisSnapshot":
        is_self_pair = self.target_sku_code == self.candidate_sku_code
        if is_self_pair and not (
            self.scope_status == PairScopeStatus.EXCLUDED.value
            and self.exclusion_reason_code == "self_pair"
        ):
            raise ValueError("self pairs must be preserved as a hard exclusion")
        if not is_self_pair and self.exclusion_reason_code == "self_pair":
            raise ValueError(
                "self_pair exclusion requires identical target and candidate"
            )
        _assert_sorted_unique(self.recall_sources, "pair recall sources")
        role_values = [str(value) for value in self.comparison_roles]
        if len(role_values) != len(set(role_values)):
            raise ValueError("comparison roles must be unique")
        if (
            self.primary_role is not None
            and self.primary_role not in self.comparison_roles
        ):
            raise ValueError("primary role must be included in comparison roles")
        gate_codes = [str(value.dimension_code) for value in self.dimension_gates]
        if gate_codes != sorted(set(gate_codes)):
            raise ValueError("pair dimension gates must be sorted and unique")
        analysis_fields = (
            self.purchase_pool,
            self.dimensions,
            self.value_anchor_analysis,
            self.replacement_pressure_analysis,
            self.purchase_pressure_comparison,
            self.market_validation,
            self.score_breakdown,
        )
        if self.scope_status == PairScopeStatus.EXCLUDED.value:
            if self.exclusion_reason_code not in HARD_EXCLUSION_CODES:
                raise ValueError(
                    "excluded pairs require one frozen hard-exclusion code"
                )
            if any(value is not None for value in analysis_fields):
                raise ValueError(
                    "hard-excluded pairs cannot contain fabricated analysis"
                )
            if self.comparison_roles or self.primary_role is not None:
                raise ValueError("hard-excluded pairs cannot carry comparison roles")
            if self.relation_assessments or self.business_questions:
                raise ValueError(
                    "hard-excluded pairs cannot carry analytical assessments"
                )
            if self.derived_facts:
                raise ValueError(
                    "hard-excluded pairs cannot carry derived analysis facts"
                )
            if self.dimension_gates or self.analysis_process is not None:
                raise ValueError(
                    "hard-excluded pairs cannot carry analysis process data"
                )
            if self.overall_conclusion_strength != ConclusionStrength.UNKNOWN.value:
                raise ValueError(
                    "hard-excluded pairs require an unknown overall conclusion"
                )
        else:
            if self.exclusion_reason_code is not None:
                raise ValueError("analyzable pairs cannot carry an exclusion code")
            if any(value is None for value in analysis_fields):
                raise ValueError(
                    "analyzable pairs require the complete analysis contract"
                )
            relation_codes = [row.relation_code for row in self.relation_assessments]
            if tuple(relation_codes) != ALL_RELATION_CODES:
                raise ValueError(
                    "analyzable pairs require all seven relation assessments"
                )
            question_codes = [row.question_code for row in self.business_questions]
            if tuple(question_codes) != ALL_QUESTION_CODES:
                raise ValueError(
                    "analyzable pairs require every frozen business question"
                )
            derived_fact_ids = [row.fact_id for row in self.derived_facts]
            if derived_fact_ids != sorted(set(derived_fact_ids)):
                raise ValueError("pair derived facts must be sorted and unique")
            assert self.purchase_pool is not None
            assert self.dimensions is not None
            assert self.value_anchor_analysis is not None
            assert self.replacement_pressure_analysis is not None
            assert self.market_validation is not None
            assert self.score_breakdown is not None
            _validate_complete_analysis_consistency(
                purchase_pool=self.purchase_pool,
                dimensions=self.dimensions,
                value_anchor_analysis=self.value_anchor_analysis,
                replacement_pressure_analysis=self.replacement_pressure_analysis,
                market_validation=self.market_validation,
                score_breakdown=self.score_breakdown,
                relation_assessments=self.relation_assessments,
                business_questions=self.business_questions,
                dimension_gates=self.dimension_gates,
            )
        if self.selection_assessment is not None:
            if self.selection_assessment.selected and (
                self.scope_status != PairScopeStatus.ANALYZABLE.value
            ):
                raise ValueError("hard-excluded pairs cannot be selected")
            if self.selection_assessment.selection_eligible and (
                self.scope_status != PairScopeStatus.ANALYZABLE.value
            ):
                raise ValueError("hard-excluded pairs cannot be selection eligible")
        if self.overall_conclusion_strength != self.overall_conclusion.strength:
            raise ValueError("overall conclusion strengths must match")
        if self.review_required and not self.review_items:
            raise ValueError(
                "review-required pairs need dimension-specific review items"
            )
        return self


class PriorityCompetitorSelection(CompetitorProfileV11BaseModel):
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    selection_rank: int = Field(ge=1, le=3)
    pair_result_hash: str = Field(min_length=1)
    primary_role: ComparisonRole
    role_codes: list[ComparisonRole] = Field(min_length=1)
    selection_score: Decimal = Field(ge=0, le=1)
    selection_available_weight: Decimal = Field(ge=0, le=1)
    selection_conclusion_strength: ConclusionStrength
    selection_reason_code: str = Field(min_length=1)
    selection_reason_cn: str = Field(min_length=1)
    pair_selection_result_hash: str | None = Field(default=None, min_length=1)
    legacy_payload: JsonObject = Field(default_factory=dict)
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection(self) -> "PriorityCompetitorSelection":
        role_codes = [str(value) for value in self.role_codes]
        if len(role_codes) != len(set(role_codes)):
            raise ValueError("selection roles must be unique")
        if self.primary_role not in self.role_codes:
            raise ValueError("selection roles must include the primary role")
        if self.selection_conclusion_strength == ConclusionStrength.UNKNOWN.value:
            raise ValueError("unknown question results cannot enter priority selection")
        return self


class SummaryFinding(CompetitorProfileV11BaseModel):
    finding_code: str = Field(min_length=1)
    candidate_sku_codes: list[str] = Field(default_factory=list)
    conclusion: MachineReadableConclusion
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidates(self) -> "SummaryFinding":
        _assert_sorted_unique(self.candidate_sku_codes, "summary finding candidates")
        return self


class SkuCompetitionAnalysisSummary(CompetitorProfileV11BaseModel):
    target_sku_code: str = Field(min_length=1)
    analysis_candidate_count: int = Field(ge=0)
    analyzable_candidate_count: int | None = Field(default=None, ge=0)
    excluded_candidate_count: int | None = Field(default=None, ge=0)
    legacy_candidate_count: int = Field(ge=0)
    dimension_availability_counts: dict[str, int]
    conclusion_strength_counts: dict[str, int]
    priority_competitors: list[PriorityCompetitorSelection] = Field(
        default_factory=list
    )
    role_buckets: dict[str, list[str]] = Field(default_factory=dict)
    competitive_advantages: list[SummaryFinding] = Field(default_factory=list)
    substitutable_values: list[SummaryFinding] = Field(default_factory=list)
    configuration_differences: list[SummaryFinding] = Field(default_factory=list)
    price_volume_pressures: list[SummaryFinding] = Field(default_factory=list)
    unknown_dimensions: list[DimensionCode] = Field(default_factory=list)
    review_items: list[ReviewItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    legacy_selection_diffs: list[LegacyPrioritySelectionDiff] = Field(
        default_factory=list
    )
    legacy_payload: JsonObject = Field(default_factory=dict)
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_summary(self) -> "SkuCompetitionAnalysisSummary":
        if len(self.priority_competitors) > 3:
            raise ValueError("summary can contain at most three priority competitors")
        if (self.analyzable_candidate_count is None) != (
            self.excluded_candidate_count is None
        ):
            raise ValueError(
                "summary analyzable and excluded counts must be populated together"
            )
        if self.analyzable_candidate_count is not None and (
            self.analyzable_candidate_count + (self.excluded_candidate_count or 0)
            != self.analysis_candidate_count
        ):
            raise ValueError(
                "summary candidate scope counts must conserve the universe"
            )
        ranks = [row.selection_rank for row in self.priority_competitors]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("priority ranks must be contiguous and ordered")
        codes = [row.candidate_sku_code for row in self.priority_competitors]
        if len(codes) != len(set(codes)):
            raise ValueError("priority competitor codes must be unique")
        if any(value < 0 for value in self.dimension_availability_counts.values()):
            raise ValueError("dimension availability counts cannot be negative")
        if any(value < 0 for value in self.conclusion_strength_counts.values()):
            raise ValueError("conclusion strength counts cannot be negative")
        for role_codes in self.role_buckets.values():
            _assert_sorted_unique(role_codes, "summary role buckets")
        _assert_sorted_unique(
            [str(value) for value in self.unknown_dimensions],
            "summary unknown dimensions",
        )
        diff_codes = [row.candidate_sku_code for row in self.legacy_selection_diffs]
        _assert_sorted_unique(diff_codes, "summary legacy selection diffs")
        return self


class CategoryPerformanceStorageBudget(CompetitorProfileV11BaseModel):
    category_code: Literal["TV", "AC"]
    maximum_candidate_count: int = Field(ge=1)
    maximum_generation_p95_ms: int = Field(ge=1)
    maximum_peak_memory_mib: int = Field(ge=1)
    maximum_serialized_draft_bytes: int = Field(ge=1)


class G29PerformanceStorageBudget(CompetitorProfileV11BaseModel):
    budget_version: Literal["competitor_profile_v1_1_budget_v1"] = (
        "competitor_profile_v1_1_budget_v1"
    )
    categories: list[CategoryPerformanceStorageBudget]
    maximum_compact_readback_ms: Literal[2000] = 2000
    maximum_provider_select_count: Literal[11] = 11
    maximum_target_incremental_select_count: Literal[0] = 0
    share_sku_snapshots: StrictBool = True
    duplicate_complete_sku_payload_per_pair: StrictBool = False
    candidate_truncation_allowed: StrictBool = False
    dimension_dropping_allowed: StrictBool = False

    @model_validator(mode="after")
    def validate_budget(self) -> "G29PerformanceStorageBudget":
        expected = {
            "TV": (377, 60_000, 1_200, 536_870_912),
            "AC": (155, 30_000, 600, 268_435_456),
        }
        actual = {
            row.category_code: (
                row.maximum_candidate_count,
                row.maximum_generation_p95_ms,
                row.maximum_peak_memory_mib,
                row.maximum_serialized_draft_bytes,
            )
            for row in self.categories
        }
        if actual != expected or len(self.categories) != 2:
            raise ValueError("G29 TV/AC performance and storage budgets are frozen")
        if not self.share_sku_snapshots or any(
            (
                self.duplicate_complete_sku_payload_per_pair,
                self.candidate_truncation_allowed,
                self.dimension_dropping_allowed,
            )
        ):
            raise ValueError("G29 storage and no-truncation flags are frozen")
        return self


class ProfileVersionAnalysisContext(CompetitorProfileV11BaseModel):
    competitor_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    source_batch_ids: list[str] = Field(min_length=1)
    market_window: JsonValue
    analysis_population: JsonValue
    schema_version: Literal["sku_competitor_decision_profile_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
    )
    rule_version: Literal["competitor_profile_materializer_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_RULE_VERSION
    )
    method_version: Literal["competitor_profile_method_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_METHOD_VERSION
    )
    score_policy: ScorePolicyContract
    performance_storage_budget: G29PerformanceStorageBudget
    legacy_recall_policy: JsonValue = None
    legacy_audit_summary: JsonObject = Field(default_factory=dict)
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_context(self) -> "ProfileVersionAnalysisContext":
        if self.category_code != self.product_category:
            raise ValueError("profile version category and product category must match")
        _assert_sorted_unique(self.source_batch_ids, "profile source batch IDs")
        return self


class ProfileGenerationReceipt(CompetitorProfileV11BaseModel):
    source_status: str = Field(min_length=1)
    source_atoms: list[JsonValue] = Field(default_factory=list)
    calculation_steps: list[JsonValue] = Field(default_factory=list)
    database_write: StrictBool = False
    external_publish: StrictBool = False
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_no_external_publish(self) -> "ProfileGenerationReceipt":
        if self.external_publish:
            raise ValueError(
                "schema-only generation receipts cannot publish externally"
            )
        return self


class PairIndexItem(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    scope_status: PairScopeStatus
    recall_rank: int = Field(ge=1)
    primary_role: ComparisonRole | None = None
    conclusion_strength: ConclusionStrength
    selected_rank: int | None = Field(default=None, ge=1, le=3)
    pair_result_hash: str = Field(min_length=1)


class FactIndexEntry(CompetitorProfileV11BaseModel):
    fact_id: str = Field(min_length=1)
    fact_code: str = Field(min_length=1)
    evidence_keys: list[str] = Field(default_factory=list)
    source_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_keys(self) -> "FactIndexEntry":
        _assert_sorted_unique(self.evidence_keys, "fact evidence keys")
        return self


class CompetitorProfileAnalysisDTO(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    profile_version: ProfileVersionAnalysisContext
    generation_receipt: ProfileGenerationReceipt
    target_snapshot: VersionSkuAnalysisSnapshot
    candidate_snapshots: list[VersionSkuAnalysisSnapshot]
    sku_summary: SkuCompetitionAnalysisSummary
    priority_selections: list[PriorityCompetitorSelection]
    full_pair_index: list[PairIndexItem]
    pair_analyses: list[PairAnalysisSnapshot]
    fact_index: dict[str, FactIndexEntry]
    evidence_index: dict[str, EvidenceRef]
    profile_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dto(self) -> "CompetitorProfileAnalysisDTO":
        version_id = self.profile_version.competitor_profile_version_id
        if self.target_snapshot.competitor_profile_version_id != version_id:
            raise ValueError("DTO target snapshot must lock the same profile version")
        if (
            self.target_snapshot.project_id != self.profile_version.project_id
            or (
                self.target_snapshot.category_code != self.profile_version.category_code
            )
            or self.target_snapshot.release_scope_key
            != (self.profile_version.release_scope_key)
        ):
            raise ValueError("DTO target snapshot scope must match profile version")
        if (
            self.target_snapshot.identity_market.sku_code
            != self.sku_summary.target_sku_code
        ):
            raise ValueError("DTO target snapshot and summary must use one SKU")
        candidate_snapshot_codes = [
            row.identity_market.sku_code for row in self.candidate_snapshots
        ]
        if candidate_snapshot_codes != sorted(set(candidate_snapshot_codes)):
            raise ValueError("DTO candidate snapshots must be sorted and unique")
        for snapshot in self.candidate_snapshots:
            if snapshot.competitor_profile_version_id != version_id:
                raise ValueError(
                    "DTO candidate snapshots must lock the same profile version"
                )
            if (
                snapshot.project_id != self.profile_version.project_id
                or (snapshot.category_code != self.profile_version.category_code)
                or snapshot.release_scope_key != self.profile_version.release_scope_key
            ):
                raise ValueError(
                    "DTO candidate snapshot scope must match profile version"
                )
        index_codes = [row.candidate_sku_code for row in self.full_pair_index]
        if index_codes != sorted(set(index_codes)):
            raise ValueError("DTO pair index must be sorted and unique")
        pair_codes = [row.candidate_sku_code for row in self.pair_analyses]
        if pair_codes != sorted(set(pair_codes)) or pair_codes != index_codes:
            raise ValueError("DTO pair analyses must exactly cover the pair index")
        if candidate_snapshot_codes != pair_codes:
            raise ValueError("DTO candidate snapshots must exactly cover pair analyses")
        candidate_snapshot_refs = {
            row.identity_market.sku_code: row.snapshot_ref
            for row in self.candidate_snapshots
        }
        for pair in self.pair_analyses:
            if pair.competitor_profile_version_id != version_id:
                raise ValueError("DTO pair analyses must lock the same profile version")
            if pair.project_id != self.profile_version.project_id or (
                pair.category_code != self.profile_version.category_code
            ):
                raise ValueError("DTO pair scope must match profile version")
            if pair.release_scope_key != self.profile_version.release_scope_key or (
                pair.target_sku_code != self.sku_summary.target_sku_code
            ):
                raise ValueError(
                    "DTO pair target and release scope must match the profile"
                )
            if pair.target_snapshot_ref != self.target_snapshot.snapshot_ref or (
                pair.candidate_snapshot_ref
                != candidate_snapshot_refs[pair.candidate_sku_code]
            ):
                raise ValueError(
                    "DTO pair refs must resolve to versioned SKU snapshots"
                )
        if self.sku_summary.analysis_candidate_count != len(self.pair_analyses):
            raise ValueError("DTO summary candidate count must match pair analyses")
        _validate_summary_against_analyses(
            summary=self.sku_summary,
            analyses=self.pair_analyses,
        )
        if self.priority_selections != self.sku_summary.priority_competitors:
            raise ValueError(
                "DTO priority selections must exactly match the saved summary"
            )
        pair_hashes = {
            row.candidate_sku_code: row.result_hash for row in self.pair_analyses
        }
        if any(
            row.pair_result_hash != pair_hashes.get(row.candidate_sku_code)
            for row in self.priority_selections
        ):
            raise ValueError("DTO selections must reference the saved pair result hash")
        pair_by_code = {row.candidate_sku_code: row for row in self.pair_analyses}
        for selection in self.priority_selections:
            pair = pair_by_code[selection.candidate_sku_code]
            if pair.scope_status != PairScopeStatus.ANALYZABLE.value or (
                pair.score_breakdown is None
            ):
                raise ValueError(
                    "DTO priority selections require analyzable scored pairs"
                )
            key_question = next(
                (
                    row
                    for row in pair.business_questions
                    if row.question_code == QuestionCode.KEY_COMPETITOR_SELECTION.value
                ),
                None,
            )
            if key_question is None or not key_question.answerable:
                raise ValueError(
                    "DTO priority selections require an answerable key question"
                )
            assessment = pair.selection_assessment
            expected_score = pair.score_breakdown.ranking_score
            if expected_score is None:
                if pair.score_breakdown.available_weight != 0:
                    raise ValueError(
                        "a null ranking score requires zero available selection weight"
                    )
                expected_score = Decimal("0")
            expected_strength = (
                assessment.selection_conclusion_strength
                if assessment is not None
                else key_question.conclusion_strength
            )
            if (
                not _decimal_equal(
                    selection.selection_score,
                    expected_score,
                )
                or not _decimal_equal(
                    selection.selection_available_weight,
                    pair.score_breakdown.available_weight,
                )
                or selection.selection_conclusion_strength != expected_strength
                or selection.primary_role != pair.primary_role
                or selection.role_codes != pair.comparison_roles
            ):
                raise ValueError(
                    "DTO selection score, coverage, conclusion and roles must match its pair"
                )
            if assessment is not None and (
                not assessment.selected
                or assessment.selection_rank != selection.selection_rank
                or assessment.selection_reason_code != selection.selection_reason_code
                or assessment.selection_reason_cn != selection.selection_reason_cn
                or assessment.pair_selection_result_hash
                != selection.pair_selection_result_hash
            ):
                raise ValueError(
                    "DTO priority selection must match its saved G35 assessment"
                )
        selected_rank_by_code = {
            row.candidate_sku_code: row.selection_rank
            for row in self.priority_selections
        }
        for index_item in self.full_pair_index:
            pair = pair_by_code[index_item.candidate_sku_code]
            expected = (
                pair.scope_status,
                pair.recall_rank,
                pair.primary_role,
                pair.overall_conclusion_strength,
                selected_rank_by_code.get(pair.candidate_sku_code),
                pair.result_hash,
            )
            actual = (
                index_item.scope_status,
                index_item.recall_rank,
                index_item.primary_role,
                index_item.conclusion_strength,
                index_item.selected_rank,
                index_item.pair_result_hash,
            )
            if actual != expected:
                raise ValueError(
                    "DTO compact pair index must match the full pair analysis"
                )
        embedded_sources = (
            self.profile_version,
            self.generation_receipt,
            self.target_snapshot,
            *(
                row
                for row in self.candidate_snapshots
                if row.snapshot_ref != self.target_snapshot.snapshot_ref
            ),
            self.sku_summary,
            *self.priority_selections,
            *self.pair_analyses,
        )
        conclusion_fact_refs = set(
            _collect_typed_list_field_values(
                embedded_sources,
                "supporting_fact_refs",
            )
        )
        saved_fact_ids = {
            str(record["fact_id"])
            for record in _iter_typed_fact_records(embedded_sources)
        }
        if not conclusion_fact_refs.issubset(saved_fact_ids):
            raise ValueError(
                "DTO conclusions must reference facts embedded in the profile"
            )
        _validate_typed_fact_evidence_closure(
            embedded_sources=embedded_sources,
            fact_index=self.fact_index,
            evidence_index=self.evidence_index,
            label="DTO",
        )
        return self


class AgentDimensionGateFact(CompetitorProfileV11BaseModel):
    """Runtime-safe typed form of a materialized dimension-gate derived fact."""

    fact_type: Literal["dimension_gate"] = "dimension_gate"
    fact_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    availability: DimensionAvailability
    conclusion_strength: ConclusionStrength
    conclusion_direction: ConclusionDirection
    support_status: FactSupportStatus = FactSupportStatus.UNKNOWN
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fact(self) -> "AgentDimensionGateFact":
        _assert_sorted_unique(self.roles, "adapter dimension-gate fact roles")
        unavailable = self.availability in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable != (
            self.conclusion_direction == ConclusionDirection.UNKNOWN.value
        ):
            raise ValueError("adapter dimension-gate fact status is inconsistent")
        return self


class AgentPrioritySelectionDiff(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    previous_rank: int | None = Field(default=None, ge=1, le=3)
    current_rank: int | None = Field(default=None, ge=1, le=3)
    diff_status: Literal["retained", "added", "dropped"]
    reason_code: str = Field(min_length=1)
    reason_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_diff(self) -> "AgentPrioritySelectionDiff":
        expected = (
            "retained"
            if self.previous_rank is not None and self.current_rank is not None
            else "dropped"
            if self.previous_rank is not None
            else "added"
        )
        if self.diff_status != expected:
            raise ValueError("adapter priority diff status does not match ranks")
        return self


class AgentCandidateAnalysis(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_result_hash: str = Field(min_length=1)
    candidate_snapshot: VersionSkuAnalysisSnapshot
    identity: IdentityMarketSnapshot
    recall_rank: int = Field(ge=1)
    recall_sources: list[str] = Field(min_length=1)
    purchase_pool: PurchasePoolAnalysis
    dimension_results: PairDimensionSet
    value_anchor_analysis: ValueAnchorAnalysisResult
    replacement_pressure_analysis: ReplacementPressureAnalysisResult
    purchase_pressure_comparison: PurchasePressureComparisonResult
    market_validation: MarketValidationAnalysisResult
    comparison_roles: list[ComparisonRole]
    primary_role: ComparisonRole
    score_breakdown: PairScoreBreakdown
    relation_assessments: list[RelationAssessment]
    business_questions: list[PairBusinessQuestionResult]
    selection_assessment: PairSelectionAssessment
    derived_facts: list[AgentDimensionGateFact] = Field(default_factory=list)
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    overall_conclusion: MachineReadableConclusion
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    pair_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_analysis(self) -> "AgentCandidateAnalysis":
        _assert_sorted_unique(self.recall_sources, "adapter candidate recall sources")
        if (
            self.candidate_snapshot.snapshot_ref != self.candidate_snapshot_ref
            or self.candidate_snapshot.result_hash
            != self.candidate_snapshot_result_hash
            or self.candidate_snapshot.identity_market != self.identity
        ):
            raise ValueError(
                "adapter candidate identity must match its snapshot and hashes"
            )
        if self.primary_role not in self.comparison_roles:
            raise ValueError(
                "adapter candidate primary role must be saved in its roles"
            )
        if self.review_required and not self.review_items:
            raise ValueError("review-required adapter candidates need review items")
        if tuple(row.relation_code for row in self.relation_assessments) != (
            ALL_RELATION_CODES
        ):
            raise ValueError("adapter candidates require all seven saved relations")
        if tuple(row.question_code for row in self.business_questions) != (
            ALL_QUESTION_CODES
        ):
            raise ValueError("adapter candidates require every saved business question")
        _validate_complete_analysis_consistency(
            purchase_pool=self.purchase_pool,
            dimensions=self.dimension_results,
            value_anchor_analysis=self.value_anchor_analysis,
            replacement_pressure_analysis=self.replacement_pressure_analysis,
            market_validation=self.market_validation,
            score_breakdown=self.score_breakdown,
            relation_assessments=self.relation_assessments,
            business_questions=self.business_questions,
        )
        return self


class AgentExcludedCandidateAudit(CompetitorProfileV11BaseModel):
    """Typed audit record for a recalled pair that was hard-excluded before analysis."""

    candidate_sku_code: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_result_hash: str = Field(min_length=1)
    candidate_snapshot: VersionSkuAnalysisSnapshot
    identity: IdentityMarketSnapshot
    recall_rank: int = Field(ge=1)
    recall_sources: list[str] = Field(min_length=1)
    exclusion_reason_code: str = Field(min_length=1)
    selection_assessment: PairSelectionAssessment
    overall_conclusion: MachineReadableConclusion
    source_facts: list[NormalizedSourceFact] = Field(default_factory=list)
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    pair_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exclusion(self) -> "AgentExcludedCandidateAudit":
        if self.identity.sku_code != self.candidate_sku_code:
            raise ValueError(
                "excluded adapter candidate identity must match its SKU code"
            )
        if (
            self.candidate_snapshot.snapshot_ref != self.candidate_snapshot_ref
            or self.candidate_snapshot.result_hash
            != self.candidate_snapshot_result_hash
            or self.candidate_snapshot.identity_market != self.identity
        ):
            raise ValueError(
                "excluded adapter candidate snapshot and hashes must match"
            )
        _assert_sorted_unique(
            self.recall_sources,
            "excluded adapter candidate recall sources",
        )
        if self.exclusion_reason_code not in HARD_EXCLUSION_CODES:
            raise ValueError(
                "excluded adapter candidates require a hard-exclusion code"
            )
        if self.selection_assessment.selection_eligible or (
            self.selection_assessment.selected
        ):
            raise ValueError("excluded adapter candidates cannot be selected")
        if self.overall_conclusion.strength != ConclusionStrength.UNKNOWN.value:
            raise ValueError(
                "excluded adapter candidates require an unknown conclusion"
            )
        if self.review_required and not self.review_items:
            raise ValueError("excluded adapter review requires concrete items")
        return self


class _AdapterProjectionContract(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    adapter_version: Literal["competitor_profile_agent_adapter_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_ADAPTER_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    profile_version: ProfileVersionAnalysisContext
    target_snapshot: VersionSkuAnalysisSnapshot
    sku_competition_summary: SkuCompetitionAnalysisSummary
    candidates: list[AgentCandidateAnalysis]
    excluded_candidates: list[AgentExcludedCandidateAudit] = Field(default_factory=list)
    priority_order: list[str] = Field(max_length=3)
    previous_priority_diffs: list[AgentPrioritySelectionDiff] = Field(
        default_factory=list
    )
    fact_index: dict[str, FactIndexEntry]
    evidence_index: dict[str, EvidenceRef]


class AdapterSourceReceipt(CompetitorProfileV11BaseModel):
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    target_snapshot_result_hash: str = Field(min_length=1)
    summary_result_hash: str = Field(min_length=1)
    candidate_snapshot_result_hashes: dict[str, str] = Field(default_factory=dict)
    candidate_pair_result_hashes: dict[str, str] = Field(default_factory=dict)
    priority_selection_result_hashes: dict[str, str] = Field(default_factory=dict)
    adapter_projection_hash: str = Field(min_length=1)
    receipt_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hash(self) -> "AdapterSourceReceipt":
        for values in (
            self.candidate_snapshot_result_hashes,
            self.candidate_pair_result_hashes,
            self.priority_selection_result_hashes,
        ):
            if list(values) != sorted(values):
                raise ValueError("adapter receipt candidate hashes must be sorted")
        payload = self.model_dump(mode="json", exclude={"receipt_hash"})
        expected = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if self.receipt_hash != expected:
            raise ValueError("adapter source receipt hash is inconsistent")
        return self


class CompetitorProfileAdapterContract(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    adapter_version: Literal["competitor_profile_agent_adapter_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_ADAPTER_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    profile_version: ProfileVersionAnalysisContext
    source_receipt: AdapterSourceReceipt
    target_snapshot: VersionSkuAnalysisSnapshot
    sku_competition_summary: SkuCompetitionAnalysisSummary
    candidates: list[AgentCandidateAnalysis]
    excluded_candidates: list[AgentExcludedCandidateAudit] = Field(default_factory=list)
    priority_order: list[str] = Field(max_length=3)
    previous_priority_diffs: list[AgentPrioritySelectionDiff] = Field(
        default_factory=list
    )
    fact_index: dict[str, FactIndexEntry]
    evidence_index: dict[str, EvidenceRef]

    @classmethod
    def build_from_authoritative_projection(
        cls,
        payload: JsonObject,
    ) -> "CompetitorProfileAdapterContract":
        """Build the only runtime-safe adapter form and its deterministic receipt."""

        if "source_receipt" in payload:
            raise ValueError("adapter builder derives source_receipt")
        _assert_authoritative_adapter_input(payload)
        projection = _AdapterProjectionContract.model_validate(payload)
        projection_payload = _strip_adapter_compatibility_fields(
            projection.model_dump(mode="json")
        )
        projection_hash = hashlib.sha256(
            _canonical_json_bytes(projection_payload)
        ).hexdigest()
        receipt_payload = {
            "competitor_profile_version_id": projection.competitor_profile_version_id,
            "profile_result_hash": projection.profile_result_hash,
            "target_snapshot_result_hash": projection.target_snapshot.result_hash,
            "summary_result_hash": projection.sku_competition_summary.result_hash,
            "candidate_snapshot_result_hashes": {
                row.candidate_sku_code: row.candidate_snapshot_result_hash
                for row in sorted(
                    [*projection.candidates, *projection.excluded_candidates],
                    key=lambda item: item.candidate_sku_code,
                )
            },
            "candidate_pair_result_hashes": {
                row.candidate_sku_code: row.pair_result_hash
                for row in sorted(
                    [*projection.candidates, *projection.excluded_candidates],
                    key=lambda item: item.candidate_sku_code,
                )
            },
            "priority_selection_result_hashes": {
                row.candidate_sku_code: row.result_hash
                for row in sorted(
                    projection.sku_competition_summary.priority_competitors,
                    key=lambda item: item.candidate_sku_code,
                )
            },
            "adapter_projection_hash": projection_hash,
        }
        receipt_payload["receipt_hash"] = hashlib.sha256(
            _canonical_json_bytes(receipt_payload)
        ).hexdigest()
        return cls.model_validate(
            {**projection_payload, "source_receipt": receipt_payload}
        )

    @model_validator(mode="before")
    @classmethod
    def reject_compatibility_payloads(cls, value: Any) -> Any:
        _assert_authoritative_adapter_input(value)
        return value

    @model_validator(mode="after")
    def validate_adapter(self) -> "CompetitorProfileAdapterContract":
        codes = [row.candidate_sku_code for row in self.candidates]
        if codes != sorted(set(codes)):
            raise ValueError("adapter candidates must be sorted and unique")
        excluded_codes = [row.candidate_sku_code for row in self.excluded_candidates]
        if excluded_codes != sorted(set(excluded_codes)):
            raise ValueError("excluded adapter candidates must be sorted and unique")
        if set(codes) & set(excluded_codes):
            raise ValueError(
                "adapter analyzed and excluded candidates must be disjoint"
            )
        expected_priority = [
            row.candidate_sku_code
            for row in self.sku_competition_summary.priority_competitors
        ]
        if self.priority_order != expected_priority:
            raise ValueError("adapter priority order must preserve the saved selection")
        if not set(self.priority_order).issubset(set(codes)):
            raise ValueError(
                "adapter priority candidates must exist in the saved pairs"
            )
        diff_codes = [row.candidate_sku_code for row in self.previous_priority_diffs]
        if diff_codes != sorted(set(diff_codes)) or not set(diff_codes).issubset(
            set(codes) | set(excluded_codes)
        ):
            raise ValueError(
                "adapter previous-priority diffs must resolve to candidates"
            )
        if any(
            row.identity.sku_code != row.candidate_sku_code for row in self.candidates
        ):
            raise ValueError("adapter candidate identity must match its SKU code")
        if self.target_snapshot.competitor_profile_version_id != (
            self.competitor_profile_version_id
        ):
            raise ValueError("adapter must lock one profile version")
        if self.profile_version.competitor_profile_version_id != (
            self.competitor_profile_version_id
        ):
            raise ValueError("adapter profile context must lock the same version")
        if (
            self.target_snapshot.project_id != self.profile_version.project_id
            or self.target_snapshot.category_code != self.profile_version.category_code
            or self.target_snapshot.release_scope_key
            != self.profile_version.release_scope_key
        ):
            raise ValueError("adapter target snapshot scope must match profile context")
        if (
            self.source_receipt.competitor_profile_version_id
            != self.competitor_profile_version_id
            or self.source_receipt.profile_result_hash != self.profile_result_hash
            or self.source_receipt.target_snapshot_result_hash
            != self.target_snapshot.result_hash
            or self.source_receipt.summary_result_hash
            != self.sku_competition_summary.result_hash
            or self.source_receipt.candidate_snapshot_result_hashes
            != {
                row.candidate_sku_code: row.candidate_snapshot_result_hash
                for row in [*self.candidates, *self.excluded_candidates]
            }
            or self.source_receipt.candidate_pair_result_hashes
            != {
                row.candidate_sku_code: row.pair_result_hash
                for row in [*self.candidates, *self.excluded_candidates]
            }
            or self.source_receipt.priority_selection_result_hashes
            != {
                row.candidate_sku_code: row.result_hash
                for row in self.sku_competition_summary.priority_competitors
            }
        ):
            raise ValueError(
                "adapter source receipt must match the consumed profile DTO"
            )
        projection_hash = hashlib.sha256(
            _canonical_json_bytes(_adapter_projection_payload(self))
        ).hexdigest()
        if self.source_receipt.adapter_projection_hash != projection_hash:
            raise ValueError("adapter source receipt must bind the runtime projection")
        if self.target_snapshot.identity_market.sku_code != (
            self.sku_competition_summary.target_sku_code
        ):
            raise ValueError("adapter target snapshot and summary must use one SKU")
        candidates_by_code = {row.candidate_sku_code: row for row in self.candidates}
        _validate_summary_against_analyses(
            summary=self.sku_competition_summary,
            analyses=[*self.candidates, *self.excluded_candidates],
        )
        for selection in self.sku_competition_summary.priority_competitors:
            candidate = candidates_by_code.get(selection.candidate_sku_code)
            if (
                candidate is None
                or candidate.pair_result_hash != selection.pair_result_hash
            ):
                raise ValueError(
                    "adapter selections must resolve to saved candidate pairs"
                )
            key_question = next(
                (
                    row
                    for row in candidate.business_questions
                    if row.question_code == QuestionCode.KEY_COMPETITOR_SELECTION.value
                ),
                None,
            )
            if (
                key_question is None
                or not key_question.answerable
                or not _decimal_equal(
                    selection.selection_score,
                    (
                        candidate.score_breakdown.ranking_score
                        if candidate.score_breakdown.ranking_score is not None
                        else Decimal("0")
                    ),
                )
                or not _decimal_equal(
                    selection.selection_available_weight,
                    candidate.score_breakdown.available_weight,
                )
                or selection.selection_conclusion_strength
                != key_question.conclusion_strength
                or selection.primary_role != candidate.primary_role
                or selection.role_codes != candidate.comparison_roles
            ):
                raise ValueError("adapter selections must preserve saved pair analysis")
        embedded_payload = {
            "profile_version": self.profile_version.model_dump(mode="json"),
            "target_snapshot": self.target_snapshot.model_dump(mode="json"),
            "sku_summary": self.sku_competition_summary.model_dump(mode="json"),
            "candidates": [row.model_dump(mode="json") for row in self.candidates],
            "excluded_candidates": [
                row.model_dump(mode="json") for row in self.excluded_candidates
            ],
        }
        fact_refs = set(
            _collect_list_field_values(embedded_payload, "supporting_fact_refs")
        )
        fact_ids = set(_collect_scalar_field_values(embedded_payload, "fact_id"))
        if not fact_refs.issubset(fact_ids):
            raise ValueError(
                "adapter conclusions must reference embedded profile facts"
            )
        _validate_fact_evidence_closure(
            embedded_payload=embedded_payload,
            fact_index=self.fact_index,
            evidence_index=self.evidence_index,
            label="adapter",
        )
        return self

    @model_serializer(mode="wrap")
    def serialize_authoritative_projection(self, handler: Any) -> JsonObject:
        current_payload = handler(self)
        _assert_authoritative_adapter_runtime_state(current_payload)
        projected = _strip_adapter_compatibility_fields(current_payload)
        receipt = dict(projected["source_receipt"])
        receipt_hash = receipt.pop("receipt_hash")
        if hashlib.sha256(_canonical_json_bytes(receipt)).hexdigest() != receipt_hash:
            raise ValueError("adapter receipt must remain valid at serialization")
        projection_payload = {
            key: child for key, child in projected.items() if key != "source_receipt"
        }
        projection_hash = hashlib.sha256(
            _canonical_json_bytes(projection_payload)
        ).hexdigest()
        if projected["source_receipt"]["adapter_projection_hash"] != projection_hash:
            raise ValueError(
                "adapter receipt must bind the runtime projection at serialization"
            )
        return projected


class LegacyCandidateCompatibilityPayload(CompetitorProfileV11BaseModel):
    rank: int = Field(ge=1)
    basis: JsonObject
    candidate: JsonObject
    candidate_fact_brief: JsonObject
    candidate_claim_value: JsonObject
    candidate_claim_contribution: JsonObject
    target_purchase_reason_profile: JsonObject
    candidate_purchase_reason_profile: JsonObject
    m12d_consumption: JsonObject
    semantic_overlap: JsonObject
    param_claim_overlap: JsonObject
    sales_overlap: JsonObject
    competitor_score: JsonValue
    anchor_substitutability: JsonObject
    value_anchor: JsonObject
    replacement_pressure: JsonObject
    purchase_pressure_comparison: JsonObject


class LegacyAnalyzedPairCompatibilityPayload(LegacyCandidateCompatibilityPayload):
    business_score: JsonValue
    purchase_pool: JsonObject
    weighted_overlap: JsonObject
    matched_dimensions: JsonValue
    shared_business_context: JsonValue
    market_validation: JsonObject
    role: str
    role_cn: str
    selection_gate: JsonObject
    ranking_trace: JsonObject
    top3_eligible: StrictBool
    ranking_gate_reasons: list[JsonValue]
    exclusion_reason_cn: JsonValue


class LegacySnapshotCompatibilityPayload(CompetitorProfileV11BaseModel):
    status: str
    project_id: str
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    batch_id: str
    market_window: JsonValue
    analysis_population: JsonValue
    target: JsonObject
    atoms_used: list[JsonValue]
    sop_steps: list[JsonValue]


class LegacyInputCompatibilityPayload(CompetitorProfileV11BaseModel):
    target_fact_brief: JsonObject
    target_claim_value: JsonObject
    target_claim_contribution: JsonObject
    candidate_count: int = Field(ge=0)
    ranking_policy: JsonValue
    candidates: list[LegacyCandidateCompatibilityPayload]

    @model_validator(mode="after")
    def validate_count(self) -> "LegacyInputCompatibilityPayload":
        if self.candidate_count != len(self.candidates):
            raise ValueError("legacy input candidate count must match candidates")
        return self


class LegacyAnalysisCompatibilityPayload(CompetitorProfileV11BaseModel):
    all_candidates: list[LegacyAnalyzedPairCompatibilityPayload]
    top_competitors: list[LegacyAnalyzedPairCompatibilityPayload]
    candidate_buckets: JsonValue
    selection_policy_cn: list[str]

    @model_validator(mode="after")
    def validate_analysis(self) -> "LegacyAnalysisCompatibilityPayload":
        all_codes = [
            str(row.candidate.get("sku_code") or "") for row in self.all_candidates
        ]
        top_codes = [
            str(row.candidate.get("sku_code") or "") for row in self.top_competitors
        ]
        if not all(all_codes) or len(all_codes) != len(set(all_codes)):
            raise ValueError("legacy analyzed candidates require unique SKU identities")
        if not set(top_codes).issubset(set(all_codes)):
            raise ValueError(
                "legacy top competitors must reference analyzed candidates"
            )
        return self


class LegacyCompetitorAnalysisCompatibilityEnvelope(CompetitorProfileV11BaseModel):
    snapshot: LegacySnapshotCompatibilityPayload
    legacy_input: LegacyInputCompatibilityPayload
    legacy_analysis: LegacyAnalysisCompatibilityPayload

    @model_validator(mode="after")
    def validate_envelope(self) -> "LegacyCompetitorAnalysisCompatibilityEnvelope":
        if self.snapshot.category_code != self.snapshot.product_category:
            raise ValueError("legacy snapshot category and product category must match")
        if self.legacy_input.candidate_count != len(
            self.legacy_analysis.all_candidates
        ):
            raise ValueError("legacy input and analysis candidate counts must match")
        return self


class LegacyTypedFieldContract(CompetitorProfileV11BaseModel):
    source_path: str = Field(min_length=1)
    source_atom: str = Field(min_length=1)
    g28_target_leaf_path: str = Field(min_length=1)
    canonical_typed_path: str = Field(min_length=1)
    target_model: str = Field(min_length=1)
    target_field: str = Field(min_length=1)
    normalized_target_path: str = Field(min_length=1)
    normalized_target_model: str = Field(min_length=1)
    normalized_target_field: str = Field(min_length=1)
    transform_code: Literal[
        "direct_assignment",
        "observed_leaf_to_typed_source_fact",
        "scalar_to_singleton_list",
        "bucket_rows_to_sku_refs",
        "canonical_reference",
    ]
    observed_source_types: list[LegacyValueType] = Field(min_length=1)
    accepted_target_types: list[LegacyValueType] = Field(min_length=1)
    occurrence_count: int = Field(ge=1)
    empty_container_observed: StrictBool
    nullable_observed: StrictBool
    preservation_policy: Literal[
        "typed_field",
        "typed_legacy_subtree",
        "typed_normalization",
        "canonical_pair_reference_no_duplicate",
    ]
    assignment_mode: Literal[
        "direct",
        "normalize_legacy_subtree",
        "scalar_to_singleton_list",
        "bucket_rows_to_sku_refs",
        "canonical_reference",
    ]
    authoritative_for_v11_analysis: StrictBool
    normalized_authoritative_for_v11_analysis: StrictBool
    normalization_required: StrictBool
    missing_policy: Literal["explicit_unknown_never_zero_false_or_empty"] = (
        "explicit_unknown_never_zero_false_or_empty"
    )
    roundtrip_required: StrictBool = True

    @model_validator(mode="after")
    def validate_types(self) -> "LegacyTypedFieldContract":
        if self.assignment_mode == "direct" and not set(
            self.observed_source_types
        ).issubset(set(self.accepted_target_types)):
            raise ValueError("typed target does not accept all observed source types")
        is_direct = (
            self.preservation_policy == "typed_field"
            and self.assignment_mode == "direct"
            and ".legacy" not in self.canonical_typed_path
        )
        if self.authoritative_for_v11_analysis != is_direct:
            raise ValueError(
                "only normalized typed fields are V1.1 analytical authority"
            )
        expected_normalized_authority = self.transform_code != "canonical_reference"
        if self.normalized_authoritative_for_v11_analysis != (
            expected_normalized_authority
        ):
            raise ValueError(
                "every canonical legacy field needs one normalized analytical destination"
            )
        expected_transform = {
            "direct": "direct_assignment",
            "normalize_legacy_subtree": "observed_leaf_to_typed_source_fact",
            "scalar_to_singleton_list": "scalar_to_singleton_list",
            "bucket_rows_to_sku_refs": "bucket_rows_to_sku_refs",
            "canonical_reference": "canonical_reference",
        }[self.assignment_mode]
        if self.transform_code != expected_transform:
            raise ValueError(
                "legacy assignment mode and executable transform must align"
            )
        needs_normalization = self.assignment_mode in {
            "normalize_legacy_subtree",
            "scalar_to_singleton_list",
            "bucket_rows_to_sku_refs",
        }
        if self.normalization_required != needs_normalization:
            raise ValueError(
                "non-direct compatibility fields require typed normalization"
            )
        if not self.roundtrip_required:
            raise ValueError("every frozen G28 field requires lossless roundtrip")
        return self


class LegacyTypedAliasContract(CompetitorProfileV11BaseModel):
    canonical_source_path: str = Field(min_length=1)
    alias_source_paths: list[str] = Field(min_length=1)
    canonical_typed_path: str = Field(min_length=1)
    conflict_policy: Literal["fail_roundtrip"] = "fail_roundtrip"
    duplicate_storage_allowed: StrictBool = False

    @model_validator(mode="after")
    def validate_aliases(self) -> "LegacyTypedAliasContract":
        _assert_sorted_unique(self.alias_source_paths, "legacy alias source paths")
        if self.canonical_source_path in self.alias_source_paths:
            raise ValueError("canonical legacy source cannot also be an alias")
        if self.duplicate_storage_allowed:
            raise ValueError("legacy aliases must resolve to one canonical stored pair")
        return self


class LegacyTypedMappingContract(CompetitorProfileV11BaseModel):
    contract_version: Literal["competitor_profile_v1_1_g29_typed_mapping_v1"] = (
        "competitor_profile_v1_1_g29_typed_mapping_v1"
    )
    source_inventory_hash: str = Field(min_length=1)
    source_fixture_count: int = Field(ge=1)
    observed_path_count: int = Field(ge=1)
    value_leaf_path_count: int = Field(ge=0)
    empty_container_path_count: int = Field(ge=0)
    field_contracts: list[LegacyTypedFieldContract]
    alias_contracts: list[LegacyTypedAliasContract]
    unmapped_path_count: Literal[0] = 0
    typed_schema_complete: StrictBool = True
    known_to_unknown_allowed: StrictBool = False
    selection_membership_policy: Literal[
        "top_list_index_to_rank_and_candidate_to_pair_ref"
    ] = "top_list_index_to_rank_and_candidate_to_pair_ref"
    contract_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_mapping(self) -> "LegacyTypedMappingContract":
        if not self.typed_schema_complete or self.known_to_unknown_allowed:
            raise ValueError(
                "G29 mapping must be complete without known-to-unknown loss"
            )
        if self.observed_path_count != len(self.field_contracts):
            raise ValueError("typed field contracts must cover every observed path")
        source_paths = [row.source_path for row in self.field_contracts]
        if source_paths != sorted(set(source_paths)):
            raise ValueError("typed field contracts must be sorted and unique")
        empty_count = sum(row.empty_container_observed for row in self.field_contracts)
        if self.empty_container_path_count != empty_count:
            raise ValueError("typed mapping empty-container count is inconsistent")
        canonical_sources = [row.canonical_source_path for row in self.alias_contracts]
        if canonical_sources != sorted(set(canonical_sources)):
            raise ValueError("typed alias contracts must be sorted and canonical")
        aliased_sources = [
            source for row in self.alias_contracts for source in row.alias_source_paths
        ]
        if len(aliased_sources) != len(set(aliased_sources)):
            raise ValueError(
                "one legacy source path cannot alias multiple canonical paths"
            )
        hash_payload = self.model_dump(mode="json", exclude={"contract_hash"})
        expected_hash = hashlib.sha256(
            json.dumps(
                hash_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if self.contract_hash != expected_hash:
            raise ValueError("typed mapping contract hash is inconsistent")
        return self


def _validate_summary_against_analyses(
    *,
    summary: SkuCompetitionAnalysisSummary,
    analyses: list[
        PairAnalysisSnapshot | AgentCandidateAnalysis | AgentExcludedCandidateAudit
    ],
) -> None:
    if summary.analysis_candidate_count != len(analyses):
        raise ValueError("summary candidate count must match saved analyses")
    if summary.analyzable_candidate_count is not None:
        analyzable_count = sum(
            (
                row.scope_status == PairScopeStatus.ANALYZABLE.value
                if isinstance(row, PairAnalysisSnapshot)
                else not isinstance(row, AgentExcludedCandidateAudit)
            )
            for row in analyses
        )
        if summary.analyzable_candidate_count != analyzable_count or (
            summary.excluded_candidate_count != len(analyses) - analyzable_count
        ):
            raise ValueError("summary scope counts must match saved analyses")
    candidate_codes: set[str] = set()
    availability_counts: dict[str, int] = {}
    conclusion_counts: dict[str, int] = {}
    role_buckets: dict[str, list[str]] = {}
    availability_by_dimension: dict[str, list[str]] = {
        code: []
        for code in (
            "battlefield_overlap",
            "user_task_overlap",
            "target_group_overlap",
            "parameter_comparison",
            "claim_comparison",
            "user_realization_comparison",
            "purchase_reason_comparison",
        )
    }
    for analysis in analyses:
        candidate_code = analysis.candidate_sku_code
        candidate_codes.add(candidate_code)
        if isinstance(analysis, AgentExcludedCandidateAudit):
            dimensions = None
            conclusion_strength = str(analysis.overall_conclusion.strength)
            roles: list[ComparisonRole] = []
        elif isinstance(analysis, PairAnalysisSnapshot):
            dimensions = analysis.dimensions
            conclusion_strength = str(analysis.overall_conclusion_strength)
            roles = analysis.comparison_roles
        else:
            dimensions = analysis.dimension_results
            conclusion_strength = str(analysis.overall_conclusion.strength)
            roles = analysis.comparison_roles
        conclusion_counts[conclusion_strength] = (
            conclusion_counts.get(conclusion_strength, 0) + 1
        )
        for role in roles:
            role_buckets.setdefault(str(role), []).append(candidate_code)
        if dimensions is None:
            continue
        for dimension_code in availability_by_dimension:
            availability = str(getattr(dimensions, dimension_code).availability)
            availability_counts[availability] = (
                availability_counts.get(availability, 0) + 1
            )
            availability_by_dimension[dimension_code].append(availability)
    expected_role_buckets = {
        role: sorted(set(codes)) for role, codes in sorted(role_buckets.items())
    }
    if summary.dimension_availability_counts != dict(
        sorted(availability_counts.items())
    ):
        raise ValueError(
            "summary dimension availability counts must match pair analyses"
        )
    if summary.conclusion_strength_counts != dict(sorted(conclusion_counts.items())):
        raise ValueError("summary conclusion strength counts must match pair analyses")
    if summary.role_buckets != expected_role_buckets:
        raise ValueError("summary role buckets must exactly match pair roles")
    expected_unknown_dimensions = sorted(
        code
        for code, values in availability_by_dimension.items()
        if values
        and all(
            value
            in {
                DimensionAvailability.UNKNOWN.value,
                DimensionAvailability.CONFLICT.value,
            }
            for value in values
        )
    )
    if [str(value) for value in summary.unknown_dimensions] != (
        expected_unknown_dimensions
    ):
        raise ValueError("summary unknown dimensions must match pair analyses")
    findings = (
        summary.competitive_advantages
        + summary.substitutable_values
        + summary.configuration_differences
        + summary.price_volume_pressures
    )
    if any(
        not set(finding.candidate_sku_codes).issubset(candidate_codes)
        for finding in findings
    ):
        raise ValueError("summary findings must reference saved candidate analyses")


def _validate_complete_analysis_consistency(
    *,
    purchase_pool: PurchasePoolAnalysis,
    dimensions: PairDimensionSet,
    value_anchor_analysis: ValueAnchorAnalysisResult,
    replacement_pressure_analysis: ReplacementPressureAnalysisResult,
    market_validation: MarketValidationAnalysisResult,
    score_breakdown: PairScoreBreakdown,
    relation_assessments: list[RelationAssessment],
    business_questions: list[PairBusinessQuestionResult],
    dimension_gates: list[PairDimensionGateSnapshot] | None = None,
) -> None:
    score_sources = {
        "purchase_pool": (
            DimensionAvailability.UNKNOWN.value
            if purchase_pool.level == "unknown"
            else DimensionAvailability.AVAILABLE.value,
            purchase_pool.score,
        ),
        "battlefield_overlap": (
            dimensions.battlefield_overlap.availability,
            dimensions.battlefield_overlap.score,
        ),
        "user_task_overlap": (
            dimensions.user_task_overlap.availability,
            dimensions.user_task_overlap.score,
        ),
        "target_group_overlap": (
            dimensions.target_group_overlap.availability,
            dimensions.target_group_overlap.score,
        ),
        "value_anchor": (
            DimensionAvailability.UNKNOWN.value
            if value_anchor_analysis.anchor_substitutability_score is None
            else DimensionAvailability.AVAILABLE.value,
            value_anchor_analysis.score,
        ),
        "replacement_pressure": (
            DimensionAvailability.UNKNOWN.value
            if replacement_pressure_analysis.replacement_pressure_score is None
            else DimensionAvailability.AVAILABLE.value,
            replacement_pressure_analysis.score,
        ),
    }
    analysis_availability = {
        "purchase_pool": score_sources["purchase_pool"][0],
        "battlefield_overlap": dimensions.battlefield_overlap.availability,
        "user_task_overlap": dimensions.user_task_overlap.availability,
        "target_group_overlap": dimensions.target_group_overlap.availability,
        "parameter_comparison": dimensions.parameter_comparison.availability,
        "claim_comparison": dimensions.claim_comparison.availability,
        "user_realization_comparison": (
            dimensions.user_realization_comparison.availability
        ),
        "purchase_reason_comparison": (
            dimensions.purchase_reason_comparison.availability
        ),
        "value_anchor": score_sources["value_anchor"][0],
        "replacement_pressure": score_sources["replacement_pressure"][0],
        "market_validation": (
            DimensionAvailability.UNKNOWN.value
            if market_validation.market_validation_strength
            == ConclusionStrength.UNKNOWN.value
            else DimensionAvailability.AVAILABLE.value
        ),
    }
    gate_availability = {
        str(row.dimension_code): str(row.availability)
        for row in (dimension_gates or [])
    }
    analysis_availability.update(gate_availability)
    for component in score_breakdown.components:
        source_availability, source_score = score_sources[component.dimension_code]
        expected_availability = gate_availability.get(
            str(component.dimension_code),
            source_availability,
        )
        if component.availability != expected_availability:
            raise ValueError("pair score availability must match its analysis result")
        unavailable = expected_availability in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable and (
            component.raw_score is not None or component.weighted_contribution != 0
        ):
            raise ValueError(
                "unavailable pair score dimensions cannot fabricate a score"
            )
        if not unavailable and (
            component.raw_score != source_score.normalized_score
            or not _decimal_equal(
                component.weighted_contribution,
                source_score.weighted_contribution,
            )
        ):
            raise ValueError("pair score components must match source analysis scores")
    for relation in relation_assessments:
        required = [str(value) for value in relation.required_dimensions]
        expected_missing = sorted(
            code
            for code in required
            if analysis_availability[code] == DimensionAvailability.UNKNOWN.value
        )
        expected_conflicts = sorted(
            code
            for code in required
            if analysis_availability[code] == DimensionAvailability.CONFLICT.value
        )
        if [str(value) for value in relation.missing_dimensions] != (
            expected_missing
        ) or [str(value) for value in relation.conflict_dimensions] != (
            expected_conflicts
        ):
            raise ValueError(
                "relation missing/conflict dimensions must match pair analyses"
            )
        unavailable_count = len(expected_missing) + len(expected_conflicts)
        required_has_partial = any(
            analysis_availability[code] == DimensionAvailability.PARTIAL.value
            for code in required
        )
        if unavailable_count == len(required) and (
            relation.status != RelationStatusV11.UNASSESSABLE.value
        ):
            raise ValueError("fully unavailable relations must be unassessable")
        if 0 < unavailable_count < len(required) and (
            relation.status != RelationStatusV11.LIMITED.value
        ):
            raise ValueError("partly unavailable relations must be limited")
        if required_has_partial and relation.status == RelationStatusV11.PASSED.value:
            raise ValueError(
                "partial source dimensions cannot produce passed relations"
            )

    questions_by_code = {row.question_code: row for row in business_questions}
    for question in business_questions:
        if question.question_code == QuestionCode.KEY_COMPETITOR_SELECTION.value:
            continue
        required = [str(value) for value in question.required_dimensions]
        expected_missing = sorted(
            code
            for code in required
            if analysis_availability[code]
            in {
                DimensionAvailability.UNKNOWN.value,
                DimensionAvailability.CONFLICT.value,
            }
        )
        if [str(value) for value in question.missing_dimensions] != expected_missing:
            raise ValueError("question missing dimensions must match pair analyses")
        expected_groups = QUESTION_ALTERNATIVE_EVIDENCE_GROUPS.get(
            question.question_code,
            {},
        )
        actual_groups = {
            row.group_code: row for row in question.alternative_evidence_groups
        }
        alternative_ready = True
        for group_code, dimensions_in_group in expected_groups.items():
            expected_satisfied = sorted(
                code
                for code in dimensions_in_group
                if analysis_availability[code]
                in {
                    DimensionAvailability.AVAILABLE.value,
                    DimensionAvailability.PARTIAL.value,
                }
            )
            if [
                str(value) for value in actual_groups[group_code].satisfied_dimensions
            ] != expected_satisfied:
                raise ValueError(
                    "question alternative evidence must match pair analyses"
                )
            alternative_ready = alternative_ready and bool(expected_satisfied)
        minimum_evidence_ready = not expected_missing and alternative_ready
        if question.answerable != minimum_evidence_ready:
            raise ValueError(
                "question answerability must match its frozen minimum evidence"
            )
    decision_questions = [
        row
        for code, row in questions_by_code.items()
        if code != QuestionCode.KEY_COMPETITOR_SELECTION.value and row.answerable
    ]
    key_question = questions_by_code[QuestionCode.KEY_COMPETITOR_SELECTION.value]
    if key_question.answerable != bool(decision_questions):
        raise ValueError(
            "key competitor selection requires one answerable product decision question"
        )
    if decision_questions:
        strength_rank = {
            ConclusionStrength.STRONG.value: 4,
            ConclusionStrength.SUPPORTED.value: 3,
            ConclusionStrength.DIRECTIONAL.value: 2,
            ConclusionStrength.REFERENCE.value: 1,
            ConclusionStrength.UNKNOWN.value: 0,
        }
        expected_strength = max(
            (row.conclusion_strength for row in decision_questions),
            key=lambda value: strength_rank[value],
        )
        if key_question.conclusion_strength != expected_strength:
            raise ValueError(
                "key competitor selection strength must match the strongest decision answer"
            )


def _feature_market_status(
    known_count: int,
    ratio: Decimal | None,
) -> str:
    if known_count < FOUNDATIONAL_FEATURE_MINIMUM_KNOWN_COUNT or ratio is None:
        return FeatureMarketStatus.UNKNOWN.value
    if ratio >= FOUNDATIONAL_FEATURE_PREVALENCE_THRESHOLD:
        return FeatureMarketStatus.FOUNDATIONAL.value
    return FeatureMarketStatus.DIFFERENTIATING.value


def _assert_sorted_unique(values: list[Any], label: str) -> None:
    normalized = [str(value) for value in values]
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{label} must be sorted and unique")


def _decimal_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.000001")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _typed_fact_projection_from_raw(
    raw_value: JsonValue,
    source_path: str,
) -> JsonObject:
    if raw_value is None:
        return {
            "presence": ValuePresence.EXPLICIT_NULL.value,
            "source_path": source_path,
        }
    if isinstance(raw_value, str) and raw_value.strip() in {"", "-"}:
        return {
            "presence": ValuePresence.MISSING.value,
            "unknown_reason_code": "legacy_missing_marker",
            "source_path": source_path,
        }
    return {
        "presence": ValuePresence.KNOWN.value,
        "value": raw_value,
        "source_path": source_path,
    }


_ADAPTER_ALLOWED_LEGACY_COUNT_PATH = (
    "adapter.sku_competition_summary.legacy_candidate_count"
)
_ADAPTER_FREEFORM_FIELD_NAMES = frozenset(
    {
        "authority",
        "baseline",
        "boundary",
        "business_effect",
        "context_values",
        "establishment",
        "estimated_contribution",
        "evidence_comparison",
        "evidence_sources",
        "evidence_strength",
        "facts",
        "filters",
        "market_summary",
        "parameter_competitiveness",
        "pool_effect",
        "purchase_pressure",
        "role_counts",
        "scorecard",
        "sections",
        "semantic_profiles",
        "shared_anchor_comparisons",
        "sku",
        "sku_gap_vs_baseline",
        "sku_observed",
        "source_lineage",
        "supporting_dimensions",
        "user_realization",
        "user_validation",
    }
)
_ADAPTER_SCALAR_JSON_FIELD_NAMES = frozenset(
    {
        "analysis_population",
        "conflicting_values",
        "market_window",
        "raw_value",
        "value",
        "window",
    }
)


def _normalized_adapter_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _adapter_key_is_compatibility_payload(key: str) -> bool:
    normalized = _normalized_adapter_key(key)
    return normalized == "rawdetails" or normalized.startswith("legacy")


def _adapter_value_is_scalar_tree(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_adapter_value_is_scalar_tree(child) for child in value)
    return isinstance(value, dict) and not value


def _is_allowed_legacy_candidate_count(path: str, key: str, value: Any) -> bool:
    full_path = f"{path}.{key}"
    return (
        key == "legacy_candidate_count"
        and full_path == _ADAPTER_ALLOWED_LEGACY_COUNT_PATH
        and isinstance(value, int)
        and not isinstance(value, bool)
    )


def _is_typed_adapter_scalar_field(key: str, value: Any) -> bool:
    return key == "evidence_strength" and isinstance(value, str) and bool(value)


def _assert_authoritative_adapter_input(value: Any, path: str = "adapter") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if _adapter_key_is_compatibility_payload(key_text):
                if _is_allowed_legacy_candidate_count(path, key_text, child):
                    continue
                raise ValueError(
                    f"adapter authoritative whitelist forbids compatibility field {path}.{key_text}"
                )
            if key_text in _ADAPTER_FREEFORM_FIELD_NAMES:
                if _is_typed_adapter_scalar_field(key_text, child):
                    continue
                if child not in (None, {}, []):
                    raise ValueError(
                        f"adapter authoritative whitelist requires typed data at {path}.{key_text}"
                    )
                continue
            if key_text in _ADAPTER_SCALAR_JSON_FIELD_NAMES and not (
                _adapter_value_is_scalar_tree(child)
            ):
                raise ValueError(
                    f"adapter authoritative whitelist requires scalar JSON at {path}.{key_text}"
                )
            _assert_authoritative_adapter_input(child, f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_authoritative_adapter_input(child, f"{path}[{index}]")


def _assert_authoritative_adapter_runtime_state(
    value: Any,
    path: str = "adapter",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if _adapter_key_is_compatibility_payload(key_text):
                if _is_allowed_legacy_candidate_count(path, key_text, child):
                    continue
                if child in (None, {}, []):
                    continue
                raise ValueError(
                    f"adapter runtime state contains compatibility data at {path}.{key_text}"
                )
            if key_text in _ADAPTER_FREEFORM_FIELD_NAMES:
                if _is_typed_adapter_scalar_field(key_text, child):
                    continue
                if child not in (None, {}, []):
                    raise ValueError(
                        f"adapter runtime state contains untyped data at {path}.{key_text}"
                    )
                continue
            if key_text in _ADAPTER_SCALAR_JSON_FIELD_NAMES and not (
                _adapter_value_is_scalar_tree(child)
            ):
                raise ValueError(
                    f"adapter runtime state requires scalar JSON at {path}.{key_text}"
                )
            _assert_authoritative_adapter_runtime_state(
                child,
                f"{path}.{key_text}",
            )
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_authoritative_adapter_runtime_state(
                child,
                f"{path}[{index}]",
            )


def _strip_adapter_compatibility_fields(
    value: Any,
    path: str = "adapter",
) -> Any:
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if _adapter_key_is_compatibility_payload(key_text):
                if _is_allowed_legacy_candidate_count(path, key_text, child):
                    projected[key_text] = child
                continue
            if key_text in _ADAPTER_FREEFORM_FIELD_NAMES:
                if _is_typed_adapter_scalar_field(key_text, child):
                    projected[key_text] = child
                continue
            projected[key_text] = _strip_adapter_compatibility_fields(
                child,
                f"{path}.{key_text}",
            )
        return projected
    if isinstance(value, list):
        return [
            _strip_adapter_compatibility_fields(child, f"{path}[{index}]")
            for index, child in enumerate(value)
        ]
    return value


def _adapter_projection_payload(
    adapter: CompetitorProfileAdapterContract,
) -> JsonObject:
    return _strip_adapter_compatibility_fields(
        {
            "source": adapter.source,
            "adapter_version": adapter.adapter_version,
            "competitor_profile_version_id": adapter.competitor_profile_version_id,
            "profile_result_hash": adapter.profile_result_hash,
            "profile_version": adapter.profile_version.model_dump(mode="json"),
            "target_snapshot": adapter.target_snapshot.model_dump(mode="json"),
            "sku_competition_summary": adapter.sku_competition_summary.model_dump(
                mode="json"
            ),
            "candidates": [row.model_dump(mode="json") for row in adapter.candidates],
            "excluded_candidates": [
                row.model_dump(mode="json") for row in adapter.excluded_candidates
            ],
            "priority_order": adapter.priority_order,
            "previous_priority_diffs": [
                row.model_dump(mode="json") for row in adapter.previous_priority_diffs
            ],
            "fact_index": {
                key: row.model_dump(mode="json")
                for key, row in adapter.fact_index.items()
            },
            "evidence_index": {
                key: row.model_dump(mode="json")
                for key, row in adapter.evidence_index.items()
            },
        }
    )


def _collect_embedded_fact_records(value: JsonValue) -> list[JsonObject]:
    records: list[JsonObject] = []
    if isinstance(value, dict):
        typed_fact = value.get("fact_type") == "dimension_gate" and {
            "fact_id",
            "code",
            "availability",
            "conclusion_strength",
            "conclusion_direction",
        }.issubset(value)
        if typed_fact or (
            {"fact_id", "code", "values"}.issubset(value)
            and isinstance(value["values"], list)
        ):
            records.append(value)
        for child in value.values():
            records.extend(_collect_embedded_fact_records(child))
    elif isinstance(value, list):
        for child in value:
            records.extend(_collect_embedded_fact_records(child))
    return records


def _fact_source_path(record: JsonObject) -> str | None:
    direct = record.get("source_path")
    if isinstance(direct, str) and direct:
        return direct
    value_paths = {
        row.get("source_path")
        for row in record.get("values", [])
        if isinstance(row, dict) and isinstance(row.get("source_path"), str)
    }
    if len(value_paths) == 1:
        return next(iter(value_paths))
    code = record.get("code")
    return f"derived.{code}" if isinstance(code, str) and code else None


def _fact_evidence_payloads(record: JsonObject) -> list[JsonObject]:
    payloads: list[JsonObject] = []
    for row in record.get("evidence_refs", []):
        if isinstance(row, dict):
            payloads.append(row)
    for value in record.get("values", []):
        if not isinstance(value, dict):
            continue
        for row in value.get("evidence_refs", []):
            if isinstance(row, dict):
                payloads.append(row)
    return payloads


def _validate_fact_evidence_closure(
    *,
    embedded_payload: JsonObject,
    fact_index: dict[str, FactIndexEntry],
    evidence_index: dict[str, EvidenceRef],
    label: str,
) -> None:
    records = _collect_embedded_fact_records(embedded_payload)
    fact_ids = [str(row["fact_id"]) for row in records]
    records_by_fact_id: dict[str, list[JsonObject]] = {}
    for record in records:
        records_by_fact_id.setdefault(str(record["fact_id"]), []).append(record)
    if set(fact_ids) != set(fact_index):
        raise ValueError(f"{label} embedded facts must exactly match the fact index")
    evidence_payload_to_keys: dict[bytes, list[str]] = {}
    for key, evidence in evidence_index.items():
        evidence_payload_to_keys.setdefault(
            _canonical_json_bytes(evidence.model_dump(mode="json")),
            [],
        ).append(key)
    for key, entry in fact_index.items():
        if key != entry.fact_id:
            raise ValueError(f"{label} fact-index keys must equal stable fact IDs")
        fact_records = records_by_fact_id[key]
        codes = {str(record["code"]) for record in fact_records}
        paths = {_fact_source_path(record) for record in fact_records}
        if len(codes) != 1 or len(paths) != 1:
            raise ValueError(
                f"{label} embedded fact IDs must be globally unique per fact identity"
            )
        if entry.fact_code != next(iter(codes)):
            raise ValueError(f"{label} fact-index codes must match embedded facts")
        source_path = next(iter(paths))
        if source_path is None or entry.source_path != source_path:
            raise ValueError(f"{label} fact-index paths must match embedded facts")
        expected_evidence_keys: list[str] = []
        for record in fact_records:
            for evidence_payload in _fact_evidence_payloads(record):
                matches = evidence_payload_to_keys.get(
                    _canonical_json_bytes(evidence_payload),
                    [],
                )
                if len(matches) != 1:
                    raise ValueError(
                        f"{label} embedded fact evidence must resolve uniquely"
                    )
                expected_evidence_keys.append(matches[0])
        expected_evidence_keys = sorted(set(expected_evidence_keys))
        if entry.evidence_keys != expected_evidence_keys:
            raise ValueError(
                f"{label} fact-index evidence must exactly match embedded facts"
            )


def _validate_typed_fact_evidence_closure(
    *,
    embedded_sources: Any,
    fact_index: dict[str, FactIndexEntry],
    evidence_index: dict[str, EvidenceRef],
    label: str,
) -> None:
    """Validate the same closure without expanding the whole typed graph to JSON."""

    fact_states: dict[str, dict[str, set[str]]] = {}
    for record in _iter_typed_fact_records(embedded_sources):
        fact_id = str(record["fact_id"])
        state = fact_states.setdefault(
            fact_id,
            {"codes": set(), "paths": set(), "evidence": set()},
        )
        state["codes"].add(str(record["code"]))
        source_path = _fact_source_path(record)
        if source_path is not None:
            state["paths"].add(source_path)
        state["evidence"].update(
            _canonical_json_bytes(payload).decode("utf-8")
            for payload in _fact_evidence_payloads(record)
        )

    if set(fact_states) != set(fact_index):
        raise ValueError(f"{label} embedded facts must exactly match the fact index")

    evidence_payload_to_keys: dict[str, list[str]] = {}
    for key, evidence in evidence_index.items():
        canonical = _canonical_json_bytes(
            evidence.model_dump(mode="json")
        ).decode("utf-8")
        evidence_payload_to_keys.setdefault(canonical, []).append(key)

    for fact_id, state in fact_states.items():
        entry = fact_index[fact_id]
        if fact_id != entry.fact_id:
            raise ValueError(f"{label} fact-index keys must equal stable fact IDs")
        if len(state["codes"]) != 1 or len(state["paths"]) != 1:
            raise ValueError(
                f"{label} embedded fact IDs must be globally unique per fact identity"
            )
        if entry.fact_code != next(iter(state["codes"])):
            raise ValueError(f"{label} fact-index codes must match embedded facts")
        if entry.source_path != next(iter(state["paths"])):
            raise ValueError(f"{label} fact-index paths must match embedded facts")
        expected_evidence_keys: list[str] = []
        for canonical in state["evidence"]:
            matches = evidence_payload_to_keys.get(canonical, [])
            if len(matches) != 1:
                raise ValueError(
                    f"{label} embedded fact evidence must resolve uniquely"
                )
            expected_evidence_keys.append(matches[0])
        if entry.evidence_keys != sorted(set(expected_evidence_keys)):
            raise ValueError(
                f"{label} fact-index evidence must exactly match embedded facts"
            )


def _iter_typed_fact_records(value: Any):
    if isinstance(value, (AnalysisItem, AgentDimensionGateFact)):
        yield value.model_dump(mode="json")
        return
    if isinstance(value, dict):
        typed_fact = value.get("fact_type") == "dimension_gate" and {
            "fact_id",
            "code",
            "availability",
            "conclusion_strength",
            "conclusion_direction",
        }.issubset(value)
        if typed_fact or (
            {"fact_id", "code", "values"}.issubset(value)
            and isinstance(value["values"], list)
        ):
            yield value
        for child in value.values():
            yield from _iter_typed_fact_records(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            yield from _iter_typed_fact_records(child)
        return
    model_fields = getattr(type(value), "model_fields", None)
    if isinstance(model_fields, dict):
        for field_name in model_fields:
            yield from _iter_typed_fact_records(getattr(value, field_name))


def _collect_typed_list_field_values(value: Any, field_name: str) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == field_name and isinstance(child, list):
                values.extend(str(item) for item in child)
            else:
                values.extend(_collect_typed_list_field_values(child, field_name))
    elif isinstance(value, (list, tuple)):
        for child in value:
            values.extend(_collect_typed_list_field_values(child, field_name))
    else:
        model_fields = getattr(type(value), "model_fields", None)
        if isinstance(model_fields, dict):
            for current_name in model_fields:
                child = getattr(value, current_name)
                if current_name == field_name and isinstance(child, list):
                    values.extend(str(item) for item in child)
                else:
                    values.extend(
                        _collect_typed_list_field_values(child, field_name)
                    )
    return values


def _collect_list_field_values(value: JsonValue, field_name: str) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == field_name and isinstance(child, list):
                values.extend(str(item) for item in child)
            else:
                values.extend(_collect_list_field_values(child, field_name))
    elif isinstance(value, list):
        for child in value:
            values.extend(_collect_list_field_values(child, field_name))
    return values


def _collect_scalar_field_values(value: JsonValue, field_name: str) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == field_name and isinstance(child, str):
                values.append(child)
            else:
                values.extend(_collect_scalar_field_values(child, field_name))
    elif isinstance(value, list):
        for child in value:
            values.extend(_collect_scalar_field_values(child, field_name))
    return values


__all__ = [
    "ALL_QUESTION_CODES",
    "ALL_RELATION_CODES",
    "AgentCandidateAnalysis",
    "AgentDimensionGateFact",
    "AgentExcludedCandidateAudit",
    "AgentPrioritySelectionDiff",
    "AnalysisItem",
    "AdapterSourceReceipt",
    "COMPETITOR_PROFILE_V1_1_ADAPTER_VERSION",
    "COMPETITOR_PROFILE_V1_1_METHOD_VERSION",
    "COMPETITOR_PROFILE_V1_1_PREVALENCE_VERSION",
    "COMPETITOR_PROFILE_V1_1_RULE_VERSION",
    "COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION",
    "COMPETITOR_PROFILE_V1_1_SCORE_POLICY_VERSION",
    "CalculationComponent",
    "CategoryPerformanceStorageBudget",
    "ClaimFactItem",
    "ClaimAttributionRecord",
    "ClaimContributionRecord",
    "ClaimContributionSnapshot",
    "ClaimMarketPosition",
    "ClaimValueFactItem",
    "ClaimValueRecord",
    "ClaimValueSnapshot",
    "ComparisonRole",
    "CompetitorProfileAdapterContract",
    "CompetitorProfileAnalysisDTO",
    "CompetitorProfileV11BaseModel",
    "ConclusionDirection",
    "ConclusionMetric",
    "ConclusionStrength",
    "DimensionAnalysisResult",
    "DimensionAvailability",
    "DimensionCode",
    "DimensionScore",
    "FOUNDATIONAL_FEATURE_MINIMUM_KNOWN_COUNT",
    "FOUNDATIONAL_FEATURE_PREVALENCE_THRESHOLD",
    "FactSectionsSnapshot",
    "FactIndexEntry",
    "FactSupportStatus",
    "FeatureAnalysisItem",
    "FeatureMarketStatus",
    "FeaturePrevalenceContract",
    "FeatureRawDifference",
    "G29PerformanceStorageBudget",
    "HARD_EXCLUSION_CODES",
    "IdentityMarketSnapshot",
    "LegacyAnalysisCompatibilityPayload",
    "LegacyAnalyzedPairCompatibilityPayload",
    "LegacyCandidateCompatibilityPayload",
    "LegacyCompetitorAnalysisCompatibilityEnvelope",
    "LegacyInputCompatibilityPayload",
    "LegacyScoreBasis",
    "LegacyPrioritySelectionDiff",
    "LegacySnapshotCompatibilityPayload",
    "LegacyTypedAliasContract",
    "LegacyTypedFieldContract",
    "LegacyTypedMappingContract",
    "LegacyValueType",
    "MachineReadableConclusion",
    "MarketValidationAnalysisResult",
    "ModuleAvailabilitySnapshot",
    "NormalizedSourceFact",
    "NormalizedSourceOccurrence",
    "PRIMARY_DIMENSION_WEIGHTS",
    "PRIMARY_SCORE_DIMENSIONS",
    "PairAnalysisSnapshot",
    "PairAnalysisProcessSnapshot",
    "PairAnalysisSourceLineage",
    "PairAuditSummary",
    "PairBusinessQuestionResult",
    "PairDimensionSet",
    "PairDimensionGateSnapshot",
    "PairIndexItem",
    "PairScopeStatus",
    "PairScoreBreakdown",
    "PairScoreComponent",
    "PairSelectionAssessment",
    "PriorityCompetitorSelection",
    "ProductFormFacts",
    "ProfileGenerationReceipt",
    "ProfileVersionAnalysisContext",
    "PurchaseReasonAnchorFact",
    "PurchaseReasonAnchorRecord",
    "PurchaseReasonSnapshot",
    "PurchasePoolAnalysis",
    "PurchasePoolGateFact",
    "PurchasePressureComparisonResult",
    "PurchasePressureReasonRecord",
    "QUESTION_ALTERNATIVE_EVIDENCE_GROUPS",
    "QUESTION_REQUIRED_DIMENSIONS",
    "QuestionAlternativeEvidenceGroup",
    "RELATION_REQUIRED_DIMENSIONS",
    "RelationAssessment",
    "RelationStatusV11",
    "ReplacementPressureAnalysisResult",
    "ReviewItem",
    "SalesOverlapSnapshot",
    "ScorePolicyComponent",
    "ScorePolicyContract",
    "SkuCompetitionAnalysisSummary",
    "SkuExcessExplanationRecord",
    "SkuLevelClaimValueRecord",
    "SkuMarketSnapshot",
    "SummaryFinding",
    "TypedFactValue",
    "ValueAnchorAnalysisResult",
    "ValueAnchorMatchDetail",
    "ValuePresence",
    "VersionSkuAnalysisSnapshot",
]
