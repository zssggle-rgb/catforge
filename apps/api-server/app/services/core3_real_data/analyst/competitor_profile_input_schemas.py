"""Typed, fact-only inputs for competitor-profile materialization."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
    EvidenceRef,
    ServingScope,
    SourceAuthorityRef,
)


COMPETITOR_PROFILE_INPUT_SCHEMA_VERSION = "competitor_profile_input_bundle_v1"
COMPETITOR_PROFILE_INPUT_PROVIDER_VERSION = "competitor_profile_input_provider_v1"
COMPETITOR_PROFILE_SOURCE_MODULES = (
    "M03B",
    "M04C",
    "M05C",
    "M07",
    "M09C",
    "M10C",
    "M11C",
    "M11D",
    "M12C",
    "M12D",
)
HARD_REQUIRED_TARGET_MODULES = frozenset({"M03B", "M07"})


class CompetitorProfileInputRequest(CompetitorProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    storage_batch_id: str = Field(min_length=1)
    source_batch_ids: list[str] = Field(min_length=1)
    analysis_population: str = Field(min_length=1)
    semantic_market_analysis_population: str = Field(min_length=1)
    claim_value_analysis_population: str = Field(min_length=1)
    market_window: str = Field(min_length=1)
    allow_preview_inputs: Literal[False] = False

    @model_validator(mode="after")
    def validate_scope(self) -> "CompetitorProfileInputRequest":
        if self.category_code != self.product_category:
            raise ValueError("input request category and product category must match")
        if self.source_batch_ids != sorted(set(self.source_batch_ids)):
            raise ValueError("input source batch IDs must be sorted and unique")
        if self.storage_batch_id not in self.source_batch_ids:
            raise ValueError("storage batch must be inside the source batch scope")
        if self.category_code == "AC" and len(self.source_batch_ids) != 1:
            raise ValueError("AC input scope requires exactly one source batch")
        return self


class UpstreamRecordSnapshot(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    source_batch_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    facts: dict[str, Any]

    @model_validator(mode="after")
    def validate_record_scope(self) -> "UpstreamRecordSnapshot":
        if self.category_code != self.product_category:
            raise ValueError("upstream record category and product category must match")
        return self


class ModuleCategorySnapshot(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    authority: SourceAuthorityRef
    hard_required_for_target: bool
    record_count: int = Field(ge=0)
    sku_count: int = Field(ge=0)
    records_by_sku: dict[str, list[UpstreamRecordSnapshot]] = Field(default_factory=dict)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_module(self) -> "ModuleCategorySnapshot":
        if self.module_code != self.authority.module_code:
            raise ValueError("module snapshot authority must match module code")
        if self.hard_required_for_target and not self.records_by_sku:
            raise ValueError("hard-required category modules cannot be empty")
        if not self.records_by_sku and self.authority.release_status != "unavailable":
            raise ValueError("empty optional modules require unavailable authority state")
        if list(self.records_by_sku) != sorted(self.records_by_sku):
            raise ValueError("module SKU keys must be sorted")
        records = [
            row
            for sku_code in self.records_by_sku
            for row in self.records_by_sku[sku_code]
        ]
        if len(records) != self.record_count:
            raise ValueError("module record count must match stored records")
        if len(self.records_by_sku) != self.sku_count:
            raise ValueError("module SKU count must match stored SKU keys")
        for sku_code, rows in self.records_by_sku.items():
            if not rows or any(row.sku_code != sku_code for row in rows):
                raise ValueError("module records must stay inside their SKU key")
            if rows != sorted(
                rows,
                key=lambda row: (row.source_batch_id, row.record_id),
            ):
                raise ValueError("module records must use deterministic order")
        return self


class CompetitorProfileCategoryInputBundle(CompetitorProfileBaseModel):
    schema_version: str = COMPETITOR_PROFILE_INPUT_SCHEMA_VERSION
    provider_version: str = COMPETITOR_PROFILE_INPUT_PROVIDER_VERSION
    serving_scope: ServingScope
    authoritative_sku_codes: list[str] = Field(min_length=1)
    modules: dict[str, ModuleCategorySnapshot]
    input_fingerprint: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_category_bundle(self) -> "CompetitorProfileCategoryInputBundle":
        if self.authoritative_sku_codes != sorted(set(self.authoritative_sku_codes)):
            raise ValueError("authoritative SKU manifest must be sorted and unique")
        if set(self.modules) != set(COMPETITOR_PROFILE_SOURCE_MODULES):
            raise ValueError("category input must contain all source modules")
        if set(self.serving_scope.source_authorities) != set(
            COMPETITOR_PROFILE_SOURCE_MODULES
        ):
            raise ValueError("serving scope must lock every source authority")
        for module_code, snapshot in self.modules.items():
            if module_code != snapshot.module_code:
                raise ValueError("module dict key must match module snapshot")
            if snapshot.authority != self.serving_scope.source_authorities[module_code]:
                raise ValueError("module snapshot must use the locked source authority")
        return self


class TargetModuleInput(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    availability: Literal["present", "unknown"]
    hard_required: bool
    records: list[UpstreamRecordSnapshot] = Field(default_factory=list)
    missing_reason_code: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> "TargetModuleInput":
        if self.availability == "present":
            if not self.records or self.missing_reason_code is not None:
                raise ValueError("present module inputs require records and no missing reason")
        elif self.records or not self.missing_reason_code:
            raise ValueError("unknown module inputs require a missing reason and no records")
        return self


class CompetitorProfileTargetInputBundle(CompetitorProfileBaseModel):
    schema_version: str = COMPETITOR_PROFILE_INPUT_SCHEMA_VERSION
    provider_version: str = COMPETITOR_PROFILE_INPUT_PROVIDER_VERSION
    serving_scope: ServingScope
    target_sku_code: str = Field(min_length=1)
    target_identity: dict[str, Any]
    modules: dict[str, TargetModuleInput]
    analysis_state: Literal["ready", "partial", "blocked"]
    hard_block_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_bundle(self) -> "CompetitorProfileTargetInputBundle":
        if set(self.modules) != set(COMPETITOR_PROFILE_SOURCE_MODULES):
            raise ValueError("target input must contain all source modules")
        if self.analysis_state == "blocked" and not self.hard_block_reasons:
            raise ValueError("blocked target inputs require hard-block reasons")
        if self.analysis_state != "blocked" and self.hard_block_reasons:
            raise ValueError("non-blocked target inputs cannot carry hard-block reasons")
        if self.analysis_state == "ready" and self.limitations:
            raise ValueError("ready target inputs cannot carry missing-module limitations")
        return self


__all__ = [
    "COMPETITOR_PROFILE_INPUT_PROVIDER_VERSION",
    "COMPETITOR_PROFILE_INPUT_SCHEMA_VERSION",
    "COMPETITOR_PROFILE_SOURCE_MODULES",
    "HARD_REQUIRED_TARGET_MODULES",
    "CompetitorProfileCategoryInputBundle",
    "CompetitorProfileInputRequest",
    "CompetitorProfileTargetInputBundle",
    "ModuleCategorySnapshot",
    "TargetModuleInput",
    "UpstreamRecordSnapshot",
]
