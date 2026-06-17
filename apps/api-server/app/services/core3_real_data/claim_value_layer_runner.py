"""M11.5 claim value layer runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.claim_value_layer_repositories import (
    ClaimValueLayerRepository,
    M115InputBlockedError,
)
from app.services.core3_real_data.claim_value_layer_schemas import M115ServiceResult, M115SkuClaimValueReviewIssueRecord
from app.services.core3_real_data.claim_value_layer_service import ClaimValueLayerService
from app.services.core3_real_data.claim_value_seed_loader import M115ClaimValueSeedError
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M11_5_MODULE_VERSION,
    CORE3_M11_5_RULE_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


class ClaimValueLayerRunner:
    module_code = Core3ModuleCode.M11_5

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
                message_cn="M11.5 缺少 M00 batch_id，无法生成战场内卖点价值分层。",
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
            rule_version=str(target.metadata.get("rule_version") or CORE3_M11_5_RULE_VERSION),
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
        rule_version: str = CORE3_M11_5_RULE_VERSION,
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
                service_result = ClaimValueLayerService(ClaimValueLayerRepository(context)).run_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_scope=sku_scope,
                    rule_version=rule_version,
                )
        except (M115InputBlockedError, M115ClaimValueSeedError, ValueError) as exc:
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
            "module_version": CORE3_M11_5_MODULE_VERSION,
            "target_sku_codes": list(sku_scope),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m11_5_claim_value_summary_v1")
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M11_5,
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


def _review_issues(result: M115ServiceResult) -> list[Core3ReviewIssueSchema]:
    return [_review_issue_schema(issue) for issue in result.review_issues[:100]]


def _review_issue_schema(issue: M115SkuClaimValueReviewIssueRecord) -> Core3ReviewIssueSchema:
    return Core3ReviewIssueSchema(
        issue_code=issue.issue_type,
        issue_type="m11_5_claim_value_review",
        severity=_review_severity(issue.issue_level),
        source_module=Core3ModuleCode.M11_5,
        object_type="sku_claim_value_layer",
        object_id=issue.related_layer_id,
        target_sku_code=issue.sku_code,
        evidence_refs=issue.evidence_ids,
        message_cn=issue.issue_message_cn,
        suggestion_cn="复核该卖点在当前战场内是否可作为后续候选召回和竞品评分依据。",
        review_required=True,
    )


def _review_severity(value: str) -> str:
    return {
        "info": "low",
        "warning": "medium",
        "blocking": "blocker",
        "blocker": "blocker",
        "error": "high",
    }.get(value, value if value in {"low", "medium", "high", "blocker"} else "medium")


def _downstream_impacts(result: M115ServiceResult) -> list[dict[str, object]]:
    return [
        {
            "sku_code": summary.sku_code,
            "battlefield_code": summary.battlefield_code,
            "module_codes": ["M12", "M13", "M14", "M15"],
            "data_domains": [Core3DataDomain.CLAIM_VALUE.value],
            "reason_cn": "M11.5 战场内卖点价值分层、证据拆分或复核状态发生变化",
        }
        for summary in result.summaries
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
        module_code=Core3ModuleCode.M11_5,
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
        module_code=Core3ModuleCode.M11_5,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=[error_message],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
