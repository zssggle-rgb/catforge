"""Typed analytical contracts for versioned competitor profiles."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


COMPETITOR_PROFILE_SCHEMA_VERSION = "sku_competitor_decision_profile_v1"
COMPETITOR_PROFILE_RULE_VERSION = "competitor_profile_materializer_v1"
COMPETITOR_PROFILE_METHOD_VERSION = "competitor_profile_method_v1"

FORBIDDEN_FACTORY_EXPORT_KEYS = frozenset(
    {
        "prompt",
        "prompt_template",
        "prompt_templates",
        "gold_set",
        "gold_sets",
        "benchmark_gold",
        "threshold_tuning_samples",
    }
)


class ReleaseStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class ReleaseQualityStatus(str, Enum):
    UNASSESSED = "unassessed"
    READY = "ready"
    LIMITED = "limited"
    BLOCKED = "blocked"


class AnalysisState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class ConclusionState(str, Enum):
    AVAILABLE = "available"
    NO_PRIORITY_COMPETITOR = "no_priority_competitor"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CandidateStatus(str, Enum):
    ELIGIBLE = "eligible"
    LIMITED = "limited"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    RECALLED_ONLY = "recalled_only"
    REFERENCE_ONLY = "reference_only"


class RelationCode(str, Enum):
    DIRECT_SUBSTITUTE = "direct_substitute"
    SAME_BUDGET_ALTERNATIVE = "same_budget_alternative"
    DOWNTRADE_DIVERSION = "downtrade_diversion"
    UPTRADE_ALTERNATIVE = "uptrade_alternative"
    SAME_BRAND_LADDER = "same_brand_ladder"
    SCENARIO_SUBSTITUTE = "scenario_substitute"
    SAME_VALUE_SUBSTITUTE = "same_value_substitute"


class RelationStatus(str, Enum):
    PASSED = "passed"
    LIMITED = "limited"
    UNASSESSABLE = "unassessable"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


class PurchasePoolLevel(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    UNKNOWN = "unknown"


class QuestionAvailability(str, Enum):
    ELIGIBLE = "eligible"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class EvidenceFamily(str, Enum):
    PURCHASE_REASON = "F1_purchase_reason"
    TASK_VALUE_SCENE = "F2_task_value_scene"
    AUDIENCE_NEED = "F3_audience_need"
    USER_REALIZATION = "F4_user_realization"
    CAPABILITY_EXPRESSION = "F5_capability_expression"


class EvidenceFamilyStatus(str, Enum):
    SUPPORTING = "supporting"
    DISCRIMINATIVE = "discriminative"
    GENERIC = "generic"
    MISSING = "missing"
    CONFLICT = "conflict"


class QuestionCode(str, Enum):
    PURCHASE_CHOICE = "purchase_choice"
    PRICE_VOLUME_PRESSURE = "price_volume_pressure"
    VALUE_SUBSTITUTION = "value_substitution"
    CONFIGURATION_FOLLOW = "configuration_follow"
    SAME_BRAND_PORTFOLIO_ROLE = "same_brand_portfolio_role"
    SCENARIO_SOLUTION = "scenario_solution"
    PRICE_LADDER_DEFENSE = "price_ladder_defense"
    KEY_COMPETITOR_SELECTION = "key_competitor_selection"


class ReferencePurpose(str, Enum):
    MARKET_BASELINE_WITHOUT_VALUE = "market_baseline_without_value"
    HIGH_PERFORMANCE_VALUE_BUNDLE = "high_performance_value_bundle"
    LOW_PERFORMANCE_VALUE_BUNDLE = "low_performance_value_bundle"
    PARAMETER_TIER_REFERENCE = "parameter_tier_reference"
    ADJACENT_BATTLEFIELD_REFERENCE = "adjacent_battlefield_reference"
    SAME_VALUE_REALIZATION_REFERENCE = "same_value_realization_reference"
    PRICE_VOLUME_ARCHETYPE_REFERENCE = "price_volume_archetype_reference"


class DecisionTopic(str, Enum):
    PURCHASE_CHOICE = "purchase_choice"
    PRICE_SCALE_PRESSURE = "price_scale_pressure"
    PORTFOLIO_OR_SCENARIO = "portfolio_or_scenario"
    VALUE_ROUTE = "value_route"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


ALL_EVIDENCE_FAMILIES = frozenset(item.value for item in EvidenceFamily)
ALL_RELATION_CODES = frozenset(item.value for item in RelationCode)
ALL_QUESTION_CODES = frozenset(item.value for item in QuestionCode)


class CompetitorProfileBaseModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        use_enum_values=True,
        validate_default=True,
    )

    @model_validator(mode="after")
    def validate_runtime_boundary(self) -> "CompetitorProfileBaseModel":
        _assert_no_factory_only_keys(self)
        return self


class EvidenceRef(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    source_batch_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_file_ids: list[str] = Field(default_factory=list)
    raw_row_ids: list[str] = Field(default_factory=list)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)


class SourceAuthorityRef(CompetitorProfileBaseModel):
    module_code: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    profile_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    release_status: Literal["published", "preview", "unavailable"]
    is_current: bool
    source_batch_ids: list[str] = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_authority_scope(self) -> "SourceAuthorityRef":
        if self.category_code != self.product_category:
            raise ValueError(
                "source authority category and product category must match"
            )
        _assert_sorted_unique(self.source_batch_ids, "source authority batch IDs")
        if self.release_status == "published" and not self.is_current:
            raise ValueError("published source authority must be current")
        if self.release_status == "preview" and self.is_current:
            raise ValueError("preview source authority cannot be current")
        if self.release_status == "unavailable" and self.is_current:
            raise ValueError("unavailable source authority cannot be current")
        return self


class ServingScope(CompetitorProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    analysis_population: str = Field(min_length=1)
    market_window: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    storage_batch_id: str = Field(min_length=1)
    source_batch_ids: list[str] = Field(min_length=1)
    source_authorities: dict[str, SourceAuthorityRef] = Field(min_length=1)
    sku_prefixes: list[str] = Field(min_length=1)
    authoritative_sku_count: int = Field(ge=1)
    authoritative_sku_manifest_hash: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "ServingScope":
        if self.category_code != self.product_category:
            raise ValueError("serving scope category and product category must match")
        _assert_sorted_unique(self.source_batch_ids, "serving scope source batch IDs")
        _assert_sorted_unique(self.sku_prefixes, "serving scope SKU prefixes")
        for module_code, authority in self.source_authorities.items():
            if module_code != authority.module_code:
                raise ValueError("source authority dict key must match module code")
            if authority.project_id != self.project_id:
                raise ValueError("source authority project must match serving scope")
            if authority.category_code != self.category_code:
                raise ValueError("source authority category must match serving scope")
            if not set(authority.source_batch_ids).issubset(self.source_batch_ids):
                raise ValueError(
                    "source authority batches must be inside serving scope"
                )
        return self


class GateResult(CompetitorProfileBaseModel):
    gate_code: str = Field(min_length=1)
    required: bool
    known: bool
    passed: bool | None = None
    reason_code: str = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_known_state(self) -> "GateResult":
        if self.known and self.passed is None:
            raise ValueError("known gates require a boolean result")
        if not self.known and self.passed is not None:
            raise ValueError("unknown gates cannot carry a boolean result")
        return self


class PurchasePoolAssessment(CompetitorProfileBaseModel):
    level: PurchasePoolLevel
    gate_results: list[GateResult] = Field(min_length=1)
    confidence_level: ConfidenceLevel
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pool_level(self) -> "PurchasePoolAssessment":
        codes = [row.gate_code for row in self.gate_results]
        if len(codes) != len(set(codes)):
            raise ValueError("purchase pool gate codes must be unique")
        required = [row for row in self.gate_results if row.required]
        if self.level == PurchasePoolLevel.UNKNOWN.value and all(
            row.known for row in required
        ):
            raise ValueError("unknown purchase pool requires an unknown required gate")
        if self.level != PurchasePoolLevel.UNKNOWN.value and any(
            not row.known for row in required
        ):
            raise ValueError("known purchase pool levels require all required gates")
        return self


class EvidenceFamilyAssessment(CompetitorProfileBaseModel):
    family: EvidenceFamily
    status: EvidenceFamilyStatus
    matched_codes: list[str] = Field(default_factory=list)
    target_strength: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_strength: Decimal | None = Field(default=None, ge=0, le=1)
    direction: Literal[
        "target_stronger",
        "candidate_stronger",
        "parity",
        "different_route",
        "unknown",
    ] = "unknown"
    independent_lineage_keys: list[str] = Field(default_factory=list)
    generic_reason_code: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence_level: ConfidenceLevel

    @model_validator(mode="after")
    def validate_family(self) -> "EvidenceFamilyAssessment":
        _assert_sorted_unique(
            self.independent_lineage_keys,
            "evidence family lineage keys",
        )
        if (
            self.status == EvidenceFamilyStatus.GENERIC.value
            and not self.generic_reason_code
        ):
            raise ValueError("generic evidence families require a reason code")
        if self.status == EvidenceFamilyStatus.MISSING.value and (
            self.matched_codes or self.independent_lineage_keys
        ):
            raise ValueError("missing evidence families cannot carry matches")
        return self


class PairMarketComparison(CompetitorProfileBaseModel):
    source_authority: SourceAuthorityRef
    analysis_population: str = Field(min_length=1)
    market_window: str = Field(min_length=1)
    comparability_status: Literal["comparable", "limited", "unknown"]
    target_weighted_price: Decimal | None = Field(default=None, ge=0)
    candidate_weighted_price: Decimal | None = Field(default=None, ge=0)
    price_gap: Decimal | None = None
    price_gap_pct: Decimal | None = None
    target_avg_weekly_volume: Decimal | None = Field(default=None, ge=0)
    candidate_avg_weekly_volume: Decimal | None = Field(default=None, ge=0)
    weekly_volume_gap: Decimal | None = None
    weekly_volume_ratio: Decimal | None = Field(default=None, ge=0)
    target_price_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_price_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    target_volume_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    candidate_volume_percentile: Decimal | None = Field(default=None, ge=0, le=1)
    target_total_sales: Decimal | None = Field(default=None, ge=0)
    candidate_total_sales: Decimal | None = Field(default=None, ge=0)
    target_sales_amount: Decimal | None = Field(default=None, ge=0)
    candidate_sales_amount: Decimal | None = Field(default=None, ge=0)
    common_week_count: int | None = Field(default=None, ge=0)
    common_platform_count: int | None = Field(default=None, ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    unknown_reasons: list[str] = Field(default_factory=list)
    causal_claim: Literal[False] = False
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_derived_values(self) -> "PairMarketComparison":
        if (
            self.target_weighted_price in {None, Decimal("0")}
            and self.price_gap_pct is not None
        ):
            raise ValueError("price gap pct requires a non-zero target price")
        if (
            self.target_avg_weekly_volume in {None, Decimal("0")}
            and self.weekly_volume_ratio is not None
        ):
            raise ValueError("weekly volume ratio requires a non-zero target volume")
        if self.comparability_status == "unknown" and not self.unknown_reasons:
            raise ValueError("unknown market comparability requires a reason")
        return self


class RelationAssessment(CompetitorProfileBaseModel):
    relation_code: RelationCode
    status: RelationStatus
    is_primary: bool = False
    confidence_level: ConfidenceLevel
    gate_results: list[GateResult] = Field(min_length=1)
    supporting_evidence_families: list[EvidenceFamily] = Field(default_factory=list)
    business_effect: dict[str, Any] = Field(default_factory=dict)
    eligible_question_codes: list[QuestionCode] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relation_state(self) -> "RelationAssessment":
        if (
            self.status
            in {
                RelationStatus.PASSED.value,
                RelationStatus.LIMITED.value,
            }
            and not self.eligible_question_codes
        ):
            raise ValueError("passed or limited relations require an eligible question")
        if (
            self.status
            in {
                RelationStatus.FAILED.value,
                RelationStatus.UNASSESSABLE.value,
                RelationStatus.REVIEW_REQUIRED.value,
            }
            and not self.reason_codes
        ):
            raise ValueError("non-driving relations require a reason code")
        if self.is_primary and self.status not in {
            RelationStatus.PASSED.value,
            RelationStatus.LIMITED.value,
        }:
            raise ValueError("only passed or limited relations can be primary")
        return self


class QuestionEligibility(CompetitorProfileBaseModel):
    question_code: QuestionCode
    availability: QuestionAvailability
    usable_relation_codes: list[RelationCode] = Field(default_factory=list)
    required_evidence_families: list[EvidenceFamily] = Field(default_factory=list)
    available_evidence_families: list[EvidenceFamily] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    business_boundary_code: str = Field(min_length=1)
    reason_cn: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_question_state(self) -> "QuestionEligibility":
        available = set(self.available_evidence_families)
        if not available.issubset(set(self.required_evidence_families)):
            raise ValueError("available evidence must be a subset of required evidence")
        if (
            self.availability == QuestionAvailability.ELIGIBLE.value
            and self.missing_inputs
        ):
            raise ValueError("eligible questions cannot have missing inputs")
        if self.availability == QuestionAvailability.UNAVAILABLE.value and not (
            self.missing_inputs or self.business_boundary_code
        ):
            raise ValueError("unavailable questions require a boundary")
        return self


class CandidateIdentity(CompetitorProfileBaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]


class CompetitorPairDraft(CompetitorProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    candidate: CandidateIdentity
    recall_sources: list[str] = Field(min_length=1)
    recall_facts: dict[str, Any] = Field(default_factory=dict)
    manifest_order_key: str = Field(min_length=1)
    competitor_member: bool
    reference_member: bool
    candidate_status: CandidateStatus
    purchase_pool: PurchasePoolAssessment
    evidence_family_assessments: list[EvidenceFamilyAssessment]
    market_comparison: PairMarketComparison
    relation_assessments: list[RelationAssessment]
    question_eligibility: list[QuestionEligibility]
    reference_purposes: list[ReferencePurpose] = Field(default_factory=list)
    selected: bool = False
    non_selection_reason_code: str | None = None
    non_selection_reason_cn: str | None = None
    confidence_level: ConfidenceLevel
    confidence: Decimal = Field(ge=0, le=1)
    review_required: bool = False
    review_status: str = Field(default="auto_pass", min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair(self) -> "CompetitorPairDraft":
        if self.category_code != self.candidate.product_category:
            raise ValueError("candidate product category must match pair category")
        if self.target_sku_code == self.candidate.sku_code:
            raise ValueError("target and candidate SKUs must differ")
        if not (self.competitor_member or self.reference_member) and (
            self.candidate_status
            not in {
                CandidateStatus.RECALLED_ONLY.value,
                CandidateStatus.REVIEW_REQUIRED.value,
                CandidateStatus.BLOCKED.value,
            }
        ):
            raise ValueError(
                "pair requires competitor or reference membership unless recalled, review, or blocked"
            )
        _assert_sorted_unique(self.recall_sources, "recall sources")
        _assert_enum_coverage(
            self.evidence_family_assessments,
            "family",
            ALL_EVIDENCE_FAMILIES,
            "evidence families",
        )
        _assert_enum_coverage(
            self.relation_assessments,
            "relation_code",
            ALL_RELATION_CODES,
            "relations",
        )
        _assert_enum_coverage(
            self.question_eligibility,
            "question_code",
            ALL_QUESTION_CODES,
            "questions",
        )
        primary = [row for row in self.relation_assessments if row.is_primary]
        if len(primary) > 1:
            raise ValueError("pair can have at most one primary relation")
        if (
            self.competitor_member
            and self.candidate_status
            in {
                CandidateStatus.ELIGIBLE.value,
                CandidateStatus.LIMITED.value,
            }
            and not primary
        ):
            raise ValueError("eligible competitor pairs require a primary relation")
        non_driving = {
            CandidateStatus.REVIEW_REQUIRED.value,
            CandidateStatus.BLOCKED.value,
            CandidateStatus.RECALLED_ONLY.value,
            CandidateStatus.REFERENCE_ONLY.value,
        }
        if self.selected and self.candidate_status not in {
            CandidateStatus.ELIGIBLE.value,
            CandidateStatus.LIMITED.value,
        }:
            raise ValueError("only eligible or limited candidates can be selected")
        if self.selected:
            by_question = {
                row.question_code: row.availability for row in self.question_eligibility
            }
            if by_question[QuestionCode.KEY_COMPETITOR_SELECTION.value] != (
                QuestionAvailability.ELIGIBLE.value
            ):
                raise ValueError(
                    "selected candidates require key-selection eligibility"
                )
        if self.candidate_status in non_driving and self.selected:
            raise ValueError("non-driving candidates cannot be selected")
        formal_competitor_statuses = {
            CandidateStatus.ELIGIBLE.value,
            CandidateStatus.LIMITED.value,
        }
        if self.competitor_member != (
            self.candidate_status in formal_competitor_statuses
        ):
            raise ValueError(
                "competitor membership requires eligible or limited status"
            )
        if self.candidate_status == CandidateStatus.REFERENCE_ONLY.value and (
            not self.reference_member or self.competitor_member
        ):
            raise ValueError(
                "reference_only status requires exclusive reference membership"
            )
        if self.reference_member and not self.reference_purposes:
            raise ValueError("reference memberships require a reference purpose")
        if self.review_required and self.review_status == "auto_pass":
            raise ValueError("review-required pairs cannot auto-pass")
        if (
            self.competitor_member
            and self.confidence_level
            in {
                ConfidenceLevel.LOW.value,
                ConfidenceLevel.UNKNOWN.value,
            }
            and not self.review_required
        ):
            raise ValueError("low-confidence competitor pairs require review")
        if (
            self.candidate_status
            in {
                CandidateStatus.REVIEW_REQUIRED.value,
                CandidateStatus.BLOCKED.value,
            }
            and not self.review_required
        ):
            raise ValueError("review or blocked candidate status requires review")
        if (
            not self.selected
            and self.competitor_member
            and not self.non_selection_reason_code
        ):
            raise ValueError("unselected competitors require a non-selection reason")
        return self


class KeyCompetitorSelectionDraft(CompetitorProfileBaseModel):
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    selection_rank: int = Field(ge=1, le=3)
    primary_decision_topic: DecisionTopic
    covered_decision_topics: list[DecisionTopic] = Field(min_length=1)
    primary_relation_code: RelationCode
    auxiliary_relation_codes: list[RelationCode] = Field(default_factory=list)
    selection_reason_cn: str = Field(min_length=1)
    independent_information_reason_cn: str = Field(min_length=1)
    price_value_pressure_summary: dict[str, Any] = Field(default_factory=dict)
    confidence_level: ConfidenceLevel
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection(self) -> "KeyCompetitorSelectionDraft":
        if self.primary_decision_topic not in self.covered_decision_topics:
            raise ValueError("covered topics must include the primary topic")
        if self.primary_relation_code in self.auxiliary_relation_codes:
            raise ValueError("primary relation cannot be repeated as auxiliary")
        return self


class KeyCompetitorSummary(CompetitorProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    display_name_cn: str = Field(min_length=1)
    selection_rank: int = Field(ge=1, le=3)
    primary_decision_topic: DecisionTopic
    primary_relation_code: RelationCode
    conclusion_cn: str = Field(min_length=1)


class SkuCompetitorDecisionProfileDraft(CompetitorProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    display_name_cn: str = Field(min_length=1)
    target_market_summary: dict[str, Any] = Field(default_factory=dict)
    analysis_state: AnalysisState
    conclusion_state: ConclusionState
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    profile_confidence: Decimal = Field(ge=0, le=1)
    candidate_status_counts: dict[str, int] = Field(default_factory=dict)
    relation_status_counts: dict[str, int] = Field(default_factory=dict)
    key_competitor_summary: list[KeyCompetitorSummary] = Field(default_factory=list)
    competitive_advantages: list[dict[str, Any]] = Field(default_factory=list)
    substitutable_values: list[dict[str, Any]] = Field(default_factory=list)
    price_scale_pressures: list[dict[str, Any]] = Field(default_factory=list)
    same_brand_findings: list[dict[str, Any]] = Field(default_factory=list)
    configuration_decisions: list[dict[str, Any]] = Field(default_factory=list)
    no_conclusion_reason: dict[str, Any] = Field(default_factory=dict)
    source_lineage: list[dict[str, Any]] = Field(default_factory=list)
    qa_index: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False
    review_status: str = Field(default="auto_pass", min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> "SkuCompetitorDecisionProfileDraft":
        if self.conclusion_state == ConclusionState.NO_PRIORITY_COMPETITOR.value and (
            self.analysis_state != AnalysisState.READY.value
        ):
            raise ValueError("no_priority_competitor requires a ready analysis")
        if self.conclusion_state == ConclusionState.INSUFFICIENT_EVIDENCE.value and (
            self.analysis_state == AnalysisState.READY.value
        ):
            raise ValueError(
                "insufficient_evidence requires partial or blocked analysis"
            )
        if len(self.key_competitor_summary) > 3:
            raise ValueError("profile can expose at most three key competitors")
        ranks = [row.selection_rank for row in self.key_competitor_summary]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("key competitor summary ranks must be contiguous")
        codes = [row.candidate_sku_code for row in self.key_competitor_summary]
        if len(codes) != len(set(codes)):
            raise ValueError("key competitor summary candidates must be unique")
        if self.conclusion_state == ConclusionState.AVAILABLE.value and not (
            self.key_competitor_summary
            or self.competitive_advantages
            or self.substitutable_values
            or self.price_scale_pressures
            or self.same_brand_findings
            or self.configuration_decisions
        ):
            raise ValueError(
                "available profiles require at least one business conclusion"
            )
        if self.conclusion_state == ConclusionState.INSUFFICIENT_EVIDENCE.value and (
            not self.no_conclusion_reason
        ):
            raise ValueError("insufficient profiles require a no-conclusion reason")
        if (
            self.analysis_state == AnalysisState.BLOCKED.value
            and not self.review_required
        ):
            raise ValueError("blocked profiles require review")
        if self.review_required and self.review_status == "auto_pass":
            raise ValueError("review-required profiles cannot auto-pass")
        if self.profile_confidence < Decimal("0.6000") and not self.review_required:
            raise ValueError("low-confidence profiles require review")
        if any(value < 0 for value in self.candidate_status_counts.values()):
            raise ValueError("candidate status counts cannot be negative")
        if any(value < 0 for value in self.relation_status_counts.values()):
            raise ValueError("relation status counts cannot be negative")
        return self


class CompetitorProfileDraftBundle(CompetitorProfileBaseModel):
    profile: SkuCompetitorDecisionProfileDraft
    pairs: list[CompetitorPairDraft]
    selections: list[KeyCompetitorSelectionDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bundle(self) -> "CompetitorProfileDraftBundle":
        pair_codes = [row.candidate.sku_code for row in self.pairs]
        if len(pair_codes) != len(set(pair_codes)):
            raise ValueError("pair candidates must be unique")
        for pair in self.pairs:
            if pair.project_id != self.profile.project_id:
                raise ValueError("pair project must match profile")
            if pair.category_code != self.profile.category_code:
                raise ValueError("pair category must match profile")
            if pair.target_sku_code != self.profile.target_sku_code:
                raise ValueError("pair target must match profile")
        if len(self.selections) > 3:
            raise ValueError("bundle can contain at most three selections")
        ranks = [row.selection_rank for row in self.selections]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("selection ranks must be contiguous and ordered")
        selection_codes = [row.candidate_sku_code for row in self.selections]
        if len(selection_codes) != len(set(selection_codes)):
            raise ValueError("selected candidates must be unique")
        pair_by_code = {row.candidate.sku_code: row for row in self.pairs}
        for selection in self.selections:
            pair = pair_by_code.get(selection.candidate_sku_code)
            if pair is None or not pair.selected:
                raise ValueError("selection must reference a selected pair")
            if selection.target_sku_code != self.profile.target_sku_code:
                raise ValueError("selection target must match profile")
        selected_pair_codes = {
            row.candidate.sku_code for row in self.pairs if row.selected
        }
        if selected_pair_codes != set(selection_codes):
            raise ValueError("selected pair flags must match selection rows")
        summary_codes = {
            row.candidate_sku_code for row in self.profile.key_competitor_summary
        }
        if summary_codes != set(selection_codes):
            raise ValueError("profile key summary must match selections")
        return self


def _assert_no_factory_only_keys(value: Any) -> None:
    if isinstance(value, BaseModel):
        _assert_model_has_no_factory_only_fields(value)
        for field_name in type(value).model_fields:
            child = getattr(value, field_name)
            if isinstance(child, CompetitorProfileBaseModel):
                _assert_model_has_no_factory_only_fields(child)
                continue
            if isinstance(child, BaseModel) or (
                isinstance(child, (dict, list, tuple)) and child
            ):
                _assert_no_factory_only_keys(child)
    elif isinstance(value, dict):
        forbidden = FORBIDDEN_FACTORY_EXPORT_KEYS.intersection(value)
        if forbidden:
            raise ValueError(
                "factory-only keys are forbidden in competitor profile contracts: "
                + ", ".join(sorted(forbidden))
            )
        for child in value.values():
            if isinstance(child, CompetitorProfileBaseModel):
                _assert_model_has_no_factory_only_fields(child)
                continue
            if isinstance(child, BaseModel) or (
                isinstance(child, (dict, list, tuple)) and child
            ):
                _assert_no_factory_only_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            if isinstance(child, CompetitorProfileBaseModel):
                _assert_model_has_no_factory_only_fields(child)
                continue
            if isinstance(child, BaseModel) or (
                isinstance(child, (dict, list, tuple)) and child
            ):
                _assert_no_factory_only_keys(child)


def _assert_model_has_no_factory_only_fields(value: BaseModel) -> None:
    forbidden = FORBIDDEN_FACTORY_EXPORT_KEYS.intersection(type(value).model_fields)
    if forbidden:
        raise ValueError(
            "factory-only keys are forbidden in competitor profile contracts: "
            + ", ".join(sorted(forbidden))
        )


def _assert_sorted_unique(values: list[str], label: str) -> None:
    if values != sorted(set(values)):
        raise ValueError(f"{label} must be sorted and unique")


def _assert_enum_coverage(
    rows: list[CompetitorProfileBaseModel],
    field_name: str,
    expected: frozenset[str],
    label: str,
) -> None:
    actual = [str(getattr(row, field_name)) for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError(f"pair must contain exactly one assessment for all {label}")


__all__ = [
    "ALL_EVIDENCE_FAMILIES",
    "ALL_QUESTION_CODES",
    "ALL_RELATION_CODES",
    "AnalysisState",
    "CandidateIdentity",
    "CandidateStatus",
    "COMPETITOR_PROFILE_METHOD_VERSION",
    "COMPETITOR_PROFILE_RULE_VERSION",
    "COMPETITOR_PROFILE_SCHEMA_VERSION",
    "CompetitorPairDraft",
    "CompetitorProfileDraftBundle",
    "ConclusionState",
    "ConfidenceLevel",
    "DecisionTopic",
    "EvidenceFamily",
    "EvidenceFamilyAssessment",
    "EvidenceFamilyStatus",
    "EvidenceRef",
    "FreshnessStatus",
    "GateResult",
    "KeyCompetitorSelectionDraft",
    "KeyCompetitorSummary",
    "PairMarketComparison",
    "PurchasePoolAssessment",
    "PurchasePoolLevel",
    "QuestionAvailability",
    "QuestionCode",
    "QuestionEligibility",
    "ReferencePurpose",
    "RelationAssessment",
    "RelationCode",
    "RelationStatus",
    "ReleaseQualityStatus",
    "ReleaseStatus",
    "ServingScope",
    "SkuCompetitorDecisionProfileDraft",
    "SourceAuthorityRef",
]
