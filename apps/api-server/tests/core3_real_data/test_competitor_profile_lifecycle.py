from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_lifecycle import (
    CHILD_MODELS,
    CompetitorProfileCurrentSwitchConflictError,
    CompetitorProfileCurrentSwitchNotAllowedError,
    CompetitorProfileDeprecateNotAllowedError,
    CompetitorProfileLifecycleService,
    CompetitorProfilePublishNotAllowedError,
    CompetitorProfileReviewNotAllowedError,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfilePersistenceBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileDraftWriteNotAllowedError,
    CompetitorProfileVersionNotFoundError,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    ReleaseQualityStatus,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_competitor_profile_repository import (
    _bundle,
    _repository,
    _version_payload,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    profile_tables = (
        entities.Core3CompetitorProfileVersion.__table__,
        entities.Core3SkuCompetitorProfile.__table__,
        entities.Core3SkuCompetitorProfilePair.__table__,
        entities.Core3SkuCompetitorProfileRelation.__table__,
        entities.Core3SkuCompetitorProfileSelection.__table__,
    )
    with engine.begin() as connection:
        entities.CategoryProject.__table__.create(bind=connection)
        entities.Core3V2PipelineRun.__table__.create(bind=connection)
        entities.Core3V2ModuleRun.__table__.create(bind=connection)
        entities.Core3SourceBatch.__table__.create(bind=connection)
        for table in profile_tables:
            table.create(bind=connection)
        connection.execute(
            entities.CategoryProject.__table__.insert(),
            [
                {"project_id": "project-tv", "name": "TV", "category_code": "TV"},
                {"project_id": "project-ac", "name": "AC", "category_code": "AC"},
            ],
        )
        for batch_id, project_id, category in (
            ("batch-1", "project-tv", "TV"),
            ("batch-2", "project-tv", "TV"),
            ("batch-ac", "project-ac", "AC"),
        ):
            connection.execute(
                entities.Core3SourceBatch.__table__.insert().values(
                    batch_id=batch_id,
                    project_id=project_id,
                    category_code=category,
                    source_system="fixture",
                    source_database="fixture",
                    source_tables=[],
                    ruleset_version="rules-v1",
                    module_version="module-v1",
                    hash_version="hash-v1",
                    scan_started_at=datetime.now(timezone.utc),
                    status="completed",
                )
            )
    db = Session(engine, autoflush=False, future=True)
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _lifecycle(session: Session) -> CompetitorProfileLifecycleService:
    return CompetitorProfileLifecycleService(
        Core3RepositoryContext(
            db=session,
            project_id="project-tv",
            category_code=Core3CategoryCode.TV,
        )
    )


def _version_and_bundle(
    session: Session,
    *,
    suffix: str = "v1",
    partial: bool = False,
) -> tuple[str, CompetitorProfilePersistenceBundle]:
    repository = _repository(session)
    version = repository.create_version(
        _version_payload(
            profile_version=f"competitor-profile-{suffix}",
            input_fingerprint=f"version-input-{suffix}",
            candidate_universe_fingerprint=f"candidate-input-{suffix}",
            result_hash=f"version-result-{suffix}",
            ready_count=0 if partial else 1,
            partial_count=1 if partial else 0,
            review_required=partial,
            review_status="review_required" if partial else "unassessed",
        )
    )
    payload = _bundle(version.competitor_profile_version_id).model_dump(mode="python")
    for row in (
        payload["profile"],
        *payload["pairs"],
        *payload["relations"],
        *payload["selections"],
    ):
        row["profile_version"] = f"competitor-profile-{suffix}"
    if partial:
        payload["profile"]["review_required"] = True
        payload["profile"]["review_status"] = "review_required"
        profile = payload["profile"]["profile_payload"]
        profile["analysis_state"] = "partial"
        profile["conclusion_state"] = "insufficient_evidence"
        profile["review_required"] = True
        profile["review_status"] = "review_required"
        profile["no_conclusion_reason"] = {"reason_cn": "部分关键用户价值证据缺失。"}
    bundle = CompetitorProfilePersistenceBundle(**payload)
    repository.write_draft(bundle)
    return version.competitor_profile_version_id, bundle


def _review_ready(
    lifecycle: CompetitorProfileLifecycleService,
    version_id: str,
) -> None:
    lifecycle.review_version(
        competitor_profile_version_id=version_id,
        reviewed_by="reviewer-a",
        release_quality_status=ReleaseQualityStatus.READY,
    )


def _publish_ready(
    lifecycle: CompetitorProfileLifecycleService,
    version_id: str,
) -> None:
    _review_ready(lifecycle, version_id)
    lifecycle.publish_version(
        competitor_profile_version_id=version_id,
        published_by="publisher-a",
        release_note_cn="通过发布门禁。",
    )


def _child_states(
    session: Session,
    version_id: str,
) -> list[tuple[str, bool]]:
    states: list[tuple[str, bool]] = []
    for model in CHILD_MODELS:
        states.extend(
            session.execute(
                select(model.release_status, model.is_current).where(
                    model.competitor_profile_version_id == version_id
                )
            ).all()
        )
    return states


def test_review_ready_freezes_all_analytical_rows_and_is_idempotent(
    session: Session,
) -> None:
    version_id, bundle = _version_and_bundle(session)
    lifecycle = _lifecycle(session)

    reviewed = lifecycle.review_version(
        competitor_profile_version_id=version_id,
        reviewed_by="reviewer-a",
        release_quality_status=ReleaseQualityStatus.READY,
    )
    repeated = lifecycle.review_version(
        competitor_profile_version_id=version_id,
        reviewed_by="reviewer-a",
        release_quality_status=ReleaseQualityStatus.READY,
    )

    assert reviewed.release_status == "review"
    assert reviewed.release_quality_status == "ready"
    assert repeated.competitor_profile_version_id == version_id
    assert set(_child_states(session, version_id)) == {("review", False)}
    with pytest.raises(CompetitorProfileDraftWriteNotAllowedError):
        _repository(session).write_draft(bundle)
    with pytest.raises(CompetitorProfileReviewNotAllowedError):
        lifecycle.review_version(
            competitor_profile_version_id=version_id,
            reviewed_by="reviewer-b",
            release_quality_status=ReleaseQualityStatus.READY,
        )


def test_review_detects_hash_mismatch_and_records_blocked_review(
    session: Session,
) -> None:
    version_id, _ = _version_and_bundle(session)
    pair = session.execute(
        select(entities.Core3SkuCompetitorProfilePair).where(
            entities.Core3SkuCompetitorProfilePair.competitor_profile_version_id
            == version_id
        )
    ).scalar_one()
    pair.result_hash = "tampered"
    session.flush()
    lifecycle = _lifecycle(session)

    with pytest.raises(
        CompetitorProfileReviewNotAllowedError,
        match="pair_hash_mismatch",
    ):
        _review_ready(lifecycle, version_id)
    assert lifecycle.repository.get_version_by_id(version_id).release_status == "draft"

    blocked = lifecycle.review_version(
        competitor_profile_version_id=version_id,
        reviewed_by="reviewer-a",
        release_quality_status=ReleaseQualityStatus.BLOCKED,
    )
    assert blocked.release_status == "review"
    assert blocked.release_quality_status == "blocked"
    assert "pair_hash_mismatch" in blocked.review_reasons


def test_publish_does_not_switch_current_and_requires_human_review(
    session: Session,
) -> None:
    version_id, _ = _version_and_bundle(session)
    lifecycle = _lifecycle(session)

    with pytest.raises(CompetitorProfilePublishNotAllowedError):
        lifecycle.publish_version(
            competitor_profile_version_id=version_id,
            published_by="publisher-a",
        )
    _review_ready(lifecycle, version_id)
    with pytest.raises(ValueError, match="non-system"):
        lifecycle.publish_version(
            competitor_profile_version_id=version_id,
            published_by="system",
        )

    published = lifecycle.publish_version(
        competitor_profile_version_id=version_id,
        published_by="publisher-a",
        release_note_cn="通过发布门禁。",
    )
    repeated = lifecycle.publish_version(
        competitor_profile_version_id=version_id,
        published_by="publisher-a",
        release_note_cn="通过发布门禁。",
    )
    assert published.release_status == "published"
    assert published.is_current is False
    assert repeated.is_current is False
    assert set(_child_states(session, version_id)) == {("published", False)}


def test_limited_release_requires_partial_coverage_and_explicit_approval(
    session: Session,
) -> None:
    version_id, _ = _version_and_bundle(session, suffix="limited", partial=True)
    lifecycle = _lifecycle(session)
    reviewed = lifecycle.review_version(
        competitor_profile_version_id=version_id,
        reviewed_by="reviewer-a",
        release_quality_status=ReleaseQualityStatus.LIMITED,
    )
    assert reviewed.review_required is True
    assert reviewed.review_reasons == ["partial_profiles_present"]

    with pytest.raises(CompetitorProfilePublishNotAllowedError, match="allow_limited"):
        lifecycle.publish_version(
            competitor_profile_version_id=version_id,
            published_by="publisher-a",
        )
    published = lifecycle.publish_version(
        competitor_profile_version_id=version_id,
        published_by="publisher-a",
        allow_limited=True,
    )
    assert published.release_quality_status == "limited"
    assert published.is_current is False


def test_current_switch_uses_cas_and_updates_all_children_atomically(
    session: Session,
) -> None:
    first_id, _ = _version_and_bundle(session, suffix="v1")
    second_id, _ = _version_and_bundle(session, suffix="v2")
    lifecycle = _lifecycle(session)
    _publish_ready(lifecycle, first_id)
    _publish_ready(lifecycle, second_id)

    first = lifecycle.set_current_version(
        competitor_profile_version_id=first_id,
        current_by="approver-a",
        expected_current_version_id=None,
    )
    second = lifecycle.set_current_version(
        competitor_profile_version_id=second_id,
        current_by="approver-b",
        expected_current_version_id=first_id,
    )
    repeated = lifecycle.set_current_version(
        competitor_profile_version_id=second_id,
        current_by="approver-b",
        expected_current_version_id=first_id,
    )

    assert first.is_current is True
    assert second.is_current is True
    assert repeated.is_current is True
    assert lifecycle.repository.get_version_by_id(first_id).is_current is False
    assert set(_child_states(session, first_id)) == {("published", False)}
    assert set(_child_states(session, second_id)) == {("published", True)}


def test_current_cas_conflict_leaves_existing_current_unchanged(
    session: Session,
) -> None:
    first_id, _ = _version_and_bundle(session, suffix="v1")
    second_id, _ = _version_and_bundle(session, suffix="v2")
    lifecycle = _lifecycle(session)
    _publish_ready(lifecycle, first_id)
    _publish_ready(lifecycle, second_id)
    lifecycle.set_current_version(
        competitor_profile_version_id=first_id,
        current_by="approver-a",
        expected_current_version_id=None,
    )

    with pytest.raises(CompetitorProfileCurrentSwitchConflictError):
        lifecycle.set_current_version(
            competitor_profile_version_id=second_id,
            current_by="approver-b",
            expected_current_version_id=None,
        )
    assert lifecycle.repository.get_version_by_id(first_id).is_current is True
    assert lifecycle.repository.get_version_by_id(second_id).is_current is False
    assert set(_child_states(session, first_id)) == {("published", True)}


def test_current_switch_failure_rolls_back_before_exposing_new_state(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id, _ = _version_and_bundle(session, suffix="v1")
    second_id, _ = _version_and_bundle(session, suffix="v2")
    lifecycle = _lifecycle(session)
    _publish_ready(lifecycle, first_id)
    _publish_ready(lifecycle, second_id)
    lifecycle.set_current_version(
        competitor_profile_version_id=first_id,
        current_by="approver-a",
        expected_current_version_id=None,
    )
    original = lifecycle._update_child_release_state

    def fail_new_current(
        version_id: str,
        **kwargs: Any,
    ) -> None:
        original(version_id, **kwargs)
        if version_id == second_id and kwargs.get("is_current") is True:
            raise RuntimeError("injected current-child failure")

    monkeypatch.setattr(lifecycle, "_update_child_release_state", fail_new_current)
    with pytest.raises(RuntimeError, match="injected"):
        lifecycle.set_current_version(
            competitor_profile_version_id=second_id,
            current_by="approver-b",
            expected_current_version_id=first_id,
        )

    session.expire_all()
    assert lifecycle.repository.get_version_by_id(first_id).is_current is True
    assert lifecycle.repository.get_version_by_id(second_id).is_current is False
    assert set(_child_states(session, first_id)) == {("published", True)}
    assert set(_child_states(session, second_id)) == {("published", False)}


def test_deprecate_preserves_history_but_refuses_current_version(
    session: Session,
) -> None:
    first_id, _ = _version_and_bundle(session, suffix="v1")
    second_id, _ = _version_and_bundle(session, suffix="v2")
    lifecycle = _lifecycle(session)
    _publish_ready(lifecycle, first_id)
    _publish_ready(lifecycle, second_id)
    lifecycle.set_current_version(
        competitor_profile_version_id=first_id,
        current_by="approver-a",
        expected_current_version_id=None,
    )
    with pytest.raises(CompetitorProfileDeprecateNotAllowedError):
        lifecycle.deprecate_version(
            competitor_profile_version_id=first_id,
            deprecated_by="approver-a",
            reason_cn="已有替代版本。",
        )

    lifecycle.set_current_version(
        competitor_profile_version_id=second_id,
        current_by="approver-b",
        expected_current_version_id=first_id,
    )
    deprecated = lifecycle.deprecate_version(
        competitor_profile_version_id=first_id,
        deprecated_by="approver-a",
        reason_cn="已有替代版本。",
    )
    repeated = lifecycle.deprecate_version(
        competitor_profile_version_id=first_id,
        deprecated_by="approver-a",
        reason_cn="已有替代版本。",
    )
    assert deprecated.release_status == "deprecated"
    assert repeated.release_status == "deprecated"
    assert "下线原因：已有替代版本。" in (deprecated.release_note_cn or "")
    assert set(_child_states(session, first_id)) == {("deprecated", False)}


def test_invalid_transition_and_cross_scope_lookup_are_rejected(
    session: Session,
) -> None:
    version_id, _ = _version_and_bundle(session)
    lifecycle = _lifecycle(session)
    with pytest.raises(CompetitorProfileCurrentSwitchNotAllowedError):
        lifecycle.set_current_version(
            competitor_profile_version_id=version_id,
            current_by="approver-a",
            expected_current_version_id=None,
        )
    with pytest.raises(CompetitorProfileReviewNotAllowedError, match="ready, limited"):
        lifecycle.review_version(
            competitor_profile_version_id=version_id,
            reviewed_by="reviewer-a",
            release_quality_status=ReleaseQualityStatus.UNASSESSED,
        )
    with pytest.raises(CompetitorProfileReviewNotAllowedError, match="ready, limited"):
        lifecycle.review_version(
            competitor_profile_version_id=version_id,
            reviewed_by="reviewer-a",
            release_quality_status="invalid-quality",  # type: ignore[arg-type]
        )

    ac_lifecycle = CompetitorProfileLifecycleService(
        Core3RepositoryContext(
            db=session,
            project_id="project-ac",
            category_code=Core3CategoryCode.AC,
        )
    )
    with pytest.raises(CompetitorProfileVersionNotFoundError):
        ac_lifecycle.review_version(
            competitor_profile_version_id=version_id,
            reviewed_by="reviewer-a",
            release_quality_status=ReleaseQualityStatus.READY,
        )


def test_selection_rank_and_relation_cardinality_are_review_gates(
    session: Session,
) -> None:
    version_id, _ = _version_and_bundle(session)
    relation = (
        session.execute(
            select(entities.Core3SkuCompetitorProfileRelation).where(
                entities.Core3SkuCompetitorProfileRelation.competitor_profile_version_id
                == version_id
            )
        )
        .scalars()
        .first()
    )
    assert relation is not None
    session.delete(relation)
    session.execute(
        update(entities.Core3CompetitorProfileVersion)
        .where(
            entities.Core3CompetitorProfileVersion.competitor_profile_version_id
            == version_id
        )
        .values(relation_count=6)
    )
    session.flush()

    with pytest.raises(
        CompetitorProfileReviewNotAllowedError,
        match="pair_relation_cardinality_invalid",
    ):
        _review_ready(_lifecycle(session), version_id)


def test_g21_quality_freshness_and_diff_entrypoints_are_read_only(
    session: Session,
) -> None:
    before_id, _ = _version_and_bundle(session, suffix="g21-before")
    after_id, _ = _version_and_bundle(session, suffix="g21-after")
    lifecycle = _lifecycle(session)
    repository = _repository(session)
    before_read = repository.get_profile(
        competitor_profile_version_id=before_id,
        target_sku_code="TV-TARGET",
    )
    assert before_read is not None
    before_version = repository.get_version_by_id(before_id)
    after_version = repository.get_version_by_id(after_id)
    frozen_versions = (
        before_version.model_dump(mode="python"),
        after_version.model_dump(mode="python"),
    )

    quality = lifecycle.assess_version_quality(
        competitor_profile_version_id=before_id,
        authoritative_sku_codes=["TV-TARGET"],
        profiles=[before_read],
    )
    freshness = lifecycle.assess_version_freshness(
        competitor_profile_version_id=before_id,
        current_serving_scope=before_version.serving_scope,
    )
    diff = lifecycle.diff_profiles(
        from_competitor_profile_version_id=before_id,
        to_competitor_profile_version_id=after_id,
        target_sku_code="TV-TARGET",
    )

    assert quality.release_quality_status == "blocked"
    assert "authoritative_manifest_hash_mismatch" in {
        row.issue_code for row in quality.issues
    }
    assert freshness.freshness_status == "current"
    assert diff.has_changes is False
    assert diff.change_summary_cn == ["两个版本的竞品画像业务结论一致。"]
    assert (
        repository.get_version_by_id(before_id).model_dump(mode="python")
        == (frozen_versions[0])
    )
    assert (
        repository.get_version_by_id(after_id).model_dump(mode="python")
        == (frozen_versions[1])
    )
