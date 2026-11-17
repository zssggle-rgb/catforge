"""Package the deterministic scoring functions without shipping the factory or database runtime."""
import argparse
import ast
from collections import defaultdict
from pathlib import Path

from snapshot import atomic_write, digest

PROFILES = {
    "user-task": ("m09c_user_task_service", "M09CProfileBuilder", "user_tasks", "m09c_tv_user_task_profile_v0.3"),
    "target-group": ("m10c_target_group_service", "M10CProfileBuilder", "target_groups", "m10c_tv_target_group_profile_v0.3"),
    "value-battlefield": ("m11c_value_battlefield_service", "M11CProfileBuilder", "battlefields", "m11c_tv_value_battlefield_profile_v0.4"),
}
ALLOCATION = "semantic_market_graph_service"
VALUE = "m12c_claim_value_quantification_service"
VALUE_SYMBOLS = ["_market_state", "ClaimState", "CommentState", "SemanticState", "ParamProfileState",
                 "_param_profile_values", "_row_wtp_input_guard", "_row_param_support_level", "_merge_claim_states",
                 "_row_canonical_claim_name", "_row_canonical_claim_code", "_build_pools", "_pool_and_metric_rows",
                 "_quantification_rows", "_attribution_rows", "_dimension_summary_rows"]
ALLOCATION_SYMBOLS = ["M11DSemanticInputs", "_resolve_population", "_build_sku_market_map", "_build_relation_candidates",
                      "_build_allocations_and_checks", "_build_summaries_and_contributions"]
STDLIB = {"collections", "dataclasses", "datetime", "decimal", "enum", "functools", "hashlib", "itertools", "json",
          "math", "re", "statistics", "typing"}
REASON = "purchase_reason_context_builder"
REASON_MODULES = {REASON, "purchase_reason_profile_schemas", "purchase_reason_anchor_taxonomy",
                  "purchase_reason_anchor_candidate_generator", "purchase_reason_profile_scoring", "purchase_reason_input_quality",
                  "purchase_reason_establishment", "purchase_reason_pressure", "purchase_reason_anchor_quality"}
MODULES = {v[0] for v in PROFILES.values()} | {"constants", "hash_utils", ALLOCATION, VALUE} | REASON_MODULES
PREFIX = "app.services.core3_real_data."


def names(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, (ast.AnnAssign, ast.Assign)):
        return [t.id for t in ([node.target] if isinstance(node, ast.AnnAssign) else node.targets) if isinstance(t, ast.Name)]
    if isinstance(node, (ast.ImportFrom, ast.Import)):
        return [a.asname or a.name for a in node.names]
    return []


class RuntimeNames(ast.NodeVisitor):
    """The original ORM names occur only in postponed annotations."""
    def __init__(self):
        self.used = set()

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.used.add(node.id)

    def visit_arg(self, node):
        pass

    def visit_FunctionDef(self, node):
        for item in [*node.decorator_list, node.args, *node.body]:
            self.visit(item)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit(node.value)


def package(source, out):
    modules = {m: ast.parse((source / (m + ".py")).read_text()) for m in MODULES}
    # Only the context assembly and snapshot formatters cross the packaging boundary.
    # The offline subclass supplies typed row lookups from the frozen snapshot.
    builder = next(n for n in modules[REASON].body if isinstance(n, ast.ClassDef) and n.name == "SkuPurchaseReasonContextBuilder")
    builder.bases = []
    builder.body = [n for n in builder.body if isinstance(n, ast.FunctionDef) and (n.name == "build_context" or n.name.endswith("_snapshot"))]
    class EntityKeys(ast.NodeTransformer):
        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == "entities":
                return ast.copy_location(ast.Constant(node.attr), node)
            return self.generic_visit(node)
    EntityKeys().visit(builder)
    symbols = {m: {n: node for node in tree.body for n in names(node)} for m, tree in modules.items()}
    chosen = defaultdict(set)
    todo = [(m, n) for m, builder, _, _ in PROFILES.values() for n in (builder, "_build_sku_inputs")]
    todo += [(ALLOCATION, n) for n in ALLOCATION_SYMBOLS]
    todo += [(VALUE, n) for n in VALUE_SYMBOLS]
    todo += [(REASON, builder.name), ("purchase_reason_anchor_candidate_generator", "AnchorCandidateGenerator"),
             ("purchase_reason_profile_scoring", "PurchaseReasonProfileScoringService")]
    while todo:
        module, name = todo.pop()
        if name in chosen[module]:
            continue
        node = symbols[module][name]
        chosen[module].add(name)
        if isinstance(node, ast.ImportFrom) and node.module not in STDLIB | {"pydantic"}:
            other = (node.module or "").removeprefix(PREFIX)
            if other not in MODULES:
                raise ValueError("non-rule import: " + str(node.module) + "." + name)
            alias = next(a for a in node.names if (a.asname or a.name) == name)
            todo.append((other, alias.name))
        elif isinstance(node, ast.Import):
            if name not in STDLIB:
                raise ValueError("non-rule import: " + name)
        else:
            visitor = RuntimeNames()
            visitor.visit(node)
            if module == "purchase_reason_profile_schemas":
                visitor.used.update(n.id for n in ast.walk(node) if isinstance(n, ast.Name))
            todo.extend((module, n) for n in visitor.used & symbols[module].keys())
    hashes = {}
    for module, selected in sorted(chosen.items()):
        output = ["from __future__ import annotations"]
        for node in modules[module].body:
            wanted = selected.intersection(names(node))
            if not wanted:
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                node.names = [a for a in node.names if (a.asname or a.name) in wanted]
                if isinstance(node, ast.ImportFrom) and node.module.startswith(PREFIX):
                    node.module = node.module.removeprefix(PREFIX)
                    node.level = 1
            output.append(ast.unparse(node))
        content = "\n\n".join(output) + "\n"
        hashes[module] = digest(content)
        atomic_write(out / (module + ".py"), content)
    atomic_write(out / "__init__.py", "")
    atomic_write(out / "REVISION", digest(hashes))
    return digest(hashes)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    p.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2] / "apps/api-server/app/services/core3_real_data")
    a = p.parse_args()
    print(package(a.source, a.out))
