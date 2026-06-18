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
        create_core3_tables(connection)
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


def create_core3_tables(connection) -> None:
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
                id, model_code, category, brand, model, platform, url_id, comment_id,
                comment_time, comment_content, comments_segments, primary_dim,
                secondary_dim, third_dim, sentiment, write_time
            ) VALUES (
                3, 'TV00029115', '彩电', '海信', '85E7Q', '京东', 'u-3',
                'c-85e7q-001', '2026-06-10 09:00:00',
                '画质清晰，安装服务及时，体育比赛很流畅。',
                '画质清晰|安装服务及时|体育比赛流畅',
                '产品体验', '画质音效', '运动流畅', 'positive',
                '2026-06-11 12:00:00'
            )
            """
        )
    )
    session.flush()


def register_m00_batch(client: TestClient) -> str:
    response = client.post(
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
    assert response.status_code == 200
    return response.json()["summary_json"]["batch_id"]


def test_m01_cleaning_api_runs_and_queries_cleaning_outputs():
    session = make_session()
    client = make_client(session)
    batch_id = register_m00_batch(client)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/run",
        json={"module_run_id": "module-run-api"},
    )

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["module_code"] == "M01"
    assert run_payload["status"] == "warning"
    assert run_payload["input_count"] == 3
    assert run_payload["summary_json"]["clean_counts"]["sku"] == 1
    assert run_payload["summary_json"]["clean_counts"]["market"] == 1
    assert run_payload["summary_json"]["clean_counts"]["attribute"] == 1
    assert run_payload["summary_json"]["clean_counts"]["claim"] == 0
    assert run_payload["summary_json"]["clean_counts"]["comment"] == 1
    assert run_payload["summary_json"]["clean_counts"]["quality_issue"] == 1
    assert run_payload["warnings"] == ["claim_coverage_missing"]

    summary_response = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/summary"
    )
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["clean_counts"]["sku"] == 1
    assert summary_payload["issue_counts"]["warning"] == 1
    assert summary_payload["market_coverage_summary"]["sku_count"] == 1
    assert summary_payload["comment_preliminary_summary"]["raw_comment_count"] == 1
    assert summary_payload["review_required"] is True
    assert "需要业务或数据复核" in summary_payload["quality_summary_cn"]

    sku_response = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/skus",
        params={"sku_code": "TV00029115"},
    )
    assert sku_response.status_code == 200
    sku_payload = sku_response.json()
    assert sku_payload["total"] == 1
    clean_sku = sku_payload["items"][0]
    assert clean_sku["sku_code"] == "TV00029115"
    assert clean_sku["coverage"]["market"]["covered"] is True
    assert clean_sku["coverage"]["attribute"]["covered"] is True
    assert clean_sku["coverage"]["comment"]["covered"] is True
    assert clean_sku["coverage"]["claim"]["covered"] is False
    assert clean_sku["coverage"]["missing_signals"]["claim_structured"]["missing"] is True

    issue_response = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/quality-issues",
        params={
            "sku_code": "TV00029115",
            "domain": "claim",
            "issue_type": "claim_coverage_missing",
            "severity": "warning",
            "review_required": True,
        },
    )
    assert issue_response.status_code == 200
    issue_payload = issue_response.json()
    assert issue_payload["total"] == 1
    assert issue_payload["items"][0]["issue_detail"] == "结构化卖点数据缺失，不代表该 SKU 没有卖点"
    assert "需要业务或数据复核" in issue_payload["quality_summary_cn"]


def test_m01_cleaning_api_validates_missing_batch():
    session = make_session()
    client = make_client(session)

    run_response = client.post(
        "/api/mvp/core3/v2/projects/core3_mvp/batches/m00_missing/cleaning/run"
    )
    summary_response = client.get(
        "/api/mvp/core3/v2/projects/core3_mvp/batches/m00_missing/cleaning/summary"
    )

    assert run_response.status_code == 404
    assert summary_response.status_code == 404
