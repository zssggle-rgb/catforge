"""Typed integration contracts for sellpoint-value profile V5.1 drafts."""

from __future__ import annotations

from typing import Any, Literal, Protocol, Sequence

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SellpointValueProfileReadBundle,
    SellpointValueVersionRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_config import (
    SellpointValueV51MethodConfig,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_COMPETITOR_METHOD_VERSION,
    SPV_V5_1_CONFIG_VERSION,
    SPV_V5_1_METHOD_VERSION,
    SPV_V5_1_RULE_VERSION,
    SPV_V5_1_SCHEMA_VERSION,
    DirectMarketComparisonResult,
    InvestmentScopeReview,
    LocalCapabilityInvestmentDecision,
    MarketArchetypeEnhancementResult,
    ParameterGroupComparisonResult,
    QuantificationLayer,
    QuestionConclusionSignal,
    SellpointValueCandidatePools,
    SellpointValueCompetitorSource,
    SkuConclusionResult,
    StrictMarketImpliedWtpResult,
    SyntheticMarketBaselineResult,
    ValueConclusionResult,
    ValueQuantificationStack,
)


class SellpointValueV51Target(SellpointValueProfileBaseModel):
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    display_name_cn: str = Field(min_length=1)


class SellpointValueV51SourceLineage(SellpointValueProfileBaseModel):
    source_code: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    version_id: str | None = None
    method_version: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    record_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ordered_fields(self) -> "SellpointValueV51SourceLineage":
        if self.record_ids != sorted(set(self.record_ids)):
            raise ValueError("lineage record ids must be sorted and unique")
        return self


class SellpointValueV51ValueInput(SellpointValueProfileBaseModel):
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str | None = None
    purchase_reason_code: str | None = None
    purchase_reason_name_cn: str | None = None
    value_bundle_code: str = Field(min_length=1)
    value_bundle_name_cn: str = Field(min_length=1)
    normalized_bundle_code: str = Field(min_length=1)
    perceived_outcome_cn: str = Field(min_length=1)
    capability_codes: list[str] = Field(default_factory=list)
    question_signals: list[QuestionConclusionSignal] = Field(default_factory=list)
    quantification_stack: ValueQuantificationStack
    direct_market_results: list[DirectMarketComparisonResult] = Field(
        default_factory=list
    )
    parameter_group_results: list[ParameterGroupComparisonResult] = Field(
        default_factory=list
    )
    market_archetype_results: list[MarketArchetypeEnhancementResult] = Field(
        default_factory=list
    )
    synthetic_market_baseline: SyntheticMarketBaselineResult | None = None
    strict_market_implied_wtp: StrictMarketImpliedWtpResult | None = None
    investment_decisions: list[LocalCapabilityInvestmentDecision] = Field(
        default_factory=list
    )
    investment_reviews: list[InvestmentScopeReview] = Field(default_factory=list)
    value_conclusion: ValueConclusionResult
    evidence_boundary_cn: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_value_graph(self) -> "SellpointValueV51ValueInput":
        if self.capability_codes != sorted(set(self.capability_codes)):
            raise ValueError("value capability codes must be sorted and unique")
        question_codes = [row.question_code for row in self.question_signals]
        if len(question_codes) != len(set(question_codes)):
            raise ValueError("materialized value questions must be unique")
        if self.quantification_stack.value_bundle_code != self.value_bundle_code:
            raise ValueError("quantification stack must match value bundle")
        layers = {row.layer for row in self.quantification_stack.results}
        if layers != set(QuantificationLayer):
            raise ValueError("V5.1 values must persist all four quantification layers")
        if self.value_conclusion.value_bundle_code != self.value_bundle_code:
            raise ValueError("value conclusion must match value bundle")
        signal_hashes = sorted(
            {row.source_result_hash for row in self.question_signals}
        )
        if self.value_conclusion.source_result_hashes != signal_hashes:
            raise ValueError(
                "value conclusion must aggregate the saved question hashes"
            )
        analytical_hashes = {
            *(row.result_hash for row in self.quantification_stack.results),
            *(row.result_hash for row in self.direct_market_results),
            *(row.result_hash for row in self.parameter_group_results),
            *(row.result_hash for row in self.market_archetype_results),
            *(
                [self.synthetic_market_baseline.result_hash]
                if self.synthetic_market_baseline is not None
                else []
            ),
            *(
                [self.strict_market_implied_wtp.result_hash]
                if self.strict_market_implied_wtp is not None
                else []
            ),
            *(row.result_hash for row in self.investment_decisions),
            *(row.result_hash for row in self.investment_reviews),
        }
        if not analytical_hashes.issubset(set(signal_hashes)):
            raise ValueError(
                "every saved analytical result must have a question conclusion signal"
            )
        return self


class SellpointValueV51MaterializationInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    target: SellpointValueV51Target
    competitor_source: SellpointValueCompetitorSource
    candidate_pools: SellpointValueCandidatePools
    method_config: SellpointValueV51MethodConfig
    source_lineage: list[SellpointValueV51SourceLineage] = Field(default_factory=list)
    values: list[SellpointValueV51ValueInput] = Field(default_factory=list)
    sku_conclusion: SkuConclusionResult
    generated_by: str = Field(default="system", min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self) -> "SellpointValueV51MaterializationInput":
        source = self.competitor_source
        pools = self.candidate_pools
        if (
            source.project_id != self.project_id
            or source.category_code != self.category_code
            or source.release_scope_key != self.release_scope_key
            or source.target_sku_code != self.target.sku_code
        ):
            raise ValueError("competitor source must match materialization scope")
        if (
            pools.project_id != self.project_id
            or pools.category_code != self.category_code
            or pools.target_sku_code != self.target.sku_code
            or pools.competitor_profile_version_id
            != source.competitor_profile_version_id
            or pools.competitor_source_result_hash != source.source_result_hash
            or pools.competitor_source_version_result_hash
            != source.source_version_result_hash
        ):
            raise ValueError("candidate pools must match the competitor source")
        if self.method_config.category_code != self.category_code:
            raise ValueError("method config must match materialization category")
        if (
            source.target_market.sku_code != self.target.sku_code
            or source.target_market.product_category != self.category_code
        ):
            raise ValueError("target identity must match source market facts")
        value_codes = [row.value_bundle_code for row in self.values]
        if len(value_codes) != len(set(value_codes)):
            raise ValueError("materialized values must be unique")
        if any(
            _value_scope(row)
            != (self.project_id, self.category_code, self.target.sku_code)
            for row in self.values
        ):
            raise ValueError("all value results must stay within materialization scope")
        if (
            self.sku_conclusion.project_id != self.project_id
            or self.sku_conclusion.category_code != self.category_code
            or self.sku_conclusion.target_sku_code != self.target.sku_code
            or self.sku_conclusion.source_result_hashes
            != sorted(row.value_conclusion.result_hash for row in self.values)
        ):
            raise ValueError("SKU conclusion must aggregate the saved value results")
        lineage_codes = [row.source_code for row in self.source_lineage]
        if len(lineage_codes) != len(set(lineage_codes)):
            raise ValueError("source lineage codes must be unique")
        return self


class SellpointValueV51Profile(SellpointValueProfileBaseModel):
    schema_version: Literal["sku_sellpoint_value_decision_profile_v1_1"] = (
        SPV_V5_1_SCHEMA_VERSION
    )
    rule_version: Literal["sellpoint_value_profile_rule_v5_1"] = SPV_V5_1_RULE_VERSION
    method_version: Literal["sellpoint_value_profile_method_v5_1"] = (
        SPV_V5_1_METHOD_VERSION
    )
    config_version: Literal["sellpoint_value_profile_low_gate_v5_1"] = (
        SPV_V5_1_CONFIG_VERSION
    )
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    target: SellpointValueV51Target
    competitor_source: SellpointValueCompetitorSource
    candidate_pools: SellpointValueCandidatePools
    method_config: SellpointValueV51MethodConfig
    source_lineage: list[SellpointValueV51SourceLineage]
    values: list[SellpointValueV51ValueInput]
    sku_conclusion: SkuConclusionResult
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_materialized_profile(self) -> "SellpointValueV51Profile":
        if [row.source_code for row in self.source_lineage] != sorted(
            row.source_code for row in self.source_lineage
        ):
            raise ValueError("materialized lineage must be canonical")
        if [row.value_bundle_code for row in self.values] != sorted(
            row.value_bundle_code for row in self.values
        ):
            raise ValueError("materialized values must be canonical")
        SellpointValueV51MaterializationInput(
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            release_scope_key=self.release_scope_key,
            profile_version=self.profile_version,
            target=self.target,
            competitor_source=self.competitor_source,
            candidate_pools=self.candidate_pools,
            method_config=self.method_config,
            source_lineage=[
                row for row in self.source_lineage if row.source_type == "upstream"
            ],
            values=self.values,
            sku_conclusion=self.sku_conclusion,
        )
        return self


class SellpointValueV51MaterializedDraft(SellpointValueProfileBaseModel):
    profile: SellpointValueV51Profile
    persistence_bundle: SellpointValueDraftBundle

    @model_validator(mode="after")
    def validate_hashes(self) -> "SellpointValueV51MaterializedDraft":
        if (
            self.profile.input_fingerprint
            != self.persistence_bundle.profile.input_fingerprint
            or self.profile.result_hash != self.persistence_bundle.profile.result_hash
        ):
            raise ValueError("typed and persisted profile hashes must match")
        return self


class SellpointValueV51CompetitorVersionSource(SellpointValueProfileBaseModel):
    access_mode: Literal["formal", "preview"]
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    method_version: Literal["competitor_profile_agent_snapshot_v2"] = (
        SPV_V5_1_COMPETITOR_METHOD_VERSION
    )
    release_status: Literal["draft", "published"]
    is_current: bool
    release_scope_key: str = Field(min_length=1)
    version_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_release(self) -> "SellpointValueV51CompetitorVersionSource":
        if self.access_mode == "formal" and (
            self.release_status != "published" or not self.is_current
        ):
            raise ValueError("formal competitor versions must be current published")
        if self.access_mode == "preview" and not (
            (self.release_status == "draft" and not self.is_current)
            or (self.release_status == "published" and self.is_current)
        ):
            raise ValueError(
                "preview competitor versions must be explicit drafts or current"
            )
        return self


class SellpointValueV51VersionRequest(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    competitor_source: SellpointValueV51CompetitorVersionSource
    expected_sku_codes: list[str] = Field(min_length=1)
    candidate_pool_hashes: dict[str, str]
    method_config: SellpointValueV51MethodConfig
    method_versions: dict[str, str]
    source_lineage: list[SellpointValueV51SourceLineage] = Field(default_factory=list)
    generated_by: str = Field(default="system", min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> "SellpointValueV51VersionRequest":
        if self.expected_sku_codes != sorted(set(self.expected_sku_codes)):
            raise ValueError("expected SKU codes must be sorted and unique")
        if set(self.candidate_pool_hashes) != set(self.expected_sku_codes):
            raise ValueError("candidate pool hashes must cover every expected SKU")
        if self.method_config.category_code != self.category_code:
            raise ValueError("version config must match category")
        if not self.method_versions:
            raise ValueError("version method versions are required")
        if [row.source_code for row in self.source_lineage] != sorted(
            row.source_code for row in self.source_lineage
        ):
            raise ValueError("version source lineage must be canonical")
        return self


class SellpointValueV51Readback(SellpointValueProfileBaseModel):
    profile: SellpointValueV51Profile
    persisted: SellpointValueProfileReadBundle


class SellpointValueV51SkuGenerationStatus(SellpointValueProfileBaseModel):
    sku_code: str = Field(min_length=1)
    status: Literal["generated", "reused", "failed"]
    profile_result_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class SellpointValueV51BatchGenerationResult(SellpointValueProfileBaseModel):
    version: SellpointValueVersionRecord
    statuses: list[SellpointValueV51SkuGenerationStatus]
    generated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "SellpointValueV51BatchGenerationResult":
        if self.generated_count + self.reused_count + self.failed_count != len(
            self.statuses
        ):
            raise ValueError("generation counts must match statuses")
        return self


class SellpointValueV51InputProvider(Protocol):
    def load_materialization_input(
        self,
        request: SellpointValueV51VersionRequest,
        sku_code: str,
    ) -> SellpointValueV51MaterializationInput: ...


def _value_scope(
    value: SellpointValueV51ValueInput,
) -> tuple[str, str, str]:
    conclusion = value.value_conclusion
    expected = (
        conclusion.project_id,
        conclusion.category_code,
        conclusion.target_sku_code,
    )
    scoped: Sequence[Any] = [
        *value.direct_market_results,
        *value.parameter_group_results,
        *value.market_archetype_results,
        *value.investment_decisions,
        *value.investment_reviews,
        *(
            [value.synthetic_market_baseline]
            if value.synthetic_market_baseline is not None
            else []
        ),
        *(
            [value.strict_market_implied_wtp]
            if value.strict_market_implied_wtp is not None
            else []
        ),
    ]
    for row in scoped:
        if (
            row.project_id,
            row.category_code,
            row.target_sku_code,
        ) != expected or row.value_bundle_code != value.value_bundle_code:
            return ("", "", "")
    return expected


__all__ = [
    "SellpointValueV51BatchGenerationResult",
    "SellpointValueV51CompetitorVersionSource",
    "SellpointValueV51InputProvider",
    "SellpointValueV51MaterializationInput",
    "SellpointValueV51MaterializedDraft",
    "SellpointValueV51Profile",
    "SellpointValueV51Readback",
    "SellpointValueV51SkuGenerationStatus",
    "SellpointValueV51SourceLineage",
    "SellpointValueV51Target",
    "SellpointValueV51ValueInput",
    "SellpointValueV51VersionRequest",
]
