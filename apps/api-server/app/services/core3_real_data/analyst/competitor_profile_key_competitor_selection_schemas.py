"""Typed contracts for the minimal zero-to-three key-competitor set."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorProfileBaseModel,
    EvidenceRef,
    KeyCompetitorSelectionDraft,
)


COMPETITOR_PROFILE_KEY_SELECTION_SCHEMA_VERSION = "competitor_profile_key_selection_v1"

DecisionTopicCode = Literal[
    "purchase_choice",
    "price_scale_pressure",
    "portfolio_or_scenario",
    "value_route",
]
RelationCode = Literal[
    "direct_substitute",
    "same_budget_alternative",
    "downtrade_diversion",
    "uptrade_alternative",
    "same_brand_ladder",
    "scenario_substitute",
    "same_value_substitute",
]

ALL_DECISION_TOPICS = {
    "purchase_choice",
    "price_scale_pressure",
    "portfolio_or_scenario",
    "value_route",
}


class KeyCompetitorSelectionConfig(CompetitorProfileBaseModel):
    config_version: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    max_selected_count: Literal[3] = 3
    decision_topic_order: list[DecisionTopicCode]
    topic_relation_priority: dict[DecisionTopicCode, list[RelationCode]]

    @model_validator(mode="after")
    def validate_config(self) -> "KeyCompetitorSelectionConfig":
        if set(self.decision_topic_order) != ALL_DECISION_TOPICS or len(
            self.decision_topic_order
        ) != len(ALL_DECISION_TOPICS):
            raise ValueError("decision topic order must cover all four topics once")
        if set(self.topic_relation_priority) != ALL_DECISION_TOPICS:
            raise ValueError("topic relation priority must cover all four topics")
        for topic, values in self.topic_relation_priority.items():
            if not values or len(values) != len(set(values)):
                raise ValueError(
                    f"{topic} relation priority must be non-empty and unique"
                )
        return self


class DecisionTopicAssessment(CompetitorProfileBaseModel):
    topic_code: DecisionTopicCode
    eligible: bool
    usable_relation_codes: list[RelationCode] = Field(default_factory=list)
    best_relation_code: RelationCode | None = None
    best_relation_status: Literal["passed", "limited"] | None = None
    best_confidence_level: Literal["high", "medium"] | None = None
    independent_evidence_family_count: int = Field(ge=0, le=4)
    f1_f4_evidence_count: int = Field(ge=0, le=2)
    market_pressure_clarity: Literal["strong", "clear", "limited", "none"]
    limitation_count: int = Field(ge=0)
    reason_code: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_topic(self) -> "DecisionTopicAssessment":
        if self.eligible and (
            not self.usable_relation_codes
            or self.best_relation_code is None
            or self.best_relation_status is None
            or self.best_confidence_level is None
        ):
            raise ValueError("eligible topics require a usable best relation")
        if not self.eligible and any(
            value is not None
            for value in (
                self.best_relation_code,
                self.best_relation_status,
                self.best_confidence_level,
            )
        ):
            raise ValueError("unavailable topics cannot carry a best relation")
        if self.best_relation_code is not None and (
            self.best_relation_code not in self.usable_relation_codes
        ):
            raise ValueError("best relation must be usable for the topic")
        return self


class KeyCompetitorPairSelectionDecision(CompetitorProfileBaseModel):
    target: CandidateIdentity
    candidate: CandidateIdentity
    source_candidate_status: Literal[
        "eligible",
        "limited",
        "review_required",
        "blocked",
        "recalled_only",
        "reference_only",
    ]
    selection_eligible: bool
    topic_assessments: list[DecisionTopicAssessment]
    selected: bool
    selection_rank: int | None = Field(default=None, ge=1, le=3)
    primary_decision_topic: DecisionTopicCode | None = None
    covered_decision_topics: list[DecisionTopicCode] = Field(default_factory=list)
    non_selection_reason_code: str | None = None
    non_selection_reason_cn: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    relation_evaluation_pair_result_hash: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> "KeyCompetitorPairSelectionDecision":
        topic_codes = [_enum_value(row.topic_code) for row in self.topic_assessments]
        if set(topic_codes) != ALL_DECISION_TOPICS or len(topic_codes) != len(
            ALL_DECISION_TOPICS
        ):
            raise ValueError("pair decision must assess all four topics once")
        if self.selected:
            if not self.selection_eligible or self.selection_rank is None:
                raise ValueError("selected pairs must be eligible and ranked")
            if self.primary_decision_topic is None or (
                self.primary_decision_topic not in self.covered_decision_topics
            ):
                raise ValueError("selected pairs require a covered primary topic")
            if self.non_selection_reason_code or self.non_selection_reason_cn:
                raise ValueError("selected pairs cannot carry non-selection reasons")
        else:
            if (
                self.selection_rank is not None
                or self.primary_decision_topic is not None
            ):
                raise ValueError("unselected pairs cannot carry rank or primary topic")
            if not self.non_selection_reason_code or not self.non_selection_reason_cn:
                raise ValueError("unselected pairs require an explicit reason")
            if self.covered_decision_topics:
                raise ValueError("unselected pairs cannot claim covered topics")
        return self


class KeyCompetitorSelectionBundle(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_key_selection_v1"] = (
        COMPETITOR_PROFILE_KEY_SELECTION_SCHEMA_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target: CandidateIdentity
    candidate_count: int = Field(ge=0)
    pair_decisions: list[KeyCompetitorPairSelectionDecision]
    selected_count: int = Field(ge=0, le=3)
    selections: list[KeyCompetitorSelectionDraft] = Field(default_factory=list)
    selection_state: Literal[
        "selected",
        "no_priority_competitor",
        "insufficient_evidence",
        "review_required",
    ]
    covered_decision_topics: list[DecisionTopicCode] = Field(default_factory=list)
    uncovered_decision_topics: list[DecisionTopicCode] = Field(default_factory=list)
    review_required: bool = False
    limitations: list[str] = Field(default_factory=list)
    config: KeyCompetitorSelectionConfig
    relation_evaluation_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> "KeyCompetitorSelectionBundle":
        if not (
            self.category_code
            == self.product_category
            == self.config.product_category
            == self.target.product_category
        ):
            raise ValueError("selection categories must match")
        candidate_codes = [row.candidate.sku_code for row in self.pair_decisions]
        if candidate_codes != sorted(set(candidate_codes)):
            raise ValueError("selection pair decisions must be sorted and unique")
        if self.candidate_count != len(self.pair_decisions):
            raise ValueError("selection candidate count must match pair decisions")
        if any(row.target != self.target for row in self.pair_decisions):
            raise ValueError("selection targets must be consistent")
        if self.selected_count != len(self.selections):
            raise ValueError("selected count must match selection rows")
        ranks = [row.selection_rank for row in self.selections]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("selection ranks must be contiguous")
        selected_codes = [row.candidate_sku_code for row in self.selections]
        if len(selected_codes) != len(set(selected_codes)):
            raise ValueError("selected candidates must be unique")
        decision_selected = {
            row.candidate.sku_code: row.selection_rank
            for row in self.pair_decisions
            if row.selected
        }
        if decision_selected != {
            row.candidate_sku_code: row.selection_rank for row in self.selections
        }:
            raise ValueError("selection rows must match selected pair decisions")
        if self.selected_count and self.selection_state != "selected":
            raise ValueError("non-empty selections require selected state")
        if not self.selected_count and self.selection_state == "selected":
            raise ValueError("selected state requires at least one selection")
        if self.review_required != (self.selection_state == "review_required"):
            raise ValueError("review flag must match selection state")
        all_topics = set(self.config.decision_topic_order)
        if set(self.covered_decision_topics) | set(
            self.uncovered_decision_topics
        ) != all_topics or set(self.covered_decision_topics) & set(
            self.uncovered_decision_topics
        ):
            raise ValueError("covered and uncovered topics must partition all topics")
        for field_name in (
            "covered_decision_topics",
            "uncovered_decision_topics",
        ):
            values = getattr(self, field_name)
            expected = [
                topic for topic in self.config.decision_topic_order if topic in values
            ]
            if values != expected:
                raise ValueError(f"{field_name} must follow configured topic order")
        return self


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


__all__ = [
    "COMPETITOR_PROFILE_KEY_SELECTION_SCHEMA_VERSION",
    "DecisionTopicAssessment",
    "KeyCompetitorPairSelectionDecision",
    "KeyCompetitorSelectionBundle",
    "KeyCompetitorSelectionConfig",
]
