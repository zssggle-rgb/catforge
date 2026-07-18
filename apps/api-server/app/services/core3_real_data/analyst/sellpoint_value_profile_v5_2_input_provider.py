"""Production input assembly for immutable sellpoint-value V5.2 drafts.

V5.2 deliberately reuses the proven V5.1 market/value graph and adds only the
saved M04C product-sellpoint layer.  The provider keeps at most one assembled
SKU in memory so a category run scales with the current SKU rather than the
whole category.
"""

from __future__ import annotations

from collections.abc import Sequence

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
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52MaterializationInput,
    SellpointValueV52VersionRequest,
)


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
        return SellpointValueV52MaterializationInput(
            base=base,
            source_sellpoints=source_sellpoints,
        )

    def _remember_input(
        self,
        key: tuple[str, str, str],
        source: SellpointValueV52MaterializationInput,
    ) -> None:
        self._cache.clear()
        self._cache[key] = source


__all__ = ["SavedV5SellpointValueV52InputProvider"]
