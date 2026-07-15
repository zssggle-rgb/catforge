from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


REAL_FIXTURE_NAMES = (
    "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz",
    "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz",
    "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz",
    "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz",
)


def _repo_root() -> Path:
    return next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "apps").is_dir() and (parent / "docs").is_dir()
    )


def _artifact_dir() -> Path:
    return (
        _repo_root()
        / "docs/core3_mvp/real_data_v2/current_implementation/competitor_profile_v1"
    )


def _load_verifier() -> ModuleType:
    script = _artifact_dir() / "G28_verify_legacy_baseline.py"
    spec = importlib.util.spec_from_file_location("g28_legacy_baseline", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _load_fixture_suite() -> dict[str, dict]:
    result = {}
    for name in REAL_FIXTURE_NAMES:
        with gzip.open(_artifact_dir() / name, "rt", encoding="utf-8") as handle:
            result[name] = json.load(handle)
    return result


def test_g28_frozen_fixture_mapping_and_gate_matrix_are_complete() -> None:
    artifact_dir = _artifact_dir()
    fixture_path = artifact_dir / REAL_FIXTURE_NAMES[0]
    with gzip.open(fixture_path, "rb") as handle:
        fixture_bytes = handle.read()
    fixture_suite = _load_fixture_suite()
    mapping = json.loads(
        (artifact_dir / "G28_legacy_to_v11_field_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    matrix = json.loads(
        (artifact_dir / "G28_gate_fixture_matrix.json").read_text(encoding="utf-8")
    )
    with gzip.open(
        artifact_dir / "G28_legacy_leaf_mapping_inventory.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        inventory = json.load(handle)
    with gzip.open(
        artifact_dir / "G28_65e7q_v1_full_universe_205_20260715.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        universe = json.load(handle)
    manifest = json.loads(
        (artifact_dir / "G28_legacy_baseline_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = json.loads(
        (artifact_dir / "G28_legacy_capture_receipts.json").read_text(
            encoding="utf-8"
        )
    )
    verifier = _load_verifier()

    result = verifier._validate(
        fixture_suite,
        mapping,
        matrix,
        inventory,
        universe,
    )

    records = {
        item["fixture"]: item for item in manifest["real_legacy_fixtures"]
    }
    receipt_records = {item["fixture"]: item for item in receipt["entries"]}
    receipt_without_hash = copy.deepcopy(receipt)
    receipt_hash = receipt_without_hash.pop("receipt_hash")
    assert hashlib.sha256(_canonical_bytes(receipt_without_hash)).hexdigest() == (
        receipt_hash
    )
    assert receipt["all_application_argv_omit_limit"]
    assert not receipt["database_write"]
    assert not receipt["remote_file_write"]
    assert not receipt["feishu_publish"]
    assert not receipt["profile_write_flag_present"]
    assert set(receipt_records) == set(records)
    assert verifier._sha256(fixture_bytes) == records[fixture_path.name][
        "canonical_json_sha256"
    ]
    assert result["mapping_coverage_pct"] == 100.0
    assert result["legacy_observed_path_count"] == manifest[
        "observed_field_coverage"
    ]["observed_path_count"]
    assert result["legacy_empty_container_path_count"] == manifest[
        "observed_field_coverage"
    ]["empty_container_path_count"]
    assert result["target_alias_group_count"] == manifest[
        "observed_field_coverage"
    ]["target_alias_group_count"]
    assert result["real_fixture_count"] == 4
    assert {
        item["m12d_consumption_state"] for item in result["real_fixtures"]
    } == {"published_ready", "published_degraded"}
    assert {item["category_code"] for item in result["real_fixtures"]} == {
        "TV",
        "AC",
    }
    assert [item["candidate_count"] for item in result["real_fixtures"]] == [
        20,
        16,
        20,
        13,
    ]
    for name, record in records.items():
        receipt_record = receipt_records[name]
        assert _sha256_file(artifact_dir / name) == record["gzip_sha256"]
        assert record["default_candidate_limit"] == 20
        assert record["invocation_omitted_limit_argument"]
        assert record["application_argv"] == receipt_record["application_argv"]
        assert record["source_stdout_sha256"] == receipt_record[
            "source_stdout_sha256"
        ]
        assert record["canonical_json_sha256"] == receipt_record[
            "canonical_json_sha256"
        ]
        assert record["gzip_sha256"] == receipt_record["gzip_sha256"]
        assert record["candidate_count"] == receipt_record[
            "actual_candidate_count"
        ]
        application_argv = receipt_record["application_argv"]
        assert "--limit" not in application_argv
        assert not any(token.startswith("--limit=") for token in application_argv)
        assert "profile-write" not in application_argv
    assert manifest["capture_contract"]["cli_default_candidate_limit"] == 20
    assert manifest["capture_contract"]["limit_argument_was_omitted"]
    assert manifest["capture_contract"]["execution_receipt_hash"] == receipt_hash
    receipt_artifact = manifest["capture_contract"]["execution_receipt"]
    assert _sha256_file(artifact_dir / receipt_artifact["file"]) == (
        receipt_artifact["sha256"]
    )
    assert manifest["observed_field_coverage"]["typed_schema_complete"] is False
    assert manifest["observed_field_coverage"]["typed_schema_completion_goal"] == (
        "G29"
    )
    assert result["gate_fixture_case_count"] == 8
    assert result["gate_matrix_result_hash"] == manifest["gate_contract"][
        "matrix_result_hash"
    ]
    assert result["top3_sku_codes"] == [
        item["sku_code"] for item in manifest["primary_65e7q"]["top3"]
    ]
    assert result["candidate_count"] == len(
        manifest["primary_65e7q"]["candidates_in_recall_order"]
    ) == 20
    capture_execution = manifest["primary_65e7q"]["capture_execution"]
    primary_receipt = receipt_records[fixture_path.name]
    assert capture_execution["application_argv"] == primary_receipt[
        "application_argv"
    ]
    assert capture_execution["canonical_json_sha256"] == primary_receipt[
        "canonical_json_sha256"
    ]
    assert capture_execution["gzip_sha256"] == _sha256_file(fixture_path)
    assert capture_execution["top3_sku_codes"] == result["top3_sku_codes"]
    assert capture_execution["matches_frozen_fixture"]
    assert result["leaf_inventory_hash"] == inventory["inventory_hash"]
    assert result["full_v1_universe"]["candidate_count"] == 352
    assert result["full_v1_universe"]["legacy_default20_subset_complete"]
    assert result["full_v1_universe"]["legacy_top3_full_count"] == 3
    assert result["full_v1_universe"]["legacy_top3_relation_count"] == 21
    assert _sha256_file(
        artifact_dir / manifest["full_v1_universe"]["file"]["file"]
    ) == manifest["full_v1_universe"]["file"]["sha256"]
    assert _sha256_file(
        artifact_dir
        / manifest["observed_field_coverage"]["inventory_file"]["file"]
    ) == manifest["observed_field_coverage"]["inventory_file"]["sha256"]
    assert _sha256_file(
        artifact_dir / manifest["observed_field_coverage"]["mapping_file"]["file"]
    ) == manifest["observed_field_coverage"]["mapping_file"]["sha256"]
    assert _sha256_file(
        artifact_dir / manifest["gate_contract"]["fixture_file"]["file"]
    ) == manifest["gate_contract"]["fixture_file"]["sha256"]
    for artifact in manifest["reproduction_scripts"].values():
        assert _sha256_file(artifact_dir / artifact["file"]) == artifact["sha256"]
    for artifact_key in (
        "legacy_artifact",
        "scale_artifact",
        "real_max_scale_artifact",
    ):
        artifact = manifest["local_performance_baseline"][artifact_key]
        assert _sha256_file(artifact_dir / artifact["file"]) == artifact["sha256"]


def test_g28_gate_matrix_is_future_contract_golden_with_sensitivity() -> None:
    matrix = json.loads(
        (_artifact_dir() / "G28_gate_fixture_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    verifier = _load_verifier()

    first = verifier._execute_gate_matrix(matrix)
    second = verifier._execute_gate_matrix(matrix)

    assert first == second
    assert first["case_count"] == 8
    assert first["runtime_behavior_proven"] is False
    assert first["hard_exclusion_properties"]["case_count"] == 5
    assert {
        item["reason_code"]
        for item in first["hard_exclusion_properties"]["cases"]
    } == verifier.EXPECTED_HARD_EXCLUSIONS
    sensitivity = first["semantic_content_sensitivity"]
    assert sensitivity["direct_choice_before"] == "supported"
    assert sensitivity["direct_choice_after"] == "directional"
    assert sensitivity["aligned_result_hash"] != sensitivity[
        "divergent_result_hash"
    ]
    assert len({item["result_hash"] for item in first["cases"]}) == 8
    by_code = {item["case_code"]: item["actual"] for item in first["cases"]}
    assert by_code["tv_m12d_missing"]["question_strength"]["direct_choice"] == (
        "directional"
    )
    assert by_code["tv_m05c_review"]["review_required"]
    assert by_code["tv_battlefield_conflict"]["conflict_dimensions"] == [
        "battlefield"
    ]
    hdmi = by_code["tv_configuration_only"]["feature_assessments"]["hdmi_2_1"]
    assert hdmi["raw_difference_preserved"]
    assert hdmi["feature_market_status"] == "foundational"
    assert hdmi["differentiation_score_contribution"] == 0
    assert not hdmi["ranking_reason_eligible"]
    assert "externally supplied" in first["foundational_feature_scope"]
    assert by_code["ac_partial"]["scope_status"] == "analyzable"
    assert by_code["ac_partial"]["must_continue"]
    assert by_code["ac_complete"]["purchase_pool"] == {
        "category_code": "AC",
        "method": "ac_product_form_and_capacity_segment",
        "level": "P0",
        "product_form_match": True,
        "capacity_segment_match": True,
    }

    complete_case = next(
        item for item in matrix["cases"] if item["case_code"] == "tv_complete"
    )
    sensitivity_input = verifier._materialize_gate_case(matrix, complete_case)
    verifier._apply_gate_mutation(
        sensitivity_input,
        {
            "operation": "remove_module_records",
            "module_code": "M07",
            "subjects": ["target", "candidate"],
        },
    )
    sensitivity_result = verifier._gate_contract_oracle(sensitivity_input)
    assert sensitivity_result["dimension_availability"]["market"] == "unknown"
    assert sensitivity_result["question_strength"]["price_volume_pressure"] == (
        "unknown"
    )


def test_g28_observed_mapping_inventory_is_explicit_and_lossless() -> None:
    with gzip.open(
        _artifact_dir() / "G28_legacy_leaf_mapping_inventory.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        inventory = json.load(handle)

    paths = inventory["observed_paths"]
    assert inventory["source_fixture_count"] == 4
    assert inventory["source_observed_path_count"] == len(paths) == 13_756
    assert inventory["source_value_leaf_path_count"] == 12_841
    assert inventory["source_empty_container_path_count"] == 915
    assert inventory["unmapped_path_count"] == 0
    assert not inventory["known_to_unknown_allowed"]
    assert inventory["typed_schema_complete"] is False
    assert inventory["typed_schema_completion_goal"] == "G29"
    assert len({item["source_path"] for item in paths}) == len(paths)
    assert all(item["target_leaf_path"] for item in paths)
    assert all(item["source_atom"] for item in paths)
    assert all(item["observed_source_types"] for item in paths)
    assert all(
        item["expected_target_types"] == item["observed_source_types"]
        for item in paths
    )
    assert all(item["occurrence_count"] > 0 for item in paths)
    assert all(item["target_requirement"] == "conditional_required" for item in paths)
    assert all(item["required_when"] == "legacy_source_path_present" for item in paths)
    assert all(item["missing_branch_policy"] for item in paths)
    assert sum(item["empty_container_observed"] for item in paths) == 915
    alias_groups = inventory["target_alias_groups"]
    assert inventory["target_alias_group_count"] == len(alias_groups) == 3_624
    assert all(item["value_equality_required"] for item in alias_groups)
    assert all(
        all(item["value_equality_by_fixture"].values()) for item in alias_groups
    )
    assert all(item["canonical_source_path"] for item in alias_groups)
    assert not any(
        fragment in item["target_leaf_path"]
        for item in paths
        for fragment in (
            "candidate_snapshot_ref.",
            "target_snapshot_ref.",
            "candidate_ref.",
        )
    )


def test_g28_observed_mapping_rejects_alias_value_conflicts() -> None:
    fixture_suite = _load_fixture_suite()
    primary = fixture_suite[REAL_FIXTURE_NAMES[0]]
    primary["legacy_analysis"]["all_candidates"][0]["param_claim_overlap"][
        "claim_overlap"
    ]["candidate_count"] = -1
    mapping = json.loads(
        (_artifact_dir() / "G28_legacy_to_v11_field_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    verifier = _load_verifier()

    with pytest.raises(
        AssertionError,
        match="legacy aliases map inconsistent values",
    ):
        verifier._build_leaf_mapping_inventory(fixture_suite, mapping)


def test_g28_full_v1_universe_has_all_relations_and_legacy_top3_payloads() -> None:
    artifact_dir = _artifact_dir()
    with gzip.open(
        artifact_dir / "G28_65e7q_v1_full_universe_205_20260715.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        universe = json.load(handle)
    with gzip.open(
        artifact_dir / REAL_FIXTURE_NAMES[0],
        "rt",
        encoding="utf-8",
    ) as handle:
        legacy = json.load(handle)
    verifier = _load_verifier()
    legacy_codes = [
        item["candidate"]["sku_code"]
        for item in legacy["legacy_input"]["candidates"]
    ]

    result = verifier._validate_full_universe(universe, legacy_codes)

    assert result["candidate_count"] == 352
    assert result["legacy_candidate_subset_count"] == 20
    assert result["target_relation_count"] == 2_464
    assert result["legacy_top3_relation_count"] == 21
    assert result["relation_index_hash"] == universe["relation_index_hash"]
    assert result["selection_count"] == 1
    assert result["legacy_default20_subset_complete"]


def test_g28_performance_baseline_has_tv_ac_sql_storage_and_budget_inputs() -> None:
    benchmark = json.loads(
        (_artifact_dir() / "G28_profile_scale_benchmark.json").read_text(
            encoding="utf-8"
        )
    )
    profile_scale = benchmark["profile_scale_benchmark"]
    real_scale = json.loads(
        (_artifact_dir() / "G28_max_candidate_scale_205_20260715.json").read_text(
            encoding="utf-8"
        )
    )
    legacy = json.loads(
        (_artifact_dir() / "G28_legacy_runtime_benchmark.json").read_text(
            encoding="utf-8"
        )
    )["legacy_runtime_benchmark"]

    assert legacy["default_candidate_limit"] == 20
    assert legacy["actual_candidate_count"] == 20
    assert legacy["single_pair"]["result"]["candidate_count"] == 1
    assert legacy["single_sku_default20_candidates"]["result"][
        "candidate_count"
    ] == 20
    assert benchmark["status"] == "passed"
    assert benchmark["machine"]["logical_cpu_count"] > 0
    assert benchmark["machine"]["physical_memory_bytes"] > 0
    assert profile_scale["repeats"] == 3
    assert profile_scale["real_205_max_candidate_skus"]["TV"][
        "candidate_count"
    ] == 359
    assert profile_scale["real_205_max_candidate_skus"]["AC"][
        "candidate_count"
    ] == 151
    for category, expected_count in (("TV", 377), ("AC", 155)):
        real_max = profile_scale["real_205_max_candidate_skus"][category]
        frozen_real_max = real_scale["categories"][category]
        assert real_max["candidate_count"] == frozen_real_max["max_candidate_count"]
        assert real_max["target_sku_code"] == frozen_real_max[
            "canonical_target_sku_code"
        ]
        case = profile_scale["synthetic_upper_bound_cases"][category]
        assert case["candidate_count"] == expected_count
        assert case["provider_sql"]["total_select_count"] == 11
        assert case["provider_sql"]["target_incremental_select_count"] == 0
        materializer = case["full_v1_materializer"]
        assert materializer["repeats"] == 3
        assert materializer["pair_count"] == expected_count
        assert materializer["relation_count"] == expected_count * 7
        assert materializer["all_runs"]["materialization_ms"]["p95"] > 0
        assert materializer["all_runs"]["peak_memory_mib"]["p50"] > 0
        assert materializer["storage"]["serialized_draft_bytes"] > 0
        assert materializer["storage"]["serialized_draft_leaf_value_count"] > 0
        budget = profile_scale["g29_budget_inputs"]["categories"][category]
        assert budget["provider_select_count"] == 11
        assert budget["serialized_draft_bytes"] == materializer["storage"][
            "serialized_draft_bytes"
        ]


def test_g28_all_real_fixtures_exclude_presentation_payloads() -> None:
    verifier = _load_verifier()
    for payload in _load_fixture_suite().values():
        assert set(payload) == {"snapshot", "legacy_input", "legacy_analysis"}
        assert set(payload["legacy_analysis"]) == {
            "all_candidates",
            "top_competitors",
            "candidate_buckets",
            "selection_policy_cn",
        }
        assert not {
            "short_answer",
            "report_payload",
            "pm_comparison_report_payload",
            "dashboard_payload",
            "feishu_card_payload",
            "display_policy",
        }.intersection(verifier._recursive_keys(payload))
