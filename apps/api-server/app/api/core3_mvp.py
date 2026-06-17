from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.core3_mvp import (
    Core3DataStatusOut,
    Core3RunOut,
    Core3RunRequest,
    Core3SkuReportOut,
    Core3SkuResolveOut,
)
from app.services.core3_mvp.data_access import (
    Core3MultipleSkuMatches,
    Core3ProjectNotFound,
    Core3SkuNotFound,
    data_status,
    resolve_sku_code,
)
from app.services.core3_mvp.report_service import (
    Core3ReportNotFound,
    create_or_reuse_run,
    export_core3_csv,
    export_evidence_cards_jsonl,
    get_competitor_evidence_cards,
    get_overview,
    get_sku_report,
    run_to_dict,
)
from app.services.core3_mvp.feature_pipeline import run_feature_extraction

router = APIRouter(prefix="/api/mvp/core3", tags=["tv-core3-mvp"])


@router.get("/projects/{project_id}/data-status", response_model=Core3DataStatusOut)
def get_data_status(project_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return data_status(db, project_id)
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/resolve-sku", response_model=Core3SkuResolveOut)
def resolve_sku(
    project_id: str,
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return resolve_sku_code(db, project_id, query)
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3SkuNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3MultipleSkuMatches as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "input": exc.query, "candidates": exc.candidates},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/run", response_model=Core3RunOut)
def run_core3(
    project_id: str,
    payload: Core3RunRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        run = create_or_reuse_run(db, project_id, payload)
        if run.status == "created":
            run_feature_extraction(db, run.run_id)
            db.refresh(run)
        return run_to_dict(run)
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3SkuNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3MultipleSkuMatches as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "input": exc.query, "candidates": exc.candidates},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/overview")
def get_core3_overview(project_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return get_overview(db, project_id)
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/sku/{sku_or_model}/report", response_model=Core3SkuReportOut)
def get_core3_sku_report(
    project_id: str,
    sku_or_model: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_sku_report(db, project_id, sku_or_model)
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3SkuNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3MultipleSkuMatches as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "input": exc.query, "candidates": exc.candidates},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/sku/{sku_or_model}/competitors/evidence")
def get_core3_competitor_evidence(
    project_id: str,
    sku_or_model: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return get_competitor_evidence_cards(db, project_id, sku_or_model)
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3SkuNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3MultipleSkuMatches as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "input": exc.query, "candidates": exc.candidates},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/export/core3.csv")
def export_core3_csv_api(project_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        return Response(
            content=export_core3_csv(db, project_id),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="sku_competitor_core3.csv"'},
        )
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/export/evidence-cards.jsonl")
def export_core3_evidence_cards_api(project_id: str, db: Session = Depends(get_db)) -> Response:
    try:
        return Response(
            content=export_evidence_cards_jsonl(db, project_id),
            media_type="application/x-ndjson; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="evidence_cards.jsonl"'},
        )
    except Core3ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Core3ReportNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
