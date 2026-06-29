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


def test_m12c_target_only_with_claim_becomes_unique_payment_potential() -> None:
    pool = m12c_service.ClaimPool(
        claim_code="tv_claim_chip_performance",
        claim_name="芯片/处理器性能",
        context_type="battlefield",
        context_code="BF_PREMIUM_PICTURE_UPGRADE",
        context_name="高端画质升级战场",
        size_tier="large_60_69",
        price_band_group="high_with_adjacent",
        sku_codes=("sku-a", "sku-b", "sku-c", "sku-d", "sku-e", "sku-f"),
        with_claim_skus=("sku-a",),
        without_claim_skus=("sku-b", "sku-c", "sku-d", "sku-e", "sku-f"),
        unknown_skus=(),
        sample_status="weak",
        quality_flags=("small_comparable_pool",),
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
        market_position={"type": "payment_unverified", "summary_cn": "价格和销量暂未验证支付价值"},
        parameter_competitiveness=competitiveness,
    )

    assert role == m12c_service.M12C_ROLE_UNIQUE
    assert m12c_service._business_claim_type(role, metric, scorecard, parameter_competitiveness=competitiveness) == m12c_service.M12C_CLAIM_TYPE_UNIQUE
    basis = m12c_service._amount_quantification_basis(pool, "sku-a")
    assert basis["amount_quantification_ready"] is False
    assert "目标 SKU 是有卖点组唯一样本" in basis["no_amount_reason_cn"]


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
