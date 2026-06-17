"""M03 parameter extraction repositories."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from app.models import entities
from app.services.core3_real_data.constants import Core3EvidenceStatus, Core3EvidenceType
from app.services.core3_real_data.repositories import Core3BaseRepository


M03_PARAM_EVIDENCE_TYPES: tuple[str, ...] = (
    Core3EvidenceType.PARAM_RAW.value,
    Core3EvidenceType.PROMO_SENTENCE.value,
    Core3EvidenceType.QUALITY_ISSUE.value,
)


class ParamRepositoryHashConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParamRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int
    reused_count: int


class ParamEvidenceReader(Core3BaseRepository):
    """Read only M02 evidence types that M03 is allowed to consume."""

    allowed_evidence_types = M03_PARAM_EVIDENCE_TYPES

    def list_param_evidence(
        self,
        batch_id: str,
        *,
        target_sku_codes: Sequence[str] = (),
        limit: int = 100000,
        offset: int = 0,
    ) -> list[entities.Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        stmt = (
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type.in_(self.allowed_evidence_types))
            .order_by(
                entities.Core3EvidenceAtom.sku_code,
                entities.Core3EvidenceAtom.evidence_type,
                entities.Core3EvidenceAtom.evidence_field,
                entities.Core3EvidenceAtom.evidence_id,
            )
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if target_sku_codes:
            stmt = stmt.where(entities.Core3EvidenceAtom.sku_code.in_(tuple(target_sku_codes)))
        return list(self.db.execute(stmt).scalars())


class ParamExtractionRepository(Core3BaseRepository):
    """Write and query M03 parameter extraction tables."""

    def save_field_profiles(
        self,
        profiles: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ParamFieldProfile,
            profiles,
            unique_fields=("batch_id", "clean_param_name", "seed_version", "rule_version"),
            hash_field="field_profile_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_param_values(
        self,
        values: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ExtractParamValue,
            values,
            unique_fields=("batch_id", "sku_code", "param_code", "source_type", "primary_evidence_id", "rule_version"),
            hash_field="param_value_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_alias_candidates(
        self,
        candidates: Sequence[Any],
        *,
        replace_existing: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ParamAliasCandidate,
            candidates,
            unique_fields=("batch_id", "clean_param_name", "seed_version"),
            hash_field=None,
            replace_existing=replace_existing,
        )

    def save_param_conflicts(
        self,
        conflicts: Sequence[Any],
        *,
        replace_existing: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ParamValueConflict,
            conflicts,
            unique_fields=("batch_id", "sku_code", "param_code", "conflict_type", "rule_version"),
            hash_field=None,
            replace_existing=replace_existing,
        )

    def save_sku_param_profiles(
        self,
        profiles: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuParamProfile,
            profiles,
            unique_fields=("batch_id", "sku_code", "seed_version", "rule_version"),
            hash_field="profile_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def list_field_profiles(
        self,
        batch_id: str,
        *,
        matched: bool | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ParamFieldProfile]:
        stmt = self._base_query(entities.Core3ParamFieldProfile, batch_id).order_by(
            entities.Core3ParamFieldProfile.clean_param_name,
            entities.Core3ParamFieldProfile.field_profile_id,
        )
        if matched is True:
            stmt = stmt.where(entities.Core3ParamFieldProfile.matched_param_code.is_not(None))
        elif matched is False:
            stmt = stmt.where(entities.Core3ParamFieldProfile.matched_param_code.is_(None))
        if review_required is not None:
            stmt = stmt.where(entities.Core3ParamFieldProfile.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_param_values(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        param_code: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ExtractParamValue]:
        stmt = self._base_query(entities.Core3ExtractParamValue, batch_id).order_by(
            entities.Core3ExtractParamValue.sku_code,
            entities.Core3ExtractParamValue.param_code,
            entities.Core3ExtractParamValue.source_priority_rank,
            entities.Core3ExtractParamValue.param_value_id,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3ExtractParamValue.sku_code == sku_code)
        if param_code is not None:
            stmt = stmt.where(entities.Core3ExtractParamValue.param_code == param_code)
        if review_required is not None:
            stmt = stmt.where(entities.Core3ExtractParamValue.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_alias_candidates(
        self,
        batch_id: str,
        *,
        review_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ParamAliasCandidate]:
        stmt = self._base_query(entities.Core3ParamAliasCandidate, batch_id).order_by(
            entities.Core3ParamAliasCandidate.clean_param_name,
            entities.Core3ParamAliasCandidate.alias_candidate_id,
        )
        if review_status is not None:
            stmt = stmt.where(entities.Core3ParamAliasCandidate.review_status == review_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_param_conflicts(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        param_code: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ParamValueConflict]:
        stmt = self._base_query(entities.Core3ParamValueConflict, batch_id).order_by(
            entities.Core3ParamValueConflict.sku_code,
            entities.Core3ParamValueConflict.param_code,
            entities.Core3ParamValueConflict.conflict_type,
            entities.Core3ParamValueConflict.conflict_id,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3ParamValueConflict.sku_code == sku_code)
        if param_code is not None:
            stmt = stmt.where(entities.Core3ParamValueConflict.param_code == param_code)
        if review_required is not None:
            stmt = stmt.where(entities.Core3ParamValueConflict.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def get_sku_param_profile(
        self,
        batch_id: str,
        sku_code: str,
    ) -> entities.Core3SkuParamProfile | None:
        stmt = (
            self._base_query(entities.Core3SkuParamProfile, batch_id)
            .where(entities.Core3SkuParamProfile.sku_code == sku_code)
            .order_by(entities.Core3SkuParamProfile.updated_at.desc(), entities.Core3SkuParamProfile.sku_param_profile_id)
        )
        return self.db.execute(stmt).scalars().first()

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool = False,
    ) -> ParamRepositoryWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        for payload in payloads:
            record, created = self._save_one(
                model_cls,
                payload,
                unique_fields=unique_fields,
                hash_field=hash_field,
                replace_existing=replace_existing,
            )
            records.append(record)
            if created:
                created_count += 1
            else:
                reused_count += 1
        return ParamRepositoryWriteResult(
            records=tuple(records),
            created_count=created_count,
            reused_count=reused_count,
        )

    def _save_one(
        self,
        model_cls: Any,
        payload: Any,
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool = False,
    ) -> tuple[Any, bool]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is not None:
            if replace_existing:
                self._update_existing(existing, normalized_payload)
                self.db.flush()
                return existing, False
            self._assert_same_hash(
                existing,
                normalized_payload,
                hash_field=hash_field,
                unique_fields=unique_fields,
                model_name=model_cls.__tablename__,
            )
            return existing, False

        record = model_cls(**_jsonable(normalized_payload))
        self.db.add(record)
        self.db.flush()
        return record, True

    @staticmethod
    def _update_existing(existing: Any, payload: Mapping[str, Any]) -> None:
        primary_keys = {column.name for column in existing.__table__.primary_key.columns}
        immutable_fields = primary_keys | {"created_at"}
        for field_name, field_value in _jsonable(payload).items():
            if field_name in immutable_fields:
                continue
            if hasattr(existing, field_name):
                setattr(existing, field_name, field_value)

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if hasattr(payload, "to_record_payload"):
            raw_payload = payload.to_record_payload()
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M03 repository payload must be a mapping or provide to_record_payload()")

        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in raw_payload.items() if key in model_fields}

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = select(model_cls).where(model_cls.project_id == self.project_id).where(
            model_cls.category_code == self.category_code.value
        )
        for field_name in unique_fields:
            field_value = payload.get(field_name)
            if field_value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required for idempotent write")
            stmt = stmt.where(getattr(model_cls, field_name) == field_value)
        return self.db.execute(stmt).scalars().first()

    @staticmethod
    def _assert_same_hash(
        existing: Any,
        payload: Mapping[str, Any],
        *,
        hash_field: str | None,
        unique_fields: tuple[str, ...],
        model_name: str,
    ) -> None:
        if hash_field is None:
            return
        incoming_hash = payload.get(hash_field)
        existing_hash = getattr(existing, hash_field)
        if incoming_hash != existing_hash:
            unique_key = {field_name: payload.get(field_name) for field_name in unique_fields}
            raise ParamRepositoryHashConflictError(
                f"{model_name} unique key already exists with different {hash_field}: {unique_key}"
            )

    def _base_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
