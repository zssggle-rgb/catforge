import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_analyst
from app.models import entities
from app.services.core3_real_data import m12c_claim_value_quantification_service as m12c_service
from app.services.core3_real_data.analyst import competitor_answer
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.sop_orchestrators import CLAIM_VALUE_REPORT_LIMIT, SopOrchestrators
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_AC_RULE_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_AC_RULE_VERSION,
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M11D_RULE_VERSION,
    CORE3_M12C_RULE_VERSION,
)


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_analyst_test"
AC_BATCH_ID = "m00_ac_analyst_test"


def _m12c_test_pool() -> m12c_service.ClaimPool:
    return m12c_service.ClaimPool(
        claim_code="tv_claim_wall_mount_design",
        claim_name="壁画贴墙",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="mid_high",
        sku_codes=("sku-a", "sku-b", "sku-c"),
        with_claim_skus=("sku-a", "sku-b"),
        without_claim_skus=("sku-c",),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
    )


def test_m12c_missing_high_price_claim_is_retained_as_intercept_or_price_up() -> None:
    metric = {
        "with_price_median": Decimal("6000"),
        "price_premium_abs": Decimal("500"),
        "weekly_sales_lift_abs": Decimal("12"),
        "weekly_sales_amount_lift_abs": Decimal("60000"),
        "effect_confidence": Decimal("0.8000"),
    }
    pool = _m12c_test_pool()

    lower_price_role = m12c_service._claim_role(
        has_claim=False,
        metric=metric,
        pool=pool,
        param_strength=Decimal("0"),
        comment_strength=Decimal("0"),
        semantic_strength=Decimal("0.6000"),
        has_negative=False,
        market_price=Decimal("5200"),
    )
    higher_price_role = m12c_service._claim_role(
        has_claim=False,
        metric=metric,
        pool=pool,
        param_strength=Decimal("0"),
        comment_strength=Decimal("0"),
        semantic_strength=Decimal("0.6000"),
        has_negative=False,
        market_price=Decimal("6200"),
    )

    assert lower_price_role == m12c_service.M12C_ROLE_HIGH_PRICE_INTERCEPT
    assert higher_price_role == m12c_service.M12C_ROLE_PRICE_UP
    assert lower_price_role in m12c_service.OPPORTUNITY_ROLES
    assert higher_price_role in m12c_service.OPPORTUNITY_ROLES


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
        entities.Core3CleanMarketWeekly.__table__,
        entities.Core3SkuMarketProfile.__table__,
        entities.Core3SkuParamProfile.__table__,
        entities.Core3SkuClaimFactProfile.__table__,
        entities.Core3SkuCommentFactProfile.__table__,
        entities.Core3M09cSkuUserTaskProfile.__table__,
        entities.Core3M10cSkuTargetGroupProfile.__table__,
        entities.Core3SkuValueBattlefieldProfile.__table__,
        entities.Core3SkuValueBattlefieldScore.__table__,
        entities.Core3SemanticMarketDimensionSummary.__table__,
        entities.Core3SemanticMarketSkuContribution.__table__,
        entities.Core3SemanticMarketAllocation.__table__,
        entities.Core3ClaimValueContextPool.__table__,
        entities.Core3ClaimValuePoolMetric.__table__,
        entities.Core3SkuClaimValueQuantification.__table__,
        entities.Core3SkuClaimContributionAttribution.__table__,
        entities.Core3ClaimValueDimensionSummary.__table__,
        entities.Core3ClaimValueReviewIssue.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)
    session = Session(engine)
    seed_data(session)
    return session


def seed_data(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
            status="registered",
        )
    )
    seed_market_profile(session, sku_code="TV00029112", model_name="65E7Q", brand_name="海信", size=65, price=Decimal("4999"), volume=Decimal("1200"))
    seed_market_profile(session, sku_code="TV00030001", model_name="65E7Q Pro", brand_name="海信", size=65, price=Decimal("6999"), volume=Decimal("800"))
    seed_market_profile(session, sku_code="TV00040001", model_name="65A7H PRO", brand_name="创维", size=65, price=Decimal("4700"), volume=Decimal("900"))
    seed_market_profile(session, sku_code="TV00040002", model_name="L65MC-SP", brand_name="小米", size=65, price=Decimal("5010"), volume=Decimal("1500"))
    seed_market_profile(session, sku_code="TV00040003", model_name="65Q9L PRO", brand_name="TCL", size=65, price=Decimal("4650"), volume=Decimal("850"))
    seed_market_profile(
        session,
        sku_code="TV00040004",
        model_name="65A6F ULTRA",
        brand_name="创维",
        size=65,
        price=Decimal("3700"),
        volume=Decimal("1400"),
        price_band="mid",
    )
    seed_fact_profiles(session)
    seed_candidate_fact_profiles(session)
    seed_business_competitor_profiles(session)
    seed_weekly_market(session)
    seed_semantic_space(session)
    seed_m12c_claim_value(session)
    session.commit()


def seed_market_profile(
    session: Session,
    *,
    sku_code: str,
    model_name: str,
    brand_name: str,
    size: int,
    price: Decimal,
    volume: Decimal,
    price_band: str = "mid_high",
) -> None:
    size_tier = "large_60_69"
    amount = price * volume
    session.add(
        entities.Core3SkuMarketProfile(
            profile_id=f"m07-{sku_code}",
            sku_market_profile_id=f"m07-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            analysis_window="full_observed_window",
            period_start_raw="26W01",
            period_end_raw="26W12",
            period_start_week_index=1,
            period_end_week_index=12,
            active_week_count=12,
            market_row_count=24,
            platform_count=2,
            screen_size_inch=Decimal(str(size)),
            size_segment=size_tier,
            screen_size_class=size_tier,
            market_pool_key=f"tv:{size_tier}:online:full_observed_window",
            size_param_confidence=Decimal("0.9500"),
            sales_volume_total=volume,
            sales_amount_total=amount,
            price_wavg=price,
            price_median=price,
            price_latest=float(price),
            price_per_inch=price / Decimal(size),
            main_channel_type="online",
            main_platform="test_platform",
            platform_share_json={"test_platform": {"volume_share": 1.0, "amount_share": 1.0}},
            price_band_category=price_band,
            price_band_size=price_band,
            price_band_rule_version=CORE3_M07_PRICE_BAND_RULE_VERSION,
            price_percentile_in_size=Decimal("0.700000"),
            volume_percentile_in_size=Decimal("0.800000"),
            amount_percentile_in_size=Decimal("0.750000"),
            same_pool_sku_count=8,
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=[f"ev-market-{sku_code}"],
            market_evidence_ids=[f"ev-market-{sku_code}"],
            rule_version=CORE3_M07_RULE_VERSION,
            input_fingerprint=f"fp-m07-{sku_code}",
            result_hash=f"hash-m07-{sku_code}",
        )
    )


def seed_ac_analyst_data(session: Session) -> None:
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
            status="registered",
        )
    )
    seed_ac_market_profile(
        session,
        sku_code="AC00038063",
        model_name="KFR-88LW/N8KS1-1U",
        brand_name="美的",
        size_tier="floor_hp_3_plus",
        price=Decimal("7208"),
        volume=Decimal("13916"),
        price_band="unknown",
    )
    seed_ac_market_profile(
        session,
        sku_code="AC00028640",
        model_name="KFR-72LW/BDN8Y-YH200",
        brand_name="海信",
        size_tier="floor_hp_3",
        price=Decimal("5899"),
        volume=Decimal("8600"),
        price_band="mid_high",
    )
    seed_ac_market_profile(
        session,
        sku_code="AC00029751",
        model_name="KFR-72LW/N8MXA1",
        brand_name="格力",
        size_tier="floor_hp_3",
        price=Decimal("6599"),
        volume=Decimal("7600"),
        price_band="high",
    )
    for sku_code, model_name, brand_name, size_tier in [
        ("AC00038063", "KFR-88LW/N8KS1-1U", "美的", "floor_hp_3_plus"),
        ("AC00028640", "KFR-72LW/BDN8Y-YH200", "海信", "floor_hp_3"),
        ("AC00029751", "KFR-72LW/N8MXA1", "格力", "floor_hp_3"),
    ]:
        seed_ac_fact_profiles(session, sku_code=sku_code, model_name=model_name, brand_name=brand_name, size_tier=size_tier)
    seed_ac_battlefield_score(
        session,
        sku_code="AC00038063",
        model_name="KFR-88LW/N8KS1-1U",
        brand_name="美的",
        size_tier="floor_hp_3_plus",
        sample_peer_codes=["AC00028640", "AC00029751"],
    )
    session.commit()


def seed_ac_market_profile(
    session: Session,
    *,
    sku_code: str,
    model_name: str,
    brand_name: str,
    size_tier: str,
    price: Decimal,
    volume: Decimal,
    price_band: str,
) -> None:
    amount = price * volume
    session.add(
        entities.Core3SkuMarketProfile(
            profile_id=f"m07-{sku_code}",
            sku_market_profile_id=f"m07-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            analysis_window="full_observed_window",
            period_start_raw="26W01",
            period_end_raw="26W24",
            period_start_week_index=1,
            period_end_week_index=24,
            active_week_count=24,
            market_row_count=24,
            platform_count=1,
            size_segment=size_tier,
            screen_size_class=size_tier,
            market_pool_key=f"ac:{size_tier}:online:full_observed_window",
            sales_volume_total=volume,
            sales_amount_total=amount,
            price_wavg=price,
            price_median=price,
            price_latest=float(price),
            main_channel_type="online",
            main_platform="test_platform",
            platform_share_json={"test_platform": {"volume_share": 1.0, "amount_share": 1.0}},
            price_band_category=price_band,
            price_band_size=price_band,
            price_band_rule_version=CORE3_M07_PRICE_BAND_RULE_VERSION,
            price_percentile_in_size=Decimal("0.900000") if price_band == "high" else Decimal("0.500000"),
            volume_percentile_in_size=Decimal("0.800000"),
            amount_percentile_in_size=Decimal("0.850000"),
            same_pool_sku_count=1 if size_tier == "floor_hp_3_plus" else 3,
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=[f"ev-market-{sku_code.lower()}"],
            market_evidence_ids=[f"ev-market-{sku_code.lower()}"],
            rule_version=CORE3_M07_RULE_VERSION,
            input_fingerprint=f"fp-m07-{sku_code}",
            result_hash=f"hash-m07-{sku_code}",
        )
    )


def seed_ac_fact_profiles(session: Session, *, sku_code: str, model_name: str, brand_name: str, size_tier: str) -> None:
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id=f"profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            param_values_json={
                "horsepower_hp": {"normalized_value": 3.0},
                "installation_type": {"normalized_value": "柜机"},
                "dimension_tier_profile": {"size": size_tier, "energy": "high_efficiency"},
                "energy_grade_normalized": {"normalized_value": "一级能效"},
                "airflow_volume_m3h": {"normalized_value": 1500},
            },
            core_picture_params_json={"horsepower_hp": {"normalized_value": 3.0}, "installation_type": {"normalized_value": "柜机"}},
            core_gaming_params_json={"airflow_volume_m3h": {"normalized_value": 1500}},
            core_system_params_json={"wifi_control_flag": {"normalized_value": True}},
            core_eye_care_params_json={"self_cleaning_flag": {"normalized_value": True}},
            param_completeness=Decimal("0.820000"),
            known_param_count=42,
            unknown_param_count=5,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=[f"ev-param-{sku_code.lower()}"],
            quality_summary_json={"taxonomy_category_code": "AC"},
            profile_hash=f"hash-param-{sku_code.lower()}",
            seed_version=CORE3_M03B_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M03B_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id=f"claim-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M04C_AC_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            raw_claim_count=3,
            matched_claim_count=3,
            fact_claim_count=3,
            unsupported_claim_count=0,
            claim_texts_json=["大风量", "自清洁", "智能控制"],
            claim_codes=["ac_claim_large_airflow_coverage", "ac_claim_self_cleaning", "ac_claim_smart_app_voice_iot"],
            fact_claim_codes=["ac_claim_large_airflow_coverage", "ac_claim_self_cleaning", "ac_claim_smart_app_voice_iot"],
            unsupported_claim_codes=[],
            dimension_profile_json={"airflow_comfort": {"fact_claim_count": 1}, "health_clean_air": {"fact_claim_count": 1}},
            dimension_position_profile_json={"airflow_comfort": ["large_airflow"], "health_clean_air": ["self_cleaning"]},
            claim_summary_json={"premium_claim_candidates": ["ac_claim_large_airflow_coverage"]},
            evidence_ids=[f"ev-claim-{sku_code.lower()}"],
            confidence=Decimal("0.9000"),
            profile_hash=f"hash-claim-{sku_code.lower()}",
            rule_version=CORE3_M04C_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id=f"comment-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M05C_AC_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            comment_sentence_count=20,
            matched_sentence_count=18,
            fact_atom_count=22,
            product_fact_sentence_count=18,
            positive_sentence_count=14,
            negative_sentence_count=1,
            neutral_sentence_count=3,
            service_excluded_sentence_count=1,
            dimension_summary_json={"airflow_comfort": {"positive": 8}, "health_clean_air": {"positive": 5}},
            signal_summary_json={"use_case_signal": ["客厅大空间"]},
            param_comment_support_json={"airflow_volume_m3h": {"positive": 3}},
            claim_comment_support_json={"ac_claim_large_airflow_coverage": {"positive": 5}, "ac_claim_self_cleaning": {"positive": 4}},
            supported_param_codes=["airflow_volume_m3h"],
            contradicted_param_codes=[],
            supported_claim_codes=["ac_claim_large_airflow_coverage", "ac_claim_self_cleaning"],
            contradicted_claim_codes=[],
            evidence_examples_json=[{"text": "客厅制冷快，风量大，自清洁也方便"}],
            evidence_ids=[f"ev-comment-{sku_code.lower()}"],
            confidence=Decimal("0.8800"),
            profile_hash=f"hash-comment-{sku_code.lower()}",
            rule_version=CORE3_M05C_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id=f"m09c-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M09C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band_in_size_tier="high",
            primary_user_task_code="TASK_LARGE_SPACE_COVERAGE",
            primary_relation_status="primary_user_task",
            secondary_user_task_codes_json=["TASK_HEALTH_CLEAN_AIR"],
            comment_observed_task_codes_json=["TASK_LARGE_SPACE_COVERAGE"],
            brand_claimed_task_codes_json=["TASK_HEALTH_CLEAN_AIR"],
            user_task_summary_json={"primary_reason_cn": "大空间风量和评论支撑。"},
            confidence=Decimal("0.8700"),
            evidence_ids_json=[f"ev-task-{sku_code.lower()}"],
            profile_hash=f"hash-task-{sku_code.lower()}",
        )
    )
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id=f"m10c-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M10C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band_in_size_tier="high",
            primary_target_group_code="TG_LIVING_ROOM_LARGE_SPACE",
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=["TG_CHILD_ELDER_COMFORT"],
            comment_observed_group_codes_json=["TG_LIVING_ROOM_LARGE_SPACE"],
            target_group_summary_json={"primary_reason_cn": "客厅大空间用户匹配。"},
            confidence=Decimal("0.8500"),
            evidence_ids_json=[f"ev-group-{sku_code.lower()}"],
            profile_hash=f"hash-group-{sku_code.lower()}",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id=f"m11c-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M11C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band_in_size_tier="high",
            price_percentile_in_size_tier=Decimal("0.973000"),
            primary_battlefield_code="BF_FLOOR_3_PREMIUM_COMFORT_HEALTH",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=["BF_MID_HIGH_SMART_CONTROL_UPGRADE"],
            opportunity_battlefield_codes_json=[],
            drag_factor_battlefield_codes_json=[],
            battlefield_summary_json={"primary_reason_cn": "大空间、舒适风、健康洁净和智能支撑。"},
            confidence=Decimal("0.8400"),
            evidence_ids_json=[f"ev-bf-{sku_code.lower()}"],
            profile_hash=f"hash-bf-{sku_code.lower()}",
        )
    )


def seed_ac_battlefield_score(
    session: Session,
    *,
    sku_code: str,
    model_name: str,
    brand_name: str,
    size_tier: str,
    sample_peer_codes: list[str],
) -> None:
    session.add(
        entities.Core3SkuValueBattlefieldScore(
            score_id=f"m11c-score-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            product_category="AC",
            taxonomy_version=CORE3_M11C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            battlefield_code="BF_FLOOR_3_PREMIUM_COMFORT_HEALTH",
            battlefield_name="3匹及以上柜机高端舒适健康战场",
            battlefield_definition="3匹及以上柜机、高价位，竞争重点是大空间舒适风、健康洁净、智能和品质信任。",
            relation_status="primary_battlefield",
            value_effect="positive",
            battlefield_score=Decimal("0.9000"),
            market_gate_status="matched",
            market_pool_fit_score=Decimal("1.0000"),
            user_voice_score=Decimal("1.0000"),
            task_group_fit_score=Decimal("1.0000"),
            claim_alignment_score=Decimal("0.8000"),
            param_capability_score=Decimal("1.0000"),
            market_validation_score=Decimal("0.9000"),
            sentiment_polarity="positive",
            size_tier=size_tier,
            price_band_in_size_tier="high",
            price_percentile_in_size_tier=Decimal("0.973000"),
            score_breakdown_json={
                "market": {
                    "comparable_market_context": {
                        "method": "pairwise_peer_overlap_active_week_average",
                        "size_tier": size_tier,
                        "comparison_size_tiers": ["floor_hp_3", "floor_hp_3_plus"],
                        "borrowed_adjacent_context_pool": True,
                        "qualified_peer_count": 37,
                        "sample_peer_comparisons": [{"peer_sku_code": code, "overlap_week_count": 12} for code in sample_peer_codes],
                        "note_cn": "销量/销额验证使用已批准相邻分档 SKU 两两重叠在售周的周均表现；累计销量仅用于展示，不参与判断。",
                    }
                }
            },
            status_reason_cn="测试主战场成立。",
            evidence_ids_json=[f"ev-score-{sku_code.lower()}"],
            confidence=Decimal("0.9000"),
            result_hash=f"hash-score-{sku_code.lower()}",
        )
    )


def seed_fact_profiles(session: Session) -> None:
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="profile-tv00029112",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="TV00029112",
            model_name="65E7Q",
            param_values_json={
                "screen_size_inch": {"normalized_value": 65},
                "display_tech_class": {"normalized_value": "miniled"},
                "dimension_tier_profile": {"size": "large_60_69", "display_tech": "miniled"},
            },
            core_picture_params_json={
                "screen_size_inch": {"normalized_value": 65},
                "mini_led_flag": {"normalized_value": True},
                "mini_led_type": {"normalized_value": "高端画质"},
                "backlight_source": {"normalized_value": "LED"},
                "quantum_dot_flag": {"normalized_value": False},
                "resolution_label": {"normalized_value": "4K"},
                "declared_brightness_nit_or_band": {"normalized_value": {"value": 5200, "unit": "nits"}},
                "local_dimming_zone_count": {"normalized_value": 1920},
                "高端画质": {"normalized_value": 95},
                "resolution_pixels": {"normalized_value": {"width": 3840, "height": 2160, "resolution_label": "4K"}},
            },
            core_gaming_params_json={"refresh_rate_hz": {"normalized_value": 144}},
            core_system_params_json={"ai_chip_flag": {"normalized_value": True}},
            core_eye_care_params_json={"low_blue_light_flag": {"normalized_value": True}},
            param_completeness=Decimal("0.820000"),
            known_param_count=42,
            unknown_param_count=5,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=["ev-param-tv00029112"],
            quality_summary_json={"status": "ok"},
            profile_hash="hash-param-tv00029112",
            seed_version="tv_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id="claim-profile-tv00029112",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code="TV00029112",
            model_name="65E7Q",
            brand_name="海信",
            raw_claim_count=3,
            matched_claim_count=3,
            fact_claim_count=2,
            unsupported_claim_count=1,
            claim_texts_json=["MiniLED 画质", "144Hz 高刷"],
            claim_codes=["tv_claim_miniled", "tv_claim_high_refresh"],
            fact_claim_codes=["tv_claim_miniled", "tv_claim_high_refresh"],
            unsupported_claim_codes=["tv_claim_unknown"],
            dimension_profile_json={"picture_quality": {"fact_claim_count": 1}, "motion_gaming": {"fact_claim_count": 1}},
            dimension_position_profile_json={"picture_quality": ["picture_flagship_miniled"]},
            claim_summary_json={"premium_claim_candidates": ["tv_claim_miniled"]},
            evidence_ids=["ev-claim-tv00029112"],
            confidence=Decimal("0.9000"),
            profile_hash="hash-claim-tv00029112",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id="comment-profile-tv00029112",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code="TV00029112",
            model_name="65E7Q",
            brand_name="海信",
            comment_sentence_count=20,
            matched_sentence_count=18,
            fact_atom_count=22,
            product_fact_sentence_count=18,
            positive_sentence_count=14,
            negative_sentence_count=2,
            neutral_sentence_count=2,
            service_excluded_sentence_count=1,
            dimension_summary_json={"picture_screen_experience": {"positive": 8}},
            signal_summary_json={"use_case_signal": ["客厅观影"]},
            param_comment_support_json={"screen_size_inch": {"positive": 3}},
            claim_comment_support_json={"tv_claim_miniled": {"positive": 5}, "tv_claim_high_refresh": {"negative": 2}},
            supported_param_codes=["screen_size_inch"],
            supported_claim_codes=["tv_claim_miniled"],
            contradicted_claim_codes=["tv_claim_high_refresh"],
            evidence_examples_json=[{"text": "画质清晰，客厅看电影不错"}],
            evidence_ids=["ev-comment-tv00029112"],
            confidence=Decimal("0.8800"),
            profile_hash="hash-comment-tv00029112",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id="m09c-profile-tv00029112",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
            sku_code="TV00029112",
            model_name="65E7Q",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_user_task_code="TASK_CINEMA_IMMERSION",
            primary_relation_status="primary_user_task",
            secondary_user_task_codes_json=["TASK_PREMIUM_PICTURE_EXPERIENCE"],
            comment_observed_task_codes_json=["TASK_CINEMA_IMMERSION"],
            brand_claimed_task_codes_json=["TASK_PREMIUM_PICTURE_EXPERIENCE"],
            user_task_summary_json={"primary_reason_cn": "评论和卖点都支撑大屏观影。"},
            confidence=Decimal("0.8700"),
            evidence_ids_json=["ev-task-tv00029112"],
            profile_hash="hash-task-tv00029112",
        )
    )
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id="m10c-profile-tv00029112",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
            sku_code="TV00029112",
            model_name="65E7Q",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_target_group_code="TG_PREMIUM_AV_ENTHUSIAST",
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=["TG_MAINSTREAM_FAMILY_VIEWER"],
            comment_observed_group_codes_json=["TG_PREMIUM_AV_ENTHUSIAST"],
            target_group_summary_json={"primary_reason_cn": "影音体验用户匹配。"},
            confidence=Decimal("0.8500"),
            evidence_ids_json=["ev-group-tv00029112"],
            profile_hash="hash-group-tv00029112",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id="m11c-profile-tv00029112",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
            sku_code="TV00029112",
            model_name="65E7Q",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_battlefield_code="BF_PREMIUM_PICTURE_UPGRADE",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=["BF_MAINSTREAM_LIVING_BALANCE"],
            opportunity_battlefield_codes_json=["BF_GAMING_SPORTS_FLUENCY"],
            drag_factor_battlefield_codes_json=["BF_SMART_CONNECTED_EXPERIENCE"],
            battlefield_summary_json={"primary_reason_cn": "MiniLED 与评论画质支撑。"},
            confidence=Decimal("0.8400"),
            evidence_ids_json=["ev-bf-tv00029112"],
            profile_hash="hash-bf-tv00029112",
        )
    )


def seed_candidate_fact_profiles(session: Session) -> None:
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="profile-tv00030001",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="TV00030001",
            model_name="65E7Q Pro",
            param_values_json={
                "screen_size_inch": {"normalized_value": 65},
                "display_tech_class": {"normalized_value": "led"},
                "dimension_tier_profile": {"size": "large_60_69", "display_tech": "led"},
            },
            core_picture_params_json={"screen_size_inch": {"normalized_value": 65}},
            core_gaming_params_json={"refresh_rate_hz": {"normalized_value": 144}},
            core_system_params_json={"wifi_flag": {"normalized_value": True}},
            core_eye_care_params_json={"low_blue_light_flag": {"normalized_value": True}},
            param_completeness=Decimal("0.760000"),
            known_param_count=38,
            unknown_param_count=8,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=["ev-param-tv00030001"],
            quality_summary_json={"status": "ok"},
            profile_hash="hash-param-tv00030001",
            seed_version="tv_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id="claim-profile-tv00030001",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code="TV00030001",
            model_name="65E7Q Pro",
            brand_name="海信",
            raw_claim_count=3,
            matched_claim_count=3,
            fact_claim_count=2,
            unsupported_claim_count=0,
            claim_texts_json=["144Hz 高刷", "智能互联"],
            claim_codes=["tv_claim_high_refresh", "tv_claim_smart_iot"],
            fact_claim_codes=["tv_claim_high_refresh", "tv_claim_smart_iot"],
            unsupported_claim_codes=[],
            dimension_profile_json={"motion_gaming": {"fact_claim_count": 1}, "smart": {"fact_claim_count": 1}},
            dimension_position_profile_json={"motion_gaming": ["gaming_high_refresh"]},
            claim_summary_json={"premium_claim_candidates": ["tv_claim_high_refresh"]},
            evidence_ids=["ev-claim-tv00030001"],
            confidence=Decimal("0.8600"),
            profile_hash="hash-claim-tv00030001",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id="comment-profile-tv00030001",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code="TV00030001",
            model_name="65E7Q Pro",
            brand_name="海信",
            comment_sentence_count=16,
            matched_sentence_count=14,
            fact_atom_count=18,
            product_fact_sentence_count=14,
            positive_sentence_count=11,
            negative_sentence_count=1,
            neutral_sentence_count=2,
            service_excluded_sentence_count=1,
            dimension_summary_json={"motion_gaming": {"positive": 5}},
            signal_summary_json={"use_case_signal": ["游戏", "客厅观影"]},
            param_comment_support_json={"refresh_rate_hz": {"positive": 4}},
            claim_comment_support_json={"tv_claim_high_refresh": {"positive": 4}},
            supported_param_codes=["refresh_rate_hz"],
            contradicted_param_codes=[],
            supported_claim_codes=["tv_claim_high_refresh"],
            contradicted_claim_codes=[],
            evidence_examples_json=[{"text": "刷新率高，玩游戏很流畅"}],
            evidence_ids=["ev-comment-tv00030001"],
            confidence=Decimal("0.8200"),
            profile_hash="hash-comment-tv00030001",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id="m09c-profile-tv00030001",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
            sku_code="TV00030001",
            model_name="65E7Q Pro",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_user_task_code="TASK_GAMING_CONSOLE_ENTERTAINMENT",
            primary_relation_status="primary_user_task",
            secondary_user_task_codes_json=["TASK_CINEMA_IMMERSION"],
            comment_observed_task_codes_json=["TASK_GAMING_CONSOLE_ENTERTAINMENT", "TASK_CINEMA_IMMERSION"],
            brand_claimed_task_codes_json=["TASK_GAMING_CONSOLE_ENTERTAINMENT"],
            user_task_summary_json={"primary_reason_cn": "高刷和评论游戏体验支撑。"},
            confidence=Decimal("0.8300"),
            evidence_ids_json=["ev-task-tv00030001"],
            profile_hash="hash-task-tv00030001",
        )
    )
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id="m10c-profile-tv00030001",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
            sku_code="TV00030001",
            model_name="65E7Q Pro",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_target_group_code="TG_GAMING_SPORTS_USER",
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=["TG_PREMIUM_AV_ENTHUSIAST"],
            comment_observed_group_codes_json=["TG_GAMING_SPORTS_USER"],
            target_group_summary_json={"primary_reason_cn": "游戏体育用户匹配。"},
            confidence=Decimal("0.8100"),
            evidence_ids_json=["ev-group-tv00030001"],
            profile_hash="hash-group-tv00030001",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id="m11c-profile-tv00030001",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
            sku_code="TV00030001",
            model_name="65E7Q Pro",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_battlefield_code="BF_GAMING_SPORTS_FLUENCY",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=["BF_PREMIUM_PICTURE_UPGRADE"],
            opportunity_battlefield_codes_json=["BF_SMART_CONNECTED_EXPERIENCE"],
            battlefield_summary_json={"primary_reason_cn": "高刷与游戏评论支撑。"},
            confidence=Decimal("0.8000"),
            evidence_ids_json=["ev-bf-tv00030001"],
            profile_hash="hash-bf-tv00030001",
        )
    )


def seed_business_competitor_profiles(session: Session) -> None:
    seed_competitor_fact_profile(
        session,
        sku_code="TV00040001",
        model_name="65A7H PRO",
        brand_name="创维",
        fact_claim_codes=["tv_claim_miniled", "tv_claim_high_refresh", "tv_claim_flush_wall_mount"],
        supported_claim_codes=["tv_claim_miniled", "tv_claim_flush_wall_mount"],
        primary_task="TASK_CINEMA_IMMERSION",
        secondary_tasks=["TASK_PREMIUM_PICTURE_EXPERIENCE"],
        primary_group="TG_PREMIUM_AV_ENTHUSIAST",
        secondary_groups=["TG_MAINSTREAM_FAMILY_VIEWER"],
        primary_battlefield="BF_PREMIUM_PICTURE_UPGRADE",
        secondary_battlefields=["BF_MAINSTREAM_LIVING_BALANCE"],
    )
    seed_competitor_fact_profile(
        session,
        sku_code="TV00040002",
        model_name="L65MC-SP",
        brand_name="小米",
        fact_claim_codes=["tv_claim_casting_connectivity"],
        supported_claim_codes=["tv_claim_casting_connectivity"],
        primary_task="TASK_VALUE_FOR_MONEY_PURCHASE",
        secondary_tasks=["TASK_SMART_CASTING_IOT"],
        primary_group="TG_VALUE_MAXIMIZER",
        secondary_groups=["TG_SMART_CONNECTED_USER"],
        primary_battlefield="BF_MAINSTREAM_FAMILY_VALUE",
        secondary_battlefields=["BF_SMART_CONNECTED_EXPERIENCE"],
    )
    seed_competitor_fact_profile(
        session,
        sku_code="TV00040003",
        model_name="65Q9L PRO",
        brand_name="TCL",
        fact_claim_codes=["tv_claim_miniled", "tv_claim_high_refresh", "tv_claim_hdmi21_connectivity"],
        supported_claim_codes=["tv_claim_miniled", "tv_claim_high_refresh"],
        primary_task="TASK_GAMING_CONSOLE_ENTERTAINMENT",
        secondary_tasks=["TASK_CINEMA_IMMERSION", "TASK_PREMIUM_PICTURE_EXPERIENCE"],
        primary_group="TG_GAMING_SPORTS_USER",
        secondary_groups=["TG_PREMIUM_AV_ENTHUSIAST"],
        primary_battlefield="BF_GAMING_SPORTS_FLUENCY",
        secondary_battlefields=["BF_PREMIUM_PICTURE_UPGRADE"],
    )
    seed_competitor_fact_profile(
        session,
        sku_code="TV00040004",
        model_name="65A6F ULTRA",
        brand_name="创维",
        fact_claim_codes=["tv_claim_miniled", "tv_claim_eye_care_display"],
        supported_claim_codes=["tv_claim_miniled"],
        primary_task="TASK_CINEMA_IMMERSION",
        secondary_tasks=["TASK_VALUE_FOR_MONEY_PURCHASE"],
        primary_group="TG_MAINSTREAM_FAMILY_VIEWER",
        secondary_groups=["TG_PREMIUM_AV_ENTHUSIAST"],
        primary_battlefield="BF_PREMIUM_VALUE_DOWNTRADE",
        secondary_battlefields=["BF_PREMIUM_PICTURE_UPGRADE", "BF_MAINSTREAM_LIVING_BALANCE"],
    )


def seed_competitor_fact_profile(
    session: Session,
    *,
    sku_code: str,
    model_name: str,
    brand_name: str,
    fact_claim_codes: list[str],
    supported_claim_codes: list[str],
    primary_task: str,
    secondary_tasks: list[str],
    primary_group: str,
    secondary_groups: list[str],
    primary_battlefield: str,
    secondary_battlefields: list[str],
) -> None:
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id=f"profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            param_values_json={
                "screen_size_inch": {"normalized_value": 65},
                "display_tech_class": {"normalized_value": "miniled"},
                "dimension_tier_profile": {"size": "large_60_69", "display_tech": "miniled"},
            },
            core_picture_params_json={"screen_size_inch": {"normalized_value": 65}, "display_tech_class": {"normalized_value": "miniled"}},
            core_gaming_params_json={"refresh_rate_hz": {"normalized_value": 144}},
            core_system_params_json={"wifi_flag": {"normalized_value": True}},
            core_eye_care_params_json={"low_blue_light_flag": {"normalized_value": True}},
            param_completeness=Decimal("0.800000"),
            known_param_count=40,
            unknown_param_count=6,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=[f"ev-param-{sku_code.lower()}"],
            quality_summary_json={"status": "ok"},
            profile_hash=f"hash-param-{sku_code.lower()}",
            seed_version="tv_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id=f"claim-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            raw_claim_count=len(fact_claim_codes),
            matched_claim_count=len(fact_claim_codes),
            fact_claim_count=len(fact_claim_codes),
            unsupported_claim_count=0,
            claim_texts_json=fact_claim_codes,
            claim_codes=fact_claim_codes,
            fact_claim_codes=fact_claim_codes,
            unsupported_claim_codes=[],
            dimension_profile_json={"picture_quality": {"fact_claim_count": len(fact_claim_codes)}},
            dimension_position_profile_json={"picture_quality": ["picture_flagship_miniled"], "motion_gaming": ["gaming_high_refresh"]},
            claim_summary_json={"premium_claim_candidates": fact_claim_codes[:2]},
            evidence_ids=[f"ev-claim-{sku_code.lower()}"],
            confidence=Decimal("0.8500"),
            profile_hash=f"hash-claim-{sku_code.lower()}",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id=f"comment-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            comment_sentence_count=18,
            matched_sentence_count=15,
            fact_atom_count=18,
            product_fact_sentence_count=15,
            positive_sentence_count=12,
            negative_sentence_count=1,
            neutral_sentence_count=2,
            service_excluded_sentence_count=1,
            dimension_summary_json={"picture_screen_experience": {"positive": 7}},
            signal_summary_json={"use_case_signal": ["客厅观影"]},
            param_comment_support_json={"screen_size_inch": {"positive": 3}},
            claim_comment_support_json={code: {"positive": 3} for code in supported_claim_codes},
            supported_param_codes=["screen_size_inch"],
            contradicted_param_codes=[],
            supported_claim_codes=supported_claim_codes,
            contradicted_claim_codes=[],
            evidence_examples_json=[{"text": "画质和客厅观影体验不错"}],
            evidence_ids=[f"ev-comment-{sku_code.lower()}"],
            confidence=Decimal("0.8200"),
            profile_hash=f"hash-comment-{sku_code.lower()}",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id=f"m09c-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_user_task_code=primary_task,
            primary_relation_status="primary_user_task",
            secondary_user_task_codes_json=secondary_tasks,
            comment_observed_task_codes_json=[primary_task],
            brand_claimed_task_codes_json=secondary_tasks,
            user_task_summary_json={"primary_reason_cn": "测试候选任务。"},
            confidence=Decimal("0.8200"),
            evidence_ids_json=[f"ev-task-{sku_code.lower()}"],
            profile_hash=f"hash-task-{sku_code.lower()}",
        )
    )
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id=f"m10c-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_target_group_code=primary_group,
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=secondary_groups,
            comment_observed_group_codes_json=[primary_group],
            target_group_summary_json={"primary_reason_cn": "测试候选客群。"},
            confidence=Decimal("0.8200"),
            evidence_ids_json=[f"ev-group-{sku_code.lower()}"],
            profile_hash=f"hash-group-{sku_code.lower()}",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id=f"m11c-profile-{sku_code.lower()}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_battlefield_code=primary_battlefield,
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=secondary_battlefields,
            opportunity_battlefield_codes_json=[],
            drag_factor_battlefield_codes_json=[],
            battlefield_summary_json={"primary_reason_cn": "测试候选战场。"},
            confidence=Decimal("0.8200"),
            evidence_ids_json=[f"ev-bf-{sku_code.lower()}"],
            profile_hash=f"hash-bf-{sku_code.lower()}",
        )
    )


def seed_weekly_market(session: Session) -> None:
    for sku_code, model_name, brand_name, points in [
        (
            "TV00029112",
            "65E7Q",
            "海信",
            [(1, Decimal("90"), Decimal("449910")), (2, Decimal("100"), Decimal("499900")), (3, Decimal("110"), Decimal("549890"))],
        ),
        (
            "TV00030001",
            "65E7Q Pro",
            "海信",
            [(2, Decimal("70"), Decimal("489930")), (3, Decimal("80"), Decimal("559920")), (4, Decimal("100"), Decimal("699900"))],
        ),
    ]:
        for week, volume, amount in points:
            session.add(
                entities.Core3CleanMarketWeekly(
                    clean_market_id=f"clean-market-{sku_code}-{week}",
                    project_id=PROJECT_ID,
                    category_code="TV",
                    batch_id=BATCH_ID,
                    source_pk=f"{sku_code}-{week}",
                    source_row_id=f"week_sales_data:{sku_code}:{week}",
                    source_operation_type="insert",
                    sku_code=sku_code,
                    model_name=model_name,
                    brand_name=brand_name,
                    period_raw=f"26W{week:02d}",
                    period_type="week",
                    period_year_hint=2026,
                    period_week_index=week,
                    period_parse_status="parsed",
                    channel_type="online",
                    platform_type="test_platform",
                    sales_volume=volume,
                    sales_amount=amount,
                    avg_price=amount / volume,
                    price_check_status="ok",
                    clean_record_key=f"market:{sku_code}:{week}",
                    clean_hash=f"hash-clean-{sku_code}-{week}",
                    clean_version="m01_clean_v1",
                    hash_version="m00_row_hash_v1",
                    record_status="active",
                    quality_status="ok",
                )
            )


def seed_semantic_space(session: Session) -> None:
    session.add(
        entities.Core3SemanticMarketDimensionSummary(
            summary_id="summary-bf-premium-picture",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="battlefield",
            dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
            dimension_name="高端画质升级战场",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            sku_relation_count=2,
            allocated_sku_count=2,
            primary_sku_count=1,
            secondary_sku_count=1,
            estimated_sales_volume=Decimal("900.0000"),
            estimated_sales_amount=Decimal("4800000.0000"),
            estimated_avg_weekly_sales_volume=Decimal("75.000000"),
            estimated_avg_weekly_sales_amount=Decimal("400000.000000"),
            total_market_sales_volume=Decimal("2000.0000"),
            total_market_sales_amount=Decimal("10000000.0000"),
            allocated_market_sales_volume=Decimal("1800.0000"),
            allocated_market_sales_amount=Decimal("9000000.0000"),
            sales_volume_share=Decimal("0.450000"),
            sales_amount_share=Decimal("0.480000"),
            allocation_coverage_rate=Decimal("0.900000"),
            brand_distribution_json={"海信": {"sku_count": 1}},
            size_price_distribution_json={"large_60_69": {"mid_high": {"sku_count": 1}}},
            relation_status_counts_json={"primary_battlefield": 1},
            top_skus_json=[{"sku_code": "TV00029112", "allocated_sales_volume": 700}],
            confidence_avg=Decimal("0.8600"),
            business_summary_cn="高端画质升级战场由 MiniLED 与高刷支撑。",
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-summary-bf-premium-picture",
            result_hash="hash-summary-bf-premium-picture",
        )
    )
    session.add(
        entities.Core3SemanticMarketSkuContribution(
            contribution_id="contribution-tv00029112-bf-premium",
            summary_id="summary-bf-premium-picture",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="battlefield",
            dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
            dimension_name="高端画质升级战场",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            allocation_weight=Decimal("0.600000"),
            allocated_sales_volume=Decimal("700.0000"),
            allocated_sales_amount=Decimal("3500000.0000"),
            allocated_avg_weekly_sales_volume=Decimal("58.333333"),
            allocated_avg_weekly_sales_amount=Decimal("291666.666667"),
            sku_share_in_dimension_volume=Decimal("0.777778"),
            sku_share_in_dimension_amount=Decimal("0.729167"),
            sku_rank_in_dimension=1,
            is_primary_dimension=True,
            allocation_role="primary",
            relation_status="primary_battlefield",
            allocation_confidence=Decimal("0.9000"),
            contribution_reason_cn="主战场贡献 SKU。",
            evidence_ids_json=["ev-bf-tv00029112"],
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-contribution-tv00029112-bf-premium",
            result_hash="hash-contribution-tv00029112-bf-premium",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="allocation-tv00029112-bf-premium",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            active_week_count=12,
            dimension_type="battlefield",
            dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
            dimension_name="高端画质升级战场",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            relation_status="primary_battlefield",
            allocation_role="primary",
            allocation_value_type="positive_value",
            final_score=Decimal("0.8500"),
            allocation_basis=Decimal("0.600000"),
            relation_factor=Decimal("1.0000"),
            allocation_weight=Decimal("0.600000"),
            sales_volume_total=Decimal("1200.0000"),
            sales_amount_total=Decimal("5998800.0000"),
            avg_weekly_sales_volume=Decimal("100.000000"),
            avg_weekly_sales_amount=Decimal("499900.000000"),
            allocated_sales_volume=Decimal("700.0000"),
            allocated_sales_amount=Decimal("3500000.0000"),
            allocated_avg_weekly_sales_volume=Decimal("58.333333"),
            allocated_avg_weekly_sales_amount=Decimal("291666.666667"),
            allocation_confidence=Decimal("0.9000"),
            allocation_basis_json={"source": "test"},
            evidence_ids_json=["ev-bf-tv00029112"],
            market_source_json={"market_window": "full_observed_window"},
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-allocation-tv00029112-bf-premium",
            result_hash="hash-allocation-tv00029112-bf-premium",
        )
    )
    session.add(
        entities.Core3SemanticMarketDimensionSummary(
            summary_id="summary-bf-mainstream-living",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="battlefield",
            dimension_code="BF_MAINSTREAM_LIVING_BALANCE",
            dimension_name="主流客厅均衡体验战场",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            sku_relation_count=4,
            allocated_sku_count=3,
            secondary_sku_count=1,
            estimated_sales_volume=Decimal("600.0000"),
            estimated_sales_amount=Decimal("3000000.0000"),
            estimated_avg_weekly_sales_volume=Decimal("50.000000"),
            estimated_avg_weekly_sales_amount=Decimal("250000.000000"),
            total_market_sales_volume=Decimal("2000.0000"),
            total_market_sales_amount=Decimal("10000000.0000"),
            allocated_market_sales_volume=Decimal("1800.0000"),
            allocated_market_sales_amount=Decimal("9000000.0000"),
            sales_volume_share=Decimal("0.300000"),
            sales_amount_share=Decimal("0.300000"),
            allocation_coverage_rate=Decimal("0.900000"),
            brand_distribution_json={"创维": {"sku_count": 1}},
            size_price_distribution_json={"large_60_69": {"mid_high": {"sku_count": 1}}},
            relation_status_counts_json={"secondary_battlefield": 1},
            top_skus_json=[{"sku_code": "TV00040001", "allocated_sales_volume": 260}],
            confidence_avg=Decimal("0.7800"),
            business_summary_cn="主流客厅均衡体验战场由家庭客厅、画质和易用性支撑。",
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-summary-bf-mainstream-living",
            result_hash="hash-summary-bf-mainstream-living",
        )
    )
    session.add(
        entities.Core3SemanticMarketDimensionSummary(
            summary_id="summary-task-cinema",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="user_task",
            dimension_code="TASK_CINEMA_IMMERSION",
            dimension_name="影院沉浸观影",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            sku_relation_count=3,
            allocated_sku_count=3,
            primary_sku_count=2,
            secondary_sku_count=1,
            estimated_sales_volume=Decimal("1100.0000"),
            estimated_sales_amount=Decimal("5500000.0000"),
            estimated_avg_weekly_sales_volume=Decimal("91.666667"),
            estimated_avg_weekly_sales_amount=Decimal("458333.333333"),
            total_market_sales_volume=Decimal("2000.0000"),
            total_market_sales_amount=Decimal("10000000.0000"),
            allocated_market_sales_volume=Decimal("1800.0000"),
            allocated_market_sales_amount=Decimal("9000000.0000"),
            sales_volume_share=Decimal("0.550000"),
            sales_amount_share=Decimal("0.550000"),
            allocation_coverage_rate=Decimal("0.900000"),
            brand_distribution_json={"海信": {"sku_count": 1}},
            size_price_distribution_json={"large_60_69": {"mid_high": {"sku_count": 1}}},
            relation_status_counts_json={"primary_user_task": 2},
            top_skus_json=[{"sku_code": "TV00029112", "allocated_sales_volume": 500}],
            confidence_avg=Decimal("0.8800"),
            business_summary_cn="影院沉浸观影由大屏、画质和影音体验支撑。",
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-summary-task-cinema",
            result_hash="hash-summary-task-cinema",
        )
    )
    session.add(
        entities.Core3SemanticMarketSkuContribution(
            contribution_id="contribution-tv00029112-task-cinema",
            summary_id="summary-task-cinema",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="user_task",
            dimension_code="TASK_CINEMA_IMMERSION",
            dimension_name="影院沉浸观影",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            allocation_weight=Decimal("0.420000"),
            allocated_sales_volume=Decimal("500.0000"),
            allocated_sales_amount=Decimal("2500000.0000"),
            allocated_avg_weekly_sales_volume=Decimal("41.666667"),
            allocated_avg_weekly_sales_amount=Decimal("208333.333333"),
            sku_share_in_dimension_volume=Decimal("0.454545"),
            sku_share_in_dimension_amount=Decimal("0.454545"),
            sku_rank_in_dimension=2,
            is_primary_dimension=True,
            allocation_role="primary",
            relation_status="primary_user_task",
            allocation_confidence=Decimal("0.8800"),
            contribution_reason_cn="主用户任务贡献 SKU。",
            evidence_ids_json=["ev-task-tv00029112"],
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-contribution-tv00029112-task-cinema",
            result_hash="hash-contribution-tv00029112-task-cinema",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="allocation-tv00029112-task-cinema",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            active_week_count=12,
            dimension_type="user_task",
            dimension_code="TASK_CINEMA_IMMERSION",
            dimension_name="影院沉浸观影",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            relation_status="primary_user_task",
            allocation_role="primary",
            allocation_value_type="positive_value",
            final_score=Decimal("0.9000"),
            allocation_basis=Decimal("0.420000"),
            relation_factor=Decimal("1.0000"),
            allocation_weight=Decimal("0.420000"),
            sales_volume_total=Decimal("1200.0000"),
            sales_amount_total=Decimal("5998800.0000"),
            avg_weekly_sales_volume=Decimal("100.000000"),
            avg_weekly_sales_amount=Decimal("499900.000000"),
            allocated_sales_volume=Decimal("500.0000"),
            allocated_sales_amount=Decimal("2500000.0000"),
            allocated_avg_weekly_sales_volume=Decimal("41.666667"),
            allocated_avg_weekly_sales_amount=Decimal("208333.333333"),
            allocation_confidence=Decimal("0.8800"),
            allocation_basis_json={"source": "test", "role": "primary"},
            evidence_ids_json=["ev-task-tv00029112"],
            market_source_json={"market_window": "full_observed_window"},
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-allocation-tv00029112-task-cinema",
            result_hash="hash-allocation-tv00029112-task-cinema",
        )
    )
    session.add(
        entities.Core3SemanticMarketDimensionSummary(
            summary_id="summary-group-premium-av",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="target_group",
            dimension_code="TG_PREMIUM_AV_ENTHUSIAST",
            dimension_name="高端影音体验用户",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            sku_relation_count=2,
            allocated_sku_count=2,
            primary_sku_count=1,
            secondary_sku_count=1,
            estimated_sales_volume=Decimal("1000.0000"),
            estimated_sales_amount=Decimal("5200000.0000"),
            estimated_avg_weekly_sales_volume=Decimal("83.333333"),
            estimated_avg_weekly_sales_amount=Decimal("433333.333333"),
            total_market_sales_volume=Decimal("2000.0000"),
            total_market_sales_amount=Decimal("10000000.0000"),
            allocated_market_sales_volume=Decimal("1800.0000"),
            allocated_market_sales_amount=Decimal("9000000.0000"),
            sales_volume_share=Decimal("0.500000"),
            sales_amount_share=Decimal("0.520000"),
            allocation_coverage_rate=Decimal("0.900000"),
            brand_distribution_json={"海信": {"sku_count": 1}},
            size_price_distribution_json={"large_60_69": {"mid_high": {"sku_count": 1}}},
            relation_status_counts_json={"primary_target_group": 1},
            top_skus_json=[{"sku_code": "TV00029112", "allocated_sales_volume": 480}],
            confidence_avg=Decimal("0.8700"),
            business_summary_cn="高端影音体验用户重视画质、音画和客厅沉浸。",
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-summary-group-premium-av",
            result_hash="hash-summary-group-premium-av",
        )
    )
    session.add(
        entities.Core3SemanticMarketSkuContribution(
            contribution_id="contribution-tv00029112-group-premium-av",
            summary_id="summary-group-premium-av",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="target_group",
            dimension_code="TG_PREMIUM_AV_ENTHUSIAST",
            dimension_name="高端影音体验用户",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            allocation_weight=Decimal("0.400000"),
            allocated_sales_volume=Decimal("480.0000"),
            allocated_sales_amount=Decimal("2400000.0000"),
            allocated_avg_weekly_sales_volume=Decimal("40.000000"),
            allocated_avg_weekly_sales_amount=Decimal("200000.000000"),
            sku_share_in_dimension_volume=Decimal("0.480000"),
            sku_share_in_dimension_amount=Decimal("0.461538"),
            sku_rank_in_dimension=1,
            is_primary_dimension=True,
            allocation_role="primary",
            relation_status="primary_target_group",
            allocation_confidence=Decimal("0.8700"),
            contribution_reason_cn="主目标客群贡献 SKU。",
            evidence_ids_json=["ev-group-tv00029112"],
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-contribution-tv00029112-group-premium-av",
            result_hash="hash-contribution-tv00029112-group-premium-av",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="allocation-tv00029112-group-premium-av",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            active_week_count=12,
            dimension_type="target_group",
            dimension_code="TG_PREMIUM_AV_ENTHUSIAST",
            dimension_name="高端影音体验用户",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            relation_status="primary_target_group",
            allocation_role="primary",
            allocation_value_type="positive_value",
            final_score=Decimal("0.8700"),
            allocation_basis=Decimal("0.400000"),
            relation_factor=Decimal("1.0000"),
            allocation_weight=Decimal("0.400000"),
            sales_volume_total=Decimal("1200.0000"),
            sales_amount_total=Decimal("5998800.0000"),
            avg_weekly_sales_volume=Decimal("100.000000"),
            avg_weekly_sales_amount=Decimal("499900.000000"),
            allocated_sales_volume=Decimal("480.0000"),
            allocated_sales_amount=Decimal("2400000.0000"),
            allocated_avg_weekly_sales_volume=Decimal("40.000000"),
            allocated_avg_weekly_sales_amount=Decimal("200000.000000"),
            allocation_confidence=Decimal("0.8700"),
            allocation_basis_json={"source": "test", "role": "primary"},
            evidence_ids_json=["ev-group-tv00029112"],
            market_source_json={"market_window": "full_observed_window"},
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-allocation-tv00029112-group-premium-av",
            result_hash="hash-allocation-tv00029112-group-premium-av",
        )
    )
    session.add(
        entities.Core3SemanticMarketDimensionSummary(
            summary_id="summary-bf-gaming-sports",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="battlefield",
            dimension_code="BF_GAMING_SPORTS_FLUENCY",
            dimension_name="游戏体育流畅战场",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            sku_relation_count=3,
            allocated_sku_count=3,
            primary_sku_count=1,
            opportunity_sku_count=1,
            estimated_sales_volume=Decimal("500.0000"),
            estimated_sales_amount=Decimal("2600000.0000"),
            estimated_avg_weekly_sales_volume=Decimal("41.666667"),
            estimated_avg_weekly_sales_amount=Decimal("216666.666667"),
            total_market_sales_volume=Decimal("2000.0000"),
            total_market_sales_amount=Decimal("10000000.0000"),
            allocated_market_sales_volume=Decimal("1800.0000"),
            allocated_market_sales_amount=Decimal("9000000.0000"),
            sales_volume_share=Decimal("0.250000"),
            sales_amount_share=Decimal("0.260000"),
            allocation_coverage_rate=Decimal("0.900000"),
            brand_distribution_json={"海信": {"sku_count": 1}},
            size_price_distribution_json={"large_60_69": {"mid_high": {"sku_count": 1}}},
            relation_status_counts_json={"opportunity_battlefield": 1},
            top_skus_json=[{"sku_code": "TV00030001", "allocated_sales_volume": 300}],
            confidence_avg=Decimal("0.8100"),
            business_summary_cn="游戏体育流畅战场由高刷和运动流畅支撑。",
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-summary-bf-gaming",
            result_hash="hash-summary-bf-gaming",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="allocation-tv00029112-bf-gaming",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            active_week_count=12,
            dimension_type="battlefield",
            dimension_code="BF_GAMING_SPORTS_FLUENCY",
            dimension_name="游戏体育流畅战场",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            relation_status="opportunity_battlefield",
            allocation_role="opportunity",
            allocation_value_type="opportunity_value",
            final_score=Decimal("0.5500"),
            allocation_basis=Decimal("0.250000"),
            relation_factor=Decimal("0.7000"),
            allocation_weight=Decimal("0.250000"),
            sales_volume_total=Decimal("1200.0000"),
            sales_amount_total=Decimal("5998800.0000"),
            avg_weekly_sales_volume=Decimal("100.000000"),
            avg_weekly_sales_amount=Decimal("499900.000000"),
            allocated_sales_volume=Decimal("300.0000"),
            allocated_sales_amount=Decimal("1499700.0000"),
            allocated_avg_weekly_sales_volume=Decimal("25.000000"),
            allocated_avg_weekly_sales_amount=Decimal("124975.000000"),
            allocation_confidence=Decimal("0.7200"),
            allocation_basis_json={"source": "test", "role": "opportunity"},
            evidence_ids_json=["ev-bf-tv00029112"],
            market_source_json={"market_window": "full_observed_window"},
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-allocation-tv00029112-bf-gaming",
            result_hash="hash-allocation-tv00029112-bf-gaming",
        )
    )
    session.add(
        entities.Core3SemanticMarketDimensionSummary(
            summary_id="summary-bf-smart-connected",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            dimension_type="battlefield",
            dimension_code="BF_SMART_CONNECTED_EXPERIENCE",
            dimension_name="智能互联体验战场",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            sku_relation_count=2,
            allocated_sku_count=2,
            drag_risk_sku_count=1,
            estimated_sales_volume=Decimal("300.0000"),
            estimated_sales_amount=Decimal("1500000.0000"),
            estimated_avg_weekly_sales_volume=Decimal("25.000000"),
            estimated_avg_weekly_sales_amount=Decimal("125000.000000"),
            total_market_sales_volume=Decimal("2000.0000"),
            total_market_sales_amount=Decimal("10000000.0000"),
            allocated_market_sales_volume=Decimal("1800.0000"),
            allocated_market_sales_amount=Decimal("9000000.0000"),
            sales_volume_share=Decimal("0.150000"),
            sales_amount_share=Decimal("0.150000"),
            allocation_coverage_rate=Decimal("0.900000"),
            brand_distribution_json={"海信": {"sku_count": 1}},
            size_price_distribution_json={"large_60_69": {"mid_high": {"sku_count": 1}}},
            relation_status_counts_json={"drag_factor_battlefield": 1},
            top_skus_json=[{"sku_code": "TV00030001", "allocated_sales_volume": 180}],
            confidence_avg=Decimal("0.7000"),
            business_summary_cn="智能互联体验战场对系统和互联能力要求更高。",
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-summary-bf-smart",
            result_hash="hash-summary-bf-smart",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="allocation-tv00029112-bf-smart",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            analysis_population="fact_complete_with_comment",
            market_window="full_observed_window",
            active_week_count=12,
            dimension_type="battlefield",
            dimension_code="BF_SMART_CONNECTED_EXPERIENCE",
            dimension_name="智能互联体验战场",
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            relation_status="drag_factor_battlefield",
            allocation_role="drag_factor",
            allocation_value_type="negative_value",
            final_score=Decimal("0.3000"),
            allocation_basis=Decimal("0.100000"),
            relation_factor=Decimal("0.5000"),
            allocation_weight=Decimal("0.100000"),
            sales_volume_total=Decimal("1200.0000"),
            sales_amount_total=Decimal("5998800.0000"),
            avg_weekly_sales_volume=Decimal("100.000000"),
            avg_weekly_sales_amount=Decimal("499900.000000"),
            allocated_sales_volume=Decimal("120.0000"),
            allocated_sales_amount=Decimal("599880.0000"),
            allocated_avg_weekly_sales_volume=Decimal("10.000000"),
            allocated_avg_weekly_sales_amount=Decimal("49990.000000"),
            allocation_confidence=Decimal("0.6500"),
            allocation_basis_json={"source": "test", "role": "drag_factor"},
            evidence_ids_json=["ev-bf-tv00029112"],
            market_source_json={"market_window": "full_observed_window"},
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-allocation-tv00029112-bf-smart",
            result_hash="hash-allocation-tv00029112-bf-smart",
        )
    )


def seed_m12c_claim_value(session: Session) -> None:
    population = "claim_value_ready_with_comment"
    session.add(
        entities.Core3ClaimValueContextPool(
            pool_id="pool-miniled",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            analysis_population=population,
            window_start_week=1,
            window_end_week=12,
            claim_code="tv_claim_miniled",
            claim_name="MiniLED",
            context_type="battlefield",
            context_code="BF_PREMIUM_PICTURE_UPGRADE",
            context_name="高端画质升级战场",
            size_tier="large_60_69",
            price_band_group="mid_high",
            pool_sku_count=8,
            with_claim_sku_count=4,
            without_claim_sku_count=4,
            unknown_claim_sku_count=0,
            pool_sku_codes_json=["TV00029112", "TV00040001"],
            with_claim_sku_codes_json=["TV00029112"],
            without_claim_sku_codes_json=["TV00040001"],
            sample_status="sufficient",
            quality_flags_json=[],
            pool_hash="hash-pool-miniled",
            rule_version=CORE3_M12C_RULE_VERSION,
            input_fingerprint="fp-pool-miniled",
        )
    )
    session.add(
        entities.Core3ClaimValuePoolMetric(
            metric_id="metric-pool-miniled",
            pool_id="pool-miniled",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            analysis_population=population,
            claim_code="tv_claim_miniled",
            claim_name="MiniLED",
            context_type="battlefield",
            context_code="BF_PREMIUM_PICTURE_UPGRADE",
            context_name="高端画质升级战场",
            size_tier="large_60_69",
            price_band_group="mid_high",
            with_price_median=Decimal("5000"),
            without_price_median=Decimal("4600"),
            price_premium_abs=Decimal("400"),
            price_premium_rate=Decimal("0.086957"),
            with_weekly_sales_median=Decimal("100"),
            without_weekly_sales_median=Decimal("80"),
            weekly_sales_lift_abs=Decimal("20"),
            weekly_sales_lift_rate=Decimal("0.250000"),
            with_weekly_sales_amount_median=Decimal("500000"),
            without_weekly_sales_amount_median=Decimal("368000"),
            weekly_sales_amount_lift_abs=Decimal("132000"),
            weekly_sales_amount_lift_rate=Decimal("0.358696"),
            market_share_lift=Decimal("0.120000"),
            claim_value_effect_score=Decimal("0.7200"),
            effect_confidence=Decimal("0.8200"),
            business_summary_cn="MiniLED 在高端画质升级战场可比池中形成正向价值。",
            quality_flags_json=[],
            result_hash="hash-metric-pool-miniled",
            rule_version=CORE3_M12C_RULE_VERSION,
        )
    )

    for row_id, sku_code, brand, model, claim_code, claim_name, role, context_code, context_name, price_premium, sales_lift, amount_lift, share, reason in [
        (
            "q-target-miniled",
            "TV00029112",
            "海信",
            "65E7Q",
            "tv_claim_miniled",
            "MiniLED",
            "premium_driver_estimated",
            "BF_PREMIUM_PICTURE_UPGRADE",
            "高端画质升级战场",
            Decimal("280"),
            Decimal("15"),
            Decimal("75000"),
            Decimal("0.650000"),
            "MiniLED 是海信 65E7Q 在高端画质战场的估算溢价卖点。",
        ),
        (
            "q-target-refresh",
            "TV00029112",
            "海信",
            "65E7Q",
            "tv_claim_high_refresh_rate",
            "高刷",
            "sales_driver_estimated",
            "BF_GAMING_SPORTS_FLUENCY",
            "游戏体育流畅战场",
            Decimal("80"),
            Decimal("22"),
            Decimal("88000"),
            Decimal("0.350000"),
            "高刷是海信 65E7Q 在游戏体育流畅战场的估算销量卖点。",
        ),
        (
            "q-target-speaker",
            "TV00029112",
            "海信",
            "65E7Q",
            "tv_claim_speaker_sound",
            "音响体验",
            "drag_factor",
            "BF_PREMIUM_PICTURE_UPGRADE",
            "高端画质升级战场",
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0.000000"),
            "音响体验在评论或参数支撑上存在拖后腿风险。",
        ),
        (
            "q-candidate-wall",
            "TV00040001",
            "创维",
            "65A7H PRO",
            "tv_claim_wall_mount_design",
            "壁画贴墙",
            "premium_driver_estimated",
            "BF_PREMIUM_PICTURE_UPGRADE",
            "高端画质升级战场",
            Decimal("180"),
            Decimal("12"),
            Decimal("52000"),
            Decimal("0.500000"),
            "壁画贴墙是创维在高端画质战场中的场景化溢价卖点。",
        ),
    ]:
        session.add(
            entities.Core3SkuClaimValueQuantification(
                sku_claim_value_id=row_id,
                pool_id="pool-miniled",
                metric_id="metric-pool-miniled",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                product_category="TV",
                market_window="full_observed_window",
                analysis_population=population,
                sku_code=sku_code,
                brand_name=brand,
                model_name=model,
                claim_code=claim_code,
                claim_name=claim_name,
                claim_dimension="picture_experience",
                claim_value_role=role,
                context_type="battlefield",
                context_code=context_code,
                context_name=context_name,
                size_tier="large_60_69",
                price_band_group="mid_high",
                claim_evidence_strength=Decimal("0.9000"),
                param_support_strength=Decimal("0.8500"),
                comment_support_strength=Decimal("0.8000"),
                semantic_support_strength=Decimal("0.9500"),
                estimated_price_premium_abs=price_premium,
                estimated_weekly_sales_lift_abs=sales_lift,
                estimated_weekly_sales_amount_lift_abs=amount_lift,
                contribution_share_in_sku=share,
                attribution_confidence=Decimal("0.8200"),
                supporting_dimensions_json={"context_type": "battlefield", "context_code": context_code},
                evidence_ids_json=[f"ev-{row_id}"],
                reason_cn=reason,
                quality_flags_json=[],
                result_hash=f"hash-{row_id}",
                rule_version=CORE3_M12C_RULE_VERSION,
            )
        )

    session.add(
        entities.Core3SkuClaimContributionAttribution(
            attribution_id="attr-target-premium",
            pool_id="pool-miniled",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            analysis_population=population,
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            context_type="battlefield",
            context_code="BF_PREMIUM_PICTURE_UPGRADE",
            context_name="高端画质升级战场",
            size_tier="large_60_69",
            price_band_group="mid_high",
            baseline_price=Decimal("4600"),
            baseline_weekly_sales_volume=Decimal("80"),
            baseline_weekly_sales_amount=Decimal("368000"),
            sku_price=Decimal("4999"),
            sku_weekly_sales_volume=Decimal("100"),
            sku_weekly_sales_amount=Decimal("499900"),
            sku_price_premium_abs=Decimal("399"),
            sku_weekly_sales_lift_abs=Decimal("20"),
            sku_weekly_sales_amount_lift_abs=Decimal("131900"),
            positive_claims_json=[{"claim_code": "tv_claim_miniled", "claim_name": "MiniLED", "claim_value_role": "premium_driver_estimated", "estimated_price_premium_abs": 280.0}],
            drag_claims_json=[{"claim_code": "tv_claim_speaker_sound", "claim_name": "音响体验", "claim_value_role": "drag_factor"}],
            opportunity_claims_json=[{"claim_code": "tv_claim_wall_mount_design", "claim_name": "壁画贴墙", "claim_value_role": "opportunity_gap"}],
            attribution_summary_cn="海信 65E7Q 的超额表现主要由 MiniLED 提供可观测解释。",
            confidence=Decimal("0.8200"),
            result_hash="hash-attr-target-premium",
            rule_version=CORE3_M12C_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimContributionAttribution(
            attribution_id="attr-candidate-premium",
            pool_id="pool-miniled",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            analysis_population=population,
            sku_code="TV00040001",
            brand_name="创维",
            model_name="65A7H PRO",
            context_type="battlefield",
            context_code="BF_PREMIUM_PICTURE_UPGRADE",
            context_name="高端画质升级战场",
            size_tier="large_60_69",
            price_band_group="mid_high",
            baseline_price=Decimal("4600"),
            baseline_weekly_sales_volume=Decimal("80"),
            baseline_weekly_sales_amount=Decimal("368000"),
            sku_price=Decimal("4700"),
            sku_weekly_sales_volume=Decimal("75"),
            sku_weekly_sales_amount=Decimal("352500"),
            sku_price_premium_abs=Decimal("100"),
            sku_weekly_sales_lift_abs=Decimal("-5"),
            sku_weekly_sales_amount_lift_abs=Decimal("-15500"),
            positive_claims_json=[{"claim_code": "tv_claim_wall_mount_design", "claim_name": "壁画贴墙", "claim_value_role": "premium_driver_estimated", "estimated_price_premium_abs": 180.0}],
            drag_claims_json=[],
            opportunity_claims_json=[],
            attribution_summary_cn="创维 65A7H PRO 的正向卖点集中在壁画贴墙。",
            confidence=Decimal("0.8200"),
            result_hash="hash-attr-candidate-premium",
            rule_version=CORE3_M12C_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3ClaimValueDimensionSummary(
            summary_id="dim-miniled-premium",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            analysis_population=population,
            claim_code="tv_claim_miniled",
            claim_name="MiniLED",
            dimension_type="battlefield",
            dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
            dimension_name="高端画质升级战场",
            size_tier="large_60_69",
            price_band_group="mid_high",
            sku_count=2,
            premium_driver_sku_count=1,
            sales_driver_sku_count=0,
            basic_threshold_sku_count=0,
            brand_claim_only_sku_count=0,
            drag_factor_sku_count=0,
            opportunity_gap_sku_count=0,
            estimated_sales_volume=Decimal("900"),
            estimated_avg_weekly_sales_volume=Decimal("75"),
            estimated_sales_amount=Decimal("4800000"),
            estimated_avg_weekly_sales_amount=Decimal("400000"),
            top_skus_json=[{"sku_code": "TV00029112", "claim_name": "MiniLED", "estimated_price_premium_abs": 280.0}],
            business_summary_cn="MiniLED 在高端画质升级战场中形成可观测溢价。",
            result_hash="hash-dim-miniled-premium",
            rule_version=CORE3_M12C_RULE_VERSION,
        )
    )


def test_list_abilities_returns_agent_contract() -> None:
    session = make_session()
    result = catforge_analyst.list_analyst_abilities(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        ability_type="sop",
    )

    assert result["status"] == "ok"
    codes = {item["code"] for item in result["result"]["abilities"]}
    assert "competitor-set" in codes
    assert "why-sales-diff" in codes
    by_code = {item["code"]: item for item in result["result"]["abilities"]}
    assert by_code["competitor-set"]["status"] == "implemented"
    assert by_code["sku-business-brief"]["status"] == "implemented"


def test_list_atom_abilities_includes_m12c_claim_value_atoms() -> None:
    session = make_session()
    result = catforge_analyst.list_analyst_abilities(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        ability_type="atom",
    )

    codes = {item["code"] for item in result["result"]["abilities"]}
    assert {
        "claim-value-space",
        "sku-claim-value",
        "claim-contribution",
        "claim-opportunity-gaps",
        "claim-value-compare",
    } <= codes


def test_sku_claim_value_returns_m12c_quantified_roles() -> None:
    session = make_session()
    result = catforge_analyst.sku_claim_value(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    payload = result["result"]["sku_claim_value"]
    assert payload["role_counts"]["premium_driver_estimated"] == 1
    assert payload["role_counts"]["sales_driver_estimated"] == 1
    assert payload["role_counts"]["drag_factor"] == 1
    top_claim = payload["claim_values"][0]
    assert top_claim["claim_code"] == "tv_claim_miniled"
    assert top_claim["estimated_contribution"]["price_premium_abs"] == 280.0


def test_sku_claim_value_uses_query_only_for_sku_resolution() -> None:
    session = make_session()
    result = catforge_analyst.sku_claim_value(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E7Q",
    )

    assert result["status"] == "ok"
    assert result["target"]["sku_code"] == "TV00029112"
    payload = result["result"]["sku_claim_value"]
    assert payload["role_counts"]["premium_driver_estimated"] == 1
    assert {item["claim_code"] for item in payload["claim_values"]} >= {
        "tv_claim_miniled",
        "tv_claim_high_refresh_rate",
    }


def test_sku_claim_value_text_formatter_uses_business_role_names() -> None:
    session = make_session()
    result = catforge_analyst.sku_claim_value(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E7Q",
        limit=2,
    )

    text = catforge_analyst.format_business_text(result)

    assert "溢价卖点" in text
    assert "强销量卖点" in text
    assert "可比产品价格差异" in text
    assert "本品可解释价差份额" in text
    assert "战场合计只汇总同一分类、同一卖点在价值战场中的去重量化结果" in text
    assert "MiniLED" in text


def test_claim_value_report_keeps_specific_claims_with_battlefield_totals() -> None:
    shared_pool = {
        "pool_claim_price_delta_abs": 500,
        "pool_claim_weekly_sales_delta_abs": 30,
        "pool_claim_weekly_sales_amount_delta_abs": 150000,
    }
    rows = []
    for claim_code, claim_name in [
        ("tv_claim_hdmi21_connectivity", "HDMI2.1 连接"),
        ("tv_claim_eye_care_display", "护眼显示"),
        ("tv_claim_dolby_audio_video", "杜比/影音认证"),
    ]:
        rows.append(
            {
                "claim_code": claim_code,
                "claim_name": claim_name,
                "claim_value_role": "premium_driver_estimated",
                "business_value_label": "强溢价卖点",
                "context_type": "battlefield",
                "context_code": "BF_PREMIUM_PICTURE_UPGRADE",
                "context_name": "高端画质升级战场",
                "size_tier": "65",
                "price_band_group": "high",
                "pool_effect": shared_pool,
                "sku_excess_explanation": {
                    "sku_excess_price_explained_abs": 50,
                    "sku_excess_weekly_sales_explained_abs": 6,
                    "sku_excess_weekly_sales_amount_explained_abs": 20000,
                    "contribution_share_in_sku": 0.12,
                },
                "evidence_strength": {"param": 1.0, "comment": 0.9, "semantic": 0.8},
                "attribution_confidence": 0.8,
            }
        )

    markdown = "\n".join(
        competitor_answer._product_claim_value_quantification_lines(
            claim_value={"claim_values": rows},
            claim_contribution={},
        )
    )

    assert "#### 强溢价卖点" in markdown
    assert "HDMI2.1 连接、护眼显示和杜比/影音认证（组合）" not in markdown
    assert "强溢价卖点组合" not in markdown
    assert "| HDMI2.1 连接 | 50元 | 6台/周 | 20,000元/周 | 高端画质升级战场 |" in markdown
    assert "| 护眼显示 | 50元 | 6台/周 | 20,000元/周 | 高端画质升级战场 |" in markdown
    assert "| 杜比/影音认证 | 50元 | 6台/周 | 20,000元/周 | 高端画质升级战场 |" in markdown
    assert "价值战场明细" in markdown


def test_claim_value_report_downgrades_weak_sample_positive_rows() -> None:
    rows = [
        {
            "claim_code": "tv_claim_hdmi21_connectivity",
            "claim_name": "HDMI2.1 连接",
            "claim_value_role": "premium_driver_estimated",
            "business_value_label": "强溢价卖点",
            "context_type": "battlefield",
            "context_code": "BF_GAMING_SPORTS_FLUENCY",
            "context_name": "游戏体育流畅战场",
            "size_tier": "large_60_69",
            "price_band_group": "high",
            "pool_effect": {
                "pool_claim_price_delta_abs": 427,
                "pool_claim_weekly_sales_delta_abs": 34,
                "pool_claim_weekly_sales_amount_delta_abs": 270000,
            },
            "sku_excess_explanation": {
                "sku_excess_price_explained_abs": 66,
                "sku_excess_weekly_sales_explained_abs": 5,
                "sku_excess_weekly_sales_amount_explained_abs": 41892,
                "contribution_share_in_sku": 0.15,
            },
            "evidence_strength": {"claim": 1.0, "param": 1.0, "comment": 1.0, "semantic": 0.8},
            "quality_flags": ["small_comparable_pool"],
            "attribution_confidence": 0.63,
            "reason_cn": "HDMI2.1 连接 被判为样本不足；所在可比池有卖点组相对对照组价格差异约 427 元，周均销量差异约 34.3 台。",
        }
    ]

    markdown = "\n".join(
        competitor_answer._product_claim_value_quantification_lines(
            claim_value={"claim_values": rows},
            claim_contribution={},
        )
    )

    assert "#### 强溢价卖点" not in markdown
    assert "#### 本品优势卖点（待量化）" in markdown
    assert "| HDMI2.1 连接 | 不作为正向量化 | 不作为正向量化 | 不作为正向量化 | 游戏体育流畅战场 |" in markdown
    assert "价值战场明细" not in markdown
    assert "66元" not in markdown
    assert "427 元" not in markdown
    assert "34.3 台" not in markdown


def test_m12c_weak_sample_pool_is_not_strong_premium() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_hdmi21_connectivity",
        claim_name="HDMI2.1 连接",
        context_type="battlefield",
        context_code="BF_GAMING_SPORTS_FLUENCY",
        context_name="游戏体育流畅战场",
        size_tier="large_60_69",
        price_band_group="high",
        sku_codes=("TV00029112", "TV00027801", "TV00028829", "TV00029936"),
        with_claim_skus=("TV00029112",),
        without_claim_skus=("TV00027801", "TV00028829", "TV00029936"),
        unknown_skus=(),
        sample_status="weak",
        quality_flags=("small_comparable_pool",),
        relaxation_path=(),
    )

    role = m12c_service._claim_role(
        has_claim=True,
        metric={
            "price_premium_abs": Decimal("427.4241"),
            "weekly_sales_lift_abs": Decimal("34.333333"),
            "weekly_sales_amount_lift_abs": Decimal("271923.846250"),
            "effect_confidence": Decimal("0.6324"),
        },
        pool=pool,
        param_strength=Decimal("1.0000"),
        comment_strength=Decimal("1.0000"),
        semantic_strength=Decimal("1.0000"),
        has_negative=False,
        market_price=Decimal("5949.0000"),
    )

    assert role == m12c_service.M12C_ROLE_SAMPLE


def test_claim_value_report_sums_same_claim_within_same_category_battlefields() -> None:
    rows = []
    for context_code, context_name, price, sales, amount in [
        ("BF_PREMIUM_PICTURE_UPGRADE", "高端画质升级战场", 60, 5, 30000),
        ("BF_GAMING_SPORTS_FLUENCY", "游戏体育流畅战场", 70, 6, 36000),
    ]:
        rows.append(
            {
                "claim_code": "tv_claim_chip_performance",
                "claim_name": "芯片/处理器性能",
                "claim_value_role": "premium_driver_estimated",
                "business_value_label": "强溢价卖点",
                "context_type": "battlefield",
                "context_code": context_code,
                "context_name": context_name,
                "size_tier": "65",
                "price_band_group": "high",
                "pool_effect": {
                    "pool_claim_price_delta_abs": 420,
                    "pool_claim_weekly_sales_delta_abs": 34,
                    "pool_claim_weekly_sales_amount_delta_abs": 270000,
                },
                "sku_excess_explanation": {
                    "sku_excess_price_explained_abs": price,
                    "sku_excess_weekly_sales_explained_abs": sales,
                    "sku_excess_weekly_sales_amount_explained_abs": amount,
                    "contribution_share_in_sku": 0.12,
                },
                "evidence_strength": {"param": 1.0, "comment": 1.0, "semantic": 0.9},
                "attribution_confidence": 0.8,
            }
        )

    markdown = "\n".join(
        competitor_answer._product_claim_value_quantification_lines(
            claim_value={"claim_values": rows},
            claim_contribution={},
        )
    )

    assert "| 芯片/处理器性能 | 130元 | 11台/周 | 66,000元/周 | 高端画质升级战场和游戏体育流畅战场 |" in markdown
    assert "| 芯片/处理器性能 | 高端画质升级战场 | 420元 | 34台/周 | 60元 | 5台/周 |" in markdown
    assert "| 芯片/处理器性能 | 游戏体育流畅战场 | 420元 | 34台/周 | 70元 | 6台/周 |" in markdown


def test_claim_value_report_dedupes_identical_battlefield_quantification() -> None:
    rows = []
    for context_code, context_name in [
        ("BF_PREMIUM_PICTURE_UPGRADE", "高端画质升级战场"),
        ("BF_GAMING_SPORTS_FLUENCY", "游戏体育流畅战场"),
    ]:
        rows.append(
            {
                "claim_code": "tv_claim_chip_performance",
                "claim_name": "芯片/处理器性能",
                "claim_value_role": "premium_driver_estimated",
                "business_value_label": "强溢价卖点",
                "context_type": "battlefield",
                "context_code": context_code,
                "context_name": context_name,
                "size_tier": "65",
                "price_band_group": "high",
                "pool_effect": {
                    "pool_claim_price_delta_abs": 420,
                    "pool_claim_weekly_sales_delta_abs": 34,
                    "pool_claim_weekly_sales_amount_delta_abs": 270000,
                },
                "sku_excess_explanation": {
                    "sku_excess_price_explained_abs": 60,
                    "sku_excess_weekly_sales_explained_abs": 5,
                    "sku_excess_weekly_sales_amount_explained_abs": 30000,
                    "contribution_share_in_sku": 0.12,
                },
                "evidence_strength": {"param": 1.0, "comment": 1.0, "semantic": 0.9},
                "attribution_confidence": 0.8,
            }
        )

    markdown = "\n".join(
        competitor_answer._product_claim_value_quantification_lines(
            claim_value={"claim_values": rows},
            claim_contribution={},
        )
    )

    assert "| 芯片/处理器性能 | 60元 | 5台/周 | 30,000元/周 | 高端画质升级战场和游戏体育流畅战场 |" in markdown
    assert "| 芯片/处理器性能 | 高端画质升级战场和游戏体育流畅战场 | 420元 | 34台/周 | 60元 | 5台/周 |" in markdown
    assert "| 芯片/处理器性能 | 120元 | 10台/周 |" not in markdown


def test_claim_value_report_moves_positive_non_battlefield_rows_to_nonquantified_fact() -> None:
    rows = [
        {
            "claim_code": "tv_claim_hdr_brightness",
            "claim_name": "HDR/高亮画质",
            "claim_value_role": "premium_driver_estimated",
            "business_value_label": "强溢价卖点",
            "context_type": "target_group",
            "context_code": "TG_PREMIUM_AV_ENTHUSIAST",
            "context_name": "高端影音体验用户",
            "size_tier": "65",
            "price_band_group": "high",
            "pool_effect": {
                "pool_claim_price_delta_abs": 360,
                "pool_claim_weekly_sales_delta_abs": 20,
                "pool_claim_weekly_sales_amount_delta_abs": 120000,
            },
            "sku_excess_explanation": {
                "sku_excess_price_explained_abs": 40,
                "sku_excess_weekly_sales_explained_abs": 5,
                "sku_excess_weekly_sales_amount_explained_abs": 20000,
            },
            "evidence_strength": {"claim": 1.0, "param": 1.0, "comment": 0.9, "semantic": 0.8},
            "attribution_confidence": 0.8,
        }
    ]

    markdown = "\n".join(
        competitor_answer._product_claim_value_quantification_lines(
            claim_value={"claim_values": rows},
            claim_contribution={},
        )
    )

    assert "#### 强溢价卖点" not in markdown
    assert "#### 本品优势卖点（待量化）" in markdown
    assert "| HDR/高亮画质 | 不作为正向量化 | 不作为正向量化 | 不作为正向量化 | 价值战场暂未形成稳定量化 |" in markdown
    assert "核心事实优势/暂不量化" not in markdown


def test_claim_value_space_returns_dimension_summary() -> None:
    session = make_session()
    result = catforge_analyst.claim_value_space(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="MiniLED",
        dimension_type="battlefield",
    )

    assert result["status"] == "ok"
    item = result["result"]["claim_value_space"]["items"][0]
    assert item["claim_code"] == "tv_claim_miniled"
    assert item["dimension_code"] == "BF_PREMIUM_PICTURE_UPGRADE"
    assert item["role_counts"]["premium_driver_estimated"] == 1


def test_claim_opportunity_gaps_uses_candidate_positive_claims() -> None:
    session = make_session()
    result = catforge_analyst.claim_opportunity_gaps(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00040001",
    )

    assert result["status"] == "ok"
    payload = result["result"]["claim_opportunity_gaps"]
    missing_codes = {item["claim_code"] for item in payload["candidate_positive_claims_missing_on_target"]}
    assert "tv_claim_wall_mount_design" in missing_codes


def test_claim_value_compare_splits_target_and_candidate_advantages() -> None:
    session = make_session()
    result = catforge_analyst.claim_value_compare(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00040001",
    )

    assert result["status"] == "ok"
    payload = result["result"]["claim_value_compare"]
    target_advantage_codes = {item["claim_code"] for item in payload["target_advantage_claims"]}
    candidate_advantage_codes = {item["claim_code"] for item in payload["candidate_advantage_claims"]}
    assert "tv_claim_miniled" in target_advantage_codes
    assert "tv_claim_wall_mount_design" in candidate_advantage_codes


def test_resolve_sku_uses_market_profile_and_size_tier() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    resolved = result["result"]["resolved_sku"]
    assert resolved["sku_code"] == "TV00029112"
    assert resolved["brand_name"] == "海信"
    assert resolved["size_tier"] == "large_60_69"
    assert resolved["price_band_in_size_tier"] == "mid_high"


def test_resolve_sku_prefers_exact_model_before_fuzzy_suffix() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        model_name="65E7Q",
    )

    assert result["status"] == "ok"
    assert result["target"]["sku_code"] == "TV00029112"


def test_resolve_sku_strips_brand_words_from_query() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E7Q",
    )

    assert result["status"] == "ok"
    assert result["target"]["sku_code"] == "TV00029112"


def test_resolve_sku_latest_uses_latest_analyst_ready_batch_not_empty_source_batch() -> None:
    session = make_session()
    session.add(
        entities.Core3SourceBatch(
            batch_id="m00_new_empty_comment_only",
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
            status="registered",
        )
    )
    session.commit()

    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="tv",
        query="海信 65E7Q",
    )

    assert result["status"] == "ok"
    assert result["batch_id"] == BATCH_ID
    assert result["target"]["sku_code"] == "TV00029112"


def test_resolve_sku_tolerates_three_digit_size_typo_before_model_letter() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 657E7q",
    )

    assert result["status"] == "ok"
    assert result["target"]["sku_code"] == "TV00029112"


def test_resolve_sku_preserves_pro_suffix_priority() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E7Q Pro",
    )

    assert result["status"] == "ok"
    assert result["target"]["sku_code"] == "TV00030001"
    assert result["target"]["model_name"] == "65E7Q Pro"


def test_resolve_sku_does_not_fallback_to_base_when_pro_is_requested() -> None:
    session = make_session()
    session.query(entities.Core3SkuMarketProfile).filter(
        entities.Core3SkuMarketProfile.sku_code == "TV00030001"
    ).delete(synchronize_session=False)
    session.query(entities.Core3SkuParamProfile).filter(
        entities.Core3SkuParamProfile.sku_code == "TV00030001"
    ).delete(synchronize_session=False)
    session.commit()

    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E7Q Pro",
    )

    assert result["status"] == "not_found"
    assert result["result"]["candidates"] == []


def test_resolve_sku_returns_candidates_for_partial_model() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E7",
    )

    assert result["status"] == "ambiguous"
    candidate_codes = [item["sku_code"] for item in result["result"]["candidates"]]
    assert candidate_codes == ["TV00029112", "TV00030001"]
    text = catforge_analyst.format_business_text(result)
    assert "匹配到多个 SKU" in text
    assert "TV00029112" in text
    assert "TV00030001" in text


def test_resolve_sku_does_not_autocorrect_ambiguous_zero_to_q() -> None:
    session = make_session()
    result = catforge_analyst.resolve_sku(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        query="海信 65E70",
    )

    assert result["status"] == "not_found"
    assert result["result"]["candidates"] == []


def test_sku_fact_brief_returns_core_fact_sections() -> None:
    session = make_session()
    target_market = session.execute(
        select(entities.Core3SkuMarketProfile).where(entities.Core3SkuMarketProfile.sku_code == "TV00029112")
    ).scalar_one()
    target_market.size_segment = "legacy_large_screen"
    target_market.screen_size_class = "legacy_large_screen"
    result = catforge_analyst.sku_fact_brief(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    fact_brief = result["result"]["fact_brief"]
    sections = fact_brief["sections"]
    assert sections["market"]["market_metrics"]["price_wavg"] == 4999.0
    assert sections["market"]["market_position"]["size_tier"] == "large_60_69"
    assert sections["parameter_fact"]["dimension_tier_profile"]["size"] == "large_60_69"
    assert sections["claim_fact"]["fact_claim_codes"] == ["tv_claim_miniled", "tv_claim_high_refresh"]
    assert sections["comment_fact"]["supported_claim_codes"] == ["tv_claim_miniled"]
    assert sections["user_task"]["primary_user_task_code"] == "TASK_CINEMA_IMMERSION"
    assert sections["target_group"]["primary_target_group_code"] == "TG_PREMIUM_AV_ENTHUSIAST"
    assert sections["value_battlefield"]["primary_battlefield_code"] == "BF_PREMIUM_PICTURE_UPGRADE"
    assert sections["sales_allocation"][0]["dimension_code"] == "BF_PREMIUM_PICTURE_UPGRADE"
    assert sections["market"]["market_pool"]["sku_count"] == 5
    assert sections["market"]["market_pool"]["size_tier"] == "large_60_69"
    assert sections["market"]["market_pool"]["target_rank_by_avg_weekly_sales"] == 2
    semantic_positions = sections["semantic_dimension_positions"]
    assert any(
        item["dimension_code"] == "TASK_CINEMA_IMMERSION"
        and item["market_space"]["estimated_sales_volume"] == 1100.0
        and item["sku_contribution"]["sku_rank_in_dimension"] == 2
        for item in semantic_positions
    )
    assert any(
        item["dimension_code"] == "TG_PREMIUM_AV_ENTHUSIAST"
        and item["market_space"]["estimated_sales_volume"] == 1000.0
        and item["sku_contribution"]["sku_rank_in_dimension"] == 1
        for item in semantic_positions
    )
    assert any(
        item["dimension_code"] == "BF_MAINSTREAM_LIVING_BALANCE"
        and item["market_space"]["estimated_sales_volume"] == 600.0
        and item["sku_allocation"] == {}
        and item["sku_contribution"] == {}
        for item in semantic_positions
    )
    assert fact_brief["missing_sections"] == []


def test_semantic_dimension_space_returns_m11d_market_space() -> None:
    session = make_session()
    result = catforge_analyst.semantic_dimension_space(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        dimension_type="battlefield",
        dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
        size_tier="large_60_69",
        price_band="mid_high",
    )

    assert result["status"] == "ok"
    assert result["result"]["summary_count"] == 1
    item = result["result"]["items"][0]
    assert item["summary"]["dimension_name"] == "高端画质升级战场"
    assert item["summary"]["estimated_sales_volume"] == 900.0
    assert item["sku_contributions"][0]["sku_code"] == "TV00029112"
    assert item["sku_contributions"][0]["size_tier"] == "large_60_69"


def test_same_size_price_candidates_returns_same_pool_candidates() -> None:
    session = make_session()
    result = catforge_analyst.same_size_price_candidates(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    search = result["result"]["candidate_search"]
    assert search["target_market"]["sku_code"] == "TV00029112"
    assert search["match_policy"] == "m07_same_size_price_band"
    candidate_codes = [item["sku_code"] for item in search["candidates"]]
    assert "TV00030001" in candidate_codes
    assert "TV00040001" in candidate_codes
    assert "TV00040002" in candidate_codes
    assert search["candidates"][0]["size_tier"] == "large_60_69"
    assert search["candidates"][0]["price_band_in_size_tier"] == "mid_high"


def test_ac_ask_infers_category_reads_facts_and_uses_m11c_sparse_pool() -> None:
    session = make_session()
    seed_ac_analyst_data(session)

    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        batch_id="latest",
        question="AC00038063的竞品有哪些",
        limit=5,
        answer_style="xiaoao",
        with_report="markdown",
    )

    assert result["status"] == "ok"
    assert result["category_code"] == "AC"
    assert result["product_category"] == "AC"
    assert result["batch_id"] == AC_BATCH_ID
    payload = result["result"]["competitor_set"]
    assert payload["candidate_count"] >= 2
    candidate_codes = [item["candidate"]["sku_code"] for item in payload["candidates"]]
    assert candidate_codes[:2] == ["AC00028640", "AC00029751"]
    fact_brief = payload["target_fact_brief"]
    sections = fact_brief["sections"]
    assert sections["claim_fact"]["fact_claim_codes"] == [
        "ac_claim_large_airflow_coverage",
        "ac_claim_self_cleaning",
        "ac_claim_smart_app_voice_iot",
    ]
    assert sections["comment_fact"]["supported_claim_codes"] == [
        "ac_claim_large_airflow_coverage",
        "ac_claim_self_cleaning",
    ]
    assert sections["user_task"]["primary_user_task_code"] == "TASK_LARGE_SPACE_COVERAGE"
    assert sections["target_group"]["primary_target_group_code"] == "TG_LIVING_ROOM_LARGE_SPACE"
    assert sections["value_battlefield"]["primary_battlefield_code"] == "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH"
    assert sections["market"]["market_position"]["price_band_in_size_tier"] == "high"
    assert sections["market"]["market_position"]["price_band_source"] == "M11C"
    assert "claim_fact" not in fact_brief["missing_sections"]
    assert "comment_fact" not in fact_brief["missing_sections"]
    markdown = result["result"]["competitor_answer"]["report_payload"]["markdown"]
    top_competitors = result["result"]["competitor_answer"]["top_competitors"]
    assert top_competitors[0]["candidate"]["sku_code"] == "AC00029751"
    assert top_competitors[0]["role"] == "primary_direct"
    assert "3匹及以上柜机高端舒适健康" in markdown
    assert "3匹及以上柜机" in markdown
    assert "用户买空调" in markdown
    assert "该匹数价格段空调" in markdown
    assert "匹数/安装能力" in markdown
    assert "清晰度规格" not in markdown
    assert "该尺寸价格段电视" not in markdown
    assert "尺寸段未知 × 价格带未知" not in markdown
    assert "未知 寸" not in markdown


def test_semantic_overlap_returns_task_group_battlefield_matches() -> None:
    session = make_session()
    result = catforge_analyst.semantic_overlap(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00030001",
    )

    assert result["status"] == "ok"
    overlap = result["result"]["semantic_overlap"]["overlap"]
    assert "TASK_CINEMA_IMMERSION" in overlap["user_task"]["matched_codes"]
    assert "TG_PREMIUM_AV_ENTHUSIAST" in overlap["target_group"]["matched_codes"]
    assert "BF_PREMIUM_PICTURE_UPGRADE" in overlap["value_battlefield"]["matched_codes"]
    assert result["result"]["semantic_overlap"]["semantic_overlap_score"] > 0


def test_pairwise_atom_tolerates_cli_limit_argument() -> None:
    session = make_session()
    result = catforge_analyst.run_analyst_command(
        session,
        command="semantic-overlap",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00030001",
        limit=20,
    )

    assert result["status"] == "ok"
    assert result["result"]["semantic_overlap"]["target_sku_code"] == "TV00029112"


def test_sales_overlap_uses_pairwise_overlap_weeks() -> None:
    session = make_session()
    result = catforge_analyst.sales_overlap(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00030001",
    )

    assert result["status"] == "ok"
    overlap = result["result"]["sales_overlap"]
    assert overlap["method"] == "pairwise_overlap_active_week_average"
    assert overlap["overlap_weeks"] == [2, 3]
    assert overlap["target"]["avg_weekly_sales_volume_on_overlap_weeks"] == 105.0
    assert overlap["candidate"]["avg_weekly_sales_volume_on_overlap_weeks"] == 75.0
    assert overlap["comparison"]["target_vs_candidate_avg_weekly_volume_gap"] == 30.0


def test_param_claim_overlap_returns_shared_params_and_claims() -> None:
    session = make_session()
    result = catforge_analyst.param_claim_overlap(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00030001",
    )

    assert result["status"] == "ok"
    overlap = result["result"]["param_claim_overlap"]
    assert "screen_size_inch" in overlap["parameter_overlap"]["matched_codes"]
    assert "refresh_rate_hz" in overlap["parameter_overlap"]["matched_codes"]
    assert "tv_claim_high_refresh" in overlap["claim_overlap"]["matched_codes"]
    assert "picture_flagship_miniled" in overlap["claim_position_overlap"]["target_only_codes"]


def test_comment_support_returns_claim_param_and_semantic_support() -> None:
    session = make_session()
    result = catforge_analyst.comment_support(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        claim_code="tv_claim_miniled",
        param_code="screen_size_inch",
        user_task_code="TASK_CINEMA_IMMERSION",
        target_group_code="TG_PREMIUM_AV_ENTHUSIAST",
        battlefield_code="BF_PREMIUM_PICTURE_UPGRADE",
    )

    assert result["status"] == "ok"
    support = result["result"]["comment_support"]
    statuses = {item["source_type"]: item["support_status"] for item in support["support_items"]}
    assert statuses["claim_code"] == "supported"
    assert statuses["param_code"] == "supported"
    assert statuses["user_task"] == "supported_or_established"
    assert statuses["target_group"] == "supported_or_established"
    assert statuses["battlefield"] == "supported_or_established"


def test_opportunity_gaps_returns_market_battlefield_and_fact_signals() -> None:
    session = make_session()
    result = catforge_analyst.opportunity_gaps(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    gaps = result["result"]["opportunity_gaps"]
    assert gaps["market_position"]["size_tier"] == "large_60_69"
    assert [item["dimension_code"] for item in gaps["opportunity_battlefields"]] == ["BF_GAMING_SPORTS_FLUENCY"]
    assert [item["dimension_code"] for item in gaps["drag_factor_battlefields"]] == ["BF_SMART_CONNECTED_EXPERIENCE"]
    assert gaps["opportunity_battlefields"][0]["market_space"]["estimated_sales_volume"] == 500.0
    claim_gap_codes = {item["gap_code"] for item in gaps["claim_gap_signals"]}
    semantic_gap_codes = {item["gap_code"] for item in gaps["semantic_gap_signals"]}
    assert "comment_claim_contradiction" in claim_gap_codes
    assert "opportunity_battlefields_present" in semantic_gap_codes
    assert "drag_factor_battlefields_present" in semantic_gap_codes


def test_competitor_set_sop_composes_candidate_evidence() -> None:
    session = make_session()
    result = catforge_analyst.competitor_set(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        limit=10,
    )

    assert result["status"] == "ok"
    payload = result["result"]["competitor_set"]
    assert payload["candidate_count"] >= 5
    candidate_codes = [item["candidate"]["sku_code"] for item in payload["candidates"]]
    assert "TV00030001" in candidate_codes
    assert "TV00040001" in candidate_codes
    assert payload["candidates"][0]["basis"]["same_size_price_pool"] is True
    overlap_methods = {item["candidate"]["sku_code"]: item["sales_overlap"]["method"] for item in payload["candidates"]}
    assert overlap_methods["TV00030001"] == "pairwise_overlap_active_week_average"
    assert [step["status"] for step in result["sop_steps"]] == ["ok", "ok", "ok", "ok", "ok", "ok"]


def test_competitor_set_fetches_full_claim_value_payload_for_reports() -> None:
    class FakeAtomicHandlers:
        def __init__(self) -> None:
            self.claim_value_limits: list[int] = []
            self.claim_contribution_limits: list[int] = []

        def resolve_sku(self, context: AnalystContext, **kwargs: object) -> dict[str, object]:
            return {
                "status": "ok",
                "command": "resolve-sku",
                "target": {
                    "sku_code": "TV00029112",
                    "brand_name": "海信",
                    "model_name": "65E7Q",
                    "product_category": "tv",
                },
            }

        def sku_fact_brief(self, context: AnalystContext, *, sku_code: str, limit: int = 20, **kwargs: object) -> dict[str, object]:
            return {
                "status": "ok",
                "command": "sku-fact-brief",
                "result": {
                    "fact_brief": {
                        "identity": {"sku_code": sku_code},
                        "sections": {},
                        "missing_sections": [],
                    }
                },
            }

        def same_size_price_candidates(self, context: AnalystContext, **kwargs: object) -> dict[str, object]:
            return {
                "status": "ok",
                "command": "same-size-price-candidates",
                "result": {
                    "candidate_search": {
                        "candidates": [
                            {
                                "sku_code": "TV00030001",
                                "brand_name": "创维",
                                "model_name": "65A7H PRO",
                                "screen_size_inch": 65,
                                "price_wavg": 5600,
                                "avg_weekly_sales_volume": 210,
                            }
                        ]
                    }
                },
            }

        def semantic_overlap(self, context: AnalystContext, **kwargs: object) -> dict[str, object]:
            return {
                "status": "ok",
                "command": "semantic-overlap",
                "result": {"semantic_overlap": {"semantic_overlap_score": 0.8, "overlap": {}}},
            }

        def param_claim_overlap(self, context: AnalystContext, **kwargs: object) -> dict[str, object]:
            return {
                "status": "ok",
                "command": "param-claim-overlap",
                "result": {"param_claim_overlap": {"param_claim_overlap_score": 0.7}},
            }

        def sales_overlap(self, context: AnalystContext, **kwargs: object) -> dict[str, object]:
            return {
                "status": "ok",
                "command": "sales-overlap",
                "result": {
                    "sales_overlap": {
                        "comparison": {
                            "target_vs_candidate_avg_weekly_volume_ratio": 1.1,
                            "target_vs_candidate_avg_weekly_volume_gap": 20,
                        }
                    }
                },
            }

        def sku_claim_value(self, context: AnalystContext, *, limit: int = 20, **kwargs: object) -> dict[str, object]:
            self.claim_value_limits.append(limit)
            return {
                "status": "ok",
                "command": "sku-claim-value",
                "result": {"sku_claim_value": {"claim_values": []}},
            }

        def claim_contribution(self, context: AnalystContext, *, limit: int = 20, **kwargs: object) -> dict[str, object]:
            self.claim_contribution_limits.append(limit)
            return {
                "status": "ok",
                "command": "claim-contribution",
                "result": {"claim_contribution": {"attributions": []}},
            }

    fake = FakeAtomicHandlers()
    orchestrator = SopOrchestrators(fake)  # type: ignore[arg-type]
    context = AnalystContext(project_id=PROJECT_ID, category_code="TV", batch_id=BATCH_ID, product_category="tv")

    result = orchestrator.competitor_set(context, sku_code="TV00029112", limit=20, answer_style="xiaoao")

    assert result["status"] == "ok"
    assert fake.claim_value_limits == [CLAIM_VALUE_REPORT_LIMIT, CLAIM_VALUE_REPORT_LIMIT]
    assert fake.claim_contribution_limits == [CLAIM_VALUE_REPORT_LIMIT, CLAIM_VALUE_REPORT_LIMIT]


def test_competitor_set_xiaoao_answer_prioritizes_business_pressure() -> None:
    session = make_session()
    result = catforge_analyst.competitor_set(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        limit=10,
        answer_style="xiaoao",
        with_report="markdown",
        max_chat_chars=600,
    )

    assert result["status"] == "ok"
    answer = result["result"]["competitor_answer"]
    top_codes = [item["candidate"]["sku_code"] for item in answer["top_competitors"]]
    assert top_codes[:3] == ["TV00040001", "TV00040003", "TV00040004"]
    assert "TV00040002" not in top_codes[:2]
    assert answer["top_competitors"][0]["role"] == "primary_direct"
    assert answer["top_competitors"][0]["weighted_overlap"]["target_group"] >= answer["top_competitors"][1]["weighted_overlap"]["target_group"]
    markdown = answer["report_payload"]["markdown"]
    assert markdown.startswith("# 海信 65E7Q 重点竞品分析报告")
    assert "## 一、分析结论" in markdown
    assert "## 二、分析过程" in markdown
    assert "### 2.1 候选 SKU 综合评分" in markdown
    assert "替代压力 5" in markdown
    assert "### 2.5 关键价值锚点、替代压力和市场验证依据" in markdown
    assert "## 三、四个产品详情链接" in markdown
    assert "[海信 65E7Q 产品画像](#profile-target)" in markdown
    assert "[创维 65A7H PRO 产品画像](#profile-competitor-1)" in markdown
    assert "## 四、四个产品横向详细对比" in markdown
    assert "| 比较内容 | 海信 65E7Q | 创维 65A7H PRO | TCL 65Q9L PRO | 创维 65A6F ULTRA |" in markdown
    assert "### 4.1 市场画像" in markdown
    assert "### 4.2 价值战场画像" in markdown
    assert "### 4.3 用户任务画像" in markdown
    assert "### 4.4 目标客群画像" in markdown
    assert "### 4.5 卖点画像" in markdown
    assert "### 4.6 参数画像" in markdown
    assert "### 4.7 卖点价值量化" in markdown
    assert "| 主价值战场 | 高端画质升级 | 高端画质升级 | 游戏体育流畅 | 高配下探价值 |" in markdown
    assert "| 命中的固定价值战场 |" in markdown
    assert "| 补充证据判断 |" in markdown
    assert "| 主用户任务 | 影院沉浸观影 | 影院沉浸观影 | 主机游戏娱乐 | 影院沉浸观影 |" in markdown
    assert "| 主目标客群 | 高端影音体验用户 | 高端影音体验用户 | 游戏体育娱乐用户 | 主流家庭观影用户 |" in markdown
    assert "| 事实卖点 | 高刷新率和MiniLED 显示 | 贴墙安装、高刷新率和MiniLED 显示 | HDMI 2.1 连接、高刷新率和MiniLED 显示 | 护眼显示和MiniLED 显示 |" in markdown
    assert "| 本品分类与卖点 | 海信 65E7Q | 创维 65A7H PRO | TCL 65Q9L PRO | 创维 65A6F ULTRA |" in markdown
    assert "| 强溢价卖点：MiniLED | 战场价差合计280元；战场销量合计15台/周；战场销额合计75,000元/周；覆盖高端画质升级战场 | 未进入强溢价卖点 | 未进入强溢价卖点 | 未进入强溢价卖点 |" in markdown
    assert "| 强销量卖点：高刷 | 战场价差合计80元；战场销量合计22台/周；战场销额合计88,000元/周；覆盖游戏体育流畅战场 | 未进入强销量卖点 | 未进入强销量卖点 | 未进入强销量卖点 |" in markdown
    assert "横向比较口径：本表以本品的业务分类和具体卖点为基准" in markdown
    assert "| 组合型增值卖点 |" not in markdown
    assert "| 基础门槛卖点 |" not in markdown
    assert "卖点溢价指数 Top" not in markdown
    assert "## 五、海信 65E7Q 产品画像" in markdown
    assert "市场画像" in markdown
    assert "价值战场画像" in markdown
    assert "用户任务画像" in markdown
    assert "目标客群画像" in markdown
    assert "卖点画像" in markdown
    assert "参数画像" in markdown
    assert "卖点价值量化" in markdown
    assert "所在池空间" in markdown
    assert "池内销量表现" in markdown
    assert "空间900台；周均75台；覆盖2个SKU" in markdown
    assert "分配700台；周均58台；权重60%；维度内第1名；占维度销量78%" in markdown
    assert "主流客厅均衡体验 | 辅战场 | 空间600台" in markdown
    assert "当前图谱未分配本品销量" in markdown
    assert "影院沉浸观影 | 主任务和评论观察任务 | 空间1,100台" in markdown
    assert "高端影音体验用户 | 主客群和评论观察客群 | 空间1,000台" in markdown
    assert "MiniLED 高端画质路线" in markdown
    assert "4K（3840x2160）" in markdown
    assert "量子点：未见" in markdown
    assert "5200尼特" in markdown
    assert "控光分区：1,920" in markdown
    assert "溢价卖点" in markdown
    assert "#### 强溢价卖点" in markdown
    assert "| MiniLED | 280元 | 15台/周 | 75,000元/周 | 高端画质升级战场 | 参数强，评论强，市场场景强 |" in markdown
    assert "#### 强销量卖点" in markdown
    assert "| 高刷 | 80元 | 22台/周 | 88,000元/周 | 游戏体育流畅战场 | 参数强，评论强，市场场景强 |" in markdown
    assert "#### 用户感知风险/拖后腿" in markdown
    assert "用户感知风险/拖后腿：音响体验" in markdown
    assert "该卖点存在用户感知不足、负向反馈或证据支撑不足，可能削弱相关场景的成交解释" in markdown
    assert "| 音响体验 | 0元 | 0台/周 | 0元/周 |" not in markdown
    assert "| MiniLED | 高端画质升级战场 | 400元 | 20台/周 | 280元 | 15台/周 |" in markdown
    assert "战场可解释价差/销量/销额合计，只汇总同一分类、同一卖点在价值战场中的去重量化结果" in markdown
    assert "业务类型说明：" in markdown
    assert "卖点解释：" in markdown
    assert "竞品拦截与补强建议：" in markdown
    assert "本品相对可比产品表现差异" in markdown
    assert "卖点贡献归因" not in markdown
    assert "语义上下文" not in markdown
    assert "卖点价值量化待生成" in markdown
    for forbidden in (
        "CLI",
        "JSON",
        "M03B",
        "BF_",
        "TG_",
        "TASK_",
        "mid_high",
        "mini_led_flag",
        "resolution_pixels",
        "core_picture_params",
        "{'unit'",
        '"unit"',
        "其他关系状态",
        "图谱空间待生成",
        "核心事实优势/暂不量化",
        "暂无该分类市场空间数据",
        "本品未进入该分类销量承接分配",
        "未分配销量，仅作机会或风险证据",
        "产品经理策略",
        "市场导购话术",
        "海信应对策略",
    ):
        assert forbidden not in markdown
    assert not re.search(r"\d+\.\d+台", markdown)
    short_answer = answer["short_answer"]
    assert len(short_answer) <= 600
    assert "创维 65A7H PRO" in short_answer
    assert "小米 L65MC-SP" not in short_answer.split("详细分析报告")[0] or "价格贴身" in short_answer
    assert "详细分析报告暂未生成" in short_answer
    for forbidden in ("CLI", "JSON", "M03B", "BF_", "TG_", "TASK_", "mid_high"):
        assert forbidden not in short_answer


def test_competitor_set_text_format_is_business_facing() -> None:
    session = make_session()
    result = catforge_analyst.competitor_set(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        limit=10,
    )

    text = catforge_analyst.format_business_text(result)

    assert text.startswith("结论：")
    assert "海信 65E7Q" in text
    assert "创维 65A7H PRO" in text
    assert "判断依据：" in text
    assert "口径与限制：" in text
    assert "CLI" not in text
    assert "CatForge" not in text
    assert "M07" not in text
    assert "BF_" not in text
    assert "TG_" not in text
    assert "TASK_" not in text
    assert "mid_high" not in text


def test_competitor_set_text_uses_xiaoao_short_answer() -> None:
    session = make_session()
    result = catforge_analyst.competitor_set(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        limit=10,
        answer_style="xiaoao",
        with_report="markdown",
    )

    text = catforge_analyst.format_business_text(result)

    assert text == result["result"]["competitor_answer"]["short_answer"]
    assert text.startswith("海信 65E7Q 的重点竞品建议看")


def test_competitor_answer_parses_feishu_docx_token() -> None:
    assert competitor_answer._extract_feishu_doc_token("https://my.feishu.cn/docx/RugxdBRmEoKHCdxseo8csmktnSb") == (
        "RugxdBRmEoKHCdxseo8csmktnSb",
        "docx",
    )
    assert competitor_answer._extract_feishu_doc_token("https://my.feishu.cn/sheets/AbCdEf") == ("AbCdEf", "sheet")


def test_xiaoao_short_answer_downgrades_when_semantic_evidence_missing() -> None:
    text = competitor_answer.render_short_answer(
        target={"brand_name": "海信", "model_name": "85E7S"},
        target_fact_brief={"sections": {"claim_fact": {"fact_claim_codes": ["tv_claim_miniled_display"]}}},
        top_competitors=[
            {
                "candidate": {"brand_name": "小米", "model_name": "L85MC-SP"},
                "value_anchor": {"shared_anchors": ["高端画质", "游戏流畅"]},
                "replacement_pressure": {"type_cn": "价值替代压力"},
                "role_cn": "强配置对标竞品",
            },
            {
                "candidate": {"brand_name": "TCL", "model_name": "85Q9M"},
                "value_anchor": {"shared_anchors": ["高端画质"]},
                "replacement_pressure": {"type_cn": "价值替代压力"},
                "role_cn": "强配置对标竞品",
            },
        ],
        report_url=None,
        max_chat_chars=600,
    )

    assert "主辅价值战场、用户任务和目标客群的有效重合更完整" not in text
    assert "当前缺少用户评论或语义图谱验证" in text
    assert "参数/卖点替代压力" in text


def test_sku_business_brief_sop_returns_summary_sections() -> None:
    session = make_session()
    result = catforge_analyst.sku_business_brief(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    brief = result["result"]["sku_business_brief"]
    assert brief["primary_semantics"]["primary_battlefield_code"] == "BF_PREMIUM_PICTURE_UPGRADE"
    assert "TV00030001" in {item["sku_code"] for item in brief["top_same_size_price_candidates"]}
    assert brief["opportunity_and_risk"]["opportunity_battlefields"][0]["dimension_code"] == "BF_GAMING_SPORTS_FLUENCY"


def test_why_sales_diff_sop_uses_overlap_week_sales() -> None:
    session = make_session()
    result = catforge_analyst.why_sales_diff(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
        candidate_sku_code="TV00030001",
    )

    assert result["status"] == "ok"
    payload = result["result"]["why_sales_diff"]
    assert payload["sales_overlap"]["method"] == "pairwise_overlap_active_week_average"
    assert payload["sales_overlap"]["comparison"]["target_vs_candidate_avg_weekly_volume_gap"] == 30.0
    assert payload["factor_summary"][0]["factor_code"] == "overlap_week_sales_gap"


def test_premium_claim_drivers_sop_classifies_claims() -> None:
    session = make_session()
    result = catforge_analyst.premium_claim_drivers(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    payload = result["result"]["premium_claim_drivers"]
    assert payload["premium_driver_claim_codes"] == ["tv_claim_miniled"]
    assert payload["drag_factor_claim_codes"] == ["tv_claim_high_refresh"]
    assert payload["semantic_context"]["primary_battlefield_code"] == "BF_PREMIUM_PICTURE_UPGRADE"


def test_battlefield_space_sop_returns_graph_space() -> None:
    session = make_session()
    result = catforge_analyst.battlefield_space(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
    )

    assert result["status"] == "ok"
    payload = result["result"]["battlefield_space"]
    assert payload["summary_count"] == 1
    assert payload["items"][0]["summary"]["dimension_code"] == "BF_PREMIUM_PICTURE_UPGRADE"


def test_battlefield_opportunity_sop_returns_related_spaces() -> None:
    session = make_session()
    result = catforge_analyst.battlefield_opportunity(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        sku_code="TV00029112",
    )

    assert result["status"] == "ok"
    payload = result["result"]["battlefield_opportunity"]
    assert payload["opportunity_gaps"]["opportunity_battlefields"][0]["dimension_code"] == "BF_GAMING_SPORTS_FLUENCY"
    space_codes = {
        item["items"][0]["summary"]["dimension_code"]
        for item in payload["related_battlefield_spaces"]
        if item.get("items")
    }
    assert {"BF_GAMING_SPORTS_FLUENCY", "BF_SMART_CONNECTED_EXPERIENCE"} <= space_codes


def test_ask_routes_competitor_question_to_sop() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="海信65E7Q和谁竞争？",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "competitor-set"
    assert result["routing"]["extracted_params"]["model_name"] == "65E7Q"
    assert result["target"]["sku_code"] == "TV00029112"
    candidate_codes = [item["candidate"]["sku_code"] for item in result["result"]["competitor_set"]["candidates"]]
    assert "TV00030001" in candidate_codes
    assert "TV00040001" in candidate_codes
    assert [step["step_code"] for step in result["sop_steps"]][:3] == [
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
    ]


def test_ask_routes_competitor_reason_question_without_candidate_to_competitor_set() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="海信65E7Q和谁竞争，为什么？",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "competitor-set"
    assert result["routing"]["matched_rule"] == "competitor_set"
    assert result["routing"]["extracted_params"]["model_name"] == "65E7Q"
    candidate_codes = [item["candidate"]["sku_code"] for item in result["result"]["competitor_set"]["candidates"]]
    assert "TV00030001" in candidate_codes
    assert "TV00040001" in candidate_codes


def test_ask_routes_pairwise_sales_diff_from_sku_codes() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="TV00029112 和 TV00030001 为什么销量差？",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "why-sales-diff"
    assert result["routing"]["extracted_params"]["sku_code"] == "TV00029112"
    assert result["routing"]["extracted_params"]["candidate_sku_code"] == "TV00030001"
    assert result["result"]["why_sales_diff"]["sales_overlap"]["method"] == "pairwise_overlap_active_week_average"


def test_ask_routes_battlefield_space_from_chinese_name() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="高端画质升级战场有哪些SKU？",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "battlefield-space"
    assert result["routing"]["extracted_params"]["query"] == "高端画质升级战场"
    assert result["result"]["battlefield_space"]["items"][0]["summary"]["dimension_code"] == "BF_PREMIUM_PICTURE_UPGRADE"


def test_ask_routes_premium_claim_question_to_sop() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="TV00029112 的哪些卖点是溢价卖点？",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "premium-claim-drivers"
    assert result["result"]["premium_claim_drivers"]["premium_driver_claim_codes"] == ["tv_claim_miniled"]
    m12c_payload = result["result"]["premium_claim_drivers"]["m12c_quantified_claim_values"]
    assert m12c_payload["role_counts"]["premium_driver_estimated"] == 1


def test_ask_routes_comment_support_with_explicit_code_filter() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="TV00029112 的评论是否支撑这个卖点？",
        claim_code="tv_claim_miniled",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "comment-support"
    support = result["result"]["comment_support"]["support_items"][0]
    assert support["code"] == "tv_claim_miniled"
    assert support["support_status"] == "supported"


def test_ask_routes_battlefield_opportunity_question_to_sop() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="TV00029112 有没有机会进入更多战场？",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "battlefield-opportunity"
    assert result["result"]["battlefield_opportunity"]["opportunity_gaps"]["opportunity_battlefields"][0]["dimension_code"] == "BF_GAMING_SPORTS_FLUENCY"


def test_ask_keeps_explicit_sku_over_extracted_model() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="海信65E7Q的业务画像",
        sku_code="TV00030001",
    )

    assert result["status"] == "ok"
    assert result["routed_command"] == "sku-business-brief"
    assert result["routing"]["applied_params"]["sku_code"] == "TV00030001"
    assert result["target"]["sku_code"] == "TV00030001"
