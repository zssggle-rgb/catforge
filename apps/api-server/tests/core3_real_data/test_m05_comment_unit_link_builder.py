from decimal import Decimal

from app.services.core3_real_data.comment_evidence_schemas import M05EvidenceInput, M05SkuInputBundle
from app.services.core3_real_data.comment_unit_builder import CommentUnitBuilder
from app.services.core3_real_data.comment_unit_link_builder import CommentUnitLinkBuilder


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


def build_standard_bundle_and_unit():
    inputs = [
        evidence_input("ev_raw", text_value="画质很好，游戏模式延迟低。"),
        evidence_input(
            "ev_sentence",
            evidence_type="comment_sentence",
            evidence_field="comment_sentence:0",
            segment_text_hash="sha256:sentence:001",
            sentence_seq=0,
            text_value="游戏模式延迟低",
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
            payload={"issue_type": "comment_dimension_missing"},
        ),
    ]
    sku_bundle = bundle(inputs)
    unit_result = CommentUnitBuilder().build_units(
        sku_bundle,
        run_id="run-m05",
        module_run_id="module-run-m05",
    )
    assert len(unit_result.records) == 1
    return sku_bundle, unit_result.records[0]


def test_comment_unit_link_builder_maps_all_source_types_to_business_roles():
    sku_bundle, unit = build_standard_bundle_and_unit()
    result = CommentUnitLinkBuilder().build_links(sku_bundle, [unit])

    assert len(result.records) == 4
    by_role = {record.link_role: record for record in result.records}
    assert set(by_role) == {"raw_source", "sentence_source", "dimension_weak_label", "quality_flag"}

    raw = by_role["raw_source"]
    assert raw.source_evidence_id == "ev_raw"
    assert raw.source_evidence_type == "comment_raw"
    assert raw.comment_id == "c-001"
    assert raw.comment_text_hash == "sha256:comment:001"
    assert raw.sentence_hash is None
    assert raw.dimension_path_raw is None
    assert raw.quality_issue_type is None

    sentence = by_role["sentence_source"]
    assert sentence.source_evidence_id == "ev_sentence"
    assert sentence.source_evidence_type == "comment_sentence"
    assert sentence.sentence_hash == "sha256:sentence:001"

    dimension = by_role["dimension_weak_label"]
    assert dimension.source_evidence_id == "ev_dimension"
    assert dimension.source_evidence_type == "comment_dimension"
    assert dimension.dimension_path_raw == "产品体验/游戏流畅"

    quality = by_role["quality_flag"]
    assert quality.source_evidence_id == "ev_quality"
    assert quality.source_evidence_type == "quality_issue"
    assert quality.quality_issue_type == "comment_dimension_missing"
    assert result.skipped_evidence_ids == []
    assert result.review_required_count == 0
    for record in result.records:
        assert record.comment_unit_id == unit.comment_unit_id
        assert record.input_fingerprint == "sha256:m05:input"
        assert record.review_status == "auto_pass"
        assert_no_forbidden_business_fields(record.model_dump())


def test_comment_unit_link_builder_is_idempotent_for_duplicate_units_and_source_ids():
    sku_bundle, unit = build_standard_bundle_and_unit()
    duplicated_unit = unit.model_copy(
        update={
            "source_comment_evidence_ids": ["ev_raw", "ev_raw"],
            "source_sentence_evidence_ids": ["ev_sentence", "ev_sentence"],
        }
    )
    result = CommentUnitLinkBuilder().build_links(sku_bundle, [duplicated_unit, duplicated_unit])

    assert len(result.records) == 4
    assert [(record.source_evidence_id, record.link_role) for record in result.records] == [
        ("ev_raw", "raw_source"),
        ("ev_sentence", "sentence_source"),
        ("ev_dimension", "dimension_weak_label"),
        ("ev_quality", "quality_flag"),
    ]


def test_comment_unit_link_builder_skips_missing_source_evidence():
    sku_bundle, unit = build_standard_bundle_and_unit()
    unit_with_missing_source = unit.model_copy(
        update={"source_comment_evidence_ids": ["ev_raw", "ev_missing"]}
    )
    result = CommentUnitLinkBuilder().build_links(sku_bundle, [unit_with_missing_source])

    assert len(result.records) == 4
    assert result.skipped_evidence_ids == ["ev_missing"]
    assert len(result.issues) == 1
    assert result.issues[0].issue_code == "m05_link_missing_source_evidence"
    assert result.issues[0].comment_unit_id == unit.comment_unit_id
    assert result.issues[0].blocked is False


def test_comment_unit_link_builder_skips_role_type_mismatch_without_crossing_m05_boundary():
    sku_bundle, unit = build_standard_bundle_and_unit()
    mismatched_unit = unit.model_copy(
        update={
            "source_comment_evidence_ids": ["ev_sentence"],
            "source_sentence_evidence_ids": [],
        }
    )
    result = CommentUnitLinkBuilder().build_links(sku_bundle, [mismatched_unit])

    assert [record.source_evidence_id for record in result.records] == ["ev_dimension", "ev_quality"]
    assert result.skipped_evidence_ids == ["ev_sentence"]
    assert len(result.issues) == 1
    assert result.issues[0].issue_code == "m05_link_evidence_role_mismatch"
    for record in result.records:
        assert_no_forbidden_business_fields(record.model_dump())


def test_comment_unit_link_builder_inherits_review_state_from_source_unit():
    inputs = [
        evidence_input(
            "ev_source_row_fallback",
            comment_id=None,
            comment_text_hash=None,
            source_row_id="comment_data:fallback",
            text_value="接口丰富，连接游戏主机方便。",
        )
    ]
    sku_bundle = bundle(inputs)
    unit = CommentUnitBuilder().build_units(sku_bundle).records[0]
    result = CommentUnitLinkBuilder().build_links(sku_bundle, [unit])

    assert len(result.records) == 1
    link = result.records[0]
    assert link.link_role == "raw_source"
    assert link.review_required is True
    assert link.review_status == "review_required"
    assert link.review_reason_json["reason_codes"] == ["source_unit_review_required"]
    assert result.review_required_count == 1


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
