"""M06 comment downstream signal repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


@dataclass(frozen=True)
class CommentSignalRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class M06InputBlockedError(RuntimeError):
    pass


class _M06RepositoryMixin(Core3BaseRepository):
    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> CommentSignalRepositoryWriteResult:
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
        return CommentSignalRepositoryWriteResult(
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
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M06 repository payload must be a mapping or Pydantic model")

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
            value = payload.get(field_name)
            if value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required")
            stmt = stmt.where(getattr(model_cls, field_name) == value)
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


class M06CommentInputRepository(_M06RepositoryMixin):
    def assert_m05_completed(self, batch_id: str) -> None:
        profile_count = self.db.execute(
            select(func.count())
            .select_from(entities.Core3CommentQualityProfile)
            .where(entities.Core3CommentQualityProfile.project_id == self.project_id)
            .where(entities.Core3CommentQualityProfile.category_code == self.category_code.value)
            .where(entities.Core3CommentQualityProfile.batch_id == batch_id)
            .where(entities.Core3CommentQualityProfile.is_current.is_(True))
        ).scalar_one()
        if int(profile_count) == 0:
            raise M06InputBlockedError("M05 comment quality profiles are required before M06")

    def list_ready_sku_codes(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[str]:
        stmt = (
            select(entities.Core3CommentQualityProfile.sku_code)
            .where(entities.Core3CommentQualityProfile.project_id == self.project_id)
            .where(entities.Core3CommentQualityProfile.category_code == self.category_code.value)
            .where(entities.Core3CommentQualityProfile.batch_id == batch_id)
            .where(entities.Core3CommentQualityProfile.is_current.is_(True))
            .where(entities.Core3CommentQualityProfile.downstream_ready.is_(True))
            .order_by(entities.Core3CommentQualityProfile.sku_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3CommentQualityProfile.sku_code.in_(list(sku_scope)))
        return [str(value) for value in self.db.execute(stmt).scalars()]

    def get_comment_quality_profile(self, batch_id: str, sku_code: str) -> entities.Core3CommentQualityProfile | None:
        stmt = (
            self._base_current_query(entities.Core3CommentQualityProfile, batch_id)
            .where(entities.Core3CommentQualityProfile.sku_code == sku_code)
            .order_by(entities.Core3CommentQualityProfile.updated_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def list_usable_comment_atoms(self, batch_id: str, sku_code: str) -> list[entities.Core3CommentEvidenceAtom]:
        stmt = (
            self._base_current_query(entities.Core3CommentEvidenceAtom, batch_id)
            .where(entities.Core3CommentEvidenceAtom.sku_code == sku_code)
            .where(entities.Core3CommentEvidenceAtom.usable_for_downstream.is_(True))
            .order_by(entities.Core3CommentEvidenceAtom.comment_unit_id, entities.Core3CommentEvidenceAtom.sentence_seq)
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_topic_hints_for_atoms(
        self,
        batch_id: str,
        sku_code: str,
        comment_evidence_ids: Sequence[str],
    ) -> list[entities.Core3CommentTopicHint]:
        if not comment_evidence_ids:
            return []
        stmt = (
            self._base_current_query(entities.Core3CommentTopicHint, batch_id)
            .where(entities.Core3CommentTopicHint.sku_code == sku_code)
            .where(entities.Core3CommentTopicHint.comment_evidence_id.in_(list(comment_evidence_ids)))
            .where(entities.Core3CommentTopicHint.topic_hint_status.in_(["matched", "low_confidence"]))
            .order_by(entities.Core3CommentTopicHint.comment_evidence_id, entities.Core3CommentTopicHint.topic_code)
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)


class CommentSignalCandidateRepository(_M06RepositoryMixin):
    def bulk_upsert_candidates(self, records: Sequence[Any]) -> CommentSignalRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentSignalCandidate,
            records,
            unique_fields=("batch_id", "signal_candidate_key", "rule_version", "asset_version"),
        )

    def list_current_candidates(
        self,
        batch_id: str,
        sku_code: str | None = None,
        *,
        signal_type: str | None = None,
        target_code_hint: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentSignalCandidate]:
        stmt = self._base_current_query(entities.Core3CommentSignalCandidate, batch_id).order_by(
            entities.Core3CommentSignalCandidate.sku_code,
            entities.Core3CommentSignalCandidate.signal_type,
            entities.Core3CommentSignalCandidate.target_code_hint,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3CommentSignalCandidate.sku_code == sku_code)
        if signal_type is not None:
            stmt = stmt.where(entities.Core3CommentSignalCandidate.signal_type == signal_type)
        if target_code_hint is not None:
            stmt = stmt.where(entities.Core3CommentSignalCandidate.target_code_hint == target_code_hint)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3CommentSignalCandidate, batch_id, sku_code, rule_version=rule_version)


class CommentDownstreamSignalRepository(_M06RepositoryMixin):
    def bulk_upsert_signals(self, records: Sequence[Any]) -> CommentSignalRepositoryWriteResult:
        return self._save_many(
            entities.Core3CommentDownstreamSignal,
            records,
            unique_fields=(
                "batch_id",
                "sku_code",
                "signal_type",
                "target_code_hint",
                "polarity",
                "rule_version",
                "asset_version",
            ),
        )

    def list_current_signals(
        self,
        batch_id: str,
        sku_code: str | None = None,
        *,
        signal_type: str | None = None,
        target_code_hint: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CommentDownstreamSignal]:
        stmt = self._base_current_query(entities.Core3CommentDownstreamSignal, batch_id).order_by(
            entities.Core3CommentDownstreamSignal.sku_code,
            entities.Core3CommentDownstreamSignal.signal_type,
            entities.Core3CommentDownstreamSignal.target_code_hint,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3CommentDownstreamSignal.sku_code == sku_code)
        if signal_type is not None:
            stmt = stmt.where(entities.Core3CommentDownstreamSignal.signal_type == signal_type)
        if target_code_hint is not None:
            stmt = stmt.where(entities.Core3CommentDownstreamSignal.target_code_hint == target_code_hint)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3CommentDownstreamSignal, batch_id, sku_code, rule_version=rule_version)


class SkuCommentSignalProfileRepository(_M06RepositoryMixin):
    def upsert_profile(self, record: Any) -> CommentSignalRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuCommentSignalProfile,
            [record],
            unique_fields=("batch_id", "sku_code", "rule_version", "asset_version"),
        )

    def get_current_profile(self, batch_id: str, sku_code: str) -> entities.Core3SkuCommentSignalProfile | None:
        stmt = (
            self._base_current_query(entities.Core3SkuCommentSignalProfile, batch_id)
            .where(entities.Core3SkuCommentSignalProfile.sku_code == sku_code)
            .order_by(entities.Core3SkuCommentSignalProfile.updated_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def list_profiles(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuCommentSignalProfile]:
        stmt = self._base_current_query(entities.Core3SkuCommentSignalProfile, batch_id).order_by(
            entities.Core3SkuCommentSignalProfile.sku_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuCommentSignalProfile.sku_code == sku_code)
        if review_required is not None:
            stmt = stmt.where(entities.Core3SkuCommentSignalProfile.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3SkuCommentSignalProfile, batch_id, sku_code, rule_version=rule_version)


class CommentDownstreamSignalReadRepository(
    M06CommentInputRepository,
    CommentSignalCandidateRepository,
    CommentDownstreamSignalRepository,
    SkuCommentSignalProfileRepository,
):
    """Combined M06 persistence boundary for runner and API."""


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
