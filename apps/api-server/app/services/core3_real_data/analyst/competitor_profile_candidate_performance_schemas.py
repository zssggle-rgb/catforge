"""Typed performance limits and metrics for the competitor candidate pipeline."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
)


COMPETITOR_PROFILE_PERFORMANCE_CONFIG_VERSION = (
    "competitor_profile_candidate_performance_v1"
)
COMPETITOR_PROFILE_PERFORMANCE_SCHEMA_VERSION = (
    "competitor_profile_candidate_performance_metrics_v1"
)
_DEFAULT_MAX_WALL_TIME_MS = Decimal("15000.000")
_DEFAULT_MAX_PEAK_MEMORY_MIB = Decimal("512.000")
_DEFAULT_MAX_PROVIDER_SELECT_COUNT = 11
_DEFAULT_PAGE_SIZES = [1, 17, 64, 256]


class CandidatePerformanceConfig(CompetitorProfileBaseModel):
    config_version: str = Field(
        default=COMPETITOR_PROFILE_PERFORMANCE_CONFIG_VERSION,
        min_length=1,
    )
    max_wall_time_ms: Decimal = Field(
        default=_DEFAULT_MAX_WALL_TIME_MS,
        gt=0,
    )
    max_peak_memory_mib: Decimal = Field(
        default=_DEFAULT_MAX_PEAK_MEMORY_MIB,
        gt=0,
    )
    max_provider_select_count: int = Field(
        default=_DEFAULT_MAX_PROVIDER_SELECT_COUNT,
        ge=1,
    )
    page_sizes: list[int] = Field(
        default_factory=lambda: list(_DEFAULT_PAGE_SIZES),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_config(self) -> "CandidatePerformanceConfig":
        if self.page_sizes != sorted(set(self.page_sizes)) or any(
            value <= 0 for value in self.page_sizes
        ):
            raise ValueError(
                "performance page sizes must be positive, sorted and unique"
            )
        if self.config_version == COMPETITOR_PROFILE_PERFORMANCE_CONFIG_VERSION and (
            self.max_wall_time_ms != _DEFAULT_MAX_WALL_TIME_MS
            or self.max_peak_memory_mib != _DEFAULT_MAX_PEAK_MEMORY_MIB
            or self.max_provider_select_count != _DEFAULT_MAX_PROVIDER_SELECT_COUNT
            or self.page_sizes != _DEFAULT_PAGE_SIZES
        ):
            raise ValueError("modified performance limits require a new config version")
        return self


class CandidatePerformanceMetrics(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_candidate_performance_metrics_v1"] = (
        COMPETITOR_PROFILE_PERFORMANCE_SCHEMA_VERSION
    )
    case_code: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    authoritative_sku_count: int = Field(ge=1)
    expected_candidate_count: int = Field(ge=0)
    recall_candidate_count: int = Field(ge=0)
    eligibility_candidate_count: int = Field(ge=0)
    source_record_count: int = Field(ge=0)
    recall_fact_count: int = Field(ge=0)
    question_assessment_count: int = Field(ge=0)
    unique_evidence_ref_count: int = Field(ge=0)
    source_page_size: int | None = Field(default=None, ge=1)
    source_page_count: int = Field(ge=0)
    provider_select_count: int | None = Field(default=None, ge=0)
    wall_time_ms: Decimal = Field(ge=0)
    peak_memory_mib: Decimal = Field(ge=0)
    status: Literal["passed", "failed"]
    failure_reason_codes: list[str] = Field(default_factory=list)
    recall_result_hash: str = Field(min_length=1)
    eligibility_result_hash: str = Field(min_length=1)
    determinism_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metrics(self) -> "CandidatePerformanceMetrics":
        if self.category_code != self.product_category:
            raise ValueError("performance category and product category must match")
        if self.failure_reason_codes != sorted(set(self.failure_reason_codes)):
            raise ValueError("performance failure reasons must be sorted and unique")
        if (self.status == "failed") != bool(self.failure_reason_codes):
            raise ValueError("performance status must match failure reasons")
        if self.question_assessment_count != self.eligibility_candidate_count * 8:
            raise ValueError(
                "performance metrics require eight questions per candidate"
            )
        if self.source_page_size is None and self.source_page_count:
            raise ValueError("source page count requires a page size")
        return self


class CandidatePerformanceSuiteReport(CompetitorProfileBaseModel):
    config: CandidatePerformanceConfig
    status: Literal["passed", "failed"]
    case_count: int = Field(ge=1)
    cases: list[CandidatePerformanceMetrics] = Field(min_length=1)
    failure_case_codes: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suite(self) -> "CandidatePerformanceSuiteReport":
        case_codes = [row.case_code for row in self.cases]
        if case_codes != sorted(set(case_codes)):
            raise ValueError("performance cases must be sorted and unique")
        if self.case_count != len(self.cases):
            raise ValueError("performance case count must match cases")
        expected_failures = sorted(
            row.case_code for row in self.cases if row.status == "failed"
        )
        if self.failure_case_codes != expected_failures:
            raise ValueError("performance failure case codes are inconsistent")
        if (self.status == "failed") != bool(self.failure_case_codes):
            raise ValueError("performance suite status must match failed cases")
        return self


__all__ = [
    "COMPETITOR_PROFILE_PERFORMANCE_CONFIG_VERSION",
    "COMPETITOR_PROFILE_PERFORMANCE_SCHEMA_VERSION",
    "CandidatePerformanceConfig",
    "CandidatePerformanceMetrics",
    "CandidatePerformanceSuiteReport",
]
