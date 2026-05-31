from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DataQualityIssue,
    RawMarketFact,
    RawSkuClaim,
    RawSkuComment,
    RawSkuMaster,
    RawSkuParam,
)


RAW_TABLES = {
    "sku_master": RawSkuMaster,
    "sku_param": RawSkuParam,
    "sku_claim": RawSkuClaim,
    "sku_comment": RawSkuComment,
    "market_fact": RawMarketFact,
}


def data_quality_report(db: Session, project_id: str) -> dict:
    counts = {
        name: db.execute(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        ).scalar_one()
        for name, model in RAW_TABLES.items()
    }
    issues = db.execute(
        select(DataQualityIssue).where(DataQualityIssue.project_id == project_id)
    ).scalars().all()
    severity_counts: dict[str, int] = {}
    for issue in issues:
        severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
    return {
        "project_id": project_id,
        "summary": {
            "raw_row_counts": counts,
            "issue_count": len(issues),
            "critical_count": severity_counts.get("critical", 0),
            "warning_count": severity_counts.get("warning", 0),
            "status": "passed" if severity_counts.get("critical", 0) == 0 else "needs_review",
        },
        "issues": [
            {
                "issue_id": issue.issue_id,
                "severity": issue.severity,
                "issue_code": issue.issue_code,
                "table_name": issue.table_name,
                "field_name": issue.field_name,
                "raw_row_id": issue.raw_row_id,
                "message": issue.message,
                "evidence": issue.evidence,
            }
            for issue in issues
        ],
    }


def profile_project(db: Session, project_id: str) -> dict:
    param_rows = db.execute(
        select(RawSkuParam.raw_param_name, func.count(RawSkuParam.id))
        .where(RawSkuParam.project_id == project_id)
        .group_by(RawSkuParam.raw_param_name)
        .order_by(func.count(RawSkuParam.id).desc())
    ).all()
    claim_count = db.execute(
        select(func.count()).select_from(RawSkuClaim).where(RawSkuClaim.project_id == project_id)
    ).scalar_one()
    comment_count = db.execute(
        select(func.count()).select_from(RawSkuComment).where(RawSkuComment.project_id == project_id)
    ).scalar_one()
    sku_count = db.execute(
        select(func.count(func.distinct(RawSkuMaster.sku_code))).where(
            RawSkuMaster.project_id == project_id
        )
    ).scalar_one()
    return {
        "step": "profile",
        "status": "completed",
        "counts": {
            "sku_count": sku_count,
            "claim_count": claim_count,
            "comment_count": comment_count,
            "field_count": len(param_rows),
        },
        "message": "数据剖析完成",
        "profile": {
            "param_fields": [{"raw_param_name": name, "count": count} for name, count in param_rows],
        },
    }

