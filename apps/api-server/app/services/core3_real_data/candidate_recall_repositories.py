"""M12 candidate recall repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.constants import M08ForModule
from app.services.core3_real_data.repositories import Core3BaseRepository


class M12InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M12SkuBundle:
    profile: entities.Core3SkuSignalProfile
    feature_view: entities.Core3SkuDownstreamFeatureView | None
    market_profile: entities.Core3SkuMarketProfile | None
    pool_members: tuple[entities.Core3MarketPoolMember, ...]
    task_scores: tuple[entities.Core3SkuTaskScore, ...]
    target_group_scores: tuple[entities.Core3SkuTargetGroupScore, ...]
    battlefield_scores: tuple[entities.Core3SkuBattlefieldScore, ...]
    battlefield_portfolio: entities.Core3SkuBattlefieldPortfolio | None
    claim_value_layers: tuple[entities.Core3SkuClaimValueLayer, ...]
    claim_value_summaries: tuple[entities.Core3SkuBattlefieldClaimValueSummary, ...]


@dataclass(frozen=True)
class CandidateRecallRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class CandidateRecallRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M08 SKU 综合信号画像": self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
            "M08 M12 特征视图": self._count_current_rows(
                entities.Core3SkuDownstreamFeatureView,
                batch_id,
                for_module=M08ForModule.M12.value,
            ),
            "M11 价值战场分数": self._count_current_rows(entities.Core3SkuBattlefieldScore, batch_id),
            "M11.7 销量分配对账": self._count_current_rows(
                entities.Core3BusinessSalesReconciliationCheck,
                batch_id,
            ),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M12InputBlockedError(f"M12 需要先完成上游产物：{', '.join(missing)}。")
        blocking_issue_count = self._count_current_rows(
            entities.Core3BusinessSalesReconciliationIssue,
            batch_id,
            severity="blocker",
            resolved_status="open",
        )
        failed_check_count = self._count_current_rows(
            entities.Core3BusinessSalesReconciliationCheck,
            batch_id,
            status="failed",
        )
        if blocking_issue_count or failed_check_count:
            raise M12InputBlockedError(
                f"M11.7 销量分配对账未通过：阻断问题 {blocking_issue_count} 条，失败检查 {failed_check_count} 条。"
            )

    def list_input_bundles(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[M12SkuBundle]:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        profile_stmt = self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
            entities.Core3SkuSignalProfile.sku_code
        )
        if sku_scope_tuple:
            profile_stmt = profile_stmt.where(entities.Core3SkuSignalProfile.sku_code.in_(sku_scope_tuple))
        profiles = self._paged_scalars(profile_stmt, limit=100000, offset=0)
        all_sku_codes = tuple(sorted({profile.sku_code for profile in profiles} | set(sku_scope_tuple)))
        return self._build_bundles(batch_id, profiles, all_sku_codes)

    def list_all_input_bundles(self, batch_id: str) -> list[M12SkuBundle]:
        profile_stmt = self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
            entities.Core3SkuSignalProfile.sku_code
        )
        profiles = self._paged_scalars(profile_stmt, limit=100000, offset=0)
        return self._build_bundles(batch_id, profiles, tuple(sorted({profile.sku_code for profile in profiles})))

    def save_run(self, record: Any) -> CandidateRecallRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateRecallRun,
            [record],
            unique_fields=("batch_id", "run_key", "rule_version"),
        )

    def save_pools(self, records: Sequence[Any]) -> CandidateRecallRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidatePool,
            records,
            unique_fields=("batch_id", "target_sku_code", "candidate_sku_code", "rule_version"),
        )

    def save_reasons(self, records: Sequence[Any]) -> CandidateRecallRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateRecallReason,
            records,
            unique_fields=("candidate_pool_id", "recall_source", "relation_type", "reason_code", "rule_version"),
        )

    def save_snapshots(self, records: Sequence[Any]) -> CandidateRecallRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateFeatureSnapshot,
            records,
            unique_fields=("candidate_pool_id", "rule_version", "feature_snapshot_hash"),
        )

    def save_review_issues(self, records: Sequence[Any]) -> CandidateRecallRepositoryWriteResult:
        return self._save_many(
            entities.Core3CandidateRecallReviewIssue,
            records,
            unique_fields=("batch_id", "target_sku_code", "candidate_sku_code", "issue_type", "input_fingerprint"),
        )

    def list_current_runs(
        self,
        batch_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateRecallRun]:
        stmt = self._current_query(entities.Core3CandidateRecallRun, batch_id).order_by(
            entities.Core3CandidateRecallRun.updated_at.desc(),
            entities.Core3CandidateRecallRun.candidate_recall_run_id,
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_pools(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        recall_strength: str | None = None,
        primary_relation_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidatePool]:
        stmt = self._current_query(entities.Core3CandidatePool, batch_id).order_by(
            entities.Core3CandidatePool.target_sku_code,
            entities.Core3CandidatePool.recall_priority_score.desc(),
            entities.Core3CandidatePool.candidate_sku_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidatePool.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidatePool.candidate_sku_code == candidate_sku_code)
        if recall_strength is not None:
            stmt = stmt.where(entities.Core3CandidatePool.recall_strength == recall_strength)
        if primary_relation_type is not None:
            stmt = stmt.where(entities.Core3CandidatePool.primary_relation_type == primary_relation_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_reasons(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        candidate_pool_id: str | None = None,
        recall_source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateRecallReason]:
        stmt = self._current_query(entities.Core3CandidateRecallReason, batch_id).order_by(
            entities.Core3CandidateRecallReason.target_sku_code,
            entities.Core3CandidateRecallReason.candidate_sku_code,
            entities.Core3CandidateRecallReason.support_score.desc(),
            entities.Core3CandidateRecallReason.recall_source,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReason.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReason.candidate_sku_code == candidate_sku_code)
        if candidate_pool_id is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReason.candidate_pool_id == candidate_pool_id)
        if recall_source is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReason.recall_source == recall_source)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_snapshots(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        candidate_pool_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateFeatureSnapshot]:
        stmt = self._current_query(entities.Core3CandidateFeatureSnapshot, batch_id).order_by(
            entities.Core3CandidateFeatureSnapshot.target_sku_code,
            entities.Core3CandidateFeatureSnapshot.candidate_sku_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateFeatureSnapshot.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateFeatureSnapshot.candidate_sku_code == candidate_sku_code)
        if candidate_pool_id is not None:
            stmt = stmt.where(entities.Core3CandidateFeatureSnapshot.candidate_pool_id == candidate_pool_id)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_review_issues(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        issue_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CandidateRecallReviewIssue]:
        stmt = self._current_query(entities.Core3CandidateRecallReviewIssue, batch_id).order_by(
            entities.Core3CandidateRecallReviewIssue.issue_level.desc(),
            entities.Core3CandidateRecallReviewIssue.target_sku_code,
            entities.Core3CandidateRecallReviewIssue.candidate_sku_code,
            entities.Core3CandidateRecallReviewIssue.issue_type,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReviewIssue.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReviewIssue.candidate_sku_code == candidate_sku_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3CandidateRecallReviewIssue.issue_type == issue_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def _build_bundles(
        self,
        batch_id: str,
        profiles: Sequence[entities.Core3SkuSignalProfile],
        sku_scope: tuple[str, ...],
    ) -> list[M12SkuBundle]:
        views_by_sku = self._list_views_by_sku(batch_id, sku_scope)
        markets_by_sku = self._list_market_profiles_by_sku(batch_id, sku_scope)
        pool_members_by_target = self._list_pool_members_by_target(batch_id, sku_scope)
        tasks_by_sku = self._list_task_scores_by_sku(batch_id, sku_scope)
        groups_by_sku = self._list_target_group_scores_by_sku(batch_id, sku_scope)
        battlefields_by_sku = self._list_battlefield_scores_by_sku(batch_id, sku_scope)
        portfolios_by_sku = self._list_battlefield_portfolios_by_sku(batch_id, sku_scope)
        claim_layers_by_sku = self._list_claim_value_layers_by_sku(batch_id, sku_scope)
        claim_summaries_by_sku = self._list_claim_value_summaries_by_sku(batch_id, sku_scope)
        return [
            M12SkuBundle(
                profile=profile,
                feature_view=views_by_sku.get(profile.sku_code),
                market_profile=markets_by_sku.get(profile.sku_code),
                pool_members=tuple(pool_members_by_target.get(profile.sku_code, ())),
                task_scores=tuple(tasks_by_sku.get(profile.sku_code, ())),
                target_group_scores=tuple(groups_by_sku.get(profile.sku_code, ())),
                battlefield_scores=tuple(battlefields_by_sku.get(profile.sku_code, ())),
                battlefield_portfolio=portfolios_by_sku.get(profile.sku_code),
                claim_value_layers=tuple(claim_layers_by_sku.get(profile.sku_code, ())),
                claim_value_summaries=tuple(claim_summaries_by_sku.get(profile.sku_code, ())),
            )
            for profile in profiles
        ]

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

    def _list_views_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, entities.Core3SkuDownstreamFeatureView]:
        stmt = (
            self._current_query(entities.Core3SkuDownstreamFeatureView, batch_id)
            .where(entities.Core3SkuDownstreamFeatureView.for_module == M08ForModule.M12.value)
            .order_by(entities.Core3SkuDownstreamFeatureView.sku_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuDownstreamFeatureView.sku_code.in_(sku_scope))
        return {view.sku_code: view for view in self._paged_scalars(stmt, limit=100000, offset=0)}

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

    def _list_pool_members_by_target(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3MarketPoolMember]]:
        stmt = self._current_query(entities.Core3MarketPoolMember, batch_id).order_by(
            entities.Core3MarketPoolMember.target_sku_code,
            entities.Core3MarketPoolMember.relation_strength.desc(),
            entities.Core3MarketPoolMember.member_sku_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3MarketPoolMember.target_sku_code.in_(sku_scope))
        result: dict[str, list[entities.Core3MarketPoolMember]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            if not row.is_target_self:
                result.setdefault(row.target_sku_code, []).append(row)
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
            entities.Core3SkuClaimValueLayer.battlefield_code,
            entities.Core3SkuClaimValueLayer.claim_value_score.desc(),
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
    ) -> CandidateRecallRepositoryWriteResult:
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
        return CandidateRecallRepositoryWriteResult(tuple(records), created_count, reused_count, updated_count)

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
            raise TypeError("M12 repository payload must be a mapping or Pydantic model")
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
