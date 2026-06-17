from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import core3_real_data
from app.core.database import get_db

from .test_m03_param_repositories_runner import BATCH_ID, PROJECT_ID, make_session, seed_m03_evidence


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(core3_real_data.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_m03_param_api_runs_and_queries_param_outputs():
    session = make_session()
    seed_m03_evidence(session)
    client = make_client(session)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/params/run",
        json={"module_run_id": "module-run-api"},
    )

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["module_code"] == "M03"
    assert run_payload["status"] == "warning"
    assert run_payload["summary_json"]["field_profile_count"] >= 4
    assert run_payload["summary_json"]["param_value_count"] >= 4
    assert run_payload["summary_json"]["sku_profile_count"] == 1
    assert run_payload["summary_json"]["alias_candidate_count"] == 1
    assert run_payload["summary_json"]["conflict_count"] >= 2

    matched_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/params/field-profiles",
        params={"matched": "true"},
    )
    assert matched_response.status_code == 200
    matched_payload = matched_response.json()
    assert matched_payload["total"] >= 3
    assert all(item["matched_param_code"] for item in matched_payload["items"])

    unmapped_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/params/field-profiles",
        params={"matched": "false", "review_required": "true"},
    )
    assert unmapped_response.status_code == 200
    unmapped_payload = unmapped_response.json()
    assert unmapped_payload["total"] == 1
    assert unmapped_payload["items"][0]["clean_param_name"] == "未知字段X"

    sku_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/skus/TV00029115/params",
        params={"batch_id": BATCH_ID},
    )
    assert sku_response.status_code == 200
    sku_payload = sku_response.json()
    assert sku_payload["profile"]["sku_code"] == "TV00029115"
    screen_size = sku_payload["profile"]["param_values_json"]["screen_size_inch"]
    assert screen_size["param_name"] == "屏幕尺寸"
    assert screen_size["normalized_value"] == {"value": 85, "unit": "inch"}
    assert screen_size["confidence"]
    assert screen_size["evidence_ids"] == ["ev_size"]
    assert any(value["param_code"] == "native_refresh_rate_hz" for value in sku_payload["values"])
    assert sku_payload["conflicts"]

    alias_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/params/alias-candidates",
        params={"review_status": "review_required"},
    )
    assert alias_response.status_code == 200
    alias_payload = alias_response.json()
    assert alias_payload["total"] == 1
    assert alias_payload["items"][0]["clean_param_name"] == "未知字段X"
    assert "需人工判断" in alias_payload["items"][0]["suggestion_reason"]

    conflicts_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/params/conflicts",
        params={"sku_code": "TV00029115", "review_required": "true"},
    )
    assert conflicts_response.status_code == 200
    conflicts_payload = conflicts_response.json()
    assert conflicts_payload["total"] >= 2
    conflict_types = {item["conflict_type"] for item in conflicts_payload["items"]}
    assert {"raw_param_vs_claim_conflict", "unit_uncertain"}.issubset(conflict_types)
    assert any(item["candidate_values_json"] for item in conflicts_payload["items"])
    assert any(item["preferred_value_json"] is not None for item in conflicts_payload["items"])
    assert all(item["review_status"] == "review_required" for item in conflicts_payload["items"])


def test_m03_param_api_returns_clear_error_when_m02_evidence_is_missing():
    session = make_session()
    client = make_client(session)

    response = client.post(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/params/run")

    assert response.status_code == 409
    assert "M02 evidence not ready" in response.json()["detail"]
