from decimal import Decimal

from app.services.core3_real_data.comment_evidence_schemas import M05EvidenceInput, M05SkuInputBundle
from app.services.core3_real_data.comment_sentence_atom_builder import CommentSentenceAtomBuilder
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


def build_unit(sku_bundle: M05SkuInputBundle):
    unit_result = CommentUnitBuilder().build_units(
        sku_bundle,
        run_id="run-m05",
        module_run_id="module-run-m05",
    )
    assert len(unit_result.records) == 1
    return unit_result.records[0]


def test_sentence_atom_builder_uses_system_split_and_merges_same_sentence_hash():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="画质清晰，游戏模式延迟低。", payload={"sentiment_clean": "正面"}),
            evidence_input(
                "ev_sentence_a",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:game",
                sentence_seq=0,
                text_value="游戏模式延迟低",
            ),
            evidence_input(
                "ev_sentence_b",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:game",
                sentence_seq=0,
                text_value="游戏模式延迟很低",
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
    )
    unit = build_unit(sku_bundle)
    result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, [unit])

    assert len(result.records) == 1
    atom = result.records[0]
    assert atom.sentence_source_priority == "system_split"
    assert atom.sentence_hash == "sha256:sentence:game"
    assert atom.sentence_text == "游戏模式延迟很低"
    assert atom.source_sentence_evidence_ids == ["ev_sentence_a", "ev_sentence_b"]
    assert atom.source_comment_evidence_ids == ["ev_raw"]
    assert atom.source_dimension_evidence_ids == ["ev_dimension"]
    assert atom.source_quality_evidence_ids == ["ev_quality"]
    assert atom.raw_dimension_paths == ["产品体验/游戏流畅"]
    assert atom.primary_domain_hint == "unknown"
    assert atom.sentiment_source == "raw_only"
    assert atom.usable_for_downstream is True
    assert atom.specificity_score >= Decimal("0.7000")
    assert result.usable_for_downstream_count == 1
    assert result.raw_fallback_count == 0
    assert_no_forbidden_business_fields(atom.model_dump())


def test_sentence_atom_builder_uses_source_segment_priority_when_payload_marks_raw_segments():
    sku_bundle = bundle(
        [
            evidence_input("ev_raw", text_value="看球赛很流畅，不拖影。"),
            evidence_input(
                "ev_segment",
                evidence_type="comment_sentence",
                evidence_field="comment_segment:0",
                segment_text_hash="sha256:sentence:sport",
                sentence_seq=0,
                text_value="看球赛很流畅，不拖影",
                payload={"source": "comments_segments"},
            ),
        ]
    )
    unit = build_unit(sku_bundle)
    result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, [unit])

    assert len(result.records) == 1
    assert result.records[0].sentence_source_priority == "source_segment"
    assert result.records[0].review_required is False
    assert result.records[0].usable_for_downstream is True


def test_sentence_atom_builder_falls_back_to_raw_text_when_sentence_evidence_missing():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_raw_only",
                text_value="画质清晰。游戏模式延迟低。",
            )
        ]
    )
    unit = build_unit(sku_bundle)
    result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, [unit])

    assert [atom.sentence_text for atom in result.records] == ["画质清晰", "游戏模式延迟低"]
    assert [atom.sentence_source_priority for atom in result.records] == ["raw_fallback", "raw_fallback"]
    assert [atom.source_sentence_evidence_ids for atom in result.records] == [[], []]
    assert [atom.source_comment_evidence_ids for atom in result.records] == [["ev_raw_only"], ["ev_raw_only"]]
    assert result.raw_fallback_count == 2
    assert result.review_required_count == 2
    for atom in result.records:
        assert atom.review_status == "review_required"
        assert atom.review_reason_json["reason_codes"] == ["raw_fallback_sentence"]


def test_sentence_atom_builder_blocks_low_value_generic_sentence_for_downstream():
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
    unit = build_unit(sku_bundle)
    result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, [unit])

    assert len(result.records) == 1
    atom = result.records[0]
    assert atom.low_value_flag is True
    assert "too_short_generic" in atom.low_value_reasons
    assert atom.usable_for_downstream is False
    assert atom.downstream_block_reasons == ["low_value_sentence"]
    assert atom.confidence <= Decimal("0.3500")
    assert result.low_value_count == 1
    assert result.usable_for_downstream_count == 0


def test_sentence_atom_builder_reports_missing_text_without_generating_future_outputs():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_empty",
                comment_id="c-empty",
                comment_text_hash="sha256:comment:empty",
                text_value="",
            )
        ]
    )
    unit_result = CommentUnitBuilder().build_units(sku_bundle)
    assert len(unit_result.records) == 1
    result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, unit_result.records)

    assert result.records == []
    assert result.candidates == []
    assert len(result.issues) == 1
    assert result.issues[0].issue_code == "m05_sentence_missing_text"
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
