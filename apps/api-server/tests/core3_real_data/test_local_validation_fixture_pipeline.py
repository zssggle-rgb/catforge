import re
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import core3_real_data
from app.core.database import get_db
from app.models import entities
from app.services.core3_real_data.constants import CORE3_M11_7_RULE_VERSION
from app.services.core3_real_data.fixtures import load_local_validation_fixture_set


PROJECT_ID = "core3_local_validation"


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    connection = engine.connect()
    with connection.begin():
        entities.Base.metadata.create_all(bind=connection)
        create_raw_source_tables(connection)
    session = Session(bind=connection)
    seed_raw_tables(session)
    return session


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(core3_real_data.router)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def create_raw_source_tables(connection) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE week_sales_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                date_value TEXT,
                channel TEXT,
                platform TEXT,
                sales_volume INTEGER,
                sales_amount NUMERIC,
                avg_price NUMERIC,
                write_time TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE attribute_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                attr_name TEXT,
                attr_value TEXT,
                write_time TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE selling_points_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                variable TEXT,
                selling_point TEXT,
                write_time TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE comment_data (
                id INTEGER PRIMARY KEY,
                model_code TEXT,
                category TEXT,
                brand TEXT,
                model TEXT,
                platform TEXT,
                url_id TEXT,
                comment_id TEXT,
                comment_time TEXT,
                comment_content TEXT,
                comments_segments TEXT,
                primary_dim TEXT,
                secondary_dim TEXT,
                third_dim TEXT,
                sentiment TEXT,
                write_time TIMESTAMP
            )
            """
        )
    )


def seed_raw_tables(session: Session) -> None:
    fixture = load_local_validation_fixture_set()
    raw_rows = fixture.raw_table_rows()
    session.add(
        entities.CategoryProject(
            project_id=PROJECT_ID,
            name="Core3 Local Validation",
            category_code="TV",
        )
    )
    session.flush()

    for row in raw_rows["week_sales_data"]:
        session.execute(
            text(
                """
                INSERT INTO week_sales_data (
                    id, model_code, category, brand, model, date_value, channel, platform,
                    sales_volume, sales_amount, avg_price, write_time
                ) VALUES (
                    :id, :model_code, :category, :brand, :model, :date_value, :channel,
                    :platform, :sales_volume, :sales_amount, :avg_price, :write_time
                )
                """
            ),
            row,
        )
    for row in raw_rows["attribute_data"]:
        session.execute(
            text(
                """
                INSERT INTO attribute_data (
                    id, model_code, category, brand, model, attr_name, attr_value, write_time
                ) VALUES (
                    :id, :model_code, :category, :brand, :model, :attr_name,
                    :attr_value, :write_time
                )
                """
            ),
            row,
        )
    for row in raw_rows["selling_points_data"]:
        session.execute(
            text(
                """
                INSERT INTO selling_points_data (
                    id, model_code, category, brand, model, variable, selling_point, write_time
                ) VALUES (
                    :id, :model_code, :category, :brand, :model, :variable,
                    :selling_point, :write_time
                )
                """
            ),
            row,
        )
    for row in raw_rows["comment_data"]:
        session.execute(
            text(
                """
                INSERT INTO comment_data (
                    id, model_code, category, brand, model, platform, url_id, comment_id,
                    comment_time, comment_content, comments_segments, primary_dim,
                    secondary_dim, third_dim, sentiment, write_time
                ) VALUES (
                    :id, :model_code, :category, :brand, :model, :platform, :url_id,
                    :comment_id, :comment_time, :comment_content, :comments_segments,
                    :primary_dim, :secondary_dim, :third_dim, :sentiment, :write_time
                )
                """
            ),
            row,
        )
    session.commit()


def test_local_validation_fixture_runs_through_m00_to_m08():
    session = make_session()
    client = make_client(session)

    m00_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/source-batches/register",
        json={
            "batch_type": "full",
            "source_tables": ["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
        },
    )
    assert m00_response.status_code == 200
    m00_payload = m00_response.json()
    batch_id = m00_payload["summary_json"]["batch_id"]
    assert m00_payload["input_count"] == 312
    assert m00_payload["summary_json"]["impacted_sku_count"] == 6

    m01_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/cleaning/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m01_response.status_code == 200
    m01_payload = m01_response.json()
    assert m01_payload["summary_json"]["clean_counts"]["sku"] == 6
    assert m01_payload["summary_json"]["clean_counts"]["claim"] == 36
    assert m01_payload["summary_json"]["clean_counts"]["comment"] == 180

    m02_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/evidence/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m02_response.status_code == 200
    m02_payload = m02_response.json()
    assert m02_payload["summary_json"]["partition_strategy"] == "sku_partition_v1"
    assert m02_payload["summary_json"]["partition_count"] == 6
    assert m02_payload["summary_json"]["evidence_counts"]["by_type"]["comment_raw"] == 30
    assert m02_payload["summary_json"]["evidence_counts"]["by_type"]["promo_raw"] == 36
    persist_module_run_result(session, batch_id, m02_payload)

    m03_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/params/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m03_response.status_code == 200, m03_response.json()
    m03_payload = m03_response.json()
    assert m03_payload["module_code"] == "M03"
    assert m03_payload["summary_json"]["sku_profile_count"] == 6
    assert m03_payload["summary_json"]["param_value_count"] > 0

    m04a_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/claims/base/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m04a_response.status_code == 200, m04a_response.json()
    m04a_payload = m04a_response.json()
    assert m04a_payload["module_code"] == "M04a"
    assert m04a_payload["summary_json"]["source_status_count"] == 6
    assert m04a_payload["summary_json"]["activation_base_count"] > 0

    m05_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/comments/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m05_response.status_code == 200, m05_response.json()
    m05_payload = m05_response.json()
    assert m05_payload["summary_json"]["sku_count"] == 4
    assert m05_payload["summary_json"]["comment_unit_count"] >= 30
    assert m05_payload["summary_json"]["evidence_atom_count"] >= 30
    assert m05_payload["summary_json"]["downstream_ready_sku_count"] >= 4

    m06_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/comments/signals/run",
        json={"run_id": "local-fixture-run", "sku_batch_size": 2},
    )
    assert m06_response.status_code == 200, m06_response.json()
    m06_payload = m06_response.json()
    assert m06_payload["module_code"] == "M06"
    assert m06_payload["summary_json"]["sku_count"] == 4
    assert m06_payload["summary_json"]["candidate_count"] > 0
    assert m06_payload["summary_json"]["downstream_signal_count"] > 0
    assert m06_payload["summary_json"]["sku_profile_count"] == 4
    assert m06_payload["summary_json"]["execution_mode"] == "sku_batch"
    assert m06_payload["summary_json"]["sku_batch_size"] == 2
    assert m06_payload["summary_json"]["batch_count"] == 2
    assert "M06 生成评论下游信号" in m06_payload["summary_json"]["boundary_note"]

    m04b_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/claims/comment-enhancement/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m04b_response.status_code == 200, m04b_response.json()
    m04b_payload = m04b_response.json()
    assert m04b_payload["module_code"] == "M04b"
    assert m04b_payload["summary_json"]["sku_count"] == 6
    assert m04b_payload["summary_json"]["validation_count"] > 0
    assert m04b_payload["summary_json"]["activation_count"] > 0
    assert "不生成任务、客群、战场或竞品结论" in m04b_payload["summary_json"]["boundary_note"]

    activations_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/claim-activations"
    )
    assert activations_response.status_code == 200
    activations_payload = activations_response.json()
    assert activations_payload["total"] > 0
    assert any(item["comment_signal_ids"] for item in activations_payload["items"])
    assert all("business_note_cn" in item for item in activations_payload["items"])
    assert all(
        item["activation_basis"] != "comment_enhanced"
        for item in activations_payload["items"]
        if item["m04b_claim_type"] == "technical_hard"
    )

    validations_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/claim-comment-validations"
    )
    assert validations_response.status_code == 200
    validations_payload = validations_response.json()
    assert validations_payload["total"] > 0
    assert any(item["comment_effect"] in {"enhance", "neutral", "weaken"} for item in validations_payload["items"])

    signal_profiles_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/comments/signals/profiles"
    )
    assert signal_profiles_response.status_code == 200
    signal_profiles_payload = signal_profiles_response.json()
    assert signal_profiles_payload["total"] == 4
    target_signal_profile = next(
        item for item in signal_profiles_payload["items"] if item["sku_code"] == "TV900001"
    )
    assert target_signal_profile["claim_validation_ready"] is True
    assert target_signal_profile["task_cue_ready"] is True
    assert target_signal_profile["battlefield_support_ready"] is True

    signals_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/comments/signals",
        params={"sku_code": "TV900001", "signal_type": "task_cue"},
    )
    assert signals_response.status_code == 200
    signals_payload = signals_response.json()
    assert signals_payload["total"] > 0
    assert {item["signal_type"] for item in signals_payload["items"]} == {"task_cue"}
    assert any(item["target_code_hint"].startswith("TASK_") for item in signals_payload["items"])

    profiles_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/comments/profiles"
    )
    assert profiles_response.status_code == 200
    profiles_payload = profiles_response.json()
    assert profiles_payload["total"] == 4
    assert {item["sku_code"] for item in profiles_payload["items"]} >= {
        "TV900001",
        "TV900004",
        "TV900005",
        "TV900006",
    }

    m07_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/market/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m07_response.status_code == 200, m07_response.json()
    m07_payload = m07_response.json()
    assert m07_payload["module_code"] == "M07"
    assert m07_payload["summary_json"]["processed_sku_count"] == 6
    assert m07_payload["summary_json"]["market_profile_count"] == 30
    assert m07_payload["summary_json"]["market_signal_count"] > 0
    assert m07_payload["summary_json"]["comparable_pool_count"] > 0
    assert m07_payload["summary_json"]["pool_member_count"] > 0
    assert "不生成任务、客群、战场、候选或竞品结论" in m07_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m07_payload["summary_json"])

    market_profiles_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/market-profiles"
    )
    assert market_profiles_response.status_code == 200
    market_profiles_payload = market_profiles_response.json()
    assert market_profiles_payload["total"] == 5
    assert_no_12m_keys(market_profiles_payload)
    target_full_profile = next(
        item
        for item in market_profiles_payload["items"]
        if item["analysis_window"] == "full_observed_window"
    )
    assert target_full_profile["brand_name"] == "海信"
    assert target_full_profile["size_segment"] == "85"
    assert target_full_profile["screen_size_inch"] == 85
    assert target_full_profile["price_wavg"] == 6999
    assert target_full_profile["sales_volume_total"] == 892
    assert target_full_profile["main_channel_type"] == "线上"
    assert target_full_profile["main_platform"] == "专业电商"
    assert "observed_window_less_than_52w" in target_full_profile["quality_flags"]
    assert "市场" in target_full_profile["business_note_cn"] or "观察期" in target_full_profile["business_note_cn"]

    market_signals_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/market-signals",
        params={"analysis_window": "full_observed_window"},
    )
    assert market_signals_response.status_code == 200
    market_signals_payload = market_signals_response.json()
    assert market_signals_payload["total"] > 0
    assert_no_12m_keys(market_signals_payload)
    assert all(item["sku_market_profile_id"] for item in market_signals_payload["items"])
    assert any(item["signal_code"] == "PLATFORM_OVERLAP_STRONG" for item in market_signals_payload["items"])
    assert all("不能单独决定任务、客群、战场或竞品" in item["business_note_cn"] for item in market_signals_payload["items"])

    pools_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/comparable-pools",
        params={"analysis_window": "full_observed_window"},
    )
    assert pools_response.status_code == 200
    pools_payload = pools_response.json()
    assert pools_payload["total"] >= 4
    assert_no_12m_keys(pools_payload)
    pool_types = {item["pool_type"] for item in pools_payload["items"]}
    assert {"same_size", "size_price_band", "platform_overlap", "market_active"}.issubset(pool_types)
    same_size_pool = next(item for item in pools_payload["items"] if item["pool_type"] == "same_size")
    assert same_size_pool["target_included"] is True
    assert set(same_size_pool["candidate_sku_codes"]) >= {"TV900001", "TV900002", "TV900003", "TV900004"}
    assert "TV900004" in same_size_pool["candidate_sku_codes"]
    assert "不等同最终竞品列表" in same_size_pool["business_note_cn"]

    members_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/market-pools/{same_size_pool['pool_id']}/members"
    )
    assert members_response.status_code == 200
    members_payload = members_response.json()
    assert members_payload["total"] >= 4
    assert_no_12m_keys(members_payload)
    assert any(item["is_target_self"] for item in members_payload["items"])
    same_brand_member = next(item for item in members_payload["items"] if item["member_sku_code"] == "TV900004")
    assert same_brand_member["member_brand_name"] == "海信"
    assert same_brand_member["size_relation"] == "same"
    assert same_brand_member["relation_strength"] > 0
    assert "同尺寸" in same_brand_member["business_note_cn"]
    assert "价位关系" in same_brand_member["business_note_cn"]

    m08_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/sku-signals/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m08_response.status_code == 200, m08_response.json()
    m08_payload = m08_response.json()
    assert m08_payload["module_code"] == "M08"
    assert m08_payload["summary_json"]["sku_signal_profile_count"] == 6
    assert m08_payload["summary_json"]["evidence_matrix_count"] >= 6 * 21
    assert m08_payload["summary_json"]["downstream_feature_view_count"] == 6 * 10
    assert m08_payload["summary_json"]["ready_view_count"] > 0
    assert "不生成任务、客群、战场、候选竞品、评分排序或报告结论" in m08_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m08_payload["summary_json"])
    assert_no_m08_forbidden_keys(m08_payload["summary_json"])

    signal_profile_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/sku-signal-profile"
    )
    assert signal_profile_response.status_code == 200
    signal_profile_payload = signal_profile_response.json()
    assert signal_profile_payload["total"] == 1
    assert_no_12m_keys(signal_profile_payload)
    assert_no_m08_forbidden_keys(signal_profile_payload)
    target_signal_profile = signal_profile_payload["items"][0]
    assert target_signal_profile["brand_name"] == "海信"
    assert target_signal_profile["profile_status"] in {"ready", "limited", "review_required"}
    assert target_signal_profile["data_completeness_score"] >= 0.7
    assert target_signal_profile["source_coverage_json"]["param"]["status"] in {"covered", "partially_covered"}
    assert target_signal_profile["source_coverage_json"]["claim"]["status"] in {"covered", "partially_covered"}
    assert target_signal_profile["source_coverage_json"]["comment"]["status"] in {"covered", "partially_covered"}
    assert target_signal_profile["source_coverage_json"]["market"]["status"] in {"covered", "partially_covered"}
    assert target_signal_profile["source_coverage_json"]["pool"]["status"] in {"covered", "partially_covered"}
    assert target_signal_profile["core_params_json"]["param_values"]
    assert "screen_size_inch" in target_signal_profile["core_params_json"]["param_values"]
    assert target_signal_profile["claim_activation_summary_json"]["claim_count"] > 0
    assert target_signal_profile["comment_signal_summary_json"]["signal_count"] > 0
    assert target_signal_profile["market_summary_json"]["price_wavg"] == 6999
    assert target_signal_profile["market_summary_json"]["sales_volume_total"] == 892
    assert target_signal_profile["comparable_pool_summary_json"]["pool_count"] > 0
    assert "same_size" in target_signal_profile["comparable_pool_summary_json"]["pool_type_counts"]
    assert target_signal_profile["business_signal_index_json"]["comment_task_hint_codes"]
    assert "M09" in target_signal_profile["downstream_ready_json"]

    matrix_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/sku-signal-evidence-matrix"
    )
    assert matrix_response.status_code == 200
    matrix_payload = matrix_response.json()
    assert matrix_payload["total"] >= 21
    assert_no_12m_keys(matrix_payload)
    assert_no_m08_forbidden_keys(matrix_payload)
    matrix_domains = {item["domain"] for item in matrix_payload["items"]}
    assert {"sku_master", "param", "claim", "comment", "market", "pool", "quality"}.issubset(matrix_domains)
    assert any(item["sub_domain"] == "task_cue" for item in matrix_payload["items"])
    assert any(item["evidence_count"] > 0 for item in matrix_payload["items"])

    downstream_views_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/downstream-feature-views"
    )
    assert downstream_views_response.status_code == 200
    downstream_views_payload = downstream_views_response.json()
    assert downstream_views_payload["total"] == 10
    assert_no_12m_keys(downstream_views_payload)
    assert_no_m08_forbidden_keys(downstream_views_payload)
    modules = {item["for_module"] for item in downstream_views_payload["items"]}
    assert {"M08_4", "M08_5", "M09", "M10", "M11", "M11_5", "M12", "M13", "M14", "M15"} == modules
    m085_view = next(item for item in downstream_views_payload["items"] if item["for_module"] == "M08_5")
    assert "core_params" in m085_view["feature_payload_json"]
    assert "claim_activation_summary" in m085_view["feature_payload_json"]
    assert "comment_signal_summary" in m085_view["feature_payload_json"]
    m12_view = next(item for item in downstream_views_payload["items"] if item["for_module"] == "M12")
    assert "pool_summary" in m12_view["feature_payload_json"]
    assert m12_view["feature_payload_json"]["pool_summary"]["pool_count"] > 0
    assert "视图只提供输入" in downstream_views_payload["summary_cn"]

    m084_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/comment-native-dimensions/run",
        json={"run_id": "local-fixture-run-m084"},
    )
    assert m084_response.status_code == 200, m084_response.json()
    m084_payload = m084_response.json()
    assert m084_payload["module_code"] == "M08.4"
    assert m084_payload["status"] in {"success", "warning"}
    assert m084_payload["summary_json"]["native_dimension_count"] > 0
    assert m084_payload["summary_json"]["alignment_proposal_count"] > 0

    m085_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-ontology/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m085_response.status_code == 200, m085_response.json()
    m085_payload = m085_response.json()
    assert m085_payload["module_code"] == "M08.5"
    assert m085_payload["status"] in {"success", "warning"}
    assert m085_payload["summary_json"]["definition_count"]["task"] == 10
    assert m085_payload["summary_json"]["definition_count"]["battlefield"] == 9
    assert m085_payload["summary_json"]["definition_count"]["service_context"] == 1
    assert m085_payload["summary_json"]["input_sku_count"] == 6
    assert m085_payload["summary_json"]["mapping_rule_count"] > 0
    assert m085_payload["summary_json"]["snapshot_count"] > 0
    assert "服务履约不进入产品战场分配" in m085_payload["summary_json"]["downstream_support"]["M11"]

    ontology_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-ontology/current"
    )
    assert ontology_response.status_code == 200
    ontology_payload = ontology_response.json()
    ontology_version_id = ontology_payload["ontology_version_id"]
    assert ontology_payload["quality_summary_json"]["service_context_count"] == 1

    definitions_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/definitions"
    )
    assert definitions_response.status_code == 200
    definitions_payload = definitions_response.json()
    definition_codes = {item["dimension_code"] for item in definitions_payload["items"]}
    assert "SERVICE_FULFILLMENT_ASSURANCE" in definition_codes
    assert "BF_SERVICE_ASSURANCE" not in definition_codes
    service_definition = next(
        item for item in definitions_payload["items"] if item["dimension_code"] == "SERVICE_FULFILLMENT_ASSURANCE"
    )
    assert service_definition["dimension_type"] == "service_context"
    assert service_definition["allocation_policy"] == "never_allocate"

    mapping_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/mapping-rules",
        params={"mapping_level": "exclude", "target_dimension_type": "battlefield"},
    )
    assert mapping_response.status_code == 200
    mapping_payload = mapping_response.json()
    assert any(item["source_code"] == "installation_service" for item in mapping_payload["items"])

    snapshots_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/snapshots"
    )
    assert snapshots_response.status_code == 200
    snapshots_payload = snapshots_response.json()
    assert any(item["signal_code"] == "SERVICE_FULFILLMENT_ASSURANCE" for item in snapshots_payload["items"])

    m09_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/user-tasks/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m09_response.status_code == 200, m09_response.json()
    m09_payload = m09_response.json()
    assert m09_payload["module_code"] == "M09"
    assert m09_payload["status"] in {"success", "warning"}
    assert m09_payload["summary_json"]["sku_count"] == 6
    assert m09_payload["summary_json"]["task_seed_task_count"] == 10
    assert m09_payload["summary_json"]["task_candidate_count"] == 60
    assert m09_payload["summary_json"]["task_score_count"] == 60
    assert m09_payload["summary_json"]["task_evidence_breakdown_count"] == 60 * 7
    assert "不生成目标客群、价值战场、候选 SKU、核心竞品或高层报告" in m09_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m09_payload["summary_json"])
    assert_no_m09_forbidden_keys(m09_payload["summary_json"])

    task_candidates_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/user-task-candidates"
    )
    assert task_candidates_response.status_code == 200
    task_candidates_payload = task_candidates_response.json()
    assert task_candidates_payload["total"] == 10
    assert_no_m09_forbidden_keys(task_candidates_payload)
    assert any(item["candidate_sources_json"] for item in task_candidates_payload["items"])

    task_scores_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/user-tasks"
    )
    assert task_scores_response.status_code == 200
    task_scores_payload = task_scores_response.json()
    assert task_scores_payload["total"] == 10
    assert_no_12m_keys(task_scores_payload)
    assert_no_m09_forbidden_keys(task_scores_payload)
    assert any(
        item["relation_level"] in {"main", "secondary", "weak"}
        for item in task_scores_payload["items"]
    )
    premium_task = next(
        item for item in task_scores_payload["items"] if item["task_code"] == "TASK_PREMIUM_PICTURE_AV"
    )
    assert premium_task["task_score"] > 0
    assert premium_task["next_module_payload_json"]["source_module"] == "M09"
    assert "能力基础" in premium_task["business_reason_cn"]
    assert "价值表达" in premium_task["business_reason_cn"]
    assert "用户反馈" in premium_task["business_reason_cn"]
    assert "市场验证" in premium_task["business_reason_cn"]

    breakdown_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/user-tasks/TASK_PREMIUM_PICTURE_AV/evidence-breakdown"
    )
    assert breakdown_response.status_code == 200
    breakdown_payload = breakdown_response.json()
    assert breakdown_payload["total"] == 7
    domains = {item["evidence_domain"] for item in breakdown_payload["items"]}
    assert {"param", "claim", "comment", "market", "risk", "seed", "profile"} == domains
    assert_no_m09_forbidden_keys(breakdown_payload)

    review_issues_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/task-review-issues",
        params={"sku_code": "TV900001"},
    )
    assert review_issues_response.status_code == 200
    review_issues_payload = review_issues_response.json()
    assert review_issues_payload["total"] >= 0
    assert_no_m09_forbidden_keys(review_issues_payload)

    m10_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/target-groups/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m10_response.status_code == 200, m10_response.json()
    m10_payload = m10_response.json()
    assert m10_payload["module_code"] == "M10"
    assert m10_payload["status"] in {"success", "warning"}
    assert m10_payload["summary_json"]["sku_count"] == 6
    assert m10_payload["summary_json"]["target_group_seed_count"] == 9
    assert m10_payload["summary_json"]["target_group_candidate_count"] == 54
    assert m10_payload["summary_json"]["target_group_score_count"] == 54
    assert m10_payload["summary_json"]["target_group_evidence_breakdown_count"] == 54 * 8
    assert "不生成价值战场、候选 SKU、核心竞品或高层报告" in m10_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m10_payload["summary_json"])
    assert_no_m10_forbidden_keys(m10_payload["summary_json"])

    target_group_candidates_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/target-group-candidates"
    )
    assert target_group_candidates_response.status_code == 200
    target_group_candidates_payload = target_group_candidates_response.json()
    assert target_group_candidates_payload["total"] == 9
    assert_no_m10_forbidden_keys(target_group_candidates_payload)
    assert any(item["candidate_source_json"] for item in target_group_candidates_payload["items"])

    target_group_scores_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/target-groups"
    )
    assert target_group_scores_response.status_code == 200
    target_group_scores_payload = target_group_scores_response.json()
    assert target_group_scores_payload["total"] == 9
    assert_no_12m_keys(target_group_scores_payload)
    assert_no_m10_forbidden_keys(target_group_scores_payload)
    assert any(
        item["relation_level"] in {"main", "secondary", "weak"}
        for item in target_group_scores_payload["items"]
    )
    av_group = next(
        item for item in target_group_scores_payload["items"] if item["target_group_code"] == "TG_AV_QUALITY_SEEKER"
    )
    assert av_group["target_group_score"] > 0
    assert av_group["source_task_scores_json"]
    assert "购买任务" in av_group["business_reason_cn"]
    assert "用户线索" in av_group["business_reason_cn"]
    assert "价格渠道" in av_group["business_reason_cn"]
    assert "市场验证" in av_group["business_reason_cn"]

    target_group_breakdown_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/target-groups/TG_AV_QUALITY_SEEKER/evidence-breakdown"
    )
    assert target_group_breakdown_response.status_code == 200
    target_group_breakdown_payload = target_group_breakdown_response.json()
    assert target_group_breakdown_payload["total"] == 8
    tg_domains = {item["evidence_domain"] for item in target_group_breakdown_payload["items"]}
    assert {"task", "comment", "price_channel", "market", "service", "risk", "seed", "profile"} == tg_domains
    assert_no_m10_forbidden_keys(target_group_breakdown_payload)

    target_group_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/target-group-review-issues",
        params={"sku_code": "TV900001"},
    )
    assert target_group_review_response.status_code == 200
    target_group_review_payload = target_group_review_response.json()
    assert target_group_review_payload["total"] >= 0
    assert_no_m10_forbidden_keys(target_group_review_payload)

    m11_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/battlefields/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m11_response.status_code == 200, m11_response.json()
    m11_payload = m11_response.json()
    assert m11_payload["module_code"] == "M11"
    assert m11_payload["status"] in {"success", "warning"}
    assert m11_payload["summary_json"]["sku_count"] == 6
    assert m11_payload["summary_json"]["battlefield_seed_count"] == 10
    assert m11_payload["summary_json"]["battlefield_candidate_count"] == 60
    assert m11_payload["summary_json"]["battlefield_score_count"] == 60
    assert m11_payload["summary_json"]["battlefield_evidence_breakdown_count"] == 60 * 10
    assert m11_payload["summary_json"]["battlefield_portfolio_count"] == 6
    assert "不生成卖点价值分层、候选 SKU、核心竞品或高层报告" in m11_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m11_payload["summary_json"])
    assert_no_m11_forbidden_keys(m11_payload["summary_json"])

    battlefield_candidates_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefield-candidates"
    )
    assert battlefield_candidates_response.status_code == 200
    battlefield_candidates_payload = battlefield_candidates_response.json()
    assert battlefield_candidates_payload["total"] == 10
    assert_no_m11_forbidden_keys(battlefield_candidates_payload)
    assert any(item["candidate_source_json"] for item in battlefield_candidates_payload["items"])

    battlefield_scores_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefields"
    )
    assert battlefield_scores_response.status_code == 200
    battlefield_scores_payload = battlefield_scores_response.json()
    assert battlefield_scores_payload["total"] == 10
    assert_no_12m_keys(battlefield_scores_payload)
    assert_no_m11_forbidden_keys(battlefield_scores_payload)
    assert any(
        item["relation_level"] in {"main", "secondary", "opportunity", "weak"}
        for item in battlefield_scores_payload["items"]
    )
    premium_battlefield = next(
        item for item in battlefield_scores_payload["items"] if item["battlefield_code"] == "BF_PREMIUM_PICTURE"
    )
    assert premium_battlefield["battlefield_score"] > 0
    assert premium_battlefield["competitor_selection_role"] in {
        "primary_search_context",
        "secondary_search_context",
        "opportunity_monitoring",
        "not_for_core_search",
    }
    assert "用户任务" in premium_battlefield["business_reason_cn"]
    assert "目标客群" in premium_battlefield["business_reason_cn"]
    assert "核心卖点" in premium_battlefield["business_reason_cn"]
    assert "关键参数" in premium_battlefield["business_reason_cn"]
    assert "市场验证" in premium_battlefield["business_reason_cn"]

    battlefield_breakdown_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefields/BF_PREMIUM_PICTURE/evidence-breakdown"
    )
    assert battlefield_breakdown_response.status_code == 200
    battlefield_breakdown_payload = battlefield_breakdown_response.json()
    assert battlefield_breakdown_payload["total"] == 10
    bf_domains = {item["evidence_domain"] for item in battlefield_breakdown_payload["items"]}
    assert {"task", "target_group", "claim", "param", "comment", "market", "service", "risk", "seed", "profile"} == bf_domains
    assert_no_m11_forbidden_keys(battlefield_breakdown_payload)

    battlefield_portfolio_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefield-portfolio"
    )
    assert battlefield_portfolio_response.status_code == 200
    battlefield_portfolio_payload = battlefield_portfolio_response.json()
    assert battlefield_portfolio_payload["total"] == 1
    portfolio_item = battlefield_portfolio_payload["items"][0]
    assert portfolio_item["battlefield_score_refs_json"]
    assert len(portfolio_item["main_battlefields_json"]) == 1
    assert len(portfolio_item["secondary_battlefields_json"]) <= 2
    assert len(portfolio_item["opportunity_battlefields_json"]) <= 3
    allocated_battlefields = portfolio_item["main_battlefields_json"] + portfolio_item["secondary_battlefields_json"]
    assert allocated_battlefields
    assert 0.99 <= sum(item["allocation_weight"] for item in allocated_battlefields) <= 1.01
    assert all(item["allocation_eligible"] for item in allocated_battlefields)
    assert all(item["market_pool_key"] for item in allocated_battlefields)
    assert "竞品召回" in battlefield_portfolio_payload["items"][0]["primary_competitor_search_context_cn"]
    assert_no_m11_forbidden_keys(battlefield_portfolio_payload)

    battlefield_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/battlefield-review-issues",
        params={"sku_code": "TV900001"},
    )
    assert battlefield_review_response.status_code == 200
    battlefield_review_payload = battlefield_review_response.json()
    assert battlefield_review_payload["total"] >= 0
    assert_no_m11_forbidden_keys(battlefield_review_payload)

    m115_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/claim-value-layers/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m115_response.status_code == 200, m115_response.json()
    m115_payload = m115_response.json()
    assert m115_payload["module_code"] == "M11.5"
    assert m115_payload["status"] in {"success", "warning"}
    assert m115_payload["summary_json"]["sku_count"] == 6
    assert m115_payload["summary_json"]["claim_seed_count"] == 20
    assert m115_payload["summary_json"]["battlefield_seed_count"] == 10
    assert m115_payload["summary_json"]["claim_candidate_count"] > 0
    assert m115_payload["summary_json"]["claim_value_layer_count"] > 0
    assert m115_payload["summary_json"]["claim_value_evidence_breakdown_count"] >= (
        m115_payload["summary_json"]["claim_value_layer_count"] * 10
    )
    assert m115_payload["summary_json"]["battlefield_claim_value_summary_count"] > 0
    assert "不生成候选 SKU、核心竞品、组件评分或高层报告" in m115_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m115_payload["summary_json"])
    assert_no_m11_5_forbidden_keys(m115_payload["summary_json"])

    claim_candidates_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefields/BF_PREMIUM_PICTURE/claim-value-candidates"
    )
    assert claim_candidates_response.status_code == 200
    claim_candidates_payload = claim_candidates_response.json()
    assert claim_candidates_payload["total"] > 0
    assert_no_m11_5_forbidden_keys(claim_candidates_payload)
    assert any(item["claim_code"].startswith("CLAIM_") for item in claim_candidates_payload["items"])
    assert all("不代表竞品结论" in item["business_note_cn"] for item in claim_candidates_payload["items"])

    claim_layers_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefields/BF_PREMIUM_PICTURE/claim-value-layers"
    )
    assert claim_layers_response.status_code == 200
    claim_layers_payload = claim_layers_response.json()
    assert claim_layers_payload["total"] > 0
    assert_no_12m_keys(claim_layers_payload)
    assert_no_m11_5_forbidden_keys(claim_layers_payload)
    assert any(
        item["layer"] in {"basic_threshold", "competitive_performance", "premium_tendency", "weak_perception", "insufficient_sample"}
        for item in claim_layers_payload["items"]
    )
    assert any("战场相关性" in item["business_reason_cn"] for item in claim_layers_payload["items"])
    first_claim_layer = claim_layers_payload["items"][0]

    claim_breakdown_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefields/BF_PREMIUM_PICTURE/claim-value-layers/{first_claim_layer['claim_code']}/evidence-breakdown"
    )
    assert claim_breakdown_response.status_code == 200
    claim_breakdown_payload = claim_breakdown_response.json()
    assert claim_breakdown_payload["total"] == 12
    cv_domains = {item["evidence_domain"] for item in claim_breakdown_payload["items"]}
    assert {
        "activation",
        "param",
        "promo",
        "comment",
        "price",
        "sales",
        "pool",
        "market",
        "service",
        "risk",
        "seed",
        "profile",
    } == cv_domains
    assert_no_m11_5_forbidden_keys(claim_breakdown_payload)

    claim_summary_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/battlefields/BF_PREMIUM_PICTURE/claim-value-summary"
    )
    assert claim_summary_response.status_code == 200
    claim_summary_payload = claim_summary_response.json()
    assert claim_summary_payload["total"] == 1
    assert claim_summary_payload["items"][0]["claim_value_layer_refs_json"]
    assert claim_summary_payload["items"][0]["comparison_focus_claims_json"]
    assert "战场内卖点组合摘要" in claim_summary_payload["summary_cn"]
    assert_no_m11_5_forbidden_keys(claim_summary_payload)

    claim_value_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/claim-value-review-issues",
        params={"sku_code": "TV900001"},
    )
    assert claim_value_review_response.status_code == 200
    claim_value_review_payload = claim_value_review_response.json()
    assert claim_value_review_payload["total"] >= 0
    assert_no_m11_5_forbidden_keys(claim_value_review_payload)

    m116_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/sku-business-profiles/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m116_response.status_code == 200, m116_response.json()
    m116_payload = m116_response.json()
    assert m116_payload["module_code"] == "M11.6"
    assert m116_payload["status"] in {"success", "warning"}
    assert m116_payload["summary_json"]["business_profile_count"] == 6
    assert m116_payload["summary_json"]["business_dimension_count"] > 0
    assert m116_payload["summary_json"]["sales_allocation_count"] > 0
    assert m116_payload["summary_json"]["dimension_counts"]["claim"] > 0
    assert m116_payload["summary_json"]["dimension_counts"]["task"] > 0
    assert m116_payload["summary_json"]["dimension_counts"]["target_group"] > 0
    assert m116_payload["summary_json"]["dimension_counts"]["battlefield"] > 0
    assert "不做全局销量守恒" in m116_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m116_payload["summary_json"])
    assert_no_m11_6_forbidden_keys(m116_payload["summary_json"])

    business_profile_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/business-profile"
    )
    assert business_profile_response.status_code == 200
    business_profile_payload = business_profile_response.json()
    assert business_profile_payload["total"] == 1
    assert_no_12m_keys(business_profile_payload)
    assert_no_m11_6_forbidden_keys(business_profile_payload)
    target_business_profile = business_profile_payload["items"][0]
    assert target_business_profile["primary_battlefield_code"]
    assert target_business_profile["primary_task_code"]
    assert target_business_profile["primary_target_group_code"]
    assert target_business_profile["core_claims_json"]
    assert target_business_profile["sales_allocation_summary_json"]
    assert target_business_profile["sales_volume_total"] == 892
    assert "主战场" in target_business_profile["business_note_cn"]
    assert "溢价判断" in target_business_profile["business_note_cn"]

    business_dimensions_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/business-profile-dimensions",
        params={"dimension_type": "claim"},
    )
    assert business_dimensions_response.status_code == 200
    business_dimensions_payload = business_dimensions_response.json()
    assert business_dimensions_payload["total"] > 0
    assert_no_m11_6_forbidden_keys(business_dimensions_payload)
    assert all(item["normalized_weight"] > 0 for item in business_dimensions_payload["items"])
    assert all(item["business_reason_cn"] for item in business_dimensions_payload["items"])

    business_allocations_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/business-profile-sales-allocation",
        params={"dimension_type": "battlefield"},
    )
    assert business_allocations_response.status_code == 200
    business_allocations_payload = business_allocations_response.json()
    assert business_allocations_payload["total"] > 0
    assert_no_m11_6_forbidden_keys(business_allocations_payload)
    allocation_weight_total = sum(item["allocation_weight"] for item in business_allocations_payload["items"])
    assert 0.99 <= allocation_weight_total <= 1.01
    assert any(item["allocated_sales_volume"] and item["allocated_sales_volume"] > 0 for item in business_allocations_payload["items"])

    business_profile_issues_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/business-profile-review-issues",
        params={"sku_code": "TV900001"},
    )
    assert business_profile_issues_response.status_code == 200
    business_profile_issues_payload = business_profile_issues_response.json()
    assert business_profile_issues_payload["total"] >= 0
    assert_no_m11_6_forbidden_keys(business_profile_issues_payload)

    m117_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-sales-reconciliation/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m117_response.status_code == 200, m117_response.json()
    m117_payload = m117_response.json()
    assert m117_payload["module_code"] == "M11.7"
    assert m117_payload["status"] in {"success", "warning"}
    assert m117_payload["summary_json"]["dimension_sales_summary_count"] == 49
    assert m117_payload["summary_json"]["standard_dimension_counts"] == {
        "claim": 20,
        "task": 10,
        "target_group": 9,
        "battlefield": 10,
    }
    assert m117_payload["summary_json"]["sku_contribution_count"] > 0
    assert m117_payload["summary_json"]["reconciliation_check_count"] > 0
    assert m117_payload["summary_json"]["m12_admission_status"] == "allowed"
    assert "不重新分配权重" in m117_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m117_payload["summary_json"])
    assert_no_m11_7_forbidden_keys(m117_payload["summary_json"])

    session.add(
        entities.Core3BusinessDimensionSkuContribution(
            dimension_sku_contribution_id="stale-m117-contribution",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=batch_id,
            dimension_type="battlefield",
            dimension_code="BF_STALE_ALL_SKU",
            dimension_name="旧版宽覆盖战场",
            sku_code="TV900001",
            allocation_weight=1,
            allocated_sales_volume=892,
            allocated_sales_amount=6200000,
            sku_share_in_dimension_volume=1,
            sku_share_in_dimension_amount=1,
            contribution_reason_cn="模拟旧版本保留下来的 current 贡献。",
            rule_version=CORE3_M11_7_RULE_VERSION,
            input_fingerprint="stale-m117-fingerprint",
            result_hash="stale-m117-result",
            is_current=True,
        )
    )
    session.flush()

    rerun_m117_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-sales-reconciliation/run",
        json={"run_id": "local-fixture-rerun"},
    )
    assert rerun_m117_response.status_code == 200, rerun_m117_response.json()
    stale_contribution_count = session.execute(
        text(
            """
            SELECT count(*)
            FROM core3_business_dimension_sku_contribution
            WHERE project_id = :project_id
              AND batch_id = :batch_id
              AND dimension_code = 'BF_STALE_ALL_SKU'
              AND is_current = 1
            """
        ),
        {"project_id": PROJECT_ID, "batch_id": batch_id},
    ).scalar_one()
    assert stale_contribution_count == 0

    dimension_sales_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-sales-summary",
        params={"dimension_type": "battlefield"},
    )
    assert dimension_sales_response.status_code == 200
    dimension_sales_payload = dimension_sales_response.json()
    assert dimension_sales_payload["total"] == 10
    assert any(item["dimension_code"] == "BF_PREMIUM_PICTURE" for item in dimension_sales_payload["items"])
    assert all(item["business_note_cn"] for item in dimension_sales_payload["items"])
    assert_no_m11_7_forbidden_keys(dimension_sales_payload)

    battlefield_contribution_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/dimension-sales-summary/battlefield/BF_PREMIUM_PICTURE/sku-contributions"
    )
    assert battlefield_contribution_response.status_code == 200
    battlefield_contribution_payload = battlefield_contribution_response.json()
    assert battlefield_contribution_payload["total"] > 0
    assert any(item["allocated_sales_volume"] and item["allocated_sales_volume"] > 0 for item in battlefield_contribution_payload["items"])
    assert all(item["allocated_sales_volume"] >= 0 for item in battlefield_contribution_payload["items"])
    assert_no_m11_7_forbidden_keys(battlefield_contribution_payload)

    reconciliation_checks_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/sales-reconciliation-checks",
        params={"status": "failed"},
    )
    assert reconciliation_checks_response.status_code == 200
    reconciliation_checks_payload = reconciliation_checks_response.json()
    assert reconciliation_checks_payload["total"] == 0
    assert_no_m11_7_forbidden_keys(reconciliation_checks_payload)

    reconciliation_issues_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/sales-reconciliation-issues",
        params={"severity": "blocker"},
    )
    assert reconciliation_issues_response.status_code == 200
    reconciliation_issues_payload = reconciliation_issues_response.json()
    assert reconciliation_issues_payload["total"] == 0
    assert_no_m11_7_forbidden_keys(reconciliation_issues_payload)

    m12_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/candidate-recall/run",
        json={"run_id": "local-fixture-run"},
    )
    assert m12_response.status_code == 200, m12_response.json()
    m12_payload = m12_response.json()
    assert m12_payload["module_code"] == "M12"
    assert m12_payload["status"] in {"success", "warning"}
    assert m12_payload["summary_json"]["target_sku_count"] == 6
    assert m12_payload["summary_json"]["candidate_pair_count"] > 0
    assert m12_payload["summary_json"]["reason_count"] >= m12_payload["summary_json"]["candidate_pair_count"]
    assert m12_payload["summary_json"]["feature_snapshot_count"] == m12_payload["summary_json"]["candidate_pair_count"]
    assert m12_payload["summary_json"]["same_brand_pair_count"] > 0
    assert "不生成最终竞品排序" in m12_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m12_payload["summary_json"])
    assert_no_m12_forbidden_keys(m12_payload["summary_json"])

    recall_runs_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/candidate-recall-runs"
    )
    assert recall_runs_response.status_code == 200
    recall_runs_payload = recall_runs_response.json()
    assert recall_runs_payload["total"] == 1
    assert recall_runs_payload["items"][0]["candidate_pair_count"] == m12_payload["summary_json"]["candidate_pair_count"]
    assert_no_m12_forbidden_keys(recall_runs_payload)

    candidate_pool_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/candidate-pool"
    )
    assert candidate_pool_response.status_code == 200
    candidate_pool_payload = candidate_pool_response.json()
    assert candidate_pool_payload["total"] >= 3
    assert_no_12m_keys(candidate_pool_payload)
    assert_no_m12_forbidden_keys(candidate_pool_payload)
    assert any(item["same_brand_flag"] for item in candidate_pool_payload["items"])
    assert any(
        item["primary_relation_type"]
        in {"direct_fight", "price_volume_pressure", "configuration_pressure", "scenario_substitute"}
        for item in candidate_pool_payload["items"]
    )
    assert all("不代表最终核心三竞品" in item["business_note_cn"] for item in candidate_pool_payload["items"])
    first_candidate = candidate_pool_payload["items"][0]

    reasons_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/candidate-pool/{first_candidate['candidate_sku_code']}/reasons"
    )
    assert reasons_response.status_code == 200
    reasons_payload = reasons_response.json()
    assert reasons_payload["total"] > 0
    assert_no_m12_forbidden_keys(reasons_payload)
    assert {
        item["recall_source"]
        for item in reasons_payload["items"]
    }.intersection({"comparable_pool", "battlefield", "task", "audience", "claim_value", "market_pressure"})
    assert all(item["reason_summary_cn"] for item in reasons_payload["items"])

    snapshot_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/candidate-pool/{first_candidate['candidate_sku_code']}/feature-snapshot"
    )
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["total"] == 1
    assert_no_12m_keys(snapshot_payload)
    assert_no_m12_forbidden_keys(snapshot_payload)
    snapshot = snapshot_payload["items"][0]
    assert snapshot["m13_component_input_json"]["target_sku_code"] == "TV900001"
    assert snapshot["m13_component_input_json"]["candidate_sku_code"] == first_candidate["candidate_sku_code"]
    assert "battlefield_overlap" in snapshot["m13_component_input_json"]
    assert "task_overlap" in snapshot["m13_component_input_json"]
    assert "audience_overlap" in snapshot["m13_component_input_json"]
    assert "claim_value_overlap" in snapshot["m13_component_input_json"]

    candidate_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/candidate-recall-review-issues",
        params={"target_sku_code": "TV900001"},
    )
    assert candidate_review_response.status_code == 200
    candidate_review_payload = candidate_review_response.json()
    assert candidate_review_payload["total"] >= 0
    assert_no_m12_forbidden_keys(candidate_review_payload)

    m13_limited_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/component-scores/run",
        json={"run_id": "local-fixture-run-limited", "max_pairs": 1},
    )
    assert m13_limited_response.status_code == 200, m13_limited_response.json()
    m13_limited_payload = m13_limited_response.json()
    assert m13_limited_payload["module_code"] == "M13"
    assert m13_limited_payload["status"] == "warning"
    assert m13_limited_payload["summary_json"]["total_candidate_pair_count"] == m12_payload["summary_json"]["candidate_pair_count"]
    assert m13_limited_payload["summary_json"]["processed_pair_count"] == 1
    assert m13_limited_payload["summary_json"]["pending_pair_count_after"] == m12_payload["summary_json"]["candidate_pair_count"] - 1
    assert m13_limited_payload["summary_json"]["batch_limited"] is True
    assert m13_limited_payload["summary_json"]["batch_completed"] is False

    m13_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/component-scores/run",
        json={"run_id": "local-fixture-run", "max_pairs": 1000, "resume_unscored_only": False},
    )
    assert m13_response.status_code == 200, m13_response.json()
    m13_payload = m13_response.json()
    assert m13_payload["module_code"] == "M13"
    assert m13_payload["status"] in {"success", "warning"}
    assert m13_payload["summary_json"]["candidate_pair_count"] == m12_payload["summary_json"]["candidate_pair_count"]
    assert m13_payload["summary_json"]["component_score_count"] == m12_payload["summary_json"]["candidate_pair_count"]
    assert m13_payload["summary_json"]["role_score_count"] == m12_payload["summary_json"]["candidate_pair_count"] * 5
    assert m13_payload["summary_json"]["component_explanation_count"] == m12_payload["summary_json"]["candidate_pair_count"] * 18
    assert "不选择核心三竞品" in m13_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m13_payload["summary_json"])
    assert_no_m13_forbidden_keys(m13_payload["summary_json"])

    component_scores_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/component-scores"
    )
    assert component_scores_response.status_code == 200
    component_scores_payload = component_scores_response.json()
    assert component_scores_payload["total"] >= 3
    assert_no_12m_keys(component_scores_payload)
    assert_no_m13_forbidden_keys(component_scores_payload)
    first_scored_candidate = component_scores_payload["items"][0]
    assert first_scored_candidate["component_total_score"] > 0
    assert first_scored_candidate["direct_fight_score"] >= 0
    assert first_scored_candidate["price_volume_pressure_score"] >= 0
    assert first_scored_candidate["benchmark_potential_score"] >= 0
    assert "不是最终核心竞品结论" in first_scored_candidate["business_note_cn"]

    single_score_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/component-scores/{first_scored_candidate['candidate_sku_code']}"
    )
    assert single_score_response.status_code == 200
    single_score_payload = single_score_response.json()
    assert single_score_payload["total"] == 1
    assert single_score_payload["items"][0]["candidate_sku_code"] == first_scored_candidate["candidate_sku_code"]

    role_scores_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/component-scores/{first_scored_candidate['candidate_sku_code']}/roles"
    )
    assert role_scores_response.status_code == 200
    role_scores_payload = role_scores_response.json()
    assert role_scores_payload["total"] == 5
    assert_no_m13_forbidden_keys(role_scores_payload)
    assert {
        item["role_code"]
        for item in role_scores_payload["items"]
    } == {"direct_fight", "price_volume_pressure", "benchmark_potential", "configuration_pressure", "service_reference"}
    assert all("不是最终排名" in item["business_note_cn"] for item in role_scores_payload["items"])

    explanations_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/component-scores/{first_scored_candidate['candidate_sku_code']}/explanations"
    )
    assert explanations_response.status_code == 200
    explanations_payload = explanations_response.json()
    assert explanations_payload["total"] == 18
    assert_no_m13_forbidden_keys(explanations_payload)
    component_codes = {item["component_code"] for item in explanations_payload["items"]}
    assert {"base_comparability", "battlefield_fit", "claim_confrontation", "evidence_completeness"}.issubset(component_codes)
    assert all(item["business_explanation_cn"] for item in explanations_payload["items"])

    score_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/component-score-review-issues",
        params={"target_sku_code": "TV900001"},
    )
    assert score_review_response.status_code == 200
    score_review_payload = score_review_response.json()
    assert score_review_payload["total"] >= 0
    assert_no_m13_forbidden_keys(score_review_payload)

    m14_limited_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/core3-selection/run",
        json={"run_id": "local-fixture-run-limited", "max_targets": 2},
    )
    assert m14_limited_response.status_code == 200, m14_limited_response.json()
    m14_limited_payload = m14_limited_response.json()
    assert m14_limited_payload["module_code"] == "M14"
    assert m14_limited_payload["status"] == "warning"
    assert m14_limited_payload["summary_json"]["total_target_count"] == 6
    assert m14_limited_payload["summary_json"]["target_sku_count"] == 2
    assert m14_limited_payload["summary_json"]["processed_target_count"] == 2
    assert m14_limited_payload["summary_json"]["selected_target_count_after"] == 2
    assert m14_limited_payload["summary_json"]["pending_target_count_after"] == 4
    assert m14_limited_payload["summary_json"]["batch_limited"] is True
    assert m14_limited_payload["summary_json"]["batch_completed"] is False

    m14_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/core3-selection/run",
        json={"run_id": "local-fixture-run", "max_targets": 50},
    )
    assert m14_response.status_code == 200, m14_response.json()
    m14_payload = m14_response.json()
    assert m14_payload["module_code"] == "M14"
    assert m14_payload["status"] in {"success", "warning"}, m14_payload
    assert m14_payload["summary_json"]["total_target_count"] == 6
    assert m14_payload["summary_json"]["target_sku_count"] == 4
    assert m14_payload["summary_json"]["processed_target_count"] == 4
    assert m14_payload["summary_json"]["selection_run_count"] == 4
    assert m14_payload["summary_json"]["slot_decision_count"] == 4 * 3
    assert m14_payload["summary_json"]["audit_count"] > 0
    assert m14_payload["summary_json"]["selected_target_count_after"] == 6
    assert m14_payload["summary_json"]["pending_target_count_after"] == 0
    assert m14_payload["summary_json"]["batch_limited"] is False
    assert m14_payload["summary_json"]["batch_completed"] is True
    assert 0 <= m14_payload["summary_json"]["selection_count"] <= 4 * 3
    assert "不是 M13 总分 TopN" in m14_payload["summary_json"]["boundary_note"]
    assert "不强行凑满" in m14_payload["summary_json"]["boundary_note"]
    assert_no_12m_keys(m14_payload["summary_json"])
    assert_no_m14_forbidden_keys(m14_payload["summary_json"])

    selection_runs_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/core3-selection-runs"
    )
    assert selection_runs_response.status_code == 200
    selection_runs_payload = selection_runs_response.json()
    assert selection_runs_payload["total"] == 1
    assert selection_runs_payload["items"][0]["selected_count"] <= 3
    assert selection_runs_payload["items"][0]["candidate_count"] >= 3
    assert "三槽位" in selection_runs_payload["summary_cn"]
    assert_no_m14_forbidden_keys(selection_runs_payload)

    selections_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/core3-selections"
    )
    assert selections_response.status_code == 200
    selections_payload = selections_response.json()
    assert 0 < selections_payload["total"] <= 3
    assert "不按总分 TopN" in selections_payload["summary_cn"]
    assert_no_m14_forbidden_keys(selections_payload)
    selection_slots = [item["slot_code"] for item in selections_payload["items"]]
    selection_candidates = [item["candidate_sku_code"] for item in selections_payload["items"]]
    assert len(selection_slots) == len(set(selection_slots))
    assert len(selection_candidates) == len(set(selection_candidates))
    assert all(item["business_conclusion_cn"] for item in selections_payload["items"])
    assert all("不是因为总分排名" in item["selection_reason_cn"] for item in selections_payload["items"])

    slot_decisions_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/core3-slot-decisions"
    )
    assert slot_decisions_response.status_code == 200
    slot_decisions_payload = slot_decisions_response.json()
    assert slot_decisions_payload["total"] == 3
    assert_no_m14_forbidden_keys(slot_decisions_payload)
    assert {item["slot_code"] for item in slot_decisions_payload["items"]} == {
        "direct_fight",
        "price_volume_pressure",
        "benchmark_potential",
    }
    assert all(item["decision_summary_cn"] for item in slot_decisions_payload["items"])

    selection_audits_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/core3-selection-audits"
    )
    assert selection_audits_response.status_code == 200
    selection_audits_payload = selection_audits_response.json()
    assert selection_audits_payload["total"] >= selections_payload["total"]
    assert_no_m14_forbidden_keys(selection_audits_payload)
    assert {"selected", "review", "rejected", "blocked"}.intersection(
        {item["audit_decision"] for item in selection_audits_payload["items"]}
    )
    assert all(item["decision_reason_cn"] for item in selection_audits_payload["items"])

    selection_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/core3-selection-review-issues",
        params={"target_sku_code": "TV900001"},
    )
    assert selection_review_response.status_code == 200
    selection_review_payload = selection_review_response.json()
    assert selection_review_payload["total"] >= 0
    assert_no_m14_forbidden_keys(selection_review_payload)

    m15_limited_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/evidence-report/run",
        json={"run_id": "local-fixture-run-limited", "max_targets": 2},
    )
    assert m15_limited_response.status_code == 200, m15_limited_response.json()
    m15_limited_payload = m15_limited_response.json()
    assert m15_limited_payload["module_code"] == "M15"
    assert m15_limited_payload["status"] == "warning"
    assert m15_limited_payload["summary_json"]["total_target_count"] == 6
    assert m15_limited_payload["summary_json"]["target_sku_count"] == 2
    assert m15_limited_payload["summary_json"]["target_report_count"] == 2
    assert m15_limited_payload["summary_json"]["processed_target_count"] == 2
    assert m15_limited_payload["summary_json"]["reported_target_count_after"] == 2
    assert m15_limited_payload["summary_json"]["pending_target_count_after"] == 4
    assert m15_limited_payload["summary_json"]["batch_limited"] is True
    assert m15_limited_payload["summary_json"]["batch_completed"] is False

    m15_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/evidence-report/run",
        json={"run_id": "local-fixture-run", "max_targets": 50},
    )
    assert m15_response.status_code == 200, m15_response.json()
    m15_payload = m15_response.json()
    assert m15_payload["module_code"] == "M15"
    assert m15_payload["status"] in {"success", "warning"}, m15_payload
    assert m15_payload["summary_json"]["total_target_count"] == 6
    assert m15_payload["summary_json"]["target_sku_count"] == 4
    assert m15_payload["summary_json"]["target_report_count"] == 4
    assert m15_payload["summary_json"]["processed_target_count"] == 4
    assert m15_payload["summary_json"]["reported_target_count_after"] == 6
    assert m15_payload["summary_json"]["pending_target_count_after"] == 0
    assert m15_payload["summary_json"]["batch_limited"] is False
    assert m15_payload["summary_json"]["batch_completed"] is True
    m14_total_selection_count = (
        m14_limited_payload["summary_json"]["selection_count"] + m14_payload["summary_json"]["selection_count"]
    )
    m15_total_card_count = (
        m15_limited_payload["summary_json"]["evidence_card_count"] + m15_payload["summary_json"]["evidence_card_count"]
    )
    m15_total_section_count = (
        m15_limited_payload["summary_json"]["section_count"] + m15_payload["summary_json"]["section_count"]
    )
    m15_total_export_count = (
        m15_limited_payload["summary_json"]["export_count"] + m15_payload["summary_json"]["export_count"]
    )
    assert m15_total_card_count == m14_total_selection_count
    assert m15_total_section_count == 6 * 11
    assert m15_total_export_count == 6 * 4
    assert "当前样例数据内" in m15_payload["summary_json"]["data_scope_note_cn"]
    assert "26W01-26W23" in m15_payload["summary_json"]["data_scope_note_cn"]
    assert "线上渠道" in m15_payload["summary_json"]["data_scope_note_cn"]
    assert "同品牌" in m15_payload["summary_json"]["data_scope_note_cn"]
    assert_no_12m_keys(m15_payload["summary_json"])

    report_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/report"
    )
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert "当前样例数据内" in report_payload["executive_conclusion_cn"]
    assert "不是简单总分排名" in report_payload["executive_conclusion_cn"]
    assert len(report_payload["core_competitors_json"]) <= 3
    assert len(report_payload["sop_trace_json"]) == 7
    assert [item["名称"] for item in report_payload["sop_trace_json"]] == [
        "SKU 信号画像",
        "用户任务识别",
        "目标客群判断",
        "价值战场判定",
        "候选池召回",
        "组件评分",
        "三槽位选择",
    ]
    assert "当前样例数据内" in report_payload["data_quality_note_cn"]
    assert "服务、物流、安装类评论只作为履约风险参考" in report_payload["data_quality_note_cn"]
    if any("宣传卖点数据缺口" in warning for warning in m15_payload["warnings"]):
        assert "宣传卖点数据缺口" in report_payload["data_quality_note_cn"]
    assert all("evidence_id" not in item for item in report_payload["short_evidence_map_json"])
    assert_no_m15_business_leak(report_payload)

    evidence_cards_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/evidence-cards"
    )
    assert evidence_cards_response.status_code == 200
    evidence_cards_payload = evidence_cards_response.json()
    assert evidence_cards_payload["total"] == selections_payload["total"]
    assert evidence_cards_payload["items"]
    assert all(item["headline_cn"] for item in evidence_cards_payload["items"])
    assert all(item["one_sentence_reason_cn"] for item in evidence_cards_payload["items"])
    assert all(item["short_evidence_refs_json"] for item in evidence_cards_payload["items"])
    assert_no_m15_business_leak(evidence_cards_payload)

    sections_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/report/sections"
    )
    assert sections_response.status_code == 200
    sections_payload = sections_response.json()
    assert sections_payload["total"] == 11
    assert [item["section_order"] for item in sections_payload["items"]] == list(range(1, 12))
    assert {"executive", "competitor_cards", "why_competitor", "data_quality"}.issubset(
        {item["section_code"] for item in sections_payload["items"]}
    )
    assert_no_m15_business_leak(sections_payload)

    export_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/report/exports/markdown"
    )
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert export_payload["export_status"] in {"ready", "review_required"}
    assert "核心竞品" in export_payload["export_payload"]
    assert "当前样例数据内" in export_payload["data_scope_note_cn"]
    assert_no_m15_business_leak(export_payload)

    report_review_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/report-review-issues",
        params={"target_sku_code": "TV900001"},
    )
    assert report_review_response.status_code == 200
    report_review_payload = report_review_response.json()
    assert report_review_payload["total"] >= 0

    first_short_ref = evidence_cards_payload["items"][0]["short_evidence_refs_json"][0]["short_ref"]
    trace_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/batches/{batch_id}/skus/TV900001/evidence-ref/{first_short_ref}"
    )
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["short_ref"] == first_short_ref
    assert "技术追溯接口" in trace_payload["business_note_cn"]

    m16_response = client.post(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs",
        json={
            "project_id": PROJECT_ID,
            "data_batch_id": batch_id,
            "run_id": "local-fixture-m16-run",
            "triggered_by": "local_fixture",
            "target_scope": {
                "scope_type": "all_sku",
                "sku_codes": [],
                "include_related_targets": True,
                "data_domains": ["report"],
                "note_cn": "本地样例 M16 生产线治理验收",
            },
        },
    )
    assert m16_response.status_code == 200, m16_response.json()
    m16_payload = m16_response.json()
    assert m16_payload["status"] in {"success", "warning"}, m16_payload
    assert m16_payload["release_status"] in {"releasable", "review_required"}
    assert m16_payload["data_batch_id"] == batch_id
    assert m16_payload["output_summary_json"]["module_count"] == 23
    assert m16_payload["output_summary_json"]["release_gate_count"] == 6
    assert "展示条件" in m16_payload["summary_cn"] or "需保留样例范围" in m16_payload["summary_cn"]
    m16_run_id = m16_payload["run_id"]

    m16_plan_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/recompute-plan"
    )
    assert m16_plan_response.status_code == 200
    m16_plan_payload = m16_plan_response.json()
    assert m16_plan_payload["total"] == 23
    plan_by_module = {item["module_code"]: item for item in m16_plan_payload["items"]}
    assert plan_by_module["M16"]["planned_action"] == "run"
    assert plan_by_module["M15"]["planned_action"] == "reuse"

    m16_module_runs_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/module-runs"
    )
    assert m16_module_runs_response.status_code == 200
    m16_module_runs_payload = m16_module_runs_response.json()
    assert m16_module_runs_payload["total"] == 23
    module_statuses = {item["module_code"]: item["status"] for item in m16_module_runs_payload["items"]}
    assert module_statuses["M16"] in {"success", "warning"}
    assert set(module_statuses) >= {
        "M00",
        "M01",
        "M02",
        "M03",
        "M04a",
        "M05",
        "M06",
        "M04b",
        "M07",
        "M08",
        "M08.4",
        "M08.5",
        "M09",
        "M10",
        "M11",
        "M11.5",
        "M11.6",
        "M11.7",
        "M12",
        "M13",
        "M14",
        "M15",
        "M16",
    }

    m16_dependencies_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/dependencies",
        params={"module_code": "M16"},
    )
    assert m16_dependencies_response.status_code == 200
    m16_dependencies_payload = m16_dependencies_response.json()
    assert m16_dependencies_payload["total"] == 22
    assert {item["dependency_status"] for item in m16_dependencies_payload["items"]} == {"valid"}
    assert {item["upstream_module_code"] for item in m16_dependencies_payload["items"]} >= {"M00", "M08", "M14", "M15"}

    m16_acceptance_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/acceptance"
    )
    assert m16_acceptance_response.status_code == 200
    m16_acceptance_payload = m16_acceptance_response.json()
    assert m16_acceptance_payload["processed_target_count"] == 6
    assert m16_acceptance_payload["report_ready_count"] == 6
    assert m16_acceptance_payload["acceptance_status"] in {"passed", "passed_with_warning"}
    assert m16_acceptance_payload["module_status_summary_json"]["M15"]["output_count"] > 0
    assert "当前样例数据内" in m16_acceptance_payload["data_scope_note_cn"]

    m16_release_gates_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/release-gates"
    )
    assert m16_release_gates_response.status_code == 200
    m16_release_gates_payload = m16_release_gates_response.json()
    assert m16_release_gates_payload["total"] == 6
    target_gate = next(item for item in m16_release_gates_payload["items"] if item["target_sku_code"] == "TV900001")
    assert target_gate["gate_status"] in {"releasable", "review_required"}
    assert target_gate["display_badges_json"]

    m16_reviews_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/reviews"
    )
    assert m16_reviews_response.status_code == 200
    assert m16_reviews_response.json()["total"] >= 0

    api_data_status_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/data-status")
    assert api_data_status_response.status_code == 200
    api_data_status_payload = api_data_status_response.json()
    assert api_data_status_payload["has_data"] is True
    assert api_data_status_payload["latest_batch_id"] == batch_id
    assert api_data_status_payload["target_count"] == 6
    assert api_data_status_payload["report_count"] == 6
    assert api_data_status_payload["latest_run_id"] == m16_run_id

    api_resolve_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/sku/resolve",
        params={"query": "TV900001"},
    )
    assert api_resolve_response.status_code == 200
    api_resolve_payload = api_resolve_response.json()
    assert api_resolve_payload["status"] == "unique"
    assert api_resolve_payload["target"]["sku_code"] == "TV900001"

    api_overview_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/overview")
    assert api_overview_response.status_code == 200
    api_overview_payload = api_overview_response.json()
    assert api_overview_payload["target_count"] == 6
    assert api_overview_payload["report_count"] == 6
    assert len(api_overview_payload["targets_preview"]) > 0

    api_targets_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets")
    assert api_targets_response.status_code == 200
    api_targets_payload = api_targets_response.json()
    assert api_targets_payload["total"] == 6
    assert any(item["target_sku_code"] == "TV900001" for item in api_targets_payload["items"])

    api_report_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets/TV900001/report")
    assert api_report_response.status_code == 200, api_report_response.json()
    api_report_payload = api_report_response.json()
    assert api_report_payload["target"]["sku_code"] == "TV900001"
    assert len(api_report_payload["core_competitors"]) > 0
    assert len(api_report_payload["evidence_cards"]) == len(api_report_payload["core_competitors"])
    assert "当前" in api_report_payload["data_scope"]["data_scope_note_cn"]
    assert "为什么" not in api_report_payload["report_title_cn"] or api_report_payload["why_these_competitors_cn"]
    assert_no_m15_business_leak(api_report_payload)
    assert "evidence_id" not in str(api_report_payload)
    assert "selection_run_id" not in str(api_report_payload)

    api_competitors_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets/TV900001/competitors"
    )
    assert api_competitors_response.status_code == 200
    api_competitors_payload = api_competitors_response.json()
    assert len(api_competitors_payload) == len(api_report_payload["core_competitors"])
    assert all(item["one_sentence_reason_cn"] for item in api_competitors_payload)

    api_cards_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets/TV900001/evidence-cards"
    )
    assert api_cards_response.status_code == 200
    api_cards_payload = api_cards_response.json()
    assert len(api_cards_payload) > 0
    assert all(item["evidence_short_refs"] for item in api_cards_payload)
    assert_no_m15_business_leak(api_cards_payload)

    api_sections_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets/TV900001/sections")
    assert api_sections_response.status_code == 200
    api_sections_payload = api_sections_response.json()
    assert len(api_sections_payload) > 0
    assert all("section_payload_json" not in item for item in api_sections_payload)
    assert_no_m15_business_leak(api_sections_payload)

    api_export_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets/TV900001/exports/markdown"
    )
    assert api_export_response.status_code == 200
    api_export_payload = api_export_response.json()
    assert api_export_payload["export_type"] == "markdown"
    assert "text/markdown" in api_export_payload["media_type"]
    assert_no_m15_business_leak(api_export_payload)

    api_trace_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/targets/TV900001/evidence/{first_short_ref}/trace"
    )
    assert api_trace_response.status_code == 200
    api_trace_payload = api_trace_response.json()
    assert api_trace_payload["short_ref"] == first_short_ref
    assert "内部复核" in api_trace_payload["trace_usage_cn"]

    api_run_list_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs")
    assert api_run_list_response.status_code == 200
    api_run_list_payload = api_run_list_response.json()
    assert api_run_list_payload["total"] >= 1
    assert any(item["run_id"] == m16_run_id for item in api_run_list_payload["items"])
    assert api_run_list_payload["items"][0]["run_id"] == m16_run_id

    api_latest_run_response = client.get(f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/latest")
    assert api_latest_run_response.status_code == 200
    assert api_latest_run_response.json()["run_id"] == m16_run_id

    api_modules_alias_response = client.get(
        f"/api/mvp/core3/v2/projects/{PROJECT_ID}/pipeline/runs/{m16_run_id}/modules"
    )
    assert api_modules_alias_response.status_code == 200
    assert api_modules_alias_response.json()["total"] == 23


def persist_module_run_result(session: Session, batch_id: str, payload: dict) -> None:
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=f"local-fixture-{payload['module_code'].lower()}",
            run_id="local-fixture-run",
            project_id=PROJECT_ID,
            category_code="TV",
            module_code=payload["module_code"],
            target_scope="batch",
            batch_id=batch_id,
            status=payload["status"],
            input_count=payload["input_count"],
            changed_input_count=payload["changed_input_count"],
            output_count=payload["output_count"],
            output_hash=payload["output_hash"],
            warnings_json=payload["warnings"],
            review_issue_summary_json={"count": len(payload["review_issues"]), "items": payload["review_issues"]},
            downstream_impact_json=payload["downstream_impacts"],
            summary_json=payload["summary_json"],
            started_at=parse_api_datetime(payload["started_at"]),
            finished_at=parse_api_datetime(payload["finished_at"]),
        )
    )
    session.commit()


def parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def assert_no_12m_keys(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert "12m" not in str(key).lower()
            assert_no_12m_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_12m_keys(item)


def assert_no_m08_forbidden_keys(value) -> None:
    forbidden = {
        "task_code",
        "target_group_code",
        "battlefield_code",
        "claim_value_layer",
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "business_conclusion",
        "report_payload",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m08_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m08_forbidden_keys(item)


def assert_no_m09_forbidden_keys(value) -> None:
    forbidden = {
        "target_group_code",
        "battlefield_code",
        "claim_value_layer",
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "business_conclusion",
        "report_payload",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m09_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m09_forbidden_keys(item)


def assert_no_m10_forbidden_keys(value) -> None:
    forbidden = {
        "battlefield_code",
        "claim_value_layer",
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "business_conclusion",
        "report_payload",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m10_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m10_forbidden_keys(item)


def assert_no_m11_forbidden_keys(value) -> None:
    forbidden = {
        "claim_value_layer",
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "business_conclusion",
        "report_payload",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m11_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m11_forbidden_keys(item)


def assert_no_m11_5_forbidden_keys(value) -> None:
    forbidden = {
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "business_conclusion",
        "report_payload",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m11_5_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m11_5_forbidden_keys(item)


def assert_no_m11_6_forbidden_keys(value) -> None:
    forbidden = {
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_score",
        "selection_slot",
        "core3_rank",
        "final_rank",
        "final_score",
        "business_conclusion",
        "report_payload",
        "report_content",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m11_6_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m11_6_forbidden_keys(item)


def assert_no_m11_7_forbidden_keys(value) -> None:
    forbidden = {
        "candidate_sku_code",
        "competitor_sku_code",
        "component_score",
        "competitor_score",
        "selection_slot",
        "core3_rank",
        "final_rank",
        "final_score",
        "business_conclusion",
        "report_payload",
        "report_content",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m11_7_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m11_7_forbidden_keys(item)


def assert_no_m12_forbidden_keys(value) -> None:
    forbidden = {
        "competitor_sku_code",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "final_rank",
        "final_score",
        "component_score",
        "competitor_score",
        "business_conclusion",
        "report_payload",
        "report_content",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m12_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m12_forbidden_keys(item)


def assert_no_m13_forbidden_keys(value) -> None:
    forbidden = {
        "competitor_sku_code",
        "competitor_role",
        "selection_slot",
        "core3_rank",
        "final_rank",
        "final_score",
        "competitor_score",
        "business_conclusion",
        "report_payload",
        "report_content",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m13_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m13_forbidden_keys(item)


def assert_no_m14_forbidden_keys(value) -> None:
    forbidden = {
        "report_payload",
        "report_content",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            assert str(key) not in forbidden
            assert_no_m14_forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m14_forbidden_keys(item)


def assert_no_m15_business_leak(value) -> None:
    forbidden_key_fragments = {
        "core3_",
        "uuid",
        "sql",
        "price_wavg_12m",
        "sales_volume_12m",
        "sales_amount_12m",
    }
    forbidden_text = {"AI 认为", "模型判断", "生成过程", "正在思考"}
    uuid_pattern = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            assert not any(fragment in key_text.lower() for fragment in forbidden_key_fragments)
            assert not uuid_pattern.search(key_text)
            assert_no_m15_business_leak(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_m15_business_leak(item)
    elif isinstance(value, str):
        assert not uuid_pattern.search(value)
        assert not any(term in value for term in forbidden_text)
