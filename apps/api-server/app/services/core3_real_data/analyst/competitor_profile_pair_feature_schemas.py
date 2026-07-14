"""Typed, conclusion-free target×candidate feature contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceRef,
    PairMarketComparison,
)


COMPETITOR_PROFILE_PAIR_FEATURE_SCHEMA_VERSION = "competitor_profile_pair_feature_v1"
PAIR_FEATURE_GROUPS = (
    "audience",
    "battlefield",
    "claim_expression",
    "claim_value",
    "market_position",
    "parameter",
    "purchase_reason",
    "task",
    "user_realization",
)
PAIR_SOURCE_MODULES = (
    "M03B",
    "M04C",
    "M05C",
    "M07",
    "M09C",
    "M10C",
    "M11C",
    "M11D",
    "M12C",
    "M12D",
)


class PairModuleAvailability(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    target_availability: Literal["present", "unknown"]
    candidate_availability: Literal["present", "unknown"]
    target_record_count: int = Field(ge=0)
    candidate_record_count: int = Field(ge=0)
    target_missing_reason_code: str | None = None
    candidate_missing_reason_code: str | None = None
    review_reason_codes: list[str] = Field(default_factory=list)
    lineage_conflict_reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> "PairModuleAvailability":
        for side in ("target", "candidate"):
            availability = getattr(self, f"{side}_availability")
            record_count = getattr(self, f"{side}_record_count")
            missing_reason = getattr(self, f"{side}_missing_reason_code")
            if availability == "present" and (record_count == 0 or missing_reason):
                raise ValueError(
                    f"present {side} module requires records and no missing reason"
                )
            if availability == "unknown" and (record_count or not missing_reason):
                raise ValueError(f"unknown {side} module requires a missing reason")
        for field_name in (
            "review_reason_codes",
            "lineage_conflict_reason_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        _assert_evidence_order(self.evidence_refs)
        return self


class PairProductFormFacts(CompetitorProfileBaseModel):
    product_category: Literal["TV", "AC"]
    target_screen_size_inch: Decimal | None = Field(default=None, ge=0)
    candidate_screen_size_inch: Decimal | None = Field(default=None, ge=0)
    target_size_segment: str | None = None
    candidate_size_segment: str | None = None
    target_ac_form: str | None = None
    candidate_ac_form: str | None = None
    target_ac_capacity: str | None = None
    candidate_ac_capacity: str | None = None
    unknown_reason_codes: list[str] = Field(default_factory=list)
    compatibility_status: Literal["not_evaluated"] = "not_evaluated"
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_category_fields(self) -> "PairProductFormFacts":
        if self.product_category == "TV" and any(
            value is not None
            for value in (
                self.target_ac_form,
                self.candidate_ac_form,
                self.target_ac_capacity,
                self.candidate_ac_capacity,
            )
        ):
            raise ValueError("TV product form facts cannot contain AC fields")
        if self.product_category == "AC" and any(
            value is not None
            for value in (
                self.target_screen_size_inch,
                self.candidate_screen_size_inch,
            )
        ):
            raise ValueError("AC product form facts cannot contain TV screen fields")
        if self.unknown_reason_codes != sorted(set(self.unknown_reason_codes)):
            raise ValueError("product form unknown reasons must be sorted and unique")
        return self


class PairAlignedFeature(CompetitorProfileBaseModel):
    feature_group: Literal[
        "audience",
        "battlefield",
        "claim_expression",
        "claim_value",
        "market_position",
        "parameter",
        "purchase_reason",
        "task",
        "user_realization",
    ]
    module_code: str = Field(min_length=1)
    feature_code: str = Field(min_length=1)
    target_values: list[str] = Field(default_factory=list)
    candidate_values: list[str] = Field(default_factory=list)
    common_values: list[str] = Field(default_factory=list)
    comparison_status: Literal[
        "shared",
        "different",
        "target_only",
        "candidate_only",
    ]
    target_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    candidate_evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    factual_only: Literal[True] = True
    advantage_claim: Literal[False] = False
    relation_claim: Literal[False] = False
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_alignment(self) -> "PairAlignedFeature":
        for field_name in ("target_values", "candidate_values", "common_values"):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        common = sorted(set(self.target_values) & set(self.candidate_values))
        if self.common_values != common:
            raise ValueError("common feature values must equal the pair intersection")
        expected_status = _comparison_status(self.target_values, self.candidate_values)
        if self.comparison_status != expected_status:
            raise ValueError("feature comparison status conflicts with known values")
        _assert_evidence_order(self.target_evidence_refs)
        _assert_evidence_order(self.candidate_evidence_refs)
        return self


class PairFeatureRecord(CompetitorProfileBaseModel):
    target: CandidateIdentity
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
    recall_sources: list[str] = Field(min_length=1)
    module_availability: list[PairModuleAvailability]
    product_form_facts: PairProductFormFacts
    market_comparison: PairMarketComparison
    aligned_features: list[PairAlignedFeature]
    unknown_reason_codes: list[str] = Field(default_factory=list)
    review_reason_codes: list[str] = Field(default_factory=list)
    lineage_conflict_reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    relation_status: Literal["not_evaluated"] = "not_evaluated"
    business_conclusion_allowed: Literal[False] = False
    causal_claim: Literal[False] = False
    recall_result_hash: str = Field(min_length=1)
    eligibility_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "PairFeatureRecord":
        if self.target.sku_code == self.candidate.sku_code:
            raise ValueError("pair feature target and candidate must differ")
        if self.target.product_category != self.candidate.product_category:
            raise ValueError("pair feature identities must use one product category")
        if self.recall_sources != sorted(set(self.recall_sources)):
            raise ValueError("pair feature recall sources must be sorted and unique")
        module_codes = [row.module_code for row in self.module_availability]
        if module_codes != list(PAIR_SOURCE_MODULES):
            raise ValueError("pair module availability must cover all source modules")
        feature_keys = [
            (row.feature_group, row.module_code, row.feature_code)
            for row in self.aligned_features
        ]
        if feature_keys != sorted(set(feature_keys)):
            raise ValueError("pair aligned features must be sorted and unique")
        for field_name in (
            "unknown_reason_codes",
            "review_reason_codes",
            "lineage_conflict_reason_codes",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        _assert_evidence_order(self.evidence_refs)
        return self


class PairFeatureBundle(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_pair_feature_v1"] = (
        COMPETITOR_PROFILE_PAIR_FEATURE_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target: CandidateIdentity
    candidate_count: int = Field(ge=0)
    pairs: list[PairFeatureRecord]
    recall_result_hash: str = Field(min_length=1)
    eligibility_result_hash: str = Field(min_length=1)
    determinism_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> "PairFeatureBundle":
        if self.category_code != self.product_category:
            raise ValueError("pair feature category and product category must match")
        if self.target.product_category != self.product_category:
            raise ValueError("pair feature target category must match bundle")
        candidate_codes = [row.candidate.sku_code for row in self.pairs]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("pair feature candidates must be sorted and unique")
        if self.candidate_count != len(self.pairs):
            raise ValueError("pair feature candidate count must match pairs")
        if any(row.target != self.target for row in self.pairs):
            raise ValueError("pair feature target must be consistent")
        return self


def _comparison_status(target_values: list[str], candidate_values: list[str]) -> str:
    if target_values and candidate_values:
        return "shared" if set(target_values) & set(candidate_values) else "different"
    return "target_only" if target_values else "candidate_only"


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
        raise ValueError("pair feature evidence refs must be sorted and unique")


__all__ = [
    "COMPETITOR_PROFILE_PAIR_FEATURE_SCHEMA_VERSION",
    "PAIR_FEATURE_GROUPS",
    "PAIR_SOURCE_MODULES",
    "PairAlignedFeature",
    "PairFeatureBundle",
    "PairFeatureRecord",
    "PairModuleAvailability",
    "PairProductFormFacts",
]
