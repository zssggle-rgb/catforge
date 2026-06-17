"""M06 comment downstream signal runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.comment_downstream_signal_repositories import (
    CommentDownstreamSignalReadRepository,
    M06InputBlockedError,
)
from app.services.core3_real_data.comment_downstream_signal_schemas import CommentSignalReviewIssue
from app.services.core3_real_data.comment_downstream_signal_service import (
    CommentDownstreamSignalService,
    CommentDownstreamSignalServiceResult,
)
from app.services.core3_real_data.comment_signal_input_service import CommentSignalInputService
from app.services.core3_real_data.comment_signal_seed_loader import (
    CommentSignalSeedLoader,
    CommentSignalSeedValidationError,
)
from app.services.core3_real_data.constants import (
    CORE3_M06_MODULE_VERSION,
    CORE3_M06_RULE_VERSION,
    CORE3_M06_SEED_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


@dataclass(frozen=True)
class CommentDownstreamSignalBatchResult:
    input_count: int
    sku_count: int
    candidate_count: int
    downstream_signal_count: int
    sku_profile_count: int
    ready_sku_count: int
    review_required_count: int
    warnings: list[str]
    review_issues: list[CommentSignalReviewIssue]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item.get("created_count", 0) for item in self.write_summary.values())

    @property
    def output_count(self) -> int:
        return self.candidate_count + self.downstream_signal_count + self.sku_profile_count


class CommentDownstreamSignalRunner:
    module_code = Core3ModuleCode.M06

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
                message_cn="M06 缺少 M00 batch_id，无法确定评论信号抽取范围。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            batch_id=batch_id,
            category_code=context.category_code.value,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            seed_version=str(target.metadata.get("seed_version") or CORE3_M06_SEED_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M06_RULE_VERSION),
            target_sku_codes=target.target_ids,
            signal_types=target.metadata.get("signal_types") or (),
            sku_batch_size=int(target.metadata.get("sku_batch_size") or 1),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M06_SEED_VERSION,
        rule_version: str = CORE3_M06_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        signal_types: Sequence[str] = (),
        sku_batch_size: int = 1,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        normalized_sku_batch_size = _normalize_sku_batch_size(sku_batch_size)
        requested_sku_codes = _normalize_sku_codes(target_sku_codes)
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

        sku_batches = _resolve_sku_batches(
            context,
            batch_id=batch_id,
            requested_sku_codes=requested_sku_codes,
            sku_batch_size=normalized_sku_batch_size,
        )
        batch_results: list[CommentDownstreamSignalBatchResult] = []
        try:
            for batch_index, sku_batch in enumerate(sku_batches, start=1):
                batch_result = CommentDownstreamSignalBatchService(context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    seed_version=seed_version,
                    rule_version=rule_version,
                    target_sku_codes=sku_batch,
                    signal_types=signal_types,
                )
                batch_result.summary["batch_index"] = batch_index
                self.db.commit()
                batch_results.append(batch_result)
        except (M06InputBlockedError, CommentSignalSeedValidationError, ValueError) as exc:
            self.db.rollback()
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m06_comment_signal_failed",
                message_cn="M06 评论下游信号抽取失败，请检查 M05 产物、评论信号 seed 或 M06 规则。",
                error_message=str(exc),
                partial_summary=_partial_summary(
                    batch_results,
                    sku_batch_size=normalized_sku_batch_size,
                    requested_sku_codes=requested_sku_codes,
                    signal_types=signal_types,
                ),
            )

        batch_result = _aggregate_batch_results(
            batch_results,
            batch_id=batch_id,
            seed_version=seed_version,
            rule_version=rule_version,
            requested_sku_codes=requested_sku_codes,
            signal_types=signal_types,
            sku_batch_size=normalized_sku_batch_size,
        )
        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M06_MODULE_VERSION,
            "seed_version": seed_version,
            "rule_version": rule_version,
            "target_sku_codes": requested_sku_codes,
            "signal_types": list(signal_types),
            **batch_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m06_comment_signal_summary_v1")
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M06,
            status=_status(batch_result),
            input_count=batch_result.input_count,
            changed_input_count=batch_result.created_output_count,
            output_count=batch_result.output_count,
            output_hash=output_hash,
            warnings=batch_result.warnings,
            review_issues=[_review_issue_schema(issue) for issue in batch_result.review_issues],
            downstream_impacts=[],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class CommentDownstreamSignalBatchService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M06_SEED_VERSION,
        rule_version: str = CORE3_M06_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        signal_types: Sequence[str] = (),
    ) -> CommentDownstreamSignalBatchResult:
        seed_result = CommentSignalSeedLoader().load()
        repository = CommentDownstreamSignalReadRepository(self.context)
        input_service = CommentSignalInputService(repository)
        bundles = input_service.list_sku_bundles(
            batch_id,
            sku_scope=target_sku_codes,
            seed_content_hash=seed_result.seed_content_hash,
            rule_version=rule_version,
        )
        service = CommentDownstreamSignalService(
            repository,
            seed=seed_result.seed,
        )
        sku_results = [
            service.process_bundle(
                bundle,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                asset_version=seed_result.asset_version or seed_version,
                signal_types=signal_types,
            )
            for bundle in bundles
        ]
        return _aggregate_results(
            sku_results,
            batch_id=batch_id,
            seed_version=seed_version,
            rule_version=rule_version,
            seed_content_hash=seed_result.seed_content_hash,
            target_sku_codes=target_sku_codes,
            signal_types=signal_types,
            seed_target_counts=seed_result.target_counts,
        )


def _resolve_sku_batches(
    context: Core3RepositoryContext,
    *,
    batch_id: str,
    requested_sku_codes: Sequence[str],
    sku_batch_size: int,
) -> list[tuple[str, ...]]:
    repository = CommentDownstreamSignalReadRepository(context)
    ready_sku_codes = repository.list_ready_sku_codes(batch_id, sku_scope=requested_sku_codes)
    if ready_sku_codes:
        return _chunk_sku_codes(ready_sku_codes, sku_batch_size)
    if requested_sku_codes:
        return [tuple(requested_sku_codes)]
    return [tuple()]


def _chunk_sku_codes(sku_codes: Sequence[str], sku_batch_size: int) -> list[tuple[str, ...]]:
    return [
        tuple(sku_codes[index : index + sku_batch_size])
        for index in range(0, len(sku_codes), sku_batch_size)
    ]


def _normalize_sku_codes(sku_codes: Sequence[str]) -> list[str]:
    return sorted({str(sku_code).strip() for sku_code in sku_codes if str(sku_code).strip()})


def _normalize_sku_batch_size(sku_batch_size: int) -> int:
    value = int(sku_batch_size)
    if value < 1:
        raise ValueError("sku_batch_size must be greater than or equal to 1")
    return min(value, 20)


def _aggregate_batch_results(
    batch_results: Sequence[CommentDownstreamSignalBatchResult],
    *,
    batch_id: str,
    seed_version: str,
    rule_version: str,
    requested_sku_codes: Sequence[str],
    signal_types: Sequence[str],
    sku_batch_size: int,
) -> CommentDownstreamSignalBatchResult:
    write_summary = _merge_write_summary([result.write_summary for result in batch_results])
    review_issues = [issue for result in batch_results for issue in result.review_issues]
    warnings = sorted({warning for result in batch_results for warning in result.warnings})
    sku_summaries = [
        sku_summary
        for result in batch_results
        for sku_summary in result.summary.get("sku_summaries", [])
    ]
    seed_content_hash = ""
    seed_target_counts: dict[str, int] = {}
    for result in batch_results:
        if not seed_content_hash:
            seed_content_hash = str(result.summary.get("seed_content_hash") or "")
        if not seed_target_counts:
            seed_target_counts = dict(result.summary.get("seed_target_counts") or {})

    summary = {
        "sku_count": sum(result.sku_count for result in batch_results),
        "ready_sku_count": sum(result.ready_sku_count for result in batch_results),
        "candidate_count": sum(result.candidate_count for result in batch_results),
        "downstream_signal_count": sum(result.downstream_signal_count for result in batch_results),
        "sku_profile_count": sum(result.sku_profile_count for result in batch_results),
        "review_required_count": sum(result.review_required_count for result in batch_results),
        "seed_content_hash": seed_content_hash,
        "seed_target_counts": seed_target_counts,
        "target_sku_codes": list(requested_sku_codes),
        "signal_types": list(signal_types),
        "sku_summaries": sku_summaries,
        "write_summary": write_summary,
        "execution_mode": "sku_batch",
        "sku_batch_size": sku_batch_size,
        "batch_count": len(batch_results),
        "batch_summaries": [
            {
                "batch_index": index,
                "target_sku_codes": list(result.summary.get("target_sku_codes") or []),
                "sku_count": result.sku_count,
                "input_count": result.input_count,
                "candidate_count": result.candidate_count,
                "downstream_signal_count": result.downstream_signal_count,
                "sku_profile_count": result.sku_profile_count,
                "review_required_count": result.review_required_count,
            }
            for index, result in enumerate(batch_results, start=1)
        ],
        "boundary_note": "M06 生成评论下游信号，供 M04b/M08/M09/M10/M11 等后续模块消费；不生成最终业务结论。",
    }
    return CommentDownstreamSignalBatchResult(
        input_count=sum(result.input_count for result in batch_results),
        sku_count=summary["sku_count"],
        candidate_count=summary["candidate_count"],
        downstream_signal_count=summary["downstream_signal_count"],
        sku_profile_count=summary["sku_profile_count"],
        ready_sku_count=summary["ready_sku_count"],
        review_required_count=summary["review_required_count"],
        warnings=warnings,
        review_issues=review_issues,
        write_summary=write_summary,
        summary=summary,
    )


def _aggregate_results(
    sku_results: Sequence[CommentDownstreamSignalServiceResult],
    *,
    batch_id: str,
    seed_version: str,
    rule_version: str,
    seed_content_hash: str,
    target_sku_codes: Sequence[str],
    signal_types: Sequence[str],
    seed_target_counts: dict[str, int],
) -> CommentDownstreamSignalBatchResult:
    write_summary = _merge_write_summary([result.write_summary for result in sku_results])
    review_issues = [issue for result in sku_results for issue in result.review_issues]
    warnings = sorted({warning for result in sku_results for warning in result.warnings})
    summary = {
        "sku_count": len(sku_results),
        "ready_sku_count": sum(1 for result in sku_results if result.profile.comment_signal_confidence > 0),
        "candidate_count": sum(len(result.candidates) for result in sku_results),
        "downstream_signal_count": sum(len(result.downstream_signals) for result in sku_results),
        "sku_profile_count": len(sku_results),
        "review_required_count": sum(1 for result in sku_results if result.profile.review_required),
        "seed_content_hash": seed_content_hash,
        "seed_target_counts": seed_target_counts,
        "target_sku_codes": list(target_sku_codes),
        "signal_types": list(signal_types),
        "sku_summaries": [result.summary for result in sku_results],
        "write_summary": write_summary,
        "boundary_note": "M06 生成评论下游信号，供 M04b/M08/M09/M10/M11 等后续模块消费；不生成最终业务结论。",
    }
    return CommentDownstreamSignalBatchResult(
        input_count=sum(result.input_count for result in sku_results),
        sku_count=len(sku_results),
        candidate_count=summary["candidate_count"],
        downstream_signal_count=summary["downstream_signal_count"],
        sku_profile_count=summary["sku_profile_count"],
        ready_sku_count=summary["ready_sku_count"],
        review_required_count=summary["review_required_count"],
        warnings=warnings,
        review_issues=review_issues,
        write_summary=write_summary,
        summary=summary,
    )


def _merge_write_summary(summaries: Sequence[dict[str, dict[str, int]]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for summary in summaries:
        for key, counts in summary.items():
            target = result.setdefault(key, {"created_count": 0, "reused_count": 0, "updated_count": 0})
            for count_key in target:
                target[count_key] += int(counts.get(count_key, 0))
    return result


def _status(batch_result: CommentDownstreamSignalBatchResult) -> Core3RunStatus:
    if batch_result.sku_count == 0:
        return Core3RunStatus.BLOCKED
    if batch_result.review_required_count or batch_result.warnings:
        return Core3RunStatus.WARNING
    return Core3RunStatus.SUCCESS


def _review_issue_schema(issue: CommentSignalReviewIssue) -> Core3ReviewIssueSchema:
    return Core3ReviewIssueSchema(
        issue_code=issue.issue_code,
        issue_type=str(issue.reason_code),
        severity=issue.severity,
        source_module=Core3ModuleCode.M06,
        object_type=issue.object_type,
        object_id=issue.object_id,
        target_sku_code=issue.sku_code,
        evidence_refs=issue.evidence_refs,
        message_cn=issue.message_cn,
        suggestion_cn=issue.suggestion_cn,
        review_required=issue.review_required,
        confidence=float(issue.confidence) if issue.confidence is not None else None,
    )


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
        module_code=Core3ModuleCode.M06,
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
    error_code: str,
    message_cn: str,
    error_message: str,
    partial_summary: dict[str, Any] | None = None,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M06,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=[message_cn, error_message],
        review_issues=[
            Core3ReviewIssueSchema(
                issue_code=error_code,
                issue_type="module_failed",
                severity="blocker",
                source_module=Core3ModuleCode.M06,
                object_type="module",
                target_sku_code=None,
                evidence_refs=[],
                message_cn=message_cn,
                suggestion_cn="检查 M05 当前产物、M06 seed 和本地 fixture 后重跑。",
                review_required=True,
            )
        ],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error_code": error_code,
            "error_message": error_message,
            **(partial_summary or {}),
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _partial_summary(
    batch_results: Sequence[CommentDownstreamSignalBatchResult],
    *,
    sku_batch_size: int,
    requested_sku_codes: Sequence[str],
    signal_types: Sequence[str],
) -> dict[str, Any]:
    if not batch_results:
        return {
            "execution_mode": "sku_batch",
            "sku_batch_size": sku_batch_size,
            "target_sku_codes": list(requested_sku_codes),
            "signal_types": list(signal_types),
            "completed_batch_count": 0,
            "partial_output_count": 0,
        }
    return {
        "execution_mode": "sku_batch",
        "sku_batch_size": sku_batch_size,
        "target_sku_codes": list(requested_sku_codes),
        "signal_types": list(signal_types),
        "completed_batch_count": len(batch_results),
        "partial_input_count": sum(result.input_count for result in batch_results),
        "partial_output_count": sum(result.output_count for result in batch_results),
        "partial_sku_count": sum(result.sku_count for result in batch_results),
    }
