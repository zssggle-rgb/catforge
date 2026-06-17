"""M14 core competitor selection repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M14InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M14CandidateInput:
    pool: entities.Core3CandidatePool
    snapshot: entities.Core3CandidateFeatureSnapshot | None
    component_score: entities.Core3CandidateComponentScore
    role_scores: dict[str, entities.Core3CandidateRoleScore]
    explanations: tuple[entities.Core3CandidateComponentExplanation, ...]
    score_issues: tuple[entities.Core3CandidateScoreReviewIssue, ...]


@dataclass(frozen=True)
class M14TargetInput:
    target_sku_code: str
    target_model_name: str | None
    target_brand_name: str | None
    target_profile_hash: str
    candidates: tuple[M14CandidateInput, ...]


@dataclass(frozen=True)
class Core3SelectionRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class Core3SelectionRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M12 候选池": self._count_current_rows(entities.Core3CandidatePool, batch_id),
            "M13 组件评分": self._count_current_rows(entities.Core3CandidateComponentScore, batch_id),
            "M13 角色评分": self._count_current_rows(entities.Core3CandidateRoleScore, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M14InputBlockedError(f"M14 需要先完成上游产物：{', '.join(missing)}。")

    def list_target_inputs(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
        max_targets: int | None = None,
        only_unselected: bool = False,
    ) -> list[M14TargetInput]:
        target_codes = self.list_current_score_target_codes(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
            max_targets=max_targets,
            only_unselected=only_unselected,
        )
        if not target_codes:
            return []
        score_stmt = self._current_query(entities.Core3CandidateComponentScore, batch_id).order_by(
            entities.Core3CandidateComponentScore.target_sku_code,
            entities.Core3CandidateComponentScore.component_total_score.desc(),
            entities.Core3CandidateComponentScore.candidate_sku_code,
        ).where(entities.Core3CandidateComponentScore.target_sku_code.in_(target_codes))
        component_scores = self._paged_scalars(score_stmt, limit=100000, offset=0)
        if not component_scores:
            return []

        pool_ids = tuple({score.candidate_pool_id for score in component_scores})
        component_score_ids = tuple({score.candidate_component_score_id for score in component_scores})
        snapshot_ids = tuple({score.feature_snapshot_id for score in component_scores})
        pools_by_id = self._list_pools_by_id(batch_id, pool_ids)
        snapshots_by_id = self._list_snapshots_by_id(batch_id, snapshot_ids)
        roles_by_component = self._list_roles_by_component(batch_id, component_score_ids)
        explanations_by_component = self._list_explanations_by_component(batch_id, component_score_ids)
        issues_by_component = self._list_issues_by_component(batch_id, component_score_ids)

        candidates_by_target: dict[str, list[M14CandidateInput]] = {}
        for score in component_scores:
            pool = pools_by_id.get(score.candidate_pool_id)
            if pool is None:
                continue
            candidate = M14CandidateInput(
                pool=pool,
                snapshot=snapshots_by_id.get(score.feature_snapshot_id),
                component_score=score,
                role_scores=dict(roles_by_component.get(score.candidate_component_score_id, {})),
                explanations=tuple(explanations_by_component.get(score.candidate_component_score_id, ())),
                score_issues=tuple(issues_by_component.get(score.candidate_component_score_id, ())),
            )
            candidates_by_target.setdefault(score.target_sku_code, []).append(candidate)

        result: list[M14TargetInput] = []
        for target_sku_code, candidates in sorted(candidates_by_target.items()):
            first = candidates[0].pool
            result.append(
                M14TargetInput(
                    target_sku_code=target_sku_code,
                    target_model_name=first.target_model_name,
                    target_brand_name=first.target_brand_name,
                    target_profile_hash=first.target_profile_hash,
                    candidates=tuple(candidates),
                )
            )
        return result

    def list_current_score_target_codes(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
        max_targets: int | None = None,
        only_unselected: bool = False,
    ) -> tuple[str, ...]:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(entities.Core3CandidateComponentScore.target_sku_code)
            .distinct()
            .where(entities.Core3CandidateComponentScore.project_id == self.project_id)
            .where(entities.Core3CandidateComponentScore.category_code == self.category_code.value)
            .where(entities.Core3CandidateComponentScore.batch_id == batch_id)
            .where(entities.Core3CandidateComponentScore.is_current.is_(True))
            .order_by(entities.Core3CandidateComponentScore.target_sku_code)
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CandidateComponentScore.target_sku_code.in_(sku_scope_tuple))
        if only_unselected:
            stmt = stmt.where(~self._selection_run_exists(batch_id, rule_version))
        limit = max_targets if max_targets is not None and max_targets > 0 else 100000
        return tuple(str(row[0]) for row in self.db.execute(stmt.limit(limit)).all())

    def count_current_score_targets(self, batch_id: str, *, sku_scope: Sequence[str] = ()) -> int:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(func.count(func.distinct(entities.Core3CandidateComponentScore.target_sku_code)))
            .where(entities.Core3CandidateComponentScore.project_id == self.project_id)
            .where(entities.Core3CandidateComponentScore.category_code == self.category_code.value)
            .where(entities.Core3CandidateComponentScore.batch_id == batch_id)
            .where(entities.Core3CandidateComponentScore.is_current.is_(True))
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CandidateComponentScore.target_sku_code.in_(sku_scope_tuple))
        return int(self.db.execute(stmt).scalar_one())

    def count_current_selection_run_targets(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
    ) -> int:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(func.count(func.distinct(entities.Core3CompetitorSelectionRun.target_sku_code)))
            .where(entities.Core3CompetitorSelectionRun.project_id == self.project_id)
            .where(entities.Core3CompetitorSelectionRun.category_code == self.category_code.value)
            .where(entities.Core3CompetitorSelectionRun.batch_id == batch_id)
            .where(entities.Core3CompetitorSelectionRun.rule_version == rule_version)
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CompetitorSelectionRun.target_sku_code.in_(sku_scope_tuple))
        return int(self.db.execute(stmt).scalar_one())

    def save_selection_runs(self, records: Sequence[Any]) -> Core3SelectionRepositoryWriteResult:
        return self._save_many(
            entities.Core3CompetitorSelectionRun,
            records,
            unique_fields=("batch_id", "target_sku_code", "rule_version"),
        )

    def save_selections(self, records: Sequence[Any]) -> Core3SelectionRepositoryWriteResult:
        return self._save_many(
            entities.Core3CompetitorSelection,
            records,
            unique_fields=("batch_id", "target_sku_code", "slot_code", "rule_version"),
        )

    def save_slot_decisions(self, records: Sequence[Any]) -> Core3SelectionRepositoryWriteResult:
        return self._save_many(
            entities.Core3CompetitorSlotDecision,
            records,
            unique_fields=("batch_id", "target_sku_code", "slot_code", "rule_version"),
        )

    def save_audits(self, records: Sequence[Any]) -> Core3SelectionRepositoryWriteResult:
        return self._save_many(
            entities.Core3CompetitorSelectionAudit,
            records,
            unique_fields=("batch_id", "target_sku_code", "candidate_sku_code", "rule_version"),
        )

    def save_review_issues(self, records: Sequence[Any]) -> Core3SelectionRepositoryWriteResult:
        return self._save_many(
            entities.Core3CompetitorSelectionReviewIssue,
            records,
            unique_fields=(
                "batch_id",
                "target_sku_code",
                "candidate_sku_code",
                "slot_code",
                "issue_scope",
                "issue_type",
                "input_fingerprint",
            ),
        )

    def list_current_selection_runs(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CompetitorSelectionRun]:
        stmt = self._current_query(entities.Core3CompetitorSelectionRun, batch_id).order_by(
            entities.Core3CompetitorSelectionRun.target_sku_code,
            entities.Core3CompetitorSelectionRun.updated_at.desc(),
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionRun.target_sku_code == target_sku_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_selections(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        slot_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CompetitorSelection]:
        stmt = self._current_query(entities.Core3CompetitorSelection, batch_id).order_by(
            entities.Core3CompetitorSelection.target_sku_code,
            entities.Core3CompetitorSelection.selection_rank,
            entities.Core3CompetitorSelection.slot_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelection.target_sku_code == target_sku_code)
        if slot_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelection.slot_code == slot_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_slot_decisions(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        slot_code: str | None = None,
        decision_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CompetitorSlotDecision]:
        stmt = self._current_query(entities.Core3CompetitorSlotDecision, batch_id).order_by(
            entities.Core3CompetitorSlotDecision.target_sku_code,
            entities.Core3CompetitorSlotDecision.slot_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSlotDecision.target_sku_code == target_sku_code)
        if slot_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSlotDecision.slot_code == slot_code)
        if decision_status is not None:
            stmt = stmt.where(entities.Core3CompetitorSlotDecision.decision_status == decision_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_audits(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        audit_decision: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CompetitorSelectionAudit]:
        stmt = self._current_query(entities.Core3CompetitorSelectionAudit, batch_id).order_by(
            entities.Core3CompetitorSelectionAudit.target_sku_code,
            entities.Core3CompetitorSelectionAudit.audit_decision,
            entities.Core3CompetitorSelectionAudit.candidate_sku_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionAudit.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionAudit.candidate_sku_code == candidate_sku_code)
        if audit_decision is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionAudit.audit_decision == audit_decision)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_review_issues(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        candidate_sku_code: str | None = None,
        slot_code: str | None = None,
        issue_type: str | None = None,
        issue_level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3CompetitorSelectionReviewIssue]:
        stmt = self._current_query(entities.Core3CompetitorSelectionReviewIssue, batch_id).order_by(
            entities.Core3CompetitorSelectionReviewIssue.issue_level.desc(),
            entities.Core3CompetitorSelectionReviewIssue.target_sku_code,
            entities.Core3CompetitorSelectionReviewIssue.slot_code,
            entities.Core3CompetitorSelectionReviewIssue.candidate_sku_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionReviewIssue.target_sku_code == target_sku_code)
        if candidate_sku_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionReviewIssue.candidate_sku_code == candidate_sku_code)
        if slot_code is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionReviewIssue.slot_code == slot_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionReviewIssue.issue_type == issue_type)
        if issue_level is not None:
            stmt = stmt.where(entities.Core3CompetitorSelectionReviewIssue.issue_level == issue_level)
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

    def _selection_run_exists(self, batch_id: str, rule_version: str) -> Any:
        return (
            select(entities.Core3CompetitorSelectionRun.selection_run_id)
            .where(entities.Core3CompetitorSelectionRun.project_id == self.project_id)
            .where(entities.Core3CompetitorSelectionRun.category_code == self.category_code.value)
            .where(entities.Core3CompetitorSelectionRun.batch_id == batch_id)
            .where(entities.Core3CompetitorSelectionRun.rule_version == rule_version)
            .where(entities.Core3CompetitorSelectionRun.target_sku_code == entities.Core3CandidateComponentScore.target_sku_code)
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
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

    def _list_pools_by_id(
        self,
        batch_id: str,
        pool_ids: tuple[str, ...],
    ) -> dict[str, entities.Core3CandidatePool]:
        if not pool_ids:
            return {}
        stmt = self._current_query(entities.Core3CandidatePool, batch_id).where(
            entities.Core3CandidatePool.candidate_pool_id.in_(pool_ids)
        )
        return {row.candidate_pool_id: row for row in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _list_snapshots_by_id(
        self,
        batch_id: str,
        snapshot_ids: tuple[str, ...],
    ) -> dict[str, entities.Core3CandidateFeatureSnapshot]:
        if not snapshot_ids:
            return {}
        stmt = self._current_query(entities.Core3CandidateFeatureSnapshot, batch_id).where(
            entities.Core3CandidateFeatureSnapshot.candidate_feature_snapshot_id.in_(snapshot_ids)
        )
        return {row.candidate_feature_snapshot_id: row for row in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _list_roles_by_component(
        self,
        batch_id: str,
        component_score_ids: tuple[str, ...],
    ) -> dict[str, dict[str, entities.Core3CandidateRoleScore]]:
        if not component_score_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateRoleScore, batch_id)
            .where(entities.Core3CandidateRoleScore.candidate_component_score_id.in_(component_score_ids))
            .order_by(
                entities.Core3CandidateRoleScore.candidate_component_score_id,
                entities.Core3CandidateRoleScore.role_code,
            )
        )
        result: dict[str, dict[str, entities.Core3CandidateRoleScore]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.candidate_component_score_id, {})[row.role_code] = row
        return result

    def _list_explanations_by_component(
        self,
        batch_id: str,
        component_score_ids: tuple[str, ...],
    ) -> dict[str, list[entities.Core3CandidateComponentExplanation]]:
        if not component_score_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateComponentExplanation, batch_id)
            .where(entities.Core3CandidateComponentExplanation.candidate_component_score_id.in_(component_score_ids))
            .order_by(
                entities.Core3CandidateComponentExplanation.candidate_component_score_id,
                entities.Core3CandidateComponentExplanation.component_code,
            )
        )
        result: dict[str, list[entities.Core3CandidateComponentExplanation]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.candidate_component_score_id, []).append(row)
        return result

    def _list_issues_by_component(
        self,
        batch_id: str,
        component_score_ids: tuple[str, ...],
    ) -> dict[str, list[entities.Core3CandidateScoreReviewIssue]]:
        if not component_score_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateScoreReviewIssue, batch_id)
            .where(entities.Core3CandidateScoreReviewIssue.candidate_component_score_id.in_(component_score_ids))
            .where(entities.Core3CandidateScoreReviewIssue.resolved_status == "open")
            .order_by(
                entities.Core3CandidateScoreReviewIssue.candidate_component_score_id,
                entities.Core3CandidateScoreReviewIssue.issue_level.desc(),
                entities.Core3CandidateScoreReviewIssue.issue_type,
            )
        )
        result: dict[str, list[entities.Core3CandidateScoreReviewIssue]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            if row.candidate_component_score_id:
                result.setdefault(row.candidate_component_score_id, []).append(row)
        return result

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> Core3SelectionRepositoryWriteResult:
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
        return Core3SelectionRepositoryWriteResult(tuple(records), created_count, reused_count, updated_count)

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
            raise TypeError("M14 repository payload must be a mapping or Pydantic model")
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
