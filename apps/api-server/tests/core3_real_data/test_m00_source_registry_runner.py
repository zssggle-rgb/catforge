from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3SourceBatchRegisterRequest, Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    CORE3_RAW_SOURCE_TABLES,
    Core3ModuleCode,
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3SourceBatchStatus,
    Core3SourceBatchType,
    Core3TargetScopeType,
)
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget
from app.services.core3_real_data.source_registry_service import SourceRegistryRunner


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    connection = engine.connect()
    with connection.begin():
        create_m00_tables(connection)
        create_raw_source_tables(connection)
    return Session(bind=connection)


def create_m00_tables(connection) -> None:
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3SourceRowRegistry.__table__,
        entities.Core3SourceImpactedSku.__table__,
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
                comment_id TEXT,
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


def seed_valid_rows(session: Session) -> None:
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
            ) VALUES (
                2, 'TV00029115', '彩电', '海信', '85E7Q', '背光分区',
                '504分区', '2026-06-11 11:00:00'
            )
            """
        )
    )
    session.flush()


def seed_quality_warning_row(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO week_sales_data (
                id, model_code, category, brand, model, date_value, channel, platform,
                sales_volume, sales_amount, avg_price, write_time
            ) VALUES (
                9, '', '彩电', '海信', '85E7Q', '26W01', '线上',
                '专业电商', 10, 59990, 5999, NULL
            )
            """
        )
    )
    session.flush()


def seed_comment_rows(session: Session, *, row_count: int) -> None:
    for row_id in range(1, row_count + 1):
        session.execute(
            text(
                """
                INSERT INTO comment_data (
                    id, model_code, category, brand, model, comment_id, comment_content,
                    comments_segments, primary_dim, secondary_dim, third_dim, sentiment, write_time
                ) VALUES (
                    :row_id, 'TV00029115', '彩电', '海信', '85E7Q', :comment_id, '画质很好',
                    '画质很好', '画质', '清晰度', NULL, '正向', '2026-06-11 12:00:00'
                )
                """
            ),
            {"row_id": row_id, "comment_id": f"c{row_id}"},
        )
    session.flush()


def test_source_registry_runner_full_registers_batch_and_rows():
    session = make_session()
    seed_valid_rows(session)

    result = SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            source_tables=["week_sales_data", "attribute_data"],
        )
    )

    assert result.status == "success"
    assert result.module_code == Core3ModuleCode.M00.value
    assert result.input_count == 2
    assert result.changed_input_count == 2
    assert result.output_count == 2
    assert result.summary_json["batch_status"] == Core3SourceBatchStatus.REGISTERED.value
    assert result.summary_json["impacted_sku_count"] == 1
    assert result.summary_json["impacted_sku_aggregation_deferred"] is False

    batch = session.execute(select(entities.Core3SourceBatch)).scalar_one()
    assert batch.batch_id == result.summary_json["batch_id"]
    assert batch.status == Core3SourceBatchStatus.REGISTERED.value
    assert batch.source_tables == ["week_sales_data", "attribute_data"]
    assert batch.impacted_sku_count == 1
    assert batch.row_counts_json["week_sales_data"] == {
        "scanned": 1,
        "registered": 1,
        "insert": 1,
        "update": 0,
        "no_change": 0,
        "not_seen_in_current_scan": 0,
        "skipped": 0,
    }
    assert batch.input_watermark_json["week_sales_data"]["candidate_rule"] == "full_table_scan"
    assert batch.schema_snapshot_json["attribute_data"]["schema_hash"].startswith("sha256:m00_schema_v1:")
    assert batch.source_pk_range_json["attribute_data"] == {"min_source_pk": "2", "max_source_pk": "2"}
    assert batch.quality_summary_json == {
        "status": "ok",
        "warnings": [],
        "review_required": False,
        "code_counts": {},
    }

    rows = session.execute(
        select(entities.Core3SourceRowRegistry).order_by(entities.Core3SourceRowRegistry.source_table)
    ).scalars().all()
    assert len(rows) == 2
    rows_by_table = {row.source_table: row for row in rows}

    week_row = rows_by_table["week_sales_data"]
    assert week_row.source_pk == "1"
    assert week_row.source_row_id == "week_sales_data:1"
    assert week_row.operation_type == "insert"
    assert week_row.row_hash.startswith("sha256:m00_row_hash_v1:")
    assert week_row.business_key_json == {
        "date_value": "26W01",
        "channel": "线上",
        "platform": "专业电商",
    }
    assert any(module["module_code"] == "M07" for module in week_row.affected_modules)

    attribute_row = rows_by_table["attribute_data"]
    assert attribute_row.source_pk == "2"
    assert attribute_row.business_key_json == {"attr_name": "背光分区", "attr_value": "504分区"}
    assert any(module["module_code"] == "M03" for module in attribute_row.affected_modules)

    impacted_sku = session.execute(select(entities.Core3SourceImpactedSku)).scalar_one()
    assert impacted_sku.sku_code_candidate == "TV00029115"
    assert impacted_sku.model_name_raw == "85E7Q"
    assert impacted_sku.source_tables == ["attribute_data", "week_sales_data"]
    assert impacted_sku.operation_summary_json["total_changed_rows"] == 2
    assert impacted_sku.operation_summary_json["by_source_table"]["attribute_data"]["insert"] == 1
    assert impacted_sku.operation_summary_json["by_source_table"]["week_sales_data"]["insert"] == 1
    assert "M03" in impacted_sku.affected_modules
    assert "M07" in impacted_sku.affected_modules


def test_source_registry_runner_marks_quality_warning_batch_for_review():
    session = make_session()
    seed_quality_warning_row(session)

    result = SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            source_tables=["week_sales_data"],
        )
    )

    assert result.status == "warning"
    assert result.input_count == 1
    assert result.output_count == 1
    assert result.warnings == ["missing_sku_code_candidate", "missing_write_time"]
    assert result.summary_json["batch_status"] == Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value

    batch = session.execute(select(entities.Core3SourceBatch)).scalar_one()
    assert batch.status == Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value
    assert batch.review_required is True
    assert batch.review_status == "review_required"
    assert batch.quality_summary_json["status"] == "review"
    assert batch.quality_summary_json["code_counts"] == {
        "missing_sku_code_candidate": 1,
        "missing_write_time": 1,
    }

    row = session.execute(select(entities.Core3SourceRowRegistry)).scalar_one()
    assert row.review_required is True
    assert row.review_status == "review_required"
    assert row.quality_hint == {
        "status": "review",
        "codes": ["missing_sku_code_candidate", "missing_write_time"],
    }
    assert row.source_field_presence_json["model_code"] == "empty_string"
    assert row.source_field_presence_json["write_time"] == "null"


def test_source_registry_runner_full_scan_commits_in_chunks_and_records_progress():
    session = make_session()
    seed_comment_rows(session, row_count=5)

    result = SourceRegistryRunner(session, row_chunk_size=2).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            source_tables=["comment_data"],
        )
    )

    assert result.status == "success"
    assert result.input_count == 5
    assert result.output_count == 5
    assert result.summary_json["processed_chunk_count"] == 3
    assert result.summary_json["row_chunk_size"] == 2

    batch = session.execute(
        select(entities.Core3SourceBatch).where(
            entities.Core3SourceBatch.batch_id == result.summary_json["batch_id"]
        )
    ).scalar_one()
    assert batch.input_watermark_json["comment_data"]["processed_chunk_count"] == 3
    assert batch.input_watermark_json["comment_data"]["row_chunk_size"] == 2
    assert batch.row_counts_json["comment_data"]["insert"] == 5


def test_source_registry_runner_incremental_without_history_falls_back_to_full():
    session = make_session()
    seed_valid_rows(session)

    result = SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            batch_type=Core3SourceBatchType.INCREMENTAL,
            source_tables=["week_sales_data"],
        )
    )

    assert result.status == "success"
    assert result.summary_json["requested_batch_type"] == Core3SourceBatchType.INCREMENTAL.value
    assert result.summary_json["effective_batch_type"] == Core3SourceBatchType.FULL.value

    batch = session.execute(select(entities.Core3SourceBatch)).scalar_one()
    assert batch.batch_type == Core3SourceBatchType.FULL.value
    watermark = batch.input_watermark_json["week_sales_data"]
    assert watermark["requested_batch_type"] == Core3SourceBatchType.INCREMENTAL.value
    assert watermark["scan_mode"] == Core3SourceBatchType.FULL.value
    assert watermark["fallback_reason"] == "no_previous_success_batch"
    assert batch.row_counts_json["week_sales_data"]["insert"] == 1
    assert batch.impacted_sku_count == 1


def test_source_registry_runner_incremental_uses_previous_watermark_and_writes_impacted_sku():
    session = make_session()
    seed_valid_rows(session)
    first = SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            source_tables=["week_sales_data"],
        )
    )
    session.execute(
        text(
            """
            UPDATE week_sales_data
            SET sales_volume = 12, sales_amount = 71988, write_time = '2026-06-12 12:00:00'
            WHERE id = 1
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO week_sales_data (
                id, model_code, category, brand, model, date_value, channel, platform,
                sales_volume, sales_amount, avg_price, write_time
            ) VALUES (
                3, 'TV00029115', '彩电', '海信', '85E7Q', '26W02', '线上',
                '平台电商', 9, 53991, 5999, '2026-06-12 13:00:00'
            )
            """
        )
    )
    session.flush()

    second = SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            batch_type=Core3SourceBatchType.INCREMENTAL,
            source_tables=["week_sales_data"],
        )
    )

    assert second.status == "success"
    assert second.input_count == 2
    assert second.changed_input_count == 2
    assert second.summary_json["effective_batch_type"] == Core3SourceBatchType.INCREMENTAL.value
    assert second.summary_json["impacted_sku_count"] == 1

    batch = session.execute(
        select(entities.Core3SourceBatch).where(
            entities.Core3SourceBatch.batch_id == second.summary_json["batch_id"]
        )
    ).scalar_one()
    watermark = batch.input_watermark_json["week_sales_data"]
    assert watermark["previous_success_batch_id"] == first.summary_json["batch_id"]
    assert watermark["previous_max_id"] == "1"
    assert watermark["candidate_rule"] == "incremental_id_watermark_and_existing_write_time"
    assert batch.row_counts_json["week_sales_data"]["update"] == 1
    assert batch.row_counts_json["week_sales_data"]["insert"] == 1
    assert batch.row_counts_json["week_sales_data"]["no_change"] == 0

    impacted_sku = session.execute(
        select(entities.Core3SourceImpactedSku).where(
            entities.Core3SourceImpactedSku.batch_id == second.summary_json["batch_id"]
        )
    ).scalar_one()
    assert impacted_sku.operation_summary_json["total_changed_rows"] == 2
    assert impacted_sku.operation_summary_json["by_source_table"]["week_sales_data"]["update"] == 1
    assert impacted_sku.operation_summary_json["by_source_table"]["week_sales_data"]["insert"] == 1


def test_source_registry_runner_incremental_without_candidates_does_not_create_impacted_sku():
    session = make_session()
    seed_valid_rows(session)
    SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            source_tables=["week_sales_data"],
        )
    )

    result = SourceRegistryRunner(session).register_batch(
        Core3SourceBatchRegisterRequest(
            project_id="core3_mvp",
            batch_type=Core3SourceBatchType.INCREMENTAL,
            source_tables=["week_sales_data"],
        )
    )

    assert result.status == "success"
    assert result.input_count == 0
    assert result.changed_input_count == 0
    assert result.summary_json["impacted_sku_count"] == 0

    batch = session.execute(
        select(entities.Core3SourceBatch).where(
            entities.Core3SourceBatch.batch_id == result.summary_json["batch_id"]
        )
    ).scalar_one()
    assert batch.row_counts_json["week_sales_data"]["registered"] == 0
    assert batch.row_counts_json["week_sales_data"]["no_change"] == 0
    impacted_sku_count = session.execute(
        select(func.count()).select_from(entities.Core3SourceImpactedSku).where(
            entities.Core3SourceImpactedSku.batch_id == result.summary_json["batch_id"]
        )
    ).scalar_one()
    assert impacted_sku_count == 0


def test_source_registry_runner_protocol_defaults_to_all_raw_tables():
    session = make_session()
    seed_valid_rows(session)
    context = build_run_context(
        run_id="run_m00_e",
        project_id="core3_mvp",
        run_mode=Core3RunMode.BOOTSTRAP_FULL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.ALL_SKU),
        module_versions={Core3ModuleCode.M00.value: "m00-test"},
    )
    target = Core3ModuleTarget(scope=Core3ModuleTargetScope.BATCH)

    result = SourceRegistryRunner(session).run(context, target)

    assert result.status == "warning"
    assert result.input_count == 2
    assert result.summary_json["source_tables"] == list(CORE3_RAW_SOURCE_TABLES)
    assert result.summary_json["impacted_sku_count"] == 1
    assert result.warnings == ["selling_points_sparse_coverage"]

    batch = session.execute(select(entities.Core3SourceBatch)).scalar_one()
    assert batch.run_id == "run_m00_e"
    assert batch.module_version == "m00-test"
    assert batch.status == Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value
    assert batch.review_required is False
    assert batch.quality_summary_json["code_counts"] == {"selling_points_sparse_coverage": 1}
    assert batch.row_counts_json["selling_points_data"]["scanned"] == 0
    assert batch.row_counts_json["comment_data"]["registered"] == 0
