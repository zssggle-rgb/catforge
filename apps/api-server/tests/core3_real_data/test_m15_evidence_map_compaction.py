from types import SimpleNamespace

from app.services.core3_real_data.evidence_report_service import (
    _EvidenceRef,
    _referenced_evidence_ref_payloads,
)


def test_m15_short_evidence_map_keeps_only_card_references():
    evidence_map = {
        f"evidence-{index}": _EvidenceRef(
            short_ref=f"证据{index}",
            evidence_id=f"evidence-{index}",
            domain_cn="评论证据",
            title_cn="评论原始维度证据",
            source_cn="用户评论",
            snippet_cn=f"样例{index}",
        )
        for index in range(1, 6)
    }
    cards = [
        SimpleNamespace(
            short_evidence_refs_json=[
                {"short_ref": "证据2"},
                {"short_ref": "证据4"},
            ]
        )
    ]

    payload = _referenced_evidence_ref_payloads(evidence_map, cards)

    assert [item["short_ref"] for item in payload] == ["证据2", "证据4"]
    assert [item["evidence_id"] for item in payload] == ["evidence-2", "evidence-4"]
