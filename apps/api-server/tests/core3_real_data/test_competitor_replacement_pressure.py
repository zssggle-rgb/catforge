from decimal import Decimal

from app.services.core3_real_data.analyst.anchor_substitutability import (
    AnchorSubstitutabilityBreakdown,
    AnchorSubstitutabilityResult,
)
from app.services.core3_real_data.analyst.replacement_pressure import (
    ReplacementPressureClassifier,
    ReplacementPressureInput,
)


def test_replacement_pressure_selects_value_substitution_as_primary() -> None:
    result = ReplacementPressureClassifier().classify(
        ReplacementPressureInput(
            purchase_pool_level="P0",
            purchase_pool_score=Decimal("1.00"),
            anchor_substitutability=_anchor_result(
                score=15,
                shared_core=["画质配置解释加价", "贵得值的体验升级"],
                candidate_stronger=["画质配置解释加价"],
            ),
            price_gap_pct_to_target=Decimal("0.02"),
            weighted_overlap={"battlefield": Decimal("0.85"), "user_task": Decimal("0.80"), "target_group": Decimal("0.75")},
            market_validation_level="strong",
            candidate_config_advantage_score=Decimal("0.80"),
            candidate_scenario_mindshare_score=Decimal("0.70"),
        )
    )

    assert result.replacement_pressure_score == 10
    assert result.replacement_pressure_level == "high"
    assert result.primary_pressure_type == "value_substitution"
    assert result.strong_pressure_allowed is True
    assert len(result.auxiliary_pressure_types) <= 2
    assert result.score_breakdown.purchase_pool_pressure == Decimal("2.0000")
    assert result.score_breakdown.purchase_reason_pressure == Decimal("3.0000")


def test_replacement_pressure_selects_price_suppression_for_lower_price_with_core_anchor() -> None:
    result = ReplacementPressureClassifier().classify(
        ReplacementPressureInput(
            purchase_pool_level="P1",
            purchase_pool_score=Decimal("0.85"),
            anchor_substitutability=_anchor_result(score=10, shared_core=["贵得值的体验升级"]),
            price_gap_pct_to_target=Decimal("-0.18"),
            weighted_overlap={"battlefield": Decimal("0.60"), "user_task": Decimal("0.55"), "target_group": Decimal("0.50")},
            market_validation_level="medium",
        )
    )

    assert result.replacement_pressure_score >= 7
    assert result.primary_pressure_type == "price_suppression"
    assert result.primary_pressure_type_cn == "价格压制压力"
    assert result.strong_pressure_allowed is True
    assert "更低价格" in result.reason_cn


def test_replacement_pressure_low_score_does_not_emit_strong_substitution_language() -> None:
    result = ReplacementPressureClassifier().classify(
        ReplacementPressureInput(
            purchase_pool_level="P4",
            purchase_pool_score=Decimal("0.35"),
            anchor_substitutability=_anchor_result(score=4, shared_core=[]),
            price_gap_pct_to_target=Decimal("0.03"),
            weighted_overlap={"battlefield": Decimal("0.20"), "user_task": Decimal("0.18"), "target_group": Decimal("0.15")},
            market_validation_level="weak",
            candidate_scenario_mindshare_score=Decimal("0.20"),
            risk_flags=["sample_limited", "claim_only"],
        )
    )

    assert result.replacement_pressure_score < 5
    assert result.primary_pressure_type == "low_pressure_review"
    assert result.strong_pressure_allowed is False
    assert result.requires_review is True
    assert "不能输出强替代话术" in result.reason_cn
    assert "强替代压力" not in result.reason_cn


def test_replacement_pressure_outputs_one_primary_and_at_most_two_auxiliary_types() -> None:
    result = ReplacementPressureClassifier().classify(
        ReplacementPressureInput(
            purchase_pool_level="P1",
            purchase_pool_score=Decimal("0.85"),
            anchor_substitutability=_anchor_result(
                score=13,
                shared_core=["画质配置解释加价"],
                candidate_stronger=["游戏设备适配降低决策风险"],
            ),
            price_gap_pct_to_target=Decimal("-0.20"),
            weighted_overlap={"battlefield": Decimal("0.82"), "user_task": Decimal("0.78"), "target_group": Decimal("0.74")},
            market_validation_level="strong",
            candidate_config_advantage_score=Decimal("0.90"),
            candidate_scenario_mindshare_score=Decimal("0.90"),
            brand_ecosystem_score=Decimal("0.80"),
        )
    )

    assert result.primary_pressure_type == "price_suppression"
    assert len(result.auxiliary_pressure_types) == 2
    assert result.primary_pressure_type not in {item.pressure_type for item in result.auxiliary_pressure_types}
    assert len({item.pressure_type for item in result.auxiliary_pressure_types}) == 2


def test_replacement_pressure_blocks_strong_output_when_anchor_pair_is_blocked() -> None:
    result = ReplacementPressureClassifier().classify(
        ReplacementPressureInput(
            purchase_pool_level="P0",
            purchase_pool_score=Decimal("1.00"),
            anchor_substitutability=_anchor_result(score=0, pair_scoring_allowed=False, requires_review=True),
            price_gap_pct_to_target=Decimal("-0.18"),
            weighted_overlap={"battlefield": Decimal("0.80"), "user_task": Decimal("0.80"), "target_group": Decimal("0.80")},
            market_validation_level="strong",
        )
    )

    assert result.replacement_pressure_score < 5
    assert result.strong_pressure_allowed is False
    assert result.requires_review is True
    assert result.score_breakdown.purchase_reason_pressure == Decimal("0.0000")
    assert "anchor_pair_scoring_blocked" in result.risk_notes


def _anchor_result(
    *,
    score: int,
    shared_core: list[str] | None = None,
    candidate_stronger: list[str] | None = None,
    pair_scoring_allowed: bool = True,
    requires_review: bool = False,
) -> AnchorSubstitutabilityResult:
    return AnchorSubstitutabilityResult(
        anchor_substitutability_score=score,
        anchor_substitutability_score_raw=Decimal(score),
        anchor_substitutability_level="strong" if score >= 13 else "medium" if score >= 10 else "partial" if score >= 7 else "insufficient",
        score_breakdown=AnchorSubstitutabilityBreakdown(),
        shared_core_anchors=shared_core or [],
        candidate_stronger_anchors=candidate_stronger or [],
        anchor_substitution_summary_cn="测试锚点替代性。",
        pair_scoring_allowed=pair_scoring_allowed,
        primary_direct_eligible=score >= 7 and pair_scoring_allowed,
        requires_review=requires_review,
    )
