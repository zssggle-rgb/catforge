from app.services.core3_real_data.constants import (
    CORE3_TARGET_BRAND_85E7Q,
    CORE3_TARGET_MODEL_85E7Q,
    CORE3_TARGET_SKU_85E7Q,
)
from app.services.core3_real_data.fixtures import (
    CORE3_REAL_DATA_FIXTURE_DIR,
    EXPECTED_BASELINE_FIXTURE,
    load_85e7q_fixture_set,
    load_json_fixture,
    load_local_validation_fixture_set,
)


def test_85e7q_fixture_files_exist_and_load():
    assert CORE3_REAL_DATA_FIXTURE_DIR.exists()

    expected = load_json_fixture(EXPECTED_BASELINE_FIXTURE)

    assert expected["target_sku_code"] == CORE3_TARGET_SKU_85E7Q
    assert expected["target_model"] == CORE3_TARGET_MODEL_85E7Q
    assert expected["target_brand"] == CORE3_TARGET_BRAND_85E7Q


def test_85e7q_fixture_covers_required_input_domains():
    fixture = load_85e7q_fixture_set()

    assert fixture.target_rows(fixture.week_sales_data)
    assert fixture.target_rows(fixture.attribute_data)
    assert fixture.target_rows(fixture.comment_data)
    assert not fixture.target_rows(fixture.selling_points_data)


def test_85e7q_fixture_keeps_same_brand_candidates_available():
    fixture = load_85e7q_fixture_set()

    assert fixture.same_brand_candidate_codes()
    assert all(code != CORE3_TARGET_SKU_85E7Q for code in fixture.same_brand_candidate_codes())


def test_85e7q_fixture_marks_online_channel_limits():
    summary = load_85e7q_fixture_set().baseline_summary()

    assert summary["channels"] == ["线上"]
    assert summary["platform_types"] == ["专业电商", "平台电商"]
    assert summary["weeks"] == ["26W01", "26W23"]


def test_85e7q_fixture_covers_missing_like_values_and_duplicate_comments():
    fixture = load_85e7q_fixture_set()
    summary = fixture.baseline_summary()

    assert fixture.missing_like_attribute_values() == {None, "", "-", "unknown"}
    assert summary["duplicate_comment_ids"] == ["CMT-85E7Q-003"]


def test_85e7q_fixture_baseline_does_not_contain_final_business_conclusion():
    fixture = load_85e7q_fixture_set()
    expected = fixture.expected_baseline

    assert expected["not_expected"]["final_competitor_codes"] == []
    assert expected["not_expected"]["business_conclusion"] is None


def test_85e7q_fixture_summary_is_stably_hashable():
    first_summary = load_85e7q_fixture_set().baseline_summary()
    second_summary = load_85e7q_fixture_set().baseline_summary()

    assert first_summary["fixture_hash"].startswith("sha256:fixture-85e7q-v1:")
    assert first_summary["fixture_hash"] == second_summary["fixture_hash"]


def test_local_validation_fixture_supports_downstream_module_validation():
    fixture = load_local_validation_fixture_set()
    summary = fixture.baseline_summary()

    assert summary["target_sku_code"] == "TV900001"
    assert summary["sku_count"] == 6
    assert summary["core3_expected"] == ["TV900002", "TV900003", "TV900004"]
    assert summary["excluded_expected"] == ["TV900005", "TV900006"]
    assert summary["row_counts"] == {
        "week_sales_data": 36,
        "attribute_data": 60,
        "selling_points_data": 36,
        "comment_data": 180,
    }
    assert all(count >= 30 for count in summary["per_sku_comment_count"].values())
    assert summary["roles"]["TV900002"] == "front_attack_competitor"
    assert summary["roles"]["TV900004"] == "same_brand_upgrade_competitor"
    assert summary["roles"]["TV900006"] == "negative_sample"


def test_local_validation_fixture_expands_to_raw_source_table_shapes():
    raw_rows = load_local_validation_fixture_set().raw_table_rows()

    assert set(raw_rows) == {"week_sales_data", "attribute_data", "selling_points_data", "comment_data"}
    assert {"model_code", "brand", "model", "date_value", "sales_volume", "avg_price"} <= set(
        raw_rows["week_sales_data"][0]
    )
    assert {"model_code", "attr_name", "attr_value"} <= set(raw_rows["attribute_data"][0])
    assert {"model_code", "variable", "selling_point"} <= set(raw_rows["selling_points_data"][0])
    assert {
        "model_code",
        "comment_id",
        "comment_content",
        "comments_segments",
        "primary_dim",
        "secondary_dim",
        "sentiment",
    } <= set(raw_rows["comment_data"][0])


def test_local_validation_fixture_keeps_expected_business_roles_outside_raw_rows():
    fixture = load_local_validation_fixture_set()
    raw_text = str(fixture.raw_table_rows())

    assert "front_attack_competitor" not in raw_text
    assert "same_brand_upgrade_competitor" not in raw_text
    assert "negative_sample" not in raw_text
    assert fixture.baseline_summary()["fixture_hash"].startswith("sha256:fixture-local-validation-v1:")
