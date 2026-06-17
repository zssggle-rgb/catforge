"""M05 comment sentence atom builder.

This builder converts comment units into sentence-level M05 evidence atoms. It
does not generate domain hints, topic hints, quality profiles, tasks,
battlefields, competitors, or report conclusions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentSentenceCandidate,
    CommentUnitRecord,
    M05EvidenceInput,
    M05SkuInputBundle,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_RULE_VERSION,
    CommentDomainHint,
    CommentLowValueReason,
    CommentSentimentSource,
    Core3ConfidenceLevel,
    Core3EvidenceType,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_EVIDENCE_ATOM_ID_HASH_VERSION = "m05_comment_evidence_atom_id_v1"
COMMENT_EVIDENCE_ATOM_RESULT_HASH_VERSION = "m05_comment_evidence_atom_result_v1"
COMMENT_SENTENCE_TEXT_HASH_VERSION = "m05_sentence_text_hash_v1"
COMMENT_SENTENCE_DUPLICATE_GROUP_HASH_VERSION = "m05_sentence_duplicate_group_v1"

SENTENCE_SOURCE_SYSTEM_SPLIT = "system_split"
SENTENCE_SOURCE_SOURCE_SEGMENT = "source_segment"
SENTENCE_SOURCE_RAW_FALLBACK = "raw_fallback"

GENERIC_POSITIVE_TEXTS = frozenset({"好", "很好", "不错", "满意", "好评", "可以", "挺好", "还行", "棒"})
PRODUCT_ENTITY_TERMS = frozenset(
    {
        "画质",
        "画面",
        "色彩",
        "亮度",
        "hdr",
        "暗场",
        "对比",
        "音质",
        "音效",
        "系统",
        "广告",
        "接口",
        "hdmi",
        "刷新率",
        "刷新",
        "高刷",
        "延迟",
        "护眼",
        "尺寸",
        "价格",
        "性价比",
    }
)
SERVICE_ENTITY_TERMS = frozenset({"安装", "师傅", "物流", "送货", "配送", "客服", "售后", "服务", "上门"})
EXPERIENCE_TERMS = frozenset(
    {
        "清晰",
        "流畅",
        "不卡",
        "卡顿",
        "不拖影",
        "拖影",
        "刺眼",
        "舒服",
        "划算",
        "贵",
        "值",
        "方便",
        "复杂",
        "好用",
    }
)
SCENARIO_TERMS = frozenset({"游戏", "看球", "球赛", "体育", "老人", "长辈", "孩子", "儿童", "客厅", "卧室", "电影", "主机"})
POLARITY_TERMS = frozenset({"好", "满意", "推荐", "差", "坏", "不满意", "卡", "卡顿", "拖影", "刺眼", "划算", "贵"})
BUSINESS_TERMS = PRODUCT_ENTITY_TERMS | SERVICE_ENTITY_TERMS | EXPERIENCE_TERMS | SCENARIO_TERMS


@dataclass(frozen=True)
class CommentSentenceAtomBuildIssue:
    issue_code: str
    message_cn: str
    comment_unit_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentSentenceAtomBuildResult:
    candidates: list[CommentSentenceCandidate]
    records: list[CommentEvidenceAtomRecord]
    issues: list[CommentSentenceAtomBuildIssue]
    review_required_count: int
    raw_fallback_count: int
    low_value_count: int
    usable_for_downstream_count: int


@dataclass
class _SentenceDraft:
    sentence_hash: str
    sentence_seq: int | None
    sentence_text: str
    normalized_sentence_text: str
    sentence_source_priority: str
    source_sentence_evidence_ids: list[str] = field(default_factory=list)
    source_comment_evidence_ids: list[str] = field(default_factory=list)
    source_dimension_evidence_ids: list[str] = field(default_factory=list)
    source_quality_evidence_ids: list[str] = field(default_factory=list)
    raw_dimension_paths: list[str] = field(default_factory=list)
    base_confidences: list[Decimal] = field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)


class CommentSentenceAtomBuilder:
    def build_atoms(
        self,
        bundle: M05SkuInputBundle,
        comment_units: Sequence[CommentUnitRecord],
        *,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
        asset_version: str = "default",
    ) -> CommentSentenceAtomBuildResult:
        evidence_by_id = {item.evidence_id: item for item in bundle.evidence_inputs}
        candidates: list[CommentSentenceCandidate] = []
        records: list[CommentEvidenceAtomRecord] = []
        issues: list[CommentSentenceAtomBuildIssue] = []

        for unit in sorted(comment_units, key=lambda item: item.comment_unit_id):
            unit_drafts, unit_issues = self._build_unit_drafts(unit, evidence_by_id)
            issues.extend(unit_issues)
            for draft in unit_drafts:
                candidate = self._build_candidate(unit, draft)
                candidates.append(candidate)
                records.append(
                    self._build_record(
                        bundle,
                        unit,
                        draft,
                        candidate,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        asset_version=asset_version,
                    )
                )

        return CommentSentenceAtomBuildResult(
            candidates=candidates,
            records=records,
            issues=issues,
            review_required_count=sum(1 for record in records if record.review_required),
            raw_fallback_count=sum(1 for record in records if record.sentence_source_priority == SENTENCE_SOURCE_RAW_FALLBACK),
            low_value_count=sum(1 for record in records if record.low_value_flag),
            usable_for_downstream_count=sum(1 for record in records if record.usable_for_downstream),
        )

    def _build_unit_drafts(
        self,
        unit: CommentUnitRecord,
        evidence_by_id: dict[str, M05EvidenceInput],
    ) -> tuple[list[_SentenceDraft], list[CommentSentenceAtomBuildIssue]]:
        issues: list[CommentSentenceAtomBuildIssue] = []
        sentence_inputs = [evidence_by_id[evidence_id] for evidence_id in unit.source_sentence_evidence_ids if evidence_id in evidence_by_id]
        drafts_by_hash: dict[str, _SentenceDraft] = {}

        if sentence_inputs:
            for sentence_input in sentence_inputs:
                text = _sentence_text(sentence_input)
                normalized = _normalize_sentence_text(text)
                if not normalized:
                    issues.append(
                        CommentSentenceAtomBuildIssue(
                            issue_code="m05_sentence_empty_source",
                            message_cn="comment_sentence evidence 文本为空，已跳过该句级来源。",
                            comment_unit_id=unit.comment_unit_id,
                            evidence_ids=[sentence_input.evidence_id],
                            review_required=True,
                            blocked=False,
                        )
                    )
                    continue
                sentence_hash = sentence_input.segment_text_hash or stable_hash(
                    normalized,
                    version=COMMENT_SENTENCE_TEXT_HASH_VERSION,
                )
                draft = drafts_by_hash.get(sentence_hash)
                if draft is None:
                    draft = _SentenceDraft(
                        sentence_hash=sentence_hash,
                        sentence_seq=sentence_input.sentence_seq,
                        sentence_text=text.strip(),
                        normalized_sentence_text=normalized,
                        sentence_source_priority=_sentence_source_priority(sentence_input),
                    )
                    drafts_by_hash[sentence_hash] = draft
                else:
                    if len(text.strip()) > len(draft.sentence_text):
                        draft.sentence_text = text.strip()
                        draft.normalized_sentence_text = normalized
                    draft.sentence_seq = _min_optional_int(draft.sentence_seq, sentence_input.sentence_seq)
                    draft.sentence_source_priority = _higher_priority(
                        draft.sentence_source_priority,
                        _sentence_source_priority(sentence_input),
                    )
                draft.source_sentence_evidence_ids.append(sentence_input.evidence_id)
                draft.base_confidences.append(sentence_input.base_confidence)
        else:
            fallback_sentences = self._raw_fallback_sentences(unit, evidence_by_id)
            if not fallback_sentences:
                issues.append(
                    CommentSentenceAtomBuildIssue(
                        issue_code="m05_sentence_missing_text",
                        message_cn="评论单元没有 comment_sentence，也没有可降级切句的 raw 文本，无法生成句级 atom。",
                        comment_unit_id=unit.comment_unit_id,
                        evidence_ids=list(unit.source_comment_evidence_ids),
                        review_required=True,
                        blocked=True,
                    )
                )
            for index, text in enumerate(fallback_sentences):
                normalized = _normalize_sentence_text(text)
                if not normalized:
                    continue
                sentence_hash = stable_hash(normalized, version=COMMENT_SENTENCE_TEXT_HASH_VERSION)
                drafts_by_hash.setdefault(
                    sentence_hash,
                    _SentenceDraft(
                        sentence_hash=sentence_hash,
                        sentence_seq=index,
                        sentence_text=text.strip(),
                        normalized_sentence_text=normalized,
                        sentence_source_priority=SENTENCE_SOURCE_RAW_FALLBACK,
                        review_required=True,
                        review_reasons=["raw_fallback_sentence"],
                    ),
                )

        unit_raw_ids = [evidence_id for evidence_id in unit.source_comment_evidence_ids if evidence_id in evidence_by_id]
        unit_dimension_ids = [evidence_id for evidence_id in unit.source_dimension_evidence_ids if evidence_id in evidence_by_id]
        unit_quality_ids = [evidence_id for evidence_id in unit.source_quality_evidence_ids if evidence_id in evidence_by_id]
        raw_dimension_paths = list(unit.raw_dimension_paths)
        raw_confidences = [evidence_by_id[evidence_id].base_confidence for evidence_id in unit_raw_ids]

        for draft in drafts_by_hash.values():
            draft.source_comment_evidence_ids.extend(unit_raw_ids)
            draft.source_dimension_evidence_ids.extend(unit_dimension_ids)
            draft.source_quality_evidence_ids.extend(unit_quality_ids)
            draft.raw_dimension_paths.extend(raw_dimension_paths)
            draft.base_confidences.extend(raw_confidences)
            draft.source_sentence_evidence_ids = _unique_values(draft.source_sentence_evidence_ids)
            draft.source_comment_evidence_ids = _unique_values(draft.source_comment_evidence_ids)
            draft.source_dimension_evidence_ids = _unique_values(draft.source_dimension_evidence_ids)
            draft.source_quality_evidence_ids = _unique_values(draft.source_quality_evidence_ids)
            draft.raw_dimension_paths = _unique_values(draft.raw_dimension_paths)

        return sorted(
            drafts_by_hash.values(),
            key=lambda draft: (draft.sentence_seq is None, draft.sentence_seq if draft.sentence_seq is not None else 10**9, draft.sentence_hash),
        ), issues

    def _raw_fallback_sentences(
        self,
        unit: CommentUnitRecord,
        evidence_by_id: dict[str, M05EvidenceInput],
    ) -> list[str]:
        raw_texts = []
        for evidence_id in unit.source_comment_evidence_ids:
            evidence_input = evidence_by_id.get(evidence_id)
            if evidence_input is not None:
                raw_texts.extend([evidence_input.text_value or "", evidence_input.clean_value or "", evidence_input.raw_value or ""])
        if unit.canonical_comment_text:
            raw_texts.append(unit.canonical_comment_text)
        normalized = [text.strip() for text in raw_texts if text and text.strip()]
        if not normalized:
            return []
        return _split_sentences(max(normalized, key=len))

    def _build_candidate(self, unit: CommentUnitRecord, draft: _SentenceDraft) -> CommentSentenceCandidate:
        return CommentSentenceCandidate(
            comment_unit_id=unit.comment_unit_id,
            comment_unit_key=unit.comment_unit_key,
            sku_code=unit.sku_code,
            sentence_seq=draft.sentence_seq,
            sentence_hash=draft.sentence_hash,
            sentence_text=draft.sentence_text,
            normalized_sentence_text=draft.normalized_sentence_text,
            sentence_source_priority=draft.sentence_source_priority,
            source_evidence_ids=self._source_evidence_ids(draft),
            raw_dimension_paths=draft.raw_dimension_paths,
        )

    def _build_record(
        self,
        bundle: M05SkuInputBundle,
        unit: CommentUnitRecord,
        draft: _SentenceDraft,
        candidate: CommentSentenceCandidate,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        asset_version: str,
    ) -> CommentEvidenceAtomRecord:
        low_value_reasons = _sentence_low_value_reasons(unit, draft.normalized_sentence_text)
        specificity_score = _specificity_score(draft.normalized_sentence_text, draft.raw_dimension_paths, low_value_reasons)
        usable_for_downstream, downstream_block_reasons = _downstream_usability(
            draft.normalized_sentence_text,
            low_value_reasons,
        )
        confidence = _sentence_confidence(unit, draft, specificity_score, low_value_reasons)
        comment_evidence_key = (
            f"{bundle.project_id}:{bundle.category_code}:{bundle.batch_id}:"
            f"{unit.sku_code}:{unit.comment_unit_id}:{draft.sentence_hash}"
        )
        id_payload = {"comment_evidence_key": comment_evidence_key, "rule_version": rule_version}
        source_evidence_ids = self._source_evidence_ids(draft)
        result_payload = {
            "comment_unit_id": unit.comment_unit_id,
            "sentence_hash": draft.sentence_hash,
            "source_evidence_ids": source_evidence_ids,
            "raw_dimension_paths": draft.raw_dimension_paths,
            "low_value_reasons": [_enum_value(reason) for reason in low_value_reasons],
            "specificity_score": specificity_score,
            "usable_for_downstream": usable_for_downstream,
            "rule_version": rule_version,
            "asset_version": asset_version,
        }
        review_required = bool(unit.review_required or draft.review_required)
        return CommentEvidenceAtomRecord(
            comment_evidence_id=stable_hash(id_payload, version=COMMENT_EVIDENCE_ATOM_ID_HASH_VERSION),
            project_id=unit.project_id,
            category_code=unit.category_code,
            batch_id=unit.batch_id,
            run_id=unit.run_id or run_id,
            module_run_id=unit.module_run_id or module_run_id,
            sku_code=unit.sku_code or bundle.sku_code,
            model_name=unit.model_name or bundle.model_name,
            brand_name=unit.brand_name or bundle.brand_name,
            comment_evidence_key=comment_evidence_key,
            comment_unit_id=unit.comment_unit_id,
            comment_id=unit.comment_id,
            comment_text_hash=unit.comment_text_hash,
            sentence_hash=draft.sentence_hash,
            sentence_seq=draft.sentence_seq,
            sentence_source_priority=draft.sentence_source_priority,
            sentence_text=draft.sentence_text,
            normalized_sentence_text=draft.normalized_sentence_text,
            sentence_length=len(draft.normalized_sentence_text),
            source_evidence_ids=source_evidence_ids,
            source_sentence_evidence_ids=draft.source_sentence_evidence_ids,
            source_comment_evidence_ids=draft.source_comment_evidence_ids,
            source_dimension_evidence_ids=draft.source_dimension_evidence_ids,
            source_quality_evidence_ids=draft.source_quality_evidence_ids,
            raw_dimension_paths=draft.raw_dimension_paths,
            primary_domain_hint=CommentDomainHint.UNKNOWN,
            sentiment_hint=unit.sentiment_hint,
            sentiment_source=CommentSentimentSource.RAW_ONLY if unit.sentiment_hint != "unknown" else CommentSentimentSource.UNKNOWN,
            sentiment_conflict_flag=unit.sentiment_conflict_flag,
            low_value_flag=bool(low_value_reasons),
            low_value_reasons=low_value_reasons,
            duplicate_group_id=unit.duplicate_group_id,
            sentence_duplicate_group_id=stable_hash(
                {
                    "project_id": unit.project_id,
                    "category_code": unit.category_code,
                    "batch_id": unit.batch_id,
                    "sku_code": unit.sku_code,
                    "sentence_hash": draft.sentence_hash,
                },
                version=COMMENT_SENTENCE_DUPLICATE_GROUP_HASH_VERSION,
            ),
            specificity_score=specificity_score,
            representative_phrase=_representative_phrase(draft.normalized_sentence_text),
            representative_phrase_rule="business_term_window",
            usable_for_downstream=usable_for_downstream,
            downstream_block_reasons=downstream_block_reasons,
            confidence=confidence,
            confidence_level=_confidence_level(confidence),
            rule_version=rule_version,
            asset_version=asset_version,
            input_fingerprint=unit.input_fingerprint or bundle.input_fingerprint,
            result_hash=stable_hash(result_payload, version=COMMENT_EVIDENCE_ATOM_RESULT_HASH_VERSION),
            review_required=review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
            review_reason_json=_review_reason(unit, draft) if review_required else {},
        )

    def _source_evidence_ids(self, draft: _SentenceDraft) -> list[str]:
        return _unique_values(
            [
                *draft.source_sentence_evidence_ids,
                *draft.source_comment_evidence_ids,
                *draft.source_dimension_evidence_ids,
                *draft.source_quality_evidence_ids,
            ]
        )


def _sentence_text(sentence_input: M05EvidenceInput) -> str:
    candidates = [sentence_input.text_value or "", sentence_input.clean_value or "", sentence_input.raw_value or ""]
    normalized = [text.strip() for text in candidates if text and text.strip()]
    return max(normalized, key=len) if normalized else ""


def _sentence_source_priority(sentence_input: M05EvidenceInput) -> str:
    payload = sentence_input.evidence_payload_json or {}
    explicit_priority = payload.get("sentence_source_priority")
    if explicit_priority in {SENTENCE_SOURCE_SYSTEM_SPLIT, SENTENCE_SOURCE_SOURCE_SEGMENT, SENTENCE_SOURCE_RAW_FALLBACK}:
        return str(explicit_priority)
    source = str(payload.get("source") or payload.get("source_type") or "").lower()
    if source in {"comments_segments", "source_segment", "raw_segment"}:
        return SENTENCE_SOURCE_SOURCE_SEGMENT
    if str(sentence_input.evidence_field or "").startswith("comment_segment"):
        return SENTENCE_SOURCE_SOURCE_SEGMENT
    return SENTENCE_SOURCE_SYSTEM_SPLIT


def _higher_priority(left: str, right: str) -> str:
    priority = {
        SENTENCE_SOURCE_SYSTEM_SPLIT: 0,
        SENTENCE_SOURCE_SOURCE_SEGMENT: 1,
        SENTENCE_SOURCE_RAW_FALLBACK: 2,
    }
    return left if priority[left] <= priority[right] else right


def _sentence_low_value_reasons(
    unit: CommentUnitRecord,
    normalized_sentence_text: str,
) -> list[CommentLowValueReason | str]:
    reasons: set[CommentLowValueReason | str] = set(unit.low_value_reasons)
    compact_text = _compact_text(normalized_sentence_text)
    if not compact_text:
        reasons.add(CommentLowValueReason.PUNCTUATION_ONLY)
    if compact_text in GENERIC_POSITIVE_TEXTS:
        reasons.add(CommentLowValueReason.TOO_SHORT_GENERIC)
    if compact_text and len(compact_text) < 4 and not _contains_any(compact_text, BUSINESS_TERMS):
        reasons.add(CommentLowValueReason.TOO_SHORT_GENERIC)
    return sorted(reasons, key=_enum_value)


def _downstream_usability(
    normalized_sentence_text: str,
    low_value_reasons: Sequence[CommentLowValueReason | str],
) -> tuple[bool, list[str]]:
    if low_value_reasons:
        return False, ["low_value_sentence"]
    compact_text = _compact_text(normalized_sentence_text)
    if len(compact_text) < 4 and not _contains_any(compact_text, BUSINESS_TERMS):
        return False, ["too_short_generic"]
    return True, []


def _specificity_score(
    normalized_sentence_text: str,
    raw_dimension_paths: Sequence[str],
    low_value_reasons: Sequence[CommentLowValueReason | str],
) -> Decimal:
    compact_text = _compact_text(normalized_sentence_text)
    length = len(compact_text)
    if 8 <= length <= 60:
        length_score = Decimal("1.0000")
    elif 4 <= length < 8:
        length_score = Decimal("0.6000")
    elif length > 60:
        length_score = Decimal("0.7500")
    else:
        length_score = Decimal("0.1500")

    entity_term_score = Decimal("1.0000") if _contains_any(compact_text, PRODUCT_ENTITY_TERMS | SERVICE_ENTITY_TERMS) else Decimal("0.0000")
    experience_term_score = Decimal("1.0000") if _contains_any(compact_text, EXPERIENCE_TERMS) else Decimal("0.0000")
    scenario_term_score = Decimal("1.0000") if _contains_any(compact_text, SCENARIO_TERMS) else Decimal("0.0000")
    polarity_specific_score = Decimal("1.0000") if _contains_any(compact_text, POLARITY_TERMS) else Decimal("0.0000")
    dimension_support_score = Decimal("1.0000") if raw_dimension_paths else Decimal("0.0000")
    generic_penalty = Decimal("1.0000") if compact_text in GENERIC_POSITIVE_TEXTS else Decimal("0.0000")
    low_value_penalty = Decimal("1.0000") if low_value_reasons else Decimal("0.0000")

    score = (
        Decimal("0.20") * length_score
        + Decimal("0.25") * entity_term_score
        + Decimal("0.20") * experience_term_score
        + Decimal("0.15") * scenario_term_score
        + Decimal("0.10") * polarity_specific_score
        + Decimal("0.10") * dimension_support_score
        - Decimal("0.30") * generic_penalty
        - Decimal("0.40") * low_value_penalty
    )
    return _quantize_score(min(Decimal("1.0000"), max(Decimal("0.0000"), score)))


def _sentence_confidence(
    unit: CommentUnitRecord,
    draft: _SentenceDraft,
    specificity_score: Decimal,
    low_value_reasons: Sequence[CommentLowValueReason | str],
) -> Decimal:
    base_candidates = [unit.confidence, *draft.base_confidences]
    base = max([value for value in base_candidates if value is not None], default=Decimal("0.0000"))
    confidence = min(Decimal("1.0000"), base * Decimal("0.80") + specificity_score * Decimal("0.20"))
    if draft.sentence_source_priority == SENTENCE_SOURCE_RAW_FALLBACK:
        confidence -= Decimal("0.1000")
    if low_value_reasons:
        confidence = min(confidence, Decimal("0.3500"))
    return _quantize_score(max(Decimal("0.0000"), confidence))


def _representative_phrase(normalized_sentence_text: str) -> str | None:
    for term_set in (SCENARIO_TERMS, PRODUCT_ENTITY_TERMS, EXPERIENCE_TERMS, SERVICE_ENTITY_TERMS):
        for term in sorted(term_set, key=len, reverse=True):
            position = normalized_sentence_text.lower().find(term.lower())
            if position >= 0:
                start = max(0, position - 4)
                end = min(len(normalized_sentence_text), position + len(term) + 8)
                return normalized_sentence_text[start:end]
    return normalized_sentence_text[:18] if normalized_sentence_text else None


def _review_reason(unit: CommentUnitRecord, draft: _SentenceDraft) -> dict[str, object]:
    reason_codes = list(draft.review_reasons)
    if unit.review_required:
        reason_codes.append("source_unit_review_required")
    return {
        "reason_codes": _unique_values(reason_codes),
        "message_cn": "句级评论证据需要复核，原因来自 raw 降级切句或来源评论单元复核状态。",
        "unit_review_reason": unit.review_reason_json,
    }


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n\r]+", text)
    return [part.strip(" ，,、\t") for part in parts if part and part.strip(" ，,、\t")]


def _normalize_sentence_text(text: str) -> str:
    stripped = re.sub(r"\s+", " ", text.strip())
    return stripped.strip(" ，,、\t")


def _compact_text(value: str) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", value.lower()))


def _contains_any(value: str, terms: frozenset[str]) -> bool:
    lower_value = value.lower()
    return any(term.lower() in lower_value for term in terms)


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


def _min_optional_int(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _quantize_score(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
