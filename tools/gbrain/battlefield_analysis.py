"""Explain battlefield fit and replay M11D role coefficients on a complete SKU denominator."""
import argparse
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from graph import verified
from profiles import CLAIM_RULE
from snapshot import digest
from value import DOMAINS, check_parents, frozen, save


def number(value):
    return Decimal(str(value))


def sensitivity(rows, secondary):
    if not secondary.is_finite() or secondary < 0:
        raise ValueError("secondary coefficient must be finite and nonnegative")
    terms = []
    for row in rows:
        role_factor = secondary if row["allocation_role"] == "secondary_value" else number(row["relation_factor"])
        terms.append((row["dimension_code"], number(row["allocation_basis"]) * role_factor))
    denominator = sum((v for _, v in terms), Decimal(0))
    weights = {}
    for index, (code, basis) in enumerate(terms):
        if code in weights:
            raise ValueError("duplicate battlefield allocation")
        weight = Decimal(0)
        if denominator:
            weight = (basis / denominator).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            if index == len(terms) - 1:
                weight = Decimal(1) - sum(weights.values())
        weights[code] = weight
    return {"secondary_factor": secondary, "raw_denominator": denominator, "weights": weights,
            "unallocated_weight": Decimal(1) - sum(weights.values())}


def reconciliation(members, markets, allocations):
    rows = defaultdict(list)
    for row in allocations:
        rows[row["sku_code"], row["dimension_type"]].append(row)
    totals = {}
    for dimension in DOMAINS.values():
        result = {}
        for unit, observed_column, allocated_column in (
            ("volume", "sales_volume_total", "allocated_sales_volume"),
            ("amount", "sales_amount_total", "allocated_sales_amount"),
        ):
            observed = allocated = unallocated = Decimal(0)
            unknown = 0
            for sku in members:
                source = markets.get(sku, {}).get(observed_column)
                if source is None:
                    unknown += 1
                    continue
                total = number(source)
                observed += total
                entries = rows[sku, dimension]
                if entries:
                    allocated += sum(number(row[allocated_column]) for row in entries)
                else:
                    unallocated += total
            result[unit] = {"observed": observed, "allocated": allocated, "unallocated": unallocated,
                            "rounding_residual": observed - allocated - unallocated, "unknown_skus": unknown}
        totals[dimension] = result
    return totals


def analyze(snapshot, out):
    manifest, _, facts = verified(snapshot)
    sku = manifest["target"]
    battlefield = frozen(out, "value-battlefield", snapshot.name)
    allocation = frozen(out, "allocation", snapshot.name)
    fingerprint = digest(battlefield)
    check_parents(allocation, {"value-battlefield": fingerprint})
    scores = sorted((r for r in battlefield["scores"] if r["sku_code"] == sku),
                    key=lambda r: (-number(r["battlefield_score"]), r["battlefield_code"]))
    focus = []
    for score in scores[:2]:
        parts = score["score_breakdown_json"]
        voice = parts["user_voice"]
        focus.append({"code": score["battlefield_code"], "fit": score["battlefield_score"],
                      "role": score["relation_status"], "confidence": score["confidence"],
                      "review_required": score["review_required"], "market_gate": score["market_gate_status"],
                      "parameters": parts["param_capability"], "claim_alignment": parts["claim_alignment"],
                      "comment_counts": {k: voice[k] for k in ("positive_count", "negative_count", "fact_count")},
                      "comment_evidence_ids": voice["evidence_ids"], "market": parts["market"]})
    markets = {key: value["market"][0] for key, value in facts.items() if value.get("market")}
    sku_rows = [r for r in allocation["allocations"] if r["sku_code"] == sku]
    battle_rows = [r for r in sku_rows if r["dimension_type"] == "battlefield"]
    eligible = sku in allocation["members"]
    selected_claims = [r for r in facts[sku].get("claim", [])
                       if r["rule_version"] == CLAIM_RULE and r["batch_id"] == manifest["batch_id"]]
    return save(out, "battlefield-analysis", {
        "snapshot_id": snapshot.name, "sku_code": sku, "rule_version": "pilot_battlefield_analysis_v1",
        "inputs": {"value-battlefield": fingerprint, "allocation": digest(allocation)},
        "ranked_count": len(scores), "leading_candidates": focus,
        "leading_gap": number(focus[0]["fit"]) - number(focus[1]["fit"]) if len(focus) > 1 else None,
        "fixed_batch_claim_count": len(selected_claims), "claim_rule": CLAIM_RULE,
        "fixed_batch_claim_coverage": "available" if selected_claims else "unknown",
        "observed_window": "full_observed_window", "population": allocation["population"],
        "included_skus": len(allocation["members"]), "target_in_population": eligible,
        "target_totals": reconciliation([sku], markets, sku_rows) if eligible else None,
        "population_totals": reconciliation(allocation["members"], markets, allocation["allocations"]),
        "baseline_weights": {r["dimension_code"]: r["allocation_weight"] for r in battle_rows},
        "scenarios": [sensitivity(battle_rows, number(v)) for v in ("0.60", "0.70", "0.80")] if eligible else [],
        "interpretation": "Observed units and revenue are apportioned separately within each dimension. "
                          "Scenario weights are model allocations. Buyer motivation and causal lift are unknown.",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    print(digest(analyze(args.snapshot, args.out)))
