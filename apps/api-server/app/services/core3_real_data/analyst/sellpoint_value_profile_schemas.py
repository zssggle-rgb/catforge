"""Typed candidate-universe contracts for sellpoint-value profiles."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CandidatePoolType = Literal["competitor", "reference"]
CandidateEligibilityStatus = Literal[
    "eligible",
    "limited",
    "review_required",
    "blocked",
    "recalled_only",
]
CandidateQuestion = Literal[
    "current_price_support",
    "value_relative_advantage",
    "same_brand_role",
    "scale_conversion",
    "configuration_follow",
    "specific_competitor",
]
ReferencePurpose = Literal[
    "same_size_market",
    "parameter_group",
    "performance_archetype",
    "battlefield_benchmark",
    "synthetic_donor",
]


class SellpointValueProfileBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CandidateDataAvailability(SellpointValueProfileBaseModel):
    market: bool = False
    parameters: bool = False
    claim_value: bool = False
    battlefield: bool = False
    user_task: bool = False
    audience: bool = False


class CandidateRoleScore(SellpointValueProfileBaseModel):
    role_code: str = Field(min_length=1)
    role_name_cn: str = ""
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    auto_select_eligible: bool = False
    review_required: bool = False


class SellpointValueCandidateManifestItem(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    pool_type: Literal["competitor"] = "competitor"
    primary_relation_type: str = Field(min_length=1)
    relation_types: list[str] = Field(default_factory=list)
    recall_sources: list[str] = Field(default_factory=list)
    recall_strength: str = "unknown"
    recall_priority_score: float | None = Field(default=None, ge=0.0, le=1.0)
    component_total_score: float | None = Field(default=None, ge=0.0, le=1.0)
    role_scores: list[CandidateRoleScore] = Field(default_factory=list)
    m14_selected: bool = False
    m14_slot_code: str | None = None
    m14_slot_name_cn: str | None = None
    m14_selection_rank: int | None = Field(default=None, ge=1)
    eligibility_status: CandidateEligibilityStatus
    eligible_questions: list[CandidateQuestion] = Field(default_factory=list)
    unavailable_questions: list[CandidateQuestion] = Field(default_factory=list)
    data_availability: CandidateDataAvailability
    same_brand: bool = False
    market_summary: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    source_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_question_partition(self) -> "SellpointValueCandidateManifestItem":
        if set(self.eligible_questions) & set(self.unavailable_questions):
            raise ValueError("eligible and unavailable questions must not overlap")
        if self.eligibility_status in {"blocked", "recalled_only", "review_required"}:
            if self.eligible_questions:
                raise ValueError(
                    "blocked, recalled_only, and review_required candidates cannot drive questions"
                )
        if self.m14_selected and self.m14_selection_rank is None:
            raise ValueError("M14 selected candidates require a selection rank")
        return self


class SellpointValueReferenceManifestItem(SellpointValueProfileBaseModel):
    reference_sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    pool_type: Literal["reference"] = "reference"
    reference_purposes: list[ReferencePurpose] = Field(min_length=1)
    also_competitor: bool = False
    market_summary: dict[str, Any] = Field(default_factory=dict)
    source_hashes: dict[str, str] = Field(default_factory=dict)


class CandidateUniverseManifest(SellpointValueProfileBaseModel):
    schema_version: Literal["sellpoint_value_candidate_universe_v1"]
    project_id: str = Field(min_length=1)
    category_code: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    competitor_universe_status: Literal["available", "unavailable"]
    competitor_candidates: list[SellpointValueCandidateManifestItem] = Field(
        default_factory=list
    )
    analysis_references: list[SellpointValueReferenceManifestItem] = Field(
        default_factory=list
    )
    candidate_count_by_status: dict[str, int] = Field(default_factory=dict)
    m12_rule_version: str = Field(min_length=1)
    m13_rule_version: str = Field(min_length=1)
    m14_rule_version: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    candidate_manifest_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "CandidateUniverseManifest":
        competitor_codes = [row.candidate_sku_code for row in self.competitor_candidates]
        if len(competitor_codes) != len(set(competitor_codes)):
            raise ValueError("competitor candidates must be unique by sku_code")
        reference_keys = [
            (row.reference_sku_code, tuple(row.reference_purposes))
            for row in self.analysis_references
        ]
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("analysis references must be unique by sku and purpose")
        if self.target_sku_code in competitor_codes:
            raise ValueError("target cannot appear in competitor candidates")
        expected_status = "available" if competitor_codes else "unavailable"
        if self.competitor_universe_status != expected_status:
            raise ValueError("competitor universe status must match candidate availability")
        actual_counts: dict[str, int] = {}
        for row in self.competitor_candidates:
            actual_counts[row.eligibility_status] = (
                actual_counts.get(row.eligibility_status, 0) + 1
            )
        if self.candidate_count_by_status != actual_counts:
            raise ValueError("candidate status counts do not match candidates")
        return self


__all__ = [
    "CandidateDataAvailability",
    "CandidateEligibilityStatus",
    "CandidatePoolType",
    "CandidateQuestion",
    "CandidateRoleScore",
    "CandidateUniverseManifest",
    "ReferencePurpose",
    "SellpointValueCandidateManifestItem",
    "SellpointValueReferenceManifestItem",
]
