from app.services.core3_real_data.analyst.competitor_answer import (
    build_competitor_answer,
)


def test_price_nearest_candidate_with_insufficient_anchor_cannot_rank_first() -> None:
    answer = build_competitor_answer(
        target=_target(),
        target_fact_brief=_target_fact_brief(),
        competitors=[
            _competitor(
                sku_code="TV_NEAREST_LOW_ANCHOR",
                model_name="价格贴身弱锚点",
                price_gap="0.00",
                anchor_score=4,
                replacement_score=8,
                semantic_score=0.95,
            ),
            _competitor(
                sku_code="TV_STRONG_ANCHOR",
                model_name="强锚点替代",
                price_gap="0.06",
                anchor_score=13,
                replacement_score=8,
                semantic_score=0.70,
            ),
        ],
        top_n=2,
    )

    top = answer["top_competitors"]
    assert top[0]["candidate"]["sku_code"] == "TV_STRONG_ANCHOR"
    assert top[0]["role"] == "primary_direct"

    nearest = _candidate_by_code(answer, "TV_NEAREST_LOW_ANCHOR")
    assert nearest["role"] != "primary_direct"
    assert nearest["selection_gate"]["primary_direct_eligible"] is False
    assert (
        "anchor_substitutability_below_primary_threshold"
        in nearest["ranking_gate_reasons"]
    )


def test_weak_market_validation_with_deviated_purchase_pool_is_excluded_from_top3() -> (
    None
):
    answer = build_competitor_answer(
        target=_target(),
        target_fact_brief=_target_fact_brief(),
        competitors=[
            _competitor(
                sku_code="TV_DEVIATED_WEAK_MARKET",
                model_name="偏离购买池弱验证",
                price_gap="0.22",
                screen_size=75,
                size_tier="large_70_79",
                price_band="high",
                anchor_score=14,
                replacement_score=9,
                semantic_score=0.95,
                overlap_week_count=0,
                avg_weekly_sales=0,
            ),
            _competitor(
                sku_code="TV_ELIGIBLE_A",
                model_name="合格候选A",
                price_gap="0.05",
                anchor_score=13,
                replacement_score=8,
                semantic_score=0.70,
            ),
            _competitor(
                sku_code="TV_ELIGIBLE_B",
                model_name="合格候选B",
                price_gap="-0.04",
                anchor_score=11,
                replacement_score=7,
                semantic_score=0.66,
            ),
            _competitor(
                sku_code="TV_ELIGIBLE_C",
                model_name="合格候选C",
                price_gap="0.09",
                anchor_score=10,
                replacement_score=6,
                semantic_score=0.60,
            ),
        ],
        top_n=3,
    )

    top_codes = [item["candidate"]["sku_code"] for item in answer["top_competitors"]]
    assert "TV_DEVIATED_WEAK_MARKET" not in top_codes

    deviated = _candidate_by_code(answer, "TV_DEVIATED_WEAK_MARKET")
    assert deviated["business_score"] > 0
    assert deviated["top3_eligible"] is False
    assert "market_weak_and_purchase_pool_deviated" in deviated["ranking_gate_reasons"]


def test_low_replacement_pressure_blocks_direct_role_upgrade() -> None:
    answer = build_competitor_answer(
        target=_target(),
        target_fact_brief=_target_fact_brief(),
        competitors=[
            _competitor(
                sku_code="TV_LOW_PRESSURE",
                model_name="低替代压力",
                price_gap="0.06",
                anchor_score=13,
                replacement_score=4,
                semantic_score=0.95,
            ),
            _competitor(
                sku_code="TV_STRONG_PRESSURE",
                model_name="强替代压力",
                price_gap="0.08",
                anchor_score=12,
                replacement_score=7,
                semantic_score=0.70,
            ),
        ],
        top_n=2,
    )

    low_pressure = _candidate_by_code(answer, "TV_LOW_PRESSURE")
    assert low_pressure["role"] != "primary_direct"
    assert low_pressure["selection_gate"]["strong_pressure_allowed"] is False
    assert (
        "replacement_pressure_below_strong_threshold"
        in low_pressure["ranking_gate_reasons"]
    )
    assert answer["top_competitors"][0]["candidate"]["sku_code"] == "TV_STRONG_PRESSURE"


def test_candidate_blocked_by_m12d_cannot_enter_top3() -> None:
    blocked = _competitor(
        sku_code="TV_M12D_BLOCKED",
        model_name="画像不可用候选",
        price_gap="0.00",
        anchor_score=14,
        replacement_score=9,
        semantic_score=0.98,
    )
    blocked["value_anchor"]["candidate_top3_eligible"] = False  # type: ignore[index]
    answer = build_competitor_answer(
        target=_target(),
        target_fact_brief=_target_fact_brief(),
        competitors=[
            blocked,
            _competitor(
                sku_code="TV_ELIGIBLE",
                model_name="正常候选",
                price_gap="0.06",
                anchor_score=10,
                replacement_score=6,
                semantic_score=0.65,
            ),
        ],
        top_n=1,
    )

    assert answer["top_competitors"][0]["candidate"]["sku_code"] == "TV_ELIGIBLE"
    blocked_result = _candidate_by_code(answer, "TV_M12D_BLOCKED")
    assert blocked_result["top3_eligible"] is False
    assert "candidate_m12d_blocks_top3" in blocked_result["ranking_gate_reasons"]


def test_low_pressure_report_does_not_call_weak_candidate_a_threat() -> None:
    answer = build_competitor_answer(
        target=_target(),
        target_fact_brief=_target_fact_brief(),
        competitors=[
            _competitor(
                sku_code="TV_LOW_PRESSURE_REPORT",
                model_name="弱替代候选",
                price_gap="0.04",
                anchor_score=6,
                replacement_score=3,
                semantic_score=0.60,
            )
        ],
        top_n=1,
        with_report="markdown",
    )

    markdown = answer["report_payload"]["markdown"]
    assert "替代压力较弱（3/10）" in markdown
    assert "的威胁来自" not in markdown
    assert "购买阻力比较" in markdown


def _target() -> dict[str, object]:
    return {
        "sku_code": "TV_TARGET",
        "brand_name": "海信",
        "model_name": "65E7Q",
        "screen_size_inch": 65,
        "size_tier": "large_60_69",
        "price_band_in_size_tier": "mid_high",
        "price_wavg": 4999,
        "avg_weekly_sales_volume": 120,
    }


def _target_fact_brief() -> dict[str, object]:
    return {"sections": {}}


def _competitor(
    *,
    sku_code: str,
    model_name: str,
    price_gap: str,
    anchor_score: int,
    replacement_score: int,
    semantic_score: float,
    screen_size: int = 65,
    size_tier: str = "large_60_69",
    price_band: str = "mid_high",
    overlap_week_count: int = 8,
    avg_weekly_sales: int = 80,
) -> dict[str, object]:
    return {
        "candidate": {
            "sku_code": sku_code,
            "brand_name": "竞品",
            "model_name": model_name,
            "screen_size_inch": screen_size,
            "size_tier": size_tier,
            "price_band_in_size_tier": price_band,
            "price_gap_pct_to_target": price_gap,
            "avg_weekly_sales_volume": avg_weekly_sales,
        },
        "semantic_overlap": {
            "value_battlefield": {
                "weighted_overlap_score": semantic_score,
                "matched_codes": ["BF_PREMIUM_PICTURE_UPGRADE"],
            },
            "user_task": {
                "weighted_overlap_score": semantic_score,
                "matched_codes": ["TASK_HOME_CINEMA_IMMERSION"],
            },
            "target_group": {
                "weighted_overlap_score": semantic_score,
                "matched_codes": ["TG_QUALITY_FAMILY_UPGRADER"],
            },
        },
        "param_claim_overlap": {},
        "sales_overlap": {
            "overlap_week_count": overlap_week_count,
            "candidate": {"avg_weekly_sales_volume_on_overlap_weeks": avg_weekly_sales},
        },
        "value_anchor": {
            "score": anchor_score / 15,
            "shared_anchors": ["贵得值的体验升级"],
            "target_stronger_anchors": [],
            "candidate_stronger_anchors": ["画质配置解释加价"]
            if anchor_score >= 12
            else [],
            "anchor_substitutability_score": anchor_score,
            "anchor_substitutability_level": "strong"
            if anchor_score >= 13
            else "partial",
            "primary_direct_eligible": anchor_score >= 7,
            "pair_scoring_allowed": True,
        },
        "replacement_pressure": {
            "type": "value_substitution",
            "type_cn": "价值替代压力",
            "score": replacement_score / 10,
            "replacement_pressure_score": replacement_score,
            "replacement_pressure_level": "high"
            if replacement_score >= 8
            else "medium"
            if replacement_score >= 5
            else "low",
            "strong_pressure_allowed": replacement_score >= 5,
            "requires_review": replacement_score < 5,
            "reason_cn": "测试替代压力依据。",
        },
    }


def _candidate_by_code(answer: dict[str, object], sku_code: str) -> dict[str, object]:
    for item in answer["all_candidates"]:  # type: ignore[index]
        candidate = item["candidate"]  # type: ignore[index]
        if candidate["sku_code"] == sku_code:  # type: ignore[index]
            return item  # type: ignore[return-value]
    raise AssertionError(f"missing candidate {sku_code}")
