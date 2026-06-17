from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import core3_real_data
from app.core.database import get_db

from .test_m05_comment_evidence_runner import BATCH_ID, PROJECT_ID, SKU_CODE, make_session, seed_comment_evidence


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(core3_real_data.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_m05_comment_api_runs_and_queries_comment_evidence_outputs():
    session = make_session()
    seed_comment_evidence(session)
    client = make_client(session)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/comments/run",
        json={"module_run_id": "module-run-api", "sku_scope": [SKU_CODE]},
    )

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["module_code"] == "M05"
    assert run_payload["status"] == "warning"
    assert run_payload["summary_json"]["comment_unit_count"] == 1
    assert run_payload["summary_json"]["evidence_atom_count"] == 1
    assert run_payload["summary_json"]["topic_hint_count"] >= 1

    profiles_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/comments/profiles",
        params={"sku_code": SKU_CODE},
    )
    assert profiles_response.status_code == 200
    profiles_payload = profiles_response.json()
    assert profiles_payload["total"] == 1
    assert profiles_payload["items"][0]["sku_code"] == SKU_CODE
    assert profiles_payload["items"][0]["downstream_ready"] is True
    assert "评论质量画像" in profiles_payload["summary_cn"]

    sku_profile_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/skus/{SKU_CODE}/comments/profile",
        params={"batch_id": BATCH_ID},
    )
    assert sku_profile_response.status_code == 200
    sku_profile_payload = sku_profile_response.json()
    assert sku_profile_payload["sku_code"] == SKU_CODE
    assert sku_profile_payload["comment_unit_count"] == 1
    assert "句级证据" in sku_profile_payload["quality_summary_cn"]

    units_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/comments/units",
        params={"sku_code": SKU_CODE},
    )
    assert units_response.status_code == 200
    units_payload = units_response.json()
    assert units_payload["total"] == 1
    assert units_payload["items"][0]["source_evidence_count"] == 3
    assert "去重评论单元" in units_payload["summary_cn"]

    atoms_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/comments/atoms",
        params={"sku_code": SKU_CODE, "usable_for_downstream": "true"},
    )
    assert atoms_response.status_code == 200
    atoms_payload = atoms_response.json()
    assert atoms_payload["total"] == 1
    assert atoms_payload["items"][0]["source_evidence_count"] == 3
    assert atoms_payload["items"][0]["primary_domain_hint"] == "product_experience"
    assert atoms_payload["items"][0]["primary_domain_hint_label_cn"] == "产品体验"
    assert atoms_payload["items"][0]["sentiment_hint"] == "positive"
    assert "后续评论信号" in atoms_payload["summary_cn"]

    topics_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/comments/topics",
        params={"sku_code": SKU_CODE, "topic_code": "TOPIC_GAMING_SMOOTHNESS"},
    )
    assert topics_response.status_code == 200
    topics_payload = topics_response.json()
    assert topics_payload["total"] >= 1
    assert topics_payload["items"][0]["topic_code"] == "TOPIC_GAMING_SMOOTHNESS"
    assert topics_payload["items"][0]["is_weak_hint"] is True
    assert "评论主题弱提示" in topics_payload["summary_cn"]


def test_m05_comment_api_returns_clear_error_when_comment_evidence_is_missing():
    session = make_session()
    client = make_client(session)

    response = client.post(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/comments/run")

    assert response.status_code == 409
    assert "M05 inputs not ready" in response.json()["detail"]
