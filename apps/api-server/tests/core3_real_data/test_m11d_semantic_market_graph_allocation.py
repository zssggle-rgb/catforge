from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_insight, catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import (
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
    Core3SourceBatchStatus,
)


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606220011"
SKU_STRONG = "TV00099001"
SKU_NO_TASK = "TV00099002"


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
        entities.Core3SkuCommentFactProfile.__table__,
        entities.Core3M09cSkuUserTaskProfile.__table__,
        entities.Core3M09cSkuUserTaskScore.__table__,
        entities.Core3M10cSkuTargetGroupProfile.__table__,
        entities.Core3M10cSkuTargetGroupScore.__table__,
        entities.Core3SkuValueBattlefieldProfile.__table__,
        entities.Core3SkuValueBattlefieldScore.__table__,
        entities.Core3SemanticMarketAllocation.__table__,
        entities.Core3SemanticMarketDimensionSummary.__table__,
        entities.Core3SemanticMarketSkuContribution.__table__,
        entities.Core3SemanticMarketGraphSnapshot.__table__,
        entities.Core3SemanticMarketReconciliationCheck.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)
    session = Session(engine)
    seed_foundation(session)
    return session


def seed_foundation(session: Session) -> None:
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
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    seed_market(session, SKU_STRONG, "75A-Pro", "海信", size=75, price=Decimal("3999"), volume=Decimal("1200"), price_band="mid")
    seed_market(session, SKU_NO_TASK, "65B-Quiet", "TCL", size=65, price=Decimal("2999"), volume=Decimal("600"), price_band="mid_low")
    seed_comment_profile(session, SKU_STRONG, "75A-Pro", "海信")
    seed_comment_profile(session, SKU_NO_TASK, "65B-Quiet", "TCL")
    seed_user_task_outputs(session, SKU_STRONG, "75A-Pro", "海信", has_primary=True)
    seed_user_task_outputs(session, SKU_NO_TASK, "65B-Quiet", "TCL", has_primary=False)
    seed_target_group_outputs(session, SKU_STRONG, "75A-Pro", "海信", primary_code="TG_LARGE_SCREEN_UPGRADER", secondary_code="TG_VALUE_MAXIMIZER")
    seed_target_group_outputs(session, SKU_NO_TASK, "65B-Quiet", "TCL", primary_code="TG_MAINSTREAM_FAMILY_VIEWER", secondary_code=None)
    seed_battlefield_outputs(
        session,
        SKU_STRONG,
        "75A-Pro",
        "海信",
        primary_code="BF_LARGE_SCREEN_VALUE_UPGRADE",
        secondary_code="BF_LARGE_SCREEN_FAMILY_CINEMA",
        size_tier="xlarge_70_85",
        price_band="mid",
    )
    seed_battlefield_outputs(
        session,
        SKU_NO_TASK,
        "65B-Quiet",
        "TCL",
        primary_code="BF_MAINSTREAM_LIVING_BALANCE",
        secondary_code=None,
        size_tier="large_60_69",
        price_band="mid_low",
    )
    seed_stale_current_battlefield_outputs(session)
    session.commit()


def seed_market(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    *,
    size: int,
    price: Decimal,
    volume: Decimal,
    price_band: str,
) -> None:
    amount = price * volume
    size_tier = "large_60_69" if size <= 69 else "xlarge_70_85"
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
            price_percentile_in_size=Decimal("0.520000"),
            volume_percentile_in_size=Decimal("0.800000") if sku_code == SKU_STRONG else Decimal("0.450000"),
            amount_percentile_in_size=Decimal("0.750000") if sku_code == SKU_STRONG else Decimal("0.420000"),
            same_pool_sku_count=4,
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


def seed_comment_profile(session: Session, sku_code: str, model_name: str, brand_name: str) -> None:
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id=f"m05c-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            comment_sentence_count=8,
            matched_sentence_count=8,
            fact_atom_count=8,
            product_fact_sentence_count=8,
            positive_sentence_count=6,
            negative_sentence_count=1,
            neutral_sentence_count=1,
            dimension_summary_json={"use_case": {"positive": 4}},
            signal_summary_json={"task": ["living_room", "value"]},
            evidence_ids=[f"ev-comment-{sku_code}"],
            confidence=Decimal("0.9000"),
            profile_hash=f"hash-m05c-{sku_code}",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )


def seed_user_task_outputs(session: Session, sku_code: str, model_name: str, brand_name: str, *, has_primary: bool) -> None:
    size_tier = "xlarge_70_85" if sku_code == SKU_STRONG else "large_60_69"
    price_band = "mid" if sku_code == SKU_STRONG else "mid_low"
    primary_code = "TASK_LARGE_SCREEN_UPGRADE" if has_primary else None
    secondary_codes = ["TASK_CINEMA_IMMERSION"] if has_primary else []
    brand_claimed_codes = [] if has_primary else ["TASK_SMART_CASTING_IOT"]
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id=f"m09c-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band_in_size_tier=price_band,
            price_percentile_in_size_tier=Decimal("0.520000"),
            primary_user_task_code=primary_code,
            primary_relation_status="primary_user_task" if has_primary else None,
            secondary_user_task_codes_json=secondary_codes,
            comment_observed_task_codes_json=["TASK_VALUE_FOR_MONEY_PURCHASE"] if has_primary else [],
            brand_claimed_task_codes_json=brand_claimed_codes,
            latent_capability_task_codes_json=[],
            drag_factor_task_codes_json=[],
            user_task_summary_json={"fixture": True},
            no_primary_reason=None if has_primary else "只有厂家表达，评论证据不足。",
            confidence=Decimal("0.9000"),
            evidence_ids_json=[f"ev-m09c-profile-{sku_code}"],
            profile_hash=f"hash-m09c-profile-{sku_code}",
        )
    )
    if has_primary:
        seed_user_task_score(session, sku_code, model_name, brand_name, "TASK_LARGE_SCREEN_UPGRADE", "大屏换新升级", "primary_user_task", Decimal("0.9200"))
        seed_user_task_score(session, sku_code, model_name, brand_name, "TASK_CINEMA_IMMERSION", "影院沉浸观影", "secondary_user_task", Decimal("0.7800"))
        seed_user_task_score(session, sku_code, model_name, brand_name, "TASK_VALUE_FOR_MONEY_PURCHASE", "预算内高性价比购买", "comment_observed_task", Decimal("0.6600"))
    else:
        seed_user_task_score(session, sku_code, model_name, brand_name, "TASK_SMART_CASTING_IOT", "投屏互联与智能控制", "brand_claimed_task", Decimal("0.7000"))


def seed_user_task_score(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    task_code: str,
    task_name: str,
    relation_status: str,
    score: Decimal,
) -> None:
    size_tier = "xlarge_70_85" if sku_code == SKU_STRONG else "large_60_69"
    price_band = "mid" if sku_code == SKU_STRONG else "mid_low"
    is_observed = relation_status == "comment_observed_task"
    session.add(
        entities.Core3M09cSkuUserTaskScore(
            score_id=f"m09c-score-{sku_code}-{task_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            user_task_code=task_code,
            user_task_name=task_name,
            user_task_definition=f"{task_name} definition",
            relation_status=relation_status,
            user_task_score=score,
            comment_task_need_score=Decimal("0.7200") if relation_status in {"primary_user_task", "secondary_user_task"} or is_observed else Decimal("0.0500"),
            claim_task_alignment_score=Decimal("0.8000"),
            param_capability_score=Decimal("0.7600"),
            size_price_fit_score=Decimal("0.8200"),
            market_validation_score=Decimal("0.7000"),
            negative_drag_score=Decimal("0.0000"),
            sentiment_polarity="positive",
            size_tier=size_tier,
            price_band_in_size_tier=price_band,
            price_percentile_in_size_tier=Decimal("0.520000"),
            score_breakdown_json={"fixture": True},
            status_reason_cn="fixture",
            evidence_ids_json=[f"ev-m09c-score-{sku_code}-{task_code}"],
            confidence=Decimal("0.8800"),
            result_hash=f"hash-m09c-score-{sku_code}-{task_code}",
        )
    )


def seed_target_group_outputs(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    *,
    primary_code: str,
    secondary_code: str | None,
) -> None:
    size_tier = "xlarge_70_85" if sku_code == SKU_STRONG else "large_60_69"
    price_band = "mid" if sku_code == SKU_STRONG else "mid_low"
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id=f"m10c-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band_in_size_tier=price_band,
            price_percentile_in_size_tier=Decimal("0.520000"),
            primary_target_group_code=primary_code,
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=[secondary_code] if secondary_code else [],
            comment_observed_group_codes_json=[],
            brand_claimed_group_codes_json=[],
            latent_group_codes_json=[],
            unmet_group_need_codes_json=[],
            target_group_summary_json={"fixture": True},
            confidence=Decimal("0.8800"),
            evidence_ids_json=[f"ev-m10c-profile-{sku_code}"],
            profile_hash=f"hash-m10c-profile-{sku_code}",
        )
    )
    seed_target_group_score(session, sku_code, model_name, brand_name, primary_code, "主目标客群", "primary_target_group", Decimal("0.9000"))
    if secondary_code:
        seed_target_group_score(session, sku_code, model_name, brand_name, secondary_code, "辅目标客群", "secondary_target_group", Decimal("0.7600"))


def seed_target_group_score(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    group_code: str,
    group_name: str,
    relation_status: str,
    score: Decimal,
) -> None:
    size_tier = "xlarge_70_85" if sku_code == SKU_STRONG else "large_60_69"
    price_band = "mid" if sku_code == SKU_STRONG else "mid_low"
    session.add(
        entities.Core3M10cSkuTargetGroupScore(
            score_id=f"m10c-score-{sku_code}-{group_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            target_group_code=group_code,
            target_group_name=group_name,
            target_group_definition=f"{group_name} definition",
            relation_status=relation_status,
            target_group_score=score,
            comment_audience_motivation_score=Decimal("0.7400"),
            task_support_score=Decimal("0.8200"),
            size_price_fit_score=Decimal("0.7800"),
            claim_alignment_score=Decimal("0.7400"),
            param_capability_score=Decimal("0.7200"),
            market_validation_score=Decimal("0.6800"),
            brand_trust_boost=Decimal("0.1200"),
            sentiment_polarity="positive",
            size_tier=size_tier,
            price_band_in_size_tier=price_band,
            price_percentile_in_size_tier=Decimal("0.520000"),
            score_breakdown_json={"fixture": True},
            status_reason_cn="fixture",
            evidence_ids_json=[f"ev-m10c-score-{sku_code}-{group_code}"],
            confidence=Decimal("0.8600"),
            result_hash=f"hash-m10c-score-{sku_code}-{group_code}",
        )
    )


def seed_battlefield_outputs(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    *,
    primary_code: str,
    secondary_code: str | None,
    size_tier: str,
    price_band: str,
) -> None:
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id=f"m11c-profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            size_tier=size_tier,
            price_band_in_size_tier=price_band,
            price_percentile_in_size_tier=Decimal("0.520000"),
            primary_battlefield_code=primary_code,
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=[secondary_code] if secondary_code else [],
            opportunity_battlefield_codes_json=[],
            drag_factor_battlefield_codes_json=[],
            battlefield_summary_json={"fixture": True},
            confidence=Decimal("0.9000"),
            evidence_ids_json=[f"ev-m11c-profile-{sku_code}"],
            profile_hash=f"hash-m11c-profile-{sku_code}",
        )
    )
    seed_battlefield_score(session, sku_code, model_name, brand_name, primary_code, "主价值战场", "primary_battlefield", Decimal("0.9100"), size_tier, price_band)
    if secondary_code:
        seed_battlefield_score(session, sku_code, model_name, brand_name, secondary_code, "辅价值战场", "secondary_battlefield", Decimal("0.7700"), size_tier, price_band)


def seed_battlefield_score(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    battlefield_code: str,
    battlefield_name: str,
    relation_status: str,
    score: Decimal,
    size_tier: str,
    price_band: str,
) -> None:
    session.add(
        entities.Core3SkuValueBattlefieldScore(
            score_id=f"m11c-score-{sku_code}-{battlefield_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            battlefield_code=battlefield_code,
            battlefield_name=battlefield_name,
            battlefield_definition=f"{battlefield_name} definition",
            relation_status=relation_status,
            value_effect="premium_driver" if relation_status == "primary_battlefield" else "basic_support",
            battlefield_score=score,
            market_gate_status="passed",
            market_pool_fit_score=Decimal("0.8500"),
            user_voice_score=Decimal("0.8000"),
            task_group_fit_score=Decimal("0.8200"),
            claim_alignment_score=Decimal("0.7600"),
            param_capability_score=Decimal("0.7800"),
            market_validation_score=Decimal("0.7000"),
            sentiment_polarity="positive",
            size_tier=size_tier,
            price_band_in_size_tier=price_band,
            price_percentile_in_size_tier=Decimal("0.520000"),
            score_breakdown_json={"fixture": True},
            status_reason_cn="fixture",
            evidence_ids_json=[f"ev-m11c-score-{sku_code}-{battlefield_code}"],
            confidence=Decimal("0.8800"),
            result_hash=f"hash-m11c-score-{sku_code}-{battlefield_code}",
        )
    )


def seed_stale_current_battlefield_outputs(session: Session) -> None:
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id=f"m11c-profile-stale-{SKU_STRONG}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version="m11c_tv_value_battlefield_taxonomy_v0.1",
            rule_version="m11c_tv_value_battlefield_profile_v0.1",
            sku_code=SKU_STRONG,
            model_name="75A-Pro",
            brand_name="海信",
            size_tier="xlarge_70_85",
            price_band_in_size_tier="mid",
            price_percentile_in_size_tier=Decimal("0.520000"),
            primary_battlefield_code="BF_LARGE_SCREEN_VALUE_UPGRADE",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=[],
            opportunity_battlefield_codes_json=[],
            drag_factor_battlefield_codes_json=[],
            battlefield_summary_json={"fixture": "stale_current_row"},
            confidence=Decimal("0.5000"),
            evidence_ids_json=["ev-stale-m11c-profile"],
            profile_hash="hash-stale-m11c-profile",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldScore(
            score_id=f"m11c-score-stale-{SKU_STRONG}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version="m11c_tv_value_battlefield_taxonomy_v0.1",
            rule_version="m11c_tv_value_battlefield_profile_v0.1",
            sku_code=SKU_STRONG,
            model_name="75A-Pro",
            brand_name="海信",
            battlefield_code="BF_LARGE_SCREEN_VALUE_UPGRADE",
            battlefield_name="旧版大屏换新战场",
            battlefield_definition="stale fixture",
            relation_status="primary_battlefield",
            value_effect="premium_driver",
            battlefield_score=Decimal("0.9900"),
            market_gate_status="passed",
            market_pool_fit_score=Decimal("1.0000"),
            user_voice_score=Decimal("1.0000"),
            task_group_fit_score=Decimal("1.0000"),
            claim_alignment_score=Decimal("1.0000"),
            param_capability_score=Decimal("1.0000"),
            market_validation_score=Decimal("1.0000"),
            sentiment_polarity="positive",
            size_tier="xlarge_70_85",
            price_band_in_size_tier="mid",
            price_percentile_in_size_tier=Decimal("0.520000"),
            score_breakdown_json={"fixture": "stale_current_row"},
            status_reason_cn="旧版本 current 行应该被 M11D 过滤。",
            evidence_ids_json=["ev-stale-m11c-score"],
            confidence=Decimal("0.5000"),
            result_hash="hash-stale-m11c-score",
        )
    )


def test_m11d_pipeline_generates_market_graph_allocations_and_checks() -> None:
    session = make_session()

    result = catforge_pipeline.run_semantic_market_graph(
        session,
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )

    assert result["status"] == "ok"
    assert result["summary"]["population_summary"]["included_sku_count"] == 2
    assert result["summary"]["population_summary"]["input_counts"]["battlefield_profiles"] == 2
    assert result["summary"]["allocation_count"] > 0
    assert result["summary"]["summary_count"] > 0
    assert result["summary"]["graph_snapshot_count"] == 1

    allocations = session.execute(select(entities.Core3SemanticMarketAllocation)).scalars().all()
    assert allocations
    for sku_code in {SKU_STRONG, SKU_NO_TASK}:
        for dimension_type in {"user_task", "target_group", "battlefield"}:
            rows = [row for row in allocations if row.sku_code == sku_code and row.dimension_type == dimension_type]
            if sku_code == SKU_NO_TASK and dimension_type == "user_task":
                assert rows == []
                continue
            assert round(sum(float(row.allocation_weight) for row in rows), 6) == 1.0

    no_task_check = session.execute(
        select(entities.Core3SemanticMarketReconciliationCheck)
        .where(entities.Core3SemanticMarketReconciliationCheck.sku_code == SKU_NO_TASK)
        .where(entities.Core3SemanticMarketReconciliationCheck.dimension_type == "user_task")
        .where(entities.Core3SemanticMarketReconciliationCheck.check_type == "no_allocation_eligible_dimension")
    ).scalar_one()
    assert no_task_check.status == "diagnostic"

    graph = session.execute(select(entities.Core3SemanticMarketGraphSnapshot)).scalar_one()
    assert graph.sku_count == 2
    assert graph.dimension_count >= 4
    assert graph.unallocated_summary_json["no_allocation_count"] == 1


def test_m11d_insight_queries_market_map_and_sku_sales_allocation() -> None:
    session = make_session()
    catforge_pipeline.run_semantic_market_graph(
        session,
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )

    market_map = catforge_insight.query_semantic_market_map(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="TV",
        dimension_type="battlefield",
        dimension_code="BF_LARGE_SCREEN_VALUE_UPGRADE",
        sku_limit=10,
    )
    assert market_map["status"] == "ok"
    assert market_map["items"][0]["dimension_code"] == "BF_LARGE_SCREEN_VALUE_UPGRADE"
    assert market_map["items"][0]["allocated_sku_count"] == 1
    assert market_map["items"][0]["estimated_sales_volume"] > 0
    assert market_map["items"][0]["contributions"][0]["sku_code"] == SKU_STRONG
    assert len(market_map["items"][0]["contributions"]) == 1

    sku_allocation = catforge_insight.query_sku_sales_allocation(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="TV",
        sku_code=SKU_STRONG,
        dimension_type="all",
    )
    assert sku_allocation["status"] == "ok"
    assert sku_allocation["sku_code"] == SKU_STRONG
    assert set(sku_allocation["totals_by_dimension_type"]) == {"battlefield", "target_group", "user_task"}
    assert round(sku_allocation["totals_by_dimension_type"]["battlefield"]["allocation_weight_sum"], 6) == 1.0

    natural = catforge_insight.answer_natural_language(
        session,
        question="查 75A-Pro 的销量分配",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    assert natural["routed_command"] == "sku-sales-allocation"
    assert natural["status"] == "ok"

    generic_map = catforge_insight.answer_natural_language(
        session,
        question="查彩电语义市场图谱",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    assert generic_map["routed_command"] == "semantic-market-map"
    assert generic_map["status"] == "ok"
    assert generic_map["summary_count"] >= 4
    assert generic_map["query_terms"] == []

    specific_map = catforge_insight.answer_natural_language(
        session,
        question="查主价值战场有多少销量",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    assert specific_map["routed_command"] == "semantic-market-map"
    assert specific_map["status"] == "ok"
    assert specific_map["dimension_type"] == "battlefield"
    assert all("主价值战场" in item["dimension_name"] for item in specific_map["items"])
