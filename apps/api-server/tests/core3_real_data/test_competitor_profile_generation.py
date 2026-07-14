from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_generation import (
    CompetitorProfileGenerationService,
)
from app.services.core3_real_data.analyst.competitor_profile_generation_schemas import (
    CompetitorProfileGenerationRequest,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileInputRequest,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer import (
    CompetitorProfileMaterializer,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileImmutableError,
    CompetitorProfileRepository,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)
from tests.core3_real_data.test_competitor_profile_materializer import (
    _config,
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
            entities.CategoryProject.__table__.insert().values(
                project_id="project-tv",
                name="TV",
                category_code="TV",
            )
        )
        connection.execute(
            entities.Core3SourceBatch.__table__.insert().values(
                batch_id="batch-1",
                project_id="project-tv",
                category_code="TV",
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


class _FixtureInputProvider:
    def __init__(self, category) -> None:
        self.category = category
        self.category_load_count = 0
        self.target_load_count = 0

    def load_category_input_bundle(self, request):
        self.category_load_count += 1
        return self.category

    def load_target_input(self, category, target_sku_code):
        self.target_load_count += 1
        return _target_bundle(category, target_sku_code)


class _OneTargetFailsMaterializer(CompetitorProfileMaterializer):
    def __init__(self, failed_code: str) -> None:
        self.failed_code = failed_code

    def materialize(self, category_bundle, target_bundle, config):
        if target_bundle.target_sku_code == self.failed_code:
            raise RuntimeError("sensitive internal failure detail")
        return super().materialize(category_bundle, target_bundle, config)


class _SelectedTargetsFailMaterializer(CompetitorProfileMaterializer):
    def __init__(self, failed_codes: set[str]) -> None:
        self.failed_codes = failed_codes

    def materialize(self, category_bundle, target_bundle, config):
        if target_bundle.target_sku_code in self.failed_codes:
            raise RuntimeError("sensitive internal failure detail")
        return super().materialize(category_bundle, target_bundle, config)


def _repository(session: Session) -> CompetitorProfileRepository:
    return CompetitorProfileRepository(
        Core3RepositoryContext(
            db=session,
            project_id="project-tv",
            category_code=Core3CategoryCode.TV,
        )
    )


def _request(category, *, profile_version: str = "competitor-profile-generation-v1"):
    return CompetitorProfileGenerationRequest(
        input_request=CompetitorProfileInputRequest(
            project_id="project-tv",
            category_code="TV",
            product_category="TV",
            storage_batch_id="batch-1",
            source_batch_ids=["batch-1"],
            analysis_population="competitor_profile_full_published_scope",
            semantic_market_analysis_population="semantic-market",
            claim_value_analysis_population="claim-value",
            market_window="full_observed_window",
        ),
        profile_version=profile_version,
        config=_config("TV"),
        generated_by="test",
    )


def test_generate_draft_persists_and_readbacks_all_children(session: Session) -> None:
    category = _category_bundle(specs=[_default_spec("TV", 1), _default_spec("TV", 2)])
    service = CompetitorProfileGenerationService(
        repository=_repository(session),
        input_provider=_FixtureInputProvider(category),
    )

    first = service.generate_draft(_request(category), target_sku_code="tv000001")
    second = service.generate_draft(_request(category), target_sku_code="TV000001")

    assert first.status == "generated"
    assert second.status == "reused"
    assert first.persisted.profile.result_hash == second.persisted.profile.result_hash
    assert len(first.persisted.relations) == len(first.persisted.pairs) * 7
    version = first.persisted.version
    assert version.processing_status == "running"
    assert version.ready_count + version.partial_count + version.blocked_count == 1


def test_generation_loads_one_category_snapshot_not_one_per_candidate(
    session: Session,
) -> None:
    category = _category_bundle(
        specs=[_default_spec("TV", number) for number in range(1, 22)]
    )
    provider = _FixtureInputProvider(category)
    result = CompetitorProfileGenerationService(
        repository=_repository(session),
        input_provider=provider,
    ).generate_draft(_request(category), target_sku_code="TV000001")

    assert provider.category_load_count == 1
    assert provider.target_load_count == 1
    assert len(result.persisted.pairs) == 20
    assert len(result.persisted.relations) == 20 * 7


def test_batch_is_resumable_and_isolates_safe_per_sku_failures(session: Session) -> None:
    category = _category_bundle(specs=[_default_spec("TV", 1), _default_spec("TV", 2)])
    repository = _repository(session)
    service = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=_FixtureInputProvider(category),
        materializer=_OneTargetFailsMaterializer("TV000002"),
    )

    first = service.batch_generate(_request(category), page_size=1)

    assert first.generated_count == 1
    assert first.failed_count == 1
    assert first.version.processing_status == "completed_with_errors"
    failed = next(row for row in first.statuses if row.status == "failed")
    assert failed.error_code == "RuntimeError"
    assert "sensitive" not in str(failed.error_message)
    assert repository.get_profile(
        competitor_profile_version_id=first.version.competitor_profile_version_id,
        target_sku_code="TV000001",
    ) is not None
    assert repository.get_profile(
        competitor_profile_version_id=first.version.competitor_profile_version_id,
        target_sku_code="TV000002",
    ) is None

    resumed = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=_FixtureInputProvider(category),
    ).batch_generate(_request(category), page_size=1)
    assert resumed.skipped_count == 1
    assert resumed.generated_count == 1
    assert resumed.failed_count == 0
    assert resumed.version.processing_status == "completed"


def test_batch_verifies_hash_receipts_without_full_graph_readback(
    session: Session,
) -> None:
    category = _category_bundle(
        specs=[_default_spec("TV", 1), _default_spec("TV", 2)]
    )
    repository = _repository(session)

    def reject_full_readback(*args, **kwargs):
        raise AssertionError("batch generation must not build a full read bundle")

    repository.write_draft = reject_full_readback  # type: ignore[method-assign]
    result = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=_FixtureInputProvider(category),
    ).batch_generate(_request(category), page_size=1)

    assert result.generated_count == 2
    assert result.failed_count == 0
    assert result.version.processing_status == "completed"


def test_same_version_rejects_changed_materialization_inputs(session: Session) -> None:
    category = _category_bundle(specs=[_default_spec("TV", 1), _default_spec("TV", 2)])
    service = CompetitorProfileGenerationService(
        repository=_repository(session),
        input_provider=_FixtureInputProvider(category),
    )
    request = _request(category)
    service.ensure_version(request)

    changed = request.model_copy(
        update={"config": request.config.model_copy(update={"config_version": "changed"})}
    )
    with pytest.raises(CompetitorProfileImmutableError):
        service.ensure_version(changed)


def test_single_sku_recovery_preserves_other_failed_targets(session: Session) -> None:
    category = _category_bundle(
        specs=[_default_spec("TV", number) for number in range(1, 4)]
    )
    repository = _repository(session)
    first = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=_FixtureInputProvider(category),
        materializer=_SelectedTargetsFailMaterializer(
            {"TV000002", "TV000003"}
        ),
    ).batch_generate(_request(category), page_size=1)

    assert first.failed_count == 2
    assert first.version.failed_count == 2
    assert set(first.version.safe_error_summary["failures"]) == {
        "TV000002",
        "TV000003",
    }

    recovered = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=_FixtureInputProvider(category),
    ).generate_draft(_request(category), target_sku_code="TV000002")

    assert recovered.persisted.version.failed_count == 1
    assert set(recovered.persisted.version.safe_error_summary["failures"]) == {
        "TV000003"
    }
