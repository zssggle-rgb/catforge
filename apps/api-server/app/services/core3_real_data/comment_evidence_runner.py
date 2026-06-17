"""M05 comment evidence runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.comment_evidence_input_service import (
    CommentEvidenceInputRepository,
    CommentEvidenceInputService,
    M05InputBlockedError,
)
from app.services.core3_real_data.comment_evidence_repositories import CommentEvidenceReadRepository
from app.services.core3_real_data.comment_evidence_schemas import M05DownstreamImpact, M05ReviewIssue
from app.services.core3_real_data.comment_evidence_service import (
    CommentEvidenceService,
    CommentEvidenceServiceResult,
)
from app.services.core3_real_data.comment_topic_seed_loader import (
    CommentTopicSeedLoader,
    CommentTopicSeedValidationError,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_MODULE_VERSION,
    CORE3_M05_RULE_VERSION,
    CORE3_M05_SEED_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


@dataclass(frozen=True)
class CommentEvidenceBatchServiceResult:
    input_count: int
    sku_count: int
    comment_unit_count: int
    unit_link_count: int
    evidence_atom_count: int
    topic_hint_count: int
    quality_profile_count: int
    usable_sentence_count: int
    downstream_ready_sku_count: int
    review_required_count: int
    warnings: list[str]
    review_issues: list[M05ReviewIssue]
    downstream_impacts: list[M05DownstreamImpact]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item.get("created_count", 0) for item in self.write_summary.values())

    @property
    def reused_output_count(self) -> int:
        return sum(item.get("reused_count", 0) for item in self.write_summary.values())

    @property
    def updated_output_count(self) -> int:
        return sum(item.get("updated_count", 0) for item in self.write_summary.values())

    @property
    def output_count(self) -> int:
        return (
            self.comment_unit_count
            + self.unit_link_count
            + self.evidence_atom_count
            + self.topic_hint_count
            + self.quality_profile_count
        )


class CommentEvidenceRunner:
    module_code = Core3ModuleCode.M05

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
                message_cn="M05 缺少 M00 batch_id，无法确定评论证据抽取范围。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )

        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            seed_version=str(target.metadata.get("seed_version") or CORE3_M05_SEED_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M05_RULE_VERSION),
            target_sku_codes=target.target_ids,
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M05_SEED_VERSION,
        rule_version: str = CORE3_M05_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(
            db=self.db,
            project_id=project_id,
            category_code=category_code,
        )
        try:
            SourceBatchReader(repository_context).get_consumable_batch(batch_id)
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
                service_result = CommentEvidenceBatchService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    seed_version=seed_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                )
        except (M05InputBlockedError, CommentTopicSeedValidationError, ValueError) as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m05_comment_evidence_failed",
                message_cn="M05 评论证据抽取失败，请检查 M02 evidence、评论主题 seed 或 M05 评论证据规则。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M05_MODULE_VERSION,
            "seed_version": seed_version,
            "rule_version": rule_version,
            "target_sku_codes": list(target_sku_codes),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m05_comment_evidence_summary_v1")
        status = _status(service_result)
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M05,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.output_count,
            output_hash=output_hash,
            warnings=service_result.warnings,
            review_issues=[_review_issue_schema(issue) for issue in service_result.review_issues],
            downstream_impacts=[_downstream_impact_payload(impact) for impact in service_result.downstream_impacts],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class CommentEvidenceBatchService:
    """Build M05 outputs from current M02 comment evidence and write them."""

    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M05_SEED_VERSION,
        rule_version: str = CORE3_M05_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
    ) -> CommentEvidenceBatchServiceResult:
        seed_result = CommentTopicSeedLoader().load()
        input_service = CommentEvidenceInputService(CommentEvidenceInputRepository(self.context))
        bundle_results = input_service.list_sku_bundles(
            batch_id,
            sku_scope=target_sku_codes,
            seed_content_hash=seed_result.seed_content_hash,
            rule_version=rule_version,
        )
        m05_service = CommentEvidenceService(
            CommentEvidenceReadRepository(self.context),
            topic_seed=seed_result.seed,
        )
        sku_results = [
            m05_service.process_bundle(
                bundle_result.bundle,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                asset_version=seed_result.asset_version or seed_version,
            )
            for bundle_result in bundle_results
        ]
        return _aggregate_results(
            sku_results,
            batch_id=batch_id,
            seed_version=seed_version,
            rule_version=rule_version,
            seed_content_hash=seed_result.seed_content_hash,
            target_sku_codes=target_sku_codes,
        )


def _aggregate_results(
    sku_results: Sequence[CommentEvidenceServiceResult],
    *,
    batch_id: str,
    seed_version: str,
    rule_version: str,
    seed_content_hash: str,
    target_sku_codes: Sequence[str],
) -> CommentEvidenceBatchServiceResult:
    write_summary = _aggregate_write_summary(result.write_summary for result in sku_results)
    review_issues = [issue for result in sku_results for issue in result.review_issues]
    downstream_impacts = _dedupe_downstream_impacts(
        impact for result in sku_results for impact in result.downstream_impacts
    )
    warnings = _warnings(sku_results, bool(target_sku_codes))
    summary = {
        "batch_id": batch_id,
        "seed_version": seed_version,
        "rule_version": rule_version,
        "seed_content_hash": seed_content_hash,
        "target_sku_codes": list(target_sku_codes),
        "sku_count": len(sku_results),
        "input_evidence_count": sum(result.input_count for result in sku_results),
        "comment_unit_count": sum(len(result.comment_units) for result in sku_results),
        "unit_link_count": sum(len(result.unit_links) for result in sku_results),
        "evidence_atom_count": sum(len(result.sentence_atoms) for result in sku_results),
        "topic_hint_count": sum(len(result.topic_hints) for result in sku_results),
        "quality_profile_count": len(sku_results),
        "usable_sentence_count": sum(result.quality_profile.usable_sentence_count for result in sku_results),
        "downstream_ready_sku_count": sum(1 for result in sku_results if result.quality_profile.downstream_ready),
        "review_required_count": sum(1 for result in sku_results if result.review_required),
        "blocked_sku_count": sum(1 for result in sku_results if result.blocked),
        "review_issue_count": len(review_issues),
        "write_summary": write_summary,
        "sku_summaries": [_sku_summary(result) for result in sku_results],
        "by_sample_status": _count_by(_enum_value(result.quality_profile.sample_status) for result in sku_results),
        "by_warning": _count_by(warning for result in sku_results for warning in result.warnings),
    }
    return CommentEvidenceBatchServiceResult(
        input_count=summary["input_evidence_count"],
        sku_count=summary["sku_count"],
        comment_unit_count=summary["comment_unit_count"],
        unit_link_count=summary["unit_link_count"],
        evidence_atom_count=summary["evidence_atom_count"],
        topic_hint_count=summary["topic_hint_count"],
        quality_profile_count=summary["quality_profile_count"],
        usable_sentence_count=summary["usable_sentence_count"],
        downstream_ready_sku_count=summary["downstream_ready_sku_count"],
        review_required_count=summary["review_required_count"],
        warnings=warnings,
        review_issues=review_issues,
        downstream_impacts=downstream_impacts,
        write_summary=write_summary,
        summary=summary,
    )


def _aggregate_write_summary(summaries: Sequence[dict[str, dict[str, int]]]) -> dict[str, dict[str, int]]:
    aggregate: dict[str, dict[str, int]] = {}
    for summary in summaries:
        for name, counts in summary.items():
            bucket = aggregate.setdefault(name, {})
            for key, value in counts.items():
                bucket[key] = bucket.get(key, 0) + int(value)
    return dict(sorted(aggregate.items()))


def _warnings(sku_results: Sequence[CommentEvidenceServiceResult], targeted_run: bool) -> list[str]:
    warnings: list[str] = []
    if not sku_results:
        warnings.append("m05_empty_comment_evidence")
        if targeted_run:
            warnings.append("m05_target_sku_has_no_comment_evidence")
    if any(result.blocked for result in sku_results):
        warnings.append("m05_comment_evidence_blocked")
    if any(result.review_required for result in sku_results):
        warnings.append("m05_comment_evidence_review_required")
    for result in sku_results:
        warnings.extend(result.warnings)
    return _unique_values(warnings)


def _status(result: CommentEvidenceBatchServiceResult) -> Core3RunStatus:
    if result.sku_count == 0:
        return Core3RunStatus.WARNING
    if result.downstream_ready_sku_count == 0:
        return Core3RunStatus.REVIEW_REQUIRED
    if result.warnings or result.review_required_count > 0:
        return Core3RunStatus.WARNING
    return Core3RunStatus.SUCCESS


def _sku_summary(result: CommentEvidenceServiceResult) -> dict[str, Any]:
    profile = result.quality_profile
    return {
        "sku_code": result.bundle.sku_code,
        "model_name": result.bundle.model_name,
        "brand_name": result.bundle.brand_name,
        "input_evidence_count": result.input_count,
        "comment_unit_count": len(result.comment_units),
        "evidence_atom_count": len(result.sentence_atoms),
        "topic_hint_count": len(result.topic_hints),
        "usable_sentence_count": profile.usable_sentence_count,
        "sample_status": _enum_value(profile.sample_status),
        "downstream_ready": profile.downstream_ready,
        "review_required": result.review_required,
        "blocked": result.blocked,
        "warning_count": len(result.warnings),
    }


def _review_issue_schema(issue: M05ReviewIssue) -> Core3ReviewIssueSchema:
    return Core3ReviewIssueSchema(
        issue_code=issue.issue_code,
        issue_type=_enum_value(issue.reason_code),
        severity=issue.severity,
        source_module=Core3ModuleCode.M05,
        object_type=issue.object_type,
        object_id=issue.object_id,
        target_sku_code=issue.sku_code,
        candidate_sku_code=None,
        evidence_refs=list(issue.evidence_refs),
        message_cn=issue.message_cn,
        suggestion_cn=issue.suggestion_cn,
        review_required=issue.review_required,
        confidence=float(issue.confidence) if issue.confidence is not None else None,
    )


def _downstream_impact_payload(impact: M05DownstreamImpact) -> dict[str, Any]:
    return {
        "module_code": _enum_value(impact.target_module),
        "sku_code": impact.sku_code,
        "impact_level": _enum_value(impact.impact_level),
        "changed_object_count": impact.changed_object_count,
        "reason_cn": impact.reason_cn,
        "evidence_refs": list(impact.evidence_refs),
    }


def _dedupe_downstream_impacts(impacts: Sequence[M05DownstreamImpact] | Any) -> list[M05DownstreamImpact]:
    result: list[M05DownstreamImpact] = []
    seen: set[tuple[str, str | None, str]] = set()
    for impact in impacts:
        key = (
            _enum_value(impact.target_module),
            impact.sku_code,
            _enum_value(impact.impact_level),
        )
        if key in seen:
            continue
        result.append(impact)
        seen.add(key)
    return result


def _count_by(values: Sequence[str] | Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


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
        module_code=Core3ModuleCode.M05,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=["m05_batch_not_consumable"],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "message_cn": message_cn,
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
) -> Core3ModuleRunResultSchema:
    summary_json = {
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "run_id": run_id,
        "error_code": error_code,
        "message_cn": message_cn,
        "error_message": error_message,
    }
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M05,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m05_comment_evidence_failed_v1"),
        warnings=[error_code],
        review_issues=[],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _unique_values(values: Sequence[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))
