"""Seed loader for M04a standard claim definitions."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.services.core3_real_data.base_claim_activation_schemas import (
    ClaimGroup,
    ClaimSeedSourceType,
    ClaimType,
    StdClaimDefinition,
    StdClaimSeed,
)
from app.services.core3_real_data.constants import (
    CORE3_M04A_SEED_VERSION,
    Core3CategoryCode,
)


DEFAULT_CLAIM_SEED_PATH = (
    Path(__file__).resolve().parents[2] / "rules" / "tv_core3_mvp_seed_v0_2.json"
)

REQUIRED_STANDARD_CLAIM_FIELDS = (
    "claim_code",
    "claim_name",
    "definition",
    "claim_group",
    "aliases",
    "keywords",
    "promo_keywords",
    "source_types",
    "evidence_requirement",
    "supporting_param_codes",
    "mapped_param_codes",
    "mapped_task_codes",
    "mapped_battlefield_codes",
    "activation_rule",
    "activation_weights",
)

REQUIRED_STANDARD_CLAIM_CODES = frozenset(
    {
        "CLAIM_LARGE_SCREEN_IMMERSION",
        "CLAIM_MINI_LED_BACKLIGHT",
        "CLAIM_OLED_SELF_LIT",
        "CLAIM_QLED_WIDE_COLOR",
        "CLAIM_HIGH_BRIGHTNESS_HDR",
        "CLAIM_FINE_LOCAL_DIMMING",
        "CLAIM_HIGH_REFRESH_RATE",
        "CLAIM_GAMING_LOW_LATENCY",
        "CLAIM_HDMI_2_1_GAMING",
        "CLAIM_SPORTS_MOTION_SMOOTH",
        "CLAIM_EYE_CARE_COMFORT",
        "CLAIM_ELDER_FRIENDLY_SMART",
        "CLAIM_SMART_VOICE_EASE",
        "CLAIM_NO_AD_OR_CLEAN_SYSTEM",
        "CLAIM_IMMERSIVE_AUDIO",
        "CLAIM_DOLBY_CINEMA_AUDIO",
        "CLAIM_THIN_DESIGN",
        "CLAIM_ENERGY_SAVING",
        "CLAIM_VALUE_FOR_MONEY",
        "CLAIM_INSTALLATION_SERVICE_ASSURANCE",
    }
)

PARAM_ONLY_ALLOWED_CLAIM_CODES = frozenset(
    {
        "CLAIM_LARGE_SCREEN_IMMERSION",
        "CLAIM_MINI_LED_BACKLIGHT",
        "CLAIM_OLED_SELF_LIT",
        "CLAIM_QLED_WIDE_COLOR",
        "CLAIM_HIGH_BRIGHTNESS_HDR",
        "CLAIM_FINE_LOCAL_DIMMING",
        "CLAIM_HIGH_REFRESH_RATE",
        "CLAIM_HDMI_2_1_GAMING",
        "CLAIM_EYE_CARE_COMFORT",
        "CLAIM_IMMERSIVE_AUDIO",
        "CLAIM_DOLBY_CINEMA_AUDIO",
    }
)

CLAIM_GROUP_TO_TYPE: dict[ClaimGroup, ClaimType] = {
    ClaimGroup.PICTURE: ClaimType.TECHNICAL,
    ClaimGroup.GAMING: ClaimType.TECHNICAL,
    ClaimGroup.MOTION: ClaimType.EXPERIENCE,
    ClaimGroup.EYE_CARE: ClaimType.MIXED,
    ClaimGroup.SMART: ClaimType.MIXED,
    ClaimGroup.AUDIO: ClaimType.MIXED,
    ClaimGroup.DESIGN: ClaimType.DESIGN,
    ClaimGroup.VALUE: ClaimType.VALUE,
    ClaimGroup.SERVICE: ClaimType.SERVICE,
}

SEED_SOURCE_TYPE_MAP: dict[str, ClaimSeedSourceType] = {
    "standard_param": ClaimSeedSourceType.STANDARD_PARAM,
    "claim_text": ClaimSeedSourceType.CLAIM_TEXT,
    "raw_param": ClaimSeedSourceType.RAW_PARAM,
}

IGNORED_SOURCE_TYPES = frozenset({"comment_text", "market_fact"})
IGNORED_ACTIVATION_WEIGHT_KEYS = frozenset({"comment", "market"})
M04A_ACTIVATION_WEIGHT_KEYS = frozenset({"param", "promo"})


class StdClaimSeedValidationError(ValueError):
    """Raised when the TV M04a claim seed violates the required contract."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class StdClaimSeedLoadResult:
    seed: StdClaimSeed
    seed_path: Path
    seed_version: str
    asset_version: str | None
    raw_version: str | None
    standard_claim_count: int
    required_claim_codes: list[str]
    claim_group_counts: dict[str, int]
    claim_type_counts: dict[str, int]
    normalized_source_type_counts: dict[str, int]
    ignored_source_type_counts: dict[str, int]
    param_only_allowed_claim_codes: list[str]
    comment_deferred_claim_codes: list[str]
    market_deferred_claim_codes: list[str]


class StdClaimSeedLoader:
    """Load and normalize the TV core3 M04a standard claim seed."""

    def __init__(self, seed_path: Path | str | None = None) -> None:
        self.seed_path = Path(seed_path) if seed_path is not None else DEFAULT_CLAIM_SEED_PATH

    def load(self) -> StdClaimSeedLoadResult:
        raw_seed = self._load_raw_seed()
        standard_claims_raw = raw_seed.get("standard_claims")
        errors: list[str] = []

        if not isinstance(standard_claims_raw, list) or not standard_claims_raw:
            raise StdClaimSeedValidationError(["standard_claims must be a non-empty list"])

        errors.extend(self._validate_unique_claim_codes(standard_claims_raw))

        source_type_counts: Counter[str] = Counter()
        ignored_source_type_counts: Counter[str] = Counter()
        claim_group_counts: Counter[str] = Counter()
        claim_type_counts: Counter[str] = Counter()
        comment_deferred_claim_codes: list[str] = []
        market_deferred_claim_codes: list[str] = []
        standard_claims: list[StdClaimDefinition] = []
        for index, raw_claim in enumerate(standard_claims_raw):
            try:
                standard_claim, normalized_sources, ignored_sources = self._normalize_standard_claim(
                    raw_claim,
                    index,
                )
            except StdClaimSeedValidationError as exc:
                errors.extend(exc.errors)
                continue

            standard_claims.append(standard_claim)
            claim_group_counts.update([str(standard_claim.claim_group)])
            claim_type_counts.update([str(standard_claim.claim_type)])
            source_type_counts.update(source.value for source in normalized_sources)
            ignored_source_type_counts.update(ignored_sources)
            if "comment_text" in ignored_sources:
                comment_deferred_claim_codes.append(standard_claim.claim_code)
            if "market_fact" in ignored_sources:
                market_deferred_claim_codes.append(standard_claim.claim_code)

        loaded_claim_codes = {item.claim_code for item in standard_claims}
        missing_claim_codes = sorted(REQUIRED_STANDARD_CLAIM_CODES - loaded_claim_codes)
        if missing_claim_codes:
            errors.append(f"standard_claims missing required claim codes: {', '.join(missing_claim_codes)}")

        if errors:
            raise StdClaimSeedValidationError(errors)

        raw_version = self._optional_string(raw_seed.get("version"))
        seed = StdClaimSeed(
            seed_version=CORE3_M04A_SEED_VERSION,
            category_code=Core3CategoryCode.TV,
            standard_claims=standard_claims,
            metadata_json={
                "asset_version": raw_version,
                "raw_seed_version": raw_version,
                "source_seed_file": self.seed_path.name,
                "raw_standard_claim_count": len(standard_claims_raw),
                "required_standard_claim_count": len(REQUIRED_STANDARD_CLAIM_CODES),
                "required_claim_codes": sorted(REQUIRED_STANDARD_CLAIM_CODES),
                "extra_claim_codes": sorted(loaded_claim_codes - REQUIRED_STANDARD_CLAIM_CODES),
                "claim_group_counts": dict(sorted(claim_group_counts.items())),
                "claim_type_counts": dict(sorted(claim_type_counts.items())),
                "normalized_source_type_counts": dict(sorted(source_type_counts.items())),
                "ignored_source_type_counts": dict(sorted(ignored_source_type_counts.items())),
                "ignored_source_types": sorted(IGNORED_SOURCE_TYPES),
                "source_type_mapping": {
                    raw_source: normalized.value
                    for raw_source, normalized in sorted(SEED_SOURCE_TYPE_MAP.items())
                },
                "param_only_allowed_claim_codes": sorted(PARAM_ONLY_ALLOWED_CLAIM_CODES),
                "comment_deferred_to_m04b_claim_codes": sorted(comment_deferred_claim_codes),
                "market_deferred_claim_codes": sorted(market_deferred_claim_codes),
                "m04a_activation_weight_keys": sorted(M04A_ACTIVATION_WEIGHT_KEYS),
                "ignored_activation_weight_keys": sorted(IGNORED_ACTIVATION_WEIGHT_KEYS),
            },
        )
        return StdClaimSeedLoadResult(
            seed=seed,
            seed_path=self.seed_path,
            seed_version=CORE3_M04A_SEED_VERSION,
            asset_version=raw_version,
            raw_version=raw_version,
            standard_claim_count=len(standard_claims),
            required_claim_codes=sorted(REQUIRED_STANDARD_CLAIM_CODES),
            claim_group_counts=dict(sorted(claim_group_counts.items())),
            claim_type_counts=dict(sorted(claim_type_counts.items())),
            normalized_source_type_counts=dict(sorted(source_type_counts.items())),
            ignored_source_type_counts=dict(sorted(ignored_source_type_counts.items())),
            param_only_allowed_claim_codes=sorted(PARAM_ONLY_ALLOWED_CLAIM_CODES),
            comment_deferred_claim_codes=sorted(comment_deferred_claim_codes),
            market_deferred_claim_codes=sorted(market_deferred_claim_codes),
        )

    def load_seed(self) -> StdClaimSeed:
        return self.load().seed

    def _load_raw_seed(self) -> dict[str, Any]:
        try:
            raw_seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StdClaimSeedValidationError([f"seed file not found: {self.seed_path}"]) from exc
        except json.JSONDecodeError as exc:
            raise StdClaimSeedValidationError([f"seed file is not valid JSON: {exc.msg}"]) from exc

        if not isinstance(raw_seed, dict):
            raise StdClaimSeedValidationError(["seed root must be a JSON object"])
        return raw_seed

    def _normalize_standard_claim(
        self,
        raw_claim: Any,
        index: int,
    ) -> tuple[StdClaimDefinition, list[ClaimSeedSourceType], list[str]]:
        prefix = f"standard_claims[{index}]"
        errors: list[str] = []
        if not isinstance(raw_claim, dict):
            raise StdClaimSeedValidationError([f"{prefix} must be an object"])

        for field_name in REQUIRED_STANDARD_CLAIM_FIELDS:
            value = raw_claim.get(field_name)
            if value is None or value == "":
                errors.append(f"{prefix}.{field_name} is required")

        if errors:
            raise StdClaimSeedValidationError(errors)

        claim_code = str(raw_claim["claim_code"]).strip()
        claim_group = self._normalize_claim_group(str(raw_claim["claim_group"]), prefix)
        claim_type = CLAIM_GROUP_TO_TYPE[claim_group]
        source_types, ignored_sources = self._normalize_source_types(raw_claim["source_types"], prefix)
        activation_rule = self._normalize_object(raw_claim["activation_rule"], f"{prefix}.activation_rule")
        activation_weights = self._normalize_activation_weights(
            raw_claim["activation_weights"],
            f"{prefix}.activation_weights",
        )

        try:
            standard_claim = StdClaimDefinition(
                claim_code=claim_code,
                claim_name=str(raw_claim["claim_name"]).strip(),
                claim_group=claim_group,
                claim_type=claim_type,
                aliases=self._normalize_string_list(raw_claim["aliases"], f"{prefix}.aliases", required=True),
                keywords=self._normalize_string_list(raw_claim["keywords"], f"{prefix}.keywords", required=True),
                promo_keywords=self._normalize_string_list(
                    raw_claim["promo_keywords"],
                    f"{prefix}.promo_keywords",
                    required=True,
                ),
                source_types=source_types,
                evidence_requirement=self._normalize_string_list(
                    raw_claim["evidence_requirement"],
                    f"{prefix}.evidence_requirement",
                    required=True,
                ),
                supporting_param_codes=self._normalize_string_list(
                    raw_claim["supporting_param_codes"],
                    f"{prefix}.supporting_param_codes",
                ),
                mapped_param_codes=self._normalize_string_list(
                    raw_claim["mapped_param_codes"],
                    f"{prefix}.mapped_param_codes",
                ),
                mapped_task_codes=self._normalize_string_list(
                    raw_claim["mapped_task_codes"],
                    f"{prefix}.mapped_task_codes",
                ),
                mapped_battlefield_codes=self._normalize_string_list(
                    raw_claim["mapped_battlefield_codes"],
                    f"{prefix}.mapped_battlefield_codes",
                ),
                comment_topic_codes=self._normalize_string_list(
                    raw_claim.get("comment_topic_codes", []),
                    f"{prefix}.comment_topic_codes",
                ),
                activation_rule=activation_rule,
                activation_weights=activation_weights,
                param_only_allowed=claim_code in PARAM_ONLY_ALLOWED_CLAIM_CODES,
                description_cn=self._optional_string(raw_claim.get("definition")),
                priority=index,
            )
        except ValidationError as exc:
            raise StdClaimSeedValidationError([f"{prefix}: {exc}"]) from exc

        return standard_claim, source_types, ignored_sources

    def _validate_unique_claim_codes(self, standard_claims_raw: list[Any]) -> list[str]:
        claim_codes: list[str] = []
        for raw_claim in standard_claims_raw:
            if isinstance(raw_claim, dict) and raw_claim.get("claim_code") is not None:
                claim_codes.append(str(raw_claim["claim_code"]).strip())

        duplicates = sorted(code for code, count in Counter(claim_codes).items() if code and count > 1)
        if duplicates:
            return [f"claim_code must be unique in standard_claims: {', '.join(duplicates)}"]
        return []

    def _normalize_claim_group(self, raw_group: str, prefix: str) -> ClaimGroup:
        clean_group = raw_group.strip()
        try:
            return ClaimGroup(clean_group)
        except ValueError as exc:
            raise StdClaimSeedValidationError([f"{prefix}.claim_group is unsupported: {clean_group}"]) from exc

    def _normalize_source_types(
        self,
        raw_source_types: Any,
        prefix: str,
    ) -> tuple[list[ClaimSeedSourceType], list[str]]:
        if not isinstance(raw_source_types, list):
            raise StdClaimSeedValidationError([f"{prefix}.source_types must be a list"])

        source_types: list[ClaimSeedSourceType] = []
        ignored_sources: list[str] = []
        seen_sources: set[ClaimSeedSourceType] = set()
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
            raise StdClaimSeedValidationError(errors)
        if not source_types:
            raise StdClaimSeedValidationError([f"{prefix}.source_types has no M04a-usable source type"])
        return source_types, ignored_sources

    def _normalize_activation_weights(self, raw_weights: Any, field_path: str) -> dict[str, Decimal]:
        if not isinstance(raw_weights, dict):
            raise StdClaimSeedValidationError([f"{field_path} must be an object"])

        errors: list[str] = []
        m04a_weights: dict[str, Decimal] = {}
        for raw_key, raw_value in raw_weights.items():
            key = str(raw_key).strip()
            if key in IGNORED_ACTIVATION_WEIGHT_KEYS:
                continue
            if key not in M04A_ACTIVATION_WEIGHT_KEYS:
                errors.append(f"{field_path} has unsupported weight key: {key}")
                continue
            try:
                weight = Decimal(str(raw_value))
            except (InvalidOperation, ValueError) as exc:
                errors.append(f"{field_path}.{key} must be numeric")
                continue
            if weight < 0:
                errors.append(f"{field_path}.{key} must not be negative")
                continue
            m04a_weights[key] = weight

        if errors:
            raise StdClaimSeedValidationError(errors)
        total_weight = sum(m04a_weights.values(), Decimal("0"))
        if total_weight <= 0:
            raise StdClaimSeedValidationError([f"{field_path} must contain positive param or promo weight"])
        return {
            key: (weight / total_weight).quantize(Decimal("0.000001"))
            for key, weight in sorted(m04a_weights.items())
        }

    def _normalize_object(self, raw_value: Any, field_path: str) -> dict[str, Any]:
        if not isinstance(raw_value, dict):
            raise StdClaimSeedValidationError([f"{field_path} must be an object"])
        return raw_value

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
            raise StdClaimSeedValidationError([f"{field_path} must be a list"])
        values = [str(value).strip() for value in raw_values if str(value).strip()]
        if required and not values:
            raise StdClaimSeedValidationError([f"{field_path} must not be empty"])
        return values

    def _optional_string(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
