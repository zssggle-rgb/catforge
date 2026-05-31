from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    CategoryProject,
    ClaimValueLayerResult,
    DataQualityIssue,
    RawMarketFact,
    ReviewQueue,
    SkuClaimResult,
    SkuParamNormalized,
)
from app.services.utils import unique_list


def build_review_queue(db: Session, project_id: str) -> dict:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    db.execute(delete(ReviewQueue).where(ReviewQueue.project_id == project_id))
    created = 0

    for issue in db.execute(
        select(DataQualityIssue).where(DataQualityIssue.project_id == project_id)
    ).scalars():
        if issue.severity == "critical":
            _add_review(
                db,
                project,
                item_type="data_quality",
                item_key=issue.issue_id,
                reason_code=issue.issue_code,
                evidence_ids=[],
                candidate_payload={"message": issue.message, "field": issue.field_name},
                confidence=0.2,
                priority="critical",
            )
            created += 1

    for claim in db.execute(
        select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)
    ).scalars():
        if claim.confidence < 0.82:
            _add_review(
                db,
                project,
                item_type="claim",
                item_key=f"{claim.sku_code}:{claim.claim_code}",
                reason_code="low_confidence",
                evidence_ids=claim.evidence_ids,
                candidate_payload={"sku_code": claim.sku_code, "claim_code": claim.claim_code},
                confidence=claim.confidence,
                priority="medium",
            )
            created += 1

    params_by_sku: dict[str, dict[str, SkuParamNormalized]] = {}
    for param in db.execute(
        select(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id)
    ).scalars():
        params_by_sku.setdefault(param.sku_code, {})[param.param_code] = param
        if param.normalized_value == "unknown":
            _add_review(
                db,
                project,
                item_type="param",
                item_key=f"{param.sku_code}:{param.param_code}",
                reason_code="unknown_field",
                evidence_ids=param.evidence_ids,
                candidate_payload={"sku_code": param.sku_code, "param_code": param.param_code},
                confidence=param.confidence,
                priority="low",
            )
            created += 1

    for sku_code, params in params_by_sku.items():
        native = params.get("native_refresh_rate_hz")
        system = params.get("system_refresh_rate_hz")
        if native and system and native.normalized_numeric and system.normalized_numeric and native.normalized_numeric != system.normalized_numeric:
            _add_review(
                db,
                project,
                item_type="param",
                item_key=f"{sku_code}:refresh_rate",
                reason_code="param_conflict",
                evidence_ids=unique_list(native.evidence_ids + system.evidence_ids),
                candidate_payload={
                    "sku_code": sku_code,
                    "native_refresh_rate_hz": native.normalized_numeric,
                    "system_refresh_rate_hz": system.normalized_numeric,
                },
                confidence=min(native.confidence, system.confidence),
                priority="high",
            )
            created += 1

    market_rows = db.execute(
        select(RawMarketFact).where(RawMarketFact.project_id == project_id)
    ).scalars().all()
    if market_rows:
        top_sales_amount = max((row.sales_amount or 0) for row in market_rows)
        for row in market_rows:
            if (row.sales_amount or 0) >= top_sales_amount or (row.avg_price or 0) >= 9000:
                _add_review(
                    db,
                    project,
                    item_type="sku",
                    item_key=row.sku_code or "",
                    reason_code="high_value_sku",
                    evidence_ids=[],
                    candidate_payload={
                        "sku_code": row.sku_code,
                        "avg_price": row.avg_price,
                        "sales_amount": row.sales_amount,
                    },
                    confidence=0.7,
                    priority="high",
                )
                created += 1

    for metric in db.execute(
        select(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == project_id)
    ).scalars():
        if metric.layer == "pending_validation":
            _add_review(
                db,
                project,
                item_type="market_metric",
                item_key=metric.claim_code,
                reason_code="insufficient_sample",
                evidence_ids=metric.evidence_ids,
                candidate_payload={
                    "claim_code": metric.claim_code,
                    "coverage_rate": metric.coverage_rate,
                    "comparable_sample_count": metric.comparable_sample_count,
                },
                confidence=metric.confidence,
                priority="medium",
            )
            created += 1

    db.commit()
    return {
        "step": "build_review_queue",
        "status": "completed",
        "counts": {"review_items": created},
        "message": "复核队列已生成",
    }


def apply_review_decision(
    db: Session,
    review_id: str,
    *,
    decision: str,
    reviewer: str,
    decision_payload: dict | None,
) -> ReviewQueue:
    item = db.get(ReviewQueue, review_id)
    if not item:
        raise ValueError("复核项不存在")
    item.status = decision
    item.reviewer = reviewer
    item.decision_payload = decision_payload or {}
    db.commit()
    db.refresh(item)
    return item


def _add_review(
    db: Session,
    project: CategoryProject,
    *,
    item_type: str,
    item_key: str,
    reason_code: str,
    evidence_ids: list[str],
    candidate_payload: dict,
    confidence: float,
    priority: str,
) -> None:
    db.add(
        ReviewQueue(
            project_id=project.project_id,
            category_code=project.category_code,
            item_type=item_type,
            item_key=item_key,
            reason_code=reason_code,
            evidence_ids=unique_list(evidence_ids),
            candidate_payload=candidate_payload,
            confidence=confidence,
            priority=priority,
            status="pending",
        )
    )

