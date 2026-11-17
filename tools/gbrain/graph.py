"""Project scoped facts to native GBrain Markdown and verify native export before inference."""
import argparse
import base64
from collections import defaultdict
import gzip
import json
from pathlib import Path
import re

from snapshot import atomic_write, canonical, digest

CONTRACT = json.loads((Path(__file__).parent / "schema/contract.json").read_text())
DEFINITIONS = {
    "parameter": ("standard_params", "param_code"), "claim": ("claims", "claim_code"),
    "comment-topic": ("subdimensions", "subdimension_code"), "user-task": ("user_tasks", "user_task_code"),
    "target-group": ("target_groups", "target_group_code"), "value-battlefield": ("battlefields", "battlefield_code"),
}


def verified(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    if directory.name != digest(manifest):
        raise ValueError("manifest identity mismatch")
    expected = dict(manifest["records"], definitions=manifest["definitions"])
    data = {}
    for name, checksum in expected.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("invalid snapshot member name")
        data[name] = json.loads((directory / (name + ".json")).read_text())
        if digest(data[name]) != checksum:
            raise ValueError("invalid snapshot member: " + name)
    return manifest, data.pop("definitions"), data


def blob(value):
    return base64.b64encode(gzip.compress(canonical(value).encode(), mtime=0)).decode()


class Graph:
    def __init__(self, root, manifest):
        self.root = root
        self.scope = {k: manifest[k] for k in CONTRACT["scope"]}
        self.nodes = {}
        self.edges = defaultdict(lambda: defaultdict(set))

    def node(self, kind, key, attributes):
        identity = {**self.scope, **key}
        slug = "catforge/" + kind + "/" + digest([identity[f] for f in CONTRACT["scope"] + CONTRACT["keys"][kind]])
        value = (kind, identity, attributes)
        if slug in self.nodes and self.nodes[slug] != value:
            raise ValueError("conflicting natural key for " + kind)
        self.nodes[slug] = value
        return slug

    def edge(self, src, verb, dst):
        if not dst:
            return
        rule = CONTRACT["relations"][verb]
        for side, slug in [("from", src), ("to", dst)]:
            if "*" not in rule[side] and self.nodes[slug][0] not in rule[side]:
                raise ValueError("invalid " + verb + " endpoint")
        targets = self.edges[src][verb]
        targets.add(dst)
        if rule["cardinality"] == "one" and len(targets) > 1:
            raise ValueError("ambiguous " + verb)

    def save(self):
        for slug, (kind, key, attrs) in self.nodes.items():
            lines = ["---", "type: " + kind, "title: " + json.dumps(str(attrs.get("label") or key.get("code") or key.get("sku_code") or kind), ensure_ascii=False)]
            for verb, targets in sorted(self.edges[slug].items()):
                lines.append(verb + ":")
                lines.extend("  - " + dst for dst in sorted(targets))
            lines.extend(["---", "", "~~~json", canonical({**key, **attrs}), "~~~", ""])
            atomic_write(self.root / (slug + ".md"), "\n".join(lines))


def project(directory, out):
    manifest, definitions, records = verified(directory)
    sid = digest(manifest)
    g = Graph(out, manifest)
    snap = g.node("input-snapshot", {"content_hash": sid}, {"member": "manifest", "payload": blob(manifest)})
    for member, value in [("definitions", definitions), *records.items()]:
        h = digest(value)
        node = g.node("input-snapshot", {"content_hash": h}, {"member": member, "payload": blob(value)})
        g.edge(snap, "based_on", node)
    defs = {}
    for kind, (table, code) in DEFINITIONS.items():
        taxonomy = definitions[kind]
        for row in taxonomy[table]:
            ref = g.node(kind, {"code": row[code], "taxonomy_version": taxonomy["taxonomy_version"]}, row)
            defs[kind, row[code]] = ref
            g.edge(snap, "defines", ref)
    refs = {"param_codes": "parameter", "claim_codes": "claim", "comment_subdimension_codes": "comment-topic",
            "source_task_codes": "user-task", "primary_task_codes": "user-task", "secondary_task_codes": "user-task",
            "primary_target_group_codes": "target-group"}
    for ref in defs.values():
        kind, _, attrs = g.nodes[ref]
        if kind in ("user-task", "target-group", "value-battlefield"):
            for field, target_kind in refs.items():
                for code in attrs.get(field, []):
                    g.edge(ref, "considers", defs.get((target_kind, code)))
    sku_nodes = {sku: g.node("sku", {"sku_code": sku}, {"label": (r.get("sku") or [{}])[0].get("model_name") or sku})
                 for sku, r in records.items()}
    sku = manifest["target"]
    r = records[sku]
    common = {"sku_code": sku, "snapshot_id": sid}
    evidence = {}
    for row in r.get("evidence", []):
        evidence[row["evidence_id"]] = g.node("source", {"evidence_id": row["evidence_id"], "source_hash": row["clean_hash"] or row["source_row_hash"]}, row)

    def fact(kind, keys, row):
        n = g.node(kind, {**common, **keys}, row)
        g.edge(n, "uses_snapshot", snap)
        g.edge(n, "observed_for", sku_nodes[sku])
        for eid in row.get("evidence_ids") or []:
            g.edge(n, "cites_evidence", evidence.get(eid))
        return n

    params = {}
    for code, row in r["parameter"][0]["param_values_json"].items():
        if not isinstance(row, dict) or not row.get("param_code"):
            continue
        params[code] = fact("sku-parameter", {"code": code}, row)
        g.edge(params[code], "measures", defs.get(("parameter", code)))
    for row in r.get("claim", []):
        ref = fact("sku-claim", {"source_id": row["claim_fact_id"]}, row)
        g.edge(ref, "expresses_claim", defs.get(("claim", row["claim_code"])))
        for code in row.get("supporting_param_codes") or []:
            g.edge(ref, "supports", params.get(code))
    for row in r.get("comment", []):
        ref = fact("comment-fact", {"source_id": row["comment_fact_id"]}, row)
        g.edge(ref, "about_topic", defs.get(("comment-topic", row["subdimension_code"])))
        for kind in ["param", "claim"]:
            for field, verb in [("supported", "supports"), ("contradicted", "contradicts")]:
                for code in row[field + "_" + kind + "_codes"] or []:
                    g.edge(ref, verb, defs.get(("parameter" if kind == "param" else kind, code)))
    for row in r.get("comment_profile", []):
        atoms = r.get("comment", [])
        fact("comment-profile", {}, {**row, **(r.get("comment_counts") or [{}])[0],
             "distinct_source_comments_in_atoms": len({a["source_comment_key"] for a in atoms})})
    window = "full_observed_window"
    for row in r.get("market", []):
        fact("market-window", {"window": window}, row)
    weeks = defaultdict(list)
    for row in r.get("week", []):
        weeks[row["period_week_index"]].append(row)
    for week, rows in weeks.items():
        fact("market-week", {"week": week}, {"rows": rows})
    def size(record):
        return record["parameter"][0]["param_values_json"].get("dimension_tier_profile", {}).get("size")
    for purpose in ["same_size_priced", "common_active_week"]:
        members = {}
        for code, rec in records.items():
            if not size(r) or size(rec) != size(r):
                continue
            market = (rec.get("market") or [{}])[0]
            overlap = sorted(set(weeks) & {v["period_week_index"] for v in rec.get("week", [])})
            if purpose == "same_size_priced" and market.get("price_wavg") is not None:
                members[code] = market["price_wavg"]
            elif purpose == "common_active_week" and code != sku and overlap:
                members[code] = overlap
        pool = g.node("market-cohort", {**common, "purpose": purpose, "window": window, "rule_version": "pilot-cohort-v1"}, {"members": members})
        g.edge(pool, "uses_snapshot", snap)
        for code in members:
            g.edge(pool, "has_member", sku_nodes[code])
    g.save()
    return len(g.nodes)


def restore(export, out, sid):
    source = export / "catforge/input-snapshot"
    payloads = {}
    for path in source.glob("*.md"):
        match = re.search(r"^~~~json\n(.+?)\n~~~", path.read_text(), re.M | re.S)
        if match:
            row = json.loads(match[1])
            value = json.loads(gzip.decompress(base64.b64decode(row["payload"], validate=True)))
            if digest(value) != row["content_hash"]:
                raise ValueError("native page hash mismatch")
            payloads[row["content_hash"]] = value
    manifest = payloads[sid]
    dest = out / sid
    for member, checksum in {**manifest["records"], "definitions": manifest["definitions"]}.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", member):
            raise ValueError("invalid snapshot member")
        atomic_write(dest / (member + ".json"), canonical(payloads[checksum]))
    atomic_write(dest / "manifest.json", canonical(manifest))
    verified(dest)
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["project", "restore"])
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    if args.action == "restore" and not args.snapshot:
        parser.error("restore needs --snapshot")
    print(project(args.source, args.out) if args.action == "project" else restore(args.source, args.out, args.snapshot))
