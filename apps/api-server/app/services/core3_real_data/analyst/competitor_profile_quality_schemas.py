"""Typed G21 contracts for competitor-profile quality, freshness, and diff."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateStatus,
    CompetitorProfileBaseModel,
    ConfidenceLevel,
    DecisionTopic,
    FreshnessStatus,
    RelationCode,
    RelationStatus,
    ReleaseQualityStatus,
)


COMPETITOR_PROFILE_QUALITY_SCHEMA_VERSION = "competitor_profile_quality_v1"
COMPETITOR_PROFILE_DIFF_SCHEMA_VERSION = "competitor_profile_diff_v1"


class QualityIssueSeverity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class CompetitorProfileQualityIssue(CompetitorProfileBaseModel):
    issue_code: str = Field(min_length=1)
    severity: QualityIssueSeverity
    scope: Literal["version", "profile", "pair", "relation", "selection", "source"]
    target_sku_code: str | None = None
    candidate_sku_code: str | None = None
    reason_cn: str = Field(min_length=1)


class CompetitorProfileVersionQualityAssessment(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_quality_v1"] = (
        COMPETITOR_PROFILE_QUALITY_SCHEMA_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_quality_status: ReleaseQualityStatus
    processing_status: str = Field(min_length=1)
    expected_sku_count: int = Field(ge=1)
    profile_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    pair_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    selection_count: int = Field(ge=0)
    assessed_sku_codes: list[str] = Field(default_factory=list)
    missing_sku_codes: list[str] = Field(default_factory=list)
    unexpected_sku_codes: list[str] = Field(default_factory=list)
    issues: list[CompetitorProfileQualityIssue] = Field(default_factory=list)
    review_required: bool
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "CompetitorProfileVersionQualityAssessment":
        for field_name in (
            "assessed_sku_codes",
            "missing_sku_codes",
            "unexpected_sku_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        if self.profile_count != len(self.assessed_sku_codes):
            raise ValueError("profile count must match assessed SKU codes")
        if (
            self.ready_count + self.partial_count + self.blocked_count
            != self.profile_count
        ):
            raise ValueError("profile state counts must match profile count")
        blocking = any(row.severity in {"P0", "P1"} for row in self.issues)
        if self.release_quality_status == ReleaseQualityStatus.READY.value:
            if self.issues or self.review_required:
                raise ValueError("ready quality cannot retain issues or review")
        elif self.release_quality_status == ReleaseQualityStatus.LIMITED.value:
            if blocking or not self.issues or not self.review_required:
                raise ValueError(
                    "limited quality requires reviewable non-blocking issues"
                )
        elif self.release_quality_status == ReleaseQualityStatus.BLOCKED.value:
            if not blocking or not self.review_required:
                raise ValueError("blocked quality requires a P0/P1 issue and review")
        elif not any(row.issue_code == "generation_incomplete" for row in self.issues):
            raise ValueError(
                "unassessed quality requires an incomplete generation issue"
            )
        return self


class CompetitorProfileFreshnessAssessment(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_quality_v1"] = (
        COMPETITOR_PROFILE_QUALITY_SCHEMA_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    freshness_status: FreshnessStatus
    changed_authority_codes: list[str] = Field(default_factory=list)
    unavailable_authority_codes: list[str] = Field(default_factory=list)
    changed_scope_fields: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    saved_scope_fingerprint: str = Field(min_length=1)
    current_scope_fingerprint: str | None = None
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_freshness(self) -> "CompetitorProfileFreshnessAssessment":
        for field_name in (
            "changed_authority_codes",
            "unavailable_authority_codes",
            "changed_scope_fields",
            "reason_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        if self.freshness_status == FreshnessStatus.CURRENT.value:
            if self.reason_codes or self.current_scope_fingerprint is None:
                raise ValueError("current freshness requires a complete matching scope")
        elif self.freshness_status == FreshnessStatus.STALE.value:
            if not (self.changed_authority_codes or self.changed_scope_fields):
                raise ValueError("stale freshness requires a concrete change")
        elif not self.reason_codes:
            raise ValueError("unknown freshness requires a reason")
        return self


class CandidateDiffSnapshot(CompetitorProfileBaseModel):
    candidate_status: CandidateStatus
    competitor_member: bool
    reference_member: bool
    selected: bool
    confidence_level: ConfidenceLevel


class CandidateStateChange(CompetitorProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    before: CandidateDiffSnapshot
    after: CandidateDiffSnapshot


class RelationDiffSnapshot(CompetitorProfileBaseModel):
    status: RelationStatus
    is_primary: bool
    confidence_level: ConfidenceLevel
    eligible_question_codes: list[str] = Field(default_factory=list)


class RelationStateChange(CompetitorProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    relation_code: RelationCode
    before: RelationDiffSnapshot
    after: RelationDiffSnapshot


class MarketDiffSnapshot(CompetitorProfileBaseModel):
    comparability_status: Literal["comparable", "limited", "unknown"]
    target_weighted_price: Decimal | None = None
    candidate_weighted_price: Decimal | None = None
    price_gap_pct: Decimal | None = None
    target_avg_weekly_volume: Decimal | None = None
    candidate_avg_weekly_volume: Decimal | None = None
    weekly_volume_ratio: Decimal | None = None


class MarketComparisonChange(CompetitorProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    before: MarketDiffSnapshot
    after: MarketDiffSnapshot


class SelectionDiffSnapshot(CompetitorProfileBaseModel):
    selection_rank: int = Field(ge=1, le=3)
    primary_decision_topic: DecisionTopic
    primary_relation_code: RelationCode
    confidence_level: ConfidenceLevel


class SelectionStateChange(CompetitorProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    before: SelectionDiffSnapshot
    after: SelectionDiffSnapshot


class ProfileStateSnapshot(CompetitorProfileBaseModel):
    analysis_state: Literal["ready", "partial", "blocked"]
    conclusion_state: Literal[
        "available", "no_priority_competitor", "insufficient_evidence"
    ]
    freshness_status: FreshnessStatus
    profile_confidence: Decimal = Field(ge=0, le=1)
    review_required: bool


class CompetitorProfileVersionDiff(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_diff_v1"] = (
        COMPETITOR_PROFILE_DIFF_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    from_competitor_profile_version_id: str = Field(min_length=1)
    to_competitor_profile_version_id: str = Field(min_length=1)
    from_profile_version: str = Field(min_length=1)
    to_profile_version: str = Field(min_length=1)
    candidate_added: list[str] = Field(default_factory=list)
    candidate_removed: list[str] = Field(default_factory=list)
    candidate_changes: list[CandidateStateChange] = Field(default_factory=list)
    relation_changes: list[RelationStateChange] = Field(default_factory=list)
    market_changes: list[MarketComparisonChange] = Field(default_factory=list)
    selection_added: list[str] = Field(default_factory=list)
    selection_removed: list[str] = Field(default_factory=list)
    selection_changes: list[SelectionStateChange] = Field(default_factory=list)
    profile_state_before: ProfileStateSnapshot
    profile_state_after: ProfileStateSnapshot
    changed_profile_sections: list[str] = Field(default_factory=list)
    has_changes: bool
    change_summary_cn: list[str] = Field(default_factory=list)
    from_result_hash: str = Field(min_length=1)
    to_result_hash: str = Field(min_length=1)
    diff_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_diff(self) -> "CompetitorProfileVersionDiff":
        for field_name in (
            "candidate_added",
            "candidate_removed",
            "selection_added",
            "selection_removed",
            "changed_profile_sections",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        changed = bool(
            self.candidate_added
            or self.candidate_removed
            or self.candidate_changes
            or self.relation_changes
            or self.market_changes
            or self.selection_added
            or self.selection_removed
            or self.selection_changes
            or self.changed_profile_sections
            or self.from_result_hash != self.to_result_hash
        )
        if self.has_changes != changed:
            raise ValueError("has_changes must match the diff content")
        if not self.change_summary_cn:
            raise ValueError("version diff requires an explainable Chinese summary")
        return self


__all__ = [
    "COMPETITOR_PROFILE_DIFF_SCHEMA_VERSION",
    "COMPETITOR_PROFILE_QUALITY_SCHEMA_VERSION",
    "CandidateDiffSnapshot",
    "CandidateStateChange",
    "CompetitorProfileFreshnessAssessment",
    "CompetitorProfileQualityIssue",
    "CompetitorProfileVersionDiff",
    "CompetitorProfileVersionQualityAssessment",
    "MarketComparisonChange",
    "MarketDiffSnapshot",
    "ProfileStateSnapshot",
    "QualityIssueSeverity",
    "RelationDiffSnapshot",
    "RelationStateChange",
    "SelectionDiffSnapshot",
    "SelectionStateChange",
]
