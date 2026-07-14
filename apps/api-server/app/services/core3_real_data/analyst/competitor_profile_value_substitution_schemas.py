"""Typed evidence contracts for purchase-reason and value substitution."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceRef,
)


COMPETITOR_PROFILE_VALUE_SUBSTITUTION_SCHEMA_VERSION = (
    "competitor_profile_value_substitution_v1"
)
VALUE_LAYER_CODES = (
    "F1_purchase_reason",
    "F4_claim_value",
    "F4_user_realization",
    "F5_claim_expression",
    "F5_parameter",
)


class ValueSubstitutionConfig(CompetitorProfileBaseModel):
    config_version: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    generic_coverage_threshold: Decimal = Field(ge=0, le=1)
    generic_value_codes: list[str] = Field(default_factory=list)
    table_stake_value_codes: list[str] = Field(default_factory=list)
    discriminative_value_codes: list[str] = Field(default_factory=list)
    value_coverage_ratios: dict[str, Decimal] = Field(default_factory=dict)
    m12d_strong_roles: list[str] = Field(min_length=1)
    m12d_supporting_roles: list[str] = Field(min_length=1)
    m12d_weak_roles: list[str] = Field(min_length=1)
    m12d_risk_roles: list[str] = Field(min_length=1)
    m12c_positive_roles: list[str] = Field(min_length=1)
    m12c_supporting_roles: list[str] = Field(min_length=1)
    m12c_opportunity_roles: list[str] = Field(min_length=1)
    m12c_risk_roles: list[str] = Field(min_length=1)
    m12c_unknown_roles: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_config(self) -> "ValueSubstitutionConfig":
        ordered_fields = (
            "generic_value_codes",
            "table_stake_value_codes",
            "discriminative_value_codes",
            "m12d_strong_roles",
            "m12d_supporting_roles",
            "m12d_weak_roles",
            "m12d_risk_roles",
            "m12c_positive_roles",
            "m12c_supporting_roles",
            "m12c_opportunity_roles",
            "m12c_risk_roles",
            "m12c_unknown_roles",
        )
        for field_name in ordered_fields:
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        for groups, label in (
            (
                [
                    set(self.generic_value_codes),
                    set(self.table_stake_value_codes),
                    set(self.discriminative_value_codes),
                ],
                "value taxonomy",
            ),
            (
                [
                    set(self.m12d_strong_roles),
                    set(self.m12d_supporting_roles),
                    set(self.m12d_weak_roles),
                    set(self.m12d_risk_roles),
                ],
                "M12D roles",
            ),
            (
                [
                    set(self.m12c_positive_roles),
                    set(self.m12c_supporting_roles),
                    set(self.m12c_opportunity_roles),
                    set(self.m12c_risk_roles),
                    set(self.m12c_unknown_roles),
                ],
                "M12C roles",
            ),
        ):
            if any(
                groups[left] & groups[right]
                for left in range(len(groups))
                for right in range(left + 1, len(groups))
            ):
                raise ValueError(f"{label} cannot overlap")
        if list(self.value_coverage_ratios) != sorted(self.value_coverage_ratios):
            raise ValueError("value coverage ratios must be sorted by code")
        return self


class PurchaseReasonAssessment(CompetitorProfileBaseModel):
    reason_code: str = Field(min_length=1)
    target_roles: list[str] = Field(default_factory=list)
    candidate_roles: list[str] = Field(default_factory=list)
    target_strength: Literal[
        "strong", "supporting", "weak", "risk", "conflict", "absent", "unknown"
    ]
    candidate_strength: Literal[
        "strong",
        "supporting",
        "weak",
        "risk",
        "conflict",
        "absent",
        "unknown",
    ]
    comparison_status: Literal[
        "shared_strong",
        "shared_limited",
        "different_role",
        "target_only",
        "candidate_only",
        "conflict",
    ]
    classification: Literal["discriminative", "supporting", "generic", "table_stake"]
    classification_reason_code: str = Field(min_length=1)
    coverage_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    positive_overlap: bool
    exact_code_match: Literal[True] = True
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    independent_lineage_keys: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reason(self) -> "PurchaseReasonAssessment":
        _assert_sorted_unique(self.target_roles, "target reason roles")
        _assert_sorted_unique(self.candidate_roles, "candidate reason roles")
        _assert_sorted_unique(
            self.independent_lineage_keys,
            "purchase reason lineage keys",
        )
        _assert_evidence_order(self.evidence_refs)
        if self.positive_overlap and self.comparison_status not in {
            "shared_strong",
            "shared_limited",
        }:
            raise ValueError("positive reason overlap requires a shared status")
        return self


class ValueLayerAssessment(CompetitorProfileBaseModel):
    value_code: str = Field(min_length=1)
    layer_code: Literal[
        "F1_purchase_reason",
        "F4_claim_value",
        "F4_user_realization",
        "F5_claim_expression",
        "F5_parameter",
    ]
    target_values: list[str] = Field(default_factory=list)
    candidate_values: list[str] = Field(default_factory=list)
    target_status: Literal[
        "positive", "supporting", "weak", "risk", "absent", "unknown", "conflict"
    ]
    candidate_status: Literal[
        "positive", "supporting", "weak", "risk", "absent", "unknown", "conflict"
    ]
    comparison_status: Literal[
        "matched",
        "different",
        "target_only",
        "candidate_only",
        "conflict",
        "absent_both",
        "unknown",
    ]
    evidence_family: Literal[
        "F1_purchase_reason",
        "F4_user_realization",
        "F5_capability_expression",
    ]
    independent_lineage_keys: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_layer(self) -> "ValueLayerAssessment":
        for field_name in (
            "target_values",
            "candidate_values",
            "independent_lineage_keys",
        ):
            _assert_sorted_unique(getattr(self, field_name), field_name)
        _assert_evidence_order(self.evidence_refs)
        return self


class ValueCodeAssessment(CompetitorProfileBaseModel):
    value_code: str = Field(min_length=1)
    classification: Literal["discriminative", "supporting", "generic", "table_stake"]
    classification_reason_code: str = Field(min_length=1)
    coverage_ratio: Decimal | None = Field(default=None, ge=0, le=1)
    layers: list[ValueLayerAssessment]
    matched_layer_codes: list[str] = Field(default_factory=list)
    matched_evidence_families: list[str] = Field(default_factory=list)
    positive_overlap: bool
    conflict: bool
    exact_code_only: Literal[True] = True
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_value(self) -> "ValueCodeAssessment":
        layer_codes = [row.layer_code for row in self.layers]
        if layer_codes != list(VALUE_LAYER_CODES):
            raise ValueError("value assessment must contain all evidence layers")
        _assert_sorted_unique(self.matched_layer_codes, "matched value layers")
        _assert_sorted_unique(
            self.matched_evidence_families,
            "matched evidence families",
        )
        _assert_evidence_order(self.evidence_refs)
        return self


class ValueSubstitutionEvidencePair(CompetitorProfileBaseModel):
    target: CandidateIdentity
    candidate: CandidateIdentity
    purchase_pool_level: Literal["P0", "P1", "P2", "P3", "unknown"]
    purchase_reason_assessments: list[PurchaseReasonAssessment]
    value_assessments: list[ValueCodeAssessment]
    evidence_status: Literal[
        "strong_overlap",
        "limited_overlap",
        "different_route",
        "conflict",
        "unassessable",
    ]
    shared_discriminative_value_codes: list[str] = Field(default_factory=list)
    target_only_positive_value_codes: list[str] = Field(default_factory=list)
    candidate_only_positive_value_codes: list[str] = Field(default_factory=list)
    independent_evidence_families: list[str] = Field(default_factory=list)
    value_research_allowed: bool
    future_relation_support_possible: bool
    purchase_choice_conclusion_allowed: Literal[False] = False
    business_boundary_code: str = Field(min_length=1)
    review_required: bool = False
    review_reason_codes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    relation_status: Literal["not_evaluated"] = "not_evaluated"
    pair_feature_result_hash: str = Field(min_length=1)
    purchase_pool_result_hash: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "ValueSubstitutionEvidencePair":
        if self.target.sku_code == self.candidate.sku_code:
            raise ValueError("value substitution target and candidate must differ")
        reason_codes = [row.reason_code for row in self.purchase_reason_assessments]
        value_codes = [row.value_code for row in self.value_assessments]
        if reason_codes != sorted(set(reason_codes)):
            raise ValueError("purchase reason assessments must be sorted and unique")
        if value_codes != sorted(set(value_codes)):
            raise ValueError("value assessments must be sorted and unique")
        for field_name in (
            "shared_discriminative_value_codes",
            "target_only_positive_value_codes",
            "candidate_only_positive_value_codes",
            "independent_evidence_families",
            "review_reason_codes",
            "limitations",
        ):
            _assert_sorted_unique(getattr(self, field_name), field_name)
        _assert_evidence_order(self.evidence_refs)
        return self


class ValueSubstitutionEvidenceBundle(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_value_substitution_v1"] = (
        COMPETITOR_PROFILE_VALUE_SUBSTITUTION_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target: CandidateIdentity
    candidate_count: int = Field(ge=0)
    pairs: list[ValueSubstitutionEvidencePair]
    config: ValueSubstitutionConfig
    pair_feature_result_hash: str = Field(min_length=1)
    purchase_pool_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> "ValueSubstitutionEvidenceBundle":
        if not (
            self.category_code
            == self.product_category
            == self.config.product_category
            == self.target.product_category
        ):
            raise ValueError("value substitution categories must match")
        candidate_codes = [row.candidate.sku_code for row in self.pairs]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("value substitution candidates must be sorted and unique")
        if self.candidate_count != len(self.pairs):
            raise ValueError("value substitution candidate count must match pairs")
        if any(row.target != self.target for row in self.pairs):
            raise ValueError("value substitution target must be consistent")
        return self


def _assert_sorted_unique(values: list[str], label: str) -> None:
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted and unique")


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
        raise ValueError("value substitution evidence refs must be sorted and unique")


__all__ = [
    "COMPETITOR_PROFILE_VALUE_SUBSTITUTION_SCHEMA_VERSION",
    "VALUE_LAYER_CODES",
    "PurchaseReasonAssessment",
    "ValueCodeAssessment",
    "ValueLayerAssessment",
    "ValueSubstitutionConfig",
    "ValueSubstitutionEvidenceBundle",
    "ValueSubstitutionEvidencePair",
]
