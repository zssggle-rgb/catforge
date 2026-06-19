"""M01 cleaning-quality runner orchestration."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_quality_service import (
    AttributeCleaner,
    ClaimCleaner,
    CleaningSourceContext,
    CleanSkuBuilder,
    CommentCleaner,
    build_market_batch_scope,
    MarketCleaner,
    QualityIssueBuilder,
)
from app.services.core3_real_data.cleaning_normalizers import PeriodParser, TextNormalizer
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


M01_DEFAULT_SOURCE_ROW_CHUNK_SIZE = 1_000


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
        source_row_chunk_size: int = M01_DEFAULT_SOURCE_ROW_CHUNK_SIZE,
        commit_each_chunk: bool = True,
    ) -> None:
        self.db = db
        self.market_cleaner = market_cleaner or MarketCleaner()
        self.attribute_cleaner = attribute_cleaner or AttributeCleaner()
        self.claim_cleaner = claim_cleaner or ClaimCleaner()
        self.comment_cleaner = comment_cleaner or CommentCleaner()
        self.sku_builder = sku_builder or CleanSkuBuilder()
        self.quality_issue_builder = quality_issue_builder or QualityIssueBuilder()
        self.source_row_chunk_size = max(int(source_row_chunk_size), 1)
        self.commit_each_chunk = commit_each_chunk

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(context, "M01 缺少 M00 batch_id，无法确定清洗范围。")

        module_run_id = target.metadata.get("module_run_id")
        include_no_change = bool(target.metadata.get("include_no_change", False))
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

        input_row_count = source_row_reader.count_processable_rows(
            batch_id,
            include_no_change=include_no_change,
            sku_codes=target_sku_codes or None,
        )
        batch_market_scope = (
            self._build_batch_market_scope(
                source_row_reader=source_row_reader,
                raw_source_repository=raw_source_repository,
                batch_id=batch_id,
                include_no_change=include_no_change,
            )
            if target_sku_codes
            else None
        )

        accumulator = _CleaningRunAccumulator()
        processed_chunk_count = 0

        try:
            for source_rows in source_row_reader.iter_processable_row_chunks(
                batch_id,
                chunk_size=self.source_row_chunk_size,
                include_no_change=include_no_change,
                sku_codes=target_sku_codes or None,
            ):
                processed_chunk_count += 1
                chunk_outputs = _empty_clean_outputs()
                raw_rows_by_ref = self._load_raw_rows_by_source_ref(
                    raw_source_repository=raw_source_repository,
                    source_rows=source_rows,
                )
                for source_row in source_rows:
                    accumulator.input_count += 1
                    if source_row.operation_type == Core3SourceOperationType.SKIPPED.value:
                        chunk_outputs["quality_issues"].append(
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
                        chunk_outputs["quality_issues"].append(
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
                        chunk_outputs["quality_issues"].append(
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

                    raw_row = raw_rows_by_ref.get((source_row.source_table, source_row.source_pk))
                    if raw_row is None:
                        chunk_outputs["quality_issues"].append(
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
                    _extend_clean_outputs(chunk_outputs, cleaned)
                    accumulator.add_cleaned(cleaned)

                self._write_outputs(
                    repository_context,
                    clean_skus=[],
                    markets=chunk_outputs["markets"],
                    attributes=chunk_outputs["attributes"],
                    claims=chunk_outputs["claims"],
                    claim_sentences=chunk_outputs["claim_sentences"],
                    comments=chunk_outputs["comments"],
                    comment_sentences=chunk_outputs["comment_sentences"],
                    comment_dimensions=chunk_outputs["comment_dimensions"],
                    quality_issues=chunk_outputs["quality_issues"],
                )
                self.db.flush()
                if self.commit_each_chunk:
                    self.db.commit()
                self.db.expunge_all()

            clean_skus = self.sku_builder.build(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                clean_version=clean_version,
                hash_version=hash_version,
                markets=accumulator.markets,
                attributes=accumulator.attributes,
                claims=accumulator.claims,
                comments=accumulator.comment_representatives(),
                comment_dimensions=[],
                comment_summaries=accumulator.comment_summaries(),
                market_scope=batch_market_scope or build_market_batch_scope(accumulator.markets),
            ).skus
            quality_issues = self.quality_issue_builder.build(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                clean_skus=clean_skus,
                markets=accumulator.markets,
                attributes=accumulator.attributes,
                claims=accumulator.claims,
                comments=[],
                comment_dimensions=[],
                include_comment_row_issues=False,
            ).issues

            self._write_outputs(
                repository_context,
                clean_skus=clean_skus,
                markets=[],
                attributes=[],
                claims=[],
                claim_sentences=[],
                comments=[],
                comment_sentences=[],
                comment_dimensions=[],
                quality_issues=quality_issues,
            )
            self.db.flush()
            if self.commit_each_chunk:
                self.db.commit()
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
        preliminary_summary = dict(summary.get("preliminary_summary") or {})
        warnings = sorted(issue_counts.get("by_type", {}).keys())
        status = Core3RunStatus.WARNING if warnings or summary["review_required"] else Core3RunStatus.SUCCESS
        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M01_MODULE_VERSION,
            "clean_version": clean_version,
            "hash_version": hash_version,
            "include_no_change": include_no_change,
            "clean_counts": clean_counts,
            "issue_counts": issue_counts,
            "review_required": summary["review_required"],
            "input_row_count": input_row_count,
            "processed_row_count": accumulator.input_count,
            "processed_chunk_count": processed_chunk_count,
            "source_row_chunk_size": self.source_row_chunk_size,
            "target_sku_codes": list(target_sku_codes),
            "market_coverage_summary": preliminary_summary.get("market_coverage_summary", {}),
            "comment_preliminary_summary": preliminary_summary.get("comment_preliminary_summary", {}),
        }
        output_hash = stable_hash(summary_json, version="m01_cleaning_summary_v1")
        finished_at = datetime.now(timezone.utc)
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M01,
            status=status,
            input_count=input_row_count,
            changed_input_count=input_row_count,
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

    def _load_raw_rows_by_source_ref(
        self,
        *,
        raw_source_repository: RawSourceRepository,
        source_rows: list[Any],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        source_pks_by_table: dict[str, list[str]] = {}
        for source_row in source_rows:
            if not source_row.source_pk:
                continue
            source_pks_by_table.setdefault(source_row.source_table, []).append(str(source_row.source_pk))

        raw_rows_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
        for source_table, source_pks in source_pks_by_table.items():
            for source_pk, raw_row in raw_source_repository.get_rows_by_source_refs(
                source_table,
                source_pks,
            ).items():
                raw_rows_by_ref[(source_table, source_pk)] = raw_row
        return raw_rows_by_ref

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

        for payload in markets:
            market_repository.save_market(payload, flush=False)
        for payload in attributes:
            attribute_repository.save_attribute(payload, flush=False)

        claim_records_by_source_row: dict[str, Any] = {}
        for payload in claims:
            saved = claim_repository.save_claim(payload, flush=False)
            claim_records_by_source_row[payload["source_row_id"]] = saved.record
        if claim_records_by_source_row:
            self.db.flush()
        claim_ids_by_source_row = {
            source_row_id: record.clean_claim_id
            for source_row_id, record in claim_records_by_source_row.items()
        }
        for payload in claim_sentences:
            clean_claim_id = claim_ids_by_source_row.get(str(payload.get("source_row_id")))
            if clean_claim_id:
                claim_repository.save_claim_sentence({**dict(payload), "clean_claim_id": clean_claim_id}, flush=False)

        comment_records_by_source_row: dict[str, Any] = {}
        for payload in comments:
            saved = comment_repository.save_comment(payload, flush=False)
            comment_records_by_source_row[payload["source_row_id"]] = saved.record
        if comment_records_by_source_row:
            self.db.flush()
        comment_ids_by_source_row = {
            source_row_id: record.clean_comment_id
            for source_row_id, record in comment_records_by_source_row.items()
        }
        for payload in comment_sentences:
            clean_comment_id = comment_ids_by_source_row.get(str(payload.get("source_row_id")))
            if clean_comment_id:
                comment_repository.save_comment_sentence(
                    {**dict(payload), "clean_comment_id": clean_comment_id},
                    flush=False,
                )
        for payload in comment_dimensions:
            clean_comment_id = comment_ids_by_source_row.get(str(payload.get("source_row_id")))
            if clean_comment_id:
                comment_repository.save_comment_dimension(
                    {**dict(payload), "clean_comment_id": clean_comment_id},
                    flush=False,
                )

        for payload in clean_skus:
            sku_repository.save_sku(payload, flush=False)
        for payload in quality_issues:
            issue_repository.save_issue(payload, flush=False)
        self.db.flush()

    def _build_batch_market_scope(
        self,
        *,
        source_row_reader: SourceRowRegistryReader,
        raw_source_repository: RawSourceRepository,
        batch_id: str,
        include_no_change: bool,
    ) -> dict[str, Any]:
        source_row_chunks = source_row_reader.iter_processable_row_chunks(
            batch_id,
            chunk_size=self.source_row_chunk_size,
            include_no_change=include_no_change,
            source_tables=("week_sales_data",),
        )
        scope_records: list[dict[str, Any]] = []
        for source_rows in source_row_chunks:
            raw_rows_by_ref = self._load_raw_rows_by_source_ref(
                raw_source_repository=raw_source_repository,
                source_rows=source_rows,
            )
            for source_row in source_rows:
                if not source_row.source_pk:
                    continue
                raw_row = raw_rows_by_ref.get((source_row.source_table, source_row.source_pk))
                if raw_row is None:
                    continue
                period = PeriodParser.parse(raw_row.get("date_value"))
                if period.period_week_index is None:
                    continue
                scope_records.append(
                    {
                        "period_raw": TextNormalizer.normalize(raw_row.get("date_value")),
                        "period_week_index": period.period_week_index,
                        "period_year_hint": period.period_year_hint,
                    }
                )
        return build_market_batch_scope(scope_records)


def _empty_clean_outputs() -> dict[str, list[dict[str, Any]]]:
    return {
        "markets": [],
        "attributes": [],
        "claims": [],
        "claim_sentences": [],
        "comments": [],
        "comment_sentences": [],
        "comment_dimensions": [],
        "quality_issues": [],
    }


def _extend_clean_outputs(
    target: dict[str, list[dict[str, Any]]],
    source: Mapping[str, list[dict[str, Any]]],
) -> None:
    target["markets"].extend(source["markets"])
    target["attributes"].extend(source["attributes"])
    target["claims"].extend(source["claims"])
    target["claim_sentences"].extend(source["claim_sentences"])
    target["comments"].extend(source["comments"])
    target["comment_sentences"].extend(source["comment_sentences"])
    target["comment_dimensions"].extend(source["comment_dimensions"])


class _CleaningRunAccumulator:
    def __init__(self) -> None:
        self.input_count = 0
        self.markets: list[dict[str, Any]] = []
        self.attributes: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []
        self._comment_representatives_by_sku: dict[str, dict[str, Any]] = {}
        self._comment_aggregates_by_sku: dict[str, dict[str, Any]] = {}

    def add_cleaned(self, cleaned: Mapping[str, list[dict[str, Any]]]) -> None:
        self.markets.extend(cleaned["markets"])
        self.attributes.extend(cleaned["attributes"])
        self.claims.extend(cleaned["claims"])
        for comment in cleaned["comments"]:
            self._add_comment(comment)

    def comment_representatives(self) -> list[dict[str, Any]]:
        return list(self._comment_representatives_by_sku.values())

    def comment_summaries(self) -> dict[str, dict[str, Any]]:
        return {
            sku_code: _comment_summary_payload(aggregate)
            for sku_code, aggregate in self._comment_aggregates_by_sku.items()
        }

    def _add_comment(self, comment: Mapping[str, Any]) -> None:
        sku_code = str(comment.get("sku_code") or "")
        if not sku_code:
            return

        aggregate = self._comment_aggregates_by_sku.setdefault(sku_code, _new_comment_aggregate())
        aggregate["raw_row_count"] += 1
        low_value = bool(comment.get("low_value_flag"))
        if low_value:
            aggregate["low_value_comment_count"] += 1

        comment_id = comment.get("comment_id")
        if comment_id:
            aggregate["distinct_comment_ids"].add(str(comment_id))

        comment_text_hash = comment.get("comment_text_hash")
        if comment_text_hash and not low_value:
            aggregate["text_hash_counts"][str(comment_text_hash)] += 1

        service_candidate = bool(comment.get("_service_candidate")) or "服务履约评价" in str(
            comment.get("low_value_reason") or ""
        )
        if service_candidate:
            aggregate["service_candidate_count"] += 1
            if not low_value:
                aggregate["service_candidate_after_low_value_count"] += 1

        if sku_code not in self._comment_representatives_by_sku:
            self._comment_representatives_by_sku[sku_code] = _comment_representative(comment)


def _new_comment_aggregate() -> dict[str, Any]:
    return {
        "raw_row_count": 0,
        "low_value_comment_count": 0,
        "service_candidate_count": 0,
        "service_candidate_after_low_value_count": 0,
        "distinct_comment_ids": set(),
        "text_hash_counts": Counter(),
    }


def _comment_representative(comment: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "source_table",
        "source_row_id",
        "sku_code",
        "model_name",
        "brand_name",
        "category_name_raw",
        "category_name",
        "comment_id",
        "low_value_flag",
        "quality_flags",
    )
    return {key: comment.get(key) for key in keys if key in comment}


def _comment_summary_payload(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    raw_row_count = int(aggregate.get("raw_row_count") or 0)
    low_value_count = int(aggregate.get("low_value_comment_count") or 0)
    service_candidate_count = int(aggregate.get("service_candidate_count") or 0)
    service_after_low_value_count = int(aggregate.get("service_candidate_after_low_value_count") or 0)
    text_hash_counts = aggregate.get("text_hash_counts") or Counter()
    duplicate_text_group_count = sum(1 for count in text_hash_counts.values() if count > 1)
    duplicate_text_row_count = sum(int(count) for count in text_hash_counts.values() if count > 1)
    candidate_after_low_value_count = max(raw_row_count - low_value_count, 0)
    distinct_comment_id_count = len(aggregate.get("distinct_comment_ids") or set())
    preliminary_filter = {
        "raw_row_count": raw_row_count,
        "low_value_comment_count": low_value_count,
        "low_value_comment_rate": _rate(low_value_count, raw_row_count),
        "empty_or_default_comment_count": max(low_value_count - service_candidate_count, 0),
        "blocked_comment_count": low_value_count,
        "candidate_after_low_value_count": candidate_after_low_value_count,
        "distinct_comment_id_count": distinct_comment_id_count,
        "distinct_comment_text_hash_count": len(text_hash_counts),
        "duplicate_text_group_count": duplicate_text_group_count,
        "duplicate_text_row_count": duplicate_text_row_count,
        "service_candidate_count": service_candidate_count,
        "service_candidate_rate": _rate(service_candidate_count, raw_row_count),
        "service_candidate_after_low_value_count": service_after_low_value_count,
        "service_candidate_after_low_value_rate": _rate(
            service_after_low_value_count,
            candidate_after_low_value_count,
        ),
        "service_candidate_not_blocked": False,
        "policy_cn": "本阶段过滤空/默认/低质评论；客服、物流、安装、售后等服务履约评价并入低价值评论，不进入后续产品分析。",
    }
    return {
        "row_count": raw_row_count,
        "covered": raw_row_count > 0,
        "distinct_comment_id_count": distinct_comment_id_count,
        "preliminary_filter": preliminary_filter,
    }


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)


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
