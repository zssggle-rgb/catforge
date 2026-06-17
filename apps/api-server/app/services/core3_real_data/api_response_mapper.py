"""Mapping utilities from Core3 analytical records to business API payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import entities
from app.services.core3_real_data.api_response_schemas import (
    Core3V2CoreCompetitorResponse,
    Core3V2DataScopeResponse,
    Core3V2EvidenceCardBusinessResponse,
    Core3V2EvidenceShortRefResponse,
    Core3V2ExportBusinessResponse,
    Core3V2ReleaseStatusResponse,
    Core3V2ReportSectionBusinessResponse,
    Core3V2ReviewHintResponse,
    Core3V2TargetProfileResponse,
    Core3V2TargetSummaryResponse,
)
from app.services.core3_real_data.constants import Core3ReleaseGateStatus


INTERNAL_KEYS = {
    "evidence_id",
    "evidence_ids",
    "selection_run_id",
    "selection_id",
    "component_score_id",
    "candidate_pool_id",
    "target_report_payload_id",
    "report_section_id",
    "report_export_id",
    "report_review_issue_id",
    "input_fingerprint",
    "output_hash",
    "result_hash",
    "checksum",
    "page_payload_hash",
    "source_payload_json",
    "raw_payload",
    "source_table",
    "source_field",
    "clean_table",
    "evidence_field",
    "raw_value",
    "normalized_value",
}

INTERNAL_KEY_SUFFIXES = ("_hash", "_fingerprint")

STATUS_LABEL_CN = {
    Core3ReleaseGateStatus.NOT_READY.value: "未就绪",
    Core3ReleaseGateStatus.REVIEW_REQUIRED.value: "需复核",
    Core3ReleaseGateStatus.RELEASABLE.value: "可汇报",
    Core3ReleaseGateStatus.RELEASED.value: "已发布",
    Core3ReleaseGateStatus.BLOCKED.value: "已阻断",
}

DISPLAY_STATUS_LABEL_CN = {
    "visible": "展示",
    "collapsed": "折叠展示",
    "hidden": "不展示",
}

EXPORT_STATUS_LABEL_CN = {
    "ready": "已生成",
    "blocked": "已阻断",
    "failed": "生成失败",
    "review_required": "需复核",
}


def sanitize_business_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in INTERNAL_KEYS or any(lowered.endswith(suffix) for suffix in INTERNAL_KEY_SUFFIXES):
                continue
            sanitized[key_text] = sanitize_business_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_business_payload(item) for item in value]
    return value


def short_refs(refs: list[dict[str, Any]] | None) -> list[Core3V2EvidenceShortRefResponse]:
    items: list[Core3V2EvidenceShortRefResponse] = []
    for ref in refs or []:
        if not isinstance(ref, dict) or not ref.get("short_ref"):
            continue
        items.append(
            Core3V2EvidenceShortRefResponse(
                short_ref=str(ref.get("short_ref")),
                evidence_domain_cn=ref.get("evidence_domain_cn"),
                evidence_title_cn=ref.get("evidence_title_cn"),
                source_cn=ref.get("source_cn"),
                snippet_cn=ref.get("snippet_cn"),
            )
        )
    return items


def target_profile_from_sku(row: entities.Core3CleanSku) -> Core3V2TargetProfileResponse:
    display_name = _display_name(row.sku_code, row.brand_name, row.model_name)
    return Core3V2TargetProfileResponse(
        sku_code=row.sku_code,
        model_name=row.model_name,
        brand_name=row.brand_name,
        display_name_cn=display_name,
        data_status_cn="已完成清洗，可用于竞品分析",
    )


def target_profile_from_report(report: entities.Core3TargetReportPayload) -> Core3V2TargetProfileResponse:
    return Core3V2TargetProfileResponse(
        sku_code=report.target_sku_code,
        model_name=None,
        brand_name=_brand_from_display(report.target_display_name_cn),
        display_name_cn=report.target_display_name_cn,
        data_status_cn="已生成核心三竞品报告",
    )


def release_status_from_gate(
    gate: entities.Core3V2ReleaseGate | None,
    *,
    fallback_scope_note: str,
) -> Core3V2ReleaseStatusResponse:
    if gate is None:
        return Core3V2ReleaseStatusResponse(
            status_code=Core3ReleaseGateStatus.NOT_READY.value,
            status_name_cn=STATUS_LABEL_CN[Core3ReleaseGateStatus.NOT_READY.value],
            gate_reason_cn="该 SKU 尚未完成 M16 发布门禁检查，只能作为内部预览。",
            data_scope_note_cn=fallback_scope_note,
            review_hint_cn="请先运行生产线治理后再进入业务汇报。",
            can_present=False,
            can_release=False,
        )
    status_code = gate.gate_status
    return Core3V2ReleaseStatusResponse(
        status_code=status_code,
        status_name_cn=STATUS_LABEL_CN.get(status_code, status_code),
        gate_reason_cn=gate.gate_reason_cn,
        data_scope_note_cn=gate.data_scope_note_cn,
        review_hint_cn=_review_hint_from_gate(gate),
        can_present=status_code
        in {
            Core3ReleaseGateStatus.REVIEW_REQUIRED.value,
            Core3ReleaseGateStatus.RELEASABLE.value,
            Core3ReleaseGateStatus.RELEASED.value,
        },
        can_release=status_code == Core3ReleaseGateStatus.RELEASABLE.value,
    )


def data_scope_from_records(
    *,
    note_cn: str | None,
    updated_at: datetime | None = None,
) -> Core3V2DataScopeResponse:
    note = note_cn or "当前样例数据内，结果只代表已接入数据。"
    return Core3V2DataScopeResponse(
        period_cn=_period_from_note(note),
        channel_scope_cn=_channel_from_note(note),
        platform_scope_cn=_platform_from_note(note),
        sample_note_cn="后续新增原始表后，可按同一流程增量清洗、抽取和重算。",
        data_scope_note_cn=note,
        updated_at=updated_at,
    )


def competitor_from_card(card: entities.Core3ReportEvidenceCard) -> Core3V2CoreCompetitorResponse:
    return Core3V2CoreCompetitorResponse(
        competitor_sku_code=card.competitor_sku_code,
        competitor_model_name=card.competitor_model_name,
        competitor_brand_name=card.competitor_brand_name,
        competitor_display_name_cn=card.competitor_display_name_cn,
        role_code=card.slot_code,
        role_name_cn=card.slot_name_cn,
        one_sentence_reason_cn=card.one_sentence_reason_cn,
        battlefield_fit_cn=card.primary_battlefield_name_cn,
        market_pressure_cn=card.pressure_level_cn,
        key_difference_cn=card.key_difference_cn,
        target_advantage_cn=card.target_advantage_cn,
        competitor_advantage_cn=card.competitor_advantage_cn,
        strategy_implication_cn=card.strategy_implication_cn,
        confidence_label_cn=card.confidence_label_cn,
        risk_note_cn=card.risk_note_cn,
        evidence_short_refs=short_refs(card.short_evidence_refs_json),
    )


def evidence_card_from_record(card: entities.Core3ReportEvidenceCard) -> Core3V2EvidenceCardBusinessResponse:
    return Core3V2EvidenceCardBusinessResponse(
        target_sku_code=card.target_sku_code,
        target_display_name_cn=card.target_display_name_cn,
        competitor_sku_code=card.competitor_sku_code,
        competitor_display_name_cn=card.competitor_display_name_cn,
        role_code=card.slot_code,
        role_name_cn=card.slot_name_cn,
        headline_cn=card.headline_cn,
        summary_cn=card.summary_cn,
        one_sentence_reason_cn=card.one_sentence_reason_cn,
        battlefield_name_cn=card.primary_battlefield_name_cn,
        confidence_label_cn=card.confidence_label_cn,
        price_evidence_cn=card.price_evidence_cn,
        channel_evidence_cn=card.channel_evidence_cn,
        param_evidence_cn=card.param_evidence_cn,
        claim_value_evidence_cn=card.claim_value_evidence_cn,
        task_audience_evidence_cn=card.task_audience_evidence_cn,
        market_evidence_cn=card.market_evidence_cn,
        comment_evidence_cn=card.comment_evidence_cn,
        key_difference_cn=card.key_difference_cn,
        target_advantage_cn=card.target_advantage_cn,
        competitor_advantage_cn=card.competitor_advantage_cn,
        strategy_implication_cn=card.strategy_implication_cn,
        risk_note_cn=card.risk_note_cn,
        evidence_short_refs=short_refs(card.short_evidence_refs_json),
    )


def section_from_record(section: entities.Core3ReportSection) -> Core3V2ReportSectionBusinessResponse:
    return Core3V2ReportSectionBusinessResponse(
        section_code=section.section_code,
        section_title_cn=section.section_title_cn,
        section_order=section.section_order,
        display_status_cn=DISPLAY_STATUS_LABEL_CN.get(section.display_status, section.display_status),
        section_payload=sanitize_business_payload(section.section_payload_json),
        evidence_short_refs=short_refs(section.short_evidence_refs_json),
    )


def export_from_record(export: entities.Core3ReportExport) -> Core3V2ExportBusinessResponse:
    return Core3V2ExportBusinessResponse(
        export_type=export.export_type,
        export_title_cn=export.export_title_cn,
        export_payload=export.export_payload,
        data_scope_note_cn=export.data_scope_note_cn,
        export_status_cn=EXPORT_STATUS_LABEL_CN.get(export.export_status, export.export_status),
        failure_reason=export.failure_reason,
        media_type=_media_type(export.export_type),
    )


def review_hint_from_gate(gate: entities.Core3V2ReleaseGate | None) -> Core3V2ReviewHintResponse:
    if gate is None:
        return Core3V2ReviewHintResponse(
            review_required=True,
            severity_name_cn="待检查",
            message_cn="尚未生成发布门禁，请先完成生产线治理。",
            suggested_action_cn="运行 M16 后再查看业务报告。",
            review_count=0,
        )
    required = len(gate.required_review_ids or [])
    warnings = len(gate.warning_review_ids or [])
    if required > 0:
        return Core3V2ReviewHintResponse(
            review_required=True,
            severity_name_cn="阻断",
            message_cn=f"存在 {required} 个必须处理的复核项，暂不能发布。",
            suggested_action_cn="请先处理阻断复核项，再重新运行发布门禁。",
            review_count=required + warnings,
        )
    if warnings > 0 or gate.gate_status == Core3ReleaseGateStatus.REVIEW_REQUIRED.value:
        return Core3V2ReviewHintResponse(
            review_required=True,
            severity_name_cn="提醒",
            message_cn=f"存在 {warnings} 个提示性复核项，汇报时需保留样例范围说明。",
            suggested_action_cn="可作为内部汇报预览，正式发布前建议复核。",
            review_count=warnings,
        )
    return Core3V2ReviewHintResponse(
        review_required=False,
        message_cn="当前报告满足发布门禁，可进入业务展示。",
        review_count=0,
    )


def target_summary_from_report(
    report: entities.Core3TargetReportPayload,
    gate: entities.Core3V2ReleaseGate | None,
) -> Core3V2TargetSummaryResponse:
    competitors = [
        str(item.get("竞品") or item.get("competitor_display_name_cn") or item.get("competitor_sku_code"))
        for item in report.core_competitors_json or []
        if isinstance(item, dict)
    ]
    release_status = release_status_from_gate(gate, fallback_scope_note=report.data_scope_note_cn)
    return Core3V2TargetSummaryResponse(
        target_sku_code=report.target_sku_code,
        target_display_name_cn=report.target_display_name_cn,
        brand_name=_brand_from_display(report.target_display_name_cn),
        report_title_cn=report.report_title_cn,
        release_status=release_status,
        selected_count=report.selected_count,
        competitor_names_cn=[name for name in competitors if name],
        data_scope_note_cn=report.data_scope_note_cn,
        review_hint_cn=release_status.review_hint_cn,
    )


def candidate_audit_from_report(report: entities.Core3TargetReportPayload) -> dict[str, Any]:
    return sanitize_business_payload(
        {
            "候选池概况": report.candidate_pool_summary_json,
            "已选择竞品数": report.selected_count,
            "空缺槽位数": report.empty_slot_count,
            "复核问题": report.review_questions_json,
        }
    )


def why_competitors_cn(report: entities.Core3TargetReportPayload, cards: list[entities.Core3ReportEvidenceCard]) -> str:
    reasons = [card.one_sentence_reason_cn for card in cards if card.one_sentence_reason_cn]
    if reasons:
        return "；".join(reasons[:3])
    logic_items = [
        str(item.get("说明") or item.get("reason_cn") or item.get("summary_cn"))
        for item in report.why_competitor_logic_json or []
        if isinstance(item, dict)
    ]
    return "；".join([item for item in logic_items if item]) or "系统按价值战场、目标客群、用户任务、卖点支撑和市场压力共同推导核心竞品。"


def battlefield_summary_cn(report: entities.Core3TargetReportPayload, cards: list[entities.Core3ReportEvidenceCard]) -> str:
    names = sorted({card.primary_battlefield_name_cn for card in cards if card.primary_battlefield_name_cn})
    if names:
        return f"当前核心竞品主要落在{'、'.join(names)}，说明目标 SKU 与竞品在关键价值战场上形成正面对比。"
    summary = report.battlefield_summary_json or {}
    return str(summary.get("summary_cn") or summary.get("战场总结") or "当前报告已生成价值战场摘要。")


def _display_name(sku_code: str, brand: str | None, model: str | None) -> str:
    parts = [part for part in [brand, model] if part]
    if parts:
        return " ".join(parts)
    return sku_code


def _brand_from_display(display_name: str | None) -> str | None:
    if not display_name:
        return None
    return str(display_name).split()[0]


def _review_hint_from_gate(gate: entities.Core3V2ReleaseGate) -> str | None:
    if gate.required_review_ids:
        return f"存在 {len(gate.required_review_ids)} 个阻断复核项。"
    if gate.warning_review_ids:
        return f"存在 {len(gate.warning_review_ids)} 个提示性复核项。"
    return None


def _period_from_note(note: str) -> str:
    if "26W" in note:
        return "26W 样例周期"
    if "当前样例数据内" in note:
        return "当前样例数据内"
    return "已接入数据范围"


def _channel_from_note(note: str) -> str:
    if "线上" in note:
        return "线上渠道"
    return "样例覆盖渠道"


def _platform_from_note(note: str) -> str:
    if "京东" in note or "天猫" in note or "抖音" in note:
        return "样例覆盖电商平台"
    return "样例覆盖平台"


def _media_type(export_type: str) -> str:
    if export_type == "markdown":
        return "text/markdown; charset=utf-8"
    if export_type == "json":
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"
