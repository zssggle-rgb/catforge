"""Validated low-gate defaults for sellpoint-value profile V5.1."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_CONFIG_VERSION,
)


class DirectMarketGapConfig(SellpointValueProfileBaseModel):
    minimum_comparator_count: Literal[1] = 1
    small_group_maximum: int = Field(default=4, ge=2)
    require_common_weeks: Literal[False] = False
    require_common_platforms: Literal[False] = False
    allow_weekly_average: Literal[True] = True


class ValueRealizationConfig(SellpointValueProfileBaseModel):
    minimum_shared_anchor_count: Literal[1] = 1
    allow_single_comparator: Literal[True] = True


class ParameterGroupConfig(SellpointValueProfileBaseModel):
    minimum_distinct_value_count: Literal[2] = 2
    minimum_skus_per_value: Literal[1] = 1
    require_ordinal_tier: Literal[False] = False


class TableStakeConfig(SellpointValueProfileBaseModel):
    minimum_known_count: int = Field(default=5, ge=1)
    prevalence_threshold: Decimal = Field(default=Decimal("0.80"), gt=0, le=1)
    insufficient_sample_status: Literal["not_assessed"] = "not_assessed"
    insufficient_sample_requires_review: Literal[False] = False


class OptionalEnhancementConfig(SellpointValueProfileBaseModel):
    required_for_profile: Literal[False] = False
    required_for_release: Literal[False] = False


class SellpointValueV51MethodConfig(SellpointValueProfileBaseModel):
    config_version: Literal["sellpoint_value_profile_low_gate_v5_1"] = (
        SPV_V5_1_CONFIG_VERSION
    )
    category_code: Literal["TV", "AC"]
    direct_market_gap: DirectMarketGapConfig = Field(
        default_factory=DirectMarketGapConfig
    )
    value_realization: ValueRealizationConfig = Field(
        default_factory=ValueRealizationConfig
    )
    parameter_group: ParameterGroupConfig = Field(default_factory=ParameterGroupConfig)
    table_stake: TableStakeConfig = Field(default_factory=TableStakeConfig)
    market_archetype: OptionalEnhancementConfig = Field(
        default_factory=OptionalEnhancementConfig
    )
    synthetic_control: OptionalEnhancementConfig = Field(
        default_factory=OptionalEnhancementConfig
    )
    strict_market_implied_wtp: OptionalEnhancementConfig = Field(
        default_factory=OptionalEnhancementConfig
    )


DEFAULT_SPV_V5_1_CONFIGS = {
    category_code: SellpointValueV51MethodConfig(category_code=category_code)
    for category_code in ("TV", "AC")
}


def sellpoint_value_v5_1_config(category_code: str) -> SellpointValueV51MethodConfig:
    """Return a validated copy so callers cannot mutate shared defaults."""

    normalized = category_code.strip().upper()
    default = DEFAULT_SPV_V5_1_CONFIGS.get(normalized)
    if default is None:
        raise ValueError(f"unsupported V5.1 category: {category_code}")
    return SellpointValueV51MethodConfig.model_validate(
        default.model_dump(mode="python")
    )


__all__ = [
    "DEFAULT_SPV_V5_1_CONFIGS",
    "DirectMarketGapConfig",
    "OptionalEnhancementConfig",
    "ParameterGroupConfig",
    "SellpointValueV51MethodConfig",
    "TableStakeConfig",
    "ValueRealizationConfig",
    "sellpoint_value_v5_1_config",
]
