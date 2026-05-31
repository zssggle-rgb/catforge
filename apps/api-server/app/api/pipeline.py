from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api import PipelineOut
from app.services.claim_factory import generate_claims
from app.services.comment_topic_factory import generate_comment_topics
from app.services.market_metrics_engine import calculate_market_metrics
from app.services.param_factory import generate_params
from app.services.review_service import build_review_queue
from app.services.task_battlefield_factory import score_tasks_battlefields

router = APIRouter(tags=["pipeline"])

PIPELINE_STEPS = {
    "generate_params": generate_params,
    "generate_claims": generate_claims,
    "generate_comment_topics": generate_comment_topics,
    "score_tasks_battlefields": score_tasks_battlefields,
    "calculate_market_metrics": calculate_market_metrics,
    "build_review_queue": build_review_queue,
}


@router.post("/projects/{project_id}/pipeline/{step}", response_model=PipelineOut)
def run_pipeline_step(project_id: str, step: str, db: Session = Depends(get_db)) -> dict:
    handler = PIPELINE_STEPS.get(step)
    if not handler:
        raise HTTPException(status_code=404, detail=f"不支持的流水线步骤: {step}")
    try:
        return handler(db, project_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

