"""Materialize frozen upper assessments for the target, retaining their exact input versions."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from graph import project
from position_graph import add_positions
from snapshot import canonical, digest
from value import DOMAINS, check_parents, frozen


def materialize(snapshot, out, stage):
    graph = project(snapshot, stage, render=False)
    profiles = add_positions(graph, snapshot, out)
    existing = set(graph.nodes)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    sku = manifest["target"]
    target = snap = market = comment = None
    definitions, dims, sources, skus = {}, {}, {}, {}
    for slug, (kind, key, row) in graph.nodes.items():
        if kind in DOMAINS:
            definitions[DOMAINS[kind], key["code"]] = slug
        elif kind == "semantic-assessment":
            dims[DOMAINS[key["kind"]], key["code"]] = slug
        elif kind == "source":
            sources[key["evidence_id"]] = slug
        elif kind == "sku":
            skus[key["sku_code"]] = slug
        elif kind == "input-snapshot" and key["content_hash"] == snapshot.name:
            snap = slug
        elif kind == "market-window":
            market = slug
        elif kind == "comment-profile":
            comment = slug
    target = skus[sku]
    def node(kind, keys, attrs, parents):
        ref = graph.node(kind, dict(keys, sku_code=sku, snapshot_id=snapshot.name), attrs)
        graph.edge(ref, "uses_snapshot", snap)
        graph.edge(ref, "assesses_sku", target)
        for parent in parents:
            graph.edge(ref, "based_on", parent)
        for eid in attrs.get("evidence_ids_json") or []:
            graph.edge(ref, "cites_evidence", sources.get(eid))
        return ref

    parents = {name: digest(frozen(out, name, snapshot.name)) for name in DOMAINS}
    allocation = frozen(out, "allocation", snapshot.name)
    check_parents(allocation, parents)
    parents["allocation"] = digest(allocation)
    allocated = {}
    for row in allocation["allocations"]:
        if row["sku_code"] != sku:
            continue
        dim = row["dimension_type"], row["dimension_code"]
        key = dict(kind=dim[0], code=dim[1], population=row["analysis_population"],
                   window=row["market_window"], rule_version=allocation["rule_version"])
        ref = node("market-allocation", key, row, [dims[dim], market, comment])
        graph.edge(ref, "assesses_dimension", definitions[dim])
        allocated[dim] = ref
    del allocation

    reason = frozen(out, "purchase-reason", snapshot.name)
    reason_uses_value = "claim-value" in reason["inputs"]
    assessed = []
    if (out / "claim-value.json").is_file():
        values = frozen(out, "claim-value", snapshot.name)
        check_parents(values, {k: parents[k] for k in ("allocation", "value-battlefield")})
        parents["claim-value"] = digest(values)
        pools = {r["pool_id"]: r for r in values["pools"]}
        metrics = {r["pool_id"]: r for r in values["metrics"]}
        for row in values["values"]:
            if row["sku_code"] != sku:
                continue
            pid = row["pool_id"]
            pool = pools[pid]
            cohort = graph.node("market-cohort", {"sku_code": sku, "snapshot_id": snapshot.name, "purpose": pid,
                                "window": row["market_window"], "rule_version": values["rule_version"]}, pool)
            graph.edge(cohort, "uses_snapshot", snap)
            for member in pool["pool_sku_codes_json"]:
                graph.edge(cohort, "has_member", skus[member])
            dim = row["context_type"], row["context_code"]
            ref = node("claim-value-assessment", dict(code=row["claim_code"], context=dim[1], pool=pid,
                       window=row["market_window"], rule_version=values["rule_version"]),
                       {**row, "pool_metrics": metrics[pid], "inputs": values["inputs"]},
                       [allocated.get(dim), dims.get(dim), market, comment])
            graph.edge(ref, "uses_cohort", cohort)
            assessed.append(ref)
        del values
    if reason_uses_value and "claim-value" not in parents:
        raise ValueError("missing claim value used by frozen purchase reason")
    check_parents(reason, {k: v for k, v in parents.items() if k != "claim-value" or reason_uses_value})
    result, = (row for row in reason["profiles"] if row["sku_code"] == sku)
    # Input availability distinguishes the replay with an intentionally withheld M12C.
    reason_kind = "purchase-reason" if reason_uses_value else "purchase-reason-without-value"
    profile = node("sku-profile", {"kind": reason_kind, "rule_version": reason["rule_version"]},
                   {**{k: v for k, v in result.items() if k != "scored_anchors"}, "inputs": reason["inputs"]},
                   [*profiles.values(), *allocated.values(), *(assessed if reason_uses_value else [])])
    for row in result["scored_anchors"]:
        code = row["anchor_code"]
        definition = graph.node("purchase-reason", {"code": code, "taxonomy_version": row["taxonomy_version"]},
                                {"label": row["anchor_cn"]})
        ref = node("semantic-assessment", {"kind": reason_kind, "code": code, "rule_version": reason["rule_version"]},
                   row, [])
        graph.edge(ref, "assesses_dimension", definition)
        graph.edge(profile, "includes_assessment", ref)
        for source in row["source_refs_json"]:
            for eid in source.get("evidence_ids") or []:
                graph.edge(ref, "cites_evidence", sources.get(eid))
    analysis = frozen(out, "battlefield-analysis", snapshot.name)
    check_parents(analysis, {k: parents[k] for k in ("allocation", "value-battlefield")})
    analysis_ref = node("battlefield-analysis", {"rule_version": analysis["rule_version"]}, analysis,
                        [profiles["value-battlefield"], *(v for (kind, _), v in allocated.items() if kind == "battlefield")])
    new = set(graph.nodes) - existing
    graph.save(new)
    return {"pages": Counter(graph.nodes[s][0] for s in new), "analysis": analysis_ref, "purchase_reason": profile}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("snapshot", "results", "stage"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    print(canonical(materialize(args.snapshot, args.results, args.stage)))
