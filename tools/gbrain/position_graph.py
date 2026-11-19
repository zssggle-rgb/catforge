"""Publish frozen positioning assessments and independently versioned PM goals."""
import argparse
from collections import defaultdict
from datetime import date
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace

from compare import FIELDS
from graph import project
from package_rules import PROFILES
from profiles import CLAIM_RULE
from snapshot import canonical


def matched_comments(comments, definition, matcher, expected):
    matched = [slug for slug, atom in comments if matcher([atom], definition)["fact_count"]]
    if len(matched) != expected:
        raise ValueError("comment trace does not reproduce the frozen component count")
    return matched


def add_goal(graph, goal, sku, definitions):
    start, end = (date.fromisoformat(goal[k]) for k in ("valid_from", "valid_until"))
    if end < start or not all(goal.get(k) for k in ("owner", "goal_id", "revision", "objective", "source_ref")):
        raise ValueError("goal requires a dated, attributed objective")
    target = graph.nodes[sku][1]["sku_code"]
    if goal["sku_code"] != target:
        raise ValueError("goal target mismatch")
    definition = definitions[goal["battlefield_code"]]
    if graph.nodes[definition][1]["taxonomy_version"] != goal["taxonomy_version"]:
        raise ValueError("goal taxonomy mismatch")
    node = graph.node("business-goal", {k: goal[k] for k in ("sku_code", "goal_id", "revision")}, goal)
    graph.edge(node, "targets_sku", sku)
    graph.edge(node, "focuses_on", definition)
    return node


def add_positions(graph, snapshot, results, goal=None):
    manifest = json.loads((snapshot / "manifest.json").read_text())
    target = manifest["target"]
    by = defaultdict(dict)
    comments = []
    claims = defaultdict(set)
    pools = []
    for slug, (kind, key, row) in graph.nodes.items():
        if kind in PROFILES or kind == "sku-parameter":
            by[kind][key["code"]] = slug
        elif kind == "sku":
            by[kind][key["sku_code"]] = slug
        elif kind == "input-snapshot":
            by[kind][key["content_hash"]] = slug
        elif kind == "source":
            by[kind][key["evidence_id"]] = slug
        elif kind == "comment-fact":
            comments.append((slug, SimpleNamespace(**row)))
        elif kind == "sku-claim" and row["rule_version"] == CLAIM_RULE and row["batch_id"] == manifest["batch_id"]:
            for eid in row.get("evidence_ids") or []:
                claims[eid].add(slug)
        elif kind == "market-window":
            by[kind][target] = slug
        elif kind == "market-cohort":
            pools.append(slug)
    target_node = by["sku"][target]
    snapshot_node = by["input-snapshot"][snapshot.name]
    def assessment(kind, key, row):
        node = graph.node(kind, {"sku_code": target, "snapshot_id": snapshot.name, **key}, row)
        graph.edge(node, "uses_snapshot", snapshot_node)
        graph.edge(node, "assesses_sku", target_node)
        return node

    published = {}
    bundle = (Path(import_module("skillrules").__file__).parent / "REVISION").read_text().strip()
    comment_parts = {"user-task": "comment_task_need", "target-group": "comment_audience_motivation",
                     "value-battlefield": "user_voice"}
    for domain, stem in FIELDS.items():
        result = json.loads((results / (domain + ".json")).read_text())
        version = result["rule_version"]
        if result["snapshot_id"] != snapshot.name or version != PROFILES[domain][3] or result["rule_bundle"] != bundle:
            raise ValueError("positioning snapshot or rule mismatch: " + domain)
        matcher = import_module("skillrules." + PROFILES[domain][0])._comment_match
        profile, = [row for row in result["profiles"] if row["sku_code"] == target]
        key = {"kind": domain, "rule_version": version}
        parent = assessment("sku-profile", key, {**profile, "rule_bundle": result["rule_bundle"]})
        published[domain] = parent
        selected = {r[stem + "_code"]: r for r in result["scores"] if r["sku_code"] == target}
        if set(selected) != set(by[domain]):
            raise ValueError("incomplete candidate set: " + domain)
        for code, row in selected.items():
            node = assessment("semantic-assessment", {**key, "code": code}, row)
            graph.edge(parent, "includes_assessment", node)
            graph.edge(node, "assesses_dimension", by[domain][code])
            parts = row["score_breakdown_json"]
            definition = SimpleNamespace(**graph.nodes[by[domain][code]][2])
            for witness in matched_comments(comments, definition, matcher, parts[comment_parts[domain]]["fact_count"]):
                graph.edge(node, "based_on", witness)
            for param in parts["param_capability"]["supported_param_codes"]:
                graph.edge(node, "based_on", by["sku-parameter"].get(param))
            for name, part in parts.items():
                if not isinstance(part, dict):
                    continue
                for eid in part.get("evidence_ids") or []:
                    graph.edge(node, "cites_evidence", by["source"].get(eid))
                    if name == "claim_alignment":
                        for witness in claims[eid]:
                            if graph.nodes[witness][2]["claim_code"] in part["matched_claim_codes"]:
                                graph.edge(node, "based_on", witness)
            graph.edge(node, "based_on", by["market-window"].get(target))
            for pool in pools:
                graph.edge(node, "uses_cohort", pool)
    if goal:
        published["business-goal"] = add_goal(graph, goal, target_node, by["value-battlefield"])
    return published


def materialize(snapshot, results, stage, goal=None):
    graph = project(snapshot, stage, render=False)
    original = set(graph.nodes)
    published = add_positions(graph, snapshot, results, goal)
    graph.save(set(graph.nodes) - original)
    return published


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("snapshot", "results", "stage"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--goal", type=Path, help="Private, versioned PM objective")
    args = parser.parse_args()
    print(canonical(materialize(args.snapshot, args.results, args.stage,
                                json.loads(args.goal.read_text()) if args.goal else None)))
