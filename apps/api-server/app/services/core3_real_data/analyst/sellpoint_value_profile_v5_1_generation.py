"""Serial generation service for immutable sellpoint-value V5.1 drafts."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator, Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SellpointValueVersionRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer import (
    materialize_sellpoint_value_profile_v5_1,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51BatchGenerationResult,
    SellpointValueV51InputProvider,
    SellpointValueV51MaterializationInput,
    SellpointValueV51Readback,
    SellpointValueV51SkuGenerationStatus,
    SellpointValueV51VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_repository import (
    SellpointValueV51Repository,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_VERSION_INPUT_HASH_VERSION = "sellpoint_value_version_input_v5_1"
SPV_V5_1_VERSION_CANDIDATE_HASH_VERSION = "sellpoint_value_version_candidates_v5_1"
SPV_V5_1_VERSION_RESULT_HASH_VERSION = "sellpoint_value_version_result_v5_1"


class SellpointValueV51GenerationAlreadyRunningError(RuntimeError):
    pass


class SellpointValueV51GenerationLock:
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


def build_v5_1_version_input_fingerprint(
    request: SellpointValueV51VersionRequest,
) -> str:
    return stable_hash(
        {
            "schema_version": SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
            "rule_version": SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
            "method_version": SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
            "project_id": request.project_id,
            "category_code": request.category_code,
            "batch_id": request.batch_id,
            "profile_version": request.profile_version,
            "competitor_source": request.competitor_source.model_dump(mode="json"),
            "expected_sku_codes": sorted(request.expected_sku_codes),
            "candidate_pool_hashes": dict(
                sorted(request.candidate_pool_hashes.items())
            ),
            "method_config": request.method_config.model_dump(mode="json"),
            "method_versions": dict(sorted(request.method_versions.items())),
            "source_lineage": [
                row.model_dump(mode="json")
                for row in sorted(
                    request.source_lineage,
                    key=lambda item: item.source_code,
                )
            ],
        },
        version=SPV_V5_1_VERSION_INPUT_HASH_VERSION,
    )


def build_v5_1_candidate_universe_fingerprint(
    request: SellpointValueV51VersionRequest,
) -> str:
    return stable_hash(
        dict(sorted(request.candidate_pool_hashes.items())),
        version=SPV_V5_1_VERSION_CANDIDATE_HASH_VERSION,
    )


def build_v5_1_version_result_hash(
    request: SellpointValueV51VersionRequest,
) -> str:
    return stable_hash(
        {
            "input_fingerprint": build_v5_1_version_input_fingerprint(request),
            "candidate_universe_fingerprint": (
                build_v5_1_candidate_universe_fingerprint(request)
            ),
            "competitor_version_result_hash": (
                request.competitor_source.version_result_hash
            ),
        },
        version=SPV_V5_1_VERSION_RESULT_HASH_VERSION,
    )


class SellpointValueV51GenerationService:
    def __init__(
        self,
        *,
        repository: SellpointValueV51Repository,
        input_provider: SellpointValueV51InputProvider,
        generation_lock: SellpointValueV51GenerationLock | None = None,
    ) -> None:
        self.repository = repository
        self.input_provider = input_provider
        self.generation_lock = generation_lock or SellpointValueV51GenerationLock()

    def ensure_version(
        self,
        request: SellpointValueV51VersionRequest,
    ) -> SellpointValueVersionRecord:
        source = request.competitor_source
        version = self.repository.create_v5_1_version(
            SellpointValueVersionDraftCreate(
                project_id=request.project_id,
                category_code=request.category_code,
                batch_id=request.batch_id,
                product_category=request.category_code,
                profile_version=request.profile_version,
                schema_version=SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
                rule_version=SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
                method_version=SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
                method_versions_json=dict(sorted(request.method_versions.items())),
                source_competitor_profile_version_id=(
                    source.competitor_profile_version_id
                ),
                source_competitor_profile_method_version=source.method_version,
                source_competitor_profile_result_hash=source.version_result_hash,
                release_quality_status=SellpointValueReleaseQualityStatus.UNASSESSED,
                generated_by=request.generated_by,
                source_batch_ids_json=[request.batch_id],
                source_scope_json={
                    "release_scope_key": source.release_scope_key,
                    "competitor_source": source.model_dump(mode="json"),
                    "expected_sku_codes": request.expected_sku_codes,
                    "candidate_pool_hashes": dict(
                        sorted(request.candidate_pool_hashes.items())
                    ),
                    "source_lineage": [
                        row.model_dump(mode="json") for row in request.source_lineage
                    ],
                },
                sku_count=len(request.expected_sku_codes),
                conclusion_available_count=0,
                partial_conclusion_count=0,
                no_conclusion_count=0,
                invalid_count=0,
                integrity_error_count=0,
                input_fingerprint=build_v5_1_version_input_fingerprint(request),
                candidate_universe_fingerprint=(
                    build_v5_1_candidate_universe_fingerprint(request)
                ),
                result_hash=build_v5_1_version_result_hash(request),
                processing_status="pending",
            ),
            competitor_source=source,
        )
        self.repository.db.commit()
        return version

    def generate_draft(
        self,
        request: SellpointValueV51VersionRequest,
        *,
        sku_code: str,
    ) -> SellpointValueV51Readback:
        if sku_code not in request.expected_sku_codes:
            raise ValueError("SKU is outside the V5.1 authoritative scope")
        version = self.ensure_version(request)
        key = _lock_key(request)
        with self.generation_lock.acquire(key) as acquired:
            if not acquired:
                raise SellpointValueV51GenerationAlreadyRunningError(
                    f"V5.1 generation already running: {key}"
                )
            readback, _ = self._generate_one(request, version, sku_code)
            self.repository.refresh_v5_1_version_progress(
                sellpoint_value_profile_version_id=(
                    version.sellpoint_value_profile_version_id
                ),
                expected_sku_codes=request.expected_sku_codes,
            )
            self.repository.db.commit()
        final = self.repository.get_v5_1_profile(
            batch_id=request.batch_id,
            profile_version=request.profile_version,
            sku_code=sku_code,
        )
        if final is None or final.profile.result_hash != readback.profile.result_hash:
            raise RuntimeError("V5.1 profile disappeared after generation commit")
        return final

    def generate_many(
        self,
        request: SellpointValueV51VersionRequest,
        *,
        sku_codes: Sequence[str] | None = None,
    ) -> SellpointValueV51BatchGenerationResult:
        requested = sorted(set(sku_codes or request.expected_sku_codes))
        if not set(requested).issubset(request.expected_sku_codes):
            raise ValueError("requested SKU codes exceed the V5.1 authoritative scope")
        version = self.ensure_version(request)
        statuses: list[SellpointValueV51SkuGenerationStatus] = []
        failed: list[str] = []
        key = _lock_key(request)
        with self.generation_lock.acquire(key) as acquired:
            if not acquired:
                raise SellpointValueV51GenerationAlreadyRunningError(
                    f"V5.1 generation already running: {key}"
                )
            for sku_code in requested:
                try:
                    readback, reused = self._generate_one(
                        request,
                        version,
                        sku_code,
                    )
                    self.repository.db.commit()
                    statuses.append(
                        SellpointValueV51SkuGenerationStatus(
                            sku_code=sku_code,
                            status="reused" if reused else "generated",
                            profile_result_hash=readback.profile.result_hash,
                        )
                    )
                except Exception as exc:  # one failed SKU must not stop the batch
                    self.repository.db.commit()
                    failed.append(sku_code)
                    statuses.append(
                        SellpointValueV51SkuGenerationStatus(
                            sku_code=sku_code,
                            status="failed",
                            error_code=exc.__class__.__name__,
                            error_message=_safe_error_message(exc),
                        )
                    )
            final_version = self.repository.refresh_v5_1_version_progress(
                sellpoint_value_profile_version_id=(
                    version.sellpoint_value_profile_version_id
                ),
                expected_sku_codes=request.expected_sku_codes,
                failed_sku_codes=failed,
            )
            self.repository.db.commit()
        return SellpointValueV51BatchGenerationResult(
            version=final_version,
            statuses=statuses,
            generated_count=sum(row.status == "generated" for row in statuses),
            reused_count=sum(row.status == "reused" for row in statuses),
            failed_count=sum(row.status == "failed" for row in statuses),
        )

    def _generate_one(
        self,
        request: SellpointValueV51VersionRequest,
        version: SellpointValueVersionRecord,
        sku_code: str,
    ) -> tuple[SellpointValueV51Readback, bool]:
        source = self.input_provider.load_materialization_input(request, sku_code)
        _assert_input_matches_request(request, source, sku_code)
        existing = self.repository.get_v5_1_profile(
            batch_id=request.batch_id,
            profile_version=request.profile_version,
            sku_code=sku_code,
        )
        with self.repository.db.begin_nested():
            materialized = materialize_sellpoint_value_profile_v5_1(
                source,
                sellpoint_value_profile_version_id=(
                    version.sellpoint_value_profile_version_id
                ),
            )
            readback = self.repository.write_v5_1_draft(materialized.persistence_bundle)
            if readback.profile.model_dump(mode="json") != (
                materialized.profile.model_dump(mode="json")
            ):
                raise RuntimeError("V5.1 typed readback changed after persistence")
        return readback, existing is not None


def _assert_input_matches_request(
    request: SellpointValueV51VersionRequest,
    source: SellpointValueV51MaterializationInput,
    sku_code: str,
) -> None:
    if (
        source.project_id != request.project_id
        or source.category_code != request.category_code
        or source.batch_id != request.batch_id
        or source.profile_version != request.profile_version
        or source.release_scope_key != request.competitor_source.release_scope_key
        or source.target.sku_code != sku_code
    ):
        raise ValueError("V5.1 materialization input does not match request scope")
    competitor = source.competitor_source
    version_source = request.competitor_source
    if (
        competitor.competitor_profile_version_id
        != version_source.competitor_profile_version_id
        or competitor.profile_version != version_source.profile_version
        or competitor.method_version != version_source.method_version
        or competitor.access_mode != version_source.access_mode
        or competitor.release_status != version_source.release_status
        or competitor.is_current != version_source.is_current
        or competitor.source_version_result_hash != version_source.version_result_hash
    ):
        raise ValueError("V5.1 SKU source does not match the locked competitor version")
    if request.candidate_pool_hashes[sku_code] != source.candidate_pools.result_hash:
        raise ValueError("V5.1 candidate pool hash changed after version creation")
    if source.method_config != request.method_config:
        raise ValueError("V5.1 method config changed after version creation")


def _lock_key(request: SellpointValueV51VersionRequest) -> str:
    return ":".join(
        (
            request.project_id,
            request.category_code,
            request.batch_id,
            request.profile_version,
        )
    )


def _safe_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return message[:320]


__all__ = [
    "SPV_V5_1_VERSION_CANDIDATE_HASH_VERSION",
    "SPV_V5_1_VERSION_INPUT_HASH_VERSION",
    "SPV_V5_1_VERSION_RESULT_HASH_VERSION",
    "SellpointValueV51GenerationAlreadyRunningError",
    "SellpointValueV51GenerationLock",
    "SellpointValueV51GenerationService",
    "build_v5_1_candidate_universe_fingerprint",
    "build_v5_1_version_input_fingerprint",
    "build_v5_1_version_result_hash",
]
