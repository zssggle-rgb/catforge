from decimal import Decimal

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentUnitRecord,
    TopicHintRecord,
)
from app.services.core3_real_data.comment_quality_profile_service import CommentQualityProfileService


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
SKU_CODE = "TV00029115"


def make_unit(
    idx: int,
    *,
    comment_text_hash: str | None = None,
    source_row_count: int = 1,
    low_value_flag: bool = False,
) -> CommentUnitRecord:
    return CommentUnitRecord(
        comment_unit_id=f"unit-{idx}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id="run-m05",
        module_run_id="module-m05",
        sku_code=SKU_CODE,
        model_name="85E7Q",
        brand_name="海信",
        comment_unit_key=f"{PROJECT_ID}:TV:{BATCH_ID}:{SKU_CODE}:comment_id:c-{idx}",
        dedup_strategy="comment_id",
        comment_id=f"c-{idx}",
        comment_text_hash=comment_text_hash if comment_text_hash is not None else f"sha256:comment:{idx}",
        canonical_comment_text=f"第{idx}条评论",
        canonical_text_length=8,
        source_row_count=source_row_count,
        source_sentence_count=1,
        source_comment_evidence_ids=[f"raw-{idx}-{row}" for row in range(source_row_count)],
        sentiment_hint="positive",
        low_value_flag=low_value_flag,
        low_value_reasons=["too_short_generic"] if low_value_flag else [],
        duplicate_source_count=max(0, source_row_count - 1),
        comment_unit_status="low_value" if low_value_flag else "usable",
        confidence=Decimal("0.9000"),
        confidence_level="high",
        input_fingerprint="sha256:m05:input",
        result_hash=f"sha256:unit:{idx}",
    )


def make_atom(
    idx: int,
    unit: CommentUnitRecord,
    *,
    domain: str = "product_experience",
    sentiment: str = "positive",
    usable: bool = True,
    low_value: bool = False,
    has_dimension: bool = True,
    domain_conflict: bool = False,
    sentiment_conflict: bool = False,
) -> CommentEvidenceAtomRecord:
    return CommentEvidenceAtomRecord(
        comment_evidence_id=f"atom-{idx}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=unit.run_id,
        module_run_id=unit.module_run_id,
        sku_code=SKU_CODE,
        model_name=unit.model_name,
        brand_name=unit.brand_name,
        comment_evidence_key=f"{unit.comment_unit_key}:sentence:{idx}",
        comment_unit_id=unit.comment_unit_id,
        comment_id=unit.comment_id,
        comment_text_hash=unit.comment_text_hash,
        sentence_hash=f"sha256:sentence:{idx}",
        sentence_seq=idx,
        sentence_text=f"第{idx}句评论",
        normalized_sentence_text=f"第{idx}句评论",
        sentence_length=6,
        source_evidence_ids=[f"source-{idx}"],
        source_comment_evidence_ids=list(unit.source_comment_evidence_ids[:1]),
        raw_dimension_paths=["产品体验/游戏流畅"] if has_dimension else [],
        primary_domain_hint=domain,
        domain_conflict_flag=domain_conflict,
        sentiment_hint=sentiment,
        sentiment_source="text_rule",
        sentiment_conflict_flag=sentiment_conflict,
        low_value_flag=low_value,
        low_value_reasons=["too_short_generic"] if low_value else [],
        specificity_score=Decimal("0.8000"),
        usable_for_downstream=usable,
        downstream_block_reasons=[] if usable else ["low_value_sentence"],
        confidence=Decimal("0.8600"),
        confidence_level="high",
        input_fingerprint=unit.input_fingerprint,
        result_hash=f"sha256:atom:{idx}",
    )


def make_topic(idx: int, atom: CommentEvidenceAtomRecord, *, status: str = "matched") -> TopicHintRecord:
    return TopicHintRecord(
        topic_hint_id=f"topic-hint-{idx}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        run_id=atom.run_id,
        module_run_id=atom.module_run_id,
        sku_code=SKU_CODE,
        model_name=atom.model_name,
        brand_name=atom.brand_name,
        comment_evidence_id=atom.comment_evidence_id,
        comment_unit_id=atom.comment_unit_id,
        topic_code="TOPIC_GAMING_SMOOTHNESS" if idx % 2 == 0 else "TOPIC_PICTURE_QUALITY",
        topic_name="游戏流畅" if idx % 2 == 0 else "画质体验",
        topic_group="product_experience",
        match_method="keyword",
        matched_terms=["游戏"] if idx % 2 == 0 else ["画质"],
        polarity_hint=atom.sentiment_hint,
        topic_confidence=Decimal("0.8200"),
        is_weak_hint=True,
        activates_product_claim=True,
        mapped_claim_codes_snapshot=["CLAIM_GAMING_LOW_LATENCY"],
        mapped_task_codes_snapshot=["TASK_GAMING_ENTERTAINMENT"],
        mapped_battlefield_codes_snapshot=["BF_GAMING_SPORTS"],
        topic_hint_status=status,
        input_fingerprint=atom.input_fingerprint,
        result_hash=f"sha256:topic:{idx}:{status}",
    )


def test_quality_profile_builds_limited_ready_profile_from_units_atoms_and_topics():
    units = [make_unit(idx) for idx in range(80)]
    atoms = [make_atom(idx, units[idx % len(units)]) for idx in range(120)]
    topics = [make_topic(idx, atom) for idx, atom in enumerate(atoms[:90])]

    result = CommentQualityProfileService().build_profile(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        comment_units=units,
        sentence_atoms=atoms,
        topic_hints=topics,
    )

    profile = result.record
    assert profile.raw_comment_row_count == 80
    assert profile.comment_unit_count == 80
    assert profile.distinct_comment_id_count == 80
    assert profile.distinct_comment_text_count == 80
    assert profile.sentence_count == 120
    assert profile.usable_sentence_count == 120
    assert profile.sample_status == "limited"
    assert profile.downstream_ready is True
    assert profile.blocked_reasons == []
    assert profile.duplicate_text_rate == Decimal("0.000000")
    assert profile.product_experience_share == Decimal("1.000000")
    assert profile.topic_distribution_json == {"TOPIC_GAMING_SMOOTHNESS": 45, "TOPIC_PICTURE_QUALITY": 45}
    assert profile.comment_usability_score > Decimal("0.800000")
    assert "样本有限但可用" in profile.quality_summary["summary_cn"]


def test_quality_profile_marks_warnings_without_generating_business_conclusions():
    units = [
        make_unit(0, comment_text_hash="sha256:same", source_row_count=2),
        make_unit(1, comment_text_hash="sha256:same", source_row_count=2),
    ]
    atoms = [
        make_atom(0, units[0], domain="service_experience", sentiment="unknown", has_dimension=False, domain_conflict=True),
        make_atom(1, units[0], domain="logistics_installation", sentiment="unknown", has_dimension=False, domain_conflict=True),
        make_atom(2, units[1], domain="service_experience", sentiment="unknown", has_dimension=False, low_value=True),
        make_atom(3, units[1], domain="product_risk", sentiment="negative", has_dimension=True, low_value=True),
        make_atom(4, units[1], domain="service_experience", sentiment="negative", has_dimension=False, low_value=True),
    ]
    topics = [make_topic(0, atoms[0])]

    result = CommentQualityProfileService().build_profile(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        comment_units=units,
        sentence_atoms=atoms,
        topic_hints=topics,
    )

    profile = result.record
    assert profile.downstream_ready is True
    assert profile.review_required is True
    assert set(profile.warning_flags) >= {
        "sample_insufficient",
        "duplicate_text_rate_high",
        "low_value_sentence_rate_high",
        "empty_dimension_rate_high",
        "sentiment_unknown_rate_high",
        "service_installation_share_high",
        "topic_unknown_rate_high",
        "domain_conflict_rate_high",
        "negative_sentence_rate_high",
    }
    assert profile.quality_summary["warning_labels_cn"]
    assert "business_conclusion" not in profile.model_dump()
    assert all(not issue.blocked for issue in result.issues if issue.issue_code in profile.warning_flags)


def test_quality_profile_blocks_downstream_when_no_comment_units_exist():
    result = CommentQualityProfileService().build_profile(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        comment_units=[],
        sentence_atoms=[],
        topic_hints=[],
        input_fingerprint="sha256:m05:empty",
    )

    profile = result.record
    assert profile.sample_status == "unknown"
    assert profile.downstream_ready is False
    assert profile.blocked_reasons == ["no_comment_unit", "no_sentence_atom"]
    assert profile.review_status == "review_required"
    assert profile.comment_usability_score == Decimal("0.000000")
    assert "暂无评论样本" in profile.quality_summary["summary_cn"]
    assert {issue.issue_code for issue in result.issues} == {"no_comment_unit", "no_sentence_atom"}

