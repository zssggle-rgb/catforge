"""Export delivery service for Core3 business APIs."""

from __future__ import annotations

from app.services.core3_real_data.api_response_schemas import Core3V2ExportBusinessResponse
from app.services.core3_real_data.business_report_query_service import BusinessReportQueryService


class ExportDeliveryService:
    def __init__(self, report_service: BusinessReportQueryService) -> None:
        self.report_service = report_service

    def get_export(self, sku_or_model: str, export_type: str) -> Core3V2ExportBusinessResponse:
        return self.report_service.get_export(sku_or_model, export_type)
