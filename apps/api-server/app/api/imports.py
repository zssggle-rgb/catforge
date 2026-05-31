from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import SourceFile
from app.schemas.api import DataQualityOut, ImportOut, ImportRequest
from app.services.ingestion_service import import_from_path, import_source_file
from app.services.profiling_service import data_quality_report

router = APIRouter(tags=["imports"])


@router.post("/projects/{project_id}/imports", response_model=ImportOut)
def import_file(project_id: str, payload: ImportRequest, db: Session = Depends(get_db)):
    try:
        if payload.file_path:
            return import_from_path(
                db,
                project_id=project_id,
                file_path=payload.file_path,
                file_type=payload.file_type,
            )
        if not payload.source_file_id:
            raise ValueError("source_file_id 或 file_path 必须提供")
        source = db.get(SourceFile, payload.source_file_id)
        if not source or source.project_id != project_id:
            raise ValueError("源文件不存在")
        return import_source_file(db, source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/data-quality", response_model=DataQualityOut)
def get_data_quality(project_id: str, db: Session = Depends(get_db)) -> dict:
    return data_quality_report(db, project_id)

