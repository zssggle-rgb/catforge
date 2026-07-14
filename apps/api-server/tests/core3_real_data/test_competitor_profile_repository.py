from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfilePersistenceBundle,
    CompetitorProfileVersionDraftCreate,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileDraftWriteNotAllowedError,
    CompetitorProfileImmutableError,
    CompetitorProfileRepository,
    CompetitorProfileVersionNotFoundError,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_competitor_profile_schemas import (
    _persistence_bundle,
    _scope,
)


PROFILE_TABLES = (
    entities.Core3CompetitorProfileVersion.__table__,
    entities.Core3SkuCompetitorProfile.__table__,
    entities.Core3SkuCompetitorProfilePair.__table__,
    entities.Core3SkuCompetitorProfileRelation.__table__,
    entities.Core3SkuCompetitorProfileSelection.__table__,
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

    with engine.begin() as connection:
        entities.CategoryProject.__table__.create(bind=connection)
        entities.Core3V2PipelineRun.__table__.create(bind=connection)
        entities.Core3V2ModuleRun.__table__.create(bind=connection)
        entities.Core3SourceBatch.__table__.create(bind=connection)
        for table in PROFILE_TABLES:
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


def _repository(session: Session) -> CompetitorProfileRepository:
    return CompetitorProfileRepository(
        Core3RepositoryContext(
            db=session,
            project_id="project-tv",
            category_code=Core3CategoryCode.TV,
        )
    )


def _version_payload(**updates) -> CompetitorProfileVersionDraftCreate:
    payload = {
        "project_id": "project-tv",
        "category_code": "TV",
        "product_category": "TV",
        "storage_batch_id": "batch-2",
        "release_scope_key": "scope-tv",
        "profile_version": "competitor-profile-v1",
        "method_versions_json": {"recall": "v1", "relations": "v1"},
        "serving_scope": _scope(),
        "sku_count": 1,
        "ready_count": 1,
        "pair_count": 1,
        "relation_count": 7,
        "selection_count": 1,
        "input_fingerprint": "version-input",
        "candidate_universe_fingerprint": "candidate-input",
        "result_hash": "version-result",
        "processing_status": "completed",
    }
    payload.update(updates)
    return CompetitorProfileVersionDraftCreate(**payload)


def _bundle(version_id: str) -> CompetitorProfilePersistenceBundle:
    payload = _persistence_bundle().model_dump(mode="python")
    payload["profile"]["competitor_profile_version_id"] = version_id
    for group in ("pairs", "relations", "selections"):
        for row in payload[group]:
            row["competitor_profile_version_id"] = version_id
    return CompetitorProfilePersistenceBundle(**payload)


def test_create_version_is_idempotent_and_conflicting_inputs_are_rejected(
    session: Session,
) -> None:
    repository = _repository(session)
    first = repository.create_version(_version_payload())
    second = repository.create_version(_version_payload())

    assert first.competitor_profile_version_id == second.competitor_profile_version_id
    with pytest.raises(CompetitorProfileImmutableError):
        repository.create_version(_version_payload(input_fingerprint="different"))


def test_write_draft_round_trips_all_five_tables(session: Session) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    readback = repository.write_draft(
        _bundle(version.competitor_profile_version_id)
    )

    assert readback.preview is True
    assert readback.version.profile_version == "competitor-profile-v1"
    assert readback.profile.target_sku_code == "TV-TARGET"
    assert readback.profile.sku_competitor_profile_id
    assert len(readback.pairs) == 1
    assert readback.pairs[0].sku_competitor_profile_pair_id
    assert len(readback.relations) == 7
    assert all(row.sku_competitor_profile_relation_id for row in readback.relations)
    assert len(readback.selections) == 1
    assert readback.selections[0].selection_rank == 1


def test_write_same_draft_is_idempotent_and_child_change_is_immutable(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    bundle = _bundle(version.competitor_profile_version_id)
    first = repository.write_draft(bundle)
    second = repository.write_draft(bundle)
    assert first.profile.sku_competitor_profile_id == second.profile.sku_competitor_profile_id

    payload = bundle.model_dump(mode="python")
    payload["pairs"][0]["result_hash"] = "different-child"
    payload["pairs"][0]["pair_payload"]["result_hash"] = "different-child"
    with pytest.raises(CompetitorProfileImmutableError):
        repository.write_draft(CompetitorProfilePersistenceBundle(**payload))


def test_repository_lists_progress_pairs_relations_and_selections(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    readback = repository.write_draft(
        _bundle(version.competitor_profile_version_id)
    )
    profile_id = readback.profile.sku_competitor_profile_id
    pair_id = readback.pairs[0].sku_competitor_profile_pair_id
    assert profile_id and pair_id

    progress = repository.list_profile_progress(
        competitor_profile_version_id=version.competitor_profile_version_id
    )
    assert progress == [
        {
            "sku_competitor_profile_id": profile_id,
            "target_sku_code": "TV-TARGET",
            "analysis_state": "ready",
            "conclusion_state": "available",
            "review_required": False,
            "result_hash": "profile-result",
        }
    ]
    assert len(repository.list_pairs(sku_competitor_profile_id=profile_id)) == 1
    assert len(
        repository.list_pairs(
            sku_competitor_profile_id=profile_id,
            candidate_status="eligible",
            selected_only=True,
        )
    ) == 1
    assert len(
        repository.list_relations(sku_competitor_profile_pair_id=pair_id)
    ) == 7
    assert len(
        repository.list_relations(
            sku_competitor_profile_pair_id=pair_id,
            relation_status="passed",
        )
    ) == 1
    assert len(repository.list_selections(sku_competitor_profile_id=profile_id)) == 1


def test_list_versions_and_get_profile_are_scoped(session: Session) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    repository.write_draft(_bundle(version.competitor_profile_version_id))

    versions = repository.list_versions(release_scope_key="scope-tv")
    assert [row.profile_version for row in versions] == ["competitor-profile-v1"]
    assert repository.get_version(
        release_scope_key="scope-tv",
        profile_version="competitor-profile-v1",
        rule_version="competitor_profile_materializer_v1",
    ) is not None
    assert repository.get_profile(
        competitor_profile_version_id=version.competitor_profile_version_id,
        target_sku_code="TV-TARGET",
    ) is not None
    assert repository.get_profile(
        competitor_profile_version_id=version.competitor_profile_version_id,
        target_sku_code="TV-MISSING",
    ) is None


def test_non_draft_version_rejects_profile_writes(session: Session) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    session.execute(
        update(entities.Core3CompetitorProfileVersion)
        .where(
            entities.Core3CompetitorProfileVersion.competitor_profile_version_id
            == version.competitor_profile_version_id
        )
        .values(release_status="review")
    )
    session.flush()

    with pytest.raises(CompetitorProfileDraftWriteNotAllowedError):
        repository.write_draft(_bundle(version.competitor_profile_version_id))


def test_repository_rejects_cross_scope_and_missing_version(session: Session) -> None:
    repository = _repository(session)
    with pytest.raises(ValueError, match="scope does not match"):
        repository.create_version(
            _version_payload(
                project_id="project-ac",
                category_code="AC",
                product_category="AC",
                storage_batch_id="batch-ac",
                release_scope_key="scope-ac",
                serving_scope=_scope("AC"),
            )
        )
    with pytest.raises(CompetitorProfileVersionNotFoundError):
        repository.get_profile(
            competitor_profile_version_id="missing",
            target_sku_code="TV-TARGET",
        )


def test_pair_pagination_clamps_to_repository_limit(session: Session) -> None:
    repository = _repository(session)
    assert repository.pagination(501, -1, max_limit=500) == (500, 0)
