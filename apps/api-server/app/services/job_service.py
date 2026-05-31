from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CategoryProject, JobAttempt, JobRun
from app.services.audit_service import create_audit_event
from app.services.goal1_analysis_service import run_goal1_analysis
from app.services.goal1_evaluation_service import run_goal1_calibration, run_goal1_evaluation
from app.services.hardening_utils import now_iso, sha256_json, stable_json

logger = logging.getLogger("catforge.jobs")

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "blocked"}
ACTIVE_STATUSES = {"queued", "running", "retrying", "cancel_requested"}
JOB_TYPES = {
    "data_import",
    "data_profile",
    "analysis_run",
    "competitor_run",
    "evaluation_run",
    "calibration_run",
    "asset_release",
    "runtime_export",
}


class JobError(Exception):
    error_code = "job_error"
    retryable = False


class TransientJobError(JobError):
    error_code = "transient_error"
    retryable = True


class ContractJobError(JobError):
    error_code = "contract_error"
    retryable = False


class JobCancelled(JobError):
    error_code = "job_cancelled"
    retryable = False


def submit_job(
    db: Session,
    *,
    project_id: str,
    job_type: str,
    idempotency_key: str,
    input_payload: dict[str, Any] | None = None,
    created_by: str = "system",
    max_attempts: int = 3,
    run_now: bool = True,
) -> JobRun:
    if job_type not in JOB_TYPES:
        raise ContractJobError(f"不支持的 job_type: {job_type}")
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ContractJobError("项目不存在")
    input_payload = input_payload or {}
    input_fingerprint = sha256_json(input_payload)
    existing = db.execute(
        select(JobRun).where(
            JobRun.project_id == project_id,
            JobRun.job_type == job_type,
            JobRun.idempotency_key == idempotency_key,
            JobRun.input_fingerprint == input_fingerprint,
        )
    ).scalar_one_or_none()
    if existing:
        existing.diagnostics_json = {
            **(existing.diagnostics_json or {}),
            "idempotent_replay": True,
        }
        db.commit()
        db.refresh(existing)
        return existing

    lock_key = _lock_key(project_id, project.category_code, job_type, input_payload)
    if lock_key and _has_active_lock(db, lock_key):
        job = JobRun(
            project_id=project_id,
            category_code=project.category_code,
            job_type=job_type,
            idempotency_key=idempotency_key,
            input_fingerprint=input_fingerprint,
            status="blocked",
            max_attempts=max_attempts,
            checkpoint_json={},
            diagnostics_json={"blocked_by_lock": lock_key},
            error_code="concurrency_lock",
            error_message="同一项目/品类/版本已有 release/export 作业在运行",
            lock_key=lock_key,
            created_by=created_by,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    job = JobRun(
        project_id=project_id,
        category_code=project.category_code,
        job_type=job_type,
        idempotency_key=idempotency_key,
        input_fingerprint=input_fingerprint,
        status="queued",
        max_attempts=max(1, max_attempts),
        checkpoint_json={"input": input_payload},
        diagnostics_json={"idempotent_replay": False},
        lock_key=lock_key,
        created_by=created_by,
    )
    db.add(job)
    db.flush()
    create_audit_event(
        db,
        action="job_submitted",
        object_type="job_run",
        object_id=job.job_id,
        project_id=project_id,
        actor_id=created_by,
        after=job_to_dict(job),
        metadata={"job_type": job_type},
    )
    db.commit()
    db.refresh(job)
    if run_now:
        execute_job(db, job.job_id)
        db.refresh(job)
    return job


def execute_job(db: Session, job_id: str) -> JobRun:
    job = db.get(JobRun, job_id)
    if not job:
        raise ContractJobError("作业不存在")
    if job.status == "cancel_requested":
        job.status = "cancelled"
        job.finished_at = job.finished_at or job.updated_at
        db.commit()
        db.refresh(job)
        return job
    if job.status in {"succeeded", "running"}:
        return job
    job.status = "running"
    job.started_at = job.started_at or job.updated_at
    db.commit()

    while job.attempt_count < job.max_attempts:
        if job.status == "cancel_requested":
            job.status = "cancelled"
            job.finished_at = job.updated_at
            db.commit()
            break
        attempt_no = job.attempt_count + 1
        attempt = JobAttempt(
            job_id=job.job_id,
            attempt_no=attempt_no,
            started_at=job.updated_at,
            status="running",
            diagnostics_json={"checkpoint_before": job.checkpoint_json},
        )
        db.add(attempt)
        job.attempt_count = attempt_no
        _structured_log("job_attempt_started", job, {"attempt_no": attempt_no})
        db.flush()
        try:
            result = _run_handler(db, job)
            attempt.status = "succeeded"
            attempt.finished_at = job.updated_at
            job.status = "succeeded"
            job.result_ref = result
            job.error_code = None
            job.error_message = None
            job.finished_at = job.updated_at
            _structured_log("job_succeeded", job, {"attempt_no": attempt_no})
            create_audit_event(
                db,
                action="job_succeeded",
                object_type="job_run",
                object_id=job.job_id,
                project_id=job.project_id,
                actor_id=job.created_by,
                after=job_to_dict(job),
                metadata={"job_type": job.job_type, "attempt_no": attempt_no},
            )
            db.commit()
            break
        except JobCancelled as exc:
            _mark_attempt_failed(attempt, exc, retry_after_seconds=None)
            job.status = "cancelled"
            job.error_code = exc.error_code
            job.error_message = str(exc)
            job.finished_at = job.updated_at
            db.commit()
            break
        except ContractJobError as exc:
            _mark_attempt_failed(attempt, exc, retry_after_seconds=None)
            job.status = "failed"
            job.error_code = exc.error_code
            job.error_message = str(exc)
            job.finished_at = job.updated_at
            _structured_log("job_failed_non_retryable", job, {"attempt_no": attempt_no})
            db.commit()
            break
        except TransientJobError as exc:
            retry_after = 2 ** (attempt_no - 1)
            _mark_attempt_failed(attempt, exc, retry_after_seconds=retry_after)
            job.error_code = exc.error_code
            job.error_message = str(exc)
            if attempt_no >= job.max_attempts:
                job.status = "failed"
                job.finished_at = job.updated_at
                _structured_log("job_failed_retry_exhausted", job, {"attempt_no": attempt_no})
                db.commit()
                break
            job.status = "retrying"
            job.diagnostics_json = {
                **(job.diagnostics_json or {}),
                "last_retry_after_seconds": retry_after,
            }
            _structured_log("job_retry_scheduled", job, {"attempt_no": attempt_no, "retry_after_seconds": retry_after})
            db.commit()
            db.refresh(job)
            continue
        finally:
            db.refresh(job)
    return job


def cancel_job(db: Session, job_id: str) -> JobRun:
    job = db.get(JobRun, job_id)
    if not job:
        raise ContractJobError("作业不存在")
    if job.status in TERMINAL_STATUSES:
        return job
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = job.updated_at
    else:
        job.status = "cancel_requested"
    db.commit()
    db.refresh(job)
    return job


def retry_job(db: Session, job_id: str) -> JobRun:
    job = db.get(JobRun, job_id)
    if not job:
        raise ContractJobError("作业不存在")
    if job.error_code == ContractJobError.error_code:
        raise ContractJobError("数据契约错误不可原地重试，请修复输入并提交新作业")
    if job.status not in {"failed", "cancelled", "blocked", "retrying"}:
        return job
    if job.status == "blocked" and job.error_code == "concurrency_lock":
        if job.lock_key and _has_active_lock(db, job.lock_key, exclude_job_id=job.job_id):
            return job
    job.status = "queued"
    job.error_code = None
    job.error_message = None
    job.finished_at = None
    db.commit()
    return execute_job(db, job.job_id)


def job_diagnostics(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(JobRun, job_id)
    if not job:
        raise ContractJobError("作业不存在")
    attempts = db.execute(
        select(JobAttempt).where(JobAttempt.job_id == job_id).order_by(JobAttempt.attempt_no)
    ).scalars().all()
    return {
        "job": job_to_dict(job),
        "checkpoint": job.checkpoint_json,
        "error_summary": {
            "error_code": job.error_code,
            "error_message": job.error_message,
        },
        "retry_history": [attempt_to_dict(row) for row in attempts],
        "stage_timings": [
            {
                "attempt_no": row.attempt_no,
                "started_at": now_iso(row.started_at),
                "finished_at": now_iso(row.finished_at),
                "status": row.status,
            }
            for row in attempts
        ],
    }


def job_to_dict(job: JobRun) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "project_id": job.project_id,
        "category_code": job.category_code,
        "idempotency_key": job.idempotency_key,
        "input_fingerprint": job.input_fingerprint,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "checkpoint_json": job.checkpoint_json,
        "result_ref": job.result_ref,
        "diagnostics_json": job.diagnostics_json,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "lock_key": job.lock_key,
        "created_by": job.created_by,
        "created_at": now_iso(job.created_at),
        "started_at": now_iso(job.started_at),
        "finished_at": now_iso(job.finished_at),
    }


def attempt_to_dict(attempt: JobAttempt) -> dict[str, Any]:
    return {
        "attempt_id": attempt.attempt_id,
        "job_id": attempt.job_id,
        "attempt_no": attempt.attempt_no,
        "worker_id": attempt.worker_id,
        "started_at": now_iso(attempt.started_at),
        "finished_at": now_iso(attempt.finished_at),
        "status": attempt.status,
        "error_code": attempt.error_code,
        "error_message": attempt.error_message,
        "retry_after_seconds": attempt.retry_after_seconds,
        "diagnostics_json": attempt.diagnostics_json,
    }


def _run_handler(db: Session, job: JobRun) -> dict[str, Any]:
    payload = (job.checkpoint_json or {}).get("input", {})
    if payload.get("cancel_before_work"):
        raise JobCancelled("作业已在执行前取消")
    _maybe_transient_failure(job, payload)
    if job.job_type == "data_import":
        return _data_import_handler(job, payload)
    if job.job_type == "data_profile":
        return _data_profile_handler(job, payload)
    if job.job_type in {"analysis_run", "competitor_run"}:
        job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "analysis_started"}
        db.flush()
        run = run_goal1_analysis(
            db,
            job.project_id,
            fixture_path=payload.get("fixture_path"),
            target_sku_code=payload.get("target_sku_code"),
        )
        job.checkpoint_json = {
            **(job.checkpoint_json or {}),
            "stage": "analysis_completed",
            "analysis_run_id": run.analysis_run_id,
        }
        if payload.get("simulate_transient_after_checkpoint") and job.attempt_count == 1:
            raise TransientJobError("checkpoint 后发生瞬时错误")
        return {"analysis_run_id": run.analysis_run_id, "counts": run.counts}
    if job.job_type == "evaluation_run":
        run = run_goal1_evaluation(db, job.project_id)
        job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "evaluation_completed", "evaluation_id": run.evaluation_id}
        return {"evaluation_id": run.evaluation_id, "metrics": run.metrics}
    if job.job_type == "calibration_run":
        run = run_goal1_calibration(db, job.project_id)
        job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "calibration_completed", "calibration_id": run.calibration_id}
        return {"calibration_id": run.calibration_id, "status": run.status}
    if job.job_type == "asset_release":
        from app.services.version_governance_service import release_asset_version

        released = release_asset_version(
            db,
            payload["asset_version_id"],
            actor_id=job.created_by,
            approved_by=payload.get("approved_by", job.created_by),
        )
        job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "release_completed", "asset_version_id": released.asset_version_id}
        return {"asset_version_id": released.asset_version_id, "status": released.lifecycle_status}
    if job.job_type == "runtime_export":
        from app.services.runtime_export_service import export_released_runtime_assets

        export = export_released_runtime_assets(
            db,
            project_id=job.project_id,
            asset_version_id=payload.get("asset_version_id"),
            allow_draft=bool(payload.get("allow_draft", False)),
            created_by=job.created_by,
        )
        job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "export_completed", "export_id": export.export_id}
        return {"export_id": export.export_id, "file_path": export.file_path}
    raise ContractJobError(f"未实现的 job_type: {job.job_type}")


def _data_import_handler(job: JobRun, payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows")
    if rows is None:
        raise ContractJobError("data_import 需要 rows")
    required_columns = payload.get("required_columns") or []
    for index, row in enumerate(rows):
        for column in required_columns:
            if row.get(column) in {None, ""}:
                raise ContractJobError(f"第 {index + 1} 行缺少必填字段: {column}")
    job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "data_import_validated", "rows_processed": len(rows)}
    return {"rows_processed": len(rows)}


def _data_profile_handler(job: JobRun, payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    job.checkpoint_json = {
        **(job.checkpoint_json or {}),
        "stage": "profile_completed",
        "rows_processed": len(rows),
        "columns": sorted({key for row in rows for key in row}),
    }
    return {"rows_processed": len(rows), "column_count": len(job.checkpoint_json["columns"])}


def _maybe_transient_failure(job: JobRun, payload: dict[str, Any]) -> None:
    fail_before_success = int(payload.get("transient_failures_before_success", 0))
    if job.attempt_count <= fail_before_success:
        job.checkpoint_json = {**(job.checkpoint_json or {}), "stage": "transient_failure_simulated"}
        raise TransientJobError("模拟瞬时错误，等待重试")


def _mark_attempt_failed(
    attempt: JobAttempt, exc: JobError, *, retry_after_seconds: int | None
) -> None:
    attempt.status = "failed"
    attempt.error_code = exc.error_code
    attempt.error_message = str(exc)
    attempt.retry_after_seconds = retry_after_seconds


def _lock_key(project_id: str, category_code: str, job_type: str, payload: dict[str, Any]) -> str | None:
    if job_type not in {"asset_release", "runtime_export"}:
        return None
    version = payload.get("version") or payload.get("asset_version_id") or payload.get("asset_version") or "latest"
    return f"{project_id}:{category_code}:{job_type}:{version}"


def _has_active_lock(db: Session, lock_key: str, *, exclude_job_id: str | None = None) -> bool:
    query = select(JobRun).where(JobRun.lock_key == lock_key, JobRun.status.in_(ACTIVE_STATUSES))
    if exclude_job_id:
        query = query.where(JobRun.job_id != exclude_job_id)
    return db.execute(query).first() is not None


def _structured_log(event: str, job: JobRun, extra: dict[str, Any]) -> None:
    logger.info(
        stable_json(
            {
                "event": event,
                "job_id": job.job_id,
                "job_type": job.job_type,
                "project_id": job.project_id,
                "status": job.status,
                **extra,
            }
        )
    )
