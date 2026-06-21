from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import catforge_insight, catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M09C_TV_TAXONOMY_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.m09c_user_task_service import M09CRunner
from tests.core3_real_data.test_m10c_target_group_profile import (
    BATCH_ID,
    PROJECT_ID,
    SKU_FAMILY,
    SKU_SENIOR,
    SKU_SMART,
    make_session as make_fact_layer_session,
)


def make_session() -> Session:
    session = make_fact_layer_session()
    bind = session.get_bind()
    for table in [
        entities.Core3M09cSkuUserTaskProfile.__table__,
        entities.Core3M09cSkuUserTaskScore.__table__,
        entities.Core3M09cUserTaskCoverage.__table__,
    ]:
        table.create(bind=bind, checkfirst=True)
    return session


def test_m09c_runner_generates_user_task_profiles_and_coverage() -> None:
    session = make_session()

    result = M09CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    session.commit()

    assert result.status == Core3RunStatus.SUCCESS
    assert result.summary_json["sku_count"] == 3
    assert result.summary_json["user_task_count"] == 12

    family_profile = session.execute(
        select(entities.Core3M09cSkuUserTaskProfile).where(entities.Core3M09cSkuUserTaskProfile.sku_code == SKU_FAMILY)
    ).scalar_one()
    assert family_profile.primary_user_task_code == "TASK_MAINSTREAM_LIVING_VIEWING"
    assert family_profile.size_tier == "xlarge_70_85"
    assert family_profile.price_band_in_size_tier == "low"

    smart_score = session.execute(
        select(entities.Core3M09cSkuUserTaskScore)
        .where(entities.Core3M09cSkuUserTaskScore.sku_code == SKU_SMART)
        .where(entities.Core3M09cSkuUserTaskScore.user_task_code == "TASK_SMART_CASTING_IOT")
    ).scalar_one()
    assert smart_score.relation_status == "brand_claimed_task"

    senior_score = session.execute(
        select(entities.Core3M09cSkuUserTaskScore)
        .where(entities.Core3M09cSkuUserTaskScore.sku_code == SKU_SENIOR)
        .where(entities.Core3M09cSkuUserTaskScore.user_task_code == "TASK_SENIOR_EASY_OPERATION")
    ).scalar_one()
    assert senior_score.relation_status == "drag_factor_task"

    coverage_rows = session.execute(select(entities.Core3M09cUserTaskCoverage)).scalars().all()
    assert len(coverage_rows) == 12


def test_m09c_pipeline_and_insight_cli_query_user_tasks() -> None:
    session = make_session()

    pipeline_result = catforge_pipeline.run_user_task(
        session,
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    assert pipeline_result["status"] == "ok"
    assert pipeline_result["summary"]["profile_count"] == 3

    sku_profile = catforge_insight.query_sku_user_task(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="75F-Family",
        include_scores=True,
    )
    coverage = catforge_insight.query_user_task_skus(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        user_task_code="TASK_MAINSTREAM_LIVING_VIEWING",
        sku_limit=10,
    )
    natural = catforge_insight.answer_natural_language(
        session,
        question="查 75F-Family 的用户任务",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    taxonomy = catforge_insight.query_user_task_taxonomy(product_category="TV")

    assert sku_profile["status"] == "ok"
    assert sku_profile["primary_user_task_code"] == "TASK_MAINSTREAM_LIVING_VIEWING"
    assert any(item["user_task_code"] == "TASK_MAINSTREAM_LIVING_VIEWING" for item in sku_profile["scores"])
    assert SKU_FAMILY in coverage["sku_codes"]
    assert natural["routed_command"] == "sku-user-task"
    assert natural["primary_user_task_code"] == "TASK_MAINSTREAM_LIVING_VIEWING"
    assert taxonomy["user_task_count"] == 12
    assert taxonomy["taxonomy_version"] == CORE3_M09C_TV_TAXONOMY_VERSION
