from decimal import Decimal

from app.services.core3_real_data.comment_domain_hint_service import CommentDomainHintService
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


def build_atoms(sku_bundle: M05SkuInputBundle):
    unit_result = CommentUnitBuilder().build_units(sku_bundle, run_id="run-m05", module_run_id="module-run-m05")
    assert len(unit_result.records) == 1
    atom_result = CommentSentenceAtomBuilder().build_atoms(sku_bundle, unit_result.records)
    assert atom_result.records
    return atom_result.records


def test_domain_hint_service_sets_product_experience_from_text_and_dimension():
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
            evidence_input(
                "ev_dimension",
                evidence_type="comment_dimension",
                evidence_field="comment_dimension",
                dimension_path_raw="产品体验/游戏流畅",
                text_value="游戏流畅",
            ),
        ]
    )
    atom = build_atoms(sku_bundle)[0]
    result = CommentDomainHintService().apply_domain_hints([atom])

    enriched = result.records[0]
    assert enriched.primary_domain_hint == "product_experience"
    assert enriched.domain_conflict_flag is False
    assert enriched.result_hash != atom.result_hash
    assert result.unknown_count == 0
    product_hint = {hint.domain_hint: hint for hint in enriched.domain_hints}["product_experience"]
    assert set(product_hint.source_terms) >= {"游戏", "延迟"}
    assert product_hint.source_dimension_paths == ["产品体验/游戏流畅"]
    assert product_hint.confidence >= Decimal("0.7000")
    assert_no_forbidden_business_fields(enriched.model_dump())


def test_domain_hint_service_isolates_service_only_sentence_as_service_domain():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_service",
                comment_id="c-service",
                comment_text_hash="sha256:comment:service",
                text_value="安装师傅服务很好。",
            )
        ]
    )
    atom = build_atoms(sku_bundle)[0]
    result = CommentDomainHintService().apply_domain_hints([atom])

    enriched = result.records[0]
    assert enriched.primary_domain_hint == "service_experience"
    assert {hint.domain_hint for hint in enriched.domain_hints} >= {"service_experience", "logistics_installation"}
    assert result.service_only_count == 1
    assert enriched.low_value_flag is True
    assert enriched.usable_for_downstream is False


def test_domain_hint_service_keeps_product_primary_when_service_is_secondary():
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
    atom = build_atoms(sku_bundle)[0]
    result = CommentDomainHintService().apply_domain_hints([atom])

    enriched = result.records[0]
    assert enriched.primary_domain_hint == "product_experience"
    assert {hint.domain_hint for hint in enriched.domain_hints} >= {"product_experience", "logistics_installation"}
    assert enriched.domain_conflict_flag is False


def test_domain_hint_service_flags_text_dimension_conflict():
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_raw",
                text_value="画质清晰，色彩很好。",
            ),
            evidence_input(
                "ev_dimension",
                evidence_type="comment_dimension",
                evidence_field="comment_dimension",
                dimension_path_raw="售后服务/安装服务",
                text_value="安装服务",
            ),
        ]
    )
    atom = build_atoms(sku_bundle)[0]
    result = CommentDomainHintService().apply_domain_hints([atom])

    enriched = result.records[0]
    assert enriched.primary_domain_hint == "product_experience"
    assert enriched.domain_conflict_flag is True
    assert result.domain_conflict_count == 1
    assert {hint.domain_hint for hint in enriched.domain_hints} >= {"product_experience", "service_experience"}


def test_domain_hint_service_marks_unknown_without_creating_future_module_outputs():
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
    atom = build_atoms(sku_bundle)[0]
    result = CommentDomainHintService().apply_domain_hints([atom])

    enriched = result.records[0]
    assert enriched.primary_domain_hint == "unknown"
    assert [hint.domain_hint for hint in enriched.domain_hints] == ["unknown"]
    assert result.unknown_count == 1
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
