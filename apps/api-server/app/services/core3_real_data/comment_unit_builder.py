"""M05 comment unit builder.

This builder consumes typed M05 evidence inputs and creates deduplicated comment
unit records. It intentionally stops before evidence links, sentence atoms,
topic hints, quality profiles, tasks, battlefields, competitors, and reports.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentUnitCandidate,
    CommentUnitRecord,
    M05EvidenceInput,
    M05SkuInputBundle,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_RULE_VERSION,
    CommentDedupStrategy,
    CommentLowValueReason,
    CommentSentimentHint,
    CommentUnitStatus,
    Core3ConfidenceLevel,
    Core3EvidenceType,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_UNIT_ID_HASH_VERSION = "m05_comment_unit_id_v1"
COMMENT_UNIT_RESULT_HASH_VERSION = "m05_comment_unit_result_v1"
COMMENT_DUPLICATE_GROUP_HASH_VERSION = "m05_comment_duplicate_group_v1"

DEFAULT_POSITIVE_PATTERNS = (
    "此用户没有填写评价",
    "默认好评",
    "系统默认好评",
    "此用户未填写评价",
    "用户没有填写评价",
)
GENERIC_POSITIVE_TEXTS = frozenset({"好", "很好", "不错", "满意", "好评", "可以", "挺好", "还行", "棒"})
PRODUCT_TERMS = frozenset(
    {
        "画质",
        "画面",
        "色彩",
        "清晰",
        "亮度",
        "hdr",
        "暗场",
        "对比",
        "游戏",
        "高刷",
        "刷新",
        "延迟",
        "流畅",
        "音质",
        "音效",
        "系统",
        "广告",
        "接口",
        "hdmi",
        "护眼",
        "尺寸",
        "客厅",
        "价格",
        "性价比",
        "划算",
        "做工",
        "质量",
    }
)
SERVICE_TERMS = frozenset({"安装", "师傅", "送货", "物流", "售后", "客服", "服务", "上门", "配送"})
POSITIVE_SENTIMENT_VALUES = frozenset({"positive", "pos", "正面", "好评", "满意", "推荐"})
NEGATIVE_SENTIMENT_VALUES = frozenset({"negative", "neg", "负面", "差评", "不满意"})
NEUTRAL_SENTIMENT_VALUES = frozenset({"neutral", "中性", "一般"})
LOW_VALUE_QUALITY_FLAGS = frozenset(
    {
        "low_value_comment",
        "duplicate_comment_text",
        "comment_text_empty",
        "comment_text_too_short",
        "default_positive",
    }
)


@dataclass(frozen=True)
class CommentUnitBuildIssue:
    issue_code: str
    message_cn: str
    evidence_ids: list[str] = field(default_factory=list)
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentUnitBuildResult:
    candidates: list[CommentUnitCandidate]
    records: list[CommentUnitRecord]
    skipped_evidence_ids: list[str]
    issues: list[CommentUnitBuildIssue]
    review_required_count: int
    low_value_count: int


@dataclass(frozen=True)
class _DedupDecision:
    unit_key: str
    strategy: CommentDedupStrategy
    penalty: Decimal
    review_required: bool


class CommentUnitBuilder:
    def __init__(self, *, duplicate_text_threshold: int = 3) -> None:
        if duplicate_text_threshold < 1:
            raise ValueError("duplicate_text_threshold must be >= 1")
        self.duplicate_text_threshold = duplicate_text_threshold

    def build_units(
        self,
        bundle: M05SkuInputBundle,
        *,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
        asset_version: str = "default",
    ) -> CommentUnitBuildResult:
        duplicate_text_counts = self._duplicate_text_counts(bundle.evidence_inputs)
        grouped_inputs: dict[str, list[M05EvidenceInput]] = defaultdict(list)
        decisions: dict[str, _DedupDecision] = {}
        skipped_evidence_ids: list[str] = []
        issues: list[CommentUnitBuildIssue] = []

        for evidence_input in bundle.evidence_inputs:
            decision = self._dedup_decision(bundle, evidence_input)
            if decision is None:
                skipped_evidence_ids.append(evidence_input.evidence_id)
                issues.append(
                    CommentUnitBuildIssue(
                        issue_code="m05_unit_missing_trace",
                        message_cn="评论 evidence 缺少 comment_id、comment_text_hash 和 source_row_id，无法生成评论单元。",
                        evidence_ids=[evidence_input.evidence_id],
                        review_required=True,
                        blocked=True,
                    )
                )
                continue
            grouped_inputs[decision.unit_key].append(evidence_input)
            decisions.setdefault(decision.unit_key, decision)

        candidates: list[CommentUnitCandidate] = []
        records: list[CommentUnitRecord] = []
        for unit_key in sorted(grouped_inputs):
            unit_inputs = grouped_inputs[unit_key]
            decision = decisions[unit_key]
            candidate = self._build_candidate(
                bundle,
                unit_key,
                decision,
                unit_inputs,
                duplicate_text_counts,
            )
            candidates.append(candidate)
            records.append(
                self._build_record(
                    bundle,
                    unit_key,
                    decision,
                    unit_inputs,
                    candidate,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    asset_version=asset_version,
                )
            )

        return CommentUnitBuildResult(
            candidates=candidates,
            records=records,
            skipped_evidence_ids=sorted(skipped_evidence_ids),
            issues=issues,
            review_required_count=sum(1 for record in records if record.review_required),
            low_value_count=sum(1 for record in records if record.low_value_flag),
        )

    def _dedup_decision(self, bundle: M05SkuInputBundle, item: M05EvidenceInput) -> _DedupDecision | None:
        prefix = f"{bundle.project_id}:{bundle.category_code}:{bundle.batch_id}:{bundle.sku_code}"
        if item.comment_id:
            return _DedupDecision(
                unit_key=f"{prefix}:comment_id:{item.comment_id}",
                strategy=CommentDedupStrategy.COMMENT_ID,
                penalty=Decimal("0.0000"),
                review_required=False,
            )
        if item.comment_text_hash:
            return _DedupDecision(
                unit_key=f"{prefix}:text_hash:{item.comment_text_hash}",
                strategy=CommentDedupStrategy.TEXT_HASH,
                penalty=Decimal("0.0800"),
                review_required=False,
            )
        if item.source_row_id:
            return _DedupDecision(
                unit_key=f"{prefix}:source_row_id:{item.source_row_id}",
                strategy=CommentDedupStrategy.SOURCE_ROW_FALLBACK,
                penalty=Decimal("0.2500"),
                review_required=True,
            )
        return None

    def _build_candidate(
        self,
        bundle: M05SkuInputBundle,
        unit_key: str,
        decision: _DedupDecision,
        unit_inputs: Sequence[M05EvidenceInput],
        duplicate_text_counts: Counter[str],
    ) -> CommentUnitCandidate:
        text = self._canonical_comment_text(unit_inputs)
        low_value_reasons = self._low_value_reasons(unit_inputs, text, duplicate_text_counts)
        confidence = self._unit_confidence(unit_inputs, decision.penalty, low_value_reasons)
        return CommentUnitCandidate(
            sku_code=bundle.sku_code,
            model_name=bundle.model_name,
            brand_name=bundle.brand_name,
            dedup_strategy=decision.strategy,
            comment_id=self._first_non_empty(item.comment_id for item in unit_inputs),
            comment_text_hash=self._first_non_empty(item.comment_text_hash for item in unit_inputs),
            source_row_ids=self._unique_values(item.source_row_id for item in unit_inputs),
            canonical_comment_text=text,
            source_evidence_ids=self._unique_values(item.evidence_id for item in unit_inputs),
            raw_dimension_paths=self._unique_values(item.dimension_path_raw for item in unit_inputs),
            sentiment_hint=self._sentiment_hint(unit_inputs)[0],
            low_value_flag=bool(low_value_reasons),
            low_value_reasons=low_value_reasons,
            confidence=confidence,
        )

    def _build_record(
        self,
        bundle: M05SkuInputBundle,
        unit_key: str,
        decision: _DedupDecision,
        unit_inputs: Sequence[M05EvidenceInput],
        candidate: CommentUnitCandidate,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        asset_version: str,
    ) -> CommentUnitRecord:
        sentiment_hint, sentiment_raw_set, sentiment_conflict_flag = self._sentiment_hint(unit_inputs)
        text_hash = candidate.comment_text_hash
        duplicate_group_id = (
            stable_hash(
                {
                    "project_id": bundle.project_id,
                    "category_code": bundle.category_code,
                    "batch_id": bundle.batch_id,
                    "sku_code": bundle.sku_code,
                    "comment_text_hash": text_hash,
                },
                version=COMMENT_DUPLICATE_GROUP_HASH_VERSION,
            )
            if text_hash
            else None
        )
        source_comment_ids = self._evidence_ids_by_type(unit_inputs, Core3EvidenceType.COMMENT_RAW)
        source_sentence_ids = self._evidence_ids_by_type(unit_inputs, Core3EvidenceType.COMMENT_SENTENCE)
        source_dimension_ids = self._evidence_ids_by_type(unit_inputs, Core3EvidenceType.COMMENT_DIMENSION)
        source_quality_ids = self._evidence_ids_by_type(unit_inputs, Core3EvidenceType.QUALITY_ISSUE)
        quality_flags = self._unique_values(flag for item in unit_inputs for flag in item.quality_flags)
        low_value_flag = candidate.low_value_flag
        review_required = decision.review_required
        confidence = candidate.confidence
        comment_unit_id = stable_hash(
            {"comment_unit_key": unit_key, "rule_version": rule_version},
            version=COMMENT_UNIT_ID_HASH_VERSION,
        )
        result_hash = stable_hash(
            {
                "comment_unit_key": unit_key,
                "source_evidence_ids": candidate.source_evidence_ids,
                "low_value_reasons": [_enum_value(reason) for reason in candidate.low_value_reasons],
                "sentiment_hint": sentiment_hint.value,
                "confidence": confidence,
                "rule_version": rule_version,
                "asset_version": asset_version,
            },
            version=COMMENT_UNIT_RESULT_HASH_VERSION,
        )
        return CommentUnitRecord(
            comment_unit_id=comment_unit_id,
            project_id=bundle.project_id,
            category_code=bundle.category_code,
            batch_id=bundle.batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=bundle.sku_code,
            model_name=bundle.model_name,
            brand_name=bundle.brand_name,
            comment_unit_key=unit_key,
            dedup_strategy=decision.strategy,
            comment_id=candidate.comment_id,
            comment_text_hash=candidate.comment_text_hash,
            source_row_id=candidate.source_row_ids[0] if candidate.source_row_ids else None,
            canonical_comment_text=candidate.canonical_comment_text,
            canonical_text_length=len(candidate.canonical_comment_text or ""),
            source_row_count=len(candidate.source_row_ids),
            source_sentence_count=len(source_sentence_ids),
            source_dimension_count=len(source_dimension_ids),
            source_quality_issue_count=len(source_quality_ids),
            source_comment_evidence_ids=source_comment_ids,
            source_sentence_evidence_ids=source_sentence_ids,
            source_dimension_evidence_ids=source_dimension_ids,
            source_quality_evidence_ids=source_quality_ids,
            raw_dimension_paths=candidate.raw_dimension_paths,
            sentiment_raw_set=sentiment_raw_set,
            sentiment_hint=sentiment_hint,
            sentiment_conflict_flag=sentiment_conflict_flag,
            low_value_flag=low_value_flag,
            low_value_reasons=candidate.low_value_reasons,
            duplicate_group_id=duplicate_group_id,
            duplicate_source_count=self._duplicate_source_count(unit_inputs),
            comment_unit_status=CommentUnitStatus.LOW_VALUE if low_value_flag else CommentUnitStatus.USABLE,
            quality_flags=quality_flags,
            confidence=confidence,
            confidence_level=self._confidence_level(confidence),
            rule_version=rule_version,
            asset_version=asset_version,
            input_fingerprint=bundle.input_fingerprint,
            result_hash=result_hash,
            review_required=review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
            review_reason_json=self._review_reason(decision),
        )

    def _canonical_comment_text(self, unit_inputs: Sequence[M05EvidenceInput]) -> str | None:
        raw_candidates: list[str] = []
        for item in unit_inputs:
            if item.evidence_type == Core3EvidenceType.COMMENT_RAW.value:
                raw_candidates.extend([item.text_value or "", item.clean_value or "", item.raw_value or ""])
        normalized_raw = [value.strip() for value in raw_candidates if value and value.strip()]
        if normalized_raw:
            return max(normalized_raw, key=len)

        candidates: list[str] = []
        for item in unit_inputs:
            candidates.extend([item.text_value or "", item.clean_value or "", item.raw_value or ""])
        normalized = [value.strip() for value in candidates if value and value.strip()]
        if not normalized:
            return None
        return max(normalized, key=len)

    def _low_value_reasons(
        self,
        unit_inputs: Sequence[M05EvidenceInput],
        text: str | None,
        duplicate_text_counts: Counter[str],
    ) -> list[CommentLowValueReason]:
        reasons: set[CommentLowValueReason] = set()
        normalized_text = (text or "").strip()
        compact_text = _compact_text(normalized_text)
        if not normalized_text:
            reasons.add(CommentLowValueReason.EMPTY_TEXT)
        if normalized_text and not compact_text:
            reasons.add(CommentLowValueReason.PUNCTUATION_ONLY)
        if any(pattern in normalized_text for pattern in DEFAULT_POSITIVE_PATTERNS):
            reasons.add(CommentLowValueReason.DEFAULT_POSITIVE)
        if compact_text and len(compact_text) < 4 and not _contains_any(compact_text, PRODUCT_TERMS | SERVICE_TERMS):
            reasons.add(CommentLowValueReason.TOO_SHORT_GENERIC)
        if compact_text in GENERIC_POSITIVE_TEXTS:
            reasons.add(CommentLowValueReason.TOO_SHORT_GENERIC)
        comment_text_hash = self._first_non_empty(item.comment_text_hash for item in unit_inputs)
        if comment_text_hash and duplicate_text_counts[comment_text_hash] > self.duplicate_text_threshold:
            reasons.add(CommentLowValueReason.TEMPLATE_DUPLICATE)
        quality_flags = set(self._unique_values(flag for item in unit_inputs for flag in item.quality_flags))
        quality_fields = {str(item.evidence_field or "") for item in unit_inputs if item.evidence_type == Core3EvidenceType.QUALITY_ISSUE.value}
        if quality_flags.intersection(LOW_VALUE_QUALITY_FLAGS) or quality_fields.intersection(LOW_VALUE_QUALITY_FLAGS):
            reasons.add(CommentLowValueReason.QUALITY_ISSUE_FLAGGED)
        if compact_text and _contains_any(compact_text, SERVICE_TERMS) and not _contains_any(compact_text, PRODUCT_TERMS):
            reasons.add(CommentLowValueReason.SERVICE_ONLY_FOR_PRODUCT_USE)
        return sorted(reasons, key=lambda reason: reason.value)

    def _sentiment_hint(
        self,
        unit_inputs: Sequence[M05EvidenceInput],
    ) -> tuple[CommentSentimentHint, list[str], bool]:
        raw_values = self._sentiment_raw_values(unit_inputs)
        normalized_values = {_normalize_sentiment_value(value) for value in raw_values}
        normalized_values.discard(None)
        if CommentSentimentHint.POSITIVE in normalized_values and CommentSentimentHint.NEGATIVE in normalized_values:
            return CommentSentimentHint.CONFLICT, raw_values, True
        if CommentSentimentHint.NEGATIVE in normalized_values:
            return CommentSentimentHint.NEGATIVE, raw_values, False
        if CommentSentimentHint.POSITIVE in normalized_values:
            return CommentSentimentHint.POSITIVE, raw_values, False
        if CommentSentimentHint.NEUTRAL in normalized_values:
            return CommentSentimentHint.NEUTRAL, raw_values, False
        return CommentSentimentHint.UNKNOWN, raw_values, False

    def _sentiment_raw_values(self, unit_inputs: Sequence[M05EvidenceInput]) -> list[str]:
        values: list[str] = []
        for item in unit_inputs:
            payload = item.evidence_payload_json or {}
            for key in ("sentiment_clean", "sentiment_raw", "sentiment", "sentiment_hint"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
        return self._unique_values(values)

    def _unit_confidence(
        self,
        unit_inputs: Sequence[M05EvidenceInput],
        dedup_penalty: Decimal,
        low_value_reasons: Sequence[CommentLowValueReason],
    ) -> Decimal:
        base_confidences = [item.base_confidence for item in unit_inputs if item.base_confidence is not None]
        base = max(base_confidences) if base_confidences else Decimal("0.0000")
        confidence = max(Decimal("0.0000"), base - dedup_penalty)
        if low_value_reasons:
            confidence = min(confidence, Decimal("0.3500"))
        return _quantize_confidence(confidence)

    def _duplicate_text_counts(self, inputs: Sequence[M05EvidenceInput]) -> Counter[str]:
        counts: Counter[str] = Counter()
        seen_per_comment_source: set[tuple[str, str]] = set()
        for item in inputs:
            if not item.comment_text_hash:
                continue
            source_key = item.comment_id or item.source_row_id or item.evidence_id
            key = (item.comment_text_hash, source_key)
            if key in seen_per_comment_source:
                continue
            counts.update([item.comment_text_hash])
            seen_per_comment_source.add(key)
        return counts

    def _duplicate_source_count(self, unit_inputs: Sequence[M05EvidenceInput]) -> int:
        source_rows = self._unique_values(item.source_row_id for item in unit_inputs)
        return len(source_rows)

    def _evidence_ids_by_type(self, unit_inputs: Sequence[M05EvidenceInput], evidence_type: Core3EvidenceType) -> list[str]:
        return self._unique_values(item.evidence_id for item in unit_inputs if item.evidence_type == evidence_type.value)

    def _confidence_level(self, confidence: Decimal) -> Core3ConfidenceLevel:
        if confidence >= Decimal("0.7500"):
            return Core3ConfidenceLevel.HIGH
        if confidence >= Decimal("0.5500"):
            return Core3ConfidenceLevel.MEDIUM
        if confidence > Decimal("0.0000"):
            return Core3ConfidenceLevel.LOW
        return Core3ConfidenceLevel.UNKNOWN

    def _review_reason(self, decision: _DedupDecision) -> dict[str, object]:
        if not decision.review_required:
            return {}
        return {
            "reason_codes": ["source_row_fallback"],
            "message_cn": "评论缺少 comment_id 和 comment_text_hash，已用 source_row_id 降级生成评论单元。",
        }

    def _first_non_empty(self, values) -> str | None:
        for value in values:
            if value:
                return str(value)
        return None

    def _unique_values(self, values) -> list[str]:
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


def _normalize_sentiment_value(value: str) -> CommentSentimentHint | None:
    normalized = value.strip().lower()
    if normalized in POSITIVE_SENTIMENT_VALUES:
        return CommentSentimentHint.POSITIVE
    if normalized in NEGATIVE_SENTIMENT_VALUES:
        return CommentSentimentHint.NEGATIVE
    if normalized in NEUTRAL_SENTIMENT_VALUES:
        return CommentSentimentHint.NEUTRAL
    return None


def _compact_text(value: str) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", value.lower()))


def _contains_any(value: str, terms: set[str]) -> bool:
    lower_value = value.lower()
    return any(term.lower() in lower_value for term in terms)


def _quantize_confidence(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
