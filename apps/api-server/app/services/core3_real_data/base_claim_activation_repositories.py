"""M04a base claim activation repositories."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from app.models import entities
from app.services.core3_real_data.constants import Core3EvidenceStatus, Core3EvidenceType
from app.services.core3_real_data.repositories import Core3BaseRepository


M04A_ALLOWED_EVIDENCE_TYPES: tuple[str, ...] = (
    Core3EvidenceType.PROMO_RAW.value,
    Core3EvidenceType.PROMO_SENTENCE.value,
    Core3EvidenceType.PARAM_RAW.value,
    Core3EvidenceType.QUALITY_ISSUE.value,
)


class ClaimActivationRepositoryHashConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimActivationRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int
    reused_count: int


class ClaimEvidenceReader(Core3BaseRepository):
    """Read only M02 evidence types that M04a is allowed to consume."""

    allowed_evidence_types = M04A_ALLOWED_EVIDENCE_TYPES

    def list_claim_evidence(
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


class SkuParamProfileReader(Core3BaseRepository):
    """Read current M03 SKU parameter profiles for M04a."""

    def list_sku_param_profiles(
        self,
        batch_id: str,
        *,
        target_sku_codes: Sequence[str] = (),
        limit: int = 100000,
        offset: int = 0,
    ) -> list[entities.Core3SkuParamProfile]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .order_by(
                entities.Core3SkuParamProfile.sku_code,
                entities.Core3SkuParamProfile.updated_at.desc(),
                entities.Core3SkuParamProfile.sku_param_profile_id,
            )
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if target_sku_codes:
            stmt = stmt.where(entities.Core3SkuParamProfile.sku_code.in_(tuple(target_sku_codes)))
        return list(self.db.execute(stmt).scalars())

    def get_sku_param_profile(self, batch_id: str, sku_code: str) -> entities.Core3SkuParamProfile | None:
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.sku_code == sku_code)
            .order_by(
                entities.Core3SkuParamProfile.updated_at.desc(),
                entities.Core3SkuParamProfile.sku_param_profile_id,
            )
        )
        return self.db.execute(stmt).scalars().first()


class ClaimActivationRepository(Core3BaseRepository):
    """Write and query M04a claim activation tables."""

    def save_source_statuses(
        self,
        statuses: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ClaimActivationRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimSourceStatus,
            statuses,
            unique_fields=("batch_id", "sku_code", "seed_version", "rule_version"),
            hash_field="status_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_claim_hits(
        self,
        hits: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ClaimActivationRepositoryWriteResult:
        return self._save_many(
            entities.Core3ExtractClaimHit,
            hits,
            unique_fields=(
                "batch_id",
                "sku_code",
                "claim_code",
                "hit_source_type",
                "source_sentence_key",
                "rule_version",
            ),
            hash_field="hit_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_activation_bases(
        self,
        activations: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ClaimActivationRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimActivationBase,
            activations,
            unique_fields=("batch_id", "sku_code", "claim_code", "seed_version", "rule_version"),
            hash_field="activation_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def get_claim_source_status(
        self,
        batch_id: str,
        sku_code: str,
    ) -> entities.Core3SkuClaimSourceStatus | None:
        stmt = (
            self._base_query(entities.Core3SkuClaimSourceStatus, batch_id)
            .where(entities.Core3SkuClaimSourceStatus.sku_code == sku_code)
            .order_by(
                entities.Core3SkuClaimSourceStatus.updated_at.desc(),
                entities.Core3SkuClaimSourceStatus.claim_source_status_id,
            )
        )
        return self.db.execute(stmt).scalars().first()

    def list_claim_source_statuses(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        claim_source_status: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimSourceStatus]:
        stmt = self._base_query(entities.Core3SkuClaimSourceStatus, batch_id).order_by(
            entities.Core3SkuClaimSourceStatus.sku_code,
            entities.Core3SkuClaimSourceStatus.claim_source_status_id,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimSourceStatus.sku_code == sku_code)
        if claim_source_status is not None:
            stmt = stmt.where(entities.Core3SkuClaimSourceStatus.claim_source_status == claim_source_status)
        if review_required is not None:
            stmt = stmt.where(entities.Core3SkuClaimSourceStatus.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_claim_hits(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        claim_code: str | None = None,
        hit_source_type: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ExtractClaimHit]:
        stmt = self._base_query(entities.Core3ExtractClaimHit, batch_id).order_by(
            entities.Core3ExtractClaimHit.sku_code,
            entities.Core3ExtractClaimHit.claim_code,
            entities.Core3ExtractClaimHit.source_sentence_key,
            entities.Core3ExtractClaimHit.claim_hit_id,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3ExtractClaimHit.sku_code == sku_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3ExtractClaimHit.claim_code == claim_code)
        if hit_source_type is not None:
            stmt = stmt.where(entities.Core3ExtractClaimHit.hit_source_type == hit_source_type)
        if review_required is not None:
            stmt = stmt.where(entities.Core3ExtractClaimHit.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_base_claims(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        claim_code: str | None = None,
        activation_basis: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimActivationBase]:
        stmt = self._base_query(entities.Core3SkuClaimActivationBase, batch_id).order_by(
            entities.Core3SkuClaimActivationBase.sku_code,
            entities.Core3SkuClaimActivationBase.claim_code,
            entities.Core3SkuClaimActivationBase.claim_activation_base_id,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivationBase.sku_code == sku_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivationBase.claim_code == claim_code)
        if activation_basis is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivationBase.activation_basis == activation_basis)
        if review_required is not None:
            stmt = stmt.where(entities.Core3SkuClaimActivationBase.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_param_only_claims(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimActivationBase]:
        return self.list_base_claims(
            batch_id,
            sku_code=sku_code,
            activation_basis="param_only",
            limit=limit,
            offset=offset,
        )

    def list_claims_requiring_review(
        self,
        batch_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimActivationBase]:
        return self.list_base_claims(
            batch_id,
            review_required=True,
            limit=limit,
            offset=offset,
        )

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str | None,
        replace_existing: bool = False,
    ) -> ClaimActivationRepositoryWriteResult:
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
        return ClaimActivationRepositoryWriteResult(
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
            raise TypeError("M04a repository payload must be a mapping or provide to_record_payload()")

        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in raw_payload.items() if key in model_fields}

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
            raise ClaimActivationRepositoryHashConflictError(
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


def _jsonable(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Enum):
            result[key] = value.value
        elif isinstance(value, Decimal):
            result[key] = value
        elif isinstance(value, list):
            result[key] = [_jsonable_item(item) for item in value]
        elif isinstance(value, tuple):
            result[key] = [_jsonable_item(item) for item in value]
        elif isinstance(value, Mapping):
            result[key] = {str(inner_key): _jsonable_item(inner_value) for inner_key, inner_value in value.items()}
        else:
            result[key] = value
    return result


def _jsonable_item(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable_item(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable_item(item) for item in value]
    return value
