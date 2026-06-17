from decimal import Decimal

import pytest

from app.services.core3_real_data.constants import (
    CORE3_M02_CLEAN_SOURCE_TABLES,
    CORE3_M02_EVIDENCE_VERSION,
    Core3CategoryCode,
    Core3EvidenceGrain,
    Core3EvidenceType,
)
from app.services.core3_real_data.evidence_mappers import (
    EvidenceIdService,
    EvidenceMapper,
    EvidenceMappingError,
    M02_EVIDENCE_MAPPING_RULES,
)


BASE_RECORD = {
    "project_id": "core3_mvp",
    "category_code": "TV",
    "batch_id": "m00_202606130001",
    "run_id": "run_001",
    "module_run_id": "module_run_m01",
    "sku_code": "TV00029115",
    "model_name": "85E7Q",
    "brand_name": "海信",
    "source_table": "attribute_data",
    "source_pk": "123",
    "source_row_id": "attribute_data:123",
    "source_row_hash": "sha256:m00_row_hash_v1:source",
    "clean_record_key": "attribute:attribute_data:123",
    "clean_hash": "sha256:m01_clean_hash_v1:attr",
    "clean_version": "m01_clean_v1",
    "quality_status": "ok",
    "quality_flags": [],
}


def test_evidence_id_service_keeps_key_stable_and_versions_id_by_clean_hash():
    service = EvidenceIdService()
    key = service.build_evidence_key(
        project_id="core3_mvp",
        category_code=Core3CategoryCode.TV,
        evidence_type=Core3EvidenceType.PARAM_RAW,
        clean_table="core3_clean_attribute",
        clean_record_key="attribute:attribute_data:123",
        evidence_field="刷新率",
    )
    same_key = service.build_evidence_key(
        project_id="core3_mvp",
        category_code="TV",
        evidence_type="param_raw",
        clean_table="core3_clean_attribute",
        clean_record_key="attribute:attribute_data:123",
        evidence_field="刷新率",
    )
    first_id = service.build_evidence_id(
        evidence_key=key,
        clean_hash="sha256:m01_clean_hash_v1:old",
        source_row_hash="sha256:m00_row_hash_v1:source",
    )
    changed_clean_hash_id = service.build_evidence_id(
        evidence_key=key,
        clean_hash="sha256:m01_clean_hash_v1:new",
        source_row_hash="sha256:m00_row_hash_v1:source",
    )

    assert key == same_key
    assert key.startswith(f"sha256:{CORE3_M02_EVIDENCE_VERSION}_key:")
    assert first_id.startswith(f"sha256:{CORE3_M02_EVIDENCE_VERSION}_id:")
    assert first_id != changed_clean_hash_id


def test_evidence_id_service_preserves_source_hash_missing_like_values_as_distinct():
    service = EvidenceIdService()
    key = service.build_evidence_key(
        project_id="core3_mvp",
        category_code="TV",
        evidence_type="comment_raw",
        clean_table="core3_clean_comment",
        clean_record_key="comment:comment_data:1",
        evidence_field="comment_raw",
    )

    none_source = service.build_evidence_id(
        evidence_key=key,
        clean_hash="sha256:m01_clean_hash_v1:comment",
        source_row_hash=None,
    )
    empty_source = service.build_evidence_id(
        evidence_key=key,
        clean_hash="sha256:m01_clean_hash_v1:comment",
        source_row_hash="",
    )
    dash_source = service.build_evidence_id(
        evidence_key=key,
        clean_hash="sha256:m01_clean_hash_v1:comment",
        source_row_hash="-",
    )

    assert len({none_source, empty_source, dash_source}) == 3


def test_evidence_mapper_has_complete_sop_mapping_rules_without_business_outputs():
    assert set(M02_EVIDENCE_MAPPING_RULES) == set(CORE3_M02_CLEAN_SOURCE_TABLES)
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_sku"].evidence_type == Core3EvidenceType.SKU_FACT
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_market_weekly"].evidence_type == Core3EvidenceType.MARKET_FACT
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_attribute"].evidence_type == Core3EvidenceType.PARAM_RAW
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_claim"].evidence_type == Core3EvidenceType.PROMO_RAW
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_claim_sentence"].evidence_type == Core3EvidenceType.PROMO_SENTENCE
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_comment"].evidence_type == Core3EvidenceType.COMMENT_RAW
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_comment_sentence"].evidence_type == Core3EvidenceType.COMMENT_SENTENCE
    assert M02_EVIDENCE_MAPPING_RULES["core3_clean_comment_dimension"].evidence_type == Core3EvidenceType.COMMENT_DIMENSION
    assert M02_EVIDENCE_MAPPING_RULES["core3_data_quality_issue"].evidence_type == Core3EvidenceType.QUALITY_ISSUE

    business_terms = {"task", "target_group", "battlefield", "competitor", "score", "report"}
    for rule in M02_EVIDENCE_MAPPING_RULES.values():
        assert not business_terms.intersection(rule.evidence_type.value.split("_"))
        assert not business_terms.intersection(rule.default_evidence_field.split("_"))


def test_mapper_maps_attribute_record_to_param_raw_draft_with_ids():
    mapper = EvidenceMapper()
    record = {
        **BASE_RECORD,
        "raw_attr_name": "刷新率",
        "clean_attr_name": "刷新率",
        "raw_attr_value": "144Hz",
        "clean_attr_value": "144Hz",
        "value_presence": "present",
        "value_number_candidates": [{"value": 144, "unit": "Hz"}],
        "value_unit_candidates": ["Hz"],
    }

    draft = mapper.map_clean_record(record, clean_table="core3_clean_attribute")
    payload = draft.to_base_payload()

    assert draft.evidence_type == Core3EvidenceType.PARAM_RAW
    assert draft.evidence_grain == Core3EvidenceGrain.FIELD
    assert draft.evidence_field == "刷新率"
    assert draft.raw_field == "刷新率"
    assert draft.raw_value == "144Hz"
    assert draft.clean_field == "刷新率"
    assert draft.clean_value == "144Hz"
    assert draft.value_presence == "present"
    assert draft.unit_value == "Hz"
    assert draft.evidence_key.startswith(f"sha256:{CORE3_M02_EVIDENCE_VERSION}_key:")
    assert draft.evidence_id.startswith(f"sha256:{CORE3_M02_EVIDENCE_VERSION}_id:")
    assert payload["evidence_type"] == "param_raw"
    assert payload["numeric_values_json"] == [{"value": 144, "unit": "Hz"}]


def test_mapper_keeps_evidence_key_stable_when_clean_hash_changes():
    mapper = EvidenceMapper()
    first = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "raw_attr_name": "刷新率",
            "clean_attr_name": "刷新率",
            "raw_attr_value": "144Hz",
            "clean_attr_value": "144Hz",
        },
        clean_table="core3_clean_attribute",
    )
    changed_clean = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "raw_attr_name": "刷新率",
            "clean_attr_name": "刷新率",
            "raw_attr_value": "144Hz",
            "clean_attr_value": "165Hz",
            "clean_hash": "sha256:m01_clean_hash_v1:attr_changed",
        },
        clean_table="core3_clean_attribute",
    )

    assert first.evidence_key == changed_clean.evidence_key
    assert first.evidence_id != changed_clean.evidence_id


def test_mapper_maps_comment_sentence_and_quality_issue_without_business_conclusions():
    mapper = EvidenceMapper()
    sentence = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "source_table": "comment_data",
            "source_pk": "456",
            "source_row_id": "comment_data:456",
            "clean_record_key": "comment_sentence:comment_data:456:segment:1",
            "clean_hash": "sha256:m01_clean_hash_v1:sentence",
            "comment_id": "cmt-001",
            "sentence_source": "segment",
            "sentence_seq": 1,
            "sentence_text": "打游戏很流畅",
            "sentence_text_hash": "sha256:text:game",
        },
        clean_table="core3_clean_comment_sentence",
    )
    issue = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "source_clean_table": "core3_data_quality_issue",
            "source_table": "selling_points_data",
            "source_row_id": "selling_points_data:789",
            "clean_record_key": "quality:claim_coverage_missing:TV00029115",
            "clean_hash": "sha256:m01_clean_hash_v1:issue",
            "domain": "claim",
            "issue_type": "claim_coverage_missing",
            "severity": "warning",
            "issue_detail": "缺少结构化卖点来源",
            "suggested_downstream_action": "M04a 不得伪造卖点事实",
            "clean_table": "core3_clean_sku",
        },
    )

    assert sentence.evidence_type == Core3EvidenceType.COMMENT_SENTENCE
    assert sentence.evidence_grain == Core3EvidenceGrain.SENTENCE
    assert sentence.evidence_field == "comment_sentence:segment:1"
    assert sentence.text_value == "打游戏很流畅"
    assert issue.clean_table == "core3_data_quality_issue"
    assert issue.evidence_type == Core3EvidenceType.QUALITY_ISSUE
    assert issue.evidence_field == "quality_issue:claim:claim_coverage_missing"
    assert issue.clean_value == "缺少结构化卖点来源"
    assert "task" not in issue.to_base_payload()
    assert "battlefield" not in issue.to_base_payload()
    assert "competitor_sku_code" not in issue.to_base_payload()


def test_mapper_maps_market_row_with_numeric_and_channel_fields():
    mapper = EvidenceMapper()
    draft = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "source_table": "week_sales_data",
            "source_pk": "222",
            "source_row_id": "week_sales_data:222",
            "clean_record_key": "market:week_sales_data:222",
            "clean_hash": "sha256:m01_clean_hash_v1:market",
            "period_raw": "2026W01",
            "period_week_index": 1,
            "channel_type": "线上",
            "platform_type": "京东",
            "sales_volume": Decimal("12.0000"),
            "sales_amount": Decimal("95988.0000"),
            "avg_price": Decimal("7999.0000"),
        },
        clean_table="core3_clean_market_weekly",
    )

    assert draft.evidence_type == Core3EvidenceType.MARKET_FACT
    assert draft.evidence_grain == Core3EvidenceGrain.ROW
    assert draft.evidence_field == "market_weekly"
    assert draft.numeric_value == Decimal("7999.0000")
    assert draft.period_raw == "2026W01"
    assert draft.channel_type == "线上"
    assert draft.platform_type == "京东"
    assert draft.numeric_values_json == [
        {"field": "sales_volume", "value": Decimal("12.0000")},
        {"field": "sales_amount", "value": Decimal("95988.0000")},
        {"field": "avg_price", "value": Decimal("7999.0000")},
    ]


def test_mapper_rejects_unknown_or_incomplete_records():
    mapper = EvidenceMapper()

    with pytest.raises(EvidenceMappingError, match="clean_table is required"):
        mapper.map_clean_record({**BASE_RECORD})
    with pytest.raises(EvidenceMappingError, match="unknown clean_table"):
        mapper.map_clean_record({**BASE_RECORD}, clean_table="core3_future_profile")
    with pytest.raises(EvidenceMappingError, match="unknown source_table"):
        mapper.map_clean_record({**BASE_RECORD, "source_table": "raw_business_score"}, clean_table="core3_clean_attribute")
    with pytest.raises(EvidenceMappingError, match="clean_hash is required"):
        mapper.map_clean_record({**BASE_RECORD, "clean_hash": ""}, clean_table="core3_clean_attribute")
