"""Compare frozen #5 outputs with a private, post-freeze CatForge JSONL export."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from compare import equivalent
from snapshot import atomic_write, canonical
from value import frozen


def keyed(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row[k] for k in fields)
        if key in result:
            raise ValueError("ambiguous held-out or generated natural key")
        result[key] = row
    return result


def compare(snapshot, out, holdout):
    manifest = json.loads((snapshot / "manifest.json").read_text())
    target = manifest["target"]
    by = defaultdict(list)
    for line in holdout.read_text().splitlines():
        family, row = json.loads(line)
        if row["project_id"] == manifest["project_id"] and row["category_code"] == manifest["category_code"] and row["sku_code"] == target:
            by[family].append(row)
    receipt = {"snapshot_id": snapshot.name, "sku_code": target, "batch_id": manifest["batch_id"]}
    for name, family, keys, fields in [
        ("allocation", "allocations", ("dimension_type", "dimension_code"),
         ("relation_status", "final_score", "allocation_weight", "allocated_sales_volume", "allocated_sales_amount")),
        ("claim-value", "values", ("claim_code", "context_type", "context_code", "pool_id"),
         ("claim_value_role", "estimated_price_premium_abs", "estimated_weekly_sales_lift_abs", "contribution_share_in_sku")),
    ]:
        result = frozen(out, name, snapshot.name)
        actual = keyed((r for r in result[family] if r["sku_code"] == target), keys)
        scope = next(iter(actual.values()), {})
        expected = keyed((r for r in by[name] if r["is_current"] and r["batch_id"] == manifest["batch_id"]
                          and r["rule_version"] == result["rule_version"]
                          and all(r[k] == scope.get(k) for k in ("analysis_population", "market_window"))), keys)
        shared = actual.keys() & expected.keys()
        differences = Counter(field for key in shared for field in fields
                              if not equivalent(actual[key][field], expected[key][field]))
        receipt[name] = {"generated": len(actual), "reference": len(expected), "matched_keys": len(shared),
                         "generated_only": len(actual.keys() - expected.keys()), "reference_only": len(expected.keys() - actual.keys()),
                         "compared_fields": fields, "field_differences": differences, "rule_version": result["rule_version"],
                         "lineage_status": "Historical upstream identity requires a separate check."}
    reasons = frozen(out, "purchase-reason", snapshot.name)
    reference = [r for r in by["reason"] if r["is_current"] and r["rule_version"] == reasons["rule_version"]]
    aligned = [r for r in reference if r["batch_id"] == manifest["batch_id"]]
    target_reasons, = (r for r in reasons["profiles"] if r["sku_code"] == target)
    receipt["purchase-reason"] = {"anchors": len(target_reasons["scored_anchors"]), "current_references": len(reference),
                                 "batch_matched": len(aligned), "reference_batches": sorted({r["batch_id"] for r in reference}),
                                 "status": "no_same_batch_reference" if not aligned else "same_batch_requires_source_lineage_check"}
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "results", "holdout", "receipt"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    atomic_write(args.receipt, canonical(compare(args.snapshot, args.results, args.holdout)))
