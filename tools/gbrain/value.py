"""Compute semantic allocation and claim value from frozen positioning results and brain facts."""
import argparse
from collections import defaultdict
from decimal import Decimal
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace as Row

from graph import verified
from profiles import CLAIM_RULE, jsonable
from snapshot import atomic_write, canonical, digest

DOMAINS = {"user-task": "user_task", "target-group": "target_group", "value-battlefield": "battlefield"}


def frozen(out, name, sid, revision=None):
    if revision is not None and not re.fullmatch("[a-f0-9]{64}", revision):
        raise ValueError("invalid result revision")
    path = out / (name + ".json") if revision is None else out / "revisions" / name / (revision + ".json")
    data = json.loads(path.read_text())
    if revision and digest(data) != revision:
        raise ValueError("result revision hash mismatch: " + name)
    if data["snapshot_id"] != sid:
        raise ValueError("mixed input snapshots: " + name)
    return data


def check_parents(result, expected):
    for name, fingerprint in expected.items():
        if result.get("inputs", {}).get(name) != fingerprint:
            raise ValueError("stale derived input: " + name)


def save(out, name, value):
    value = json.loads(json.dumps(value, default=jsonable))
    body = canonical(value)
    latest = out / (name + ".json")
    revisions = out / "revisions" / name
    revisions.mkdir(parents=True, exist_ok=True)
    revision = revisions / (sha256(body.encode()).hexdigest() + ".json")
    with (revisions / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if latest.exists():
            # Preserve canonical files produced by earlier releases on their first update.
            checksum = sha256()
            with latest.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    checksum.update(chunk)
            previous = revisions / (checksum.hexdigest() + ".json")
            if not previous.exists():
                os.link(latest, previous)
        if not revision.exists():
            atomic_write(revision, body)
        with TemporaryDirectory(dir=out) as tmp:
            link = Path(tmp) / latest.name
            os.link(revision, link)
            os.replace(link, latest)
    return value


def allocations(snapshot, out):
    from skillrules import semantic_market_graph_service as rules
    manifest, _, facts = verified(snapshot)
    parents = {}
    inputs = {}
    for kind, stem in DOMAINS.items():
        result = frozen(out, kind, snapshot.name)
        parents[kind] = digest(result)
        for family in ("profiles", "scores"):
            inputs[stem + "_" + family] = tuple(Row(**r) for r in result[family])
    inputs["market_profiles"] = tuple(Row(**r) for f in facts.values() for r in f.get("market", []))
    inputs["comment_profiles"] = tuple(Row(**r) for f in facts.values() for r in f.get("comment_profile", []))
    inputs = rules.M11DSemanticInputs(**inputs)
    market = rules._build_sku_market_map(inputs.market_profiles)
    pop = "fact_complete_with_comment"
    included, population = rules._resolve_population(inputs, sku_markets=market, analysis_population=pop, target_sku_codes=())
    dimensions = tuple(DOMAINS.values())
    candidates = rules._build_relation_candidates(inputs, included_skus=included, dimension_types=dimensions)
    common = dict(sku_markets=market, included_skus=included, dimension_types=dimensions, project_id=manifest["project_id"],
                  category_code="TV", batch_id=manifest["batch_id"], run_id=None, module_run_id=None, product_category="TV",
                  analysis_population=pop, market_window="full_observed_window", rule_version="m11d_semantic_market_allocation_v0.1")
    rows, checks = rules._build_allocations_and_checks(candidates, **common)
    summaries, contributions = rules._build_summaries_and_contributions(candidates, rows, **common)
    return save(out, "allocation", {"snapshot_id": snapshot.name, "rule_version": common["rule_version"], "inputs": parents,
                "population": population, "members": included, **{key: [r.payload for r in group] for key,group in
                [("allocations", rows), ("checks", checks), ("summaries", summaries), ("contributions", contributions)]}})


def claim_state(rules, r):
    row = Row(**r)
    code = rules._row_canonical_claim_code(row)
    name = rules._row_canonical_claim_name(row)
    return rules.ClaimState(sku_code=row.sku_code, claim_code=code, claim_name=name, claim_dimension=row.claim_dimension,
             claim_subtype=row.claim_subtype, claim_kind=row.claim_kind, param_support_status=row.param_support_status,
             supporting_param_codes=tuple(row.supporting_param_codes or []), supporting_param_snapshot=row.supporting_param_snapshot_json or {},
             match_score=rules._q4(row.match_score), confidence=rules._q4(row.confidence), fact_claim_flag=row.fact_claim_flag,
             service_separate_flag=row.service_separate_flag, evidence_ids=tuple(row.evidence_ids or []),
             param_support_level=rules._row_param_support_level(row), param_support_specificity=row.param_support_specificity,
             primary_supporting_param_codes=tuple(row.primary_supporting_param_codes or []), generic_support_param_codes=tuple(row.generic_support_param_codes or []),
             source_claim_group_id=row.source_claim_group_id, same_source_param_group_id=row.same_source_param_group_id,
             canonical_claim_code=code, canonical_claim_name=name, wtp_input_guard=rules._row_wtp_input_guard(row),
             member_claim_codes=(row.claim_code,), member_claim_names=(row.claim_name,))


def quantify(snapshot, out):
    from skillrules import m12c_claim_value_quantification_service as rules
    manifest, _, facts = verified(snapshot)
    allocation = frozen(out, "allocation", snapshot.name)
    positioning = frozen(out, "value-battlefield", snapshot.name)
    positioning_hash = digest(positioning)
    check_parents(allocation, {"value-battlefield": positioning_hash})
    weights = defaultdict(dict)
    for r in allocation["allocations"]:
        if r["dimension_type"] == "battlefield" and Decimal(str(r["allocation_weight"])) > 0:
            weights[r["sku_code"]]["battlefield", r["dimension_code"]] = Decimal(str(r["allocation_weight"]))
    semantics, comments, claims, params, markets = {}, {}, {}, {}, {}
    profiles = {r["sku_code"]: r for r in positioning["profiles"]}
    participating = {r["sku_code"] for r in allocation["contributions"]}
    for sku in sorted(participating):
        f = facts[sku]
        if not all(f.get(k) for k in ("serving_claim", "market", "comment_profile", "parameter")):
            continue
        serving = f["serving_claim"][0]["batch_id"]
        merged = {}
        for row in sorted(f.get("claim", []), key=lambda r: (r["claim_code"], r["source_claim_key"])):
            if row["rule_version"] == CLAIM_RULE and row["batch_id"] == serving:
                claim = claim_state(rules, row)
                merged[claim.claim_code] = rules._merge_claim_states(merged.get(claim.claim_code), claim)
        if not merged:
            continue
        claims[sku] = merged
        markets[sku] = rules._market_state(Row(**f["market"][0]))
        p = f["parameter"][0]
        params[sku] = rules.ParamProfileState(sku, rules._param_profile_values(Row(**p)), tuple(p["evidence_ids"] or []))
        c = f["comment_profile"][0]
        comments[sku] = rules.CommentState(sku, tuple(c["supported_claim_codes"] or []), tuple(c["contradicted_claim_codes"] or []),
                                          c["positive_sentence_count"], c["negative_sentence_count"], rules._q4(c["confidence"]))
        prof = profiles[sku]
        contexts = [("battlefield", code, code, role) for role, codes in
                    [("primary", [prof["primary_battlefield_code"]]), ("secondary", prof["secondary_battlefield_codes_json"])] for code in codes or [] if code]
        if not contexts:
            viable = sorted((r for r in positioning["scores"] if r["sku_code"] == sku and r["market_gate_status"] != "mismatch"
                             and r["relation_status"] in ("primary_battlefield", "secondary_battlefield", "opportunity_battlefield")),
                            key=lambda r: -float(r["battlefield_score"]))
            if viable:
                r = viable[0]
                contexts.append(("battlefield", r["battlefield_code"], r["battlefield_name"], r["relation_status"].split("_")[0]))
        if not contexts:
            contexts.extend((kind, code, code, "m11d_allocation_fallback") for kind, code in weights[sku])
        semantics[sku] = rules.SemanticState(sku, tuple(contexts), weights[sku])
    spaces = {(r["dimension_type"], r["dimension_code"]): Row(**r) for r in allocation["summaries"]}
    common = dict(project_id=manifest["project_id"], category_code="TV", batch_id=manifest["batch_id"], product_category="TV",
                  run_id=None, module_run_id=None, market_window="full_observed_window", analysis_population="claim_value_ready_with_comment",
                  rule_version="m12c_tv_claim_value_quantification_v0.2")
    pools = rules._build_pools(markets=markets, claims=claims, semantics=semantics, dimension_names={k:v.dimension_name for k,v in spaces.items()}, param_profiles=params)
    pool_rows, metrics, by_pool = rules._pool_and_metric_rows(pools=pools, markets=markets, **common)
    rows, by_context = rules._quantification_rows(pools=pools, metric_by_pool=by_pool, markets=markets, claims=claims,
                                param_profiles=params, comments=comments, semantics=semantics, output_sku_codes=set(markets), **common)
    attrs = rules._attribution_rows(quant_by_sku_context=by_context, markets=markets, **common)
    summaries = rules._dimension_summary_rows(quant_rows=rows, dimension_spaces=spaces, **common)
    return save(out, "claim-value", {"snapshot_id": snapshot.name, "rule_version": common["rule_version"],
               "inputs": {"allocation": digest(allocation), "value-battlefield": positioning_hash},
               "members": sorted(markets), "pools": pool_rows, "metrics": metrics, "values": rows, "attributions": attrs, "summaries": summaries})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["allocation", "claim-value"])
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    result = (allocations if args.action == "allocation" else quantify)(args.snapshot, args.out)
    print(args.action, len(result["members"]), digest(result))
