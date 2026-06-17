"""M08.4 comment-native business dimension discovery contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import CORE3_M08_4_RULE_VERSION, CORE3_M08_4_SEED_VERSION, Core3RunStatus


class M084BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M084NativeSignalRecord(M084BaseModel):
    native_signal_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    native_signal_code: str
    native_signal_name_cn: str
    signal_type: str
    source_comment_domain: str = "unknown"
    sentence_count: int = Field(default=0, ge=0)
    sku_count: int = Field(default=0, ge=0)
    strong_sentence_count: int = Field(default=0, ge=0)
    positive_sentence_count: int = Field(default=0, ge=0)
    negative_sentence_count: int = Field(default=0, ge=0)
    service_sentence_count: int = Field(default=0, ge=0)
    low_value_excluded_count: int = Field(default=0, ge=0)
    avg_strength_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    specificity_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    comment_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    native_keyword_json: dict[str, Any] = Field(default_factory=dict)
    sku_distribution_json: dict[str, Any] = Field(default_factory=dict)
    representative_phrase_json: list[Any] = Field(default_factory=list)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    product_anchor_hint_json: dict[str, Any] = Field(default_factory=dict)
    service_context_flag: bool = False
    signal_status: str = "active"
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    source_rule_version: str = CORE3_M08_4_RULE_VERSION
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M084NativeDimensionCandidateRecord(M084BaseModel):
    native_dimension_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    dimension_type: str
    native_dimension_code: str
    native_dimension_name_cn: str
    definition_draft_cn: str
    source_signal_codes: list[str] = Field(default_factory=list)
    include_keyword_json: dict[str, Any] = Field(default_factory=dict)
    exclude_keyword_json: dict[str, Any] = Field(default_factory=dict)
    sentence_count: int = Field(default=0, ge=0)
    sku_count: int = Field(default=0, ge=0)
    strong_sku_count: int = Field(default=0, ge=0)
    native_support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    product_anchor_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    distinctiveness_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    representative_phrase_json: list[Any] = Field(default_factory=list)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    support_summary_json: dict[str, Any] = Field(default_factory=dict)
    service_context_flag: bool = False
    candidate_status: str = "candidate"
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M08_4_RULE_VERSION
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M084SkuSupportRecord(M084BaseModel):
    native_dimension_sku_support_id: str
    native_dimension_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str
    model_name: str | None = None
    brand_name: str | None = None
    dimension_type: str
    native_dimension_code: str
    comment_sentence_count: int = Field(default=0, ge=0)
    comment_support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    product_anchor_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    market_anchor_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    support_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    support_level: str = "weak"
    evidence_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    support_reason_cn: str
    service_context_flag: bool = False
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M08_4_RULE_VERSION
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M084AlignmentProposalRecord(M084BaseModel):
    alignment_proposal_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    native_dimension_id: str | None = None
    alignment_key: str
    seed_dimension_type: str
    seed_dimension_code: str | None = None
    seed_dimension_name_cn: str | None = None
    native_dimension_code: str | None = None
    native_dimension_name_cn: str | None = None
    alignment_relation: str = "unmatched"
    alignment_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    proposed_action: str = "review"
    reason_cn: str
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    downstream_effect_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = True
    review_status: str = "open"
    rule_version: str = CORE3_M08_4_RULE_VERSION
    seed_version: str = CORE3_M08_4_SEED_VERSION
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M084ReviewIssueRecord(M084BaseModel):
    native_dimension_issue_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    issue_key: str
    issue_code: str
    issue_type: str
    severity: str = "warning"
    object_type: str
    object_code: str
    issue_message_cn: str
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    suggested_action_cn: str
    review_status: str = "open"
    rule_version: str = CORE3_M08_4_RULE_VERSION
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


@dataclass(frozen=True)
class M084ServiceResult:
    signals: tuple[M084NativeSignalRecord, ...]
    candidates: tuple[M084NativeDimensionCandidateRecord, ...]
    sku_supports: tuple[M084SkuSupportRecord, ...]
    alignments: tuple[M084AlignmentProposalRecord, ...]
    issues: tuple[M084ReviewIssueRecord, ...]
    summary: dict[str, Any]
    warnings: list[str]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int = 0
