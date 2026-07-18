"""Serial generation service for immutable sellpoint-value V5.2 drafts."""

from __future__ import annotations

from typing import Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SellpointValueVersionRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SellpointValueV51GenerationAlreadyRunningError,
    SellpointValueV51GenerationLock,
    build_v5_1_candidate_universe_fingerprint,
    build_v5_1_version_input_fingerprint,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer import (
    build_v5_2_source_hashes,
    materialize_sellpoint_value_profile_v5_2,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52BatchGenerationResult,
    SellpointValueV52InputProvider,
    SellpointValueV52MaterializationInput,
    SellpointValueV52Readback,
    SellpointValueV52SkuGenerationStatus,
    SellpointValueV52VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_repository import (
    SellpointValueV52Repository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    SPV_V5_2_METHOD_VERSION,
    SPV_V5_2_RULE_VERSION,
    SPV_V5_2_SCHEMA_VERSION,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_2_VERSION_INPUT_HASH_VERSION = "sellpoint_value_version_input_v5_2"
SPV_V5_2_VERSION_RESULT_HASH_VERSION = "sellpoint_value_version_result_v5_2"


def build_v5_2_version_input_fingerprint(
    request: SellpointValueV52VersionRequest,
) -> str:
    return stable_hash(
        {
            "schema_version": SPV_V5_2_SCHEMA_VERSION,
            "rule_version": SPV_V5_2_RULE_VERSION,
            "method_version": SPV_V5_2_METHOD_VERSION,
            "base_version_input_fingerprint": (
                build_v5_1_version_input_fingerprint(request.base)
            ),
            "source_hashes_by_sku": {
                code: hashes.model_dump(mode="json")
                for code, hashes in request.source_hashes_by_sku.items()
            },
        },
        version=SPV_V5_2_VERSION_INPUT_HASH_VERSION,
    )


def build_v5_2_version_result_hash(
    request: SellpointValueV52VersionRequest,
) -> str:
    return stable_hash(
        {
            "input_fingerprint": build_v5_2_version_input_fingerprint(request),
            "candidate_universe_fingerprint": (
                build_v5_1_candidate_universe_fingerprint(request.base)
            ),
            "competitor_version_result_hash": (
                request.base.competitor_source.version_result_hash
            ),
        },
        version=SPV_V5_2_VERSION_RESULT_HASH_VERSION,
    )


class SellpointValueV52GenerationService:
    def __init__(
        self,
        *,
        repository: SellpointValueV52Repository,
        input_provider: SellpointValueV52InputProvider,
        generation_lock: SellpointValueV51GenerationLock | None = None,
    ) -> None:
        self.repository = repository
        self.input_provider = input_provider
        self.generation_lock = generation_lock or SellpointValueV51GenerationLock()

    def ensure_version(
        self,
        request: SellpointValueV52VersionRequest,
    ) -> SellpointValueVersionRecord:
        base = request.base
        competitor = base.competitor_source
        version = self.repository.create_v5_2_version(
            SellpointValueVersionDraftCreate(
                project_id=base.project_id,
                category_code=base.category_code,
                batch_id=base.batch_id,
                product_category=base.category_code,
                profile_version=base.profile_version,
                schema_version=SPV_V5_2_SCHEMA_VERSION,
                rule_version=SPV_V5_2_RULE_VERSION,
                method_version=SPV_V5_2_METHOD_VERSION,
                method_versions_json={
                    **dict(sorted(base.method_versions.items())),
                    "layer_mapping": "sellpoint_value_layer_mapping_v5_2",
                    "source_sellpoint_reader": "m04c_source_sellpoint_reader_v5_2",
                },
                source_competitor_profile_version_id=(
                    competitor.competitor_profile_version_id
                ),
                source_competitor_profile_method_version=competitor.method_version,
                source_competitor_profile_result_hash=(
                    competitor.version_result_hash
                ),
                release_quality_status=SellpointValueReleaseQualityStatus.UNASSESSED,
                generated_by=base.generated_by,
                source_batch_ids_json=[base.batch_id],
                source_scope_json={
                    "release_scope_key": competitor.release_scope_key,
                    "competitor_source": competitor.model_dump(mode="json"),
                    "expected_sku_codes": base.expected_sku_codes,
                    "candidate_pool_hashes": dict(
                        sorted(base.candidate_pool_hashes.items())
                    ),
                    "source_hashes_by_sku": {
                        code: hashes.model_dump(mode="json")
                        for code, hashes in request.source_hashes_by_sku.items()
                    },
                },
                sku_count=len(base.expected_sku_codes),
                conclusion_available_count=0,
                partial_conclusion_count=0,
                no_conclusion_count=0,
                invalid_count=0,
                integrity_error_count=0,
                input_fingerprint=build_v5_2_version_input_fingerprint(request),
                candidate_universe_fingerprint=(
                    build_v5_1_candidate_universe_fingerprint(base)
                ),
                result_hash=build_v5_2_version_result_hash(request),
                processing_status="pending",
            ),
            competitor_source=competitor,
        )
        self.repository.db.commit()
        return version

    def generate_draft(
        self,
        request: SellpointValueV52VersionRequest,
        *,
        sku_code: str,
    ) -> SellpointValueV52Readback:
        base = request.base
        if sku_code not in base.expected_sku_codes:
            raise ValueError("SKU is outside the V5.2 authoritative scope")
        version = self.ensure_version(request)
        with self.generation_lock.acquire(_lock_key(request)) as acquired:
            if not acquired:
                raise SellpointValueV51GenerationAlreadyRunningError(
                    f"V5.2 generation already running: {_lock_key(request)}"
                )
            readback, _ = self._generate_one(request, version, sku_code)
            self.repository.refresh_v5_2_version_progress(
                sellpoint_value_profile_version_id=(
                    version.sellpoint_value_profile_version_id
                ),
                expected_sku_codes=base.expected_sku_codes,
                validate_readbacks=True,
            )
            self.repository.db.commit()
        final = self.repository.get_v5_2_profile(
            batch_id=base.batch_id,
            profile_version=base.profile_version,
            sku_code=sku_code,
        )
        if final is None or final.profile.result_hash != readback.profile.result_hash:
            raise RuntimeError("V5.2 profile disappeared after generation commit")
        return final

    def generate_many(
        self,
        request: SellpointValueV52VersionRequest,
        *,
        sku_codes: Sequence[str] | None = None,
    ) -> SellpointValueV52BatchGenerationResult:
        base = request.base
        requested = sorted(set(sku_codes or base.expected_sku_codes))
        if not set(requested).issubset(base.expected_sku_codes):
            raise ValueError("requested SKU codes exceed V5.2 authoritative scope")
        version = self.ensure_version(request)
        statuses: list[SellpointValueV52SkuGenerationStatus] = []
        failed: list[str] = []
        with self.generation_lock.acquire(_lock_key(request)) as acquired:
            if not acquired:
                raise SellpointValueV51GenerationAlreadyRunningError(
                    f"V5.2 generation already running: {_lock_key(request)}"
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
                        SellpointValueV52SkuGenerationStatus(
                            sku_code=sku_code,
                            status="reused" if reused else "generated",
                            profile_result_hash=readback.profile.result_hash,
                        )
                    )
                except Exception as exc:  # one SKU must not stop the batch
                    self.repository.db.commit()
                    failed.append(sku_code)
                    statuses.append(
                        SellpointValueV52SkuGenerationStatus(
                            sku_code=sku_code,
                            status="failed",
                            error_code=exc.__class__.__name__,
                            error_message=_safe_error_message(exc),
                        )
                    )
            final_version = self.repository.refresh_v5_2_version_progress(
                sellpoint_value_profile_version_id=(
                    version.sellpoint_value_profile_version_id
                ),
                expected_sku_codes=base.expected_sku_codes,
                failed_sku_codes=failed,
                validate_readbacks=(
                    not failed
                    and requested == base.expected_sku_codes
                ),
            )
            self.repository.db.commit()
        return SellpointValueV52BatchGenerationResult(
            version=final_version,
            statuses=statuses,
            generated_count=sum(row.status == "generated" for row in statuses),
            reused_count=sum(row.status == "reused" for row in statuses),
            failed_count=sum(row.status == "failed" for row in statuses),
        )

    def _generate_one(
        self,
        request: SellpointValueV52VersionRequest,
        version: SellpointValueVersionRecord,
        sku_code: str,
    ) -> tuple[SellpointValueV52Readback, bool]:
        source = self.input_provider.load_materialization_input(request, sku_code)
        _assert_input_matches_request(request, source, sku_code)
        base = request.base
        existing = self.repository.get_v5_2_profile(
            batch_id=base.batch_id,
            profile_version=base.profile_version,
            sku_code=sku_code,
        )
        with self.repository.db.begin_nested():
            materialized = materialize_sellpoint_value_profile_v5_2(
                source,
                sellpoint_value_profile_version_id=(
                    version.sellpoint_value_profile_version_id
                ),
            )
            readback = self.repository.write_v5_2_draft(
                materialized.persistence_bundle
            )
            if readback.profile.model_dump(mode="json") != (
                materialized.profile.model_dump(mode="json")
            ):
                raise RuntimeError("V5.2 typed readback changed after persistence")
        return readback, existing is not None


def _assert_input_matches_request(
    request: SellpointValueV52VersionRequest,
    source: SellpointValueV52MaterializationInput,
    sku_code: str,
) -> None:
    base = request.base
    source_base = source.base
    if (
        source_base.project_id != base.project_id
        or source_base.category_code != base.category_code
        or source_base.batch_id != base.batch_id
        or source_base.profile_version != base.profile_version
        or source_base.target.sku_code != sku_code
        or source_base.release_scope_key != base.competitor_source.release_scope_key
    ):
        raise ValueError("V5.2 materialization input does not match request scope")
    if source_base.candidate_pools.result_hash != base.candidate_pool_hashes[sku_code]:
        raise ValueError("V5.2 candidate pool hash changed after version creation")
    if build_v5_2_source_hashes(source) != request.source_hashes_by_sku[sku_code]:
        raise ValueError("V5.2 upstream source hashes changed after version creation")


def _lock_key(request: SellpointValueV52VersionRequest) -> str:
    base = request.base
    return ":".join(
        (base.project_id, base.category_code, base.batch_id, base.profile_version)
    )


def _safe_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    return message[:320]


__all__ = [
    "SPV_V5_2_VERSION_INPUT_HASH_VERSION",
    "SPV_V5_2_VERSION_RESULT_HASH_VERSION",
    "SellpointValueV52GenerationService",
    "build_v5_2_version_input_fingerprint",
    "build_v5_2_version_result_hash",
]
