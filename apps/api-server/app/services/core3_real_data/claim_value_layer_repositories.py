"""M11.5 claim value layer repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.constants import M08ForModule
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3BaseRepository


class M115InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M115InputBundle:
    profile: entities.Core3SkuSignalProfile
    feature_view: entities.Core3SkuDownstreamFeatureView | None
    evidence_matrices: tuple[entities.Core3SkuSignalEvidenceMatrix, ...]
    battlefield_scores: tuple[entities.Core3SkuBattlefieldScore, ...]
    battlefield_breakdowns: tuple[entities.Core3SkuBattlefieldEvidenceBreakdown, ...]
    battlefield_portfolio: entities.Core3SkuBattlefieldPortfolio | None
    battlefield_score_fingerprint: str


@dataclass(frozen=True)
class ClaimValueRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class ClaimValueLayerRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M08 SKU 综合信号画像": self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
            "M08 M11.5 特征视图": self._count_current_rows(
                entities.Core3SkuDownstreamFeatureView,
                batch_id,
                for_module=M08ForModule.M11_5.value,
            ),
            "M11 价值战场分数": self._count_current_rows(entities.Core3SkuBattlefieldScore, batch_id),
            "M11 价值战场组合画像": self._count_current_rows(entities.Core3SkuBattlefieldPortfolio, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M115InputBlockedError(f"M11.5 需要先完成上游产物：{', '.join(missing)}。")

    def list_input_bundles(self, batch_id: str, sku_scope: Sequence[str] = ()) -> list[M115InputBundle]:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        profile_stmt = self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
            entities.Core3SkuSignalProfile.sku_code
        )
        if sku_scope_tuple:
            profile_stmt = profile_stmt.where(entities.Core3SkuSignalProfile.sku_code.in_(sku_scope_tuple))
        profiles = self._paged_scalars(profile_stmt, limit=100000, offset=0)
        views_by_sku = self._list_views_by_sku(batch_id, sku_scope_tuple)
        matrices_by_sku = self._list_matrices_by_sku(batch_id, sku_scope_tuple)
        scores_by_sku = self._list_battlefield_scores_by_sku(batch_id, sku_scope_tuple)
        breakdowns_by_sku = self._list_battlefield_breakdowns_by_sku(batch_id, sku_scope_tuple)
        portfolios_by_sku = self._list_battlefield_portfolios_by_sku(batch_id, sku_scope_tuple)
        return [
            M115InputBundle(
                profile=profile,
                feature_view=views_by_sku.get(profile.sku_code),
                evidence_matrices=tuple(matrices_by_sku.get(profile.sku_code, ())),
                battlefield_scores=tuple(scores_by_sku.get(profile.sku_code, ())),
                battlefield_breakdowns=tuple(breakdowns_by_sku.get(profile.sku_code, ())),
                battlefield_portfolio=portfolios_by_sku.get(profile.sku_code),
                battlefield_score_fingerprint=_battlefield_score_fingerprint(
                    scores_by_sku.get(profile.sku_code, ()),
                    breakdowns_by_sku.get(profile.sku_code, ()),
                    portfolios_by_sku.get(profile.sku_code),
                ),
            )
            for profile in profiles
        ]

    def save_candidates(self, records: Sequence[Any]) -> ClaimValueRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuBattlefieldClaimCandidate,
            records,
            unique_fields=("batch_id", "sku_code", "battlefield_code", "claim_code", "rule_version", "claim_seed_hash", "battlefield_seed_hash"),
        )

    def save_layers(self, records: Sequence[Any]) -> ClaimValueRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimValueLayer,
            records,
            unique_fields=("batch_id", "sku_code", "battlefield_code", "claim_code", "rule_version", "claim_seed_hash", "battlefield_seed_hash"),
        )

    def save_breakdowns(self, records: Sequence[Any]) -> ClaimValueRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimValueEvidenceBreakdown,
            records,
            unique_fields=("sku_claim_value_layer_id", "evidence_domain", "claim_seed_hash", "battlefield_seed_hash", "rule_version"),
        )

    def save_summaries(self, records: Sequence[Any]) -> ClaimValueRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuBattlefieldClaimValueSummary,
            records,
            unique_fields=("batch_id", "sku_code", "battlefield_code", "rule_version", "claim_seed_hash", "battlefield_seed_hash"),
        )

    def save_review_issues(self, records: Sequence[Any]) -> ClaimValueRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuClaimValueReviewIssue,
            records,
            unique_fields=("batch_id", "sku_code", "battlefield_code", "claim_code", "issue_type", "input_fingerprint"),
        )

    def list_current_candidates(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        battlefield_code: str | None = None,
        claim_code: str | None = None,
        candidate_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuBattlefieldClaimCandidate]:
        stmt = self._current_query(entities.Core3SkuBattlefieldClaimCandidate, batch_id).order_by(
            entities.Core3SkuBattlefieldClaimCandidate.sku_code,
            entities.Core3SkuBattlefieldClaimCandidate.battlefield_code,
            entities.Core3SkuBattlefieldClaimCandidate.claim_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimCandidate.sku_code == sku_code)
        if battlefield_code is not None:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimCandidate.battlefield_code == battlefield_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimCandidate.claim_code == claim_code)
        if candidate_status is not None:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimCandidate.candidate_status == candidate_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_layers(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        battlefield_code: str | None = None,
        claim_code: str | None = None,
        layer: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimValueLayer]:
        stmt = self._current_query(entities.Core3SkuClaimValueLayer, batch_id).order_by(
            entities.Core3SkuClaimValueLayer.sku_code,
            entities.Core3SkuClaimValueLayer.battlefield_code,
            entities.Core3SkuClaimValueLayer.claim_value_score.desc(),
            entities.Core3SkuClaimValueLayer.claim_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueLayer.sku_code == sku_code)
        if battlefield_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueLayer.battlefield_code == battlefield_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueLayer.claim_code == claim_code)
        if layer is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueLayer.layer == layer)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_breakdowns(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        battlefield_code: str | None = None,
        claim_code: str | None = None,
        evidence_domain: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimValueEvidenceBreakdown]:
        stmt = self._current_query(entities.Core3SkuClaimValueEvidenceBreakdown, batch_id).order_by(
            entities.Core3SkuClaimValueEvidenceBreakdown.sku_code,
            entities.Core3SkuClaimValueEvidenceBreakdown.battlefield_code,
            entities.Core3SkuClaimValueEvidenceBreakdown.claim_code,
            entities.Core3SkuClaimValueEvidenceBreakdown.evidence_domain,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueEvidenceBreakdown.sku_code == sku_code)
        if battlefield_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueEvidenceBreakdown.battlefield_code == battlefield_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueEvidenceBreakdown.claim_code == claim_code)
        if evidence_domain is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueEvidenceBreakdown.evidence_domain == evidence_domain)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_summaries(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        battlefield_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuBattlefieldClaimValueSummary]:
        stmt = self._current_query(entities.Core3SkuBattlefieldClaimValueSummary, batch_id).order_by(
            entities.Core3SkuBattlefieldClaimValueSummary.sku_code,
            entities.Core3SkuBattlefieldClaimValueSummary.battlefield_code,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimValueSummary.sku_code == sku_code)
        if battlefield_code is not None:
            stmt = stmt.where(entities.Core3SkuBattlefieldClaimValueSummary.battlefield_code == battlefield_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_review_issues(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        battlefield_code: str | None = None,
        claim_code: str | None = None,
        issue_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuClaimValueReviewIssue]:
        stmt = self._current_query(entities.Core3SkuClaimValueReviewIssue, batch_id).order_by(
            entities.Core3SkuClaimValueReviewIssue.issue_level.desc(),
            entities.Core3SkuClaimValueReviewIssue.sku_code,
            entities.Core3SkuClaimValueReviewIssue.battlefield_code,
            entities.Core3SkuClaimValueReviewIssue.claim_code,
            entities.Core3SkuClaimValueReviewIssue.issue_type,
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueReviewIssue.sku_code == sku_code)
        if battlefield_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueReviewIssue.battlefield_code == battlefield_code)
        if claim_code is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueReviewIssue.claim_code == claim_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3SkuClaimValueReviewIssue.issue_type == issue_type)
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
            .where(entities.Core3SkuDownstreamFeatureView.for_module == M08ForModule.M11_5.value)
            .order_by(entities.Core3SkuDownstreamFeatureView.sku_code)
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuDownstreamFeatureView.sku_code.in_(sku_scope))
        return {view.sku_code: view for view in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _list_matrices_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuSignalEvidenceMatrix]]:
        stmt = self._current_query(entities.Core3SkuSignalEvidenceMatrix, batch_id).order_by(
            entities.Core3SkuSignalEvidenceMatrix.sku_code,
            entities.Core3SkuSignalEvidenceMatrix.domain,
            entities.Core3SkuSignalEvidenceMatrix.sub_domain,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuSignalEvidenceMatrix.sku_code.in_(sku_scope))
        result: dict[str, list[entities.Core3SkuSignalEvidenceMatrix]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.sku_code, []).append(row)
        return result

    def _list_battlefield_scores_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuBattlefieldScore]]:
        stmt = self._current_query(entities.Core3SkuBattlefieldScore, batch_id).order_by(
            entities.Core3SkuBattlefieldScore.sku_code,
            entities.Core3SkuBattlefieldScore.battlefield_score.desc(),
            entities.Core3SkuBattlefieldScore.battlefield_code,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuBattlefieldScore.sku_code.in_(sku_scope))
        result: dict[str, list[entities.Core3SkuBattlefieldScore]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.sku_code, []).append(row)
        return result

    def _list_battlefield_breakdowns_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, list[entities.Core3SkuBattlefieldEvidenceBreakdown]]:
        stmt = self._current_query(entities.Core3SkuBattlefieldEvidenceBreakdown, batch_id).order_by(
            entities.Core3SkuBattlefieldEvidenceBreakdown.sku_code,
            entities.Core3SkuBattlefieldEvidenceBreakdown.battlefield_code,
            entities.Core3SkuBattlefieldEvidenceBreakdown.evidence_domain,
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuBattlefieldEvidenceBreakdown.sku_code.in_(sku_scope))
        result: dict[str, list[entities.Core3SkuBattlefieldEvidenceBreakdown]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.sku_code, []).append(row)
        return result

    def _list_battlefield_portfolios_by_sku(self, batch_id: str, sku_scope: tuple[str, ...]) -> dict[str, entities.Core3SkuBattlefieldPortfolio]:
        stmt = self._current_query(entities.Core3SkuBattlefieldPortfolio, batch_id).order_by(
            entities.Core3SkuBattlefieldPortfolio.sku_code
        )
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuBattlefieldPortfolio.sku_code.in_(sku_scope))
        return {row.sku_code: row for row in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> ClaimValueRepositoryWriteResult:
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
        return ClaimValueRepositoryWriteResult(tuple(records), created_count, reused_count, updated_count)

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
        _assign_existing(existing, normalized_payload)
        self.db.flush()
        return existing, "updated"

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw_payload = payload.model_dump(mode="python")
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M11.5 repository payload must be a mapping or Pydantic model")
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


def _battlefield_score_fingerprint(
    scores: Sequence[entities.Core3SkuBattlefieldScore],
    breakdowns: Sequence[entities.Core3SkuBattlefieldEvidenceBreakdown],
    portfolio: entities.Core3SkuBattlefieldPortfolio | None,
) -> str:
    return stable_hash(
        {
            "score_hashes": [row.result_hash for row in scores],
            "breakdown_hashes": [row.result_hash for row in breakdowns],
            "portfolio_hash": portfolio.result_hash if portfolio is not None else None,
        },
        version="m11_5_battlefield_score_fingerprint_v1",
    )


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


def _assign_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    _refresh_existing(existing, payload)
