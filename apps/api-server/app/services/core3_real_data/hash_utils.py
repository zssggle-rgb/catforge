"""Stable hashing helpers for Core3 real-data v2."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_HASH_VERSION = "v1"
HASH_ALGORITHM = "sha256"


def normalize_for_hash(value: Any) -> Any:
    """Return a JSON-safe representation without collapsing missing-like values.

    The pipeline treats null, empty strings, ``unknown`` and ``-`` as different
    observations. This function only normalizes types and ordering; it does not
    apply business meaning to values.
    """

    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return {"__type": "float", "value": f"{value:.1f}"}
        return {"__type": "float", "value": repr(value)}
    if isinstance(value, Decimal):
        return {"__type": "decimal", "value": format(value.normalize(), "f")}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            normalized = value.isoformat(timespec="microseconds")
        else:
            normalized = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
        return {"__type": "datetime", "value": normalized}
    if isinstance(value, date):
        return {"__type": "date", "value": value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): normalize_for_hash(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, tuple):
        return {"__type": "tuple", "items": [normalize_for_hash(item) for item in value]}
    if isinstance(value, list):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, set | frozenset):
        normalized_items = [normalize_for_hash(item) for item in value]
        return {
            "__type": "set",
            "items": sorted(normalized_items, key=canonicalize_json),
        }
    return {"__type": value.__class__.__name__, "value": str(value)}


def canonicalize_json(value: Any) -> str:
    """Serialize a value into deterministic compact JSON."""

    normalized = normalize_for_hash(value)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any, version: str = DEFAULT_HASH_VERSION) -> str:
    """Return a version-prefixed stable hash for a normalized value."""

    payload = {
        "hash_version": version,
        "value": normalize_for_hash(value),
    }
    digest = hashlib.sha256(canonicalize_json(payload).encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{version}:{digest}"


def hash_records(
    records: Iterable[Mapping[str, Any]],
    keys: Sequence[str],
    version: str = DEFAULT_HASH_VERSION,
) -> str:
    """Hash records after sorting by the provided business keys."""

    key_list = list(keys)
    normalized_records = [normalize_for_hash(dict(record)) for record in records]
    sorted_records = sorted(normalized_records, key=lambda record: _record_sort_key(record, key_list))
    return stable_hash({"keys": key_list, "records": sorted_records}, version=version)


def _record_sort_key(record: Mapping[str, Any], keys: Sequence[str]) -> tuple[str, ...]:
    return tuple(canonicalize_json(record.get(key)) for key in keys)
