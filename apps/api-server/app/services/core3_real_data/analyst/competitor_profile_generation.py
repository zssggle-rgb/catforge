"""Transactional single-SKU and resumable batch generation for competitor profiles."""

from __future__ import annotations

from contextlib import contextmanager
import gc
import logging
from threading import Lock
from typing import Iterator, Protocol

from app.services.core3_real_data.analyst.competitor_profile_generation_schemas import (
    CompetitorProfileBatchGenerationResult,
    CompetitorProfileGenerationReadback,
    CompetitorProfileGenerationRequest,
    CompetitorProfileSkuGenerationStatus,
)
from app.services.core3_real_data.analyst.competitor_profile_input_provider import (
    CompetitorProfileInputProvider,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer import (
    CompetitorProfileMaterializer,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    MaterializedCompetitorProfile,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfilePersistenceBundle,
    CompetitorProfileReadBundle,
    CompetitorProfileResultHashReceipt,
    CompetitorProfileVersionDraftCreate,
    CompetitorProfileVersionRecord,
    SkuCompetitorPairDraft,
    SkuCompetitorProfileDraft,
    SkuCompetitorRelationDraft,
    SkuCompetitorSelectionDraft,
    validate_persistence_bundle_parts,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileRepository,
)
from app.services.core3_real_data.hash_utils import stable_hash


logger = logging.getLogger(__name__)


class CompetitorProfileGenerationAlreadyRunningError(RuntimeError):
    pass


class CompetitorProfileGenerationReadbackError(RuntimeError):
    pass


class CompetitorProfileGenerationLock(Protocol):
    @contextmanager
    def acquire(self, key: str) -> Iterator[bool]: ...


class InMemoryCompetitorProfileGenerationLock:
    """Process-local non-blocking lock; replaceable by a distributed lock."""

    _guard = Lock()
    _locks: dict[str, Lock] = {}

    @contextmanager
    def acquire(self, key: str) -> Iterator[bool]:
        with self._guard:
            lock = self._locks.setdefault(key, Lock())
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()


class CompetitorProfileGenerationService:
    """Connect the frozen input, materializer, and persistence contracts."""

    def __init__(
        self,
        *,
        repository: CompetitorProfileRepository,
        input_provider: CompetitorProfileInputProvider,
        materializer: CompetitorProfileMaterializer | None = None,
        generation_lock: CompetitorProfileGenerationLock | None = None,
    ) -> None:
        self.repository = repository
        self.input_provider = input_provider
        self.materializer = materializer or CompetitorProfileMaterializer()
        self.generation_lock = generation_lock or InMemoryCompetitorProfileGenerationLock()

    def ensure_version(
        self,
        request: CompetitorProfileGenerationRequest,
        *,
        category_bundle: CompetitorProfileCategoryInputBundle | None = None,
    ) -> CompetitorProfileVersionRecord:
        category = category_bundle or self.input_provider.load_category_input_bundle(
            request.input_request
        )
        _assert_generation_scope(request, category)
        version_input_fingerprint = _version_input_fingerprint(request, category)
        version = self.repository.create_version(
            CompetitorProfileVersionDraftCreate(
                project_id=category.serving_scope.project_id,
                category_code=category.serving_scope.category_code,
                product_category=category.serving_scope.product_category,
                storage_batch_id=category.serving_scope.storage_batch_id,
                release_scope_key=category.serving_scope.release_scope_key,
                profile_version=request.profile_version,
                method_versions_json=_method_versions(request),
                serving_scope=category.serving_scope,
                generated_by=request.generated_by,
                sku_count=len(category.authoritative_sku_codes),
                input_fingerprint=version_input_fingerprint,
                candidate_universe_fingerprint=stable_hash(
                    {
                        "authoritative_sku_codes": category.authoritative_sku_codes,
                        "category_input_fingerprint": category.input_fingerprint,
                    },
                    version="competitor_profile_candidate_universe_v1",
                ),
                result_hash=stable_hash(
                    {
                        "profile_version": request.profile_version,
                        "release_scope_key": category.serving_scope.release_scope_key,
                        "version_input_fingerprint": version_input_fingerprint,
                    },
                    version="competitor_profile_version_result_v1",
                ),
            )
        )
        self.repository.db.commit()
        return version

    def generate_draft(
        self,
        request: CompetitorProfileGenerationRequest,
        *,
        target_sku_code: str,
    ) -> CompetitorProfileGenerationReadback:
        category = self.input_provider.load_category_input_bundle(request.input_request)
        _assert_generation_scope(request, category)
        target_code = target_sku_code.strip().upper()
        if target_code not in set(category.authoritative_sku_codes):
            raise ValueError(
                f"SKU is outside the authoritative competitor-profile scope: {target_code}"
            )
        version = self.ensure_version(request, category_bundle=category)
        key = _lock_key(version)
        with self.generation_lock.acquire(key) as acquired:
            if not acquired:
                raise CompetitorProfileGenerationAlreadyRunningError(
                    f"competitor profile generation already running: {key}"
                )
            target = self.input_provider.load_target_input(category, target_code)
            materialized = self.materializer.materialize(category, target, request.config)
            del target, category
            gc.collect()
            bundle = materialized_to_persistence_bundle(materialized, version)
            receipt = _readback_receipt(bundle)
            failures = _generation_failures(version)
            failures.pop(target_code, None)
            with self.repository.db.begin():
                created = self.repository.write_draft_without_readback(
                    bundle,
                    use_savepoint=False,
                )
                updated = _checkpoint_version(
                    self.repository,
                    version,
                    added=materialized if created else None,
                    failures=failures,
                    processing_status="running",
                )
            del bundle, materialized
            self.repository.db.expunge_all()
            gc.collect()
            if updated.sku_count == (
                updated.ready_count
                + updated.partial_count
                + updated.blocked_count
                + updated.failed_count
            ):
                with self.repository.db.begin():
                    self.repository.update_draft_generation_state(
                        updated.competitor_profile_version_id,
                        ready_count=updated.ready_count,
                        partial_count=updated.partial_count,
                        blocked_count=updated.blocked_count,
                        failed_count=updated.failed_count,
                        pair_count=updated.pair_count,
                        relation_count=updated.relation_count,
                        selection_count=updated.selection_count,
                        processing_status=(
                            "completed_with_errors"
                            if updated.failed_count
                            else "completed"
                        ),
                        safe_error_summary={"failures": failures},
                    )
            actual_receipt = self.repository.get_profile_result_hash_receipt(
                competitor_profile_version_id=version.competitor_profile_version_id,
                target_sku_code=target_code,
            )
            _verify_readback(receipt, actual_receipt)
            persisted = self.repository.get_profile(
                competitor_profile_version_id=version.competitor_profile_version_id,
                target_sku_code=target_code,
                compact=len(receipt.pair_hashes) > 100,
            )
            self.repository.db.commit()
            if persisted is None:
                raise CompetitorProfileGenerationReadbackError(
                    "competitor profile disappeared after generation commit"
                )
            return CompetitorProfileGenerationReadback(
                status="generated" if created else "reused",
                persisted=persisted,
            )

    def batch_generate(
        self,
        request: CompetitorProfileGenerationRequest,
        *,
        resume_unfinished_only: bool = True,
        page_size: int = 50,
        max_new_skus: int | None = None,
    ) -> CompetitorProfileBatchGenerationResult:
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be between 1 and 500")
        if max_new_skus is not None and max_new_skus < 1:
            raise ValueError("max_new_skus must be greater than zero")
        if max_new_skus is not None and not resume_unfinished_only:
            raise ValueError("max_new_skus requires resume_unfinished_only")
        category = self.input_provider.load_category_input_bundle(request.input_request)
        _assert_generation_scope(request, category)
        version = self.ensure_version(request, category_bundle=category)
        key = _lock_key(version)
        with self.generation_lock.acquire(key) as acquired:
            if not acquired:
                raise CompetitorProfileGenerationAlreadyRunningError(
                    f"competitor profile generation already running: {key}"
                )
            existing_codes = _all_profile_codes(
                self.repository,
                version.competitor_profile_version_id,
            )
            self.repository.db.commit()
            scheduled = [
                code
                for code in category.authoritative_sku_codes
                if not (resume_unfinished_only and code in existing_codes)
            ]
            if max_new_skus is not None:
                scheduled = scheduled[:max_new_skus]
            statuses = [
                CompetitorProfileSkuGenerationStatus(
                    target_sku_code=code,
                    status="skipped",
                )
                for code in category.authoritative_sku_codes
                if resume_unfinished_only and code in existing_codes
            ]
            failures = _generation_failures(version)
            checkpoint: str | None = None
            current = version
            for page_start in range(0, len(scheduled), page_size):
                for code in scheduled[page_start : page_start + page_size]:
                    checkpoint = code
                    try:
                        target = self.input_provider.load_target_input(category, code)
                        materialized = self.materializer.materialize(
                            category,
                            target,
                            request.config,
                        )
                        bundle = materialized_to_persistence_bundle(materialized, current)
                        existing = code in existing_codes
                        failures.pop(code, None)
                        with self.repository.db.begin():
                            persisted = self.repository.write_draft(
                                bundle,
                                use_savepoint=False,
                            )
                            current = _checkpoint_version(
                                self.repository,
                                current,
                                added=None if existing else materialized,
                                failures=failures,
                                processing_status="running",
                            )
                        _verify_readback(
                            _readback_receipt(bundle),
                            _receipt_from_read_bundle(persisted),
                        )
                        existing_codes.add(code)
                        statuses.append(
                            CompetitorProfileSkuGenerationStatus(
                                target_sku_code=code,
                                status="reused" if existing else "generated",
                                profile_result_hash=materialized.draft.profile.result_hash,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001 - per-SKU isolation boundary
                        self.repository.db.rollback()
                        logger.exception(
                            "competitor profile generation failed",
                            extra={
                                "project_id": request.input_request.project_id,
                                "category_code": request.input_request.category_code,
                                "profile_version": request.profile_version,
                                "target_sku_code": code,
                            },
                        )
                        error_code = type(exc).__name__
                        failures[code] = {
                            "error_code": error_code,
                            "error_message": "SKU competitor profile generation failed; inspect server logs.",
                        }
                        statuses.append(
                            CompetitorProfileSkuGenerationStatus(
                                target_sku_code=code,
                                status="failed",
                                **failures[code],
                            )
                        )
                        with self.repository.db.begin():
                            current = _checkpoint_version(
                                self.repository,
                                current,
                                added=None,
                                failures=failures,
                                processing_status="running",
                            )
            unfinished = [
                code
                for code in category.authoritative_sku_codes
                if code not in existing_codes
            ]
            final_status = (
                "completed_with_errors"
                if failures and set(unfinished) == set(failures)
                else "completed"
                if not unfinished
                else "running"
            )
            with self.repository.db.begin():
                current = self.repository.update_draft_generation_state(
                    current.competitor_profile_version_id,
                    ready_count=current.ready_count,
                    partial_count=current.partial_count,
                    blocked_count=current.blocked_count,
                    failed_count=len(failures),
                    pair_count=current.pair_count,
                    relation_count=current.relation_count,
                    selection_count=current.selection_count,
                    processing_status=final_status,
                    safe_error_summary={"failures": failures},
                )
            statuses.sort(key=lambda row: row.target_sku_code)
            return CompetitorProfileBatchGenerationResult(
                version=current,
                requested_sku_count=len(category.authoritative_sku_codes),
                remaining_sku_count=len(unfinished),
                generated_count=sum(row.status == "generated" for row in statuses),
                reused_count=sum(row.status == "reused" for row in statuses),
                skipped_count=sum(row.status == "skipped" for row in statuses),
                failed_count=sum(row.status == "failed" for row in statuses),
                checkpoint_sku_code=checkpoint,
                statuses=statuses,
            )


def materialized_to_persistence_bundle(
    materialized: MaterializedCompetitorProfile,
    version: CompetitorProfileVersionRecord,
) -> CompetitorProfilePersistenceBundle:
    """Attach one immutable materialized draft to a persisted version scope."""

    draft = materialized.draft
    if draft.profile.category_code != version.category_code:
        raise ValueError("materialized profile category must match version")
    common = {
        "competitor_profile_version_id": version.competitor_profile_version_id,
        "project_id": version.project_id,
        "category_code": version.category_code,
        "product_category": version.product_category,
        "storage_batch_id": version.storage_batch_id,
        "release_scope_key": version.release_scope_key,
        "profile_version": version.profile_version,
        "schema_version": version.schema_version,
        "rule_version": version.rule_version,
        "method_version": version.method_version,
    }
    profile = SkuCompetitorProfileDraft(
        **common,
        target_sku_code=draft.profile.target_sku_code,
        input_fingerprint=draft.profile.input_fingerprint,
        result_hash=draft.profile.result_hash,
        review_required=draft.profile.review_required,
        review_status=draft.profile.review_status,
        review_reasons=draft.profile.limitations,
        profile_payload=draft.profile,
    )
    pairs = [
        SkuCompetitorPairDraft(
            **common,
            target_sku_code=draft.profile.target_sku_code,
            candidate_sku_code=pair.candidate.sku_code,
            candidate_status=pair.candidate_status,
            confidence_level=pair.confidence_level,
            selected=pair.selected,
            competitor_member=pair.competitor_member,
            reference_member=pair.reference_member,
            input_fingerprint=pair.input_fingerprint,
            result_hash=pair.result_hash,
            review_required=pair.review_required,
            review_status=pair.review_status,
            review_reasons=pair.risk_flags,
            pair_payload=pair,
        )
        for pair in draft.pairs
    ]
    relations = [
        SkuCompetitorRelationDraft(
            **common,
            target_sku_code=draft.profile.target_sku_code,
            candidate_sku_code=pair.candidate.sku_code,
            relation_code=relation.relation_code,
            input_fingerprint=pair.input_fingerprint,
            result_hash=relation.result_hash,
            review_required=str(relation.status) == "review_required",
            review_status=(
                "review_required"
                if str(relation.status) == "review_required"
                else "auto_pass"
            ),
            review_reasons=relation.reason_codes,
            relation_payload=relation,
        )
        for pair in draft.pairs
        for relation in pair.relation_assessments
    ]
    pair_by_code = {pair.candidate.sku_code: pair for pair in draft.pairs}
    selections = [
        SkuCompetitorSelectionDraft(
            **common,
            target_sku_code=selection.target_sku_code,
            candidate_sku_code=selection.candidate_sku_code,
            selection_rank=selection.selection_rank,
            input_fingerprint=pair_by_code[
                selection.candidate_sku_code
            ].input_fingerprint,
            result_hash=selection.result_hash,
            selection_payload=selection,
        )
        for selection in draft.selections
    ]
    validate_persistence_bundle_parts(
        profile=profile,
        pairs=pairs,
        relations=relations,
        selections=selections,
    )
    return CompetitorProfilePersistenceBundle.model_construct(
        profile=profile,
        pairs=pairs,
        relations=relations,
        selections=selections,
    )


def _assert_generation_scope(
    request: CompetitorProfileGenerationRequest,
    category: CompetitorProfileCategoryInputBundle,
) -> None:
    scope = category.serving_scope
    input_request = request.input_request
    if (
        scope.project_id != input_request.project_id
        or scope.category_code != input_request.category_code
        or scope.product_category != request.config.product_category
        or scope.storage_batch_id != input_request.storage_batch_id
    ):
        raise ValueError("generation request, input bundle, and config scope must match")


def _method_versions(request: CompetitorProfileGenerationRequest) -> dict[str, str]:
    config = request.config
    return dict(
        sorted(
            {
                "candidate_eligibility": config.eligibility.config_version,
                "candidate_recall": config.recall.config_version,
                "key_selection": config.key_selection.config_version,
                "materializer": config.config_version,
                "price_volume": config.price_volume.config_version,
                "purchase_pool": config.purchase_pool.config_version,
                "relation": config.relation.config_version,
                "value_substitution": config.value_substitution.config_version,
            }.items()
        )
    )


def _version_input_fingerprint(
    request: CompetitorProfileGenerationRequest,
    category: CompetitorProfileCategoryInputBundle,
) -> str:
    return stable_hash(
        {
            "category_input_fingerprint": category.input_fingerprint,
            "serving_scope": category.serving_scope.model_dump(mode="json"),
            "config": request.config.model_dump(mode="json"),
        },
        version="competitor_profile_version_input_v1",
    )


def _lock_key(version: CompetitorProfileVersionRecord) -> str:
    return (
        f"{version.project_id}:{version.category_code}:"
        f"{version.release_scope_key}:{version.profile_version}"
    )


def _all_profile_codes(
    repository: CompetitorProfileRepository,
    version_id: str,
) -> set[str]:
    codes: set[str] = set()
    offset = 0
    while True:
        rows = repository.list_profile_progress(
            competitor_profile_version_id=version_id,
            limit=1000,
            offset=offset,
        )
        codes.update(str(row["target_sku_code"]) for row in rows)
        if len(rows) < 1000:
            return codes
        offset += len(rows)


def _generation_failures(
    version: CompetitorProfileVersionRecord,
) -> dict[str, dict[str, str]]:
    raw = version.safe_error_summary.get("failures", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(code): {
            "error_code": str(value.get("error_code", "GenerationError")),
            "error_message": str(
                value.get(
                    "error_message",
                    "SKU competitor profile generation failed; inspect server logs.",
                )
            ),
        }
        for code, value in raw.items()
        if isinstance(value, dict)
    }


def _checkpoint_version(
    repository: CompetitorProfileRepository,
    version: CompetitorProfileVersionRecord,
    *,
    added: MaterializedCompetitorProfile | None,
    failures: dict[str, dict[str, str]],
    processing_status: str,
) -> CompetitorProfileVersionRecord:
    ready = version.ready_count
    partial = version.partial_count
    blocked = version.blocked_count
    pair_count = version.pair_count
    relation_count = version.relation_count
    selection_count = version.selection_count
    if added is not None:
        state = str(added.draft.profile.analysis_state)
        ready += state == "ready"
        partial += state == "partial"
        blocked += state == "blocked"
        pair_count += len(added.draft.pairs)
        relation_count += sum(
            len(pair.relation_assessments) for pair in added.draft.pairs
        )
        selection_count += len(added.draft.selections)
    return repository.update_draft_generation_state(
        version.competitor_profile_version_id,
        ready_count=ready,
        partial_count=partial,
        blocked_count=blocked,
        failed_count=len(failures),
        pair_count=pair_count,
        relation_count=relation_count,
        selection_count=selection_count,
        processing_status=processing_status,
        safe_error_summary={"failures": failures},
    )


def _readback_receipt(
    expected: CompetitorProfilePersistenceBundle,
) -> CompetitorProfileResultHashReceipt:
    return CompetitorProfileResultHashReceipt(
        profile_result_hash=expected.profile.result_hash,
        pair_hashes=tuple(
            sorted((row.candidate_sku_code, row.result_hash) for row in expected.pairs)
        ),
        relation_hashes=tuple(
            sorted(
                (row.candidate_sku_code, row.relation_code, row.result_hash)
                for row in expected.relations
            )
        ),
        selection_hashes=tuple(
            sorted(
                (row.candidate_sku_code, row.result_hash)
                for row in expected.selections
            )
        ),
    )


def _verify_readback(
    expected: CompetitorProfileResultHashReceipt,
    actual: CompetitorProfileResultHashReceipt,
) -> None:
    if expected.profile_result_hash != actual.profile_result_hash:
        raise CompetitorProfileGenerationReadbackError(
            "competitor profile readback hash mismatch"
        )
    if (
        expected.pair_hashes != actual.pair_hashes
        or expected.relation_hashes != actual.relation_hashes
        or expected.selection_hashes != actual.selection_hashes
    ):
        raise CompetitorProfileGenerationReadbackError(
            "competitor profile child readback hash mismatch"
        )


def _receipt_from_read_bundle(
    actual: CompetitorProfileReadBundle,
) -> CompetitorProfileResultHashReceipt:
    return CompetitorProfileResultHashReceipt(
        profile_result_hash=actual.profile.result_hash,
        pair_hashes=tuple(
            sorted((row.candidate_sku_code, row.result_hash) for row in actual.pairs)
        ),
        relation_hashes=tuple(
            sorted(
                (row.candidate_sku_code, row.relation_code, row.result_hash)
                for row in actual.relations
            )
        ),
        selection_hashes=tuple(
            sorted(
                (row.candidate_sku_code, row.result_hash)
                for row in actual.selections
            )
        ),
    )


__all__ = [
    "CompetitorProfileGenerationAlreadyRunningError",
    "CompetitorProfileGenerationReadbackError",
    "CompetitorProfileGenerationService",
    "InMemoryCompetitorProfileGenerationLock",
    "materialized_to_persistence_bundle",
]
