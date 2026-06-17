"""M11.7 dimension sales reconciliation runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M11_7_MODULE_VERSION,
    CORE3_M11_7_RULE_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.dimension_sales_reconciliation_repositories import (
    DimensionSalesReconciliationRepository,
    M117InputBlockedError,
)
from app.services.core3_real_data.dimension_sales_reconciliation_schemas import (
    M117BusinessSalesReconciliationIssueRecord,
    M117ServiceResult,
)
from app.services.core3_real_data.dimension_sales_reconciliation_service import DimensionSalesReconciliationService
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


class DimensionSalesReconciliationRunner:
    module_code = Core3ModuleCode.M11_7

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
                message_cn="M11.7 缺少 M00 batch_id，无法做销量分配对账。",
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
            rule_version=str(target.metadata.get("rule_version") or CORE3_M11_7_RULE_VERSION),
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
        rule_version: str = CORE3_M11_7_RULE_VERSION,
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
                service_result = DimensionSalesReconciliationService(
                    DimensionSalesReconciliationRepository(context)
                ).run_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_scope=sku_scope,
                    rule_version=rule_version,
                )
        except (M117InputBlockedError, ValueError) as exc:
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
            "module_version": CORE3_M11_7_MODULE_VERSION,
            "target_sku_codes": list(sku_scope),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m11_7_dimension_sales_reconciliation_summary_v1")
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M11_7,
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


def _review_issues(result: M117ServiceResult) -> list[Core3ReviewIssueSchema]:
    return [_review_issue_schema(issue) for issue in result.issues[:100]]


def _review_issue_schema(issue: M117BusinessSalesReconciliationIssueRecord) -> Core3ReviewIssueSchema:
    return Core3ReviewIssueSchema(
        issue_code=issue.issue_code,
        issue_type="m11_7_sales_reconciliation_review",
        severity="blocker" if issue.severity == "blocker" else "medium",
        source_module=Core3ModuleCode.M11_7,
        object_type=issue.issue_scope,
        object_id=issue.reconciliation_issue_id,
        target_sku_code=issue.sku_code or None,
        evidence_refs=issue.evidence_ids,
        message_cn=issue.issue_message_cn,
        suggestion_cn=issue.suggested_action_cn,
        review_required=True,
    )


def _downstream_impacts(result: M117ServiceResult) -> list[dict[str, object]]:
    impacted_skus = sorted({item.sku_code for item in result.contributions})
    return [
        {
            "sku_code": sku_code,
            "module_codes": ["M12", "M13", "M14", "M15", "M16"],
            "data_domains": [Core3DataDomain.PROFILE.value, Core3DataDomain.CLAIM_VALUE.value],
            "reason_cn": "M11.7 销量分配对账或维度市场结构发生变化",
        }
        for sku_code in impacted_skus
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
        module_code=Core3ModuleCode.M11_7,
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
        module_code=Core3ModuleCode.M11_7,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=[f"M11.7 dimension sales reconciliation failed: {error_message}"],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
