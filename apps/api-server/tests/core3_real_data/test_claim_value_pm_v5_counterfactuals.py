from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketCellRow,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_counterfactuals import (
    _same_claim_contrast,
    build_v5_counterfactual_sets,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldDefinitionSnapshot,
    MethodConfigManifest,
    SellpointValueV5Context,
)
from tests.core3_real_data.test_claim_value_pm_v4_linkage import _context


BATTLEFIELD = "BF_PREMIUM_PICTURE_UPGRADE"


def _snapshot(
    base: SkuEvidenceSnapshot,
    *,
    sku_code: str,
    brand: str,
    price: float,
    tier: int | None,
    supported: list[str] | None = None,
    contradicted: list[str] | None = None,
    advertised: list[str] | None = None,
    authority_eligible: bool | None = None,
    platforms: int = 2,
    sales_volume: float = 1000,
) -> SkuEvidenceSnapshot:
    payload = base.model_dump(mode="python")
    payload["identity"].update(
        {"sku_code": sku_code, "brand_name": brand, "model_name": sku_code}
    )
    facts = deepcopy(payload["facts"])
    facts["dimension_tier_ranks"] = {} if tier is None else {"picture": tier}
    facts["advertised_claim_codes"] = advertised or []
    facts["supported_claim_codes"] = supported or []
    facts["contradicted_claim_codes"] = contradicted or []
    if authority_eligible is not None:
        facts["candidate_source"] = {
            "provenance": "M14",
            "authority_eligible": authority_eligible,
        }
    payload["facts"] = facts
    payload["market"] = {
        "price_wavg": price,
        "sales_volume_total": sales_volume,
        "active_week_count": 24,
        "platform_count": platforms,
        "price_volatility": 0.1,
    }
    payload["battlefields"] = [
        {
            "primary_battlefield_code": BATTLEFIELD,
            "secondary_battlefield_codes": [],
            "opportunity_battlefield_codes": [],
        }
    ]
    payload.pop("snapshot_hash")
    return SkuEvidenceSnapshot(
        **payload,
        snapshot_hash=canonical_v4_hash(payload),
    )


def _v5_context(
    *,
    direct_authority_eligible: bool = False,
    weak_own_curve: bool = False,
    reverse_universe: bool = False,
) -> SellpointValueV5Context:
    v4 = _context()
    target = _snapshot(
        v4.target_snapshot,
        sku_code="TARGET",
        brand="海信",
        price=6000,
        tier=3,
        advertised=["CLAIM-PICTURE"],
        supported=["CLAIM-PICTURE"],
        platforms=1 if weak_own_curve else 2,
        sales_volume=2000,
    )
    direct = _snapshot(
        target,
        sku_code="DIRECT-LOWER",
        brand="小米",
        price=5800,
        tier=2,
        authority_eligible=direct_authority_eligible,
    )
    same_claim = _snapshot(
        target,
        sku_code="SAME-CLAIM",
        brand="TCL",
        price=5500,
        tier=3,
        advertised=["CLAIM-PICTURE"],
        contradicted=["CLAIM-PICTURE"],
    )
    brand_ladder = _snapshot(
        target,
        sku_code="BRAND-LOWER",
        brand="海信",
        price=4200,
        tier=2,
    )
    unknown = _snapshot(
        target,
        sku_code="UNKNOWN-TIER",
        brand="其他",
        price=5900,
        tier=None,
    )
    donors = [
        _snapshot(
            target,
            sku_code=f"DONOR-{index}",
            brand=f"品牌{index}",
            price=5000 + index * 100,
            tier=2,
        )
        for index in range(5)
    ]
    universe = [target, direct, same_claim, brand_ladder, unknown, *donors]
    if reverse_universe:
        universe.reverse()

    cells = []
    for sku_code in (target.identity.sku_code, direct.identity.sku_code):
        for week in range(1, 13):
            cells.append(
                MarketCellRow(
                    sku_code=sku_code,
                    battlefield_code=BATTLEFIELD,
                    period_week_index=week,
                    platform_type="jd",
                    avg_price=6000,
                    sales_volume=100,
                    sales_amount=600000,
                    price_check_status="ok",
                    promotion_suspect=False,
                    inventory_status="unavailable",
                )
            )
    v4_payload = v4.model_dump(mode="python")
    v4_payload.update(
        {
            "target": target.identity.model_dump(mode="python"),
            "target_snapshot": target.model_dump(mode="python"),
            "candidate_snapshots": [direct.model_dump(mode="python")],
            "market_cells": [row.model_dump(mode="python") for row in cells],
        }
    )
    v4_payload.pop("input_hash")
    rebuilt_v4 = SellpointValueV4Context(
        **v4_payload,
        input_hash=canonical_v4_hash(v4_payload),
    )
    payload = {
        "schema_version": "sellpoint_value_v5_context_v1",
        "project_id": rebuilt_v4.project_id,
        "category_code": rebuilt_v4.category_code,
        "v4_context": rebuilt_v4,
        "market_universe": universe,
        "battlefield_taxonomy": [
            BattlefieldDefinitionSnapshot(
                battlefield_code=BATTLEFIELD,
                battlefield_name_cn="高端画质升级",
                source_hash="taxonomy-hash",
            )
        ],
        "method_configs": MethodConfigManifest(
            recall_version="sellpoint_value_pm_v5_counterfactual_recall_v1",
            synthetic_version="sellpoint_value_pm_v5_synthetic_control_v1",
            archetype_version="sellpoint_value_pm_v5_performance_archetype_v1",
            expansion_version="sellpoint_value_pm_v5_expansion_gate_v1",
            amount_version="sellpoint_value_pm_v4_matched_wtp_config_v2",
        ),
        "input_hash": "v5-input-hash",
    }
    return SellpointValueV5Context(**payload)


def _sets(context: SellpointValueV5Context):
    return build_v5_counterfactual_sets(
        context,
        bundle_code="picture_bundle",
        focus_dimension_codes=["picture"],
        focus_claim_codes=["CLAIM-PICTURE"],
    )


def test_m14_ineligible_still_has_multi_layer_fallbacks() -> None:
    by_question = {row.question: row for row in _sets(_v5_context())}

    direct = next(
        row
        for row in by_question["relative_highlight"].candidates
        if row.method == "direct_sku"
    )
    assert direct.stage == "screened"
    assert "direct_authority_not_eligible" in direct.reject_reasons
    assert by_question["relative_highlight"].highest_available_method == "same_budget_pool"
    assert by_question["user_realization"].highest_available_method == "same_claim_realization"
    assert by_question["price_realization"].highest_available_method == "own_price_curve"
    assert by_question["volume_realization"].highest_available_method == "same_budget_pool"

    synthetic = next(
        row
        for row in by_question["without_value_baseline"].candidates
        if row.method == "market_synthetic"
    )
    assert synthetic.stage == "recalled"
    assert len(synthetic.candidate_sku_codes) >= 5
    assert synthetic.eligible_measures == []
    assert synthetic.control_dimensions["balanced"] is False


def test_authoritative_direct_candidate_wins_when_explicitly_eligible() -> None:
    relative = {
        row.question: row for row in _sets(_v5_context(direct_authority_eligible=True))
    }["relative_highlight"]

    assert relative.highest_available_method == "direct_sku"
    direct = next(row for row in relative.candidates if row.method == "direct_sku")
    assert direct.stage == "eligible"
    assert direct.comparability_grade == "A"
    assert direct.common_week_count == 12


def test_unknown_tier_is_never_treated_as_lower_value() -> None:
    baseline = {row.question: row for row in _sets(_v5_context())}[
        "without_value_baseline"
    ]

    unknown_rows = [
        row
        for row in baseline.candidates
        if "UNKNOWN-TIER" in row.candidate_sku_codes
        and row.method == "param_tier_pool"
    ]
    assert unknown_rows == []


def test_resolver_is_independent_of_market_universe_order() -> None:
    normal = _sets(_v5_context())
    reversed_rows = _sets(_v5_context(reverse_universe=True))

    assert [row.set_hash for row in normal] == [row.set_hash for row in reversed_rows]
    assert [
        [(candidate.method, candidate.candidate_key) for candidate in row.candidates]
        for row in normal
    ] == [
        [(candidate.method, candidate.candidate_key) for candidate in row.candidates]
        for row in reversed_rows
    ]


def test_weak_own_price_curve_is_rejected_without_guessing() -> None:
    price = {row.question: row for row in _sets(_v5_context(weak_own_curve=True))}[
        "price_realization"
    ]
    own = next(row for row in price.candidates if row.method == "own_price_curve")

    assert own.stage == "rejected"
    assert own.eligible_measures == []
    assert own.reject_reasons == ["platform_count_insufficient"]


def test_same_claim_contrast_fails_closed_without_bundle_claims() -> None:
    context = _v5_context()
    snapshots = {row.identity.sku_code: row for row in context.market_universe}

    assert _same_claim_contrast(snapshots["TARGET"], snapshots["SAME-CLAIM"], []) == {}


def test_unrelated_claim_contradiction_is_not_a_value_counterfactual() -> None:
    context = _v5_context()
    snapshots = {row.identity.sku_code: row for row in context.market_universe}

    assert (
        _same_claim_contrast(
            snapshots["TARGET"], snapshots["SAME-CLAIM"], ["CLAIM-GAMING"]
        )
        == {}
    )


def test_user_realization_window_is_wider_than_same_budget_price_pool() -> None:
    context = _v5_context()
    universe = [
        row.model_copy(update={"market": {**row.market, "price_wavg": 4800}})
        if row.identity.sku_code == "SAME-CLAIM"
        else row
        for row in context.market_universe
    ]
    sets = _sets(context.model_copy(update={"market_universe": universe}))
    by_question = {row.question: row for row in sets}

    assert any(
        row.method == "same_claim_realization"
        and row.candidate_sku_codes == ["SAME-CLAIM"]
        and row.stage == "eligible"
        for row in by_question["user_realization"].candidates
    )
    assert not any(
        row.method == "same_budget_pool"
        and row.candidate_sku_codes == ["SAME-CLAIM"]
        for row in by_question["relative_highlight"].candidates
    )


def test_g01_cohorts_and_65e7q_coverage_are_frozen(repo_root: Path) -> None:
    base = repo_root / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v5"
    manifest = json.loads((base / "G01_cohort_manifest.json").read_text(encoding="utf-8"))
    fixture = json.loads((base / "G01_65E7Q_fixture.json").read_text(encoding="utf-8"))

    assert [row["cohort_id"] for row in manifest["cohorts"]] == [
        "C01_65E7Q_MULTI_LAYER",
        "C02_DIRECT_TIER",
        "C03_SYNTHETIC_DONOR_RICH",
        "C04_SAME_CLAIM_DIFFERENT_REALIZATION",
        "C05_NO_STRONG_OWN_PRICE_CURVE",
        "C06_EXISTING_AND_EXCLUDED_BATTLEFIELD",
        "C07_NO_OBSERVABLE_EXPANSION",
        "C08_NEGATIVE_MIXED_USER_VALUE",
    ]
    assert fixture["counterfactual_coverage"] == {
        "same_market_pool_peer_count": 51,
        "same_brand_size_peer_count": 8,
        "same_budget_15pct_peer_count": 3,
        "broad_synthetic_donor_count": 9,
        "param_tier_roles": ["lower", "same", "higher"],
        "own_price_curve_strong": True,
    }
    assert fixture["quantification_boundary"]["strict_amount_allowed_now"] is False


def test_g03_source_does_not_estimate_effects_or_legacy_amounts(repo_root: Path) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/claim_value_pm_v5_counterfactuals.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "estimated_price_premium_abs",
        "weekly_sales_lift_abs",
        "matched_equal_choice_price_gap",
        "placebo_percentile =",
        "donor_weights =",
    ):
        assert forbidden not in source
