from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import core3_real_data
from app.core.database import get_db
from app.services.core3_real_data.param_extraction_runner import ParamExtractionRunner

from .test_m04a_claim_repositories_runner import (
    BATCH_ID,
    MODULE_RUN_ID_M03,
    PROJECT_ID,
    SKU_CODE,
    make_run_context,
    make_session,
    make_target,
    seed_m04a_evidence,
)


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(core3_real_data.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_m04a_claim_api_runs_and_queries_base_claim_outputs():
    session = make_session()
    seed_m04a_evidence(session)
    ParamExtractionRunner(session).run(make_run_context(), make_target(MODULE_RUN_ID_M03))
    client = make_client(session)

    run_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/claims/base/run",
        json={"module_run_id": "module-run-api"},
    )

    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["module_code"] == "M04a"
    assert run_payload["status"] == "warning"
    assert run_payload["summary_json"]["source_status_count"] == 1
    assert run_payload["summary_json"]["activation_base_count"] >= 20
    assert run_payload["summary_json"]["claim_hit_count"] >= 3

    status_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/claims/source-status",
        params={"sku_code": SKU_CODE},
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["total"] == 1
    assert status_payload["items"][0]["claim_source_status"] == "has_structured_claim"
    assert "可用结构化宣传卖点" in status_payload["items"][0]["status_note"]

    sku_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/skus/{SKU_CODE}/claims/base",
        params={"batch_id": BATCH_ID},
    )
    assert sku_response.status_code == 200
    sku_payload = sku_response.json()
    assert sku_payload["sku_code"] == SKU_CODE
    assert sku_payload["source_status"]["claim_source_status"] == "has_structured_claim"
    assert sku_payload["total_base_claim_count"] >= 20
    assert "基础卖点" in sku_payload["summary_cn"]
    mini_led = next(item for item in sku_payload["base_claims"] if item["claim_code"] == "CLAIM_MINI_LED_BACKLIGHT")
    assert mini_led["claim_name"]
    assert mini_led["activation_basis"] == "param_and_promo"
    assert {"ev_miniled", "ev_promo_game"}.issubset(set(mini_led["evidence_ids"]))

    hits_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/claims/hits",
        params={
            "sku_code": SKU_CODE,
            "claim_code": "CLAIM_MINI_LED_BACKLIGHT",
            "hit_source_type": "promo_sentence",
        },
    )
    assert hits_response.status_code == 200
    hits_payload = hits_response.json()
    assert hits_payload["total"] >= 1
    assert all(item["hit_source_type"] == "promo_sentence" for item in hits_payload["items"])
    assert all(item["claim_code"] == "CLAIM_MINI_LED_BACKLIGHT" for item in hits_payload["items"])


def test_m04a_claim_api_returns_clear_error_when_inputs_are_missing():
    session = make_session()
    client = make_client(session)

    response = client.post(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{BATCH_ID}/claims/base/run")

    assert response.status_code == 409
    assert "M04a inputs not ready" in response.json()["detail"]
