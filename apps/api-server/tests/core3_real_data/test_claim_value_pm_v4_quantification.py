from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketCellRow,
    MarketImpliedWtp,
    QuantificationResult,
    SellpointValueV4Context,
    SourceAuthority,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    _battlefield_sample_weight,
    build_counterfactual_assessments,
    quantify_sellpoint_value,
)
from tests.core3_real_data.test_claim_value_pm_v4_counterfactual import (
    BATTLEFIELD,
    _base_context,
    _candidate,
    _picture_link,
)


def _synthetic_context(
    *,
    crossings: tuple[float, ...] = (0.08, 0.10),
    families: tuple[str, ...] = ("family-a", "family-b"),
    roles: tuple[str, ...] | None = None,
    tiers: tuple[str, ...] | None = None,
    lineage_conflict: bool = False,
    unstable_leave_one_out: bool = False,
    promotion_suspect: bool = False,
    gap_mode: str = "full",
    reverse_direction: bool = False,
    single_week: bool = False,
) -> SellpointValueV4Context:
    context = _base_context(lineage_conflict=lineage_conflict)
    roles = roles or tuple("base_value" for _ in crossings)
    tiers = tiers or tuple("base" for _ in crossings)
    candidates = [
        _candidate(
            context,
            sku_code=f"BASE-{index + 1}",
            role=roles[index],
            provenance="M14",
            tier=tiers[index],
            brightness=1300 + index * 100,
            zones=264 + index * 20,
        )
        for index in range(len(crossings))
    ]
    if unstable_leave_one_out:
        gaps = [-0.04 + (0.10 / 14) * index for index in range(15)] + [0.10]
    elif gap_mode == "near":
        gaps = [0.01 + (0.09 / 15) * index for index in range(16)]
    elif gap_mode == "hole":
        gaps = [-0.20] * 8 + [0.20] * 8
    else:
        gaps = [-0.04 + (0.18 / 15) * index for index in range(16)]
    if single_week:
        gaps = [0.0]
    cells: list[MarketCellRow] = []
    for week, gap in enumerate(gaps, start=1):
        for platform in ("jd", "tmall"):
            candidate_price = 4800 + week * 30 if gap_mode == "near" else 5000
            target_price = candidate_price * (1 + gap)
            target_sales = 500.0
            cells.append(
                MarketCellRow(
                    sku_code=context.target.sku_code,
                    battlefield_code=BATTLEFIELD,
                    period_week_index=week,
                    platform_type=platform,
                    avg_price=target_price,
                    sales_volume=target_sales,
                    sales_amount=target_price * target_sales,
                    series_name="target-family",
                    price_check_status="ok",
                    promotion_suspect=promotion_suspect,
                    inventory_status="unavailable",
                )
            )
            for index, candidate in enumerate(candidates):
                share = (
                    0.5 + 0.8 * (gap - crossings[index])
                    if reverse_direction
                    else 0.5 + 0.8 * (crossings[index] - gap)
                )
                share = min(max(share, 0.08), 0.92)
                candidate_sales = target_sales * (1 - share) / share
                cells.append(
                    MarketCellRow(
                        sku_code=candidate.identity.sku_code,
                        battlefield_code=BATTLEFIELD,
                        period_week_index=week,
                        platform_type=platform,
                        avg_price=candidate_price,
                        sales_volume=candidate_sales,
                        sales_amount=candidate_price * candidate_sales,
                        series_name=families[index],
                        price_check_status="ok",
                        promotion_suspect=promotion_suspect,
                        inventory_status="unavailable",
                    )
                )
    payload = context.model_dump(mode="python")
    payload["candidate_snapshots"] = [
        item.model_dump(mode="python") for item in candidates
    ]
    payload["market_cells"] = [item.model_dump(mode="python") for item in cells]
    payload.pop("input_hash")
    return SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )


def _quantify(context: SellpointValueV4Context) -> QuantificationResult:
    link = _picture_link(context)
    assessments = build_counterfactual_assessments(context, link)
    return quantify_sellpoint_value(context, link, assessments)


def test_two_independent_families_recover_bounded_400_500_wtp() -> None:
    context = _synthetic_context()

    first = _quantify(context)
    second = _quantify(context)

    assert first == second
    assert first.level == "Q5_MARKET_IMPLIED_WTP"
    assert first.value_status == "established"
    assert first.product_role == "core_differentiated_value"
    assert first.wtp.status == "available"
    assert first.wtp.method == "matched_equal_choice_price_gap"
    assert (
        first.wtp.method_config_version == "sellpoint_value_pm_v4_matched_wtp_config_v2"
    )
    assert first.wtp.pair_count == 2
    assert first.wtp.model_family_count == 2
    assert first.wtp.estimate_low is not None
    assert first.wtp.estimate_high is not None
    assert first.wtp.estimate_low <= 400 <= first.wtp.estimate_high
    assert first.wtp.estimate_low <= 500 <= first.wtp.estimate_high
    assert first.wtp.causal_claim is False
    assert first.wtp.psychological_max_price is False
    bootstrap = first.wtp.sensitivity_summary["cluster_week_bootstrap"]
    assert set(bootstrap) == {"BASE-1", "BASE-2"}
    assert all(item["iterations"] == 200 for item in bootstrap.values())
    assert all(item["stable"] is True for item in bootstrap.values())
    assert first.wtp.sensitivity_summary["weighted_median_center"] == 400.0
    assert first.choice_association is not None
    assert first.choice_association.method == "pair_curve_same_price"
    assert first.whole_product_price_acceptance is not None
    assert (
        first.whole_product_price_acceptance["attribution_scope"]
        == "whole_product_only"
    )
    serialized = json.dumps(first.model_dump(mode="json"), ensure_ascii=False)
    for member in _picture_link(context).bundle.members:
        assert f"{member.capability_code}_wtp" not in serialized


def test_market_cell_truncation_blocks_amount_but_keeps_descriptive_choice() -> None:
    context = _synthetic_context()
    authorities = [
        *context.authority_manifest,
        SourceAuthority(
            module_code="M07",
            table_name="core3_clean_market_weekly",
            authority_mode="configured_rule",
            rule_version="v1",
            selected_batch_ids=["synthetic"],
            row_count=len(context.market_cells),
            availability="present",
            usability="limited",
            source_hash="synthetic-m07",
            selected_reason="synthetic truncation fixture",
            warnings=["market_cells_truncated"],
        ),
    ]
    context = context.model_copy(update={"authority_manifest": authorities})

    result = _quantify(context)

    assert result.choice_association is not None
    assert result.choice_association.status == "available"
    assert result.wtp.status == "blocked"
    assert result.wtp.estimate_low is None
    assert result.wtp.exclusion_reasons == ["market_cells_truncated"]


def test_battlefield_weight_is_explanatory_and_uses_conservative_pair_value() -> None:
    target = MarketCellRow(
        sku_code="TARGET",
        battlefield_code=BATTLEFIELD,
        period_week_index=1,
        platform_type="jd",
        battlefield_allocation_weight=0.8,
        price_check_status="ok",
        promotion_suspect=False,
        inventory_status="unavailable",
    )
    candidate = target.model_copy(
        update={"sku_code": "CANDIDATE", "battlefield_allocation_weight": 0.6}
    )

    weight, complete = _battlefield_sample_weight(target, candidate)
    missing_weight, missing_complete = _battlefield_sample_weight(
        target.model_copy(update={"battlefield_allocation_weight": None}),
        candidate.model_copy(update={"battlefield_allocation_weight": None}),
    )

    assert (weight, complete) == (0.6, True)
    assert (missing_weight, missing_complete) == (1.0, False)


def test_same_family_pairs_do_not_satisfy_q5_family_gate() -> None:
    result = _quantify(_synthetic_context(families=("same-family", "same-family")))

    assert result.level == "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE"
    assert result.wtp.status == "insufficient"
    assert result.wtp.estimate_low is None
    assert "model_family_count_below_2" in result.wtp.exclusion_reasons


def test_single_pair_never_becomes_market_implied_wtp() -> None:
    result = _quantify(_synthetic_context(crossings=(0.08,), families=("family-a",)))

    assert result.level == "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE"
    assert result.wtp.status == "insufficient"
    assert result.wtp.pair_count == 1
    assert "independent_a_pair_count_below_2" in result.wtp.exclusion_reasons


def test_same_value_only_can_show_choice_but_not_incremental_wtp() -> None:
    result = _quantify(
        _synthetic_context(
            crossings=(0.08,),
            families=("family-a",),
            roles=("same_value",),
            tiers=("premium",),
        )
    )

    assert result.level == "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE"
    assert result.choice_association is not None
    assert result.choice_association.status == "available"
    assert result.wtp.estimate_low is None
    assert "same_value_only" in result.wtp.exclusion_reasons


def test_leave_one_week_out_failure_makes_amount_unstable_and_null() -> None:
    result = _quantify(_synthetic_context(unstable_leave_one_out=True))

    assert result.level == "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE"
    assert result.wtp.status == "unstable"
    assert result.wtp.estimate_low is None
    assert result.wtp.estimate_high is None
    assert "leave_one_week_out_stability_failed" in result.wtp.exclusion_reasons
    assert any(
        not item["stable"]
        for item in result.wtp.sensitivity_summary["leave_one_week_out"].values()
    )


def test_bootstrap_failure_blocks_amount_even_when_other_gates_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.core3_real_data.analyst import claim_value_pm_v4_service

    monkeypatch.setattr(
        claim_value_pm_v4_service,
        "_cluster_week_bootstrap",
        lambda _curve, *, seed_material: {
            "stable": False,
            "seed_hash": seed_material,
            "iterations": 200,
            "successful_crossing_count": 100,
            "success_rate": 0.5,
            "crossing_ratio_p10": 0.01,
            "crossing_ratio_p90": 0.2,
            "crossing_span": 0.19,
        },
    )

    result = _quantify(_synthetic_context())

    assert result.wtp.status == "unstable"
    assert result.wtp.estimate_low is None
    assert result.wtp.estimate_high is None
    assert result.wtp.exclusion_reasons == ["cluster_bootstrap_stability_failed"]
    assert all(
        not item["stable"]
        for item in result.wtp.sensitivity_summary["cluster_week_bootstrap"].values()
    )


def test_positive_price_direction_is_unstable_and_never_returns_amount() -> None:
    result = _quantify(_synthetic_context(reverse_direction=True))

    assert result.wtp.status == "unstable"
    assert result.wtp.estimate_low is None
    assert "price_direction_consistency_failed" in result.wtp.exclusion_reasons


def test_single_week_cohort_stops_before_choice_and_price_sensitivity() -> None:
    result = _quantify(_synthetic_context(single_week=True))

    assert result.level == "Q2_RELATIVE_EXPERIENCE"
    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert result.wtp.estimate_low is None


def test_stretch_only_is_observation_not_incremental_target_wtp() -> None:
    result = _quantify(
        _synthetic_context(
            crossings=(0.08,),
            families=("family-a",),
            roles=("stretch_benchmark",),
            tiers=("flagship",),
        )
    )

    assert result.level == "Q2_RELATIVE_EXPERIENCE"
    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert "base_counterfactual_missing" in result.wtp.exclusion_reasons


def test_perfect_market_curve_cannot_replace_unobserved_user_value() -> None:
    context = _synthetic_context()
    payload = context.model_dump(mode="python")
    payload["target_snapshot"]["comment_outcomes"] = []
    for candidate in payload["candidate_snapshots"]:
        candidate["comment_outcomes"] = []
    payload.pop("input_hash")
    context = SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )

    result = _quantify(context)

    assert result.level == "Q0_NOT_OBSERVED"
    assert result.value_status == "not_observed"
    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert result.wtp.estimate_low is None
    assert "user_value_not_fully_established" in result.wtp.exclusion_reasons


def test_partial_user_value_can_reach_market_observation_but_not_wtp() -> None:
    context = _synthetic_context()
    payload = context.model_dump(mode="python")
    payload["target_snapshot"]["comment_outcomes"] = payload["target_snapshot"][
        "comment_outcomes"
    ][:1]
    payload.pop("input_hash")
    context = SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )

    result = _quantify(context)

    assert result.value_status == "partial"
    assert result.level == "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE"
    assert result.choice_association is not None
    assert result.choice_association.status == "available"
    assert result.wtp.status == "insufficient"
    assert result.wtp.estimate_low is None
    assert "user_value_not_fully_established" in result.wtp.exclusion_reasons


def test_one_sided_zero_sales_cells_are_excluded_from_main_curve() -> None:
    context = _synthetic_context()
    payload = context.model_dump(mode="python")
    for row in payload["market_cells"]:
        if row["sku_code"].startswith("BASE-"):
            row["sales_volume"] = 0
            row["sales_amount"] = 0
    payload.pop("input_hash")
    context = SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )

    result = _quantify(context)

    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert result.wtp.estimate_low is None


def test_lineage_conflict_blocks_amount_but_keeps_descriptive_choice() -> None:
    result = _quantify(_synthetic_context(lineage_conflict=True))

    assert result.wtp.status == "blocked"
    assert result.wtp.estimate_low is None
    assert "version_lineage_conflict" in result.wtp.exclusion_reasons
    assert result.choice_association is not None
    assert result.choice_association.status == "available"


def test_near_same_price_is_distinct_from_exact_same_price_and_has_no_wtp() -> None:
    result = _quantify(
        _synthetic_context(
            crossings=(0.08, 0.10),
            families=("family-a", "family-b"),
            gap_mode="near",
        )
    )

    assert result.choice_association is not None
    assert result.choice_association.status == "available"
    assert result.choice_association.method == "near_same_price"
    assert result.wtp.estimate_low is None
    assert "strong_pair_curve_count_below_2" in result.wtp.exclusion_reasons


def test_sparse_gap_hole_does_not_interpolate_same_price() -> None:
    result = _quantify(
        _synthetic_context(
            crossings=(0.08,),
            families=("family-a",),
            gap_mode="hole",
        )
    )

    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert result.choice_association.same_price_choice_share is None
    assert result.wtp.estimate_low is None


def test_promotion_suspect_cells_do_not_enter_choice_or_wtp() -> None:
    result = _quantify(_synthetic_context(promotion_suspect=True))

    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert result.wtp.status == "insufficient"
    assert result.wtp.estimate_low is None


def test_65e7q_fixture_boundaries_never_invent_member_amounts(
    repo_root: Path,
) -> None:
    fixture = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G01_65E7Q_fixture.json"
        ).read_text(encoding="utf-8")
    )
    context = _base_context(lineage_conflict=True)
    tier_by_role = {
        "base_value": "base",
        "same_value": "premium",
        "stretch_benchmark": "flagship",
    }
    candidates = []
    for item in fixture["counterfactual_candidates"]:
        candidate = _candidate(
            context,
            sku_code=item["sku_code"],
            role=item["role"],
            provenance="competitor_set_fallback",
            tier=tier_by_role[item["role"]],
            size=item["screen_size_inch"],
            brightness=item["capability"].get("brightness_nit"),
            zones=item["capability"].get("local_dimming_zones"),
        )
        candidates.append(candidate.model_copy(update={"comment_outcomes": []}))
    payload = context.model_dump(mode="python")
    payload["candidate_snapshots"] = [
        item.model_dump(mode="python") for item in candidates
    ]
    payload["market_cells"] = []
    payload.pop("input_hash")
    context = SellpointValueV4Context(
        **payload,
        input_hash=canonical_v4_hash(payload),
    )

    result = _quantify(context)

    assert result.wtp.status == "blocked"
    assert result.wtp.estimate_low is None
    assert result.wtp.estimate_high is None
    assert result.wtp.causal_claim is False
    serialized = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    assert "estimated_price_premium_abs" not in serialized
    assert "MiniLED WTP" not in serialized
    assert "亮度 WTP" not in serialized


def test_g06_models_match_frozen_contract(repo_root: Path) -> None:
    from app.services.core3_real_data.analyst import claim_value_pm_v4_schemas

    contract = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G02_schema_contract.json"
        ).read_text(encoding="utf-8")
    )["models"]
    for name in ("ChoiceAssociation", "MarketImpliedWtp", "QuantificationResult"):
        model = getattr(claim_value_pm_v4_schemas, name)
        assert set(model.model_fields) == set(contract[name]["fields"])
        assert {
            key for key, field in model.model_fields.items() if field.is_required()
        } == set(contract[name]["required"])


def test_wtp_schema_rejects_amounts_without_full_gate() -> None:
    base = {
        "method_config_version": "sellpoint_value_pm_v4_matched_wtp_config_v2",
        "causal_claim": False,
        "psychological_max_price": False,
    }
    with pytest.raises(ValidationError):
        MarketImpliedWtp(
            status="available",
            method="matched_equal_choice_price_gap",
            estimate_low=400,
            estimate_high=500,
            reference_price=5000,
            pair_count=1,
            model_family_count=1,
            **base,
        )
    with pytest.raises(ValidationError, match="bootstrap and conservative interval"):
        MarketImpliedWtp(
            status="available",
            method="matched_equal_choice_price_gap",
            estimate_low=400,
            estimate_high=500,
            reference_price=5000,
            pair_count=2,
            model_family_count=2,
            **base,
        )

    with pytest.raises(ValidationError):
        MarketImpliedWtp(
            status="insufficient",
            method="none",
            estimate_low=None,
            estimate_high=None,
            reference_price=None,
            pair_count=0,
            model_family_count=0,
            causal_claim=False,
            psychological_max_price=False,
            method_config_version="sellpoint_value_pm_v4_matched_wtp_config_v1",
        )
    with pytest.raises(ValidationError):
        MarketImpliedWtp(
            status="insufficient",
            method="none",
            estimate_low=400,
            estimate_high=500,
            reference_price=5000,
            pair_count=0,
            model_family_count=0,
            **base,
        )


def test_g06_source_does_not_read_legacy_allocated_amounts(repo_root: Path) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/claim_value_pm_v4_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "estimated_price_premium_abs",
        "allocated_price_premium",
        "battlefield_allocation_weight *",
    ):
        assert forbidden not in source
