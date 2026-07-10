"""Typed contracts for the product-manager sellpoint value analysis."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClaimValuePmBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimValuePmMarketWeeklyRow(ClaimValuePmBaseModel):
    sku_code: str = Field(min_length=1)
    period_week_index: int
    period_raw: str | None = None
    platform_type: str = "unknown"
    channel_type: str | None = None
    sales_volume: float | None = None
    sales_amount: float | None = None
    avg_price: float | None = None
    price_check_status: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimValuePmCommentAtom(ClaimValuePmBaseModel):
    source_comment_key: str = Field(min_length=1)
    source_comment_id: str | None = None
    sentence_seq: int | None = None
    clean_comment_text: str = Field(min_length=1)
    dimension_code: str
    subdimension_code: str
    dimension_type: str
    polarity: str
    support_relation: str
    supported_param_codes: list[str] = Field(default_factory=list)
    contradicted_param_codes: list[str] = Field(default_factory=list)
    supported_claim_codes: list[str] = Field(default_factory=list)
    contradicted_claim_codes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ClaimValuePmCompetitorSnapshot(ClaimValuePmBaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    selection_rank: int | None = None
    slot_code: str | None = None
    slot_name_cn: str | None = None
    selection_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_completeness_score: float | None = Field(default=None, ge=0.0, le=1.0)
    selection_source: str
    selection_evidence_ids: list[str] = Field(default_factory=list)
    fact_brief: dict[str, Any] = Field(default_factory=dict)
    comment_atoms: list[ClaimValuePmCommentAtom] = Field(default_factory=list)
    market_weekly_rows: list[ClaimValuePmMarketWeeklyRow] = Field(default_factory=list)


class ClaimValuePmContext(ClaimValuePmBaseModel):
    schema_version: Literal["sellpoint_value_pm_context_v1"] = "sellpoint_value_pm_context_v1"
    project_id: str = Field(min_length=1)
    category_code: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    product_category: str = Field(min_length=1)
    market_window: str = Field(min_length=1)
    target: dict[str, Any]
    fact_brief: dict[str, Any]
    comment_atoms: list[ClaimValuePmCommentAtom] = Field(default_factory=list)
    market_weekly_rows: list[ClaimValuePmMarketWeeklyRow] = Field(default_factory=list)
    competitor_source: str = "none"
    competitor_selection_batch_id: str | None = None
    competitors: list[ClaimValuePmCompetitorSnapshot] = Field(default_factory=list)
    purchase_reason_hypothesis: dict[str, Any] = Field(default_factory=dict)
    source_versions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimValuePmDataIssue(ClaimValuePmBaseModel):
    code: str
    severity: Literal["warning", "blocking"]
    scope: Literal["product_fact", "user_evidence", "market", "competitor", "general"] = "general"
    message_cn: str
    source_modules: list[str] = Field(default_factory=list)
    affected_unit_codes: list[str] = Field(default_factory=list)


class ClaimValuePmDataGate(ClaimValuePmBaseModel):
    status: Literal["ready", "partial", "blocked"]
    status_cn: str
    issues: list[ClaimValuePmDataIssue] = Field(default_factory=list)
    available_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    review_required: bool = False


class ClaimValuePmUserUnderstanding(ClaimValuePmBaseModel):
    status: Literal["direct", "outcome_only", "unrecognized", "negative", "mixed", "insufficient"]
    status_cn: str
    eligible_sentence_count: int = Field(default=0, ge=0)
    direct_sentence_count: int = Field(default=0, ge=0)
    indirect_sentence_count: int = Field(default=0, ge=0)
    unattributable_sentence_count: int = Field(default=0, ge=0)
    negative_sentence_count: int = Field(default=0, ge=0)
    direct_choice_sentence_count: int = Field(default=0, ge=0)
    perception_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    positive_examples: list[dict[str, Any]] = Field(default_factory=list)
    negative_examples: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimValuePmCompetitorComparison(ClaimValuePmBaseModel):
    sku_code: str
    display_name: str
    selection_role_cn: str | None = None
    fact_relation: Literal["target_stronger", "competitor_stronger", "different", "similar", "unknown"]
    target_fact_cn: str
    competitor_fact_cn: str
    competitor_user_status_cn: str
    market_position_cn: str
    isolation_grade: Literal["A", "B", "C", "unknown"] = "unknown"


class ClaimValuePmWeights(ClaimValuePmBaseModel):
    product_fact_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    user_perception_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    pricing_readiness: Literal["single_test", "bundle_test", "not_ready", "insufficient"]
    pricing_readiness_cn: str


class ClaimValuePmPurchaseRole(ClaimValuePmBaseModel):
    status: Literal[
        "direct_reason",
        "entry_requirement_hypothesis",
        "post_purchase_satisfaction",
        "experience_bonus",
        "drag",
        "mixed_experience",
        "not_proven",
    ]
    status_cn: str
    basis_cn: str


class ClaimValuePmValueUnit(ClaimValuePmBaseModel):
    unit_code: str
    unit_name_cn: str
    unit_type: Literal["experience_bundle", "independent_capability"] = "experience_bundle"
    product_claim_cn: str
    linked_param_codes: list[str] = Field(default_factory=list)
    linked_claim_codes: list[str] = Field(default_factory=list)
    product_fact_status: Literal["confirmed", "partial", "conflict", "unknown"]
    product_fact_status_cn: str
    product_fact_items: list[str] = Field(default_factory=list)
    user_understanding: ClaimValuePmUserUnderstanding
    purchase_role: ClaimValuePmPurchaseRole
    weights: ClaimValuePmWeights
    evidence_stage: Literal["E0", "E1", "E2", "E3", "E4"]
    competitor_comparison: list[ClaimValuePmCompetitorComparison] = Field(default_factory=list)
    decision_code: str
    decision_cn: str
    next_validation_cn: str
    limitations: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimValuePmCurvePoint(ClaimValuePmBaseModel):
    relative_price_gap: float
    relative_price_gap_min: float | None = None
    relative_price_gap_max: float | None = None
    target_choice_share: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0)


class ClaimValuePmPairCurve(ClaimValuePmBaseModel):
    competitor_sku_code: str
    competitor_name: str
    exact_size_match: bool = False
    configuration_isolation_grade: Literal["A", "B", "C", "unknown"] = "unknown"
    sample_level: Literal["strong", "medium", "weak", "insufficient"]
    valid_cell_count: int = Field(default=0, ge=0)
    distinct_week_count: int = Field(default=0, ge=0)
    price_gap_bin_count: int = Field(default=0, ge=0)
    observed_gap_min: float | None = None
    observed_gap_max: float | None = None
    observed_price_gap_bins: list[float] = Field(default_factory=list)
    same_price_share: float | None = Field(default=None, ge=0.0, le=1.0)
    same_price_method: str | None = None
    same_price_advantage_pp: float | None = None
    hold_gap_ratio: float | None = None
    hold_gap_amount: float | None = None
    hold_gap_lower_bound_ratio: float | None = None
    target_reference_price: float | None = None
    competitor_reference_price: float | None = None
    curve_points: list[ClaimValuePmCurvePoint] = Field(default_factory=list)
    selection_weight: float = Field(default=0.0, ge=0.0)
    limitations: list[str] = Field(default_factory=list)


class ClaimValuePmPriceScenario(ClaimValuePmBaseModel):
    label_cn: str
    price: float | None = None
    price_change_pct: float
    pair_count: int = Field(default=0, ge=0)
    weight_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    comparison_choice_share: float | None = Field(default=None, ge=0.0, le=1.0)
    choice_index: float | None = Field(default=None, ge=0.0)
    comparison_revenue_index: float | None = Field(default=None, ge=0.0)
    status_cn: str


class ClaimValuePmMarketPricing(ClaimValuePmBaseModel):
    method_level: Literal["L0", "L1", "L2", "L3"]
    method_name_cn: str
    attribution_status: Literal["whole_product_only", "bundle_directional", "not_available"]
    attribution_status_cn: str
    current_price: float | None = None
    valid_pair_count: int = Field(default=0, ge=0)
    strong_pair_count: int = Field(default=0, ge=0)
    direction_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    same_price_choice_share: float | None = Field(default=None, ge=0.0, le=1.0)
    same_price_choice_advantage_pp: float | None = None
    same_price_competitor_interval_pp: list[float] = Field(default_factory=list)
    selection_holding_gap_amount_range: list[float] = Field(default_factory=list)
    selection_holding_gap_ratio_range: list[float] = Field(default_factory=list)
    holding_gap_status_cn: str
    current_price_acceptance_status: Literal[
        "room_remaining",
        "mostly_captured",
        "over_captured",
        "no_observed_advantage",
        "insufficient",
    ] = "insufficient"
    current_price_acceptance_status_cn: str = "无法判断"
    current_price_acceptance_basis_cn: str = "当前样本不足，不能判断价格是否已经消耗整机优势。"
    pair_curves: list[ClaimValuePmPairCurve] = Field(default_factory=list)
    price_scenarios: list[ClaimValuePmPriceScenario] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClaimValuePmAction(ClaimValuePmBaseModel):
    priority: int = Field(ge=1)
    action_type: str
    action_cn: str
    why_cn: str
    success_signal_cn: str


class ClaimValuePmAnalysis(ClaimValuePmBaseModel):
    schema_version: Literal["sellpoint_value_pm_v1"] = "sellpoint_value_pm_v1"
    analysis_status: Literal["ready", "partial", "blocked"]
    target: dict[str, Any]
    data_gate: ClaimValuePmDataGate
    headline_cn: str
    decision_summary: list[ClaimValuePmAction] = Field(default_factory=list)
    value_units: list[ClaimValuePmValueUnit] = Field(default_factory=list)
    market_pricing: ClaimValuePmMarketPricing
    competitor_boundary: dict[str, Any] = Field(default_factory=dict)
    test_backlog: list[ClaimValuePmAction] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
