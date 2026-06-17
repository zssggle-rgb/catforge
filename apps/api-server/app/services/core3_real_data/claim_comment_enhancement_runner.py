"""M04b claim comment enhancement runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.claim_comment_enhancement_repositories import (
    ClaimCommentEnhancementRepository,
    M04bInputBlockedError,
)
from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimCommentReviewIssueRecord,
)
from app.services.core3_real_data.claim_comment_enhancement_service import (
    ClaimCommentEnhancementService,
    ClaimCommentEnhancementServiceResult,
)
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M04B_RULE_VERSION,
    CORE3_M04B_SEED_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


class ClaimCommentEnhancementRunner:
    module_code = Core3ModuleCode.M04B

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
                message_cn="M04b 缺少 M00 batch_id，无法确定卖点评论验证范围。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            batch_id=batch_id,
            category_code=context.category_code.value,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            seed_version=str(target.metadata.get("seed_version") or CORE3_M04B_SEED_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M04B_RULE_VERSION),
            sku_scope=target.target_ids,
            claim_scope=tuple(target.metadata.get("claim_scope") or ()),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M04B_SEED_VERSION,
        rule_version: str = CORE3_M04B_RULE_VERSION,
        sku_scope: Sequence[str] = (),
        claim_scope: Sequence[str] = (),
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
                service_result = ClaimCommentEnhancementService(
                    ClaimCommentEnhancementRepository(context)
                ).run_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_scope=sku_scope,
                    claim_scope=claim_scope,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
        except (M04bInputBlockedError, ValueError) as exc:
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
            "batch_id": batch_id,
            "seed_version": seed_version,
            "rule_version": rule_version,
            "target_sku_codes": list(sku_scope),
            "claim_scope": list(claim_scope),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m04b_claim_comment_summary_v1")
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M04B,
            status=_status(service_result),
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.output_count,
            output_hash=output_hash,
            warnings=service_result.warnings,
            review_issues=[_review_issue_schema(issue) for issue in service_result.issues[:50]],
            downstream_impacts=_downstream_impacts(service_result),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


def _status(result: ClaimCommentEnhancementServiceResult) -> Core3RunStatus:
    if not result.bundles:
        return Core3RunStatus.BLOCKED
    if result.issues or result.warnings:
        return Core3RunStatus.WARNING
    return Core3RunStatus.SUCCESS


def _review_issue_schema(issue: ClaimCommentReviewIssueRecord) -> Core3ReviewIssueSchema:
    return Core3ReviewIssueSchema(
        issue_code=issue.issue_type,
        issue_type=issue.issue_type,
        severity=_severity(issue.severity),
        source_module=Core3ModuleCode.M04B,
        object_type="claim_activation",
        object_id=issue.claim_activation_id,
        target_sku_code=issue.sku_code,
        evidence_refs=issue.evidence_ids,
        message_cn=issue.business_note,
        suggestion_cn=issue.suggested_action,
        review_required=issue.review_required,
    )


def _severity(value: str) -> str:
    return {
        "info": "low",
        "warning": "medium",
        "review_required": "high",
        "blocked": "blocker",
    }.get(str(value), "medium")


def _downstream_impacts(result: ClaimCommentEnhancementServiceResult) -> list[dict[str, object]]:
    sku_codes = sorted({activation.sku_code for activation in result.activations})
    return [
        {
            "sku_code": sku_code,
            "module_codes": ["M08", "M09", "M10", "M11", "M11.5", "M12", "M13", "M14", "M15", "M16"],
            "data_domains": [Core3DataDomain.CLAIM.value, Core3DataDomain.COMMENT.value],
            "reason_cn": "M04b 最终卖点激活或评论验证风险发生变化",
        }
        for sku_code in sku_codes
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
        module_code=Core3ModuleCode.M04B,
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
        module_code=Core3ModuleCode.M04B,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=["M04b 评论验证增强失败", error_message],
        review_issues=[
            Core3ReviewIssueSchema(
                issue_code="m04b_claim_comment_failed",
                issue_type="module_failed",
                severity="blocker",
                source_module=Core3ModuleCode.M04B,
                object_type="module",
                evidence_refs=[],
                message_cn="M04b 评论验证增强失败，请检查 M04a/M06 产物和本地 fixture。",
                suggestion_cn="确认 M04a 基础卖点、M06 claim_validation 信号和 seed 后重跑。",
                review_required=True,
            )
        ],
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
