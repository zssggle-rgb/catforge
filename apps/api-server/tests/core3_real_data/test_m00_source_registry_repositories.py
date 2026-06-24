from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.services.core3_real_data.constants import Core3SourceBatchType
from app.services.core3_real_data.repositories import (
    Core3RepositoryContext,
    RawSourceMutationNotAllowed,
    RawSourceReadOnlyGuard,
)
from app.services.core3_real_data.source_registry_repositories import (
    RAW_SOURCE_BUSINESS_KEY_COLUMNS,
    RAW_SOURCE_HASH_COLUMNS,
    RawSourceRepository,
    SourceScanPlan,
    SourceSchemaInspector,
)


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    with engine.begin() as connection:
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
                INSERT INTO week_sales_data (
                    id, model_code, category, brand, model, date_value, channel, platform,
                    sales_volume, sales_amount, avg_price, write_time
                ) VALUES
                    (1, 'TV00029115', '彩电', '海信', '85E7Q', '26W01', '线上', '专业电商', 10, 59990, 5999, '2026-06-11 10:00:00'),
                    (2, 'TV00029115', '彩电', '海信', '85E7Q', '26W02', '线上', '平台电商', 12, 71988, 5999, '2026-06-12 10:00:00'),
                    (3, 'TV00010001', '彩电', '海信', '85Q6N', '26W01', '线上', '专业电商', 7, 41993, 5999, '2026-06-12 11:00:00'),
                    (4, 'AC00010001', '空调', '海信', 'KFR-35GW', '26W01', '线上', '专业电商', 5, 14995, 2999, '2026-06-12 12:00:00')
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
    return Session(engine)


def make_repo() -> RawSourceRepository:
    return RawSourceRepository(Core3RepositoryContext(db=make_session(), project_id="core3_mvp"))


def test_raw_source_repository_lists_configured_source_tables():
    repo = make_repo()
    configs = repo.list_source_tables()

    assert [config.source_table for config in configs] == [
        "week_sales_data",
        "attribute_data",
        "selling_points_data",
        "comment_data",
    ]
    assert configs[0].business_key_columns == ("date_value", "channel", "platform")
    assert RAW_SOURCE_BUSINESS_KEY_COLUMNS["attribute_data"] == ("attr_name", "attr_value")
    assert "comment_content" in RAW_SOURCE_HASH_COLUMNS["comment_data"]


def test_schema_inspector_returns_columns_and_stable_schema_hash():
    repo = make_repo()
    snapshot = repo.inspect_table("week_sales_data")
    inspector_snapshot = SourceSchemaInspector(repo.context).inspect_table("week_sales_data")

    column_names = [column.name for column in snapshot.columns]
    assert "model_code" in column_names
    assert "write_time" in column_names
    assert snapshot.schema_hash.startswith("sha256:m00_schema_v1:")
    assert inspector_snapshot.schema_hash == snapshot.schema_hash
    assert snapshot.to_json()["columns"][0]["name"] == "id"

    with pytest.raises(ValueError, match="raw source table not found"):
        repo.inspect_table("comment_data")


def test_raw_source_repository_gets_table_watermark_without_mutating_raw_table():
    repo = make_repo()
    watermark = repo.get_table_watermark("week_sales_data")

    assert watermark.source_table == "week_sales_data"
    assert watermark.row_count == 3
    assert watermark.min_source_pk == "1"
    assert watermark.max_source_pk == "3"
    assert watermark.distinct_sku_count == 2
    assert watermark.min_write_time is not None
    assert watermark.max_write_time is not None


def test_raw_source_repository_iterates_rows_with_scan_plan():
    repo = make_repo()
    scan_plan = SourceScanPlan(
        source_table="week_sales_data",
        batch_type=Core3SourceBatchType.FULL,
        min_source_pk="2",
        limit=1,
    )

    rows = list(repo.iter_rows("week_sales_data", scan_plan))

    assert len(rows) == 1
    assert rows[0]["id"] == 2
    assert rows[0]["model_code"] == "TV00029115"
    assert rows[0]["platform"] == "平台电商"


def test_raw_source_repository_iterates_incremental_rows_by_write_time():
    repo = make_repo()
    scan_plan = SourceScanPlan(
        source_table="week_sales_data",
        batch_type=Core3SourceBatchType.INCREMENTAL,
        min_write_time_exclusive=datetime(2026, 6, 12, 10, 30, tzinfo=timezone.utc),
    )

    rows = list(repo.iter_rows("week_sales_data", scan_plan))

    assert [row["id"] for row in rows] == [3]


def test_raw_source_repository_filters_raw_rows_by_category_code():
    repo = make_repo()
    full_rows = list(repo.iter_rows("week_sales_data", SourceScanPlan(source_table="week_sales_data")))
    watermark = repo.get_table_watermark("week_sales_data")

    assert [row["id"] for row in full_rows] == [1, 2, 3]
    assert watermark.row_count == 3
    assert watermark.max_source_pk == "3"
    assert watermark.distinct_sku_count == 2


def test_raw_source_repository_can_filter_ac_raw_rows_by_category_code():
    session = make_session()
    repo = RawSourceRepository(Core3RepositoryContext(db=session, project_id="core3_mvp", category_code="AC"))

    full_rows = list(repo.iter_rows("week_sales_data", SourceScanPlan(source_table="week_sales_data")))
    watermark = repo.get_table_watermark("week_sales_data")

    assert [row["id"] for row in full_rows] == [4]
    assert watermark.row_count == 1
    assert watermark.max_source_pk == "4"
    assert watermark.distinct_sku_count == 1


def test_raw_source_repository_gets_row_by_source_reference():
    repo = make_repo()

    row = repo.get_row_by_source_ref("week_sales_data", "1")

    assert row is not None
    assert row["model"] == "85E7Q"
    assert repo.get_row_by_source_ref("week_sales_data", "999") is None


def test_raw_source_repository_rejects_unknown_table_and_mismatched_scan_plan():
    repo = make_repo()

    with pytest.raises(ValueError, match="unknown raw source table"):
        repo.get_table_watermark("raw_sku_master")

    with pytest.raises(ValueError, match="does not match"):
        list(
            repo.iter_rows(
                "week_sales_data",
                SourceScanPlan(source_table="attribute_data"),
            )
        )


def test_raw_source_repository_public_interface_stays_read_only():
    repo = make_repo()

    RawSourceReadOnlyGuard.assert_repository_interface_read_only(repo)

    with pytest.raises(RawSourceMutationNotAllowed):
        RawSourceReadOnlyGuard.ensure_select_method("update_raw")
