from __future__ import annotations

import pytest

from app.services.core3_real_data.analyst.competitor_profile_storage import (
    CompetitorProfileStorageCodecError,
    PAIR_EVIDENCE_DICTIONARY_CODEC,
    RELATION_FROM_PAIR_CODEC,
    decode_pair_payload,
    encode_pair_payload,
    is_relation_from_pair_pointer,
    relation_from_pair_pointer,
)
from tests.core3_real_data.test_competitor_profile_schemas import _pair


def test_pair_storage_codec_is_lossless_and_deterministic() -> None:
    payload = _pair().model_dump(mode="json")

    first = encode_pair_payload(payload)
    second = encode_pair_payload(dict(reversed(list(payload.items()))))

    assert first == second
    assert first["$codec"] == PAIR_EVIDENCE_DICTIONARY_CODEC
    assert first["evidence_dictionary"]
    assert decode_pair_payload(first) == payload
    assert encode_pair_payload(first) == first


def test_pair_storage_codec_preserves_repeated_evidence_by_reference() -> None:
    payload = _pair().model_dump(mode="json")
    repeated_ref = payload["evidence_refs"][0]
    payload["purchase_pool"]["evidence_refs"] = [repeated_ref]
    payload["purchase_pool"]["gate_results"][0]["evidence_refs"] = [
        repeated_ref
    ]

    encoded = encode_pair_payload(payload)

    assert encoded["evidence_dictionary"].count(repeated_ref) == 1
    assert decode_pair_payload(encoded) == payload


@pytest.mark.parametrize(
    "payload",
    [
        {"$codec": "unknown"},
        {
            "$codec": PAIR_EVIDENCE_DICTIONARY_CODEC,
            "result_hash": "result",
            "input_fingerprint": "input",
            "evidence_dictionary": [],
            "payload": {"result_hash": "result", "input_fingerprint": "input", "evidence_refs": [0]},
        },
    ],
)
def test_pair_storage_codec_rejects_unsupported_or_invalid_payloads(payload) -> None:
    with pytest.raises(CompetitorProfileStorageCodecError):
        decode_pair_payload(payload)


def test_relation_pointer_keeps_identity_and_hash() -> None:
    relation = _pair().relation_assessments[0].model_dump(mode="json")

    pointer = relation_from_pair_pointer(relation)

    assert pointer == {
        "$codec": RELATION_FROM_PAIR_CODEC,
        "relation_code": relation["relation_code"],
        "result_hash": relation["result_hash"],
    }
    assert is_relation_from_pair_pointer(pointer) is True
    assert is_relation_from_pair_pointer(relation) is False
