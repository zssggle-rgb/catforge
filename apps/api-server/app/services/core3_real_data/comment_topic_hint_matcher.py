"""M05 weak topic hint matcher.

The matcher consumes M05 sentence atoms and the validated TV comment-topic seed.
It produces weak topic hints only. It does not create user tasks, target groups,
battlefields, competitors, scores, selections, or report conclusions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentTopicSeed,
    CommentTopicSeedIndex,
    TopicHintRecord,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_RULE_VERSION,
    CommentDomainHint,
    CommentSentimentHint,
    CommentTopicHintStatus,
    CommentTopicMatchMethod,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_TOPIC_HINT_ID_HASH_VERSION = "m05_comment_topic_hint_id_v1"
COMMENT_TOPIC_HINT_RESULT_HASH_VERSION = "m05_comment_topic_hint_result_v1"

MATCHED_THRESHOLD = Decimal("0.7500")
LOW_CONFIDENCE_THRESHOLD = Decimal("0.5000")
PRODUCT_DOMAINS = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value,
    CommentDomainHint.PRODUCT_RISK.value,
    CommentDomainHint.MARKET_PERCEPTION.value,
}
SERVICE_DOMAINS = {
    CommentDomainHint.SERVICE_EXPERIENCE.value,
    CommentDomainHint.LOGISTICS_INSTALLATION.value,
}


@dataclass(frozen=True)
class CommentTopicHintIssue:
    issue_code: str
    message_cn: str
    comment_evidence_id: str | None = None
    topic_code: str | None = None
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentTopicHintMatchResult:
    records: list[TopicHintRecord]
    issues: list[CommentTopicHintIssue] = field(default_factory=list)
    matched_count: int = 0
    low_confidence_count: int = 0
    blocked_low_value_count: int = 0
    blocked_service_guardrail_count: int = 0
    unknown_atom_count: int = 0


@dataclass(frozen=True)
class _TopicMatch:
    topic: CommentTopicSeed
    match_method: CommentTopicMatchMethod
    matched_terms: list[str]
    matched_terms_by_source: dict[str, list[str]]
    polarity_hint: CommentSentimentHint
    keyword_match_score: Decimal
    polarity_match_score: Decimal
    domain_consistency_score: Decimal
    dimension_support_score: Decimal
    low_value_penalty: Decimal
    service_product_conflict_penalty: Decimal
    topic_confidence: Decimal
    topic_hint_status: CommentTopicHintStatus


class CommentTopicHintMatcher:
    def match_topic_hints(
        self,
        seed: CommentTopicSeedIndex,
        atoms: Sequence[CommentEvidenceAtomRecord],
        *,
        rule_version: str = CORE3_M05_RULE_VERSION,
        asset_version: str = "default",
    ) -> CommentTopicHintMatchResult:
        records: list[TopicHintRecord] = []
        unknown_atom_count = 0
        for atom in atoms:
            atom_records = self._match_atom(seed, atom, rule_version=rule_version, asset_version=asset_version)
            if not atom_records:
                unknown_atom_count += 1
            records.extend(atom_records)

        return CommentTopicHintMatchResult(
            records=sorted(records, key=lambda item: (item.comment_evidence_id, item.topic_code)),
            matched_count=sum(1 for record in records if record.topic_hint_status == CommentTopicHintStatus.MATCHED.value),
            low_confidence_count=sum(
                1 for record in records if record.topic_hint_status == CommentTopicHintStatus.LOW_CONFIDENCE.value
            ),
            blocked_low_value_count=sum(
                1 for record in records if record.topic_hint_status == CommentTopicHintStatus.BLOCKED_LOW_VALUE.value
            ),
            blocked_service_guardrail_count=sum(
                1 for record in records if record.topic_hint_status == CommentTopicHintStatus.BLOCKED_SERVICE_GUARDRAIL.value
            ),
            unknown_atom_count=unknown_atom_count,
        )

    def _match_atom(
        self,
        seed: CommentTopicSeedIndex,
        atom: CommentEvidenceAtomRecord,
        *,
        rule_version: str,
        asset_version: str,
    ) -> list[TopicHintRecord]:
        matches = []
        for topic in seed.topics:
            topic_match = self._match_topic(atom, topic)
            if topic_match is None:
                continue
            matches.append(
                self._build_record(
                    atom,
                    topic_match,
                    rule_version=rule_version,
                    asset_version=asset_version,
                )
            )
        return matches

    def _match_topic(self, atom: CommentEvidenceAtomRecord, topic: CommentTopicSeed) -> _TopicMatch | None:
        text = _compact_text(atom.normalized_sentence_text or atom.sentence_text)
        negative_terms = _matched_terms(text, topic.negative_keywords)
        positive_terms = _matched_terms(text, topic.positive_keywords)
        keyword_terms = _matched_terms(text, topic.keywords)
        alias_terms = _matched_terms(text, topic.aliases)

        # Dimension paths only support confidence; they must not create a topic alone.
        dimension_terms = _matched_dimension_terms(atom.raw_dimension_paths, topic.dimension_paths)
        if not (negative_terms or positive_terms or keyword_terms or alias_terms):
            return None

        if negative_terms:
            match_method = CommentTopicMatchMethod.NEGATIVE_KEYWORD
            matched_terms = negative_terms
            polarity_hint = CommentSentimentHint.NEGATIVE
            source_key = "negative_keywords"
        elif positive_terms:
            match_method = CommentTopicMatchMethod.POSITIVE_KEYWORD
            matched_terms = positive_terms
            polarity_hint = CommentSentimentHint.POSITIVE
            source_key = "positive_keywords"
        elif keyword_terms:
            match_method = CommentTopicMatchMethod.KEYWORD
            matched_terms = keyword_terms
            polarity_hint = _polarity_from_atom(atom)
            source_key = "keywords"
        else:
            match_method = CommentTopicMatchMethod.PHRASE
            matched_terms = alias_terms
            polarity_hint = _polarity_from_atom(atom)
            source_key = "aliases"

        keyword_match_score = _keyword_match_score(matched_terms, keyword_terms, alias_terms, positive_terms, negative_terms)
        polarity_match_score = _polarity_match_score(atom, polarity_hint)
        domain_consistency_score = _domain_consistency_score(atom, topic)
        dimension_support_score = Decimal("1.0000") if dimension_terms else Decimal("0.0000")
        low_value_penalty = Decimal("1.0000") if atom.low_value_flag else Decimal("0.0000")
        service_product_conflict_penalty = _service_product_conflict_penalty(atom, topic)
        topic_confidence = _topic_confidence(
            keyword_match_score=keyword_match_score,
            polarity_match_score=polarity_match_score,
            domain_consistency_score=domain_consistency_score,
            dimension_support_score=dimension_support_score,
            specificity_score=atom.specificity_score,
            low_value_penalty=low_value_penalty,
            service_product_conflict_penalty=service_product_conflict_penalty,
        )
        topic_hint_status = _topic_status(atom, topic, topic_confidence, service_product_conflict_penalty)
        if topic_hint_status is None:
            return None

        matched_terms_by_source = {
            source_key: matched_terms,
            "keywords": keyword_terms,
            "aliases": alias_terms,
            "positive_keywords": positive_terms,
            "negative_keywords": negative_terms,
            "dimension_paths": dimension_terms,
        }
        matched_terms_by_source = {key: values for key, values in matched_terms_by_source.items() if values}
        return _TopicMatch(
            topic=topic,
            match_method=match_method,
            matched_terms=_unique_values([*matched_terms, *dimension_terms]),
            matched_terms_by_source=matched_terms_by_source,
            polarity_hint=polarity_hint,
            keyword_match_score=keyword_match_score,
            polarity_match_score=polarity_match_score,
            domain_consistency_score=domain_consistency_score,
            dimension_support_score=dimension_support_score,
            low_value_penalty=low_value_penalty,
            service_product_conflict_penalty=service_product_conflict_penalty,
            topic_confidence=topic_confidence,
            topic_hint_status=topic_hint_status,
        )

    def _build_record(
        self,
        atom: CommentEvidenceAtomRecord,
        match: _TopicMatch,
        *,
        rule_version: str,
        asset_version: str,
    ) -> TopicHintRecord:
        topic = match.topic
        topic_hint_id = stable_hash(
            {
                "comment_evidence_id": atom.comment_evidence_id,
                "topic_code": topic.topic_code,
                "rule_version": rule_version,
            },
            version=COMMENT_TOPIC_HINT_ID_HASH_VERSION,
        )
        result_hash = stable_hash(
            {
                "comment_evidence_id": atom.comment_evidence_id,
                "topic_code": topic.topic_code,
                "matched_terms": match.matched_terms,
                "polarity_hint": match.polarity_hint.value,
                "topic_confidence": match.topic_confidence,
                "topic_hint_status": match.topic_hint_status.value,
                "asset_version": asset_version,
                "rule_version": rule_version,
            },
            version=COMMENT_TOPIC_HINT_RESULT_HASH_VERSION,
        )
        return TopicHintRecord(
            topic_hint_id=topic_hint_id,
            project_id=atom.project_id,
            category_code=atom.category_code,
            batch_id=atom.batch_id,
            run_id=atom.run_id,
            module_run_id=atom.module_run_id,
            sku_code=atom.sku_code,
            model_name=atom.model_name,
            brand_name=atom.brand_name,
            comment_evidence_id=atom.comment_evidence_id,
            comment_unit_id=atom.comment_unit_id,
            topic_code=topic.topic_code,
            topic_name=topic.topic_name,
            topic_group=topic.topic_group,
            topic_definition=topic.topic_definition,
            match_method=match.match_method,
            matched_terms=match.matched_terms,
            match_source_json={
                "matched_terms_by_source": match.matched_terms_by_source,
                "confidence_components": {
                    "keyword_match_score": match.keyword_match_score,
                    "polarity_match_score": match.polarity_match_score,
                    "domain_consistency_score": match.domain_consistency_score,
                    "dimension_support_score": match.dimension_support_score,
                    "specificity_score": atom.specificity_score,
                    "low_value_penalty": match.low_value_penalty,
                    "service_product_conflict_penalty": match.service_product_conflict_penalty,
                },
                "primary_domain_hint": atom.primary_domain_hint,
                "service_guardrail": topic.service_guardrail,
            },
            polarity_hint=match.polarity_hint,
            topic_confidence=match.topic_confidence,
            is_weak_hint=True,
            activates_product_claim=topic.activates_product_claim,
            service_guardrail_flag=topic.service_guardrail,
            mapped_claim_codes_snapshot=topic.mapped_claim_codes,
            mapped_task_codes_snapshot=topic.mapped_task_codes,
            mapped_battlefield_codes_snapshot=topic.mapped_battlefield_codes,
            topic_hint_status=match.topic_hint_status,
            rule_version=rule_version,
            asset_version=asset_version,
            input_fingerprint=atom.input_fingerprint,
            result_hash=result_hash,
            review_required=atom.review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if atom.review_required else Core3ReviewStatus.AUTO_PASS,
            review_reason_json=atom.review_reason_json if atom.review_required else {},
        )


def _keyword_match_score(
    matched_terms: Sequence[str],
    keyword_terms: Sequence[str],
    alias_terms: Sequence[str],
    positive_terms: Sequence[str],
    negative_terms: Sequence[str],
) -> Decimal:
    all_text_terms = _unique_values([*keyword_terms, *alias_terms, *positive_terms, *negative_terms])
    term_count = max(len(all_text_terms), len(matched_terms))
    if term_count >= 3:
        return Decimal("1.0000")
    if term_count == 2:
        return Decimal("0.8500")
    return Decimal("0.7000")


def _polarity_match_score(atom: CommentEvidenceAtomRecord, polarity_hint: CommentSentimentHint) -> Decimal:
    atom_sentiment = _sentiment_value(atom.sentiment_hint)
    if polarity_hint == CommentSentimentHint.UNKNOWN or atom_sentiment == CommentSentimentHint.UNKNOWN:
        return Decimal("0.5000")
    if atom_sentiment == CommentSentimentHint.CONFLICT:
        return Decimal("0.2000")
    if atom_sentiment == polarity_hint:
        return Decimal("1.0000")
    if atom_sentiment == CommentSentimentHint.NEUTRAL:
        return Decimal("0.6000")
    return Decimal("0.0000")


def _domain_consistency_score(atom: CommentEvidenceAtomRecord, topic: CommentTopicSeed) -> Decimal:
    primary_domain = _enum_value(atom.primary_domain_hint)
    if primary_domain == topic.topic_group:
        return Decimal("1.0000")
    if primary_domain == CommentDomainHint.UNKNOWN.value:
        return Decimal("0.5000")
    if primary_domain in PRODUCT_DOMAINS and topic.topic_group in PRODUCT_DOMAINS:
        return Decimal("0.6500")
    return Decimal("0.0000")


def _service_product_conflict_penalty(atom: CommentEvidenceAtomRecord, topic: CommentTopicSeed) -> Decimal:
    primary_domain = _enum_value(atom.primary_domain_hint)
    if primary_domain in PRODUCT_DOMAINS and topic.topic_group in SERVICE_DOMAINS:
        return Decimal("1.0000")
    if primary_domain in SERVICE_DOMAINS and topic.topic_group in PRODUCT_DOMAINS:
        return Decimal("1.0000")
    return Decimal("0.0000")


def _topic_confidence(
    *,
    keyword_match_score: Decimal,
    polarity_match_score: Decimal,
    domain_consistency_score: Decimal,
    dimension_support_score: Decimal,
    specificity_score: Decimal,
    low_value_penalty: Decimal,
    service_product_conflict_penalty: Decimal,
) -> Decimal:
    score = (
        Decimal("0.45") * keyword_match_score
        + Decimal("0.20") * polarity_match_score
        + Decimal("0.15") * domain_consistency_score
        + Decimal("0.10") * dimension_support_score
        + Decimal("0.10") * specificity_score
        - Decimal("0.30") * low_value_penalty
        - Decimal("0.20") * service_product_conflict_penalty
    )
    return _quantize_confidence(min(Decimal("1.0000"), max(Decimal("0.0000"), score)))


def _topic_status(
    atom: CommentEvidenceAtomRecord,
    topic: CommentTopicSeed,
    topic_confidence: Decimal,
    service_product_conflict_penalty: Decimal,
) -> CommentTopicHintStatus | None:
    if atom.low_value_flag:
        return CommentTopicHintStatus.BLOCKED_LOW_VALUE
    if topic.service_guardrail and service_product_conflict_penalty > 0:
        return CommentTopicHintStatus.BLOCKED_SERVICE_GUARDRAIL
    if topic_confidence >= MATCHED_THRESHOLD:
        return CommentTopicHintStatus.MATCHED
    if topic_confidence >= LOW_CONFIDENCE_THRESHOLD:
        return CommentTopicHintStatus.LOW_CONFIDENCE
    return None


def _polarity_from_atom(atom: CommentEvidenceAtomRecord) -> CommentSentimentHint:
    sentiment = _sentiment_value(atom.sentiment_hint)
    if sentiment in {CommentSentimentHint.POSITIVE, CommentSentimentHint.NEGATIVE, CommentSentimentHint.NEUTRAL}:
        return sentiment
    return CommentSentimentHint.UNKNOWN


def _sentiment_value(value) -> CommentSentimentHint:
    normalized = _enum_value(value)
    try:
        return CommentSentimentHint(normalized)
    except ValueError:
        return CommentSentimentHint.UNKNOWN


def _matched_terms(compact_text: str, terms: Sequence[str]) -> list[str]:
    lower_text = compact_text.lower()
    return sorted(
        {term for term in terms if _compact_text(term) and _compact_text(term) in lower_text},
        key=lambda value: (len(value), value),
    )


def _matched_dimension_terms(raw_dimension_paths: Sequence[str], seed_dimension_paths: Sequence[str]) -> list[str]:
    if not seed_dimension_paths:
        return []
    matched: list[str] = []
    compact_paths = [_compact_text(path) for path in raw_dimension_paths]
    for dimension_path in seed_dimension_paths:
        compact_dimension_path = _compact_text(dimension_path)
        if compact_dimension_path and any(compact_dimension_path in path for path in compact_paths):
            matched.append(dimension_path)
    return sorted(set(matched))


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


def _quantize_confidence(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
