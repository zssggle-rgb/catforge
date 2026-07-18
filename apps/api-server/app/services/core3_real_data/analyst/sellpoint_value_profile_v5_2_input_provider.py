"""Production input assembly for immutable sellpoint-value V5.2 drafts.

V5.2 deliberately reuses the proven V5.1 market/value graph and adds only the
saved M04C product-sellpoint layer.  The provider keeps at most one assembled
SKU in memory so a category run scales with the current SKU rather than the
whole category.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_input_provider import (
    SavedV5SellpointValueV51InputProvider,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_claim_reader import (
    M04CSourceSellpointReadRequest,
    M04CSourceSellpointReader,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer import (
    build_v5_2_source_hashes,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_mapping import (
    CompetitorSellpointObservation,
    match_source_sellpoint_value_bundle_codes,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52MaterializationInput,
    SellpointValueV52VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)


_PRESSURE_RANK = {
    "unassessed": -1,
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
_SUPPORTED_MARKET_LEVELS = {
    "directional",
    "moderate",
    "strong",
    "supported",
}
_TARGET_WEAKNESS_CLASSES = {
    "missing_competitive_gap",
    "unconverted",
}


class SavedV5SellpointValueV52InputProvider:
    """Join one saved V5.1 graph with the same SKU's current M04C facts."""

    def __init__(
        self,
        *,
        base_provider: SavedV5SellpointValueV51InputProvider,
        source_sellpoint_reader: M04CSourceSellpointReader,
    ) -> None:
        self.base_provider = base_provider
        self.source_sellpoint_reader = source_sellpoint_reader
        self._cache: dict[
            tuple[str, str, str],
            SellpointValueV52MaterializationInput,
        ] = {}

    def build_version_request(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        profile_version: str,
        expected_sku_codes: Sequence[str],
        generated_by: str,
    ) -> SellpointValueV52VersionRequest:
        base = self.base_provider.build_version_request(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            profile_version=profile_version,
            expected_sku_codes=expected_sku_codes,
            generated_by=generated_by,
        )
        hashes = {}
        for sku_code in base.expected_sku_codes:
            source = self._build_input(base, sku_code)
            hashes[sku_code] = build_v5_2_source_hashes(source)
            self._remember_input(
                (base.profile_version, base.batch_id, sku_code),
                source,
            )
        return SellpointValueV52VersionRequest(
            base=base,
            source_hashes_by_sku=dict(sorted(hashes.items())),
        )

    def load_materialization_input(
        self,
        request: SellpointValueV52VersionRequest,
        sku_code: str,
    ) -> SellpointValueV52MaterializationInput:
        normalized = sku_code.strip().upper()
        key = (
            request.base.profile_version,
            request.base.batch_id,
            normalized,
        )
        source = self._cache.get(key)
        if source is None:
            source = self._build_input(request.base, normalized)
            self._remember_input(key, source)
        if (
            build_v5_2_source_hashes(source)
            != request.source_hashes_by_sku.get(normalized)
        ):
            raise ValueError(
                "saved V5.2 upstream inputs changed after request creation"
            )
        return source

    def _build_input(
        self,
        base_request: SellpointValueV51VersionRequest,
        sku_code: str,
    ) -> SellpointValueV52MaterializationInput:
        # The concrete request is intentionally obtained from the V5.1
        # provider so its existing scope and competitor-version checks remain
        # authoritative.
        base = self.base_provider.load_materialization_input(
            base_request,
            sku_code,
        )
        source_sellpoints = self.source_sellpoint_reader.read(
            M04CSourceSellpointReadRequest(
                project_id=base.project_id,
                category_code=base.category_code,
                batch_id=base.batch_id,
                sku_code=base.target.sku_code,
            )
        )
        competitor_sellpoints = self._competitor_sellpoints(
            base=base,
            target_source_sellpoints=source_sellpoints.source_sellpoints,
        )
        return SellpointValueV52MaterializationInput(
            base=base,
            source_sellpoints=source_sellpoints,
            competitor_sellpoints=competitor_sellpoints,
        )

    def _competitor_sellpoints(
        self,
        *,
        base: Any,
        target_source_sellpoints: Sequence[Any],
    ) -> list[CompetitorSellpointObservation]:
        candidates = list(base.candidate_pools.formal_competitors)
        if not candidates:
            return []
        requests = [
            M04CSourceSellpointReadRequest(
                project_id=base.project_id,
                category_code=base.category_code,
                batch_id=base.batch_id,
                sku_code=candidate.candidate_sku_code,
            )
            for candidate in candidates
        ]
        reader = getattr(self.source_sellpoint_reader, "read_many", None)
        if reader is None:
            competitor_sources = {
                request.sku_code: self.source_sellpoint_reader.read(request)
                for request in requests
            }
        else:
            competitor_sources = reader(requests)

        target_claim_codes = {
            row.normalized_claim_code for row in target_source_sellpoints
        }
        target_value_codes = {
            value_code
            for sellpoint in target_source_sellpoints
            for value_code in match_source_sellpoint_value_bundle_codes(
                category_code=base.category_code,
                source_sellpoint=sellpoint,
                values=base.values,
            )
        }
        observations = []
        for candidate in candidates:
            result = competitor_sources.get(candidate.candidate_sku_code)
            if result is None:
                continue
            for sellpoint in result.source_sellpoints:
                linked_value_codes = match_source_sellpoint_value_bundle_codes(
                    category_code=base.category_code,
                    source_sellpoint=sellpoint,
                    values=base.values,
                )
                observations.append(
                    CompetitorSellpointObservation(
                        candidate_sku_code=candidate.candidate_sku_code,
                        source_sellpoint=sellpoint,
                        target_has_matching_sellpoint=(
                            sellpoint.normalized_claim_code
                            in target_claim_codes
                            or bool(
                                target_value_codes
                                & set(linked_value_codes)
                            )
                        ),
                        competitor_value_advantage=(
                            _candidate_value_advantage(
                                candidate,
                                linked_value_codes=linked_value_codes,
                                values=base.values,
                            )
                        ),
                        target_value_weakness=_target_value_weakness(
                            linked_value_codes,
                            values=base.values,
                        ),
                        market_support=_market_support(candidate),
                        linked_value_bundle_codes=linked_value_codes,
                        evidence_refs=[
                            SellpointValueEvidenceRef(
                                module_code="COMPETITOR_PROFILE",
                                record_type="pair",
                                record_id=(
                                    f"{base.target.sku_code}:"
                                    f"{candidate.candidate_sku_code}"
                                ),
                                result_hash=candidate.pair_result_hash,
                            )
                        ],
                    )
                )
        return sorted(
            observations,
            key=lambda row: (
                row.candidate_sku_code,
                row.source_sellpoint.claim_fact_id,
            ),
        )

    def _remember_input(
        self,
        key: tuple[str, str, str],
        source: SellpointValueV52MaterializationInput,
    ) -> None:
        self._cache.clear()
        self._cache[key] = source


def _target_value_weakness(
    linked_value_codes: Sequence[str],
    *,
    values: Sequence[Any],
) -> bool:
    linked = set(linked_value_codes)
    return any(
        _enum_text(decision.classification) in _TARGET_WEAKNESS_CLASSES
        for value in values
        if str(value.value_bundle_code) in linked
        for decision in value.investment_decisions
    )


def _candidate_value_advantage(
    candidate: Any,
    *,
    linked_value_codes: Sequence[str],
    values: Sequence[Any],
) -> bool:
    if not linked_value_codes:
        return False
    relevant_keys = _relevant_value_keys(linked_value_codes, values)
    pair = candidate.pair_facts
    pressure = pair.purchase_pressure_comparison or {}
    if pressure.get("comparison_allowed"):
        for row in pressure.get("shared_anchor_comparisons") or ():
            if not _mapping_matches_keys(row, relevant_keys):
                continue
            target_rank = _PRESSURE_RANK.get(
                _enum_text(row.get("target_pressure_level")),
                -1,
            )
            candidate_rank = _PRESSURE_RANK.get(
                _enum_text(row.get("candidate_pressure_level")),
                -1,
            )
            if target_rank > candidate_rank >= 0:
                return True

    anchors = pair.anchor_substitutability or {}
    return any(
        _value_matches_keys(anchor, relevant_keys)
        for anchor in anchors.get("candidate_stronger_anchors") or ()
    )


def _relevant_value_keys(
    linked_value_codes: Sequence[str],
    values: Sequence[Any],
) -> set[str]:
    linked = set(linked_value_codes)
    keys = {_normalized_key(code) for code in linked}
    for value in values:
        if str(value.value_bundle_code) not in linked:
            continue
        keys.update(
            _normalized_key(item)
            for item in (
                value.value_bundle_code,
                value.normalized_bundle_code,
                value.battlefield_code,
                value.purchase_reason_code,
                *value.capability_codes,
            )
            if item
        )
    return {key for key in keys if key}


def _mapping_matches_keys(
    row: Mapping[str, Any],
    relevant_keys: set[str],
) -> bool:
    return any(
        _value_matches_keys(row.get(field), relevant_keys)
        for field in ("anchor_code", "anchor_cn", "value_bundle_code")
    )


def _value_matches_keys(value: Any, relevant_keys: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(
            _value_matches_keys(item, relevant_keys)
            for item in value.values()
        )
    normalized = _normalized_key(value)
    return bool(
        normalized
        and any(
            normalized == key
            or (
                len(normalized) >= 6
                and len(key) >= 6
                and (normalized in key or key in normalized)
            )
            for key in relevant_keys
        )
    )


def _market_support(candidate: Any) -> bool:
    validation = candidate.pair_facts.market_validation or {}
    level = _enum_text(
        validation.get("level")
        or validation.get("market_validation_strength")
        or (validation.get("conclusion") or {}).get("strength")
    )
    weekly_sales = candidate.market.avg_weekly_sales_volume
    return (
        level in _SUPPORTED_MARKET_LEVELS
        and weekly_sales is not None
        and weekly_sales > 0
    )


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", _enum_text(value))


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


__all__ = ["SavedV5SellpointValueV52InputProvider"]
