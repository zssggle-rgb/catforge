from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    AssetVersion,
    BattlefieldDef,
    CalibrationRun,
    CategoryProject,
    ClaimValueLayerResult,
    CommentTopicDef,
    EvaluationRun,
    EvidenceItem,
    ImportBatch,
    RawMarketFact,
    RawSkuClaim,
    RawSkuComment,
    RawSkuMaster,
    RawSkuParam,
    ReviewQueue,
    RuntimeExport,
    SourceFile,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuCommentTopicResult,
    SkuCompetitorResult,
    SkuParamNormalized,
    SkuTaskScore,
    StdClaimDef,
    StdParamDef,
    TargetGroupDef,
    UserTaskDef,
)
from app.services.audit_service import create_audit_event
from app.services.factory_utils import ensure_seed_assets
from app.services.goal1_analysis_service import get_goal1_analysis, run_goal1_analysis, run_to_dict
from app.services.goal1_evaluation_service import (
    calibration_to_dict,
    evaluation_to_dict,
    import_goal1_gold_labels,
    run_goal1_calibration,
)
from app.services.market_metrics_engine import calculate_market_metrics
from app.services.profiling_service import data_quality_report
from app.services.review_service import build_review_queue
from app.services.runtime_export_service import _allowed_files, _forbidden_patterns
from app.services.version_governance_service import asset_version_to_dict, latest_released_asset_version


LIBRARY_MODELS = {
    "parameters": (StdParamDef, "param_id", "param_code", "param_name"),
    "claims": (StdClaimDef, "claim_id", "claim_code", "claim_name"),
    "comment_topics": (CommentTopicDef, "topic_id", "topic_code", "topic_name"),
    "tasks": (UserTaskDef, "task_id", "task_code", "task_name"),
    "target_groups": (TargetGroupDef, "target_group_id", "target_group_code", "target_group_name"),
    "battlefields": (BattlefieldDef, "battlefield_id", "battlefield_code", "battlefield_name"),
}

LIBRARY_ALIASES = {
    "comment-topics": "comment_topics",
    "comment_topics": "comment_topics",
    "user-tasks": "tasks",
    "tasks": "tasks",
    "target-groups": "target_groups",
    "target_groups": "target_groups",
    "value-battlefields": "battlefields",
    "battlefields": "battlefields",
    "parameters": "parameters",
    "claims": "claims",
}

APPROVED_DELIVERABLES = [
    "TV category semantic asset pack",
    "TV SKU analysis result pack",
    "TV market calibration report",
    "runtime scoring rules",
    "competitor runtime rules",
    "evidence cards",
    "release manifest",
]


def use_tv_fixture(db: Session, project_id: str, *, target_sku_code: str = "TV00029115") -> dict[str, Any]:
    run = run_goal1_analysis(db, project_id, target_sku_code=target_sku_code)
    market_metrics = calculate_market_metrics(db, project_id)
    calibration: dict[str, Any] | None = None
    try:
        import_goal1_gold_labels(db, project_id)
        calibration = calibration_to_dict(run_goal1_calibration(db, project_id))
    except ValueError:
        calibration = None
    review = build_review_queue(db, project_id)
    return {
        "status": "completed",
        "analysis_run": run_to_dict(run),
        "market_metrics": market_metrics,
        "calibration": calibration,
        "review_queue": review,
        "message": "已载入 1000-SKU 风格彩电夹具数据并完成内部工作台分析。",
    }


def profile_dashboard(db: Session, project_id: str) -> dict[str, Any]:
    project = _project_or_raise(db, project_id)
    ensure_seed_assets(db, project_id, project.category_code)
    quality = data_quality_report(db, project_id)
    masters = db.execute(select(RawSkuMaster).where(RawSkuMaster.project_id == project_id)).scalars().all()
    params = db.execute(select(RawSkuParam).where(RawSkuParam.project_id == project_id)).scalars().all()
    claims = db.execute(select(RawSkuClaim).where(RawSkuClaim.project_id == project_id)).scalars().all()
    comments = db.execute(select(RawSkuComment).where(RawSkuComment.project_id == project_id)).scalars().all()
    markets = db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id)).scalars().all()
    latest_run = db.execute(
        select(AnalysisRun).where(AnalysisRun.project_id == project_id).order_by(AnalysisRun.created_at.desc())
    ).scalars().first()
    sku_codes = [row.sku_code for row in masters if row.sku_code]
    model_names = [row.model_name for row in masters if row.model_name]
    time_values = _time_values(masters, params, claims, comments, markets)
    return {
        "project_id": project_id,
        "category_code": project.category_code,
        "sku_count": len(set(sku_codes)),
        "brand_count": len({row.brand for row in masters if row.brand}),
        "channel_count": len(_channels(params, claims, comments, markets)),
        "time_range": {"start": min(time_values) if time_values else "unknown", "end": max(time_values) if time_values else "unknown"},
        "raw_parameter_row_count": len(params),
        "raw_claim_row_count": len(claims),
        "raw_comment_row_count": len(comments),
        "market_fact_row_count": len(markets),
        "source_row_counts": quality["summary"].get("raw_row_counts", {}),
        "missing_field_rates": _missing_field_rates(masters, params, claims, comments, markets),
        "duplicate_sku_count": _duplicate_count(sku_codes),
        "duplicate_model_count": _duplicate_count(model_names),
        "unmapped_parameter_fields": _unmapped_parameter_fields(db, project_id, params),
        "unmapped_claim_clusters": _unmapped_claim_clusters(db, project_id, claims),
        "quality_summary": quality["summary"],
        "quality_issues": quality["issues"],
        "latest_analysis_run": run_to_dict(latest_run) if latest_run else None,
    }


def library_rows(db: Session, project_id: str, library_type: str) -> dict[str, Any]:
    key = _library_key(library_type)
    model, _, _, _ = LIBRARY_MODELS[key]
    project = _project_or_raise(db, project_id)
    ensure_seed_assets(db, project_id, project.category_code)
    rows = db.execute(select(model).where(model.project_id == project_id)).scalars().all()
    return {
        "library_type": key,
        "count": len(rows),
        "items": [_library_row(db, row, key) for row in rows],
    }


def mapping_rules(db: Session, project_id: str) -> dict[str, Any]:
    project = _project_or_raise(db, project_id)
    ensure_seed_assets(db, project_id, project.category_code)
    items: list[dict[str, Any]] = []
    params = db.execute(select(StdParamDef).where(StdParamDef.project_id == project_id)).scalars().all()
    claims = db.execute(select(StdClaimDef).where(StdClaimDef.project_id == project_id)).scalars().all()
    topics = db.execute(select(CommentTopicDef).where(CommentTopicDef.project_id == project_id)).scalars().all()
    tasks = db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars().all()
    battlefields = db.execute(select(BattlefieldDef).where(BattlefieldDef.project_id == project_id)).scalars().all()

    for param in params:
        for claim_code in param.mapped_claim_codes or []:
            items.append(_mapping_row(db, project_id, "param", param.param_code, "claim", claim_code, "supports", 0.82, param.normalize_rule, param.version))
    for claim in claims:
        for task_code in claim.mapped_task_codes or []:
            items.append(_mapping_row(db, project_id, "claim", claim.claim_code, "task", task_code, "activates", 0.8, claim.activation_rule, claim.version))
        for battlefield_code in claim.mapped_battlefield_codes or []:
            items.append(_mapping_row(db, project_id, "claim", claim.claim_code, "battlefield", battlefield_code, "supports", 0.76, claim.raw_keywords, claim.version))
    for topic in topics:
        for claim_code in topic.mapped_claim_codes or []:
            items.append(_mapping_row(db, project_id, "comment_topic", topic.topic_code, "claim", claim_code, "perception_evidence", 0.68, topic.keywords, topic.version))
        for task_code in topic.mapped_task_codes or []:
            items.append(_mapping_row(db, project_id, "comment_topic", topic.topic_code, "task", task_code, "experience_signal", 0.72, topic.keywords, topic.version))
    for task in tasks:
        for target_code in task.default_target_group_codes or []:
            items.append(_mapping_row(db, project_id, "task", task.task_code, "target_group", target_code, "implies", 0.72, task.score_rule, task.version))
        for battlefield_code in task.battlefield_codes or []:
            items.append(_mapping_row(db, project_id, "task", task.task_code, "battlefield", battlefield_code, "enters", 0.8, task.score_rule, task.version))
    for battlefield in battlefields:
        if battlefield.competitor_rule_ref:
            items.append(_mapping_row(db, project_id, "battlefield", battlefield.battlefield_code, "competitor_rule", battlefield.competitor_rule_ref, "uses_runtime_rule", 0.8, battlefield.entry_thresholds, battlefield.version))
    return {"count": len(items), "items": items}


def review_asset(
    db: Session,
    project_id: str,
    asset_type: str,
    asset_id: str,
    *,
    decision: str,
    reviewer: str,
    decision_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row, key = _find_library_row(db, project_id, asset_type, asset_id)
    before = _serialize(row)
    status = {
        "approved": "approved",
        "rejected": "rejected",
        "needs_split": "needs_split",
        "needs_merge": "needs_merge",
        "deprecated": "deprecated",
        "pending": "pending",
    }.get(decision)
    if status is None:
        raise ValueError(f"不支持的复核状态: {decision}")
    row.status = status
    review = ReviewQueue(
        project_id=project_id,
        category_code=row.category_code,
        item_type=f"asset_{key}",
        item_key=getattr(row, LIBRARY_MODELS[key][2]),
        reason_code="asset_library_review",
        evidence_ids=[],
        candidate_payload={
            "asset_type": key,
            "asset_id": asset_id,
            "decision": decision,
            "review_context": {
                "object_type": f"asset_{key}",
                "object_type_label": _library_label(key),
                "decision_target": getattr(row, LIBRARY_MODELS[key][2]),
                "result_feedback": "复核决定会写回对应资产库行的 review_status/status，并影响发布门禁统计。",
            },
            **(decision_payload or {}),
        },
        confidence=float(getattr(row, "evidence_weight", 0.8) or 0.8),
        priority="medium",
        status=decision,
        reviewer=reviewer,
        decision_payload=decision_payload or {},
    )
    db.add(review)
    db.flush()
    create_audit_event(
        db,
        action=f"asset_library_review_{decision}",
        object_type=f"asset_{key}",
        object_id=getattr(row, LIBRARY_MODELS[key][2]),
        project_id=project_id,
        actor_id=reviewer,
        before=before,
        after=_serialize(row),
        metadata={"review_id": review.review_id},
    )
    db.commit()
    db.refresh(row)
    return _library_row(db, row, key)


def update_asset(
    db: Session,
    project_id: str,
    asset_type: str,
    asset_id: str,
    *,
    patch: dict[str, Any],
    actor_id: str = "api",
) -> dict[str, Any]:
    row, key = _find_library_row(db, project_id, asset_type, asset_id)
    before = _serialize(row)
    editable = {
        "param_name", "param_group", "data_type", "unit", "raw_aliases", "normalize_rule", "level_rule",
        "business_meaning", "mapped_claim_codes", "claim_name", "claim_group", "definition", "activation_rule",
        "raw_keywords", "supporting_param_codes", "comment_topic_codes", "mapped_task_codes",
        "mapped_battlefield_codes", "topic_name", "topic_group", "keywords", "sentiment_hint",
        "mapped_task_codes", "task_name", "positive_claim_codes", "positive_param_codes",
        "default_target_group_codes", "battlefield_codes", "score_rule", "target_group_name",
        "battlefield_name", "required_signal_rule", "entry_thresholds", "competitor_rule_ref",
    }
    for field, value in patch.items():
        if field in editable and hasattr(row, field):
            setattr(row, field, value)
    row.status = "pending"
    create_audit_event(
        db,
        action="asset_library_edit",
        object_type=f"asset_{key}",
        object_id=getattr(row, LIBRARY_MODELS[key][2]),
        project_id=project_id,
        actor_id=actor_id,
        before=before,
        after=_serialize(row),
    )
    db.commit()
    db.refresh(row)
    return _library_row(db, row, key)


def merge_assets(db: Session, project_id: str, asset_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _record_asset_operation(db, project_id, asset_type, payload, operation="needs_merge")


def split_asset(db: Session, project_id: str, asset_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _record_asset_operation(db, project_id, asset_type, payload, operation="needs_split")


def sku_batch_results(db: Session, project_id: str) -> dict[str, Any]:
    skus = sorted({row.sku_code for row in db.execute(select(RawSkuMaster).where(RawSkuMaster.project_id == project_id)).scalars() if row.sku_code})
    items = [_sku_summary_row(db, project_id, sku_code) for sku_code in skus]
    return {"count": len(items), "items": items}


def sku_qa_detail(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    summary = _sku_summary_row(db, project_id, sku_code)
    analysis = get_goal1_analysis(db, project_id, sku_code)
    params = db.execute(select(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id, SkuParamNormalized.sku_code == sku_code)).scalars().all()
    topics = db.execute(select(SkuCommentTopicResult).where(SkuCommentTopicResult.project_id == project_id, SkuCommentTopicResult.sku_code == sku_code)).scalars().all()
    value_layers = _sku_claim_value_layers(db, project_id, sku_code)
    competitors = db.execute(select(SkuCompetitorResult).where(SkuCompetitorResult.project_id == project_id, SkuCompetitorResult.target_sku_code == sku_code).order_by(SkuCompetitorResult.rank)).scalars().all()
    evidence_ids = _unique(
        [e for row in params for e in row.evidence_ids]
        + [e for row in analysis["claim_results"] for e in row.get("evidence_ids", [])]
        + [e for row in analysis["task_scores"] for e in row.get("evidence_ids", [])]
        + [e for row in analysis["battlefield_scores"] for e in row.get("evidence_ids", [])]
        + [e for row in topics for e in row.evidence_ids]
        + [e for row in competitors for e in row.evidence_ids]
    )
    evidence_cards = _evidence_cards(db, project_id, evidence_ids)
    return {
        "sku_code": sku_code,
        "signal_card": summary,
        "normalized_parameters": [_result_row(db, row, "param", row.param_code, row.normalized_value, {"unit": row.unit, "numeric": row.normalized_numeric, "bool": row.normalized_bool}) for row in params],
        "activated_standard_claims": analysis["claim_results"],
        "comment_topic_evidence": [_result_row(db, row, "comment_topic", row.topic_code, row.sentiment, {"activates_product_claim": row.activates_product_claim}) for row in topics],
        "user_task_scores": analysis["task_scores"],
        "target_group_scores": _target_group_scores(db, project_id, analysis["task_scores"]),
        "battlefield_scores": analysis["battlefield_scores"],
        "claim_value_layers": value_layers,
        "competitor_relationships": [_competitor_row(row) for row in competitors],
        "evidence_cards": evidence_cards,
        "review_flags": _review_flags(db, project_id, sku_code),
        "report_preview": _sku_report_preview(summary, analysis, value_layers),
    }


def sku_evidence(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    detail = sku_qa_detail(db, project_id, sku_code)
    return {"sku_code": sku_code, "count": len(detail["evidence_cards"]), "items": detail["evidence_cards"]}


def sku_competitors(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    return competitor_inspection(db, project_id, sku_code=sku_code)


def sku_report_preview(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    detail = sku_qa_detail(db, project_id, sku_code)
    return {"sku_code": sku_code, "report_preview": detail["report_preview"]}


def competitor_inspection(db: Session, project_id: str, sku_code: str | None = None) -> dict[str, Any]:
    query = select(SkuCompetitorResult).where(SkuCompetitorResult.project_id == project_id)
    if sku_code:
        query = query.where(SkuCompetitorResult.target_sku_code == sku_code)
    rows = db.execute(query.order_by(SkuCompetitorResult.target_sku_code, SkuCompetitorResult.rank)).scalars().all()
    return {"count": len(rows), "items": [_competitor_row(row) for row in rows]}


def calibration_summary(db: Session, project_id: str) -> dict[str, Any]:
    return calibration_report(db, project_id)


def calibration_claims(db: Session, project_id: str) -> dict[str, Any]:
    rows = db.execute(select(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == project_id)).scalars().all()
    return {"count": len(rows), "items": [_serialize(row) for row in rows]}


def calibration_battlefields(db: Session, project_id: str) -> dict[str, Any]:
    rows = db.execute(select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id)).scalars().all()
    grouped: dict[str, list[SkuBattlefieldScore]] = {}
    for row in rows:
        grouped.setdefault(row.battlefield_code, []).append(row)
    items = []
    sku_count = max(1, len({row.sku_code for row in rows}))
    for code, values in grouped.items():
        items.append(
            {
                "battlefield_code": code,
                "sku_coverage": round(len({row.sku_code for row in values}) / sku_count, 4),
                "avg_score": _avg([row.score for row in values]),
                "avg_confidence": _avg([row.confidence for row in values]),
                "review_status": _combined_review_status([row.review_status for row in values]),
                "evidence_ids": _unique([e for row in values for e in row.evidence_ids]),
            }
        )
    return {"count": len(items), "items": items}


def calibration_review_summary(db: Session, project_id: str) -> dict[str, Any]:
    return {"project_id": project_id, "review_summary": _review_status_summary(db, project_id)}


def calibration_report(db: Session, project_id: str) -> dict[str, Any]:
    evaluation = db.execute(select(EvaluationRun).where(EvaluationRun.project_id == project_id).order_by(EvaluationRun.created_at.desc())).scalars().first()
    calibration = db.execute(select(CalibrationRun).where(CalibrationRun.project_id == project_id).order_by(CalibrationRun.created_at.desc())).scalars().first()
    claim_metrics = db.execute(select(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == project_id)).scalars().all()
    parameter_rows = library_rows(db, project_id, "parameters")["items"]
    topic_rows = library_rows(db, project_id, "comment_topics")["items"]
    review_summary = _review_status_summary(db, project_id)
    return {
        "project_id": project_id,
        "parameter_coverage": [{"param_code": row["param_code"], "coverage_rate": row["field_coverage_rate"], "unknown_rate": row["value_unknown_rate"]} for row in parameter_rows],
        "claim_coverage": [{"claim_code": row.claim_code, "coverage_rate": row.coverage_rate, "psi": row.psi, "ssi": row.ssi, "cpi": row.cpi, "sample_sufficiency": row.comparable_sample_count} for row in claim_metrics],
        "comment_topic_coverage": [{"topic_code": row["topic_code"], "mention_rate": row["mention_rate"], "positive_rate": row["positive_rate"], "negative_rate": row["negative_rate"]} for row in topic_rows],
        "psi_price_support": {row.claim_code: row.psi for row in claim_metrics},
        "ssi_sales_support": {row.claim_code: row.ssi for row in claim_metrics},
        "cpi_comment_perception": {row.claim_code: row.cpi for row in claim_metrics},
        "sample_sufficiency": {row.claim_code: row.comparable_sample_count for row in claim_metrics},
        "expert_review_summary": review_summary,
        "evaluation_metrics": evaluation.metrics if evaluation else {},
        "evaluation": evaluation_to_dict(evaluation) if evaluation else None,
        "calibration": calibration_to_dict(calibration) if calibration else None,
        "release_recommendation": _release_recommendation(review_summary, claim_metrics),
    }


def export_preview(db: Session, project_id: str) -> dict[str, Any]:
    project = _project_or_raise(db, project_id)
    released = latest_released_asset_version(db, project_id)
    versions = db.execute(select(AssetVersion).where(AssetVersion.project_id == project_id).order_by(AssetVersion.created_at.desc())).scalars().all()
    allowed = sorted(_allowed_files())
    return {
        "project_id": project_id,
        "category_code": project.category_code,
        "released_asset_version": asset_version_to_dict(released) if released else None,
        "asset_versions": [asset_version_to_dict(row) for row in versions],
        "export_manifest_preview": {
            "asset_version": released.version if released else "unreleased",
            "category": project.category_code,
            "files": allowed,
            "created_at": datetime.utcnow().isoformat(),
            "forbidden_patterns_checked": True,
        },
        "file_list": [{"file": file_name, "deliverable": _deliverable_for_file(file_name), "exportable": True} for file_name in allowed],
        "approved_deliverables": APPROVED_DELIVERABLES,
        "forbidden_patterns": _forbidden_patterns(),
        "factory_exclusions": [
            "prompt templates",
            "Gold Set builders",
            "rule generators",
            "semantic clustering internals",
            "cross-category migration tools",
            "raw expert annotations",
            "factory run logs",
        ],
        "release_gate": {
            "has_released_version": released is not None,
            "export_allowed": released is not None,
            "factory_only_content_blocked": True,
            "internal_boundary": "CatForge 是内部品类资产生产线；运行态导出只包含已批准交付物，不包含工厂生成逻辑。",
        },
    }


def export_manifest(db: Session, project_id: str, export_id: str) -> dict[str, Any]:
    row = db.execute(select(RuntimeExport).where(RuntimeExport.project_id == project_id, RuntimeExport.export_id == export_id)).scalar_one_or_none()
    if not row:
        raise ValueError("导出不存在")
    return row.manifest_json


def _library_row(db: Session, row: Any, library_type: str) -> dict[str, Any]:
    if library_type == "parameters":
        coverage, unknown_rate = _param_coverage(db, row.project_id, row.param_code)
        evidence_ids = _asset_evidence_ids(db, row.project_id, "param", [row.param_code, row.param_name, *(row.raw_aliases or [])])
        common = _common_row(db, row.project_id, "standard_parameter", row.param_code, row.param_name, row.business_meaning or "由原始参数字段、参数值和卖点文本派生参数共同形成。", _param_examples(db, row.project_id, row.param_code, row.raw_aliases), {"data_type": row.data_type, "unit": row.unit, "normalize_rule": row.normalize_rule, "level_rule": row.level_rule}, {"mapped_claim_codes": row.mapped_claim_codes}, evidence_ids, row.evidence_weight, row.status, row.version, row.version)
        return {**common, "param_id": row.param_id, "param_code": row.param_code, "param_name": row.param_name, "param_group": row.param_group, "data_type": row.data_type, "unit": row.unit, "raw_aliases": row.raw_aliases, "normalize_rule": row.normalize_rule, "level_rule": row.level_rule, "business_meaning": row.business_meaning, "mapped_claim_codes": row.mapped_claim_codes, "field_coverage_rate": coverage, "value_unknown_rate": unknown_rate, "example_raw_fields": common["raw_fields_or_text_examples"].get("fields", []), "example_raw_values": common["raw_fields_or_text_examples"].get("values", []), "generation_method": "seed+rule+field_coverage"}
    if library_type == "claims":
        metric = db.execute(select(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == row.project_id, ClaimValueLayerResult.claim_code == row.claim_code)).scalars().first()
        evidence_ids = _asset_evidence_ids(db, row.project_id, "claim", [row.claim_code, row.claim_name, *(row.raw_keywords or [])])
        coverage = metric.coverage_rate if metric else _claim_coverage(db, row.project_id, row.claim_code)
        common = _common_row(db, row.project_id, "standard_claim", row.claim_code, row.claim_name, row.definition, _claim_examples(db, row.project_id, row.raw_keywords), {"activation_rule": row.activation_rule, "supporting_param_codes": row.supporting_param_codes, "comment_topic_codes": row.comment_topic_codes, "default_value_layer_hint": row.default_layer_hint}, {"mapped_task_codes": row.mapped_task_codes, "mapped_battlefield_codes": row.mapped_battlefield_codes}, evidence_ids, 0.82, row.status, row.version, row.version)
        return {**common, "claim_id": row.claim_id, "claim_code": row.claim_code, "claim_name": row.claim_name, "claim_group": row.claim_group, "definition": row.definition, "activation_rule": row.activation_rule, "raw_keywords": row.raw_keywords, "supporting_param_codes": row.supporting_param_codes, "comment_topic_codes": row.comment_topic_codes, "mapped_task_codes": row.mapped_task_codes, "mapped_battlefield_codes": row.mapped_battlefield_codes, "default_value_layer_hint": row.default_layer_hint, "coverage_rate": coverage, "psi_price_support": metric.psi if metric else None, "ssi_sales_support": metric.ssi if metric else None, "cpi_comment_perception": metric.cpi if metric else None, "sample_sufficiency": metric.comparable_sample_count if metric else 0, "example_raw_claims": common["raw_fields_or_text_examples"], "generation_method": "seed+rule+market_calibrated"}
    if library_type == "comment_topics":
        stats = _topic_stats(db, row.project_id, row.topic_code)
        evidence_ids = _asset_evidence_ids(db, row.project_id, "comment", [row.topic_code, row.topic_name, *(row.keywords or [])])
        common = _common_row(db, row.project_id, "comment_topic", row.topic_code, row.topic_name, f"由评论句子、情感和产品/服务体验分类形成；主题组 {row.topic_group}。", _topic_examples(db, row.project_id, row.topic_code, row.keywords), {"product_or_service": "product" if row.activates_product_claim else "service", "sentiment_scope": row.sentiment_hint}, {"mapped_claim_codes": row.mapped_claim_codes, "mapped_task_codes": row.mapped_task_codes}, evidence_ids, 0.78, row.status, row.version, row.version)
        return {**common, "topic_id": row.topic_id, "topic_code": row.topic_code, "topic_name": row.topic_name, "topic_group": row.topic_group, "product_or_service": "product" if row.activates_product_claim else "service", "sentiment_scope": row.sentiment_hint, "raw_keywords": row.keywords, "example_sentences": common["raw_fields_or_text_examples"], "mapped_claim_codes": row.mapped_claim_codes, "mapped_task_codes": row.mapped_task_codes, **stats}
    if library_type == "tasks":
        examples = _example_skus_for_task(db, row.project_id, row.task_code)
        evidence_ids = _asset_evidence_ids(db, row.project_id, None, [row.task_code, row.task_name, *(row.positive_claim_codes or []), *(row.positive_param_codes or [])])
        common = _common_row(db, row.project_id, "user_task", row.task_code, row.task_name, row.definition, row.comment_topic_codes, {"positive_claim_codes": row.positive_claim_codes, "positive_param_codes": row.positive_param_codes, "positive_comment_topic_codes": row.comment_topic_codes, "negative_or_weak_signals": []}, {"mapped_target_group_codes": row.default_target_group_codes, "mapped_battlefield_codes": row.battlefield_codes}, evidence_ids, 0.8, row.status, row.version, row.version)
        return {**common, "task_id": row.task_id, "task_code": row.task_code, "task_name": row.task_name, "definition": row.definition, "positive_claim_codes": row.positive_claim_codes, "positive_param_codes": row.positive_param_codes, "positive_comment_topic_codes": row.comment_topic_codes, "negative_or_weak_signals": [], "mapped_target_group_codes": row.default_target_group_codes, "mapped_battlefield_codes": row.battlefield_codes, "scoring_rule_id": f"{row.task_code}:{row.version}", "example_skus": examples}
    if library_type == "target_groups":
        source_tasks = _source_tasks_for_target_group(db, row.project_id, row.target_group_code)
        common = _common_row(db, row.project_id, "target_group", row.target_group_code, row.target_group_name, row.definition, [], {"price_band_signals": _price_signals(db, row.project_id), "channel_signals": _channel_signals(db, row.project_id), "comment_topic_signals": source_tasks}, {"source_task_codes": source_tasks}, [], 0.76, row.status, row.version, row.version)
        return {**common, "target_group_id": row.target_group_id, "target_group_code": row.target_group_code, "target_group_name": row.target_group_name, "definition": row.definition, "source_task_codes": source_tasks, "price_band_signals": common["derived_features"]["price_band_signals"], "channel_signals": common["derived_features"]["channel_signals"], "comment_topic_signals": common["derived_features"]["comment_topic_signals"], "example_skus": _example_skus_for_target_group(db, row.project_id, row.target_group_code)}
    examples = _example_skus_for_battlefield(db, row.project_id, row.battlefield_code)
    density = round(len(examples) / max(1, _sku_count(db, row.project_id)), 4)
    common = _common_row(db, row.project_id, "battlefield", row.battlefield_code, row.battlefield_name, row.definition, [], {"required_signal_rule": row.required_signal_rule, "score_rule": row.score_rule, "entry_thresholds": row.entry_thresholds}, {"competitor_rule_ref": row.competitor_rule_ref}, [], 0.78, row.status, row.version, row.version)
    return {**common, "battlefield_id": row.battlefield_id, "battlefield_code": row.battlefield_code, "battlefield_name": row.battlefield_name, "definition": row.definition, "core_task_codes": _core_tasks_for_battlefield(db, row.project_id, row.battlefield_code), "core_claim_codes": _core_claims_for_battlefield(db, row.project_id, row.battlefield_code), "core_param_codes": _core_params_for_battlefield(db, row.project_id, row.battlefield_code), "target_group_codes": _target_groups_for_battlefield(db, row.project_id, row.battlefield_code), "entry_rule": row.required_signal_rule, "main_threshold": (row.entry_thresholds or {}).get("main"), "secondary_threshold": (row.entry_thresholds or {}).get("secondary"), "opportunity_threshold": (row.entry_thresholds or {}).get("opportunity"), "weak_threshold": (row.entry_thresholds or {}).get("weak"), "example_skus": examples, "market_density": density}


def _common_row(
    db: Session,
    project_id: str,
    object_type: str,
    object_code: str,
    object_name: str,
    source_basis: Any,
    raw_examples: Any,
    derived_features: Any,
    mapping_lineage: Any,
    evidence_ids: list[str],
    confidence: float,
    review_status: str,
    asset_version: str,
    rule_version: str,
) -> dict[str, Any]:
    meta = _review_meta(db, project_id, object_code)
    source = _latest_source(db, project_id)
    return {
        "object_type": object_type,
        "object_code": object_code,
        "object_name": object_name,
        "source_basis": source_basis,
        "source_dataset_id": source["source_dataset_id"],
        "source_batch_id": source["source_batch_id"],
        "raw_fields_or_text_examples": raw_examples,
        "derived_features": derived_features,
        "mapping_lineage": mapping_lineage,
        "evidence_ids": evidence_ids,
        "confidence": round(float(confidence or 0.0), 4),
        "review_status": review_status or "unknown",
        "asset_version": asset_version,
        "rule_version": rule_version,
        "last_reviewer": meta["last_reviewer"],
        "review_timestamp": meta["review_timestamp"],
    }


def _mapping_row(db: Session, project_id: str, source_type: str, source_code: str, target_type: str, target_code: str, relation_type: str, weight: float, evidence_basis: Any, version: str) -> dict[str, Any]:
    evidence_ids = _asset_evidence_ids(db, project_id, None, [source_code, target_code])
    return {
        **_common_row(db, project_id, "mapping_rule", f"{source_type}:{source_code}->{target_type}:{target_code}", relation_type, f"{source_type} 到 {target_type} 的语义图边", evidence_basis, {"weight": weight, "condition": evidence_basis}, {"source_type": source_type, "source_code": source_code, "target_type": target_type, "target_code": target_code}, evidence_ids, weight, "pending", version, version),
        "source_type": source_type,
        "source_code": source_code,
        "target_type": target_type,
        "target_code": target_code,
        "relation_type": relation_type,
        "weight": weight,
        "condition": evidence_basis,
        "evidence_basis": evidence_basis,
    }


def _sku_summary_row(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    master = db.execute(select(RawSkuMaster).where(RawSkuMaster.project_id == project_id, RawSkuMaster.sku_code == sku_code)).scalars().first()
    market = db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id, RawMarketFact.sku_code == sku_code)).scalars().first()
    claims = db.execute(select(SkuClaimResult).where(SkuClaimResult.project_id == project_id, SkuClaimResult.sku_code == sku_code)).scalars().all()
    tasks = db.execute(select(SkuTaskScore).where(SkuTaskScore.project_id == project_id, SkuTaskScore.sku_code == sku_code)).scalars().all()
    battlefields = db.execute(select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id, SkuBattlefieldScore.sku_code == sku_code)).scalars().all()
    competitors = db.execute(select(SkuCompetitorResult).where(SkuCompetitorResult.project_id == project_id, SkuCompetitorResult.target_sku_code == sku_code)).scalars().all()
    evidence_ids = _unique([e for row in claims + tasks + battlefields + competitors for e in row.evidence_ids])
    return {
        "sku_code": sku_code,
        "brand": master.brand if master else "unknown",
        "model": master.model_name if master else "unknown",
        "price_band": _price_band(market.avg_price if market else None),
        "channels": [market.channel_name or market.channel_group] if market and (market.channel_name or market.channel_group) else [],
        "sales_volume": market.sales_volume if market else None,
        "sales_amount": market.sales_amount if market else None,
        "source_basis": "released assets + raw SKU facts + market facts + comments",
        "raw_fields_or_text_examples": {**_raw_sku_fields(db, project_id, sku_code), **_raw_text_examples(db, project_id, sku_code)},
        "derived_features": {"claim_count": len(claims), "task_count": len(tasks), "battlefield_count": len(battlefields), "direct_competitor_count": len([row for row in competitors if row.competitor_type == "direct"])},
        "mapping_lineage": {"top_activated_claims": _top_codes(claims, "claim_code", "score"), "top_user_tasks": _top_codes(tasks, "task_code", "score"), "target_groups": _target_group_scores(db, project_id, [_serialize(row) for row in tasks]), "battlefield_assignments": _top_codes(battlefields, "battlefield_code", "score"), "claim_value_layers": _sku_claim_value_layers(db, project_id, sku_code)},
        "top_activated_claims": _top_codes(claims, "claim_code", "score"),
        "top_user_tasks": _top_codes(tasks, "task_code", "score"),
        "target_groups": [item["target_group_code"] for item in _target_group_scores(db, project_id, [_serialize(row) for row in tasks])],
        "battlefield_assignments": _top_codes(battlefields, "battlefield_code", "score"),
        "claim_value_layers": _sku_claim_value_layers(db, project_id, sku_code),
        "direct_competitor_count": len([row for row in competitors if row.competitor_type == "direct"]),
        "review_flags": _review_flags(db, project_id, sku_code),
        "evidence_ids": evidence_ids,
        "confidence": _avg([row.confidence for row in claims + tasks + battlefields]),
        "review_status": _combined_review_status([row.review_status for row in claims + tasks + battlefields]),
        "asset_version": _first([getattr(row, "asset_version", None) for row in claims + tasks + battlefields]) or "unknown",
        "rule_version": _first([getattr(row, "rule_version", None) for row in claims + tasks + battlefields]) or "unknown",
        **_review_meta(db, project_id, sku_code),
    }


def _result_row(db: Session, row: Any, object_type: str, object_code: str, value: Any, features: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "object_type": object_type,
        "object_code": object_code,
        "value": value,
        "source_basis": f"{object_type} runtime result",
        "raw_fields_or_text_examples": features,
        "derived_features": features,
        "mapping_lineage": {"object_code": object_code},
        "evidence_ids": row.evidence_ids,
        "confidence": row.confidence,
        "review_status": row.review_status,
        "asset_version": row.asset_version,
        "rule_version": row.rule_version,
        **_review_meta(db, row.project_id, row.sku_code),
    }


def _competitor_row(row: SkuCompetitorResult) -> dict[str, Any]:
    return {
        "target_sku_code": row.target_sku_code,
        "competitor_sku_code": row.competitor_sku_code,
        "battlefield_code": row.battlefield_code,
        "competitor_type": row.competitor_type,
        "rank": row.rank,
        "score": row.score,
        "component_scores": row.component_scores,
        "source_basis": "competitor runtime scoring over same category, price band, battlefield and core claims",
        "raw_fields_or_text_examples": row.evidence_card,
        "derived_features": row.component_scores,
        "mapping_lineage": {"battlefield_code": row.battlefield_code, "competitor_type": row.competitor_type},
        "evidence_ids": row.evidence_ids,
        "evidence_card": row.evidence_card,
        "confidence": row.confidence,
        "review_status": row.review_status,
        "asset_version": row.asset_version,
        "rule_version": row.rule_version,
        "last_reviewer": None,
        "review_timestamp": None,
        "insufficient_reasons": row.insufficient_reasons,
    }


def _project_or_raise(db: Session, project_id: str) -> CategoryProject:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    return project


def _library_key(library_type: str) -> str:
    key = LIBRARY_ALIASES.get(library_type, library_type)
    if key not in LIBRARY_MODELS:
        raise ValueError(f"未知资产库类型: {library_type}")
    return key


def _find_library_row(db: Session, project_id: str, asset_type: str, asset_id: str) -> tuple[Any, str]:
    key = _library_key(asset_type)
    model, id_attr, code_attr, _ = LIBRARY_MODELS[key]
    row = db.execute(
        select(model).where(
            model.project_id == project_id,
            (getattr(model, id_attr) == asset_id) | (getattr(model, code_attr) == asset_id),
        )
    ).scalar_one_or_none()
    if not row:
        raise ValueError("资产行不存在")
    return row, key


def _record_asset_operation(db: Session, project_id: str, asset_type: str, payload: dict[str, Any], *, operation: str) -> dict[str, Any]:
    actor_id = payload.get("actor_id", "api")
    asset_ids = payload.get("asset_ids") or ([payload["asset_id"]] if payload.get("asset_id") else [])
    updated = []
    for asset_id in asset_ids:
        row, key = _find_library_row(db, project_id, asset_type, str(asset_id))
        row.status = operation
        updated.append(getattr(row, LIBRARY_MODELS[key][2]))
    create_audit_event(
        db,
        action=f"asset_library_{operation}",
        object_type=f"asset_{_library_key(asset_type)}",
        object_id=",".join(updated) or project_id,
        project_id=project_id,
        actor_id=actor_id,
        after={"operation": operation, "asset_ids": asset_ids, "payload": payload},
    )
    db.commit()
    return {"status": operation, "updated": updated}


def _missing_field_rates(*row_groups: list[Any]) -> list[dict[str, Any]]:
    rates = []
    for rows in row_groups:
        if not rows:
            continue
        for column in rows[0].__table__.columns:
            if column.name in {"id", "created_at", "updated_at"}:
                continue
            missing = sum(1 for row in rows if _is_unknown(getattr(row, column.name)))
            if missing:
                rates.append({"table": rows[0].__tablename__, "field": column.name, "missing_rate": round(missing / len(rows), 4), "missing_count": missing})
    return sorted(rates, key=lambda item: item["missing_rate"], reverse=True)[:30]


def _is_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    return str(value).strip().lower() in {"", "unknown", "null", "none", "n/a", "na", "-", "--"}


def _duplicate_count(values: list[str | None]) -> int:
    counter = Counter(value for value in values if value)
    return sum(1 for value in counter.values() if value > 1)


def _unmapped_parameter_fields(db: Session, project_id: str, params: list[RawSkuParam]) -> list[dict[str, Any]]:
    defs = db.execute(select(StdParamDef).where(StdParamDef.project_id == project_id)).scalars().all()
    known = {item.param_code.lower() for item in defs} | {item.param_name.lower() for item in defs}
    for item in defs:
        known.update(str(alias).lower() for alias in item.raw_aliases or [])
    counter = Counter((row.raw_param_name or "unknown") for row in params if (row.raw_param_name or "unknown").lower() not in known)
    return [{"raw_param_name": name, "count": count, "status": "unmapped"} for name, count in counter.most_common(20)]


def _unmapped_claim_clusters(db: Session, project_id: str, claims: list[RawSkuClaim]) -> list[dict[str, Any]]:
    activated = {row.sku_code for row in db.execute(select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)).scalars() if row.sku_code}
    counter = Counter((row.claim_title or row.claim_text or "unknown")[:80] for row in claims if row.sku_code not in activated)
    return [{"cluster_text": text, "count": count, "status": "unmapped"} for text, count in counter.most_common(20)]


def _channels(params: list[RawSkuParam], claims: list[RawSkuClaim], comments: list[RawSkuComment], markets: list[RawMarketFact]) -> set[str]:
    return {
        value
        for value in [*(row.source_channel for row in params), *(row.source_channel for row in claims), *(row.platform for row in comments), *(row.channel_name or row.channel_group for row in markets)]
        if value
    }


def _time_values(masters: list[RawSkuMaster], params: list[RawSkuParam], claims: list[RawSkuClaim], comments: list[RawSkuComment], markets: list[RawMarketFact]) -> list[str]:
    return sorted(
        str(value)
        for value in [*(row.launch_date for row in masters), *(row.observed_at for row in params), *(row.observed_at for row in claims), *(row.comment_time for row in comments), *(row.period for row in markets)]
        if value
    )


def _latest_source(db: Session, project_id: str) -> dict[str, str | None]:
    source = db.execute(select(SourceFile).where(SourceFile.project_id == project_id).order_by(SourceFile.created_at.desc())).scalars().first()
    batch = db.execute(select(ImportBatch).where(ImportBatch.project_id == project_id).order_by(ImportBatch.created_at.desc())).scalars().first()
    return {"source_dataset_id": source.source_file_id if source else None, "source_batch_id": batch.import_batch_id if batch else None}


def _param_coverage(db: Session, project_id: str, param_code: str) -> tuple[float, float]:
    rows = db.execute(select(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id, SkuParamNormalized.param_code == param_code)).scalars().all()
    sku_count = _sku_count(db, project_id)
    unknown = len([row for row in rows if row.normalized_value == "unknown"])
    return round(len(rows) / max(1, sku_count), 4), round(unknown / max(1, len(rows)), 4)


def _claim_coverage(db: Session, project_id: str, claim_code: str) -> float:
    count = db.execute(select(func.count()).select_from(SkuClaimResult).where(SkuClaimResult.project_id == project_id, SkuClaimResult.claim_code == claim_code)).scalar_one()
    return round(count / max(1, _sku_count(db, project_id)), 4)


def _topic_stats(db: Session, project_id: str, topic_code: str) -> dict[str, Any]:
    rows = db.execute(select(SkuCommentTopicResult).where(SkuCommentTopicResult.project_id == project_id, SkuCommentTopicResult.topic_code == topic_code)).scalars().all()
    positive = len([row for row in rows if row.sentiment == "positive"])
    negative = len([row for row in rows if row.sentiment == "negative"])
    total = max(1, len(rows))
    return {"mention_rate": round(len(rows) / max(1, _sku_count(db, project_id)), 4), "positive_rate": round(positive / total, 4), "negative_rate": round(negative / total, 4)}


def _asset_evidence_ids(db: Session, project_id: str, source_type: str | None, tokens: list[Any]) -> list[str]:
    token_text = [str(item).lower() for item in tokens if item not in {None, ""}]
    query = select(EvidenceItem).where(EvidenceItem.project_id == project_id)
    if source_type:
        query = query.where(EvidenceItem.source_type == source_type)
    rows = db.execute(query.order_by(EvidenceItem.created_at.desc())).scalars().all()
    ids = []
    for row in rows:
        haystack = " ".join(str(value or "").lower() for value in [row.field_name, row.raw_value, row.normalized_value])
        if not token_text or any(token in haystack for token in token_text):
            ids.append(row.evidence_id)
        if len(ids) >= 8:
            break
    return _unique(ids)


def _param_examples(db: Session, project_id: str, param_code: str, aliases: list[str] | None) -> dict[str, list[str]]:
    tokens = {param_code.lower(), *(str(alias).lower() for alias in aliases or [])}
    rows = db.execute(select(RawSkuParam).where(RawSkuParam.project_id == project_id)).scalars().all()
    matched = [row for row in rows if (row.raw_param_name or "").lower() in tokens or param_code.lower() in (row.raw_param_name or "").lower()]
    return {"fields": _unique([row.raw_param_name or "unknown" for row in matched])[:6], "values": _unique([row.raw_param_value or "unknown" for row in matched])[:6]}


def _claim_examples(db: Session, project_id: str, keywords: list[str] | None) -> list[str]:
    lowered = [keyword.lower() for keyword in keywords or []]
    rows = db.execute(select(RawSkuClaim).where(RawSkuClaim.project_id == project_id)).scalars().all()
    examples = []
    for row in rows:
        text = " ".join(part for part in [row.claim_title, row.claim_text] if part)
        if not lowered or any(keyword in text.lower() for keyword in lowered):
            examples.append(text)
    return _unique(examples)[:6]


def _topic_examples(db: Session, project_id: str, topic_code: str, keywords: list[str] | None) -> list[str]:
    evidence = db.execute(select(EvidenceItem).where(EvidenceItem.project_id == project_id, EvidenceItem.source_type == "comment")).scalars().all()
    examples = [row.raw_value for row in evidence if row.field_name == topic_code and row.raw_value]
    if examples:
        return _unique(examples)[:6]
    lowered = [keyword.lower() for keyword in keywords or []]
    comments = db.execute(select(RawSkuComment).where(RawSkuComment.project_id == project_id)).scalars().all()
    return _unique([row.comment_text for row in comments if row.comment_text and any(keyword in row.comment_text.lower() for keyword in lowered)])[:6]


def _example_skus_for_task(db: Session, project_id: str, task_code: str) -> list[str]:
    rows = db.execute(select(SkuTaskScore).where(SkuTaskScore.project_id == project_id, SkuTaskScore.task_code == task_code).order_by(SkuTaskScore.score.desc())).scalars().all()
    return [row.sku_code for row in rows[:6]]


def _example_skus_for_battlefield(db: Session, project_id: str, battlefield_code: str) -> list[str]:
    rows = db.execute(select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id, SkuBattlefieldScore.battlefield_code == battlefield_code).order_by(SkuBattlefieldScore.score.desc())).scalars().all()
    return [row.sku_code for row in rows[:6]]


def _example_skus_for_target_group(db: Session, project_id: str, target_group_code: str) -> list[str]:
    task_codes = _source_tasks_for_target_group(db, project_id, target_group_code)
    rows = db.execute(select(SkuTaskScore).where(SkuTaskScore.project_id == project_id, SkuTaskScore.task_code.in_(task_codes)).order_by(SkuTaskScore.score.desc())).scalars().all() if task_codes else []
    return _unique([row.sku_code for row in rows])[:6]


def _source_tasks_for_target_group(db: Session, project_id: str, target_group_code: str) -> list[str]:
    rows = db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars().all()
    return [row.task_code for row in rows if target_group_code in (row.default_target_group_codes or [])]


def _core_tasks_for_battlefield(db: Session, project_id: str, battlefield_code: str) -> list[str]:
    rows = db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars().all()
    return [row.task_code for row in rows if battlefield_code in (row.battlefield_codes or [])]


def _core_claims_for_battlefield(db: Session, project_id: str, battlefield_code: str) -> list[str]:
    rows = db.execute(select(StdClaimDef).where(StdClaimDef.project_id == project_id)).scalars().all()
    return [row.claim_code for row in rows if battlefield_code in (row.mapped_battlefield_codes or [])]


def _core_params_for_battlefield(db: Session, project_id: str, battlefield_code: str) -> list[str]:
    claim_codes = set(_core_claims_for_battlefield(db, project_id, battlefield_code))
    rows = db.execute(select(StdParamDef).where(StdParamDef.project_id == project_id)).scalars().all()
    return [row.param_code for row in rows if claim_codes.intersection(row.mapped_claim_codes or [])]


def _target_groups_for_battlefield(db: Session, project_id: str, battlefield_code: str) -> list[str]:
    task_codes = set(_core_tasks_for_battlefield(db, project_id, battlefield_code))
    rows = db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars().all()
    return _unique([target for row in rows if row.task_code in task_codes for target in (row.default_target_group_codes or [])])


def _target_group_scores(db: Session, project_id: str, task_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks = {row.task_code: row for row in db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars()}
    output: dict[str, dict[str, Any]] = {}
    for score in task_scores:
        task = tasks.get(score["task_code"])
        if not task:
            continue
        for target_code in task.default_target_group_codes or []:
            current = output.get(target_code, {"target_group_code": target_code, "score": 0.0, "source_task_codes": [], "evidence_ids": []})
            current["score"] = max(current["score"], float(score.get("score") or 0.0))
            current["source_task_codes"] = _unique([*current["source_task_codes"], task.task_code])
            current["evidence_ids"] = _unique([*current["evidence_ids"], *(score.get("evidence_ids") or [])])
            output[target_code] = current
    return list(output.values())


def _sku_claim_value_layers(db: Session, project_id: str, sku_code: str) -> list[dict[str, Any]]:
    claims = db.execute(select(SkuClaimResult).where(SkuClaimResult.project_id == project_id, SkuClaimResult.sku_code == sku_code)).scalars().all()
    metrics = {row.claim_code: row for row in db.execute(select(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == project_id)).scalars()}
    return [{"claim_code": row.claim_code, "layer": metrics[row.claim_code].layer if row.claim_code in metrics else "unknown", "coverage_rate": metrics[row.claim_code].coverage_rate if row.claim_code in metrics else None, "psi": metrics[row.claim_code].psi if row.claim_code in metrics else None, "ssi": metrics[row.claim_code].ssi if row.claim_code in metrics else None, "cpi": metrics[row.claim_code].cpi if row.claim_code in metrics else None, "evidence_ids": row.evidence_ids} for row in claims]


def _review_flags(db: Session, project_id: str, sku_code: str) -> list[dict[str, Any]]:
    rows = db.execute(select(ReviewQueue).where(ReviewQueue.project_id == project_id, ReviewQueue.item_key.like(f"{sku_code}%"))).scalars().all()
    return [_serialize(row) for row in rows]


def _evidence_cards(db: Session, project_id: str, evidence_ids: list[str]) -> list[dict[str, Any]]:
    if not evidence_ids:
        return []
    rows = db.execute(select(EvidenceItem).where(EvidenceItem.project_id == project_id, EvidenceItem.evidence_id.in_(evidence_ids))).scalars().all()
    return [_serialize(row) for row in rows]


def _review_meta(db: Session, project_id: str, item_key_hint: str) -> dict[str, Any]:
    review = db.execute(select(ReviewQueue).where(ReviewQueue.project_id == project_id, ReviewQueue.item_key.like(f"%{item_key_hint}%")).order_by(ReviewQueue.updated_at.desc())).scalars().first()
    return {"last_reviewer": review.reviewer if review else None, "review_timestamp": review.updated_at.isoformat() if review and review.updated_at else None}


def _review_status_summary(db: Session, project_id: str) -> dict[str, int]:
    rows = db.execute(select(ReviewQueue).where(ReviewQueue.project_id == project_id)).scalars().all()
    return dict(Counter(row.status for row in rows))


def _release_recommendation(review_summary: dict[str, int], claim_metrics: list[ClaimValueLayerResult]) -> str:
    if review_summary.get("pending", 0) > 0:
        return "hold_for_internal_review"
    if not claim_metrics:
        return "hold_for_missing_market_metrics"
    if any(row.confidence < 0.5 for row in claim_metrics):
        return "hold_for_low_confidence_metrics"
    return "ready_for_release_gate"


def _deliverable_for_file(file_name: str) -> str:
    if file_name in {"std_param_def.csv", "std_claim_def.csv", "comment_topic_def.csv", "user_task_def.csv", "target_group_def.csv", "battlefield_def.csv", "mapping_rules.csv"}:
        return "TV category semantic asset pack"
    if file_name == "sku_analysis_results.csv":
        return "TV SKU analysis result pack"
    if file_name == "quality_report.json":
        return "TV market calibration report"
    if file_name == "scoring_rules.yaml":
        return "runtime scoring rules"
    if file_name == "competitor_runtime_rules.yaml":
        return "competitor runtime rules"
    if file_name == "evidence_cards.jsonl":
        return "evidence cards"
    return "release manifest"


def _raw_sku_fields(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    master = db.execute(select(RawSkuMaster).where(RawSkuMaster.project_id == project_id, RawSkuMaster.sku_code == sku_code)).scalars().first()
    market = db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id, RawMarketFact.sku_code == sku_code)).scalars().first()
    return {"master": _serialize(master) if master else None, "market": _serialize(market) if market else None}


def _raw_text_examples(db: Session, project_id: str, sku_code: str) -> dict[str, list[str]]:
    claims = db.execute(select(RawSkuClaim).where(RawSkuClaim.project_id == project_id, RawSkuClaim.sku_code == sku_code)).scalars().all()
    comments = db.execute(select(RawSkuComment).where(RawSkuComment.project_id == project_id, RawSkuComment.sku_code == sku_code)).scalars().all()
    return {"claim_text": [row.claim_text for row in claims if row.claim_text], "comments_text": [row.comment_text for row in comments if row.comment_text]}


def _sku_report_preview(summary: dict[str, Any], analysis: dict[str, Any], value_layers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": f"{summary['sku_code']} 内部 QA 报告预览",
        "summary": {
            "brand": summary["brand"],
            "model": summary["model"],
            "price_band": summary["price_band"],
            "top_claims": [row["claim_code"] for row in analysis["claim_results"][:5]],
            "top_tasks": [row["task_code"] for row in analysis["task_scores"][:5]],
            "battlefields": [row["battlefield_code"] for row in analysis["battlefield_scores"][:5]],
            "claim_value_layers": value_layers[:5],
        },
    }


def _price_band(avg_price: float | None) -> str:
    if avg_price is None:
        return "unknown"
    if avg_price >= 12000:
        return "premium"
    if avg_price >= 8000:
        return "upper_mid"
    if avg_price >= 5000:
        return "mainstream"
    return "entry"


def _price_signals(db: Session, project_id: str) -> dict[str, int]:
    rows = db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id)).scalars().all()
    return dict(Counter(_price_band(row.avg_price) for row in rows))


def _channel_signals(db: Session, project_id: str) -> dict[str, int]:
    rows = db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id)).scalars().all()
    return dict(Counter(row.channel_name or row.channel_group or "unknown" for row in rows))


def _top_codes(rows: list[Any], code_attr: str, score_attr: str, limit: int = 5) -> list[str]:
    return [getattr(row, code_attr) for row in sorted(rows, key=lambda item: getattr(item, score_attr, 0), reverse=True)[:limit]]


def _sku_count(db: Session, project_id: str) -> int:
    return int(db.execute(select(func.count(func.distinct(RawSkuMaster.sku_code))).where(RawSkuMaster.project_id == project_id)).scalar_one() or 0)


def _library_label(key: str) -> str:
    return {
        "parameters": "标准参数库",
        "claims": "标准卖点库",
        "comment_topics": "评论主题库",
        "tasks": "用户任务库",
        "target_groups": "目标人群库",
        "battlefields": "价值战场库",
    }[key]


def _serialize(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    data: dict[str, Any] = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        data[column.name] = value
    return data


def _unique(values: list[Any]) -> list[Any]:
    output: list[Any] = []
    for value in values:
        if value not in {None, ""} and value not in output:
            output.append(value)
    return output


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _combined_review_status(values: list[str]) -> str:
    if not values:
        return "unknown"
    if any(value in {"rejected"} for value in values):
        return "rejected"
    if any(value in {"needs_review", "pending"} for value in values):
        return "needs_review"
    if all(value in {"approved", "auto_pass"} for value in values):
        return "approved"
    return values[0]


def _first(values: list[Any]) -> Any:
    return next((value for value in values if value), None)
