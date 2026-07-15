"""Stable hashing helpers for Core3 real-data v2."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Iterator, Mapping, Sequence


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
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{version}:{digest}"


def stable_hash_json(value: Any, version: str = DEFAULT_HASH_VERSION) -> str:
    """Hash an already normalized JSON payload without a redundant tree walk.

    Callers must pass only dictionaries, lists, and JSON scalar values emitted
    by typed ``model_dump(mode="json")`` contracts. Raw Decimal, datetime,
    Enum, tuple, set, and float values must continue to use :func:`stable_hash`.
    """

    payload = {
        "hash_version": version,
        "value": value,
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    return f"{HASH_ALGORITHM}:{version}:{digest}"


def stable_hash_streaming(value: Any, version: str = DEFAULT_HASH_VERSION) -> str:
    """Hash a large typed graph without materializing its normalized JSON tree.

    The byte stream is deliberately identical to :func:`stable_hash`. Pydantic
    models are dumped one model at a time, so callers can hash a list containing
    hundreds of large pair records without retaining a second complete tree and
    a complete canonical JSON string at the same time.
    """

    digest = hashlib.sha256()
    for chunk in _iter_normalized_json(
        {"hash_version": version, "value": value},
        dump_typed_models=True,
    ):
        digest.update(chunk.encode("utf-8"))
    return f"{HASH_ALGORITHM}:{version}:{digest.hexdigest()}"


def _iter_normalized_json(
    value: Any,
    *,
    dump_typed_models: bool,
) -> Iterator[str]:
    if dump_typed_models and _is_json_dump_model(value):
        # One typed row is bounded (for example one candidate pair). Let the C
        # JSON encoder handle that row, then release it before advancing to the
        # next row instead of walking millions of scalar fields in Python.
        yield canonicalize_json(value.model_dump(mode="json"))
        return
    if value is None or isinstance(value, bool | int | str):
        yield json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return
    if isinstance(value, float):
        normalized = f"{value:.1f}" if value.is_integer() else repr(value)
        yield from _iter_normalized_json(
            {"__type": "float", "value": normalized},
            dump_typed_models=dump_typed_models,
        )
        return
    if isinstance(value, Decimal):
        yield from _iter_normalized_json(
            {"__type": "decimal", "value": format(value.normalize(), "f")},
            dump_typed_models=dump_typed_models,
        )
        return
    if isinstance(value, datetime):
        normalized = (
            value.isoformat(timespec="microseconds")
            if value.tzinfo is None
            else value.astimezone(timezone.utc).isoformat(timespec="microseconds")
        )
        yield from _iter_normalized_json(
            {"__type": "datetime", "value": normalized},
            dump_typed_models=dump_typed_models,
        )
        return
    if isinstance(value, date):
        yield from _iter_normalized_json(
            {"__type": "date", "value": value.isoformat()},
            dump_typed_models=dump_typed_models,
        )
        return
    if isinstance(value, Enum):
        yield from _iter_normalized_json(
            value.value,
            dump_typed_models=dump_typed_models,
        )
        return
    if isinstance(value, Mapping):
        yield "{"
        for index, key in enumerate(sorted(value, key=lambda item: str(item))):
            if index:
                yield ","
            yield json.dumps(str(key), ensure_ascii=False, separators=(",", ":"))
            yield ":"
            yield from _iter_normalized_json(
                value[key],
                dump_typed_models=dump_typed_models,
            )
        yield "}"
        return
    if isinstance(value, tuple):
        yield from _iter_normalized_json(
            {"__type": "tuple", "items": list(value)},
            dump_typed_models=dump_typed_models,
        )
        return
    if isinstance(value, list):
        yield "["
        for index, item in enumerate(value):
            if index:
                yield ","
            yield from _iter_normalized_json(
                item,
                dump_typed_models=dump_typed_models,
            )
        yield "]"
        return
    if isinstance(value, set | frozenset):
        normalized_items = [normalize_for_hash(item) for item in value]
        yield from _iter_normalized_json(
            {
                "__type": "set",
                "items": sorted(normalized_items, key=canonicalize_json),
            },
            dump_typed_models=dump_typed_models,
        )
        return
    yield from _iter_normalized_json(
        {"__type": value.__class__.__name__, "value": str(value)},
        dump_typed_models=dump_typed_models,
    )


def _is_json_dump_model(value: Any) -> bool:
    return callable(getattr(value, "model_dump", None))


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
