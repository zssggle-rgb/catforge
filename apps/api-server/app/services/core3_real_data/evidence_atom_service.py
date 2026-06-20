"""M02 evidence atom service and runner orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    CORE3_M02_CONFIDENCE_RULE_VERSION,
    CORE3_M02_EVIDENCE_VERSION,
    CORE3_M02_MODULE_VERSION,
    Core3ConfidenceLevel,
    Core3DataDomain,
    Core3EvidenceInactiveReason,
    Core3ModuleCode,
    Core3QualityIssueType,
    Core3ReviewStatus,
    Core3RunStatus,
)
from app.services.core3_real_data.evidence_atom_repositories import (
    EvidenceAtomRepository,
    EvidenceCurrentConflictError,
    EvidenceLinkRepository,
)
from app.services.core3_real_data.evidence_confidence import EvidenceConfidenceService
from app.services.core3_real_data.evidence_links import EvidenceLinkBuilder
from app.services.core3_real_data.evidence_mappers import EvidenceMapper, MappedEvidenceDraft
from app.services.core3_real_data.evidence_payloads import EvidencePayloadBuilder
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


CLEAN_MODEL_BY_TABLE: dict[str, Any] = {
    "core3_clean_sku": entities.Core3CleanSku,
    "core3_clean_market_weekly": entities.Core3CleanMarketWeekly,
    "core3_clean_attribute": entities.Core3CleanAttribute,
    "core3_clean_claim": entities.Core3CleanClaim,
    "core3_clean_claim_sentence": entities.Core3CleanClaimSentence,
    "core3_clean_comment": entities.Core3CleanComment,
    "core3_clean_comment_sentence": entities.Core3CleanCommentSentence,
    "core3_clean_comment_dimension": entities.Core3CleanCommentDimension,
    "core3_data_quality_issue": entities.Core3DataQualityIssue,
}

M02_PARTITION_STRATEGY = "sku_partition_v1"
MAX_SQL_EXCLUDE_SOURCE_ROW_IDS = 50000
COMMENT_SEMANTIC_CLEAN_TABLES = frozenset(
    {
        "core3_clean_comment",
        "core3_clean_comment_sentence",
        "core3_clean_comment_dimension",
    }
)
COMMENT_SEMANTIC_EVIDENCE_TYPES = (
    "comment_raw",
    "comment_sentence",
    "comment_dimension",
)
COMMENT_QUALITY_ISSUE_CLEAN_TABLES = ("core3_data_quality_issue",)
COMMENT_QUALITY_ISSUE_EVIDENCE_TYPES = ("quality_issue",)
NON_CONSUMABLE_COMMENT_QUALITY_TYPES = frozenset(
    {
        Core3QualityIssueType.LOW_VALUE_COMMENT.value,
        Core3QualityIssueType.DUPLICATE_COMMENT_TEXT.value,
    }
)
EXACT_NON_BUSINESS_COMMENT_TEXTS = frozenset(
    {
        "好",
        "很好",
        "非常好",
        "不错",
        "挺好",
        "可以",
        "还可以",
        "满意",
        "很满意",
        "好用",
        "此用户未及时填写评价内容",
    }
)
NON_BUSINESS_COMMENT_CONTAINS = (
    "送装一体",
    "京东服务",
)


@dataclass(frozen=True)
class CleanFactBatch:
    clean_table: str
    records: list[Mapping[str, Any] | Any]


@dataclass(frozen=True)
class CommentSemanticFilter:
    low_value_source_rows: set[str]
    duplicate_non_representative_source_rows: set[str]
    template_source_rows: set[str]

    @property
    def excluded_source_rows(self) -> set[str]:
        return (
            set(self.low_value_source_rows)
            | set(self.duplicate_non_representative_source_rows)
            | set(self.template_source_rows)
        )


@dataclass(frozen=True)
class EvidenceAtomServiceResult:
    input_count: int
    created_atom_count: int
    reused_atom_count: int
    superseded_atom_count: int
    inactive_atom_count: int
    created_link_count: int
    reused_link_count: int
    inactive_link_count: int
    preloaded_link_count: int
    summary: dict[str, Any]
    link_counts: dict[str, int]
    partition_count: int
    partition_summaries: list[dict[str, Any]]
    warnings: list[str]


class CleanFactReader:
    """Read M01 clean facts as the only M02 input surface."""

    def __init__(self, repository_context: Core3RepositoryContext) -> None:
        self.context = repository_context
        self.db = repository_context.db

    def list_fact_batches(
        self,
        batch_id: str,
        *,
        target_sku_codes: Sequence[str] = (),
        comment_filter: CommentSemanticFilter | None = None,
    ) -> list[CleanFactBatch]:
        target_set = {sku_code for sku_code in target_sku_codes if sku_code}
        resolved_comment_filter = comment_filter or self.build_comment_semantic_filter(batch_id, target_set)
        return [
            CleanFactBatch(
                clean_table=clean_table,
                records=self._list_table(clean_table, batch_id, target_set, resolved_comment_filter),
            )
            for clean_table in CLEAN_MODEL_BY_TABLE
        ]

    def list_partition_sku_codes(
        self,
        batch_id: str,
        *,
        target_sku_codes: Sequence[str] = (),
    ) -> list[str]:
        if target_sku_codes:
            return sorted({sku_code for sku_code in target_sku_codes if sku_code})

        stmt = (
            select(entities.Core3CleanSku.sku_code)
            .where(entities.Core3CleanSku.project_id == self.context.project_id)
            .where(entities.Core3CleanSku.category_code == self.context.category_code.value)
            .where(entities.Core3CleanSku.batch_id == batch_id)
            .where(entities.Core3CleanSku.sku_code.is_not(None))
            .distinct()
            .order_by(entities.Core3CleanSku.sku_code)
        )
        return [str(sku_code) for sku_code in self.db.execute(stmt).scalars() if sku_code]

    def _list_table(
        self,
        clean_table: str,
        batch_id: str,
        target_sku_codes: set[str],
        comment_filter: CommentSemanticFilter,
    ) -> list[Mapping[str, Any] | Any]:
        model_cls = CLEAN_MODEL_BY_TABLE[clean_table]
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.context.project_id)
            .where(model_cls.category_code == self.context.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )
        if target_sku_codes and hasattr(model_cls, "sku_code"):
            stmt = stmt.where(model_cls.sku_code.in_(tuple(target_sku_codes)))
        if clean_table == "core3_data_quality_issue":
            stmt = stmt.where(
                ~(
                    (model_cls.domain == "comment")
                    & model_cls.issue_type.in_(tuple(NON_CONSUMABLE_COMMENT_QUALITY_TYPES))
                )
            )
            stmt = _exclude_comment_quality_source_rows(stmt, model_cls, comment_filter.excluded_source_rows)
        elif clean_table in COMMENT_SEMANTIC_CLEAN_TABLES:
            stmt = _exclude_low_value_comment_rows(stmt, clean_table, model_cls)
            stmt = _exclude_source_rows(stmt, model_cls, comment_filter.excluded_source_rows)
        stmt = stmt.order_by(*_order_columns(model_cls))
        records = list(self.db.execute(stmt).scalars())
        if clean_table == "core3_data_quality_issue":
            return [
                _quality_issue_payload(record)
                for record in records
                if not _is_non_consumable_comment_quality_issue(record, comment_filter)
            ]
        if clean_table in COMMENT_SEMANTIC_CLEAN_TABLES:
            return [
                record
                for record in records
                if not _is_non_consumable_comment_semantic_record(record, comment_filter)
            ]
        return records

    def list_low_value_comment_source_rows(self, batch_id: str, target_sku_codes: Sequence[str] | set[str] = ()) -> set[str]:
        return self.build_comment_semantic_filter(batch_id, target_sku_codes).low_value_source_rows

    def build_comment_semantic_filter(
        self,
        batch_id: str,
        target_sku_codes: Sequence[str] | set[str] = (),
    ) -> CommentSemanticFilter:
        target_set = {sku_code for sku_code in target_sku_codes if sku_code}
        stmt = (
            select(
                entities.Core3CleanComment.source_row_id,
                entities.Core3CleanComment.duplicate_group_key,
                entities.Core3CleanComment.clean_comment_text,
                entities.Core3CleanComment.low_value_flag,
                entities.Core3CleanComment.quality_flags,
            )
            .where(entities.Core3CleanComment.project_id == self.context.project_id)
            .where(entities.Core3CleanComment.category_code == self.context.category_code.value)
            .where(entities.Core3CleanComment.batch_id == batch_id)
        )
        if target_set:
            stmt = stmt.where(entities.Core3CleanComment.sku_code.in_(tuple(target_set)))
        target_comments = list(self.db.execute(stmt).mappings())

        low_value_source_rows: set[str] = set()
        template_source_rows: set[str] = set()
        duplicate_candidate_groups: set[str] = set()
        target_rows_by_source: dict[str, Mapping[str, Any]] = {}
        for comment in target_comments:
            source_row_id = str(comment.get("source_row_id") or "")
            if not source_row_id:
                continue
            target_rows_by_source[source_row_id] = comment
            if _is_low_value_comment_record(comment):
                low_value_source_rows.add(source_row_id)
                continue
            if _is_non_business_comment_template(comment.get("clean_comment_text")):
                template_source_rows.add(source_row_id)
                continue
            duplicate_group_key = comment.get("duplicate_group_key")
            if duplicate_group_key:
                duplicate_candidate_groups.add(str(duplicate_group_key))

        representative_by_group: dict[str, str] = {}
        if duplicate_candidate_groups:
            for group_chunk in _chunks(sorted(duplicate_candidate_groups), 1000):
                representative_stmt = (
                    select(
                        entities.Core3CleanComment.duplicate_group_key,
                        func.min(entities.Core3CleanComment.source_row_id),
                    )
                    .where(entities.Core3CleanComment.project_id == self.context.project_id)
                    .where(entities.Core3CleanComment.category_code == self.context.category_code.value)
                    .where(entities.Core3CleanComment.batch_id == batch_id)
                    .where(entities.Core3CleanComment.low_value_flag.is_(False))
                    .where(entities.Core3CleanComment.duplicate_group_key.in_(tuple(group_chunk)))
                    .group_by(entities.Core3CleanComment.duplicate_group_key)
                )
                representative_by_group.update(
                    {
                        str(group_key): str(source_row_id)
                        for group_key, source_row_id in self.db.execute(representative_stmt).all()
                        if group_key and source_row_id
                    }
                )

        duplicate_non_representative_source_rows: set[str] = set()
        for source_row_id, comment in target_rows_by_source.items():
            if source_row_id in low_value_source_rows or source_row_id in template_source_rows:
                continue
            duplicate_group_key = comment.get("duplicate_group_key")
            representative_source_row_id = representative_by_group.get(str(duplicate_group_key)) if duplicate_group_key else None
            if representative_source_row_id and source_row_id != representative_source_row_id:
                duplicate_non_representative_source_rows.add(source_row_id)

        return CommentSemanticFilter(
            low_value_source_rows=low_value_source_rows,
            duplicate_non_representative_source_rows=duplicate_non_representative_source_rows,
            template_source_rows=template_source_rows,
        )


class EvidenceAtomService:
    def __init__(
        self,
        repository_context: Core3RepositoryContext,
        *,
        fact_reader: CleanFactReader | None = None,
        mapper: EvidenceMapper | None = None,
        payload_builder: EvidencePayloadBuilder | None = None,
        confidence_service: EvidenceConfidenceService | None = None,
        link_builder: EvidenceLinkBuilder | None = None,
    ) -> None:
        self.context = repository_context
        self.fact_reader = fact_reader or CleanFactReader(repository_context)
        self.mapper = mapper or EvidenceMapper()
        self.payload_builder = payload_builder or EvidencePayloadBuilder()
        self.confidence_service = confidence_service or EvidenceConfidenceService()
        self.link_builder = link_builder or EvidenceLinkBuilder()

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        evidence_version: str = CORE3_M02_EVIDENCE_VERSION,
        confidence_rule_version: str = CORE3_M02_CONFIDENCE_RULE_VERSION,
        asset_version: str = "default",
        target_sku_codes: Sequence[str] = (),
    ) -> EvidenceAtomServiceResult:
        atom_repository = EvidenceAtomRepository(self.context)
        link_repository = EvidenceLinkRepository(self.context)
        if atom_repository.count_current_atoms() == 0:
            atom_repository.skip_existing_lookup_when_empty()
        if link_repository.count_batch_links(batch_id) == 0:
            link_repository.skip_existing_lookup_for_batch(batch_id)

        input_count = 0
        created_atom_count = 0
        reused_atom_count = 0
        superseded_atom_count = 0
        inactive_atom_count = 0
        created_link_count = 0
        reused_link_count = 0
        inactive_link_count = 0
        preloaded_link_count = 0
        partition_summaries: list[dict[str, Any]] = []
        partition_sku_codes = self.fact_reader.list_partition_sku_codes(
            batch_id,
            target_sku_codes=target_sku_codes,
        )
        partition_targets: list[tuple[str | None, Sequence[str]]] = [
            (sku_code, (sku_code,)) for sku_code in partition_sku_codes
        ] or [(None, target_sku_codes)]

        for partition_index, (partition_sku_code, partition_target_sku_codes) in enumerate(partition_targets, start=1):
            partition_result = self._build_partition(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                evidence_version=evidence_version,
                confidence_rule_version=confidence_rule_version,
                asset_version=asset_version,
                target_sku_codes=partition_target_sku_codes,
                atom_repository=atom_repository,
                link_repository=link_repository,
            )
            input_count += int(partition_result["input_count"])
            created_atom_count += int(partition_result["created_atom_count"])
            reused_atom_count += int(partition_result["reused_atom_count"])
            superseded_atom_count += int(partition_result["superseded_atom_count"])
            inactive_atom_count += int(partition_result["inactive_atom_count"])
            created_link_count += int(partition_result["created_link_count"])
            reused_link_count += int(partition_result["reused_link_count"])
            inactive_link_count += int(partition_result["inactive_link_count"])
            preloaded_link_count += int(partition_result["preloaded_link_count"])
            partition_summaries.append(
                {
                    "partition_index": partition_index,
                    "sku_code": partition_sku_code,
                    **partition_result,
                }
            )
            self.context.db.flush()
            self.context.db.expunge_all()
            atom_repository.clear_save_cache()
            link_repository.clear_save_cache()

        self.context.db.flush()

        summary = atom_repository.get_summary(batch_id)
        link_counts = link_repository.count_by_type(batch_id)
        warnings = _warnings(summary, input_count=input_count)
        return EvidenceAtomServiceResult(
            input_count=input_count,
            created_atom_count=created_atom_count,
            reused_atom_count=reused_atom_count,
            superseded_atom_count=superseded_atom_count,
            inactive_atom_count=inactive_atom_count,
            created_link_count=created_link_count,
            reused_link_count=reused_link_count,
            inactive_link_count=inactive_link_count,
            preloaded_link_count=preloaded_link_count,
            summary=summary,
            link_counts=link_counts,
            partition_count=len(partition_targets),
            partition_summaries=partition_summaries,
            warnings=warnings,
        )

    def _build_partition(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        evidence_version: str,
        confidence_rule_version: str,
        asset_version: str,
        target_sku_codes: Sequence[str],
        atom_repository: EvidenceAtomRepository,
        link_repository: EvidenceLinkRepository,
    ) -> dict[str, int]:
        comment_filter = self.fact_reader.build_comment_semantic_filter(batch_id, target_sku_codes)
        fact_batches = self.fact_reader.list_fact_batches(
            batch_id,
            target_sku_codes=target_sku_codes,
            comment_filter=comment_filter,
        )
        input_count = 0
        created_atom_count = 0
        reused_atom_count = 0
        superseded_pairs: list[tuple[Any, Any]] = []
        inactive_evidence_ids = self._mark_non_consumable_comment_evidence_inactive(
            atom_repository=atom_repository,
            link_repository=link_repository,
            batch_id=batch_id,
            comment_filter=comment_filter,
        )
        inactive_atom_count = len(inactive_evidence_ids)
        current_records: list[Any] = []

        for fact_batch in fact_batches:
            for record in fact_batch.records:
                input_count += 1
                if _record_status(record) != "active":
                    inactive_atom_count += atom_repository.mark_inactive_by_clean_record(
                        batch_id,
                        fact_batch.clean_table,
                        str(_record_value(record, "clean_record_key")),
                        inactive_reason=Core3EvidenceInactiveReason.CLEAN_RECORD_INACTIVE.value,
                    )
                    continue

                draft = self.mapper.map_clean_record(
                    record,
                    clean_table=fact_batch.clean_table,
                    evidence_version=evidence_version,
                )
                payload = self._atom_payload(
                    draft,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    confidence_rule_version=confidence_rule_version,
                    evidence_version=evidence_version,
                    asset_version=asset_version,
                )
                result = atom_repository.save_atom(payload)
                if result.created:
                    created_atom_count += 1
                else:
                    reused_atom_count += 1
                if result.superseded_record is not None:
                    superseded_pairs.append((result.record, result.superseded_record))
                    link_repository.mark_links_inactive_for_evidence(result.superseded_record.evidence_id)
                current_records.append(result.record)

        self.context.db.flush()

        created_link_count = 0
        reused_link_count = 0
        link_drafts = self.link_builder.build_links(current_records, superseded_pairs=superseded_pairs)
        desired_link_keys = {
            (link.from_evidence_id, link.to_evidence_id, link.link_type.value)
            for link in link_drafts
        }
        desired_link_types = sorted({link.link_type.value for link in link_drafts})
        evidence_ids = [str(record.evidence_id) for record in current_records]
        preloaded_link_count = link_repository.preload_links_for_evidence_set(
            batch_id,
            evidence_ids=evidence_ids,
            link_types=desired_link_types,
        )
        for link in link_drafts:
            link_result = link_repository.save_link(link.to_payload())
            if link_result.created:
                created_link_count += 1
            else:
                reused_link_count += 1

        inactive_link_count = link_repository.mark_obsolete_current_links_for_evidence_set(
            batch_id,
            evidence_ids=evidence_ids,
            desired_link_keys=desired_link_keys,
            link_types=desired_link_types,
        )
        self.context.db.flush()
        return {
            "input_count": input_count,
            "created_atom_count": created_atom_count,
            "reused_atom_count": reused_atom_count,
            "superseded_atom_count": len(superseded_pairs),
            "inactive_atom_count": inactive_atom_count,
            "created_link_count": created_link_count,
            "reused_link_count": reused_link_count,
            "inactive_link_count": inactive_link_count,
            "preloaded_link_count": preloaded_link_count,
            "skipped_low_value_comment_count": len(comment_filter.low_value_source_rows),
            "skipped_duplicate_comment_count": len(comment_filter.duplicate_non_representative_source_rows),
            "skipped_template_comment_count": len(comment_filter.template_source_rows),
        }

    def _mark_non_consumable_comment_evidence_inactive(
        self,
        *,
        atom_repository: EvidenceAtomRepository,
        link_repository: EvidenceLinkRepository,
        batch_id: str,
        comment_filter: CommentSemanticFilter,
    ) -> list[str]:
        inactive_evidence_ids: list[str] = []
        for source_row_ids, inactive_reason in [
            (comment_filter.low_value_source_rows, Core3EvidenceInactiveReason.LOW_VALUE_SKIPPED.value),
            (
                comment_filter.duplicate_non_representative_source_rows,
                Core3EvidenceInactiveReason.DUPLICATE_REPRESENTATIVE_SKIPPED.value,
            ),
            (comment_filter.template_source_rows, Core3EvidenceInactiveReason.COMMENT_TEMPLATE_SKIPPED.value),
        ]:
            if not source_row_ids:
                continue
            inactive_evidence_ids.extend(
                atom_repository.mark_evidence_inactive_by_source_rows(
                    batch_id,
                    source_row_ids=source_row_ids,
                    clean_tables=tuple(COMMENT_SEMANTIC_CLEAN_TABLES),
                    evidence_types=COMMENT_SEMANTIC_EVIDENCE_TYPES,
                    inactive_reason=inactive_reason,
                )
            )
            inactive_evidence_ids.extend(
                atom_repository.mark_evidence_inactive_by_source_rows(
                    batch_id,
                    source_row_ids=source_row_ids,
                    clean_tables=COMMENT_QUALITY_ISSUE_CLEAN_TABLES,
                    evidence_types=COMMENT_QUALITY_ISSUE_EVIDENCE_TYPES,
                    inactive_reason=inactive_reason,
                )
            )

        for evidence_id in inactive_evidence_ids:
            link_repository.mark_links_inactive_for_evidence(evidence_id)
        return inactive_evidence_ids

    def _atom_payload(
        self,
        draft: MappedEvidenceDraft,
        *,
        run_id: str | None,
        module_run_id: str | None,
        evidence_version: str,
        confidence_rule_version: str,
        asset_version: str,
    ) -> dict[str, Any]:
        payload = self.payload_builder.build_atom_values(draft)
        if draft.evidence_time is not None:
            payload["evidence_time"] = draft.evidence_time
        evidence_payload = payload["evidence_payload_json"]
        confidence = self.confidence_service.calculate(draft, evidence_payload=evidence_payload)
        review_required = _review_required(draft, confidence.confidence_level)
        payload.update(
            run_id=run_id,
            module_run_id=module_run_id,
            base_confidence=confidence.base_confidence,
            confidence_level=confidence.confidence_level.value,
            evidence_status="current",
            inactive_reason=None,
            is_current=True,
            evidence_version=evidence_version,
            confidence_rule_version=confidence_rule_version,
            asset_version=asset_version,
            review_required=review_required,
            review_status=(
                Core3ReviewStatus.REVIEW_REQUIRED.value
                if review_required
                else Core3ReviewStatus.AUTO_PASS.value
            ),
        )
        return payload


class EvidenceAtomRunner:
    module_code = Core3ModuleCode.M02

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(context, "M02 缺少 M00 batch_id，无法确定 evidence 生成范围。")

        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            evidence_version=str(target.metadata.get("evidence_version") or CORE3_M02_EVIDENCE_VERSION),
            confidence_rule_version=str(
                target.metadata.get("confidence_rule_version") or CORE3_M02_CONFIDENCE_RULE_VERSION
            ),
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
        evidence_version: str = CORE3_M02_EVIDENCE_VERSION,
        confidence_rule_version: str = CORE3_M02_CONFIDENCE_RULE_VERSION,
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
                _minimal_context(project_id=project_id, category_code=category_code, batch_id=batch_id, run_id=run_id),
                str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        try:
            with self.db.begin_nested():
                service_result = EvidenceAtomService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    evidence_version=evidence_version,
                    confidence_rule_version=confidence_rule_version,
                    target_sku_codes=target_sku_codes,
                )
        except EvidenceCurrentConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m02_current_evidence_conflict",
                message_cn="同一 evidence_key 存在多条 current evidence，M02 停止以避免下游引用不确定证据。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m02_evidence_build_failed",
                message_cn="M02 evidence 生成失败，请检查清洗事实字段和 evidence 映射规则。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M02_MODULE_VERSION,
            "evidence_version": evidence_version,
            "confidence_rule_version": confidence_rule_version,
            "target_sku_codes": list(target_sku_codes),
            "partition_strategy": M02_PARTITION_STRATEGY,
            "partition_count": service_result.partition_count,
            "partition_summaries": service_result.partition_summaries,
            "evidence_counts": service_result.summary,
            "link_counts": service_result.link_counts,
            "created_atom_count": service_result.created_atom_count,
            "reused_atom_count": service_result.reused_atom_count,
            "superseded_atom_count": service_result.superseded_atom_count,
            "inactive_atom_count": service_result.inactive_atom_count,
            "created_link_count": service_result.created_link_count,
            "reused_link_count": service_result.reused_link_count,
            "inactive_link_count": service_result.inactive_link_count,
            "preloaded_link_count": service_result.preloaded_link_count,
        }
        output_hash = stable_hash(summary_json, version="m02_evidence_summary_v1")
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M02,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_atom_count
            + service_result.superseded_atom_count
            + service_result.inactive_atom_count,
            output_count=int(service_result.summary["total"]),
            output_hash=output_hash,
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=_downstream_impacts(service_result.summary),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


def _order_columns(model_cls: Any) -> list[Any]:
    columns = [model_cls.batch_id]
    for field_name in ("sku_code", "source_row_id", "clean_record_key"):
        if hasattr(model_cls, field_name):
            columns.append(getattr(model_cls, field_name))
    return columns


def _quality_issue_payload(record: entities.Core3DataQualityIssue) -> dict[str, Any]:
    issue_key = record.clean_record_key or f"quality:{record.domain}:{record.issue_type}:{record.sku_code or record.issue_id}"
    source_payload = {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
    }
    source_payload.update(
        source_clean_table="core3_data_quality_issue",
        clean_record_key=issue_key,
        clean_hash=stable_hash(
            {
                "batch_id": record.batch_id,
                "domain": record.domain,
                "issue_type": record.issue_type,
                "source_row_id": record.source_row_id,
                "clean_record_key": issue_key,
                "sku_code": record.sku_code,
                "severity": record.severity,
                "issue_detail": record.issue_detail,
                "issue_payload_json": record.issue_payload_json or {},
            },
            version=CORE3_M01_CLEAN_HASH_VERSION,
        ),
        clean_version=CORE3_M01_CLEAN_VERSION,
        quality_status="warning" if record.severity in {"warning", "error"} else "ok",
        quality_flags=[record.issue_type],
    )
    return source_payload


def _record_status(record: Mapping[str, Any] | Any) -> str:
    status = _record_value(record, "record_status")
    return str(status or "active")


def _is_non_consumable_comment_semantic_record(
    record: Mapping[str, Any] | Any,
    comment_filter: CommentSemanticFilter,
) -> bool:
    if _is_low_value_comment_record(record):
        return True
    source_row_id = _record_value(record, "source_row_id")
    return bool(source_row_id and str(source_row_id) in comment_filter.excluded_source_rows)


def _is_non_consumable_comment_quality_issue(
    record: entities.Core3DataQualityIssue,
    comment_filter: CommentSemanticFilter,
) -> bool:
    if record.domain != "comment":
        return False
    if record.issue_type in NON_CONSUMABLE_COMMENT_QUALITY_TYPES:
        return True
    return bool(record.source_row_id and str(record.source_row_id) in comment_filter.excluded_source_rows)


def _is_low_value_comment_record(record: Mapping[str, Any] | Any) -> bool:
    if bool(_record_value(record, "low_value_flag")):
        return True
    quality_flags = _record_value(record, "quality_flags") or []
    return Core3QualityIssueType.LOW_VALUE_COMMENT.value in {str(flag) for flag in quality_flags}


def _is_non_business_comment_template(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    compact = (
        text.replace(" ", "")
        .replace("，", ",")
        .replace("。", "")
        .replace("！", "!")
        .replace("；", ";")
    )
    if compact in EXACT_NON_BUSINESS_COMMENT_TEXTS:
        return True
    if any(pattern in compact for pattern in NON_BUSINESS_COMMENT_CONTAINS):
        return True
    return "购物体验" in compact and "强烈推荐" in compact


def _exclude_source_rows(stmt: Any, model_cls: Any, source_row_ids: set[str]) -> Any:
    if not source_row_ids or not hasattr(model_cls, "source_row_id"):
        return stmt
    if len(source_row_ids) > MAX_SQL_EXCLUDE_SOURCE_ROW_IDS:
        return stmt
    for source_row_chunk in _chunks(sorted(source_row_ids), 1000):
        stmt = stmt.where(~model_cls.source_row_id.in_(tuple(source_row_chunk)))
    return stmt


def _exclude_low_value_comment_rows(stmt: Any, clean_table: str, model_cls: Any) -> Any:
    if clean_table == "core3_clean_comment" and hasattr(model_cls, "low_value_flag"):
        return stmt.where(model_cls.low_value_flag.is_(False))
    if clean_table in {"core3_clean_comment_sentence", "core3_clean_comment_dimension"} and hasattr(
        model_cls,
        "clean_comment_id",
    ):
        return stmt.where(
            exists()
            .where(entities.Core3CleanComment.clean_comment_id == model_cls.clean_comment_id)
            .where(entities.Core3CleanComment.low_value_flag.is_(False))
        )
    return stmt


def _exclude_comment_quality_source_rows(stmt: Any, model_cls: Any, source_row_ids: set[str]) -> Any:
    if not source_row_ids or not hasattr(model_cls, "source_row_id"):
        return stmt
    if len(source_row_ids) > MAX_SQL_EXCLUDE_SOURCE_ROW_IDS:
        return stmt
    for source_row_chunk in _chunks(sorted(source_row_ids), 1000):
        stmt = stmt.where(
            (model_cls.domain != "comment")
            | model_cls.source_row_id.is_(None)
            | ~model_cls.source_row_id.in_(tuple(source_row_chunk))
        )
    return stmt


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _record_value(record: Mapping[str, Any] | Any, field_name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _review_required(draft: MappedEvidenceDraft, confidence_level: Core3ConfidenceLevel) -> bool:
    source_payload = draft.source_payload or {}
    if bool(source_payload.get("review_required")):
        return True
    return confidence_level in {Core3ConfidenceLevel.LOW, Core3ConfidenceLevel.UNKNOWN}


def _warnings(summary: Mapping[str, Any], *, input_count: int) -> list[str]:
    warnings: list[str] = []
    if input_count == 0:
        warnings.append("m02_empty_clean_input")
    if int(summary.get("low_confidence", 0)) > 0:
        warnings.append("m02_low_confidence_evidence")
    if int(summary.get("review_required", 0)) > 0:
        warnings.append("m02_review_required_evidence")
    return warnings


def _downstream_impacts(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    if int(summary.get("current", 0)) <= 0:
        return []
    return [
        {
            "module_code": Core3ModuleCode.M03.value,
            "reason_cn": "M02 已生成参数 evidence，M03 可构建参数画像。",
        },
        {
            "module_code": Core3ModuleCode.M04A.value,
            "reason_cn": "M02 已生成卖点和质量 evidence，M04a 可做基础卖点激活。",
        },
        {
            "module_code": Core3ModuleCode.M05.value,
            "reason_cn": "M02 已生成评论 evidence 和评论关系，M05 可构建评论基础证据。",
        },
        {
            "module_code": Core3ModuleCode.M07.value,
            "reason_cn": "M02 已生成市场 evidence，M07 可构建市场画像。",
        },
    ]


def _blocked_result(
    context: Core3RunContext,
    message: str,
    *,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M02,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=["m02_batch_not_consumable"],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "batch_id": context.batch_id,
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
        module_code=Core3ModuleCode.M02,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m02_evidence_failed_v1"),
        warnings=[error_code],
        review_issues=[],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _minimal_context(*, project_id: str, category_code: str, batch_id: str, run_id: str | None) -> Core3RunContext:
    from app.schemas.core3_real_data import Core3TargetScopeSchema
    from app.services.core3_real_data.constants import Core3RunMode, Core3TargetScopeType

    return Core3RunContext(
        run_id=run_id or "m02-blocked",
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )
