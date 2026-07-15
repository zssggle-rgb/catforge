"""Pure G36 materialization of frozen V1.1 analysis outputs.

This module deliberately has no calculator, selector, provider, repository, or
database dependency.  It validates the G32--G35 hash chain and maps it into the
lossless persistence DTO introduced in G29/G31.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import EvidenceRef
from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    PairGateEvaluation,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PairAnalysisAssembly,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    AnalysisItem,
    CompetitorProfileAnalysisDTO,
    CompetitorProfileV11BaseModel,
    ConclusionDirection,
    ConclusionStrength,
    DimensionAvailability,
    FactIndexEntry,
    FactSupportStatus,
    LegacyPrioritySelectionDiff,
    LegacyScoreBasis,
    MachineReadableConclusion,
    PairAnalysisProcessSnapshot,
    PairAnalysisSnapshot,
    PairAuditSummary,
    PairDimensionGateSnapshot,
    PairIndexItem,
    PairScopeStatus,
    PairSelectionAssessment,
    PriorityCompetitorSelection,
    ProfileGenerationReceipt,
    ProfileVersionAnalysisContext,
    ReviewItem,
    SkuCompetitionAnalysisSummary,
    SummaryFinding,
    TypedFactValue,
    VersionSkuAnalysisSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    CompetitorSelectionResult,
    PairSelectionDecision,
    assert_competitor_selection_result_integrity,
    assert_pair_selection_integrity,
)
from app.services.core3_real_data.hash_utils import stable_hash, stable_hash_streaming


COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION = (
    "competitor_profile_v1_1_materializer_v1"
)

_SUMMARY_BUCKET_BY_QUESTION = {
    "purchase_choice": "competitive_advantages",
    "scenario_solution": "competitive_advantages",
    "same_brand_portfolio_role": "competitive_advantages",
    "value_substitution": "substitutable_values",
    "configuration_follow": "configuration_differences",
    "price_volume_pressure": "price_volume_pressures",
    "price_ladder_defense": "price_volume_pressures",
}


class CompetitorProfileV11MaterializationError(RuntimeError):
    """Raised when frozen stage outputs do not form one immutable graph."""


class HardExcludedPairMaterializationInput(CompetitorProfileV11BaseModel):
    """Recall metadata that G33 correctly omits for hard-excluded pairs."""

    candidate_sku_code: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    recall_sources: list[str] = Field(min_length=1)
    recall_fact_items: list[dict[str, Any]] = Field(default_factory=list)
    recall_rank: int = Field(ge=1)
    legacy_recall_basis: dict[str, Any] = Field(default_factory=dict)
    legacy_basis: LegacyScoreBasis = Field(default_factory=LegacyScoreBasis)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_recall(self) -> "HardExcludedPairMaterializationInput":
        if self.recall_sources != sorted(set(self.recall_sources)):
            raise ValueError("hard-excluded recall sources must be sorted and unique")
        return self


class MaterializedCompetitorProfileV11(CompetitorProfileV11BaseModel):
    target_sku_code: str = Field(min_length=1)
    dto: CompetitorProfileAnalysisDTO
    stage_result_hashes: dict[str, str]
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "MaterializedCompetitorProfileV11":
        if self.target_sku_code != self.dto.sku_summary.target_sku_code:
            raise ValueError("materialized target must match its DTO")
        if self.dto.profile_result_hash != self.result_hash:
            raise ValueError("materialized and DTO result hashes must match")
        return self


class CompetitorProfileV11Materializer:
    """Map G32--G35 outputs to one immutable DTO without analysis calls."""

    def materialize(
        self,
        *,
        profile_version: ProfileVersionAnalysisContext,
        target_snapshot: VersionSkuAnalysisSnapshot,
        candidate_snapshots: Sequence[VersionSkuAnalysisSnapshot],
        pair_assemblies: Sequence[PairAnalysisAssembly],
        gate_evaluations: Sequence[PairGateEvaluation],
        selection_result: CompetitorSelectionResult,
        hard_excluded_inputs: Sequence[HardExcludedPairMaterializationInput] = (),
    ) -> MaterializedCompetitorProfileV11:
        snapshots = _unique_by_sku(candidate_snapshots, label="candidate snapshots")
        assemblies = _unique_by_candidate(pair_assemblies, label="G33 assemblies")
        gates = _unique_by_candidate(gate_evaluations, label="G34 gates")
        excluded = {
            row.candidate_sku_code: row
            for row in hard_excluded_inputs
        }
        if len(excluded) != len(hard_excluded_inputs):
            raise CompetitorProfileV11MaterializationError(
                "hard-excluded inputs must be unique by candidate SKU"
            )
        selection_result = CompetitorSelectionResult.model_validate(selection_result)
        assert_competitor_selection_result_integrity(selection_result)
        _assert_authority(
            profile_version=profile_version,
            target_snapshot=target_snapshot,
            candidate_snapshots=snapshots,
            assemblies=assemblies,
            gates=gates,
            selection=selection_result,
        )

        decisions = {
            _required_candidate_code(row): row
            for row in selection_result.pair_decisions
        }
        pair_analyses: list[PairAnalysisSnapshot] = []
        for candidate_code in sorted(decisions):
            decision = decisions[candidate_code]
            gate = gates[candidate_code]
            assembly = assemblies.get(candidate_code)
            assert_pair_selection_integrity(
                decision,
                assembly=assembly,
                gate=gate,
            )
            pair_analyses.append(
                _materialize_pair(
                    decision=decision,
                    gate=gate,
                    assembly=assembly,
                    excluded_input=excluded.get(candidate_code),
                )
            )
        unused_excluded = sorted(set(excluded) - set(decisions))
        if unused_excluded:
            raise CompetitorProfileV11MaterializationError(
                f"hard-excluded inputs are outside the selection universe: {unused_excluded}"
            )

        pair_by_code = {row.candidate_sku_code: row for row in pair_analyses}
        priority = _priority_selections(selection_result, pair_by_code)
        summary = _summary(selection_result, pair_analyses, priority)
        pair_index = [
            PairIndexItem(
                candidate_sku_code=row.candidate_sku_code,
                scope_status=row.scope_status,
                recall_rank=row.recall_rank,
                primary_role=row.primary_role,
                conclusion_strength=row.overall_conclusion_strength,
                selected_rank=(
                    row.selection_assessment.selection_rank
                    if row.selection_assessment is not None
                    else None
                ),
                pair_result_hash=row.result_hash,
            )
            for row in pair_analyses
        ]
        input_fingerprint = stable_hash(
            {
                "materializer_version": COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION,
                "profile_version": profile_version.model_dump(mode="json"),
                "target_snapshot_hash": target_snapshot.result_hash,
                "candidate_snapshot_hashes": {
                    code: row.result_hash for code, row in snapshots.items()
                },
                "assembly_hashes": {
                    code: row.result_hash for code, row in assemblies.items()
                },
                "gate_hashes": {code: row.result_hash for code, row in gates.items()},
                "selection_result_hash": selection_result.result_hash,
            },
            version="competitor_profile_v1_1_materializer_input_v1",
        )
        generation_receipt = _generation_receipt(
            target_snapshot=target_snapshot,
            candidate_snapshots=snapshots,
            pair_analyses=pair_analyses,
            selection_result=selection_result,
            input_fingerprint=input_fingerprint,
        )
        candidate_snapshot_rows = [snapshots[code] for code in sorted(snapshots)]
        persisted_candidate_snapshots = [
            row
            for row in candidate_snapshot_rows
            if row.snapshot_ref != target_snapshot.snapshot_ref
        ]
        fact_index, evidence_index = _build_indexes(
            [
                profile_version,
                generation_receipt,
                target_snapshot,
                *persisted_candidate_snapshots,
                summary,
                *priority,
                *pair_analyses,
            ]
        )
        result_payload = {
            "profile_version": profile_version,
            "generation_receipt": generation_receipt,
            "target_snapshot": target_snapshot,
            "candidate_snapshots": persisted_candidate_snapshots,
            "sku_summary": summary,
            "priority_selections": priority,
            "pair_analyses": pair_analyses,
            "full_pair_index": pair_index,
            "fact_index": fact_index,
            "evidence_index": evidence_index,
            "input_fingerprint": input_fingerprint,
        }
        profile_result_hash = stable_hash_streaming(
            result_payload,
            version="competitor_profile_v1_1_profile_result_v1",
        )
        dto = CompetitorProfileAnalysisDTO(
            profile_version=profile_version,
            generation_receipt=generation_receipt,
            target_snapshot=target_snapshot,
            candidate_snapshots=candidate_snapshot_rows,
            sku_summary=summary,
            priority_selections=priority,
            full_pair_index=pair_index,
            pair_analyses=pair_analyses,
            fact_index=fact_index,
            evidence_index=evidence_index,
            profile_result_hash=profile_result_hash,
        )
        return MaterializedCompetitorProfileV11(
            target_sku_code=selection_result.target_sku_code,
            dto=dto,
            stage_result_hashes={
                "target_snapshot": target_snapshot.result_hash,
                "selection": selection_result.result_hash,
                "summary": summary.result_hash,
                "generation_receipt": generation_receipt.result_hash,
            },
            input_fingerprint=input_fingerprint,
            result_hash=profile_result_hash,
        )


def _materialize_pair(
    *,
    decision: PairSelectionDecision,
    gate: PairGateEvaluation,
    assembly: PairAnalysisAssembly | None,
    excluded_input: HardExcludedPairMaterializationInput | None,
) -> PairAnalysisSnapshot:
    candidate_code = _required_candidate_code(decision)
    assessment = PairSelectionAssessment(
        answerable_question_codes=decision.answerable_question_codes,
        selection_eligible=decision.selection_eligible,
        selected=decision.selected,
        selection_rank=decision.selection_rank,
        selection_reason_code=decision.selection_reason_code,
        selection_reason_cn=decision.selection_reason_cn,
        selection_conclusion_strength=decision.selection_conclusion_strength,
        market_validation_strength=decision.market_validation_strength,
        legacy_rank=decision.legacy_rank,
        legacy_role=decision.legacy_role,
        pair_selection_result_hash=decision.result_hash,
    )
    input_fingerprint = stable_hash(
        {
            "assembly_result_hash": assembly.result_hash if assembly else None,
            "gate_result_hash": gate.result_hash,
            "pair_selection_result_hash": decision.result_hash,
            "materializer_version": COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION,
        },
        version="competitor_profile_v1_1_pair_materializer_input_v1",
    )
    if assembly is None:
        if excluded_input is None:
            raise CompetitorProfileV11MaterializationError(
                f"hard-excluded candidate {candidate_code} is missing recall metadata"
            )
        if (
            gate.scope.candidate_snapshot_ref != excluded_input.candidate_snapshot_ref
            or gate.scope.candidate_sku_code != excluded_input.candidate_sku_code
        ):
            raise CompetitorProfileV11MaterializationError(
                "hard-excluded recall metadata must match its scope result"
            )
        payload: dict[str, Any] = {
            "project_id": gate.project_id,
            "category_code": gate.category_code,
            "competitor_profile_version_id": gate.competitor_profile_version_id,
            "release_scope_key": gate.release_scope_key,
            "target_sku_code": gate.target_sku_code,
            "candidate_sku_code": candidate_code,
            "target_snapshot_ref": gate.scope.target_snapshot_ref,
            "candidate_snapshot_ref": excluded_input.candidate_snapshot_ref,
            "scope_status": gate.scope.scope_status,
            "exclusion_reason_code": gate.scope.exclusion_reason_code,
            "recall_sources": excluded_input.recall_sources,
            "recall_facts": {"items": excluded_input.recall_fact_items},
            "recall_rank": excluded_input.recall_rank,
            "legacy_recall_basis": excluded_input.legacy_recall_basis,
            "legacy_basis": excluded_input.legacy_basis,
            "selection_assessment": assessment,
            "overall_conclusion_strength": ConclusionStrength.UNKNOWN.value,
            "overall_conclusion": MachineReadableConclusion(
                conclusion_code=f"scope_excluded_{gate.scope.exclusion_reason_code}",
                subject=candidate_code,
                direction=ConclusionDirection.UNKNOWN.value,
                strength=ConclusionStrength.UNKNOWN.value,
                limitations=[
                    f"candidate excluded by {gate.scope.exclusion_reason_code}"
                ],
                audit_summary_cn=decision.selection_reason_cn,
            ),
            "source_lineage": {
                "source_module_versions": {
                    "G34.scope": gate.scope.method_version,
                    "G34.gate": gate.method_version,
                    "G35.selection": "competitor_profile_v1_1_selector_v1",
                },
                "source_result_hashes": {
                    "G34.scope": gate.scope.result_hash,
                    "G34.gate": gate.result_hash,
                    "G35.selection": decision.result_hash,
                },
                "evidence_refs": excluded_input.evidence_refs,
            },
            "evidence_refs": excluded_input.evidence_refs,
            "limitations": [f"scope_excluded:{gate.scope.exclusion_reason_code}"],
            "audit_summary": PairAuditSummary(
                legacy_exclusion_reason_cn=decision.selection_reason_cn,
                summary_cn=decision.selection_reason_cn,
            ),
            "input_fingerprint": input_fingerprint,
        }
    else:
        if excluded_input is not None:
            raise CompetitorProfileV11MaterializationError(
                f"analyzable candidate {candidate_code} cannot have exclusion metadata"
            )
        overall = _overall_conclusion(gate)
        payload = {
            "project_id": assembly.project_id,
            "category_code": assembly.category_code,
            "competitor_profile_version_id": assembly.competitor_profile_version_id,
            "release_scope_key": assembly.release_scope_key,
            "target_sku_code": assembly.target_sku_code,
            "candidate_sku_code": assembly.candidate_sku_code,
            "target_snapshot_ref": assembly.target_snapshot_ref,
            "candidate_snapshot_ref": assembly.candidate_snapshot_ref,
            "scope_status": gate.scope.scope_status,
            "recall_sources": assembly.recall_sources,
            "recall_facts": {"items": assembly.recall_facts},
            "recall_rank": assembly.recall_rank,
            "legacy_basis": assembly.legacy_basis,
            "dimension_gates": [
                PairDimensionGateSnapshot.model_validate(row.model_dump(mode="json"))
                for row in gate.dimension_states
            ],
            "purchase_pool": assembly.purchase_pool,
            "dimensions": assembly.dimensions,
            "value_anchor_analysis": assembly.value_anchor_analysis,
            "replacement_pressure_analysis": assembly.replacement_pressure_analysis,
            "purchase_pressure_comparison": assembly.purchase_pressure_comparison,
            "market_validation": assembly.market_validation,
            "comparison_roles": decision.comparison_roles,
            "primary_role": decision.primary_role,
            "score_breakdown": decision.score_breakdown,
            "analysis_process": PairAnalysisProcessSnapshot(
                aligned_features=assembly.aligned_features,
                purchase_reason_assessments=assembly.purchase_reason_assessments,
                value_assessments=assembly.value_assessments,
                price_volume_process=assembly.price_volume_process,
                calculator_versions=assembly.calculator_versions,
                assembly_result_hash=assembly.result_hash,
                gate_result_hash=gate.result_hash,
            ),
            "selection_assessment": assessment,
            "relation_assessments": gate.relation_assessments,
            "business_questions": gate.business_questions,
            "derived_facts": _dimension_result_facts(gate),
            "overall_conclusion_strength": overall.strength,
            "overall_conclusion": overall,
            "review_required": gate.review_required,
            "review_items": gate.review_items,
            "source_lineage": assembly.source_lineage,
            "evidence_refs": assembly.evidence_refs,
            "limitations": sorted(set(assembly.limitations)),
            "audit_summary": PairAuditSummary(
                role_cn=(str(decision.primary_role) if decision.primary_role else None),
                summary_cn=assembly.audit_summary_cn,
            ),
            "input_fingerprint": input_fingerprint,
        }
    result_hash = stable_hash(
        payload,
        version="competitor_profile_v1_1_pair_snapshot_result_v1",
    )
    return PairAnalysisSnapshot(**payload, result_hash=result_hash)


def _priority_selections(
    selection: CompetitorSelectionResult,
    pair_by_code: Mapping[str, PairAnalysisSnapshot],
) -> list[PriorityCompetitorSelection]:
    rows: list[PriorityCompetitorSelection] = []
    for plan in selection.priority_competitors:
        pair = pair_by_code[plan.candidate_sku_code]
        payload = {
            "target_sku_code": selection.target_sku_code,
            "candidate_sku_code": plan.candidate_sku_code,
            "selection_rank": plan.selection_rank,
            "pair_result_hash": pair.result_hash,
            "primary_role": plan.primary_role,
            "role_codes": plan.role_codes,
            "selection_score": plan.selection_score,
            "selection_available_weight": plan.selection_available_weight,
            "selection_conclusion_strength": plan.selection_conclusion_strength,
            "selection_reason_code": plan.selection_reason_code,
            "selection_reason_cn": plan.selection_reason_cn,
            "pair_selection_result_hash": plan.pair_selection_result_hash,
        }
        rows.append(
            PriorityCompetitorSelection(
                **payload,
                result_hash=stable_hash(
                    payload,
                    version="competitor_profile_v1_1_priority_selection_result_v1",
                ),
            )
        )
    return rows


def _summary(
    selection: CompetitorSelectionResult,
    pairs: Sequence[PairAnalysisSnapshot],
    priority: Sequence[PriorityCompetitorSelection],
) -> SkuCompetitionAnalysisSummary:
    availability_counts: dict[str, int] = {}
    conclusion_counts: dict[str, int] = {}
    availability_by_dimension: dict[str, list[str]] = {}
    review_items: list[ReviewItem] = []
    limitations: set[str] = set()
    buckets: dict[str, list[SummaryFinding]] = {
        "competitive_advantages": [],
        "substitutable_values": [],
        "configuration_differences": [],
        "price_volume_pressures": [],
    }
    for pair in pairs:
        strength = str(pair.overall_conclusion_strength)
        conclusion_counts[strength] = conclusion_counts.get(strength, 0) + 1
        review_items.extend(pair.review_items)
        limitations.update(pair.limitations)
        if pair.dimensions is not None:
            for code in (
                "battlefield_overlap",
                "user_task_overlap",
                "target_group_overlap",
                "parameter_comparison",
                "claim_comparison",
                "user_realization_comparison",
                "purchase_reason_comparison",
            ):
                availability = str(getattr(pair.dimensions, code).availability)
                availability_counts[availability] = (
                    availability_counts.get(availability, 0) + 1
                )
                availability_by_dimension.setdefault(code, []).append(availability)
        for question in pair.business_questions:
            question_code = str(question.question_code)
            bucket = _SUMMARY_BUCKET_BY_QUESTION.get(question_code)
            if bucket is None or not question.answerable:
                continue
            buckets[bucket].append(
                SummaryFinding(
                    finding_code=f"{question_code}:{pair.candidate_sku_code}",
                    candidate_sku_codes=[pair.candidate_sku_code],
                    conclusion=question.conclusion,
                    evidence_refs=_conclusion_evidence_refs(
                        pair,
                        question.conclusion.supporting_fact_refs,
                    ),
                )
            )
    unknown_dimensions = sorted(
        code
        for code, values in availability_by_dimension.items()
        if values
        and all(
            value
            in {
                DimensionAvailability.UNKNOWN.value,
                DimensionAvailability.CONFLICT.value,
            }
            for value in values
        )
    )
    review_items = _dedupe_models(review_items)
    legacy_diffs = [
        LegacyPrioritySelectionDiff.model_validate(row.model_dump(mode="json"))
        for row in selection.legacy_selection_diffs
    ]
    input_fingerprint = stable_hash(
        {
            "pair_result_hashes": {
                row.candidate_sku_code: row.result_hash for row in pairs
            },
            "selection_result_hash": selection.result_hash,
        },
        version="competitor_profile_v1_1_summary_input_v1",
    )
    payload = {
        "target_sku_code": selection.target_sku_code,
        "analysis_candidate_count": len(pairs),
        "analyzable_candidate_count": sum(
            row.scope_status == PairScopeStatus.ANALYZABLE.value for row in pairs
        ),
        "excluded_candidate_count": sum(
            row.scope_status == PairScopeStatus.EXCLUDED.value for row in pairs
        ),
        "legacy_candidate_count": sum(
            row.legacy_rank is not None for row in selection.pair_decisions
        ),
        "dimension_availability_counts": dict(sorted(availability_counts.items())),
        "conclusion_strength_counts": dict(sorted(conclusion_counts.items())),
        "priority_competitors": list(priority),
        "role_buckets": selection.role_buckets,
        **buckets,
        "unknown_dimensions": unknown_dimensions,
        "review_items": review_items,
        "limitations": sorted(limitations),
        "legacy_selection_diffs": legacy_diffs,
        "input_fingerprint": input_fingerprint,
    }
    return SkuCompetitionAnalysisSummary(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_v1_1_summary_result_v1",
        ),
    )


def _generation_receipt(
    *,
    target_snapshot: VersionSkuAnalysisSnapshot,
    candidate_snapshots: Mapping[str, VersionSkuAnalysisSnapshot],
    pair_analyses: Sequence[PairAnalysisSnapshot],
    selection_result: CompetitorSelectionResult,
    input_fingerprint: str,
) -> ProfileGenerationReceipt:
    partial = any(
        row.review_required
        or row.overall_conclusion_strength == ConclusionStrength.UNKNOWN.value
        for row in pair_analyses
    )
    payload = {
        "source_status": "partial" if partial else "ready",
        "source_atoms": [
            {
                "target_snapshot_ref": target_snapshot.snapshot_ref,
                "candidate_snapshot_refs": {
                    code: row.snapshot_ref for code, row in candidate_snapshots.items()
                },
            }
        ],
        "calculation_steps": [
            {"stage": "G32", "result_hash": target_snapshot.result_hash},
            {
                "stage": "G33_G34_G35",
                "pair_result_hashes": {
                    row.candidate_sku_code: row.result_hash for row in pair_analyses
                },
                "selection_result_hash": selection_result.result_hash,
            },
            {
                "stage": "G36",
                "method_version": COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION,
            },
        ],
        "database_write": False,
        "external_publish": False,
        "input_fingerprint": input_fingerprint,
    }
    return ProfileGenerationReceipt(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_v1_1_generation_receipt_v1",
        ),
    )


def _overall_conclusion(gate: PairGateEvaluation) -> MachineReadableConclusion:
    key = next(
        (
            row
            for row in gate.business_questions
            if str(row.question_code) == "key_competitor_selection"
        ),
        None,
    )
    if key is None:
        raise CompetitorProfileV11MaterializationError(
            "G34 gate is missing the key competitor selection question"
        )
    return key.conclusion


def _dimension_result_facts(gate: PairGateEvaluation) -> list[AnalysisItem]:
    rows = []
    for state in gate.dimension_states:
        dimension_code = str(state.dimension_code)
        source_path = f"pair.dimension_results.{dimension_code}"
        known = state.availability not in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        rows.append(
            AnalysisItem(
                fact_id=state.source_result_hash,
                code=f"dimension_result:{dimension_code}",
                roles=["conclusion_support"],
                values=[
                    TypedFactValue(
                        presence="known" if known else "missing",
                        value=(
                            {
                                "availability": str(state.availability),
                                "conclusion_strength": str(
                                    state.conclusion_strength
                                ),
                                "conclusion_direction": str(
                                    state.conclusion_direction
                                ),
                            }
                            if known
                            else None
                        ),
                        unknown_reason_code=(
                            None if known else f"dimension_{state.availability}"
                        ),
                        source_path=source_path,
                        evidence_refs=state.evidence_refs,
                    )
                ],
                support_status=(
                    FactSupportStatus.SUPPORTED.value
                    if known
                    else FactSupportStatus.UNKNOWN.value
                ),
                evidence_refs=state.evidence_refs,
            )
        )
    return sorted(rows, key=lambda row: row.fact_id)


def _assert_authority(
    *,
    profile_version: ProfileVersionAnalysisContext,
    target_snapshot: VersionSkuAnalysisSnapshot,
    candidate_snapshots: Mapping[str, VersionSkuAnalysisSnapshot],
    assemblies: Mapping[str, PairAnalysisAssembly],
    gates: Mapping[str, PairGateEvaluation],
    selection: CompetitorSelectionResult,
) -> None:
    _assert_snapshot_hash(target_snapshot)
    for snapshot in candidate_snapshots.values():
        _assert_snapshot_hash(snapshot)
    scope = (
        profile_version.project_id,
        profile_version.category_code,
        profile_version.competitor_profile_version_id,
        profile_version.release_scope_key,
    )
    if profile_version.score_policy != selection.score_policy:
        raise CompetitorProfileV11MaterializationError(
            "profile context and G35 score policies must match"
        )
    if (
        target_snapshot.project_id,
        target_snapshot.category_code,
        target_snapshot.competitor_profile_version_id,
        target_snapshot.release_scope_key,
    ) != scope or target_snapshot.identity_market.sku_code != selection.target_sku_code:
        raise CompetitorProfileV11MaterializationError(
            "target snapshot must match the profile and selection authority"
        )
    if (
        selection.project_id,
        selection.category_code,
        selection.competitor_profile_version_id,
        selection.release_scope_key,
    ) != scope:
        raise CompetitorProfileV11MaterializationError(
            "G35 selection must match the profile authority"
        )
    decision_codes = {_required_candidate_code(row) for row in selection.pair_decisions}
    if set(candidate_snapshots) != decision_codes or set(gates) != decision_codes:
        raise CompetitorProfileV11MaterializationError(
            "snapshots, gates, and G35 decisions must cover the complete universe"
        )
    analyzable_codes = {
        _required_candidate_code(row)
        for row in selection.pair_decisions
        if row.scope_status == PairScopeStatus.ANALYZABLE.value
    }
    if set(assemblies) != analyzable_codes:
        raise CompetitorProfileV11MaterializationError(
            "G33 assemblies must exactly cover analyzable candidates"
        )
    if selection.analysis_candidate_count != len(analyzable_codes):
        raise CompetitorProfileV11MaterializationError(
            "G35 analyzable candidate count is stale"
        )
    for code, snapshot in candidate_snapshots.items():
        if snapshot.identity_market.sku_code != code or (
            snapshot.project_id,
            snapshot.category_code,
            snapshot.competitor_profile_version_id,
            snapshot.release_scope_key,
        ) != scope:
            raise CompetitorProfileV11MaterializationError(
                f"candidate snapshot authority mismatch: {code}"
            )
        if gates[code].scope.candidate_snapshot_ref != snapshot.snapshot_ref:
            raise CompetitorProfileV11MaterializationError(
                f"candidate snapshot ref does not resolve: {code}"
            )


def _assert_snapshot_hash(snapshot: VersionSkuAnalysisSnapshot) -> None:
    expected_ref = stable_hash(
        {
            "competitor_profile_version_id": snapshot.competitor_profile_version_id,
            "sku_code": snapshot.identity_market.sku_code,
            "input_fingerprint": snapshot.input_fingerprint,
        },
        version="competitor_profile_v1_1_sku_snapshot_ref_v1",
    )
    expected_result = stable_hash(
        snapshot.model_dump(
            mode="json",
            exclude={"schema_version", "result_hash"},
        ),
        version="competitor_profile_v1_1_sku_snapshot_result_v1",
    )
    if snapshot.snapshot_ref != expected_ref or snapshot.result_hash != expected_result:
        raise CompetitorProfileV11MaterializationError(
            f"G32 SKU snapshot hash does not close: {snapshot.identity_market.sku_code}"
        )


def _unique_by_sku(
    rows: Sequence[VersionSkuAnalysisSnapshot],
    *,
    label: str,
) -> dict[str, VersionSkuAnalysisSnapshot]:
    result = {row.identity_market.sku_code: row for row in rows}
    if len(result) != len(rows):
        raise CompetitorProfileV11MaterializationError(
            f"{label} must be unique by SKU"
        )
    return dict(sorted(result.items()))


def _unique_by_candidate(
    rows: Sequence[Any],
    *,
    label: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        code = row.candidate_sku_code
        if not code or code in result:
            raise CompetitorProfileV11MaterializationError(
                f"{label} require decoded unique candidate SKUs"
            )
        result[code] = row
    return dict(sorted(result.items()))


def _required_candidate_code(decision: PairSelectionDecision) -> str:
    if not decision.candidate_sku_code:
        raise CompetitorProfileV11MaterializationError(
            "persisted candidate universe requires a decoded candidate SKU"
        )
    return decision.candidate_sku_code


def _dedupe_models(rows: Iterable[ReviewItem]) -> list[ReviewItem]:
    keyed = {
        _canonical_json(row.model_dump(mode="json")): row
        for row in rows
    }
    return [keyed[key] for key in sorted(keyed)]


def _conclusion_evidence_refs(
    pair: PairAnalysisSnapshot,
    supporting_fact_refs: Sequence[str],
) -> list[EvidenceRef]:
    facts = {row.fact_id: row for row in pair.derived_facts}
    keyed = {
        _canonical_json(evidence.model_dump(mode="json")): evidence
        for fact_id in supporting_fact_refs
        if (fact := facts.get(fact_id)) is not None
        for evidence in fact.evidence_refs
    }
    return [keyed[key] for key in sorted(keyed)]


def _build_indexes(
    sources: Sequence[Any],
) -> tuple[dict[str, FactIndexEntry], dict[str, EvidenceRef]]:
    fact_states: dict[str, dict[str, set[str]]] = {}
    unique_evidence_payloads: dict[str, dict[str, Any]] = {}
    for source in sources:
        payload = (
            source.model_dump(mode="json")
            if callable(getattr(source, "model_dump", None))
            else source
        )
        for record in _collect_fact_records(payload):
            fact_id = str(record["fact_id"])
            state = fact_states.setdefault(
                fact_id,
                {"codes": set(), "paths": set(), "evidence": set()},
            )
            state["codes"].add(str(record["code"]))
            state["paths"].add(_fact_source_path(record))
            state["evidence"].update(
                _canonical_json(raw) for raw in _fact_evidence_payloads(record)
            )
        for raw in _collect_evidence_payloads(payload):
            unique_evidence_payloads.setdefault(_canonical_json(raw), raw)

    evidence_index: dict[str, EvidenceRef] = {}
    payload_to_key: dict[str, str] = {}
    for canonical, raw in sorted(unique_evidence_payloads.items()):
        evidence = EvidenceRef.model_validate(raw)
        normalized = evidence.model_dump(mode="json")
        key = (
            "evidence:"
            f"{stable_hash(normalized, version='competitor_profile_v1_1_evidence_v1')}"
        )
        evidence_index[key] = evidence
        payload_to_key[canonical] = key
        payload_to_key[_canonical_json(normalized)] = key
    fact_index: dict[str, FactIndexEntry] = {}
    for fact_id, state in sorted(fact_states.items()):
        codes = state["codes"]
        paths = state["paths"]
        if len(codes) != 1 or len(paths) != 1:
            raise CompetitorProfileV11MaterializationError(
                "embedded analysis fact IDs must be globally unique per fact identity: "
                f"{fact_id}"
            )
        evidence_keys = sorted(
            {
                payload_to_key[canonical]
                for canonical in state["evidence"]
            }
        )
        fact_index[fact_id] = FactIndexEntry(
            fact_id=fact_id,
            fact_code=next(iter(codes)),
            evidence_keys=evidence_keys,
            source_path=next(iter(paths)),
        )
    return dict(sorted(fact_index.items())), dict(sorted(evidence_index.items()))


def _collect_fact_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if {"fact_id", "code", "values"}.issubset(value) and isinstance(
            value["values"], list
        ):
            records.append(value)
        for child in value.values():
            records.extend(_collect_fact_records(child))
    elif isinstance(value, list):
        for child in value:
            records.extend(_collect_fact_records(child))
    return records


def _collect_evidence_payloads(value: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if isinstance(value, dict):
        required = {
            "module_code",
            "profile_version",
            "rule_version",
            "taxonomy_version",
            "record_type",
            "record_id",
            "result_hash",
        }
        if required.issubset(value):
            payloads.append(value)
        for child in value.values():
            payloads.extend(_collect_evidence_payloads(child))
    elif isinstance(value, list):
        for child in value:
            payloads.extend(_collect_evidence_payloads(child))
    return payloads


def _fact_evidence_payloads(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    payloads = [
        row for row in record.get("evidence_refs", []) if isinstance(row, dict)
    ]
    for value in record.get("values", []):
        if isinstance(value, dict):
            payloads.extend(
                row
                for row in value.get("evidence_refs", [])
                if isinstance(row, dict)
            )
    return payloads


def _fact_source_path(record: Mapping[str, Any]) -> str:
    direct = record.get("source_path")
    if isinstance(direct, str) and direct:
        return direct
    value_paths = {
        row.get("source_path")
        for row in record.get("values", [])
        if isinstance(row, dict) and isinstance(row.get("source_path"), str)
    }
    if len(value_paths) == 1:
        return str(next(iter(value_paths)))
    return f"derived.{record['code']}"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION",
    "CompetitorProfileV11MaterializationError",
    "CompetitorProfileV11Materializer",
    "HardExcludedPairMaterializationInput",
    "MaterializedCompetitorProfileV11",
]
