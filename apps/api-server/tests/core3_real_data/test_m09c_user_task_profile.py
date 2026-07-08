from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import catforge_insight, catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    Core3ModuleCode,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    Core3RunStatus,
    Core3SourceBatchStatus,
)
from app.services.core3_real_data.m09c_user_task_service import (
    M09CUserTaskTaxonomyLoader,
    M09CRunner,
    _failed_result,
    ac_user_task_taxonomy_v0_1,
)
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

    assert result.status == Core3RunStatus.WARNING
    assert result.summary_json["sku_count"] == 2
    assert result.summary_json["user_task_count"] == 12
    assert result.summary_json["comment_missing_excluded_sku_count"] == 1

    family_profile = session.execute(
        select(entities.Core3M09cSkuUserTaskProfile).where(
            entities.Core3M09cSkuUserTaskProfile.sku_code == SKU_FAMILY
        )
    ).scalar_one()
    assert family_profile.primary_user_task_code == "TASK_MAINSTREAM_LIVING_VIEWING"
    assert family_profile.size_tier == "xlarge_70_85"
    assert family_profile.price_band_in_size_tier == "low"

    smart_profile = session.execute(
        select(entities.Core3M09cSkuUserTaskProfile).where(
            entities.Core3M09cSkuUserTaskProfile.sku_code == SKU_SMART
        )
    ).scalar_one_or_none()
    assert smart_profile is None

    senior_score = session.execute(
        select(entities.Core3M09cSkuUserTaskScore)
        .where(entities.Core3M09cSkuUserTaskScore.sku_code == SKU_SENIOR)
        .where(
            entities.Core3M09cSkuUserTaskScore.user_task_code
            == "TASK_SENIOR_EASY_OPERATION"
        )
    ).scalar_one()
    assert senior_score.relation_status == "drag_factor_task"

    coverage_rows = (
        session.execute(select(entities.Core3M09cUserTaskCoverage)).scalars().all()
    )
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
    assert pipeline_result["status"] == "warning"
    assert pipeline_result["summary"]["profile_count"] == 2

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
    assert any(
        item["user_task_code"] == "TASK_MAINSTREAM_LIVING_VIEWING"
        for item in sku_profile["scores"]
    )
    assert SKU_FAMILY in coverage["sku_codes"]
    assert natural["routed_command"] == "sku-user-task"
    assert natural["primary_user_task_code"] == "TASK_MAINSTREAM_LIVING_VIEWING"
    assert taxonomy["user_task_count"] == 12
    assert taxonomy["taxonomy_version"] == CORE3_M09C_TV_TAXONOMY_VERSION


def test_m09c_reads_serving_comment_profile_from_newer_batch() -> None:
    session = make_session()
    comment_batch_id = "m00_202606230001_comment"
    session.add(
        entities.Core3SourceBatch(
            batch_id=comment_batch_id,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 23, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id="comment-profile-newer-smart",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=comment_batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=SKU_SMART,
            model_name="75S-Smart",
            brand_name="TCL",
            comment_sentence_count=1,
            matched_sentence_count=1,
            fact_atom_count=1,
            product_fact_sentence_count=1,
            positive_sentence_count=1,
            negative_sentence_count=0,
            dimension_summary_json={},
            signal_summary_json={},
            param_comment_support_json={},
            claim_comment_support_json={},
            polarity_summary_json={},
            evidence_examples_json=[],
            supported_param_codes=[],
            contradicted_param_codes=[],
            unmentioned_param_codes=[],
            supported_claim_codes=[],
            contradicted_claim_codes=[],
            unmentioned_claim_codes=[],
            evidence_ids=["ev-comment-profile-newer-smart"],
            quality_flags=[],
            confidence=1,
            profile_hash="sha256:comment-profile-newer-smart",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3CommentFactAtom(
            comment_fact_id="comment-fact-newer-smart-1",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=comment_batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=SKU_SMART,
            model_name="75S-Smart",
            brand_name="TCL",
            source_comment_key="comment-newer-smart-1",
            clean_comment_text="投屏方便，语音控制和智能联动都顺手",
            dimension_code="use_case_signal",
            dimension_name="用途信号",
            subdimension_code="use_casting_online",
            subdimension_name="use_casting_online",
            dimension_type="use_case_signal",
            polarity="positive",
            evidence_strength="strong",
            support_relation="supports_sku_param_claim",
            support_target_type="signal",
            supported_param_codes=[],
            contradicted_param_codes=[],
            supported_claim_codes=[],
            contradicted_claim_codes=[],
            param_snapshot_json={},
            claim_snapshot_json={},
            signal_payload_json={},
            extraction_payload_json={},
            evidence_ids=["ev-comment-newer-smart-1"],
            quality_flags=[],
            confidence=1,
            fact_hash="sha256:comment-newer-smart-1",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )

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
    assert result.summary_json["comment_missing_excluded_sku_count"] == 0

    smart_score = session.execute(
        select(entities.Core3M09cSkuUserTaskScore)
        .where(entities.Core3M09cSkuUserTaskScore.sku_code == SKU_SMART)
        .where(
            entities.Core3M09cSkuUserTaskScore.user_task_code
            == "TASK_SMART_CASTING_IOT"
        )
    ).scalar_one()
    assert smart_score.comment_task_need_score > 0


def test_m09c_ac_user_task_taxonomy_is_published() -> None:
    taxonomy = ac_user_task_taxonomy_v0_1()
    loaded = M09CUserTaskTaxonomyLoader().load(
        CORE3_M09C_AC_TAXONOMY_VERSION, product_category="AC"
    )
    config = catforge_pipeline.product_category_config("ac")
    insight_result = catforge_insight.query_user_task_taxonomy(product_category="AC")

    assert taxonomy.taxonomy_version == CORE3_M09C_AC_TAXONOMY_VERSION
    assert loaded.product_category == "AC"
    assert config["user_task_taxonomy_version"] == CORE3_M09C_AC_TAXONOMY_VERSION
    assert insight_result["user_task_count"] == 12
    assert "TASK_FAST_COOL_HEAT" in taxonomy.user_tasks_by_code
    assert "TASK_LARGE_SPACE_COVERAGE" in taxonomy.user_tasks_by_code


def test_m09c_failed_result_uses_current_review_issue_schema() -> None:
    result = _failed_result(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id="run-test",
        started_at=datetime.now(timezone.utc),
        error_code="m09c_user_task_failed",
        message_cn="用户任务画像生成失败",
        error_message="上游事实层缺失",
    )

    assert result.status == Core3RunStatus.FAILED
    assert result.review_issues[0].issue_code == "m09c_user_task_failed"
    assert result.review_issues[0].severity == "blocker"
    assert result.review_issues[0].source_module == Core3ModuleCode.M09C
    assert result.review_issues[0].object_type == "module_run"
    assert result.review_issues[0].object_id == "run-test"
