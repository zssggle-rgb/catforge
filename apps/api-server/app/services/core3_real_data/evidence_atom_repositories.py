"""M02 evidence atom repositories."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from sqlalchemy import func, or_, select

from app.models.entities import Core3EvidenceAtom, Core3EvidenceLink
from app.services.core3_real_data.constants import (
    Core3ConfidenceLevel,
    Core3EvidenceLinkStatus,
    Core3EvidenceStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3BaseRepository


class EvidenceCurrentConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceAtomWriteResult:
    record: Core3EvidenceAtom
    created: bool
    superseded_record: Core3EvidenceAtom | None = None


@dataclass(frozen=True)
class EvidenceLinkWriteResult:
    record: Core3EvidenceLink
    created: bool


class EvidenceAtomRepository(Core3BaseRepository):
    def __init__(self, context) -> None:
        super().__init__(context)
        self._atom_by_id: dict[str, Core3EvidenceAtom] = {}
        self._current_by_key: dict[str, Core3EvidenceAtom | None] = {}
        self._skip_existing_lookup = False

    def skip_existing_lookup_when_empty(self) -> None:
        self._skip_existing_lookup = True

    def clear_save_cache(self) -> None:
        self._atom_by_id.clear()
        self._current_by_key.clear()

    def count_current_atoms(
        self,
        *,
        batch_id: str | None = None,
        target_sku_codes: Sequence[str] = (),
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
        )
        if batch_id is not None:
            stmt = stmt.where(Core3EvidenceAtom.batch_id == batch_id)
        if target_sku_codes:
            stmt = stmt.where(Core3EvidenceAtom.sku_code.in_(tuple(target_sku_codes)))
        return int(self.db.execute(stmt).scalar_one())

    def save_atom(
        self,
        payload: Mapping[str, Any],
        *,
        supersede_existing: bool = True,
    ) -> EvidenceAtomWriteResult:
        normalized_payload = self._model_payload(Core3EvidenceAtom, self._with_project_defaults(payload))
        evidence_id = _required_value(normalized_payload, "evidence_id")
        evidence_key = _required_value(normalized_payload, "evidence_key")
        normalized_payload.setdefault("evidence_status", Core3EvidenceStatus.CURRENT.value)
        normalized_payload.setdefault("is_current", True)

        existing = self._get_by_id_for_save(evidence_id)
        if existing is not None:
            return EvidenceAtomWriteResult(record=existing, created=False)

        superseded_record = None
        current = self._find_current_by_key_for_save(evidence_key)
        if current is not None and current.evidence_id != evidence_id:
            if not supersede_existing:
                raise EvidenceCurrentConflictError(f"current evidence already exists for key: {evidence_key}")
            superseded_record = self.mark_superseded(
                current.evidence_id,
                inactive_reason="superseded_by_clean_hash",
            )

        record = Core3EvidenceAtom(**_jsonable(normalized_payload))
        self.db.add(record)
        self._atom_by_id[evidence_id] = record
        if record.is_current and record.evidence_status == Core3EvidenceStatus.CURRENT.value:
            self._current_by_key[evidence_key] = record
        return EvidenceAtomWriteResult(record=record, created=True, superseded_record=superseded_record)

    def get_by_id(self, evidence_id: str) -> Core3EvidenceAtom | None:
        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.evidence_id == evidence_id)
        )
        return self.db.execute(stmt).scalars().first()

    def find_current_by_key(self, evidence_key: str) -> Core3EvidenceAtom | None:
        records = self.list_current_by_key(evidence_key, limit=2)
        if len(records) > 1:
            raise EvidenceCurrentConflictError(f"multiple current evidence rows for key: {evidence_key}")
        return records[0] if records else None

    def list_current_by_key(self, evidence_key: str, *, limit: int = 100) -> list[Core3EvidenceAtom]:
        normalized_limit, _ = self.pagination(limit=limit, offset=0)
        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.evidence_key == evidence_key)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .order_by(Core3EvidenceAtom.updated_at.desc(), Core3EvidenceAtom.evidence_id)
            .limit(normalized_limit)
        )
        return list(self.db.execute(stmt).scalars())

    def list_by_clean_record(
        self,
        batch_id: str,
        clean_table: str,
        clean_record_key: str,
        *,
        current_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset)
        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .where(Core3EvidenceAtom.clean_table == clean_table)
            .where(Core3EvidenceAtom.clean_record_key == clean_record_key)
            .order_by(Core3EvidenceAtom.created_at, Core3EvidenceAtom.evidence_id)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if current_only:
            stmt = stmt.where(Core3EvidenceAtom.is_current.is_(True)).where(
                Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value
            )
        return list(self.db.execute(stmt).scalars())

    def list_current_by_sku(
        self,
        batch_id: str,
        sku_code: str,
        *,
        evidence_types: Sequence[str] | None = None,
        min_confidence: Decimal | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset)
        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .where(Core3EvidenceAtom.sku_code == sku_code)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .order_by(Core3EvidenceAtom.evidence_type, Core3EvidenceAtom.evidence_field, Core3EvidenceAtom.evidence_id)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if evidence_types:
            stmt = stmt.where(Core3EvidenceAtom.evidence_type.in_(tuple(evidence_types)))
        if min_confidence is not None:
            stmt = stmt.where(Core3EvidenceAtom.base_confidence >= min_confidence)
        return list(self.db.execute(stmt).scalars())

    def mark_superseded(
        self,
        evidence_id: str,
        *,
        inactive_reason: str = "superseded_by_clean_hash",
    ) -> Core3EvidenceAtom:
        record = self._require_atom(evidence_id)
        record.evidence_status = Core3EvidenceStatus.SUPERSEDED.value
        record.is_current = False
        record.inactive_reason = inactive_reason
        record.updated_at = self.now_utc()
        self.db.flush()
        self._atom_by_id[record.evidence_id] = record
        self._current_by_key[record.evidence_key] = None
        return record

    def mark_inactive_by_clean_record(
        self,
        batch_id: str,
        clean_table: str,
        clean_record_key: str,
        *,
        inactive_reason: str = "clean_record_inactive",
    ) -> int:
        records = self.list_by_clean_record(
            batch_id,
            clean_table,
            clean_record_key,
            current_only=True,
            limit=1000,
        )
        for record in records:
            record.evidence_status = Core3EvidenceStatus.INACTIVE.value
            record.is_current = False
            record.inactive_reason = inactive_reason
            record.updated_at = self.now_utc()
            self._atom_by_id[record.evidence_id] = record
            self._current_by_key[record.evidence_key] = None
        self.db.flush()
        return len(records)

    def mark_low_value_comment_semantic_evidence_inactive(
        self,
        batch_id: str,
        *,
        source_row_ids: Sequence[str],
        inactive_reason: str = "low_value_skipped",
    ) -> list[str]:
        return self.mark_evidence_inactive_by_source_rows(
            batch_id,
            source_row_ids=source_row_ids,
            clean_tables=(
                "core3_clean_comment",
                "core3_clean_comment_sentence",
                "core3_clean_comment_dimension",
            ),
            evidence_types=(
                "comment_raw",
                "comment_sentence",
                "comment_dimension",
            ),
            inactive_reason=inactive_reason,
        )

    def mark_evidence_inactive_by_source_rows(
        self,
        batch_id: str,
        *,
        source_row_ids: Sequence[str],
        clean_tables: Sequence[str],
        inactive_reason: str,
        evidence_types: Sequence[str] | None = None,
        evidence_fields: Sequence[str] | None = None,
    ) -> list[str]:
        source_row_id_set = {str(source_row_id) for source_row_id in source_row_ids if source_row_id}
        if not source_row_id_set:
            return []
        inactive_evidence_ids: list[str] = []
        for source_row_chunk in _chunks(sorted(source_row_id_set), 1000):
            stmt = (
                select(Core3EvidenceAtom)
                .where(Core3EvidenceAtom.project_id == self.project_id)
                .where(Core3EvidenceAtom.category_code == self.category_code.value)
                .where(Core3EvidenceAtom.batch_id == batch_id)
                .where(Core3EvidenceAtom.source_row_id.in_(tuple(source_row_chunk)))
                .where(Core3EvidenceAtom.clean_table.in_(tuple(clean_tables)))
                .where(Core3EvidenceAtom.is_current.is_(True))
                .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            )
            if evidence_types is not None:
                stmt = stmt.where(Core3EvidenceAtom.evidence_type.in_(tuple(evidence_types)))
            if evidence_fields is not None:
                stmt = stmt.where(Core3EvidenceAtom.evidence_field.in_(tuple(evidence_fields)))
            for record in self.db.execute(stmt).scalars():
                record.evidence_status = Core3EvidenceStatus.INACTIVE.value
                record.is_current = False
                record.inactive_reason = inactive_reason
                record.updated_at = self.now_utc()
                inactive_evidence_ids.append(record.evidence_id)
                self._atom_by_id[record.evidence_id] = record
                self._current_by_key[record.evidence_key] = None
        if inactive_evidence_ids:
            self.db.flush()
        return inactive_evidence_ids

    def _get_by_id_for_save(self, evidence_id: str) -> Core3EvidenceAtom | None:
        cached = self._atom_by_id.get(evidence_id)
        if cached is not None:
            return cached
        if self._skip_existing_lookup:
            return None
        with self.db.no_autoflush:
            record = self.get_by_id(evidence_id)
        if record is not None:
            self._atom_by_id[evidence_id] = record
        return record

    def _find_current_by_key_for_save(self, evidence_key: str) -> Core3EvidenceAtom | None:
        if evidence_key in self._current_by_key:
            return self._current_by_key[evidence_key]
        if self._skip_existing_lookup:
            self._current_by_key[evidence_key] = None
            return None
        with self.db.no_autoflush:
            record = self.find_current_by_key(evidence_key)
        self._current_by_key[evidence_key] = record
        if record is not None:
            self._atom_by_id[record.evidence_id] = record
        return record

    def get_summary(self, batch_id: str, *, low_confidence_threshold: Decimal = Decimal("0.5500")) -> dict[str, Any]:
        base_filters = (
            Core3EvidenceAtom.project_id == self.project_id,
            Core3EvidenceAtom.category_code == self.category_code.value,
            Core3EvidenceAtom.batch_id == batch_id,
        )
        total = int(
            self.db.execute(
                select(func.count()).select_from(Core3EvidenceAtom).where(*base_filters)
            ).scalar_one()
        )
        by_type = _group_count(self.db, Core3EvidenceAtom.evidence_type, base_filters)
        by_status = _group_count(self.db, Core3EvidenceAtom.evidence_status, base_filters)
        by_confidence_level = _group_count(self.db, Core3EvidenceAtom.confidence_level, base_filters)
        low_confidence = int(
            self.db.execute(
                select(func.count())
                .select_from(Core3EvidenceAtom)
                .where(*base_filters)
                .where(Core3EvidenceAtom.base_confidence < low_confidence_threshold)
            ).scalar_one()
        )
        review_required = int(
            self.db.execute(
                select(func.count())
                .select_from(Core3EvidenceAtom)
                .where(*base_filters)
                .where(Core3EvidenceAtom.review_required.is_(True))
            ).scalar_one()
        )
        return {
            "batch_id": batch_id,
            "total": total,
            "current": by_status.get(Core3EvidenceStatus.CURRENT.value, 0),
            "inactive": by_status.get(Core3EvidenceStatus.INACTIVE.value, 0),
            "superseded": by_status.get(Core3EvidenceStatus.SUPERSEDED.value, 0),
            "skipped": by_status.get(Core3EvidenceStatus.SKIPPED.value, 0),
            "low_confidence": low_confidence,
            "review_required": review_required,
            "by_type": by_type,
            "by_status": by_status,
            "by_confidence_level": by_confidence_level,
        }

    def _list_by_batch(self, batch_id: str, *, limit: int = 1000) -> list[Core3EvidenceAtom]:
        normalized_limit, _ = self.pagination(limit=limit, offset=0, max_limit=100000)
        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .order_by(Core3EvidenceAtom.created_at, Core3EvidenceAtom.evidence_id)
            .limit(normalized_limit)
        )
        return list(self.db.execute(stmt).scalars())

    def _require_atom(self, evidence_id: str) -> Core3EvidenceAtom:
        record = self.get_by_id(evidence_id)
        if record is None:
            raise ValueError(f"evidence atom not found: {evidence_id}")
        return record

    def _with_project_defaults(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        normalized_payload.setdefault("project_id", self.project_id)
        normalized_payload.setdefault("category_code", self.category_code.value)
        return normalized_payload

    @staticmethod
    def _model_payload(model_cls: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in payload.items() if key in model_fields}


class CurrentEvidenceReader(Core3BaseRepository):
    def list_current(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        evidence_types: Sequence[str] | None = None,
        confidence_levels: Sequence[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset)
        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .order_by(Core3EvidenceAtom.sku_code, Core3EvidenceAtom.evidence_type, Core3EvidenceAtom.evidence_id)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if sku_code is not None:
            stmt = stmt.where(Core3EvidenceAtom.sku_code == sku_code)
        if evidence_types:
            stmt = stmt.where(Core3EvidenceAtom.evidence_type.in_(tuple(evidence_types)))
        if confidence_levels:
            stmt = stmt.where(Core3EvidenceAtom.confidence_level.in_(tuple(confidence_levels)))
        return list(self.db.execute(stmt).scalars())


class EvidenceLinkRepository(Core3BaseRepository):
    def __init__(self, context) -> None:
        super().__init__(context)
        self._link_by_key: dict[tuple[str, str, str], Core3EvidenceLink] = {}
        self._skip_existing_lookup_batches: set[str] = set()
        self._skip_existing_lookup_evidence_sets: dict[str, set[str]] = {}

    def skip_existing_lookup_for_batch(self, batch_id: str) -> None:
        self._skip_existing_lookup_batches.add(batch_id)

    def skip_existing_lookup_for_evidence_set(self, batch_id: str, evidence_ids: Sequence[str]) -> None:
        evidence_id_set = {str(evidence_id) for evidence_id in evidence_ids if evidence_id}
        if evidence_id_set:
            self._skip_existing_lookup_evidence_sets.setdefault(batch_id, set()).update(evidence_id_set)

    def clear_save_cache(self) -> None:
        self._link_by_key.clear()

    def count_batch_links(self, batch_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Core3EvidenceLink)
            .where(Core3EvidenceLink.project_id == self.project_id)
            .where(Core3EvidenceLink.category_code == self.category_code.value)
            .where(Core3EvidenceLink.batch_id == batch_id)
        )
        return int(self.db.execute(stmt).scalar_one())

    def save_link(self, payload: Mapping[str, Any]) -> EvidenceLinkWriteResult:
        normalized_payload = self._with_project_defaults(payload)
        normalized_payload.setdefault(
            "link_id",
            self._build_link_id(normalized_payload),
        )
        normalized_payload.setdefault("link_status", Core3EvidenceLinkStatus.CURRENT.value)
        normalized_payload = self._model_payload(Core3EvidenceLink, normalized_payload)

        link_key = (
            _required_value(normalized_payload, "from_evidence_id"),
            _required_value(normalized_payload, "to_evidence_id"),
            _required_value(normalized_payload, "link_type"),
        )
        cached = self._link_by_key.get(link_key)
        if cached is not None:
            self._refresh_existing_link(cached, normalized_payload)
            return EvidenceLinkWriteResult(record=cached, created=False)
        batch_id = str(normalized_payload.get("batch_id") or "")
        if not self._should_skip_existing_lookup(batch_id, link_key):
            with self.db.no_autoflush:
                existing = self._find_existing_link(*link_key)
            if existing is not None:
                self._refresh_existing_link(existing, normalized_payload)
                self._link_by_key[link_key] = existing
                return EvidenceLinkWriteResult(record=existing, created=False)

        record = Core3EvidenceLink(**_jsonable(normalized_payload))
        self.db.add(record)
        self._link_by_key[link_key] = record
        return EvidenceLinkWriteResult(record=record, created=True)

    def _should_skip_existing_lookup(self, batch_id: str, link_key: tuple[str, str, str]) -> bool:
        if batch_id in self._skip_existing_lookup_batches:
            return True
        evidence_id_set = self._skip_existing_lookup_evidence_sets.get(batch_id)
        if not evidence_id_set:
            return False
        return link_key[0] in evidence_id_set and link_key[1] in evidence_id_set

    def get_by_id(self, link_id: str) -> Core3EvidenceLink | None:
        stmt = (
            select(Core3EvidenceLink)
            .where(Core3EvidenceLink.project_id == self.project_id)
            .where(Core3EvidenceLink.category_code == self.category_code.value)
            .where(Core3EvidenceLink.link_id == link_id)
        )
        return self.db.execute(stmt).scalars().first()

    def list_links(
        self,
        evidence_id: str,
        *,
        direction: str = "both",
        link_type: str | None = None,
        current_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Core3EvidenceLink]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset)
        stmt = (
            select(Core3EvidenceLink)
            .where(Core3EvidenceLink.project_id == self.project_id)
            .where(Core3EvidenceLink.category_code == self.category_code.value)
            .order_by(Core3EvidenceLink.created_at, Core3EvidenceLink.link_id)
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if direction == "from":
            stmt = stmt.where(Core3EvidenceLink.from_evidence_id == evidence_id)
        elif direction == "to":
            stmt = stmt.where(Core3EvidenceLink.to_evidence_id == evidence_id)
        elif direction == "both":
            stmt = stmt.where(
                or_(
                    Core3EvidenceLink.from_evidence_id == evidence_id,
                    Core3EvidenceLink.to_evidence_id == evidence_id,
                )
            )
        else:
            raise ValueError(f"unknown link direction: {direction}")
        if link_type is not None:
            stmt = stmt.where(Core3EvidenceLink.link_type == link_type)
        if current_only:
            stmt = stmt.where(Core3EvidenceLink.link_status == Core3EvidenceLinkStatus.CURRENT.value)
        return list(self.db.execute(stmt).scalars())

    def mark_links_inactive_for_evidence(self, evidence_id: str) -> int:
        links = self.list_links(evidence_id, current_only=True, limit=1000)
        for link in links:
            link.link_status = Core3EvidenceLinkStatus.INACTIVE.value
            link.updated_at = self.now_utc()
        self.db.flush()
        return len(links)

    def mark_obsolete_current_links_for_evidence_set(
        self,
        batch_id: str,
        *,
        evidence_ids: Sequence[str],
        desired_link_keys: set[tuple[str, str, str]],
        link_types: Sequence[str],
    ) -> int:
        evidence_id_set = {str(evidence_id) for evidence_id in evidence_ids if evidence_id}
        if not evidence_id_set or not link_types:
            return 0

        obsolete_count = 0
        for evidence_id_chunk in _chunks(sorted(evidence_id_set), 1000):
            stmt = (
                select(Core3EvidenceLink)
                .where(Core3EvidenceLink.project_id == self.project_id)
                .where(Core3EvidenceLink.category_code == self.category_code.value)
                .where(Core3EvidenceLink.batch_id == batch_id)
                .where(Core3EvidenceLink.link_status == Core3EvidenceLinkStatus.CURRENT.value)
                .where(Core3EvidenceLink.link_type.in_(tuple(link_types)))
                .where(Core3EvidenceLink.from_evidence_id.in_(tuple(evidence_id_chunk)))
            )
            for link in self.db.execute(stmt).scalars():
                if link.to_evidence_id not in evidence_id_set:
                    continue
                link_key = (link.from_evidence_id, link.to_evidence_id, link.link_type)
                if link_key in desired_link_keys:
                    continue
                link.link_status = Core3EvidenceLinkStatus.INACTIVE.value
                link.updated_at = self.now_utc()
                obsolete_count += 1

        if obsolete_count:
            self.db.flush()
        return obsolete_count

    def preload_links_for_evidence_set(
        self,
        batch_id: str,
        *,
        evidence_ids: Sequence[str],
        link_types: Sequence[str],
    ) -> int:
        evidence_id_set = {str(evidence_id) for evidence_id in evidence_ids if evidence_id}
        if not evidence_id_set or not link_types:
            return 0

        preloaded_count = 0
        for evidence_id_chunk in _chunks(sorted(evidence_id_set), 1000):
            stmt = (
                select(Core3EvidenceLink)
                .where(Core3EvidenceLink.project_id == self.project_id)
                .where(Core3EvidenceLink.category_code == self.category_code.value)
                .where(Core3EvidenceLink.batch_id == batch_id)
                .where(Core3EvidenceLink.link_type.in_(tuple(link_types)))
                .where(Core3EvidenceLink.from_evidence_id.in_(tuple(evidence_id_chunk)))
            )
            for link in self.db.execute(stmt).scalars():
                if link.to_evidence_id not in evidence_id_set:
                    continue
                self._link_by_key[(link.from_evidence_id, link.to_evidence_id, link.link_type)] = link
                preloaded_count += 1
        return preloaded_count

    def count_by_type(self, batch_id: str) -> dict[str, int]:
        stmt = (
            select(Core3EvidenceLink.link_type, func.count())
            .where(Core3EvidenceLink.project_id == self.project_id)
            .where(Core3EvidenceLink.category_code == self.category_code.value)
            .where(Core3EvidenceLink.batch_id == batch_id)
            .where(Core3EvidenceLink.link_status == Core3EvidenceLinkStatus.CURRENT.value)
            .group_by(Core3EvidenceLink.link_type)
        )
        return {str(link_type): int(count) for link_type, count in self.db.execute(stmt).all()}

    def _find_existing_link(self, from_evidence_id: str, to_evidence_id: str, link_type: str) -> Core3EvidenceLink | None:
        stmt = (
            select(Core3EvidenceLink)
            .where(Core3EvidenceLink.project_id == self.project_id)
            .where(Core3EvidenceLink.category_code == self.category_code.value)
            .where(Core3EvidenceLink.from_evidence_id == from_evidence_id)
            .where(Core3EvidenceLink.to_evidence_id == to_evidence_id)
            .where(Core3EvidenceLink.link_type == link_type)
        )
        return self.db.execute(stmt).scalars().first()

    def _refresh_existing_link(self, link: Core3EvidenceLink, payload: Mapping[str, Any]) -> None:
        link.from_evidence_key = str(payload["from_evidence_key"])
        link.to_evidence_key = str(payload["to_evidence_key"])
        link.link_payload_json = payload.get("link_payload_json") or {}
        link.confidence = payload.get("confidence") or link.confidence
        link.link_status = str(payload.get("link_status") or Core3EvidenceLinkStatus.CURRENT.value)
        link.updated_at = self.now_utc()

    def _build_link_id(self, payload: Mapping[str, Any]) -> str:
        return stable_hash(
            {
                "project_id": payload.get("project_id", self.project_id),
                "category_code": payload.get("category_code", self.category_code.value),
                "batch_id": payload.get("batch_id"),
                "from_evidence_id": payload.get("from_evidence_id"),
                "to_evidence_id": payload.get("to_evidence_id"),
                "link_type": payload.get("link_type"),
            },
            version="m02_link_v1",
        )

    def _with_project_defaults(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        normalized_payload.setdefault("project_id", self.project_id)
        normalized_payload.setdefault("category_code", self.category_code.value)
        return normalized_payload

    @staticmethod
    def _model_payload(model_cls: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in payload.items() if key in model_fields}


def _chunks(values: Sequence[str], size: int) -> list[Sequence[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _required_value(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field_name} is required")
    return str(value)


def _count_by(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _group_count(db: Any, column: Any, filters: Sequence[Any]) -> dict[str, int]:
    stmt = (
        select(column, func.count())
        .select_from(Core3EvidenceAtom)
        .where(*filters)
        .group_by(column)
    )
    return {str(value): int(count) for value, count in db.execute(stmt).all() if value is not None}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
