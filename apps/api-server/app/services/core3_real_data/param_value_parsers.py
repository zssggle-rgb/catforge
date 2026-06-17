"""M03 deterministic parameter value parser registry."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Sequence

from app.services.core3_real_data.param_extraction_schemas import ParamParserStatus


M03_VALUE_PRESENT = "present"
M03_VALUE_UNKNOWN = "unknown"
UNKNOWN_LITERALS = frozenset({"", "-", "--", "---", "unknown", "unk", "null", "none", "n/a", "na", "暂无", "未知", "不详"})
TRUE_LITERALS = frozenset({"是", "有", "支持", "true", "yes", "y", "1", "支持此功能"})
FALSE_LITERALS = frozenset({"否", "无", "不支持", "false", "no", "n", "0", "不支持此功能"})
LIST_SPLIT_PATTERN = re.compile(r"[/,，、;；|]+")
NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
RESOLUTION_PATTERN = re.compile(r"(?P<width>\d{3,5})\s*[x×*]\s*(?P<height>\d{3,5})", re.IGNORECASE)
HDMI_VERSION_PATTERN = re.compile(r"hdmi\s*(?P<version>2\.1|2\.0|1\.4)", re.IGNORECASE)


@dataclass(frozen=True)
class ParamValueParserContext:
    param_code: str | None = None
    param_name: str | None = None
    clean_param_name: str | None = None
    data_type: str | None = None
    enum_values: Sequence[str] = field(default_factory=tuple)
    keywords: Sequence[str] = field(default_factory=tuple)
    unit: str | None = None

    @property
    def field_text(self) -> str:
        return _normalize_text(" ".join(_present_strings([self.param_code, self.param_name, self.clean_param_name])))


@dataclass(frozen=True)
class ParamParseResult:
    parser_name: str
    parser_status: ParamParserStatus
    value_presence: str
    normalized_value: dict[str, Any] | list[Any] | str | int | float | bool | None
    numeric_value: Decimal | None = None
    value_text: str | None = None
    unit: str | None = None
    value_level: str | None = None
    quality_flags: list[str] = field(default_factory=list)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    @property
    def parsed(self) -> bool:
        return self.parser_status in {
            ParamParserStatus.PARSED,
            ParamParserStatus.SCOPE_UNCERTAIN,
            ParamParserStatus.UNIT_UNCERTAIN,
        }

    def to_param_value_payload(self) -> dict[str, Any]:
        return {
            "normalized_value": self.normalized_value,
            "numeric_value": self.numeric_value,
            "value_text": self.value_text,
            "unit": self.unit,
            "value_level": self.value_level,
            "value_presence": self.value_presence,
            "parser_type": self.parser_name,
            "parser_status": self.parser_status.value,
            "quality_flags": self.quality_flags,
        }


ParserCallable = Callable[[Any, ParamValueParserContext], ParamParseResult]


class ParamValueParserRegistry:
    """Register and dispatch deterministic M03 value parsers."""

    def __init__(self) -> None:
        self._parsers: dict[str, ParserCallable] = {}
        self._register_defaults()

    @property
    def registered_parser_names(self) -> set[str]:
        return set(self._parsers)

    def register(self, parser_name: str, parser: ParserCallable) -> None:
        if not parser_name.strip():
            raise ValueError("parser_name must not be empty")
        self._parsers[parser_name] = parser

    def require(self, parser_name: str) -> ParserCallable:
        parser = self._parsers.get(parser_name)
        if parser is None:
            raise KeyError(f"parser is not registered: {parser_name}")
        return parser

    def parse(
        self,
        value: Any,
        parser_name: str,
        context: ParamValueParserContext | None = None,
    ) -> ParamParseResult:
        return self.require(parser_name)(value, context or ParamValueParserContext())

    def parse_with_context(
        self,
        value: Any,
        parser_names: Sequence[str],
        context: ParamValueParserContext | None = None,
    ) -> ParamParseResult:
        normalized_context = context or ParamValueParserContext()
        last_result: ParamParseResult | None = None
        for parser_name in parser_names:
            result = self.parse(value, parser_name, normalized_context)
            if result.parsed or result.parser_status == ParamParserStatus.UNKNOWN:
                return result
            last_result = result
        return last_result or _failed_result("unregistered", value, "no_parser_names")

    def _register_defaults(self) -> None:
        self.register("inch", _parse_inch)
        self.register("resolution", _parse_resolution)
        self.register("hz", _parse_hz)
        self.register("nits", _parse_nits)
        self.register("zones", _parse_zones)
        self.register("ports", _parse_ports)
        self.register("gb", _parse_gb)
        self.register("percentage", _parse_percentage)
        self.register("boolean_keyword", _parse_boolean_keyword)
        self.register("enum_keyword", _parse_enum_keyword)
        self.register("list_keyword", _parse_list_keyword)
        self.register("string", _parse_string)
        self.register("number", _parse_number)
        self.register("watt", _parse_watt)
        self.register("ms", _parse_ms)
        self.register("date_period", _parse_date_period)


def _parse_inch(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("inch", value)
    if unknown is not None:
        return unknown
    number = _first_decimal(value)
    if number is None:
        return _failed_result("inch", value, "number_not_found")
    return _number_result("inch", value, number, unit="inch", normalized_key="value")


def _parse_resolution(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("resolution", value)
    if unknown is not None:
        return unknown
    text = _normalize_text(value)
    dimension_match = RESOLUTION_PATTERN.search(text)
    width: int | None = None
    height: int | None = None
    if dimension_match:
        width = int(dimension_match.group("width"))
        height = int(dimension_match.group("height"))
        resolution_class = "8K" if width >= 7000 or height >= 4000 else "4K" if width >= 3000 else None
    elif re.search(r"(?<!\d)8\s*k(?![a-z])", text):
        resolution_class = "8K"
    elif re.search(r"(?<!\d)4\s*k(?![a-z])", text):
        resolution_class = "4K"
    else:
        return _failed_result("resolution", value, "resolution_not_found")

    normalized_value: dict[str, Any] = {"resolution_class": resolution_class}
    if width is not None and height is not None:
        normalized_value.update({"width": width, "height": height})
    return ParamParseResult(
        parser_name="resolution",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=normalized_value,
        value_text=_value_text(value),
    )


def _parse_hz(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("hz", value)
    if unknown is not None:
        return unknown
    number = _first_decimal(value)
    if number is None:
        return _failed_result("hz", value, "hz_not_found")

    clean_field_text = _normalize_text(context.clean_param_name)
    field_text = context.field_text
    scope = "unknown"
    status = ParamParserStatus.PARSED
    quality_flags: list[str] = []
    if any(token in clean_field_text for token in ["原生", "native"]):
        scope = "native"
    elif any(token in clean_field_text for token in ["系统", "倍频", "动态", "motion", "system"]):
        scope = "system"
    elif number > Decimal("240"):
        scope = "system"
        status = ParamParserStatus.SCOPE_UNCERTAIN
        quality_flags.extend(["scope_uncertain", "high_refresh_rate_requires_review"])
    elif any(token in field_text for token in ["原生", "native"]):
        scope = "native"
    elif any(token in field_text for token in ["系统", "倍频", "动态", "motion", "system"]):
        scope = "system"

    return ParamParseResult(
        parser_name="hz",
        parser_status=status,
        value_presence=M03_VALUE_PRESENT,
        normalized_value={"value": _json_number(number), "unit": "Hz", "scope": scope},
        numeric_value=number,
        value_text=_value_text(value),
        unit="Hz",
        quality_flags=quality_flags,
    )


def _parse_nits(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("nits", value)
    if unknown is not None:
        return unknown
    number = _first_decimal(value)
    if number is None:
        return _failed_result("nits", value, "nits_not_found")

    text = _normalize_text(value)
    field_text = context.field_text
    has_unit = bool(re.search(r"nits?|尼特", text, re.IGNORECASE))
    status = ParamParserStatus.PARSED
    quality_flags: list[str] = []
    if not has_unit and any(token in field_text for token in ["亮度", "峰值", "brightness"]):
        status = ParamParserStatus.UNIT_UNCERTAIN
        quality_flags.append("unit_inferred")
    elif not has_unit:
        return _failed_result("nits", value, "nits_unit_not_found")
    return _number_result(
        "nits",
        value,
        number,
        unit="nits",
        normalized_key="value",
        status=status,
        quality_flags=quality_flags,
    )


def _parse_zones(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("zones", value)
    if unknown is not None:
        return unknown
    text = _normalize_text(value)
    if "千级" in text and "分区" in text:
        return ParamParseResult(
            parser_name="zones",
            parser_status=ParamParserStatus.PARSED,
            value_presence=M03_VALUE_PRESENT,
            normalized_value={"level": "thousand_level", "exact": False},
            value_text=_value_text(value),
            unit="zones",
            value_level="thousand_level",
            quality_flags=["zone_level_not_exact"],
        )
    number = _first_decimal(value)
    if number is None:
        return _failed_result("zones", value, "zone_count_not_found")
    return _number_result("zones", value, number, unit="zones", normalized_key="value")


def _parse_ports(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("ports", value)
    if unknown is not None:
        return unknown
    text = _normalize_text(value)
    version_match = HDMI_VERSION_PATTERN.search(text)
    version = version_match.group("version") if version_match else None
    count_text = text
    if version_match is not None:
        count_text = f"{text[: version_match.start()]} {text[version_match.end() :]}"
    numbers = _decimal_values(count_text)
    port_count: Decimal | None = None
    if numbers:
        port_count = numbers[0]
    if version is None and port_count is None:
        return _failed_result("ports", value, "port_count_or_version_not_found")

    quality_flags: list[str] = []
    if version is not None and port_count is None:
        quality_flags.append("hdmi_version_without_count")
    normalized_value = {
        "hdmi_version": version,
        "port_count": _json_number(port_count) if port_count is not None else None,
    }
    return ParamParseResult(
        parser_name="ports",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=normalized_value,
        numeric_value=port_count,
        value_text=_value_text(value),
        unit="ports" if port_count is not None else None,
        quality_flags=quality_flags,
    )


def _parse_gb(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("gb", value)
    if unknown is not None:
        return unknown
    values = _decimal_values(value)
    if not values:
        return _failed_result("gb", value, "gb_not_found")

    selected = values[0]
    param_text = _normalize_text(" ".join(_present_strings([context.param_code, context.param_name, context.clean_param_name])))
    if len(values) > 1 and any(token in param_text for token in ["rom", "存储", "storage"]):
        selected = values[-1]
    elif len(values) > 1 and any(token in param_text for token in ["ram", "运行内存", "内存"]):
        selected = values[0]
    normalized_value: dict[str, Any] = {
        "value": _json_number(selected),
        "unit": "GB",
    }
    if len(values) > 1:
        normalized_value["values_gb"] = [_json_number(item) for item in values]
    return ParamParseResult(
        parser_name="gb",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=normalized_value,
        numeric_value=selected,
        value_text=_value_text(value),
        unit="GB",
    )


def _parse_percentage(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("percentage", value)
    if unknown is not None:
        return unknown
    number = _first_decimal(value)
    if number is None or "%" not in _value_text(value):
        return _failed_result("percentage", value, "percentage_not_found")
    return _number_result("percentage", value, number, unit="%", normalized_key="value")


def _parse_boolean_keyword(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("boolean_keyword", value)
    if unknown is not None:
        return unknown
    normalized = _normalize_text(value)
    if normalized in {_normalize_text(item) for item in TRUE_LITERALS}:
        parsed_value = True
    elif normalized in {_normalize_text(item) for item in FALSE_LITERALS}:
        parsed_value = False
    else:
        return _failed_result("boolean_keyword", value, "boolean_keyword_not_found")
    return ParamParseResult(
        parser_name="boolean_keyword",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=parsed_value,
        value_text=_value_text(value),
    )


def _parse_enum_keyword(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("enum_keyword", value)
    if unknown is not None:
        return unknown
    text = _normalize_text(value)
    for enum_value in context.enum_values:
        if _normalize_text(enum_value) in text:
            return ParamParseResult(
                parser_name="enum_keyword",
                parser_status=ParamParserStatus.PARSED,
                value_presence=M03_VALUE_PRESENT,
                normalized_value=str(enum_value),
                value_text=_value_text(value),
            )
    for keyword in context.keywords:
        if _normalize_text(keyword) in text:
            return ParamParseResult(
                parser_name="enum_keyword",
                parser_status=ParamParserStatus.PARSED,
                value_presence=M03_VALUE_PRESENT,
                normalized_value=str(keyword),
                value_text=_value_text(value),
            )
    return _failed_result("enum_keyword", value, "enum_keyword_not_found")


def _parse_list_keyword(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("list_keyword", value)
    if unknown is not None:
        return unknown
    text = _value_text(value)
    normalized_text = _normalize_text(text)
    matched: list[str] = []
    for term in [*context.enum_values, *context.keywords]:
        if _normalize_text(term) in normalized_text:
            matched.append(str(term))
    if not matched:
        matched = [part.strip() for part in LIST_SPLIT_PATTERN.split(text) if part.strip()]
    if not matched:
        return _failed_result("list_keyword", value, "list_keyword_not_found")
    return ParamParseResult(
        parser_name="list_keyword",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=_unique_preserve_order(matched),
        value_text=text,
    )


def _parse_string(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("string", value)
    if unknown is not None:
        return unknown
    return ParamParseResult(
        parser_name="string",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=_value_text(value),
        value_text=_value_text(value),
    )


def _parse_number(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("number", value)
    if unknown is not None:
        return unknown
    number = _first_decimal(value)
    if number is None:
        return _failed_result("number", value, "number_not_found")
    return _number_result("number", value, number, unit=context.unit, normalized_key="value")


def _parse_watt(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("watt", value)
    if unknown is not None:
        return unknown
    if not re.search(r"(?<=\d)\s*w\b|瓦", _normalize_text(value), re.IGNORECASE):
        return _failed_result("watt", value, "watt_unit_not_found")
    number = _first_decimal(value)
    if number is None:
        return _failed_result("watt", value, "watt_not_found")
    return _number_result("watt", value, number, unit="W", normalized_key="value")


def _parse_ms(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("ms", value)
    if unknown is not None:
        return unknown
    if not re.search(r"(?<=\d)\s*ms\b|毫秒", _normalize_text(value), re.IGNORECASE):
        return _failed_result("ms", value, "ms_unit_not_found")
    number = _first_decimal(value)
    if number is None:
        return _failed_result("ms", value, "ms_not_found")
    return _number_result("ms", value, number, unit="ms", normalized_key="value")


def _parse_date_period(value: Any, context: ParamValueParserContext) -> ParamParseResult:
    unknown = _unknown_result("date_period", value)
    if unknown is not None:
        return unknown
    text = _value_text(value)
    year_match = re.search(r"(20\d{2})", text)
    normalized_value: dict[str, Any] = {"value": text}
    if year_match:
        normalized_value["year"] = int(year_match.group(1))
    return ParamParseResult(
        parser_name="date_period",
        parser_status=ParamParserStatus.PARSED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=normalized_value,
        value_text=text,
    )


def _unknown_result(parser_name: str, value: Any) -> ParamParseResult | None:
    if value is None:
        flag = "unknown_null"
    else:
        text = _normalize_text(value)
        flag = f"unknown_{text or 'empty'}" if text in UNKNOWN_LITERALS else None
    if flag is None:
        return None
    return ParamParseResult(
        parser_name=parser_name,
        parser_status=ParamParserStatus.UNKNOWN,
        value_presence=M03_VALUE_UNKNOWN,
        normalized_value=None,
        value_text=None if value is None else _value_text(value),
        quality_flags=[flag],
    )


def _failed_result(parser_name: str, value: Any, reason: str) -> ParamParseResult:
    return ParamParseResult(
        parser_name=parser_name,
        parser_status=ParamParserStatus.FAILED,
        value_presence=M03_VALUE_PRESENT,
        normalized_value=None,
        value_text=_value_text(value),
        quality_flags=[reason],
    )


def _number_result(
    parser_name: str,
    value: Any,
    number: Decimal,
    *,
    unit: str | None,
    normalized_key: str,
    status: ParamParserStatus = ParamParserStatus.PARSED,
    quality_flags: list[str] | None = None,
) -> ParamParseResult:
    return ParamParseResult(
        parser_name=parser_name,
        parser_status=status,
        value_presence=M03_VALUE_PRESENT,
        normalized_value={normalized_key: _json_number(number), "unit": unit},
        numeric_value=number,
        value_text=_value_text(value),
        unit=unit,
        quality_flags=quality_flags or [],
    )


def _first_decimal(value: Any) -> Decimal | None:
    values = _decimal_values(value)
    return values[0] if values else None


def _decimal_values(value: Any) -> list[Decimal]:
    text = _normalize_text(value).replace(",", "")
    values: list[Decimal] = []
    for match in NUMBER_PATTERN.finditer(text):
        try:
            values.append(Decimal(match.group(0)))
        except InvalidOperation:
            continue
    return values


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _normalize_text(value: Any) -> str:
    return _value_text(value).casefold().replace(" ", "")


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _present_strings(values: Iterable[str | None]) -> list[str]:
    return [str(value) for value in values if value]


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
