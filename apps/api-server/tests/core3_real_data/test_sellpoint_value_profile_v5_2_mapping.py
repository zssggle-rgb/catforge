from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_mapping import (
    CompetitorSellpointObservation,
    build_layered_sellpoint_analysis,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    CompetitorSellpointFindingType,
    M04CSourceLineage,
    ParameterClassification,
    SellpointClassification,
    SourceSellpointFact,
    SourceSellpointReadResult,
    SourceSellpointState,
)


GAME_CLAIM = (
    "【其他卖点】4K 170Hz原生高刷+300Hz动态刷新，"
    "四路满血HDMI 2.1支持48Gbps传输，游戏影音双丝滑"
)


def _evidence(record_id: str, module: str = "M04C") -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code=module,
        record_type="fact",
        record_id=record_id,
        result_hash=f"sha256:{record_id}",
        evidence_ids=[f"ev-{record_id}"],
    )


def _lineage(category_code: str = "TV") -> M04CSourceLineage:
    return M04CSourceLineage(
        project_id="project-1",
        category_code=category_code,
        batch_id="batch-1",
        sku_code=f"{category_code}0001",
        claim_profile_id="claim-profile-1",
        taxonomy_version=f"{category_code.lower()}-taxonomy",
        rule_version=f"{category_code.lower()}-rule",
        profile_result_hash="sha256:profile",
        evidence_ref=_evidence("profile"),
    )


def _source_fact(
    *,
    claim_code: str,
    claim_name: str,
    raw_claim_text: str,
    primary_params: list[str] | None = None,
    supporting_params: list[str] | None = None,
    fact_id: str = "claim-fact-1",
) -> SourceSellpointFact:
    return SourceSellpointFact(
        source_claim_key="raw:1",
        claim_fact_id=fact_id,
        merged_claim_fact_ids=[fact_id],
        raw_claim_text=raw_claim_text,
        clean_claim_text=raw_claim_text,
        normalized_claim_code=claim_code,
        normalized_claim_name_cn=claim_name,
        claim_dimension="product_experience",
        claim_kind="product_experience",
        claim_subtype="experience",
        param_support_status="supported",
        param_support_level="specific",
        param_support_specificity="specific",
        primary_supporting_param_codes=sorted(primary_params or []),
        supporting_param_codes=sorted(supporting_params or []),
        generic_support_param_codes=[],
        fact_claim=True,
        confidence=Decimal("0.90"),
        evidence_refs=[_evidence(fact_id)],
    )


def _source_result(
    facts: list[SourceSellpointFact],
    *,
    category_code: str = "TV",
) -> SourceSellpointReadResult:
    return SourceSellpointReadResult(
        status=(
            SourceSellpointState.AVAILABLE
            if facts
            else SourceSellpointState.NO_SOURCE_SELLPOINT
        ),
        lineage=_lineage(category_code) if facts else None,
        source_sellpoints=facts,
    )


def _decision(
    capability_code: str,
    classification: str,
    *,
    confidence: str = "0.85",
) -> SimpleNamespace:
    return SimpleNamespace(
        capability_code=capability_code,
        capability_name_cn=capability_code,
        classification=classification,
        confidence=Decimal(confidence),
        evidence_refs=[_evidence(f"decision-{capability_code}", "SPV51")],
    )


def _parameter_result(
    parameter_code: str,
    *,
    core_highlight_eligible: bool,
    target_value: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        parameter_code=parameter_code,
        parameter_name_cn=parameter_code,
        target_value=target_value,
        core_highlight_eligible=core_highlight_eligible,
        status="conclusion_available",
        confidence=Decimal("0.80"),
        evidence_refs=[_evidence(f"param-{parameter_code}", "SPV51")],
    )


def _value(
    *,
    definition_code: str,
    outcome: str,
    decisions: list[SimpleNamespace],
    parameter_results: list[SimpleNamespace] | None = None,
    market_available: bool = True,
) -> SimpleNamespace:
    direct_results = (
        [
            SimpleNamespace(
                status="conclusion_available",
                result_hash=f"sha256:market-{definition_code}",
                evidence_refs=[_evidence(f"market-{definition_code}", "SPV51")],
            )
        ]
        if market_available
        else []
    )
    return SimpleNamespace(
        value_bundle_code=f"bundle-{definition_code}",
        normalized_bundle_code=definition_code,
        capability_codes=[definition_code],
        perceived_outcome_cn=outcome,
        investment_decisions=decisions,
        parameter_group_results=parameter_results or [],
        direct_market_results=direct_results,
        value_conclusion=SimpleNamespace(
            status="conclusion_available",
            evidence_refs=[_evidence(f"value-{definition_code}", "SPV51")],
        ),
    )


def _parameter_fact(
    parameter_code: str,
    value: Any,
    *,
    category_code: str = "TV",
) -> SimpleNamespace:
    return SimpleNamespace(
        parameter_code=parameter_code,
        normalized_value=value,
        value_text=str(value),
        numeric_value=None,
        evidence_ids=[f"ev-{parameter_code}"],
        source_snapshot_ref=f"snapshot-{category_code}",
        source_snapshot_result_hash=f"sha256:snapshot-{category_code}",
    )


def test_game_claim_remains_original_and_value_theme_stays_internal() -> None:
    source = _source_fact(
        claim_code="tv_claim_gaming_low_latency",
        claim_name="游戏/低延迟",
        raw_claim_text=GAME_CLAIM,
        primary_params=["declared_refresh_rate_hz"],
        supporting_params=["hdmi21_port_count"],
    )
    gaming = _value(
        definition_code="tv_gaming_motion_fluency",
        outcome="游戏操作响应更快，高速画面更流畅。",
        decisions=[
            _decision("tv_gaming_motion_fluency", "unconverted"),
            _decision("param:hdmi21_port_count", "table_stake"),
        ],
        parameter_results=[
            _parameter_result(
                "declared_refresh_rate_hz",
                core_highlight_eligible=True,
                target_value="300",
            )
        ],
    )

    result = build_layered_sellpoint_analysis(
        category_code="TV",
        target_sku_code="TV00029112",
        source_sellpoints=_source_result([source]),
        values=[gaming],
        target_parameter_facts=[
            _parameter_fact("declared_refresh_rate_hz", "300"),
            _parameter_fact("hdmi21_port_count", "4"),
        ],
    )

    assert result.source_sellpoints[0].raw_claim_text == GAME_CLAIM
    assert result.source_sellpoints[0].exact_quote_cn == "游戏影音双丝滑"
    assessment = result.sellpoint_assessments[0]
    assert (
        assessment.classification
        == SellpointClassification.USER_UNRECOGNIZED_SELLPOINT
    )
    assert assessment.normalized_claim_code == "tv_claim_gaming_low_latency"
    assert assessment.value_bundle_codes == [
        "bundle-tv_gaming_motion_fluency"
    ]
    value_link = result.sellpoint_user_value_links[0]
    assert value_link.internal_value_theme_codes == [
        "tv_gaming_motion_fluency"
    ]
    assert all(
        row.normalized_claim_code != "tv_gaming_motion_fluency"
        for row in result.sellpoint_assessments
    )
    assert (
        result.integrity.value_theme_as_sellpoint_count
        == result.integrity.parameter_as_sellpoint_count
        == result.integrity.unsourced_sellpoint_count
        == 0
    )


def test_table_stake_with_source_claim_is_basic_sellpoint_and_parameter() -> None:
    source = _source_fact(
        claim_code="tv_claim_miniled_display",
        claim_name="MiniLED 显示/背光",
        raw_claim_text="【核心定位】65英寸Mini LED电视，呈现专业画质。",
        primary_params=["mini_led_flag"],
    )
    picture = _value(
        definition_code="tv_bright_room_dark_detail",
        outcome="明亮环境画面清楚，暗场层次更完整。",
        decisions=[
            _decision("tv_bright_room_dark_detail", "retain"),
            _decision("param:mini_led_flag", "table_stake"),
        ],
    )

    result = build_layered_sellpoint_analysis(
        category_code="TV",
        target_sku_code="TV00029112",
        source_sellpoints=_source_result([source]),
        values=[picture],
        target_parameter_facts=[_parameter_fact("mini_led_flag", True)],
    )

    assert (
        result.sellpoint_assessments[0].classification
        == SellpointClassification.BASIC_SELLPOINT
    )
    assert (
        result.parameter_assessments[0].classification
        == ParameterClassification.BASIC_PARAMETER
    )


def test_table_stake_without_source_claim_remains_basic_parameter_only() -> None:
    picture = _value(
        definition_code="tv_bright_room_dark_detail",
        outcome="明亮环境画面清楚。",
        decisions=[_decision("param:mini_led_flag", "table_stake")],
    )

    result = build_layered_sellpoint_analysis(
        category_code="TV",
        target_sku_code="TV00029112",
        source_sellpoints=_source_result([]),
        values=[picture],
        target_parameter_facts=[_parameter_fact("mini_led_flag", True)],
    )

    assert result.sellpoint_assessments == []
    assert result.sellpoint_parameter_links == []
    assert result.parameter_assessments[0].parameter_code == "mini_led_flag"
    assert (
        result.parameter_assessments[0].classification
        == ParameterClassification.BASIC_PARAMETER
    )


def test_parameter_gap_does_not_create_a_sellpoint_opportunity() -> None:
    color = _value(
        definition_code="tv_color_picture_truth",
        outcome="颜色更真实。",
        decisions=[
            _decision("param:quantum_dot_flag", "missing_competitive_gap")
        ],
    )

    result = build_layered_sellpoint_analysis(
        category_code="TV",
        target_sku_code="TV00029112",
        source_sellpoints=_source_result([]),
        values=[color],
        target_parameter_facts=[_parameter_fact("quantum_dot_flag", False)],
    )

    assert result.competitor_sellpoint_findings == []
    assert (
        result.parameter_assessments[0].classification
        == ParameterClassification.PARAMETER_GAP
    )


def test_competitor_opportunity_requires_a_source_sellpoint_and_three_signals() -> (
    None
):
    competitor_claim = _source_fact(
        claim_code="tv_claim_qd_miniled_display",
        claim_name="量子点 MiniLED 显示",
        raw_claim_text="量子点MiniLED带来更丰富的色彩层次。",
        fact_id="competitor-claim-1",
    )
    observation = CompetitorSellpointObservation(
        candidate_sku_code="TV-C01",
        source_sellpoint=competitor_claim,
        target_has_matching_sellpoint=False,
        competitor_value_advantage=True,
        target_value_weakness=True,
        market_support=True,
        linked_value_bundle_codes=["bundle-color"],
        evidence_refs=[_evidence("comparison-1", "COMPETITOR")],
    )

    result = build_layered_sellpoint_analysis(
        category_code="TV",
        target_sku_code="TV00029112",
        source_sellpoints=_source_result([]),
        values=[],
        target_parameter_facts=[],
        competitor_sellpoints=[observation],
    )

    assert len(result.competitor_sellpoint_findings) == 1
    assert (
        result.competitor_sellpoint_findings[0].finding_type
        == CompetitorSellpointFindingType.SELLPOINT_OPPORTUNITY
    )


def test_ac_claim_maps_only_to_ac_user_value_definition() -> None:
    source = _source_fact(
        claim_code="ac_claim_quiet_sleep",
        claim_name="静音睡眠",
        raw_claim_text="低噪运行，夜间睡眠更安静。",
        primary_params=["indoor_noise_db"],
    )
    quiet = _value(
        definition_code="ac_sleep_quiet_comfort",
        outcome="夜间运行更安静，不打扰睡眠。",
        decisions=[_decision("ac_sleep_quiet_comfort", "retain")],
    )

    result = build_layered_sellpoint_analysis(
        category_code="AC",
        target_sku_code="AC0001",
        source_sellpoints=_source_result([source], category_code="AC"),
        values=[quiet],
        target_parameter_facts=[
            _parameter_fact("indoor_noise_db", "18", category_code="AC")
        ],
    )

    assert result.sellpoint_user_value_links[0].internal_value_theme_codes == [
        "ac_sleep_quiet_comfort"
    ]
    assert all(
        not code.startswith("tv_")
        for row in result.sellpoint_user_value_links
        for code in row.internal_value_theme_codes
    )
