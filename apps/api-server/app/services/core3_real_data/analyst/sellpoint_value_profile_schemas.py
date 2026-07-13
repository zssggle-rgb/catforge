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
CapabilityFactStatus = Literal[
    "known_present",
    "known_absent",
    "missing",
    "contradicted",
]
CapabilityKind = Literal["capability", "experience_outcome"]
InvestmentClassification = Literal[
    "retain",
    "unconverted",
    "do_not_follow",
    "table_stake",
    "missing_competitive_gap",
    "unknown",
]
UserFeedbackStatus = Literal[
    "realized_advantage",
    "realized",
    "partial",
    "not_observed",
    "weaker",
    "negative",
    "unknown",
    "conflicted",
]
RelativeExperienceStatus = Literal[
    "advantage",
    "parity",
    "weaker",
    "unknown",
    "conflicted",
]
MarketEvidenceStatus = Literal[
    "positive",
    "not_weaker",
    "negative",
    "unknown",
    "not_applicable",
]
CompetitivePerformanceStatus = Literal[
    "stronger",
    "not_weaker",
    "weaker",
    "unknown",
    "conflicted",
]
InvestmentLevel = Literal["high", "standard", "low", "unknown"]
ThresholdStatus = Literal[
    "meets_table_stake",
    "below_table_stake",
    "insufficient_known_sample",
    "incomplete_scope",
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


class SellpointValueEvidenceRef(SellpointValueProfileBaseModel):
    module_code: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    batch_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_file_ids: list[str] = Field(default_factory=list)
    raw_row_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CapabilityThresholdConfig(SellpointValueProfileBaseModel):
    config_version: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    minimum_known_count: int = Field(ge=1)
    prevalence_threshold: float = Field(gt=0.0, le=1.0)
    required_scope_dimensions: list[
        Literal[
            "category_code",
            "price_band",
            "product_form",
            "size_relation",
        ]
    ] = Field(min_length=1)
    missing_value_policy: Literal["exclude_from_known"] = "exclude_from_known"
    validation_status: Literal["provisional", "validated"] = "provisional"

    @model_validator(mode="after")
    def validate_scope_dimensions(self) -> "CapabilityThresholdConfig":
        if len(self.required_scope_dimensions) != len(
            set(self.required_scope_dimensions)
        ):
            raise ValueError("required scope dimensions must be unique")
        return self


class CapabilityComparisonScope(SellpointValueProfileBaseModel):
    category_code: Literal["TV", "AC"]
    price_band: str | None = None
    product_form: str | None = None
    size_relation: str | None = None
    battlefield_codes: list[str] = Field(default_factory=list)
    competitor_roles: list[str] = Field(default_factory=list)
    candidate_scope_ids: list[str] = Field(default_factory=list)
    scope_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope_ids(self) -> "CapabilityComparisonScope":
        if len(self.candidate_scope_ids) != len(set(self.candidate_scope_ids)):
            raise ValueError("candidate scope ids must be unique")
        return self


class CapabilityCandidateFact(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    fact_status: CapabilityFactStatus
    normalized_value: Any | None = None
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)


class CapabilityPrevalenceSummary(SellpointValueProfileBaseModel):
    config_version: str = Field(min_length=1)
    config_validation_status: Literal["provisional", "validated"]
    total_candidate_count: int = Field(ge=0)
    known_count: int = Field(ge=0)
    present_count: int = Field(ge=0)
    absent_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    contradicted_count: int = Field(ge=0)
    prevalence: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_status: ThresholdStatus
    minimum_known_count: int = Field(ge=1)
    prevalence_threshold: float = Field(gt=0.0, le=1.0)
    comparison_scope: CapabilityComparisonScope
    candidate_fact_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "CapabilityPrevalenceSummary":
        if self.known_count != self.present_count + self.absent_count:
            raise ValueError("known count must equal present plus absent")
        if self.total_candidate_count != (
            self.known_count + self.missing_count + self.contradicted_count
        ):
            raise ValueError("candidate fact counts must cover the total")
        if self.known_count == 0 and self.prevalence is not None:
            raise ValueError("prevalence requires at least one known fact")
        if self.known_count:
            expected = self.present_count / self.known_count
            if self.prevalence is None or abs(self.prevalence - expected) > 1e-9:
                raise ValueError("prevalence must equal present divided by known")
        if (
            self.threshold_status == "meets_table_stake"
            and (
                self.known_count < self.minimum_known_count
                or self.prevalence is None
                or self.prevalence < self.prevalence_threshold
            )
        ):
            raise ValueError("table-stake threshold status conflicts with counts")
        return self


class CapabilityInvestmentInput(SellpointValueProfileBaseModel):
    capability_code: str = Field(min_length=1)
    capability_name_cn: str = Field(min_length=1)
    capability_kind: CapabilityKind = "capability"
    parent_capability_code: str | None = None
    target_fact_status: CapabilityFactStatus
    target_value: Any | None = None
    investment_level: InvestmentLevel = "unknown"
    candidate_facts: list[CapabilityCandidateFact] = Field(default_factory=list)
    comparison_scope: CapabilityComparisonScope
    user_feedback_status: UserFeedbackStatus = "unknown"
    relative_experience_status: RelativeExperienceStatus = "unknown"
    competitor_experience_stronger: bool | None = None
    price_support: MarketEvidenceStatus = "unknown"
    volume_support: MarketEvidenceStatus = "unknown"
    choice_support: MarketEvidenceStatus = "unknown"
    current_competitive_performance: CompetitivePerformanceStatus = "unknown"
    experience_outcomes: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate_scope(self) -> "CapabilityInvestmentInput":
        codes = [row.candidate_sku_code for row in self.candidate_facts]
        if len(codes) != len(set(codes)):
            raise ValueError("candidate facts must be unique by sku_code")
        if not set(codes).issubset(set(self.comparison_scope.candidate_scope_ids)):
            raise ValueError("candidate facts must belong to the comparison scope")
        if self.capability_kind == "experience_outcome" and not self.parent_capability_code:
            raise ValueError("experience outcomes require a parent capability")
        return self


class CapabilityInvestmentDecision(SellpointValueProfileBaseModel):
    capability_code: str = Field(min_length=1)
    capability_name_cn: str = Field(min_length=1)
    capability_kind: CapabilityKind
    parent_capability_code: str | None = None
    classification: InvestmentClassification
    target_fact_status: CapabilityFactStatus
    target_value: Any | None = None
    investment_level: InvestmentLevel
    prevalence_summary: CapabilityPrevalenceSummary
    user_feedback_status: UserFeedbackStatus
    relative_experience_status: RelativeExperienceStatus
    competitor_experience_stronger: bool | None = None
    price_support: MarketEvidenceStatus
    volume_support: MarketEvidenceStatus
    choice_support: MarketEvidenceStatus
    current_competitive_performance: CompetitivePerformanceStatus
    experience_outcomes: list[str] = Field(default_factory=list)
    candidate_scope_ids: list[str] = Field(default_factory=list)
    business_reason_cn: str = Field(min_length=1)
    boundary_cn: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    review_status: Literal["auto_pass", "review_required"]
    review_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    decision_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision_state(self) -> "CapabilityInvestmentDecision":
        if self.classification == "table_stake" and (
            self.capability_kind != "capability"
            or self.target_fact_status != "known_present"
        ):
            raise ValueError("table stake requires a present capability fact")
        if self.classification in {"retain", "unconverted"} and (
            self.target_fact_status != "known_present"
        ):
            raise ValueError("retain and unconverted require a present target fact")
        if self.classification in {"do_not_follow", "missing_competitive_gap"} and (
            self.target_fact_status != "known_absent"
        ):
            raise ValueError("absent-capability decisions require a known absent fact")
        if self.classification == "unknown" and self.review_status != "review_required":
            raise ValueError("unknown decisions require review")
        if self.review_status == "auto_pass" and self.review_reasons:
            raise ValueError("auto-pass decisions cannot contain review reasons")
        return self


__all__ = [
    "CapabilityCandidateFact",
    "CapabilityComparisonScope",
    "CapabilityFactStatus",
    "CapabilityInvestmentDecision",
    "CapabilityInvestmentInput",
    "CapabilityKind",
    "CapabilityPrevalenceSummary",
    "CapabilityThresholdConfig",
    "CandidateDataAvailability",
    "CandidateEligibilityStatus",
    "CandidatePoolType",
    "CandidateQuestion",
    "CandidateRoleScore",
    "CandidateUniverseManifest",
    "CompetitivePerformanceStatus",
    "InvestmentClassification",
    "InvestmentLevel",
    "MarketEvidenceStatus",
    "ReferencePurpose",
    "RelativeExperienceStatus",
    "SellpointValueEvidenceRef",
    "SellpointValueCandidateManifestItem",
    "SellpointValueReferenceManifestItem",
    "ThresholdStatus",
    "UserFeedbackStatus",
]
