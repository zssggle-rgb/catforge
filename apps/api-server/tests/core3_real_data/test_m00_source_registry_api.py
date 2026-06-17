from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import core3_real_data
from app.core.database import get_db
from app.models import entities


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
    session = Session(bind=connection)
    seed_85e7q_fixture(session)
    return session


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(core3_real_data.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


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


def seed_85e7q_fixture(session: Session) -> None:
    session.execute(
        text(
            """
            INSERT INTO week_sales_data (
                id, model_code, category, brand, model, date_value, channel, platform,
                sales_volume, sales_amount, avg_price, write_time
            ) VALUES (
                1, 'TV00029115', '彩电', '海信', '85E7Q', '26W01', '线上',
                '专业电商', 46, 275954, 5999, '2026-06-11 10:00:00'
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
    session.execute(
        text(
            """
            INSERT INTO comment_data (
                id, model_code, category, brand, model, comment_id, comment_content,
                comments_segments, primary_dim, secondary_dim, third_dim, sentiment, write_time
            ) VALUES (
                3, 'TV00029115', '彩电', '海信', '85E7Q', 'c-85e7q-001',
                '画质清晰，安装服务及时，体育比赛很流畅。',
                '画质清晰|安装服务及时|体育比赛流畅',
                '产品体验', '画质音效', '运动流畅', 'positive',
                '2026-06-11 12:00:00'
            )
            """
        )
    )
    session.flush()


def test_m00_source_registry_api_registers_and_queries_85e7q_fixture():
    session = make_session()
    client = make_client(session)

    register_response = client.post(
        "/api/mvp/core3/v2/projects/core3_mvp/source-batches/register",
        json={
            "batch_type": "full",
            "source_tables": [
                "week_sales_data",
                "attribute_data",
                "selling_points_data",
                "comment_data",
            ],
        },
    )

    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["status"] == "warning"
    assert register_payload["input_count"] == 3
    assert register_payload["changed_input_count"] == 3
    assert register_payload["summary_json"]["impacted_sku_count"] == 1
    assert register_payload["warnings"] == ["selling_points_sparse_coverage"]

    batch_id = register_payload["summary_json"]["batch_id"]
    batch_response = client.get(f"/api/mvp/core3/v2/projects/core3_mvp/source-batches/{batch_id}")
    assert batch_response.status_code == 200
    batch_payload = batch_response.json()
    assert batch_payload["status"] == "registered_with_warning"
    assert batch_payload["impacted_sku_count"] == 1
    assert batch_payload["row_counts_json"]["selling_points_data"]["scanned"] == 0
    assert batch_payload["quality_summary_json"]["code_counts"] == {
        "selling_points_sparse_coverage": 1
    }

    row_response = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/source-batches/{batch_id}/rows",
        params={"sku_code_candidate": "TV00029115", "limit": 10},
    )
    assert row_response.status_code == 200
    row_payload = row_response.json()
    assert row_payload["total"] == 3
    assert {item["source_table"] for item in row_payload["items"]} == {
        "week_sales_data",
        "attribute_data",
        "comment_data",
    }

    selling_point_rows = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/source-batches/{batch_id}/rows",
        params={"source_table": "selling_points_data"},
    ).json()
    assert selling_point_rows["total"] == 0

    impacted_response = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/source-batches/{batch_id}/impacted-skus"
    )
    assert impacted_response.status_code == 200
    impacted_payload = impacted_response.json()
    assert impacted_payload["total"] == 1
    impacted_sku = impacted_payload["items"][0]
    assert impacted_sku["sku_code_candidate"] == "TV00029115"
    assert impacted_sku["model_name_raw"] == "85E7Q"
    assert impacted_sku["source_tables"] == [
        "attribute_data",
        "comment_data",
        "week_sales_data",
    ]
    assert "selling_points_data" not in impacted_sku["source_tables"]
    for module_code in ["M03", "M05", "M06", "M07"]:
        assert module_code in impacted_sku["affected_modules"]


def test_m00_source_registry_api_validates_request_and_missing_batch():
    session = make_session()
    client = make_client(session)

    invalid_register = client.post(
        "/api/mvp/core3/v2/projects/core3_mvp/source-batches/register",
        json={"batch_type": "bad", "source_tables": ["week_sales_data"]},
    )
    assert invalid_register.status_code == 422

    missing_batch = client.get("/api/mvp/core3/v2/projects/core3_mvp/source-batches/m00_missing")
    assert missing_batch.status_code == 404
    assert missing_batch.json()["detail"] == "source batch not found"

    bad_source_table = client.get(
        "/api/mvp/core3/v2/projects/core3_mvp/source-batches/m00_missing/rows",
        params={"source_table": "raw_sku_master"},
    )
    assert bad_source_table.status_code == 404
