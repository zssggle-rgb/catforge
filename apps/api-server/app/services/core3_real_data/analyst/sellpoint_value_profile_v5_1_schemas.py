"""Typed contracts for the low-gate sellpoint-value profile V5.1.

This module defines data and state invariants only.  It does not read competitor
profiles, select candidates, calculate market gaps, persist rows, or render
product-manager answers.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
    SellpointValueProfileBaseModel,
)


SPV_V5_1_SCHEMA_VERSION = "sku_sellpoint_value_decision_profile_v1_1"
SPV_V5_1_RULE_VERSION = "sellpoint_value_profile_rule_v5_1"
SPV_V5_1_METHOD_VERSION = "sellpoint_value_profile_method_v5_1"
SPV_V5_1_CONFIG_VERSION = "sellpoint_value_profile_low_gate_v5_1"
SPV_V5_1_COMPETITOR_METHOD_VERSION = "competitor_profile_agent_snapshot_v2"


class QuestionConclusionStatus(str, Enum):
    CONCLUSION_AVAILABLE = "conclusion_available"
    PARTIAL_CONCLUSION = "partial_conclusion"
    NO_CONCLUSION = "no_conclusion"
    INVALID = "invalid"


class QuestionConclusionStrength(str, Enum):
    GROUP = "group"
    SMALL_GROUP = "small_group"
    SINGLE = "single"
    DIRECTIONAL = "directional"
    NONE = "none"


class CandidateSourceType(str, Enum):
    COMPETITOR = "competitor"
    MARKET_REFERENCE = "market_reference"


class QuantificationLayer(str, Enum):
    USER_VALUE_EVIDENCE = "user_value_evidence"
    DIRECT_MARKET_GAP = "direct_market_gap"
    MARKET_ARCHETYPE = "market_archetype"
    STRICT_MARKET_IMPLIED_WTP = "strict_market_implied_wtp"


class TableStakeAssessmentStatus(str, Enum):
    CONFIRMED_TABLE_STAKE = "confirmed_table_stake"
    NOT_TABLE_STAKE = "not_table_stake"
    NOT_ASSESSED = "not_assessed"
    INVALID = "invalid"


class CompetitorProfileCandidateRef(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_rank: int = Field(ge=1)
    selected_rank: int | None = Field(default=None, ge=1, le=3)
    role: str = Field(min_length=1)
    business_score: Decimal = Field(ge=0, le=1)
    pair_result_hash: str = Field(min_length=1)


class SellpointValueCompetitorSource(SellpointValueProfileBaseModel):
    source: Literal["competitor_profile_agent_snapshot_v2"]
    access_mode: Literal["formal", "preview"]
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    method_version: Literal["competitor_profile_agent_snapshot_v2"]
    release_status: Literal["draft", "published"]
    is_current: bool
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidates: list[CompetitorProfileCandidateRef] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list, max_length=3)
    source_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source(self) -> "SellpointValueCompetitorSource":
        if self.access_mode == "formal" and (
            self.release_status != "published" or not self.is_current
        ):
            raise ValueError("formal competitor source must be current published")
        if self.access_mode == "preview":
            valid_preview = (
                self.release_status == "draft" and not self.is_current
            ) or (self.release_status == "published" and self.is_current)
            if not valid_preview:
                raise ValueError(
                    "preview requires a non-current draft or current published"
                )
        codes = [row.candidate_sku_code for row in self.candidates]
        if len(codes) != len(set(codes)):
            raise ValueError("competitor source candidates must be unique")
        if self.target_sku_code in codes:
            raise ValueError("competitor source cannot contain the target SKU")
        if {row.source_rank for row in self.candidates} != set(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("competitor source ranks must be contiguous")
        selected = sorted(
            (row for row in self.candidates if row.selected_rank is not None),
            key=lambda row: row.selected_rank or 0,
        )
        selected_codes = [row.candidate_sku_code for row in selected]
        if selected and [row.selected_rank for row in selected] != list(
            range(1, len(selected) + 1)
        ):
            raise ValueError("selected competitor ranks must be contiguous")
        if self.priority_order != selected_codes:
            raise ValueError("priority order must match saved selected ranks")
        return self


class QuestionCandidateUse(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_type: CandidateSourceType
    selected: bool
    usable_dimensions: list[str] = Field(default_factory=list)
    unavailable_dimensions: list[str] = Field(default_factory=list)
    selection_reasons: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_question_use(self) -> "QuestionCandidateUse":
        usable = set(self.usable_dimensions)
        unavailable = set(self.unavailable_dimensions)
        if len(usable) != len(self.usable_dimensions) or len(unavailable) != len(
            self.unavailable_dimensions
        ):
            raise ValueError("question candidate dimensions must be unique")
        if usable & unavailable:
            raise ValueError("usable and unavailable dimensions must not overlap")
        if self.selected:
            if not self.usable_dimensions or not self.selection_reasons:
                raise ValueError("selected candidates require usable facts and reasons")
            if self.rejection_reasons:
                raise ValueError("selected candidates cannot contain rejection reasons")
        elif not self.rejection_reasons:
            raise ValueError("unselected candidates require question-local reasons")
        return self


class DirectMarketGap(SellpointValueProfileBaseModel):
    method: Literal[
        "same_claim_different_realization",
        "direct_comparable",
        "same_budget_pool",
        "same_brand_size_ladder",
        "parameter_configuration",
    ]
    comparator_sku_codes: list[str] = Field(min_length=1)
    comparator_count: int = Field(ge=1)
    strength: Literal["single", "small_group", "group"]
    target_price: Decimal | None = Field(default=None, ge=0)
    comparator_price: Decimal | None = Field(default=None, ge=0)
    price_gap_abs: Decimal | None = None
    price_gap_pct: Decimal | None = None
    target_weekly_sales: Decimal | None = Field(default=None, ge=0)
    comparator_weekly_sales: Decimal | None = Field(default=None, ge=0)
    sales_gap_abs: Decimal | None = None
    sales_gap_pct: Decimal | None = None
    causal_claim: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gap(self) -> "DirectMarketGap":
        if len(self.comparator_sku_codes) != len(set(self.comparator_sku_codes)):
            raise ValueError("direct market comparators must be unique")
        if self.comparator_count != len(self.comparator_sku_codes):
            raise ValueError("comparator count must match comparator SKU codes")
        expected_strength = (
            "single"
            if self.comparator_count == 1
            else "small_group"
            if self.comparator_count <= 4
            else "group"
        )
        if self.strength != expected_strength:
            raise ValueError("direct market strength must match comparator count")
        price_values = (
            self.target_price,
            self.comparator_price,
            self.price_gap_abs,
            self.price_gap_pct,
        )
        sales_values = (
            self.target_weekly_sales,
            self.comparator_weekly_sales,
            self.sales_gap_abs,
            self.sales_gap_pct,
        )
        if any(value is not None for value in price_values) and not all(
            value is not None for value in price_values
        ):
            raise ValueError(
                "price comparison fields must be all present or all absent"
            )
        if any(value is not None for value in sales_values) and not all(
            value is not None for value in sales_values
        ):
            raise ValueError(
                "sales comparison fields must be all present or all absent"
            )
        if not any(value is not None for value in (*price_values, *sales_values)):
            raise ValueError("direct market gap requires a price or sales comparison")
        return self


class QuantificationResult(SellpointValueProfileBaseModel):
    layer: QuantificationLayer
    method: str = Field(min_length=1)
    status: QuestionConclusionStatus
    strength: QuestionConclusionStrength
    candidate_uses: list[QuestionCandidateUse] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    direct_market_gaps: list[DirectMarketGap] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result_state(self) -> "QuantificationResult":
        candidate_codes = [row.candidate_sku_code for row in self.candidate_uses]
        if len(candidate_codes) != len(set(candidate_codes)):
            raise ValueError("question candidate uses must be unique by SKU")
        selected = [row for row in self.candidate_uses if row.selected]
        if self.status in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }:
            if not self.result or self.strength == QuestionConclusionStrength.NONE:
                raise ValueError("available conclusions require a result and strength")
            if self.layer != QuantificationLayer.USER_VALUE_EVIDENCE and not selected:
                raise ValueError("market conclusions require selected candidates")
        if self.status == QuestionConclusionStatus.NO_CONCLUSION:
            if self.result or self.direct_market_gaps:
                raise ValueError(
                    "no-conclusion results cannot expose calculated effects"
                )
            if self.strength != QuestionConclusionStrength.NONE:
                raise ValueError("no-conclusion results require none strength")
            if self.review_required or self.review_reasons:
                raise ValueError("missing evidence is not an automatic review")
        if self.status == QuestionConclusionStatus.INVALID:
            if not self.review_required or not self.review_reasons:
                raise ValueError("invalid results require explicit review reasons")
        elif self.review_required != bool(self.review_reasons):
            raise ValueError("review flag and reasons must agree")
        if self.layer == QuantificationLayer.DIRECT_MARKET_GAP:
            if (
                self.status
                in {
                    QuestionConclusionStatus.CONCLUSION_AVAILABLE,
                    QuestionConclusionStatus.PARTIAL_CONCLUSION,
                }
                and not self.direct_market_gaps
            ):
                raise ValueError("direct market conclusions require gap rows")
        elif self.direct_market_gaps:
            raise ValueError("direct market gaps belong only to the direct layer")
        return self


class ValueQuantificationStack(SellpointValueProfileBaseModel):
    value_bundle_code: str = Field(min_length=1)
    results: list[QuantificationResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_layers(self) -> "ValueQuantificationStack":
        layers = [row.layer for row in self.results]
        if len(layers) != len(set(layers)):
            raise ValueError("value quantification layers must be unique")
        return self


class TableStakeAssessment(SellpointValueProfileBaseModel):
    capability_code: str = Field(min_length=1)
    status: TableStakeAssessmentStatus
    total_count: int = Field(ge=0)
    known_count: int = Field(ge=0)
    present_count: int = Field(ge=0)
    absent_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    contradicted_count: int = Field(ge=0)
    minimum_known_count: int = Field(ge=1)
    prevalence_threshold: Decimal = Field(gt=0, le=1)
    prevalence: Decimal | None = Field(default=None, ge=0, le=1)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assessment(self) -> "TableStakeAssessment":
        if self.known_count != self.present_count + self.absent_count:
            raise ValueError("known count must equal present plus absent")
        if self.total_count != (
            self.known_count + self.missing_count + self.contradicted_count
        ):
            raise ValueError("table-stake fact counts must cover the total")
        expected = (
            Decimal(self.present_count) / Decimal(self.known_count)
            if self.known_count
            else None
        )
        if self.prevalence != expected:
            raise ValueError("prevalence must equal present divided by known")
        if self.status == TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE and (
            self.known_count < self.minimum_known_count
            or self.prevalence is None
            or self.prevalence < self.prevalence_threshold
        ):
            raise ValueError("confirmed table stake must pass the positive threshold")
        if self.status == TableStakeAssessmentStatus.NOT_TABLE_STAKE and (
            self.known_count < self.minimum_known_count
            or self.prevalence is None
            or self.prevalence >= self.prevalence_threshold
        ):
            raise ValueError(
                "not-table-stake requires sufficient known samples below threshold"
            )
        if self.status == TableStakeAssessmentStatus.NOT_ASSESSED:
            if self.known_count >= self.minimum_known_count:
                raise ValueError("not-assessed requires insufficient known samples")
            if self.review_required or self.review_reasons:
                raise ValueError(
                    "insufficient table-stake samples do not require review"
                )
        elif (
            self.status != TableStakeAssessmentStatus.INVALID
            and self.known_count < self.minimum_known_count
        ):
            raise ValueError("insufficient known samples must remain not-assessed")
        if self.status == TableStakeAssessmentStatus.INVALID:
            if not self.review_required or not self.review_reasons:
                raise ValueError("invalid table-stake assessments require review")
        elif self.review_required != bool(self.review_reasons):
            raise ValueError("review flag and reasons must agree")
        return self


class ConclusionDistribution(SellpointValueProfileBaseModel):
    total_count: int = Field(ge=0)
    conclusion_available_count: int = Field(ge=0)
    partial_conclusion_count: int = Field(ge=0)
    no_conclusion_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_distribution(self) -> "ConclusionDistribution":
        if self.total_count != (
            self.conclusion_available_count
            + self.partial_conclusion_count
            + self.no_conclusion_count
            + self.invalid_count
        ):
            raise ValueError("conclusion distribution must cover the total")
        return self


class ReleaseIntegritySummary(SellpointValueProfileBaseModel):
    expected_sku_count: int = Field(ge=1)
    generated_sku_count: int = Field(ge=0)
    generation_failure_count: int = Field(ge=0)
    invalid_profile_count: int = Field(ge=0)
    cross_category_count: int = Field(ge=0)
    duplicate_sku_count: int = Field(ge=0)
    dangling_reference_count: int = Field(ge=0)
    hash_mismatch_count: int = Field(ge=0)


class ProfileReleaseAssessment(SellpointValueProfileBaseModel):
    release_quality_status: Literal["ready", "limited", "blocked"]
    conclusion_distribution: ConclusionDistribution
    integrity: ReleaseIntegritySummary
    review_item_count: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_release_quality(self) -> "ProfileReleaseAssessment":
        integrity = self.integrity
        blocking = any(
            (
                integrity.generated_sku_count != integrity.expected_sku_count,
                integrity.generation_failure_count,
                integrity.invalid_profile_count,
                integrity.cross_category_count,
                integrity.duplicate_sku_count,
                integrity.dangling_reference_count,
                integrity.hash_mismatch_count,
                self.conclusion_distribution.invalid_count,
            )
        )
        limited = any(
            (
                self.conclusion_distribution.partial_conclusion_count,
                self.conclusion_distribution.no_conclusion_count,
                self.review_item_count,
                bool(self.limitations),
            )
        )
        expected = "blocked" if blocking else "limited" if limited else "ready"
        if self.release_quality_status != expected:
            raise ValueError(
                "release quality must be derived from integrity and states"
            )
        return self


__all__ = [
    "CandidateSourceType",
    "CompetitorProfileCandidateRef",
    "ConclusionDistribution",
    "DirectMarketGap",
    "ProfileReleaseAssessment",
    "QuantificationLayer",
    "QuantificationResult",
    "QuestionCandidateUse",
    "QuestionConclusionStatus",
    "QuestionConclusionStrength",
    "ReleaseIntegritySummary",
    "SPV_V5_1_COMPETITOR_METHOD_VERSION",
    "SPV_V5_1_CONFIG_VERSION",
    "SPV_V5_1_METHOD_VERSION",
    "SPV_V5_1_RULE_VERSION",
    "SPV_V5_1_SCHEMA_VERSION",
    "SellpointValueCompetitorSource",
    "TableStakeAssessment",
    "TableStakeAssessmentStatus",
    "ValueQuantificationStack",
]
