"""M08.5 business-dimension ontology calibration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.services.core3_real_data.constants import Core3RunStatus


class M085BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


class M085VersionRecord(M085BaseModel):
    ontology_version_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    ontology_version: str
    base_seed_version: str
    base_seed_hash: str
    source_profile_batch_hash: str
    calibration_scope: str = "project_batch"
    status: str
    active_from_run_id: str | None = None
    dimension_count_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    review_status: str = "auto_pass"
    rule_version: str
    seed_version: str
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M085DimensionDefinitionRecord(M085BaseModel):
    dimension_definition_id: str
    ontology_version_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    dimension_type: str
    dimension_code: str
    base_dimension_code: str | None = None
    dimension_name_cn: str
    definition_cn: str
    business_question_cn: str
    include_rule_json: dict[str, Any] = Field(default_factory=dict)
    exclude_rule_json: dict[str, Any] = Field(default_factory=dict)
    required_evidence_json: dict[str, Any] = Field(default_factory=dict)
    optional_evidence_json: dict[str, Any] = Field(default_factory=dict)
    negative_evidence_json: dict[str, Any] = Field(default_factory=dict)
    boundary_policy: str
    allocation_policy: str
    candidate_trigger_policy_json: dict[str, Any] = Field(default_factory=dict)
    profile_eligibility_policy_json: dict[str, Any] = Field(default_factory=dict)
    downstream_policy_json: dict[str, Any] = Field(default_factory=dict)
    distinctiveness_score: Decimal = Decimal("0.0000")
    support_score: Decimal = Decimal("0.0000")
    sku_coverage_count: int = Field(default=0, ge=0)
    strong_sku_coverage_count: int = Field(default=0, ge=0)
    definition_status: str
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str
    seed_version: str
    seed_hash: str
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M085EvidenceAnchorRecord(M085BaseModel):
    dimension_anchor_id: str
    dimension_definition_id: str
    ontology_version_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    anchor_type: str
    anchor_code: str
    anchor_name_cn: str
    anchor_role: str = "optional"
    polarity: str = "positive"
    weight: Decimal = Decimal("0.0000")
    min_sentence_count: int | None = None
    min_sku_count: int | None = None
    min_confidence: Decimal | None = None
    representative_phrase_json: list[Any] = Field(default_factory=list)
    representative_evidence_ids: list[Any] = Field(default_factory=list)
    source_rule_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str
    seed_version: str
    seed_hash: str
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M085MappingRuleRecord(M085BaseModel):
    dimension_mapping_rule_id: str
    ontology_version_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    source_type: str
    source_code: str
    source_name_cn: str | None = None
    target_dimension_type: str
    target_dimension_code: str
    mapping_level: str
    mapping_strength: Decimal = Decimal("0.0000")
    requires_product_anchor: bool = False
    requires_market_anchor: bool = False
    service_guardrail_flag: bool = False
    low_value_guardrail_flag: bool = False
    rule_expr_json: dict[str, Any] = Field(default_factory=dict)
    reason_cn: str
    active: bool = True
    rule_version: str
    seed_version: str
    seed_hash: str
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M085CandidateSnapshotRecord(M085BaseModel):
    candidate_snapshot_id: str
    ontology_version_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    snapshot_type: str
    signal_type: str
    signal_code: str
    signal_name_cn: str
    sentence_count: int = Field(default=0, ge=0)
    sku_count: int = Field(default=0, ge=0)
    strong_sentence_count: int = Field(default=0, ge=0)
    service_sentence_count: int = Field(default=0, ge=0)
    low_value_sentence_count: int = Field(default=0, ge=0)
    avg_signal_score: Decimal = Decimal("0.0000")
    coverage_ratio: Decimal = Decimal("0.0000")
    specificity_score: Decimal = Decimal("0.0000")
    distribution_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[Any] = Field(default_factory=list)
    rule_version: str
    seed_version: str
    seed_hash: str
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


class M085CalibrationIssueRecord(M085BaseModel):
    calibration_issue_id: str
    ontology_version_id: str
    project_id: str
    category_code: str = "TV"
    batch_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    issue_scope: str
    dimension_type: str | None = None
    dimension_code: str | None = None
    source_type: str | None = None
    source_code: str | None = None
    issue_code: str
    severity: str
    issue_message_cn: str
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    suggested_action_cn: str
    review_status: str = "open"
    rule_version: str
    seed_version: str
    seed_hash: str
    input_fingerprint: str
    result_hash: str
    is_current: bool = True


@dataclass(frozen=True)
class M085ServiceResult:
    version: M085VersionRecord
    definitions: tuple[M085DimensionDefinitionRecord, ...]
    anchors: tuple[M085EvidenceAnchorRecord, ...]
    mapping_rules: tuple[M085MappingRuleRecord, ...]
    snapshots: tuple[M085CandidateSnapshotRecord, ...]
    issues: tuple[M085CalibrationIssueRecord, ...]
    summary: dict[str, Any]
    warnings: list[str]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int = 0
