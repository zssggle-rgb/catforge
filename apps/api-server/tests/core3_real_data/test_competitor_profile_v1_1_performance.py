import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BENCHMARK_PATH = (
    REPO_ROOT
    / "docs/core3_mvp/real_data_v2/current_implementation/competitor_profile_v1"
    / "G39_v11_max_scale_benchmark.json"
)


def test_g39_maximum_candidate_benchmark_passes_frozen_budget():
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    assert benchmark["benchmark_version"] == (
        "competitor_profile_v1_1_g39_max_scale_v1"
    )
    assert benchmark["measurement_contract"] == {
        "candidate_truncation_allowed": False,
        "dimension_dropping_allowed": False,
        "generation_timing_scope": (
            "materialize_frozen_g32_g35_outputs_and_serialize_draft"
        ),
        "input_preparation_reported_separately": True,
        "peak_memory_scope": (
            "incremental_process_rss_above_prepared_work_item_baseline"
        ),
    }
    assert set(benchmark["categories"]) == {"TV", "AC"}
    for category, expected_count in {"TV": 377, "AC": 155}.items():
        result = benchmark["categories"][category]
        budget = result["budget"]
        assert result["passed"] is True
        assert result["deterministic"] is True
        assert result["repeats"] == 3
        assert result["candidate_count"] == expected_count
        assert all(
            row["candidate_count"] == expected_count for row in result["runs"]
        )
        assert (
            result["generation_and_serialization_p95_ms"]
            <= budget["maximum_generation_p95_ms"]
        )
        assert (
            result["maximum_peak_memory_mib"]
            <= budget["maximum_peak_memory_mib"]
        )
        assert (
            result["maximum_serialized_draft_bytes"]
            <= budget["maximum_serialized_draft_bytes"]
        )
        assert len(
            {row["profile_result_hash"] for row in result["runs"]}
        ) == 1


def test_g39_sql_contract_is_fixed_and_has_no_candidate_loop_selects():
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    assert benchmark["sql_contract"] == {
        "candidate_loop_selects": 0,
        "evidence_tests": [
            "test_provider_loads_complete_category_once_and_reuses_target_bundle",
            "test_full_compact_and_question_reads_are_deterministic_and_bounded",
        ],
        "provider_select_count": 11,
        "repository_full_compact_question_select_count": 7,
        "target_incremental_provider_select_count": 0,
    }
