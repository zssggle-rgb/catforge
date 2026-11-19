from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.constants import CORE3_TARGET_SKU_85E7Q

from .test_m01_no_business_outputs import make_client, make_session, register_m00_batch


FORBIDDEN_M02_BUSINESS_FIELDS = {
    "param_code",
    "claim_code",
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "candidate_id",
    "competitor_type",
    "component_scores",
    "selection_slot",
    "business_conclusion",
    "business_conclusion_cn",
    "report_payload",
    "report_content",
    "evidence_card",
}


def create_evidence_tables(session: Session) -> None:
    bind = session.get_bind()
    entities.Core3EvidenceAtom.__table__.create(bind=bind, checkfirst=True)
    entities.Core3EvidenceLink.__table__.create(bind=bind, checkfirst=True)


def run_85e7q_no_claim_m02_fixture() -> tuple[Session, str, dict[str, Any]]:
    session = make_session()
    create_evidence_tables(session)
    client = make_client(session)
    batch_id = register_m00_batch(client)
    m01_response = client.post(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/cleaning/run",
        json={"target_sku_codes": [CORE3_TARGET_SKU_85E7Q], "module_run_id": "module-run-m01-i"},
    )
    assert m01_response.status_code == 200
    assert m01_response.json()["summary_json"]["clean_counts"]["claim"] == 0
    assert m01_response.json()["summary_json"]["clean_counts"]["claim_sentence"] == 0

    m02_response = client.post(
        f"/api/mvp/core3/v2/projects/core3_mvp/batches/{batch_id}/evidence/run",
        json={"target_sku_codes": [CORE3_TARGET_SKU_85E7Q], "module_run_id": "module-run-m02-i"},
    )
    assert m02_response.status_code == 200
    return session, batch_id, m02_response.json()


def test_m02_85e7q_fixture_does_not_fabricate_promo_evidence_when_claim_source_missing():
    session, batch_id, m02_payload = run_85e7q_no_claim_m02_fixture()
    records = _evidence_records(session, batch_id)
    by_type = Counter(record.evidence_type for record in records)

    assert m02_payload["module_code"] == "M02"
    assert by_type == {
        "sku_fact": 1,
        "market_fact": 2,
        "param_raw": 6,
        "comment_raw": 2,
        "comment_sentence": 4,
        "comment_dimension": 2,
        "quality_issue": 5,
    }
    assert by_type["promo_raw"] == 0
    assert by_type["promo_sentence"] == 0
    assert m02_payload["summary_json"]["evidence_counts"]["by_type"].get("promo_raw") is None
    assert m02_payload["summary_json"]["evidence_counts"]["by_type"].get("promo_sentence") is None

    claim_quality = [
        record
        for record in records
        if record.evidence_type == "quality_issue"
        and record.evidence_payload_json.get("issue_type") == "claim_coverage_missing"
    ]
    assert len(claim_quality) == 1
    assert claim_quality[0].evidence_field == "quality_issue:claim:claim_coverage_missing"
    assert claim_quality[0].text_value == "结构化卖点数据缺失，不代表该 SKU 没有卖点"


def test_m02_outputs_stay_inside_raw_evidence_boundary():
    session, batch_id, m02_payload = run_85e7q_no_claim_m02_fixture()
    records = _evidence_records(session, batch_id)
    links = session.execute(select(entities.Core3EvidenceLink)).scalars().all()

    assert_no_m02_business_fields(m02_payload)
    assert links
    for record in records:
        assert_no_m02_business_fields(record.evidence_payload_json)
        assert record.evidence_type in {
            "sku_fact",
            "market_fact",
            "param_raw",
            "promo_raw",
            "promo_sentence",
            "comment_raw",
            "comment_sentence",
            "comment_dimension",
            "quality_issue",
        }
        assert not record.evidence_payload_json.keys() & FORBIDDEN_M02_BUSINESS_FIELDS
    for link in links:
        assert_no_m02_business_fields(link.link_payload_json)


def test_m02_quality_and_comment_dimension_are_not_promoted_to_business_facts():
    session, batch_id, _ = run_85e7q_no_claim_m02_fixture()
    records = _evidence_records(session, batch_id)
    quality_records = [record for record in records if record.evidence_type == "quality_issue"]
    dimension_records = [record for record in records if record.evidence_type == "comment_dimension"]

    assert quality_records
    assert dimension_records
    assert all(record.evidence_field.startswith("quality_issue:") for record in quality_records)
    assert all(record.evidence_field == "comment_dimension" for record in dimension_records)
    assert all("issue_type" in record.evidence_payload_json for record in quality_records)
    assert all(
        set(record.evidence_payload_json) <= {
            "dimension_path_raw",
            "dimension_quality_flag",
            "primary_dim_raw",
            "secondary_dim_raw",
            "third_dim_raw",
        }
        for record in dimension_records
    )
    assert_no_m02_business_fields([record.evidence_payload_json for record in quality_records + dimension_records])


def _evidence_records(session: Session, batch_id: str) -> list[entities.Core3EvidenceAtom]:
    return list(
        session.execute(
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.sku_code == CORE3_TARGET_SKU_85E7Q)
            .order_by(entities.Core3EvidenceAtom.evidence_type, entities.Core3EvidenceAtom.evidence_field)
        ).scalars()
    )


def assert_no_m02_business_fields(payload: Any) -> None:
    if isinstance(payload, dict):
        assert FORBIDDEN_M02_BUSINESS_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_m02_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_m02_business_fields(item)
