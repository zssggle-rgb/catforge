"""Operator-facing initialization status for Core3 real-data pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import (
    Core3PipelineInitializationModuleStatus,
    Core3PipelineInitializationStatusResponse,
)
from app.services.core3_real_data.constants import (
    CORE3_M03B_RULE_VERSION,
    CORE3_M03_RULE_VERSION,
    CORE3_MODULE_LABEL_CN,
    Core3CategoryCode,
    Core3ModuleCode,
    Core3RunStatus,
)


@dataclass(frozen=True)
class InitializationArtifact:
    model: type
    target_field: str | None = None
    current_only: bool = True
    where_equals: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class InitializationModuleSpec:
    module_code: Core3ModuleCode
    stage_name_cn: str
    stage_description_cn: str
    artifacts: tuple[InitializationArtifact, ...]
    output_target_field: str | None = None
    result_entry_url: str | None = None


INITIALIZATION_MODULE_SPECS: tuple[InitializationModuleSpec, ...] = (
    InitializationModuleSpec(
        Core3ModuleCode.M00,
        "读取原始数据",
        "扫描原始表，识别新增、变化和未变化的 SKU 数据。",
        (
            InitializationArtifact(entities.Core3SourceRowRegistry, "sku_code_candidate", current_only=False),
            InitializationArtifact(entities.Core3SourceImpactedSku, "sku_code_candidate", current_only=False),
        ),
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M01,
        "清洗与去重",
        "标准化 SKU、价格销量、参数、卖点和评论，标记低价值及重复评论。",
        (
            InitializationArtifact(entities.Core3CleanSku, "sku_code", current_only=False),
            InitializationArtifact(entities.Core3CleanMarketWeekly, "sku_code", current_only=False),
            InitializationArtifact(entities.Core3CleanAttribute, "sku_code", current_only=False),
            InitializationArtifact(entities.Core3CleanClaim, "sku_code", current_only=False),
            InitializationArtifact(entities.Core3CleanComment, "sku_code", current_only=False),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M02,
        "生成证据库",
        "把清洗后的事实转成可追溯证据，并排除不能下游消费的低价值评论证据。",
        (InitializationArtifact(entities.Core3EvidenceAtom, "sku_code"),),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M03,
        "生成参数画像",
        "从参数、卖点和质量提示中抽取标准参数，形成 SKU 参数画像。",
        (
            InitializationArtifact(entities.Core3ExtractParamValue, "sku_code", where_equals=(("rule_version", CORE3_M03_RULE_VERSION),)),
            InitializationArtifact(entities.Core3SkuParamProfile, "sku_code", where_equals=(("rule_version", CORE3_M03_RULE_VERSION),)),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M03B,
        "生成 SKU 参数事实画像",
        "只基于参数 evidence 生成 SKU 参数事实画像，并形成各参数维度档位与档位覆盖。",
        (
            InitializationArtifact(entities.Core3ExtractParamValue, "sku_code", where_equals=(("rule_version", CORE3_M03B_RULE_VERSION),)),
            InitializationArtifact(entities.Core3SkuParamProfile, "sku_code", where_equals=(("rule_version", CORE3_M03B_RULE_VERSION),)),
            InitializationArtifact(entities.Core3SkuParamDimensionTier, "sku_code", where_equals=(("rule_version", CORE3_M03B_RULE_VERSION),)),
            InitializationArtifact(entities.Core3ParamTierCoverage, None, where_equals=(("rule_version", CORE3_M03B_RULE_VERSION),)),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M04A,
        "生成卖点画像",
        "结合结构化卖点和参数证据，判断每个 SKU 可成立的基础卖点。",
        (
            InitializationArtifact(entities.Core3SkuClaimSourceStatus, "sku_code"),
            InitializationArtifact(entities.Core3SkuClaimActivationBase, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M05,
        "整理评论证据",
        "将代表评论拆成可用语义单元，建立评论质量画像。",
        (
            InitializationArtifact(entities.Core3CommentQualityProfile, "sku_code"),
            InitializationArtifact(entities.Core3CommentUnit, "sku_code"),
            InitializationArtifact(entities.Core3CommentEvidenceAtom, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M06,
        "抽取评论信号",
        "从可用评论证据中抽取用户任务、客群、战场、痛点和价格感知线索。",
        (
            InitializationArtifact(entities.Core3SkuCommentSignalProfile, "sku_code"),
            InitializationArtifact(entities.Core3CommentDownstreamSignal, "sku_code"),
            InitializationArtifact(entities.Core3CommentSignalCandidate, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M04B,
        "评论验证卖点",
        "用评论信号验证、增强或削弱基础卖点，形成可下游使用的卖点激活结果。",
        (
            InitializationArtifact(entities.Core3SkuClaimCommentValidation, "sku_code"),
            InitializationArtifact(entities.Core3SkuClaimActivation, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M07,
        "生成市场画像",
        "生成价格、销量、渠道和可比池画像，为后续竞品召回提供市场边界。",
        (
            InitializationArtifact(entities.Core3SkuMarketProfile, "sku_code"),
            InitializationArtifact(entities.Core3MarketSignal, "sku_code"),
            InitializationArtifact(entities.Core3ComparablePoolBaseline, "target_sku_code"),
            InitializationArtifact(entities.Core3MarketPoolMember, "target_sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M08,
        "汇总 SKU 信号",
        "汇总参数、卖点、评论和市场证据，形成后续模块统一消费的 SKU 画像。",
        (
            InitializationArtifact(entities.Core3SkuSignalProfile, "sku_code"),
            InitializationArtifact(entities.Core3SkuSignalEvidenceMatrix, "sku_code"),
            InitializationArtifact(entities.Core3SkuDownstreamFeatureView, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M08_4,
        "发现原生维度",
        "先从真实可用评论中发现原生任务、客群、产品价值和服务语境，再与预设维度对齐。",
        (
            InitializationArtifact(entities.Core3CommentNativeSignal, "native_signal_code"),
            InitializationArtifact(entities.Core3NativeDimensionCandidate, "native_dimension_code"),
            InitializationArtifact(entities.Core3NativeDimensionSkuSupport, "sku_code"),
            InitializationArtifact(entities.Core3NativeDimensionAlignmentProposal, "alignment_key"),
            InitializationArtifact(entities.Core3NativeDimensionReviewIssue, "object_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M08_5,
        "校准业务维度",
        "消费原生维度发现结果，结合参数、卖点和 SKU 画像校准任务、客群、战场定义，剥离服务履约线索。",
        (
            InitializationArtifact(entities.Core3DimensionOntologyVersion, None),
            InitializationArtifact(entities.Core3DimensionDefinition, "dimension_code"),
            InitializationArtifact(entities.Core3DimensionCandidateSnapshot, "signal_code"),
            InitializationArtifact(entities.Core3DimensionCalibrationIssue, "dimension_code"),
        ),
        output_target_field="dimension_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M09,
        "识别用户任务",
        "基于 SKU 综合画像推导用户任务，而不是直接把评论标签当结论。",
        (
            InitializationArtifact(entities.Core3SkuTaskCandidate, "sku_code"),
            InitializationArtifact(entities.Core3SkuTaskScore, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M10,
        "识别目标客群",
        "结合任务、评论、价格渠道和市场表现推导目标客群。",
        (
            InitializationArtifact(entities.Core3SkuTargetGroupCandidate, "sku_code"),
            InitializationArtifact(entities.Core3SkuTargetGroupScore, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M11,
        "识别价值战场",
        "结合任务、客群、卖点、参数、评论和市场表现推导价值战场。",
        (
            InitializationArtifact(entities.Core3SkuBattlefieldCandidate, "sku_code"),
            InitializationArtifact(entities.Core3SkuBattlefieldScore, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M11_5,
        "卖点价值分层",
        "在价值战场内判断卖点是核心价值、支撑价值还是弱相关线索。",
        (InitializationArtifact(entities.Core3SkuClaimValueLayer, "sku_code"),),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M11_6,
        "生成 SKU 业务画像",
        "汇总主战场、主任务、主客群、卖点价值、溢价和市场角色，形成 SKU 级业务画像。",
        (
            InitializationArtifact(entities.Core3SkuBusinessProfile, "sku_code"),
            InitializationArtifact(entities.Core3SkuBusinessProfileDimension, "sku_code"),
            InitializationArtifact(entities.Core3SkuBusinessProfileSalesAllocation, "sku_code"),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M11_7,
        "校验销量分配",
        "校验卖点、任务、客群和价值战场的估算销量是否与 SKU 总销量横纵一致。",
        (
            InitializationArtifact(entities.Core3BusinessDimensionSalesSummary, "dimension_code"),
            InitializationArtifact(entities.Core3BusinessDimensionSkuContribution, "sku_code"),
            InitializationArtifact(entities.Core3BusinessSalesReconciliationCheck, None),
        ),
        output_target_field="sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M12,
        "召回候选竞品",
        "基于战场、价格、尺寸、渠道和画像相似性召回候选竞品池。",
        (InitializationArtifact(entities.Core3CandidatePool, "target_sku_code"),),
        output_target_field="target_sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M13,
        "计算竞品得分",
        "按角色和证据组件计算候选竞品的对打、挤压和标杆分。",
        (
            InitializationArtifact(entities.Core3CandidateComponentScore, "target_sku_code"),
            InitializationArtifact(entities.Core3CandidateRoleScore, "target_sku_code"),
        ),
        output_target_field="target_sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M14,
        "选择核心三竞品",
        "按三类业务角色选择核心竞品，保留未入选和空槽原因。",
        (InitializationArtifact(entities.Core3CompetitorSelection, "target_sku_code"),),
        output_target_field="target_sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M15,
        "生成竞品报告",
        "生成面向业务汇报的竞品结论、证据卡和报告结构。",
        (
            InitializationArtifact(entities.Core3TargetReportPayload, "target_sku_code"),
            InitializationArtifact(entities.Core3ReportEvidenceCard, "target_sku_code"),
        ),
        output_target_field="target_sku_code",
    ),
    InitializationModuleSpec(
        Core3ModuleCode.M16,
        "验收与发布检查",
        "复用已落库产物生成验收、复核队列和发布门禁。",
        (
            InitializationArtifact(entities.Core3V2AcceptanceReport, None, current_only=False),
            InitializationArtifact(entities.Core3V2ReleaseGate, "target_sku_code", current_only=False),
        ),
        output_target_field="target_sku_code",
    ),
)


INITIALIZATION_MODULE_ORDER: tuple[Core3ModuleCode, ...] = tuple(spec.module_code for spec in INITIALIZATION_MODULE_SPECS)


class PipelineInitializationStatusService:
    def __init__(self, db: Session, project_id: str, category_code: Core3CategoryCode | str = Core3CategoryCode.TV) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = Core3CategoryCode(category_code)

    def build_status(self, batch_id: str | None = None) -> Core3PipelineInitializationStatusResponse:
        batch = self._resolve_batch(batch_id)
        resolved_batch_id = batch.batch_id if batch else None
        source_row_count = self._count(entities.Core3SourceRowRegistry, resolved_batch_id, current_only=False)
        impacted_sku_count = self._count(entities.Core3SourceImpactedSku, resolved_batch_id, current_only=False)
        clean_sku_count = self._count(entities.Core3CleanSku, resolved_batch_id, current_only=False)
        expected_target_count = clean_sku_count or impacted_sku_count
        latest_pipeline_run = self._latest_pipeline_run(resolved_batch_id)
        module_statuses: list[Core3PipelineInitializationModuleStatus] = []
        for spec in INITIALIZATION_MODULE_SPECS:
            module_statuses.append(
                self._module_status(
                    spec,
                    batch_id=resolved_batch_id,
                    expected_target_count=expected_target_count,
                    previous_statuses=module_statuses,
                )
            )
        ready_count = sum(1 for item in module_statuses if item.execution_status == "completed")
        return Core3PipelineInitializationStatusResponse(
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=resolved_batch_id,
            batch_status_cn=_batch_status_cn(batch),
            source_row_count=source_row_count,
            impacted_sku_count=impacted_sku_count,
            clean_sku_count=clean_sku_count,
            latest_pipeline_run_id=latest_pipeline_run.run_id if latest_pipeline_run else None,
            modules=module_statuses,
            summary_cn=f"当前生产线共有 {len(module_statuses)} 个环节，已形成完整产物 {ready_count} 个环节。",
        )

    def _module_status(
        self,
        spec: InitializationModuleSpec,
        *,
        batch_id: str | None,
        expected_target_count: int,
        previous_statuses: list[Core3PipelineInitializationModuleStatus],
    ) -> Core3PipelineInitializationModuleStatus:
        latest_run = self._latest_module_run(spec.module_code, batch_id)
        output_count = sum(self._artifact_count(artifact, batch_id) for artifact in spec.artifacts)
        processed_target_count = self._processed_target_count(spec, batch_id)
        current_output_count = sum(self._artifact_count(artifact, batch_id, current_only=True) for artifact in spec.artifacts)
        review_issue_count = _review_issue_count(latest_run)
        warning_count = len(latest_run.warnings_json or []) if latest_run else 0
        blocked_reason = _blocked_reason_for_previous(previous_statuses)
        execution_status = self._execution_status(
            spec,
            output_count=output_count,
            processed_target_count=processed_target_count,
            expected_target_count=expected_target_count,
            latest_run=latest_run,
            blocked_reason=blocked_reason,
            batch_id=batch_id,
        )
        can_skip = (
            spec.module_code != Core3ModuleCode.M00
            and execution_status == "completed"
            and latest_run is not None
            and latest_run.status
            in {
                Core3RunStatus.SUCCESS.value,
                Core3RunStatus.WARNING.value,
                Core3RunStatus.SKIPPED_REUSED.value,
            }
        )
        return Core3PipelineInitializationModuleStatus(
            module_code=spec.module_code,
            module_name_cn=CORE3_MODULE_LABEL_CN.get(spec.module_code, spec.module_code.value),
            stage_name_cn=spec.stage_name_cn,
            stage_description_cn=spec.stage_description_cn,
            execution_status=execution_status,
            execution_status_cn=_execution_status_cn(execution_status),
            can_execute=blocked_reason is None or spec.module_code == Core3ModuleCode.M00,
            can_skip=can_skip,
            skip_reason_cn="已完成且未发现必须重跑的新增影响，默认跳过。" if can_skip else None,
            blocked_reason_cn=blocked_reason,
            expected_target_count=expected_target_count,
            processed_target_count=processed_target_count,
            output_count=output_count,
            current_output_count=current_output_count,
            review_issue_count=review_issue_count,
            warning_count=warning_count,
            latest_run_id=latest_run.run_id if latest_run else None,
            latest_module_run_id=latest_run.module_run_id if latest_run else None,
            latest_status=latest_run.status if latest_run else None,
            latest_started_at=latest_run.started_at if latest_run else None,
            latest_finished_at=latest_run.finished_at if latest_run else None,
            latest_summary_cn=_module_summary_cn(spec, latest_run, output_count, processed_target_count),
            latest_summary_json=dict(latest_run.summary_json or {}) if latest_run else {},
            result_entry_url=spec.result_entry_url,
        )

    def _execution_status(
        self,
        spec: InitializationModuleSpec,
        *,
        output_count: int,
        processed_target_count: int,
        expected_target_count: int,
        latest_run: entities.Core3V2ModuleRun | None,
        blocked_reason: str | None,
        batch_id: str | None,
    ) -> str:
        if spec.module_code != Core3ModuleCode.M00 and not batch_id:
            return "blocked"
        if latest_run and latest_run.status in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value}:
            return "failed" if latest_run.status == Core3RunStatus.FAILED.value else "blocked"
        if output_count <= 0:
            return "blocked" if blocked_reason else "not_started"
        if spec.output_target_field and expected_target_count > 0 and processed_target_count < expected_target_count:
            return "partial"
        return "completed"

    def _processed_target_count(self, spec: InitializationModuleSpec, batch_id: str | None) -> int:
        if not batch_id:
            return 0
        target_field = spec.output_target_field
        if not target_field:
            return 1 if sum(self._artifact_count(artifact, batch_id) for artifact in spec.artifacts) else 0
        totals = []
        for artifact in spec.artifacts:
            if not hasattr(artifact.model, target_field):
                continue
            totals.append(
                self._artifact_count_distinct(
                    artifact,
                    target_field,
                    batch_id,
                )
            )
        return max(totals or [0])

    def _artifact_count(self, artifact: InitializationArtifact, batch_id: str | None, *, current_only: bool | None = None) -> int:
        return self._count(
            artifact.model,
            batch_id,
            current_only=artifact.current_only if current_only is None else current_only,
            where_equals=artifact.where_equals,
        )

    def _artifact_count_distinct(
        self,
        artifact: InitializationArtifact,
        field_name: str,
        batch_id: str | None,
    ) -> int:
        return self._count_distinct(
            artifact.model,
            field_name,
            batch_id,
            current_only=artifact.current_only,
            where_equals=artifact.where_equals,
        )

    def _count(
        self,
        model: type,
        batch_id: str | None,
        *,
        current_only: bool,
        where_equals: tuple[tuple[str, Any], ...] = (),
    ) -> int:
        filters = self._base_filters(model, batch_id, current_only=current_only, where_equals=where_equals)
        if filters is None:
            return 0
        return int(self.db.execute(select(func.count()).select_from(model).where(*filters)).scalar_one())

    def _count_distinct(
        self,
        model: type,
        field_name: str,
        batch_id: str | None,
        *,
        current_only: bool,
        where_equals: tuple[tuple[str, Any], ...] = (),
    ) -> int:
        filters = self._base_filters(model, batch_id, current_only=current_only, where_equals=where_equals)
        if filters is None:
            return 0
        field = getattr(model, field_name)
        return int(self.db.execute(select(func.count(func.distinct(field))).select_from(model).where(*filters)).scalar_one())

    def _base_filters(
        self,
        model: type,
        batch_id: str | None,
        *,
        current_only: bool,
        where_equals: tuple[tuple[str, Any], ...] = (),
    ) -> list[Any] | None:
        if not hasattr(model, "project_id"):
            return None
        filters: list[Any] = [model.project_id == self.project_id]
        if hasattr(model, "category_code"):
            filters.append(model.category_code == self.category_code.value)
        if batch_id and hasattr(model, "batch_id"):
            filters.append(model.batch_id == batch_id)
        if current_only and hasattr(model, "is_current"):
            filters.append(model.is_current.is_(True))
        for field_name, expected_value in where_equals:
            if not hasattr(model, field_name):
                return None
            filters.append(getattr(model, field_name) == expected_value)
        return filters

    def _resolve_batch(self, batch_id: str | None) -> entities.Core3SourceBatch | None:
        stmt = (
            select(entities.Core3SourceBatch)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(entities.Core3SourceBatch.category_code == self.category_code.value)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3SourceBatch.batch_id == batch_id)
        return self.db.execute(stmt.order_by(entities.Core3SourceBatch.updated_at.desc())).scalars().first()

    def _latest_pipeline_run(self, batch_id: str | None) -> entities.Core3V2PipelineRun | None:
        stmt = (
            select(entities.Core3V2PipelineRun)
            .where(entities.Core3V2PipelineRun.project_id == self.project_id)
            .where(entities.Core3V2PipelineRun.category_code == self.category_code.value)
        )
        if batch_id:
            stmt = stmt.where(entities.Core3V2PipelineRun.data_batch_id == batch_id)
        return self.db.execute(stmt.order_by(entities.Core3V2PipelineRun.updated_at.desc())).scalars().first()

    def _latest_module_run(
        self,
        module_code: Core3ModuleCode,
        batch_id: str | None,
    ) -> entities.Core3V2ModuleRun | None:
        base_stmt = (
            select(entities.Core3V2ModuleRun)
            .where(entities.Core3V2ModuleRun.project_id == self.project_id)
            .where(entities.Core3V2ModuleRun.category_code == self.category_code.value)
            .where(entities.Core3V2ModuleRun.module_code == module_code.value)
        )
        if batch_id:
            base_stmt = base_stmt.where(entities.Core3V2ModuleRun.batch_id == batch_id)

        executed_run = (
            self.db.execute(
                base_stmt.where(entities.Core3V2ModuleRun.status != Core3RunStatus.SKIPPED_REUSED.value).order_by(
                    entities.Core3V2ModuleRun.updated_at.desc()
                )
            )
            .scalars()
            .first()
        )
        if executed_run is not None:
            return executed_run
        return self.db.execute(base_stmt.order_by(entities.Core3V2ModuleRun.updated_at.desc())).scalars().first()


def module_spec(module_code: Core3ModuleCode | str) -> InitializationModuleSpec:
    normalized = Core3ModuleCode(module_code)
    for spec in INITIALIZATION_MODULE_SPECS:
        if spec.module_code == normalized:
            return spec
    raise ValueError(f"unknown initialization module: {module_code}")


def _batch_status_cn(batch: entities.Core3SourceBatch | None) -> str:
    if batch is None:
        return "尚未读取原始数据"
    if batch.status in {"registered", "registered_with_warning"}:
        return "原始数据已读取"
    if batch.status == "running":
        return "正在读取原始数据"
    if batch.status == "failed":
        return "原始数据读取失败"
    return "原始数据状态待确认"


def _execution_status_cn(status: str) -> str:
    return {
        "completed": "已完成",
        "partial": "部分完成",
        "not_started": "未执行",
        "blocked": "等待上游",
        "failed": "执行失败",
    }.get(status, "状态待确认")


def _blocked_reason_for_previous(previous_statuses: list[Core3PipelineInitializationModuleStatus]) -> str | None:
    for item in previous_statuses:
        if item.execution_status in {"not_started", "blocked", "failed"}:
            return f"需要先完成“{item.stage_name_cn}”。"
    return None


def _review_issue_count(latest_run: entities.Core3V2ModuleRun | None) -> int:
    if latest_run is None:
        return 0
    summary = latest_run.review_issue_summary_json or {}
    return int(summary.get("count") or 0)


def _module_summary_cn(
    spec: InitializationModuleSpec,
    latest_run: entities.Core3V2ModuleRun | None,
    output_count: int,
    processed_target_count: int,
) -> str:
    if latest_run and latest_run.error_message_cn:
        return latest_run.error_message_cn
    if output_count <= 0:
        return f"尚未生成“{spec.stage_name_cn}”产物。"
    if processed_target_count > 0:
        return f"已生成 {output_count} 条产物，覆盖 {processed_target_count} 个 SKU。"
    return f"已生成 {output_count} 条产物。"
