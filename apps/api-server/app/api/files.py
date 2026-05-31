from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import SourceFile
from app.schemas.api import SourceFileOut
from app.services.ingestion_service import infer_file_type, register_source_file, save_upload

router = APIRouter(tags=["files"])


@router.post("/projects/{project_id}/files", response_model=SourceFileOut)
async def upload_source_file(
    project_id: str,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    db: Session = Depends(get_db),
) -> SourceFile:
    try:
        inferred_type = infer_file_type(file.filename or "", file_type)
        path = save_upload(project_id, file.filename or "upload.csv", await file.read())
        return register_source_file(
            db,
            project_id=project_id,
            file_name=file.filename or path.name,
            file_type=inferred_type,
            storage_path=str(path),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

