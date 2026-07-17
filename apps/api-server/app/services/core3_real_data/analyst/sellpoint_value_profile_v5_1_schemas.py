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
    pair_facts: CompetitorProfilePairFacts

    @model_validator(mode="after")
    def validate_candidate(self) -> "CompetitorProfileCandidateRef":
        if self.market.sku_code != self.candidate_sku_code:
            raise ValueError("competitor market facts must match candidate SKU")
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
    "ConclusionDistribution",
    "DirectMarketGap",
    "InvestmentQuestionCode",
    "InvestmentScopeReview",
    "LocalCapabilityInvestmentDecision",
    "ProfileReleaseAssessment",
    "QuantificationLayer",
    "QuantificationResult",
    "QuestionCandidateUse",
    "QuestionCandidateSet",
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
    "SellpointValueAnalysisReference",
    "SellpointValueCandidatePools",
    "TableStakeAssessment",
    "TableStakeAssessmentStatus",
    "ValueQuantificationStack",
]
