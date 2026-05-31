from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    BattlefieldDef,
    ClaimValueLayerResult,
    CommentTopicDef,
    ReviewQueue,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuCommentTopicResult,
    SkuParamNormalized,
    SkuTaskScore,
    StdClaimDef,
    StdParamDef,
    TargetGroupDef,
    UserTaskDef,
)
from app.schemas.api import ReviewDecision
from app.services.review_service import apply_review_decision

router = APIRouter(tags=["assets"])

ASSET_MODELS = {
    "params": StdParamDef,
    "parameters": StdParamDef,
    "std_params": StdParamDef,
    "claim_defs": StdClaimDef,
    "topic_defs": CommentTopicDef,
    "task_defs": UserTaskDef,
    "target_groups": TargetGroupDef,
    "battlefield_defs": BattlefieldDef,
    "normalized_params": SkuParamNormalized,
    "claims": SkuClaimResult,
    "claim_results": SkuClaimResult,
    "topics": SkuCommentTopicResult,
    "comment_topics": SkuCommentTopicResult,
    "tasks": SkuTaskScore,
    "task_scores": SkuTaskScore,
    "battlefields": SkuBattlefieldScore,
    "battlefield_scores": SkuBattlefieldScore,
    "market_metrics": ClaimValueLayerResult,
    "claim_value_layers": ClaimValueLayerResult,
}


@router.get("/projects/{project_id}/assets/{asset_type}")
def list_assets(project_id: str, asset_type: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    model = ASSET_MODELS.get(asset_type)
    if not model:
        raise HTTPException(status_code=404, detail=f"未知资产类型: {asset_type}")
    rows = db.execute(select(model).where(model.project_id == project_id)).scalars().all()
    return {"asset_type": asset_type, "count": len(rows), "items": [_serialize(row) for row in rows]}


@router.get("/projects/{project_id}/review-queue")
def list_review_queue(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(
        select(ReviewQueue).where(ReviewQueue.project_id == project_id).order_by(ReviewQueue.created_at.desc())
    ).scalars().all()
    return {"count": len(rows), "items": [_serialize(row) for row in rows]}


@router.post("/review-queue/{review_id}/decision")
def review_decision(review_id: str, payload: ReviewDecision, db: Session = Depends(get_db)) -> dict:
    try:
        row = apply_review_decision(
            db,
            review_id,
            decision=payload.decision,
            reviewer=payload.reviewer,
            decision_payload=payload.decision_payload,
        )
        return _serialize(row)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _serialize(row) -> dict[str, Any]:
    data = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[column.name] = value
    return data

