"""M11.6 SKU business profile repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M116InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M116SkuBundle:
    profile: entities.Core3SkuSignalProfile
    market_profile: entities.Core3SkuMarketProfile | None
    task_scores: tuple[entities.Core3SkuTaskScore, ...]
    target_group_scores: tuple[entities.Core3SkuTargetGroupScore, ...]
    battlefield_scores: tuple[entities.Core3SkuBattlefieldScore, ...]
    battlefield_portfolio: entities.Core3SkuBattlefieldPortfolio | None
    claim_value_layers: tuple[entities.Core3SkuClaimValueLayer, ...]
    claim_value_summaries: tuple[entities.Core3SkuBattlefieldClaimValueSummary, ...]


@dataclass(frozen=True)
class SkuBusinessProfileRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class SkuBusinessProfileRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M08 SKU 综合信号画像": self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
            "M09 用户任务得分": self._count_current_rows(entities.Core3SkuTaskScore, batch_id),
            "M10 目标客群得分": self._count_current_rows(entities.Core3SkuTargetGroupScore, batch_id),
            "M11 价值战场得分": self._count_current_rows(entities.Core3SkuBattlefieldScore, batch_id),
            "M11.5 战场内卖点价值分层": self._count_current_rows(entities.Core3SkuClaimValueLayer, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M116InputBlockedError(f"M11.6 需要先完成上游产物：{', '.join(missing)}。")

    def list_input_bundles(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[M116SkuBundle]:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        profile_stmt = self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
            entities.Core3SkuSignalProfile.sku_code
        )
        if sku_scope_tuple:
            profile_stmt = profile_stmt.where(entities.Core3SkuSignalProfile.sku_code.in_(sku_scope_tuple))
        profiles = self._paged_scalars(profile_stmt, limit=100000, offset=0)
        sku_codes = tuple(sorted({profile.sku_code for profile in profiles}))
        markets_by_sku = self._list_market_profiles_by_sku(batch_id, sku_codes)
        tasks_by_sku = self._list_task_scores_by_sku(batch_id, sku_codes)
        groups_by_sku = self._list_target_group_scores_by_sku(batch_id, sku_codes)
        battlefields_by_sku = self._list_battlefield_scores_by_sku(batch_id, sku_codes)
        portfolios_by_sku = self._list_battlefield_portfolios_by_sku(batch_id, sku_codes)
        claim_layers_by_sku = self._list_claim_value_layers_by_sku(batch_id, sku_codes)
        claim_summaries_by_sku = self._list_claim_value_summaries_by_sku(batch_id, sku_codes)
        return [
            M116SkuBundle(
                profile=profile,
                market_profile=markets_by_sku.get(profile.sku_code),
                task_scores=tuple(tasks_by_sku.get(profile.sku_code, ())),
                target_group_scores=tuple(groups_by_sku.get(profile.sku_code, ())),
                battlefield_scores=tuple(battlefields_by_sku.get(profile.sku_code, ())),
                battlefield_portfolio=portfolios_by_sku.get(profile.sku_code),
                claim_value_layers=tuple(claim_layers_by_sku.get(profile.sku_code, ())),
                claim_value_summaries=tuple(claim_summaries_by_sku.get(profile.sku_code, ())),
            )
            for profile in profiles
        ]

    def save_profiles(self, records: Sequence[Any]) -> SkuBusinessProfileRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuBusinessProfile,
            records,
            unique_fields=("batch_id", "sku_code", "rule_version"),
        )

    def mark_child_outputs_stale(self, *, batch_id: str, rule_version: str, sku_codes: Sequence[str]) -> None:
        sku_scope = tuple(sorted({sku_code for sku_code in sku_codes if sku_code}))
        if not sku_scope:
            return
        for model_cls in (
            entities.Core3SkuBusinessProfileDimension,
            entities.Core3SkuBusinessProfileSalesAllocation,
            entities.Core3SkuBusinessProfileReviewIssue,
        ):
            stmt = (
                update(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(model_cls.batch_id == batch_id)
                .where(model_cls.rule_version == rule_version)
                .where(model_cls.sku_code.in_(sku_scope))
                .where(model_cls.is_current.is_(True))
                .values(is_current=False)
            )
            self.db.execute(stmt)
        self.db.flush()

    def save_dimensions(self, records: Sequence[Any]) -> SkuBusinessProfileRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuBusinessProfileDimension,
            records,
            unique_fields=("batch_id", "sku_code", "dimension_type", "dimension_code", "rule_version"),
        )

    def save_allocations(self, records: Sequence[Any]) -> SkuBusinessProfileRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuBusinessProfileSalesAllocation,
            records,
            unique_fields=("batch_id", "sku_code", "dimension_type", "dimension_code", "rule_version"),
        )

    def save_review_issues(self, records: Sequence[Any]) -> SkuBusinessProfileRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuBusinessProfileReviewIssue,
            records,
            unique_fields=("batch_id", "sku_code", "dimension_type", "dimension_code", "issue_type", "input_fingerprint"),
        )

    def list_current_profiles(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        market_role: str | None = None,
        premium_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuBusinessProfile]:
        stmt = self._current_query(entities.Core3SkuBusinessProfile, batch_id).order_by(
            entities.Core3SkuBusinessProfile.sku_code
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfile.sku_code == sku_code)
        if market_role is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfile.market_role == market_role)
        if premium_type is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfile.premium_type == premium_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_dimensions(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        dimension_type: str | None = None,
        dimension_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuBusinessProfileDimension]:
        stmt = self._current_query(entities.Core3SkuBusinessProfileDimension, batch_id).order_by(
            entities.Core3SkuBusinessProfileDimension.sku_code,
            entities.Core3SkuBusinessProfileDimension.dimension_type,
            entities.Core3SkuBusinessProfileDimension.dimension_rank,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileDimension.sku_code == sku_code)
        if dimension_type is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileDimension.dimension_type == dimension_type)
        if dimension_code is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileDimension.dimension_code == dimension_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_allocations(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        dimension_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuBusinessProfileSalesAllocation]:
        stmt = self._current_query(entities.Core3SkuBusinessProfileSalesAllocation, batch_id).order_by(
            entities.Core3SkuBusinessProfileSalesAllocation.sku_code,
            entities.Core3SkuBusinessProfileSalesAllocation.dimension_type,
            entities.Core3SkuBusinessProfileSalesAllocation.allocation_weight.desc(),
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileSalesAllocation.sku_code == sku_code)
        if dimension_type is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileSalesAllocation.dimension_type == dimension_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_review_issues(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        issue_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuBusinessProfileReviewIssue]:
        stmt = self._current_query(entities.Core3SkuBusinessProfileReviewIssue, batch_id).order_by(
            entities.Core3SkuBusinessProfileReviewIssue.issue_level.desc(),
            entities.Core3SkuBusinessProfileReviewIssue.sku_code,
            entities.Core3SkuBusinessProfileReviewIssue.issue_type,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileReviewIssue.sku_code == sku_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3SkuBusinessProfileReviewIssue.issue_type == issue_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def count_current_rows(self, model_cls: Any, batch_id: str, **filters: Any) -> int:
        return self._count_current_rows(model_cls, batch_id, **filters)

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

    def _count_current_rows(self, model_cls: Any, batch_id: str, **filters: Any) -> int:
        stmt = (
            select(func.count())
            .select_from(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
            .where(model_cls.is_current.is_(True))
        )
        for field_name, value in filters.items():
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return int(self.db.execute(stmt).scalar_one())

    def _list_market_profiles_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, entities.Core3SkuMarketProfile]:
        stmt = self._current_query(entities.Core3SkuMarketProfile, batch_id).order_by(
            entities.Core3SkuMarketProfile.sku_code,
            entities.Core3SkuMarketProfile.market_confidence.desc(),
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuMarketProfile.sku_code.in_(sku_scope))
        result: dict[str, entities.Core3SkuMarketProfile] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.sku_code, row)
        return result

    def _list_task_scores_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuTaskScore]]:
        stmt = self._current_query(entities.Core3SkuTaskScore, batch_id).order_by(
            entities.Core3SkuTaskScore.sku_code,
            entities.Core3SkuTaskScore.task_score.desc(),
            entities.Core3SkuTaskScore.task_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuTaskScore.sku_code.in_(sku_scope))
        return _group_by_sku(self._paged_scalars(stmt, limit=100000, offset=0))

    def _list_target_group_scores_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuTargetGroupScore]]:
        stmt = self._current_query(entities.Core3SkuTargetGroupScore, batch_id).order_by(
            entities.Core3SkuTargetGroupScore.sku_code,
            entities.Core3SkuTargetGroupScore.target_group_score.desc(),
            entities.Core3SkuTargetGroupScore.target_group_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuTargetGroupScore.sku_code.in_(sku_scope))
        return _group_by_sku(self._paged_scalars(stmt, limit=100000, offset=0))

    def _list_battlefield_scores_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuBattlefieldScore]]:
        stmt = self._current_query(entities.Core3SkuBattlefieldScore, batch_id).order_by(
            entities.Core3SkuBattlefieldScore.sku_code,
            entities.Core3SkuBattlefieldScore.battlefield_score.desc(),
            entities.Core3SkuBattlefieldScore.battlefield_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuBattlefieldScore.sku_code.in_(sku_scope))
        return _group_by_sku(self._paged_scalars(stmt, limit=100000, offset=0))

    def _list_battlefield_portfolios_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, entities.Core3SkuBattlefieldPortfolio]:
        stmt = self._current_query(entities.Core3SkuBattlefieldPortfolio, batch_id).order_by(
            entities.Core3SkuBattlefieldPortfolio.sku_code
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuBattlefieldPortfolio.sku_code.in_(sku_scope))
        return {row.sku_code: row for row in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _list_claim_value_layers_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuClaimValueLayer]]:
        stmt = self._current_query(entities.Core3SkuClaimValueLayer, batch_id).order_by(
            entities.Core3SkuClaimValueLayer.sku_code,
            entities.Core3SkuClaimValueLayer.claim_value_score.desc(),
            entities.Core3SkuClaimValueLayer.claim_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuClaimValueLayer.sku_code.in_(sku_scope))
        return _group_by_sku(self._paged_scalars(stmt, limit=100000, offset=0))

    def _list_claim_value_summaries_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuBattlefieldClaimValueSummary]]:
        stmt = self._current_query(entities.Core3SkuBattlefieldClaimValueSummary, batch_id).order_by(
            entities.Core3SkuBattlefieldClaimValueSummary.sku_code,
            entities.Core3SkuBattlefieldClaimValueSummary.battlefield_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimValueSummary.sku_code.in_(sku_scope))
        return _group_by_sku(self._paged_scalars(stmt, limit=100000, offset=0))

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> SkuBusinessProfileRepositoryWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        updated_count = 0
        for payload in payloads:
            record, status = self._save_one(model_cls, payload, unique_fields=unique_fields, hash_field=hash_field)
            records.append(record)
            if status == "created":
                created_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                reused_count += 1
        return SkuBusinessProfileRepositoryWriteResult(tuple(records), created_count, reused_count, updated_count)

    def _save_one(self, model_cls: Any, payload: Any, *, unique_fields: tuple[str, ...], hash_field: str) -> tuple[Any, str]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is None:
            record = model_cls(**_jsonable_payload(normalized_payload))
            self.db.add(record)
            self.db.flush()
            return record, "created"
        if normalized_payload.get(hash_field) == getattr(existing, hash_field):
            _refresh_existing(existing, normalized_payload)
            self.db.flush()
            return existing, "reused"
        _refresh_existing(existing, normalized_payload)
        self.db.flush()
        return existing, "updated"

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw_payload = payload.model_dump(mode="python")
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M11.6 repository payload must be a mapping or Pydantic model")
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


def _group_by_sku(rows: Sequence[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for row in rows:
        result.setdefault(row.sku_code, []).append(row)
    return result


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
