from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.profiling_service import profile_project

router = APIRouter(tags=["pipeline"])


@router.post("/projects/{project_id}/profile")
def run_profile(project_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return profile_project(db, project_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

