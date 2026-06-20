"""Repositories for M03A parameter taxonomy assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.constants import Core3EvidenceStatus, Core3EvidenceType
from app.services.core3_real_data.param_taxonomy_schemas import TaxonomyReviewStatus, TaxonomyStatus


M03A_ALLOWED_EVIDENCE_TYPES = (Core3EvidenceType.PARAM_RAW.value,)


class ParamTaxonomyImmutableError(RuntimeError):
    pass


class ParamTaxonomyNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class ParamTaxonomyPayload:
    version: dict[str, Any]
    fields: list[dict[str, Any]]
    clusters: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    definitions: list[dict[str, Any]]
    mapping_rules: list[dict[str, Any]]
    review_items: list[dict[str, Any]]


class _ParamTaxonomyBaseRepository:
    def __init__(self, db: Session, project_id: str) -> None:
        if not project_id.strip():
            raise ValueError("project_id is required")
        self.db = db
        self.project_id = project_id

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def pagination(limit: int = 100, offset: int = 0, *, max_limit: int = 1000) -> tuple[int, int]:
        normalized_limit = min(max(limit, 1), max_limit)
        normalized_offset = max(offset, 0)
        return normalized_limit, normalized_offset


class ParamTaxonomyEvidenceReader(_ParamTaxonomyBaseRepository):
    """Read M02 param evidence without constraining category_code to the TV enum."""

    def list_param_raw_evidence(
        self,
        *,
        batch_ids: Sequence[str],
        category_code: str,
        limit: int = 200000,
        offset: int = 0,
    ) -> list[entities.Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=200000)
        stmt = (
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == category_code)
            .where(entities.Core3EvidenceAtom.batch_id.in_(tuple(batch_ids)))
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type.in_(M03A_ALLOWED_EVIDENCE_TYPES))
            .order_by(
                entities.Core3EvidenceAtom.batch_id,
                entities.Core3EvidenceAtom.sku_code,
                entities.Core3EvidenceAtom.evidence_field,
                entities.Core3EvidenceAtom.evidence_id,
            )
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        return list(self.db.execute(stmt).scalars())


class ParamTaxonomyRepository(_ParamTaxonomyBaseRepository):
    def get_version(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
    ) -> entities.Core3ParamTaxonomyVersion | None:
        stmt = (
            select(entities.Core3ParamTaxonomyVersion)
            .where(entities.Core3ParamTaxonomyVersion.project_id == self.project_id)
            .where(entities.Core3ParamTaxonomyVersion.taxonomy_version == taxonomy_version)
        )
        if category_code is not None:
            stmt = stmt.where(entities.Core3ParamTaxonomyVersion.category_code == category_code)
        return self.db.execute(stmt).scalars().first()

    def get_current_published(self, category_code: str) -> entities.Core3ParamTaxonomyVersion | None:
        stmt = (
            select(entities.Core3ParamTaxonomyVersion)
            .where(entities.Core3ParamTaxonomyVersion.project_id == self.project_id)
            .where(entities.Core3ParamTaxonomyVersion.category_code == category_code)
            .where(entities.Core3ParamTaxonomyVersion.status == TaxonomyStatus.PUBLISHED.value)
            .order_by(
                entities.Core3ParamTaxonomyVersion.published_at.desc(),
                entities.Core3ParamTaxonomyVersion.updated_at.desc(),
            )
        )
        return self.db.execute(stmt).scalars().first()

    def save_taxonomy_payload(
        self,
        payload: ParamTaxonomyPayload,
        *,
        force_rebuild: bool = False,
    ) -> entities.Core3ParamTaxonomyVersion:
        taxonomy_version = str(payload.version["taxonomy_version"])
        category_code = str(payload.version["category_code"])
        existing = self.get_version(taxonomy_version, category_code=category_code)
        if existing is not None:
            if existing.status == TaxonomyStatus.PUBLISHED.value:
                raise ParamTaxonomyImmutableError(f"published taxonomy cannot be overwritten: {taxonomy_version}")
            if not force_rebuild:
                raise ParamTaxonomyImmutableError(
                    f"taxonomy draft already exists; use force_rebuild to replace: {taxonomy_version}"
                )
            self.delete_taxonomy_payload(taxonomy_version, category_code=category_code)

        version = entities.Core3ParamTaxonomyVersion(**payload.version)
        self.db.add(version)
        self.db.add_all(entities.Core3ParamRawFieldInventory(**item) for item in payload.fields)
        self.db.add_all(entities.Core3ParamFieldCluster(**item) for item in payload.clusters)
        self.db.add_all(entities.Core3ParamConceptCandidate(**item) for item in payload.candidates)
        self.db.add_all(entities.Core3ParamDefinition(**item) for item in payload.definitions)
        self.db.add_all(entities.Core3ParamFieldMappingRule(**item) for item in payload.mapping_rules)
        self.db.add_all(entities.Core3ParamTaxonomyReviewItem(**item) for item in payload.review_items)
        self.db.flush()
        return version

    def delete_taxonomy_payload(self, taxonomy_version: str, *, category_code: str | None = None) -> None:
        for model in [
            entities.Core3ParamTaxonomyReviewItem,
            entities.Core3ParamFieldMappingRule,
            entities.Core3ParamDefinition,
            entities.Core3ParamConceptCandidate,
            entities.Core3ParamFieldCluster,
            entities.Core3ParamRawFieldInventory,
            entities.Core3ParamTaxonomyVersion,
        ]:
            stmt = (
                delete(model)
                .where(model.project_id == self.project_id)
                .where(model.taxonomy_version == taxonomy_version)
            )
            if category_code is not None:
                stmt = stmt.where(model.category_code == category_code)
            self.db.execute(stmt)
        self.db.flush()

    def load_taxonomy(self, taxonomy_version: str, *, category_code: str | None = None) -> dict[str, Any]:
        version = self.get_version(taxonomy_version, category_code=category_code)
        if version is None:
            raise ParamTaxonomyNotFoundError(f"taxonomy version not found: {taxonomy_version}")
        return {
            "version": version,
            "fields": self.list_fields(taxonomy_version, category_code=version.category_code, limit=10000),
            "clusters": self.list_clusters(taxonomy_version, category_code=version.category_code, limit=10000),
            "candidates": self.list_candidates(taxonomy_version, category_code=version.category_code, limit=10000),
            "definitions": self.list_definitions(taxonomy_version, category_code=version.category_code, limit=10000),
            "mapping_rules": self.list_mapping_rules(taxonomy_version, category_code=version.category_code, limit=10000),
            "review_items": self.list_review_items(taxonomy_version, category_code=version.category_code, limit=10000),
        }

    def list_fields(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        stmt = self._base_version_query(entities.Core3ParamRawFieldInventory, taxonomy_version, category_code=category_code).order_by(
            entities.Core3ParamRawFieldInventory.raw_param_name,
            entities.Core3ParamRawFieldInventory.raw_field_id,
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset, max_limit=10000)

    def list_clusters(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        stmt = self._base_version_query(entities.Core3ParamFieldCluster, taxonomy_version, category_code=category_code).order_by(
            entities.Core3ParamFieldCluster.cluster_code,
            entities.Core3ParamFieldCluster.field_cluster_id,
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset, max_limit=10000)

    def list_candidates(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        stmt = self._base_version_query(entities.Core3ParamConceptCandidate, taxonomy_version, category_code=category_code).order_by(
            entities.Core3ParamConceptCandidate.candidate_code,
            entities.Core3ParamConceptCandidate.concept_candidate_id,
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset, max_limit=10000)

    def list_definitions(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        stmt = self._base_version_query(entities.Core3ParamDefinition, taxonomy_version, category_code=category_code).order_by(
            entities.Core3ParamDefinition.param_code,
            entities.Core3ParamDefinition.param_definition_id,
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset, max_limit=10000)

    def list_mapping_rules(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        stmt = self._base_version_query(entities.Core3ParamFieldMappingRule, taxonomy_version, category_code=category_code).order_by(
            entities.Core3ParamFieldMappingRule.raw_param_name,
            entities.Core3ParamFieldMappingRule.mapping_rule_id,
        )
        return self._paged_scalars(stmt, limit=limit, offset=offset, max_limit=10000)

    def list_review_items(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        review_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        stmt = self._base_version_query(entities.Core3ParamTaxonomyReviewItem, taxonomy_version, category_code=category_code).order_by(
            entities.Core3ParamTaxonomyReviewItem.severity.desc(),
            entities.Core3ParamTaxonomyReviewItem.item_type,
            entities.Core3ParamTaxonomyReviewItem.review_item_id,
        )
        if review_status is not None:
            stmt = stmt.where(entities.Core3ParamTaxonomyReviewItem.review_status == review_status)
        return self._paged_scalars(stmt, limit=limit, offset=offset, max_limit=10000)

    def count_review_items(
        self,
        taxonomy_version: str,
        *,
        category_code: str | None = None,
        review_status: str | None = None,
    ) -> int:
        stmt = self._base_version_query(entities.Core3ParamTaxonomyReviewItem, taxonomy_version, category_code=category_code)
        if review_status is not None:
            stmt = stmt.where(entities.Core3ParamTaxonomyReviewItem.review_status == review_status)
        return len(list(self.db.execute(stmt).scalars()))

    def apply_review_decision(
        self,
        *,
        taxonomy_version: str,
        review_item_id: str,
        review_status: str,
        decision_payload: dict[str, Any],
    ) -> entities.Core3ParamTaxonomyReviewItem:
        item = self.db.get(entities.Core3ParamTaxonomyReviewItem, review_item_id)
        if item is None or item.project_id != self.project_id or item.taxonomy_version != taxonomy_version:
            raise ParamTaxonomyNotFoundError(f"review item not found: {review_item_id}")
        item.review_status = review_status
        item.review_decision_json = decision_payload
        self._refresh_version_counts(taxonomy_version)
        self.db.flush()
        return item

    def publish(self, *, category_code: str, taxonomy_version: str) -> entities.Core3ParamTaxonomyVersion:
        version = self.get_version(taxonomy_version, category_code=category_code)
        if version is None:
            raise ParamTaxonomyNotFoundError(f"taxonomy version not found: {taxonomy_version}")
        self._refresh_version_counts(taxonomy_version, category_code=category_code)
        if version.status == TaxonomyStatus.PUBLISHED.value:
            return version
        if version.blocking_review_count > 0:
            raise ValueError("taxonomy has blocking review items and cannot be published")

        current = self.get_current_published(category_code)
        if current is not None and current.taxonomy_version != taxonomy_version:
            current.status = TaxonomyStatus.SUPERSEDED.value
        version.status = TaxonomyStatus.PUBLISHED.value
        version.published_at = self.now_utc()
        self.db.flush()
        return version

    def _refresh_version_counts(self, taxonomy_version: str, *, category_code: str | None = None) -> None:
        version = self.get_version(taxonomy_version, category_code=category_code)
        if version is None:
            return
        review_count_stmt = (
            select(func.count())
            .select_from(entities.Core3ParamTaxonomyReviewItem)
            .where(entities.Core3ParamTaxonomyReviewItem.project_id == self.project_id)
            .where(entities.Core3ParamTaxonomyReviewItem.taxonomy_version == taxonomy_version)
            .where(entities.Core3ParamTaxonomyReviewItem.review_status == TaxonomyReviewStatus.REVIEW_REQUIRED.value)
        )
        blocking_count_stmt = (
            select(func.count())
            .select_from(entities.Core3ParamTaxonomyReviewItem)
            .where(entities.Core3ParamTaxonomyReviewItem.project_id == self.project_id)
            .where(entities.Core3ParamTaxonomyReviewItem.taxonomy_version == taxonomy_version)
            .where(entities.Core3ParamTaxonomyReviewItem.review_status == TaxonomyReviewStatus.REVIEW_REQUIRED.value)
            .where(entities.Core3ParamTaxonomyReviewItem.severity == "blocking")
        )
        if category_code is not None:
            review_count_stmt = review_count_stmt.where(entities.Core3ParamTaxonomyReviewItem.category_code == category_code)
            blocking_count_stmt = blocking_count_stmt.where(entities.Core3ParamTaxonomyReviewItem.category_code == category_code)
        version.review_required_count = int(self.db.execute(review_count_stmt).scalar_one())
        version.blocking_review_count = int(self.db.execute(blocking_count_stmt).scalar_one())

    def _base_version_query(self, model: Any, taxonomy_version: str, *, category_code: str | None = None):
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.taxonomy_version == taxonomy_version)
        )
        if category_code is not None:
            stmt = stmt.where(model.category_code == category_code)
        return stmt

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int, max_limit: int = 1000) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=max_limit)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())
