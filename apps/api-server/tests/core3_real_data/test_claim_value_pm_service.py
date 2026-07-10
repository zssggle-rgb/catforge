from __future__ import annotations

from copy import deepcopy

from app.services.core3_real_data.analyst.claim_value_pm_schemas import (
    ClaimValuePmCommentAtom,
    ClaimValuePmCompetitorSnapshot,
    ClaimValuePmContext,
    ClaimValuePmMarketWeeklyRow,
)
from app.services.core3_real_data.analyst.claim_value_pm_service import (
    TV_VALUE_UNITS,
    analyze_sellpoint_value_pm,
    attribute_comment_atoms,
    build_data_gate,
    build_market_pricing,
    build_pair_curve,
    choice_share_crossing,
    evaluate_choice_curve,
    pava_nonincreasing,
    _fact_relation,
)


def _atom(text: str, *, subdimension: str = "picture_clarity_resolution", polarity: str = "positive") -> ClaimValuePmCommentAtom:
    return ClaimValuePmCommentAtom(
        source_comment_key=f"comment-{abs(hash((text, subdimension)))}",
        sentence_seq=1,
        clean_comment_text=text,
        dimension_code="picture_screen_experience",
        subdimension_code=subdimension,
        dimension_type="product_experience",
        polarity=polarity,
        support_relation="supports_sku_param_claim" if polarity == "positive" else "contradicts_sku_param_claim",
        supported_claim_codes=["tv_claim_miniled_display"] if polarity == "positive" else [],
        contradicted_claim_codes=["tv_claim_miniled_display"] if polarity != "positive" else [],
        evidence_ids=[f"ev-{abs(hash(text))}"],
        confidence=0.9,
    )


def _fact_brief(*, broken_claim: bool = False) -> dict:
    return {
        "sku": {"sku_code": "TV00029112", "brand_name": "海信", "model_name": "65E7Q"},
        "sections": {
            "parameter_fact": {
                "summary": {"conflict_count": 0},
                "core_params": {
                    "picture": {
                        "screen_size_inch": {"normalized_value": 65},
                        "mini_led_flag": {"normalized_value": True},
                        "declared_brightness_nit_or_band": {"normalized_value": {"value": 5200, "unit": "nits"}},
                        "local_dimming_zone_count": {"normalized_value": 1920},
                        "quantum_dot_flag": {"normalized_value": False},
                        "wide_color_gamut_pct": {"normalized_value": 98},
                    },
                    "gaming": {
                        "refresh_rate_hz": {"normalized_value": 300},
                        "hdmi21_port_count": {"normalized_value": 2},
                    },
                    "system": {
                        "processor_chip_model": {"normalized_value": "MT9655"},
                        "memory_capacity_gb": {"normalized_value": 4},
                        "speaker_power_w": {"normalized_value": 20},
                    },
                    "audio": {"dolby_audio_flag": {"normalized_value": True}},
                    "eye_care": {
                        "low_blue_light_flag": {"normalized_value": True},
                        "flicker_free_flag": {"normalized_value": True},
                    },
                },
            },
            "claim_fact": {
                "summary": {"matched_claim_count": 13, "fact_claim_count": 0 if broken_claim else 3},
                "fact_claim_codes": [] if broken_claim else ["tv_claim_miniled_display", "tv_claim_hdr_high_brightness", "tv_claim_local_dimming"],
                "quality_flags": ["m03b_param_profile_missing"] if broken_claim else [],
            },
            "comment_fact": {"summary": {"comment_sentence_count": 3}},
            "market": {"market_metrics": {"price_wavg": 6999}, "market_position": {"screen_size_inch": 65, "price_percentile_in_size": 0.7}},
            "user_task": {"primary": "TASK_PREMIUM_PICTURE_EXPERIENCE"},
            "target_group": {"primary": "TG_PREMIUM_AV_ENTHUSIAST"},
            "value_battlefield": {"primary": "BF_PREMIUM_PICTURE_UPGRADE"},
            "semantic_dimension_positions": [{"dimension_code": "BF_PREMIUM_PICTURE_UPGRADE"}],
        },
        "evidence_sources": [],
    }


def _context(*, broken_claim: bool = False, atoms: list[ClaimValuePmCommentAtom] | None = None) -> ClaimValuePmContext:
    return ClaimValuePmContext(
        project_id="core3_mvp",
        category_code="TV",
        batch_id="batch-test",
        product_category="TV",
        market_window="full_observed_window",
        target={"sku_code": "TV00029112", "brand_name": "海信", "model_name": "65E7Q"},
        fact_brief=_fact_brief(broken_claim=broken_claim),
        comment_atoms=atoms or [],
        market_weekly_rows=[],
        competitors=[],
    )


def _weekly_rows(sku_code: str, *, target: bool) -> list[ClaimValuePmMarketWeeklyRow]:
    gaps = [-0.08, -0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.08]
    rows: list[ClaimValuePmMarketWeeklyRow] = []
    for week, gap in enumerate(gaps, start=1):
        competitor_price = 5000.0
        if target:
            price = competitor_price * (1 + gap)
            share = 0.62 - 1.5 * gap
            sales = 100 * share / (1 - share)
        else:
            price = competitor_price
            sales = 100.0
        rows.append(
            ClaimValuePmMarketWeeklyRow(
                sku_code=sku_code,
                period_week_index=week,
                platform_type="jd",
                sales_volume=sales,
                sales_amount=sales * price,
                avg_price=price,
                price_check_status="ok",
                evidence_ids=[f"ev-{sku_code}-{week}"],
            )
        )
    return rows


def _competitor_snapshot(sku_code: str, *, size: int = 65, weak: bool = False) -> ClaimValuePmCompetitorSnapshot:
    fact = deepcopy(_fact_brief())
    fact["sku"] = {"sku_code": sku_code, "brand_name": "竞品", "model_name": sku_code}
    fact["sections"]["market"]["market_position"]["screen_size_inch"] = size
    fact["sections"]["parameter_fact"]["core_params"]["picture"]["screen_size_inch"]["normalized_value"] = size
    rows = _weekly_rows(sku_code, target=False)
    if weak:
        rows = rows[:4]
    return ClaimValuePmCompetitorSnapshot(
        sku_code=sku_code,
        brand_name="竞品",
        model_name=sku_code,
        selection_rank=1,
        slot_code="primary_direct",
        slot_name_cn="首选直接竞品",
        selection_confidence=0.9,
        evidence_completeness_score=0.9,
        selection_source="M14",
        fact_brief=fact,
        market_weekly_rows=rows,
    )


def test_generic_picture_praise_is_not_direct_miniled_evidence() -> None:
    definition = TV_VALUE_UNITS[0]
    result = attribute_comment_atoms(definition, [_atom("画质很好，非常清晰")], eligible_sentence_count=1)

    assert result.status == "unrecognized"
    assert result.direct_sentence_count == 0
    assert result.indirect_sentence_count == 0
    assert result.unattributable_sentence_count == 1
    assert result.perception_weight == 0


def test_concrete_bright_room_outcome_supports_bundle_but_not_single_parameter() -> None:
    definition = TV_VALUE_UNITS[0]
    result = attribute_comment_atoms(definition, [_atom("白天阳光照进客厅也看得清，不发灰")], eligible_sentence_count=1)

    assert result.status == "outcome_only"
    assert result.direct_sentence_count == 0
    assert result.indirect_sentence_count == 1
    assert result.perception_weight == 0.5


def test_brightness_comment_is_not_misread_as_eye_care_evidence() -> None:
    definition = next(item for item in TV_VALUE_UNITS if item.code == "tv_long_viewing_comfort")
    result = attribute_comment_atoms(
        definition,
        [_atom("声音也大，亮度也高", subdimension="picture_brightness_hdr")],
        eligible_sentence_count=1,
    )

    assert result.direct_sentence_count == 0
    assert result.indirect_sentence_count == 0
    assert result.status == "unrecognized"


def test_direct_parameter_and_negative_experience_are_kept_separate() -> None:
    definition = TV_VALUE_UNITS[0]
    result = attribute_comment_atoms(
        definition,
        [
            _atom("5200nit亮度，暗场层次很清楚"),
            _atom("暗场漏光和光晕很明显", polarity="negative"),
        ],
        eligible_sentence_count=2,
    )

    assert result.status == "mixed"
    assert result.direct_sentence_count == 1
    assert result.negative_sentence_count == 1
    assert len(result.positive_examples) == 1
    assert len(result.negative_examples) == 1


def test_m03b_m04c_conflict_blocks_sellpoint_attribution() -> None:
    gate = build_data_gate(_context(broken_claim=True, atoms=[_atom("画质很好")]))

    codes = {issue.code for issue in gate.issues}
    assert gate.status == "partial"
    assert gate.status_cn == "数据需修复，卖点结论暂停"
    assert "m03b_m04c_presence_conflict" in codes
    assert "m04c_all_claims_unresolved" in codes
    assert gate.review_required is True


def test_pava_curve_is_non_increasing_and_does_not_extrapolate() -> None:
    curve = pava_nonincreasing(
        [
            (-0.10, 0.65, 10),
            (0.00, 0.55, 10),
            (0.05, 0.60, 10),
            (0.10, 0.40, 10),
        ]
    )

    assert all(left[1] >= right[1] for left, right in zip(curve, curve[1:]))
    assert evaluate_choice_curve(curve, -0.11, observed_min=-0.10, observed_max=0.10) is None
    assert evaluate_choice_curve(curve, 0.11, observed_min=-0.10, observed_max=0.10) is None
    assert evaluate_choice_curve(curve, 0.0, observed_min=-0.10, observed_max=0.10) is not None


def test_choice_crossing_is_only_found_inside_observed_range() -> None:
    curve = [(-0.05, 0.65, 10), (0.0, 0.60, 10), (0.05, 0.50, 10), (0.10, 0.40, 10)]

    crossing = choice_share_crossing(curve, threshold=0.5, start_gap=0.0, observed_min=-0.05, observed_max=0.10)

    assert crossing == 0.05
    assert choice_share_crossing(curve, threshold=0.5, start_gap=0.11, observed_min=-0.05, observed_max=0.10) is None


def test_pair_curve_calculates_same_price_advantage_and_holding_gap() -> None:
    result = build_pair_curve(
        _weekly_rows("TV-TARGET", target=True),
        _weekly_rows("TV-COMP", target=False),
        competitor_sku_code="TV-COMP",
        competitor_name="竞品A",
        selection_confidence=0.9,
        evidence_completeness_score=0.9,
    )

    assert result.sample_level == "strong"
    assert result.valid_cell_count == 8
    assert result.same_price_share is not None and result.same_price_share > 0.6
    assert result.same_price_advantage_pp is not None and result.same_price_advantage_pp > 10
    assert result.hold_gap_ratio is not None and 0.07 <= result.hold_gap_ratio <= 0.09
    assert result.hold_gap_amount is not None and 350 <= result.hold_gap_amount <= 450


def test_full_analysis_keeps_generic_comments_out_of_technical_weight() -> None:
    result = analyze_sellpoint_value_pm(_context(atoms=[_atom("好高清，画面很清晰")]))
    bright = next(item for item in result["value_units"] if item["unit_code"] == "tv_bright_room_dark_detail")

    assert result["schema_version"] == "sellpoint_value_pm_v1"
    assert bright["user_understanding"]["direct_sentence_count"] == 0
    assert bright["user_understanding"]["unattributable_sentence_count"] == 1
    assert "same_price_choice_weight" not in bright["weights"]
    assert bright["weights"]["pricing_readiness"] == "insufficient"
    assert not result["market_pricing"]["selection_holding_gap_amount_range"]


def test_missing_market_blocks_pricing_but_does_not_turn_product_fact_into_conflict() -> None:
    context = _context(atoms=[_atom("画质很好")])
    fact = deepcopy(context.fact_brief)
    fact["sections"].pop("market")
    context = context.model_copy(update={"fact_brief": fact})

    result = analyze_sellpoint_value_pm(context)
    bright = next(item for item in result["value_units"] if item["unit_code"] == "tv_bright_room_dark_detail")

    assert result["data_gate"]["status"] == "blocked"
    assert bright["product_fact_status"] == "confirmed"
    assert bright["product_fact_status"] != "conflict"


def test_product_fact_blocker_keeps_l3_market_as_observation_without_price_action() -> None:
    context = _context(broken_claim=True).model_copy(
        update={
            "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
            "competitors": [
                _competitor_snapshot("TV-EXACT-1"),
                _competitor_snapshot("TV-EXACT-2"),
                _competitor_snapshot("TV-EXACT-3"),
            ],
        }
    )

    result = analyze_sellpoint_value_pm(context)

    assert result["market_pricing"]["method_level"] == "L3"
    assert result["data_gate"]["status_cn"] == "数据需修复，卖点结论暂停"
    assert all(item["action_type"] != "价格验证" for item in result["decision_summary"])
    assert [item["action_type"] for item in result["test_backlog"]] == ["先修数据"]


def test_mixed_user_feedback_is_not_promoted_to_keep_and_strengthen() -> None:
    context = _context(
        atoms=[
            _atom("5200nit亮度，暗场层次很清楚"),
            _atom("暗场漏光和光晕很明显", polarity="negative"),
        ]
    )

    result = analyze_sellpoint_value_pm(context)
    bright = next(item for item in result["value_units"] if item["unit_code"] == "tv_bright_room_dark_detail")

    assert bright["user_understanding"]["status"] == "mixed"
    assert bright["purchase_role"]["status"] == "mixed_experience"
    assert bright["decision_code"] == "FIX_EXPERIENCE"
    assert "保留并做强" not in bright["decision_cn"]


def test_post_purchase_experience_and_direct_purchase_reason_are_separate() -> None:
    post_purchase = analyze_sellpoint_value_pm(
        _context(atoms=[_atom("白天阳光照进客厅也看得清，不发灰")])
    )
    direct_reason = analyze_sellpoint_value_pm(
        _context(atoms=[_atom("就是因为白天阳光照进来还能看得清才买的")])
    )

    post_unit = next(item for item in post_purchase["value_units"] if item["unit_code"] == "tv_bright_room_dark_detail")
    direct_unit = next(item for item in direct_reason["value_units"] if item["unit_code"] == "tv_bright_room_dark_detail")
    assert post_unit["purchase_role"]["status"] == "post_purchase_satisfaction"
    assert post_unit["purchase_role"]["status_cn"] == "已形成购后体验，尚未证明影响选购"
    assert direct_unit["purchase_role"]["status"] == "direct_reason"
    assert direct_unit["user_understanding"]["direct_choice_sentence_count"] == 1


def test_two_weak_pairs_do_not_upgrade_to_l2() -> None:
    context = _context().model_copy(
        update={
            "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
            "competitors": [
                _competitor_snapshot("TV-WEAK-1", weak=True),
                _competitor_snapshot("TV-WEAK-2", weak=True),
            ],
        }
    )

    pricing = build_market_pricing(context)

    assert pricing.method_level == "L1"
    assert pricing.strong_pair_count == 0


def test_l3_matches_the_two_native_m14_price_roles_and_requires_exact_size() -> None:
    base = _context().model_copy(update={"market_weekly_rows": _weekly_rows("TV-TARGET", target=True)})
    ready = base.model_copy(
        update={
            "competitors": [
                _competitor_snapshot("TV-EXACT-1").model_copy(update={"slot_code": "direct_fight"}),
                _competitor_snapshot("TV-EXACT-2").model_copy(update={"slot_code": "price_volume_pressure"}),
            ]
        }
    )
    cross_size = base.model_copy(
        update={
            "competitors": [
                _competitor_snapshot("TV-EXACT-1").model_copy(update={"slot_code": "direct_fight"}),
                _competitor_snapshot("TV-CROSS-SIZE", size=55).model_copy(update={"slot_code": "price_volume_pressure"}),
            ]
        }
    )

    ready_pricing = build_market_pricing(ready)
    cross_size_pricing = build_market_pricing(cross_size)

    assert ready_pricing.method_level == "L3"
    assert cross_size_pricing.method_level == "L1"
    cross_pair = next(item for item in cross_size_pricing.pair_curves if item.competitor_sku_code == "TV-CROSS-SIZE")
    assert cross_pair.exact_size_match is False
    assert cross_pair.sample_level == "insufficient"
    assert "只用于配置事实观察" in cross_pair.limitations[0]


def test_current_price_scenario_uses_same_rounded_price_and_pair_set() -> None:
    context = _context().model_copy(
        update={
            "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
            "competitors": [
                _competitor_snapshot("TV-EXACT-1").model_copy(update={"slot_code": "direct_fight"}),
                _competitor_snapshot("TV-EXACT-2").model_copy(update={"slot_code": "price_volume_pressure"}),
            ],
        }
    )

    pricing = build_market_pricing(context)
    current = next(item for item in pricing.price_scenarios if item.label_cn == "当前价格")

    assert current.price == pricing.current_price
    assert current.price_change_pct == 0
    assert current.choice_index == 100
    assert current.comparison_revenue_index == 100
    assert pricing.current_price_acceptance_status in {"room_remaining", "mostly_captured", "over_captured"}
    assert pricing.current_price_acceptance_status_cn != "无法判断"


def test_real_m03b_shape_supports_system_aliases_and_native_l3() -> None:
    target_fact = deepcopy(_fact_brief())
    core = target_fact["sections"]["parameter_fact"]["core_params"]
    core.pop("audio")
    core["eye_care"] = {}
    core["system"]["ram_gb"] = core["system"].pop("memory_capacity_gb")
    core["system"]["storage_gb"] = {"normalized_value": 64}
    competitors: list[ClaimValuePmCompetitorSnapshot] = []
    for sku_code, role in (("TV-DIRECT", "direct_fight"), ("TV-PRICE", "price_volume_pressure")):
        snapshot = _competitor_snapshot(sku_code)
        competitor_fact = deepcopy(target_fact)
        competitor_fact["sku"] = {"sku_code": sku_code, "brand_name": "竞品", "model_name": sku_code}
        competitors.append(snapshot.model_copy(update={"slot_code": role, "fact_brief": competitor_fact}))
    context = _context().model_copy(
        update={
            "fact_brief": target_fact,
            "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
            "competitors": competitors,
        }
    )

    pricing = build_market_pricing(context)

    assert {item.configuration_isolation_grade for item in pricing.pair_curves} == {"A"}
    assert pricing.method_level == "L3"
    assert pricing.current_price_acceptance_status != "insufficient"


def test_pava_uses_constant_value_inside_a_merged_block() -> None:
    curve = pava_nonincreasing([(-0.1, 0.6, 1), (0.0, 0.4, 1), (0.1, 0.5, 1)])

    value = evaluate_choice_curve(curve, 0.0, observed_min=-0.1, observed_max=0.1)

    assert value == 0.45


def test_purchase_reason_is_not_spliced_across_unrelated_comment_sentences() -> None:
    result = analyze_sellpoint_value_pm(
        _context(
            atoms=[
                _atom("看中这款电视才买的"),
                _atom("5200nit亮度，暗场层次很清楚"),
            ]
        )
    )
    bright = next(item for item in result["value_units"] if item["unit_code"] == "tv_bright_room_dark_detail")

    assert bright["user_understanding"]["direct_choice_sentence_count"] == 0
    assert bright["purchase_role"]["status"] == "post_purchase_satisfaction"


def test_sparse_price_gaps_do_not_create_a_same_price_result() -> None:
    target_rows: list[ClaimValuePmMarketWeeklyRow] = []
    competitor_rows: list[ClaimValuePmMarketWeeklyRow] = []
    for week in range(1, 9):
        gap = -0.20 if week <= 4 else 0.20
        competitor_price = 5000.0
        target_price = competitor_price * (1 + gap)
        target_rows.append(
            ClaimValuePmMarketWeeklyRow(
                sku_code="TV-TARGET",
                period_week_index=week,
                platform_type="jd",
                sales_volume=120 if gap < 0 else 80,
                sales_amount=(120 if gap < 0 else 80) * target_price,
                avg_price=target_price,
                price_check_status="ok",
            )
        )
        competitor_rows.append(
            ClaimValuePmMarketWeeklyRow(
                sku_code="TV-COMP",
                period_week_index=week,
                platform_type="jd",
                sales_volume=100,
                sales_amount=100 * competitor_price,
                avg_price=competitor_price,
                price_check_status="ok",
            )
        )

    curve = build_pair_curve(
        target_rows,
        competitor_rows,
        competitor_sku_code="TV-COMP",
        competitor_name="竞品A",
        exact_size_match=True,
        configuration_isolation_grade="A",
    )

    assert curve.same_price_share is None
    assert curve.same_price_method is None
    assert any("样本空洞" in item for item in curve.limitations)


def test_non_l3_market_result_never_publishes_a_holding_gap_lower_bound() -> None:
    context = _context().model_copy(
        update={
            "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
            "competitors": [_competitor_snapshot("TV-ONLY-PAIR")],
        }
    )

    pricing = build_market_pricing(context)

    assert pricing.method_level == "L1"
    assert pricing.selection_holding_gap_amount_range == []
    assert pricing.selection_holding_gap_ratio_range == []
    assert "至少保持" not in pricing.holding_gap_status_cn


def test_benchmark_and_up_downtrade_roles_do_not_enter_the_current_price_curve() -> None:
    competitors = [
        _competitor_snapshot("TV-BENCHMARK").model_copy(update={"slot_code": "benchmark_potential"}),
        _competitor_snapshot("TV-UPTRADE").model_copy(update={"slot_code": "uptrade_alternative"}),
        _competitor_snapshot("TV-DOWNTRADE").model_copy(update={"slot_code": "downtrade_diversion"}),
    ]
    context = _context().model_copy(
        update={
            "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
            "competitors": competitors,
        }
    )

    pricing = build_market_pricing(context)

    assert pricing.method_level == "L0"
    assert pricing.valid_pair_count == 0
    assert all(item.sample_level == "insufficient" for item in pricing.pair_curves)
    assert all("只用于事实观察" in item.limitations[0] for item in pricing.pair_curves)


def test_missing_parameter_is_unknown_and_300hz_is_same_tier_as_288hz() -> None:
    definition = next(item for item in TV_VALUE_UNITS if item.code == "tv_gaming_motion_fluency")
    target_missing = deepcopy(_fact_brief())
    target_missing["sections"]["parameter_fact"]["core_params"]["gaming"] = {}
    competitor = deepcopy(_fact_brief())

    assert _fact_relation(definition, target_missing, competitor) == "unknown"

    competitor["sections"]["parameter_fact"]["core_params"]["gaming"]["refresh_rate_hz"]["normalized_value"] = 288
    assert _fact_relation(definition, _fact_brief(), competitor) == "similar"

    bright_definition = next(item for item in TV_VALUE_UNITS if item.code == "tv_bright_room_dark_detail")
    partial_competitor = deepcopy(_fact_brief())
    partial_picture = partial_competitor["sections"]["parameter_fact"]["core_params"]["picture"]
    partial_picture.pop("declared_brightness_nit_or_band")
    partial_picture.pop("local_dimming_zone_count")
    assert _fact_relation(bright_definition, _fact_brief(), partial_competitor) == "unknown"

    partial_picture["declared_brightness_nit_or_band"] = {"normalized_value": {"value": 1000, "unit": "nits"}}
    assert _fact_relation(bright_definition, _fact_brief(), partial_competitor) == "unknown"


def test_competitor_stronger_bundle_cannot_be_promoted_to_a_price_test() -> None:
    competitors: list[ClaimValuePmCompetitorSnapshot] = []
    for index in range(1, 4):
        competitor = _competitor_snapshot(f"TV-AUDIO-{index}")
        fact = deepcopy(competitor.fact_brief)
        fact["sections"]["parameter_fact"]["core_params"]["system"]["speaker_power_w"]["normalized_value"] = 60
        competitors.append(competitor.model_copy(update={"fact_brief": fact}))
    result = analyze_sellpoint_value_pm(
        _context(
            atoms=[
                _atom(
                    "就是因为杜比声场有影院感才买的",
                    subdimension="audio_quality",
                )
            ]
        ).model_copy(
            update={
                "market_weekly_rows": _weekly_rows("TV-TARGET", target=True),
                "competitors": competitors,
            }
        )
    )
    audio = next(item for item in result["value_units"] if item["unit_code"] == "tv_cinema_soundstage")

    assert result["market_pricing"]["method_level"] == "L3"
    assert audio["purchase_role"]["status"] == "direct_reason"
    assert audio["weights"]["pricing_readiness"] == "insufficient"
    assert audio["decision_code"] == "CLOSE_COMPETITOR_GAP"
