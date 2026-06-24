"""M07 market profile and comparable pool service."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    M07_ADJACENT_SIZE_SEGMENTS,
    M07_ANALYSIS_WINDOWS,
    M07_PRICE_BAND_ORDER,
    M07AnalysisWindow,
    M07MarketSignalCode,
    M07Polarity,
    M07PoolType,
    M07PriceBand,
    M07SampleStatus,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.market_profile_repositories import M07MarketRepository
from app.services.core3_real_data.market_profile_schemas import (
    M07ComparablePoolRecord,
    M07MarketInputRow,
    M07MarketPoolMemberRecord,
    M07MarketSignalRecord,
    M07RunResult,
    M07SkuMarketMetrics,
    M07SkuMarketProfileRecord,
    M07SkuSizeInput,
    confidence_level,
    signal_level,
)


D0 = Decimal("0")
D1 = Decimal("1")
SCREEN_SIZE_MIN_INCH = Decimal("20")
SCREEN_SIZE_MAX_INCH = Decimal("130")
SCREEN_SIZE_EXACT_RAW_NAMES = frozenset({"尺寸"})
SCREEN_SIZE_RANGE_RAW_NAMES = frozenset({"尺寸段"})
SCREEN_SIZE_AREA_RAW_TOKENS = ("面积",)


@dataclass(frozen=True)
class M07ServiceResult:
    profiles: list[M07SkuMarketProfileRecord]
    signals: list[M07MarketSignalRecord]
    pools: list[M07ComparablePoolRecord]
    members: list[M07MarketPoolMemberRecord]
    summary: dict[str, Any]
    warnings: list[str]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int


class MarketProfileService:
    def __init__(self, repository: M07MarketRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str | None = None,
        sku_scope: Sequence[str] = (),
        analysis_windows: Sequence[str | M07AnalysisWindow] = (),
        rule_version: str = CORE3_M07_RULE_VERSION,
        price_band_rule_version: str = CORE3_M07_PRICE_BAND_RULE_VERSION,
        pool_rule_version: str = CORE3_M07_POOL_RULE_VERSION,
    ) -> M07ServiceResult:
        product_category_value = _normalize_product_category(product_category, self.repository.category_code)
        self.repository.assert_inputs_ready(batch_id)
        sku_codes_in_scope = tuple(sorted({code for code in sku_scope if code}))
        windows = tuple(M07AnalysisWindow(window) for window in (analysis_windows or M07_ANALYSIS_WINDOWS))

        clean_skus = self.repository.list_clean_skus(batch_id)
        sku_lookup = {sku.sku_code: sku for sku in clean_skus}
        market_rows = self._market_rows(batch_id)
        size_inputs = self._size_inputs(batch_id, product_category=product_category_value)

        all_sku_codes = sorted(set(sku_lookup) | {row.sku_code for row in market_rows})
        if sku_codes_in_scope:
            all_sku_codes = sorted(set(all_sku_codes) | set(sku_codes_in_scope))
        profiles_by_window: dict[str, list[M07SkuMarketMetrics]] = {}
        global_latest_week = _max_week(row.period_week_index for row in market_rows)
        global_first_week = _min_week(row.period_week_index for row in market_rows)
        global_week_count = (global_latest_week - global_first_week + 1) if global_latest_week and global_first_week else 0
        for window in windows:
            metrics = [
                self._calculate_metrics(
                    sku_code=sku_code,
                    sku_row=sku_lookup.get(sku_code),
                    market_rows=[row for row in market_rows if row.sku_code == sku_code],
                    size_input=size_inputs.get(sku_code),
                    analysis_window=window,
                    global_latest_week=global_latest_week,
                    global_week_count=global_week_count,
                    product_category=product_category_value,
                    rule_version=rule_version,
                    price_band_rule_version=price_band_rule_version,
                )
                for sku_code in all_sku_codes
            ]
            profiles_by_window[window.value] = self._apply_percentiles(metrics, product_category=product_category_value)

        profile_records: list[M07SkuMarketProfileRecord] = []
        for metrics in profiles_by_window.values():
            for item in metrics:
                if sku_codes_in_scope and item.sku_code not in sku_codes_in_scope:
                    continue
                profile_records.append(
                    self._profile_record(
                        item,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        price_band_rule_version=price_band_rule_version,
                    )
                )
        profile_write = self.repository.save_profiles(profile_records)

        signals = self._build_signals(profile_records, profiles_by_window, rule_version=rule_version)
        signal_write = self.repository.save_signals(signals)

        pools, members = self._build_pools_and_members(
            profile_records,
            profiles_by_window,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            pool_rule_version=pool_rule_version,
        )
        pool_write = self.repository.save_pools(pools)
        member_write = self.repository.save_members(members)

        warnings = self._warnings(profile_records, pools)
        scope_notes = self._scope_notes(profile_records)
        quality_notes = self._quality_notes(profile_records, pools)
        review_required_count = sum(1 for item in [*profile_records, *signals, *pools, *members] if item.review_required)
        output_count = len(profile_records) + len(signals) + len(pools) + len(members)
        created_count = (
            profile_write.created_count
            + signal_write.created_count
            + pool_write.created_count
            + member_write.created_count
        )
        summary = {
            "batch_id": batch_id,
            "product_category": product_category_value,
            "rule_version": rule_version,
            "price_band_rule_version": price_band_rule_version,
            "pool_rule_version": pool_rule_version,
            "analysis_windows": [window.value for window in windows],
            "sku_count": len(all_sku_codes),
            "processed_sku_count": len({profile.sku_code for profile in profile_records}),
            "market_profile_count": len(profile_records),
            "market_signal_count": len(signals),
            "comparable_pool_count": len(pools),
            "pool_member_count": len(members),
            "review_required_count": review_required_count,
            "scope_notes": scope_notes,
            "quality_notes": quality_notes,
            "sample_status_counts": dict(Counter(profile.sample_status for profile in profile_records)),
            "pool_status_counts": dict(Counter(pool.sample_status for pool in pools)),
            "created_output_count": created_count,
            "updated_output_count": (
                profile_write.updated_count
                + signal_write.updated_count
                + pool_write.updated_count
                + member_write.updated_count
            ),
            "reused_output_count": (
                profile_write.reused_count
                + signal_write.reused_count
                + pool_write.reused_count
                + member_write.reused_count
            ),
            "boundary_note": (
                "M07 只生成市场画像、市场信号和可比池基线；不生成任务、客群、战场、候选或竞品结论，"
                "不使用 12m 伪口径。"
            ),
            "downstream_support": {
                "M08": "可消费市场画像、市场信号和可比池摘要",
                "M11.5": "可消费池内价格、销量、销额分布作为卖点价值层基线",
                "M12": "可消费市场可比池，但需在 M12 再决定候选召回",
                "M13": "可消费池成员关系强度和市场压力指标",
            },
        }
        status = Core3RunStatus.WARNING if warnings else Core3RunStatus.SUCCESS
        return M07ServiceResult(
            profiles=profile_records,
            signals=signals,
            pools=pools,
            members=members,
            summary=summary,
            warnings=warnings,
            status=status,
            input_count=len(market_rows),
            output_count=output_count,
            created_output_count=created_count,
        )

    def _market_rows(self, batch_id: str) -> list[M07MarketInputRow]:
        evidence_by_clean_key: dict[str, list[str]] = {}
        evidence_by_source_row: dict[str, list[str]] = {}
        for evidence in self.repository.list_market_evidence(batch_id):
            if evidence.clean_record_key:
                evidence_by_clean_key.setdefault(evidence.clean_record_key, []).append(evidence.evidence_id)
            if evidence.source_row_id:
                evidence_by_source_row.setdefault(evidence.source_row_id, []).append(evidence.evidence_id)

        rows: list[M07MarketInputRow] = []
        for row in self.repository.list_clean_market_rows(batch_id):
            if not row.sku_code:
                continue
            evidence_ids = _unique(
                [
                    *evidence_by_clean_key.get(row.clean_record_key, []),
                    *evidence_by_source_row.get(row.source_row_id, []),
                ]
            )
            quality_flags = list(row.quality_flags or [])
            if row.price_check_status not in {"ok", "uncheckable", None}:
                quality_flags.append("price_check_mismatch")
            rows.append(
                M07MarketInputRow(
                    clean_market_id=row.clean_market_id,
                    sku_code=row.sku_code,
                    model_name=row.model_name,
                    brand_name=row.brand_name,
                    category_name=row.category_name_raw,
                    period_raw=row.period_raw,
                    period_week_index=row.period_week_index,
                    channel_type=row.channel_type,
                    platform_type=row.platform_type,
                    sales_volume=row.sales_volume,
                    sales_amount=row.sales_amount,
                    avg_price=row.avg_price,
                    price_check_status=row.price_check_status,
                    clean_hash=row.clean_hash,
                    quality_flags=quality_flags,
                    evidence_ids=evidence_ids,
                )
            )
        return rows

    def _size_inputs(self, batch_id: str, *, product_category: str = "TV") -> dict[str, M07SkuSizeInput]:
        if product_category == "AC":
            return self._ac_size_inputs(batch_id)
        return self._tv_size_inputs(batch_id)

    def _tv_size_inputs(self, batch_id: str) -> dict[str, M07SkuSizeInput]:
        extracted: dict[str, M07SkuSizeInput] = {}
        candidates_by_sku: dict[str, list[Any]] = {}
        for value in self.repository.list_extract_param_values(batch_id):
            if value.param_code != "screen_size_inch":
                continue
            candidates_by_sku.setdefault(value.sku_code, []).append(value)
        for sku_code, candidates in sorted(candidates_by_sku.items()):
            selected = _select_screen_size_param_value(candidates)
            if selected is None:
                continue
            number = _valid_screen_size_number(selected.numeric_value)
            if number is None:
                continue
            extracted[sku_code] = M07SkuSizeInput(
                sku_code=sku_code,
                screen_size_inch=number,
                size_segment=_size_segment(number),
                confidence=selected.confidence,
                evidence_ids=list(selected.evidence_ids or []),
                profile_hash=selected.param_value_hash,
            )

        for profile in self.repository.list_sku_param_profiles(batch_id):
            if profile.sku_code in extracted:
                continue
            entry = _screen_size_entry(profile.param_values_json) or _screen_size_entry(profile.core_picture_params_json)
            number = _valid_screen_size_number(entry.get("numeric_value") if entry else None)
            if number is None:
                continue
            confidence = _decimal_or_none(entry.get("confidence") if entry else None) or Decimal("0.0000")
            extracted[profile.sku_code] = M07SkuSizeInput(
                sku_code=profile.sku_code,
                screen_size_inch=number,
                size_segment=_size_segment(number),
                confidence=confidence,
                evidence_ids=list(entry.get("evidence_ids") or profile.evidence_ids or []) if entry else list(profile.evidence_ids or []),
                profile_hash=profile.profile_hash,
            )
        return extracted

    def _ac_size_inputs(self, batch_id: str) -> dict[str, M07SkuSizeInput]:
        extracted: dict[str, M07SkuSizeInput] = {}
        for profile in self.repository.list_sku_param_profiles(batch_id):
            values = profile.param_values_json or {}
            horsepower_entry = _profile_param_entry(values, "horsepower_hp")
            installation_entry = _profile_param_entry(values, "installation_type")
            cooling_entry = _profile_param_entry(values, "cooling_capacity_w")
            horsepower = _decimal_or_none((horsepower_entry or {}).get("numeric_value"))
            installation = _normalized_text_value(installation_entry)
            cooling_capacity = _decimal_or_none((cooling_entry or {}).get("numeric_value"))
            size_segment = _ac_size_segment(installation, horsepower, cooling_capacity)
            size_class = _ac_size_class(installation, horsepower)
            if size_segment == "unknown" and size_class == "unknown":
                continue
            evidence_ids = _unique(
                [
                    *_list_or_empty((horsepower_entry or {}).get("evidence_ids")),
                    *_list_or_empty((installation_entry or {}).get("evidence_ids")),
                    *_list_or_empty((cooling_entry or {}).get("evidence_ids")),
                    *_list_or_empty(profile.evidence_ids),
                ]
            )
            confidence_values = [
                _decimal_or_none((horsepower_entry or {}).get("confidence")),
                _decimal_or_none((installation_entry or {}).get("confidence")),
                _decimal_or_none((cooling_entry or {}).get("confidence")),
            ]
            confidence = max((value for value in confidence_values if value is not None), default=Decimal("0.0000"))
            extracted[profile.sku_code] = M07SkuSizeInput(
                sku_code=profile.sku_code,
                screen_size_inch=None,
                size_segment=size_segment,
                confidence=confidence,
                evidence_ids=evidence_ids,
                profile_hash=profile.profile_hash,
            )
        return extracted

    def _calculate_metrics(
        self,
        *,
        sku_code: str,
        sku_row: Any | None,
        market_rows: list[M07MarketInputRow],
        size_input: M07SkuSizeInput | None,
        analysis_window: M07AnalysisWindow,
        global_latest_week: int | None,
        global_week_count: int,
        product_category: str,
        rule_version: str,
        price_band_rule_version: str,
    ) -> M07SkuMarketMetrics:
        rows = _rows_for_window(market_rows, analysis_window, global_latest_week)
        first_week = _min_week(row.period_week_index for row in rows)
        last_week = _max_week(row.period_week_index for row in rows)
        sku_latest_week = _max_week(row.period_week_index for row in market_rows)
        latest_week_gap = (
            global_latest_week - sku_latest_week
            if global_latest_week is not None and sku_latest_week is not None
            else None
        )
        sales_volume_total = _sum_decimal(row.sales_volume for row in rows if row.sales_volume is not None)
        sales_amount_total = _sum_decimal(row.sales_amount for row in rows if row.sales_amount is not None)
        price_wavg = _weighted_price(rows)
        latest_price = _weighted_price([row for row in rows if row.period_week_index == last_week])
        weekly_prices = _weekly_prices(rows)
        price_median = _median_decimal(weekly_prices)
        price_min = min(weekly_prices) if weekly_prices else None
        price_max = max(weekly_prices) if weekly_prices else None
        price_per_inch = _safe_div(price_wavg, size_input.screen_size_inch) if product_category == "TV" and size_input else None
        channel_share = _share_json(rows, "channel_type")
        platform_share = _share_json(rows, "platform_type")
        main_channel = _main_share_key(channel_share)
        main_platform = _main_share_key(platform_share)
        screen_size_class = _market_size_class(product_category, size_input)
        market_pool_key = _market_pool_key(
            _category_value(self.repository.category_code),
            screen_size_class,
            main_channel,
            analysis_window,
        )
        trend = _trend_metrics(market_rows, global_latest_week)
        quality_flags = _quality_flags(
            rows=rows,
            all_rows=market_rows,
            size_input=size_input,
            global_week_count=global_week_count,
            latest_week_gap=latest_week_gap,
            trend=trend,
            channel_share=channel_share,
            platform_share=platform_share,
            price_wavg=price_wavg,
            product_category=product_category,
        )
        active_week_count = len(
            {
                row.period_week_index
                for row in rows
                if row.period_week_index is not None and row.sales_volume is not None
            }
        )
        sample_status = _initial_sample_status(active_week_count, bool(rows))
        confidence = _market_confidence(
            active_week_count=active_week_count,
            sample_status=sample_status,
            price_wavg=price_wavg,
            size_input=size_input,
            product_category=product_category,
            quality_flags=quality_flags,
        )
        evidence_ids = _unique([evidence_id for row in rows for evidence_id in row.evidence_ids])
        param_evidence_ids = list(size_input.evidence_ids) if size_input else []
        input_fingerprint = stable_hash(
            {
                "clean_hashes": sorted(row.clean_hash for row in rows),
                "evidence_ids": sorted(evidence_ids),
                "size_profile_hash": size_input.profile_hash if size_input else None,
                "analysis_window": analysis_window.value,
                "rule_version": rule_version,
                "price_band_rule_version": price_band_rule_version,
            },
            version="m07-profile-input-v1",
        )
        model_name = _first_present(row.model_name for row in rows) or getattr(sku_row, "model_name", None)
        brand_name = _first_present(row.brand_name for row in rows) or getattr(sku_row, "brand_name", None)
        category_name = _first_present(row.category_name for row in rows) or getattr(sku_row, "category_name", None)
        result_hash = stable_hash(
            {
                "sku_code": sku_code,
                "analysis_window": analysis_window.value,
                "period_start": first_week,
                "period_end": last_week,
                "sales_volume_total": sales_volume_total,
                "sales_amount_total": sales_amount_total,
                "price_wavg": price_wavg,
                "price_latest": latest_price,
                "screen_size_inch": size_input.screen_size_inch if size_input else None,
                "screen_size_class": screen_size_class,
                "size_segment": size_input.size_segment if size_input else "unknown",
                "market_pool_key": market_pool_key,
                "quality_flags": sorted(set(quality_flags)),
                "product_category": product_category,
                "rule_version": rule_version,
            },
            version="m07-profile-result-v1",
        )
        return M07SkuMarketMetrics(
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            category_name=category_name,
            analysis_window=analysis_window,
            period_start_raw=_period_raw_for_week(rows, first_week),
            period_end_raw=_period_raw_for_week(rows, last_week),
            period_start_week_index=first_week,
            period_end_week_index=last_week,
            global_latest_week_index=global_latest_week,
            sku_latest_week_index=sku_latest_week,
            latest_week_gap=latest_week_gap,
            active_week_count=active_week_count,
            market_row_count=len(rows),
            platform_count=len(platform_share),
            screen_size_inch=size_input.screen_size_inch if size_input else None,
            size_segment=size_input.size_segment if size_input else "unknown",
            screen_size_class=screen_size_class,
            market_pool_key=market_pool_key,
            size_param_confidence=size_input.confidence if size_input else Decimal("0.0000"),
            sales_volume_total=sales_volume_total,
            sales_amount_total=sales_amount_total,
            price_wavg=price_wavg,
            price_latest=latest_price,
            price_median=price_median,
            price_min=price_min,
            price_max=price_max,
            price_per_inch=price_per_inch,
            main_channel_type=main_channel,
            main_platform=main_platform,
            channel_share_json=channel_share,
            platform_share_json=platform_share,
            price_change_recent_4w=trend.get("price_change_recent_4w"),
            sales_growth_recent_4w=trend.get("sales_growth_recent_4w"),
            amount_growth_recent_4w=trend.get("amount_growth_recent_4w"),
            price_volatility=_coefficient_of_variation(weekly_prices),
            sales_volatility=_coefficient_of_variation(_weekly_volumes(rows)),
            promotion_suspect_flag=bool(
                trend.get("price_change_recent_4w") is not None
                and trend.get("sales_growth_recent_4w") is not None
                and trend["price_change_recent_4w"] <= Decimal("-0.0300")
                and trend["sales_growth_recent_4w"] >= Decimal("0.1000")
            ),
            market_confidence=confidence,
            confidence_level=confidence_level(confidence),
            sample_status=sample_status,
            quality_flags=sorted(set(quality_flags)),
            evidence_ids=_unique([*evidence_ids, *param_evidence_ids]),
            market_evidence_ids=evidence_ids,
            param_evidence_ids=param_evidence_ids,
            input_fingerprint=input_fingerprint,
            result_hash=result_hash,
        )

    def _apply_percentiles(self, metrics: list[M07SkuMarketMetrics], *, product_category: str = "TV") -> list[M07SkuMarketMetrics]:
        by_size: dict[str, list[M07SkuMarketMetrics]] = {}
        by_market_pool: dict[str, list[M07SkuMarketMetrics]] = {}
        for item in metrics:
            by_size.setdefault(item.size_segment, []).append(item)
            by_market_pool.setdefault(item.market_pool_key or "unknown", []).append(item)
        updated: list[M07SkuMarketMetrics] = []
        for item in metrics:
            size_pool = by_size.get(item.size_segment, [])
            market_pool = by_market_pool.get(item.market_pool_key or "unknown", [])
            category_price = _percentile(item.price_wavg, [row.price_wavg for row in metrics])
            category_volume = _percentile(item.sales_volume_total, [row.sales_volume_total for row in metrics])
            category_amount = _percentile(item.sales_amount_total, [row.sales_amount_total for row in metrics])
            size_price = _percentile(item.price_wavg, [row.price_wavg for row in size_pool])
            size_volume = _percentile(item.sales_volume_total, [row.sales_volume_total for row in size_pool])
            size_amount = _percentile(item.sales_amount_total, [row.sales_amount_total for row in size_pool])
            same_pool_price = _percentile(item.price_wavg, [row.price_wavg for row in market_pool])
            same_pool_volume = _percentile(item.sales_volume_total, [row.sales_volume_total for row in market_pool])
            same_pool_amount = _percentile(item.sales_amount_total, [row.sales_amount_total for row in market_pool])
            price_per_inch_percentile = _percentile(item.price_per_inch, [row.price_per_inch for row in market_pool])
            price_band_category = _price_band(category_price, len([row for row in metrics if row.price_wavg is not None]))
            price_band_size = _price_band(size_price, len([row for row in size_pool if row.price_wavg is not None]))
            sample_status = _combined_sample_status(
                active_week_count=item.active_week_count,
                category_count=len([row for row in metrics if row.price_wavg is not None]),
                size_count=len([row for row in size_pool if row.price_wavg is not None]),
                has_rows=item.market_row_count > 0,
            )
            quality_flags = set(item.quality_flags)
            if price_band_category == M07PriceBand.UNKNOWN.value or price_band_size == M07PriceBand.UNKNOWN.value:
                quality_flags.add("price_band_sample_insufficient")
            if sample_status != M07SampleStatus.SUFFICIENT:
                quality_flags.add("market_sample_limited")
            if len(size_pool) < 3 and item.size_segment != "unknown":
                quality_flags.add("size_pool_insufficient")
            elif len(size_pool) <= 5 and item.size_segment != "unknown":
                quality_flags.add("size_pool_limited")
            if len(market_pool) < 3 and item.screen_size_class != "unknown":
                quality_flags.add("market_pool_insufficient")
            elif len(market_pool) <= 5 and item.screen_size_class != "unknown":
                quality_flags.add("market_pool_limited")
            price_gap_category = _gap(item.price_wavg, _median_decimal([row.price_wavg for row in metrics]))
            price_gap_size = _gap(item.price_wavg, _median_decimal([row.price_wavg for row in size_pool]))
            volume_gap_size = _gap(item.sales_volume_total, _median_decimal([row.sales_volume_total for row in size_pool]))
            amount_gap_size = _gap(item.sales_amount_total, _median_decimal([row.sales_amount_total for row in size_pool]))
            confidence = _market_confidence(
                active_week_count=item.active_week_count,
                sample_status=sample_status,
                price_wavg=item.price_wavg,
                size_input=M07SkuSizeInput(
                    sku_code=item.sku_code,
                    screen_size_inch=item.screen_size_inch,
                    size_segment=item.size_segment,
                    confidence=item.size_param_confidence,
                    evidence_ids=item.param_evidence_ids,
                ),
                product_category=product_category,
                quality_flags=list(quality_flags),
            )
            updated.append(
                item.model_copy(
                    update={
                        "price_percentile_in_category": category_price,
                        "volume_percentile_in_category": category_volume,
                        "amount_percentile_in_category": category_amount,
                        "price_percentile_in_size": size_price,
                        "volume_percentile_in_size": size_volume,
                        "amount_percentile_in_size": size_amount,
                        "same_pool_price_percentile": same_pool_price,
                        "same_pool_volume_percentile": same_pool_volume,
                        "same_pool_amount_percentile": same_pool_amount,
                        "price_per_inch_percentile": price_per_inch_percentile,
                        "same_pool_sku_count": len(market_pool),
                        "price_band_category": price_band_category,
                        "price_band_size": price_band_size,
                        "price_gap_to_category_median": price_gap_category,
                        "price_gap_to_size_median": price_gap_size,
                        "volume_gap_to_size_median": volume_gap_size,
                        "amount_gap_to_size_median": amount_gap_size,
                        "sample_status": sample_status,
                        "market_confidence": confidence,
                        "confidence_level": confidence_level(confidence),
                        "quality_flags": sorted(quality_flags),
                        "result_hash": stable_hash(
                            {
                                "base": item.result_hash,
                                "category_price": category_price,
                                "size_price": size_price,
                                "same_pool_price": same_pool_price,
                                "same_pool_volume": same_pool_volume,
                                "same_pool_amount": same_pool_amount,
                                "price_band_category": price_band_category,
                                "price_band_size": price_band_size,
                                "price_per_inch_percentile": price_per_inch_percentile,
                                "market_pool_key": item.market_pool_key,
                                "sample_status": sample_status,
                                "quality_flags": sorted(quality_flags),
                            },
                            version="m07-profile-percentile-v1",
                        ),
                    }
                )
            )
        return updated

    def _profile_record(
        self,
        item: M07SkuMarketMetrics,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        price_band_rule_version: str,
    ) -> M07SkuMarketProfileRecord:
        profile_key = _logic_key(batch_id, item.sku_code, item.analysis_window, rule_version)
        return M07SkuMarketProfileRecord(
            **item.model_dump(mode="python"),
            sku_market_profile_id=_stable_id("m07prof", profile_key),
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            profile_key=profile_key,
            price_band_method="category_and_size_quantile",
            rule_version=rule_version,
            price_band_rule_version=price_band_rule_version,
            processing_status="success" if item.market_row_count else "blocked",
            review_required=item.sample_status in {M07SampleStatus.INSUFFICIENT, M07SampleStatus.UNKNOWN},
            review_status=(
                "review_required"
                if item.sample_status in {M07SampleStatus.INSUFFICIENT, M07SampleStatus.UNKNOWN}
                else "auto_pass"
            ),
            review_reason_json=_review_reason(item),
        )

    def _build_signals(
        self,
        profiles: list[M07SkuMarketProfileRecord],
        profiles_by_window: dict[str, list[M07SkuMarketMetrics]],
        *,
        rule_version: str,
    ) -> list[M07MarketSignalRecord]:
        price_per_inch_percentile: dict[tuple[str, str], Decimal | None] = {}
        for window, items in profiles_by_window.items():
            for item in items:
                price_per_inch_percentile[(item.sku_code, window)] = item.price_per_inch_percentile

        records: list[M07MarketSignalRecord] = []
        for profile in profiles:
            records.extend(self._signals_for_profile(profile, price_per_inch_percentile, rule_version=rule_version))
        return records

    def _signals_for_profile(
        self,
        profile: M07SkuMarketProfileRecord,
        price_per_inch_percentile: Mapping[tuple[str, str], Decimal | None],
        *,
        rule_version: str,
    ) -> list[M07MarketSignalRecord]:
        signal_defs: list[tuple[M07MarketSignalCode, str, Decimal | None, str, str, M07Polarity, str | None]] = []
        max_price = _max_decimal(profile.price_percentile_in_category, profile.price_percentile_in_size)
        min_price = _min_decimal(profile.price_percentile_in_category, profile.price_percentile_in_size)
        max_volume = _max_decimal(profile.volume_percentile_in_category, profile.volume_percentile_in_size)
        max_amount = _max_decimal(profile.amount_percentile_in_category, profile.amount_percentile_in_size)
        price_inch_pct = price_per_inch_percentile.get((profile.sku_code, profile.analysis_window))
        if max_price is not None and max_price >= Decimal("0.75"):
            signal_defs.append((M07MarketSignalCode.PRICE_PERCENTILE_HIGH, "价格分位高", max_price, "price_percentile", "category_or_size", M07Polarity.NEGATIVE, None))
        if min_price is not None and min_price <= Decimal("0.25"):
            signal_defs.append((M07MarketSignalCode.PRICE_PERCENTILE_LOW, "价格分位低", D1 - min_price, "price_percentile", "category_or_size", M07Polarity.POSITIVE, None))
        if max_volume is not None and max_volume >= Decimal("0.75"):
            signal_defs.append((M07MarketSignalCode.SALES_VOLUME_STRONG, "销量强", max_volume, "volume_percentile", "category_or_size", M07Polarity.POSITIVE, None))
        if max_amount is not None and max_amount >= Decimal("0.75"):
            signal_defs.append((M07MarketSignalCode.SALES_AMOUNT_STRONG, "销额强", max_amount, "amount_percentile", "category_or_size", M07Polarity.POSITIVE, None))
        if price_inch_pct is not None and price_inch_pct <= Decimal("0.30"):
            signal_defs.append((M07MarketSignalCode.PRICE_PER_INCH_VALUE, "每英寸价格效率好", D1 - price_inch_pct, "price_per_inch_percentile", "category", M07Polarity.POSITIVE, None))
        if profile.price_change_recent_4w is not None and profile.price_change_recent_4w <= Decimal("-0.03"):
            strength = min(D1, abs(profile.price_change_recent_4w) / Decimal("0.10"))
            signal_defs.append((M07MarketSignalCode.RECENT_PRICE_DROP, "近期价格下探", strength, "price_change_recent_4w", "self", M07Polarity.NEGATIVE, None))
        if profile.sales_growth_recent_4w is not None and profile.sales_growth_recent_4w >= Decimal("0.08"):
            strength = min(D1, profile.sales_growth_recent_4w / Decimal("0.20"))
            signal_defs.append((M07MarketSignalCode.RECENT_SALES_UP, "近期销量上升", strength, "sales_growth_recent_4w", "self", M07Polarity.POSITIVE, None))
        if profile.same_pool_volume_percentile is not None and profile.same_pool_volume_percentile >= Decimal("0.75"):
            signal_defs.append((M07MarketSignalCode.SALES_VOLUME_STRONG, "同池销量强", profile.same_pool_volume_percentile, "same_pool_volume_percentile", "market_pool", M07Polarity.POSITIVE, profile.market_pool_key))
        if profile.same_pool_amount_percentile is not None and profile.same_pool_amount_percentile >= Decimal("0.75"):
            signal_defs.append((M07MarketSignalCode.SALES_AMOUNT_STRONG, "同池销额强", profile.same_pool_amount_percentile, "same_pool_amount_percentile", "market_pool", M07Polarity.POSITIVE, profile.market_pool_key))
        platform_share = _largest_share(profile.platform_share_json)
        if platform_share is not None and platform_share >= Decimal("0.70"):
            signal_defs.append((M07MarketSignalCode.PLATFORM_OVERLAP_STRONG, "平台集中度高", platform_share, "platform_amount_share", "platform", M07Polarity.NEUTRAL, profile.main_platform))
        if profile.sample_status in {M07SampleStatus.INSUFFICIENT, M07SampleStatus.UNKNOWN} or profile.price_wavg is None:
            signal_defs.append((M07MarketSignalCode.SAMPLE_INSUFFICIENT, "市场样本不足", Decimal("1.0000"), "sample_status", "self", M07Polarity.RISK, None))

        records: list[M07MarketSignalRecord] = []
        for code, name, value, metric, scope, polarity, scope_key in signal_defs:
            blocked = code == M07MarketSignalCode.SAMPLE_INSUFFICIENT
            strength = _clamp01(value or D0)
            signal_key = _logic_key(profile.batch_id, profile.sku_code, profile.analysis_window, code.value, scope, rule_version)
            result_hash = stable_hash(
                {
                    "signal_key": signal_key,
                    "signal_value": value,
                    "signal_strength": strength,
                    "basis_metric": metric,
                    "profile_hash": profile.result_hash,
                },
                version="m07-signal-v1",
            )
            records.append(
                M07MarketSignalRecord(
                    market_signal_id=_stable_id("m07sig", signal_key),
                    project_id=profile.project_id,
                    category_code=profile.category_code,
                    batch_id=profile.batch_id,
                    run_id=profile.run_id,
                    module_run_id=profile.module_run_id,
                    sku_market_profile_id=profile.sku_market_profile_id,
                    sku_code=profile.sku_code,
                    model_name=profile.model_name,
                    brand_name=profile.brand_name,
                    signal_key=signal_key,
                    analysis_window=profile.analysis_window,
                    signal_code=code,
                    signal_name=name,
                    signal_value=value,
                    signal_strength=strength,
                    signal_level=signal_level(strength, blocked=blocked),
                    basis_metric=metric,
                    basis_value_json=_signal_basis(profile, metric, value),
                    comparison_scope=scope,
                    comparison_scope_key=scope_key,
                    polarity=polarity,
                    downstream_usage_json=_downstream_usage_json(code),
                    confidence=Decimal("0.3500") if blocked else profile.market_confidence,
                    confidence_level=confidence_level(Decimal("0.3500") if blocked else profile.market_confidence),
                    sample_status=profile.sample_status,
                    quality_flags=profile.quality_flags,
                    evidence_ids=profile.evidence_ids,
                    rule_version=rule_version,
                    input_fingerprint=profile.input_fingerprint,
                    result_hash=result_hash,
                    review_required=blocked,
                    review_status="review_required" if blocked else "auto_pass",
                    review_reason_json={"reason": "market_sample_insufficient"} if blocked else {},
                )
            )
        return records

    def _build_pools_and_members(
        self,
        profiles: list[M07SkuMarketProfileRecord],
        profiles_by_window: dict[str, list[M07SkuMarketMetrics]],
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        pool_rule_version: str,
    ) -> tuple[list[M07ComparablePoolRecord], list[M07MarketPoolMemberRecord]]:
        profiles_by_key = {(profile.sku_code, profile.analysis_window): profile for profile in profiles}
        pools: list[M07ComparablePoolRecord] = []
        members: list[M07MarketPoolMemberRecord] = []
        for target in profiles:
            all_window_profiles = [
                item
                for item in profiles_by_window.get(str(target.analysis_window), [])
                if (item.sku_code, str(item.analysis_window)) in profiles_by_key
            ]
            for pool_type in M07PoolType:
                candidates = self._pool_candidates(target, all_window_profiles, pool_type)
                if not candidates:
                    continue
                pool = self._pool_record(
                    target,
                    candidates,
                    pool_type=pool_type,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    pool_rule_version=pool_rule_version,
                )
                pools.append(pool)
                members.extend(
                    self._member_records(
                        pool,
                        target,
                        [profiles_by_key[(candidate.sku_code, str(candidate.analysis_window))] for candidate in candidates],
                        rule_version=rule_version,
                    )
                )
        return pools, members

    def _pool_candidates(
        self,
        target: M07SkuMarketProfileRecord,
        profiles: list[M07SkuMarketMetrics],
        pool_type: M07PoolType,
    ) -> list[M07SkuMarketMetrics]:
        if pool_type == M07PoolType.SAME_SIZE:
            if target.size_segment == "unknown":
                return []
            return [item for item in profiles if item.size_segment == target.size_segment]
        if pool_type == M07PoolType.ADJACENT_SIZE:
            adjacent = set(M07_ADJACENT_SIZE_SEGMENTS.get(str(target.size_segment), ()))
            if not adjacent:
                return []
            return [item for item in profiles if item.size_segment in adjacent]
        if pool_type == M07PoolType.SAME_PRICE_BAND:
            if target.price_band_category == M07PriceBand.UNKNOWN:
                return []
            return [item for item in profiles if item.price_band_category == target.price_band_category]
        if pool_type == M07PoolType.SIZE_PRICE_BAND:
            adjacent_sizes = set(M07_ADJACENT_SIZE_SEGMENTS.get(str(target.size_segment), ()))
            allowed_sizes = {target.size_segment, *adjacent_sizes} - {"unknown"}
            allowed_bands = _adjacent_price_bands(target.price_band_category)
            if not allowed_sizes or target.price_band_category == M07PriceBand.UNKNOWN:
                return []
            return [
                item
                for item in profiles
                if item.size_segment in allowed_sizes and item.price_band_category in allowed_bands
            ]
        if pool_type == M07PoolType.PLATFORM_OVERLAP:
            return [
                item
                for item in profiles
                if _overlap_score(target.platform_share_json, item.platform_share_json) >= Decimal("0.7000")
            ]
        if pool_type == M07PoolType.MARKET_ACTIVE:
            return [item for item in profiles if item.active_week_count >= 3 and item.sales_volume_total is not None]
        return []

    def _pool_record(
        self,
        target: M07SkuMarketProfileRecord,
        candidates: list[M07SkuMarketMetrics],
        *,
        pool_type: M07PoolType,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        pool_rule_version: str,
    ) -> M07ComparablePoolRecord:
        candidate_codes = sorted({item.sku_code for item in candidates})
        sample_status = _pool_sample_status(len(candidate_codes))
        quality_flags = set()
        if sample_status == M07SampleStatus.INSUFFICIENT:
            quality_flags.add("pool_insufficient")
        elif sample_status == M07SampleStatus.LIMITED:
            quality_flags.add("pool_limited")
        if pool_type in {M07PoolType.SAME_SIZE, M07PoolType.ADJACENT_SIZE, M07PoolType.SIZE_PRICE_BAND} and target.size_segment == "unknown":
            quality_flags.add("size_missing")
        pool_key = _logic_key(batch_id, target.sku_code, target.analysis_window, pool_type.value, rule_version)
        evidence_ids = _unique(evidence_id for item in candidates for evidence_id in item.evidence_ids)
        result_hash = stable_hash(
            {
                "pool_key": pool_key,
                "candidate_sku_codes": candidate_codes,
                "median_price": _median_decimal([item.price_wavg for item in candidates]),
                "median_volume": _median_decimal([item.sales_volume_total for item in candidates]),
                "median_amount": _median_decimal([item.sales_amount_total for item in candidates]),
                "pool_rule_version": pool_rule_version,
            },
            version="m07-pool-v1",
        )
        pool_confidence = _pool_confidence(sample_status, candidates)
        return M07ComparablePoolRecord(
            pool_id=_stable_id("m07pool", pool_key),
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            pool_key=pool_key,
            target_sku_code=target.sku_code,
            target_model_name=target.model_name,
            target_brand_name=target.brand_name,
            analysis_window=target.analysis_window,
            pool_type=pool_type,
            pool_condition_json=_pool_condition(target, pool_type),
            candidate_sku_codes=candidate_codes,
            pool_sku_count=len(candidate_codes),
            valid_member_count=sum(1 for item in candidates if item.market_confidence > 0),
            target_included=target.sku_code in candidate_codes,
            target_size_segment=target.size_segment,
            target_price_band=target.price_band_category,
            median_price=_median_decimal([item.price_wavg for item in candidates]),
            median_volume=_median_decimal([item.sales_volume_total for item in candidates]),
            median_amount=_median_decimal([item.sales_amount_total for item in candidates]),
            price_distribution_json=_distribution([item.price_wavg for item in candidates]),
            volume_distribution_json=_distribution([item.sales_volume_total for item in candidates]),
            amount_distribution_json=_distribution([item.sales_amount_total for item in candidates]),
            platform_distribution_json=_platform_distribution(candidates),
            pool_confidence=pool_confidence,
            sample_status=sample_status,
            basis=_pool_basis(target, pool_type, len(candidate_codes)),
            quality_flags=sorted(quality_flags),
            evidence_ids=evidence_ids,
            rule_version=rule_version,
            pool_rule_version=pool_rule_version,
            input_fingerprint=stable_hash(
                {"target": target.input_fingerprint, "members": sorted(item.input_fingerprint for item in candidates)},
                version="m07-pool-input-v1",
            ),
            result_hash=result_hash,
            review_required=sample_status == M07SampleStatus.INSUFFICIENT,
            review_status="review_required" if sample_status == M07SampleStatus.INSUFFICIENT else "auto_pass",
            review_reason_json={"reason": "pool_insufficient"} if sample_status == M07SampleStatus.INSUFFICIENT else {},
        )

    def _member_records(
        self,
        pool: M07ComparablePoolRecord,
        target: M07SkuMarketProfileRecord,
        members: list[M07SkuMarketProfileRecord],
        *,
        rule_version: str,
    ) -> list[M07MarketPoolMemberRecord]:
        price_values = [member.price_wavg for member in members]
        volume_values = [member.sales_volume_total for member in members]
        amount_values = [member.sales_amount_total for member in members]
        records: list[M07MarketPoolMemberRecord] = []
        for member in sorted(members, key=lambda item: item.sku_code):
            size_relation = _size_relation(target.size_segment, member.size_segment)
            price_relation = _price_band_relation(target.price_band_category, member.price_band_category)
            platform_overlap = _overlap_score(target.platform_share_json, member.platform_share_json)
            channel_overlap = _overlap_score(target.channel_share_json, member.channel_share_json)
            price_gap = _gap(member.price_wavg, target.price_wavg)
            relation_strength = _relation_strength(
                size_relation=size_relation,
                price_relation=price_relation,
                platform_overlap=platform_overlap,
                active_week_count=member.active_week_count,
                market_confidence=member.market_confidence,
            )
            member_key = _logic_key(pool.pool_id, target.sku_code, member.sku_code, rule_version)
            result_hash = stable_hash(
                {
                    "member_key": member_key,
                    "size_relation": size_relation,
                    "price_relation": price_relation,
                    "platform_overlap": platform_overlap,
                    "relation_strength": relation_strength,
                },
                version="m07-pool-member-v1",
            )
            records.append(
                M07MarketPoolMemberRecord(
                    pool_member_id=_stable_id("m07pm", member_key),
                    project_id=pool.project_id,
                    category_code=pool.category_code,
                    batch_id=pool.batch_id,
                    run_id=pool.run_id,
                    module_run_id=pool.module_run_id,
                    pool_id=pool.pool_id,
                    target_sku_code=target.sku_code,
                    member_sku_code=member.sku_code,
                    analysis_window=target.analysis_window,
                    member_model_name=member.model_name,
                    member_brand_name=member.brand_name,
                    is_target_self=target.sku_code == member.sku_code,
                    size_relation=size_relation,
                    price_band_relation=price_relation,
                    platform_overlap_score=platform_overlap,
                    channel_overlap_score=channel_overlap,
                    price_gap_to_target=price_gap,
                    price_gap_pct_to_target=_safe_div(price_gap, target.price_wavg),
                    volume_gap_to_target=_gap(member.sales_volume_total, target.sales_volume_total),
                    amount_gap_to_target=_gap(member.sales_amount_total, target.sales_amount_total),
                    member_price_percentile_in_pool=_percentile(member.price_wavg, price_values),
                    member_volume_percentile_in_pool=_percentile(member.sales_volume_total, volume_values),
                    member_amount_percentile_in_pool=_percentile(member.sales_amount_total, amount_values),
                    member_market_confidence=member.market_confidence,
                    relation_strength=relation_strength,
                    quality_flags=member.quality_flags,
                    evidence_ids=member.evidence_ids,
                    rule_version=rule_version,
                    input_fingerprint=stable_hash(
                        {"pool": pool.input_fingerprint, "member": member.input_fingerprint},
                        version="m07-pool-member-input-v1",
                    ),
                    result_hash=result_hash,
                    review_required=pool.review_required or member.review_required,
                    review_status="review_required" if pool.review_required or member.review_required else "auto_pass",
                    review_reason_json={"reason": "pool_or_member_requires_review"} if pool.review_required or member.review_required else {},
                )
            )
        return records

    def _warnings(self, profiles: list[M07SkuMarketProfileRecord], pools: list[M07ComparablePoolRecord]) -> list[str]:
        warnings: list[str] = []
        if not profiles:
            warnings.append("M07 未生成市场画像，请先确认 M01 清洗和 M03 参数画像是否有可消费数据。")
        full_observed_profiles = [profile for profile in profiles if _is_full_observed_window(profile.analysis_window)]
        if profiles and not full_observed_profiles:
            warnings.append("M07 未生成全量观察窗口市场画像，后续尺寸价格池和销量基线不能高置信使用。")
        if any("size_missing" in profile.quality_flags for profile in full_observed_profiles):
            warnings.append(_size_missing_warning(full_observed_profiles))
        if any("price_missing" in profile.quality_flags for profile in full_observed_profiles):
            warnings.append("部分 SKU 缺少有效价格，价格池和溢价判断需要低置信使用。")
        return warnings

    def _scope_notes(self, profiles: list[M07SkuMarketProfileRecord]) -> list[str]:
        notes: list[str] = []
        if any("observed_window_less_than_52w" in profile.quality_flags for profile in profiles):
            notes.append("当前数据按已导入的 2026 年线上观察窗口分析，不补造 52 周或 12 月伪口径。")
        if any("online_only_channel" in profile.quality_flags for profile in profiles):
            notes.append("当前数据为线上渠道样本，M07 生成线上平台市场画像，不推断线下渠道。")
        return notes

    def _quality_notes(self, profiles: list[M07SkuMarketProfileRecord], pools: list[M07ComparablePoolRecord]) -> list[str]:
        notes: list[str] = []
        if any(profile.sample_status != M07SampleStatus.SUFFICIENT for profile in profiles):
            notes.append("部分 SKU 的周样本偏少，相关市场趋势和增长判断低置信使用。")
        if any("price_missing" in profile.quality_flags for profile in profiles if not _is_full_observed_window(profile.analysis_window)):
            notes.append("部分 SKU 在短周期窗口无成交价格，短周期趋势低置信使用，全量观察窗口仍可用于市场基线。")
        if any(pool.sample_status == M07SampleStatus.INSUFFICIENT for pool in pools):
            notes.append("部分可比池样本不足，下游按低置信使用或进入复核。")
        return notes


def _is_full_observed_window(value: M07AnalysisWindow | str | None) -> bool:
    if isinstance(value, M07AnalysisWindow):
        return value == M07AnalysisWindow.FULL_OBSERVED_WINDOW
    return value == M07AnalysisWindow.FULL_OBSERVED_WINDOW.value


def _size_missing_warning(profiles: Sequence[Any]) -> str:
    category_codes = {str(_category_value(getattr(profile, "category_code", ""))).upper() for profile in profiles}
    if "AC" in category_codes:
        return "部分 SKU 缺少有效空调匹数或安装方式，规格价格池和战场划分需要低置信使用。"
    return "部分 SKU 缺少有效屏幕尺寸，尺寸价格池和战场划分需要低置信使用。"


def _rows_for_window(
    rows: list[M07MarketInputRow],
    window: M07AnalysisWindow,
    global_latest_week: int | None,
) -> list[M07MarketInputRow]:
    if window == M07AnalysisWindow.FULL_OBSERVED_WINDOW:
        return list(rows)
    if window == M07AnalysisWindow.LATEST_WEEK:
        sku_latest = _max_week(row.period_week_index for row in rows)
        return [row for row in rows if row.period_week_index == sku_latest] if sku_latest is not None else []
    window_size = {
        M07AnalysisWindow.RECENT_4W: 4,
        M07AnalysisWindow.RECENT_8W: 8,
        M07AnalysisWindow.RECENT_12W: 12,
    }.get(window)
    if window_size is None or global_latest_week is None:
        return []
    start_week = global_latest_week - window_size + 1
    return [row for row in rows if row.period_week_index is not None and start_week <= row.period_week_index <= global_latest_week]


def _weighted_price(rows: list[M07MarketInputRow]) -> Decimal | None:
    amount = D0
    volume = D0
    for row in rows:
        if row.sales_volume is None or row.sales_amount is None or row.sales_volume <= 0:
            continue
        amount += row.sales_amount
        volume += row.sales_volume
    return _safe_div(amount, volume)


def _weekly_prices(rows: list[M07MarketInputRow]) -> list[Decimal]:
    by_week: dict[int, list[M07MarketInputRow]] = {}
    for row in rows:
        if row.period_week_index is not None:
            by_week.setdefault(row.period_week_index, []).append(row)
    prices: list[Decimal] = []
    for week_rows in by_week.values():
        weighted = _weighted_price(week_rows)
        if weighted is not None:
            prices.append(weighted)
            continue
        avg_prices = [row.avg_price for row in week_rows if row.avg_price is not None]
        if avg_prices:
            prices.append(_median_decimal(avg_prices))
    return prices


def _weekly_volumes(rows: list[M07MarketInputRow]) -> list[Decimal]:
    by_week: dict[int, Decimal] = {}
    for row in rows:
        if row.period_week_index is None or row.sales_volume is None:
            continue
        by_week[row.period_week_index] = by_week.get(row.period_week_index, D0) + row.sales_volume
    return list(by_week.values())


def _trend_metrics(rows: list[M07MarketInputRow], global_latest_week: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {"quality_flags": []}
    if global_latest_week is None:
        result["quality_flags"].append("trend_sample_insufficient")
        return result
    recent = [row for row in rows if row.period_week_index is not None and global_latest_week - 3 <= row.period_week_index <= global_latest_week]
    baseline = [row for row in rows if row.period_week_index is not None and global_latest_week - 7 <= row.period_week_index <= global_latest_week - 4]
    if len({row.period_week_index for row in recent}) < 3:
        result["quality_flags"].append("trend_sample_insufficient")
        return result
    if len({row.period_week_index for row in baseline}) < 3:
        result["quality_flags"].append("baseline_window_insufficient")
        return result
    recent_price = _weighted_price(recent)
    baseline_price = _weighted_price(baseline)
    recent_volume = _sum_decimal(row.sales_volume for row in recent if row.sales_volume is not None)
    baseline_volume = _sum_decimal(row.sales_volume for row in baseline if row.sales_volume is not None)
    recent_amount = _sum_decimal(row.sales_amount for row in recent if row.sales_amount is not None)
    baseline_amount = _sum_decimal(row.sales_amount for row in baseline if row.sales_amount is not None)
    result["price_change_recent_4w"] = _rate_change(recent_price, baseline_price)
    result["sales_growth_recent_4w"] = _rate_change(recent_volume, baseline_volume)
    result["amount_growth_recent_4w"] = _rate_change(recent_amount, baseline_amount)
    return result


def _share_json(rows: list[M07MarketInputRow], field_name: str) -> dict[str, Any]:
    grouped: dict[str, dict[str, Decimal]] = {}
    total_volume = D0
    total_amount = D0
    for row in rows:
        key = getattr(row, field_name) or "unknown"
        item = grouped.setdefault(key, {"sales_volume": D0, "sales_amount": D0})
        if row.sales_volume is not None:
            item["sales_volume"] += row.sales_volume
            total_volume += row.sales_volume
        if row.sales_amount is not None:
            item["sales_amount"] += row.sales_amount
            total_amount += row.sales_amount
    result: dict[str, Any] = {}
    for key, item in sorted(grouped.items()):
        result[key] = {
            "sales_volume": item["sales_volume"],
            "sales_amount": item["sales_amount"],
            "volume_share": _safe_div(item["sales_volume"], total_volume) or D0,
            "amount_share": _safe_div(item["sales_amount"], total_amount) or D0,
        }
    return result


def _quality_flags(
    *,
    rows: list[M07MarketInputRow],
    all_rows: list[M07MarketInputRow],
    size_input: M07SkuSizeInput | None,
    global_week_count: int,
    latest_week_gap: int | None,
    trend: Mapping[str, Any],
    channel_share: Mapping[str, Any],
    platform_share: Mapping[str, Any],
    price_wavg: Decimal | None,
    product_category: str = "TV",
) -> list[str]:
    flags: list[str] = []
    if global_week_count < 52:
        flags.append("observed_window_less_than_52w")
    if set(channel_share) == {"线上"}:
        flags.append("online_only_channel")
    if latest_week_gap is not None and latest_week_gap > 2:
        flags.append("latest_week_gap")
    if price_wavg is None:
        flags.append("price_missing")
    if _market_size_input_missing(product_category, size_input):
        flags.append("size_missing")
    if not platform_share or "unknown" in platform_share:
        flags.append("platform_missing")
    flags.extend(str(flag) for flag in trend.get("quality_flags") or [])
    for row in [*rows, *all_rows]:
        flags.extend(row.quality_flags)
        if row.sales_volume is None:
            flags.append("missing_sales_volume")
        if row.sales_volume == 0 and row.sales_amount and row.sales_amount > 0:
            flags.append("market_amount_without_volume")
    return sorted(set(flags))


def _market_confidence(
    *,
    active_week_count: int,
    sample_status: M07SampleStatus | str,
    price_wavg: Decimal | None,
    size_input: M07SkuSizeInput | None,
    product_category: str = "TV",
    quality_flags: Sequence[str],
) -> Decimal:
    score = Decimal("0.30")
    if active_week_count >= 6:
        score += Decimal("0.25")
    elif active_week_count >= 3:
        score += Decimal("0.15")
    if price_wavg is not None:
        score += Decimal("0.20")
    if not _market_size_input_missing(product_category, size_input):
        score += Decimal("0.15") * size_input.confidence
    if sample_status == M07SampleStatus.SUFFICIENT:
        score += Decimal("0.10")
    elif sample_status == M07SampleStatus.LIMITED:
        score += Decimal("0.05")
    penalty = Decimal("0.04") * Decimal(len({flag for flag in quality_flags if flag not in {"observed_window_less_than_52w", "online_only_channel"}}))
    return _quant4(max(D0, min(D1, score - penalty)))


def _initial_sample_status(active_week_count: int, has_rows: bool) -> M07SampleStatus:
    if not has_rows:
        return M07SampleStatus.UNKNOWN
    if active_week_count >= 6:
        return M07SampleStatus.SUFFICIENT
    if active_week_count >= 3:
        return M07SampleStatus.LIMITED
    return M07SampleStatus.INSUFFICIENT


def _combined_sample_status(
    *,
    active_week_count: int,
    category_count: int,
    size_count: int,
    has_rows: bool,
) -> M07SampleStatus:
    if not has_rows:
        return M07SampleStatus.UNKNOWN
    if active_week_count >= 6 and category_count >= 6:
        return M07SampleStatus.SUFFICIENT
    if active_week_count >= 3 and category_count >= 3 and size_count >= 3:
        return M07SampleStatus.LIMITED
    return M07SampleStatus.INSUFFICIENT


def _profile_window_value(value: str | M07AnalysisWindow) -> str:
    return value.value if isinstance(value, M07AnalysisWindow) else str(value)


def _pool_sample_status(count: int) -> M07SampleStatus:
    if count >= 6:
        return M07SampleStatus.SUFFICIENT
    if count >= 3:
        return M07SampleStatus.LIMITED
    return M07SampleStatus.INSUFFICIENT


def _pool_confidence(sample_status: M07SampleStatus, candidates: list[M07SkuMarketMetrics]) -> Decimal:
    base = {
        M07SampleStatus.SUFFICIENT: Decimal("0.80"),
        M07SampleStatus.LIMITED: Decimal("0.62"),
        M07SampleStatus.INSUFFICIENT: Decimal("0.38"),
        M07SampleStatus.UNKNOWN: Decimal("0.20"),
    }[sample_status]
    if not candidates:
        return Decimal("0.0000")
    avg_confidence = sum((item.market_confidence for item in candidates), D0) / Decimal(len(candidates))
    return _quant4(min(D1, base * Decimal("0.50") + avg_confidence * Decimal("0.50")))


def _normalize_product_category(product_category: str | None, category_code: Any) -> str:
    normalized = str(product_category or _category_value(category_code) or "TV").strip().upper()
    if normalized in {"AC", "AIR_CONDITIONER", "空调"}:
        return "AC"
    return "TV"


def _profile_param_entry(values: Any, param_code: str) -> dict[str, Any] | None:
    if not isinstance(values, Mapping):
        return None
    entry = values.get(param_code)
    return entry if isinstance(entry, dict) else None


def _normalized_text_value(entry: Mapping[str, Any] | None) -> str | None:
    if not entry:
        return None
    for key in ("normalized_value", "value_text", "raw_param_value"):
        value = entry.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _ac_size_segment(installation: str | None, horsepower: Decimal | None, cooling_capacity: Decimal | None) -> str:
    install_segment = _ac_installation_segment(installation)
    hp_segment = _ac_horsepower_segment(horsepower)
    if hp_segment == "hp_unknown":
        hp_segment = _ac_cooling_capacity_segment(cooling_capacity)
    if install_segment == "unknown" and hp_segment == "hp_unknown":
        return "unknown"
    return f"{install_segment if install_segment != 'unknown' else 'ac'}_{hp_segment}"


def _ac_size_class(installation: str | None, horsepower: Decimal | None) -> str:
    install_segment = _ac_installation_segment(installation)
    hp_segment = _ac_horsepower_segment(horsepower)
    if install_segment == "unknown" and hp_segment == "hp_unknown":
        return "unknown"
    if install_segment == "unknown":
        return f"ac_{hp_segment}"
    if hp_segment == "hp_unknown":
        return install_segment
    return f"{install_segment}_{hp_segment}"


def _ac_installation_segment(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if text in {"floor_standing", "floor", "cabinet"} or "柜" in text or "立柜" in text:
        return "floor"
    if text in {"wall_mounted", "wall", "hanging"} or "挂" in text or "壁挂" in text:
        return "wall"
    if text in {"mobile", "portable"} or "移动" in text:
        return "mobile"
    return "unknown"


def _ac_horsepower_segment(value: Decimal | None) -> str:
    if value is None:
        return "hp_unknown"
    if value <= Decimal("1"):
        return "hp_1_or_below"
    if value <= Decimal("1.5"):
        return "hp_1_5"
    if value <= Decimal("2"):
        return "hp_2"
    if value <= Decimal("3"):
        return "hp_3"
    return "hp_3_plus"


def _ac_cooling_capacity_segment(value: Decimal | None) -> str:
    if value is None:
        return "hp_unknown"
    if value < Decimal("3000"):
        return "hp_1_or_below"
    if value < Decimal("4000"):
        return "hp_1_5"
    if value < Decimal("5500"):
        return "hp_2"
    if value < Decimal("7500"):
        return "hp_3"
    return "hp_3_plus"


def _market_size_input_missing(product_category: str, size_input: M07SkuSizeInput | None) -> bool:
    if size_input is None:
        return True
    if product_category == "AC":
        return size_input.size_segment == "unknown"
    return size_input.screen_size_inch is None


def _market_size_class(product_category: str, size_input: M07SkuSizeInput | None) -> str:
    if size_input is None:
        return "unknown"
    if product_category == "AC":
        return _ac_size_class_from_segment(size_input.size_segment)
    return _screen_size_class(size_input.screen_size_inch)


def _ac_size_class_from_segment(size_segment: str) -> str:
    text = str(size_segment or "unknown")
    if text == "unknown":
        return "unknown"
    parts = text.split("_")
    if parts[0] in {"wall", "floor", "mobile"}:
        return text
    return f"ac_{text}"


def _list_or_empty(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple, set)) else []


def _size_segment(value: Decimal | None) -> str:
    number_decimal = _valid_screen_size_number(value)
    if number_decimal is None:
        return "unknown"
    common = [50, 55, 65, 75, 85, 100]
    number = float(number_decimal)
    nearest = min(common, key=lambda item: abs(item - number))
    if abs(nearest - number) <= 2:
        return str(nearest)
    return f"custom_{round(number)}"


def _screen_size_class(value: Decimal | None) -> str:
    number_decimal = _valid_screen_size_number(value)
    if number_decimal is None:
        return "unknown"
    number = float(number_decimal)
    if number <= 43:
        return "compact_screen"
    if number <= 69:
        return "mainstream_living"
    if number <= 89:
        return "large_upgrade"
    return "ultra_large_flagship"


def _market_pool_key(
    category_code: str,
    screen_size_class: str,
    main_channel_type: str | None,
    analysis_window: M07AnalysisWindow | str,
) -> str:
    window = analysis_window.value if isinstance(analysis_window, M07AnalysisWindow) else str(analysis_window)
    channel = _pool_key_part(main_channel_type or "unknown")
    return f"{_pool_key_part(category_code)}:{_pool_key_part(screen_size_class)}:{channel}:{_pool_key_part(window)}"


def _category_value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _pool_key_part(value: str) -> str:
    normalized = str(value or "unknown").strip().lower().replace(" ", "_")
    return normalized or "unknown"


def _screen_size_entry(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    entry = payload.get("screen_size_inch")
    return entry if isinstance(entry, dict) else None


def _select_screen_size_param_value(candidates: Sequence[Any]) -> Any | None:
    valid_values = [
        value
        for value in candidates
        if _valid_screen_size_number(getattr(value, "numeric_value", None)) is not None
        and not _is_screen_size_area_field(value)
    ]
    if not valid_values:
        return None
    return sorted(valid_values, key=_screen_size_param_value_sort_key)[0]


def _screen_size_param_value_sort_key(value: Any) -> tuple[int, int, Decimal, str]:
    return (
        _screen_size_param_field_rank(value),
        int(getattr(value, "source_priority_rank", 99) or 99),
        -(_decimal_or_none(getattr(value, "confidence", None)) or D0),
        str(getattr(value, "param_value_id", "") or ""),
    )


def _screen_size_param_field_rank(value: Any) -> int:
    if _valid_screen_size_number(getattr(value, "numeric_value", None)) is None or _is_screen_size_area_field(value):
        return 90
    raw_name = _screen_size_raw_name(value)
    raw_value = str(getattr(value, "raw_param_value", "") or "")
    source_type = str(getattr(value, "source_type", "") or "")
    if raw_name in SCREEN_SIZE_EXACT_RAW_NAMES:
        return 0
    if source_type == "model_name":
        return 1
    if raw_name in SCREEN_SIZE_RANGE_RAW_NAMES or _looks_like_size_range(raw_value):
        return 4
    if "尺寸" in raw_name or "英寸" in raw_name or raw_name.endswith("寸"):
        return 2
    if source_type == "derived_from_claim":
        return 3
    return 5


def _valid_screen_size_number(value: Any) -> Decimal | None:
    number = _decimal_or_none(value)
    if number is None:
        return None
    if number < SCREEN_SIZE_MIN_INCH or number > SCREEN_SIZE_MAX_INCH:
        return None
    return number


def _is_screen_size_area_field(value: Any) -> bool:
    raw_name = _screen_size_raw_name(value)
    return any(token in raw_name for token in SCREEN_SIZE_AREA_RAW_TOKENS)


def _screen_size_raw_name(value: Any) -> str:
    return str(getattr(value, "raw_param_name", "") or "").strip()


def _looks_like_size_range(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and any(token in text for token in ("-", "~", "～", "至", "以上", "以下", ">=", "<=", "≥", "≤"))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _sum_decimal(values: Iterable[Decimal]) -> Decimal:
    return sum(values, D0)


def _safe_div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _quant6(numerator / denominator)


def _rate_change(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    return _quant6((current - previous) / previous)


def _percentile(value: Decimal | None, values: Iterable[Decimal | None]) -> Decimal | None:
    valid = sorted(item for item in values if item is not None)
    if value is None or not valid:
        return None
    count = sum(1 for item in valid if item <= value)
    return _quant6(Decimal(count) / Decimal(len(valid)))


def _price_band(percentile_value: Decimal | None, sample_count: int) -> str:
    if percentile_value is None or sample_count < 3:
        return M07PriceBand.UNKNOWN.value
    if percentile_value <= Decimal("0.20"):
        return M07PriceBand.LOW.value
    if percentile_value <= Decimal("0.40"):
        return M07PriceBand.MID_LOW.value
    if percentile_value <= Decimal("0.60"):
        return M07PriceBand.MID.value
    if percentile_value <= Decimal("0.80"):
        return M07PriceBand.MID_HIGH.value
    return M07PriceBand.HIGH.value


def _median_decimal(values: Iterable[Decimal | None]) -> Decimal | None:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return _quant6(Decimal(str(median(valid))))


def _coefficient_of_variation(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, D0) / Decimal(len(values))
    if mean == 0:
        return None
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values))
    return _quant6(Decimal(str(float(variance) ** 0.5)) / mean)


def _gap(value: Decimal | None, baseline: Decimal | None) -> Decimal | None:
    if value is None or baseline is None:
        return None
    return _quant6(value - baseline)


def _max_decimal(*values: Decimal | None) -> Decimal | None:
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def _min_decimal(*values: Decimal | None) -> Decimal | None:
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def _quant4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _quant6(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def _clamp01(value: Decimal) -> Decimal:
    return _quant4(max(D0, min(D1, value)))


def _max_week(values: Iterable[int | None]) -> int | None:
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def _min_week(values: Iterable[int | None]) -> int | None:
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def _period_raw_for_week(rows: list[M07MarketInputRow], week_index: int | None) -> str | None:
    if week_index is None:
        return None
    for row in rows:
        if row.period_week_index == week_index and row.period_raw:
            return row.period_raw
    return None


def _main_share_key(share_json: Mapping[str, Any]) -> str | None:
    if not share_json:
        return None
    return max(share_json, key=lambda key: _decimal_or_none(share_json[key].get("amount_share")) or D0)


def _largest_share(share_json: Mapping[str, Any]) -> Decimal | None:
    values = [_decimal_or_none(item.get("amount_share")) for item in share_json.values() if isinstance(item, Mapping)]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def _overlap_score(left: Mapping[str, Any], right: Mapping[str, Any]) -> Decimal:
    score = D0
    for key in set(left) | set(right):
        left_share = _decimal_or_none(left.get(key, {}).get("amount_share") if isinstance(left.get(key), Mapping) else None) or D0
        right_share = _decimal_or_none(right.get(key, {}).get("amount_share") if isinstance(right.get(key), Mapping) else None) or D0
        score += min(left_share, right_share)
    return _clamp01(score)


def _distribution(values: Iterable[Decimal | None]) -> dict[str, Any]:
    valid = sorted(value for value in values if value is not None)
    if not valid:
        return {"count": 0}
    return {
        "count": len(valid),
        "min": valid[0],
        "p50": _median_decimal(valid),
        "max": valid[-1],
    }


def _platform_distribution(candidates: list[M07SkuMarketMetrics]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for item in candidates:
        if item.main_platform:
            counter[str(item.main_platform)] += 1
    return dict(counter)


def _adjacent_price_bands(band: str | M07PriceBand) -> set[str]:
    band_value = band.value if isinstance(band, M07PriceBand) else str(band)
    if band_value == M07PriceBand.UNKNOWN.value:
        return {M07PriceBand.UNKNOWN.value}
    ordered = [item.value for item in M07_PRICE_BAND_ORDER]
    index = ordered.index(band_value)
    values = {band_value}
    if index > 0:
        values.add(ordered[index - 1])
    if index + 1 < len(ordered):
        values.add(ordered[index + 1])
    return values


def _size_relation(target_size: str, member_size: str) -> str:
    if target_size == "unknown" or member_size == "unknown":
        return "unknown"
    if target_size == member_size:
        return "same"
    if member_size in M07_ADJACENT_SIZE_SEGMENTS.get(str(target_size), ()):
        return "adjacent"
    return "different"


def _price_band_relation(target_band: str, member_band: str) -> str:
    if target_band == M07PriceBand.UNKNOWN or member_band == M07PriceBand.UNKNOWN:
        return "unknown"
    target = str(target_band)
    member = str(member_band)
    if target == member:
        return "same"
    ordered = [item.value for item in M07_PRICE_BAND_ORDER]
    if target not in ordered or member not in ordered:
        return "unknown"
    diff = ordered.index(member) - ordered.index(target)
    if abs(diff) == 1:
        return "adjacent"
    return "higher" if diff > 0 else "lower"


def _relation_strength(
    *,
    size_relation: str,
    price_relation: str,
    platform_overlap: Decimal,
    active_week_count: int,
    market_confidence: Decimal,
) -> Decimal:
    size_score = {"same": Decimal("1.0"), "adjacent": Decimal("0.7"), "different": Decimal("0.2")}.get(size_relation, D0)
    price_score = {"same": Decimal("1.0"), "adjacent": Decimal("0.7"), "higher": Decimal("0.4"), "lower": Decimal("0.4")}.get(price_relation, D0)
    market_activity = min(D1, Decimal(active_week_count) / Decimal("6"))
    return _clamp01(
        Decimal("0.30") * size_score
        + Decimal("0.25") * price_score
        + Decimal("0.20") * platform_overlap
        + Decimal("0.15") * market_activity
        + Decimal("0.10") * market_confidence
    )


def _pool_condition(target: M07SkuMarketProfileRecord, pool_type: M07PoolType) -> dict[str, Any]:
    return {
        "pool_type": pool_type.value,
        "category_code": target.category_code,
        "target_size_segment": target.size_segment,
        "target_screen_size_class": target.screen_size_class,
        "market_pool_key": target.market_pool_key,
        "target_price_band": target.price_band_category,
        "analysis_window": target.analysis_window,
        "main_channel_type": target.main_channel_type,
        "brand_filter": "none",
        "allowed_size_segments": sorted({target.size_segment, *M07_ADJACENT_SIZE_SEGMENTS.get(str(target.size_segment), ())}),
        "allowed_price_bands": sorted(_adjacent_price_bands(target.price_band_category)),
    }


def _pool_basis(target: M07SkuMarketProfileRecord, pool_type: M07PoolType, count: int) -> str:
    labels = {
        M07PoolType.SAME_SIZE: f"与 {target.model_name or target.sku_code} 同为 {target.size_segment} 寸尺寸段",
        M07PoolType.ADJACENT_SIZE: f"与 {target.model_name or target.sku_code} 处在相邻尺寸段",
        M07PoolType.SAME_PRICE_BAND: f"与 {target.model_name or target.sku_code} 同处 {target.price_band_category} 价格带",
        M07PoolType.SIZE_PRICE_BAND: "同/相邻尺寸且同/相邻价格带，适合作为市场可比基线",
        M07PoolType.PLATFORM_OVERLAP: "平台销售结构重合，适合作为渠道平台比较基线",
        M07PoolType.MARKET_ACTIVE: "观察期内有连续市场销售事实，适合作为活跃市场基线",
    }
    return f"{labels[pool_type]}，池内共 {count} 个 SKU；M07 不按品牌排除，也不等同最终竞品。"


def _signal_basis(profile: M07SkuMarketProfileRecord, metric: str, value: Decimal | None) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "analysis_window": profile.analysis_window,
        "price_wavg": profile.price_wavg,
        "sales_volume_total": profile.sales_volume_total,
        "sales_amount_total": profile.sales_amount_total,
        "price_percentile_in_category": profile.price_percentile_in_category,
        "price_percentile_in_size": profile.price_percentile_in_size,
        "same_pool_price_percentile": profile.same_pool_price_percentile,
        "same_pool_volume_percentile": profile.same_pool_volume_percentile,
        "same_pool_amount_percentile": profile.same_pool_amount_percentile,
        "price_per_inch_percentile": profile.price_per_inch_percentile,
        "market_pool_key": profile.market_pool_key,
        "screen_size_class": profile.screen_size_class,
        "sample_status": profile.sample_status,
    }


def _downstream_usage_json(code: M07MarketSignalCode) -> dict[str, Any]:
    return {
        "M09": {
            "allowed": True,
            "usage": "market_support_for_task",
            "cannot_alone_determine_task": True,
        },
        "M10": {
            "allowed": True,
            "usage": "market_fit_cue",
            "cannot_alone_determine_target_group": True,
        },
        "M11": {
            "allowed": True,
            "usage": "battlefield_market_support",
            "cannot_alone_determine_battlefield": True,
        },
        "M13": {"allowed": True, "usage": "market_pressure_component"},
        "M15": {"display_as_market_evidence_only": True},
        "signal_code": code.value,
    }


def _review_reason(item: M07SkuMarketMetrics) -> dict[str, Any]:
    reasons = []
    if item.market_row_count == 0:
        reasons.append("missing_market")
    if item.size_segment == "unknown":
        reasons.append("size_missing")
    if item.sample_status in {M07SampleStatus.INSUFFICIENT, M07SampleStatus.UNKNOWN}:
        reasons.append("market_sample_limited")
    return {"reasons": reasons} if reasons else {}


def _logic_key(*parts: Any) -> str:
    return "|".join(str(part.value if isinstance(part, Enum) else part) for part in parts)


def _stable_id(prefix: str, payload: Any) -> str:
    digest = stable_hash(payload, version=f"{prefix}-id-v1").split(":")[-1]
    return f"{prefix}_{digest[:32]}"


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(str(value))
        seen.add(str(value))
    return result


def _first_present(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None
