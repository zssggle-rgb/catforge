"""Typed receipts for candidate-pipeline canonicalization and replay checks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
)


COMPETITOR_PROFILE_DETERMINISM_SCHEMA_VERSION = (
    "competitor_profile_candidate_determinism_receipt_v1"
)


class ModuleCanonicalizationStats(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    category_input_record_count: int = Field(ge=0)
    category_unique_record_count: int = Field(ge=0)
    category_exact_duplicate_count: int = Field(ge=0)
    target_input_record_count: int = Field(ge=0)
    target_unique_record_count: int = Field(ge=0)
    target_exact_duplicate_count: int = Field(ge=0)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "ModuleCanonicalizationStats":
        if self.category_input_record_count != (
            self.category_unique_record_count + self.category_exact_duplicate_count
        ):
            raise ValueError("category canonicalization counts are inconsistent")
        if self.target_input_record_count != (
            self.target_unique_record_count + self.target_exact_duplicate_count
        ):
            raise ValueError("target canonicalization counts are inconsistent")
        if self.target_unique_record_count > self.category_unique_record_count:
            raise ValueError("target records cannot exceed category records")
        return self


class DeterminismCheck(CompetitorProfileBaseModel):
    check_code: str = Field(min_length=1)
    passed: Literal[True] = True
    checked_node_count: int = Field(ge=0)
    detail_hash: str = Field(min_length=1)


class CandidatePipelineDeterminismReceipt(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_candidate_determinism_receipt_v1"] = (
        COMPETITOR_PROFILE_DETERMINISM_SCHEMA_VERSION
    )
    mode: Literal["generated", "verified"]
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    category_input_fingerprint: str = Field(min_length=1)
    target_input_fingerprint: str = Field(min_length=1)
    recall_config_version: str = Field(min_length=1)
    eligibility_config_version: str = Field(min_length=1)
    recall_result_hash: str = Field(min_length=1)
    eligibility_result_hash: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    recall_fact_count: int = Field(ge=0)
    question_assessment_count: int = Field(ge=0)
    unique_evidence_ref_count: int = Field(ge=0)
    replay_count: Literal[2] = 2
    canonicalization_stats: list[ModuleCanonicalizationStats]
    checks: list[DeterminismCheck] = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_receipt(self) -> "CandidatePipelineDeterminismReceipt":
        if self.category_code != self.product_category:
            raise ValueError("determinism category and product category must match")
        module_codes = [row.module_code for row in self.canonicalization_stats]
        if module_codes != sorted(set(module_codes)):
            raise ValueError("canonicalization stats must be sorted and unique")
        check_codes = [row.check_code for row in self.checks]
        if check_codes != sorted(set(check_codes)):
            raise ValueError("determinism checks must be sorted and unique")
        if self.question_assessment_count != self.candidate_count * 8:
            raise ValueError(
                "determinism receipt requires eight questions per candidate"
            )
        return self


__all__ = [
    "COMPETITOR_PROFILE_DETERMINISM_SCHEMA_VERSION",
    "CandidatePipelineDeterminismReceipt",
    "DeterminismCheck",
    "ModuleCanonicalizationStats",
]
