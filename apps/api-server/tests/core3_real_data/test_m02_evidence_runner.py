from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    Core3EvidenceLinkStatus,
    Core3ModuleTargetScope,
    Core3QualityIssueType,
    Core3RunMode,
    Core3SourceBatchStatus,
    Core3TargetScopeType,
)
from app.services.core3_real_data.evidence_atom_service import (
    MAX_SQL_EXCLUDE_SOURCE_ROW_IDS,
    EvidenceAtomRunner,
    _exclude_source_rows,
)
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
RUN_ID = "run-m02-g"
MODULE_RUN_ID = "module-run-m02-g"


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
        entities.Core3CleanSku.__table__,
        entities.Core3CleanMarketWeekly.__table__,
        entities.Core3CleanAttribute.__table__,
        entities.Core3CleanClaim.__table__,
        entities.Core3CleanClaimSentence.__table__,
        entities.Core3CleanComment.__table__,
        entities.Core3CleanCommentSentence.__table__,
        entities.Core3CleanCommentDimension.__table__,
        entities.Core3DataQualityIssue.__table__,
        entities.Core3EvidenceAtom.__table__,
        entities.Core3EvidenceLink.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    seed_foundation(session)
    seed_clean_facts(session)
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
            module_code="M02",
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
            status=Core3SourceBatchStatus.REGISTERED.value,
            review_status="auto_pass",
        )
    )
    session.flush()


def seed_clean_facts(session: Session) -> None:
    common = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
    }
    session.add(
        entities.Core3CleanSku(
            **common,
            sku_code="TV00029115",
            sku_code_raw_values=["TV00029115"],
            model_name="85E7Q",
            model_name_raw_values=["85E7Q"],
            brand_name="海信",
            brand_raw_values=["海信"],
            category_name="彩电",
            source_tables=["attribute_data", "selling_points_data", "comment_data"],
            first_seen_source_row_id="attribute_data:2",
            representative_source_row_ids=["attribute_data:2", "selling_points_data:3", "comment_data:4"],
            coverage_json={"attribute": {"covered": True}, "claim": {"covered": True}, "comment": {"covered": True}},
            field_conflicts_json={},
            missing_signals_json={},
            clean_record_key="sku:TV00029115",
            clean_hash="sha256:m01_clean_hash_v1:sku",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
            quality_flags=[],
            review_required=False,
            review_status="auto_pass",
        )
    )
    session.add(
        entities.Core3CleanAttribute(
            **common,
            source_table="attribute_data",
            source_pk="2",
            source_row_id="attribute_data:2",
            source_row_hash="sha256:m00_row_hash_v1:attribute",
            source_operation_type="insert",
            sku_code="TV00029115",
            model_name="85E7Q",
            brand_name="海信",
            raw_attr_name="刷新率",
            clean_attr_name="刷新率",
            raw_attr_value="144Hz",
            clean_attr_value="144Hz",
            value_presence="present",
            value_number_candidates=[144],
            value_unit_candidates=["Hz"],
            clean_record_key="attribute:attribute_data:2",
            clean_hash="sha256:m01_clean_hash_v1:attribute",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
            quality_flags=[],
            review_required=False,
            review_status="auto_pass",
        )
    )
    claim = entities.Core3CleanClaim(
        **common,
        source_table="selling_points_data",
        source_pk="3",
        source_row_id="selling_points_data:3",
        source_row_hash="sha256:m00_row_hash_v1:claim",
        source_operation_type="insert",
        sku_code="TV00029115",
        model_name="85E7Q",
        brand_name="海信",
        claim_seq_raw="卖点1",
        claim_seq=1,
        raw_claim_text="游戏低延迟，体育画面流畅",
        clean_claim_text="游戏低延迟，体育画面流畅",
        claim_text_presence="present",
        title_hint="游戏低延迟",
        structure_hints={},
        clean_record_key="claim:selling_points_data:3",
        clean_hash="sha256:m01_clean_hash_v1:claim",
        clean_version="m01_clean_v1",
        hash_version="m01_clean_hash_v1",
        quality_status="ok",
        quality_flags=[],
        review_required=False,
        review_status="auto_pass",
    )
    session.add(claim)
    session.flush()
    session.add(
        entities.Core3CleanClaimSentence(
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            source_row_id="selling_points_data:3",
            clean_claim_id=claim.clean_claim_id,
            sku_code="TV00029115",
            claim_seq=1,
            sentence_seq=1,
            sentence_text="游戏低延迟",
            sentence_text_hash="sha256:text:claim-sentence",
            sentence_role_hint="body",
            split_rule="m01_rule",
            clean_record_key="claim_sentence:selling_points_data:3:1",
            clean_hash="sha256:m01_clean_hash_v1:claim_sentence",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
            quality_flags=[],
        )
    )
    comment = entities.Core3CleanComment(
        **common,
        source_table="comment_data",
        source_pk="4",
        source_row_id="comment_data:4",
        source_row_hash="sha256:m00_row_hash_v1:comment",
        source_operation_type="insert",
        sku_code="TV00029115",
        model_name="85E7Q",
        brand_name="海信",
        platform_raw="京东",
        url_id="u-4",
        comment_id="c-4",
        comment_time_raw="2026-06-10 09:00:00",
        comment_time=datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc),
        comment_time_parse_status="parsed",
        raw_comment_text="画质很好，游戏模式延迟低",
        clean_comment_text="画质很好，游戏模式延迟低",
        comment_text_presence="present",
        comment_text_hash="sha256:text:comment",
        segment_text_raw="画质很好",
        segment_text_clean="画质很好",
        segment_text_hash="sha256:segment:comment",
        sentiment_raw="正面",
        sentiment_clean="positive",
        low_value_flag=False,
        duplicate_group_key="dup:comment",
        dimension_available=True,
        clean_record_key="comment:comment_data:4",
        clean_hash="sha256:m01_clean_hash_v1:comment",
        clean_version="m01_clean_v1",
        hash_version="m01_clean_hash_v1",
        quality_status="ok",
        quality_flags=[],
        review_required=False,
        review_status="auto_pass",
    )
    session.add(comment)
    session.flush()
    session.add_all(
        [
            entities.Core3CleanCommentSentence(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                source_row_id="comment_data:4",
                clean_comment_id=comment.clean_comment_id,
                sku_code="TV00029115",
                comment_id="c-4",
                sentence_source="segment",
                sentence_seq=1,
                sentence_text="画质很好",
                sentence_text_hash="sha256:text:comment-sentence",
                source_segment_text="画质很好",
                is_from_existing_segment=True,
                split_rule="m01_rule",
                clean_record_key="comment_sentence:comment_data:4:segment:1",
                clean_hash="sha256:m01_clean_hash_v1:comment_sentence",
                clean_version="m01_clean_v1",
                hash_version="m01_clean_hash_v1",
                quality_status="ok",
                quality_flags=[],
            ),
            entities.Core3CleanCommentDimension(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                source_row_id="comment_data:4",
                clean_comment_id=comment.clean_comment_id,
                sku_code="TV00029115",
                comment_id="c-4",
                primary_dim_raw="产品体验",
                secondary_dim_raw="画质",
                third_dim_raw=None,
                dimension_path_raw="产品体验>画质",
                dimension_available=True,
                dimension_quality_flag="ok",
                clean_record_key="comment_dimension:comment_data:4",
                clean_hash="sha256:m01_clean_hash_v1:comment_dimension",
                clean_version="m01_clean_v1",
                hash_version="m01_clean_hash_v1",
                quality_status="ok",
                quality_flags=[],
            ),
        ]
    )
    session.add(
        entities.Core3DataQualityIssue(
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            run_id=RUN_ID,
            module_run_id=MODULE_RUN_ID,
            module_code="M01",
            domain="param",
            source_table="attribute_data",
            source_row_id="attribute_data:2",
            clean_table="core3_clean_attribute",
            clean_record_key="attribute:attribute_data:2",
            sku_code="TV00029115",
            issue_type="unknown_value",
            severity="warning",
            issue_detail="该参数原始值需要复核。",
            issue_payload_json={"clean_record_key": "attribute:attribute_data:2"},
            suggested_downstream_action="M03 降低该参数证据权重。",
            review_required=True,
            review_status="review_required",
        )
    )
    session.flush()


def make_context():
    return build_run_context(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )


def make_target():
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        metadata={"batch_id": BATCH_ID, "module_run_id": MODULE_RUN_ID},
    )


def evidence_by_type(session: Session) -> dict[str, list[entities.Core3EvidenceAtom]]:
    records = session.execute(select(entities.Core3EvidenceAtom)).scalars().all()
    grouped = {}
    for record in records:
        grouped.setdefault(record.evidence_type, []).append(record)
    return grouped


def test_evidence_atom_runner_consumes_clean_facts_and_writes_atoms_links_summary_idempotently():
    session = make_session()
    runner = EvidenceAtomRunner(session)

    first = runner.run(make_context(), make_target())
    second = runner.run(make_context(), make_target())

    grouped = evidence_by_type(session)
    link_counts = second.summary_json["link_counts"]

    assert first.module_code == "M02"
    assert first.status == "warning"
    assert second.status == "warning"
    assert second.summary_json["created_atom_count"] == 0
    assert second.summary_json["reused_atom_count"] == first.input_count
    assert second.summary_json["partition_strategy"] == "sku_partition_v1"
    assert second.summary_json["partition_count"] == 1
    assert second.summary_json["evidence_counts"]["by_type"] == {
        "comment_dimension": 1,
        "comment_raw": 1,
        "comment_sentence": 1,
        "param_raw": 1,
        "promo_raw": 1,
        "promo_sentence": 1,
        "quality_issue": 1,
        "sku_fact": 1,
    }
    assert link_counts["has_sentence"] == 2
    assert link_counts["has_dimension"] == 1
    assert link_counts["has_quality_issue"] >= 1
    assert "m02_low_confidence_evidence" in second.warnings
    assert "m02_review_required_evidence" in second.warnings
    assert {impact["module_code"] for impact in second.downstream_impacts} >= {"M03", "M04a", "M05", "M07"}

    param = grouped["param_raw"][0]
    assert param.clean_record_key == "attribute:attribute_data:2"
    assert param.evidence_payload_json["clean_attr_value"] == "144Hz"
    assert param.base_confidence == Decimal("0.9000")
    assert "task_code" not in param.evidence_payload_json
    assert "battlefield_code" not in param.evidence_payload_json
    assert "competitor_sku_code" not in param.evidence_payload_json
    assert session.execute(select(entities.Core3EvidenceLink)).scalars().all()


def test_large_comment_source_exclusion_does_not_expand_sql_parameters():
    stmt = select(entities.Core3CleanComment)
    source_row_ids = {f"comment_data:{index}" for index in range(MAX_SQL_EXCLUDE_SOURCE_ROW_IDS + 1)}

    filtered_stmt = _exclude_source_rows(stmt, entities.Core3CleanComment, source_row_ids)
    compiled = filtered_stmt.compile()

    assert "NOT IN" not in str(compiled)
    assert not compiled.params


def test_evidence_atom_runner_excludes_low_value_comments_from_semantic_evidence_but_keeps_quality_issue():
    session = make_session()
    common = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "source_table": "comment_data",
        "source_pk": "low-value",
        "source_row_id": "comment_data:low-value",
        "source_row_hash": "sha256:m00_row_hash_v1:low-value",
        "source_operation_type": "insert",
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "brand_name": "海信",
        "platform_raw": "京东",
        "comment_id": "c-low-value",
        "comment_time_parse_status": "missing",
        "clean_version": "m01_clean_v1",
        "hash_version": "m01_clean_hash_v1",
        "quality_status": "warning",
        "quality_flags": [Core3QualityIssueType.LOW_VALUE_COMMENT.value],
        "review_required": False,
        "review_status": "auto_pass",
    }
    low_value_comment = entities.Core3CleanComment(
        **common,
        raw_comment_text="此用户没有填写评价",
        clean_comment_text="此用户没有填写评价",
        comment_text_presence="present",
        comment_text_hash="sha256:text:low-value",
        sentiment_clean="unknown",
        low_value_flag=True,
        low_value_reason="默认或空评价",
        duplicate_group_key="sha256:text:low-value",
        dimension_available=False,
        clean_record_key="comment:comment_data:low-value",
        clean_hash="sha256:m01_clean_hash_v1:low-value-comment",
    )
    session.add(low_value_comment)
    session.flush()
    legacy_semantic_atom = entities.Core3EvidenceAtom(
        evidence_id="legacy-low-value-comment-raw",
        evidence_key="legacy-low-value-comment-raw",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=MODULE_RUN_ID,
        sku_code="TV00029115",
        model_name="85E7Q",
        brand_name="海信",
        evidence_type="comment_raw",
        evidence_grain="row",
        evidence_field="clean_comment_text",
        evidence_title="评论正文",
        source_table="comment_data",
        source_pk="low-value",
        source_row_id="comment_data:low-value",
        source_row_hash="sha256:m00_row_hash_v1:low-value",
        clean_table="core3_clean_comment",
        clean_record_key="comment:comment_data:low-value",
        clean_hash="sha256:m01_clean_hash_v1:legacy-low-value-comment",
        clean_version="m01_clean_v1",
        raw_field="raw_comment_text",
        raw_value="此用户没有填写评价",
        clean_field="clean_comment_text",
        clean_value="此用户没有填写评价",
        value_presence="present",
        text_value="此用户没有填写评价",
        comment_id="c-low-value",
        comment_text_hash="sha256:text:low-value",
        quality_status="warning",
        quality_flags=[Core3QualityIssueType.LOW_VALUE_COMMENT.value],
        base_confidence=Decimal("0.3000"),
        confidence_level="low",
        evidence_payload_json={"legacy": True},
        evidence_status="current",
        is_current=True,
        evidence_version="m02_evidence_v1",
        confidence_rule_version="m02_confidence_v1",
        asset_version="default",
        review_required=True,
        review_status="review_required",
    )
    session.add(legacy_semantic_atom)
    session.add_all(
        [
            entities.Core3CleanCommentSentence(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                source_row_id="comment_data:low-value",
                clean_comment_id=low_value_comment.clean_comment_id,
                sku_code="TV00029115",
                comment_id="c-low-value",
                sentence_source="system_split",
                sentence_seq=1,
                sentence_text="此用户没有填写评价",
                sentence_text_hash="sha256:sentence:low-value",
                is_from_existing_segment=False,
                split_rule="m01_rule",
                clean_record_key="comment_sentence:comment_data:low-value:1",
                clean_hash="sha256:m01_clean_hash_v1:low-value-sentence",
                clean_version="m01_clean_v1",
                hash_version="m01_clean_hash_v1",
                quality_status="ok",
                quality_flags=[],
            ),
            entities.Core3CleanCommentDimension(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                source_row_id="comment_data:low-value",
                clean_comment_id=low_value_comment.clean_comment_id,
                sku_code="TV00029115",
                comment_id="c-low-value",
                dimension_available=False,
                dimension_quality_flag="missing",
                clean_record_key="comment_dimension:comment_data:low-value",
                clean_hash="sha256:m01_clean_hash_v1:low-value-dimension",
                clean_version="m01_clean_v1",
                hash_version="m01_clean_hash_v1",
                quality_status="warning",
                quality_flags=["comment_dimension_missing"],
            ),
            entities.Core3DataQualityIssue(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                run_id=RUN_ID,
                module_run_id=MODULE_RUN_ID,
                module_code="M01",
                domain="comment",
                source_table="comment_data",
                source_row_id="comment_data:low-value",
                clean_table="core3_clean_comment",
                clean_record_key="comment:comment_data:low-value",
                sku_code="TV00029115",
                issue_type=Core3QualityIssueType.LOW_VALUE_COMMENT.value,
                severity="info",
                issue_detail="TV00029115 存在默认评价或空评价",
                issue_payload_json={"comment_id": "c-low-value"},
                suggested_downstream_action="M02 以后不进入评论语义分析链路，仅进入数据质量统计",
                review_required=False,
                review_status="auto_pass",
            ),
        ]
    )
    session.flush()

    result = EvidenceAtomRunner(session).run(make_context(), make_target())

    current_low_value_atoms = session.execute(
        select(entities.Core3EvidenceAtom)
        .where(entities.Core3EvidenceAtom.source_row_id == "comment_data:low-value")
        .where(entities.Core3EvidenceAtom.is_current.is_(True))
        .where(entities.Core3EvidenceAtom.evidence_status == "current")
        .order_by(entities.Core3EvidenceAtom.evidence_type)
    ).scalars().all()
    assert current_low_value_atoms == []
    assert legacy_semantic_atom.evidence_status == "inactive"
    assert legacy_semantic_atom.inactive_reason == "low_value_skipped"
    assert result.summary_json["partition_summaries"][0]["skipped_low_value_comment_count"] == 1


def test_evidence_atom_runner_keeps_only_one_representative_for_duplicate_comment_text():
    session = make_session()
    common = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "source_table": "comment_data",
        "source_operation_type": "insert",
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "brand_name": "海信",
        "platform_raw": "京东",
        "comment_time_parse_status": "parsed",
        "comment_text_presence": "present",
        "comment_text_hash": "sha256:text:large-duplicate",
        "sentiment_clean": "positive",
        "low_value_flag": False,
        "duplicate_group_key": "dup:large-duplicate",
        "dimension_available": False,
        "clean_version": "m01_clean_v1",
        "hash_version": "m01_clean_hash_v1",
        "quality_status": "ok",
        "quality_flags": [],
        "review_required": False,
        "review_status": "auto_pass",
    }
    session.add_all(
        entities.Core3CleanComment(
            **common,
            source_pk=f"dup-{index}",
            source_row_id=f"comment_data:dup-{index}",
            source_row_hash=f"sha256:m00_row_hash_v1:dup-{index}",
            url_id=f"url-dup-{index}",
            comment_id=f"comment-dup-{index}",
            comment_time=datetime(2026, 6, 10, 10, index % 60, tzinfo=timezone.utc),
            raw_comment_text="包装不错，客服很好",
            clean_comment_text="包装不错，客服很好",
            clean_record_key=f"comment:comment_data:dup-{index}",
            clean_hash=f"sha256:m01_clean_hash_v1:comment-dup-{index}",
        )
        for index in range(60)
    )
    session.flush()

    result = EvidenceAtomRunner(session).run(make_context(), make_target())
    duplicate_atoms = (
        session.execute(
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.comment_text_hash == "sha256:text:large-duplicate")
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == "current")
        )
        .scalars()
        .all()
    )

    assert result.summary_json["partition_count"] == 1
    assert len(duplicate_atoms) == 1
    assert duplicate_atoms[0].source_row_id == "comment_data:dup-0"
    assert result.summary_json["partition_summaries"][0]["skipped_duplicate_comment_count"] == 59


def test_evidence_atom_runner_marks_legacy_duplicate_comment_evidence_inactive():
    session = make_session()
    common = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "source_table": "comment_data",
        "source_operation_type": "insert",
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "brand_name": "海信",
        "platform_raw": "京东",
        "comment_time_parse_status": "parsed",
        "comment_text_presence": "present",
        "comment_text_hash": "sha256:text:legacy-duplicate",
        "sentiment_clean": "positive",
        "low_value_flag": False,
        "duplicate_group_key": "dup:legacy-duplicate",
        "dimension_available": False,
        "clean_version": "m01_clean_v1",
        "hash_version": "m01_clean_hash_v1",
        "quality_status": "ok",
        "quality_flags": [],
        "review_required": False,
        "review_status": "auto_pass",
    }
    session.add_all(
        entities.Core3CleanComment(
            **common,
            source_pk=f"legacy-dup-{index}",
            source_row_id=f"comment_data:legacy-dup-{index}",
            source_row_hash=f"sha256:m00_row_hash_v1:legacy-dup-{index}",
            url_id=f"url-legacy-dup-{index}",
            comment_id=f"comment-legacy-dup-{index}",
            comment_time=datetime(2026, 6, 10, 10, index % 60, tzinfo=timezone.utc),
            raw_comment_text="安装很好，物流很快",
            clean_comment_text="安装很好，物流很快",
            clean_record_key=f"comment:comment_data:legacy-dup-{index}",
            clean_hash=f"sha256:m01_clean_hash_v1:legacy-comment-dup-{index}",
        )
        for index in range(60)
    )
    session.flush()

    legacy_left = entities.Core3EvidenceAtom(
        evidence_id="legacy-duplicate-left",
        evidence_key="legacy-duplicate-left",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=MODULE_RUN_ID,
        sku_code="TV00029115",
        evidence_type="comment_raw",
        evidence_grain="row",
        evidence_field="clean_comment_text",
        source_row_id="comment_data:legacy-dup-1",
        clean_table="core3_clean_comment",
        clean_record_key="comment:comment_data:legacy-dup-1",
        clean_hash="sha256:m01_clean_hash_v1:legacy-left",
        clean_version="m01_clean_v1",
        comment_text_hash="sha256:text:legacy-duplicate",
        evidence_status="current",
        is_current=True,
        evidence_version="m02_evidence_v1",
        confidence_rule_version="m02_confidence_v1",
        asset_version="default",
        review_required=False,
        review_status="auto_pass",
    )
    legacy_right = entities.Core3EvidenceAtom(
        evidence_id="legacy-duplicate-right",
        evidence_key="legacy-duplicate-right",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=MODULE_RUN_ID,
        sku_code="TV00029115",
        evidence_type="comment_raw",
        evidence_grain="row",
        evidence_field="clean_comment_text",
        source_row_id="comment_data:legacy-dup-2",
        clean_table="core3_clean_comment",
        clean_record_key="comment:comment_data:legacy-dup-2",
        clean_hash="sha256:m01_clean_hash_v1:legacy-right",
        clean_version="m01_clean_v1",
        comment_text_hash="sha256:text:legacy-duplicate",
        evidence_status="current",
        is_current=True,
        evidence_version="m02_evidence_v1",
        confidence_rule_version="m02_confidence_v1",
        asset_version="default",
        review_required=False,
        review_status="auto_pass",
    )
    session.add_all([legacy_left, legacy_right])
    session.flush()
    legacy_link = entities.Core3EvidenceLink(
        link_id="legacy-pairwise-link",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        from_evidence_id=legacy_left.evidence_id,
        to_evidence_id=legacy_right.evidence_id,
        from_evidence_key=legacy_left.evidence_key,
        to_evidence_key=legacy_right.evidence_key,
        link_type="same_comment_text",
        link_payload_json={
            "match_rule": "comment_text_hash",
            "comment_text_hash": "sha256:text:legacy-duplicate",
            "legacy_pairwise": True,
        },
        confidence=Decimal("0.7000"),
        link_status=Core3EvidenceLinkStatus.CURRENT.value,
    )
    session.add(legacy_link)
    session.flush()

    result = EvidenceAtomRunner(session).run(make_context(), make_target())

    assert result.summary_json["inactive_atom_count"] >= 2
    assert legacy_left.evidence_status == "inactive"
    assert legacy_left.inactive_reason == "duplicate_representative_skipped"
    assert legacy_right.evidence_status == "inactive"
    assert legacy_right.inactive_reason == "duplicate_representative_skipped"
    assert legacy_link.link_status == Core3EvidenceLinkStatus.INACTIVE.value


def test_evidence_atom_runner_supersedes_old_current_when_clean_hash_changes():
    session = make_session()
    runner = EvidenceAtomRunner(session)
    runner.run(make_context(), make_target())
    attribute = session.execute(select(entities.Core3CleanAttribute)).scalar_one()
    attribute.clean_attr_value = "165Hz"
    attribute.clean_hash = "sha256:m01_clean_hash_v1:attribute_changed"

    result = runner.run(make_context(), make_target())

    param_records = (
        session.execute(
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.evidence_type == "param_raw")
            .order_by(entities.Core3EvidenceAtom.created_at, entities.Core3EvidenceAtom.evidence_id)
        )
        .scalars()
        .all()
    )
    supersedes_links = (
        session.execute(select(entities.Core3EvidenceLink).where(entities.Core3EvidenceLink.link_type == "supersedes"))
        .scalars()
        .all()
    )

    assert result.summary_json["superseded_atom_count"] == 1
    assert len(param_records) == 2
    assert [record.evidence_status for record in param_records] == ["superseded", "current"]
    assert param_records[0].evidence_key == param_records[1].evidence_key
    assert param_records[0].evidence_id != param_records[1].evidence_id
    assert len(supersedes_links) == 1
    assert supersedes_links[0].from_evidence_id == param_records[1].evidence_id
    assert supersedes_links[0].to_evidence_id == param_records[0].evidence_id


def test_evidence_atom_runner_blocks_when_m00_batch_is_not_consumable():
    session = make_session()
    batch = session.execute(select(entities.Core3SourceBatch)).scalar_one()
    batch.status = Core3SourceBatchStatus.FAILED.value

    result = EvidenceAtomRunner(session).run(make_context(), make_target())

    assert result.status == "blocked"
    assert result.warnings == ["m02_batch_not_consumable"]
    assert result.output_count == 0
    assert session.execute(select(entities.Core3EvidenceAtom)).scalars().all() == []
