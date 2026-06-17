from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import core3_real_data
from app.core.database import get_db
from app.models import entities
from app.services.core3_real_data.constants import CORE3_TARGET_SKU_85E7Q
from app.services.core3_real_data.fixtures import load_85e7q_fixture_set


FORBIDDEN_M01_BUSINESS_FIELDS = {
    "evidence_id",
    "evidence_ids",
    "param_code",
    "claim_code",
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "business_conclusion",
    "business_conclusion_cn",
    "score",
    "rank",
    "role",
    "report_payload",
    "evidence_card",
}


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
    seed_raw_tables_from_85e7q_fixture(session)
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


def seed_raw_tables_from_85e7q_fixture(session: Session) -> None:
    fixture = load_85e7q_fixture_set()
    for row in fixture.week_sales_data:
        session.execute(
            text(
                """
                INSERT INTO week_sales_data (
                    id, model_code, category, brand, model, date_value, channel, platform,
                    sales_volume, sales_amount, avg_price, write_time
                ) VALUES (
                    :id, :model_code, '彩电', :brand, :model_name, :week, :channel,
                    :platform_type, :sales_volume, :sales_amount, :average_price,
                    '2026-06-11 10:00:00'
                )
                """
            ),
            row,
        )
    for row in fixture.attribute_data:
        session.execute(
            text(
                """
                INSERT INTO attribute_data (
                    id, model_code, category, brand, model, attr_name, attr_value, write_time
                ) VALUES (
                    :id, :model_code, '彩电', :brand, :model_name, :attribute_name,
                    :attr_value, '2026-06-11 11:00:00'
                )
                """
            ),
            {**row, "attr_value": _attribute_value(row)},
        )
    for index, row in enumerate(fixture.selling_points_data, start=1):
        session.execute(
            text(
                """
                INSERT INTO selling_points_data (
                    id, model_code, category, brand, model, variable, selling_point, write_time
                ) VALUES (
                    :id, :model_code, '彩电', :brand, :model_name, :variable,
                    :selling_point, '2026-06-11 12:00:00'
                )
                """
            ),
            {**row, "variable": f"卖点{index}"},
        )
    for row in fixture.comment_data:
        session.execute(
            text(
                """
                INSERT INTO comment_data (
                    id, model_code, category, brand, model, platform, url_id, comment_id,
                    comment_time, comment_content, comments_segments, primary_dim,
                    secondary_dim, third_dim, sentiment, write_time
                ) VALUES (
                    :id, :model_code, '彩电', :brand, :model_name, '京东', NULL,
                    :comment_id, :write_time, :comment_text, :comments_segments,
                    :comment_dimension, NULL, NULL, :sentiment, :write_time
                )
                """
            ),
            {**row, "comment_text": row.get("comments_segments")},
        )
    session.flush()


def test_m01_fixture_acceptance_keeps_cleaning_boundary_for_85e7q():
    session = make_session()
    client = make_client(session)
    batch_id = register_m00_batch(client)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/run",
        json={"target_sku_codes": [CORE3_TARGET_SKU_85E7Q], "module_run_id": "module-run-m01-i"},
    )

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["status"] == "warning"
    assert run_payload["summary_json"]["clean_counts"] == {
        "sku": 1,
        "market": 2,
        "attribute": 6,
        "claim": 0,
        "claim_sentence": 0,
        "comment": 4,
        "comment_sentence": 8,
        "comment_dimension": 4,
        "quality_issue": 7,
    }
    assert run_payload["summary_json"]["issue_counts"]["by_type"] == {
        "claim_coverage_missing": 1,
        "duplicate_comment_text": 2,
        "unknown_value": 4,
    }
    assert_no_business_fields(run_payload)

    sku_payload = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/skus",
        params={"sku_code": CORE3_TARGET_SKU_85E7Q},
    ).json()["items"][0]
    assert sku_payload["coverage"]["market"] == {"row_count": 2, "covered": True}
    assert sku_payload["coverage"]["attribute"] == {
        "row_count": 6,
        "covered": True,
        "unknown_count": 4,
    }
    assert sku_payload["coverage"]["claim"] == {"row_count": 0, "covered": False}
    assert sku_payload["coverage"]["comment"] == {
        "row_count": 4,
        "covered": True,
        "distinct_comment_id_count": 3,
    }
    missing_claim = sku_payload["coverage"]["missing_signals"]["claim_structured"]
    assert missing_claim == {
        "missing": True,
        "reason": "本批 selling_points_data 未覆盖该 SKU",
        "business_interpretation": "结构化卖点数据缺失，不代表该 SKU 没有卖点",
    }
    assert_no_business_fields(sku_payload)

    claim_issue = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/quality-issues",
        params={"sku_code": CORE3_TARGET_SKU_85E7Q, "issue_type": "claim_coverage_missing"},
    ).json()
    unknown_issues = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/quality-issues",
        params={"sku_code": CORE3_TARGET_SKU_85E7Q, "issue_type": "unknown_value"},
    ).json()
    duplicate_issues = client.get(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/quality-issues",
        params={"sku_code": CORE3_TARGET_SKU_85E7Q, "issue_type": "duplicate_comment_text"},
    ).json()

    assert claim_issue["total"] == 1
    assert claim_issue["items"][0]["issue_detail"] == "结构化卖点数据缺失，不代表该 SKU 没有卖点"
    assert unknown_issues["total"] == 4
    assert {item["issue_payload_json"]["value_presence"] for item in unknown_issues["items"]} == {
        "unknown_literal",
        "empty",
        "dash",
        "null",
    }
    assert duplicate_issues["total"] == 2
    assert_no_business_fields(claim_issue)
    assert_no_business_fields(unknown_issues)
    assert_no_business_fields(duplicate_issues)


def test_m01_api_payloads_do_not_expose_business_conclusion_fields():
    session = make_session()
    client = make_client(session)
    batch_id = register_m00_batch(client)
    client.post(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/run",
        json={"target_sku_codes": [CORE3_TARGET_SKU_85E7Q]},
    )

    payloads = [
        client.get(f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/summary").json(),
        client.get(f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/skus").json(),
        client.get(f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/quality-issues").json(),
    ]

    for payload in payloads:
        assert_no_business_fields(payload)


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


def assert_no_business_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        assert FORBIDDEN_M01_BUSINESS_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_business_fields(item)


def _attribute_value(row: dict[str, Any]) -> Any:
    value = row.get("attribute_value")
    unit = row.get("unit")
    if value in (None, "", "-", "unknown") or not unit:
        return value
    return f"{value}{unit}"
