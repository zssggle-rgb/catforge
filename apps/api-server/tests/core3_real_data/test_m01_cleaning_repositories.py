from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.cleaning_repositories import (
    CleanAttributeRepository,
    CleanClaimRepository,
    CleanCommentRepository,
    CleaningQueryRepository,
    CleanMarketRepository,
    CleanSkuRepository,
    DataQualityIssueRepository,
    SourceBatchReader,
    SourceImpactedSkuReader,
    SourceRowRegistryReader,
)
from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    Core3DataDomain,
    Core3QualityIssueSeverity,
    Core3QualityIssueType,
    Core3ReviewStatus,
    Core3SourceBatchStatus,
    Core3SourceOperationType,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext, RawSourceReadOnlyGuard
from app.services.core3_real_data.source_registry_repositories import RawSourceRepository


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
RUN_ID = "run-m01-d"
MODULE_RUN_ID = "module-run-m01-d"


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
        entities.Core3SourceRowRegistry.__table__,
        entities.Core3SourceImpactedSku.__table__,
        entities.Core3CleanSku.__table__,
        entities.Core3CleanMarketWeekly.__table__,
        entities.Core3CleanAttribute.__table__,
        entities.Core3CleanClaim.__table__,
        entities.Core3CleanClaimSentence.__table__,
        entities.Core3CleanComment.__table__,
        entities.Core3CleanCommentSentence.__table__,
        entities.Core3CleanCommentDimension.__table__,
        entities.Core3DataQualityIssue.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    seed_m00_dependencies(session)
    return session


def seed_m00_dependencies(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3V2PipelineRun(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_mode="bootstrap_full",
            ruleset_version="tv-core3-real-data-v2-0.1.0",
        )
    )
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=MODULE_RUN_ID,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M01",
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
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    for index, operation_type in enumerate(
        [
            Core3SourceOperationType.INSERT.value,
            Core3SourceOperationType.UPDATE.value,
            Core3SourceOperationType.NO_CHANGE.value,
            Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN.value,
            Core3SourceOperationType.SKIPPED.value,
        ],
        start=1,
    ):
        session.add(
            entities.Core3SourceRowRegistry(
                row_registry_id=f"m00rr_{index}",
                batch_id=BATCH_ID,
                project_id=PROJECT_ID,
                category_code="TV",
                source_table="attribute_data",
                source_pk=str(index),
                source_pk_strategy="id_column",
                source_row_id=f"attribute_data:{index}",
                row_hash=f"sha256:m00_row_hash_v1:{index}",
                hash_version="m00_row_hash_v1",
                sku_code_candidate="TV00029115",
                operation_type=operation_type,
                affected_modules=["M01"],
                quality_hint={},
                review_status=Core3ReviewStatus.AUTO_PASS.value,
            )
        )
    session.add(
        entities.Core3SourceImpactedSku(
            impacted_sku_id="m00sku_001",
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            sku_code_candidate="TV00029115",
            source_tables=["attribute_data", "comment_data"],
            operation_summary_json={"total_changed_rows": 2},
            affected_modules=["M01"],
            impact_reason="参数和评论原始行发生变化",
            impact_level="high",
            needs_recompute=True,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.flush()


def make_context(session: Session) -> Core3RepositoryContext:
    return Core3RepositoryContext(db=session, project_id=PROJECT_ID)


def common_fact_payload(**overrides):
    payload = {
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "source_pk": "1",
        "source_row_id": "attribute_data:1",
        "source_row_hash": "sha256:m00_row_hash_v1:1",
        "source_operation_type": Core3SourceOperationType.INSERT,
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "brand_name": "海信",
        "clean_record_key": "attribute:attribute_data:1",
        "clean_hash": "sha256:m01_clean_hash_v1:attribute",
        "clean_version": CORE3_M01_CLEAN_VERSION,
        "hash_version": CORE3_M01_CLEAN_HASH_VERSION,
        "record_status": "active",
        "quality_status": "ok",
        "quality_flags": [],
        "review_required": False,
        "review_status": Core3ReviewStatus.AUTO_PASS,
    }
    payload.update(overrides)
    return payload


def test_m01_source_readers_consume_m00_scope_without_direct_raw_scan():
    session = make_session()
    context = make_context(session)

    batch = SourceBatchReader(context).get_consumable_batch(BATCH_ID)
    rows = SourceRowRegistryReader(context).list_processable_rows(BATCH_ID)
    rows_with_no_change = SourceRowRegistryReader(context).list_processable_rows(BATCH_ID, include_no_change=True)
    impacted = SourceImpactedSkuReader(context).list_impacted_skus(BATCH_ID, needs_recompute=True)

    assert batch.batch_id == BATCH_ID
    assert [row.operation_type for row in rows] == ["insert", "update", "not_seen_in_current_scan", "skipped"]
    assert [row.operation_type for row in rows_with_no_change] == [
        "insert",
        "update",
        "no_change",
        "not_seen_in_current_scan",
        "skipped",
    ]
    assert impacted[0].sku_code_candidate == "TV00029115"

    RawSourceReadOnlyGuard.assert_repository_interface_read_only(RawSourceRepository(context))


def test_m01_source_reader_filters_processable_rows_by_target_sku():
    session = make_session()
    context = make_context(session)
    session.add(
        entities.Core3SourceRowRegistry(
            row_registry_id="m00rr_other_sku",
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            source_table="comment_data",
            source_pk="999",
            source_pk_strategy="id_column",
            source_row_id="comment_data:999",
            row_hash="sha256:m00_row_hash_v1:999",
            hash_version="m00_row_hash_v1",
            sku_code_candidate="TV00099999",
            operation_type=Core3SourceOperationType.INSERT.value,
            affected_modules=["M01"],
            quality_hint={},
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.flush()

    rows = SourceRowRegistryReader(context).list_processable_rows(
        BATCH_ID,
        target_sku_codes=("TV00099999",),
    )

    assert [row.source_row_id for row in rows] == ["comment_data:999"]


def test_clean_sku_repository_is_idempotent_and_rejects_hash_conflicts():
    session = make_session()
    repo = CleanSkuRepository(make_context(session))
    payload = {
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "sku_code": "TV00029115",
        "sku_code_raw_values": ["TV00029115"],
        "model_name": "85E7Q",
        "model_name_raw_values": ["85E7Q"],
        "brand_name": "海信",
        "brand_raw_values": ["海信"],
        "category_name": "彩电",
        "source_tables": ["attribute_data", "comment_data"],
        "representative_source_row_ids": ["attribute_data:1"],
        "coverage_json": {"claim": {"covered": False}},
        "field_conflicts_json": {},
        "missing_signals_json": {"claim_structured": {"missing": True}},
        "clean_record_key": "sku:TV00029115",
        "clean_hash": "sha256:m01_clean_hash_v1:sku",
        "clean_version": CORE3_M01_CLEAN_VERSION,
        "hash_version": CORE3_M01_CLEAN_HASH_VERSION,
        "quality_status": "warning",
        "quality_flags": ["claim_coverage_missing"],
        "review_required": True,
        "review_status": Core3ReviewStatus.REVIEW_REQUIRED,
    }

    first = repo.save_sku(payload)
    second = repo.save_sku({**payload, "model_name": "不应覆盖"})

    assert first.created is True
    assert second.created is False
    assert second.record.clean_sku_id == first.record.clean_sku_id
    assert repo.list_clean_skus(BATCH_ID, review_required=True)[0].sku_code == "TV00029115"

    changed = repo.save_sku(
        {
            **payload,
            "model_name": "85E7Q Pro",
            "clean_hash": "sha256:m01_clean_hash_v1:changed",
        }
    )

    assert changed.created is False
    assert changed.record.clean_sku_id == first.record.clean_sku_id
    assert changed.record.model_name == "85E7Q Pro"
    assert changed.record.clean_hash == "sha256:m01_clean_hash_v1:changed"


def test_clean_fact_repositories_write_claim_comment_and_summary():
    session = make_session()
    context = make_context(session)
    market = CleanMarketRepository(context).save_market(
        common_fact_payload(
            source_table="week_sales_data",
            source_pk="10",
            source_row_id="week_sales_data:10",
            source_row_hash="sha256:m00_row_hash_v1:market",
            clean_record_key="market:week_sales_data:10",
            clean_hash="sha256:m01_clean_hash_v1:market",
            category_name_raw="彩电",
            period_raw="26W01",
            period_type="week",
            period_year_hint=2026,
            period_week_index=1,
            period_parse_status="parsed",
            channel_type="online",
            platform_type="jd",
            sales_volume=Decimal("12"),
            sales_amount=Decimal("96000"),
            avg_price=Decimal("8000"),
            price_check_status="ok",
        )
    )
    attribute = CleanAttributeRepository(context).save_attribute(
        common_fact_payload(
            raw_attr_name="刷新率",
            clean_attr_name="刷新率",
            raw_attr_value="300HZ",
            clean_attr_value="300HZ",
            value_presence="present",
            value_number_candidates=[{"number": "300", "unit": "HZ"}],
            value_unit_candidates=["HZ"],
        )
    )
    claim = CleanClaimRepository(context).save_claim(
        common_fact_payload(
            source_table="selling_points_data",
            source_pk="20",
            source_row_id="selling_points_data:20",
            clean_record_key="claim:selling_points_data:20",
            clean_hash="sha256:m01_clean_hash_v1:claim",
            claim_seq_raw="卖点1",
            claim_seq=1,
            raw_claim_text="游戏低延迟",
            clean_claim_text="游戏低延迟",
            claim_text_presence="present",
            structure_hints={},
        )
    )
    claim_sentence = CleanClaimRepository(context).save_claim_sentence(
        common_fact_payload(
            source_table="selling_points_data",
            source_pk="20",
            source_row_id="selling_points_data:20",
            clean_claim_id=claim.record.clean_claim_id,
            claim_seq=1,
            sentence_seq=1,
            sentence_text="游戏低延迟",
            sentence_text_hash="sha256:m01_clean_hash_v1:claim_sentence_text",
            split_rule="punctuation",
            clean_record_key="claim_sentence:selling_points_data:20:1",
            clean_hash="sha256:m01_clean_hash_v1:claim_sentence",
        )
    )
    comment = CleanCommentRepository(context).save_comment(
        common_fact_payload(
            source_table="comment_data",
            source_pk="30",
            source_row_id="comment_data:30",
            clean_record_key="comment:comment_data:30",
            clean_hash="sha256:m01_clean_hash_v1:comment",
            platform_raw="京东",
            comment_id="c-30",
            comment_time_parse_status="missing",
            raw_comment_text="画质很好，游戏模式延迟低",
            clean_comment_text="画质很好，游戏模式延迟低",
            comment_text_presence="present",
            sentiment_clean="positive",
            low_value_flag=False,
            dimension_available=True,
        )
    )
    comment_sentence = CleanCommentRepository(context).save_comment_sentence(
        common_fact_payload(
            source_table="comment_data",
            source_pk="30",
            source_row_id="comment_data:30",
            clean_comment_id=comment.record.clean_comment_id,
            comment_id="c-30",
            sentence_source="system_split",
            sentence_seq=1,
            sentence_text="画质很好",
            sentence_text_hash="sha256:m01_clean_hash_v1:comment_sentence_text",
            split_rule="punctuation",
            clean_record_key="comment_sentence:comment_data:30:system_split:1",
            clean_hash="sha256:m01_clean_hash_v1:comment_sentence",
        )
    )
    dimension = CleanCommentRepository(context).save_comment_dimension(
        common_fact_payload(
            source_table="comment_data",
            source_pk="30",
            source_row_id="comment_data:30",
            clean_comment_id=comment.record.clean_comment_id,
            comment_id="c-30",
            primary_dim_raw="产品体验",
            secondary_dim_raw="画质",
            dimension_path_raw="产品体验/画质",
            dimension_available=True,
            dimension_quality_flag="ok",
            clean_record_key="comment_dimension:comment_data:30",
            clean_hash="sha256:m01_clean_hash_v1:comment_dimension",
        )
    )

    assert market.created is True
    assert attribute.created is True
    assert claim.created is True
    assert claim_sentence.created is True
    assert comment.created is True
    assert comment_sentence.created is True
    assert dimension.created is True

    summary = CleaningQueryRepository(context).get_clean_summary(BATCH_ID)
    drilldown = CleaningQueryRepository(context).get_sku_clean_drilldown(BATCH_ID, "TV00029115")

    assert summary["clean_counts"] == {
        "sku": 0,
        "market": 1,
        "attribute": 1,
        "claim": 1,
        "claim_sentence": 1,
        "comment": 1,
        "comment_sentence": 1,
        "comment_dimension": 1,
        "quality_issue": 0,
    }
    assert drilldown["market"][0].period_week_index == 1
    assert drilldown["attribute"][0].clean_attr_name == "刷新率"
    assert drilldown["claim"][0].claim_seq == 1
    assert drilldown["comment"][0].comment_id == "c-30"


def test_data_quality_issue_repository_dedupes_and_filters_null_safe():
    session = make_session()
    context = make_context(session)
    repo = DataQualityIssueRepository(context)
    payload = {
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "module_code": "M01",
        "domain": Core3DataDomain.CLAIM,
        "source_table": None,
        "source_row_id": None,
        "clean_table": "core3_clean_sku",
        "clean_record_key": "sku:TV00029115",
        "sku_code": "TV00029115",
        "issue_type": Core3QualityIssueType.CLAIM_COVERAGE_MISSING,
        "severity": Core3QualityIssueSeverity.WARNING,
        "issue_detail": "结构化卖点缺失，不代表没有卖点",
        "issue_payload_json": {"claim": {"covered": False}},
        "suggested_downstream_action": "M04a 不得伪造卖点事实",
        "review_required": True,
        "review_status": Core3ReviewStatus.REVIEW_REQUIRED,
    }

    first = repo.save_issue(payload)
    second = repo.save_issue({**payload, "issue_detail": "不应重复写入"})
    issue_list = repo.list_quality_issues(
        BATCH_ID,
        sku_code="TV00029115",
        domain="claim",
        issue_type="claim_coverage_missing",
        severity="warning",
        review_required=True,
    )
    summary = CleaningQueryRepository(context).get_clean_summary(BATCH_ID)

    assert first.created is True
    assert second.created is False
    assert second.record.issue_id == first.record.issue_id
    assert len(issue_list) == 1
    assert summary["issue_counts"]["warning"] == 1
    assert summary["issue_counts"]["review_required"] == 1
    assert summary["issue_counts"]["by_type"] == {"claim_coverage_missing": 1}
