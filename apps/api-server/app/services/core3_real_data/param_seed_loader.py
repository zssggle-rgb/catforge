"""Seed loader for M03 standard parameter definitions."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.services.core3_real_data.constants import (
    CORE3_M03_SEED_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.param_extraction_schemas import (
    ParamDataType,
    ParamGroup,
    ParamSourceType,
    StdParamDefinition,
    StdParamSeed,
)


DEFAULT_PARAM_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "tv_core3_mvp_seed_v0_2.json"
)

REQUIRED_STANDARD_PARAM_FIELDS = (
    "param_code",
    "param_name",
    "data_type",
    "param_group",
    "aliases",
    "value_parsers",
    "source_types",
)

CORE_PARAM_CODES = frozenset(
    {
        "screen_size_inch",
        "resolution_class",
        "native_refresh_rate_hz",
        "peak_brightness_nits",
        "dimming_zones",
        "mini_led_flag",
        "hdmi_2_1_ports",
        "ram_gb",
        "storage_gb",
    }
)

SEED_PARAM_GROUP_MAP: dict[str, ParamGroup] = {
    "display_basic": ParamGroup.PICTURE,
    "picture_quality": ParamGroup.PICTURE,
    "backlight_control": ParamGroup.PICTURE,
    "eye_experience": ParamGroup.EYE_CARE,
    "smart_system": ParamGroup.SYSTEM,
    "gaming": ParamGroup.GAMING,
    "audio": ParamGroup.AUDIO,
}

SEED_SOURCE_TYPE_MAP: dict[str, ParamSourceType] = {
    "raw_param": ParamSourceType.RAW_PARAM,
    "claim_text": ParamSourceType.DERIVED_FROM_CLAIM,
    "model_name": ParamSourceType.MODEL_NAME,
}

IGNORED_SOURCE_TYPES = frozenset({"comment_text", "raw_master"})


class StdParamSeedValidationError(ValueError):
    """Raised when the TV M03 parameter seed violates the required contract."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class StdParamSeedLoadResult:
    seed: StdParamSeed
    seed_path: Path
    seed_version: str
    raw_version: str | None
    standard_param_count: int
    normalized_source_type_counts: dict[str, int]
    ignored_source_type_counts: dict[str, int]
    core_param_codes: list[str]


class StdParamSeedLoader:
    """Load and normalize the TV core3 M03 standard parameter seed."""

    def __init__(self, seed_path: Path | str | None = None) -> None:
        self.seed_path = Path(seed_path) if seed_path is not None else DEFAULT_PARAM_SEED_PATH

    def load(self) -> StdParamSeedLoadResult:
        raw_seed = self._load_raw_seed()
        standard_params_raw = raw_seed.get("standard_params")
        errors: list[str] = []

        if not isinstance(standard_params_raw, list) or not standard_params_raw:
            raise StdParamSeedValidationError(["standard_params must be a non-empty list"])

        duplicate_errors = self._validate_unique_param_codes(standard_params_raw)
        errors.extend(duplicate_errors)

        source_type_counts: Counter[str] = Counter()
        ignored_source_type_counts: Counter[str] = Counter()
        standard_params: list[StdParamDefinition] = []
        for index, raw_param in enumerate(standard_params_raw):
            try:
                standard_param, normalized_sources, ignored_sources = self._normalize_standard_param(
                    raw_param,
                    index,
                )
            except StdParamSeedValidationError as exc:
                errors.extend(exc.errors)
                continue
            standard_params.append(standard_param)
            source_type_counts.update(source.value for source in normalized_sources)
            ignored_source_type_counts.update(ignored_sources)

        loaded_param_codes = {item.param_code for item in standard_params}
        missing_core_codes = sorted(CORE_PARAM_CODES - loaded_param_codes)
        if missing_core_codes:
            errors.append(f"standard_params missing core param codes: {', '.join(missing_core_codes)}")

        if errors:
            raise StdParamSeedValidationError(errors)

        seed = StdParamSeed(
            seed_version=CORE3_M03_SEED_VERSION,
            category_code=Core3CategoryCode.TV,
            standard_params=standard_params,
            metadata_json={
                "raw_seed_version": raw_seed.get("version"),
                "source_seed_file": self.seed_path.name,
                "raw_standard_param_count": len(standard_params_raw),
                "normalized_source_type_counts": dict(sorted(source_type_counts.items())),
                "ignored_source_type_counts": dict(sorted(ignored_source_type_counts.items())),
                "ignored_source_types": sorted(IGNORED_SOURCE_TYPES),
                "source_type_mapping": {
                    raw_source: normalized.value
                    for raw_source, normalized in sorted(SEED_SOURCE_TYPE_MAP.items())
                },
                "required_core_param_codes": sorted(CORE_PARAM_CODES),
            },
        )
        return StdParamSeedLoadResult(
            seed=seed,
            seed_path=self.seed_path,
            seed_version=CORE3_M03_SEED_VERSION,
            raw_version=raw_seed.get("version"),
            standard_param_count=len(standard_params),
            normalized_source_type_counts=dict(sorted(source_type_counts.items())),
            ignored_source_type_counts=dict(sorted(ignored_source_type_counts.items())),
            core_param_codes=sorted(code for code in loaded_param_codes if code in CORE_PARAM_CODES),
        )

    def load_seed(self) -> StdParamSeed:
        return self.load().seed

    def _load_raw_seed(self) -> dict[str, Any]:
        try:
            raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StdParamSeedValidationError([f"seed file not found: {self.seed_path}"]) from exc
        except json.JSONDecodeError as exc:
            raise StdParamSeedValidationError([f"seed file is not valid JSON: {exc.msg}"]) from exc

        if not isinstance(raw_seed, dict):
            raise StdParamSeedValidationError(["seed root must be a JSON object"])
        return raw_seed

    def _normalize_standard_param(
        self,
        raw_param: Any,
        index: int,
    ) -> tuple[StdParamDefinition, list[ParamSourceType], list[str]]:
        prefix = f"standard_params[{index}]"
        errors: list[str] = []
        if not isinstance(raw_param, dict):
            raise StdParamSeedValidationError([f"{prefix} must be an object"])

        for field_name in REQUIRED_STANDARD_PARAM_FIELDS:
            value = raw_param.get(field_name)
            if value is None or value == "":
                errors.append(f"{prefix}.{field_name} is required")

        if errors:
            raise StdParamSeedValidationError(errors)

        param_code = str(raw_param["param_code"]).strip()
        param_group = self._normalize_param_group(str(raw_param["param_group"]), prefix)
        data_type = self._normalize_data_type(str(raw_param["data_type"]), prefix)
        aliases = self._normalize_string_list(raw_param["aliases"], f"{prefix}.aliases", required=True)
        value_parsers = self._normalize_string_list(
            raw_param["value_parsers"],
            f"{prefix}.value_parsers",
            required=True,
        )
        enum_values = self._normalize_string_list(raw_param.get("enum_values", []), f"{prefix}.enum_values")
        keywords = self._normalize_string_list(raw_param.get("keywords", []), f"{prefix}.keywords")
        source_types, ignored_sources = self._normalize_source_types(raw_param["source_types"], prefix)

        parser_config_json = {
            "raw_param_group": raw_param.get("param_group"),
            "source_priority": self._normalize_string_list(
                raw_param.get("source_priority", []),
                f"{prefix}.source_priority",
            ),
            "thresholds": raw_param.get("thresholds") or {},
            "evidence_requirement": self._normalize_string_list(
                raw_param.get("evidence_requirement", []),
                f"{prefix}.evidence_requirement",
            ),
            "mapped_claim_codes": self._normalize_string_list(
                raw_param.get("mapped_claim_codes", []),
                f"{prefix}.mapped_claim_codes",
            ),
            "mapped_task_codes": self._normalize_string_list(
                raw_param.get("mapped_task_codes", []),
                f"{prefix}.mapped_task_codes",
            ),
            "mapped_battlefield_codes": self._normalize_string_list(
                raw_param.get("mapped_battlefield_codes", []),
                f"{prefix}.mapped_battlefield_codes",
            ),
        }

        try:
            standard_param = StdParamDefinition(
                param_code=param_code,
                param_name=str(raw_param["param_name"]).strip(),
                data_type=data_type,
                param_group=param_group,
                aliases=aliases,
                value_parsers=value_parsers,
                unit=self._optional_string(raw_param.get("unit")),
                enum_values=enum_values,
                keywords=keywords,
                source_types=source_types,
                parser_config_json=parser_config_json,
                description_cn=self._optional_string(raw_param.get("definition")),
                required_for_core=param_code in CORE_PARAM_CODES,
                priority=index,
            )
        except ValidationError as exc:
            raise StdParamSeedValidationError([f"{prefix}: {exc}"]) from exc

        return standard_param, source_types, ignored_sources

    def _validate_unique_param_codes(self, standard_params_raw: list[Any]) -> list[str]:
        param_codes: list[str] = []
        errors: list[str] = []
        for index, raw_param in enumerate(standard_params_raw):
            if not isinstance(raw_param, dict):
                continue
            param_code = raw_param.get("param_code")
            if param_code is not None:
                param_codes.append(str(param_code).strip())

        duplicates = sorted(code for code, count in Counter(param_codes).items() if code and count > 1)
        if duplicates:
            errors.append(f"param_code must be unique in standard_params: {', '.join(duplicates)}")
        return errors

    def _normalize_param_group(self, raw_group: str, prefix: str) -> ParamGroup:
        clean_group = raw_group.strip()
        if clean_group in SEED_PARAM_GROUP_MAP:
            return SEED_PARAM_GROUP_MAP[clean_group]
        try:
            return ParamGroup(clean_group)
        except ValueError as exc:
            raise StdParamSeedValidationError([f"{prefix}.param_group is unsupported: {clean_group}"]) from exc

    def _normalize_data_type(self, raw_data_type: str, prefix: str) -> ParamDataType:
        clean_data_type = raw_data_type.strip()
        try:
            return ParamDataType(clean_data_type)
        except ValueError as exc:
            raise StdParamSeedValidationError([f"{prefix}.data_type is unsupported: {clean_data_type}"]) from exc

    def _normalize_source_types(
        self,
        raw_source_types: Any,
        prefix: str,
    ) -> tuple[list[ParamSourceType], list[str]]:
        if not isinstance(raw_source_types, list):
            raise StdParamSeedValidationError([f"{prefix}.source_types must be a list"])

        source_types: list[ParamSourceType] = []
        ignored_sources: list[str] = []
        seen_sources: set[ParamSourceType] = set()
        errors: list[str] = []
        for raw_source_type in raw_source_types:
            clean_source_type = str(raw_source_type).strip()
            if clean_source_type in IGNORED_SOURCE_TYPES:
                ignored_sources.append(clean_source_type)
                continue
            mapped_source_type = SEED_SOURCE_TYPE_MAP.get(clean_source_type)
            if mapped_source_type is None:
                errors.append(f"{prefix}.source_types has unsupported source type: {clean_source_type}")
                continue
            if mapped_source_type not in seen_sources:
                source_types.append(mapped_source_type)
                seen_sources.add(mapped_source_type)

        if errors:
            raise StdParamSeedValidationError(errors)
        return source_types, ignored_sources

    def _normalize_string_list(
        self,
        raw_values: Any,
        field_path: str,
        *,
        required: bool = False,
    ) -> list[str]:
        if raw_values is None:
            raw_values = []
        if not isinstance(raw_values, list):
            raise StdParamSeedValidationError([f"{field_path} must be a list"])
        values = [str(value).strip() for value in raw_values if str(value).strip()]
        if required and not values:
            raise StdParamSeedValidationError([f"{field_path} must not be empty"])
        return values

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
