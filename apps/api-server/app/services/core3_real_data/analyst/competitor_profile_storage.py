"""Compact, lossless storage codecs for competitor-profile payloads.

The public typed contracts remain unchanged.  These helpers only reduce repeated
evidence dictionaries inside persisted JSONB values and let relation index rows
refer to the canonical relation already stored in their parent pair payload.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


PAIR_EVIDENCE_DICTIONARY_CODEC = "competitor_profile_pair_evidence_dictionary_v1"
RELATION_FROM_PAIR_CODEC = "competitor_profile_relation_from_pair_v1"
_CODEC_KEY = "$codec"


class CompetitorProfileStorageCodecError(ValueError):
    """Raised when a persisted compact payload is malformed or unsupported."""


def encode_pair_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic, lossless evidence-dictionary representation."""

    if payload.get(_CODEC_KEY) == PAIR_EVIDENCE_DICTIONARY_CODEC:
        return dict(payload)
    if _CODEC_KEY in payload:
        raise CompetitorProfileStorageCodecError(
            f"unsupported competitor pair storage codec: {payload.get(_CODEC_KEY)!r}"
        )

    evidence_dictionary: list[dict[str, Any]] = []
    evidence_indexes: dict[str, int] = {}

    def compact(value: Any, *, field_name: str | None = None) -> Any:
        if field_name == "evidence_refs":
            if not isinstance(value, list):
                raise CompetitorProfileStorageCodecError(
                    "competitor pair evidence_refs must be a list"
                )
            indexes: list[int] = []
            for ref in value:
                if not isinstance(ref, Mapping):
                    raise CompetitorProfileStorageCodecError(
                        "competitor pair evidence refs must be objects"
                    )
                normalized = dict(ref)
                key = json.dumps(
                    normalized,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                index = evidence_indexes.get(key)
                if index is None:
                    index = len(evidence_dictionary)
                    evidence_indexes[key] = index
                    evidence_dictionary.append(normalized)
                indexes.append(index)
            return indexes
        if isinstance(value, Mapping):
            return {
                key: compact(value[key], field_name=key)
                for key in sorted(value)
            }
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    result_hash = payload.get("result_hash")
    input_fingerprint = payload.get("input_fingerprint")
    if not isinstance(result_hash, str) or not result_hash:
        raise CompetitorProfileStorageCodecError(
            "competitor pair payload requires result_hash"
        )
    if not isinstance(input_fingerprint, str) or not input_fingerprint:
        raise CompetitorProfileStorageCodecError(
            "competitor pair payload requires input_fingerprint"
        )
    return {
        _CODEC_KEY: PAIR_EVIDENCE_DICTIONARY_CODEC,
        "result_hash": result_hash,
        "input_fingerprint": input_fingerprint,
        "evidence_dictionary": evidence_dictionary,
        "payload": compact(dict(payload)),
    }


def decode_pair_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Restore a typed pair payload from raw or compact persisted JSON."""

    codec = payload.get(_CODEC_KEY)
    if codec is None:
        return dict(payload)
    if codec != PAIR_EVIDENCE_DICTIONARY_CODEC:
        raise CompetitorProfileStorageCodecError(
            f"unsupported competitor pair storage codec: {codec!r}"
        )
    evidence_dictionary = payload.get("evidence_dictionary")
    compact_payload = payload.get("payload")
    if not isinstance(evidence_dictionary, list) or not all(
        isinstance(ref, Mapping) for ref in evidence_dictionary
    ):
        raise CompetitorProfileStorageCodecError(
            "compact competitor pair evidence dictionary is invalid"
        )
    if not isinstance(compact_payload, Mapping):
        raise CompetitorProfileStorageCodecError(
            "compact competitor pair payload is invalid"
        )

    def expand(value: Any, *, field_name: str | None = None) -> Any:
        if field_name == "evidence_refs":
            if not isinstance(value, list) or not all(
                isinstance(index, int) and not isinstance(index, bool)
                for index in value
            ):
                raise CompetitorProfileStorageCodecError(
                    "compact competitor pair evidence indexes are invalid"
                )
            try:
                return [dict(evidence_dictionary[index]) for index in value]
            except IndexError as exc:
                raise CompetitorProfileStorageCodecError(
                    "compact competitor pair evidence index is out of range"
                ) from exc
        if isinstance(value, Mapping):
            return {
                key: expand(child, field_name=key)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    restored = expand(compact_payload)
    if not isinstance(restored, dict):
        raise CompetitorProfileStorageCodecError(
            "restored competitor pair payload must be an object"
        )
    for field_name in ("result_hash", "input_fingerprint"):
        if restored.get(field_name) != payload.get(field_name):
            raise CompetitorProfileStorageCodecError(
                f"compact competitor pair {field_name} does not match its envelope"
            )
    return restored


def relation_from_pair_pointer(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a self-validating pointer to a relation in the parent pair payload."""

    relation_code = payload.get("relation_code")
    result_hash = payload.get("result_hash")
    if not isinstance(relation_code, str) or not relation_code:
        raise CompetitorProfileStorageCodecError(
            "relation payload requires relation_code"
        )
    if not isinstance(result_hash, str) or not result_hash:
        raise CompetitorProfileStorageCodecError("relation payload requires result_hash")
    return {
        _CODEC_KEY: RELATION_FROM_PAIR_CODEC,
        "relation_code": relation_code,
        "result_hash": result_hash,
    }


def is_relation_from_pair_pointer(payload: object) -> bool:
    return (
        isinstance(payload, Mapping)
        and payload.get(_CODEC_KEY) == RELATION_FROM_PAIR_CODEC
    )


__all__ = [
    "CompetitorProfileStorageCodecError",
    "PAIR_EVIDENCE_DICTIONARY_CODEC",
    "RELATION_FROM_PAIR_CODEC",
    "decode_pair_payload",
    "encode_pair_payload",
    "is_relation_from_pair_pointer",
    "relation_from_pair_pointer",
]
