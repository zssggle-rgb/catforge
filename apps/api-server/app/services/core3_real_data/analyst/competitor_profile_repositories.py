"""Transactional repository for versioned competitor profiles."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfilePersistenceBundle,
    CompetitorProfileReadBundle,
    CompetitorProfileVersionDraftCreate,
    CompetitorProfileVersionRecord,
    SkuCompetitorPairDraft,
    SkuCompetitorProfileDraft,
    SkuCompetitorRelationDraft,
    SkuCompetitorSelectionDraft,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorPairDraft,
    KeyCompetitorSelectionDraft,
    RelationAssessment,
    ServingScope,
    SkuCompetitorDecisionProfileDraft,
)
from app.services.core3_real_data.repositories import (
    Core3BaseRepository,
    Core3RepositoryContext,
)


class CompetitorProfileRepositoryError(RuntimeError):
    pass


class CompetitorProfileVersionNotFoundError(CompetitorProfileRepositoryError):
    pass


class CompetitorProfileNotFoundError(CompetitorProfileRepositoryError):
    pass


class CompetitorProfileImmutableError(CompetitorProfileRepositoryError):
    pass


class CompetitorProfileDraftWriteNotAllowedError(CompetitorProfileRepositoryError):
    pass


_PERSISTENCE_FLUSH_BATCH_SIZE = 32


class CompetitorProfileRepository(Core3BaseRepository):
    def __init__(self, context: Core3RepositoryContext) -> None:
        super().__init__(context)

    def create_version(
        self,
        payload: CompetitorProfileVersionDraftCreate,
    ) -> CompetitorProfileVersionRecord:
        self._assert_context_scope(payload.project_id, payload.category_code)
        existing = self._find_version(
            release_scope_key=payload.release_scope_key,
            profile_version=payload.profile_version,
            rule_version=payload.rule_version,
        )
        if existing is not None:
            self._assert_same_version_inputs(existing, payload)
            return _version_record(existing)
        try:
            with self.db.begin_nested():
                row = entities.Core3CompetitorProfileVersion(
                    **_version_entity_payload(payload)
                )
                self.db.add(row)
                self.db.flush()
            return _version_record(row)
        except IntegrityError:
            concurrent = self._find_version(
                release_scope_key=payload.release_scope_key,
                profile_version=payload.profile_version,
                rule_version=payload.rule_version,
            )
            if concurrent is None:
                raise
            self._assert_same_version_inputs(concurrent, payload)
            return _version_record(concurrent)

    def write_draft(
        self,
        bundle: CompetitorProfilePersistenceBundle,
        *,
        use_savepoint: bool = True,
    ) -> CompetitorProfileReadBundle:
        version, row, _ = self._write_draft_rows(
            bundle,
            use_savepoint=use_savepoint,
        )
        return self._read_bundle(version, row, preview=True)

    def write_draft_without_readback(
        self,
        bundle: CompetitorProfilePersistenceBundle,
        *,
        use_savepoint: bool = True,
    ) -> bool:
        """Persist one immutable draft without materializing a second full graph.

        Generation callers that already hold the complete materialized graph can
        release it after commit and perform one deliberate readback afterwards.
        The return value is true only when this call inserted the draft.
        """

        _, _, created = self._write_draft_rows(
            bundle,
            use_savepoint=use_savepoint,
        )
        return created

    def _write_draft_rows(
        self,
        bundle: CompetitorProfilePersistenceBundle,
        *,
        use_savepoint: bool,
    ) -> tuple[
        entities.Core3CompetitorProfileVersion,
        entities.Core3SkuCompetitorProfile,
        bool,
    ]:
        profile = bundle.profile
        self._assert_context_scope(profile.project_id, profile.category_code)
        version = self._version_by_id(
            profile.competitor_profile_version_id,
            for_update=True,
        )
        self._assert_draft_version(version)
        self._assert_version_matches_scope(version, profile)
        existing = self._find_profile(
            version_id=profile.competitor_profile_version_id,
            target_sku_code=profile.target_sku_code,
        )
        if existing is not None:
            self._assert_same_profile_inputs(existing, bundle)
            return version, existing, False
        if not use_savepoint:
            row = self._insert_bundle(bundle)
            return version, row, True
        try:
            with self.db.begin_nested():
                row = self._insert_bundle(bundle)
        except IntegrityError:
            concurrent = self._find_profile(
                version_id=profile.competitor_profile_version_id,
                target_sku_code=profile.target_sku_code,
            )
            if concurrent is None:
                raise
            self._assert_same_profile_inputs(concurrent, bundle)
            return version, concurrent, False
        return version, row, True

    def get_version(
        self,
        *,
        release_scope_key: str,
        profile_version: str,
        rule_version: str,
    ) -> CompetitorProfileVersionRecord | None:
        row = self._find_version(
            release_scope_key=release_scope_key,
            profile_version=profile_version,
            rule_version=rule_version,
        )
        return _version_record(row) if row else None

    def get_version_by_id(
        self,
        competitor_profile_version_id: str,
    ) -> CompetitorProfileVersionRecord:
        """Return one version inside the repository project/category boundary."""

        return _version_record(
            self._version_by_id(competitor_profile_version_id)
        )

    def list_versions(
        self,
        *,
        release_scope_key: str | None = None,
        release_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CompetitorProfileVersionRecord]:
        normalized_limit, normalized_offset = self.pagination(limit, offset)
        model = entities.Core3CompetitorProfileVersion
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
        )
        if release_scope_key is not None:
            stmt = stmt.where(model.release_scope_key == release_scope_key)
        if release_status is not None:
            stmt = stmt.where(model.release_status == release_status)
        rows = self.db.execute(
            stmt.order_by(model.generated_at.desc(), model.profile_version)
            .offset(normalized_offset)
            .limit(normalized_limit)
        ).scalars()
        return [_version_record(row) for row in rows]

    def get_profile(
        self,
        *,
        competitor_profile_version_id: str,
        target_sku_code: str,
        preview: bool = True,
    ) -> CompetitorProfileReadBundle | None:
        version = self._version_by_id(competitor_profile_version_id)
        profile = self._find_profile(
            version_id=competitor_profile_version_id,
            target_sku_code=target_sku_code,
        )
        return self._read_bundle(version, profile, preview=preview) if profile else None

    def get_current_published_profile(
        self,
        *,
        release_scope_key: str,
        target_sku_code: str,
    ) -> CompetitorProfileReadBundle | None:
        """Read one formal profile without falling back to drafts or legacy outputs."""

        version_model = entities.Core3CompetitorProfileVersion
        version = self.db.execute(
            select(version_model)
            .where(version_model.project_id == self.project_id)
            .where(version_model.category_code == self.category_code.value)
            .where(version_model.release_scope_key == release_scope_key)
            .where(version_model.release_status == "published")
            .where(version_model.is_current.is_(True))
        ).scalars().first()
        if version is None:
            return None
        profile = self._find_profile(
            version_id=version.competitor_profile_version_id,
            target_sku_code=target_sku_code,
        )
        if profile is None:
            return None
        if profile.release_status != "published" or not profile.is_current:
            raise CompetitorProfileRepositoryError(
                "current version and SKU profile release state are inconsistent"
            )
        return self._read_bundle(version, profile, preview=False)

    def update_draft_generation_state(
        self,
        competitor_profile_version_id: str,
        *,
        ready_count: int,
        partial_count: int,
        blocked_count: int,
        failed_count: int,
        pair_count: int,
        relation_count: int,
        selection_count: int,
        processing_status: str,
        safe_error_summary: Mapping[str, Any] | None = None,
    ) -> CompetitorProfileVersionRecord:
        """Checkpoint draft-only generation counters without changing analysis rows."""

        counts = {
            "ready_count": ready_count,
            "partial_count": partial_count,
            "blocked_count": blocked_count,
            "failed_count": failed_count,
            "pair_count": pair_count,
            "relation_count": relation_count,
            "selection_count": selection_count,
        }
        if any(value < 0 for value in counts.values()):
            raise ValueError("generation counters cannot be negative")
        version = self._version_by_id(
            competitor_profile_version_id,
            for_update=True,
        )
        self._assert_draft_version(version)
        if ready_count + partial_count + blocked_count + failed_count > version.sku_count:
            raise ValueError("generation status counters cannot exceed SKU manifest")
        if relation_count > pair_count * 7:
            raise ValueError("generation relation count cannot exceed seven per pair")
        if selection_count > version.sku_count * 3:
            raise ValueError("generation selection count cannot exceed three per SKU")
        for field_name, value in counts.items():
            setattr(version, field_name, value)
        version.processing_status = str(processing_status).strip()
        if not version.processing_status:
            raise ValueError("processing status is required")
        version.safe_error_summary_json = dict(safe_error_summary or {})
        self.db.flush()
        return _version_record(version)

    def list_profile_progress(
        self,
        *,
        competitor_profile_version_id: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._version_by_id(competitor_profile_version_id)
        normalized_limit, normalized_offset = self.pagination(
            limit,
            offset,
            max_limit=1000,
        )
        model = entities.Core3SkuCompetitorProfile
        rows = self.db.execute(
            select(
                model.sku_competitor_profile_id,
                model.target_sku_code,
                model.analysis_state,
                model.conclusion_state,
                model.review_required,
                model.result_hash,
            )
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.competitor_profile_version_id == competitor_profile_version_id)
            .order_by(model.target_sku_code)
            .offset(normalized_offset)
            .limit(normalized_limit)
        ).mappings()
        return [dict(row) for row in rows]

    def list_pairs(
        self,
        *,
        sku_competitor_profile_id: str,
        candidate_status: str | None = None,
        selected_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuCompetitorPairDraft]:
        normalized_limit, normalized_offset = self.pagination(
            limit,
            offset,
            max_limit=500,
        )
        self._profile_by_id(sku_competitor_profile_id)
        model = entities.Core3SkuCompetitorProfilePair
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.sku_competitor_profile_id == sku_competitor_profile_id)
        )
        if candidate_status is not None:
            stmt = stmt.where(model.candidate_status == candidate_status)
        if selected_only:
            stmt = stmt.where(model.selected.is_(True))
        rows = self.db.execute(
            stmt.order_by(model.selected.desc(), model.candidate_sku_code)
            .offset(normalized_offset)
            .limit(normalized_limit)
        ).scalars()
        return [_pair_draft(row) for row in rows]

    def list_relations(
        self,
        *,
        sku_competitor_profile_pair_id: str,
        relation_status: str | None = None,
    ) -> list[SkuCompetitorRelationDraft]:
        pair = self._pair_by_id(sku_competitor_profile_pair_id)
        model = entities.Core3SkuCompetitorProfileRelation
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.sku_competitor_profile_pair_id == pair.sku_competitor_profile_pair_id)
        )
        if relation_status is not None:
            stmt = stmt.where(model.relation_status == relation_status)
        rows = self.db.execute(stmt.order_by(model.relation_code)).scalars()
        return [_relation_draft(row) for row in rows]

    def list_selections(
        self,
        *,
        sku_competitor_profile_id: str,
    ) -> list[SkuCompetitorSelectionDraft]:
        self._profile_by_id(sku_competitor_profile_id)
        model = entities.Core3SkuCompetitorProfileSelection
        rows = self.db.execute(
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.sku_competitor_profile_id == sku_competitor_profile_id)
            .order_by(model.selection_rank)
        ).scalars()
        return [_selection_draft(row) for row in rows]

    def _insert_bundle(
        self,
        bundle: CompetitorProfilePersistenceBundle,
    ) -> entities.Core3SkuCompetitorProfile:
        profile_row = entities.Core3SkuCompetitorProfile(
            **_profile_entity_payload(bundle.profile)
        )
        self.db.add(profile_row)
        self.db.flush()
        pair_ids: dict[str, str] = {}
        for start in range(0, len(bundle.pairs), _PERSISTENCE_FLUSH_BATCH_SIZE):
            rows = [
                entities.Core3SkuCompetitorProfilePair(
                    **_pair_entity_payload(
                        pair,
                        profile_id=profile_row.sku_competitor_profile_id,
                    )
                )
                for pair in bundle.pairs[
                    start : start + _PERSISTENCE_FLUSH_BATCH_SIZE
                ]
            ]
            self.db.add_all(rows)
            self.db.flush()
            pair_ids.update(
                {
                    row.candidate_sku_code: row.sku_competitor_profile_pair_id
                    for row in rows
                }
            )
            for row in rows:
                self.db.expunge(row)
            del rows
        for start in range(0, len(bundle.relations), _PERSISTENCE_FLUSH_BATCH_SIZE):
            rows = [
                entities.Core3SkuCompetitorProfileRelation(
                    **_relation_entity_payload(
                        relation,
                        pair_id=pair_ids[relation.candidate_sku_code],
                    )
                )
                for relation in bundle.relations[
                    start : start + _PERSISTENCE_FLUSH_BATCH_SIZE
                ]
            ]
            self.db.add_all(rows)
            self.db.flush()
            for row in rows:
                self.db.expunge(row)
            del rows
        for start in range(0, len(bundle.selections), _PERSISTENCE_FLUSH_BATCH_SIZE):
            rows = [
                entities.Core3SkuCompetitorProfileSelection(
                    **_selection_entity_payload(
                        selection,
                        profile_id=profile_row.sku_competitor_profile_id,
                        pair_id=pair_ids[selection.candidate_sku_code],
                    )
                )
                for selection in bundle.selections[
                    start : start + _PERSISTENCE_FLUSH_BATCH_SIZE
                ]
            ]
            self.db.add_all(rows)
            self.db.flush()
            for row in rows:
                self.db.expunge(row)
            del rows
        return profile_row

    def _read_bundle(
        self,
        version: entities.Core3CompetitorProfileVersion,
        profile: entities.Core3SkuCompetitorProfile,
        *,
        preview: bool,
    ) -> CompetitorProfileReadBundle:
        profile_id = profile.sku_competitor_profile_id
        pair_rows = list(
            self.db.execute(
                select(entities.Core3SkuCompetitorProfilePair)
                .where(
                    entities.Core3SkuCompetitorProfilePair.sku_competitor_profile_id
                    == profile_id
                )
                .order_by(entities.Core3SkuCompetitorProfilePair.candidate_sku_code)
            ).scalars()
        )
        relation_rows = list(
            self.db.execute(
                select(entities.Core3SkuCompetitorProfileRelation)
                .join(
                    entities.Core3SkuCompetitorProfilePair,
                    entities.Core3SkuCompetitorProfilePair.sku_competitor_profile_pair_id
                    == entities.Core3SkuCompetitorProfileRelation.sku_competitor_profile_pair_id,
                )
                .where(
                    entities.Core3SkuCompetitorProfilePair.sku_competitor_profile_id
                    == profile_id
                )
                .order_by(
                    entities.Core3SkuCompetitorProfileRelation.candidate_sku_code,
                    entities.Core3SkuCompetitorProfileRelation.relation_code,
                )
            ).scalars()
        )
        selection_rows = list(
            self.db.execute(
                select(entities.Core3SkuCompetitorProfileSelection)
                .where(
                    entities.Core3SkuCompetitorProfileSelection.sku_competitor_profile_id
                    == profile_id
                )
                .order_by(entities.Core3SkuCompetitorProfileSelection.selection_rank)
            ).scalars()
        )
        return CompetitorProfileReadBundle(
            version=_version_record(version),
            profile=_profile_draft(profile),
            pairs=[_pair_draft(row) for row in pair_rows],
            relations=[_relation_draft(row) for row in relation_rows],
            selections=[_selection_draft(row) for row in selection_rows],
            preview=preview,
        )

    def _assert_same_profile_inputs(
        self,
        existing: entities.Core3SkuCompetitorProfile,
        bundle: CompetitorProfilePersistenceBundle,
    ) -> None:
        if (
            existing.input_fingerprint != bundle.profile.input_fingerprint
            or existing.result_hash != bundle.profile.result_hash
        ):
            raise CompetitorProfileImmutableError(
                "draft SKU exists with different immutable inputs"
            )
        pair_model = entities.Core3SkuCompetitorProfilePair
        relation_model = entities.Core3SkuCompetitorProfileRelation
        selection_model = entities.Core3SkuCompetitorProfileSelection
        actual_pairs = dict(
            self.db.execute(
                select(pair_model.candidate_sku_code, pair_model.result_hash).where(
                    pair_model.sku_competitor_profile_id
                    == existing.sku_competitor_profile_id
                )
            ).all()
        )
        actual_relations = {
            (candidate_sku_code, relation_code): result_hash
            for candidate_sku_code, relation_code, result_hash in self.db.execute(
                select(
                    relation_model.candidate_sku_code,
                    relation_model.relation_code,
                    relation_model.result_hash,
                )
                .join(
                    pair_model,
                    pair_model.sku_competitor_profile_pair_id
                    == relation_model.sku_competitor_profile_pair_id,
                )
                .where(
                    pair_model.sku_competitor_profile_id
                    == existing.sku_competitor_profile_id
                )
            ).all()
        }
        actual_selections = dict(
            self.db.execute(
                select(
                    selection_model.candidate_sku_code,
                    selection_model.result_hash,
                ).where(
                    selection_model.sku_competitor_profile_id
                    == existing.sku_competitor_profile_id
                )
            ).all()
        )
        expected_pairs = {
            row.candidate_sku_code: row.result_hash for row in bundle.pairs
        }
        expected_relations = {
            (row.candidate_sku_code, row.relation_code): row.result_hash
            for row in bundle.relations
        }
        expected_selections = {
            row.candidate_sku_code: row.result_hash for row in bundle.selections
        }
        if (
            expected_pairs != actual_pairs
            or expected_relations != actual_relations
            or expected_selections != actual_selections
        ):
            raise CompetitorProfileImmutableError(
                "draft child rows differ from the existing profile"
            )

    def _find_version(
        self,
        *,
        release_scope_key: str,
        profile_version: str,
        rule_version: str,
    ) -> entities.Core3CompetitorProfileVersion | None:
        model = entities.Core3CompetitorProfileVersion
        return self.db.execute(
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.release_scope_key == release_scope_key)
            .where(model.profile_version == profile_version)
            .where(model.rule_version == rule_version)
        ).scalars().first()

    def _version_by_id(
        self,
        version_id: str,
        *,
        for_update: bool = False,
    ) -> entities.Core3CompetitorProfileVersion:
        model = entities.Core3CompetitorProfileVersion
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.competitor_profile_version_id == version_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        row = self.db.execute(stmt).scalars().first()
        if row is None:
            raise CompetitorProfileVersionNotFoundError(
                f"competitor profile version not found: {version_id}"
            )
        return row

    def _find_profile(
        self,
        *,
        version_id: str,
        target_sku_code: str,
    ) -> entities.Core3SkuCompetitorProfile | None:
        model = entities.Core3SkuCompetitorProfile
        return self.db.execute(
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.competitor_profile_version_id == version_id)
            .where(model.target_sku_code == target_sku_code)
        ).scalars().first()

    def _profile_by_id(self, profile_id: str) -> entities.Core3SkuCompetitorProfile:
        model = entities.Core3SkuCompetitorProfile
        row = self.db.execute(
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.sku_competitor_profile_id == profile_id)
        ).scalars().first()
        if row is None:
            raise CompetitorProfileNotFoundError(
                f"competitor SKU profile not found: {profile_id}"
            )
        return row

    def _pair_by_id(self, pair_id: str) -> entities.Core3SkuCompetitorProfilePair:
        model = entities.Core3SkuCompetitorProfilePair
        row = self.db.execute(
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.sku_competitor_profile_pair_id == pair_id)
        ).scalars().first()
        if row is None:
            raise CompetitorProfileNotFoundError(
                f"competitor pair not found: {pair_id}"
            )
        return row

    def _assert_context_scope(self, project_id: str, category_code: str) -> None:
        if project_id != self.project_id or category_code != self.category_code.value:
            raise ValueError("payload project/category scope does not match repository")

    @staticmethod
    def _assert_draft_version(version: entities.Core3CompetitorProfileVersion) -> None:
        if version.release_status != "draft" or version.is_current:
            raise CompetitorProfileDraftWriteNotAllowedError(
                "write_draft requires a non-current draft version"
            )

    @staticmethod
    def _assert_version_matches_scope(
        version: entities.Core3CompetitorProfileVersion,
        scope: Any,
    ) -> None:
        for field_name in (
            "project_id",
            "category_code",
            "product_category",
            "storage_batch_id",
            "release_scope_key",
            "profile_version",
            "schema_version",
            "rule_version",
            "method_version",
        ):
            if getattr(version, field_name) != getattr(scope, field_name):
                raise ValueError(f"profile {field_name} must match version")

    @staticmethod
    def _assert_same_version_inputs(
        existing: entities.Core3CompetitorProfileVersion,
        payload: CompetitorProfileVersionDraftCreate,
    ) -> None:
        if (
            existing.input_fingerprint != payload.input_fingerprint
            or existing.candidate_universe_fingerprint
            != payload.candidate_universe_fingerprint
            or existing.result_hash != payload.result_hash
        ):
            raise CompetitorProfileImmutableError(
                "profile version exists with different immutable inputs"
            )


def _version_entity_payload(payload: CompetitorProfileVersionDraftCreate) -> dict[str, Any]:
    raw = _model_payload(payload)
    scope = raw.pop("serving_scope")
    raw["serving_scope_json"] = scope
    raw["source_authorities_json"] = scope["source_authorities"]
    raw["source_batch_ids_json"] = scope["source_batch_ids"]
    raw["authoritative_sku_manifest_hash"] = scope[
        "authoritative_sku_manifest_hash"
    ]
    raw["review_reasons_json"] = raw.pop("review_reasons")
    return raw


def _profile_entity_payload(payload: SkuCompetitorProfileDraft) -> dict[str, Any]:
    raw = _scope_entity_payload(payload)
    raw.pop("sku_competitor_profile_id", None)
    profile = _json_payload(payload.profile_payload)
    raw.update(
        {
            "target_sku_code": payload.target_sku_code,
            "display_name_cn": profile["display_name_cn"],
            "analysis_state": profile["analysis_state"],
            "conclusion_state": profile["conclusion_state"],
            "freshness_status": profile["freshness_status"],
            "profile_confidence": payload.profile_payload.profile_confidence,
            "candidate_status_counts_json": profile["candidate_status_counts"],
            "relation_status_counts_json": profile["relation_status_counts"],
            "competitive_advantages_json": profile["competitive_advantages"],
            "substitutable_values_json": profile["substitutable_values"],
            "price_scale_pressure_json": profile["price_scale_pressures"],
            "same_brand_findings_json": profile["same_brand_findings"],
            "configuration_decisions_json": profile["configuration_decisions"],
            "no_conclusion_reason_json": profile["no_conclusion_reason"],
            "source_lineage_json": profile["source_lineage"],
            "qa_index_json": profile["qa_index"],
            "evidence_refs_json": profile["evidence_refs"],
            "limitations_json": profile["limitations"],
            "profile_payload_json": profile,
        }
    )
    return raw


def _pair_entity_payload(
    payload: SkuCompetitorPairDraft,
    *,
    profile_id: str,
) -> dict[str, Any]:
    raw = _scope_entity_payload(payload)
    raw.pop("sku_competitor_profile_pair_id", None)
    raw.pop("sku_competitor_profile_id", None)
    pair = _json_payload(payload.pair_payload)
    primary = next((row for row in pair["relation_assessments"] if row["is_primary"]), None)
    raw.update(
        {
            "sku_competitor_profile_id": profile_id,
            "target_sku_code": payload.target_sku_code,
            "candidate_sku_code": payload.candidate_sku_code,
            "candidate_identity_json": pair["candidate"],
            "recall_sources_json": pair["recall_sources"],
            "recall_facts_json": pair["recall_facts"],
            "competitor_member": payload.competitor_member,
            "reference_member": payload.reference_member,
            "candidate_status": payload.candidate_status,
            "purchase_pool_level": pair["purchase_pool"]["level"],
            "purchase_pool_json": pair["purchase_pool"],
            "evidence_family_json": pair["evidence_family_assessments"],
            "market_comparison_json": pair["market_comparison"],
            "question_eligibility_json": pair["question_eligibility"],
            "reference_purposes_json": pair["reference_purposes"],
            "primary_relation_code": primary["relation_code"] if primary else None,
            "relation_codes_json": [
                row["relation_code"]
                for row in pair["relation_assessments"]
                if row["status"] in {"passed", "limited"}
            ],
            "selected": payload.selected,
            "non_selection_reason_code": pair["non_selection_reason_code"],
            "non_selection_reason_cn": pair["non_selection_reason_cn"],
            "confidence_level": payload.confidence_level,
            "confidence": payload.pair_payload.confidence,
            "evidence_refs_json": pair["evidence_refs"],
            "limitations_json": pair["limitations"],
            "risk_flags_json": pair["risk_flags"],
            "pair_payload_json": pair,
        }
    )
    return raw


def _relation_entity_payload(
    payload: SkuCompetitorRelationDraft,
    *,
    pair_id: str,
) -> dict[str, Any]:
    raw = _scope_entity_payload(payload)
    raw.pop("sku_competitor_profile_relation_id", None)
    raw.pop("sku_competitor_profile_pair_id", None)
    relation = _json_payload(payload.relation_payload)
    raw.update(
        {
            "sku_competitor_profile_pair_id": pair_id,
            "target_sku_code": payload.target_sku_code,
            "candidate_sku_code": payload.candidate_sku_code,
            "relation_code": payload.relation_code,
            "relation_status": relation["status"],
            "is_primary": relation["is_primary"],
            "confidence_level": relation["confidence_level"],
            "gate_results_json": relation["gate_results"],
            "supporting_evidence_families_json": relation[
                "supporting_evidence_families"
            ],
            "business_effect_json": relation["business_effect"],
            "eligible_question_codes_json": relation["eligible_question_codes"],
            "reason_codes_json": relation["reason_codes"],
            "evidence_refs_json": relation["evidence_refs"],
            "limitations_json": relation["limitations"],
            "relation_payload_json": relation,
        }
    )
    return raw


def _selection_entity_payload(
    payload: SkuCompetitorSelectionDraft,
    *,
    profile_id: str,
    pair_id: str,
) -> dict[str, Any]:
    raw = _scope_entity_payload(payload)
    for key in (
        "sku_competitor_profile_selection_id",
        "sku_competitor_profile_id",
        "sku_competitor_profile_pair_id",
    ):
        raw.pop(key, None)
    selection = _json_payload(payload.selection_payload)
    raw.update(
        {
            "sku_competitor_profile_id": profile_id,
            "sku_competitor_profile_pair_id": pair_id,
            "target_sku_code": payload.target_sku_code,
            "candidate_sku_code": payload.candidate_sku_code,
            "selection_rank": payload.selection_rank,
            "primary_decision_topic": selection["primary_decision_topic"],
            "covered_decision_topics_json": selection["covered_decision_topics"],
            "primary_relation_code": selection["primary_relation_code"],
            "auxiliary_relation_codes_json": selection["auxiliary_relation_codes"],
            "selection_reason_cn": selection["selection_reason_cn"],
            "independent_information_reason_cn": selection[
                "independent_information_reason_cn"
            ],
            "price_value_pressure_summary_json": selection[
                "price_value_pressure_summary"
            ],
            "confidence_level": selection["confidence_level"],
            "evidence_refs_json": selection["evidence_refs"],
            "selection_payload_json": selection,
        }
    )
    return raw


def _scope_entity_payload(payload: BaseModel) -> dict[str, Any]:
    raw = payload.model_dump(
        mode="python",
        exclude={
            "profile_payload",
            "pair_payload",
            "relation_payload",
            "selection_payload",
        },
    )
    raw = {key: _jsonable(value) for key, value in raw.items()}
    raw["review_reasons_json"] = raw.pop("review_reasons")
    return raw


def _version_record(row: entities.Core3CompetitorProfileVersion) -> CompetitorProfileVersionRecord:
    payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    payload["serving_scope"] = ServingScope(**payload.pop("serving_scope_json"))
    payload.pop("source_authorities_json", None)
    payload.pop("source_batch_ids_json", None)
    payload.pop("authoritative_sku_manifest_hash", None)
    payload["safe_error_summary"] = payload.pop("safe_error_summary_json") or {}
    payload["review_reasons"] = payload.pop("review_reasons_json")
    return CompetitorProfileVersionRecord(**payload)


def _profile_draft(row: entities.Core3SkuCompetitorProfile) -> SkuCompetitorProfileDraft:
    return SkuCompetitorProfileDraft(
        **_row_scope(row),
        sku_competitor_profile_id=row.sku_competitor_profile_id,
        target_sku_code=row.target_sku_code,
        profile_payload=SkuCompetitorDecisionProfileDraft(**row.profile_payload_json),
    )


def _pair_draft(row: entities.Core3SkuCompetitorProfilePair) -> SkuCompetitorPairDraft:
    return SkuCompetitorPairDraft(
        **_row_scope(row),
        sku_competitor_profile_pair_id=row.sku_competitor_profile_pair_id,
        sku_competitor_profile_id=row.sku_competitor_profile_id,
        target_sku_code=row.target_sku_code,
        candidate_sku_code=row.candidate_sku_code,
        candidate_status=row.candidate_status,
        confidence_level=row.confidence_level,
        selected=row.selected,
        competitor_member=row.competitor_member,
        reference_member=row.reference_member,
        pair_payload=CompetitorPairDraft(**row.pair_payload_json),
    )


def _relation_draft(
    row: entities.Core3SkuCompetitorProfileRelation,
) -> SkuCompetitorRelationDraft:
    return SkuCompetitorRelationDraft(
        **_row_scope(row),
        sku_competitor_profile_relation_id=row.sku_competitor_profile_relation_id,
        sku_competitor_profile_pair_id=row.sku_competitor_profile_pair_id,
        target_sku_code=row.target_sku_code,
        candidate_sku_code=row.candidate_sku_code,
        relation_code=row.relation_code,
        relation_payload=RelationAssessment(**row.relation_payload_json),
    )


def _selection_draft(
    row: entities.Core3SkuCompetitorProfileSelection,
) -> SkuCompetitorSelectionDraft:
    return SkuCompetitorSelectionDraft(
        **_row_scope(row),
        sku_competitor_profile_selection_id=row.sku_competitor_profile_selection_id,
        sku_competitor_profile_id=row.sku_competitor_profile_id,
        sku_competitor_profile_pair_id=row.sku_competitor_profile_pair_id,
        target_sku_code=row.target_sku_code,
        candidate_sku_code=row.candidate_sku_code,
        selection_rank=row.selection_rank,
        selection_payload=KeyCompetitorSelectionDraft(**row.selection_payload_json),
    )


def _row_scope(row: Any) -> dict[str, Any]:
    return {
        "competitor_profile_version_id": row.competitor_profile_version_id,
        "project_id": row.project_id,
        "category_code": row.category_code,
        "product_category": row.product_category,
        "storage_batch_id": row.storage_batch_id,
        "release_scope_key": row.release_scope_key,
        "profile_version": row.profile_version,
        "schema_version": row.schema_version,
        "rule_version": row.rule_version,
        "method_version": row.method_version,
        "release_status": row.release_status,
        "is_current": row.is_current,
        "input_fingerprint": row.input_fingerprint,
        "result_hash": row.result_hash,
        "processing_status": row.processing_status,
        "review_required": row.review_required,
        "review_status": row.review_status,
        "review_reasons": row.review_reasons_json,
    }


def _model_payload(payload: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.model_dump(mode="python") if isinstance(payload, BaseModel) else dict(payload)
    return {key: _jsonable(value) for key, value in raw.items()}


def _json_payload(payload: BaseModel) -> dict[str, Any]:
    """Return a JSON-column-safe payload without weakening typed numeric columns."""

    return payload.model_dump(mode="json")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, BaseModel):
        return _model_payload(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "CompetitorProfileDraftWriteNotAllowedError",
    "CompetitorProfileImmutableError",
    "CompetitorProfileNotFoundError",
    "CompetitorProfileRepository",
    "CompetitorProfileRepositoryError",
    "CompetitorProfileVersionNotFoundError",
]
