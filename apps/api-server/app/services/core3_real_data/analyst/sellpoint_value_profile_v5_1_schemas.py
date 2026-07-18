"""Typed contracts for the low-gate sellpoint-value profile V5.1.

This module defines data and state invariants only.  It does not read competitor
profiles, select candidates, calculate market gaps, persist rows, or render
product-manager answers.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from statistics import median
from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CandidateQuestion,
    CapabilityInvestmentInput,
    InvestmentClassification,
    SellpointValueEvidenceRef,
    SellpointValueProfileBaseModel,
)


SPV_V5_1_SCHEMA_VERSION = "sku_sellpoint_value_decision_profile_v1_1"
SPV_V5_1_RULE_VERSION = "sellpoint_value_profile_rule_v5_1"
SPV_V5_1_METHOD_VERSION = "sellpoint_value_profile_method_v5_1"
SPV_V5_1_CONFIG_VERSION = "sellpoint_value_profile_low_gate_v5_1"
SPV_V5_1_COMPETITOR_METHOD_VERSION = "competitor_profile_agent_snapshot_v2"
SPV_V5_1_CANDIDATE_QUESTIONS: tuple[CandidateQuestion, ...] = (
    "current_price_support",
    "value_relative_advantage",
    "same_brand_role",
    "scale_conversion",
    "configuration_follow",
    "specific_competitor",
    "parameter_conversion",
    "battlefield_expansion",
)
SPV_V5_1_COMPETITOR_FACT_GROUPS = (
    "basis",
    "semantic_overlap",
    "parameter_claim_overlap",
    "sales_overlap",
    "target_purchase_reason_profile",
    "candidate_purchase_reason_profile",
    "anchor_substitutability",
    "value_anchor",
    "replacement_pressure",
    "purchase_pressure_comparison",
    "m12d_consumption",
    "purchase_pool",
    "weighted_overlap",
    "matched_dimensions",
    "market_validation",
    "selection_gate",
    "ranking_trace",
    "ranking_gate_reasons",
    "shared_business_context",
)


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


class MarketObservationSourceType(str, Enum):
    TARGET = "target"
    COMPETITOR = "competitor"
    MARKET_REFERENCE = "market_reference"


class MarketMetricCode(str, Enum):
    PRICE = "price"
    WEEKLY_SALES = "weekly_sales"


class MarketComparisonDirection(str, Enum):
    TARGET_HIGHER = "target_higher"
    TARGET_LOWER = "target_lower"
    EQUAL = "equal"


class AnalysisReferencePurpose(str, Enum):
    SAME_SIZE_MARKET = "same_size_market"
    SAME_BUDGET_MARKET = "same_budget_market"
    SAME_BRAND_SIZE_LADDER = "same_brand_size_ladder"
    PARAMETER_GROUP = "parameter_group"
    PERFORMANCE_ARCHETYPE = "performance_archetype"
    BATTLEFIELD_BENCHMARK = "battlefield_benchmark"
    SYNTHETIC_DONOR = "synthetic_donor"


class InvestmentQuestionCode(str, Enum):
    INVESTMENT_CONVERSION = "investment_conversion"
    CONFIGURATION_FOLLOW = "configuration_follow"


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


class CompetitorProfileSkuMarketFacts(SellpointValueProfileBaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    product_category: Literal["TV", "AC"]
    size_tier: str | None = None
    price_band_in_size_tier: str | None = None
    screen_size_inch: Decimal | None = Field(default=None, ge=0)
    weighted_price: Decimal | None = Field(default=None, ge=0)
    avg_weekly_sales_volume: Decimal | None = Field(default=None, ge=0)
    sales_volume_total: Decimal | None = Field(default=None, ge=0)
    price_gap_to_target: Decimal | None = None
    price_gap_pct_to_target: Decimal | None = None


class CompetitorProfilePairFacts(SellpointValueProfileBaseModel):
    basis: dict[str, Any]
    semantic_overlap: dict[str, Any]
    parameter_claim_overlap: dict[str, Any]
    sales_overlap: dict[str, Any]
    target_purchase_reason_profile: dict[str, Any]
    candidate_purchase_reason_profile: dict[str, Any]
    anchor_substitutability: dict[str, Any]
    value_anchor: dict[str, Any]
    replacement_pressure: dict[str, Any]
    purchase_pressure_comparison: dict[str, Any]
    m12d_consumption: dict[str, Any]
    purchase_pool: dict[str, Any]
    weighted_overlap: dict[str, Any]
    matched_dimensions: dict[str, Any]
    market_validation: dict[str, Any]
    selection_gate: dict[str, Any]
    ranking_trace: dict[str, Any]
    ranking_gate_reasons: list[str]
    shared_business_context: list[str]
    available_fact_groups: list[str]
    unavailable_fact_groups: list[str]

    @model_validator(mode="after")
    def validate_availability(self) -> "CompetitorProfilePairFacts":
        available = self.available_fact_groups
        unavailable = self.unavailable_fact_groups
        if len(available) != len(set(available)) or len(unavailable) != len(
            set(unavailable)
        ):
            raise ValueError("competitor fact availability groups must be unique")
        if set(available) & set(unavailable):
            raise ValueError("competitor fact availability groups must not overlap")
        expected = set(SPV_V5_1_COMPETITOR_FACT_GROUPS)
        if set(available) | set(unavailable) != expected:
            raise ValueError("competitor fact availability must cover every fact group")
        return self


class CompetitorProfileCandidateRef(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_rank: int = Field(ge=1)
    selected_rank: int | None = Field(default=None, ge=1, le=3)
    role: str = Field(min_length=1)
    role_cn: str = Field(min_length=1)
    business_score: Decimal = Field(ge=0, le=1)
    pair_result_hash: str = Field(min_length=1)
    market: CompetitorProfileSkuMarketFacts
    parameter_facts: list["CompetitorProfileParameterFact"] = Field(
        default_factory=list
    )
    pair_facts: CompetitorProfilePairFacts

    @model_validator(mode="after")
    def validate_candidate(self) -> "CompetitorProfileCandidateRef":
        if self.market.sku_code != self.candidate_sku_code:
            raise ValueError("competitor market facts must match candidate SKU")
        codes = [row.parameter_code for row in self.parameter_facts]
        if len(codes) != len(set(codes)):
            raise ValueError("competitor parameter facts must be unique")
        return self


class CompetitorProfileParameterFact(SellpointValueProfileBaseModel):
    parameter_code: str = Field(min_length=1)
    fact_status: Literal[
        "known_present",
        "known_absent",
        "missing",
        "contradicted",
    ]
    normalized_value: Any | None = None
    numeric_value: Decimal | None = None
    value_text: str | None = None
    unit: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_snapshot_ref: str = Field(min_length=1)
    source_snapshot_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fact(self) -> "CompetitorProfileParameterFact":
        if self.evidence_ids != sorted(set(self.evidence_ids)):
            raise ValueError("parameter evidence IDs must be sorted and unique")
        return self


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
    target_market: CompetitorProfileSkuMarketFacts
    target_parameter_facts: list[CompetitorProfileParameterFact] = Field(
        default_factory=list
    )
    candidates: list[CompetitorProfileCandidateRef] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list, max_length=3)
    source_version_result_hash: str = Field(min_length=1)
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
        if (
            self.target_market.sku_code != self.target_sku_code
            or self.target_market.product_category != self.category_code
        ):
            raise ValueError("competitor source target market must match source scope")
        target_codes = [row.parameter_code for row in self.target_parameter_facts]
        if len(target_codes) != len(set(target_codes)):
            raise ValueError("target parameter facts must be unique")
        codes = [row.candidate_sku_code for row in self.candidates]
        if len(codes) != len(set(codes)):
            raise ValueError("competitor source candidates must be unique")
        if self.target_sku_code in codes:
            raise ValueError("competitor source cannot contain the target SKU")
        if any(
            row.market.product_category != self.category_code for row in self.candidates
        ):
            raise ValueError("competitor source candidates must stay in category")
        if [row.source_rank for row in self.candidates] != list(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("competitor source ranks must be ordered and contiguous")
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
    source_rank: int | None = Field(default=None, ge=1)
    priority_rank: int | None = Field(default=None, ge=1, le=3)
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
        if self.usable_dimensions != sorted(self.usable_dimensions) or (
            self.unavailable_dimensions != sorted(self.unavailable_dimensions)
        ):
            raise ValueError("question candidate dimensions must be sorted")
        if usable & unavailable:
            raise ValueError("usable and unavailable dimensions must not overlap")
        if self.source_type == CandidateSourceType.MARKET_REFERENCE and (
            self.source_rank is not None or self.priority_rank is not None
        ):
            raise ValueError("market references cannot carry competitor ranks")
        if self.selected:
            if not self.usable_dimensions or not self.selection_reasons:
                raise ValueError("selected candidates require usable facts and reasons")
            if self.rejection_reasons:
                raise ValueError("selected candidates cannot contain rejection reasons")
        elif not self.rejection_reasons:
            raise ValueError("unselected candidates require question-local reasons")
        return self


class SellpointValueAnalysisReference(SellpointValueProfileBaseModel):
    reference_sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    purposes: list[AnalysisReferencePurpose] = Field(min_length=1)
    also_competitor: bool = False
    same_brand_as_target: bool | None = None
    market: CompetitorProfileSkuMarketFacts
    parameter_facts: dict[str, Any] | None = None
    battlefield_facts: dict[str, Any] | None = None
    value_facts: dict[str, Any] | None = None
    source_hashes: dict[str, str] = Field(default_factory=dict)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reference(self) -> "SellpointValueAnalysisReference":
        if self.market.sku_code != self.reference_sku_code:
            raise ValueError("analysis reference market facts must match reference SKU")
        purposes = [value.value for value in self.purposes]
        if purposes != sorted(set(purposes)):
            raise ValueError("analysis reference purposes must be sorted and unique")
        return self


class QuestionCandidateSet(SellpointValueProfileBaseModel):
    question_code: CandidateQuestion
    required_dimensions: list[str] = Field(default_factory=list)
    alternative_dimension_groups: list[list[str]] = Field(default_factory=list)
    allowed_reference_purposes: list[AnalysisReferencePurpose] = Field(
        default_factory=list
    )
    candidate_uses: list[QuestionCandidateUse] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate_set(self) -> "QuestionCandidateSet":
        if self.required_dimensions != sorted(set(self.required_dimensions)):
            raise ValueError("required dimensions must be sorted and unique")
        normalized_groups = [
            sorted(set(group)) for group in self.alternative_dimension_groups
        ]
        if any(not group for group in normalized_groups):
            raise ValueError("alternative dimension groups cannot be empty")
        if normalized_groups != self.alternative_dimension_groups:
            raise ValueError("alternative dimension groups must be sorted and unique")
        purposes = [value.value for value in self.allowed_reference_purposes]
        if purposes != sorted(set(purposes)):
            raise ValueError("allowed reference purposes must be sorted and unique")
        keys = [
            (row.source_type.value, row.candidate_sku_code)
            for row in self.candidate_uses
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("question candidate uses must be unique within each pool")
        return self


class SellpointValueCandidatePools(SellpointValueProfileBaseModel):
    schema_version: Literal["sellpoint_value_candidate_pools_v5_1"]
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    competitor_profile_version_id: str = Field(min_length=1)
    competitor_source_result_hash: str = Field(min_length=1)
    competitor_source_version_result_hash: str = Field(min_length=1)
    formal_competitors: list[CompetitorProfileCandidateRef] = Field(
        default_factory=list
    )
    priority_order: list[str] = Field(default_factory=list, max_length=3)
    analysis_references: list[SellpointValueAnalysisReference] = Field(
        default_factory=list
    )
    question_candidate_sets: list[QuestionCandidateSet] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pools(self) -> "SellpointValueCandidatePools":
        competitor_codes = [row.candidate_sku_code for row in self.formal_competitors]
        if len(competitor_codes) != len(set(competitor_codes)):
            raise ValueError("formal competitors must be unique")
        if self.target_sku_code in competitor_codes:
            raise ValueError("target cannot appear in the formal competitor pool")
        if [row.source_rank for row in self.formal_competitors] != list(
            range(1, len(self.formal_competitors) + 1)
        ):
            raise ValueError("formal competitor ranks must be ordered and contiguous")
        selected = sorted(
            (row for row in self.formal_competitors if row.selected_rank is not None),
            key=lambda row: row.selected_rank or 0,
        )
        if self.priority_order != [row.candidate_sku_code for row in selected]:
            raise ValueError(
                "priority order must remain a label from the source profile"
            )
        reference_codes = [row.reference_sku_code for row in self.analysis_references]
        if len(reference_codes) != len(set(reference_codes)):
            raise ValueError("analysis references must be unique")
        if self.target_sku_code in reference_codes:
            raise ValueError("target cannot appear in the analysis reference pool")
        if any(
            row.market.product_category != self.category_code
            for row in [*self.formal_competitors, *self.analysis_references]
        ):
            raise ValueError("candidate pools must stay within category")
        competitor_code_set = set(competitor_codes)
        if any(
            row.also_competitor != (row.reference_sku_code in competitor_code_set)
            for row in self.analysis_references
        ):
            raise ValueError("analysis reference overlap flag must match formal pool")
        questions = [row.question_code for row in self.question_candidate_sets]
        if questions != list(SPV_V5_1_CANDIDATE_QUESTIONS):
            raise ValueError("candidate pools must assess every question in order")
        expected_keys = [
            *((CandidateSourceType.COMPETITOR, code) for code in competitor_codes),
            *((CandidateSourceType.MARKET_REFERENCE, code) for code in reference_codes),
        ]
        candidate_by_code = {
            row.candidate_sku_code: row for row in self.formal_competitors
        }
        for question in self.question_candidate_sets:
            actual_keys = [
                (row.source_type, row.candidate_sku_code)
                for row in question.candidate_uses
            ]
            if actual_keys != expected_keys:
                raise ValueError(
                    "each question must assess every pool member in source order"
                )
            for use in question.candidate_uses:
                if use.source_type != CandidateSourceType.COMPETITOR:
                    continue
                candidate = candidate_by_code[use.candidate_sku_code]
                if (
                    use.source_rank != candidate.source_rank
                    or use.priority_rank != candidate.selected_rank
                ):
                    raise ValueError(
                        "question competitor ranks must remain source labels"
                    )
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


class MarketComparatorObservation(SellpointValueProfileBaseModel):
    category_code: Literal["TV", "AC"]
    candidate_use: QuestionCandidateUse
    market: CompetitorProfileSkuMarketFacts
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_observation(self) -> "MarketComparatorObservation":
        if self.market.product_category != self.category_code:
            raise ValueError("market comparator must stay within category")
        if self.market.sku_code != self.candidate_use.candidate_sku_code:
            raise ValueError("market comparator facts must match candidate use")
        return self


class DirectMarketComparisonInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    method: Literal[
        "same_claim_different_realization",
        "direct_comparable",
        "same_budget_pool",
        "same_brand_size_ladder",
        "parameter_configuration",
    ] = "direct_comparable"
    target_market: CompetitorProfileSkuMarketFacts
    comparators: list[MarketComparatorObservation] = Field(default_factory=list)
    target_evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self) -> "DirectMarketComparisonInput":
        if (
            self.target_market.sku_code != self.target_sku_code
            or self.target_market.product_category != self.category_code
        ):
            raise ValueError("direct market target facts must match input scope")
        identities = [
            (
                row.candidate_use.source_type,
                row.candidate_use.candidate_sku_code,
            )
            for row in self.comparators
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("market comparator identities must be unique")
        if any(row.category_code != self.category_code for row in self.comparators):
            raise ValueError("direct market comparators must stay within category")
        if any(row.market.sku_code == self.target_sku_code for row in self.comparators):
            raise ValueError("direct market comparator cannot be the target")
        return self


class MetricCandidateDisposition(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_type: CandidateSourceType
    used_metrics: list[MarketMetricCode] = Field(default_factory=list)
    skipped_metrics: list[MarketMetricCode] = Field(default_factory=list)
    skip_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disposition(self) -> "MetricCandidateDisposition":
        used = [row.value for row in self.used_metrics]
        skipped = [row.value for row in self.skipped_metrics]
        if used != sorted(set(used)) or skipped != sorted(set(skipped)):
            raise ValueError("metric disposition lists must be sorted and unique")
        if set(used) & set(skipped):
            raise ValueError("a candidate metric cannot be used and skipped")
        if self.skip_reasons != sorted(set(self.skip_reasons)):
            raise ValueError("metric skip reasons must be sorted and unique")
        return self


class MarketMetricComparison(SellpointValueProfileBaseModel):
    metric: MarketMetricCode
    strength: QuestionConclusionStrength
    target_value: Decimal = Field(ge=0)
    comparator_average: Decimal = Field(ge=0)
    comparator_sku_codes: list[str] = Field(min_length=1)
    comparator_count: int = Field(ge=1)
    gap_abs: Decimal
    gap_pct: Decimal | None = None
    direction: MarketComparisonDirection

    @model_validator(mode="after")
    def validate_metric(self) -> "MarketMetricComparison":
        if self.comparator_sku_codes != sorted(set(self.comparator_sku_codes)):
            raise ValueError("metric comparator SKU codes must be sorted and unique")
        if self.comparator_count != len(self.comparator_sku_codes):
            raise ValueError("metric comparator count must match SKU codes")
        expected_strength = (
            QuestionConclusionStrength.SINGLE
            if self.comparator_count == 1
            else QuestionConclusionStrength.SMALL_GROUP
            if self.comparator_count <= 4
            else QuestionConclusionStrength.GROUP
        )
        if self.strength != expected_strength:
            raise ValueError("market metric strength must match comparator count")
        if self.gap_abs != self.target_value - self.comparator_average:
            raise ValueError("metric gap must equal target minus comparator average")
        expected_direction = (
            MarketComparisonDirection.TARGET_HIGHER
            if self.gap_abs > 0
            else MarketComparisonDirection.TARGET_LOWER
            if self.gap_abs < 0
            else MarketComparisonDirection.EQUAL
        )
        if self.direction != expected_direction:
            raise ValueError("metric direction must match the calculated gap")
        if self.comparator_average == 0 and self.gap_pct is not None:
            raise ValueError("zero comparator average has no percentage gap")
        if self.comparator_average > 0 and self.gap_pct is None:
            raise ValueError("positive comparator average requires percentage gap")
        return self


class DirectMarketComparisonResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    method: str = Field(min_length=1)
    status: QuestionConclusionStatus
    strength: QuestionConclusionStrength
    used_comparator_sku_codes: list[str] = Field(default_factory=list)
    comparator_count: int = Field(ge=0)
    price_comparison: MarketMetricComparison | None = None
    sales_comparison: MarketMetricComparison | None = None
    candidate_dispositions: list[MetricCandidateDisposition] = Field(
        default_factory=list
    )
    business_conclusion_cn: str = Field(min_length=1)
    causal_claim: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "DirectMarketComparisonResult":
        codes = self.used_comparator_sku_codes
        if codes != sorted(set(codes)) or self.comparator_count != len(codes):
            raise ValueError(
                "direct market used comparators must be unique and counted"
            )
        comparisons = [
            row
            for row in (self.price_comparison, self.sales_comparison)
            if row is not None
        ]
        strength_rank = {
            QuestionConclusionStrength.SINGLE: 1,
            QuestionConclusionStrength.SMALL_GROUP: 2,
            QuestionConclusionStrength.GROUP: 3,
        }
        expected_strength = (
            min(comparisons, key=lambda row: strength_rank[row.strength]).strength
            if comparisons
            else QuestionConclusionStrength.NONE
        )
        if self.strength != expected_strength:
            raise ValueError("direct market strength must match its weakest metric")
        available_count = sum(
            row is not None for row in (self.price_comparison, self.sales_comparison)
        )
        expected_status = (
            QuestionConclusionStatus.NO_CONCLUSION
            if available_count == 0
            else QuestionConclusionStatus.CONCLUSION_AVAILABLE
            if available_count == 2
            else QuestionConclusionStatus.PARTIAL_CONCLUSION
        )
        if self.status != expected_status:
            raise ValueError("direct market status must match available metrics")
        if self.review_required or self.review_reasons:
            raise ValueError("missing direct market metrics do not require review")
        dispositions = [
            (row.candidate_sku_code, row.source_type.value)
            for row in self.candidate_dispositions
        ]
        if dispositions != sorted(set(dispositions)):
            raise ValueError("direct market dispositions must be sorted and unique")
        return self


class ParameterValueObservation(SellpointValueProfileBaseModel):
    category_code: Literal["TV", "AC"]
    sku_code: str = Field(min_length=1)
    source_type: MarketObservationSourceType
    normalized_value: str | None = None
    weighted_price: Decimal | None = Field(default=None, ge=0)
    avg_weekly_sales_volume: Decimal | None = Field(default=None, ge=0)
    candidate_use: QuestionCandidateUse | None = None
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_observation(self) -> "ParameterValueObservation":
        if self.normalized_value is not None and not self.normalized_value.strip():
            raise ValueError("normalized parameter value cannot be blank")
        if self.source_type == MarketObservationSourceType.TARGET:
            if self.candidate_use is not None:
                raise ValueError(
                    "target parameter observation cannot carry candidate use"
                )
        else:
            if self.candidate_use is None:
                raise ValueError(
                    "candidate parameter observation requires candidate use"
                )
            if (
                self.candidate_use.candidate_sku_code != self.sku_code
                or self.candidate_use.source_type.value != self.source_type.value
            ):
                raise ValueError("parameter observation must match candidate use")
        return self


class ParameterGroupComparisonInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    parameter_code: str = Field(min_length=1)
    parameter_name_cn: str = Field(min_length=1)
    unit: str | None = None
    target: ParameterValueObservation
    comparators: list[ParameterValueObservation] = Field(default_factory=list)
    exclude_from_core_sellpoints: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> "ParameterGroupComparisonInput":
        if (
            self.target.source_type != MarketObservationSourceType.TARGET
            or self.target.sku_code != self.target_sku_code
            or self.target.category_code != self.category_code
        ):
            raise ValueError("parameter target observation must match input scope")
        identities = [(row.source_type, row.sku_code) for row in self.comparators]
        if len(identities) != len(set(identities)):
            raise ValueError("parameter comparator identities must be unique")
        if any(
            row.source_type == MarketObservationSourceType.TARGET
            for row in self.comparators
        ):
            raise ValueError("parameter comparators cannot use target identity")
        if any(row.category_code != self.category_code for row in self.comparators):
            raise ValueError("parameter comparators must stay within category")
        if any(row.sku_code == self.target_sku_code for row in self.comparators):
            raise ValueError("parameter comparator cannot be the target")
        return self


class ParameterCandidateDisposition(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_type: CandidateSourceType
    used: bool
    skip_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disposition(self) -> "ParameterCandidateDisposition":
        if self.skip_reasons != sorted(set(self.skip_reasons)):
            raise ValueError("parameter skip reasons must be sorted and unique")
        if (self.used and self.skip_reasons) or (
            not self.used and not self.skip_reasons
        ):
            raise ValueError("used parameter rows cannot have skip reasons")
        return self


class ParameterValueGroup(SellpointValueProfileBaseModel):
    normalized_value: str = Field(min_length=1)
    is_target_group: bool
    sku_codes: list[str] = Field(min_length=1)
    sku_count: int = Field(ge=1)
    price_sku_codes: list[str] = Field(default_factory=list)
    average_price: Decimal | None = Field(default=None, ge=0)
    sales_sku_codes: list[str] = Field(default_factory=list)
    average_weekly_sales: Decimal | None = Field(default=None, ge=0)
    price_gap_to_target_group: Decimal | None = None
    price_gap_pct_to_target_group: Decimal | None = None
    sales_gap_to_target_group: Decimal | None = None
    sales_gap_pct_to_target_group: Decimal | None = None

    @model_validator(mode="after")
    def validate_group(self) -> "ParameterValueGroup":
        if self.sku_codes != sorted(set(self.sku_codes)) or self.sku_count != len(
            self.sku_codes
        ):
            raise ValueError("parameter group SKU codes must be unique and counted")
        for codes, average, label in (
            (self.price_sku_codes, self.average_price, "price"),
            (self.sales_sku_codes, self.average_weekly_sales, "sales"),
        ):
            if codes != sorted(set(codes)) or not set(codes).issubset(self.sku_codes):
                raise ValueError(f"parameter group {label} SKU codes are invalid")
            if bool(codes) != (average is not None):
                raise ValueError(
                    f"parameter group {label} average must match SKU codes"
                )
        return self


class ParameterGroupComparisonResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    parameter_code: str = Field(min_length=1)
    parameter_name_cn: str = Field(min_length=1)
    unit: str | None = None
    target_value: str | None = None
    status: QuestionConclusionStatus
    strength: QuestionConclusionStrength
    distinct_values: list[str] = Field(default_factory=list)
    different_value_comparator_count: int = Field(ge=0)
    groups: list[ParameterValueGroup] = Field(default_factory=list)
    candidate_dispositions: list[ParameterCandidateDisposition] = Field(
        default_factory=list
    )
    core_highlight_eligible: bool
    business_conclusion_cn: str = Field(min_length=1)
    causal_claim: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "ParameterGroupComparisonResult":
        if self.distinct_values != sorted(set(self.distinct_values)):
            raise ValueError("parameter distinct values must be sorted and unique")
        group_values = [row.normalized_value for row in self.groups]
        if len(group_values) != len(set(group_values)) or set(group_values) != set(
            self.distinct_values
        ):
            raise ValueError("parameter groups must match distinct values")
        target_groups = [row for row in self.groups if row.is_target_group]
        if self.target_value is None:
            if target_groups or self.status != QuestionConclusionStatus.NO_CONCLUSION:
                raise ValueError(
                    "missing target parameter value cannot form a conclusion"
                )
        elif (
            len(target_groups) != 1
            or target_groups[0].normalized_value != self.target_value
        ):
            raise ValueError("parameter result requires exactly one target value group")
        expected_strength = (
            QuestionConclusionStrength.NONE
            if self.different_value_comparator_count == 0
            else QuestionConclusionStrength.DIRECTIONAL
            if self.different_value_comparator_count == 1
            else QuestionConclusionStrength.SMALL_GROUP
            if self.different_value_comparator_count <= 4
            else QuestionConclusionStrength.GROUP
        )
        if self.strength != expected_strength:
            raise ValueError(
                "parameter strength must match different-value sample size"
            )
        if self.different_value_comparator_count == 0:
            if self.status != QuestionConclusionStatus.NO_CONCLUSION:
                raise ValueError(
                    "parameter comparison requires a different value group"
                )
        elif self.status not in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }:
            raise ValueError("different parameter values must form a usable conclusion")
        if self.review_required or self.review_reasons:
            raise ValueError("missing parameter evidence does not require review")
        dispositions = [
            (row.candidate_sku_code, row.source_type.value)
            for row in self.candidate_dispositions
        ]
        if dispositions != sorted(set(dispositions)):
            raise ValueError("parameter dispositions must be sorted and unique")
        return self


class MarketArchetypeMethod(str, Enum):
    SAME_BUDGET = "same_budget"
    PERFORMANCE_CONTRAST = "performance_contrast"
    ADJACENT_BATTLEFIELD = "adjacent_battlefield"


class MarketArchetypeGroupSnapshot(SellpointValueProfileBaseModel):
    role: str = Field(min_length=1)
    sku_codes: list[str] = Field(default_factory=list)
    sku_count: int = Field(ge=0)
    average_price: Decimal | None = Field(default=None, ge=0)
    average_weekly_sales: Decimal | None = Field(default=None, ge=0)
    value_bundle_prevalence: dict[str, Decimal] = Field(default_factory=dict)
    user_outcome_prevalence: dict[str, Decimal] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_group(self) -> "MarketArchetypeGroupSnapshot":
        if self.sku_codes != sorted(set(self.sku_codes)):
            raise ValueError("market archetype SKU codes must be sorted and unique")
        if self.sku_count < len(self.sku_codes):
            raise ValueError(
                "market archetype representatives cannot exceed sample count"
            )
        for mapping in (
            self.value_bundle_prevalence,
            self.user_outcome_prevalence,
        ):
            if any(value < 0 or value > 1 for value in mapping.values()):
                raise ValueError(
                    "market archetype prevalence must be between zero and one"
                )
        return self


class MarketArchetypeEnhancementResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    method: MarketArchetypeMethod
    status: QuestionConclusionStatus
    strength: QuestionConclusionStrength
    groups: list[MarketArchetypeGroupSnapshot] = Field(default_factory=list)
    business_conclusion_cn: str = Field(min_length=1)
    visible_by_default: bool
    causal_claim: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    source_result_hashes: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "MarketArchetypeEnhancementResult":
        roles = [row.role for row in self.groups]
        if roles != sorted(set(roles)):
            raise ValueError("market archetype roles must be sorted and unique")
        if self.source_result_hashes != sorted(set(self.source_result_hashes)):
            raise ValueError("market archetype source hashes must be sorted and unique")
        if self.status == QuestionConclusionStatus.NO_CONCLUSION:
            if (
                self.strength != QuestionConclusionStrength.NONE
                or self.visible_by_default
            ):
                raise ValueError(
                    "unavailable archetypes must stay hidden with none strength"
                )
        elif self.status in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }:
            if not self.groups or self.strength == QuestionConclusionStrength.NONE:
                raise ValueError("available archetypes require groups and strength")
            if not self.visible_by_default:
                raise ValueError(
                    "available market archetypes are default business results"
                )
        if self.review_required or self.review_reasons:
            raise ValueError(
                "optional market archetype failure does not require review"
            )
        return self


class SyntheticMarketBaselineResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    status: QuestionConclusionStatus
    strength: QuestionConclusionStrength
    source_status: str = Field(min_length=1)
    donor_sku_codes: list[str] = Field(default_factory=list)
    donor_count: int = Field(ge=0)
    effective_donor_count: Decimal | None = Field(default=None, ge=0)
    price_difference_estimate: Decimal | None = None
    sales_difference_estimate: Decimal | None = None
    gate_pass: bool
    failed_gates: list[str] = Field(default_factory=list)
    business_conclusion_cn: str = Field(min_length=1)
    visible_by_default: bool
    causal_claim: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    source_result_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "SyntheticMarketBaselineResult":
        if self.donor_sku_codes != sorted(set(self.donor_sku_codes)):
            raise ValueError("synthetic donor SKU codes must be sorted and unique")
        if self.donor_count != len(self.donor_sku_codes):
            raise ValueError("synthetic donor count must match codes")
        if self.gate_pass != (not self.failed_gates):
            raise ValueError("synthetic gate flag must match failed gates")
        effects = (self.price_difference_estimate, self.sales_difference_estimate)
        if self.status == QuestionConclusionStatus.CONCLUSION_AVAILABLE:
            if (
                not self.gate_pass
                or not any(value is not None for value in effects)
                or self.strength == QuestionConclusionStrength.NONE
                or not self.visible_by_default
            ):
                raise ValueError("available synthetic baseline requires passed effects")
        elif self.status == QuestionConclusionStatus.NO_CONCLUSION:
            if (
                any(value is not None for value in effects)
                or self.strength != QuestionConclusionStrength.NONE
                or self.visible_by_default
            ):
                raise ValueError("unavailable synthetic baseline cannot expose effects")
        if self.review_required or self.review_reasons:
            raise ValueError("optional synthetic failure does not require review")
        return self


class StrictMarketImpliedWtpResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    status: QuestionConclusionStatus
    method: str = Field(min_length=1)
    estimate_low: Decimal | None = None
    estimate_center: Decimal | None = None
    estimate_high: Decimal | None = None
    reference_price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(min_length=1)
    pair_count: int = Field(ge=0)
    model_family_count: int = Field(ge=0)
    gate_results: dict[str, bool] = Field(default_factory=dict)
    business_conclusion_cn: str = Field(min_length=1)
    visible_by_default: bool
    causal_claim: Literal[False] = False
    psychological_max_price: Literal[False] = False
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    source_status: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "StrictMarketImpliedWtpResult":
        amounts = (self.estimate_low, self.estimate_center, self.estimate_high)
        if self.status == QuestionConclusionStatus.CONCLUSION_AVAILABLE:
            if (
                any(value is None for value in amounts)
                or not self.visible_by_default
                or self.method != "matched_equal_choice_price_gap"
                or self.pair_count < 2
                or self.model_family_count < 2
                or not self.gate_results
                or not all(self.gate_results.values())
            ):
                raise ValueError(
                    "available strict WTP requires amounts and passed gates"
                )
            if not self.estimate_low <= self.estimate_center <= self.estimate_high:  # type: ignore[operator]
                raise ValueError("strict WTP center must stay inside its interval")
        elif self.status == QuestionConclusionStatus.NO_CONCLUSION:
            if (
                any(value is not None for value in amounts)
                or self.reference_price is not None
                or self.visible_by_default
            ):
                raise ValueError(
                    "unavailable strict WTP must stay hidden without amounts"
                )
        if self.review_required or self.review_reasons:
            raise ValueError("optional strict WTP failure does not require review")
        return self


class QuestionConclusionSignal(SellpointValueProfileBaseModel):
    question_code: str = Field(min_length=1)
    status: QuestionConclusionStatus
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    source_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signal(self) -> "QuestionConclusionSignal":
        if (
            self.status
            in {
                QuestionConclusionStatus.NO_CONCLUSION,
                QuestionConclusionStatus.INVALID,
            }
            and self.confidence is not None
        ):
            raise ValueError(
                "no-conclusion and invalid signals cannot carry confidence"
            )
        if self.status == QuestionConclusionStatus.INVALID:
            if not self.review_required or not self.review_reasons:
                raise ValueError("invalid question signal requires local review")
        elif self.review_required or self.review_reasons:
            raise ValueError("only invalid question signals require review")
        return self


class ValueConclusionAggregationInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    question_signals: list[QuestionConclusionSignal] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_questions(self) -> "ValueConclusionAggregationInput":
        codes = [row.question_code for row in self.question_signals]
        if len(codes) != len(set(codes)):
            raise ValueError("value question signals must be unique")
        return self


class ValueConclusionResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    status: QuestionConclusionStatus
    question_count: int = Field(ge=0)
    conclusion_available_count: int = Field(ge=0)
    partial_conclusion_count: int = Field(ge=0)
    no_conclusion_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    conclusion_confidences: list[Decimal] = Field(default_factory=list)
    confidence_min: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_median: Decimal | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    source_result_hashes: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "ValueConclusionResult":
        counts = (
            self.conclusion_available_count,
            self.partial_conclusion_count,
            self.no_conclusion_count,
            self.invalid_count,
        )
        if self.question_count != sum(counts):
            raise ValueError("value conclusion counts must cover all questions")
        expected_status = (
            QuestionConclusionStatus.INVALID
            if self.invalid_count
            else QuestionConclusionStatus.CONCLUSION_AVAILABLE
            if self.conclusion_available_count
            else QuestionConclusionStatus.PARTIAL_CONCLUSION
            if self.partial_conclusion_count
            else QuestionConclusionStatus.NO_CONCLUSION
        )
        if self.status != expected_status:
            raise ValueError("value status must follow local question precedence")
        if self.conclusion_confidences != sorted(self.conclusion_confidences):
            raise ValueError("value conclusion confidences must be sorted")
        if self.conclusion_confidences:
            if self.confidence_min != min(
                self.conclusion_confidences
            ) or self.confidence_median != median(self.conclusion_confidences):
                raise ValueError("value confidence summary must match direct evidence")
        elif self.confidence_min is not None or self.confidence_median is not None:
            raise ValueError("missing conclusion confidence must remain unknown")
        if self.review_required != (self.status == QuestionConclusionStatus.INVALID):
            raise ValueError("value review is only the overlay for local invalid state")
        if self.review_required != bool(self.review_reasons):
            raise ValueError("value review flag and reasons must agree")
        if self.source_result_hashes != sorted(set(self.source_result_hashes)):
            raise ValueError("value source hashes must be sorted and unique")
        return self


class SkuConclusionAggregationInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    value_results: list[ValueConclusionResult] = Field(default_factory=list)
    structural_invalid_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self) -> "SkuConclusionAggregationInput":
        codes = [row.value_bundle_code for row in self.value_results]
        if len(codes) != len(set(codes)):
            raise ValueError("SKU value results must be unique")
        if any(
            row.project_id != self.project_id
            or row.category_code != self.category_code
            or row.target_sku_code != self.target_sku_code
            for row in self.value_results
        ):
            raise ValueError("SKU value results must stay within scope")
        if self.structural_invalid_reasons != sorted(
            set(self.structural_invalid_reasons)
        ):
            raise ValueError("structural invalid reasons must be sorted and unique")
        return self


class SkuConclusionResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    status: QuestionConclusionStatus
    consumer_status: Literal[
        "usable_conclusion",
        "usable_partial",
        "data_insufficient",
        "invalid",
    ]
    value_count: int = Field(ge=0)
    conclusion_available_value_codes: list[str] = Field(default_factory=list)
    partial_conclusion_value_codes: list[str] = Field(default_factory=list)
    no_conclusion_value_codes: list[str] = Field(default_factory=list)
    invalid_value_codes: list[str] = Field(default_factory=list)
    local_review_value_codes: list[str] = Field(default_factory=list)
    conclusion_confidences: list[Decimal] = Field(default_factory=list)
    confidence_min: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_median: Decimal | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    structural_invalid_reasons: list[str] = Field(default_factory=list)
    source_result_hashes: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "SkuConclusionResult":
        code_lists = (
            self.conclusion_available_value_codes,
            self.partial_conclusion_value_codes,
            self.no_conclusion_value_codes,
            self.invalid_value_codes,
        )
        if any(values != sorted(set(values)) for values in code_lists):
            raise ValueError("SKU value code lists must be sorted and unique")
        flattened = [value for values in code_lists for value in values]
        if self.value_count != len(flattened) or len(flattened) != len(set(flattened)):
            raise ValueError("SKU value state lists must partition every value")
        expected_status = (
            QuestionConclusionStatus.INVALID
            if self.structural_invalid_reasons
            else QuestionConclusionStatus.CONCLUSION_AVAILABLE
            if self.conclusion_available_value_codes
            else QuestionConclusionStatus.PARTIAL_CONCLUSION
            if self.partial_conclusion_value_codes
            else QuestionConclusionStatus.INVALID
            if self.invalid_value_codes and not self.no_conclusion_value_codes
            else QuestionConclusionStatus.NO_CONCLUSION
        )
        if self.status != expected_status:
            raise ValueError("SKU status must not propagate a local invalid value")
        expected_consumer_status = {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE: "usable_conclusion",
            QuestionConclusionStatus.PARTIAL_CONCLUSION: "usable_partial",
            QuestionConclusionStatus.NO_CONCLUSION: "data_insufficient",
            QuestionConclusionStatus.INVALID: "invalid",
        }[self.status]
        if self.consumer_status != expected_consumer_status:
            raise ValueError("SKU consumer status must match conclusion status")
        if self.local_review_value_codes != self.invalid_value_codes:
            raise ValueError("local review values must preserve local invalid values")
        if self.conclusion_confidences != sorted(self.conclusion_confidences):
            raise ValueError("SKU conclusion confidences must be sorted")
        if self.conclusion_confidences:
            if self.confidence_min != min(
                self.conclusion_confidences
            ) or self.confidence_median != median(self.conclusion_confidences):
                raise ValueError("SKU confidence summary must match direct evidence")
        elif self.confidence_min is not None or self.confidence_median is not None:
            raise ValueError(
                "SKU confidence must remain unknown without direct evidence"
            )
        if self.review_required != (self.status == QuestionConclusionStatus.INVALID):
            raise ValueError("only an invalid SKU requires SKU-level review")
        if self.review_required != bool(self.review_reasons):
            raise ValueError("SKU review flag and reasons must agree")
        if self.source_result_hashes != sorted(set(self.source_result_hashes)):
            raise ValueError("SKU source hashes must be sorted and unique")
        return self


class VersionConclusionAggregationInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    expected_sku_codes: list[str] = Field(min_length=1)
    sku_results: list[SkuConclusionResult] = Field(default_factory=list)
    generation_failure_sku_codes: list[str] = Field(default_factory=list)
    dangling_reference_count: int = Field(default=0, ge=0)
    hash_mismatch_count: int = Field(default=0, ge=0)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input(self) -> "VersionConclusionAggregationInput":
        if self.expected_sku_codes != sorted(set(self.expected_sku_codes)):
            raise ValueError("expected SKU codes must be sorted and unique")
        if self.generation_failure_sku_codes != sorted(
            set(self.generation_failure_sku_codes)
        ):
            raise ValueError("generation failure SKU codes must be sorted and unique")
        return self


class VersionConclusionResult(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_quality_status: Literal["ready", "limited", "blocked"]
    conclusion_distribution: ConclusionDistribution
    integrity: ReleaseIntegritySummary
    conclusion_available_sku_codes: list[str] = Field(default_factory=list)
    partial_conclusion_sku_codes: list[str] = Field(default_factory=list)
    no_conclusion_sku_codes: list[str] = Field(default_factory=list)
    invalid_sku_codes: list[str] = Field(default_factory=list)
    generation_failure_sku_codes: list[str] = Field(default_factory=list)
    local_review_item_count: int = Field(ge=0)
    confidence_min: Decimal | None = Field(default=None, ge=0, le=1)
    confidence_median: Decimal | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    source_result_hashes: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "VersionConclusionResult":
        lists = (
            self.conclusion_available_sku_codes,
            self.partial_conclusion_sku_codes,
            self.no_conclusion_sku_codes,
            self.invalid_sku_codes,
        )
        if any(values != sorted(set(values)) for values in lists):
            raise ValueError("version SKU status lists must be sorted and unique")
        flattened = [value for values in lists for value in values]
        if len(flattened) != len(set(flattened)):
            raise ValueError("version SKU status lists must not overlap")
        if self.conclusion_distribution.total_count != len(flattened):
            raise ValueError("version distribution must match SKU status lists")
        expected_counts = (
            len(self.conclusion_available_sku_codes),
            len(self.partial_conclusion_sku_codes),
            len(self.no_conclusion_sku_codes),
            len(self.invalid_sku_codes),
        )
        actual_counts = (
            self.conclusion_distribution.conclusion_available_count,
            self.conclusion_distribution.partial_conclusion_count,
            self.conclusion_distribution.no_conclusion_count,
            self.conclusion_distribution.invalid_count,
        )
        if actual_counts != expected_counts:
            raise ValueError("version distribution counts must match SKU status lists")
        if self.integrity.invalid_profile_count != len(
            self.invalid_sku_codes
        ) or self.integrity.generation_failure_count != len(
            self.generation_failure_sku_codes
        ):
            raise ValueError("version integrity counts must match saved status lists")
        blocking = any(
            (
                self.integrity.generated_sku_count != self.integrity.expected_sku_count,
                self.integrity.generation_failure_count,
                self.integrity.invalid_profile_count,
                self.integrity.cross_category_count,
                self.integrity.duplicate_sku_count,
                self.integrity.dangling_reference_count,
                self.integrity.hash_mismatch_count,
                self.conclusion_distribution.invalid_count,
            )
        )
        limited = any(
            (
                self.conclusion_distribution.partial_conclusion_count,
                self.conclusion_distribution.no_conclusion_count,
                self.local_review_item_count,
                bool(self.limitations),
            )
        )
        expected_quality = "blocked" if blocking else "limited" if limited else "ready"
        if self.release_quality_status != expected_quality:
            raise ValueError(
                "version quality must derive from integrity and local states"
            )
        if (self.confidence_min is None) != (self.confidence_median is None):
            raise ValueError(
                "version confidence summary must be jointly present or absent"
            )
        if (
            self.confidence_min is not None
            and self.confidence_median is not None
            and self.confidence_min > self.confidence_median
        ):
            raise ValueError("version confidence minimum cannot exceed median")
        if self.source_result_hashes != sorted(set(self.source_result_hashes)):
            raise ValueError("version source hashes must be sorted and unique")
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
        candidate_keys = [
            (row.source_type, row.candidate_sku_code) for row in self.candidate_uses
        ]
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("question candidate uses must be unique within each pool")
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
    scope_complete: bool = True
    exclude_from_core_sellpoints: bool | None = None
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_assessment(self) -> "TableStakeAssessment":
        if self.exclude_from_core_sellpoints is not None and (
            self.exclude_from_core_sellpoints
            != (self.status == TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE)
        ):
            raise ValueError(
                "only confirmed table stakes are excluded from core sellpoints"
            )
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
            not self.scope_complete
            or self.contradicted_count
            or self.known_count < self.minimum_known_count
            or self.prevalence is None
            or self.prevalence < self.prevalence_threshold
        ):
            raise ValueError("confirmed table stake must pass the positive threshold")
        if self.status == TableStakeAssessmentStatus.NOT_TABLE_STAKE and (
            not self.scope_complete
            or self.contradicted_count
            or self.known_count < self.minimum_known_count
            or self.prevalence is None
            or self.prevalence >= self.prevalence_threshold
        ):
            raise ValueError(
                "not-table-stake requires sufficient known samples below threshold"
            )
        if self.status == TableStakeAssessmentStatus.NOT_ASSESSED:
            if self.known_count >= self.minimum_known_count and self.scope_complete:
                raise ValueError("not-assessed requires insufficient samples or scope")
            if self.review_required or self.review_reasons:
                raise ValueError(
                    "insufficient table-stake samples do not require review"
                )
        elif self.status != TableStakeAssessmentStatus.INVALID and (
            self.known_count < self.minimum_known_count or not self.scope_complete
        ):
            raise ValueError("insufficient evidence must remain not-assessed")
        if self.status == TableStakeAssessmentStatus.INVALID:
            if not self.review_required or not self.review_reasons:
                raise ValueError("invalid table-stake assessments require review")
        elif self.review_required != bool(self.review_reasons):
            raise ValueError("review flag and reasons must agree")
        return self


class CapabilityInvestmentQuestionInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    question_code: InvestmentQuestionCode
    value_bundle_code: str = Field(min_length=1)
    investment: CapabilityInvestmentInput

    @model_validator(mode="after")
    def validate_scope(self) -> "CapabilityInvestmentQuestionInput":
        if self.investment.comparison_scope.category_code != self.category_code:
            raise ValueError("investment question must stay within category")
        return self


class LocalCapabilityInvestmentDecision(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    question_code: InvestmentQuestionCode
    value_bundle_code: str = Field(min_length=1)
    capability_code: str = Field(min_length=1)
    capability_name_cn: str = Field(min_length=1)
    classification: InvestmentClassification
    status: QuestionConclusionStatus
    table_stake_assessment: TableStakeAssessment
    used_dimensions: list[str] = Field(default_factory=list)
    unavailable_dimensions: list[str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_local_decision(self) -> "LocalCapabilityInvestmentDecision":
        used = self.used_dimensions
        unavailable = self.unavailable_dimensions
        if used != sorted(set(used)) or unavailable != sorted(set(unavailable)):
            raise ValueError("investment dimensions must be sorted and unique")
        if set(used) & set(unavailable):
            raise ValueError(
                "used and unavailable investment dimensions cannot overlap"
            )
        if self.status in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }:
            if self.classification == "unknown" or self.confidence is None:
                raise ValueError(
                    "available investment conclusions require a classification"
                )
            if self.review_required or self.review_reasons:
                raise ValueError("valid investment conclusions cannot carry review")
        elif self.status == QuestionConclusionStatus.NO_CONCLUSION:
            if self.classification != "unknown" or self.confidence is not None:
                raise ValueError("no-conclusion investments must remain unknown")
            if self.review_required or self.review_reasons:
                raise ValueError("insufficient investment evidence is not review")
        elif self.status == QuestionConclusionStatus.INVALID:
            if (
                self.classification != "unknown"
                or not self.review_required
                or not self.review_reasons
            ):
                raise ValueError("invalid investment decisions require local review")
        if self.classification == "table_stake" and (
            self.table_stake_assessment.status
            != TableStakeAssessmentStatus.CONFIRMED_TABLE_STAKE
        ):
            raise ValueError("table-stake decisions require a confirmed assessment")
        allowed = (
            {"retain", "unconverted", "table_stake", "unknown"}
            if self.question_code == InvestmentQuestionCode.INVESTMENT_CONVERSION
            else {"do_not_follow", "missing_competitive_gap", "unknown"}
        )
        if self.classification not in allowed:
            raise ValueError("investment classification does not answer this question")
        return self


class InvestmentScopeReview(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    question_code: InvestmentQuestionCode
    value_bundle_code: str = Field(min_length=1)
    invalid_capability_codes: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_review(self) -> "InvestmentScopeReview":
        if self.invalid_capability_codes != sorted(set(self.invalid_capability_codes)):
            raise ValueError("invalid capability codes must be sorted and unique")
        if self.review_required != bool(self.invalid_capability_codes):
            raise ValueError("local review must match invalid capabilities")
        if self.review_required != bool(self.review_reasons):
            raise ValueError("local review flag and reasons must agree")
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
    "AnalysisReferencePurpose",
    "CandidateSourceType",
    "CapabilityInvestmentQuestionInput",
    "CompetitorProfileCandidateRef",
    "CompetitorProfileParameterFact",
    "ConclusionDistribution",
    "DirectMarketComparisonInput",
    "DirectMarketComparisonResult",
    "DirectMarketGap",
    "InvestmentQuestionCode",
    "InvestmentScopeReview",
    "LocalCapabilityInvestmentDecision",
    "MarketComparatorObservation",
    "MarketComparisonDirection",
    "MarketArchetypeEnhancementResult",
    "MarketArchetypeGroupSnapshot",
    "MarketArchetypeMethod",
    "MarketMetricCode",
    "MarketMetricComparison",
    "MarketObservationSourceType",
    "MetricCandidateDisposition",
    "ParameterCandidateDisposition",
    "ParameterGroupComparisonInput",
    "ParameterGroupComparisonResult",
    "ParameterValueGroup",
    "ParameterValueObservation",
    "ProfileReleaseAssessment",
    "QuantificationLayer",
    "QuantificationResult",
    "QuestionCandidateUse",
    "QuestionCandidateSet",
    "QuestionConclusionSignal",
    "QuestionConclusionStatus",
    "QuestionConclusionStrength",
    "ReleaseIntegritySummary",
    "SPV_V5_1_COMPETITOR_METHOD_VERSION",
    "SPV_V5_1_CANDIDATE_QUESTIONS",
    "SPV_V5_1_CONFIG_VERSION",
    "SPV_V5_1_METHOD_VERSION",
    "SPV_V5_1_RULE_VERSION",
    "SPV_V5_1_SCHEMA_VERSION",
    "SellpointValueCompetitorSource",
    "SkuConclusionAggregationInput",
    "SkuConclusionResult",
    "StrictMarketImpliedWtpResult",
    "SyntheticMarketBaselineResult",
    "SellpointValueAnalysisReference",
    "SellpointValueCandidatePools",
    "TableStakeAssessment",
    "TableStakeAssessmentStatus",
    "ValueConclusionAggregationInput",
    "ValueConclusionResult",
    "ValueQuantificationStack",
    "VersionConclusionAggregationInput",
    "VersionConclusionResult",
]
