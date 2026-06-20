import pytest

from app.services.core3_real_data.api_response_guardrail import ApiResponseGuardrail, ApiResponseGuardrailError
from app.services.core3_real_data.fixtures import load_85e7q_fixture_set, load_local_validation_fixture_set


def test_acceptance_local_fixture_covers_final_business_scenarios():
    fixture = load_local_validation_fixture_set()
    summary = fixture.baseline_summary()
    scenarios = fixture.scenario_by_sku()

    assert summary["target_sku_code"] == "TV900001"
    assert summary["row_counts"] == {
        "week_sales_data": 36,
        "attribute_data": 60,
        "selling_points_data": 36,
        "comment_data": 180,
    }
    assert summary["core3_expected"] == ["TV900002", "TV900003", "TV900004"]
    assert summary["excluded_expected"] == ["TV900005", "TV900006"]
    assert scenarios["TV900004"]["brand"] == "海信"
    assert scenarios["TV900004"]["role_expected"] == "same_brand_upgrade_competitor"
    assert "TV900004" in summary["core3_expected"]
    assert scenarios["TV900006"]["role_expected"] == "negative_sample"
    assert all(len(item["claims"]) >= 6 for item in scenarios.values())
    assert all(count >= 30 for count in summary["per_sku_comment_count"].values())


def test_acceptance_local_fixture_keeps_method_labels_out_of_raw_rows():
    fixture = load_local_validation_fixture_set()
    raw_text = str(fixture.raw_table_rows())

    assert "front_attack_competitor" not in raw_text
    assert "same_brand_upgrade_competitor" not in raw_text
    assert "negative_sample" not in raw_text
    assert "expected_competitor_set" not in raw_text


def test_acceptance_85e7q_fixture_preserves_selling_point_data_gap():
    fixture = load_85e7q_fixture_set()
    summary = fixture.baseline_summary()

    assert summary["market_has_target"] is True
    assert summary["attribute_has_target"] is True
    assert summary["comment_has_target"] is True
    assert summary["selling_points_has_target"] is False
    assert fixture.same_brand_candidate_codes()


def test_acceptance_api_guardrail_blocks_internal_display_terms():
    guardrail = ApiResponseGuardrail()
    blocked_payloads = [
        {"data_scope_note_cn": "当前样例数据内", "summary_cn": "来自 market_aggregate 的内部口径"},
        {"data_scope_note_cn": "当前样例数据内", "summary_cn": "comment_signal 命中后生成"},
        {"data_scope_note_cn": "当前样例数据内", "summary_cn": "状态 review_required"},
        {"data_scope_note_cn": "当前样例数据内", "display_payload_json": {}},
        {"data_scope_note_cn": "当前样例数据内", "summary_cn": "提示词生成过程"},
    ]

    for payload in blocked_payloads:
        with pytest.raises(ApiResponseGuardrailError):
            guardrail.validate_business_response(payload)


def test_acceptance_api_guardrail_allows_controlled_codes_for_frontend_mapping():
    payload = {
        "project_id": "d8d2245b-358b-4a64-95cc-9d7f2341bd26",
        "category_code": "TV",
        "target": {"sku_code": "TV900001", "target_sku_code": "TV900001"},
        "release_status": {
            "status_code": "review_required",
            "status_name_cn": "需复核",
            "data_scope_note_cn": "当前样例数据内",
        },
        "core_competitors": [
            {
                "competitor_sku_code": "TV900002",
                "role_code": "direct_fight",
                "one_sentence_reason_cn": "同尺寸、同价格带、同价值战场，当前证据可支撑正面对打判断。",
            }
        ],
        "data_quality_note_cn": "当前样例数据内，后续接入 205 全量数据后复核。",
    }

    ApiResponseGuardrail().validate_business_response(payload)
