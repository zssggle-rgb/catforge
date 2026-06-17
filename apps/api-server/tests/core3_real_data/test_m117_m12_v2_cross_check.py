from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.core3_real_data.candidate_recall_service import _battlefield_overlap
from app.services.core3_real_data.dimension_sales_reconciliation_service import (
    ContributionDraft,
    _battlefield_v2_summary,
    _top_sku_contribution,
)


def test_m117_battlefield_summary_exposes_portfolio_pool_and_anchor_context() -> None:
    draft = ContributionDraft(
        allocation=SimpleNamespace(
            allocated_sales_volume=Decimal("120.0"),
            allocated_sales_amount=Decimal("680000.0"),
            allocation_weight=Decimal("0.6200"),
            allocation_confidence=Decimal("0.7800"),
        ),
        profile=SimpleNamespace(
            sku_code="TV900001",
            brand_name="海信",
            model_name="85E7Q",
        ),
        dimension=SimpleNamespace(
            evidence_level="multi_signal",
            evidence_ids=("ev-bf",),
            support_breakdown_json={
                "portfolio_role": "main_battlefield",
                "market_pool_key": "large_size|mid_price|online",
                "screen_size_class": "large_size",
                "product_anchor_score": "0.7100",
            },
        ),
        dimension_name="游戏体育流畅战场",
        is_primary=True,
    )

    top_skus = _top_sku_contribution((draft,))
    summary = _battlefield_v2_summary((draft,))

    assert top_skus[0]["market_pool_key"] == "large_size|mid_price|online"
    assert top_skus[0]["screen_size_class"] == "large_size"
    assert top_skus[0]["portfolio_role"] == "main_battlefield"
    assert top_skus[0]["product_anchor_score"] == "0.7100"
    assert summary["allocation_policy"] == "m11_v2_portfolio"
    assert summary["portfolio_role_counts"] == {"main_battlefield": 1}
    assert summary["market_pool_counts"] == {"large_size|mid_price|online": 1}
    assert summary["primary_sku_codes"] == ["TV900001"]


def test_m12_battlefield_overlap_uses_main_secondary_portfolio_weight() -> None:
    target = _bundle(
        "TV900001",
        main=[_portfolio_item("BF_GAME", 0.82, 0.7)],
        secondary=[_portfolio_item("BF_MOVIE", 0.66, 0.3)],
        opportunity=[_portfolio_item("BF_EYE", 0.58, 0)],
    )
    candidate = _bundle(
        "TV900002",
        main=[_portfolio_item("BF_GAME", 0.78, 0.65)],
        secondary=[_portfolio_item("BF_SOUND", 0.63, 0.35)],
        opportunity=[],
    )

    overlap = _battlefield_overlap(target, candidate)

    assert overlap["matched_codes"] == ["BF_GAME"]
    assert overlap["main_match"] is True
    assert overlap["opportunity_only_match"] is False
    assert overlap["overlap_score"] >= 0.62
    assert overlap["matched_items"][0]["target_allocation_weight"] == 0.7
    assert overlap["matched_items"][0]["candidate_allocation_weight"] == 0.65


def test_m12_opportunity_only_battlefield_overlap_is_weak_signal() -> None:
    target = _bundle(
        "TV900001",
        main=[_portfolio_item("BF_GAME", 0.82, 0.7)],
        secondary=[_portfolio_item("BF_MOVIE", 0.66, 0.3)],
        opportunity=[_portfolio_item("BF_EYE", 0.58, 0)],
    )
    candidate = _bundle(
        "TV900003",
        main=[_portfolio_item("BF_SOUND", 0.81, 1.0)],
        secondary=[],
        opportunity=[_portfolio_item("BF_EYE", 0.55, 0)],
    )

    overlap = _battlefield_overlap(target, candidate)

    assert overlap["matched_codes"] == ["BF_EYE"]
    assert overlap["main_match"] is False
    assert overlap["opportunity_only_match"] is True
    assert overlap["overlap_score"] < 0.3


def _bundle(
    sku_code: str,
    *,
    main: list[dict],
    secondary: list[dict],
    opportunity: list[dict],
):
    portfolio = SimpleNamespace(
        main_battlefields_json=main,
        secondary_battlefields_json=secondary,
        opportunity_battlefields_json=opportunity,
        primary_search_battlefield_codes_json=[item["battlefield_code"] for item in main],
        secondary_search_battlefield_codes_json=[item["battlefield_code"] for item in secondary],
        opportunity_monitoring_codes_json=[item["battlefield_code"] for item in opportunity],
        evidence_ids=(f"ev-{sku_code}",),
    )
    score_rows = []
    for relation_level, items in (("main", main), ("secondary", secondary), ("opportunity", opportunity)):
        for item in items:
            score_rows.append(
                SimpleNamespace(
                    battlefield_code=item["battlefield_code"],
                    battlefield_name_cn=item["battlefield_name_cn"],
                    battlefield_score=Decimal(str(item["battlefield_score"])),
                    relation_level=relation_level,
                    evidence_ids=(f"ev-{sku_code}-{item['battlefield_code']}",),
                )
            )
    return SimpleNamespace(battlefield_portfolio=portfolio, battlefield_scores=tuple(score_rows))


def _portfolio_item(code: str, score: float, allocation_weight: float) -> dict:
    return {
        "battlefield_code": code,
        "battlefield_name_cn": f"{code} 战场",
        "battlefield_score": score,
        "allocation_weight": allocation_weight,
        "market_pool_key": "large_size|mid_price|online",
        "screen_size_class": "large_size",
        "product_anchor_score": 0.72,
    }
