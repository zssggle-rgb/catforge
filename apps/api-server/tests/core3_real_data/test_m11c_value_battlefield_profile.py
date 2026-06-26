from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_insight, catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    Core3RunStatus,
    Core3SourceBatchStatus,
)
from app.services.core3_real_data.m11c_value_battlefield_service import (
    M11CValueBattlefieldTaxonomyLoader,
    M11CRunner,
    _canonical_size_tier,
    _derive_comparable_market_contexts,
    _derive_price_bands,
    _market_validation_score,
    ac_value_battlefield_taxonomy_v0_1,
)


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606210011"
SKU_VALUE = "TV00090001"
SKU_MID = "TV00090002"
SKU_HIGH = "TV00090003"
SKU_GIANT_VALUE = "TV00090004"
SKU_GIANT_FLAGSHIP = "TV00090005"
SKU_HISENSE_65E7Q = "TV00029112"
AC_BATCH_ID = "m00_202606210012_ac"
AC_LOW = "AC000LOW"
AC_MID = "AC000MID"
AC_HIGH = "AC000HIGH"


def test_m11c_ac_value_battlefield_taxonomy_is_published_with_hp_price_gates() -> None:
    taxonomy = ac_value_battlefield_taxonomy_v0_1()
    loaded = M11CValueBattlefieldTaxonomyLoader().load(
        CORE3_M11C_AC_TAXONOMY_VERSION, product_category="AC"
    )
    config = catforge_pipeline.product_category_config("ac")
    insight_result = catforge_insight.query_value_battlefield_taxonomy(
        product_category="AC"
    )

    assert taxonomy.taxonomy_version == CORE3_M11C_AC_TAXONOMY_VERSION
    assert loaded.product_category == "AC"
    assert (
        config["value_battlefield_taxonomy_version"] == CORE3_M11C_AC_TAXONOMY_VERSION
    )
    assert insight_result["battlefield_count"] == 11
    assert taxonomy.battlefields_by_code[
        "BF_WALL_1_5_MAINSTREAM_VALUE"
    ].allowed_size_tiers == ("wall_hp_1_5",)
    assert taxonomy.battlefields_by_code[
        "BF_WALL_1_5_MAINSTREAM_VALUE"
    ].allowed_price_bands == ("low", "mid_low", "mid")
    assert taxonomy.battlefields_by_code[
        "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH"
    ].allowed_size_tiers == ("floor_hp_3", "floor_hp_3_plus")
    assert taxonomy.battlefields_by_code[
        "BF_FLOOR_3_PREMIUM_COMFORT_HEALTH"
    ].allowed_price_bands == ("mid_high", "high")


def test_m11c_canonical_size_tier_supports_ac_hp_segments() -> None:
    wall_profile = ac_param_profile(
        "AC0001",
        dimension_tier_profile={"installation": "wall_mounted", "horsepower": "hp_1_5"},
        installation_type="wall_mounted",
        horsepower_hp=Decimal("1.5"),
    )
    floor_profile = ac_param_profile(
        "AC0002",
        dimension_tier_profile={"installation": "floor_standing", "horsepower": "hp_3"},
        installation_type="floor_standing",
        horsepower_hp=Decimal("3"),
    )

    assert _canonical_size_tier(wall_profile) == "wall_hp_1_5"
    assert _canonical_size_tier(floor_profile) == "floor_hp_3"


def test_m11c_single_sku_scope_uses_full_ac_batch_for_hp_price_band() -> None:
    session = make_session()
    seed_ac_batch(session)

    result = M11CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="AC",
        batch_id=AC_BATCH_ID,
        product_category="AC",
        taxonomy_version=CORE3_M11C_AC_TAXONOMY_VERSION,
        rule_version=CORE3_M11C_AC_RULE_VERSION,
        target_sku_codes=[AC_LOW],
        force_rebuild=True,
    )
    session.commit()

    assert result.status in {Core3RunStatus.SUCCESS.value, Core3RunStatus.WARNING.value}
    assert result.summary_json["sku_count"] == 1
    assert result.summary_json["size_price_counts"] == {"wall_hp_1_5:low": 1}

    profile = session.execute(
        select(entities.Core3SkuValueBattlefieldProfile).where(
            entities.Core3SkuValueBattlefieldProfile.batch_id == AC_BATCH_ID,
            entities.Core3SkuValueBattlefieldProfile.category_code == "AC",
            entities.Core3SkuValueBattlefieldProfile.sku_code == AC_LOW,
        )
    ).scalar_one()
    assert profile.size_tier == "wall_hp_1_5"
    assert profile.price_band_in_size_tier == "low"
    assert profile.price_percentile_in_size_tier == Decimal("0.0000")


def test_ac_floor_hp_3_plus_borrows_floor_hp_3_price_context() -> None:
    base_inputs = [
        (entities.Core3SkuParamProfile(sku_code="AC3A"), "floor_hp_3"),
        (entities.Core3SkuParamProfile(sku_code="AC3B"), "floor_hp_3"),
        (entities.Core3SkuParamProfile(sku_code="ACPLUS"), "floor_hp_3_plus"),
    ]
    market_profiles = {
        "AC3A": entities.Core3SkuMarketProfile(
            sku_code="AC3A", price_wavg=Decimal("5200")
        ),
        "AC3B": entities.Core3SkuMarketProfile(
            sku_code="AC3B", price_wavg=Decimal("6500")
        ),
        "ACPLUS": entities.Core3SkuMarketProfile(
            sku_code="ACPLUS", price_wavg=Decimal("7200")
        ),
    }
    weekly_rows = [
        *_weekly_rows(
            "AC3A", start=1, end=4, weekly_volume=Decimal("20"), price=Decimal("5200")
        ),
        *_weekly_rows(
            "AC3B", start=1, end=4, weekly_volume=Decimal("30"), price=Decimal("6500")
        ),
        *_weekly_rows(
            "ACPLUS", start=1, end=4, weekly_volume=Decimal("40"), price=Decimal("7200")
        ),
    ]

    price_bands = _derive_price_bands(base_inputs, market_profiles)
    contexts = _derive_comparable_market_contexts(base_inputs, weekly_rows)

    assert price_bands["ACPLUS"] == ("high", Decimal("1.0000"))
    assert contexts["ACPLUS"]["size_tier"] == "floor_hp_3_plus"
    assert contexts["ACPLUS"]["comparison_size_tiers"] == [
        "floor_hp_3",
        "floor_hp_3_plus",
    ]
    assert contexts["ACPLUS"]["borrowed_adjacent_context_pool"] is True
    assert contexts["ACPLUS"]["qualified_peer_count"] == 2


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
        entities.Core3SkuParamProfile.__table__,
        entities.Core3SkuMarketProfile.__table__,
        entities.Core3CleanMarketWeekly.__table__,
        entities.Core3SkuClaimFactProfile.__table__,
        entities.Core3SkuClaimFact.__table__,
        entities.Core3SkuCommentFactProfile.__table__,
        entities.Core3CommentFactAtom.__table__,
        entities.Core3SkuValueBattlefieldProfile.__table__,
        entities.Core3SkuValueBattlefieldScore.__table__,
        entities.Core3ValueBattlefieldGraphSnapshot.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)
    session = Session(engine)
    seed_foundation(session)
    return session


def ac_param_profile(
    sku_code: str,
    *,
    dimension_tier_profile: dict[str, str],
    installation_type: str,
    horsepower_hp: Decimal,
    batch_id: str = BATCH_ID,
) -> entities.Core3SkuParamProfile:
    return entities.Core3SkuParamProfile(
        sku_param_profile_id=f"param-{sku_code}",
        project_id=PROJECT_ID,
        category_code="AC",
        batch_id=batch_id,
        sku_code=sku_code,
        model_name=sku_code,
        param_values_json={
            "dimension_tier_profile": dimension_tier_profile,
            "installation_type": {
                "normalized_value": installation_type,
                "value_presence": "present",
            },
            "horsepower_hp": {
                "normalized_value": str(horsepower_hp),
                "numeric_value": str(horsepower_hp),
                "value_presence": "present",
            },
        },
        core_picture_params_json={},
        core_gaming_params_json={},
        core_system_params_json={},
        core_eye_care_params_json={},
        param_completeness=Decimal("0.800000"),
        known_param_count=3,
        unknown_param_count=0,
        conflict_count=0,
        review_required_count=0,
        evidence_ids=[f"ev-param-{sku_code}"],
        quality_summary_json={},
        profile_hash=f"sha256:param-{sku_code}",
        seed_version=CORE3_M03B_AC_TAXONOMY_VERSION,
        rule_version=CORE3_M03B_AC_RULE_VERSION,
    )


def seed_foundation(session: Session) -> None:
    session.add(
        entities.CategoryProject(
            project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=[
                "week_sales_data",
                "attribute_data",
                "selling_points_data",
                "comment_data",
            ],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    seed_sku(
        session,
        SKU_VALUE,
        "75X-Value",
        "海信",
        size=75,
        price=Decimal("2999"),
        volume=Decimal("900"),
    )
    seed_sku(
        session,
        SKU_MID,
        "75X-Mid",
        "TCL",
        size=75,
        price=Decimal("5999"),
        volume=Decimal("300"),
    )
    seed_sku(
        session,
        SKU_HIGH,
        "85X-High",
        "索尼",
        size=85,
        price=Decimal("9999"),
        volume=Decimal("100"),
    )
    seed_sku(
        session,
        SKU_GIANT_VALUE,
        "100X-Value",
        "海信",
        size=100,
        price=Decimal("8999"),
        volume=Decimal("480"),
    )
    seed_sku(
        session,
        SKU_GIANT_FLAGSHIP,
        "100X-Flagship",
        "索尼",
        size=100,
        price=Decimal("39999"),
        volume=Decimal("60"),
    )
    seed_value_sku_claims(
        session, sku_code=SKU_VALUE, model_name="75X-Value", brand_name="海信"
    )
    seed_value_sku_comments(
        session, sku_code=SKU_VALUE, model_name="75X-Value", brand_name="海信"
    )
    seed_value_sku_claims(
        session, sku_code=SKU_GIANT_VALUE, model_name="100X-Value", brand_name="海信"
    )
    seed_value_sku_comments(
        session, sku_code=SKU_GIANT_VALUE, model_name="100X-Value", brand_name="海信"
    )
    session.commit()


def seed_ac_batch(session: Session) -> None:
    session.add(
        entities.Core3SourceBatch(
            batch_id=AC_BATCH_ID,
            project_id=PROJECT_ID,
            category_code="AC",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=[
                "week_sales_data",
                "attribute_data",
                "selling_points_data",
                "comment_data",
            ],
            ruleset_version="ac-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    seed_ac_sku(session, AC_LOW, price=Decimal("1500"), volume=Decimal("500"))
    seed_ac_sku(session, AC_MID, price=Decimal("3000"), volume=Decimal("300"))
    seed_ac_sku(session, AC_HIGH, price=Decimal("6000"), volume=Decimal("100"))
    session.commit()


def seed_ac_sku(
    session: Session, sku_code: str, *, price: Decimal, volume: Decimal
) -> None:
    amount = price * volume
    session.add(
        ac_param_profile(
            sku_code,
            dimension_tier_profile={
                "installation": "wall_mounted",
                "horsepower": "hp_1_5",
            },
            installation_type="wall_mounted",
            horsepower_hp=Decimal("1.5"),
            batch_id=AC_BATCH_ID,
        )
    )
    session.add(
        entities.Core3SkuMarketProfile(
            profile_id=f"market-profile-{sku_code}",
            sku_market_profile_id=f"market-{sku_code}",
            project_id=PROJECT_ID,
            category_code="AC",
            batch_id=AC_BATCH_ID,
            sku_code=sku_code,
            model_name=sku_code,
            brand_name="海信" if sku_code == AC_LOW else "竞品",
            analysis_window="full_observed_window",
            active_week_count=4,
            market_row_count=4,
            platform_count=1,
            size_segment="wall_hp_1_5",
            screen_size_class="wall_hp_1_5",
            sales_volume_total=volume,
            sales_amount_total=amount,
            price_wavg=price,
            price_median=price,
            volume_percentile_in_size=Decimal("0.500000"),
            amount_percentile_in_size=Decimal("0.500000"),
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=[f"ev-market-{sku_code}"],
            rule_version=CORE3_M07_RULE_VERSION,
            input_fingerprint=f"fp-{sku_code}",
            result_hash=f"sha256:market-{sku_code}",
        )
    )
    weekly_volume = volume / Decimal("4")
    weekly_amount = amount / Decimal("4")
    for week in range(1, 5):
        session.add(
            entities.Core3CleanMarketWeekly(
                project_id=PROJECT_ID,
                category_code="AC",
                batch_id=AC_BATCH_ID,
                source_table="week_sales_data",
                source_pk=f"ac-market-week-{sku_code}-{week}",
                source_row_id=f"ac-market-week-{sku_code}-{week}",
                source_operation_type="insert",
                sku_code=sku_code,
                model_name=sku_code,
                brand_name="海信" if sku_code == AC_LOW else "竞品",
                period_raw=f"26W{week:02d}",
                period_type="week",
                period_week_index=week,
                channel_type="online",
                platform_type="test_platform",
                sales_volume=weekly_volume,
                sales_amount=weekly_amount,
                avg_price=price,
                price_check_status="ok",
                clean_record_key=f"ac-market-week-{sku_code}-{week}",
                clean_hash=f"sha256:ac-market-week-{sku_code}-{week}",
                clean_version="test",
                hash_version="test",
                record_status="active",
                quality_status="ok",
                quality_flags=[],
                review_required=False,
                review_status="auto_pass",
            )
        )


def seed_sku(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    *,
    size: int,
    price: Decimal,
    volume: Decimal,
) -> None:
    amount = price * volume
    if size >= 98:
        size_tier = "giant_98_plus"
    elif size >= 70:
        size_tier = "xlarge_70_85"
    elif size >= 60:
        size_tier = "large_60_69"
    elif size >= 46:
        size_tier = "medium_46_59"
    else:
        size_tier = "small_32_45"
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id=f"param-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            param_values_json={
                "screen_size_inch": {
                    "normalized_value": size,
                    "numeric_value": size,
                    "value_presence": "present",
                },
                "resolution_class": {
                    "normalized_value": "4K",
                    "value_text": "4K",
                    "value_presence": "present",
                },
                "hdr_support_flag": {
                    "normalized_value": True,
                    "value_presence": "present",
                },
                "declared_brightness_nit_or_band": {
                    "normalized_value": 600,
                    "numeric_value": 600,
                    "value_presence": "present",
                },
                "full_screen_design_flag": {
                    "normalized_value": True,
                    "value_presence": "present",
                },
                "dimension_tier_profile": {"size": size_tier},
            },
            core_picture_params_json={},
            core_gaming_params_json={},
            core_system_params_json={},
            core_eye_care_params_json={},
            param_completeness=Decimal("0.800000"),
            known_param_count=5,
            unknown_param_count=0,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=[f"ev-param-{sku_code}"],
            quality_summary_json={},
            profile_hash=f"sha256:param-{sku_code}",
            seed_version=CORE3_M03B_TAXONOMY_VERSION,
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuMarketProfile(
            profile_id=f"market-profile-{sku_code}",
            sku_market_profile_id=f"market-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            analysis_window="full_observed_window",
            active_week_count=12,
            market_row_count=24,
            platform_count=2,
            screen_size_inch=Decimal(str(size)),
            size_segment="75_85",
            screen_size_class="large_upgrade",
            sales_volume_total=volume,
            sales_amount_total=amount,
            price_wavg=price,
            price_median=price,
            price_per_inch=price / Decimal(size),
            volume_percentile_in_size=Decimal("0.900000")
            if sku_code == SKU_VALUE
            else Decimal("0.300000"),
            amount_percentile_in_size=Decimal("0.800000")
            if sku_code == SKU_VALUE
            else Decimal("0.200000"),
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=[f"ev-market-{sku_code}"],
            rule_version=CORE3_M07_RULE_VERSION,
            input_fingerprint=f"fp-{sku_code}",
            result_hash=f"sha256:market-{sku_code}",
        )
    )
    weekly_volume = volume / Decimal("12")
    weekly_amount = amount / Decimal("12")
    for week in range(1, 13):
        session.add(
            entities.Core3CleanMarketWeekly(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                source_table="week_sales_data",
                source_pk=f"market-week-{sku_code}-{week}",
                source_row_id=f"market-week-{sku_code}-{week}",
                source_operation_type="insert",
                sku_code=sku_code,
                model_name=model_name,
                brand_name=brand_name,
                period_raw=f"26W{week:02d}",
                period_type="week",
                period_week_index=week,
                period_parse_status="ok",
                channel_type="online",
                platform_type="test_platform",
                sales_volume=weekly_volume,
                sales_amount=weekly_amount,
                avg_price=price,
                price_check_status="ok",
                clean_record_key=f"market-week-{sku_code}-{week}",
                clean_hash=f"sha256:market-week-{sku_code}-{week}",
                clean_version="test",
                hash_version="test",
                record_status="active",
                quality_status="ok",
                quality_flags=[],
                review_required=False,
                review_status="auto_pass",
            )
        )


def seed_value_sku_claims(
    session: Session, *, sku_code: str, model_name: str, brand_name: str
) -> None:
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id=f"claim-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            raw_claim_count=3,
            matched_claim_count=3,
            fact_claim_count=3,
            unsupported_claim_count=0,
            param_unknown_claim_count=0,
            service_separate_claim_count=0,
            claim_texts_json=[],
            claim_codes=[
                "tv_claim_theater_scene",
                "tv_claim_value_price",
                "tv_claim_full_screen_design",
            ],
            fact_claim_codes=[
                "tv_claim_theater_scene",
                "tv_claim_value_price",
                "tv_claim_full_screen_design",
            ],
            unsupported_claim_codes=[],
            service_claim_codes=[],
            dimension_profile_json={},
            dimension_position_profile_json={},
            claim_summary_json={},
            evidence_ids=["ev-claim-profile"],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash=f"sha256:claim-profile-{sku_code}",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    for claim_code, claim_name in [
        ("tv_claim_theater_scene", "大屏影院"),
        ("tv_claim_value_price", "高性价比"),
        ("tv_claim_full_screen_design", "全面屏设计"),
    ]:
        session.add(
            claim_fact(sku_code, model_name, brand_name, claim_code, claim_name)
        )


def claim_fact(
    sku_code: str, model_name: str, brand_name: str, claim_code: str, claim_name: str
) -> entities.Core3SkuClaimFact:
    return entities.Core3SkuClaimFact(
        claim_fact_id=f"claim-fact-{sku_code}-{claim_code}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
        sku_code=sku_code,
        model_name=model_name,
        brand_name=brand_name,
        source_claim_key=f"seed:{claim_code}",
        raw_claim_text=claim_name,
        clean_claim_text=claim_name,
        claim_code=claim_code,
        claim_name=claim_name,
        claim_dimension="value_test",
        claim_subtype="value_test",
        claim_kind="product_experience",
        match_type="seed",
        match_score=Decimal("1.0000"),
        param_support_status="supported",
        supporting_param_codes=["screen_size_inch"],
        supporting_param_snapshot_json={},
        support_explanation="test seed",
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=[f"ev-claim-{claim_code}"],
        quality_flags=[],
        confidence=Decimal("0.9000"),
        fact_hash=f"sha256:{sku_code}:{claim_code}",
        rule_version=CORE3_M04C_TV_RULE_VERSION,
    )


def seed_value_sku_comments(
    session: Session, *, sku_code: str, model_name: str, brand_name: str
) -> None:
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id=f"comment-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            comment_sentence_count=3,
            matched_sentence_count=3,
            fact_atom_count=3,
            product_fact_sentence_count=3,
            positive_sentence_count=3,
            negative_sentence_count=0,
            dimension_summary_json={},
            signal_summary_json={},
            param_comment_support_json={},
            claim_comment_support_json={},
            polarity_summary_json={},
            evidence_examples_json=[],
            supported_param_codes=["screen_size_inch"],
            contradicted_param_codes=[],
            unmentioned_param_codes=[],
            supported_claim_codes=["tv_claim_theater_scene", "tv_claim_value_price"],
            contradicted_claim_codes=[],
            unmentioned_claim_codes=[],
            evidence_ids=["ev-comment-profile"],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash=f"sha256:comment-profile-{sku_code}",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    comments = [
        (
            "use_living_room_cinema",
            "客厅看电影大屏很震撼",
            "use_case_signal",
            "用途信号",
        ),
        (
            "appearance_size_fit",
            "75寸放客厅尺寸正好",
            "appearance_installation_space",
            "外观安装空间",
        ),
        (
            "value_price",
            "价格划算，补贴后性价比很高",
            "price_value_perception",
            "价格价值感知",
        ),
    ]
    for index, (subdimension_code, text, dimension_code, dimension_name) in enumerate(
        comments, start=1
    ):
        session.add(
            comment_fact(
                sku_code,
                model_name,
                brand_name,
                index,
                subdimension_code,
                text,
                dimension_code,
                dimension_name,
            )
        )


def comment_fact(
    sku_code: str,
    model_name: str,
    brand_name: str,
    index: int,
    subdimension_code: str,
    text: str,
    dimension_code: str,
    dimension_name: str,
) -> entities.Core3CommentFactAtom:
    return entities.Core3CommentFactAtom(
        comment_fact_id=f"comment-fact-{sku_code}-{index}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
        sku_code=sku_code,
        model_name=model_name,
        brand_name=brand_name,
        source_comment_key=f"comment-{sku_code}-{index}",
        clean_comment_text=text,
        dimension_code=dimension_code,
        dimension_name=dimension_name,
        subdimension_code=subdimension_code,
        subdimension_name=subdimension_code,
        dimension_type="product_experience"
        if not dimension_code.endswith("signal")
        else dimension_code,
        polarity="positive",
        evidence_strength="strong",
        support_relation="supports_sku_param_claim",
        support_target_type="signal",
        supported_param_codes=["screen_size_inch"]
        if subdimension_code == "appearance_size_fit"
        else [],
        contradicted_param_codes=[],
        supported_claim_codes=["tv_claim_value_price"]
        if subdimension_code == "value_price"
        else [],
        contradicted_claim_codes=[],
        param_snapshot_json={},
        claim_snapshot_json={},
        signal_payload_json={},
        extraction_payload_json={},
        evidence_ids=[f"ev-comment-{sku_code}-{index}"],
        quality_flags=[],
        confidence=Decimal("0.9000"),
        fact_hash=f"sha256:comment-{sku_code}-{index}",
        rule_version=CORE3_M05C_TV_RULE_VERSION,
    )


def seed_hisense_65e7q_battlefield_case(session: Session) -> None:
    seed_sku(
        session,
        SKU_HISENSE_65E7Q,
        "65E7Q",
        "海信",
        size=65,
        price=Decimal("5949"),
        volume=Decimal("6023"),
    )
    seed_sku(
        session,
        "TV00029113",
        "65Q9L PRO",
        "TCL",
        size=65,
        price=Decimal("5522"),
        volume=Decimal("4268"),
    )
    seed_sku(
        session,
        "TV00029114",
        "65A7H PRO",
        "创维",
        size=65,
        price=Decimal("5637"),
        volume=Decimal("5199"),
    )
    seed_hisense_65e7q_params(session)
    seed_hisense_65e7q_claims(session)
    seed_hisense_65e7q_comments(session)


def seed_hisense_65e7q_params(session: Session) -> None:
    profile = session.execute(
        select(entities.Core3SkuParamProfile).where(
            entities.Core3SkuParamProfile.sku_code == SKU_HISENSE_65E7Q
        )
    ).scalar_one()
    values = dict(profile.param_values_json or {})
    values.update(
        {
            "display_tech_class": {
                "normalized_value": "MiniLED",
                "value_presence": "present",
            },
            "mini_led_flag": {"normalized_value": True, "value_presence": "present"},
            "mini_led_type": {
                "normalized_value": "high_end",
                "value_presence": "present",
            },
            "quantum_dot_flag": {
                "normalized_value": False,
                "value_presence": "present",
            },
            "local_dimming_zone_count": {
                "normalized_value": 1920,
                "numeric_value": 1920,
                "value_presence": "present",
            },
            "color_gamut_ratio": {
                "normalized_value": 95,
                "numeric_value": 95,
                "value_presence": "present",
            },
            "processor_chip_model": {
                "normalized_value": "MT9655",
                "value_presence": "present",
            },
            "declared_refresh_rate_hz": {
                "normalized_value": 300,
                "numeric_value": 300,
                "value_presence": "present",
            },
            "hdmi_version_mix": {
                "normalized_value": "HDMI2.1",
                "value_presence": "present",
            },
            "hdmi_2_1_port_count": {
                "normalized_value": 2,
                "numeric_value": 2,
                "value_presence": "present",
            },
        }
    )
    profile.param_values_json = values
    profile.known_param_count = len(values)


def seed_hisense_65e7q_claims(session: Session) -> None:
    claim_codes = [
        "tv_claim_miniled_display",
        "tv_claim_hdr_high_brightness",
        "tv_claim_wide_color_accuracy",
        "tv_claim_local_dimming",
        "tv_claim_picture_engine_ai",
        "tv_claim_high_refresh_rate",
        "tv_claim_gaming_low_latency",
        "tv_claim_hdmi21_connectivity",
    ]
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id=f"claim-profile-{SKU_HISENSE_65E7Q}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code=SKU_HISENSE_65E7Q,
            model_name="65E7Q",
            brand_name="海信",
            raw_claim_count=len(claim_codes),
            matched_claim_count=len(claim_codes),
            fact_claim_count=len(claim_codes),
            unsupported_claim_count=0,
            param_unknown_claim_count=0,
            service_separate_claim_count=0,
            claim_texts_json=[],
            claim_codes=claim_codes,
            fact_claim_codes=claim_codes,
            unsupported_claim_codes=[],
            service_claim_codes=[],
            dimension_profile_json={},
            dimension_position_profile_json={},
            claim_summary_json={},
            evidence_ids=["ev-claim-profile-65e7q"],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash="sha256:claim-profile-65e7q",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    for claim_code in claim_codes:
        session.add(
            claim_fact(
                SKU_HISENSE_65E7Q,
                "65E7Q",
                "海信",
                claim_code,
                claim_code.replace("tv_claim_", ""),
            )
        )


def seed_hisense_65e7q_comments(session: Session) -> None:
    picture_comments = [
        ("picture_clarity_resolution", "画质清晰，细节非常好"),
        ("picture_clarity_resolution", "好高清，换掉老电视后提升明显"),
        ("picture_clarity_resolution", "屏幕清晰，看电影很舒服"),
        ("picture_clarity_resolution", "65寸画面细腻，客厅观影效果好"),
        ("picture_brightness_hdr", "亮度很高，白天客厅看也清楚"),
        ("picture_brightness_hdr", "同价位亮度高，HDR效果明显"),
        ("picture_brightness_hdr", "高亮画面有层次，暗场也稳"),
        ("picture_color_accuracy", "色彩真实，人物肤色自然"),
        ("picture_color_accuracy", "色彩鲜艳但不偏，画质满意"),
        ("picture_color_accuracy", "色彩和清晰度都符合高端预期"),
        ("picture_local_dimming_black", "控光不错，黑位表现比旧电视好"),
        ("use_living_room_cinema", "客厅看大片有影院感"),
    ]
    gaming_comments = [
        ("gaming_high_refresh_motion", "画面切换流畅"),
        ("gaming_high_refresh_motion", "高刷画面不卡顿"),
        ("use_gaming_sports", "游戏性能不错，适合接主机"),
        ("system_smooth_ads", "系统流畅不卡顿"),
    ]
    comments = picture_comments + gaming_comments
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id=f"comment-profile-{SKU_HISENSE_65E7Q}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=SKU_HISENSE_65E7Q,
            model_name="65E7Q",
            brand_name="海信",
            comment_sentence_count=len(comments),
            matched_sentence_count=len(comments),
            fact_atom_count=len(comments),
            product_fact_sentence_count=len(comments),
            positive_sentence_count=len(comments),
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
            evidence_ids=["ev-comment-profile-65e7q"],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash="sha256:comment-profile-65e7q",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    for index, (subdimension_code, text) in enumerate(comments, start=1):
        session.add(
            comment_fact(
                SKU_HISENSE_65E7Q,
                "65E7Q",
                "海信",
                index,
                subdimension_code,
                text,
                "product_experience",
                "产品体验",
            )
        )


def test_m11c_runner_generates_value_battlefield_profile_and_graph():
    session = make_session()

    result = M11CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    session.commit()

    assert result.status == Core3RunStatus.SUCCESS
    assert result.summary_json["sku_count"] == 5
    assert result.summary_json["battlefield_count"] == 13

    profile = session.execute(
        select(entities.Core3SkuValueBattlefieldProfile).where(
            entities.Core3SkuValueBattlefieldProfile.sku_code == SKU_VALUE
        )
    ).scalar_one()
    assert profile.primary_battlefield_code == "BF_LARGE_SCREEN_VALUE_UPGRADE"
    assert profile.size_tier == "xlarge_70_85"
    assert profile.price_band_in_size_tier == "low"

    score = session.execute(
        select(entities.Core3SkuValueBattlefieldScore)
        .where(entities.Core3SkuValueBattlefieldScore.sku_code == SKU_VALUE)
        .where(
            entities.Core3SkuValueBattlefieldScore.battlefield_code
            == "BF_LARGE_SCREEN_VALUE_UPGRADE"
        )
    ).scalar_one()
    assert score.relation_status == "primary_battlefield"
    assert score.market_gate_status == "matched"
    assert score.user_voice_score > Decimal("0.9000")

    graph = session.execute(
        select(entities.Core3ValueBattlefieldGraphSnapshot)
    ).scalar_one()
    assert graph.battlefield_count == 13
    assert "BF_LARGE_SCREEN_VALUE_UPGRADE" in graph.coverage_summary_json
    assert "BF_GIANT_SCREEN_VALUE_DOWNTRADE" in graph.coverage_summary_json


def test_m11c_prefers_premium_picture_when_comment_evidence_is_stronger_than_gaming():
    session = make_session()
    seed_hisense_65e7q_battlefield_case(session)

    result = M11CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        target_sku_codes=[SKU_HISENSE_65E7Q],
        force_rebuild=True,
    )
    session.commit()

    assert result.status == Core3RunStatus.SUCCESS
    profile = session.execute(
        select(entities.Core3SkuValueBattlefieldProfile).where(
            entities.Core3SkuValueBattlefieldProfile.sku_code == SKU_HISENSE_65E7Q
        )
    ).scalar_one()
    assert profile.size_tier == "large_60_69"
    assert profile.price_band_in_size_tier == "high"
    assert profile.primary_battlefield_code == "BF_PREMIUM_PICTURE_UPGRADE"
    assert "BF_GAMING_SPORTS_FLUENCY" in profile.secondary_battlefield_codes_json

    scores = {
        row.battlefield_code: row
        for row in session.execute(
            select(entities.Core3SkuValueBattlefieldScore).where(
                entities.Core3SkuValueBattlefieldScore.sku_code == SKU_HISENSE_65E7Q
            )
        ).scalars()
    }
    picture = scores["BF_PREMIUM_PICTURE_UPGRADE"]
    gaming = scores["BF_GAMING_SPORTS_FLUENCY"]
    assert picture.relation_status == "primary_battlefield"
    assert gaming.relation_status == "secondary_battlefield"
    assert picture.user_voice_score > gaming.user_voice_score
    assert picture.task_group_fit_score == Decimal("0.8000")
    assert (
        picture.score_breakdown_json["user_voice"]["relative_comment_intensity_score"]
        > gaming.score_breakdown_json["user_voice"]["relative_comment_intensity_score"]
    )


def test_m11c_splits_giant_value_downtrade_from_flagship():
    session = make_session()

    result = M11CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    session.commit()

    assert result.status == Core3RunStatus.SUCCESS
    profile = session.execute(
        select(entities.Core3SkuValueBattlefieldProfile).where(
            entities.Core3SkuValueBattlefieldProfile.sku_code == SKU_GIANT_VALUE
        )
    ).scalar_one()
    assert profile.size_tier == "giant_98_plus"
    assert profile.price_band_in_size_tier == "low"
    assert profile.primary_battlefield_code == "BF_GIANT_SCREEN_VALUE_DOWNTRADE"

    downtrade_score = session.execute(
        select(entities.Core3SkuValueBattlefieldScore)
        .where(entities.Core3SkuValueBattlefieldScore.sku_code == SKU_GIANT_VALUE)
        .where(
            entities.Core3SkuValueBattlefieldScore.battlefield_code
            == "BF_GIANT_SCREEN_VALUE_DOWNTRADE"
        )
    ).scalar_one()
    flagship_score = session.execute(
        select(entities.Core3SkuValueBattlefieldScore)
        .where(entities.Core3SkuValueBattlefieldScore.sku_code == SKU_GIANT_VALUE)
        .where(
            entities.Core3SkuValueBattlefieldScore.battlefield_code
            == "BF_GIANT_HOME_THEATER_FLAGSHIP"
        )
    ).scalar_one()

    assert downtrade_score.relation_status == "primary_battlefield"
    assert downtrade_score.market_gate_status == "matched"
    assert flagship_score.relation_status == "excluded"


def test_m11c_pipeline_and_insight_cli_query_value_battlefields():
    session = make_session()

    pipeline_result = catforge_pipeline.run_value_battlefield(
        session,
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    assert pipeline_result["status"] == "ok"
    assert pipeline_result["summary"]["profile_count"] == 5

    current_profile = session.execute(
        select(entities.Core3SkuValueBattlefieldProfile).where(
            entities.Core3SkuValueBattlefieldProfile.sku_code == SKU_VALUE,
            entities.Core3SkuValueBattlefieldProfile.taxonomy_version
            == CORE3_M11C_TV_TAXONOMY_VERSION,
        )
    ).scalar_one()
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id="legacy-taxonomy-profile",
            project_id=current_profile.project_id,
            category_code=current_profile.category_code,
            batch_id=current_profile.batch_id,
            product_category=current_profile.product_category,
            taxonomy_version="m11c_tv_value_battlefield_taxonomy_legacy",
            rule_version=current_profile.rule_version,
            sku_code=current_profile.sku_code,
            model_name=current_profile.model_name,
            brand_name=current_profile.brand_name,
            size_tier=current_profile.size_tier,
            price_band_in_size_tier=current_profile.price_band_in_size_tier,
            price_percentile_in_size_tier=current_profile.price_percentile_in_size_tier,
            primary_battlefield_code=current_profile.primary_battlefield_code,
            primary_relation_status=current_profile.primary_relation_status,
            secondary_battlefield_codes_json=current_profile.secondary_battlefield_codes_json,
            opportunity_battlefield_codes_json=current_profile.opportunity_battlefield_codes_json,
            drag_factor_battlefield_codes_json=current_profile.drag_factor_battlefield_codes_json,
            battlefield_summary_json=current_profile.battlefield_summary_json,
            review_required=current_profile.review_required,
            review_status=current_profile.review_status,
            review_reason_json=current_profile.review_reason_json,
            confidence=current_profile.confidence,
            evidence_ids_json=current_profile.evidence_ids_json,
            profile_hash="sha256:legacy-taxonomy-profile",
            is_current=True,
        )
    )
    session.commit()

    sku_profile = catforge_insight.query_sku_value_battlefield(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="75X-Value",
        include_scores=True,
    )
    coverage = catforge_insight.query_value_battlefield_skus(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        battlefield_code="BF_LARGE_SCREEN_VALUE_UPGRADE",
        relation_status="primary_battlefield",
        sku_limit=10,
    )
    natural = catforge_insight.answer_natural_language(
        session,
        question="查 75X-Value 的价值战场",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    taxonomy = catforge_insight.query_value_battlefield_taxonomy(product_category="TV")

    assert sku_profile["status"] == "ok"
    assert sku_profile["primary_battlefield_code"] == "BF_LARGE_SCREEN_VALUE_UPGRADE"
    assert any(
        item["battlefield_code"] == "BF_LARGE_SCREEN_VALUE_UPGRADE"
        for item in sku_profile["scores"]
    )
    assert coverage["sku_codes"] == [SKU_VALUE]
    assert natural["routed_command"] == "sku-value-battlefield"
    assert natural["primary_battlefield_code"] == "BF_LARGE_SCREEN_VALUE_UPGRADE"
    assert taxonomy["battlefield_count"] == 13
    assert taxonomy["taxonomy_version"] == CORE3_M11C_TV_TAXONOMY_VERSION
    assert any(
        item["battlefield_code"] == "BF_GIANT_SCREEN_VALUE_DOWNTRADE"
        for item in taxonomy["battlefields"]
    )


def test_comparable_market_validation_uses_overlap_week_average_not_cumulative_sales() -> (
    None
):
    legacy_sku = "TV000LEGACY"
    new_sku = "TV000NEW"
    peer_sku = "TV000PEER"
    base_inputs = [
        (_param_profile_for_small_sku(legacy_sku), "small_32_45"),
        (_param_profile_for_small_sku(new_sku), "small_32_45"),
        (_param_profile_for_small_sku(peer_sku), "small_32_45"),
    ]
    weekly_rows = [
        *_weekly_rows(
            legacy_sku,
            start=1,
            end=13,
            weekly_volume=Decimal("100"),
            price=Decimal("1500"),
        ),
        *_weekly_rows(
            legacy_sku,
            start=14,
            end=24,
            weekly_volume=Decimal("50"),
            price=Decimal("1500"),
        ),
        *_weekly_rows(
            new_sku,
            start=14,
            end=24,
            weekly_volume=Decimal("150"),
            price=Decimal("1400"),
        ),
        *_weekly_rows(
            peer_sku,
            start=14,
            end=24,
            weekly_volume=Decimal("100"),
            price=Decimal("1300"),
        ),
    ]

    contexts = _derive_comparable_market_contexts(base_inputs, weekly_rows)

    assert (
        contexts[legacy_sku]["target_sales_volume_total_display_only"]
        > contexts[new_sku]["target_sales_volume_total_display_only"]
    )
    assert contexts[legacy_sku]["comparable_volume_percentile"] == 0.0
    assert contexts[new_sku]["comparable_volume_percentile"] == 1.0
    assert _market_validation_score(
        _market_profile_with_legacy_cumulative_rank(), contexts[new_sku]
    ) > _market_validation_score(
        _market_profile_with_legacy_cumulative_rank(),
        contexts[legacy_sku],
    )


def _param_profile_for_small_sku(sku_code: str) -> entities.Core3SkuParamProfile:
    return entities.Core3SkuParamProfile(
        sku_code=sku_code,
        param_values_json={"dimension_tier_profile": {"size": "small_32_45"}},
    )


def _weekly_rows(
    sku_code: str,
    *,
    start: int,
    end: int,
    weekly_volume: Decimal,
    price: Decimal,
) -> list[entities.Core3CleanMarketWeekly]:
    return [
        entities.Core3CleanMarketWeekly(
            sku_code=sku_code,
            period_week_index=week,
            sales_volume=weekly_volume,
            sales_amount=weekly_volume * price,
            record_status="active",
            quality_status="ok",
        )
        for week in range(start, end + 1)
    ]


def _market_profile_with_legacy_cumulative_rank() -> entities.Core3SkuMarketProfile:
    return entities.Core3SkuMarketProfile(
        sales_volume_total=Decimal("9999"),
        sales_amount_total=Decimal("9999999"),
        volume_percentile_in_size=Decimal("1.000000"),
        amount_percentile_in_size=Decimal("1.000000"),
        sample_status="sufficient",
    )
