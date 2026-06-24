from sqlalchemy import select

from app.cli import catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import CORE3_M03B_AC_RULE_VERSION, Core3RunStatus, M07_ANALYSIS_WINDOWS
from tests.core3_real_data.test_m03b_sku_param_profile_runner import BATCH_ID, PROJECT_ID, make_session, seed_ac_param_evidence


def test_pipeline_cli_natural_language_runs_ac_param_profile():
    session = make_session()
    seed_ac_param_evidence(session)

    result = catforge_pipeline.answer_natural_language(
        session,
        question="生成空调 SKU 参数画像",
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id=BATCH_ID,
        product_category="auto",
        force_rebuild=True,
    )

    assert result["status"] == "ok"
    assert result["product_category"] == "AC"
    assert result["routed_command"] == "run-param-profile"
    assert result["summary"]["sku_profile_count"] == 1

    profile = session.execute(
        select(entities.Core3SkuParamProfile)
        .where(entities.Core3SkuParamProfile.sku_code == "AC00000001")
        .where(entities.Core3SkuParamProfile.rule_version == CORE3_M03B_AC_RULE_VERSION)
    ).scalar_one()
    assert profile.param_values_json["dimension_tier_profile"]["health"] == "health_fresh_air"


def test_pipeline_cli_natural_language_runs_market_profile(monkeypatch):
    session = make_session()
    captured_calls = []

    class FakeMarketProfileRunner:
        def __init__(self, db):
            self.db = db

        def run_batch(self, **kwargs):
            captured_calls.append(kwargs)

            class Result:
                status = Core3RunStatus.SUCCESS
                input_count = 2
                output_count = 4
                changed_input_count = 4
                warnings = []
                summary_json = {
                    "market_profile_count": 1,
                    "market_signal_count": 1,
                    "comparable_pool_count": 1,
                    "pool_member_count": 1,
                    "review_required_count": 0,
                }

            return Result()

    monkeypatch.setattr(catforge_pipeline, "MarketProfileRunner", FakeMarketProfileRunner)
    monkeypatch.setattr(catforge_pipeline, "resolve_source_batch_id", lambda db, project_id, source_category_code, batch_id: BATCH_ID)

    result = catforge_pipeline.answer_natural_language(
        session,
        question="重新生成 TV00027354 的市场画像",
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id="latest",
        product_category="auto",
        input_source="auto",
        force_rebuild=False,
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "run-market-profile"
    assert len(captured_calls) == len(M07_ANALYSIS_WINDOWS)
    assert [call["analysis_windows"][0] for call in captured_calls] == [window.value for window in M07_ANALYSIS_WINDOWS]
    assert {call["sku_scope"] for call in captured_calls} == {("TV00027354",)}
    assert {call["batch_id"] for call in captured_calls} == {BATCH_ID}
    assert {call["run_id"] for call in captured_calls} == {result["run_id"]}
    assert {call["module_run_id"] for call in captured_calls} == {result["module_run_id"]}
    assert {call["product_category"] for call in captured_calls} == {"TV"}

    pipeline_run = session.get(entities.Core3V2PipelineRun, result["run_id"])
    module_run = session.get(entities.Core3V2ModuleRun, result["module_run_id"])
    assert pipeline_run is not None
    assert pipeline_run.status == Core3RunStatus.SUCCESS.value
    assert module_run is not None
    assert module_run.status == Core3RunStatus.SUCCESS.value
    assert module_run.output_count == 4 * len(M07_ANALYSIS_WINDOWS)


def test_pipeline_cli_runs_market_profile_in_sku_chunks(monkeypatch):
    session = make_session()
    captured_calls = []

    class FakeMarketProfileRunner:
        def __init__(self, db):
            self.db = db

        def run_batch(self, **kwargs):
            captured_calls.append(kwargs)

            class Result:
                status = Core3RunStatus.SUCCESS
                input_count = 2
                output_count = 4
                changed_input_count = 4
                warnings = []
                review_issues = []
                downstream_impacts = []
                summary_json = {
                    "sku_count": 2,
                    "processed_sku_count": len(kwargs["sku_scope"]),
                    "market_profile_count": len(kwargs["sku_scope"]),
                    "market_signal_count": len(kwargs["sku_scope"]) * 2,
                    "comparable_pool_count": len(kwargs["sku_scope"]),
                    "pool_member_count": len(kwargs["sku_scope"]),
                    "review_required_count": 0,
                    "created_output_count": 4,
                    "updated_output_count": 0,
                    "reused_output_count": 0,
                    "analysis_windows": list(kwargs["analysis_windows"]),
                }

            return Result()

    monkeypatch.setattr(catforge_pipeline, "MarketProfileRunner", FakeMarketProfileRunner)
    monkeypatch.setattr(catforge_pipeline, "resolve_source_batch_id", lambda db, project_id, source_category_code, batch_id: BATCH_ID)

    result = catforge_pipeline.run_market_profile(
        session,
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id="latest",
        sku_scope=("TV00027354", "TV00029115", "TV00030000"),
        analysis_windows=("full_observed_window",),
        sku_chunk_size=2,
    )

    assert result["status"] == "ok"
    assert result["executed_chunk_count"] == 2
    assert [call["sku_scope"] for call in captured_calls] == [("TV00027354", "TV00029115"), ("TV00030000",)]
    assert {call["product_category"] for call in captured_calls} == {"TV"}
    assert result["summary"]["market_profile_count"] == 3


def test_pipeline_cli_runs_ac_market_profile_with_ac_prefix(monkeypatch):
    session = make_session()
    captured_calls = []

    class FakeMarketProfileRunner:
        def __init__(self, db):
            self.db = db

        def run_batch(self, **kwargs):
            captured_calls.append(kwargs)

            class Result:
                status = Core3RunStatus.SUCCESS
                input_count = 2
                output_count = 4
                changed_input_count = 4
                warnings = []
                review_issues = []
                downstream_impacts = []
                summary_json = {
                    "sku_count": len(kwargs["sku_scope"]),
                    "processed_sku_count": len(kwargs["sku_scope"]),
                    "market_profile_count": len(kwargs["sku_scope"]),
                    "market_signal_count": len(kwargs["sku_scope"]),
                    "comparable_pool_count": len(kwargs["sku_scope"]),
                    "pool_member_count": len(kwargs["sku_scope"]),
                    "review_required_count": 0,
                    "created_output_count": 4,
                    "updated_output_count": 0,
                    "reused_output_count": 0,
                    "analysis_windows": list(kwargs["analysis_windows"]),
                }

            return Result()

    monkeypatch.setattr(catforge_pipeline, "MarketProfileRunner", FakeMarketProfileRunner)
    monkeypatch.setattr(catforge_pipeline, "resolve_source_batch_id", lambda db, project_id, source_category_code, batch_id: BATCH_ID)
    monkeypatch.setattr(
        catforge_pipeline,
        "list_sku_codes_with_prefix",
        lambda db, project_id, category_code, batch_id, prefix: ["AC00000001", "AC00000002"] if prefix == "AC" else [],
    )

    result = catforge_pipeline.run_market_profile(
        session,
        project_id=PROJECT_ID,
        source_category_code="AC",
        batch_id="latest",
        product_category="AC",
        analysis_windows=("full_observed_window",),
        sku_chunk_size=10,
    )

    assert result["status"] == "ok"
    assert result["product_category"] == "AC"
    assert result["product_category_label_cn"] == "空调"
    assert result["sku_scope_mode"] == "ac_prefix_default"
    assert captured_calls[0]["category_code"] == "AC"
    assert captured_calls[0]["product_category"] == "AC"
    assert captured_calls[0]["sku_scope"] == ("AC00000001", "AC00000002")
