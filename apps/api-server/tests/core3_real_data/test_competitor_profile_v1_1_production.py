from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.cli.catforge_analyst import build_parser
from app.services.core3_real_data.analyst.competitor_profile_config import (
    build_production_materialization_config,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_production import (
    CompetitorProfileV11ProductionService,
    CompetitorProfileV11ProductionWorkItemBuilder,
    production_performance_storage_budget,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11Repository,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _target_bundle,
)


PROFILE_TABLES = (
    entities.Core3CompetitorProfileVersion.__table__,
    entities.Core3CompetitorProfileSkuSnapshot.__table__,
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
            [{"project_id": "project-tv", "name": "TV", "category_code": "TV"}],
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


class _FixtureProvider:
    def __init__(self):
        self.category = _category_bundle()
        self.target = _target_bundle(self.category, "TV000001")

    def build_production_input_request(self):
        return object()

    def load_category_input_bundle(self, _request):
        return self.category

    def load_target_input(self, category, target_sku_code):
        assert category == self.category
        assert target_sku_code == "TV000001"
        return self.target


def _repository(session: Session) -> CompetitorProfileV11Repository:
    return CompetitorProfileV11Repository(
        Core3RepositoryContext(
            db=session,
            project_id="project-tv",
            category_code=Core3CategoryCode.TV,
        )
    )


def test_production_work_item_preserves_the_full_candidate_universe() -> None:
    provider = _FixtureProvider()
    builder = CompetitorProfileV11ProductionWorkItemBuilder()
    config = build_production_materialization_config(provider.category)
    prepared = builder.prepare(provider.category, provider.target, config)
    snapshot_stage = builder.build_snapshot_stage(
        prepared,
        competitor_profile_version_id="competitor-profile-v11-production-test",
    )
    assert not hasattr(snapshot_stage, "category_bundle")
    expected = [row.candidate.sku_code for row in prepared.pair_features.pairs]
    item = builder.build_work_item_from_snapshot_stage(
        snapshot_stage,
        competitor_profile_version_id="competitor-profile-v11-production-test",
    )

    assert [row.candidate_sku_code for row in item.pair_assemblies] == expected
    assert [row.candidate_sku_code for row in item.gate_evaluations] == expected
    assert [
        row.candidate_sku_code for row in item.selection_result.pair_decisions
    ] == expected
    assert len(item.candidate_snapshots) == len(expected)
    assert item.selection_result.analysis_candidate_count == len(expected)
    assert item.selection_result.selected_count == 3


def test_production_service_persists_once_and_reuses_the_same_draft(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(session)
    monkeypatch.setattr(
        repository,
        "_read_projection",
        lambda **_kwargs: pytest.fail(
            "production generation must not materialize a second full readback"
        ),
    )
    service = CompetitorProfileV11ProductionService(
        repository=repository,
        input_provider=_FixtureProvider(),
    )

    first = service.generate_single_draft(
        target_sku_code="TV000001",
        profile_version="competitor-profile-v11-production-test",
        generated_by="pytest",
    )
    second = service.generate_single_draft(
        target_sku_code="TV000001",
        profile_version="competitor-profile-v11-production-test",
        generated_by="pytest",
    )

    assert first.status == "generated"
    assert second.status == "reused"
    assert first.materialized.dto == second.materialized.dto
    assert first.version.competitor_profile_version_id == (
        second.version.competitor_profile_version_id
    )
    assert first.version.release_status == "draft"
    assert first.version.is_current is False
    assert second.version.ready_count + second.version.partial_count == 1
    assert second.version.pair_count == first.candidate_count
    assert second.version.relation_count == first.candidate_count * 7
    assert second.version.selection_count == len(first.selected_sku_codes)
    assert (
        session.scalar(
            select(func.count()).select_from(entities.Core3CompetitorProfileSkuSnapshot)
        )
        == first.candidate_count + 1
    )


def test_production_service_records_a_safe_failed_version_state(
    session: Session,
) -> None:
    class _FailingBuilder(CompetitorProfileV11ProductionWorkItemBuilder):
        def build_work_item_from_snapshot_stage(
            self,
            stage,
            *,
            competitor_profile_version_id,
        ):
            raise RuntimeError("fixture failure with internal detail")

    repository = _repository(session)
    service = CompetitorProfileV11ProductionService(
        repository=repository,
        input_provider=_FixtureProvider(),
        work_item_builder=_FailingBuilder(),
    )

    with pytest.raises(RuntimeError, match="fixture failure"):
        service.generate_single_draft(
            target_sku_code="TV000001",
            profile_version="competitor-profile-v11-production-failed-test",
            generated_by="pytest",
        )

    version = session.scalars(
        select(entities.Core3CompetitorProfileVersion).where(
            entities.Core3CompetitorProfileVersion.profile_version
            == "competitor-profile-v11-production-failed-test"
        )
    ).one()
    assert version.release_status == "draft"
    assert version.processing_status == "failed"
    assert version.failed_count == 1
    assert version.safe_error_summary_json == {"failures": {"TV000001": "RuntimeError"}}
    assert (
        session.scalar(
            select(func.count()).select_from(entities.Core3SkuCompetitorProfile)
        )
        == 0
    )


def test_production_budget_keeps_no_truncation_contract() -> None:
    budget = production_performance_storage_budget()
    assert budget.maximum_compact_readback_ms == 2000
    assert budget.candidate_truncation_allowed is False
    assert budget.dimension_dropping_allowed is False


def test_cli_exposes_explicit_single_sku_v11_write_boundary() -> None:
    args = build_parser().parse_args(
        [
            "competitor-profile-v1-1-generate",
            "--project-id",
            "project-tv",
            "--category-code",
            "TV",
            "--sku-code",
            "TV000001",
            "--profile-version",
            "competitor-profile-v11-production-test",
            "--generated-by",
            "pytest",
            "--enable-profile-write",
        ]
    )
    assert args.command == "competitor-profile-v1-1-generate"
    assert args.sku_code == "TV000001"
    assert args.enable_profile_write is True
