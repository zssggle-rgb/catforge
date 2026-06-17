"""M01 cleaning-quality repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select

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
    ) -> list[Core3SourceRowRegistry]:
        normalized_operations = _operation_values(operation_types)
        if include_no_change and operation_types is None:
            normalized_operations = (*normalized_operations, Core3SourceOperationType.NO_CHANGE.value)

        stmt = (
            select(Core3SourceRowRegistry)
            .where(Core3SourceRowRegistry.project_id == self.project_id)
            .where(Core3SourceRowRegistry.category_code == self.category_code.value)
            .where(Core3SourceRowRegistry.batch_id == batch_id)
            .where(Core3SourceRowRegistry.operation_type.in_(normalized_operations))
            .order_by(Core3SourceRowRegistry.source_table, Core3SourceRowRegistry.source_pk)
        )
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


class CleanAttributeRepository(_CleanFactRepository):
    model_cls = Core3CleanAttribute
    unique_fields = ("batch_id", "source_row_id")

    def save_attribute(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        return self._save_clean_fact(payload)


class CleanClaimRepository(_CleanFactRepository):
    def save_claim(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanClaim
        self.unique_fields = ("batch_id", "source_row_id")
        return self._save_clean_fact(payload)

    def save_claim_sentence(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanClaimSentence
        self.unique_fields = ("batch_id", "source_row_id", "sentence_seq")
        return self._save_clean_fact(payload)


class CleanCommentRepository(_CleanFactRepository):
    def save_comment(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanComment
        self.unique_fields = ("batch_id", "source_row_id")
        return self._save_clean_fact(payload)

    def save_comment_sentence(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanCommentSentence
        self.unique_fields = ("batch_id", "source_row_id", "sentence_source", "sentence_seq")
        return self._save_clean_fact(payload)

    def save_comment_dimension(self, payload: Mapping[str, Any]) -> CleanWriteResult:
        self.model_cls = Core3CleanCommentDimension
        self.unique_fields = ("batch_id", "source_row_id")
        return self._save_clean_fact(payload)


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
