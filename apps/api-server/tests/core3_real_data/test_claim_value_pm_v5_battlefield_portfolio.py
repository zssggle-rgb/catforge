from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    BattlefieldPortfolioInput,
    ExpansionGap,
    SellpointValueV5Context,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_service import (
    build_battlefield_portfolio_options,
)
from tests.core3_real_data.test_claim_value_pm_v5_counterfactuals import (
    _v5_context,
)


PICTURE = "BF_PREMIUM_PICTURE_UPGRADE"
SMART = "BF_SMART_CONNECTED_EXPERIENCE"
GAME = "BF_GAMING_SPORTS_FLUENCY"
LIVING = "BF_MAINSTREAM_LIVING_BALANCE"
EYE = "BF_EYE_CARE_FAMILY_COMFORT"
LARGE_CINEMA = "BF_LARGE_SCREEN_FAMILY_CINEMA"


def _portfolio_context() -> SellpointValueV5Context:
    context = _v5_context()
    target = context.v4_context.target_snapshot
    payload = target.model_dump(mode="python")
    payload["battlefields"] = [
        {
            "primary_battlefield_code": PICTURE,
            "secondary_battlefield_codes": [SMART, GAME],
            "opportunity_battlefield_codes": [EYE],
            "user_observed_battlefield_codes": [LIVING],
            "drag_factor_battlefield_codes": ["BF_DRAG"],
        }
    ]
    payload.pop("snapshot_hash")
    rebuilt_target = SkuEvidenceSnapshot(
        **payload,
        snapshot_hash=canonical_v4_hash(payload),
    )
    v4_payload = context.v4_context.model_dump(mode="python")
    v4_payload["target_snapshot"] = rebuilt_target.model_dump(mode="python")
    v4_payload["target"] = rebuilt_target.identity.model_dump(mode="python")
    v4_payload.pop("input_hash")
    rebuilt_v4 = SellpointValueV4Context(
        **v4_payload,
        input_hash=canonical_v4_hash(v4_payload),
    )
    context_payload = context.model_dump(mode="python")
    context_payload["v4_context"] = rebuilt_v4.model_dump(mode="python")
    context_payload["market_universe"] = [
        rebuilt_target.model_dump(mode="python")
        if row.identity.sku_code == rebuilt_target.identity.sku_code
        else row.model_dump(mode="python")
        for row in context.market_universe
    ]
    return SellpointValueV5Context(**context_payload)


def _input(
    code: str,
    membership: str,
    *,
    role_capped: bool = False,
    user_value_status: str = "observed_positive",
    claim_support: str = "strong",
    capability_status: str = "complete",
    gaps: list[ExpansionGap] | None = None,
    market_status: str = "available",
    immutable_gate: bool | None = True,
    product_form_gate: bool | None = True,
    adjacency: float | None = 0.8,
    donors: int = 5,
    lineage_blocking: bool = False,
) -> BattlefieldPortfolioInput:
    return BattlefieldPortfolioInput(
        battlefield_code=code,
        battlefield_name_cn=code,
        source_membership=membership,
        user_value_status=user_value_status,
        claim_support=claim_support,
        capability_status=capability_status,
        capability_gaps=gaps or [],
        market_realization_status=market_status,
        role_capped=role_capped,
        immutable_market_gate_pass=immutable_gate,
        product_form_gate_pass=product_form_gate,
        task_group_adjacency=adjacency,
        donor_count=donors,
        market_space={"estimated_sales_volume": 1000},
        current_allocation=None,
        overlap_risk="medium",
        lineage_blocking=lineage_blocking,
    )


def test_all_entered_memberships_are_strengthening_not_expansion() -> None:
    context = _portfolio_context()
    inputs = [
        _input(PICTURE, "primary", market_status="degraded"),
        _input(GAME, "secondary", capability_status="partial"),
        _input(LIVING, "user_observed", claim_support="missing"),
        _input(EYE, "opportunity", role_capped=True),
    ]
    result = build_battlefield_portfolio_options(context, inputs)
    by_code = {row.battlefield_code: row for row in result}

    assert {row.option_type for row in result} == {"strengthen_existing"}
    assert by_code[PICTURE].strengthen_path == "market_activation"
    assert by_code[GAME].strengthen_path == "capability_completion"
    assert by_code[LIVING].strengthen_path == "communication_activation"
    assert by_code[EYE].strengthen_path == "portfolio_priority"


def test_excluded_expansion_requires_mutable_gap_market_gate_and_donors() -> None:
    context = _portfolio_context()
    eligible_gap = ExpansionGap(
        gap_code="claim_expression",
        change_type="communication",
        mutable_in_scope=True,
        status="missing",
        evidence=[],
    )
    eligible = build_battlefield_portfolio_options(
        context,
        [_input("BF_NEW", "excluded", gaps=[eligible_gap])],
    )[0]

    assert eligible.option_type == "expand_excluded"
    assert eligible.expansion_eligibility is not None
    assert eligible.expansion_eligibility.stage == "eligible"
    assert eligible.expansion_eligibility.eligible is True

    immutable_gap = ExpansionGap(
        gap_code="screen_size",
        change_type="size",
        mutable_in_scope=False,
        status="missing",
        evidence=[],
    )
    rejected = build_battlefield_portfolio_options(
        context,
        [
            _input(
                LARGE_CINEMA,
                "excluded",
                gaps=[immutable_gap],
                immutable_gate=False,
                donors=10,
            )
        ],
    )[0]

    assert rejected.expansion_eligibility is not None
    assert rejected.expansion_eligibility.stage == "rejected"
    assert "immutable_size_price_market_gate_failed" in rejected.limitations
    assert "immutable_gap:screen_size" in rejected.limitations


def test_65e7q_eye_care_is_existing_and_large_cinema_is_rejected() -> None:
    context = _portfolio_context()
    size_gap = ExpansionGap(
        gap_code="screen_size",
        change_type="size",
        mutable_in_scope=False,
        status="missing",
        evidence=[],
    )
    result = build_battlefield_portfolio_options(
        context,
        [
            _input(EYE, "opportunity", role_capped=True),
            _input(
                LARGE_CINEMA,
                "excluded",
                gaps=[size_gap],
                immutable_gate=False,
                donors=9,
            ),
        ],
    )
    eye, cinema = result

    assert eye.battlefield_code == EYE
    assert eye.option_type == "strengthen_existing"
    assert eye.strengthen_path == "portfolio_priority"
    assert "不是进入新战场" in eye.evidence_boundary
    assert cinema.option_type == "expand_excluded"
    assert cinema.expansion_eligibility is not None
    assert cinema.expansion_eligibility.eligible is False


def test_no_excluded_input_produces_a_legal_empty_expansion_list() -> None:
    result = build_battlefield_portfolio_options(
        _portfolio_context(),
        [_input(PICTURE, "primary")],
    )

    assert [row for row in result if row.option_type == "expand_excluded"] == []


def test_membership_drift_is_blocked_instead_of_relabelled() -> None:
    with pytest.raises(ValueError, match="membership mismatch"):
        build_battlefield_portfolio_options(
            _portfolio_context(),
            [_input(EYE, "excluded")],
        )


def test_duplicate_input_and_drag_lineage_are_explicit() -> None:
    context = _portfolio_context()
    with pytest.raises(ValueError, match="duplicate battlefield"):
        build_battlefield_portfolio_options(
            context,
            [_input(PICTURE, "primary"), _input(PICTURE, "primary")],
        )
    drag = build_battlefield_portfolio_options(
        context,
        [
            _input(
                "BF_DRAG",
                "drag",
                user_value_status="observed_negative",
                lineage_blocking=True,
            )
        ],
    )[0]
    assert drag.strengthen_path == "maintain_or_cap"
    assert drag.limitations == [
        "battlefield_lineage_conflict",
        "drag_battlefield_not_positive_growth_option",
    ]


def test_expansion_unknown_and_recall_states_do_not_become_eligible() -> None:
    context = _portfolio_context()
    unknown_gap = ExpansionGap(
        gap_code="capability",
        change_type="capability",
        mutable_in_scope=True,
        status="unknown",
        evidence=[],
    )
    deferred = build_battlefield_portfolio_options(
        context,
        [
            _input(
                "BF_UNKNOWN",
                "excluded",
                gaps=[unknown_gap],
                immutable_gate=None,
                product_form_gate=None,
                adjacency=None,
            )
        ],
    )[0]
    assert deferred.expansion_eligibility is not None
    assert deferred.expansion_eligibility.stage == "deferred_unknown"

    recalled = build_battlefield_portfolio_options(
        context,
        [
            _input(
                "BF_RECALL",
                "excluded",
                adjacency=0.3,
                donors=2,
            )
        ],
    )[0]
    assert recalled.expansion_eligibility is not None
    assert recalled.expansion_eligibility.stage == "recalled"
    assert "task_group_adjacency_insufficient" in recalled.limitations
    assert "expansion_donor_count_insufficient" in recalled.limitations


def test_expansion_without_market_space_or_with_lineage_is_rejected() -> None:
    context = _portfolio_context()
    payload = _input("BF_EMPTY", "excluded", lineage_blocking=True).model_dump(
        mode="python"
    )
    payload["market_space"] = {}
    rejected = build_battlefield_portfolio_options(
        context,
        [BattlefieldPortfolioInput(**payload)],
    )[0]
    assert rejected.expansion_eligibility is not None
    assert rejected.expansion_eligibility.stage == "rejected"
    assert "battlefield_lineage_conflict" in rejected.limitations
    assert "battlefield_market_space_missing" in rejected.limitations


def test_portfolio_result_is_independent_of_input_order() -> None:
    context = _portfolio_context()
    rows = [
        _input(PICTURE, "primary"),
        _input(EYE, "opportunity", role_capped=True),
        _input("BF_NEW", "excluded"),
    ]
    first = build_battlefield_portfolio_options(context, rows)
    second = build_battlefield_portfolio_options(context, list(reversed(rows)))

    assert [row.model_dump(mode="json") for row in first] == [
        row.model_dump(mode="json") for row in second
    ]


def test_battlefield_input_is_typed_and_forbids_hidden_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BattlefieldPortfolioInput(
            **{
                **_input(PICTURE, "primary").model_dump(mode="python"),
                "automatic_sales_lift": 999,
            }
        )


def test_g01_c06_c07_are_bound_to_portfolio_regression(repo_root: Path) -> None:
    manifest = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v5/G01_cohort_manifest.json"
        ).read_text(encoding="utf-8")
    )
    by_id = {row["cohort_id"]: row for row in manifest["cohorts"]}

    assert by_id["C06_EXISTING_AND_EXCLUDED_BATTLEFIELD"]["sku_codes"] == [
        "TV00029112"
    ]
    assert by_id["C07_NO_OBSERVABLE_EXPANSION"]["input_sha256"] == (
        "586e1136c32abd0e4c7b8769607053306281408dd227229b722ab6f1545aca72"
    )


def test_portfolio_source_does_not_turn_market_space_into_increment(repo_root: Path) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/claim_value_pm_v5_service.py"
    ).read_text(encoding="utf-8")
    section = source.split("def build_battlefield_portfolio_options", 1)[1].split(
        "def _failed_synthetic", 1
    )[0]

    assert "increment=" not in section
    assert "allocated_sales_volume" not in section
    assert "sales_lift" not in section
