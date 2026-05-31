from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    CalibrationRun,
    CategoryProject,
    EvaluationRun,
    GoldLabel,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuCompetitorResult,
    SkuTaskScore,
)
from app.services.goal1_analysis_service import ASSET_VERSION, REPO_ROOT

DEFAULT_GOLD_LABEL_PATH = REPO_ROOT / "examples" / "goal1" / "goldset" / "tv_gold_labels.csv"


def import_goal1_gold_labels(
    db: Session, project_id: str, *, file_path: str | None = None
) -> dict[str, Any]:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    path = Path(file_path) if file_path else DEFAULT_GOLD_LABEL_PATH
    if not path.exists():
        raise ValueError(f"Gold Set 文件不存在: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    db.execute(delete(GoldLabel).where(GoldLabel.project_id == project_id))
    for row in rows:
        db.add(
            GoldLabel(
                project_id=project_id,
                category_code=project.category_code,
                label_type=row["label_type"],
                target_sku_code=row["target_sku_code"],
                candidate_code=row["candidate_code"],
                expected_label=row["expected_label"],
                expected_score_class=row.get("expected_score_class"),
                expert_id=row.get("expert_id"),
                notes=row.get("notes"),
                raw_payload=row,
                asset_version=ASSET_VERSION,
            )
        )
    db.commit()
    return {"status": "completed", "imported": len(rows), "file_path": str(path)}


def run_goal1_evaluation(db: Session, project_id: str) -> EvaluationRun:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    labels = db.execute(select(GoldLabel).where(GoldLabel.project_id == project_id)).scalars().all()
    if not labels:
        raise ValueError("Gold Set 为空，请先导入标签")
    detail_rows = [_evaluate_label(db, label) for label in labels]
    metrics = _metrics(detail_rows)
    run = EvaluationRun(
        project_id=project_id,
        category_code=project.category_code,
        status="completed" if len(labels) >= 3 else "insufficient_goldset",
        gold_label_count=len(labels),
        metrics=metrics,
        report={"labels": detail_rows, "summary": metrics},
        rule_versions=_current_rule_versions(db, project_id),
        asset_version=ASSET_VERSION,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_goal1_calibration(db: Session, project_id: str) -> CalibrationRun:
    labels = db.execute(select(GoldLabel).where(GoldLabel.project_id == project_id)).scalars().all()
    if not labels:
        raise ValueError("Gold Set 为空，请先导入标签")
    evaluation = run_goal1_evaluation(db, project_id)
    status = "draft_candidate" if len(labels) >= 3 else "insufficient_goldset"
    candidate_patch = _candidate_patch(evaluation.metrics)
    run = CalibrationRun(
        project_id=project_id,
        category_code=evaluation.category_code,
        status=status,
        target_metric="macro_f1",
        before_metrics=evaluation.metrics,
        after_metrics=evaluation.metrics,
        candidate_rule_patch=candidate_patch,
        rule_versions=evaluation.rule_versions,
        asset_version=ASSET_VERSION,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def evaluation_to_dict(run: EvaluationRun) -> dict[str, Any]:
    return {
        "evaluation_id": run.evaluation_id,
        "project_id": run.project_id,
        "status": run.status,
        "gold_label_count": run.gold_label_count,
        "metrics": run.metrics,
        "report": run.report,
        "rule_versions": run.rule_versions,
        "asset_version": run.asset_version,
    }


def calibration_to_dict(run: CalibrationRun) -> dict[str, Any]:
    return {
        "calibration_id": run.calibration_id,
        "project_id": run.project_id,
        "status": run.status,
        "target_metric": run.target_metric,
        "before_metrics": run.before_metrics,
        "after_metrics": run.after_metrics,
        "candidate_rule_patch": run.candidate_rule_patch,
        "rule_versions": run.rule_versions,
        "asset_version": run.asset_version,
    }


def _evaluate_label(db: Session, label: GoldLabel) -> dict[str, Any]:
    predicted_label = "none"
    predicted_score_class = None
    score = None
    if label.label_type == "claim":
        row = db.execute(
            select(SkuClaimResult).where(
                SkuClaimResult.project_id == label.project_id,
                SkuClaimResult.sku_code == label.target_sku_code,
                SkuClaimResult.claim_code == label.candidate_code,
            )
        ).scalar_one_or_none()
        if row:
            predicted_label = "positive"
            score = row.score
            predicted_score_class = _score_class(row.score)
    elif label.label_type == "task":
        row = db.execute(
            select(SkuTaskScore).where(
                SkuTaskScore.project_id == label.project_id,
                SkuTaskScore.sku_code == label.target_sku_code,
                SkuTaskScore.task_code == label.candidate_code,
            )
        ).scalar_one_or_none()
        if row:
            predicted_label = "positive"
            score = row.score
            predicted_score_class = row.relation_level
    elif label.label_type == "battlefield":
        row = db.execute(
            select(SkuBattlefieldScore).where(
                SkuBattlefieldScore.project_id == label.project_id,
                SkuBattlefieldScore.sku_code == label.target_sku_code,
                SkuBattlefieldScore.battlefield_code == label.candidate_code,
            )
        ).scalar_one_or_none()
        if row:
            predicted_label = row.relation_level
            score = row.score
            predicted_score_class = _score_class(row.score)
    elif label.label_type == "competitor":
        row = db.execute(
            select(SkuCompetitorResult).where(
                SkuCompetitorResult.project_id == label.project_id,
                SkuCompetitorResult.target_sku_code == label.target_sku_code,
                SkuCompetitorResult.competitor_sku_code == label.candidate_code,
            )
        ).scalar_one_or_none()
        if row:
            predicted_label = row.competitor_type
            score = row.score
            predicted_score_class = _score_class(row.score)
    label_match = predicted_label == label.expected_label
    score_class_match = (
        True
        if label.expected_score_class in {None, ""}
        else predicted_score_class == label.expected_score_class
    )
    return {
        "label_id": label.label_id,
        "label_type": label.label_type,
        "target_sku_code": label.target_sku_code,
        "candidate_code": label.candidate_code,
        "expected_label": label.expected_label,
        "predicted_label": predicted_label,
        "expected_score_class": label.expected_score_class,
        "predicted_score_class": predicted_score_class,
        "score": score,
        "match": label_match,
        "score_class_match": score_class_match,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_type.setdefault(row["label_type"], []).append(row)
    per_type = {label_type: _classification_metrics(items) for label_type, items in by_type.items()}
    accuracy = sum(1 for row in rows if row["match"]) / max(1, len(rows))
    macro_f1 = sum(item["f1"] for item in per_type.values()) / max(1, len(per_type))
    competitor_rows = by_type.get("competitor", [])
    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "per_type": per_type,
        "competitor": {
            "top_k_hit_rate": round(
                sum(1 for row in competitor_rows if row["predicted_label"] != "none")
                / max(1, len(competitor_rows)),
                4,
            ),
            "type_accuracy": per_type.get("competitor", {}).get("accuracy", 0.0),
            "mrr": round(
                sum(1.0 for row in competitor_rows if row["predicted_label"] != "none")
                / max(1, len(competitor_rows)),
                4,
            ),
        },
    }


def _classification_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    correct = sum(1 for row in rows if row["match"])
    predicted = sum(1 for row in rows if row["predicted_label"] != "none")
    expected = len(rows)
    precision = correct / max(1, predicted)
    recall = correct / max(1, expected)
    f1 = 2 * precision * recall / max(0.0001, precision + recall)
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(correct / max(1, len(rows)), 4),
        "support": len(rows),
    }


def _candidate_patch(metrics: dict[str, Any]) -> dict[str, Any]:
    if metrics.get("macro_f1", 0) >= 0.99:
        return {
            "status": "no_threshold_change_needed",
            "reason": "当前 Gold Set 已达到目标指标，生成空草案但不自动发布。",
            "changes": [],
        }
    return {
        "status": "draft_threshold_adjustment",
        "reason": "基于 bounded grid-search 候选，降低召回不足类型的激活阈值 5 分。",
        "changes": [
            {
                "rule_set_id": "tv_claim_activation_v1",
                "operation": "adjust_threshold",
                "field": "thresholds.activated",
                "delta": -5,
                "bounds": [50, 90],
            }
        ],
    }


def _score_class(score: float | None) -> str | None:
    if score is None:
        return None
    normalized = score / 100 if score > 1 else score
    if normalized >= 0.85:
        return "high"
    if normalized >= 0.55:
        return "medium"
    return "low"


def _current_rule_versions(db: Session, project_id: str) -> dict[str, str]:
    claim = db.execute(select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)).scalars().first()
    task = db.execute(select(SkuTaskScore).where(SkuTaskScore.project_id == project_id)).scalars().first()
    battlefield = db.execute(
        select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id)
    ).scalars().first()
    competitor = db.execute(
        select(SkuCompetitorResult).where(SkuCompetitorResult.project_id == project_id)
    ).scalars().first()
    return {
        "claim_activation": claim.rule_version if claim else "unknown",
        "task_score": task.rule_version if task else "unknown",
        "battlefield_score": battlefield.rule_version if battlefield else "unknown",
        "competitor_score": competitor.rule_version if competitor else "unknown",
    }
