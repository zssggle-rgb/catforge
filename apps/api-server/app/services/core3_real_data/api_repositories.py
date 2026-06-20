"""Read-only repositories for Core3 business API aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


@dataclass(frozen=True)
class Core3TargetReportSummary:
    batch_id: str
    target_sku_code: str
    target_display_name_cn: str
    report_title_cn: str
    data_scope_note_cn: str
    selected_count: int
    core_competitors_json: list[dict[str, Any]]


class Core3RealDataApiRepository(Core3BaseRepository):
    def latest_batch(self) -> entities.Core3SourceBatch | None:
        stmt = (
            select(entities.Core3SourceBatch)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code.value)
            .order_by(entities.Core3SourceBatch.updated_at.desc(), entities.Core3SourceBatch.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def count_batches(self) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(entities.Core3SourceBatch)
                .where(entities.Core3SourceBatch.project_id == self.project_id)
                .where(entities.Core3SourceBatch.category_code == self.category_code.value)
            ).scalar_one()
        )

    def latest_run(self) -> entities.Core3V2PipelineRun | None:
        stmt = (
            select(entities.Core3V2PipelineRun)
            .where(entities.Core3V2PipelineRun.project_id == self.project_id)
            .where(entities.Core3V2PipelineRun.category_code == self.category_code.value)
            .order_by(entities.Core3V2PipelineRun.updated_at.desc(), entities.Core3V2PipelineRun.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def list_pipeline_runs(self, *, limit: int = 20, offset: int = 0) -> list[entities.Core3V2PipelineRun]:
        limit, offset = self.pagination(limit, offset, max_limit=100)
        stmt = (
            select(entities.Core3V2PipelineRun)
            .where(entities.Core3V2PipelineRun.project_id == self.project_id)
            .where(entities.Core3V2PipelineRun.category_code == self.category_code.value)
            .order_by(entities.Core3V2PipelineRun.updated_at.desc(), entities.Core3V2PipelineRun.created_at.desc())
        )
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def count_pipeline_runs(self) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(entities.Core3V2PipelineRun)
                .where(entities.Core3V2PipelineRun.project_id == self.project_id)
                .where(entities.Core3V2PipelineRun.category_code == self.category_code.value)
            ).scalar_one()
        )

    def latest_acceptance(self) -> entities.Core3V2AcceptanceReport | None:
        latest = self.latest_run()
        if latest is None:
            return None
        return self.db.execute(
            select(entities.Core3V2AcceptanceReport)
            .where(entities.Core3V2AcceptanceReport.run_id == latest.run_id)
            .order_by(entities.Core3V2AcceptanceReport.updated_at.desc())
        ).scalars().first()

    def list_skus(self, batch_id: str | None = None, *, limit: int = 1000, offset: int = 0) -> list[entities.Core3CleanSku]:
        limit, offset = self.pagination(limit, offset, max_limit=5000)
        stmt = (
            select(entities.Core3CleanSku)
            .where(entities.Core3CleanSku.project_id == self.project_id)
            .where(entities.Core3CleanSku.category_code == self.category_code.value)
            .order_by(entities.Core3CleanSku.sku_code)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3CleanSku.batch_id == batch_id)
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def find_sku_matches(self, query: str, batch_id: str | None = None, *, limit: int = 20) -> list[entities.Core3CleanSku]:
        normalized = query.strip()
        if not normalized:
            return []
        like_value = f"%{normalized}%"
        stmt = (
            select(entities.Core3CleanSku)
            .where(entities.Core3CleanSku.project_id == self.project_id)
            .where(entities.Core3CleanSku.category_code == self.category_code.value)
            .where(
                or_(
                    entities.Core3CleanSku.sku_code.ilike(like_value),
                    entities.Core3CleanSku.model_name.ilike(like_value),
                    entities.Core3CleanSku.brand_name.ilike(like_value),
                )
            )
            .order_by(entities.Core3CleanSku.sku_code)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3CleanSku.batch_id == batch_id)
        return list(self.db.execute(stmt.limit(limit)).scalars())

    def count_targets_with_reports(self, batch_id: str | None = None) -> int:
        stmt = (
            select(func.count(func.distinct(entities.Core3TargetReportPayload.target_sku_code)))
            .where(entities.Core3TargetReportPayload.project_id == self.project_id)
            .where(entities.Core3TargetReportPayload.category_code == self.category_code.value)
            .where(entities.Core3TargetReportPayload.is_current.is_(True))
        )
        if batch_id:
            stmt = stmt.where(entities.Core3TargetReportPayload.batch_id == batch_id)
        return int(self.db.execute(stmt).scalar_one())

    def count_current_reports(self, batch_id: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(entities.Core3TargetReportPayload)
            .where(entities.Core3TargetReportPayload.project_id == self.project_id)
            .where(entities.Core3TargetReportPayload.category_code == self.category_code.value)
            .where(entities.Core3TargetReportPayload.is_current.is_(True))
        )
        if batch_id:
            stmt = stmt.where(entities.Core3TargetReportPayload.batch_id == batch_id)
        return int(self.db.execute(stmt).scalar_one())

    def latest_report(
        self,
        target_sku_code: str,
        *,
        batch_id: str | None = None,
    ) -> entities.Core3TargetReportPayload | None:
        stmt = (
            select(entities.Core3TargetReportPayload)
            .where(entities.Core3TargetReportPayload.project_id == self.project_id)
            .where(entities.Core3TargetReportPayload.category_code == self.category_code.value)
            .where(entities.Core3TargetReportPayload.target_sku_code == target_sku_code)
            .where(entities.Core3TargetReportPayload.is_current.is_(True))
            .order_by(entities.Core3TargetReportPayload.updated_at.desc())
        )
        if batch_id:
            stmt = stmt.where(entities.Core3TargetReportPayload.batch_id == batch_id)
        return self.db.execute(stmt).scalars().first()

    def list_reports(
        self,
        *,
        batch_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3TargetReportSummary]:
        limit, offset = self.pagination(limit, offset, max_limit=1000)
        stmt = self._target_report_summary_stmt(batch_id=batch_id)
        rows = self.db.execute(stmt.limit(limit).offset(offset)).mappings()
        return [
            Core3TargetReportSummary(
                batch_id=str(row["batch_id"]),
                target_sku_code=str(row["target_sku_code"]),
                target_display_name_cn=str(row["target_display_name_cn"]),
                report_title_cn=str(row["report_title_cn"]),
                data_scope_note_cn=str(row["data_scope_note_cn"]),
                selected_count=int(row["selected_count"] or 0),
                core_competitors_json=list(row["core_competitors_json"] or []),
            )
            for row in rows
        ]

    def _target_report_summary_stmt(self, *, batch_id: str | None = None):
        report = entities.Core3TargetReportPayload
        stmt = (
            select(
                report.batch_id,
                report.target_sku_code,
                report.target_display_name_cn,
                report.report_title_cn,
                report.data_scope_note_cn,
                report.selected_count,
                report.core_competitors_json,
            )
            .where(report.project_id == self.project_id)
            .where(report.category_code == self.category_code.value)
            .where(report.is_current.is_(True))
            .order_by(report.target_sku_code)
        )
        if batch_id:
            stmt = stmt.where(report.batch_id == batch_id)
        return stmt

    def list_cards(
        self,
        target_sku_code: str,
        *,
        batch_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[entities.Core3ReportEvidenceCard]:
        limit, offset = self.pagination(limit, offset, max_limit=100)
        stmt = (
            select(entities.Core3ReportEvidenceCard)
            .where(entities.Core3ReportEvidenceCard.project_id == self.project_id)
            .where(entities.Core3ReportEvidenceCard.category_code == self.category_code.value)
            .where(entities.Core3ReportEvidenceCard.target_sku_code == target_sku_code)
            .where(entities.Core3ReportEvidenceCard.is_current.is_(True))
            .order_by(entities.Core3ReportEvidenceCard.slot_code, entities.Core3ReportEvidenceCard.competitor_sku_code)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3ReportEvidenceCard.batch_id == batch_id)
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def list_sections(
        self,
        target_sku_code: str,
        *,
        batch_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[entities.Core3ReportSection]:
        limit, offset = self.pagination(limit, offset, max_limit=100)
        stmt = (
            select(entities.Core3ReportSection)
            .where(entities.Core3ReportSection.project_id == self.project_id)
            .where(entities.Core3ReportSection.category_code == self.category_code.value)
            .where(entities.Core3ReportSection.target_sku_code == target_sku_code)
            .where(entities.Core3ReportSection.is_current.is_(True))
            .order_by(entities.Core3ReportSection.section_order)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3ReportSection.batch_id == batch_id)
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def list_exports(
        self,
        target_sku_code: str,
        *,
        batch_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[entities.Core3ReportExport]:
        limit, offset = self.pagination(limit, offset, max_limit=100)
        stmt = (
            select(entities.Core3ReportExport)
            .where(entities.Core3ReportExport.project_id == self.project_id)
            .where(entities.Core3ReportExport.category_code == self.category_code.value)
            .where(entities.Core3ReportExport.target_sku_code == target_sku_code)
            .where(entities.Core3ReportExport.is_current.is_(True))
            .order_by(entities.Core3ReportExport.export_type)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3ReportExport.batch_id == batch_id)
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def get_export(
        self,
        target_sku_code: str,
        export_type: str,
        *,
        batch_id: str | None = None,
    ) -> entities.Core3ReportExport | None:
        stmt = (
            select(entities.Core3ReportExport)
            .where(entities.Core3ReportExport.project_id == self.project_id)
            .where(entities.Core3ReportExport.category_code == self.category_code.value)
            .where(entities.Core3ReportExport.target_sku_code == target_sku_code)
            .where(entities.Core3ReportExport.export_type == export_type)
            .where(entities.Core3ReportExport.is_current.is_(True))
            .order_by(entities.Core3ReportExport.updated_at.desc())
        )
        if batch_id:
            stmt = stmt.where(entities.Core3ReportExport.batch_id == batch_id)
        return self.db.execute(stmt).scalars().first()

    def latest_release_gate(
        self,
        target_sku_code: str,
        *,
        batch_id: str | None = None,
        run_id: str | None = None,
    ) -> entities.Core3V2ReleaseGate | None:
        stmt = (
            select(entities.Core3V2ReleaseGate)
            .where(entities.Core3V2ReleaseGate.project_id == self.project_id)
            .where(entities.Core3V2ReleaseGate.category_code == self.category_code.value)
            .where(entities.Core3V2ReleaseGate.target_sku_code == target_sku_code)
            .order_by(entities.Core3V2ReleaseGate.updated_at.desc())
        )
        if batch_id:
            stmt = stmt.where(entities.Core3V2ReleaseGate.batch_id == batch_id)
        if run_id:
            stmt = stmt.where(entities.Core3V2ReleaseGate.run_id == run_id)
        return self.db.execute(stmt).scalars().first()

    def release_status_counts(self, batch_id: str | None = None) -> dict[str, int]:
        stmt = (
            select(entities.Core3V2ReleaseGate.gate_status, func.count())
            .where(entities.Core3V2ReleaseGate.project_id == self.project_id)
            .where(entities.Core3V2ReleaseGate.category_code == self.category_code.value)
            .group_by(entities.Core3V2ReleaseGate.gate_status)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3V2ReleaseGate.batch_id == batch_id)
        return {str(status): int(count) for status, count in self.db.execute(stmt).all()}

    def get_evidence_atom(self, evidence_id: str) -> entities.Core3EvidenceAtom | None:
        return self.db.get(entities.Core3EvidenceAtom, evidence_id)

    def rows_as_dicts(self, rows: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "run_id": row.run_id,
                "run_mode": row.run_mode,
                "trigger_type": row.trigger_type,
                "triggered_by": row.triggered_by,
                "status": row.status,
                "release_status": row.release_status,
                "data_batch_id": row.data_batch_id,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "summary_cn": self._run_summary_cn(row),
            }
            for row in rows
        ]

    @staticmethod
    def _run_summary_cn(row: entities.Core3V2PipelineRun) -> str:
        target_count = (row.output_summary_json or {}).get("target_count")
        module_count = (row.output_summary_json or {}).get("module_count")
        if target_count is not None and module_count is not None:
            return f"本次生产线运行覆盖 {target_count} 个目标 SKU、{module_count} 个模块。"
        return "本次生产线运行已记录，可继续查看模块快照、复核项和发布门禁。"
