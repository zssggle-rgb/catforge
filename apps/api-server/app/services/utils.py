import re
from statistics import median
from typing import Any


MISSING_VALUES = {"", "-", "unknown", "null", "none", "nan", "na", "n/a", "未知", "无", "空"}
TRUE_VALUES = {"true", "yes", "y", "1", "是", "支持", "有", "具备", "包含"}
FALSE_VALUES = {"false", "no", "n", "0", "否", "不支持", "没有", "无"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_missing(value: Any) -> bool:
    return clean_text(value).lower() in MISSING_VALUES


def to_float(value: Any) -> float | None:
    if is_missing(value):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def to_bool(value: Any) -> bool | None:
    text = clean_text(value)
    lowered = text.lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    if is_missing(text):
        return None
    return None


def parse_number(text: Any) -> float | None:
    if is_missing(text):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", clean_text(text).replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def parse_unit_number(text: Any, units: tuple[str, ...]) -> float | None:
    if is_missing(text):
        return None
    pattern = r"(\d+(?:\.\d+)?)\s*(?:" + "|".join(re.escape(unit) for unit in units) + r")"
    match = re.search(pattern, clean_text(text), flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return parse_number(text)


def relation_level(score: float, thresholds: dict | None = None) -> str:
    thresholds = thresholds or {"main": 75, "secondary": 60, "opportunity": 45, "weak": 1}
    if score >= thresholds.get("main", 75):
        return "main"
    if score >= thresholds.get("secondary", 60):
        return "secondary"
    if score >= thresholds.get("opportunity", 45):
        return "opportunity"
    if score >= thresholds.get("weak", 1):
        return "weak"
    return "none"


def safe_median(values: list[float]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return float(median(filtered))


def unique_list(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values or []:
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output

