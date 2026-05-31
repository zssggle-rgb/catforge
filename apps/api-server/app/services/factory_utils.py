from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    BattlefieldDef,
    CommentTopicDef,
    EvidenceItem,
    SkuClaimResult,
    SkuCommentTopicResult,
    SkuParamNormalized,
    StdClaimDef,
    StdParamDef,
    TargetGroupDef,
    UserTaskDef,
)
from app.services.seed_loader import load_tv_seed_rules
from app.services.utils import unique_list


def reset_table(db: Session, model: type, project_id: str) -> None:
    db.execute(delete(model).where(model.project_id == project_id))


def add_evidence(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    sku_code: str | None,
    source_type: str,
    source_file_id: str | None,
    raw_row_id: str | None,
    field_name: str | None,
    raw_value: str | None,
    normalized_value,
    confidence: float,
) -> EvidenceItem:
    evidence = EvidenceItem(
        project_id=project_id,
        category_code=category_code,
        sku_code=sku_code,
        source_type=source_type,
        source_file_id=source_file_id,
        raw_row_id=raw_row_id,
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=confidence,
    )
    db.add(evidence)
    db.flush()
    return evidence


def upsert_param_result(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    sku_code: str,
    param_code: str,
    normalized_value,
    normalized_numeric: float | None,
    normalized_bool: bool | None,
    unit: str | None,
    raw_value: str | None,
    confidence: float,
    evidence_ids: Iterable[str],
) -> SkuParamNormalized:
    existing = db.execute(
        select(SkuParamNormalized).where(
            SkuParamNormalized.project_id == project_id,
            SkuParamNormalized.sku_code == sku_code,
            SkuParamNormalized.param_code == param_code,
        )
    ).scalar_one_or_none()
    value_text = "unknown" if normalized_value is None else str(normalized_value)
    if existing:
        existing.evidence_ids = unique_list([*existing.evidence_ids, *list(evidence_ids)])
        if existing.normalized_value == "unknown" or confidence >= existing.confidence:
            existing.normalized_value = value_text
            existing.normalized_numeric = normalized_numeric
            existing.normalized_bool = normalized_bool
            existing.unit = unit
            existing.raw_value = raw_value
            existing.confidence = confidence
        return existing
    result = SkuParamNormalized(
        project_id=project_id,
        category_code=category_code,
        sku_code=sku_code,
        param_code=param_code,
        normalized_value=value_text,
        normalized_numeric=normalized_numeric,
        normalized_bool=normalized_bool,
        unit=unit,
        raw_value=raw_value,
        confidence=confidence,
        evidence_ids=unique_list(list(evidence_ids)),
    )
    db.add(result)
    db.flush()
    return result


def upsert_claim_result(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    sku_code: str,
    claim_code: str,
    confidence: float,
    activation_source: str,
    evidence_ids: Iterable[str],
    extracted_values: dict | None = None,
) -> SkuClaimResult:
    existing = db.execute(
        select(SkuClaimResult).where(
            SkuClaimResult.project_id == project_id,
            SkuClaimResult.sku_code == sku_code,
            SkuClaimResult.claim_code == claim_code,
        )
    ).scalar_one_or_none()
    if existing:
        existing.confidence = max(existing.confidence, confidence)
        existing.evidence_ids = unique_list([*existing.evidence_ids, *list(evidence_ids)])
        existing.extracted_values = {**(existing.extracted_values or {}), **(extracted_values or {})}
        return existing
    result = SkuClaimResult(
        project_id=project_id,
        category_code=category_code,
        sku_code=sku_code,
        claim_code=claim_code,
        confidence=confidence,
        activation_source=activation_source,
        evidence_ids=unique_list(list(evidence_ids)),
        extracted_values=extracted_values or {},
    )
    db.add(result)
    db.flush()
    return result


def upsert_topic_result(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    sku_code: str,
    topic_code: str,
    sentiment: str,
    confidence: float,
    evidence_ids: Iterable[str],
    activates_product_claim: bool,
) -> SkuCommentTopicResult:
    existing = db.execute(
        select(SkuCommentTopicResult).where(
            SkuCommentTopicResult.project_id == project_id,
            SkuCommentTopicResult.sku_code == sku_code,
            SkuCommentTopicResult.topic_code == topic_code,
        )
    ).scalar_one_or_none()
    if existing:
        existing.confidence = max(existing.confidence, confidence)
        existing.evidence_ids = unique_list([*existing.evidence_ids, *list(evidence_ids)])
        if sentiment == "positive":
            existing.sentiment = sentiment
        return existing
    result = SkuCommentTopicResult(
        project_id=project_id,
        category_code=category_code,
        sku_code=sku_code,
        topic_code=topic_code,
        sentiment=sentiment,
        confidence=confidence,
        evidence_ids=unique_list(list(evidence_ids)),
        activates_product_claim=activates_product_claim,
    )
    db.add(result)
    db.flush()
    return result


def ensure_seed_assets(db: Session, project_id: str, category_code: str = "TV") -> dict[str, int]:
    rules = load_tv_seed_rules()
    counts = {"params": 0, "claims": 0, "topics": 0, "tasks": 0, "target_groups": 0, "battlefields": 0}

    for item in rules["standard_params"]:
        exists = db.execute(
            select(StdParamDef).where(
                StdParamDef.project_id == project_id,
                StdParamDef.param_code == item["param_code"],
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                StdParamDef(
                    project_id=project_id,
                    category_code=category_code,
                    param_code=item["param_code"],
                    param_name=item["param_name"],
                    param_group=item["param_group"],
                    data_type=item["data_type"],
                    unit=item.get("unit"),
                    raw_aliases=item.get("raw_aliases", []),
                    normalize_rule=item.get("normalize_rule", {}),
                    level_rule=item.get("level_rule"),
                    business_meaning=item.get("business_meaning"),
                    mapped_claim_codes=item.get("mapped_claim_codes", []),
                    evidence_weight=item.get("evidence_weight", 0.8),
                    status="candidate",
                    version=rules["version"],
                )
            )
            counts["params"] += 1

    for item in rules["standard_claims"]:
        exists = db.execute(
            select(StdClaimDef).where(
                StdClaimDef.project_id == project_id,
                StdClaimDef.claim_code == item["claim_code"],
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                StdClaimDef(
                    project_id=project_id,
                    category_code=category_code,
                    claim_code=item["claim_code"],
                    claim_name=item["claim_name"],
                    claim_group=item["claim_group"],
                    definition=item["definition"],
                    activation_rule=item.get("activation_rule", {}),
                    raw_keywords=item.get("raw_keywords", []),
                    supporting_param_codes=item.get("supporting_param_codes", []),
                    comment_topic_codes=item.get("comment_topic_codes", []),
                    mapped_task_codes=item.get("mapped_task_codes", []),
                    mapped_battlefield_codes=item.get("mapped_battlefield_codes", []),
                    default_layer_hint=item.get("default_layer_hint"),
                    confidence_rule=item.get("confidence_rule"),
                    status="candidate",
                    version=rules["version"],
                )
            )
            counts["claims"] += 1

    for item in rules["comment_topics"]:
        exists = db.execute(
            select(CommentTopicDef).where(
                CommentTopicDef.project_id == project_id,
                CommentTopicDef.topic_code == item["topic_code"],
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                CommentTopicDef(
                    project_id=project_id,
                    category_code=category_code,
                    topic_code=item["topic_code"],
                    topic_name=item["topic_name"],
                    topic_group=item["topic_group"],
                    keywords=item.get("keywords", []),
                    sentiment_hint=item.get("sentiment_hint"),
                    mapped_claim_codes=item.get("mapped_claim_codes", []),
                    mapped_task_codes=item.get("mapped_task_codes", []),
                    activates_product_claim=item.get("activates_product_claim", True),
                    status="candidate",
                    version=rules["version"],
                )
            )
            counts["topics"] += 1

    for item in rules["user_tasks"]:
        exists = db.execute(
            select(UserTaskDef).where(
                UserTaskDef.project_id == project_id,
                UserTaskDef.task_code == item["task_code"],
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                UserTaskDef(
                    project_id=project_id,
                    category_code=category_code,
                    task_code=item["task_code"],
                    task_name=item["task_name"],
                    definition=item["definition"],
                    positive_claim_codes=item.get("positive_claim_codes", []),
                    positive_param_codes=item.get("positive_param_codes", []),
                    comment_topic_codes=item.get("comment_topic_codes", []),
                    default_target_group_codes=item.get("default_target_group_codes", []),
                    battlefield_codes=item.get("battlefield_codes", []),
                    score_rule=item.get("score_rule", {}),
                    status="candidate",
                    version=rules["version"],
                )
            )
            counts["tasks"] += 1

    for item in rules["target_groups"]:
        exists = db.execute(
            select(TargetGroupDef).where(
                TargetGroupDef.project_id == project_id,
                TargetGroupDef.target_group_code == item["target_group_code"],
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                TargetGroupDef(
                    project_id=project_id,
                    category_code=category_code,
                    target_group_code=item["target_group_code"],
                    target_group_name=item["target_group_name"],
                    definition=item["definition"],
                    status="candidate",
                    version=rules["version"],
                )
            )
            counts["target_groups"] += 1

    for item in rules["battlefields"]:
        exists = db.execute(
            select(BattlefieldDef).where(
                BattlefieldDef.project_id == project_id,
                BattlefieldDef.battlefield_code == item["battlefield_code"],
            )
        ).scalar_one_or_none()
        if not exists:
            db.add(
                BattlefieldDef(
                    project_id=project_id,
                    category_code=category_code,
                    battlefield_code=item["battlefield_code"],
                    battlefield_name=item["battlefield_name"],
                    definition=item["definition"],
                    required_signal_rule=item.get("required_signal_rule"),
                    score_rule=item.get("score_rule", {}),
                    entry_thresholds=item.get("entry_thresholds", {}),
                    competitor_rule_ref=item.get("competitor_rule_ref"),
                    status="candidate",
                    version=rules["version"],
                )
            )
            counts["battlefields"] += 1

    db.flush()
    return counts


def project_param_map(db: Session, project_id: str) -> dict[str, dict[str, SkuParamNormalized]]:
    rows = db.execute(
        select(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id)
    ).scalars()
    output: dict[str, dict[str, SkuParamNormalized]] = {}
    for row in rows:
        output.setdefault(row.sku_code, {})[row.param_code] = row
    return output

