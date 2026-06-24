"""M01 cleaning-quality repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select, tuple_

from app.models.entities import (
    Core3CleanAttribute,
    Core3CleanClaim,
    Core3CleanClaimSentence,
    Core3CleanComment,
    Core3CleanCommentDimension,
    Core3CleanCommentSentence,
    Core3CleanMarketWeekly,
    Core3CleanSku,
    Core3DataQualityIssue,
    Core3SourceBatch,
    Core3SourceImpactedSku,
    Core3SourceRowRegistry,
    new_id,
    now_utc,
)
from app.services.core3_real_data.constants import (
    Core3ReviewStatus,
    Core3SourceBatchStatus,
    Core3SourceOperationType,
)
from app.services.core3_real_data.repositories import Core3BaseRepository


DEFAULT_M01_OPERATION_TYPES: tuple[Core3SourceOperationType, ...] = (
    Core3SourceOperationType.INSERT,
    Core3SourceOperationType.UPDATE,
    Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN,
    Core3SourceOperationType.SKIPPED,
)
M01_CLEAN_TABLES: tuple[str, ...] = (
    "core3_clean_sku",
    "core3_clean_market_weekly",
    "core3_clean_attribute",
    "core3_clean_claim",
    "core3_clean_claim_sentence",
    "core3_clean_comment",
    "core3_clean_comment_sentence",
    "core3_clean_comment_dimension",
    "core3_data_quality_issue",
)


class CleanHashConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class CleanWriteResult:
    record: Any
    created: bool


@dataclass(frozen=True)
class BulkCleanWriteResult:
    ids_by_key: dict[tuple[Any, ...], str]
    created_count: int = 0
    updated_count: int = 0
    reused_count: int = 0


class SourceBatchReader(Core3BaseRepository):
    consumable_statuses = (
        Core3SourceBatchStatus.REGISTERED.value,
        Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value,
    )

    def get_consumable_batch(self, batch_id: str) -> Core3SourceBatch:
        stmt = (
            select(Core3SourceBatch)
            .where(Core3SourceBatch.project_id == self.project_id)
            .where(Core3SourceBatch.category_code == self.category_code.value)
            .where(Core3SourceBatch.batch_id == batch_id)
        )
        batch = self.db.execute(stmt).scalars().first()
        if batch is None:
            raise ValueError(f"source batch not found: {batch_id}")
        if batch.status not in self.consumable_statuses:
            raise ValueError(f"source batch is not consumable: {batch_id}")
        return batch


class SourceRowRegistryReader(Core3BaseRepository):
    def list_processable_rows(
        self,
        batch_id: str,
        *,
        include_no_change: bool = False,
        operation_types: Sequence[Core3SourceOperationType | str] | None = None,
        target_sku_codes: Sequence[str] = (),
    ) -> list[Core3SourceRowRegistry]:
        normalized_operations = _operation_values(operation_types)
        if include_no_change and operation_types is None:
            normalized_operations = (*normalized_operations, Core3SourceOperationType.NO_CHANGE.value)
        normalized_target_skus = _unique_non_empty_values(target_sku_codes)

        stmt = (
            select(Core3SourceRowRegistry)
            .where(Core3SourceRowRegistry.project_id == self.project_id)
            .where(Core3SourceRowRegistry.category_code == self.category_code.value)
            .where(Core3SourceRowRegistry.batch_id == batch_id)
            .where(Core3SourceRowRegistry.operation_type.in_(normalized_operations))
            .order_by(Core3SourceRowRegistry.source_table, Core3SourceRowRegistry.source_pk)
        )
        if normalized_target_skus:
            stmt = stmt.where(Core3SourceRowRegistry.sku_code_candidate.in_(normalized_target_skus))
        return list(self.db.execute(stmt).scalars())


class SourceImpactedSkuReader(Core3BaseRepository):
    def list_impacted_skus(
        self,
        batch_id: str,
        *,
        needs_recompute: bool | None = None,
    ) -> list[Core3SourceImpactedSku]:
        stmt = (
            select(Core3SourceImpactedSku)
            .where(Core3SourceImpactedSku.project_id == self.project_id)
            .where(Core3SourceImpactedSku.category_code == self.category_code.value)
            .where(Core3SourceImpactedSku.batch_id == batch_id)
            .order_by(Core3SourceImpactedSku.sku_code_candidate)
        )
        if needs_recompute is not None:
            stmt = stmt.where(Core3SourceImpactedSku.needs_recompute == needs_recompute)
        return list(self.db.execute(stmt).scalars())


class _CleanFactRepository(Core3BaseRepository):
    model_cls: Any
    unique_fields: tuple[str, ...]

    def _save_clean_fact(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        normalized_payload = self._model_payload(self.model_cls, self._with_project_defaults(payload))
        lookup = {field: normalized_payload.get(field) for field in self.unique_fields}
        existing = self._find_by_lookup(self.model_cls, lookup)
        if existing is not None:
            existing_hash = getattr(existing, "clean_hash", None)
            incoming_hash = normalized_payload.get("clean_hash")
            if existing_hash != incoming_hash:
                self._update_existing(existing, normalized_payload)
            return CleanWriteResult(record=existing, created=False)

        record = self.model_cls(**_jsonable(normalized_payload))
        self.db.add(record)
        self.db.flush()
        return CleanWriteResult(record=record, created=True)

    def _bulk_upsert_clean_facts(
        self,
        payloads: Sequence[Mapping[str, Any]],
        *,
        id_field: str,
    ) -> BulkCleanWriteResult:
        normalized_payloads = [
            self._normalize_bulk_payload(payload, id_field=id_field) for payload in payloads
        ]
        if not normalized_payloads:
            return BulkCleanWriteResult(ids_by_key={})

        existing_by_key = self._existing_rows_by_key(normalized_payloads, id_field=id_field)
        ids_by_key: dict[tuple[Any, ...], str] = {}
        insert_rows: list[dict[str, Any]] = []
        created_count = 0
        updated_count = 0
        reused_count = 0

        for payload in normalized_payloads:
            key = self._unique_key(payload)
            if _key_has_null(key):
                saved = self._save_clean_fact(payload)
                ids_by_key[key] = str(getattr(saved.record, id_field))
                if saved.created:
                    created_count += 1
                else:
                    reused_count += 1
                continue

            existing = existing_by_key.get(key)
            if existing is not None:
                ids_by_key[key] = str(existing[id_field])
                if existing.get("clean_hash") is not None and existing.get("clean_hash") != payload.get("clean_hash"):
                    existing_record = self._find_by_lookup(
                        self.model_cls,
                        {field: payload.get(field) for field in self.unique_fields},
                    )
                    if existing_record is not None:
                        self._update_existing(existing_record, payload)
                        updated_count += 1
                    else:
                        insert_rows.append(payload)
                        created_count += 1
                else:
                    reused_count += 1
                continue

            insert_rows.append(payload)
            ids_by_key[key] = str(payload[id_field])
            created_count += 1

        for chunk in _chunks(insert_rows, 1000):
            self.db.bulk_insert_mappings(self.model_cls, chunk)
        if insert_rows:
            self.db.flush()

        return BulkCleanWriteResult(
            ids_by_key=ids_by_key,
            created_count=created_count,
            updated_count=updated_count,
            reused_count=reused_count,
        )

    def _normalize_bulk_payload(self, payload: Mapping[str, Any], *, id_field: str) -> dict[str, Any]:
        normalized_payload = self._model_payload(self.model_cls, self._with_project_defaults(payload))
        normalized_payload.setdefault(id_field, new_id())
        now = now_utc()
        model_columns = self.model_cls.__table__.columns
        if "created_at" in model_columns:
            normalized_payload.setdefault("created_at", now)
        if "updated_at" in model_columns:
            normalized_payload.setdefault("updated_at", now)
        for column in model_columns:
            if column.name in normalized_payload:
                continue
            default = column.default
            if default is None:
                continue
            if default.is_scalar:
                normalized_payload[column.name] = default.arg
            elif default.is_callable and default.arg in (list, dict):
                normalized_payload[column.name] = default.arg()
        return _jsonable(normalized_payload)

    def _existing_rows_by_key(
        self,
        payloads: Sequence[Mapping[str, Any]],
        *,
        id_field: str,
    ) -> dict[tuple[Any, ...], dict[str, Any]]:
        keys = [self._unique_key(payload) for payload in payloads]
        searchable_keys = [key for key in dict.fromkeys(keys) if not _key_has_null(key)]
        if not searchable_keys:
            return {}

        existing_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        columns = [getattr(self.model_cls, field) for field in self.unique_fields]
        selected_columns = [getattr(self.model_cls, id_field), *columns]
        if hasattr(self.model_cls, "clean_hash"):
            selected_columns.append(getattr(self.model_cls, "clean_hash"))

        for key_chunk in _chunks(searchable_keys, 500):
            stmt = (
                select(*selected_columns)
                .where(self.model_cls.project_id == self.project_id)
                .where(self.model_cls.category_code == self.category_code.value)
            )
            if len(columns) == 1:
                stmt = stmt.where(columns[0].in_([key[0] for key in key_chunk]))
            else:
                stmt = stmt.where(tuple_(*columns).in_(key_chunk))
            for row in self.db.execute(stmt).mappings():
                key = tuple(row[field] for field in self.unique_fields)
                existing_by_key[key] = dict(row)
        return existing_by_key

    def _unique_key(self, payload: Mapping[str, Any]) -> tuple[Any, ...]:
        return tuple(payload.get(field) for field in self.unique_fields)

    def _with_project_defaults(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        normalized_payload.setdefault("project_id", self.project_id)
        normalized_payload.setdefault("category_code", self.category_code.value)
        return normalized_payload

    @staticmethod
    def _model_payload(model_cls: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in payload.items() if key in model_fields}

    def _find_by_lookup(self, model_cls: Any, lookup: Mapping[str, Any]) -> Any | None:
        stmt = select(model_cls)
        for field, value in lookup.items():
            column = getattr(model_cls, field)
            stmt = stmt.where(column.is_(None) if value is None else column == value)
        return self.db.execute(stmt).scalars().first()

    def _update_existing(self, existing: Any, payload: Mapping[str, Any]) -> None:
        jsonable_payload = _jsonable(payload)
        for column in existing.__table__.columns:
            if column.primary_key or column.name == "created_at":
                continue
            if column.name in jsonable_payload:
                setattr(existing, column.name, jsonable_payload[column.name])
        self.db.flush()


class CleanSkuRepository(_CleanFactRepository):
    model_cls = Core3CleanSku
    unique_fields = ("batch_id", "sku_code")

    def save_sku(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        return self._save_clean_fact(payload)

    def save_skus(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        return self._bulk_upsert_clean_facts(payloads, id_field="clean_sku_id")

    def list_clean_skus(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        quality_status: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3CleanSku]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset)
        stmt = (
            select(Core3CleanSku)
            .where(Core3CleanSku.project_id == self.project_id)
            .where(Core3CleanSku.category_code == self.category_code.value)
            .where(Core3CleanSku.batch_id == batch_id)
            .order_by(Core3CleanSku.sku_code)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if sku_code is not None:
            stmt = stmt.where(Core3CleanSku.sku_code == sku_code)
        if quality_status is not None:
            stmt = stmt.where(Core3CleanSku.quality_status == quality_status)
        if review_required is not None:
            stmt = stmt.where(Core3CleanSku.review_required == review_required)
        return list(self.db.execute(stmt).scalars())


class CleanMarketRepository(_CleanFactRepository):
    model_cls = Core3CleanMarketWeekly
    unique_fields = ("batch_id", "source_row_id")

    def save_market(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        return self._save_clean_fact(payload)

    def save_markets(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        return self._bulk_upsert_clean_facts(payloads, id_field="clean_market_id")


class CleanAttributeRepository(_CleanFactRepository):
    model_cls = Core3CleanAttribute
    unique_fields = ("batch_id", "source_row_id")

    def save_attribute(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        return self._save_clean_fact(payload)

    def save_attributes(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        return self._bulk_upsert_clean_facts(payloads, id_field="clean_attribute_id")


class CleanClaimRepository(_CleanFactRepository):
    def save_claim(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanClaim
        self.unique_fields = ("batch_id", "source_row_id")
        return self._save_clean_fact(payload)

    def save_claims(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        self.model_cls = Core3CleanClaim
        self.unique_fields = ("batch_id", "source_row_id")
        return self._bulk_upsert_clean_facts(payloads, id_field="clean_claim_id")

    def save_claim_sentence(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanClaimSentence
        self.unique_fields = ("batch_id", "source_row_id", "sentence_seq")
        return self._save_clean_fact(payload)

    def save_claim_sentences(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        self.model_cls = Core3CleanClaimSentence
        self.unique_fields = ("batch_id", "source_row_id", "sentence_seq")
        return self._bulk_upsert_clean_facts(payloads, id_field="claim_sentence_id")


class CleanCommentRepository(_CleanFactRepository):
    def save_comment(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanComment
        self.unique_fields = ("batch_id", "source_row_id")
        return self._save_clean_fact(payload)

    def save_comments(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        self.model_cls = Core3CleanComment
        self.unique_fields = ("batch_id", "source_row_id")
        return self._bulk_upsert_clean_facts(payloads, id_field="clean_comment_id")

    def save_comment_sentence(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanCommentSentence
        self.unique_fields = ("batch_id", "source_row_id", "sentence_source", "sentence_seq")
        return self._save_clean_fact(payload)

    def save_comment_sentences(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        self.model_cls = Core3CleanCommentSentence
        self.unique_fields = ("batch_id", "source_row_id", "sentence_source", "sentence_seq")
        return self._bulk_upsert_clean_facts(payloads, id_field="comment_sentence_id")

    def save_comment_dimension(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanCommentDimension
        self.unique_fields = ("batch_id", "source_row_id")
        return self._save_clean_fact(payload)

    def save_comment_dimensions(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        self.model_cls = Core3CleanCommentDimension
        self.unique_fields = ("batch_id", "source_row_id")
        return self._bulk_upsert_clean_facts(payloads, id_field="comment_dimension_id")


class DataQualityIssueRepository(_CleanFactRepository):
    model_cls = Core3DataQualityIssue
    unique_fields = ("batch_id", "domain", "issue_type", "source_row_id", "clean_record_key", "sku_code")

    def save_issue(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        normalized_payload = self._model_payload(Core3DataQualityIssue, self._with_project_defaults(payload))
        lookup = {field: normalized_payload.get(field) for field in self.unique_fields}
        existing = self._find_by_lookup(Core3DataQualityIssue, lookup)
        if existing is not None:
            self._update_existing(existing, normalized_payload)
            return CleanWriteResult(record=existing, created=False)

        issue = Core3DataQualityIssue(**_jsonable(normalized_payload))
        self.db.add(issue)
        self.db.flush()
        return CleanWriteResult(record=issue, created=True)

    def save_issues(self, payloads: Sequence[Mapping[str, Any]]) -> BulkCleanWriteResult:
        return self._bulk_upsert_clean_facts(payloads, id_field="issue_id")

    def list_quality_issues(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        domain: str | None = None,
        issue_type: str | None = None,
        severity: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3DataQualityIssue]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset)
        stmt = (
            select(Core3DataQualityIssue)
            .where(Core3DataQualityIssue.project_id == self.project_id)
            .where(Core3DataQualityIssue.category_code == self.category_code.value)
            .where(Core3DataQualityIssue.batch_id == batch_id)
            .order_by(Core3DataQualityIssue.created_at, Core3DataQualityIssue.issue_id)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if sku_code is not None:
            stmt = stmt.where(Core3DataQualityIssue.sku_code == sku_code)
        if domain is not None:
            stmt = stmt.where(Core3DataQualityIssue.domain == domain)
        if issue_type is not None:
            stmt = stmt.where(Core3DataQualityIssue.issue_type == issue_type)
        if severity is not None:
            stmt = stmt.where(Core3DataQualityIssue.severity == severity)
        if review_required is not None:
            stmt = stmt.where(Core3DataQualityIssue.review_required == review_required)
        return list(self.db.execute(stmt).scalars())


class CleaningQueryRepository(Core3BaseRepository):
    def get_clean_summary(self, batch_id: str) -> dict[str, Any]:
        clean_counts = {
            "sku": self._count(Core3CleanSku, batch_id),
            "market": self._count(Core3CleanMarketWeekly, batch_id),
            "attribute": self._count(Core3CleanAttribute, batch_id),
            "claim": self._count(Core3CleanClaim, batch_id),
            "claim_sentence": self._count(Core3CleanClaimSentence, batch_id),
            "comment": self._count(Core3CleanComment, batch_id),
            "comment_sentence": self._count(Core3CleanCommentSentence, batch_id),
            "comment_dimension": self._count(Core3CleanCommentDimension, batch_id),
            "quality_issue": self._count(Core3DataQualityIssue, batch_id),
        }
        issues = DataQualityIssueRepository(self.context).list_quality_issues(batch_id, limit=1000)
        issue_counts = {
            "info": sum(1 for issue in issues if issue.severity == "info"),
            "warning": sum(1 for issue in issues if issue.severity == "warning"),
            "error": sum(1 for issue in issues if issue.severity == "error"),
            "review_required": sum(1 for issue in issues if issue.review_required),
            "by_type": _count_by([issue.issue_type for issue in issues]),
        }
        return {
            "batch_id": batch_id,
            "clean_counts": clean_counts,
            "issue_counts": issue_counts,
            "review_required": issue_counts["review_required"] > 0,
        }

    def list_clean_skus(self, batch_id: str, **filters: Any) -> list[Core3CleanSku]:
        return CleanSkuRepository(self.context).list_clean_skus(batch_id, **filters)

    def list_quality_issues(self, batch_id: str, **filters: Any) -> list[Core3DataQualityIssue]:
        return DataQualityIssueRepository(self.context).list_quality_issues(batch_id, **filters)

    def get_sku_clean_drilldown(self, batch_id: str, sku_code: str) -> dict[str, Any]:
        sku = CleanSkuRepository(self.context).list_clean_skus(batch_id, sku_code=sku_code, limit=1)
        return {
            "sku": sku[0] if sku else None,
            "market": self._list_by_sku(Core3CleanMarketWeekly, batch_id, sku_code),
            "attribute": self._list_by_sku(Core3CleanAttribute, batch_id, sku_code),
            "claim": self._list_by_sku(Core3CleanClaim, batch_id, sku_code),
            "comment": self._list_by_sku(Core3CleanComment, batch_id, sku_code),
            "quality_issues": self.list_quality_issues(batch_id, sku_code=sku_code),
        }

    def _count(self, model_cls: Any, batch_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )
        return int(self.db.execute(stmt).scalar_one())

    def _list_by_sku(self, model_cls: Any, batch_id: str, sku_code: str) -> list[Any]:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
            .where(model_cls.sku_code == sku_code)
        )
        return list(self.db.execute(stmt).scalars())


def _operation_values(operation_types: Sequence[Core3SourceOperationType | str] | None) -> tuple[str, ...]:
    source = operation_types or DEFAULT_M01_OPERATION_TYPES
    return tuple(item.value if hasattr(item, "value") else str(item) for item in source)


def _unique_non_empty_values(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _key_has_null(key: tuple[Any, ...]) -> bool:
    return any(value is None for value in key)


def _chunks(values: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _count_by(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
