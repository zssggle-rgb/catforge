"""Typed contracts for the sellpoint-value V5 decision analysis.

V5 composes the already-audited V4 context and adds multi-layer
counterfactuals, observational market references, battlefield portfolio
options, parallel price/volume accounting, and a single PM business DTO.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    EvidenceRef,
    MarketImpliedWtp,
    SellpointBundle,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
    SkuIdentity,
    SourceAuthority,
)


AnalysisState = Literal["ready", "partial", "blocked"]
ValueStatus = Literal[
    "observed_positive",
    "observed_mixed",
    "observed_negative",
    "partial",
    "not_observed",
    "conflicted",
    "unknown",
]
MeasureStatus = Literal[
    "available", "degraded", "blocked", "unidentifiable", "not_applicable"
]
CounterfactualQuestion = Literal[
    "user_realization",
    "relative_highlight",
    "without_value_baseline",
    "price_realization",
    "volume_realization",
    "strict_bundle_price_interval",
    "battlefield_portfolio",
]
CounterfactualMethod = Literal[
    "direct_sku",
    "same_budget_pool",
    "same_brand_size_ladder",
    "param_tier_pool",
    "same_claim_realization",
    "own_price_curve",
    "market_synthetic",
    "performance_archetype",
]
CandidateStage = Literal["recalled", "screened", "eligible", "rejected"]
ComparabilityGrade = Literal["A", "B", "C", "unusable"]
HighlightType = Literal[
    "user_realization", "relative_value", "price_realization", "volume_realization"
]
BattlefieldMembership = Literal[
    "primary", "secondary", "opportunity", "user_observed", "drag", "excluded"
]
BattlefieldOptionType = Literal["strengthen_existing", "expand_excluded"]
StrengthenPath = Literal[
    "communication_activation",
    "capability_completion",
    "market_activation",
    "portfolio_priority",
    "maintain_or_cap",
]
ExpansionStage = Literal["recalled", "eligible", "rejected", "deferred_unknown"]
GapChangeType = Literal[
    "communication", "capability", "price", "size", "product_form", "unknown"
]
IncrementClaimType = Literal[
    "current_allocation",
    "observational_gross",
    "observational_cannibalization",
    "observational_net",
]
AmountMethod = Literal["none", "matched_equal_choice_price_gap"]
ArchetypeRole = Literal[
    "high_performance", "neutral", "low_performance", "unstable"
]


class SellpointValueV5BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class BattlefieldDefinitionSnapshot(SellpointValueV5BaseModel):
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = ""
    immutable_size_tiers: list[str] = Field(default_factory=list)
    product_forms: list[str] = Field(default_factory=list)
    source_hash: str = Field(min_length=1)


class MethodConfigManifest(SellpointValueV5BaseModel):
    recall_version: str = Field(min_length=1)
    synthetic_version: str = Field(min_length=1)
    archetype_version: str = Field(min_length=1)
    expansion_version: str = Field(min_length=1)
    amount_version: str = Field(min_length=1)


class SellpointValueV5Context(SellpointValueV5BaseModel):
    schema_version: Literal["sellpoint_value_v5_context_v1"]
    project_id: str = Field(min_length=1)
    category_code: str = Field(min_length=1)
    v4_context: SellpointValueV4Context
    market_universe: list[SkuEvidenceSnapshot]
    battlefield_taxonomy: list[BattlefieldDefinitionSnapshot]
    method_configs: MethodConfigManifest
    source_authorities: list[SourceAuthority] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    input_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "SellpointValueV5Context":
        if self.project_id != self.v4_context.project_id:
            raise ValueError("V5 and V4 project_id must match")
        if self.category_code != self.v4_context.category_code:
            raise ValueError("V5 and V4 category_code must match")
        codes = [row.identity.sku_code for row in self.market_universe]
        if len(codes) != len(set(codes)):
            raise ValueError("market_universe must be unique by sku_code")
        if self.v4_context.target.sku_code not in set(codes):
            raise ValueError("market_universe must include the target SKU")
        return self


class CounterfactualCandidate(SellpointValueV5BaseModel):
    method: CounterfactualMethod
    question: CounterfactualQuestion
    stage: CandidateStage
    candidate_key: str = Field(min_length=1)
    candidate_sku_codes: list[str] = Field(default_factory=list)
    provenance: str = Field(min_length=1)
    value_tier_relation: Literal["lower", "same", "higher", "unknown"] = "unknown"
    control_dimensions: dict[str, Any]
    common_week_count: int = Field(default=0, ge=0)
    common_platform_count: int = Field(default=0, ge=0)
    observed_price_overlap: float | None = Field(default=None, ge=0.0, le=1.0)
    other_bundle_difference_count: int | None = Field(default=None, ge=0)
    promotion_suspect: bool | None = None
    inventory_status: Literal["unknown", "available", "unavailable"] = "unknown"
    comparability_grade: ComparabilityGrade | None = None
    eligible_measures: list[str] = Field(default_factory=list)
    reject_reasons: list[str]
    sample_manifest_hash: str | None = None
    source_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stage(self) -> "CounterfactualCandidate":
        if len(self.candidate_sku_codes) != len(set(self.candidate_sku_codes)):
            raise ValueError("candidate_sku_codes must be unique")
        if self.stage in {"recalled", "screened", "eligible"} and not self.candidate_sku_codes:
            raise ValueError("non-rejected candidate requires candidate_sku_codes")
        if self.stage == "eligible" and not self.eligible_measures:
            raise ValueError("eligible candidate requires eligible_measures")
        if self.stage == "rejected" and not self.reject_reasons:
            raise ValueError("rejected candidate requires reject_reasons")
        if self.stage != "eligible" and self.eligible_measures:
            raise ValueError("only eligible candidates may expose eligible_measures")
        return self


class CounterfactualSet(SellpointValueV5BaseModel):
    bundle_code: str = Field(min_length=1)
    question: CounterfactualQuestion
    candidates: list[CounterfactualCandidate]
    highest_available_method: CounterfactualMethod | None
    selection_reasons: list[str]
    degradation_reasons: list[str] = Field(default_factory=list)
    set_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_question(self) -> "CounterfactualSet":
        if any(row.question != self.question for row in self.candidates):
            raise ValueError("candidate question must match counterfactual set")
        if self.highest_available_method is not None and not any(
            row.method == self.highest_available_method and row.stage == "eligible"
            for row in self.candidates
        ):
            raise ValueError("highest_available_method must reference an eligible candidate")
        return self


class BalanceMetric(SellpointValueV5BaseModel):
    covariate_code: str = Field(min_length=1)
    before_smd: float | None
    after_smd: float | None
    status: Literal["balanced", "limited", "failed", "unknown"]


class SyntheticDiagnostics(SellpointValueV5BaseModel):
    donor_count: int = Field(ge=0)
    max_weight: float | None = Field(ge=0.0, le=1.0)
    overlap_pass: bool
    balance_pass: bool
    leave_one_sign_consistency: float | None = Field(ge=0.0, le=1.0)
    placebo_percentile: float | None = Field(ge=0.0, le=1.0)
    common_week_count: int = Field(default=0, ge=0)
    common_platform_count: int = Field(default=0, ge=0)
    gate_pass: bool
    failed_gates: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_gate(self) -> "SyntheticDiagnostics":
        if self.gate_pass and self.failed_gates:
            raise ValueError("passed synthetic diagnostics cannot contain failed gates")
        if not self.gate_pass and not self.failed_gates:
            raise ValueError("failed synthetic diagnostics require failed_gates")
        return self


class IntervalEstimate(SellpointValueV5BaseModel):
    estimate: float | None
    low: float | None
    high: float | None
    unit: str = Field(min_length=1)
    observational: bool
    currency: str | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "IntervalEstimate":
        values = (self.estimate, self.low, self.high)
        if any(value is None for value in values):
            if not all(value is None for value in values):
                raise ValueError("interval values must be all present or all null")
            return self
        if not self.low <= self.estimate <= self.high:  # type: ignore[operator]
            raise ValueError("interval estimate must be inside low/high")
        return self


class SyntheticControlResult(SellpointValueV5BaseModel):
    status: MeasureStatus
    target_sku_code: str = Field(min_length=1)
    bundle_code: str = Field(min_length=1)
    donor_weights: dict[str, float]
    effective_donor_count: float | None = Field(default=None, ge=0.0)
    balance: list[BalanceMetric]
    observed_window: dict[str, Any] = Field(default_factory=dict)
    price_difference: IntervalEstimate | None = None
    sales_difference: IntervalEstimate | None = None
    share_difference: IntervalEstimate | None = None
    amount_difference: IntervalEstimate | None = None
    diagnostics: SyntheticDiagnostics
    limitations: list[str] = Field(default_factory=list)
    causal_claim: Literal[False]
    method_config_version: str = Field(min_length=1)
    sample_manifest_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_weights_and_effect(self) -> "SyntheticControlResult":
        if any(weight < 0 or weight > 1 for weight in self.donor_weights.values()):
            raise ValueError("synthetic weights must be between zero and one")
        if self.donor_weights and abs(sum(self.donor_weights.values()) - 1.0) > 1e-6:
            raise ValueError("synthetic weights must sum to one")
        effects = (
            self.price_difference,
            self.sales_difference,
            self.share_difference,
            self.amount_difference,
        )
        if self.status == "available" and not self.diagnostics.gate_pass:
            raise ValueError("available synthetic result requires passed diagnostics")
        if self.status != "available" and any(effect is not None for effect in effects):
            raise ValueError("unavailable synthetic result cannot expose effects")
        return self


class PerformanceArchetype(SellpointValueV5BaseModel):
    role: ArchetypeRole
    metric: Literal["log1p_sales_residual", "choice_share_residual"]
    sku_count: int = Field(ge=0)
    representative_sku_codes: list[str] = Field(default_factory=list)
    bundle_prevalence: dict[str, float]
    user_outcome_prevalence: dict[str, float] = Field(default_factory=dict)
    price_interval: IntervalEstimate | None = None
    volume_interval: IntervalEstimate | None = None
    residual_interval: IntervalEstimate | None = None
    stability: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    causal_claim: Literal[False]
    method_config_version: str = Field(min_length=1)
    sample_manifest_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)


class BundlePriceInterval(SellpointValueV5BaseModel):
    status: MeasureStatus
    method: AmountMethod
    estimate: IntervalEstimate | None
    reference_price: float | None = None
    pair_count: int = Field(ge=0)
    model_family_count: int = Field(ge=0)
    gate_results: dict[str, bool]
    limitations: list[str] = Field(default_factory=list)
    causal_claim: Literal[False]
    psychological_max_price: Literal[False]
    method_config_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_amount(self) -> "BundlePriceInterval":
        if self.status == "available":
            if self.method != "matched_equal_choice_price_gap" or self.estimate is None:
                raise ValueError("available bundle price interval requires matched estimate")
            if self.pair_count < 2 or self.model_family_count < 2:
                raise ValueError("available bundle price interval requires two pairs and families")
            if not self.gate_results or not all(self.gate_results.values()):
                raise ValueError("available bundle price interval requires all gates")
        elif self.estimate is not None or self.reference_price is not None:
            raise ValueError("unavailable bundle price interval cannot expose amount")
        return self


class PriceRealization(SellpointValueV5BaseModel):
    status: MeasureStatus
    current_price: float | None
    market_position: dict[str, Any]
    direct_and_pool_gaps: list[dict[str, Any]] = Field(default_factory=list)
    own_price_curve: dict[str, Any] | None = None
    strict_bundle_interval: BundlePriceInterval | None
    limitations: list[str]


class VolumeRealization(SellpointValueV5BaseModel):
    status: MeasureStatus
    raw_market_position: dict[str, Any]
    controlled_residual: IntervalEstimate | None
    synthetic_difference: IntervalEstimate | None
    choice_association: dict[str, Any] | None = None
    limitations: list[str]


class BattlefieldAllocation(SellpointValueV5BaseModel):
    battlefield_code: str = Field(min_length=1)
    allocated_sales_volume: float | None
    allocated_sales_amount: float | None
    allocation_weight: float | None = Field(ge=0.0, le=1.0)
    incremental: Literal[False]
    source_lineage_hash: str = Field(min_length=1)
    lineage_status: str = Field(min_length=1)


class IncrementDecomposition(SellpointValueV5BaseModel):
    gross_status: MeasureStatus
    cannibalization_status: MeasureStatus
    net_status: MeasureStatus
    gross: IntervalEstimate | None
    cannibalization: IntervalEstimate | None
    net: IntervalEstimate | None
    claim_types: list[IncrementClaimType]
    overlap_risk: Literal["unknown", "low", "medium", "high"] = "unknown"
    limitations: list[str] = Field(default_factory=list)
    causal_claim: Literal[False]

    @model_validator(mode="after")
    def validate_net(self) -> "IncrementDecomposition":
        if self.net is not None and (self.gross is None or self.cannibalization is None):
            raise ValueError("net requires gross and cannibalization")
        status_payloads = (
            (self.gross_status, self.gross, "gross"),
            (self.cannibalization_status, self.cannibalization, "cannibalization"),
            (self.net_status, self.net, "net"),
        )
        for status, payload, name in status_payloads:
            if status == "available" and payload is None:
                raise ValueError(f"available {name} requires an interval")
            if status != "available" and payload is not None:
                raise ValueError(f"unavailable {name} cannot expose an interval")
        return self


class RealizationAccountingInput(SellpointValueV5BaseModel):
    current_price: float | None
    current_sales_volume: float | None
    price_percentile: float | None = Field(ge=0.0, le=1.0)
    volume_percentile: float | None = Field(ge=0.0, le=1.0)
    amount_percentile: float | None = Field(ge=0.0, le=1.0)
    direct_and_pool_gaps: list[dict[str, Any]]
    own_price_curve: dict[str, Any] | None
    controlled_residual: IntervalEstimate | None
    choice_association: dict[str, Any] | None
    synthetic_control: SyntheticControlResult | None
    battlefield_allocations: list[BattlefieldAllocation]
    cannibalization: IntervalEstimate | None
    overlap_risk: Literal["unknown", "low", "medium", "high"]
    strict_market_wtp: MarketImpliedWtp | None
    limitations: list[str] = Field(default_factory=list)


class RealizationAccountingResult(SellpointValueV5BaseModel):
    price: PriceRealization
    volume: VolumeRealization
    battlefield_allocations: list[BattlefieldAllocation]
    increment: IncrementDecomposition
    limitations: list[str]
    result_hash: str = Field(min_length=1)


class ExpansionGap(SellpointValueV5BaseModel):
    gap_code: str = Field(min_length=1)
    change_type: GapChangeType
    mutable_in_scope: bool
    status: Literal["present", "missing", "unknown", "blocking"]
    evidence: list[EvidenceRef]


class ExpansionEligibility(SellpointValueV5BaseModel):
    stage: ExpansionStage
    current_membership: Literal["excluded"]
    immutable_market_gate_pass: bool | None
    task_group_adjacency: float | None = Field(default=None, ge=0.0, le=1.0)
    gaps: list[ExpansionGap]
    donor_count: int = Field(ge=0)
    overlap_risk: Literal["unknown", "low", "medium", "high"] = "unknown"
    eligible: bool
    reasons: list[str]

    @model_validator(mode="after")
    def validate_eligibility(self) -> "ExpansionEligibility":
        if self.eligible != (self.stage == "eligible"):
            raise ValueError("eligible flag must match expansion stage")
        if self.eligible and (
            self.immutable_market_gate_pass is not True
            or self.donor_count < 5
            or any(
                gap.status == "blocking"
                or (
                    gap.status in {"missing", "unknown"}
                    and not gap.mutable_in_scope
                )
                for gap in self.gaps
            )
        ):
            raise ValueError("eligible expansion requires market gate, donors and mutable gaps")
        if not self.eligible and not self.reasons:
            raise ValueError("ineligible expansion requires reasons")
        return self


class BattlefieldPortfolioInput(SellpointValueV5BaseModel):
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = ""
    source_membership: BattlefieldMembership
    user_value_status: ValueStatus
    claim_support: Literal["strong", "weak", "missing", "unknown"]
    capability_status: Literal["complete", "partial", "missing", "unknown"]
    capability_gaps: list[ExpansionGap]
    market_realization_status: MeasureStatus
    role_capped: bool
    immutable_market_gate_pass: bool | None
    product_form_gate_pass: bool | None
    task_group_adjacency: float | None = Field(ge=0.0, le=1.0)
    donor_count: int = Field(ge=0)
    market_space: dict[str, Any]
    current_allocation: BattlefieldAllocation | None
    overlap_risk: Literal["unknown", "low", "medium", "high"]
    lineage_blocking: bool
    source_refs: list[EvidenceRef] = Field(default_factory=list)


class BattlefieldPortfolioOption(SellpointValueV5BaseModel):
    option_type: BattlefieldOptionType
    battlefield_code: str = Field(min_length=1)
    current_membership: BattlefieldMembership
    strengthen_path: StrengthenPath | None = None
    expansion_eligibility: ExpansionEligibility | None = None
    market_space: dict[str, Any]
    current_allocation: BattlefieldAllocation | None = None
    price_reference: PriceRealization | None = None
    volume_reference: VolumeRealization | None = None
    increment: IncrementDecomposition | None = None
    evidence_boundary: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_option(self) -> "BattlefieldPortfolioOption":
        if self.option_type == "expand_excluded":
            if self.current_membership != "excluded" or self.expansion_eligibility is None:
                raise ValueError("expansion option requires excluded membership and eligibility")
            if self.strengthen_path is not None:
                raise ValueError("expansion option cannot contain strengthen_path")
        else:
            if self.current_membership == "excluded" or self.strengthen_path is None:
                raise ValueError("strengthening requires an entered battlefield and path")
            if self.expansion_eligibility is not None:
                raise ValueError("strengthening cannot contain expansion eligibility")
        return self


class ValueHighlight(SellpointValueV5BaseModel):
    highlight_type: HighlightType
    bundle_code: str = Field(min_length=1)
    title_cn: str = Field(min_length=1)
    reason_cn: str = Field(min_length=1)
    comparison_basis_cn: str = Field(min_length=1)
    price_realization_cn: str | None = None
    volume_realization_cn: str | None = None
    evidence_boundary_cn: str = Field(min_length=1)
    internal_rank_components: dict[str, float] = Field(default_factory=dict)


class ValueAccountRow(SellpointValueV5BaseModel):
    battlefield: dict[str, Any]
    perceived_user_value: dict[str, Any]
    sellpoint_bundle: SellpointBundle
    value_status: ValueStatus
    highlight_types: list[HighlightType] = Field(default_factory=list)
    counterfactual_sets: list[CounterfactualSet] = Field(default_factory=list)
    counterfactual_summary_cn: str = Field(min_length=1)
    price_realization: PriceRealization
    volume_realization: VolumeRealization
    battlefield_allocation: BattlefieldAllocation | None = None
    increment: IncrementDecomposition | None = None
    boundary_cn: str = Field(min_length=1)
    confidence_label_cn: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    source_refs: list[EvidenceRef] = Field(default_factory=list)


class PmDecisionSummary(SellpointValueV5BaseModel):
    highlights: list[ValueHighlight] = Field(max_length=3)
    no_highlight_reason_cn: str | None = None
    price_summary_cn: str = Field(min_length=1)
    volume_summary_cn: str = Field(min_length=1)
    existing_battlefield_summary_cn: str = Field(min_length=1)
    expansion_summary_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_highlights(self) -> "PmDecisionSummary":
        if not self.highlights and not self.no_highlight_reason_cn:
            raise ValueError("empty highlights require an explicit reason")
        if self.highlights and self.no_highlight_reason_cn:
            raise ValueError("highlight reason is only valid for an empty list")
        return self


class SkuPerceivedValueMarketRealizationReport(SellpointValueV5BaseModel):
    schema_version: Literal["sellpoint_value_pm_v5_report_v1"]
    target: SkuIdentity
    analysis_state: AnalysisState
    decision_summary: PmDecisionSummary
    value_account_rows: list[ValueAccountRow]
    market_reference: dict[str, Any]
    battlefield_options: list[BattlefieldPortfolioOption]
    overall_boundary_cn: str = Field(min_length=1)
    data_scope_cn: str = Field(min_length=1)
    audit: dict[str, Any]
    result_hash: str = Field(min_length=1)


__all__ = [
    "AmountMethod",
    "AnalysisState",
    "ArchetypeRole",
    "BalanceMetric",
    "BattlefieldAllocation",
    "BattlefieldDefinitionSnapshot",
    "BattlefieldMembership",
    "BattlefieldOptionType",
    "BattlefieldPortfolioInput",
    "BattlefieldPortfolioOption",
    "BundlePriceInterval",
    "CandidateStage",
    "ComparabilityGrade",
    "CounterfactualCandidate",
    "CounterfactualMethod",
    "CounterfactualQuestion",
    "CounterfactualSet",
    "ExpansionEligibility",
    "ExpansionGap",
    "ExpansionStage",
    "GapChangeType",
    "HighlightType",
    "IncrementClaimType",
    "IncrementDecomposition",
    "IntervalEstimate",
    "MeasureStatus",
    "MethodConfigManifest",
    "PerformanceArchetype",
    "PmDecisionSummary",
    "PriceRealization",
    "RealizationAccountingInput",
    "RealizationAccountingResult",
    "SellpointValueV5BaseModel",
    "SellpointValueV5Context",
    "SkuPerceivedValueMarketRealizationReport",
    "StrengthenPath",
    "SyntheticControlResult",
    "SyntheticDiagnostics",
    "ValueAccountRow",
    "ValueHighlight",
    "ValueStatus",
    "VolumeRealization",
]
