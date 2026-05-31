from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import JobRun, RuntimeExport


def readiness(db: Session) -> dict[str, str]:
    db.execute(text("select 1"))
    return {"status": "ready", "database": "ok"}


def metrics(db: Session) -> dict[str, int | float]:
    job_counts = {
        status: count
        for status, count in db.execute(
            select(JobRun.status, func.count(JobRun.job_id)).group_by(JobRun.status)
        ).all()
    }
    total_jobs = sum(job_counts.values())
    failed_jobs = job_counts.get("failed", 0)
    retry_count = db.execute(select(func.sum(JobRun.attempt_count - 1))).scalar() or 0
    export_count = db.execute(select(func.count(RuntimeExport.export_id))).scalar() or 0
    succeeded_jobs = job_counts.get("succeeded", 0)
    return {
        "jobs_total": total_jobs,
        "jobs_failed": failed_jobs,
        "jobs_succeeded": succeeded_jobs,
        "job_retry_count": max(0, int(retry_count)),
        "runtime_export_count": export_count,
        "analysis_throughput_jobs": succeeded_jobs,
    }
