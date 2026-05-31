import json
import zipfile


def test_goal3_internal_workbench_fixture_review_calibration_and_export_boundary(client, repo_root):
    project_id = _create_project(client)
    expected = json.loads(
        (repo_root / "examples/goal3/expected/goal3_expected_min.json").read_text(encoding="utf-8")
    )["tv00029115_min_expected"]

    fixture = client.post(f"/api/projects/{project_id}/workbench/use-fixture", json={})
    assert fixture.status_code == 200, fixture.text
    assert fixture.json()["status"] == "completed"

    overview = client.get(f"/api/projects/{project_id}/workbench/data-overview")
    assert overview.status_code == 200, overview.text
    overview_body = overview.json()
    assert overview_body["sku_count"] == 8
    assert overview_body["raw_parameter_row_count"] > 0
    assert overview_body["raw_claim_row_count"] == 8
    assert overview_body["raw_comment_row_count"] == 8
    assert overview_body["market_fact_row_count"] == 8
    assert not any(
        item["table"] == "raw_sku_param" and item["field"] == "raw_param_value"
        for item in overview_body["missing_field_rates"]
    )

    parameters = client.get(f"/api/projects/{project_id}/assets/parameters")
    assert parameters.status_code == 200, parameters.text
    parameter_rows = parameters.json()["items"]
    parameter_codes = {row["param_code"] for row in parameter_rows}
    assert {"screen_size_inch", "mini_led_flag", "refresh_rate_hz", "peak_brightness_nits", "dimming_zones", "hdmi_2_1_ports"}.issubset(parameter_codes)
    _assert_common_workbench_row(parameter_rows[0])

    reviewed = client.patch(
        f"/api/projects/{project_id}/assets/parameters/screen_size_inch/review",
        json={"decision": "approved", "reviewer": "analyst_a"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == "approved"
    assert reviewed.json()["last_reviewer"] == "analyst_a"

    for path in [
        "claims",
        "comment-topics",
        "tasks",
        "target-groups",
        "battlefields",
        "mappings",
    ]:
        response = client.get(f"/api/projects/{project_id}/assets/{path}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] > 0
        _assert_common_workbench_row(body["items"][0])

    sku_results = client.get(f"/api/projects/{project_id}/sku-results")
    assert sku_results.status_code == 200, sku_results.text
    assert sku_results.json()["count"] == 8
    _assert_common_workbench_row(sku_results.json()["items"][0])

    sku_detail = client.get(f"/api/projects/{project_id}/sku-results/TV00029115")
    assert sku_detail.status_code == 200, sku_detail.text
    detail = sku_detail.json()
    claim_codes = {row["claim_code"] for row in detail["activated_standard_claims"]}
    task_codes = {row["task_code"] for row in detail["user_task_scores"]}
    battlefield_codes = {row["battlefield_code"] for row in detail["battlefield_scores"]}
    assert set(expected["activated_claims"]).issubset(claim_codes)
    assert set(expected["tasks"]).issubset(task_codes)
    assert set(expected["battlefields"]).issubset(battlefield_codes)
    assert detail["evidence_cards"]
    assert all(row["evidence_ids"] for row in detail["activated_standard_claims"])

    competitors = client.get(f"/api/projects/{project_id}/sku-results/TV00029115/competitors")
    assert competitors.status_code == 200, competitors.text
    assert competitors.json()["items"]
    assert all(row["component_scores"] and row["evidence_ids"] for row in competitors.json()["items"])

    calibration = client.get(f"/api/projects/{project_id}/calibration/summary")
    assert calibration.status_code == 200, calibration.text
    calibration_body = calibration.json()
    assert calibration_body["parameter_coverage"]
    assert calibration_body["claim_coverage"]
    assert "psi_price_support" in calibration_body
    assert "ssi_sales_support" in calibration_body
    assert "cpi_comment_perception" in calibration_body
    assert "sample_sufficiency" in calibration_body
    assert "expert_review_summary" in calibration_body
    assert "release_recommendation" in calibration_body

    preview = client.get(f"/api/projects/{project_id}/runtime-export/preview")
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["approved_deliverables"] == [
        "TV category semantic asset pack",
        "TV SKU analysis result pack",
        "TV market calibration report",
        "runtime scoring rules",
        "competitor runtime rules",
        "evidence cards",
        "release manifest",
    ]
    assert preview_body["release_gate"]["factory_only_content_blocked"] is True
    assert "prompt templates" in preview_body["factory_exclusions"]

    asset = _create_release_asset(client, project_id)
    export = client.post(
        f"/api/projects/{project_id}/runtime-export",
        json={"asset_version_id": asset["asset_version_id"], "created_by": "goal3-test"},
    )
    assert export.status_code == 200, export.text
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
    with zipfile.ZipFile(export.json()["file_path"]) as archive:
        names = set(archive.namelist())
        assert names.issubset(allowed)
        assert "asset_manifest.json" in names
        for name in names:
            assert not any(pattern in name.lower() for pattern in forbidden)
            content = archive.read(name).decode("utf-8", errors="ignore").lower()
            assert not any(pattern in content for pattern in forbidden)


def _assert_common_workbench_row(row):
    for key in [
        "source_basis",
        "raw_fields_or_text_examples",
        "derived_features",
        "mapping_lineage",
        "evidence_ids",
        "confidence",
        "review_status",
        "asset_version",
        "rule_version",
    ]:
        assert key in row


def _create_project(client) -> str:
    response = client.post(
        "/projects",
        json={"name": "Goal3 内部工作台验收", "category_code": "TV", "description": "自动化测试"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project_id"]


def _create_release_asset(client, project_id: str) -> dict:
    response = client.post(
        "/api/assets/versions",
        json={
            "project_id": project_id,
            "asset_type": "runtime_asset",
            "category_code": "TV",
            "version": "tv_goal3_release_test",
            "manifest_json": {
                "rule_versions": {"claim_activation": "1.0.0", "competitor": "1.0.0"},
                "quality_gates": {"workbench_reviewed": True, "export_boundary_checked": True},
                "approved_deliverables": ["TV category semantic asset pack"],
                "files": [],
            },
            "created_by": "pytest",
        },
    )
    assert response.status_code == 200, response.text
    asset = response.json()
    asset_id = asset["asset_version_id"]
    assert client.post(f"/api/assets/{asset_id}/submit-review", json={"actor_id": "pytest"}).status_code == 200
    assert client.post(f"/api/assets/{asset_id}/approve", json={"actor_id": "pytest"}).status_code == 200
    released = client.post(f"/api/assets/{asset_id}/release", json={"actor_id": "pytest", "approved_by": "pytest"})
    assert released.status_code == 200, released.text
    return released.json()
