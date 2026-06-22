from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_analyst
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M11D_RULE_VERSION,
)


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_analyst_test"


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
        entities.Core3SemanticMarketDimensionSummary.__table__,
        entities.Core3SemanticMarketSkuContribution.__table__,
        entities.Core3SemanticMarketAllocation.__table__,
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
    seed_fact_profiles(session)
    seed_candidate_fact_profiles(session)
    seed_weekly_market(session)
    seed_semantic_space(session)
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
            price_band_category="mid_high",
            price_band_size="mid_high",
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
            core_picture_params_json={"screen_size_inch": {"normalized_value": 65}},
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
            claim_comment_support_json={"tv_claim_miniled": {"positive": 5}},
            supported_param_codes=["screen_size_inch"],
            supported_claim_codes=["tv_claim_miniled"],
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


def test_sku_fact_brief_returns_core_fact_sections() -> None:
    session = make_session()
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
    assert sections["parameter_fact"]["dimension_tier_profile"]["size"] == "large_60_69"
    assert sections["claim_fact"]["fact_claim_codes"] == ["tv_claim_miniled", "tv_claim_high_refresh"]
    assert sections["comment_fact"]["supported_claim_codes"] == ["tv_claim_miniled"]
    assert sections["user_task"]["primary_user_task_code"] == "TASK_CINEMA_IMMERSION"
    assert sections["target_group"]["primary_target_group_code"] == "TG_PREMIUM_AV_ENTHUSIAST"
    assert sections["value_battlefield"]["primary_battlefield_code"] == "BF_PREMIUM_PICTURE_UPGRADE"
    assert sections["sales_allocation"][0]["dimension_code"] == "BF_PREMIUM_PICTURE_UPGRADE"
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
    assert [item["sku_code"] for item in search["candidates"]] == ["TV00030001"]
    assert search["candidates"][0]["size_tier"] == "large_60_69"
    assert search["candidates"][0]["price_band_in_size_tier"] == "mid_high"


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


def test_ask_routes_competitor_question_to_sop_placeholder() -> None:
    session = make_session()
    result = catforge_analyst.answer_natural_language(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="tv",
        question="海信65E7Q和谁竞争？",
        query="65E7Q",
    )

    assert result["status"] == "not_implemented"
    assert result["routed_command"] == "competitor-set"
    assert [step["step_code"] for step in result["sop_steps"]][:3] == [
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
    ]
