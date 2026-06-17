"""M03 raw parameter field profiling service."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

from app.services.core3_real_data.constants import (
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    Core3CategoryCode,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ValuePresenceStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_extraction_schemas import (
    ParamCandidateStatus,
    ParamMatchType,
    ParamReviewStatus,
)
from app.services.core3_real_data.param_field_matcher import ParamFieldMatch, ParamFieldNormalizer


PARAM_FIELD_PROFILE_HASH_VERSION = "m03-field-profile-v1"
PARAM_FIELD_PROFILE_ID_HASH_VERSION = "m03-field-profile-id-v1"
DEFAULT_ALLOWED_EVIDENCE_TYPES = frozenset({Core3EvidenceType.PARAM_RAW.value})
PRESENT_VALUE = Core3ValuePresenceStatus.PRESENT.value
UNKNOWN_VALUE_PRESENCES = frozenset(
    {
        Core3ValuePresenceStatus.NULL.value,
        Core3ValuePresenceStatus.EMPTY.value,
        Core3ValuePresenceStatus.DASH.value,
        Core3ValuePresenceStatus.UNKNOWN_LITERAL.value,
        Core3ValuePresenceStatus.MISSING_COLUMN.value,
    }
)
BOOLEAN_TRUE_VALUES = frozenset({"是", "有", "支持", "true", "yes", "y", "1"})
BOOLEAN_FALSE_VALUES = frozenset({"否", "无", "不支持", "false", "no", "n", "0"})
UNIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("inch", re.compile(r"(?:英寸|寸|\binch\b)", re.IGNORECASE)),
    ("hz", re.compile(r"hz", re.IGNORECASE)),
    ("nits", re.compile(r"(?:nits?|尼特)", re.IGNORECASE)),
    ("gb", re.compile(r"gb|(?<![a-z])g(?![a-z])", re.IGNORECASE)),
    ("分区", re.compile(r"(?:分区|zones?)", re.IGNORECASE)),
    ("w", re.compile(r"(?<=\d)\s*w\b|瓦", re.IGNORECASE)),
    ("ms", re.compile(r"(?<=\d)\s*ms\b|毫秒", re.IGNORECASE)),
    ("%", re.compile(r"%|％")),
)
NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class ParamFieldEvidence:
    evidence_id: str
    sku_code: str | None
    raw_param_name: str | None
    clean_param_name: str
    clean_param_value: Any
    value_presence: str


@dataclass(frozen=True)
class ParamFieldProfileDraft:
    field_profile_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    raw_param_name: str | None
    clean_param_name: str
    normalized_param_name: str
    occurrence_count: int
    sku_coverage_count: int
    sku_coverage_rate: Decimal
    unknown_count: int
    unknown_rate: Decimal
    present_count: int
    top_values_json: list[dict[str, Any]]
    value_pattern_summary_json: dict[str, Any]
    matched_param_code: str | None
    matched_param_name: str | None
    param_group: str | None
    match_type: str
    alias_confidence: Decimal
    candidate_status: str
    review_required: bool
    review_status: str
    review_reason: dict[str, Any] | None
    evidence_ids: list[str]
    field_profile_hash: str
    seed_version: str
    rule_version: str

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "field_profile_id": self.field_profile_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "raw_param_name": self.raw_param_name,
            "clean_param_name": self.clean_param_name,
            "normalized_param_name": self.normalized_param_name,
            "occurrence_count": self.occurrence_count,
            "sku_coverage_count": self.sku_coverage_count,
            "sku_coverage_rate": self.sku_coverage_rate,
            "unknown_count": self.unknown_count,
            "unknown_rate": self.unknown_rate,
            "present_count": self.present_count,
            "top_values_json": self.top_values_json,
            "value_pattern_summary_json": self.value_pattern_summary_json,
            "matched_param_code": self.matched_param_code,
            "matched_param_name": self.matched_param_name,
            "param_group": self.param_group,
            "match_type": self.match_type,
            "alias_confidence": self.alias_confidence,
            "candidate_status": self.candidate_status,
            "review_required": self.review_required,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "evidence_ids": self.evidence_ids,
            "field_profile_hash": self.field_profile_hash,
            "seed_version": self.seed_version,
            "rule_version": self.rule_version,
        }

    def with_match(self, match: ParamFieldMatch) -> "ParamFieldProfileDraft":
        return replace(
            self,
            matched_param_code=match.matched_param_code,
            matched_param_name=match.matched_param_name,
            param_group=match.param_group,
            match_type=match.match_type.value,
            alias_confidence=match.alias_confidence,
            candidate_status=match.candidate_status.value,
            review_required=match.review_required,
            review_status=match.review_status.value,
            review_reason=match.review_reason,
            field_profile_hash=_build_field_profile_hash(
                clean_param_name=self.clean_param_name,
                normalized_param_name=self.normalized_param_name,
                occurrence_count=self.occurrence_count,
                sku_coverage_count=self.sku_coverage_count,
                sku_coverage_rate=self.sku_coverage_rate,
                unknown_count=self.unknown_count,
                unknown_rate=self.unknown_rate,
                top_values_json=self.top_values_json,
                value_pattern_summary_json=self.value_pattern_summary_json,
                matched_param_code=match.matched_param_code,
                match_type=match.match_type.value,
                alias_confidence=match.alias_confidence,
                seed_version=self.seed_version,
                rule_version=self.rule_version,
            ),
        )


class ParamFieldProfiler:
    """Aggregate current M02 param_raw evidence into field profiles."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M03_SEED_VERSION,
        rule_version: str = CORE3_M03_RULE_VERSION,
        top_value_limit: int = 10,
        allowed_evidence_types: Iterable[str] = DEFAULT_ALLOWED_EVIDENCE_TYPES,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.seed_version = seed_version
        self.rule_version = rule_version
        self.top_value_limit = top_value_limit
        self.allowed_evidence_types = frozenset(allowed_evidence_types)

    def build_profiles(
        self,
        evidence_records: Iterable[Any],
        *,
        total_sku_count: int | None = None,
    ) -> list[ParamFieldProfileDraft]:
        normalized_records = [record for record in self._iter_field_evidence(evidence_records)]
        if not normalized_records:
            return []

        denominator = total_sku_count if total_sku_count is not None else _count_distinct_sku(normalized_records)
        groups: dict[str, list[ParamFieldEvidence]] = defaultdict(list)
        for record in normalized_records:
            groups[ParamFieldNormalizer.normalize(record.clean_param_name)].append(record)

        profiles = [
            self._build_profile(group_records=records, total_sku_count=denominator)
            for _, records in sorted(groups.items(), key=lambda item: item[0])
        ]
        return profiles

    def _iter_field_evidence(self, evidence_records: Iterable[Any]) -> Iterable[ParamFieldEvidence]:
        for record in evidence_records:
            evidence_type = _field_value(record, "evidence_type")
            if evidence_type is not None and _enum_value(evidence_type) not in self.allowed_evidence_types:
                continue
            evidence_status = _field_value(record, "evidence_status")
            if evidence_status is not None and _enum_value(evidence_status) != Core3EvidenceStatus.CURRENT.value:
                continue
            is_current = _field_value(record, "is_current")
            if is_current is False:
                continue

            clean_param_name = _first_non_empty(
                _field_value(record, "clean_param_name"),
                _field_value(record, "clean_attr_name"),
                _field_value(record, "evidence_field"),
                _field_value(record, "clean_field"),
                _field_value(record, "raw_param_name"),
                _field_value(record, "raw_attr_name"),
                _field_value(record, "raw_field"),
            )
            if clean_param_name is None:
                continue
            clean_param_value = _first_existing(
                _field_value(record, "clean_param_value"),
                _field_value(record, "clean_attr_value"),
                _field_value(record, "clean_value"),
                _field_value(record, "text_value"),
                _field_value(record, "normalized_value"),
                _field_value(record, "raw_value"),
            )
            value_presence = _field_value(record, "value_presence") or _classify_presence(clean_param_value)
            classified_presence = _classify_presence(clean_param_value)
            if _enum_value(value_presence) == PRESENT_VALUE and classified_presence != PRESENT_VALUE:
                value_presence = classified_presence
            yield ParamFieldEvidence(
                evidence_id=str(_first_non_empty(_field_value(record, "evidence_id"), "")),
                sku_code=_optional_string(_field_value(record, "sku_code")),
                raw_param_name=_optional_string(
                    _first_non_empty(
                        _field_value(record, "raw_param_name"),
                        _field_value(record, "raw_attr_name"),
                        _field_value(record, "raw_field"),
                        _field_value(record, "evidence_field"),
                    )
                ),
                clean_param_name=str(clean_param_name).strip(),
                clean_param_value=clean_param_value,
                value_presence=_enum_value(value_presence),
            )

    def _build_profile(
        self,
        *,
        group_records: list[ParamFieldEvidence],
        total_sku_count: int,
    ) -> ParamFieldProfileDraft:
        first_record = group_records[0]
        evidence_ids = _unique_preserve_order(record.evidence_id for record in group_records if record.evidence_id)
        occurrence_count = len(group_records)
        sku_coverage_count = _count_distinct_sku(group_records)
        present_values = [
            record.clean_param_value
            for record in group_records
            if _presence_is_present(record.value_presence)
        ]
        unknown_count = occurrence_count - len(present_values)
        top_values_json = _top_values(present_values, limit=self.top_value_limit)
        value_pattern_summary_json = _value_pattern_summary(present_values)
        sku_coverage_rate = _rate(sku_coverage_count, total_sku_count)
        unknown_rate = _rate(unknown_count, occurrence_count)
        normalized_param_name = ParamFieldNormalizer.normalize(first_record.clean_param_name)
        field_profile_id = _build_field_profile_id(
            project_id=self.project_id,
            batch_id=self.batch_id,
            clean_param_name=first_record.clean_param_name,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )
        field_profile_hash = _build_field_profile_hash(
            clean_param_name=first_record.clean_param_name,
            normalized_param_name=normalized_param_name,
            occurrence_count=occurrence_count,
            sku_coverage_count=sku_coverage_count,
            sku_coverage_rate=sku_coverage_rate,
            unknown_count=unknown_count,
            unknown_rate=unknown_rate,
            top_values_json=top_values_json,
            value_pattern_summary_json=value_pattern_summary_json,
            matched_param_code=None,
            match_type=ParamMatchType.UNMAPPED.value,
            alias_confidence=Decimal("0.0000"),
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )

        return ParamFieldProfileDraft(
            field_profile_id=field_profile_id,
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            raw_param_name=first_record.raw_param_name,
            clean_param_name=first_record.clean_param_name,
            normalized_param_name=normalized_param_name,
            occurrence_count=occurrence_count,
            sku_coverage_count=sku_coverage_count,
            sku_coverage_rate=sku_coverage_rate,
            unknown_count=unknown_count,
            unknown_rate=unknown_rate,
            present_count=len(present_values),
            top_values_json=top_values_json,
            value_pattern_summary_json=value_pattern_summary_json,
            matched_param_code=None,
            matched_param_name=None,
            param_group=None,
            match_type=ParamMatchType.UNMAPPED.value,
            alias_confidence=Decimal("0.0000"),
            candidate_status=ParamCandidateStatus.CANDIDATE.value,
            review_required=False,
            review_status=ParamReviewStatus.AUTO_PASS.value,
            review_reason=None,
            evidence_ids=evidence_ids,
            field_profile_hash=field_profile_hash,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )


def _build_field_profile_id(
    *,
    project_id: str,
    batch_id: str,
    clean_param_name: str,
    seed_version: str,
    rule_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "clean_param_name": clean_param_name,
            "seed_version": seed_version,
            "rule_version": rule_version,
        },
        version=PARAM_FIELD_PROFILE_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m03fp_{digest[:32]}"


def _build_field_profile_hash(**payload: Any) -> str:
    return stable_hash(payload, version=PARAM_FIELD_PROFILE_HASH_VERSION)


def _field_value(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def _first_existing(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _classify_presence(value: Any) -> str:
    if value is None:
        return Core3ValuePresenceStatus.NULL.value
    text = str(value).strip()
    if text == "":
        return Core3ValuePresenceStatus.EMPTY.value
    if text in {"-", "--", "---", "—", "–"}:
        return Core3ValuePresenceStatus.DASH.value
    if text.casefold() in {"unknown", "unk", "null", "none", "n/a", "na", "暂无", "未知", "不详", "无数据"}:
        return Core3ValuePresenceStatus.UNKNOWN_LITERAL.value
    return Core3ValuePresenceStatus.PRESENT.value


def _presence_is_present(value_presence: str) -> bool:
    return _enum_value(value_presence) == PRESENT_VALUE


def _count_distinct_sku(records: Iterable[ParamFieldEvidence]) -> int:
    return len({record.sku_code for record in records if record.sku_code})


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _top_values(values: Iterable[Any], *, limit: int) -> list[dict[str, Any]]:
    counter = Counter(_value_to_text(value) for value in values)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _value_pattern_summary(values: list[Any]) -> dict[str, Any]:
    value_texts = [_value_to_text(value) for value in values]
    unit_candidates = _unit_candidates(value_texts)
    number_like_count = sum(1 for value in value_texts if NUMBER_PATTERN.search(value))
    boolean_like_count = sum(1 for value in value_texts if _is_boolean_like(value))
    distinct_values = sorted(set(value_texts))
    enum_like_count = len(value_texts) if 0 < len(distinct_values) <= 12 else 0

    return {
        "present_value_count": len(value_texts),
        "distinct_value_count": len(distinct_values),
        "number_like_count": number_like_count,
        "boolean_like_count": boolean_like_count,
        "enum_like_count": enum_like_count,
        "unit_candidates": unit_candidates,
        "sample_values": distinct_values[:10],
    }


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict | list):
        return str(value)
    return str(value).strip()


def _unit_candidates(value_texts: Iterable[str]) -> list[str]:
    candidates: set[str] = set()
    for value_text in value_texts:
        for unit, pattern in UNIT_PATTERNS:
            if pattern.search(value_text):
                candidates.add(unit)
    return sorted(candidates)


def _is_boolean_like(value_text: str) -> bool:
    normalized = ParamFieldNormalizer.normalize_value_text(value_text)
    return normalized in BOOLEAN_TRUE_VALUES or normalized in BOOLEAN_FALSE_VALUES
