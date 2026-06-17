"""M16 pipeline governance runner."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.constants import (
    CORE3_M16_MODULE_VERSION,
    CORE3_M16_RULE_VERSION,
    Core3ModuleCode,
    Core3PipelineTriggerType,
)
from app.services.core3_real_data.pipeline_execution_service import PipelineExecutionService
from app.services.core3_real_data.pipeline_repositories import PipelineRepository
from app.services.core3_real_data.pipeline_schemas import M16PipelineRunRequest, M16TargetScope
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


class PipelineGovernanceRunner:
    module_code = Core3ModuleCode.M16

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        request = M16PipelineRunRequest(
            project_id=context.project_id,
            category_code=context.category_code,
            run_id=context.run_id,
            data_batch_id=context.batch_id or target.metadata.get("batch_id"),
            run_mode=context.run_mode,
            trigger_type=Core3PipelineTriggerType.MANUAL,
            triggered_by=context.triggered_by,
            target_scope=M16TargetScope(
                scope_type=context.target_scope.scope_type,
                sku_codes=list(context.target_scope.sku_codes or target.target_ids),
                include_related_targets=context.target_scope.include_related_targets,
                related_target_reason=context.target_scope.related_target_reason,
                data_domains=list(context.target_scope.data_domains or target.data_domains),
                note_cn=context.target_scope.note_cn or "M16 生产线治理验收",
            ),
            ruleset_version=context.ruleset_version,
            module_version=context.module_version(Core3ModuleCode.M16) or CORE3_M16_MODULE_VERSION,
            rule_version=target.metadata.get("rule_version", CORE3_M16_RULE_VERSION),
            module_versions=dict(context.module_versions or {}),
            seed_versions=dict(context.seed_versions or {}),
            input_watermarks=dict(context.input_watermarks or {}),
        )
        repository = PipelineRepository(
            Core3RepositoryContext(
                db=self.db,
                project_id=context.project_id,
                category_code=context.category_code,
            )
        )
        artifacts = PipelineExecutionService(repository).run(request)
        m16_run = next(row for row in artifacts.module_runs if row.module_code == Core3ModuleCode.M16.value)
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M16,
            status=m16_run.status,
            input_count=m16_run.input_count,
            changed_input_count=m16_run.changed_input_count,
            output_count=m16_run.output_count,
            output_hash=m16_run.output_hash,
            warnings=m16_run.warnings_json or [],
            review_issues=[],
            downstream_impacts=[m16_run.downstream_impact_json or {}],
            summary_json=m16_run.summary_json or {},
            started_at=m16_run.started_at,
            finished_at=m16_run.finished_at,
        )
