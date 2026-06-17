"""Overview and target list queries for Core3 business APIs."""

from __future__ import annotations

from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.api_response_mapper import (
    data_scope_from_records,
    release_status_from_gate,
    target_summary_from_report,
)
from app.services.core3_real_data.api_response_schemas import (
    Core3V2DataStatusResponse,
    Core3V2OverviewResponse,
    Core3V2TargetListResponse,
)


class OverviewQueryService:
    def __init__(self, repository: Core3RealDataApiRepository) -> None:
        self.repository = repository

    def data_status(self) -> Core3V2DataStatusResponse:
        batch = self.repository.latest_batch()
        latest_run = self.repository.latest_run()
        report_count = self.repository.count_current_reports(batch.batch_id if batch else None)
        target_count = self.repository.count_targets_with_reports(batch.batch_id if batch else None)
        release_counts = self.repository.release_status_counts(batch.batch_id if batch else None)
        data_scope = data_scope_from_records(
            note_cn=self._scope_note(batch=batch, report_count=report_count),
            updated_at=batch.updated_at if batch else None,
        )
        return Core3V2DataStatusResponse(
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            has_data=batch is not None,
            latest_batch_id=batch.batch_id if batch else None,
            batch_count=self.repository.count_batches(),
            target_count=target_count,
            report_count=report_count,
            latest_run_id=latest_run.run_id if latest_run else None,
            release_status_counts=release_counts,
            data_scope=data_scope,
            summary_cn=(
                f"当前已接入 {target_count} 个可分析目标，已生成 {report_count} 份核心三竞品报告。"
                if batch
                else "当前项目尚未接入可分析数据。"
            ),
        )

    def overview(self) -> Core3V2OverviewResponse:
        status = self.data_status()
        acceptance = self.repository.latest_acceptance()
        targets = self.targets(limit=6, offset=0)
        return Core3V2OverviewResponse(
            project_id=status.project_id,
            category_code=status.category_code,
            data_status_cn="已生成本地样例分析结果" if status.has_data else "尚未接入分析数据",
            latest_batch_id=status.latest_batch_id,
            latest_run_id=status.latest_run_id,
            target_count=status.target_count,
            report_count=status.report_count,
            release_status_counts=status.release_status_counts,
            data_scope=status.data_scope,
            acceptance_summary_cn=acceptance.acceptance_summary_cn if acceptance else None,
            targets_preview=targets.items,
            summary_cn=(
                f"当前 MVP 已形成 {status.report_count} 份可查看报告，页面可按目标 SKU 进入竞品推导。"
                if status.has_data
                else "请先完成 M00-M16 本地链路后再查看业务报告。"
            ),
        )

    def targets(self, *, limit: int = 100, offset: int = 0) -> Core3V2TargetListResponse:
        batch = self.repository.latest_batch()
        reports = self.repository.list_reports(batch_id=batch.batch_id if batch else None, limit=limit, offset=offset)
        items = [
            target_summary_from_report(
                report,
                self.repository.latest_release_gate(report.target_sku_code, batch_id=report.batch_id),
            )
            for report in reports
        ]
        total = self.repository.count_current_reports(batch.batch_id if batch else None)
        return Core3V2TargetListResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            summary_cn=f"当前共有 {total} 个目标 SKU 已生成核心三竞品报告。",
        )

    @staticmethod
    def _scope_note(*, batch, report_count: int) -> str:
        if batch is None:
            return "当前尚未接入样例数据。"
        if report_count > 0:
            return "当前样例数据内，M00-M16 本地链路已生成核心三竞品分析结果。"
        return "当前样例数据内，已接入原始数据但尚未生成核心三竞品报告。"
