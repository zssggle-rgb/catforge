from __future__ import annotations

import copy
import inspect
from decimal import Decimal
from time import perf_counter
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst import (
    competitor_profile_candidate_performance as performance_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_performance import (
    CandidatePerformanceBenchmark,
    CandidatePerformanceError,
    CandidatePerformanceLimitError,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_performance_schemas import (
    CandidatePerformanceConfig,
    CandidatePerformanceMetrics,
    CandidatePerformanceSuiteReport,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer import (
    CompetitorProfileMaterializer,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)
from tests.core3_real_data.test_competitor_profile_input_provider import (
    _provider,
    _request,
    _seed_category,
)
from tests.core3_real_data.test_competitor_profile_materializer import (
    _config as _materializer_config,
)


def _large_bundle(
    category: str,
    candidate_count: int,
    *,
    sparse: bool = False,
) -> CompetitorProfileCategoryInputBundle:
    specs: list[dict[str, Any]] = []
    for number in range(1, candidate_count + 2):
        spec = _default_spec(category, number)
        spec.update(
            {
                "brand": "目标品牌" if number == 1 else f"品牌-{number % 17}",
                "price": Decimal("5000") + Decimal(number % 100),
                "weekly_volume": Decimal("100") + Decimal(number % 31),
                "market_pool": "full-shared-market",
                "task_primary": "shared-task",
                "audience_primary": "shared-audience",
                "battlefield_primary": "shared-value",
                "purchase_reasons": ["shared-reason"],
                "claim_values": ["shared-claim"],
            }
        )
        if sparse and number > 1:
            spec["missing_modules"] = {
                "M04C",
                "M05C",
                "M09C",
                "M10C",
                "M11C",
                "M11D",
                "M12C",
                "M12D",
            }
        specs.append(spec)
    return _category_bundle(category, specs)


def _measure(
    category: str,
    candidate_count: int,
    *,
    case_code: str,
    sparse: bool = False,
    page_size: int | None = None,
    config: CandidatePerformanceConfig | None = None,
    provider_select_count: int | None = None,
) -> Any:
    bundle = _large_bundle(category, candidate_count, sparse=sparse)
    return CandidatePerformanceBenchmark().measure(
        bundle,
        _target_bundle(bundle, f"{category}000001"),
        case_code=case_code,
        expected_candidate_count=candidate_count,
        config=config,
        source_page_size=page_size,
        provider_select_count=provider_select_count,
    )


@pytest.mark.parametrize("candidate_count", [0, 1, 155])
def test_small_and_current_ac_scale_keep_every_candidate(candidate_count: int) -> None:
    run = _measure(
        "TV",
        candidate_count,
        case_code=f"tv-{candidate_count:03d}",
        page_size=64,
    )
    metrics = CandidatePerformanceBenchmark().enforce(run)

    assert metrics.status == "passed"
    assert metrics.recall_candidate_count == candidate_count
    assert metrics.eligibility_candidate_count == candidate_count
    assert metrics.question_assessment_count == candidate_count * 8
    assert metrics.wall_time_ms > 0
    assert metrics.peak_memory_mib > 0
    assert len(run.pipeline.recall_manifest.candidates) == candidate_count


def test_tv_377_and_above_current_scale_have_no_business_count_cap() -> None:
    current = _measure(
        "TV",
        377,
        case_code="tv-current-377",
        page_size=64,
    )
    above = _measure(
        "TV",
        512,
        case_code="tv-above-current-512-sparse",
        sparse=True,
        page_size=256,
    )

    assert (
        CandidatePerformanceBenchmark().enforce(current).recall_candidate_count == 377
    )
    assert CandidatePerformanceBenchmark().enforce(above).recall_candidate_count == 512
    assert len(current.pipeline.eligibility_manifest.candidates) == 377
    assert len(above.pipeline.eligibility_manifest.candidates) == 512
    assert all(
        row.candidate_status == "reference_only"
        for row in above.pipeline.eligibility_manifest.candidates
    )


def test_full_materializer_conserves_377_pairs_and_all_seven_relations() -> None:
    bundle = _large_bundle("TV", 377)
    started = perf_counter()
    result = CompetitorProfileMaterializer().materialize(
        bundle,
        _target_bundle(bundle, "TV000001"),
        _materializer_config("TV"),
    )
    elapsed_seconds = perf_counter() - started

    assert len(result.draft.pairs) == 377
    assert sum(
        len(pair.relation_assessments) for pair in result.draft.pairs
    ) == 377 * 7
    assert len({pair.candidate.sku_code for pair in result.draft.pairs}) == 377
    assert elapsed_seconds < 30


def test_ac_155_uses_the_same_full_pipeline_without_tv_rule_leakage() -> None:
    run = _measure(
        "AC",
        155,
        case_code="ac-current-155",
        page_size=64,
    )
    metrics = CandidatePerformanceBenchmark().enforce(run)

    assert metrics.category_code == "AC"
    assert metrics.recall_candidate_count == 155
    assert all(
        row.candidate.product_category == "AC"
        for row in run.pipeline.eligibility_manifest.candidates
    )


def test_frozen_page_sizes_change_only_io_metrics_not_business_hashes() -> None:
    runs = [
        _measure(
            "TV",
            35,
            case_code=f"tv-pages-{page_size:03d}",
            page_size=page_size,
        )
        for page_size in (1, 17, 64, 256)
    ]

    assert len({run.metrics.recall_result_hash for run in runs}) == 1
    assert len({run.metrics.eligibility_result_hash for run in runs}) == 1
    assert len({run.metrics.determinism_result_hash for run in runs}) == 1
    assert [run.metrics.source_page_count for run in runs] == sorted(
        (run.metrics.source_page_count for run in runs),
        reverse=True,
    )
    assert all(run.metrics.status == "passed" for run in runs)


def test_performance_overrun_and_query_growth_fail_explicitly_without_truncating() -> (
    None
):
    config = CandidatePerformanceConfig(
        config_version="test-explicit-performance-failure-v1",
        max_wall_time_ms=Decimal("0.001"),
        max_provider_select_count=1,
    )
    run = _measure(
        "TV",
        1,
        case_code="explicit-limit-failure",
        page_size=64,
        config=config,
        provider_select_count=2,
    )

    assert run.metrics.status == "failed"
    assert set(run.metrics.failure_reason_codes) >= {
        "provider_select_count_exceeded",
        "wall_time_limit_exceeded",
    }
    assert run.metrics.recall_candidate_count == 1
    assert len(run.pipeline.recall_manifest.candidates) == 1
    with pytest.raises(CandidatePerformanceLimitError) as exc_info:
        CandidatePerformanceBenchmark().enforce(run)
    assert exc_info.value.metrics.result_hash == run.metrics.result_hash


def test_actual_g09_provider_uses_fixed_select_count_and_target_adds_no_query() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    entities.Base.metadata.create_all(engine)
    session = Session(engine, autoflush=False, future=True)
    try:
        _seed_category(session)
        provider = _provider(session)
        select_count = 0

        def count_selects(_, __, statement, ___, ____, _____) -> None:
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            bundle = provider.load_category_input_bundle(_request())
            count_after_category = select_count
            target = provider.load_target_input(bundle, "TV000001")
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        run = CandidatePerformanceBenchmark().measure(
            bundle,
            target,
            case_code="g09-provider-fixed-query-count",
            expected_candidate_count=1,
            provider_select_count=select_count,
        )
        assert count_after_category == 11
        assert select_count == 11
        assert CandidatePerformanceBenchmark().enforce(run).provider_select_count == 11
    finally:
        session.close()
        engine.dispose()


def test_exact_duplicate_records_are_canonicalized_before_performance_counts() -> None:
    bundle = _large_bundle("TV", 1)
    payload = bundle.model_dump(mode="python")
    rows = payload["modules"]["M12C"]["records_by_sku"]["TV000002"]
    rows.append(copy.deepcopy(rows[0]))
    rows.sort(key=lambda row: (row["source_batch_id"], row["record_id"]))
    payload["modules"]["M12C"]["record_count"] += 1
    duplicated = CompetitorProfileCategoryInputBundle.model_validate(payload)

    run = CandidatePerformanceBenchmark().measure(
        duplicated,
        _target_bundle(duplicated, "TV000001"),
        case_code="duplicate-source-canonicalization",
        expected_candidate_count=1,
        source_page_size=17,
    )
    assert run.metrics.status == "passed"
    assert run.metrics.recall_candidate_count == 1
    stats = {
        row.module_code: row for row in run.pipeline.receipt.canonicalization_stats
    }
    assert stats["M12C"].category_exact_duplicate_count == 1


def test_suite_report_and_typed_contracts_preserve_failed_cases() -> None:
    passed = _measure("TV", 1, case_code="case-passed").metrics
    failed_config = CandidatePerformanceConfig(
        config_version="test-query-limit-v1",
        max_provider_select_count=1,
    )
    failed = _measure(
        "TV",
        1,
        case_code="case-failed",
        config=failed_config,
        provider_select_count=2,
    ).metrics
    suite = CandidatePerformanceBenchmark.suite([passed, failed])

    assert suite.status == "failed"
    assert suite.failure_case_codes == ["case-failed"]
    assert [row.case_code for row in suite.cases] == ["case-failed", "case-passed"]

    payload = suite.model_dump(mode="python")
    payload["failure_case_codes"] = []
    with pytest.raises(ValidationError, match="failure case codes"):
        CandidatePerformanceSuiteReport.model_validate(payload)

    metrics_payload = passed.model_dump(mode="python")
    metrics_payload["question_assessment_count"] += 1
    with pytest.raises(ValidationError, match="eight questions"):
        CandidatePerformanceMetrics.model_validate(metrics_payload)


def test_config_version_scope_and_runtime_boundaries_are_explicit() -> None:
    with pytest.raises(ValidationError, match="new config version"):
        CandidatePerformanceConfig(max_wall_time_ms=Decimal("1000"))
    with pytest.raises(ValidationError, match="positive, sorted and unique"):
        CandidatePerformanceConfig(
            config_version="test-bad-pages-v1",
            page_sizes=[64, 1],
        )
    with pytest.raises(CandidatePerformanceError, match="authoritative SKU universe"):
        bundle = _large_bundle("TV", 1)
        CandidatePerformanceBenchmark().measure(
            bundle,
            _target_bundle(bundle, "TV000001"),
            case_code="invalid-expected-count",
            expected_candidate_count=2,
        )

    source = inspect.getsource(performance_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
