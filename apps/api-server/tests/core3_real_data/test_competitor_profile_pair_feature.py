from __future__ import annotations

import inspect
from dataclasses import replace
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_pair_feature as pair_feature_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
    PairFeatureError,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairAlignedFeature,
    PairFeatureBundle,
    PairProductFormFacts,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)


def _pipeline(bundle: CompetitorProfileCategoryInputBundle, target: str = "TV000001"):
    return CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, target),
    )


def _build(bundle: CompetitorProfileCategoryInputBundle, target: str = "TV000001"):
    return PairFeatureBuilder().build(_pipeline(bundle, target))


def _pair(bundle: PairFeatureBundle, sku_code: str):
    return next(row for row in bundle.pairs if row.candidate.sku_code == sku_code)


def _feature(pair, group: str, code: str):
    return next(
        row
        for row in pair.aligned_features
        if row.feature_group == group and row.feature_code == code
    )


def _add_param_record(
    bundle: CompetitorProfileCategoryInputBundle,
    sku_code: str,
    *,
    value: str,
) -> CompetitorProfileCategoryInputBundle:
    payload = bundle.model_dump(mode="python")
    rows = payload["modules"]["M03B"]["records_by_sku"][sku_code]
    row = dict(rows[0])
    row["record_id"] = f"m03b-{sku_code}-refresh"
    row["result_hash"] = f"m03b-{sku_code}-refresh-hash"
    row["facts"] = {
        "sku_code": sku_code,
        "param_code": "refresh_rate",
        "normalized_value": value,
    }
    rows.append(row)
    rows.sort(key=lambda item: (item["source_batch_id"], item["record_id"]))
    payload["modules"]["M03B"]["record_count"] += 1
    return CompetitorProfileCategoryInputBundle.model_validate(payload)


def test_pair_bundle_conserves_candidates_and_stays_conclusion_free() -> None:
    result = _build(_category_bundle())

    assert result.candidate_count == 4
    assert [row.candidate.sku_code for row in result.pairs] == [
        "TV000002",
        "TV000003",
        "TV000004",
        "TV000006",
    ]
    assert all(row.target == result.target for row in result.pairs)
    assert all(row.competitor_member is False for row in result.pairs)
    assert all(row.relation_status == "not_evaluated" for row in result.pairs)
    assert all(row.business_conclusion_allowed is False for row in result.pairs)
    assert all(row.causal_claim is False for row in result.pairs)
    assert all(len(row.module_availability) == 10 for row in result.pairs)
    assert all(
        feature.factual_only
        and not feature.advantage_claim
        and not feature.relation_claim
        for row in result.pairs
        for feature in row.aligned_features
    )


def test_market_comparison_uses_descriptive_price_and_weekly_volume_only() -> None:
    direct = _pair(_build(_category_bundle()), "TV000002")
    market = direct.market_comparison

    assert market.comparability_status == "comparable"
    assert market.target_weighted_price == Decimal("5000")
    assert market.candidate_weighted_price == Decimal("5100")
    assert market.price_gap == Decimal("100.0000")
    assert market.price_gap_pct == Decimal("0.020000")
    assert market.target_avg_weekly_volume == Decimal("100.000000")
    assert market.candidate_avg_weekly_volume == Decimal("120.000000")
    assert market.weekly_volume_gap == Decimal("20.000000")
    assert market.weekly_volume_ratio == Decimal("1.200000")
    assert market.target_total_sales == Decimal("1000")
    assert market.candidate_total_sales == Decimal("1200")
    assert market.common_week_count is None
    assert market.common_platform_count is None
    assert market.causal_claim is False


def test_zero_target_price_and_volume_keep_ratios_unknown_instead_of_zero() -> None:
    target = _default_spec("TV", 1)
    target.update(
        {
            "price": Decimal("0"),
            "weekly_volume": Decimal("0"),
            "market_pool": "zero-market",
        }
    )
    candidate = _default_spec("TV", 2)
    candidate.update(
        {
            "price": Decimal("5000"),
            "weekly_volume": Decimal("100"),
            "market_pool": "zero-market",
        }
    )
    market = (
        _build(_category_bundle(specs=[target, candidate])).pairs[0].market_comparison
    )

    assert market.target_weighted_price == Decimal("0")
    assert market.target_avg_weekly_volume == Decimal("0.000000")
    assert market.price_gap == Decimal("5000.0000")
    assert market.weekly_volume_gap == Decimal("100.000000")
    assert market.price_gap_pct is None
    assert market.weekly_volume_ratio is None
    assert set(market.unknown_reasons) >= {
        "target_avg_weekly_volume_zero_for_ratio",
        "target_weighted_price_zero_for_ratio",
    }


def test_sparse_modules_are_typed_unknown_and_do_not_create_false_or_zero_features() -> (
    None
):
    sparse = _pair(_build(_category_bundle()), "TV000006")
    availability = {row.module_code: row for row in sparse.module_availability}

    assert availability["M12D"].candidate_availability == "unknown"
    assert availability["M12D"].candidate_record_count == 0
    assert availability["M12D"].candidate_missing_reason_code == (
        "candidate_m12d_not_covered_by_locked_authority"
    )
    assert "candidate_m12d_unknown" in sparse.unknown_reason_codes
    reason = _feature(sparse, "purchase_reason", "clear-picture")
    assert reason.comparison_status == "target_only"
    assert reason.candidate_values == []
    assert reason.common_values == []


def test_all_nine_feature_groups_are_saved_with_exact_evidence() -> None:
    bundle = _category_bundle()
    for sku_code in ("TV000001", "TV000002"):
        bundle.modules["M04C"].records_by_sku[sku_code][0].facts.update(
            {
                "claim_codes": ["claim-picture", "claim-picture"],
                "fact_claim_codes": ["claim-picture"],
            }
        )
        bundle.modules["M05C"].records_by_sku[sku_code][0].facts.update(
            {"supported_claim_codes": ["claim-picture", "claim-picture"]}
        )
    direct = _pair(_build(bundle), "TV000002")
    groups = {row.feature_group for row in direct.aligned_features}

    assert groups == {
        "audience",
        "battlefield",
        "claim_expression",
        "claim_value",
        "market_position",
        "parameter",
        "purchase_reason",
        "task",
        "user_realization",
    }
    claim = _feature(direct, "claim_expression", "claim-picture")
    assert claim.comparison_status == "shared"
    assert claim.common_values == ["expressed", "fact_supported"]
    assert claim.target_evidence_refs[0].module_code == "M04C"
    assert claim.candidate_evidence_refs[0].module_code == "M04C"


def test_parameter_alignment_handles_same_different_and_multiple_records() -> None:
    bundle = _add_param_record(_category_bundle(), "TV000001", value="144hz")
    bundle = _add_param_record(bundle, "TV000002", value="120hz")
    direct = _pair(_build(bundle), "TV000002")

    shared = _feature(direct, "parameter", "ac_product_form")
    different = _feature(direct, "parameter", "refresh_rate")
    assert shared.comparison_status == "shared"
    assert shared.common_values == ["wall_mounted"]
    assert different.comparison_status == "different"
    assert different.target_values == ["144hz"]
    assert different.candidate_values == ["120hz"]
    assert len(different.target_evidence_refs) == 1
    assert len(different.candidate_evidence_refs) == 1


def test_purchase_reason_and_claim_role_values_are_deduped_without_losing_roles() -> (
    None
):
    bundle = _category_bundle()
    target_reason = bundle.modules["M12D"].records_by_sku["TV000001"][0]
    target_reason.facts["core_payment_anchors_json"] += [
        {"anchor_code": "clear-picture"},
        {"anchor_code": "clear-picture"},
    ]
    candidate_reason = bundle.modules["M12D"].records_by_sku["TV000002"][0]
    candidate_reason.facts["established_anchors_json"] = [
        {"anchor_code": "clear-picture"},
        {"anchor_code": "clear-picture"},
    ]
    direct = _pair(_build(bundle), "TV000002")

    reason = _feature(direct, "purchase_reason", "clear-picture")
    assert reason.target_values == ["core_payment_anchor"]
    assert reason.candidate_values == ["core_payment_anchor", "established_anchor"]
    assert reason.common_values == ["core_payment_anchor"]
    assert reason.comparison_status == "shared"
    claim = _feature(direct, "claim_value", "bright-room-clear")
    assert claim.common_values == ["role:value_bundle_claim"]


def test_tv_and_ac_product_form_fields_are_isolated() -> None:
    tv = _pair(_build(_category_bundle()), "TV000002").product_form_facts
    assert tv.product_category == "TV"
    assert tv.target_screen_size_inch == Decimal("65")
    assert tv.candidate_screen_size_inch == Decimal("65")
    assert tv.target_ac_form is None
    assert tv.target_ac_capacity is None

    target = _default_spec("AC", 1)
    target.update({"market_pool": "ac-1.5p", "task_primary": "sleep"})
    candidate = _default_spec("AC", 2)
    candidate.update({"market_pool": "ac-1.5p", "task_primary": "sleep"})
    ac_result = (
        _build(
            _category_bundle("AC", [target, candidate]),
            "AC000001",
        )
        .pairs[0]
        .product_form_facts
    )
    assert ac_result.product_category == "AC"
    assert ac_result.target_screen_size_inch is None
    assert ac_result.candidate_screen_size_inch is None
    assert ac_result.target_ac_form == "wall_mounted"
    assert ac_result.candidate_ac_form == "wall_mounted"
    assert ac_result.target_ac_capacity == "1.5p"
    assert ac_result.candidate_ac_capacity == "1.5p"


def test_review_and_lineage_conflict_flags_are_preserved_without_pair_conclusion() -> (
    None
):
    bundle = _category_bundle()
    bundle.modules["M12D"].records_by_sku["TV000002"][0].facts["review_required"] = True
    bundle.modules["M03B"].records_by_sku["TV000002"][0].facts["conflict_count"] = 1
    direct = _pair(_build(bundle), "TV000002")

    assert direct.candidate_status == "review_required"
    assert "candidate_m12d_review_required" in direct.review_reason_codes
    assert "candidate_m03b_conflict_count_positive" in (
        direct.lineage_conflict_reason_codes
    )
    assert direct.relation_status == "not_evaluated"
    assert direct.business_conclusion_allowed is False


def test_input_order_is_stable_and_protected_feature_changes_update_pair_hash() -> None:
    first = _build(_category_bundle())
    reordered = _build(_category_bundle(reorder_semantic_values=True))
    assert reordered.result_hash == first.result_hash
    assert [row.result_hash for row in reordered.pairs] == [
        row.result_hash for row in first.pairs
    ]

    changed_bundle = _category_bundle()
    changed_bundle.modules["M04C"].records_by_sku["TV000002"][0].facts[
        "claim_codes"
    ] = ["new-claim-expression"]
    changed_pipeline = _pipeline(changed_bundle)
    assert (
        changed_pipeline.receipt.result_hash
        == _pipeline(_category_bundle()).receipt.result_hash
    )
    changed = PairFeatureBuilder().build(changed_pipeline)
    assert changed.result_hash != first.result_hash
    assert (
        _feature(
            _pair(changed, "TV000002"),
            "claim_expression",
            "new-claim-expression",
        ).comparison_status
        == "candidate_only"
    )


def test_empty_manifest_scope_checks_and_schema_contradictions_fail_closed() -> None:
    target = _default_spec("TV", 1)
    empty_bundle = _category_bundle(specs=[target])
    empty_pipeline = _pipeline(empty_bundle)
    empty = PairFeatureBuilder().build(empty_pipeline)
    assert empty.candidate_count == 0
    assert empty.pairs == []

    bad_receipt = empty_pipeline.receipt.model_copy(
        update={"target_sku_code": "TV999999"}
    )
    with pytest.raises(PairFeatureError, match="target conflicts"):
        PairFeatureBuilder().build(replace(empty_pipeline, receipt=bad_receipt))

    tv_form = _pair(_build(_category_bundle()), "TV000002").product_form_facts
    with pytest.raises(ValidationError, match="cannot contain AC fields"):
        PairProductFormFacts.model_validate(
            {**tv_form.model_dump(mode="python"), "target_ac_form": "wall_mounted"}
        )

    direct = _pair(_build(_category_bundle()), "TV000002")
    alignment = direct.aligned_features[0]
    with pytest.raises(ValidationError, match="pair intersection"):
        PairAlignedFeature.model_validate(
            {**alignment.model_dump(mode="python"), "common_values": ["invented"]}
        )

    pair_payload = direct.model_dump(mode="python")
    pair_payload["business_conclusion_allowed"] = True
    with pytest.raises(ValidationError):
        direct.__class__.model_validate(pair_payload)

    bundle_result = _build(_category_bundle())
    bundle_payload = bundle_result.model_dump(mode="python")
    bundle_payload["candidate_count"] += 1
    with pytest.raises(ValidationError, match="candidate count"):
        PairFeatureBundle.model_validate(bundle_payload)


def test_pair_builder_has_no_database_or_external_llm_dependency() -> None:
    source = inspect.getsource(pair_feature_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
