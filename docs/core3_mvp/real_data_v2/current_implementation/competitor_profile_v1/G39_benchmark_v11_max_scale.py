#!/usr/bin/env python3
"""Run deterministic local-equivalent V1.1 maximum-candidate benchmarks."""

from __future__ import annotations

import gc
import json
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
API_ROOT = REPO_ROOT / "apps" / "api-server"
sys.path.insert(0, str(API_ROOT))

from app.services.core3_real_data.analyst.competitor_profile_v1_1_materializer import (  # noqa: E402
    CompetitorProfileV11Materializer,
)
from tests.core3_real_data.test_competitor_profile_v1_1_materializer_generation import (  # noqa: E402
    _max_candidate_work_item,
)


OUTPUT = HERE / "G39_v11_max_scale_benchmark.json"
REPEATS = 3
BUDGETS = {
    "TV": {
        "candidate_count": 377,
        "maximum_generation_p95_ms": 60_000,
        "maximum_peak_memory_mib": 1_200,
        "maximum_serialized_draft_bytes": 536_870_912,
    },
    "AC": {
        "candidate_count": 155,
        "maximum_generation_p95_ms": 30_000,
        "maximum_peak_memory_mib": 600,
        "maximum_serialized_draft_bytes": 268_435_456,
    },
}


def _percentile(values: list[float], percentile: int) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def _peak_rss_mib() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bytes_used = usage if sys.platform == "darwin" else usage * 1024
    return bytes_used / 1024 / 1024


def _current_rss_mib() -> float:
    return psutil.Process().memory_info().rss / 1024 / 1024


def _run_once(category: str, run_number: int) -> dict[str, Any]:
    budget = BUDGETS[category]
    gc.collect()
    input_started = time.perf_counter()
    item = _max_candidate_work_item(
        category,
        budget["candidate_count"],
        version_id=f"competitor-profile-v11-{category.lower()}-g39-max-scale",
    )
    input_preparation_ms = (time.perf_counter() - input_started) * 1000
    gc.collect()
    work_item_peak_memory_mib = _peak_rss_mib()
    work_item_baseline_memory_mib = _current_rss_mib()
    started = time.perf_counter()
    dto = (
        CompetitorProfileV11Materializer()
        .materialize(
            profile_version=item.profile_version,
            target_snapshot=item.target_snapshot,
            candidate_snapshots=item.candidate_snapshots,
            pair_assemblies=item.pair_assemblies,
            gate_evaluations=item.gate_evaluations,
            selection_result=item.selection_result,
            hard_excluded_inputs=item.hard_excluded_inputs,
        )
        .dto
    )
    materialized_peak_memory_mib = _peak_rss_mib()
    serialized = dto.model_dump_json()
    process_peak_memory_mib = _peak_rss_mib()
    run = {
        "run_number": run_number,
        "candidate_count": len(dto.pair_analyses),
        "candidate_snapshot_count": len(dto.candidate_snapshots),
        "priority_count": len(dto.priority_selections),
        "generation_and_serialization_ms": round(
            (time.perf_counter() - started) * 1000, 3
        ),
        "input_preparation_ms": round(input_preparation_ms, 3),
        "work_item_baseline_memory_mib": round(
            work_item_baseline_memory_mib,
            3,
        ),
        "work_item_peak_memory_mib": round(work_item_peak_memory_mib, 3),
        "materialized_peak_memory_mib": round(materialized_peak_memory_mib, 3),
        "process_peak_memory_mib": round(process_peak_memory_mib, 3),
        "peak_memory_mib": round(
            max(0.0, process_peak_memory_mib - work_item_baseline_memory_mib),
            3,
        ),
        "serialized_draft_bytes": len(serialized.encode("utf-8")),
        "profile_result_hash": dto.profile_result_hash,
    }
    if run["candidate_count"] != budget["candidate_count"]:
        raise RuntimeError(f"{category} maximum candidate case was truncated")
    return run


def _run_category(category: str) -> dict[str, Any]:
    budget = BUDGETS[category]
    runs = [
        json.loads(
            subprocess.check_output(
                [sys.executable, __file__, "--run-once", category, str(run_number)],
                text=True,
            )
        )
        for run_number in range(1, REPEATS + 1)
    ]

    hashes = {row["profile_result_hash"] for row in runs}
    generation_values = [row["generation_and_serialization_ms"] for row in runs]
    peak_memory = max(row["peak_memory_mib"] for row in runs)
    maximum_bytes = max(row["serialized_draft_bytes"] for row in runs)
    summary = {
        "candidate_count": budget["candidate_count"],
        "repeats": REPEATS,
        "generation_and_serialization_p95_ms": round(
            _percentile(generation_values, 95), 3
        ),
        "maximum_peak_memory_mib": peak_memory,
        "maximum_serialized_draft_bytes": maximum_bytes,
        "deterministic_profile_result_hash": next(iter(hashes)),
        "deterministic": len(hashes) == 1,
        "budget": budget,
        "runs": runs,
    }
    summary["passed"] = bool(
        summary["deterministic"]
        and summary["generation_and_serialization_p95_ms"]
        <= budget["maximum_generation_p95_ms"]
        and peak_memory <= budget["maximum_peak_memory_mib"]
        and maximum_bytes <= budget["maximum_serialized_draft_bytes"]
    )
    return summary


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--run-once":
        print(json.dumps(_run_once(sys.argv[2], int(sys.argv[3])), sort_keys=True))
        return 0
    result = {
        "benchmark_version": "competitor_profile_v1_1_g39_max_scale_v1",
        "measurement_contract": {
            "generation_timing_scope": (
                "materialize_frozen_g32_g35_outputs_and_serialize_draft"
            ),
            "input_preparation_reported_separately": True,
            "peak_memory_scope": (
                "incremental_process_rss_above_prepared_work_item_baseline"
            ),
            "candidate_truncation_allowed": False,
            "dimension_dropping_allowed": False,
        },
        "machine": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "categories": {
            category: _run_category(category) for category in ("TV", "AC")
        },
        "sql_contract": {
            "provider_select_count": 11,
            "target_incremental_provider_select_count": 0,
            "repository_full_compact_question_select_count": 7,
            "evidence_tests": [
                "test_provider_loads_complete_category_once_and_reuses_target_bundle",
                "test_full_compact_and_question_reads_are_deterministic_and_bounded",
            ],
            "candidate_loop_selects": 0,
        },
    }
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(row["passed"] for row in result["categories"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
