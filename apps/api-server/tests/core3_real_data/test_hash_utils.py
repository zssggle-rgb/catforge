from datetime import date, datetime, timezone
from decimal import Decimal

from app.services.core3_real_data.hash_utils import canonicalize_json, hash_records, normalize_for_hash, stable_hash


def test_canonicalize_json_sorts_dict_keys_and_preserves_chinese():
    left = {"sku_code": "TV00029115", "brand": "海信", "metrics": {"b": 2, "a": 1}}
    right = {"metrics": {"a": 1, "b": 2}, "brand": "海信", "sku_code": "TV00029115"}

    assert canonicalize_json(left) == canonicalize_json(right)
    assert "海信" in canonicalize_json(left)


def test_normalize_for_hash_preserves_missing_like_values_as_distinct():
    values = [None, "", " ", "-", "unknown", "UNKNOWN", "null", False, 0]
    canonical_values = [canonicalize_json(value) for value in values]

    assert len(set(canonical_values)) == len(values)


def test_normalize_for_hash_handles_dates_decimals_tuples_and_sets():
    value = {
        "decimal": Decimal("1.2300"),
        "datetime": datetime(2026, 6, 12, 15, 22, 11, 180000, tzinfo=timezone.utc),
        "date": date(2026, 6, 12),
        "tuple": ("TV00029115", "85E7Q"),
        "set": {"comment", "market", "param"},
    }

    normalized = normalize_for_hash(value)

    assert normalized["decimal"] == {"__type": "decimal", "value": "1.23"}
    assert normalized["datetime"] == {"__type": "datetime", "value": "2026-06-12T15:22:11.180000+00:00"}
    assert normalized["date"] == {"__type": "date", "value": "2026-06-12"}
    assert normalized["tuple"] == {"__type": "tuple", "items": ["TV00029115", "85E7Q"]}
    assert normalized["set"]["__type"] == "set"
    assert normalized["set"]["items"] == ["comment", "market", "param"]


def test_stable_hash_includes_version_and_is_order_insensitive_for_dicts():
    value_a = {"b": 2, "a": 1}
    value_b = {"a": 1, "b": 2}

    first_hash = stable_hash(value_a, version="hash-v1")
    second_hash = stable_hash(value_b, version="hash-v1")
    different_version_hash = stable_hash(value_a, version="hash-v2")

    assert first_hash == second_hash
    assert first_hash.startswith("sha256:hash-v1:")
    assert different_version_hash.startswith("sha256:hash-v2:")
    assert first_hash != different_version_hash


def test_hash_records_sorts_by_business_keys_before_hashing():
    records_a = [
        {"sku_code": "TV00029115", "source_table": "week_sales_data", "source_pk": 2, "price": Decimal("3999.00")},
        {"sku_code": "TV00010001", "source_table": "week_sales_data", "source_pk": 1, "price": Decimal("2999.00")},
    ]
    records_b = list(reversed(records_a))

    assert hash_records(records_a, keys=["source_table", "source_pk"], version="row-v1") == hash_records(
        records_b,
        keys=["source_table", "source_pk"],
        version="row-v1",
    )
    assert hash_records(records_a, keys=["source_table", "source_pk"], version="row-v1") != hash_records(
        records_a,
        keys=["sku_code"],
        version="row-v1",
    )


def test_list_order_remains_significant():
    assert stable_hash(["market", "param"], version="list-v1") != stable_hash(["param", "market"], version="list-v1")

