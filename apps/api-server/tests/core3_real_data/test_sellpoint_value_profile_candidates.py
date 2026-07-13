from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.models import entities
from app.services.core3_real_data.analyst import atomic_handlers as atomic_handlers_module
from app.services.core3_real_data.analyst.analyst_schemas import (
    AnalystContext,
    ResolvedSku,
)
from app.services.core3_real_data.analyst.atomic_handlers import AtomicAnalystHandlers
from app.services.core3_real_data.analyst.sellpoint_value_profile_candidate_repositories import (
    SellpointValueCandidateUniverseRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_candidate_service import (
    build_candidate_universe_manifest,
    candidate_manifest_as_v4_fallback,
)


def _record(
    index: int,
    *,
    component: bool = True,
    feature: dict[str, Any] | None = None,
    selection_rank: int | None = None,
    processing_status: str = "success",
    review_required: bool = False,
) -> dict[str, Any]:
    sku_code = f"TV-CANDIDATE-{index:03d}"
    return {
        "candidate_sku_code": sku_code,
        "candidate_brand_name": f"品牌{index % 5}",
        "candidate_model_name": f"型号{index}",
        "same_brand_flag": index % 4 == 0,
        "primary_relation_type": "direct_fight",
        "relation_types": ["direct_fight", "price_volume_pressure"],
        "recall_sources": ["M07", "M11C"],
        "recall_strength": "strong",
        "recall_priority_score": 0.9 - (index % 10) / 100,
        "processing_status": processing_status,
        "review_required": review_required,
        "review_reasons": ["pool_review"] if review_required else [],
        "pool_result_hash": f"pool-{index}",
        "component": (
            {
                "component_total_score": 0.8,
                "sample_status": "sufficient",
                "processing_status": "success",
                "review_required": False,
                "review_reasons": [],
                "result_hash": f"component-{index}",
            }
            if component
            else None
        ),
        "roles": [
            {
                "role_code": "direct_fight",
                "role_name_cn": "直接竞争参照",
                "role_score": 0.82,
                "role_confidence": 0.9,
                "auto_select_eligible": True,
                "review_required": False,
            }
        ],
        "feature": feature
        if feature is not None
        else {
            "market_feature": {"price_wavg": 5000 + index},
            "param_feature": {"refresh_rate": 144},
            "claim_value_overlap": {"picture": 0.8},
            "battlefield_overlap": {"BF_PICTURE": 0.7},
            "task_overlap": {"movie": 0.6},
            "audience_overlap": {"family": 0.6},
            "feature_snapshot_hash": f"feature-{index}",
        },
        "selection": (
            {
                "slot_code": "same_value",
                "slot_name_cn": "重点直接竞品",
                "selection_rank": selection_rank,
                "result_hash": f"selection-{index}",
            }
            if selection_rank is not None
            else None
        ),
    }


def _manifest(
    records: list[dict[str, Any]],
    *,
    references: list[dict[str, Any]] | None = None,
):
    return build_candidate_universe_manifest(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        target_sku_code="TV-TARGET",
        candidate_records=records,
        market_references=references or [],
    )


@pytest.mark.parametrize("candidate_count", [0, 1, 12, 35])
def test_manifest_has_no_business_count_cap(candidate_count: int) -> None:
    manifest = _manifest([_record(index) for index in range(candidate_count)])

    assert len(manifest.competitor_candidates) == candidate_count
    assert manifest.competitor_universe_status == (
        "available" if candidate_count else "unavailable"
    )
    assert len(candidate_manifest_as_v4_fallback(manifest)) == candidate_count


@pytest.mark.parametrize("selected_count", [0, 1, 3])
def test_m14_only_labels_candidates_without_changing_universe(
    selected_count: int,
) -> None:
    records = [
        _record(index, selection_rank=index + 1 if index < selected_count else None)
        for index in range(35)
    ]

    manifest = _manifest(records)

    assert len(manifest.competitor_candidates) == 35
    assert sum(row.m14_selected for row in manifest.competitor_candidates) == selected_count


def test_manifest_sorting_and_hash_are_input_order_independent() -> None:
    records = [_record(index, selection_rank=index + 1 if index < 3 else None) for index in range(18)]
    references = [
        {
            "sku_code": "TV-REFERENCE-1",
            "reference_purposes": ["same_size_market"],
            "price_wavg": 4900,
        },
        {
            "sku_code": "TV-REFERENCE-1",
            "reference_purposes": ["battlefield_benchmark"],
            "price_wavg": 4900,
        },
    ]

    first = _manifest(records, references=references)
    second = _manifest(list(reversed(records)), references=list(reversed(references)))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.candidate_manifest_hash == second.candidate_manifest_hash


def test_question_eligibility_degrades_without_promoting_weak_rows() -> None:
    records = [
        _record(1),
        _record(2, feature={"market_feature": {"price_wavg": 5000}}),
        _record(3, review_required=True),
        _record(4, processing_status="failed"),
        _record(5, component=False),
    ]

    manifest = _manifest(records)
    by_code = {row.candidate_sku_code: row for row in manifest.competitor_candidates}

    assert by_code["TV-CANDIDATE-001"].eligibility_status == "eligible"
    assert by_code["TV-CANDIDATE-002"].eligibility_status == "limited"
    assert by_code["TV-CANDIDATE-003"].eligibility_status == "review_required"
    assert by_code["TV-CANDIDATE-004"].eligibility_status == "blocked"
    assert by_code["TV-CANDIDATE-005"].eligibility_status == "recalled_only"
    assert not by_code["TV-CANDIDATE-003"].eligible_questions
    assert not by_code["TV-CANDIDATE-004"].eligible_questions
    assert not by_code["TV-CANDIDATE-005"].eligible_questions
    assert len(candidate_manifest_as_v4_fallback(manifest)) == 2


def test_reference_pool_stays_separate_and_merges_reference_purposes() -> None:
    records = [_record(1)]
    references = [
        {
            "sku_code": "TV-CANDIDATE-001",
            "reference_purposes": ["same_size_market"],
            "price_wavg": 5100,
        },
        {
            "sku_code": "TV-CANDIDATE-001",
            "reference_purposes": ["performance_archetype"],
            "price_wavg": 5100,
        },
        {
            "sku_code": "TV-REFERENCE-ONLY",
            "reference_purposes": ["parameter_group"],
            "price_wavg": 4800,
        },
        {"sku_code": "TV-TARGET", "reference_purposes": ["same_size_market"]},
    ]

    manifest = _manifest(records, references=references)
    by_code = {row.reference_sku_code: row for row in manifest.analysis_references}

    assert len(manifest.competitor_candidates) == 1
    assert set(by_code) == {"TV-CANDIDATE-001", "TV-REFERENCE-ONLY"}
    assert by_code["TV-CANDIDATE-001"].also_competitor is True
    assert by_code["TV-CANDIDATE-001"].reference_purposes == [
        "performance_archetype",
        "same_size_market",
    ]
    assert by_code["TV-REFERENCE-ONLY"].also_competitor is False


def test_without_m12_or_m13_market_rows_remain_reference_only() -> None:
    manifest = _manifest(
        [],
        references=[
            {
                "sku_code": "TV-SAME-SIZE-ONLY",
                "reference_purposes": ["same_size_market"],
                "price_wavg": 4600,
            }
        ],
    )

    assert manifest.competitor_universe_status == "unavailable"
    assert manifest.competitor_candidates == []
    assert [row.reference_sku_code for row in manifest.analysis_references] == [
        "TV-SAME-SIZE-ONLY"
    ]
    assert candidate_manifest_as_v4_fallback(manifest) == []


class _ScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def scalars(self) -> list[Any]:
        return self.rows


class _CountingSession:
    def __init__(self, pools: list[Any]) -> None:
        self.pools = pools
        self.query_count = 0

    def execute(self, statement: Any) -> _ScalarResult:
        self.query_count += 1
        entity = statement.column_descriptions[0].get("entity")
        return _ScalarResult(self.pools if entity is entities.Core3CandidatePool else [])


def _pool(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        candidate_pool_id=f"pool-{index}",
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        target_sku_code="TV-TARGET",
        candidate_sku_code=f"TV-CANDIDATE-{index:03d}",
        candidate_brand_name="品牌",
        candidate_model_name=f"型号{index}",
        same_brand_flag=False,
        primary_relation_type="direct_fight",
        relation_types_json=["direct_fight"],
        recall_sources_json=["M07"],
        recall_strength="strong",
        recall_priority_score=0.8,
        processing_status="success",
        review_required=False,
        review_reason_json={},
        result_hash=f"pool-hash-{index}",
    )


def test_repository_query_count_is_constant_above_one_candidate() -> None:
    query_counts = []
    for count in (1, 12, 35):
        session = _CountingSession([_pool(index) for index in range(count)])
        repository = SellpointValueCandidateUniverseRepository(
            session,  # type: ignore[arg-type]
            project_id="project-1",
            category_code="TV",
        )

        records = repository.load_candidate_records(
            batch_id="batch-1",
            target_sku_code="TV-TARGET",
        )

        assert len(records) == count
        query_counts.append(session.query_count)

    assert query_counts == [5, 5, 5]


def test_repository_without_m12_returns_empty_without_m13_queries() -> None:
    session = _CountingSession([])
    repository = SellpointValueCandidateUniverseRepository(
        session,  # type: ignore[arg-type]
        project_id="project-1",
        category_code="TV",
    )

    records = repository.load_candidate_records(
        batch_id="batch-1",
        target_sku_code="TV-TARGET",
    )

    assert records == []
    assert session.query_count == 2


def test_atomic_handler_returns_full_competitors_and_separate_market_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repository:
        db = object()
        project_id = "project-1"
        category_code = "TV"

        def __init__(self) -> None:
            self.reference_limit = None

        def resolve_sku(self, **_kwargs: Any) -> list[ResolvedSku]:
            return [
                ResolvedSku(
                    sku_code="TV-TARGET",
                    brand_name="海信",
                    model_name="65E7Q",
                    product_category="TV",
                    source="fixture",
                )
            ]

        def same_size_price_candidates(self, **kwargs: Any) -> dict[str, Any]:
            self.reference_limit = kwargs["limit"]
            return {
                "match_policy": "m07_same_size_price_band",
                "candidates": [
                    {
                        "sku_code": "TV-REFERENCE",
                        "brand_name": "参照品牌",
                        "model_name": "参照型号",
                        "price_wavg": 4800,
                    }
                ],
            }

    class CandidateRepository:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def load_candidate_records(self, **_kwargs: Any) -> list[dict[str, Any]]:
            return [_record(index) for index in range(35)]

    monkeypatch.setattr(
        atomic_handlers_module,
        "SellpointValueCandidateUniverseRepository",
        CandidateRepository,
    )
    repository = Repository()
    handlers = AtomicAnalystHandlers(repository)  # type: ignore[arg-type]
    context = AnalystContext(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
    )

    result = handlers.sellpoint_value_candidate_universe(
        context,
        sku_code="TV-TARGET",
    )

    assert result["status"] == "ok"
    assert repository.reference_limit == 0
    manifest = result["result"]["candidate_universe"]
    assert len(manifest["competitor_candidates"]) == 35
    assert [row["reference_sku_code"] for row in manifest["analysis_references"]] == [
        "TV-REFERENCE"
    ]
