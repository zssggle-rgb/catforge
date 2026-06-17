"""Evidence short-ref trace queries for internal review."""

from __future__ import annotations

from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.api_response_schemas import ApiQueryError, Core3V2EvidenceTraceResponse
from app.services.core3_real_data.sku_resolution_service import SkuResolutionService


class EvidenceTraceQueryService:
    def __init__(
        self,
        repository: Core3RealDataApiRepository,
        resolver: SkuResolutionService | None = None,
    ) -> None:
        self.repository = repository
        self.resolver = resolver or SkuResolutionService(repository)

    def get_trace(self, sku_or_model: str, short_ref: str) -> Core3V2EvidenceTraceResponse:
        sku_code = self.resolver.resolve_unique_sku_code(sku_or_model)
        report = self.repository.latest_report(sku_code)
        if report is None:
            raise ApiQueryError(
                status_code=404,
                error_code="business_report_not_found",
                message_cn=f"{sku_code} 尚未生成核心三竞品报告。",
            )
        ref_item = next(
            (
                item
                for item in report.short_evidence_map_json or []
                if isinstance(item, dict) and str(item.get("short_ref")) == short_ref
            ),
            None,
        )
        if ref_item is None:
            raise ApiQueryError(
                status_code=404,
                error_code="short_ref_not_found",
                message_cn=f"{sku_code} 的报告中没有找到证据短号 {short_ref}。",
            )
        evidence = None
        evidence_id = ref_item.get("evidence_id")
        if evidence_id:
            evidence = self.repository.get_evidence_atom(str(evidence_id))
        confidence_value = (
            getattr(evidence, "confidence", None)
            if evidence is not None and getattr(evidence, "confidence", None) is not None
            else getattr(evidence, "base_confidence", None)
        )
        return Core3V2EvidenceTraceResponse(
            short_ref=short_ref,
            target_sku_code=sku_code,
            evidence_domain_cn=ref_item.get("evidence_domain_cn"),
            evidence_title_cn=ref_item.get("evidence_title_cn"),
            source_cn=ref_item.get("source_cn"),
            snippet_cn=ref_item.get("snippet_cn"),
            source_table=getattr(evidence, "source_table", None),
            clean_table=getattr(evidence, "clean_table", None),
            evidence_field=getattr(evidence, "evidence_field", None),
            confidence=float(confidence_value) if confidence_value is not None else None,
        )
