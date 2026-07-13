"""DTOs for materializing and diffing SKU sellpoint-value profiles."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    SkuIdentity,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    SkuPerceivedValueMarketRealizationReport,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SellpointValueProfileReadBundle,
    SellpointValueVersionRecord,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CandidateUniverseManifest,
    CapabilityInvestmentDecision,
    CapabilityThresholdConfig,
    SellpointValueProfileBaseModel,
)


REQUIRED_PROFILE_SOURCE_MODULES: tuple[str, ...] = (
    "M03B",
    "M04C",
    "M05C",
    "M07",
    "M09C",
    "M10C",
    "M11C",
    "M11D",
    "M12D",
    "M12C",
    "M12",
    "M13",
    "M14",
)


class ProfileSourceLineage(SellpointValueProfileBaseModel):
    module_code: str = Field(min_length=1)
    status: Literal["present", "missing", "conflict"]
    rule_versions: list[str] = Field(default_factory=list)
    result_hashes: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source_status(self) -> "ProfileSourceLineage":
        if self.status == "present" and not self.result_hashes:
            raise ValueError("present source lineage requires result hashes")
        if self.status != "present" and not self.limitations:
            raise ValueError("missing or conflicting lineage requires limitations")
        return self


class ProfileQaTopic(SellpointValueProfileBaseModel):
    topic_code: str = Field(min_length=1)
    question_examples_cn: list[str] = Field(default_factory=list)
    fact_paths: list[str] = Field(min_length=1)
    candidate_scope_codes: list[str] = Field(default_factory=list)
    value_item_keys: list[str] = Field(default_factory=list)
    answer_boundary_cn: str = Field(min_length=1)


class ProfileRejectedCandidate(SellpointValueProfileBaseModel):
    candidate_sku_codes: list[str] = Field(default_factory=list)
    method: str = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)


class ProfileCandidateEvaluation(SellpointValueProfileBaseModel):
    candidate_key: str = Field(min_length=1)
    candidate_sku_codes: list[str] = Field(default_factory=list)
    method: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    selected: bool
    eligible_measures: list[str] = Field(default_factory=list)
    reject_reasons: list[str] = Field(default_factory=list)
    sample_manifest_hash: str | None = None


class ProfileQuestionAnalysis(SellpointValueProfileBaseModel):
    question_code: str = Field(min_length=1)
    source_question_code: str = Field(min_length=1)
    business_question_cn: str = Field(min_length=1)
    battlefield_code: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    candidate_pool_type: Literal["competitor", "reference", "mixed", "unknown"]
    eligible_candidate_ids: list[str] = Field(default_factory=list)
    selected_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidates: list[ProfileRejectedCandidate] = Field(default_factory=list)
    candidate_evaluations: list[ProfileCandidateEvaluation] = Field(
        default_factory=list
    )
    method: str | None = None
    selection_reasons: list[str] = Field(default_factory=list)
    degradation_reasons: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    conclusion_boundary_cn: str = Field(min_length=1)
    sample_manifest_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)


class SellpointValueFivePmDecisions(SellpointValueProfileBaseModel):
    investments_to_retain: list[str] = Field(default_factory=list)
    investments_not_converted: list[str] = Field(default_factory=list)
    configurations_not_to_follow: list[str] = Field(default_factory=list)
    missing_competitive_gaps: list[str] = Field(default_factory=list)
    table_stakes_to_maintain: list[str] = Field(default_factory=list)
    current_price_support_cn: str = Field(min_length=1)
    growth_action_cn: str = Field(min_length=1)


class SellpointValueDecisionValueItem(SellpointValueProfileBaseModel):
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = ""
    purchase_reason_code: str | None = None
    purchase_reason_name_cn: str | None = None
    value_bundle_code: str = Field(min_length=1)
    value_bundle_name_cn: str = Field(min_length=1)
    perceived_value_name_cn: str = Field(min_length=1)
    perceived_outcome_cn: str = Field(min_length=1)
    value_status: str = Field(min_length=1)
    capability_codes: list[str] = Field(default_factory=list)
    investment_decisions: list[CapabilityInvestmentDecision] = Field(
        default_factory=list
    )
    question_analyses: list[dict[str, Any]] = Field(default_factory=list)
    price_realization: dict[str, Any] = Field(default_factory=dict)
    volume_realization: dict[str, Any] = Field(default_factory=dict)
    battlefield_allocation: dict[str, Any] | None = None
    increment: dict[str, Any] | None = None
    boundary_cn: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    value_item_hash: str = Field(min_length=1)


class SkuSellpointValueDecisionProfile(SellpointValueProfileBaseModel):
    schema_version: Literal["sku_sellpoint_value_decision_profile_v1"]
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    method_versions: dict[str, str]
    target: SkuIdentity
    analysis_state: Literal["ready", "partial", "blocked"]
    freshness_status: Literal["current", "stale", "unknown"]
    profile_confidence: float = Field(ge=0.0, le=1.0)
    source_lineage: list[ProfileSourceLineage]
    target_market_summary: dict[str, Any]
    candidate_universe: CandidateUniverseManifest
    threshold_config: CapabilityThresholdConfig
    investment_decisions: list[CapabilityInvestmentDecision]
    value_items: list[SellpointValueDecisionValueItem]
    question_analyses: list[dict[str, Any]]
    price_role: dict[str, Any]
    battlefield_options: list[dict[str, Any]]
    pm_decisions: SellpointValueFivePmDecisions
    qa_index: list[ProfileQaTopic]
    evidence_summary: dict[str, Any]
    limitations: list[str]
    review_required: bool
    review_reasons: list[str]
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile_scope(self) -> "SkuSellpointValueDecisionProfile":
        if self.target.product_category != self.category_code:
            raise ValueError("profile target category must match category_code")
        if self.target.sku_code != self.candidate_universe.target_sku_code:
            raise ValueError("profile target must match candidate universe")
        codes = [row.capability_code for row in self.investment_decisions]
        if len(codes) != len(set(codes)):
            raise ValueError("investment decisions must be unique by capability_code")
        if self.analysis_state == "blocked" and not self.review_required:
            raise ValueError("blocked profiles require review")
        if self.review_required and not self.review_reasons:
            raise ValueError("review-required profiles need reasons")
        return self


class SellpointValueMaterializationInput(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    source_batch_scope_id: str | None = None
    profile_version: str = Field(min_length=1)
    target: SkuIdentity
    source_lineage: list[ProfileSourceLineage]
    current_source_hashes: dict[str, list[str]] = Field(default_factory=dict)
    candidate_universe: CandidateUniverseManifest
    threshold_config: CapabilityThresholdConfig
    investment_decisions: list[CapabilityInvestmentDecision]
    v5_report: SkuPerceivedValueMarketRealizationReport
    method_versions: dict[str, str]
    generated_by: str = Field(default="system", min_length=1)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_materialization_scope(self) -> "SellpointValueMaterializationInput":
        if self.target.product_category != self.category_code:
            raise ValueError("target category must match materialization category")
        if self.target.sku_code != self.candidate_universe.target_sku_code:
            raise ValueError("target must match candidate universe")
        if (
            self.candidate_universe.project_id != self.project_id
            or self.candidate_universe.category_code != self.category_code
            or self.candidate_universe.batch_id
            != (self.source_batch_scope_id or self.batch_id)
        ):
            raise ValueError("candidate universe scope must match materialization")
        if self.target.sku_code != self.v5_report.target.sku_code:
            raise ValueError("target must match V5 report")
        if self.threshold_config.category_code != self.category_code:
            raise ValueError("threshold category must match materialization category")
        modules = [row.module_code for row in self.source_lineage]
        if len(modules) != len(set(modules)):
            raise ValueError("source lineage modules must be unique")
        if set(modules) != set(REQUIRED_PROFILE_SOURCE_MODULES):
            raise ValueError("source lineage must cover every required module")
        if not self.method_versions:
            raise ValueError("method versions are required")
        return self


class MaterializedSellpointValueDraft(SellpointValueProfileBaseModel):
    profile: SkuSellpointValueDecisionProfile
    persistence_bundle: SellpointValueDraftBundle

    @model_validator(mode="after")
    def validate_materialized_hashes(self) -> "MaterializedSellpointValueDraft":
        if self.profile.input_fingerprint != self.persistence_bundle.profile.input_fingerprint:
            raise ValueError("profile and persistence input fingerprints must match")
        if self.profile.result_hash != self.persistence_bundle.profile.result_hash:
            raise ValueError("profile and persistence result hashes must match")
        return self


class SellpointValueVersionRequest(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    method_versions: dict[str, str]
    source_scope: dict[str, Any] = Field(default_factory=dict)
    version_input_fingerprint: str = Field(min_length=1)
    candidate_universe_fingerprint: str = Field(min_length=1)
    version_result_hash: str = Field(min_length=1)
    generated_by: str = Field(default="system", min_length=1)


class SkuGenerationStatus(SellpointValueProfileBaseModel):
    sku_code: str = Field(min_length=1)
    status: Literal["generated", "reused", "skipped", "failed"]
    profile_result_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class SellpointValueBatchGenerationResult(SellpointValueProfileBaseModel):
    version: SellpointValueVersionRecord
    requested_sku_count: int = Field(ge=0)
    remaining_sku_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    checkpoint_sku_code: str | None = None
    statuses: list[SkuGenerationStatus]

    @model_validator(mode="after")
    def validate_batch_counts(self) -> "SellpointValueBatchGenerationResult":
        if self.remaining_sku_count > self.requested_sku_count:
            raise ValueError(
                "remaining SKU count cannot exceed requested SKU count"
            )
        if (
            self.generated_count
            + self.reused_count
            + self.skipped_count
            + self.failed_count
            != len(self.statuses)
        ):
            raise ValueError("batch counts must match status rows")
        if (
            self.version.processing_status == "completed"
            and self.remaining_sku_count
        ):
            raise ValueError("completed batches cannot retain unfinished SKUs")
        return self


class SellpointValueProfileDiff(SellpointValueProfileBaseModel):
    sku_code: str = Field(min_length=1)
    from_profile_version: str = Field(min_length=1)
    to_profile_version: str = Field(min_length=1)
    candidate_added: list[str] = Field(default_factory=list)
    candidate_removed: list[str] = Field(default_factory=list)
    candidate_status_changes: list[dict[str, str]] = Field(default_factory=list)
    investment_classification_changes: list[dict[str, str | None]] = Field(
        default_factory=list
    )
    value_item_added: list[str] = Field(default_factory=list)
    value_item_removed: list[str] = Field(default_factory=list)
    price_role_changed: bool = False
    pm_decisions_changed: bool = False
    from_result_hash: str = Field(min_length=1)
    to_result_hash: str = Field(min_length=1)
    diff_hash: str = Field(min_length=1)


class ProfileGenerationReadback(SellpointValueProfileBaseModel):
    profile: SkuSellpointValueDecisionProfile
    persisted: SellpointValueProfileReadBundle


__all__ = [
    "MaterializedSellpointValueDraft",
    "ProfileGenerationReadback",
    "ProfileQaTopic",
    "ProfileSourceLineage",
    "REQUIRED_PROFILE_SOURCE_MODULES",
    "SellpointValueBatchGenerationResult",
    "SellpointValueDecisionValueItem",
    "SellpointValueFivePmDecisions",
    "SellpointValueMaterializationInput",
    "SellpointValueProfileDiff",
    "SellpointValueVersionRequest",
    "SkuGenerationStatus",
    "SkuSellpointValueDecisionProfile",
]
