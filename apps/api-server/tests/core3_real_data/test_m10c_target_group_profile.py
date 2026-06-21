from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_insight, catforge_pipeline
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    Core3RunStatus,
    Core3SourceBatchStatus,
)
from app.services.core3_real_data.m10c_target_group_service import M10CRunner


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606210012"
SKU_FAMILY = "TV00091001"
SKU_SMART = "TV00091002"
SKU_SENIOR = "TV00091003"


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
        entities.Core3M10cSkuTargetGroupProfile.__table__,
        entities.Core3M10cSkuTargetGroupScore.__table__,
        entities.Core3M10cTargetGroupCoverage.__table__,
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
            scan_started_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    seed_sku(session, SKU_FAMILY, "75F-Family", "海信", size=75, price=Decimal("2999"), volume=Decimal("900"))
    seed_sku(session, SKU_SMART, "75S-Smart", "TCL", size=75, price=Decimal("5999"), volume=Decimal("300"))
    seed_sku(session, SKU_SENIOR, "43P-Parent", "创维", size=43, price=Decimal("1599"), volume=Decimal("120"))
    seed_claims(
        session,
        SKU_FAMILY,
        "75F-Family",
        "海信",
        ["tv_claim_theater_scene", "tv_claim_hdr_high_brightness", "tv_claim_speaker_sound"],
    )
    seed_claims(
        session,
        SKU_SMART,
        "75S-Smart",
        "TCL",
        ["tv_claim_voice_control", "tv_claim_casting_connectivity", "tv_claim_ai_large_model", "tv_claim_smart_home_iot"],
    )
    seed_comments(
        session,
        SKU_FAMILY,
        "75F-Family",
        "海信",
        [
            ("audience_child_family", "一家人客厅追剧都说画质不错", "audience_signal", "人群信号", "positive"),
            ("use_living_room_cinema", "客厅看电影大屏很震撼", "use_case_signal", "用途信号", "positive"),
        ],
    )
    seed_comments(
        session,
        SKU_SENIOR,
        "43P-Parent",
        "创维",
        [
            ("audience_senior", "买给爸妈用，但是广告多操作也不简单", "audience_signal", "人群信号", "negative"),
        ],
    )
    session.commit()


def seed_sku(session: Session, sku_code: str, model_name: str, brand_name: str, *, size: int, price: Decimal, volume: Decimal) -> None:
    size_tier = "small_32_45" if size <= 45 else "xlarge_70_85"
    amount = price * volume
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id=f"param-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=model_name,
            param_values_json={
                "screen_size_inch": {"normalized_value": size, "numeric_value": size, "value_presence": "present"},
                "resolution_class": {"normalized_value": "4K", "value_text": "4K", "value_presence": "present"},
                "hdr_support_flag": {"normalized_value": True, "value_presence": "present"},
                "memory_capacity_gb": {"normalized_value": 4, "numeric_value": 4, "value_presence": "present"},
                "speaker_power_w": {"normalized_value": 40, "numeric_value": 40, "value_presence": "present"},
                "voice_recognition_flag": {"normalized_value": True, "value_presence": "present"},
                "far_field_voice_flag": {"normalized_value": True, "value_presence": "present"},
                "network_tv_flag": {"normalized_value": True, "value_presence": "present"},
                "wifi_builtin_flag": {"normalized_value": True, "value_presence": "present"},
                "smart_tv_flag": {"normalized_value": True, "value_presence": "present"},
                "ai_large_model_flag": {"normalized_value": True, "value_presence": "present"},
                "iot_control_flag": {"normalized_value": True, "value_presence": "present"},
                "dimension_tier_profile": {"size": size_tier},
            },
            core_picture_params_json={},
            core_gaming_params_json={},
            core_system_params_json={},
            core_eye_care_params_json={},
            param_completeness=Decimal("0.800000"),
            known_param_count=12,
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
            size_segment="75_85" if size > 45 else "32_45",
            screen_size_class="large_upgrade" if size > 45 else "compact_screen",
            sales_volume_total=volume,
            sales_amount_total=amount,
            price_wavg=price,
            price_median=price,
            price_per_inch=price / Decimal(size),
            volume_percentile_in_size=Decimal("0.900000") if sku_code == SKU_FAMILY else Decimal("0.300000"),
            amount_percentile_in_size=Decimal("0.800000") if sku_code == SKU_FAMILY else Decimal("0.200000"),
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


def seed_claims(session: Session, sku_code: str, model_name: str, brand_name: str, claim_codes: list[str]) -> None:
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
            evidence_ids=[f"ev-claim-profile-{sku_code}"],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash=f"sha256:claim-profile-{sku_code}",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    for claim_code in claim_codes:
        session.add(
            entities.Core3SkuClaimFact(
                claim_fact_id=f"claim-fact-{sku_code}-{claim_code}",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                product_category="TV",
                taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
                sku_code=sku_code,
                model_name=model_name,
                brand_name=brand_name,
                source_claim_key=f"seed:{sku_code}:{claim_code}",
                raw_claim_text=claim_code,
                clean_claim_text=claim_code,
                claim_code=claim_code,
                claim_name=claim_code,
                claim_dimension="test",
                claim_subtype="test",
                claim_kind="product_experience",
                match_type="seed",
                match_score=Decimal("1.0000"),
                param_support_status="supported",
                supporting_param_codes=["screen_size_inch"],
                supporting_param_snapshot_json={},
                support_explanation="test seed",
                fact_claim_flag=True,
                service_separate_flag=False,
                evidence_ids=[f"ev-claim-{sku_code}-{claim_code}"],
                quality_flags=[],
                confidence=Decimal("0.9000"),
                fact_hash=f"sha256:{sku_code}:{claim_code}",
                rule_version=CORE3_M04C_TV_RULE_VERSION,
            )
        )


def seed_comments(
    session: Session,
    sku_code: str,
    model_name: str,
    brand_name: str,
    comments: list[tuple[str, str, str, str, str]],
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
            comment_sentence_count=len(comments),
            matched_sentence_count=len(comments),
            fact_atom_count=len(comments),
            product_fact_sentence_count=len(comments),
            positive_sentence_count=sum(1 for item in comments if item[4] == "positive"),
            negative_sentence_count=sum(1 for item in comments if item[4] == "negative"),
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
            evidence_ids=[f"ev-comment-profile-{sku_code}"],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash=f"sha256:comment-profile-{sku_code}",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    for index, (subdimension_code, text, dimension_code, dimension_name, polarity) in enumerate(comments, start=1):
        session.add(
            entities.Core3CommentFactAtom(
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
                dimension_type=dimension_code,
                polarity=polarity,
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
                evidence_ids=[f"ev-comment-{sku_code}-{index}"],
                quality_flags=[],
                confidence=Decimal("0.9000"),
                fact_hash=f"sha256:comment-{sku_code}-{index}",
                rule_version=CORE3_M05C_TV_RULE_VERSION,
            )
        )


def test_m10c_runner_generates_target_group_profiles_and_coverage() -> None:
    session = make_session()

    result = M10CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    session.commit()

    assert result.status == Core3RunStatus.SUCCESS
    assert result.summary_json["sku_count"] == 3
    assert result.summary_json["target_group_count"] == 10

    family_profile = session.execute(
        select(entities.Core3M10cSkuTargetGroupProfile).where(entities.Core3M10cSkuTargetGroupProfile.sku_code == SKU_FAMILY)
    ).scalar_one()
    assert family_profile.primary_target_group_code == "TG_MAINSTREAM_FAMILY_VIEWER"
    assert family_profile.size_tier == "xlarge_70_85"
    assert family_profile.price_band_in_size_tier == "low"

    smart_score = session.execute(
        select(entities.Core3M10cSkuTargetGroupScore)
        .where(entities.Core3M10cSkuTargetGroupScore.sku_code == SKU_SMART)
        .where(entities.Core3M10cSkuTargetGroupScore.target_group_code == "TG_SMART_CONNECTED_USER")
    ).scalar_one()
    assert smart_score.relation_status == "brand_claimed_group"

    senior_score = session.execute(
        select(entities.Core3M10cSkuTargetGroupScore)
        .where(entities.Core3M10cSkuTargetGroupScore.sku_code == SKU_SENIOR)
        .where(entities.Core3M10cSkuTargetGroupScore.target_group_code == "TG_SENIOR_PARENT_FRIENDLY")
    ).scalar_one()
    assert senior_score.relation_status == "unmet_group_need"

    coverage_count = session.execute(select(entities.Core3M10cTargetGroupCoverage)).scalars().all()
    assert len(coverage_count) == 10


def test_m10c_pipeline_and_insight_cli_query_target_groups() -> None:
    session = make_session()

    pipeline_result = catforge_pipeline.run_target_group(
        session,
        project_id=PROJECT_ID,
        source_category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        force_rebuild=True,
    )
    assert pipeline_result["status"] == "ok"
    assert pipeline_result["summary"]["profile_count"] == 3

    sku_profile = catforge_insight.query_sku_target_group(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="75F-Family",
        include_scores=True,
    )
    coverage = catforge_insight.query_target_group_skus(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        target_group_code="TG_MAINSTREAM_FAMILY_VIEWER",
        sku_limit=10,
    )
    natural = catforge_insight.answer_natural_language(
        session,
        question="查 75F-Family 的目标客群",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )
    taxonomy = catforge_insight.query_target_group_taxonomy(product_category="TV")

    assert sku_profile["status"] == "ok"
    assert sku_profile["primary_target_group_code"] == "TG_MAINSTREAM_FAMILY_VIEWER"
    assert any(item["target_group_code"] == "TG_MAINSTREAM_FAMILY_VIEWER" for item in sku_profile["scores"])
    assert SKU_FAMILY in coverage["sku_codes"]
    assert natural["routed_command"] == "sku-target-group"
    assert natural["primary_target_group_code"] == "TG_MAINSTREAM_FAMILY_VIEWER"
    assert taxonomy["target_group_count"] == 10
    assert taxonomy["taxonomy_version"] == CORE3_M10C_TV_TAXONOMY_VERSION
