"""Pre-relation eligibility and reference-purpose contracts for recalled candidates."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CandidateStatus,
    CompetitorProfileBaseModel,
    EvidenceFamily,
    EvidenceRef,
    QuestionCode,
    ReferencePurpose,
    RelationCode,
)


COMPETITOR_PROFILE_ELIGIBILITY_SCHEMA_VERSION = (
    "competitor_profile_candidate_eligibility_v1"
)
COMPETITOR_PROFILE_ELIGIBILITY_CONFIG_VERSION = (
    "competitor_profile_candidate_eligibility_config_v1"
)
_DEFAULT_EXPLICIT_ABSENCE_CLAIM_ROLES = [
    "drag_factor",
    "known_absent",
    "not_supported",
    "opportunity_gap",
]
_DEFAULT_REVIEW_PROCESSING_STATUSES = [
    "blocked",
    "failed",
    "review_required",
]


class ProvisionalQuestionReadiness(str, Enum):
    ELIGIBLE = "provisional_eligible"
    LIMITED = "provisional_limited"
    UNAVAILABLE = "unavailable"


ALL_PROVISIONAL_QUESTION_CODES = tuple(sorted(item.value for item in QuestionCode))


class CandidateEligibilityConfig(CompetitorProfileBaseModel):
    config_version: str = Field(
        default=COMPETITOR_PROFILE_ELIGIBILITY_CONFIG_VERSION,
        min_length=1,
    )
    explicit_absence_claim_roles: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_EXPLICIT_ABSENCE_CLAIM_ROLES),
        min_length=1,
    )
    review_processing_statuses: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_REVIEW_PROCESSING_STATUSES),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_config(self) -> "CandidateEligibilityConfig":
        for field_name in (
            "explicit_absence_claim_roles",
            "review_processing_statuses",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        if self.config_version == COMPETITOR_PROFILE_ELIGIBILITY_CONFIG_VERSION and (
            self.explicit_absence_claim_roles != _DEFAULT_EXPLICIT_ABSENCE_CLAIM_ROLES
            or self.review_processing_statuses != _DEFAULT_REVIEW_PROCESSING_STATUSES
        ):
            raise ValueError(
                "modified eligibility configuration requires a new config version"
            )
        return self


class ProvisionalQuestionAssessment(CompetitorProfileBaseModel):
    question_code: QuestionCode
    readiness: ProvisionalQuestionReadiness
    pending_relation_codes: list[RelationCode] = Field(default_factory=list)
    required_evidence_families: list[EvidenceFamily] = Field(default_factory=list)
    available_evidence_families: list[EvidenceFamily] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(min_length=1)
    can_drive_business_conclusion: Literal[False] = False
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_question(self) -> "ProvisionalQuestionAssessment":
        for field_name in (
            "pending_relation_codes",
            "required_evidence_families",
            "available_evidence_families",
            "missing_inputs",
            "reason_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        if not set(self.available_evidence_families).issubset(
            set(self.required_evidence_families)
        ):
            raise ValueError("available evidence must be a subset of required evidence")
        if (
            self.readiness == ProvisionalQuestionReadiness.ELIGIBLE.value
            and self.missing_inputs
        ):
            raise ValueError(
                "provisional eligible questions cannot have missing inputs"
            )
        if (
            self.readiness == ProvisionalQuestionReadiness.UNAVAILABLE.value
            and not self.missing_inputs
        ):
            raise ValueError("unavailable provisional questions require missing inputs")
        return self


class CandidateEligibilityAssessment(CompetitorProfileBaseModel):
    candidate: CandidateIdentity
    candidate_status: Literal[
        "recalled_only",
        "reference_only",
        "review_required",
        "blocked",
    ]
    relation_evaluation_member: bool
    competitor_member: Literal[False] = False
    reference_member: bool
    reference_purposes: list[ReferencePurpose] = Field(default_factory=list)
    available_evidence_families: list[EvidenceFamily] = Field(default_factory=list)
    independent_lineage_keys: list[str] = Field(default_factory=list)
    question_readiness: list[ProvisionalQuestionAssessment]
    reason_codes: list[str] = Field(min_length=1)
    unknown_reason_codes: list[str] = Field(default_factory=list)
    review_reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    recall_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate(self) -> "CandidateEligibilityAssessment":
        for field_name in (
            "reference_purposes",
            "available_evidence_families",
            "independent_lineage_keys",
            "reason_codes",
            "unknown_reason_codes",
            "review_reason_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        question_codes = [row.question_code for row in self.question_readiness]
        if question_codes != list(ALL_PROVISIONAL_QUESTION_CODES):
            raise ValueError(
                "candidate eligibility must cover all provisional questions"
            )
        if self.reference_member != bool(self.reference_purposes):
            raise ValueError("reference membership must match reference purposes")
        if self.candidate_status == CandidateStatus.REFERENCE_ONLY.value and (
            self.relation_evaluation_member or not self.reference_member
        ):
            raise ValueError(
                "reference-only candidates cannot enter relation evaluation"
            )
        if (
            self.candidate_status
            in {
                CandidateStatus.REVIEW_REQUIRED.value,
                CandidateStatus.BLOCKED.value,
            }
            and self.relation_evaluation_member
        ):
            raise ValueError(
                "review or blocked candidates cannot enter relation evaluation"
            )
        if self.candidate_status == CandidateStatus.REVIEW_REQUIRED.value and not (
            self.review_reason_codes
        ):
            raise ValueError("review-required candidates require review reasons")
        if self.candidate_status == CandidateStatus.BLOCKED.value and not (
            self.review_reason_codes
        ):
            raise ValueError("blocked candidates require blocking reasons")
        if self.candidate_status == CandidateStatus.RECALLED_ONLY.value and not (
            self.relation_evaluation_member or self.reason_codes
        ):
            raise ValueError(
                "recalled-only candidates require an evaluation or hold reason"
            )
        _assert_evidence_order(self.evidence_refs)
        return self


class CandidateEligibilityManifest(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_candidate_eligibility_v1"] = (
        COMPETITOR_PROFILE_ELIGIBILITY_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    recall_result_hash: str = Field(min_length=1)
    config: CandidateEligibilityConfig
    candidate_count: int = Field(ge=0)
    relation_evaluation_candidate_count: int = Field(ge=0)
    reference_candidate_count: int = Field(ge=0)
    candidate_count_by_status: dict[str, int]
    candidates: list[CandidateEligibilityAssessment]
    limitations: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "CandidateEligibilityManifest":
        if self.category_code != self.product_category:
            raise ValueError("eligibility category and product category must match")
        candidate_codes = [row.candidate.sku_code for row in self.candidates]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("eligibility candidates must be sorted and unique")
        if self.target_sku_code in candidate_codes:
            raise ValueError("eligibility manifest cannot contain target SKU")
        if self.candidate_count != len(self.candidates):
            raise ValueError("eligibility candidate count must match candidates")
        if self.relation_evaluation_candidate_count != sum(
            row.relation_evaluation_member for row in self.candidates
        ):
            raise ValueError("relation evaluation candidate count is inconsistent")
        if self.reference_candidate_count != sum(
            row.reference_member for row in self.candidates
        ):
            raise ValueError("reference candidate count is inconsistent")
        expected_counts = dict(
            sorted(Counter(row.candidate_status for row in self.candidates).items())
        )
        if self.candidate_count_by_status != expected_counts:
            raise ValueError("candidate status counts are inconsistent")
        if self.limitations != sorted(set(self.limitations)):
            raise ValueError("eligibility limitations must be sorted and unique")
        return self


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
        raise ValueError("eligibility evidence refs must be sorted and unique")


__all__ = [
    "ALL_PROVISIONAL_QUESTION_CODES",
    "COMPETITOR_PROFILE_ELIGIBILITY_CONFIG_VERSION",
    "COMPETITOR_PROFILE_ELIGIBILITY_SCHEMA_VERSION",
    "CandidateEligibilityAssessment",
    "CandidateEligibilityConfig",
    "CandidateEligibilityManifest",
    "ProvisionalQuestionAssessment",
    "ProvisionalQuestionReadiness",
]
