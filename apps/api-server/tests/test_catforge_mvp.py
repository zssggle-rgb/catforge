import zipfile


SAMPLE_FILES = [
    ("examples/sample_sku_master.csv", "sku_master"),
    ("examples/sample_sku_params.csv", "sku_param"),
    ("examples/sample_sku_claims.csv", "sku_claim"),
    ("examples/sample_sku_comments.csv", "sku_comment"),
    ("examples/sample_market_facts.csv", "market_fact"),
]

PIPELINE_STEPS = [
    "generate_params",
    "generate_claims",
    "generate_comment_topics",
    "score_tasks_battlefields",
    "calculate_market_metrics",
    "build_review_queue",
]


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_import_quality_pipeline_and_runtime_export(client, repo_root):
    project_id = _create_project(client)
    _import_samples(client, repo_root, project_id)

    quality = client.get(f"/projects/{project_id}/data-quality").json()
    assert quality["summary"]["raw_row_counts"]["sku_master"] == 5
    assert quality["summary"]["critical_count"] == 0
    assert quality["summary"]["status"] == "passed"

    for step in PIPELINE_STEPS:
        response = client.post(f"/projects/{project_id}/pipeline/{step}")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed"

    params = _items(client, project_id, "normalized_params")
    sample_params = {
        item["param_code"]: item for item in params if item["sku_code"] == "TV00029115"
    }
    assert sample_params["screen_size_inch"]["normalized_numeric"] == 85
    assert sample_params["system_refresh_rate_hz"]["normalized_numeric"] == 300
    assert sample_params["native_refresh_rate_hz"]["normalized_numeric"] == 170
    assert sample_params["mini_led_flag"]["normalized_bool"] is True
    assert sample_params["ram_gb"]["normalized_numeric"] == 4
    assert sample_params["storage_gb"]["normalized_numeric"] == 64
    assert sample_params["instant_peak_brightness_nits"]["normalized_numeric"] == 5200
    assert sample_params["sustained_peak_brightness_nits"]["normalized_numeric"] == 3800
    assert sample_params["dimming_zones"]["normalized_numeric"] == 3500
    assert sample_params["eye_dimming_freq_hz"]["normalized_numeric"] == 20000
    assert sample_params["hdmi_2_1_ports"]["normalized_numeric"] == 4
    assert sample_params["mini_led_flag"]["evidence_ids"]

    competitor_params = {
        item["param_code"]: item for item in params if item["sku_code"] == "TV00010002"
    }
    assert competitor_params["mini_led_flag"]["normalized_value"] == "unknown"
    assert competitor_params["mini_led_flag"]["normalized_bool"] is None

    claims = {
        item["claim_code"]
        for item in _items(client, project_id, "claims")
        if item["sku_code"] == "TV00029115"
    }
    assert {
        "CLAIM_LARGE_SCREEN_IMMERSION",
        "CLAIM_MINI_LED_BACKLIGHT",
        "CLAIM_HIGH_BRIGHTNESS_HDR",
        "CLAIM_FINE_LOCAL_DIMMING",
        "CLAIM_HIGH_REFRESH_RATE",
        "CLAIM_HDMI_2_1_GAMING",
        "CLAIM_EYE_CARE_COMFORT",
        "CLAIM_SMART_VOICE_EASE",
    }.issubset(claims)

    topics = {
        item["topic_code"]: item
        for item in _items(client, project_id, "topics")
        if item["sku_code"] == "TV00029115"
    }
    assert {
        "TOPIC_PICTURE_QUALITY",
        "TOPIC_SPORTS_WATCHING",
        "TOPIC_INTERFACE_CONNECTIVITY",
        "TOPIC_EASE_OF_USE",
        "TOPIC_SENIOR_FRIENDLY",
        "TOPIC_INSTALLATION_SERVICE",
    }.issubset(topics)
    assert topics["TOPIC_INSTALLATION_SERVICE"]["activates_product_claim"] is False

    task_scores = {
        item["task_code"]: item
        for item in _items(client, project_id, "tasks")
        if item["sku_code"] == "TV00029115"
    }
    assert task_scores["TASK_PREMIUM_PICTURE_AV"]["score"] >= 75
    assert task_scores["TASK_SENIOR_EASY_USE"]["evidence_ids"]

    battlefield_scores = {
        item["battlefield_code"]: item
        for item in _items(client, project_id, "battlefields")
        if item["sku_code"] == "TV00029115"
    }
    assert battlefield_scores["BF_PREMIUM_PICTURE"]["relation_level"] in {"main", "secondary"}
    assert battlefield_scores["BF_FAMILY_EYE_CARE"]["relation_level"] in {"weak", "opportunity", "secondary"}

    review = client.get(f"/projects/{project_id}/review-queue").json()
    reason_codes = {item["reason_code"] for item in review["items"]}
    assert "param_conflict" in reason_codes
    assert "high_value_sku" in reason_codes
    claim_review = next(item for item in review["items"] if item["item_type"] == "claim")
    assert claim_review["candidate_payload"]["review_context"]["object_type_label"] == "SKU 卖点结果"
    decision_response = client.post(
        f"/review-queue/{claim_review['review_id']}/decision",
        json={"decision": "approved", "reviewer": "pytest"},
    )
    assert decision_response.status_code == 200, decision_response.text
    sku_code, claim_code = claim_review["item_key"].split(":")
    reviewed_claim = next(
        item
        for item in _items(client, project_id, "claims")
        if item["sku_code"] == sku_code and item["claim_code"] == claim_code
    )
    assert reviewed_claim["review_status"] == "approved"
    assert reviewed_claim["status"] == "accepted"

    export_response = client.post(
        f"/projects/{project_id}/export-runtime", json={"version": "0.1.0"}
    )
    assert export_response.status_code == 200, export_response.text
    export_data = export_response.json()
    assert set(export_data["files"]) == {
        "std_param_def.csv",
        "std_claim_def.csv",
        "comment_topic_def.csv",
        "user_task_def.csv",
        "target_group_def.csv",
        "battlefield_def.csv",
        "mapping_rules.csv",
        "scoring.yaml",
        "competitor_rule.yaml",
        "sample_sku_results.csv",
        "sample_evidence_cards.jsonl",
        "asset_readme.md",
        "release_note.md",
    }
    forbidden = {
        "prompt",
        "gold_set_builder",
        "category_builder",
        "migration_template",
        "rule_generator",
        "semantic_clustering",
        "factory_internal",
        "benchmark_builder",
    }
    with zipfile.ZipFile(export_data["package_path"]) as archive:
        names = archive.namelist()
        assert set(names) == set(export_data["files"])
        for name in names:
            lowered = name.lower()
            assert not any(pattern in lowered for pattern in forbidden)


def test_missing_sku_code_creates_critical_quality_issue(client, tmp_path):
    project_id = _create_project(client)
    bad_file = tmp_path / "bad_params.csv"
    bad_file.write_text(
        "sku_code,raw_param_name,raw_param_value,raw_unit,source_channel,observed_at\n"
        ",屏幕尺寸,85英寸,,JD,2026-05-25T00:00:00\n",
        encoding="utf-8",
    )
    response = client.post(
        f"/projects/{project_id}/imports",
        json={"file_path": str(bad_file), "file_type": "sku_param"},
    )
    assert response.status_code == 200
    quality = client.get(f"/projects/{project_id}/data-quality").json()
    assert quality["summary"]["critical_count"] == 1
    assert quality["issues"][0]["issue_code"] == "missing_required_field"


def _create_project(client) -> str:
    response = client.post(
        "/projects",
        json={"name": "彩电 MVP 验收项目", "category_code": "TV", "description": "自动化测试"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project_id"]


def _import_samples(client, repo_root, project_id: str) -> None:
    for path, file_type in SAMPLE_FILES:
        response = client.post(
            f"/projects/{project_id}/imports",
            json={"file_path": str(repo_root / path), "file_type": file_type},
        )
        assert response.status_code == 200, response.text


def _items(client, project_id: str, asset_type: str) -> list[dict]:
    response = client.get(f"/projects/{project_id}/assets/{asset_type}")
    assert response.status_code == 200, response.text
    return response.json()["items"]
