#!/usr/bin/env python3
"""Build the deterministic G28 manifest from the frozen artifacts."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import G28_verify_legacy_baseline as verifier


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
OUTPUT = HERE / "G28_legacy_baseline_manifest.json"
CAPTURE_RECEIPT = HERE / "G28_legacy_capture_receipts.json"

FIXTURE_ROLES = {
    "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz": (
        "TV complete/default-limit golden"
    ),
    "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz": (
        "TV published-degraded real compatibility"
    ),
    "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz": (
        "AC published-ready real compatibility"
    ),
    "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz": (
        "AC published-degraded real compatibility"
    ),
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_gzip_json(path: Path) -> tuple[dict[str, Any], bytes]:
    with gzip.open(path, "rb") as handle:
        raw = handle.read()
    return json.loads(raw), raw


def _candidate_summary(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item["candidate"]
    value_anchor = item.get("value_anchor") or {}
    replacement = item.get("replacement_pressure") or {}
    return {
        "recall_rank": item["rank"],
        "sku_code": candidate["sku_code"],
        "name": " ".join(
            value
            for value in (
                candidate.get("brand_name"),
                candidate.get("model_name"),
            )
            if value
        ),
        "competitor_score": item.get("competitor_score"),
        "business_score": item.get("business_score"),
        "role": item.get("role"),
        "anchor_score": value_anchor.get("anchor_substitutability_score"),
        "replacement_score": replacement.get("replacement_pressure_score"),
    }


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "file": path.name,
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _load_validated_capture_receipt() -> dict[str, Any]:
    receipt = _load_json(CAPTURE_RECEIPT)
    receipt_hash = receipt["receipt_hash"]
    unhashed = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    assert _sha256_bytes(verifier._canonical_bytes(unhashed)) == receipt_hash
    assert receipt["source_environment"] == "205-read-only"
    assert receipt["all_application_argv_omit_limit"]
    assert not receipt["database_write"]
    assert not receipt["remote_file_write"]
    assert not receipt["feishu_publish"]
    assert not receipt["profile_write_flag_present"]
    return receipt


def main() -> int:
    capture_receipt = _load_validated_capture_receipt()
    capture_by_fixture = {
        item["fixture"]: item for item in capture_receipt["entries"]
    }
    assert set(capture_by_fixture) == set(FIXTURE_ROLES)
    fixture_suite: dict[str, dict[str, Any]] = {}
    fixture_records: list[dict[str, Any]] = []
    for path in verifier.DEFAULT_FIXTURES:
        payload, raw = _load_gzip_json(path)
        fixture_suite[path.name] = payload
        validated = verifier._validate_real_fixture(path.name, payload)
        capture_entry = capture_by_fixture[path.name]
        assert capture_entry["target_sku_code"] == validated["target_sku_code"]
        assert capture_entry["category_code"] == validated["category_code"]
        assert capture_entry["actual_candidate_count"] == validated["candidate_count"]
        assert capture_entry["canonical_json_sha256"] == _sha256_bytes(raw)
        assert capture_entry["canonical_json_bytes"] == len(raw)
        assert capture_entry["gzip_sha256"] == _sha256_file(path)
        assert capture_entry["gzip_bytes"] == path.stat().st_size
        fixture_records.append(
            {
                **validated,
                "role": FIXTURE_ROLES[path.name],
                "default_candidate_limit": capture_entry[
                    "default_candidate_limit"
                ],
                "invocation_omitted_limit_argument": not capture_entry[
                    "limit_argument_present"
                ],
                "application_argv": capture_entry["application_argv"],
                "source_stdout_sha256": capture_entry[
                    "source_stdout_sha256"
                ],
                "gzip_sha256": _sha256_file(path),
                "gzip_bytes": path.stat().st_size,
                "canonical_json_sha256": _sha256_bytes(raw),
                "canonical_json_bytes": len(raw),
                "contains_display_payload": False,
                "source_batch_id": payload["snapshot"]["batch_id"],
            }
        )

    mapping = _load_json(verifier.DEFAULT_MAPPING)
    matrix = _load_json(verifier.DEFAULT_MATRIX)
    with gzip.open(verifier.DEFAULT_LEAF_INVENTORY, "rt", encoding="utf-8") as handle:
        inventory = json.load(handle)
    universe, universe_raw = _load_gzip_json(verifier.DEFAULT_FULL_UNIVERSE)
    validation = verifier._validate(
        fixture_suite,
        mapping,
        matrix,
        inventory,
        universe,
    )
    gate_execution = verifier._execute_gate_matrix(matrix)
    primary = fixture_suite[verifier.DEFAULT_FIXTURE.name]
    analyzed = primary["legacy_analysis"]["all_candidates"]
    top3 = primary["legacy_analysis"]["top_competitors"]
    legacy_benchmark_path = HERE / "G28_legacy_runtime_benchmark.json"
    scale_benchmark_path = HERE / "G28_profile_scale_benchmark.json"
    max_scale_path = HERE / "G28_max_candidate_scale_205_20260715.json"
    legacy_benchmark = _load_json(legacy_benchmark_path)
    scale_benchmark = _load_json(scale_benchmark_path)
    scale = scale_benchmark["profile_scale_benchmark"]

    code_files = {
        "catforge_analyst.py": (
            REPO_ROOT / "apps/api-server/app/cli/catforge_analyst.py"
        ),
        "competitor_answer.py": (
            REPO_ROOT
            / "apps/api-server/app/services/core3_real_data/analyst/competitor_answer.py"
        ),
        "sop_orchestrators.py": (
            REPO_ROOT
            / "apps/api-server/app/services/core3_real_data/analyst/sop_orchestrators.py"
        ),
        "anchor_substitutability.py": (
            REPO_ROOT
            / "apps/api-server/app/services/core3_real_data/analyst/anchor_substitutability.py"
        ),
        "replacement_pressure.py": (
            REPO_ROOT
            / "apps/api-server/app/services/core3_real_data/analyst/replacement_pressure.py"
        ),
        "purchase_pressure_comparison.py": (
            REPO_ROOT
            / "apps/api-server/app/services/core3_real_data/analyst/purchase_pressure_comparison.py"
        ),
    }
    manifest = {
        "manifest_version": "competitor_profile_v1_1_g28_legacy_baseline_manifest_v4",
        "capture_date": "2026-07-15",
        "scope": {
            "objective": (
                "Freeze the current competitor-analysis machine contract before "
                "V1.1 schema or algorithm changes."
            ),
            "source_environment": "205-read-only",
            "database_write": False,
            "remote_file_write": False,
            "feishu_publish": False,
            "algorithm_change": False,
            "schema_change": False,
        },
        "capture_contract": {
            "command": "competitor-set",
            "answer_style": "xiaoao",
            "with_report": "none",
            "top_n": 3,
            "cli_default_candidate_limit": 20,
            "limit_argument_was_omitted": capture_receipt[
                "all_application_argv_omit_limit"
            ],
            "execution_receipt": _artifact(CAPTURE_RECEIPT),
            "execution_receipt_hash": capture_receipt["receipt_hash"],
            "presentation_fields_removed_after_capture": True,
            "default_limit_code_evidence": [
                "apps/api-server/app/cli/catforge_analyst.py:96",
                "apps/api-server/app/services/core3_real_data/analyst/sop_orchestrators.py:665",
            ],
        },
        "provenance": {
            "remote_commit": capture_receipt["remote_commit"],
            "remote_api_image": capture_receipt["remote_api_image"],
            "code_hashes": {
                name: _sha256_file(path) for name, path in code_files.items()
            },
        },
        "real_legacy_fixtures": sorted(
            fixture_records, key=lambda item: item["fixture"]
        ),
        "primary_65e7q": {
            "candidate_count": 20,
            "candidates_in_recall_order": [
                _candidate_summary(item)
                for item in sorted(analyzed, key=lambda value: value["rank"])
            ],
            "top3": [
                {
                    "selection_rank": rank,
                    **_candidate_summary(item),
                }
                for rank, item in enumerate(top3, start=1)
            ],
            "analysis_hash": legacy_benchmark["legacy_runtime_benchmark"][
                "deterministic_rerun_hash"
            ],
            "local_analysis_rerun_hash_equal": True,
            "capture_execution": {
                "application_argv": capture_by_fixture[
                    verifier.DEFAULT_FIXTURE.name
                ]["application_argv"],
                "source_stdout_sha256": capture_by_fixture[
                    verifier.DEFAULT_FIXTURE.name
                ]["source_stdout_sha256"],
                "canonical_json_sha256": capture_by_fixture[
                    verifier.DEFAULT_FIXTURE.name
                ]["canonical_json_sha256"],
                "gzip_sha256": capture_by_fixture[verifier.DEFAULT_FIXTURE.name][
                    "gzip_sha256"
                ],
                "actual_candidate_count": capture_by_fixture[
                    verifier.DEFAULT_FIXTURE.name
                ]["actual_candidate_count"],
                "top3_sku_codes": capture_by_fixture[
                    verifier.DEFAULT_FIXTURE.name
                ]["top3_sku_codes"],
                "matches_frozen_fixture": True,
            },
        },
        "observed_field_coverage": {
            "mapping_file": _artifact(verifier.DEFAULT_MAPPING),
            "inventory_file": _artifact(verifier.DEFAULT_LEAF_INVENTORY),
            "inventory_hash": inventory["inventory_hash"],
            "source_fixture_count": inventory["source_fixture_count"],
            "mapping_rule_count": inventory["mapping_rule_count"],
            "observed_path_count": inventory["source_observed_path_count"],
            "value_leaf_path_count": inventory["source_value_leaf_path_count"],
            "empty_container_path_count": inventory[
                "source_empty_container_path_count"
            ],
            "target_alias_group_count": inventory["target_alias_group_count"],
            "alias_value_conflict_count": 0,
            "coverage_pct_of_observed_paths": 100.0,
            "known_to_unknown_allowed": False,
            "typed_schema_complete": False,
            "typed_schema_completion_goal": "G29",
        },
        "gate_contract": {
            "fixture_file": _artifact(verifier.DEFAULT_MATRIX),
            "case_count": gate_execution["case_count"],
            "oracle_version": gate_execution["oracle_version"],
            "matrix_result_hash": gate_execution["matrix_result_hash"],
            "hard_exclusion_property_count": gate_execution[
                "hard_exclusion_properties"
            ]["case_count"],
            "semantic_content_sensitivity": gate_execution[
                "semantic_content_sensitivity"
            ],
            "foundational_feature_scope": gate_execution[
                "foundational_feature_scope"
            ],
            "runtime_behavior_proven": False,
            "implementation_goal": "G34",
        },
        "full_v1_universe": {
            "file": {
                **_artifact(verifier.DEFAULT_FULL_UNIVERSE),
                "canonical_json_sha256": _sha256_bytes(universe_raw),
                "canonical_json_bytes": len(universe_raw),
            },
            **validation["full_v1_universe"],
            "transaction_mode": universe["transaction_mode"],
            "remote_file_write": False,
        },
        "local_performance_baseline": {
            "workstation_note": (
                "Observed G28 baseline and G29 budget input, not a release gate."
            ),
            "machine": legacy_benchmark["machine"],
            "legacy_artifact": _artifact(legacy_benchmark_path),
            "scale_artifact": _artifact(scale_benchmark_path),
            "real_max_scale_artifact": _artifact(max_scale_path),
            "legacy_single_pair": legacy_benchmark["legacy_runtime_benchmark"][
                "single_pair"
            ],
            "legacy_single_sku_default20": legacy_benchmark[
                "legacy_runtime_benchmark"
            ]["single_sku_default20_candidates"],
            "real_205_max_candidate_skus": scale[
                "real_205_max_candidate_skus"
            ],
            "synthetic_upper_bound_cases": scale[
                "synthetic_upper_bound_cases"
            ],
            "g29_budget_inputs": scale["g29_budget_inputs"],
        },
        "storage_baseline": {
            **validation["storage"],
            "v1_tv_377_serialized_draft_bytes": scale[
                "synthetic_upper_bound_cases"
            ]["TV"]["full_v1_materializer"]["storage"][
                "serialized_draft_bytes"
            ],
            "v1_ac_155_serialized_draft_bytes": scale[
                "synthetic_upper_bound_cases"
            ]["AC"]["full_v1_materializer"]["storage"][
                "serialized_draft_bytes"
            ],
            "design_consequence": (
                "V1.1 must share SKU snapshots and persist compact pair "
                "calculations instead of duplicating legacy fact trees per pair."
            ),
        },
        "reproduction_scripts": {
            name: _artifact(HERE / name)
            for name in (
                "G28_capture_legacy_fixture.py",
                "G28_capture_legacy_suite.py",
                "G28_export_v1_universe_readonly.py",
                "G28_store_deterministic_gzip.py",
                "G28_verify_legacy_baseline.py",
                "G28_build_manifest.py",
            )
        },
    }
    OUTPUT.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "built",
                "output": OUTPUT.name,
                "sha256": _sha256_file(OUTPUT),
                "bytes": OUTPUT.stat().st_size,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
