"""M03 field normalizer and standard parameter matcher."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from app.services.core3_real_data.param_extraction_schemas import (
    ParamCandidateStatus,
    ParamMatchType,
    ParamReviewStatus,
    StdParamDefinition,
    StdParamSeed,
)


CONFIDENCE_BASE: dict[ParamMatchType, Decimal] = {
    ParamMatchType.EXACT_ALIAS: Decimal("0.95"),
    ParamMatchType.STANDARD_NAME: Decimal("0.93"),
    ParamMatchType.CONTAINS_ALIAS: Decimal("0.82"),
    ParamMatchType.KEYWORD: Decimal("0.70"),
    ParamMatchType.VALUE_PATTERN: Decimal("0.55"),
    ParamMatchType.UNMAPPED: Decimal("0.00"),
}

CORE_TECH_TERMS = frozenset(
    {
        "hdr",
        "hdmi",
        "miniled",
        "mini led",
        "cpu",
        "gpu",
        "ram",
        "rom",
        "dolby",
        "刷新",
        "高刷",
        "亮度",
        "分区",
        "色域",
        "芯片",
        "内存",
        "存储",
        "杜比",
    }
)


class ParamFieldNormalizer:
    """Normalize raw parameter field names for matching only."""

    _bracket_content_pattern = re.compile(r"[\(（][^\)）]*[\)）]")
    _separator_pattern = re.compile(r"[\s_\-—–/\\·]+")

    @classmethod
    def normalize(cls, value: Any) -> str:
        if value is None:
            return ""
        text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
        text = cls._bracket_content_pattern.sub("", text)
        text = cls._separator_pattern.sub("", text)
        return text

    @classmethod
    def normalize_value_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return unicodedata.normalize("NFKC", str(value)).strip().casefold()


@dataclass(frozen=True)
class ParamFieldMatch:
    matched_param_code: str | None
    matched_param_name: str | None
    param_group: str | None
    match_type: ParamMatchType
    alias_confidence: Decimal
    candidate_status: ParamCandidateStatus
    review_required: bool
    review_status: ParamReviewStatus
    review_reason: dict[str, Any] | None
    matched_by: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "matched_param_code": self.matched_param_code,
            "matched_param_name": self.matched_param_name,
            "param_group": self.param_group,
            "match_type": self.match_type.value,
            "alias_confidence": self.alias_confidence,
            "candidate_status": self.candidate_status.value,
            "review_required": self.review_required,
            "review_status": self.review_status.value,
            "review_reason": self.review_reason,
        }


@dataclass(frozen=True)
class _MatchCandidate:
    param: StdParamDefinition
    match_type: ParamMatchType
    matched_by: str


@dataclass(frozen=True)
class ParamMappingGuardRule:
    raw_name_keywords: tuple[str, ...]
    blocked_param_codes: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True)
class _GuardResult:
    candidates: list[_MatchCandidate]
    blocked_param_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]


PARAM_MAPPING_GUARD_RULES: tuple[ParamMappingGuardRule, ...] = (
    ParamMappingGuardRule(
        raw_name_keywords=("内置wifi", "wifi", "wi-fi", "无线网络"),
        blocked_param_codes=("speaker_power_w", "speaker_channel", "audio_system"),
        reason_code="wifi_field_cannot_support_audio_param",
    ),
    ParamMappingGuardRule(
        raw_name_keywords=(
            "hdmi数量",
            "usb数量",
            "三维电视",
            "屏幕比例",
            "屏幕面积",
            "整机厚度",
            "整机宽度",
            "水平视角",
            "垂直视角",
            "灯珠数量",
            "能效指数",
            "被动待机功率",
            "边框",
            "机身厚度",
            "曲面弧度",
            "ic型号",
        ),
        blocked_param_codes=("color_depth_bit",),
        reason_code="non_color_field_cannot_support_color_depth",
    ),
    ParamMappingGuardRule(
        raw_name_keywords=("人工智能", "全屋智控", "无缝贴墙"),
        blocked_param_codes=("motion_compensation_flag", "memc_support_flag"),
        reason_code="smart_or_installation_field_cannot_support_motion_compensation",
    ),
    ParamMappingGuardRule(
        raw_name_keywords=("面板刷新率", "屏幕刷新率", "刷新率"),
        blocked_param_codes=("panel_type",),
        reason_code="refresh_field_cannot_support_panel_type",
    ),
    ParamMappingGuardRule(
        raw_name_keywords=("hdr",),
        blocked_param_codes=("peak_brightness_nits", "instant_peak_brightness_nits", "sustained_brightness_nits"),
        reason_code="hdr_field_cannot_support_brightness_without_nits_value",
    ),
)

PARAM_RAW_NAME_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "color_depth_bit": ("色深", "色彩深度", "色彩位深", "位深", "bit", "10bit", "12bit"),
    "speaker_power_w": ("音", "声", "喇叭", "扬声器", "功率", "speaker", "audio"),
    "speaker_channel": ("音", "声", "喇叭", "扬声器", "声道", "speaker", "audio"),
    "motion_compensation_flag": ("运动", "补偿", "memc", "流畅", "防抖"),
    "mini_led_flag": ("mini", "miniled", "mini led", "迷你led", "背光", "u+mini"),
    "peak_brightness_nits": ("亮度", "峰值", "尼特", "nits", "xdr"),
    "panel_type": ("面板", "屏体", "屏幕类型", "面板类型"),
    "hdmi_port_count": ("hdmi",),
    "usb_port_count": ("usb",),
    "energy_efficiency_index": ("能效", "能源效率"),
    "body_thickness_mm": ("厚度", "机身厚度", "整机厚度"),
}


class ParamAliasMatcher:
    """Match a raw parameter field profile to one standard parameter definition."""

    def __init__(self, seed: StdParamSeed) -> None:
        self.seed = seed
        self._params = list(seed.standard_params)
        self._alias_entries = self._build_alias_entries(self._params)
        self._standard_name_entries = [
            (ParamFieldNormalizer.normalize(param.param_name), param)
            for param in self._params
            if ParamFieldNormalizer.normalize(param.param_name)
        ]
        self._keyword_entries = self._build_keyword_entries(self._params)

    def match_profile(self, profile: Any) -> ParamFieldMatch:
        clean_param_name = _value(profile, "clean_param_name") or _value(profile, "raw_param_name") or ""
        normalized_param_name = _value(profile, "normalized_param_name") or ParamFieldNormalizer.normalize(
            clean_param_name
        )
        coverage_rate = _decimal(_value(profile, "sku_coverage_rate"), Decimal("0"))
        unknown_rate = _decimal(_value(profile, "unknown_rate"), Decimal("0"))
        pattern_summary = _value(profile, "value_pattern_summary_json") or {}

        candidates = self._find_candidates(
            clean_param_name=str(clean_param_name),
            normalized_param_name=str(normalized_param_name),
            pattern_summary=pattern_summary,
        )
        if not candidates:
            return self._unmapped_match(
                clean_param_name=str(clean_param_name),
                normalized_param_name=str(normalized_param_name),
                coverage_rate=coverage_rate,
                unknown_rate=unknown_rate,
                pattern_summary=pattern_summary,
            )

        guard_result = self._apply_mapping_guard(
            candidates,
            clean_param_name=str(clean_param_name),
            normalized_param_name=str(normalized_param_name),
        )
        candidates = guard_result.candidates
        if not candidates:
            return self._guard_blocked_match(
                coverage_rate=coverage_rate,
                blocked_param_codes=guard_result.blocked_param_codes,
                reason_codes=guard_result.reason_codes,
            )

        selected = candidates[0]
        confidence = CONFIDENCE_BASE[selected.match_type]
        review_reasons: list[str] = []

        if coverage_rate >= Decimal("0.800000") and self._profile_matches_param_parser(
            selected.param,
            pattern_summary,
        ):
            confidence += Decimal("0.03")
        if unknown_rate > Decimal("0.500000"):
            confidence -= Decimal("0.10")
            review_reasons.append("unknown_rate_gt_50_percent")
        if len(candidates) > 1:
            confidence -= Decimal("0.15")
            review_reasons.append("multiple_standard_param_candidates")
        if _bool_value(selected.param.required_for_core) and selected.match_type not in {
            ParamMatchType.EXACT_ALIAS,
            ParamMatchType.STANDARD_NAME,
        }:
            review_reasons.append("core_param_requires_exact_or_standard_review")
        if guard_result.reason_codes:
            review_reasons.append("param_mapping_guard_removed_conflicting_candidate")

        confidence = _bounded_confidence(confidence)
        review_required = bool(review_reasons)
        review_reason = None
        if review_required:
            review_reason = {
                "reason_codes": review_reasons,
                "candidate_param_codes": [candidate.param.param_code for candidate in candidates],
                "matched_by": selected.matched_by,
            }
            if guard_result.blocked_param_codes:
                review_reason["guard_blocked_param_codes"] = list(guard_result.blocked_param_codes)
                review_reason["guard_reason_codes"] = list(guard_result.reason_codes)

        return ParamFieldMatch(
            matched_param_code=selected.param.param_code,
            matched_param_name=selected.param.param_name,
            param_group=str(selected.param.param_group) if selected.param.param_group is not None else None,
            match_type=selected.match_type,
            alias_confidence=confidence,
            candidate_status=(
                ParamCandidateStatus.REVIEW_REQUIRED if review_required else ParamCandidateStatus.MATCHED
            ),
            review_required=review_required,
            review_status=(
                ParamReviewStatus.REVIEW_REQUIRED if review_required else ParamReviewStatus.AUTO_PASS
            ),
            review_reason=review_reason,
            matched_by=selected.matched_by,
        )

    def _apply_mapping_guard(
        self,
        candidates: list[_MatchCandidate],
        *,
        clean_param_name: str,
        normalized_param_name: str,
    ) -> _GuardResult:
        raw_name_text = _normalized_guard_text(f"{clean_param_name} {normalized_param_name}")
        accepted: list[_MatchCandidate] = []
        blocked_codes: list[str] = []
        reason_codes: list[str] = []
        for candidate in candidates:
            candidate_reasons = _mapping_guard_reasons(raw_name_text, candidate.param.param_code)
            if candidate_reasons:
                blocked_codes.append(candidate.param.param_code)
                reason_codes.extend(candidate_reasons)
                continue
            accepted.append(candidate)
        return _GuardResult(
            candidates=accepted,
            blocked_param_codes=tuple(dict.fromkeys(blocked_codes)),
            reason_codes=tuple(dict.fromkeys(reason_codes)),
        )

    def _guard_blocked_match(
        self,
        *,
        coverage_rate: Decimal,
        blocked_param_codes: tuple[str, ...],
        reason_codes: tuple[str, ...],
    ) -> ParamFieldMatch:
        return ParamFieldMatch(
            matched_param_code=None,
            matched_param_name=None,
            param_group=None,
            match_type=ParamMatchType.UNMAPPED,
            alias_confidence=Decimal("0.0000"),
            candidate_status=ParamCandidateStatus.CANDIDATE,
            review_required=True,
            review_status=ParamReviewStatus.REVIEW_REQUIRED,
            review_reason={
                "reason_codes": ["param_mapping_guard_blocked", *reason_codes],
                "coverage_rate": str(coverage_rate),
                "blocked_param_codes": list(blocked_param_codes),
            },
        )

    def match_profiles(self, profiles: Iterable[Any]) -> list[ParamFieldMatch]:
        return [self.match_profile(profile) for profile in profiles]

    def apply_match(self, profile: Any) -> Any:
        if not hasattr(profile, "with_match"):
            raise TypeError("profile must provide with_match(match)")
        return profile.with_match(self.match_profile(profile))

    def apply_matches(self, profiles: Iterable[Any]) -> list[Any]:
        return [self.apply_match(profile) for profile in profiles]

    def _find_candidates(
        self,
        *,
        clean_param_name: str,
        normalized_param_name: str,
        pattern_summary: dict[str, Any],
    ) -> list[_MatchCandidate]:
        exact_alias = [
            _MatchCandidate(param=param, match_type=ParamMatchType.EXACT_ALIAS, matched_by=alias)
            for alias, param in self._alias_entries
            if normalized_param_name == alias
        ]
        if exact_alias:
            return _dedupe_candidates(exact_alias)

        standard_name = [
            _MatchCandidate(param=param, match_type=ParamMatchType.STANDARD_NAME, matched_by=param.param_name)
            for normalized_name, param in self._standard_name_entries
            if normalized_param_name == normalized_name
        ]
        if standard_name:
            return _dedupe_candidates(standard_name)

        contains_alias = [
            _MatchCandidate(param=param, match_type=ParamMatchType.CONTAINS_ALIAS, matched_by=alias)
            for alias, param in self._alias_entries
            if len(alias) >= 2 and alias in normalized_param_name and alias != normalized_param_name
        ]
        if contains_alias:
            return _dedupe_candidates(contains_alias)

        searchable_value_text = ParamFieldNormalizer.normalize_value_text(
            " ".join(str(value) for value in pattern_summary.get("sample_values", []))
        )
        keyword = [
            _MatchCandidate(param=param, match_type=ParamMatchType.KEYWORD, matched_by=keyword_text)
            for keyword_text, param in self._keyword_entries
            if keyword_text
            and (
                keyword_text in normalized_param_name
                or keyword_text in searchable_value_text
                or ParamFieldNormalizer.normalize_value_text(keyword_text) in searchable_value_text
            )
        ]
        if keyword:
            return _dedupe_candidates(keyword)

        value_pattern = [
            _MatchCandidate(param=param, match_type=ParamMatchType.VALUE_PATTERN, matched_by="value_pattern")
            for param in self._params
            if self._profile_matches_param_parser(param, pattern_summary)
            and self._value_pattern_candidate_allowed(
                param,
                clean_param_name=clean_param_name,
                normalized_param_name=normalized_param_name,
                pattern_summary=pattern_summary,
            )
        ]
        return _dedupe_candidates(value_pattern)

    def _unmapped_match(
        self,
        *,
        clean_param_name: str,
        normalized_param_name: str,
        coverage_rate: Decimal,
        unknown_rate: Decimal,
        pattern_summary: dict[str, Any],
    ) -> ParamFieldMatch:
        candidate_like = coverage_rate >= Decimal("0.300000") or self._has_core_tech_term(
            clean_param_name,
            normalized_param_name,
            pattern_summary,
        )
        no_effective_values = unknown_rate > Decimal("0.800000") and not pattern_summary.get("sample_values")
        if candidate_like and not no_effective_values:
            return ParamFieldMatch(
                matched_param_code=None,
                matched_param_name=None,
                param_group=None,
                match_type=ParamMatchType.UNMAPPED,
                alias_confidence=Decimal("0.0000"),
                candidate_status=ParamCandidateStatus.CANDIDATE,
                review_required=True,
                review_status=ParamReviewStatus.REVIEW_REQUIRED,
                review_reason={
                    "reason_codes": ["unmapped_high_coverage_or_core_tech_field"],
                    "coverage_rate": str(coverage_rate),
                },
            )
        return ParamFieldMatch(
            matched_param_code=None,
            matched_param_name=None,
            param_group=None,
            match_type=ParamMatchType.UNMAPPED,
            alias_confidence=Decimal("0.0000"),
            candidate_status=ParamCandidateStatus.IGNORED,
            review_required=False,
            review_status=ParamReviewStatus.AUTO_PASS,
            review_reason=None,
        )

    def _profile_matches_param_parser(
        self,
        param: StdParamDefinition,
        pattern_summary: dict[str, Any],
    ) -> bool:
        parser_names = set(param.value_parsers)
        unit_candidates = {str(item).casefold() for item in pattern_summary.get("unit_candidates", [])}
        sample_values = [str(item).casefold() for item in pattern_summary.get("sample_values", [])]
        number_like_count = int(pattern_summary.get("number_like_count") or 0)
        boolean_like_count = int(pattern_summary.get("boolean_like_count") or 0)
        sample_text = ParamFieldNormalizer.normalize_value_text(" ".join(sample_values))

        if "inch" in parser_names and unit_candidates & {"inch", "英寸", "寸"}:
            return True
        if "hz" in parser_names and unit_candidates & {"hz"}:
            return True
        if "nits" in parser_names and unit_candidates & {"nits", "nit", "尼特"}:
            return True
        if "zones" in parser_names and unit_candidates & {"分区", "zones", "zone"}:
            return True
        if "gb" in parser_names and unit_candidates & {"gb", "g"}:
            return True
        if "watt" in parser_names and unit_candidates & {"w", "瓦"}:
            return True
        if "ms" in parser_names and unit_candidates & {"ms", "毫秒"}:
            return True
        if "percentage" in parser_names and unit_candidates & {"%"}:
            return True
        if "resolution" in parser_names and any(
            re.search(r"\b[48]k\b|3840\s*[x×]\s*2160|7680\s*[x×]\s*4320", value)
            for value in sample_values
        ):
            return True
        if "boolean_keyword" in parser_names and boolean_like_count:
            return True
        if ("enum_keyword" in parser_names or "list_keyword" in parser_names) and self._samples_hit_seed_terms(
            param,
            sample_text,
        ):
            return True
        return "number" in parser_names and number_like_count > 0

    def _samples_hit_seed_terms(self, param: StdParamDefinition, sample_text: str) -> bool:
        if not sample_text:
            return False
        seed_terms = [*param.enum_values, *param.keywords]
        for term in seed_terms:
            normalized_term = ParamFieldNormalizer.normalize_value_text(term)
            if normalized_term and normalized_term in sample_text:
                return True
        return False

    def _value_pattern_candidate_allowed(
        self,
        param: StdParamDefinition,
        *,
        clean_param_name: str,
        normalized_param_name: str,
        pattern_summary: dict[str, Any],
    ) -> bool:
        parser_names = set(param.value_parsers)
        if "boolean_keyword" not in parser_names:
            return True

        sample_text = ParamFieldNormalizer.normalize_value_text(
            " ".join(str(value) for value in pattern_summary.get("sample_values", []))
        )
        if self._samples_hit_seed_terms(param, sample_text):
            return True

        raw_text = _normalized_guard_text(f"{clean_param_name} {normalized_param_name}")
        semantic_terms = [
            param.param_name,
            *param.aliases,
            *param.keywords,
            *PARAM_RAW_NAME_REQUIREMENTS.get(param.param_code, ()),
        ]
        return any(_normalized_guard_text(term) in raw_text for term in semantic_terms if _normalized_guard_text(term))

    def _has_core_tech_term(
        self,
        clean_param_name: str,
        normalized_param_name: str,
        pattern_summary: dict[str, Any],
    ) -> bool:
        sample_text = ParamFieldNormalizer.normalize_value_text(
            " ".join(str(value) for value in pattern_summary.get("sample_values", []))
        )
        raw_text = f"{clean_param_name} {normalized_param_name} {sample_text}".casefold()
        return any(term.casefold().replace(" ", "") in raw_text.replace(" ", "") for term in CORE_TECH_TERMS)

    def _build_alias_entries(
        self,
        params: Iterable[StdParamDefinition],
    ) -> list[tuple[str, StdParamDefinition]]:
        entries: list[tuple[str, StdParamDefinition]] = []
        for param in params:
            for alias in param.aliases:
                normalized_alias = ParamFieldNormalizer.normalize(alias)
                if normalized_alias:
                    entries.append((normalized_alias, param))
        return entries

    def _build_keyword_entries(
        self,
        params: Iterable[StdParamDefinition],
    ) -> list[tuple[str, StdParamDefinition]]:
        entries: list[tuple[str, StdParamDefinition]] = []
        for param in params:
            for keyword in param.keywords:
                normalized_keyword = ParamFieldNormalizer.normalize(keyword)
                if len(normalized_keyword) >= 2:
                    entries.append((normalized_keyword, param))
        return entries


def _dedupe_candidates(candidates: list[_MatchCandidate]) -> list[_MatchCandidate]:
    deduped: list[_MatchCandidate] = []
    seen_codes: set[str] = set()
    for candidate in candidates:
        if candidate.param.param_code in seen_codes:
            continue
        deduped.append(candidate)
        seen_codes.add(candidate.param.param_code)
    return sorted(deduped, key=lambda item: int(item.param.priority or 0))


def _mapping_guard_reasons(raw_name_text: str, param_code: str) -> list[str]:
    reasons: list[str] = []
    for rule in PARAM_MAPPING_GUARD_RULES:
        if param_code not in rule.blocked_param_codes:
            continue
        if any(_normalized_guard_text(keyword) in raw_name_text for keyword in rule.raw_name_keywords):
            reasons.append(rule.reason_code)
    required_keywords = PARAM_RAW_NAME_REQUIREMENTS.get(param_code)
    if required_keywords and not any(_normalized_guard_text(keyword) in raw_name_text for keyword in required_keywords):
        reasons.append(f"{param_code}_raw_name_semantic_mismatch")
    return reasons


def _normalized_guard_text(value: str) -> str:
    return ParamFieldNormalizer.normalize(value).replace(" ", "")


def _value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _decimal(value: Any, default: Decimal) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _bounded_confidence(confidence: Decimal) -> Decimal:
    if confidence < Decimal("0"):
        return Decimal("0.0000")
    if confidence > Decimal("1"):
        return Decimal("1.0000")
    return confidence.quantize(Decimal("0.0001"))


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).casefold() in {"true", "1", "yes"}
