from decimal import Decimal

from app.services.core3_real_data import m12c_claim_value_quantification_service as m12c_service


def test_m12c_param_value_parsing_ignores_metadata_dicts() -> None:
    metadata = {
        "rule_version": "m03b_tv_param_profile_v0.1",
        "parser_version": "m03b_tv_parser_v0.1",
        "taxonomy_version": "tv_param_taxonomy_manual_v0.1",
    }

    assert m12c_service._decimal_param_value(metadata) is None
    assert m12c_service._truthy_param_value(metadata) is None
    assert m12c_service._param_value_type(metadata) == "text"


def test_m12c_support_param_codes_filters_internal_fields() -> None:
    claim = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_hdr_high_brightness",
        claim_name="HDR/高亮画质",
        claim_dimension="画质",
        claim_subtype="高亮",
        claim_kind="fact",
        param_support_status="supported",
        supporting_param_codes=("_metadata", "declared_brightness_nit_or_band"),
        supporting_param_snapshot={},
        match_score=Decimal("0.9000"),
        confidence=Decimal("0.9000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("e1",),
    )

    support_codes = m12c_service._claim_support_param_codes(claim, "tv_claim_hdr_high_brightness")

    assert "_metadata" not in support_codes
    assert support_codes[0] == "declared_brightness_nit_or_band"


def test_m12c_single_claim_group_can_quantify_with_relaxed_thresholds() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_chip_performance",
        claim_name="芯片/处理器性能",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="high_with_adjacent",
        sku_codes=("sku-a", "sku-b", "sku-c"),
        with_claim_skus=("sku-a",),
        without_claim_skus=("sku-b", "sku-c"),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
        pool_relax_level="L2",
    )
    metric = {
        "with_price_median": Decimal("5949"),
        "price_premium_abs": Decimal("1533.9000"),
        "weekly_sales_lift_abs": Decimal("-71.000000"),
        "weekly_sales_amount_lift_abs": Decimal("110000"),
        "effect_confidence": Decimal("0.5500"),
    }
    competitiveness = {
        "overall_parameter_competitiveness_level": m12c_service.M12C_PARAM_LEVEL_LEADING,
        "overall_parameter_competitiveness_score": 92,
        "sparse_sample_flag": False,
        "explanation_cn": "芯片参数在同战场可比池中领先。",
    }

    role = m12c_service._claim_role(
        target_sku="sku-a",
        has_claim=True,
        metric=metric,
        pool=pool,
        param_strength=Decimal("1.0000"),
        comment_strength=Decimal("0.6500"),
        semantic_strength=Decimal("0.9500"),
        battlefield_claim_relevance=Decimal("1.0000"),
        parameter_competitiveness=competitiveness,
        has_negative=False,
    )
    scorecard = m12c_service._claim_value_scorecard(
        pool=pool,
        role=role,
        metric=metric,
        has_claim=True,
        param_strength=Decimal("1.0000"),
        comment_strength=Decimal("0.6500"),
        semantic_strength=Decimal("0.9500"),
        has_negative=False,
        market_position={"type": "premium_accepted", "summary_cn": "价格较高且销量不弱"},
        parameter_competitiveness=competitiveness,
    )

    assert role == m12c_service.M12C_ROLE_PREMIUM
    assert (
        m12c_service._business_claim_type(
            role,
            metric,
            scorecard,
            market_position={"type": "premium_accepted"},
            parameter_competitiveness=competitiveness,
        )
        == m12c_service.M12C_CLAIM_TYPE_PREMIUM
    )
    basis = m12c_service._amount_quantification_basis(pool, "sku-a")
    assert basis["amount_quantification_ready"] is True
    assert basis["sample_grade"] == "可量化，比较组单样本"
    assert "single_sku_comparison_group" in basis["quality_flags"]


def test_m12c_numeric_claim_pool_splits_by_param_tier_before_claim_presence() -> None:
    markets = {
        sku: m12c_service.MarketState(
            sku_code=sku,
            brand_name="brand",
            model_name=sku,
            size_tier="large_60_69",
            exact_size_tier="65",
            price_band="high",
            price=price,
            sales_volume_total=Decimal("100"),
            sales_amount_total=price * Decimal("100"),
            avg_weekly_sales_volume=Decimal("10"),
            avg_weekly_sales_amount=price * Decimal("10"),
            active_week_count=10,
            window_start_week=2601,
            window_end_week=2624,
        )
        for sku, price in {
            "sku-high": Decimal("6000"),
            "sku-mid": Decimal("5500"),
            "sku-low": Decimal("5000"),
        }.items()
    }
    claim_code = "tv_claim_hdr_high_brightness"
    claims = {
        sku: {
            claim_code: m12c_service.ClaimState(
                sku_code=sku,
                claim_code=claim_code,
                claim_name="HDR/高亮画质",
                claim_dimension="picture_quality",
                claim_subtype="brightness",
                claim_kind="product_experience",
                param_support_status="supported",
                supporting_param_codes=("declared_brightness_nit_or_band",),
                supporting_param_snapshot={},
                match_score=Decimal("1.0000"),
                confidence=Decimal("0.9000"),
                fact_claim_flag=True,
                service_separate_flag=False,
                evidence_ids=(f"ev-{sku}",),
                param_support_level=m12c_service.M04C_PARAM_SUPPORT_STRONG_NUMERIC,
                primary_supporting_param_codes=("declared_brightness_nit_or_band",),
                wtp_input_guard=m12c_service.M04C_WTP_GUARD_ELIGIBLE,
            )
        }
        for sku in markets
    }
    param_profiles = {
        "sku-high": m12c_service.ParamProfileState("sku-high", {"declared_brightness_nit_or_band": {"normalized_value": 5200}}, ("p1",)),
        "sku-mid": m12c_service.ParamProfileState("sku-mid", {"declared_brightness_nit_or_band": {"normalized_value": 4000}}, ("p2",)),
        "sku-low": m12c_service.ParamProfileState("sku-low", {"declared_brightness_nit_or_band": {"normalized_value": 3000}}, ("p3",)),
    }
    semantics = {
        sku: m12c_service.SemanticState(
            sku_code=sku,
            contexts=(("battlefield", "BF_PREMIUM_PICTURE_UPGRADE", "高端画质升级战场", "primary"),),
        )
        for sku in markets
    }

    pools = m12c_service._build_pools(
        markets=markets,
        claims=claims,
        semantics=semantics,
        dimension_names={("battlefield", "BF_PREMIUM_PICTURE_UPGRADE"): "高端画质升级战场"},
        param_profiles=param_profiles,
    )

    pool = next(item for item in pools if item.claim_code == claim_code)
    assert pool.comparison_basis == "numeric_param_tier"
    assert pool.comparison_param_code == "declared_brightness_nit_or_band"
    assert pool.comparison_threshold_value == "4000.0000"
    assert set(pool.with_claim_skus) == {"sku-high", "sku-mid"}
    assert set(pool.without_claim_skus) == {"sku-low"}
    assert pool.sample_status == "sufficient"


def test_m12c_refresh_rate_numeric_pool_uses_business_tiers_not_median() -> None:
    claim_code = "tv_claim_high_refresh_rate"
    claims = {
        sku: {
            claim_code: m12c_service.ClaimState(
                sku_code=sku,
                claim_code=claim_code,
                claim_name="高刷新率",
                claim_dimension="motion_gaming",
                claim_subtype="refresh_rate",
                claim_kind="product_experience",
                param_support_status="supported",
                supporting_param_codes=("declared_refresh_rate_hz",),
                supporting_param_snapshot={},
                match_score=Decimal("1.0000"),
                confidence=Decimal("0.9000"),
                fact_claim_flag=True,
                service_separate_flag=False,
                evidence_ids=(f"ev-{sku}",),
                param_support_level=m12c_service.M04C_PARAM_SUPPORT_STRONG_NUMERIC,
                primary_supporting_param_codes=("declared_refresh_rate_hz",),
                wtp_input_guard=m12c_service.M04C_WTP_GUARD_ELIGIBLE,
            )
        }
        for sku in ("sku-300", "sku-288", "sku-144")
    }
    param_profiles = {
        "sku-300": m12c_service.ParamProfileState("sku-300", {"declared_refresh_rate_hz": {"normalized_value": 300}}, ()),
        "sku-288": m12c_service.ParamProfileState("sku-288", {"declared_refresh_rate_hz": {"normalized_value": 288}}, ()),
        "sku-144": m12c_service.ParamProfileState("sku-144", {"declared_refresh_rate_hz": {"normalized_value": 144}}, ()),
    }

    split = m12c_service._split_numeric_param_groups(tuple(param_profiles), claims, param_profiles, claim_code)

    assert split is not None
    assert split.comparison_basis == "numeric_param_tier"
    assert split.comparison_threshold_value == "refresh_advanced_240_300"
    assert split.comparison_group_label_cn == "240/288/300Hz 超高刷档组"
    assert set(split.with_skus) == {"sku-300", "sku-288"}
    assert set(split.without_skus) == {"sku-144"}


def test_m12c_refresh_rate_same_business_tier_does_not_split_300_vs_288() -> None:
    claim_code = "tv_claim_high_refresh_rate"
    claims = {
        sku: {
            claim_code: m12c_service.ClaimState(
                sku_code=sku,
                claim_code=claim_code,
                claim_name="高刷新率",
                claim_dimension="motion_gaming",
                claim_subtype="refresh_rate",
                claim_kind="product_experience",
                param_support_status="supported",
                supporting_param_codes=("declared_refresh_rate_hz",),
                supporting_param_snapshot={},
                match_score=Decimal("1.0000"),
                confidence=Decimal("0.9000"),
                fact_claim_flag=True,
                service_separate_flag=False,
                evidence_ids=(f"ev-{sku}",),
                param_support_level=m12c_service.M04C_PARAM_SUPPORT_STRONG_NUMERIC,
                primary_supporting_param_codes=("declared_refresh_rate_hz",),
                wtp_input_guard=m12c_service.M04C_WTP_GUARD_ELIGIBLE,
            )
        }
        for sku in ("sku-300", "sku-288-a", "sku-288-b")
    }
    param_profiles = {
        "sku-300": m12c_service.ParamProfileState("sku-300", {"declared_refresh_rate_hz": {"normalized_value": 300}}, ()),
        "sku-288-a": m12c_service.ParamProfileState("sku-288-a", {"declared_refresh_rate_hz": {"normalized_value": 288}}, ()),
        "sku-288-b": m12c_service.ParamProfileState("sku-288-b", {"declared_refresh_rate_hz": {"normalized_value": 288}}, ()),
    }

    split = m12c_service._split_numeric_param_groups(tuple(param_profiles), claims, param_profiles, claim_code)

    assert split is not None
    assert split.comparison_threshold_value == "refresh_advanced_240_300"
    assert set(split.with_skus) == {"sku-300", "sku-288-a", "sku-288-b"}
    assert split.without_skus == ()
    assert split.control_group_label_cn == "同档内无低刷新对照"


def test_m12c_refresh_rate_parameter_competitiveness_treats_300_and_288_as_same_tier() -> None:
    result = m12c_service._single_param_competitiveness(
        param_code="declared_refresh_rate_hz",
        target_entry={"normalized_value": 300},
        pool_entries=[
            {"normalized_value": 300},
            {"normalized_value": 300},
            {"normalized_value": 288},
            {"normalized_value": 288},
            {"normalized_value": 288},
            {"normalized_value": 240},
            {"normalized_value": 144},
        ],
    )

    assert result["target_business_tier_code"] == "refresh_advanced_240_300"
    assert result["target_business_tier_label_cn"] == "240/288/300Hz 超高刷档"
    assert result["target_tier_coverage_rate"] >= 0.75
    assert result["level"] == m12c_service.M12C_PARAM_LEVEL_PARITY
    assert "基础门槛" in result["reason_cn"]


def test_m12c_refresh_rate_display_uses_business_tier_not_exact_300hz_amount_label() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_high_refresh_rate",
        claim_name="高刷新率",
        context_type="battlefield",
        context_code="BF_GAMING_SPORTS_FLUENCY",
        context_name="游戏体育流畅战场",
        size_tier="large_60_69",
        price_band_group="high",
        sku_codes=("sku-a", "sku-b"),
        with_claim_skus=("sku-a",),
        without_claim_skus=("sku-b",),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
        comparison_basis="numeric_param_tier",
        comparison_param_code="declared_refresh_rate_hz",
    )
    claim = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_high_refresh_rate",
        claim_name="高刷新率",
        claim_dimension="motion_gaming",
        claim_subtype="refresh_rate",
        claim_kind="product_experience",
        param_support_status="supported",
        supporting_param_codes=("declared_refresh_rate_hz",),
        supporting_param_snapshot={},
        match_score=Decimal("1.0000"),
        confidence=Decimal("0.9000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("ev-refresh",),
    )

    name = m12c_service._claim_business_display_name(
        pool,
        claim,
        "sku-a",
        {"sku-a": m12c_service.ParamProfileState("sku-a", {"declared_refresh_rate_hz": {"normalized_value": 300}}, ())},
    )

    assert name == "240/288/300Hz 超高刷档"
    assert "300Hz 高阶刷新率" not in name


def test_m12c_high_coverage_refresh_rate_is_threshold_not_premium_even_with_positive_price_delta() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_high_refresh_rate",
        claim_name="高刷新率",
        context_type="battlefield",
        context_code="BF_GAMING_SPORTS_FLUENCY",
        context_name="游戏体育流畅战场",
        size_tier="large_60_69",
        price_band_group="mid_high_with_adjacent",
        sku_codes=("sku-a", "sku-b", "sku-c", "sku-d", "sku-e", "sku-f", "sku-g"),
        with_claim_skus=("sku-a", "sku-b", "sku-c", "sku-d", "sku-e", "sku-f"),
        without_claim_skus=("sku-g",),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
        pool_relax_level="L2",
        comparison_basis="numeric_param_tier",
        comparison_param_code="declared_refresh_rate_hz",
        comparison_threshold_value="refresh_advanced_240_300",
        comparison_group_label_cn="240/288/300Hz 超高刷档组",
        control_group_label_cn="低刷新档组",
    )
    metric = {
        "price_premium_abs": Decimal("689.4150"),
        "weekly_sales_lift_abs": Decimal("-4.979166"),
        "weekly_sales_amount_lift_abs": Decimal("216294.492292"),
        "effect_confidence": Decimal("0.8050"),
    }
    competitiveness = {
        "wtp_input_guard": m12c_service.M04C_WTP_GUARD_ELIGIBLE,
        "overall_parameter_competitiveness_level": m12c_service.M12C_PARAM_LEVEL_LEADING,
        "overall_parameter_competitiveness_score": 96,
        "sparse_sample_flag": False,
    }

    role = m12c_service._claim_role(
        target_sku="sku-a",
        has_claim=True,
        metric=metric,
        pool=pool,
        param_strength=Decimal("0.9600"),
        comment_strength=Decimal("1.0000"),
        semantic_strength=Decimal("1.0000"),
        battlefield_claim_relevance=Decimal("1.0000"),
        parameter_competitiveness=competitiveness,
        has_negative=False,
    )

    assert role == m12c_service.M12C_ROLE_BASIC


def test_m12c_blocked_generic_claim_is_threshold_not_premium() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_dolby_audio_video",
        claim_name="杜比/影音认证",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="high",
        sku_codes=("sku-a", "sku-b", "sku-c", "sku-d", "sku-e", "sku-f"),
        with_claim_skus=("sku-a", "sku-b", "sku-c"),
        without_claim_skus=("sku-d", "sku-e", "sku-f"),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
    )
    metric = {
        "price_premium_abs": Decimal("500.0000"),
        "weekly_sales_lift_abs": Decimal("20.000000"),
        "weekly_sales_amount_lift_abs": Decimal("100000.000000"),
        "effect_confidence": Decimal("0.9000"),
    }
    competitiveness = {
        "wtp_input_guard": m12c_service.M04C_WTP_GUARD_BLOCKED_GENERIC,
        "overall_parameter_competitiveness_level": m12c_service.M12C_PARAM_LEVEL_PARITY,
        "sparse_sample_flag": False,
    }

    role = m12c_service._claim_role(
        target_sku="sku-a",
        has_claim=True,
        metric=metric,
        pool=pool,
        param_strength=Decimal("0.4500"),
        comment_strength=Decimal("1.0000"),
        semantic_strength=Decimal("1.0000"),
        battlefield_claim_relevance=Decimal("1.0000"),
        parameter_competitiveness=competitiveness,
        has_negative=False,
    )
    scorecard = m12c_service._claim_value_scorecard(
        pool=pool,
        role=role,
        metric=metric,
        has_claim=True,
        param_strength=Decimal("0.4500"),
        comment_strength=Decimal("1.0000"),
        semantic_strength=Decimal("1.0000"),
        has_negative=False,
        market_position={"type": "premium_accepted", "summary_cn": "价格较高且销量不弱"},
        parameter_competitiveness=competitiveness,
    )

    assert role == m12c_service.M12C_ROLE_BASIC
    assert (
        m12c_service._business_claim_type(
            role,
            metric,
            scorecard,
            market_position={"type": "premium_accepted"},
            parameter_competitiveness=competitiveness,
        )
        == m12c_service.M12C_CLAIM_TYPE_THRESHOLD
    )


def test_m12c_eye_care_requires_strict_eye_care_params_before_positive_value() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_eye_care_display",
        claim_name="护眼显示",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="high",
        sku_codes=("sku-a", "sku-b", "sku-c"),
        with_claim_skus=("sku-a",),
        without_claim_skus=("sku-b", "sku-c"),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
    )
    claim = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_eye_care_display",
        claim_name="护眼显示",
        claim_dimension="picture_quality",
        claim_subtype="eye_care",
        claim_kind="product_experience",
        param_support_status="supported",
        supporting_param_codes=("hdr_support_flag", "declared_brightness_nit_or_band", "declared_refresh_rate_hz"),
        supporting_param_snapshot={},
        match_score=Decimal("1.0000"),
        confidence=Decimal("0.9000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("ev-eye",),
        param_support_level=m12c_service.M04C_PARAM_SUPPORT_STRONG_NUMERIC,
        primary_supporting_param_codes=("declared_brightness_nit_or_band",),
        wtp_input_guard=m12c_service.M04C_WTP_GUARD_ELIGIBLE,
    )
    assert "declared_brightness_nit_or_band" not in m12c_service._claim_support_param_codes(claim, "tv_claim_eye_care_display")
    competitiveness = m12c_service._claim_parameter_competitiveness(
        pool=pool,
        target_sku="sku-a",
        claim=claim,
        claims={"sku-a": {"tv_claim_eye_care_display": claim}},
        comments={"sku-a": m12c_service.CommentState("sku-a", ("tv_claim_eye_care_display",), (), 8, 0, Decimal("0.9000"))},
        param_profiles={
            "sku-a": m12c_service.ParamProfileState(
                "sku-a",
                {"hdr_support_flag": True, "declared_brightness_nit_or_band": 5200, "declared_refresh_rate_hz": 300},
                (),
            )
        },
    )
    assert competitiveness["target_has_supporting_param"] is False
    assert competitiveness["overall_parameter_competitiveness_level"] == m12c_service.M12C_PARAM_LEVEL_WEAK

    role = m12c_service._claim_role(
        target_sku="sku-a",
        has_claim=True,
        metric={
            "price_premium_abs": Decimal("500.0000"),
            "weekly_sales_lift_abs": Decimal("20.000000"),
            "weekly_sales_amount_lift_abs": Decimal("100000.000000"),
            "effect_confidence": Decimal("0.9000"),
        },
        pool=pool,
        param_strength=Decimal("1.0000"),
        comment_strength=Decimal("0.9000"),
        semantic_strength=Decimal("1.0000"),
        battlefield_claim_relevance=Decimal("1.0000"),
        parameter_competitiveness=competitiveness,
        has_negative=False,
    )
    assert role == m12c_service.M12C_ROLE_BRAND


def test_m12c_scene_context_claim_never_becomes_positive_value() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_theater_scene",
        claim_name="影院/观影场景",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="high",
        sku_codes=("sku-a", "sku-b", "sku-c"),
        with_claim_skus=("sku-a",),
        without_claim_skus=("sku-b", "sku-c"),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
    )
    role = m12c_service._claim_role(
        target_sku="sku-a",
        has_claim=True,
        metric={
            "price_premium_abs": Decimal("500.0000"),
            "weekly_sales_lift_abs": Decimal("20.000000"),
            "weekly_sales_amount_lift_abs": Decimal("100000.000000"),
            "effect_confidence": Decimal("0.9000"),
        },
        pool=pool,
        param_strength=Decimal("1.0000"),
        comment_strength=Decimal("1.0000"),
        semantic_strength=Decimal("1.0000"),
        battlefield_claim_relevance=Decimal("1.0000"),
        parameter_competitiveness={"wtp_input_guard": m12c_service.M04C_WTP_GUARD_NOT_SCOPE},
        has_negative=False,
    )
    assert role == m12c_service.M12C_ROLE_BRAND
    assert role not in m12c_service.POSITIVE_ROLES


def test_m12c_hdr_numeric_display_uses_brightness_value_reason() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_hdr_high_brightness",
        claim_name="HDR/高亮画质",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="high",
        sku_codes=("sku-a", "sku-b", "sku-c"),
        with_claim_skus=("sku-a",),
        without_claim_skus=("sku-b", "sku-c"),
        unknown_skus=(),
        sample_status="sufficient",
        quality_flags=(),
        relaxation_path=(),
        comparison_basis="numeric_param_tier",
        comparison_param_code="declared_brightness_nit_or_band",
    )
    claim = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_hdr_high_brightness",
        claim_name="HDR/高亮画质",
        claim_dimension="picture_quality",
        claim_subtype="brightness",
        claim_kind="product_experience",
        param_support_status="supported",
        supporting_param_codes=("declared_brightness_nit_or_band",),
        supporting_param_snapshot={},
        match_score=Decimal("1.0000"),
        confidence=Decimal("0.9000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("ev-hdr",),
    )
    name = m12c_service._claim_business_display_name(
        pool,
        claim,
        "sku-a",
        {"sku-a": m12c_service.ParamProfileState("sku-a", {"declared_brightness_nit_or_band": {"normalized_value": 5200}}, ())},
    )
    assert name == "5200nits 高亮档位"


def test_m12c_merges_same_canonical_claim_states() -> None:
    chip = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_chip_performance",
        claim_name="芯片/处理器性能",
        claim_dimension="system_performance",
        claim_subtype="chip",
        claim_kind="product_experience",
        param_support_status="supported",
        supporting_param_codes=("processor_chip_model",),
        supporting_param_snapshot={},
        match_score=Decimal("1.0000"),
        confidence=Decimal("0.9000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("ev-chip",),
        param_support_level=m12c_service.M04C_PARAM_SUPPORT_STRONG_SPECIFIC,
        primary_supporting_param_codes=("processor_chip_model",),
        canonical_claim_code="tv_claim_chip_performance",
        canonical_claim_name="芯片/处理器性能",
        wtp_input_guard=m12c_service.M04C_WTP_GUARD_ELIGIBLE,
        member_claim_codes=("tv_claim_chip_performance",),
        member_claim_names=("芯片/处理器性能",),
    )
    picture = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_chip_performance",
        claim_name="芯片/处理器性能",
        claim_dimension="picture_quality",
        claim_subtype="picture_engine",
        claim_kind="product_experience",
        param_support_status="supported",
        supporting_param_codes=("processor_chip_model",),
        supporting_param_snapshot={},
        match_score=Decimal("1.0000"),
        confidence=Decimal("0.8000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("ev-picture",),
        param_support_level=m12c_service.M04C_PARAM_SUPPORT_STRONG_SPECIFIC,
        primary_supporting_param_codes=("processor_chip_model",),
        canonical_claim_code="tv_claim_chip_performance",
        canonical_claim_name="芯片/处理器性能",
        wtp_input_guard=m12c_service.M04C_WTP_GUARD_ELIGIBLE,
        member_claim_codes=("tv_claim_picture_engine_ai",),
        member_claim_names=("画质芯片/AI 画质引擎",),
    )

    merged = m12c_service._merge_claim_states(chip, picture)

    assert merged.claim_code == "tv_claim_chip_performance"
    assert merged.member_claim_codes == ("tv_claim_chip_performance", "tv_claim_picture_engine_ai")
    assert merged.evidence_ids == ("ev-chip", "ev-picture")
    assert merged.payment_value_eligible is True
