from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.entities import Core3PipelineRun, Core3SkuMarketProfile, RawMarketFact
from app.services.core3_mvp.data_access import Core3InputBundle, is_unknown
from app.services.core3_mvp.evidence_graph import get_or_create_evidence


@dataclass(frozen=True)
class MarketProfile:
    sku_code: str
    brand: str | None
    model_name: str | None
    series: str | None
    price_wavg_12m: float | None
    price_latest: float | None
    sales_volume_12m: float | None
    sales_amount_12m: float | None
    channel_share: dict[str, float]
    price_drop_rate_3m: float | None
    sales_growth_3m: float | None
    price_percentile: float | None
    sales_percentile: float | None
    sales_amount_percentile: float | None
    evidence_ids: list[str]
    missing_signals: list[str]
    confidence: float


def build_market_profiles(
    db: Session,
    run: Core3PipelineRun,
    bundle: Core3InputBundle,
    target_sku_codes: list[str],
) -> list[Core3SkuMarketProfile]:
    computed = compute_market_profiles(bundle)
    db.execute(delete(Core3SkuMarketProfile).where(Core3SkuMarketProfile.run_id == run.run_id))
    rows: list[Core3SkuMarketProfile] = []
    for sku_code in target_sku_codes:
        profile = computed.get(sku_code) or _empty_market_profile(bundle, sku_code)
        evidence_ids = _market_evidence_ids(db, run, profile, bundle)
        row = Core3SkuMarketProfile(
            run_id=run.run_id,
            project_id=run.project_id,
            category_code=run.category_code,
            sku_code=profile.sku_code,
            brand=profile.brand,
            model_name=profile.model_name,
            series=profile.series,
            price_wavg_12m=profile.price_wavg_12m,
            price_latest=profile.price_latest,
            sales_volume_12m=profile.sales_volume_12m,
            sales_amount_12m=profile.sales_amount_12m,
            channel_share=profile.channel_share,
            price_drop_rate_3m=profile.price_drop_rate_3m,
            sales_growth_3m=profile.sales_growth_3m,
            price_percentile=profile.price_percentile,
            sales_percentile=profile.sales_percentile,
            sales_amount_percentile=profile.sales_amount_percentile,
            evidence_ids=evidence_ids,
            missing_signals=profile.missing_signals,
            confidence=profile.confidence,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def compute_market_profiles(bundle: Core3InputBundle) -> dict[str, MarketProfile]:
    masters = {str(row.sku_code).strip(): row for row in bundle.sku_master if not is_unknown(row.sku_code)}
    facts_by_sku: dict[str, list[RawMarketFact]] = defaultdict(list)
    for fact in bundle.market_facts:
        if not is_unknown(fact.sku_code):
            facts_by_sku[str(fact.sku_code).strip()].append(fact)

    base: dict[str, MarketProfile] = {}
    for sku_code in sorted(set(masters) | set(facts_by_sku)):
        rows = _last_12_period_rows(facts_by_sku.get(sku_code, []))
        base[sku_code] = _compute_one_profile(sku_code, masters.get(sku_code), rows)

    _apply_percentiles(base)
    return base


def _compute_one_profile(sku_code: str, master: Any, rows: list[RawMarketFact]) -> MarketProfile:
    sales_volume = _sum_known(row.sales_volume for row in rows)
    sales_amount = _sum_known(row.sales_amount for row in rows)
    price_wavg = _weighted_price(rows, fallback_to_avg=True)
    latest_rows = _latest_rows(rows)
    price_latest = _latest_price(latest_rows)
    channel_share = _channel_share(rows)
    periods = sorted({str(row.period) for row in rows if not is_unknown(row.period)})
    price_drop = _price_drop_rate(rows)
    sales_growth = _sales_growth(rows)
    missing = _missing_signals(
        price_wavg=price_wavg,
        price_latest=price_latest,
        sales_volume=sales_volume,
        channel_share=channel_share,
        period_count=len(periods),
    )
    return MarketProfile(
        sku_code=sku_code,
        brand=getattr(master, "brand", None),
        model_name=getattr(master, "model_name", None),
        series=getattr(master, "series", None),
        price_wavg_12m=price_wavg,
        price_latest=price_latest,
        sales_volume_12m=sales_volume,
        sales_amount_12m=sales_amount,
        channel_share=channel_share,
        price_drop_rate_3m=price_drop,
        sales_growth_3m=sales_growth,
        price_percentile=None,
        sales_percentile=None,
        sales_amount_percentile=None,
        evidence_ids=[],
        missing_signals=missing,
        confidence=_confidence(price_wavg, price_latest, sales_volume, channel_share, len(periods)),
    )


def _empty_market_profile(bundle: Core3InputBundle, sku_code: str) -> MarketProfile:
    master = next((row for row in bundle.sku_master if row.sku_code == sku_code), None)
    return MarketProfile(
        sku_code=sku_code,
        brand=getattr(master, "brand", None),
        model_name=getattr(master, "model_name", None),
        series=getattr(master, "series", None),
        price_wavg_12m=None,
        price_latest=None,
        sales_volume_12m=None,
        sales_amount_12m=None,
        channel_share={},
        price_drop_rate_3m=None,
        sales_growth_3m=None,
        price_percentile=None,
        sales_percentile=None,
        sales_amount_percentile=None,
        evidence_ids=[],
        missing_signals=["missing_price", "missing_sales", "missing_channel", "missing_latest_price"],
        confidence=0.25,
    )


def _market_evidence_ids(
    db: Session,
    run: Core3PipelineRun,
    profile: MarketProfile,
    bundle: Core3InputBundle,
) -> list[str]:
    rows = [row for row in bundle.market_facts if str(row.sku_code or "").strip() == profile.sku_code]
    if not rows:
        return []
    source_ref = {
        "table": "raw_market_fact",
        "sku_code": profile.sku_code,
        "period_window": sorted({str(row.period) for row in rows if not is_unknown(row.period)}),
        "raw_refs": [
            {
                "source_file_id": row.source_file_id,
                "raw_row_id": row.raw_row_id,
                "period": row.period,
                "channel": _channel_key(row),
            }
            for row in rows
        ],
        "aggregation": "sum_or_weighted_average",
        "run_id": run.run_id,
    }
    evidence_ids: list[str] = []
    for field_name, value in [
        ("market.price_wavg_12m", profile.price_wavg_12m),
        ("market.price_latest", profile.price_latest),
        ("market.sales_volume_12m", profile.sales_volume_12m),
        ("market.sales_amount_12m", profile.sales_amount_12m),
        ("market.channel_share", profile.channel_share),
        ("market.price_drop_rate_3m", profile.price_drop_rate_3m),
        ("market.sales_growth_3m", profile.sales_growth_3m),
    ]:
        if value is None or value == {}:
            continue
        evidence = get_or_create_evidence(
            db,
            project_id=run.project_id,
            category_code=run.category_code,
            sku_code=profile.sku_code,
            source_type="market_aggregate",
            source_file_id=None,
            raw_row_id=None,
            field_name=field_name,
            raw_value=profile.sku_code,
            normalized_value=value,
            source_ref={**source_ref, "field_name": field_name},
            confidence=profile.confidence,
        )
        evidence_ids.append(evidence.evidence_id)
    return evidence_ids


def _last_12_period_rows(rows: list[RawMarketFact]) -> list[RawMarketFact]:
    periods = sorted({str(row.period) for row in rows if not is_unknown(row.period)})
    if not periods:
        return rows
    keep = set(periods[-12:])
    return [row for row in rows if str(row.period) in keep]


def _latest_rows(rows: list[RawMarketFact]) -> list[RawMarketFact]:
    periods = sorted({str(row.period) for row in rows if not is_unknown(row.period)})
    if not periods:
        return rows
    latest = periods[-1]
    return [row for row in rows if str(row.period) == latest]


def _sum_known(values: Any) -> float | None:
    known = [float(value) for value in values if value is not None]
    if not known:
        return None
    return round(sum(known), 4)


def _weighted_price(rows: list[RawMarketFact], *, fallback_to_avg: bool = False) -> float | None:
    amount = _sum_known(row.sales_amount for row in rows)
    volume = _sum_known(row.sales_volume for row in rows)
    if amount is not None and volume and volume > 0:
        return round(amount / volume, 4)
    weighted_rows = [row for row in rows if row.avg_price is not None and row.sales_volume is not None and row.sales_volume > 0]
    if weighted_rows:
        weighted = sum(float(row.avg_price) * float(row.sales_volume) for row in weighted_rows)
        total_weight = sum(float(row.sales_volume) for row in weighted_rows)
        return round(weighted / total_weight, 4)
    if fallback_to_avg:
        prices = [float(row.avg_price) for row in rows if row.avg_price is not None]
        if prices:
            return round(sum(prices) / len(prices), 4)
    return None


def _latest_price(rows: list[RawMarketFact]) -> float | None:
    return _weighted_price(rows, fallback_to_avg=True)


def _channel_share(rows: list[RawMarketFact]) -> dict[str, float]:
    values: dict[str, float] = defaultdict(float)
    metric = "volume" if any(row.sales_volume is not None for row in rows) else "amount"
    for row in rows:
        value = row.sales_volume if metric == "volume" else row.sales_amount
        if value is None:
            continue
        values[_channel_key(row)] += float(value)
    total = sum(values.values())
    if total <= 0:
        return {}
    return {key: round(value / total, 4) for key, value in sorted(values.items())}


def _channel_key(row: RawMarketFact) -> str:
    for value in [row.channel_name, row.channel_type, row.channel_group]:
        if not is_unknown(value):
            return str(value).strip()
    return "unknown"


def _price_drop_rate(rows: list[RawMarketFact]) -> float | None:
    latest, previous = _latest_and_previous_windows(rows)
    latest_price = _weighted_price(latest, fallback_to_avg=True)
    previous_price = _weighted_price(previous, fallback_to_avg=True)
    if latest_price is None or previous_price in {None, 0}:
        return None
    return round((previous_price - latest_price) / previous_price, 4)


def _sales_growth(rows: list[RawMarketFact]) -> float | None:
    latest, previous = _latest_and_previous_windows(rows)
    latest_volume = _sum_known(row.sales_volume for row in latest)
    previous_volume = _sum_known(row.sales_volume for row in previous)
    if latest_volume is None or previous_volume in {None, 0}:
        return None
    return round((latest_volume - previous_volume) / previous_volume, 4)


def _latest_and_previous_windows(rows: list[RawMarketFact]) -> tuple[list[RawMarketFact], list[RawMarketFact]]:
    periods = sorted({str(row.period) for row in rows if not is_unknown(row.period)})
    latest_periods = set(periods[-3:])
    previous_periods = set(periods[-6:-3])
    return (
        [row for row in rows if str(row.period) in latest_periods],
        [row for row in rows if str(row.period) in previous_periods],
    )


def _missing_signals(
    *,
    price_wavg: float | None,
    price_latest: float | None,
    sales_volume: float | None,
    channel_share: dict[str, float],
    period_count: int,
) -> list[str]:
    missing: list[str] = []
    if price_wavg is None:
        missing.append("missing_price")
    if sales_volume is None or sales_volume <= 0:
        missing.append("missing_sales")
    if not channel_share:
        missing.append("missing_channel")
    if period_count < 3:
        missing.append("insufficient_periods")
    if price_latest is None:
        missing.append("missing_latest_price")
    return missing


def _confidence(
    price_wavg: float | None,
    price_latest: float | None,
    sales_volume: float | None,
    channel_share: dict[str, float],
    period_count: int,
) -> float:
    score = 1.0
    if price_wavg is None:
        score -= 0.25
    if sales_volume is None or sales_volume <= 0:
        score -= 0.25
    if not channel_share:
        score -= 0.15
    if period_count < 3:
        score -= 0.10
    if price_latest is None:
        score -= 0.10
    return round(max(0.1, score), 4)


def _apply_percentiles(profiles: dict[str, MarketProfile]) -> None:
    price_percentiles = _percentiles({sku: row.price_wavg_12m for sku, row in profiles.items()})
    sales_percentiles = _percentiles({sku: row.sales_volume_12m for sku, row in profiles.items()})
    amount_percentiles = _percentiles({sku: row.sales_amount_12m for sku, row in profiles.items()})
    for sku_code, row in list(profiles.items()):
        profiles[sku_code] = MarketProfile(
            **{
                **row.__dict__,
                "price_percentile": price_percentiles.get(sku_code),
                "sales_percentile": sales_percentiles.get(sku_code),
                "sales_amount_percentile": amount_percentiles.get(sku_code),
            }
        )


def _percentiles(values: dict[str, float | None]) -> dict[str, float]:
    known = sorted((float(value), sku) for sku, value in values.items() if value is not None)
    count = len(known)
    if not count:
        return {}
    return {sku: round((index + 1) / count, 4) for index, (_, sku) in enumerate(known)}
