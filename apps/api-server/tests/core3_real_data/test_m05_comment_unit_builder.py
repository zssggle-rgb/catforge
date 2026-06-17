from decimal import Decimal

from app.services.core3_real_data.comment_evidence_schemas import M05EvidenceInput, M05SkuInputBundle
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
    raw_value: str | None = None,
    clean_value: str | None = None,
    payload: dict | None = None,
    quality_flags: list[str] | None = None,
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
        raw_value=raw_value,
        clean_value=clean_value,
        evidence_payload_json=payload or {},
        base_confidence=base_confidence,
        confidence_level="high",
        quality_flags=quality_flags or [],
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


def test_comment_unit_builder_merges_comment_id_group_and_collects_sources():
    result = CommentUnitBuilder().build_units(
        bundle(
            [
                evidence_input(
                    "ev_raw",
                    text_value="画质很好，游戏模式延迟低。",
                    payload={"sentiment_clean": "正面"},
                ),
                evidence_input(
                    "ev_sentence",
                    evidence_type="comment_sentence",
                    evidence_field="comment_sentence:0",
                    segment_text_hash="sha256:sentence:001",
                    sentence_seq=0,
                    text_value="游戏模式延迟低",
                    payload={"sentiment_clean": "positive"},
                ),
                evidence_input(
                    "ev_dimension",
                    evidence_type="comment_dimension",
                    evidence_field="comment_dimension",
                    dimension_path_raw="产品体验/游戏流畅",
                    text_value="游戏流畅",
                ),
                evidence_input(
                    "ev_quality",
                    evidence_type="quality_issue",
                    evidence_field="comment_dimension_missing",
                    text_value="评论维度缺失提示",
                ),
            ]
        ),
        run_id="run-m05",
        module_run_id="module-run-m05",
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record.dedup_strategy == "comment_id"
    assert record.comment_id == "c-001"
    assert record.canonical_comment_text == "画质很好，游戏模式延迟低。"
    assert record.source_comment_evidence_ids == ["ev_raw"]
    assert record.source_sentence_evidence_ids == ["ev_sentence"]
    assert record.source_dimension_evidence_ids == ["ev_dimension"]
    assert record.source_quality_evidence_ids == ["ev_quality"]
    assert record.raw_dimension_paths == ["产品体验/游戏流畅"]
    assert record.sentiment_hint == "positive"
    assert record.sentiment_conflict_flag is False
    assert record.comment_unit_status == "usable"
    assert record.confidence == Decimal("0.9000")
    assert record.confidence_level == "high"
    assert result.review_required_count == 0
    assert result.low_value_count == 0
    assert_no_forbidden_business_fields(record.model_dump())


def test_comment_unit_builder_uses_text_hash_and_source_row_fallback_penalties():
    result = CommentUnitBuilder().build_units(
        bundle(
            [
                evidence_input(
                    "ev_text_hash",
                    comment_id=None,
                    comment_text_hash="sha256:comment:text-only",
                    source_row_id="comment_data:text-only",
                ),
                evidence_input(
                    "ev_source_row",
                    comment_id=None,
                    comment_text_hash=None,
                    source_row_id="comment_data:source-row-only",
                    text_value="接口丰富，连接游戏主机方便。",
                ),
            ]
        )
    )

    by_evidence = {record.source_comment_evidence_ids[0]: record for record in result.records}
    text_hash_record = by_evidence["ev_text_hash"]
    source_row_record = by_evidence["ev_source_row"]

    assert text_hash_record.dedup_strategy == "text_hash"
    assert text_hash_record.confidence == Decimal("0.8200")
    assert text_hash_record.review_required is False
    assert source_row_record.dedup_strategy == "source_row_fallback"
    assert source_row_record.confidence == Decimal("0.6500")
    assert source_row_record.review_required is True
    assert source_row_record.review_status == "review_required"
    assert source_row_record.review_reason_json["reason_codes"] == ["source_row_fallback"]


def test_comment_unit_builder_flags_low_value_rules_and_caps_confidence():
    result = CommentUnitBuilder().build_units(
        bundle(
            [
                evidence_input("ev_default", comment_id="c-default", comment_text_hash="sha256:default", text_value="此用户没有填写评价"),
                evidence_input("ev_punctuation", comment_id="c-punct", comment_text_hash="sha256:punct", text_value="！！！"),
                evidence_input("ev_generic", comment_id="c-generic", comment_text_hash="sha256:generic", text_value="很好"),
                evidence_input("ev_service", comment_id="c-service", comment_text_hash="sha256:service", text_value="安装师傅服务很好"),
                evidence_input(
                    "ev_quality_raw",
                    comment_id="c-quality",
                    comment_text_hash="sha256:quality",
                    text_value="产品很满意",
                ),
                evidence_input(
                    "ev_quality_flag",
                    evidence_type="quality_issue",
                    evidence_field="low_value_comment",
                    comment_id="c-quality",
                    comment_text_hash="sha256:quality",
                    text_value="低价值评论提示",
                    quality_flags=["low_value_comment"],
                ),
            ]
        )
    )

    by_comment_id = {record.comment_id: record for record in result.records}
    assert "default_positive" in by_comment_id["c-default"].low_value_reasons
    assert "punctuation_only" in by_comment_id["c-punct"].low_value_reasons
    assert "too_short_generic" in by_comment_id["c-generic"].low_value_reasons
    assert "service_only_for_product_use" in by_comment_id["c-service"].low_value_reasons
    assert "quality_issue_flagged" in by_comment_id["c-quality"].low_value_reasons

    assert result.low_value_count == 5
    for record in result.records:
        assert record.comment_unit_status == "low_value"
        assert record.confidence <= Decimal("0.3500")


def test_comment_unit_builder_detects_template_duplicate_and_sentiment_conflict():
    result = CommentUnitBuilder(duplicate_text_threshold=2).build_units(
        bundle(
            [
                evidence_input(
                    "ev_dup_1",
                    comment_id="c-dup-1",
                    comment_text_hash="sha256:comment:duplicate",
                    text_value="观赛画面流畅，不拖影。",
                    payload={"sentiment_clean": "正面"},
                ),
                evidence_input(
                    "ev_dup_2",
                    comment_id="c-dup-2",
                    comment_text_hash="sha256:comment:duplicate",
                    text_value="观赛画面流畅，不拖影。",
                ),
                evidence_input(
                    "ev_dup_3",
                    comment_id="c-dup-3",
                    comment_text_hash="sha256:comment:duplicate",
                    text_value="观赛画面流畅，不拖影。",
                ),
                evidence_input(
                    "ev_conflict",
                    evidence_type="comment_sentence",
                    evidence_field="comment_sentence:0",
                    comment_id="c-dup-1",
                    comment_text_hash="sha256:comment:duplicate",
                    segment_text_hash="sha256:sentence:conflict",
                    sentence_seq=0,
                    text_value="偶尔拖影",
                    payload={"sentiment_clean": "负面"},
                ),
            ]
        )
    )

    by_comment_id = {record.comment_id: record for record in result.records}
    assert by_comment_id["c-dup-1"].sentiment_hint == "conflict"
    assert by_comment_id["c-dup-1"].sentiment_conflict_flag is True
    for record in result.records:
        assert "template_duplicate" in record.low_value_reasons
        assert record.comment_unit_status == "low_value"


def test_comment_unit_builder_skips_untraceable_input_without_future_outputs():
    result = CommentUnitBuilder().build_units(
        bundle(
            [
                evidence_input(
                    "ev_no_trace",
                    comment_id=None,
                    comment_text_hash=None,
                    source_row_id="",
                    text_value="画质很好",
                )
            ]
        )
    )

    assert result.records == []
    assert result.candidates == []
    assert result.skipped_evidence_ids == ["ev_no_trace"]
    assert len(result.issues) == 1
    assert result.issues[0].issue_code == "m05_unit_missing_trace"
    assert result.issues[0].blocked is True


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
