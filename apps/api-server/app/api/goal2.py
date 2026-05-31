from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import RuntimeExport
from app.services.audit_service import audit_to_dict, create_audit_event, query_audit_events
from app.services.job_service import (
    ContractJobError,
    cancel_job,
    job_diagnostics,
    job_to_dict,
    retry_job,
    submit_job,
)
from app.services.observability_service import metrics
from app.services.runtime_export_service import (
    RuntimeExportError,
    export_released_runtime_assets,
    runtime_export_to_dict,
)
from app.services.version_governance_service import (
    VersionGovernanceError,
    approve_asset_version,
    archive_asset_version,
    asset_diff_to_dict,
    asset_version_to_dict,
    create_asset_version,
    diff_asset_versions,
    edit_asset_version,
    list_asset_versions,
    release_asset_version,
    rollback_asset_version,
    submit_asset_review,
)

router = APIRouter(prefix="/api", tags=["goal2-production-hardening"])


@router.post("/jobs")
def create_job(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        job = submit_job(
            db,
            project_id=payload["project_id"],
            job_type=payload["job_type"],
            idempotency_key=payload["idempotency_key"],
            input_payload=payload.get("input", {}),
            created_by=payload.get("created_by", "api"),
            max_attempts=int(payload.get("max_attempts", 3)),
            run_now=bool(payload.get("run_now", True)),
        )
        return job_to_dict(job)
    except (KeyError, ContractJobError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.models import JobRun

    job = db.get(JobRun, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return job_to_dict(job)


@router.post("/jobs/{job_id}/cancel")
def cancel_job_api(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return job_to_dict(cancel_job(db, job_id))
    except ContractJobError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/retry")
def retry_job_api(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return job_to_dict(retry_job(db, job_id))
    except ContractJobError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/diagnostics")
def job_diagnostics_api(job_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return job_diagnostics(db, job_id)
    except ContractJobError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/assets/versions")
def create_asset_version_api(
    payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        row = create_asset_version(
            db,
            project_id=payload.get("project_id"),
            asset_type=payload.get("asset_type", "runtime_asset"),
            category_code=payload.get("category_code", "TV"),
            version=payload["version"],
            manifest_json=payload.get("manifest_json", {}),
            created_by=payload.get("created_by", "api"),
        )
        return asset_version_to_dict(row)
    except (KeyError, VersionGovernanceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/edit")
def edit_asset_version_api(
    asset_id: str, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return asset_version_to_dict(
            edit_asset_version(
                db,
                asset_id,
                manifest_json=payload.get("manifest_json", {}),
                actor_id=payload.get("actor_id", "api"),
            )
        )
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/submit-review")
def submit_review_api(asset_id: str, payload: dict[str, Any] | None = Body(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return asset_version_to_dict(submit_asset_review(db, asset_id, actor_id=(payload or {}).get("actor_id", "api")))
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/approve")
def approve_asset_api(asset_id: str, payload: dict[str, Any] | None = Body(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return asset_version_to_dict(approve_asset_version(db, asset_id, actor_id=(payload or {}).get("actor_id", "api")))
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/release")
def release_asset_api(asset_id: str, payload: dict[str, Any] | None = Body(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        payload = payload or {}
        return asset_version_to_dict(
            release_asset_version(
                db,
                asset_id,
                actor_id=payload.get("actor_id", "api"),
                approved_by=payload.get("approved_by"),
            )
        )
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assets/{asset_id}/versions")
def asset_versions_api(asset_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        rows = list_asset_versions(db, asset_id)
        return {"items": [asset_version_to_dict(row) for row in rows], "count": len(rows)}
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/assets/diff")
def asset_diff_api(
    from_version: str = Query(...),
    to_version: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return asset_diff_to_dict(diff_asset_versions(db, from_version, to_version))
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/rollback")
def rollback_asset_api(
    asset_id: str, payload: dict[str, Any] | None = Body(default=None), db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        payload = payload or {}
        return asset_version_to_dict(
            rollback_asset_version(
                db,
                asset_id,
                target_version_id=payload.get("target_version_id"),
                reason=payload.get("reason", ""),
                actor_id=payload.get("actor_id", "api"),
            )
        )
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/{asset_id}/archive")
def archive_asset_api(
    asset_id: str, payload: dict[str, Any] | None = Body(default=None), db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        payload = payload or {}
        return asset_version_to_dict(
            archive_asset_version(
                db,
                asset_id,
                reason=payload.get("reason", ""),
                actor_id=payload.get("actor_id", "api"),
            )
        )
    except VersionGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/runtime-export")
def runtime_export_api(
    project_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        payload = payload or {}
        return runtime_export_to_dict(
            export_released_runtime_assets(
                db,
                project_id=project_id,
                asset_version_id=payload.get("asset_version_id"),
                allow_draft=bool(payload.get("allow_draft", False)),
                created_by=payload.get("created_by", "api"),
            )
        )
    except RuntimeExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/exports/{export_id}")
def get_runtime_export(export_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(RuntimeExport, export_id)
    if not row:
        raise HTTPException(status_code=404, detail="导出不存在")
    return runtime_export_to_dict(row)


@router.get("/exports/{export_id}/download")
def download_runtime_export(export_id: str, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(RuntimeExport, export_id)
    if not row:
        raise HTTPException(status_code=404, detail="导出不存在")
    return FileResponse(row.file_path, filename=row.file_path.split("/")[-1])


@router.get("/audit")
def list_audit_events(
    project_id: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = query_audit_events(
        db,
        project_id=project_id,
        object_type=object_type,
        object_id=object_id,
        action=action,
    )
    return {"count": len(rows), "items": [audit_to_dict(row) for row in rows]}


@router.post("/audit/permission-change")
def audit_permission_change(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    event = create_audit_event(
        db,
        action="user_permission_changed",
        object_type="user_permission",
        object_id=payload["user_id"],
        project_id=payload.get("project_id"),
        actor_id=payload.get("actor_id", "api"),
        before=payload.get("before"),
        after=payload.get("after"),
        metadata={"reason": payload.get("reason", "")},
        commit=True,
    )
    return audit_to_dict(event)


@router.get("/metrics")
def metrics_api(db: Session = Depends(get_db)) -> dict[str, Any]:
    return metrics(db)
