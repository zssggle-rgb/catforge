from sqlalchemy import select

from app.cli import catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import CORE3_M03B_AC_RULE_VERSION
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
