from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    CategoryProject,
    ClaimValueLayerResult,
    DataQualityIssue,
    RawMarketFact,
    ReviewQueue,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuParamNormalized,
    SkuTaskScore,
)
from app.services.audit_service import create_audit_event
from app.services.utils import unique_list


OBJECT_LABELS = {
    "data_quality": "数据质量问题",
    "claim": "SKU 卖点结果",
    "param": "SKU 参数归一结果",
    "sku": "高价值 SKU 标记",
    "market_metric": "卖点市场分层结果",
    "task": "用户任务评分",
    "battlefield": "价值战场评分",
}

REASON_LABELS = {
    "missing_required_field": "必填字段缺失",
    "low_confidence": "置信度偏低",
    "unknown_field": "字段无法确定",
    "param_conflict": "参数来源冲突",
    "high_value_sku": "高价值 SKU 需要人工确认",
    "insufficient_sample": "样本不足",
}


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

    for task in db.execute(
        select(SkuTaskScore).where(SkuTaskScore.project_id == project_id)
    ).scalars():
        if task.review_status == "needs_review" or task.confidence < 0.65:
            _add_review(
                db,
                project,
                item_type="task",
                item_key=f"{task.sku_code}:{task.task_code}",
                reason_code="low_confidence",
                evidence_ids=task.evidence_ids,
                candidate_payload={
                    "sku_code": task.sku_code,
                    "task_code": task.task_code,
                    "score": task.score,
                    "relation_level": task.relation_level,
                },
                confidence=task.confidence,
                priority="medium",
            )
            created += 1

    for battlefield in db.execute(
        select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id)
    ).scalars():
        if battlefield.review_status == "needs_review" or battlefield.confidence < 0.65:
            _add_review(
                db,
                project,
                item_type="battlefield",
                item_key=f"{battlefield.sku_code}:{battlefield.battlefield_code}",
                reason_code="low_confidence",
                evidence_ids=battlefield.evidence_ids,
                candidate_payload={
                    "sku_code": battlefield.sku_code,
                    "battlefield_code": battlefield.battlefield_code,
                    "score": battlefield.score,
                    "relation_level": battlefield.relation_level,
                },
                confidence=battlefield.confidence,
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
    _apply_decision_to_target(db, item, decision=decision, decision_payload=decision_payload or {})
    create_audit_event(
        db,
        action=f"asset_review_{decision}",
        object_type="review_queue",
        object_id=item.review_id,
        project_id=item.project_id,
        actor_id=reviewer,
        after={
            "review_id": item.review_id,
            "item_type": item.item_type,
            "item_key": item.item_key,
            "decision": decision,
        },
        metadata={"decision_payload": decision_payload or {}},
    )
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
    enriched_payload = {
        **candidate_payload,
        "review_context": {
            "object_type": item_type,
            "object_type_label": OBJECT_LABELS.get(item_type, item_type),
            "reason_label": REASON_LABELS.get(reason_code, reason_code),
            "decision_target": _decision_target(item_type, candidate_payload),
            "result_feedback": _result_feedback_hint(item_type),
        },
    }
    db.add(
        ReviewQueue(
            project_id=project.project_id,
            category_code=project.category_code,
            item_type=item_type,
            item_key=item_key,
            reason_code=reason_code,
            evidence_ids=unique_list(evidence_ids),
            candidate_payload=enriched_payload,
            confidence=confidence,
            priority=priority,
            status="pending",
        )
    )


def _apply_decision_to_target(
    db: Session, item: ReviewQueue, *, decision: str, decision_payload: dict
) -> None:
    target_status = {
        "approved": "accepted",
        "rejected": "rejected",
        "edited": "accepted",
    }[decision]
    review_status = {
        "approved": "approved",
        "rejected": "rejected",
        "edited": "edited",
    }[decision]
    if item.item_type == "claim":
        sku_code, claim_code = _split_item_key(item.item_key)
        row = db.execute(
            select(SkuClaimResult).where(
                SkuClaimResult.project_id == item.project_id,
                SkuClaimResult.sku_code == sku_code,
                SkuClaimResult.claim_code == claim_code,
            )
        ).scalar_one_or_none()
        if row:
            row.review_status = review_status
            row.status = target_status
            if decision == "edited":
                if "score" in decision_payload:
                    row.score = float(decision_payload["score"])
                if "confidence" in decision_payload:
                    row.confidence = float(decision_payload["confidence"])
                if "extracted_values" in decision_payload:
                    row.extracted_values = decision_payload["extracted_values"]
        return
    if item.item_type == "param":
        sku_code, param_code = _split_item_key(item.item_key)
        rows = []
        if param_code == "refresh_rate":
            rows = db.execute(
                select(SkuParamNormalized).where(
                    SkuParamNormalized.project_id == item.project_id,
                    SkuParamNormalized.sku_code == sku_code,
                    SkuParamNormalized.param_code.in_(["native_refresh_rate_hz", "system_refresh_rate_hz"]),
                )
            ).scalars().all()
        else:
            row = db.execute(
                select(SkuParamNormalized).where(
                    SkuParamNormalized.project_id == item.project_id,
                    SkuParamNormalized.sku_code == sku_code,
                    SkuParamNormalized.param_code == param_code,
                )
            ).scalar_one_or_none()
            rows = [row] if row else []
        for row in rows:
            row.review_status = review_status
            row.status = target_status
            if decision == "edited" and "normalized_value" in decision_payload:
                row.normalized_value = str(decision_payload["normalized_value"])
                row.raw_value = str(decision_payload["normalized_value"])
        return
    if item.item_type == "task":
        sku_code, task_code = _split_item_key(item.item_key)
        row = db.execute(
            select(SkuTaskScore).where(
                SkuTaskScore.project_id == item.project_id,
                SkuTaskScore.sku_code == sku_code,
                SkuTaskScore.task_code == task_code,
            )
        ).scalar_one_or_none()
        if row:
            row.review_status = review_status
            row.status = target_status
        return
    if item.item_type == "battlefield":
        sku_code, battlefield_code = _split_item_key(item.item_key)
        row = db.execute(
            select(SkuBattlefieldScore).where(
                SkuBattlefieldScore.project_id == item.project_id,
                SkuBattlefieldScore.sku_code == sku_code,
                SkuBattlefieldScore.battlefield_code == battlefield_code,
            )
        ).scalar_one_or_none()
        if row:
            row.review_status = review_status
            row.status = target_status
        return
    if item.item_type == "market_metric":
        row = db.execute(
            select(ClaimValueLayerResult).where(
                ClaimValueLayerResult.project_id == item.project_id,
                ClaimValueLayerResult.claim_code == item.item_key,
            )
        ).scalar_one_or_none()
        if row:
            row.status = target_status


def _decision_target(item_type: str, payload: dict) -> str:
    if item_type == "claim":
        return f"{payload.get('sku_code')} 的卖点 {payload.get('claim_code')}"
    if item_type == "param":
        return f"{payload.get('sku_code')} 的参数 {payload.get('param_code', 'refresh_rate')}"
    if item_type == "task":
        return f"{payload.get('sku_code')} 的用户任务 {payload.get('task_code')}"
    if item_type == "battlefield":
        return f"{payload.get('sku_code')} 的价值战场 {payload.get('battlefield_code')}"
    if item_type == "market_metric":
        return f"卖点 {payload.get('claim_code')} 的市场分层"
    if item_type == "sku":
        return f"SKU {payload.get('sku_code')}"
    return payload.get("message") or item_type


def _result_feedback_hint(item_type: str) -> str:
    if item_type in {"claim", "param", "task", "battlefield", "market_metric"}:
        return "复核决定会同步写回对应分析结果的 review_status/status。"
    return "复核决定保留在队列记录中，用于问题闭环追踪。"


def _split_item_key(item_key: str) -> tuple[str, str]:
    left, _, right = item_key.partition(":")
    return left, right
