import json
import zipfile

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AnalysisRun


def test_goal2_duplicate_analysis_job_is_idempotent_and_does_not_duplicate_rows(client):
    project_id = _create_project(client)
    payload = {
        "project_id": project_id,
        "job_type": "analysis_run",
        "idempotency_key": "same-analysis",
        "input": {"target_sku_code": "TV00029115"},
        "max_attempts": 2,
    }

    first = client.post("/api/jobs", json=payload)
    second = client.post("/api/jobs", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["job_id"] == second.json()["job_id"]
    assert second.json()["diagnostics_json"]["idempotent_replay"] is True
    assert _analysis_run_count(project_id) == 1


def test_goal2_retry_contract_failure_checkpoint_and_cancel(client):
    project_id = _create_project(client)

    transient = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "job_type": "data_profile",
            "idempotency_key": "retry-profile",
            "input": {
                "rows": [{"sku_code": "TV1", "brand": "A"}],
                "transient_failures_before_success": 1,
            },
            "max_attempts": 3,
        },
    )
    assert transient.status_code == 200, transient.text
    transient_body = transient.json()
    assert transient_body["status"] == "succeeded"
    assert transient_body["attempt_count"] == 2
    diagnostics = client.get(f"/api/jobs/{transient_body['job_id']}/diagnostics").json()
    assert diagnostics["retry_history"][0]["status"] == "failed"
    assert diagnostics["retry_history"][0]["retry_after_seconds"] == 1

    contract = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "job_type": "data_import",
            "idempotency_key": "bad-import",
            "input": {"rows": [{"sku_code": ""}], "required_columns": ["sku_code"]},
            "max_attempts": 5,
        },
    )
    assert contract.status_code == 200, contract.text
    contract_body = contract.json()
    assert contract_body["status"] == "failed"
    assert contract_body["attempt_count"] == 1
    assert contract_body["error_code"] == "contract_error"
    retry_contract = client.post(f"/api/jobs/{contract_body['job_id']}/retry")
    assert retry_contract.status_code == 400

    checkpoint = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "job_type": "analysis_run",
            "idempotency_key": "checkpoint-analysis",
            "input": {"target_sku_code": "TV00029115", "simulate_transient_after_checkpoint": True},
            "max_attempts": 2,
        },
    )
    assert checkpoint.status_code == 200, checkpoint.text
    checkpoint_body = checkpoint.json()
    assert checkpoint_body["status"] == "succeeded"
    assert checkpoint_body["attempt_count"] == 2
    assert checkpoint_body["checkpoint_json"]["stage"] == "analysis_completed"
    assert _analysis_run_count(project_id) == 1

    queued = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "job_type": "data_profile",
            "idempotency_key": "cancel-profile",
            "input": {"rows": [{"sku_code": "TV1"}]},
            "run_now": False,
        },
    )
    assert queued.status_code == 200, queued.text
    assert queued.json()["status"] == "queued"
    cancelled = client.post(f"/api/jobs/{queued.json()['job_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_goal2_version_governance_release_lock_export_audit_and_rollback(client, repo_root):
    project_id = _create_project(client)
    client.post(
        f"/api/projects/{project_id}/run-analysis",
        json={"target_sku_code": "TV00029115"},
    )

    asset = _create_asset_version(client, project_id, "tv_assets_goal2_v1")
    asset_id = asset["asset_version_id"]

    lock_job = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "job_type": "asset_release",
            "idempotency_key": "release-lock-1",
            "input": {"asset_version_id": asset_id},
            "run_now": False,
        },
    )
    assert lock_job.status_code == 200
    blocked_job = client.post(
        "/api/jobs",
        json={
            "project_id": project_id,
            "job_type": "asset_release",
            "idempotency_key": "release-lock-2",
            "input": {"asset_version_id": asset_id},
            "run_now": False,
        },
    )
    assert blocked_job.status_code == 200
    assert blocked_job.json()["status"] == "blocked"
    client.post(f"/api/jobs/{lock_job.json()['job_id']}/cancel")

    assert client.post(f"/api/assets/{asset_id}/submit-review", json={"actor_id": "reviewer"}).status_code == 200
    assert client.post(f"/api/assets/{asset_id}/approve", json={"actor_id": "approver"}).status_code == 200
    release = client.post(f"/api/assets/{asset_id}/release", json={"actor_id": "release_mgr"})
    assert release.status_code == 200, release.text
    released = release.json()
    assert released["lifecycle_status"] == "released"

    rerelease = client.post(f"/api/assets/{asset_id}/release", json={"actor_id": "release_mgr"})
    assert rerelease.status_code == 400

    edit = client.post(
        f"/api/assets/{asset_id}/edit",
        json={"actor_id": "editor", "manifest_json": {"quality_gates": {"claim_f1": 0.91}}},
    )
    assert edit.status_code == 200, edit.text
    edited = edit.json()
    assert edited["asset_version_id"] != asset_id
    assert edited["lifecycle_status"] == "draft"
    assert client.get(f"/api/assets/{asset_id}/versions").json()["count"] >= 2
    archived = client.post(
        f"/api/assets/{edited['asset_version_id']}/archive",
        json={"actor_id": "archiver", "reason": "验收归档"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["lifecycle_status"] == "archived"
    edit_archived = client.post(
        f"/api/assets/{edited['asset_version_id']}/edit",
        json={"actor_id": "editor", "manifest_json": {"quality_gates": {"claim_f1": 0.5}}},
    )
    assert edit_archived.status_code == 400

    export = client.post(
        f"/api/projects/{project_id}/runtime-export",
        json={"asset_version_id": asset_id, "created_by": "exporter"},
    )
    assert export.status_code == 200, export.text
    export_body = export.json()
    allowed = {
        line.strip()
        for line in (repo_root / "examples/goal2/exports/allowed_files.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    forbidden = [
        line.strip().lower()
        for line in (repo_root / "examples/goal2/exports/forbidden_patterns.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with zipfile.ZipFile(export_body["file_path"]) as archive:
        names = set(archive.namelist())
        assert names.issubset(allowed)
        assert "asset_manifest.json" in names
        manifest = json.loads(archive.read("asset_manifest.json").decode("utf-8"))
        assert manifest["files"]
        for name in names:
            lowered = name.lower()
            assert not any(pattern in lowered for pattern in forbidden)
            content = archive.read(name).decode("utf-8", errors="ignore").lower()
            assert not any(pattern in content for pattern in forbidden)

    forbidden_asset = _create_asset_version(
        client,
        project_id,
        "tv_assets_forbidden",
        manifest_json={
            "runtime_files": [{"path": "release_note.md", "content": "prompt_template should fail"}]
        },
    )
    client.post(f"/api/assets/{forbidden_asset['asset_version_id']}/approve", json={"actor_id": "approver"})
    client.post(f"/api/assets/{forbidden_asset['asset_version_id']}/release", json={"actor_id": "release_mgr"})
    forbidden_export = client.post(
        f"/api/projects/{project_id}/runtime-export",
        json={"asset_version_id": forbidden_asset["asset_version_id"]},
    )
    assert forbidden_export.status_code == 400

    rollback = client.post(
        f"/api/assets/{asset_id}/rollback",
        json={"target_version_id": asset_id, "reason": "回滚验收", "actor_id": "release_mgr"},
    )
    assert rollback.status_code == 200, rollback.text
    rollback_body = rollback.json()
    assert rollback_body["lifecycle_status"] == "released"
    assert rollback_body["rollback_from_version_id"] == asset_id

    rule_response = client.post(
        "/api/rule-sets",
        json={
            "rule_set_id": "goal2_audit_rule",
            "category": "TV",
            "rule_type": "claim_activation",
            "version": "1.0.0",
            "rules": [
                {
                    "rule_id": "CLAIM_AUDIT",
                    "output_code": "CLAIM_AUDIT",
                    "score": {"weights": [{"feature": "claim_text", "op": "contains", "value": "audit", "points": 100}]},
                }
            ],
        },
    )
    assert rule_response.status_code == 200, rule_response.text

    audit = client.get(f"/api/audit?project_id={project_id}").json()["items"]
    actions = {item["action"] for item in audit} | {
        item["action"] for item in client.get("/api/audit?action=rule_edit").json()["items"]
    }
    assert {"asset_released", "runtime_export_created", "asset_rollback", "rule_edit"}.issubset(actions)

    permission_audit = client.post(
        "/api/audit/permission-change",
        json={
            "project_id": project_id,
            "actor_id": "admin",
            "user_id": "analyst_a",
            "before": {"role": "viewer"},
            "after": {"role": "reviewer"},
            "reason": "验收权限变更审计",
        },
    )
    assert permission_audit.status_code == 200, permission_audit.text
    assert permission_audit.json()["action"] == "user_permission_changed"

    ready = client.get("/readyz")
    assert ready.status_code == 200
    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert "jobs_total" in metrics.json()


def _create_project(client) -> str:
    response = client.post(
        "/projects",
        json={"name": "Goal2 生产化验收", "category_code": "TV", "description": "自动化测试"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project_id"]


def _create_asset_version(client, project_id: str, version: str, manifest_json: dict | None = None) -> dict:
    response = client.post(
        "/api/assets/versions",
        json={
            "project_id": project_id,
            "asset_type": "runtime_asset",
            "category_code": "TV",
            "version": version,
            "manifest_json": manifest_json
            or {
                "rule_versions": {"claim_activation": "1.0.0", "competitor": "1.0.0"},
                "input_dataset_fingerprint": "sha256:test",
                "evaluation_report_id": "eval-test",
                "quality_gates": {"claim_f1": 0.9, "competitor_top3_hit_rate": 0.8},
                "files": [],
            },
            "created_by": "pytest",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _analysis_run_count(project_id: str) -> int:
    with SessionLocal() as db:
        return len(db.execute(select(AnalysisRun).where(AnalysisRun.project_id == project_id)).scalars().all())
