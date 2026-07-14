"""Typed seven-relation and question-eligibility evaluation contracts."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    ALL_EVIDENCE_FAMILIES,
    ALL_QUESTION_CODES,
    ALL_RELATION_CODES,
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceFamilyAssessment,
    EvidenceRef,
    QuestionEligibility,
    RelationAssessment,
)


COMPETITOR_PROFILE_RELATION_EVALUATION_SCHEMA_VERSION = (
    "competitor_profile_relation_evaluation_v1"
)


class CompetitorRelationConfig(CompetitorProfileBaseModel):
    config_version: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    downtrade_min_price_gap_pct: Decimal = Field(gt=0, lt=1)
    uptrade_min_price_gap_pct: Decimal = Field(gt=0, lt=1)
    strong_price_gap_pct: Decimal = Field(gt=0, lt=1)
    strong_volume_ratio: Decimal = Field(gt=1)
    threshold_parameter_codes: list[str] = Field(min_length=1)
    primary_relation_priority: list[
        Literal[
            "direct_substitute",
            "same_budget_alternative",
            "downtrade_diversion",
            "uptrade_alternative",
            "same_brand_ladder",
            "scenario_substitute",
            "same_value_substitute",
        ]
    ]

    @model_validator(mode="after")
    def validate_config(self) -> "CompetitorRelationConfig":
        if self.strong_price_gap_pct < max(
            self.downtrade_min_price_gap_pct,
            self.uptrade_min_price_gap_pct,
        ):
            raise ValueError("strong price gap must cover up/down minimums")
        if self.threshold_parameter_codes != sorted(
            set(self.threshold_parameter_codes)
        ):
            raise ValueError("threshold parameter codes must be sorted and unique")
        if set(self.primary_relation_priority) != ALL_RELATION_CODES:
            raise ValueError("primary relation priority must cover all seven relations")
        return self


class CompetitorRelationPairEvaluation(CompetitorProfileBaseModel):
    target: CandidateIdentity
    candidate: CandidateIdentity
    candidate_status: Literal[
        "eligible",
        "limited",
        "review_required",
        "blocked",
        "recalled_only",
        "reference_only",
    ]
    competitor_member: bool
    reference_member: bool
    primary_relation_code: (
        Literal[
            "direct_substitute",
            "same_budget_alternative",
            "downtrade_diversion",
            "uptrade_alternative",
            "same_brand_ladder",
            "scenario_substitute",
            "same_value_substitute",
        ]
        | None
    ) = None
    relation_assessments: list[RelationAssessment]
    evidence_family_assessments: list[EvidenceFamilyAssessment]
    question_eligibility: list[QuestionEligibility]
    overall_confidence_level: Literal["high", "medium", "low", "unknown"]
    review_required: bool = False
    review_reason_codes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    selected: Literal[False] = False
    selection_status: Literal["not_evaluated"] = "not_evaluated"
    causal_claim: Literal[False] = False
    wtp_claim: Literal[False] = False
    price_change_sales_increment_claim: Literal[False] = False
    pair_feature_result_hash: str = Field(min_length=1)
    purchase_pool_result_hash: str = Field(min_length=1)
    value_substitution_result_hash: str = Field(min_length=1)
    price_volume_pressure_result_hash: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "CompetitorRelationPairEvaluation":
        if self.target.sku_code == self.candidate.sku_code:
            raise ValueError("relation target and candidate must differ")
        relation_codes = sorted(
            _enum_value(row.relation_code) for row in self.relation_assessments
        )
        if relation_codes != sorted(ALL_RELATION_CODES):
            raise ValueError("relation assessments must cover all seven relations")
        family_codes = sorted(
            _enum_value(row.family) for row in self.evidence_family_assessments
        )
        if family_codes != sorted(ALL_EVIDENCE_FAMILIES):
            raise ValueError("evidence assessments must cover all five families")
        question_codes = sorted(
            _enum_value(row.question_code) for row in self.question_eligibility
        )
        if question_codes != sorted(ALL_QUESTION_CODES):
            raise ValueError("question eligibility must cover all eight questions")
        primary_rows = [row for row in self.relation_assessments if row.is_primary]
        if self.primary_relation_code is None and primary_rows:
            raise ValueError("primary relation rows require a primary code")
        if self.primary_relation_code is not None and (
            len(primary_rows) != 1
            or _enum_value(primary_rows[0].relation_code) != self.primary_relation_code
        ):
            raise ValueError("primary relation code must match exactly one relation")
        if self.competitor_member != (self.candidate_status in {"eligible", "limited"}):
            raise ValueError("competitor membership must match candidate status")
        for field_name in ("review_reason_codes", "limitations"):
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
            raise ValueError("relation evidence refs must be sorted and unique")
        return self


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


class CompetitorRelationEvaluationBundle(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_relation_evaluation_v1"] = (
        COMPETITOR_PROFILE_RELATION_EVALUATION_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target: CandidateIdentity
    candidate_count: int = Field(ge=0)
    pairs: list[CompetitorRelationPairEvaluation]
    config: CompetitorRelationConfig
    pair_feature_result_hash: str = Field(min_length=1)
    purchase_pool_result_hash: str = Field(min_length=1)
    value_substitution_result_hash: str = Field(min_length=1)
    price_volume_pressure_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> "CompetitorRelationEvaluationBundle":
        if not (
            self.category_code
            == self.product_category
            == self.config.product_category
            == self.target.product_category
        ):
            raise ValueError("relation evaluation categories must match")
        candidate_codes = [row.candidate.sku_code for row in self.pairs]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("relation candidates must be sorted and unique")
        if self.candidate_count != len(self.pairs):
            raise ValueError("relation candidate count must match pairs")
        if any(row.target != self.target for row in self.pairs):
            raise ValueError("relation target must be consistent")
        return self


__all__ = [
    "COMPETITOR_PROFILE_RELATION_EVALUATION_SCHEMA_VERSION",
    "CompetitorRelationConfig",
    "CompetitorRelationEvaluationBundle",
    "CompetitorRelationPairEvaluation",
]
