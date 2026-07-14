from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_materializer as materializer_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer import (
    CompetitorProfileMaterializationError,
    CompetitorProfileMaterializer,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    CompetitorProfileBatchMaterializationResult,
    CompetitorProfileMaterializationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorPairDraft,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)
from tests.core3_real_data.test_competitor_profile_key_competitor_selection import (
    _config as _key_config,
)
from tests.core3_real_data.test_competitor_profile_price_volume_pressure import (
    _config as _price_config,
)
from tests.core3_real_data.test_competitor_profile_purchase_pool import (
    _config as _pool_config,
)
from tests.core3_real_data.test_competitor_profile_relation_evaluation import (
    _align_value_layers,
    _config as _relation_config,
)
from tests.core3_real_data.test_competitor_profile_value_substitution import (
    _config as _value_config,
)


def _config(
    category: str = "TV",
    *,
    version: str = "materializer-test-v1",
) -> CompetitorProfileMaterializationConfig:
    return CompetitorProfileMaterializationConfig(
        config_version=version,
        product_category=category,
        recall=CandidateRecallConfig(),
        eligibility=CandidateEligibilityConfig(),
        purchase_pool=_pool_config(category),
        value_substitution=_value_config(category),
        price_volume=_price_config(category),
        relation=_relation_config(category),
        key_selection=_key_config(category),
    )


def _materialize(category_bundle, target: str = "TV000001", config=None):
    return CompetitorProfileMaterializer().materialize(
        category_bundle,
        _target_bundle(category_bundle, target),
        config or _config(category_bundle.serving_scope.product_category),
    )


def _aligned_bundle(candidate_codes: tuple[str, ...]):
    bundle = _category_bundle()
    sku_codes = ("TV000001", *candidate_codes)
    _align_value_layers(bundle, sku_codes, code="clear-picture")
    for sku_code in sku_codes:
        bundle.modules["M12D"].records_by_sku[sku_code][0].facts[
            "core_payment_anchors_json"
        ] = [{"anchor_code": "clear-picture"}]
    return bundle


def test_single_sku_materializes_complete_profile_pairs_relations_and_selection() -> (
    None
):
    result = _materialize(_category_bundle())
    draft = result.draft

    assert result.target_sku_code == "TV000001"
    assert draft.profile.analysis_state == "partial"
    assert draft.profile.conclusion_state == "available"
    assert draft.profile.target_market_summary["price_wavg"] == Decimal("5000")
    assert len(draft.pairs) == 4
    assert len(draft.selections) == 1
    assert sum(row.selected for row in draft.pairs) == 1
    assert next(row for row in draft.pairs if row.selected).candidate.sku_code == (
        draft.selections[0].candidate_sku_code
    )
    assert all(len(row.relation_assessments) == 7 for row in draft.pairs)
    assert all(len(row.evidence_family_assessments) == 5 for row in draft.pairs)
    assert all(len(row.question_eligibility) == 8 for row in draft.pairs)
    assert set(result.stage_result_hashes) == {
        "candidate_pipeline",
        "pair_feature",
        "purchase_pool",
        "value_substitution",
        "price_volume_pressure",
        "relation_evaluation",
        "key_selection",
        "profile",
    }


@pytest.mark.parametrize(
    ("candidate_codes", "expected_selected"),
    [
        (("TV000002",), 1),
        (("TV000002", "TV000003"), 2),
        (("TV000002", "TV000003", "TV000004"), 3),
    ],
)
def test_materializer_assembles_real_zero_to_three_selection_labels(
    candidate_codes: tuple[str, ...],
    expected_selected: int,
) -> None:
    result = _materialize(_aligned_bundle(candidate_codes))

    assert len(result.draft.selections) == expected_selected
    assert [row.selection_rank for row in result.draft.selections] == list(
        range(1, expected_selected + 1)
    )
    assert len(result.draft.pairs) == 4


def test_reference_and_review_candidates_are_preserved_with_explicit_reasons() -> None:
    result = _materialize(_category_bundle())
    by_sku = {row.candidate.sku_code: row for row in result.draft.pairs}

    assert by_sku["TV000003"].candidate_status == "review_required"
    assert by_sku["TV000003"].review_required is True
    assert by_sku["TV000003"].competitor_member is False
    assert by_sku["TV000003"].non_selection_reason_code == "review_required"
    assert by_sku["TV000006"].candidate_status == "reference_only"
    assert by_sku["TV000006"].reference_member is True
    assert by_sku["TV000006"].competitor_member is False
    assert by_sku["TV000006"].non_selection_reason_code == "ineligible_status"


def test_pair_schema_accepts_noncompetitor_recalled_and_blocked_states() -> None:
    result = _materialize(_category_bundle())
    reference = next(
        row for row in result.draft.pairs if row.candidate.sku_code == "TV000006"
    )
    recalled_payload = reference.model_dump(mode="python")
    recalled_payload.update(
        {
            "candidate_status": "recalled_only",
            "reference_member": False,
            "reference_purposes": [],
        }
    )
    recalled = CompetitorPairDraft.model_validate(recalled_payload)
    assert recalled.competitor_member is False
    assert recalled.review_required is False

    blocked_payload = dict(recalled_payload)
    blocked_payload.update(
        {
            "candidate_status": "blocked",
            "review_required": True,
            "review_status": "review_required",
        }
    )
    blocked = CompetitorPairDraft.model_validate(blocked_payload)
    assert blocked.competitor_member is False
    assert blocked.review_required is True


def test_profile_business_conclusions_keep_evidence_and_noncausal_boundaries() -> None:
    result = _materialize(_aligned_bundle(("TV000002", "TV000004")))
    profile = result.draft.profile

    assert profile.substitutable_values
    assert all(row["causal_wtp_claim"] is False for row in profile.substitutable_values)
    assert profile.price_scale_pressures
    assert all(row["causal_claim"] is False for row in profile.price_scale_pressures)
    assert all(
        row["price_change_sales_increment_claim"] is False
        for row in profile.price_scale_pressures
    )
    assert len(profile.qa_index) == 8
    assert profile.evidence_refs
    assert profile.source_lineage
    formal_candidates = {
        pair.candidate.sku_code
        for pair in result.draft.pairs
        if any(
            relation.status in {"passed", "limited"}
            for relation in pair.relation_assessments
        )
    }
    for section in (
        profile.competitive_advantages,
        profile.substitutable_values,
        profile.price_scale_pressures,
        profile.same_brand_findings,
        profile.configuration_decisions,
    ):
        assert {row["candidate_sku_code"] for row in section}.issubset(
            formal_candidates
        )


def test_ready_no_priority_partial_and_blocked_states_remain_distinct() -> None:
    unrelated = [_default_spec("TV", 1), _default_spec("TV", 2)]
    unrelated[0].update(
        {
            "price": Decimal("5000"),
            "task_primary": "cinema",
            "battlefield_primary": "picture",
        }
    )
    unrelated[1].update(
        {
            "price": Decimal("5100"),
            "task_primary": "gaming",
            "battlefield_primary": "gaming",
        }
    )
    no_priority = _materialize(_category_bundle(specs=unrelated)).draft.profile
    assert no_priority.analysis_state == "ready"
    assert no_priority.conclusion_state == "no_priority_competitor"
    assert no_priority.no_conclusion_reason["reason_code"] == ("no_priority_competitor")

    partial_specs = [_default_spec("TV", 1), _default_spec("TV", 2)]
    partial_specs[0]["missing_modules"] = {"M05C"}
    partial = _materialize(_category_bundle(specs=partial_specs)).draft.profile
    assert partial.analysis_state == "partial"

    blocked_specs = [_default_spec("TV", 1), _default_spec("TV", 2)]
    blocked_specs[0]["missing_modules"] = {"M03B"}
    blocked = _materialize(_category_bundle(specs=blocked_specs)).draft.profile
    assert blocked.analysis_state == "blocked"
    assert blocked.conclusion_state == "insufficient_evidence"
    assert blocked.review_required is True


def test_batch_isolates_one_bad_target_and_is_order_independent() -> None:
    category = _category_bundle()
    good = _target_bundle(category, "TV000001")
    other = _target_bundle(category, "TV000002")
    ac_category = _category_bundle(
        "AC",
        [_default_spec("AC", 1), _default_spec("AC", 2)],
    )
    bad = _target_bundle(ac_category, "AC000001")
    service = CompetitorProfileMaterializer()

    first = service.materialize_batch(category, [other, bad, good], _config())
    second = service.materialize_batch(category, [good, other, bad], _config())

    assert first.requested_count == 3
    assert first.succeeded_count == 2
    assert first.failed_count == 1
    assert [row.target_sku_code for row in first.statuses] == [
        "AC000001",
        "TV000001",
        "TV000002",
    ]
    failed = first.statuses[0]
    assert failed.error_code == "category_scope_mismatch"
    assert "AC" not in failed.error_message
    assert first.result_hash == second.result_hash

    resumed = service.materialize_batch(category, [other, good], _config())
    assert resumed.succeeded_count == 2
    assert resumed.failed_count == 0


def test_batch_rejects_duplicate_targets_before_generation() -> None:
    category = _category_bundle()
    target = _target_bundle(category, "TV000001")

    with pytest.raises(CompetitorProfileMaterializationError, match="unique"):
        CompetitorProfileMaterializer().materialize_batch(
            category,
            [target, target],
            _config(),
        )


def test_tv_ac_scope_hash_schema_and_no_db_llm() -> None:
    tv = _materialize(_category_bundle())
    reordered = _category_bundle(reorder_semantic_values=True)
    assert _materialize(reordered).result_hash == tv.result_hash

    changed = _materialize(
        _category_bundle(),
        config=_config(version="materializer-test-v2"),
    )
    assert changed.input_fingerprint != tv.input_fingerprint
    assert changed.result_hash != tv.result_hash

    facts = _category_bundle()
    facts.modules["M07"].records_by_sku["TV000002"][0].facts["sales_volume_total"] = (
        Decimal("1500")
    )
    fact_changed = _materialize(facts)
    assert fact_changed.result_hash != tv.result_hash

    ac_specs = [_default_spec("AC", 1), _default_spec("AC", 2)]
    ac = _materialize(
        _category_bundle("AC", ac_specs),
        target="AC000001",
        config=_config("AC"),
    )
    assert ac.product_category == "AC"

    with pytest.raises(ValidationError, match="counts"):
        batch = CompetitorProfileMaterializer().materialize_batch(
            _category_bundle(),
            [_target_bundle(_category_bundle(), "TV000001")],
            _config(),
        )
        payload = batch.model_dump(mode="python")
        payload["failed_count"] += 1
        CompetitorProfileBatchMaterializationResult.model_validate(payload)

    source = inspect.getsource(materializer_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
    assert '"causal_wtp_claim": true' not in source
