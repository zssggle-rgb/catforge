"""Typed read-only context contracts for sellpoint value analysis V4.

The module grows by approved goal: G03 owns observable context and lineage;
G04 adds reason/value/bundle linkage. Counterfactuals, quantification, and
rendering remain outside the G04 boundary.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Availability = Literal["present", "missing"]
Usability = Literal["usable", "limited", "unusable"]
IssueSeverity = Literal["info", "warning", "blocking"]
LineageStatus = Literal["aligned", "stale_revalidated", "stale_conflict", "unresolved"]
AuthorityMode = Literal["published_release", "configured_rule", "fallback"]
ValueStatus = Literal["established", "partial", "not_observed", "conflicted"]
LinkStatus = Literal["supported", "partial", "conflicted", "insufficient"]
BusinessTier = Literal["unknown", "base", "enhanced", "premium", "flagship"]


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
    "ComparablePoolTierFact",
    "EvidenceRef",
    "LineageGate",
    "LineageIssue",
    "MarketCellRow",
    "PurchaseReasonSnapshot",
    "ReasonValueBundleLink",
    "SellpointBundle",
    "SellpointValueV4Context",
    "SkuEvidenceSnapshot",
    "SkuIdentity",
    "SourceAuthority",
    "SourceStatus",
]
