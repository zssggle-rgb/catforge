"""M04b claim comment enhancement repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.constants import CommentSignalType
from app.services.core3_real_data.repositories import Core3BaseRepository


@dataclass(frozen=True)
class ClaimCommentRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class M04bInputBlockedError(RuntimeError):
    pass


class _M04bRepositoryMixin(Core3BaseRepository):
    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> ClaimCommentRepositoryWriteResult:
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
        return ClaimCommentRepositoryWriteResult(
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
            _refresh_existing(existing, normalized_payload)
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
            raise TypeError("M04b repository payload must be a mapping or Pydantic model")

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

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
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
                self._current_query(model_cls, batch_id)
                .where(model_cls.sku_code == sku_code)
                .where(model_cls.rule_version == rule_version)
            ).scalars()
        )
        for record in records:
            record.is_current = False
            record.processing_status = "inactive"
        self.db.flush()
        return len(records)


class M04bClaimBaseRepository(_M04bRepositoryMixin):
    def assert_m04a_completed(self, batch_id: str) -> None:
        base_count = self.db.execute(
            select(func.count())
            .select_from(entities.Core3SkuClaimActivationBase)
            .where(entities.Core3SkuClaimActivationBase.project_id == self.project_id)
            .where(entities.Core3SkuClaimActivationBase.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimActivationBase.batch_id == batch_id)
        ).scalar_one()
        if int(base_count) == 0:
            raise M04bInputBlockedError("M04a base claim activations are required before M04b")

    def list_source_statuses(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[entities.Core3SkuClaimSourceStatus]:
        stmt = (
            select(entities.Core3SkuClaimSourceStatus)
            .where(entities.Core3SkuClaimSourceStatus.project_id == self.project_id)
            .where(entities.Core3SkuClaimSourceStatus.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimSourceStatus.batch_id == batch_id)
            .order_by(entities.Core3SkuClaimSourceStatus.sku_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuClaimSourceStatus.sku_code.in_(list(sku_scope)))
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_base_claims(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        claim_scope: Sequence[str] = (),
    ) -> list[entities.Core3SkuClaimActivationBase]:
        stmt = (
            select(entities.Core3SkuClaimActivationBase)
            .where(entities.Core3SkuClaimActivationBase.project_id == self.project_id)
            .where(entities.Core3SkuClaimActivationBase.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimActivationBase.batch_id == batch_id)
            .order_by(entities.Core3SkuClaimActivationBase.sku_code, entities.Core3SkuClaimActivationBase.claim_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuClaimActivationBase.sku_code.in_(list(sku_scope)))
        if claim_scope:
            stmt = stmt.where(entities.Core3SkuClaimActivationBase.claim_code.in_(list(claim_scope)))
        return self._paged_scalars(stmt, limit=100000, offset=0)


class M04bClaimValidationSignalRepository(_M04bRepositoryMixin):
    def assert_m06_completed(self, batch_id: str) -> None:
        signal_count = self.db.execute(
            select(func.count())
            .select_from(entities.Core3CommentDownstreamSignal)
            .where(entities.Core3CommentDownstreamSignal.project_id == self.project_id)
            .where(entities.Core3CommentDownstreamSignal.category_code == self.category_code.value)
            .where(entities.Core3CommentDownstreamSignal.batch_id == batch_id)
            .where(entities.Core3CommentDownstreamSignal.is_current.is_(True))
            .where(entities.Core3CommentDownstreamSignal.signal_type == CommentSignalType.CLAIM_VALIDATION.value)
        ).scalar_one()
        if int(signal_count) == 0:
            raise M04bInputBlockedError("M06 claim_validation signals are required before M04b")

    def list_claim_validation_signals(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        claim_scope: Sequence[str] = (),
    ) -> list[entities.Core3CommentDownstreamSignal]:
        stmt = (
            self._current_query(entities.Core3CommentDownstreamSignal, batch_id)
            .where(entities.Core3CommentDownstreamSignal.signal_type == CommentSignalType.CLAIM_VALIDATION.value)
            .where(entities.Core3CommentDownstreamSignal.target_code_hint.like("CLAIM_%"))
            .order_by(
                entities.Core3CommentDownstreamSignal.sku_code,
                entities.Core3CommentDownstreamSignal.target_code_hint,
                entities.Core3CommentDownstreamSignal.polarity,
            )
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3CommentDownstreamSignal.sku_code.in_(list(sku_scope)))
        if claim_scope:
            stmt = stmt.where(entities.Core3CommentDownstreamSignal.target_code_hint.in_(list(claim_scope)))
        return self._paged_scalars(stmt, limit=100000, offset=0)


class SkuClaimCommentValidationRepository(_M04bRepositoryMixin):
    def bulk_upsert_validations(self, records: Sequence[Any]) -> ClaimCommentRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimCommentValidation,
            records,
            unique_fields=("batch_id", "sku_code", "claim_code", "rule_version", "seed_version"),
        )

    def list_current_validations(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        claim_code: str | None = None,
        comment_effect: str | None = None,
        perception_status: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimCommentValidation]:
        stmt = self._current_query(entities.Core3SkuClaimCommentValidation, batch_id).order_by(
            entities.Core3SkuClaimCommentValidation.sku_code,
            entities.Core3SkuClaimCommentValidation.claim_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimCommentValidation.sku_code == sku_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimCommentValidation.claim_code == claim_code)
        if comment_effect is not None:
            stmt = stmt.where(entities.Core3SkuClaimCommentValidation.comment_effect == comment_effect)
        if perception_status is not None:
            stmt = stmt.where(entities.Core3SkuClaimCommentValidation.perception_status == perception_status)
        if review_required is not None:
            stmt = stmt.where(entities.Core3SkuClaimCommentValidation.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3SkuClaimCommentValidation, batch_id, sku_code, rule_version=rule_version)


class SkuClaimActivationRepository(_M04bRepositoryMixin):
    def bulk_upsert_activations(self, records: Sequence[Any]) -> ClaimCommentRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimActivation,
            records,
            unique_fields=("batch_id", "sku_code", "claim_code", "rule_version", "seed_version"),
        )

    def list_current_activations(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        claim_code: str | None = None,
        activation_level: str | None = None,
        activation_basis: str | None = None,
        perception_status: str | None = None,
        missing_structured_claim_flag: bool | None = None,
        param_only_flag: bool | None = None,
        comment_only_flag: bool | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimActivation]:
        stmt = self._current_query(entities.Core3SkuClaimActivation, batch_id).order_by(
            entities.Core3SkuClaimActivation.sku_code,
            entities.Core3SkuClaimActivation.final_activation_score.desc(),
            entities.Core3SkuClaimActivation.claim_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.sku_code == sku_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.claim_code == claim_code)
        if activation_level is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.activation_level == activation_level)
        if activation_basis is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.activation_basis == activation_basis)
        if perception_status is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.perception_status == perception_status)
        if missing_structured_claim_flag is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.missing_structured_claim_flag.is_(missing_structured_claim_flag))
        if param_only_flag is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.param_only_flag.is_(param_only_flag))
        if comment_only_flag is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.comment_only_flag.is_(comment_only_flag))
        if review_required is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivation.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def get_activation(self, claim_activation_id: str) -> entities.Core3SkuClaimActivation | None:
        stmt = (
            select(entities.Core3SkuClaimActivation)
            .where(entities.Core3SkuClaimActivation.project_id == self.project_id)
            .where(entities.Core3SkuClaimActivation.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimActivation.claim_activation_id == claim_activation_id)
            .where(entities.Core3SkuClaimActivation.is_current.is_(True))
        )
        return self.db.execute(stmt).scalars().first()

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3SkuClaimActivation, batch_id, sku_code, rule_version=rule_version)


class ClaimCommentReviewIssueRepository(_M04bRepositoryMixin):
    def bulk_upsert_issues(self, records: Sequence[Any]) -> ClaimCommentRepositoryWriteResult:
        return self._save_many(
            entities.Core3ClaimCommentReviewIssue,
            records,
            unique_fields=("batch_id", "sku_code", "claim_code", "issue_type", "rule_version", "seed_version"),
        )

    def list_current_issues(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        claim_code: str | None = None,
        issue_type: str | None = None,
        severity: str | None = None,
        issue_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ClaimCommentReviewIssue]:
        stmt = self._current_query(entities.Core3ClaimCommentReviewIssue, batch_id).order_by(
            entities.Core3ClaimCommentReviewIssue.sku_code,
            entities.Core3ClaimCommentReviewIssue.claim_code,
            entities.Core3ClaimCommentReviewIssue.issue_type,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3ClaimCommentReviewIssue.sku_code == sku_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3ClaimCommentReviewIssue.claim_code == claim_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3ClaimCommentReviewIssue.issue_type == issue_type)
        if severity is not None:
            stmt = stmt.where(entities.Core3ClaimCommentReviewIssue.severity == severity)
        if issue_status is not None:
            stmt = stmt.where(entities.Core3ClaimCommentReviewIssue.issue_status == issue_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def mark_previous_inactive(self, batch_id: str, sku_code: str, *, rule_version: str) -> int:
        return self._mark_previous_inactive(entities.Core3ClaimCommentReviewIssue, batch_id, sku_code, rule_version=rule_version)


class ClaimCommentEnhancementRepository(
    M04bClaimBaseRepository,
    M04bClaimValidationSignalRepository,
    SkuClaimCommentValidationRepository,
    SkuClaimActivationRepository,
    ClaimCommentReviewIssueRepository,
):
    """Combined M04b persistence boundary for runner and API."""


def _assign_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    for key, value in _jsonable_payload(payload).items():
        if key in primary_keys or key == "created_at":
            continue
        setattr(existing, key, value)
    if hasattr(existing, "is_current"):
        existing.is_current = True


def _refresh_existing(existing: Any, payload: Mapping[str, Any]) -> None:
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
