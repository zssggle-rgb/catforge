"""Run each SKU profile skill against the verified native graph readback."""
import argparse
from decimal import Decimal
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace

from graph import verified
from package_rules import PROFILES
from snapshot import atomic_write, canonical, digest

CLAIM_RULE = "m04c_tv_claim_fact_profile_v0.2"


def jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def run(snapshot, output, domains):
    manifest, definitions, records = verified(snapshot)
    ns = SimpleNamespace
    def rows(family):
        return [ns(**row) for r in records.values() for row in r.get(family, [])]
    def current(family):
        return {r.sku_code: r for r in rows(family)}
    def exact_claims(family):
        return [r for r in rows(family) if r.batch_id == manifest["batch_id"] and r.rule_version == CLAIM_RULE]
    claims = {}
    for row in exact_claims("claim"):
        claims.setdefault(row.sku_code, []).append(row)
    inputs = dict(param_profiles=rows("parameter"), market_profiles=current("market"), market_weekly_rows=rows("week"),
                  comment_profiles=current("comment_profile"), claim_profiles={r.sku_code: r for r in exact_claims("claim_profile")},
                  claim_facts=claims, comment_facts={s: [ns(**r) for r in v.get("comment", [])] for s,v in records.items()})
    for domain in domains:
        module, builder, field, version = PROFILES[domain]
        rules = import_module("skillrules." + module)
        definitions_for_domain = definitions[domain]
        dims = tuple(ns(**row) for row in definitions_for_domain[field])
        scorer = getattr(rules, builder)(project_id=manifest["project_id"], category_code=manifest["category_code"],
                       batch_id=manifest["batch_id"], run_id=None, module_run_id=None, rule_version=version,
                       taxonomy=ns(**{**definitions_for_domain, field: dims}), **{field: dims})
        p, scores, _, _ = scorer.build(rules._build_sku_inputs(**inputs), **({"graph_mode": "skip"} if domain == "value-battlefield" else {}))
        revision = (Path(import_module("skillrules").__file__).parent / "REVISION").read_text().strip()
        result = {"snapshot_id": snapshot.name, "rule_version": version, "rule_bundle": revision,
                  "profiles": [x.payload for x in p], "scores": [x.payload for x in scores]}
        # Make the frozen file stable across reruns without rounding numeric scores.
        result = json.loads(json.dumps(result, default=jsonable))
        atomic_write(output / (domain + ".json"), canonical(result))
        print(domain, len(p), len(scores), digest(result), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--domain", choices=PROFILES, action="append")
    a = p.parse_args()
    run(a.snapshot, a.out, a.domain or PROFILES)
