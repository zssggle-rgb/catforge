"""M14 core competitor selection contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M14_RULE_VERSION,
    Core3CategoryCode,
    Core3RunStatus,
    M14AuditDecision,
    M14IssueLevel,
    M14IssueScope,
    M14PressureLevel,
    M14SelectionSlot,
    M14SelectionStatus,
    M14SlotDecisionStatus,
)


class M14BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M14CompetitorSelectionRunRecord(M14BaseModel):
    selection_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    candidate_count: int = Field(default=0, ge=0)
    scored_candidate_count: int = Field(default=0, ge=0)
    selected_count: int = Field(default=0, ge=0, le=3)
    empty_slot_count: int = Field(default=0, ge=0, le=3)
    review_candidate_count: int = Field(default=0, ge=0)
    blocked_candidate_count: int = Field(default=0, ge=0)
    selection_status: M14SelectionStatus = M14SelectionStatus.SUCCESS
    selection_summary_cn: str = Field(min_length=1)
    empty_slots_json: list[dict[str, Any]] = Field(default_factory=list)
    selection_policy_json: dict[str, Any] = Field(default_factory=dict)
    target_profile_hash: str = Field(min_length=1)
    m12_recall_fingerprint: str = Field(min_length=1)
    m13_score_fingerprint: str = Field(min_length=1)
    evidence_revision: str = "m14_evidence_revision_v1"
    rule_version: str = CORE3_M14_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M14CompetitorSelectionRecord(M14BaseModel):
    competitor_selection_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    candidate_role_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    same_brand_flag: bool = False
    slot_code: M14SelectionSlot
    slot_name_cn: str = Field(min_length=1)
    selection_rank: int = Field(default=1, ge=1, le=3)
    primary_battlefield_code: str | None = None
    primary_battlefield_name: str | None = None
    slot_selection_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    role_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    component_total_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_completeness_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    pressure_level: M14PressureLevel = M14PressureLevel.MEDIUM
    selection_reason_cn: str = Field(min_length=1)
    selection_reason_short_cn: str = Field(min_length=1)
    business_conclusion_cn: str = Field(min_length=1)
    strategy_hint_cn: str | None = None
    risk_summary_cn: str | None = None
    component_scores_json: dict[str, Any] = Field(default_factory=dict)
    role_scores_json: dict[str, Any] = Field(default_factory=dict)
    selection_evidence_json: dict[str, Any] = Field(default_factory=dict)
    selected_by_rules_json: list[dict[str, Any] | str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    positive_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    target_profile_hash: str = Field(min_length=1)
    candidate_profile_hash: str = Field(min_length=1)
    m13_score_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M14_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M14SlotDecisionRecord(M14BaseModel):
    slot_decision_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    selected_competitor_selection_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    candidate_sku_code: str | None = None
    candidate_model_name: str | None = None
    slot_code: M14SelectionSlot
    slot_name_cn: str = Field(min_length=1)
    decision_status: M14SlotDecisionStatus = M14SlotDecisionStatus.EMPTY
    selected_candidate_count: int = Field(default=0, ge=0, le=1)
    slot_candidate_count: int = Field(default=0, ge=0)
    empty_reason_code: str | None = None
    empty_reason_cn: str | None = None
    review_reason: str | None = None
    top_candidate_sku_code: str | None = None
    top_candidate_model_name: str | None = None
    top_candidate_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    decision_confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    decision_summary_cn: str = Field(min_length=1)
    decision_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M14_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M14SelectionAuditRecord(M14BaseModel):
    selection_audit_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    evaluated_slot_codes_json: list[str] = Field(default_factory=list)
    audit_decision: M14AuditDecision = M14AuditDecision.REJECTED
    selected_slot_code: str | None = None
    best_slot_code: str | None = None
    decision_reason_cn: str = Field(min_length=1)
    failed_conditions_json: list[dict[str, Any] | str] = Field(default_factory=list)
    slot_scores_json: dict[str, Any] = Field(default_factory=dict)
    candidate_total_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    best_role_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_completeness_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    confidence: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    duplicate_with_candidate_sku_code: str | None = None
    business_distinctiveness_score: Decimal = Field(default=Decimal("0.8000"), ge=0, le=1)
    strategic_value_score: Decimal = Field(default=Decimal("0.0000"), ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M14_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M14SelectionReviewIssueRecord(M14BaseModel):
    selection_review_issue_id: str = Field(min_length=1)
    selection_run_id: str | None = None
    competitor_selection_id: str | None = None
    slot_decision_id: str | None = None
    selection_audit_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    slot_code: str = ""
    candidate_sku_code: str = ""
    issue_scope: M14IssueScope = M14IssueScope.CANDIDATE
    issue_type: str = Field(min_length=1)
    issue_level: M14IssueLevel = M14IssueLevel.WARNING
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str | None = None
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    resolved_by: str | None = None
    resolution_note: str | None = None
    rule_version: str = CORE3_M14_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M14BuildArtifacts:
    selection_run: M14CompetitorSelectionRunRecord
    selections: tuple[M14CompetitorSelectionRecord, ...] = field(default_factory=tuple)
    slot_decisions: tuple[M14SlotDecisionRecord, ...] = field(default_factory=tuple)
    audits: tuple[M14SelectionAuditRecord, ...] = field(default_factory=tuple)
    review_issues: tuple[M14SelectionReviewIssueRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class M14ServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    warnings: list[str]
    selection_runs: list[M14CompetitorSelectionRunRecord]
    selections: list[M14CompetitorSelectionRecord]
    slot_decisions: list[M14SlotDecisionRecord]
    audits: list[M14SelectionAuditRecord]
    review_issues: list[M14SelectionReviewIssueRecord]
    summary: dict[str, Any]
