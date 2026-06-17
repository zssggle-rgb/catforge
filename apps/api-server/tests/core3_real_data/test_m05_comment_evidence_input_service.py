from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.comment_evidence_input_service import (
    CommentEvidenceInputRepository,
    CommentEvidenceInputService,
    M05InputBlockedError,
)
from app.services.core3_real_data.constants import CommentSampleStatus, Core3RunStatus
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
RUN_ID = "run-m05-d"
M02_MODULE_RUN_ID = "module-run-m02"


def make_session(*, m02_status: str = "warning") -> Session:
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
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
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
            module_run_id=M02_MODULE_RUN_ID,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M02",
            batch_id=BATCH_ID,
            status=m02_status,
            output_count=5,
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_id=RUN_ID,
            module_run_id=M02_MODULE_RUN_ID,
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


def evidence(
    evidence_id: str,
    *,
    sku_code: str = "TV00029115",
    evidence_type: str = "comment_raw",
    evidence_grain: str = "row",
    evidence_field: str = "comment_raw",
    clean_table: str = "core3_clean_comment",
    clean_record_key: str | None = None,
    clean_hash: str | None = None,
    source_row_id: str | None = None,
    comment_id: str | None = "c-001",
    comment_text_hash: str | None = "sha256:text:comment",
    segment_text_hash: str | None = None,
    sentence_seq: int | None = None,
    text_value: str | None = "画质很好，游戏模式延迟低",
    dimension_path_raw: str | None = None,
    evidence_status: str = "current",
    is_current: bool = True,
) -> entities.Core3EvidenceAtom:
    clean_record_key = clean_record_key if clean_record_key is not None else f"{clean_table}:{evidence_id}"
    clean_hash = clean_hash if clean_hash is not None else f"sha256:m01_clean_hash_v1:{evidence_id}"
    return entities.Core3EvidenceAtom(
        evidence_id=evidence_id,
        evidence_key=f"{BATCH_ID}:{sku_code}:{evidence_type}:{evidence_id}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=M02_MODULE_RUN_ID,
        sku_code=sku_code,
        model_name="85E7Q" if sku_code == "TV00029115" else "Other",
        brand_name="海信",
        evidence_type=evidence_type,
        evidence_grain=evidence_grain,
        evidence_field=evidence_field,
        evidence_title=evidence_field,
        source_table="comment_data",
        source_pk=evidence_id,
        source_row_id=source_row_id if source_row_id is not None else f"comment_data:{evidence_id}",
        source_row_hash=f"sha256:m00_row_hash_v1:{evidence_id}",
        clean_table=clean_table,
        clean_record_key=clean_record_key,
        clean_hash=clean_hash,
        clean_version="m01_clean_v1",
        raw_field=evidence_field,
        raw_value=text_value,
        clean_field=evidence_field,
        clean_value=text_value,
        value_presence="present",
        numeric_values_json=[],
        text_value=text_value,
        text_hash=segment_text_hash or comment_text_hash,
        comment_id=comment_id,
        comment_text_hash=comment_text_hash,
        segment_text_hash=segment_text_hash,
        sentence_seq=sentence_seq,
        dimension_path_raw=dimension_path_raw,
        quality_status="ok",
        quality_flags=[],
        base_confidence=Decimal("0.9000"),
        confidence_level="high",
        evidence_payload_json={"text": text_value},
        evidence_status=evidence_status,
        is_current=is_current,
        evidence_version="m02_evidence_v1",
        confidence_rule_version="m02_confidence_v1",
        asset_version="default",
        review_required=False,
        review_status="auto_pass",
    )


def seed_comment_evidence(session: Session) -> None:
    session.add_all(
        [
            evidence("ev_raw", evidence_type="comment_raw", evidence_grain="row"),
            evidence(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_grain="sentence",
                evidence_field="comment_sentence:0",
                clean_table="core3_clean_comment_sentence",
                clean_record_key="comment_sentence:comment_data:ev_raw:0",
                segment_text_hash="sha256:segment:1",
                sentence_seq=0,
                text_value="游戏模式延迟低",
            ),
            evidence(
                "ev_dimension",
                evidence_type="comment_dimension",
                evidence_grain="dimension",
                evidence_field="comment_dimension",
                clean_table="core3_clean_comment_dimension",
                clean_record_key="comment_dimension:comment_data:ev_raw:0",
                dimension_path_raw="产品体验/游戏流畅",
            ),
            evidence(
                "ev_quality",
                evidence_type="quality_issue",
                evidence_grain="quality",
                evidence_field="quality_issue:comment:duplicate_comment_text",
                clean_table="core3_data_quality_issue",
                clean_record_key="quality:duplicate_comment_text:TV00029115",
                text_value="重复评论提示",
            ),
            evidence(
                "ev_low_value_quality",
                evidence_type="quality_issue",
                evidence_grain="quality",
                evidence_field="quality_issue:comment:low_value_comment",
                clean_table="core3_data_quality_issue",
                clean_record_key="quality:low_value_comment:TV00029115",
                text_value="低价值评论提示",
            ),
            evidence("ev_param", evidence_type="param_raw", evidence_grain="field", source_row_id="attribute_data:1"),
            evidence("ev_old", evidence_type="comment_raw", evidence_status="superseded", is_current=False),
            evidence("ev_other_sku", sku_code="TV00010001", evidence_type="comment_raw"),
        ]
    )
    session.flush()


def test_m05_input_repository_requires_consumable_m02_module_run():
    warning_session = make_session(m02_status=Core3RunStatus.WARNING.value)
    assert CommentEvidenceInputRepository(make_context(warning_session)).assert_m02_completed(BATCH_ID).status == "warning"

    failed_session = make_session(m02_status=Core3RunStatus.FAILED.value)
    with pytest.raises(M05InputBlockedError, match="not consumable"):
        CommentEvidenceInputRepository(make_context(failed_session)).assert_m02_completed(BATCH_ID)


def test_m05_input_repository_reads_only_current_comment_evidence_by_sku():
    session = make_session()
    seed_comment_evidence(session)
    repo = CommentEvidenceInputRepository(make_context(session))

    sku_codes = repo.list_sku_codes_with_comment_evidence(BATCH_ID)
    records = repo.list_comment_evidence(BATCH_ID, sku_scope=["TV00029115"])
    type_counts = repo.count_comment_evidence_by_type(BATCH_ID, sku_code="TV00029115")
    hashes = repo.get_evidence_result_hashes(["ev_raw", "ev_sentence"])

    assert sku_codes == ["TV00010001", "TV00029115"]
    assert {record.evidence_id for record in records} == {"ev_raw", "ev_sentence", "ev_dimension"}
    assert type_counts == {
        "comment_dimension": 1,
        "comment_raw": 1,
        "comment_sentence": 1,
    }
    assert hashes == {
        "ev_raw": "sha256:m01_clean_hash_v1:ev_raw",
        "ev_sentence": "sha256:m01_clean_hash_v1:ev_sentence",
    }

    with pytest.raises(ValueError, match="unsupported M05 evidence_types"):
        repo.list_comment_evidence(BATCH_ID, evidence_types=["param_raw"])


def test_m05_input_service_builds_bundle_and_stable_input_fingerprint():
    session = make_session()
    seed_comment_evidence(session)
    service = CommentEvidenceInputService(CommentEvidenceInputRepository(make_context(session)))

    first = service.build_sku_bundle(BATCH_ID, "TV00029115", seed_content_hash="sha256:seed")
    second = service.build_sku_bundle(BATCH_ID, "TV00029115", seed_content_hash="sha256:seed")
    changed_seed = service.build_sku_bundle(BATCH_ID, "TV00029115", seed_content_hash="sha256:changed")

    assert first.bundle.sku_code == "TV00029115"
    assert first.bundle.model_name == "85E7Q"
    assert [item.evidence_id for item in first.bundle.evidence_inputs] == [
        "ev_dimension",
        "ev_raw",
        "ev_sentence",
    ]
    assert first.raw_count == 1
    assert first.sentence_count == 1
    assert first.dimension_count == 1
    assert first.quality_issue_count == 0
    assert first.sample_status == CommentSampleStatus.INSUFFICIENT
    assert first.review_required is False
    assert first.blocked is False
    assert first.can_degrade_sentence is False
    assert first.bundle.input_fingerprint == second.bundle.input_fingerprint
    assert first.bundle.input_fingerprint != changed_seed.bundle.input_fingerprint


def test_m05_input_service_marks_missing_raw_and_sentence_degrade_cases():
    no_raw_session = make_session()
    no_raw_session.add(evidence("ev_sentence_only", evidence_type="comment_sentence", clean_table="core3_clean_comment_sentence"))
    no_raw_session.flush()
    no_raw = CommentEvidenceInputService(CommentEvidenceInputRepository(make_context(no_raw_session))).build_sku_bundle(
        BATCH_ID,
        "TV00029115",
    )

    assert no_raw.raw_count == 0
    assert no_raw.sample_status == CommentSampleStatus.UNKNOWN
    assert no_raw.review_required is True
    assert no_raw.blocked is False
    assert [issue.issue_code for issue in no_raw.issues] == ["m05_missing_comment_raw"]

    raw_only_session = make_session()
    raw_only_session.add(evidence("ev_raw_only", evidence_type="comment_raw"))
    raw_only_session.flush()
    raw_only = CommentEvidenceInputService(
        CommentEvidenceInputRepository(make_context(raw_only_session))
    ).build_sku_bundle(BATCH_ID, "TV00029115")

    assert raw_only.raw_count == 1
    assert raw_only.sentence_count == 0
    assert raw_only.can_degrade_sentence is True
    assert raw_only.review_required is True
    assert {issue.issue_code for issue in raw_only.issues} == {
        "m05_missing_comment_sentence",
        "m05_missing_comment_dimension",
    }


def test_m05_input_service_flags_traceability_without_generating_downstream_conclusions():
    session = make_session()
    session.add_all(
        [
            evidence("ev_no_clean_key", clean_record_key="", evidence_type="comment_raw"),
            evidence(
                "ev_weak_trace",
                evidence_type="comment_sentence",
                clean_table="core3_clean_comment_sentence",
                comment_id=None,
                comment_text_hash=None,
                source_row_id="",
                segment_text_hash="sha256:segment:weak",
            ),
        ]
    )
    session.flush()
    result = CommentEvidenceInputService(CommentEvidenceInputRepository(make_context(session))).build_sku_bundle(
        BATCH_ID,
        "TV00029115",
    )

    assert result.blocked is True
    assert result.review_required is True
    assert {issue.issue_code for issue in result.issues} >= {
        "m05_missing_clean_record_trace",
        "m05_weak_comment_trace",
    }
    assert_no_forbidden_business_fields(result.bundle.model_dump())


def assert_no_forbidden_business_fields(payload):
    forbidden = {
        "task_code",
        "target_group_code",
        "battlefield_code",
        "competitor_sku_code",
        "candidate_sku_code",
        "selection_slot",
        "business_conclusion",
        "report_payload",
        "report_content",
        "rank",
        "score",
    }
    if isinstance(payload, dict):
        assert forbidden.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_forbidden_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_business_fields(item)
