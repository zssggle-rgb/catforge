from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.constants import Core3ModuleCode, Core3RunStatus
from app.services.core3_real_data.pipeline_initialization_service import module_spec

from .test_local_validation_fixture_pipeline import PROJECT_ID, make_client, make_session


def test_pipeline_initialization_runs_and_skips_completed_module():
    session = make_session()
    client = make_client(session)

    initial_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization")
    assert initial_response.status_code == 200
    initial_payload = initial_response.json()
    assert initial_payload["batch_id"] is None
    assert initial_payload["modules"][0]["module_code"] == Core3ModuleCode.M00.value
    assert initial_payload["modules"][0]["can_execute"] is True
    assert initial_payload["modules"][1]["execution_status"] == "blocked"

    m00_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M00.value},
    )
    assert m00_response.status_code == 200
    m00_payload = m00_response.json()
    batch_id = m00_payload["batch_id"]
    assert batch_id
    assert m00_payload["result"]["status"] in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value}
    assert m00_payload["module"]["execution_status"] == "completed"

    m01_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M01.value, "batch_id": batch_id},
    )
    assert m01_response.status_code == 200
    m01_payload = m01_response.json()
    assert m01_payload["skipped"] is False
    assert m01_payload["result"]["status"] in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value}
    assert m01_payload["module"]["execution_status"] in {"completed", "partial"}
    assert m01_payload["module"]["output_count"] > 0
    actual_m01_run_id = m01_payload["module"]["latest_run_id"]

    repeat_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M01.value, "batch_id": batch_id},
    )
    assert repeat_response.status_code == 200
    repeat_payload = repeat_response.json()
    assert repeat_payload["skipped"] is True
    assert repeat_payload["result"]["status"] == Core3RunStatus.SKIPPED_REUSED.value
    assert repeat_payload["module"]["latest_run_id"] == actual_m01_run_id
    assert repeat_payload["module"]["latest_status"] in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value}

    module_runs = (
        session.query(entities.Core3V2ModuleRun)
        .filter(entities.Core3V2ModuleRun.project_id == PROJECT_ID)
        .filter(entities.Core3V2ModuleRun.batch_id == batch_id)
        .all()
    )
    statuses = {(item.module_code, item.status) for item in module_runs}
    assert (Core3ModuleCode.M00.value, m00_payload["result"]["status"]) in statuses
    assert (Core3ModuleCode.M01.value, Core3RunStatus.SKIPPED_REUSED.value) in statuses


def test_m084_initialization_progress_counts_sku_support_not_dimension_candidates():
    spec = module_spec(Core3ModuleCode.M08_4)

    assert spec.output_target_field == "sku_code"


def test_pipeline_initialization_preregisters_module_run_for_m03(monkeypatch):
    session = make_session()
    client = make_client(session)

    m00_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M00.value},
    )
    batch_id = m00_response.json()["batch_id"]
    client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M01.value, "batch_id": batch_id},
    )
    client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M02.value, "batch_id": batch_id},
    )

    def fake_m03_run(self, context, target):
        module_run_id = target.metadata["module_run_id"]
        assert session.get(entities.Core3V2ModuleRun, module_run_id) is not None
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M03,
            status=Core3RunStatus.SUCCESS,
            input_count=1,
            changed_input_count=1,
            output_count=1,
            output_hash="test-m03",
            warnings=[],
            review_issues=[],
            downstream_impacts=[],
            summary_json={"module_run_id_seen": module_run_id},
        )

    monkeypatch.setattr("app.api.core3_real_data.ParamExtractionRunner.run", fake_m03_run)

    response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/initialization/run",
        json={"module_code": Core3ModuleCode.M03.value, "batch_id": batch_id, "force_rebuild": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["status"] == Core3RunStatus.SUCCESS.value
    module_run_id = payload["result"]["summary_json"]["module_run_id_seen"]
    module_run = session.get(entities.Core3V2ModuleRun, module_run_id)
    assert module_run is not None
    assert module_run.status == Core3RunStatus.SUCCESS.value
