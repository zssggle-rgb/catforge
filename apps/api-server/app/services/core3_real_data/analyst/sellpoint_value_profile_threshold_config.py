"""Reviewed draft thresholds for capability prevalence by category."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CapabilityThresholdConfig,
)


THRESHOLD_CONFIG_VERSION = "sellpoint_value_thresholds_draft_v1"

DEFAULT_CAPABILITY_THRESHOLD_CONFIGS: dict[str, CapabilityThresholdConfig] = {
    "TV": CapabilityThresholdConfig(
        config_version=THRESHOLD_CONFIG_VERSION,
        category_code="TV",
        minimum_known_count=5,
        prevalence_threshold=0.8,
        required_scope_dimensions=[
            "category_code",
            "price_band",
            "size_relation",
        ],
        validation_status="provisional",
    ),
    "AC": CapabilityThresholdConfig(
        config_version=THRESHOLD_CONFIG_VERSION,
        category_code="AC",
        minimum_known_count=5,
        prevalence_threshold=0.8,
        required_scope_dimensions=[
            "category_code",
            "price_band",
            "product_form",
            "size_relation",
        ],
        validation_status="provisional",
    ),
}


def capability_threshold_config(
    category_code: str,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> CapabilityThresholdConfig:
    """Return a validated copy so callers cannot mutate shared defaults."""

    normalized = category_code.upper()
    base = DEFAULT_CAPABILITY_THRESHOLD_CONFIGS.get(normalized)
    if base is None:
        raise ValueError(f"unsupported capability threshold category: {category_code}")
    payload = base.model_dump(mode="python")
    payload.update(dict(overrides or {}))
    return CapabilityThresholdConfig.model_validate(payload)


__all__ = [
    "DEFAULT_CAPABILITY_THRESHOLD_CONFIGS",
    "THRESHOLD_CONFIG_VERSION",
    "capability_threshold_config",
]
