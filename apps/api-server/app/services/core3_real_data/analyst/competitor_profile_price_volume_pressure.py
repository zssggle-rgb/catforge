"""Classify descriptive price-volume pressure without causal claims."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairFeatureBundle,
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureAssessment,
    PriceVolumePressureBundle,
    PriceVolumePressureConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticBundle,
    PurchasePoolSemanticPairAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import EvidenceRef
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionEvidenceBundle,
    ValueSubstitutionEvidencePair,
)
from app.services.core3_real_data.hash_utils import stable_hash


class PriceVolumePressureEvaluationError(RuntimeError):
    """Raised when G14, G15, G16, and G17 scopes do not align."""


class PriceVolumePressureEvaluator:
    """Evaluate market pressure direction from locked descriptive M07 facts."""

    def evaluate(
        self,
        pair_bundle: PairFeatureBundle,
        purchase_pool_bundle: PurchasePoolSemanticBundle,
        value_bundle: ValueSubstitutionEvidenceBundle,
        config: PriceVolumePressureConfig,
    ) -> PriceVolumePressureBundle:
        self._assert_inputs(pair_bundle, purchase_pool_bundle, value_bundle, config)
        pool_by_sku = {
            row.candidate.sku_code: row for row in purchase_pool_bundle.pairs
        }
        value_by_sku = {row.candidate.sku_code: row for row in value_bundle.pairs}
        pairs = [
            self._evaluate_pair(
                pair,
                pool_by_sku[pair.candidate.sku_code],
                value_by_sku[pair.candidate.sku_code],
                config,
            )
            for pair in pair_bundle.pairs
        ]
        input_fingerprint = stable_hash(
            {
                "pair_feature_result_hash": pair_bundle.result_hash,
                "purchase_pool_result_hash": purchase_pool_bundle.result_hash,
                "value_substitution_result_hash": value_bundle.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_price_volume_pressure_input_v1",
        )
        return PriceVolumePressureBundle(
            project_id=pair_bundle.project_id,
            category_code=pair_bundle.category_code,
            product_category=pair_bundle.product_category,
            release_scope_key=pair_bundle.release_scope_key,
            target=pair_bundle.target,
            candidate_count=len(pairs),
            pairs=pairs,
            config=config,
            pair_feature_result_hash=pair_bundle.result_hash,
            purchase_pool_result_hash=purchase_pool_bundle.result_hash,
            value_substitution_result_hash=value_bundle.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "input_fingerprint": input_fingerprint,
                    "pair_hashes": {
                        row.candidate.sku_code: row.result_hash for row in pairs
                    },
                },
                version="competitor_profile_price_volume_pressure_result_v1",
            ),
        )

    @staticmethod
    def _assert_inputs(
        pair_bundle: PairFeatureBundle,
        pool_bundle: PurchasePoolSemanticBundle,
        value_bundle: ValueSubstitutionEvidenceBundle,
        config: PriceVolumePressureConfig,
    ) -> None:
        common_scope = (
            pair_bundle.project_id,
            pair_bundle.category_code,
            pair_bundle.product_category,
            pair_bundle.release_scope_key,
            pair_bundle.target,
        )
        if common_scope != (
            pool_bundle.project_id,
            pool_bundle.category_code,
            pool_bundle.product_category,
            pool_bundle.release_scope_key,
            pool_bundle.target,
        ) or common_scope != (
            value_bundle.project_id,
            value_bundle.category_code,
            value_bundle.product_category,
            value_bundle.release_scope_key,
            value_bundle.target,
        ):
            raise PriceVolumePressureEvaluationError(
                "pair, purchase-pool, and value scopes must match"
            )
        if config.product_category != pair_bundle.product_category:
            raise PriceVolumePressureEvaluationError(
                "price-volume config category must match inputs"
            )
        if pool_bundle.pair_feature_result_hash != pair_bundle.result_hash:
            raise PriceVolumePressureEvaluationError(
                "purchase pool must consume the supplied pair feature result"
            )
        if (
            value_bundle.pair_feature_result_hash != pair_bundle.result_hash
            or value_bundle.purchase_pool_result_hash != pool_bundle.result_hash
        ):
            raise PriceVolumePressureEvaluationError(
                "value evidence must consume the supplied pair and pool results"
            )
        candidate_lists = (
            [row.candidate.sku_code for row in pair_bundle.pairs],
            [row.candidate.sku_code for row in pool_bundle.pairs],
            [row.candidate.sku_code for row in value_bundle.pairs],
        )
        if len({tuple(values) for values in candidate_lists}) != 1:
            raise PriceVolumePressureEvaluationError(
                "pair, pool, and value candidates must match exactly"
            )

    def _evaluate_pair(
        self,
        pair: PairFeatureRecord,
        pool: PurchasePoolSemanticPairAssessment,
        value: ValueSubstitutionEvidencePair,
        config: PriceVolumePressureConfig,
    ) -> PriceVolumePressureAssessment:
        market = pair.market_comparison
        review_reasons = {
            reason
            for reason in [
                *pair.review_reason_codes,
                *pair.lineage_conflict_reason_codes,
            ]
            if "_m07_" in reason.lower() or reason.lower().startswith("m07_")
        }
        review_required = bool(review_reasons)
        local_budget_band = _budget_band(market.price_gap_pct, config)
        if (
            local_budget_band != "unknown"
            and pool.budget_band != "unknown"
            and local_budget_band != pool.budget_band
        ):
            review_reasons.add("purchase_pool_and_pressure_budget_band_mismatch")
            review_required = True
        comparability = "conflict" if review_required else market.comparability_status
        pattern, pattern_limitations = _market_pattern(
            market=market,
            budget_band=local_budget_band,
            review_required=review_required,
            config=config,
        )
        pressure = _pressure_direction(
            pattern=pattern,
            pool_level=pool.purchase_pool.level,
            budget_band=local_budget_band,
            value_status=value.evidence_status,
        )
        limitations = set(pattern_limitations)
        limitations.update(
            _pressure_limitations(pattern, pressure, value.evidence_status)
        )
        diagnostics = []
        if market.common_week_count is not None:
            diagnostics.append("common_week_count_diagnostic_only")
        if market.common_platform_count is not None:
            diagnostics.append("common_platform_count_diagnostic_only")
        confidence = _confidence(
            pressure=pressure,
            comparability=comparability,
            pool_level=pool.purchase_pool.level,
            value_status=value.evidence_status,
            review_required=review_required,
        )
        evidence_refs = _m07_refs(pair.evidence_refs)
        input_fingerprint = stable_hash(
            {
                "pair_feature_result_hash": pair.result_hash,
                "purchase_pool_result_hash": pool.result_hash,
                "value_substitution_result_hash": value.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_price_volume_pressure_pair_input_v1",
        )
        payload = {
            "target_sku_code": pair.target.sku_code,
            "candidate_sku_code": pair.candidate.sku_code,
            "purchase_pool_level": pool.purchase_pool.level,
            "value_evidence_status": value.evidence_status,
            "budget_band": local_budget_band,
            "market_comparability_status": comparability,
            "market_pattern": pattern,
            "pressure_direction": pressure,
            "market_comparison_result_hash": market.result_hash,
            "diagnostic_only_fields": sorted(diagnostics),
            "confidence_level": confidence,
            "review_required": review_required,
            "review_reason_codes": sorted(review_reasons),
            "limitations": sorted(limitations),
            "pair_feature_result_hash": pair.result_hash,
            "purchase_pool_result_hash": pool.result_hash,
            "value_substitution_result_hash": value.result_hash,
            "config_version": config.config_version,
            "input_fingerprint": input_fingerprint,
        }
        return PriceVolumePressureAssessment(
            target=pair.target,
            candidate=pair.candidate,
            purchase_pool_level=pool.purchase_pool.level,
            value_evidence_status=value.evidence_status,
            budget_band=local_budget_band,
            market_comparability_status=comparability,
            market_pattern=pattern,
            pressure_direction=pressure,
            target_weighted_price=market.target_weighted_price,
            candidate_weighted_price=market.candidate_weighted_price,
            price_gap=market.price_gap,
            price_gap_pct=market.price_gap_pct,
            target_avg_weekly_volume=market.target_avg_weekly_volume,
            candidate_avg_weekly_volume=market.candidate_avg_weekly_volume,
            weekly_volume_gap=market.weekly_volume_gap,
            weekly_volume_ratio=market.weekly_volume_ratio,
            target_total_sales=market.target_total_sales,
            candidate_total_sales=market.candidate_total_sales,
            target_sales_amount=market.target_sales_amount,
            candidate_sales_amount=market.candidate_sales_amount,
            target_price_percentile=market.target_price_percentile,
            candidate_price_percentile=market.candidate_price_percentile,
            target_volume_percentile=market.target_volume_percentile,
            candidate_volume_percentile=market.candidate_volume_percentile,
            common_week_count=market.common_week_count,
            common_platform_count=market.common_platform_count,
            diagnostic_only_fields=sorted(diagnostics),
            confidence_level=confidence,
            review_required=review_required,
            review_reason_codes=sorted(review_reasons),
            limitations=sorted(limitations),
            evidence_refs=evidence_refs,
            pair_feature_result_hash=pair.result_hash,
            purchase_pool_result_hash=pool.result_hash,
            value_substitution_result_hash=value.result_hash,
            config_version=config.config_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                payload,
                version="competitor_profile_price_volume_pressure_pair_result_v1",
            ),
        )


def _budget_band(
    price_gap_pct: Decimal | None,
    config: PriceVolumePressureConfig,
) -> str:
    if price_gap_pct is None:
        return "unknown"
    absolute = abs(price_gap_pct)
    if absolute <= config.same_budget_max_gap_ratio:
        return "same"
    if absolute <= config.adjacent_budget_max_gap_ratio:
        return "adjacent"
    return "outside"


def _market_pattern(
    *,
    market,
    budget_band: str,
    review_required: bool,
    config: PriceVolumePressureConfig,
) -> tuple[str, list[str]]:
    if review_required:
        return "review_required", ["m07_review_or_lineage_conflict"]
    if market.comparability_status == "unknown":
        return "no_market_comparison", list(market.unknown_reasons)
    required = (
        market.target_weighted_price,
        market.candidate_weighted_price,
        market.target_avg_weekly_volume,
        market.candidate_avg_weekly_volume,
        market.price_gap,
        market.price_gap_pct,
        market.weekly_volume_gap,
        market.weekly_volume_ratio,
    )
    if any(value is None for value in required):
        return "no_market_comparison", ["required_price_volume_fact_unknown"]
    if (
        market.target_weighted_price <= 0
        or market.candidate_weighted_price <= 0
        or market.target_avg_weekly_volume <= 0
        or market.candidate_avg_weekly_volume <= 0
    ):
        return "no_market_comparison", ["positive_price_and_weekly_volume_required"]
    ratio = market.weekly_volume_ratio
    if ratio >= config.material_higher_volume_ratio:
        volume_direction = "higher"
    elif ratio <= config.material_lower_volume_ratio:
        volume_direction = "lower"
    else:
        return "volume_parity", []
    if budget_band == "same":
        return (
            "same_budget_candidate_higher_volume"
            if volume_direction == "higher"
            else "same_budget_candidate_lower_volume",
            [],
        )
    if market.price_gap < 0:
        return (
            "lower_price_candidate_higher_volume"
            if volume_direction == "higher"
            else "lower_price_lower_volume",
            [],
        )
    return (
        "higher_price_candidate_higher_volume"
        if volume_direction == "higher"
        else "higher_price_lower_volume",
        [],
    )


def _pressure_direction(
    *,
    pattern: str,
    pool_level: str,
    budget_band: str,
    value_status: str,
) -> str:
    if pattern in {"no_market_comparison", "review_required"}:
        return "unassessable"
    if pool_level == "unknown":
        return "unassessable"
    if pool_level == "P3" or budget_band == "outside":
        return "reference_only"
    if value_status in {"unassessable", "conflict"}:
        return "reference_only"
    if pattern == "same_budget_candidate_higher_volume":
        return (
            "value_route_pressure"
            if value_status == "different_route"
            else "direct_budget_pressure"
        )
    if pattern == "lower_price_candidate_higher_volume":
        return "downtrade_volume_pressure"
    if pattern == "higher_price_candidate_higher_volume":
        return (
            "value_route_pressure"
            if value_status == "different_route"
            else "uptrade_market_acceptance"
        )
    return "no_observed_pressure"


def _pressure_limitations(
    pattern: str,
    pressure: str,
    value_status: str,
) -> set[str]:
    limitations: set[str] = set()
    if pattern == "lower_price_lower_volume":
        limitations.add("lower_price_did_not_show_higher_market_acceptance")
    if pressure == "reference_only":
        limitations.add("market_reference_not_purchase_pressure_conclusion")
    if value_status in {"unassessable", "conflict"}:
        limitations.add("value_evidence_not_sufficient_for_pressure_attribution")
    if pressure != "unassessable":
        limitations.add("descriptive_market_association_not_causal_increment")
    return limitations


def _confidence(
    *,
    pressure: str,
    comparability: str,
    pool_level: str,
    value_status: str,
    review_required: bool,
) -> str:
    if pressure == "unassessable" or review_required:
        return "unknown"
    if pressure in {"reference_only", "no_observed_pressure"}:
        return "low"
    if (
        comparability == "comparable"
        and pool_level in {"P0", "P1"}
        and value_status in {"strong_overlap", "limited_overlap"}
    ):
        return "high"
    return "medium"


def _m07_refs(refs: Sequence[EvidenceRef]) -> list[EvidenceRef]:
    return _merge_refs(ref for ref in refs if ref.module_code == "M07")


def _merge_refs(*groups: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    unique: dict[tuple[str, str, str, str, str], EvidenceRef] = {}
    for group in groups:
        for ref in group:
            key = (
                ref.module_code,
                ref.source_batch_id or "",
                ref.record_type,
                ref.record_id,
                ref.result_hash,
            )
            unique[key] = ref
    return [unique[key] for key in sorted(unique)]


def _ref_payload(ref: EvidenceRef) -> Mapping[str, object]:
    return ref.model_dump(mode="json")


__all__ = [
    "PriceVolumePressureEvaluationError",
    "PriceVolumePressureEvaluator",
]
