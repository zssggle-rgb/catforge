"""M16 pipeline governance contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.core3_real_data.constants import (
    CORE3_DEFAULT_RULESET_VERSION,
    CORE3_M16_MODULE_VERSION,
    CORE3_M16_RULE_VERSION,
    Core3CategoryCode,
    Core3DataDomain,
    Core3ModuleCode,
    Core3PipelineAcceptanceStatus,
    Core3PipelineDependencyStatus,
    Core3PipelinePlannedAction,
    Core3PipelineReviewDecisionType,
    Core3PipelineReviewStatus,
    Core3PipelineTriggerType,
    Core3ReleaseGateStatus,
    Core3ReviewSeverity,
    Core3RunMode,
    Core3RunStatus,
    Core3TargetScopeType,
)


class M16BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M16TargetScope(M16BaseModel):
    scope_type: Core3TargetScopeType = Core3TargetScopeType.ALL_SKU
    sku_codes: list[str] = Field(default_factory=list)
    include_related_targets: bool = True
    related_target_reason: str | None = None
    data_domains: list[Core3DataDomain] = Field(default_factory=list)
    note_cn: str | None = None


class M16PipelineRunRequest(M16BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    parent_run_id: str | None = None
    data_batch_id: str | None = None
    run_mode: Core3RunMode = Core3RunMode.ACCEPTANCE_ONLY
    trigger_type: Core3PipelineTriggerType = Core3PipelineTriggerType.MANUAL
    triggered_by: str = "system"
    target_scope: M16TargetScope = Field(default_factory=M16TargetScope)
    ruleset_version: str = CORE3_DEFAULT_RULESET_VERSION
    module_version: str = CORE3_M16_MODULE_VERSION
    rule_version: str = CORE3_M16_RULE_VERSION
    module_versions: dict[str, str] = Field(default_factory=dict)
    seed_versions: dict[str, str] = Field(default_factory=dict)
    input_watermarks: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_module_versions(self) -> "M16PipelineRunRequest":
        if Core3ModuleCode.M16.value not in self.module_versions:
            self.module_versions[Core3ModuleCode.M16.value] = self.module_version
        return self


class M16RecomputePlanRecord(M16BaseModel):
    plan_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    module_code: Core3ModuleCode
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    start_from_module: Core3ModuleCode
    change_domain: str = "report"
    change_reason_cn: str = Field(min_length=1)
    upstream_dependency_hash: str | None = None
    previous_output_hash: str | None = None
    planned_action: Core3PipelinePlannedAction = Core3PipelinePlannedAction.REUSE
    priority: int = Field(default=100, ge=0)
    related_targets_json: dict[str, Any] = Field(default_factory=dict)
    plan_reason_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class M16ModuleRunRecord(M16BaseModel):
    module_run_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    module_code: Core3ModuleCode
    target_scope: str = "batch"
    target_id: str | None = None
    batch_id: str | None = None
    status: Core3RunStatus
    input_count: int = Field(default=0, ge=0)
    changed_input_count: int = Field(default=0, ge=0)
    output_count: int = Field(default=0, ge=0)
    output_hash: str | None = None
    warnings_json: list[str] = Field(default_factory=list)
    review_issue_summary_json: dict[str, Any] = Field(default_factory=dict)
    downstream_impact_json: dict[str, Any] = Field(default_factory=dict)
    summary_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message_cn: str | None = None


class M16DependencySnapshotRecord(M16BaseModel):
    dependency_snapshot_id: str = Field(min_length=1)
    module_run_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    module_code: Core3ModuleCode
    upstream_module_code: Core3ModuleCode
    upstream_target_id: str | None = None
    upstream_output_hash: str | None = None
    rule_version: str | None = None
    seed_version_json: dict[str, Any] = Field(default_factory=dict)
    dependency_status: Core3PipelineDependencyStatus = Core3PipelineDependencyStatus.VALID
    reused_from_module_run_id: str | None = None


class M16ReviewQueueRecord(M16BaseModel):
    review_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    source_module_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    module_code: Core3ModuleCode
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_sku_code: str | None = None
    candidate_sku_code: str | None = None
    object_type: str = "run"
    object_id: str = ""
    issue_type: str = Field(min_length=1)
    severity: Core3ReviewSeverity = Core3ReviewSeverity.MEDIUM
    issue_title_cn: str = Field(min_length=1)
    issue_detail_cn: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_flags_json: list[str] = Field(default_factory=list)
    suggested_action_cn: str = Field(min_length=1)
    review_status: Core3PipelineReviewStatus = Core3PipelineReviewStatus.PENDING
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    resolution_note_cn: str | None = None
    is_blocking_release: bool = False
    source_issue_table: str | None = None
    source_issue_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class M16ReviewDecisionRequest(M16BaseModel):
    decision_type: Core3PipelineReviewDecisionType
    decision_reason_cn: str = Field(min_length=1)
    impact_scope_json: dict[str, Any] = Field(default_factory=dict)
    need_recompute: bool = False
    recompute_mode: Core3RunMode | None = None
    decided_by: str = "system"


class M16ReviewDecisionRecord(M16BaseModel):
    decision_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decision_type: Core3PipelineReviewDecisionType
    decision_reason_cn: str = Field(min_length=1)
    impact_scope_json: dict[str, Any] = Field(default_factory=dict)
    need_recompute: bool = False
    recompute_mode: str | None = None
    created_followup_run_id: str | None = None
    decided_by: str = "system"
    decided_at: datetime


class M16AcceptanceReportRecord(M16BaseModel):
    acceptance_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    data_batch_id: str | None = None
    processed_sku_count: int = Field(ge=0)
    processed_target_count: int = Field(ge=0)
    report_ready_count: int = Field(ge=0)
    high_confidence_report_count: int = Field(ge=0)
    medium_confidence_report_count: int = Field(ge=0)
    limited_report_count: int = Field(ge=0)
    blocked_report_count: int = Field(ge=0)
    avg_competitor_count: Decimal
    direct_slot_fill_rate: Decimal
    pressure_slot_fill_rate: Decimal
    benchmark_slot_fill_rate: Decimal
    evidence_coverage_rate: Decimal
    review_pending_count: int = Field(ge=0)
    blocker_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    acceptance_status: Core3PipelineAcceptanceStatus
    acceptance_summary_cn: str = Field(min_length=1)
    data_scope_note_cn: str = Field(min_length=1)
    module_status_summary_json: dict[str, Any] = Field(default_factory=dict)
    report_status_summary_json: dict[str, Any] = Field(default_factory=dict)
    quality_gate_json: dict[str, Any] = Field(default_factory=dict)
    acceptance_detail_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class M16ReleaseGateRecord(M16BaseModel):
    release_gate_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    report_payload_id: str | None = None
    selection_run_id: str | None = None
    gate_status: Core3ReleaseGateStatus
    gate_reason_cn: str = Field(min_length=1)
    required_review_ids: list[str] = Field(default_factory=list)
    warning_review_ids: list[str] = Field(default_factory=list)
    data_scope_note_cn: str = Field(min_length=1)
    display_badges_json: list[dict[str, Any]] = Field(default_factory=list)
    gate_check_json: dict[str, Any] = Field(default_factory=dict)
    released_by: str | None = None
    released_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class M16PipelineRunResponse(M16BaseModel):
    run_id: str = Field(min_length=1)
    parent_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_mode: Core3RunMode
    trigger_type: str
    triggered_by: str
    data_batch_id: str | None = None
    target_scope_json: dict[str, Any] = Field(default_factory=dict)
    ruleset_version: str
    module_version_json: dict[str, Any] = Field(default_factory=dict)
    seed_version_json: dict[str, Any] = Field(default_factory=dict)
    input_watermark_json: dict[str, Any] = Field(default_factory=dict)
    status: Core3RunStatus
    release_status: Core3ReleaseGateStatus
    output_summary_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message_cn: str | None = None
    summary_cn: str | None = None


class M16ListResponse(M16BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None
