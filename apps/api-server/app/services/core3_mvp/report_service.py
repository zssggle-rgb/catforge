from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Core3CompetitorCandidate,
    Core3CompetitorResult,
    Core3EvidenceCard,
    Core3PipelineRun,
    Core3SkuFeatureProfile,
    Core3SkuMarketProfile,
    EvidenceItem,
    new_id,
    now_utc,
)
from app.schemas.core3_mvp import Core3RunRequest
from app.services.core3_mvp.data_access import (
    Core3InputBundle,
    is_unknown,
    load_project_input,
    resolve_sku_code,
)

CORE3_RULE_VERSION = "core3-mvp-0.1.0"
CREATED_ONLY_WARNING = "Core3 Goal B 仅创建运行上下文，市场画像和竞品计算将在后续 Goal 实现"
EMPTY_WARNING = "项目没有可用 SKU 主数据，Core3 运行已完成为空结果"
CORE3_ROLE_ORDER = ["direct", "pressure", "benchmark_potential"]
CORE3_CSV_FIELDS = [
    "target_sku_code",
    "role",
    "competitor_sku_code",
    "score",
    "reason",
    "confidence",
    "confidence_level",
    "review_flag",
    "insufficient_reasons",
]


class Core3RunNotFound(ValueError):
    pass


class Core3ReportNotFound(ValueError):
    pass


def create_or_reuse_run(
    db: Session,
    project_id: str,
    request: Core3RunRequest,
) -> Core3PipelineRun:
    bundle = load_project_input(db, project_id)
    scope, target_sku_code, target_sku_codes = _resolve_targets(db, bundle, request)
    base_fingerprint = input_fingerprint(bundle, scope=scope, target_sku_codes=target_sku_codes)
    if not request.force_recompute:
        existing = _find_existing_run(
            db,
            project_id=project_id,
            scope=scope,
            target_sku_code=target_sku_code,
            input_fingerprint=base_fingerprint,
        )
        if existing:
            return existing

    run_fingerprint = base_fingerprint
    if request.force_recompute:
        run_fingerprint = input_fingerprint(
            bundle,
            scope=scope,
            target_sku_codes=target_sku_codes,
            force_recompute_nonce=new_id(),
        )

    now = now_utc()
    status = "created" if target_sku_codes else "completed_empty"
    run = Core3PipelineRun(
        project_id=project_id,
        category_code=bundle.project.category_code,
        status=status,
        scope=scope,
        target_sku_code=target_sku_code,
        input_fingerprint=run_fingerprint,
        rule_version=CORE3_RULE_VERSION,
        counts=_counts(bundle, target_sku_codes),
        warnings=[CREATED_ONLY_WARNING] if status == "created" else [EMPTY_WARNING],
        diagnostics={
            "target_sku_codes": target_sku_codes,
            "base_input_fingerprint": base_fingerprint,
            "created_only": status == "created",
            "force_recompute": request.force_recompute,
        },
        started_at=now if status == "completed_empty" else None,
        finished_at=now if status == "completed_empty" else None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_run(
    db: Session,
    run_id: str,
    *,
    status: str = "completed",
    counts: dict[str, int | float] | None = None,
    warnings: list[str] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> Core3PipelineRun:
    if status not in {"completed", "completed_empty"}:
        raise ValueError("finish_run status 必须是 completed 或 completed_empty")
    run = db.get(Core3PipelineRun, run_id)
    if not run:
        raise Core3RunNotFound("Core3 run 不存在")
    now = now_utc()
    run.status = status
    run.started_at = run.started_at or now
    run.finished_at = now
    if counts is not None:
        run.counts = counts
    if warnings is not None:
        run.warnings = warnings
    if diagnostics is not None:
        run.diagnostics = {**(run.diagnostics or {}), **diagnostics}
    db.commit()
    db.refresh(run)
    return run


def fail_run(
    db: Session,
    run_id: str,
    error_message: str,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> Core3PipelineRun:
    run = db.get(Core3PipelineRun, run_id)
    if not run:
        raise Core3RunNotFound("Core3 run 不存在")
    run.status = "failed"
    run.started_at = run.started_at or now_utc()
    run.finished_at = now_utc()
    run.warnings = [*(run.warnings or []), error_message]
    run.diagnostics = {**(run.diagnostics or {}), "error_message": error_message, **(diagnostics or {})}
    db.commit()
    db.refresh(run)
    return run


def input_fingerprint(
    bundle: Core3InputBundle,
    *,
    scope: str,
    target_sku_codes: list[str],
    force_recompute_nonce: str | None = None,
) -> str:
    payload = {
        "project": {
            "project_id": bundle.project.project_id,
            "category_code": bundle.project.category_code,
            "version": bundle.project.version,
        },
        "scope": scope,
        "target_sku_codes": target_sku_codes,
        "force_recompute_nonce": force_recompute_nonce,
        "sku_master": _rows_payload(
            bundle.sku_master,
            ["sku_code", "brand", "model_name", "series", "category_name", "launch_date", "product_url"],
        ),
        "market_facts": _rows_payload(
            bundle.market_facts,
            [
                "sku_code",
                "period",
                "period_type",
                "channel_group",
                "channel_type",
                "channel_name",
                "sales_volume",
                "sales_amount",
                "avg_price",
                "promotion_flag",
            ],
        ),
        "params": _rows_payload(
            bundle.params,
            ["sku_code", "raw_param_name", "raw_param_value", "raw_unit", "source_channel", "observed_at"],
        ),
        "claims": _rows_payload(
            bundle.claims,
            ["sku_code", "claim_title", "claim_text", "claim_order", "source_channel", "observed_at"],
        ),
        "comments": _rows_payload(
            bundle.comments,
            [
                "sku_code",
                "platform",
                "comment_id",
                "comment_text",
                "rating",
                "comment_time",
                "dimension_1",
                "dimension_2",
                "dimension_3",
            ],
        ),
    }
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def run_to_dict(run: Core3PipelineRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "status": run.status,
        "scope": run.scope,
        "target_sku_code": run.target_sku_code,
        "counts": run.counts or {},
        "warnings": run.warnings or [],
        "diagnostics": run.diagnostics or {},
        "latest_report_ref": None,
    }


def get_sku_report(db: Session, project_id: str, sku_or_model: str) -> dict[str, Any]:
    resolved = resolve_sku_code(db, project_id, sku_or_model)
    sku_code = resolved["sku_code"]
    run = _latest_completed_run(db, project_id)
    if not run:
        raise Core3ReportNotFound("Core3 report 尚未生成")
    feature = db.execute(
        select(Core3SkuFeatureProfile).where(
            Core3SkuFeatureProfile.run_id == run.run_id,
            Core3SkuFeatureProfile.project_id == project_id,
            Core3SkuFeatureProfile.sku_code == sku_code,
        )
    ).scalar_one_or_none()
    market = db.execute(
        select(Core3SkuMarketProfile).where(
            Core3SkuMarketProfile.run_id == run.run_id,
            Core3SkuMarketProfile.project_id == project_id,
            Core3SkuMarketProfile.sku_code == sku_code,
        )
    ).scalar_one_or_none()
    if not feature or not market:
        raise Core3ReportNotFound("Core3 report 尚未包含该 SKU")
    competitor_results = _competitor_results(db, run.run_id, project_id, sku_code)
    insufficient_reasons = _unique_strings(
        [
            *(feature.missing_signals or []),
            *(market.missing_signals or []),
            *[
                reason
                for row in competitor_results
                for reason in (row.insufficient_reasons or [])
            ],
        ]
    )
    report_confidences = [feature.confidence or 0.0, market.confidence or 0.0]
    non_empty_competitors = [row.confidence for row in competitor_results if row.competitor_sku_code]
    if competitor_results:
        report_confidences.append(min(non_empty_competitors) if non_empty_competitors else 0.0)
    confidence = min(report_confidences)
    return {
        "project_id": project_id,
        "run_id": run.run_id,
        "target_sku": {
            "sku_code": sku_code,
            "brand": resolved.get("brand"),
            "model_name": resolved.get("model_name"),
            "series": resolved.get("series"),
        },
        "derivation_summary": _derivation_summary(db, run, project_id, sku_code, feature, competitor_results),
        "market_profile": _market_to_dict(market),
        "standard_params": feature.standard_params or {},
        "activated_claims": feature.claim_activations or [],
        "comment_topics": feature.comment_topics or [],
        "tasks": feature.task_scores or [],
        "target_groups": feature.target_group_scores or [],
        "battlefields": feature.battlefield_scores or [],
        "core_competitors": [_competitor_to_dict(row) for row in competitor_results],
        "extraction_diagnostics": feature.extraction_diagnostics or {},
        "confidence_level": _confidence_level(confidence),
        "review_flag": confidence < 0.55 or bool(insufficient_reasons) or any(row.review_flag for row in competitor_results),
        "insufficient_reasons": insufficient_reasons,
    }


def _derivation_summary(
    db: Session,
    run: Core3PipelineRun,
    project_id: str,
    sku_code: str,
    feature: Core3SkuFeatureProfile,
    competitor_results: list[Core3CompetitorResult],
) -> dict[str, Any]:
    candidate_rows = list(
        db.execute(
            select(Core3CompetitorCandidate).where(
                Core3CompetitorCandidate.run_id == run.run_id,
                Core3CompetitorCandidate.project_id == project_id,
                Core3CompetitorCandidate.target_sku_code == sku_code,
            )
        ).scalars()
    )
    selected = [row for row in competitor_results if row.competitor_sku_code]
    return {
        "run_counts": run.counts or {},
        "target_feature_counts": {
            "standard_param_count": len(feature.standard_params or {}),
            "activated_claim_count": len(feature.claim_activations or []),
            "comment_topic_count": len(feature.comment_topics or []),
            "task_count": len(feature.task_scores or []),
            "target_group_count": len(feature.target_group_scores or []),
            "battlefield_count": len(feature.battlefield_scores or []),
        },
        "candidate_pool": {
            "total": len(candidate_rows),
            "eligible": sum(1 for row in candidate_rows if row.gate_status == "eligible"),
            "insufficient": sum(1 for row in candidate_rows if row.gate_status == "insufficient"),
            "selected": len(selected),
            "hard_filters": [
                "同品类",
                "排除目标自身",
                "候选有主数据身份",
                "价格在可比窗口内",
                "尺寸差不超过业务阈值",
                "存在任务或战场交集",
                "价格或销量证据可观察",
            ],
        },
        "selection_policy": {
            "role_order": CORE3_ROLE_ORDER,
            "dedupe_rules": ["同一 SKU 不重复入选", "同系列优先保留高分型号", "品牌过度集中时优先分散"],
            "no_force_fill": True,
        },
    }


def get_competitor_evidence_cards(db: Session, project_id: str, sku_or_model: str) -> dict[str, Any]:
    resolved = resolve_sku_code(db, project_id, sku_or_model)
    sku_code = resolved["sku_code"]
    run = _latest_completed_run(db, project_id)
    if not run:
        raise Core3ReportNotFound("Core3 report 尚未生成")
    cards = list(
        db.execute(
            select(Core3EvidenceCard).where(
                Core3EvidenceCard.run_id == run.run_id,
                Core3EvidenceCard.project_id == project_id,
                Core3EvidenceCard.target_sku_code == sku_code,
            )
        ).scalars()
    )
    if not cards:
        raise Core3ReportNotFound("Core3 report 尚未包含该 SKU 证据卡")
    cards.sort(key=lambda row: CORE3_ROLE_ORDER.index(row.role) if row.role in CORE3_ROLE_ORDER else 99)
    evidence_by_id = _evidence_items_by_id(db, project_id, _unique_strings([e for card in cards for e in (card.evidence_ids or [])]))
    return {
        "project_id": project_id,
        "run_id": run.run_id,
        "target_sku_code": sku_code,
        "count": len(cards),
        "items": [
            {
                "role": card.role,
                "competitor_sku_code": card.competitor_sku_code,
                "evidence_categories": card.evidence_categories or [],
                "evidence_card": card.card_json or {},
                "evidence_items": [
                    evidence_by_id[evidence_id]
                    for evidence_id in (card.evidence_ids or [])
                    if evidence_id in evidence_by_id
                ],
            }
            for card in cards
        ],
    }


def get_overview(db: Session, project_id: str) -> dict[str, Any]:
    run = _latest_completed_run(db, project_id)
    if not run:
        raise Core3ReportNotFound("Core3 overview 尚未生成")
    feature_rows = list(
        db.execute(
            select(Core3SkuFeatureProfile).where(
                Core3SkuFeatureProfile.run_id == run.run_id,
                Core3SkuFeatureProfile.project_id == project_id,
            )
        ).scalars()
    )
    market_by_sku = {
        row.sku_code: row
        for row in db.execute(
            select(Core3SkuMarketProfile).where(
                Core3SkuMarketProfile.run_id == run.run_id,
                Core3SkuMarketProfile.project_id == project_id,
            )
        ).scalars()
    }
    results_by_sku: dict[str, list[Core3CompetitorResult]] = {}
    for row in db.execute(
        select(Core3CompetitorResult).where(
            Core3CompetitorResult.run_id == run.run_id,
            Core3CompetitorResult.project_id == project_id,
        )
    ).scalars():
        results_by_sku.setdefault(row.target_sku_code, []).append(row)

    rows = []
    confidence_distribution = {"high": 0, "medium": 0, "low": 0}
    insufficient_counter: dict[str, int] = {}
    for feature in sorted(feature_rows, key=lambda row: row.sku_code):
        market = market_by_sku.get(feature.sku_code)
        results = sorted(
            results_by_sku.get(feature.sku_code, []),
            key=lambda row: CORE3_ROLE_ORDER.index(row.role) if row.role in CORE3_ROLE_ORDER else 99,
        )
        row_confidence = _overview_confidence_level(feature, market, results)
        confidence_distribution[row_confidence] += 1
        insufficient_reasons = _unique_strings(
            [
                *(feature.missing_signals or []),
                *((market.missing_signals or []) if market else []),
                *[reason for result in results for reason in (result.insufficient_reasons or [])],
            ]
        )
        for reason in insufficient_reasons:
            insufficient_counter[reason] = insufficient_counter.get(reason, 0) + 1
        row_by_role = {result.role: result for result in results}
        rows.append(
            {
                "target_sku_code": feature.sku_code,
                "brand": market.brand if market else None,
                "model_name": market.model_name if market else None,
                "primary_battlefield": _primary_battlefield(feature),
                "direct_competitor": _competitor_brief(row_by_role.get("direct")),
                "pressure_competitor": _competitor_brief(row_by_role.get("pressure")),
                "benchmark_potential_competitor": _competitor_brief(row_by_role.get("benchmark_potential")),
                "confidence_level": row_confidence,
                "review_flag": any(result.review_flag for result in results) or bool(insufficient_reasons),
                "insufficient_reasons": insufficient_reasons,
            }
        )

    return {
        "project_id": project_id,
        "latest_run_id": run.run_id,
        "analyzed_sku_count": len(rows),
        "confidence_distribution": confidence_distribution,
        "insufficient_reason_top5": [
            {"reason": reason, "count": count}
            for reason, count in sorted(insufficient_counter.items(), key=lambda item: (-item[1], item[0]))[:5]
        ],
        "rows": rows,
    }


def export_core3_csv(db: Session, project_id: str) -> str:
    run = _latest_completed_run(db, project_id)
    if not run:
        raise Core3ReportNotFound("Core3 export 尚未生成")
    rows = _all_competitor_results(db, run.run_id, project_id)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CORE3_CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "target_sku_code": row.target_sku_code,
                "role": row.role,
                "competitor_sku_code": row.competitor_sku_code or "",
                "score": row.score,
                "reason": row.reason or "",
                "confidence": row.confidence,
                "confidence_level": row.confidence_level,
                "review_flag": row.review_flag,
                "insufficient_reasons": "|".join(row.insufficient_reasons or []),
            }
        )
    return buffer.getvalue()


def export_evidence_cards_jsonl(db: Session, project_id: str) -> str:
    run = _latest_completed_run(db, project_id)
    if not run:
        raise Core3ReportNotFound("Core3 evidence card export 尚未生成")
    cards = list(
        db.execute(
            select(Core3EvidenceCard).where(
                Core3EvidenceCard.run_id == run.run_id,
                Core3EvidenceCard.project_id == project_id,
            )
        ).scalars()
    )
    cards.sort(
        key=lambda row: (
            row.target_sku_code,
            CORE3_ROLE_ORDER.index(row.role) if row.role in CORE3_ROLE_ORDER else 99,
        )
    )
    return "".join(
        json.dumps(
            {
                "target_sku_code": card.target_sku_code,
                "role": card.role,
                "competitor_sku_code": card.competitor_sku_code,
                "evidence_card": card.card_json or {},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for card in cards
    )


def _resolve_targets(
    db: Session,
    bundle: Core3InputBundle,
    request: Core3RunRequest,
) -> tuple[str, str | None, list[str]]:
    if request.batch:
        return "batch", None, _valid_sku_codes(bundle)

    query = request.target_sku_code if not is_unknown(request.target_sku_code) else request.target_model
    if is_unknown(query):
        raise ValueError("batch=false 时必须提供有效的 target_sku_code 或 target_model")
    resolved = resolve_sku_code(db, bundle.project.project_id, str(query))
    target_sku_code = resolved["sku_code"]
    return "single_sku", target_sku_code, [target_sku_code]


def _latest_completed_run(db: Session, project_id: str) -> Core3PipelineRun | None:
    return db.execute(
        select(Core3PipelineRun)
        .where(
            Core3PipelineRun.project_id == project_id,
            Core3PipelineRun.status == "completed",
        )
        .order_by(Core3PipelineRun.updated_at.desc())
    ).scalars().first()


def _market_to_dict(row: Core3SkuMarketProfile) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand": row.brand,
        "model_name": row.model_name,
        "series": row.series,
        "price_wavg_12m": row.price_wavg_12m,
        "price_latest": row.price_latest,
        "sales_volume_12m": row.sales_volume_12m,
        "sales_amount_12m": row.sales_amount_12m,
        "channel_share": row.channel_share or {},
        "price_drop_rate_3m": row.price_drop_rate_3m,
        "sales_growth_3m": row.sales_growth_3m,
        "price_percentile": row.price_percentile,
        "sales_percentile": row.sales_percentile,
        "sales_amount_percentile": row.sales_amount_percentile,
        "evidence_ids": row.evidence_ids or [],
        "missing_signals": row.missing_signals or [],
        "confidence": row.confidence,
    }


def _competitor_results(
    db: Session,
    run_id: str,
    project_id: str,
    sku_code: str,
) -> list[Core3CompetitorResult]:
    rows = list(
        db.execute(
            select(Core3CompetitorResult).where(
                Core3CompetitorResult.run_id == run_id,
                Core3CompetitorResult.project_id == project_id,
                Core3CompetitorResult.target_sku_code == sku_code,
            )
        ).scalars()
    )
    rows.sort(key=lambda row: CORE3_ROLE_ORDER.index(row.role) if row.role in CORE3_ROLE_ORDER else 99)
    return rows


def _all_competitor_results(db: Session, run_id: str, project_id: str) -> list[Core3CompetitorResult]:
    rows = list(
        db.execute(
            select(Core3CompetitorResult).where(
                Core3CompetitorResult.run_id == run_id,
                Core3CompetitorResult.project_id == project_id,
            )
        ).scalars()
    )
    rows.sort(
        key=lambda row: (
            row.target_sku_code,
            CORE3_ROLE_ORDER.index(row.role) if row.role in CORE3_ROLE_ORDER else 99,
        )
    )
    return rows


def _overview_confidence_level(
    feature: Core3SkuFeatureProfile,
    market: Core3SkuMarketProfile | None,
    results: list[Core3CompetitorResult],
) -> str:
    confidences = [feature.confidence or 0.0]
    if market:
        confidences.append(market.confidence or 0.0)
    non_empty = [row.confidence for row in results if row.competitor_sku_code]
    if non_empty:
        confidences.append(min(non_empty))
    if any(row.review_flag for row in results):
        confidences.append(0.54)
    return _confidence_level(min(confidences or [0.0]))


def _primary_battlefield(feature: Core3SkuFeatureProfile) -> str | None:
    rows = feature.battlefield_scores or []
    if not rows:
        return None
    first = sorted(rows, key=lambda item: (-(item.get("final_score") or item.get("score") or 0), item.get("battlefield_code") or ""))[0]
    return first.get("battlefield_code")


def _competitor_brief(row: Core3CompetitorResult | None) -> dict[str, Any] | None:
    if not row:
        return None
    card = row.evidence_card or {}
    competitor = card.get("competitor") or {}
    return {
        "sku_code": row.competitor_sku_code,
        "brand": competitor.get("brand"),
        "model_name": competitor.get("model_name"),
        "score": row.score,
        "confidence_level": row.confidence_level,
        "insufficient_reasons": row.insufficient_reasons or [],
    }


def _competitor_to_dict(row: Core3CompetitorResult) -> dict[str, Any]:
    card = row.evidence_card or {}
    competitor = card.get("competitor") or {}
    return {
        "role": row.role,
        "role_name": _role_name(row.role),
        "competitor_sku_code": row.competitor_sku_code,
        "competitor_brand": competitor.get("brand"),
        "competitor_model_name": competitor.get("model_name"),
        "competitor_series": competitor.get("series"),
        "battlefield_code": row.battlefield_code,
        "score": row.score,
        "component_scores": row.component_scores or {},
        "reason": row.reason,
        "confidence": row.confidence,
        "confidence_level": row.confidence_level,
        "review_flag": row.review_flag,
        "insufficient_reasons": row.insufficient_reasons or [],
        "evidence_ids": row.evidence_ids or [],
        "evidence_categories": card.get("evidence_categories", []),
        "evidence_card": card,
    }


def _role_name(role: str) -> str:
    return {
        "direct": "正面对打竞品",
        "pressure": "价格/销量挤压竞品",
        "benchmark_potential": "高端标杆/潜在下探竞品",
    }.get(role, role)


def _evidence_items_by_id(db: Session, project_id: str, evidence_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not evidence_ids:
        return {}
    rows = list(
        db.execute(
            select(EvidenceItem).where(
                EvidenceItem.project_id == project_id,
                EvidenceItem.evidence_id.in_(evidence_ids),
            )
        ).scalars()
    )
    return {row.evidence_id: _evidence_item_to_dict(row) for row in rows}


def _evidence_item_to_dict(row: EvidenceItem) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "source_type": row.source_type,
        "source_file_id": row.source_file_id,
        "raw_row_id": row.raw_row_id,
        "sku_code": row.sku_code,
        "field_name": row.field_name,
        "raw_value": row.raw_value,
        "normalized_value": row.normalized_value,
        "source_ref": row.source_ref,
        "confidence": row.confidence,
    }


def _confidence_level(confidence: float) -> str:
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.55:
        return "medium"
    return "low"


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _valid_sku_codes(bundle: Core3InputBundle) -> list[str]:
    return sorted({str(row.sku_code).strip() for row in bundle.sku_master if not is_unknown(row.sku_code)})


def _find_existing_run(
    db: Session,
    *,
    project_id: str,
    scope: str,
    target_sku_code: str | None,
    input_fingerprint: str,
) -> Core3PipelineRun | None:
    conditions = [
        Core3PipelineRun.project_id == project_id,
        Core3PipelineRun.scope == scope,
        Core3PipelineRun.input_fingerprint == input_fingerprint,
    ]
    if target_sku_code is None:
        conditions.append(Core3PipelineRun.target_sku_code.is_(None))
    else:
        conditions.append(Core3PipelineRun.target_sku_code == target_sku_code)
    rows = db.execute(
        select(Core3PipelineRun).where(*conditions).order_by(Core3PipelineRun.updated_at.desc())
    ).scalars().all()
    completed = [row for row in rows if row.status in {"completed", "completed_empty"}]
    if completed:
        return completed[0]
    return rows[0] if rows else None


def _counts(bundle: Core3InputBundle, target_sku_codes: list[str]) -> dict[str, int | float]:
    return {
        "sku_count": len(_valid_sku_codes(bundle)),
        "target_sku_count": len(target_sku_codes),
        "market_fact_count": len(bundle.market_facts),
        "param_row_count": len(bundle.params),
        "claim_row_count": len(bundle.claims),
        "comment_row_count": len(bundle.comments),
        "market_profile_count": 0,
        "feature_profile_count": 0,
        "competitor_candidate_count": 0,
        "competitor_result_count": 0,
        "evidence_card_count": 0,
    }


def _rows_payload(rows: list[Any], fields: list[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "source_file_id": row.source_file_id,
            "import_batch_id": row.import_batch_id,
            "raw_row_id": row.raw_row_id,
        }
        item.update({field: getattr(row, field) for field in fields})
        output.append(item)
    return sorted(output, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
