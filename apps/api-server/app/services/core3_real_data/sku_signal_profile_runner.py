"""M08 SKU signal profile runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M08_FEATURE_VERSION,
    CORE3_M08_MODULE_VERSION,
    CORE3_M08_RULE_VERSION,
    CORE3_M08_VIEW_SCHEMA_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget
from app.services.core3_real_data.sku_signal_profile_repositories import (
    M08InputBlockedError,
    M08SkuSignalRepository,
)
from app.services.core3_real_data.sku_signal_profile_schemas import M08QualityIssue
from app.services.core3_real_data.sku_signal_profile_service import M08ServiceResult, SkuSignalProfileService


class SkuSignalProfileRunner:
    module_code = Core3ModuleCode.M08

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(
                project_id=context.project_id,
                category_code=context.category_code.value,
                batch_id=None,
                run_id=context.run_id,
                message_cn="M08 缺少 M00 batch_id，无法生成 SKU 综合信号画像。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            batch_id=batch_id,
            category_code=context.category_code.value,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            sku_scope=target.target_ids,
            rule_version=str(target.metadata.get("rule_version") or CORE3_M08_RULE_VERSION),
            feature_version=str(target.metadata.get("feature_version") or CORE3_M08_FEATURE_VERSION),
            view_schema_version=str(target.metadata.get("view_schema_version") or CORE3_M08_VIEW_SCHEMA_VERSION),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M08_RULE_VERSION,
        feature_version: str = CORE3_M08_FEATURE_VERSION,
        view_schema_version: str = CORE3_M08_VIEW_SCHEMA_VERSION,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        context = Core3RepositoryContext(db=self.db, project_id=project_id, category_code=category_code)
        try:
            SourceBatchReader(context).get_consumable_batch(batch_id)
        except ValueError as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        try:
            with self.db.begin_nested():
                service_result = SkuSignalProfileService(M08SkuSignalRepository(context)).run_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_scope=sku_scope,
                    rule_version=rule_version,
                    feature_version=feature_version,
                    view_schema_version=view_schema_version,
                )
        except (M08InputBlockedError, ValueError) as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_message=str(exc),
            )

        summary_json = {
            "project_id": project_id,
            "category_code": category_code,
            "run_id": run_id,
            "module_version": CORE3_M08_MODULE_VERSION,
            "target_sku_codes": list(sku_scope),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m08_sku_signal_profile_summary_v1")
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M08,
            status=service_result.status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.output_count,
            output_hash=output_hash,
            warnings=service_result.warnings,
            review_issues=_review_issues(service_result),
            downstream_impacts=_downstream_impacts(service_result),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


def _review_issues(result: M08ServiceResult) -> list[Core3ReviewIssueSchema]:
    return [
        _review_issue_schema(issue)
        for issue in result.review_issues[:100]
    ]


def _review_issue_schema(issue: M08QualityIssue) -> Core3ReviewIssueSchema:
    return Core3ReviewIssueSchema(
        issue_code=issue.issue_code,
        issue_type="m08_sku_signal_profile_quality",
        severity=issue.severity,
        source_module=Core3ModuleCode.M08,
        object_type="sku_signal_profile",
        target_sku_code=issue.sku_code,
        evidence_refs=issue.evidence_ids,
        message_cn=issue.message_cn,
        suggestion_cn=issue.suggestion_cn,
        review_required=issue.review_required,
    )


def _downstream_impacts(result: M08ServiceResult) -> list[dict[str, object]]:
    return [
        {
            "sku_code": profile.sku_code,
            "module_codes": ["M08.4", "M08.5", "M09", "M10", "M11", "M11.5", "M12", "M13", "M14", "M15"],
            "data_domains": [Core3DataDomain.PROFILE.value],
            "reason_cn": "M08 SKU 综合信号画像、证据矩阵或下游特征视图发生变化",
        }
        for profile in result.profiles
    ]


def _blocked_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str | None,
    run_id: str | None,
    message_cn: str,
    started_at: datetime,
    finished_at: datetime,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M08,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        output_count=0,
        warnings=[message_cn],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "blocked_reason_cn": message_cn,
        },
        started_at=started_at,
        finished_at=finished_at,
    )


def _failed_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    started_at: datetime,
    error_message: str,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M08,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=["M08 SKU 综合信号画像生成失败", error_message],
        review_issues=[
            Core3ReviewIssueSchema(
                issue_code="m08_sku_signal_profile_failed",
                issue_type="module_failed",
                severity="blocker",
                source_module=Core3ModuleCode.M08,
                object_type="module",
                evidence_refs=[],
                message_cn="M08 SKU 综合信号画像生成失败，请检查 M03/M04b/M06/M07 上游产物。",
                suggestion_cn="确认参数画像、卖点激活、评论信号、市场画像和可比池已生成后重跑。",
                review_required=True,
            )
        ],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "failed_reason_cn": "M08 SKU 综合信号画像生成失败",
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
