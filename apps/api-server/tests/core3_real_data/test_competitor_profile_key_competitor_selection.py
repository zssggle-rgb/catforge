from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_key_competitor_selection as selection_module,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection import (
    KeyCompetitorSelectionError,
    KeyCompetitorSelector,
    _selection_reason_cn,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection_schemas import (
    DecisionTopicAssessment,
    KeyCompetitorSelectionBundle,
    KeyCompetitorSelectionConfig,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
)
from tests.core3_real_data.test_competitor_profile_price_volume_pressure import (
    _two_specs,
)
from tests.core3_real_data.test_competitor_profile_relation_evaluation import (
    _align_value_layers,
    _evaluate,
    _value_config,
)


def _config(
    category: str = "TV",
    *,
    version: str = "key-selection-test-v1",
) -> KeyCompetitorSelectionConfig:
    return KeyCompetitorSelectionConfig(
        config_version=version,
        product_category=category,
        decision_topic_order=[
            "purchase_choice",
            "price_scale_pressure",
            "portfolio_or_scenario",
            "value_route",
        ],
        topic_relation_priority={
            "purchase_choice": [
                "direct_substitute",
                "same_budget_alternative",
            ],
            "price_scale_pressure": [
                "downtrade_diversion",
                "uptrade_alternative",
                "same_budget_alternative",
                "direct_substitute",
            ],
            "portfolio_or_scenario": [
                "same_brand_ladder",
                "scenario_substitute",
            ],
            "value_route": [
                "same_value_substitute",
                "uptrade_alternative",
                "downtrade_diversion",
                "direct_substitute",
                "same_budget_alternative",
            ],
        },
    )


def _select(relation_bundle, config: KeyCompetitorSelectionConfig | None = None):
    return KeyCompetitorSelector().select(
        relation_bundle,
        config or _config(relation_bundle.product_category),
    )


def _decision(result: KeyCompetitorSelectionBundle, sku_code: str):
    return next(
        row for row in result.pair_decisions if row.candidate.sku_code == sku_code
    )


def _fully_aligned_relation_bundle(candidate_codes: tuple[str, ...]):
    bundle = _category_bundle()
    sku_codes = ("TV000001", *candidate_codes)
    _align_value_layers(bundle, sku_codes, code="clear-picture")
    for sku_code in sku_codes:
        bundle.modules["M12D"].records_by_sku[sku_code][0].facts[
            "core_payment_anchors_json"
        ] = [{"anchor_code": "clear-picture"}]
    value_config = _value_config(
        discriminative=("clear-picture",),
        coverage={"clear-picture": Decimal("0.20")},
    )
    return _evaluate(bundle, value_config=value_config)[4]


def _sparse_only_relation_bundle():
    target = _default_spec("TV", 1)
    target.update(
        {
            "brand": "海信",
            "price": Decimal("5000"),
            "task_primary": "cinema",
            "battlefield_primary": "picture",
        }
    )
    candidate = _default_spec("TV", 2)
    candidate.update(
        {
            "price": Decimal("5050"),
            "task_primary": "cinema",
            "battlefield_primary": "picture",
            "missing_modules": {"M09C", "M10C", "M11C", "M11D", "M12C", "M12D"},
        }
    )
    return _evaluate(_category_bundle(specs=[target, candidate]))[4]


def _p3_limited_relation_bundle():
    specs = _two_specs(
        candidate_price=Decimal("7000"),
        candidate_volume=Decimal("100"),
    )
    bundle = _category_bundle(specs=specs)
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002"),
        code="reason-shared",
    )
    value_config = _value_config(
        discriminative=("reason-shared",),
        coverage={"reason-shared": Decimal("0.20")},
    )
    return _evaluate(bundle, value_config=value_config)[4]


def _single_pair_bundle(relation_bundle, pair, *, suffix: str):
    return relation_bundle.model_copy(
        update={
            "candidate_count": 1,
            "pairs": [pair],
            "result_hash": f"{relation_bundle.result_hash}-{suffix}",
        }
    )


def _questions_with_availability(pair, updates: dict[str, str]):
    rows = []
    for question in pair.question_eligibility:
        availability = updates.get(question.question_code)
        rows.append(
            question
            if availability is None
            else question.model_copy(
                update={
                    "availability": availability,
                    "missing_inputs": (
                        [] if availability == "eligible" else ["synthetic_gap"]
                    ),
                }
            )
        )
    return rows


def test_a14_one_verified_candidate_is_selected_without_filling_three() -> None:
    relation_bundle = _evaluate(_category_bundle())[4]
    result = _select(relation_bundle)

    assert result.selection_state == "selected"
    assert result.selected_count == 1
    assert [row.candidate_sku_code for row in result.selections] == ["TV000002"]
    assert result.selections[0].selection_rank == 1
    assert result.selections[0].primary_decision_topic == "purchase_choice"
    assert _decision(result, "TV000003").non_selection_reason_code == (
        "review_required"
    )
    assert _decision(result, "TV000006").non_selection_reason_code == (
        "ineligible_status"
    )


def test_two_candidates_cover_purchase_and_portfolio_without_duplicate_slots() -> None:
    relation_bundle = _fully_aligned_relation_bundle(("TV000002", "TV000003"))
    result = _select(relation_bundle)

    assert result.selected_count == 2
    assert [row.candidate_sku_code for row in result.selections] == [
        "TV000002",
        "TV000003",
    ]
    assert [row.primary_decision_topic for row in result.selections] == [
        "purchase_choice",
        "portfolio_or_scenario",
    ]
    assert [row.selection_rank for row in result.selections] == [1, 2]
    assert result.selections[1].primary_relation_code == "same_brand_ladder"
    assert "同品牌产品线的升降档关系" in result.selections[1].selection_reason_cn
    assert "同品牌产品线重叠或" not in result.selections[1].selection_reason_cn


def test_scenario_selection_reason_does_not_imply_same_brand() -> None:
    reason = _selection_reason_cn(
        "portfolio_or_scenario",
        "scenario_substitute",
    )

    assert "另一种产品方案" in reason
    assert "同品牌" not in reason


def test_three_candidates_add_stronger_price_pressure_and_portfolio_information() -> (
    None
):
    relation_bundle = _fully_aligned_relation_bundle(
        ("TV000002", "TV000003", "TV000004")
    )
    result = _select(relation_bundle)

    assert result.selected_count == 3
    assert [row.candidate_sku_code for row in result.selections] == [
        "TV000002",
        "TV000004",
        "TV000003",
    ]
    assert [row.primary_decision_topic for row in result.selections] == [
        "purchase_choice",
        "price_scale_pressure",
        "portfolio_or_scenario",
    ]
    assert len({row.candidate_sku_code for row in result.selections}) == 3


def test_zero_selection_distinguishes_no_priority_insufficient_and_review() -> None:
    unrelated = _two_specs(
        candidate_price=Decimal("5100"),
        candidate_volume=Decimal("120"),
        different_route=True,
        shared_reason=False,
    )
    unrelated[1]["task_primary"] = "gaming"
    no_priority = _select(_evaluate(_category_bundle(specs=unrelated))[4])
    assert no_priority.selected_count == 0
    assert no_priority.selection_state == "no_priority_competitor"

    insufficient = _select(_sparse_only_relation_bundle())
    assert insufficient.selected_count == 0
    assert insufficient.selection_state == "insufficient_evidence"

    target = _default_spec("TV", 1)
    target.update(
        {
            "brand": "海信",
            "price": Decimal("5000"),
            "task_primary": "cinema",
            "battlefield_primary": "picture",
        }
    )
    candidate = _default_spec("TV", 2)
    candidate.update(
        {
            "brand": "海信",
            "price": Decimal("6000"),
            "task_primary": "gaming",
            "battlefield_primary": "gaming",
            "battlefield_secondary": ["picture"],
        }
    )
    review = _select(_evaluate(_category_bundle(specs=[target, candidate]))[4])
    assert review.selected_count == 0
    assert review.selection_state == "review_required"
    assert review.review_required is True


def test_a13_high_volume_reference_never_enters_key_selection() -> None:
    bundle = _category_bundle()
    market = bundle.modules["M07"].records_by_sku["TV000006"][0]
    market.facts["sales_volume_total"] = Decimal("999999")
    relation_bundle = _evaluate(bundle)[4]
    result = _select(relation_bundle)

    sparse = _decision(result, "TV000006")
    assert sparse.selected is False
    assert sparse.source_candidate_status == "reference_only"
    assert sparse.non_selection_reason_code == "ineligible_status"


def test_a15_duplicate_theme_keeps_stronger_candidate_and_explains_the_other() -> None:
    target = _default_spec("TV", 1)
    target.update(
        {
            "brand": "海信",
            "price": Decimal("5000"),
            "task_primary": "cinema",
            "audience_primary": "family-av",
            "battlefield_primary": "picture",
            "purchase_reasons": ["clear-picture"],
            "claim_values": ["clear-picture"],
        }
    )
    strong = _default_spec("TV", 2)
    strong.update(
        {
            "brand": "TCL",
            "price": Decimal("5100"),
            "task_primary": "cinema",
            "audience_primary": "family-av",
            "battlefield_primary": "picture",
            "purchase_reasons": ["clear-picture"],
            "claim_values": ["clear-picture"],
        }
    )
    weaker = _default_spec("TV", 3)
    weaker.update(
        {
            "brand": "创维",
            "price": Decimal("5100"),
            "task_primary": "cinema",
            "battlefield_primary": "picture",
            "purchase_reasons": ["clear-picture"],
            "claim_values": ["clear-picture"],
            "missing_modules": {"M05C", "M10C", "M12C"},
        }
    )
    bundle = _category_bundle(specs=[target, strong, weaker])
    _align_value_layers(bundle, ("TV000001", "TV000002"), code="clear-picture")
    value_config = _value_config(
        discriminative=("clear-picture",),
        coverage={"clear-picture": Decimal("0.20")},
    )
    relation_bundle = _evaluate(bundle, value_config=value_config)[4]
    result = _select(relation_bundle)

    assert [row.candidate_sku_code for row in result.selections] == ["TV000002"]
    assert _decision(result, "TV000003").non_selection_reason_code == (
        "weaker_duplicate_pressure"
    )


def test_same_strength_duplicate_uses_sku_tie_break_and_topic_covered_reason() -> None:
    specs = _two_specs(
        candidate_price=Decimal("5100"),
        candidate_volume=Decimal("120"),
    )
    clone = dict(specs[1])
    clone["sku_code"] = "TV000003"
    clone["model"] = "型号3"
    bundle = _category_bundle(specs=[specs[0], specs[1], clone])
    _align_value_layers(
        bundle,
        ("TV000001", "TV000002", "TV000003"),
        code="reason-shared",
    )
    value_config = _value_config(
        discriminative=("reason-shared",),
        coverage={"reason-shared": Decimal("0.20")},
    )
    result = _select(_evaluate(bundle, value_config=value_config)[4])

    assert result.selections[0].candidate_sku_code == "TV000002"
    assert _decision(result, "TV000003").non_selection_reason_code == (
        "topic_already_covered"
    )


def test_passed_and_high_confidence_outrank_limited_and_medium_without_score() -> None:
    passed_high = DecisionTopicAssessment(
        topic_code="value_route",
        eligible=True,
        usable_relation_codes=["same_value_substitute"],
        best_relation_code="same_value_substitute",
        best_relation_status="passed",
        best_confidence_level="high",
        independent_evidence_family_count=3,
        f1_f4_evidence_count=2,
        market_pressure_clarity="clear",
        limitation_count=0,
        reason_code="verified_decision_topic",
        result_hash="passed-high",
    )
    limited_medium = DecisionTopicAssessment(
        topic_code="value_route",
        eligible=True,
        usable_relation_codes=["same_value_substitute"],
        best_relation_code="same_value_substitute",
        best_relation_status="limited",
        best_confidence_level="medium",
        independent_evidence_family_count=4,
        f1_f4_evidence_count=2,
        market_pressure_clarity="strong",
        limitation_count=0,
        reason_code="verified_decision_topic",
        result_hash="limited-medium",
    )

    assert selection_module._meaningfully_stronger(
        passed_high,
        limited_medium,
        "value_route",
    )
    source = inspect.getsource(selection_module)
    assert "weighted_score" not in source
    assert "total_score" not in source


def test_all_required_non_selection_reason_codes_are_explicit() -> None:
    assert {
        "ineligible_status",
        "review_required",
        "question_unavailable",
        "confidence_insufficient",
        "no_verified_decision_topic",
        "topic_already_covered",
        "weaker_duplicate_pressure",
        "specialized_question_only",
    }.issubset(selection_module._REASON_CN)
    assert "rank>3" not in " ".join(selection_module._REASON_CN.values())


def test_limited_candidate_requires_explicit_key_question_eligibility() -> None:
    relation_bundle = _p3_limited_relation_bundle()
    unavailable = _select(relation_bundle)
    assert unavailable.selected_count == 0
    assert _decision(unavailable, "TV000002").non_selection_reason_code == (
        "question_unavailable"
    )

    pair = relation_bundle.pairs[0]
    key_enabled = pair.model_copy(
        update={
            "question_eligibility": _questions_with_availability(
                pair,
                {
                    "key_competitor_selection": "eligible",
                    "value_substitution": "eligible",
                },
            )
        }
    )
    enabled_bundle = _single_pair_bundle(
        relation_bundle,
        key_enabled,
        suffix="key-enabled",
    )
    selected = _select(enabled_bundle)
    assert selected.selected_count == 1
    assert selected.selections[0].candidate_sku_code == "TV000002"
    assert selected.selections[0].primary_decision_topic == "value_route"
    assert selected.selections[0].confidence_level == "medium"


def test_confidence_no_topic_and_specialized_only_reasons_are_emitted() -> None:
    relation_bundle = _evaluate(_category_bundle())[4]
    direct = next(
        row for row in relation_bundle.pairs if row.candidate.sku_code == "TV000002"
    )
    low_relations = [
        row.model_copy(update={"confidence_level": "low"})
        if row.status in {"passed", "limited"}
        else row
        for row in direct.relation_assessments
    ]
    low_pair = direct.model_copy(
        update={
            "relation_assessments": low_relations,
            "overall_confidence_level": "low",
        }
    )
    low_result = _select(
        _single_pair_bundle(relation_bundle, low_pair, suffix="low-confidence")
    )
    assert _decision(low_result, "TV000002").non_selection_reason_code == (
        "confidence_insufficient"
    )

    unavailable_topics = {
        "purchase_choice": "unavailable",
        "price_volume_pressure": "unavailable",
        "price_ladder_defense": "unavailable",
        "same_brand_portfolio_role": "unavailable",
        "scenario_solution": "unavailable",
        "value_substitution": "unavailable",
        "configuration_follow": "unavailable",
    }
    no_topic_pair = direct.model_copy(
        update={
            "question_eligibility": _questions_with_availability(
                direct,
                unavailable_topics,
            )
        }
    )
    no_topic = _select(
        _single_pair_bundle(relation_bundle, no_topic_pair, suffix="no-topic")
    )
    assert _decision(no_topic, "TV000002").non_selection_reason_code == (
        "no_verified_decision_topic"
    )

    specialized_updates = dict(unavailable_topics)
    specialized_updates["configuration_follow"] = "eligible"
    specialized_pair = direct.model_copy(
        update={
            "question_eligibility": _questions_with_availability(
                direct,
                specialized_updates,
            )
        }
    )
    specialized = _select(
        _single_pair_bundle(relation_bundle, specialized_pair, suffix="specialized")
    )
    assert _decision(specialized, "TV000002").non_selection_reason_code == (
        "specialized_question_only"
    )


def test_config_and_bundle_reject_invalid_topic_and_rank_contracts() -> None:
    payload = _config().model_dump(mode="python")
    payload["decision_topic_order"] = payload["decision_topic_order"][:-1]
    with pytest.raises(ValidationError, match="all four topics"):
        KeyCompetitorSelectionConfig.model_validate(payload)

    result = _select(_evaluate(_category_bundle())[4])
    invalid = result.model_dump(mode="python")
    invalid["selections"][0]["selection_rank"] = 2
    with pytest.raises(ValidationError, match="contiguous"):
        KeyCompetitorSelectionBundle.model_validate(invalid)


def test_candidate_conservation_tv_ac_hash_scope_schema_and_no_db_llm() -> None:
    relation_bundle = _evaluate(_category_bundle())[4]
    result = _select(relation_bundle)
    assert result.candidate_count == relation_bundle.candidate_count
    assert [row.candidate.sku_code for row in result.pair_decisions] == [
        row.candidate.sku_code for row in relation_bundle.pairs
    ]

    reordered = relation_bundle.model_copy(
        update={"pairs": list(reversed(relation_bundle.pairs))}
    )
    assert _select(reordered).result_hash == result.result_hash

    changed = _select(relation_bundle, _config(version="key-selection-test-v2"))
    assert changed.input_fingerprint != result.input_fingerprint
    assert changed.result_hash != result.result_hash

    changed_bundle = _category_bundle()
    changed_bundle.modules["M07"].records_by_sku["TV000002"][0].facts[
        "sales_volume_total"
    ] = Decimal("1500")
    fact_changed = _select(_evaluate(changed_bundle)[4])
    assert fact_changed.input_fingerprint != result.input_fingerprint
    assert fact_changed.result_hash != result.result_hash

    target = _default_spec("AC", 1)
    candidate = _default_spec("AC", 2)
    candidate.update(
        {
            "task_primary": target["task_primary"],
            "battlefield_primary": target["battlefield_primary"],
            "purchase_reasons": target["purchase_reasons"],
            "claim_values": target["claim_values"],
        }
    )
    ac_relations = _evaluate(
        _category_bundle("AC", [target, candidate]),
        target="AC000001",
    )[4]
    ac = _select(ac_relations, _config("AC"))
    assert ac.product_category == "AC"
    assert ac.candidate_count == 1

    with pytest.raises(KeyCompetitorSelectionError, match="category"):
        _select(relation_bundle, _config("AC"))

    with pytest.raises(ValidationError, match="candidate count"):
        payload = result.model_dump(mode="python")
        payload["candidate_count"] += 1
        KeyCompetitorSelectionBundle.model_validate(payload)

    source = inspect.getsource(selection_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
    assert "top 3" not in source
    assert "topn" not in source
