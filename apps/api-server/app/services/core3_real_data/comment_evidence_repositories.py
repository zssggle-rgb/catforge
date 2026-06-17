"""M05 comment evidence persistence repositories."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


@dataclass(frozen=True)
class CommentEvidenceRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class CommentEvidenceRepositoryError(RuntimeError):
    pass


class _M05RepositoryMixin(Core3BaseRepository):
    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> CommentEvidenceRepositoryWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        updated_count = 0
        for payload in payloads:
            record, status = self._save_one(
                model_cls,
                payload,
                unique_fields=unique_fields,
                hash_field=hash_field,
            )
            records.append(record)
            if status == "created":
                created_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                reused_count += 1
        return CommentEvidenceRepositoryWriteResult(
            records=tuple(records),
            created_count=created_count,
            reused_count=reused_count,
            updated_count=updated_count,
        )

    def _save_one(
        self,
        model_cls: Any,
        payload: Any,
        *,
        unique_fields: tuple[str, ...],
        hash_field: str,
    ) -> tuple[Any, str]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is None:
            record = model_cls(**_jsonable_payload(normalized_payload))
            self.db.add(record)
            self.db.flush()
            return record, "created"

        incoming_hash = normalized_payload.get(hash_field)
        if incoming_hash == getattr(existing, hash_field):
            _refresh_run_context(existing, normalized_payload)
            self.db.flush()
            return existing, "reused"

        _assign_existing(existing, normalized_payload)
        self.db.flush()
        return existing, "updated"

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw_payload = payload.model_dump(mode="python")
        elif hasattr(payload, "to_record_payload"):
            raw_payload = payload.to_record_payload()
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M05 repository payload must be a mapping, Pydantic model, or provide to_record_payload()")

        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        result = {key: value for key, value in raw_payload.items() if key in model_fields}
        for audit_field in ("created_at", "updated_at"):
            if result.get(audit_field) is None:
                result.pop(audit_field, None)
        return result

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
        )
        for field_name in unique_fields:
            field_value = payload.get(field_name)
            if field_value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required for idempotent write")
            stmt = stmt.where(getattr(model_cls, field_name) == field_value)
        return self.db.execute(stmt).scalars().first()

    def _base_current_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
            .where(model_cls.is_current.is_(True))
        )

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())

    def _mark_previous_inactive(self, model_cls: Any, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        records = list(
            self.db.execute(
                self._base_current_query(model_cls, batch_id)
                .where(model_cls.sku_code == sku_code)
                .where(model_cls.rule_version == rule_version)
            ).scalars()
        )
        for record in records:
            record.is_current = False
            record.processing_status = "inactive"
        self.db.flush()
        return len(records)


class CommentUnitRepository(_M05RepositoryMixin):
    def get_current_by_fingerprint(
        self,
        batch_id: str,
        sku_code: str,
        input_fingerprint: str,
    ) -> list[entities.Core3CommentUnit]:
        stmt = (
            self._base_current_query(entities.Core3CommentUnit, batch_id)
            .where(entities.Core3CommentUnit.sku_code == sku_code)
            .where(entities.Core3CommentUnit.input_fingerprint == input_fingerprint)
            .order_by(entities.Core3CommentUnit.comment_unit_key)
        )
        return list(self.db.execute(stmt).scalars())

    def bulk_upsert_comment_units(self, records: Sequence[Any]) -> CommentEvidenceRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentUnit,
            records,
            unique_fields=("batch_id", "comment_unit_key", "rule_version"),
        )

    def list_current_units(
        self,
        batch_id: str,
        sku_code: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentUnit]:
        stmt = (
            self._base_current_query(entities.Core3CommentUnit, batch_id)
            .where(entities.Core3CommentUnit.sku_code == sku_code)
            .order_by(entities.Core3CommentUnit.comment_unit_key, entities.Core3CommentUnit.comment_unit_id)
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def get_unit(self, comment_unit_id: str) -> entities.Core3CommentUnit | None:
        stmt = (
            select(entities.Core3CommentUnit)
            .where(entities.Core3CommentUnit.project_id == self.project_id)
            .where(entities.Core3CommentUnit.category_code == self.category_code.value)
            .where(entities.Core3CommentUnit.comment_unit_id == comment_unit_id)
        )
        return self.db.execute(stmt).scalars().first()

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3CommentUnit, batch_id, sku_code, rule_version=rule_version)


class CommentUnitEvidenceLinkRepository(_M05RepositoryMixin):
    def delete_current_links_for_sku(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        stmt = (
            delete(entities.Core3CommentUnitEvidenceLink)
            .where(entities.Core3CommentUnitEvidenceLink.project_id == self.project_id)
            .where(entities.Core3CommentUnitEvidenceLink.category_code == self.category_code.value)
            .where(entities.Core3CommentUnitEvidenceLink.batch_id == batch_id)
            .where(entities.Core3CommentUnitEvidenceLink.sku_code == sku_code)
            .where(entities.Core3CommentUnitEvidenceLink.rule_version == rule_version)
            .where(entities.Core3CommentUnitEvidenceLink.is_current.is_(True))
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return int(result.rowcount or 0)

    def bulk_insert_links(self, records: Sequence[Any]) -> CommentEvidenceRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentUnitEvidenceLink,
            records,
            unique_fields=("comment_unit_id", "source_evidence_id", "link_role", "rule_version"),
        )

    def list_links_by_unit(
        self,
        comment_unit_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentUnitEvidenceLink]:
        stmt = (
            select(entities.Core3CommentUnitEvidenceLink)
            .where(entities.Core3CommentUnitEvidenceLink.project_id == self.project_id)
            .where(entities.Core3CommentUnitEvidenceLink.category_code == self.category_code.value)
            .where(entities.Core3CommentUnitEvidenceLink.comment_unit_id == comment_unit_id)
            .where(entities.Core3CommentUnitEvidenceLink.is_current.is_(True))
            .order_by(
                entities.Core3CommentUnitEvidenceLink.link_role,
                entities.Core3CommentUnitEvidenceLink.source_evidence_id,
            )
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_links_by_source_evidence(
        self,
        source_evidence_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentUnitEvidenceLink]:
        stmt = (
            select(entities.Core3CommentUnitEvidenceLink)
            .where(entities.Core3CommentUnitEvidenceLink.project_id == self.project_id)
            .where(entities.Core3CommentUnitEvidenceLink.category_code == self.category_code.value)
            .where(entities.Core3CommentUnitEvidenceLink.source_evidence_id == source_evidence_id)
            .where(entities.Core3CommentUnitEvidenceLink.is_current.is_(True))
            .order_by(entities.Core3CommentUnitEvidenceLink.comment_unit_id)
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset)


class CommentEvidenceAtomRepository(_M05RepositoryMixin):
    def bulk_upsert_atoms(self, records: Sequence[Any]) -> CommentEvidenceRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentEvidenceAtom,
            records,
            unique_fields=("batch_id", "comment_evidence_key", "rule_version"),
        )

    def list_current_atoms(
        self,
        batch_id: str,
        sku_code: str,
        *,
        primary_domain_hint: str | None = None,
        sentiment_hint: str | None = None,
        low_value_flag: bool | None = None,
        usable_for_downstream: bool | None = None,
        topic_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentEvidenceAtom]:
        stmt = (
            self._base_current_query(entities.Core3CommentEvidenceAtom, batch_id)
            .where(entities.Core3CommentEvidenceAtom.sku_code == sku_code)
            .order_by(
                entities.Core3CommentEvidenceAtom.comment_unit_id,
                entities.Core3CommentEvidenceAtom.sentence_seq,
                entities.Core3CommentEvidenceAtom.comment_evidence_id,
            )
        )
        if primary_domain_hint is not None:
            stmt = stmt.where(entities.Core3CommentEvidenceAtom.primary_domain_hint == primary_domain_hint)
        if sentiment_hint is not None:
            stmt = stmt.where(entities.Core3CommentEvidenceAtom.sentiment_hint == sentiment_hint)
        if low_value_flag is not None:
            stmt = stmt.where(entities.Core3CommentEvidenceAtom.low_value_flag.is_(low_value_flag))
        if usable_for_downstream is not None:
            stmt = stmt.where(entities.Core3CommentEvidenceAtom.usable_for_downstream.is_(usable_for_downstream))
        if topic_code is not None:
            topic_subquery = (
                select(entities.Core3CommentTopicHint.comment_evidence_id)
                .where(entities.Core3CommentTopicHint.project_id == self.project_id)
                .where(entities.Core3CommentTopicHint.category_code == self.category_code.value)
                .where(entities.Core3CommentTopicHint.batch_id == batch_id)
                .where(entities.Core3CommentTopicHint.sku_code == sku_code)
                .where(entities.Core3CommentTopicHint.is_current.is_(True))
                .where(entities.Core3CommentTopicHint.topic_code == topic_code)
            )
            stmt = stmt.where(entities.Core3CommentEvidenceAtom.comment_evidence_id.in_(topic_subquery))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def count_usable_atoms(self, batch_id: str, sku_code: str) -> int:
        stmt = (
            select(func.count())
            .select_from(entities.Core3CommentEvidenceAtom)
            .where(entities.Core3CommentEvidenceAtom.project_id == self.project_id)
            .where(entities.Core3CommentEvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3CommentEvidenceAtom.batch_id == batch_id)
            .where(entities.Core3CommentEvidenceAtom.sku_code == sku_code)
            .where(entities.Core3CommentEvidenceAtom.is_current.is_(True))
            .where(entities.Core3CommentEvidenceAtom.usable_for_downstream.is_(True))
        )
        return int(self.db.execute(stmt).scalar_one())

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(
            entities.Core3CommentEvidenceAtom,
            batch_id,
            sku_code,
            rule_version=rule_version,
        )


class CommentTopicHintRepository(_M05RepositoryMixin):
    def bulk_upsert_topic_hints(self, records: Sequence[Any]) -> CommentEvidenceRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentTopicHint,
            records,
            unique_fields=("comment_evidence_id", "topic_code", "match_method", "rule_version"),
        )

    def list_current_topic_hints(
        self,
        batch_id: str,
        sku_code: str,
        *,
        topic_code: str | None = None,
        topic_group: str | None = None,
        polarity_hint: str | None = None,
        topic_hint_status: str | None = None,
        service_guardrail_flag: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentTopicHint]:
        stmt = (
            self._base_current_query(entities.Core3CommentTopicHint, batch_id)
            .where(entities.Core3CommentTopicHint.sku_code == sku_code)
            .order_by(
                entities.Core3CommentTopicHint.comment_evidence_id,
                entities.Core3CommentTopicHint.topic_code,
                entities.Core3CommentTopicHint.topic_hint_id,
            )
        )
        if topic_code is not None:
            stmt = stmt.where(entities.Core3CommentTopicHint.topic_code == topic_code)
        if topic_group is not None:
            stmt = stmt.where(entities.Core3CommentTopicHint.topic_group == topic_group)
        if polarity_hint is not None:
            stmt = stmt.where(entities.Core3CommentTopicHint.polarity_hint == polarity_hint)
        if topic_hint_status is not None:
            stmt = stmt.where(entities.Core3CommentTopicHint.topic_hint_status == topic_hint_status)
        if service_guardrail_flag is not None:
            stmt = stmt.where(entities.Core3CommentTopicHint.service_guardrail_flag.is_(service_guardrail_flag))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def aggregate_topic_distribution(self, batch_id: str, sku_code: str) -> dict[str, int]:
        records = self.list_current_topic_hints(batch_id, sku_code, limit=100000)
        counter = Counter(record.topic_code for record in records)
        return dict(sorted(counter.items()))

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3CommentTopicHint, batch_id, sku_code, rule_version=rule_version)


class CommentQualityProfileRepository(_M05RepositoryMixin):
    def upsert_profile(self, record: Any) -> CommentEvidenceRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentQualityProfile,
            [record],
            unique_fields=("batch_id", "sku_code", "rule_version", "asset_version"),
        )

    def get_current_profile(self, batch_id: str, sku_code: str) -> entities.Core3CommentQualityProfile | None:
        stmt = (
            self._base_current_query(entities.Core3CommentQualityProfile, batch_id)
            .where(entities.Core3CommentQualityProfile.sku_code == sku_code)
            .order_by(
                entities.Core3CommentQualityProfile.updated_at.desc(),
                entities.Core3CommentQualityProfile.comment_quality_profile_id,
            )
        )
        return self.db.execute(stmt).scalars().first()

    def list_profiles(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        downstream_ready: bool | None = None,
        review_required: bool | None = None,
        sample_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentQualityProfile]:
        stmt = self._base_current_query(entities.Core3CommentQualityProfile, batch_id).order_by(
            entities.Core3CommentQualityProfile.sku_code,
            entities.Core3CommentQualityProfile.comment_quality_profile_id,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3CommentQualityProfile.sku_code == sku_code)
        if downstream_ready is not None:
            stmt = stmt.where(entities.Core3CommentQualityProfile.downstream_ready.is_(downstream_ready))
        if review_required is not None:
            stmt = stmt.where(entities.Core3CommentQualityProfile.review_required.is_(review_required))
        if sample_status is not None:
            stmt = stmt.where(entities.Core3CommentQualityProfile.sample_status == sample_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_review_required_profiles(
        self,
        batch_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentQualityProfile]:
        return self.list_profiles(batch_id, review_required=True, limit=limit, offset=offset)

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(
            entities.Core3CommentQualityProfile,
            batch_id,
            sku_code,
            rule_version=rule_version,
        )


class CommentEvidenceReadRepository(
    CommentUnitRepository,
    CommentUnitEvidenceLinkRepository,
    CommentEvidenceAtomRepository,
    CommentTopicHintRepository,
    CommentQualityProfileRepository,
):
    """Combined read/write boundary for runner and API composition."""


def _assign_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    for key, value in _jsonable_payload(payload).items():
        if key in primary_keys or key == "created_at":
            continue
        setattr(existing, key, value)
    if hasattr(existing, "is_current"):
        existing.is_current = True


def _refresh_run_context(existing: Any, payload: Mapping[str, Any]) -> None:
    for key in ("run_id", "module_run_id", "input_fingerprint", "processing_status"):
        if key in payload:
            setattr(existing, key, payload[key])
    if hasattr(existing, "is_current"):
        existing.is_current = True


def _jsonable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Mapping | list | tuple):
            result[key] = _jsonable_item(value)
        elif isinstance(value, Enum):
            result[key] = value.value
        elif isinstance(value, datetime):
            result[key] = value
        else:
            result[key] = value
    return result


def _jsonable_item(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable_item(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable_item(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable_item(item) for item in value]
    return value

