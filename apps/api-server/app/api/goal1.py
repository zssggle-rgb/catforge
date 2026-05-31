from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    AnalysisRun,
    CalibrationRun,
    EvaluationRun,
    EvidenceItem,
    RuleSet,
    SkuCompetitorResult,
)
from app.services.goal1_analysis_service import (
    get_goal1_analysis,
    run_goal1_analysis,
    run_to_dict,
)
from app.services.goal1_evaluation_service import (
    calibration_to_dict,
    evaluation_to_dict,
    import_goal1_gold_labels,
    run_goal1_calibration,
    run_goal1_evaluation,
)
from app.services.goal1_rule_engine import (
    RuleValidationError,
    parse_rule_documents,
    validate_rule_documents,
)

router = APIRouter(prefix="/api", tags=["goal1-core-engine"])


@router.post("/rule-sets/validate")
def validate_rule_sets(payload: Any = Body(...)) -> dict[str, Any]:
    try:
        rule_sets = _rule_sets_from_payload(payload)
        validate_rule_documents(rule_sets)
        return {"valid": True, "errors": [], "rule_set_count": len(rule_sets)}
    except RuleValidationError as exc:
        return {"valid": False, "errors": exc.errors}
    except Exception as exc:
        return {"valid": False, "errors": [str(exc)]}


@router.post("/rule-sets")
def create_rule_sets(payload: Any = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        rule_sets = _rule_sets_from_payload(payload)
        validate_rule_documents(rule_sets)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
    created = []
    for rule_set in rule_sets:
        row = RuleSet(
            rule_set_id=rule_set["rule_set_id"],
            category_code=rule_set.get("category", "TV"),
            rule_type=rule_set.get("rule_type", "competitor_score"),
            version=str(rule_set["version"]),
            status=rule_set.get("status", "draft"),
            source_format=_payload_format(payload),
            content=rule_set,
            validation_errors=[],
        )
        db.add(row)
        db.flush()
        created.append(_rule_set_to_dict(row))
    db.commit()
    return {"status": "created", "rule_sets": created}


@router.get("/rule-sets/{rule_set_id}")
def get_rule_set(rule_set_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(
        select(RuleSet)
        .where(RuleSet.rule_set_id == rule_set_id)
        .order_by(RuleSet.updated_at.desc())
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="规则集不存在")
    return _rule_set_to_dict(row)


@router.post("/rule-sets/{rule_set_id}/activate")
def activate_rule_set(rule_set_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(select(RuleSet).where(RuleSet.rule_set_id == rule_set_id)).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="规则集不存在")
    rows.sort(key=lambda row: row.updated_at, reverse=True)
    active = rows[0]
    for row in rows:
        row.status = "draft"
    active.status = "active"
    db.commit()
    db.refresh(active)
    return {"status": "active", "rule_set": _rule_set_to_dict(active)}


@router.post("/projects/{project_id}/run-analysis")
def run_analysis(
    project_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        run = run_goal1_analysis(
            db,
            project_id,
            fixture_path=(payload or {}).get("fixture_path"),
            target_sku_code=(payload or {}).get("target_sku_code"),
        )
        return run_to_dict(run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/analysis-runs/{run_id}")
def get_analysis_run(project_id: str, run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.execute(
        select(AnalysisRun).where(
            AnalysisRun.project_id == project_id,
            AnalysisRun.analysis_run_id == run_id,
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="分析运行不存在")
    return run_to_dict(run)


@router.get("/projects/{project_id}/sku/{sku_code}/analysis")
def get_sku_analysis(project_id: str, sku_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_goal1_analysis(db, project_id, sku_code)


@router.get("/projects/{project_id}/sku/{sku_code}/competitors")
def get_sku_competitors(project_id: str, sku_code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(
        select(SkuCompetitorResult)
        .where(
            SkuCompetitorResult.project_id == project_id,
            SkuCompetitorResult.target_sku_code == sku_code,
        )
        .order_by(SkuCompetitorResult.rank)
    ).scalars().all()
    return {
        "sku_code": sku_code,
        "items": [
            {
                "target_sku_code": row.target_sku_code,
                "competitor_sku_code": row.competitor_sku_code,
                "battlefield_code": row.battlefield_code,
                "competitor_type": row.competitor_type,
                "rank": row.rank,
                "score": row.score,
                "component_scores": row.component_scores,
                "evidence_ids": row.evidence_ids,
                "evidence_card": row.evidence_card,
                "confidence": row.confidence,
                "rule_version": row.rule_version,
                "asset_version": row.asset_version,
                "review_status": row.review_status,
                "insufficient_reasons": row.insufficient_reasons,
            }
            for row in rows
        ],
    }


@router.get("/projects/{project_id}/evidence/{evidence_id}")
def get_evidence(project_id: str, evidence_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(
        select(EvidenceItem).where(
            EvidenceItem.project_id == project_id,
            EvidenceItem.evidence_id == evidence_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="证据不存在")
    return {
        "evidence_id": row.evidence_id,
        "project_id": row.project_id,
        "category_code": row.category_code,
        "sku_code": row.sku_code,
        "source_type": row.source_type,
        "source_file_id": row.source_file_id,
        "raw_row_id": row.raw_row_id,
        "field_name": row.field_name,
        "raw_value": row.raw_value,
        "normalized_value": row.normalized_value,
        "source_ref": row.source_ref,
        "confidence": row.confidence,
    }


@router.post("/projects/{project_id}/gold-labels/import")
def import_gold_labels(
    project_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return import_goal1_gold_labels(db, project_id, file_path=(payload or {}).get("file_path"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/evaluation/run")
def run_evaluation(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return evaluation_to_dict(run_goal1_evaluation(db, project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/evaluation/{evaluation_id}")
def get_evaluation(project_id: str, evaluation_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.execute(
        select(EvaluationRun).where(
            EvaluationRun.project_id == project_id,
            EvaluationRun.evaluation_id == evaluation_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="评测运行不存在")
    return evaluation_to_dict(row)


@router.post("/projects/{project_id}/calibration/run")
def run_calibration(project_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return calibration_to_dict(run_goal1_calibration(db, project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _rule_sets_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "content" in payload:
        return parse_rule_documents(str(payload["content"]), payload.get("format", "yaml"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, str):
        return parse_rule_documents(payload, "yaml")
    raise ValueError("请求体必须是规则集对象、规则集数组或 {content, format}")


def _payload_format(payload: Any) -> str:
    if isinstance(payload, dict) and payload.get("format"):
        return str(payload["format"])
    if isinstance(payload, str):
        return "yaml"
    return "json"


def _rule_set_to_dict(row: RuleSet) -> dict[str, Any]:
    return {
        "id": row.id,
        "rule_set_id": row.rule_set_id,
        "category_code": row.category_code,
        "rule_type": row.rule_type,
        "version": row.version,
        "status": row.status,
        "source_format": row.source_format,
        "content": row.content,
        "validation_errors": row.validation_errors,
    }
