"""M01 cleaning-quality runner orchestration."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Core3CleanSku
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_quality_service import (
    AttributeCleaner,
    ClaimCleaner,
    CleaningSourceContext,
    CleanSkuBuilder,
    CommentCleaner,
    MarketCleaner,
    QualityIssueBuilder,
)
from app.services.core3_real_data.cleaning_repositories import (
    CleanAttributeRepository,
    CleanClaimRepository,
    CleanCommentRepository,
    CleanHashConflictError,
    CleaningQueryRepository,
    CleanMarketRepository,
    CleanSkuRepository,
    DataQualityIssueRepository,
    SourceBatchReader,
    SourceRowRegistryReader,
)
from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    CORE3_M01_MODULE_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3QualityIssueSeverity,
    Core3QualityIssueType,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceOperationType,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.runner import Core3ModuleTarget
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.source_registry_repositories import RawSourceRepository


class CleaningQualityRunner:
    module_code = Core3ModuleCode.M01

    def __init__(
        self,
        db: Session,
        *,
        market_cleaner: MarketCleaner | None = None,
        attribute_cleaner: AttributeCleaner | None = None,
        claim_cleaner: ClaimCleaner | None = None,
        comment_cleaner: CommentCleaner | None = None,
        sku_builder: CleanSkuBuilder | None = None,
        quality_issue_builder: QualityIssueBuilder | None = None,
    ) -> None:
        self.db = db
        self.market_cleaner = market_cleaner or MarketCleaner()
        self.attribute_cleaner = attribute_cleaner or AttributeCleaner()
        self.claim_cleaner = claim_cleaner or ClaimCleaner()
        self.comment_cleaner = comment_cleaner or CommentCleaner()
        self.sku_builder = sku_builder or CleanSkuBuilder()
        self.quality_issue_builder = quality_issue_builder or QualityIssueBuilder()

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(context, "M01 缺少 M00 batch_id，无法确定清洗范围。")

        module_run_id = target.metadata.get("module_run_id")
        include_no_change = bool(target.metadata.get("include_no_change", False))
        skip_completed_skus = bool(target.metadata.get("skip_completed_skus", False))
        clean_version = str(target.metadata.get("clean_version") or CORE3_M01_CLEAN_VERSION)
        hash_version = str(target.metadata.get("hash_version") or CORE3_M01_CLEAN_HASH_VERSION)
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=module_run_id,
            clean_version=clean_version,
            hash_version=hash_version,
            include_no_change=include_no_change,
            skip_completed_skus=skip_completed_skus,
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
        clean_version: str = CORE3_M01_CLEAN_VERSION,
        hash_version: str = CORE3_M01_CLEAN_HASH_VERSION,
        include_no_change: bool = False,
        skip_completed_skus: bool = False,
        target_sku_codes: tuple[str, ...] = (),
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(
            db=self.db,
            project_id=project_id,
            category_code=category_code,
        )
        source_batch_reader = SourceBatchReader(repository_context)
        source_row_reader = SourceRowRegistryReader(repository_context)
        raw_source_repository = RawSourceRepository(repository_context)

        try:
            source_batch_reader.get_consumable_batch(batch_id)
        except ValueError as exc:
            return _blocked_result(
                _minimal_context(project_id=project_id, category_code=category_code, run_id=run_id),
                str(exc),
                batch_id=batch_id,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        processable_rows = source_row_reader.list_processable_rows(
            batch_id,
            include_no_change=include_no_change,
            target_sku_codes=target_sku_codes,
        )
        registered_input_count = len(processable_rows)
        skipped_completed_sku_codes: set[str] = set()
        skipped_completed_input_row_count = 0
        if skip_completed_skus:
            skipped_completed_sku_codes = _completed_clean_sku_codes(
                repository_context,
                batch_id=batch_id,
                target_sku_codes=target_sku_codes,
            )
            if skipped_completed_sku_codes:
                rows_before_skip = len(processable_rows)
                processable_rows = [
                    row
                    for row in processable_rows
                    if row.sku_code_candidate not in skipped_completed_sku_codes
                ]
                skipped_completed_input_row_count = rows_before_skip - len(processable_rows)

        raw_rows_by_source_ref = _load_raw_rows_by_source_ref(
            raw_source_repository,
            processable_rows,
        )

        markets: list[dict[str, Any]] = []
        attributes: list[dict[str, Any]] = []
        claims: list[dict[str, Any]] = []
        claim_sentences: list[dict[str, Any]] = []
        comments: list[dict[str, Any]] = []
        comment_sentences: list[dict[str, Any]] = []
        comment_dimensions: list[dict[str, Any]] = []
        row_quality_issues: list[dict[str, Any]] = []

        try:
            with self.db.begin_nested():
                for source_row in processable_rows:
                    if source_row.operation_type == Core3SourceOperationType.SKIPPED.value:
                        row_quality_issues.append(
                            _source_row_issue(
                                source_row,
                                project_id=project_id,
                                category_code=category_code,
                                batch_id=batch_id,
                                run_id=run_id,
                                module_run_id=module_run_id,
                                issue_detail="M00 标记该来源行为 skipped，M01 不生成业务清洗事实。",
                            )
                        )
                        continue
                    if source_row.operation_type == Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN.value:
                        row_quality_issues.append(
                            _source_row_issue(
                                source_row,
                                project_id=project_id,
                                category_code=category_code,
                                batch_id=batch_id,
                                run_id=run_id,
                                module_run_id=module_run_id,
                                issue_detail="M00 标记该来源行本次扫描未见，M01 不生成业务清洗事实。",
                            )
                        )
                        continue
                    if not source_row.source_pk or not source_row.source_row_id:
                        row_quality_issues.append(
                            _source_row_issue(
                                source_row,
                                project_id=project_id,
                                category_code=category_code,
                                batch_id=batch_id,
                                run_id=run_id,
                                module_run_id=module_run_id,
                                issue_detail="来源行缺少 source_pk 或 source_row_id，无法回读原始表。",
                            )
                        )
                        continue

                    raw_row = raw_rows_by_source_ref.get((source_row.source_table, str(source_row.source_pk)))
                    if raw_row is None:
                        row_quality_issues.append(
                            _source_row_issue(
                                source_row,
                                project_id=project_id,
                                category_code=category_code,
                                batch_id=batch_id,
                                run_id=run_id,
                                module_run_id=module_run_id,
                                issue_detail="M00 登记的来源行无法从原始表回读，M01 不生成业务清洗事实。",
                            )
                        )
                        continue

                    source_context = CleaningSourceContext(
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        source_table=source_row.source_table,
                        source_pk=source_row.source_pk,
                        source_row_id=source_row.source_row_id,
                        source_row_hash=source_row.row_hash,
                        source_operation_type=source_row.operation_type,
                        clean_version=clean_version,
                        hash_version=hash_version,
                    )
                    cleaned = self._clean_source_row(raw_row, source_context)
                    markets.extend(cleaned["markets"])
                    attributes.extend(cleaned["attributes"])
                    claims.extend(cleaned["claims"])
                    claim_sentences.extend(cleaned["claim_sentences"])
                    comments.extend(cleaned["comments"])
                    comment_sentences.extend(cleaned["comment_sentences"])
                    comment_dimensions.extend(cleaned["comment_dimensions"])

                clean_skus = self.sku_builder.build(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    clean_version=clean_version,
                    hash_version=hash_version,
                    markets=markets,
                    attributes=attributes,
                    claims=claims,
                    comments=comments,
                ).skus
                quality_issues = self.quality_issue_builder.build(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    clean_skus=clean_skus,
                    markets=markets,
                    attributes=attributes,
                    claims=claims,
                    comments=comments,
                    comment_dimensions=comment_dimensions,
                ).issues
                quality_issues.extend(row_quality_issues)

                self._write_outputs(
                    repository_context,
                    clean_skus=clean_skus,
                    markets=markets,
                    attributes=attributes,
                    claims=claims,
                    claim_sentences=claim_sentences,
                    comments=comments,
                    comment_sentences=comment_sentences,
                    comment_dimensions=comment_dimensions,
                    quality_issues=quality_issues,
                )
        except CleanHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_message=str(exc),
            )

        summary = CleaningQueryRepository(repository_context).get_clean_summary(batch_id)
        clean_counts = dict(summary["clean_counts"])
        issue_counts = dict(summary["issue_counts"])
        warnings = sorted(issue_counts.get("by_type", {}).keys())
        status = Core3RunStatus.WARNING if warnings or summary["review_required"] else Core3RunStatus.SUCCESS
        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M01_MODULE_VERSION,
            "clean_version": clean_version,
            "hash_version": hash_version,
            "include_no_change": include_no_change,
            "skip_completed_skus": skip_completed_skus,
            "registered_input_row_count": registered_input_count,
            "skipped_completed_sku_codes": sorted(skipped_completed_sku_codes),
            "skipped_completed_input_row_count": skipped_completed_input_row_count,
            "clean_counts": clean_counts,
            "issue_counts": issue_counts,
            "review_required": summary["review_required"],
            "input_row_count": len(processable_rows),
            "target_sku_codes": list(target_sku_codes),
        }
        output_hash = stable_hash(summary_json, version="m01_cleaning_summary_v1")
        finished_at = datetime.now(timezone.utc)
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M01,
            status=status,
            input_count=len(processable_rows),
            changed_input_count=len(processable_rows),
            output_count=sum(clean_counts.values()),
            output_hash=output_hash,
            warnings=warnings,
            review_issues=[],
            downstream_impacts=_downstream_impacts(clean_counts),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _clean_source_row(
        self,
        raw_row: Mapping[str, Any],
        context: CleaningSourceContext,
    ) -> dict[str, list[dict[str, Any]]]:
        result = {
            "markets": [],
            "attributes": [],
            "claims": [],
            "claim_sentences": [],
            "comments": [],
            "comment_sentences": [],
            "comment_dimensions": [],
        }
        if context.source_table == "week_sales_data":
            result["markets"].append(self.market_cleaner.clean(raw_row, context).market)
        elif context.source_table == "attribute_data":
            result["attributes"].append(self.attribute_cleaner.clean(raw_row, context).attribute)
        elif context.source_table == "selling_points_data":
            claim_result = self.claim_cleaner.clean(raw_row, context)
            if claim_result.claim is not None:
                result["claims"].append(claim_result.claim)
                result["claim_sentences"].extend(claim_result.sentences)
        elif context.source_table == "comment_data":
            comment_result = self.comment_cleaner.clean(raw_row, context)
            result["comments"].append(comment_result.comment)
            result["comment_sentences"].extend(comment_result.sentences)
            if comment_result.dimension is not None:
                result["comment_dimensions"].append(comment_result.dimension)
        else:
            raise ValueError(f"unknown source_table for M01 cleaning: {context.source_table}")
        return result

    def _write_outputs(
        self,
        repository_context: Core3RepositoryContext,
        *,
        clean_skus: list[Mapping[str, Any]],
        markets: list[Mapping[str, Any]],
        attributes: list[Mapping[str, Any]],
        claims: list[Mapping[str, Any]],
        claim_sentences: list[Mapping[str, Any]],
        comments: list[Mapping[str, Any]],
        comment_sentences: list[Mapping[str, Any]],
        comment_dimensions: list[Mapping[str, Any]],
        quality_issues: list[Mapping[str, Any]],
    ) -> None:
        sku_repository = CleanSkuRepository(repository_context)
        market_repository = CleanMarketRepository(repository_context)
        attribute_repository = CleanAttributeRepository(repository_context)
        claim_repository = CleanClaimRepository(repository_context)
        comment_repository = CleanCommentRepository(repository_context)
        issue_repository = DataQualityIssueRepository(repository_context)

        market_repository.save_markets(markets)
        attribute_repository.save_attributes(attributes)

        claim_ids_by_source_row = _ids_by_source_row(claim_repository.save_claims(claims))
        claim_sentence_payloads: list[Mapping[str, Any]] = []
        for payload in claim_sentences:
            clean_claim_id = claim_ids_by_source_row.get(str(payload.get("source_row_id")))
            if clean_claim_id:
                claim_sentence_payloads.append({**dict(payload), "clean_claim_id": clean_claim_id})
        claim_repository.save_claim_sentences(claim_sentence_payloads)

        comment_ids_by_source_row = _ids_by_source_row(comment_repository.save_comments(comments))
        comment_sentence_payloads: list[Mapping[str, Any]] = []
        for payload in comment_sentences:
            clean_comment_id = comment_ids_by_source_row.get(str(payload.get("source_row_id")))
            if clean_comment_id:
                comment_sentence_payloads.append({**dict(payload), "clean_comment_id": clean_comment_id})
        comment_repository.save_comment_sentences(comment_sentence_payloads)
        comment_dimension_payloads: list[Mapping[str, Any]] = []
        for payload in comment_dimensions:
            clean_comment_id = comment_ids_by_source_row.get(str(payload.get("source_row_id")))
            if clean_comment_id:
                comment_dimension_payloads.append({**dict(payload), "clean_comment_id": clean_comment_id})
        comment_repository.save_comment_dimensions(comment_dimension_payloads)

        sku_repository.save_skus(clean_skus)
        issue_repository.save_issues(quality_issues)


def _source_row_issue(
    source_row: Any,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    issue_detail: str,
) -> dict[str, Any]:
    source_row_id = source_row.source_row_id or source_row.row_registry_id
    return {
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "run_id": run_id,
        "module_run_id": module_run_id,
        "module_code": Core3ModuleCode.M01.value,
        "domain": Core3DataDomain.QUALITY.value,
        "source_table": source_row.source_table,
        "source_row_id": source_row.source_row_id,
        "clean_table": None,
        "clean_record_key": f"source_row:{source_row_id}",
        "sku_code": source_row.sku_code_candidate,
        "issue_type": Core3QualityIssueType.MISSING_REQUIRED_FIELD.value,
        "severity": Core3QualityIssueSeverity.WARNING.value,
        "issue_detail": issue_detail,
        "issue_payload_json": {
            "source_pk": source_row.source_pk,
            "source_row_id": source_row.source_row_id,
            "operation_type": source_row.operation_type,
            "quality_hint": source_row.quality_hint or {},
        },
        "suggested_downstream_action": "下游模块不得把该来源行解释为业务事实，只能作为数据质量提示。",
        "review_required": True,
        "review_status": Core3ReviewStatus.REVIEW_REQUIRED.value,
    }


def _ids_by_source_row(result: Any) -> dict[str, str]:
    ids_by_source_row: dict[str, str] = {}
    for key, record_id in result.ids_by_key.items():
        if len(key) < 2 or key[1] is None:
            continue
        ids_by_source_row[str(key[1])] = record_id
    return ids_by_source_row


def _load_raw_rows_by_source_ref(
    raw_source_repository: RawSourceRepository,
    processable_rows: Sequence[Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    source_pks_by_table: dict[str, list[str]] = {}
    for source_row in processable_rows:
        if not source_row.source_table or source_row.source_pk in (None, ""):
            continue
        source_pks_by_table.setdefault(source_row.source_table, []).append(str(source_row.source_pk))

    rows_by_source_ref: dict[tuple[str, str], dict[str, Any]] = {}
    for source_table, source_pks in source_pks_by_table.items():
        for source_pk, raw_row in raw_source_repository.get_rows_by_source_refs(source_table, source_pks).items():
            rows_by_source_ref[(source_table, source_pk)] = raw_row
    return rows_by_source_ref


def _completed_clean_sku_codes(
    repository_context: Core3RepositoryContext,
    *,
    batch_id: str,
    target_sku_codes: Sequence[str],
) -> set[str]:
    stmt = (
        select(Core3CleanSku.sku_code)
        .where(Core3CleanSku.project_id == repository_context.project_id)
        .where(Core3CleanSku.category_code == repository_context.category_code.value)
        .where(Core3CleanSku.batch_id == batch_id)
    )
    normalized_target_skus = tuple(
        dict.fromkeys(str(sku_code).strip() for sku_code in target_sku_codes if str(sku_code).strip())
    )
    if normalized_target_skus:
        stmt = stmt.where(Core3CleanSku.sku_code.in_(normalized_target_skus))
    return {str(sku_code) for sku_code in repository_context.db.execute(stmt).scalars() if sku_code}


def _downstream_impacts(clean_counts: Mapping[str, int]) -> list[dict[str, Any]]:
    if not any(clean_counts.values()):
        return []
    return [
        {
            "module_code": Core3ModuleCode.M02.value,
            "reason_cn": "M01 已生成或复用清洗事实，M02 可基于清洗层构建 evidence 原子。",
        }
    ]


def _blocked_result(
    context: Core3RunContext,
    message: str,
    *,
    batch_id: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M01,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=["m00_batch_not_consumable"],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "batch_id": batch_id or context.batch_id,
            "message_cn": message,
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
    summary_json = {
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "run_id": run_id,
        "error_code": "m01_clean_hash_conflict",
        "message_cn": "同 batch 已存在不同 clean_hash，M01 停止写入以避免静默覆盖。",
        "error_message": error_message,
    }
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M01,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m01_cleaning_failed_v1"),
        warnings=["clean_hash_conflict"],
        review_issues=[],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _minimal_context(*, project_id: str, category_code: str, run_id: str | None) -> Core3RunContext:
    from app.schemas.core3_real_data import Core3TargetScopeSchema
    from app.services.core3_real_data.constants import Core3RunMode, Core3TargetScopeType

    return Core3RunContext(
        run_id=run_id or "m01-blocked",
        project_id=project_id,
        category_code=category_code,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )
