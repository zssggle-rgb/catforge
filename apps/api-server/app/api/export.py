from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.api import ExportOut, ExportRequest
from app.services.asset_exporter import export_runtime_package

router = APIRouter(tags=["export"])


@router.post("/projects/{project_id}/export-runtime", response_model=ExportOut)
def export_runtime(project_id: str, payload: ExportRequest, db: Session = Depends(get_db)):
    try:
        package = export_runtime_package(db, project_id, payload.version)
        return {
            "package_id": package.package_id,
            "package_path": package.package_path,
            "files": package.file_list,
            "status": package.status,
            "message": "运行态资产包导出完成，仅包含白名单文件",
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

