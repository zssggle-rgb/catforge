"""Typed contracts for the full, pre-qualification competitor recall manifest."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceRef,
)


COMPETITOR_PROFILE_RECALL_SCHEMA_VERSION = "competitor_profile_recall_manifest_v1"
COMPETITOR_PROFILE_RECALL_CONFIG_VERSION = "competitor_profile_recall_v1"
_DEFAULT_SAME_BUDGET_PCT = Decimal("0.1500")
_DEFAULT_ADJACENT_BUDGET_PCT = Decimal("0.3000")
_DEFAULT_PRICE_DIRECTION_MIN_PCT = Decimal("0.0800")
_DEFAULT_STRONG_PRICE_DIFFERENCE_PCT = Decimal("0.1500")
_DEFAULT_MARKET_PERFORMANCE_RATIO = Decimal("1.2500")
_DEFAULT_TV_SIZE_TOLERANCE = Decimal("0.0100")
_DEFAULT_AC_FORM_CODES = sorted(
    {
        "ac_product_form",
        "form_factor",
        "installation_type",
        "product_form",
    }
)
_DEFAULT_AC_CAPACITY_CODES = sorted(
    {
        "applicable_area_segment",
        "capacity_tier",
        "cooling_capacity_segment",
        "cooling_capacity_tier",
        "horsepower_segment",
    }
)


class RecallEntryCode(str, Enum):
    DOWNTRADE = "downtrade"
    MARKET_REFERENCE = "market_reference"
    SAME_BRAND_LADDER = "same_brand_ladder"
    SAME_PURCHASE_POOL = "same_purchase_pool"
    SAME_VALUE = "same_value"
    SCENARIO = "scenario"
    UPTRADE = "uptrade"


ALL_RECALL_ENTRY_CODES = tuple(sorted(item.value for item in RecallEntryCode))


class CandidateRecallConfig(CompetitorProfileBaseModel):
    config_version: str = Field(
        default=COMPETITOR_PROFILE_RECALL_CONFIG_VERSION,
        min_length=1,
    )
    enabled_entries: list[RecallEntryCode] = Field(
        default_factory=lambda: list(ALL_RECALL_ENTRY_CODES),
        min_length=1,
    )
    same_budget_pct: Decimal = Field(default=_DEFAULT_SAME_BUDGET_PCT, gt=0, lt=1)
    adjacent_budget_pct: Decimal = Field(
        default=_DEFAULT_ADJACENT_BUDGET_PCT,
        gt=0,
        lt=1,
    )
    price_direction_min_pct: Decimal = Field(
        default=_DEFAULT_PRICE_DIRECTION_MIN_PCT,
        gt=0,
        lt=1,
    )
    strong_price_difference_pct: Decimal = Field(
        default=_DEFAULT_STRONG_PRICE_DIFFERENCE_PCT,
        gt=0,
        lt=1,
    )
    market_performance_ratio: Decimal = Field(
        default=_DEFAULT_MARKET_PERFORMANCE_RATIO,
        gt=1,
    )
    tv_screen_size_tolerance_inch: Decimal = Field(
        default=_DEFAULT_TV_SIZE_TOLERANCE,
        ge=0,
        le=1,
    )
    ac_form_param_codes: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_AC_FORM_CODES),
        min_length=1,
    )
    ac_capacity_param_codes: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_AC_CAPACITY_CODES),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_recall_config(self) -> "CandidateRecallConfig":
        if self.enabled_entries != sorted(set(self.enabled_entries)):
            raise ValueError("enabled recall entries must be sorted and unique")
        if self.same_budget_pct >= self.adjacent_budget_pct:
            raise ValueError("same-budget threshold must be below adjacent-budget threshold")
        if self.price_direction_min_pct > self.strong_price_difference_pct:
            raise ValueError("direction threshold cannot exceed strong price threshold")
        for field_name in ("ac_form_param_codes", "ac_capacity_param_codes"):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        if self.config_version == COMPETITOR_PROFILE_RECALL_CONFIG_VERSION and (
            self.enabled_entries != list(ALL_RECALL_ENTRY_CODES)
            or self.same_budget_pct != _DEFAULT_SAME_BUDGET_PCT
            or self.adjacent_budget_pct != _DEFAULT_ADJACENT_BUDGET_PCT
            or self.price_direction_min_pct != _DEFAULT_PRICE_DIRECTION_MIN_PCT
            or self.strong_price_difference_pct
            != _DEFAULT_STRONG_PRICE_DIFFERENCE_PCT
            or self.market_performance_ratio != _DEFAULT_MARKET_PERFORMANCE_RATIO
            or self.tv_screen_size_tolerance_inch != _DEFAULT_TV_SIZE_TOLERANCE
            or self.ac_form_param_codes != _DEFAULT_AC_FORM_CODES
            or self.ac_capacity_param_codes != _DEFAULT_AC_CAPACITY_CODES
        ):
            raise ValueError("modified recall configuration requires a new config version")
        return self


class RecallFact(CompetitorProfileBaseModel):
    entry_code: RecallEntryCode
    reason_code: str = Field(min_length=1)
    matched_values: list[str] = Field(default_factory=list)
    target_values: dict[str, Any] = Field(default_factory=dict)
    candidate_values: dict[str, Any] = Field(default_factory=dict)
    target_evidence_refs: list[EvidenceRef] = Field(min_length=1)
    candidate_evidence_refs: list[EvidenceRef] = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_recall_fact(self) -> "RecallFact":
        if self.matched_values != sorted(set(self.matched_values)):
            raise ValueError("recall fact matched values must be sorted and unique")
        _assert_evidence_order(self.target_evidence_refs)
        _assert_evidence_order(self.candidate_evidence_refs)
        return self


class RecalledCandidate(CompetitorProfileBaseModel):
    candidate: CandidateIdentity
    recall_sources: list[RecallEntryCode] = Field(min_length=1)
    recall_facts: list[RecallFact] = Field(min_length=1)
    unknown_reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(min_length=1)
    manifest_order_key: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_recalled_candidate(self) -> "RecalledCandidate":
        if self.recall_sources != sorted(set(self.recall_sources)):
            raise ValueError("candidate recall sources must be sorted and unique")
        fact_order = [
            (row.entry_code, row.reason_code, tuple(row.matched_values))
            for row in self.recall_facts
        ]
        if fact_order != sorted(fact_order) or len(fact_order) != len(set(fact_order)):
            raise ValueError("candidate recall facts must be sorted and unique")
        if set(self.recall_sources) != {row.entry_code for row in self.recall_facts}:
            raise ValueError("candidate recall sources must match recall facts")
        if self.unknown_reason_codes != sorted(set(self.unknown_reason_codes)):
            raise ValueError("candidate unknown reasons must be sorted and unique")
        _assert_evidence_order(self.evidence_refs)
        return self


class RecallEntryCoverage(CompetitorProfileBaseModel):
    entry_code: RecallEntryCode
    status: Literal["available", "partial", "unavailable", "disabled"]
    candidate_count: int = Field(ge=0)
    target_missing_modules: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_coverage(self) -> "RecallEntryCoverage":
        if self.target_missing_modules != sorted(set(self.target_missing_modules)):
            raise ValueError("coverage missing modules must be sorted and unique")
        if self.reason_codes != sorted(set(self.reason_codes)):
            raise ValueError("coverage reasons must be sorted and unique")
        if self.status == "disabled" and self.candidate_count:
            raise ValueError("disabled recall entries cannot have candidates")
        return self


class CandidateRecallManifest(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_recall_manifest_v1"] = (
        COMPETITOR_PROFILE_RECALL_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    category_input_fingerprint: str = Field(min_length=1)
    target_input_fingerprint: str = Field(min_length=1)
    config: CandidateRecallConfig
    candidate_count: int = Field(ge=0)
    candidates: list[RecalledCandidate]
    entry_coverage: dict[str, RecallEntryCoverage]
    limitations: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "CandidateRecallManifest":
        if self.category_code != self.product_category:
            raise ValueError("recall manifest category and product category must match")
        candidate_codes = [row.candidate.sku_code for row in self.candidates]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("recalled candidate SKUs must be sorted and unique")
        if self.target_sku_code in candidate_codes:
            raise ValueError("recall manifest cannot contain the target SKU")
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate count must match recalled candidates")
        if set(self.entry_coverage) != set(ALL_RECALL_ENTRY_CODES):
            raise ValueError("recall manifest must contain coverage for every entry")
        enabled = set(self.config.enabled_entries)
        for entry_code, coverage in self.entry_coverage.items():
            if entry_code != coverage.entry_code:
                raise ValueError("entry coverage key must match its entry code")
            if (entry_code in enabled) == (coverage.status == "disabled"):
                raise ValueError("entry coverage status must match recall configuration")
        for candidate in self.candidates:
            if candidate.candidate.product_category != self.product_category:
                raise ValueError("candidate product category must match recall manifest")
            if not set(candidate.recall_sources).issubset(enabled):
                raise ValueError("candidate cannot use a disabled recall entry")
        if self.limitations != sorted(set(self.limitations)):
            raise ValueError("recall limitations must be sorted and unique")
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
        raise ValueError("recall evidence refs must be sorted and unique")


__all__ = [
    "ALL_RECALL_ENTRY_CODES",
    "COMPETITOR_PROFILE_RECALL_CONFIG_VERSION",
    "COMPETITOR_PROFILE_RECALL_SCHEMA_VERSION",
    "CandidateRecallConfig",
    "CandidateRecallManifest",
    "RecallEntryCode",
    "RecallEntryCoverage",
    "RecallFact",
    "RecalledCandidate",
]
