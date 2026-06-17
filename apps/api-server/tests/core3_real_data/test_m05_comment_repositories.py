from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.comment_evidence_repositories import (
    CommentEvidenceAtomRepository,
    CommentEvidenceReadRepository,
    CommentQualityProfileRepository,
    CommentTopicHintRepository,
    CommentUnitEvidenceLinkRepository,
    CommentUnitRepository,
)
from app.services.core3_real_data.comment_evidence_schemas import CommentUnitEvidenceLinkRecord
from app.services.core3_real_data.comment_quality_profile_service import CommentQualityProfileService
from app.services.core3_real_data.repositories import Core3RepositoryContext

from .test_m05_comment_quality_profile_service import (
    BATCH_ID,
    PROJECT_ID,
    SKU_CODE,
    make_atom,
    make_topic,
    make_unit,
)


RUN_ID = "run-m05-m"
MODULE_RUN_ID = "module-run-m05-m"


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
        entities.Core3CommentUnit.__table__,
        entities.Core3CommentUnitEvidenceLink.__table__,
        entities.Core3CommentEvidenceAtom.__table__,
        entities.Core3CommentTopicHint.__table__,
        entities.Core3CommentQualityProfile.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    seed_foundation(session)
    return session


def seed_foundation(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3V2PipelineRun(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_mode="daily_incremental",
            ruleset_version="tv-core3-real-data-v2-0.1.0",
        )
    )
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=MODULE_RUN_ID,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M05",
            batch_id=BATCH_ID,
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_id=RUN_ID,
            module_run_id=MODULE_RUN_ID,
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            status="registered",
            review_status="auto_pass",
        )
    )
    session.flush()


def make_context(session: Session) -> Core3RepositoryContext:
    return Core3RepositoryContext(db=session, project_id=PROJECT_ID)


def make_link(unit) -> CommentUnitEvidenceLinkRecord:
    return CommentUnitEvidenceLinkRecord(
        unit_link_id="unit-link-0",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=MODULE_RUN_ID,
        sku_code=SKU_CODE,
        model_name=unit.model_name,
        brand_name=unit.brand_name,
        comment_unit_id=unit.comment_unit_id,
        source_evidence_id=unit.source_comment_evidence_ids[0],
        source_evidence_type="comment_raw",
        link_role="raw_source",
        source_row_id="comment_data:raw-0",
        comment_id=unit.comment_id,
        comment_text_hash=unit.comment_text_hash,
        rule_version=unit.rule_version,
        asset_version=unit.asset_version,
        input_fingerprint=unit.input_fingerprint,
        result_hash="sha256:unit-link:0",
    )


def build_profile(units, atoms, topics):
    return CommentQualityProfileService().build_profile(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        comment_units=units,
        sentence_atoms=atoms,
        topic_hints=topics,
    ).record


def test_comment_unit_repository_reuses_same_hash_and_updates_same_key_changed_hash():
    session = make_session()
    repository = CommentUnitRepository(make_context(session))
    unit = make_unit(0)

    created = repository.bulk_upsert_comment_units([unit])
    reused = repository.bulk_upsert_comment_units([unit])
    updated_unit = unit.model_copy(update={"result_hash": "sha256:unit:changed", "confidence": Decimal("0.7000")})
    updated = repository.bulk_upsert_comment_units([updated_unit])

    assert created.created_count == 1
    assert reused.reused_count == 1
    assert updated.updated_count == 1
    persisted = repository.get_unit(unit.comment_unit_id)
    assert persisted is not None
    assert persisted.result_hash == "sha256:unit:changed"
    assert persisted.confidence == Decimal("0.7000")
    assert len(repository.get_current_by_fingerprint(BATCH_ID, SKU_CODE, unit.input_fingerprint)) == 1
    assert len(repository.list_current_units(BATCH_ID, SKU_CODE)) == 1


def test_comment_repositories_persist_and_filter_links_atoms_topics_and_profile():
    session = make_session()
    context = make_context(session)
    unit = make_unit(0)
    atom = make_atom(0, unit, domain="product_experience", sentiment="positive")
    topic = make_topic(0, atom)
    profile = build_profile([unit], [atom], [topic])

    CommentUnitRepository(context).bulk_upsert_comment_units([unit])
    CommentUnitEvidenceLinkRepository(context).bulk_insert_links([make_link(unit)])
    CommentEvidenceAtomRepository(context).bulk_upsert_atoms([atom])
    CommentTopicHintRepository(context).bulk_upsert_topic_hints([topic])
    CommentQualityProfileRepository(context).upsert_profile(profile)

    links_by_unit = CommentUnitEvidenceLinkRepository(context).list_links_by_unit(unit.comment_unit_id)
    links_by_source = CommentUnitEvidenceLinkRepository(context).list_links_by_source_evidence(
        unit.source_comment_evidence_ids[0]
    )
    atoms_by_domain = CommentEvidenceAtomRepository(context).list_current_atoms(
        BATCH_ID,
        SKU_CODE,
        primary_domain_hint="product_experience",
        sentiment_hint="positive",
        usable_for_downstream=True,
        topic_code="TOPIC_GAMING_SMOOTHNESS",
    )
    topics = CommentTopicHintRepository(context).list_current_topic_hints(
        BATCH_ID,
        SKU_CODE,
        topic_code="TOPIC_GAMING_SMOOTHNESS",
        topic_hint_status="matched",
    )
    topic_distribution = CommentTopicHintRepository(context).aggregate_topic_distribution(BATCH_ID, SKU_CODE)
    persisted_profile = CommentQualityProfileRepository(context).get_current_profile(BATCH_ID, SKU_CODE)
    review_profiles = CommentQualityProfileRepository(context).list_review_required_profiles(BATCH_ID)

    assert [link.source_evidence_id for link in links_by_unit] == [unit.source_comment_evidence_ids[0]]
    assert [link.unit_link_id for link in links_by_source] == ["unit-link-0"]
    assert [record.comment_evidence_id for record in atoms_by_domain] == [atom.comment_evidence_id]
    assert CommentEvidenceAtomRepository(context).count_usable_atoms(BATCH_ID, SKU_CODE) == 1
    assert [record.topic_hint_id for record in topics] == [topic.topic_hint_id]
    assert topic_distribution == {"TOPIC_GAMING_SMOOTHNESS": 1}
    assert persisted_profile is not None
    assert persisted_profile.comment_quality_profile_id == profile.comment_quality_profile_id
    assert [record.comment_quality_profile_id for record in review_profiles] == [profile.comment_quality_profile_id]


def test_comment_repositories_mark_current_outputs_inactive_and_clean_links():
    session = make_session()
    context = make_context(session)
    unit = make_unit(0)
    atom = make_atom(0, unit)
    topic = make_topic(0, atom)
    profile = build_profile([unit], [atom], [topic])

    unit_repo = CommentUnitRepository(context)
    link_repo = CommentUnitEvidenceLinkRepository(context)
    atom_repo = CommentEvidenceAtomRepository(context)
    topic_repo = CommentTopicHintRepository(context)
    profile_repo = CommentQualityProfileRepository(context)
    unit_repo.bulk_upsert_comment_units([unit])
    link_repo.bulk_insert_links([make_link(unit)])
    atom_repo.bulk_upsert_atoms([atom])
    topic_repo.bulk_upsert_topic_hints([topic])
    profile_repo.upsert_profile(profile)

    assert unit_repo.mark_previous_inactive(BATCH_ID, SKU_CODE, rule_version=unit.rule_version) == 1
    assert atom_repo.mark_previous_inactive(BATCH_ID, SKU_CODE, rule_version=atom.rule_version) == 1
    assert topic_repo.mark_previous_inactive(BATCH_ID, SKU_CODE, rule_version=topic.rule_version) == 1
    assert profile_repo.mark_previous_inactive(BATCH_ID, SKU_CODE, rule_version=profile.rule_version) == 1
    assert link_repo.delete_current_links_for_sku(BATCH_ID, SKU_CODE, rule_version=unit.rule_version) == 1

    assert unit_repo.list_current_units(BATCH_ID, SKU_CODE) == []
    assert atom_repo.list_current_atoms(BATCH_ID, SKU_CODE) == []
    assert topic_repo.list_current_topic_hints(BATCH_ID, SKU_CODE) == []
    assert profile_repo.get_current_profile(BATCH_ID, SKU_CODE) is None
    assert session.execute(select(entities.Core3CommentUnitEvidenceLink)).scalars().all() == []


def test_combined_comment_evidence_read_repository_exposes_m05_boundaries():
    session = make_session()
    repository = CommentEvidenceReadRepository(make_context(session))
    unit = make_unit(0)

    repository.bulk_upsert_comment_units([unit])

    assert [record.comment_unit_id for record in repository.list_current_units(BATCH_ID, SKU_CODE)] == [
        unit.comment_unit_id
    ]

