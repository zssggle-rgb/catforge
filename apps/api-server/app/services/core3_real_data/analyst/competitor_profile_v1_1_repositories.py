"""Atomic, immutable persistence for typed competitor profile V1.1 analyses."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileDraftWriteNotAllowedError,
    CompetitorProfileImmutableError,
    CompetitorProfileNotFoundError,
    CompetitorProfileRepository,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_persistence_schemas import (
    CompetitorProfileV11CompactDTO,
    CompetitorProfileV11QuestionDTO,
    CompetitorProfileV11QuestionPair,
    CompetitorProfileV11ReadResult,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    ALL_RELATION_CODES,
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
    CompetitorProfileAnalysisDTO,
    ConclusionStrength,
    PairAnalysisSnapshot,
    PriorityCompetitorSelection,
    QuestionCode,
    RelationAssessment,
    VersionSkuAnalysisSnapshot,
)
from app.services.core3_real_data.hash_utils import stable_hash_json
from app.services.core3_real_data.repositories import Core3RepositoryContext


class CompetitorProfileV11IntegrityError(RuntimeError):
    """Raised when saved V1.1 rows no longer form one closed typed graph."""


ReadMode = Literal["full", "compact", "question_specific"]
_V11_PERSISTENCE_BATCH_SIZE = 8


class CompetitorProfileV11Repository(CompetitorProfileRepository):
    """Keep V1.1 immutable graphs separate from the legacy V1 repository path."""

    profile_schema_version = COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION

    def __init__(self, context: Core3RepositoryContext) -> None:
        super().__init__(context)

    def write_draft(
        self,
        dto: CompetitorProfileAnalysisDTO,
        *,
        use_savepoint: bool = True,
    ) -> CompetitorProfileAnalysisDTO:
        """Write snapshots and all target-SKU rows atomically.

        The caller owns the outer transaction.  A nested transaction ensures a
        failed child insert cannot leave only snapshots or a partial profile.
        """

        if not use_savepoint:
            raise ValueError("V1.1 atomic writes require use_savepoint=True")
        # Revalidate a fresh copy because Pydantic models can be mutated after
        # construction.  Persistence never trusts a formerly-valid instance.
        dto = CompetitorProfileAnalysisDTO.model_validate(dto.model_dump(mode="json"))

        self._assert_context_scope(
            dto.profile_version.project_id,
            dto.profile_version.category_code,
        )
        version = self._version_by_id(
            dto.profile_version.competitor_profile_version_id,
            for_update=True,
        )
        self._assert_v11_draft_version(version, dto)
        existing = self._find_v11_profile(
            version_id=version.competitor_profile_version_id,
            target_sku_code=dto.sku_summary.target_sku_code,
        )
        if existing is not None:
            readback = self._read_projection(
                version=version,
                profile=existing,
                read_mode="full",
                preview=True,
            ).full
            if readback != dto:
                raise CompetitorProfileImmutableError(
                    "V1.1 draft already exists with different immutable analysis"
                )
            return readback

        def insert() -> entities.Core3SkuCompetitorProfile:
            self._insert_materialized_graph(version, dto)
            profile_row = self._find_v11_profile(
                version_id=version.competitor_profile_version_id,
                target_sku_code=dto.sku_summary.target_sku_code,
            )
            if profile_row is None:
                raise CompetitorProfileV11IntegrityError(
                    "V1.1 insert did not produce a readable profile root"
                )
            return profile_row

        try:
            with self.db.begin_nested():
                profile_row = insert()
                readback = self._read_projection(
                    version=version,
                    profile=profile_row,
                    read_mode="full",
                    preview=True,
                ).full
                if readback != dto:
                    raise CompetitorProfileV11IntegrityError(
                        "V1.1 write readback differs from the typed input"
                    )
        except IntegrityError:
            concurrent = self._find_v11_profile(
                version_id=version.competitor_profile_version_id,
                target_sku_code=dto.sku_summary.target_sku_code,
            )
            if concurrent is None:
                raise
            readback = self._read_projection(
                version=version,
                profile=concurrent,
                read_mode="full",
                preview=True,
            ).full
            if readback != dto:
                raise CompetitorProfileImmutableError(
                    "concurrent V1.1 draft has different immutable analysis"
                )
            return readback
        assert readback is not None
        return readback

    def write_materialized_draft_without_readback(
        self,
        dto: CompetitorProfileAnalysisDTO,
    ) -> bool:
        """Persist a freshly materialized DTO without a second full graph copy.

        This bounded-memory path is intentionally limited to the production
        materializer boundary.  It re-runs the DTO's graph validator, verifies
        immutable hashes when the draft already exists, and streams child rows
        in small batches.  The caller owns commit/rollback and performs the
        deliberate acceptance readback after releasing generation memory.
        """

        dto.validate_dto()
        self._assert_context_scope(
            dto.profile_version.project_id,
            dto.profile_version.category_code,
        )
        version = self._version_by_id(
            dto.profile_version.competitor_profile_version_id,
            for_update=True,
        )
        self._assert_v11_draft_version(version, dto)
        existing = self._find_v11_profile(
            version_id=version.competitor_profile_version_id,
            target_sku_code=dto.sku_summary.target_sku_code,
        )
        if existing is not None:
            self._assert_existing_materialized_graph(existing, dto)
            return False
        with self.db.begin_nested():
            self._insert_materialized_graph(version, dto)
        return True

    def _insert_materialized_graph(
        self,
        version: entities.Core3CompetitorProfileVersion,
        dto: CompetitorProfileAnalysisDTO,
    ) -> None:
        snapshot_refs = self._write_snapshots(version, dto)
        self._assert_dto_snapshot_refs(dto, snapshot_refs)
        profile_row = self._insert_profile(version, dto)
        profile_id = profile_row.sku_competitor_profile_id
        self.db.expunge(profile_row)
        pair_ids = self._insert_pairs(version, profile_id, dto)
        self._insert_relations(version, pair_ids, dto)
        self._insert_selections(version, profile_id, pair_ids, dto)
        self.db.flush()

    def get_profile(
        self,
        *,
        competitor_profile_version_id: str,
        target_sku_code: str,
        read_mode: ReadMode = "full",
        question_code: QuestionCode | str | None = None,
        preview: bool = False,
    ) -> CompetitorProfileV11ReadResult | None:
        """Read one explicit version; draft access requires explicit preview."""

        version = self._version_by_id(competitor_profile_version_id)
        self._assert_v11_version(version)
        if version.release_status != "published" or not version.is_current:
            if not preview:
                raise CompetitorProfileDraftWriteNotAllowedError(
                    "non-current V1.1 versions require explicit preview=True"
                )
        profile = self._find_v11_profile(
            version_id=competitor_profile_version_id,
            target_sku_code=target_sku_code,
        )
        if profile is None:
            return None
        if not preview and (
            profile.release_status != "published" or not profile.is_current
        ):
            raise CompetitorProfileV11IntegrityError(
                "published V1.1 version and profile release state are inconsistent"
            )
        return self._read_projection(
            version=version,
            profile=profile,
            read_mode=read_mode,
            question_code=question_code,
            preview=preview,
        )

    def get_current_published_profile(
        self,
        *,
        release_scope_key: str,
        target_sku_code: str,
        read_mode: ReadMode = "full",
        question_code: QuestionCode | str | None = None,
    ) -> CompetitorProfileV11ReadResult | None:
        """Formal serving path: only the current published V1.1 version."""

        version_model = entities.Core3CompetitorProfileVersion
        version = (
            self.db.execute(
                select(version_model)
                .where(version_model.project_id == self.project_id)
                .where(version_model.category_code == self.category_code.value)
                .where(version_model.release_scope_key == release_scope_key)
                .where(
                    version_model.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .where(version_model.release_status == "published")
                .where(version_model.is_current.is_(True))
            )
            .scalars()
            .first()
        )
        if version is None:
            return None
        profile = self._find_v11_profile(
            version_id=version.competitor_profile_version_id,
            target_sku_code=target_sku_code,
        )
        if profile is None:
            return None
        if profile.release_status != "published" or not profile.is_current:
            raise CompetitorProfileV11IntegrityError(
                "current published V1.1 version and profile state are inconsistent"
            )
        return self._read_projection(
            version=version,
            profile=profile,
            read_mode=read_mode,
            question_code=question_code,
            preview=False,
        )

    def get_serving_current_published_profile(
        self,
        *,
        target_sku_code: str,
        read_mode: ReadMode = "full",
        question_code: QuestionCode | str | None = None,
    ) -> CompetitorProfileV11ReadResult | None:
        """Read the most recently activated formal current containing a target.

        Release scopes are immutable source fingerprints.  A normal analyst
        request does not know that internal key, so formal serving selects only
        from V1.1 rows already marked published/current and uses ``current_at``
        as the deterministic category-level activation pointer.
        """

        version_model = entities.Core3CompetitorProfileVersion
        profile_model = entities.Core3SkuCompetitorProfile
        release_scope_key = (
            self.db.execute(
                select(version_model.release_scope_key)
                .join(
                    profile_model,
                    profile_model.competitor_profile_version_id
                    == version_model.competitor_profile_version_id,
                )
                .where(version_model.project_id == self.project_id)
                .where(version_model.category_code == self.category_code.value)
                .where(
                    version_model.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .where(version_model.release_status == "published")
                .where(version_model.is_current.is_(True))
                .where(version_model.current_at.is_not(None))
                .where(profile_model.target_sku_code == target_sku_code)
                .where(profile_model.release_status == "published")
                .where(profile_model.is_current.is_(True))
                .order_by(
                    version_model.current_at.desc(),
                    version_model.competitor_profile_version_id.desc(),
                )
            )
            .scalars()
            .first()
        )
        if release_scope_key is None:
            return None
        return self.get_current_published_profile(
            release_scope_key=release_scope_key,
            target_sku_code=target_sku_code,
            read_mode=read_mode,
            question_code=question_code,
        )

    def _write_snapshots(
        self,
        version: entities.Core3CompetitorProfileVersion,
        dto: CompetitorProfileAnalysisDTO,
    ) -> dict[str, str]:
        snapshots = [dto.target_snapshot, *dto.candidate_snapshots]
        ref_owners: dict[str, str] = {}
        for snapshot in snapshots:
            sku_code = snapshot.identity_market.sku_code
            owner = ref_owners.setdefault(snapshot.snapshot_ref, sku_code)
            if owner != sku_code:
                raise CompetitorProfileV11IntegrityError(
                    "one V1.1 snapshot ref cannot identify different SKUs"
                )
        model = entities.Core3CompetitorProfileSkuSnapshot
        existing = list(
            self.db.execute(
                select(
                    model.sku_code,
                    model.project_id,
                    model.category_code,
                    model.release_scope_key,
                    model.input_fingerprint,
                    model.result_hash,
                    model.snapshot_json["snapshot_ref"]
                    .as_string()
                    .label("snapshot_ref"),
                )
                .where(
                    model.competitor_profile_version_id
                    == version.competitor_profile_version_id
                )
                .order_by(model.sku_code)
            ).mappings()
        )
        by_sku = {row.sku_code: row for row in existing}
        version_ref_owners: dict[str, str] = {}
        for row in existing:
            if (
                row.project_id != version.project_id
                or row.category_code != version.category_code
                or row.release_scope_key != version.release_scope_key
                or not row.snapshot_ref
            ):
                raise CompetitorProfileV11IntegrityError(
                    "saved V1.1 snapshot crosses its version or SKU scope"
                )
            owner = version_ref_owners.setdefault(row.snapshot_ref, row.sku_code)
            if owner != row.sku_code:
                raise CompetitorProfileV11IntegrityError(
                    "one V1.1 snapshot ref cannot identify different SKUs in a version"
                )
        saved_refs = {row.sku_code: row.snapshot_ref for row in existing}
        pending_identities: dict[str, tuple[str, str, str]] = {}
        pending: list[entities.Core3CompetitorProfileSkuSnapshot] = []

        def flush_pending() -> None:
            if not pending:
                return
            self.db.flush()
            for pending_row in pending:
                self.db.expunge(pending_row)
            pending.clear()

        for snapshot in snapshots:
            sku_code = snapshot.identity_market.sku_code
            pending_identity = pending_identities.get(sku_code)
            requested_identity = (
                snapshot.input_fingerprint,
                snapshot.result_hash,
                snapshot.snapshot_ref,
            )
            if pending_identity is not None:
                if pending_identity != requested_identity:
                    raise CompetitorProfileImmutableError(
                        f"V1.1 snapshot is inconsistent within one DTO: {sku_code}"
                    )
                continue
            owner = version_ref_owners.setdefault(snapshot.snapshot_ref, sku_code)
            if owner != sku_code:
                raise CompetitorProfileV11IntegrityError(
                    "one V1.1 snapshot ref cannot identify different SKUs in a version"
                )
            payload = _json(snapshot)
            row = by_sku.get(sku_code)
            if row is not None:
                if (
                    row.project_id != dto.profile_version.project_id
                    or row.category_code != dto.profile_version.category_code
                    or row.release_scope_key != dto.profile_version.release_scope_key
                    or row.input_fingerprint != snapshot.input_fingerprint
                    or row.result_hash != snapshot.result_hash
                    or row.snapshot_ref != snapshot.snapshot_ref
                ):
                    raise CompetitorProfileImmutableError(
                        f"V1.1 snapshot is immutable within a version: {sku_code}"
                    )
                continue
            row = model(
                competitor_profile_version_id=version.competitor_profile_version_id,
                project_id=version.project_id,
                category_code=version.category_code,
                release_scope_key=version.release_scope_key,
                sku_code=sku_code,
                profile_version=version.profile_version,
                schema_version=version.schema_version,
                rule_version=version.rule_version,
                method_version=version.method_version,
                snapshot_json=payload,
                module_availability_json=_json(snapshot.module_availability),
                evidence_refs_json=_json(snapshot.evidence_refs),
                source_lineage_json=_json(snapshot.source_lineage),
                limitations_json=list(snapshot.limitations),
                input_fingerprint=snapshot.input_fingerprint,
                result_hash=snapshot.result_hash,
            )
            self.db.add(row)
            pending.append(row)
            pending_identities[sku_code] = requested_identity
            saved_refs[sku_code] = snapshot.snapshot_ref
            if len(pending) >= _V11_PERSISTENCE_BATCH_SIZE:
                flush_pending()
        flush_pending()
        return saved_refs

    def _insert_profile(
        self,
        version: entities.Core3CompetitorProfileVersion,
        dto: CompetitorProfileAnalysisDTO,
    ) -> entities.Core3SkuCompetitorProfile:
        summary = dto.sku_summary
        identity = dto.target_snapshot.identity_market
        review_items = _json(summary.review_items)
        available_count = sum(
            count
            for availability, count in summary.dimension_availability_counts.items()
            if availability in {"available", "partial"}
        )
        total_dimension_count = sum(summary.dimension_availability_counts.values())
        confidence = (
            Decimal(available_count) / Decimal(total_dimension_count)
            if total_dimension_count
            else Decimal("0")
        )
        profile = entities.Core3SkuCompetitorProfile(
            competitor_profile_version_id=version.competitor_profile_version_id,
            project_id=version.project_id,
            category_code=version.category_code,
            product_category=version.product_category,
            storage_batch_id=version.storage_batch_id,
            release_scope_key=version.release_scope_key,
            profile_version=version.profile_version,
            schema_version=version.schema_version,
            rule_version=version.rule_version,
            method_version=version.method_version,
            target_sku_code=summary.target_sku_code,
            display_name_cn=identity.model_name or identity.sku_code,
            analysis_state=_analysis_state(summary.dimension_availability_counts),
            conclusion_state=(
                "available" if dto.priority_selections else "no_priority_competitor"
            ),
            freshness_status="unknown",
            profile_confidence=confidence,
            candidate_status_counts_json={
                "analysis_candidate_count": summary.analysis_candidate_count,
                "legacy_candidate_count": summary.legacy_candidate_count,
            },
            relation_status_counts_json=dict(summary.conclusion_strength_counts),
            competitive_advantages_json=_json(summary.competitive_advantages),
            substitutable_values_json=_json(summary.substitutable_values),
            price_scale_pressure_json=_json(summary.price_volume_pressures),
            same_brand_findings_json=[],
            configuration_decisions_json=_json(summary.configuration_differences),
            no_conclusion_reason_json={},
            source_lineage_json=[],
            qa_index_json=_json(dto.full_pair_index),
            evidence_refs_json=[],
            limitations_json=list(summary.limitations),
            profile_payload_json={
                "profile_version": _json(dto.profile_version),
                "generation_receipt": _json(dto.generation_receipt),
                "full_pair_index": _json(dto.full_pair_index),
                "compact_integrity_hash": _compact_integrity_hash(
                    profile_version=_json(dto.profile_version),
                    generation_receipt=_json(dto.generation_receipt),
                    sku_summary=_json(summary),
                    priority_selections=_json(dto.priority_selections),
                    full_pair_index=_json(dto.full_pair_index),
                    profile_result_hash=dto.profile_result_hash,
                ),
            },
            analysis_summary_json=_json(summary),
            analysis_fact_index_json=_json(dto.fact_index),
            analysis_evidence_index_json=_json(dto.evidence_index),
            analysis_result_hash=dto.profile_result_hash,
            analysis_candidate_count=len(dto.pair_analyses),
            analysis_available_dimension_count=available_count,
            analysis_review_item_count=len(review_items),
            release_status="draft",
            is_current=False,
            input_fingerprint=dto.generation_receipt.input_fingerprint,
            result_hash=dto.profile_result_hash,
            processing_status="success",
            review_required=bool(review_items),
            review_status="pending" if review_items else "auto_pass",
            review_reasons_json=[
                str(
                    item.get("review_code")
                    or item.get("reason_code")
                    or "review_required"
                )
                for item in review_items
            ],
        )
        self.db.add(profile)
        self.db.flush()
        return profile

    def _insert_pairs(
        self,
        version: entities.Core3CompetitorProfileVersion,
        profile_id: str,
        dto: CompetitorProfileAnalysisDTO,
    ) -> dict[str, str]:
        selected = {row.candidate_sku_code: row for row in dto.priority_selections}
        snapshot_by_sku = {
            row.identity_market.sku_code: row for row in dto.candidate_snapshots
        }
        pair_ids: dict[str, str] = {}
        pending: list[entities.Core3SkuCompetitorProfilePair] = []

        def flush_pending() -> None:
            if not pending:
                return
            self.db.flush()
            for pending_row in pending:
                self.db.expunge(pending_row)
            pending.clear()

        for pair in dto.pair_analyses:
            selection = selected.get(pair.candidate_sku_code)
            candidate_snapshot = snapshot_by_sku[pair.candidate_sku_code]
            primary_relation = _primary_relation(pair)
            score = pair.score_breakdown
            selection_question = _question(pair, QuestionCode.KEY_COMPETITOR_SELECTION)
            pair_id = entities.new_id()
            row = entities.Core3SkuCompetitorProfilePair(
                sku_competitor_profile_pair_id=pair_id,
                sku_competitor_profile_id=profile_id,
                competitor_profile_version_id=version.competitor_profile_version_id,
                project_id=version.project_id,
                category_code=version.category_code,
                product_category=version.product_category,
                storage_batch_id=version.storage_batch_id,
                release_scope_key=version.release_scope_key,
                profile_version=version.profile_version,
                schema_version=version.schema_version,
                rule_version=version.rule_version,
                method_version=version.method_version,
                target_sku_code=pair.target_sku_code,
                candidate_sku_code=pair.candidate_sku_code,
                candidate_identity_json=_json(candidate_snapshot.identity_market),
                recall_sources_json=list(pair.recall_sources),
                recall_facts_json=_json(pair.recall_facts),
                competitor_member=_enum_value(pair.scope_status) == "analyzable",
                reference_member=False,
                candidate_status=(
                    "eligible"
                    if _enum_value(pair.scope_status) == "analyzable"
                    else "recalled_only"
                ),
                scope_status=_enum_value(pair.scope_status),
                exclusion_reason_code=pair.exclusion_reason_code,
                target_snapshot_ref=pair.target_snapshot_ref,
                candidate_snapshot_ref=pair.candidate_snapshot_ref,
                purchase_pool_level=(
                    pair.purchase_pool.level if pair.purchase_pool else "unknown"
                ),
                purchase_pool_json=_json(pair.purchase_pool)
                if pair.purchase_pool
                else {},
                evidence_family_json=[],
                market_comparison_json=_json(pair.market_validation)
                if pair.market_validation
                else {},
                question_eligibility_json=_json(pair.business_questions),
                reference_purposes_json=[],
                primary_relation_code=(
                    _enum_value(primary_relation.relation_code)
                    if primary_relation
                    else None
                ),
                relation_codes_json=[
                    _enum_value(row.relation_code) for row in pair.relation_assessments
                ],
                selected=selection is not None,
                non_selection_reason_code=(
                    None
                    if selection
                    else pair.selection_assessment.selection_reason_code
                    if pair.selection_assessment is not None
                    else "not_priority_selected"
                ),
                non_selection_reason_cn=(
                    None
                    if selection or pair.selection_assessment is None
                    else pair.selection_assessment.selection_reason_cn
                ),
                confidence_level=_confidence_level(pair.overall_conclusion_strength),
                confidence=(
                    score.ranking_score
                    if score and score.ranking_score is not None
                    else Decimal("0")
                ),
                evidence_refs_json=_json(pair.evidence_refs),
                limitations_json=list(pair.limitations),
                risk_flags_json=[],
                pair_payload_json={},
                analysis_snapshot_json=_json(pair),
                analysis_conclusion_strength=_enum_value(
                    pair.overall_conclusion_strength
                ),
                analysis_score=(score.ranking_score if score else None),
                analysis_available_weight=(score.available_weight if score else None),
                analysis_result_hash=pair.result_hash,
                analysis_review_required=pair.review_required,
                selection_question_code=(
                    QuestionCode.KEY_COMPETITOR_SELECTION.value if selection else None
                ),
                selection_conclusion_strength=(
                    _enum_value(selection_question.conclusion_strength)
                    if selection and selection_question is not None
                    else None
                ),
                release_status="draft",
                is_current=False,
                input_fingerprint=pair.input_fingerprint,
                result_hash=pair.result_hash,
                processing_status="success",
                review_required=pair.review_required,
                review_status="pending" if pair.review_required else "auto_pass",
                review_reasons_json=[
                    str(
                        item.get("review_code")
                        or item.get("reason_code")
                        or "review_required"
                    )
                    for item in _json(pair.review_items)
                ],
            )
            self.db.add(row)
            pending.append(row)
            pair_ids[pair.candidate_sku_code] = pair_id
            if len(pending) >= _V11_PERSISTENCE_BATCH_SIZE:
                flush_pending()
        flush_pending()
        return pair_ids

    def _insert_relations(
        self,
        version: entities.Core3CompetitorProfileVersion,
        pair_ids: dict[str, str],
        dto: CompetitorProfileAnalysisDTO,
    ) -> None:
        pending: list[entities.Core3SkuCompetitorProfileRelation] = []

        def flush_pending() -> None:
            if not pending:
                return
            self.db.flush()
            for pending_row in pending:
                self.db.expunge(pending_row)
            pending.clear()

        for pair in dto.pair_analyses:
            primary = _primary_relation(pair)
            for relation in pair.relation_assessments:
                review_items = _json(relation.review_items)
                pending.append(
                    entities.Core3SkuCompetitorProfileRelation(
                        sku_competitor_profile_relation_id=entities.new_id(),
                        sku_competitor_profile_pair_id=pair_ids[
                            pair.candidate_sku_code
                        ],
                        competitor_profile_version_id=version.competitor_profile_version_id,
                        project_id=version.project_id,
                        category_code=version.category_code,
                        product_category=version.product_category,
                        storage_batch_id=version.storage_batch_id,
                        release_scope_key=version.release_scope_key,
                        profile_version=version.profile_version,
                        schema_version=version.schema_version,
                        rule_version=version.rule_version,
                        method_version=version.method_version,
                        target_sku_code=pair.target_sku_code,
                        candidate_sku_code=pair.candidate_sku_code,
                        relation_code=_enum_value(relation.relation_code),
                        relation_status=_enum_value(relation.status),
                        analysis_relation_status=_enum_value(relation.status),
                        analysis_review_items_json=review_items,
                        is_primary=(
                            primary is not None
                            and relation.relation_code == primary.relation_code
                        ),
                        confidence_level=_confidence_level(
                            relation.conclusion_strength
                        ),
                        gate_results_json=[],
                        supporting_evidence_families_json=[],
                        business_effect_json={},
                        eligible_question_codes_json=[],
                        reason_codes_json=[],
                        evidence_refs_json=_json(relation.evidence_refs),
                        limitations_json=list(relation.limitations),
                        relation_payload_json=_json(relation),
                        release_status="draft",
                        is_current=False,
                        input_fingerprint=relation.input_fingerprint,
                        result_hash=relation.result_hash,
                        processing_status="success",
                        review_required=relation.review_required,
                        review_status="pending"
                        if relation.review_required
                        else "auto_pass",
                        review_reasons_json=[
                            str(
                                item.get("review_code")
                                or item.get("reason_code")
                                or "review_required"
                            )
                            for item in review_items
                        ],
                    )
                )
                self.db.add(pending[-1])
                if len(pending) >= _V11_PERSISTENCE_BATCH_SIZE:
                    flush_pending()
        flush_pending()

    def _insert_selections(
        self,
        version: entities.Core3CompetitorProfileVersion,
        profile_id: str,
        pair_ids: dict[str, str],
        dto: CompetitorProfileAnalysisDTO,
    ) -> None:
        pair_by_sku = {row.candidate_sku_code: row for row in dto.pair_analyses}
        rows = []
        for selection in dto.priority_selections:
            pair = pair_by_sku[selection.candidate_sku_code]
            formal_relation = _primary_relation(pair)
            # The legacy selection column is non-null.  When no V1.1 relation
            # is passed/limited, retain the first frozen relation code only as
            # a compatibility index; no relation row is marked primary and no
            # V1.1 reader or agent may consume it as a business conclusion.
            index_relation = formal_relation or (
                pair.relation_assessments[0] if pair.relation_assessments else None
            )
            if index_relation is None:
                raise CompetitorProfileV11IntegrityError(
                    "selected V1.1 pairs require one persisted relation index"
                )
            rows.append(
                entities.Core3SkuCompetitorProfileSelection(
                    sku_competitor_profile_id=profile_id,
                    sku_competitor_profile_pair_id=pair_ids[
                        selection.candidate_sku_code
                    ],
                    competitor_profile_version_id=version.competitor_profile_version_id,
                    project_id=version.project_id,
                    category_code=version.category_code,
                    product_category=version.product_category,
                    storage_batch_id=version.storage_batch_id,
                    release_scope_key=version.release_scope_key,
                    profile_version=version.profile_version,
                    schema_version=version.schema_version,
                    rule_version=version.rule_version,
                    method_version=version.method_version,
                    target_sku_code=selection.target_sku_code,
                    candidate_sku_code=selection.candidate_sku_code,
                    selection_rank=selection.selection_rank,
                    primary_decision_topic="purchase_choice",
                    covered_decision_topics_json=[
                        QuestionCode.KEY_COMPETITOR_SELECTION.value
                    ],
                    primary_relation_code=_enum_value(index_relation.relation_code),
                    auxiliary_relation_codes_json=[
                        _enum_value(row.relation_code)
                        for row in pair.relation_assessments
                        if row.relation_code != index_relation.relation_code
                    ],
                    selection_reason_cn=selection.selection_reason_cn,
                    independent_information_reason_cn=selection.selection_reason_cn,
                    price_value_pressure_summary_json={},
                    confidence_level=_confidence_level(
                        selection.selection_conclusion_strength
                    ),
                    evidence_refs_json=[],
                    selection_payload_json=_json(selection),
                    selection_policy_version="competitor_profile_selection_v1_1",
                    selection_score=selection.selection_score,
                    selection_available_weight=selection.selection_available_weight,
                    selection_conclusion_strength=_enum_value(
                        selection.selection_conclusion_strength
                    ),
                    selection_role_codes_json=[
                        _enum_value(row) for row in selection.role_codes
                    ],
                    selection_score_breakdown_json=_json(pair.score_breakdown),
                    release_status="draft",
                    is_current=False,
                    input_fingerprint=pair.input_fingerprint,
                    result_hash=selection.result_hash,
                    processing_status="success",
                    review_required=False,
                    review_status="auto_pass",
                    review_reasons_json=[],
                )
            )
        self.db.add_all(rows)

    def _read_projection(
        self,
        *,
        version: entities.Core3CompetitorProfileVersion,
        profile: entities.Core3SkuCompetitorProfile,
        read_mode: ReadMode,
        preview: bool,
        question_code: QuestionCode | str | None = None,
    ) -> CompetitorProfileV11ReadResult:
        self._assert_v11_version(version)
        if profile.schema_version != COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION:
            raise CompetitorProfileV11IntegrityError(
                "legacy V1 rows cannot enter the V1.1 reader"
            )
        self._assert_saved_row_scope(version, profile, profile.target_sku_code)
        self._assert_version_snapshot_ref_owners(version)
        if read_mode == "question_specific":
            if question_code is None:
                raise ValueError("question_specific reads require question_code")
            question = QuestionCode(question_code)
        elif question_code is not None:
            raise ValueError("question_code is only valid for question_specific reads")
        else:
            question = None

        if read_mode == "compact":
            return self._read_compact_projection(
                version=version,
                profile=profile,
                preview=preview,
            )

        pair_model = entities.Core3SkuCompetitorProfilePair
        pairs = list(
            self.db.execute(
                select(pair_model)
                .where(
                    pair_model.sku_competitor_profile_id
                    == profile.sku_competitor_profile_id
                )
                .where(
                    pair_model.schema_version == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .order_by(pair_model.candidate_sku_code)
            ).scalars()
        )
        snapshot_model = entities.Core3CompetitorProfileSkuSnapshot
        snapshots = list(
            self.db.execute(
                select(snapshot_model)
                .where(
                    snapshot_model.competitor_profile_version_id
                    == version.competitor_profile_version_id
                )
                .where(
                    snapshot_model.sku_code.in_(
                        [
                            profile.target_sku_code,
                            *[row.candidate_sku_code for row in pairs],
                        ]
                    )
                )
                .order_by(snapshot_model.sku_code)
            ).scalars()
        )
        relation_model = entities.Core3SkuCompetitorProfileRelation
        relations = list(
            self.db.execute(
                select(relation_model)
                .where(
                    relation_model.competitor_profile_version_id
                    == version.competitor_profile_version_id
                )
                .where(relation_model.target_sku_code == profile.target_sku_code)
                .where(
                    relation_model.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .order_by(
                    relation_model.candidate_sku_code, relation_model.relation_code
                )
            ).scalars()
        )
        selection_model = entities.Core3SkuCompetitorProfileSelection
        selections = list(
            self.db.execute(
                select(selection_model)
                .where(
                    selection_model.sku_competitor_profile_id
                    == profile.sku_competitor_profile_id
                )
                .where(
                    selection_model.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .order_by(selection_model.selection_rank)
            ).scalars()
        )
        for row in [*pairs, *relations, *selections]:
            self._assert_saved_row_scope(version, row, profile.target_sku_code)
        if not preview:
            release_rows = [*pairs, *relations, *selections]
            if any(
                row.release_status != "published" or not row.is_current
                for row in release_rows
            ):
                raise CompetitorProfileV11IntegrityError(
                    "formal V1.1 reads require every analytical row to be current published"
                )

        context_payload = dict(profile.profile_payload_json or {})
        try:
            profile_version = context_payload["profile_version"]
            generation_receipt = context_payload["generation_receipt"]
            full_pair_index = context_payload["full_pair_index"]
            target_snapshot, candidate_snapshots = self._resolve_read_snapshots(
                version=version,
                profile=profile,
                pairs=pairs,
                snapshots=snapshots,
            )
            pair_analyses = [
                PairAnalysisSnapshot.model_validate(_validated_pair_payload(row))
                for row in pairs
            ]
            priority_selections = [
                PriorityCompetitorSelection.model_validate(
                    _validated_selection_payload(row)
                )
                for row in selections
            ]
            self._assert_relation_indices(pair_analyses, relations)
            dto = CompetitorProfileAnalysisDTO.model_validate(
                {
                    "profile_version": profile_version,
                    "generation_receipt": generation_receipt,
                    "target_snapshot": target_snapshot,
                    "candidate_snapshots": candidate_snapshots,
                    "sku_summary": profile.analysis_summary_json,
                    "priority_selections": priority_selections,
                    "full_pair_index": full_pair_index,
                    "pair_analyses": pair_analyses,
                    "fact_index": profile.analysis_fact_index_json,
                    "evidence_index": profile.analysis_evidence_index_json,
                    "profile_result_hash": profile.analysis_result_hash,
                }
            )
            self._assert_analysis_context(version, dto.profile_version)
        except (KeyError, TypeError, ValueError) as exc:
            raise CompetitorProfileV11IntegrityError(
                "saved V1.1 rows do not form a valid typed profile"
            ) from exc

        if profile.result_hash != dto.profile_result_hash:
            raise CompetitorProfileV11IntegrityError(
                "V1.1 profile hash columns disagree"
            )
        if read_mode == "full":
            return CompetitorProfileV11ReadResult(
                status="available",
                read_mode="full",
                preview=preview,
                competitor_profile_version_id=version.competitor_profile_version_id,
                full=dto,
            )
        assert question is not None
        snapshot_by_sku = {
            row.identity_market.sku_code: row for row in dto.candidate_snapshots
        }
        question_pairs = []
        for pair in dto.pair_analyses:
            result = _question(pair, question)
            if result is None:
                continue
            question_pairs.append(
                CompetitorProfileV11QuestionPair(
                    candidate_snapshot=snapshot_by_sku[pair.candidate_sku_code],
                    pair_analysis=pair,
                    question_result=result,
                )
            )
        return CompetitorProfileV11ReadResult(
            status="available",
            read_mode="question_specific",
            preview=preview,
            competitor_profile_version_id=version.competitor_profile_version_id,
            question=CompetitorProfileV11QuestionDTO(
                question_code=question,
                profile_version=dto.profile_version,
                generation_receipt=dto.generation_receipt,
                target_snapshot=dto.target_snapshot,
                sku_summary=dto.sku_summary,
                priority_selections=dto.priority_selections,
                pairs=question_pairs,
                fact_index=dto.fact_index,
                evidence_index=dto.evidence_index,
                profile_result_hash=dto.profile_result_hash,
            ),
        )

    def _read_compact_projection(
        self,
        *,
        version: entities.Core3CompetitorProfileVersion,
        profile: entities.Core3SkuCompetitorProfile,
        preview: bool,
    ) -> CompetitorProfileV11ReadResult:
        """Read the compact index without loading pair/relation analysis JSON."""

        pair_model = entities.Core3SkuCompetitorProfilePair
        pair_headers = list(
            self.db.execute(
                select(
                    pair_model.candidate_sku_code,
                    pair_model.target_snapshot_ref,
                    pair_model.candidate_snapshot_ref,
                    pair_model.analysis_result_hash,
                    pair_model.analysis_conclusion_strength,
                    pair_model.analysis_score,
                    pair_model.analysis_available_weight,
                    pair_model.selection_conclusion_strength,
                    pair_model.scope_status,
                    pair_model.competitor_profile_version_id,
                    pair_model.project_id,
                    pair_model.category_code,
                    pair_model.product_category,
                    pair_model.release_scope_key,
                    pair_model.profile_version,
                    pair_model.schema_version,
                    pair_model.rule_version,
                    pair_model.method_version,
                    pair_model.target_sku_code,
                    pair_model.release_status,
                    pair_model.is_current,
                )
                .where(
                    pair_model.sku_competitor_profile_id
                    == profile.sku_competitor_profile_id
                )
                .where(
                    pair_model.schema_version == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .order_by(pair_model.candidate_sku_code)
            ).all()
        )
        snapshot_model = entities.Core3CompetitorProfileSkuSnapshot
        snapshots = list(
            self.db.execute(
                select(snapshot_model)
                .where(
                    snapshot_model.competitor_profile_version_id
                    == version.competitor_profile_version_id
                )
                .where(
                    snapshot_model.sku_code.in_(
                        [
                            profile.target_sku_code,
                            *[row.candidate_sku_code for row in pair_headers],
                        ]
                    )
                )
                .order_by(snapshot_model.sku_code)
            ).scalars()
        )
        selection_model = entities.Core3SkuCompetitorProfileSelection
        selections = list(
            self.db.execute(
                select(selection_model)
                .where(
                    selection_model.sku_competitor_profile_id
                    == profile.sku_competitor_profile_id
                )
                .where(
                    selection_model.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .order_by(selection_model.selection_rank)
            ).scalars()
        )
        relation_model = entities.Core3SkuCompetitorProfileRelation
        relation_headers = list(
            self.db.execute(
                select(
                    relation_model.candidate_sku_code,
                    relation_model.relation_code,
                    relation_model.competitor_profile_version_id,
                    relation_model.project_id,
                    relation_model.category_code,
                    relation_model.product_category,
                    relation_model.release_scope_key,
                    relation_model.profile_version,
                    relation_model.schema_version,
                    relation_model.rule_version,
                    relation_model.method_version,
                    relation_model.target_sku_code,
                    relation_model.release_status,
                    relation_model.is_current,
                )
                .where(
                    relation_model.competitor_profile_version_id
                    == version.competitor_profile_version_id
                )
                .where(relation_model.target_sku_code == profile.target_sku_code)
                .where(
                    relation_model.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
                .order_by(
                    relation_model.candidate_sku_code, relation_model.relation_code
                )
            ).all()
        )
        for row in [*pair_headers, *relation_headers, *selections]:
            self._assert_saved_row_scope(version, row, profile.target_sku_code)
        if not preview:
            if any(
                row.release_status != "published" or not row.is_current
                for row in [*pair_headers, *relation_headers, *selections]
            ):
                raise CompetitorProfileV11IntegrityError(
                    "formal V1.1 reads require every analytical row to be current published"
                )

        try:
            context = dict(profile.profile_payload_json or {})
            pair_index = context["full_pair_index"]
            index_headers = {
                row["candidate_sku_code"]: (
                    row["pair_result_hash"],
                    row["scope_status"],
                    row["conclusion_strength"],
                )
                for row in pair_index
            }
            actual_headers = {
                row.candidate_sku_code: (
                    row.analysis_result_hash,
                    row.scope_status,
                    row.analysis_conclusion_strength,
                )
                for row in pair_headers
            }
            if index_headers != actual_headers:
                raise CompetitorProfileV11IntegrityError(
                    "compact pair index differs from saved pair rows"
                )
            pair_header_by_sku = {row.candidate_sku_code: row for row in pair_headers}
            pair_index_by_sku = {row["candidate_sku_code"]: row for row in pair_index}
            selection_payloads = []
            for row in selections:
                payload = _validated_selection_payload(row)
                pair_header = pair_header_by_sku.get(row.candidate_sku_code)
                index_item = pair_index_by_sku.get(row.candidate_sku_code)
                if pair_header is None or index_item is None:
                    raise CompetitorProfileV11IntegrityError(
                        "compact selection points outside the pair index"
                    )
                _assert_compact_selection(payload, row, pair_header, index_item)
                selection_payloads.append(payload)
            expected_relations = {
                (row.candidate_sku_code, relation_code)
                for row in pair_headers
                if row.scope_status == "analyzable"
                for relation_code in ALL_RELATION_CODES
            }
            actual_relations = {
                (row.candidate_sku_code, row.relation_code) for row in relation_headers
            }
            if expected_relations != actual_relations:
                raise CompetitorProfileV11IntegrityError(
                    "compact relation index differs from saved analyzable pairs"
                )
            snapshot_by_ref: dict[str, entities.Core3CompetitorProfileSkuSnapshot] = {}
            for row in snapshots:
                payload = dict(row.snapshot_json or {})
                snapshot_ref = payload.get("snapshot_ref")
                if (
                    not snapshot_ref
                    or snapshot_ref in snapshot_by_ref
                    or payload.get("competitor_profile_version_id")
                    != version.competitor_profile_version_id
                    or payload.get("project_id") != version.project_id
                    or payload.get("category_code") != version.category_code
                    or payload.get("release_scope_key") != version.release_scope_key
                    or (payload.get("identity_market") or {}).get("sku_code")
                    != row.sku_code
                    or payload.get("result_hash") != row.result_hash
                ):
                    raise CompetitorProfileV11IntegrityError(
                        "compact snapshot index contains a cross-scope or inconsistent row"
                    )
                snapshot_by_ref[str(snapshot_ref)] = row
            target_refs = {row.target_snapshot_ref for row in pair_headers}
            if pair_headers:
                if len(target_refs) != 1 or None in target_refs:
                    raise CompetitorProfileV11IntegrityError(
                        "compact pairs do not share one target snapshot"
                    )
                target_row = snapshot_by_ref.get(next(iter(target_refs)))
            else:
                target_rows = [
                    row for row in snapshots if row.sku_code == profile.target_sku_code
                ]
                target_row = target_rows[0] if len(target_rows) == 1 else None
            if target_row is None or target_row.sku_code != profile.target_sku_code:
                raise CompetitorProfileV11IntegrityError(
                    "compact target snapshot ref is dangling"
                )
            for row in pair_headers:
                snapshot = snapshot_by_ref.get(row.candidate_snapshot_ref)
                if snapshot is None or snapshot.sku_code != row.candidate_sku_code:
                    raise CompetitorProfileV11IntegrityError(
                        f"compact candidate snapshot ref is dangling: {row.candidate_sku_code}"
                    )
            compact = CompetitorProfileV11CompactDTO.model_validate(
                {
                    "profile_version": context["profile_version"],
                    "generation_receipt": context["generation_receipt"],
                    "target_snapshot": target_row.snapshot_json,
                    "sku_summary": profile.analysis_summary_json,
                    "priority_selections": selection_payloads,
                    "full_pair_index": pair_index,
                    "profile_result_hash": profile.analysis_result_hash,
                }
            )
            self._assert_analysis_context(version, compact.profile_version)
            expected_compact_hash = context["compact_integrity_hash"]
            actual_compact_hash = _compact_integrity_hash(
                profile_version=compact.profile_version.model_dump(mode="json"),
                generation_receipt=compact.generation_receipt.model_dump(mode="json"),
                sku_summary=compact.sku_summary.model_dump(mode="json"),
                priority_selections=[
                    row.model_dump(mode="json") for row in compact.priority_selections
                ],
                full_pair_index=[
                    row.model_dump(mode="json") for row in compact.full_pair_index
                ],
                profile_result_hash=compact.profile_result_hash,
            )
            if expected_compact_hash != actual_compact_hash:
                raise CompetitorProfileV11IntegrityError(
                    "compact integrity receipt differs from the saved summary or pair index"
                )
        except CompetitorProfileV11IntegrityError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise CompetitorProfileV11IntegrityError(
                "saved V1.1 rows do not form a valid compact profile"
            ) from exc
        if profile.result_hash != compact.profile_result_hash:
            raise CompetitorProfileV11IntegrityError(
                "V1.1 profile hash columns disagree"
            )
        return CompetitorProfileV11ReadResult(
            status="available",
            read_mode="compact",
            preview=preview,
            competitor_profile_version_id=version.competitor_profile_version_id,
            compact=compact,
        )

    def _assert_version_snapshot_ref_owners(
        self,
        version: entities.Core3CompetitorProfileVersion,
    ) -> None:
        """Require every logical snapshot ref to have one SKU owner per version."""

        model = entities.Core3CompetitorProfileSkuSnapshot
        ref_rows = self.db.execute(
            select(
                model.sku_code,
                model.snapshot_json["snapshot_ref"].as_string().label("snapshot_ref"),
            )
            .where(
                model.competitor_profile_version_id
                == version.competitor_profile_version_id
            )
            .order_by(model.sku_code)
        ).all()
        owners: dict[str, str] = {}
        for row in ref_rows:
            snapshot_ref = row.snapshot_ref
            if not snapshot_ref:
                raise CompetitorProfileV11IntegrityError(
                    "V1.1 version contains a snapshot without a logical ref"
                )
            owner = owners.setdefault(str(snapshot_ref), row.sku_code)
            if owner != row.sku_code:
                raise CompetitorProfileV11IntegrityError(
                    "one V1.1 snapshot ref cannot identify different SKUs in a version"
                )

    @staticmethod
    def _assert_saved_row_scope(
        version: entities.Core3CompetitorProfileVersion,
        row: Any,
        target_sku_code: str,
    ) -> None:
        expected = (
            version.competitor_profile_version_id,
            version.project_id,
            version.category_code,
            version.product_category,
            version.release_scope_key,
            version.profile_version,
            version.schema_version,
            version.rule_version,
            version.method_version,
            target_sku_code,
        )
        actual = (
            row.competitor_profile_version_id,
            row.project_id,
            row.category_code,
            row.product_category,
            row.release_scope_key,
            row.profile_version,
            row.schema_version,
            row.rule_version,
            row.method_version,
            row.target_sku_code,
        )
        if actual != expected:
            raise CompetitorProfileV11IntegrityError(
                "saved V1.1 row crosses version, category, release, or target scope"
            )

    def _resolve_read_snapshots(
        self,
        *,
        version: entities.Core3CompetitorProfileVersion,
        profile: entities.Core3SkuCompetitorProfile,
        pairs: Sequence[entities.Core3SkuCompetitorProfilePair],
        snapshots: Sequence[entities.Core3CompetitorProfileSkuSnapshot],
    ) -> tuple[VersionSkuAnalysisSnapshot, list[VersionSkuAnalysisSnapshot]]:
        parsed: dict[str, VersionSkuAnalysisSnapshot] = {}
        for row in snapshots:
            if (
                row.project_id != version.project_id
                or row.category_code != version.category_code
                or row.release_scope_key != version.release_scope_key
            ):
                raise CompetitorProfileV11IntegrityError(
                    "V1.1 snapshot crosses version scope"
                )
            snapshot = VersionSkuAnalysisSnapshot.model_validate(row.snapshot_json)
            if (
                snapshot.snapshot_ref in parsed
                or snapshot.competitor_profile_version_id
                != version.competitor_profile_version_id
                or snapshot.identity_market.sku_code != row.sku_code
                or snapshot.result_hash != row.result_hash
            ):
                raise CompetitorProfileV11IntegrityError(
                    "V1.1 snapshot row is inconsistent"
                )
            parsed[snapshot.snapshot_ref] = snapshot
        target_refs = {row.target_snapshot_ref for row in pairs}
        if pairs:
            if len(target_refs) != 1 or None in target_refs:
                raise CompetitorProfileV11IntegrityError(
                    "V1.1 pairs do not share one target snapshot"
                )
            target = parsed.get(next(iter(target_refs)))
        else:
            target_matches = [
                snapshot
                for snapshot in parsed.values()
                if snapshot.identity_market.sku_code == profile.target_sku_code
            ]
            target = target_matches[0] if len(target_matches) == 1 else None
        if target is None or target.identity_market.sku_code != profile.target_sku_code:
            raise CompetitorProfileV11IntegrityError(
                "V1.1 target snapshot ref is dangling"
            )
        candidates = []
        for pair in pairs:
            snapshot = parsed.get(pair.candidate_snapshot_ref)
            if (
                snapshot is None
                or snapshot.identity_market.sku_code != pair.candidate_sku_code
            ):
                raise CompetitorProfileV11IntegrityError(
                    f"V1.1 candidate snapshot ref is dangling: {pair.candidate_sku_code}"
                )
            candidates.append(snapshot)
        return target, sorted(candidates, key=lambda row: row.identity_market.sku_code)

    @staticmethod
    def _assert_relation_indices(
        pairs: Sequence[PairAnalysisSnapshot],
        rows: Sequence[entities.Core3SkuCompetitorProfileRelation],
    ) -> None:
        expected = {
            (
                pair.candidate_sku_code,
                _enum_value(relation.relation_code),
            ): relation.result_hash
            for pair in pairs
            for relation in pair.relation_assessments
        }
        actual = {
            (row.candidate_sku_code, row.relation_code): row.result_hash for row in rows
        }
        if expected != actual:
            raise CompetitorProfileV11IntegrityError(
                "V1.1 relation index differs from saved pair analyses"
            )

    @staticmethod
    def _assert_dto_snapshot_refs(
        dto: CompetitorProfileAnalysisDTO,
        saved_refs: dict[str, str],
    ) -> None:
        expected = [dto.target_snapshot, *dto.candidate_snapshots]
        for snapshot in expected:
            saved_ref = saved_refs.get(snapshot.identity_market.sku_code)
            if saved_ref is None:
                raise CompetitorProfileV11IntegrityError(
                    "required V1.1 snapshot is missing"
                )
            if saved_ref != snapshot.snapshot_ref:
                raise CompetitorProfileV11IntegrityError(
                    "V1.1 snapshot ref does not resolve in the same version"
                )

    def _assert_existing_materialized_graph(
        self,
        existing: entities.Core3SkuCompetitorProfile,
        dto: CompetitorProfileAnalysisDTO,
    ) -> None:
        """Verify idempotency through immutable graph hashes, without full readback."""

        if (
            existing.input_fingerprint != dto.generation_receipt.input_fingerprint
            or existing.result_hash != dto.profile_result_hash
            or existing.analysis_result_hash != dto.profile_result_hash
        ):
            raise CompetitorProfileImmutableError(
                "existing V1.1 draft has different immutable profile hashes"
            )

        pair_model = entities.Core3SkuCompetitorProfilePair
        relation_model = entities.Core3SkuCompetitorProfileRelation
        selection_model = entities.Core3SkuCompetitorProfileSelection
        snapshot_model = entities.Core3CompetitorProfileSkuSnapshot
        profile_id = existing.sku_competitor_profile_id
        actual_pairs = dict(
            self.db.execute(
                select(pair_model.candidate_sku_code, pair_model.result_hash).where(
                    pair_model.sku_competitor_profile_id == profile_id
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
                .where(
                    relation_model.competitor_profile_version_id
                    == dto.profile_version.competitor_profile_version_id
                )
                .where(
                    relation_model.target_sku_code == dto.sku_summary.target_sku_code
                )
            ).all()
        }
        actual_selections = dict(
            self.db.execute(
                select(
                    selection_model.candidate_sku_code,
                    selection_model.result_hash,
                ).where(selection_model.sku_competitor_profile_id == profile_id)
            ).all()
        )
        snapshots = [dto.target_snapshot, *dto.candidate_snapshots]
        snapshot_codes = [row.identity_market.sku_code for row in snapshots]
        actual_snapshots = {
            row.sku_code: (
                row.input_fingerprint,
                row.result_hash,
                row.snapshot_ref,
            )
            for row in self.db.execute(
                select(
                    snapshot_model.sku_code,
                    snapshot_model.input_fingerprint,
                    snapshot_model.result_hash,
                    snapshot_model.snapshot_json["snapshot_ref"]
                    .as_string()
                    .label("snapshot_ref"),
                )
                .where(
                    snapshot_model.competitor_profile_version_id
                    == dto.profile_version.competitor_profile_version_id
                )
                .where(snapshot_model.sku_code.in_(snapshot_codes))
            ).mappings()
        }
        expected_pairs = {
            row.candidate_sku_code: row.result_hash for row in dto.pair_analyses
        }
        expected_relations = {
            (
                row.candidate_sku_code,
                _enum_value(relation.relation_code),
            ): relation.result_hash
            for row in dto.pair_analyses
            for relation in row.relation_assessments
        }
        expected_selections = {
            row.candidate_sku_code: row.result_hash for row in dto.priority_selections
        }
        expected_snapshots = {
            row.identity_market.sku_code: (
                row.input_fingerprint,
                row.result_hash,
                row.snapshot_ref,
            )
            for row in snapshots
        }
        if (
            actual_pairs != expected_pairs
            or actual_relations != expected_relations
            or actual_selections != expected_selections
            or actual_snapshots != expected_snapshots
        ):
            raise CompetitorProfileImmutableError(
                "existing V1.1 draft child hashes differ from materialized analysis"
            )

    @staticmethod
    def _assert_v11_version(version: entities.Core3CompetitorProfileVersion) -> None:
        if version.schema_version != COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION:
            raise CompetitorProfileNotFoundError(
                "requested version is not a competitor profile V1.1 version"
            )

    def _assert_v11_draft_version(
        self,
        version: entities.Core3CompetitorProfileVersion,
        dto: CompetitorProfileAnalysisDTO,
    ) -> None:
        self._assert_v11_version(version)
        self._assert_draft_version(version)
        self._assert_analysis_context(version, dto.profile_version)

    @staticmethod
    def _assert_analysis_context(
        version: entities.Core3CompetitorProfileVersion,
        context: Any,
    ) -> None:
        for field in (
            "competitor_profile_version_id",
            "project_id",
            "category_code",
            "release_scope_key",
        ):
            if getattr(context, field) != getattr(version, field):
                raise ValueError(f"V1.1 DTO {field} must match its version")
        if (
            context.product_category != version.product_category
            or context.rule_version != version.rule_version
            or context.method_version != version.method_version
        ):
            raise ValueError("V1.1 DTO method/category scope must match its version")
        serving_scope = dict(version.serving_scope_json or {})
        if (
            list(context.source_batch_ids) != list(version.source_batch_ids_json or [])
            or _json(context.market_window) != serving_scope.get("market_window")
            or _json(context.analysis_population)
            != serving_scope.get("analysis_population")
        ):
            raise ValueError(
                "V1.1 DTO source batches, market window, and population must match its version"
            )

    def _find_v11_profile(
        self,
        *,
        version_id: str,
        target_sku_code: str,
    ) -> entities.Core3SkuCompetitorProfile | None:
        model = entities.Core3SkuCompetitorProfile
        return (
            self.db.execute(
                select(model)
                .where(model.project_id == self.project_id)
                .where(model.category_code == self.category_code.value)
                .where(model.competitor_profile_version_id == version_id)
                .where(model.target_sku_code == target_sku_code)
                .where(model.schema_version == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION)
            )
            .scalars()
            .first()
        )


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


def _analysis_state(counts: dict[str, int]) -> str:
    unknown = counts.get("unknown", 0) + counts.get("conflict", 0)
    available = counts.get("available", 0) + counts.get("partial", 0)
    if unknown == 0:
        return "ready"
    return "partial" if available else "blocked"


def _confidence_level(strength: ConclusionStrength) -> str:
    return {
        "strong": "high",
        "supported": "high",
        "directional": "medium",
        "reference": "low",
        "unknown": "unknown",
    }[_enum_value(strength)]


def _primary_relation(pair: PairAnalysisSnapshot) -> RelationAssessment | None:
    formal = [
        row
        for row in pair.relation_assessments
        if _enum_value(row.status) in {"passed", "limited"}
    ]
    return formal[0] if formal else None


def _question(
    pair: PairAnalysisSnapshot,
    question_code: QuestionCode,
) -> Any | None:
    return next(
        (
            row
            for row in pair.business_questions
            if _enum_value(row.question_code) == _enum_value(question_code)
        ),
        None,
    )


def _enum_value(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def _validated_selection_payload(
    row: entities.Core3SkuCompetitorProfileSelection,
) -> dict[str, Any]:
    payload = dict(row.selection_payload_json or {})
    if (
        payload.get("candidate_sku_code") != row.candidate_sku_code
        or payload.get("selection_rank") != row.selection_rank
        or payload.get("result_hash") != row.result_hash
    ):
        raise CompetitorProfileV11IntegrityError(
            "V1.1 selection index differs from its saved typed payload"
        )
    return payload


def _validated_pair_payload(
    row: entities.Core3SkuCompetitorProfilePair,
) -> dict[str, Any]:
    payload = dict(row.analysis_snapshot_json or {})
    if (
        payload.get("candidate_sku_code") != row.candidate_sku_code
        or payload.get("target_sku_code") != row.target_sku_code
        or payload.get("result_hash") != row.result_hash
        or payload.get("result_hash") != row.analysis_result_hash
        or payload.get("target_snapshot_ref") != row.target_snapshot_ref
        or payload.get("candidate_snapshot_ref") != row.candidate_snapshot_ref
    ):
        raise CompetitorProfileV11IntegrityError(
            "V1.1 pair index differs from its saved typed payload"
        )
    return payload


def _assert_compact_selection(
    payload: dict[str, Any],
    row: entities.Core3SkuCompetitorProfileSelection,
    pair_header: Any,
    index_item: dict[str, Any],
) -> None:
    score_breakdown = dict(row.selection_score_breakdown_json or {})
    role_codes = list(payload.get("role_codes") or [])
    try:
        ranking_score_raw = score_breakdown.get("ranking_score")
        expected_pair_score = (
            None if ranking_score_raw is None else Decimal(str(ranking_score_raw))
        )
        expected_selection_score = expected_pair_score or Decimal("0")
        inconsistent = (
            payload.get("pair_result_hash") != pair_header.analysis_result_hash
            or Decimal(str(payload.get("selection_score"))) != row.selection_score
            or row.selection_score != expected_selection_score
            or pair_header.analysis_score != expected_pair_score
            or Decimal(str(payload.get("selection_available_weight")))
            != row.selection_available_weight
            or row.selection_available_weight != pair_header.analysis_available_weight
            or payload.get("selection_conclusion_strength")
            != row.selection_conclusion_strength
            or row.selection_conclusion_strength
            != pair_header.selection_conclusion_strength
            or role_codes != list(row.selection_role_codes_json or [])
            or payload.get("primary_role") != index_item.get("primary_role")
            or index_item.get("selected_rank") != row.selection_rank
            or Decimal(str(score_breakdown.get("available_weight")))
            != row.selection_available_weight
        )
    except (InvalidOperation, TypeError, ValueError):
        inconsistent = True
    if inconsistent:
        raise CompetitorProfileV11IntegrityError(
            "compact selection differs from its saved pair score, role, or question"
        )


def _compact_integrity_hash(
    *,
    profile_version: dict[str, Any],
    generation_receipt: dict[str, Any],
    sku_summary: dict[str, Any],
    priority_selections: list[dict[str, Any]],
    full_pair_index: list[dict[str, Any]],
    profile_result_hash: str,
) -> str:
    """Bind every compact projection field to the fully validated write DTO."""

    return stable_hash_json(
        {
            "profile_version": profile_version,
            "generation_receipt": generation_receipt,
            "sku_summary": sku_summary,
            "priority_selections": priority_selections,
            "full_pair_index": full_pair_index,
            "profile_result_hash": profile_result_hash,
        }
    )


__all__ = [
    "CompetitorProfileV11IntegrityError",
    "CompetitorProfileV11Repository",
    "ReadMode",
]
