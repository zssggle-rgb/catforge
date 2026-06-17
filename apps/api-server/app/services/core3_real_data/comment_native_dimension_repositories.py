"""M08.4 comment-native dimension repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M084InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M084InputBundle:
    profiles: tuple[entities.Core3SkuSignalProfile, ...]
    matrices: tuple[entities.Core3SkuSignalEvidenceMatrix, ...]
    comment_atoms: tuple[entities.Core3CommentEvidenceAtom, ...]
    downstream_signals: tuple[entities.Core3CommentDownstreamSignal, ...]
    market_profiles: tuple[entities.Core3SkuMarketProfile, ...] = ()
    param_values: tuple[entities.Core3ExtractParamValue, ...] = ()
    param_profiles: tuple[entities.Core3SkuParamProfile, ...] = ()
    claim_activation_bases: tuple[entities.Core3SkuClaimActivationBase, ...] = ()
    claim_activations: tuple[entities.Core3SkuClaimActivation, ...] = ()


@dataclass(frozen=True)
class M084WriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class CommentNativeDimensionRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M08 SKU 综合信号画像": self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
            "M08 证据矩阵": self._count_current_rows(entities.Core3SkuSignalEvidenceMatrix, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M084InputBlockedError(f"M08.4 需要先完成上游产物：{', '.join(missing)}。")

    def load_input_bundle(self, batch_id: str) -> M084InputBundle:
        profiles = self._paged_scalars(
            self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
                entities.Core3SkuSignalProfile.sku_code
            )
        )
        matrices = self._paged_scalars(
            self._current_query(entities.Core3SkuSignalEvidenceMatrix, batch_id).order_by(
                entities.Core3SkuSignalEvidenceMatrix.sku_code,
                entities.Core3SkuSignalEvidenceMatrix.domain,
                entities.Core3SkuSignalEvidenceMatrix.sub_domain,
            )
        )
        comment_atoms = self._paged_scalars(
            self._current_query(entities.Core3CommentEvidenceAtom, batch_id)
            .where(entities.Core3CommentEvidenceAtom.usable_for_downstream.is_(True))
            .where(entities.Core3CommentEvidenceAtom.low_value_flag.is_(False))
            .order_by(entities.Core3CommentEvidenceAtom.sku_code, entities.Core3CommentEvidenceAtom.comment_evidence_id)
        )
        downstream_signals = self._paged_scalars(
            self._current_query(entities.Core3CommentDownstreamSignal, batch_id).order_by(
                entities.Core3CommentDownstreamSignal.sku_code,
                entities.Core3CommentDownstreamSignal.signal_type,
                entities.Core3CommentDownstreamSignal.target_code_hint,
            )
        )
        sku_codes = tuple(sorted({profile.sku_code for profile in profiles}))
        market_profiles = self._list_market_profiles(batch_id, sku_codes)
        param_values = self._list_param_values(batch_id, sku_codes)
        param_profiles = self._list_param_profiles(batch_id, sku_codes)
        claim_activation_bases = self._list_claim_activation_bases(batch_id, sku_codes)
        claim_activations = self._list_claim_activations(batch_id, sku_codes)
        return M084InputBundle(
            profiles=tuple(profiles),
            matrices=tuple(matrices),
            comment_atoms=tuple(comment_atoms),
            downstream_signals=tuple(downstream_signals),
            market_profiles=tuple(market_profiles),
            param_values=tuple(param_values),
            param_profiles=tuple(param_profiles),
            claim_activation_bases=tuple(claim_activation_bases),
            claim_activations=tuple(claim_activations),
        )

    def supersede_current_outputs(self, batch_id: str, *, rule_version: str) -> int:
        total = 0
        total += self._mark_current_inactive(
            entities.Core3CommentNativeSignal,
            batch_id,
            version_field="source_rule_version",
            version_value=rule_version,
        )
        for model_cls in (
            entities.Core3NativeDimensionCandidate,
            entities.Core3NativeDimensionSkuSupport,
            entities.Core3NativeDimensionAlignmentProposal,
            entities.Core3NativeDimensionReviewIssue,
        ):
            total += self._mark_current_inactive(
                model_cls,
                batch_id,
                version_field="rule_version",
                version_value=rule_version,
            )
        self.db.flush()
        return total

    def save_signals(self, records: Sequence[Any]) -> M084WriteResult:
        return self._save_many(
            entities.Core3CommentNativeSignal,
            records,
            unique_fields=("batch_id", "native_signal_code", "source_rule_version"),
        )

    def save_candidates(self, records: Sequence[Any]) -> M084WriteResult:
        return self._save_many(
            entities.Core3NativeDimensionCandidate,
            records,
            unique_fields=("batch_id", "dimension_type", "native_dimension_code", "rule_version"),
        )

    def save_sku_supports(self, records: Sequence[Any]) -> M084WriteResult:
        return self._save_many(
            entities.Core3NativeDimensionSkuSupport,
            records,
            unique_fields=("native_dimension_id", "sku_code", "rule_version"),
        )

    def save_alignments(self, records: Sequence[Any]) -> M084WriteResult:
        return self._save_many(
            entities.Core3NativeDimensionAlignmentProposal,
            records,
            unique_fields=("batch_id", "alignment_key", "rule_version"),
        )

    def save_issues(self, records: Sequence[Any]) -> M084WriteResult:
        return self._save_many(
            entities.Core3NativeDimensionReviewIssue,
            records,
            unique_fields=("batch_id", "issue_key", "rule_version"),
        )

    def list_current_candidates(
        self,
        batch_id: str,
        *,
        dimension_type: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[entities.Core3NativeDimensionCandidate]:
        stmt = self._current_query(entities.Core3NativeDimensionCandidate, batch_id).order_by(
            entities.Core3NativeDimensionCandidate.dimension_type,
            entities.Core3NativeDimensionCandidate.native_support_score.desc(),
            entities.Core3NativeDimensionCandidate.native_dimension_code,
        )
        if dimension_type:
            stmt = stmt.where(entities.Core3NativeDimensionCandidate.dimension_type == dimension_type)
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

    def _list_param_values(self, batch_id: str, sku_codes: Sequence[str]) -> list[entities.Core3ExtractParamValue]:
        if not sku_codes:
            return []
        stmt = (
            self._base_query(entities.Core3ExtractParamValue, batch_id)
            .where(entities.Core3ExtractParamValue.sku_code.in_(sku_codes))
            .order_by(
                entities.Core3ExtractParamValue.sku_code,
                entities.Core3ExtractParamValue.param_code,
                entities.Core3ExtractParamValue.source_priority_rank,
            )
        )
        return self._paged_scalars(stmt)

    def _list_market_profiles(self, batch_id: str, sku_codes: Sequence[str]) -> list[entities.Core3SkuMarketProfile]:
        if not sku_codes:
            return []
        stmt = (
            self._current_query(entities.Core3SkuMarketProfile, batch_id)
            .where(entities.Core3SkuMarketProfile.sku_code.in_(sku_codes))
            .order_by(
                entities.Core3SkuMarketProfile.sku_code,
                entities.Core3SkuMarketProfile.market_confidence.desc(),
                entities.Core3SkuMarketProfile.analysis_window,
            )
        )
        return self._paged_scalars(stmt)

    def _list_param_profiles(self, batch_id: str, sku_codes: Sequence[str]) -> list[entities.Core3SkuParamProfile]:
        if not sku_codes:
            return []
        stmt = (
            self._base_query(entities.Core3SkuParamProfile, batch_id)
            .where(entities.Core3SkuParamProfile.sku_code.in_(sku_codes))
            .order_by(entities.Core3SkuParamProfile.sku_code, entities.Core3SkuParamProfile.updated_at.desc())
        )
        return self._paged_scalars(stmt)

    def _list_claim_activation_bases(
        self,
        batch_id: str,
        sku_codes: Sequence[str],
    ) -> list[entities.Core3SkuClaimActivationBase]:
        if not sku_codes:
            return []
        stmt = (
            self._base_query(entities.Core3SkuClaimActivationBase, batch_id)
            .where(entities.Core3SkuClaimActivationBase.sku_code.in_(sku_codes))
            .order_by(
                entities.Core3SkuClaimActivationBase.sku_code,
                entities.Core3SkuClaimActivationBase.claim_code,
            )
        )
        return self._paged_scalars(stmt)

    def _list_claim_activations(self, batch_id: str, sku_codes: Sequence[str]) -> list[entities.Core3SkuClaimActivation]:
        if not sku_codes:
            return []
        stmt = (
            self._current_query(entities.Core3SkuClaimActivation, batch_id)
            .where(entities.Core3SkuClaimActivation.sku_code.in_(sku_codes))
            .order_by(
                entities.Core3SkuClaimActivation.sku_code,
                entities.Core3SkuClaimActivation.claim_code,
            )
        )
        return self._paged_scalars(stmt)

    def _paged_scalars(self, stmt: Any, *, limit: int = 100000, offset: int = 0) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=250000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())

    def _mark_current_inactive(
        self,
        model_cls: Any,
        batch_id: str,
        *,
        version_field: str,
        version_value: str,
    ) -> int:
        rows = self._paged_scalars(
            self._current_query(model_cls, batch_id).where(getattr(model_cls, version_field) == version_value),
            limit=250000,
        )
        for row in rows:
            row.is_current = False
        return len(rows)

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> M084WriteResult:
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
        return M084WriteResult(tuple(records), created_count=created_count, reused_count=reused_count, updated_count=updated_count)

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
            raise TypeError("M08.4 repository payload must be a mapping or Pydantic model")
        if not raw_payload.get("project_id"):
            raw_payload["project_id"] = self.project_id
        if not raw_payload.get("category_code"):
            raw_payload["category_code"] = self.category_code.value
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in raw_payload.items() if key in model_fields and value is not None}

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
        )
        for field_name in unique_fields:
            value = payload.get(field_name)
            if value is None:
                stmt = stmt.where(getattr(model_cls, field_name).is_(None))
            else:
                stmt = stmt.where(getattr(model_cls, field_name) == _jsonable_value(value, nested=False))
        return self.db.execute(stmt).scalars().first()

    def _find_by_stable_identifier(self, model_cls: Any, payload: Mapping[str, Any]) -> Any | None:
        identifier_field = _stable_identifier_field(model_cls)
        if identifier_field is None or not payload.get(identifier_field):
            return None
        return (
            self.db.execute(
                select(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(getattr(model_cls, identifier_field) == payload[identifier_field])
            )
            .scalars()
            .first()
        )


def _stable_identifier_field(model_cls: Any) -> str | None:
    mapping = {
        entities.Core3CommentNativeSignal: "native_signal_id",
        entities.Core3NativeDimensionCandidate: "native_dimension_id",
        entities.Core3NativeDimensionSkuSupport: "native_dimension_sku_support_id",
        entities.Core3NativeDimensionAlignmentProposal: "alignment_proposal_id",
        entities.Core3NativeDimensionReviewIssue: "native_dimension_issue_id",
    }
    return mapping.get(model_cls)


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
    if hasattr(existing, "is_current"):
        existing.is_current = True
