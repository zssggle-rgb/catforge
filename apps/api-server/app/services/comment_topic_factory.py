import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CategoryProject, RawSkuComment, SkuCommentTopicResult
from app.services.factory_utils import add_evidence, ensure_seed_assets, upsert_topic_result
from app.services.seed_loader import load_tv_seed_rules
from app.services.utils import clean_text


NEGATIVE_WORDS = ["慢", "卡", "差", "贵", "偏高", "不清楚", "不流畅", "失败"]
POSITIVE_WORDS = ["好", "不错", "清晰", "流畅", "爽", "专业", "够用", "自然", "高"]


def generate_comment_topics(db: Session, project_id: str) -> dict:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    ensure_seed_assets(db, project_id, project.category_code)
    db.execute(delete(SkuCommentTopicResult).where(SkuCommentTopicResult.project_id == project_id))

    rules = load_tv_seed_rules()["comment_topics"]
    rows = db.execute(
        select(RawSkuComment).where(RawSkuComment.project_id == project_id)
    ).scalars().all()
    hits = 0
    for row in rows:
        for sentence in split_comment(row.comment_text or ""):
            for topic in rules:
                if any(keyword.lower() in sentence.lower() for keyword in topic.get("keywords", [])):
                    sentiment = infer_sentiment(sentence, row.rating)
                    confidence = 0.82 if sentiment == "positive" else 0.72
                    evidence = add_evidence(
                        db,
                        project_id=project_id,
                        category_code=row.category_code,
                        sku_code=row.sku_code,
                        source_type="comment",
                        source_file_id=row.source_file_id,
                        raw_row_id=row.raw_row_id,
                        field_name=topic["topic_code"],
                        raw_value=sentence,
                        normalized_value={"topic_code": topic["topic_code"], "sentiment": sentiment},
                        confidence=confidence,
                    )
                    upsert_topic_result(
                        db,
                        project_id=project_id,
                        category_code=row.category_code,
                        sku_code=row.sku_code or "",
                        topic_code=topic["topic_code"],
                        sentiment=sentiment,
                        confidence=confidence,
                        evidence_ids=[evidence.evidence_id],
                        activates_product_claim=topic.get("activates_product_claim", True),
                    )
                    hits += 1

    db.commit()
    result_count = len(
        db.execute(
            select(SkuCommentTopicResult).where(SkuCommentTopicResult.project_id == project_id)
        ).scalars().all()
    )
    return {
        "step": "generate_comment_topics",
        "status": "completed",
        "counts": {
            "raw_comment_rows": len(rows),
            "topic_hits": hits,
            "topic_results": result_count,
        },
        "message": "评论主题识别完成",
    }


def split_comment(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    parts = re.split(r"[。！？!?；;\n]", cleaned)
    return [part.strip(" ，,") for part in parts if part.strip(" ，,")]


def infer_sentiment(sentence: str, rating: float | None) -> str:
    if any(word in sentence for word in NEGATIVE_WORDS):
        return "negative"
    if any(word in sentence for word in POSITIVE_WORDS):
        return "positive"
    if rating is not None:
        if rating >= 4:
            return "positive"
        if rating <= 2:
            return "negative"
    return "neutral"

