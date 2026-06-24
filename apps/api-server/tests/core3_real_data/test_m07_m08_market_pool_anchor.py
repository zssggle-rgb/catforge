from decimal import Decimal
from types import SimpleNamespace

from app.services.core3_real_data.constants import M07AnalysisWindow, M07MarketSignalCode, M07SampleStatus, M08ForModule
from app.services.core3_real_data.market_profile_schemas import M07MarketInputRow, M07SkuMarketMetrics
from app.services.core3_real_data.market_profile_service import (
    MarketProfileService,
    _market_size_class,
    _market_pool_key,
    _observed_window_sample_status,
    _quality_flags,
    _rows_for_window,
    _screen_size_class,
    _select_screen_size_param_value,
    _size_segment,
    _trend_metrics,
)
from app.services.core3_real_data.sku_signal_profile_schemas import M08SkuSignalProfileRecord
from app.services.core3_real_data.sku_signal_profile_service import _business_signal_index, _view_payload


def _metric(
    sku_code: str,
    *,
    size: str,
    price: str,
    volume: str,
    amount: str,
) -> M07SkuMarketMetrics:
    size_value = Decimal(size)
    screen_size_class = _screen_size_class(size_value)
    return M07SkuMarketMetrics(
        sku_code=sku_code,
        analysis_window=M07AnalysisWindow.FULL_OBSERVED_WINDOW,
        screen_size_inch=size_value,
        size_segment=size,
        screen_size_class=screen_size_class,
        market_pool_key=_market_pool_key("TV", screen_size_class, "线上", M07AnalysisWindow.FULL_OBSERVED_WINDOW),
        active_week_count=8,
        market_row_count=8,
        platform_count=1,
        price_wavg=Decimal(price),
        price_per_inch=Decimal(price) / size_value,
        sales_volume_total=Decimal(volume),
        sales_amount_total=Decimal(amount),
        main_channel_type="线上",
        input_fingerprint=f"input-{sku_code}",
        result_hash=f"hash-{sku_code}",
    )


def _market_row(sku_code: str, week: int, volume: str, amount: str) -> M07MarketInputRow:
    return M07MarketInputRow(
        clean_market_id=f"clean-{sku_code}-{week}",
        sku_code=sku_code,
        period_week_index=week,
        channel_type="线上",
        platform_type="平台电商",
        sales_volume=Decimal(volume),
        sales_amount=Decimal(amount),
        avg_price=Decimal(amount) / Decimal(volume) if Decimal(volume) else None,
        clean_hash=f"hash-{sku_code}-{week}",
    )


def test_m07_market_pool_fields_separate_small_and_large_size_classes() -> None:
    service = MarketProfileService(repository=object())
    updated = service._apply_percentiles(
        [
            _metric("TV43", size="43", price="1999", volume="80", amount="159920"),
            _metric("TV75", size="75", price="4299", volume="40", amount="171960"),
            _metric("TV85A", size="85", price="5999", volume="60", amount="359940"),
            _metric("TV85B", size="85", price="6999", volume="20", amount="139980"),
        ]
    )

    by_sku = {item.sku_code: item for item in updated}

    assert by_sku["TV43"].screen_size_class == "compact_screen"
    assert by_sku["TV43"].same_pool_sku_count == 1
    assert by_sku["TV75"].screen_size_class == "large_upgrade"
    assert by_sku["TV75"].same_pool_sku_count == 3
    assert by_sku["TV75"].market_pool_key == "tv:large_upgrade:线上:full_observed_window"
    assert by_sku["TV75"].same_pool_price_percentile == Decimal("0.333333")
    assert by_sku["TV85A"].same_pool_volume_percentile == Decimal("1.000000")
    assert by_sku["TV85B"].price_per_inch_percentile == Decimal("1.000000")


def test_m07_screen_size_helpers_reject_zero_and_prefer_exact_size() -> None:
    assert _screen_size_class(Decimal("0")) == "unknown"
    assert _size_segment(Decimal("0")) == "unknown"

    selected = _select_screen_size_param_value(
        [
            SimpleNamespace(
                param_value_id="zero",
                raw_param_name="屏幕尺寸",
                raw_param_value="0",
                numeric_value=Decimal("0"),
                source_type="raw_param",
                source_priority_rank=1,
                confidence=Decimal("0.9500"),
            ),
            SimpleNamespace(
                param_value_id="range",
                raw_param_name="尺寸段",
                raw_param_value="≥70",
                numeric_value=Decimal("70"),
                source_type="raw_param",
                source_priority_rank=1,
                confidence=Decimal("0.9500"),
            ),
            SimpleNamespace(
                param_value_id="exact",
                raw_param_name="尺寸",
                raw_param_value="85英寸",
                numeric_value=Decimal("85"),
                source_type="raw_param",
                source_priority_rank=1,
                confidence=Decimal("0.9500"),
            ),
        ]
    )

    assert selected is not None
    assert selected.param_value_id == "exact"


def test_m07_ac_market_size_inputs_use_horsepower_and_installation() -> None:
    profile = SimpleNamespace(
        sku_code="AC00000001",
        profile_hash="sha256:ac-param-profile",
        evidence_ids=["ev-profile"],
        param_values_json={
            "installation_type": {
                "normalized_value": "wall_mounted",
                "value_text": "挂机",
                "confidence": Decimal("0.9000"),
                "evidence_ids": ["ev-install"],
            },
            "horsepower_hp": {
                "normalized_value": 1.5,
                "numeric_value": Decimal("1.5"),
                "confidence": Decimal("0.9200"),
                "evidence_ids": ["ev-hp"],
            },
            "cooling_capacity_w": {
                "normalized_value": 3510,
                "numeric_value": Decimal("3510"),
                "confidence": Decimal("0.8800"),
                "evidence_ids": ["ev-cooling"],
            },
        },
    )

    service = MarketProfileService(repository=SimpleNamespace(list_sku_param_profiles=lambda batch_id: [profile]))
    size_inputs = service._size_inputs("batch-ac", product_category="AC")

    size_input = size_inputs["AC00000001"]
    assert size_input.screen_size_inch is None
    assert size_input.size_segment == "wall_hp_1_5"
    assert _market_size_class("AC", size_input) == "wall_hp_1_5"
    assert size_input.confidence == Decimal("0.9200")

    flags = _quality_flags(
        rows=[],
        all_rows=[],
        size_input=size_input,
        global_week_count=8,
        latest_week_gap=None,
        trend={},
        channel_share={"线上": {}},
        platform_share={"平台电商": {}},
        price_wavg=Decimal("2999"),
        product_category="AC",
    )
    assert "size_missing" not in flags


def test_m07_ac_percentiles_do_not_require_screen_size_inch() -> None:
    service = MarketProfileService(repository=object())
    updated = service._apply_percentiles(
        [
            M07SkuMarketMetrics(
                sku_code="AC-A",
                analysis_window=M07AnalysisWindow.FULL_OBSERVED_WINDOW,
                size_segment="wall_hp_1_5",
                screen_size_class="wall_hp_1_5",
                market_pool_key="ac:wall_hp_1_5:线上:full_observed_window",
                active_week_count=8,
                market_row_count=8,
                platform_count=1,
                size_param_confidence=Decimal("0.9200"),
                price_wavg=Decimal("2999"),
                sales_volume_total=Decimal("100"),
                sales_amount_total=Decimal("299900"),
                main_channel_type="线上",
                input_fingerprint="input-a",
                result_hash="hash-a",
            ),
            M07SkuMarketMetrics(
                sku_code="AC-B",
                analysis_window=M07AnalysisWindow.FULL_OBSERVED_WINDOW,
                size_segment="floor_hp_3",
                screen_size_class="floor_hp_3",
                market_pool_key="ac:floor_hp_3:线上:full_observed_window",
                active_week_count=8,
                market_row_count=8,
                platform_count=1,
                size_param_confidence=Decimal("0.9000"),
                price_wavg=Decimal("6999"),
                sales_volume_total=Decimal("30"),
                sales_amount_total=Decimal("209970"),
                main_channel_type="线上",
                input_fingerprint="input-b",
                result_hash="hash-b",
            ),
        ],
        product_category="AC",
    )

    by_sku = {item.sku_code: item for item in updated}
    assert by_sku["AC-A"].price_per_inch_percentile is None
    assert "size_missing" not in by_sku["AC-A"].quality_flags
    assert by_sku["AC-A"].market_confidence > Decimal("0.6000")


def test_m07_late_launch_complete_latest_week_is_sufficient() -> None:
    service = MarketProfileService(repository=object())
    updated = service._apply_percentiles(
        [
            M07SkuMarketMetrics(
                sku_code="AC-LATE",
                analysis_window=M07AnalysisWindow.LATEST_WEEK,
                period_start_week_index=24,
                period_end_week_index=24,
                global_latest_week_index=24,
                size_segment="wall_hp_1_5",
                screen_size_class="wall_hp_1_5",
                market_pool_key="ac:wall_hp_1_5:线上:latest_week",
                active_week_count=1,
                market_row_count=1,
                platform_count=1,
                size_param_confidence=Decimal("0.9200"),
                price_wavg=Decimal("2999"),
                sales_volume_total=Decimal("10"),
                sales_amount_total=Decimal("29990"),
                main_channel_type="线上",
                input_fingerprint="input-late",
                result_hash="hash-late",
            )
        ],
        product_category="AC",
    )

    item = updated[0]
    assert item.sample_status == M07SampleStatus.SUFFICIENT
    assert "market_sample_limited" not in item.quality_flags
    assert item.market_confidence >= Decimal("0.8500")


def test_m07_late_launch_complete_recent_window_is_sufficient() -> None:
    assert (
        _observed_window_sample_status(
            active_week_count=3,
            has_rows=True,
            analysis_window=M07AnalysisWindow.RECENT_4W,
            first_week=22,
            global_latest_week=24,
        )
        == M07SampleStatus.SUFFICIENT
    )
    assert (
        _observed_window_sample_status(
            active_week_count=0,
            has_rows=True,
            analysis_window=M07AnalysisWindow.RECENT_4W,
            first_week=21,
            global_latest_week=24,
        )
        == M07SampleStatus.SUFFICIENT
    )


def test_m07_latest_week_uses_global_week_and_missing_sales_is_zero() -> None:
    rows = [_market_row("AC-LATE", 23, "12", "35988")]

    assert _rows_for_window(rows, M07AnalysisWindow.LATEST_WEEK, 24) == []
    assert (
        _observed_window_sample_status(
            active_week_count=0,
            has_rows=True,
            analysis_window=M07AnalysisWindow.LATEST_WEEK,
            first_week=24,
            global_latest_week=24,
        )
        == M07SampleStatus.SUFFICIENT
    )


def test_m07_trend_treats_missing_sales_weeks_as_zero() -> None:
    trend = _trend_metrics([_market_row("AC-LATE", 17, "10", "29990")], global_latest_week=24)

    assert trend["sales_growth_recent_4w"] == Decimal("-1.000000")
    assert trend["amount_growth_recent_4w"] == Decimal("-1.000000")
    assert trend["quality_flags"] == []


def test_m07_zero_sales_window_is_not_price_or_platform_missing() -> None:
    flags = _quality_flags(
        rows=[],
        all_rows=[_market_row("AC-LATE", 20, "8", "23992")],
        size_input=SimpleNamespace(size_segment="wall_hp_1_5"),
        global_week_count=8,
        latest_week_gap=4,
        trend={},
        channel_share={},
        platform_share={},
        price_wavg=None,
        sales_volume_total=Decimal("0"),
        has_market_history=True,
        product_category="AC",
    )

    assert "price_missing" not in flags
    assert "platform_missing" not in flags


def test_m07_sufficient_zero_sales_profile_does_not_emit_sample_insufficient_signal() -> None:
    service = MarketProfileService(repository=object())
    profile = SimpleNamespace(
        project_id="project",
        category_code="AC",
        batch_id="batch",
        run_id=None,
        module_run_id=None,
        sku_market_profile_id="profile-ac-zero",
        sku_code="AC-ZERO",
        model_name=None,
        brand_name=None,
        analysis_window=M07AnalysisWindow.LATEST_WEEK,
        price_percentile_in_category=None,
        price_percentile_in_size=None,
        volume_percentile_in_category=Decimal("0.1000"),
        volume_percentile_in_size=Decimal("0.1000"),
        amount_percentile_in_category=Decimal("0.1000"),
        amount_percentile_in_size=Decimal("0.1000"),
        price_change_recent_4w=None,
        sales_growth_recent_4w=None,
        same_pool_volume_percentile=None,
        same_pool_amount_percentile=None,
        platform_share_json={},
        main_platform=None,
        market_pool_key=None,
        sample_status=M07SampleStatus.SUFFICIENT,
        price_wavg=None,
        market_confidence=Decimal("0.8000"),
        quality_flags=[],
        evidence_ids=[],
        input_fingerprint="input-ac-zero",
        result_hash="hash-ac-zero",
    )

    signals = service._signals_for_profile(profile, {}, rule_version="m07_market_profile_v1")

    assert all(signal.signal_code != M07MarketSignalCode.SAMPLE_INSUFFICIENT for signal in signals)


def test_m07_online_current_year_scope_is_not_execution_warning() -> None:
    service = MarketProfileService(repository=object())
    profile = SimpleNamespace(
        quality_flags=["observed_window_less_than_52w", "online_only_channel"],
        sample_status=M07SampleStatus.SUFFICIENT,
        analysis_window=M07AnalysisWindow.FULL_OBSERVED_WINDOW,
    )
    pool = SimpleNamespace(sample_status=M07SampleStatus.INSUFFICIENT)

    assert service._warnings([profile], [pool]) == []
    assert service._scope_notes([profile]) == [
        "当前数据按已导入的 2026 年线上观察窗口分析，不补造 52 周或 12 月伪口径。",
        "当前数据为线上渠道样本，M07 生成线上平台市场画像，不推断线下渠道。",
    ]
    assert service._quality_notes([profile], [pool]) == ["部分可比池样本不足，下游按低置信使用或进入复核。"]


def test_m07_missing_size_or_price_remains_execution_warning() -> None:
    service = MarketProfileService(repository=object())
    profile = SimpleNamespace(
        quality_flags=["size_missing", "price_missing"],
        sample_status=M07SampleStatus.SUFFICIENT,
        analysis_window=M07AnalysisWindow.FULL_OBSERVED_WINDOW,
    )

    warnings = service._warnings([profile], [])

    assert "部分 SKU 缺少有效屏幕尺寸，尺寸价格池和战场划分需要低置信使用。" in warnings
    assert "部分 SKU 缺少有效价格，价格池和溢价判断需要低置信使用。" in warnings


def test_m07_short_window_missing_price_is_quality_note_not_execution_warning() -> None:
    service = MarketProfileService(repository=object())
    full_profile = SimpleNamespace(
        quality_flags=[],
        sample_status=M07SampleStatus.SUFFICIENT,
        analysis_window=M07AnalysisWindow.FULL_OBSERVED_WINDOW,
    )
    short_window_profile = SimpleNamespace(
        quality_flags=["price_missing"],
        sample_status=M07SampleStatus.UNKNOWN,
        analysis_window=M07AnalysisWindow.RECENT_4W,
    )

    assert service._warnings([full_profile, short_window_profile], []) == []
    assert service._quality_notes([full_profile, short_window_profile], []) == [
        "部分 SKU 在自身可观测期内周样本不完整，相关市场趋势和增长判断低置信使用。",
        "部分 SKU 在短周期窗口无可计算成交价格；零销量周按 0 销量处理，不作为销量样本缺失。",
    ]


def test_m08_business_signal_index_exposes_market_pool_and_layered_product_anchors() -> None:
    market_summary = {
        "screen_size_class": "large_upgrade",
        "market_pool_key": "tv:large_upgrade:线上:full_observed_window",
        "same_pool_price_percentile": Decimal("0.333333"),
        "same_pool_volume_percentile": Decimal("0.800000"),
        "same_pool_amount_percentile": Decimal("0.750000"),
        "price_per_inch_percentile": Decimal("0.300000"),
        "same_pool_sku_count": 8,
    }
    index = _business_signal_index(
        context=SimpleNamespace(comment_signals=[]),
        core_params={
            "param_values": {
                "screen_size_inch": {
                    "value": 85,
                    "numeric_value": Decimal("85"),
                    "confidence": Decimal("0.9500"),
                    "evidence_ids": ["ev-size"],
                },
                "native_refresh_rate_hz": {
                    "value": 144,
                    "numeric_value": Decimal("144"),
                    "unit": "Hz",
                    "confidence": Decimal("0.9500"),
                    "evidence_ids": ["ev-refresh"],
                },
            }
        },
        claim_summary={
            "top_claims": [
                {
                    "claim_code_hint": "CLAIM_HIGH_REFRESH_RATE",
                    "claim_name": "高刷新率",
                    "claim_group": "gaming",
                    "activation_level": "medium",
                    "final_activation_score": Decimal("0.6800"),
                    "confidence": Decimal("0.9000"),
                }
            ]
        },
        comment_summary={"signal_type_summary": {}},
        market_summary=market_summary,
        market_signal_summary={"signal_code_counts": {"sales_volume_strong": 1}},
        pool_summary={"pool_type_counts": {"same_size": 1}},
        risk_signals=[],
    )

    anchors = index["product_anchor_index"]["anchor_groups"]
    assert index["market_pool_key"] == "tv:large_upgrade:线上:full_observed_window"
    assert anchors["motion_gaming"]["source_status"] == "claim_plus_param"
    assert anchors["motion_gaming"]["overall_score"] >= Decimal("0.3000")
    assert anchors["screen_value_market"]["market_hits"]

    profile = M08SkuSignalProfileRecord(
        sku_signal_profile_id="m08p-TV85",
        project_id="project",
        category_code="TV",
        batch_id="batch",
        sku_code="TV85",
        data_completeness_score=Decimal("0.8000"),
        confidence=Decimal("0.8000"),
        business_signal_index_json=index,
        market_summary_json=market_summary,
        input_fingerprint="input",
        profile_hash="profile-hash",
        result_hash="result-hash",
    )
    payload = _view_payload(profile, M08ForModule.M11)
    assert payload["market_pool_key"] == "tv:large_upgrade:线上:full_observed_window"
    assert payload["product_anchor_index"]["anchor_groups"]["motion_gaming"]["param_hits"]
