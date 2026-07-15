from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileVersionDraftCreate,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileImmutableError,
    CompetitorProfileRepository,
    CompetitorProfileVersionNotFoundError,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_reader import (
    CompetitorProfileV11ReadRequest,
    CompetitorProfileV11Reader,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11IntegrityError,
    CompetitorProfileV11Repository,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_METHOD_VERSION,
    COMPETITOR_PROFILE_V1_1_RULE_VERSION,
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
    CompetitorProfileAnalysisDTO,
    VersionSkuAnalysisSnapshot,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_competitor_profile_v1_1_schemas import (
    _conclusion,
    _dto_payload,
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


def _repository(session: Session) -> CompetitorProfileV11Repository:
    return CompetitorProfileV11Repository(
        Core3RepositoryContext(
            db=session,
            project_id="project-1",
            category_code=Core3CategoryCode.TV,
        )
    )


def _version_payload() -> CompetitorProfileVersionDraftCreate:
    return CompetitorProfileVersionDraftCreate(
        project_id="project-1",
        category_code="TV",
        product_category="TV",
        storage_batch_id="batch-1",
        release_scope_key="project-1:TV",
        profile_version="competitor-profile-v1-1-test",
        schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
        rule_version=COMPETITOR_PROFILE_V1_1_RULE_VERSION,
        method_version=COMPETITOR_PROFILE_V1_1_METHOD_VERSION,
        method_versions_json={"profile": COMPETITOR_PROFILE_V1_1_METHOD_VERSION},
        serving_scope={
            "project_id": "project-1",
            "category_code": "TV",
            "product_category": "TV",
            "storage_batch_id": "batch-1",
            "release_scope_key": "project-1:TV",
            "analysis_population": "online_market",
            "market_window": "2026-01/2026-06",
            "taxonomy_version": "taxonomy-tv-v1",
            "source_batch_ids": ["batch-1"],
            "source_authorities": {
                "M12D": {
                    "module_code": "M12D",
                    "project_id": "project-1",
                    "category_code": "TV",
                    "product_category": "TV",
                    "profile_version": "m12d-tv-v1",
                    "schema_version": "schema-v1",
                    "rule_version": "m12d-tv-rule-v1",
                    "taxonomy_version": "taxonomy-tv-v1",
                    "release_status": "published",
                    "is_current": True,
                    "source_batch_ids": ["batch-1"],
                    "result_hash": "hash:m12d",
                }
            },
            "sku_prefixes": ["TV"],
            "authoritative_sku_count": 2,
            "authoritative_sku_manifest_hash": "hash:manifest",
        },
        sku_count=1,
        ready_count=1,
        pair_count=1,
        relation_count=7,
        selection_count=1,
        input_fingerprint="fingerprint:version",
        candidate_universe_fingerprint="fingerprint:universe",
        result_hash="hash:version",
        processing_status="completed",
    )


def _dto(version_id: str) -> CompetitorProfileAnalysisDTO:
    payload = copy.deepcopy(_dto_payload())
    payload["profile_version"]["competitor_profile_version_id"] = version_id
    for key in ("target_snapshot",):
        payload[key]["competitor_profile_version_id"] = version_id
    for snapshot in payload["candidate_snapshots"]:
        snapshot["competitor_profile_version_id"] = version_id
    for pair in payload["pair_analyses"]:
        pair["competitor_profile_version_id"] = version_id
    return CompetitorProfileAnalysisDTO.model_validate(payload)


def _self_pair_dto(version_id: str) -> CompetitorProfileAnalysisDTO:
    payload = copy.deepcopy(_dto_payload())
    payload["profile_version"]["competitor_profile_version_id"] = version_id
    target = payload["target_snapshot"]
    target["competitor_profile_version_id"] = version_id
    payload["candidate_snapshots"] = [copy.deepcopy(target)]
    pair = payload["pair_analyses"][0]
    pair["competitor_profile_version_id"] = version_id
    for field in (
        "purchase_pool",
        "dimensions",
        "value_anchor_analysis",
        "replacement_pressure_analysis",
        "purchase_pressure_comparison",
        "market_validation",
        "score_breakdown",
    ):
        pair[field] = None
    pair.update(
        {
            "candidate_sku_code": "T1",
            "candidate_snapshot_ref": target["snapshot_ref"],
            "scope_status": "excluded",
            "exclusion_reason_code": "self_pair",
            "comparison_roles": [],
            "primary_role": None,
            "legacy_primary_role": None,
            "relation_assessments": [],
            "business_questions": [],
            "source_facts": [],
            "overall_conclusion_strength": "unknown",
            "overall_conclusion": _conclusion(
                code="self_pair_excluded",
                strength="unknown",
            ),
            "result_hash": "hash:self-pair",
        }
    )
    payload["sku_summary"].update(
        {
            "dimension_availability_counts": {},
            "conclusion_strength_counts": {"unknown": 1},
            "priority_competitors": [],
            "role_buckets": {},
            "unknown_dimensions": [],
        }
    )
    payload["priority_selections"] = []
    payload["full_pair_index"] = [
        {
            "candidate_sku_code": "T1",
            "scope_status": "excluded",
            "recall_rank": pair["recall_rank"],
            "primary_role": None,
            "conclusion_strength": "unknown",
            "selected_rank": None,
            "pair_result_hash": "hash:self-pair",
        }
    ]
    payload["profile_result_hash"] = "hash:self-profile"
    return CompetitorProfileAnalysisDTO.model_validate(payload)


def _all_unknown_dto(version_id: str) -> CompetitorProfileAnalysisDTO:
    payload = copy.deepcopy(_dto_payload())
    payload["profile_version"]["competitor_profile_version_id"] = version_id
    payload["target_snapshot"]["competitor_profile_version_id"] = version_id
    payload["candidate_snapshots"][0]["competitor_profile_version_id"] = version_id
    pair = payload["pair_analyses"][0]
    pair["competitor_profile_version_id"] = version_id
    def unknown_score(weight: str) -> dict:
        return {
            "configured_weight": weight,
            "raw_score": None,
            "available_weight": "0",
            "normalized_score": None,
            "weighted_contribution": "0",
        }
    pair["purchase_pool"] = {
        "level": "unknown",
        "gate_facts": [
            {
                "gate_code": "category_form",
                "known": False,
                "passed": None,
                "reason_code": "product_form_missing",
            }
        ],
        "score": unknown_score("0.20"),
        "conclusion": _conclusion(code="purchase_pool_unknown", strength="unknown"),
        "result_hash": "hash:purchase-pool-unknown",
    }
    for dimension in pair["dimensions"].values():
        dimension.update(
            {
                "availability": "unknown",
                "score": unknown_score(dimension["score"]["configured_weight"]),
                "calculation_components": [],
                "conclusion_strength": "unknown",
                "conclusion": _conclusion(
                    code=f"{dimension['dimension_code']}_unknown",
                    strength="unknown",
                ),
            }
        )
    pair["value_anchor_analysis"].update(
        {
            "shared_anchors": [],
            "target_stronger_anchors": [],
            "candidate_stronger_anchors": [],
            "purchase_pressure_comparison": {
                "comparison_allowed": False,
                "conclusion": _conclusion(
                    code="purchase_pressure_unknown",
                    strength="unknown",
                ),
                "calculator_method_version": "purchase-pressure-v1",
                "calculator_config_version": "purchase-pressure-config-v1",
                "result_hash": "hash:purchase-pressure-unknown",
            },
            "anchor_substitutability_score": None,
            "anchor_substitutability_level": "unknown",
            "score": unknown_score("0.15"),
            "conclusion_strength": "unknown",
            "conclusion": _conclusion(code="value_anchor_unknown", strength="unknown"),
        }
    )
    pair["replacement_pressure_analysis"].update(
        {
            "primary_pressure_type": "unknown",
            "auxiliary_pressure_types": [],
            "replacement_pressure_score": None,
            "replacement_pressure_level": "unknown",
            "score": unknown_score("0.10"),
            "conclusion_strength": "unknown",
            "conclusion": _conclusion(
                code="replacement_pressure_unknown",
                strength="unknown",
            ),
        }
    )
    pair["market_validation"].update(
        {
            "target_weighted_price": None,
            "candidate_weighted_price": None,
            "price_gap": None,
            "price_ratio": None,
            "market_validation_strength": "unknown",
            "conclusion": _conclusion(
                code="market_validation_unknown",
                strength="unknown",
            ),
        }
    )
    pair["market_validation"]["sales_overlap_snapshot"].update(
        {
            "overlap_weeks": [],
            "target_overall_weekly_volume": None,
            "candidate_overall_weekly_volume": None,
            "target_overlap_weekly_volume": None,
            "candidate_overlap_weekly_volume": None,
            "volume_gap": None,
            "volume_ratio": None,
        }
    )
    for component in pair["score_breakdown"]["components"]:
        component.update(
            {
                "availability": "unknown",
                "raw_score": None,
                "weighted_contribution": "0",
            }
        )
    pair["score_breakdown"].update(
        {
            "raw_total": "0",
            "available_weight": "0",
            "normalized_total": None,
            "coverage": "0",
            "ranking_score": None,
        }
    )
    for relation in pair["relation_assessments"]:
        relation.update(
            {
                "status": "unassessable",
                "missing_dimensions": sorted(relation["required_dimensions"]),
                "conclusion_strength": "unknown",
                "conclusion": _conclusion(
                    code=f"{relation['relation_code']}_unknown",
                    strength="unknown",
                ),
            }
        )
    for question in pair["business_questions"]:
        question.update(
            {
                "answerable": False,
                "conclusion_strength": "unknown",
                "conclusion": _conclusion(
                    code=f"{question['question_code']}_unknown",
                    strength="unknown",
                ),
                "missing_dimensions": (
                    []
                    if question["question_code"] == "key_competitor_selection"
                    else sorted(question["required_dimensions"])
                ),
            }
        )
        for group in question["alternative_evidence_groups"]:
            group["satisfied_dimensions"] = []
    pair.update(
        {
            "overall_conclusion_strength": "unknown",
            "overall_conclusion": _conclusion(code="overall_unknown", strength="unknown"),
        }
    )
    payload["sku_summary"].update(
        {
            "dimension_availability_counts": {"unknown": 7},
            "conclusion_strength_counts": {"unknown": 1},
            "priority_competitors": [],
            "role_buckets": {"direct_competitor": ["C1"]},
            "unknown_dimensions": sorted(pair["dimensions"]),
        }
    )
    payload["priority_selections"] = []
    payload["full_pair_index"][0].update(
        {
            "conclusion_strength": "unknown",
            "selected_rank": None,
        }
    )
    payload["profile_result_hash"] = "hash:all-unknown-profile"
    return CompetitorProfileAnalysisDTO.model_validate(payload)


def _zero_candidate_dto(version_id: str) -> CompetitorProfileAnalysisDTO:
    payload = copy.deepcopy(_dto_payload())
    payload["profile_version"]["competitor_profile_version_id"] = version_id
    payload["target_snapshot"]["competitor_profile_version_id"] = version_id
    payload["candidate_snapshots"] = []
    payload["pair_analyses"] = []
    payload["full_pair_index"] = []
    payload["priority_selections"] = []
    payload["sku_summary"].update(
        {
            "analysis_candidate_count": 0,
            "legacy_candidate_count": 0,
            "dimension_availability_counts": {},
            "conclusion_strength_counts": {},
            "priority_competitors": [],
            "role_buckets": {},
            "unknown_dimensions": [],
        }
    )
    payload["profile_result_hash"] = "hash:zero-candidate-profile"
    return CompetitorProfileAnalysisDTO.model_validate(payload)


def _write(session: Session) -> tuple[CompetitorProfileV11Repository, CompetitorProfileAnalysisDTO]:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)
    repository.write_draft(dto)
    return repository, dto


def _count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _insert_snapshot(
    session: Session,
    dto: CompetitorProfileAnalysisDTO,
    *,
    result_hash: str | None = None,
) -> None:
    snapshot = dto.target_snapshot
    session.add(
        entities.Core3CompetitorProfileSkuSnapshot(
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            project_id=dto.profile_version.project_id,
            category_code=dto.profile_version.category_code,
            release_scope_key=dto.profile_version.release_scope_key,
            sku_code=snapshot.identity_market.sku_code,
            profile_version="competitor-profile-v1-1-test",
            schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
            rule_version=COMPETITOR_PROFILE_V1_1_RULE_VERSION,
            method_version=COMPETITOR_PROFILE_V1_1_METHOD_VERSION,
            snapshot_json=snapshot.model_dump(mode="json"),
            module_availability_json=[
                row.model_dump(mode="json") for row in snapshot.module_availability
            ],
            evidence_refs_json=[
                row.model_dump(mode="json") for row in snapshot.evidence_refs
            ],
            source_lineage_json=snapshot.source_lineage,
            limitations_json=snapshot.limitations,
            input_fingerprint=snapshot.input_fingerprint,
            result_hash=result_hash or snapshot.result_hash,
        )
    )
    session.flush()


def _insert_unrelated_snapshot_with_ref(
    session: Session,
    dto: CompetitorProfileAnalysisDTO,
    *,
    snapshot_ref: str,
) -> None:
    payload = dto.target_snapshot.model_dump(mode="json")
    payload["identity_market"]["sku_code"] = "OTHER"
    payload["snapshot_ref"] = snapshot_ref
    payload["result_hash"] = "hash:other-snapshot"
    snapshot = VersionSkuAnalysisSnapshot.model_validate(payload)
    session.add(
        entities.Core3CompetitorProfileSkuSnapshot(
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            project_id=dto.profile_version.project_id,
            category_code=dto.profile_version.category_code,
            release_scope_key=dto.profile_version.release_scope_key,
            sku_code=snapshot.identity_market.sku_code,
            profile_version="competitor-profile-v1-1-test",
            schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
            rule_version=COMPETITOR_PROFILE_V1_1_RULE_VERSION,
            method_version=COMPETITOR_PROFILE_V1_1_METHOD_VERSION,
            snapshot_json=snapshot.model_dump(mode="json"),
            module_availability_json=[
                row.model_dump(mode="json") for row in snapshot.module_availability
            ],
            evidence_refs_json=[
                row.model_dump(mode="json") for row in snapshot.evidence_refs
            ],
            source_lineage_json=snapshot.source_lineage,
            limitations_json=snapshot.limitations,
            input_fingerprint=snapshot.input_fingerprint,
            result_hash=snapshot.result_hash,
        )
    )
    session.flush()


def test_atomic_write_roundtrip_is_lossless_and_idempotent(session: Session) -> None:
    repository, dto = _write(session)
    second = repository.write_draft(dto)

    assert second == dto
    assert _count(session, entities.Core3CompetitorProfileSkuSnapshot) == 2
    assert _count(session, entities.Core3SkuCompetitorProfile) == 1
    assert _count(session, entities.Core3SkuCompetitorProfilePair) == 1
    assert _count(session, entities.Core3SkuCompetitorProfileRelation) == 7
    assert _count(session, entities.Core3SkuCompetitorProfileSelection) == 1

    changed = dto.model_copy(deep=True)
    changed.profile_result_hash = "hash:different"
    with pytest.raises(CompetitorProfileImmutableError):
        repository.write_draft(changed)


def test_version_snapshot_is_reused_and_conflicting_unique_row_fails_closed(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)
    _insert_snapshot(session, dto)
    assert repository.write_draft(dto) == dto
    assert _count(session, entities.Core3CompetitorProfileSkuSnapshot) == 2

    session.rollback()
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)
    _insert_snapshot(session, dto, result_hash="hash:conflicting-snapshot")
    with pytest.raises(CompetitorProfileImmutableError, match="snapshot is immutable"):
        repository.write_draft(dto)
    assert _count(session, entities.Core3SkuCompetitorProfile) == 0


def test_snapshot_ref_has_one_sku_owner_across_the_entire_version(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)
    _insert_unrelated_snapshot_with_ref(
        session,
        dto,
        snapshot_ref=dto.target_snapshot.snapshot_ref,
    )
    with pytest.raises(CompetitorProfileV11IntegrityError, match="different SKUs in a version"):
        repository.write_draft(dto)
    assert _count(session, entities.Core3SkuCompetitorProfile) == 0

    session.rollback()
    repository, dto = _write(session)
    _insert_unrelated_snapshot_with_ref(
        session,
        dto,
        snapshot_ref=dto.target_snapshot.snapshot_ref,
    )
    for read_mode in ("full", "compact", "question_specific"):
        kwargs = (
            {"question_code": "purchase_choice"}
            if read_mode == "question_specific"
            else {}
        )
        with pytest.raises(
            CompetitorProfileV11IntegrityError,
            match="different SKUs in a version",
        ):
            repository.get_profile(
                competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
                target_sku_code="T1",
                read_mode=read_mode,
                preview=True,
                **kwargs,
            )


def test_self_pair_hard_exclusion_reuses_target_snapshot_and_roundtrips(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _self_pair_dto(version.competitor_profile_version_id)
    assert repository.write_draft(dto) == dto
    assert _count(session, entities.Core3CompetitorProfileSkuSnapshot) == 1
    assert _count(session, entities.Core3SkuCompetitorProfilePair) == 1
    assert _count(session, entities.Core3SkuCompetitorProfileRelation) == 0
    assert _count(session, entities.Core3SkuCompetitorProfileSelection) == 0


def test_all_unknown_analyzable_pair_has_no_primary_relation_and_roundtrips(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _all_unknown_dto(version.competitor_profile_version_id)
    assert repository.write_draft(dto) == dto
    primary_count = session.scalar(
        select(func.count())
        .select_from(entities.Core3SkuCompetitorProfileRelation)
        .where(entities.Core3SkuCompetitorProfileRelation.is_primary.is_(True))
    )
    assert primary_count == 0
    compact = repository.get_profile(
        competitor_profile_version_id=version.competitor_profile_version_id,
        target_sku_code="T1",
        read_mode="compact",
        preview=True,
    )
    assert compact is not None and compact.compact is not None


def test_zero_candidate_profile_resolves_target_snapshot_without_pair_refs(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _zero_candidate_dto(version.competitor_profile_version_id)
    assert repository.write_draft(dto) == dto
    compact = repository.get_profile(
        competitor_profile_version_id=version.competitor_profile_version_id,
        target_sku_code="T1",
        read_mode="compact",
        preview=True,
    )
    assert compact is not None and compact.compact is not None
    assert compact.compact.full_pair_index == []


def test_concurrent_unique_profile_conflict_reloads_identical_saved_graph(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, dto = _write(session)
    concurrent_repository = _repository(session)
    original_find = concurrent_repository._find_v11_profile
    calls = 0

    def miss_once(*, version_id: str, target_sku_code: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return original_find(
            version_id=version_id,
            target_sku_code=target_sku_code,
        )

    monkeypatch.setattr(concurrent_repository, "_find_v11_profile", miss_once)
    assert concurrent_repository.write_draft(dto) == dto
    assert calls >= 2
    assert _count(session, entities.Core3SkuCompetitorProfile) == 1


def test_failed_child_write_rolls_back_snapshots_and_every_profile_row(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)

    def fail(*args, **kwargs) -> None:
        raise RuntimeError("synthetic relation failure")

    monkeypatch.setattr(repository, "_insert_relations", fail)
    with pytest.raises(RuntimeError, match="synthetic relation failure"):
        repository.write_draft(dto)

    assert _count(session, entities.Core3CompetitorProfileSkuSnapshot) == 0
    assert _count(session, entities.Core3SkuCompetitorProfile) == 0
    assert _count(session, entities.Core3SkuCompetitorProfilePair) == 0
    assert _count(session, entities.Core3SkuCompetitorProfileRelation) == 0
    assert _count(session, entities.Core3SkuCompetitorProfileSelection) == 0


def test_atomic_write_cannot_disable_savepoint_or_trust_post_validation_mutation(
    session: Session,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)
    with pytest.raises(ValueError, match="require use_savepoint"):
        repository.write_draft(dto, use_savepoint=False)
    assert _count(session, entities.Core3CompetitorProfileSkuSnapshot) == 0

    dto.candidate_snapshots[0].snapshot_ref = "snapshot:mutated-after-validation"
    with pytest.raises(ValueError, match="refs must resolve"):
        repository.write_draft(dto)
    assert _count(session, entities.Core3CompetitorProfileSkuSnapshot) == 0
    assert _count(session, entities.Core3SkuCompetitorProfile) == 0
    session.commit()
    assert _count(session, entities.Core3SkuCompetitorProfilePair) == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_batch_ids", ["other-batch"]),
        ("market_window", "other-window"),
        ("analysis_population", "offline-market"),
    ],
)
def test_version_source_lineage_must_match_dto_context(
    session: Session,
    field_name: str,
    value,
) -> None:
    repository = _repository(session)
    version = repository.create_version(_version_payload())
    dto = _dto(version.competitor_profile_version_id)
    setattr(dto.profile_version, field_name, value)
    with pytest.raises(ValueError, match="source batches, market window, and population"):
        repository.write_draft(dto)
    assert _count(session, entities.Core3SkuCompetitorProfile) == 0


def test_full_compact_and_question_reads_are_deterministic_and_bounded(
    session: Session,
) -> None:
    repository, dto = _write(session)
    statements = 0
    statement_texts: list[str] = []

    @event.listens_for(session.bind, "before_cursor_execute")
    def count_selects(_conn, _cursor, statement, _params, _context, _many) -> None:
        nonlocal statements
        if statement.lstrip().upper().startswith("SELECT"):
            statements += 1
            statement_texts.append(statement)

    full = repository.get_profile(
        competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        target_sku_code="T1",
        preview=True,
    )
    full_selects = statements
    assert full is not None and full.full == dto
    assert full_selects == 7

    statements = 0
    statement_texts.clear()
    compact = repository.get_profile(
        competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        target_sku_code="T1",
        read_mode="compact",
        preview=True,
    )
    assert compact is not None and compact.compact is not None
    assert compact.compact.full_pair_index == dto.full_pair_index
    assert statements == 7
    assert not any("analysis_snapshot_json" in sql for sql in statement_texts)

    statements = 0
    question = repository.get_profile(
        competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        target_sku_code="T1",
        read_mode="question_specific",
        question_code="purchase_choice",
        preview=True,
    )
    assert question is not None and question.question is not None
    assert question.question.pairs[0].question_result.question_code == "purchase_choice"
    assert statements == 7

    repeated = repository.get_profile(
        competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        target_sku_code="T1",
        preview=True,
    )
    assert repeated == full


def test_compact_selection_cannot_drift_from_saved_pair(
    session: Session,
) -> None:
    repository, dto = _write(session)
    selection = session.execute(
        select(entities.Core3SkuCompetitorProfileSelection)
    ).scalars().one()
    selection_payload = dict(selection.selection_payload_json)
    selection_payload["selection_score"] = "0.75"
    selection.selection_payload_json = selection_payload
    profile = session.execute(select(entities.Core3SkuCompetitorProfile)).scalars().one()
    summary = dict(profile.analysis_summary_json)
    priorities = [dict(row) for row in summary["priority_competitors"]]
    priorities[0]["selection_score"] = "0.75"
    summary["priority_competitors"] = priorities
    profile.analysis_summary_json = summary
    session.flush()
    with pytest.raises(CompetitorProfileV11IntegrityError, match="score, role, or question"):
        repository.get_profile(
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            target_sku_code="T1",
            read_mode="compact",
            preview=True,
        )


def test_pair_index_scope_and_strength_tampering_fails_in_every_read_mode(
    session: Session,
) -> None:
    repository, dto = _write(session)
    profile = session.execute(select(entities.Core3SkuCompetitorProfile)).scalars().one()
    payload = dict(profile.profile_payload_json)
    pair_index = [dict(row) for row in payload["full_pair_index"]]
    pair_index[0].update(
        {"scope_status": "excluded", "conclusion_strength": "unknown"}
    )
    payload["full_pair_index"] = pair_index
    profile.profile_payload_json = payload
    session.flush()
    reads = (
        {"read_mode": "full"},
        {"read_mode": "compact"},
        {"read_mode": "question_specific", "question_code": "purchase_choice"},
    )
    for kwargs in reads:
        with pytest.raises(CompetitorProfileV11IntegrityError):
            repository.get_profile(
                competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
                target_sku_code="T1",
                preview=True,
                **kwargs,
            )


@pytest.mark.parametrize("tamper", ["pair_recall_rank", "summary_conclusion"])
def test_compact_integrity_receipt_closes_summary_and_pair_index(
    session: Session,
    tamper: str,
) -> None:
    repository, dto = _write(session)
    profile = session.execute(select(entities.Core3SkuCompetitorProfile)).scalars().one()
    if tamper == "pair_recall_rank":
        payload = copy.deepcopy(profile.profile_payload_json)
        payload["full_pair_index"][0]["recall_rank"] += 1
        profile.profile_payload_json = payload
    else:
        summary = copy.deepcopy(profile.analysis_summary_json)
        summary["competitive_advantages"].append(
            {
                "finding_code": "tampered_advantage",
                "candidate_sku_codes": ["C1"],
                "conclusion": _conclusion(
                    code="tampered_advantage",
                    strength="supported",
                ),
                "evidence_refs": [],
            }
        )
        profile.analysis_summary_json = summary
    session.flush()

    with pytest.raises(CompetitorProfileV11IntegrityError, match="integrity receipt"):
        repository.get_profile(
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            target_sku_code="T1",
            read_mode="compact",
            preview=True,
        )


def test_dangling_and_cross_scope_snapshot_refs_fail_closed(session: Session) -> None:
    repository, dto = _write(session)
    version_id = dto.profile_version.competitor_profile_version_id
    session.execute(
        update(entities.Core3SkuCompetitorProfilePair)
        .where(entities.Core3SkuCompetitorProfilePair.competitor_profile_version_id == version_id)
        .values(candidate_snapshot_ref="snapshot:missing")
    )
    session.flush()
    with pytest.raises(CompetitorProfileV11IntegrityError, match="dangling"):
        repository.get_profile(
            competitor_profile_version_id=version_id,
            target_sku_code="T1",
            preview=True,
        )

    session.rollback()
    repository, dto = _write(session)
    snapshot = session.execute(
        select(entities.Core3CompetitorProfileSkuSnapshot)
        .where(entities.Core3CompetitorProfileSkuSnapshot.sku_code == "C1")
    ).scalars().one()
    payload = dict(snapshot.snapshot_json)
    payload["release_scope_key"] = "other:TV"
    snapshot.snapshot_json = payload
    session.flush()
    with pytest.raises(CompetitorProfileV11IntegrityError):
        repository.get_profile(
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            target_sku_code="T1",
            preview=True,
        )


def test_reader_separates_formal_current_from_explicit_draft_preview(
    session: Session,
) -> None:
    repository, dto = _write(session)
    reader = CompetitorProfileV11Reader(repository)
    formal_request = CompetitorProfileV11ReadRequest(
        project_id="project-1",
        category_code="TV",
        release_scope_key="project-1:TV",
        target_sku_code="T1",
        read_mode="compact",
    )
    assert reader.read(formal_request).status == "profile_unavailable"

    preview = reader.read(
        CompetitorProfileV11ReadRequest(
            project_id="project-1",
            category_code="TV",
            release_scope_key="project-1:TV",
            target_sku_code="T1",
            access_mode="preview",
            read_mode="compact",
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            allow_draft_preview=True,
        )
    )
    assert preview.status == "available" and preview.preview is True

    with pytest.raises(ValueError, match="formal reads"):
        CompetitorProfileV11ReadRequest(
            project_id="project-1",
            category_code="TV",
            release_scope_key="project-1:TV",
            target_sku_code="T1",
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        )


def test_legacy_v1_repository_does_not_read_v1_1_rows(session: Session) -> None:
    repository, dto = _write(session)
    legacy = CompetitorProfileRepository(repository.context)
    with pytest.raises(CompetitorProfileVersionNotFoundError):
        legacy.get_profile(
            competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
            target_sku_code="T1",
            preview=True,
        )
    with pytest.raises(CompetitorProfileVersionNotFoundError):
        legacy.get_version_by_id(dto.profile_version.competitor_profile_version_id)
    assert legacy.list_versions(release_scope_key="project-1:TV") == []


def test_formal_read_requires_every_release_row_to_be_current_published(
    session: Session,
) -> None:
    repository, dto = _write(session)
    version_id = dto.profile_version.competitor_profile_version_id
    session.execute(
        update(entities.Core3CompetitorProfileVersion)
        .where(entities.Core3CompetitorProfileVersion.competitor_profile_version_id == version_id)
        .values(
            release_status="published",
            is_current=True,
            published_by="test",
            current_by="test",
            current_at=datetime.now(timezone.utc),
        )
    )
    session.execute(
        update(entities.Core3SkuCompetitorProfile)
        .where(entities.Core3SkuCompetitorProfile.competitor_profile_version_id == version_id)
        .values(release_status="published", is_current=True)
    )
    session.flush()
    with pytest.raises(CompetitorProfileV11IntegrityError, match="every analytical row"):
        repository.get_current_published_profile(
            release_scope_key="project-1:TV",
            target_sku_code="T1",
            read_mode="compact",
        )
    for model in (
        entities.Core3SkuCompetitorProfilePair,
        entities.Core3SkuCompetitorProfileRelation,
        entities.Core3SkuCompetitorProfileSelection,
    ):
        session.execute(
            update(model)
            .where(model.competitor_profile_version_id == version_id)
            .values(release_status="published", is_current=True)
        )
    session.flush()
    result = repository.get_current_published_profile(
        release_scope_key="project-1:TV",
        target_sku_code="T1",
        read_mode="compact",
    )
    assert result is not None and result.preview is False
    serving_result = CompetitorProfileV11Reader(repository).read(
        CompetitorProfileV11ReadRequest(
            project_id="project-1",
            category_code="TV",
            target_sku_code="T1",
            read_mode="compact",
        )
    )
    assert serving_result.status == "available"
    assert serving_result.competitor_profile_version_id == version_id


def test_unknown_null_and_empty_typed_values_survive_storage(session: Session) -> None:
    repository, dto = _write(session)
    readback = repository.get_profile(
        competitor_profile_version_id=dto.profile_version.competitor_profile_version_id,
        target_sku_code="T1",
        preview=True,
    )
    assert readback is not None and readback.full is not None
    assert readback.full.model_dump(mode="json") == dto.model_dump(mode="json")
