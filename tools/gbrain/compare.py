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
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    if isinstance(a, (float, int)) or isinstance(b, (float, int)):
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except ArithmeticError:
            return False
    return False


def component_differences(actual, expected, path=()):
    if isinstance(actual, dict) and isinstance(expected, dict):
        for k in sorted(actual.keys() | expected.keys()):
            if k not in actual or k not in expected:
                yield ".".join((*path, k))
            else:
                yield from component_differences(actual[k], expected[k], (*path, k))
    elif not equivalent(actual, expected):
        if path[-1:] == ("evidence_ids",) and sorted(actual) == sorted(expected):
            yield ".".join((*path, "order"))
        else:
            yield ".".join(path)


def compare(results, holdout):
    report = []
    for domain in PROFILES:
        data = json.loads((results / (domain + ".json")).read_text())
        stem = FIELDS[domain]
        key = stem + "_code"
        actual = {(r["sku_code"], r[key]): r for r in data["scores"]}
        paths = sorted(holdout.glob("sku-" + domain + "-*.json"))
        if not paths:
            raise ValueError("missing holdout for " + domain)
        result_sha = digest(data)
        for path in paths:
            expected = json.loads(path.read_text())
            sku = expected["sku"]["sku_code"]
            if expected["rule_version"] != data["rule_version"] or expected["batch_id"] != next(v["batch_id"] for v in data["profiles"] if v["sku_code"] == sku):
                raise ValueError("holdout scope/version mismatch")
            diffs = []
            counts = Counter()
            presentation = Counter()
            excluded = set()
            missing = []
            for reference in expected["scores"]:
                code = reference[key]
                row = actual.get((sku, code))
                if row is None:
                    missing.append(code)
                    continue
                for field, value in reference.items():
                    source_field = "score_breakdown_json" if field == "score_breakdown" else field
                    if source_field in row:
                        counts[field] += 1
                        if field == "score_breakdown":
                            for path in component_differences(row[source_field], value):
                                if path.endswith((".sample_comments", ".evidence_ids.order")):
                                    presentation[path] += 1
                                else:
                                    diffs.append({"code": code, "field": path})
                        elif not equivalent(row[source_field], value):
                            diffs.append({"code": code, "field": field})
                    else:
                        excluded.add(field)
            extras = {r[key] for r in data["scores"] if r["sku_code"] == sku} - {r[key] for r in expected["scores"]}
            report.append({"domain": domain, "sku": sku, "candidates": len(expected["scores"]), "extra": sorted(extras),
                           "missing": missing, "checked": counts, "differences": diffs, "excluded": sorted(excluded),
                           "presentation_differences": presentation,
                           "scope": "candidate scores and components; profile-level and internal-only fields excluded",
                           "result_sha": result_sha})
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("results", "holdout", "receipt"):
        p.add_argument(k, type=Path)
    args = p.parse_args()
    report = compare(args.results, args.holdout)
    atomic_write(args.receipt, canonical(report))
    if any(r["extra"] or r["missing"] or r["differences"] or not r["checked"] for r in report):
        raise SystemExit(1)
