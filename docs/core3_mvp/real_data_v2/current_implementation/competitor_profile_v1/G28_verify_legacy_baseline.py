#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import gc
import gzip
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
DEFAULT_FIXTURE = (
    HERE / "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz"
)
DEFAULT_FIXTURES = (
    DEFAULT_FIXTURE,
    HERE / "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz",
    HERE / "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz",
    HERE / "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz",
)
EXPECTED_REAL_FIXTURES = {
    DEFAULT_FIXTURE.name: {
        "category_code": "TV",
        "target_sku_code": "TV00029112",
        "candidate_count": 20,
        "m12d_consumption_state": "published_ready",
    },
    "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz": {
        "category_code": "TV",
        "target_sku_code": "TV00009549",
        "candidate_count": 13,
        "m12d_consumption_state": "published_degraded",
    },
    "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz": {
        "category_code": "AC",
        "target_sku_code": "AC00026378",
        "candidate_count": 16,
        "m12d_consumption_state": "published_ready",
    },
    "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz": {
        "category_code": "AC",
        "target_sku_code": "AC00034959",
        "candidate_count": 20,
        "m12d_consumption_state": "published_degraded",
    },
}
DEFAULT_MAPPING = HERE / "G28_legacy_to_v11_field_mapping.json"
DEFAULT_MATRIX = HERE / "G28_gate_fixture_matrix.json"
DEFAULT_LEAF_INVENTORY = HERE / "G28_legacy_leaf_mapping_inventory.json.gz"
DEFAULT_FULL_UNIVERSE = (
    HERE / "G28_65e7q_v1_full_universe_205_20260715.json.gz"
)
EXPECTED_TOP3 = ["TV00027801", "TV00028909", "TV00029936"]
EXPECTED_CASES = {
    "tv_complete",
    "tv_m12d_missing",
    "tv_m05c_review",
    "tv_battlefield_conflict",
    "tv_market_only",
    "tv_configuration_only",
    "ac_complete",
    "ac_partial",
}
EXPECTED_HARD_EXCLUSIONS = {
    "self_pair",
    "project_mismatch",
    "category_mismatch",
    "candidate_outside_manifest",
    "identity_decode_failed",
}
EXPECTED_SOURCE_MODULES = {
    "M03B",
    "M04C",
    "M05C",
    "M07",
    "M09C",
    "M10C",
    "M11C",
    "M11D",
    "M12C",
    "M12D",
}
DIMENSION_CODES = {
    "market",
    "configuration",
    "semantic",
    "purchase_reason",
    "user_realization",
    "battlefield",
}
QUESTION_CODES = {
    "direct_choice",
    "price_volume_pressure",
    "configuration_attention",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized_leaf_paths(value: Any, prefix: str = "") -> set[str]:
    if isinstance(value, dict):
        if not value:
            return {prefix}
        result: set[str] = set()
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(_normalized_leaf_paths(child, child_prefix))
        return result
    if isinstance(value, list):
        if not value:
            return {prefix}
        result: set[str] = set()
        child_prefix = f"{prefix}[]"
        for child in value:
            result.update(_normalized_leaf_paths(child, child_prefix))
        return result
    return {prefix}


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"unsupported JSON value type: {type(value)!r}")


def _leaf_observations(
    value: Any,
    fixture_name: str,
    prefix: str = "",
    result: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    observations = result if result is not None else {}
    if isinstance(value, dict):
        if not value:
            _record_observation(
                observations,
                prefix=prefix,
                fixture_name=fixture_name,
                value=value,
                path_kind="empty_container",
            )
            return observations
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _leaf_observations(child, fixture_name, child_prefix, observations)
        return observations
    if isinstance(value, list) and value:
        child_prefix = f"{prefix}[]"
        for child in value:
            _leaf_observations(child, fixture_name, child_prefix, observations)
        return observations
    _record_observation(
        observations,
        prefix=prefix,
        fixture_name=fixture_name,
        value=value,
        path_kind="empty_container" if isinstance(value, list) else "value_leaf",
    )
    return observations


def _record_observation(
    observations: dict[str, dict[str, Any]],
    *,
    prefix: str,
    fixture_name: str,
    value: Any,
    path_kind: str,
) -> None:
    observation = observations.setdefault(
        prefix,
        {
            "occurrence_count": 0,
            "source_types": set(),
            "path_kinds": set(),
            "values_by_fixture": {},
        },
    )
    observation["occurrence_count"] += 1
    observation["source_types"].add(_json_type(value))
    observation["path_kinds"].add(path_kind)
    observation["values_by_fixture"].setdefault(fixture_name, []).append(value)


def _extract_normalized_values(value: Any, normalized_path: str) -> list[Any]:
    tokens = [token for token in normalized_path.split(".") if token]

    def visit(current: Any, index: int) -> list[Any]:
        if index == len(tokens):
            return [current]
        token = tokens[index]
        is_array = token.endswith("[]")
        key = token[:-2] if is_array else token
        if not isinstance(current, dict) or key not in current:
            return []
        child = current[key]
        if not is_array:
            return visit(child, index + 1)
        if not isinstance(child, list):
            return []
        if not child:
            return [[]] if index == len(tokens) - 1 else []
        result: list[Any] = []
        for item in child:
            result.extend(visit(item, index + 1))
        return result

    return visit(value, 0)


def _alias_value_hash(payload: dict[str, Any], source_path: str) -> str:
    candidate_roots = (
        ("legacy_input.candidates[]", payload["legacy_input"]["candidates"]),
        (
            "legacy_analysis.all_candidates[]",
            payload["legacy_analysis"]["all_candidates"],
        ),
    )
    for root, rows in candidate_roots:
        if source_path == root or source_path.startswith(f"{root}."):
            suffix = source_path[len(root) :].removeprefix(".")
            keyed: dict[str, list[Any]] = {}
            for row in rows:
                sku_code = str((row.get("candidate") or {}).get("sku_code") or "")
                assert sku_code and sku_code not in keyed
                keyed[sku_code] = (
                    [row]
                    if not suffix
                    else _extract_normalized_values(row, suffix)
                )
            return _sha256(_canonical_bytes(dict(sorted(keyed.items()))))
    return _sha256(
        _canonical_bytes(_extract_normalized_values(payload, source_path))
    )


def _covered(path: str, mapping: dict[str, Any]) -> bool:
    source = str(mapping["source"])
    mode = str(mapping["mode"])
    if mode == "scalar":
        return path == source
    return path == source or path.startswith(f"{source}.") or path.startswith(
        f"{source}[]"
    )


def _mapping_for_path(path: str, mappings: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [item for item in mappings if _covered(path, item)]
    assert matches, f"no mapping for legacy leaf path {path}"
    return max(matches, key=lambda item: len(str(item["source"])))


def _source_atom(path: str) -> str:
    atom_by_fragment = (
        ("purchase_reason", "m12d-purchase-reason-consumption"),
        ("m12d_consumption", "m12d-purchase-reason-consumption"),
        ("claim_contribution", "claim-contribution"),
        ("claim_value", "sku-claim-value"),
        ("fact_brief", "sku-fact-brief"),
        ("semantic_overlap", "semantic-overlap"),
        ("param_claim_overlap", "param-claim-overlap"),
        ("sales_overlap", "sales-overlap"),
        ("market_validation", "sales-overlap"),
        ("anchor_substitutability", "value-anchor-matcher"),
        ("value_anchor", "value-anchor-matcher"),
        ("replacement_pressure", "replacement-pressure-classifier"),
        ("purchase_pressure_comparison", "purchase-pressure-comparison"),
    )
    for fragment, atom in atom_by_fragment:
        if fragment in path:
            return atom
    if path.startswith("legacy_analysis."):
        return "competitor-answer"
    if path.startswith("legacy_input.candidates"):
        return "same-size-price-candidates"
    if path.startswith("legacy_input."):
        return "competitor-set"
    return "competitor-set-snapshot"


def _build_leaf_mapping_inventory(
    fixture_suite: dict[str, dict[str, Any]],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    observations: dict[str, dict[str, Any]] = {}
    for fixture_name, payload in sorted(fixture_suite.items()):
        _leaf_observations(payload, fixture_name, result=observations)
    mappings = mapping["mappings"]
    observed_paths: list[dict[str, Any]] = []
    for source_path in sorted(observations):
        rule = _mapping_for_path(source_path, mappings)
        source_prefix = str(rule["source"])
        suffix = source_path[len(source_prefix) :]
        target_prefix = str(rule.get("value_target", rule["target"]))
        source_types = sorted(observations[source_path]["source_types"])
        values_by_fixture = observations[source_path]["values_by_fixture"]
        observed_paths.append(
            {
                "source_path": source_path,
                "source_path_kind": sorted(
                    observations[source_path]["path_kinds"]
                ),
                "target_leaf_path": f"{target_prefix}{suffix}",
                "reference_path": rule.get("reference_path"),
                "mapping_rule_source": source_prefix,
                "mapping_mode": rule["mode"],
                "source_atom": _source_atom(source_path),
                "observed_source_types": source_types,
                "expected_target_types": source_types,
                "occurrence_count": observations[source_path]["occurrence_count"],
                "occurrence_count_by_fixture": {
                    fixture_name: len(values)
                    for fixture_name, values in sorted(values_by_fixture.items())
                },
                "value_sequence_sha256_by_fixture": {
                    fixture_name: _sha256(_canonical_bytes(values))
                    for fixture_name, values in sorted(values_by_fixture.items())
                },
                "observed_in_fixtures": sorted(values_by_fixture),
                "target_requirement": "conditional_required",
                "required_when": "legacy_source_path_present",
                "nullable_observed": "null" in source_types,
                "empty_container_observed": bool(
                    {"array", "object"}.intersection(source_types)
                ),
                "presence_policy": "required_when_legacy_source_path_present",
                "unknown_policy": (
                    "preserve_null_when_legacy_null; explicit_unknown_only_when_"
                    "legacy_source_absent"
                ),
                "missing_branch_policy": (
                    "emit_explicit_unknown_with_limitation; never_substitute_"
                    "zero_false_or_empty"
                ),
            }
        )

    path_by_source = {item["source_path"]: item for item in observed_paths}
    target_sources: dict[str, list[str]] = {}
    for item in observed_paths:
        target_sources.setdefault(item["target_leaf_path"], []).append(
            item["source_path"]
        )
    alias_groups: list[dict[str, Any]] = []
    for target_path, source_paths in sorted(target_sources.items()):
        if len(source_paths) < 2:
            continue
        sorted_sources = sorted(source_paths, key=_canonical_source_priority)
        jointly_observed = set(
            path_by_source[sorted_sources[0]]["observed_in_fixtures"]
        )
        for source_path in sorted_sources[1:]:
            jointly_observed.intersection_update(
                path_by_source[source_path]["observed_in_fixtures"]
            )
        equality_by_fixture: dict[str, bool] = {}
        comparison_hashes_by_fixture: dict[str, dict[str, str]] = {}
        for fixture_name in sorted(jointly_observed):
            source_hashes = {
                source_path: _alias_value_hash(
                    fixture_suite[fixture_name], source_path
                )
                for source_path in sorted_sources
            }
            comparison_hashes_by_fixture[fixture_name] = source_hashes
            equality_by_fixture[fixture_name] = len(set(source_hashes.values())) == 1
        consistent = bool(equality_by_fixture) and all(equality_by_fixture.values())
        assert consistent, (
            "legacy aliases map inconsistent values into one V1.1 target path: "
            f"{target_path} <- {sorted_sources}"
        )
        alias_groups.append(
            {
                "alias_group_id": f"alias_{len(alias_groups) + 1:04d}",
                "target_leaf_path": target_path,
                "canonical_source_path": sorted_sources[0],
                "alias_source_paths": sorted_sources[1:],
                "all_source_paths": sorted_sources,
                "value_equality_by_fixture": equality_by_fixture,
                "candidate_keyed_value_hashes_by_fixture": (
                    comparison_hashes_by_fixture
                ),
                "value_equality_required": True,
                "conflict_policy": "fail_g28_and_g29_roundtrip",
            }
        )

    empty_container_count = sum(
        item["empty_container_observed"] for item in observed_paths
    )
    inventory = {
        "inventory_version": "competitor_profile_v1_1_g28_observed_mapping_v2",
        "source_fixtures": sorted(fixture_suite),
        "source_fixture_count": len(fixture_suite),
        "source_observed_path_count": len(observed_paths),
        "source_value_leaf_path_count": len(observed_paths) - empty_container_count,
        "source_empty_container_path_count": empty_container_count,
        "mapping_rule_count": len(mappings),
        "unmapped_path_count": 0,
        "known_to_unknown_allowed": False,
        "typed_schema_complete": False,
        "typed_schema_completion_goal": "G29",
        "observed_paths": observed_paths,
        "target_alias_group_count": len(alias_groups),
        "target_alias_groups": alias_groups,
    }
    inventory["inventory_hash"] = _sha256(_canonical_bytes(inventory))
    return inventory


def _canonical_source_priority(source_path: str) -> tuple[int, int, str]:
    if source_path.startswith("snapshot."):
        priority = 0
    elif source_path.startswith("legacy_input."):
        priority = 1
    else:
        priority = 2
    return priority, len(source_path), source_path


def _write_deterministic_gzip(path: Path, value: Any) -> None:
    canonical = _canonical_bytes(value)
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_handle,
            mtime=0,
        ) as gzip_handle:
            gzip_handle.write(canonical)


def _recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(
            *(_recursive_keys(child) for child in value.values()),
        )
    if isinstance(value, list):
        return set().union(*(_recursive_keys(child) for child in value))
    return set()


def _apply_gate_mutation(pair_input: dict[str, Any], mutation: dict[str, Any]) -> None:
    module_facts = pair_input["module_facts"]
    operation = mutation["operation"]
    subjects = mutation.get("subjects", [])
    if operation == "remove_module_records":
        module_code = mutation["module_code"]
        facts = module_facts.get(module_code, {})
        for subject in subjects:
            facts.pop(subject, None)
        if not facts:
            module_facts.pop(module_code, None)
        return
    if operation == "retain_only_modules":
        retained = set(mutation["module_codes"])
        for module_code in list(module_facts):
            if module_code not in retained:
                module_facts.pop(module_code)
        return
    if operation == "set_review_required":
        facts = module_facts[mutation["module_code"]]
        for subject in subjects:
            subject_facts = facts[subject]
            subject_facts["_review_required"] = True
            subject_facts.setdefault("_review_reason_codes", []).append(
                mutation["reason_code"]
            )
        return
    if operation == "append_conflicting_record":
        facts = module_facts[mutation["module_code"]]
        for subject in subjects:
            facts[subject].setdefault("_conflicting_records", []).append(
                copy.deepcopy(mutation["facts"])
            )
        return
    if operation == "set_partial":
        for module_code in mutation["module_codes"]:
            facts = module_facts[module_code]
            for subject in subjects:
                facts[subject]["_availability"] = "partial"
        return
    if operation == "set_feature_values":
        feature_code = mutation["feature_code"]
        facts = module_facts.setdefault("M03B", {})
        facts.setdefault("target", {})[feature_code] = mutation["target_value"]
        facts.setdefault("candidate", {})[feature_code] = mutation[
            "candidate_value"
        ]
        return
    if operation == "set_feature_market_status":
        pair_input.setdefault("feature_market_context", {})[
            mutation["feature_code"]
        ] = {
            "status": mutation["status"],
            "prevalence": copy.deepcopy(mutation["prevalence"]),
        }
        return
    raise AssertionError(f"unsupported gate fixture mutation: {operation}")


def _materialize_gate_case(
    matrix: dict[str, Any], case: dict[str, Any]
) -> dict[str, Any]:
    pair_input = copy.deepcopy(matrix["base_inputs"][case["base_input_ref"]])
    for mutation in case["input_mutations"]:
        _apply_gate_mutation(pair_input, mutation)
    return pair_input


def _module_state(module_facts: dict[str, Any], module_code: str) -> str:
    facts = module_facts.get(module_code)
    if not facts or not any(subject in facts for subject in ("target", "candidate")):
        return "missing"
    subject_facts = [
        facts[subject]
        for subject in ("target", "candidate")
        if isinstance(facts.get(subject), dict)
    ]
    if any(item.get("_conflicting_records") for item in subject_facts):
        return "conflict"
    if any(item.get("_review_required") for item in subject_facts):
        return "review"
    if any(item.get("_availability") == "partial" for item in subject_facts):
        return "partial"
    return "available"


def _dimension_from_states(
    states: dict[str, str],
    module_codes: tuple[str, ...],
    *,
    conflict_as_conflict: bool = True,
) -> str:
    selected = [states[code] for code in module_codes]
    if all(state == "missing" for state in selected):
        return "unknown"
    if conflict_as_conflict and any(state in {"conflict", "review"} for state in selected):
        return "conflict"
    if all(state == "available" for state in selected):
        return "available"
    return "partial"


def _hard_exclusion_reasons(pair_input: dict[str, Any]) -> list[str]:
    target = pair_input["target"]
    candidate = pair_input["candidate"]
    scope = pair_input["scope"]
    reasons: list[str] = []
    if target.get("sku_code") == candidate.get("sku_code"):
        reasons.append("self_pair")
    if scope.get("target_project_id") != scope.get("candidate_project_id"):
        reasons.append("project_mismatch")
    if target.get("category_code") != candidate.get("category_code"):
        reasons.append("category_mismatch")
    if candidate.get("sku_code") not in set(
        scope.get("authoritative_manifest_sku_codes") or []
    ):
        reasons.append("candidate_outside_manifest")
    if not scope.get("target_identity_decoded") or not scope.get(
        "candidate_identity_decoded"
    ):
        reasons.append("identity_decode_failed")
    return [code for code in sorted(EXPECTED_HARD_EXCLUSIONS) if code in reasons]


def _semantic_content_alignment(module_facts: dict[str, Any]) -> str:
    comparisons = (
        ("M09C", "primary_user_task_code"),
        ("M10C", "primary_target_group_code"),
        ("M11C", "primary_battlefield_code"),
    )
    observed: list[bool] = []
    for module_code, key in comparisons:
        module = module_facts.get(module_code) or {}
        target_value = (module.get("target") or {}).get(key)
        candidate_value = (module.get("candidate") or {}).get(key)
        if target_value is None or candidate_value is None:
            continue
        observed.append(target_value == candidate_value)
    if not observed:
        return "unknown"
    if all(observed):
        return "aligned"
    if any(observed):
        return "partial"
    return "divergent"


def _purchase_pool_contract(pair_input: dict[str, Any]) -> dict[str, Any]:
    module = pair_input.get("module_facts", {}).get("M03B", {})
    target = module.get("target") or {}
    candidate = module.get("candidate") or {}
    category_code = pair_input["target"]["category_code"]
    if category_code == "AC":
        form_known = bool(
            target.get("ac_product_form") and candidate.get("ac_product_form")
        )
        capacity_known = bool(
            target.get("cooling_capacity_segment")
            and candidate.get("cooling_capacity_segment")
        )
        form_match = form_known and (
            target["ac_product_form"] == candidate["ac_product_form"]
        )
        capacity_match = capacity_known and (
            target["cooling_capacity_segment"]
            == candidate["cooling_capacity_segment"]
        )
        if form_match and capacity_match:
            level = "P0"
        elif form_match or capacity_match:
            level = "P1"
        elif form_known or capacity_known:
            level = "P2"
        else:
            level = "unknown"
        return {
            "category_code": "AC",
            "method": "ac_product_form_and_capacity_segment",
            "level": level,
            "product_form_match": form_match if form_known else None,
            "capacity_segment_match": capacity_match if capacity_known else None,
        }
    target_size = target.get("screen_size_inch")
    candidate_size = candidate.get("screen_size_inch")
    size_known = target_size is not None and candidate_size is not None
    return {
        "category_code": "TV",
        "method": "tv_screen_size",
        "level": "P0" if size_known and target_size == candidate_size else "unknown",
        "screen_size_match": (
            target_size == candidate_size if size_known else None
        ),
    }


def _gate_contract_oracle(pair_input: dict[str, Any]) -> dict[str, Any]:
    hard_exclusion_reasons = _hard_exclusion_reasons(pair_input)
    if hard_exclusion_reasons:
        return {
            "scope_status": "excluded",
            "hard_exclusion_reasons": hard_exclusion_reasons,
            "must_continue": [],
        }
    module_facts = pair_input["module_facts"]
    states = {
        module_code: _module_state(module_facts, module_code)
        for module_code in sorted(EXPECTED_SOURCE_MODULES)
    }
    semantic = _dimension_from_states(
        states,
        ("M09C", "M10C", "M11C", "M11D"),
        conflict_as_conflict=False,
    )
    purchase_reason = _dimension_from_states(states, ("M12D",))
    battlefield = _dimension_from_states(states, ("M11C", "M11D"))
    if states["M05C"] in {"review", "conflict"}:
        user_realization = "conflict"
    elif states["M05C"] == "missing" or states["M12C"] == "missing":
        user_realization = "unknown"
    elif states["M12D"] == "missing" or any(
        states[code] == "partial" for code in ("M05C", "M12C", "M12D")
    ):
        user_realization = "partial"
    else:
        user_realization = "available"
    configuration = _dimension_from_states(
        states, ("M03B", "M04C", "M12C")
    )
    if states["M04C"] == states["M12C"] == "missing":
        configuration = "unknown"
    dimensions = {
        "market": _dimension_from_states(states, ("M07",)),
        "configuration": configuration,
        "semantic": semantic,
        "purchase_reason": purchase_reason,
        "user_realization": user_realization,
        "battlefield": battlefield,
    }
    semantic_content_alignment = _semantic_content_alignment(module_facts)

    direct_dimensions = (
        dimensions["semantic"],
        dimensions["purchase_reason"],
        dimensions["user_realization"],
        dimensions["battlefield"],
    )
    if (
        all(value in {"available", "conflict"} for value in direct_dimensions)
        and dimensions["battlefield"] != "conflict"
        and semantic_content_alignment in {"aligned", "partial"}
    ):
        direct_choice = "supported"
    elif any(value != "unknown" for value in direct_dimensions):
        direct_choice = "directional"
    else:
        direct_choice = "unknown"
    if dimensions["market"] == "unknown":
        price_volume = "unknown"
    elif any(value != "unknown" for value in direct_dimensions):
        price_volume = "supported"
    else:
        price_volume = "directional"
    if dimensions["configuration"] == "unknown":
        configuration_attention = "unknown"
    elif any(
        dimensions[code] != "unknown"
        for code in ("market", "semantic", "purchase_reason")
    ):
        configuration_attention = "supported"
    else:
        configuration_attention = "directional"

    feature_assessments: dict[str, Any] = {}
    for feature_code, context in sorted(
        pair_input.get("feature_market_context", {}).items()
    ):
        target_value = module_facts.get("M03B", {}).get("target", {}).get(
            feature_code
        )
        candidate_value = module_facts.get("M03B", {}).get("candidate", {}).get(
            feature_code
        )
        foundational = context["status"] == "foundational"
        feature_assessments[feature_code] = {
            "target_value": target_value,
            "candidate_value": candidate_value,
            "raw_difference_preserved": target_value != candidate_value,
            "feature_market_status": context["status"],
            "prevalence": context["prevalence"],
            "differentiation_score_contribution": 0 if foundational else None,
            "ranking_reason_eligible": not foundational,
        }

    known_dimensions = {
        code for code, availability in dimensions.items() if availability != "unknown"
    }
    category_code = pair_input["target"]["category_code"]
    continuations: list[str] = []
    if category_code == "AC":
        continuations.append("ac_purchase_pool")
    if all(value == "available" for value in dimensions.values()):
        continuations.extend(
            ["all_dimensions", "role_assignment", "priority_selection"]
        )
    elif known_dimensions == {"market"}:
        continuations.extend(
            [
                "market_analysis",
                "price_volume_question",
                "market_reference_selection",
            ]
        )
    elif known_dimensions == {"configuration"}:
        continuations.extend(
            [
                "configuration_analysis",
                "foundational_feature_filter",
                "configuration_benchmark_selection",
            ]
        )
    elif dimensions["user_realization"] == "conflict":
        continuations.extend(
            [
                "all_non_conflict_dimensions",
                "directional_user_realization",
                "priority_selection",
            ]
        )
    elif dimensions["battlefield"] == "conflict":
        continuations.extend(
            [
                "all_non_conflict_dimensions",
                "limited_relations",
                "specialty_selection",
            ]
        )
    elif category_code == "AC":
        continuations.extend(["known_dimensions", "specialty_selection"])
    else:
        continuations.extend(
            [
                "market_analysis",
                "configuration_analysis",
                "semantic_analysis",
                "specialty_selection",
            ]
        )

    return {
        "scope_status": "analyzable",
        "hard_exclusion_reasons": [],
        "must_continue": continuations,
        "module_states": states,
        "dimension_availability": dimensions,
        "semantic_content_alignment": semantic_content_alignment,
        "purchase_pool": _purchase_pool_contract(pair_input),
        "question_strength": {
            "direct_choice": direct_choice,
            "price_volume_pressure": price_volume,
            "configuration_attention": configuration_attention,
        },
        "review_required": any(
            state in {"review", "conflict"} for state in states.values()
        ),
        "conflict_dimensions": sorted(
            code for code, availability in dimensions.items() if availability == "conflict"
        ),
        "feature_assessments": feature_assessments,
    }


def _execute_hard_exclusion_properties(matrix: dict[str, Any]) -> dict[str, Any]:
    complete_case = next(
        item for item in matrix["cases"] if item["case_code"] == "tv_complete"
    )
    base = _materialize_gate_case(matrix, complete_case)
    mutations: dict[str, Callable[[dict[str, Any]], None]] = {
        "self_pair": lambda value: value["candidate"].__setitem__(
            "sku_code", value["target"]["sku_code"]
        ),
        "project_mismatch": lambda value: value["scope"].__setitem__(
            "candidate_project_id", "different-project"
        ),
        "category_mismatch": lambda value: value["candidate"].__setitem__(
            "category_code", "AC"
        ),
        "candidate_outside_manifest": lambda value: value["scope"].__setitem__(
            "authoritative_manifest_sku_codes", [value["target"]["sku_code"]]
        ),
        "identity_decode_failed": lambda value: value["scope"].__setitem__(
            "candidate_identity_decoded", False
        ),
    }
    results: list[dict[str, Any]] = []
    for reason_code in sorted(mutations):
        pair_input = copy.deepcopy(base)
        mutations[reason_code](pair_input)
        actual = _gate_contract_oracle(pair_input)
        assert actual == {
            "scope_status": "excluded",
            "hard_exclusion_reasons": [reason_code],
            "must_continue": [],
        }
        results.append(
            {
                "reason_code": reason_code,
                "input_hash": _sha256(_canonical_bytes(pair_input)),
                "result_hash": _sha256(_canonical_bytes(actual)),
            }
        )
    payload = {"case_count": len(results), "cases": results}
    payload["result_hash"] = _sha256(_canonical_bytes(payload))
    return payload


def _execute_semantic_sensitivity(matrix: dict[str, Any]) -> dict[str, Any]:
    complete_case = next(
        item for item in matrix["cases"] if item["case_code"] == "tv_complete"
    )
    aligned_input = _materialize_gate_case(matrix, complete_case)
    divergent_input = copy.deepcopy(aligned_input)
    divergent_input["module_facts"]["M09C"]["candidate"][
        "primary_user_task_code"
    ] = "TASK_DIFFERENT"
    divergent_input["module_facts"]["M10C"]["candidate"][
        "primary_target_group_code"
    ] = "TG_DIFFERENT"
    divergent_input["module_facts"]["M11C"]["candidate"][
        "primary_battlefield_code"
    ] = "BF_DIFFERENT"
    aligned = _gate_contract_oracle(aligned_input)
    divergent = _gate_contract_oracle(divergent_input)
    assert aligned["dimension_availability"]["semantic"] == "available"
    assert divergent["dimension_availability"]["semantic"] == "available"
    assert aligned["semantic_content_alignment"] == "aligned"
    assert divergent["semantic_content_alignment"] == "divergent"
    assert aligned["question_strength"]["direct_choice"] == "supported"
    assert divergent["question_strength"]["direct_choice"] == "directional"
    payload = {
        "mutation": "replace_candidate_task_group_battlefield_codes",
        "availability_unchanged": True,
        "aligned_result_hash": _sha256(_canonical_bytes(aligned)),
        "divergent_result_hash": _sha256(_canonical_bytes(divergent)),
        "direct_choice_before": aligned["question_strength"]["direct_choice"],
        "direct_choice_after": divergent["question_strength"]["direct_choice"],
    }
    assert payload["aligned_result_hash"] != payload["divergent_result_hash"]
    payload["result_hash"] = _sha256(_canonical_bytes(payload))
    return payload


def _execute_gate_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    assert matrix["runtime_behavior_proven"] is False
    assert "future executable contract golden" in matrix["fixture_purpose"]
    case_results: list[dict[str, Any]] = []
    for case in sorted(matrix["cases"], key=lambda item: item["case_code"]):
        pair_input = _materialize_gate_case(matrix, case)
        actual = _gate_contract_oracle(pair_input)
        assert actual["scope_status"] == case["scope_status"]
        assert actual["must_continue"] == case["must_continue"]
        assert actual["module_states"] == case["module_states"]
        assert actual["dimension_availability"] == case["dimension_expectations"]
        assert actual["question_strength"] == case["required_question_strength"]
        assert actual["review_required"] == case["review_required"]
        assert actual["conflict_dimensions"] == sorted(
            case.get("conflict_dimensions", [])
        )
        forbidden = set(case.get("forbidden_assumptions", []))
        assert not forbidden.intersection(_recursive_keys(pair_input))
        assert not forbidden.intersection(_recursive_keys(actual))
        if "purchase_pool_expectation" in case:
            expected_pool = case["purchase_pool_expectation"]
            actual_pool = actual["purchase_pool"]
            assert all(actual_pool[key] == value for key, value in expected_pool.items())
        if case["case_code"] == "tv_configuration_only":
            hdmi = actual["feature_assessments"]["hdmi_2_1"]
            assert hdmi["raw_difference_preserved"]
            assert hdmi["feature_market_status"] == "foundational"
            assert hdmi["differentiation_score_contribution"] == 0
            assert not hdmi["ranking_reason_eligible"]
        case_payload = {
            "case_code": case["case_code"],
            "materialized_input_hash": _sha256(_canonical_bytes(pair_input)),
            "actual": actual,
        }
        case_payload["result_hash"] = _sha256(_canonical_bytes(case_payload))
        case_results.append(case_payload)
    result = {
        "oracle_version": "g28-v1.1-future-g34-contract-oracle-v2",
        "runtime_behavior_proven": False,
        "evidence_scope": (
            "deterministic future-contract golden only; current V1 runtime behavior "
            "is not inferred from this oracle"
        ),
        "case_count": len(case_results),
        "cases": case_results,
        "hard_exclusion_properties": _execute_hard_exclusion_properties(matrix),
        "semantic_content_sensitivity": _execute_semantic_sensitivity(matrix),
        "foundational_feature_scope": (
            "downstream behavior after an externally supplied foundational status; "
            "prevalence classification and threshold remain G29 work"
        ),
    }
    result["matrix_result_hash"] = _sha256(_canonical_bytes(result))
    return result


def _timed(callable_: Callable[[], Any], repeats: int = 3) -> dict[str, Any]:
    elapsed_ms: list[float] = []
    result: Any = None
    tracemalloc.start()
    for _ in range(repeats):
        started = time.perf_counter()
        result = callable_()
        elapsed_ms.append((time.perf_counter() - started) * 1000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "repeats": repeats,
        "samples_ms": [round(value, 3) for value in elapsed_ms],
        "cold_ms": round(elapsed_ms[0], 3),
        "warm_ms": (
            _series(elapsed_ms[1:]) if len(elapsed_ms) > 1 else None
        ),
        "min_ms": round(min(elapsed_ms), 3),
        "median_ms": round(statistics.median(elapsed_ms), 3),
        "p95_ms": round(_percentile(elapsed_ms, 0.95), 3),
        "max_ms": round(max(elapsed_ms), 3),
        "peak_memory_mib": round(peak / 1024 / 1024, 3),
        "result": result,
    }


def _percentile(values: list[float], quantile: float) -> float:
    assert values
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (
        position - lower
    )


def _series(values: list[float]) -> dict[str, Any]:
    assert values
    return {
        "samples": [round(value, 3) for value in values],
        "p50": round(statistics.median(values), 3),
        "p95": round(_percentile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def _leaf_value_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_value_count(child) for child in value.values())
    if isinstance(value, list):
        return max(1, sum(_leaf_value_count(child) for child in value))
    return 1


def _physical_memory_bytes() -> int | None:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (OSError, TypeError, ValueError):
        return None


def _load_fixture(path: Path) -> tuple[dict[str, Any], bytes]:
    with gzip.open(path, "rb") as handle:
        raw = handle.read()
    return json.loads(raw), raw


def _validate_full_universe(
    full_universe: dict[str, Any],
    legacy_candidate_codes: list[str],
) -> dict[str, Any]:
    fixture_hash = full_universe["fixture_hash"]
    unhashed = {
        key: value for key, value in full_universe.items() if key != "fixture_hash"
    }
    assert fixture_hash == _sha256(_canonical_bytes(unhashed))
    assert full_universe["source_environment"] == "205-read-only"
    assert full_universe["transaction_mode"] == "READ ONLY"
    assert full_universe["canonical_order"] == (
        "candidate_sku_code_ascending;relation_candidate_and_code_ascending"
    )
    assert full_universe["profile"]["target_sku_code"] == "TV00029112"
    assert full_universe["version"]["competitor_profile_version_id"] == (
        "c45c0002-9b8a-4b0d-8b12-344dee020e15"
    )
    candidates = full_universe["candidates"]
    candidate_codes = [item["candidate_sku_code"] for item in candidates]
    assert full_universe["candidate_count"] == len(candidates) == 352
    assert candidate_codes == sorted(set(candidate_codes))
    assert [item["candidate_order"] for item in candidates] == list(
        range(1, len(candidates) + 1)
    )
    assert set(legacy_candidate_codes).issubset(candidate_codes)
    assert len(legacy_candidate_codes) == 20
    for item in candidates:
        assert item["recall_sources_json"]
        assert item["candidate_status"]
        assert item["result_hash"].startswith(
            "sha256:competitor_profile_materialized_pair_result_v1:"
        )

    pair_status_counts: dict[str, int] = {}
    for candidate in candidates:
        status = candidate["candidate_status"]
        pair_status_counts[status] = pair_status_counts.get(status, 0) + 1
    assert dict(sorted(pair_status_counts.items())) == full_universe[
        "pair_status_counts"
    ]
    assert full_universe["pair_status_counts"] == full_universe["profile"][
        "candidate_status_counts_json"
    ]

    relations = full_universe["relations"]
    assert full_universe["target_relation_count"] == len(relations) == (
        len(candidates) * 7
    )
    relation_keys = [
        (item["candidate_sku_code"], item["relation_code"])
        for item in relations
    ]
    assert relation_keys == sorted(relation_keys)
    assert len(relation_keys) == len(set(relation_keys))
    candidate_code_set = set(candidate_codes)
    relation_count_by_candidate: dict[str, int] = {}
    relation_status_counts: dict[str, int] = {}
    for relation in relations:
        candidate_code = relation["candidate_sku_code"]
        assert candidate_code in candidate_code_set
        relation_count_by_candidate[candidate_code] = (
            relation_count_by_candidate.get(candidate_code, 0) + 1
        )
        status = relation["relation_status"]
        relation_status_counts[status] = relation_status_counts.get(status, 0) + 1
    assert set(relation_count_by_candidate.values()) == {7}
    assert dict(sorted(relation_status_counts.items())) == full_universe[
        "relation_status_counts"
    ]
    assert full_universe["relation_status_counts"] == full_universe["profile"][
        "relation_status_counts_json"
    ]
    assert full_universe["relation_index_hash"] == _sha256(
        _canonical_bytes(relations)
    )

    relation_index = {
        (item["candidate_sku_code"], item["relation_code"]): item
        for item in relations
    }
    top3_full = full_universe["legacy_top3_full"]
    assert [item["candidate_sku_code"] for item in top3_full] == EXPECTED_TOP3
    for expected_rank, item in enumerate(top3_full, start=1):
        assert item["legacy_rank"] == expected_rank
        assert item["pair"]["candidate_sku_code"] == item["candidate_sku_code"]
        assert "pair_payload_json" in item["pair"]
        assert len(item["relations"]) == 7
        for relation in item["relations"]:
            assert "relation_payload_json" in relation
            key = (relation["candidate_sku_code"], relation["relation_code"])
            indexed = relation_index[key]
            assert indexed["relation_status"] == relation["relation_status"]
            assert indexed["result_hash"] == relation["result_hash"]
            assert indexed["eligible_question_codes_json"] == relation[
                "eligible_question_codes_json"
            ]

    selections = full_universe["selections"]
    assert [item["selection_rank"] for item in selections] == list(
        range(1, len(selections) + 1)
    )
    return {
        "fixture_hash": fixture_hash,
        "candidate_count": len(candidates),
        "candidate_code_hash": _sha256(_canonical_bytes(candidate_codes)),
        "legacy_candidate_subset_count": len(legacy_candidate_codes),
        "legacy_default20_subset_complete": True,
        "target_relation_count": full_universe["target_relation_count"],
        "relation_index_hash": full_universe["relation_index_hash"],
        "legacy_top3_full_count": len(top3_full),
        "legacy_top3_relation_count": sum(
            len(item["relations"]) for item in top3_full
        ),
        "pair_status_counts": full_universe["pair_status_counts"],
        "relation_status_counts": full_universe["relation_status_counts"],
        "selection_count": len(selections),
        "version_result_hash": full_universe["version"]["result_hash"],
        "candidate_universe_fingerprint": full_universe["version"][
            "candidate_universe_fingerprint"
        ],
    }


def _pair_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = {
        item["candidate"]["sku_code"]: item
        for item in payload["legacy_input"]["candidates"]
    }
    analyses = {
        item["candidate"]["sku_code"]: item
        for item in payload["legacy_analysis"]["all_candidates"]
    }
    assert set(inputs) == set(analyses), "input/analysis candidate sets differ"
    return [
        {
            "candidate_sku_code": sku_code,
            "legacy_input": inputs[sku_code],
            "legacy_analysis": analyses[sku_code],
        }
        for sku_code in sorted(inputs)
    ]


def _validate_real_fixture(
    fixture_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    expected = EXPECTED_REAL_FIXTURES[fixture_name]
    assert set(payload) == {"snapshot", "legacy_input", "legacy_analysis"}
    forbidden_display_fields = {
        "short_answer",
        "report_payload",
        "pm_comparison_report_payload",
        "dashboard_payload",
        "feishu_card_payload",
        "display_policy",
    }
    assert not forbidden_display_fields.intersection(_recursive_keys(payload))
    candidates = payload["legacy_input"]["candidates"]
    analyzed = payload["legacy_analysis"]["all_candidates"]
    top3 = payload["legacy_analysis"]["top_competitors"]
    candidate_count = expected["candidate_count"]
    assert payload["snapshot"]["status"] == "ok"
    assert payload["snapshot"]["category_code"] == expected["category_code"]
    assert payload["snapshot"]["target"]["sku_code"] == expected[
        "target_sku_code"
    ]
    assert payload["legacy_input"]["candidate_count"] == candidate_count
    assert 1 <= candidate_count <= 20
    assert len(candidates) == len(analyzed) == candidate_count
    assert len(top3) == min(3, candidate_count)
    input_codes = [item["candidate"]["sku_code"] for item in candidates]
    analyzed_codes = [item["candidate"]["sku_code"] for item in analyzed]
    assert len(set(input_codes)) == candidate_count
    assert len(set(analyzed_codes)) == candidate_count
    assert set(input_codes) == set(analyzed_codes)
    target_contract = candidates[0]["m12d_consumption"]["target_contract"]
    assert target_contract["consumption_state"] == expected[
        "m12d_consumption_state"
    ]
    return {
        "fixture": fixture_name,
        "category_code": expected["category_code"],
        "target_sku_code": expected["target_sku_code"],
        "candidate_count": candidate_count,
        "top3_sku_codes": [
            item["candidate"]["sku_code"] for item in top3
        ],
        "m12d_consumption_state": target_contract["consumption_state"],
        "m12d_downstream_action": target_contract["downstream_action"],
        "canonical_result_hash": _sha256(_canonical_bytes(payload)),
    }


def _validate(
    fixture_suite: dict[str, dict[str, Any]],
    mapping: dict[str, Any],
    matrix: dict[str, Any],
    leaf_inventory: dict[str, Any] | None = None,
    full_universe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert set(fixture_suite) == set(EXPECTED_REAL_FIXTURES)
    fixture_results = [
        _validate_real_fixture(fixture_name, payload)
        for fixture_name, payload in sorted(fixture_suite.items())
    ]
    payload = fixture_suite[DEFAULT_FIXTURE.name]
    candidates = payload["legacy_input"]["candidates"]
    top3 = payload["legacy_analysis"]["top_competitors"]
    assert [item["candidate"]["sku_code"] for item in top3] == EXPECTED_TOP3

    observed_source_paths: set[str] = set()
    for fixture_payload in fixture_suite.values():
        observed_source_paths.update(_normalized_leaf_paths(fixture_payload))
    mappings = mapping["mappings"]
    uncovered = sorted(
        path
        for path in observed_source_paths
        if not any(_covered(path, item) for item in mappings)
    )
    assert not uncovered, f"unmapped legacy observed paths: {uncovered[:20]}"

    case_codes = {item["case_code"] for item in matrix["cases"]}
    assert case_codes == EXPECTED_CASES
    assert set(matrix["hard_exclusion_codes"]) == EXPECTED_HARD_EXCLUSIONS
    assert set(matrix["source_modules"]) == EXPECTED_SOURCE_MODULES
    for case in matrix["cases"]:
        assert case["scope_status"] == "analyzable"
        assert case["must_continue"]
        assert case["base_input_ref"] in matrix["base_inputs"]
        assert set(case["module_states"]) == EXPECTED_SOURCE_MODULES
        assert isinstance(case["input_mutations"], list)
        assert set(case["dimension_expectations"]) == DIMENSION_CODES
        assert set(case["required_question_strength"]) == QUESTION_CODES

    generated_inventory = _build_leaf_mapping_inventory(fixture_suite, mapping)
    assert generated_inventory["source_observed_path_count"] == len(
        observed_source_paths
    )
    assert generated_inventory["source_empty_container_path_count"] > 0
    assert generated_inventory["target_alias_group_count"] > 0
    if leaf_inventory is not None:
        assert leaf_inventory == generated_inventory
    gate_execution = _execute_gate_matrix(matrix)
    full_universe_result = None
    if full_universe is not None:
        full_universe_result = _validate_full_universe(
            full_universe,
            [item["candidate"]["sku_code"] for item in candidates],
        )

    pairs = _pair_payloads(payload)
    pair_sizes = [_canonical_bytes(pair) for pair in pairs]
    target_snapshot = {
        "target": payload["snapshot"]["target"],
        "target_fact_brief": payload["legacy_input"]["target_fact_brief"],
        "target_claim_value": payload["legacy_input"]["target_claim_value"],
        "target_claim_contribution": payload["legacy_input"][
            "target_claim_contribution"
        ],
    }
    return {
        "candidate_count": len(candidates),
        "top3_sku_codes": EXPECTED_TOP3,
        "real_fixture_count": len(fixture_suite),
        "real_fixtures": fixture_results,
        "legacy_observed_path_count": len(observed_source_paths),
        "legacy_value_leaf_path_count": generated_inventory[
            "source_value_leaf_path_count"
        ],
        "legacy_empty_container_path_count": generated_inventory[
            "source_empty_container_path_count"
        ],
        "target_alias_group_count": generated_inventory[
            "target_alias_group_count"
        ],
        "mapping_count": len(mappings),
        "mapping_coverage_pct": 100.0,
        "leaf_inventory_hash": generated_inventory["inventory_hash"],
        "gate_fixture_case_count": len(matrix["cases"]),
        "gate_matrix_result_hash": gate_execution["matrix_result_hash"],
        "gate_case_result_hashes": {
            item["case_code"]: item["result_hash"]
            for item in gate_execution["cases"]
        },
        "full_v1_universe": full_universe_result,
        "storage": {
            "target_snapshot_bytes": len(_canonical_bytes(target_snapshot)),
            "single_pair_min_bytes": min(map(len, pair_sizes)),
            "single_pair_median_bytes": int(
                statistics.median(map(len, pair_sizes))
            ),
            "single_pair_max_bytes": max(map(len, pair_sizes)),
            "default20_candidate_payload_bytes": sum(map(len, pair_sizes)),
            "naive_377_pair_projection_bytes": round(
                statistics.mean(map(len, pair_sizes)) * 377
            ),
        },
    }


def _legacy_benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    api_root = REPO_ROOT / "apps" / "api-server"
    sys.path.insert(0, str(api_root))
    from app.services.core3_real_data.analyst.competitor_answer import (  # noqa: PLC0415
        build_competitor_answer,
    )

    target = payload["snapshot"]["target"]
    fact_brief = payload["legacy_input"]["target_fact_brief"]
    candidates = payload["legacy_input"]["candidates"]

    def run(selected: list[dict[str, Any]]) -> dict[str, Any]:
        answer = build_competitor_answer(
            target=target,
            target_fact_brief=fact_brief,
            target_claim_value=payload["legacy_input"]["target_claim_value"],
            target_claim_contribution=payload["legacy_input"][
                "target_claim_contribution"
            ],
            competitors=selected,
            top_n=min(3, len(selected)),
            with_report="none",
        )
        return {
            "candidate_count": len(answer["all_candidates"]),
            "top_sku_codes": [
                item["candidate"]["sku_code"]
                for item in answer["top_competitors"]
            ],
            "analysis_hash": _sha256(
                _canonical_bytes(
                    {
                        "all_candidates": answer["all_candidates"],
                        "top_competitors": answer["top_competitors"],
                        "candidate_buckets": answer["candidate_buckets"],
                    }
                )
            ),
        }

    single = _timed(lambda: run(candidates[:1]), repeats=3)
    full_first = _timed(lambda: run(candidates), repeats=3)
    full_second = run(candidates)
    assert full_first["result"]["analysis_hash"] == full_second["analysis_hash"]
    return {
        "single_pair": single,
        "single_sku_default20_candidates": full_first,
        "default_candidate_limit": 20,
        "actual_candidate_count": len(candidates),
        "deterministic_rerun_hash": full_second["analysis_hash"],
        "code_path": "build_competitor_answer(with_report=none)",
    }


def _provider_select_baseline(category: str) -> dict[str, Any]:
    api_root = REPO_ROOT / "apps" / "api-server"
    sys.path.insert(0, str(api_root))
    from sqlalchemy import create_engine, event  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415
    from sqlalchemy.pool import StaticPool  # noqa: PLC0415

    from app.models import entities  # noqa: PLC0415
    from tests.core3_real_data.test_competitor_profile_input_provider import (  # noqa: PLC0415
        _provider,
        _request,
        _seed_category,
    )

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    entities.Base.metadata.create_all(engine)
    session = Session(engine, autoflush=False, future=True)
    try:
        _seed_category(session, category=category)
        provider = _provider(session, category)
        select_count = 0

        def count_selects(_, __, statement, ___, ____, _____) -> None:
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            bundle = provider.load_category_input_bundle(_request(category))
            category_select_count = select_count
            provider.load_target_input(bundle, f"{category}000001")
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)
        return {
            "category_bundle_select_count": category_select_count,
            "target_incremental_select_count": select_count - category_select_count,
            "total_select_count": select_count,
            "scale_behavior": "fixed_query_count; no_target_n_plus_one",
            "database": "ephemeral_in_memory_sqlite_fixture",
        }
    finally:
        session.close()
        engine.dispose()


def _materializer_scale_runs(
    bundle: Any,
    target: Any,
    config: Any,
    *,
    repeats: int,
) -> dict[str, Any]:
    from app.services.core3_real_data.analyst.competitor_profile_materializer import (  # noqa: PLC0415
        CompetitorProfileMaterializer,
    )

    runs: list[dict[str, Any]] = []
    storage: dict[str, Any] | None = None
    for run_number in range(1, repeats + 1):
        gc.collect()
        tracemalloc.start()
        tracemalloc.reset_peak()
        started = time.perf_counter()
        materialized = CompetitorProfileMaterializer().materialize(
            bundle, target, config
        )
        materialization_ms = (time.perf_counter() - started) * 1000
        serialization_started = time.perf_counter()
        draft_payload = materialized.draft.model_dump(mode="json")
        canonical = _canonical_bytes(draft_payload)
        serialization_ms = (time.perf_counter() - serialization_started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        pair_count = len(materialized.draft.pairs)
        relation_count = sum(
            len(pair.relation_assessments) for pair in materialized.draft.pairs
        )
        if storage is None:
            pair_payloads = [
                pair.model_dump(mode="json") for pair in materialized.draft.pairs
            ]
            pair_bytes = [len(_canonical_bytes(pair)) for pair in pair_payloads]
            pair_fields = [_leaf_value_count(pair) for pair in pair_payloads]
            storage = {
                "serialized_draft_bytes": len(canonical),
                "serialized_draft_leaf_value_count": _leaf_value_count(
                    draft_payload
                ),
                "single_pair_bytes": {
                    "min": min(pair_bytes),
                    "p50": round(statistics.median(pair_bytes)),
                    "p95": round(_percentile([float(v) for v in pair_bytes], 0.95)),
                    "max": max(pair_bytes),
                },
                "single_pair_leaf_value_count": {
                    "min": min(pair_fields),
                    "p50": round(statistics.median(pair_fields)),
                    "p95": round(
                        _percentile([float(v) for v in pair_fields], 0.95)
                    ),
                    "max": max(pair_fields),
                },
            }
        runs.append(
            {
                "run_number": run_number,
                "run_kind": "cold" if run_number == 1 else "warm",
                "materialization_ms": materialization_ms,
                "serialization_ms": serialization_ms,
                "peak_memory_mib": peak / 1024 / 1024,
                "pair_count": pair_count,
                "relation_count": relation_count,
                "result_hash": _sha256(canonical),
            }
        )
        del canonical, draft_payload, materialized
        gc.collect()
    assert len({item["result_hash"] for item in runs}) == 1
    warm_runs = runs[1:]
    return {
        "repeats": repeats,
        "cold_run": {
            key: round(value, 3) if isinstance(value, float) else value
            for key, value in runs[0].items()
        },
        "warm_runs": {
            "materialization_ms": _series(
                [item["materialization_ms"] for item in warm_runs]
            ),
            "serialization_ms": _series(
                [item["serialization_ms"] for item in warm_runs]
            ),
            "peak_memory_mib": _series(
                [item["peak_memory_mib"] for item in warm_runs]
            ),
        },
        "all_runs": {
            "materialization_ms": _series(
                [item["materialization_ms"] for item in runs]
            ),
            "serialization_ms": _series(
                [item["serialization_ms"] for item in runs]
            ),
            "peak_memory_mib": _series(
                [item["peak_memory_mib"] for item in runs]
            ),
        },
        "deterministic_result_hash": runs[0]["result_hash"],
        "pair_count": runs[0]["pair_count"],
        "relation_count": runs[0]["relation_count"],
        "storage": storage,
    }


def _scale_case(
    category: str,
    candidate_count: int,
    *,
    repeats: int,
) -> dict[str, Any]:
    api_root = REPO_ROOT / "apps" / "api-server"
    sys.path.insert(0, str(api_root))
    from app.services.core3_real_data.analyst.competitor_profile_candidate_performance import (  # noqa: PLC0415
        CandidatePerformanceBenchmark,
    )
    from tests.core3_real_data.test_competitor_profile_candidate_performance import (  # noqa: PLC0415
        _large_bundle,
    )
    from tests.core3_real_data.test_competitor_profile_candidate_recall import (  # noqa: PLC0415
        _target_bundle,
    )
    from tests.core3_real_data.test_competitor_profile_materializer import (  # noqa: PLC0415
        _config,
    )

    provider_selects = _provider_select_baseline(category)
    bundle = _large_bundle(category, candidate_count)
    target = _target_bundle(bundle, f"{category}000001")
    candidate_runs: list[dict[str, Any]] = []
    for run_number in range(1, repeats + 1):
        run = CandidatePerformanceBenchmark().measure(
            bundle,
            target,
            case_code=(
                f"g28-{category.lower()}-{candidate_count}-scale-{run_number}"
            ),
            expected_candidate_count=candidate_count,
            source_page_size=64,
            provider_select_count=provider_selects["total_select_count"],
        )
        metrics = CandidatePerformanceBenchmark().enforce(run)
        candidate_runs.append(
            {
                "run_number": run_number,
                "run_kind": "cold" if run_number == 1 else "warm",
                "wall_time_ms": float(metrics.wall_time_ms),
                "peak_memory_mib": float(metrics.peak_memory_mib),
                "result_hash": metrics.determinism_result_hash,
                "candidate_count": metrics.recall_candidate_count,
            }
        )
        del run
        gc.collect()
    assert len({item["result_hash"] for item in candidate_runs}) == 1
    warm_candidate_runs = candidate_runs[1:]
    materializer = _materializer_scale_runs(
        bundle,
        target,
        _config(category),
        repeats=repeats,
    )
    return {
        "category_code": category,
        "benchmark_target_sku_code": f"{category}000001",
        "candidate_count": candidate_count,
        "provider_sql": provider_selects,
        "candidate_pipeline": {
            "repeats": repeats,
            "cold_run": candidate_runs[0],
            "warm_runs": {
                "wall_time_ms": _series(
                    [item["wall_time_ms"] for item in warm_candidate_runs]
                ),
                "peak_memory_mib": _series(
                    [item["peak_memory_mib"] for item in warm_candidate_runs]
                ),
            },
            "all_runs": {
                "wall_time_ms": _series(
                    [item["wall_time_ms"] for item in candidate_runs]
                ),
                "peak_memory_mib": _series(
                    [item["peak_memory_mib"] for item in candidate_runs]
                ),
            },
            "deterministic_result_hash": candidate_runs[0]["result_hash"],
        },
        "full_v1_materializer": materializer,
    }


def _budget_ceiling(value: float, *, step: int, multiplier: float = 1.25) -> int:
    return math.ceil(value * multiplier / step) * step


def _profile_scale_benchmark() -> dict[str, Any]:
    repeats = 3
    tv = _scale_case("TV", 377, repeats=repeats)
    ac = _scale_case("AC", 155, repeats=repeats)
    max_candidate_facts = {
        "TV": {
            "source_environment": "205-read-only",
            "version_id": "c45c0002-9b8a-4b0d-8b12-344dee020e15",
            "target_sku_code": "TV00025784",
            "display_name_cn": "红米 l75ma-ra",
            "candidate_count": 359,
            "tied_max_target_count": 151,
        },
        "AC": {
            "source_environment": "205-read-only",
            "version_id": "45725326-720c-45c8-9a3b-e86fb6cc1f0b",
            "target_sku_code": "AC00028642",
            "display_name_cn": "小米 kfr-35gw/n1a1",
            "candidate_count": 151,
            "tied_max_target_count": 49,
        },
    }
    cases = {"TV": tv, "AC": ac}
    budget_inputs: dict[str, Any] = {
        "derivation_rule": (
            "For G29 schema-budget inputs only: ceil(max(cold,p95) * 1.25) "
            "to 100ms for latency, ceil(max peak MiB * 1.25) to 16MiB, "
            "fixed provider SELECT count equals the measured count, and storage "
            "uses actual canonical JSON bytes without compression. G39/G41 set "
            "release gates after implementation and 205 readback."
        ),
        "categories": {},
    }
    for category, case in cases.items():
        candidate = case["candidate_pipeline"]
        materializer = case["full_v1_materializer"]
        budget_inputs["categories"][category] = {
            "candidate_pipeline_wall_time_ms": _budget_ceiling(
                max(
                    candidate["cold_run"]["wall_time_ms"],
                    candidate["all_runs"]["wall_time_ms"]["p95"],
                ),
                step=100,
            ),
            "materialization_wall_time_ms": _budget_ceiling(
                max(
                    materializer["cold_run"]["materialization_ms"],
                    materializer["all_runs"]["materialization_ms"]["p95"],
                ),
                step=100,
            ),
            "peak_memory_mib": _budget_ceiling(
                max(
                    candidate["all_runs"]["peak_memory_mib"]["max"],
                    materializer["all_runs"]["peak_memory_mib"]["max"],
                ),
                step=16,
            ),
            "provider_select_count": case["provider_sql"]["total_select_count"],
            "serialized_draft_bytes": materializer["storage"][
                "serialized_draft_bytes"
            ],
            "serialized_draft_leaf_value_count": materializer["storage"][
                "serialized_draft_leaf_value_count"
            ],
        }
    return {
        "benchmark_version": "competitor_profile_v1_1_g28_scale_benchmark_v2",
        "repeats": repeats,
        "real_205_max_candidate_skus": max_candidate_facts,
        "synthetic_upper_bound_cases": cases,
        "g29_budget_inputs": budget_inputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        action="append",
        help=(
            "Repeat to override the four default real compatibility fixtures. "
            "All four named fixtures remain required for full validation."
        ),
    )
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--leaf-inventory", type=Path, default=DEFAULT_LEAF_INVENTORY
    )
    parser.add_argument(
        "--full-universe", type=Path, default=DEFAULT_FULL_UNIVERSE
    )
    parser.add_argument("--write-derived-artifacts", action="store_true")
    parser.add_argument("--run-legacy-benchmark", action="store_true")
    parser.add_argument("--run-profile-scale-benchmark", action="store_true")
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args()

    fixture_paths = tuple(args.fixture or DEFAULT_FIXTURES)
    primary_path = next(
        path for path in fixture_paths if path.name == DEFAULT_FIXTURE.name
    )
    fixture_load = _timed(lambda: _load_fixture(primary_path), repeats=3)
    payload, raw = fixture_load.pop("result")
    fixture_suite = {primary_path.name: payload}
    fixture_receipts = [
        {
            "path": primary_path.name,
            "gzip_bytes": primary_path.stat().st_size,
            "canonical_json_bytes": len(raw),
            "canonical_json_sha256": _sha256(raw),
            "load_benchmark": fixture_load,
        }
    ]
    for path in fixture_paths:
        if path == primary_path:
            continue
        fixture_payload, fixture_raw = _load_fixture(path)
        fixture_suite[path.name] = fixture_payload
        fixture_receipts.append(
            {
                "path": path.name,
                "gzip_bytes": path.stat().st_size,
                "canonical_json_bytes": len(fixture_raw),
                "canonical_json_sha256": _sha256(fixture_raw),
            }
        )
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    generated_inventory = _build_leaf_mapping_inventory(fixture_suite, mapping)
    if args.write_derived_artifacts:
        _write_deterministic_gzip(args.leaf_inventory, generated_inventory)
    leaf_inventory = None
    if args.leaf_inventory.exists():
        with gzip.open(args.leaf_inventory, "rt", encoding="utf-8") as handle:
            leaf_inventory = json.load(handle)
    full_universe = None
    if args.full_universe.exists():
        with gzip.open(args.full_universe, "rt", encoding="utf-8") as handle:
            full_universe = json.load(handle)
    result = {
        "status": "passed",
        "fixtures": sorted(fixture_receipts, key=lambda item: item["path"]),
        "validation": _validate(
            fixture_suite,
            mapping,
            matrix,
            leaf_inventory,
            full_universe,
        ),
        "machine": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
            "physical_memory_bytes": _physical_memory_bytes(),
        },
    }
    if args.run_legacy_benchmark:
        result["legacy_runtime_benchmark"] = _legacy_benchmark(payload)
    if args.run_profile_scale_benchmark:
        result["profile_scale_benchmark"] = _profile_scale_benchmark()
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    if args.result_output is not None:
        args.result_output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
