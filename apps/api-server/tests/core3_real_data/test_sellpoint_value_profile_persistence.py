from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
    SellpointValueDraftBundle,
    SellpointValueReleaseQualityStatus,
    SellpointValueVersionDraftCreate,
    SkuSellpointValueCandidateDraft,
    SkuSellpointValueItemDraft,
    SkuSellpointValueProfileDraft,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueDraftWriteNotAllowedError,
    SellpointValueImmutableVersionError,
    SellpointValueProfileRepository,
    SellpointValuePublishNotAllowedError,
    SellpointValueVersionNotFoundError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0045_core3_sellpoint_value_profile.py"
)
PROFILE_TABLES = {
    "core3_sellpoint_value_profile_version",
    "core3_sku_sellpoint_value_profile",
    "core3_sku_sellpoint_value_candidate",
    "core3_sku_sellpoint_value_item",
}


class BoundOp:
    def __init__(self, bind: Any) -> None:
        self.bind = bind

    def get_bind(self) -> Any:
        return self.bind


def _migration():
    spec = importlib.util.spec_from_file_location(
        "core3_sellpoint_value_profile_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def _create_dependencies(connection: Any) -> None:
    entities.CategoryProject.__table__.create(bind=connection, checkfirst=True)
    entities.Core3SourceBatch.__table__.create(bind=connection, checkfirst=True)


def _create_profile_tables(connection: Any) -> None:
    for table in (
        entities.Core3SellpointValueProfileVersion.__table__,
        entities.Core3SkuSellpointValueProfile.__table__,
        entities.Core3SkuSellpointValueCandidate.__table__,
        entities.Core3SkuSellpointValueItem.__table__,
    ):
        table.create(bind=connection, checkfirst=True)


@pytest.fixture
def session() -> Session:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        _create_profile_tables(connection)
    db = Session(engine, autoflush=False, future=True)
    db.add_all(
        [
            entities.CategoryProject(
                project_id="project-tv",
                name="TV project",
                category_code="TV",
            ),
            entities.CategoryProject(
                project_id="project-ac",
                name="AC project",
                category_code="AC",
            ),
            _source_batch("batch-tv", "project-tv", "TV"),
            _source_batch("batch-ac", "project-ac", "AC"),
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _source_batch(batch_id: str, project_id: str, category_code: str):
    return entities.Core3SourceBatch(
        batch_id=batch_id,
        project_id=project_id,
        category_code=category_code,
        source_system="fixture",
        source_database="fixture",
        source_tables=[],
        ruleset_version="rules-v1",
        module_version="module-v1",
        hash_version="hash-v1",
        scan_started_at=datetime.now(timezone.utc),
        status="completed",
    )


def _repository(
    session: Session,
    *,
    project_id: str = "project-tv",
    category_code: Core3CategoryCode = Core3CategoryCode.TV,
) -> SellpointValueProfileRepository:
    return SellpointValueProfileRepository(
        Core3RepositoryContext(
            db=session,
            project_id=project_id,
            category_code=category_code,
        )
    )


def _mark_version_ready(
    repository: SellpointValueProfileRepository,
    version_id: str,
    *,
    limited: bool = False,
    sku_code: str = "TV001",
) -> None:
    repository.update_version_progress(
        sellpoint_value_profile_version_id=version_id,
        sku_count=1,
        ready_count=0 if limited else 1,
        review_required_count=1 if limited else 0,
        blocked_count=0,
        failed_count=0,
        quality_summary_json={
            "release_quality_status": "limited" if limited else "ready"
        },
        validation_summary_json={"sku_statuses": {sku_code: "generated"}},
        release_quality_status=(
            SellpointValueReleaseQualityStatus.LIMITED
            if limited
            else SellpointValueReleaseQualityStatus.READY
        ),
        processing_status="completed",
        review_required=limited,
        review_status="review_required" if limited else "auto_pass",
    )


def _version_payload(
    profile_version: str = "spv-v1",
    *,
    input_fingerprint: str | None = None,
    result_hash: str | None = None,
    category_code: str = "TV",
    project_id: str = "project-tv",
    batch_id: str = "batch-tv",
) -> SellpointValueVersionDraftCreate:
    return SellpointValueVersionDraftCreate(
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        product_category=category_code,
        profile_version=profile_version,
        method_versions_json={"candidate": "v1", "threshold": "v1"},
        source_batch_ids_json=[batch_id],
        source_scope_json={"modules": ["M03B", "M12", "M13"]},
        input_fingerprint=input_fingerprint or f"version-input-{profile_version}",
        candidate_universe_fingerprint=f"candidate-{profile_version}",
        result_hash=result_hash or f"version-result-{profile_version}",
    )


def _bundle(
    version_id: str,
    *,
    profile_version: str = "spv-v1",
    sku_code: str = "TV001",
    profile_result_hash: str | None = None,
    candidate_result_hash: str = "candidate-result-1",
    profile_confidence: Decimal = Decimal("0.8200"),
    review_required: bool = False,
    review_status: str = "auto_pass",
) -> SellpointValueDraftBundle:
    common = {
        "sellpoint_value_profile_version_id": version_id,
        "project_id": "project-tv",
        "category_code": "TV",
        "batch_id": "batch-tv",
        "product_category": "TV",
        "profile_version": profile_version,
        "schema_version": SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
        "rule_version": SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        "method_version": SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        "input_fingerprint": f"profile-input-{profile_version}-{sku_code}",
        "review_required": review_required,
        "review_status": review_status,
        "review_reason_json": (
            {"reasons": ["low_confidence"]} if review_required else {}
        ),
    }
    evidence_ref = SellpointValueEvidenceRef(
        module_code="M03B",
        record_type="core3_sku_param_profile",
        record_id="param-1",
        result_hash="param-hash-1",
        batch_id="batch-tv",
        evidence_ids=["evidence-1"],
    )
    profile = SkuSellpointValueProfileDraft(
        **common,
        result_hash=profile_result_hash or f"profile-result-{sku_code}",
        sku_code=sku_code,
        model_name="65E7Q",
        brand_name="海信",
        display_name_cn="海信 65E7Q",
        analysis_state="ready",
        freshness_status="current",
        profile_confidence=profile_confidence,
        target_market_summary_json={"price_wavg": 5000},
        source_lineage_json=[{"module_code": "M03B", "result_hash": "param-hash-1"}],
        candidate_universe_summary_json={"candidate_count": 2},
        threshold_summary_json={"minimum_known_count": 5},
        question_analyses_json=[{"question": "current_price_support"}],
        investment_decisions_json=[{"classification": "retain"}],
        pm_decisions_json={"retain": ["picture"]},
        qa_index_json=[{"topic": "price", "path": "price_role"}],
        evidence_refs_json=[evidence_ref],
    )
    candidate = SkuSellpointValueCandidateDraft(
        **common,
        result_hash=candidate_result_hash,
        target_sku_code=sku_code,
        candidate_sku_code="TV-COMPETITOR",
        candidate_brand_name="TCL",
        candidate_model_name="65Q9L PRO",
        pool_type="competitor",
        primary_relation_type="direct_fight",
        relation_types_json=["direct_fight"],
        eligibility_status="eligible",
        m12_summary_json={"recall_strength": "strong"},
        m13_summary_json={"component_total_score": 0.8},
        m14_summary_json={"selected": True, "rank": 1},
        eligible_questions_json=["current_price_support", "specific_competitor"],
        selected_questions_json=["current_price_support"],
        data_availability_json={"market": True, "parameters": True},
        market_summary_json={"price_wavg": 4800},
        confidence=Decimal("0.8000"),
        evidence_refs_json=[evidence_ref],
    )
    reference = SkuSellpointValueCandidateDraft(
        **common,
        result_hash="reference-result-1",
        target_sku_code=sku_code,
        candidate_sku_code="TV-REFERENCE",
        pool_type="reference",
        primary_relation_type="same_size_market",
        relation_types_json=["same_size_market"],
        eligibility_status="limited",
        data_availability_json={"market": True},
        market_summary_json={"price_wavg": 5200},
        confidence=Decimal("0.7000"),
        evidence_refs_json=[evidence_ref],
    )
    value_item = SkuSellpointValueItemDraft(
        **common,
        result_hash="value-result-1",
        sku_code=sku_code,
        battlefield_code="BF-PREMIUM-PICTURE",
        battlefield_name_cn="高端画质升级",
        purchase_reason_code="picture_quality",
        purchase_reason_name_cn="画质升级",
        value_bundle_code="picture_bundle",
        value_bundle_name_cn="强光与暗场画质",
        normalized_bundle_code="picture_bundle",
        perceived_outcome_cn="强光环境更清晰，暗场层次更完整",
        perceived_value_status="observed_positive",
        capability_codes_json=["local_dimming", "high_brightness"],
        investment_decisions_json=[{"classification": "retain"}],
        investment_classifications_json=["retain"],
        question_result_refs_json=[{"question": "current_price_support"}],
        question_codes_json=["current_price_support"],
        price_realization_json={"status": "positive"},
        volume_realization_json={"status": "not_weaker"},
        evidence_refs_json=[evidence_ref],
        evidence_boundary_cn="观察性市场比较，不等同随机实验。",
        confidence=Decimal("0.8300"),
    )
    return SellpointValueDraftBundle(
        profile=profile,
        candidates=[candidate, reference],
        value_items=[value_item],
    )


def test_models_and_migration_contract_are_registered() -> None:
    assert PROFILE_TABLES.issubset(Base.metadata.tables)
    version_table = entities.Core3SellpointValueProfileVersion.__table__
    unique = next(
        constraint
        for constraint in version_table.constraints
        if constraint.name == "uq_core3_spv_version_key"
    )
    unique_columns = {column.name for column in unique.columns}

    assert "is_current" not in unique_columns
    assert unique_columns == {
        "project_id",
        "category_code",
        "batch_id",
        "profile_version",
        "rule_version",
    }
    assert any(
        index.name == "uq_core3_spv_current_published" and index.unique
        for index in version_table.indexes
    )
    current_index = next(
        index
        for index in version_table.indexes
        if index.name == "uq_core3_spv_current_published"
    )
    assert current_index.dialect_options["postgresql"]["where"] is not None
    assert current_index.dialect_options["sqlite"]["where"] is not None
    for table_name in PROFILE_TABLES:
        table = Base.metadata.tables[table_name]
        for field in (
            "project_id",
            "category_code",
            "batch_id",
            "schema_version",
            "rule_version",
            "method_version",
            "input_fingerprint",
            "result_hash",
            "review_status",
        ):
            assert field in table.c
        for constraint in table.constraints:
            if constraint.name:
                assert len(constraint.name) <= 63
        for index in table.indexes:
            assert index.name is not None and len(index.name) <= 63
    expected_gin_indexes = {
        "ix_core3_spv_version_source_gin",
        "ix_core3_spv_version_quality_gin",
        "ix_core3_spv_profile_questions_gin",
        "ix_core3_spv_profile_investment_gin",
        "ix_core3_spv_profile_evidence_gin",
        "ix_core3_spv_candidate_questions_gin",
        "ix_core3_spv_candidate_evidence_gin",
        "ix_core3_spv_item_questions_gin",
        "ix_core3_spv_item_investment_gin",
        "ix_core3_spv_item_evidence_gin",
    }
    actual_gin_indexes = {
        index.name
        for table_name in PROFILE_TABLES
        for index in Base.metadata.tables[table_name].indexes
        if index.dialect_options["postgresql"]["using"] == "gin"
    }
    assert actual_gin_indexes == expected_gin_indexes


def test_migration_upgrade_and_downgrade_on_sqlite() -> None:
    migration = _migration()
    engine = _engine()
    original_op = migration.op

    assert migration.revision == "0045_core3_sellpoint_value_profile"
    assert migration.down_revision == "0044_core3_m12d_reason_pressure"
    try:
        with engine.begin() as connection:
            _create_dependencies(connection)
            migration.op = BoundOp(connection)
            try:
                migration.upgrade()
                assert PROFILE_TABLES.issubset(inspect(connection).get_table_names())
                migration.downgrade()
                assert not PROFILE_TABLES.intersection(
                    inspect(connection).get_table_names()
                )
            finally:
                migration.op = original_op
    finally:
        engine.dispose()


def test_schema_rejects_low_confidence_autopass_and_factory_only_payload() -> None:
    with pytest.raises(ValidationError, match="low-confidence"):
        SkuSellpointValueProfileDraft.model_validate(
            {
                **_bundle("version-id").profile.model_dump(mode="python"),
                "profile_confidence": Decimal("0.4000"),
                "review_required": False,
                "review_status": "auto_pass",
            }
        )
    with pytest.raises(ValidationError, match="factory-only"):
        SellpointValueVersionDraftCreate.model_validate(
            {
                **_version_payload().model_dump(mode="python"),
                "source_scope_json": {"prompt_template": "do not persist"},
            }
        )

    bundle = _bundle("version-id")
    with pytest.raises(ValidationError, match="low-confidence"):
        SkuSellpointValueCandidateDraft.model_validate(
            {
                **bundle.candidates[0].model_dump(mode="python"),
                "confidence": Decimal("0.4000"),
            }
        )
    with pytest.raises(ValidationError, match="low-confidence"):
        SkuSellpointValueItemDraft.model_validate(
            {
                **bundle.value_items[0].model_dump(mode="python"),
                "confidence": Decimal("0.4000"),
            }
        )


def test_create_write_read_and_idempotent_reuse(session: Session) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    bundle = _bundle(version.sellpoint_value_profile_version_id)

    first = repository.write_draft(bundle)
    second = repository.write_draft(bundle)
    version_readback = repository.get_version(
        batch_id="batch-tv",
        profile_version="spv-v1",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    )
    readback = repository.get_profile(
        batch_id="batch-tv",
        profile_version="spv-v1",
        sku_code="TV001",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert version_readback is not None
    assert version_readback.result_hash == version.result_hash
    assert repository.list_versions(
        batch_id="batch-tv",
        release_status="draft",
        limit=1,
    )[0].profile_version == "spv-v1"
    assert readback is not None
    assert readback.model_dump(mode="json") == first.model_dump(mode="json")
    assert len(readback.candidates) == 2
    assert len(readback.value_items) == 1
    assert readback.profile.evidence_refs_json[0].record_id == "param-1"
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 1


def test_saved_v5_generation_source_projects_only_consumed_facts(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    repository.write_draft(_bundle(version.sellpoint_value_profile_version_id))
    item = session.execute(
        select(entities.Core3SkuSellpointValueItem)
    ).scalar_one()
    item.investment_decisions_json = [
        {
            "capability_code": "local_dimming",
            "capability_name_cn": "分区控光",
            "classification": "retain",
            "target_fact_status": "known_present",
            "target_value": "1920",
            "relative_experience_status": "better",
            "evidence_refs": [{"payload": "x" * 10000}],
            "prevalence_summary": {"unused": True},
        }
    ]
    session.flush()

    source = repository.get_saved_v5_generation_source(
        batch_id="batch-tv",
        profile_version="spv-v1",
        sku_code="TV001",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    )

    assert source is not None
    assert source.version.result_hash == version.result_hash
    assert source.profile.sku_code == "TV001"
    assert [row.candidate_sku_code for row in source.candidates] == [
        "TV-REFERENCE"
    ]
    assert source.value_items[0].investment_decisions_json == [
        {
            "capability_code": "local_dimming",
            "capability_name_cn": "分区控光",
            "classification": "retain",
            "target_fact_status": "known_present",
            "target_value": "1920",
            "relative_experience_status": "better",
        }
    ]
    assert "evidence_refs" not in source.value_items[0].investment_decisions_json[0]


def test_immutable_version_profile_and_children_cannot_be_overwritten(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    bundle = _bundle(version.sellpoint_value_profile_version_id)
    repository.write_draft(bundle)

    with pytest.raises(SellpointValueImmutableVersionError):
        repository.create_version(
            _version_payload(input_fingerprint="different-version-input")
        )
    with pytest.raises(SellpointValueImmutableVersionError):
        repository.write_draft(
            _bundle(
                version.sellpoint_value_profile_version_id,
                profile_result_hash="different-profile-result",
            )
        )
    with pytest.raises(SellpointValueImmutableVersionError):
        repository.write_draft(
            _bundle(
                version.sellpoint_value_profile_version_id,
                candidate_result_hash="different-candidate-result",
            )
        )


def test_concurrent_same_version_and_profile_insert_reuse_existing_rows(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(session)
    payload = _version_payload()
    version = repository.create_version(payload)
    bundle = _bundle(version.sellpoint_value_profile_version_id)
    existing = repository.write_draft(bundle)
    original_find_version = repository._find_version
    original_find_profile = repository._find_profile
    version_calls = 0
    profile_calls = 0

    def stale_version_precheck(**kwargs):
        nonlocal version_calls
        version_calls += 1
        if version_calls == 1:
            return None
        return original_find_version(**kwargs)

    def stale_profile_precheck(**kwargs):
        nonlocal profile_calls
        profile_calls += 1
        if profile_calls == 1:
            return None
        return original_find_profile(**kwargs)

    monkeypatch.setattr(repository, "_find_version", stale_version_precheck)
    reused_version = repository.create_version(payload)
    monkeypatch.setattr(repository, "_find_profile", stale_profile_precheck)
    reused_profile = repository.write_draft(bundle)

    assert reused_version.sellpoint_value_profile_version_id == (
        version.sellpoint_value_profile_version_id
    )
    assert reused_profile.model_dump(mode="json") == existing.model_dump(mode="json")
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SellpointValueProfileVersion)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 1


def test_candidate_and_value_item_filters_paginate_after_filtering(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    written = repository.write_draft(
        _bundle(version.sellpoint_value_profile_version_id)
    )
    profile_id = written.profile.sku_sellpoint_value_profile_id

    assert repository.list_profiles(
        sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
        analysis_state="ready",
        limit=1,
    )[0].sku_code == "TV001"
    progress = repository.list_profile_progress(
        sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
        limit=1,
    )
    assert [row.model_dump() for row in progress] == [
            {
                "sku_code": "TV001",
                "analysis_state": "ready",
                "conclusion_status": None,
                "review_required": False,
            }
        ]
    assert [
        row.candidate_sku_code
        for row in repository.list_candidates(
            sku_sellpoint_value_profile_id=profile_id,
            question_code="current_price_support",
            selected_only=True,
        )
    ] == ["TV-COMPETITOR"]
    assert repository.list_candidates(
        sku_sellpoint_value_profile_id=profile_id,
        eligibility_status="eligible",
        limit=1,
    )[0].candidate_sku_code == "TV-COMPETITOR"
    assert repository.list_value_items(
        sku_sellpoint_value_profile_id=profile_id,
        question_code="current_price_support",
        investment_classification="retain",
        limit=1,
    )[0].normalized_bundle_code == "picture_bundle"
    assert repository.list_value_items(
        sku_sellpoint_value_profile_id=profile_id,
        investment_classification="do_not_follow",
    ) == []


def test_project_and_category_isolation_blocks_cross_scope_reads(
    session: Session,
) -> None:
    tv_repository = _repository(session)
    version = tv_repository.create_version(_version_payload())
    tv_repository.write_draft(_bundle(version.sellpoint_value_profile_version_id))
    ac_repository = _repository(
        session,
        project_id="project-ac",
        category_code=Core3CategoryCode.AC,
    )

    assert ac_repository.get_profile(
        batch_id="batch-tv",
        profile_version="spv-v1",
        sku_code="TV001",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    ) is None
    with pytest.raises(SellpointValueVersionNotFoundError):
        ac_repository.list_profiles(
            sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id
        )


def test_review_publish_switches_only_explicit_reviewed_version(
    session: Session,
) -> None:
    repository = _repository(session)
    v1 = repository.create_version(_version_payload("spv-v1"))
    p1 = repository.write_draft(
        _bundle(v1.sellpoint_value_profile_version_id, profile_version="spv-v1")
    )
    _mark_version_ready(repository, v1.sellpoint_value_profile_version_id)
    repository.review_version(
        sellpoint_value_profile_version_id=v1.sellpoint_value_profile_version_id,
        reviewed_by="reviewer-1",
        release_quality_status=SellpointValueReleaseQualityStatus.READY,
    )
    published_v1 = repository.publish_version(
        sellpoint_value_profile_version_id=v1.sellpoint_value_profile_version_id,
        published_by="approver-1",
    )

    assert published_v1.release_status == "published"
    assert published_v1.is_current is True
    assert repository.get_profile(
        batch_id="batch-tv",
        profile_version="spv-v1",
        sku_code="TV001",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    ).profile.is_current is True
    with pytest.raises(SellpointValueDraftWriteNotAllowedError):
        repository.write_draft(
            _bundle(v1.sellpoint_value_profile_version_id, profile_version="spv-v1")
        )

    v2 = repository.create_version(_version_payload("spv-v2"))
    p2 = repository.write_draft(
        _bundle(
            v2.sellpoint_value_profile_version_id,
            profile_version="spv-v2",
            sku_code="TV002",
        )
    )
    _mark_version_ready(
        repository,
        v2.sellpoint_value_profile_version_id,
        sku_code="TV002",
    )
    repository.review_version(
        sellpoint_value_profile_version_id=v2.sellpoint_value_profile_version_id,
        reviewed_by="reviewer-2",
        release_quality_status=SellpointValueReleaseQualityStatus.READY,
    )
    repository.publish_version(
        sellpoint_value_profile_version_id=v2.sellpoint_value_profile_version_id,
        published_by="approver-2",
    )
    session.refresh(
        session.get(
            entities.Core3SellpointValueProfileVersion,
            v1.sellpoint_value_profile_version_id,
        )
    )

    old_version = session.get(
        entities.Core3SellpointValueProfileVersion,
        v1.sellpoint_value_profile_version_id,
    )
    old_profile = session.get(
        entities.Core3SkuSellpointValueProfile,
        p1.profile.sku_sellpoint_value_profile_id,
    )
    new_profile = session.get(
        entities.Core3SkuSellpointValueProfile,
        p2.profile.sku_sellpoint_value_profile_id,
    )
    assert old_version is not None and old_version.is_current is False
    assert old_profile is not None and old_profile.is_current is False
    assert new_profile is not None and new_profile.is_current is True


def test_default_profile_read_only_returns_current_published(
    session: Session,
) -> None:
    repository = _repository(session)
    draft = repository.create_version(_version_payload("spv-draft"))
    repository.write_draft(
        _bundle(
            draft.sellpoint_value_profile_version_id,
            profile_version="spv-draft",
        )
    )
    _mark_version_ready(repository, draft.sellpoint_value_profile_version_id)

    assert repository.get_current_published_profile(
        batch_id="batch-tv", sku_code="TV001"
    ) is None
    assert repository.resolve_profile_targets(
        batch_id="batch-tv", sku_code="TV001"
    ) == []
    preview_targets = repository.resolve_profile_targets(
        batch_id="batch-tv",
        profile_version="spv-draft",
        model_name="65E7Q",
    )
    assert preview_targets == [
        {
            "sku_code": "TV001",
            "brand_name": "海信",
            "model_name": "65E7Q",
            "product_category": "TV",
            "profile_version": "spv-draft",
            "rule_version": SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        }
    ]
    composite_preview = repository.get_profile(
        batch_id="serving-scope:TV:batch-tv,batch-older",
        profile_version="spv-draft",
        sku_code="TV001",
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    )
    assert composite_preview is not None
    assert composite_preview.profile.batch_id == "batch-tv"

    repository.review_version(
        sellpoint_value_profile_version_id=draft.sellpoint_value_profile_version_id,
        reviewed_by="reviewer",
        release_quality_status=SellpointValueReleaseQualityStatus.READY,
    )
    repository.publish_version(
        sellpoint_value_profile_version_id=draft.sellpoint_value_profile_version_id,
        published_by="approver",
    )
    current = repository.get_current_published_profile(
        batch_id="batch-tv", sku_code="TV001"
    )
    composite_current = repository.get_current_published_profile(
        batch_id="serving-scope:TV:batch-tv,batch-older",
        sku_code="TV001",
    )

    assert current is not None
    assert current.profile.profile_version == "spv-draft"
    assert current.profile.release_status == "published"
    assert composite_current is not None
    assert composite_current.profile.result_hash == current.profile.result_hash
    assert repository.resolve_profile_targets(
        batch_id="batch-tv", query="海信 65E7Q"
    )[0]["profile_version"] == "spv-draft"


def test_publish_quality_and_approver_gates(session: Session) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    repository.write_draft(_bundle(version.sellpoint_value_profile_version_id))
    _mark_version_ready(
        repository,
        version.sellpoint_value_profile_version_id,
        limited=True,
    )
    repository.review_version(
        sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
        reviewed_by="reviewer",
        release_quality_status=SellpointValueReleaseQualityStatus.LIMITED,
    )

    with pytest.raises(SellpointValuePublishNotAllowedError, match="non-system"):
        repository.publish_version(
            sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
            published_by="system",
            allow_limited=True,
        )
    with pytest.raises(SellpointValuePublishNotAllowedError, match="allow_limited"):
        repository.publish_version(
            sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
            published_by="approver",
        )
    assert repository.publish_version(
        sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
        published_by="approver",
        allow_limited=True,
    ).is_current is True


def test_publish_rejects_empty_or_incomplete_profile_version(
    session: Session,
) -> None:
    repository = _repository(session)
    empty = repository.create_version(_version_payload("spv-empty"))
    repository.review_version(
        sellpoint_value_profile_version_id=empty.sellpoint_value_profile_version_id,
        reviewed_by="reviewer",
        release_quality_status=SellpointValueReleaseQualityStatus.READY,
    )

    with pytest.raises(SellpointValuePublishNotAllowedError, match="incomplete"):
        repository.publish_version(
            sellpoint_value_profile_version_id=empty.sellpoint_value_profile_version_id,
            published_by="approver",
        )


def test_blocked_quality_cannot_publish_and_context_mismatch_cannot_write(
    session: Session,
) -> None:
    repository = _repository(session)
    with pytest.raises(ValueError, match="scope"):
        repository.create_version(
            _version_payload(
                category_code="AC",
                project_id="project-ac",
                batch_id="batch-ac",
            )
        )

    version = repository.create_version(_version_payload())
    repository.write_draft(_bundle(version.sellpoint_value_profile_version_id))
    repository.review_version(
        sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
        reviewed_by="reviewer",
        release_quality_status=SellpointValueReleaseQualityStatus.BLOCKED,
    )
    with pytest.raises(SellpointValuePublishNotAllowedError, match="blocked"):
        repository.publish_version(
            sellpoint_value_profile_version_id=version.sellpoint_value_profile_version_id,
            published_by="approver",
        )


def test_single_sku_write_rolls_back_when_child_flush_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    original_flush = session.flush

    def fail_on_profile(*args: Any, **kwargs: Any) -> None:
        if any(
            isinstance(row, entities.Core3SkuSellpointValueProfile)
            for row in session.new
        ):
            raise RuntimeError("simulated child write failure")
        original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", fail_on_profile)
    with pytest.raises(RuntimeError, match="simulated"):
        repository.write_draft(_bundle(version.sellpoint_value_profile_version_id))
    monkeypatch.setattr(session, "flush", original_flush)

    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueCandidate)
    ) == 0


def test_tampered_json_is_rejected_on_typed_readback(session: Session) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    written = repository.write_draft(
        _bundle(version.sellpoint_value_profile_version_id)
    )
    row = session.get(
        entities.Core3SkuSellpointValueProfile,
        written.profile.sku_sellpoint_value_profile_id,
    )
    assert row is not None
    row.pm_decisions_json = {"prompt_template": "factory-only"}
    session.flush()

    with pytest.raises(ValidationError, match="factory-only"):
        repository.get_profile(
            batch_id="batch-tv",
            profile_version="spv-v1",
            sku_code="TV001",
            rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        )


def test_persistence_contract_has_no_factory_prompt_or_gold_columns() -> None:
    forbidden_tokens = ("prompt", "gold", "benchmark")
    for table_name in PROFILE_TABLES:
        column_names = {column.name.lower() for column in Base.metadata.tables[table_name].c}
        assert not any(
            token in column_name
            for token in forbidden_tokens
            for column_name in column_names
        )
    source = MIGRATION_PATH.read_text(encoding="utf-8").lower()
    assert "prompt_template" not in source
    assert "gold_set" not in source
