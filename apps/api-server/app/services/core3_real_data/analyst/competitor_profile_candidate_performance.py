"""Local performance gates for the deterministic competitor candidate pipeline."""

from __future__ import annotations

import tracemalloc
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter_ns
from typing import Sequence

from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
    CandidatePipelineRun,
    SourcePages,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_performance_schemas import (
    CandidatePerformanceConfig,
    CandidatePerformanceMetrics,
    CandidatePerformanceSuiteReport,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.hash_utils import stable_hash


_MIB = Decimal(1024 * 1024)
_NANOSECONDS_PER_MILLISECOND = Decimal(1_000_000)


class CandidatePerformanceError(RuntimeError):
    """Base class for invalid or failed candidate performance cases."""


class CandidatePerformanceLimitError(CandidatePerformanceError):
    def __init__(self, metrics: CandidatePerformanceMetrics) -> None:
        self.metrics = metrics
        super().__init__(
            "candidate performance limits failed: "
            + ", ".join(metrics.failure_reason_codes)
        )


@dataclass(frozen=True)
class CandidatePerformanceRun:
    pipeline: CandidatePipelineRun
    metrics: CandidatePerformanceMetrics


class CandidatePerformanceBenchmark:
    """Measure the full two-pass pipeline without changing its candidate set."""

    def measure(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        *,
        case_code: str,
        expected_candidate_count: int,
        config: CandidatePerformanceConfig | None = None,
        source_page_size: int | None = None,
        provider_select_count: int | None = None,
    ) -> CandidatePerformanceRun:
        performance_config = config or CandidatePerformanceConfig()
        if expected_candidate_count < 0:
            raise CandidatePerformanceError(
                "expected candidate count must be non-negative"
            )
        if expected_candidate_count > len(category_bundle.authoritative_sku_codes) - 1:
            raise CandidatePerformanceError(
                "expected candidate count exceeds the authoritative SKU universe"
            )
        if provider_select_count is not None and provider_select_count < 0:
            raise CandidatePerformanceError(
                "provider select count must be non-negative"
            )
        if source_page_size is not None and source_page_size <= 0:
            raise CandidatePerformanceError("source page size must be positive")

        source_pages = (
            _source_pages(category_bundle, source_page_size)
            if source_page_size is not None
            else None
        )
        source_page_count = sum(len(pages) for pages in (source_pages or {}).values())
        tracing_already_active = tracemalloc.is_tracing()
        if not tracing_already_active:
            tracemalloc.start()
        tracemalloc.reset_peak()
        started_ns = perf_counter_ns()
        try:
            pipeline = CandidatePipelineDeterminismGuard().run(
                category_bundle,
                target_bundle,
                source_pages=source_pages,
            )
        finally:
            elapsed_ns = perf_counter_ns() - started_ns
            _, peak_bytes = tracemalloc.get_traced_memory()
            if not tracing_already_active:
                tracemalloc.stop()

        wall_time_ms = (Decimal(elapsed_ns) / _NANOSECONDS_PER_MILLISECOND).quantize(
            Decimal("0.001")
        )
        peak_memory_mib = (Decimal(peak_bytes) / _MIB).quantize(Decimal("0.001"))
        receipt = pipeline.receipt
        failures = sorted(
            {
                *(
                    ["recall_candidate_count_mismatch"]
                    if receipt.candidate_count != expected_candidate_count
                    else []
                ),
                *(
                    ["eligibility_candidate_count_mismatch"]
                    if pipeline.eligibility_manifest.candidate_count
                    != expected_candidate_count
                    else []
                ),
                *(
                    ["provider_select_count_exceeded"]
                    if provider_select_count is not None
                    and provider_select_count
                    > performance_config.max_provider_select_count
                    else []
                ),
                *(
                    ["source_page_size_outside_frozen_suite"]
                    if source_page_size is not None
                    and source_page_size not in performance_config.page_sizes
                    else []
                ),
                *(
                    ["wall_time_limit_exceeded"]
                    if wall_time_ms > performance_config.max_wall_time_ms
                    else []
                ),
                *(
                    ["peak_memory_limit_exceeded"]
                    if peak_memory_mib > performance_config.max_peak_memory_mib
                    else []
                ),
            }
        )
        source_record_count = sum(
            row.category_unique_record_count for row in receipt.canonicalization_stats
        )
        input_payload = {
            "case_code": case_code,
            "project_id": category_bundle.serving_scope.project_id,
            "category_code": category_bundle.serving_scope.category_code,
            "target_sku_code": target_bundle.target_sku_code,
            "config": performance_config.model_dump(mode="python"),
            "expected_candidate_count": expected_candidate_count,
            "source_page_size": source_page_size,
            "source_page_count": source_page_count,
            "provider_select_count": provider_select_count,
            "determinism_result_hash": receipt.result_hash,
        }
        input_fingerprint = stable_hash(
            input_payload,
            version="competitor_profile_candidate_performance_input_v1",
        )
        result_payload = {
            **input_payload,
            "input_fingerprint": input_fingerprint,
            "wall_time_ms": wall_time_ms,
            "peak_memory_mib": peak_memory_mib,
            "failure_reason_codes": failures,
        }
        metrics = CandidatePerformanceMetrics(
            case_code=case_code,
            project_id=category_bundle.serving_scope.project_id,
            category_code=category_bundle.serving_scope.category_code,
            product_category=category_bundle.serving_scope.product_category,
            target_sku_code=target_bundle.target_sku_code,
            config_version=performance_config.config_version,
            authoritative_sku_count=len(category_bundle.authoritative_sku_codes),
            expected_candidate_count=expected_candidate_count,
            recall_candidate_count=receipt.candidate_count,
            eligibility_candidate_count=pipeline.eligibility_manifest.candidate_count,
            source_record_count=source_record_count,
            recall_fact_count=receipt.recall_fact_count,
            question_assessment_count=receipt.question_assessment_count,
            unique_evidence_ref_count=receipt.unique_evidence_ref_count,
            source_page_size=source_page_size,
            source_page_count=source_page_count,
            provider_select_count=provider_select_count,
            wall_time_ms=wall_time_ms,
            peak_memory_mib=peak_memory_mib,
            status="failed" if failures else "passed",
            failure_reason_codes=failures,
            recall_result_hash=receipt.recall_result_hash,
            eligibility_result_hash=receipt.eligibility_result_hash,
            determinism_result_hash=receipt.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_candidate_performance_result_v1",
            ),
        )
        return CandidatePerformanceRun(pipeline=pipeline, metrics=metrics)

    def enforce(self, run: CandidatePerformanceRun) -> CandidatePerformanceMetrics:
        if run.metrics.status == "failed":
            raise CandidatePerformanceLimitError(run.metrics)
        return run.metrics

    @staticmethod
    def suite(
        cases: Sequence[CandidatePerformanceMetrics],
        *,
        config: CandidatePerformanceConfig | None = None,
    ) -> CandidatePerformanceSuiteReport:
        performance_config = config or CandidatePerformanceConfig()
        ordered = sorted(cases, key=lambda row: row.case_code)
        if not ordered:
            raise CandidatePerformanceError("performance suite requires cases")
        failure_codes = sorted(
            row.case_code for row in ordered if row.status == "failed"
        )
        input_payload = {
            "config": performance_config.model_dump(mode="python"),
            "case_input_fingerprints": [row.input_fingerprint for row in ordered],
        }
        input_fingerprint = stable_hash(
            input_payload,
            version="competitor_profile_candidate_performance_suite_input_v1",
        )
        return CandidatePerformanceSuiteReport(
            config=performance_config,
            status="failed" if failure_codes else "passed",
            case_count=len(ordered),
            cases=ordered,
            failure_case_codes=failure_codes,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    **input_payload,
                    "input_fingerprint": input_fingerprint,
                    "case_result_hashes": [row.result_hash for row in ordered],
                    "failure_case_codes": failure_codes,
                },
                version="competitor_profile_candidate_performance_suite_result_v1",
            ),
        )


def _source_pages(
    bundle: CompetitorProfileCategoryInputBundle,
    page_size: int,
) -> SourcePages:
    pages: dict[str, list[list[UpstreamRecordSnapshot]]] = {}
    for module_code, module in bundle.modules.items():
        records = [
            record
            for sku_code in module.records_by_sku
            for record in module.records_by_sku[sku_code]
        ]
        pages[module_code] = [
            records[offset : offset + page_size]
            for offset in range(0, len(records), page_size)
        ]
    return pages


__all__ = [
    "CandidatePerformanceBenchmark",
    "CandidatePerformanceError",
    "CandidatePerformanceLimitError",
    "CandidatePerformanceRun",
]
