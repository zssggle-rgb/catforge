"""Review, publication, and current-switch lifecycle for competitor profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select, update

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_diff import (
    CompetitorProfileDiffService,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_METHOD_VERSION,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    TargetMaterializationStatus,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_quality import (
    CompetitorProfileQualityService,
    ProfileQualityInput,
)
from app.services.core3_real_data.analyst.competitor_profile_quality_schemas import (
    CompetitorProfileFreshnessAssessment,
    CompetitorProfileVersionDiff,
    CompetitorProfileVersionQualityAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileNotFoundError,
    CompetitorProfileRepository,
    CompetitorProfileVersionNotFoundError,
    _version_record,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    ReleaseQualityStatus,
    ServingScope,
)
from app.services.core3_real_data.repositories import (
    Core3BaseRepository,
    Core3RepositoryContext,
)


class CompetitorProfileLifecycleError(RuntimeError):
    """Base class for safe competitor-profile lifecycle errors."""


class CompetitorProfileReviewNotAllowedError(CompetitorProfileLifecycleError):
    pass


class CompetitorProfilePublishNotAllowedError(CompetitorProfileLifecycleError):
    pass


class CompetitorProfileCurrentSwitchNotAllowedError(CompetitorProfileLifecycleError):
    pass


class CompetitorProfileCurrentSwitchConflictError(CompetitorProfileLifecycleError):
    pass


class CompetitorProfileDeprecateNotAllowedError(CompetitorProfileLifecycleError):
    pass


CHILD_MODELS = (
    entities.Core3SkuCompetitorProfile,
    entities.Core3SkuCompetitorProfilePair,
    entities.Core3SkuCompetitorProfileRelation,
    entities.Core3SkuCompetitorProfileSelection,
)

INTEGRITY_PAYLOAD_COLUMNS = (
    (entities.Core3SkuCompetitorProfile, "profile_payload_json"),
    (entities.Core3SkuCompetitorProfilePair, "pair_payload_json"),
    (entities.Core3SkuCompetitorProfileRelation, "relation_payload_json"),
    (entities.Core3SkuCompetitorProfileSelection, "selection_payload_json"),
)


class CompetitorProfileLifecycleService(Core3BaseRepository):
    """Own the immutable release state machine; never generate analytical rows."""

    def __init__(self, context: Core3RepositoryContext) -> None:
        super().__init__(context)
        self.repository = CompetitorProfileRepository(context)
        self.quality_service = CompetitorProfileQualityService()
        self.diff_service = CompetitorProfileDiffService()

    def assess_version_quality(
        self,
        *,
        competitor_profile_version_id: str,
        authoritative_sku_codes: Sequence[str],
        profiles: Sequence[ProfileQualityInput],
        generation_failures: Sequence[TargetMaterializationStatus] = (),
    ) -> CompetitorProfileVersionQualityAssessment:
        """Assess a version without changing its release or analytical state."""

        version = self.repository.get_version_by_id(competitor_profile_version_id)
        return self.quality_service.assess_version(
            version=version,
            authoritative_sku_codes=authoritative_sku_codes,
            profiles=profiles,
            generation_failures=generation_failures,
        )

    def assess_version_freshness(
        self,
        *,
        competitor_profile_version_id: str,
        current_serving_scope: ServingScope | None,
    ) -> CompetitorProfileFreshnessAssessment:
        """Compare frozen upstream scope without rewriting the saved version."""

        version = self.repository.get_version_by_id(competitor_profile_version_id)
        return self.quality_service.assess_freshness(
            version=version,
            current_serving_scope=current_serving_scope,
        )

    def diff_profiles(
        self,
        *,
        from_competitor_profile_version_id: str,
        to_competitor_profile_version_id: str,
        target_sku_code: str,
    ) -> CompetitorProfileVersionDiff:
        """Read and compare two saved SKU profiles inside this repository scope."""

        before_version = self.repository.get_version_by_id(
            from_competitor_profile_version_id
        )
        after_version = self.repository.get_version_by_id(
            to_competitor_profile_version_id
        )
        before = self.repository.get_profile(
            competitor_profile_version_id=from_competitor_profile_version_id,
            target_sku_code=target_sku_code,
            preview=True,
        )
        after = self.repository.get_profile(
            competitor_profile_version_id=to_competitor_profile_version_id,
            target_sku_code=target_sku_code,
            preview=True,
        )
        if before is None or after is None:
            raise CompetitorProfileNotFoundError(
                "both competitor profile versions are required for diff"
            )
        return self.diff_service.diff_profiles(
            from_version=before_version,
            from_profile=before,
            to_version=after_version,
            to_profile=after,
        )

    def review_version(
        self,
        *,
        competitor_profile_version_id: str,
        reviewed_by: str,
        release_quality_status: ReleaseQualityStatus,
    ) -> CompetitorProfileVersionRecord:
        actor = _explicit_actor(reviewed_by, allow_system=False)
        quality = _enum_value(release_quality_status)
        if quality not in {
            ReleaseQualityStatus.READY.value,
            ReleaseQualityStatus.LIMITED.value,
            ReleaseQualityStatus.BLOCKED.value,
        }:
            raise CompetitorProfileReviewNotAllowedError(
                "review requires ready, limited, or blocked release quality"
            )
        version = self._version_by_id(
            competitor_profile_version_id,
            for_update=True,
        )
        if version.release_status == "review":
            if (
                version.release_quality_status == quality
                and version.reviewed_by == actor
            ):
                return self._version_record_by_id(competitor_profile_version_id)
            raise CompetitorProfileReviewNotAllowedError(
                "reviewed versions are immutable"
            )
        if version.release_status != "draft" or version.is_current:
            raise CompetitorProfileReviewNotAllowedError(
                "only non-current draft versions can be reviewed"
            )

        base_violations = self._review_integrity_violations(version)
        quality_violations = self._quality_violations(version, quality)
        violations = sorted(set(base_violations + quality_violations))
        if quality == ReleaseQualityStatus.BLOCKED.value:
            if not violations:
                raise CompetitorProfileReviewNotAllowedError(
                    "blocked review requires a concrete integrity or quality reason"
                )
        elif violations:
            raise CompetitorProfileReviewNotAllowedError(
                "review quality gate failed: " + ",".join(violations)
            )

        now = datetime.now(timezone.utc)
        version.release_status = "review"
        version.release_quality_status = quality
        version.reviewed_at = now
        version.reviewed_by = actor
        version.review_required = quality != ReleaseQualityStatus.READY.value
        version.review_status = (
            "reviewed"
            if quality == ReleaseQualityStatus.READY.value
            else "review_required"
        )
        version.review_reasons_json = violations or (
            ["partial_profiles_present"]
            if quality == ReleaseQualityStatus.LIMITED.value
            else []
        )
        self._update_child_release_state(
            competitor_profile_version_id,
            release_status="review",
            is_current=False,
        )
        self.db.flush()
        return self._version_record_by_id(competitor_profile_version_id)

    def publish_version(
        self,
        *,
        competitor_profile_version_id: str,
        published_by: str,
        allow_limited: bool = False,
        release_note_cn: str | None = None,
    ) -> CompetitorProfileVersionRecord:
        actor = _explicit_actor(published_by, allow_system=False)
        initial = self._version_by_id(competitor_profile_version_id)
        self._lock_release_scope(initial.release_scope_key)
        version = self._version_by_id(
            competitor_profile_version_id,
            for_update=True,
        )
        if version.release_status == "published":
            if version.published_by == actor and (
                release_note_cn is None or release_note_cn == version.release_note_cn
            ):
                return self._version_record_by_id(competitor_profile_version_id)
            raise CompetitorProfilePublishNotAllowedError(
                "published version metadata is immutable"
            )
        if version.release_status != "review" or version.is_current:
            raise CompetitorProfilePublishNotAllowedError(
                "only reviewed non-current versions can be published"
            )
        quality = version.release_quality_status
        if quality not in {
            ReleaseQualityStatus.READY.value,
            ReleaseQualityStatus.LIMITED.value,
        }:
            raise CompetitorProfilePublishNotAllowedError(
                f"release quality {quality} cannot be published"
            )
        if quality == ReleaseQualityStatus.LIMITED.value and not allow_limited:
            raise CompetitorProfilePublishNotAllowedError(
                "limited release requires explicit allow_limited approval"
            )

        version.release_status = "published"
        version.is_current = False
        version.published_at = datetime.now(timezone.utc)
        version.published_by = actor
        if release_note_cn is not None:
            version.release_note_cn = release_note_cn
        self._update_child_release_state(
            competitor_profile_version_id,
            release_status="published",
            is_current=False,
        )
        self.db.flush()
        return self._version_record_by_id(competitor_profile_version_id)

    def set_current_version(
        self,
        *,
        competitor_profile_version_id: str,
        current_by: str,
        expected_current_version_id: str | None,
    ) -> CompetitorProfileVersionRecord:
        actor = _explicit_actor(current_by, allow_system=False)
        initial = self._version_by_id(competitor_profile_version_id)
        self._lock_release_scope(initial.release_scope_key)
        version = self._version_by_id(
            competitor_profile_version_id,
            for_update=True,
        )
        if version.release_status != "published":
            raise CompetitorProfileCurrentSwitchNotAllowedError(
                "only published versions can become current"
            )
        current = self._current_for_scope(
            version.release_scope_key,
            for_update=True,
        )
        if current is not None and (
            current.competitor_profile_version_id
            == version.competitor_profile_version_id
        ):
            return self._version_record_by_id(competitor_profile_version_id)
        actual_current_id = (
            current.competitor_profile_version_id if current is not None else None
        )
        if actual_current_id != expected_current_version_id:
            raise CompetitorProfileCurrentSwitchConflictError(
                "current version changed; expected-current CAS did not match"
            )

        with self.db.begin_nested():
            if current is not None:
                self.db.execute(
                    update(entities.Core3CompetitorProfileVersion)
                    .where(
                        entities.Core3CompetitorProfileVersion.project_id
                        == self.project_id
                    )
                    .where(
                        entities.Core3CompetitorProfileVersion.category_code
                        == self.category_code.value
                    )
                    .where(
                        entities.Core3CompetitorProfileVersion.competitor_profile_version_id
                        == current.competitor_profile_version_id
                    )
                    .where(entities.Core3CompetitorProfileVersion.is_current.is_(True))
                    .values(is_current=False)
                )
                self._update_child_release_state(
                    current.competitor_profile_version_id,
                    is_current=False,
                )
            version.is_current = True
            version.current_at = datetime.now(timezone.utc)
            version.current_by = actor
            self._update_child_release_state(
                version.competitor_profile_version_id,
                is_current=True,
            )
            self.db.flush()
        return self._version_record_by_id(competitor_profile_version_id)

    def deprecate_version(
        self,
        *,
        competitor_profile_version_id: str,
        deprecated_by: str,
        reason_cn: str,
    ) -> CompetitorProfileVersionRecord:
        actor = _explicit_actor(deprecated_by, allow_system=False)
        reason = reason_cn.strip()
        if not reason:
            raise ValueError("deprecation reason is required")
        version = self._version_by_id(
            competitor_profile_version_id,
            for_update=True,
        )
        reason_note = f"下线原因：{reason}"
        if version.release_status == "deprecated":
            if version.deprecated_by == actor and reason_note in (
                version.release_note_cn or ""
            ):
                return self._version_record_by_id(competitor_profile_version_id)
            raise CompetitorProfileDeprecateNotAllowedError(
                "deprecated version metadata is immutable"
            )
        if version.release_status != "published" or version.is_current:
            raise CompetitorProfileDeprecateNotAllowedError(
                "only non-current published versions can be deprecated"
            )
        version.release_status = "deprecated"
        version.deprecated_at = datetime.now(timezone.utc)
        version.deprecated_by = actor
        version.release_note_cn = "\n".join(
            part for part in (version.release_note_cn, reason_note) if part
        )
        self._update_child_release_state(
            competitor_profile_version_id,
            release_status="deprecated",
            is_current=False,
        )
        self.db.flush()
        return self._version_record_by_id(competitor_profile_version_id)

    def _review_integrity_violations(
        self,
        version: entities.Core3CompetitorProfileVersion,
    ) -> list[str]:
        version_id = version.competitor_profile_version_id
        violations: list[str] = []
        expected_processing_status = (
            "success"
            if version.method_version == AGENT_SNAPSHOT_METHOD_VERSION
            else "completed"
        )
        if version.processing_status != expected_processing_status:
            violations.append("generation_not_completed")
        if version.sku_count <= 0:
            violations.append("authoritative_sku_count_empty")

        actual_counts = {
            "profile_count": self._count(
                entities.Core3SkuCompetitorProfile, version_id
            ),
            "pair_count": self._count(
                entities.Core3SkuCompetitorProfilePair, version_id
            ),
            "relation_count": self._count(
                entities.Core3SkuCompetitorProfileRelation, version_id
            ),
            "selection_count": self._count(
                entities.Core3SkuCompetitorProfileSelection, version_id
            ),
        }
        expected_counts = {
            "profile_count": version.sku_count,
            "pair_count": version.pair_count,
            "relation_count": version.relation_count,
            "selection_count": version.selection_count,
        }
        for name, expected in expected_counts.items():
            if actual_counts[name] != expected:
                violations.append(f"{name}_mismatch")

        state_counts = dict(
            self.db.execute(
                select(
                    entities.Core3SkuCompetitorProfile.analysis_state,
                    func.count(),
                )
                .where(
                    entities.Core3SkuCompetitorProfile.competitor_profile_version_id
                    == version_id
                )
                .group_by(entities.Core3SkuCompetitorProfile.analysis_state)
            ).all()
        )
        for state, expected in (
            ("ready", version.ready_count),
            ("partial", version.partial_count),
            ("blocked", version.blocked_count),
        ):
            if int(state_counts.get(state, 0)) != expected:
                violations.append(f"{state}_count_mismatch")
        if sum(state_counts.values()) + version.failed_count != version.sku_count:
            violations.append("status_count_mismatch")

        payload_columns = (
            ((entities.Core3SkuCompetitorProfilePair, "pair_payload_json"),)
            if version.method_version == AGENT_SNAPSHOT_METHOD_VERSION
            else INTEGRITY_PAYLOAD_COLUMNS
        )
        for model, payload_column in payload_columns:
            violations.extend(
                self._row_integrity_violations(
                    model,
                    payload_column,
                    version,
                )
            )
        if version.method_version == AGENT_SNAPSHOT_METHOD_VERSION:
            violations.extend(self._agent_snapshot_integrity_violations(version))
        elif self._invalid_relation_group_count(version_id):
            violations.append("pair_relation_cardinality_invalid")
        if self._invalid_selection_ranks(version_id):
            violations.append("selection_rank_sequence_invalid")
        if self._selected_pair_codes(version_id) != self._selection_pair_codes(
            version_id
        ):
            violations.append("selected_pair_selection_mismatch")
        return violations

    def _quality_violations(
        self,
        version: entities.Core3CompetitorProfileVersion,
        quality: str,
    ) -> list[str]:
        version_id = version.competitor_profile_version_id
        review_required_count = sum(
            self._count(model, version_id, review_required=True)
            for model in CHILD_MODELS
        )
        if quality == ReleaseQualityStatus.READY.value:
            violations = []
            if version.ready_count != version.sku_count:
                violations.append("ready_release_not_fully_ready")
            if version.partial_count or version.blocked_count or version.failed_count:
                violations.append("ready_release_has_non_ready_profiles")
            if review_required_count:
                violations.append("ready_release_has_review_required_rows")
            return violations
        if quality == ReleaseQualityStatus.LIMITED.value:
            violations = []
            if version.partial_count <= 0:
                violations.append("limited_release_requires_partial_profiles")
            if version.ready_count + version.partial_count != version.sku_count:
                violations.append("limited_release_coverage_invalid")
            if version.blocked_count or version.failed_count:
                violations.append("limited_release_has_blocked_or_failed_profiles")
            return violations
        reasons = []
        if version.blocked_count or version.failed_count:
            reasons.append("blocked_or_failed_profiles_present")
        if review_required_count:
            reasons.append("review_required_rows_present")
        return reasons

    def _row_integrity_violations(
        self,
        model: Any,
        payload_column: str,
        version: entities.Core3CompetitorProfileVersion,
    ) -> list[str]:
        rows = self.db.execute(
            select(
                model.project_id,
                model.category_code,
                model.product_category,
                model.storage_batch_id,
                model.release_scope_key,
                model.profile_version,
                model.schema_version,
                model.rule_version,
                model.method_version,
                model.input_fingerprint,
                model.result_hash,
                getattr(model, payload_column),
            )
            .where(
                model.competitor_profile_version_id
                == version.competitor_profile_version_id
            )
            .execution_options(yield_per=50)
        )
        expected_scope = (
            version.project_id,
            version.category_code,
            version.product_category,
            version.storage_batch_id,
            version.release_scope_key,
            version.profile_version,
            version.schema_version,
            version.rule_version,
            version.method_version,
        )
        scope_mismatch = False
        hash_mismatch = False
        input_mismatch = False
        for row in rows:
            if tuple(row[:9]) != expected_scope:
                scope_mismatch = True
            payload = row[11] or {}
            payload_result_hash = payload.get("result_hash")
            if row[10] != payload_result_hash:
                hash_mismatch = True
            payload_input = payload.get("input_fingerprint")
            if payload_input is not None and row[9] != payload_input:
                input_mismatch = True
        prefix = model.__tablename__.removeprefix("core3_sku_competitor_profile")
        prefix = prefix.strip("_") or "profile"
        violations = []
        if scope_mismatch:
            violations.append(f"{prefix}_scope_mismatch")
        if hash_mismatch:
            violations.append(f"{prefix}_hash_mismatch")
        if input_mismatch:
            violations.append(f"{prefix}_input_fingerprint_mismatch")
        return violations

    def _agent_snapshot_integrity_violations(
        self,
        version: entities.Core3CompetitorProfileVersion,
    ) -> list[str]:
        """Validate agent-aligned graph indexes without loading analytical JSON."""

        version_id = version.competitor_profile_version_id
        violations: set[str] = set()
        if version.relation_count != 0 or self._count(
            entities.Core3SkuCompetitorProfileRelation, version_id
        ):
            violations.add("agent_snapshot_relation_rows_present")

        snapshot_model = entities.Core3CompetitorProfileSkuSnapshot
        snapshot_rows = self.db.execute(
            select(
                snapshot_model.competitor_profile_sku_snapshot_id,
                snapshot_model.sku_code,
                snapshot_model.project_id,
                snapshot_model.category_code,
                snapshot_model.release_scope_key,
                snapshot_model.profile_version,
                snapshot_model.schema_version,
                snapshot_model.rule_version,
                snapshot_model.method_version,
                snapshot_model.result_hash,
                snapshot_model.snapshot_json["snapshot_ref"].as_string(),
                snapshot_model.snapshot_json["identity"]["sku_code"].as_string(),
                snapshot_model.snapshot_json[
                    "competitor_profile_version_id"
                ].as_string(),
                snapshot_model.snapshot_json["result_hash"].as_string(),
            )
            .where(snapshot_model.competitor_profile_version_id == version_id)
            .execution_options(yield_per=100)
        )
        expected_scope = (
            version.project_id,
            version.category_code,
            version.release_scope_key,
            version.profile_version,
            version.schema_version,
            version.rule_version,
            version.method_version,
        )
        for row in snapshot_rows:
            if tuple(row[2:9]) != expected_scope:
                violations.add("agent_snapshot_scope_mismatch")
            if (
                row[10] != row[0]
                or row[11] != row[1]
                or row[12] != version_id
                or row[13] != row[9]
            ):
                violations.add("agent_snapshot_payload_mismatch")

        profile_model = entities.Core3SkuCompetitorProfile
        profile_rows = self.db.execute(
            select(
                profile_model.sku_competitor_profile_id,
                profile_model.target_sku_code,
                profile_model.analysis_candidate_count,
                profile_model.result_hash,
                profile_model.analysis_result_hash,
                profile_model.project_id,
                profile_model.category_code,
                profile_model.release_scope_key,
                profile_model.profile_version,
                profile_model.schema_version,
                profile_model.rule_version,
                profile_model.method_version,
                profile_model.profile_payload_json[
                    "competitor_profile_version_id"
                ].as_string(),
                profile_model.profile_payload_json["target"]["sku_code"].as_string(),
                profile_model.profile_payload_json["release_scope_key"].as_string(),
                profile_model.profile_payload_json["profile_version"].as_string(),
                profile_model.profile_payload_json["result_hash"].as_string(),
                profile_model.profile_payload_json["target_snapshot_ref"].as_string(),
            )
            .where(profile_model.competitor_profile_version_id == version_id)
            .execution_options(yield_per=100)
        )
        profile_ids: set[str] = set()
        target_snapshot_refs: set[str] = set()
        for row in profile_rows:
            profile_ids.add(row[0])
            target_snapshot_refs.add(row[17])
            if (
                row[4] != row[3]
                or tuple(row[5:12]) != expected_scope
                or row[12] != version_id
                or row[13] != row[1]
                or row[14] != version.release_scope_key
                or row[15] != version.profile_version
                or row[16] != row[3]
            ):
                violations.add("agent_profile_payload_mismatch")

        pair_model = entities.Core3SkuCompetitorProfilePair
        pair_counts = (
            select(
                pair_model.sku_competitor_profile_id.label("profile_id"),
                func.count().label("pair_count"),
            )
            .where(pair_model.competitor_profile_version_id == version_id)
            .group_by(pair_model.sku_competitor_profile_id)
            .subquery()
        )
        candidate_count_mismatches = int(
            self.db.scalar(
                select(func.count())
                .select_from(profile_model)
                .outerjoin(
                    pair_counts,
                    pair_counts.c.profile_id == profile_model.sku_competitor_profile_id,
                )
                .where(profile_model.competitor_profile_version_id == version_id)
                .where(
                    func.coalesce(pair_counts.c.pair_count, 0)
                    != func.coalesce(profile_model.analysis_candidate_count, 0)
                )
            )
            or 0
        )
        if candidate_count_mismatches:
            violations.add("agent_profile_candidate_count_mismatch")

        snapshot_ids = set(
            self.db.execute(
                select(snapshot_model.competitor_profile_sku_snapshot_id).where(
                    snapshot_model.competitor_profile_version_id == version_id
                )
            ).scalars()
        )
        if target_snapshot_refs - snapshot_ids:
            violations.add("agent_profile_target_snapshot_missing")
        pair_snapshot_refs = self.db.execute(
            select(
                pair_model.sku_competitor_profile_id,
                pair_model.target_snapshot_ref,
                pair_model.candidate_snapshot_ref,
                pair_model.analysis_result_hash,
                pair_model.result_hash,
            )
            .where(pair_model.competitor_profile_version_id == version_id)
            .execution_options(yield_per=500)
        )
        for (
            profile_id,
            target_ref,
            candidate_ref,
            analysis_hash,
            result_hash,
        ) in pair_snapshot_refs:
            if profile_id not in profile_ids:
                violations.add("agent_pair_profile_missing")
            if target_ref not in snapshot_ids:
                violations.add("agent_pair_target_snapshot_missing")
            if candidate_ref not in snapshot_ids:
                violations.add("agent_pair_candidate_snapshot_missing")
            if analysis_hash != result_hash:
                violations.add("agent_pair_analysis_hash_mismatch")

        selection_model = entities.Core3SkuCompetitorProfileSelection
        selection_mismatches = int(
            self.db.scalar(
                select(func.count())
                .select_from(selection_model)
                .join(
                    pair_model,
                    pair_model.sku_competitor_profile_pair_id
                    == selection_model.sku_competitor_profile_pair_id,
                )
                .where(selection_model.competitor_profile_version_id == version_id)
                .where(
                    (
                        selection_model.sku_competitor_profile_id
                        != pair_model.sku_competitor_profile_id
                    )
                    | (
                        selection_model.candidate_sku_code
                        != pair_model.candidate_sku_code
                    )
                    | (selection_model.result_hash != pair_model.result_hash)
                    | (pair_model.selected.is_(False))
                    | (
                        selection_model.selection_rank
                        != pair_model.pair_payload_json["selected_rank"].as_integer()
                    )
                )
            )
            or 0
        )
        if selection_mismatches:
            violations.add("agent_selection_index_mismatch")
        return sorted(violations)

    def _count(
        self,
        model: Any,
        version_id: str,
        *,
        review_required: bool | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(model)
            .where(model.competitor_profile_version_id == version_id)
        )
        if review_required is not None:
            stmt = stmt.where(model.review_required.is_(review_required))
        return int(self.db.scalar(stmt) or 0)

    def _invalid_relation_group_count(self, version_id: str) -> int:
        relation_groups = (
            select(
                entities.Core3SkuCompetitorProfileRelation.sku_competitor_profile_pair_id.label(
                    "pair_id"
                ),
                func.count().label("relation_count"),
            )
            .where(
                entities.Core3SkuCompetitorProfileRelation.competitor_profile_version_id
                == version_id
            )
            .group_by(
                entities.Core3SkuCompetitorProfileRelation.sku_competitor_profile_pair_id
            )
            .subquery()
        )
        pair = entities.Core3SkuCompetitorProfilePair
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(pair)
                .outerjoin(
                    relation_groups,
                    relation_groups.c.pair_id == pair.sku_competitor_profile_pair_id,
                )
                .where(pair.competitor_profile_version_id == version_id)
                .where(func.coalesce(relation_groups.c.relation_count, 0) != 7)
            )
            or 0
        )

    def _invalid_selection_ranks(self, version_id: str) -> bool:
        model = entities.Core3SkuCompetitorProfileSelection
        groups = self.db.execute(
            select(
                model.sku_competitor_profile_id,
                func.count(),
                func.min(model.selection_rank),
                func.max(model.selection_rank),
            )
            .where(model.competitor_profile_version_id == version_id)
            .group_by(model.sku_competitor_profile_id)
        ).all()
        return any(
            minimum != 1 or maximum != count for _, count, minimum, maximum in groups
        )

    def _selected_pair_codes(self, version_id: str) -> set[tuple[str, str]]:
        model = entities.Core3SkuCompetitorProfilePair
        return set(
            self.db.execute(
                select(model.sku_competitor_profile_id, model.candidate_sku_code)
                .where(model.competitor_profile_version_id == version_id)
                .where(model.selected.is_(True))
            ).all()
        )

    def _selection_pair_codes(self, version_id: str) -> set[tuple[str, str]]:
        model = entities.Core3SkuCompetitorProfileSelection
        return set(
            self.db.execute(
                select(model.sku_competitor_profile_id, model.candidate_sku_code).where(
                    model.competitor_profile_version_id == version_id
                )
            ).all()
        )

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

    def _version_record_by_id(
        self,
        version_id: str,
    ) -> CompetitorProfileVersionRecord:
        return _version_record(self._version_by_id(version_id))

    def _lock_release_scope(self, release_scope_key: str) -> None:
        project = self.db.execute(
            select(entities.CategoryProject.project_id)
            .where(entities.CategoryProject.project_id == self.project_id)
            .where(entities.CategoryProject.category_code == self.category_code.value)
            .with_for_update()
        ).scalar_one_or_none()
        if project is None:
            raise CompetitorProfileVersionNotFoundError(
                "competitor profile project/category scope not found"
            )
        list(
            self.db.execute(
                select(
                    entities.Core3CompetitorProfileVersion.competitor_profile_version_id
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
                    == release_scope_key
                )
                .with_for_update()
            ).scalars()
        )

    def _current_for_scope(
        self,
        release_scope_key: str,
        *,
        for_update: bool,
    ) -> entities.Core3CompetitorProfileVersion | None:
        model = entities.Core3CompetitorProfileVersion
        stmt = (
            select(model)
            .where(model.project_id == self.project_id)
            .where(model.category_code == self.category_code.value)
            .where(model.release_scope_key == release_scope_key)
            .where(model.release_status == "published")
            .where(model.is_current.is_(True))
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.execute(stmt).scalars().first()

    def _update_child_release_state(
        self,
        version_id: str,
        *,
        release_status: str | None = None,
        is_current: bool | None = None,
    ) -> None:
        values = {}
        if release_status is not None:
            values["release_status"] = release_status
        if is_current is not None:
            values["is_current"] = is_current
        for model in CHILD_MODELS:
            self.db.execute(
                update(model)
                .where(model.project_id == self.project_id)
                .where(model.category_code == self.category_code.value)
                .where(model.competitor_profile_version_id == version_id)
                .values(**values)
            )


def _explicit_actor(actor: str, *, allow_system: bool) -> str:
    normalized = actor.strip()
    if not normalized or (not allow_system and normalized.lower() == "system"):
        raise ValueError("an explicit non-system actor is required")
    return normalized


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


__all__ = [
    "CompetitorProfileCurrentSwitchConflictError",
    "CompetitorProfileCurrentSwitchNotAllowedError",
    "CompetitorProfileDeprecateNotAllowedError",
    "CompetitorProfileLifecycleError",
    "CompetitorProfileLifecycleService",
    "CompetitorProfilePublishNotAllowedError",
    "CompetitorProfileReviewNotAllowedError",
]
