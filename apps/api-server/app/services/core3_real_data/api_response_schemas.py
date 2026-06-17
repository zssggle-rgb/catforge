"""Business-facing API schemas for Core3 real-data v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiQueryError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message_cn: str,
        action_hint_cn: str | None = None,
    ) -> None:
        super().__init__(message_cn)
        self.status_code = status_code
        self.error_code = error_code
        self.message_cn = message_cn
        self.action_hint_cn = action_hint_cn


class Core3ApiBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Core3V2DataScopeResponse(Core3ApiBaseModel):
    period_cn: str = "当前样例数据内"
    channel_scope_cn: str = "样例覆盖渠道"
    platform_scope_cn: str = "样例覆盖平台"
    sample_note_cn: str = "当前结果仅代表已接入数据，不代表全市场最终结论。"
    data_scope_note_cn: str = Field(min_length=1)
    updated_at: datetime | None = None


class Core3V2ReleaseStatusResponse(Core3ApiBaseModel):
    status_code: str = Field(min_length=1)
    status_name_cn: str = Field(min_length=1)
    gate_reason_cn: str = Field(min_length=1)
    data_scope_note_cn: str = Field(min_length=1)
    review_hint_cn: str | None = None
    can_present: bool = False
    can_release: bool = False


class Core3V2TargetProfileResponse(Core3ApiBaseModel):
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    size_segment_cn: str | None = None
    price_band_cn: str | None = None
    data_status_cn: str = "已生成竞品报告"


class Core3V2EvidenceShortRefResponse(Core3ApiBaseModel):
    short_ref: str = Field(min_length=1)
    evidence_domain_cn: str | None = None
    evidence_title_cn: str | None = None
    source_cn: str | None = None
    snippet_cn: str | None = None


class Core3V2CoreCompetitorResponse(Core3ApiBaseModel):
    competitor_sku_code: str = Field(min_length=1)
    competitor_model_name: str | None = None
    competitor_brand_name: str | None = None
    competitor_display_name_cn: str = Field(min_length=1)
    role_code: str = Field(min_length=1)
    role_name_cn: str = Field(min_length=1)
    one_sentence_reason_cn: str = Field(min_length=1)
    battlefield_fit_cn: str = Field(min_length=1)
    market_pressure_cn: str = Field(min_length=1)
    key_difference_cn: str = Field(min_length=1)
    target_advantage_cn: str = Field(min_length=1)
    competitor_advantage_cn: str = Field(min_length=1)
    strategy_implication_cn: str = Field(min_length=1)
    confidence_label_cn: str = Field(min_length=1)
    risk_note_cn: str | None = None
    evidence_short_refs: list[Core3V2EvidenceShortRefResponse] = Field(default_factory=list)


class Core3V2EvidenceCardBusinessResponse(Core3ApiBaseModel):
    target_sku_code: str = Field(min_length=1)
    target_display_name_cn: str = Field(min_length=1)
    competitor_sku_code: str = Field(min_length=1)
    competitor_display_name_cn: str = Field(min_length=1)
    role_code: str = Field(min_length=1)
    role_name_cn: str = Field(min_length=1)
    headline_cn: str = Field(min_length=1)
    summary_cn: str = Field(min_length=1)
    one_sentence_reason_cn: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    confidence_label_cn: str = Field(min_length=1)
    price_evidence_cn: str | None = None
    channel_evidence_cn: str | None = None
    param_evidence_cn: str | None = None
    claim_value_evidence_cn: str | None = None
    task_audience_evidence_cn: str | None = None
    market_evidence_cn: str | None = None
    comment_evidence_cn: str | None = None
    key_difference_cn: str = Field(min_length=1)
    target_advantage_cn: str = Field(min_length=1)
    competitor_advantage_cn: str = Field(min_length=1)
    strategy_implication_cn: str = Field(min_length=1)
    risk_note_cn: str | None = None
    evidence_short_refs: list[Core3V2EvidenceShortRefResponse] = Field(default_factory=list)


class Core3V2ReportSectionBusinessResponse(Core3ApiBaseModel):
    section_code: str = Field(min_length=1)
    section_title_cn: str = Field(min_length=1)
    section_order: int = Field(ge=0)
    display_status_cn: str = Field(min_length=1)
    section_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_short_refs: list[Core3V2EvidenceShortRefResponse] = Field(default_factory=list)


class Core3V2ReviewHintResponse(Core3ApiBaseModel):
    review_required: bool = False
    severity_name_cn: str | None = None
    message_cn: str = Field(min_length=1)
    suggested_action_cn: str | None = None
    review_count: int = Field(default=0, ge=0)


class Core3V2ExportBusinessResponse(Core3ApiBaseModel):
    export_type: str = Field(min_length=1)
    export_title_cn: str = Field(min_length=1)
    export_payload: str = Field(min_length=1)
    data_scope_note_cn: str = Field(min_length=1)
    export_status_cn: str = Field(min_length=1)
    failure_reason: str | None = None
    media_type: str = "text/plain; charset=utf-8"


class Core3V2BusinessReportResponse(Core3ApiBaseModel):
    project_id: str = Field(min_length=1)
    category_code: str = "TV"
    target: Core3V2TargetProfileResponse
    report_title_cn: str = Field(min_length=1)
    executive_conclusion_cn: str = Field(min_length=1)
    data_scope: Core3V2DataScopeResponse
    release_status: Core3V2ReleaseStatusResponse
    core_competitors: list[Core3V2CoreCompetitorResponse] = Field(default_factory=list)
    why_these_competitors_cn: str = Field(min_length=1)
    battlefield_summary_cn: str = Field(min_length=1)
    evidence_cards: list[Core3V2EvidenceCardBusinessResponse] = Field(default_factory=list)
    sections: list[Core3V2ReportSectionBusinessResponse] = Field(default_factory=list)
    candidate_audit: dict[str, Any] = Field(default_factory=dict)
    review_hint: Core3V2ReviewHintResponse
    exports: list[Core3V2ExportBusinessResponse] = Field(default_factory=list)
    data_quality_note_cn: str = Field(min_length=1)


class Core3V2SkuResolveResponse(Core3ApiBaseModel):
    status: str = Field(min_length=1)
    query: str = Field(min_length=1)
    target: Core3V2TargetProfileResponse | None = None
    candidates: list[Core3V2TargetProfileResponse] = Field(default_factory=list)
    message_cn: str = Field(min_length=1)
    action_hint_cn: str | None = None


class Core3V2TargetSummaryResponse(Core3ApiBaseModel):
    target_sku_code: str = Field(min_length=1)
    target_display_name_cn: str = Field(min_length=1)
    brand_name: str | None = None
    report_title_cn: str | None = None
    release_status: Core3V2ReleaseStatusResponse
    selected_count: int = Field(default=0, ge=0)
    competitor_names_cn: list[str] = Field(default_factory=list)
    data_scope_note_cn: str = Field(min_length=1)
    review_hint_cn: str | None = None


class Core3V2TargetListResponse(Core3ApiBaseModel):
    items: list[Core3V2TargetSummaryResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str = Field(min_length=1)


class Core3V2OverviewResponse(Core3ApiBaseModel):
    project_id: str = Field(min_length=1)
    category_code: str = "TV"
    data_status_cn: str = Field(min_length=1)
    latest_batch_id: str | None = None
    latest_run_id: str | None = None
    target_count: int = Field(default=0, ge=0)
    report_count: int = Field(default=0, ge=0)
    release_status_counts: dict[str, int] = Field(default_factory=dict)
    data_scope: Core3V2DataScopeResponse
    acceptance_summary_cn: str | None = None
    targets_preview: list[Core3V2TargetSummaryResponse] = Field(default_factory=list)
    summary_cn: str = Field(min_length=1)


class Core3V2DataStatusResponse(Core3ApiBaseModel):
    project_id: str = Field(min_length=1)
    category_code: str = "TV"
    has_data: bool
    latest_batch_id: str | None = None
    batch_count: int = Field(default=0, ge=0)
    target_count: int = Field(default=0, ge=0)
    report_count: int = Field(default=0, ge=0)
    latest_run_id: str | None = None
    release_status_counts: dict[str, int] = Field(default_factory=dict)
    data_scope: Core3V2DataScopeResponse
    summary_cn: str = Field(min_length=1)


class Core3V2EvidenceTraceResponse(Core3ApiBaseModel):
    short_ref: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    trace_usage_cn: str = "证据追溯仅供内部复核，不进入高层展示页。"
    evidence_domain_cn: str | None = None
    evidence_title_cn: str | None = None
    source_cn: str | None = None
    snippet_cn: str | None = None
    source_table: str | None = None
    clean_table: str | None = None
    evidence_field: str | None = None
    confidence: float | None = None


class Core3V2PipelineRunListResponse(Core3ApiBaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str = Field(min_length=1)


class Core3V2ReviewDecisionAliasRequest(Core3ApiBaseModel):
    decision_type: str = Field(min_length=1)
    decision_reason_cn: str = Field(min_length=1)
    decided_by: str = Field(default="system", min_length=1)
    impact_scope: dict[str, Any] = Field(default_factory=dict)
    need_recompute: bool = False
    recompute_mode: str | None = None


class Core3V2ReleaseActionRequest(Core3ApiBaseModel):
    released_by: str = Field(default="system", min_length=1)
    release_note_cn: str | None = None
