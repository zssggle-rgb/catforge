"""Read-only repositories for the sellpoint-value candidate universe."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.analyst_repository import batch_ids_from_scope
from app.services.core3_real_data.constants import (
    CORE3_M12_RULE_VERSION,
    CORE3_M13_RULE_VERSION,
    CORE3_M14_RULE_VERSION,
)


class SellpointValueCandidateUniverseRepository:
    """Load all current M12/M13 candidates with M14 as an optional label."""

    def __init__(self, db: Session, *, project_id: str, category_code: str) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = category_code

    def load_candidate_records(
        self,
        *,
        batch_id: str,
        target_sku_code: str,
    ) -> list[dict[str, Any]]:
        scope = tuple(batch_ids_from_scope(batch_id)) or (batch_id,)
        pools = self._candidate_pools(scope, target_sku_code)
        selected_pools = _select_scope_rows(
            pools,
            scope=scope,
            key=lambda row: str(row.candidate_sku_code),
        )
        pool_ids = [row.candidate_pool_id for row in selected_pools]
        components = _first_by_pool(self._component_scores(scope, pool_ids))
        roles_by_pool: dict[str, list[Any]] = defaultdict(list)
        for row in self._role_scores(scope, pool_ids):
            roles_by_pool[row.candidate_pool_id].append(row)
        features = _first_by_pool(self._feature_snapshots(scope, pool_ids))
        selection_rows = _select_scope_rows(
            self._m14_selections(scope, target_sku_code),
            scope=scope,
            key=lambda row: str(row.candidate_sku_code),
        )
        selections = {str(row.candidate_sku_code): row for row in selection_rows}
        return [
            _candidate_record(
                pool,
                component=components.get(pool.candidate_pool_id),
                roles=roles_by_pool.get(pool.candidate_pool_id, []),
                feature=features.get(pool.candidate_pool_id),
                selection=selections.get(str(pool.candidate_sku_code)),
            )
            for pool in selected_pools
        ]

    def _candidate_pools(
        self, scope: Sequence[str], target_sku_code: str
    ) -> list[entities.Core3CandidatePool]:
        stmt = (
            select(entities.Core3CandidatePool)
            .where(entities.Core3CandidatePool.project_id == self.project_id)
            .where(entities.Core3CandidatePool.category_code == self.category_code)
            .where(entities.Core3CandidatePool.batch_id.in_(scope))
            .where(entities.Core3CandidatePool.target_sku_code == target_sku_code)
            .where(entities.Core3CandidatePool.rule_version == CORE3_M12_RULE_VERSION)
            .where(entities.Core3CandidatePool.is_current.is_(True))
            .order_by(
                entities.Core3CandidatePool.candidate_sku_code,
                entities.Core3CandidatePool.recall_priority_score.desc(),
                entities.Core3CandidatePool.candidate_pool_id,
            )
        )
        return list(self.db.execute(stmt).scalars())

    def _component_scores(
        self, scope: Sequence[str], pool_ids: Sequence[str]
    ) -> list[entities.Core3CandidateComponentScore]:
        if not pool_ids:
            return []
        stmt = (
            select(entities.Core3CandidateComponentScore)
            .where(entities.Core3CandidateComponentScore.project_id == self.project_id)
            .where(entities.Core3CandidateComponentScore.category_code == self.category_code)
            .where(entities.Core3CandidateComponentScore.batch_id.in_(scope))
            .where(entities.Core3CandidateComponentScore.candidate_pool_id.in_(pool_ids))
            .where(entities.Core3CandidateComponentScore.rule_version == CORE3_M13_RULE_VERSION)
            .where(entities.Core3CandidateComponentScore.is_current.is_(True))
            .order_by(
                entities.Core3CandidateComponentScore.candidate_pool_id,
                entities.Core3CandidateComponentScore.component_total_score.desc(),
            )
        )
        return list(self.db.execute(stmt).scalars())

    def _role_scores(
        self, scope: Sequence[str], pool_ids: Sequence[str]
    ) -> list[entities.Core3CandidateRoleScore]:
        if not pool_ids:
            return []
        stmt = (
            select(entities.Core3CandidateRoleScore)
            .where(entities.Core3CandidateRoleScore.project_id == self.project_id)
            .where(entities.Core3CandidateRoleScore.category_code == self.category_code)
            .where(entities.Core3CandidateRoleScore.batch_id.in_(scope))
            .where(entities.Core3CandidateRoleScore.candidate_pool_id.in_(pool_ids))
            .where(entities.Core3CandidateRoleScore.rule_version == CORE3_M13_RULE_VERSION)
            .where(entities.Core3CandidateRoleScore.is_current.is_(True))
            .order_by(
                entities.Core3CandidateRoleScore.candidate_pool_id,
                entities.Core3CandidateRoleScore.role_score.desc(),
                entities.Core3CandidateRoleScore.role_code,
            )
        )
        return list(self.db.execute(stmt).scalars())

    def _feature_snapshots(
        self, scope: Sequence[str], pool_ids: Sequence[str]
    ) -> list[entities.Core3CandidateFeatureSnapshot]:
        if not pool_ids:
            return []
        stmt = (
            select(entities.Core3CandidateFeatureSnapshot)
            .where(entities.Core3CandidateFeatureSnapshot.project_id == self.project_id)
            .where(entities.Core3CandidateFeatureSnapshot.category_code == self.category_code)
            .where(entities.Core3CandidateFeatureSnapshot.batch_id.in_(scope))
            .where(entities.Core3CandidateFeatureSnapshot.candidate_pool_id.in_(pool_ids))
            .where(
                entities.Core3CandidateFeatureSnapshot.rule_version
                == CORE3_M12_RULE_VERSION
            )
            .where(entities.Core3CandidateFeatureSnapshot.is_current.is_(True))
            .order_by(
                entities.Core3CandidateFeatureSnapshot.candidate_pool_id,
                entities.Core3CandidateFeatureSnapshot.candidate_feature_snapshot_id,
            )
        )
        return list(self.db.execute(stmt).scalars())

    def _m14_selections(
        self, scope: Sequence[str], target_sku_code: str
    ) -> list[entities.Core3CompetitorSelection]:
        stmt = (
            select(entities.Core3CompetitorSelection)
            .join(
                entities.Core3CompetitorSelectionRun,
                entities.Core3CompetitorSelectionRun.selection_run_id
                == entities.Core3CompetitorSelection.selection_run_id,
            )
            .where(entities.Core3CompetitorSelection.project_id == self.project_id)
            .where(entities.Core3CompetitorSelection.category_code == self.category_code)
            .where(entities.Core3CompetitorSelection.batch_id.in_(scope))
            .where(entities.Core3CompetitorSelection.target_sku_code == target_sku_code)
            .where(entities.Core3CompetitorSelection.rule_version == CORE3_M14_RULE_VERSION)
            .where(entities.Core3CompetitorSelection.is_current.is_(True))
            .where(entities.Core3CompetitorSelection.review_required.is_(False))
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
            .where(
                entities.Core3CompetitorSelectionRun.rule_version
                == CORE3_M14_RULE_VERSION
            )
            .where(entities.Core3CompetitorSelectionRun.review_required.is_(False))
            .order_by(
                entities.Core3CompetitorSelection.selection_rank,
                entities.Core3CompetitorSelection.candidate_sku_code,
            )
        )
        return list(self.db.execute(stmt).scalars())


def _select_scope_rows(
    rows: Sequence[Any],
    *,
    scope: Sequence[str],
    key: Any,
) -> list[Any]:
    rank = {batch: index for index, batch in enumerate(scope)}
    selected: dict[Any, Any] = {}
    for row in rows:
        row_key = key(row)
        current = selected.get(row_key)
        if current is None or rank.get(str(row.batch_id), len(rank)) < rank.get(
            str(current.batch_id), len(rank)
        ):
            selected[row_key] = row
    return [selected[row_key] for row_key in sorted(selected)]


def _first_by_pool(rows: Sequence[Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for row in rows:
        selected.setdefault(str(row.candidate_pool_id), row)
    return selected


def _candidate_record(
    pool: entities.Core3CandidatePool,
    *,
    component: entities.Core3CandidateComponentScore | None,
    roles: Sequence[entities.Core3CandidateRoleScore],
    feature: entities.Core3CandidateFeatureSnapshot | None,
    selection: entities.Core3CompetitorSelection | None,
) -> dict[str, Any]:
    return {
        "candidate_sku_code": pool.candidate_sku_code,
        "candidate_brand_name": pool.candidate_brand_name,
        "candidate_model_name": pool.candidate_model_name,
        "same_brand_flag": pool.same_brand_flag,
        "primary_relation_type": pool.primary_relation_type,
        "relation_types": list(pool.relation_types_json or []),
        "recall_sources": list(pool.recall_sources_json or []),
        "recall_strength": pool.recall_strength,
        "recall_priority_score": pool.recall_priority_score,
        "processing_status": pool.processing_status,
        "review_required": pool.review_required,
        "review_reasons": list((pool.review_reason_json or {}).get("reasons") or []),
        "pool_record_id": pool.candidate_pool_id,
        "pool_evidence_ids": list(getattr(pool, "evidence_ids", None) or []),
        "pool_result_hash": pool.result_hash,
        "component": (
            {
                "component_total_score": component.component_total_score,
                "sample_status": component.sample_status,
                "processing_status": component.processing_status,
                "review_required": component.review_required,
                "review_reasons": [component.review_reason]
                if component.review_reason
                else [],
                "record_id": getattr(
                    component, "candidate_component_score_id", None
                ),
                "evidence_ids": list(
                    getattr(component, "evidence_ids", None) or []
                ),
                "result_hash": component.result_hash,
            }
            if component
            else None
        ),
        "roles": [
            {
                "role_code": row.role_code,
                "role_name_cn": row.role_name_cn,
                "role_score": row.role_score,
                "role_confidence": row.role_confidence,
                "auto_select_eligible": row.auto_select_eligible,
                "review_required": row.review_required,
            }
            for row in roles
        ],
        "feature": (
            {
                "market_feature": dict(feature.market_feature_json or {}),
                "param_feature": dict(feature.param_feature_json or {}),
                "claim_value_overlap": dict(feature.claim_value_overlap_json or {}),
                "battlefield_overlap": dict(feature.battlefield_overlap_json or {}),
                "task_overlap": dict(feature.task_overlap_json or {}),
                "audience_overlap": dict(feature.audience_overlap_json or {}),
                "record_id": getattr(
                    feature, "candidate_feature_snapshot_id", None
                ),
                "evidence_ids": list(getattr(feature, "evidence_ids", None) or []),
                "feature_snapshot_hash": feature.feature_snapshot_hash,
            }
            if feature
            else {}
        ),
        "selection": (
            {
                "slot_code": selection.slot_code,
                "slot_name_cn": selection.slot_name_cn,
                "selection_rank": selection.selection_rank,
                "record_id": getattr(selection, "competitor_selection_id", None),
                "evidence_ids": list(
                    getattr(selection, "evidence_ids", None) or []
                ),
                "result_hash": selection.result_hash,
            }
            if selection
            else None
        ),
    }


__all__ = ["SellpointValueCandidateUniverseRepository"]
