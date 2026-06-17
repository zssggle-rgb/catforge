"""M16 pipeline governance execution service."""

from __future__ import annotations

from uuid import uuid4

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M16_MODULE_VERSION,
    CORE3_M16_RULE_VERSION,
    CORE3_MODULE_LABEL_CN,
    Core3ModuleCode,
    Core3PipelineDependencyStatus,
    Core3PipelinePlannedAction,
    Core3PipelineWatermarkScope,
    Core3ReleaseGateStatus,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.pipeline_acceptance_service import AcceptanceService
from app.services.core3_real_data.pipeline_dependency_graph import PipelineDependencyGraph
from app.services.core3_real_data.pipeline_recompute_planner import RecomputePlanner
from app.services.core3_real_data.pipeline_release_gate_service import ReleaseGateService, derive_release_status
from app.services.core3_real_data.pipeline_repositories import (
    M16PipelineArtifacts,
    PipelineRepository,
    module_status_from_summary,
)
from app.services.core3_real_data.pipeline_review_aggregator import ReviewAggregator
from app.services.core3_real_data.pipeline_schemas import M16PipelineRunRequest, M16PipelineRunResponse


class PipelineExecutionService:
    def __init__(
        self,
        repository: PipelineRepository,
        graph: PipelineDependencyGraph | None = None,
        planner: RecomputePlanner | None = None,
        review_aggregator: ReviewAggregator | None = None,
        release_gate_service: ReleaseGateService | None = None,
        acceptance_service: AcceptanceService | None = None,
    ) -> None:
        self.repository = repository
        self.graph = graph or PipelineDependencyGraph()
        self.planner = planner or RecomputePlanner(self.graph)
        self.review_aggregator = review_aggregator or ReviewAggregator(self.graph)
        self.release_gate_service = release_gate_service or ReleaseGateService()
        self.acceptance_service = acceptance_service or AcceptanceService()

    def run(self, request: M16PipelineRunRequest) -> M16PipelineArtifacts:
        batch = self._resolve_batch(request.data_batch_id)
        run_id = request.run_id or f"m16-{uuid4()}"
        module_versions = dict(request.module_versions)
        module_versions.setdefault(Core3ModuleCode.M16.value, request.module_version or CORE3_M16_MODULE_VERSION)
        run = self.repository.create_pipeline_run(
            run_id=run_id,
            parent_run_id=request.parent_run_id,
            data_batch_id=batch.batch_id,
            run_mode=request.run_mode.value,
            trigger_type=request.trigger_type.value,
            triggered_by=request.triggered_by,
            target_scope_json=request.target_scope.model_dump(mode="json"),
            ruleset_version=request.ruleset_version,
            module_version_json=module_versions,
            seed_version_json=dict(request.seed_versions),
            input_watermark_json=dict(request.input_watermarks),
        )
        try:
            module_outputs = self.repository.module_output_summaries(batch.batch_id)
            plans = self.repository.save_plans(
                self.planner.build_plan(
                    run_id=run.run_id,
                    project_id=request.project_id,
                    category_code=request.category_code.value,
                    batch_id=batch.batch_id,
                    run_mode=request.run_mode,
                    target_scope_json=request.target_scope.model_dump(mode="json"),
                    module_outputs=module_outputs,
                )
            )
            plan_by_module = {Core3ModuleCode(plan.module_code): plan for plan in plans}
            module_runs = self.repository.save_module_runs(
                [
                    self._module_run_payload(
                        run_id=run.run_id,
                        request=request,
                        batch_id=batch.batch_id,
                        plan=plan_by_module[module_code],
                        module_code=module_code,
                        output_summary=summary,
                    )
                    for module_code, summary in module_outputs.items()
                ]
            )
            module_runs_by_code = {Core3ModuleCode(row.module_code): row for row in module_runs}
            self.repository.save_dependency_snapshots(
                self._dependency_snapshots(
                    run_id=run.run_id,
                    request=request,
                    module_runs=module_runs_by_code,
                )
            )

            reports = self.repository.report_payloads(batch.batch_id)
            cards = self.repository.report_cards(batch.batch_id)
            review_payloads = self.review_aggregator.collect(
                run_id=run.run_id,
                project_id=request.project_id,
                category_code=request.category_code.value,
                batch_id=batch.batch_id,
                module_runs=module_runs_by_code,
                m15_review_issues=self.repository.m15_review_issues(batch.batch_id),
                report_payloads=reports,
                report_cards=cards,
                guardrail_issues=self.repository.source_report_guardrail_issues(batch.batch_id),
            )
            review_items = self.repository.upsert_review_queue(review_payloads)
            gate_payloads = self.release_gate_service.evaluate(
                run_id=run.run_id,
                project_id=request.project_id,
                category_code=request.category_code.value,
                batch_id=batch.batch_id,
                reports=reports,
                cards=cards,
                reviews=review_items,
            )
            gates = self.repository.write_release_gates(gate_payloads)
            acceptance_payload = self.acceptance_service.build_report(
                run_id=run.run_id,
                project_id=request.project_id,
                category_code=request.category_code.value,
                batch_id=batch.batch_id,
                module_runs=module_runs_by_code,
                review_items=review_items,
                report_payloads=reports,
                report_cards=cards,
                release_gates=gates,
            )
            acceptance = self.repository.write_acceptance_report(acceptance_payload)
            m16_run = self.repository.save_module_runs(
                [
                    self._m16_module_run_payload(
                        run_id=run.run_id,
                        request=request,
                        batch_id=batch.batch_id,
                        acceptance=acceptance,
                        gates=gates,
                        review_items=review_items,
                    )
                ]
            )[0]
            module_runs_by_code[Core3ModuleCode.M16] = m16_run
            self.repository.save_dependency_snapshots(
                self._dependency_snapshots(
                    run_id=run.run_id,
                    request=request,
                    module_runs=module_runs_by_code,
                )
            )
            release_status = derive_release_status(gates)
            final_status = _final_run_status(acceptance.acceptance_status, release_status)
            output_summary = {
                "module_count": len(module_runs_by_code),
                "module_success_count": sum(
                    1
                    for row in module_runs_by_code.values()
                    if row.status in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value, Core3RunStatus.SKIPPED_REUSED.value}
                ),
                "review_queue_count": len(review_items),
                "release_gate_count": len(gates),
                "report_ready_count": acceptance.report_ready_count,
                "report_blocked_count": acceptance.blocked_report_count,
                "processed_target_count": acceptance.processed_target_count,
            }
            quality_summary = {
                "acceptance_status": acceptance.acceptance_status,
                "release_status": release_status.value,
                "blocker_count": acceptance.blocker_count,
                "warning_count": acceptance.warning_count,
                "data_scope_note_cn": acceptance.data_scope_note_cn,
            }
            run = self.repository.finish_pipeline_run(
                run.run_id,
                status=final_status,
                release_status=release_status,
                output_summary_json=output_summary,
                quality_summary_json=quality_summary,
            )
            self._update_watermarks(run.run_id, module_runs_by_code, gates)
            return M16PipelineArtifacts(
                run=run,
                plans=tuple(plans),
                module_runs=tuple(module_runs_by_code.values()),
                review_items=tuple(review_items),
                acceptance_report=acceptance,
                release_gates=tuple(gates),
            )
        except Exception as exc:
            self.repository.fail_pipeline_run(run.run_id, "m16_pipeline_failed", f"M16 生产线治理运行失败：{exc}")
            raise

    def response(self, run: entities.Core3V2PipelineRun) -> M16PipelineRunResponse:
        return M16PipelineRunResponse(
            run_id=run.run_id,
            parent_run_id=run.parent_run_id,
            project_id=run.project_id,
            category_code=run.category_code,
            run_mode=run.run_mode,
            trigger_type=run.trigger_type,
            triggered_by=run.triggered_by,
            data_batch_id=run.data_batch_id,
            target_scope_json=run.target_scope_json or {},
            ruleset_version=run.ruleset_version,
            module_version_json=run.module_version_json or {},
            seed_version_json=run.seed_version_json or {},
            input_watermark_json=run.input_watermark_json or {},
            status=run.status,
            release_status=run.release_status,
            output_summary_json=run.output_summary_json or {},
            quality_summary_json=run.quality_summary_json or {},
            started_at=run.started_at,
            finished_at=run.finished_at,
            error_code=run.error_code,
            error_message_cn=run.error_message_cn,
            summary_cn=_run_summary_cn(run),
        )

    def _resolve_batch(self, batch_id: str | None) -> entities.Core3SourceBatch:
        batch = self.repository.get_batch(batch_id) if batch_id else self.repository.find_latest_batch()
        if batch is None:
            raise ValueError("M16 需要先完成 M00 批次登记。")
        return batch

    def _module_run_payload(
        self,
        *,
        run_id: str,
        request: M16PipelineRunRequest,
        batch_id: str,
        plan: entities.Core3V2RecomputePlan,
        module_code: Core3ModuleCode,
        output_summary,
    ) -> dict:
        status = module_status_from_summary(output_summary)
        if plan.planned_action == Core3PipelinePlannedAction.REUSE.value and status != Core3RunStatus.BLOCKED:
            status = Core3RunStatus.SKIPPED_REUSED
        summary_json = dict(output_summary.summary_json or {})
        summary_json.update(
            {
                "m16_plan_id": plan.plan_id,
                "m16_planned_action": plan.planned_action,
                "m16_governance_note_cn": "M16 未重跑业务模块，仅复用已落库产物生成治理快照。",
            }
        )
        return {
            "run_id": run_id,
            "project_id": request.project_id,
            "category_code": request.category_code.value,
            "module_code": module_code.value,
            "target_scope": plan.target_type,
            "target_id": plan.target_id,
            "batch_id": batch_id,
            "status": status.value,
            "input_count": output_summary.input_count,
            "changed_input_count": 0,
            "output_count": output_summary.output_count,
            "output_hash": output_summary.output_hash,
            "warnings_json": [f"{CORE3_MODULE_LABEL_CN[module_code]} 存在待复核问题"] if output_summary.warning_count else [],
            "review_issue_summary_json": {
                "count": output_summary.review_issue_count,
            },
            "downstream_impact_json": {
                "module_codes": [code.value for code in self.graph.downstream_modules(module_code)],
            },
            "summary_json": summary_json,
            "started_at": self.repository.now(),
            "finished_at": self.repository.now(),
            "error_code": "missing_module_output" if status == Core3RunStatus.BLOCKED else None,
            "error_message_cn": "缺少可验收产物" if status == Core3RunStatus.BLOCKED else None,
        }

    def _m16_module_run_payload(
        self,
        *,
        run_id: str,
        request: M16PipelineRunRequest,
        batch_id: str,
        acceptance: entities.Core3V2AcceptanceReport,
        gates: list[entities.Core3V2ReleaseGate],
        review_items: list[entities.Core3V2ReviewQueue],
    ) -> dict:
        status = Core3RunStatus.SUCCESS if acceptance.blocker_count == 0 else Core3RunStatus.BLOCKED
        if status == Core3RunStatus.SUCCESS and (acceptance.warning_count > 0 or acceptance.review_pending_count > 0):
            status = Core3RunStatus.WARNING
        summary = {
            "acceptance_id": acceptance.acceptance_id,
            "acceptance_status": acceptance.acceptance_status,
            "release_gate_count": len(gates),
            "review_queue_count": len(review_items),
            "report_ready_count": acceptance.report_ready_count,
            "blocked_report_count": acceptance.blocked_report_count,
            "boundary_note_cn": "M16 只做生产线治理、复核、验收和发布门禁，不生成新的竞品业务结论。",
        }
        return {
            "run_id": run_id,
            "project_id": request.project_id,
            "category_code": request.category_code.value,
            "module_code": Core3ModuleCode.M16.value,
            "target_scope": "batch",
            "target_id": batch_id,
            "batch_id": batch_id,
            "status": status.value,
            "input_count": len(gates) + len(review_items),
            "changed_input_count": len(review_items),
            "output_count": len(gates) + len(review_items) + 1,
            "output_hash": stable_hash(summary, version="m16_pipeline_summary_v1"),
            "warnings_json": [acceptance.acceptance_summary_cn] if status == Core3RunStatus.WARNING else [],
            "review_issue_summary_json": {
                "count": len(review_items),
                "blocker_count": acceptance.blocker_count,
            },
            "downstream_impact_json": {"module_codes": ["API", "FRONTEND", "ACCEPTANCE"]},
            "summary_json": summary,
            "started_at": self.repository.now(),
            "finished_at": self.repository.now(),
            "error_code": "acceptance_failed" if status == Core3RunStatus.BLOCKED else None,
            "error_message_cn": acceptance.acceptance_summary_cn if status == Core3RunStatus.BLOCKED else None,
        }

    def _dependency_snapshots(
        self,
        *,
        run_id: str,
        request: M16PipelineRunRequest,
        module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
    ) -> list[dict]:
        snapshots: list[dict] = []
        for module_code, module_run in module_runs.items():
            for upstream in self.graph.required_upstreams(module_code):
                upstream_run = module_runs.get(upstream)
                status = (
                    Core3PipelineDependencyStatus.VALID.value
                    if upstream_run and upstream_run.output_hash
                    else Core3PipelineDependencyStatus.MISSING.value
                )
                snapshots.append(
                    {
                        "module_run_id": module_run.module_run_id,
                        "run_id": run_id,
                        "project_id": request.project_id,
                        "category_code": request.category_code.value,
                        "module_code": module_code.value,
                        "upstream_module_code": upstream.value,
                        "upstream_target_id": upstream_run.target_id if upstream_run else None,
                        "upstream_output_hash": upstream_run.output_hash if upstream_run else None,
                        "rule_version": CORE3_M16_RULE_VERSION,
                        "seed_version_json": request.seed_versions,
                        "dependency_status": status,
                        "reused_from_module_run_id": upstream_run.module_run_id if upstream_run else None,
                    }
                )
        return snapshots

    def _update_watermarks(
        self,
        run_id: str,
        module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
        gates: list[entities.Core3V2ReleaseGate],
    ) -> None:
        for module_code, module_run in module_runs.items():
            if module_run.status in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value}:
                continue
            self.repository.upsert_watermark(
                watermark_scope=Core3PipelineWatermarkScope.MODULE,
                run_id=run_id,
                module_code=module_code.value,
                target_id=module_run.target_id,
                output_hash=module_run.output_hash,
                watermark_json={"status": module_run.status},
            )
        for gate in gates:
            if gate.gate_status in {Core3ReleaseGateStatus.RELEASABLE.value, Core3ReleaseGateStatus.RELEASED.value}:
                self.repository.upsert_watermark(
                    watermark_scope=Core3PipelineWatermarkScope.TARGET_SKU,
                    run_id=run_id,
                    module_code=Core3ModuleCode.M16.value,
                    target_id=gate.target_sku_code,
                    output_hash=stable_hash(gate.gate_check_json or {}, version="m16_release_gate_v1"),
                    watermark_json={"gate_status": gate.gate_status, "release_gate_id": gate.release_gate_id},
                )


def _final_run_status(acceptance_status: str, release_status: Core3ReleaseGateStatus) -> Core3RunStatus:
    if release_status == Core3ReleaseGateStatus.BLOCKED or acceptance_status == "failed":
        return Core3RunStatus.BLOCKED
    if release_status == Core3ReleaseGateStatus.REVIEW_REQUIRED or acceptance_status == "passed_with_warning":
        return Core3RunStatus.WARNING
    return Core3RunStatus.SUCCESS


def _run_summary_cn(run: entities.Core3V2PipelineRun) -> str:
    if run.status == Core3RunStatus.BLOCKED.value:
        return "M16 验收发现阻断问题，当前结果不能进入高层展示。"
    if run.status == Core3RunStatus.WARNING.value:
        return "M16 验收带说明通过，报告可预览但需保留样例范围和复核提示。"
    if run.status == Core3RunStatus.SUCCESS.value:
        return "M16 验收通过，报告具备业务展示条件。"
    return "M16 生产线治理运行记录。"
