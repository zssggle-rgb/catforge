"""Business report query service for Core3 real-data v2."""

from __future__ import annotations

from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.api_response_guardrail import ApiResponseGuardrail, ApiResponseGuardrailError
from app.services.core3_real_data.api_response_mapper import (
    battlefield_summary_cn,
    candidate_audit_from_report,
    competitor_from_card,
    data_scope_from_records,
    evidence_card_from_record,
    export_from_record,
    release_status_from_gate,
    review_hint_from_gate,
    section_from_record,
    target_profile_from_report,
    why_competitors_cn,
)
from app.services.core3_real_data.api_response_schemas import (
    ApiQueryError,
    Core3V2BusinessReportResponse,
    Core3V2EvidenceCardBusinessResponse,
    Core3V2ExportBusinessResponse,
    Core3V2ReportSectionBusinessResponse,
)
from app.services.core3_real_data.sku_resolution_service import SkuResolutionService


class BusinessReportQueryService:
    def __init__(
        self,
        repository: Core3RealDataApiRepository,
        resolver: SkuResolutionService | None = None,
        guardrail: ApiResponseGuardrail | None = None,
    ) -> None:
        self.repository = repository
        self.resolver = resolver or SkuResolutionService(repository)
        self.guardrail = guardrail or ApiResponseGuardrail()

    def get_report(self, sku_or_model: str) -> Core3V2BusinessReportResponse:
        sku_code = self.resolver.resolve_unique_sku_code(sku_or_model)
        report = self.repository.latest_report(sku_code)
        if report is None:
            raise ApiQueryError(
                status_code=404,
                error_code="business_report_not_found",
                message_cn=f"{sku_code} 尚未生成核心三竞品报告。",
                action_hint_cn="请先完成 M14 三竞品选择和 M15 报告生成。",
            )
        gate = self.repository.latest_release_gate(sku_code, batch_id=report.batch_id)
        cards = self.repository.list_cards(sku_code, batch_id=report.batch_id, limit=20)
        sections = self.repository.list_sections(sku_code, batch_id=report.batch_id, limit=50)
        exports = self.repository.list_exports(sku_code, batch_id=report.batch_id, limit=20)
        response = Core3V2BusinessReportResponse(
            project_id=report.project_id,
            category_code=report.category_code,
            target=target_profile_from_report(report),
            report_title_cn=report.report_title_cn,
            executive_conclusion_cn=report.executive_conclusion_cn,
            data_scope=data_scope_from_records(note_cn=report.data_scope_note_cn, updated_at=report.updated_at),
            release_status=release_status_from_gate(gate, fallback_scope_note=report.data_scope_note_cn),
            core_competitors=[competitor_from_card(card) for card in cards],
            why_these_competitors_cn=why_competitors_cn(report, cards),
            battlefield_summary_cn=battlefield_summary_cn(report, cards),
            evidence_cards=[evidence_card_from_record(card) for card in cards],
            sections=[section_from_record(section) for section in sections],
            candidate_audit=candidate_audit_from_report(report),
            review_hint=review_hint_from_gate(gate),
            exports=[export_from_record(export) for export in exports],
            data_quality_note_cn=report.data_quality_note_cn,
        )
        self._validate_business(response.model_dump(mode="python"))
        return response

    def list_competitors(self, sku_or_model: str) -> list:
        report = self.get_report(sku_or_model)
        return report.core_competitors

    def list_evidence_cards(self, sku_or_model: str) -> list[Core3V2EvidenceCardBusinessResponse]:
        report = self.get_report(sku_or_model)
        return report.evidence_cards

    def list_sections(self, sku_or_model: str) -> list[Core3V2ReportSectionBusinessResponse]:
        report = self.get_report(sku_or_model)
        return report.sections

    def get_export(self, sku_or_model: str, export_type: str) -> Core3V2ExportBusinessResponse:
        sku_code = self.resolver.resolve_unique_sku_code(sku_or_model)
        report = self.repository.latest_report(sku_code)
        if report is None:
            raise ApiQueryError(
                status_code=404,
                error_code="business_report_not_found",
                message_cn=f"{sku_code} 尚未生成核心三竞品报告。",
            )
        export = self.repository.get_export(sku_code, export_type, batch_id=report.batch_id)
        if export is None:
            raise ApiQueryError(
                status_code=404,
                error_code="report_export_not_found",
                message_cn=f"{sku_code} 尚未生成 {export_type} 导出内容。",
            )
        response = export_from_record(export)
        self._validate_business(response.model_dump(mode="python"))
        return response

    def _validate_business(self, payload: dict) -> None:
        try:
            self.guardrail.validate_business_response(payload)
        except ApiResponseGuardrailError as exc:
            raise ApiQueryError(
                status_code=500,
                error_code="business_api_guardrail_failed",
                message_cn=str(exc),
            ) from exc
