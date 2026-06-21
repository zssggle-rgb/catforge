from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_insight
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    Core3SourceBatchStatus,
)
from app.services.core3_real_data.m04c_claim_fact_profile_service import M04CRunner


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606210001"
SKU_CODE = "TV00077777"


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
        entities.Core3EvidenceAtom.__table__,
        entities.Core3SkuParamProfile.__table__,
        entities.Core3SkuClaimFactProfile.__table__,
        entities.Core3SkuClaimFact.__table__,
        entities.Core3SkuClaimDimensionPosition.__table__,
        entities.Core3ClaimPositionCoverage.__table__,
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
            source_tables=["selling_points_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
        )
    )
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="param-profile-tv-77777",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=SKU_CODE,
            model_name="75X-Test",
            param_values_json={
                "mini_led_flag": {"normalized_value": True, "value_presence": "present"},
                "mini_led_type": {"normalized_value": "MINILED", "value_text": "MINILED", "value_presence": "present"},
                "local_dimming_zone_count": {"normalized_value": 1000, "numeric_value": 1000, "value_presence": "present"},
                "hdr_support_flag": {"normalized_value": True, "value_presence": "present"},
                "declared_brightness_nit_or_band": {"normalized_value": 800, "numeric_value": 800, "value_presence": "present"},
                "declared_refresh_rate_hz": {"normalized_value": 144, "numeric_value": 144, "value_presence": "present"},
                "ai_capability_flag": {"normalized_value": True, "value_presence": "present"},
                "ai_model_name": {"normalized_value": "星海大模型", "value_text": "星海大模型", "value_presence": "present"},
                "voice_recognition_flag": {"normalized_value": True, "value_presence": "present"},
                "hdmi_version_mix": {"normalized_value": {"has_hdmi_2_1": True}, "value_presence": "present"},
            },
            core_picture_params_json={},
            core_gaming_params_json={},
            core_system_params_json={},
            core_eye_care_params_json={},
            param_completeness=Decimal("0.900000"),
            known_param_count=10,
            unknown_param_count=0,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=[],
            quality_summary_json={},
            profile_hash="sha256:test-param-profile",
            seed_version="tv_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add_all(
        [
            promo_evidence("ev_claim_picture", "MiniLED 千级分区 HDR 高亮 AI画质引擎 144Hz 游戏"),
            promo_evidence("ev_claim_smart", "AI大模型语音控制"),
            promo_evidence("ev_claim_service", "送货安装售后服务"),
            promo_evidence("ev_claim_picture_raw_duplicate", "MiniLED 千级分区 HDR 高亮 AI画质引擎 144Hz 游戏", evidence_type="promo_raw"),
        ]
    )
    session.commit()


def promo_evidence(evidence_id: str, claim_text: str, *, evidence_type: str = "promo_sentence") -> entities.Core3EvidenceAtom:
    return entities.Core3EvidenceAtom(
        evidence_id=evidence_id,
        evidence_key=evidence_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        model_name="75X-Test",
        brand_name="测试品牌",
        evidence_type=evidence_type,
        evidence_grain="sentence",
        evidence_field="卖点",
        source_table="selling_points_data",
        source_pk=evidence_id,
        source_row_id=evidence_id,
        clean_table="core3_clean_claim_sentence",
        clean_record_key=evidence_id,
        clean_hash=f"sha256:{evidence_id}",
        clean_version="m01-cleaning-quality-0.1.0",
        raw_field="selling_point",
        raw_value=claim_text,
        clean_field="claim_sentence",
        clean_value=claim_text,
        text_value=claim_text,
        sentence_seq=1,
        quality_status="ok",
        quality_flags=[],
        base_confidence=Decimal("0.9000"),
        confidence_level="high",
        evidence_payload_json={},
        evidence_status="current",
    )


def test_m04c_runner_generates_claim_fact_profile_and_service_separation():
    session = make_session()

    result = M04CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        input_source="evidence",
        force_rebuild=True,
    )
    session.commit()

    assert result.status == "success"
    assert result.summary_json["input_claim_text_count"] == 3
    assert result.summary_json["sku_profile_count"] == 1
    assert result.summary_json["service_separate_claim_count"] == 1
    assert result.summary_json["fact_claim_count"] >= 6

    profile = session.execute(select(entities.Core3SkuClaimFactProfile)).scalar_one()
    assert profile.fact_claim_count >= 6
    assert "tv_claim_service_fulfillment" in profile.service_claim_codes
    assert profile.dimension_position_profile_json["supported:picture_quality"]["position_code"] == "picture_flagship_miniled_composite"

    service_fact = session.execute(
        select(entities.Core3SkuClaimFact).where(entities.Core3SkuClaimFact.claim_code == "tv_claim_service_fulfillment")
    ).scalar_one()
    assert service_fact.service_separate_flag is True
    assert service_fact.fact_claim_flag is False


def test_m04c_insight_queries_claim_profile_taxonomy_and_coverage():
    session = make_session()
    M04CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        input_source="evidence",
        force_rebuild=True,
    )
    session.commit()

    profile = catforge_insight.query_sku_claim_profile(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="75X-Test",
        include_claim_facts=True,
    )
    taxonomy = catforge_insight.query_claim_taxonomy(product_category="TV", search="MiniLED")
    coverage = catforge_insight.query_claim_position_coverage(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="MiniLED 复合画质旗舰型覆盖 SKU",
        sku_limit=10,
    )
    natural = catforge_insight.answer_natural_language(
        session,
        question="查 75X-Test 的卖点画像",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )

    assert profile["status"] == "ok"
    assert profile["claim_summary"]["service_separate_claim_count"] == 1
    assert any(item["claim_code"] == "tv_claim_miniled_display" for item in profile["claim_facts"])
    assert taxonomy["taxonomy_version"] == CORE3_M04C_TV_TAXONOMY_VERSION
    assert any(item["claim_code"] == "tv_claim_miniled_display" for item in taxonomy["claims"])
    assert coverage["coverage_count"] == 1
    assert coverage["coverages"][0]["position_code"] == "picture_flagship_miniled_composite"
    assert coverage["coverages"][0]["sku_codes"] == [SKU_CODE]
    assert natural["routed_command"] == "sku-claim-profile"
    assert natural["sku"]["sku_code"] == SKU_CODE
