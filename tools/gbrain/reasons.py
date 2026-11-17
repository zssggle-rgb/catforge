"""Run the purchase-reason skill on the serving inputs and derived assessments in one snapshot."""
import argparse
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from graph import verified
from snapshot import digest
from value import frozen, save
from skillrules.constants import Core3CategoryCode
from skillrules.purchase_reason_context_builder import SkuPurchaseReasonContextBuilder
from skillrules.purchase_reason_anchor_candidate_generator import AnchorCandidateGenerator
from skillrules.purchase_reason_anchor_taxonomy import tv_purchase_reason_anchor_taxonomy_v0_1
from skillrules.purchase_reason_profile_scoring import PurchaseReasonProfileScoringService

TABLES = {
    "Core3SkuParamProfile": ("parameter", "core3_sku_param_profile", "sku_param_profile_id"),
    "Core3SkuClaimFactProfile": ("claim_profile", "core3_sku_claim_fact_profile", "claim_profile_id"),
    "Core3SkuClaimFact": ("claim", "core3_sku_claim_fact", "claim_fact_id"),
    "Core3SkuClaimDimensionPosition": ("claim_position", "core3_sku_claim_dimension_position", "dimension_position_id"),
    "Core3SkuCommentFactProfile": ("comment_profile", "core3_sku_comment_fact_profile", "comment_profile_id"),
    "Core3CommentFactAtom": ("comment", "core3_comment_fact_atom", "comment_fact_id"),
    "Core3SkuMarketProfile": ("market", "core3_sku_market_profile", "profile_id"),
    "Core3M09cSkuUserTaskProfile": ("user-task", "core3_m09c_sku_user_task_profile", "profile_id"),
    "Core3M10cSkuTargetGroupProfile": ("target-group", "core3_m10c_sku_target_group_profile", "profile_id"),
    "Core3SkuValueBattlefieldProfile": ("value-battlefield", "core3_sku_value_battlefield_profile", "profile_id"),
    "Core3SemanticMarketAllocation": ("allocations", "core3_semantic_market_allocation", "allocation_id"),
    "Core3SemanticMarketSkuContribution": ("contributions", "core3_semantic_market_sku_contribution", "contribution_id"),
    "Core3SkuClaimValueQuantification": ("values", "core3_sku_claim_value_quantification", "sku_claim_value_id"),
    "Core3SkuClaimContributionAttribution": ("attributions", "core3_sku_claim_contribution_attribution", "attribution_id"),
}


class SnapshotRows(SkuPurchaseReasonContextBuilder):
    def __init__(self, manifest, facts):
        self.project_id = manifest["project_id"]
        self.category_code = Core3CategoryCode.TV
        self.rows = facts

    def _list_sku_rows(self, model, batch_id, sku_code, *, rule_version, taxonomy_version=None, order_fields=(), limit=50):
        family, table, pk = TABLES[model]
        meta = SimpleNamespace(name=table, primary_key=SimpleNamespace(columns=[SimpleNamespace(name=pk)]))
        rows = [SimpleNamespace(**{k: Decimal(str(v)) if k == "allocation_weight" and v is not None else v for k,v in r.items()}, __table__=meta) for r in self.rows.get(family, []) if r["sku_code"] == sku_code
                and r.get("rule_version") == rule_version and (not taxonomy_version or r.get("taxonomy_version") == taxonomy_version)]
        rows.sort(key=lambda r: tuple(str(getattr(r, k, "") or "") for k in (*order_fields, pk)))
        return rows[:limit] if limit > 0 else rows

    def _get_profile(self, model, batch_id, sku_code, **versions):
        rows = self._list_sku_rows(model, batch_id, sku_code, **versions, limit=0)
        if len(rows) > 1:
            raise ValueError("ambiguous serving input: " + model)
        return next(iter(rows), None)

    def _get_param_profile(self, batch_id, sku_code, rule_version):
        return self._get_profile("Core3SkuParamProfile", batch_id, sku_code, rule_version=rule_version)

    def _get_market_profile(self, batch_id, sku_code, rule_version):
        return self._get_profile("Core3SkuMarketProfile", batch_id, sku_code, rule_version=rule_version)


def reasons(snapshot, out, skus, use_value=True, all_members=False):
    manifest, _, data = verified(snapshot)
    indexes = defaultdict(lambda: defaultdict(list))
    parents = {}
    def index(name, families):
        result = frozen(out, name, snapshot.name)
        parents[name] = digest(result)
        for field, family in families:
            for row in result[field]:
                indexes[row["sku_code"]][family].append(row)
    for name in ("user-task", "target-group", "value-battlefield"):
        index(name, [("profiles", name)])
    index("allocation", [("allocations", "allocations"), ("contributions", "contributions")])
    if use_value:
        index("claim-value", [("values", "values"), ("attributions", "attributions")])
    taxonomy = tv_purchase_reason_anchor_taxonomy_v0_1()
    generator = AnchorCandidateGenerator(taxonomy)
    scorer = PurchaseReasonProfileScoringService()
    profiles = []
    for sku in sorted(data) if all_members else (skus or [manifest["target"]]):
        facts = {**data[sku], **indexes[sku]}
        serving = (facts.get("serving_claim") or [{}])[0].get("batch_id")
        for field in ["claim_profile", "claim"]:
            facts[field] = [r for r in facts.get(field, []) if r["batch_id"] == serving]
        for row in facts.get("comment_profile", []):
            # The original comments stay in CatForge. Supply the cleaned witnesses retained in the graph.
            row["evidence_examples_json"] = [{"comment_fact_id": a["comment_fact_id"], "clean_comment_text": a["clean_comment_text"],
                                             "polarity": a["polarity"]} for a in facts.get("comment", [])[:8]]
            for atom in facts.get("comment", []):
                atom.update(rule_version=row["rule_version"], taxonomy_version=row["taxonomy_version"])
        ctx = SnapshotRows(manifest, facts).build_context(batch_id=manifest["batch_id"], sku_code=sku)
        outcome = scorer.score(candidate_set=generator.generate(ctx), context=ctx)
        profiles.append({**outcome.model_dump(mode="json"), "input_status": ctx.input_status_json,
                         "missing_inputs": ctx.missing_input_reasons_json})
    return save(out, "purchase-reason" if use_value else "purchase-reason-without-value", {
                "snapshot_id": snapshot.name, "inputs": parents, "rule_version": "m12d_sku_purchase_reason_profile_v0.1",
                "taxonomy": taxonomy.model_dump(mode="json"), "profiles": profiles})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    p.add_argument("out", type=Path)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--sku", action="append")
    scope.add_argument("--all-members", action="store_true")
    p.add_argument("--without-claim-value", action="store_true")
    a = p.parse_args()
    result = reasons(a.snapshot, a.out, a.sku, not a.without_claim_value, a.all_members)
    print(len(result["profiles"]), digest(result))
