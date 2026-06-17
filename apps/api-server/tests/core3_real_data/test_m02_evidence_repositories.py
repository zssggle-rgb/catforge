from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.evidence_atom_repositories import (
    CurrentEvidenceReader,
    EvidenceAtomRepository,
    EvidenceCurrentConflictError,
    EvidenceLinkRepository,
)
from app.services.core3_real_data.evidence_confidence import EvidenceConfidenceService
from app.services.core3_real_data.evidence_mappers import EvidenceMapper
from app.services.core3_real_data.evidence_payloads import EvidencePayloadBuilder
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
        entities.Core3EvidenceLink.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 13, tzinfo=timezone.utc),
            status="registered",
        )
    )
    session.flush()
    return session


def make_context(session: Session) -> Core3RepositoryContext:
    return Core3RepositoryContext(db=session, project_id=PROJECT_ID)


def atom_payload(clean_table: str = "core3_clean_attribute", **overrides) -> dict:
    source_record = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "brand_name": "海信",
        "source_table": "attribute_data",
        "source_pk": "123",
        "source_row_id": "attribute_data:123",
        "source_row_hash": "sha256:m00_row_hash_v1:source",
        "clean_record_key": "attribute:attribute_data:123",
        "clean_hash": "sha256:m01_clean_hash_v1:attr",
        "clean_version": "m01_clean_v1",
        "quality_status": "ok",
        "quality_flags": [],
        "raw_attr_name": "刷新率",
        "clean_attr_name": "刷新率",
        "raw_attr_value": "144Hz",
        "clean_attr_value": "144Hz",
        "value_presence": "present",
    }
    source_record.update(overrides)
    draft = EvidenceMapper().map_clean_record(source_record, clean_table=clean_table)
    payload = EvidencePayloadBuilder().build_atom_values(draft)
    confidence = EvidenceConfidenceService().calculate(
        draft,
        evidence_payload=payload["evidence_payload_json"],
    )
    payload.update(
        base_confidence=confidence.base_confidence,
        confidence_level=confidence.confidence_level.value,
        evidence_status="current",
        inactive_reason=None,
        is_current=True,
        evidence_version="m02_evidence_v1",
        confidence_rule_version="m02_confidence_v1",
        asset_version="default",
        review_required=False,
        review_status="auto_pass",
    )
    return payload


def test_evidence_atom_repository_is_idempotent_and_lists_current_by_sku():
    session = make_session()
    repo = EvidenceAtomRepository(make_context(session))
    payload = atom_payload()

    first = repo.save_atom(payload)
    second = repo.save_atom({**payload, "evidence_title": "不应覆盖"})
    current = repo.find_current_by_key(payload["evidence_key"])
    sku_evidence = repo.list_current_by_sku(BATCH_ID, "TV00029115", evidence_types=["param_raw"])

    assert first.created is True
    assert second.created is False
    assert second.record.evidence_id == first.record.evidence_id
    assert current is not None
    assert current.evidence_id == payload["evidence_id"]
    assert [record.evidence_id for record in sku_evidence] == [payload["evidence_id"]]


def test_evidence_atom_repository_supersedes_old_current_when_clean_hash_changes():
    session = make_session()
    repo = EvidenceAtomRepository(make_context(session))
    old_payload = atom_payload(clean_attr_value="144Hz", clean_hash="sha256:m01_clean_hash_v1:old")
    new_payload = atom_payload(clean_attr_value="165Hz", clean_hash="sha256:m01_clean_hash_v1:new")

    old = repo.save_atom(old_payload)
    new = repo.save_atom(new_payload)
    old_record = repo.get_by_id(old.record.evidence_id)
    current = repo.find_current_by_key(old_payload["evidence_key"])
    all_versions = repo.list_by_clean_record(BATCH_ID, "core3_clean_attribute", "attribute:attribute_data:123")

    assert new.created is True
    assert new.superseded_record is not None
    assert new.superseded_record.evidence_id == old.record.evidence_id
    assert old_record is not None
    assert old_record.evidence_status == "superseded"
    assert old_record.is_current is False
    assert old_record.inactive_reason == "superseded_by_clean_hash"
    assert current is not None
    assert current.evidence_id == new.record.evidence_id
    assert len(all_versions) == 2


def test_evidence_atom_repository_marks_clean_record_inactive_without_deleting_history():
    session = make_session()
    repo = EvidenceAtomRepository(make_context(session))
    payload = atom_payload()
    saved = repo.save_atom(payload)

    affected = repo.mark_inactive_by_clean_record(
        BATCH_ID,
        "core3_clean_attribute",
        "attribute:attribute_data:123",
        inactive_reason="clean_record_inactive",
    )
    record = repo.get_by_id(saved.record.evidence_id)
    current = repo.list_by_clean_record(
        BATCH_ID,
        "core3_clean_attribute",
        "attribute:attribute_data:123",
        current_only=True,
    )
    all_versions = repo.list_by_clean_record(BATCH_ID, "core3_clean_attribute", "attribute:attribute_data:123")

    assert affected == 1
    assert record is not None
    assert record.evidence_status == "inactive"
    assert record.is_current is False
    assert record.inactive_reason == "clean_record_inactive"
    assert current == []
    assert len(all_versions) == 1


def test_evidence_atom_repository_detects_multiple_current_rows_for_same_key():
    session = make_session()
    repo = EvidenceAtomRepository(make_context(session))
    payload = atom_payload()
    repo.save_atom(payload)
    conflict_payload = {
        **payload,
        "evidence_id": f"{payload['evidence_id']}:conflict",
        "clean_hash": "sha256:m01_clean_hash_v1:conflict",
    }
    model_fields = set(entities.Core3EvidenceAtom.__table__.columns.keys())
    session.add(entities.Core3EvidenceAtom(**{key: value for key, value in conflict_payload.items() if key in model_fields}))
    session.flush()

    with pytest.raises(EvidenceCurrentConflictError, match="multiple current evidence"):
        repo.find_current_by_key(payload["evidence_key"])


def test_evidence_link_repository_is_idempotent_and_queries_directions():
    session = make_session()
    context = make_context(session)
    atom_repo = EvidenceAtomRepository(context)
    link_repo = EvidenceLinkRepository(context)
    comment = atom_repo.save_atom(
        atom_payload(
            "core3_clean_comment",
            source_table="comment_data",
            source_pk="4",
            source_row_id="comment_data:4",
            clean_record_key="comment:comment_data:4",
            clean_hash="sha256:m01_clean_hash_v1:comment",
            clean_comment_text="打游戏很流畅",
            comment_text_presence="present",
            low_value_flag=False,
        )
    )
    sentence = atom_repo.save_atom(
        atom_payload(
            "core3_clean_comment_sentence",
            source_table="comment_data",
            source_pk="4",
            source_row_id="comment_data:4",
            clean_record_key="comment_sentence:comment_data:4:1",
            clean_hash="sha256:m01_clean_hash_v1:comment_sentence",
            sentence_source="segment",
            sentence_seq=1,
            sentence_text="打游戏很流畅",
        )
    )

    payload = {
        "batch_id": BATCH_ID,
        "from_evidence_id": comment.record.evidence_id,
        "to_evidence_id": sentence.record.evidence_id,
        "from_evidence_key": comment.record.evidence_key,
        "to_evidence_key": sentence.record.evidence_key,
        "link_type": "has_sentence",
        "link_payload_json": {"source_row_id": "comment_data:4"},
        "confidence": Decimal("1.0000"),
    }
    first = link_repo.save_link(payload)
    second = link_repo.save_link({**payload, "link_payload_json": {"ignored": True}})
    from_links = link_repo.list_links(comment.record.evidence_id, direction="from")
    to_links = link_repo.list_links(sentence.record.evidence_id, direction="to")
    both_links = link_repo.list_links(comment.record.evidence_id, direction="both", current_only=False)
    count_by_type = link_repo.count_by_type(BATCH_ID)
    inactive_count = link_repo.mark_links_inactive_for_evidence(comment.record.evidence_id)
    active_after_inactive = link_repo.list_links(comment.record.evidence_id)
    all_after_inactive = link_repo.list_links(comment.record.evidence_id, current_only=False)

    assert first.created is True
    assert second.created is False
    assert second.record.link_id == first.record.link_id
    assert [link.link_id for link in from_links] == [first.record.link_id]
    assert [link.link_id for link in to_links] == [first.record.link_id]
    assert [link.link_id for link in both_links] == [first.record.link_id]
    assert count_by_type == {"has_sentence": 1}
    assert inactive_count == 1
    assert active_after_inactive == []
    assert all_after_inactive[0].link_status == "inactive"


def test_current_reader_and_summary_filter_current_evidence_only():
    session = make_session()
    context = make_context(session)
    repo = EvidenceAtomRepository(context)
    current_reader = CurrentEvidenceReader(context)
    high_payload = atom_payload()
    low_payload = atom_payload(
        "core3_clean_comment",
        source_table="comment_data",
        source_pk="4",
        source_row_id="comment_data:4",
        clean_record_key="comment:comment_data:4",
        clean_hash="sha256:m01_clean_hash_v1:comment",
        clean_comment_text="默认好评",
        comment_text_presence="present",
        low_value_flag=True,
    )
    low_payload.update(
        base_confidence=Decimal("0.2500"),
        confidence_level="low",
        review_required=True,
        review_status="review_required",
    )
    repo.save_atom(high_payload)
    repo.save_atom(low_payload)

    current_param = current_reader.list_current(
        BATCH_ID,
        sku_code="TV00029115",
        evidence_types=["param_raw"],
        confidence_levels=["high"],
    )
    current_low = current_reader.list_current(
        BATCH_ID,
        sku_code="TV00029115",
        confidence_levels=["low"],
    )
    summary = repo.get_summary(BATCH_ID)

    assert [record.evidence_id for record in current_param] == [high_payload["evidence_id"]]
    assert [record.evidence_id for record in current_low] == [low_payload["evidence_id"]]
    assert summary["total"] == 2
    assert summary["current"] == 2
    assert summary["low_confidence"] == 1
    assert summary["review_required"] == 1
    assert summary["by_type"] == {"comment_raw": 1, "param_raw": 1}
    assert summary["by_confidence_level"] == {"high": 1, "low": 1}
