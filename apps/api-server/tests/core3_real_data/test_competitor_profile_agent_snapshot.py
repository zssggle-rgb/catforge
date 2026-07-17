from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst import (
    competitor_profile_agent_snapshot_generation as generation_module,
    sop_orchestrators as sop_module,
)
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.analyst_service import CatForgeAnalystService
from app.services.core3_real_data.analyst.competitor_answer import (
    render_competitor_answer_from_saved_agent_analysis,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_generation import (
    CompetitorProfileAgentSnapshotGenerationService,
    _build_agent_snapshot,
    _identity,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_METHOD_VERSION,
    AGENT_SNAPSHOT_RULE_VERSION,
    CompetitorProfileAgentSnapshotAdapter,
)
from app.services.core3_real_data.analyst.competitor_profile_lifecycle import (
    CompetitorProfileLifecycleService,
    CompetitorProfileReviewNotAllowedError,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileVersionDraftCreate,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_reader import (
    CompetitorProfileV11ReadRequest,
    CompetitorProfileV11Reader,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    ReleaseQualityStatus,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorProfileAdapter,
    SellpointValueCompetitorReadRequest,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext


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
            [{"project_id": "project-1", "name": "TV", "category_code": "TV"}],
        )
        connection.execute(
            entities.Core3SourceBatch.__table__.insert().values(
                batch_id="batch-1",
                project_id="project-1",
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


def _repository(session: Session) -> CompetitorProfileAgentSnapshotRepository:
    return CompetitorProfileAgentSnapshotRepository(
        Core3RepositoryContext(
            db=session,
            project_id="project-1",
            category_code=Core3CategoryCode.TV,
        )
    )


def _version(repository: CompetitorProfileAgentSnapshotRepository):
    scope = {
        "project_id": "project-1",
        "category_code": "TV",
        "product_category": "TV",
        "storage_batch_id": "batch-1",
        "release_scope_key": "project-1:TV:agent",
        "analysis_population": "existing_competitor_agent_analysis",
        "market_window": "full_observed_window",
        "taxonomy_version": "agent-source-v1",
        "source_batch_ids": ["batch-1"],
        "source_authorities": {
            "M12D": {
                "module_code": "M12D",
                "project_id": "project-1",
                "category_code": "TV",
                "product_category": "TV",
                "profile_version": "m12d-v1",
                "schema_version": "schema-v1",
                "rule_version": "rule-v1",
                "taxonomy_version": "taxonomy-v1",
                "release_status": "published",
                "is_current": True,
                "source_batch_ids": ["batch-1"],
                "result_hash": "hash:m12d",
            }
        },
        "sku_prefixes": ["TV"],
        "authoritative_sku_count": 3,
        "authoritative_sku_manifest_hash": "hash:manifest",
    }
    return repository.create_version(
        CompetitorProfileVersionDraftCreate(
            project_id="project-1",
            category_code="TV",
            product_category="TV",
            storage_batch_id="batch-1",
            release_scope_key="project-1:TV:agent",
            profile_version="agent-profile-r1",
            schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
            rule_version=AGENT_SNAPSHOT_RULE_VERSION,
            method_version=AGENT_SNAPSHOT_METHOD_VERSION,
            method_versions_json={"analysis_source": "legacy-live-v1"},
            serving_scope=scope,
            sku_count=3,
            input_fingerprint="fingerprint:version",
            candidate_universe_fingerprint="fingerprint:universe",
            result_hash="hash:version",
            processing_status="running",
        )
    )


def _candidate(sku_code: str, rank: int, score: float, role: str) -> dict:
    return {
        "rank": rank,
        "candidate": {
            "sku_code": sku_code,
            "brand_name": "品牌",
            "model_name": sku_code,
            "screen_size_inch": 65,
            "size_tier": "65",
            "price_band_in_size_tier": "high",
            "price_wavg": 5000 + rank,
            "sales_volume_total": 1000 + rank,
            "avg_weekly_sales_volume": 50 + rank,
            "same_pool_sku_count": 20,
            "price_gap_to_target": rank,
            "price_gap_pct_to_target": rank / 100,
            "evidence_id_count": 2,
        },
        "competitor_score": score,
        "basis": {"same_size_price_pool": True},
        "semantic_overlap": {"value_battlefield": {"score": score}},
        "param_claim_overlap": {"claim_overlap": {}},
        "sales_overlap": {"comparison": {}},
        "candidate_fact_brief": {
            "sections": {
                "market": {
                    "market_metrics": {
                        "price_wavg": 5000 + rank,
                        "sales_volume_total": 1000 + rank,
                        "avg_weekly_sales_volume": 50 + rank,
                    }
                }
            }
        },
        "candidate_claim_value": {},
        "candidate_claim_contribution": {},
        "target_purchase_reason_profile": {"profile_confidence": 0.8},
        "candidate_purchase_reason_profile": {"profile_confidence": 0.7},
        "anchor_substitutability": {},
        "value_anchor": {
            "shared_anchors": ["画质"],
            "target_stronger_anchors": [],
            "candidate_stronger_anchors": [],
            "proposition_only_anchors": [],
            "anchor_substitutability_score": 15,
            "anchor_substitutability_level": "strong",
        },
        "replacement_pressure": {
            "type": "direct",
            "type_cn": "直接替代",
            "score": score,
            "reason_cn": "形成购买替代压力",
        },
        "purchase_pressure_comparison": {"comparison_allowed": True},
        "m12d_consumption": {"requires_review": False},
        "business_score": score,
        "role": role,
        "role_cn": role,
        "purchase_pool": {"level": "P0", "score": 1.0},
        "weighted_overlap": {
            "battlefield": score,
            "user_task": score,
            "target_group": score,
        },
        "matched_dimensions": {},
        "market_validation": {
            "level": "strong",
            "level_cn": "强",
            "overlap_week_count": 20,
            "avg_weekly_sales_volume": 50 + rank,
            "summary_cn": "具备市场分流能力",
        },
        "selection_gate": {"top3_eligible": True},
        "ranking_trace": {"selection_effect_cn": "进入重点竞品"},
        "ranking_gate_reasons": ["published_ready"],
        "shared_business_context": ["客厅换新"],
        "top3_eligible": True,
        "exclusion_reason_cn": None,
    }


def _source_result() -> dict:
    first = _candidate("TV00000002", 1, 0.91, "primary_direct")
    second = _candidate("TV00000003", 2, 0.82, "downtrade_diversion")
    return {
        "status": "ok",
        "target": {
            "sku_code": "TV00000001",
            "brand_name": "海信",
            "model_name": "65E7Q",
            "product_category": "TV",
            "size_tier": "65",
            "price_band_in_size_tier": "high",
            "screen_size_inch": 65,
            "weighted_price": 5949,
            "avg_weekly_sales_volume": 251,
        },
        "result": {
            "competitor_set": {
                "ranking_policy": ["same_size_price_pool"],
                "target_fact_brief": {
                    "sections": {
                        "market": {
                            "market_metrics": {
                                "price_wavg": 5949,
                                "sales_volume_total": 6000,
                                "avg_weekly_sales_volume": 251,
                            }
                        }
                    }
                },
                "target_claim_value": {},
                "target_claim_contribution": {},
                "m12d_consumption": {},
                "candidates": [first, second],
            },
            "competitor_answer": {
                "all_candidates": [second, first],
                "top_competitors": [first, second],
            },
        },
        "evidence": [
            {
                "source_module": "M07",
                "sku_code": "TV00000001",
                "row_count": 1,
            }
        ],
        "limitations": [],
    }


def _source_result_for_target(sku_code: str) -> dict:
    source = deepcopy(_source_result())
    source["target"]["sku_code"] = sku_code
    source["target"]["model_name"] = sku_code
    for receipt in source["evidence"]:
        receipt["sku_code"] = sku_code
    return source


def test_zero_candidate_snapshot_roundtrip_and_business_answer(
    session: Session,
) -> None:
    repository = _repository(session)
    version = _version(repository)
    source = _source_result_for_target("TV00000001")
    source["result"]["competitor_set"]["candidates"] = []
    source["result"]["competitor_answer"]["all_candidates"] = []
    source["result"]["competitor_answer"]["top_competitors"] = []
    profile, snapshots = _build_agent_snapshot(
        source_result=source,
        version=version,
    )
    assert profile.candidates == []
    assert profile.candidate_pool_order == []
    assert profile.analysis_order == []
    assert profile.priority_order == []
    assert len(snapshots) == 1
    assert repository.write_agent_snapshot_draft(
        profile=profile,
        sku_snapshots=snapshots,
    )
    compact = repository.read_agent_snapshot(
        target_sku_code="TV00000001",
        read_mode="compact",
        access_mode="preview",
        competitor_profile_version_id=version.competitor_profile_version_id,
        release_scope_key=version.release_scope_key,
    )
    assert compact.status == "available"
    assert compact.compact is not None
    assert compact.compact.candidate_count == 0
    assert compact.compact.pair_index == []
    full = repository.read_agent_snapshot(
        target_sku_code="TV00000001",
        read_mode="full",
        access_mode="preview",
        competitor_profile_version_id=version.competitor_profile_version_id,
        release_scope_key=version.release_scope_key,
    )
    assert full.status == "available"
    assert full.full is not None
    runtime = CompetitorProfileAgentSnapshotAdapter().adapt(
        full.full,
        full.sku_snapshots,
    )
    assert runtime.candidates == []
    answer = render_competitor_answer_from_saved_agent_analysis(
        target=runtime.target.model_dump(mode="json"),
        target_fact_brief=runtime.target_fact_brief,
        target_claim_value=runtime.target_claim_value,
        target_claim_contribution=runtime.target_claim_contribution,
        candidates=[],
        priority_order=[],
        with_report="none",
    )
    assert "当前没有足够证据形成稳定重点竞品" in answer["short_answer"]
    saved = session.execute(
        select(entities.Core3SkuCompetitorProfile).where(
            entities.Core3SkuCompetitorProfile.target_sku_code == "TV00000001"
        )
    ).scalar_one()
    assert saved.conclusion_state == "no_priority_competitor"
    assert saved.no_conclusion_reason_json["reason_code"] == "no_market_candidates"


def test_agent_sku_identity_canonicalizes_equal_decimal_scales() -> None:
    first = _identity(
        {
            "sku_code": "TV00000001",
            "screen_size_inch": "65.0",
            "weighted_price": "5949.00",
            "avg_weekly_sales_volume": "156.5",
            "sales_volume_total": "6260.000",
        },
        "TV",
        fact_brief={},
    )
    second = _identity(
        {
            "sku_code": "TV00000001",
            "screen_size_inch": "65.0000",
            "weighted_price": "5949",
            "avg_weekly_sales_volume": "156.5000",
            "sales_volume_total": "6260",
        },
        "TV",
        fact_brief={},
    )
    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.avg_weekly_sales_volume == second.avg_weekly_sales_volume
    assert str(first.avg_weekly_sales_volume) == "156.500000"
    rounded_float = _identity(
        {"sku_code": "TV00000002", "avg_weekly_sales_volume": 404.4583333333333},
        "TV",
        fact_brief={},
    )
    exact_decimal = _identity(
        {
            "sku_code": "TV00000002",
            "avg_weekly_sales_volume": "404.4583333333333333333333333",
        },
        "TV",
        fact_brief={},
    )
    assert rounded_float == exact_decimal
    assert str(rounded_float.avg_weekly_sales_volume) == "404.458333"


def test_batch_generation_resumes_failures_and_reuses_completed_profiles(
    session: Session,
    monkeypatch,
) -> None:
    repository = _repository(session)
    version = _version(repository)

    class InputProvider:
        @staticmethod
        def build_production_input_request():
            raise AssertionError("batch scope should be prepared once")

    service = CompetitorProfileAgentSnapshotGenerationService(
        repository=repository,
        input_provider=InputProvider(),
    )
    monkeypatch.setattr(
        service,
        "_prepare_scope",
        lambda: (version.serving_scope, object()),
    )
    targets = ["TV00000001", "TV00000004", "TV00000005"]
    monkeypatch.setattr(service, "_authoritative_target_codes", lambda _: targets)
    monkeypatch.setattr(service, "_ensure_version", lambda **_: version)
    attempts: dict[str, int] = {}

    def run_existing(*, target_sku_code: str, **_):
        attempts[target_sku_code] = attempts.get(target_sku_code, 0) + 1
        if target_sku_code == "TV00000004" and attempts[target_sku_code] == 1:
            raise RuntimeError("fixture transient failure")
        return _source_result_for_target(target_sku_code)

    monkeypatch.setattr(service, "_run_existing_agent", run_existing)
    progress: list[dict] = []
    first = service.generate_batch_draft(
        profile_version=version.profile_version,
        generated_by="pytest",
        checkpoint_every=1,
        progress_callback=progress.append,
    )
    assert first.generated_count == 2
    assert first.reused_count == 0
    assert first.failure_codes == (("TV00000004", "RuntimeError"),)
    assert first.version.processing_status == "failed"
    assert progress[-1]["processed_count"] == 3
    assert progress[-1]["failure_count"] == 1

    resumed = service.generate_batch_draft(
        profile_version=version.profile_version,
        generated_by="pytest",
        checkpoint_every=2,
    )
    assert resumed.generated_count == 1
    assert resumed.reused_count == 2
    assert resumed.failure_codes == ()
    assert resumed.version.processing_status == "success"
    assert attempts == {
        "TV00000001": 1,
        "TV00000004": 2,
        "TV00000005": 1,
    }
    profiles = list(
        session.execute(
            select(entities.Core3SkuCompetitorProfile.target_sku_code)
            .where(
                entities.Core3SkuCompetitorProfile.competitor_profile_version_id
                == version.competitor_profile_version_id
            )
            .order_by(entities.Core3SkuCompetitorProfile.target_sku_code)
        ).scalars()
    )
    assert profiles == targets
    assert (
        session.scalar(
            select(entities.Core3CompetitorProfileVersion.failed_count).where(
                entities.Core3CompetitorProfileVersion.competitor_profile_version_id
                == version.competitor_profile_version_id
            )
        )
        == 0
    )


def _completed_agent_snapshot_version(
    session: Session,
) -> tuple[CompetitorProfileAgentSnapshotRepository, str]:
    repository = _repository(session)
    version = _version(repository)
    for index, target in enumerate(("TV00000001", "TV00000004", "TV00000005")):
        source = _source_result_for_target(target)
        if index == 0:
            source["limitations"] = ["fixture evidence limitation"]
        profile, snapshots = _build_agent_snapshot(
            source_result=source,
            version=version,
        )
        repository.write_agent_snapshot_draft(
            profile=profile,
            sku_snapshots=snapshots,
        )
    repository.update_draft_generation_state(
        version.competitor_profile_version_id,
        ready_count=2,
        partial_count=1,
        blocked_count=0,
        failed_count=0,
        pair_count=6,
        relation_count=0,
        selection_count=6,
        processing_status="success",
    )
    return repository, version.competitor_profile_version_id


def test_agent_snapshot_limited_release_uses_method_specific_integrity_gate(
    session: Session,
) -> None:
    repository, version_id = _completed_agent_snapshot_version(session)
    lifecycle = CompetitorProfileLifecycleService(repository.context)

    reviewed = lifecycle.review_version(
        competitor_profile_version_id=version_id,
        reviewed_by="competitor-profile-reviewer",
        release_quality_status=ReleaseQualityStatus.LIMITED,
    )
    assert reviewed.release_status == "review"
    assert reviewed.release_quality_status == "limited"

    published = lifecycle.publish_version(
        competitor_profile_version_id=version_id,
        published_by="competitor-profile-publisher",
        allow_limited=True,
        release_note_cn="Agent snapshot V2 limited release fixture.",
    )
    assert published.release_status == "published"
    assert published.is_current is False

    current = lifecycle.set_current_version(
        competitor_profile_version_id=version_id,
        current_by="competitor-profile-approver",
        expected_current_version_id=None,
    )
    assert current.is_current is True
    formal = repository.read_agent_snapshot(
        target_sku_code="TV00000001",
        read_mode="compact",
        access_mode="formal",
    )
    assert formal.status == "available"
    assert formal.preview is False
    spv_source = SellpointValueCompetitorProfileAdapter(repository).read(
        SellpointValueCompetitorReadRequest(
            project_id="project-1",
            category_code="TV",
            target_sku_code="TV00000001",
            access_mode="formal",
        )
    )
    assert spv_source.source is not None
    assert spv_source.source.release_status == "published"
    assert spv_source.source.is_current
    assert spv_source.source.source_version_result_hash == current.result_hash


def test_agent_snapshot_release_gate_detects_selection_hash_tampering(
    session: Session,
) -> None:
    repository, version_id = _completed_agent_snapshot_version(session)
    selection = session.execute(
        select(entities.Core3SkuCompetitorProfileSelection)
        .where(
            entities.Core3SkuCompetitorProfileSelection.competitor_profile_version_id
            == version_id
        )
        .limit(1)
    ).scalar_one()
    selection.result_hash = "tampered-selection-hash"
    session.flush()
    lifecycle = CompetitorProfileLifecycleService(repository.context)

    with pytest.raises(
        CompetitorProfileReviewNotAllowedError,
        match="agent_selection_index_mismatch",
    ):
        lifecycle.review_version(
            competitor_profile_version_id=version_id,
            reviewed_by="competitor-profile-reviewer",
            release_quality_status=ReleaseQualityStatus.LIMITED,
        )


def test_agent_snapshot_roundtrip_and_compact_read(session: Session) -> None:
    repository = _repository(session)
    version = _version(repository)
    profile, snapshots = _build_agent_snapshot(
        source_result=_source_result(),
        version=version,
    )
    assert all(not row.evidence and not row.limitations for row in snapshots)

    assert repository.write_agent_snapshot_draft(
        profile=profile,
        sku_snapshots=snapshots,
    )
    assert not repository.write_agent_snapshot_draft(
        profile=profile,
        sku_snapshots=snapshots,
    )

    reader = CompetitorProfileV11Reader(repository)
    full = reader.read(
        CompetitorProfileV11ReadRequest(
            project_id="project-1",
            category_code="TV",
            release_scope_key=version.release_scope_key,
            target_sku_code="TV00000001",
            access_mode="preview",
            read_mode="full",
            competitor_profile_version_id=version.competitor_profile_version_id,
            allow_draft_preview=True,
        )
    )
    assert full.status == "available"
    assert full.full == profile
    assert len(full.sku_snapshots) == 3
    assert full.full.target_fact_brief == {"storage_ref": full.full.target_snapshot_ref}
    runtime = CompetitorProfileAgentSnapshotAdapter().adapt(
        full.full,
        full.sku_snapshots,
    )
    assert (
        runtime.target_fact_brief
        == _source_result()["result"]["competitor_set"]["target_fact_brief"]
    )
    assert [row.candidate.sku_code for row in runtime.candidates] == [
        "TV00000003",
        "TV00000002",
    ]
    assert runtime.candidates[0].candidate_fact_brief["sections"]["market"]
    compact = reader.read(
        CompetitorProfileV11ReadRequest(
            project_id="project-1",
            category_code="TV",
            release_scope_key=version.release_scope_key,
            target_sku_code="TV00000001",
            access_mode="preview",
            read_mode="compact",
            competitor_profile_version_id=version.competitor_profile_version_id,
            allow_draft_preview=True,
        )
    )
    assert compact.status == "available"
    assert compact.compact is not None
    assert compact.compact.candidate_count == 2
    assert compact.compact.priority_order == ["TV00000002", "TV00000003"]
    assert [row.source_rank for row in compact.compact.pair_index] == [1, 2]

    spv_source = SellpointValueCompetitorProfileAdapter(repository).read(
        SellpointValueCompetitorReadRequest(
            project_id="project-1",
            category_code="TV",
            target_sku_code="TV00000001",
            access_mode="preview",
            release_scope_key=version.release_scope_key,
            competitor_profile_version_id=version.competitor_profile_version_id,
        )
    )
    assert spv_source.status == "available"
    assert spv_source.source is not None
    assert spv_source.source.source_version_result_hash == version.result_hash
    assert spv_source.source.source_result_hash == profile.result_hash
    assert [row.candidate_sku_code for row in spv_source.source.candidates] == [
        "TV00000002",
        "TV00000003",
    ]
    assert spv_source.source.priority_order == ["TV00000002", "TV00000003"]


def test_generation_reuses_saved_draft_without_running_live_analysis(
    session: Session,
    monkeypatch,
) -> None:
    repository = _repository(session)
    version = _version(repository)
    profile, snapshots = _build_agent_snapshot(
        source_result=_source_result(),
        version=version,
    )
    assert repository.write_agent_snapshot_draft(
        profile=profile,
        sku_snapshots=snapshots,
    )

    class InputProvider:
        @staticmethod
        def build_production_input_request():
            return object()

    service = CompetitorProfileAgentSnapshotGenerationService(
        repository=repository,
        input_provider=InputProvider(),
    )
    monkeypatch.setattr(
        service,
        "_current_purchase_reason_authority",
        lambda: object(),
    )
    monkeypatch.setattr(
        generation_module,
        "_serving_scope",
        lambda *_: version.serving_scope,
    )
    monkeypatch.setattr(service, "_ensure_version", lambda **_: version)

    def fail_live_analysis(**_):
        raise AssertionError("saved draft unexpectedly reran live analysis")

    monkeypatch.setattr(service, "_run_existing_agent", fail_live_analysis)
    result = service.generate_single_draft(
        target_sku_code="tv00000001",
        profile_version=version.profile_version,
        generated_by="pytest",
    )
    assert result.status == "reused"
    assert result.profile == profile
    assert result.selected_sku_codes == ("TV00000002", "TV00000003")


def test_selected_source_review_state_is_preserved(session: Session) -> None:
    repository = _repository(session)
    version = _version(repository)
    source = _source_result()
    source["result"]["competitor_answer"]["top_competitors"][0]["m12d_consumption"][
        "requires_review"
    ] = True
    profile, snapshots = _build_agent_snapshot(
        source_result=source,
        version=version,
    )
    assert repository.write_agent_snapshot_draft(
        profile=profile,
        sku_snapshots=snapshots,
    )
    selection = session.execute(
        select(entities.Core3SkuCompetitorProfileSelection).where(
            entities.Core3SkuCompetitorProfileSelection.candidate_sku_code
            == "TV00000002"
        )
    ).scalar_one()
    assert selection.review_required
    assert selection.review_status == "review_required"


def test_saved_renderer_does_not_reanalyze_or_reorder(monkeypatch) -> None:
    source = _source_result()
    candidates = source["result"]["competitor_answer"]["all_candidates"]

    def fail(*_, **__):
        raise AssertionError("saved renderer attempted live analysis")

    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer._enrich_competitor",
        fail,
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer._select_top_competitors",
        fail,
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.render_competitor_report",
        lambda **_: "report",
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.build_pm_competitor_comparison_payload",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.render_pm_comparison_report",
        lambda **_: "pm report",
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.pm_business_output_issue",
        lambda _: None,
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.render_short_answer",
        lambda **_: "answer",
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.build_competitor_dashboard_payload",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "app.services.core3_real_data.analyst.competitor_answer.render_feishu_card_payload",
        lambda _: {},
    )
    answer = render_competitor_answer_from_saved_agent_analysis(
        target=source["target"],
        target_fact_brief=source["result"]["competitor_set"]["target_fact_brief"],
        target_claim_value={},
        target_claim_contribution={},
        candidates=candidates,
        priority_order=["TV00000002", "TV00000003"],
    )
    assert [row["candidate"]["sku_code"] for row in answer["all_candidates"]] == [
        "TV00000003",
        "TV00000002",
    ]
    assert [row["candidate"]["sku_code"] for row in answer["top_competitors"]] == [
        "TV00000002",
        "TV00000003",
    ]


def test_competitor_agent_preview_consumes_saved_profile_only(
    session: Session,
    monkeypatch,
) -> None:
    repository = _repository(session)
    version = _version(repository)
    profile, snapshots = _build_agent_snapshot(
        source_result=_source_result(),
        version=version,
    )
    assert repository.write_agent_snapshot_draft(
        profile=profile,
        sku_snapshots=snapshots,
    )
    service = CatForgeAnalystService(
        session,
        project_id="project-1",
        category_code="TV",
    )

    def fail_legacy(*_, **__):
        raise AssertionError("saved profile unexpectedly entered live analysis")

    monkeypatch.setattr(
        service.sop_orchestrators,
        "_competitor_set_legacy",
        fail_legacy,
    )
    captured: dict[str, object] = {}

    def render_saved(**kwargs):
        captured.update(kwargs)
        return {
            "short_answer": "saved answer",
            "all_candidates": kwargs["candidates"],
        }

    monkeypatch.setattr(
        sop_module,
        "render_competitor_answer_from_saved_agent_analysis",
        render_saved,
    )
    result = service.dispatch(
        "competitor-set",
        AnalystContext(
            project_id="project-1",
            category_code="TV",
            batch_id="batch-1",
            product_category="tv",
        ),
        sku_code="TV00000001",
        answer_style="xiaoao",
        with_report="none",
        profile_access_mode="preview",
        competitor_profile_version_id=version.competitor_profile_version_id,
        competitor_profile_release_scope_key=version.release_scope_key,
        allow_draft_preview=True,
    )
    assert result["status"] == "ok"
    assert result["result"]["competitor_set"]["source"] == "competitor_profile_v1_1"
    assert result["result"]["competitor_set"]["saved_priority_order"] == [
        "TV00000002",
        "TV00000003",
    ]
    assert [row["candidate"]["sku_code"] for row in captured["candidates"]] == [
        "TV00000003",
        "TV00000002",
    ]
    assert [step["step_code"] for step in result["sop_steps"]] == [
        "resolve-sku",
        "competitor-profile-read",
        "competitor-profile-adapter",
        "competitor-profile-render",
    ]
