from decimal import Decimal

from app.services.core3_real_data.comment_domain_hint_service import CommentDomainHintService
from app.services.core3_real_data.comment_evidence_schemas import M05EvidenceInput, M05SkuInputBundle
from app.services.core3_real_data.comment_sentence_atom_builder import CommentSentenceAtomBuilder
from app.services.core3_real_data.comment_sentiment_hint_service import CommentSentimentHintService
from app.services.core3_real_data.comment_topic_hint_matcher import CommentTopicHintMatcher
from app.services.core3_real_data.comment_topic_seed_loader import CommentTopicSeedLoader
from app.services.core3_real_data.comment_unit_builder import CommentUnitBuilder


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
SKU_CODE = "TV00029115"


def evidence_input(
    evidence_id: str,
    *,
    evidence_type: str = "comment_raw",
    evidence_field: str | None = None,
    comment_id: str | None = "c-001",
    comment_text_hash: str | None = "sha256:comment:001",
    source_row_id: str | None = None,
    segment_text_hash: str | None = None,
    sentence_seq: int | None = None,
    dimension_path_raw: str | None = None,
    text_value: str | None = "画质很好，游戏模式延迟低。",
    payload: dict | None = None,
    base_confidence: Decimal = Decimal("0.9000"),
) -> M05EvidenceInput:
    source_row_id = source_row_id if source_row_id is not None else f"comment_data:{evidence_id}"
    evidence_field = evidence_field if evidence_field is not None else evidence_type
    return M05EvidenceInput(
        evidence_id=evidence_id,
        evidence_key=f"{BATCH_ID}:{SKU_CODE}:{evidence_type}:{evidence_id}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        model_name="85E7Q",
        brand_name="海信",
        evidence_type=evidence_type,
        evidence_field=evidence_field,
        source_row_id=source_row_id,
        clean_record_key=f"clean:{evidence_id}",
        comment_id=comment_id,
        comment_text_hash=comment_text_hash,
        segment_text_hash=segment_text_hash,
        sentence_seq=sentence_seq,
        dimension_path_raw=dimension_path_raw,
        text_value=text_value,
        evidence_payload_json=payload or {},
        base_confidence=base_confidence,
        confidence_level="high",
    )


def bundle(inputs: list[M05EvidenceInput]) -> M05SkuInputBundle:
    return M05SkuInputBundle(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        model_name="85E7Q",
        brand_name="海信",
        evidence_inputs=inputs,
        input_fingerprint="sha256:m05:input",
    )


def build_topic_ready_atoms(sku_bundle: M05SkuInputBundle):
    unit_result = CommentUnitBuilder().build_units(sku_bundle, run_id="run-m05", module_run_id="module-run-m05")
    assert len(unit_result.records) == 1
    atom_result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, unit_result.records)
    assert atom_result.records
    domain_result = CommentDomainHintService().apply_domain_hints(atom_result.records)
    sentiment_result = CommentSentimentHintService().apply_sentiment_hints(domain_result.records)
    return sentiment_result.records


def test_topic_hint_matcher_matches_gaming_topic_from_positive_seed_keywords():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="游戏模式延迟低，玩主机很流畅。", payload={"sentiment_clean": "正面"}),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:gaming",
                sentence_seq=0,
                text_value="游戏模式延迟低，玩主机很流畅",
            ),
        ]
    )
    atoms = build_topic_ready_atoms(sku_bundle)
    seed = CommentTopicSeedLoader().load_seed()
    result = CommentTopicHintMatcher().match_topic_hints(seed, atoms)

    by_topic = {record.topic_code: record for record in result.records}
    gaming = by_topic["TOPIC_GAMING_SMOOTHNESS"]
    assert gaming.match_method == "positive_keyword"
    assert gaming.polarity_hint == "positive"
    assert gaming.topic_hint_status == "matched"
    assert gaming.topic_confidence >= Decimal("0.7500")
    assert gaming.service_guardrail_flag is False
    assert gaming.mapped_claim_codes_snapshot == [
        "CLAIM_HIGH_REFRESH_RATE",
        "CLAIM_GAMING_LOW_LATENCY",
        "CLAIM_HDMI_2_1_GAMING",
    ]
    assert gaming.mapped_task_codes_snapshot == ["TASK_GAMING_ENTERTAINMENT"]
    assert gaming.mapped_battlefield_codes_snapshot == ["BF_GAMING_SPORTS"]
    assert result.matched_count >= 1
    assert_no_forbidden_business_fields(gaming.model_dump())


def test_topic_hint_matcher_matches_negative_system_topic():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="系统卡顿严重，广告多。"),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:system-risk",
                sentence_seq=0,
                text_value="系统卡顿严重，广告多",
            ),
        ]
    )
    atoms = build_topic_ready_atoms(sku_bundle)
    result = CommentTopicHintMatcher().match_topic_hints(CommentTopicSeedLoader().load_seed(), atoms)

    by_topic = {record.topic_code: record for record in result.records}
    system_topic = by_topic["TOPIC_SYSTEM_ADS_PERFORMANCE"]
    assert system_topic.match_method == "negative_keyword"
    assert system_topic.polarity_hint == "negative"
    assert system_topic.topic_hint_status == "matched"
    assert set(system_topic.matched_terms) >= {"广告多", "卡顿"}


def test_topic_hint_matcher_blocks_low_value_topic_hint_instead_of_strong_topic():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="画质清晰。"),
            evidence_input(
                "ev_quality",
                evidence_type="quality_issue",
                evidence_field="low_value_comment",
                text_value="低价值评论提示",
                payload={"issue_type": "low_value_comment"},
            ),
        ]
    )
    atoms = build_topic_ready_atoms(sku_bundle)
    assert atoms[0].low_value_flag is True
    result = CommentTopicHintMatcher().match_topic_hints(CommentTopicSeedLoader().load_seed(), atoms)

    by_topic = {record.topic_code: record for record in result.records}
    picture_topic = by_topic["TOPIC_PICTURE_QUALITY"]
    assert picture_topic.topic_hint_status == "blocked_low_value"
    assert picture_topic.is_weak_hint is True
    assert result.blocked_low_value_count >= 1


def test_topic_hint_matcher_sets_service_guardrail_for_service_topic():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_service",
                comment_id="c-service",
                comment_text_hash="sha256:comment:service",
                text_value="安装师傅服务专业，态度好。",
            )
        ]
    )
    atoms = build_topic_ready_atoms(sku_bundle)
    result = CommentTopicHintMatcher().match_topic_hints(CommentTopicSeedLoader().load_seed(), atoms)

    by_topic = {record.topic_code: record for record in result.records}
    service_topic = by_topic["TOPIC_INSTALLATION_SERVICE"]
    assert service_topic.service_guardrail_flag is True
    assert service_topic.topic_group == "service_experience"
    assert service_topic.topic_hint_status == "blocked_low_value"
    assert service_topic.activates_product_claim is False


def test_topic_hint_matcher_does_not_write_unknown_topic_when_no_seed_match():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_unknown",
                comment_id="c-unknown",
                comment_text_hash="sha256:comment:unknown",
                text_value="今天收到。",
            )
        ]
    )
    atoms = build_topic_ready_atoms(sku_bundle)
    result = CommentTopicHintMatcher().match_topic_hints(CommentTopicSeedLoader().load_seed(), atoms)

    assert result.records == []
    assert result.unknown_atom_count == 1


def test_topic_hint_matcher_blocks_service_topic_when_product_sentence_mentions_service_secondarily():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_product_service",
                comment_id="c-product-service",
                comment_text_hash="sha256:comment:product-service",
                text_value="画质清晰，安装也很快。",
            )
        ]
    )
    atoms = build_topic_ready_atoms(sku_bundle)
    result = CommentTopicHintMatcher().match_topic_hints(CommentTopicSeedLoader().load_seed(), atoms)

    by_topic = {record.topic_code: record for record in result.records}
    assert by_topic["TOPIC_PICTURE_QUALITY"].topic_hint_status == "matched"
    assert by_topic["TOPIC_INSTALLATION_SERVICE"].topic_hint_status == "blocked_service_guardrail"
    assert by_topic["TOPIC_INSTALLATION_SERVICE"].service_guardrail_flag is True
    assert result.blocked_service_guardrail_count == 1


def assert_no_forbidden_business_fields(payload):
    forbidden = {
        "task_code",
        "target_group_code",
        "battlefield_code",
        "competitor_sku_code",
        "candidate_sku_code",
        "selection_slot",
        "business_conclusion",
        "report_payload",
        "report_content",
        "rank",
        "score",
    }
    if isinstance(payload, dict):
        assert forbidden.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_forbidden_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_business_fields(item)
