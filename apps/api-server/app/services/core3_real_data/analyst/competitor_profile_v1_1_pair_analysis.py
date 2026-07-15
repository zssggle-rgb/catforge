"""Calculate and assemble lossless V1.1 target×candidate analysis components.

The calculator calls the frozen mature value-anchor and pressure algorithms.  The
assembler only projects already calculated results into typed V1.1 contracts; it
does not classify scope, evaluate formal relations, assign roles, rank candidates,
or persist data.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.anchor_substitutability import (
    VALUE_ANCHOR_MATCHER_CONFIG_VERSION,
    VALUE_ANCHOR_MATCHER_METHOD_VERSION,
    AnchorSubstitutabilityResult,
    ValueAnchorMatcher,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    RecalledCandidate,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairAlignedFeature,
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticPairAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import EvidenceRef
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    PRIMARY_DIMENSION_WEIGHTS,
    AnalysisItem,
    CalculationComponent,
    ConclusionMetric,
    DimensionAnalysisResult,
    DimensionScore,
    LegacyScoreBasis,
    MachineReadableConclusion,
    MarketValidationAnalysisResult,
    PairAnalysisSourceLineage,
    PairDimensionSet,
    PurchasePoolAnalysis,
    PurchasePoolGateFact,
    PurchasePressureComparisonResult,
    ReplacementPressureAnalysisResult,
    ReviewItem,
    SalesOverlapSnapshot,
    ValueAnchorAnalysisResult,
    ValueAnchorMatchDetail,
    VersionSkuAnalysisSnapshot,
    CompetitorProfileV11BaseModel,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionEvidencePair,
)
from app.services.core3_real_data.analyst.purchase_pressure_comparison import (
    PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION,
    PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION,
    PurchasePressureComparator,
    PurchasePressureComparisonResult as MaturePurchasePressureResult,
)
from app.services.core3_real_data.analyst.replacement_pressure import (
    REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION,
    REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION,
    ReplacementPressureClassifier,
    ReplacementPressureInput,
    ReplacementPressureResult,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.purchase_reason_profile_contract import (
    derive_consumption_capabilities,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamAnchorContract,
    M12DDownstreamProfileContract,
    M12DDownstreamReadContract,
)


PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION = "competitor_profile_pair_calculator_v1_1"
PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION = "competitor_profile_pair_assembler_v1_1"
LEGACY_WEIGHTED_OVERLAP_CONFIG_VERSION = "legacy_weighted_role_overlap_v1"
SUPPORTING_DIMENSION_WEIGHT = Decimal("0.10")

_DIMENSION_MODULES: dict[str, tuple[str, ...]] = {
    "battlefield_overlap": ("M11C", "M11D"),
    "user_task_overlap": ("M09C",),
    "target_group_overlap": ("M10C",),
    "parameter_comparison": ("M03B",),
    "claim_comparison": ("M04C", "M05C"),
    "user_realization_comparison": ("M05C",),
    "purchase_reason_comparison": ("M12D",),
}
_DIMENSION_WEIGHTS = {
    "battlefield_overlap": PRIMARY_DIMENSION_WEIGHTS["battlefield_overlap"],
    "user_task_overlap": PRIMARY_DIMENSION_WEIGHTS["user_task_overlap"],
    "target_group_overlap": PRIMARY_DIMENSION_WEIGHTS["target_group_overlap"],
    "parameter_comparison": SUPPORTING_DIMENSION_WEIGHT,
    "claim_comparison": SUPPORTING_DIMENSION_WEIGHT,
    "user_realization_comparison": SUPPORTING_DIMENSION_WEIGHT,
    "purchase_reason_comparison": SUPPORTING_DIMENSION_WEIGHT,
}
_ROLE_WEIGHTS = {
    "primary": Decimal("1.00"),
    "secondary": Decimal("0.75"),
    "user_observed": Decimal("0.45"),
    "comment_observed": Decimal("0.45"),
    "opportunity": Decimal("0.35"),
    "latent": Decimal("0.35"),
    "brand_claimed": Decimal("0.25"),
    "drag": Decimal("-0.30"),
    "drag_factor": Decimal("-0.30"),
    "unmet_need": Decimal("-0.30"),
}
_POOL_SCORES = {
    "P0": Decimal("1.00"),
    "P1": Decimal("0.85"),
    "P2": Decimal("0.70"),
    "P3": Decimal("0.55"),
}
_M12D_ROLE_VALUES = {
    "core_payment",
    "supporting",
    "weak_expression",
    "risk_drag",
}
_M12D_STATUS_VALUES = {
    "ready",
    "ready_limited",
    "ready_degraded",
    "weak_expression_only",
    "missing_input",
    "review_required",
    "failed",
}


class PairAnalysisInputError(RuntimeError):
    """Raised when pair stages or shared snapshots do not form one hash chain."""


@dataclass(frozen=True)
class PairAnalysisCalculatorInput:
    competitor_profile_version_id: str
    pair_feature: PairFeatureRecord
    purchase_pool: PurchasePoolSemanticPairAssessment
    value_substitution: ValueSubstitutionEvidencePair
    price_volume_pressure: PriceVolumePressureAssessment
    target_snapshot: VersionSkuAnalysisSnapshot
    candidate_snapshot: VersionSkuAnalysisSnapshot
    recalled_candidate: RecalledCandidate
    recall_rank: int
    legacy_basis: LegacyScoreBasis | None = None


@dataclass(frozen=True)
class DimensionCalculation:
    dimension_code: str
    availability: str
    raw_score: Decimal | None
    positive_intersection: Decimal | None
    positive_union: Decimal | None
    risk_overlap: Decimal | None
    target_only_count: int
    candidate_only_count: int


@dataclass(frozen=True)
class _PairAnalysisCoreCalculation:
    source: PairAnalysisCalculatorInput
    target_m12d_contract: M12DDownstreamReadContract
    candidate_m12d_contract: M12DDownstreamReadContract
    dimension_calculations: Mapping[str, DimensionCalculation]
    value_anchor_result: AnchorSubstitutabilityResult
    replacement_pressure_result: ReplacementPressureResult
    purchase_pressure_result: MaturePurchasePressureResult
    purchase_pool_score: Decimal | None
    calculator_versions: Mapping[str, str]
    input_fingerprint: str


@dataclass(frozen=True)
class PairAnalysisCalculation(_PairAnalysisCoreCalculation):
    """Complete calculated pair result consumed losslessly by the assembler."""

    purchase_pool_analysis: PurchasePoolAnalysis
    dimensions: PairDimensionSet
    value_anchor_analysis: ValueAnchorAnalysisResult
    replacement_pressure_analysis: ReplacementPressureAnalysisResult
    purchase_pressure_analysis: PurchasePressureComparisonResult
    market_validation: MarketValidationAnalysisResult
    legacy_basis: LegacyScoreBasis
    calculation_result_hash: str


class PairAnalysisAssembly(CompetitorProfileV11BaseModel):
    """Typed G33 output consumed by G34/G35 before final pair materialization."""

    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    competitor_profile_version_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    target_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    recall_sources: list[str] = Field(min_length=1)
    recall_facts: list[dict[str, Any]] = Field(min_length=1)
    recall_rank: int = Field(ge=1)
    purchase_pool: PurchasePoolAnalysis
    dimensions: PairDimensionSet
    value_anchor_analysis: ValueAnchorAnalysisResult
    replacement_pressure_analysis: ReplacementPressureAnalysisResult
    purchase_pressure_comparison: PurchasePressureComparisonResult
    market_validation: MarketValidationAnalysisResult
    aligned_features: list[dict[str, Any]]
    purchase_reason_assessments: list[dict[str, Any]]
    value_assessments: list[dict[str, Any]]
    price_volume_process: dict[str, Any]
    legacy_basis: LegacyScoreBasis
    source_lineage: PairAnalysisSourceLineage
    evidence_refs: list[EvidenceRef]
    limitations: list[str] = Field(default_factory=list)
    calculator_versions: dict[str, str]
    audit_summary_cn: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    calculation_result_hash: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assembly(self) -> "PairAnalysisAssembly":
        if self.target_sku_code == self.candidate_sku_code:
            raise ValueError("G33 analysis assembly cannot contain a self pair")
        if self.recall_sources != sorted(set(self.recall_sources)):
            raise ValueError("assembly recall sources must be sorted and unique")
        feature_keys = [
            (
                str(row.get("feature_group") or ""),
                str(row.get("module_code") or ""),
                str(row.get("feature_code") or ""),
            )
            for row in self.aligned_features
        ]
        if feature_keys != sorted(set(feature_keys)):
            raise ValueError("assembly aligned features must remain sorted and unique")
        expected_versions = _calculator_versions()
        if self.calculator_versions != expected_versions:
            raise ValueError("assembly must freeze every mature calculator version")
        _assert_evidence_order(self.evidence_refs)
        if self.source_lineage.evidence_refs != self.evidence_refs:
            raise ValueError("assembly and source-lineage evidence closure must match")
        evidence_keys = {_evidence_key(row) for row in self.evidence_refs}
        missing_keys = {
            _evidence_key(row)
            for row in _assembly_child_evidence(self)
            if _evidence_key(row) not in evidence_keys
        }
        if missing_keys:
            raise ValueError("assembly evidence closure is missing child evidence refs")
        if self.limitations != sorted(set(self.limitations)):
            raise ValueError("assembly limitations must be sorted and unique")
        return self


class PairAnalysisCalculator:
    """Run mature pair algorithms over one frozen pair and two shared snapshots."""

    def __init__(
        self,
        *,
        value_anchor_matcher: ValueAnchorMatcher | None = None,
        replacement_pressure_classifier: ReplacementPressureClassifier | None = None,
        purchase_pressure_comparator: PurchasePressureComparator | None = None,
    ) -> None:
        self._value_anchor_matcher = value_anchor_matcher or ValueAnchorMatcher()
        self._replacement_pressure_classifier = (
            replacement_pressure_classifier or ReplacementPressureClassifier()
        )
        self._purchase_pressure_comparator = (
            purchase_pressure_comparator or PurchasePressureComparator()
        )

    def calculate(
        self,
        source: PairAnalysisCalculatorInput,
    ) -> PairAnalysisCalculation:
        _validate_source(source)
        target_contract = _m12d_contract(source.target_snapshot)
        candidate_contract = _m12d_contract(source.candidate_snapshot)
        dimension_calculations = _dimension_calculations(
            source.target_snapshot,
            source.candidate_snapshot,
        )
        anchor = self._value_anchor_matcher.match(
            target_contract=target_contract,
            candidate_contract=candidate_contract,
        )
        purchase_pressure = self._purchase_pressure_comparator.compare(
            target_contract=target_contract,
            candidate_contract=candidate_contract,
        )
        pool_score = _POOL_SCORES.get(source.purchase_pool.purchase_pool.level)
        semantic_scores = {
            key: dimension_calculations[dimension].raw_score
            for key, dimension in (
                ("battlefield", "battlefield_overlap"),
                ("user_task", "user_task_overlap"),
                ("target_group", "target_group_overlap"),
            )
        }
        replacement = self._replacement_pressure_classifier.classify(
            ReplacementPressureInput(
                purchase_pool_level=source.purchase_pool.purchase_pool.level,
                purchase_pool_score=pool_score,
                anchor_substitutability=anchor,
                price_gap_pct_to_target=source.price_volume_pressure.price_gap_pct,
                weighted_overlap=semantic_scores,
                market_validation_level=_market_level(source.price_volume_pressure),
                candidate_config_advantage_score=_candidate_value_advantage(
                    source.value_substitution
                ),
                candidate_scenario_mindshare_score=_candidate_scenario_advantage(
                    dimension_calculations
                ),
                risk_flags=_replacement_risk_flags(source),
            )
        )
        versions = _calculator_versions()
        input_fingerprint = stable_hash(
            {
                "method_version": PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
                "competitor_profile_version_id": source.competitor_profile_version_id,
                "pair_feature_result_hash": source.pair_feature.result_hash,
                "purchase_pool_result_hash": source.purchase_pool.result_hash,
                "value_substitution_result_hash": source.value_substitution.result_hash,
                "price_volume_result_hash": source.price_volume_pressure.result_hash,
                "target_snapshot_result_hash": source.target_snapshot.result_hash,
                "candidate_snapshot_result_hash": source.candidate_snapshot.result_hash,
                "recalled_candidate_result_hash": source.recalled_candidate.result_hash,
                "recall_rank": source.recall_rank,
                "legacy_basis": (
                    source.legacy_basis.model_dump(mode="json")
                    if source.legacy_basis is not None
                    else None
                ),
                "calculator_versions": versions,
            },
            version=PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
        )
        core = _PairAnalysisCoreCalculation(
            source=source,
            target_m12d_contract=target_contract,
            candidate_m12d_contract=candidate_contract,
            dimension_calculations=dimension_calculations,
            value_anchor_result=anchor,
            replacement_pressure_result=replacement,
            purchase_pressure_result=purchase_pressure,
            purchase_pool_score=pool_score,
            calculator_versions=versions,
            input_fingerprint=input_fingerprint,
        )
        subject = _subject(source)
        purchase_pressure_analysis = _purchase_pressure_analysis(core, subject)
        dimensions = _dimension_set(core, subject)
        purchase_pool_analysis = _purchase_pool_analysis(core, subject)
        value_anchor_analysis = _value_anchor_analysis(
            core,
            purchase_pressure_analysis,
            subject,
        )
        replacement_pressure_analysis = _replacement_pressure_analysis(core, subject)
        market_validation = _market_validation(core, subject)
        legacy_basis = source.legacy_basis or _reconstructed_legacy_basis(
            core,
            purchase_pool_analysis,
            dimensions,
            value_anchor_analysis,
            replacement_pressure_analysis,
        )
        calculation_result_hash = _calculation_result_hash(
            input_fingerprint=input_fingerprint,
            purchase_pool=purchase_pool_analysis,
            dimensions=dimensions,
            value_anchor=value_anchor_analysis,
            replacement_pressure=replacement_pressure_analysis,
            purchase_pressure=purchase_pressure_analysis,
            market_validation=market_validation,
            legacy_basis=legacy_basis,
            calculator_versions=versions,
        )
        return PairAnalysisCalculation(
            **vars(core),
            purchase_pool_analysis=purchase_pool_analysis,
            dimensions=dimensions,
            value_anchor_analysis=value_anchor_analysis,
            replacement_pressure_analysis=replacement_pressure_analysis,
            purchase_pressure_analysis=purchase_pressure_analysis,
            market_validation=market_validation,
            legacy_basis=legacy_basis,
            calculation_result_hash=calculation_result_hash,
        )


class PairAnalysisAssembler:
    """Project a calculation into typed G33 data without calling calculators."""

    def assemble(self, calculation: PairAnalysisCalculation) -> PairAnalysisAssembly:
        expected_calculation_hash = _calculation_result_hash(
            input_fingerprint=calculation.input_fingerprint,
            purchase_pool=calculation.purchase_pool_analysis,
            dimensions=calculation.dimensions,
            value_anchor=calculation.value_anchor_analysis,
            replacement_pressure=calculation.replacement_pressure_analysis,
            purchase_pressure=calculation.purchase_pressure_analysis,
            market_validation=calculation.market_validation,
            legacy_basis=calculation.legacy_basis,
            calculator_versions=calculation.calculator_versions,
        )
        if calculation.calculation_result_hash != expected_calculation_hash:
            raise PairAnalysisInputError(
                "pair calculation result hash does not close before assembly"
            )
        source = calculation.source
        purchase_pressure = calculation.purchase_pressure_analysis
        dimensions = calculation.dimensions
        purchase_pool = calculation.purchase_pool_analysis
        value_anchor = calculation.value_anchor_analysis
        replacement = calculation.replacement_pressure_analysis
        market = calculation.market_validation
        evidence_refs = _dedupe_evidence(
            [
                *source.recalled_candidate.evidence_refs,
                *(
                    ref
                    for fact in source.recalled_candidate.recall_facts
                    for ref in (
                        *fact.target_evidence_refs,
                        *fact.candidate_evidence_refs,
                    )
                ),
                *source.pair_feature.evidence_refs,
                *source.purchase_pool.evidence_refs,
                *source.value_substitution.evidence_refs,
                *source.price_volume_pressure.evidence_refs,
                *source.target_snapshot.evidence_refs,
                *source.candidate_snapshot.evidence_refs,
                *(
                    ref
                    for gate in purchase_pool.gate_facts
                    for ref in gate.evidence_refs
                ),
                *(
                    ref
                    for key in _DIMENSION_MODULES
                    for ref in getattr(dimensions, key).evidence_refs
                ),
                *value_anchor.evidence_refs,
                *replacement.evidence_refs,
                *purchase_pressure.evidence_refs,
                *market.evidence_refs,
            ]
        )
        lineage = _pair_lineage(calculation, evidence_refs)
        legacy_basis = calculation.legacy_basis
        limitations = sorted(
            {
                *source.pair_feature.unknown_reason_codes,
                *source.pair_feature.review_reason_codes,
                *source.pair_feature.lineage_conflict_reason_codes,
                *source.purchase_pool.limitations,
                *source.value_substitution.limitations,
                *source.price_volume_pressure.limitations,
                *source.target_snapshot.limitations,
                *source.candidate_snapshot.limitations,
                *value_anchor.limitations,
                *replacement.limitations,
                *purchase_pressure.limitations,
                *market.limitations,
            }
        )
        payload: dict[str, Any] = {
            "project_id": source.target_snapshot.project_id,
            "category_code": source.target_snapshot.category_code,
            "competitor_profile_version_id": source.competitor_profile_version_id,
            "release_scope_key": source.target_snapshot.release_scope_key,
            "target_sku_code": source.target_snapshot.identity_market.sku_code,
            "candidate_sku_code": source.candidate_snapshot.identity_market.sku_code,
            "target_snapshot_ref": source.target_snapshot.snapshot_ref,
            "candidate_snapshot_ref": source.candidate_snapshot.snapshot_ref,
            "recall_sources": sorted(
                str(value) for value in source.recalled_candidate.recall_sources
            ),
            "recall_facts": [
                row.model_dump(mode="json")
                for row in source.recalled_candidate.recall_facts
            ],
            "recall_rank": source.recall_rank,
            "purchase_pool": purchase_pool.model_dump(mode="json"),
            "dimensions": dimensions.model_dump(mode="json"),
            "value_anchor_analysis": value_anchor.model_dump(mode="json"),
            "replacement_pressure_analysis": replacement.model_dump(mode="json"),
            "purchase_pressure_comparison": purchase_pressure.model_dump(mode="json"),
            "market_validation": market.model_dump(mode="json"),
            "aligned_features": [
                row.model_dump(mode="json")
                for row in source.pair_feature.aligned_features
            ],
            "purchase_reason_assessments": [
                row.model_dump(mode="json")
                for row in source.value_substitution.purchase_reason_assessments
            ],
            "value_assessments": [
                row.model_dump(mode="json")
                for row in source.value_substitution.value_assessments
            ],
            "price_volume_process": source.price_volume_pressure.model_dump(
                mode="json"
            ),
            "legacy_basis": legacy_basis.model_dump(mode="json"),
            "source_lineage": lineage.model_dump(mode="json"),
            "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
            "limitations": limitations,
            "calculator_versions": dict(calculation.calculator_versions),
            "audit_summary_cn": (
                f"已完成{source.target_snapshot.identity_market.sku_code}与"
                f"{source.candidate_snapshot.identity_market.sku_code}的多维成对计算；"
                "角色、关系门槛和排序尚未在 G33 生成。"
            ),
            "input_fingerprint": calculation.input_fingerprint,
            "calculation_result_hash": calculation.calculation_result_hash,
        }
        return PairAnalysisAssembly.model_validate(
            {
                **payload,
                "result_hash": stable_hash(
                    {
                        "assembler_method_version": PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
                        **payload,
                    },
                    version=PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
                ),
            }
        )


def _validate_source(source: PairAnalysisCalculatorInput) -> None:
    if not source.competitor_profile_version_id.strip():
        raise PairAnalysisInputError("competitor profile version ID is required")
    if source.recall_rank < 1:
        raise PairAnalysisInputError("recall rank must be positive")
    target = source.target_snapshot
    candidate = source.candidate_snapshot
    scopes = {
        (
            row.project_id,
            row.category_code,
            row.release_scope_key,
            row.competitor_profile_version_id,
        )
        for row in (target, candidate)
    }
    if len(scopes) != 1 or target.competitor_profile_version_id != (
        source.competitor_profile_version_id
    ):
        raise PairAnalysisInputError(
            "pair snapshots must share one exact version scope"
        )
    target_code = target.identity_market.sku_code
    candidate_code = candidate.identity_market.sku_code
    if target_code == candidate_code:
        raise PairAnalysisInputError("self pairs belong to the G34 scope classifier")
    stages = (
        source.pair_feature,
        source.purchase_pool,
        source.value_substitution,
        source.price_volume_pressure,
    )
    if any(
        row.target.sku_code != target_code or row.candidate.sku_code != candidate_code
        for row in stages
    ):
        raise PairAnalysisInputError(
            "pair stage identities do not match shared snapshots"
        )
    if source.recalled_candidate.candidate.sku_code != candidate_code:
        raise PairAnalysisInputError(
            "recalled candidate does not match the pair candidate"
        )
    if source.pair_feature.recall_result_hash != source.recalled_candidate.result_hash:
        raise PairAnalysisInputError("pair feature recall hash chain mismatch")
    if source.purchase_pool.pair_feature_result_hash != source.pair_feature.result_hash:
        raise PairAnalysisInputError("purchase-pool hash chain mismatch")
    if (
        source.value_substitution.pair_feature_result_hash
        != source.pair_feature.result_hash
        or source.value_substitution.purchase_pool_result_hash
        != source.purchase_pool.result_hash
    ):
        raise PairAnalysisInputError("value-substitution hash chain mismatch")
    if (
        source.price_volume_pressure.pair_feature_result_hash
        != source.pair_feature.result_hash
        or source.price_volume_pressure.purchase_pool_result_hash
        != source.purchase_pool.result_hash
        or source.price_volume_pressure.value_substitution_result_hash
        != source.value_substitution.result_hash
    ):
        raise PairAnalysisInputError("price-volume hash chain mismatch")
    target_versions = target.source_lineage.get("source_module_versions") or {}
    candidate_versions = candidate.source_lineage.get("source_module_versions") or {}
    target_hashes = target.source_lineage.get("source_result_hashes") or {}
    candidate_hashes = candidate.source_lineage.get("source_result_hashes") or {}
    if target_versions != candidate_versions or target_hashes != candidate_hashes:
        raise PairAnalysisInputError(
            "pair snapshots do not share one authority lineage"
        )


def _dimension_calculations(
    target: VersionSkuAnalysisSnapshot,
    candidate: VersionSkuAnalysisSnapshot,
) -> dict[str, DimensionCalculation]:
    items = _dimension_items(target, candidate)
    result: dict[str, DimensionCalculation] = {}
    for code in _DIMENSION_MODULES:
        target_items, candidate_items = items[code]
        availability = _dimension_availability(
            target,
            candidate,
            _DIMENSION_MODULES[code],
        )
        if availability in {"unknown", "conflict"}:
            result[code] = DimensionCalculation(
                dimension_code=code,
                availability=availability,
                raw_score=None,
                positive_intersection=None,
                positive_union=None,
                risk_overlap=None,
                target_only_count=len(
                    {row.code for row in target_items}
                    - {row.code for row in candidate_items}
                ),
                candidate_only_count=len(
                    {row.code for row in candidate_items}
                    - {row.code for row in target_items}
                ),
            )
            continue
        weighted = code in {
            "battlefield_overlap",
            "user_task_overlap",
            "target_group_overlap",
        }
        score, intersection, union, risk = _overlap_score(
            target_items,
            candidate_items,
            weighted=weighted,
        )
        target_codes = {row.code for row in target_items}
        candidate_codes = {row.code for row in candidate_items}
        result[code] = DimensionCalculation(
            dimension_code=code,
            availability=availability,
            raw_score=score,
            positive_intersection=intersection,
            positive_union=union,
            risk_overlap=risk,
            target_only_count=len(target_codes - candidate_codes),
            candidate_only_count=len(candidate_codes - target_codes),
        )
    return result


def _dimension_items(
    target: VersionSkuAnalysisSnapshot,
    candidate: VersionSkuAnalysisSnapshot,
) -> dict[str, tuple[list[AnalysisItem], list[AnalysisItem]]]:
    return {
        "battlefield_overlap": (
            list(target.fact_sections.battlefield_items),
            list(candidate.fact_sections.battlefield_items),
        ),
        "user_task_overlap": (
            list(target.fact_sections.task_items),
            list(candidate.fact_sections.task_items),
        ),
        "target_group_overlap": (
            list(target.fact_sections.audience_items),
            list(candidate.fact_sections.audience_items),
        ),
        "parameter_comparison": (
            list(target.fact_sections.parameter_items),
            list(candidate.fact_sections.parameter_items),
        ),
        "claim_comparison": (
            [_as_analysis_item(row) for row in target.fact_sections.claim_items],
            [_as_analysis_item(row) for row in candidate.fact_sections.claim_items],
        ),
        "user_realization_comparison": (
            [
                _as_analysis_item(row)
                for row in target.fact_sections.claim_items
                if any(role.startswith("user_") for role in row.roles)
            ],
            [
                _as_analysis_item(row)
                for row in candidate.fact_sections.claim_items
                if any(role.startswith("user_") for role in row.roles)
            ],
        ),
        "purchase_reason_comparison": (
            [
                _as_analysis_item(row)
                for row in target.fact_sections.purchase_reason_anchors
            ],
            [
                _as_analysis_item(row)
                for row in candidate.fact_sections.purchase_reason_anchors
            ],
        ),
    }


def _dimension_availability(
    target: VersionSkuAnalysisSnapshot,
    candidate: VersionSkuAnalysisSnapshot,
    modules: Sequence[str],
) -> str:
    target_by_module = {
        row.module_code: row.availability for row in target.module_availability
    }
    candidate_by_module = {
        row.module_code: row.availability for row in candidate.module_availability
    }
    target_states = [target_by_module.get(code, "unknown") for code in modules]
    candidate_states = [candidate_by_module.get(code, "unknown") for code in modules]
    states = [*target_states, *candidate_states]
    if "conflict" in states:
        return "conflict"
    if all(value == "unknown" for value in target_states) or all(
        value == "unknown" for value in candidate_states
    ):
        return "unknown"
    if "unknown" in states or "partial" in states:
        return "partial"
    return "available"


def _overlap_score(
    target_items: Sequence[AnalysisItem],
    candidate_items: Sequence[AnalysisItem],
    *,
    weighted: bool,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    target_weights = {
        row.code: _item_weight(row, weighted=weighted) for row in target_items
    }
    candidate_weights = {
        row.code: _item_weight(row, weighted=weighted) for row in candidate_items
    }
    codes = set(target_weights) | set(candidate_weights)
    intersection = Decimal("0")
    union = Decimal("0")
    for code in codes:
        target_weight = max(target_weights.get(code, Decimal("0")), Decimal("0"))
        candidate_weight = max(candidate_weights.get(code, Decimal("0")), Decimal("0"))
        intersection += min(target_weight, candidate_weight)
        union += max(target_weight, candidate_weight)
    negative_codes = {
        code
        for code in set(target_weights) & set(candidate_weights)
        if target_weights[code] < 0 or candidate_weights[code] < 0
    }
    target_positive_count = len(
        [value for value in target_weights.values() if value > 0]
    )
    risk = Decimal(len(negative_codes)) / Decimal(max(target_positive_count, 1))
    raw = intersection / union if union else Decimal("0")
    score = max(Decimal("0"), raw - risk * Decimal("0.25"))
    return (
        _q(score),
        _q(intersection),
        _q(union),
        _q(risk),
    )


def _item_weight(item: AnalysisItem, *, weighted: bool) -> Decimal:
    if not weighted:
        return Decimal("1")
    values = [_ROLE_WEIGHTS.get(str(role), Decimal("0")) for role in item.roles]
    positive = [value for value in values if value > 0]
    if positive:
        return max(positive)
    negative = [value for value in values if value < 0]
    return min(negative) if negative else Decimal("1")


def _m12d_contract(snapshot: VersionSkuAnalysisSnapshot) -> M12DDownstreamReadContract:
    sku_code = snapshot.identity_market.sku_code
    version = str(
        (snapshot.source_lineage.get("source_module_versions") or {}).get("M12D")
        or "m12d_unknown"
    )
    batch_ids = [
        str(value)
        for value in (snapshot.source_lineage.get("source_batch_ids") or [])
        if str(value).strip()
    ]
    lookup_key = {
        "project_id": snapshot.project_id,
        "category_code": snapshot.category_code,
        "batch_id": batch_ids[0] if batch_ids else "unknown_batch",
        "m12d_profile_version": version,
        "sku_code": sku_code,
    }
    module = next(
        (row for row in snapshot.module_availability if row.module_code == "M12D"),
        None,
    )
    purchase = snapshot.purchase_reason_snapshot
    if (
        module is None
        or module.availability in {"unknown", "conflict"}
        or purchase is None
        or not purchase.found
    ):
        reason = (
            "M12D 事实冲突，价值锚点与购买阻力计算保持未知。"
            if module is not None and module.availability == "conflict"
            else "M12D 成交理由画像缺失，价值锚点与购买阻力计算保持未知。"
        )
        return M12DDownstreamReadContract(
            found=False,
            lookup_key=lookup_key,
            consumption_state="not_found",
            downstream_action="block_target_or_drop_candidate",
            message_cn=reason,
            release_quality_status="blocked",
            capabilities={"comparison_mode": "blocked"},
        )
    anchors = _m12d_anchors(purchase)
    if not anchors:
        return M12DDownstreamReadContract(
            found=False,
            lookup_key=lookup_key,
            consumption_state="not_found",
            downstream_action="block_target_or_drop_candidate",
            message_cn="M12D 未保留可识别锚点代码，成熟算法不能安全计算。",
            release_quality_status="blocked",
            capabilities={"comparison_mode": "blocked"},
        )
    core_codes = sorted(
        {row.anchor_code for row in anchors if str(row.role) == "core_payment"}
    )
    supporting_codes = sorted(
        {row.anchor_code for row in anchors if str(row.role) == "supporting"}
    )
    weak_codes = sorted(
        {row.anchor_code for row in anchors if str(row.role) == "weak_expression"}
    )
    risk_codes = sorted(
        {row.anchor_code for row in anchors if str(row.role) == "risk_drag"}
    )
    established_codes = sorted(
        {
            row.anchor_code
            for row in anchors
            if str(row.establishment_status) in {"established", "established_limited"}
        }
    )
    proposition_codes = sorted(
        {
            row.anchor_code
            for row in anchors
            if str(row.establishment_status) == "proposition_only"
        }
    )
    review_required = bool(module.review_required or module.availability == "partial")
    declared_mode = str(purchase.comparison_mode or "").lower()
    if declared_mode not in {"strong", "limited", "facts_only", "blocked"}:
        declared_mode = None
    profile_status = _m12d_profile_status(
        purchase.consumption_state,
        declared_mode or "facts_only",
        review_required,
    )
    profile = M12DDownstreamProfileContract(
        project_id=snapshot.project_id,
        category_code=snapshot.category_code,
        batch_id=lookup_key["batch_id"],
        product_category=snapshot.category_code,
        m12d_profile_version=version,
        sku_code=sku_code,
        model_name=snapshot.identity_market.model_name,
        brand_name=snapshot.identity_market.brand_name,
        display_name_cn=" ".join(
            value
            for value in (
                snapshot.identity_market.brand_name,
                snapshot.identity_market.model_name,
            )
            if value
        )
        or sku_code,
        status=profile_status,
        profile_confidence=purchase.profile_confidence,
        confidence_level=_confidence_level(purchase.profile_confidence),
        core_reasons_cn=sorted(set(purchase.core_reasons_cn)),
        core_payment_anchors=core_codes,
        supporting_anchors=supporting_codes,
        weak_expression_anchors=weak_codes,
        risk_drag_anchors=risk_codes,
        established_anchors=established_codes,
        proposition_anchors=proposition_codes,
        pressure_summary=dict(
            purchase.legacy_payload.get("pressure_summary_json") or {}
        ),
        anchors=anchors,
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        review_reasons=sorted({row.review_code for row in module.review_items}),
        degradation_reasons=(
            ["m12d_snapshot_partial"] if module.availability == "partial" else []
        ),
        evidence_summary=dict(
            purchase.legacy_payload.get("evidence_summary_json") or {}
        ),
        source_batch_ids=batch_ids,
        source_refs=[
            row.model_dump(mode="json")
            for row in snapshot.evidence_refs
            if row.module_code == "M12D"
        ],
    )
    capability_contract = derive_consumption_capabilities(
        profile=profile,
        anchors=anchors,
        release_quality_status="limited" if review_required else "ready",
    )
    capabilities = _cap_declared_m12d_capabilities(
        capability_contract.model_dump(mode="json"),
        declared_mode,
    )
    mode = str(capabilities["comparison_mode"])
    if mode == "strong" and not review_required:
        consumption_state = "published_ready"
        downstream_action = "normal_pair_scoring"
        release_quality = "ready"
    elif mode in {"strong", "limited", "facts_only"}:
        consumption_state = "published_degraded"
        downstream_action = "degraded_pair_scoring"
        release_quality = "limited"
    else:
        consumption_state = "published_unusable"
        downstream_action = "block_target_or_drop_candidate"
        release_quality = "blocked"
    return M12DDownstreamReadContract(
        found=True,
        lookup_key=lookup_key,
        consumption_state=consumption_state,
        downstream_action=downstream_action,
        message_cn=(
            "已从版本共享 SKU 快照恢复 M12D 成熟算法合同。"
            if not review_required
            else "M12D 快照可用于降级计算，结论需携带复核状态。"
        ),
        release_quality_status=release_quality,
        capabilities=capabilities,
        profile=profile,
    )


def _m12d_anchors(purchase: Any) -> list[M12DDownstreamAnchorContract]:
    by_code: dict[str, M12DDownstreamAnchorContract] = {}
    for row in purchase.anchors:
        raw = dict(row.raw_details)
        code = str(raw.get("anchor_code") or "").strip()
        if not code:
            continue
        role = _m12d_role(str(raw.get("role") or row.role))
        risk_flags = [
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, sort_keys=True)
            for value in (raw.get("risk_flags") or raw.get("risk_flags_json") or [])
        ]
        payload = {
            "anchor_code": code,
            "anchor_cn": row.anchor_cn,
            "anchor_family_code": raw.get("anchor_family_code"),
            "anchor_rank": raw.get("anchor_rank") or 0,
            "role": role,
            "evidence_strength": row.evidence_strength,
            "confidence": raw.get("confidence") or purchase.profile_confidence,
            "establishment_status": row.establishment_status,
            "establishment_score": row.establishment_score,
            "establishment_domains": raw.get("establishment_domains")
            or raw.get("establishment_domains_json")
            or [],
            "user_validation_status": row.user_validation_status,
            "core_eligible": row.core_eligible,
            "core_ineligible_reasons": raw.get("core_ineligible_reasons")
            or raw.get("core_ineligible_reasons_json")
            or [],
            "pressure_level": row.pressure_level,
            "pressure_summary_cn": row.pressure_summary_cn or "",
            "evidence_domains": row.evidence_domains,
            "support_summary_cn": row.support_summary_cn or "",
            "weakness_summary_cn": row.weakness_summary_cn or "",
            "risk_flags": sorted(set(risk_flags)),
            "source_refs": raw.get("source_refs") or raw.get("source_refs_json") or [],
        }
        try:
            anchor = M12DDownstreamAnchorContract.model_validate(payload)
        except ValueError:
            continue
        existing = by_code.get(code)
        if existing is None or _m12d_role_priority(
            str(anchor.role)
        ) < _m12d_role_priority(str(existing.role)):
            by_code[code] = anchor
    return [by_code[code] for code in sorted(by_code)]


def _m12d_role(value: str) -> str:
    if value in _M12D_ROLE_VALUES:
        return value
    if value in {"established", "proposition"}:
        return "supporting"
    if value == "weak":
        return "weak_expression"
    if value == "risk":
        return "risk_drag"
    return "supporting"


def _m12d_role_priority(value: str) -> int:
    return {
        "core_payment": 0,
        "supporting": 1,
        "weak_expression": 2,
        "risk_drag": 3,
    }.get(value, 4)


def _m12d_profile_status(state: str, mode: str, review_required: bool) -> str:
    if review_required:
        return "review_required"
    normalized = str(state or "").lower()
    if normalized in _M12D_STATUS_VALUES:
        return normalized
    if mode == "strong":
        return "ready"
    if mode == "limited":
        return "ready_limited"
    if mode == "facts_only":
        return "ready_degraded"
    return "missing_input"


def _cap_declared_m12d_capabilities(
    capabilities: dict[str, Any],
    declared_mode: str | None,
) -> dict[str, Any]:
    if declared_mode is None:
        return capabilities
    rank = {"blocked": 0, "facts_only": 1, "limited": 2, "strong": 3}
    derived_mode = str(capabilities.get("comparison_mode") or "blocked")
    effective_mode = min(
        (declared_mode, derived_mode),
        key=lambda value: rank.get(value, 0),
    )
    result = {**capabilities, "comparison_mode": effective_mode}
    if effective_mode == "blocked":
        return {
            **result,
            "fact_dimensions_allowed": False,
            "proposition_comparison_allowed": False,
            "established_reason_comparison_allowed": False,
            "strong_reason_comparison_allowed": False,
            "pressure_comparison_allowed": False,
        }
    if effective_mode == "facts_only":
        return {
            **result,
            "established_reason_comparison_allowed": False,
            "strong_reason_comparison_allowed": False,
            "pressure_comparison_allowed": False,
        }
    if effective_mode == "limited":
        result["strong_reason_comparison_allowed"] = False
    return result


def _confidence_level(value: Decimal) -> str:
    if value >= Decimal("0.80"):
        return "high"
    if value >= Decimal("0.60"):
        return "medium"
    if value > 0:
        return "low"
    return "unknown"


def _dimension_set(
    calculation: _PairAnalysisCoreCalculation,
    subject: str,
) -> PairDimensionSet:
    source = calculation.source
    items = _dimension_items(source.target_snapshot, source.candidate_snapshot)
    dimensions = {
        code: _dimension_result(
            calculation,
            code,
            items[code][0],
            items[code][1],
            subject,
        )
        for code in _DIMENSION_MODULES
    }
    aligned_payload = [
        row.model_dump(mode="json") for row in source.pair_feature.aligned_features
    ]
    return PairDimensionSet(
        battlefield_overlap=dimensions["battlefield_overlap"],
        user_task_overlap=dimensions["user_task_overlap"],
        target_group_overlap=dimensions["target_group_overlap"],
        parameter_comparison=dimensions["parameter_comparison"],
        claim_comparison=dimensions["claim_comparison"],
        user_realization_comparison=dimensions["user_realization_comparison"],
        purchase_reason_comparison=dimensions["purchase_reason_comparison"],
        legacy_semantic_overlap_payload={
            "method_version": LEGACY_WEIGHTED_OVERLAP_CONFIG_VERSION,
            "aligned_features": [
                row
                for row in aligned_payload
                if row.get("feature_group") in {"battlefield", "task", "audience"}
            ],
        },
        legacy_parameter_claim_overlap_payload={
            "aligned_features": [
                row
                for row in aligned_payload
                if row.get("feature_group")
                in {"parameter", "claim_expression", "user_realization"}
            ],
            "purchase_reason_assessments": [
                row.model_dump(mode="json")
                for row in source.value_substitution.purchase_reason_assessments
            ],
            "value_assessments": [
                row.model_dump(mode="json")
                for row in source.value_substitution.value_assessments
            ],
        },
    )


def _dimension_result(
    calculation: _PairAnalysisCoreCalculation,
    code: str,
    target_items: list[AnalysisItem],
    candidate_items: list[AnalysisItem],
    subject: str,
) -> DimensionAnalysisResult:
    source = calculation.source
    computed = calculation.dimension_calculations[code]
    target_by_code = {row.code: row for row in target_items}
    candidate_by_code = {row.code: row for row in candidate_items}
    shared_codes = sorted(set(target_by_code) & set(candidate_by_code))
    target_only_codes = sorted(set(target_by_code) - set(candidate_by_code))
    candidate_only_codes = sorted(set(candidate_by_code) - set(target_by_code))
    shared_items = [
        _merge_analysis_items(target_by_code[value], candidate_by_code[value])
        for value in shared_codes
    ]
    evidence_refs = _dedupe_evidence(
        [
            *(ref for row in target_items for ref in row.evidence_refs),
            *(ref for row in candidate_items for ref in row.evidence_refs),
            *_module_evidence(source.target_snapshot, _DIMENSION_MODULES[code]),
            *_module_evidence(source.candidate_snapshot, _DIMENSION_MODULES[code]),
        ]
    )
    fact_refs = sorted(
        {
            *(row.fact_id for row in target_items),
            *(row.fact_id for row in candidate_items),
            *_source_fact_ids(source.target_snapshot, _DIMENSION_MODULES[code]),
            *_source_fact_ids(source.candidate_snapshot, _DIMENSION_MODULES[code]),
        }
    )
    review_items = _dimension_review_items(
        code,
        source.target_snapshot,
        source.candidate_snapshot,
        _DIMENSION_MODULES[code],
    )
    limitations = _dimension_limitations(
        code,
        computed.availability,
        source.target_snapshot,
        source.candidate_snapshot,
        _DIMENSION_MODULES[code],
    )
    if computed.raw_score is None or not fact_refs:
        availability = "conflict" if computed.availability == "conflict" else "unknown"
        score = _unknown_score(_DIMENSION_WEIGHTS[code])
        conclusion = _unknown_conclusion(
            code=f"{code}_unknown",
            subject=subject,
            limitations=limitations or [f"{code}_required_facts_unknown"],
        )
        components = [
            CalculationComponent(
                component_code="overlap_score",
                known=False,
                unknown_reason_code=f"{code}_required_facts_unknown",
            )
        ]
    else:
        availability = computed.availability
        score = _known_score(_DIMENSION_WEIGHTS[code], computed.raw_score)
        strength = _score_strength(
            computed.raw_score,
            availability=availability,
            review_required=bool(review_items),
        )
        direction = _comparison_direction(
            shared_codes,
            target_only_codes,
            candidate_only_codes,
        )
        conclusion = _known_conclusion(
            code=f"{code}_{direction}",
            subject=subject,
            direction=direction,
            strength=strength,
            fact_refs=fact_refs,
            metrics=[
                ("overlap_score", computed.raw_score, "ratio"),
                ("shared_count", len(shared_codes), "count"),
                ("target_only_count", len(target_only_codes), "count"),
                ("candidate_only_count", len(candidate_only_codes), "count"),
            ],
            limitations=limitations,
            summary_cn=(
                f"{code} 已保存双方事实、共同项与差异项；"
                f"重合得分为{computed.raw_score}。"
            ),
        )
        components = [
            CalculationComponent(
                component_code="positive_weighted_intersection",
                known=True,
                input_fact_refs=fact_refs,
                value=computed.positive_intersection,
            ),
            CalculationComponent(
                component_code="positive_weighted_union",
                known=True,
                input_fact_refs=fact_refs,
                value=computed.positive_union,
            ),
            CalculationComponent(
                component_code="risk_overlap",
                known=True,
                input_fact_refs=fact_refs,
                value=computed.risk_overlap,
            ),
            CalculationComponent(
                component_code="overlap_score",
                known=True,
                input_fact_refs=fact_refs,
                value=computed.raw_score,
            ),
        ]
    legacy_payload = {
        "method_version": LEGACY_WEIGHTED_OVERLAP_CONFIG_VERSION,
        "aligned_features": [
            row.model_dump(mode="json")
            for row in source.pair_feature.aligned_features
            if _aligned_feature_matches_dimension(row, code)
        ],
    }
    if code == "purchase_reason_comparison":
        legacy_payload["assessments"] = [
            row.model_dump(mode="json")
            for row in source.value_substitution.purchase_reason_assessments
        ]
    payload = {
        "dimension_code": code,
        "availability": availability,
        "target_items": [row.model_dump(mode="json") for row in target_items],
        "candidate_items": [row.model_dump(mode="json") for row in candidate_items],
        "shared_items": [row.model_dump(mode="json") for row in shared_items],
        "target_only_items": [
            target_by_code[value].model_dump(mode="json") for value in target_only_codes
        ],
        "candidate_only_items": [
            candidate_by_code[value].model_dump(mode="json")
            for value in candidate_only_codes
        ],
        "score": score.model_dump(mode="json"),
        "calculation_components": [row.model_dump(mode="json") for row in components],
        "conclusion_strength": conclusion.strength,
        "conclusion": conclusion.model_dump(mode="json"),
        "review_required": bool(review_items),
        "review_items": [row.model_dump(mode="json") for row in review_items],
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
        "limitations": limitations,
        "legacy_payload": legacy_payload,
    }
    return DimensionAnalysisResult.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload,
                version=f"competitor_profile_v1_1_{code}_result_v1",
            ),
        }
    )


def _purchase_pool_analysis(
    calculation: _PairAnalysisCoreCalculation,
    subject: str,
) -> PurchasePoolAnalysis:
    source = calculation.source
    pool = source.purchase_pool.purchase_pool
    gate_facts = [
        PurchasePoolGateFact(
            gate_code=row.gate_code,
            known=row.known,
            passed=row.passed,
            facts={"required": row.required},
            reason_code=row.reason_code,
            evidence_refs=row.evidence_refs,
        )
        for row in sorted(pool.gate_results, key=lambda value: value.gate_code)
    ]
    fact_refs = sorted(
        {
            *_source_fact_ids(source.target_snapshot, ("M03B", "M07", "M09C", "M11C")),
            *_source_fact_ids(
                source.candidate_snapshot, ("M03B", "M07", "M09C", "M11C")
            ),
        }
    )
    if calculation.purchase_pool_score is None or not fact_refs:
        score = _unknown_score(PRIMARY_DIMENSION_WEIGHTS["purchase_pool"])
        conclusion = _unknown_conclusion(
            code="purchase_pool_unknown",
            subject=subject,
            limitations=pool.limitations or ["purchase_pool_required_gate_unknown"],
        )
    else:
        score = _known_score(
            PRIMARY_DIMENSION_WEIGHTS["purchase_pool"],
            calculation.purchase_pool_score,
        )
        conclusion = _known_conclusion(
            code=f"purchase_pool_{pool.level.lower()}",
            subject=subject,
            direction="parity" if pool.level in {"P0", "P1"} else "different_route",
            strength=_score_strength(calculation.purchase_pool_score),
            fact_refs=fact_refs,
            metrics=[
                ("purchase_pool_score", calculation.purchase_pool_score, "ratio"),
                (
                    "known_gate_count",
                    len([row for row in gate_facts if row.known]),
                    "count",
                ),
            ],
            limitations=pool.limitations,
            summary_cn=f"双方购买池为{pool.level}。",
        )
    payload = {
        "level": pool.level,
        "gate_facts": [row.model_dump(mode="json") for row in gate_facts],
        "score": score.model_dump(mode="json"),
        "conclusion": conclusion.model_dump(mode="json"),
        "legacy_payload": {
            "purchase_pool": pool.model_dump(mode="json"),
            "battlefield_overlap": source.purchase_pool.battlefield_overlap.model_dump(
                mode="json"
            ),
            "budget_band": source.purchase_pool.budget_band,
            "shared_primary_task_codes": source.purchase_pool.shared_primary_task_codes,
            "shared_task_codes": source.purchase_pool.shared_task_codes,
            "config_version": source.purchase_pool.config_version,
        },
    }
    return PurchasePoolAnalysis.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload,
                version="competitor_profile_v1_1_purchase_pool_result_v1",
            ),
        }
    )


def _purchase_pressure_analysis(
    calculation: _PairAnalysisCoreCalculation,
    subject: str,
) -> PurchasePressureComparisonResult:
    raw = calculation.purchase_pressure_result
    source = calculation.source
    evidence_refs = _dedupe_evidence(
        [
            *_module_evidence(source.target_snapshot, ("M12D",)),
            *_module_evidence(source.candidate_snapshot, ("M12D",)),
        ]
    )
    fact_refs = sorted(
        {
            *_source_fact_ids(source.target_snapshot, ("M12D",)),
            *_source_fact_ids(source.candidate_snapshot, ("M12D",)),
        }
    )
    limitations = [raw.limitation_cn] if raw.limitation_cn else []
    comparison_allowed = raw.comparison_allowed and bool(fact_refs)
    if not raw.comparison_allowed:
        limitations.append("purchase_pressure_comparison_unavailable")
    if not fact_refs:
        limitations.append("purchase_pressure_evidence_unavailable")
    limitations = sorted(set(limitations))
    if not comparison_allowed:
        conclusion = _unknown_conclusion(
            code="purchase_pressure_unknown",
            subject=subject,
            limitations=limitations,
        )
    else:
        target_rank = _pressure_rank(raw.target_highest_pressure_level)
        candidate_rank = _pressure_rank(raw.candidate_highest_pressure_level)
        direction = (
            "target_stronger"
            if target_rank < candidate_rank
            else "candidate_stronger"
            if candidate_rank < target_rank
            else "parity"
        )
        conclusion = _known_conclusion(
            code=f"purchase_pressure_{direction}",
            subject=subject,
            direction=direction,
            strength="supported" if raw.shared_anchor_comparisons else "reference",
            fact_refs=fact_refs,
            metrics=[
                ("shared_anchor_count", len(raw.shared_anchor_comparisons), "count"),
                ("target_pressure_rank", target_rank, "rank"),
                ("candidate_pressure_rank", candidate_rank, "rank"),
            ],
            limitations=limitations,
            summary_cn=raw.summary_cn,
        )
    payload = {
        "comparison_allowed": comparison_allowed,
        "target_highest_pressure_level": raw.target_highest_pressure_level,
        "candidate_highest_pressure_level": raw.candidate_highest_pressure_level,
        "shared_anchor_comparisons": [
            row.to_dict() for row in raw.shared_anchor_comparisons
        ],
        "conclusion": conclusion.model_dump(mode="json"),
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
        "limitations": limitations,
        "calculator_method_version": PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION,
        "calculator_config_version": PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION,
        "legacy_payload": raw.to_business_payload(),
    }
    return PurchasePressureComparisonResult.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload,
                version=PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION,
            ),
        }
    )


def _value_anchor_analysis(
    calculation: _PairAnalysisCoreCalculation,
    purchase_pressure: PurchasePressureComparisonResult,
    subject: str,
) -> ValueAnchorAnalysisResult:
    source = calculation.source
    raw = calculation.value_anchor_result
    target_items = [
        _as_analysis_item(row)
        for row in source.target_snapshot.fact_sections.purchase_reason_anchors
        if "core_payment" in row.roles or row.anchor_role == "core_payment"
    ]
    candidate_items = [
        _as_analysis_item(row)
        for row in source.candidate_snapshot.fact_sections.purchase_reason_anchors
        if "core_payment" in row.roles or row.anchor_role == "core_payment"
    ]
    evidence_refs = _dedupe_evidence(
        [
            *_module_evidence(source.target_snapshot, ("M12D",)),
            *_module_evidence(source.candidate_snapshot, ("M12D",)),
        ]
    )
    fact_refs = sorted(
        {
            *(row.fact_id for row in target_items),
            *(row.fact_id for row in candidate_items),
            *_source_fact_ids(source.target_snapshot, ("M12D",)),
            *_source_fact_ids(source.candidate_snapshot, ("M12D",)),
        }
    )
    allowed = raw.pair_scoring_allowed and bool(fact_refs)
    review_items = []
    if raw.requires_review:
        review_items.append(
            ReviewItem(
                review_code="value_anchor_mature_calculator_review",
                dimension_code="value_anchor",
                reason_cn="成熟价值锚点算法要求降低置信度或复核。",
                evidence_refs=evidence_refs,
            )
        )
    limitations = sorted(set(raw.gate_reasons))
    if not allowed:
        score = _unknown_score(PRIMARY_DIMENSION_WEIGHTS["value_anchor"])
        conclusion = _unknown_conclusion(
            code="value_anchor_unknown",
            subject=subject,
            limitations=limitations or ["m12d_pair_scoring_unavailable"],
        )
        anchor_score: Decimal | None = None
        level = "unknown"
    else:
        anchor_score = Decimal(raw.anchor_substitutability_score)
        normalized = anchor_score / Decimal("15")
        score = _known_score(PRIMARY_DIMENSION_WEIGHTS["value_anchor"], normalized)
        direction = (
            "candidate_stronger"
            if raw.candidate_stronger_anchors
            else "target_stronger"
            if raw.target_only_anchors
            else "parity"
            if raw.shared_core_anchors
            else "different_route"
        )
        conclusion = _known_conclusion(
            code=f"value_anchor_{direction}",
            subject=subject,
            direction=direction,
            strength=_score_strength(
                normalized,
                availability="partial" if raw.requires_review else "available",
                review_required=raw.requires_review,
            ),
            fact_refs=fact_refs,
            metrics=[
                ("anchor_substitutability_score", anchor_score, "points_15"),
                ("shared_anchor_count", len(raw.shared_core_anchors), "count"),
                (
                    "candidate_stronger_count",
                    len(raw.candidate_stronger_anchors),
                    "count",
                ),
            ],
            limitations=limitations,
            summary_cn=raw.anchor_substitution_summary_cn,
        )
        level = raw.anchor_substitutability_level
    details = [
        ValueAnchorMatchDetail(
            target_anchor_code=row.target_anchor_code,
            candidate_anchor_code=row.candidate_anchor_code,
            match_type=row.match_type,
            score=row.score,
            evidence_comparison={
                "target_anchor_cn": row.target_anchor_cn,
                "candidate_anchor_cn": row.candidate_anchor_cn,
                "target_role": row.target_role,
                "candidate_role": row.candidate_role,
                "target_evidence_strength": row.target_evidence_strength,
                "candidate_evidence_strength": row.candidate_evidence_strength,
                "summary_cn": row.evidence_comparison_cn,
            },
            evidence_refs=evidence_refs,
        )
        for row in raw.match_details
    ]
    legacy = raw.to_legacy_value_anchor()
    legacy.update(
        {
            "anchor_substitutability_score_raw": str(
                raw.anchor_substitutability_score_raw
            ),
            "score_breakdown": {
                key: str(value) for key, value in vars(raw.score_breakdown).items()
            },
            "candidate_only_anchors": list(raw.candidate_only_anchors),
            "risk_drag_anchors": list(raw.risk_drag_anchors),
        }
    )
    payload = {
        "target_core_anchors": [row.model_dump(mode="json") for row in target_items],
        "candidate_core_anchors": [
            row.model_dump(mode="json") for row in candidate_items
        ],
        "shared_anchors": sorted(set(raw.shared_core_anchors)),
        "target_stronger_anchors": sorted(set(raw.target_only_anchors)),
        "candidate_stronger_anchors": sorted(set(raw.candidate_stronger_anchors)),
        "weak_expression_anchors": sorted(set(raw.weak_expression_anchors)),
        "proposition_only_anchors": sorted(set(raw.proposition_only_anchors)),
        "purchase_pressure_comparison": purchase_pressure.model_dump(mode="json"),
        "match_details": [row.model_dump(mode="json") for row in details],
        "anchor_substitutability_score": anchor_score,
        "anchor_substitutability_level": level,
        "score": score.model_dump(mode="json"),
        "conclusion_strength": conclusion.strength,
        "conclusion": conclusion.model_dump(mode="json"),
        "review_required": bool(review_items),
        "review_items": [row.model_dump(mode="json") for row in review_items],
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
        "limitations": limitations,
        "calculator_method_version": VALUE_ANCHOR_MATCHER_METHOD_VERSION,
        "calculator_config_version": VALUE_ANCHOR_MATCHER_CONFIG_VERSION,
        "legacy_matcher_payload": _json_safe(legacy),
        "legacy_payload": {
            "target_usage_decision": _usage_decision_payload(raw.target_usage_decision),
            "candidate_usage_decision": _usage_decision_payload(
                raw.candidate_usage_decision
            ),
            "primary_direct_eligible": raw.primary_direct_eligible,
            "pair_scoring_allowed": raw.pair_scoring_allowed,
        },
    }
    return ValueAnchorAnalysisResult.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload, version=VALUE_ANCHOR_MATCHER_METHOD_VERSION
            ),
        }
    )


def _replacement_pressure_analysis(
    calculation: _PairAnalysisCoreCalculation,
    subject: str,
) -> ReplacementPressureAnalysisResult:
    source = calculation.source
    raw = calculation.replacement_pressure_result
    fact_refs = sorted(
        {
            *_source_fact_ids(
                source.target_snapshot, ("M07", "M09C", "M10C", "M11C", "M12D")
            ),
            *_source_fact_ids(
                source.candidate_snapshot, ("M07", "M09C", "M10C", "M11C", "M12D")
            ),
        }
    )
    evidence_refs = _dedupe_evidence(
        [
            *_module_evidence(
                source.target_snapshot, ("M07", "M09C", "M10C", "M11C", "M12D")
            ),
            *_module_evidence(
                source.candidate_snapshot, ("M07", "M09C", "M10C", "M11C", "M12D")
            ),
        ]
    )
    known_inputs = bool(
        calculation.purchase_pool_score is not None
        or source.price_volume_pressure.price_gap_pct is not None
        or any(
            calculation.dimension_calculations[code].raw_score is not None
            for code in (
                "battlefield_overlap",
                "user_task_overlap",
                "target_group_overlap",
            )
        )
        or calculation.value_anchor_result.pair_scoring_allowed
    )
    review_items = []
    if raw.requires_review and known_inputs:
        review_items.append(
            ReviewItem(
                review_code="replacement_pressure_mature_calculator_review",
                dimension_code="replacement_pressure",
                reason_cn="成熟替代压力算法要求降低置信度或复核。",
                evidence_refs=evidence_refs,
            )
        )
    limitations = sorted(set(raw.risk_notes))
    if not known_inputs or not fact_refs:
        score = _unknown_score(PRIMARY_DIMENSION_WEIGHTS["replacement_pressure"])
        conclusion = _unknown_conclusion(
            code="replacement_pressure_unknown",
            subject=subject,
            limitations=limitations or ["replacement_pressure_inputs_unknown"],
        )
        pressure_score: Decimal | None = None
        level = "unknown"
        primary_type = "unknown"
        components = [
            CalculationComponent(
                component_code="replacement_pressure_score",
                known=False,
                unknown_reason_code="replacement_pressure_inputs_unknown",
            )
        ]
    else:
        pressure_score = Decimal(raw.replacement_pressure_score)
        normalized = pressure_score / Decimal("10")
        score = _known_score(
            PRIMARY_DIMENSION_WEIGHTS["replacement_pressure"], normalized
        )
        conclusion = _known_conclusion(
            code=f"replacement_pressure_{raw.primary_pressure_type}",
            subject=subject,
            direction=(
                "positive_pressure"
                if raw.replacement_pressure_score >= 5
                else "no_material_effect"
            ),
            strength=_score_strength(
                normalized,
                availability="partial" if raw.requires_review else "available",
                review_required=raw.requires_review,
            ),
            fact_refs=fact_refs,
            metrics=[
                ("replacement_pressure_score", pressure_score, "points_10"),
                (
                    "strong_pressure_allowed",
                    int(raw.strong_pressure_allowed),
                    "boolean",
                ),
            ],
            limitations=limitations,
            summary_cn=raw.reason_cn,
        )
        level = raw.replacement_pressure_level
        primary_type = raw.primary_pressure_type
        components = [
            CalculationComponent(
                component_code=key,
                known=True,
                input_fact_refs=fact_refs,
                value=value,
            )
            for key, value in vars(raw.score_breakdown).items()
        ]
    legacy_payload = raw.to_legacy_replacement_pressure()
    legacy_payload.update(
        {
            "replacement_pressure_score_raw": str(raw.replacement_pressure_score_raw),
            "risk_notes": list(raw.risk_notes),
            "auxiliary_pressure_details": [
                {
                    "type": row.pressure_type,
                    "type_cn": row.pressure_type_cn,
                    "score": str(row.score),
                    "reason_cn": row.reason_cn,
                }
                for row in raw.auxiliary_pressure_types
            ],
        }
    )
    payload = {
        "primary_pressure_type": primary_type,
        "auxiliary_pressure_types": sorted(
            {row.pressure_type for row in raw.auxiliary_pressure_types}
        )
        if known_inputs
        else [],
        "pressure_components": [row.model_dump(mode="json") for row in components],
        "replacement_pressure_score": pressure_score,
        "replacement_pressure_level": level,
        "affected_purchase_reasons": sorted(
            set(calculation.value_anchor_result.shared_core_anchors)
            | set(calculation.value_anchor_result.candidate_stronger_anchors)
        ),
        "business_effect": {
            "primary_pressure_type_cn": raw.primary_pressure_type_cn,
            "strong_pressure_allowed": raw.strong_pressure_allowed,
            "reason_cn": raw.reason_cn,
            "risk_notes": list(raw.risk_notes),
        },
        "score": score.model_dump(mode="json"),
        "conclusion_strength": conclusion.strength,
        "conclusion": conclusion.model_dump(mode="json"),
        "review_required": bool(review_items),
        "review_items": [row.model_dump(mode="json") for row in review_items],
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
        "limitations": limitations,
        "calculator_method_version": REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION,
        "calculator_config_version": REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION,
        "legacy_payload": _json_safe(legacy_payload),
    }
    return ReplacementPressureAnalysisResult.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload,
                version=REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION,
            ),
        }
    )


def _market_validation(
    calculation: _PairAnalysisCoreCalculation,
    subject: str,
) -> MarketValidationAnalysisResult:
    source = calculation.source
    pressure = source.price_volume_pressure
    market = source.pair_feature.market_comparison
    diagnostics = dict(market.diagnostics)
    overlap_weeks = sorted(
        {
            str(value)
            for value in (diagnostics.get("overlap_weeks") or [])
            if str(value).strip()
        }
    )
    target_overlap = _decimal_or_none(diagnostics.get("target_overlap_weekly_volume"))
    candidate_overlap = _decimal_or_none(
        diagnostics.get("candidate_overlap_weekly_volume")
    )
    method = str(
        diagnostics.get("sales_overlap_method")
        or diagnostics.get("method")
        or "full_observed_weekly_average"
    )
    if target_overlap is None and method == "full_observed_weekly_average":
        target_overlap = pressure.target_avg_weekly_volume
    if candidate_overlap is None and method == "full_observed_weekly_average":
        candidate_overlap = pressure.candidate_avg_weekly_volume
    volume_gap = (
        candidate_overlap - target_overlap
        if target_overlap is not None and candidate_overlap is not None
        else None
    )
    volume_ratio = (
        candidate_overlap / target_overlap
        if target_overlap not in {None, Decimal("0")} and candidate_overlap is not None
        else None
    )
    sales = SalesOverlapSnapshot(
        method=method,
        window=market.market_window,
        overlap_weeks=overlap_weeks,
        target_overall_weekly_volume=pressure.target_avg_weekly_volume,
        candidate_overall_weekly_volume=pressure.candidate_avg_weekly_volume,
        target_overlap_weekly_volume=target_overlap,
        candidate_overlap_weekly_volume=candidate_overlap,
        volume_gap=volume_gap,
        volume_ratio=volume_ratio,
        boundary={
            "common_week_required": False,
            "common_platform_required": False,
            "common_week_count": pressure.common_week_count,
            "common_platform_count": pressure.common_platform_count,
            "diagnostic_only_fields": pressure.diagnostic_only_fields,
        },
        legacy_payload=diagnostics,
    )
    evidence_refs = _dedupe_evidence(
        [
            *_module_evidence(source.target_snapshot, ("M07",)),
            *_module_evidence(source.candidate_snapshot, ("M07",)),
            *pressure.evidence_refs,
        ]
    )
    fact_refs = sorted(
        {
            *_source_fact_ids(source.target_snapshot, ("M07",)),
            *_source_fact_ids(source.candidate_snapshot, ("M07",)),
        }
    )
    limitations = sorted(set(pressure.limitations))
    metrics = [
        ("price_gap", pressure.price_gap, "currency"),
        ("price_gap_pct", pressure.price_gap_pct, "ratio"),
        ("weekly_volume_gap", pressure.weekly_volume_gap, "units_per_week"),
        ("weekly_volume_ratio", pressure.weekly_volume_ratio, "ratio"),
    ]
    known_metrics = [row for row in metrics if row[1] is not None]
    if (
        pressure.market_comparability_status in {"unknown", "conflict"}
        or not known_metrics
        or not fact_refs
    ):
        conclusion = _unknown_conclusion(
            code="market_validation_unknown",
            subject=subject,
            limitations=limitations or ["market_comparison_unknown"],
        )
    else:
        strength = {
            "high": "strong",
            "medium": "supported",
            "low": "directional",
            "unknown": "reference",
        }[pressure.confidence_level]
        if (
            pressure.market_comparability_status == "limited"
            or pressure.review_required
        ):
            strength = {
                "strong": "directional",
                "supported": "directional",
                "directional": "directional",
                "reference": "reference",
            }[strength]
        direction = (
            "no_material_effect"
            if pressure.pressure_direction == "no_observed_pressure"
            else "positive_pressure"
            if pressure.pressure_direction != "reference_only"
            else "different_route"
        )
        conclusion = _known_conclusion(
            code=f"market_{pressure.pressure_direction}",
            subject=subject,
            direction=direction,
            strength=strength,
            fact_refs=fact_refs,
            metrics=known_metrics,
            limitations=limitations,
            summary_cn=(
                f"量价表现为{pressure.market_pattern}，"
                f"市场压力方向为{pressure.pressure_direction}。"
            ),
        )
    target_price = pressure.target_weighted_price
    candidate_price = pressure.candidate_weighted_price
    price_ratio = (
        candidate_price / target_price
        if target_price not in {None, Decimal("0")} and candidate_price is not None
        else None
    )
    payload = {
        "sales_overlap_snapshot": sales.model_dump(mode="json"),
        "target_weighted_price": target_price,
        "candidate_weighted_price": candidate_price,
        "price_gap": pressure.price_gap,
        "price_ratio": price_ratio,
        "market_validation_strength": conclusion.strength,
        "conclusion": conclusion.model_dump(mode="json"),
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
        "limitations": limitations,
        "legacy_summary": {
            "price_volume_assessment": pressure.model_dump(mode="json"),
            "pair_market_comparison": market.model_dump(mode="json"),
        },
    }
    return MarketValidationAnalysisResult.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload,
                version="competitor_profile_v1_1_market_validation_result_v1",
            ),
        }
    )


def _pair_lineage(
    calculation: PairAnalysisCalculation,
    evidence_refs: list[EvidenceRef],
) -> PairAnalysisSourceLineage:
    source = calculation.source
    versions = dict(
        sorted(
            (
                source.target_snapshot.source_lineage.get("source_module_versions")
                or {}
            ).items()
        )
    )
    hashes = dict(
        sorted(
            (
                source.target_snapshot.source_lineage.get("source_result_hashes") or {}
            ).items()
        )
    )
    return PairAnalysisSourceLineage(
        source_module_versions=versions,
        source_result_hashes=hashes,
        evidence_refs=evidence_refs,
        legacy_m12d_consumption={
            "target": calculation.target_m12d_contract.model_dump(mode="json"),
            "candidate": calculation.candidate_m12d_contract.model_dump(mode="json"),
            "calculator_versions": dict(calculation.calculator_versions),
        },
    )


def _reconstructed_legacy_basis(
    calculation: _PairAnalysisCoreCalculation,
    purchase_pool: PurchasePoolAnalysis,
    dimensions: PairDimensionSet,
    value_anchor: ValueAnchorAnalysisResult,
    replacement: ReplacementPressureAnalysisResult,
) -> LegacyScoreBasis:
    semantic_scores = [
        row.score.raw_score
        for row in (
            dimensions.battlefield_overlap,
            dimensions.user_task_overlap,
            dimensions.target_group_overlap,
        )
        if row.score.raw_score is not None
    ]
    param_claim_scores = [
        row.score.raw_score
        for row in (
            dimensions.parameter_comparison,
            dimensions.claim_comparison,
            dimensions.user_realization_comparison,
        )
        if row.score.raw_score is not None
    ]
    volume_target = calculation.source.price_volume_pressure.target_avg_weekly_volume
    volume_candidate = (
        calculation.source.price_volume_pressure.candidate_avg_weekly_volume
    )
    sales_closeness = (
        min(volume_target, volume_candidate) / max(volume_target, volume_candidate)
        if volume_target not in {None, Decimal("0")}
        and volume_candidate not in {None, Decimal("0")}
        else None
    )
    primary = [
        (purchase_pool.score.raw_score, PRIMARY_DIMENSION_WEIGHTS["purchase_pool"]),
        (
            dimensions.battlefield_overlap.score.raw_score,
            PRIMARY_DIMENSION_WEIGHTS["battlefield_overlap"],
        ),
        (
            dimensions.user_task_overlap.score.raw_score,
            PRIMARY_DIMENSION_WEIGHTS["user_task_overlap"],
        ),
        (
            dimensions.target_group_overlap.score.raw_score,
            PRIMARY_DIMENSION_WEIGHTS["target_group_overlap"],
        ),
        (value_anchor.score.raw_score, PRIMARY_DIMENSION_WEIGHTS["value_anchor"]),
        (
            replacement.score.raw_score,
            PRIMARY_DIMENSION_WEIGHTS["replacement_pressure"],
        ),
    ]
    available = [(score, weight) for score, weight in primary if score is not None]
    available_weight = sum((weight for _score, weight in available), Decimal("0"))
    competitor_score = (
        sum((score * weight for score, weight in available), Decimal("0"))
        / available_weight
        if available_weight
        else None
    )
    return LegacyScoreBasis(
        competitor_score=_q(competitor_score) if competitor_score is not None else None,
        semantic_overlap_score=_mean(semantic_scores),
        parameter_claim_overlap_score=_mean(param_claim_scores),
        sales_closeness_score=_q(sales_closeness)
        if sales_closeness is not None
        else None,
        legacy_payload={
            "basis_source": "v1_1_compatibility_reconstructed",
            "method_version": PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
            "available_weight": str(available_weight),
        },
    )


def _dimension_review_items(
    dimension_code: str,
    target: VersionSkuAnalysisSnapshot,
    candidate: VersionSkuAnalysisSnapshot,
    modules: Sequence[str],
) -> list[ReviewItem]:
    result: list[ReviewItem] = []
    for side, snapshot in (("target", target), ("candidate", candidate)):
        for row in snapshot.module_availability:
            if row.module_code not in modules or not row.review_required:
                continue
            result.append(
                ReviewItem(
                    review_code=f"{side}_{row.module_code.lower()}_review",
                    dimension_code=dimension_code,
                    reason_cn=f"{side} 的 {row.module_code} 证据需要复核。",
                    evidence_refs=row.evidence_refs,
                )
            )
    return sorted(result, key=lambda row: row.review_code)


def _dimension_limitations(
    dimension_code: str,
    availability: str,
    target: VersionSkuAnalysisSnapshot,
    candidate: VersionSkuAnalysisSnapshot,
    modules: Sequence[str],
) -> list[str]:
    result = []
    for side, snapshot in (("target", target), ("candidate", candidate)):
        by_module = {row.module_code: row for row in snapshot.module_availability}
        for code in modules:
            state = by_module[code].availability
            if state != "available":
                result.append(f"{side}_{code.lower()}_{state}")
    if availability in {"unknown", "conflict"}:
        result.append(f"{dimension_code}_{availability}")
    return sorted(set(result))


def _merge_analysis_items(
    target: AnalysisItem, candidate: AnalysisItem
) -> AnalysisItem:
    refs = _dedupe_evidence([*target.evidence_refs, *candidate.evidence_refs])
    statuses = {target.support_status, candidate.support_status}
    support_status = (
        "contradicted"
        if "contradicted" in statuses
        else "supported"
        if "supported" in statuses
        else "unsupported"
        if "unsupported" in statuses
        else "unknown"
    )
    payload = {
        "code": target.code,
        "roles": sorted(set(target.roles) | set(candidate.roles)),
        "values": [
            *[row.model_dump(mode="json") for row in target.values],
            *[row.model_dump(mode="json") for row in candidate.values],
        ],
        "support_status": support_status,
        "confidence": _minimum_known(target.confidence, candidate.confidence),
        "evidence_refs": [row.model_dump(mode="json") for row in refs],
        "legacy_payload": {
            "target_fact_id": target.fact_id,
            "candidate_fact_id": candidate.fact_id,
        },
    }
    return AnalysisItem(
        fact_id=stable_hash(payload, version="competitor_profile_v1_1_shared_fact_v1"),
        **payload,
    )


def _as_analysis_item(value: Any) -> AnalysisItem:
    return AnalysisItem(
        fact_id=value.fact_id,
        code=value.code,
        roles=list(value.roles),
        values=list(value.values),
        support_status=value.support_status,
        confidence=value.confidence,
        evidence_refs=list(value.evidence_refs),
        legacy_payload=dict(value.legacy_payload),
    )


def _module_evidence(
    snapshot: VersionSkuAnalysisSnapshot,
    modules: Sequence[str],
) -> list[EvidenceRef]:
    return [row for row in snapshot.evidence_refs if row.module_code in modules]


def _source_fact_ids(
    snapshot: VersionSkuAnalysisSnapshot,
    modules: Sequence[str],
) -> list[str]:
    return sorted(
        row.fact_id for row in snapshot.source_facts if row.source_atom in modules
    )


def _known_score(weight: Decimal, raw_score: Decimal) -> DimensionScore:
    return DimensionScore(
        configured_weight=weight,
        raw_score=raw_score,
        available_weight=weight,
        normalized_score=raw_score,
        weighted_contribution=raw_score * weight,
    )


def _unknown_score(weight: Decimal) -> DimensionScore:
    return DimensionScore(
        configured_weight=weight,
        raw_score=None,
        available_weight=Decimal("0"),
        normalized_score=None,
        weighted_contribution=Decimal("0"),
    )


def _known_conclusion(
    *,
    code: str,
    subject: str,
    direction: str,
    strength: str,
    fact_refs: Sequence[str],
    metrics: Sequence[tuple[str, Any, str | None]],
    limitations: Sequence[str],
    summary_cn: str,
) -> MachineReadableConclusion:
    return MachineReadableConclusion(
        conclusion_code=code,
        subject=subject,
        direction=direction,
        metrics=[
            ConclusionMetric(
                metric_code=metric_code,
                value=_json_metric_value(value),
                unit=unit,
            )
            for metric_code, value, unit in metrics
        ],
        supporting_fact_refs=sorted(set(fact_refs)),
        strength=strength,
        limitations=sorted(set(limitations)),
        audit_summary_cn=summary_cn,
    )


def _unknown_conclusion(
    *,
    code: str,
    subject: str,
    limitations: Sequence[str],
) -> MachineReadableConclusion:
    return MachineReadableConclusion(
        conclusion_code=code,
        subject=subject,
        direction="unknown",
        strength="unknown",
        limitations=sorted(set(limitations)) or ["required_facts_unknown"],
        audit_summary_cn="所需事实缺失或冲突，本维度保持未知。",
    )


def _score_strength(
    score: Decimal,
    *,
    availability: str = "available",
    review_required: bool = False,
) -> str:
    if score >= Decimal("0.80"):
        value = "strong"
    elif score >= Decimal("0.60"):
        value = "supported"
    elif score >= Decimal("0.30"):
        value = "directional"
    else:
        value = "reference"
    if availability == "partial" or review_required:
        return "directional" if value in {"strong", "supported"} else value
    return value


def _comparison_direction(
    shared: Sequence[str],
    target_only: Sequence[str],
    candidate_only: Sequence[str],
) -> str:
    if len(candidate_only) > len(target_only):
        return "candidate_stronger"
    if len(target_only) > len(candidate_only):
        return "target_stronger"
    if shared:
        return "parity"
    return "different_route"


def _aligned_feature_matches_dimension(row: PairAlignedFeature, code: str) -> bool:
    return (
        row.feature_group
        in {
            "battlefield_overlap": {"battlefield"},
            "user_task_overlap": {"task"},
            "target_group_overlap": {"audience"},
            "parameter_comparison": {"parameter"},
            "claim_comparison": {"claim_expression"},
            "user_realization_comparison": {"user_realization"},
            "purchase_reason_comparison": {"purchase_reason"},
        }[code]
    )


def _market_level(pressure: PriceVolumePressureAssessment) -> str:
    if pressure.market_comparability_status in {"unknown", "conflict"}:
        return "missing"
    if pressure.market_comparability_status == "limited" or pressure.review_required:
        return "weak"
    return {
        "high": "strong",
        "medium": "medium",
        "low": "weak",
        "unknown": "weak",
    }[pressure.confidence_level]


def _candidate_value_advantage(value: ValueSubstitutionEvidencePair) -> Decimal | None:
    positive = len(value.candidate_only_positive_value_codes)
    total = len(
        set(value.shared_discriminative_value_codes)
        | set(value.target_only_positive_value_codes)
        | set(value.candidate_only_positive_value_codes)
    )
    return _q(Decimal(positive) / Decimal(total)) if total else None


def _candidate_scenario_advantage(
    dimensions: Mapping[str, DimensionCalculation],
) -> Decimal | None:
    values = [
        row
        for row in (
            dimensions["battlefield_overlap"],
            dimensions["user_task_overlap"],
        )
        if row.raw_score is not None
    ]
    if not values:
        return None
    total = sum(row.target_only_count + row.candidate_only_count for row in values)
    candidate = sum(row.candidate_only_count for row in values)
    return _q(Decimal(candidate) / Decimal(total)) if total else Decimal("0")


def _replacement_risk_flags(source: PairAnalysisCalculatorInput) -> list[str]:
    flags = set(source.pair_feature.review_reason_codes)
    if source.pair_feature.lineage_conflict_reason_codes:
        flags.add("evidence_conflict")
    if source.price_volume_pressure.market_comparability_status == "unknown":
        flags.add("market_missing")
    if (
        source.price_volume_pressure.market_comparability_status == "limited"
        or source.price_volume_pressure.review_required
    ):
        flags.add("sample_limited")
    if source.value_substitution.evidence_status == "unassessable":
        flags.add("sample_limited")
    return sorted(flags)


def _calculator_versions() -> dict[str, str]:
    return dict(
        sorted(
            {
                "purchase_pressure_config": PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION,
                "purchase_pressure_method": PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION,
                "replacement_pressure_config": REPLACEMENT_PRESSURE_CLASSIFIER_CONFIG_VERSION,
                "replacement_pressure_method": REPLACEMENT_PRESSURE_CLASSIFIER_METHOD_VERSION,
                "value_anchor_config": VALUE_ANCHOR_MATCHER_CONFIG_VERSION,
                "value_anchor_method": VALUE_ANCHOR_MATCHER_METHOD_VERSION,
            }.items()
        )
    )


def _calculation_result_hash(
    *,
    input_fingerprint: str,
    purchase_pool: PurchasePoolAnalysis,
    dimensions: PairDimensionSet,
    value_anchor: ValueAnchorAnalysisResult,
    replacement_pressure: ReplacementPressureAnalysisResult,
    purchase_pressure: PurchasePressureComparisonResult,
    market_validation: MarketValidationAnalysisResult,
    legacy_basis: LegacyScoreBasis,
    calculator_versions: Mapping[str, str],
) -> str:
    return stable_hash(
        {
            "input_fingerprint": input_fingerprint,
            "purchase_pool_result_hash": purchase_pool.result_hash,
            "dimensions": {
                key: getattr(dimensions, key).result_hash for key in _DIMENSION_MODULES
            },
            "value_anchor_result_hash": value_anchor.result_hash,
            "replacement_pressure_result_hash": replacement_pressure.result_hash,
            "purchase_pressure_result_hash": purchase_pressure.result_hash,
            "market_validation_result_hash": market_validation.result_hash,
            "legacy_basis": legacy_basis.model_dump(mode="json"),
            "calculator_versions": dict(calculator_versions),
        },
        version=PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
    )


def _usage_decision_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    return {
        "subject_role": value.subject_role,
        "action": value.action,
        "pair_scoring_allowed": value.pair_scoring_allowed,
        "strong_ranking_allowed": value.strong_ranking_allowed,
        "top3_eligible": value.top3_eligible,
        "requires_review": value.requires_review,
        "confidence_state": value.confidence_state,
        "message_cn": value.message_cn,
        "reasons": list(value.reasons),
    }


def _pressure_rank(value: str) -> int:
    return {
        "unassessed": -1,
        "none": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }.get(str(value), -1)


def _subject(source: PairAnalysisCalculatorInput) -> str:
    return (
        f"{source.target_snapshot.identity_market.sku_code}:"
        f"{source.candidate_snapshot.identity_market.sku_code}"
    )


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return _q(sum(values, Decimal("0")) / Decimal(len(values))) if values else None


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _json_metric_value(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    return value


def _minimum_known(*values: Decimal | None) -> Decimal | None:
    known = [value for value in values if value is not None]
    return min(known) if known else None


def _dedupe_evidence(values: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    indexed: dict[tuple[str, str, str, str, str], EvidenceRef] = {}
    for value in values:
        key = _evidence_key(value)
        existing = indexed.get(key)
        if existing is None:
            indexed[key] = value
            continue
        for field_name in ("profile_version", "rule_version", "taxonomy_version"):
            if getattr(existing, field_name) != getattr(value, field_name):
                raise ValueError(
                    "duplicate evidence ref carries conflicting version metadata"
                )
        confidences = {
            confidence
            for confidence in (existing.confidence, value.confidence)
            if confidence is not None
        }
        if len(confidences) > 1:
            raise ValueError(
                "duplicate evidence ref carries conflicting confidence metadata"
            )
        indexed[key] = existing.model_copy(
            update={
                "evidence_ids": sorted(
                    set(existing.evidence_ids) | set(value.evidence_ids)
                ),
                "source_file_ids": sorted(
                    set(existing.source_file_ids) | set(value.source_file_ids)
                ),
                "raw_row_ids": sorted(
                    set(existing.raw_row_ids) | set(value.raw_row_ids)
                ),
                "confidence": next(iter(confidences), None),
            }
        )
    return [indexed[key] for key in sorted(indexed)]


def _assembly_child_evidence(
    assembly: PairAnalysisAssembly,
) -> list[EvidenceRef]:
    values: list[EvidenceRef] = []
    for gate in assembly.purchase_pool.gate_facts:
        values.extend(gate.evidence_refs)
    for code in _DIMENSION_MODULES:
        dimension = getattr(assembly.dimensions, code)
        values.extend(dimension.evidence_refs)
        for item in (
            *dimension.target_items,
            *dimension.candidate_items,
            *dimension.shared_items,
            *dimension.target_only_items,
            *dimension.candidate_only_items,
        ):
            values.extend(item.evidence_refs)
        for review in dimension.review_items:
            values.extend(review.evidence_refs)
    values.extend(assembly.value_anchor_analysis.evidence_refs)
    for item in (
        *assembly.value_anchor_analysis.target_core_anchors,
        *assembly.value_anchor_analysis.candidate_core_anchors,
    ):
        values.extend(item.evidence_refs)
    for detail in assembly.value_anchor_analysis.match_details:
        values.extend(detail.evidence_refs)
    for review in assembly.value_anchor_analysis.review_items:
        values.extend(review.evidence_refs)
    values.extend(assembly.replacement_pressure_analysis.evidence_refs)
    for review in assembly.replacement_pressure_analysis.review_items:
        values.extend(review.evidence_refs)
    values.extend(assembly.purchase_pressure_comparison.evidence_refs)
    values.extend(assembly.market_validation.evidence_refs)
    return values


def _evidence_key(value: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        value.module_code,
        value.source_batch_id or "",
        value.record_type,
        value.record_id,
        value.result_hash,
    )


def _assert_evidence_order(values: Sequence[EvidenceRef]) -> None:
    keys = [_evidence_key(value) for value in values]
    if keys != sorted(set(keys)):
        raise ValueError("pair analysis evidence refs must be sorted and unique")


__all__ = [
    "LEGACY_WEIGHTED_OVERLAP_CONFIG_VERSION",
    "PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION",
    "PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION",
    "DimensionCalculation",
    "PairAnalysisAssembler",
    "PairAnalysisAssembly",
    "PairAnalysisCalculation",
    "PairAnalysisCalculator",
    "PairAnalysisCalculatorInput",
    "PairAnalysisInputError",
]
