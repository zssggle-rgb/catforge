"""Typed integrity layer for source-grounded V5.2 profile drafts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SellpointValueProfileReadBundle,
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SellpointValueVersionRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_config import (
    SellpointValueV51MethodConfig,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer import (
    build_v5_1_profile_input_fingerprint_from_profile,
    build_v5_1_profile_result_hash,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51CompetitorVersionSource,
    SellpointValueV51Profile,
    SellpointValueV51SourceLineage,
    SellpointValueV51Target,
    SellpointValueV51ValueInput,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_repository import (
    SellpointValueV51Repository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SellpointValueCandidatePools,
    SellpointValueCompetitorSource,
    SkuConclusionResult,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer import (
    build_v5_2_profile_input_fingerprint_from_profile,
    build_v5_2_profile_result_hash,
    project_v5_2_profile_to_persistence,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52Profile,
    SellpointValueV52Readback,
    SellpointValueV52SourceHashes,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    LayeredSellpointAnalysis,
    SPV_V5_2_METHOD_VERSION,
    SPV_V5_2_RULE_VERSION,
    SPV_V5_2_SCHEMA_VERSION,
    SourceSellpointReadResult,
)


class SellpointValueV52RepositoryError(RuntimeError):
    pass


class SellpointValueV52ReadbackIntegrityError(SellpointValueV52RepositoryError):
    pass


class SellpointValueV52Repository(SellpointValueV51Repository):
    """Persist only V5.2 drafts and prove the full layered graph on read."""

    def create_v5_2_version(
        self,
        payload: SellpointValueVersionDraftCreate,
        *,
        competitor_source: SellpointValueV51CompetitorVersionSource,
    ) -> SellpointValueVersionRecord:
        if (
            payload.schema_version != SPV_V5_2_SCHEMA_VERSION
            or payload.rule_version != SPV_V5_2_RULE_VERSION
            or payload.method_version != SPV_V5_2_METHOD_VERSION
        ):
            raise ValueError("V5.2 repository requires the V5.2 version contract")
        if (
            payload.source_competitor_profile_version_id
            != competitor_source.competitor_profile_version_id
            or payload.source_competitor_profile_method_version
            != competitor_source.method_version
            or payload.source_competitor_profile_result_hash
            != competitor_source.version_result_hash
        ):
            raise ValueError("V5.2 version must bind the competitor source")
        self._assert_competitor_version(competitor_source)
        return SellpointValueProfileRepository.create_version(self, payload)

    def write_v5_2_draft(
        self,
        bundle: SellpointValueDraftBundle,
    ) -> SellpointValueV52Readback:
        if bundle.profile.method_version != SPV_V5_2_METHOD_VERSION:
            raise ValueError("write_v5_2_draft accepts only V5.2 payloads")
        persisted = SellpointValueProfileRepository.write_draft(
            self,
            bundle,
            use_savepoint=True,
        )
        return self._validate_v5_2_readback(persisted)

    def get_v5_2_profile(
        self,
        *,
        batch_id: str,
        profile_version: str,
        sku_code: str,
    ) -> SellpointValueV52Readback | None:
        persisted = SellpointValueProfileRepository.get_profile(
            self,
            batch_id=batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
            rule_version=SPV_V5_2_RULE_VERSION,
        )
        return self._validate_v5_2_readback(persisted) if persisted else None

    def refresh_v5_2_version_progress(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        expected_sku_codes: Sequence[str],
        failed_sku_codes: Sequence[str] = (),
        validate_readbacks: bool = False,
    ) -> SellpointValueVersionRecord:
        expected = sorted(set(expected_sku_codes))
        if list(expected_sku_codes) != expected:
            raise ValueError("expected SKU codes must be sorted and unique")
        version = self._version_by_id(sellpoint_value_profile_version_id)
        if version.method_version != SPV_V5_2_METHOD_VERSION:
            raise ValueError("V5.2 progress requires a V5.2 version")
        previous_failed = set(
            (version.validation_summary_json or {}).get("failed_sku_codes", [])
        )
        progress = self.list_profile_progress(
            sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
            limit=1000,
        )
        generated = {row.sku_code for row in progress}
        unexpected = sorted(generated - set(expected))
        failed = sorted(
            (previous_failed | set(failed_sku_codes)) - generated
        )
        missing = sorted(set(expected) - generated - set(failed))
        statuses = Counter(row.conclusion_status for row in progress)
        integrity_errors = 0
        readback_error_codes: list[str] = []
        if validate_readbacks:
            for code in sorted(generated):
                try:
                    self.get_v5_2_profile(
                        batch_id=version.batch_id,
                        profile_version=version.profile_version,
                        sku_code=code,
                    )
                except (
                    ValidationError,
                    SellpointValueV52RepositoryError,
                    ValueError,
                ):
                    readback_error_codes.append(code)
            integrity_errors = len(readback_error_codes)
        completed = len(generated) + len(failed) >= len(expected)
        blocked = bool(
            failed
            or missing
            or unexpected
            or integrity_errors
            or statuses["invalid"]
        )
        limited = bool(
            statuses["partial_conclusion"] or statuses["no_conclusion"]
        )
        quality = (
            SellpointValueReleaseQualityStatus.BLOCKED
            if blocked
            else SellpointValueReleaseQualityStatus.LIMITED
            if limited
            else SellpointValueReleaseQualityStatus.READY
        )
        reasons = [
            reason
            for reason, active in (
                ("generation_failure", bool(failed)),
                ("missing_authoritative_sku", bool(missing)),
                ("unexpected_sku", bool(unexpected)),
                ("layer_integrity_error", bool(integrity_errors)),
                ("readback_validation_pending", completed and not validate_readbacks),
                ("invalid_sku", bool(statuses["invalid"])),
            )
            if active
        ]
        return self.update_version_progress(
            sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
            sku_count=len(expected),
            ready_count=statuses["conclusion_available"],
            review_required_count=0,
            blocked_count=statuses["invalid"],
            failed_count=len(failed),
            quality_summary_json={
                "release_quality_status": quality.value,
                "conclusion_available_count": statuses["conclusion_available"],
                "partial_conclusion_count": statuses["partial_conclusion"],
                "no_conclusion_count": statuses["no_conclusion"],
                "invalid_count": statuses["invalid"],
            },
            validation_summary_json={
                "expected_sku_codes": expected,
                "generated_sku_codes": sorted(generated),
                "failed_sku_codes": failed,
                "missing_sku_codes": missing,
                "unexpected_sku_codes": unexpected,
                "readback_error_sku_codes": readback_error_codes,
                "readback_validation_status": (
                    "completed" if validate_readbacks else "deferred"
                ),
            },
            release_quality_status=quality,
            processing_status=(
                "completed"
                if completed and (validate_readbacks or failed)
                else "validating"
                if completed
                else "running"
            ),
            review_required=bool(reasons),
            review_status="review_required" if reasons else "auto_pass",
            review_reason_json={"reasons": reasons} if reasons else {},
            conclusion_available_count=statuses["conclusion_available"],
            partial_conclusion_count=statuses["partial_conclusion"],
            no_conclusion_count=statuses["no_conclusion"],
            invalid_count=statuses["invalid"],
            integrity_error_count=integrity_errors + len(unexpected),
        )

    def _validate_v5_2_readback(
        self,
        persisted: SellpointValueProfileReadBundle,
    ) -> SellpointValueV52Readback:
        version = persisted.version
        row = persisted.profile
        if (
            version.method_version != SPV_V5_2_METHOD_VERSION
            or row.method_version != SPV_V5_2_METHOD_VERSION
            or row.schema_version != SPV_V5_2_SCHEMA_VERSION
            or row.rule_version != SPV_V5_2_RULE_VERSION
        ):
            raise SellpointValueV52ReadbackIntegrityError(
                "typed V5.2 readback requires the V5.2 contract"
            )
        try:
            profile = _reconstruct_v5_2_profile(persisted)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 typed payload reconstruction failed"
            ) from exc
        if build_v5_1_profile_input_fingerprint_from_profile(
            profile.base_profile
        ) != profile.base_profile.input_fingerprint:
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 base profile input fingerprint mismatch"
            )
        if (
            build_v5_1_profile_result_hash(profile.base_profile)
            != profile.base_profile.result_hash
        ):
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 base profile result hash mismatch"
            )
        if (
            build_v5_2_profile_input_fingerprint_from_profile(profile)
            != profile.input_fingerprint
        ):
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 profile input fingerprint mismatch"
            )
        if build_v5_2_profile_result_hash(profile) != profile.result_hash:
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 profile result hash mismatch"
            )
        integrity = profile.layered_sellpoint_analysis.integrity
        if any(
            (
                integrity.unsourced_sellpoint_count,
                integrity.parameter_as_sellpoint_count,
                integrity.value_theme_as_sellpoint_count,
                integrity.exact_quote_mismatch_count,
                integrity.dangling_sellpoint_link_count,
                integrity.source_profile_hash_mismatch_count,
            )
        ):
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 layered sellpoint integrity failed"
            )
        source = profile.base_profile.competitor_source
        self._assert_competitor_version(
            SellpointValueV51CompetitorVersionSource(
                access_mode=source.access_mode,
                competitor_profile_version_id=source.competitor_profile_version_id,
                profile_version=source.profile_version,
                method_version=source.method_version,
                release_status=source.release_status,
                is_current=source.is_current,
                release_scope_key=source.release_scope_key,
                version_result_hash=source.source_version_result_hash,
            )
        )
        candidate_hashes = (version.source_scope_json or {}).get(
            "candidate_pool_hashes", {}
        )
        if candidate_hashes.get(row.sku_code) != (
            profile.base_profile.candidate_pools.result_hash
        ):
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 candidate pool hash does not match version scope"
            )
        source_hashes = (version.source_scope_json or {}).get(
            "source_hashes_by_sku", {}
        )
        if source_hashes.get(row.sku_code) != profile.source_hashes.model_dump(
            mode="json"
        ):
            raise SellpointValueV52ReadbackIntegrityError(
                "V5.2 source hash manifest changed after version creation"
            )
        expected = project_v5_2_profile_to_persistence(
            profile,
            sellpoint_value_profile_version_id=(
                version.sellpoint_value_profile_version_id
            ),
        )
        _assert_projection_matches(expected, persisted)
        return SellpointValueV52Readback(profile=profile, persisted=persisted)


def _reconstruct_v5_2_profile(
    persisted: SellpointValueProfileReadBundle,
) -> SellpointValueV52Profile:
    row = persisted.profile
    source_rows = row.source_lineage_json or []
    competitor_sources = [
        item.get("payload")
        for item in source_rows
        if item.get("record_type") == "competitor_source"
    ]
    lineage = [
        item.get("payload")
        for item in source_rows
        if item.get("record_type") == "source_lineage"
    ]
    m04c = [
        item.get("payload")
        for item in source_rows
        if item.get("record_type") == "m04c_source_sellpoints"
    ]
    if (
        len(competitor_sources) != 1
        or len(m04c) != 1
        or any(item is None for item in lineage)
    ):
        raise SellpointValueV52ReadbackIntegrityError(
            "V5.2 source lineage envelope is incomplete"
        )
    pm = row.pm_decisions_json or {}
    if pm.get("record_type") != "sku_conclusion":
        raise SellpointValueV52ReadbackIntegrityError(
            "V5.2 SKU conclusion envelope is incomplete"
        )
    base_meta = _required_mapping(pm, "v5_1_base_profile_meta")
    base = SellpointValueV51Profile(
        project_id=row.project_id,
        category_code=row.category_code,
        batch_id=row.batch_id,
        release_scope_key=competitor_sources[0]["release_scope_key"],
        profile_version=row.profile_version,
        target=SellpointValueV51Target(
            sku_code=row.sku_code,
            model_code=row.model_code,
            model_name=row.model_name,
            brand_name=row.brand_name,
            display_name_cn=row.display_name_cn,
        ),
        competitor_source=SellpointValueCompetitorSource.model_validate(
            competitor_sources[0]
        ),
        candidate_pools=SellpointValueCandidatePools.model_validate(
            _required_envelope(
                row.candidate_universe_summary_json,
                "candidate_pools",
            )
        ),
        method_config=SellpointValueV51MethodConfig.model_validate(
            _required_envelope(row.threshold_summary_json, "method_config")
        ),
        source_lineage=[
            SellpointValueV51SourceLineage.model_validate(item)
            for item in lineage
        ],
        values=[
            SellpointValueV51ValueInput.model_validate(item["payload"])
            for item in row.question_analyses_json or []
            if item.get("record_type") == "value_analysis"
        ],
        sku_conclusion=SkuConclusionResult.model_validate(pm["payload"]),
        evidence_refs=base_meta["evidence_refs"],
        limitations=base_meta["limitations"],
        input_fingerprint=base_meta["input_fingerprint"],
        result_hash=base_meta["result_hash"],
    )
    return SellpointValueV52Profile(
        base_profile=base,
        source_hashes=SellpointValueV52SourceHashes.model_validate(
            _required_mapping(pm, "source_hashes")
        ),
        source_sellpoints=SourceSellpointReadResult.model_validate(m04c[0]),
        layered_sellpoint_analysis=LayeredSellpointAnalysis.model_validate(
            _required_mapping(pm, "layered_sellpoint_analysis")
        ),
        input_fingerprint=row.input_fingerprint,
        result_hash=row.result_hash,
    )


def _required_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    result = value.get(key)
    if not isinstance(result, Mapping):
        raise SellpointValueV52ReadbackIntegrityError(
            f"V5.2 {key} payload is incomplete"
        )
    return result


def _required_envelope(value: Mapping[str, Any], record_type: str) -> Any:
    if value.get("record_type") != record_type or value.get("payload") is None:
        raise SellpointValueV52ReadbackIntegrityError(
            f"V5.2 {record_type} envelope is incomplete"
        )
    return value["payload"]


def _assert_projection_matches(
    expected: SellpointValueDraftBundle,
    actual: SellpointValueProfileReadBundle,
) -> None:
    _assert_model_projection(
        expected.profile,
        actual.profile,
        exclude={
            "sku_sellpoint_value_profile_id",
            "generated_at",
            "created_at",
            "updated_at",
            "release_status",
            "is_current",
        },
    )
    expected_candidates = {
        (row.pool_type, row.candidate_sku_code): row
        for row in expected.candidates
    }
    actual_candidates = {
        (row.pool_type, row.candidate_sku_code): row
        for row in actual.candidates
    }
    expected_values = {
        (row.battlefield_code, row.normalized_bundle_code): row
        for row in expected.value_items
    }
    actual_values = {
        (row.battlefield_code, row.normalized_bundle_code): row
        for row in actual.value_items
    }
    if set(expected_candidates) != set(actual_candidates) or set(
        expected_values
    ) != set(actual_values):
        raise SellpointValueV52ReadbackIntegrityError(
            "V5.2 child identity set contains missing or dangling rows"
        )
    for key, expected_row in expected_candidates.items():
        _assert_model_projection(
            expected_row,
            actual_candidates[key],
            exclude={
                "sku_sellpoint_value_candidate_id",
                "sku_sellpoint_value_profile_id",
                "created_at",
                "updated_at",
                "release_status",
                "is_current",
            },
        )
    for key, expected_row in expected_values.items():
        _assert_model_projection(
            expected_row,
            actual_values[key],
            exclude={
                "sku_sellpoint_value_item_id",
                "sku_sellpoint_value_profile_id",
                "created_at",
                "updated_at",
                "release_status",
                "is_current",
            },
        )


def _assert_model_projection(expected: Any, actual: Any, *, exclude: set[str]) -> None:
    actual_payload = actual.model_dump(mode="python", exclude=exclude)
    for key, value in expected.model_dump(mode="python").items():
        if key in {"release_status", "is_current"}:
            continue
        if actual_payload.get(key) != value:
            raise SellpointValueV52ReadbackIntegrityError(
                f"V5.2 persisted projection mismatch: {key}"
            )


__all__ = [
    "SellpointValueV52ReadbackIntegrityError",
    "SellpointValueV52Repository",
    "SellpointValueV52RepositoryError",
]
