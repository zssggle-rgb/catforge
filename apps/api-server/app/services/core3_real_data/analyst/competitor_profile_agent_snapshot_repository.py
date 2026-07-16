"""Persistence/readback for an already-calculated competitor-agent snapshot."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_METHOD_VERSION,
    AGENT_SNAPSHOT_RULE_VERSION,
    AgentCompetitorProfileCompact,
    AgentCompetitorProfileReadResult,
    AgentCompetitorProfileSnapshot,
    AgentPairIndexItem,
    AgentSkuSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileDraftWriteNotAllowedError,
    CompetitorProfileImmutableError,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11IntegrityError,
    CompetitorProfileV11Repository,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
)


_ROLE_TO_RELATION = {
    "primary_direct": "direct_substitute",
    "strong_direct": "direct_substitute",
    "downtrade_diversion": "downtrade_diversion",
    "uptrade_alternative": "uptrade_alternative",
    "price_adjacent": "same_budget_alternative",
    "scenario_alternative": "scenario_substitute",
}

_SAVED_ANALYSIS_DIMENSIONS = (
    "purchase_pool",
    "semantic_overlap",
    "parameter_claim_overlap",
    "purchase_reason_substitution",
    "price_volume_pressure",
    "relation_role",
    "priority_selection",
)


class CompetitorProfileAgentSnapshotRepository(CompetitorProfileV11Repository):
    """Reuse the V1.1 tables without recreating the live agent analysis."""

    def write_agent_snapshot_draft(
        self,
        *,
        profile: AgentCompetitorProfileSnapshot,
        sku_snapshots: Sequence[AgentSkuSnapshot],
    ) -> bool:
        profile = AgentCompetitorProfileSnapshot.model_validate(
            profile.model_dump(mode="json")
        )
        snapshots = [
            AgentSkuSnapshot.model_validate(row.model_dump(mode="json"))
            for row in sku_snapshots
        ]
        self._assert_context_scope(profile.project_id, profile.category_code)
        version = self._version_by_id(
            profile.competitor_profile_version_id,
            for_update=True,
        )
        self._assert_agent_version(version, profile=profile)
        existing = self._find_v11_profile(
            version_id=profile.competitor_profile_version_id,
            target_sku_code=profile.target.sku_code,
        )
        if existing is not None:
            saved = self._read_agent_profile_row(existing)
            if saved != profile:
                raise CompetitorProfileImmutableError(
                    "agent-aligned competitor draft already exists with different analysis"
                )
            return False

        snapshot_by_code = {row.identity.sku_code: row for row in snapshots}
        expected_codes = {
            profile.target.sku_code,
            *(row.candidate_sku_code for row in profile.candidates),
        }
        if set(snapshot_by_code) != expected_codes:
            raise ValueError(
                "agent snapshot set must cover target and saved candidates"
            )
        for row in snapshots:
            if (
                row.competitor_profile_version_id
                != profile.competitor_profile_version_id
                or row.release_scope_key != profile.release_scope_key
                or row.project_id != profile.project_id
                or row.category_code != profile.category_code
            ):
                raise ValueError("agent SKU snapshot scope must match profile")

        try:
            with self.db.begin_nested():
                self._write_agent_sku_snapshots(version, snapshots)
                profile_row = self._insert_agent_profile(version, profile)
                pair_ids = self._insert_agent_pairs(version, profile_row, profile)
                self._insert_agent_selections(
                    version,
                    profile_row,
                    pair_ids,
                    profile,
                )
                self.db.flush()
        except IntegrityError:
            concurrent = self._find_v11_profile(
                version_id=profile.competitor_profile_version_id,
                target_sku_code=profile.target.sku_code,
            )
            if (
                concurrent is None
                or self._read_agent_profile_row(concurrent) != profile
            ):
                raise
            return False
        return True

    def read_agent_snapshot(
        self,
        *,
        target_sku_code: str,
        read_mode: Literal["full", "compact"],
        access_mode: Literal["formal", "preview"],
        competitor_profile_version_id: str | None = None,
        release_scope_key: str | None = None,
    ) -> AgentCompetitorProfileReadResult:
        version = self._resolve_agent_version(
            target_sku_code=target_sku_code,
            access_mode=access_mode,
            competitor_profile_version_id=competitor_profile_version_id,
            release_scope_key=release_scope_key,
        )
        if version is None:
            return AgentCompetitorProfileReadResult(
                status="profile_unavailable",
                read_mode=read_mode,
                preview=access_mode == "preview",
            )
        if read_mode == "compact":
            compact = self._read_agent_compact_by_version(
                competitor_profile_version_id=version.competitor_profile_version_id,
                target_sku_code=target_sku_code,
            )
            if compact is None:
                return AgentCompetitorProfileReadResult(
                    status="profile_unavailable",
                    read_mode="compact",
                    preview=access_mode == "preview",
                )
            return AgentCompetitorProfileReadResult(
                status="available",
                read_mode="compact",
                preview=access_mode == "preview",
                competitor_profile_version_id=version.competitor_profile_version_id,
                compact=compact,
            )
        profile_row = self._find_v11_profile(
            version_id=version.competitor_profile_version_id,
            target_sku_code=target_sku_code,
        )
        if profile_row is None:
            return AgentCompetitorProfileReadResult(
                status="profile_unavailable",
                read_mode=read_mode,
                preview=access_mode == "preview",
            )
        full = self._read_agent_profile_row(profile_row)
        self._verify_pair_index(profile_row, full)
        sku_snapshots = self._read_agent_sku_snapshots(full)
        return AgentCompetitorProfileReadResult(
            status="available",
            read_mode="full",
            preview=access_mode == "preview",
            competitor_profile_version_id=version.competitor_profile_version_id,
            full=full,
            sku_snapshots=sku_snapshots,
        )

    def _resolve_agent_version(
        self,
        *,
        target_sku_code: str,
        access_mode: Literal["formal", "preview"],
        competitor_profile_version_id: str | None,
        release_scope_key: str | None,
    ) -> entities.Core3CompetitorProfileVersion | None:
        version_model = entities.Core3CompetitorProfileVersion
        profile_model = entities.Core3SkuCompetitorProfile
        if access_mode == "preview":
            if not competitor_profile_version_id or not release_scope_key:
                raise ValueError(
                    "agent snapshot preview requires explicit version and release scope"
                )
            version = self._version_by_id(competitor_profile_version_id)
            if version.release_scope_key != release_scope_key:
                raise ValueError("preview version does not belong to requested scope")
            if (
                version.schema_version != COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                or version.method_version != AGENT_SNAPSHOT_METHOD_VERSION
                or version.rule_version != AGENT_SNAPSHOT_RULE_VERSION
            ):
                return None
            if version.release_status == "published" and version.is_current:
                return version
            if version.release_status != "draft" or version.is_current:
                raise CompetitorProfileDraftWriteNotAllowedError(
                    "agent snapshot preview only accepts a non-current draft"
                )
            return version
        if competitor_profile_version_id is not None:
            raise ValueError("formal agent snapshot reads cannot select a version")
        stmt = (
            select(version_model)
            .join(
                profile_model,
                profile_model.competitor_profile_version_id
                == version_model.competitor_profile_version_id,
            )
            .where(version_model.project_id == self.project_id)
            .where(version_model.category_code == self.category_code.value)
            .where(
                version_model.schema_version == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
            )
            .where(version_model.method_version == AGENT_SNAPSHOT_METHOD_VERSION)
            .where(version_model.rule_version == AGENT_SNAPSHOT_RULE_VERSION)
            .where(version_model.release_status == "published")
            .where(version_model.is_current.is_(True))
            .where(profile_model.target_sku_code == target_sku_code)
        )
        if release_scope_key is not None:
            stmt = stmt.where(version_model.release_scope_key == release_scope_key)
        return (
            self.db.execute(stmt.order_by(version_model.generated_at.desc()).limit(1))
            .scalars()
            .first()
        )

    def _assert_agent_version(
        self,
        version: entities.Core3CompetitorProfileVersion,
        *,
        profile: AgentCompetitorProfileSnapshot | None = None,
    ) -> None:
        if (
            version.schema_version != COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
            or version.method_version != AGENT_SNAPSHOT_METHOD_VERSION
            or version.rule_version != AGENT_SNAPSHOT_RULE_VERSION
        ):
            raise ValueError("version is not an agent-aligned competitor snapshot")
        if profile is None:
            return
        if version.release_status != "draft" or version.is_current:
            raise CompetitorProfileDraftWriteNotAllowedError(
                "agent snapshot writes require a non-current draft"
            )
        if (
            version.project_id != profile.project_id
            or version.category_code != profile.category_code
            or version.release_scope_key != profile.release_scope_key
            or version.profile_version != profile.profile_version
            or version.storage_batch_id != profile.storage_batch_id
        ):
            raise ValueError("agent snapshot profile does not match version scope")

    def _write_agent_sku_snapshots(
        self,
        version: entities.Core3CompetitorProfileVersion,
        snapshots: Sequence[AgentSkuSnapshot],
    ) -> None:
        model = entities.Core3CompetitorProfileSkuSnapshot
        for snapshot in snapshots:
            existing = (
                self.db.execute(
                    select(model)
                    .where(
                        model.competitor_profile_version_id
                        == version.competitor_profile_version_id
                    )
                    .where(model.sku_code == snapshot.identity.sku_code)
                )
                .scalars()
                .first()
            )
            if existing is not None:
                if (
                    existing.result_hash != snapshot.result_hash
                    or existing.snapshot_json != snapshot.model_dump(mode="json")
                ):
                    raise CompetitorProfileImmutableError(
                        f"shared agent snapshot differs for {snapshot.identity.sku_code}"
                    )
                continue
            self.db.add(
                model(
                    competitor_profile_sku_snapshot_id=snapshot.snapshot_ref,
                    competitor_profile_version_id=version.competitor_profile_version_id,
                    project_id=version.project_id,
                    category_code=version.category_code,
                    release_scope_key=version.release_scope_key,
                    sku_code=snapshot.identity.sku_code,
                    profile_version=version.profile_version,
                    schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
                    rule_version=AGENT_SNAPSHOT_RULE_VERSION,
                    method_version=AGENT_SNAPSHOT_METHOD_VERSION,
                    snapshot_json=snapshot.model_dump(mode="json"),
                    module_availability_json=snapshot.available_modules,
                    evidence_refs_json=_json([row.raw for row in snapshot.evidence]),
                    source_lineage_json={
                        "source_analysis_version": "competitor_set_legacy_analysis_v1",
                        "source_batch_ids": list(version.source_batch_ids_json or []),
                    },
                    limitations_json=snapshot.limitations,
                    input_fingerprint=snapshot.input_fingerprint,
                    result_hash=snapshot.result_hash,
                )
            )

    def _insert_agent_profile(
        self,
        version: entities.Core3CompetitorProfileVersion,
        profile: AgentCompetitorProfileSnapshot,
    ) -> entities.Core3SkuCompetitorProfile:
        roles = Counter(row.analysis.role for row in profile.candidates)
        eligibility = Counter(
            "eligible" if row.analysis.top3_eligible else "limited"
            for row in profile.candidates
        )
        review_count = sum(
            bool((row.analysis.m12d_consumption or {}).get("requires_review"))
            for row in profile.candidates
        )
        confidence = _profile_confidence(profile)
        has_candidates = bool(profile.candidates)
        display_name = (
            " ".join(
                value
                for value in (profile.target.brand_name, profile.target.model_name)
                if value
            )
            or profile.target.sku_code
        )
        row = entities.Core3SkuCompetitorProfile(
            competitor_profile_version_id=version.competitor_profile_version_id,
            project_id=version.project_id,
            category_code=version.category_code,
            product_category=version.product_category,
            storage_batch_id=version.storage_batch_id,
            release_scope_key=version.release_scope_key,
            profile_version=version.profile_version,
            schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
            rule_version=AGENT_SNAPSHOT_RULE_VERSION,
            method_version=AGENT_SNAPSHOT_METHOD_VERSION,
            target_sku_code=profile.target.sku_code,
            display_name_cn=display_name,
            analysis_state="partial" if profile.limitations else "ready",
            conclusion_state=(
                "available" if has_candidates else "no_priority_competitor"
            ),
            freshness_status="current",
            profile_confidence=confidence,
            candidate_status_counts_json=dict(sorted(eligibility.items())),
            relation_status_counts_json=dict(sorted(roles.items())),
            competitive_advantages_json=[],
            substitutable_values_json=[],
            price_scale_pressure_json=[],
            same_brand_findings_json=[],
            configuration_decisions_json=[],
            no_conclusion_reason_json=(
                {}
                if has_candidates
                else {
                    "reason_code": "no_market_candidates",
                    "reason_cn": "现有竞品分析智能体未找到符合购买池的候选。",
                }
            ),
            source_lineage_json=_json([row.raw for row in profile.evidence]),
            qa_index_json=[
                {"selection_rank": rank, "candidate_sku_code": sku_code}
                for rank, sku_code in enumerate(profile.priority_order, start=1)
            ],
            evidence_refs_json=_json([row.raw for row in profile.evidence]),
            limitations_json=profile.limitations,
            profile_payload_json=profile.model_dump(mode="json"),
            analysis_summary_json={
                "candidate_count": len(profile.candidates),
                "candidate_pool_order": profile.candidate_pool_order,
                "analysis_order": profile.analysis_order,
                "priority_order": profile.priority_order,
                "source_analysis_result_hash": profile.source_analysis_result_hash,
                "profile_result_hash": profile.result_hash,
            },
            analysis_fact_index_json={
                row.candidate_sku_code: row.result_hash for row in profile.candidates
            },
            analysis_evidence_index_json={
                "receipt_count": len(profile.evidence),
                "source_modules": sorted(
                    {row.source_module for row in profile.evidence}
                ),
            },
            analysis_result_hash=profile.result_hash,
            analysis_candidate_count=len(profile.candidates),
            analysis_available_dimension_count=(
                len(_SAVED_ANALYSIS_DIMENSIONS) if has_candidates else 0
            ),
            analysis_review_item_count=review_count,
            release_status="draft",
            is_current=False,
            input_fingerprint=profile.input_fingerprint,
            result_hash=profile.result_hash,
            processing_status="success",
            review_required=review_count > 0,
            review_status="review_required" if review_count else "auto_pass",
            review_reasons_json=(
                ["saved_agent_source_requires_review"] if review_count else []
            ),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _insert_agent_pairs(
        self,
        version: entities.Core3CompetitorProfileVersion,
        profile_row: entities.Core3SkuCompetitorProfile,
        profile: AgentCompetitorProfileSnapshot,
    ) -> dict[str, str]:
        model = entities.Core3SkuCompetitorProfilePair
        pair_ids: dict[str, str] = {}
        for record in profile.candidates:
            analysis = record.analysis
            selected = record.selected_rank is not None
            relation = _ROLE_TO_RELATION.get(analysis.role, "same_value_substitute")
            confidence = _candidate_confidence(analysis.model_dump(mode="python"))
            confidence_level = _confidence_level(confidence)
            status = "eligible" if analysis.top3_eligible else "limited"
            review_required = bool(
                (analysis.m12d_consumption or {}).get("requires_review")
            )
            pair_row = model(
                sku_competitor_profile_id=profile_row.sku_competitor_profile_id,
                competitor_profile_version_id=version.competitor_profile_version_id,
                project_id=version.project_id,
                category_code=version.category_code,
                product_category=version.product_category,
                storage_batch_id=version.storage_batch_id,
                release_scope_key=version.release_scope_key,
                profile_version=version.profile_version,
                schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
                rule_version=AGENT_SNAPSHOT_RULE_VERSION,
                method_version=AGENT_SNAPSHOT_METHOD_VERSION,
                target_sku_code=profile.target.sku_code,
                candidate_sku_code=record.candidate_sku_code,
                candidate_identity_json=analysis.candidate.model_dump(mode="json"),
                recall_sources_json=["same_size_price_pool"],
                recall_facts_json={
                    "source_rank": record.source_rank,
                    "candidate_pool_policy": profile.candidate_pool_policy,
                },
                competitor_member=True,
                reference_member=False,
                candidate_status=status,
                scope_status="analyzable",
                exclusion_reason_code=None,
                target_snapshot_ref=profile.target_snapshot_ref,
                candidate_snapshot_ref=record.candidate_snapshot_ref,
                purchase_pool_level=_purchase_pool_level(analysis.purchase_pool),
                purchase_pool_json=_json(analysis.purchase_pool),
                evidence_family_json=_saved_evidence_families(
                    analysis.model_dump(mode="python")
                ),
                market_comparison_json=_json(analysis.market_validation),
                question_eligibility_json=[
                    "key_competitor_selection",
                    "purchase_choice",
                    "price_volume_pressure",
                    "value_substitution",
                ],
                reference_purposes_json=[],
                primary_relation_code=relation,
                relation_codes_json=[relation],
                selected=selected,
                non_selection_reason_code=None if selected else "saved_outside_top3",
                non_selection_reason_cn=(
                    None
                    if selected
                    else analysis.exclusion_reason_cn
                    or "未进入已保存的重点竞品 Top 3。"
                ),
                confidence_level=confidence_level,
                confidence=confidence,
                evidence_refs_json=_json([row.raw for row in record.evidence]),
                limitations_json=[],
                risk_flags_json=(["source_requires_review"] if review_required else []),
                pair_payload_json=_json(
                    {
                        "source_rank": record.source_rank,
                        "selected_rank": record.selected_rank,
                        "role": analysis.role,
                        "role_cn": analysis.role_cn,
                        "business_score": analysis.business_score,
                        "result_hash": record.result_hash,
                    }
                ),
                analysis_snapshot_json={
                    "storage_mode": "agent_profile_candidate_ref",
                    "profile_result_hash": profile.result_hash,
                    "candidate_sku_code": record.candidate_sku_code,
                    "candidate_result_hash": record.result_hash,
                    "candidate_snapshot_result_hash": (
                        record.candidate_snapshot_result_hash
                    ),
                },
                analysis_conclusion_strength="supported" if selected else "directional",
                analysis_score=analysis.business_score,
                analysis_available_weight=Decimal("1"),
                analysis_result_hash=record.result_hash,
                analysis_review_required=review_required,
                selection_question_code=(
                    "key_competitor_selection" if selected else None
                ),
                selection_conclusion_strength="supported" if selected else None,
                release_status="draft",
                is_current=False,
                input_fingerprint=record.input_fingerprint,
                result_hash=record.result_hash,
                processing_status="success",
                review_required=review_required,
                review_status="review_required" if review_required else "auto_pass",
                review_reasons_json=(
                    ["saved_agent_source_requires_review"] if review_required else []
                ),
            )
            self.db.add(pair_row)
            self.db.flush()
            pair_ids[record.candidate_sku_code] = (
                pair_row.sku_competitor_profile_pair_id
            )
        return pair_ids

    def _insert_agent_selections(
        self,
        version: entities.Core3CompetitorProfileVersion,
        profile_row: entities.Core3SkuCompetitorProfile,
        pair_ids: dict[str, str],
        profile: AgentCompetitorProfileSnapshot,
    ) -> None:
        by_code = {row.candidate_sku_code: row for row in profile.candidates}
        model = entities.Core3SkuCompetitorProfileSelection
        for rank, candidate_sku_code in enumerate(profile.priority_order, start=1):
            record = by_code[candidate_sku_code]
            analysis = record.analysis
            relation = _ROLE_TO_RELATION.get(analysis.role, "same_value_substitute")
            confidence = _candidate_confidence(analysis.model_dump(mode="python"))
            review_required = bool(
                (analysis.m12d_consumption or {}).get("requires_review")
            )
            reason_parts = [
                str(item)
                for item in (analysis.ranking_gate_reasons or [])
                if str(item).strip()
            ]
            selection_reason = (
                "、".join(reason_parts)
                or f"现有竞品分析结果将其列为第 {rank} 位重点竞品。"
            )
            independent_reason = (
                str((analysis.replacement_pressure or {}).get("reason_cn") or "")
                or "该候选提供了独立的购买替代参照。"
            )
            row = model(
                sku_competitor_profile_id=profile_row.sku_competitor_profile_id,
                sku_competitor_profile_pair_id=pair_ids[candidate_sku_code],
                competitor_profile_version_id=version.competitor_profile_version_id,
                project_id=version.project_id,
                category_code=version.category_code,
                product_category=version.product_category,
                storage_batch_id=version.storage_batch_id,
                release_scope_key=version.release_scope_key,
                profile_version=version.profile_version,
                schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
                rule_version=AGENT_SNAPSHOT_RULE_VERSION,
                method_version=AGENT_SNAPSHOT_METHOD_VERSION,
                target_sku_code=profile.target.sku_code,
                candidate_sku_code=candidate_sku_code,
                selection_rank=rank,
                primary_decision_topic="purchase_choice",
                covered_decision_topics_json=[
                    "purchase_choice",
                    "price_scale_pressure",
                    "value_route",
                ],
                primary_relation_code=relation,
                auxiliary_relation_codes_json=[],
                selection_reason_cn=selection_reason,
                independent_information_reason_cn=independent_reason,
                price_value_pressure_summary_json=_json(
                    {
                        "purchase_pressure_comparison": analysis.purchase_pressure_comparison,
                        "market_validation": analysis.market_validation,
                    }
                ),
                confidence_level=_confidence_level(confidence),
                evidence_refs_json=_json([row.raw for row in record.evidence]),
                selection_payload_json=_json(
                    {
                        "saved_selected_rank": rank,
                        "source_rank": record.source_rank,
                        "role": analysis.role,
                        "ranking_trace": analysis.ranking_trace,
                        "selection_gate": analysis.selection_gate,
                    }
                ),
                selection_policy_version=AGENT_SNAPSHOT_METHOD_VERSION,
                selection_score=analysis.business_score,
                selection_available_weight=Decimal("1"),
                selection_conclusion_strength="supported",
                selection_role_codes_json=[analysis.role],
                selection_score_breakdown_json=_json(
                    {
                        "business_score": analysis.business_score,
                        "purchase_pool": analysis.purchase_pool,
                        "weighted_overlap": analysis.weighted_overlap,
                        "replacement_pressure": analysis.replacement_pressure,
                        "market_validation": analysis.market_validation,
                    }
                ),
                release_status="draft",
                is_current=False,
                input_fingerprint=record.input_fingerprint,
                result_hash=record.result_hash,
                processing_status="success",
                review_required=review_required,
                review_status=("review_required" if review_required else "auto_pass"),
                review_reasons_json=(
                    ["saved_agent_source_requires_review"] if review_required else []
                ),
            )
            self.db.add(row)

    def _read_agent_profile_row(
        self,
        row: entities.Core3SkuCompetitorProfile,
    ) -> AgentCompetitorProfileSnapshot:
        profile = AgentCompetitorProfileSnapshot.model_validate(
            row.profile_payload_json
        )
        if (
            profile.result_hash != row.result_hash
            or profile.result_hash != row.analysis_result_hash
            or profile.target.sku_code != row.target_sku_code
            or profile.competitor_profile_version_id
            != row.competitor_profile_version_id
        ):
            raise CompetitorProfileV11IntegrityError(
                "saved agent profile root differs from typed payload"
            )
        return profile

    def _read_agent_sku_snapshots(
        self,
        profile: AgentCompetitorProfileSnapshot,
    ) -> list[AgentSkuSnapshot]:
        model = entities.Core3CompetitorProfileSkuSnapshot
        expected_codes = {
            profile.target.sku_code,
            *(row.candidate_sku_code for row in profile.candidates),
        }
        rows = list(
            self.db.execute(
                select(model)
                .where(
                    model.competitor_profile_version_id
                    == profile.competitor_profile_version_id
                )
                .where(model.sku_code.in_(sorted(expected_codes)))
                .where(model.method_version == AGENT_SNAPSHOT_METHOD_VERSION)
            ).scalars()
        )
        snapshots = []
        for row in rows:
            snapshot = AgentSkuSnapshot.model_validate(row.snapshot_json)
            if (
                snapshot.identity.sku_code != row.sku_code
                or snapshot.snapshot_ref != row.competitor_profile_sku_snapshot_id
                or snapshot.result_hash != row.result_hash
                or snapshot.competitor_profile_version_id
                != profile.competitor_profile_version_id
            ):
                raise CompetitorProfileV11IntegrityError(
                    "saved agent SKU snapshot differs from its row identity"
                )
            snapshots.append(snapshot)
        if {row.identity.sku_code for row in snapshots} != expected_codes:
            raise CompetitorProfileV11IntegrityError(
                "saved agent profile is missing shared SKU snapshots"
            )
        return snapshots

    def _verify_pair_index(
        self,
        profile_row: entities.Core3SkuCompetitorProfile,
        profile: AgentCompetitorProfileSnapshot,
    ) -> None:
        model = entities.Core3SkuCompetitorProfilePair
        rows = self.db.execute(
            select(
                model.candidate_sku_code,
                model.analysis_result_hash,
                model.selected,
            )
            .where(
                model.sku_competitor_profile_id == profile_row.sku_competitor_profile_id
            )
            .order_by(model.candidate_sku_code)
        ).all()
        expected = sorted(
            (
                record.candidate_sku_code,
                record.result_hash,
                record.selected_rank is not None,
            )
            for record in profile.candidates
        )
        if [tuple(row) for row in rows] != expected:
            raise CompetitorProfileV11IntegrityError(
                "saved agent pair index differs from typed profile"
            )

    def _read_agent_compact_by_version(
        self,
        *,
        competitor_profile_version_id: str,
        target_sku_code: str,
    ) -> AgentCompetitorProfileCompact | None:
        profile_model = entities.Core3SkuCompetitorProfile
        profile_row = self.db.execute(
            select(
                profile_model.sku_competitor_profile_id,
                profile_model.competitor_profile_version_id,
                profile_model.profile_version,
                profile_model.release_scope_key,
                profile_model.target_sku_code,
                profile_model.analysis_candidate_count,
                profile_model.analysis_summary_json,
                profile_model.analysis_result_hash,
            )
            .where(
                profile_model.competitor_profile_version_id
                == competitor_profile_version_id
            )
            .where(profile_model.target_sku_code == target_sku_code)
            .where(profile_model.method_version == AGENT_SNAPSHOT_METHOD_VERSION)
        ).first()
        if profile_row is None:
            return None
        summary = dict(profile_row.analysis_summary_json or {})
        model = entities.Core3SkuCompetitorProfilePair
        rows = self.db.execute(
            select(
                model.candidate_sku_code,
                model.pair_payload_json,
                model.analysis_score,
                model.analysis_result_hash,
            ).where(
                model.sku_competitor_profile_id == profile_row.sku_competitor_profile_id
            )
        ).all()
        index = []
        for candidate_sku_code, payload, score, result_hash in rows:
            metadata = dict(payload or {})
            index.append(
                AgentPairIndexItem(
                    candidate_sku_code=candidate_sku_code,
                    source_rank=int(metadata["source_rank"]),
                    selected_rank=metadata.get("selected_rank"),
                    role=str(metadata["role"]),
                    business_score=score,
                    result_hash=str(result_hash),
                )
            )
        index.sort(key=lambda row: row.source_rank)
        return AgentCompetitorProfileCompact(
            competitor_profile_version_id=profile_row.competitor_profile_version_id,
            profile_version=profile_row.profile_version,
            release_scope_key=profile_row.release_scope_key,
            target_sku_code=profile_row.target_sku_code,
            candidate_count=int(profile_row.analysis_candidate_count or 0),
            priority_order=list(summary.get("priority_order") or []),
            pair_index=index,
            profile_result_hash=str(profile_row.analysis_result_hash),
        )


def _purchase_pool_level(payload: dict[str, Any]) -> str:
    value = str(payload.get("level") or "unknown")
    return value if value in {"P0", "P1", "P2", "P3", "unknown"} else "unknown"


def _candidate_confidence(payload: dict[str, Any]) -> Decimal:
    profiles = [
        payload.get("target_purchase_reason_profile") or {},
        payload.get("candidate_purchase_reason_profile") or {},
    ]
    values = [
        Decimal(str(row["profile_confidence"]))
        for row in profiles
        if row.get("profile_confidence") is not None
    ]
    if not values:
        return Decimal("0")
    value = sum(values, Decimal("0")) / Decimal(len(values))
    return min(Decimal("1"), max(Decimal("0"), value))


def _profile_confidence(profile: AgentCompetitorProfileSnapshot) -> Decimal:
    values = [
        _candidate_confidence(row.analysis.model_dump(mode="python"))
        for row in profile.candidates
    ]
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _confidence_level(value: Decimal) -> str:
    if value >= Decimal("0.8"):
        return "high"
    if value >= Decimal("0.5"):
        return "medium"
    return "low" if value > 0 else "unknown"


def _saved_evidence_families(payload: dict[str, Any]) -> list[str]:
    families = []
    for field_name, family in (
        ("semantic_overlap", "semantic"),
        ("param_claim_overlap", "parameter_claim"),
        ("sales_overlap", "market"),
        ("candidate_purchase_reason_profile", "purchase_reason"),
        ("candidate_claim_value", "claim_value"),
    ):
        if payload.get(field_name):
            families.append(family)
    return families


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


__all__ = ["CompetitorProfileAgentSnapshotRepository"]
