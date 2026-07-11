"""Typed contracts for the read-only sellpoint-value V4 analysis chain.

The module covers observable context, lineage, reason/value/bundle linkage,
counterfactual comparability, market quantification, and the PM report DTO.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Availability = Literal["present", "missing"]
Usability = Literal["usable", "limited", "unusable"]
IssueSeverity = Literal["info", "warning", "blocking"]
LineageStatus = Literal["aligned", "stale_revalidated", "stale_conflict", "unresolved"]
AuthorityMode = Literal["published_release", "configured_rule", "fallback"]
ValueStatus = Literal[
    "established",
    "partial",
    "negative",
    "mixed",
    "not_observed",
]
LinkStatus = Literal["supported", "partial", "conflicted", "insufficient"]
BusinessTier = Literal["unknown", "base", "enhanced", "premium", "flagship"]
QuantificationLevel = Literal[
    "Q0_NOT_OBSERVED",
    "Q1_USER_VALUE_ESTABLISHED",
    "Q2_RELATIVE_EXPERIENCE",
    "Q3_MARKET_CHOICE_ASSOCIATION",
    "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE",
    "Q5_MARKET_IMPLIED_WTP",
]
CounterfactualRole = Literal["base_value", "same_value", "stretch_benchmark"]
CandidateProvenance = Literal[
    "M14", "competitor_set_fallback", "M12C_pool", "same_family_search"
]
IsolationGrade = Literal["A", "B", "C", "unusable"]
ProductRole = Literal[
    "core_differentiated_value",
    "basic_threshold",
    "supporting_choice_value",
    "customer_captured_value",
    "configuration_support",
    "price_pressure",
    "undetermined",
]
MonetizationStatus = Literal[
    "not_measured",
    "choice_supported",
    "whole_product_only",
    "partially_captured",
    "fully_captured",
    "over_captured",
    "unidentifiable",
]
WtpMethod = Literal["none", "matched_equal_choice_price_gap"]
AnalysisStatus = Literal["ready", "partial", "blocked"]


class SellpointValueV4BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class EvidenceRef(SellpointValueV4BaseModel):
    module_code: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    batch_id: str | None = None
    rule_version: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class SourceAuthority(SellpointValueV4BaseModel):
    module_code: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    authority_mode: AuthorityMode
    rule_version: str | None = None
    schema_version: str | None = None
    taxonomy_version: str | None = None
    release_id: str | None = None
    selected_batch_ids: list[str]
    row_count: int = Field(ge=0)
    availability: Availability
    usability: Usability
    source_hash: str | None = None
    selected_reason: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_availability(self) -> "SourceAuthority":
        if self.availability == "missing":
            if self.row_count != 0 or self.selected_batch_ids:
                raise ValueError("missing authority cannot contain selected rows")
            if self.usability == "usable":
                raise ValueError("missing authority cannot be usable")
        elif self.row_count == 0:
            raise ValueError("present authority requires row_count > 0")
        return self


class SourceStatus(SellpointValueV4BaseModel):
    availability: Availability
    usability: Usability
    issue_codes: list[str] = Field(default_factory=list)


class LineageIssue(SellpointValueV4BaseModel):
    code: str = Field(min_length=1)
    severity: IssueSeverity
    scope: Literal["source", "relation", "bundle", "quantification", "report"]
    message_cn: str = Field(min_length=1)
    affected_module_codes: list[str] = Field(default_factory=list)
    affected_reason_codes: list[str] = Field(default_factory=list)
    affected_bundle_codes: list[str] = Field(default_factory=list)
    source_refs: list[EvidenceRef] = Field(default_factory=list)


class LineageGate(SellpointValueV4BaseModel):
    status: LineageStatus
    published_lineage: list[SourceAuthority]
    current_validation_lineage: list[SourceAuthority]
    issues: list[LineageIssue] = Field(default_factory=list)
    blocked_reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> "LineageGate":
        issue_codes = {issue.code for issue in self.issues}
        if (
            self.status == "stale_conflict"
            and "version_lineage_conflict" not in issue_codes
        ):
            raise ValueError("stale_conflict requires version_lineage_conflict")
        if self.status == "unresolved" and not self.issues:
            raise ValueError("unresolved lineage requires an explicit issue")
        return self


class SkuIdentity(SellpointValueV4BaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    product_category: str = Field(min_length=1)
    screen_size_inch: float | None = None
    size_tier: str | None = None
    price_band: str | None = None


class MarketCellRow(SellpointValueV4BaseModel):
    sku_code: str = Field(min_length=1)
    battlefield_code: str
    period_week_index: int
    platform_type: str
    channel_type: str | None = None
    avg_price: float | None = None
    sales_volume: float | None = None
    sales_amount: float | None = None
    battlefield_allocation_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    value_bundle_tiers: dict[str, str] = Field(default_factory=dict)
    other_bundle_tiers: dict[str, str] = Field(default_factory=dict)
    brand_name: str | None = None
    series_name: str | None = None
    price_check_status: str = Field(min_length=1)
    promotion_suspect: bool
    inventory_status: Literal["unavailable"]
    quality_flags: list[str] = Field(default_factory=list)
    source_ref: EvidenceRef | None = None


class SkuEvidenceSnapshot(SellpointValueV4BaseModel):
    identity: SkuIdentity
    source_status: dict[str, SourceStatus]
    facts: dict[str, Any]
    comment_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    market: dict[str, Any]
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    target_groups: list[dict[str, Any]] = Field(default_factory=list)
    battlefields: list[dict[str, Any]] = Field(default_factory=list)
    semantic_market: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[EvidenceRef]
    snapshot_hash: str = Field(min_length=1)


class PurchaseReasonSnapshot(SellpointValueV4BaseModel):
    found: bool
    lineage_status: LineageStatus
    profile_version: str | None
    release_id: str | None = None
    anchors: list[dict[str, Any]]
    review_required: bool = False
    source_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_found(self) -> "PurchaseReasonSnapshot":
        if not self.found and (self.profile_version or self.anchors):
            raise ValueError("missing purchase reason profile cannot contain anchors")
        return self


class ComparablePoolTierFact(SellpointValueV4BaseModel):
    claim_code: str = Field(min_length=1)
    bundle_code: str = Field(min_length=1)
    context_code: str = Field(min_length=1)
    comparison_basis: str = Field(default="claim_presence", min_length=1)
    comparison_param_code: str | None = None
    pool_sku_count: int = Field(ge=0)
    with_count: int = Field(ge=0)
    without_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    sample_status: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)
    pool_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "ComparablePoolTierFact":
        if (
            self.with_count + self.without_count + self.unknown_count
            > self.pool_sku_count
        ):
            raise ValueError("pool counts cannot exceed pool_sku_count")
        return self


class BundleMember(SellpointValueV4BaseModel):
    capability_code: str = Field(min_length=1)
    capability_name_cn: str = Field(min_length=1)
    fact_status: Literal["confirmed", "partial", "conflict", "unknown"]
    business_tier: BusinessTier
    fact_summary_cn: str = ""
    user_result_support: str = "not_observed"
    source_refs: list[EvidenceRef] = Field(default_factory=list)


class SellpointBundle(SellpointValueV4BaseModel):
    bundle_code: str = Field(min_length=1)
    bundle_name_cn: str = Field(min_length=1)
    bundle_family: str = Field(min_length=1)
    business_tier: BusinessTier
    members: list[BundleMember]
    collinearity_group: str | None = None
    independently_identifiable: bool = False
    limitations: list[str] = Field(default_factory=list)


class ReasonValueBundleLink(SellpointValueV4BaseModel):
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = ""
    battlefield_market_space: dict[str, Any] | None = None
    purchase_reason_code: str = Field(min_length=1)
    purchase_reason_name_cn: str = ""
    purchase_reason_family: str | None = None
    purchase_reason_source_status: LineageStatus = "unresolved"
    realized_value_code: str = Field(min_length=1)
    realized_value_name_cn: str = ""
    scenario_cn: str = ""
    outcome_cn: str = ""
    bundle: SellpointBundle
    link_status: LinkStatus
    value_status: ValueStatus
    evidence_domains: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_refs: list[EvidenceRef] = Field(default_factory=list)
    relation_hash: str = Field(min_length=1)


class ComparabilityAssessment(SellpointValueV4BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    role: CounterfactualRole
    provenance: CandidateProvenance
    isolation_grade: IsolationGrade
    exact_size_match: bool = False
    battlefield_overlap: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_overlap: float = Field(default=0.0, ge=0.0, le=1.0)
    value_tier_relation: Literal["lower", "same", "higher", "unknown"] = "unknown"
    common_cell_count: int = Field(default=0, ge=0)
    common_week_count: int = Field(default=0, ge=0)
    price_overlap: bool = False
    other_bundle_difference_count: int = Field(default=0, ge=0)
    promotion_clean_cell_count: int = Field(default=0, ge=0)
    inventory_status: Literal["unavailable"] = "unavailable"
    comment_comparable: bool = False
    eligible: bool
    eligible_quantification_levels: list[QuantificationLevel]
    reject_reasons: list[str] = Field(default_factory=list)
    assessment_hash: str = ""


class ChoiceAssociation(SellpointValueV4BaseModel):
    status: Literal["available", "insufficient", "unstable"]
    method: Literal["pair_curve_same_price", "near_same_price", "none"]
    same_price_choice_share: float | None = Field(default=None, ge=0.0, le=1.0)
    choice_difference_pp: float | None = None
    pair_count: int = Field(ge=0)
    cell_count: int = Field(ge=0)
    week_count: int = Field(ge=0)
    observed_price_gap_range: list[float] = Field(default_factory=list)
    direction_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_available(self) -> "ChoiceAssociation":
        if self.status == "available" and (
            self.method == "none" or self.same_price_choice_share is None
        ):
            raise ValueError("available choice association requires an observed share")
        if (
            self.same_price_choice_share is not None
            and self.choice_difference_pp is None
        ):
            raise ValueError("choice share requires choice_difference_pp")
        return self


class MarketImpliedWtp(SellpointValueV4BaseModel):
    status: Literal["available", "insufficient", "unstable", "blocked"]
    method: WtpMethod
    method_config_version: Literal["sellpoint_value_pm_v4_matched_wtp_config_v2"]
    estimate_low: float | None = None
    estimate_high: float | None = None
    reference_price: float | None = None
    currency: str = "CNY"
    pair_count: int = Field(ge=0)
    model_family_count: int = Field(ge=0)
    cell_count: int = Field(default=0, ge=0)
    week_count: int = Field(default=0, ge=0)
    observed_price_range: list[float] = Field(default_factory=list)
    observed_value_tiers: list[BusinessTier] = Field(default_factory=list)
    sensitivity_summary: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    exclusion_reasons: list[str] = Field(default_factory=list)
    causal_claim: Literal[False]
    psychological_max_price: Literal[False]

    @model_validator(mode="after")
    def validate_amount_boundary(self) -> "MarketImpliedWtp":
        amounts = (self.estimate_low, self.estimate_high, self.reference_price)
        if self.status == "available":
            if (
                self.method != "matched_equal_choice_price_gap"
                or any(value is None for value in amounts)
                or self.pair_count < 2
                or self.model_family_count < 2
            ):
                raise ValueError(
                    "available WTP requires two pairs, two families, and amounts"
                )
            if self.estimate_low > self.estimate_high:  # type: ignore[operator]
                raise ValueError("WTP estimate_low cannot exceed estimate_high")
            required_sensitivity = {
                "leave_one_week_out",
                "cluster_week_bootstrap",
                "joint_crossing_stability",
                "pair_quality_weights",
                "weighted_median_center",
                "conservative_interval_components",
            }
            if not required_sensitivity <= set(self.sensitivity_summary):
                raise ValueError(
                    "available WTP requires v2 bootstrap and conservative interval evidence"
                )
            bootstrap = self.sensitivity_summary["cluster_week_bootstrap"]
            joint = self.sensitivity_summary["joint_crossing_stability"]
            if (
                len(bootstrap) < 2
                or not all(item.get("stable") is True for item in bootstrap.values())
                or len(joint) < 2
                or not all(item.get("stable") is True for item in joint.values())
            ):
                raise ValueError("available WTP requires two stable bootstrap pairs")
            center = self.sensitivity_summary["weighted_median_center"]
            if not isinstance(center, (int, float)) or not (
                self.estimate_low <= center <= self.estimate_high  # type: ignore[operator]
            ):
                raise ValueError("WTP interval must contain the weighted median center")
        elif any(value is not None for value in amounts):
            raise ValueError("unavailable WTP cannot expose amount fields")
        return self


class QuantificationResult(SellpointValueV4BaseModel):
    level: QuantificationLevel
    value_status: ValueStatus
    product_role: ProductRole
    monetization_status: MonetizationStatus
    relative_experience: dict[str, Any] | None = None
    choice_association: ChoiceAssociation | None = None
    whole_product_price_acceptance: dict[str, Any] | None = None
    wtp: MarketImpliedWtp
    gate_results: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_monotonic_level(self) -> "QuantificationResult":
        rank = {
            "Q0_NOT_OBSERVED": 0,
            "Q1_USER_VALUE_ESTABLISHED": 1,
            "Q2_RELATIVE_EXPERIENCE": 2,
            "Q3_MARKET_CHOICE_ASSOCIATION": 3,
            "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE": 4,
            "Q5_MARKET_IMPLIED_WTP": 5,
        }[self.level]
        if rank >= 1 and self.value_status not in {"established", "partial"}:
            raise ValueError("Q1+ requires established or partial user value")
        if rank >= 2 and self.relative_experience is None:
            raise ValueError("Q2+ requires relative_experience")
        if rank >= 3 and (
            self.choice_association is None
            or self.choice_association.status != "available"
        ):
            raise ValueError("Q3+ requires available choice association")
        if rank >= 4 and (
            self.whole_product_price_acceptance is None
            or self.whole_product_price_acceptance.get("status") != "available"
        ):
            raise ValueError("Q4+ requires available whole-product price acceptance")
        if rank == 5 and self.wtp.status != "available":
            raise ValueError("Q5 requires available WTP")
        if rank < 5 and (
            self.wtp.estimate_low is not None or self.wtp.estimate_high is not None
        ):
            raise ValueError("Q0-Q4 cannot expose WTP amounts")
        return self


class ProductValueStructureRow(SellpointValueV4BaseModel):
    battlefield: dict[str, Any]
    purchase_reason: dict[str, Any]
    realized_user_value: dict[str, Any]
    sellpoint_bundle: dict[str, Any]
    counterfactual_result: dict[str, Any]
    selection_price_realization: QuantificationResult
    product_role: ProductRole
    confidence_label_cn: str = ""
    drilldown: dict[str, Any] = Field(default_factory=dict)


class SkuProductValueRealizationReport(SellpointValueV4BaseModel):
    schema_version: Literal["sellpoint_value_pm_v4_result_v1"]
    analysis_status: AnalysisStatus
    target: SkuIdentity
    headline_cn: str = Field(min_length=1)
    value_structure_rows: list[ProductValueStructureRow]
    overall_quantification_boundary: dict[str, Any]
    data_scope_note_cn: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    qa_appendix: dict[str, Any] = Field(default_factory=dict)
    input_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)


class SellpointValueV4Context(SellpointValueV4BaseModel):
    schema_version: Literal["sellpoint_value_v4_context_v1"]
    project_id: str = Field(min_length=1)
    category_code: str = Field(min_length=1)
    requested_batch_id: str = Field(min_length=1)
    serving_batch_ids: list[str] = Field(min_length=1)
    market_window: str = Field(min_length=1)
    target: SkuIdentity
    authority_manifest: list[SourceAuthority]
    lineage_gate: LineageGate
    target_snapshot: SkuEvidenceSnapshot
    purchase_reason_profile: PurchaseReasonSnapshot
    candidate_snapshots: list[SkuEvidenceSnapshot] = Field(max_length=12)
    market_cells: list[MarketCellRow] = Field(max_length=2000)
    m12c_pool_tiers: list[ComparablePoolTierFact]
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    input_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity_and_scope(self) -> "SellpointValueV4Context":
        if self.target.sku_code != self.target_snapshot.identity.sku_code:
            raise ValueError("target and target_snapshot identity must match")
        if self.category_code != self.target.product_category:
            raise ValueError("category_code and target product_category must match")
        candidate_codes = [item.identity.sku_code for item in self.candidate_snapshots]
        if self.target.sku_code in candidate_codes:
            raise ValueError("target cannot appear in candidate_snapshots")
        if len(candidate_codes) != len(set(candidate_codes)):
            raise ValueError("candidate_snapshots must be unique by sku_code")
        return self


__all__ = [
    "BundleMember",
    "ComparabilityAssessment",
    "ChoiceAssociation",
    "ComparablePoolTierFact",
    "EvidenceRef",
    "LineageGate",
    "LineageIssue",
    "MarketImpliedWtp",
    "MarketCellRow",
    "PurchaseReasonSnapshot",
    "ProductValueStructureRow",
    "QuantificationResult",
    "ReasonValueBundleLink",
    "SellpointBundle",
    "SellpointValueV4Context",
    "SkuEvidenceSnapshot",
    "SkuIdentity",
    "SkuProductValueRealizationReport",
    "SourceAuthority",
    "SourceStatus",
]
