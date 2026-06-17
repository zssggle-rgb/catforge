from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from app.models.entities import RawSkuClaim, RawSkuComment, RawSkuParam
from app.schemas.core3_mvp import (
    Core3CandidateClaim,
    Core3CandidateCommentTopic,
    Core3CandidateParamAlias,
    Core3ParamFieldProfile,
    Core3SeedCatalog,
    Core3StandardParamSeed,
)
from app.services.core3_mvp.data_access import Core3InputBundle, is_unknown


POSITIVE_WORDS = ["好", "不错", "清晰", "流畅", "满意", "舒服", "方便", "够用", "专业", "喜欢", "爽", "大气"]
NEGATIVE_WORDS = ["卡", "慢", "刺眼", "反光", "漏光", "拖影", "麻烦", "广告多", "贵", "故障", "差", "模糊"]
NEGATIONS = ["不", "没有", "没", "无"]
SERVICE_WORDS = ["安装", "师傅", "服务", "送货", "售后", "上门"]
PRICE_WORDS = ["价格", "性价比", "划算", "优惠", "便宜", "贵"]
GENERIC_RELEVANCE_TERMS = {"hz", "gb", "g", "w", "ms", "%", "nits", "nit", "尼特"}


@dataclass(frozen=True)
class ParsedParamValue:
    parser: str
    value: Any
    unit: str | None = None
    extra: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParamExtraction:
    sku_code: str
    param_code: str
    normalized_value: Any
    unit: str | None
    source_type: str
    source_file_id: str | None
    raw_row_id: str | None
    field_name: str
    raw_value: str
    confidence: float
    match_type: str
    source_ref: dict[str, Any]


@dataclass(frozen=True)
class ClaimSentence:
    sku_code: str
    sentence: str
    source_file_id: str | None
    raw_row_id: str | None
    sentence_index: int
    row: RawSkuClaim


@dataclass(frozen=True)
class ClaimHit:
    sku_code: str
    claim_code: str
    sentence: str
    matched_keywords: list[str]
    source_file_id: str | None
    raw_row_id: str | None
    sentence_index: int
    confidence: float
    source_ref: dict[str, Any]


@dataclass(frozen=True)
class CommentSentence:
    sku_code: str
    sentence: str
    comment_id: str | None
    sentence_index: int
    source_file_id: str | None
    raw_row_id: str | None
    comment_type: str
    sentiment: str
    row: RawSkuComment


@dataclass(frozen=True)
class CommentTopicHit:
    sku_code: str
    topic_code: str
    sentence: str
    sentiment: str
    comment_type: str
    matched_keywords: list[str]
    source_file_id: str | None
    raw_row_id: str | None
    sentence_index: int
    confidence: float
    source_ref: dict[str, Any]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", "", text).casefold()


def split_sentences(text: Any) -> list[str]:
    if is_unknown(text):
        return []
    normalized = unicodedata.normalize("NFKC", str(text)).strip()
    parts = re.split(r"[。！？!?；;\n\r，,]+", normalized)
    return [part.strip() for part in parts if part.strip()]


def profile_param_fields(bundle: Core3InputBundle, seed: Core3SeedCatalog) -> list[Core3ParamFieldProfile]:
    sku_count = len({row.sku_code for row in bundle.sku_master if not is_unknown(row.sku_code)}) or 1
    grouped: dict[str, list[RawSkuParam]] = defaultdict(list)
    for row in bundle.params:
        if not is_unknown(row.raw_param_name):
            grouped[str(row.raw_param_name).strip()].append(row)

    profiles: list[Core3ParamFieldProfile] = []
    for raw_name, rows in sorted(grouped.items()):
        non_empty = [row for row in rows if not is_unknown(row.raw_param_value)]
        values = [str(row.raw_param_value).strip() for row in non_empty]
        match = match_param_field(raw_name, seed)
        profiles.append(
            Core3ParamFieldProfile(
                raw_param_name=raw_name,
                row_count=len(rows),
                sku_count=len({row.sku_code for row in rows if not is_unknown(row.sku_code)}),
                coverage=round(len({row.sku_code for row in rows if not is_unknown(row.sku_code)}) / sku_count, 4),
                non_empty_rate=round(len(non_empty) / len(rows), 4) if rows else 0.0,
                top_values=[value for value, _ in Counter(values).most_common(5)],
                contains_numeric=any(bool(re.search(r"\d", value)) for value in values),
                matched_param_code=match["param_code"],
                match_type=match["match_type"],
                match_confidence=match["confidence"],
                status="mapped" if match["param_code"] else "unmapped",
            )
        )
    return profiles


def match_param_field(raw_param_name: Any, seed: Core3SeedCatalog) -> dict[str, Any]:
    raw_norm = normalize_text(raw_param_name)
    if not raw_norm:
        return {"param_code": None, "match_type": None, "confidence": 0.0}
    for item in seed.standard_params:
        aliases = [item.param_name, item.param_code, *item.aliases]
        if raw_norm in {normalize_text(alias) for alias in aliases}:
            return {"param_code": item.param_code, "match_type": "exact_alias", "confidence": 0.95}
    for item in seed.standard_params:
        aliases = [item.param_name, *item.aliases]
        alias_norms = [normalize_text(alias) for alias in aliases if alias]
        if any(alias and (alias in raw_norm or raw_norm in alias) for alias in alias_norms):
            return {"param_code": item.param_code, "match_type": "contains_alias", "confidence": 0.85}
    for item in seed.standard_params:
        keyword_norms = [normalize_text(keyword) for keyword in item.keywords if keyword]
        if any(keyword and keyword in raw_norm for keyword in keyword_norms):
            return {"param_code": item.param_code, "match_type": "keyword", "confidence": 0.75}
    return {"param_code": None, "match_type": None, "confidence": 0.0}


def parse_value(value: Any, parser: str, *, param_code: str | None = None) -> ParsedParamValue | None:
    if is_unknown(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    parser = parser.strip()
    if parser in {"number", "string", "date_period", "list_keyword"}:
        return _parse_generic(text, parser)
    if parser == "inch":
        number = _first_number(text, r"(\d+(?:\.\d+)?)\s*(?:英寸|寸|inch|\")?")
        return _number_result(parser, number, "inch")
    if parser == "hz":
        number = _first_number(text, r"(\d+(?:\.\d+)?)\s*(?:hz|赫兹)", flags=re.I)
        return _number_result(parser, number, "Hz")
    if parser == "nits":
        number = _first_number(text, r"(\d+(?:\.\d+)?)\s*(?:nits?|尼特)", flags=re.I)
        return _number_result(parser, number, "nits")
    if parser == "zones":
        if "千级分区" in text:
            return ParsedParamValue(parser=parser, value=1000, unit="zones", extra={"raw_expression": "千级分区"})
        if "百级分区" in text:
            return ParsedParamValue(parser=parser, value=100, unit="zones", extra={"raw_expression": "百级分区"})
        number = _first_number(text, r"(\d+(?:\.\d+)?)\s*(?:个)?\s*(?:分区|zones?)", flags=re.I)
        return _number_result(parser, number, "zones")
    if parser == "gb":
        return _parse_gb(text, param_code)
    if parser == "ports":
        return _parse_ports(text)
    if parser == "resolution":
        return _parse_resolution(text)
    if parser == "percentage":
        return _parse_percentage(text)
    if parser == "watt":
        number = _first_number(text, r"(\d+(?:\.\d+)?)\s*(?:w|瓦)", flags=re.I)
        return _number_result(parser, number, "W")
    if parser == "ms":
        number = _first_number(text, r"(\d+(?:\.\d+)?)\s*(?:ms|毫秒)", flags=re.I)
        return _number_result(parser, number, "ms")
    if parser == "boolean_keyword":
        return _parse_boolean(text)
    if parser == "enum_keyword":
        return _parse_enum(text)
    return None


def parse_param_value(raw_value: Any, param: Core3StandardParamSeed) -> ParsedParamValue | None:
    for parser in param.value_parsers:
        parsed = parse_value(raw_value, parser, param_code=param.param_code)
        if parsed is None:
            continue
        value = parsed.value
        if isinstance(value, dict):
            if param.param_code in value:
                value = value[param.param_code]
            elif "value" in value:
                value = value["value"]
        if value is None or is_unknown(value):
            continue
        return ParsedParamValue(parser=parsed.parser, value=value, unit=param.unit or parsed.unit, extra=parsed.extra or {})
    return None


def extract_param_values(bundle: Core3InputBundle, seed: Core3SeedCatalog) -> tuple[list[ParamExtraction], list[dict[str, Any]]]:
    params_by_code = {item.param_code: item for item in seed.standard_params}
    extractions: list[ParamExtraction] = []
    conflicts: list[dict[str, Any]] = []
    current_values: dict[tuple[str, str], Any] = {}

    for row in bundle.params:
        if is_unknown(row.sku_code) or is_unknown(row.raw_param_name):
            continue
        match = match_param_field(row.raw_param_name, seed)
        param_code = match["param_code"]
        if not param_code:
            continue
        parsed = parse_param_value(row.raw_param_value, params_by_code[param_code])
        if parsed is None:
            continue
        if (
            param_code == "native_refresh_rate_hz"
            and normalize_text(row.raw_param_name) in {normalize_text("屏幕刷新率"), normalize_text("刷新率")}
            and isinstance(parsed.value, int | float)
            and parsed.value >= 240
        ):
            param_code = "system_refresh_rate_hz"
        key = (str(row.sku_code).strip(), param_code)
        if key in current_values and current_values[key] != parsed.value:
            conflicts.append(
                {
                    "sku_code": key[0],
                    "param_code": param_code,
                    "values": [current_values[key], parsed.value],
                    "raw_param_name": row.raw_param_name,
                }
            )
        current_values.setdefault(key, parsed.value)
        extractions.append(
            ParamExtraction(
                sku_code=str(row.sku_code).strip(),
                param_code=param_code,
                normalized_value=parsed.value,
                unit=parsed.unit,
                source_type="raw_param",
                source_file_id=row.source_file_id,
                raw_row_id=row.raw_row_id,
                field_name=str(row.raw_param_name),
                raw_value=str(row.raw_param_value),
                confidence=match["confidence"],
                match_type=match["match_type"] or "unknown",
                source_ref={"table": "raw_sku_param", "parser": parsed.parser},
            )
        )

    claim_sentences = build_claim_sentences(bundle.claims)
    for sentence in claim_sentences:
        for param in seed.standard_params:
            if not _param_sentence_relevant(sentence.sentence, param):
                continue
            parsed = parse_param_value(sentence.sentence, param)
            if parsed is None:
                continue
            extractions.append(
                ParamExtraction(
                    sku_code=sentence.sku_code,
                    param_code=param.param_code,
                    normalized_value=parsed.value,
                    unit=parsed.unit,
                    source_type="claim_text",
                    source_file_id=sentence.source_file_id,
                    raw_row_id=sentence.raw_row_id,
                    field_name="claim_text",
                    raw_value=sentence.sentence,
                    confidence=0.72,
                    match_type="claim_text_parser",
                    source_ref={
                        "table": "raw_sku_claim",
                        "sentence_index": sentence.sentence_index,
                        "parser": parsed.parser,
                    },
                )
            )
    return extractions, conflicts


def build_claim_sentences(rows: list[RawSkuClaim]) -> list[ClaimSentence]:
    output: list[ClaimSentence] = []
    for row in rows:
        if is_unknown(row.sku_code):
            continue
        text = " ".join(part for part in [row.claim_title, row.claim_text] if not is_unknown(part))
        for index, sentence in enumerate(split_sentences(text)):
            output.append(
                ClaimSentence(
                    sku_code=str(row.sku_code).strip(),
                    sentence=sentence,
                    source_file_id=row.source_file_id,
                    raw_row_id=row.raw_row_id,
                    sentence_index=index,
                    row=row,
                )
            )
    return output


def extract_claim_hits(bundle: Core3InputBundle, seed: Core3SeedCatalog) -> list[ClaimHit]:
    hits: list[ClaimHit] = []
    for sentence in build_claim_sentences(bundle.claims):
        for claim in seed.standard_claims:
            keywords = _matched_keywords(sentence.sentence, [*claim.promo_keywords, *claim.keywords, *claim.aliases])
            if not keywords or _is_negated(sentence.sentence, keywords):
                continue
            hits.append(
                ClaimHit(
                    sku_code=sentence.sku_code,
                    claim_code=claim.claim_code,
                    sentence=sentence.sentence,
                    matched_keywords=keywords,
                    source_file_id=sentence.source_file_id,
                    raw_row_id=sentence.raw_row_id,
                    sentence_index=sentence.sentence_index,
                    confidence=min(0.95, 0.72 + 0.04 * len(keywords)),
                    source_ref={
                        "table": "raw_sku_claim",
                        "sentence_index": sentence.sentence_index,
                        "matched_keywords": keywords,
                    },
                )
            )
    return hits


def build_comment_sentences(rows: list[RawSkuComment]) -> list[CommentSentence]:
    output: list[CommentSentence] = []
    for row in rows:
        if is_unknown(row.sku_code):
            continue
        for index, sentence in enumerate(split_sentences(row.comment_text)):
            output.append(
                CommentSentence(
                    sku_code=str(row.sku_code).strip(),
                    sentence=sentence,
                    comment_id=row.comment_id,
                    sentence_index=index,
                    source_file_id=row.source_file_id,
                    raw_row_id=row.raw_row_id,
                    comment_type=classify_comment_type(sentence),
                    sentiment=classify_sentiment(sentence),
                    row=row,
                )
            )
    return output


def extract_comment_topic_hits(bundle: Core3InputBundle, seed: Core3SeedCatalog) -> list[CommentTopicHit]:
    hits: list[CommentTopicHit] = []
    for sentence in build_comment_sentences(bundle.comments):
        scored: list[tuple[int, Any, list[str]]] = []
        for topic in seed.comment_topics:
            keywords = _matched_keywords(sentence.sentence, [*topic.keywords, *topic.aliases])
            if keywords:
                scored.append((len(keywords), topic, keywords))
        scored.sort(key=lambda item: (-item[0], item[1].topic_code))
        for _, topic, keywords in scored[:3]:
            hits.append(
                CommentTopicHit(
                    sku_code=sentence.sku_code,
                    topic_code=topic.topic_code,
                    sentence=sentence.sentence,
                    sentiment=sentence.sentiment,
                    comment_type=sentence.comment_type,
                    matched_keywords=keywords,
                    source_file_id=sentence.source_file_id,
                    raw_row_id=sentence.raw_row_id,
                    sentence_index=sentence.sentence_index,
                    confidence=min(0.95, 0.68 + 0.05 * len(keywords)),
                    source_ref={
                        "table": "raw_sku_comment",
                        "comment_id": sentence.comment_id,
                        "sentence_index": sentence.sentence_index,
                        "matched_keywords": keywords,
                    },
                )
            )
    return hits


def classify_comment_type(sentence: str) -> str:
    if _matched_keywords(sentence, SERVICE_WORDS):
        return "service_experience"
    if _matched_keywords(sentence, PRICE_WORDS):
        return "price_value"
    return "product_experience"


def classify_sentiment(sentence: str) -> str:
    text = normalize_text(sentence)
    positive = 0
    negative = 0
    for word in POSITIVE_WORDS:
        if normalize_text(word) in text:
            if _word_negated(text, normalize_text(word)):
                negative += 1
            else:
                positive += 1
    for word in NEGATIVE_WORDS:
        word_norm = normalize_text(word)
        if word_norm in text:
            if _word_negated(text, word_norm):
                positive += 1
            else:
                negative += 1
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def discover_candidate_param_aliases(
    profiles: list[Core3ParamFieldProfile],
    *,
    min_coverage: float = 0.2,
) -> list[Core3CandidateParamAlias]:
    candidates: list[Core3CandidateParamAlias] = []
    for profile in profiles:
        if profile.matched_param_code or profile.coverage < min_coverage:
            continue
        candidates.append(
            Core3CandidateParamAlias(
                raw_param_name=profile.raw_param_name,
                coverage=profile.coverage,
                examples=profile.top_values,
                suggested_param_code=None,
                confidence=min(0.8, 0.45 + profile.coverage),
            )
        )
    return candidates


def discover_candidate_claims(
    bundle: Core3InputBundle,
    seed: Core3SeedCatalog,
    claim_hits: list[ClaimHit],
    *,
    min_coverage: float = 0.2,
) -> list[Core3CandidateClaim]:
    hit_keys = {(hit.source_file_id, hit.raw_row_id, hit.sentence_index) for hit in claim_hits}
    known_keywords = {normalize_text(keyword) for claim in seed.standard_claims for keyword in [*claim.keywords, *claim.aliases]}
    phrase_skus: dict[str, set[str]] = defaultdict(set)
    phrase_sentences: dict[str, list[str]] = defaultdict(list)
    sku_count = len({row.sku_code for row in bundle.sku_master if not is_unknown(row.sku_code)}) or 1
    for sentence in build_claim_sentences(bundle.claims):
        if (sentence.source_file_id, sentence.raw_row_id, sentence.sentence_index) in hit_keys:
            continue
        for phrase in _candidate_phrases(sentence.sentence):
            if normalize_text(phrase) in known_keywords:
                continue
            phrase_skus[phrase].add(sentence.sku_code)
            phrase_sentences[phrase].append(sentence.sentence)
    return [
        Core3CandidateClaim(
            raw_phrase=phrase,
            coverage=round(len(skus) / sku_count, 4),
            example_skus=sorted(skus)[:5],
            sample_sentences=sentences[:3],
            suggested_group=_suggest_claim_group(phrase),
            confidence=min(0.82, 0.45 + len(skus) / sku_count),
        )
        for phrase, skus in sorted(phrase_skus.items())
        if len(skus) / sku_count >= min_coverage
        for sentences in [phrase_sentences[phrase]]
    ]


def discover_candidate_comment_topics(
    bundle: Core3InputBundle,
    seed: Core3SeedCatalog,
    topic_hits: list[CommentTopicHit],
    *,
    min_coverage: float = 0.2,
) -> list[Core3CandidateCommentTopic]:
    hit_keys = {(hit.source_file_id, hit.raw_row_id, hit.sentence_index) for hit in topic_hits}
    known_keywords = {normalize_text(keyword) for topic in seed.comment_topics for keyword in [*topic.keywords, *topic.aliases]}
    phrase_skus: dict[str, set[str]] = defaultdict(set)
    phrase_sentences: dict[str, list[str]] = defaultdict(list)
    phrase_sentiments: dict[str, Counter[str]] = defaultdict(Counter)
    sku_count = len({row.sku_code for row in bundle.sku_master if not is_unknown(row.sku_code)}) or 1
    for sentence in build_comment_sentences(bundle.comments):
        if (sentence.source_file_id, sentence.raw_row_id, sentence.sentence_index) in hit_keys:
            continue
        for phrase in _candidate_phrases(sentence.sentence):
            if normalize_text(phrase) in known_keywords:
                continue
            phrase_skus[phrase].add(sentence.sku_code)
            phrase_sentences[phrase].append(sentence.sentence)
            phrase_sentiments[phrase][sentence.sentiment] += 1
    output: list[Core3CandidateCommentTopic] = []
    for phrase, skus in sorted(phrase_skus.items()):
        coverage = len(skus) / sku_count
        if coverage < min_coverage:
            continue
        sentiment_hint = phrase_sentiments[phrase].most_common(1)[0][0]
        output.append(
            Core3CandidateCommentTopic(
                raw_phrase=phrase,
                coverage=round(coverage, 4),
                sample_sentences=phrase_sentences[phrase][:3],
                suggested_topic_group="service_experience" if _matched_keywords(phrase, SERVICE_WORDS) else "product_experience",
                sentiment_hint=sentiment_hint,
                confidence=min(0.82, 0.45 + coverage),
            )
        )
    return output


def _parse_generic(text: str, parser: str) -> ParsedParamValue | None:
    if parser == "string":
        return ParsedParamValue(parser=parser, value=text)
    if parser == "number":
        return _number_result(parser, _first_number(text, r"(\d+(?:\.\d+)?)"), None)
    if parser == "date_period":
        return ParsedParamValue(parser=parser, value=text)
    if parser == "list_keyword":
        values = re.findall(r"(HDR10\+?|HLG|Dolby Vision|杜比视界|IMAX Enhanced)", text, flags=re.I)
        return ParsedParamValue(parser=parser, value=values) if values else None
    return None


def _parse_gb(text: str, param_code: str | None) -> ParsedParamValue | None:
    values = [_coerce_number(match) for match in re.findall(r"(\d+(?:\.\d+)?)\s*(?:gb|g)", text, flags=re.I)]
    if not values:
        return None
    payload: dict[str, Any] = {"values": values}
    if len(values) >= 2:
        payload["ram_gb"] = values[0]
        payload["storage_gb"] = values[1]
    elif param_code:
        payload[param_code] = values[0]
    if param_code in payload:
        return ParsedParamValue(parser="gb", value=payload[param_code], unit="GB", extra={"split": payload})
    return ParsedParamValue(parser="gb", value=payload if len(values) >= 2 else values[0], unit="GB", extra={"split": payload})


def _parse_ports(text: str) -> ParsedParamValue | None:
    patterns = [
        r"(\d+)\s*[x×*]?\s*(?:个|路)?\s*HDMI\s*2\.?1",
        r"(\d+)\s*(?:个|路)\s*满血",
        r"HDMI\s*2\.?1\s*(?:接口)?\s*(\d+)\s*(?:个|路)",
    ]
    for pattern in patterns:
        number = _first_number(text, pattern, flags=re.I)
        if number is not None:
            return _number_result("ports", number, "ports")
    if re.search(r"HDMI\s*2\.?1", text, flags=re.I):
        return ParsedParamValue(parser="ports", value=1, unit="ports")
    return None


def _parse_resolution(text: str) -> ParsedParamValue | None:
    compact = normalize_text(text).replace("×", "x").replace("*", "x")
    if "8k" in compact or "7680x4320" in compact:
        return ParsedParamValue(parser="resolution", value="8K")
    if "4k" in compact or "3840x2160" in compact:
        return ParsedParamValue(parser="resolution", value="4K")
    if "fhd" in compact or "1920x1080" in compact:
        return ParsedParamValue(parser="resolution", value="FHD")
    return None


def _parse_percentage(text: str) -> ParsedParamValue | None:
    number = _first_number(text, r"(\d+(?:\.\d+)?)\s*%")
    if number is None:
        return None
    standard = None
    for candidate in ["DCI-P3", "BT.2020", "BT2020", "NTSC", "sRGB"]:
        if normalize_text(candidate) in normalize_text(text):
            standard = "BT.2020" if candidate == "BT2020" else candidate
            break
    return ParsedParamValue(parser="percentage", value={"value": _coerce_number(number), "standard": standard}, unit="%")


def _parse_boolean(text: str) -> ParsedParamValue | None:
    norm = normalize_text(text)
    if is_unknown(norm):
        return None
    true_terms = ["是", "支持", "有", "具备", "miniled", "mini led", "oled", "qled", "vrr", "allm", "freesync", "无频闪", "无广告"]
    false_terms = ["不支持", "不具备", "没有", "否", "false"]
    if any(normalize_text(term) in norm for term in true_terms):
        return ParsedParamValue(parser="boolean_keyword", value=True)
    if norm in {"无", "否", "false", "no"} or any(normalize_text(term) in norm for term in false_terms):
        return ParsedParamValue(parser="boolean_keyword", value=False)
    return None


def _parse_enum(text: str) -> ParsedParamValue | None:
    norm = normalize_text(text)
    mappings = [
        ("MiniLED", ["miniled", "mini led", "迷你led", "u+mini"]),
        ("OLED", ["oled", "自发光"]),
        ("QLED", ["qled", "量子点"]),
        ("4K", ["4k", "3840x2160", "3840×2160"]),
        ("8K", ["8k", "7680x4320", "7680×4320"]),
        ("FHD", ["fhd", "1920x1080", "1920×1080"]),
    ]
    for value, terms in mappings:
        if any(normalize_text(term) in norm for term in terms):
            return ParsedParamValue(parser="enum_keyword", value=value)
    return None


def _number_result(parser: str, number: str | float | int | None, unit: str | None) -> ParsedParamValue | None:
    if number is None:
        return None
    return ParsedParamValue(parser=parser, value=_coerce_number(number), unit=unit)


def _first_number(text: str, pattern: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags=flags)
    return match.group(1) if match else None


def _coerce_number(value: str | float | int) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _param_sentence_relevant(sentence: str, param: Core3StandardParamSeed) -> bool:
    haystack = normalize_text(sentence)
    terms = [
        term
        for term in [param.param_name, *param.aliases, *param.keywords]
        if normalize_text(term) not in GENERIC_RELEVANCE_TERMS
    ]
    if any(normalize_text(term) and normalize_text(term) in haystack for term in terms):
        return True
    if param.param_code == "hdmi_2_1_ports" and re.search(r"HDMI\s*2\.?1", sentence, flags=re.I):
        return True
    if param.param_code in {"native_refresh_rate_hz", "refresh_rate_hz"} and "高刷" in sentence:
        return True
    return False


def _matched_keywords(text: str, keywords: list[str]) -> list[str]:
    haystack = normalize_text(text)
    matches: list[str] = []
    for keyword in keywords:
        key = normalize_text(keyword)
        if key and key in haystack and keyword not in matches:
            matches.append(keyword)
    return matches


def _is_negated(sentence: str, keywords: list[str]) -> bool:
    text = normalize_text(sentence)
    for keyword in keywords:
        key = normalize_text(keyword)
        index = text.find(key)
        if index < 0:
            continue
        prefix = text[max(0, index - 4):index]
        if any(neg in prefix for neg in ["不支持", "不是", "不具备", "非"]):
            return True
    return False


def _word_negated(text: str, word: str) -> bool:
    index = text.find(word)
    if index < 0:
        return False
    prefix = text[max(0, index - 3):index]
    return any(normalize_text(neg) in prefix for neg in NEGATIONS)


def _candidate_phrases(sentence: str) -> list[str]:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\+ ]+", " ", unicodedata.normalize("NFKC", sentence))
    chunks = [chunk.strip() for chunk in re.split(r"\s+", cleaned) if chunk.strip()]
    phrases: list[str] = []
    if 4 <= len(cleaned.strip()) <= 24:
        phrases.append(cleaned.strip())
    for chunk in chunks:
        if 3 <= len(chunk) <= 18 and not re.fullmatch(r"\d+(?:\.\d+)?", chunk):
            phrases.append(chunk)
    return list(dict.fromkeys(phrases))


def _suggest_claim_group(phrase: str) -> str:
    if _matched_keywords(phrase, ["画质", "亮度", "屏", "芯片", "色彩"]):
        return "picture"
    if _matched_keywords(phrase, ["游戏", "高刷", "HDMI"]):
        return "gaming"
    if _matched_keywords(phrase, ["音", "杜比"]):
        return "audio"
    if _matched_keywords(phrase, ["护眼", "蓝光"]):
        return "eye_care"
    return "unknown"
