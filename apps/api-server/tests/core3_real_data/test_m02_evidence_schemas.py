from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.core3_real_data import (
    ConfidenceLevel,
    EvidenceAtomListItem,
    EvidenceAtomRead,
    EvidenceCounts,
    EvidenceGrain,
    EvidenceInactiveReason,
    EvidenceLinkRead,
    EvidenceLinkStatus,
    EvidenceLinkType,
    EvidenceRunRequest,
    EvidenceRunResult,
    EvidenceStatus,
    EvidenceSummary,
    EvidenceTraceResponse,
    EvidenceType,
    SkuEvidenceQuery,
    SkuEvidenceResponse,
)
from app.services.core3_real_data.constants import (
    CORE3_M02_CONFIDENCE_RULE_VERSION,
    CORE3_M02_EVIDENCE_VERSION,
    CORE3_M02_MODULE_VERSION,
    Core3RunStatus,
)


def _atom_kwargs() -> dict:
    return {
        "evidence_id": "m02ev_001",
        "evidence_key": "sha256:m02_evidence_key:param",
        "project_id": "core3_mvp",
        "batch_id": "m00_202606130001",
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "brand_name": "海信",
        "evidence_type": EvidenceType.PARAM_RAW,
        "evidence_grain": EvidenceGrain.FIELD,
        "evidence_field": "clean_attr_value",
        "evidence_title": "刷新率参数原始证据",
        "source_table": "attribute_data",
        "source_pk": "123",
        "source_row_id": "attribute_data:123",
        "source_row_hash": "sha256:m00_row_hash_v1:source",
        "clean_table": "core3_clean_attribute",
        "clean_record_key": "attribute:attribute_data:123",
        "clean_hash": "sha256:m01_clean_hash_v1:attr",
        "clean_version": "m01_clean_v1",
        "raw_field": "参数值",
        "raw_value": "144Hz",
        "clean_field": "刷新率",
        "clean_value": "144Hz",
        "value_presence": "present",
        "numeric_value": Decimal("144.0000"),
        "numeric_values_json": [{"value": 144, "unit": "Hz"}],
        "unit_value": "Hz",
        "text_value": "144Hz",
        "text_hash": "sha256:text:144hz",
        "quality_status": "ok",
        "base_confidence": Decimal("0.9000"),
        "confidence_level": ConfidenceLevel.HIGH,
        "evidence_payload_json": {"clean_attr_name": "刷新率", "clean_attr_value": "144Hz"},
        "created_at": "2026-06-13T00:00:00Z",
        "updated_at": "2026-06-13T00:00:01Z",
    }


def _list_item() -> EvidenceAtomListItem:
    return EvidenceAtomListItem(
        evidence_id="m02ev_001",
        evidence_key="sha256:m02_evidence_key:param",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        evidence_type=EvidenceType.PARAM_RAW,
        evidence_grain=EvidenceGrain.FIELD,
        evidence_field="clean_attr_value",
        evidence_title="刷新率参数原始证据",
        clean_table="core3_clean_attribute",
        clean_record_key="attribute:attribute_data:123",
        source_row_id="attribute_data:123",
        base_confidence=Decimal("0.9000"),
        confidence_level=ConfidenceLevel.HIGH,
        created_at="2026-06-13T00:00:00Z",
    )


def test_m02_evidence_enums_match_sop_contract():
    assert [item.value for item in EvidenceType] == [
        "sku_fact",
        "market_fact",
        "param_raw",
        "promo_raw",
        "promo_sentence",
        "comment_raw",
        "comment_sentence",
        "comment_dimension",
        "quality_issue",
    ]
    assert [item.value for item in EvidenceGrain] == ["sku", "row", "field", "sentence", "dimension", "quality"]
    assert [item.value for item in EvidenceStatus] == ["current", "inactive", "superseded", "skipped"]
    assert {item.value for item in EvidenceInactiveReason} >= {
        "clean_record_inactive",
        "quality_issue_resolved",
        "superseded_by_clean_hash",
    }
    assert [item.value for item in EvidenceLinkType] == [
        "same_source_row",
        "same_clean_record",
        "has_sentence",
        "has_dimension",
        "has_quality_issue",
        "same_comment",
        "same_comment_text",
        "same_segment",
        "supersedes",
    ]
    assert [item.value for item in EvidenceLinkStatus] == ["current", "inactive", "superseded"]
    assert [item.value for item in ConfidenceLevel] == ["high", "medium", "low", "unknown"]


def test_evidence_run_request_defaults_to_m02_versions():
    request = EvidenceRunRequest(project_id="core3_mvp", batch_id="m00_202606130001")

    assert request.model_dump() == {
        "project_id": "core3_mvp",
        "batch_id": "m00_202606130001",
        "category_code": "TV",
        "run_id": None,
        "module_run_id": None,
        "mode": "incremental",
        "module_version": CORE3_M02_MODULE_VERSION,
        "evidence_version": CORE3_M02_EVIDENCE_VERSION,
        "confidence_rule_version": CORE3_M02_CONFIDENCE_RULE_VERSION,
        "target_sku_codes": [],
        "include_inactive_clean_records": False,
        "force_rebuild": False,
        "triggered_by": "system",
    }

    with pytest.raises(ValidationError):
        EvidenceRunRequest(project_id="", batch_id="m00_202606130001")
    with pytest.raises(ValidationError, match="target_sku_codes"):
        EvidenceRunRequest(project_id="core3_mvp", batch_id="m00_202606130001", target_sku_codes=[""])


def test_evidence_counts_summary_and_run_result_validate_contracts():
    counts = EvidenceCounts(
        param_raw=81,
        comment_raw=3621,
        current=3702,
        by_type={EvidenceType.PARAM_RAW.value: 81, EvidenceType.COMMENT_RAW.value: 3621},
        by_status={EvidenceStatus.CURRENT.value: 3702},
        by_confidence_level={ConfidenceLevel.HIGH.value: 81, ConfidenceLevel.MEDIUM.value: 3621},
    )
    summary = EvidenceSummary(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        evidence_counts=counts,
        source_clean_tables=["core3_clean_attribute", "core3_clean_comment"],
        missing_clean_tables=["core3_clean_claim"],
        quality_summary_cn="参数和评论证据已生成，卖点清洗表暂无可用记录。",
    )
    result = EvidenceRunResult(
        batch_id="m00_202606130001",
        status=Core3RunStatus.SUCCESS,
        evidence_counts=counts,
        summary=summary,
    )

    payload = result.model_dump()
    assert payload["module_code"] == "M02"
    assert payload["evidence_counts"]["by_type"]["param_raw"] == 81
    assert payload["summary"]["missing_clean_tables"] == ["core3_clean_claim"]

    with pytest.raises(ValidationError):
        EvidenceCounts(param_raw=-1)
    with pytest.raises(ValidationError, match="unknown evidence_type"):
        EvidenceCounts(by_type={"task_profile": 1})
    with pytest.raises(ValidationError, match="negative count"):
        EvidenceCounts(by_status={"current": -1})
    with pytest.raises(ValidationError, match="unknown clean_table"):
        EvidenceSummary(
            project_id="core3_mvp",
            batch_id="m00_202606130001",
            source_clean_tables=["core3_future_profile"],
        )


def test_evidence_atom_read_preserves_source_and_clean_trace_contract():
    atom = EvidenceAtomRead(**_atom_kwargs())

    payload = atom.model_dump()
    assert payload["evidence_type"] == "param_raw"
    assert payload["evidence_grain"] == "field"
    assert payload["confidence_level"] == "high"
    assert payload["source_table"] == "attribute_data"
    assert payload["clean_table"] == "core3_clean_attribute"
    assert payload["raw_value"] == "144Hz"
    assert payload["evidence_payload_json"]["clean_attr_name"] == "刷新率"

    with pytest.raises(ValidationError, match="unknown source_table"):
        EvidenceAtomRead(**{**_atom_kwargs(), "source_table": "raw_business_score"})
    with pytest.raises(ValidationError, match="unknown clean_table"):
        EvidenceAtomRead(**{**_atom_kwargs(), "clean_table": "core3_business_profile"})
    with pytest.raises(ValidationError):
        EvidenceAtomRead(**{**_atom_kwargs(), "base_confidence": Decimal("1.2")})


def test_evidence_list_item_keeps_m02_boundary_without_business_outputs():
    item = _list_item()
    payload = item.model_dump()

    assert payload["evidence_type"] == "param_raw"
    assert payload["base_confidence"] == Decimal("0.9000")
    assert "raw_value" not in payload
    assert "clean_value" not in payload
    assert "text_value" not in payload
    assert "evidence_payload_json" not in payload
    assert "task_scores" not in payload
    assert "battlefield_scores" not in payload
    assert "competitor_sku_code" not in payload
    assert "report_content" not in payload

    with pytest.raises(ValidationError):
        EvidenceAtomListItem(**{**payload, "task_scores": []})


def test_sku_evidence_query_response_link_and_trace_contracts():
    item = _list_item()
    link = EvidenceLinkRead(
        link_id="m02link_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        from_evidence_id="m02ev_comment",
        to_evidence_id="m02ev_sentence",
        from_evidence_key="sha256:m02_evidence_key:comment",
        to_evidence_key="sha256:m02_evidence_key:sentence",
        link_type=EvidenceLinkType.HAS_SENTENCE,
        confidence=Decimal("1.0000"),
        created_at="2026-06-13T00:00:02Z",
        updated_at="2026-06-13T00:00:03Z",
    )
    query = SkuEvidenceQuery(
        project_id="core3_mvp",
        sku_code="TV00029115",
        evidence_types=[EvidenceType.PARAM_RAW],
        min_confidence=Decimal("0.5"),
    )
    response = SkuEvidenceResponse(query=query, items=[item], links=[link], total=1, limit=100, offset=0)
    trace = EvidenceTraceResponse(
        evidence=EvidenceAtomRead(**_atom_kwargs()),
        downstream_links=[link],
        related_evidence=[item],
        trace_summary_cn="该证据来自属性清洗表，可回溯到原始参数行。",
    )

    assert query.model_dump()["evidence_statuses"] == ["current"]
    assert response.model_dump()["links"][0]["link_type"] == "has_sentence"
    assert trace.model_dump()["evidence"]["evidence_id"] == "m02ev_001"

    with pytest.raises(ValidationError):
        SkuEvidenceQuery(project_id="core3_mvp", sku_code="TV00029115", evidence_types=["task_profile"])
    with pytest.raises(ValidationError):
        SkuEvidenceQuery(project_id="core3_mvp", sku_code="TV00029115", limit=0)
    with pytest.raises(ValidationError):
        EvidenceLinkRead(**{**link.model_dump(), "confidence": Decimal("1.5")})
