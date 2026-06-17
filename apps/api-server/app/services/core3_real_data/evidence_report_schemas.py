"""M15 evidence card and executive report contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import (
    CORE3_M15_RULE_VERSION,
    Core3CategoryCode,
    Core3RunStatus,
    M15ConfidenceLabel,
    M15ReadinessLevel,
    M15ReportExportStatus,
    M15ReportExportType,
    M15ReportIssueLevel,
    M15ReportIssueScope,
    M15ReportSectionCode,
    M15ReportSectionDisplayStatus,
)


class M15BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M15EvidenceCardRecord(M15BaseModel):
    evidence_card_id: str = Field(min_length=1)
    card_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    selection_id: str = Field(min_length=1)
    component_score_id: str | None = None
    candidate_pool_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_display_name_cn: str = Field(min_length=1)
    competitor_sku_code: str = Field(min_length=1)
    competitor_model_name: str | None = None
    competitor_brand_name: str | None = None
    competitor_display_name_cn: str = Field(min_length=1)
    slot_code: str = Field(min_length=1)
    slot_name_cn: str = Field(min_length=1)
    primary_battlefield_code: str | None = None
    primary_battlefield_name_cn: str = Field(min_length=1)
    pressure_level_cn: str = Field(min_length=1)
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.READY
    confidence_label_cn: str = Field(min_length=1)
    headline_cn: str = Field(min_length=1)
    summary_cn: str = Field(min_length=1)
    one_sentence_reason_cn: str = Field(min_length=1)
    price_evidence_cn: str | None = None
    channel_evidence_cn: str | None = None
    param_evidence_cn: str | None = None
    claim_value_evidence_cn: str | None = None
    task_audience_evidence_cn: str | None = None
    market_evidence_cn: str | None = None
    comment_evidence_cn: str | None = None
    evidence_matrix_json: list[dict[str, Any]] = Field(default_factory=list)
    key_difference_cn: str = Field(min_length=1)
    target_advantage_cn: str = Field(min_length=1)
    competitor_advantage_cn: str = Field(min_length=1)
    strategy_implication_cn: str = Field(min_length=1)
    risk_note_cn: str | None = None
    short_evidence_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    display_payload_json: dict[str, Any] = Field(default_factory=dict)
    export_payload_json: dict[str, Any] = Field(default_factory=dict)
    selection_result_hash: str = Field(min_length=1)
    rule_version: str = CORE3_M15_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M15TargetReportPayloadRecord(M15BaseModel):
    target_report_payload_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    target_display_name_cn: str = Field(min_length=1)
    report_title_cn: str = Field(min_length=1)
    executive_conclusion_cn: str = Field(min_length=1)
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.REVIEW_REQUIRED
    confidence_label_cn: str = Field(min_length=1)
    data_scope_note_cn: str = Field(min_length=1)
    target_profile_summary_cn: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    selected_count: int = Field(default=0, ge=0, le=3)
    empty_slot_count: int = Field(default=0, ge=0, le=3)
    battlefield_summary_json: dict[str, Any] = Field(default_factory=dict)
    task_group_summary_json: dict[str, Any] = Field(default_factory=dict)
    target_signal_cards_json: list[dict[str, Any]] = Field(default_factory=list)
    core_competitors_json: list[dict[str, Any]] = Field(default_factory=list)
    empty_slots_json: list[dict[str, Any]] = Field(default_factory=list)
    why_competitor_logic_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix_json: list[dict[str, Any]] = Field(default_factory=list)
    key_difference_json: list[dict[str, Any]] = Field(default_factory=list)
    strategy_hint_json: list[dict[str, Any]] = Field(default_factory=list)
    sop_trace_json: list[dict[str, Any]] = Field(default_factory=list)
    candidate_pool_summary_json: dict[str, Any] = Field(default_factory=dict)
    review_questions_json: list[dict[str, Any]] = Field(default_factory=list)
    data_quality_note_cn: str = Field(min_length=1)
    short_evidence_map_json: list[dict[str, Any]] = Field(default_factory=list)
    export_payload_json: dict[str, Any] = Field(default_factory=dict)
    ui_guardrail_result_json: dict[str, Any] = Field(default_factory=dict)
    m14_selection_fingerprint: str = Field(min_length=1)
    evidence_revision: str | None = None
    rule_version: str = CORE3_M15_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M15ReportSectionRecord(M15BaseModel):
    report_section_id: str = Field(min_length=1)
    target_report_payload_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    section_code: M15ReportSectionCode
    section_title_cn: str = Field(min_length=1)
    section_order: int = Field(ge=1)
    section_payload_json: dict[str, Any] = Field(default_factory=dict)
    display_status: M15ReportSectionDisplayStatus = M15ReportSectionDisplayStatus.VISIBLE
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.READY
    contains_internal_field_flag: bool = False
    contains_uuid_flag: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    short_evidence_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    rule_version: str = CORE3_M15_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M15ReportExportRecord(M15BaseModel):
    report_export_id: str = Field(min_length=1)
    target_report_payload_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    export_type: M15ReportExportType
    export_title_cn: str = Field(min_length=1)
    export_payload: str = Field(min_length=1)
    export_payload_json: dict[str, Any] = Field(default_factory=dict)
    data_scope_note_cn: str = Field(min_length=1)
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.READY
    checksum: str = Field(min_length=1)
    page_payload_hash: str = Field(min_length=1)
    export_status: M15ReportExportStatus = M15ReportExportStatus.READY
    failure_reason: str | None = None
    rule_version: str = CORE3_M15_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


class M15ReportReviewIssueRecord(M15BaseModel):
    report_review_issue_id: str = Field(min_length=1)
    target_report_payload_id: str | None = None
    evidence_card_id: str | None = None
    report_section_id: str | None = None
    report_export_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    issue_scope: M15ReportIssueScope = M15ReportIssueScope.REPORT
    section_code: str = ""
    issue_type: str = Field(min_length=1)
    issue_level: M15ReportIssueLevel = M15ReportIssueLevel.WARNING
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str | None = None
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    resolved_by: str | None = None
    resolution_note: str | None = None
    rule_version: str = CORE3_M15_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class M15BuildArtifacts:
    evidence_cards: tuple[M15EvidenceCardRecord, ...] = ()
    report_payloads: tuple[M15TargetReportPayloadRecord, ...] = ()
    report_sections: tuple[M15ReportSectionRecord, ...] = ()
    report_exports: tuple[M15ReportExportRecord, ...] = ()
    review_issues: tuple[M15ReportReviewIssueRecord, ...] = ()


@dataclass(frozen=True)
class M15ServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int
    summary: dict[str, Any]
    warnings: list[str]
    review_issues: tuple[M15ReportReviewIssueRecord, ...]
    artifacts: M15BuildArtifacts
