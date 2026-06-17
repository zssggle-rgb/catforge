"""M07 market profile repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.constants import Core3CleanRecordStatus, Core3EvidenceStatus, Core3EvidenceType
from app.services.core3_real_data.repositories import Core3BaseRepository


class M07InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class _M07RepositoryMixin(Core3BaseRepository):
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
    ) -> MarketRepositoryWriteResult:
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
        return MarketRepositoryWriteResult(
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
            existing = self._find_by_stable_identifier(model_cls, normalized_payload)
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
            raise TypeError("M07 repository payload must be a mapping or Pydantic model")
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

    def _find_by_stable_identifier(self, model_cls: Any, payload: Mapping[str, Any]) -> Any | None:
        identifier_field = _stable_identifier_field(model_cls)
        if identifier_field is None:
            return None
        identifier = payload.get(identifier_field)
        if not identifier:
            return None
        return (
            self.db.execute(
                select(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(getattr(model_cls, identifier_field) == identifier)
            )
            .scalars()
            .first()
        )


class M07InputRepository(_M07RepositoryMixin):
    """Read only M01/M02/M03 tables allowed by M07."""

    def assert_inputs_ready(self, batch_id: str) -> None:
        market_count = self.db.execute(
            select(func.count())
            .select_from(entities.Core3CleanMarketWeekly)
            .where(entities.Core3CleanMarketWeekly.project_id == self.project_id)
            .where(entities.Core3CleanMarketWeekly.category_code == self.category_code.value)
            .where(entities.Core3CleanMarketWeekly.batch_id == batch_id)
            .where(entities.Core3CleanMarketWeekly.record_status == Core3CleanRecordStatus.ACTIVE.value)
        ).scalar_one()
        if int(market_count) == 0:
            raise M07InputBlockedError("M07 需要先完成 M01 市场周销清洗，当前批次没有可用清洗周销。")

        evidence_count = self.db.execute(
            select(func.count())
            .select_from(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type == Core3EvidenceType.MARKET_FACT.value)
        ).scalar_one()
        if int(evidence_count) == 0:
            raise M07InputBlockedError("M07 需要先完成 M02 market_fact 证据原子层。")

        param_profile_count = self.db.execute(
            select(func.count())
            .select_from(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
        ).scalar_one()
        if int(param_profile_count) == 0:
            raise M07InputBlockedError("M07 需要先完成 M03 参数画像，以便读取屏幕尺寸。")

    def list_clean_skus(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[entities.Core3CleanSku]:
        stmt = (
            select(entities.Core3CleanSku)
            .where(entities.Core3CleanSku.project_id == self.project_id)
            .where(entities.Core3CleanSku.category_code == self.category_code.value)
            .where(entities.Core3CleanSku.batch_id == batch_id)
            .order_by(entities.Core3CleanSku.sku_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3CleanSku.sku_code.in_(tuple(sku_scope)))
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_clean_market_rows(self, batch_id: str) -> list[entities.Core3CleanMarketWeekly]:
        stmt = (
            select(entities.Core3CleanMarketWeekly)
            .where(entities.Core3CleanMarketWeekly.project_id == self.project_id)
            .where(entities.Core3CleanMarketWeekly.category_code == self.category_code.value)
            .where(entities.Core3CleanMarketWeekly.batch_id == batch_id)
            .where(entities.Core3CleanMarketWeekly.record_status == Core3CleanRecordStatus.ACTIVE.value)
            .where(entities.Core3CleanMarketWeekly.sku_code.is_not(None))
            .order_by(
                entities.Core3CleanMarketWeekly.sku_code,
                entities.Core3CleanMarketWeekly.period_week_index,
                entities.Core3CleanMarketWeekly.platform_type,
                entities.Core3CleanMarketWeekly.clean_market_id,
            )
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_market_evidence(self, batch_id: str) -> list[entities.Core3EvidenceAtom]:
        stmt = (
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type == Core3EvidenceType.MARKET_FACT.value)
            .order_by(
                entities.Core3EvidenceAtom.sku_code,
                entities.Core3EvidenceAtom.clean_record_key,
                entities.Core3EvidenceAtom.evidence_id,
            )
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_sku_param_profiles(self, batch_id: str) -> list[entities.Core3SkuParamProfile]:
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .order_by(entities.Core3SkuParamProfile.sku_code)
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def list_extract_param_values(self, batch_id: str) -> list[entities.Core3ExtractParamValue]:
        stmt = (
            select(entities.Core3ExtractParamValue)
            .where(entities.Core3ExtractParamValue.project_id == self.project_id)
            .where(entities.Core3ExtractParamValue.category_code == self.category_code.value)
            .where(entities.Core3ExtractParamValue.batch_id == batch_id)
            .order_by(
                entities.Core3ExtractParamValue.sku_code,
                entities.Core3ExtractParamValue.param_code,
                entities.Core3ExtractParamValue.source_priority_rank,
            )
        )
        return self._paged_scalars(stmt, limit=100000, offset=0)


class M07MarketProfileRepository(_M07RepositoryMixin):
    def save_profiles(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuMarketProfile,
            records,
            unique_fields=("batch_id", "sku_code", "analysis_window", "rule_version"),
        )

    def list_current_profiles(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        analysis_window: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuMarketProfile]:
        stmt = self._current_query(entities.Core3SkuMarketProfile, batch_id).order_by(
            entities.Core3SkuMarketProfile.sku_code,
            entities.Core3SkuMarketProfile.analysis_window,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuMarketProfile.sku_code == sku_code)
        if analysis_window is not None:
            stmt = stmt.where(entities.Core3SkuMarketProfile.analysis_window == analysis_window)
        return self._paged_scalars(stmt, limit=limit, offset=offset)


class M07MarketSignalRepository(_M07RepositoryMixin):
    def save_signals(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._save_many(
            entities.Core3MarketSignal,
            records,
            unique_fields=("batch_id", "sku_code", "analysis_window", "signal_code", "comparison_scope", "rule_version"),
        )

    def list_current_signals(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        signal_code: str | None = None,
        analysis_window: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3MarketSignal]:
        stmt = self._current_query(entities.Core3MarketSignal, batch_id).order_by(
            entities.Core3MarketSignal.sku_code,
            entities.Core3MarketSignal.analysis_window,
            entities.Core3MarketSignal.signal_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3MarketSignal.sku_code == sku_code)
        if signal_code is not None:
            stmt = stmt.where(entities.Core3MarketSignal.signal_code == signal_code)
        if analysis_window is not None:
            stmt = stmt.where(entities.Core3MarketSignal.analysis_window == analysis_window)
        return self._paged_scalars(stmt, limit=limit, offset=offset)


class M07ComparablePoolRepository(_M07RepositoryMixin):
    def save_pools(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._save_many(
            entities.Core3ComparablePoolBaseline,
            records,
            unique_fields=("batch_id", "target_sku_code", "analysis_window", "pool_type", "rule_version"),
        )

    def list_current_pools(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        pool_type: str | None = None,
        analysis_window: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ComparablePoolBaseline]:
        stmt = self._current_query(entities.Core3ComparablePoolBaseline, batch_id).order_by(
            entities.Core3ComparablePoolBaseline.target_sku_code,
            entities.Core3ComparablePoolBaseline.analysis_window,
            entities.Core3ComparablePoolBaseline.pool_type,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3ComparablePoolBaseline.target_sku_code == target_sku_code)
        if pool_type is not None:
            stmt = stmt.where(entities.Core3ComparablePoolBaseline.pool_type == pool_type)
        if analysis_window is not None:
            stmt = stmt.where(entities.Core3ComparablePoolBaseline.analysis_window == analysis_window)
        return self._paged_scalars(stmt, limit=limit, offset=offset)


class M07MarketPoolMemberRepository(_M07RepositoryMixin):
    def save_members(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._save_many(
            entities.Core3MarketPoolMember,
            records,
            unique_fields=("pool_id", "target_sku_code", "member_sku_code", "rule_version"),
        )

    def list_current_members(
        self,
        batch_id: str,
        *,
        pool_id: str | None = None,
        target_sku_code: str | None = None,
        member_sku_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3MarketPoolMember]:
        stmt = self._current_query(entities.Core3MarketPoolMember, batch_id).order_by(
            entities.Core3MarketPoolMember.pool_id,
            entities.Core3MarketPoolMember.member_sku_code,
        )
        if pool_id is not None:
            stmt = stmt.where(entities.Core3MarketPoolMember.pool_id == pool_id)
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3MarketPoolMember.target_sku_code == target_sku_code)
        if member_sku_code is not None:
            stmt = stmt.where(entities.Core3MarketPoolMember.member_sku_code == member_sku_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)


class M07MarketRepository(
    M07InputRepository,
    M07MarketProfileRepository,
    M07MarketSignalRepository,
    M07ComparablePoolRepository,
    M07MarketPoolMemberRepository,
):
    pass


def _stable_identifier_field(model_cls: Any) -> str | None:
    if model_cls is entities.Core3SkuMarketProfile:
        return "sku_market_profile_id"
    if model_cls is entities.Core3MarketSignal:
        return "market_signal_id"
    if model_cls is entities.Core3ComparablePoolBaseline:
        return "pool_id"
    if model_cls is entities.Core3MarketPoolMember:
        return "pool_member_id"
    return None


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
