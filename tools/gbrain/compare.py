"""Offline verification against held-out CatForge SKU answer exports."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from package_rules import PROFILES
from snapshot import atomic_write, canonical, digest

FIELDS = {"user-task": "user_task", "target-group": "target_group", "value-battlefield": "battlefield"}


def equivalent(a, b):
    if a == b:
        return True
    if isinstance(a, (float, int)) or isinstance(b, (float, int)):
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except ArithmeticError:
            return False
    return False


def compare(results, holdout):
    report = []
    for domain in PROFILES:
        data = json.loads((results / (domain + ".json")).read_text())
        stem = FIELDS[domain]
        key = stem + "_code"
        actual = {(r["sku_code"], r[key]): r for r in data["scores"]}
        for path in sorted(holdout.glob("sku-" + domain + "-*.json")):
            expected = json.loads(path.read_text())
            sku = expected["sku"]["sku_code"]
            if expected["rule_version"] != data["rule_version"] or expected["batch_id"] != next(v["batch_id"] for v in data["profiles"] if v["sku_code"] == sku):
                raise ValueError("holdout scope/version mismatch")
            diffs = []
            counts = Counter()
            for reference in expected["scores"]:
                code = reference[key]
                row = actual[sku, code]
                for field, value in reference.items():
                    if field in row and not isinstance(value, (list, dict)):
                        counts[field] += 1
                        if not equivalent(row[field], value):
                            diffs.append({"code": code, "field": field, "expected": value, "actual": row[field]})
            extras = {r[key] for r in data["scores"] if r["sku_code"] == sku} - {r[key] for r in expected["scores"]}
            report.append({"domain": domain, "sku": sku, "candidates": len(expected["scores"]), "extra": sorted(extras),
                           "checked": counts, "differences": diffs, "result_sha": digest(data)})
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("results", "holdout", "receipt"):
        p.add_argument(k, type=Path)
    args = p.parse_args()
    atomic_write(args.receipt, canonical(compare(args.results, args.holdout)))
