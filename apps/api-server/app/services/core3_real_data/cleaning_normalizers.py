"""M01 deterministic normalizers, parsers and clean-hash helpers."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    Core3QualityIssueType,
    Core3ValuePresenceStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


MISSING_COLUMN = object()
VOLATILE_CLEAN_HASH_FIELDS = frozenset(
    {
        "batch_id",
        "run_id",
        "module_run_id",
        "created_at",
        "updated_at",
    }
)
UNKNOWN_LITERALS = frozenset(
    {
        "unknown",
        "unk",
        "null",
        "none",
        "n/a",
        "na",
        "暂无",
        "未知",
        "不详",
        "无数据",
    }
)
DEFAULT_LOW_VALUE_COMMENT_PATTERNS: tuple[str, ...] = (
    "此用户没有填写评价",
    "此用户未填写评价",
    "此用户未及时填写评价",
    "默认好评",
    "系统默认好评",
)
EXACT_LOW_VALUE_COMMENT_PATTERNS = frozenset(
    {
        "好",
        "很好",
        "非常好",
        "不错",
        "挺好",
        "可以",
        "还可以",
        "满意",
        "很满意",
        "好用",
        "好评",
    }
)
SERVICE_FULFILLMENT_TERMS = frozenset(
    {
        "安装",
        "安装师傅",
        "师傅",
        "配送",
        "送货",
        "送装",
        "物流",
        "快递",
        "客服",
        "售后",
        "退换",
        "退货",
        "换货",
        "发票",
        "保修",
        "保价",
        "上门",
        "预约",
        "签收",
        "派送",
    }
)
PRODUCT_EXPERIENCE_TERMS = frozenset(
    {
        "画质",
        "屏幕",
        "清晰",
        "色彩",
        "亮度",
        "音质",
        "声音",
        "刷新率",
        "高刷",
        "延迟",
        "游戏",
        "看球",
        "体育",
        "系统",
        "遥控",
        "语音",
        "投屏",
        "护眼",
        "尺寸",
        "大屏",
        "反应",
        "流畅",
        "卡顿",
        "开机",
        "广告",
    }
)


class TextNormalizer:
    _html_tag_pattern = re.compile(r"<[^>]+>")
    _control_pattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _zero_width_pattern = re.compile(r"[\u200b-\u200f\ufeff]")
    _space_pattern = re.compile(r"\s+")

    @classmethod
    def normalize(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = html.unescape(str(value))
        text = cls._html_tag_pattern.sub(" ", text)
        text = cls._control_pattern.sub(" ", text)
        text = cls._zero_width_pattern.sub("", text)
        text = unicodedata.normalize("NFKC", text)
        text = cls._space_pattern.sub(" ", text)
        return text.strip()


class ValuePresenceClassifier:
    @classmethod
    def classify(cls, value: Any = MISSING_COLUMN, *, field_exists: bool = True) -> Core3ValuePresenceStatus:
        if not field_exists or value is MISSING_COLUMN:
            return Core3ValuePresenceStatus.MISSING_COLUMN
        if value is None:
            return Core3ValuePresenceStatus.NULL

        normalized = TextNormalizer.normalize(value)
        if normalized == "":
            return Core3ValuePresenceStatus.EMPTY
        if normalized in {"-", "--", "---", "—", "–"}:
            return Core3ValuePresenceStatus.DASH
        if normalized.casefold() in UNKNOWN_LITERALS:
            return Core3ValuePresenceStatus.UNKNOWN_LITERAL
        return Core3ValuePresenceStatus.PRESENT


@dataclass(frozen=True)
class NumberParseResult:
    raw_value: Any
    value: Decimal | None
    value_presence: Core3ValuePresenceStatus
    issue_type: Core3QualityIssueType | None = None

    @property
    def is_valid(self) -> bool:
        return self.issue_type is None and self.value is not None


class NumberParser:
    _number_pattern = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")

    @classmethod
    def parse(cls, value: Any = MISSING_COLUMN, *, allow_negative: bool = False) -> NumberParseResult:
        presence = ValuePresenceClassifier.classify(value)
        if presence != Core3ValuePresenceStatus.PRESENT:
            issue = (
                Core3QualityIssueType.UNKNOWN_VALUE
                if presence
                in {
                    Core3ValuePresenceStatus.EMPTY,
                    Core3ValuePresenceStatus.DASH,
                    Core3ValuePresenceStatus.UNKNOWN_LITERAL,
                }
                else None
            )
            return NumberParseResult(
                raw_value=None if value is MISSING_COLUMN else value,
                value=None,
                value_presence=presence,
                issue_type=issue,
            )

        normalized = TextNormalizer.normalize(value)
        assert normalized is not None
        number_text = normalized.replace(",", "").replace("，", "")
        if not cls._number_pattern.match(number_text):
            return NumberParseResult(
                raw_value=value,
                value=None,
                value_presence=presence,
                issue_type=Core3QualityIssueType.INVALID_NUMBER,
            )

        try:
            parsed = Decimal(number_text)
        except InvalidOperation:
            return NumberParseResult(
                raw_value=value,
                value=None,
                value_presence=presence,
                issue_type=Core3QualityIssueType.INVALID_NUMBER,
            )

        if parsed < 0 and not allow_negative:
            return NumberParseResult(
                raw_value=value,
                value=parsed,
                value_presence=presence,
                issue_type=Core3QualityIssueType.NEGATIVE_NUMBER,
            )
        return NumberParseResult(raw_value=value, value=parsed, value_presence=presence)


@dataclass(frozen=True)
class PriceCheckResult:
    expected_price: Decimal | None
    delta: Decimal | None
    issue_type: Core3QualityIssueType | None = None
    status: str = "uncheckable"


def check_average_price(
    *,
    sales_amount: Decimal | None,
    sales_volume: Decimal | None,
    avg_price: Decimal | None,
) -> PriceCheckResult:
    if sales_amount is None or sales_volume is None or avg_price is None or sales_volume == 0:
        return PriceCheckResult(expected_price=None, delta=None)

    expected = sales_amount / sales_volume
    delta = avg_price - expected
    abs_delta = abs(delta)
    relative_delta = abs_delta / abs(expected) if expected else Decimal("0")
    if abs_delta > Decimal("1") and relative_delta > Decimal("0.01"):
        return PriceCheckResult(
            expected_price=expected,
            delta=delta,
            issue_type=Core3QualityIssueType.PRICE_CHECK_MISMATCH,
            status="mismatch",
        )
    return PriceCheckResult(expected_price=expected, delta=delta, status="ok")


@dataclass(frozen=True)
class PeriodParseResult:
    raw_value: Any
    period_type: str | None
    period_year_hint: int | None
    period_week_index: int | None
    period_parse_status: str


class PeriodParser:
    _week_pattern = re.compile(r"^(?P<year>\d{2}|\d{4})\s*[-_/]?\s*[wW周]\s*(?P<week>\d{1,2})$")

    @classmethod
    def parse(cls, value: Any) -> PeriodParseResult:
        normalized = TextNormalizer.normalize(value)
        if not normalized:
            return PeriodParseResult(value, None, None, None, "failed")

        match = cls._week_pattern.match(normalized)
        if not match:
            return PeriodParseResult(value, None, None, None, "failed")

        year_text = match.group("year")
        week_index = int(match.group("week"))
        if not 1 <= week_index <= 53:
            return PeriodParseResult(value, None, None, None, "failed")

        year = int(year_text)
        if len(year_text) == 2:
            year += 2000
        return PeriodParseResult(value, "week", year, week_index, "parsed")


class SentenceSplitter:
    _separator_pattern = re.compile(r"[\n\r。！？!?；;]+")
    _prefix_pattern = re.compile(r"^\s*(?:[-*•·]+|\d+[.)、]|[一二三四五六七八九十]+[、.])\s*")

    @classmethod
    def split(cls, value: Any, *, max_sentence_length: int = 160) -> list[str]:
        normalized = TextNormalizer.normalize(value)
        if not normalized:
            return []

        sentences: list[str] = []
        for part in cls._separator_pattern.split(normalized):
            sentence = cls._prefix_pattern.sub("", part).strip(" ,，:")
            if not sentence:
                continue
            sentences.extend(cls._split_long_sentence(sentence, max_sentence_length=max_sentence_length))
        return sentences

    @classmethod
    def _split_long_sentence(cls, sentence: str, *, max_sentence_length: int) -> list[str]:
        if len(sentence) <= max_sentence_length:
            return [sentence]
        chunks: list[str] = []
        remaining = sentence
        while len(remaining) > max_sentence_length:
            chunks.append(remaining[:max_sentence_length])
            remaining = remaining[max_sentence_length:]
        if remaining:
            chunks.append(remaining)
        return chunks


def extract_claim_seq(variable: Any) -> int | None:
    normalized = TextNormalizer.normalize(variable)
    if not normalized:
        return None
    match = re.search(r"卖点\s*(\d{1,2})", normalized)
    if not match:
        return None
    claim_seq = int(match.group(1))
    if not 1 <= claim_seq <= 13:
        return None
    return claim_seq


def is_low_value_comment(value: Any, patterns: Iterable[str] = DEFAULT_LOW_VALUE_COMMENT_PATTERNS) -> bool:
    normalized = TextNormalizer.normalize(value)
    if not normalized:
        return True
    compact = normalized.replace(" ", "")
    return compact in EXACT_LOW_VALUE_COMMENT_PATTERNS or any(pattern in compact for pattern in patterns)


def is_service_fulfillment_text(value: Any) -> bool:
    normalized = TextNormalizer.normalize(value)
    if not normalized:
        return False
    compact = normalized.replace(" ", "")
    service_hits = [term for term in SERVICE_FULFILLMENT_TERMS if term in compact]
    if not service_hits:
        return False
    product_hit = any(term in compact for term in PRODUCT_EXPERIENCE_TERMS)
    if product_hit:
        return False
    return True


def extract_number_candidates(value: Any) -> list[dict[str, str]]:
    normalized = TextNormalizer.normalize(value)
    if not normalized:
        return []
    candidates: list[dict[str, str]] = []
    for match in re.finditer(r"(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?P<unit>[A-Za-z%寸英吋]+)?", normalized):
        candidate = {"number": match.group("number")}
        unit = match.group("unit")
        if unit:
            candidate["unit"] = unit
        candidates.append(candidate)
    return candidates


class CleanHashService:
    @classmethod
    def clean_record_key(cls, domain: str, *parts: Any) -> str:
        normalized_parts = [TextNormalizer.normalize(part) for part in parts]
        usable_parts = [part for part in normalized_parts if part]
        return ":".join([domain, *usable_parts])

    @classmethod
    def clean_hash(
        cls,
        clean_domain: str,
        payload: Mapping[str, Any],
        *,
        fields: Sequence[str] | None = None,
        version: str = CORE3_M01_CLEAN_HASH_VERSION,
    ) -> str:
        hash_fields = list(fields) if fields is not None else sorted(set(payload) - VOLATILE_CLEAN_HASH_FIELDS)
        hash_payload = {
            "clean_domain": clean_domain,
            "payload": {field: payload.get(field) for field in sorted(hash_fields)},
        }
        return stable_hash(hash_payload, version=version)
