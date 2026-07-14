"""Typed purchase-pool and battlefield-overlap contracts for competitor profiles."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairFeatureBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceRef,
    PurchasePoolAssessment,
)


COMPETITOR_PROFILE_PURCHASE_POOL_SCHEMA_VERSION = "competitor_profile_purchase_pool_v1"
PURCHASE_POOL_GATE_CODES = (
    "budget_reachability",
    "category_product_form_compatibility",
    "size_capacity_task_substitutability",
    "task_value_scene_overlap",
)
POSITIVE_BATTLEFIELD_ROLES = (
    "opportunity",
    "primary",
    "secondary",
    "user_observed",
)


class PurchasePoolSemanticConfig(CompetitorProfileBaseModel):
    config_version: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    same_budget_max_gap_ratio: Decimal = Field(ge=0, le=1)
    adjacent_budget_max_gap_ratio: Decimal = Field(ge=0, le=2)
    generic_coverage_threshold: Decimal = Field(ge=0, le=1)
    generic_value_codes: list[str] = Field(default_factory=list)
    table_stake_value_codes: list[str] = Field(default_factory=list)
    discriminative_value_codes: list[str] = Field(default_factory=list)
    value_coverage_ratios: dict[str, Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self) -> "PurchasePoolSemanticConfig":
        if self.same_budget_max_gap_ratio > self.adjacent_budget_max_gap_ratio:
            raise ValueError("same-budget threshold cannot exceed adjacent-budget")
        for field_name in (
            "generic_value_codes",
            "table_stake_value_codes",
            "discriminative_value_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        taxonomy_sets = [
            set(self.generic_value_codes),
            set(self.table_stake_value_codes),
            set(self.discriminative_value_codes),
        ]
        if any(
            taxonomy_sets[left] & taxonomy_sets[right]
            for left in range(len(taxonomy_sets))
            for right in range(left + 1, len(taxonomy_sets))
        ):
            raise ValueError("value taxonomy classifications cannot overlap")
        if list(self.value_coverage_ratios) != sorted(self.value_coverage_ratios):
            raise ValueError("value coverage ratios must be sorted by code")
        return self


class BattlefieldCodeAssessment(CompetitorProfileBaseModel):
    battlefield_code: str = Field(min_length=1)
    target_roles: list[
        Literal["primary", "secondary", "opportunity", "user_observed", "drag"]
    ] = Field(default_factory=list)
    candidate_roles: list[
        Literal["primary", "secondary", "opportunity", "user_observed", "drag"]
    ] = Field(default_factory=list)
    classification: Literal[
        "discriminative",
        "supporting",
        "generic",
        "table_stake",
    ]
    classification_reason_code: str = Field(min_length=1)
    coverage_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    overlap_type: Literal[
        "shared_primary",
        "shared_current",
        "shared_opportunity",
        "target_opportunity_candidate_current",
        "candidate_opportunity_target_current",
        "shared_drag",
        "target_drag",
        "candidate_drag",
        "role_conflict",
        "target_only",
        "candidate_only",
    ]
    positive_overlap: bool
    supports_purchase_pool_overlap: bool
    explicit_drag: bool
    review_required: bool = False
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "BattlefieldCodeAssessment":
        for field_name in ("target_roles", "candidate_roles"):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        has_drag = "drag" in self.target_roles or "drag" in self.candidate_roles
        if self.explicit_drag != has_drag:
            raise ValueError("drag must come from an explicit upstream role")
        if self.supports_purchase_pool_overlap and (
            not self.positive_overlap or self.classification != "discriminative"
        ):
            raise ValueError(
                "purchase-pool value support requires positive discriminative overlap"
            )
        _assert_evidence_order(self.evidence_refs)
        return self


class BattlefieldOverlapSummary(CompetitorProfileBaseModel):
    assessments: list[BattlefieldCodeAssessment]
    target_primary_codes: list[str] = Field(default_factory=list)
    candidate_primary_codes: list[str] = Field(default_factory=list)
    shared_positive_codes: list[str] = Field(default_factory=list)
    shared_discriminative_codes: list[str] = Field(default_factory=list)
    supporting_or_generic_codes: list[str] = Field(default_factory=list)
    target_drag_codes: list[str] = Field(default_factory=list)
    candidate_drag_codes: list[str] = Field(default_factory=list)
    value_route_status: Literal["same", "different", "unknown"]
    review_required: bool = False
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_summary(self) -> "BattlefieldOverlapSummary":
        codes = [row.battlefield_code for row in self.assessments]
        if codes != sorted(set(codes)):
            raise ValueError("battlefield assessments must be sorted and unique")
        for field_name in (
            "target_primary_codes",
            "candidate_primary_codes",
            "shared_positive_codes",
            "shared_discriminative_codes",
            "supporting_or_generic_codes",
            "target_drag_codes",
            "candidate_drag_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        expected_discriminative = sorted(
            row.battlefield_code
            for row in self.assessments
            if row.supports_purchase_pool_overlap
        )
        if self.shared_discriminative_codes != expected_discriminative:
            raise ValueError("shared discriminative codes conflict with assessments")
        _assert_evidence_order(self.evidence_refs)
        return self


class PurchasePoolSemanticPairAssessment(CompetitorProfileBaseModel):
    target: CandidateIdentity
    candidate: CandidateIdentity
    candidate_status: Literal[
        "recalled_only",
        "reference_only",
        "review_required",
        "blocked",
    ]
    purchase_pool: PurchasePoolAssessment
    battlefield_overlap: BattlefieldOverlapSummary
    shared_primary_task_codes: list[str] = Field(default_factory=list)
    shared_task_codes: list[str] = Field(default_factory=list)
    budget_band: Literal["same", "adjacent", "outside", "unknown"]
    same_product_form: bool | None = None
    same_size_or_capacity_segment: bool | None = None
    review_required: bool = False
    review_reason_codes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    relation_status: Literal["not_evaluated"] = "not_evaluated"
    value_substitution_status: Literal["not_evaluated"] = "not_evaluated"
    price_volume_pressure_status: Literal["not_evaluated"] = "not_evaluated"
    competitor_member: Literal[False] = False
    pair_feature_result_hash: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "PurchasePoolSemanticPairAssessment":
        if self.target.sku_code == self.candidate.sku_code:
            raise ValueError("purchase-pool target and candidate must differ")
        gate_codes = [row.gate_code for row in self.purchase_pool.gate_results]
        if gate_codes != list(PURCHASE_POOL_GATE_CODES):
            raise ValueError("purchase pool must contain the four required gates")
        for field_name in (
            "shared_primary_task_codes",
            "shared_task_codes",
            "review_reason_codes",
            "limitations",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        _assert_evidence_order(self.evidence_refs)
        return self


class PurchasePoolSemanticBundle(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_purchase_pool_v1"] = (
        COMPETITOR_PROFILE_PURCHASE_POOL_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target: CandidateIdentity
    candidate_count: int = Field(ge=0)
    pairs: list[PurchasePoolSemanticPairAssessment]
    config: PurchasePoolSemanticConfig
    pair_feature_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> "PurchasePoolSemanticBundle":
        if self.category_code != self.product_category:
            raise ValueError("purchase-pool category and product category must match")
        if self.config.product_category != self.product_category:
            raise ValueError("purchase-pool config category must match bundle")
        if self.target.product_category != self.product_category:
            raise ValueError("purchase-pool target category must match bundle")
        candidate_codes = [row.candidate.sku_code for row in self.pairs]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("purchase-pool candidates must be sorted and unique")
        if self.candidate_count != len(self.pairs):
            raise ValueError("purchase-pool candidate count must match pairs")
        if any(row.target != self.target for row in self.pairs):
            raise ValueError("purchase-pool target must be consistent")
        return self


def assert_pair_feature_category(
    bundle: PairFeatureBundle,
    config: PurchasePoolSemanticConfig,
) -> None:
    if bundle.product_category != config.product_category:
        raise ValueError("pair feature and purchase-pool config categories must match")


def _assert_evidence_order(values: list[EvidenceRef]) -> None:
    keys = [
        (
            row.module_code,
            row.source_batch_id or "",
            row.record_type,
            row.record_id,
            row.result_hash,
        )
        for row in values
    ]
    if keys != sorted(set(keys)):
        raise ValueError("purchase-pool evidence refs must be sorted and unique")


__all__ = [
    "COMPETITOR_PROFILE_PURCHASE_POOL_SCHEMA_VERSION",
    "POSITIVE_BATTLEFIELD_ROLES",
    "PURCHASE_POOL_GATE_CODES",
    "BattlefieldCodeAssessment",
    "BattlefieldOverlapSummary",
    "PurchasePoolSemanticBundle",
    "PurchasePoolSemanticConfig",
    "PurchasePoolSemanticPairAssessment",
    "assert_pair_feature_category",
]
