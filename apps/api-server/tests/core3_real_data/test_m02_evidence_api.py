from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import core3_real_data
from app.core.database import get_db

from .test_m02_evidence_runner import BATCH_ID, PROJECT_ID, make_session


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(core3_real_data.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_m02_evidence_api_runs_and_queries_trace_links_and_sku_evidence():
    session = make_session()
    client = make_client(session)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/evidence/run",
        json={"module_run_id": "module-run-api"},
    )

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["module_code"] == "M02"
    assert run_payload["status"] == "warning"
    assert run_payload["summary_json"]["evidence_counts"]["by_type"]["param_raw"] == 1
    assert run_payload["summary_json"]["evidence_counts"]["by_type"]["comment_raw"] == 1
    assert run_payload["summary_json"]["link_counts"]["has_sentence"] == 2
    assert "m02_low_confidence_evidence" in run_payload["warnings"]

    summary_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/evidence/summary"
    )
    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["evidence_counts"]["param_raw"] == 1
    assert summary_payload["evidence_counts"]["promo_raw"] == 1
    assert summary_payload["evidence_counts"]["comment_dimension"] == 1
    assert summary_payload["evidence_counts"]["link"] >= 4
    assert "core3_clean_attribute" in summary_payload["source_clean_tables"]
    assert "core3_clean_market_weekly" in summary_payload["missing_clean_tables"]
    assert summary_payload["review_required"] is True
    assert "需要复核" in summary_payload["quality_summary_cn"]

    sku_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/skus/TV00029115/evidence",
        params={
            "batch_id": BATCH_ID,
            "evidence_type": "param_raw",
            "min_confidence": "0.5",
        },
    )
    assert sku_response.status_code == 200
    sku_payload = sku_response.json()
    assert sku_payload["total"] == 1
    assert sku_payload["query"]["evidence_types"] == ["param_raw"]
    assert sku_payload["items"][0]["evidence_type"] == "param_raw"
    assert sku_payload["items"][0]["evidence_title"]
    assert any(link["link_type"] == "has_quality_issue" for link in sku_payload["links"])

    evidence_id = sku_payload["items"][0]["evidence_id"]
    trace_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/evidence/{evidence_id}")
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["evidence"]["evidence_payload_json"]["clean_attr_value"] == "144Hz"
    assert trace_payload["downstream_links"]
    assert trace_payload["related_evidence"]
    assert "可回溯" in trace_payload["trace_summary_cn"]

    links_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/evidence/{evidence_id}/links",
        params={"link_type": "has_quality_issue"},
    )
    assert links_response.status_code == 200
    assert [link["link_type"] for link in links_response.json()] == ["has_quality_issue"]


def test_m02_evidence_api_validates_missing_batch_unknown_evidence_and_bad_type():
    session = make_session()
    client = make_client(session)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/m00_missing/evidence/run"
    )
    summary_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/m00_missing/evidence/summary"
    )
    missing_evidence_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/evidence/evidence_missing"
    )
    bad_type_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/skus/TV00029115/evidence",
        params={"batch_id": BATCH_ID, "evidence_type": "task_code"},
    )

    assert run_response.status_code == 404
    assert summary_response.status_code == 404
    assert missing_evidence_response.status_code == 404
    assert bad_type_response.status_code == 400
