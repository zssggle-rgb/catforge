"""Typed descriptive price-volume pressure contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceRef,
)


COMPETITOR_PROFILE_PRICE_VOLUME_PRESSURE_SCHEMA_VERSION = (
    "competitor_profile_price_volume_pressure_v1"
)


class PriceVolumePressureConfig(CompetitorProfileBaseModel):
    config_version: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    same_budget_max_gap_ratio: Decimal = Field(ge=0, le=1)
    adjacent_budget_max_gap_ratio: Decimal = Field(ge=0, le=2)
    material_higher_volume_ratio: Decimal = Field(gt=1)
    material_lower_volume_ratio: Decimal = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "PriceVolumePressureConfig":
        if self.same_budget_max_gap_ratio > self.adjacent_budget_max_gap_ratio:
            raise ValueError("same-budget threshold cannot exceed adjacent-budget")
        if (
            self.material_lower_volume_ratio
            >= Decimal("1") / self.material_higher_volume_ratio
        ):
            raise ValueError(
                "lower-volume threshold must leave a non-empty parity interval"
            )
        return self


class PriceVolumePressureAssessment(CompetitorProfileBaseModel):
    target: CandidateIdentity
    candidate: CandidateIdentity
    purchase_pool_level: Literal["P0", "P1", "P2", "P3", "unknown"]
    value_evidence_status: Literal[
        "strong_overlap",
        "limited_overlap",
        "different_route",
        "conflict",
        "unassessable",
    ]
    budget_band: Literal["same", "adjacent", "outside", "unknown"]
    market_comparability_status: Literal["comparable", "limited", "unknown", "conflict"]
    market_pattern: Literal[
        "same_budget_candidate_higher_volume",
        "same_budget_candidate_lower_volume",
        "lower_price_candidate_higher_volume",
        "higher_price_candidate_higher_volume",
        "higher_price_lower_volume",
        "lower_price_lower_volume",
        "volume_parity",
        "no_market_comparison",
        "review_required",
    ]
    pressure_direction: Literal[
        "direct_budget_pressure",
        "downtrade_volume_pressure",
        "uptrade_market_acceptance",
        "value_route_pressure",
        "reference_only",
        "no_observed_pressure",
        "unassessable",
    ]
    target_weighted_price: Decimal | None = Field(default=None, ge=0)
    candidate_weighted_price: Decimal | None = Field(default=None, ge=0)
    price_gap: Decimal | None = None
    price_gap_pct: Decimal | None = None
    target_avg_weekly_volume: Decimal | None = Field(default=None, ge=0)
    candidate_avg_weekly_volume: Decimal | None = Field(default=None, ge=0)
    weekly_volume_gap: Decimal | None = None
    weekly_volume_ratio: Decimal | None = Field(default=None, ge=0)
    target_total_sales: Decimal | None = Field(default=None, ge=0)
    candidate_total_sales: Decimal | None = Field(default=None, ge=0)
    target_sales_amount: Decimal | None = Field(default=None, ge=0)
    candidate_sales_amount: Decimal | None = Field(default=None, ge=0)
    target_price_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_price_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    target_volume_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_volume_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    common_week_count: int | None = Field(default=None, ge=0)
    common_platform_count: int | None = Field(default=None, ge=0)
    diagnostic_only_fields: list[str] = Field(default_factory=list)
    confidence_level: Literal["high", "medium", "low", "unknown"]
    review_required: bool = False
    review_reason_codes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    causal_claim: Literal[False] = False
    wtp_claim: Literal[False] = False
    price_change_sales_increment_claim: Literal[False] = False
    formal_relation_status: Literal["not_evaluated"] = "not_evaluated"
    pair_feature_result_hash: str = Field(min_length=1)
    purchase_pool_result_hash: str = Field(min_length=1)
    value_substitution_result_hash: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "PriceVolumePressureAssessment":
        if self.target.sku_code == self.candidate.sku_code:
            raise ValueError("price-volume target and candidate must differ")
        for field_name in (
            "diagnostic_only_fields",
            "review_reason_codes",
            "limitations",
        ):
            values = getattr(self, field_name)
            if values != sorted(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
        keys = [
            (
                row.module_code,
                row.source_batch_id or "",
                row.record_type,
                row.record_id,
                row.result_hash,
            )
            for row in self.evidence_refs
        ]
        if keys != sorted(set(keys)):
            raise ValueError("price-volume evidence refs must be sorted and unique")
        if self.weekly_volume_ratio is not None and (
            self.target_avg_weekly_volume in {None, Decimal("0")}
        ):
            raise ValueError(
                "weekly volume ratio requires a positive target denominator"
            )
        if self.price_gap_pct is not None and (
            self.target_weighted_price in {None, Decimal("0")}
        ):
            raise ValueError("price gap percent requires a positive target denominator")
        return self


class PriceVolumePressureBundle(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_price_volume_pressure_v1"] = (
        COMPETITOR_PROFILE_PRICE_VOLUME_PRESSURE_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target: CandidateIdentity
    candidate_count: int = Field(ge=0)
    pairs: list[PriceVolumePressureAssessment]
    config: PriceVolumePressureConfig
    pair_feature_result_hash: str = Field(min_length=1)
    purchase_pool_result_hash: str = Field(min_length=1)
    value_substitution_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> "PriceVolumePressureBundle":
        if not (
            self.category_code
            == self.product_category
            == self.config.product_category
            == self.target.product_category
        ):
            raise ValueError("price-volume categories must match")
        candidate_codes = [row.candidate.sku_code for row in self.pairs]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("price-volume candidates must be sorted and unique")
        if self.candidate_count != len(self.pairs):
            raise ValueError("price-volume candidate count must match pairs")
        if any(row.target != self.target for row in self.pairs):
            raise ValueError("price-volume target must be consistent")
        return self


__all__ = [
    "COMPETITOR_PROFILE_PRICE_VOLUME_PRESSURE_SCHEMA_VERSION",
    "PriceVolumePressureAssessment",
    "PriceVolumePressureBundle",
    "PriceVolumePressureConfig",
]
