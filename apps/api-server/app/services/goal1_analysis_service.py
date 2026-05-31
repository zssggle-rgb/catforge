from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisRun,
    CategoryProject,
    EvidenceItem,
    ImportBatch,
    RawMarketFact,
    RawSkuClaim,
    RawSkuComment,
    RawSkuMaster,
    RawSkuParam,
    RuleSet,
    SourceFile,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuCommentTopicResult,
    SkuCompetitorResult,
    SkuParamNormalized,
    SkuTaskScore,
)
from app.services.goal1_rule_engine import (
    RuleEvaluationContext,
    confidence_to_float,
    evaluate_rule_set,
    load_rule_documents,
    validate_rule_documents,
)
from app.services.factory_utils import ensure_seed_assets

ASSET_VERSION = "goal1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RULE_DIR = REPO_ROOT / "examples" / "goal1" / "rules"
DEFAULT_FIXTURE_PATH = REPO_ROOT / "examples" / "goal1" / "fixtures" / "tv_market_fixture.csv"


@dataclass
class SkuFeatureBundle:
    sku_code: str
    brand: str
    model: str
    category: str
    channel: str
    week: str
    params: dict[str, Any]
    market: dict[str, Any]
    claim_text: str
    comments_text: str
    comment_topics: dict[str, bool]
    evidence_by_feature: dict[str, list[str]]
    claim_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    battlefield_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def features(self) -> dict[str, Any]:
        return {
            "sku_identity": {
                "brand": self.brand,
                "model": self.model,
                "category": self.category,
                "channel": self.channel,
            },
            "param": self.params,
            "market": self.market,
            "claim_text": self.claim_text,
            "comment_topic": self.comment_topics,
            "claim": self.claim_results,
            "task": self.task_results,
            "battlefield": self.battlefield_results,
            "derived": {},
        }


def run_goal1_analysis(
    db: Session,
    project_id: str,
    *,
    fixture_path: str | None = None,
    target_sku_code: str | None = None,
) -> AnalysisRun:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")

    claim_rule, task_rule, battlefield_rule, competitor_rule = load_default_rule_sets()
    ensure_seed_assets(db, project_id, project.category_code)
    _persist_rule_sets(db, [claim_rule, task_rule, battlefield_rule, competitor_rule])
    _reset_goal1_project_data(db, project_id)
    bundles = load_goal1_fixture(
        db,
        project=project,
        fixture_path=Path(fixture_path) if fixture_path else DEFAULT_FIXTURE_PATH,
    )
    if target_sku_code and target_sku_code not in bundles:
        raise ValueError(f"fixture 中不存在目标 SKU: {target_sku_code}")

    _evaluate_claims(db, project, bundles, claim_rule)
    _evaluate_tasks(db, project, bundles, task_rule)
    _evaluate_battlefields(db, project, bundles, battlefield_rule)

    from app.services.goal1_competitor_engine import generate_goal1_competitors

    competitor_count = generate_goal1_competitors(
        db,
        project=project,
        bundles=bundles,
        competitor_rule=competitor_rule,
        target_sku_code=target_sku_code,
    )
    run = AnalysisRun(
        project_id=project_id,
        category_code=project.category_code,
        status="completed",
        target_sku_code=target_sku_code,
        fixture_path=str(fixture_path or DEFAULT_FIXTURE_PATH),
        rule_versions={
            "claim_activation": claim_rule["version"],
            "task_score": task_rule["version"],
            "battlefield_score": battlefield_rule["version"],
            "competitor_score": competitor_rule["version"],
        },
        asset_version=ASSET_VERSION,
        counts={
            "sku_count": len(bundles),
            "claim_results": _count(db, SkuClaimResult, project_id),
            "task_scores": _count(db, SkuTaskScore, project_id),
            "battlefield_scores": _count(db, SkuBattlefieldScore, project_id),
            "competitor_results": competitor_count,
        },
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def load_default_rule_sets() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    claim_sets = load_rule_documents(DEFAULT_RULE_DIR / "tv_claim_activation.yaml")
    task_battlefield_sets = load_rule_documents(DEFAULT_RULE_DIR / "tv_task_battlefield.yaml")
    competitor_sets = load_rule_documents(DEFAULT_RULE_DIR / "tv_competitor.yaml")
    rule_sets = claim_sets + task_battlefield_sets + competitor_sets
    validate_rule_documents(rule_sets)
    by_type = {item.get("rule_type", "competitor_score"): item for item in rule_sets}
    return (
        by_type["claim_activation"],
        by_type["task_score"],
        by_type["battlefield_score"],
        by_type["competitor_score"],
    )


def load_goal1_fixture(
    db: Session, *, project: CategoryProject, fixture_path: Path = DEFAULT_FIXTURE_PATH
) -> dict[str, SkuFeatureBundle]:
    if not fixture_path.exists():
        raise ValueError(f"fixture 文件不存在: {fixture_path}")
    with fixture_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    source = SourceFile(
        project_id=project.project_id,
        category_code=project.category_code,
        file_name=fixture_path.name,
        file_type="goal1_market_fixture",
        storage_path=str(fixture_path),
        status="imported",
        row_count=len(rows),
    )
    db.add(source)
    db.flush()
    batch = ImportBatch(
        project_id=project.project_id,
        category_code=project.category_code,
        source_file_id=source.source_file_id,
        file_type="goal1_market_fixture",
        status="completed",
        row_count=len(rows),
        error_count=0,
    )
    db.add(batch)
    db.flush()

    bundles: dict[str, SkuFeatureBundle] = {}
    for index, row in enumerate(rows, start=1):
        sku_code = row["sku_code"].strip()
        raw_row_id = str(index)
        category = row.get("category") or project.category_code
        db.add(
            RawSkuMaster(
                project_id=project.project_id,
                category_code=category,
                source_file_id=source.source_file_id,
                import_batch_id=batch.import_batch_id,
                raw_row_id=raw_row_id,
                sku_code=sku_code,
                brand=row.get("brand"),
                model_name=row.get("model"),
                category_name=category,
            )
        )
        db.add(
            RawSkuClaim(
                project_id=project.project_id,
                category_code=category,
                source_file_id=source.source_file_id,
                import_batch_id=batch.import_batch_id,
                raw_row_id=raw_row_id,
                sku_code=sku_code,
                claim_title="goal1_fixture_claims",
                claim_text=row.get("raw_claim_text"),
                claim_order=1,
                source_channel=row.get("channel"),
                observed_at=row.get("week"),
            )
        )
        db.add(
            RawSkuComment(
                project_id=project.project_id,
                category_code=category,
                source_file_id=source.source_file_id,
                import_batch_id=batch.import_batch_id,
                raw_row_id=raw_row_id,
                sku_code=sku_code,
                platform=row.get("channel"),
                comment_id=f"goal1-{sku_code}",
                comment_text=row.get("comments_text"),
                rating=5.0,
                comment_time=row.get("week"),
            )
        )
        market = {
            "avg_price": _float(row.get("avg_price")),
            "sales_volume": _float(row.get("sales_volume")),
            "sales_amount": _float(row.get("sales_amount")),
            "channel": row.get("channel"),
            "week": row.get("week"),
        }
        db.add(
            RawMarketFact(
                project_id=project.project_id,
                category_code=category,
                source_file_id=source.source_file_id,
                import_batch_id=batch.import_batch_id,
                raw_row_id=raw_row_id,
                sku_code=sku_code,
                period=row.get("week"),
                period_type="week",
                channel_group=row.get("channel"),
                channel_type="online",
                channel_name=row.get("channel"),
                sales_volume=market["sales_volume"],
                sales_amount=market["sales_amount"],
                avg_price=market["avg_price"],
                promotion_flag=None,
            )
        )

        evidence_by_feature: dict[str, list[str]] = {}
        params = _extract_params(row)
        for param_code, value in params.items():
            db.add(
                RawSkuParam(
                    project_id=project.project_id,
                    category_code=category,
                    source_file_id=source.source_file_id,
                    import_batch_id=batch.import_batch_id,
                    raw_row_id=f"{raw_row_id}:{param_code}",
                    sku_code=sku_code,
                    raw_param_name=param_code,
                    raw_param_value=row.get(param_code),
                    raw_unit=_param_unit(param_code),
                    source_channel=row.get("channel"),
                    observed_at=row.get("week"),
                )
            )
            evidence = _add_goal1_evidence(
                db,
                project=project,
                category_code=category,
                sku_code=sku_code,
                source_type="param",
                source_file_id=source.source_file_id,
                raw_row_id=raw_row_id,
                field_name=param_code,
                raw_value=row.get(param_code),
                normalized_value={param_code: value},
                source_ref={"fixture": str(fixture_path), "row": index, "column": param_code},
                confidence=0.92,
            )
            evidence_by_feature[f"param.{param_code}"] = [evidence.evidence_id]
            db.add(
                SkuParamNormalized(
                    project_id=project.project_id,
                    category_code=category,
                    sku_code=sku_code,
                    param_code=param_code,
                    normalized_value="unknown" if value is None else str(value),
                    normalized_numeric=value if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
                    normalized_bool=value if isinstance(value, bool) else None,
                    unit=_param_unit(param_code),
                    raw_value=row.get(param_code),
                    confidence=0.92,
                    evidence_ids=[evidence.evidence_id],
                    review_status="auto_pass" if value is not None else "needs_review",
                    status="accepted" if value is not None else "candidate",
                    rule_version="fixture-normalizer-v1",
                    asset_version=ASSET_VERSION,
                    version=ASSET_VERSION,
                )
            )

        claim_evidence = _add_goal1_evidence(
            db,
            project=project,
            category_code=category,
            sku_code=sku_code,
            source_type="claim",
            source_file_id=source.source_file_id,
            raw_row_id=raw_row_id,
            field_name="raw_claim_text",
            raw_value=row.get("raw_claim_text"),
            normalized_value={"claim_text": row.get("raw_claim_text")},
            source_ref={"fixture": str(fixture_path), "row": index, "column": "raw_claim_text"},
            confidence=0.88,
        )
        evidence_by_feature["claim_text"] = [claim_evidence.evidence_id]
        comment_evidence = _add_goal1_evidence(
            db,
            project=project,
            category_code=category,
            sku_code=sku_code,
            source_type="comment",
            source_file_id=source.source_file_id,
            raw_row_id=raw_row_id,
            field_name="comments_text",
            raw_value=row.get("comments_text"),
            normalized_value={"comments_text": row.get("comments_text")},
            source_ref={"fixture": str(fixture_path), "row": index, "column": "comments_text"},
            confidence=0.82,
        )
        topics = _comment_topics(row.get("comments_text") or "")
        for topic_code, active in topics.items():
            if not active:
                continue
            evidence_by_feature[f"comment_topic.{topic_code}"] = [comment_evidence.evidence_id]
            db.add(
                SkuCommentTopicResult(
                    project_id=project.project_id,
                    category_code=category,
                    sku_code=sku_code,
                    topic_code=topic_code,
                    sentiment="positive",
                    confidence=0.82,
                    evidence_ids=[comment_evidence.evidence_id],
                    activates_product_claim=True,
                    review_status="auto_pass",
                    status="accepted",
                    rule_version="comment-topic-keyword-v1",
                    asset_version=ASSET_VERSION,
                    version=ASSET_VERSION,
                )
            )

        for market_code, value in market.items():
            evidence = _add_goal1_evidence(
                db,
                project=project,
                category_code=category,
                sku_code=sku_code,
                source_type="market",
                source_file_id=source.source_file_id,
                raw_row_id=raw_row_id,
                field_name=market_code,
                raw_value=row.get(market_code),
                normalized_value={market_code: value},
                source_ref={"fixture": str(fixture_path), "row": index, "column": market_code},
                confidence=0.9,
            )
            evidence_by_feature[f"market.{market_code}"] = [evidence.evidence_id]

        bundles[sku_code] = SkuFeatureBundle(
            sku_code=sku_code,
            brand=row.get("brand") or "",
            model=row.get("model") or "",
            category=category,
            channel=row.get("channel") or "",
            week=row.get("week") or "",
            params=params,
            market=market,
            claim_text=row.get("raw_claim_text") or "",
            comments_text=row.get("comments_text") or "",
            comment_topics=topics,
            evidence_by_feature=evidence_by_feature,
        )
    db.flush()
    return bundles


def get_goal1_analysis(db: Session, project_id: str, sku_code: str) -> dict[str, Any]:
    claims = db.execute(
        select(SkuClaimResult).where(
            SkuClaimResult.project_id == project_id,
            SkuClaimResult.sku_code == sku_code,
        )
    ).scalars().all()
    tasks = db.execute(
        select(SkuTaskScore).where(
            SkuTaskScore.project_id == project_id,
            SkuTaskScore.sku_code == sku_code,
        )
    ).scalars().all()
    battlefields = db.execute(
        select(SkuBattlefieldScore).where(
            SkuBattlefieldScore.project_id == project_id,
            SkuBattlefieldScore.sku_code == sku_code,
        )
    ).scalars().all()
    competitors = db.execute(
        select(SkuCompetitorResult).where(
            SkuCompetitorResult.project_id == project_id,
            SkuCompetitorResult.target_sku_code == sku_code,
        ).order_by(SkuCompetitorResult.rank)
    ).scalars().all()
    return {
        "sku_code": sku_code,
        "claim_results": [_claim_to_dict(row) for row in claims],
        "task_scores": [_task_to_dict(row) for row in tasks],
        "battlefield_scores": [_battlefield_to_dict(row) for row in battlefields],
        "competitors": [_competitor_to_dict(row) for row in competitors],
    }


def run_to_dict(run: AnalysisRun) -> dict[str, Any]:
    return {
        "run_id": run.analysis_run_id,
        "analysis_run_id": run.analysis_run_id,
        "project_id": run.project_id,
        "category_code": run.category_code,
        "status": run.status,
        "target_sku_code": run.target_sku_code,
        "fixture_path": run.fixture_path,
        "rule_versions": run.rule_versions,
        "asset_version": run.asset_version,
        "counts": run.counts,
        "error_message": run.error_message,
    }


def _persist_rule_sets(db: Session, rule_sets: list[dict[str, Any]]) -> None:
    for rule_set in rule_sets:
        existing = db.execute(
            select(RuleSet).where(
                RuleSet.rule_set_id == rule_set["rule_set_id"],
                RuleSet.version == str(rule_set["version"]),
            )
        ).scalar_one_or_none()
        if existing:
            existing.content = rule_set
            existing.rule_type = rule_set.get("rule_type", "competitor_score")
            existing.status = rule_set.get("status", "draft")
            continue
        db.add(
            RuleSet(
                rule_set_id=rule_set["rule_set_id"],
                category_code=rule_set.get("category", rule_set.get("category_code", "TV")),
                rule_type=rule_set.get("rule_type", "competitor_score"),
                version=str(rule_set["version"]),
                status=rule_set.get("status", "draft"),
                source_format="yaml",
                content=rule_set,
                validation_errors=[],
            )
        )
    db.flush()


def _reset_goal1_project_data(db: Session, project_id: str) -> None:
    for model in [
        AnalysisRun,
        SkuCompetitorResult,
        SkuBattlefieldScore,
        SkuTaskScore,
        SkuClaimResult,
        SkuCommentTopicResult,
        SkuParamNormalized,
        EvidenceItem,
        RawMarketFact,
        RawSkuComment,
        RawSkuClaim,
        RawSkuMaster,
        RawSkuParam,
        ImportBatch,
        SourceFile,
    ]:
        db.execute(delete(model).where(model.project_id == project_id))
    db.flush()


def _evaluate_claims(
    db: Session,
    project: CategoryProject,
    bundles: dict[str, SkuFeatureBundle],
    rule_set: dict[str, Any],
) -> None:
    for bundle in bundles.values():
        context = RuleEvaluationContext(bundle.features, bundle.evidence_by_feature)
        for result in evaluate_rule_set(rule_set, context):
            if not result.matched:
                continue
            confidence = confidence_to_float(result.confidence)
            bundle.claim_results[result.output_code] = {"score": result.score, "confidence": confidence}
            bundle.evidence_by_feature[f"claim.{result.output_code}"] = result.evidence_ids
            db.add(
                SkuClaimResult(
                    project_id=project.project_id,
                    category_code=project.category_code,
                    sku_code=bundle.sku_code,
                    claim_code=result.output_code,
                    score=result.score,
                    confidence=confidence,
                    activation_source="goal1_rule_dsl",
                    evidence_ids=result.evidence_ids,
                    extracted_values={"rule_id": result.rule_id},
                    review_status=result.review_status,
                    status="accepted",
                    rule_version=result.rule_version,
                    asset_version=ASSET_VERSION,
                    version=ASSET_VERSION,
                )
            )
    db.flush()


def _evaluate_tasks(
    db: Session,
    project: CategoryProject,
    bundles: dict[str, SkuFeatureBundle],
    rule_set: dict[str, Any],
) -> None:
    for bundle in bundles.values():
        context = RuleEvaluationContext(bundle.features, bundle.evidence_by_feature)
        for result in evaluate_rule_set(rule_set, context):
            if not result.matched:
                continue
            confidence = confidence_to_float(result.confidence)
            bundle.task_results[result.output_code] = {
                "score": result.score,
                "relation_level": result.relation_level,
                "confidence": confidence,
            }
            bundle.evidence_by_feature[f"task.{result.output_code}"] = result.evidence_ids
            db.add(
                SkuTaskScore(
                    project_id=project.project_id,
                    category_code=project.category_code,
                    sku_code=bundle.sku_code,
                    task_code=result.output_code,
                    score=result.score,
                    relation_level=result.relation_level,
                    confidence=confidence,
                    evidence_ids=result.evidence_ids,
                    reason=f"Goal1 DSL 规则 {result.rule_id} 命中，得分 {result.score}",
                    review_status=result.review_status,
                    status="accepted",
                    rule_version=result.rule_version,
                    asset_version=ASSET_VERSION,
                    version=ASSET_VERSION,
                )
            )
    db.flush()


def _evaluate_battlefields(
    db: Session,
    project: CategoryProject,
    bundles: dict[str, SkuFeatureBundle],
    rule_set: dict[str, Any],
) -> None:
    for bundle in bundles.values():
        context = RuleEvaluationContext(bundle.features, bundle.evidence_by_feature)
        for result in evaluate_rule_set(rule_set, context):
            if not result.matched:
                continue
            confidence = confidence_to_float(result.confidence)
            bundle.battlefield_results[result.output_code] = {
                "score": result.score,
                "relation_level": result.relation_level,
                "confidence": confidence,
            }
            bundle.evidence_by_feature[f"battlefield.{result.output_code}"] = result.evidence_ids
            db.add(
                SkuBattlefieldScore(
                    project_id=project.project_id,
                    category_code=project.category_code,
                    sku_code=bundle.sku_code,
                    battlefield_code=result.output_code,
                    score=result.score,
                    relation_level=result.relation_level,
                    confidence=confidence,
                    evidence_ids=result.evidence_ids,
                    reason=f"Goal1 DSL 规则 {result.rule_id} 命中，得分 {result.score}",
                    review_status=result.review_status,
                    status="accepted",
                    rule_version=result.rule_version,
                    asset_version=ASSET_VERSION,
                    version=ASSET_VERSION,
                )
            )
    db.flush()


def _extract_params(row: dict[str, str]) -> dict[str, Any]:
    return {
        "screen_size_inch": _float(row.get("screen_size_inch")),
        "mini_led_flag": _bool(row.get("mini_led_flag")),
        "oled_flag": _bool(row.get("oled_flag")),
        "refresh_rate_hz": _float(row.get("refresh_rate_hz")),
        "peak_brightness_nits": _float(row.get("peak_brightness_nits")),
        "dimming_zones": _float(row.get("dimming_zones")),
        "hdmi_2_1_ports": _float(row.get("hdmi_2_1_ports")),
        "low_blue_light_flag": _bool(row.get("low_blue_light_flag")),
        "eye_dimming_freq_hz": _float(row.get("eye_dimming_freq_hz")),
        "voice_control_flag": _bool(row.get("voice_control_flag")),
    }


def _comment_topics(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        "picture_quality_positive": _contains_any(lowered, ["画质", "清晰", "色彩", "黑位", "亮度", "画面亮", "自然"]),
        "viewing_experience_positive": _contains_any(lowered, ["体验", "电影", "爽", "画质", "画面", "沉浸"]),
        "sound_positive": _contains_any(lowered, ["音效", "音质", "声音", "环绕"]),
        "sports_smoothness_positive": _contains_any(lowered, ["看球", "不卡", "运动", "流畅", "顺滑"]),
        "interface_positive": _contains_any(lowered, ["接口", "hdmi", "丰富", "够用"]),
    }


def _add_goal1_evidence(
    db: Session,
    *,
    project: CategoryProject,
    category_code: str,
    sku_code: str,
    source_type: str,
    source_file_id: str,
    raw_row_id: str,
    field_name: str,
    raw_value: str | None,
    normalized_value: Any,
    source_ref: dict[str, Any],
    confidence: float,
) -> EvidenceItem:
    evidence = EvidenceItem(
        project_id=project.project_id,
        category_code=category_code,
        sku_code=sku_code,
        source_type=source_type,
        source_file_id=source_file_id,
        raw_row_id=raw_row_id,
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        source_ref=source_ref,
        confidence=confidence,
    )
    db.add(evidence)
    db.flush()
    return evidence


def _claim_to_dict(row: SkuClaimResult) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "claim_code": row.claim_code,
        "score": row.score,
        "confidence": row.confidence,
        "evidence_ids": row.evidence_ids,
        "rule_version": row.rule_version,
        "asset_version": row.asset_version,
        "review_status": row.review_status,
        "status": row.status,
    }


def _task_to_dict(row: SkuTaskScore) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "task_code": row.task_code,
        "score": row.score,
        "relation_level": row.relation_level,
        "confidence": row.confidence,
        "evidence_ids": row.evidence_ids,
        "rule_version": row.rule_version,
        "asset_version": row.asset_version,
        "review_status": row.review_status,
    }


def _battlefield_to_dict(row: SkuBattlefieldScore) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "battlefield_code": row.battlefield_code,
        "score": row.score,
        "relation_level": row.relation_level,
        "confidence": row.confidence,
        "evidence_ids": row.evidence_ids,
        "rule_version": row.rule_version,
        "asset_version": row.asset_version,
        "review_status": row.review_status,
    }


def _competitor_to_dict(row: SkuCompetitorResult) -> dict[str, Any]:
    return {
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


def _param_unit(param_code: str) -> str | None:
    if param_code == "screen_size_inch":
        return "inch"
    if param_code.endswith("_hz"):
        return "Hz"
    if param_code.endswith("_nits"):
        return "nits"
    if param_code == "dimming_zones":
        return "zones"
    if param_code == "hdmi_2_1_ports":
        return "ports"
    return None


def _float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes", "y", "是"}:
        return True
    if lowered in {"false", "0", "no", "n", "否"}:
        return False
    return None


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _count(db: Session, model: type, project_id: str) -> int:
    return len(db.execute(select(model).where(model.project_id == project_id)).scalars().all())
