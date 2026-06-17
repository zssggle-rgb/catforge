"""M03 SKU parameter profile builder."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_conflicts import ParamValueConflictDraft
from app.services.core3_real_data.param_extraction_service import ExtractedParamValueDraft
from app.services.core3_real_data.param_extraction_schemas import StdParamDefinition, StdParamSeed


SKU_PARAM_PROFILE_ID_HASH_VERSION = "m03-sku-param-profile-id-v1"
SKU_PARAM_PROFILE_HASH_VERSION = "m03-sku-param-profile-v1"
PRESENT_VALUE = "present"
SCREEN_SIZE_PARAM_CODE = "screen_size_inch"
SCREEN_SIZE_MIN_INCH = Decimal("20")
SCREEN_SIZE_MAX_INCH = Decimal("130")
SCREEN_SIZE_EXACT_RAW_NAMES = frozenset({"尺寸"})
SCREEN_SIZE_RANGE_RAW_NAMES = frozenset({"尺寸段"})
SCREEN_SIZE_AREA_RAW_TOKENS = ("面积",)

CORE_PICTURE_PARAM_CODES = (
    "screen_size_inch",
    "resolution_class",
    "native_refresh_rate_hz",
    "system_refresh_rate_hz",
    "refresh_rate_hz",
    "peak_brightness_nits",
    "dimming_zones",
    "mini_led_flag",
    "hdr_format_list",
    "color_gamut_pct",
    "color_gamut_standard",
)
CORE_GAMING_PARAM_CODES = (
    "native_refresh_rate_hz",
    "system_refresh_rate_hz",
    "refresh_rate_hz",
    "hdmi_2_1_ports",
    "full_bandwidth_hdmi_flag",
    "vrr_flag",
    "allm_flag",
    "input_lag_ms",
    "game_mode_flag",
    "freesync_flag",
)
CORE_SYSTEM_PARAM_CODES = (
    "ram_gb",
    "storage_gb",
    "chipset_name",
    "os_name",
    "voice_control_flag",
    "far_field_voice_flag",
    "startup_ads_risk_flag",
)
CORE_EYE_CARE_PARAM_CODES = (
    "eye_dimming_freq_hz",
    "low_blue_light_flag",
    "flicker_free_flag",
    "ambient_light_sensor_flag",
    "anti_glare_flag",
    "elder_mode_flag",
    "child_mode_flag",
)


@dataclass(frozen=True)
class SkuParamProfileDraft:
    sku_param_profile_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    sku_code: str
    model_name: str | None
    param_values_json: dict[str, Any]
    core_picture_params_json: dict[str, Any]
    core_gaming_params_json: dict[str, Any]
    core_system_params_json: dict[str, Any]
    core_eye_care_params_json: dict[str, Any]
    param_completeness: Decimal
    known_param_count: int
    unknown_param_count: int
    conflict_count: int
    review_required_count: int
    evidence_ids: list[str]
    quality_summary_json: dict[str, Any]
    profile_hash: str
    seed_version: str
    rule_version: str

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "sku_param_profile_id": self.sku_param_profile_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "model_name": self.model_name,
            "param_values_json": self.param_values_json,
            "core_picture_params_json": self.core_picture_params_json,
            "core_gaming_params_json": self.core_gaming_params_json,
            "core_system_params_json": self.core_system_params_json,
            "core_eye_care_params_json": self.core_eye_care_params_json,
            "param_completeness": self.param_completeness,
            "known_param_count": self.known_param_count,
            "unknown_param_count": self.unknown_param_count,
            "conflict_count": self.conflict_count,
            "review_required_count": self.review_required_count,
            "evidence_ids": self.evidence_ids,
            "quality_summary_json": self.quality_summary_json,
            "profile_hash": self.profile_hash,
            "seed_version": self.seed_version,
            "rule_version": self.rule_version,
        }


class SkuParamProfileBuilder:
    """Build SKU-level parameter profiles from extracted values and conflicts."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        seed: StdParamSeed,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M03_SEED_VERSION,
        rule_version: str = CORE3_M03_RULE_VERSION,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.seed = seed
        self.seed_version = seed_version
        self.rule_version = rule_version
        self._param_defs = {param.param_code: param for param in seed.standard_params}
        self._core_param_codes = tuple(param.param_code for param in seed.standard_params if param.required_for_core)

    def build_profiles(
        self,
        values: Iterable[ExtractedParamValueDraft],
        conflicts: Iterable[ParamValueConflictDraft] = (),
    ) -> list[SkuParamProfileDraft]:
        value_list = list(values)
        conflict_list = list(conflicts)
        values_by_sku: dict[str, list[ExtractedParamValueDraft]] = {}
        for value in value_list:
            values_by_sku.setdefault(value.sku_code, []).append(value)
        conflicts_by_sku: dict[str, list[ParamValueConflictDraft]] = {}
        for conflict in conflict_list:
            conflicts_by_sku.setdefault(conflict.sku_code, []).append(conflict)

        sku_codes = sorted(set(values_by_sku) | set(conflicts_by_sku))
        return [
            self._build_one_profile(
                sku_code=sku_code,
                values=values_by_sku.get(sku_code, []),
                conflicts=conflicts_by_sku.get(sku_code, []),
            )
            for sku_code in sku_codes
        ]

    def _build_one_profile(
        self,
        *,
        sku_code: str,
        values: list[ExtractedParamValueDraft],
        conflicts: list[ParamValueConflictDraft],
    ) -> SkuParamProfileDraft:
        values_by_param: dict[str, list[ExtractedParamValueDraft]] = {}
        for value in values:
            values_by_param.setdefault(value.param_code, []).append(value)

        param_values_json: dict[str, Any] = {}
        main_values_by_param: dict[str, ExtractedParamValueDraft] = {}
        for param_code, candidates in sorted(values_by_param.items()):
            main_value = _select_main_value(candidates)
            main_values_by_param[param_code] = main_value
            param_values_json[param_code] = _param_value_entry(
                main_value,
                candidates,
                self._param_defs.get(param_code),
            )

        known_param_count = sum(1 for value in main_values_by_param.values() if value.value_presence == PRESENT_VALUE)
        unknown_param_count = sum(1 for value in main_values_by_param.values() if value.value_presence != PRESENT_VALUE)
        conflict_count = len(conflicts)
        review_required_count = sum(1 for value in main_values_by_param.values() if value.review_required) + len(
            conflicts
        )
        evidence_ids = _unique_preserve_order(
            evidence_id
            for value in values
            for evidence_id in value.evidence_ids
            if evidence_id
        )
        param_completeness = self._core_param_completeness(main_values_by_param)
        quality_summary_json = self._quality_summary(
            main_values_by_param,
            conflicts,
            known_param_count=known_param_count,
            unknown_param_count=unknown_param_count,
            review_required_count=review_required_count,
        )
        profile_hash = _build_profile_hash(
            sku_code=sku_code,
            param_values_json=param_values_json,
            param_completeness=param_completeness,
            unknown_param_count=unknown_param_count,
            conflict_count=conflict_count,
            quality_summary_json=quality_summary_json,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )

        return SkuParamProfileDraft(
            sku_param_profile_id=_build_profile_id(
                project_id=self.project_id,
                batch_id=self.batch_id,
                sku_code=sku_code,
                seed_version=self.seed_version,
                rule_version=self.rule_version,
            ),
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            sku_code=sku_code,
            model_name=_first_present(value.model_name for value in values),
            param_values_json=param_values_json,
            core_picture_params_json=_core_summary(main_values_by_param, CORE_PICTURE_PARAM_CODES),
            core_gaming_params_json=_core_summary(main_values_by_param, CORE_GAMING_PARAM_CODES),
            core_system_params_json=_core_summary(main_values_by_param, CORE_SYSTEM_PARAM_CODES),
            core_eye_care_params_json=_core_summary(main_values_by_param, CORE_EYE_CARE_PARAM_CODES),
            param_completeness=param_completeness,
            known_param_count=known_param_count,
            unknown_param_count=unknown_param_count,
            conflict_count=conflict_count,
            review_required_count=review_required_count,
            evidence_ids=evidence_ids,
            quality_summary_json=quality_summary_json,
            profile_hash=profile_hash,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )

    def _core_param_completeness(
        self,
        main_values_by_param: dict[str, ExtractedParamValueDraft],
    ) -> Decimal:
        total_core_count = len(self._core_param_codes)
        if total_core_count == 0:
            return Decimal("0.000000")
        known_core_count = sum(
            1
            for param_code in self._core_param_codes
            if param_code in main_values_by_param
            and main_values_by_param[param_code].value_presence == PRESENT_VALUE
        )
        return (Decimal(known_core_count) / Decimal(total_core_count)).quantize(Decimal("0.000001"))

    def _quality_summary(
        self,
        main_values_by_param: dict[str, ExtractedParamValueDraft],
        conflicts: list[ParamValueConflictDraft],
        *,
        known_param_count: int,
        unknown_param_count: int,
        review_required_count: int,
    ) -> dict[str, Any]:
        low_confidence_param_codes = sorted(
            param_code
            for param_code, value in main_values_by_param.items()
            if value.confidence_level in {"low", "unknown"}
        )
        review_required_param_codes = sorted(
            param_code for param_code, value in main_values_by_param.items() if value.review_required
        )
        missing_core_param_codes = sorted(set(self._core_param_codes) - set(main_values_by_param))
        quality_flag_counts = Counter(
            flag for value in main_values_by_param.values() for flag in value.quality_flags
        )
        conflict_type_counts = Counter(conflict.conflict_type for conflict in conflicts)
        return {
            "known_param_count": known_param_count,
            "unknown_param_count": unknown_param_count,
            "review_required_count": review_required_count,
            "missing_core_param_codes": missing_core_param_codes,
            "low_confidence_param_codes": low_confidence_param_codes,
            "review_required_param_codes": review_required_param_codes,
            "quality_flag_counts": dict(sorted(quality_flag_counts.items())),
            "conflict_type_counts": dict(sorted(conflict_type_counts.items())),
        }


def _select_main_value(candidates: list[ExtractedParamValueDraft]) -> ExtractedParamValueDraft:
    present_values = [value for value in candidates if value.value_presence == PRESENT_VALUE]
    pool = present_values or candidates
    if pool and pool[0].param_code == SCREEN_SIZE_PARAM_CODE:
        return _select_screen_size_main_value(pool)
    return sorted(
        pool,
        key=lambda value: (
            value.source_priority_rank,
            -value.confidence,
            value.param_value_id,
        ),
    )[0]


def _select_screen_size_main_value(candidates: list[ExtractedParamValueDraft]) -> ExtractedParamValueDraft:
    valid_values = [value for value in candidates if _screen_size_number(value) is not None]
    pool = valid_values or candidates
    return sorted(pool, key=_screen_size_candidate_sort_key)[0]


def _screen_size_candidate_sort_key(value: ExtractedParamValueDraft) -> tuple[int, int, Decimal, str]:
    return (
        _screen_size_field_rank(value),
        value.source_priority_rank,
        -value.confidence,
        value.param_value_id,
    )


def _screen_size_field_rank(value: ExtractedParamValueDraft) -> int:
    if _screen_size_number(value) is None:
        return 90
    raw_name = _raw_name(value)
    if raw_name in SCREEN_SIZE_EXACT_RAW_NAMES:
        return 0
    if value.source_type == "model_name":
        return 1
    if raw_name in SCREEN_SIZE_RANGE_RAW_NAMES or _looks_like_size_range(value.raw_param_value):
        return 4
    if "尺寸" in raw_name or "英寸" in raw_name or raw_name.endswith("寸"):
        return 2
    if value.source_type == "derived_from_claim":
        return 3
    return 5


def _screen_size_number(value: ExtractedParamValueDraft) -> Decimal | None:
    if value.value_presence != PRESENT_VALUE or value.numeric_value is None:
        return None
    if any(token in _raw_name(value) for token in SCREEN_SIZE_AREA_RAW_TOKENS):
        return None
    number = Decimal(str(value.numeric_value))
    if number < SCREEN_SIZE_MIN_INCH or number > SCREEN_SIZE_MAX_INCH:
        return None
    return number


def _raw_name(value: ExtractedParamValueDraft) -> str:
    return str(value.raw_param_name or "").strip()


def _looks_like_size_range(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and any(token in text for token in ("-", "~", "～", "至", "以上", "以下", ">=", "<=", "≥", "≤"))


def _param_value_entry(
    main_value: ExtractedParamValueDraft,
    candidates: list[ExtractedParamValueDraft],
    param_def: StdParamDefinition | None,
) -> dict[str, Any]:
    entry = {
        "param_code": main_value.param_code,
        "param_name": main_value.param_name,
        "param_group": main_value.param_group,
        "data_type": main_value.data_type,
        "normalized_value": main_value.normalized_value,
        "numeric_value": str(main_value.numeric_value) if main_value.numeric_value is not None else None,
        "value_text": main_value.value_text,
        "unit": main_value.unit,
        "value_level": main_value.value_level,
        "value_presence": main_value.value_presence,
        "source_type": main_value.source_type,
        "source_priority_rank": main_value.source_priority_rank,
        "confidence": str(main_value.confidence),
        "confidence_level": main_value.confidence_level,
        "evidence_ids": main_value.evidence_ids,
        "quality_flags": main_value.quality_flags,
        "review_required": main_value.review_required,
        "conflict_flag": main_value.conflict_flag,
        "conflict_id": main_value.conflict_id,
        "param_value_id": main_value.param_value_id,
    }
    if param_def is not None:
        entry["required_for_core"] = param_def.required_for_core
    if len(candidates) > 1:
        entry["candidates"] = [_candidate_entry(candidate) for candidate in candidates]
    return entry


def _candidate_entry(value: ExtractedParamValueDraft) -> dict[str, Any]:
    return {
        "param_value_id": value.param_value_id,
        "normalized_value": value.normalized_value,
        "numeric_value": str(value.numeric_value) if value.numeric_value is not None else None,
        "value_presence": value.value_presence,
        "source_type": value.source_type,
        "confidence": str(value.confidence),
        "evidence_ids": value.evidence_ids,
        "quality_flags": value.quality_flags,
        "review_required": value.review_required,
        "conflict_flag": value.conflict_flag,
        "conflict_id": value.conflict_id,
    }


def _core_summary(
    main_values_by_param: dict[str, ExtractedParamValueDraft],
    param_codes: Iterable[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for param_code in param_codes:
        value = main_values_by_param.get(param_code)
        if value is None:
            continue
        summary[param_code] = {
            "normalized_value": value.normalized_value,
            "numeric_value": str(value.numeric_value) if value.numeric_value is not None else None,
            "unit": value.unit,
            "value_presence": value.value_presence,
            "confidence": str(value.confidence),
            "confidence_level": value.confidence_level,
            "review_required": value.review_required,
            "conflict_flag": value.conflict_flag,
            "evidence_ids": value.evidence_ids,
            "quality_flags": value.quality_flags,
        }
    return summary


def _build_profile_id(
    *,
    project_id: str,
    batch_id: str,
    sku_code: str,
    seed_version: str,
    rule_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "seed_version": seed_version,
            "rule_version": rule_version,
        },
        version=SKU_PARAM_PROFILE_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m03profile_{digest[:32]}"


def _build_profile_hash(**payload: Any) -> str:
    return stable_hash(payload, version=SKU_PARAM_PROFILE_HASH_VERSION)


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _first_present(values: Iterable[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
