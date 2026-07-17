from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_market_comparison import (
    calculate_direct_market_comparison,
    calculate_parameter_group_comparison,
    calculate_parameter_group_comparisons,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    DirectMarketComparisonInput,
    MarketComparatorObservation,
    ParameterGroupComparisonInput,
    ParameterValueObservation,
    QuestionCandidateUse,
    CompetitorProfileSkuMarketFacts,
)


def _evidence(code: str) -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code="M07",
        record_type="sku_market_profile",
        record_id=code,
        result_hash=f"hash-{code}",
    )


def _use(
    code: str,
    *,
    source_type: str = "competitor",
    selected: bool = True,
) -> QuestionCandidateUse:
    return QuestionCandidateUse(
        candidate_sku_code=code,
        source_type=source_type,
        selected=selected,
        usable_dimensions=["market_price", "weekly_sales"] if selected else [],
        unavailable_dimensions=[] if selected else ["market_price", "weekly_sales"],
        selection_reasons=["value_comparable"] if selected else [],
        rejection_reasons=[] if selected else ["value_anchor_unavailable"],
        evidence_refs=[_evidence(f"use-{source_type}-{code}")],
    )


def _market(
    code: str,
    *,
    category_code: str = "TV",
    price: Decimal | None = Decimal("5000"),
    sales: Decimal | None = Decimal("50"),
) -> CompetitorProfileSkuMarketFacts:
    return CompetitorProfileSkuMarketFacts(
        sku_code=code,
        product_category=category_code,
        weighted_price=price,
        avg_weekly_sales_volume=sales,
    )


def _market_observation(
    code: str,
    *,
    category_code: str = "TV",
    source_type: str = "competitor",
    selected: bool = True,
    price: Decimal | None = Decimal("5000"),
    sales: Decimal | None = Decimal("50"),
) -> MarketComparatorObservation:
    return MarketComparatorObservation(
        category_code=category_code,
        candidate_use=_use(code, source_type=source_type, selected=selected),
        market=_market(
            code,
            category_code=category_code,
            price=price,
            sales=sales,
        ),
        evidence_refs=[_evidence(f"market-{source_type}-{code}")],
    )


def _direct_input(
    comparators: list[MarketComparatorObservation],
    *,
    category_code: str = "TV",
    target_price: Decimal | None = Decimal("6000"),
    target_sales: Decimal | None = Decimal("40"),
) -> DirectMarketComparisonInput:
    return DirectMarketComparisonInput(
        project_id="project-1",
        category_code=category_code,
        target_sku_code=f"{category_code}-TARGET",
        value_bundle_code="VALUE-1",
        target_market=_market(
            f"{category_code}-TARGET",
            category_code=category_code,
            price=target_price,
            sales=target_sales,
        ),
        comparators=comparators,
        target_evidence_refs=[_evidence(f"target-{category_code}")],
    )


def _parameter_observation(
    code: str,
    value: str | None,
    *,
    category_code: str = "TV",
    source_type: str = "competitor",
    selected: bool = True,
    price: Decimal | None = Decimal("5000"),
    sales: Decimal | None = Decimal("50"),
) -> ParameterValueObservation:
    return ParameterValueObservation(
        category_code=category_code,
        sku_code=code,
        source_type=source_type,
        normalized_value=value,
        weighted_price=price,
        avg_weekly_sales_volume=sales,
        candidate_use=_use(code, source_type=source_type, selected=selected),
        evidence_refs=[_evidence(f"parameter-{source_type}-{code}")],
    )


def _parameter_input(
    comparators: list[ParameterValueObservation],
    *,
    category_code: str = "TV",
    parameter_code: str = "refresh_rate_hz",
    parameter_name_cn: str = "刷新率",
    target_value: str | None = "120",
    target_price: Decimal | None = Decimal("6000"),
    target_sales: Decimal | None = Decimal("40"),
    exclude_from_core_sellpoints: bool = False,
) -> ParameterGroupComparisonInput:
    target_code = f"{category_code}-TARGET"
    return ParameterGroupComparisonInput(
        project_id="project-1",
        category_code=category_code,
        target_sku_code=target_code,
        value_bundle_code="VALUE-1",
        parameter_code=parameter_code,
        parameter_name_cn=parameter_name_cn,
        unit="Hz" if parameter_code == "refresh_rate_hz" else None,
        target=ParameterValueObservation(
            category_code=category_code,
            sku_code=target_code,
            source_type="target",
            normalized_value=target_value,
            weighted_price=target_price,
            avg_weekly_sales_volume=target_sales,
            evidence_refs=[_evidence(f"parameter-target-{category_code}")],
        ),
        comparators=comparators,
        exclude_from_core_sellpoints=exclude_from_core_sellpoints,
    )


def test_single_comparator_produces_price_and_sales_market_result() -> None:
    result = calculate_direct_market_comparison(
        _direct_input([_market_observation("TV-C1")])
    )

    assert result.status == "conclusion_available"
    assert result.strength == "single"
    assert result.comparator_count == 1
    assert result.price_comparison is not None
    assert result.price_comparison.gap_abs == Decimal("1000.0000")
    assert result.price_comparison.gap_pct == Decimal("0.200000")
    assert result.price_comparison.direction == "target_higher"
    assert result.sales_comparison is not None
    assert result.sales_comparison.gap_abs == Decimal("-10.000000")
    assert result.causal_claim is False
    assert result.review_required is False


@pytest.mark.parametrize(
    ("count", "strength"),
    [(2, "small_group"), (4, "small_group"), (5, "group")],
)
def test_direct_market_strength_uses_all_available_comparators(
    count: int,
    strength: str,
) -> None:
    result = calculate_direct_market_comparison(
        _direct_input(
            [
                _market_observation(
                    f"TV-C{index}",
                    price=Decimal(5000 + index * 100),
                    sales=Decimal(30 + index),
                )
                for index in range(1, count + 1)
            ]
        )
    )

    assert result.comparator_count == count
    assert result.strength == strength


def test_missing_metric_skips_only_that_candidate_metric() -> None:
    result = calculate_direct_market_comparison(
        _direct_input(
            [
                _market_observation("TV-C1", price=None, sales=Decimal("60")),
                _market_observation("TV-C2", price=Decimal("5500"), sales=None),
            ]
        )
    )

    assert result.status == "conclusion_available"
    assert result.strength == "single"
    assert result.price_comparison is not None
    assert result.price_comparison.comparator_sku_codes == ["TV-C2"]
    assert result.price_comparison.strength == "single"
    assert result.sales_comparison is not None
    assert result.sales_comparison.comparator_sku_codes == ["TV-C1"]
    assert result.sales_comparison.strength == "single"
    by_code = {row.candidate_sku_code: row for row in result.candidate_dispositions}
    assert by_code["TV-C1"].used_metrics == ["weekly_sales"]
    assert by_code["TV-C1"].skip_reasons == ["candidate_price_missing"]
    assert by_code["TV-C2"].used_metrics == ["price"]
    assert by_code["TV-C2"].skip_reasons == ["candidate_weekly_sales_missing"]


def test_missing_one_target_metric_is_partial_not_no_conclusion() -> None:
    result = calculate_direct_market_comparison(
        _direct_input(
            [_market_observation("TV-C1")],
            target_sales=None,
        )
    )

    assert result.status == "partial_conclusion"
    assert result.price_comparison is not None
    assert result.sales_comparison is None
    assert result.review_required is False


def test_same_sku_in_two_pools_is_counted_once_with_competitor_precedence() -> None:
    result = calculate_direct_market_comparison(
        _direct_input(
            [
                _market_observation("TV-C1", source_type="market_reference"),
                _market_observation("TV-C1", source_type="competitor"),
            ]
        )
    )

    assert result.used_comparator_sku_codes == ["TV-C1"]
    assert result.comparator_count == 1
    reference = next(
        row
        for row in result.candidate_dispositions
        if row.source_type == "market_reference"
    )
    assert reference.used_metrics == []
    assert reference.skip_reasons == ["duplicate_sku_identity_not_counted"]


def test_rejected_or_empty_market_candidates_return_no_conclusion_without_review() -> (
    None
):
    result = calculate_direct_market_comparison(
        _direct_input(
            [
                _market_observation("TV-C1", selected=False),
                _market_observation("TV-C2", price=None, sales=None),
            ]
        )
    )

    assert result.status == "no_conclusion"
    assert result.strength == "none"
    assert result.review_required is False
    assert "no comparator" not in result.business_conclusion_cn.lower()


def test_direct_market_result_is_deterministic_across_input_order() -> None:
    rows = [
        _market_observation("TV-C2", price=Decimal("5200")),
        _market_observation("TV-C1", price=Decimal("5100")),
    ]

    first = calculate_direct_market_comparison(_direct_input(rows))
    second = calculate_direct_market_comparison(_direct_input(list(reversed(rows))))

    assert first == second
    assert first.evidence_refs == sorted(
        first.evidence_refs,
        key=lambda row: (
            row.module_code,
            row.record_type,
            row.record_id,
            row.result_hash,
        ),
    )


def test_direct_market_input_rejects_cross_category_comparator() -> None:
    with pytest.raises(ValidationError, match="stay within category"):
        _direct_input(
            [_market_observation("AC-C1", category_code="AC")],
            category_code="TV",
        )


def test_parameter_groups_keep_every_actual_value_without_ordinal_tiers() -> None:
    result = calculate_parameter_group_comparison(
        _parameter_input(
            [
                _parameter_observation(
                    "TV-C60", "60", price=Decimal("4000"), sales=Decimal("80")
                ),
                _parameter_observation(
                    "TV-C120", "120", price=Decimal("5500"), sales=Decimal("45")
                ),
                _parameter_observation(
                    "TV-C144", "144", price=Decimal("6500"), sales=Decimal("30")
                ),
            ]
        )
    )

    assert result.status == "conclusion_available"
    assert result.distinct_values == ["120", "144", "60"]
    assert {row.normalized_value for row in result.groups} == {"60", "120", "144"}
    by_value = {row.normalized_value: row for row in result.groups}
    assert by_value["60"].sales_gap_to_target_group == Decimal("37.500000")
    assert by_value["144"].price_gap_to_target_group == Decimal("750.0000")
    assert "ordinal_tiers_not_required" in result.limitations


def test_single_different_parameter_value_is_directional_and_usable() -> None:
    result = calculate_parameter_group_comparison(
        _parameter_input([_parameter_observation("TV-C1", "60")])
    )

    assert result.status == "conclusion_available"
    assert result.strength == "directional"
    assert result.different_value_comparator_count == 1


def test_missing_parameter_value_skips_only_that_row() -> None:
    result = calculate_parameter_group_comparison(
        _parameter_input(
            [
                _parameter_observation("TV-C1", None),
                _parameter_observation("TV-C2", "60"),
            ]
        )
    )

    assert result.different_value_comparator_count == 1
    by_code = {row.candidate_sku_code: row for row in result.candidate_dispositions}
    assert by_code["TV-C1"].used is False
    assert by_code["TV-C1"].skip_reasons == ["parameter_value_missing"]
    assert by_code["TV-C2"].used is True


def test_parameter_group_keeps_partial_market_metrics() -> None:
    result = calculate_parameter_group_comparison(
        _parameter_input(
            [
                _parameter_observation(
                    "TV-C1",
                    "60",
                    price=None,
                    sales=Decimal("80"),
                )
            ],
            target_price=None,
        )
    )

    assert result.status == "partial_conclusion"
    alternative = next(row for row in result.groups if row.normalized_value == "60")
    assert alternative.price_gap_to_target_group is None
    assert alternative.sales_gap_to_target_group == Decimal("40.000000")
    assert "parameter_price_group_comparison_unavailable" in result.limitations


def test_confirmed_table_stake_is_not_core_highlight_but_still_calculated() -> None:
    hdmi = calculate_parameter_group_comparison(
        _parameter_input(
            [_parameter_observation("TV-C1", "2.0")],
            parameter_code="hdmi_2_1",
            parameter_name_cn="HDMI 2.1",
            target_value="2.1",
            exclude_from_core_sellpoints=True,
        )
    )
    refresh_rate = calculate_parameter_group_comparison(
        _parameter_input(
            [_parameter_observation("TV-C2", "60")],
            parameter_code="refresh_rate_hz",
            parameter_name_cn="刷新率",
        )
    )

    assert hdmi.status == "conclusion_available"
    assert hdmi.core_highlight_eligible is False
    assert "confirmed_table_stake_not_core_highlight" in hdmi.limitations
    assert refresh_rate.status == "conclusion_available"
    assert refresh_rate.core_highlight_eligible is True


def test_same_parameter_value_or_missing_target_returns_local_no_conclusion() -> None:
    same = calculate_parameter_group_comparison(
        _parameter_input([_parameter_observation("TV-C1", "120")])
    )
    missing_target = calculate_parameter_group_comparison(
        _parameter_input(
            [_parameter_observation("TV-C1", "60")],
            target_value=None,
        )
    )

    assert same.status == "no_conclusion"
    assert same.review_required is False
    assert missing_target.status == "no_conclusion"
    assert missing_target.review_required is False
    assert "target_parameter_value_missing" in missing_target.limitations


def test_parameter_batch_is_deterministic_and_keeps_tv_ac_isolated() -> None:
    tv = _parameter_input([_parameter_observation("TV-C1", "60")])
    ac = _parameter_input(
        [
            _parameter_observation(
                "AC-C1",
                "2匹",
                category_code="AC",
                price=Decimal("4000"),
                sales=Decimal("20"),
            )
        ],
        category_code="AC",
        parameter_code="horsepower",
        parameter_name_cn="匹数",
        target_value="1.5匹",
    )

    first = calculate_parameter_group_comparisons([tv, ac])
    second = calculate_parameter_group_comparisons([ac, tv])

    assert first == second
    assert [(row.category_code, row.parameter_code) for row in first] == [
        ("AC", "horsepower"),
        ("TV", "refresh_rate_hz"),
    ]


def test_parameter_input_rejects_cross_category_observation() -> None:
    with pytest.raises(ValidationError, match="stay within category"):
        _parameter_input(
            [_parameter_observation("AC-C1", "2匹", category_code="AC")],
            category_code="TV",
        )
