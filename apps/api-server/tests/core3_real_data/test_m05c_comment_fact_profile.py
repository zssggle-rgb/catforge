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
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    Core3SourceBatchStatus,
)
from app.services.core3_real_data.m05c_comment_fact_profile_service import M05CRunner


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
        entities.Core3CommentFactAtom.__table__,
        entities.Core3SkuCommentFactProfile.__table__,
        entities.Core3CommentFactCoverage.__table__,
        entities.Core3CommentFactReviewIssue.__table__,
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
            source_tables=["comment_data"],
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
                "resolution_class": {"normalized_value": "4K", "value_text": "4K", "value_presence": "present"},
                "hdr_support_flag": {"normalized_value": True, "value_presence": "present"},
                "declared_brightness_nit_or_band": {"normalized_value": 800, "numeric_value": 800, "value_presence": "present"},
                "declared_refresh_rate_hz": {"normalized_value": 144, "numeric_value": 144, "value_presence": "present"},
                "processor_chip_model": {"normalized_value": "A73", "value_text": "A73", "value_presence": "present"},
                "memory_capacity_gb": {"normalized_value": 4, "numeric_value": 4, "value_presence": "present"},
                "voice_recognition_flag": {"normalized_value": True, "value_presence": "present"},
                "hdmi_version_mix": {"normalized_value": {"has_hdmi_2_1": True}, "value_presence": "present"},
                "speaker_power_w": {"normalized_value": 40, "numeric_value": 40, "value_presence": "present"},
                "screen_size_inch": {"normalized_value": 75, "numeric_value": 75, "value_presence": "present"},
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
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id="claim-profile-tv-77777",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code=SKU_CODE,
            model_name="75X-Test",
            brand_name="创维",
            raw_claim_count=4,
            matched_claim_count=4,
            fact_claim_count=4,
            unsupported_claim_count=0,
            param_unknown_claim_count=0,
            service_separate_claim_count=0,
            claim_texts_json=[],
            claim_codes=["tv_claim_high_refresh_rate", "tv_claim_chip_performance", "tv_claim_speaker_sound", "tv_claim_value_price"],
            fact_claim_codes=["tv_claim_high_refresh_rate", "tv_claim_chip_performance", "tv_claim_speaker_sound", "tv_claim_value_price"],
            unsupported_claim_codes=[],
            service_claim_codes=[],
            dimension_profile_json={},
            dimension_position_profile_json={},
            claim_summary_json={},
            evidence_ids=[],
            quality_flags=[],
            confidence=Decimal("0.9000"),
            profile_hash="sha256:test-claim-profile",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    session.add_all(
        [
            claim_fact("claim-refresh", "tv_claim_high_refresh_rate", "高刷新率", "motion_gaming", "refresh", ["declared_refresh_rate_hz"]),
            claim_fact("claim-chip", "tv_claim_chip_performance", "芯片性能", "system_performance", "chip", ["processor_chip_model"]),
            claim_fact("claim-sound", "tv_claim_speaker_sound", "音响效果", "audio_cinema", "sound", ["speaker_power_w"]),
            claim_fact("claim-value", "tv_claim_value_price", "性价比", "energy_value", "value", []),
        ]
    )
    comments = [
        ("comment-1", "画质清晰，系统流畅不卡顿，高刷游戏很顺"),
        ("comment-2", "创维老牌子值得信赖，再次购买"),
        ("comment-3", "比索尼便宜，画质也不错"),
        ("comment-4", "安装师傅很好"),
        ("comment-5", "音质差，声音小"),
    ]
    session.add_all(comment_evidence(evidence_id, text_value, index) for index, (evidence_id, text_value) in enumerate(comments, start=1))
    session.commit()


def claim_fact(
    claim_fact_id: str,
    claim_code: str,
    claim_name: str,
    claim_dimension: str,
    claim_subtype: str,
    supporting_param_codes: list[str],
) -> entities.Core3SkuClaimFact:
    return entities.Core3SkuClaimFact(
        claim_fact_id=claim_fact_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
        sku_code=SKU_CODE,
        model_name="75X-Test",
        brand_name="创维",
        source_claim_key=f"seed:{claim_code}",
        claim_seq=1,
        raw_claim_text=claim_name,
        clean_claim_text=claim_name,
        claim_code=claim_code,
        claim_name=claim_name,
        claim_dimension=claim_dimension,
        claim_subtype=claim_subtype,
        claim_kind="product_experience",
        match_type="seed",
        match_score=Decimal("1.0000"),
        param_support_status="supported",
        supporting_param_codes=supporting_param_codes,
        supporting_param_snapshot_json={},
        support_explanation="test seed",
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=[],
        quality_flags=[],
        confidence=Decimal("0.9000"),
        fact_hash=f"sha256:{claim_fact_id}",
        rule_version=CORE3_M04C_TV_RULE_VERSION,
    )


def comment_evidence(evidence_id: str, text_value: str, sentence_seq: int) -> entities.Core3EvidenceAtom:
    return entities.Core3EvidenceAtom(
        evidence_id=evidence_id,
        evidence_key=evidence_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        model_name="75X-Test",
        brand_name="创维",
        evidence_type="comment_sentence",
        evidence_grain="sentence",
        evidence_field="评论",
        source_table="comment_data",
        source_pk=evidence_id,
        source_row_id=evidence_id,
        clean_table="core3_clean_comment_sentence",
        clean_record_key=evidence_id,
        clean_hash=f"sha256:{evidence_id}",
        clean_version="m01-cleaning-quality-0.1.0",
        raw_field="comment_text",
        raw_value=text_value,
        clean_field="comment_sentence",
        clean_value=text_value,
        text_value=text_value,
        comment_id=f"c-{sentence_seq}",
        sentence_seq=sentence_seq,
        quality_status="ok",
        quality_flags=[],
        base_confidence=Decimal("0.9000"),
        confidence_level="high",
        sample_status="sufficient",
        evidence_payload_json={},
        evidence_status="current",
    )


def test_m05c_runner_generates_comment_fact_profile_and_dimension_coverage():
    session = make_session()

    result = M05CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        llm_mode="off",
        force_rebuild=True,
    )
    session.commit()

    assert result.status in {"success", "warning"}
    assert result.summary_json["input_comment_sentence_count"] == 5
    assert result.summary_json["sku_profile_count"] == 1
    assert result.summary_json["comment_fact_count"] >= 8
    assert result.summary_json["service_excluded_sentence_count"] == 1
    assert result.summary_json["review_issue_count"] == 1

    profile = session.execute(select(entities.Core3SkuCommentFactProfile)).scalar_one()
    assert profile.positive_sentence_count >= 3
    assert profile.negative_sentence_count == 1
    assert profile.service_excluded_sentence_count == 1
    assert "declared_refresh_rate_hz" in profile.supported_param_codes
    assert "speaker_power_w" in profile.contradicted_param_codes
    assert "brand_power_signal" in profile.signal_summary_json

    system_fact = session.execute(
        select(entities.Core3CommentFactAtom).where(entities.Core3CommentFactAtom.subdimension_code == "system_smooth_ads")
    ).scalar_one()
    assert system_fact.polarity == "positive"
    assert system_fact.support_relation == "supports_sku_param_claim"

    service_fact = session.execute(
        select(entities.Core3CommentFactAtom).where(entities.Core3CommentFactAtom.subdimension_code == "service_delivery_install")
    ).scalar_one()
    assert service_fact.support_relation == "service_excluded"

    coverage_types = set(session.execute(select(entities.Core3CommentFactCoverage.coverage_type)).scalars())
    assert "brand_power_signal" in coverage_types
    assert "competitor_comparison_signal" in coverage_types
    assert "param_support" in coverage_types
    assert "param_contradiction" in coverage_types

    review_issue = session.execute(select(entities.Core3CommentFactReviewIssue)).scalar_one()
    assert review_issue.issue_type == "comment_contradicts_existing_param_or_claim"


def test_m05c_insight_queries_comment_profile_taxonomy_and_coverage():
    session = make_session()
    M05CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="TV",
        llm_mode="off",
        force_rebuild=True,
    )
    session.commit()

    profile = catforge_insight.query_sku_comment_profile(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="75X-Test",
        include_comment_facts=True,
    )
    taxonomy = catforge_insight.query_comment_taxonomy(product_category="TV", search="品牌力")
    coverage = catforge_insight.query_comment_dimension_coverage(
        session,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        query="品牌力覆盖哪些 SKU",
        sku_limit=10,
    )
    natural = catforge_insight.answer_natural_language(
        session,
        question="查 75X-Test 的评论画像",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id="latest",
        product_category="auto",
        output_format="json",
        sku_limit=10,
    )

    assert profile["status"] == "ok"
    assert profile["comment_summary"]["service_excluded_sentence_count"] == 1
    assert any(item["subdimension_code"] == "brand_trust" for item in profile["comment_facts"])
    assert taxonomy["taxonomy_version"] == CORE3_M05C_TV_TAXONOMY_VERSION
    assert any(item["subdimension_code"] == "brand_trust" for item in taxonomy["subdimensions"])
    assert coverage["coverage_count"] >= 1
    assert coverage["coverages"][0]["sku_codes"] == [SKU_CODE]
    assert natural["routed_command"] == "sku-comment-profile"
    assert natural["sku"]["sku_code"] == SKU_CODE


def test_m05c_blocks_unpublished_comment_taxonomy_for_other_category():
    session = make_session()

    result = M05CRunner(session).run_batch(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        product_category="AC",
        llm_mode="off",
        force_rebuild=True,
    )

    assert result.status == "failed"
    assert "评论事实 taxonomy 未发布" in result.warnings[-1]
