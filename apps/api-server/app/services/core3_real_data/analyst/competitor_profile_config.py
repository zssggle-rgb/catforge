"""Production configuration resolved from one locked competitor-profile input bundle."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Mapping

from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection_schemas import (
    KeyCompetitorSelectionConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    CompetitorProfileMaterializationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionConfig,
)
from app.services.core3_real_data.hash_utils import stable_hash


PRODUCTION_CONFIG_METHOD_VERSION = "competitor_profile_production_config_v1"
GENERIC_COVERAGE_THRESHOLD = Decimal("0.8000")

_M12C_POSITIVE_ROLES = sorted(
    {
        "basic_threshold",
        "brand_claim_only",
        "premium_driver_estimated",
        "sales_driver_estimated",
        "unique_payment_potential",
        "user_validated_need",
        "value_bundle_claim",
        "weak_user_perception_claim",
    }
)
_M12C_OPPORTUNITY_ROLES = sorted(
    {"high_price_competitor_intercept", "opportunity_gap", "price_up_opportunity"}
)


def build_production_materialization_config(
    category_bundle: CompetitorProfileCategoryInputBundle,
) -> CompetitorProfileMaterializationConfig:
    """Build one deterministic config from the complete locked category scope."""

    coverage = _value_coverage_ratios(category_bundle)
    generic = sorted(
        code for code, ratio in coverage.items() if ratio >= GENERIC_COVERAGE_THRESHOLD
    )
    discriminative = sorted(set(coverage) - set(generic))
    config_hash = stable_hash(
        {
            "method_version": PRODUCTION_CONFIG_METHOD_VERSION,
            "category_input_fingerprint": category_bundle.input_fingerprint,
            "generic_coverage_threshold": GENERIC_COVERAGE_THRESHOLD,
            "generic_value_codes": generic,
            "discriminative_value_codes": discriminative,
            "value_coverage_ratios": coverage,
        },
        version=PRODUCTION_CONFIG_METHOD_VERSION,
    )
    suffix = config_hash.rsplit(":", 1)[-1][:12]
    category = category_bundle.serving_scope.product_category
    base_version = f"{PRODUCTION_CONFIG_METHOD_VERSION}_{category.lower()}_{suffix}"
    shared = {
        "generic_coverage_threshold": GENERIC_COVERAGE_THRESHOLD,
        "generic_value_codes": generic,
        "table_stake_value_codes": [],
        "discriminative_value_codes": discriminative,
        "value_coverage_ratios": coverage,
    }
    return CompetitorProfileMaterializationConfig(
        config_version=base_version,
        product_category=category,
        recall=CandidateRecallConfig(),
        eligibility=CandidateEligibilityConfig(),
        purchase_pool=PurchasePoolSemanticConfig(
            config_version=f"{base_version}_purchase_pool",
            product_category=category,
            same_budget_max_gap_ratio=Decimal("0.1500"),
            adjacent_budget_max_gap_ratio=Decimal("0.3500"),
            **shared,
        ),
        value_substitution=ValueSubstitutionConfig(
            config_version=f"{base_version}_value_substitution",
            product_category=category,
            **shared,
            m12d_strong_roles=sorted(
                {"core_payment_anchor", "core_reason", "established_anchor"}
            ),
            m12d_supporting_roles=["supporting_anchor"],
            m12d_weak_roles=sorted(
                {"proposition_anchor", "weak_expression_anchor"}
            ),
            m12d_risk_roles=["risk_drag_anchor"],
            m12c_positive_roles=sorted(
                {
                    "premium_driver_estimated",
                    "sales_driver_estimated",
                    "unique_payment_potential",
                    "value_bundle_claim",
                }
            ),
            m12c_supporting_roles=sorted(
                {
                    "basic_threshold",
                    "brand_claim_only",
                    "user_validated_need",
                    "weak_user_perception_claim",
                }
            ),
            m12c_opportunity_roles=_M12C_OPPORTUNITY_ROLES,
            m12c_risk_roles=["drag_factor"],
            m12c_unknown_roles=["sample_insufficient"],
        ),
        price_volume=PriceVolumePressureConfig(
            config_version=f"{base_version}_price_volume",
            product_category=category,
            same_budget_max_gap_ratio=Decimal("0.1500"),
            adjacent_budget_max_gap_ratio=Decimal("0.3500"),
            material_higher_volume_ratio=Decimal("1.1000"),
            material_lower_volume_ratio=Decimal("0.9000"),
        ),
        relation=CompetitorRelationConfig(
            config_version=f"{base_version}_relation",
            product_category=category,
            downtrade_min_price_gap_pct=Decimal("0.0800"),
            uptrade_min_price_gap_pct=Decimal("0.0800"),
            strong_price_gap_pct=Decimal("0.1500"),
            strong_volume_ratio=Decimal("1.2500"),
            threshold_parameter_codes=(
                sorted({"hdmi_2_1_ports", "hdr_format_list", "screen_size_inch"})
                if category == "TV"
                else sorted(
                    {
                        "ac_product_form",
                        "cooling_capacity_segment",
                        "horsepower_segment",
                    }
                )
            ),
            primary_relation_priority=[
                "direct_substitute",
                "same_budget_alternative",
                "downtrade_diversion",
                "uptrade_alternative",
                "same_brand_ladder",
                "scenario_substitute",
                "same_value_substitute",
            ],
        ),
        key_selection=KeyCompetitorSelectionConfig(
            config_version=f"{base_version}_key_selection",
            product_category=category,
            decision_topic_order=[
                "purchase_choice",
                "price_scale_pressure",
                "portfolio_or_scenario",
                "value_route",
            ],
            topic_relation_priority={
                "purchase_choice": [
                    "direct_substitute",
                    "same_budget_alternative",
                ],
                "price_scale_pressure": [
                    "downtrade_diversion",
                    "uptrade_alternative",
                    "same_budget_alternative",
                    "direct_substitute",
                ],
                "portfolio_or_scenario": [
                    "same_brand_ladder",
                    "scenario_substitute",
                ],
                "value_route": [
                    "same_value_substitute",
                    "uptrade_alternative",
                    "downtrade_diversion",
                    "direct_substitute",
                    "same_budget_alternative",
                ],
            },
        ),
    )


def _value_coverage_ratios(
    category_bundle: CompetitorProfileCategoryInputBundle,
) -> dict[str, Decimal]:
    codes_by_sku: dict[str, set[str]] = defaultdict(set)
    for module_code in ("M05C", "M11C", "M11D", "M12C", "M12D"):
        module = category_bundle.modules[module_code]
        for sku_code, rows in module.records_by_sku.items():
            for row in rows:
                codes_by_sku[sku_code].update(_positive_value_codes(module_code, row.facts))
    denominator = Decimal(len(category_bundle.authoritative_sku_codes))
    counts: dict[str, int] = defaultdict(int)
    for codes in codes_by_sku.values():
        for code in codes:
            counts[code] += 1
    return {
        code: (Decimal(counts[code]) / denominator).quantize(Decimal("0.0001"))
        for code in sorted(counts)
    }


def _positive_value_codes(module_code: str, facts: Mapping[str, Any]) -> set[str]:
    if module_code == "M05C":
        return _codes_from_fields(
            facts,
            "supported_claim_codes",
            "supported_param_codes",
            "topic_codes",
            "value_codes",
            "topic_code",
        )
    if module_code == "M11C":
        return _codes_from_fields(
            facts,
            "primary_battlefield_code",
            "secondary_battlefield_codes_json",
        )
    if module_code == "M11D":
        role = str(facts.get("allocation_role") or "").strip().lower()
        return (
            _extract_codes(facts.get("dimension_code"))
            if role in {"primary", "secondary", "user_observed"}
            else set()
        )
    if module_code == "M12C":
        role = str(facts.get("claim_value_role") or "").strip().lower()
        return (
            _extract_codes(facts.get("claim_code"))
            if role in set(_M12C_POSITIVE_ROLES)
            else set()
        )
    if module_code == "M12D":
        return _codes_from_fields(
            facts,
            "core_reasons_json",
            "core_payment_anchors_json",
            "supporting_anchors_json",
            "weak_expression_anchors_json",
            "established_anchors_json",
            "proposition_anchors_json",
        )
    return set()


def _codes_from_fields(facts: Mapping[str, Any], *field_names: str) -> set[str]:
    result: set[str] = set()
    for field_name in field_names:
        result.update(_extract_codes(facts.get(field_name)))
    return result


def _extract_codes(value: Any) -> set[str]:
    result: set[str] = set()
    if value is None or isinstance(value, bool):
        return result
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized and normalized not in {"-", "none", "null", "unknown"}:
            result.add(normalized)
        return result
    if isinstance(value, Mapping):
        found = False
        for key in (
            "anchor_code",
            "reason_code",
            "claim_code",
            "value_code",
            "battlefield_code",
            "topic_code",
            "code",
        ):
            if key in value:
                found = True
                result.update(_extract_codes(value[key]))
        if not found:
            for child in value.values():
                if isinstance(child, (Mapping, list, tuple, set, frozenset)):
                    result.update(_extract_codes(child))
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            result.update(_extract_codes(child))
    return result


__all__ = [
    "GENERIC_COVERAGE_THRESHOLD",
    "PRODUCTION_CONFIG_METHOD_VERSION",
    "build_production_materialization_config",
]
