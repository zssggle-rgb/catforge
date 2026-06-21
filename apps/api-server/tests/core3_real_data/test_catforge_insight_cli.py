from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_insight
from app.models import entities
from app.services.core3_real_data.constants import CORE3_M03B_AC_RULE_VERSION, CORE3_M03B_AC_TAXONOMY_VERSION, CORE3_M03B_RULE_VERSION, CORE3_M07_RULE_VERSION


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_test"


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
        entities.Core3SkuParamDimensionTier.__table__,
        entities.Core3ParamTierCoverage.__table__,
        entities.Core3SkuMarketProfile.__table__,
        entities.Core3MarketSignal.__table__,
        entities.Core3ComparablePoolBaseline.__table__,
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
            source_tables=["attribute_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            status="registered",
        )
    )
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="profile_tv_100a4f",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="TV00027354",
            model_name="100A4F",
            param_values_json={
                "screen_size_inch": {"normalized_value": 100},
                "display_tech_class": {"normalized_value": "miniled"},
                "dimension_tier_profile": {"size": "giant_98_plus", "display_tech": "miniled"},
            },
            core_picture_params_json={"screen_size_inch": {"normalized_value": 100}},
            core_gaming_params_json={},
            core_system_params_json={},
            core_eye_care_params_json={},
            param_completeness=Decimal("0.820000"),
            known_param_count=41,
            unknown_param_count=9,
            conflict_count=1,
            review_required_count=1,
            evidence_ids=["ev_size", "ev_miniled"],
            quality_summary_json={"review": "param_conflict"},
            profile_hash="sha256:test-profile",
            seed_version="tv_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="profile_ac_kfr35",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="AC00000001",
            model_name="KFR-35GW",
            param_values_json={
                "horsepower_hp": {"normalized_value": 1.5},
                "fresh_air_flag": {"normalized_value": True},
                "dimension_tier_profile": {"horsepower": "hp_1_5", "health": "health_fresh_air"},
            },
            core_picture_params_json={"horsepower_hp": {"normalized_value": 1.5}},
            core_gaming_params_json={},
            core_system_params_json={"fresh_air_flag": {"normalized_value": True}},
            core_eye_care_params_json={},
            param_completeness=Decimal("0.760000"),
            known_param_count=25,
            unknown_param_count=3,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=["ev_ac_hp", "ev_ac_fresh"],
            quality_summary_json={"taxonomy_category_code": "AC"},
            profile_hash="sha256:test-ac-profile",
            seed_version=CORE3_M03B_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M03B_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuParamDimensionTier(
            dimension_tier_id="tier_tv_100a4f_display",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version="tv_param_taxonomy_manual_v0.1",
            sku_code="TV00027354",
            model_name="100A4F",
            dimension_code="display_tech",
            tier_code="miniled",
            tier_name="MiniLED",
            tier_rank=30,
            basis_param_codes=["display_tech_class"],
            basis_values_json={"display_tech_class": "miniled"},
            rule_snapshot_json={},
            explanation="LCD + MiniLED 背光。",
            evidence_ids=["ev_miniled"],
            confidence=Decimal("1.0000"),
            quality_flags=[],
            profile_hash="sha256:test-tier-display",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuParamDimensionTier(
            dimension_tier_id="tier_tv_100a4f_size",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version="tv_param_taxonomy_manual_v0.1",
            sku_code="TV00027354",
            model_name="100A4F",
            dimension_code="size",
            tier_code="giant_98_plus",
            tier_name="巨幕 98+",
            tier_rank=60,
            basis_param_codes=["screen_size_inch"],
            basis_values_json={"screen_size_inch": 100},
            rule_snapshot_json={},
            explanation=">=98 英寸。",
            evidence_ids=["ev_size"],
            confidence=Decimal("1.0000"),
            quality_flags=[],
            profile_hash="sha256:test-tier-size",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3ParamTierCoverage(
            tier_coverage_id="coverage_display_miniled",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version="tv_param_taxonomy_manual_v0.1",
            dimension_code="display_tech",
            tier_code="miniled",
            tier_name="MiniLED",
            tier_rank=30,
            rule_summary="LCD + MiniLED 背光",
            sku_count=2,
            sku_ratio=Decimal("0.200000"),
            sku_codes=["TV00027354", "TV00029204"],
            sample_sku_codes=["TV00027354", "TV00029204"],
            coverage_status="covered",
            coverage_hash="sha256:test-coverage-miniled",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3ParamTierCoverage(
            tier_coverage_id="coverage_display_lcd_led",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version="tv_param_taxonomy_manual_v0.1",
            dimension_code="display_tech",
            tier_code="lcd_led",
            tier_name="LCD/LED",
            tier_rank=10,
            rule_summary="LCD + LED 背光，非 MiniLED",
            sku_count=1,
            sku_ratio=Decimal("0.100000"),
            sku_codes=["TV00010000"],
            sample_sku_codes=["TV00010000"],
            coverage_status="covered",
            coverage_hash="sha256:test-coverage-lcd-led",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3ParamTierCoverage(
            tier_coverage_id="coverage_picture_premium",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version="tv_param_taxonomy_manual_v0.1",
            dimension_code="picture_overall",
            tier_code="picture_premium",
            tier_name="高端画质",
            tier_rank=40,
            rule_summary="MiniLED/QD/RGB MiniLED，且亮度或分区有明显支撑",
            sku_count=1,
            sku_ratio=Decimal("0.100000"),
            sku_codes=["TV00027354"],
            sample_sku_codes=["TV00027354"],
            coverage_status="covered",
            coverage_hash="sha256:test-coverage-picture-premium",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuParamDimensionTier(
            dimension_tier_id="tier_ac_kfr35_health",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version=CORE3_M03B_AC_TAXONOMY_VERSION,
            sku_code="AC00000001",
            model_name="KFR-35GW",
            dimension_code="health",
            tier_code="health_fresh_air",
            tier_name="新风能力",
            tier_rank=20,
            basis_param_codes=["fresh_air_flag", "purification_flag"],
            basis_values_json={"fresh_air_flag": True},
            rule_snapshot_json={},
            explanation="具备新风。",
            evidence_ids=["ev_ac_fresh"],
            confidence=Decimal("1.0000"),
            quality_flags=[],
            profile_hash="sha256:test-ac-tier-health",
            rule_version=CORE3_M03B_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3ParamTierCoverage(
            tier_coverage_id="coverage_ac_health_fresh_air",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            taxonomy_version=CORE3_M03B_AC_TAXONOMY_VERSION,
            dimension_code="health",
            tier_code="health_fresh_air",
            tier_name="新风能力",
            tier_rank=20,
            rule_summary="具备新风",
            sku_count=1,
            sku_ratio=Decimal("0.006452"),
            sku_codes=["AC00000001"],
            sample_sku_codes=["AC00000001"],
            coverage_status="insufficient_sample",
            coverage_hash="sha256:test-ac-coverage-health",
            rule_version=CORE3_M03B_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuMarketProfile(
            sku_market_profile_id="m07_profile_tv_100a4f",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="TV00027354",
            model_name="100A4F",
            analysis_window="full_observed_window",
            period_start_raw="26W01",
            period_end_raw="26W23",
            active_week_count=10,
            market_row_count=20,
            platform_count=2,
            screen_size_inch=Decimal("100"),
            size_segment="100",
            screen_size_class="ultra_large_flagship",
            market_pool_key="tv:ultra_large_flagship:线上:full_observed_window",
            size_param_confidence=Decimal("0.9500"),
            sales_volume_total=Decimal("80"),
            sales_amount_total=Decimal("559920"),
            price_wavg=Decimal("6999"),
            price_latest=6999,
            price_median=Decimal("6999"),
            price_min=Decimal("6799"),
            price_max=Decimal("7199"),
            price_per_inch=Decimal("69.990000"),
            main_channel_type="线上",
            main_platform="专业电商",
            platform_share_json={"专业电商": {"volume_share": 1.0, "amount_share": 1.0}},
            price_band_category="high",
            price_band_size="mid_high",
            price_percentile_in_category=Decimal("1.000000"),
            volume_percentile_in_category=Decimal("1.000000"),
            amount_percentile_in_category=Decimal("1.000000"),
            price_percentile_in_size=Decimal("1.000000"),
            volume_percentile_in_size=Decimal("1.000000"),
            amount_percentile_in_size=Decimal("1.000000"),
            same_pool_volume_percentile=Decimal("1.000000"),
            same_pool_sku_count=2,
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=["ev_market_100a4f"],
            market_evidence_ids=["ev_market_100a4f"],
            param_evidence_ids=["ev_size"],
            input_fingerprint="sha256:m07-input-100a4f",
            result_hash="sha256:m07-profile-100a4f",
            rule_version=CORE3_M07_RULE_VERSION,
            price_band_rule_version="m07_price_band_v1",
        )
    )
    session.add(
        entities.Core3SkuMarketProfile(
            sku_market_profile_id="m07_profile_tv_85",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="TV00029115",
            model_name="85E7Q",
            analysis_window="full_observed_window",
            active_week_count=8,
            market_row_count=16,
            platform_count=1,
            screen_size_inch=Decimal("85"),
            size_segment="85",
            screen_size_class="large_upgrade",
            market_pool_key="tv:large_upgrade:线上:full_observed_window",
            size_param_confidence=Decimal("0.9500"),
            sales_volume_total=Decimal("40"),
            sales_amount_total=Decimal("239960"),
            price_wavg=Decimal("5999"),
            price_latest=5999,
            price_band_category="mid_high",
            price_band_size="mid",
            volume_percentile_in_category=Decimal("0.500000"),
            volume_percentile_in_size=Decimal("1.000000"),
            same_pool_volume_percentile=Decimal("1.000000"),
            same_pool_sku_count=1,
            market_confidence=Decimal("0.8000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=["ev_market_85"],
            input_fingerprint="sha256:m07-input-85",
            result_hash="sha256:m07-profile-85",
            rule_version=CORE3_M07_RULE_VERSION,
            price_band_rule_version="m07_price_band_v1",
        )
    )
    session.add(
        entities.Core3MarketSignal(
            market_signal_id="m07_signal_100a4f_volume",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_market_profile_id="m07_profile_tv_100a4f",
            sku_code="TV00027354",
            model_name="100A4F",
            signal_key="m07:TV00027354:full_observed_window:SALES_VOLUME_STRONG",
            analysis_window="full_observed_window",
            signal_code="SALES_VOLUME_STRONG",
            signal_name="销量强",
            signal_value=Decimal("1.000000"),
            signal_strength=Decimal("1.0000"),
            signal_level="strong",
            basis_metric="volume_percentile_in_category",
            basis_value_json={"volume_percentile_in_category": 1.0},
            comparison_scope="category",
            polarity="positive",
            confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            quality_flags=[],
            evidence_ids=["ev_market_100a4f"],
            input_fingerprint="sha256:m07-signal-input",
            result_hash="sha256:m07-signal-100a4f",
            rule_version=CORE3_M07_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3ComparablePoolBaseline(
            pool_id="m07_pool_100a4f_same_price",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            pool_key="m07:TV00027354:full_observed_window:same_price_band",
            target_sku_code="TV00027354",
            target_model_name="100A4F",
            analysis_window="full_observed_window",
            pool_type="same_price_band",
            pool_condition_json={"target_price_band": "high"},
            candidate_sku_codes=["TV00027354", "TV00029115"],
            pool_sku_count=2,
            valid_member_count=2,
            target_included=True,
            target_size_segment="100",
            target_price_band="high",
            median_price=Decimal("6499"),
            median_volume=Decimal("60"),
            median_amount=Decimal("399940"),
            price_distribution_json={},
            volume_distribution_json={},
            amount_distribution_json={},
            platform_distribution_json={},
            pool_confidence=Decimal("0.7000"),
            sample_status="insufficient",
            basis="同价格带市场比较。",
            quality_flags=["pool_insufficient"],
            evidence_ids=["ev_market_100a4f", "ev_market_85"],
            input_fingerprint="sha256:m07-pool-input",
            result_hash="sha256:m07-pool-100a4f",
            rule_version=CORE3_M07_RULE_VERSION,
            pool_rule_version="m07_pool_v1",
        )
    )
    session.commit()


def test_query_sku_param_profile_by_model_name():
    session = make_session()

    result = catforge_insight.query_sku_param_profile(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="100A4F",
    )

    assert result["status"] == "ok"
    assert result["batch_id"] == BATCH_ID
    assert result["sku"] == {"sku_code": "TV00027354", "model_name": "100A4F"}
    assert result["dimension_tier_profile"]["display_tech"] == "miniled"
    assert result["summary"]["known_param_count"] == 41


def test_query_tv_param_taxonomy_exposes_standard_params_and_raw_mapping():
    result = catforge_insight.query_tv_param_taxonomy(group="picture", search="MINILED")

    assert result["status"] == "ok"
    assert result["taxonomy_version"] == "tv_param_taxonomy_manual_v0.1"
    assert any(item["param_code"] == "mini_led_type" for item in result["params"])
    assert "MINILED2" in result["raw_field_mapping"]


def test_tier_coverage_and_natural_language_route_to_matching_skus():
    session = make_session()

    direct = catforge_insight.query_tier_coverage(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="MiniLED 档位覆盖 SKU",
        sku_limit=1,
    )
    natural = catforge_insight.answer_natural_language(
        session,
        question="查 MiniLED 档位覆盖哪些 SKU",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=1,
    )

    assert direct["status"] == "ok"
    assert direct["coverage_count"] == 1
    assert direct["coverages"][0]["sku_codes"] == ["TV00027354"]
    assert direct["coverages"][0]["sku_codes_truncated"] is True
    assert {item["tier_code"] for item in direct["coverages"]} == {"miniled"}
    assert natural["routed_command"] == "tier-coverage"
    assert natural["coverages"][0]["tier_code"] == "miniled"


def test_ac_taxonomy_profile_and_tier_queries_are_routed_by_natural_language():
    session = make_session()

    taxonomy = catforge_insight.answer_natural_language(
        session,
        question="查空调标准参数",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    profile = catforge_insight.answer_natural_language(
        session,
        question="查 AC00000001 的参数画像",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    coverage = catforge_insight.answer_natural_language(
        session,
        question="查空调新风档位覆盖哪些 SKU",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )

    assert taxonomy["category_code"] == "AC"
    assert taxonomy["taxonomy_version"] == CORE3_M03B_AC_TAXONOMY_VERSION
    assert any(item["param_code"] == "fresh_air_flag" for item in taxonomy["params"])
    assert profile["status"] == "ok"
    assert profile["product_category"] == "AC"
    assert profile["sku"]["sku_code"] == "AC00000001"
    assert profile["dimension_tier_profile"]["health"] == "health_fresh_air"
    assert coverage["product_category"] == "AC"
    assert coverage["coverages"][0]["sku_codes"] == ["AC00000001"]


def test_positive_ac_tier_query_does_not_match_negative_tier():
    taxonomy = catforge_insight.query_param_taxonomy(product_category="AC")
    tiers = [
        catforge_insight.M03BTierDefinition(
            dimension_code=item["dimension_code"],
            tier_code=item["tier_code"],
            tier_name=item["tier_name"],
            tier_rank=item["tier_rank"],
            rule_summary=item["rule_summary"],
        )
        for item in taxonomy["dimension_tiers"]
    ]

    matches = catforge_insight.resolve_tiers(tiers, dimension="health", tier=None, query="查空调新风档位覆盖哪些 SKU")

    assert {item.tier_code for item in matches} == {"health_fresh_air", "health_fresh_purification"}


def test_market_profile_bucket_and_pool_queries_are_routed_by_natural_language():
    session = make_session()

    profile = catforge_insight.answer_natural_language(
        session,
        question="查 100A4F 的市场画像",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    bucket = catforge_insight.answer_natural_language(
        session,
        question="查高价格带覆盖哪些 SKU",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    pools = catforge_insight.answer_natural_language(
        session,
        question="查 100A4F 的可比池",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )

    assert profile["routed_command"] == "sku-market-profile"
    assert profile["sku"]["sku_code"] == "TV00027354"
    assert profile["market_metrics"]["sales_volume_total"] == 80.0
    assert profile["business_bucket_position"]["price_bucket_code"] == "high"

    assert bucket["routed_command"] == "market-bucket-coverage"
    assert bucket["coverage_count"] >= 1
    assert any("TV00027354" in item["sku_codes"] for item in bucket["coverages"])

    assert pools["routed_command"] == "comparable-pools"
    assert pools["pool_count"] == 1
    assert pools["pools"][0]["pool_type"] == "same_price_band"


def test_cli_main_can_emit_json_for_natural_language(monkeypatch, capsys):
    session = make_session()

    class SessionFactory:
        def __call__(self):
            return session

    monkeypatch.setattr(catforge_insight, "SessionLocal", SessionFactory())

    exit_code = catforge_insight.main(
        [
            "ask",
            "查",
            "100A4F",
            "的参数画像",
            "--project-id",
            PROJECT_ID,
            "--category-code",
            "TV",
            "--batch-id",
            "latest",
            "--format",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"routed_command": "sku-param-profile"' in captured.out
    assert '"sku_code": "TV00027354"' in captured.out
