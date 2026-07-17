"""V5.1 integrity layer over the existing sellpoint-value profile tables."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterator, Mapping, Sequence

from pydantic import ValidationError
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_V5_1_COMPETITOR_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION,
    SellpointValueDraftBundle,
    SellpointValueProfileReadBundle,
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SellpointValueVersionRecord,
    SkuSellpointValueCandidateRecord,
    SkuSellpointValueItemRecord,
    SkuSellpointValueProfileRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
    SellpointValueProfileRepositoryError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer import (
    build_v5_1_profile_input_fingerprint_from_profile,
    build_v5_1_profile_result_hash,
    project_v5_1_profile_to_persistence,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51CompetitorVersionSource,
    SellpointValueV51Profile,
    SellpointValueV51Readback,
    SellpointValueV51SourceLineage,
    SellpointValueV51Target,
    SellpointValueV51ValueInput,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    CandidateSourceType,
    SellpointValueCandidatePools,
    SellpointValueCompetitorSource,
    SkuConclusionResult,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_config import (
    SellpointValueV51MethodConfig,
)


class SellpointValueV51RepositoryError(SellpointValueProfileRepositoryError):
    pass


class SellpointValueV51SourceIntegrityError(SellpointValueV51RepositoryError):
    pass


class SellpointValueV51ReadbackIntegrityError(SellpointValueV51RepositoryError):
    pass


SPV_V5_1_PROGRESS_READ_PAGE_SIZE = 64


class SellpointValueV51Repository(SellpointValueProfileRepository):
    """Persist only V5.1 drafts and prove their typed graph on every readback."""

    def create_v5_1_version(
        self,
        payload: SellpointValueVersionDraftCreate,
        *,
        competitor_source: SellpointValueV51CompetitorVersionSource,
    ) -> SellpointValueVersionRecord:
        _assert_v5_1_version_payload(payload, competitor_source)
        self._assert_competitor_version(competitor_source)
        return super().create_version(payload)

    def write_v5_1_draft(
        self,
        bundle: SellpointValueDraftBundle,
    ) -> SellpointValueV51Readback:
        if bundle.profile.method_version != SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION:
            raise ValueError("write_v5_1_draft accepts only V5.1 payloads")
        persisted = super().write_draft(bundle, use_savepoint=True)
        return self._validate_v5_1_readback(persisted)

    def get_v5_1_profile(
        self,
        *,
        batch_id: str,
        profile_version: str,
        sku_code: str,
    ) -> SellpointValueV51Readback | None:
        persisted = super().get_profile(
            batch_id=batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
            rule_version=SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION,
        )
        return self._validate_v5_1_readback(persisted) if persisted else None

    def refresh_v5_1_version_progress(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        expected_sku_codes: Sequence[str],
        failed_sku_codes: Sequence[str] = (),
    ) -> SellpointValueVersionRecord:
        expected = sorted(set(expected_sku_codes))
        failed = sorted(set(failed_sku_codes))
        if list(expected_sku_codes) != expected:
            raise ValueError("expected SKU codes must be sorted and unique")
        if not set(failed).issubset(expected):
            raise ValueError("failed SKU codes must stay in the expected scope")
        version = self._version_by_id(sellpoint_value_profile_version_id)
        if version.method_version != SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION:
            raise ValueError("V5.1 progress cannot update a historical V5 version")
        generated_codes: list[str] = []
        hash_or_reference_errors: list[str] = []
        statuses: Counter[str] = Counter()
        for row, persisted in self._iter_v5_1_read_bundles(version):
            generated_codes.append(row.sku_code)
            statuses[row.conclusion_status] += 1
            try:
                self._validate_v5_1_readback(persisted)
            except (ValidationError, SellpointValueV51RepositoryError, ValueError):
                hash_or_reference_errors.append(row.sku_code)
        unexpected_codes = sorted(set(generated_codes) - set(expected))
        local_review_count = int(
            self.db.scalar(
                select(func.count())
                .select_from(entities.Core3SkuSellpointValueItem)
                .where(
                    entities.Core3SkuSellpointValueItem.sellpoint_value_profile_version_id
                    == sellpoint_value_profile_version_id
                )
                .where(entities.Core3SkuSellpointValueItem.review_required.is_(True))
            )
            or 0
        )
        missing_codes = sorted(set(expected) - set(generated_codes) - set(failed))
        integrity_error_count = len(unexpected_codes) + len(hash_or_reference_errors)
        blocking = bool(
            failed
            or missing_codes
            or unexpected_codes
            or hash_or_reference_errors
            or statuses["invalid"]
        )
        limited = bool(
            statuses["partial_conclusion"]
            or statuses["no_conclusion"]
            or local_review_count
        )
        quality = (
            SellpointValueReleaseQualityStatus.BLOCKED
            if blocking
            else SellpointValueReleaseQualityStatus.LIMITED
            if limited
            else SellpointValueReleaseQualityStatus.READY
        )
        completed = len(generated_codes) + len(failed) >= len(expected)
        reasons = [
            reason
            for reason, active in (
                ("generation_failure", bool(failed)),
                ("missing_authoritative_sku", bool(missing_codes)),
                ("unexpected_sku", bool(unexpected_codes)),
                ("readback_integrity_error", bool(hash_or_reference_errors)),
                ("invalid_sku", bool(statuses["invalid"])),
                ("local_value_review", bool(local_review_count)),
            )
            if active
        ]
        return super().update_version_progress(
            sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
            sku_count=len(expected),
            ready_count=statuses["conclusion_available"],
            review_required_count=local_review_count,
            blocked_count=statuses["invalid"],
            failed_count=len(failed),
            quality_summary_json={
                "release_quality_status": quality.value,
                "conclusion_available_count": statuses["conclusion_available"],
                "partial_conclusion_count": statuses["partial_conclusion"],
                "no_conclusion_count": statuses["no_conclusion"],
                "invalid_count": statuses["invalid"],
                "local_review_item_count": local_review_count,
            },
            validation_summary_json={
                "expected_sku_codes": expected,
                "generated_sku_codes": sorted(generated_codes),
                "failed_sku_codes": failed,
                "missing_sku_codes": missing_codes,
                "unexpected_sku_codes": unexpected_codes,
                "readback_error_sku_codes": sorted(hash_or_reference_errors),
            },
            release_quality_status=quality,
            processing_status="completed" if completed else "running",
            review_required=bool(reasons),
            review_status="review_required" if reasons else "auto_pass",
            review_reason_json={"reasons": reasons} if reasons else {},
            conclusion_available_count=statuses["conclusion_available"],
            partial_conclusion_count=statuses["partial_conclusion"],
            no_conclusion_count=statuses["no_conclusion"],
            invalid_count=statuses["invalid"],
            integrity_error_count=integrity_error_count,
        )

    def _iter_v5_1_read_bundles(
        self,
        version: entities.Core3SellpointValueProfileVersion,
    ) -> Iterator[
        tuple[
            entities.Core3SkuSellpointValueProfile,
            SellpointValueProfileReadBundle,
        ]
    ]:
        profile_model = entities.Core3SkuSellpointValueProfile
        candidate_model = entities.Core3SkuSellpointValueCandidate
        item_model = entities.Core3SkuSellpointValueItem
        version_record = SellpointValueVersionRecord.model_validate(version)
        offset = 0
        while True:
            profiles = list(
                self.db.execute(
                    select(profile_model)
                    .where(
                        profile_model.sellpoint_value_profile_version_id
                        == version.sellpoint_value_profile_version_id
                    )
                    .order_by(profile_model.sku_code)
                    .offset(offset)
                    .limit(SPV_V5_1_PROGRESS_READ_PAGE_SIZE)
                ).scalars()
            )
            if not profiles:
                return
            profile_ids = [row.sku_sellpoint_value_profile_id for row in profiles]
            candidates = list(
                self.db.execute(
                    select(candidate_model)
                    .where(candidate_model.sku_sellpoint_value_profile_id.in_(profile_ids))
                    .order_by(
                        candidate_model.sku_sellpoint_value_profile_id,
                        candidate_model.pool_type,
                        candidate_model.candidate_sku_code,
                    )
                ).scalars()
            )
            value_items = list(
                self.db.execute(
                    select(item_model)
                    .where(item_model.sku_sellpoint_value_profile_id.in_(profile_ids))
                    .order_by(
                        item_model.sku_sellpoint_value_profile_id,
                        item_model.battlefield_code,
                        item_model.normalized_bundle_code,
                    )
                ).scalars()
            )
            candidates_by_profile: dict[str, list[Any]] = {}
            for row in candidates:
                candidates_by_profile.setdefault(
                    row.sku_sellpoint_value_profile_id, []
                ).append(row)
            items_by_profile: dict[str, list[Any]] = {}
            for row in value_items:
                items_by_profile.setdefault(
                    row.sku_sellpoint_value_profile_id, []
                ).append(row)
            for profile in profiles:
                profile_id = profile.sku_sellpoint_value_profile_id
                yield profile, SellpointValueProfileReadBundle(
                    version=version_record,
                    profile=SkuSellpointValueProfileRecord.model_validate(profile),
                    candidates=[
                        SkuSellpointValueCandidateRecord.model_validate(row)
                        for row in candidates_by_profile.get(profile_id, [])
                    ],
                    value_items=[
                        SkuSellpointValueItemRecord.model_validate(row)
                        for row in items_by_profile.get(profile_id, [])
                    ],
                )
            if len(profiles) < SPV_V5_1_PROGRESS_READ_PAGE_SIZE:
                return
            offset += len(profiles)

    def _validate_v5_1_readback(
        self,
        persisted: SellpointValueProfileReadBundle,
    ) -> SellpointValueV51Readback:
        version = persisted.version
        row = persisted.profile
        if (
            version.method_version != SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION
            or row.method_version != SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION
        ):
            raise SellpointValueV51ReadbackIntegrityError(
                "typed V5.1 readback cannot consume a historical V5 row"
            )
        try:
            profile = _reconstruct_profile(persisted)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise SellpointValueV51ReadbackIntegrityError(
                "V5.1 typed payload reconstruction failed"
            ) from exc
        if build_v5_1_profile_input_fingerprint_from_profile(profile) != (
            profile.input_fingerprint
        ):
            raise SellpointValueV51ReadbackIntegrityError(
                "V5.1 profile input fingerprint mismatch"
            )
        if build_v5_1_profile_result_hash(profile) != profile.result_hash:
            raise SellpointValueV51ReadbackIntegrityError(
                "V5.1 profile result hash mismatch"
            )
        source = profile.competitor_source
        if (
            version.source_competitor_profile_version_id
            != source.competitor_profile_version_id
            or version.source_competitor_profile_method_version != source.method_version
            or version.source_competitor_profile_result_hash
            != source.source_version_result_hash
        ):
            raise SellpointValueV51ReadbackIntegrityError(
                "V5.1 profile competitor lineage does not match its version"
            )
        candidate_hashes = (version.source_scope_json or {}).get(
            "candidate_pool_hashes"
        ) or {}
        if candidate_hashes.get(profile.target.sku_code) != (
            profile.candidate_pools.result_hash
        ):
            raise SellpointValueV51ReadbackIntegrityError(
                "V5.1 candidate pool hash does not match the version scope"
            )
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
        _assert_no_dangling_references(profile)
        expected = project_v5_1_profile_to_persistence(
            profile,
            sellpoint_value_profile_version_id=(
                version.sellpoint_value_profile_version_id
            ),
        )
        _assert_projection_matches(expected, persisted)
        return SellpointValueV51Readback(profile=profile, persisted=persisted)

    def _assert_competitor_version(
        self,
        source: SellpointValueV51CompetitorVersionSource,
    ) -> None:
        row = (
            self.db.execute(
                select(entities.Core3CompetitorProfileVersion)
                .where(
                    entities.Core3CompetitorProfileVersion.competitor_profile_version_id
                    == source.competitor_profile_version_id
                )
                .where(
                    entities.Core3CompetitorProfileVersion.project_id == self.project_id
                )
                .where(
                    entities.Core3CompetitorProfileVersion.category_code
                    == self.category_code.value
                )
                .where(
                    entities.Core3CompetitorProfileVersion.release_scope_key
                    == source.release_scope_key
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            raise SellpointValueV51SourceIntegrityError(
                "competitor profile source version does not exist in scope"
            )
        actual = (
            row.profile_version,
            row.method_version,
            row.release_status,
            row.is_current,
            row.result_hash,
        )
        expected = (
            source.profile_version,
            source.method_version,
            source.release_status,
            source.is_current,
            source.version_result_hash,
        )
        if actual != expected:
            raise SellpointValueV51SourceIntegrityError(
                "competitor profile source identity or hash changed"
            )


def _reconstruct_profile(
    persisted: SellpointValueProfileReadBundle,
) -> SellpointValueV51Profile:
    row = persisted.profile
    source_rows = row.source_lineage_json or []
    sources = [
        item.get("payload")
        for item in source_rows
        if item.get("record_type") == "competitor_source"
    ]
    lineage = [
        item.get("payload")
        for item in source_rows
        if item.get("record_type") == "source_lineage"
    ]
    if len(sources) != 1 or any(item is None for item in lineage):
        raise SellpointValueV51ReadbackIntegrityError(
            "V5.1 source lineage envelope is incomplete"
        )
    candidate_payload = _typed_envelope_payload(
        row.candidate_universe_summary_json,
        "candidate_pools",
    )
    config_payload = _typed_envelope_payload(
        row.threshold_summary_json,
        "method_config",
    )
    conclusion_payload = _typed_envelope_payload(
        row.pm_decisions_json,
        "sku_conclusion",
    )
    values = [
        item.get("payload")
        for item in row.question_analyses_json or []
        if item.get("record_type") == "value_analysis"
    ]
    if len(values) != len(row.question_analyses_json or []):
        raise SellpointValueV51ReadbackIntegrityError(
            "V5.1 question payload contains an unknown envelope"
        )
    return SellpointValueV51Profile(
        schema_version=row.schema_version,
        rule_version=row.rule_version,
        method_version=row.method_version,
        project_id=row.project_id,
        category_code=row.category_code,
        batch_id=row.batch_id,
        release_scope_key=sources[0]["release_scope_key"],
        profile_version=row.profile_version,
        target=SellpointValueV51Target(
            sku_code=row.sku_code,
            model_code=row.model_code,
            model_name=row.model_name,
            brand_name=row.brand_name,
            display_name_cn=row.display_name_cn,
        ),
        competitor_source=SellpointValueCompetitorSource.model_validate(sources[0]),
        candidate_pools=SellpointValueCandidatePools.model_validate(candidate_payload),
        method_config=SellpointValueV51MethodConfig.model_validate(config_payload),
        source_lineage=[
            SellpointValueV51SourceLineage.model_validate(item) for item in lineage
        ],
        values=[SellpointValueV51ValueInput.model_validate(item) for item in values],
        sku_conclusion=SkuConclusionResult.model_validate(conclusion_payload),
        evidence_refs=row.evidence_refs_json,
        limitations=row.limitations_json,
        input_fingerprint=row.input_fingerprint,
        result_hash=row.result_hash,
    )


def _typed_envelope_payload(value: Mapping[str, Any], record_type: str) -> Any:
    if value.get("record_type") != record_type or value.get("payload") is None:
        raise SellpointValueV51ReadbackIntegrityError(
            f"V5.1 {record_type} envelope is incomplete"
        )
    return value["payload"]


def _assert_projection_matches(
    expected: SellpointValueDraftBundle,
    actual: SellpointValueProfileReadBundle,
) -> None:
    expected_candidates = {
        (row.pool_type, row.candidate_sku_code): row for row in expected.candidates
    }
    actual_candidates = {
        (row.pool_type, row.candidate_sku_code): row for row in actual.candidates
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
        raise SellpointValueV51ReadbackIntegrityError(
            "V5.1 child identity set contains missing or dangling rows"
        )
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
    expected_payload = expected.model_dump(mode="python")
    actual_payload = actual.model_dump(mode="python", exclude=exclude)
    for key, value in expected_payload.items():
        if key in {"release_status", "is_current"}:
            continue
        if actual_payload.get(key) != value:
            raise SellpointValueV51ReadbackIntegrityError(
                f"V5.1 persisted projection mismatch: {key}"
            )


def _assert_no_dangling_references(profile: SellpointValueV51Profile) -> None:
    valid_keys = {
        *(
            (CandidateSourceType.COMPETITOR, row.candidate_sku_code)
            for row in profile.candidate_pools.formal_competitors
        ),
        *(
            (CandidateSourceType.MARKET_REFERENCE, row.reference_sku_code)
            for row in profile.candidate_pools.analysis_references
        ),
    }
    valid_codes = {row[1] for row in valid_keys} | {profile.target.sku_code}
    dangling: set[str] = set()
    for value in profile.values:
        for quantification in value.quantification_stack.results:
            for use in quantification.candidate_uses:
                if (use.source_type, use.candidate_sku_code) not in valid_keys:
                    dangling.add(use.candidate_sku_code)
        for result in value.direct_market_results:
            dangling.update(
                code
                for code in result.used_comparator_sku_codes
                if code not in valid_codes
            )
            for disposition in result.candidate_dispositions:
                if (
                    disposition.source_type,
                    disposition.candidate_sku_code,
                ) not in valid_keys:
                    dangling.add(disposition.candidate_sku_code)
        for result in value.parameter_group_results:
            for disposition in result.candidate_dispositions:
                if (
                    disposition.source_type,
                    disposition.candidate_sku_code,
                ) not in valid_keys:
                    dangling.add(disposition.candidate_sku_code)
            for group in result.groups:
                dangling.update(
                    code for code in group.sku_codes if code not in valid_codes
                )
        for result in value.market_archetype_results:
            for group in result.groups:
                dangling.update(
                    code for code in group.sku_codes if code not in valid_codes
                )
        if value.synthetic_market_baseline is not None:
            dangling.update(
                code
                for code in value.synthetic_market_baseline.donor_sku_codes
                if code not in valid_codes
            )
    if dangling:
        raise SellpointValueV51ReadbackIntegrityError(
            "V5.1 analytical payload contains dangling SKU references: "
            + ",".join(sorted(dangling))
        )


def _assert_v5_1_version_payload(
    payload: SellpointValueVersionDraftCreate,
    source: SellpointValueV51CompetitorVersionSource,
) -> None:
    if (
        payload.schema_version != SELLPOINT_VALUE_PROFILE_V5_1_SCHEMA_VERSION
        or payload.rule_version != SELLPOINT_VALUE_PROFILE_V5_1_RULE_VERSION
        or payload.method_version != SELLPOINT_VALUE_PROFILE_V5_1_METHOD_VERSION
    ):
        raise ValueError("V5.1 repository requires the V5.1 version contract")
    if (
        payload.source_competitor_profile_version_id
        != source.competitor_profile_version_id
        or payload.source_competitor_profile_method_version
        != SELLPOINT_VALUE_PROFILE_V5_1_COMPETITOR_METHOD_VERSION
        or payload.source_competitor_profile_result_hash != source.version_result_hash
    ):
        raise ValueError("V5.1 version payload must bind the competitor source")


__all__ = [
    "SellpointValueV51ReadbackIntegrityError",
    "SellpointValueV51Repository",
    "SellpointValueV51RepositoryError",
    "SellpointValueV51SourceIntegrityError",
]
