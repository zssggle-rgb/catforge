from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M07_AC_POOL_RULE_VERSION,
    CORE3_M07_AC_PRICE_BAND_RULE_VERSION,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M12C_AC_RULE_VERSION,
    CORE3_M12C_TV_RULE_VERSION,
    Core3SourceBatchStatus,
)
from app.services.core3_real_data.m12c_claim_value_quantification_service import (
    M12C_CLAIM_PARAM_FALLBACKS,
    M12C_PRODUCT_CATEGORY_INPUT_RULES,
    M12CRepository,
)
from app.services.core3_real_data import m12c_claim_value_quantification_service as m12c_service
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "core3_mvp"
AC_BATCH_ID = "m00_ac_main"
AC_SKU = "AC00099001"


def test_m12c_ac_input_rules_are_configured() -> None:
    config = catforge_pipeline.product_category_config("ac")

    assert config["claim_value_quantification_rule_version"] == CORE3_M12C_AC_RULE_VERSION
    assert (
        catforge_pipeline.product_category_config("tv")["claim_value_quantification_rule_version"]
        == CORE3_M12C_TV_RULE_VERSION
    )
    assert M12C_PRODUCT_CATEGORY_INPUT_RULES["AC"]["claim_rule_version"] == CORE3_M04C_AC_RULE_VERSION
    assert M12C_PRODUCT_CATEGORY_INPUT_RULES["AC"]["comment_rule_version"] == CORE3_M05C_AC_RULE_VERSION
    assert M12C_PRODUCT_CATEGORY_INPUT_RULES["AC"]["battlefield_rule_version"] == CORE3_M11C_AC_RULE_VERSION
    assert "airflow_volume_m3h" in M12C_CLAIM_PARAM_FALLBACKS["ac_claim_large_airflow_coverage"]


def test_m12c_quality_assessment_only_reads_referenced_claim_rows() -> None:
    rows = [
        {
            "claim_code": "target_claim",
            "quality_flags_json": [],
            "supporting_dimensions_json": {
                "quality_assessment": {
                    "amount_quantification_status": "ready",
                    "relative_comparison_status": "ready",
                }
            },
        },
        {
            "claim_code": "unrelated_claim",
            "quality_flags_json": ["l4_threshold_only", "l4_threshold_only_no_amount"],
            "supporting_dimensions_json": {
                "quality_assessment": {
                    "amount_quantification_status": "not_quantifiable",
                    "relative_comparison_status": "ready",
                }
            },
        },
    ]

    result = m12c_service.assess_m12c_claim_value_quality(
        rows,
        referenced_claim_codes=("target_claim",),
    )

    assert result["availability"] == "available"
    assert result["usability"] == "usable"
    assert result["review_required"] is False
    assert result["selected_claim_codes"] == ["target_claim"]
    assert result["amount_quantification_status"] == "ready"
    assert result["limitation_flags"] == []


def test_m12c_amount_and_single_group_limitations_stay_claim_scoped() -> None:
    amount_limited = m12c_service.assess_m12c_claim_value_quality(
        [
            {
                "claim_code": "amount_limited_claim",
                "quality_flags_json": [
                    "relaxed_pool_not_amount_quantifiable",
                    "l4_threshold_only_no_amount",
                ],
            }
        ],
        referenced_claim_codes=("amount_limited_claim",),
    )
    single_group = m12c_service.assess_m12c_claim_value_quality(
        [
            {
                "claim_code": "single_group_claim",
                "quality_flags_json": ["single_sku_comparison_group"],
            }
        ],
        referenced_claim_codes=("single_group_claim",),
    )

    assert amount_limited["usability"] == "usable"
    assert amount_limited["amount_quantification_status"] == "not_quantifiable"
    assert amount_limited["review_required"] is False
    assert single_group["usability"] == "usable"
    assert single_group["amount_quantification_status"] == "ready"
    assert single_group["relative_comparison_status"] == "limited"


def test_m12c_not_quantifiable_claim_never_outputs_amount_or_sales_lift() -> None:
    result = m12c_service._claim_contribution_amounts(
        amount_ready=False,
        business_claim_type=m12c_service.M12C_CLAIM_TYPE_PREMIUM,
        effective_price_space=Decimal("2000"),
        weekly_sales_space=Decimal("50"),
        weekly_amount_space=Decimal("100000"),
        weighted_share=Decimal("0.8"),
        coefficient=Decimal("1"),
    )

    assert result == {
        "estimated_price_premium_abs": Decimal("0.0000"),
        "estimated_weekly_sales_lift_abs": Decimal("0.000000"),
        "estimated_weekly_sales_amount_lift_abs": Decimal("0.000000"),
    }


def test_m07_market_rule_versions_are_isolated_by_product_category() -> None:
    tv_config = catforge_pipeline.product_category_config("tv")
    ac_config = catforge_pipeline.product_category_config("ac")

    assert tv_config["market_rule_version"] == CORE3_M07_RULE_VERSION
    assert tv_config["market_price_band_rule_version"] == CORE3_M07_PRICE_BAND_RULE_VERSION
    assert tv_config["market_pool_rule_version"] == CORE3_M07_POOL_RULE_VERSION
    assert ac_config["market_rule_version"] == CORE3_M07_RULE_VERSION
    assert ac_config["market_price_band_rule_version"] == CORE3_M07_AC_PRICE_BAND_RULE_VERSION
    assert ac_config["market_pool_rule_version"] == CORE3_M07_AC_POOL_RULE_VERSION


def test_m12c_repository_reads_ac_claim_and_comment_rules() -> None:
    session = make_session()
    seed_ac_claim_and_comment(session)

    repo = M12CRepository(
        Core3RepositoryContext(db=session, project_id=PROJECT_ID, category_code="AC")
    )

    claims = repo.list_claim_states(
        batch_id=AC_BATCH_ID,
        product_category="AC",
        sku_codes={AC_SKU},
    )
    comments = repo.list_comment_states(batch_id=AC_BATCH_ID, product_category="AC")

    assert set(claims) == {AC_SKU}
    assert "ac_claim_large_airflow_coverage" in claims[AC_SKU]
    assert claims[AC_SKU]["ac_claim_large_airflow_coverage"].supporting_param_codes == ("airflow_volume_m3h",)
    assert set(comments) == {AC_SKU}
    assert comments[AC_SKU].supported_claim_codes == ("ac_claim_large_airflow_coverage",)


def test_m12c_repository_reads_ac_battlefield_rules() -> None:
    session = make_session()
    seed_ac_battlefield_profile(session)

    repo = M12CRepository(
        Core3RepositoryContext(db=session, project_id=PROJECT_ID, category_code="AC")
    )

    semantics = repo.list_semantic_states(
        batch_id=AC_BATCH_ID,
        product_category="AC",
        analysis_population="claim_value_ready_with_comment",
        market_window="full_observed_window",
    )

    assert semantics[AC_SKU].contexts == (
        (
            "battlefield",
            "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH",
            "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH",
            "primary",
        ),
    )


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3SkuClaimFactProfile.__table__,
        entities.Core3SkuClaimFact.__table__,
        entities.Core3SkuCommentFactProfile.__table__,
        entities.Core3SkuValueBattlefieldProfile.__table__,
        entities.Core3SkuValueBattlefieldScore.__table__,
        entities.Core3SemanticMarketAllocation.__table__,
        entities.Core3SemanticMarketSkuContribution.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)
    session = Session(engine)
    seed_foundation(session)
    return session


def seed_foundation(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="AC"))
    session.add(
        entities.Core3SourceBatch(
            batch_id=AC_BATCH_ID,
            project_id=PROJECT_ID,
            category_code="AC",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="ac-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    session.commit()


def seed_ac_claim_and_comment(session: Session) -> None:
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id="claim-profile-ac00099001",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M04C_AC_TAXONOMY_VERSION,
            sku_code=AC_SKU,
            model_name="KFR-72LW",
            brand_name="海信",
            raw_claim_count=1,
            matched_claim_count=1,
            fact_claim_count=1,
            unsupported_claim_count=0,
            claim_texts_json=["大风量"],
            claim_codes=["ac_claim_large_airflow_coverage"],
            fact_claim_codes=["ac_claim_large_airflow_coverage"],
            unsupported_claim_codes=[],
            dimension_profile_json={"airflow_comfort": {"fact_claim_count": 1}},
            dimension_position_profile_json={"airflow_comfort": ["large_airflow"]},
            claim_summary_json={"premium_claim_candidates": ["ac_claim_large_airflow_coverage"]},
            evidence_ids=["ev-claim-ac00099001"],
            confidence=Decimal("0.9000"),
            profile_hash="hash-claim-ac00099001",
            rule_version=CORE3_M04C_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFact(
            claim_fact_id="claim-fact-ac00099001-airflow",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M04C_AC_TAXONOMY_VERSION,
            sku_code=AC_SKU,
            model_name="KFR-72LW",
            brand_name="海信",
            source_claim_key="selling-point:1",
            raw_claim_text="大风量",
            clean_claim_text="大风量",
            claim_code="ac_claim_large_airflow_coverage",
            claim_name="大风量/全域送风",
            claim_dimension="airflow_comfort",
            claim_subtype="large_airflow",
            claim_kind="product_experience",
            match_type="seed_rule",
            match_score=Decimal("0.9500"),
            param_support_status="supported",
            param_support_level="strong_numeric_or_tier_support",
            param_support_specificity="specific",
            supporting_param_codes=["airflow_volume_m3h"],
            primary_supporting_param_codes=["airflow_volume_m3h"],
            generic_support_param_codes=[],
            supporting_param_snapshot_json={"airflow_volume_m3h": {"normalized_value": 1500}},
            support_explanation="循环风量支撑大风量卖点。",
            canonical_claim_code="ac_claim_large_airflow_coverage",
            canonical_claim_name="大风量/全域送风",
            wtp_input_guard="eligible_strong_param",
            fact_claim_flag=True,
            service_separate_flag=False,
            evidence_ids=["ev-claim-ac00099001"],
            confidence=Decimal("0.9000"),
            fact_hash="hash-claim-fact-ac00099001-airflow",
            rule_version=CORE3_M04C_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id="comment-profile-ac00099001",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M05C_AC_TAXONOMY_VERSION,
            sku_code=AC_SKU,
            model_name="KFR-72LW",
            brand_name="海信",
            comment_sentence_count=10,
            matched_sentence_count=8,
            fact_atom_count=8,
            product_fact_sentence_count=8,
            positive_sentence_count=7,
            negative_sentence_count=0,
            neutral_sentence_count=1,
            service_excluded_sentence_count=0,
            dimension_summary_json={"airflow_comfort": {"positive": 6}},
            signal_summary_json={"use_case_signal": ["客厅大空间"]},
            param_comment_support_json={"airflow_volume_m3h": {"positive": 3}},
            claim_comment_support_json={"ac_claim_large_airflow_coverage": {"positive": 5}},
            supported_param_codes=["airflow_volume_m3h"],
            contradicted_param_codes=[],
            supported_claim_codes=["ac_claim_large_airflow_coverage"],
            contradicted_claim_codes=[],
            evidence_examples_json=[{"text": "客厅制冷快，风量大"}],
            evidence_ids=["ev-comment-ac00099001"],
            confidence=Decimal("0.8800"),
            profile_hash="hash-comment-ac00099001",
            rule_version=CORE3_M05C_AC_RULE_VERSION,
        )
    )
    session.commit()


def seed_ac_battlefield_profile(session: Session) -> None:
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id="m11c-profile-ac00099001",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M11C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_AC_RULE_VERSION,
            sku_code=AC_SKU,
            model_name="KFR-72LW",
            brand_name="海信",
            size_tier="3hp_floor",
            price_band_in_size_tier="high",
            primary_battlefield_code="BF_FLOOR_3_PREMIUM_COMFORT_HEALTH",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=[],
            opportunity_battlefield_codes_json=[],
            drag_factor_battlefield_codes_json=[],
            battlefield_summary_json={"primary_reason_cn": "3匹柜机高端舒适健康战场。"},
            confidence=Decimal("0.8400"),
            evidence_ids_json=["ev-bf-ac00099001"],
            profile_hash="hash-bf-ac00099001",
        )
    )
    session.commit()
