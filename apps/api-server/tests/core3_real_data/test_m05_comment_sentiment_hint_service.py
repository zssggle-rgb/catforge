from decimal import Decimal

from app.services.core3_real_data.comment_domain_hint_service import CommentDomainHintService
from app.services.core3_real_data.comment_evidence_schemas import M05EvidenceInput, M05SkuInputBundle
from app.services.core3_real_data.comment_sentence_atom_builder import CommentSentenceAtomBuilder
from app.services.core3_real_data.comment_sentiment_hint_service import CommentSentimentHintService
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


def build_enriched_atoms(sku_bundle: M05SkuInputBundle):
    unit_result = CommentUnitBuilder().build_units(sku_bundle, run_id="run-m05", module_run_id="module-run-m05")
    assert len(unit_result.records) == 1
    atom_result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, unit_result.records)
    assert atom_result.records
    domain_result = CommentDomainHintService().apply_domain_hints(atom_result.records)
    return domain_result.records


def test_sentiment_hint_service_combines_raw_positive_and_positive_text():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="画质清晰，游戏模式延迟低。", payload={"sentiment_clean": "正面"}),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:game",
                sentence_seq=0,
                text_value="游戏模式延迟低",
            ),
        ]
    )
    atom = build_enriched_atoms(sku_bundle)[0]
    result = CommentSentimentHintService().apply_sentiment_hints([atom])

    enriched = result.records[0]
    assert enriched.sentiment_hint == "positive"
    assert enriched.sentiment_source == "raw_text_combined"
    assert enriched.sentiment_conflict_flag is False
    assert enriched.confidence == atom.confidence
    assert result.positive_count == 1
    assert result.text_rule_count == 1
    assert_no_forbidden_business_fields(enriched.model_dump())


def test_sentiment_hint_service_uses_text_rule_when_raw_sentiment_is_unknown():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="接口丰富，连接游戏主机很方便。"),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:interface",
                sentence_seq=0,
                text_value="连接游戏主机很方便",
            ),
        ]
    )
    atom = build_enriched_atoms(sku_bundle)[0]
    result = CommentSentimentHintService().apply_sentiment_hints([atom])

    enriched = result.records[0]
    assert enriched.sentiment_hint == "positive"
    assert enriched.sentiment_source == "text_rule"
    assert enriched.sentiment_conflict_flag is False
    assert enriched.confidence <= Decimal("0.7200")


def test_sentiment_hint_service_marks_raw_text_conflict_for_review():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="系统卡顿严重，广告多。", payload={"sentiment_clean": "正面"}),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:conflict",
                sentence_seq=0,
                text_value="系统卡顿严重，广告多",
            ),
        ]
    )
    atom = build_enriched_atoms(sku_bundle)[0]
    result = CommentSentimentHintService().apply_sentiment_hints([atom])

    enriched = result.records[0]
    assert enriched.sentiment_hint == "conflict"
    assert enriched.sentiment_source == "raw_text_combined"
    assert enriched.sentiment_conflict_flag is True
    assert enriched.review_required is True
    assert enriched.review_status == "review_required"
    assert enriched.review_reason_json["reason_codes"] == ["sentiment_conflict"]
    assert enriched.confidence <= Decimal("0.4500")
    assert result.conflict_count == 1
    assert len(result.issues) == 1


def test_sentiment_hint_service_preserves_raw_neutral_without_text_signal():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="今天收到。", payload={"sentiment_clean": "neutral"}),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:neutral",
                sentence_seq=0,
                text_value="今天收到",
            ),
        ]
    )
    atom = build_enriched_atoms(sku_bundle)[0]
    result = CommentSentimentHintService().apply_sentiment_hints([atom])

    enriched = result.records[0]
    assert enriched.sentiment_hint == "neutral"
    assert enriched.sentiment_source == "raw_only"
    assert enriched.sentiment_conflict_flag is False
    assert result.neutral_count == 1


def test_sentiment_hint_service_does_not_turn_low_value_generic_positive_into_strong_positive():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_generic",
                comment_id="c-generic",
                comment_text_hash="sha256:comment:generic",
                text_value="很好",
            )
        ]
    )
    atom = build_enriched_atoms(sku_bundle)[0]
    result = CommentSentimentHintService().apply_sentiment_hints([atom])

    enriched = result.records[0]
    assert enriched.low_value_flag is True
    assert enriched.sentiment_hint == "unknown"
    assert enriched.sentiment_source == "unknown"
    assert enriched.confidence <= Decimal("0.3500")
    assert result.unknown_count == 1


def test_sentiment_hint_service_detects_negative_text_without_raw_sentiment():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="开机慢，操作复杂。"),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:negative",
                sentence_seq=0,
                text_value="开机慢，操作复杂",
            ),
        ]
    )
    atom = build_enriched_atoms(sku_bundle)[0]
    result = CommentSentimentHintService().apply_sentiment_hints([atom])

    enriched = result.records[0]
    assert enriched.sentiment_hint == "negative"
    assert enriched.sentiment_source == "text_rule"
    assert enriched.sentiment_conflict_flag is False
    assert result.negative_count == 1
    assert_no_forbidden_business_fields(enriched.model_dump())


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
