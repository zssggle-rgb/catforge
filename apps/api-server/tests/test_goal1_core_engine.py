import copy
import json

from app.services.goal1_analysis_service import load_default_rule_sets
from app.services.goal1_rule_engine import RuleEvaluationContext, evaluate_rule_set


def test_goal1_rule_validation_rejects_unknown_operator(client):
    payload = {
        "rule_set_id": "bad_tv_claim_rules",
        "category": "TV",
        "rule_type": "claim_activation",
        "version": "1.0.0",
        "rules": [
            {
                "rule_id": "BAD_OPERATOR",
                "output_code": "CLAIM_BAD",
                "conditions": {"feature": "param.mini_led_flag", "op": "near", "value": True},
                "score": {"weights": [{"feature": "param.mini_led_flag", "points": 100}]},
            }
        ],
    }

    response = client.post("/api/rule-sets/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert "near" in " ".join(body["errors"])


def test_goal1_threshold_change_changes_claim_activation():
    claim_rule, _, _, _ = load_default_rule_sets()
    mini_led_rule = copy.deepcopy(claim_rule)
    mini_led_rule["rules"] = [item for item in mini_led_rule["rules"] if item["rule_id"] == "CLAIM_MINI_LED"]
    context = RuleEvaluationContext(
        features={
            "param": {"mini_led_flag": True},
            "claim_text": "",
            "comment_topic": {},
            "market": {},
            "claim": {},
            "task": {},
            "battlefield": {},
            "derived": {},
        },
        evidence_by_feature={"param.mini_led_flag": ["evidence-param-mini-led"]},
    )

    baseline = evaluate_rule_set(mini_led_rule, context)[0]
    mini_led_rule["rules"][0]["thresholds"]["activated"] = 80
    changed = evaluate_rule_set(mini_led_rule, context)[0]

    assert baseline.score == 70
    assert baseline.matched is True
    assert changed.score == 70
    assert changed.matched is False


def test_goal1_fixture_end_to_end_competitors_evaluation_and_calibration(client, repo_root):
    project_id = _create_project(client)
    expected = json.loads(
        (repo_root / "examples/goal1/expected/goal1_expected_min.json").read_text(encoding="utf-8")
    )

    run_response = client.post(
        f"/api/projects/{project_id}/run-analysis",
        json={"target_sku_code": expected["target_sku_code"]},
    )
    assert run_response.status_code == 200, run_response.text
    run = run_response.json()
    assert run["status"] == "completed"
    assert run["counts"]["sku_count"] == 8
    assert run["counts"]["competitor_results"] >= 3

    fetched_run = client.get(f"/api/projects/{project_id}/analysis-runs/{run['run_id']}")
    assert fetched_run.status_code == 200
    assert fetched_run.json()["run_id"] == run["run_id"]

    analysis_response = client.get(
        f"/api/projects/{project_id}/sku/{expected['target_sku_code']}/analysis"
    )
    assert analysis_response.status_code == 200, analysis_response.text
    analysis = analysis_response.json()
    claim_codes = {item["claim_code"] for item in analysis["claim_results"]}
    battlefield_codes = {item["battlefield_code"] for item in analysis["battlefield_scores"]}
    assert set(expected["must_activate_claims"]).issubset(claim_codes)
    assert set(expected["must_enter_battlefields"]).issubset(battlefield_codes)

    for item in analysis["claim_results"] + analysis["task_scores"] + analysis["battlefield_scores"]:
        assert item["evidence_ids"]
        assert item["confidence"] > 0
        assert item["rule_version"]
        assert item["asset_version"]
        assert item["review_status"]

    competitors_response = client.get(
        f"/api/projects/{project_id}/sku/{expected['target_sku_code']}/competitors"
    )
    assert competitors_response.status_code == 200, competitors_response.text
    competitors = competitors_response.json()["items"]
    competitor_types = {item["competitor_type"] for item in competitors}
    assert set(expected["must_have_competitor_types"]).issubset(competitor_types)
    for competitor in competitors:
        assert competitor["component_scores"]
        assert competitor["evidence_ids"]
        assert competitor["confidence"] > 0
        assert competitor["rule_version"]
        assert competitor["asset_version"]
        assert competitor["review_status"]

    first_evidence_id = competitors[0]["evidence_ids"][0]
    evidence_response = client.get(f"/api/projects/{project_id}/evidence/{first_evidence_id}")
    assert evidence_response.status_code == 200, evidence_response.text
    assert evidence_response.json()["source_ref"]

    import_response = client.post(f"/api/projects/{project_id}/gold-labels/import", json={})
    assert import_response.status_code == 200, import_response.text
    assert import_response.json()["imported"] == 7

    evaluation_response = client.post(f"/api/projects/{project_id}/evaluation/run")
    assert evaluation_response.status_code == 200, evaluation_response.text
    evaluation = evaluation_response.json()
    assert evaluation["gold_label_count"] == 7
    assert evaluation["metrics"]["macro_f1"] >= 0.85
    assert evaluation["metrics"]["competitor"]["type_accuracy"] >= 0.66

    get_evaluation = client.get(
        f"/api/projects/{project_id}/evaluation/{evaluation['evaluation_id']}"
    )
    assert get_evaluation.status_code == 200
    assert get_evaluation.json()["evaluation_id"] == evaluation["evaluation_id"]

    calibration_response = client.post(f"/api/projects/{project_id}/calibration/run")
    assert calibration_response.status_code == 200, calibration_response.text
    calibration = calibration_response.json()
    assert calibration["status"] == "draft_candidate"
    assert calibration["candidate_rule_patch"]
    assert calibration["before_metrics"]
    assert calibration["after_metrics"]


def _create_project(client) -> str:
    response = client.post(
        "/projects",
        json={"name": "Goal1 彩电核心引擎验收", "category_code": "TV", "description": "自动化测试"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project_id"]
