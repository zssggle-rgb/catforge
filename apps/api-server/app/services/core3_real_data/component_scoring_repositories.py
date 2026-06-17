"""M13 component scoring repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M13InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M13CandidateInput:
    pool: entities.Core3CandidatePool
    snapshot: entities.Core3CandidateFeatureSnapshot | None
    reasons: tuple[entities.Core3CandidateRecallReason, ...]


@dataclass(frozen=True)
class ComponentScoringRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class ComponentScoringRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M12 候选池": self._count_current_rows(entities.Core3CandidatePool, batch_id),
            "M12 pair 特征快照": self._count_current_rows(entities.Core3CandidateFeatureSnapshot, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M13InputBlockedError(f"M13 需要先完成上游产物：{', '.join(missing)}。")

    def list_current_candidate_inputs(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
        max_pairs: int | None = None,
        only_unscored: bool = False,
    ) -> list[M13CandidateInput]:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        pool_stmt = self._current_query(entities.Core3CandidatePool, batch_id).order_by(
            entities.Core3CandidatePool.target_sku_code,
            entities.Core3CandidatePool.recall_priority_score.desc(),
            entities.Core3CandidatePool.candidate_sku_code,
        )
        if sku_scope_tuple:
            pool_stmt = pool_stmt.where(entities.Core3CandidatePool.target_sku_code.in_(sku_scope_tuple))
        if only_unscored:
            pool_stmt = pool_stmt.where(~self._component_score_exists(batch_id, rule_version))
        limit = max_pairs if max_pairs is not None and max_pairs > 0 else 100000
        pools = self._paged_scalars(pool_stmt, limit=limit, offset=0)
        pool_ids = tuple(pool.candidate_pool_id for pool in pools)
        snapshots_by_pool = self._list_snapshots_by_pool(batch_id, pool_ids)
        reasons_by_pool = self._list_reasons_by_pool(batch_id, pool_ids)
        return [
            M13CandidateInput(
                pool=pool,
                snapshot=snapshots_by_pool.get(pool.candidate_pool_id),
                reasons=tuple(reasons_by_pool.get(pool.candidate_pool_id, ())),
            )
            for pool in pools
        ]

    def count_current_candidate_pairs(self, batch_id: str, *, sku_scope: Sequence[str] = ()) -> int:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(func.count())
            .select_from(entities.Core3CandidatePool)
            .where(entities.Core3CandidatePool.project_id == self.project_id)
            .where(entities.Core3CandidatePool.category_code == self.category_code.value)
            .where(entities.Core3CandidatePool.batch_id == batch_id)
            .where(entities.Core3CandidatePool.is_current.is_(True))
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CandidatePool.target_sku_code.in_(sku_scope_tuple))
        return int(self.db.execute(stmt).scalar_one())

    def count_current_component_scores(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
    ) -> int:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(func.count())
            .select_from(entities.Core3CandidateComponentScore)
            .where(entities.Core3CandidateComponentScore.project_id == self.project_id)
            .where(entities.Core3CandidateComponentScore.category_code == self.category_code.value)
            .where(entities.Core3CandidateComponentScore.batch_id == batch_id)
            .where(entities.Core3CandidateComponentScore.rule_version == rule_version)
            .where(entities.Core3CandidateComponentScore.is_current.is_(True))
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CandidateComponentScore.target_sku_code.in_(sku_scope_tuple))
        return int(self.db.execute(stmt).scalar_one())

    def save_component_scores(self, records: Sequence[Any]) -> ComponentScoringRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateComponentScore,
            records,
            unique_fields=("batch_id", "target_sku_code", "candidate_sku_code", "rule_version"),
        )

    def save_role_scores(self, records: Sequence[Any]) -> ComponentScoringRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateRoleScore,
            records,
            unique_fields=("batch_id", "target_sku_code", "candidate_sku_code", "role_code", "rule_version"),
        )

    def save_explanations(self, records: Sequence[Any]) -> ComponentScoringRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateComponentExplanation,
            records,
            unique_fields=("batch_id", "target_sku_code", "candidate_sku_code", "component_code", "rule_version"),
        )

    def save_review_issues(self, records: Sequence[Any]) -> ComponentScoringRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateScoreReviewIssue,
            records,
            unique_fields=(
                "batch_id",
                "target_sku_code",
                "candidate_sku_code",
                "issue_scope",
                "component_code",
                "role_code",
                "issue_type",
                "input_fingerprint",
            ),
        )

    def list_current_component_scores(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateComponentScore]:
        stmt = self._current_query(entities.Core3CandidateComponentScore, batch_id).order_by(
            entities.Core3CandidateComponentScore.target_sku_code,
            entities.Core3CandidateComponentScore.component_total_score.desc(),
            entities.Core3CandidateComponentScore.candidate_sku_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateComponentScore.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateComponentScore.candidate_sku_code == candidate_sku_code)
        if review_required is not None:
            stmt = stmt.where(entities.Core3CandidateComponentScore.review_required.is_(review_required))
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_role_scores(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        role_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateRoleScore]:
        stmt = self._current_query(entities.Core3CandidateRoleScore, batch_id).order_by(
            entities.Core3CandidateRoleScore.target_sku_code,
            entities.Core3CandidateRoleScore.candidate_sku_code,
            entities.Core3CandidateRoleScore.role_score.desc(),
            entities.Core3CandidateRoleScore.role_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateRoleScore.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateRoleScore.candidate_sku_code == candidate_sku_code)
        if role_code is not None:
            stmt = stmt.where(entities.Core3CandidateRoleScore.role_code == role_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_explanations(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        component_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateComponentExplanation]:
        stmt = self._current_query(entities.Core3CandidateComponentExplanation, batch_id).order_by(
            entities.Core3CandidateComponentExplanation.target_sku_code,
            entities.Core3CandidateComponentExplanation.candidate_sku_code,
            entities.Core3CandidateComponentExplanation.component_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateComponentExplanation.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateComponentExplanation.candidate_sku_code == candidate_sku_code)
        if component_code is not None:
            stmt = stmt.where(entities.Core3CandidateComponentExplanation.component_code == component_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_review_issues(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        issue_type: str | None = None,
        issue_level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateScoreReviewIssue]:
        stmt = self._current_query(entities.Core3CandidateScoreReviewIssue, batch_id).order_by(
            entities.Core3CandidateScoreReviewIssue.issue_level.desc(),
            entities.Core3CandidateScoreReviewIssue.target_sku_code,
            entities.Core3CandidateScoreReviewIssue.candidate_sku_code,
            entities.Core3CandidateScoreReviewIssue.issue_type,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateScoreReviewIssue.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateScoreReviewIssue.candidate_sku_code == candidate_sku_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3CandidateScoreReviewIssue.issue_type == issue_type)
        if issue_level is not None:
            stmt = stmt.where(entities.Core3CandidateScoreReviewIssue.issue_level == issue_level)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def _base_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
        return self._base_query(model_cls, batch_id).where(model_cls.is_current.is_(True))

    def _component_score_exists(self, batch_id: str, rule_version: str) -> Any:
        return (
            select(entities.Core3CandidateComponentScore.candidate_component_score_id)
            .where(entities.Core3CandidateComponentScore.project_id == self.project_id)
            .where(entities.Core3CandidateComponentScore.category_code == self.category_code.value)
            .where(entities.Core3CandidateComponentScore.batch_id == batch_id)
            .where(entities.Core3CandidateComponentScore.rule_version == rule_version)
            .where(entities.Core3CandidateComponentScore.target_sku_code == entities.Core3CandidatePool.target_sku_code)
            .where(entities.Core3CandidateComponentScore.candidate_sku_code == entities.Core3CandidatePool.candidate_sku_code)
            .where(entities.Core3CandidateComponentScore.is_current.is_(True))
            .exists()
        )

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

    def _list_snapshots_by_pool(
        self,
        batch_id: str,
        pool_ids: tuple[str, ...],
    ) -> dict[str, entities.Core3CandidateFeatureSnapshot]:
        if not pool_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateFeatureSnapshot, batch_id)
            .where(entities.Core3CandidateFeatureSnapshot.candidate_pool_id.in_(pool_ids))
            .order_by(
                entities.Core3CandidateFeatureSnapshot.candidate_pool_id,
                entities.Core3CandidateFeatureSnapshot.updated_at.desc(),
            )
        )
        result: dict[str, entities.Core3CandidateFeatureSnapshot] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.candidate_pool_id, row)
        return result

    def _list_reasons_by_pool(
        self,
        batch_id: str,
        pool_ids: tuple[str, ...],
    ) -> dict[str, list[entities.Core3CandidateRecallReason]]:
        if not pool_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateRecallReason, batch_id)
            .where(entities.Core3CandidateRecallReason.candidate_pool_id.in_(pool_ids))
            .order_by(
                entities.Core3CandidateRecallReason.candidate_pool_id,
                entities.Core3CandidateRecallReason.support_score.desc(),
                entities.Core3CandidateRecallReason.recall_source,
            )
        )
        result: dict[str, list[entities.Core3CandidateRecallReason]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.candidate_pool_id, []).append(row)
        return result

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> ComponentScoringRepositoryWriteResult:
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
        return ComponentScoringRepositoryWriteResult(tuple(records), created_count, reused_count, updated_count)

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
            raise TypeError("M13 repository payload must be a mapping or Pydantic model")
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
