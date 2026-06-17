"""M08.5 business-dimension ontology repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M085InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M085InputBundle:
    profiles: tuple[entities.Core3SkuSignalProfile, ...]
    matrices: tuple[entities.Core3SkuSignalEvidenceMatrix, ...]
    comment_atoms: tuple[entities.Core3CommentEvidenceAtom, ...]
    downstream_signals: tuple[entities.Core3CommentDownstreamSignal, ...]
    native_dimension_candidates: tuple[entities.Core3NativeDimensionCandidate, ...]
    native_dimension_sku_supports: tuple[entities.Core3NativeDimensionSkuSupport, ...]
    native_dimension_alignments: tuple[entities.Core3NativeDimensionAlignmentProposal, ...]
    native_dimension_review_issues: tuple[entities.Core3NativeDimensionReviewIssue, ...]


@dataclass(frozen=True)
class DimensionOntologyWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class _M085RepositoryMixin(Core3BaseRepository):
    def _base_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
        return self._base_query(model_cls, batch_id).where(model_cls.is_current.is_(True))

    def _paged_scalars(self, stmt: Any, *, limit: int = 100000, offset: int = 0) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=250000)
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

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> DimensionOntologyWriteResult:
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
        return DimensionOntologyWriteResult(
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
            raise TypeError("M08.5 repository payload must be a mapping or Pydantic model")
        if not raw_payload.get("project_id"):
            raw_payload["project_id"] = self.project_id
        if not raw_payload.get("category_code"):
            raw_payload["category_code"] = self.category_code.value
        model_fields = set(model_cls.__table__.columns.keys())
        result = {key: value for key, value in raw_payload.items() if key in model_fields}
        for audit_field in ("created_at", "updated_at", "activated_at"):
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
                stmt = stmt.where(getattr(model_cls, field_name).is_(None))
                continue
            value = _jsonable_value(value, nested=False)
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


class DimensionOntologyRepository(_M085RepositoryMixin):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M08 SKU 综合信号画像": self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
            "M08 证据矩阵": self._count_current_rows(entities.Core3SkuSignalEvidenceMatrix, batch_id),
            "M08.4 原生业务维度候选": self._count_current_rows(entities.Core3NativeDimensionCandidate, batch_id),
            "M08.4 原生维度对齐建议": self._count_current_rows(entities.Core3NativeDimensionAlignmentProposal, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M085InputBlockedError(f"M08.5 需要先完成上游产物：{', '.join(missing)}。")

    def load_input_bundle(self, batch_id: str) -> M085InputBundle:
        profiles = self._paged_scalars(
            self._current_query(entities.Core3SkuSignalProfile, batch_id).order_by(
                entities.Core3SkuSignalProfile.sku_code,
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
                entities.Core3CommentDownstreamSignal.signal_type,
                entities.Core3CommentDownstreamSignal.target_code_hint,
                entities.Core3CommentDownstreamSignal.sku_code,
            )
        )
        native_dimension_candidates = self._paged_scalars(
            self._current_query(entities.Core3NativeDimensionCandidate, batch_id).order_by(
                entities.Core3NativeDimensionCandidate.dimension_type,
                entities.Core3NativeDimensionCandidate.native_dimension_code,
            )
        )
        native_dimension_sku_supports = self._paged_scalars(
            self._current_query(entities.Core3NativeDimensionSkuSupport, batch_id).order_by(
                entities.Core3NativeDimensionSkuSupport.native_dimension_code,
                entities.Core3NativeDimensionSkuSupport.sku_code,
            )
        )
        native_dimension_alignments = self._paged_scalars(
            self._current_query(entities.Core3NativeDimensionAlignmentProposal, batch_id).order_by(
                entities.Core3NativeDimensionAlignmentProposal.seed_dimension_type,
                entities.Core3NativeDimensionAlignmentProposal.seed_dimension_code,
                entities.Core3NativeDimensionAlignmentProposal.native_dimension_code,
            )
        )
        native_dimension_review_issues = self._paged_scalars(
            self._current_query(entities.Core3NativeDimensionReviewIssue, batch_id).order_by(
                entities.Core3NativeDimensionReviewIssue.object_type,
                entities.Core3NativeDimensionReviewIssue.object_code,
                entities.Core3NativeDimensionReviewIssue.issue_code,
            )
        )
        return M085InputBundle(
            profiles=tuple(profiles),
            matrices=tuple(matrices),
            comment_atoms=tuple(comment_atoms),
            downstream_signals=tuple(downstream_signals),
            native_dimension_candidates=tuple(native_dimension_candidates),
            native_dimension_sku_supports=tuple(native_dimension_sku_supports),
            native_dimension_alignments=tuple(native_dimension_alignments),
            native_dimension_review_issues=tuple(native_dimension_review_issues),
        )

    def supersede_current_versions(self, batch_id: str, *, keep_ontology_version_id: str) -> None:
        rows = self._paged_scalars(
            self._current_query(entities.Core3DimensionOntologyVersion, batch_id).where(
                entities.Core3DimensionOntologyVersion.ontology_version_id != keep_ontology_version_id
            )
        )
        for row in rows:
            row.is_current = False
            if row.status in {"active", "active_with_warning"}:
                row.status = "superseded"
        self.db.flush()

    def save_version(self, record: Any) -> DimensionOntologyWriteResult:
        return self._save_many(
            entities.Core3DimensionOntologyVersion,
            (record,),
            unique_fields=("batch_id", "ontology_version"),
        )

    def save_definitions(self, records: Sequence[Any]) -> DimensionOntologyWriteResult:
        return self._save_many(
            entities.Core3DimensionDefinition,
            records,
            unique_fields=("ontology_version_id", "dimension_type", "dimension_code"),
        )

    def save_anchors(self, records: Sequence[Any]) -> DimensionOntologyWriteResult:
        return self._save_many(
            entities.Core3DimensionEvidenceAnchor,
            records,
            unique_fields=("dimension_definition_id", "anchor_type", "anchor_code", "anchor_role", "polarity"),
        )

    def save_mapping_rules(self, records: Sequence[Any]) -> DimensionOntologyWriteResult:
        return self._save_many(
            entities.Core3DimensionMappingRule,
            records,
            unique_fields=(
                "ontology_version_id",
                "source_type",
                "source_code",
                "target_dimension_type",
                "target_dimension_code",
                "mapping_level",
            ),
        )

    def save_snapshots(self, records: Sequence[Any]) -> DimensionOntologyWriteResult:
        return self._save_many(
            entities.Core3DimensionCandidateSnapshot,
            records,
            unique_fields=("ontology_version_id", "snapshot_type", "signal_type", "signal_code"),
        )

    def save_issues(self, records: Sequence[Any]) -> DimensionOntologyWriteResult:
        return self._save_many(
            entities.Core3DimensionCalibrationIssue,
            records,
            unique_fields=(
                "ontology_version_id",
                "issue_scope",
                "dimension_type",
                "dimension_code",
                "source_type",
                "source_code",
                "issue_code",
            ),
        )

    def get_current_version(self, batch_id: str) -> entities.Core3DimensionOntologyVersion | None:
        return (
            self.db.execute(
                self._current_query(entities.Core3DimensionOntologyVersion, batch_id)
                .where(entities.Core3DimensionOntologyVersion.status.in_(("active", "active_with_warning")))
                .order_by(entities.Core3DimensionOntologyVersion.updated_at.desc())
            )
            .scalars()
            .first()
        )

    def list_definitions(self, ontology_version_id: str, *, dimension_type: str | None = None, limit: int = 200, offset: int = 0) -> list[entities.Core3DimensionDefinition]:
        stmt = (
            select(entities.Core3DimensionDefinition)
            .where(entities.Core3DimensionDefinition.project_id == self.project_id)
            .where(entities.Core3DimensionDefinition.category_code == self.category_code.value)
            .where(entities.Core3DimensionDefinition.ontology_version_id == ontology_version_id)
            .where(entities.Core3DimensionDefinition.is_current.is_(True))
            .order_by(entities.Core3DimensionDefinition.dimension_type, entities.Core3DimensionDefinition.dimension_code)
        )
        if dimension_type:
            stmt = stmt.where(entities.Core3DimensionDefinition.dimension_type == dimension_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_snapshots(self, ontology_version_id: str, *, snapshot_type: str | None = None, limit: int = 200, offset: int = 0) -> list[entities.Core3DimensionCandidateSnapshot]:
        stmt = (
            select(entities.Core3DimensionCandidateSnapshot)
            .where(entities.Core3DimensionCandidateSnapshot.project_id == self.project_id)
            .where(entities.Core3DimensionCandidateSnapshot.category_code == self.category_code.value)
            .where(entities.Core3DimensionCandidateSnapshot.ontology_version_id == ontology_version_id)
            .where(entities.Core3DimensionCandidateSnapshot.is_current.is_(True))
            .order_by(entities.Core3DimensionCandidateSnapshot.snapshot_type, entities.Core3DimensionCandidateSnapshot.signal_type)
        )
        if snapshot_type:
            stmt = stmt.where(entities.Core3DimensionCandidateSnapshot.snapshot_type == snapshot_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_mapping_rules(
        self,
        ontology_version_id: str,
        *,
        target_dimension_type: str | None = None,
        mapping_level: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[entities.Core3DimensionMappingRule]:
        stmt = (
            select(entities.Core3DimensionMappingRule)
            .where(entities.Core3DimensionMappingRule.project_id == self.project_id)
            .where(entities.Core3DimensionMappingRule.category_code == self.category_code.value)
            .where(entities.Core3DimensionMappingRule.ontology_version_id == ontology_version_id)
            .where(entities.Core3DimensionMappingRule.is_current.is_(True))
            .order_by(
                entities.Core3DimensionMappingRule.target_dimension_type,
                entities.Core3DimensionMappingRule.target_dimension_code,
                entities.Core3DimensionMappingRule.mapping_level,
            )
        )
        if target_dimension_type:
            stmt = stmt.where(entities.Core3DimensionMappingRule.target_dimension_type == target_dimension_type)
        if mapping_level:
            stmt = stmt.where(entities.Core3DimensionMappingRule.mapping_level == mapping_level)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_issues(self, ontology_version_id: str, *, severity: str | None = None, limit: int = 200, offset: int = 0) -> list[entities.Core3DimensionCalibrationIssue]:
        stmt = (
            select(entities.Core3DimensionCalibrationIssue)
            .where(entities.Core3DimensionCalibrationIssue.project_id == self.project_id)
            .where(entities.Core3DimensionCalibrationIssue.category_code == self.category_code.value)
            .where(entities.Core3DimensionCalibrationIssue.ontology_version_id == ontology_version_id)
            .where(entities.Core3DimensionCalibrationIssue.is_current.is_(True))
            .order_by(entities.Core3DimensionCalibrationIssue.severity.desc(), entities.Core3DimensionCalibrationIssue.issue_code)
        )
        if severity:
            stmt = stmt.where(entities.Core3DimensionCalibrationIssue.severity == severity)
        return self._paged_scalars(stmt, limit=limit, offset=offset)


def _jsonable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable_value(value, nested=False) for key, value in payload.items()}


def _stable_identifier_field(model_cls: Any) -> str | None:
    mapping = {
        entities.Core3DimensionOntologyVersion: "ontology_version_id",
        entities.Core3DimensionDefinition: "dimension_definition_id",
        entities.Core3DimensionEvidenceAnchor: "dimension_anchor_id",
        entities.Core3DimensionMappingRule: "dimension_mapping_rule_id",
        entities.Core3DimensionCandidateSnapshot: "candidate_snapshot_id",
        entities.Core3DimensionCalibrationIssue: "calibration_issue_id",
    }
    return mapping.get(model_cls)


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


def _assign_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    _refresh_existing(existing, payload)
