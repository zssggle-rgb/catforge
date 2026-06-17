"""Repository boundaries for M16 pipeline governance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_BUSINESS_DISPLAY_FORBIDDEN_PATTERNS,
    CORE3_M16_MODULE_VERSION,
    CORE3_M16_RULE_VERSION,
    CORE3_MODULE_LABEL_CN,
    Core3ModuleCode,
    Core3PipelineAcceptanceStatus,
    Core3PipelineDependencyStatus,
    Core3PipelinePlannedAction,
    Core3PipelineReviewDecisionType,
    Core3PipelineReviewStatus,
    Core3PipelineWatermarkScope,
    Core3ReleaseGateStatus,
    Core3ReviewSeverity,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.pipeline_dependency_graph import PipelineDependencyGraph
from app.services.core3_real_data.repositories import Core3BaseRepository


@dataclass(frozen=True)
class M16ModuleOutputSummary:
    module_code: Core3ModuleCode
    output_count: int
    input_count: int
    review_issue_count: int = 0
    warning_count: int = 0
    target_count: int = 0
    output_hash: str | None = None
    summary_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class M16PipelineArtifacts:
    run: entities.Core3V2PipelineRun
    plans: tuple[entities.Core3V2RecomputePlan, ...]
    module_runs: tuple[entities.Core3V2ModuleRun, ...]
    review_items: tuple[entities.Core3V2ReviewQueue, ...]
    acceptance_report: entities.Core3V2AcceptanceReport
    release_gates: tuple[entities.Core3V2ReleaseGate, ...]


class PipelineRepository(Core3BaseRepository):
    def now(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def find_latest_batch(self) -> entities.Core3SourceBatch | None:
        stmt = (
            select(entities.Core3SourceBatch)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code.value)
            .order_by(entities.Core3SourceBatch.updated_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def get_batch(self, batch_id: str) -> entities.Core3SourceBatch | None:
        stmt = (
            select(entities.Core3SourceBatch)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code.value)
            .where(entities.Core3SourceBatch.batch_id == batch_id)
        )
        return self.db.execute(stmt).scalars().first()

    def create_pipeline_run(
        self,
        *,
        run_id: str,
        parent_run_id: str | None,
        data_batch_id: str | None,
        run_mode: str,
        trigger_type: str,
        triggered_by: str,
        target_scope_json: dict[str, Any],
        ruleset_version: str,
        module_version_json: dict[str, Any],
        seed_version_json: dict[str, Any],
        input_watermark_json: dict[str, Any],
    ) -> entities.Core3V2PipelineRun:
        now = self.now()
        existing = self.db.get(entities.Core3V2PipelineRun, run_id)
        if existing is not None:
            existing.status = Core3RunStatus.RUNNING.value
            existing.release_status = Core3ReleaseGateStatus.NOT_READY.value
            existing.error_code = None
            existing.error_message_cn = None
            existing.started_at = now
            existing.finished_at = None
            existing.data_batch_id = data_batch_id
            existing.target_scope_json = target_scope_json
            existing.module_version_json = module_version_json
            existing.seed_version_json = seed_version_json
            existing.input_watermark_json = input_watermark_json
            return existing

        row = entities.Core3V2PipelineRun(
            run_id=run_id,
            parent_run_id=parent_run_id,
            project_id=self.project_id,
            category_code=self.category_code.value,
            run_mode=run_mode,
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            data_batch_id=data_batch_id,
            target_scope_json=target_scope_json,
            ruleset_version=ruleset_version,
            module_version_json=module_version_json,
            seed_version_json=seed_version_json,
            input_watermark_json=input_watermark_json,
            status=Core3RunStatus.RUNNING.value,
            release_status=Core3ReleaseGateStatus.NOT_READY.value,
            started_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def finish_pipeline_run(
        self,
        run_id: str,
        *,
        status: Core3RunStatus,
        release_status: Core3ReleaseGateStatus,
        output_summary_json: dict[str, Any],
        quality_summary_json: dict[str, Any],
    ) -> entities.Core3V2PipelineRun:
        row = self.db.get(entities.Core3V2PipelineRun, run_id)
        if row is None:
            raise ValueError(f"pipeline run not found: {run_id}")
        row.status = status.value
        row.release_status = release_status.value
        row.output_summary_json = output_summary_json
        row.quality_summary_json = quality_summary_json
        row.finished_at = self.now()
        self.db.flush()
        return row

    def fail_pipeline_run(self, run_id: str, error_code: str, error_message_cn: str) -> None:
        row = self.db.get(entities.Core3V2PipelineRun, run_id)
        if row is None:
            return
        row.status = Core3RunStatus.FAILED.value
        row.release_status = Core3ReleaseGateStatus.BLOCKED.value
        row.error_code = error_code
        row.error_message_cn = error_message_cn
        row.finished_at = self.now()

    def save_plans(self, plans: Sequence[dict[str, Any]]) -> list[entities.Core3V2RecomputePlan]:
        rows: list[entities.Core3V2RecomputePlan] = []
        for payload in plans:
            existing = self.db.execute(
                select(entities.Core3V2RecomputePlan)
                .where(entities.Core3V2RecomputePlan.run_id == payload["run_id"])
                .where(entities.Core3V2RecomputePlan.module_code == payload["module_code"])
                .where(entities.Core3V2RecomputePlan.target_type == payload["target_type"])
                .where(entities.Core3V2RecomputePlan.target_id == payload["target_id"])
            ).scalars().first()
            row = existing or entities.Core3V2RecomputePlan()
            for key, value in payload.items():
                setattr(row, key, value)
            if existing is None:
                self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def save_module_runs(self, module_runs: Sequence[dict[str, Any]]) -> list[entities.Core3V2ModuleRun]:
        rows: list[entities.Core3V2ModuleRun] = []
        for payload in module_runs:
            existing = self.db.execute(
                select(entities.Core3V2ModuleRun)
                .where(entities.Core3V2ModuleRun.run_id == payload["run_id"])
                .where(entities.Core3V2ModuleRun.module_code == payload["module_code"])
                .where(entities.Core3V2ModuleRun.target_scope == payload["target_scope"])
                .where(entities.Core3V2ModuleRun.target_id == payload["target_id"])
            ).scalars().first()
            row = existing or entities.Core3V2ModuleRun()
            for key, value in payload.items():
                setattr(row, key, value)
            if existing is None:
                self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def save_dependency_snapshots(self, snapshots: Sequence[dict[str, Any]]) -> list[entities.Core3V2ModuleDependencySnapshot]:
        rows: list[entities.Core3V2ModuleDependencySnapshot] = []
        for payload in snapshots:
            existing = self.db.execute(
                select(entities.Core3V2ModuleDependencySnapshot)
                .where(entities.Core3V2ModuleDependencySnapshot.run_id == payload["run_id"])
                .where(entities.Core3V2ModuleDependencySnapshot.module_run_id == payload["module_run_id"])
                .where(entities.Core3V2ModuleDependencySnapshot.upstream_module_code == payload["upstream_module_code"])
                .where(entities.Core3V2ModuleDependencySnapshot.upstream_target_id == payload.get("upstream_target_id"))
            ).scalars().first()
            row = existing or entities.Core3V2ModuleDependencySnapshot()
            for key, value in payload.items():
                setattr(row, key, value)
            if existing is None:
                self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def upsert_review_queue(self, items: Sequence[dict[str, Any]]) -> list[entities.Core3V2ReviewQueue]:
        rows: list[entities.Core3V2ReviewQueue] = []
        for payload in items:
            existing = self.db.execute(
                select(entities.Core3V2ReviewQueue)
                .where(entities.Core3V2ReviewQueue.run_id == payload["run_id"])
                .where(entities.Core3V2ReviewQueue.module_code == payload["module_code"])
                .where(entities.Core3V2ReviewQueue.target_type == payload["target_type"])
                .where(entities.Core3V2ReviewQueue.target_id == payload["target_id"])
                .where(entities.Core3V2ReviewQueue.issue_type == payload["issue_type"])
                .where(entities.Core3V2ReviewQueue.object_id == payload.get("object_id", ""))
            ).scalars().first()
            row = existing or entities.Core3V2ReviewQueue()
            for key, value in payload.items():
                setattr(row, key, value)
            if existing is None:
                self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def insert_review_decision(self, review_id: str, payload: dict[str, Any]) -> entities.Core3V2ReviewDecision:
        review = self.db.get(entities.Core3V2ReviewQueue, review_id)
        if review is None:
            raise ValueError(f"review item not found: {review_id}")
        row = entities.Core3V2ReviewDecision(
            review_id=review_id,
            run_id=review.run_id,
            decision_type=payload["decision_type"],
            decision_reason_cn=payload["decision_reason_cn"],
            impact_scope_json=payload.get("impact_scope_json", {}),
            need_recompute=payload.get("need_recompute", False),
            recompute_mode=payload.get("recompute_mode"),
            decided_by=payload.get("decided_by", "system"),
            decided_at=self.now(),
        )
        review.review_status = _status_from_decision(payload["decision_type"])
        review.reviewer = row.decided_by
        review.reviewed_at = row.decided_at
        review.resolution_note_cn = row.decision_reason_cn
        self.db.add(row)
        self.db.flush()
        return row

    def write_acceptance_report(self, payload: dict[str, Any]) -> entities.Core3V2AcceptanceReport:
        existing = self.db.execute(
            select(entities.Core3V2AcceptanceReport).where(entities.Core3V2AcceptanceReport.run_id == payload["run_id"])
        ).scalars().first()
        row = existing or entities.Core3V2AcceptanceReport()
        for key, value in payload.items():
            setattr(row, key, value)
        if existing is None:
            self.db.add(row)
        self.db.flush()
        return row

    def write_release_gates(self, gates: Sequence[dict[str, Any]]) -> list[entities.Core3V2ReleaseGate]:
        rows: list[entities.Core3V2ReleaseGate] = []
        for payload in gates:
            existing = self.db.execute(
                select(entities.Core3V2ReleaseGate)
                .where(entities.Core3V2ReleaseGate.run_id == payload["run_id"])
                .where(entities.Core3V2ReleaseGate.target_sku_code == payload["target_sku_code"])
            ).scalars().first()
            row = existing or entities.Core3V2ReleaseGate()
            for key, value in payload.items():
                setattr(row, key, value)
            if existing is None:
                self.db.add(row)
            rows.append(row)
        self.db.flush()
        return rows

    def mark_release_gate_released(self, release_gate_id: str, released_by: str) -> entities.Core3V2ReleaseGate:
        row = self.db.get(entities.Core3V2ReleaseGate, release_gate_id)
        if row is None:
            raise ValueError(f"release gate not found: {release_gate_id}")
        if row.gate_status not in {Core3ReleaseGateStatus.RELEASABLE.value, Core3ReleaseGateStatus.RELEASED.value}:
            raise ValueError("当前门禁状态不可正式发布")
        row.gate_status = Core3ReleaseGateStatus.RELEASED.value
        row.released_by = released_by
        row.released_at = self.now()
        return row

    def upsert_watermark(
        self,
        *,
        watermark_scope: Core3PipelineWatermarkScope,
        run_id: str,
        module_code: str | None = None,
        target_id: str | None = None,
        output_hash: str | None = None,
        watermark_json: dict[str, Any] | None = None,
    ) -> entities.Core3V2PipelineWatermark:
        row = self.db.execute(
            select(entities.Core3V2PipelineWatermark)
            .where(entities.Core3V2PipelineWatermark.project_id == self.project_id)
            .where(entities.Core3V2PipelineWatermark.category_code == self.category_code.value)
            .where(entities.Core3V2PipelineWatermark.watermark_scope == watermark_scope.value)
            .where(entities.Core3V2PipelineWatermark.source_table.is_(None))
            .where(entities.Core3V2PipelineWatermark.module_code == module_code)
            .where(entities.Core3V2PipelineWatermark.target_id == target_id)
        ).scalars().first()
        if row is None:
            row = entities.Core3V2PipelineWatermark(
                project_id=self.project_id,
                category_code=self.category_code.value,
                watermark_scope=watermark_scope.value,
                source_table=None,
                module_code=module_code,
                target_id=target_id,
            )
            self.db.add(row)
        row.last_row_hash_snapshot = output_hash
        row.watermark_json = {"last_success_run_id": run_id, **(watermark_json or {})}
        row.updated_by = "M16"
        return row

    def list_plans(self, run_id: str, *, limit: int = 1000, offset: int = 0) -> list[entities.Core3V2RecomputePlan]:
        limit, offset = self.pagination(limit, offset, max_limit=5000)
        stmt = (
            select(entities.Core3V2RecomputePlan)
            .where(entities.Core3V2RecomputePlan.run_id == run_id)
            .order_by(entities.Core3V2RecomputePlan.priority, entities.Core3V2RecomputePlan.module_code)
        )
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def list_module_runs(self, run_id: str, *, limit: int = 1000, offset: int = 0) -> list[entities.Core3V2ModuleRun]:
        limit, offset = self.pagination(limit, offset, max_limit=5000)
        stmt = (
            select(entities.Core3V2ModuleRun)
            .where(entities.Core3V2ModuleRun.run_id == run_id)
            .order_by(entities.Core3V2ModuleRun.module_code)
        )
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def list_dependency_snapshots(
        self,
        run_id: str,
        *,
        module_code: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[entities.Core3V2ModuleDependencySnapshot]:
        limit, offset = self.pagination(limit, offset, max_limit=5000)
        stmt = (
            select(entities.Core3V2ModuleDependencySnapshot)
            .where(entities.Core3V2ModuleDependencySnapshot.run_id == run_id)
            .order_by(
                entities.Core3V2ModuleDependencySnapshot.module_code,
                entities.Core3V2ModuleDependencySnapshot.upstream_module_code,
            )
        )
        if module_code:
            stmt = stmt.where(entities.Core3V2ModuleDependencySnapshot.module_code == module_code)
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def list_reviews(
        self,
        run_id: str | None = None,
        *,
        target_sku_code: str | None = None,
        severity: str | None = None,
        review_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3V2ReviewQueue]:
        limit, offset = self.pagination(limit, offset, max_limit=1000)
        stmt = (
            select(entities.Core3V2ReviewQueue)
            .where(entities.Core3V2ReviewQueue.project_id == self.project_id)
            .where(entities.Core3V2ReviewQueue.category_code == self.category_code.value)
        )
        if run_id:
            stmt = stmt.where(entities.Core3V2ReviewQueue.run_id == run_id)
        if target_sku_code:
            stmt = stmt.where(entities.Core3V2ReviewQueue.target_sku_code == target_sku_code)
        if severity:
            stmt = stmt.where(entities.Core3V2ReviewQueue.severity == severity)
        if review_status:
            stmt = stmt.where(entities.Core3V2ReviewQueue.review_status == review_status)
        stmt = stmt.order_by(entities.Core3V2ReviewQueue.severity.desc(), entities.Core3V2ReviewQueue.created_at.desc())
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def get_acceptance_report(self, run_id: str) -> entities.Core3V2AcceptanceReport | None:
        return self.db.execute(
            select(entities.Core3V2AcceptanceReport).where(entities.Core3V2AcceptanceReport.run_id == run_id)
        ).scalars().first()

    def list_release_gates(
        self,
        run_id: str | None = None,
        *,
        target_sku_code: str | None = None,
        gate_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3V2ReleaseGate]:
        limit, offset = self.pagination(limit, offset, max_limit=1000)
        stmt = (
            select(entities.Core3V2ReleaseGate)
            .where(entities.Core3V2ReleaseGate.project_id == self.project_id)
            .where(entities.Core3V2ReleaseGate.category_code == self.category_code.value)
        )
        if run_id:
            stmt = stmt.where(entities.Core3V2ReleaseGate.run_id == run_id)
        if target_sku_code:
            stmt = stmt.where(entities.Core3V2ReleaseGate.target_sku_code == target_sku_code)
        if gate_status:
            stmt = stmt.where(entities.Core3V2ReleaseGate.gate_status == gate_status)
        stmt = stmt.order_by(entities.Core3V2ReleaseGate.target_sku_code)
        return list(self.db.execute(stmt.limit(limit).offset(offset)).scalars())

    def module_output_summaries(self, batch_id: str) -> dict[Core3ModuleCode, M16ModuleOutputSummary]:
        summaries: dict[Core3ModuleCode, M16ModuleOutputSummary] = {}
        for module_code in PipelineDependencyGraph().topological_order():
            if module_code == Core3ModuleCode.M16:
                continue
            summary = self._module_summary(module_code, batch_id)
            summaries[module_code] = summary
        return summaries

    def report_payloads(self, batch_id: str) -> list[entities.Core3TargetReportPayload]:
        return self._current_rows(
            entities.Core3TargetReportPayload,
            batch_id,
            order_by=(entities.Core3TargetReportPayload.target_sku_code,),
            limit=100000,
        )

    def report_cards(self, batch_id: str) -> list[entities.Core3ReportEvidenceCard]:
        return self._current_rows(
            entities.Core3ReportEvidenceCard,
            batch_id,
            order_by=(entities.Core3ReportEvidenceCard.target_sku_code,),
            limit=100000,
        )

    def m15_review_issues(self, batch_id: str) -> list[entities.Core3ReportReviewIssue]:
        return self._current_rows(
            entities.Core3ReportReviewIssue,
            batch_id,
            order_by=(entities.Core3ReportReviewIssue.issue_level.desc(), entities.Core3ReportReviewIssue.target_sku_code),
            limit=100000,
        )

    def source_report_guardrail_issues(self, batch_id: str) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for section in self._current_rows(entities.Core3ReportSection, batch_id, limit=100000):
            if section.contains_internal_field_flag or section.contains_uuid_flag:
                issues.append(
                    {
                        "module_code": Core3ModuleCode.M15.value,
                        "target_sku_code": section.target_sku_code,
                        "object_type": "report_section",
                        "object_id": section.report_section_id,
                        "issue_type": "internal_field_exposed",
                        "severity": Core3ReviewSeverity.BLOCKER.value,
                        "issue_title_cn": "高层展示出现内部技术字段",
                        "issue_detail_cn": f"{section.target_sku_code} 的报告章节包含内部字段或 UUID，不符合高层展示规范。",
                        "suggested_action_cn": "返回 M15 修正展示 payload 后重新验收。",
                    }
                )
        return issues

    def count_rows(self, model_cls: Any, *filters: Any) -> int:
        return int(self.db.execute(select(func.count()).select_from(model_cls).where(*filters)).scalar_one())

    def _module_summary(self, module_code: Core3ModuleCode, batch_id: str) -> M16ModuleOutputSummary:
        counts = _MODULE_COUNT_SPECS[module_code]
        output_count = 0
        target_codes: set[str] = set()
        detail: dict[str, int] = {}
        for model_cls, field_name in counts:
            count = self._count_current_rows(model_cls, batch_id)
            detail[model_cls.__tablename__] = count
            output_count += count
            if field_name:
                target_codes.update(self._distinct_values(model_cls, batch_id, field_name))
        review_issue_count = self._module_review_issue_count(module_code, batch_id)
        warning_count = review_issue_count
        output_hash = stable_hash(
            {
                "module_code": module_code.value,
                "batch_id": batch_id,
                "counts": detail,
                "targets": sorted(target_codes),
                "review_issue_count": review_issue_count,
            },
            version="m16_module_output_v1",
        )
        return M16ModuleOutputSummary(
            module_code=module_code,
            output_count=output_count,
            input_count=output_count,
            review_issue_count=review_issue_count,
            warning_count=warning_count,
            target_count=len(target_codes),
            output_hash=output_hash,
            summary_json={
                "module_code": module_code.value,
                "module_name_cn": CORE3_MODULE_LABEL_CN[module_code],
                "table_counts": detail,
                "target_count": len(target_codes),
                "review_issue_count": review_issue_count,
            },
        )

    def _module_review_issue_count(self, module_code: Core3ModuleCode, batch_id: str) -> int:
        model_cls = _MODULE_REVIEW_TABLES.get(module_code)
        if model_cls is None:
            return 0
        return self._count_current_rows(model_cls, batch_id)

    def _count_current_rows(self, model_cls: Any, batch_id: str) -> int:
        filters = [
            model_cls.project_id == self.project_id,
            model_cls.category_code == self.category_code.value,
        ]
        if hasattr(model_cls, "batch_id"):
            filters.append(model_cls.batch_id == batch_id)
        if hasattr(model_cls, "is_current"):
            filters.append(model_cls.is_current.is_(True))
        return self.count_rows(model_cls, *filters)

    def _distinct_values(self, model_cls: Any, batch_id: str, field_name: str) -> set[str]:
        if not hasattr(model_cls, field_name):
            return set()
        filters = [
            model_cls.project_id == self.project_id,
            model_cls.category_code == self.category_code.value,
        ]
        if hasattr(model_cls, "batch_id"):
            filters.append(model_cls.batch_id == batch_id)
        if hasattr(model_cls, "is_current"):
            filters.append(model_cls.is_current.is_(True))
        column = getattr(model_cls, field_name)
        rows = self.db.execute(select(column).where(*filters).distinct()).all()
        return {str(row[0]) for row in rows if row[0]}

    def _current_rows(
        self,
        model_cls: Any,
        batch_id: str,
        *,
        order_by: Sequence[Any] = (),
        limit: int = 1000,
    ) -> list[Any]:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
        )
        if hasattr(model_cls, "batch_id"):
            stmt = stmt.where(model_cls.batch_id == batch_id)
        if hasattr(model_cls, "is_current"):
            stmt = stmt.where(model_cls.is_current.is_(True))
        if order_by:
            stmt = stmt.order_by(*order_by)
        return list(self.db.execute(stmt.limit(limit)).scalars())


def module_status_from_summary(summary: M16ModuleOutputSummary) -> Core3RunStatus:
    if summary.output_count <= 0:
        return Core3RunStatus.BLOCKED
    if summary.review_issue_count > 0 or summary.warning_count > 0:
        return Core3RunStatus.WARNING
    return Core3RunStatus.SUCCESS


def severity_blocks_release(severity: str) -> bool:
    return severity == Core3ReviewSeverity.BLOCKER.value


def _status_from_decision(decision_type: str) -> str:
    if decision_type == Core3PipelineReviewDecisionType.APPROVE.value:
        return Core3PipelineReviewStatus.APPROVED.value
    if decision_type == Core3PipelineReviewDecisionType.WAIVE.value:
        return Core3PipelineReviewStatus.WAIVED.value
    if decision_type == Core3PipelineReviewDecisionType.REJECT.value:
        return Core3PipelineReviewStatus.REJECTED.value
    return Core3PipelineReviewStatus.RESOLVED.value


_MODULE_COUNT_SPECS: dict[Core3ModuleCode, tuple[tuple[Any, str | None], ...]] = {
    Core3ModuleCode.M00: (
        (entities.Core3SourceBatch, None),
        (entities.Core3SourceRowRegistry, "sku_code_candidate"),
        (entities.Core3SourceImpactedSku, "sku_code_candidate"),
    ),
    Core3ModuleCode.M01: (
        (entities.Core3CleanSku, "sku_code"),
        (entities.Core3CleanMarketWeekly, "sku_code"),
        (entities.Core3CleanAttribute, "sku_code"),
        (entities.Core3CleanClaim, "sku_code"),
        (entities.Core3CleanComment, "sku_code"),
        (entities.Core3DataQualityIssue, "sku_code"),
    ),
    Core3ModuleCode.M02: ((entities.Core3EvidenceAtom, "sku_code"),),
    Core3ModuleCode.M03: (
        (entities.Core3ParamFieldProfile, None),
        (entities.Core3ExtractParamValue, "sku_code"),
        (entities.Core3ParamAliasCandidate, None),
        (entities.Core3ParamValueConflict, "sku_code"),
        (entities.Core3SkuParamProfile, "sku_code"),
    ),
    Core3ModuleCode.M04A: (
        (entities.Core3ExtractClaimHit, "sku_code"),
        (entities.Core3SkuClaimSourceStatus, "sku_code"),
        (entities.Core3SkuClaimActivationBase, "sku_code"),
    ),
    Core3ModuleCode.M05: (
        (entities.Core3CommentUnit, "sku_code"),
        (entities.Core3CommentUnitEvidenceLink, "sku_code"),
        (entities.Core3CommentEvidenceAtom, "sku_code"),
        (entities.Core3CommentTopicHint, "sku_code"),
        (entities.Core3CommentQualityProfile, "sku_code"),
    ),
    Core3ModuleCode.M06: (
        (entities.Core3CommentSignalCandidate, "sku_code"),
        (entities.Core3CommentDownstreamSignal, "sku_code"),
        (entities.Core3SkuCommentSignalProfile, "sku_code"),
    ),
    Core3ModuleCode.M04B: (
        (entities.Core3SkuClaimCommentValidation, "sku_code"),
        (entities.Core3SkuClaimActivation, "sku_code"),
        (entities.Core3ClaimCommentReviewIssue, "sku_code"),
    ),
    Core3ModuleCode.M07: (
        (entities.Core3SkuMarketProfile, "sku_code"),
        (entities.Core3MarketSignal, "sku_code"),
        (entities.Core3ComparablePoolBaseline, "target_sku_code"),
        (entities.Core3MarketPoolMember, "target_sku_code"),
    ),
    Core3ModuleCode.M08: (
        (entities.Core3SkuSignalProfile, "sku_code"),
        (entities.Core3SkuSignalEvidenceMatrix, "sku_code"),
        (entities.Core3SkuDownstreamFeatureView, "sku_code"),
    ),
    Core3ModuleCode.M08_4: (
        (entities.Core3CommentNativeSignal, "sku_code"),
        (entities.Core3NativeDimensionCandidate, "native_dimension_code"),
        (entities.Core3NativeDimensionSkuSupport, "sku_code"),
        (entities.Core3NativeDimensionAlignmentProposal, "native_dimension_code"),
        (entities.Core3NativeDimensionReviewIssue, "object_code"),
    ),
    Core3ModuleCode.M08_5: (
        (entities.Core3DimensionOntologyVersion, None),
        (entities.Core3DimensionDefinition, "dimension_code"),
        (entities.Core3DimensionEvidenceAnchor, "anchor_code"),
        (entities.Core3DimensionMappingRule, "target_dimension_code"),
        (entities.Core3DimensionCandidateSnapshot, "signal_code"),
        (entities.Core3DimensionCalibrationIssue, "dimension_code"),
    ),
    Core3ModuleCode.M09: (
        (entities.Core3SkuTaskCandidate, "sku_code"),
        (entities.Core3SkuTaskScore, "sku_code"),
        (entities.Core3SkuTaskEvidenceBreakdown, "sku_code"),
        (entities.Core3SkuTaskReviewIssue, "sku_code"),
    ),
    Core3ModuleCode.M10: (
        (entities.Core3SkuTargetGroupCandidate, "sku_code"),
        (entities.Core3SkuTargetGroupScore, "sku_code"),
        (entities.Core3SkuTargetGroupEvidenceBreakdown, "sku_code"),
        (entities.Core3SkuTargetGroupReviewIssue, "sku_code"),
    ),
    Core3ModuleCode.M11: (
        (entities.Core3SkuBattlefieldCandidate, "sku_code"),
        (entities.Core3SkuBattlefieldScore, "sku_code"),
        (entities.Core3SkuBattlefieldEvidenceBreakdown, "sku_code"),
        (entities.Core3SkuBattlefieldPortfolio, "sku_code"),
        (entities.Core3SkuBattlefieldReviewIssue, "sku_code"),
    ),
    Core3ModuleCode.M11_5: (
        (entities.Core3SkuBattlefieldClaimCandidate, "sku_code"),
        (entities.Core3SkuClaimValueLayer, "sku_code"),
        (entities.Core3SkuClaimValueEvidenceBreakdown, "sku_code"),
        (entities.Core3SkuBattlefieldClaimValueSummary, "sku_code"),
        (entities.Core3SkuClaimValueReviewIssue, "sku_code"),
    ),
    Core3ModuleCode.M11_6: (
        (entities.Core3SkuBusinessProfile, "sku_code"),
        (entities.Core3SkuBusinessProfileDimension, "sku_code"),
        (entities.Core3SkuBusinessProfileSalesAllocation, "sku_code"),
        (entities.Core3SkuBusinessProfileReviewIssue, "sku_code"),
    ),
    Core3ModuleCode.M11_7: (
        (entities.Core3BusinessDimensionSalesSummary, "dimension_code"),
        (entities.Core3BusinessDimensionSkuContribution, "sku_code"),
        (entities.Core3BusinessSalesReconciliationCheck, None),
        (entities.Core3BusinessSalesReconciliationIssue, "sku_code"),
    ),
    Core3ModuleCode.M12: (
        (entities.Core3CandidateRecallRun, None),
        (entities.Core3CandidatePool, "target_sku_code"),
        (entities.Core3CandidateRecallReason, "target_sku_code"),
        (entities.Core3CandidateFeatureSnapshot, "target_sku_code"),
        (entities.Core3CandidateRecallReviewIssue, "target_sku_code"),
    ),
    Core3ModuleCode.M13: (
        (entities.Core3CandidateComponentScore, "target_sku_code"),
        (entities.Core3CandidateRoleScore, "target_sku_code"),
        (entities.Core3CandidateComponentExplanation, "target_sku_code"),
        (entities.Core3CandidateScoreReviewIssue, "target_sku_code"),
    ),
    Core3ModuleCode.M14: (
        (entities.Core3CompetitorSelectionRun, "target_sku_code"),
        (entities.Core3CompetitorSelection, "target_sku_code"),
        (entities.Core3CompetitorSlotDecision, "target_sku_code"),
        (entities.Core3CompetitorSelectionAudit, "target_sku_code"),
        (entities.Core3CompetitorSelectionReviewIssue, "target_sku_code"),
    ),
    Core3ModuleCode.M15: (
        (entities.Core3ReportEvidenceCard, "target_sku_code"),
        (entities.Core3TargetReportPayload, "target_sku_code"),
        (entities.Core3ReportSection, "target_sku_code"),
        (entities.Core3ReportExport, "target_sku_code"),
        (entities.Core3ReportReviewIssue, "target_sku_code"),
    ),
}

_MODULE_REVIEW_TABLES: dict[Core3ModuleCode, Any] = {
    Core3ModuleCode.M04B: entities.Core3ClaimCommentReviewIssue,
    Core3ModuleCode.M08_4: entities.Core3NativeDimensionReviewIssue,
    Core3ModuleCode.M08_5: entities.Core3DimensionCalibrationIssue,
    Core3ModuleCode.M09: entities.Core3SkuTaskReviewIssue,
    Core3ModuleCode.M10: entities.Core3SkuTargetGroupReviewIssue,
    Core3ModuleCode.M11: entities.Core3SkuBattlefieldReviewIssue,
    Core3ModuleCode.M11_5: entities.Core3SkuClaimValueReviewIssue,
    Core3ModuleCode.M11_6: entities.Core3SkuBusinessProfileReviewIssue,
    Core3ModuleCode.M11_7: entities.Core3BusinessSalesReconciliationIssue,
    Core3ModuleCode.M12: entities.Core3CandidateRecallReviewIssue,
    Core3ModuleCode.M13: entities.Core3CandidateScoreReviewIssue,
    Core3ModuleCode.M14: entities.Core3CompetitorSelectionReviewIssue,
    Core3ModuleCode.M15: entities.Core3ReportReviewIssue,
}
