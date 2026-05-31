from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    CategoryProject,
    ClaimValueLayerResult,
    RawMarketFact,
    SkuClaimResult,
    SkuCommentTopicResult,
    StdClaimDef,
)
from app.services.factory_utils import ensure_seed_assets
from app.services.utils import safe_median, unique_list


MIN_COMPARABLE_SAMPLE = 2


def calculate_market_metrics(db: Session, project_id: str) -> dict:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    ensure_seed_assets(db, project_id, project.category_code)
    db.execute(delete(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == project_id))

    markets = [
        row
        for row in db.execute(
            select(RawMarketFact).where(RawMarketFact.project_id == project_id)
        ).scalars()
        if row.sku_code
    ]
    all_skus = {row.sku_code for row in markets if row.sku_code}
    market_by_sku = {row.sku_code: row for row in markets if row.sku_code}
    claims_by_code: dict[str, list[SkuClaimResult]] = {}
    for row in db.execute(
        select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)
    ).scalars():
        claims_by_code.setdefault(row.claim_code, []).append(row)

    claim_defs = db.execute(
        select(StdClaimDef).where(StdClaimDef.project_id == project_id)
    ).scalars().all()
    created = 0
    for claim_def in claim_defs:
        claim_rows = claims_by_code.get(claim_def.claim_code, [])
        with_claim = {row.sku_code for row in claim_rows}
        without_claim = all_skus - with_claim
        coverage = len(with_claim) / len(all_skus) if all_skus else 0.0
        with_prices = [market_by_sku[sku].avg_price for sku in with_claim if sku in market_by_sku and market_by_sku[sku].avg_price is not None]
        without_prices = [market_by_sku[sku].avg_price for sku in without_claim if sku in market_by_sku and market_by_sku[sku].avg_price is not None]
        with_sales = [market_by_sku[sku].sales_volume for sku in with_claim if sku in market_by_sku and market_by_sku[sku].sales_volume is not None]
        without_sales = [market_by_sku[sku].sales_volume for sku in without_claim if sku in market_by_sku and market_by_sku[sku].sales_volume is not None]
        comparable_count = min(len(with_prices), len(without_prices))

        psi = None
        ssi = None
        confidence = 0.45
        layer = "pending_validation"
        if comparable_count >= MIN_COMPARABLE_SAMPLE:
            with_price = safe_median(with_prices)
            without_price = safe_median(without_prices)
            if with_price and without_price:
                psi = with_price / without_price - 1
            with_sales_share = sum(with_sales) / max(1.0, sum(with_sales + without_sales))
            without_sales_share = sum(without_sales) / max(1.0, sum(with_sales + without_sales))
            if without_sales_share:
                ssi = with_sales_share / without_sales_share - 1
            confidence = 0.72
            if coverage >= 0.7 and (psi is None or abs(psi) < 0.08) and (ssi is None or abs(ssi) < 0.15):
                layer = "baseline_threshold"
            elif (psi or 0) > 0.12 or (ssi or 0) > 0.25:
                layer = "premium_or_sales_support"
            else:
                layer = "performance_signal"

        cpi = _comment_perception_index(db, project_id, claim_def.comment_topic_codes)
        db.add(
            ClaimValueLayerResult(
                project_id=project_id,
                category_code=project.category_code,
                claim_code=claim_def.claim_code,
                coverage_rate=round(coverage, 4),
                psi=psi,
                ssi=ssi,
                cpi=cpi,
                comparable_sample_count=comparable_count,
                layer=layer,
                confidence=confidence,
                evidence_ids=unique_list([e for row in claim_rows for e in row.evidence_ids]),
            )
        )
        created += 1

    db.commit()
    return {
        "step": "calculate_market_metrics",
        "status": "completed",
        "counts": {"claim_value_layers": created, "sku_count": len(all_skus)},
        "message": "市场指标与卖点价值分层完成",
    }


def _comment_perception_index(db: Session, project_id: str, topic_codes: list[str]) -> float | None:
    if not topic_codes:
        return None
    rows = db.execute(
        select(SkuCommentTopicResult).where(
            SkuCommentTopicResult.project_id == project_id,
            SkuCommentTopicResult.topic_code.in_(topic_codes),
        )
    ).scalars().all()
    if not rows:
        return None
    positive = len([row for row in rows if row.sentiment == "positive"])
    negative = len([row for row in rows if row.sentiment == "negative"])
    return round((positive - negative) / max(1, positive + negative), 4)

