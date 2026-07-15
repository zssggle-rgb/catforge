from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic_core import PydanticSerializationError

from app.services.core3_real_data.analyst import competitor_answer
from app.services.core3_real_data.analyst.competitor_profile_v1_1_adapter import (
    CompetitorProfileAgentAdapter,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    CandidateScopeClassifier,
    PairGateEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_materializer import (
    CompetitorProfileV11Materializer,
    HardExcludedPairMaterializationInput,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PairAnalysisCalculator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_persistence_schemas import (
    CompetitorProfileV11CompactDTO,
    CompetitorProfileV11QuestionDTO,
    CompetitorProfileV11QuestionPair,
    CompetitorProfileV11ReadResult,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    ProfileVersionAnalysisContext,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    CompetitorProfileV11Selector,
    PairSelectionInput,
)
from tests.core3_real_data.test_competitor_profile_v1_1_gate_evaluation import (
    _legacy_relations,
    _scope,
)
from tests.core3_real_data.test_competitor_profile_v1_1_materializer_generation import (
    _profile_context,
    _twenty_candidate_65e7q_item,
    _valid_market_only_assembly,
    _work_item,
)
from tests.core3_real_data.test_competitor_profile_v1_1_pair_analysis import (
    _assemble,
    _source,
)
from tests.core3_real_data.test_competitor_profile_v1_1_repository import (
    _zero_candidate_dto,
)
from tests.core3_real_data.test_competitor_profile_v1_1_schemas import _budget


def _materialize(item):
    return (
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


def _market_only_dto():
    source = _source()
    _, base = _assemble(source)
    assembly = _valid_market_only_assembly(base)
    gate = PairGateEvaluator().evaluate(
        scope=_scope(source),
        assembly=assembly,
        legacy_relation_assessments=_legacy_relations(assembly),
    )
    pair_input = PairSelectionInput(assembly=assembly, gate_evaluation=gate)
    selection = CompetitorProfileV11Selector().select([pair_input])
    return (
        CompetitorProfileV11Materializer()
        .materialize(
            profile_version=_profile_context(pair_input),
            target_snapshot=source.target_snapshot,
            candidate_snapshots=[source.candidate_snapshot],
            pair_assemblies=[assembly],
            gate_evaluations=[gate],
            selection_result=selection,
        )
        .dto
    )


def _hard_excluded_dto():
    source = _source()
    target = source.target_snapshot
    scope = CandidateScopeClassifier().classify(
        target_snapshot=target,
        candidate_snapshot=target,
        authoritative_manifest_sku_codes=[target.identity_market.sku_code],
    )
    gate = PairGateEvaluator().evaluate(
        scope=scope,
        project_id=target.project_id,
        category_code=target.category_code,
        competitor_profile_version_id=target.competitor_profile_version_id,
        release_scope_key=target.release_scope_key,
    )
    selection = CompetitorProfileV11Selector().select(
        [PairSelectionInput(gate_evaluation=gate)]
    )
    context = ProfileVersionAnalysisContext(
        competitor_profile_version_id=target.competitor_profile_version_id,
        project_id=target.project_id,
        category_code=target.category_code,
        product_category=target.category_code,
        release_scope_key=target.release_scope_key,
        source_batch_ids=["batch-1"],
        market_window="fixture-window",
        analysis_population="fixture-population",
        score_policy=selection.score_policy,
        performance_storage_budget=_budget(),
    )
    return (
        CompetitorProfileV11Materializer()
        .materialize(
            profile_version=context,
            target_snapshot=target,
            candidate_snapshots=[target],
            pair_assemblies=[],
            gate_evaluations=[gate],
            selection_result=selection,
            hard_excluded_inputs=[
                HardExcludedPairMaterializationInput(
                    candidate_sku_code=target.identity_market.sku_code,
                    candidate_snapshot_ref=target.snapshot_ref,
                    recall_sources=["authoritative_manifest"],
                    recall_rank=1,
                )
            ],
        )
        .dto
    )


def _question_dto(dto):
    question_result = next(
        row
        for row in dto.pair_analyses[0].business_questions
        if row.question_code == "purchase_choice"
    )
    return CompetitorProfileV11QuestionDTO(
        question_code="purchase_choice",
        profile_version=dto.profile_version,
        generation_receipt=dto.generation_receipt,
        target_snapshot=dto.target_snapshot,
        sku_summary=dto.sku_summary,
        priority_selections=dto.priority_selections,
        pairs=[
            CompetitorProfileV11QuestionPair(
                candidate_snapshot=dto.candidate_snapshots[0],
                pair_analysis=dto.pair_analyses[0],
                question_result=question_result,
            )
        ],
        fact_index=dto.fact_index,
        evidence_index=dto.evidence_index,
        profile_result_hash=dto.profile_result_hash,
    )


@pytest.mark.parametrize("category", ["TV", "AC"])
def test_adapter_and_renderer_preserve_saved_results_for_tv_and_ac(
    category: str,
) -> None:
    dto = _materialize(_work_item(category))
    profile = CompetitorProfileAgentAdapter().adapt_full(dto)
    answer = competitor_answer.render_competitor_answer_from_profile(
        profile=profile,
        with_report="markdown",
    )

    assert profile.profile_version.category_code == category
    assert [row.candidate_sku_code for row in profile.candidates] == [
        row.candidate_sku_code
        for row in dto.pair_analyses
        if row.scope_status == "analyzable"
    ]
    assert [row["candidate"]["sku_code"] for row in answer["top_competitors"]] == (
        profile.priority_order
    )
    assert answer["source"] == "competitor_profile_v1_1"
    assert answer["report_payload"]["markdown"]
    assert answer["feishu_card_payload"]["schema"] == "2.0"
    saved_dimensions = answer["top_competitors"][0]["saved_score_dimensions"]
    assert answer["dashboard_payload"]["competitors"][0]["score_dimensions"] == [
        {
            "dimension_cn": row["dimension_cn"],
            "score": competitor_answer._dashboard_score_value(row["score"]),
        }
        for row in saved_dimensions
    ]
    assert [row["dimension_cn"] for row in saved_dimensions] == [
        "购买池",
        "价值战场",
        "用户任务",
        "目标客群",
        "价值锚点",
        "替代压力",
    ]


def test_65e7q_keeps_all_twenty_candidates_and_saved_priority_order() -> None:
    dto = _materialize(_twenty_candidate_65e7q_item())
    profile = CompetitorProfileAgentAdapter().adapt_full(dto)
    answer = competitor_answer.render_competitor_answer_from_profile(profile=profile)

    assert profile.target_snapshot.identity_market.sku_code == "TV00029112"
    assert profile.target_snapshot.identity_market.model_name == "65E7Q"
    assert len(profile.candidates) == 20
    assert len(answer["all_candidates"]) == 20
    assert [row["candidate"]["sku_code"] for row in answer["top_competitors"]] == (
        profile.priority_order
    )
    assert {row["candidate"]["sku_code"] for row in answer["all_candidates"]} == {
        row.candidate_sku_code for row in dto.pair_analyses
    }
    assert answer["previous_priority_diffs"] == [
        {
            "candidate_sku_code": row.candidate_sku_code,
            "previous_rank": row.legacy_rank,
            "current_rank": row.new_rank,
            "diff_status": row.diff_status,
            "reason_code": row.reason_code,
            "reason_cn": row.reason_cn,
        }
        for row in dto.sku_summary.legacy_selection_diffs
    ]


def test_market_only_pair_preserves_null_analysis_score_and_zero_selection() -> None:
    dto = _market_only_dto()
    profile = CompetitorProfileAgentAdapter().adapt_full(dto)
    answer = competitor_answer.render_competitor_answer_from_profile(profile=profile)

    assert profile.candidates[0].score_breakdown.ranking_score is None
    assert dto.priority_selections[0].selection_score == Decimal("0")
    assert answer["top_competitors"][0]["business_score"] is None
    assert answer["top_competitors"][0]["ranking_trace"]["ranking_score"] is None
    assert answer["top_competitors"][0]["selection_gate"]["selected"] is True


def test_hard_exclusion_is_not_analyzed_but_remains_in_audit() -> None:
    dto = _hard_excluded_dto()
    profile = CompetitorProfileAgentAdapter().adapt_full(dto)
    answer = competitor_answer.render_competitor_answer_from_profile(profile=profile)

    assert profile.candidates == []
    assert len(profile.excluded_candidates) == 1
    assert profile.excluded_candidates[0].exclusion_reason_code == "self_pair"
    assert answer["top_competitors"] == []
    assert answer["all_candidates"] == []
    assert answer["excluded_candidate_audit"][0]["exclusion_reason_code"] == (
        "self_pair"
    )


def test_zero_candidate_profile_renders_explicit_no_conclusion() -> None:
    dto = _zero_candidate_dto("version-1")
    adapter = CompetitorProfileAgentAdapter()
    profile = adapter.adapt_full(dto)
    answer = competitor_answer.render_competitor_answer_from_profile(profile=profile)
    compact = adapter.adapt_compact(
        CompetitorProfileV11CompactDTO(
            profile_version=dto.profile_version,
            generation_receipt=dto.generation_receipt,
            target_snapshot=dto.target_snapshot,
            sku_summary=dto.sku_summary,
            priority_selections=dto.priority_selections,
            full_pair_index=dto.full_pair_index,
            profile_result_hash=dto.profile_result_hash,
        )
    )
    question = adapter.adapt_question(
        CompetitorProfileV11QuestionDTO(
            question_code="purchase_choice",
            profile_version=dto.profile_version,
            generation_receipt=dto.generation_receipt,
            target_snapshot=dto.target_snapshot,
            sku_summary=dto.sku_summary,
            priority_selections=dto.priority_selections,
            pairs=[],
            fact_index=dto.fact_index,
            evidence_index=dto.evidence_index,
            profile_result_hash=dto.profile_result_hash,
        )
    )

    assert profile.candidates == []
    assert profile.excluded_candidates == []
    assert profile.source_receipt.candidate_snapshot_result_hashes == {}
    assert profile.source_receipt.candidate_pair_result_hashes == {}
    assert compact.full_pair_index == []
    assert question.candidates == []
    assert answer["top_competitors"] == []
    assert "当前证据尚未形成稳定的重点竞品名单" in answer["short_answer"]


def test_compact_question_and_unavailable_reader_projections_are_explicit() -> None:
    dto = _materialize(_work_item())
    compact = CompetitorProfileV11CompactDTO(
        profile_version=dto.profile_version,
        generation_receipt=dto.generation_receipt,
        target_snapshot=dto.target_snapshot,
        sku_summary=dto.sku_summary,
        priority_selections=dto.priority_selections,
        full_pair_index=dto.full_pair_index,
        profile_result_hash=dto.profile_result_hash,
    ).model_copy(deep=True)
    question = _question_dto(dto)
    adapter = CompetitorProfileAgentAdapter()

    compact_result = adapter.adapt(
        CompetitorProfileV11ReadResult(
            status="available",
            read_mode="compact",
            competitor_profile_version_id=(
                dto.profile_version.competitor_profile_version_id
            ),
            compact=compact,
        )
    )
    question_result_projection = adapter.adapt(
        CompetitorProfileV11ReadResult(
            status="available",
            read_mode="question_specific",
            competitor_profile_version_id=(
                dto.profile_version.competitor_profile_version_id
            ),
            question=question,
        )
    )
    unavailable = adapter.adapt(
        CompetitorProfileV11ReadResult(
            status="profile_unavailable",
            read_mode="full",
        )
    )

    assert compact_result.compact is not None
    assert compact_result.compact.priority_order == [
        row.candidate_sku_code for row in dto.priority_selections
    ]
    assert question_result_projection.question is not None
    assert question_result_projection.question.question_code == "purchase_choice"
    assert unavailable.status == "profile_unavailable"
    assert unavailable.full is None


def test_partial_projections_reject_mixed_scope_and_missing_question_facts() -> None:
    dto = _materialize(_work_item())
    compact = CompetitorProfileV11CompactDTO(
        profile_version=dto.profile_version,
        generation_receipt=dto.generation_receipt,
        target_snapshot=dto.target_snapshot,
        sku_summary=dto.sku_summary,
        priority_selections=dto.priority_selections,
        full_pair_index=dto.full_pair_index,
        profile_result_hash=dto.profile_result_hash,
    ).model_copy(deep=True)
    compact.target_snapshot.release_scope_key = "other:TV"
    with pytest.raises(ValueError, match="scope must match"):
        CompetitorProfileAgentAdapter().adapt_compact(compact)

    mixed_candidate = _question_dto(dto).model_copy(deep=True)
    mixed_candidate.pairs[0].candidate_snapshot.release_scope_key = "other:TV"
    with pytest.raises(ValueError, match="mixed profile scope"):
        CompetitorProfileAgentAdapter().adapt_question(mixed_candidate)

    mixed_pair = _question_dto(dto).model_copy(deep=True)
    mixed_pair.pairs[0].pair_analysis.project_id = "other-project"
    with pytest.raises(ValueError, match="question pair.*mixed profile scope"):
        CompetitorProfileAgentAdapter().adapt_question(mixed_pair)

    question = _question_dto(dto)
    question.fact_index.clear()
    with pytest.raises(ValueError, match="facts must resolve"):
        CompetitorProfileAgentAdapter().adapt_question(question)


def test_post_build_mutation_fails_closed_for_every_projection() -> None:
    dto = _materialize(_work_item())
    profile = CompetitorProfileAgentAdapter().adapt_full(dto)
    profile.candidates[0].identity.model_name = "MUTATED"
    with pytest.raises(PydanticSerializationError, match="runtime projection"):
        profile.model_dump(mode="json")

    compact = CompetitorProfileAgentAdapter().adapt_compact(
        CompetitorProfileV11CompactDTO(
            profile_version=dto.profile_version,
            generation_receipt=dto.generation_receipt,
            target_snapshot=dto.target_snapshot,
            sku_summary=dto.sku_summary,
            priority_selections=dto.priority_selections,
            full_pair_index=dto.full_pair_index,
            profile_result_hash=dto.profile_result_hash,
        )
    )
    compact.priority_order.clear()
    with pytest.raises(PydanticSerializationError, match="runtime projection"):
        compact.model_dump(mode="json")

    question = CompetitorProfileAgentAdapter().adapt_question(_question_dto(dto))
    question.candidates[0].identity.model_name = "MUTATED"
    with pytest.raises(PydanticSerializationError, match="runtime projection"):
        question.model_dump(mode="json")


def test_renderer_rejects_invalid_display_options_and_translates_pressure_codes() -> (
    None
):
    profile = CompetitorProfileAgentAdapter().adapt_full(_materialize(_work_item()))

    with pytest.raises(ValueError, match="max_chat_chars"):
        competitor_answer.render_competitor_answer_from_profile(
            profile=profile,
            max_chat_chars=0,
        )
    with pytest.raises(ValueError, match="with_report"):
        competitor_answer.render_competitor_answer_from_profile(
            profile=profile,
            with_report="unsupported",  # type: ignore[arg-type]
        )
    assert {
        "value_substitution",
        "price_suppression",
        "configuration_benchmark",
        "scenario_mindshare",
        "brand_ecosystem",
        "downtrade_diversion",
        "uptrade_alternative",
        "low_pressure_review",
    }.issubset(competitor_answer.PROFILE_V11_PRESSURE_CN)
    assert {
        "purchase_pool",
        "battlefield_overlap",
        "user_task_overlap",
        "target_group_overlap",
        "parameter_comparison",
        "claim_comparison",
        "user_realization_comparison",
        "purchase_reason_comparison",
        "value_anchor",
        "replacement_pressure",
        "market_validation",
    } == set(competitor_answer.PROFILE_V11_DIMENSION_CN)


def test_adapter_and_renderer_make_zero_analysis_sort_or_selection_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dto = _materialize(_work_item())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("profile consumption attempted live analysis")

    for name in (
        "_enrich_competitor",
        "_sort_key",
        "_assign_top_roles",
        "_select_top_competitors",
        "_market_validation_score",
    ):
        monkeypatch.setattr(competitor_answer, name, forbidden)
    monkeypatch.setattr(PairAnalysisCalculator, "calculate", forbidden)
    monkeypatch.setattr(PairGateEvaluator, "evaluate", forbidden)
    monkeypatch.setattr(CompetitorProfileV11Selector, "select", forbidden)

    profile = CompetitorProfileAgentAdapter().adapt_full(dto)
    answer = competitor_answer.render_competitor_answer_from_profile(profile=profile)

    assert answer["top_competitors"]


def test_runtime_projection_contains_no_legacy_or_raw_bags() -> None:
    dto = _materialize(_work_item())
    payload = CompetitorProfileAgentAdapter().adapt_full(dto).model_dump(mode="json")

    keys = _mapping_keys(payload)
    assert "raw_details" not in keys
    assert not any(
        key.lower().replace("_", "").startswith("legacy")
        and key != "legacy_candidate_count"
        for key in keys
    )
    assert payload["sku_competition_summary"]["legacy_candidate_count"] == 1


def _mapping_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_mapping_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_mapping_keys(child))
    return keys
