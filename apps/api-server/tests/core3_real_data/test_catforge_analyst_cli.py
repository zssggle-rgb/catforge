from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_analyst
from app.models import entities
from app.services.core3_real_data.constants import CORE3_M07_PRICE_BAND_RULE_VERSION, CORE3_M07_RULE_VERSION


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
        entities.Core3SkuMarketProfile.__table__,
        entities.Core3SkuParamProfile.__table__,
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
