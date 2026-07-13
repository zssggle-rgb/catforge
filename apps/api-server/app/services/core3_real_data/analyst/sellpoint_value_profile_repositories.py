"""Transactional repositories for versioned sellpoint-value profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.models import entities
from app.services.core3_real_data.analyst.analyst_repository import (
    batch_ids_from_scope,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SellpointValueProfileReadBundle,
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SellpointValueVersionRecord,
    SkuSellpointValueCandidateRecord,
    SkuSellpointValueItemRecord,
    SkuSellpointValueProfileRecord,
    SkuSellpointValueProfileProgressRecord,
)
from app.services.core3_real_data.repositories import (
    Core3BaseRepository,
    Core3RepositoryContext,
)


class SellpointValueProfileRepositoryError(RuntimeError):
    pass


class SellpointValueVersionNotFoundError(SellpointValueProfileRepositoryError):
    pass


class SellpointValueProfileNotFoundError(SellpointValueProfileRepositoryError):
    pass


class SellpointValueImmutableVersionError(SellpointValueProfileRepositoryError):
    pass


class SellpointValueDraftWriteNotAllowedError(SellpointValueProfileRepositoryError):
    pass


class SellpointValuePublishNotAllowedError(SellpointValueProfileRepositoryError):
    pass


class SellpointValueProfileRepository(Core3BaseRepository):
    def __init__(self, context: Core3RepositoryContext) -> None:
        super().__init__(context)

    def create_version(
        self,
        payload: SellpointValueVersionDraftCreate,
    ) -> SellpointValueVersionRecord:
        self._assert_context_scope(payload.project_id, payload.category_code)
        existing = self._find_version(
            batch_id=payload.batch_id,
            profile_version=payload.profile_version,
            rule_version=payload.rule_version,
        )
        if existing is not None:
            if (
                existing.input_fingerprint != payload.input_fingerprint
                or existing.candidate_universe_fingerprint
                != payload.candidate_universe_fingerprint
                or existing.result_hash != payload.result_hash
            ):
                raise SellpointValueImmutableVersionError(
                    "profile version already exists with different immutable inputs"
                )
            return SellpointValueVersionRecord.model_validate(existing)
        try:
            with self.db.begin_nested():
                row = entities.Core3SellpointValueProfileVersion(
                    **_entity_payload(payload)
                )
                self.db.add(row)
                self.db.flush()
            return SellpointValueVersionRecord.model_validate(row)
        except IntegrityError:
            concurrent = self._find_version(
                batch_id=payload.batch_id,
                profile_version=payload.profile_version,
                rule_version=payload.rule_version,
            )
            if concurrent is None:
                raise
            if (
                concurrent.input_fingerprint != payload.input_fingerprint
                or concurrent.candidate_universe_fingerprint
                != payload.candidate_universe_fingerprint
                or concurrent.result_hash != payload.result_hash
            ):
                raise SellpointValueImmutableVersionError(
                    "concurrent profile version has different immutable inputs"
                )
            return SellpointValueVersionRecord.model_validate(concurrent)

    def write_draft(
        self,
        bundle: SellpointValueDraftBundle,
        *,
        use_savepoint: bool = True,
    ) -> SellpointValueProfileReadBundle:
        profile = bundle.profile
        self._assert_context_scope(profile.project_id, profile.category_code)
        version = self._version_by_id(
            profile.sellpoint_value_profile_version_id,
            for_update=True,
        )
        self._assert_draft_version(version)
        self._assert_version_matches_profile(version, profile)
        existing = self._find_profile(
            batch_id=profile.batch_id,
            profile_version=profile.profile_version,
            sku_code=profile.sku_code,
            rule_version=profile.rule_version,
        )
        if existing is not None:
            if (
                existing.input_fingerprint != profile.input_fingerprint
                or existing.result_hash != profile.result_hash
            ):
                raise SellpointValueImmutableVersionError(
                    "draft SKU already exists with different immutable inputs"
                )
            self._assert_existing_children_match(existing, bundle)
            return self._read_bundle(version, existing)

        if use_savepoint:
            try:
                with self.db.begin_nested():
                    profile_row = self._insert_draft_rows(bundle)
            except IntegrityError:
                concurrent = self._find_profile(
                    batch_id=profile.batch_id,
                    profile_version=profile.profile_version,
                    sku_code=profile.sku_code,
                    rule_version=profile.rule_version,
                )
                if concurrent is None:
                    raise
                if (
                    concurrent.input_fingerprint != profile.input_fingerprint
                    or concurrent.result_hash != profile.result_hash
                ):
                    raise SellpointValueImmutableVersionError(
                        "concurrent draft SKU has different immutable inputs"
                    )
                self._assert_existing_children_match(concurrent, bundle)
                return self._read_bundle(version, concurrent)
        else:
            profile_row = self._insert_draft_rows(bundle)
        return self._read_bundle(version, profile_row)

    def _insert_draft_rows(
        self,
        bundle: SellpointValueDraftBundle,
    ) -> entities.Core3SkuSellpointValueProfile:
        profile_row = entities.Core3SkuSellpointValueProfile(
            **_entity_payload(bundle.profile)
        )
        self.db.add(profile_row)
        self.db.flush()
        for candidate in bundle.candidates:
            candidate_payload = _entity_payload(candidate)
            candidate_payload["sku_sellpoint_value_profile_id"] = (
                profile_row.sku_sellpoint_value_profile_id
            )
            self.db.add(
                entities.Core3SkuSellpointValueCandidate(**candidate_payload)
            )
        for item in bundle.value_items:
            item_payload = _entity_payload(item)
            item_payload["sku_sellpoint_value_profile_id"] = (
                profile_row.sku_sellpoint_value_profile_id
            )
            self.db.add(entities.Core3SkuSellpointValueItem(**item_payload))
        self.db.flush()
        return profile_row

    def get_version(
        self,
        *,
        batch_id: str,
        profile_version: str,
        rule_version: str,
    ) -> SellpointValueVersionRecord | None:
        row = self._find_version(
            batch_id=batch_id,
            profile_version=profile_version,
            rule_version=rule_version,
        )
        return SellpointValueVersionRecord.model_validate(row) if row else None

    def list_versions(
        self,
        *,
        batch_id: str,
        release_status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SellpointValueVersionRecord]:
        normalized_limit, normalized_offset = self.pagination(limit, offset)
        stmt = (
            select(entities.Core3SellpointValueProfileVersion)
            .where(
                entities.Core3SellpointValueProfileVersion.project_id
                == self.project_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.category_code
                == self.category_code.value
            )
            .where(
                _batch_scope_filter(
                    entities.Core3SellpointValueProfileVersion.batch_id,
                    batch_id,
                )
            )
        )
        if release_status is not None:
            stmt = stmt.where(
                entities.Core3SellpointValueProfileVersion.release_status
                == release_status
            )
        stmt = stmt.order_by(
            entities.Core3SellpointValueProfileVersion.generated_at.desc(),
            entities.Core3SellpointValueProfileVersion.profile_version,
        ).offset(normalized_offset).limit(normalized_limit)
        return [
            SellpointValueVersionRecord.model_validate(row)
            for row in self.db.execute(stmt).scalars()
        ]

    def get_profile(
        self,
        *,
        batch_id: str,
        profile_version: str,
        sku_code: str,
        rule_version: str,
    ) -> SellpointValueProfileReadBundle | None:
        version = self._find_version(
            batch_id=batch_id,
            profile_version=profile_version,
            rule_version=rule_version,
        )
        if version is None:
            return None
        profile = self._find_profile(
            batch_id=version.batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
            rule_version=rule_version,
        )
        if profile is None:
            return None
        return self._read_bundle(version, profile)

    def get_current_published_profile(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> SellpointValueProfileReadBundle | None:
        version = self._find_current_published_version(batch_id=batch_id)
        if version is None:
            return None
        stmt = (
            select(entities.Core3SkuSellpointValueProfile)
            .where(
                entities.Core3SkuSellpointValueProfile.project_id
                == self.project_id
            )
            .where(
                entities.Core3SkuSellpointValueProfile.category_code
                == self.category_code.value
            )
            .where(
                entities.Core3SkuSellpointValueProfile.batch_id
                == version.batch_id
            )
            .where(
                entities.Core3SkuSellpointValueProfile.sellpoint_value_profile_version_id
                == version.sellpoint_value_profile_version_id
            )
            .where(entities.Core3SkuSellpointValueProfile.sku_code == sku_code)
            .where(
                entities.Core3SkuSellpointValueProfile.release_status
                == "published"
            )
            .where(entities.Core3SkuSellpointValueProfile.is_current.is_(True))
        )
        profile = self.db.execute(stmt).scalars().first()
        return self._read_bundle(version, profile) if profile else None

    def resolve_profile_targets(
        self,
        *,
        batch_id: str,
        profile_version: str | None = None,
        sku_code: str | None = None,
        model_name: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, str | None]]:
        normalized_limit, _ = self.pagination(limit, 0, max_limit=50)
        profile = entities.Core3SkuSellpointValueProfile
        version = entities.Core3SellpointValueProfileVersion
        stmt = (
            select(profile)
            .join(
                version,
                version.sellpoint_value_profile_version_id
                == profile.sellpoint_value_profile_version_id,
            )
            .where(profile.project_id == self.project_id)
            .where(profile.category_code == self.category_code.value)
            .where(_batch_scope_filter(profile.batch_id, batch_id))
        )
        if profile_version is None:
            stmt = (
                stmt.where(version.release_status == "published")
                .where(version.is_current.is_(True))
                .where(profile.release_status == "published")
                .where(profile.is_current.is_(True))
            )
        else:
            stmt = stmt.where(version.profile_version == profile_version)
        if sku_code:
            stmt = stmt.where(profile.sku_code == sku_code)
        elif model_name:
            stmt = stmt.where(profile.model_name.ilike(f"%{model_name.strip()}%"))
        elif query:
            text_query = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    profile.sku_code.ilike(text_query),
                    profile.model_name.ilike(text_query),
                    profile.display_name_cn.ilike(text_query),
                )
            )
        else:
            return []
        rows = list(
            self.db.execute(
                stmt.order_by(
                    _batch_scope_order(profile.batch_id, batch_id),
                    profile.sku_code,
                ).limit(normalized_limit)
            ).scalars()
        )
        return [
            {
                "sku_code": row.sku_code,
                "brand_name": row.brand_name,
                "model_name": row.model_name,
                "product_category": row.product_category,
                "profile_version": row.profile_version,
                "rule_version": row.rule_version,
            }
            for row in rows
        ]

    def list_profiles(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        analysis_state: str | None = None,
        review_required: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuSellpointValueProfileRecord]:
        self._version_by_id(sellpoint_value_profile_version_id)
        normalized_limit, normalized_offset = self.pagination(limit, offset)
        stmt = (
            select(entities.Core3SkuSellpointValueProfile)
            .where(
                entities.Core3SkuSellpointValueProfile.project_id
                == self.project_id
            )
            .where(
                entities.Core3SkuSellpointValueProfile.category_code
                == self.category_code.value
            )
            .where(
                entities.Core3SkuSellpointValueProfile.sellpoint_value_profile_version_id
                == sellpoint_value_profile_version_id
            )
        )
        if analysis_state is not None:
            stmt = stmt.where(
                entities.Core3SkuSellpointValueProfile.analysis_state
                == analysis_state
            )
        if review_required is not None:
            stmt = stmt.where(
                entities.Core3SkuSellpointValueProfile.review_required
                == review_required
            )
        stmt = stmt.order_by(
            entities.Core3SkuSellpointValueProfile.sku_code
        ).offset(normalized_offset).limit(normalized_limit)
        return [
            SkuSellpointValueProfileRecord.model_validate(row)
            for row in self.db.execute(stmt).scalars()
        ]

    def list_profile_progress(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[SkuSellpointValueProfileProgressRecord]:
        """Read only the fields needed to resume and update batch counters."""

        self._version_by_id(sellpoint_value_profile_version_id)
        normalized_limit, normalized_offset = self.pagination(
            limit,
            offset,
            max_limit=1000,
        )
        profile = entities.Core3SkuSellpointValueProfile
        stmt = (
            select(
                profile.sku_code,
                profile.analysis_state,
                profile.review_required,
            )
            .where(profile.project_id == self.project_id)
            .where(profile.category_code == self.category_code.value)
            .where(
                profile.sellpoint_value_profile_version_id
                == sellpoint_value_profile_version_id
            )
            .order_by(profile.sku_code)
            .offset(normalized_offset)
            .limit(normalized_limit)
        )
        return [
            SkuSellpointValueProfileProgressRecord.model_validate(row)
            for row in self.db.execute(stmt).mappings()
        ]

    def list_candidates(
        self,
        *,
        sku_sellpoint_value_profile_id: str,
        question_code: str | None = None,
        eligibility_status: str | None = None,
        selected_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuSellpointValueCandidateRecord]:
        self._profile_by_id(sku_sellpoint_value_profile_id)
        stmt = (
            select(entities.Core3SkuSellpointValueCandidate)
            .where(
                entities.Core3SkuSellpointValueCandidate.project_id
                == self.project_id
            )
            .where(
                entities.Core3SkuSellpointValueCandidate.category_code
                == self.category_code.value
            )
            .where(
                entities.Core3SkuSellpointValueCandidate.sku_sellpoint_value_profile_id
                == sku_sellpoint_value_profile_id
            )
            .order_by(
                entities.Core3SkuSellpointValueCandidate.pool_type,
                entities.Core3SkuSellpointValueCandidate.candidate_sku_code,
            )
        )
        rows = list(self.db.execute(stmt).scalars())
        if eligibility_status is not None:
            rows = [
                row for row in rows if row.eligibility_status == eligibility_status
            ]
        if question_code is not None:
            field_name = (
                "selected_questions_json"
                if selected_only
                else "eligible_questions_json"
            )
            rows = [
                row
                for row in rows
                if question_code in (getattr(row, field_name) or [])
            ]
        normalized_limit, normalized_offset = self.pagination(limit, offset)
        return [
            SkuSellpointValueCandidateRecord.model_validate(row)
            for row in rows[
                normalized_offset : normalized_offset + normalized_limit
            ]
        ]

    def list_value_items(
        self,
        *,
        sku_sellpoint_value_profile_id: str,
        question_code: str | None = None,
        investment_classification: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuSellpointValueItemRecord]:
        self._profile_by_id(sku_sellpoint_value_profile_id)
        stmt = (
            select(entities.Core3SkuSellpointValueItem)
            .where(
                entities.Core3SkuSellpointValueItem.project_id == self.project_id
            )
            .where(
                entities.Core3SkuSellpointValueItem.category_code
                == self.category_code.value
            )
            .where(
                entities.Core3SkuSellpointValueItem.sku_sellpoint_value_profile_id
                == sku_sellpoint_value_profile_id
            )
            .order_by(
                entities.Core3SkuSellpointValueItem.battlefield_code,
                entities.Core3SkuSellpointValueItem.normalized_bundle_code,
            )
        )
        rows = list(self.db.execute(stmt).scalars())
        if question_code is not None:
            rows = [
                row for row in rows if question_code in (row.question_codes_json or [])
            ]
        if investment_classification is not None:
            rows = [
                row
                for row in rows
                if investment_classification
                in (row.investment_classifications_json or [])
            ]
        normalized_limit, normalized_offset = self.pagination(limit, offset)
        return [
            SkuSellpointValueItemRecord.model_validate(row)
            for row in rows[
                normalized_offset : normalized_offset + normalized_limit
            ]
        ]

    def review_version(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        reviewed_by: str,
        release_quality_status: SellpointValueReleaseQualityStatus,
    ) -> SellpointValueVersionRecord:
        if not reviewed_by.strip():
            raise ValueError("reviewed_by is required")
        version = self._version_by_id(
            sellpoint_value_profile_version_id,
            for_update=True,
        )
        if version.release_status != "draft" or version.is_current:
            raise SellpointValueDraftWriteNotAllowedError(
                "only non-current draft versions can be reviewed"
            )
        now = datetime.now(timezone.utc)
        version.release_status = "reviewed"
        version.release_quality_status = _enum_value(release_quality_status)
        version.reviewed_at = now
        version.reviewed_by = reviewed_by
        version.review_required = (
            version.release_quality_status
            in {"limited", "blocked", "unassessed"}
        )
        version.review_status = (
            "review_required" if version.review_required else "reviewed"
        )
        self._update_child_release_status(
            sellpoint_value_profile_version_id,
            release_status="reviewed",
            is_current=False,
        )
        self.db.flush()
        return SellpointValueVersionRecord.model_validate(version)

    def _lock_batch_release_scope(self, batch_id: str) -> None:
        """Serialize review/publish transitions that share one current slot."""

        stmt = (
            select(entities.Core3SourceBatch.batch_id)
            .where(entities.Core3SourceBatch.project_id == self.project_id)
            .where(
                entities.Core3SourceBatch.category_code == self.category_code.value
            )
            .where(entities.Core3SourceBatch.batch_id == batch_id)
            .with_for_update()
        )
        if self.db.execute(stmt).scalar_one_or_none() is None:
            raise SellpointValueVersionNotFoundError(
                f"sellpoint value source batch not found: {batch_id}"
            )

    def update_version_progress(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        sku_count: int,
        ready_count: int,
        review_required_count: int,
        blocked_count: int,
        failed_count: int,
        quality_summary_json: Mapping[str, Any],
        validation_summary_json: Mapping[str, Any],
        release_quality_status: SellpointValueReleaseQualityStatus,
        processing_status: str,
        review_required: bool,
        review_status: str,
        review_reason_json: Mapping[str, Any] | None = None,
    ) -> SellpointValueVersionRecord:
        version = self._version_by_id(
            sellpoint_value_profile_version_id,
            for_update=True,
        )
        self._assert_draft_version(version)
        counts = {
            "sku_count": sku_count,
            "ready_count": ready_count,
            "review_required_count": review_required_count,
            "blocked_count": blocked_count,
            "failed_count": failed_count,
        }
        if any(value < 0 for value in counts.values()):
            raise ValueError("version progress counts cannot be negative")
        if ready_count + review_required_count + blocked_count + failed_count > sku_count:
            raise ValueError("version progress status counts cannot exceed sku_count")
        for field_name, value in counts.items():
            setattr(version, field_name, value)
        version.quality_summary_json = dict(quality_summary_json)
        version.validation_summary_json = dict(validation_summary_json)
        version.release_quality_status = _enum_value(release_quality_status)
        version.processing_status = processing_status
        version.review_required = review_required
        version.review_status = review_status
        version.review_reason_json = dict(review_reason_json or {})
        self.db.flush()
        return SellpointValueVersionRecord.model_validate(version)

    def publish_version(
        self,
        *,
        sellpoint_value_profile_version_id: str,
        published_by: str,
        allow_limited: bool = False,
        release_note_cn: str | None = None,
    ) -> SellpointValueVersionRecord:
        if not published_by.strip() or published_by.strip().lower() == "system":
            raise SellpointValuePublishNotAllowedError(
                "publishing requires an explicit non-system approver"
            )
        initial = self._version_by_id(
            sellpoint_value_profile_version_id,
            for_update=False,
        )
        self._lock_batch_release_scope(initial.batch_id)
        version = self._version_by_id(
            sellpoint_value_profile_version_id,
            for_update=True,
        )
        if version.release_status != "reviewed" or version.is_current:
            raise SellpointValuePublishNotAllowedError(
                "only reviewed non-current versions can be published"
            )
        quality = str(version.release_quality_status)
        if quality == "blocked" or quality == "unassessed":
            raise SellpointValuePublishNotAllowedError(
                f"release quality {quality} cannot be published"
            )
        if quality == "limited" and not allow_limited:
            raise SellpointValuePublishNotAllowedError(
                "limited release requires explicit allow_limited approval"
            )
        self._assert_publish_completeness(version)

        scope_filter = (
            entities.Core3SellpointValueProfileVersion.project_id
            == self.project_id,
            entities.Core3SellpointValueProfileVersion.category_code
            == self.category_code.value,
            entities.Core3SellpointValueProfileVersion.batch_id == version.batch_id,
        )
        self.db.execute(
            update(entities.Core3SellpointValueProfileVersion)
            .where(*scope_filter)
            .where(
                entities.Core3SellpointValueProfileVersion.sellpoint_value_profile_version_id
                != version.sellpoint_value_profile_version_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.release_status
                == "published"
            )
            .where(entities.Core3SellpointValueProfileVersion.is_current.is_(True))
            .values(is_current=False)
        )
        self._clear_other_current_children(version)
        version.release_status = "published"
        version.is_current = True
        version.published_at = datetime.now(timezone.utc)
        version.published_by = published_by
        if release_note_cn is not None:
            version.release_note_cn = release_note_cn
        self._update_child_release_status(
            version.sellpoint_value_profile_version_id,
            release_status="published",
            is_current=True,
        )
        self.db.flush()
        return SellpointValueVersionRecord.model_validate(version)

    def _assert_publish_completeness(
        self,
        version: entities.Core3SellpointValueProfileVersion,
    ) -> None:
        actual_profile_count = int(
            self.db.scalar(
                select(func.count())
                .select_from(entities.Core3SkuSellpointValueProfile)
                .where(
                    entities.Core3SkuSellpointValueProfile.project_id
                    == self.project_id
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.category_code
                    == self.category_code.value
                )
                .where(
                    entities.Core3SkuSellpointValueProfile.sellpoint_value_profile_version_id
                    == version.sellpoint_value_profile_version_id
                )
            )
            or 0
        )
        counted = (
            version.ready_count
            + version.review_required_count
            + version.blocked_count
            + version.failed_count
        )
        violations = []
        if version.processing_status != "completed":
            violations.append("generation_not_completed")
        if version.sku_count <= 0:
            violations.append("authoritative_sku_count_empty")
        if actual_profile_count != version.sku_count:
            violations.append("profile_count_mismatch")
        if counted != version.sku_count:
            violations.append("status_count_mismatch")
        if version.failed_count or version.blocked_count:
            violations.append("failed_or_blocked_profiles_present")
        if version.release_quality_status == "ready" and (
            version.ready_count != version.sku_count
            or version.review_required_count
        ):
            violations.append("ready_release_not_fully_ready")
        if version.release_quality_status == "limited" and (
            version.review_required_count <= 0
            or version.ready_count + version.review_required_count
            != version.sku_count
        ):
            violations.append("limited_release_counts_invalid")
        if violations:
            raise SellpointValuePublishNotAllowedError(
                "profile version is incomplete: " + ",".join(violations)
            )

    def _find_version(
        self,
        *,
        batch_id: str,
        profile_version: str,
        rule_version: str,
    ) -> entities.Core3SellpointValueProfileVersion | None:
        stmt = (
            select(entities.Core3SellpointValueProfileVersion)
            .where(
                entities.Core3SellpointValueProfileVersion.project_id
                == self.project_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.category_code
                == self.category_code.value
            )
            .where(
                _batch_scope_filter(
                    entities.Core3SellpointValueProfileVersion.batch_id,
                    batch_id,
                )
            )
            .where(
                entities.Core3SellpointValueProfileVersion.profile_version
                == profile_version
            )
            .where(
                entities.Core3SellpointValueProfileVersion.rule_version
                == rule_version
            )
        )
        return self.db.execute(
            stmt.order_by(
                _batch_scope_order(
                    entities.Core3SellpointValueProfileVersion.batch_id,
                    batch_id,
                )
            )
        ).scalars().first()

    def _find_current_published_version(
        self,
        *,
        batch_id: str,
    ) -> entities.Core3SellpointValueProfileVersion | None:
        stmt = (
            select(entities.Core3SellpointValueProfileVersion)
            .where(
                entities.Core3SellpointValueProfileVersion.project_id
                == self.project_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.category_code
                == self.category_code.value
            )
            .where(
                _batch_scope_filter(
                    entities.Core3SellpointValueProfileVersion.batch_id,
                    batch_id,
                )
            )
            .where(
                entities.Core3SellpointValueProfileVersion.release_status
                == "published"
            )
            .where(entities.Core3SellpointValueProfileVersion.is_current.is_(True))
            .order_by(
                _batch_scope_order(
                    entities.Core3SellpointValueProfileVersion.batch_id,
                    batch_id,
                ),
                entities.Core3SellpointValueProfileVersion.published_at.desc()
            )
        )
        return self.db.execute(stmt).scalars().first()

    def _version_by_id(
        self,
        version_id: str,
        *,
        for_update: bool = False,
    ) -> entities.Core3SellpointValueProfileVersion:
        stmt = (
            select(entities.Core3SellpointValueProfileVersion)
            .where(
                entities.Core3SellpointValueProfileVersion.project_id
                == self.project_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.category_code
                == self.category_code.value
            )
            .where(
                entities.Core3SellpointValueProfileVersion.sellpoint_value_profile_version_id
                == version_id
            )
        )
        if for_update:
            stmt = stmt.with_for_update()
        row = self.db.execute(stmt).scalars().first()
        if row is None:
            raise SellpointValueVersionNotFoundError(
                f"sellpoint value profile version not found: {version_id}"
            )
        return row

    def _find_profile(
        self,
        *,
        batch_id: str,
        profile_version: str,
        sku_code: str,
        rule_version: str,
    ) -> entities.Core3SkuSellpointValueProfile | None:
        stmt = (
            select(entities.Core3SkuSellpointValueProfile)
            .where(
                entities.Core3SkuSellpointValueProfile.project_id
                == self.project_id
            )
            .where(
                entities.Core3SkuSellpointValueProfile.category_code
                == self.category_code.value
            )
            .where(entities.Core3SkuSellpointValueProfile.batch_id == batch_id)
            .where(
                entities.Core3SkuSellpointValueProfile.profile_version
                == profile_version
            )
            .where(entities.Core3SkuSellpointValueProfile.sku_code == sku_code)
            .where(
                entities.Core3SkuSellpointValueProfile.rule_version
                == rule_version
            )
        )
        return self.db.execute(stmt).scalars().first()

    def _profile_by_id(
        self, profile_id: str
    ) -> entities.Core3SkuSellpointValueProfile:
        stmt = (
            select(entities.Core3SkuSellpointValueProfile)
            .where(
                entities.Core3SkuSellpointValueProfile.project_id
                == self.project_id
            )
            .where(
                entities.Core3SkuSellpointValueProfile.category_code
                == self.category_code.value
            )
            .where(
                entities.Core3SkuSellpointValueProfile.sku_sellpoint_value_profile_id
                == profile_id
            )
        )
        row = self.db.execute(stmt).scalars().first()
        if row is None:
            raise SellpointValueProfileNotFoundError(
                f"sellpoint value SKU profile not found: {profile_id}"
            )
        return row

    def _read_bundle(
        self,
        version: entities.Core3SellpointValueProfileVersion,
        profile: entities.Core3SkuSellpointValueProfile,
    ) -> SellpointValueProfileReadBundle:
        profile_id = profile.sku_sellpoint_value_profile_id
        candidates = list(
            self.db.execute(
                select(entities.Core3SkuSellpointValueCandidate)
                .where(
                    entities.Core3SkuSellpointValueCandidate.sku_sellpoint_value_profile_id
                    == profile_id
                )
                .order_by(
                    entities.Core3SkuSellpointValueCandidate.pool_type,
                    entities.Core3SkuSellpointValueCandidate.candidate_sku_code,
                )
            ).scalars()
        )
        value_items = list(
            self.db.execute(
                select(entities.Core3SkuSellpointValueItem)
                .where(
                    entities.Core3SkuSellpointValueItem.sku_sellpoint_value_profile_id
                    == profile_id
                )
                .order_by(
                    entities.Core3SkuSellpointValueItem.battlefield_code,
                    entities.Core3SkuSellpointValueItem.normalized_bundle_code,
                )
            ).scalars()
        )
        return SellpointValueProfileReadBundle(
            version=SellpointValueVersionRecord.model_validate(version),
            profile=SkuSellpointValueProfileRecord.model_validate(profile),
            candidates=[
                SkuSellpointValueCandidateRecord.model_validate(row)
                for row in candidates
            ],
            value_items=[
                SkuSellpointValueItemRecord.model_validate(row)
                for row in value_items
            ],
        )

    def _assert_existing_children_match(
        self,
        profile: entities.Core3SkuSellpointValueProfile,
        bundle: SellpointValueDraftBundle,
    ) -> None:
        existing = self._read_bundle(
            self._version_by_id(profile.sellpoint_value_profile_version_id),
            profile,
        )
        expected_candidates = {
            (row.candidate_sku_code, row.pool_type): row.result_hash
            for row in bundle.candidates
        }
        actual_candidates = {
            (row.candidate_sku_code, row.pool_type): row.result_hash
            for row in existing.candidates
        }
        expected_items = {
            (row.battlefield_code, row.normalized_bundle_code): row.result_hash
            for row in bundle.value_items
        }
        actual_items = {
            (row.battlefield_code, row.normalized_bundle_code): row.result_hash
            for row in existing.value_items
        }
        if expected_candidates != actual_candidates or expected_items != actual_items:
            raise SellpointValueImmutableVersionError(
                "draft child rows differ from the immutable existing profile"
            )

    def _assert_context_scope(self, project_id: str, category_code: str) -> None:
        if project_id != self.project_id or category_code != self.category_code.value:
            raise ValueError("payload project/category scope does not match repository")

    def _assert_draft_version(
        self, version: entities.Core3SellpointValueProfileVersion
    ) -> None:
        if version.release_status != "draft" or version.is_current:
            raise SellpointValueDraftWriteNotAllowedError(
                "write_draft requires a non-current draft version"
            )

    @staticmethod
    def _assert_version_matches_profile(
        version: entities.Core3SellpointValueProfileVersion,
        profile: Any,
    ) -> None:
        for field_name in (
            "project_id",
            "category_code",
            "batch_id",
            "product_category",
            "profile_version",
            "schema_version",
            "rule_version",
            "method_version",
        ):
            if getattr(version, field_name) != getattr(profile, field_name):
                raise ValueError(f"profile {field_name} must match version")

    def _update_child_release_status(
        self,
        version_id: str,
        *,
        release_status: str,
        is_current: bool,
    ) -> None:
        for model in (
            entities.Core3SkuSellpointValueProfile,
            entities.Core3SkuSellpointValueCandidate,
            entities.Core3SkuSellpointValueItem,
        ):
            self.db.execute(
                update(model)
                .where(model.project_id == self.project_id)
                .where(model.category_code == self.category_code.value)
                .where(model.sellpoint_value_profile_version_id == version_id)
                .values(release_status=release_status, is_current=is_current)
            )

    def _clear_other_current_children(
        self, version: entities.Core3SellpointValueProfileVersion
    ) -> None:
        for model in (
            entities.Core3SkuSellpointValueProfile,
            entities.Core3SkuSellpointValueCandidate,
            entities.Core3SkuSellpointValueItem,
        ):
            self.db.execute(
                update(model)
                .where(model.project_id == self.project_id)
                .where(model.category_code == self.category_code.value)
                .where(model.batch_id == version.batch_id)
                .where(
                    model.sellpoint_value_profile_version_id
                    != version.sellpoint_value_profile_version_id
                )
                .where(model.is_current.is_(True))
                .values(is_current=False)
            )


def _entity_payload(payload: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        raw = payload.model_dump(mode="python")
    else:
        raw = dict(payload)
    return {key: _jsonable(value) for key, value in raw.items()}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, BaseModel):
        return {
            key: _jsonable(item)
            for key, item in value.model_dump(mode="python").items()
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def _enum_value(value: Enum | str) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def _batch_scope_filter(column: Any, batch_id: str) -> Any:
    batch_ids = batch_ids_from_scope(batch_id)
    anchor_batch_id = batch_ids[0] if batch_ids else batch_id
    return column == anchor_batch_id


def _batch_scope_order(column: Any, batch_id: str) -> Any:
    batch_ids = batch_ids_from_scope(batch_id)
    return case(
        {scope_batch_id: index for index, scope_batch_id in enumerate(batch_ids)},
        value=column,
        else_=len(batch_ids),
    )


__all__ = [
    "SellpointValueDraftWriteNotAllowedError",
    "SellpointValueImmutableVersionError",
    "SellpointValueProfileNotFoundError",
    "SellpointValueProfileRepository",
    "SellpointValueProfileRepositoryError",
    "SellpointValuePublishNotAllowedError",
    "SellpointValueVersionNotFoundError",
]
