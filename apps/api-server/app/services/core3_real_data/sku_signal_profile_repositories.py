"""M08 SKU signal profile repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M08_FEATURE_VERSION,
    Core3EvidenceStatus,
    M07AnalysisWindow,
)
from app.services.core3_real_data.repositories import Core3BaseRepository


class M08InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class SkuSignalRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class _M08RepositoryMixin(Core3BaseRepository):
    def _base_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
        return self._base_query(model_cls, batch_id).where(model_cls.is_current.is_(True))

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> SkuSignalRepositoryWriteResult:
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
        return SkuSignalRepositoryWriteResult(
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
            raise TypeError("M08 repository payload must be a mapping or Pydantic model")
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


class M08InputRepository(_M08RepositoryMixin):
    """Read only upstream module outputs allowed by M08."""

    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M01 清洗 SKU": self._count_rows(entities.Core3CleanSku, batch_id),
            "M03 参数画像": self._count_rows(entities.Core3SkuParamProfile, batch_id),
            "M04b 卖点激活": self._count_current_rows(entities.Core3SkuClaimActivation, batch_id),
            "M06 评论信号画像": self._count_current_rows(entities.Core3SkuCommentSignalProfile, batch_id),
            "M07 市场画像": self._count_current_rows(entities.Core3SkuMarketProfile, batch_id),
            "M07 可比池": self._count_current_rows(entities.Core3ComparablePoolBaseline, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M08InputBlockedError(f"M08 需要先完成上游产物：{', '.join(missing)}。")

    def _count_rows(self, model_cls: Any, batch_id: str) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(model_cls.batch_id == batch_id)
            ).scalar_one()
        )

    def _count_current_rows(self, model_cls: Any, batch_id: str) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(model_cls.batch_id == batch_id)
                .where(model_cls.is_current.is_(True))
            ).scalar_one()
        )

    def list_clean_skus(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[entities.Core3CleanSku]:
        stmt = (
            self._base_query(entities.Core3CleanSku, batch_id)
            .order_by(entities.Core3CleanSku.sku_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3CleanSku.sku_code.in_(tuple(sku_scope)))
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_param_values(self, batch_id: str) -> list[entities.Core3ExtractParamValue]:
        stmt = (
            self._base_query(entities.Core3ExtractParamValue, batch_id)
            .order_by(
                entities.Core3ExtractParamValue.sku_code,
                entities.Core3ExtractParamValue.param_code,
                entities.Core3ExtractParamValue.source_priority_rank,
            )
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_param_profiles(self, batch_id: str) -> list[entities.Core3SkuParamProfile]:
        stmt = self._base_query(entities.Core3SkuParamProfile, batch_id).order_by(
            entities.Core3SkuParamProfile.sku_code,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_claim_activations(self, batch_id: str) -> list[entities.Core3SkuClaimActivation]:
        stmt = self._current_query(entities.Core3SkuClaimActivation, batch_id).order_by(
            entities.Core3SkuClaimActivation.sku_code,
            entities.Core3SkuClaimActivation.claim_code,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_claim_validations(self, batch_id: str) -> list[entities.Core3SkuClaimCommentValidation]:
        stmt = self._current_query(entities.Core3SkuClaimCommentValidation, batch_id).order_by(
            entities.Core3SkuClaimCommentValidation.sku_code,
            entities.Core3SkuClaimCommentValidation.claim_code,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_comment_profiles(self, batch_id: str) -> list[entities.Core3SkuCommentSignalProfile]:
        stmt = self._current_query(entities.Core3SkuCommentSignalProfile, batch_id).order_by(
            entities.Core3SkuCommentSignalProfile.sku_code,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_comment_signals(self, batch_id: str) -> list[entities.Core3CommentDownstreamSignal]:
        stmt = self._current_query(entities.Core3CommentDownstreamSignal, batch_id).order_by(
            entities.Core3CommentDownstreamSignal.sku_code,
            entities.Core3CommentDownstreamSignal.signal_type,
            entities.Core3CommentDownstreamSignal.target_code_hint,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_market_profiles(self, batch_id: str) -> list[entities.Core3SkuMarketProfile]:
        stmt = self._current_query(entities.Core3SkuMarketProfile, batch_id).order_by(
            entities.Core3SkuMarketProfile.sku_code,
            entities.Core3SkuMarketProfile.analysis_window,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_market_signals(self, batch_id: str) -> list[entities.Core3MarketSignal]:
        stmt = self._current_query(entities.Core3MarketSignal, batch_id).order_by(
            entities.Core3MarketSignal.sku_code,
            entities.Core3MarketSignal.analysis_window,
            entities.Core3MarketSignal.signal_code,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_comparable_pools(self, batch_id: str) -> list[entities.Core3ComparablePoolBaseline]:
        stmt = self._current_query(entities.Core3ComparablePoolBaseline, batch_id).order_by(
            entities.Core3ComparablePoolBaseline.target_sku_code,
            entities.Core3ComparablePoolBaseline.analysis_window,
            entities.Core3ComparablePoolBaseline.pool_type,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_pool_members(self, batch_id: str) -> list[entities.Core3MarketPoolMember]:
        stmt = self._current_query(entities.Core3MarketPoolMember, batch_id).order_by(
            entities.Core3MarketPoolMember.target_sku_code,
            entities.Core3MarketPoolMember.pool_id,
            entities.Core3MarketPoolMember.member_sku_code,
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_evidence_atoms(self, batch_id: str) -> list[entities.Core3EvidenceAtom]:
        stmt = (
            self._current_query(entities.Core3EvidenceAtom, batch_id)
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .order_by(
                entities.Core3EvidenceAtom.sku_code,
                entities.Core3EvidenceAtom.evidence_type,
                entities.Core3EvidenceAtom.evidence_id,
            )
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)


class M08SkuSignalProfileRepository(_M08RepositoryMixin):
    def save_profiles(self, records: Sequence[Any]) -> SkuSignalRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuSignalProfile,
            records,
            unique_fields=("batch_id", "sku_code", "profile_scope", "feature_version"),
            hash_field="profile_hash",
        )

    def save_matrices(self, records: Sequence[Any]) -> SkuSignalRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuSignalEvidenceMatrix,
            records,
            unique_fields=("sku_signal_profile_id", "domain", "sub_domain", "evidence_role", "feature_version"),
        )

    def save_views(self, records: Sequence[Any]) -> SkuSignalRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuDownstreamFeatureView,
            records,
            unique_fields=("sku_signal_profile_id", "for_module", "view_role", "view_schema_version"),
            hash_field="view_hash",
        )

    def list_current_profiles(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        profile_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuSignalProfile]:
        stmt = self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
            entities.Core3SkuSignalProfile.sku_code,
            entities.Core3SkuSignalProfile.profile_scope,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuSignalProfile.sku_code == sku_code)
        if profile_status is not None:
            stmt = stmt.where(entities.Core3SkuSignalProfile.profile_status == profile_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_matrices(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        domain: str | None = None,
        missing_flag: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuSignalEvidenceMatrix]:
        stmt = self._current_query(entities.Core3SkuSignalEvidenceMatrix, batch_id).order_by(
            entities.Core3SkuSignalEvidenceMatrix.sku_code,
            entities.Core3SkuSignalEvidenceMatrix.domain,
            entities.Core3SkuSignalEvidenceMatrix.sub_domain,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuSignalEvidenceMatrix.sku_code == sku_code)
        if domain is not None:
            stmt = stmt.where(entities.Core3SkuSignalEvidenceMatrix.domain == domain)
        if missing_flag is not None:
            stmt = stmt.where(entities.Core3SkuSignalEvidenceMatrix.missing_flag.is_(missing_flag))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_views(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        for_module: str | None = None,
        ready_for_module: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuDownstreamFeatureView]:
        stmt = self._current_query(entities.Core3SkuDownstreamFeatureView, batch_id).order_by(
            entities.Core3SkuDownstreamFeatureView.sku_code,
            entities.Core3SkuDownstreamFeatureView.for_module,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuDownstreamFeatureView.sku_code == sku_code)
        if for_module is not None:
            stmt = stmt.where(entities.Core3SkuDownstreamFeatureView.for_module == for_module)
        if ready_for_module is not None:
            stmt = stmt.where(entities.Core3SkuDownstreamFeatureView.ready_for_module.is_(ready_for_module))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def get_profile_by_id(self, profile_id: str) -> entities.Core3SkuSignalProfile | None:
        return self.db.execute(
            select(entities.Core3SkuSignalProfile)
            .where(entities.Core3SkuSignalProfile.project_id == self.project_id)
            .where(entities.Core3SkuSignalProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuSignalProfile.sku_signal_profile_id == profile_id)
            .where(entities.Core3SkuSignalProfile.is_current.is_(True))
        ).scalars().first()


class M08SkuSignalRepository(M08InputRepository, M08SkuSignalProfileRepository):
    pass


def _jsonable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable_value(value, nested=False) for key, value in payload.items()}


def _jsonable_value(value: Any, *, nested: bool = True) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value) if nested else value
    if isinstance(value, dict):
        return {str(key): _jsonable_value(item, nested=True) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_value(item, nested=True) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item, nested=True) for item in value]
    return value


def _refresh_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    for field_name, value in _jsonable_payload(payload).items():
        if field_name in primary_keys or field_name == "created_at":
            continue
        setattr(existing, field_name, value)
    existing.is_current = True


def _assign_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    _refresh_existing(existing, payload)
