from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    MarketCellRow,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    build_counterfactual_assessments,
    build_reason_value_bundle_links,
)
from tests.core3_real_data.test_claim_value_pm_v4_linkage import _atom, _context


BATTLEFIELD = "BF_PREMIUM_PICTURE_UPGRADE"


def _base_context(*, lineage_conflict: bool = False) -> SellpointValueV4Context:
    context = _context(
        atoms=[
            _atom("白天阳光照进客厅也看得清，暗场层次也清楚", key="bright"),
            _atom(
                "肤色自然，颜色还原很真实",
                key="color",
                subdimension="picture_color_accuracy",
            ),
        ],
        lineage_conflict=lineage_conflict,
    )
    payload = context.target_snapshot.model_dump(mode="python")
    facts = deepcopy(payload["facts"])
    facts["parameter_fact"]["core_params"]["gaming"]["hdmi21_port_count"] = {
        "normalized_value": 2
    }
    payload["facts"] = facts
    payload.pop("snapshot_hash")
    snapshot = SkuEvidenceSnapshot(
        **payload,
        snapshot_hash=canonical_v4_hash(payload),
    )
    return context.model_copy(
        update={"target_snapshot": snapshot, "target": snapshot.identity}
    )


def _set_target_size_and_tier(
    context: SellpointValueV4Context,
    *,
    size: float,
    tier: str,
) -> SellpointValueV4Context:
    payload = context.target_snapshot.model_dump(mode="python")
    payload["identity"]["screen_size_inch"] = size
    facts = deepcopy(payload["facts"])
    facts["parameter_fact"]["dimension_tier_profile"]["picture"] = tier
    facts["parameter_fact"]["core_params"]["picture"]["screen_size_inch"] = {
        "normalized_value": size
    }
    payload["facts"] = facts
    payload.pop("snapshot_hash")
    snapshot = SkuEvidenceSnapshot(
        **payload,
        snapshot_hash=canonical_v4_hash(payload),
    )
    return context.model_copy(
        update={"target_snapshot": snapshot, "target": snapshot.identity}
    )


def _candidate(
    context: SellpointValueV4Context,
    *,
    sku_code: str,
    role: str,
    provenance: str,
    tier: str,
    size: float | None = None,
    battlefield: str = BATTLEFIELD,
    brightness: float | None = None,
    zones: int | None = None,
    other_bundle_differences: bool = False,
) -> SkuEvidenceSnapshot:
    payload = context.target_snapshot.model_dump(mode="python")
    payload["identity"].update(
        {
            "sku_code": sku_code,
            "model_name": sku_code,
            "screen_size_inch": (
                context.target_snapshot.identity.screen_size_inch
                if size is None
                else size
            ),
        }
    )
    facts = deepcopy(payload["facts"])
    facts["candidate_source"] = {
        "slot_code": role,
        "provenance": provenance,
    }
    facts["parameter_fact"]["dimension_tier_profile"]["picture"] = tier
    picture = facts["parameter_fact"]["core_params"]["picture"]
    picture["screen_size_inch"] = {
        "normalized_value": payload["identity"]["screen_size_inch"]
    }
    if brightness is not None:
        picture["declared_brightness_nit_or_band"] = {
            "normalized_value": {"value": brightness, "unit": "nits"}
        }
    if zones is not None:
        picture["local_dimming_zone_count"] = {"normalized_value": zones}
    if other_bundle_differences:
        facts["parameter_fact"]["core_params"]["gaming"]["refresh_rate_hz"] = {
            "normalized_value": 120
        }
        facts["parameter_fact"]["core_params"]["system"]["memory_capacity_gb"] = {
            "normalized_value": 2
        }
    payload["facts"] = facts
    payload["battlefields"] = [
        {
            "primary_battlefield_code": battlefield,
            "secondary_battlefield_codes": [],
            "opportunity_battlefield_codes": [],
        }
    ]
    payload.pop("snapshot_hash")
    return SkuEvidenceSnapshot(
        **payload,
        snapshot_hash=canonical_v4_hash(payload),
    )


def _market_cells(
    target_sku_code: str,
    candidates: list[SkuEvidenceSnapshot],
    *,
    weeks: int = 12,
    promotion_suspect: bool = False,
    price_status: str = "ok",
    battlefield: str = BATTLEFIELD,
) -> list[MarketCellRow]:
    result: list[MarketCellRow] = []
    sku_codes = [target_sku_code, *(item.identity.sku_code for item in candidates)]
    for position, sku_code in enumerate(sku_codes):
        for week in range(1, weeks + 1):
            result.append(
                MarketCellRow(
                    sku_code=sku_code,
                    battlefield_code=battlefield,
                    period_week_index=week,
                    platform_type="jd",
                    avg_price=5000 + position * 30 + week * 10,
                    sales_volume=100 + week,
                    sales_amount=(5000 + position * 30 + week * 10) * (100 + week),
                    price_check_status=price_status,
                    promotion_suspect=promotion_suspect,
                    inventory_status="unavailable",
                )
            )
    return result


def _with_candidates(
    context: SellpointValueV4Context,
    candidates: list[SkuEvidenceSnapshot],
    *,
    weeks: int = 12,
    promotion_suspect: bool = False,
    price_status: str = "ok",
    include_cells: bool = True,
) -> SellpointValueV4Context:
    cells = (
        _market_cells(
            context.target.sku_code,
            candidates,
            weeks=weeks,
            promotion_suspect=promotion_suspect,
            price_status=price_status,
        )
        if include_cells
        else []
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


def _picture_link(context: SellpointValueV4Context):
    return next(
        item
        for item in build_reason_value_bundle_links(context)
        if item.purchase_reason_code == "picture_upgrade_justifies_price"
    )


def test_three_roles_and_four_provenances_are_preserved_without_money() -> None:
    context = _base_context()
    candidates = [
        _candidate(
            context,
            sku_code="BASE-M14",
            role="base_value",
            provenance="M14",
            tier="base",
            brightness=1300,
            zones=264,
        ),
        _candidate(
            context,
            sku_code="SAME-M12C",
            role="same_value",
            provenance="M12C_pool",
            tier="premium",
        ),
        _candidate(
            context,
            sku_code="STRETCH-FAMILY",
            role="stretch_benchmark",
            provenance="same_family_search",
            tier="flagship",
            brightness=7000,
            zones=3000,
        ),
        _candidate(
            context,
            sku_code="BASE-FALLBACK",
            role="base_value",
            provenance="competitor_set_fallback",
            tier="enhanced",
            brightness=2200,
            zones=768,
        ),
    ]
    context = _with_candidates(context, candidates)

    first = build_counterfactual_assessments(context, _picture_link(context))
    second = build_counterfactual_assessments(context, _picture_link(context))

    assert [item.assessment_hash for item in first] == [
        item.assessment_hash for item in second
    ]
    by_sku = {item.candidate_sku_code: item for item in first}
    assert by_sku["BASE-M14"].role == "base_value"
    assert by_sku["BASE-M14"].provenance == "M14"
    assert by_sku["BASE-M14"].isolation_grade == "A"
    assert "Q5_MARKET_IMPLIED_WTP" in by_sku["BASE-M14"].eligible_quantification_levels
    assert by_sku["SAME-M12C"].role == "same_value"
    assert by_sku["SAME-M12C"].provenance == "M12C_pool"
    assert "same_value_only" in by_sku["SAME-M12C"].reject_reasons
    assert (
        "Q5_MARKET_IMPLIED_WTP"
        not in by_sku["SAME-M12C"].eligible_quantification_levels
    )
    assert by_sku["STRETCH-FAMILY"].eligible_quantification_levels == [
        "Q2_RELATIVE_EXPERIENCE"
    ]
    assert by_sku["BASE-FALLBACK"].provenance == "competitor_set_fallback"
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in first], ensure_ascii=False
    )
    assert "wtp_amount" not in serialized.lower()
    assert "estimated_price_premium_abs" not in serialized


@pytest.mark.parametrize(
    ("size", "battlefield", "weeks", "promotion", "price_status", "reason"),
    [
        (75, BATTLEFIELD, 12, False, "ok", "size_mismatch"),
        (65, "BF_OTHER", 12, False, "ok", "battlefield_mismatch"),
        (65, BATTLEFIELD, 12, True, "ok", "promotion_clean_cells_insufficient"),
        (65, BATTLEFIELD, 12, False, "invalid", "no_common_week_platform_cells"),
    ],
)
def test_comparability_failures_degrade_instead_of_guessing(
    size: float,
    battlefield: str,
    weeks: int,
    promotion: bool,
    price_status: str,
    reason: str,
) -> None:
    context = _base_context()
    candidate = _candidate(
        context,
        sku_code="DEGRADED",
        role="base_value",
        provenance="M14",
        tier="base",
        size=size,
        battlefield=battlefield,
        brightness=1300,
        zones=264,
    )
    context = _with_candidates(
        context,
        [candidate],
        weeks=weeks,
        promotion_suspect=promotion,
        price_status=price_status,
    )

    result = build_counterfactual_assessments(context, _picture_link(context))[0]

    assert reason in result.reject_reasons
    assert "Q5_MARKET_IMPLIED_WTP" not in result.eligible_quantification_levels
    if reason in {
        "size_mismatch",
        "battlefield_mismatch",
        "no_common_week_platform_cells",
    }:
        assert result.isolation_grade == "unusable"
        assert result.eligible is False


def test_two_other_bundle_differences_prevent_high_grade() -> None:
    context = _base_context()
    candidate = _candidate(
        context,
        sku_code="COLLINEAR-DIFF",
        role="base_value",
        provenance="M14",
        tier="base",
        brightness=1300,
        zones=264,
        other_bundle_differences=True,
    )
    context = _with_candidates(context, [candidate])

    result = build_counterfactual_assessments(context, _picture_link(context))[0]

    assert result.other_bundle_difference_count >= 2
    assert result.isolation_grade == "C"
    assert "other_bundle_differences" in result.reject_reasons
    assert result.eligible_quantification_levels == []


def test_observed_tier_overrides_a_stale_declared_role_and_degrades_candidate() -> None:
    context = _base_context()
    candidate = _candidate(
        context,
        sku_code="STALE-SLOT",
        role="base_value",
        provenance="M14",
        tier="flagship",
        brightness=7000,
        zones=3000,
    )
    context = _with_candidates(context, [candidate])

    result = build_counterfactual_assessments(context, _picture_link(context))[0]

    assert result.role == "stretch_benchmark"
    assert result.isolation_grade == "C"
    assert "candidate_role_tier_conflict" in result.reject_reasons
    assert result.eligible_quantification_levels == []


def test_g01_five_cohorts_replay_their_stop_boundaries(repo_root: Path) -> None:
    manifest = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G01_cohort_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert [item["cohort_id"] for item in manifest["cohorts"]] == [
        "C01_IDENTIFIABLE_CANDIDATE_PICTURE_TIER",
        "C02_ONLY_SAME_VALUE",
        "C03_FULL_COLLINEAR_SELLPOINTS",
        "C04_NO_TEMPORAL_PRICE_VARIATION",
        "C05_VERSION_FACT_CONFLICT",
    ]

    c01_context = _set_target_size_and_tier(_base_context(), size=75, tier="base")
    c01_candidate = _candidate(
        c01_context,
        sku_code="TV00027913",
        role="stretch_benchmark",
        provenance="same_family_search",
        tier="premium",
        size=75,
        brightness=2200,
        zones=768,
    )
    c01_context = _with_candidates(c01_context, [c01_candidate])
    c01 = build_counterfactual_assessments(c01_context, _picture_link(c01_context))[0]
    assert c01.role == "stretch_benchmark"
    assert c01.isolation_grade == "A"
    assert "Q5_MARKET_IMPLIED_WTP" not in c01.eligible_quantification_levels

    same_context = _base_context()
    same_candidate = _candidate(
        same_context,
        sku_code="TV00029020",
        role="same_value",
        provenance="competitor_set_fallback",
        tier="premium",
    )
    same_context = _with_candidates(same_context, [same_candidate])
    same_link = _picture_link(same_context)
    c02 = build_counterfactual_assessments(same_context, same_link)[0]
    assert "same_value_only" in c02.reject_reasons
    assert "Q5_MARKET_IMPLIED_WTP" not in c02.eligible_quantification_levels
    assert same_link.bundle.collinearity_group is not None
    assert len(build_counterfactual_assessments(same_context, same_link)) == 1

    one_week_context = _with_candidates(
        _base_context(),
        [
            _candidate(
                _base_context(),
                sku_code="ONE-WEEK",
                role="base_value",
                provenance="M14",
                tier="base",
                brightness=1300,
                zones=264,
            )
        ],
        weeks=1,
    )
    c04 = build_counterfactual_assessments(
        one_week_context, _picture_link(one_week_context)
    )[0]
    assert c04.common_week_count == 1
    assert "temporal_variation_insufficient" in c04.reject_reasons
    assert "Q5_MARKET_IMPLIED_WTP" not in c04.eligible_quantification_levels

    conflict_context = _base_context(lineage_conflict=True)
    conflict_candidate = _candidate(
        conflict_context,
        sku_code="VERSION-CONFLICT",
        role="base_value",
        provenance="M14",
        tier="base",
        brightness=1300,
        zones=264,
    )
    conflict_context = _with_candidates(conflict_context, [conflict_candidate])
    c05 = build_counterfactual_assessments(
        conflict_context, _picture_link(conflict_context)
    )[0]
    assert c05.isolation_grade == "A"
    assert "Q5_MARKET_IMPLIED_WTP" not in c05.eligible_quantification_levels


def test_65e7q_fixture_roles_are_replayed_from_fallback_provenance(
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
    candidates = [
        _candidate(
            context,
            sku_code=item["sku_code"],
            role=item["role"],
            provenance="competitor_set_fallback",
            tier=tier_by_role[item["role"]],
            size=item["screen_size_inch"],
            brightness=item["capability"].get("brightness_nit"),
            zones=item["capability"].get("local_dimming_zones"),
        )
        for item in fixture["counterfactual_candidates"]
    ]
    context = _with_candidates(context, candidates, include_cells=False)

    results = build_counterfactual_assessments(context, _picture_link(context))

    assert {item.candidate_sku_code: item.role for item in results} == {
        item["sku_code"]: item["role"] for item in fixture["counterfactual_candidates"]
    }
    assert {item.provenance for item in results} == {"competitor_set_fallback"}
    assert all(item.isolation_grade == "unusable" for item in results)
    assert all(item.eligible_quantification_levels == [] for item in results)


def test_g05_schema_matches_frozen_contract(repo_root: Path) -> None:
    from app.services.core3_real_data.analyst import claim_value_pm_v4_schemas

    contract = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G02_schema_contract.json"
        ).read_text(encoding="utf-8")
    )["models"]["ComparabilityAssessment"]
    model = claim_value_pm_v4_schemas.ComparabilityAssessment

    assert set(model.model_fields) == set(contract["fields"])
    assert {
        key for key, field in model.model_fields.items() if field.is_required()
    } == set(contract["required"])


def test_g05_source_does_not_consume_legacy_amounts_or_choice_curve(
    repo_root: Path,
) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/claim_value_pm_v4_service.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "estimated_price_premium_abs",
        "same_price_choice_share",
        "selection_holding_gap",
        "pava",
    ):
        assert forbidden not in source.lower()
