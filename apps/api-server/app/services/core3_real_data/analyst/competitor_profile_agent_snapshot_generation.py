"""Persist the existing competitor agent's completed analysis without re-analysis."""

from __future__ import annotations

import gc
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import func, select, text

from app.models import entities
from app.services.core3_real_data.analyst.analyst_repository import (
    format_serving_scope_batch_id,
)
from app.services.core3_real_data.analyst.analyst_service import CatForgeAnalystService
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_CANDIDATE_LIMIT,
    AGENT_SNAPSHOT_METHOD_VERSION,
    AGENT_SNAPSHOT_PRIORITY_LIMIT,
    AGENT_SNAPSHOT_RULE_VERSION,
    AGENT_SNAPSHOT_SOURCE_VERSION,
    AgentCandidateAnalysisPayload,
    AgentCandidateAnalysisRecord,
    AgentCompetitorProfileSnapshot,
    AgentEvidenceReceipt,
    AgentSkuIdentity,
    AgentSkuSourcePayload,
    AgentSkuSnapshot,
    encode_agent_sku_payload,
)
from app.services.core3_real_data.analyst.competitor_profile_input_provider import (
    CompetitorProfileInputProvider,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileVersionDraftCreate,
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    ServingScope,
    SourceAuthorityRef,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
)
from app.services.core3_real_data.constants import CORE3_M12D_RULE_VERSION
from app.services.core3_real_data.hash_utils import stable_hash


@dataclass(frozen=True)
class AgentSnapshotGenerationResult:
    status: Literal["generated", "reused"]
    version: CompetitorProfileVersionRecord
    profile: AgentCompetitorProfileSnapshot
    candidate_count: int
    selected_sku_codes: tuple[str, ...]


@dataclass(frozen=True)
class AgentSnapshotBatchGenerationResult:
    version: CompetitorProfileVersionRecord
    target_count: int
    generated_count: int
    reused_count: int
    failure_codes: tuple[tuple[str, str], ...]
    last_target_sku_code: str | None


class AgentSnapshotBatchAlreadyRunningError(RuntimeError):
    """Raised when another writer owns the category/scope batch lock."""


AGENT_SNAPSHOT_BATCH_WRITER_LOCK_KEY = (
    f"catforge:{AGENT_SNAPSHOT_METHOD_VERSION}:batch_writer"
)


class CompetitorProfileAgentSnapshotGenerationService:
    """Run ``competitor-set`` once, type it, and save that exact result."""

    def __init__(
        self,
        *,
        repository: CompetitorProfileAgentSnapshotRepository,
        input_provider: CompetitorProfileInputProvider,
    ) -> None:
        self.repository = repository
        self.input_provider = input_provider
        self._prepared_scope: (
            tuple[
                ServingScope,
                entities.Core3PurchaseReasonProfileVersion,
            ]
            | None
        ) = None
        self._agent_runner_cache: (
            tuple[
                str,
                CatForgeAnalystService,
                Any,
            ]
            | None
        ) = None

    def generate_single_draft(
        self,
        *,
        target_sku_code: str,
        profile_version: str,
        generated_by: str,
    ) -> AgentSnapshotGenerationResult:
        target_code = target_sku_code.strip().upper()
        if not target_code:
            raise ValueError("target SKU code is required")
        scope, _authority = self._prepare_scope()
        version = self._ensure_version(
            serving_scope=scope,
            profile_version=profile_version,
            generated_by=generated_by,
        )
        existing = self.repository.read_agent_snapshot(
            target_sku_code=target_code,
            read_mode="full",
            access_mode="preview",
            competitor_profile_version_id=version.competitor_profile_version_id,
            release_scope_key=version.release_scope_key,
        )
        if existing.status == "available":
            if existing.full is None:
                raise RuntimeError(
                    "available agent snapshot is missing its full payload"
                )
            return AgentSnapshotGenerationResult(
                status="reused",
                version=version,
                profile=existing.full,
                candidate_count=len(existing.full.candidates),
                selected_sku_codes=tuple(existing.full.priority_order),
            )
        try:
            source_result = self._run_existing_agent(
                target_sku_code=target_code,
                serving_scope=scope,
                candidate_limit=AGENT_SNAPSHOT_CANDIDATE_LIMIT,
            )
            profile, snapshots = _build_agent_snapshot(
                source_result=source_result,
                version=version,
            )
            created = self.repository.write_agent_snapshot_draft(
                profile=profile,
                sku_snapshots=snapshots,
            )
            self.repository.db.flush()
            version = self._refresh_version_state(version.competitor_profile_version_id)
            self.repository.db.commit()
        except Exception as exc:
            self.repository.db.rollback()
            self._refresh_version_state(
                version.competitor_profile_version_id,
                failure_code=type(exc).__name__,
                failed_target_sku_code=target_code,
            )
            raise
        return AgentSnapshotGenerationResult(
            status="generated" if created else "reused",
            version=version,
            profile=profile,
            candidate_count=len(profile.candidates),
            selected_sku_codes=tuple(profile.priority_order),
        )

    def generate_batch_draft(
        self,
        *,
        profile_version: str,
        generated_by: str,
        checkpoint_every: int = 10,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> AgentSnapshotBatchGenerationResult:
        """Persist one full authoritative category scope with DB-backed resume.

        A long-lived service prepares the category scope and legacy analyst once.
        Each target still runs the existing competitor agent exactly once unless
        its immutable draft already exists, in which case resume reuses it.
        """

        if checkpoint_every < 1:
            raise ValueError("checkpoint_every must be at least 1")
        normalized_version = profile_version.strip()
        if not normalized_version:
            raise ValueError("profile version is required")
        scope, authority = self._prepare_scope()
        target_codes = self._authoritative_target_codes(authority)
        with self._batch_writer_lock():
            version = self._ensure_version(
                serving_scope=scope,
                profile_version=normalized_version,
                generated_by=generated_by,
            )
            existing = self._existing_profile_index(
                version.competitor_profile_version_id
            )
            unexpected = sorted(set(existing).difference(target_codes))
            if unexpected:
                raise ValueError(
                    "agent snapshot version contains targets outside the authority manifest: "
                    + ",".join(unexpected[:10])
                )
            failure_codes = self._saved_batch_failure_codes(
                version.competitor_profile_version_id
            )
            for code in existing:
                failure_codes.pop(code, None)
            generated_count = 0
            reused_count = 0
            last_target: str | None = None
            for index, target_code in enumerate(target_codes, start=1):
                last_target = target_code
                if target_code in existing:
                    reused_count += 1
                else:
                    source_result = None
                    profile = None
                    snapshots = None
                    try:
                        source_result = self._run_existing_agent(
                            target_sku_code=target_code,
                            serving_scope=scope,
                            candidate_limit=AGENT_SNAPSHOT_CANDIDATE_LIMIT,
                        )
                        profile, snapshots = _build_agent_snapshot(
                            source_result=source_result,
                            version=version,
                        )
                        if len(profile.candidates) > AGENT_SNAPSHOT_CANDIDATE_LIMIT:
                            raise ValueError(
                                "existing agent returned more candidates than requested"
                            )
                        created = self.repository.write_agent_snapshot_draft(
                            profile=profile,
                            sku_snapshots=snapshots,
                        )
                        self.repository.db.commit()
                        if created:
                            generated_count += 1
                        else:
                            reused_count += 1
                        existing[target_code] = (
                            profile.result_hash,
                            len(profile.candidates),
                        )
                        failure_codes.pop(target_code, None)
                    except Exception as exc:
                        self.repository.db.rollback()
                        failure_codes[target_code] = type(exc).__name__
                    finally:
                        del source_result, profile, snapshots
                checkpoint = index % checkpoint_every == 0 or index == len(target_codes)
                if checkpoint:
                    version = self._checkpoint_batch_version(
                        version.competitor_profile_version_id,
                        failure_codes=failure_codes,
                        last_target_sku_code=last_target,
                        target_count=len(target_codes),
                        final=index == len(target_codes),
                    )
                    if progress_callback is not None:
                        progress_callback(
                            {
                                "category_code": scope.category_code,
                                "competitor_profile_version_id": (
                                    version.competitor_profile_version_id
                                ),
                                "profile_version": version.profile_version,
                                "processed_count": index,
                                "target_count": len(target_codes),
                                "generated_count": generated_count,
                                "reused_count": reused_count,
                                "failure_count": len(failure_codes),
                                "last_target_sku_code": last_target,
                                "processing_status": version.processing_status,
                            }
                        )
                    gc.collect()
            return AgentSnapshotBatchGenerationResult(
                version=version,
                target_count=len(target_codes),
                generated_count=generated_count,
                reused_count=reused_count,
                failure_codes=tuple(sorted(failure_codes.items())),
                last_target_sku_code=last_target,
            )

    def _prepare_scope(
        self,
    ) -> tuple[ServingScope, entities.Core3PurchaseReasonProfileVersion]:
        if self._prepared_scope is None:
            request = self.input_provider.build_production_input_request()
            authority = self._current_purchase_reason_authority()
            self._prepared_scope = (_serving_scope(request, authority), authority)
        return self._prepared_scope

    def _authoritative_target_codes(
        self,
        authority: entities.Core3PurchaseReasonProfileVersion,
    ) -> list[str]:
        model = entities.Core3SkuPurchaseReasonProfile
        codes = list(
            self.repository.db.execute(
                select(model.sku_code)
                .where(
                    model.purchase_reason_version_id
                    == authority.purchase_reason_version_id
                )
                .where(model.release_status == "published")
                .where(model.is_current.is_(True))
                .order_by(model.sku_code)
            ).scalars()
        )
        expected_count = int(authority.sku_count or 0)
        if len(codes) != len(set(codes)) or len(codes) != expected_count:
            raise ValueError(
                "current M12D profile rows do not match the authoritative SKU count"
            )
        prefix = self.repository.category_code.value
        if any(not code.startswith(prefix) for code in codes):
            raise ValueError("authoritative M12D profile contains a cross-category SKU")
        return codes

    def _existing_profile_index(
        self,
        competitor_profile_version_id: str,
    ) -> dict[str, tuple[str, int]]:
        model = entities.Core3SkuCompetitorProfile
        rows = self.repository.db.execute(
            select(
                model.target_sku_code,
                model.analysis_result_hash,
                model.analysis_candidate_count,
            )
            .where(model.competitor_profile_version_id == competitor_profile_version_id)
            .where(model.method_version == AGENT_SNAPSHOT_METHOD_VERSION)
        ).all()
        return {
            str(code): (str(result_hash), int(candidate_count or 0))
            for code, result_hash, candidate_count in rows
        }

    def _saved_batch_failure_codes(
        self,
        competitor_profile_version_id: str,
    ) -> dict[str, str]:
        model = entities.Core3CompetitorProfileVersion
        row = self.repository.db.execute(
            select(model.safe_error_summary_json).where(
                model.competitor_profile_version_id == competitor_profile_version_id
            )
        ).scalar_one()
        failures = dict((row or {}).get("failures") or {})
        return {str(code): str(value) for code, value in failures.items()}

    @contextmanager
    def _batch_writer_lock(self):
        bind = self.repository.db.get_bind()
        if bind.dialect.name != "postgresql":
            yield
            return
        connection = bind.connect()
        acquired = bool(
            connection.execute(
                text("select pg_try_advisory_lock(hashtext(:lock_key))"),
                {"lock_key": AGENT_SNAPSHOT_BATCH_WRITER_LOCK_KEY},
            ).scalar_one()
        )
        if not acquired:
            connection.close()
            raise AgentSnapshotBatchAlreadyRunningError(
                "another agent snapshot batch writer owns this category scope"
            )
        try:
            yield
        finally:
            connection.execute(
                text("select pg_advisory_unlock(hashtext(:lock_key))"),
                {"lock_key": AGENT_SNAPSHOT_BATCH_WRITER_LOCK_KEY},
            )
            connection.close()

    def _run_existing_agent(
        self,
        *,
        target_sku_code: str,
        serving_scope: ServingScope,
        candidate_limit: int,
    ) -> dict[str, Any]:
        cached = self._agent_runner_cache
        if cached is None or cached[0] != serving_scope.release_scope_key:
            service = CatForgeAnalystService(
                self.repository.db,
                project_id=serving_scope.project_id,
                category_code=serving_scope.category_code,
            )
            context = service.build_context(
                batch_id=format_serving_scope_batch_id(
                    serving_scope.product_category,
                    serving_scope.source_batch_ids,
                ),
                product_category=serving_scope.product_category.lower(),
                market_window=serving_scope.market_window,
                analysis_population=(
                    "fact_complete_with_comment"
                    if serving_scope.category_code == "TV"
                    else "all_semantic_profiles"
                ),
                resolve_latest=False,
            )
            self._agent_runner_cache = (
                serving_scope.release_scope_key,
                service,
                context,
            )
        else:
            _, service, context = cached
        result = service.sop_orchestrators.competitor_set(
            context,
            sku_code=target_sku_code,
            limit=candidate_limit,
            answer_style="xiaoao",
            with_report="none",
            top_n=AGENT_SNAPSHOT_PRIORITY_LIMIT,
            legacy_live_analysis=True,
        )
        payload = result.get("result") or {}
        competitor_set = payload.get("competitor_set") or {}
        answer = payload.get("competitor_answer") or {}
        if result.get("status") != "ok":
            raise ValueError(
                str(result.get("message_cn") or "existing competitor analysis failed")
            )
        candidate_rows = list(competitor_set.get("candidates") or [])
        analysis_rows = list(answer.get("all_candidates") or [])
        if len(candidate_rows) != len(analysis_rows):
            raise ValueError("existing competitor candidate and analysis counts differ")
        if len(candidate_rows) > candidate_limit:
            raise ValueError(
                "existing competitor analysis exceeded its candidate limit"
            )
        if len(answer.get("top_competitors") or []) > AGENT_SNAPSHOT_PRIORITY_LIMIT:
            raise ValueError(
                "existing competitor analysis returned more than three priorities"
            )
        return result

    def _current_purchase_reason_authority(
        self,
    ) -> entities.Core3PurchaseReasonProfileVersion:
        model = entities.Core3PurchaseReasonProfileVersion
        rows = list(
            self.repository.db.execute(
                select(model)
                .where(model.project_id == self.repository.project_id)
                .where(model.category_code == self.repository.category_code.value)
                .where(model.product_category == self.repository.category_code.value)
                .where(model.rule_version == CORE3_M12D_RULE_VERSION)
                .where(model.release_status == "published")
                .where(model.is_current.is_(True))
            ).scalars()
        )
        if len(rows) != 1:
            raise ValueError(
                "agent snapshot generation requires exactly one current published M12D version"
            )
        return rows[0]

    def _ensure_version(
        self,
        *,
        serving_scope: ServingScope,
        profile_version: str,
        generated_by: str,
    ) -> CompetitorProfileVersionRecord:
        method_versions = {
            "analysis_source": AGENT_SNAPSHOT_SOURCE_VERSION,
            "candidate_discovery": "same_size_price_candidates_v1",
            "persistence": AGENT_SNAPSHOT_METHOD_VERSION,
        }
        version_input_fingerprint = stable_hash(
            {
                "serving_scope": serving_scope.model_dump(mode="json"),
                "method_versions": method_versions,
            },
            version="competitor_profile_agent_snapshot_version_input_v1",
        )
        version = self.repository.create_version(
            CompetitorProfileVersionDraftCreate(
                project_id=serving_scope.project_id,
                category_code=serving_scope.category_code,
                product_category=serving_scope.product_category,
                storage_batch_id=serving_scope.storage_batch_id,
                release_scope_key=serving_scope.release_scope_key,
                profile_version=profile_version,
                schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
                rule_version=AGENT_SNAPSHOT_RULE_VERSION,
                method_version=AGENT_SNAPSHOT_METHOD_VERSION,
                method_versions_json=method_versions,
                serving_scope=serving_scope,
                generated_by=generated_by,
                sku_count=serving_scope.authoritative_sku_count,
                input_fingerprint=version_input_fingerprint,
                candidate_universe_fingerprint=stable_hash(
                    {
                        "source_authority": serving_scope.source_authorities[
                            "M12D"
                        ].result_hash,
                        "policy": (
                            "same_size_price_candidates_limit_"
                            f"{AGENT_SNAPSHOT_CANDIDATE_LIMIT}"
                        ),
                    },
                    version="competitor_profile_agent_candidate_universe_v1",
                ),
                result_hash=stable_hash(
                    {
                        "profile_version": profile_version,
                        "release_scope_key": serving_scope.release_scope_key,
                        "version_input_fingerprint": version_input_fingerprint,
                    },
                    version="competitor_profile_agent_snapshot_version_result_v1",
                ),
                processing_status="running",
            )
        )
        self.repository.db.commit()
        return version

    def _refresh_version_state(
        self,
        competitor_profile_version_id: str,
        *,
        failure_code: str | None = None,
        failed_target_sku_code: str | None = None,
    ) -> CompetitorProfileVersionRecord:
        failure_codes = (
            {failed_target_sku_code or "unknown": failure_code} if failure_code else {}
        )
        model = entities.Core3SkuCompetitorProfile
        completed_count = int(
            self.repository.db.scalar(
                select(func.count())
                .select_from(model)
                .where(
                    model.competitor_profile_version_id == competitor_profile_version_id
                )
                .where(model.method_version == AGENT_SNAPSHOT_METHOD_VERSION)
            )
            or 0
        )
        return self._checkpoint_batch_version(
            competitor_profile_version_id,
            failure_codes=failure_codes,
            last_target_sku_code=failed_target_sku_code,
            target_count=completed_count + len(failure_codes),
            final=True,
        )

    def _checkpoint_batch_version(
        self,
        competitor_profile_version_id: str,
        *,
        failure_codes: dict[str, str],
        last_target_sku_code: str | None,
        target_count: int,
        final: bool,
    ) -> CompetitorProfileVersionRecord:
        db = self.repository.db
        profile_states = list(
            db.execute(
                select(entities.Core3SkuCompetitorProfile.analysis_state)
                .where(
                    entities.Core3SkuCompetitorProfile.competitor_profile_version_id
                    == competitor_profile_version_id
                )
                .where(
                    entities.Core3SkuCompetitorProfile.method_version
                    == AGENT_SNAPSHOT_METHOD_VERSION
                )
            ).scalars()
        )
        counts = {state: profile_states.count(state) for state in set(profile_states)}
        pair_count = _version_row_count(
            db,
            entities.Core3SkuCompetitorProfilePair,
            competitor_profile_version_id,
        )
        selection_count = _version_row_count(
            db,
            entities.Core3SkuCompetitorProfileSelection,
            competitor_profile_version_id,
        )
        completed_count = counts.get("ready", 0) + counts.get("partial", 0)
        complete = completed_count == target_count and not failure_codes
        version = self.repository.update_draft_generation_state(
            competitor_profile_version_id,
            ready_count=counts.get("ready", 0),
            partial_count=counts.get("partial", 0),
            blocked_count=counts.get("blocked", 0),
            failed_count=len(failure_codes),
            pair_count=pair_count,
            relation_count=0,
            selection_count=selection_count,
            processing_status=(
                "success" if complete else "failed" if final else "running"
            ),
            safe_error_summary={
                "failures": dict(sorted(failure_codes.items())),
                "checkpoint": {
                    "completed_count": completed_count,
                    "target_count": target_count,
                    "last_target_sku_code": last_target_sku_code,
                },
            },
        )
        db.commit()
        return version


def _serving_scope(request, authority) -> ServingScope:
    source_batch_ids = sorted({str(value) for value in request.source_batch_ids})
    source_authority = SourceAuthorityRef(
        module_code="M12D",
        project_id=request.project_id,
        category_code=request.category_code,
        product_category=request.product_category,
        profile_version=str(authority.m12d_profile_version),
        schema_version=str(authority.schema_version),
        rule_version=str(authority.rule_version),
        taxonomy_version="m12d_purchase_reason_profile_v1",
        release_status="published",
        is_current=True,
        source_batch_ids=source_batch_ids,
        result_hash=str(authority.result_hash),
    )
    manifest_hash = stable_hash(
        {
            "m12d_profile_version": authority.m12d_profile_version,
            "m12d_result_hash": authority.result_hash,
            "sku_count": authority.sku_count,
        },
        version="competitor_profile_agent_authoritative_manifest_v1",
    )
    scope_fingerprint = stable_hash(
        {
            "project_id": request.project_id,
            "category_code": request.category_code,
            "storage_batch_id": request.storage_batch_id,
            "source_batch_ids": source_batch_ids,
            "authority_result_hash": authority.result_hash,
            "candidate_policy": (
                f"same_size_price_candidates_limit_{AGENT_SNAPSHOT_CANDIDATE_LIMIT}"
            ),
        },
        version="competitor_profile_agent_release_scope_v1",
    )
    return ServingScope(
        project_id=request.project_id,
        category_code=request.category_code,
        product_category=request.product_category,
        analysis_population="existing_competitor_agent_analysis",
        market_window=request.market_window,
        taxonomy_version="competitor_profile_agent_snapshot_source_v1",
        storage_batch_id=request.storage_batch_id,
        source_batch_ids=source_batch_ids,
        source_authorities={"M12D": source_authority},
        sku_prefixes=[request.category_code],
        authoritative_sku_count=max(int(authority.sku_count or 0), 1),
        authoritative_sku_manifest_hash=manifest_hash,
        release_scope_key=(
            f"{request.project_id}:{request.category_code}:"
            f"{scope_fingerprint.rsplit(':', 1)[-1][:24]}"
        ),
    )


def _build_agent_snapshot(
    *,
    source_result: dict[str, Any],
    version: CompetitorProfileVersionRecord,
) -> tuple[AgentCompetitorProfileSnapshot, list[AgentSkuSnapshot]]:
    payload = source_result.get("result") or {}
    source_set = payload.get("competitor_set") or {}
    source_answer = payload.get("competitor_answer") or {}
    target_raw = source_result.get("target") or {}
    fact_brief = source_set.get("target_fact_brief") or {}
    target = _identity(target_raw, version.category_code, fact_brief=fact_brief)
    evidence = _evidence_receipts(source_result.get("evidence") or [])
    limitations = _unique_strings(source_result.get("limitations") or [])
    all_candidates = list(source_answer.get("all_candidates") or [])
    raw_candidates = list(source_set.get("candidates") or [])
    priority_order = [
        str((row.get("candidate") or {}).get("sku_code") or "")
        for row in (source_answer.get("top_competitors") or [])
    ]
    priority_order = [value for value in priority_order if value]
    candidate_pool_order = [
        str((row.get("candidate") or {}).get("sku_code") or "")
        for row in raw_candidates
    ]
    analysis_order = [
        str((row.get("candidate") or {}).get("sku_code") or "")
        for row in all_candidates
    ]
    if (
        len(candidate_pool_order) != len(set(candidate_pool_order))
        or len(analysis_order) != len(set(analysis_order))
        or set(candidate_pool_order) != set(analysis_order)
    ):
        raise ValueError("existing agent candidate and analysis sets differ")

    target_purchase_reason = (
        (all_candidates[0].get("target_purchase_reason_profile") or {})
        if all_candidates
        else {}
    )
    snapshot_refs = {
        sku_code: stable_hash(
            {
                "competitor_profile_version_id": version.competitor_profile_version_id,
                "sku_code": sku_code,
            },
            version="competitor_profile_agent_snapshot_ref_v1",
        )
        for sku_code in {target.sku_code, *analysis_order}
    }
    target_snapshot = _sku_snapshot(
        version=version,
        identity=target,
        fact_brief=fact_brief,
        claim_value=source_set.get("target_claim_value") or {},
        claim_contribution=source_set.get("target_claim_contribution") or {},
        purchase_reason_profile=target_purchase_reason,
        evidence=[],
        limitations=[],
        snapshot_ref=snapshot_refs[target.sku_code],
    )
    candidate_snapshots: list[AgentSkuSnapshot] = []
    records: list[AgentCandidateAnalysisRecord] = []
    selected_ranks = {
        sku_code: rank for rank, sku_code in enumerate(priority_order, start=1)
    }
    for row in all_candidates:
        analysis = AgentCandidateAnalysisPayload.model_validate(row)
        candidate_identity = _identity(
            analysis.candidate.model_dump(mode="python"),
            version.category_code,
            fact_brief=analysis.candidate_fact_brief,
        )
        candidate_evidence = _evidence_for_sku(
            evidence,
            candidate_identity.sku_code,
            target_sku_code=target.sku_code,
        )
        candidate_snapshot = _sku_snapshot(
            version=version,
            identity=candidate_identity,
            fact_brief=analysis.candidate_fact_brief,
            claim_value=analysis.candidate_claim_value,
            claim_contribution=analysis.candidate_claim_contribution,
            purchase_reason_profile=analysis.candidate_purchase_reason_profile,
            evidence=[],
            limitations=[],
            snapshot_ref=snapshot_refs[candidate_identity.sku_code],
        )
        candidate_snapshots.append(candidate_snapshot)
        storage_ref = {"storage_ref": candidate_snapshot.snapshot_ref}
        stored_analysis = analysis.model_copy(
            update={
                "candidate_fact_brief": storage_ref,
                "candidate_claim_value": storage_ref,
                "candidate_claim_contribution": storage_ref,
            }
        )
        record_input = stable_hash(
            {
                "target_sku_code": target.sku_code,
                "candidate_analysis": stored_analysis.model_dump(mode="json"),
                "candidate_snapshot_ref": candidate_snapshot.snapshot_ref,
                "candidate_snapshot_result_hash": candidate_snapshot.result_hash,
            },
            version="competitor_profile_agent_candidate_input_v2",
        )
        record_data = {
            "candidate_sku_code": candidate_identity.sku_code,
            "candidate_snapshot_ref": candidate_snapshot.snapshot_ref,
            "candidate_snapshot_result_hash": candidate_snapshot.result_hash,
            "source_rank": analysis.rank,
            "selected_rank": selected_ranks.get(candidate_identity.sku_code),
            "analysis": stored_analysis,
            "evidence": candidate_evidence,
            "input_fingerprint": record_input,
        }
        records.append(
            AgentCandidateAnalysisRecord(
                **record_data,
                result_hash=stable_hash(
                    _model_json(record_data),
                    version="competitor_profile_agent_candidate_result_v2",
                ),
            )
        )

    source_analysis_result_hash = stable_hash(
        {
            "target": target_raw,
            "ranking_policy": source_set.get("ranking_policy") or [],
            "target_fact_brief": fact_brief,
            "target_claim_value": source_set.get("target_claim_value") or {},
            "target_claim_contribution": source_set.get("target_claim_contribution")
            or {},
            "m12d_consumption": source_set.get("m12d_consumption") or {},
            "candidate_pool_order": candidate_pool_order,
            "all_candidates": all_candidates,
            "priority_order": priority_order,
        },
        version="competitor_set_legacy_analysis_result_v1",
    )
    profile_input = stable_hash(
        {
            "source_analysis_result_hash": source_analysis_result_hash,
            "source_batch_ids": version.serving_scope.source_batch_ids,
            "target_sku_code": target.sku_code,
            "method_version": AGENT_SNAPSHOT_METHOD_VERSION,
        },
        version="competitor_profile_agent_profile_input_v2",
    )
    profile_data = {
        "source": "competitor_profile_v1_1",
        "schema_version": COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
        "method_version": AGENT_SNAPSHOT_METHOD_VERSION,
        "source_analysis_version": AGENT_SNAPSHOT_SOURCE_VERSION,
        "competitor_profile_version_id": version.competitor_profile_version_id,
        "profile_version": version.profile_version,
        "project_id": version.project_id,
        "category_code": version.category_code,
        "release_scope_key": version.release_scope_key,
        "storage_batch_id": version.storage_batch_id,
        "source_batch_ids": version.serving_scope.source_batch_ids,
        "target": target,
        "target_snapshot_ref": target_snapshot.snapshot_ref,
        "target_snapshot_result_hash": target_snapshot.result_hash,
        "target_fact_brief": {"storage_ref": target_snapshot.snapshot_ref},
        "target_claim_value": {"storage_ref": target_snapshot.snapshot_ref},
        "target_claim_contribution": {"storage_ref": target_snapshot.snapshot_ref},
        "m12d_consumption": source_set.get("m12d_consumption") or {},
        "candidate_pool_policy": source_set.get("ranking_policy")
        or ["same_size_price_pool"],
        "candidate_pool_order": candidate_pool_order,
        "analysis_order": analysis_order,
        "candidates": records,
        "priority_order": priority_order,
        "evidence": evidence,
        "limitations": limitations,
        "source_analysis_result_hash": source_analysis_result_hash,
        "input_fingerprint": profile_input,
    }
    profile = AgentCompetitorProfileSnapshot(
        **profile_data,
        result_hash=stable_hash(
            _model_json(profile_data),
            version="competitor_profile_agent_profile_result_v2",
        ),
    )
    return profile, [target_snapshot, *candidate_snapshots]


def _identity(
    row: dict[str, Any],
    category_code: str,
    *,
    fact_brief: dict[str, Any],
) -> AgentSkuIdentity:
    market_metrics = ((fact_brief.get("sections") or {}).get("market") or {}).get(
        "market_metrics"
    ) or {}
    return AgentSkuIdentity(
        sku_code=str(row.get("sku_code") or ""),
        brand_name=row.get("brand_name"),
        model_name=row.get("model_name"),
        product_category=category_code,
        size_tier=row.get("size_tier"),
        price_band_in_size_tier=row.get("price_band_in_size_tier"),
        screen_size_inch=_canonical_decimal(row.get("screen_size_inch"), "0.01"),
        weighted_price=_canonical_decimal(
            row.get("weighted_price")
            if row.get("weighted_price") is not None
            else row.get("price_wavg", market_metrics.get("price_wavg")),
            "0.0001",
        ),
        avg_weekly_sales_volume=_canonical_decimal(
            row.get("avg_weekly_sales_volume")
            if row.get("avg_weekly_sales_volume") is not None
            else market_metrics.get("avg_weekly_sales_volume"),
            "0.000001",
        ),
        sales_volume_total=_canonical_decimal(
            row.get("sales_volume_total")
            if row.get("sales_volume_total") is not None
            else market_metrics.get("sales_volume_total"),
            "0.0001",
        ),
    )


def _canonical_decimal(value: Any, quantum: str) -> Decimal | None:
    """Make equal source numerics produce one stable snapshot/hash value."""

    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


def _sku_snapshot(
    *,
    version: CompetitorProfileVersionRecord,
    identity: AgentSkuIdentity,
    fact_brief: dict[str, Any],
    claim_value: dict[str, Any],
    claim_contribution: dict[str, Any],
    purchase_reason_profile: dict[str, Any],
    evidence: list[AgentEvidenceReceipt],
    limitations: list[str],
    snapshot_ref: str,
) -> AgentSkuSnapshot:
    source_payload = AgentSkuSourcePayload(
        fact_brief=fact_brief,
        claim_value=claim_value,
        claim_contribution=claim_contribution,
        purchase_reason_profile=purchase_reason_profile,
    )
    payload_b64 = encode_agent_sku_payload(source_payload)
    available_modules = []
    if fact_brief:
        available_modules.append("sku_fact_brief")
    if claim_value:
        available_modules.append("sku_claim_value")
    if claim_contribution:
        available_modules.append("claim_contribution")
    if purchase_reason_profile:
        available_modules.append("M12D")
    input_fingerprint = stable_hash(
        {
            "identity": identity.model_dump(mode="json"),
            "payload_codec": "gzip+base64+json",
            "payload_b64": payload_b64,
        },
        version="competitor_profile_agent_sku_snapshot_input_v2",
    )
    data = {
        "schema_version": COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
        "method_version": AGENT_SNAPSHOT_METHOD_VERSION,
        "competitor_profile_version_id": version.competitor_profile_version_id,
        "project_id": version.project_id,
        "category_code": version.category_code,
        "release_scope_key": version.release_scope_key,
        "identity": identity,
        "payload_codec": "gzip+base64+json",
        "payload_b64": payload_b64,
        "available_modules": available_modules,
        "evidence": evidence,
        "limitations": limitations,
        "snapshot_ref": snapshot_ref,
        "input_fingerprint": input_fingerprint,
    }
    return AgentSkuSnapshot(
        **data,
        result_hash=stable_hash(
            _model_json(data),
            version="competitor_profile_agent_sku_snapshot_result_v2",
        ),
    )


def _evidence_receipts(rows: list[dict[str, Any]]) -> list[AgentEvidenceReceipt]:
    receipts = []
    for row in rows:
        raw = dict(row)
        receipts.append(
            AgentEvidenceReceipt(
                source_module=str(row.get("source_module") or "unknown"),
                sku_code=_optional_text(row.get("sku_code")),
                candidate_sku_code=_optional_text(row.get("candidate_sku_code")),
                row_count=_optional_nonnegative_int(row.get("row_count")),
                evidence_id_count=_optional_nonnegative_int(
                    row.get("evidence_id_count")
                ),
                profile_version=_optional_text(row.get("profile_version")),
                result_hash=_optional_text(row.get("result_hash")),
                raw=raw,
            )
        )
    return receipts


def _evidence_for_sku(
    evidence: list[AgentEvidenceReceipt],
    sku_code: str,
    *,
    target_sku_code: str | None = None,
) -> list[AgentEvidenceReceipt]:
    matched = [
        row
        for row in evidence
        if row.sku_code == sku_code
        or row.candidate_sku_code == sku_code
        or (
            target_sku_code is not None
            and row.sku_code == target_sku_code
            and row.candidate_sku_code in {None, sku_code}
        )
    ]
    return matched


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _model_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _model_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_model_json(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def _unique_strings(values: list[Any]) -> list[str]:
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _version_row_count(db, model, version_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.competitor_profile_version_id == version_id)
            .where(model.method_version == AGENT_SNAPSHOT_METHOD_VERSION)
        )
        or 0
    )


__all__ = [
    "AGENT_SNAPSHOT_BATCH_WRITER_LOCK_KEY",
    "AgentSnapshotBatchAlreadyRunningError",
    "AgentSnapshotBatchGenerationResult",
    "AgentSnapshotGenerationResult",
    "CompetitorProfileAgentSnapshotGenerationService",
]
