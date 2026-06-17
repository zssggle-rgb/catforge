"""M05 weak sentiment hint service.

This service combines raw sentiment inherited from M02/M05 comment units with
sentence text rules. It only enriches M05 sentence atoms and intentionally stops
before topic hints, quality profiles, tasks, battlefields, competitors, and
reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import CommentEvidenceAtomRecord
from app.services.core3_real_data.constants import (
    CommentLowValueReason,
    CommentSentimentHint,
    CommentSentimentSource,
    Core3ConfidenceLevel,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_SENTIMENT_HINT_RESULT_HASH_VERSION = "m05_comment_sentiment_hint_result_v1"

RAW_POSITIVE_VALUES = frozenset({"positive", "pos", "正面", "好评", "满意", "推荐"})
RAW_NEGATIVE_VALUES = frozenset({"negative", "neg", "负面", "差评", "不满意"})
RAW_NEUTRAL_VALUES = frozenset({"neutral", "中性", "一般"})

TEXT_POSITIVE_TERMS = frozenset(
    {
        "清晰",
        "流畅",
        "不卡",
        "不拖影",
        "满意",
        "推荐",
        "好用",
        "方便",
        "划算",
        "值",
        "舒服",
        "低延迟",
        "延迟低",
        "无广告",
        "很快",
    }
)
TEXT_NEGATIVE_TERMS = frozenset(
    {
        "卡顿",
        "很卡",
        "广告多",
        "拖影",
        "刺眼",
        "不满意",
        "差",
        "坏",
        "故障",
        "慢",
        "复杂",
        "漏光",
        "不值",
        "贵",
        "闪退",
        "死机",
    }
)
TEXT_NEUTRAL_TERMS = frozenset({"一般", "还行", "普通", "正常"})
LOW_VALUE_POSITIVE_BLOCK_REASONS = {
    CommentLowValueReason.DEFAULT_POSITIVE.value,
    CommentLowValueReason.TOO_SHORT_GENERIC.value,
    CommentLowValueReason.EMPTY_TEXT.value,
}


@dataclass(frozen=True)
class CommentSentimentHintIssue:
    issue_code: str
    message_cn: str
    comment_evidence_id: str | None = None
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentSentimentHintResult:
    records: list[CommentEvidenceAtomRecord]
    issues: list[CommentSentimentHintIssue] = field(default_factory=list)
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    unknown_count: int = 0
    conflict_count: int = 0
    text_rule_count: int = 0


@dataclass(frozen=True)
class _TextSentiment:
    sentiment: CommentSentimentHint
    matched_terms: list[str]
    conflict_flag: bool = False


class CommentSentimentHintService:
    def apply_sentiment_hints(self, atoms: Sequence[CommentEvidenceAtomRecord]) -> CommentSentimentHintResult:
        records: list[CommentEvidenceAtomRecord] = []
        issues: list[CommentSentimentHintIssue] = []
        for atom in atoms:
            enriched, atom_issues = self._apply_atom(atom)
            records.append(enriched)
            issues.extend(atom_issues)

        return CommentSentimentHintResult(
            records=records,
            issues=issues,
            positive_count=sum(1 for record in records if record.sentiment_hint == CommentSentimentHint.POSITIVE.value),
            negative_count=sum(1 for record in records if record.sentiment_hint == CommentSentimentHint.NEGATIVE.value),
            neutral_count=sum(1 for record in records if record.sentiment_hint == CommentSentimentHint.NEUTRAL.value),
            unknown_count=sum(1 for record in records if record.sentiment_hint == CommentSentimentHint.UNKNOWN.value),
            conflict_count=sum(1 for record in records if record.sentiment_hint == CommentSentimentHint.CONFLICT.value),
            text_rule_count=sum(
                1
                for record in records
                if record.sentiment_source in {CommentSentimentSource.TEXT_RULE.value, CommentSentimentSource.RAW_TEXT_COMBINED.value}
            ),
        )

    def _apply_atom(self, atom: CommentEvidenceAtomRecord) -> tuple[CommentEvidenceAtomRecord, list[CommentSentimentHintIssue]]:
        raw_sentiment = _normalize_raw_sentiment(atom.sentiment_hint)
        text_sentiment = _text_sentiment(atom.normalized_sentence_text or atom.sentence_text, atom.low_value_reasons)
        final_sentiment, source, conflict_flag = _combine_sentiment(raw_sentiment, text_sentiment)
        confidence = _sentiment_confidence(atom, final_sentiment, source)
        review_required = bool(atom.review_required or conflict_flag)
        review_reason_json = _review_reason(atom, text_sentiment, conflict_flag) if review_required else {}
        issues = []
        if conflict_flag:
            issues.append(
                CommentSentimentHintIssue(
                    issue_code="m05_sentiment_conflict",
                    message_cn="原始情感与文本情感强冲突，需要复核。",
                    comment_evidence_id=atom.comment_evidence_id,
                    review_required=True,
                    blocked=False,
                )
            )
        updated = atom.model_copy(
            update={
                "sentiment_hint": final_sentiment,
                "sentiment_source": source,
                "sentiment_conflict_flag": conflict_flag,
                "confidence": confidence,
                "confidence_level": _confidence_level(confidence),
                "review_required": review_required,
                "review_status": Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
                "review_reason_json": review_reason_json,
                "result_hash": self._result_hash(atom, final_sentiment, source, conflict_flag, confidence, text_sentiment),
            }
        )
        return updated, issues

    def _result_hash(
        self,
        atom: CommentEvidenceAtomRecord,
        final_sentiment: CommentSentimentHint,
        source: CommentSentimentSource,
        conflict_flag: bool,
        confidence: Decimal,
        text_sentiment: _TextSentiment,
    ) -> str:
        return stable_hash(
            {
                "comment_evidence_id": atom.comment_evidence_id,
                "sentence_hash": atom.sentence_hash,
                "previous_result_hash": atom.result_hash,
                "sentiment_hint": final_sentiment.value,
                "sentiment_source": source.value,
                "sentiment_conflict_flag": conflict_flag,
                "matched_text_terms": text_sentiment.matched_terms,
                "confidence": confidence,
                "rule_version": atom.rule_version,
                "asset_version": atom.asset_version,
            },
            version=COMMENT_SENTIMENT_HINT_RESULT_HASH_VERSION,
        )


def _normalize_raw_sentiment(value) -> CommentSentimentHint:
    raw = _enum_value(value).strip().lower()
    if raw in RAW_POSITIVE_VALUES:
        return CommentSentimentHint.POSITIVE
    if raw in RAW_NEGATIVE_VALUES:
        return CommentSentimentHint.NEGATIVE
    if raw in RAW_NEUTRAL_VALUES:
        return CommentSentimentHint.NEUTRAL
    if raw == CommentSentimentHint.CONFLICT.value:
        return CommentSentimentHint.CONFLICT
    return CommentSentimentHint.UNKNOWN


def _text_sentiment(text: str, low_value_reasons: Sequence[str | CommentLowValueReason]) -> _TextSentiment:
    compact_text = _compact_text(text)
    positive_terms = _matched_terms(compact_text, TEXT_POSITIVE_TERMS)
    negative_terms = _matched_terms(compact_text, TEXT_NEGATIVE_TERMS)
    neutral_terms = _matched_terms(compact_text, TEXT_NEUTRAL_TERMS)

    low_value_reason_values = {_enum_value(reason) for reason in low_value_reasons}
    if low_value_reason_values.intersection(LOW_VALUE_POSITIVE_BLOCK_REASONS) and positive_terms and not negative_terms:
        return _TextSentiment(sentiment=CommentSentimentHint.UNKNOWN, matched_terms=[])

    if positive_terms and negative_terms:
        return _TextSentiment(
            sentiment=CommentSentimentHint.CONFLICT,
            matched_terms=sorted(set([*positive_terms, *negative_terms])),
            conflict_flag=True,
        )
    if negative_terms:
        return _TextSentiment(sentiment=CommentSentimentHint.NEGATIVE, matched_terms=negative_terms)
    if positive_terms:
        return _TextSentiment(sentiment=CommentSentimentHint.POSITIVE, matched_terms=positive_terms)
    if neutral_terms:
        return _TextSentiment(sentiment=CommentSentimentHint.NEUTRAL, matched_terms=neutral_terms)
    return _TextSentiment(sentiment=CommentSentimentHint.UNKNOWN, matched_terms=[])


def _combine_sentiment(
    raw_sentiment: CommentSentimentHint,
    text_sentiment: _TextSentiment,
) -> tuple[CommentSentimentHint, CommentSentimentSource, bool]:
    text = text_sentiment.sentiment
    if raw_sentiment == CommentSentimentHint.CONFLICT:
        return CommentSentimentHint.CONFLICT, CommentSentimentSource.RAW_ONLY, True
    if text == CommentSentimentHint.CONFLICT:
        source = CommentSentimentSource.TEXT_RULE if raw_sentiment == CommentSentimentHint.UNKNOWN else CommentSentimentSource.RAW_TEXT_COMBINED
        return CommentSentimentHint.CONFLICT, source, True
    if raw_sentiment == CommentSentimentHint.UNKNOWN and text == CommentSentimentHint.UNKNOWN:
        return CommentSentimentHint.UNKNOWN, CommentSentimentSource.UNKNOWN, False
    if raw_sentiment == CommentSentimentHint.UNKNOWN:
        return text, CommentSentimentSource.TEXT_RULE, False
    if text == CommentSentimentHint.UNKNOWN:
        return raw_sentiment, CommentSentimentSource.RAW_ONLY, False
    if raw_sentiment == text:
        return raw_sentiment, CommentSentimentSource.RAW_TEXT_COMBINED, False
    if raw_sentiment == CommentSentimentHint.NEUTRAL:
        return text, CommentSentimentSource.RAW_TEXT_COMBINED, False
    if text == CommentSentimentHint.NEUTRAL:
        return raw_sentiment, CommentSentimentSource.RAW_TEXT_COMBINED, False
    return CommentSentimentHint.CONFLICT, CommentSentimentSource.RAW_TEXT_COMBINED, True


def _sentiment_confidence(
    atom: CommentEvidenceAtomRecord,
    final_sentiment: CommentSentimentHint,
    source: CommentSentimentSource,
) -> Decimal:
    confidence = atom.confidence
    if source == CommentSentimentSource.TEXT_RULE:
        confidence = min(confidence, Decimal("0.7200"))
    if final_sentiment == CommentSentimentHint.UNKNOWN:
        confidence = min(confidence, Decimal("0.5000"))
    if final_sentiment == CommentSentimentHint.CONFLICT:
        confidence = min(confidence, Decimal("0.4500"))
    if atom.low_value_flag:
        confidence = min(confidence, Decimal("0.3500"))
    return _quantize_confidence(confidence)


def _review_reason(
    atom: CommentEvidenceAtomRecord,
    text_sentiment: _TextSentiment,
    conflict_flag: bool,
) -> dict[str, object]:
    reason_codes = []
    if atom.review_required:
        reason_codes.extend(atom.review_reason_json.get("reason_codes", []))
    if conflict_flag:
        reason_codes.append("sentiment_conflict")
    return {
        "reason_codes": _unique_values(reason_codes),
        "message_cn": "句级情感需要复核，原因来自原始情感与文本规则冲突或上游复核状态。",
        "matched_text_terms": text_sentiment.matched_terms,
        "upstream_review_reason": atom.review_reason_json,
    }


def _matched_terms(compact_text: str, terms: frozenset[str]) -> list[str]:
    lower_text = compact_text.lower()
    return sorted({term for term in terms if _compact_text(term) in lower_text}, key=lambda value: (len(value), value))


def _compact_text(value: str | None) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", (value or "").lower()))


def _unique_values(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return sorted(result)


def _confidence_level(confidence: Decimal) -> Core3ConfidenceLevel:
    if confidence >= Decimal("0.7500"):
        return Core3ConfidenceLevel.HIGH
    if confidence >= Decimal("0.5500"):
        return Core3ConfidenceLevel.MEDIUM
    if confidence > Decimal("0.0000"):
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN


def _quantize_confidence(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
