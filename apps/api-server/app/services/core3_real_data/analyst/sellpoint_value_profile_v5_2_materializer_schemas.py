"""Typed materialization and generation contracts for V5.2 drafts."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SellpointValueProfileReadBundle,
    SellpointValueVersionRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51MaterializationInput,
    SellpointValueV51Profile,
    SellpointValueV51VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_mapping import (
    CompetitorSellpointObservation,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    LayeredSellpointAnalysis,
    SPV_V5_2_METHOD_VERSION,
    SPV_V5_2_RULE_VERSION,
    SPV_V5_2_SCHEMA_VERSION,
    SourceSellpointReadResult,
)


class SellpointValueV52SourceHashes(SellpointValueProfileBaseModel):
    m04c_profile_result_hash: str = Field(min_length=1)
    m03b_parameter_result_hashes: list[str] = Field(default_factory=list)
    upstream_result_hashes: dict[str, str] = Field(default_factory=dict)
    user_value_result_hashes: list[str] = Field(default_factory=list)
    competitor_profile_result_hash: str = Field(min_length=1)
    competitor_sku_result_hash: str = Field(min_length=1)
    competitor_sellpoint_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hashes(self) -> "SellpointValueV52SourceHashes":
        for hashes in (
            self.m03b_parameter_result_hashes,
            self.user_value_result_hashes,
        ):
            if hashes != sorted(set(hashes)):
                raise ValueError("source result hashes must be sorted and unique")
        if list(self.upstream_result_hashes) != sorted(
            self.upstream_result_hashes
        ):
            raise ValueError("upstream source hashes must be canonical")
        return self


class SellpointValueV52MaterializationInput(SellpointValueProfileBaseModel):
    base: SellpointValueV51MaterializationInput
    source_sellpoints: SourceSellpointReadResult
    competitor_sellpoints: list[CompetitorSellpointObservation] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_scope(self) -> "SellpointValueV52MaterializationInput":
        lineage = self.source_sellpoints.lineage
        if lineage is not None and (
            lineage.project_id != self.base.project_id
            or lineage.category_code != self.base.category_code
            or lineage.batch_id != self.base.batch_id
            or lineage.sku_code != self.base.target.sku_code
        ):
            raise ValueError("M04C source sellpoints must match materialization scope")
        return self


class SellpointValueV52Profile(SellpointValueProfileBaseModel):
    schema_version: Literal["sku_sellpoint_value_decision_profile_v1_2"] = (
        SPV_V5_2_SCHEMA_VERSION
    )
    rule_version: Literal["sellpoint_value_profile_rule_v5_2"] = (
        SPV_V5_2_RULE_VERSION
    )
    method_version: Literal["sellpoint_value_profile_method_v5_2"] = (
        SPV_V5_2_METHOD_VERSION
    )
    base_profile: SellpointValueV51Profile
    source_hashes: SellpointValueV52SourceHashes
    source_sellpoints: SourceSellpointReadResult
    layered_sellpoint_analysis: LayeredSellpointAnalysis
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> "SellpointValueV52Profile":
        target = self.base_profile.target
        layered = self.layered_sellpoint_analysis
        if (
            layered.category_code != self.base_profile.category_code
            or layered.target_sku_code != target.sku_code
        ):
            raise ValueError("layered sellpoint analysis must match base profile")
        if layered.source_sellpoint_state != self.source_sellpoints.status:
            raise ValueError("layered analysis must preserve M04C source state")
        return self


class SellpointValueV52MaterializedDraft(SellpointValueProfileBaseModel):
    profile: SellpointValueV52Profile
    persistence_bundle: SellpointValueDraftBundle

    @model_validator(mode="after")
    def validate_hashes(self) -> "SellpointValueV52MaterializedDraft":
        if (
            self.profile.input_fingerprint
            != self.persistence_bundle.profile.input_fingerprint
            or self.profile.result_hash
            != self.persistence_bundle.profile.result_hash
        ):
            raise ValueError("typed and persisted V5.2 hashes must match")
        return self


class SellpointValueV52Readback(SellpointValueProfileBaseModel):
    profile: SellpointValueV52Profile
    persisted: SellpointValueProfileReadBundle


class SellpointValueV52VersionRequest(SellpointValueProfileBaseModel):
    base: SellpointValueV51VersionRequest
    source_hashes_by_sku: dict[str, SellpointValueV52SourceHashes]

    @model_validator(mode="after")
    def validate_request(self) -> "SellpointValueV52VersionRequest":
        if list(self.source_hashes_by_sku) != sorted(self.source_hashes_by_sku):
            raise ValueError("V5.2 source hash manifest must be canonical")
        if set(self.source_hashes_by_sku) != set(self.base.expected_sku_codes):
            raise ValueError("V5.2 source hashes must cover every expected SKU")
        return self


class SellpointValueV52SkuGenerationStatus(SellpointValueProfileBaseModel):
    sku_code: str = Field(min_length=1)
    status: Literal["generated", "reused", "failed"]
    profile_result_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class SellpointValueV52BatchGenerationResult(SellpointValueProfileBaseModel):
    version: SellpointValueVersionRecord
    statuses: list[SellpointValueV52SkuGenerationStatus]
    generated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "SellpointValueV52BatchGenerationResult":
        if self.generated_count + self.reused_count + self.failed_count != len(
            self.statuses
        ):
            raise ValueError("generation counts must match V5.2 statuses")
        return self


class SellpointValueV52InputProvider(Protocol):
    def load_materialization_input(
        self,
        request: SellpointValueV52VersionRequest,
        sku_code: str,
    ) -> SellpointValueV52MaterializationInput: ...


__all__ = [
    "SellpointValueV52BatchGenerationResult",
    "SellpointValueV52InputProvider",
    "SellpointValueV52MaterializationInput",
    "SellpointValueV52MaterializedDraft",
    "SellpointValueV52Profile",
    "SellpointValueV52Readback",
    "SellpointValueV52SkuGenerationStatus",
    "SellpointValueV52SourceHashes",
    "SellpointValueV52VersionRequest",
]
