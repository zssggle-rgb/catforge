from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import workbench_service as workbench

router = APIRouter(prefix="/api", tags=["goal3-tv-asset-workbench"])


@router.post("/projects/{project_id}/workbench/use-fixture")
def use_fixture(
    project_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return workbench.use_tv_fixture(
            db,
            project_id,
            target_sku_code=(payload or {}).get("target_sku_code", "TV00029115"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/workbench/data-overview")
def data_overview(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return workbench.profile_dashboard(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/assets/parameters")
def parameter_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.library_rows(db, project_id, "parameters")


@router.get("/projects/{project_id}/assets/claims")
def claim_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.library_rows(db, project_id, "claims")


@router.get("/projects/{project_id}/assets/comment-topics")
def comment_topic_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.library_rows(db, project_id, "comment-topics")


@router.get("/projects/{project_id}/assets/tasks")
def task_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.library_rows(db, project_id, "tasks")


@router.get("/projects/{project_id}/assets/target-groups")
def target_group_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.library_rows(db, project_id, "target-groups")


@router.get("/projects/{project_id}/assets/battlefields")
def battlefield_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.library_rows(db, project_id, "battlefields")


@router.get("/projects/{project_id}/assets/mappings")
def mapping_library(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.mapping_rules(db, project_id)


@router.patch("/projects/{project_id}/assets/{asset_type}/{asset_id}/review")
def review_asset(
    project_id: str,
    asset_type: str,
    asset_id: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return workbench.review_asset(
            db,
            project_id,
            asset_type,
            asset_id,
            decision=payload["decision"],
            reviewer=payload.get("reviewer", "api"),
            decision_payload=payload.get("decision_payload"),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/projects/{project_id}/assets/{asset_type}/{asset_id}")
def update_asset(
    project_id: str,
    asset_type: str,
    asset_id: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return workbench.update_asset(
            db,
            project_id,
            asset_type,
            asset_id,
            patch=payload.get("patch", payload),
            actor_id=payload.get("actor_id", "api"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/assets/{asset_type}/merge")
def merge_assets(
    project_id: str,
    asset_type: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return workbench.merge_assets(db, project_id, asset_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/assets/{asset_type}/split")
def split_asset(
    project_id: str,
    asset_type: str,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return workbench.split_asset(db, project_id, asset_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/sku-results")
def sku_results(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.sku_batch_results(db, project_id)


@router.get("/projects/{project_id}/sku-results/{sku_code}")
def sku_result_detail(project_id: str, sku_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.sku_qa_detail(db, project_id, sku_code)


@router.get("/projects/{project_id}/sku-results/{sku_code}/evidence")
def sku_result_evidence(project_id: str, sku_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.sku_evidence(db, project_id, sku_code)


@router.get("/projects/{project_id}/sku-results/{sku_code}/competitors")
def sku_result_competitors(project_id: str, sku_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.sku_competitors(db, project_id, sku_code)


@router.get("/projects/{project_id}/sku-results/{sku_code}/report-preview")
def sku_result_report_preview(project_id: str, sku_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.sku_report_preview(db, project_id, sku_code)


@router.get("/projects/{project_id}/competitors")
def competitor_results(
    project_id: str,
    sku_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return workbench.competitor_inspection(db, project_id, sku_code=sku_code)


@router.get("/projects/{project_id}/calibration/summary")
def calibration_summary(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.calibration_summary(db, project_id)


@router.get("/projects/{project_id}/calibration/claims")
def calibration_claims(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.calibration_claims(db, project_id)


@router.get("/projects/{project_id}/calibration/battlefields")
def calibration_battlefields(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.calibration_battlefields(db, project_id)


@router.get("/projects/{project_id}/calibration/review-summary")
def calibration_review_summary(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return workbench.calibration_review_summary(db, project_id)


@router.get("/projects/{project_id}/runtime-export/preview")
def runtime_export_preview(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return workbench.export_preview(db, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/runtime-export/{export_id}/manifest")
def runtime_export_manifest(project_id: str, export_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return workbench.export_manifest(db, project_id, export_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
