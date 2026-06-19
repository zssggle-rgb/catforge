from datetime import datetime, timezone

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.cleaning_runner import CleaningQualityRunner
from app.services.core3_real_data.constants import (
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3SourceBatchStatus,
    Core3SourceOperationType,
    Core3TargetScopeType,
)
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
RUN_ID = "run-m01-g"
MODULE_RUN_ID = "module-run-m01-g"


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    connection = engine.connect()
    with connection.begin():
        create_foundation_tables(connection)
        create_raw_source_tables(connection)
    session = Session(bind=connection)
    seed_m00_batch(session)
    seed_raw_rows(session)
    return session


def create_foundation_tables(connection) -> None:
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
        table.create(bind=connection, checkfirst=True)


def create_raw_source_tables(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE week_sales_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                date_value TEXT,
                channel TEXT,
                platform TEXT,
                sales_volume INTEGER,
                sales_amount NUMERIC,
                avg_price NUMERIC,
                write_time TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE attribute_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                attr_name TEXT,
                attr_value TEXT,
                write_time TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE selling_points_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                variable TEXT,
                selling_point TEXT,
                write_time TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE comment_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                platform TEXT,
                url_id TEXT,
                comment_id TEXT,
                comment_time TEXT,
                comment_content TEXT,
                comments_segments TEXT,
                primary_dim TEXT,
                secondary_dim TEXT,
                third_dim TEXT,
                sentiment TEXT,
                write_time TIMESTAMP
            )
            """
        )
    )


def seed_m00_batch(session: Session) -> None:
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
            module_code="M01",
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
    rows = [
        ("rr-market", "week_sales_data", "1", Core3SourceOperationType.INSERT.value, "TV00029115"),
        ("rr-attribute", "attribute_data", "2", Core3SourceOperationType.UPDATE.value, "TV00029115"),
        ("rr-claim", "selling_points_data", "3", Core3SourceOperationType.INSERT.value, "TV00029115"),
        ("rr-comment", "comment_data", "4", Core3SourceOperationType.INSERT.value, "TV00029115"),
        ("rr-no-change", "attribute_data", "5", Core3SourceOperationType.NO_CHANGE.value, "TV00029115"),
        ("rr-not-seen", "attribute_data", "999", Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN.value, "TV00029115"),
        ("rr-skipped", "comment_data", None, Core3SourceOperationType.SKIPPED.value, None),
    ]
    for row_registry_id, source_table, source_pk, operation_type, sku_code in rows:
        source_row_id = f"{source_table}:{source_pk}" if source_pk is not None else None
        session.add(
            entities.Core3SourceRowRegistry(
                row_registry_id=row_registry_id,
                batch_id=BATCH_ID,
                project_id=PROJECT_ID,
                category_code="TV",
                source_table=source_table,
                source_pk=source_pk,
                source_pk_strategy="id_column",
                source_row_id=source_row_id,
                row_hash=f"sha256:m00_row_hash_v1:{row_registry_id}",
                hash_version="m00_row_hash_v1",
                sku_code_candidate=sku_code,
                operation_type=operation_type,
                affected_modules=["M01"],
                quality_hint={},
                review_status="auto_pass",
            )
        )
    session.flush()


def seed_raw_rows(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO week_sales_data (
                id, model_code, category, brand, model, date_value, channel, platform,
                sales_volume, sales_amount, avg_price, write_time
            ) VALUES (
                1, 'TV00029115', '彩电', '海信', '85E7Q', '26W01', '线上',
                '专业电商', 10, 59990, 5999, '2026-06-11 10:00:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO attribute_data (
                id, model_code, category, brand, model, attr_name, attr_value, write_time
            ) VALUES
              (2, 'TV00029115', '彩电', '海信', '85E7Q', '背光分区', '504分区', '2026-06-11 11:00:00'),
              (5, 'TV00029115', '彩电', '海信', '85E7Q', '刷新率', '300Hz', '2026-06-11 11:05:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO selling_points_data (
                id, model_code, category, brand, model, variable, selling_point, write_time
            ) VALUES (
                3, 'TV00029115', '彩电', '海信', '85E7Q', '卖点1',
                '游戏低延迟，体育画面流畅', '2026-06-11 12:00:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO comment_data (
                id, model_code, category, brand, model, platform, url_id, comment_id,
                comment_time, comment_content, comments_segments, primary_dim,
                secondary_dim, third_dim, sentiment, write_time
            ) VALUES (
                4, 'TV00029115', '彩电', '海信', '85E7Q', '京东', 'u-4', 'c-4',
                '2026-06-10 09:00:00', '画质很好，游戏模式延迟低',
                '画质很好', '产品体验', '画质', NULL, '正面',
                '2026-06-11 13:00:00'
            )
            """
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


def test_cleaning_quality_runner_consumes_m00_scope_and_writes_clean_outputs():
    session = make_session()

    result = CleaningQualityRunner(session).run(make_context(), make_target())

    assert result.status == "warning"
    assert result.module_code == "M01"
    assert result.input_count == 6
    assert result.summary_json["clean_counts"]["sku"] == 1
    assert result.summary_json["clean_counts"]["market"] == 1
    assert result.summary_json["clean_counts"]["attribute"] == 1
    assert result.summary_json["clean_counts"]["claim"] == 1
    assert result.summary_json["clean_counts"]["claim_sentence"] >= 1
    assert result.summary_json["clean_counts"]["comment"] == 1
    assert result.summary_json["clean_counts"]["comment_sentence"] >= 1
    assert result.summary_json["clean_counts"]["comment_dimension"] == 1
    assert result.summary_json["clean_counts"]["quality_issue"] == 2
    assert result.summary_json["issue_counts"]["by_type"] == {"missing_required_field": 2}
    assert result.summary_json["market_coverage_summary"]["full_week_coverage_sku_count"] == 1
    assert result.summary_json["market_coverage_summary"]["sku_with_single_platform_week_count"] == 1
    assert result.summary_json["comment_preliminary_summary"]["raw_comment_count"] == 1
    assert result.summary_json["comment_preliminary_summary"]["low_value_comment_count"] == 0
    assert result.summary_json["comment_preliminary_summary"]["service_candidate_not_blocked"] is False
    assert result.summary_json["processed_chunk_count"] == 1
    assert result.summary_json["source_row_chunk_size"] == 1000
    assert result.summary_json["review_required"] is True
    assert result.downstream_impacts[0]["module_code"] == "M02"

    attributes = session.execute(select(entities.Core3CleanAttribute)).scalars().all()
    assert [attribute.source_row_id for attribute in attributes] == ["attribute_data:2"]
    clean_sku = session.execute(select(entities.Core3CleanSku)).scalar_one()
    assert clean_sku.coverage_json["claim"]["covered"] is True
    assert clean_sku.coverage_json["market"]["weekly_coverage"]["single_platform_is_normal"] is True
    assert clean_sku.missing_signals_json == {}


def test_cleaning_quality_runner_commits_source_rows_in_chunks():
    session = make_session()

    result = CleaningQualityRunner(session, source_row_chunk_size=2).run(make_context(), make_target())

    assert result.status == "warning"
    assert result.input_count == 6
    assert result.summary_json["processed_row_count"] == 6
    assert result.summary_json["processed_chunk_count"] == 3
    assert result.summary_json["source_row_chunk_size"] == 2
    assert result.summary_json["clean_counts"]["comment"] == 1
    assert session.execute(select(entities.Core3CleanSku)).scalar_one().sku_code == "TV00029115"


def test_cleaning_quality_runner_is_idempotent_for_same_batch_and_hashes():
    session = make_session()
    runner = CleaningQualityRunner(session)

    first = runner.run(make_context(), make_target())
    second = runner.run(make_context(), make_target())

    assert first.status == "warning"
    assert second.status == "warning"
    assert second.summary_json["clean_counts"] == first.summary_json["clean_counts"]
    assert session.execute(select(entities.Core3CleanSku)).scalars().all()[0].sku_code == "TV00029115"
    assert len(session.execute(select(entities.Core3CleanAttribute)).scalars().all()) == 1
    assert len(session.execute(select(entities.Core3DataQualityIssue)).scalars().all()) == 2


def test_cleaning_quality_runner_updates_existing_clean_fact_when_hash_changes():
    session = make_session()
    runner = CleaningQualityRunner(session)
    runner.run(make_context(), make_target())
    session.execute(text("UPDATE attribute_data SET attr_value = '512分区' WHERE id = 2"))

    result = runner.run(make_context(), make_target())
    clean_attribute = session.execute(select(entities.Core3CleanAttribute)).scalar_one()

    assert result.status == "warning"
    assert result.summary_json["clean_counts"]["attribute"] == 1
    assert clean_attribute.clean_attr_value == "512分区"


def test_cleaning_quality_runner_blocks_when_m00_batch_is_not_consumable():
    session = make_session()
    batch = session.execute(select(entities.Core3SourceBatch)).scalar_one()
    batch.status = Core3SourceBatchStatus.FAILED.value

    result = CleaningQualityRunner(session).run(make_context(), make_target())

    assert result.status == "blocked"
    assert result.summary_json["batch_id"] == BATCH_ID
    assert result.warnings == ["m00_batch_not_consumable"]
    assert not session.execute(select(entities.Core3CleanSku)).scalars().all()
