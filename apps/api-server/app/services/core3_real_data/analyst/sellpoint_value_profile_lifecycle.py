"""Version lifecycle, batch scheduling, resume, and diff for profile drafts."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from threading import Lock
from typing import Iterator, Protocol, Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer import (
    materialize_sellpoint_value_profile,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer_schemas import (
    ProfileGenerationReadback,
    SellpointValueBatchGenerationResult,
    SellpointValueMaterializationInput,
    SellpointValueProfileDiff,
    SellpointValueVersionRequest,
    SkuGenerationStatus,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SellpointValueProfileReadBundle,
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SellpointValueVersionRecord,
    SkuSellpointValueProfileRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.hash_utils import stable_hash


PROFILE_DIFF_HASH_VERSION = "sellpoint_value_profile_diff_v1"
logger = logging.getLogger(__name__)


class SellpointValueGenerationAlreadyRunningError(RuntimeError):
    pass


class SellpointValueReadbackHashMismatchError(RuntimeError):
    pass


class SellpointValueMaterializationInputProvider(Protocol):
    def list_authoritative_sku_codes(
        self,
        request: SellpointValueVersionRequest,
    ) -> Sequence[str]: ...

    def load_materialization_input(
        self,
        request: SellpointValueVersionRequest,
        sku_code: str,
    ) -> SellpointValueMaterializationInput: ...


class ProfileGenerationLock(Protocol):
    @contextmanager
    def acquire(self, key: str) -> Iterator[bool]: ...


class InMemoryProfileGenerationLock:
    """Process-local non-blocking lock; injectable for distributed runtimes."""

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


class SellpointValueProfileLifecycleService:
    def __init__(
        self,
        *,
        repository: SellpointValueProfileRepository,
        input_provider: SellpointValueMaterializationInputProvider,
        generation_lock: ProfileGenerationLock | None = None,
    ) -> None:
        self.repository = repository
        self.input_provider = input_provider
        self.generation_lock = generation_lock or InMemoryProfileGenerationLock()

    def ensure_version(
        self,
        request: SellpointValueVersionRequest,
    ) -> SellpointValueVersionRecord:
        version = self.repository.create_version(
            SellpointValueVersionDraftCreate(
                project_id=request.project_id,
                category_code=request.category_code,
                batch_id=request.batch_id,
                product_category=request.category_code,
                profile_version=request.profile_version,
                method_version=SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
                method_versions_json=dict(sorted(request.method_versions.items())),
                generated_by=request.generated_by,
                source_batch_ids_json=list(
                    request.source_scope.get("source_batch_ids")
                    or [request.batch_id]
                ),
                source_scope_json=request.source_scope,
                input_fingerprint=request.version_input_fingerprint,
                candidate_universe_fingerprint=(
                    request.candidate_universe_fingerprint
                ),
                result_hash=request.version_result_hash,
                processing_status="pending",
            )
        )
        self.repository.db.commit()
        return version

    def generate_draft(
        self,
        request: SellpointValueVersionRequest,
        *,
        sku_code: str,
    ) -> ProfileGenerationReadback:
        authoritative = _unique_codes(
            self.input_provider.list_authoritative_sku_codes(request)
        )
        if sku_code not in set(authoritative):
            raise ValueError(
                f"SKU is outside the authoritative profile scope: {sku_code}"
            )
        version = self.ensure_version(request)
        key = _lock_key(request)
        with self.generation_lock.acquire(key) as acquired:
            if not acquired:
                raise SellpointValueGenerationAlreadyRunningError(
                    f"profile generation already running: {key}"
                )
            with self.repository.db.begin():
                self._update_progress(
                    request=request,
                    version_id=version.sellpoint_value_profile_version_id,
                    authoritative_sku_codes=authoritative,
                    status_updates={},
                    checkpoint_sku_code=sku_code,
                    processing_status="running",
                )
                readback, _ = self._generate_one(request, version, sku_code)
                self._update_progress(
                    request=request,
                    version_id=version.sellpoint_value_profile_version_id,
                    authoritative_sku_codes=authoritative,
                    status_updates={sku_code: "generated"},
                    checkpoint_sku_code=sku_code,
                    processing_status="completed",
                )
            persisted = self.get_profile(
                batch_id=request.batch_id,
                profile_version=request.profile_version,
                sku_code=sku_code,
            )
            if persisted is None:
                raise SellpointValueReadbackHashMismatchError(
                    "profile disappeared after final generation commit"
                )
            _verify_readback(readback.persisted, persisted)
            return ProfileGenerationReadback(
                profile=readback.profile,
                persisted=persisted,
            )

    def batch_generate(
        self,
        request: SellpointValueVersionRequest,
        *,
        resume_unfinished_only: bool = True,
        page_size: int = 50,
    ) -> SellpointValueBatchGenerationResult:
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size must be between 1 and 500")
        version = self.ensure_version(request)
        key = _lock_key(request)
        with self.generation_lock.acquire(key) as acquired:
            if not acquired:
                raise SellpointValueGenerationAlreadyRunningError(
                    f"profile generation already running: {key}"
                )
            sku_codes = _unique_codes(
                self.input_provider.list_authoritative_sku_codes(request)
            )
            completed = {
                row.sku_code
                for row in self._all_profiles(
                    version.sellpoint_value_profile_version_id
                )
            }
            statuses: list[SkuGenerationStatus] = []
            status_updates: dict[str, str] = {}
            checkpoint: str | None = None
            self._update_progress(
                request=request,
                version_id=version.sellpoint_value_profile_version_id,
                authoritative_sku_codes=sku_codes,
                status_updates={},
                checkpoint_sku_code=None,
                processing_status="running",
            )
            self.repository.db.commit()

            for page_start in range(0, len(sku_codes), page_size):
                for sku_code in sku_codes[page_start : page_start + page_size]:
                    checkpoint = sku_code
                    if resume_unfinished_only and sku_code in completed:
                        statuses.append(
                            SkuGenerationStatus(
                                sku_code=sku_code,
                                status="skipped",
                            )
                        )
                        status_updates[sku_code] = "skipped"
                        self._update_progress(
                            request=request,
                            version_id=version.sellpoint_value_profile_version_id,
                            authoritative_sku_codes=sku_codes,
                            status_updates=status_updates,
                            checkpoint_sku_code=checkpoint,
                            processing_status="running",
                        )
                        self.repository.db.commit()
                        continue
                    try:
                        self._update_progress(
                            request=request,
                            version_id=version.sellpoint_value_profile_version_id,
                            authoritative_sku_codes=sku_codes,
                            status_updates=status_updates,
                            checkpoint_sku_code=checkpoint,
                            processing_status="running",
                        )
                        readback, reused = self._generate_one(
                            request,
                            version,
                            sku_code,
                        )
                        status = "reused" if reused else "generated"
                        statuses.append(
                            SkuGenerationStatus(
                                sku_code=sku_code,
                                status=status,
                                profile_result_hash=readback.profile.result_hash,
                            )
                        )
                        status_updates[sku_code] = status
                        self._update_progress(
                            request=request,
                            version_id=version.sellpoint_value_profile_version_id,
                            authoritative_sku_codes=sku_codes,
                            status_updates=status_updates,
                            checkpoint_sku_code=checkpoint,
                            processing_status="running",
                        )
                        self.repository.db.commit()
                    except Exception as exc:  # isolated per SKU by design
                        self.repository.db.rollback()
                        logger.exception(
                            "sellpoint-value profile generation failed",
                            extra={
                                "project_id": request.project_id,
                                "category_code": request.category_code,
                                "batch_id": request.batch_id,
                                "profile_version": request.profile_version,
                                "sku_code": sku_code,
                            },
                        )
                        statuses.append(
                            SkuGenerationStatus(
                                sku_code=sku_code,
                                status="failed",
                                error_code=type(exc).__name__,
                                error_message="SKU profile generation failed; inspect server logs.",
                            )
                        )
                        status_updates[sku_code] = "failed"
                        self._update_progress(
                            request=request,
                            version_id=version.sellpoint_value_profile_version_id,
                            authoritative_sku_codes=sku_codes,
                            status_updates=status_updates,
                            checkpoint_sku_code=checkpoint,
                            processing_status="running",
                        )
                        self.repository.db.commit()

            final_processing = (
                "completed_with_errors"
                if any(row.status == "failed" for row in statuses)
                else "completed"
            )
            final_version = self._update_progress(
                request=request,
                version_id=version.sellpoint_value_profile_version_id,
                authoritative_sku_codes=sku_codes,
                status_updates=status_updates,
                checkpoint_sku_code=checkpoint,
                processing_status=final_processing,
            )
            self.repository.db.commit()
            return SellpointValueBatchGenerationResult(
                version=final_version,
                requested_sku_count=len(sku_codes),
                generated_count=sum(row.status == "generated" for row in statuses),
                reused_count=sum(row.status == "reused" for row in statuses),
                skipped_count=sum(row.status == "skipped" for row in statuses),
                failed_count=sum(row.status == "failed" for row in statuses),
                checkpoint_sku_code=checkpoint,
                statuses=statuses,
            )

    def get_profile(
        self,
        *,
        batch_id: str,
        profile_version: str,
        sku_code: str,
    ) -> SellpointValueProfileReadBundle | None:
        targets = self.repository.resolve_profile_targets(
            batch_id=batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
        )
        if not targets:
            return None
        return self.repository.get_profile(
            batch_id=batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
            rule_version=str(targets[0]["rule_version"]),
        )

    def list_profiles(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuSellpointValueProfileRecord]:
        return self.repository.list_profiles(
            sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
            limit=limit,
            offset=offset,
        )

    def diff_profiles(
        self,
        *,
        batch_id: str,
        sku_code: str,
        from_profile_version: str,
        to_profile_version: str,
    ) -> SellpointValueProfileDiff:
        before = self.get_profile(
            batch_id=batch_id,
            profile_version=from_profile_version,
            sku_code=sku_code,
        )
        after = self.get_profile(
            batch_id=batch_id,
            profile_version=to_profile_version,
            sku_code=sku_code,
        )
        if before is None or after is None:
            raise ValueError("both profile versions are required for diff")
        candidate_changes = _candidate_diff(before, after)
        investment_changes = _investment_diff(before, after)
        value_changes = _value_item_diff(before, after)
        payload = {
            "sku_code": sku_code,
            "from_profile_version": from_profile_version,
            "to_profile_version": to_profile_version,
            **candidate_changes,
            "investment_classification_changes": investment_changes,
            **value_changes,
            "price_role_changed": (
                before.profile.price_role_json != after.profile.price_role_json
            ),
            "pm_decisions_changed": (
                before.profile.pm_decisions_json != after.profile.pm_decisions_json
            ),
            "from_result_hash": before.profile.result_hash,
            "to_result_hash": after.profile.result_hash,
        }
        return SellpointValueProfileDiff(
            **payload,
            diff_hash=stable_hash(payload, version=PROFILE_DIFF_HASH_VERSION),
        )

    def _generate_one(
        self,
        request: SellpointValueVersionRequest,
        version: SellpointValueVersionRecord,
        sku_code: str,
    ) -> tuple[ProfileGenerationReadback, bool]:
        existing = self.get_profile(
            batch_id=request.batch_id,
            profile_version=request.profile_version,
            sku_code=sku_code,
        )
        source = self.input_provider.load_materialization_input(request, sku_code)
        _assert_request_matches_input(request, source, sku_code)
        materialized = materialize_sellpoint_value_profile(
            source,
            sellpoint_value_profile_version_id=(
                version.sellpoint_value_profile_version_id
            ),
        )
        persisted = self.repository.write_draft(
            materialized.persistence_bundle,
        )
        _verify_readback(materialized.persistence_bundle, persisted)
        return (
            ProfileGenerationReadback(
                profile=materialized.profile,
                persisted=persisted,
            ),
            existing is not None,
        )

    def _update_progress(
        self,
        *,
        request: SellpointValueVersionRequest,
        version_id: str,
        authoritative_sku_codes: Sequence[str],
        status_updates: dict[str, str],
        checkpoint_sku_code: str | None,
        processing_status: str,
    ) -> SellpointValueVersionRecord:
        version = self.repository.get_version(
            batch_id=request.batch_id,
            profile_version=request.profile_version,
            rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        )
        if version is None:
            raise ValueError("profile version disappeared during generation")
        previous = dict(
            (version.validation_summary_json or {}).get("sku_statuses") or {}
        )
        previous.update(status_updates)
        authoritative = set(authoritative_sku_codes)
        profiles = [
            row
            for row in self._all_profiles(version_id)
            if row.sku_code in authoritative
        ]
        ready_count = sum(
            row.analysis_state == "ready" and not row.review_required
            for row in profiles
        )
        blocked_count = sum(row.analysis_state == "blocked" for row in profiles)
        review_count = sum(
            row.review_required and row.analysis_state != "blocked"
            for row in profiles
        )
        failed_count = sum(
            status == "failed"
            for sku_code, status in previous.items()
            if sku_code in authoritative
        )
        if failed_count or blocked_count:
            quality = SellpointValueReleaseQualityStatus.BLOCKED
        elif review_count:
            quality = SellpointValueReleaseQualityStatus.LIMITED
        elif len(profiles) == len(authoritative):
            quality = SellpointValueReleaseQualityStatus.READY
        else:
            quality = SellpointValueReleaseQualityStatus.UNASSESSED
        needs_review = bool(failed_count or blocked_count or review_count)
        return self.repository.update_version_progress(
            sellpoint_value_profile_version_id=version_id,
            sku_count=len(authoritative),
            ready_count=ready_count,
            review_required_count=review_count,
            blocked_count=blocked_count,
            failed_count=failed_count,
            quality_summary_json={
                "release_quality_status": quality.value,
                "ready_count": ready_count,
                "review_required_count": review_count,
                "blocked_count": blocked_count,
                "failed_count": failed_count,
            },
            validation_summary_json={
                "checkpoint_sku_code": checkpoint_sku_code,
                "sku_statuses": dict(sorted(previous.items())),
            },
            release_quality_status=quality,
            processing_status=processing_status,
            review_required=needs_review,
            review_status=(
                "review_required" if needs_review else "auto_pass"
            ),
            review_reason_json={
                "reasons": [
                    reason
                    for reason, count in (
                        ("sku_generation_failed", failed_count),
                        ("sku_profile_blocked", blocked_count),
                        ("sku_profile_review_required", review_count),
                    )
                    if count
                ]
            },
        )

    def _all_profiles(
        self,
        version_id: str,
    ) -> list[SkuSellpointValueProfileRecord]:
        result = []
        offset = 0
        while True:
            page = self.repository.list_profiles(
                sellpoint_value_profile_version_id=version_id,
                limit=1000,
                offset=offset,
            )
            result.extend(page)
            if len(page) < 1000:
                return result
            offset += len(page)


def _assert_request_matches_input(
    request: SellpointValueVersionRequest,
    source: SellpointValueMaterializationInput,
    sku_code: str,
) -> None:
    for field_name in (
        "project_id",
        "category_code",
        "batch_id",
        "profile_version",
    ):
        if getattr(request, field_name) != getattr(source, field_name):
            raise ValueError(f"materialization input {field_name} does not match request")
    if source.target.sku_code != sku_code:
        raise ValueError("materialization input target does not match requested SKU")
    if source.method_versions != request.method_versions:
        raise ValueError("materialization method versions do not match request")


def _verify_readback(
    expected: object,
    actual: SellpointValueProfileReadBundle,
) -> None:
    expected_bundle = expected
    expected_profile = getattr(expected_bundle, "profile")
    if expected_profile.result_hash != actual.profile.result_hash:
        raise SellpointValueReadbackHashMismatchError(
            "profile result hash changed after persistence readback"
        )
    expected_candidates = {
        (row.candidate_sku_code, row.pool_type): row.result_hash
        for row in getattr(expected_bundle, "candidates")
    }
    actual_candidates = {
        (row.candidate_sku_code, row.pool_type): row.result_hash
        for row in actual.candidates
    }
    expected_items = {
        (row.battlefield_code, row.normalized_bundle_code): row.result_hash
        for row in getattr(expected_bundle, "value_items")
    }
    actual_items = {
        (row.battlefield_code, row.normalized_bundle_code): row.result_hash
        for row in actual.value_items
    }
    if expected_candidates != actual_candidates or expected_items != actual_items:
        raise SellpointValueReadbackHashMismatchError(
            "profile child hashes changed after persistence readback"
        )


def _candidate_diff(
    before: SellpointValueProfileReadBundle,
    after: SellpointValueProfileReadBundle,
) -> dict[str, object]:
    old = {
        f"{row.pool_type}:{row.candidate_sku_code}": row.eligibility_status
        for row in before.candidates
    }
    new = {
        f"{row.pool_type}:{row.candidate_sku_code}": row.eligibility_status
        for row in after.candidates
    }
    return {
        "candidate_added": sorted(set(new) - set(old)),
        "candidate_removed": sorted(set(old) - set(new)),
        "candidate_status_changes": [
            {
                "candidate_key": key,
                "from_status": old[key],
                "to_status": new[key],
            }
            for key in sorted(set(old) & set(new))
            if old[key] != new[key]
        ],
    }


def _investment_diff(
    before: SellpointValueProfileReadBundle,
    after: SellpointValueProfileReadBundle,
) -> list[dict[str, str | None]]:
    old = {
        str(row.get("capability_code")): str(row.get("classification"))
        for row in before.profile.investment_decisions_json
        if row.get("capability_code")
    }
    new = {
        str(row.get("capability_code")): str(row.get("classification"))
        for row in after.profile.investment_decisions_json
        if row.get("capability_code")
    }
    return [
        {
            "capability_code": code,
            "from_classification": old.get(code),
            "to_classification": new.get(code),
        }
        for code in sorted(set(old) | set(new))
        if old.get(code) != new.get(code)
    ]


def _value_item_diff(
    before: SellpointValueProfileReadBundle,
    after: SellpointValueProfileReadBundle,
) -> dict[str, list[str]]:
    old = {
        f"{row.battlefield_code}:{row.normalized_bundle_code}"
        for row in before.value_items
    }
    new = {
        f"{row.battlefield_code}:{row.normalized_bundle_code}"
        for row in after.value_items
    }
    return {
        "value_item_added": sorted(new - old),
        "value_item_removed": sorted(old - new),
    }


def _unique_codes(values: Sequence[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _lock_key(request: SellpointValueVersionRequest) -> str:
    return ":".join(
        (
            request.project_id,
            request.category_code,
            request.batch_id,
            request.profile_version,
        )
    )


__all__ = [
    "InMemoryProfileGenerationLock",
    "PROFILE_DIFF_HASH_VERSION",
    "ProfileGenerationLock",
    "SellpointValueGenerationAlreadyRunningError",
    "SellpointValueMaterializationInputProvider",
    "SellpointValueProfileLifecycleService",
    "SellpointValueReadbackHashMismatchError",
]
