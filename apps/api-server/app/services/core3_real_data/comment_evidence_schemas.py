"""M05 comment evidence Pydantic contracts.

M05 builds comment units, sentence-level evidence atoms, weak topic hints, and
comment quality profiles. It intentionally stops before user-task, target-group,
battlefield, competitor, score, selection, and report conclusions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.core3_real_data.constants import (
    CORE3_M05_ALLOWED_EVIDENCE_TYPES,
    CORE3_M05_MODULE_VERSION,
    CORE3_M05_RULE_VERSION,
    CORE3_M05_SEED_VERSION,
    CommentDedupStrategy,
    CommentDomainHint,
    CommentLowValueReason,
    CommentReviewReasonCode,
    CommentSampleStatus,
    CommentSentimentHint,
    CommentSentimentSource,
    CommentTopicHintStatus,
    CommentTopicMatchMethod,
    CommentUnitStatus,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3ReviewSeverity,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchType,
    Core3SourceImpactLevel,
)


CommentConfidenceLevel = Core3ConfidenceLevel
CommentReviewStatus = Core3ReviewStatus


class Core3CommentEvidenceBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


def _validate_non_empty_strings(values: list[str], field_name: str) -> list[str]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain empty values")
    return values


class M05RunRequest(Core3CommentEvidenceBaseModel):
    project_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M05_MODULE_VERSION
    seed_version: str = CORE3_M05_SEED_VERSION
    rule_version: str = CORE3_M05_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_sku_scope(cls, sku_scope: list[str]) -> list[str]:
        return _validate_non_empty_strings(sku_scope, "sku_scope")


class M05RunResult(Core3CommentEvidenceBaseModel):
    batch_id: str = Field(min_length=1)
    module_code: Core3ModuleCode = Core3ModuleCode.M05
    status: Core3RunStatus
    comment_unit_count: int = Field(default=0, ge=0)
    unit_link_count: int = Field(default=0, ge=0)
    evidence_atom_count: int = Field(default=0, ge=0)
    topic_hint_count: int = Field(default=0, ge=0)
    quality_profile_count: int = Field(default=0, ge=0)
    usable_sentence_count: int = Field(default=0, ge=0)
    downstream_ready_sku_count: int = Field(default=0, ge=0)
    review_required_count: int = Field(default=0, ge=0)
    review_required: bool = False
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, warnings: list[str]) -> list[str]:
        return _validate_non_empty_strings(warnings, "warnings")


class M05EvidenceInput(Core3CommentEvidenceBaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_key: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    evidence_type: Core3EvidenceType
    evidence_field: str | None = None
    source_row_id: str | None = None
    clean_record_key: str | None = None
    comment_id: str | None = None
    comment_text_hash: str | None = None
    segment_text_hash: str | None = None
    sentence_seq: int | None = Field(default=None, ge=0)
    dimension_path_raw: str | None = None
    text_value: str | None = None
    raw_value: str | None = None
    clean_value: str | None = None
    evidence_payload_json: dict[str, Any] = Field(default_factory=dict)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    base_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list)
    is_current: bool = True

    @field_validator("evidence_type")
    @classmethod
    def validate_m05_evidence_type(cls, evidence_type: Core3EvidenceType) -> Core3EvidenceType:
        if evidence_type not in CORE3_M05_ALLOWED_EVIDENCE_TYPES:
            raise ValueError(f"evidence_type is not allowed for M05: {evidence_type}")
        return evidence_type

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags(cls, quality_flags: list[str]) -> list[str]:
        return _validate_non_empty_strings(quality_flags, "quality_flags")


class M05SkuInputBundle(Core3CommentEvidenceBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    evidence_inputs: list[M05EvidenceInput] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle_sku_consistency(self) -> "M05SkuInputBundle":
        mismatched = [
            item.evidence_id
            for item in self.evidence_inputs
            if item.sku_code is not None and item.sku_code != self.sku_code
        ]
        if mismatched:
            raise ValueError(f"evidence_inputs contains mismatched sku_code: {', '.join(mismatched)}")
        return self


class CommentTopicSeed(Core3CommentEvidenceBaseModel):
    topic_code: str = Field(min_length=1)
    topic_name: str = Field(min_length=1)
    topic_group: str = Field(min_length=1)
    topic_definition: str | None = None
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    positive_keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    evidence_requirement: list[str] = Field(default_factory=list)
    dimension_paths: list[str] = Field(default_factory=list)
    mapped_claim_codes: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)
    activates_product_claim: bool = False
    service_guardrail: bool = False
    priority: int = Field(default=0, ge=0)

    @field_validator(
        "keywords",
        "positive_keywords",
        "negative_keywords",
        "aliases",
        "source_types",
        "evidence_requirement",
        "dimension_paths",
        "mapped_claim_codes",
        "mapped_task_codes",
        "mapped_battlefield_codes",
    )
    @classmethod
    def validate_seed_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment topic seed list values")


class CommentTopicSeedIndex(Core3CommentEvidenceBaseModel):
    seed_version: str = CORE3_M05_SEED_VERSION
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    topics: list[CommentTopicSeed] = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_topic_codes(self) -> "CommentTopicSeedIndex":
        topic_codes = [topic.topic_code for topic in self.topics]
        if len(topic_codes) != len(set(topic_codes)):
            raise ValueError("topic_code must be unique in comment topic seed")
        return self

    @property
    def topic_by_code(self) -> dict[str, CommentTopicSeed]:
        return {topic.topic_code: topic for topic in self.topics}


class DomainHint(Core3CommentEvidenceBaseModel):
    domain_hint: CommentDomainHint
    source_terms: list[str] = Field(default_factory=list)
    source_dimension_paths: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("source_terms", "source_dimension_paths", "evidence_ids")
    @classmethod
    def validate_domain_hint_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "domain hint list values")


class SentimentHint(Core3CommentEvidenceBaseModel):
    sentiment_hint: CommentSentimentHint
    sentiment_source: CommentSentimentSource = CommentSentimentSource.UNKNOWN
    source_values: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    conflict_flag: bool = False

    @field_validator("source_values")
    @classmethod
    def validate_source_values(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "sentiment source_values")


class CommentUnitCandidate(Core3CommentEvidenceBaseModel):
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    dedup_strategy: CommentDedupStrategy
    comment_id: str | None = None
    comment_text_hash: str | None = None
    source_row_ids: list[str] = Field(default_factory=list)
    canonical_comment_text: str | None = None
    source_evidence_ids: list[str] = Field(default_factory=list)
    raw_dimension_paths: list[str] = Field(default_factory=list)
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    low_value_flag: bool = False
    low_value_reasons: list[CommentLowValueReason] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)

    @field_validator("source_row_ids", "source_evidence_ids", "raw_dimension_paths")
    @classmethod
    def validate_candidate_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment unit candidate list values")

    @model_validator(mode="after")
    def validate_candidate_traceability(self) -> "CommentUnitCandidate":
        if not (self.comment_id or self.comment_text_hash or self.source_row_ids):
            raise ValueError("CommentUnitCandidate requires comment_id, comment_text_hash, or source_row_ids")
        return self


class CommentUnitRecord(Core3CommentEvidenceBaseModel):
    comment_unit_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_unit_key: str = Field(min_length=1)
    dedup_strategy: CommentDedupStrategy
    comment_id: str | None = None
    comment_text_hash: str | None = None
    source_row_id: str | None = None
    canonical_comment_text: str | None = None
    canonical_text_length: int = Field(default=0, ge=0)
    source_row_count: int = Field(default=0, ge=0)
    source_sentence_count: int = Field(default=0, ge=0)
    source_dimension_count: int = Field(default=0, ge=0)
    source_quality_issue_count: int = Field(default=0, ge=0)
    source_comment_evidence_ids: list[str] = Field(default_factory=list)
    source_sentence_evidence_ids: list[str] = Field(default_factory=list)
    source_dimension_evidence_ids: list[str] = Field(default_factory=list)
    source_quality_evidence_ids: list[str] = Field(default_factory=list)
    raw_dimension_paths: list[str] = Field(default_factory=list)
    sentiment_raw_set: list[str] = Field(default_factory=list)
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    sentiment_conflict_flag: bool = False
    low_value_flag: bool = False
    low_value_reasons: list[CommentLowValueReason] = Field(default_factory=list)
    duplicate_group_id: str | None = None
    duplicate_source_count: int = Field(default=0, ge=0)
    comment_unit_status: CommentUnitStatus = CommentUnitStatus.USABLE
    quality_flags: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    rule_version: str = CORE3_M05_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator(
        "source_comment_evidence_ids",
        "source_sentence_evidence_ids",
        "source_dimension_evidence_ids",
        "source_quality_evidence_ids",
        "raw_dimension_paths",
        "sentiment_raw_set",
        "quality_flags",
    )
    @classmethod
    def validate_unit_string_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment unit list values")

    @model_validator(mode="after")
    def validate_unit_traceability(self) -> "CommentUnitRecord":
        if not (self.comment_id or self.comment_text_hash or self.source_row_id):
            raise ValueError("CommentUnitRecord requires comment_id, comment_text_hash, or source_row_id")
        return self


class CommentUnitEvidenceLinkRecord(Core3CommentEvidenceBaseModel):
    unit_link_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_unit_id: str = Field(min_length=1)
    source_evidence_id: str = Field(min_length=1)
    source_evidence_type: Core3EvidenceType
    link_role: str = Field(min_length=1)
    source_row_id: str | None = None
    comment_id: str | None = None
    comment_text_hash: str | None = None
    sentence_hash: str | None = None
    dimension_path_raw: str | None = None
    quality_issue_type: str | None = None
    rule_version: str = CORE3_M05_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("source_evidence_type")
    @classmethod
    def validate_link_evidence_type(cls, evidence_type: Core3EvidenceType) -> Core3EvidenceType:
        if evidence_type not in CORE3_M05_ALLOWED_EVIDENCE_TYPES:
            raise ValueError(f"source_evidence_type is not allowed for M05: {evidence_type}")
        return evidence_type


class CommentSentenceCandidate(Core3CommentEvidenceBaseModel):
    comment_unit_id: str = Field(min_length=1)
    comment_unit_key: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    sentence_seq: int | None = Field(default=None, ge=0)
    sentence_hash: str | None = None
    sentence_text: str = Field(min_length=1)
    normalized_sentence_text: str = Field(min_length=1)
    sentence_source_priority: str = "raw_fallback"
    source_evidence_ids: list[str] = Field(min_length=1)
    raw_dimension_paths: list[str] = Field(default_factory=list)

    @field_validator("source_evidence_ids", "raw_dimension_paths")
    @classmethod
    def validate_sentence_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment sentence candidate list values")


class CommentEvidenceAtomRecord(Core3CommentEvidenceBaseModel):
    comment_evidence_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_evidence_key: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    comment_id: str | None = None
    comment_text_hash: str | None = None
    sentence_hash: str | None = None
    sentence_seq: int | None = Field(default=None, ge=0)
    sentence_source_priority: str = "raw_fallback"
    sentence_text: str = Field(min_length=1)
    normalized_sentence_text: str = Field(min_length=1)
    sentence_length: int = Field(default=0, ge=0)
    source_evidence_ids: list[str] = Field(min_length=1)
    source_sentence_evidence_ids: list[str] = Field(default_factory=list)
    source_comment_evidence_ids: list[str] = Field(default_factory=list)
    source_dimension_evidence_ids: list[str] = Field(default_factory=list)
    source_quality_evidence_ids: list[str] = Field(default_factory=list)
    raw_dimension_paths: list[str] = Field(default_factory=list)
    domain_hints: list[DomainHint] = Field(default_factory=list)
    primary_domain_hint: CommentDomainHint = CommentDomainHint.UNKNOWN
    domain_conflict_flag: bool = False
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    sentiment_source: CommentSentimentSource = CommentSentimentSource.UNKNOWN
    sentiment_conflict_flag: bool = False
    low_value_flag: bool = False
    low_value_reasons: list[CommentLowValueReason] = Field(default_factory=list)
    duplicate_group_id: str | None = None
    sentence_duplicate_group_id: str | None = None
    specificity_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    representative_phrase: str | None = None
    representative_phrase_rule: str | None = None
    usable_for_downstream: bool = True
    downstream_block_reasons: list[str] = Field(default_factory=list)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    rule_version: str = CORE3_M05_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator(
        "source_evidence_ids",
        "source_sentence_evidence_ids",
        "source_comment_evidence_ids",
        "source_dimension_evidence_ids",
        "source_quality_evidence_ids",
        "raw_dimension_paths",
        "downstream_block_reasons",
    )
    @classmethod
    def validate_atom_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment evidence atom list values")

    @model_validator(mode="after")
    def validate_downstream_block_reason(self) -> "CommentEvidenceAtomRecord":
        if not self.usable_for_downstream and not self.downstream_block_reasons:
            raise ValueError("downstream_block_reasons is required when usable_for_downstream is false")
        return self


class TopicHintRecord(Core3CommentEvidenceBaseModel):
    topic_hint_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_evidence_id: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    topic_code: str = Field(min_length=1)
    topic_name: str = Field(min_length=1)
    topic_group: str = Field(min_length=1)
    topic_definition: str | None = None
    match_method: CommentTopicMatchMethod
    matched_terms: list[str] = Field(default_factory=list)
    match_source_json: dict[str, Any] = Field(default_factory=dict)
    polarity_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    topic_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    is_weak_hint: bool = True
    activates_product_claim: bool = False
    service_guardrail_flag: bool = False
    mapped_claim_codes_snapshot: list[str] = Field(default_factory=list)
    mapped_task_codes_snapshot: list[str] = Field(default_factory=list)
    mapped_battlefield_codes_snapshot: list[str] = Field(default_factory=list)
    topic_hint_status: CommentTopicHintStatus = CommentTopicHintStatus.MATCHED
    rule_version: str = CORE3_M05_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator(
        "matched_terms",
        "mapped_claim_codes_snapshot",
        "mapped_task_codes_snapshot",
        "mapped_battlefield_codes_snapshot",
    )
    @classmethod
    def validate_topic_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment topic hint list values")

    @model_validator(mode="after")
    def validate_weak_hint_boundary(self) -> "TopicHintRecord":
        if not self.is_weak_hint:
            raise ValueError("M05 topic hints must remain weak hints")
        return self


class CommentQualityProfileRecord(Core3CommentEvidenceBaseModel):
    comment_quality_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    profile_key: str = Field(min_length=1)
    raw_comment_row_count: int = Field(default=0, ge=0)
    comment_unit_count: int = Field(default=0, ge=0)
    distinct_comment_id_count: int = Field(default=0, ge=0)
    distinct_comment_text_count: int = Field(default=0, ge=0)
    sentence_count: int = Field(default=0, ge=0)
    usable_sentence_count: int = Field(default=0, ge=0)
    low_value_unit_count: int = Field(default=0, ge=0)
    low_value_sentence_count: int = Field(default=0, ge=0)
    duplicate_text_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    duplicate_row_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    empty_dimension_count: int = Field(default=0, ge=0)
    empty_dimension_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    sentiment_distribution_json: dict[str, int] = Field(default_factory=dict)
    sentiment_unknown_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    sentiment_conflict_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    domain_distribution_json: dict[str, int] = Field(default_factory=dict)
    topic_distribution_json: dict[str, int] = Field(default_factory=dict)
    service_installation_share: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    product_experience_share: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    negative_sentence_rate: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    sample_status: CommentSampleStatus = CommentSampleStatus.UNKNOWN
    comment_usability_score: Decimal = Field(default=Decimal("0.000000"), ge=0, le=1)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    warning_flags: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    downstream_ready: bool = False
    rule_version: str = CORE3_M05_RULE_VERSION
    asset_version: str = "default"
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("warning_flags", "blocked_reasons")
    @classmethod
    def validate_profile_lists(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "comment quality profile list values")

    @field_validator("sentiment_distribution_json")
    @classmethod
    def validate_sentiment_distribution(cls, values: dict[str, int]) -> dict[str, int]:
        allowed = {item.value for item in CommentSentimentHint}
        return _validate_count_map(values, allowed, "sentiment_distribution_json")

    @field_validator("domain_distribution_json")
    @classmethod
    def validate_domain_distribution(cls, values: dict[str, int]) -> dict[str, int]:
        allowed = {item.value for item in CommentDomainHint}
        return _validate_count_map(values, allowed, "domain_distribution_json")

    @model_validator(mode="after")
    def validate_profile_consistency(self) -> "CommentQualityProfileRecord":
        if self.usable_sentence_count > self.sentence_count:
            raise ValueError("usable_sentence_count must be <= sentence_count")
        if self.low_value_sentence_count > self.sentence_count:
            raise ValueError("low_value_sentence_count must be <= sentence_count")
        if self.low_value_unit_count > self.comment_unit_count:
            raise ValueError("low_value_unit_count must be <= comment_unit_count")
        if not self.downstream_ready and not self.blocked_reasons:
            raise ValueError("blocked_reasons is required when downstream_ready is false")
        return self


class M05ReviewIssue(Core3CommentEvidenceBaseModel):
    issue_code: str = Field(min_length=1)
    reason_code: CommentReviewReasonCode
    severity: Core3ReviewSeverity
    object_type: str = Field(min_length=1)
    object_id: str | None = None
    sku_code: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    message_cn: str = Field(min_length=1)
    suggestion_cn: str | None = None
    review_required: bool = True
    confidence: Decimal | None = Field(default=None, ge=0, le=1)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "evidence_refs")


class M05DownstreamImpact(Core3CommentEvidenceBaseModel):
    target_module: Core3ModuleCode
    sku_code: str | None = None
    impact_level: Core3SourceImpactLevel
    changed_object_count: int = Field(default=0, ge=0)
    reason_cn: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("evidence_refs")
    @classmethod
    def validate_impact_evidence_refs(cls, values: list[str]) -> list[str]:
        return _validate_non_empty_strings(values, "evidence_refs")


def _validate_count_map(values: dict[str, int], allowed_values: set[str], label: str) -> dict[str, int]:
    for key, count in values.items():
        if key not in allowed_values:
            raise ValueError(f"unknown {label}: {key}")
        if count < 0:
            raise ValueError(f"negative count for {key}")
    return values
