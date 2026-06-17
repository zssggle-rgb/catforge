"""M16 recompute planning from existing module outputs."""

from __future__ import annotations

from typing import Any

from app.services.core3_real_data.constants import (
    CORE3_DATA_DOMAIN_START_MODULE,
    CORE3_MODULE_LABEL_CN,
    Core3DataDomain,
    Core3ModuleCode,
    Core3PipelinePlannedAction,
    Core3RunMode,
)
from app.services.core3_real_data.pipeline_dependency_graph import PipelineDependencyGraph
from app.services.core3_real_data.pipeline_repositories import M16ModuleOutputSummary


class RecomputePlanner:
    def __init__(self, graph: PipelineDependencyGraph | None = None) -> None:
        self.graph = graph or PipelineDependencyGraph()

    def build_plan(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        run_mode: Core3RunMode | str,
        target_scope_json: dict[str, Any],
        module_outputs: dict[Core3ModuleCode, M16ModuleOutputSummary],
    ) -> list[dict[str, Any]]:
        mode = Core3RunMode(run_mode)
        target_id = self._target_id(batch_id, target_scope_json)
        start_module = self._start_module(mode, target_scope_json)
        plans: list[dict[str, Any]] = []
        for index, module_code in enumerate(self.graph.topological_order()):
            summary = module_outputs.get(module_code)
            planned_action = self._planned_action(module_code, mode, summary)
            plans.append(
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "category_code": category_code,
                    "batch_id": batch_id,
                    "module_code": module_code.value,
                    "target_type": "batch" if module_code not in {Core3ModuleCode.M12, Core3ModuleCode.M13, Core3ModuleCode.M14, Core3ModuleCode.M15} else "target_sku",
                    "target_id": target_id,
                    "start_from_module": start_module.value,
                    "change_domain": self._change_domain(mode, target_scope_json),
                    "change_reason_cn": self._change_reason_cn(mode, module_code, planned_action),
                    "upstream_dependency_hash": summary.output_hash if summary is not None else None,
                    "previous_output_hash": summary.output_hash if summary is not None else None,
                    "planned_action": planned_action.value,
                    "priority": index * 10,
                    "related_targets_json": {
                        "target_scope": target_scope_json,
                        "module_name_cn": CORE3_MODULE_LABEL_CN[module_code],
                    },
                    "plan_reason_json": {
                        "run_mode": mode.value,
                        "module_code": module_code.value,
                        "module_output_count": summary.output_count if summary is not None else 0,
                        "module_review_issue_count": summary.review_issue_count if summary is not None else 0,
                    },
                }
            )
        return plans

    def _planned_action(
        self,
        module_code: Core3ModuleCode,
        mode: Core3RunMode,
        summary: M16ModuleOutputSummary | None,
    ) -> Core3PipelinePlannedAction:
        if module_code == Core3ModuleCode.M16:
            return Core3PipelinePlannedAction.RUN
        if mode == Core3RunMode.ACCEPTANCE_ONLY:
            return Core3PipelinePlannedAction.REUSE if summary and summary.output_count > 0 else Core3PipelinePlannedAction.BLOCK
        if summary and summary.output_count > 0:
            return Core3PipelinePlannedAction.REUSE
        return Core3PipelinePlannedAction.RUN

    def _target_id(self, batch_id: str, target_scope_json: dict[str, Any]) -> str:
        sku_codes = target_scope_json.get("sku_codes") or []
        if sku_codes:
            return ",".join(sorted(str(code) for code in sku_codes))
        return batch_id

    def _start_module(self, mode: Core3RunMode, target_scope_json: dict[str, Any]) -> Core3ModuleCode:
        if mode == Core3RunMode.ACCEPTANCE_ONLY:
            return Core3ModuleCode.M16
        domains = target_scope_json.get("data_domains") or []
        if domains:
            module_codes = [
                CORE3_DATA_DOMAIN_START_MODULE.get(Core3DataDomain(domain), Core3ModuleCode.M00)
                for domain in domains
            ]
            order = self.graph.topological_order()
            return min(module_codes, key=lambda code: order.index(code))
        if mode == Core3RunMode.SINGLE_TARGET_REFRESH:
            return Core3ModuleCode.M08
        if mode == Core3RunMode.RULESET_REPLAY:
            return Core3ModuleCode.M03
        if mode == Core3RunMode.REVIEW_REWORK:
            return Core3ModuleCode.M12
        return Core3ModuleCode.M00

    def _change_domain(self, mode: Core3RunMode, target_scope_json: dict[str, Any]) -> str:
        if mode == Core3RunMode.ACCEPTANCE_ONLY:
            return "report"
        domains = target_scope_json.get("data_domains") or []
        if domains:
            return str(domains[0])
        return "source"

    def _change_reason_cn(
        self,
        mode: Core3RunMode,
        module_code: Core3ModuleCode,
        planned_action: Core3PipelinePlannedAction,
    ) -> str:
        if module_code == Core3ModuleCode.M16:
            return "生成本次生产线复核、验收和发布门禁。"
        if planned_action == Core3PipelinePlannedAction.REUSE:
            return f"{CORE3_MODULE_LABEL_CN[module_code]} 已有上游产物，本次只做治理层复用和验收。"
        if planned_action == Core3PipelinePlannedAction.BLOCK:
            return f"{CORE3_MODULE_LABEL_CN[module_code]} 缺少可验收产物，后续发布门禁需要阻断。"
        return f"{mode.value} 模式下计划运行 {CORE3_MODULE_LABEL_CN[module_code]}。"
