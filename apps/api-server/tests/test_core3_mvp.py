import csv
import json
from io import StringIO

from sqlalchemy import func, inspect, select

from app.core.database import SessionLocal, engine
from app.models import SkuCompetitorResult
from app.models.entities import (
    Core3CompetitorCandidate,
    Core3CompetitorResult,
    Core3EvidenceCard,
    Core3PipelineRun,
    Core3SkuFeatureProfile,
    Core3SkuMarketProfile,
    EvidenceItem,
)
from app.services.core3_mvp.data_access import is_unknown, load_project_input
from app.services.core3_mvp.evidence_graph import get_or_create_evidence
from app.services.core3_mvp.extraction import (
    discover_candidate_param_aliases,
    parse_value,
    profile_param_fields,
)
from app.services.core3_mvp.feature_pipeline import run_feature_extraction
from app.services.core3_mvp.seed_loader import (
    REQUIRED_PARSERS,
    SKU_LEVEL_FORBIDDEN_KEYS,
    load_core3_seed,
    validate_core3_seed,
)


SAMPLE_FILES = [
    ("examples/sample_sku_master.csv", "sku_master"),
    ("examples/sample_sku_params.csv", "sku_param"),
    ("examples/sample_sku_claims.csv", "sku_claim"),
    ("examples/sample_sku_comments.csv", "sku_comment"),
    ("examples/sample_market_facts.csv", "market_fact"),
]


def test_core3_data_status_and_resolve_sku(client, repo_root, tmp_path):
    missing = client.get("/api/mvp/core3/projects/not-exists/data-status")
    assert missing.status_code == 404

    empty_project_id = _create_project(client, "彩电 Core3 空项目")
    empty_status = client.get(f"/api/mvp/core3/projects/{empty_project_id}/data-status")
    assert empty_status.status_code == 200, empty_status.text
    empty_body = empty_status.json()
    assert empty_body["sku_count"] == 0
    assert empty_body["status"] == "degraded"

    project_id = _create_project(client, "彩电 Core3 样例项目")
    _import_samples(client, repo_root, project_id)

    status = client.get(f"/api/mvp/core3/projects/{project_id}/data-status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["project_id"] == project_id
    assert body["category_code"] == "TV"
    assert body["status"] == "ready"
    assert body["sku_count"] == 5
    assert body["brand_count"] == 5
    assert body["channel_count"] >= 1
    assert body["market_fact_count"] == 5
    assert body["param_row_count"] > 0
    assert body["claim_row_count"] > 0
    assert body["comment_row_count"] == 5
    assert body["missing_summary"]["missing_market_sku_count"] == 0
    assert body["latest_run"] is None

    sku_response = client.get(
        f"/api/mvp/core3/projects/{project_id}/resolve-sku", params={"query": "TV00029115"}
    )
    assert sku_response.status_code == 200, sku_response.text
    sku_body = sku_response.json()
    assert sku_body["sku_code"] == "TV00029115"
    assert sku_body["brand"] == "海信"
    assert sku_body["model_name"] == "85E7Q"
    assert sku_body["match_type"] == "sku_code_exact"
    assert sku_body["candidates"] == []

    model_response = client.get(
        f"/api/mvp/core3/projects/{project_id}/resolve-sku", params={"query": "Redmi MAX"}
    )
    assert model_response.status_code == 200, model_response.text
    model_body = model_response.json()
    assert model_body["sku_code"] == "TV00010002"
    assert model_body["match_type"] == "model_name_contains"

    duplicate_master = tmp_path / "ambiguous_sku_master.csv"
    duplicate_master.write_text(
        "sku_code,brand,model_name,series,category_code,category_name,launch_date,product_url\n"
        "TVCOREX,海信,85E7Q Pro,E7Q,TV,彩电,,\n",
        encoding="utf-8",
    )
    import_response = client.post(
        f"/projects/{project_id}/imports",
        json={"file_path": str(duplicate_master), "file_type": "sku_master"},
    )
    assert import_response.status_code == 200, import_response.text

    conflict = client.get(
        f"/api/mvp/core3/projects/{project_id}/resolve-sku", params={"query": "85E7"}
    )
    assert conflict.status_code == 409, conflict.text
    detail = conflict.json()["detail"]
    assert detail["input"] == "85E7"
    assert len(detail["candidates"]) == 2
    assert {item["sku_code"] for item in detail["candidates"]} == {"TV00029115", "TVCOREX"}
    assert all(item["match_type"] == "model_name_contains" for item in detail["candidates"])

    unknown = client.get(
        f"/api/mvp/core3/projects/{project_id}/resolve-sku", params={"query": "-"}
    )
    assert unknown.status_code == 400

    schema = client.get("/openapi.json").json()
    assert "/api/mvp/core3/projects/{project_id}/data-status" in schema["paths"]
    assert "/api/mvp/core3/projects/{project_id}/resolve-sku" in schema["paths"]
    assert "/api/mvp/core3/projects/{project_id}/run" in schema["paths"]
    assert _competitor_result_count() == 0


def test_core3_is_unknown_recognizes_empty_dash_and_null():
    assert is_unknown("")
    assert is_unknown("   ")
    assert is_unknown("-")
    assert is_unknown("null")
    assert is_unknown(" NULL ")
    assert is_unknown(None)
    assert not is_unknown("TV00029115")


def test_core3_tables_are_created_in_sqlite(client):
    table_names = set(inspect(engine).get_table_names())
    assert {
        "core3_pipeline_run",
        "core3_sku_market_profile",
        "core3_sku_feature_profile",
        "core3_competitor_candidate",
        "core3_competitor_result",
        "core3_evidence_card",
    }.issubset(table_names)


def test_core3_run_context_lifecycle_reuse_force_and_batch(client, repo_root):
    project_id = _create_project(client, "彩电 Core3 Run 项目")
    _import_samples(client, repo_root, project_id)

    created = client.post(
        f"/api/mvp/core3/projects/{project_id}/run",
        json={"target_sku_code": "TV00029115"},
    )
    assert created.status_code == 200, created.text
    created_body = created.json()
    assert created_body["status"] == "completed"
    assert created_body["scope"] == "single_sku"
    assert created_body["target_sku_code"] == "TV00029115"
    assert created_body["counts"]["sku_count"] == 5
    assert created_body["counts"]["target_sku_count"] == 1
    assert created_body["counts"]["market_profile_count"] == 5
    assert created_body["counts"]["feature_profile_count"] == 5
    assert created_body["counts"]["competitor_result_count"] == 3
    assert created_body["counts"]["evidence_card_count"] == 3
    assert created_body["diagnostics"]["target_sku_codes"] == ["TV00029115"]
    run_id = created_body["run_id"]

    with SessionLocal() as db:
        run = db.get(Core3PipelineRun, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.input_fingerprint
        assert run.finished_at is not None

    reused = client.post(
        f"/api/mvp/core3/projects/{project_id}/run",
        json={"target_sku_code": "TV00029115", "force_recompute": False},
    )
    assert reused.status_code == 200, reused.text
    reused_body = reused.json()
    assert reused_body["run_id"] == run_id
    assert reused_body["status"] == "completed"
    assert reused_body["counts"]["competitor_result_count"] == 3

    forced = client.post(
        f"/api/mvp/core3/projects/{project_id}/run",
        json={"target_sku_code": "TV00029115", "force_recompute": True},
    )
    assert forced.status_code == 200, forced.text
    forced_body = forced.json()
    assert forced_body["run_id"] != run_id
    assert forced_body["status"] == "completed"
    assert forced_body["diagnostics"]["force_recompute"] is True

    batch = client.post(f"/api/mvp/core3/projects/{project_id}/run", json={"batch": True})
    assert batch.status_code == 200, batch.text
    batch_body = batch.json()
    assert batch_body["status"] == "completed"
    assert batch_body["scope"] == "batch"
    assert batch_body["target_sku_code"] is None
    assert batch_body["counts"]["target_sku_count"] == 5
    assert batch_body["counts"]["competitor_result_count"] == 15
    assert batch_body["counts"]["evidence_card_count"] == 15
    assert batch_body["diagnostics"]["target_sku_codes"] == [
        "TV00010001",
        "TV00010002",
        "TV00010003",
        "TV00010004",
        "TV00029115",
    ]
    assert _model_count(Core3PipelineRun) == 3
    assert _core3_result_counts()["competitor_results"] == 21


def test_core3_run_empty_project_and_missing_target_do_not_fabricate_results(client):
    project_id = _create_project(client, "彩电 Core3 空 Run 项目")

    empty = client.post(f"/api/mvp/core3/projects/{project_id}/run", json={"batch": True})
    assert empty.status_code == 200, empty.text
    empty_body = empty.json()
    assert empty_body["status"] == "completed_empty"
    assert empty_body["counts"]["target_sku_count"] == 0
    assert empty_body["diagnostics"]["target_sku_codes"] == []

    before_count = _model_count(Core3PipelineRun)
    missing = client.post(
        f"/api/mvp/core3/projects/{project_id}/run",
        json={"target_sku_code": "TV-NOT-EXISTS"},
    )
    assert missing.status_code == 404
    assert _model_count(Core3PipelineRun) == before_count
    assert _core3_result_counts() == {
        "market_profiles": 0,
        "feature_profiles": 0,
        "competitor_candidates": 0,
        "competitor_results": 0,
        "evidence_cards": 0,
    }


def test_core3_seed_v0_2_loads_validates_and_is_extraction_ready():
    seed = load_core3_seed()
    validation = validate_core3_seed(seed)
    assert validation["valid"] is True
    assert validation["errors"] == []

    assert validation["counts"]["standard_params"] >= 35
    assert validation["counts"]["standard_claims"] >= 18
    assert validation["counts"]["comment_topics"] >= 15
    assert validation["counts"]["user_tasks"] >= 9
    assert validation["counts"]["target_groups"] >= 8
    assert validation["counts"]["battlefields"] >= 9

    _assert_unique([item.param_code for item in seed.standard_params])
    _assert_unique([item.claim_code for item in seed.standard_claims])
    _assert_unique([item.topic_code for item in seed.comment_topics])
    _assert_unique([item.task_code for item in seed.user_tasks])
    _assert_unique([item.target_group_code for item in seed.target_groups])
    _assert_unique([item.battlefield_code for item in seed.battlefields])

    param_codes = {item.param_code for item in seed.standard_params}
    claim_codes = {item.claim_code for item in seed.standard_claims}
    task_codes = {item.task_code for item in seed.user_tasks}
    battlefield_codes = {item.battlefield_code for item in seed.battlefields}

    parser_codes = {parser for item in seed.standard_params for parser in item.value_parsers}
    assert REQUIRED_PARSERS.issubset(parser_codes)

    brightness = next(item for item in seed.standard_params if item.param_code == "peak_brightness_nits")
    assert {"峰值亮度", "尼特"}.issubset(set(brightness.aliases))
    assert "nits" in brightness.value_parsers
    assert "CLAIM_HIGH_BRIGHTNESS_HDR" in brightness.mapped_claim_codes

    gaming_claim = next(item for item in seed.standard_claims if item.claim_code == "CLAIM_HDMI_2_1_GAMING")
    assert set(gaming_claim.supporting_param_codes).issubset(param_codes)
    assert "HDMI 2.1" in gaming_claim.promo_keywords
    assert "TASK_GAMING_ENTERTAINMENT" in gaming_claim.mapped_task_codes

    sports_topic = next(item for item in seed.comment_topics if item.topic_code == "TOPIC_SPORTS_WATCHING")
    assert set(sports_topic.mapped_claim_codes).issubset(claim_codes)
    assert sports_topic.activates_product_claim is True

    value_task = next(item for item in seed.user_tasks if item.task_code == "TASK_VALUE_PURCHASE")
    assert set(value_task.mapped_claim_codes).issubset(claim_codes)
    assert set(value_task.mapped_battlefield_codes).issubset(battlefield_codes)

    premium_battlefield = next(
        item for item in seed.battlefields if item.battlefield_code == "BF_PREMIUM_PICTURE"
    )
    assert set(premium_battlefield.core_task_codes).issubset(task_codes)
    assert set(premium_battlefield.core_claim_codes).issubset(claim_codes)
    assert set(premium_battlefield.core_param_codes).issubset(param_codes)


def test_core3_seed_v0_2_has_no_sku_level_conclusion_fields():
    raw = load_core3_seed().model_dump()
    found = _collect_forbidden_keys(raw, SKU_LEVEL_FORBIDDEN_KEYS)
    assert found == []


def test_core3_extraction_parsers_cover_goal_d_required_examples():
    assert parse_value("85英寸", "inch").value == 85
    assert parse_value("144Hz", "hz").value == 144
    assert parse_value("1600nits", "nits").value == 1600
    assert parse_value("1296分区", "zones").value == 1296
    gb = parse_value("4GB+64GB", "gb").value
    assert gb["ram_gb"] == 4
    assert gb["storage_gb"] == 64
    assert parse_value("2个HDMI2.1", "ports").value == 2
    assert parse_value("Mini LED", "boolean_keyword").value is True
    assert parse_value("OLED", "boolean_keyword").value is True
    assert parse_value("支持VRR", "boolean_keyword").value is True
    assert parse_value("无频闪", "boolean_keyword").value is True
    assert parse_value("-", "boolean_keyword") is None


def test_core3_field_profile_and_candidate_alias_come_from_raw_data(client, repo_root, tmp_path):
    project_id = _create_project(client, "彩电 Core3 抽取画像项目")
    _import_samples(client, repo_root, project_id)
    _import_goal_d_extra_inputs(client, tmp_path, project_id)

    with SessionLocal() as db:
        bundle = load_project_input(db, project_id)
        seed = load_core3_seed()
        profiles = profile_param_fields(bundle, seed)
        screen = next(item for item in profiles if item.raw_param_name == "尺寸(寸)")
        assert screen.matched_param_code == "screen_size_inch"
        assert screen.coverage == 0.2
        assert screen.non_empty_rate == 1.0
        assert "85" in screen.top_values

        candidates = discover_candidate_param_aliases(profiles)
        assert any(item.raw_param_name == "黑曜屏等级" and item.coverage == 1.0 for item in candidates)


def test_core3_feature_pipeline_extracts_real_features_evidence_and_candidates(client, repo_root, tmp_path):
    project_id = _create_project(client, "彩电 Core3 特征抽取项目")
    _import_samples(client, repo_root, project_id)
    _import_goal_d_extra_inputs(client, tmp_path, project_id)

    run_response = client.post(f"/api/mvp/core3/projects/{project_id}/run", json={"batch": True})
    assert run_response.status_code == 200, run_response.text
    run_id = run_response.json()["run_id"]

    with SessionLocal() as db:
        profiles = run_feature_extraction(db, run_id)
        assert len(profiles) == 5
        first_evidence_count = _model_count(EvidenceItem)
        profiles_again = run_feature_extraction(db, run_id)
        assert len(profiles_again) == 5
        assert _model_count(EvidenceItem) == first_evidence_count

        all_profiles = {
            row.sku_code: row
            for row in db.query(Core3SkuFeatureProfile).filter(Core3SkuFeatureProfile.run_id == run_id).all()
        }
        target = all_profiles["TV00029115"]
        assert target.standard_params["screen_size_inch"]["normalized_value"] == 85
        assert target.standard_params["system_refresh_rate_hz"]["normalized_value"] == 300
        assert target.standard_params["native_refresh_rate_hz"]["normalized_value"] == 170
        assert target.standard_params["instant_peak_brightness_nits"]["normalized_value"] == 5200
        assert target.standard_params["dimming_zones"]["normalized_value"] == 3500
        assert target.standard_params["hdmi_2_1_ports"]["normalized_value"] == 4
        assert target.standard_params["eye_dimming_freq_hz"]["normalized_value"] == 20000
        assert target.standard_params["mini_led_flag"]["normalized_value"] is True
        assert target.standard_params["ram_gb"]["normalized_value"] == 4
        assert target.standard_params["storage_gb"]["normalized_value"] == 64
        assert all(value["evidence_ids"] for value in target.standard_params.values())

        claim_codes = {item["claim_code"] for item in target.claim_activations}
        assert {
            "CLAIM_MINI_LED_BACKLIGHT",
            "CLAIM_HIGH_BRIGHTNESS_HDR",
            "CLAIM_HDMI_2_1_GAMING",
            "CLAIM_EYE_CARE_COMFORT",
        }.issubset(claim_codes)
        assert all(item["evidence_ids"] for item in target.claim_activations)
        hdr = next(item for item in target.claim_activations if item["claim_code"] == "CLAIM_HIGH_BRIGHTNESS_HDR")
        assert hdr["param_score"] is not None
        assert hdr["promo_score"] is not None

        topics = {item["topic_code"]: item for item in target.comment_topics}
        assert "TOPIC_SPORTS_WATCHING" in topics
        assert topics["TOPIC_SPORTS_WATCHING"]["sample_sentences"][0]["sentiment"] == "positive"
        assert "TOPIC_INSTALLATION_SERVICE" in topics
        assert topics["TOPIC_INSTALLATION_SERVICE"]["comment_type"] == "service_experience"

        diagnostics = target.extraction_diagnostics
        assert any(item["raw_param_name"] == "黑曜屏等级" for item in diagnostics["candidate_param_aliases"])
        assert any("黑曜晶彩Pro" in item["raw_phrase"] for item in diagnostics["candidate_claims"])
        assert any("包装气味明显" in item["raw_phrase"] for item in diagnostics["candidate_comment_topics"])
        assert target.feature_evidence_ids
        assert target.confidence > 0

        value_profile = all_profiles["TV00010002"]
        assert "mini_led_flag" not in value_profile.standard_params

        run = db.get(Core3PipelineRun, run_id)
        assert run.status == "completed"
        assert run.counts["feature_profile_count"] == 5
        assert run.counts["market_profile_count"] == 5
        assert run.counts["competitor_candidate_count"] > 0
        assert run.counts["competitor_result_count"] == 15
        assert run.counts["evidence_card_count"] == 15
        assert target.task_scores
        assert target.target_group_scores
        assert target.battlefield_scores
        gaming = next(item for item in target.task_scores if item["task_code"] == "TASK_GAMING_ENTERTAINMENT")
        assert gaming["component_scores"]["claim_signal"] is not None
        assert gaming["component_scores"]["param_signal"] is not None
        assert gaming["evidence_ids"]
        premium = next(item for item in target.battlefield_scores if item["battlefield_code"] == "BF_PREMIUM_PICTURE")
        assert premium["semantic_score"] > 0
        assert premium["market_score"] > 0
        assert premium["final_score"] > 0
        assert premium["evidence_ids"]
        assert _core3_result_counts()["competitor_results"] == 15


def test_core3_market_profile_and_report_api_full_core3(client, repo_root):
    project_id = _create_project(client, "彩电 Core3 市场画像项目")
    _import_samples(client, repo_root, project_id)

    run_id = _create_core3_run(client, project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, run_id)
        market = _market_profile(db, run_id, "TV00029115")
        assert market.price_wavg_12m == 9710.9085
        assert market.price_latest == 9710.9085
        assert market.sales_volume_12m == 3267
        assert market.sales_amount_12m == 31725538
        assert market.channel_share == {"JD": 1.0}
        assert market.price_percentile == 0.6
        assert market.sales_percentile == 0.8
        assert market.sales_amount_percentile == 1.0
        assert market.evidence_ids
        assert "insufficient_periods" in market.missing_signals
        assert market.confidence == 0.9

    report = client.get(f"/api/mvp/core3/projects/{project_id}/sku/85E7Q/report")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["target_sku"]["sku_code"] == "TV00029115"
    assert body["market_profile"]["sales_percentile"] == 0.8
    assert body["standard_params"]["screen_size_inch"]["normalized_value"] == 85
    assert any(item["claim_code"] == "CLAIM_HIGH_BRIGHTNESS_HDR" for item in body["activated_claims"])
    assert any(item["topic_code"] == "TOPIC_SPORTS_WATCHING" for item in body["comment_topics"])
    assert body["tasks"]
    assert body["target_groups"]
    assert body["battlefields"]
    competitors = body["core_competitors"]
    assert [item["role"] for item in competitors] == ["direct", "pressure", "benchmark_potential"]
    non_empty = [item for item in competitors if item["competitor_sku_code"]]
    assert len({item["competitor_sku_code"] for item in non_empty}) == len(non_empty)
    assert all(item["competitor_sku_code"] != "TV00029115" for item in non_empty)
    high_confidence = [item for item in non_empty if item["confidence_level"] == "high"]
    assert high_confidence
    assert all(len(item["evidence_categories"]) >= 4 for item in high_confidence)

    evidence = client.get(f"/api/mvp/core3/projects/{project_id}/sku/85E7Q/competitors/evidence")
    assert evidence.status_code == 200, evidence.text
    evidence_body = evidence.json()
    assert evidence_body["target_sku_code"] == "TV00029115"
    assert evidence_body["count"] == 3
    direct = next(item for item in evidence_body["items"] if item["role"] == "direct")
    assert direct["competitor_sku_code"]
    assert len(direct["evidence_categories"]) >= 4
    assert direct["evidence_items"]


def test_core3_overview_and_exports_follow_contract(client, repo_root):
    project_id = _create_project(client, "彩电 Core3 导出项目")
    _import_samples(client, repo_root, project_id)

    run_response = client.post(f"/api/mvp/core3/projects/{project_id}/run", json={"batch": True})
    assert run_response.status_code == 200, run_response.text
    run_id = run_response.json()["run_id"]

    overview = client.get(f"/api/mvp/core3/projects/{project_id}/overview")
    assert overview.status_code == 200, overview.text
    overview_body = overview.json()
    assert overview_body["latest_run_id"] == run_id
    assert overview_body["analyzed_sku_count"] == 5
    assert overview_body["confidence_distribution"]
    first_row = overview_body["rows"][0]
    assert {
        "target_sku_code",
        "brand",
        "model_name",
        "primary_battlefield",
        "direct_competitor",
        "pressure_competitor",
        "benchmark_potential_competitor",
        "confidence_level",
        "review_flag",
        "insufficient_reasons",
    }.issubset(first_row)

    csv_response = client.get(f"/api/mvp/core3/projects/{project_id}/export/core3.csv")
    assert csv_response.status_code == 200, csv_response.text
    assert "sku_competitor_core3.csv" in csv_response.headers["content-disposition"]
    csv_rows = list(csv.DictReader(StringIO(csv_response.text)))
    assert csv_rows
    assert csv_rows[0].keys() == {
        "target_sku_code",
        "role",
        "competitor_sku_code",
        "score",
        "reason",
        "confidence",
        "confidence_level",
        "review_flag",
        "insufficient_reasons",
    }
    assert {row["role"] for row in csv_rows} == {"direct", "pressure", "benchmark_potential"}

    jsonl_response = client.get(f"/api/mvp/core3/projects/{project_id}/export/evidence-cards.jsonl")
    assert jsonl_response.status_code == 200, jsonl_response.text
    assert "evidence_cards.jsonl" in jsonl_response.headers["content-disposition"]
    jsonl_rows = [json.loads(line) for line in jsonl_response.text.splitlines() if line.strip()]
    assert jsonl_rows
    assert all({"target_sku_code", "role", "competitor_sku_code", "evidence_card"}.issubset(row) for row in jsonl_rows)


def test_core3_semantic_scores_change_with_extracted_params_claims_and_comments(client, repo_root, tmp_path):
    baseline_project_id = _create_project(client, "彩电 Core3 语义基准项目")
    _import_samples(client, repo_root, baseline_project_id)
    baseline_run_id = _create_core3_run(client, baseline_project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, baseline_run_id)
        baseline_profile = _feature_profile(db, baseline_run_id, "TV00029115")
        baseline_premium = _battlefield_score(baseline_profile, "BF_PREMIUM_PICTURE", "semantic_score")
        baseline_gaming = _task_score(baseline_profile, "TASK_GAMING_ENTERTAINMENT")

    weak_project_id = _create_project(client, "彩电 Core3 语义弱信号项目")
    _import_sample_files(
        client,
        repo_root,
        weak_project_id,
        exclude={"sku_param", "sku_claim", "sku_comment"},
    )
    weak_params = tmp_path / "weak_params.csv"
    weak_params.write_text(
        "sku_code,raw_param_name,raw_param_value,raw_unit,source_channel,observed_at\n"
        "TV00029115,屏幕尺寸,85英寸,,JD,2026-05-25T00:00:00\n",
        encoding="utf-8",
    )
    weak_claims = tmp_path / "weak_claims.csv"
    weak_claims.write_text(
        "sku_code,claim_title,claim_text,claim_order,source_channel,observed_at\n"
        "TV00029115,基础介绍,日常观看电视,1,JD,2026-05-25T00:00:00\n",
        encoding="utf-8",
    )
    weak_comments = tmp_path / "weak_comments.csv"
    weak_comments.write_text(
        "sku_code,platform,comment_id,comment_text,rating,comment_time,dimension_1,dimension_2,dimension_3\n"
        "TV00029115,京东,W1,送货很快,5,2026-05-05T17:38:00,,,\n",
        encoding="utf-8",
    )
    for path, file_type in [
        (weak_params, "sku_param"),
        (weak_claims, "sku_claim"),
        (weak_comments, "sku_comment"),
    ]:
        _import_file(client, weak_project_id, path, file_type)
    weak_run_id = _create_core3_run(client, weak_project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, weak_run_id)
        weak_profile = _feature_profile(db, weak_run_id, "TV00029115")
        weak_premium = _battlefield_score(weak_profile, "BF_PREMIUM_PICTURE", "semantic_score")
        weak_gaming = _task_score(weak_profile, "TASK_GAMING_ENTERTAINMENT")

    assert baseline_premium > weak_premium
    assert baseline_gaming > weak_gaming


def test_core3_market_changes_affect_market_score_and_pressure_slot(client, repo_root, tmp_path):
    baseline_project_id = _create_project(client, "彩电 Core3 pressure 基准项目")
    _import_samples(client, repo_root, baseline_project_id)
    baseline_run_id = _create_core3_run(client, baseline_project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, baseline_run_id)
        baseline_profile = _feature_profile(db, baseline_run_id, "TV00029115")
        baseline_market_score = _battlefield_score(baseline_profile, "BF_LARGE_SCREEN_VALUE", "market_score")
        baseline_pressure = _competitor_result(db, baseline_run_id, "TV00029115", "pressure")

    changed_project_id = _create_project(client, "彩电 Core3 pressure 改市场项目")
    _import_sample_files(client, repo_root, changed_project_id, exclude={"market_fact"})
    changed_market = tmp_path / "pressure_market.csv"
    changed_market.write_text(
        "sku_code,period,period_type,channel_group,channel_type,channel_name,sales_volume,sales_amount,avg_price,promotion_flag\n"
        "TV00029115,2026W21,week,线上,专业电商,JD,3267,31725538,9710.91,false\n"
        "TV00010001,2026W21,week,线上,专业电商,JD,2800,26320000,9400,false\n"
        "TV00010002,2026W21,week,线上,专业电商,JD,10,49900,4990,true\n"
        "TV00010003,2026W21,week,线上,专业电商,JD,900,13491000,14990,false\n"
        "TV00010004,2026W21,week,线上,专业电商,JD,1200,17988000,14990,false\n",
        encoding="utf-8",
    )
    _import_file(client, changed_project_id, changed_market, "market_fact")
    changed_run_id = _create_core3_run(client, changed_project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, changed_run_id)
        changed_profile = _feature_profile(db, changed_run_id, "TV00029115")
        changed_market_score = _battlefield_score(changed_profile, "BF_LARGE_SCREEN_VALUE", "market_score")
        changed_pressure = _competitor_result(db, changed_run_id, "TV00029115", "pressure")

    assert baseline_market_score != changed_market_score
    assert baseline_pressure.component_scores["sales_strength"] > changed_pressure.component_scores["sales_strength"]
    assert baseline_pressure.score > changed_pressure.score


def test_core3_candidate_pool_excludes_target_and_non_empty_results_are_unique(client, repo_root):
    project_id = _create_project(client, "彩电 Core3 候选去重项目")
    _import_samples(client, repo_root, project_id)
    run_id = _create_core3_run(client, project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, run_id)
        candidates = db.execute(
            select(Core3CompetitorCandidate).where(
                Core3CompetitorCandidate.run_id == run_id,
                Core3CompetitorCandidate.target_sku_code == "TV00029115",
            )
        ).scalars().all()
        assert candidates
        assert all(row.candidate_sku_code != row.target_sku_code for row in candidates)
        results = db.execute(
            select(Core3CompetitorResult).where(
                Core3CompetitorResult.run_id == run_id,
                Core3CompetitorResult.target_sku_code == "TV00029115",
            )
        ).scalars().all()
        non_empty_codes = [row.competitor_sku_code for row in results if row.competitor_sku_code]
        assert len(non_empty_codes) == len(set(non_empty_codes))


def test_core3_no_qualified_candidate_writes_insufficient_role_results(client, tmp_path):
    project_id = _create_project(client, "彩电 Core3 无候选项目")
    _import_single_sku_inputs(client, tmp_path, project_id)
    run_id = _create_core3_run(client, project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, run_id)
        results = db.execute(
            select(Core3CompetitorResult).where(
                Core3CompetitorResult.run_id == run_id,
                Core3CompetitorResult.target_sku_code == "TVONLY001",
            )
        ).scalars().all()
        assert {row.role for row in results} == {"direct", "pressure", "benchmark_potential"}
        assert all(row.competitor_sku_code is None for row in results)
        assert all(row.review_flag for row in results)
        assert all("insufficient_comparable_pool" in row.insufficient_reasons for row in results)


def test_core3_market_profile_degrades_when_price_or_sales_missing(client, repo_root, tmp_path):
    project_id = _create_project(client, "彩电 Core3 缺量价项目")
    _import_sample_files(client, repo_root, project_id, exclude={"market_fact"})
    market_file = tmp_path / "missing_market.csv"
    market_file.write_text(
        "sku_code,period,period_type,channel_group,channel_type,channel_name,sales_volume,sales_amount,avg_price,promotion_flag\n"
        "TV00029115,2026W21,week,线上,专业电商,JD,,,9999,false\n",
        encoding="utf-8",
    )
    _import_file(client, project_id, market_file, "market_fact")

    run_id = _create_core3_run(client, project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, run_id)
        market = _market_profile(db, run_id, "TV00029115")
        assert market.price_wavg_12m == 9999
        assert market.price_latest == 9999
        assert market.sales_volume_12m is None
        assert "missing_sales" in market.missing_signals
        assert "missing_channel" in market.missing_signals
        assert market.confidence < 0.7


def test_core3_market_profile_computes_price_drop_and_sales_growth(client, repo_root, tmp_path):
    project_id = _create_project(client, "彩电 Core3 趋势项目")
    _import_sample_files(
        client,
        repo_root,
        project_id,
        exclude={"sku_param", "sku_claim", "sku_comment", "market_fact"},
    )
    trend_market = tmp_path / "trend_market.csv"
    trend_market.write_text(
        "sku_code,period,period_type,channel_group,channel_type,channel_name,sales_volume,sales_amount,avg_price,promotion_flag\n"
        "TV00029115,2026M01,month,线上,专业电商,JD,100,100000,1000,false\n"
        "TV00029115,2026M02,month,线上,专业电商,JD,100,100000,1000,false\n"
        "TV00029115,2026M03,month,线上,专业电商,JD,100,100000,1000,false\n"
        "TV00029115,2026M04,month,线上,专业电商,JD,200,160000,800,true\n"
        "TV00029115,2026M05,month,线上,专业电商,JD,200,160000,800,true\n"
        "TV00029115,2026M06,month,线上,专业电商,JD,200,160000,800,true\n",
        encoding="utf-8",
    )
    _import_file(client, project_id, trend_market, "market_fact")

    run_id = _create_core3_run(client, project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, run_id)
        market = _market_profile(db, run_id, "TV00029115")
        assert market.price_drop_rate_3m == 0.2
        assert market.sales_growth_3m == 1.0
        assert "insufficient_periods" not in market.missing_signals


def test_core3_sales_percentile_changes_when_sales_volume_changes(client, repo_root, tmp_path):
    baseline_project_id = _create_project(client, "彩电 Core3 基准销量项目")
    _import_samples(client, repo_root, baseline_project_id)
    baseline_run_id = _create_core3_run(client, baseline_project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, baseline_run_id)
        baseline = _market_profile(db, baseline_run_id, "TV00010003").sales_percentile

    changed_project_id = _create_project(client, "彩电 Core3 改销量项目")
    _import_sample_files(client, repo_root, changed_project_id, exclude={"market_fact"})
    changed_market = tmp_path / "changed_market.csv"
    changed_market.write_text(
        "sku_code,period,period_type,channel_group,channel_type,channel_name,sales_volume,sales_amount,avg_price,promotion_flag\n"
        "TV00029115,2026W21,week,线上,专业电商,JD,3267,31725538,9710.91,false\n"
        "TV00010001,2026W21,week,线上,专业电商,JD,2800,26320000,9400,false\n"
        "TV00010002,2026W21,week,线上,专业电商,JD,5200,25948000,4990,true\n"
        "TV00010003,2026W21,week,线上,专业电商,JD,9000,134910000,14990,false\n"
        "TV00010004,2026W21,week,线上,专业电商,JD,1200,17988000,14990,false\n",
        encoding="utf-8",
    )
    _import_file(client, changed_project_id, changed_market, "market_fact")
    changed_run_id = _create_core3_run(client, changed_project_id)
    with SessionLocal() as db:
        run_feature_extraction(db, changed_run_id)
        changed = _market_profile(db, changed_run_id, "TV00010003").sales_percentile

    assert baseline == 0.2
    assert changed == 1.0


def test_core3_feature_profile_without_comments_has_missing_reason_not_false_topics(client, repo_root):
    project_id = _create_project(client, "彩电 Core3 无评论项目")
    _import_sample_files(client, repo_root, project_id, exclude={"sku_comment"})
    run_id = _create_core3_run(client, project_id)

    with SessionLocal() as db:
        run_feature_extraction(db, run_id)
        profile = db.execute(
            select(Core3SkuFeatureProfile).where(
                Core3SkuFeatureProfile.run_id == run_id,
                Core3SkuFeatureProfile.sku_code == "TV00029115",
            )
        ).scalar_one()
        assert profile.comment_topics == []
        assert "TV00029115:missing_comment_topics" in profile.missing_signals
        assert all(item["comment_score"] is None for item in profile.claim_activations)
        assert profile.extraction_diagnostics["missing_signals"] == profile.missing_signals


def test_core3_get_or_create_evidence_deduplicates_same_raw_ref(client, repo_root):
    project_id = _create_project(client, "彩电 Core3 证据去重项目")
    _import_samples(client, repo_root, project_id)
    with SessionLocal() as db:
        bundle = load_project_input(db, project_id)
        row = next(item for item in bundle.params if item.sku_code == "TV00029115")
        first = get_or_create_evidence(
            db,
            project_id=project_id,
            category_code="TV",
            sku_code=row.sku_code,
            source_type="raw_param",
            source_file_id=row.source_file_id,
            raw_row_id=row.raw_row_id,
            field_name=row.raw_param_name,
            raw_value=row.raw_param_value,
            normalized_value={"param_code": "screen_size_inch", "value": 85},
            source_ref={"table": "raw_sku_param", "parser": "inch"},
            confidence=0.95,
        )
        second = get_or_create_evidence(
            db,
            project_id=project_id,
            category_code="TV",
            sku_code=row.sku_code,
            source_type="raw_param",
            source_file_id=row.source_file_id,
            raw_row_id=row.raw_row_id,
            field_name=row.raw_param_name,
            raw_value=row.raw_param_value,
            normalized_value={"param_code": "screen_size_inch", "value": 85},
            source_ref={"table": "raw_sku_param", "parser": "inch"},
            confidence=0.95,
        )
        assert first.evidence_id == second.evidence_id


def _create_project(client, name: str) -> str:
    response = client.post(
        "/projects",
        json={"name": name, "category_code": "TV", "description": "Core3 自动化测试"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project_id"]


def _import_samples(client, repo_root, project_id: str) -> None:
    _import_sample_files(client, repo_root, project_id)


def _import_sample_files(client, repo_root, project_id: str, exclude: set[str] | None = None) -> None:
    exclude = exclude or set()
    for path, file_type in SAMPLE_FILES:
        if file_type not in exclude:
            _import_file(client, project_id, repo_root / path, file_type)


def _import_file(client, project_id: str, path, file_type: str) -> None:
    response = client.post(
        f"/projects/{project_id}/imports",
        json={"file_path": str(path), "file_type": file_type},
    )
    assert response.status_code == 200, response.text


def _create_core3_run(client, project_id: str) -> str:
    response = client.post(f"/api/mvp/core3/projects/{project_id}/run", json={"batch": True})
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _import_goal_d_extra_inputs(client, tmp_path, project_id: str) -> None:
    sku_codes = ["TV00029115", "TV00010001", "TV00010002", "TV00010003", "TV00010004"]
    params_file = tmp_path / "goal_d_extra_params.csv"
    params_file.write_text(
        "sku_code,raw_param_name,raw_param_value,raw_unit,source_channel,observed_at\n"
        + "\n".join(f"{sku_code},黑曜屏等级,Pro,,JD,2026-05-25T00:00:00" for sku_code in sku_codes)
        + "\n",
        encoding="utf-8",
    )
    claims_file = tmp_path / "goal_d_extra_claims.csv"
    claims_file.write_text(
        "sku_code,claim_title,claim_text,claim_order,source_channel,observed_at\n"
        + "\n".join(
            f"{sku_code},黑曜体验,黑曜晶彩Pro 星河控影体验,{index},JD,2026-05-25T00:00:00"
            for index, sku_code in enumerate(sku_codes, start=10)
        )
        + "\n",
        encoding="utf-8",
    )
    comments_file = tmp_path / "goal_d_extra_comments.csv"
    comments_file.write_text(
        "sku_code,platform,comment_id,comment_text,rating,comment_time,dimension_1,dimension_2,dimension_3\n"
        + "\n".join(
            f"{sku_code},京东,GD{index},包装气味明显,4,2026-05-09T13:00:00,,,"
            for index, sku_code in enumerate(sku_codes, start=1)
        )
        + "\n",
        encoding="utf-8",
    )
    for path, file_type in [
        (params_file, "sku_param"),
        (claims_file, "sku_claim"),
        (comments_file, "sku_comment"),
    ]:
        response = client.post(
            f"/projects/{project_id}/imports",
            json={"file_path": str(path), "file_type": file_type},
        )
        assert response.status_code == 200, response.text


def _competitor_result_count() -> int:
    with SessionLocal() as db:
        return int(db.execute(select(func.count()).select_from(SkuCompetitorResult)).scalar_one())


def _model_count(model: type) -> int:
    with SessionLocal() as db:
        return int(db.execute(select(func.count()).select_from(model)).scalar_one())


def _core3_result_counts() -> dict[str, int]:
    return {
        "market_profiles": _model_count(Core3SkuMarketProfile),
        "feature_profiles": _model_count(Core3SkuFeatureProfile),
        "competitor_candidates": _model_count(Core3CompetitorCandidate),
        "competitor_results": _model_count(Core3CompetitorResult),
        "evidence_cards": _model_count(Core3EvidenceCard),
    }


def _market_profile(db, run_id: str, sku_code: str) -> Core3SkuMarketProfile:
    return db.execute(
        select(Core3SkuMarketProfile).where(
            Core3SkuMarketProfile.run_id == run_id,
            Core3SkuMarketProfile.sku_code == sku_code,
        )
    ).scalar_one()


def _feature_profile(db, run_id: str, sku_code: str) -> Core3SkuFeatureProfile:
    return db.execute(
        select(Core3SkuFeatureProfile).where(
            Core3SkuFeatureProfile.run_id == run_id,
            Core3SkuFeatureProfile.sku_code == sku_code,
        )
    ).scalar_one()


def _competitor_result(db, run_id: str, sku_code: str, role: str) -> Core3CompetitorResult:
    return db.execute(
        select(Core3CompetitorResult).where(
            Core3CompetitorResult.run_id == run_id,
            Core3CompetitorResult.target_sku_code == sku_code,
            Core3CompetitorResult.role == role,
        )
    ).scalar_one()


def _task_score(profile: Core3SkuFeatureProfile, task_code: str) -> float:
    return next((item["score"] for item in profile.task_scores if item["task_code"] == task_code), 0.0)


def _battlefield_score(profile: Core3SkuFeatureProfile, battlefield_code: str, score_key: str) -> float:
    return next(
        (
            item.get(score_key) or 0.0
            for item in profile.battlefield_scores
            if item["battlefield_code"] == battlefield_code
        ),
        0.0,
    )


def _import_single_sku_inputs(client, tmp_path, project_id: str) -> None:
    master = tmp_path / "single_master.csv"
    master.write_text(
        "sku_code,brand,model_name,series,category_code,category_name,launch_date,product_url\n"
        "TVONLY001,海信,Only 85,Only,TV,彩电,,\n",
        encoding="utf-8",
    )
    market = tmp_path / "single_market.csv"
    market.write_text(
        "sku_code,period,period_type,channel_group,channel_type,channel_name,sales_volume,sales_amount,avg_price,promotion_flag\n"
        "TVONLY001,2026W21,week,线上,专业电商,JD,100,900000,9000,false\n",
        encoding="utf-8",
    )
    params = tmp_path / "single_params.csv"
    params.write_text(
        "sku_code,raw_param_name,raw_param_value,raw_unit,source_channel,observed_at\n"
        "TVONLY001,屏幕尺寸,85英寸,,JD,2026-05-25T00:00:00\n"
        "TVONLY001,Mini LED,支持,,JD,2026-05-25T00:00:00\n",
        encoding="utf-8",
    )
    claims = tmp_path / "single_claims.csv"
    claims.write_text(
        "sku_code,claim_title,claim_text,claim_order,source_channel,observed_at\n"
        "TVONLY001,画质,Mini LED 大屏电视,1,JD,2026-05-25T00:00:00\n",
        encoding="utf-8",
    )
    comments = tmp_path / "single_comments.csv"
    comments.write_text(
        "sku_code,platform,comment_id,comment_text,rating,comment_time,dimension_1,dimension_2,dimension_3\n"
        "TVONLY001,京东,S1,画面不错,5,2026-05-05T17:38:00,,,\n",
        encoding="utf-8",
    )
    for path, file_type in [
        (master, "sku_master"),
        (market, "market_fact"),
        (params, "sku_param"),
        (claims, "sku_claim"),
        (comments, "sku_comment"),
    ]:
        _import_file(client, project_id, path, file_type)


def _assert_unique(values: list[str]) -> None:
    assert len(values) == len(set(values))


def _collect_forbidden_keys(value, forbidden: set[str], path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in forbidden:
                found.append(child_path)
            found.extend(_collect_forbidden_keys(child, forbidden, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_collect_forbidden_keys(child, forbidden, f"{path}[{index}]"))
    return found
