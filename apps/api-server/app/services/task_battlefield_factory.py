from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    BattlefieldDef,
    CategoryProject,
    RawMarketFact,
    RawSkuMaster,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuCommentTopicResult,
    SkuParamNormalized,
    SkuTaskScore,
    UserTaskDef,
)
from app.services.factory_utils import ensure_seed_assets
from app.services.utils import relation_level, unique_list


def score_tasks_battlefields(db: Session, project_id: str) -> dict:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    ensure_seed_assets(db, project_id, project.category_code)
    db.execute(delete(SkuTaskScore).where(SkuTaskScore.project_id == project_id))
    db.execute(delete(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id))

    skus = [
        row.sku_code
        for row in db.execute(
            select(RawSkuMaster).where(RawSkuMaster.project_id == project_id)
        ).scalars()
        if row.sku_code
    ]
    tasks = db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars().all()
    battlefields = db.execute(
        select(BattlefieldDef).where(BattlefieldDef.project_id == project_id)
    ).scalars().all()

    claims_by_sku = _claims_by_sku(db, project_id)
    params_by_sku = _params_by_sku(db, project_id)
    topics_by_sku = _topics_by_sku(db, project_id)
    market_by_sku = _market_by_sku(db, project_id)

    task_scores_by_sku: dict[str, dict[str, SkuTaskScore]] = {}
    for sku_code in skus:
        for task in tasks:
            score, confidence, evidence_ids, reason = _score_task(
                task,
                claims_by_sku.get(sku_code, {}),
                params_by_sku.get(sku_code, {}),
                topics_by_sku.get(sku_code, {}),
                market_by_sku.get(sku_code),
            )
            if score <= 0:
                continue
            row = SkuTaskScore(
                project_id=project_id,
                category_code=project.category_code,
                sku_code=sku_code,
                task_code=task.task_code,
                score=round(score, 2),
                relation_level=relation_level(score),
                confidence=round(confidence, 3),
                evidence_ids=evidence_ids,
                reason=reason,
            )
            db.add(row)
            db.flush()
            task_scores_by_sku.setdefault(sku_code, {})[task.task_code] = row

        for battlefield in battlefields:
            score, confidence, evidence_ids, reason = _score_battlefield(
                battlefield,
                task_scores_by_sku.get(sku_code, {}),
                claims_by_sku.get(sku_code, {}),
                topics_by_sku.get(sku_code, {}),
                market_by_sku.get(sku_code),
            )
            if score <= 0:
                continue
            db.add(
                SkuBattlefieldScore(
                    project_id=project_id,
                    category_code=project.category_code,
                    sku_code=sku_code,
                    battlefield_code=battlefield.battlefield_code,
                    score=round(score, 2),
                    relation_level=relation_level(score, battlefield.entry_thresholds),
                    confidence=round(confidence, 3),
                    evidence_ids=evidence_ids,
                    reason=reason,
                )
            )

    db.commit()
    task_count = len(
        db.execute(select(SkuTaskScore).where(SkuTaskScore.project_id == project_id)).scalars().all()
    )
    battlefield_count = len(
        db.execute(
            select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id)
        ).scalars().all()
    )
    return {
        "step": "score_tasks_battlefields",
        "status": "completed",
        "counts": {"task_scores": task_count, "battlefield_scores": battlefield_count},
        "message": "用户任务与价值战场评分完成",
    }


def _claims_by_sku(db: Session, project_id: str) -> dict[str, dict[str, SkuClaimResult]]:
    output: dict[str, dict[str, SkuClaimResult]] = {}
    for row in db.execute(
        select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)
    ).scalars():
        output.setdefault(row.sku_code, {})[row.claim_code] = row
    return output


def _params_by_sku(db: Session, project_id: str) -> dict[str, dict[str, SkuParamNormalized]]:
    output: dict[str, dict[str, SkuParamNormalized]] = {}
    for row in db.execute(
        select(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id)
    ).scalars():
        output.setdefault(row.sku_code, {})[row.param_code] = row
    return output


def _topics_by_sku(db: Session, project_id: str) -> dict[str, dict[str, SkuCommentTopicResult]]:
    output: dict[str, dict[str, SkuCommentTopicResult]] = {}
    for row in db.execute(
        select(SkuCommentTopicResult).where(SkuCommentTopicResult.project_id == project_id)
    ).scalars():
        output.setdefault(row.sku_code, {})[row.topic_code] = row
    return output


def _market_by_sku(db: Session, project_id: str) -> dict[str, RawMarketFact]:
    output: dict[str, RawMarketFact] = {}
    for row in db.execute(select(RawMarketFact).where(RawMarketFact.project_id == project_id)).scalars():
        if row.sku_code:
            output[row.sku_code] = row
    return output


def _score_task(task: UserTaskDef, claims: dict, params: dict, topics: dict, market) -> tuple[float, float, list[str], str]:
    claim_hits = [claims[code] for code in task.positive_claim_codes if code in claims]
    param_hits = [params[code] for code in task.positive_param_codes if code in params and params[code].normalized_value != "unknown"]
    topic_hits = [topics[code] for code in task.comment_topic_codes if code in topics]

    claim_score = min(100, 100 * len(claim_hits) / max(1, len(task.positive_claim_codes)))
    param_score = min(100, 100 * len(param_hits) / max(1, len(task.positive_param_codes)))
    topic_score = min(100, 100 * len(topic_hits) / max(1, len(task.comment_topic_codes))) if task.comment_topic_codes else 0
    market_score = 80 if market and (market.sales_volume or 0) >= 1000 else 40 if market else 0
    weights = task.score_rule or {"claim": 0.45, "param": 0.25, "comment": 0.2, "market": 0.1}
    score = (
        weights.get("claim", 0.45) * claim_score
        + weights.get("param", 0.25) * param_score
        + weights.get("comment", 0.2) * topic_score
        + weights.get("market", 0.1) * market_score
    )
    if task.task_code == "TASK_CHILD_EYE_CARE" and not topic_hits:
        score = min(score, 62)
    confidence_inputs = [row.confidence for row in claim_hits + param_hits + topic_hits]
    confidence = sum(confidence_inputs) / len(confidence_inputs) if confidence_inputs else 0.45
    evidence = unique_list(
        [e for row in claim_hits for e in row.evidence_ids]
        + [e for row in param_hits for e in row.evidence_ids]
        + [e for row in topic_hits for e in row.evidence_ids]
    )
    reason = f"命中卖点 {len(claim_hits)} 个、参数 {len(param_hits)} 个、评论主题 {len(topic_hits)} 个。"
    return score, confidence, evidence, reason


def _score_battlefield(battlefield: BattlefieldDef, tasks: dict, claims: dict, topics: dict, market) -> tuple[float, float, list[str], str]:
    code = battlefield.battlefield_code
    task_codes = {
        "BF_FAMILY_VIEWING_UPGRADE": ["TASK_LIVING_ROOM_CINEMA", "TASK_LARGE_SCREEN_REPLACEMENT"],
        "BF_PREMIUM_PICTURE": ["TASK_PREMIUM_PICTURE_AV"],
        "BF_GAMING_SPORTS": ["TASK_GAMING_ENTERTAINMENT", "TASK_SPORTS_WATCHING"],
        "BF_LARGE_SCREEN_REPLACEMENT": ["TASK_LARGE_SCREEN_REPLACEMENT"],
        "BF_FAMILY_EYE_CARE": ["TASK_CHILD_EYE_CARE"],
        "BF_SENIOR_EASE_OF_USE": ["TASK_SENIOR_EASY_USE"],
    }.get(code, [])
    core_claims = {
        "BF_FAMILY_VIEWING_UPGRADE": ["CLAIM_LARGE_SCREEN_IMMERSION", "CLAIM_HIGH_BRIGHTNESS_HDR"],
        "BF_PREMIUM_PICTURE": ["CLAIM_MINI_LED_BACKLIGHT", "CLAIM_HIGH_BRIGHTNESS_HDR", "CLAIM_FINE_LOCAL_DIMMING"],
        "BF_GAMING_SPORTS": ["CLAIM_HIGH_REFRESH_RATE", "CLAIM_HDMI_2_1_GAMING"],
        "BF_LARGE_SCREEN_REPLACEMENT": ["CLAIM_LARGE_SCREEN_IMMERSION"],
        "BF_FAMILY_EYE_CARE": ["CLAIM_EYE_CARE_COMFORT"],
        "BF_SENIOR_EASE_OF_USE": ["CLAIM_SMART_VOICE_EASE"],
    }.get(code, [])
    topic_codes = {
        "BF_PREMIUM_PICTURE": ["TOPIC_PICTURE_QUALITY"],
        "BF_GAMING_SPORTS": ["TOPIC_GAMING_SMOOTHNESS", "TOPIC_SPORTS_WATCHING", "TOPIC_INTERFACE_CONNECTIVITY"],
        "BF_SENIOR_EASE_OF_USE": ["TOPIC_EASE_OF_USE", "TOPIC_SENIOR_FRIENDLY"],
    }.get(code, [])

    task_rows = [tasks[task_code] for task_code in task_codes if task_code in tasks]
    task_score = max([row.score for row in task_rows], default=0)
    claim_score = min(100, 100 * len([c for c in core_claims if c in claims]) / max(1, len(core_claims)))
    topic_score = min(100, 100 * len([t for t in topic_codes if t in topics]) / max(1, len(topic_codes))) if topic_codes else 0
    price_fit = 80 if market and (market.avg_price or 0) >= 8000 else 55 if market else 0
    weights = battlefield.score_rule or {"task_score": 0.4, "core_claim_bundle": 0.35, "price_channel_fit": 0.15, "comment_validation": 0.1}
    score = (
        weights.get("task_score", 0.4) * task_score
        + weights.get("core_claim_bundle", 0.35) * claim_score
        + weights.get("price_channel_fit", 0.15) * price_fit
        + weights.get("comment_validation", 0.1) * topic_score
    )
    if code == "BF_FAMILY_EYE_CARE" and topic_score == 0:
        score = min(score, 58)
    evidence = unique_list(
        [e for row in task_rows for e in row.evidence_ids]
        + [e for claim_code in core_claims if claim_code in claims for e in claims[claim_code].evidence_ids]
        + [e for topic_code in topic_codes if topic_code in topics for e in topics[topic_code].evidence_ids]
    )
    confidence_inputs = [row.confidence for row in task_rows] + [claims[c].confidence for c in core_claims if c in claims]
    confidence = sum(confidence_inputs) / len(confidence_inputs) if confidence_inputs else 0.45
    reason = f"战场由 {len(task_rows)} 个任务、{len([c for c in core_claims if c in claims])} 个核心卖点和 {len([t for t in topic_codes if t in topics])} 个评论主题支撑。"
    return score, confidence, evidence, reason

